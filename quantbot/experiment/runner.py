"""Minimal experiment runner for QuantBot.

Paper mode only - no real trading, no profitability claims.
"""

from pathlib import Path
from typing import Any

from quantbot.core.determinism import sha256_file
from quantbot.data.loaders import load_bars_from_csv
from quantbot.data.manifest import ManifestVerifier
from quantbot.experiment.gates import gate_experiment_result
from quantbot.experiment.result import ExperimentResult
from quantbot.experiment.spec import ExperimentSpec
from quantbot.replay.runner import ReplayRunner
from quantbot.version import ENGINE_VERSION


# Strategy class registry - minimal factory
_STRATEGY_REGISTRY: dict[str, type] = {}


def _register_strategy(cls: type) -> type:
    """Decorator to register a strategy class in the registry."""
    _STRATEGY_REGISTRY[cls.__name__] = cls
    return cls


def _build_strategy(strategy_name: str, params: dict[str, Any]) -> Any:
    """Build a strategy instance from name and parameters.

    Args:
        strategy_name: Name of the strategy class.
        params: Dict of parameters to pass to the strategy constructor.

    Returns:
        Strategy instance.

    Raises:
        ValueError: If strategy_name is not found in registry.
    """
    if strategy_name not in _STRATEGY_REGISTRY:
        raise ValueError(
            f"Strategy '{strategy_name}' not found in registry. "
            f"Available: {list(_STRATEGY_REGISTRY.keys())}"
        )
    cls = _STRATEGY_REGISTRY[strategy_name]
    return cls(**params)


def _count_signals_by_direction(strategy, bars) -> tuple[int, int, int]:
    """Count long/short/flat signals from a strategy run.

    Args:
        strategy: Strategy instance with on_bar method.
        bars: List of bars to process.

    Returns:
        Tuple of (long_count, short_count, flat_count).
    """
    long_count = 0
    short_count = 0
    flat_count = 0

    for bar in bars:
        sig = strategy.on_bar(bar)
        if sig is not None:
            direction = getattr(sig, "direction", None)
            if direction == "long":
                long_count += 1
            elif direction == "short":
                short_count += 1
            else:
                flat_count += 1

    return long_count, short_count, flat_count


def _compute_economics_summary(strategy, bars, fee_bps: float, slippage_bps: float):
    """Compute event accounting from position transitions.

    Tracks explicit position transitions that incur costs:
    - entry: position opens (None -> long/short)
    - exit: position closes (long/short -> None)
    - flip: position reverses (long -> short or short -> long)

    A flip counts as exit + entry (2 cost-bearing events).

    Args:
        strategy: Strategy instance with on_bar method.
        bars: List of bars to process.
        fee_bps: Fee in basis points.
        slippage_bps: Slippage in basis points.

    Returns:
        EconomicsSummary with event counts and cost estimates.
    """
    from quantbot.experiment.result import EconomicsSummary

    entry_count = 0
    exit_count = 0
    flip_count = 0
    prev_direction = None  # None, "long", or "short"

    for bar in bars:
        sig = strategy.on_bar(bar)
        if sig is None:
            # Signal is flat/neutral
            if prev_direction is not None:
                # Position was open, now closed
                exit_count += 1
                prev_direction = None
        else:
            direction = getattr(sig, "direction", None)
            if direction is None or direction == "flat":
                # Signal is flat/neutral
                if prev_direction is not None:
                    # Position was open, now closed
                    exit_count += 1
                    prev_direction = None
            elif direction == "long":
                if prev_direction is None:
                    # Entry from flat
                    entry_count += 1
                elif prev_direction == "short":
                    # Flip from short to long
                    flip_count += 1
                prev_direction = "long"
            elif direction == "short":
                if prev_direction is None:
                    # Entry from flat
                    entry_count += 1
                elif prev_direction == "long":
                    # Flip from long to short
                    flip_count += 1
                prev_direction = "short"

    # cost_side_count = entries + exits (flips count as 2 since they are exit+entry)
    cost_side_count = entry_count + exit_count + flip_count
    assumed_total_cost_bps = cost_side_count * (fee_bps + slippage_bps)

    return EconomicsSummary(
        cost_side_count=cost_side_count,
        entry_count=entry_count,
        exit_count=exit_count,
        flip_count=flip_count,
        fee_bps=fee_bps,
        slippage_bps=slippage_bps,
        assumed_total_cost_bps=assumed_total_cost_bps,
    )


def _compute_return_summary(strategy, bars, economics_summary):
    """Compute gross and net return series from position state and bar close changes.

    Derives position state deterministically from signals:
    - When signal changes direction, position state changes
    - First bar with non-flat signal establishes initial position

    Gross return series:
    - Long position: return = (close_t - close_{t-1}) / close_{t-1}
    - Short position: return = -(close_t - close_{t-1}) / close_{t-1}
    - Flat position: return = 0

    Net return = gross return - event-based costs (applied as bps of notional per event).
    Per-bar net return distributes total cost evenly across bars held.

    Args:
        strategy: Strategy instance with on_bar method.
        bars: List of bars to process.
        economics_summary: EconomicsSummary with cost_side_count and assumed_total_cost_bps.

    Returns:
        Tuple of (ReturnSummary, ReturnSeries) with aggregate and per-bar data.
    """
    from quantbot.experiment.result import ReturnSeries, ReturnSummary

    if len(bars) < 2:
        return ReturnSummary(), ReturnSeries()

    # Build position state series from signals
    position_states: list[str] = []  # "long", "short", "flat"
    prev_direction = None

    for i, bar in enumerate(bars):
        sig = strategy.on_bar(bar)
        if sig is None:
            direction = "flat"
        else:
            direction = getattr(sig, "direction", "flat")
            if direction is None:
                direction = "flat"

        # First non-flat signal establishes initial position
        if prev_direction is None and direction != "flat":
            prev_direction = direction

        position_states.append(prev_direction if prev_direction is not None else "flat")

        # Update prev_direction for next iteration
        if direction != "flat":
            prev_direction = direction
        elif prev_direction is not None and direction == "flat":
            # Position closed
            prev_direction = None

    # Compute gross returns from bar-to-bar close changes
    gross_return_total = 1.0
    bars_held = 0
    winning_bars = 0
    losing_bars = 0
    gross_returns: list[float] = []
    bar_timestamps: list[str] = []

    # Per-bar cost for net return calculation (distributed evenly)
    cost_per_event = economics_summary.assumed_total_cost_bps / 10000.0
    cost_deduction_total = economics_summary.cost_side_count * cost_per_event

    for i in range(1, len(bars)):
        prev_close = bars[i - 1].close
        curr_close = bars[i].close
        position = position_states[i]

        if position == "flat":
            bar_return = 0.0
        elif position == "long":
            bar_return = (curr_close - prev_close) / prev_close
        elif position == "short":
            bar_return = -(curr_close - prev_close) / prev_close
        else:
            bar_return = 0.0

        gross_return_total *= (1 + bar_return)
        gross_returns.append(bar_return)
        bar_timestamps.append(bars[i].timestamp)

        if position != "flat":
            bars_held += 1
            if bar_return > 0:
                winning_bars += 1
            elif bar_return < 0:
                losing_bars += 1

    # Convert from product of (1 + r) to simple return
    gross_return_total = gross_return_total - 1.0

    # Per-bar net cost (distributed evenly across bars held)
    per_bar_net_cost = cost_deduction_total / bars_held if bars_held > 0 else 0.0

    # Compute net returns per bar
    net_returns: list[float] = []
    for i, gross_ret in enumerate(gross_returns):
        position = position_states[i + 1]  # position_states is offset by 1 vs gross_returns
        if position != "flat":
            net_returns.append(gross_ret - per_bar_net_cost)
        else:
            net_returns.append(0.0)

    net_return_total = gross_return_total - cost_deduction_total

    return_summary = ReturnSummary(
        gross_return_total=gross_return_total,
        net_return_total=net_return_total,
        cost_deduction_total=cost_deduction_total,
        bars_held=bars_held,
        winning_bars=winning_bars,
        losing_bars=losing_bars,
    )

    return_series = ReturnSeries(
        gross_returns=gross_returns,
        net_returns=net_returns,
        bar_timestamps=bar_timestamps,
        interval="unknown",  # Interval not reliably determinable here
    )

    return return_summary, return_series


def run_experiment(
    spec: ExperimentSpec,
    manifest_path: Path,
    csv_path: Path,
    output_dir: Path,
) -> ExperimentResult:
    """Run a deterministic experiment from spec through receipt.

    Steps:
        1. Verify manifest.
        2. Load bars from CSV.
        3. Build strategy from spec.
        4. Run replay with strategy.
        5. Count signals by direction.
        6. Produce ExperimentResult.

    Args:
        spec: ExperimentSpec describing the experiment.
        manifest_path: Path to manifest JSON file.
        csv_path: Path to bars CSV file.
        output_dir: Directory for output files.

    Returns:
        ExperimentResult with spec, receipt path, and summary counts.

    Raises:
        AssertionError: If manifest verification fails.
        ValueError: If strategy_name not in registry.
    """
    # Step 1: verify manifest
    verifier = ManifestVerifier(manifest_path)
    base_dir = manifest_path.parent
    assert verifier.verify_all(base_dir), (
        f"Manifest verification failed for {manifest_path}"
    )

    # Step 2: load bars
    bars = load_bars_from_csv(csv_path)

    # Step 3: build strategy from spec
    strategy = _build_strategy(spec.strategy_name, spec.strategy_params)

    # Step 4: run replay
    runner = ReplayRunner(bars, strategy=strategy)
    receipt = runner.run()

    # Step 5: write receipt to output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = output_dir / "receipt.json"

    # Import canonical_json_dumps locally to avoid circular
    from quantbot.core.determinism import canonical_json_dumps

    receipt_json = canonical_json_dumps(receipt.to_dict())
    receipt_path.write_text(receipt_json, encoding="utf-8")

    # Compute receipt digest
    receipt_digest = sha256_file(receipt_path)

    # Step 6: count signals by direction (need to re-run since runner consumed bars)
    # Re-create strategy instance for counting
    strategy_for_count = _build_strategy(spec.strategy_name, spec.strategy_params)
    long_count, short_count, flat_count = _count_signals_by_direction(
        strategy_for_count, bars
    )

    # Step 7: compute event accounting for economics
    strategy_for_economics = _build_strategy(spec.strategy_name, spec.strategy_params)
    economics_summary = _compute_economics_summary(
        strategy_for_economics, bars, spec.fee_bps, spec.slippage_bps
    )

    # Step 8: compute return series from position state and bar close changes
    strategy_for_returns = _build_strategy(spec.strategy_name, spec.strategy_params)
    return_summary, return_series = _compute_return_summary(
        strategy_for_returns, bars, economics_summary
    )

    result_path = output_dir / "experiment_result.json"
    result = ExperimentResult(
        spec=spec,
        receipt_path=receipt_path,
        result_path=result_path,
        receipt_digest=receipt_digest,
        bar_count=receipt.bar_count,
        signal_count=receipt.signal_count,
        first_timestamp=receipt.first_timestamp,
        last_timestamp=receipt.last_timestamp,
        long_count=long_count,
        short_count=short_count,
        flat_count=flat_count,
        engine_version=ENGINE_VERSION,
        fee_bps=spec.fee_bps,
        slippage_bps=spec.slippage_bps,
        economics_summary=economics_summary,
        return_summary=return_summary,
        return_series=return_series,
    )

    # Run gate checks and attach verdict
    result.gate_verdict = gate_experiment_result(result)

    # Write deterministic result artifact (now includes gate_verdict)
    result.write_json(result_path)

    return result
