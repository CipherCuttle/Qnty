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
    )

    # Run gate checks and attach verdict
    result.gate_verdict = gate_experiment_result(result)

    # Write deterministic result artifact (now includes gate_verdict)
    result.write_json(result_path)

    return result
