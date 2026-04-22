"""Stage 1 TSMOM Admissibility Diagnostic Surfaces.

Per Component 6 specification:
  - Per-split, per-regime: sign consistency, bootstrap distribution,
    median/mean return stability, trial count (must be >=5 for any regime claim)
  - Output: docs/verdicts/stage1_verdict.md compatible structured results
  - Funding sensitivity table (BTC only, 548/1500/4928 bps/yr as sensitivity rows)

PASS criteria:
  TSMOM+vol-overlay shows sign consistency OR rank evidence OR return stability
  materially above always-long benchmark across test quarters, with >=5 trials
  per regime per split, and bootstrap distribution not centered at zero.

FAIL criteria:
  TSMOM indistinguishable from or worse than always-long benchmark;
  no sign consistency; bootstrap distribution centered near zero; insufficient trials.

CONTINUE: Mixed evidence; needs explicit conditions to proceed.
"""

import csv
import math
import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final

from quantbot.experiment.portfolio_evaluator import SplitResult, evaluate_grid
from quantbot.experiment.walkforward import build_walkforward_splits, WalkForwardSplit
from quantbot.data.multi_asset_loader import load_all_ohlcv
from quantbot.data.quarterly_universe import (
    QUARTERLY_DATES,
    QUARTERLY_UNIVERSES,
    MATIC_CUTOFF,
)


# Bootstrap settings
BOOTSTRAP_N: Final[int] = 1000
BOOTSTRAP_ALPHA: Final[float] = 0.05  # 95% CI

# Minimum trials per regime to make a claim
MIN_TRIALS: Final[int] = 5

# Funding rate rows (bps/yr) for BTC-only sensitivity
BTC_FUNDING_RATES: list[int] = [548, 1500, 4928]


@dataclass
class RegimeDiagnostics:
    """Diagnostic surfaces for one regime in one split."""

    split_index: int
    regime: str  # "low_vol" or "high_vol"
    test_start: str
    test_end: str
    param_return_period: int
    param_threshold: float

    # Raw metrics
    tsmm_return: float
    benchmark_return: float
    trial_count: int
    sign: str  # "positive", "negative", "flat"

    # Bootstrap
    bootstrap_mean: float
    bootstrap_median: float
    bootstrap_std: float
    bootstrap_ci_lower: float
    bootstrap_ci_upper: float

    # Comparison vs benchmark
    excess_return: float  # tsmm_return - benchmark_return
    sign_consistency: float  # fraction of quarters positive (0.0 to 1.0)
    rank_vs_benchmark: str  # "above", "below", "equal"


@dataclass
class SplitDiagnostics:
    """Full diagnostics for one split across both regimes."""

    split_index: int
    test_start: str
    test_end: str
    universe: list[str]
    param_return_period: int
    param_threshold: float

    low_vol: RegimeDiagnostics | None
    high_vol: RegimeDiagnostics | None

    total_tsmm_return: float
    total_benchmark_return: float
    total_excess_return: float
    total_trial_count: int


@dataclass
class Stage1Verdict:
    """Final verdict and summary for Stage 1."""

    verdict: str  # "PASS", "FAIL", "CONTINUE"
    reasoning: list[str]
    splits_tested: int
    params_tested: int
    quarters_covered: list[str]

    # Per-regime summary
    low_vol_pass: bool
    high_vol_pass: bool

    # Bootstrap evidence
    bootstrap_centered_near_zero: bool

    # Trial adequacy
    all_regimes_adequate_trials: bool

    # Funding sensitivity (BTC only)
    btc_funding_sensitivity: dict[int, float]  # bps/yr -> return delta

    # Full split diagnostics
    split_diagnostics: list[SplitDiagnostics]


def _bootstrap_stats(returns: list[float], n: int = BOOTSTRAP_N, seed: int = 42) -> tuple[float, float, float, float, float]:
    """Bootstrap statistics for a list of returns.

    Returns:
        (mean, median, std, ci_lower, ci_upper)
    """
    if len(returns) < 2:
        return (0.0, 0.0, 0.0, 0.0, 0.0)

    rng = random.Random(seed)
    boot_means: list[float] = []

    for _ in range(n):
        sample = [returns[rng.randint(0, len(returns) - 1)] for _ in returns]
        boot_means.append(sum(sample) / len(sample))

    boot_means.sort()
    mean = sum(boot_means) / len(boot_means)
    median = boot_means[len(boot_means) // 2]
    std = math.sqrt(sum((x - mean) ** 2 for x in boot_means) / len(boot_means))
    ci_lower = boot_means[int(len(boot_means) * BOOTSTRAP_ALPHA / 2)]
    ci_upper = boot_means[int(len(boot_means) * (1 - BOOTSTRAP_ALPHA / 2))]

    return mean, median, std, ci_lower, ci_upper


def _compute_regime_diagnostics(result: SplitResult, regime_key: str) -> RegimeDiagnostics | None:
    """Compute regime-level diagnostics from a SplitResult.

    Uses the stored per-regime return lists for bootstrap computation.
    """
    if regime_key == "low_vol":
        tsmm_ret = result.tsmm_low_vol_return
        trials = result.tsmm_low_vol_trials
        sign = result.tsmm_low_vol_sign
        bench_ret = result.benchmark_low_vol_return
        returns = result.tsmm_low_vol_returns
    elif regime_key == "high_vol":
        tsmm_ret = result.tsmm_high_vol_return
        trials = result.tsmm_high_vol_trials
        sign = result.tsmm_high_vol_sign
        bench_ret = result.benchmark_high_vol_return
        returns = result.tsmm_high_vol_returns
    else:
        return None

    if trials < MIN_TRIALS:
        return None

    boot_mean, boot_median, boot_std, ci_lo, ci_hi = _bootstrap_stats(returns) if returns else (0.0, 0.0, 0.0, 0.0, 0.0)

    return RegimeDiagnostics(
        split_index=result.split_index,
        regime=regime_key,
        test_start=result.test_start,
        test_end=result.test_end,
        param_return_period=result.param_return_period,
        param_threshold=result.param_threshold,
        tsmm_return=tsmm_ret,
        benchmark_return=bench_ret,
        trial_count=trials,
        sign=sign,
        bootstrap_mean=boot_mean,
        bootstrap_median=boot_median,
        bootstrap_std=boot_std,
        bootstrap_ci_lower=ci_lo,
        bootstrap_ci_upper=ci_hi,
        excess_return=tsmm_ret - bench_ret,
        sign_consistency=1.0 if tsmm_ret > 0 else 0.0,
        rank_vs_benchmark="above" if tsmm_ret > bench_ret else "below" if tsmm_ret < bench_ret else "equal",
    )


def _compute_split_diagnostics(result: SplitResult) -> SplitDiagnostics:
    """Compute full split diagnostics from a SplitResult."""
    low_vol_diag = _compute_regime_diagnostics(result, "low_vol")
    high_vol_diag = _compute_regime_diagnostics(result, "high_vol")

    return SplitDiagnostics(
        split_index=result.split_index,
        test_start=result.test_start,
        test_end=result.test_end,
        universe=result.universe,
        param_return_period=result.param_return_period,
        param_threshold=result.param_threshold,
        low_vol=low_vol_diag,
        high_vol=high_vol_diag,
        total_tsmm_return=result.tsmm_total_return,
        total_benchmark_return=result.benchmark_total_return,
        total_excess_return=result.tsmm_total_return - result.benchmark_total_return,
        total_trial_count=result.tsmm_total_trials,
    )


def run_stage1_diagnostics() -> Stage1Verdict:
    """Run the full Stage 1 diagnostic pipeline.

    Returns:
        Stage1Verdict with all diagnostic surfaces and the final PASS/FAIL/CONTINUE verdict.
    """
    # Load data
    bars_by_symbol = load_all_ohlcv()

    if not bars_by_symbol:
        raise ValueError("No OHLCV data loaded — check data/ directory")

    # Use BTC as reference for bar alignment
    ref_bars = bars_by_symbol.get("BTCUSDT", [])
    if not ref_bars:
        raise ValueError("BTCUSDT data required for alignment")

    # Build walkforward splits
    train_size = 540   # ~2 quarters of 8h bars
    test_size = 270    # ~1 quarter
    step_size = 270    # contiguous non-overlapping

    splits = build_walkforward_splits(ref_bars, train_size, test_size, step_size)

    if len(splits) < 3:
        raise ValueError(f"Insufficient data for walkforward: only {len(splits)} splits")

    # Filter splits to start from Q3 2021 or later
    cutoff_ts = "2021-07-01"
    filtered_splits: list[WalkForwardSplit] = [
        s for s in splits
        if ref_bars[s.test_start].timestamp >= cutoff_ts
    ]

    if not filtered_splits:
        filtered_splits = splits

    # Limit to 8-12 test quarters
    test_quarters = filtered_splits[:12]

    # Build split_bar_indices
    split_bar_indices = [
        (s.train_start, s.train_end, s.test_start, s.test_end)
        for s in test_quarters
    ]

    # Evaluate all grid params across all splits
    results = evaluate_grid(
        bars_by_symbol=bars_by_symbol,
        split_bar_indices=split_bar_indices,
        quarterly_dates=QUARTERLY_DATES,
        universe_by_quarter=QUARTERLY_UNIVERSES,
    )

    # Group results by split_index
    by_split: defaultdict[int, list[SplitResult]] = defaultdict(list)
    for r in results:
        by_split[r.split_index].append(r)

    # Compute per-split diagnostics
    split_diags = [_compute_split_diagnostics(r) for r in results]

    # BTC funding sensitivity (secondary context only)
    btc_funding_sensitivity: dict[int, float] = {}
    for bps in BTC_FUNDING_RATES:
        annual_rate = bps / 10000
        per_bar_cost = annual_rate / 1095
        btc_funding_sensitivity[bps] = -per_bar_cost

    # --- Compute verdict ---
    all_regime_pass: list[bool] = []
    bootstrap_ci_includes_zero_list: list[bool] = []
    trial_adequate = True

    for r in results:
        for regime_key in ("low_vol", "high_vol"):
            diag = _compute_regime_diagnostics(r, regime_key)
            if diag is None:
                continue
            if diag.trial_count < MIN_TRIALS:
                trial_adequate = False
            # Check bootstrap centering: does 95% CI include zero?
            # If zero IS in the CI, the mean is not statistically bounded away from zero
            ci_includes_zero = diag.bootstrap_ci_lower <= 0 <= diag.bootstrap_ci_upper
            bootstrap_ci_includes_zero_list.append(ci_includes_zero)
            # Pass criteria: above benchmark AND positive return
            pass_regime = (
                diag.excess_return > 0
                and diag.sign == "positive"
                and diag.trial_count >= MIN_TRIALS
            )
            all_regime_pass.append(pass_regime)

    pass_fraction = sum(all_regime_pass) / max(len(all_regime_pass), 1)
    zero_in_ci_frac = sum(bootstrap_ci_includes_zero_list) / max(len(bootstrap_ci_includes_zero_list), 1)
    bootstrap_centered = zero_in_ci_frac > 0.5

    # Determine verdict
    if pass_fraction >= 0.6 and not bootstrap_centered and trial_adequate:
        verdict_label = "PASS"
        reasoning = [
            f"Sign consistency: {pass_fraction:.0%} of regime instances beat benchmark",
            f"Bootstrap 95% CI excludes zero in {1-zero_in_ci_frac:.0%} of regime instances (not centered)",
            f"Trial adequacy: {'adequate' if trial_adequate else 'inadequate'}",
        ]
    elif pass_fraction < 0.3 or bootstrap_centered:
        verdict_label = "FAIL"
        reasoning = [
            f"Sign consistency insufficient: {pass_fraction:.0%} beat benchmark",
            f"Bootstrap 95% CI includes zero in {zero_in_ci_frac:.0%} of regime instances (centered)",
            f"Trial adequacy: {'adequate' if trial_adequate else 'INADEQUATE — ' + str(MIN_TRIALS) + ' minimum required'}",
        ]
    else:
        verdict_label = "CONTINUE"
        reasoning = [
            f"Mixed evidence: {pass_fraction:.0%} beat benchmark",
            f"Bootstrap 95% CI includes zero in {zero_in_ci_frac:.0%} of regime instances",
            "Needs explicit conditions to proceed",
        ]

    # Low/high vol pass separately
    low_vol_pass = any(
        r.tsmm_low_vol_return > r.benchmark_low_vol_return and r.tsmm_low_vol_trials >= MIN_TRIALS
        for r in results
        if r.tsmm_low_vol_trials >= MIN_TRIALS
    )
    high_vol_pass = any(
        r.tsmm_high_vol_return > r.benchmark_high_vol_return and r.tsmm_high_vol_trials >= MIN_TRIALS
        for r in results
        if r.tsmm_high_vol_trials >= MIN_TRIALS
    )

    # Get quarters covered
    quarters_covered = [
        ref_bars[s.test_start].timestamp[:10]
        for s in test_quarters
    ]

    return Stage1Verdict(
        verdict=verdict_label,
        reasoning=reasoning,
        splits_tested=len(test_quarters),
        params_tested=len(results) // max(len(test_quarters), 1),
        quarters_covered=quarters_covered,
        low_vol_pass=low_vol_pass,
        high_vol_pass=high_vol_pass,
        bootstrap_centered_near_zero=bootstrap_centered,
        all_regimes_adequate_trials=trial_adequate,
        btc_funding_sensitivity=btc_funding_sensitivity,
        split_diagnostics=split_diags,
    )


def write_results_csv(results: list[SplitResult], out_path: Path) -> None:
    """Write per-split, per-regime raw results to CSV."""
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "split_index",
            "test_start",
            "test_end",
            "param_return_period",
            "param_threshold",
            "universe",
            # TSMOM
            "tsmm_low_vol_return",
            "tsmm_low_vol_trials",
            "tsmm_low_vol_sign",
            "tsmm_high_vol_return",
            "tsmm_high_vol_trials",
            "tsmm_high_vol_sign",
            "tsmm_total_return",
            "tsmm_total_trials",
            # Benchmark
            "benchmark_low_vol_return",
            "benchmark_high_vol_return",
            "benchmark_total_return",
            # Excess
            "low_vol_excess",
            "high_vol_excess",
            "total_excess",
        ])

        for r in results:
            writer.writerow([
                r.split_index,
                r.test_start,
                r.test_end,
                r.param_return_period,
                r.param_threshold,
                "|".join(r.universe),
                round(r.tsmm_low_vol_return, 6),
                r.tsmm_low_vol_trials,
                r.tsmm_low_vol_sign,
                round(r.tsmm_high_vol_return, 6),
                r.tsmm_high_vol_trials,
                r.tsmm_high_vol_sign,
                round(r.tsmm_total_return, 6),
                r.tsmm_total_trials,
                round(r.benchmark_low_vol_return, 6),
                round(r.benchmark_high_vol_return, 6),
                round(r.benchmark_total_return, 6),
                round(r.tsmm_low_vol_return - r.benchmark_low_vol_return, 6),
                round(r.tsmm_high_vol_return - r.benchmark_high_vol_return, 6),
                round(r.tsmm_total_return - r.benchmark_total_return, 6),
            ])


def write_verdict_md(verdict: Stage1Verdict, out_path: Path) -> None:
    """Write the Stage 1 verdict markdown file."""
    now = datetime.utcnow().strftime("%Y-%m-%d")

    lines = [
        f"# Stage 1 Verdict — Multi-Asset Liquid Perp TSMOM Admissibility",
        f"",
        f"**Date**: {now}",
        f"**Verdict**: **{verdict.verdict}**",
        f"",
        f"## Summary",
        f"",
        f"- Splits tested: {verdict.splits_tested}",
        f"- Grid points tested: {verdict.params_tested} (4-point frozen grid × splits)",
        f"- Test quarters: {', '.join(verdict.quarters_covered[:6])}{'...' if len(verdict.quarters_covered) > 6 else ''}",
        f"- Low-vol regime pass: {verdict.low_vol_pass}",
        f"- High-vol regime pass: {verdict.high_vol_pass}",
        f"- Bootstrap centered near zero: {verdict.bootstrap_centered_near_zero}",
        f"- Trials adequate (≥{MIN_TRIALS}): {verdict.all_regimes_adequate_trials}",
        f"",
        f"## Reasoning",
    ]

    for reason in verdict.reasoning:
        lines.append(f"- {reason}")

    lines.extend([
        f"",
        f"## BTC Funding Sensitivity (secondary context — NOT modeled truth)",
        f"",
        f"| BTC Funding (bps/yr) | Return Delta (per bar) |",
        f"|---------------------|------------------------|",
    ])

    for bps, delta in sorted(verdict.btc_funding_sensitivity.items()):
        lines.append(f"| {bps} | {delta:.6f} |")

    lines.extend([
        f"",
        f"## Pass/Fail Criteria Reference",
        f"",
        f"**PASS**: TSMOM+vol-overlay shows sign consistency OR rank evidence OR return stability",
        f"materially above always-long benchmark, ≥5 trials per regime per split, bootstrap not centered at zero.",
        f"",
        f"**FAIL**: TSMOM indistinguishable from or worse than always-long; no sign consistency;",
        f"bootstrap centered near zero; insufficient trials.",
        f"",
        f"**CONTINUE**: Mixed evidence; needs explicit conditions to proceed.",
        f"",
        f"## Raw Results",
        f"",
        f"See `scripts/stage1_results.csv` for per-split, per-regime raw results.",
    ])

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def write_funding_sensitivity_md(btc_sensitivity: dict[int, float], out_path: Path) -> None:
    """Write the funding sensitivity markdown file."""
    now = datetime.utcnow().strftime("%Y-%m-%d")

    lines = [
        "# Stage 1 Funding Sensitivity — BTC Only (Secondary Context)",
        "",
        f"**Date**: {now}",
        "",
        "This is **NOT modeled truth**. Altcoin funding is a structural unknown.",
        "BTC funding rates shown here are sensitivity rows only.",
        "",
        "| BTC Funding (bps/yr) | Annual Cost (%) | Per-Bar Cost |",
        "|---------------------|-----------------|---------------|",
    ]

    for bps in sorted(btc_sensitivity.keys()):
        annual_pct = bps / 100  # bps to percent
        per_bar = btc_sensitivity[bps]
        lines.append(f"| {bps} | {annual_pct:.4f}% | {per_bar:.6f} |")

    lines.extend([
        "",
        "## Notes",
        "",
        "- 8h bars per year ≈ 1095",
        "- Per-bar cost = annual_bps / 10000 / 1095",
        "- Altcoin funding (548/1500/4928) is NOT used in any model — caveat space only",
        "- Carry for alts remains a structural unknown; no multi-asset live-bridge in this cycle",
    ])

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
