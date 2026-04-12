"""Minimal CLI entrypoint for Qnty replay."""

import argparse
import sys
from pathlib import Path

from quantbot.app.run_replay import run_replay
from quantbot.version import ENGINE_VERSION


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qnty-replay", description="Qnty replay runner")
    parser.add_argument("--version", action="version", version=f"%(prog)s {ENGINE_VERSION}")
    parser.add_argument("--manifest", required=True, type=Path, help="Path to manifest JSON")
    parser.add_argument("--csv", required=True, type=Path, help="Path to bars CSV")
    parser.add_argument("--out", required=True, type=Path, help="Output directory")
    parser.add_argument("--sha256-sidecar", action="store_true", help="Emit .sha256 sidecar")
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 1

    try:
        receipt_path = run_replay(
            manifest_path=args.manifest,
            csv_path=args.csv,
            output_dir=args.out,
            emit_sha256=args.sha256_sidecar,
        )
        print(receipt_path)
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
