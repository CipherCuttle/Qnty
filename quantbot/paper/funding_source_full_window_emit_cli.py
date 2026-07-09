"""CLI entry point for full-window funding-source snapshot + bundle emission."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

from quantbot.paper.funding_source_full_window_emit import (
    emit_full_window_funding_source_snapshot,
    FundingSourceSnapshotEmissionError,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qnty-full-window-emit",
        description="Emit a full-window funding-source snapshot and immutable bundle.",
    )
    parser.add_argument(
        "--db",
        required=True,
        help="Path to the SQLite database (opened read-only).",
    )
    parser.add_argument(
        "--funding-source-dir",
        required=True,
        dest="funding_source_dir",
        help="Path to the directory containing funding source CSV files.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        dest="output_dir",
        help="Directory to write snapshot and bundle artifacts.",
    )
    parser.add_argument(
        "--generated-at-utc",
        default=None,
        dest="generated_at_utc",
        help="ISO-8601 UTC timestamp (default: current UTC time).",
    )
    parser.add_argument(
        "--qnty-git-commit",
        default=None,
        dest="qnty_git_commit",
        help="Git commit hash for provenance (default: auto-detected).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        dest="dry_run",
        help="Print what would be done without writing artifacts.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # --- Validate --db ---
    db_path = os.path.abspath(args.db)
    if not os.path.isfile(db_path):
        print(f"ERROR: --db path does not exist: {db_path}", file=sys.stderr)
        return 1

    # --- Validate --funding-source-dir ---
    funding_dir = os.path.abspath(args.funding_source_dir)
    if not os.path.isdir(funding_dir):
        print(
            f"ERROR: --funding-source-dir path does not exist: {funding_dir}",
            file=sys.stderr,
        )
        return 1

    # --- Validate/create --output-dir ---
    output_dir = os.path.abspath(args.output_dir)
    if not os.path.isdir(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    # --- Resolve optional args ---
    generated_at = args.generated_at_utc
    if generated_at is None:
        generated_at = datetime.now(timezone.utc).isoformat()

    git_commit = args.qnty_git_commit

    # --- Dry-run mode ---
    if args.dry_run:
        summary = {
            "status": "DRY_RUN",
            "db": db_path,
            "funding_source_dir": funding_dir,
            "output_dir": output_dir,
            "generated_at_utc": generated_at,
            "qnty_git_commit": git_commit,
        }
        print(json.dumps(summary, indent=2))
        return 0

    # --- Execute ---
    try:
        result = emit_full_window_funding_source_snapshot(
            db_path,
            data_dir=funding_dir,
            generated_at_utc=generated_at,
            qnty_git_commit=git_commit or "",
            writer_or_verifier_command="qnty-full-window-emit",
        )
    except FundingSourceSnapshotEmissionError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    # --- Machine-readable summary ---
    summary = {
        "status": "OK",
        "snapshot_path": str(result.snapshot_path),
        "snapshot_sha256": result.snapshot_sha256,
        "bundle_path": str(result.bundle_path),
        "bundle_sha256": result.source_bundle_sha256,
        "target_batch_id": result.target_batch_id,
        "lane_id": result.lane_id,
        "evaluation_window": result.evaluation_window,
        "resolved_funding_source_dir": result.resolved_funding_source_dir,
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())