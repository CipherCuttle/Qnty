"""Index CLI for QuantBot.

qnty-index path [path ...]

Paper mode only - no live trading, no profitability claims.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from quantbot.experiment.index import IndexedExperiment, index_experiment_artifacts


def _format_row(exp: IndexedExperiment) -> str:
    """Format a single indexed experiment as a compact text row."""
    return (
        f"{exp.experiment_name} | {exp.strategy_name} | {exp.fixture_name} | "
        f"{exp.gate_status or 'N/A'} | {exp.split_count} | {exp.signal_count} | "
        f"{exp.result_type} | {exp.artifact_path}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="qnty-index",
        description="Index experiment artifacts and produce a normalized summary.",
    )
    parser.add_argument(
        "paths",
        type=Path,
        nargs="+",
        help="Paths to experiment_result.json or walkforward_result.json files, "
             "or directories containing them.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON array.",
    )

    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 1

    # Validate paths exist
    for p in args.paths:
        if not p.exists():
            print(f"Error: Path does not exist: {p}", file=sys.stderr)
            return 1

    # Index artifacts
    try:
        indexed = index_experiment_artifacts(args.paths)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    # Handle empty result
    if not indexed:
        if args.json:
            print("[]")
        else:
            print("No artifacts found.")
        return 0

    # Output
    if args.json:
        # Machine-readable JSON: list of dicts
        records = [
            {
                "experiment_name": e.experiment_name,
                "strategy_name": e.strategy_name,
                "fixture_name": e.fixture_name,
                "gate_status": e.gate_status,
                "split_count": e.split_count,
                "signal_count": e.signal_count,
                "receipt_digest": e.receipt_digest,
                "artifact_path": str(e.artifact_path),
                "result_type": e.result_type,
            }
            for e in indexed
        ]
        print(json.dumps(records, indent=2))
    else:
        # Header
        print(
            "experiment_name | strategy_name | fixture_name | gate_status | "
            "split_count | signal_count | result_type | artifact_path"
        )
        # Rows
        for exp in indexed:
            print(_format_row(exp))

    return 0