#!/usr/bin/env python3
"""Reconcile the paper_pnl_v1 ledger. Exits non-zero on any invariant failure.

.. deprecated::
   JSONL paper path is deprecated by ADR 0001 (SQLite path).
   Kept for rollback / historical compatibility.
   Do not delete yet.

Usage:
    python scripts/paper_reconcile.py
    QNTY_PAPER_OUTPUT_DIR=... python scripts/paper_reconcile.py
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from quantbot.paper import paper_output_dir
from quantbot.paper.reconcile import reconcile


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reconcile paper_pnl_v1 ledger")
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args(argv)

    out = Path(args.output_dir) if args.output_dir else paper_output_dir()
    failures = reconcile(out)

    if failures:
        print(f"RECONCILE FAILED ({len(failures)} issue(s)):")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("RECONCILE PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
