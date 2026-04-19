#!/usr/bin/env python3
"""Apples-to-apples walkforward comparison: BASE vs RFB.

Runs identical walkforward experiments for:
  - RollingReturnBreakoutStrategy (BASE)
  - RegimeFilteredBreakoutStrategy (RFB)

Two cost settings: 10/5 and 20/10.
Output: structured metrics for final verdict.
"""

import json
import tempfile
from pathlib import Path

from quantbot.experiment.spec import ExperimentSpec
from quantbot.experiment.walkforward_runner import run_walkforward_experiment


def run_experiment(
    strategy_name: str,
    fee_bps: float,
    slippage_bps: float,
    output_base: Path,
) -> dict:
    """Run a single walkforward experiment and return key metrics."""
    spec = ExperimentSpec(
        experiment_name=f"compare_{strategy_name}",
        strategy_name=strategy_name,
        strategy_params={},
        fixture_name="BTCUSDT_8h",
        fee_bps=fee_bps,
        slippage_bps=slippage_bps,
    )

    manifest_path = Path("tests/fixtures/BTCUSDT_manifest.json")
    csv_path = Path("tests/fixtures/BTCUSDT_8h.csv")
    output_dir = output_base / f"{strategy_name}_fee{fee_bps}_slip{slippage_bps}"

    result = run_walkforward_experiment(
        spec=spec,
        manifest_path=manifest_path,
        csv_path=csv_path,
        output_dir=output_dir,
        train_size=720,
        test_size=120,
        step_size=120,
        interval="8h",
    )

    # Extract metrics
    econ = result.economics_summary
    ret = result.return_summary

    # Count window outcomes
    positive_windows = 0
    negative_windows = 0
    zero_signal_windows = 0
    for split in result.splits:
        if split.signal_count == 0:
            zero_signal_windows += 1
        elif split.return_summary and split.return_summary.net_return_total > 0:
            positive_windows += 1
        elif split.return_summary and split.return_summary.net_return_total < 0:
            negative_windows += 1

    return {
        "strategy": strategy_name,
        "fee_bps": fee_bps,
        "slippage_bps": slippage_bps,
        "signal_count": result.total_signal_count,
        "entry_count": econ.entry_count if econ else 0,
        "exit_count": econ.exit_count if econ else 0,
        "flip_count": econ.flip_count if econ else 0,
        "cost_side_count": econ.cost_side_count if econ else 0,
        "gross_return_total": ret.gross_return_total if ret else 0.0,
        "net_return_total": ret.net_return_total if ret else 0.0,
        "positive_windows": positive_windows,
        "negative_windows": negative_windows,
        "zero_signal_windows": zero_signal_windows,
        "window_count": result.split_count,
    }


def print_comparison_table(results: list[dict]) -> None:
    """Print a structured comparison table."""
    print("\n" + "=" * 90)
    print("WALKFORWARD COMPARISON: BASE (RollingReturnBreakout) vs RFB (RegimeFilteredBreakout)")
    print("=" * 90)
    print(f"Fixtures: BTCUSDT_8h.csv (2190 bars)")
    print(f"Windows: train=720, test=120, step=120")
    print("-" * 90)

    for cost_label, fee, slip in [("fee=10/slip=5", 10, 5), ("fee=20/slip=10", 20, 10)]:
        print(f"\n### {cost_label} ###")
        print("-" * 60)

        base = next(r for r in results if r["strategy"] == "RollingReturnBreakoutStrategy" and r["fee_bps"] == fee)
        rfb = next(r for r in results if r["strategy"] == "RegimeFilteredBreakoutStrategy" and r["fee_bps"] == fee)

        signal_ratio = rfb["signal_count"] / base["signal_count"] if base["signal_count"] > 0 else 0.0
        net_ratio = rfb["net_return_total"] / base["net_return_total"] if base["net_return_total"] != 0 else 0.0

        print(f"{'Metric':<25} {'BASE':>15} {'RFB':>15} {'Ratio':>10}")
        print("-" * 65)
        print(f"{'signal_count':<25} {base['signal_count']:>15} {rfb['signal_count']:>15} {signal_ratio:>10.3f}")
        print(f"{'entry_count':<25} {base['entry_count']:>15} {rfb['entry_count']:>15} {rfb['entry_count']/base['entry_count'] if base['entry_count']>0 else 0:>10.3f}")
        print(f"{'exit_count':<25} {base['exit_count']:>15} {rfb['exit_count']:>15} {rfb['exit_count']/base['exit_count'] if base['exit_count']>0 else 0:>10.3f}")
        print(f"{'flip_count':<25} {base['flip_count']:>15} {rfb['flip_count']:>15} {rfb['flip_count']/base['flip_count'] if base['flip_count']>0 else 0:>10.3f}")
        print(f"{'cost_side_count':<25} {base['cost_side_count']:>15} {rfb['cost_side_count']:>15} {rfb['cost_side_count']/base['cost_side_count'] if base['cost_side_count']>0 else 0:>10.3f}")
        print(f"{'gross_return_total':<25} {base['gross_return_total']:>15.4f} {rfb['gross_return_total']:>15.4f} {rfb['gross_return_total']/base['gross_return_total'] if base['gross_return_total']!=0 else 0:>10.3f}")
        print(f"{'net_return_total':<25} {base['net_return_total']:>15.4f} {rfb['net_return_total']:>15.4f} {net_ratio:>10.3f}")
        print(f"{'positive_windows':<25} {base['positive_windows']:>15} {rfb['positive_windows']:>15}")
        print(f"{'negative_windows':<25} {base['negative_windows']:>15} {rfb['negative_windows']:>15}")
        print(f"{'zero_signal_windows':<25} {base['zero_signal_windows']:>15} {rfb['zero_signal_windows']:>15}")
        print(f"{'window_count':<25} {base['window_count']:>15} {rfb['window_count']:>15}")

        print(f"\n  Signal reduction ratio (RFB/BASE):     {signal_ratio:.3f}")
        print(f"  Net return reduction ratio (RFB/BASE):  {net_ratio:.3f}")

        if signal_ratio < net_ratio:
            verdict = "RFB REDUCES SIGNALS MORE THAN RETURNS (filter is working)"
        elif signal_ratio > net_ratio:
            verdict = "RFB REDUCES RETURNS MORE THAN SIGNALS (filter is hurting)"
        else:
            verdict = "RFB net decline is PROPORTIONAL to signal reduction"

        print(f"  Verdict: {verdict}")

    print("\n" + "=" * 90)
    print("SUMMARY")
    print("=" * 90)

    # Fee 10/5
    base_10 = next(r for r in results if r["strategy"] == "RollingReturnBreakoutStrategy" and r["fee_bps"] == 10)
    rfb_10 = next(r for r in results if r["strategy"] == "RegimeFilteredBreakoutStrategy" and r["fee_bps"] == 10)
    sig_ratio_10 = rfb_10["signal_count"] / base_10["signal_count"] if base_10["signal_count"] > 0 else 0.0
    net_ratio_10 = rfb_10["net_return_total"] / base_10["net_return_total"] if base_10["net_return_total"] != 0 else 0.0

    # Fee 20/10
    base_20 = next(r for r in results if r["strategy"] == "RollingReturnBreakoutStrategy" and r["fee_bps"] == 20)
    rfb_20 = next(r for r in results if r["strategy"] == "RegimeFilteredBreakoutStrategy" and r["fee_bps"] == 20)
    sig_ratio_20 = rfb_20["signal_count"] / base_20["signal_count"] if base_20["signal_count"] > 0 else 0.0
    net_ratio_20 = rfb_20["net_return_total"] / base_20["net_return_total"] if base_20["net_return_total"] != 0 else 0.0

    print(f"\n  COST SETTING     SIGNAL RATIO    NET RATIO    INTERPRETATION")
    print(f"  fee=10/slip=5    {sig_ratio_10:.3f}          {net_ratio_10:.3f}        {'RFB filter works' if net_ratio_10 > sig_ratio_10 else 'RFB filter proportional or worse'}")
    print(f"  fee=20/slip=10   {sig_ratio_20:.3f}          {net_ratio_20:.3f}        {'RFB filter works' if net_ratio_20 > sig_ratio_20 else 'RFB filter proportional or worse'}")

    print("\n  COST SENSITIVITY:")
    base_net_10 = base_10["net_return_total"]
    base_net_20 = base_20["net_return_total"]
    rfb_net_10 = rfb_10["net_return_total"]
    rfb_net_20 = rfb_20["net_return_total"]
    print(f"    BASE net @ 10/5: {base_net_10:.4f}  @ 20/10: {base_net_20:.4f}  drop: {((base_net_20-base_net_10)/base_net_10*100) if base_net_10 != 0 else float('inf'):.1f}%")
    print(f"    RFB  net @ 10/5: {rfb_net_10:.4f}  @ 20/10: {rfb_net_20:.4f}  drop: {((rfb_net_20-rfb_net_10)/rfb_net_10*100) if rfb_net_10 != 0 else float('inf'):.1f}%")

    print("\n  FINAL QUESTION: Does RFB's regime filter ACTUALLY improve net returns,")
    print("                  or just reduce them proportionally to signal reduction?")

    if net_ratio_10 >= sig_ratio_10 and net_ratio_20 >= sig_ratio_20:
        final = "RFB FILTER APPEARS TO WORK: net return decline is LESS than signal decline."
    elif net_ratio_10 < sig_ratio_10 and net_ratio_20 < sig_ratio_20:
        final = "RFB FILTER IS HURTING: net return declines MORE than signal count."
    else:
        final = "RFB FILTER MIXED: works at one cost setting, fails at another."

    print(f"\n  ANSWER: {final}")
    print("=" * 90)


def main() -> None:
    strategies = [
        ("RollingReturnBreakoutStrategy", 10, 5),
        ("RegimeFilteredBreakoutStrategy", 10, 5),
        ("RollingReturnBreakoutStrategy", 20, 10),
        ("RegimeFilteredBreakoutStrategy", 20, 10),
    ]

    results = []
    with tempfile.TemporaryDirectory() as tmpdir:
        base_output = Path(tmpdir)

        for strategy, fee, slip in strategies:
            print(f"\nRunning: {strategy} (fee={fee}, slip={slip})...")
            result = run_experiment(strategy, fee, slip, base_output)
            results.append(result)
            print(f"  Done. Signals: {result['signal_count']}, Net: {result['net_return_total']:.4f}")

    print_comparison_table(results)

    # Also print as JSON for programmatic use
    print("\n\n### RAW JSON OUTPUT ###")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
