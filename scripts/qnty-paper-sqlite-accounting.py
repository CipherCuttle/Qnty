#!/usr/bin/env python3
"""Run SQLite paper accounting writer (Phase 2).

Processes forward observer signals and writes all ledger rows inside a single
BEGIN IMMEDIATE transaction, with full reconciliation before commit.

Usage::

    python scripts/qnty-paper-sqlite-accounting.py \
        --db-path /srv/qnty/output/paper_pnl_v1/paper_ledger.db \
        [--forward-obs-dir /path/to/forward_obs_v1] \
        [--data-dir /path/to/data] \
        [--json]

Environment variables:
    QNTY_PAPER_DB_PATH   Override the default DB path if --db-path not provided.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Allow running from repo root without installing
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quantbot.paper.sqlite_writer import run_sqlite_accounting


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run SQLite paper accounting writer (Phase 2).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exit codes (RUNNER STATUS ONLY — authoritative trust is the verifier's
paper_verify_report.json, never the writer's return code):
  0  OK (complete batch committed)
  2  ABORTED (freshness/divergence gate)
  3  CONFIG_ERROR (DB/config identity invalid)
  4  CORRUPT_LEDGER (reconciliation failed)
  5  PRE_START (valid DB, no eligible bars)
  6  LEDGER_BUSY (could not acquire writer lock)

Environment variables:
  QNTY_PAPER_DB_PATH   Path to paper_ledger.db (fallback if --db-path not provided)
""",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help=(
            "Path to paper_ledger.db. "
            "Overrides QNTY_PAPER_DB_PATH environment variable. "
            "Required if QNTY_PAPER_DB_PATH is not set."
        ),
    )
    parser.add_argument(
        "--forward-obs-dir",
        default=None,
        help=(
            "Override forward_obs_v1 directory. "
            "Default: <output_dir>/forward_obs_v1"
        ),
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help=(
            "Override data directory for OHLCV/funding loaders. "
            "Patches the data loader _DATA_DIR variables."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as machine-parseable JSON to stdout.",
    )
    args = parser.parse_args(argv)

    # Resolve db_path: --db-path > QNTY_PAPER_DB_PATH > error
    db_path = args.db_path
    if db_path is None:
        db_path = os.environ.get("QNTY_PAPER_DB_PATH")
    if db_path is None:
        print(
            "ERROR: --db-path is required or set QNTY_PAPER_DB_PATH environment variable.",
            file=sys.stderr,
        )
        parser.print_help(sys.stderr)
        return 1

    # Convert paths to Path objects if provided
    forward_obs_dir = Path(args.forward_obs_dir) if args.forward_obs_dir else None
    data_dir = Path(args.data_dir) if args.data_dir else None

    # Call the accounting function
    status_code, status_message = run_sqlite_accounting(
        db_path=db_path,
        forward_obs_dir=forward_obs_dir,
        data_dir=data_dir,
    )

    # Build result dictionary
    result = {
        "status_code": status_code,
        "status_message": status_message,
    }

    # Output based on --json flag
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        # Human-readable output
        status_names = {
            0: "OK",
            2: "ABORTED",
            3: "CONFIG_ERROR",
            4: "CORRUPT_LEDGER",
            5: "PRE_START",
            6: "LEDGER_BUSY",
        }
        status_name = status_names.get(status_code, "UNKNOWN")
        print(f"Status: {status_name} ({status_code})")
        print(f"Message: {status_message}")

        if status_code == 0:
            print("\nBatch committed successfully (runner status only).")
            print(
                "This is NOT an authoritative OK. Authoritative paper trust is the "
                "verifier's paper_verify_report.json — run scripts/qnty-paper-sqlite-verify.py."
            )

    return status_code


if __name__ == "__main__":
    sys.exit(main())
