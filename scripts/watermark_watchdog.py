#!/usr/bin/env python3
"""Watermark watchdog — read-only observability sidecar (PR #13).

Reads the ledger watermark (read-only) and checks it against the expected minimum for the
current 8h cycle (00:00 / 08:00 / 16:00 UTC), accounting for QNTY's intentional one-bar
processing lag and a grace window. Emits a watchdog receipt.

Status / exit codes:
  OK       — observed watermark >= expected minimum            -> exit 0
  STALE    — watermark has fallen behind the expected minimum  -> exit 1
  DEFERRED — ledger DB was locked (no spin-retry)              -> exit 0
  ERROR    — unexpected read failure                           -> exit 0 (receipt records it)

Usage:
    python scripts/watermark_watchdog.py [--db-path DB] [--grace-minutes N]
                                         [--out-dir DIR] [--now ISO8601]
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow running from repo root without installing.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from quantbot.paper.db import get_paper_db_path
from quantbot.paper.provenance import git_sha
from quantbot.sidecars import watchdog_receipt_dir
from quantbot.sidecars.ledger_ro import LedgerLocked, read_head_ro
from quantbot.sidecars.time_bars import (
    DEFAULT_GRACE_MINUTES,
    DEFAULT_PROCESSING_LAG_BARS,
    evaluate_watchdog,
    parse_ts,
)
from quantbot.sidecars.receipt import build_watchdog_receipt, write_receipt

RECEIPT_FILE = "watchdog_receipt.json"

# Exit codes by status.
_EXIT = {"OK": 0, "DEFERRED": 0, "ERROR": 0, "STALE": 1}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only watermark staleness watchdog.")
    parser.add_argument("--db-path", default=None,
                        help="Paper ledger DB path (default: get_paper_db_path()).")
    parser.add_argument("--grace-minutes", type=int, default=DEFAULT_GRACE_MINUTES,
                        help=f"Grace window after a boundary (default: {DEFAULT_GRACE_MINUTES}).")
    parser.add_argument("--processing-lag-bars", type=int, default=DEFAULT_PROCESSING_LAG_BARS,
                        help="Intentional closed-bar processing lag "
                             f"(default: {DEFAULT_PROCESSING_LAG_BARS}).")
    parser.add_argument("--out-dir", default=None,
                        help="Receipt output dir (default: watchdog_receipt_dir()).")
    parser.add_argument("--now", default=None,
                        help="Override 'now' (ISO-8601, testing hook). Default: current UTC.")
    args = parser.parse_args(argv)

    db_path = Path(args.db_path) if args.db_path else get_paper_db_path()
    out_dir = Path(args.out_dir) if args.out_dir else watchdog_receipt_dir()
    now = parse_ts(args.now) if args.now else datetime.now(timezone.utc)

    status = "OK"
    overall = "OK"
    detail: dict = {
        "now_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "grace_minutes": args.grace_minutes,
        "processing_lag_bars": args.processing_lag_bars,
    }

    try:
        head = read_head_ro(db_path)
        observed = head["components"].get("watermark_bar_ts")
        status, detail = evaluate_watchdog(
            observed, now, args.grace_minutes, args.processing_lag_bars
        )
        overall = status
    except LedgerLocked:
        status = "DEFERRED"
        overall = "DEFERRED"
    except Exception as exc:  # noqa: BLE001 - record any read failure rather than crash a timer
        status = "ERROR"
        overall = "ERROR"
        detail["error"] = f"{type(exc).__name__}: {exc}"

    receipt = build_watchdog_receipt(
        status=status, overall=overall, detail=detail, generator_commit=git_sha()
    )
    path = write_receipt(out_dir, RECEIPT_FILE, receipt)
    print(
        f"watchdog: status={status} observed={detail.get('observed_watermark')} "
        f"expected_min={detail.get('expected_min_watermark')} -> {path}"
    )
    return _EXIT.get(status, 0)


if __name__ == "__main__":
    sys.exit(main())
