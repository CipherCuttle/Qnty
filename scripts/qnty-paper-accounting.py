#!/usr/bin/env python3
"""Paper PnL accounting — one run.

Consumes the read-only shadow observer output (observation_log.json) and appends to the
paper_pnl_v1 ledger. Strictly additive; never writes to forward_obs_v1.

This is a SIMULATION. Paper PnL is not live trading. See docs/paper_pnl_v1_schema.md.

Usage:
    python scripts/qnty-paper-accounting.py
    # paths default to /srv/qnty/...; override for dev/tests with env vars:
    QNTY_PAPER_OUTPUT_DIR=... QNTY_FORWARD_OBS_DIR=... python scripts/qnty-paper-accounting.py
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from quantbot.paper.config import ConfigContractError
from quantbot.paper.runner import run_once

# Exit codes (documented in docs/ops/VM_90D_RUNBOOK.md § 3.5b):
#   0 = run complete   2 = freshness/divergence gate ABORTED (ABORTED summary written)
#   3 = stale/incompatible paper_config.json — clean abort, NO ledger or summary writes
EXIT_CONFIG_CONTRACT = 3


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one paper PnL accounting pass")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--forward-obs-dir", default=None)
    parser.add_argument("--data-dir", default="data")
    args = parser.parse_args(argv)

    try:
        summary = run_once(
            output_dir=Path(args.output_dir) if args.output_dir else None,
            forward_obs_dir=Path(args.forward_obs_dir) if args.forward_obs_dir else None,
            data_dir=Path(args.data_dir),
        )
    except ConfigContractError as exc:
        # The config that DEFINES the output contract is itself stale/incompatible, so no
        # valid ABORTED summary can be built and NO ledger/summary/state rows are written.
        # Fail cleanly (no traceback) with explicit archive/re-init guidance, NOT exit 1.
        print("Paper accounting ABORTED — stale/incompatible paper_config.json (SIMULATION).")
        print("No fills/trades/equity/state/summary rows were written.")
        print(f"  reason: {exc}")
        print("  Fix: archive the stale paper output dir and re-init a fresh write-once")
        print("  config with a fresh FUTURE forward_start_ts for this engine version, e.g.:")
        print("    ts=$(date -u +%Y%m%dT%H%M%SZ)")
        print("    mv <PAPER_OUTPUT_DIR> <PAPER_OUTPUT_DIR>.archived-$ts")
        print("    python -m quantbot.paper.config --forward-start-ts <FUTURE_UTC_8H_BOUNDARY>")
        return EXIT_CONFIG_CONTRACT

    # An aborted run (freshness/divergence gate) writes a minimal ABORTED summary with no
    # bars_elapsed/closed_trades/etc. Handle it cleanly: do NOT claim "run complete" and do
    # NOT KeyError on missing keys; exit non-zero so a caller/timer notices the abort.
    if summary.get("status") == "ABORTED":
        print("Paper accounting run ABORTED (SIMULATION) — no ledger rows written.")
        print(f"  forward_start_ts: {summary.get('forward_start_ts')}")
        print(f"  abort code:       {summary.get('abort_code')}")
        print(f"  abort reason:     {summary.get('abort_reason')}")
        print(f"  verdict:          {summary.get('current_verdict')}")
        return 2

    print("Paper accounting run complete (SIMULATION).")
    print(f"  forward_start_ts: {summary['forward_start_ts']}")
    print(f"  bars elapsed:     {summary['bars_elapsed']}")
    print(f"  closed trades:    {summary['closed_trades']}")
    print(f"  winrate:          {summary['winrate']}")
    print(f"  total PnL:        {summary['total_pnl']}")
    print(f"  max drawdown:     {summary['max_drawdown']}")
    print(f"  funding gaps:     {summary.get('funding_gap_count', 0)}")
    print(f"  verdict:          {summary['current_verdict']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
