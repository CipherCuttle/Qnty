#!/usr/bin/env python3
"""Read-only SQLite paper ledger verifier CLI (Phase 3).

Opens ``paper_ledger.db`` read-only (URI ``mode=ro`` + ``PRAGMA query_only=ON``)
and validates committed DB state. It NEVER writes the DB. By default it PUBLISHES
the authoritative paper status to ``paper_verify_report.json`` (+ receipt + log)
next to the DB; ``--no-emit`` runs a pure read-only check that writes nothing.

Usage::

    python scripts/qnty-paper-sqlite-verify.py \
        --db-path /srv/qnty/output/paper_pnl_v1/paper_ledger.db \
        [--output-dir DIR] [--no-emit] [--json] [--verbose]

Environment variables:
    QNTY_PAPER_DB_PATH   Override the default DB path if --db-path not provided.

Exit codes:
    0  OK            DB verified consistent
    3  CONFIG_ERROR  DB/config identity invalid
    4  CORRUPT       a verification invariant failed
    5  PRE_START     valid DB, no committed eligible bars yet
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Allow running from repo root without installing.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quantbot.paper.sqlite_verify import (  # noqa: E402
    REPORT_FILE,
    VERIFIER_DISCLAIMER,
    verify_and_publish,
    verify_database,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only SQLite paper ledger verifier (Phase 3).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exit codes:
  0  OK            (DB verified consistent)
  3  CONFIG_ERROR  (DB/config identity invalid)
  4  CORRUPT       (a verification invariant failed)
  5  PRE_START     (valid DB, no committed eligible bars yet)

Environment variables:
  QNTY_PAPER_DB_PATH   Path to paper_ledger.db (fallback if --db-path not provided)

The verifier opens the DB read-only / query-only and never writes the DB or
touches VM / live output. By default it PUBLISHES the authoritative paper status
to paper_verify_report.json (+ paper_verify_receipt.md / paper_verify_log.jsonl)
next to the DB; the committed DB and the writer's status code are raw accounting
artifacts only. Pass --no-emit for a pure read-only check that writes nothing.
""",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help=(
            "Path to paper_ledger.db. Overrides QNTY_PAPER_DB_PATH. "
            "Required if QNTY_PAPER_DB_PATH is not set."
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory for the published verify artifacts (default: the DB's directory).",
    )
    parser.add_argument(
        "--no-emit",
        action="store_true",
        help=(
            "Do not publish artifacts; run the pure read-only check only "
            "(no paper_verify_report.json is written)."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output a machine-readable JSON report to stdout.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print every failure detail (default prints up to 20).",
    )
    args = parser.parse_args(argv)

    db_path = args.db_path or os.environ.get("QNTY_PAPER_DB_PATH")
    if db_path is None:
        print(
            "ERROR: --db-path is required or set QNTY_PAPER_DB_PATH environment variable.",
            file=sys.stderr,
        )
        parser.print_help(sys.stderr)
        return 1

    if args.no_emit:
        result = verify_database(db_path=db_path)
        report_path = None
    else:
        out = Path(args.output_dir) if args.output_dir else Path(db_path).parent
        result = verify_and_publish(db_path=db_path, output_dir=out)
        report_path = str(out / REPORT_FILE)

    if args.json:
        print(
            json.dumps(
                {
                    "status": result.status,
                    "exit_code": result.exit_code,
                    "failures": result.failures,
                    "report": result.report,
                    "report_path": report_path,
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(f"Status: {result.status} (exit {result.exit_code})")
        print(f"DB:     {result.report.get('db_path')}")
        if report_path is not None:
            print(f"Report: {report_path} (AUTHORITATIVE)")
        if result.status == "PRE_START":
            print("No committed eligible bars yet (valid pre-start DB).")
        elif result.status == "OK":
            print(
                f"Verified: {result.report.get('batches')} batch(es), "
                f"{result.report.get('events')} event(s), "
                f"{result.report.get('equity_rows')} equity row(s)."
            )
        if result.failures:
            shown = result.failures if args.verbose else result.failures[:20]
            print(f"Failures ({len(result.failures)}):")
            for f in shown:
                print(f"  - {f}")
            if not args.verbose and len(result.failures) > len(shown):
                print(f"  ... and {len(result.failures) - len(shown)} more (use --verbose)")
        print(f"\n{VERIFIER_DISCLAIMER}")

    return result.exit_code


if __name__ == "__main__":
    sys.exit(main())
