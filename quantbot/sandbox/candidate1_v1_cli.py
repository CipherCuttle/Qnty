"""CLI for the Candidate 1 synthetic-only sandbox."""
from __future__ import annotations
import argparse
import hashlib
import sys
from pathlib import Path
from .candidate1_v1 import (SCENARIOS, RULE_KINDS, SandboxValidationError, load_bundle,
                            run_bundle, verify_receipt_bytes)

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m quantbot.sandbox.candidate1_v1_cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list-rules")
    sub.add_parser("list-scenarios")
    run = sub.add_parser("run"); run.add_argument("--variants", required=True); run.add_argument("--out", required=True)
    verify = sub.add_parser("verify"); verify.add_argument("--receipt", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "list-rules":
            print("\n".join(RULE_KINDS)); return 0
        if args.command == "list-scenarios":
            print("\n".join(s["scenario_id"] for s in SCENARIOS)); return 0
        if args.command == "run":
            _, digest = run_bundle(Path(args.variants), Path(args.out)); print(f"RECEIPT_SHA256={digest}"); return 0
        data = Path(args.receipt).read_bytes(); verify_receipt_bytes(data)
        print(f"RECEIPT_VERIFY_OK sha256={hashlib.sha256(data).hexdigest()}"); return 0
    except FileExistsError:
        print("output path already exists", file=sys.stderr); return 4
    except FileNotFoundError as error:
        print(f"path not found: {error.filename or error}", file=sys.stderr); return 2 if args.command != "run" else 4
    except (OSError, SandboxValidationError, ValueError) as error:
        print(f"{error}", file=sys.stderr)
        return 3 if args.command == "verify" else 2

if __name__ == "__main__":
    raise SystemExit(main())
