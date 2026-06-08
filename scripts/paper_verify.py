#!/usr/bin/env python3
"""Authoritative, read-only verifier for the paper_pnl_v1 ledger (verify-run snapshot model).

.. deprecated::
   JSONL paper path is deprecated by ADR 0001 (SQLite path).
   Kept for rollback / historical compatibility.
   Do not delete yet.

This is the ONLY component that publishes an authoritative paper status. Each invocation freezes
the exact bytes of every input into `verify_runs/<run_id>/inputs/`, verifies that frozen snapshot
(re-deriving the verdict from the snapshotted ledgers — it does NOT trust the runner's
paper_pnl_summary.json status), and writes:
  - verify_runs/<run_id>/paper_verify_report.json   (per-run terminal report)
  - verify_runs/<run_id>/paper_verify_receipt.md    (per-run receipt)
  - paper_verify_report.json   (top-level pointer to the latest terminal report — AUTHORITATIVE)
  - paper_verify_receipt.md    (latest human receipt)
  - paper_verify_trusted_ok.json (preserved trusted OK baseline — advanced ONLY on OK)
  - paper_verify_log.jsonl     (append-only audit trail; NON-gating)

A paper run is trusted iff the latest paper_verify_report.json says OK. A CORRUPT/INCOMPLETE/
CONFIG_ERROR/RUNNING_STALE/NEEDS_BOOTSTRAP run never overwrites the trusted baseline, so detected
tampering is not forgotten. See docs/paper_pnl_v1_schema.md § 5a.

This is a SIMULATION. Paper PnL is not live trading.

Usage:
    python scripts/paper_verify.py
    python scripts/paper_verify.py --bootstrap         # establish the first trusted baseline
    QNTY_PAPER_OUTPUT_DIR=... python scripts/paper_verify.py --output-dir ...
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from quantbot.paper.verify import verify


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Authoritative read-only verifier for paper_pnl_v1 ledger"
    )
    parser.add_argument("--bootstrap", action="store_true", help="Establish first trusted baseline")
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir) if args.output_dir else None
    result = verify(output_dir=output_dir, bootstrap=args.bootstrap)

    if result["status"] == "OK":
        print("Paper verify OK (authoritative).")
        if result.get("report"):
            print(f"  runs checked: {result['report'].get('runs_checked', '?')}")
            print(f"  failures:     {result['report'].get('failure_count', 0)}")
        return 0

    if result["status"] in ("INCOMPLETE", "RUNNING_STALE", "NEEDS_BOOTSTRAP"):
        print(f"Paper verify NOT YET CERTIFIABLE: {result['status']}")
        if result.get("report"):
            print(f"  detail: {result['report'].get('reason', '')}")
        return 5

    # CONFIG_ERROR or CORRUPT
    print(f"Paper verify FAILED: {result['status']}")
    if result.get("report"):
        for f in result["report"].get("failures", [])[:10]:
            print(f"  - {f}")
    return 3 if result["status"] == "CONFIG_ERROR" else 4


if __name__ == "__main__":
    sys.exit(main())
