"""CLI stub for offline edge validation — skeleton mode only.

PR A — safe skeleton.  No exchange, engine, DB, or paper imports.
Stdlib + schema only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from quantbot.experiment.offline_edge_schema import (
    CostModelAssumptions,
    ReceiptMetadata,
    SKELETON_ONLY,
    ValidationReceipt,
)

# ── Constants ─────────────────────────────────────────────────────────────

PROD_PATH_PREFIX = "/srv/qnty"
PROD_PAPER_PNL_V1_PATH = "/srv/qnty/output/paper_pnl_v1"
OFFICIAL_REPORT_PATTERNS = ("paper_verify_report.json", "official_report")


# ── Argument Parser ───────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the offline edge validation CLI."""
    parser = argparse.ArgumentParser(
        description="Offline edge validation runner (skeleton mode — no-op)."
    )

    parser.add_argument(
        "--read-only",
        action="store_true",
        required=True,
        help="Read-only mode: no mutations to input data or production paths.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory to write validation_receipt.json",
    )
    parser.add_argument(
        "--bars-dir",
        required=False,
        default=None,
        help="Directory containing bar/candle CSV files",
    )
    parser.add_argument(
        "--funding-dir",
        required=False,
        default=None,
        help="Directory containing funding rate CSV files",
    )
    parser.add_argument(
        "--manifest-dir",
        required=False,
        default=None,
        help="Directory containing manifest JSON files",
    )
    return parser


# ── Prod-path Guard ──────────────────────────────────────────────────────


def refuse_prod_path(path_str: str) -> None:
    """Exit with code 3 if *path_str* is a production or official-report path.

    Parameters
    ----------
    path_str : str
        The path to check.

    Exits
    -----
    sys.exit(3)
        If *path_str* starts with ``PROD_PATH_PREFIX`` or contains any
        ``OFFICIAL_REPORT_PATTERNS`` substring.
    """
    if path_str.startswith(PROD_PATH_PREFIX):
        print(
            f"Refusing to operate on production path: {path_str}",
            file=sys.stderr,
        )
        sys.exit(3)

    for pattern in OFFICIAL_REPORT_PATTERNS:
        if pattern in path_str:
            print(
                f"Refusing to operate on official report path: {path_str}",
                file=sys.stderr,
            )
            sys.exit(3)


# ── Main ─────────────────────────────────────────────────────────────────


def main() -> None:
    """Parse args, guard prod paths, write skeleton receipt, exit 0."""
    parser = build_parser()
    args = parser.parse_args()

    # Guard production paths
    refuse_prod_path(args.output_dir)
    if args.bars_dir is not None:
        refuse_prod_path(args.bars_dir)
    if args.funding_dir is not None:
        refuse_prod_path(args.funding_dir)
    if args.manifest_dir is not None:
        refuse_prod_path(args.manifest_dir)

    # Build skeleton receipt
    receipt: ValidationReceipt = ValidationReceipt(
        validation_receipt=ReceiptMetadata(
            tool_name="offline_edge_validator",
            tool_version="0.1.0",
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            pipeline_description="skeleton",
        ),
        input_manifest_fingerprint="PLACEHOLDER_SKELETON_NO_OP",
        cost_model_assumptions=CostModelAssumptions(
            slippage_bps_per_side=5.0,
            commission_bps_per_side=5.0,
            heat_cap=1.0,
            vol_lookback_bars=90,
            vol_floor=1e-6,
        ),
        per_stage_metrics={},
        final_verdict=SKELETON_ONLY,
    )

    # Ensure output directory exists
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Write receipt
    receipt_path = output_dir / "validation_receipt.json"
    with open(receipt_path, "w") as f:
        json.dump(receipt, f, indent=2)

    # Summary to stdout
    print(f"Validation receipt written to {receipt_path}")
    print(f"Final verdict: {receipt['final_verdict']}")
    print("Mode: read-only skeleton (no-op)")


if __name__ == "__main__":
    main()