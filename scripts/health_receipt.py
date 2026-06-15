#!/usr/bin/env python3
"""Health receipt generator — read-only observability sidecar (PR #13).

Reads the latest paper report JSON and the SQLite ledger (read-only) and emits a standalone
health receipt: the hashed paper report, a logical ledger-head fingerprint, physical DB
metadata, and best-effort host/service context. It NEVER writes to the paper DB and writes only
into a separate receipt directory.

Overall status:
  OK       — report present and consistent, ledger read cleanly
  WARN     — soft anomaly (report status != OK, failures > 0, commit mismatch)
  DEFERRED — ledger DB was locked (no spin-retry); try again next tick
  ERROR    — paper report missing/unreadable, or an unexpected read failure

Always exits 0 (health is informational; the watchdog is the gating sidecar).

Usage:
    python scripts/health_receipt.py [--paper-output-dir DIR] [--db-path DB]
                                     [--out-dir DIR] [--expected-commit SHA]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Allow running from repo root without installing.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from quantbot.core.determinism import sha256_file
from quantbot.paper import paper_output_dir
from quantbot.paper.db import get_paper_db_path
from quantbot.paper.provenance import git_sha
from quantbot.paper.sqlite_verify import REPORT_FILE
from quantbot.sidecars import health_receipt_dir
from quantbot.sidecars.ledger_ro import LedgerLocked, physical_metadata, read_head_ro
from quantbot.sidecars.receipt import (
    build_health_receipt,
    host_stats,
    service_status,
    write_receipt,
)

RECEIPT_FILE = "health_receipt.json"

# Units the receipt reports on (read-only `systemctl show`); degrade to "unknown" if absent.
WATCHED_UNITS = [
    "qnty-paper-pnl.service",
    "qnty-paper-pnl.timer",
    "qnty-shadow-run.timer",
]


def _load_report(report_path: Path) -> dict | None:
    try:
        with open(report_path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a read-only paper health receipt.")
    parser.add_argument("--paper-output-dir", default=None,
                        help="Dir holding paper_verify_report.json (default: paper_output_dir()).")
    parser.add_argument("--db-path", default=None,
                        help="Paper ledger DB path (default: get_paper_db_path()).")
    parser.add_argument("--out-dir", default=None,
                        help="Receipt output dir (default: health_receipt_dir()).")
    parser.add_argument("--expected-commit", default=None,
                        help="Optional expected generator commit; falls back to "
                             "QNTY_EXPECTED_COMMIT. Absent -> null / not checked.")
    args = parser.parse_args(argv)

    paper_dir = Path(args.paper_output_dir) if args.paper_output_dir else paper_output_dir()
    db_path = Path(args.db_path) if args.db_path else get_paper_db_path()
    out_dir = Path(args.out_dir) if args.out_dir else health_receipt_dir()
    expected_commit = args.expected_commit or os.environ.get("QNTY_EXPECTED_COMMIT") or None

    report_path = paper_dir / REPORT_FILE
    report = _load_report(report_path)
    report_sha = sha256_file(report_path) if report_path.exists() else None

    overall = "OK"
    ledger_head: dict | None = None
    ledger_physical: dict | None = None

    try:
        ledger_head = read_head_ro(db_path)
        ledger_physical = physical_metadata(db_path)
    except LedgerLocked:
        overall = "DEFERRED"

    if overall != "DEFERRED":
        if report is None:
            overall = "ERROR"
        else:
            failures = report.get("failure_count") or 0
            commit_mismatch = (
                expected_commit is not None and git_sha() != expected_commit
            )
            if report.get("status") != "OK" or failures > 0 or commit_mismatch:
                overall = "WARN"

    receipt = build_health_receipt(
        generator_commit=git_sha(),
        expected_commit=expected_commit,
        paper_report=report,
        paper_report_sha256=report_sha,
        ledger_head=ledger_head,
        ledger_physical=ledger_physical,
        services=service_status(WATCHED_UNITS),
        host=host_stats(disk_path=out_dir.parent if out_dir.parent.exists() else "/"),
        overall=overall,
    )

    path = write_receipt(out_dir, RECEIPT_FILE, receipt)
    print(f"health receipt: overall={overall} -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
