#!/usr/bin/env python3
"""Stage 1 TSMOM Admissibility Evaluation Runner.

Usage:
    python scripts/run_stage1.py [--carry-mode none|proxy|real]

Options:
    --carry-mode   Carry mode:
        none    No carry adjustment (default, existing behavior)
        proxy   Regime-based proxy carry (548/1500/4928 bps/yr)
        real    Real per-symbol funding rates from data/*_8h_funding.csv

Outputs:
    docs/verdicts/stage1_verdict.md
    scripts/stage1_results.csv
    docs/verdicts/stage1_funding_sensitivity.md
    docs/verdicts/stage1_net_carry_results.csv  (when --carry-mode real)
"""

import argparse
import sys
from pathlib import Path

# Ensure quantbot is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from quantbot.experiment.stage1_diagnostics import (
    run_stage1_diagnostics,
    write_results_csv,
    write_verdict_md,
    write_funding_sensitivity_md,
)
from quantbot.experiment.portfolio_evaluator import evaluate_grid
from quantbot.experiment.walkforward import build_walkforward_splits
from quantbot.data.multi_asset_loader import load_all_ohlcv
from quantbot.data.quarterly_universe import QUARTERLY_DATES, QUARTERLY_UNIVERSES
from quantbot.data.funding_loader import load_all_funding


# Regime-based proxy carry scalars (bps/yr), applied to all symbols uniformly
REGIME_PROXY_CARRY: dict[str, int] = {
    "2022 (Bear)": 766,
    "2024-H1 (Bull/ETF)": 1594,
    "2025 (Current)": 548,
}

# Honest coverage: funding data available 2021-Q3 through 2025-Q2
HONEST_COVERAGE_START = "2021-07-01"
HONEST_COVERAGE_END = "2025-06-30"


def _proxy_carry_for_dt(dt_str: str) -> float:
    """Return proxy carry per bar (annual bps → per-bar fraction) for a given dt.

    Uses 3 × 8h bars per day × 365 days = 1095 bars/year.
    """
    if dt_str >= "2025-01-01":
        annual_bps = 548
    elif dt_str >= "2024-01-01":
        annual_bps = 1594
    else:
        annual_bps = 766
    return annual_bps / 10000 / 1095


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 1 TSMOM Evaluation")
    parser.add_argument(
        "--carry-mode",
        choices=["none", "proxy", "real"],
        default="none",
        help="Carry adjustment mode (default: none)",
    )
    args = parser.parse_args()

    print("Loading OHLCV data...")
    bars_by_symbol = load_all_ohlcv()

    if not bars_by_symbol:
        print("ERROR: No OHLCV data loaded — check data/ directory")
        return 1

    print(f"  Loaded symbols: {sorted(bars_by_symbol.keys())}")

    # Reference bars for walkforward
    ref_bars = bars_by_symbol.get("BTCUSDT", [])
    if not ref_bars:
        print("ERROR: BTCUSDT data required")
        return 1

    print(f"  BTCUSDT bars: {len(ref_bars)}")
    print(f"  Date range: {ref_bars[0].timestamp} → {ref_bars[-1].timestamp}")

    # Build walkforward splits
    train_size = 540   # ~2 quarters of 8h bars
    test_size = 270    # ~1 quarter
    step_size = 270

    splits = build_walkforward_splits(ref_bars, train_size, test_size, step_size)
    print(f"  Total walkforward splits: {len(splits)}")

    # Filter to start from Q3 2021
    cutoff_ts = HONEST_COVERAGE_START
    filtered = [s for s in splits if ref_bars[s.test_start].timestamp >= cutoff_ts]
    if not filtered:
        filtered = splits

    # For real-carry mode, also filter to honest coverage end
    if args.carry_mode == "real":
        # Honest coverage ends 2025-06-30
        honest_end = HONEST_COVERAGE_END
        filtered = [s for s in filtered if ref_bars[s.test_start].timestamp <= honest_end]
        print(f"  [real-carry] Honest coverage windows (2021-Q3 to 2025-Q2): {len(filtered)}")

    test_quarters = filtered[:12]
    print(f"  Test quarters (2021-Q4+): {len(test_quarters)}")

    split_bar_indices = [
        (s.train_start, s.train_end, s.test_start, s.test_end)
        for s in test_quarters
    ]

    # Load funding data for real-carry mode
    funding_df = None
    if args.carry_mode == "real":
        print("\nLoading real funding data...")
        funding_df = load_all_funding()
        print(f"  Funding records: {len(funding_df)}")
        print(f"  Symbols with funding: {funding_df['symbol'].nunique()}")

    # Run evaluation — always runs gross (funding_df=None)
    # When funding_df is passed, evaluate_split computes both gross + net
    print("\nEvaluating 4-point TSMOM grid across all splits (gross)...")
    results = evaluate_grid(
        bars_by_symbol=bars_by_symbol,
        split_bar_indices=split_bar_indices,
        quarterly_dates=QUARTERLY_DATES,
        universe_by_quarter=QUARTERLY_UNIVERSES,
        funding_df=None,  # Always gross for comparison baseline
    )
    print(f"  Total result rows: {len(results)}")

    # Write gross CSV
    csv_path = Path("scripts/stage1_results.csv")
    write_results_csv(results, csv_path)
    print(f"  CSV written: {csv_path}")

    # Run diagnostics on gross results
    print("\nRunning Stage 1 diagnostics (gross)...")
    verdict = run_stage1_diagnostics()

    # Write verdict
    verdict_path = Path("docs/verdicts/stage1_verdict.md")
    write_verdict_md(verdict, verdict_path)
    print(f"  Verdict written: {verdict_path}")

    # Write funding sensitivity
    sensitivity_path = Path("docs/verdicts/stage1_funding_sensitivity.md")
    write_funding_sensitivity_md(verdict.btc_funding_sensitivity, sensitivity_path)
    print(f"  Funding sensitivity written: {sensitivity_path}")

    # Print gross summary
    print(f"\n{'='*60}")
    print(f"STAGE 1 VERDICT (gross): {verdict.verdict}")
    print(f"{'='*60}")
    for reason in verdict.reasoning:
        print(f"  • {reason}")

    print(f"\n  Splits tested: {verdict.splits_tested}")
    print(f"  Grid points: {verdict.params_tested}")
    print(f"  Low-vol pass: {verdict.low_vol_pass}")
    print(f"  High-vol pass: {verdict.high_vol_pass}")
    print(f"  Bootstrap near zero: {verdict.bootstrap_centered_near_zero}")
    print(f"  Trials adequate: {verdict.all_regimes_adequate_trials}")

    # Run net-of-carry evaluation if requested
    if args.carry_mode in ("proxy", "real") and funding_df is not None:
        print(f"\n{'='*60}")
        print(f"STAGE 1 NET-OF-CARRY ({args.carry_mode})")
        print(f"{'='*60}")

        results_net = evaluate_grid(
            bars_by_symbol=bars_by_symbol,
            split_bar_indices=split_bar_indices,
            quarterly_dates=QUARTERLY_DATES,
            universe_by_quarter=QUARTERLY_UNIVERSES,
            funding_df=funding_df,
        )
        print(f"  Net result rows: {len(results_net)}")

        # Write net CSV
        net_csv_path = Path("scripts/stage1_net_carry_results.csv")
        write_results_csv(results_net, net_csv_path)
        print(f"  Net CSV written: {net_csv_path}")

        # Compare gross vs net
        print(f"\n  {'Split':>6} {'ReturnPeriod':>13} {'Threshold':>9} | {'GrossReturn':>12} {'NetReturn':>12} {'Carry':>10}")
        print(f"  {'-'*6} {'-'*13} {'-'*9} | {'-'*12} {'-'*12} {'-'*10}")
        for r_gross, r_net in zip(results, results_net):
            gross = r_gross.tsmm_total_return
            net = r_net.tsmm_total_return_net
            carry = gross - net
            print(f"  {r_gross.split_index:>6} {r_gross.param_return_period:>13} "
                  f"{r_gross.param_threshold:>9.2f} | {gross:>12.4f} {net:>12.4f} {carry:>10.4f}")
    elif args.carry_mode == "none":
        print("\n[carry-mode=none] Skipping net-of-carry run.")

    print(f"\n  Results: {csv_path}")
    print(f"  Verdict: {verdict_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
