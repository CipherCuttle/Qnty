#!/usr/bin/env python3
"""Read-only realized attribution reporter for QNTY paper ledgers (v0).

Deterministic, read-only extraction of the realized/unrealized attribution
fields defined by ``docs/status/realized_attribution_spec.md``. Makes a dated
attribution snapshot reproducible without ad-hoc SQL.

Usage::

    python scripts/qnty-paper-realized-attribution.py --db-path <path> --json
    python scripts/qnty-paper-realized-attribution.py --db-path <path> --json --pretty
    python scripts/qnty-paper-realized-attribution.py --db-path <path> --json --lane-label prod

This tool is READ-ONLY evidence tooling. It opens the ledger with SQLite
``mode=ro`` + ``PRAGMA query_only=ON``, never runs a writer/verifier/migration,
never mutates the DB, and only prints JSON to stdout. It preserves
EDGE_UNPROVEN, BLOCK_LIVE_INTEGRATION, and full-ledger CAVEATED_ENGINE_SEMANTICS
and cannot change them.

Exit codes:
  0  report emitted
  1  missing DB / invalid schema / malformed ledger
  2  read-only integrity violation (DB changed during read)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running from repo root without installing.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quantbot.paper.realized_attribution import (
    ReporterError,
    build_report,
    render_json,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only realized attribution reporter for QNTY paper ledgers.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--db-path",
        required=True,
        help="Path to the paper_ledger.db SQLite file (opened read-only).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the report as JSON to stdout.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print the JSON (indented, sorted keys).",
    )
    parser.add_argument(
        "--lane-label",
        default=None,
        help="Optional human lane label recorded in the report provenance.",
    )
    args = parser.parse_args(argv)

    try:
        report = build_report(args.db_path, lane_label=args.lane_label)
    except ReporterError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    output = render_json(report, pretty=args.pretty)
    print(output)

    if report.get("read_only_integrity") != "READ_ONLY_CONFIRMED":
        print(
            "error: read-only integrity violation (DB changed during read)",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
