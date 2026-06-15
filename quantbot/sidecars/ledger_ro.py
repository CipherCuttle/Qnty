"""Read-only ledger access for sidecars.

Everything here opens the paper ledger in SQLite read-only mode (``mode=ro`` +
``PRAGMA query_only=ON`` via :func:`quantbot.paper.db.connect_readonly`), so any accidental
write raises ``sqlite3.OperationalError``. Reads are short-lived: open, read, close. There is
no spin-retry — if the DB is locked we raise :class:`LedgerLocked` and the caller emits a
DEFERRED receipt and exits 0.

Ledger identity here is *logical* (a ``head_fingerprint`` over stable read-only values), never a
raw hash of the .db file — WAL/checkpoint churn makes physical file hashes noisy. Physical file
metadata (size, mtime, user_version, wal_present) is recorded separately for forensics only.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quantbot.core.determinism import canonical_json_dumps
from quantbot.paper.db import connect_readonly


class LedgerLocked(Exception):
    """Raised when the ledger DB is locked (busy writer). Caller should DEFER, not retry."""


def _is_locked(exc: sqlite3.OperationalError) -> bool:
    msg = str(exc).lower()
    return "database is locked" in msg or "database is busy" in msg


def open_ro(db_path: str | Path) -> sqlite3.Connection:
    """Open a read-only, snapshot-pinned connection to the ledger.

    Mirrors the verifier's ``_open_snapshot``: a ``BEGIN`` plus a first read pin one WAL
    snapshot for all subsequent reads on this connection. The caller must close it.
    """
    conn = connect_readonly(db_path)
    conn.execute("BEGIN")
    # First read pins the WAL snapshot for every subsequent query on this connection.
    conn.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
    return conn


def _scalar(conn: sqlite3.Connection, sql: str) -> Any:
    row = conn.execute(sql).fetchone()
    if row is None:
        return None
    return row[0]


def _canon_num(value: Any) -> float | None:
    """Canonicalize a numeric value for deterministic fingerprinting.

    Rounds to 8 decimals (the repo's accounting convention) so platform float repr can never
    vary the fingerprint across reads. Returns ``None`` unchanged.
    """
    if value is None:
        return None
    return round(float(value), 8)


def read_head(conn: sqlite3.Connection) -> dict[str, Any]:
    """Read the logical ledger-head components over a pinned read-only snapshot.

    Numeric fields (equity, drawdown) are canonicalized so the fingerprint is reproducible.
    """
    watermark = _scalar(conn, "SELECT watermark_bar_ts FROM ledger_state WHERE id = 1")

    eq_row = conn.execute(
        "SELECT seq, bar_ts, equity, drawdown FROM equity_snapshots "
        "ORDER BY seq DESC LIMIT 1"
    ).fetchone()
    latest_equity: dict[str, Any] | None
    if eq_row is None:
        latest_equity = None
    else:
        latest_equity = {
            "seq": eq_row["seq"],
            "bar_ts": eq_row["bar_ts"],
            "equity": _canon_num(eq_row["equity"]),
            "drawdown": _canon_num(eq_row["drawdown"]),
        }

    counts = {
        "ledger_batches": int(_scalar(conn, "SELECT COUNT(*) FROM ledger_batches") or 0),
        "ledger_events": int(_scalar(conn, "SELECT COUNT(*) FROM ledger_events") or 0),
        "equity_snapshots": int(_scalar(conn, "SELECT COUNT(*) FROM equity_snapshots") or 0),
    }

    return {
        "watermark_bar_ts": watermark,
        "latest_equity": latest_equity,
        "counts": counts,
        "max_batch_id": _scalar(conn, "SELECT MAX(batch_id) FROM ledger_batches"),
        "max_event_seq": _scalar(conn, "SELECT MAX(seq) FROM ledger_events"),
    }


def head_fingerprint(components: dict[str, Any]) -> str:
    """SHA-256 over the canonical JSON of the (already canonicalized) head components."""
    payload = canonical_json_dumps(components).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def read_head_ro(db_path: str | Path) -> dict[str, Any]:
    """Short-lived read of the logical head: open RO, read, close.

    Returns ``{"components": {...}, "head_fingerprint": "<hex>"}``. Raises :class:`LedgerLocked`
    if the DB is locked (no spin-retry).
    """
    try:
        conn = open_ro(db_path)
    except sqlite3.OperationalError as exc:
        if _is_locked(exc):
            raise LedgerLocked(str(exc)) from exc
        raise
    try:
        components = read_head(conn)
    except sqlite3.OperationalError as exc:
        if _is_locked(exc):
            raise LedgerLocked(str(exc)) from exc
        raise
    finally:
        conn.close()
    return {"components": components, "head_fingerprint": head_fingerprint(components)}


def physical_metadata(db_path: str | Path) -> dict[str, Any]:
    """Physical DB-file metadata for forensics — NOT a stable identity.

    Records size, mtime, ``PRAGMA user_version`` and whether a ``-wal`` sidecar file is present.
    Deliberately does NOT hash the .db file (WAL/checkpoint churn makes that noisy).
    """
    path = Path(db_path)
    meta: dict[str, Any] = {
        "db_path": str(path),
        "db_size_bytes": None,
        "db_mtime_utc": None,
        "user_version": None,
        "wal_present": Path(str(path) + "-wal").exists(),
    }
    try:
        stat = path.stat()
        meta["db_size_bytes"] = stat.st_size
        meta["db_mtime_utc"] = (
            datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        )
    except OSError:
        pass

    try:
        conn = connect_readonly(db_path)
        try:
            meta["user_version"] = _scalar(conn, "PRAGMA user_version")
        finally:
            conn.close()
    except sqlite3.OperationalError as exc:
        if _is_locked(exc):
            raise LedgerLocked(str(exc)) from exc
        # Unreadable PRAGMA is non-fatal for forensics metadata.
        meta["user_version"] = None
    return meta
