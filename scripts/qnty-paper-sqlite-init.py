#!/usr/bin/env python3
"""Initialise a fresh paper-ledger SQLite database.

Creates the SQLite/WAL ledger database for paper PnL v1 with the full schema,
append-only triggers, and the singleton config row.

Refuses to run if:
- the target DB file already exists
- legacy JSONL paper artifacts are present in the output directory

Usage::

    python scripts/qnty-paper-sqlite-init.py \
        --forward-start-ts 2026-06-09T00:00:00 \
        [--db-path /srv/qnty/output/paper_pnl_v1/paper_ledger.db] \
        [--initial-equity-usd 10000] \
        [--notional-usd 1000] \
        [--leverage 1.0] \
        [--fee-bps 5.0] \
        [--slippage-bps 5.0] \
        [--bar-interval-hours 8] \
        [--max-bar-staleness-hours 24] \
        [--heartbeat-max-age-hours 24]

Environment variables:
    QNTY_PAPER_DB_PATH   Override the default DB path.
    QNTY_PAPER_OUTPUT_DIR  Override the default output directory (for legacy check).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running from repo root without installing
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quantbot.core.determinism import canonical_json_dumps
from quantbot.paper.config import build_config
from quantbot.paper.db import (
    DEFAULT_DB_PATH,
    PAPER_ENGINE_VERSION,
    _legacy_artifact_paths,
    config_hash_from_row,
    get_paper_db_path,
    initialize_database,
    validate_database_identity,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Initialise a fresh paper-ledger SQLite database (Phase 1)."
    )
    parser.add_argument(
        "--forward-start-ts",
        required=True,
        help="Hard UTC bar boundary (e.g. 2026-06-09T00:00:00). No fill before this.",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help=(
            "Path for the new SQLite DB file. "
            "Overrides QNTY_PAPER_DB_PATH and the built-in default. "
            f"Default: {DEFAULT_DB_PATH}"
        ),
    )
    parser.add_argument("--initial-equity-usd", type=float, default=10_000.0)
    parser.add_argument("--notional-usd", type=float, default=1_000.0)
    parser.add_argument("--leverage", type=float, default=1.0)
    parser.add_argument("--fee-bps", type=float, default=5.0)
    parser.add_argument("--slippage-bps", type=float, default=5.0)
    parser.add_argument("--bar-interval-hours", type=int, default=8)
    parser.add_argument("--max-bar-staleness-hours", type=float, default=24.0)
    parser.add_argument("--heartbeat-max-age-hours", type=float, default=24.0)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing DB file (not recommended).",
    )
    args = parser.parse_args(argv)

    db_path = get_paper_db_path(args.db_path)
    output_dir = db_path.parent

    # --- Refuse if legacy artifacts exist -----------------------------------
    legacy = _legacy_artifact_paths(output_dir)
    if legacy and not args.force:
        print(
            "ERROR: legacy paper artifacts found in output directory:",
            file=sys.stderr,
        )
        for p in legacy:
            print(f"  {p}", file=sys.stderr)
        print(
            "Archive or remove these files, or use --force to proceed anyway.",
            file=sys.stderr,
        )
        return 1

    # --- Refuse if DB already exists ----------------------------------------
    if db_path.exists() and not args.force:
        print(f"ERROR: database already exists: {db_path}", file=sys.stderr)
        print("Use --force to overwrite (not recommended).", file=sys.stderr)
        return 1

    # --- Build canonical config dict ----------------------------------------
    config = build_config(
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

    # --- Initialise DB ------------------------------------------------------
    try:
        initialize_database(db_path, config)
    except Exception as exc:
        print(f"ERROR: failed to initialise database: {exc}", file=sys.stderr)
        return 1

    # --- Validate what we just wrote ----------------------------------------
    import sqlite3

    from quantbot.paper.db import connect_readonly

    try:
        conn = connect_readonly(db_path)
        try:
            validated = validate_database_identity(conn)
        finally:
            conn.close()
    except Exception as exc:
        print(f"ERROR: identity validation failed: {exc}", file=sys.stderr)
        return 1

    # --- Print summary ------------------------------------------------------
    summary = {
        "db_path": str(db_path),
        "schema_version": validated["db_schema_version"],
        "paper_engine_version": validated["paper_engine_version"],
        "forward_start_ts": validated["forward_start_ts"],
        "config_hash": validated["config_hash"],
        "created_at": validated["created_at"],
    }

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
