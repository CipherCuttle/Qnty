"""Read-only realized attribution reporter (v0).

Deterministic, read-only extraction of the realized/unrealized attribution
fields defined by ``docs/status/realized_attribution_spec.md`` (spec version
1.0.0) from a QNTY paper SQLite ledger.

This module is **read-only evidence tooling**. It:

- opens the ledger in SQLite read-only URI mode (``file:<path>?mode=ro``) and
  sets ``PRAGMA query_only=ON``;
- never creates a WAL/journal/temp/sidecar/output file, and never mutates the
  input DB (byte-for-byte proof is emitted via before/after sha256/size/mtime);
- computes closed-trade realized net PnL as ``SUM(trades.net_pnl)`` and keeps
  it strictly separate from ledger-level nets and from unrealized marks;
- reports missing optional fields as ``UNAVAILABLE_READ_ONLY`` rather than
  inventing values;
- never runs a writer, verifier, or migration, and never upgrades a
  clean-carry label.

It is not strategy work, not shorting work, not live work, not writer work.
``EDGE_UNPROVEN``, ``BLOCK_LIVE_INTEGRATION``, and full-ledger
``CAVEATED_ENGINE_SEMANTICS`` are preserved; this reporter can never change
them.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "realized_attribution_report_v0"
SPEC_VERSION = "1.0.0"

#: Accounting-identity tolerance, adopted verbatim from the spec / verifier.
ACCOUNTING_ABS_TOL = 1e-6

#: Sentinel for optional fields that are genuinely absent in the source DB.
UNAVAILABLE = "UNAVAILABLE_READ_ONLY"

#: Verifier report artifact filename (authoritative status lives here, not in DB).
VERIFY_REPORT_FILE = "paper_verify_report.json"


class ReporterError(Exception):
    """Raised for missing DB / invalid schema / malformed ledger.

    The CLI maps this to a non-zero exit code.
    """


# ---------------------------------------------------------------------------
# Read-only source-integrity helpers
# ---------------------------------------------------------------------------


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _file_stat(path: Path) -> tuple[str, int, int]:
    """Return (sha256, size_bytes, mtime_ns) for read-only integrity proof."""
    st = path.stat()
    return _file_sha256(path), st.st_size, st.st_mtime_ns


# ---------------------------------------------------------------------------
# Schema-tolerant read helpers
# ---------------------------------------------------------------------------


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    except sqlite3.Error:
        return set()
    return {r["name"] for r in rows}


def _has_table(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _get(row: sqlite3.Row | None, key: str, default: Any = UNAVAILABLE) -> Any:
    if row is None:
        return default
    try:
        value = row[key]
    except (IndexError, KeyError):
        return default
    return default if value is None else value


# ---------------------------------------------------------------------------
# Report sections
# ---------------------------------------------------------------------------


def _lane_identity(conn: sqlite3.Connection, warnings: list[str]) -> dict[str, Any]:
    if not _has_table(conn, "paper_config"):
        raise ReporterError("invalid schema: missing paper_config table")
    cols = _table_columns(conn, "paper_config")
    row = conn.execute("SELECT * FROM paper_config WHERE id = 1").fetchone()
    if row is None:
        raise ReporterError("malformed ledger: paper_config has no id=1 row")

    def opt(name: str) -> Any:
        return _get(row, name) if name in cols else UNAVAILABLE

    initial_equity = opt("initial_equity_usd")
    return {
        "lane_id": opt("lane_id"),
        "config_hash": opt("config_hash"),
        "config_hash_v2": opt("config_hash_v2"),
        "git_sha": UNAVAILABLE,  # per-batch stamp; see latest_batch/ledger_batches
        "initial_equity": initial_equity,
        "baseline_label": opt("baseline_label"),
    }


def _latest_batch(conn: sqlite3.Connection) -> dict[str, Any]:
    if not _has_table(conn, "ledger_batches"):
        return {k: UNAVAILABLE for k in ("batch_id", "window_start", "window_end", "watermark", "git_sha")}
    cols = _table_columns(conn, "ledger_batches")
    row = conn.execute(
        "SELECT * FROM ledger_batches "
        "WHERE committed_at IS NOT NULL "
        "ORDER BY batch_id DESC LIMIT 1"
    ).fetchone()

    def opt(name: str) -> Any:
        return _get(row, name) if name in cols else UNAVAILABLE

    return {
        "batch_id": opt("batch_id"),
        "window_start": opt("prior_watermark_bar_ts"),
        "window_end": opt("new_watermark_bar_ts"),
        "watermark": opt("new_watermark_bar_ts"),
        "git_sha": opt("git_sha"),
        "config_hash": opt("config_hash"),
        "lane_id": opt("lane_id"),
    }


def _watermark(conn: sqlite3.Connection) -> Any:
    if not _has_table(conn, "ledger_state"):
        return UNAVAILABLE
    row = conn.execute(
        "SELECT watermark_bar_ts FROM ledger_state WHERE id = 1"
    ).fetchone()
    return _get(row, "watermark_bar_ts")


def _latest_equity(conn: sqlite3.Connection, initial_equity: Any) -> dict[str, Any]:
    if not _has_table(conn, "equity_snapshots"):
        raise ReporterError("invalid schema: missing equity_snapshots table")
    row = conn.execute(
        "SELECT seq, batch_id, bar_ts, realized_gross_pnl, unrealized_pnl, "
        "funding_cum, fees_cum, equity, drawdown, num_open "
        "FROM equity_snapshots ORDER BY seq DESC LIMIT 1"
    ).fetchone()
    if row is None:
        # A valid schema with no committed equity snapshot yet: report empty.
        return {
            "snapshot_ts": UNAVAILABLE,
            "initial_equity": initial_equity,
            "equity": UNAVAILABLE,
            "equity_delta": UNAVAILABLE,
            "realized_gross_pnl": UNAVAILABLE,
            "unrealized_pnl": UNAVAILABLE,
            "funding_cum": UNAVAILABLE,
            "fees_cum": UNAVAILABLE,
            "num_open": UNAVAILABLE,
        }
    equity = _get(row, "equity")
    equity_delta: Any = UNAVAILABLE
    if isinstance(equity, (int, float)) and isinstance(initial_equity, (int, float)):
        equity_delta = equity - initial_equity
    return {
        "snapshot_ts": _get(row, "bar_ts"),
        "initial_equity": initial_equity,
        "equity": equity,
        "equity_delta": equity_delta,
        "realized_gross_pnl": _get(row, "realized_gross_pnl"),
        "unrealized_pnl": _get(row, "unrealized_pnl"),
        "funding_cum": _get(row, "funding_cum"),
        "fees_cum": _get(row, "fees_cum"),
        "num_open": _get(row, "num_open"),
    }


def _realized_attribution(
    conn: sqlite3.Connection, latest_equity: dict[str, Any], warnings: list[str]
) -> dict[str, Any]:
    if not _has_table(conn, "trades"):
        raise ReporterError("invalid schema: missing trades table")

    # Closed-trade decomposition (spec query category 3). Headline realized-net
    # is SUM(trades.net_pnl) — NOT realized_gross - fees_cum - funding_cum.
    trow = conn.execute(
        "SELECT COUNT(*) AS n_closed, "
        "SUM(gross_pnl) AS gross, SUM(fees) AS fees, "
        "SUM(funding) AS funding, SUM(net_pnl) AS net "
        "FROM trades"
    ).fetchone()
    n_closed = int(_get(trow, "n_closed", 0) or 0)
    closed_gross = _get(trow, "gross", 0.0) if n_closed else 0.0
    closed_fees = _get(trow, "fees", 0.0) if n_closed else 0.0
    closed_funding = _get(trow, "funding", 0.0) if n_closed else 0.0
    closed_net = _get(trow, "net", 0.0) if n_closed else 0.0

    fills_count: Any = UNAVAILABLE
    if _has_table(conn, "fills"):
        frow = conn.execute("SELECT COUNT(*) AS c FROM fills").fetchone()
        fills_count = int(_get(frow, "c", 0) or 0)

    ledger_gross = latest_equity.get("realized_gross_pnl", UNAVAILABLE)
    ledger_fees = latest_equity.get("fees_cum", UNAVAILABLE)
    ledger_funding = latest_equity.get("funding_cum", UNAVAILABLE)
    ledger_unrealized = latest_equity.get("unrealized_pnl", UNAVAILABLE)
    equity = latest_equity.get("equity", UNAVAILABLE)
    initial_equity = latest_equity.get("initial_equity", UNAVAILABLE)

    # Accounting identity residual (spec § Accounting Identity):
    #   equity - (initial + realized_gross - fees_cum - funding_cum + unrealized)
    identity_residual: Any = UNAVAILABLE
    parts = [initial_equity, ledger_gross, ledger_fees, ledger_funding, ledger_unrealized, equity]
    if all(isinstance(p, (int, float)) for p in parts):
        identity_residual = equity - (
            initial_equity + ledger_gross - ledger_fees - ledger_funding + ledger_unrealized
        )
        if abs(identity_residual) > ACCOUNTING_ABS_TOL:
            warnings.append(
                f"accounting_identity_residual {identity_residual!r} exceeds "
                f"tolerance {ACCOUNTING_ABS_TOL}"
            )

    # Closed-net identity: SUM(net_pnl) vs SUM(gross - fees - funding).
    closed_net_identity_residual: Any = UNAVAILABLE
    if n_closed and all(
        isinstance(v, (int, float)) for v in (closed_net, closed_gross, closed_fees, closed_funding)
    ):
        closed_net_identity_residual = closed_net - (closed_gross - closed_fees - closed_funding)
        if abs(closed_net_identity_residual) > ACCOUNTING_ABS_TOL:
            warnings.append(
                f"closed_net_identity_residual {closed_net_identity_residual!r} "
                f"exceeds tolerance {ACCOUNTING_ABS_TOL}"
            )

    return {
        "n_closed": n_closed,
        "fills_count": fills_count,
        "closed_trade_realized_gross_pnl": closed_gross,
        "closed_trade_fees": closed_fees,
        "closed_trade_funding": closed_funding,
        "closed_trade_realized_net_pnl": closed_net,
        "ledger_realized_gross_pnl": ledger_gross,
        "ledger_fees_cum": ledger_fees,
        "ledger_funding_cum": ledger_funding,
        "ledger_unrealized_pnl": ledger_unrealized,
        "accounting_identity_residual": identity_residual,
        "closed_net_identity_residual": closed_net_identity_residual,
    }


def _open_positions(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    if not _has_table(conn, "open_positions"):
        return []
    op_cols = _table_columns(conn, "open_positions")
    has_side_col = "side" in op_cols

    # Latest per-symbol unrealized detail, if a snapshot exists.
    unrealized_by_symbol: dict[str, Any] = {}
    if _has_table(conn, "position_snapshots") and _has_table(conn, "position_snapshot_symbols"):
        latest = conn.execute(
            "SELECT seq FROM position_snapshots ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        if latest is not None:
            for r in conn.execute(
                "SELECT symbol, unrealized_gross FROM position_snapshot_symbols "
                "WHERE snapshot_seq = ?",
                (latest["seq"],),
            ).fetchall():
                unrealized_by_symbol[r["symbol"]] = _get(r, "unrealized_gross")

    positions: list[dict[str, Any]] = []
    for row in conn.execute("SELECT * FROM open_positions ORDER BY symbol").fetchall():
        symbol = _get(row, "symbol")
        qty = _get(row, "qty")
        if has_side_col:
            side = _get(row, "side")
        else:
            # Engine is long-only (spec def. #8): only BUY entry / SELL exit
            # fills exist, so an open position with positive qty is long. We do
            # not invent a short side.
            side = "long" if isinstance(qty, (int, float)) and qty > 0 else UNAVAILABLE
        notes = []
        if not has_side_col:
            notes.append("side inferred from long-only engine invariant (no side column)")
        positions.append(
            {
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "entry_price": _get(row, "entry_price"),
                "entry_fee": _get(row, "entry_fee"),
                "funding_accrued": _get(row, "funding_accrued"),
                "hold_bars": _get(row, "hold_bars"),
                "unrealized_pnl": unrealized_by_symbol.get(symbol, UNAVAILABLE),
                "notes": "; ".join(notes) if notes else "",
            }
        )
    return positions


def _evidence_quality(db_path: Path, warnings: list[str]) -> dict[str, Any]:
    """Read verifier/clean-carry status from an existing report artifact only.

    Never runs the verifier, never mutates the DB. If no report exists next to
    the DB, every field is ``UNAVAILABLE_READ_ONLY`` — labels are never
    invented or upgraded.
    """
    fields = [
        "current_verdict",
        "funding_clean_carry_decision",
        "funding_clean_carry_status",
        "funding_clean_carry_reason_codes",
        "funding_clean_carry_batch_decision",
        "funding_clean_carry_batch_status",
        "funding_clean_carry_batch_reason_codes",
        "funding_clean_carry_batch",
    ]
    out: dict[str, Any] = {f: UNAVAILABLE for f in fields}
    out["verify_report_path"] = UNAVAILABLE

    report_path = db_path.parent / VERIFY_REPORT_FILE
    if not report_path.is_file():
        warnings.append(
            f"no {VERIFY_REPORT_FILE} next to DB; verifier/clean-carry fields "
            f"{UNAVAILABLE}"
        )
        return out
    try:
        report = json.loads(report_path.read_text())
    except (OSError, ValueError) as exc:
        warnings.append(f"could not read {VERIFY_REPORT_FILE}: {exc}")
        return out

    out["verify_report_path"] = str(report_path)
    for f in fields:
        if f in report and report[f] is not None:
            out[f] = report[f]
    return out


# ---------------------------------------------------------------------------
# Top-level report
# ---------------------------------------------------------------------------


def build_report(db_path: str | Path, lane_label: str | None = None) -> dict[str, Any]:
    """Build the realized attribution report for ``db_path`` (read-only).

    Raises :class:`ReporterError` on missing DB, invalid schema, or malformed
    ledger.
    """
    path = Path(db_path)
    if not path.is_file():
        raise ReporterError(f"database not found: {path}")

    resolved = path.resolve()
    sha_before, size_before, mtime_before = _file_stat(resolved)

    warnings: list[str] = []
    unavailable_fields: list[str] = []

    uri = f"file:{resolved}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=30.0)
    try:
        conn.execute("PRAGMA query_only=ON")
        conn.row_factory = sqlite3.Row

        lane_identity = _lane_identity(conn, warnings)
        latest_batch = _latest_batch(conn)
        watermark = _watermark(conn)
        if watermark is not UNAVAILABLE:
            latest_batch.setdefault("watermark_ledger_state", watermark)
        latest_equity = _latest_equity(conn, lane_identity.get("initial_equity", UNAVAILABLE))
        realized = _realized_attribution(conn, latest_equity, warnings)
        open_positions = _open_positions(conn)
        evidence_quality = _evidence_quality(resolved, warnings)
    finally:
        conn.close()

    sha_after, size_after, mtime_after = _file_stat(resolved)

    read_only_ok = (
        sha_before == sha_after
        and size_before == size_after
        and mtime_before == mtime_after
    )
    read_only_integrity = "READ_ONLY_CONFIRMED" if read_only_ok else "READ_ONLY_VIOLATION"
    if not read_only_ok:
        warnings.append(
            "read-only integrity check failed: DB file changed during read"
        )

    # Collect which spec-relevant optional fields resolved to UNAVAILABLE.
    def _collect_unavailable(prefix: str, obj: Any) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                _collect_unavailable(f"{prefix}.{k}", v)
        elif obj == UNAVAILABLE:
            unavailable_fields.append(prefix)

    for name, section in (
        ("lane_identity", lane_identity),
        ("latest_batch", latest_batch),
        ("latest_equity", latest_equity),
        ("realized_attribution", realized),
        ("evidence_quality", evidence_quality),
    ):
        _collect_unavailable(name, section)

    return {
        "schema_version": SCHEMA_VERSION,
        "spec_version": SPEC_VERSION,
        "db_path": str(resolved),
        "lane_label": lane_label if lane_label is not None else UNAVAILABLE,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "db_sha256_before": sha_before,
        "db_sha256_after": sha_after,
        "db_size_before": size_before,
        "db_size_after": size_after,
        "db_mtime_before": mtime_before,
        "db_mtime_after": mtime_after,
        "read_only_integrity": read_only_integrity,
        "lane_identity": lane_identity,
        "latest_batch": latest_batch,
        "latest_equity": latest_equity,
        "realized_attribution": realized,
        "open_positions": open_positions,
        "evidence_quality": evidence_quality,
        "unavailable_fields": sorted(set(unavailable_fields)),
        "warnings": warnings,
        # Status labels this reporter preserves and can never change.
        "status_labels": [
            "EDGE_UNPROVEN",
            "BLOCK_LIVE_INTEGRATION",
            "CAVEATED_ENGINE_SEMANTICS",
        ],
    }


def render_json(report: dict[str, Any], pretty: bool = False) -> str:
    """Serialize a report deterministically to JSON."""
    if pretty:
        return json.dumps(report, indent=2, sort_keys=True)
    return json.dumps(report, sort_keys=True, separators=(",", ":"))
