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

from quantbot.paper.runner import run_once


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one paper PnL accounting pass")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--forward-obs-dir", default=None)
    parser.add_argument("--data-dir", default="data")
    args = parser.parse_args(argv)

    summary = run_once(
        output_dir=Path(args.output_dir) if args.output_dir else None,
        forward_obs_dir=Path(args.forward_obs_dir) if args.forward_obs_dir else None,
        data_dir=Path(args.data_dir),
    )

    print("Paper accounting run complete (SIMULATION).")
    print(f"  forward_start_ts: {summary['forward_start_ts']}")
    print(f"  bars elapsed:     {summary['bars_elapsed']}")
    print(f"  closed trades:    {summary['closed_trades']}")
    print(f"  winrate:          {summary['winrate']}")
    print(f"  total PnL:        {summary['total_pnl']}")
    print(f"  max drawdown:     {summary['max_drawdown']}")
    print(f"  verdict:          {summary['current_verdict']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
