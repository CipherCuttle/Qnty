#!/usr/bin/env python3
"""Authoritative, read-only verifier for the paper_pnl_v1 ledger (verify-run snapshot model).

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
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from quantbot.paper.verify import (  # noqa: E402
    STATUS_CONFIG_ERROR,
    STATUS_CORRUPT,
    STATUS_INCOMPLETE,
    STATUS_NEEDS_BOOTSTRAP,
    STATUS_OK,
    STATUS_RUNNING_STALE,
    STATUS_VERIFYING,
    verify,
)

# Exit codes:
#   0 = OK         — authoritative: the snapshot reconciles and is trusted (simulation).
#   3 = CONFIG_ERROR — stale/incompatible/unloadable paper_config.json.
#   4 = CORRUPT    — an integrity invariant failed; the run is NOT trusted (also any unknown /
#                    in-flight VERIFYING status that should never be returned).
#   5 = INCOMPLETE / RUNNING_STALE / NEEDS_BOOTSTRAP — nothing certifiable yet, a crashed/in-flight
#                    run, or committed ledgers awaiting an explicit --bootstrap baseline.
_EXIT = {
    STATUS_OK: 0,
    STATUS_CONFIG_ERROR: 3,
    STATUS_CORRUPT: 4,
    STATUS_INCOMPLETE: 5,
    STATUS_RUNNING_STALE: 5,
    STATUS_NEEDS_BOOTSTRAP: 5,
    # VERIFYING is an in-flight marker verify() never returns; if it ever surfaces, fail closed.
    STATUS_VERIFYING: 4,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify the paper_pnl_v1 ledger (authoritative)")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument(
        "--bootstrap",
        action="store_true",
        help="Establish the first trusted OK baseline when committed ledgers exist but none has "
        "been anchored yet (operator action; use once after reviewing the first committed bars).",
    )
    args = parser.parse_args(argv)

    report = verify(
        output_dir=Path(args.output_dir) if args.output_dir else None,
        bootstrap=args.bootstrap,
    )
    status = report["status"]

    print(f"PAPER VERIFY: {status} (SIMULATION) — authoritative status in paper_verify_report.json")
    print(f"  verify-run:       {report['verify_run_dir']}/")
    print(f"  forward_start_ts: {report['forward_start_ts']}")
    print(f"  committed bars:   {report['bars_committed']}")
    print(f"  verdict:          {report['current_verdict']}")
    if report["failures"]:
        print(f"  failures ({report['failure_count']}):")
        for f in report["failures"][:10]:
            print(f"    - {f}")
    return _EXIT.get(status, 4)


if __name__ == "__main__":
    sys.exit(main())
