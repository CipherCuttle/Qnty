#!/usr/bin/env python3
"""Run Stage 2 Stress Diagnostics.

Usage:
    python scripts/run_stage2_stress.py [--carry-inputs PATH]

Options:
    --carry-inputs   Path to stage3c_carry_comparison.csv for real-carry scenario.
                    When provided, adds a "real-carry" scenario alongside the
                    existing scalar scenarios (548/1500/4928 bps/yr).

Outputs:
    scripts/stage2_stress_results.csv
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from quantbot.experiment.stage2_stress_diagnostics import (
    run_stress_diagnostics,
    write_stress_results_csv,
    apply_carry_stress,
    apply_real_carry_stress,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 2 Stress Diagnostics")
    parser.add_argument(
        "--carry-inputs",
        type=str,
        default=None,
        help="Path to stage3c_carry_comparison.csv for real-carry scenario",
    )
    args = parser.parse_args()

    print("Running Stage 2 stress diagnostics...")
    diagnostics = run_stress_diagnostics(carry_csv_path=args.carry_inputs)

    # Write CSV
    output_path = Path("scripts/stage2_stress_results.csv")
    write_stress_results_csv(output_path, diagnostics)
    print(f"Results written: {output_path}")

    # Print summary
    print("\n=== COMBINED-REGIME MATRIX ===")
    for row in diagnostics["regime_summary"]:
        print(f"  {row['regime_key']}: sign_cons={row['sign_consistency']:.2%}, "
              f"trials={row['trial_count']}, excess={row['total_excess']:.4f}")

    print("\n=== CARRY STRESS ===")
    for cr in diagnostics["carry_results"]:
        print(f"  {cr.scenario_label} ({cr.annual_bps} bps/yr): "
              f"{cr.positive_fraction:.1%} positive net "
              f"({cr.positive_net_instances}/{cr.total_instances})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
