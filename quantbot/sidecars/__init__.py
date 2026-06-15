"""Read-only observability sidecars for the paper lane (PR #13).

Strictly additive and observability-only: these helpers read the latest paper report
JSON and the SQLite ledger (read-only) and emit standalone receipts. They never write to
the paper DB, never mutate the paper lane, and write only into separate receipt directories.

Two sidecars are built on this library:
  - health receipt generator  (scripts/health_receipt.py)
  - watermark watchdog         (scripts/watermark_watchdog.py)

See docs/ADR/0001-paper-sqlite-ledger.md for the ledger contract this observes.
"""

from __future__ import annotations

import os
from pathlib import Path

# Bumped only on a breaking change to receipt schemas.
SIDECAR_SCHEMA_VERSION = 1


def receipts_root() -> Path:
    """Root directory for sidecar receipts.

    Override with ``QNTY_RECEIPTS_DIR`` (used for tests / dev boxes where /srv/qnty does
    not exist). Default is a sibling of the paper output, never inside it.
    """
    return Path(os.environ.get("QNTY_RECEIPTS_DIR", "/srv/qnty/receipts"))


def health_receipt_dir() -> Path:
    """Output directory for health receipts (``<root>/health``)."""
    return receipts_root() / "health"


def watchdog_receipt_dir() -> Path:
    """Output directory for watchdog receipts (``<root>/watchdog``)."""
    return receipts_root() / "watchdog"
