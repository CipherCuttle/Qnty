#!/usr/bin/env python3
"""Initialise a fresh NEW-LANE paper output dir + SQLite ledger DB.

A thin, fail-closed CLI over :func:`quantbot.paper.lane_init.init_lane`. It writes the
unchanged v1 ``paper_config.json`` plus the additive ``lane_identity.json`` /
``lane_config_v2.json`` sidecars and initializes the lane DB, then verifies it read-only.

It NEVER runs the paper writer, NEVER starts a cycle, and NEVER touches
systemd/timers/network. ``--output-dir`` and ``--db-path`` are REQUIRED and have no env
defaults, so a lane can never accidentally resolve to the production baseline.

Usage::

    python scripts/qnty-paper-lane-init.py \
        --output-dir /tmp/lane_shadow_vol_a \
        --db-path /tmp/lane_shadow_vol_a/paper_ledger.db \
        --lane-id shadow_vol_a \
        --strategy-id vol_norm \
        --strategy-version 1 \
        --forward-start-ts 2026-06-20T16:00:00

This is SIMULATION-support tooling. It makes NO profitability or edge claim
(strategy remains EDGE_UNPROVEN).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running from the repo root without installing.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quantbot.paper.config import (  # noqa: E402
    DEFAULT_BAR_INTERVAL_HOURS,
    DEFAULT_FEE_BPS,
    DEFAULT_HEARTBEAT_MAX_AGE_HOURS,
    DEFAULT_INITIAL_EQUITY_USD,
    DEFAULT_LEVERAGE,
    DEFAULT_MAX_BAR_STALENESS_HOURS,
    DEFAULT_NOTIONAL_USD,
    DEFAULT_SLIPPAGE_BPS,
)
from quantbot.paper.lane_init import init_lane  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Initialise a fresh new-lane paper output dir + ledger DB "
        "(init only; never runs the writer)."
    )
    parser.add_argument("--output-dir", required=True, help="New-lane output directory (must be absent/empty, NOT the baseline).")
    parser.add_argument("--db-path", required=True, help="New-lane DB path (must not exist, NOT the baseline).")
    parser.add_argument("--lane-id", required=True)
    parser.add_argument("--strategy-id", required=True)
    parser.add_argument("--strategy-version", required=True)
    parser.add_argument(
        "--forward-start-ts",
        required=True,
        help="Hard UTC bar boundary (e.g. 2026-06-20T16:00:00). No fill before this.",
    )
    parser.add_argument("--initial-equity-usd", type=float, default=DEFAULT_INITIAL_EQUITY_USD)
    parser.add_argument("--notional-usd", type=float, default=DEFAULT_NOTIONAL_USD)
    parser.add_argument("--leverage", type=float, default=DEFAULT_LEVERAGE)
    parser.add_argument("--fee-bps", type=float, default=DEFAULT_FEE_BPS)
    parser.add_argument("--slippage-bps", type=float, default=DEFAULT_SLIPPAGE_BPS)
    parser.add_argument("--bar-interval-hours", type=int, default=DEFAULT_BAR_INTERVAL_HOURS)
    parser.add_argument(
        "--max-bar-staleness-hours", type=float, default=DEFAULT_MAX_BAR_STALENESS_HOURS
    )
    parser.add_argument(
        "--heartbeat-max-age-hours", type=float, default=DEFAULT_HEARTBEAT_MAX_AGE_HOURS
    )
    args = parser.parse_args(argv)

    try:
        result = init_lane(
            output_dir=args.output_dir,
            db_path=args.db_path,
            lane_id=args.lane_id,
            strategy_id=args.strategy_id,
            strategy_version=args.strategy_version,
            forward_start_ts=args.forward_start_ts,
            initial_equity_usd=args.initial_equity_usd,
            notional_usd=args.notional_usd,
            leverage=args.leverage,
            fee_bps=args.fee_bps,
            slippage_bps=args.slippage_bps,
            bar_interval_hours=args.bar_interval_hours,
            max_bar_staleness_hours=args.max_bar_staleness_hours,
            heartbeat_max_age_hours=args.heartbeat_max_age_hours,
        )
    except (ValueError, FileExistsError) as exc:
        print(f"Lane init REFUSED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    print(f"Initialised lane '{args.lane_id}' (writer NOT run).")
    print(f"  output_dir:               {result.output_dir}")
    print(f"  db_path:                  {result.db_path}")
    print(f"  paper_config.json:        {result.paper_config_path}")
    print(f"  lane_identity.json:       {result.lane_identity_path}")
    print(f"  lane_config_v2.json:      {result.lane_config_v2_path}")
    print(f"  accounting_config_hash_v1:{result.accounting_config_hash_v1}")
    print(f"  config_hash_v2:           {result.config_hash_v2}")
    print(f"  verify_status:            {result.verify_status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
