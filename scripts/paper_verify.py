#!/usr/bin/env python3
"""Authoritative, read-only verifier for the paper_pnl_v1 ledger.

This is the ONLY component that publishes an authoritative paper status. It reads every paper
artifact read-only, re-derives the verdict from the ledgers themselves (it does NOT trust the
runner's paper_pnl_summary.json status), and writes:
  - paper_verify_report.json  (authoritative status)
  - paper_verify_receipt.md   (human receipt)
  - paper_verify_log.jsonl    (append-only audit trail)

A paper run is only trusted if this report says OK. See docs/paper_pnl_v1_schema.md § 5a.

This is a SIMULATION. Paper PnL is not live trading.

Usage:
    python scripts/paper_verify.py
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
    STATUS_OK,
    STATUS_RUNNING_STALE,
    STATUS_VERIFYING,
    verify,
)

# Exit codes:
#   0 = OK         — authoritative: the paper run reconciles and is trusted (simulation).
#   3 = CONFIG_ERROR — stale/incompatible/unloadable paper_config.json.
#   4 = CORRUPT    — an integrity invariant failed; the run is NOT trusted (also any unknown /
#                    in-flight VERIFYING status that should never be returned).
#   5 = INCOMPLETE / RUNNING_STALE — nothing certifiable yet, or a crashed/in-flight run.
_EXIT = {
    STATUS_OK: 0,
    STATUS_CONFIG_ERROR: 3,
    STATUS_CORRUPT: 4,
    STATUS_INCOMPLETE: 5,
    STATUS_RUNNING_STALE: 5,
    # VERIFYING is an in-flight marker verify() never returns; if it ever surfaces, fail closed.
    STATUS_VERIFYING: 4,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify the paper_pnl_v1 ledger (authoritative)")
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args(argv)

    report = verify(output_dir=Path(args.output_dir) if args.output_dir else None)
    status = report["status"]

    print(f"PAPER VERIFY: {status} (SIMULATION) — authoritative status in paper_verify_report.json")
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
