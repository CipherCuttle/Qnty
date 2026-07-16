"""CLI for the QNTY cross-agent continuity control plane.

Usage:
    python -m quantbot.continuity verify [--root PATH]
    python -m quantbot.continuity show [--root PATH]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from quantbot.continuity.context import (
    ACTIVE_TASK_RELPATH,
    load_and_verify_continuity_state,
    render_context_packet,
)


def _discover_root(explicit: str | None) -> Path:
    if explicit is not None:
        return Path(explicit)
    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if (candidate / ACTIVE_TASK_RELPATH).is_file():
            return candidate
    print(
        f"CONTINUITY_VERIFY_FAILED: {ACTIVE_TASK_RELPATH} not found from {current}; pass --root",
        file=sys.stderr,
    )
    raise SystemExit(1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m quantbot.continuity")
    parser.add_argument("command", choices=("verify", "show"))
    parser.add_argument("--root", default=None, help="repository root (default: discover from cwd)")
    args = parser.parse_args(argv)
    root = _discover_root(args.root)
    try:
        state = load_and_verify_continuity_state(root)
    except ValueError as error:
        print(f"CONTINUITY_VERIFY_FAILED: {error}", file=sys.stderr)
        return 1
    if args.command == "verify":
        print(f"CONTINUITY_VERIFY_OK handoff_receipt_sha256={state['handoff_receipt_sha256']}")
        return 0
    print(render_context_packet(state))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
