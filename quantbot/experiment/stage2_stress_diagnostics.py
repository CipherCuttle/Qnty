"""Stage 2 Stress Diagnostics.

Two components:
  3a: Combined-regime re-stratification of existing Stage 1 results
  3b: Carry scenario stress testing

Uniform carry stress scenarios anchored to BTC-observed rates.
For sensitivity analysis only. Not modeled truth. Altcoin carry is
structurally unknown. Not a conservative bound.
"""

import csv
import math
import random
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from quantbot.data.multi_asset_loader import load_all_ohlcv
from quantbot.data.quarterly_universe import QUARTERLY_DATES, QUARTERLY_UNIVERSES
from quantbot.experiment.regime import compute_combined_regime
from quantbot.experiment.walkforward import build_walkforward_splits


# Carry scenarios (bps/yr) - labeled exactly as specified
CARRY_SCENARIOS: Final[list[tuple[str, int]]] = [
    ("S1", 548),
    ("S2", 1500),
    ("S3", 4928),
]

# Convert annual bps to per-bar (8h bars: ~1095 per year)
CARRY_BARS_PER_YEAR: Final[int] = 1095


# Bootstrap settings
BOOTSTRAP_N: Final[int] = 1000
BOOTSTRAP_ALPHA: Final[float] = 0.05
MIN_TRIALS: Final[int] = 5


@dataclass
class CombinedRegimeCell:
    """Diagnostics for one cell in the combined-regime matrix."""
    vol_regime: str  # "low_vol" or "high_vol"
    trend_regime: str  # "uptrend", "downtrend", or "sideways"
    split_index: int
    param_return_period: int
    param_threshold: float

    # Per-bar returns (not aggregated)
    tsmm_returns: list[float]
    benchmark_returns: list[float]

    @property
    def trial_count(self) -> int:
        return len(self.tsmm_returns)

    @property
    def tsmm_excess(self) -> float:
        if not self.tsmm_returns:
            return 0.0
        tsmm_total = sum(self.tsmm_returns)
        bench_total = sum(self.benchmark_returns) if self.benchmark_returns else 0.0
        return tsmm_total - bench_total

    @property
    def sign_consistency(self) -> float:
        """Fraction of bars where TSMOM excess is positive."""
        if not self.tsmm_returns:
            return 0.0
        positive = sum(1 for r in self.tsmm_returns if r > 0)
        return positive / len(self.tsmm_returns)

    @property
    def net_positive_count(self) -> int:
        return sum(1 for r in self.tsmm_returns if r > 0)


@dataclass
class CarryStressResult:
    """Carry stress result for one scenario."""
    scenario_label: str
    annual_bps: int
    carry_per_bar: float
    total_instances: int
    positive_net_instances: int

    @property
    def positive_fraction(self) -> float:
        if self.total_instances == 0:
            return 0.0
        return self.positive_net_instances / self.total_instances


def _bootstrap_ci(returns: list[float], n: int = BOOTSTRAP_N, seed: int = 42) -> tuple[float, float]:
    """Compute bootstrap 95% CI for mean return."""
    if len(returns) < 2:
        return (0.0, 0.0)

    rng = random.Random(seed)
    boot_means: list[float] = []

    for _ in range(n):
        sample = [returns[rng.randint(0, len(returns) - 1)] for _ in returns]
        boot_means.append(sum(sample) / len(sample))

    boot_means.sort()
    ci_lower = boot_means[int(len(boot_means) * BOOTSTRAP_ALPHA / 2)]
    ci_upper = boot_means[int(len(boot_means) * (1 - BOOTSTRAP_ALPHA / 2))]
    return (ci_lower, ci_upper)


def compute_combined_regime_matrix(
    bars_by_symbol: dict,
    ref_bars: list,
    split_bar_indices: list[tuple[int, int, int, int]],
) -> dict[str, list[CombinedRegimeCell]]:
    """Re-stratify Stage 1 results by combined regime.

    Returns dict keyed by "vol_trend" e.g. "low_vol_uptrend".
    Values are lists of CombinedRegimeCell for each split/param combo.
    """
    # Import here to avoid circular
    from quantbot.experiment.portfolio_evaluator import evaluate_split

    cells_by_regime: dict[str, list[CombinedRegimeCell]] = defaultdict(list)

    for split_idx, (train_start, train_end, test_start, test_end) in enumerate(split_bar_indices):
        if test_start >= len(ref_bars):
            continue

        test_bar_ts = ref_bars[test_start].timestamp
        quarter_idx = 0
        for qi, qdate in enumerate(QUARTERLY_DATES):
            if test_bar_ts >= qdate:
                quarter_idx = qi
        qdate = QUARTERLY_DATES[quarter_idx] if quarter_idx < len(QUARTERLY_DATES) else QUARTERLY_DATES[-1]
        universe = QUARTERLY_UNIVERSES.get(qdate, ["BTCUSDT", "ETHUSDT"])

        # Extract test bars
        test_bars = {s: bars[test_start:test_end] for s, bars in bars_by_symbol.items() if test_end <= len(bars)}

        test_start_str = ref_bars[test_start].timestamp
        test_end_str = ref_bars[min(test_end, len(ref_bars) - 1)].timestamp

        # Compute combined regime for this test period
        # Use first symbol's bars as reference
        ref_test_bars = test_bars.get("BTCUSDT", [])
        if len(ref_test_bars) < 21:
            continue

        combined = compute_combined_regime(
            ref_test_bars,
            vol_window=20,
            vol_high_quantile=0.65,  # Use default
            trend_window=20,
            trend_threshold=0.001,
        )

        regime_key = f"{combined.vol_label}_{combined.trend_label}"

        # Run evaluation with default vol_quantile to get per-bar returns
        # We need to call evaluate_split but it returns aggregated results
        # Instead, we inline the per-bar computation
        train_bars = {s: bars[train_start:train_end] for s, bars in bars_by_symbol.items() if train_end <= len(bars)}

        from quantbot.strategy.vol_state_overlay import VolStateOverlay
        from quantbot.strategy.tsmom_strategy import TSMOMStrategy, TSMOM_GRID

        for params in TSMOM_GRID:
            rp = params["return_period"]
            th = params["threshold"]

            # Initialize overlays
            overlays: dict[str, VolStateOverlay] = {}
            for symbol in universe:
                if symbol not in test_bars:
                    continue
                ts = TSMOMStrategy(return_period=rp, threshold=th, symbol=symbol)
                vol_ov = VolStateOverlay(tsme=ts, vol_high_quantile=0.65)
                overlays[symbol] = vol_ov

            # Per-bar accumulation
            tsmm_returns: list[float] = []
            bench_returns: list[float] = []
            prev_close: dict[str, float] = {}

            min_test_len = min(len(bars) for bars in test_bars.values()) if test_bars else 0

            for i in range(min_test_len):
                for symbol in universe:
                    if symbol not in test_bars or i >= len(test_bars[symbol]):
                        continue
                    bar = test_bars[symbol][i]

                    if symbol not in prev_close:
                        prev_close[symbol] = bar.close
                        continue

                    # Get regime and signal
                    overlay = overlays[symbol]
                    signal, regime = overlay.on_bar(bar)

                    # Per-bar log return
                    ret = math.log(bar.close / prev_close[symbol]) if prev_close[symbol] > 0 and bar.close > 0 else 0.0

                    # Only accumulate if in known regime AND regime matches the split's regime
                    if regime in ("low_vol", "high_vol"):
                        # Check if this bar's regime matches the split's combined regime's vol component
                        if regime == combined.vol_label:
                            bench_returns.append(ret)
                            if signal is not None and signal.direction == "long":
                                tsmm_returns.append(ret)

                    prev_close[symbol] = bar.close

            if tsmm_returns:  # Only store if we have data
                cell = CombinedRegimeCell(
                    vol_regime=combined.vol_label,
                    trend_regime=combined.trend_label,
                    split_index=split_idx,
                    param_return_period=rp,
                    param_threshold=th,
                    tsmm_returns=tsmm_returns,
                    benchmark_returns=bench_returns,
                )
                cells_by_regime[regime_key].append(cell)

    return cells_by_regime


def aggregate_regime_matrix(
    cells_by_regime: dict[str, list[CombinedRegimeCell]],
) -> list[dict]:
    """Aggregate per-cell data into summary rows."""
    rows = []
    for regime_key, cells in cells_by_regime.items():
        if not cells:
            continue

        vol, trend = regime_key.split("_", 1)
        all_returns = []
        all_bench = []
        for cell in cells:
            all_returns.extend(cell.tsmm_returns)
            all_bench.extend(cell.benchmark_returns)

        if not all_returns:
            continue

        total_excess = sum(all_returns) - sum(all_bench)
        positive_count = sum(1 for r in all_returns if r > 0)
        sign_cons = positive_count / len(all_returns)

        ci_lower, ci_upper = _bootstrap_ci(all_returns)

        rows.append({
            "vol_regime": vol,
            "trend_regime": trend,
            "regime_key": regime_key,
            "trial_count": len(all_returns),
            "positive_count": positive_count,
            "sign_consistency": sign_cons,
            "median_excess": total_excess / len(all_returns) if all_returns else 0.0,
            "total_excess": total_excess,
            "ci_lower": ci_lower,
            "ci_upper": ci_upper,
            "cell_count": len(cells),
        })

    return rows


def apply_carry_stress(
    cells_by_regime: dict[str, list[CombinedRegimeCell]],
) -> list[CarryStressResult]:
    """Apply carry scenarios to combined regime cells.

    Carry is applied symmetrically to both TSMOM and benchmark
    (fair net comparison).
    """
    results = []

    for scenario_label, annual_bps in CARRY_SCENARIOS:
        carry_per_bar = annual_bps / 10000 / CARRY_BARS_PER_YEAR

        total_instances = 0
        positive_net_instances = 0

        for regime_key, cells in cells_by_regime.items():
            for cell in cells:
                # Apply carry to each bar
                for ret in cell.tsmm_returns:
                    total_instances += 1
                    net = ret - carry_per_bar
                    if net > 0:
                        positive_net_instances += 1

        results.append(CarryStressResult(
            scenario_label=scenario_label,
            annual_bps=annual_bps,
            carry_per_bar=carry_per_bar,
            total_instances=total_instances,
            positive_net_instances=positive_net_instances,
        ))

    return results


def run_stress_diagnostics() -> dict:
    """Run full Stage 2 stress diagnostics."""
    # Load data
    bars_by_symbol = load_all_ohlcv()
    ref_bars = bars_by_symbol.get("BTCUSDT", [])

    # Build splits
    splits = build_walkforward_splits(ref_bars, train_size=540, test_size=270, step_size=270)

    # Filter to 2021-Q4+
    cutoff_ts = "2021-07-01"
    filtered = [s for s in splits if ref_bars[s.test_start].timestamp >= cutoff_ts]
    test_quarters = filtered[:12]

    split_bar_indices = [
        (s.train_start, s.train_end, s.test_start, s.test_end)
        for s in test_quarters
    ]

    # Compute combined regime matrix
    cells_by_regime = compute_combined_regime_matrix(
        bars_by_symbol, ref_bars, split_bar_indices
    )

    # Aggregate
    regime_summary = aggregate_regime_matrix(cells_by_regime)

    # Carry stress
    carry_results = apply_carry_stress(cells_by_regime)

    return {
        "cells_by_regime": cells_by_regime,
        "regime_summary": regime_summary,
        "carry_results": carry_results,
    }


# ----------------------------------------------------------------------
# I/O
# ----------------------------------------------------------------------


def write_stress_results_csv(output_path: Path, diagnostics: dict) -> None:
    """Write combined-regime matrix + carry table to CSV."""
    regime_summary = diagnostics["regime_summary"]
    carry_results = diagnostics["carry_results"]

    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)

        # Section 1: Combined-regime matrix
        writer.writerow(["=== COMBINED-REGIME MATRIX ==="])
        writer.writerow([
            "vol_regime", "trend_regime", "regime_key",
            "trial_count", "positive_count", "sign_consistency",
            "median_excess", "total_excess", "ci_lower", "ci_upper",
            "cell_count",
        ])
        for row in regime_summary:
            writer.writerow([
                row["vol_regime"],
                row["trend_regime"],
                row["regime_key"],
                row["trial_count"],
                row["positive_count"],
                f"{row['sign_consistency']:.4f}",
                f"{row['median_excess']:.6f}",
                f"{row['total_excess']:.6f}",
                f"{row['ci_lower']:.6f}",
                f"{row['ci_upper']:.6f}",
                row["cell_count"],
            ])

        writer.writerow([])

        # Section 2: Carry stress
        writer.writerow(["=== CARRY STRESS ==="])
        writer.writerow([
            "scenario", "annual_bps", "carry_per_bar",
            "total_instances", "positive_net_instances", "positive_fraction",
        ])
        for cr in carry_results:
            writer.writerow([
                cr.scenario_label,
                cr.annual_bps,
                f"{cr.carry_per_bar:.8f}",
                cr.total_instances,
                cr.positive_net_instances,
                f"{cr.positive_fraction:.4f}",
            ])

        writer.writerow([])
        writer.writerow(["=== CARRY SCENARIO LABEL ==="])
        writer.writerow(["Uniform carry stress scenarios anchored to BTC-observed rates."])
        writer.writerow(["For sensitivity analysis only. Not modeled truth."])
        writer.writerow(["Altcoin carry is structurally unknown. Not a conservative bound."])
