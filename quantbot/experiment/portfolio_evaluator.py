"""Portfolio evaluator for Stage 1 TSMOM admissibility test.

Per Component 5 specification:
  - Equal-weight long portfolio from top-5 universe signals
  - Compute per-split, per-regime: gross return (no carry), sign, trial count
  - Also compute always-long equal-weight top-5 benchmark for the same periods
  - Compare TSMOM vs benchmark per split
  - No carry — carry is unknown for altcoins

The evaluator operates on pre-aligned multi-symbol bar series and
produces structured results suitable for stage1_diagnostics.
"""

import math
from dataclasses import dataclass, field
from typing import Final

import pandas as pd

from quantbot.data.funding_loader import build_funding_lookup
from quantbot.data.quarterly_universe import get_universe_at_date
from quantbot.data.types import Bar
from quantbot.strategy.vol_state_overlay import VolStateOverlay
from quantbot.strategy.tsmom_strategy import TSMOMStrategy, TSMOM_GRID


# Train: 2 quarters (~540 8h bars), Test: 1 quarter (~270 bars)
TRAIN_BARS: Final[int] = 540
TEST_BARS: Final[int] = 270


@dataclass
class SplitResult:
    """Results for a single walkforward split."""

    split_index: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    universe: list[str]
    param_return_period: int
    param_threshold: float

    # Per-regime TSMOM results — GROSS
    tsmm_low_vol_return: float = 0.0
    tsmm_low_vol_trials: int = 0
    tsmm_low_vol_sign: str = "flat"
    tsmm_low_vol_returns: list[float] = field(default_factory=list)  # per-bar log returns

    tsmm_high_vol_return: float = 0.0
    tsmm_high_vol_trials: int = 0
    tsmm_high_vol_sign: str = "flat"
    tsmm_high_vol_returns: list[float] = field(default_factory=list)

    # Benchmark (always-long top-5 equal-weight)
    benchmark_low_vol_return: float = 0.0
    benchmark_high_vol_return: float = 0.0

    # Aggregate TSMOM (all regimes)
    tsmm_total_return: float = 0.0
    tsmm_total_trials: int = 0
    benchmark_total_return: float = 0.0

    # Net-of-carry variants (gross if funding_df is None)
    tsmm_low_vol_return_net: float = 0.0
    tsmm_high_vol_return_net: float = 0.0
    tsmm_total_return_net: float = 0.0


def _log_return(close_start: float, close_end: float) -> float:
    """Log return between two close prices."""
    if close_start <= 0 or close_end <= 0:
        return 0.0
    return math.log(close_end / close_start)


def evaluate_split(
    split_index: int,
    train_bars_by_symbol: dict[str, list[Bar]],
    test_bars_by_symbol: dict[str, list[Bar]],
    universe: list[str],
    return_period: int,
    threshold: float,
    test_start_str: str,
    test_end_str: str,
    vol_quantile: float = 0.65,
    funding_df: pd.DataFrame | None = None,
) -> SplitResult:
    """Evaluate one walkforward split.

    Args:
        split_index: Index of this split
        train_bars_by_symbol: Training bars per symbol
        test_bars_by_symbol: Test bars per symbol (aligned across symbols)
        universe: Top-5 universe symbols for this quarter
        return_period: TSMOM return period
        threshold: TSMOM threshold
        test_start_str: ISO date string for test start
        test_end_str: ISO date string for test end
        funding_df: Optional DataFrame with columns [symbol, dt, fundingRate]
            from load_all_funding(). When provided, net-of-carry returns are
            computed by subtracting |funding_rate| * 3 per bar.

    Returns:
        SplitResult with per-regime and aggregate metrics (gross + net).
    """
    # Build fast funding lookup when available
    funding_lookup: dict[tuple[str, pd.Timestamp], float] | None = None
    _funding_df = funding_df  # Store for fallback access
    if funding_df is not None and not funding_df.empty:
        funding_lookup = build_funding_lookup(funding_df)
    result = SplitResult(
        split_index=split_index,
        train_start="train_start",
        train_end="train_end",
        test_start=test_start_str,
        test_end=test_end_str,
        universe=universe,
        param_return_period=return_period,
        param_threshold=threshold,
    )

    # Determine common test length
    if not test_bars_by_symbol:
        return result

    min_test_len = min(len(bars) for bars in test_bars_by_symbol.values())
    if min_test_len == 0:
        return result

    # Initialize per-symbol overlays
    overlays: dict[str, VolStateOverlay] = {}
    for symbol in universe:
        if symbol not in test_bars_by_symbol:
            continue
        ts = TSMOMStrategy(
            return_period=return_period,
            threshold=threshold,
            symbol=symbol,
        )
        vol_ov = VolStateOverlay(tsme=ts, vol_high_quantile=vol_quantile)
        overlays[symbol] = vol_ov

    # Per-regime return accumulators — gross
    tsmm_low: list[float] = []
    tsmm_high: list[float] = []
    bench_low: list[float] = []
    bench_high: list[float] = []

    # Per-regime return accumulators — net of carry
    tsmm_low_net: list[float] = []
    tsmm_high_net: list[float] = []

    prev_close: dict[str, float] = {}
    prev_regime: dict[str, str] = {}

    for i in range(min_test_len):
        regime_at_bar: dict[str, str] = {}

        for symbol in universe:
            if symbol not in test_bars_by_symbol:
                continue
            bars = test_bars_by_symbol[symbol]
            if i >= len(bars):
                continue

            bar = bars[i]

            # Init prev_close
            if symbol not in prev_close:
                prev_close[symbol] = bar.close
                regime_at_bar[symbol] = "unknown"
                continue

            # Get regime and signal
            overlay = overlays[symbol]
            signal, regime = overlay.on_bar(bar)
            regime_at_bar[symbol] = regime

            # Per-bar log return for this symbol
            ret = _log_return(prev_close[symbol], bar.close)

            # Carry cost: |funding_rate| * 3 per bar (3 × 8h periods/day)
            carry_cost = 0.0
            if funding_lookup is not None:
                bar_dt = pd.Timestamp(bar.timestamp).tz_localize("UTC")
                key = (symbol, bar_dt)
                if key in funding_lookup:
                    fr = abs(funding_lookup[key])
                    carry_cost = fr * 3
                else:
                    # Forward-fill: try nearest prior dt for this symbol
                    sub = _funding_df[_funding_df["symbol"] == symbol]
                    leq = sub[sub["dt"] <= bar_dt]
                    if not leq.empty:
                        carry_cost = abs(float(leq.iloc[-1]["fundingRate"])) * 3

            ret_net = ret - carry_cost

            current_regime = regime if regime in ("low_vol", "high_vol") else None

            if current_regime:
                if current_regime == "low_vol":
                    bench_low.append(ret)
                    if signal is not None and signal.direction == "long":
                        tsmm_low.append(ret)
                        tsmm_low_net.append(ret_net)
                else:
                    bench_high.append(ret)
                    if signal is not None and signal.direction == "long":
                        tsmm_high.append(ret)
                        tsmm_high_net.append(ret_net)

            prev_close[symbol] = bar.close
            prev_regime[symbol] = regime

    # Aggregate — gross
    result.tsmm_low_vol_returns = list(tsmm_low)
    result.tsmm_high_vol_returns = list(tsmm_high)
    result.tsmm_low_vol_return = sum(tsmm_low) if tsmm_low else 0.0
    result.tsmm_low_vol_trials = len(tsmm_low)
    result.tsmm_low_vol_sign = "positive" if result.tsmm_low_vol_return > 0 else "negative"
    result.tsmm_high_vol_return = sum(tsmm_high) if tsmm_high else 0.0
    result.tsmm_high_vol_trials = len(tsmm_high)
    result.tsmm_high_vol_sign = "positive" if result.tsmm_high_vol_return > 0 else "negative"

    result.benchmark_low_vol_return = sum(bench_low) if bench_low else 0.0
    result.benchmark_high_vol_return = sum(bench_high) if bench_high else 0.0

    all_tsmom = tsmm_low + tsmm_high
    all_bench = bench_low + bench_high
    result.tsmm_total_return = sum(all_tsmom) if all_tsmom else 0.0
    result.tsmm_total_trials = len(all_tsmom)
    result.benchmark_total_return = sum(all_bench) if all_bench else 0.0

    # Aggregate — net of carry (funding_df None → net == gross)
    result.tsmm_low_vol_return_net = sum(tsmm_low_net) if tsmm_low_net else result.tsmm_low_vol_return
    result.tsmm_high_vol_return_net = sum(tsmm_high_net) if tsmm_high_net else result.tsmm_high_vol_return
    result.tsmm_total_return_net = result.tsmm_low_vol_return_net + result.tsmm_high_vol_return_net

    return result


def evaluate_grid(
    bars_by_symbol: dict[str, list[Bar]],
    split_bar_indices: list[tuple[int, int, int, int]],
    quarterly_dates: list[str],
    universe_by_quarter: dict[str, list[str]],
    vol_quantile: float = 0.65,
    funding_df: pd.DataFrame | None = None,
) -> list[SplitResult]:
    """Evaluate all 4 grid parameter combinations across all splits.

    Args:
        bars_by_symbol: All bars per symbol
        split_bar_indices: List of (train_start, train_end, test_start, test_end) indices
        quarterly_dates: Ordered list of quarter start dates
        universe_by_quarter: Universe per quarter date string
        funding_df: Optional funding DataFrame for net-of-carry mode.

    Returns:
        List of SplitResult objects (all params × all splits)
    """
    all_results: list[SplitResult] = []

    # Reference bars for timestamp lookup
    ref_bars = next((bars for bars in bars_by_symbol.values()), [])

    for split_idx, (train_start, train_end, test_start, test_end) in enumerate(split_bar_indices):
        # Find quarter for this split
        if test_start >= len(ref_bars):
            continue
        test_bar_ts = ref_bars[test_start].timestamp

        quarter_idx = 0
        for qi, qdate in enumerate(quarterly_dates):
            if test_bar_ts >= qdate:
                quarter_idx = qi

        qdate = quarterly_dates[quarter_idx] if quarter_idx < len(quarterly_dates) else quarterly_dates[-1]
        universe = universe_by_quarter.get(qdate, ["BTCUSDT", "ETHUSDT"])

        # Extract bars
        train_bars = {s: bars[train_start:train_end] for s, bars in bars_by_symbol.items() if train_end <= len(bars)}
        test_bars = {s: bars[test_start:test_end] for s, bars in bars_by_symbol.items() if test_end <= len(bars)}

        test_start_str = ref_bars[test_start].timestamp if test_start < len(ref_bars) else "unknown"
        test_end_str = ref_bars[min(test_end, len(ref_bars) - 1)].timestamp if test_end <= len(ref_bars) else "unknown"

        for params in TSMOM_GRID:
            rp = params["return_period"]
            th = params["threshold"]

            split_result = evaluate_split(
                split_index=split_idx,
                train_bars_by_symbol=train_bars,
                test_bars_by_symbol=test_bars,
                universe=universe,
                return_period=rp,
                threshold=th,
                test_start_str=test_start_str,
                test_end_str=test_end_str,
                vol_quantile=vol_quantile,
                funding_df=funding_df,
            )
            all_results.append(split_result)

    return all_results
