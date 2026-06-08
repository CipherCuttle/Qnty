"""Read-only SQLite paper ledger verifier (Phase 3).

Opens ``paper_ledger.db`` read-only (URI ``mode=ro`` + ``PRAGMA query_only=ON``)
and validates the committed DB state from the typed tables. The verifier never
writes the DB, never writes artifacts, and never touches VM / live output.

It is a parallel implementation to the JSONL verifier in ``verify.py``; it does
NOT reuse the JSONL snapshot / trusted-baseline authority logic. The committed DB
is the record; this verifier reports on it.

Statuses / exit codes:
  OK            0   DB verified consistent
  CONFIG_ERROR  3   DB/config identity invalid
  CORRUPT       4   a verification invariant failed
  PRE_START     5   valid DB, no committed eligible bars yet

Verifier v1 scope (see disclaimer ``VERIFIER_DISCLAIMER``): it validates SQLite
ledger integrity and internal accounting consistency. It does NOT independently
rederive OHLCV marks / unrealized PnL / exposure from source price data, and it
does NOT re-derive ``source_observation_digest`` from a canonical source JSON
(Phase 2 does not persist the full source observation row — only the consumed
subset). See ``docs/ADR/0001-paper-sqlite-ledger.md``.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from quantbot.paper import (
    BASELINE_LABEL,
    PAPER_ENGINE_VERSION,
    SCHEMA_VERSION,
)
from quantbot.paper.db import (
    DB_SCHEMA_VERSION,
    config_hash_from_row,
    connect_readonly,
    get_paper_db_path,
)

# ---------------------------------------------------------------------------
# Statuses / exit codes
# ---------------------------------------------------------------------------

STATUS_OK = "OK"
STATUS_CONFIG_ERROR = "CONFIG_ERROR"
STATUS_CORRUPT = "CORRUPT"
STATUS_PRE_START = "PRE_START"

EXIT_CODE: dict[str, int] = {
    STATUS_OK: 0,
    STATUS_CONFIG_ERROR: 3,
    STATUS_CORRUPT: 4,
    STATUS_PRE_START: 5,
}

VERIFIER_DISCLAIMER = (
    "Verifier v1 validates SQLite ledger integrity and internal accounting "
    "consistency. It does not independently rederive OHLCV marks/unrealized "
    "PnL/exposure from source price data."
)

# Numeric tolerances
_ABS_TOL = 1e-6
_TIGHT_TOL = 1e-8

# Required tables / triggers / indexes expected from the Phase 1 substrate.
_REQUIRED_TABLES = [
    "paper_config",
    "ledger_batches",
    "ledger_events",
    "signal_snapshots",
    "fills",
    "trades",
    "funding",
    "position_snapshots",
    "position_snapshot_symbols",
    "equity_snapshots",
    "ledger_state",
    "open_positions",
]

_APPEND_ONLY_TABLES = [
    "paper_config",
    "ledger_events",
    "signal_snapshots",
    "fills",
    "trades",
    "funding",
    "position_snapshots",
    "position_snapshot_symbols",
    "equity_snapshots",
]

_REQUIRED_INDEXES = [
    "idx_ledger_events_event_type",
    "idx_ledger_events_bar_ts",
    "idx_ledger_events_symbol",
    "idx_ledger_events_batch_id",
]

# event_type -> typed table
_EVENT_TABLE: dict[str, str] = {
    "signal_snapshot": "signal_snapshots",
    "funding": "funding",
    "fill": "fills",
    "trade": "trades",
    "position_snapshot": "position_snapshots",
    "equity_snapshot": "equity_snapshots",
}

_EVENT_TYPES = list(_EVENT_TABLE.keys())

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_HEX16 = re.compile(r"^[0-9a-f]{16}$")


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class VerifyResult:
    status: str
    failures: list[str] = field(default_factory=list)
    report: dict[str, Any] = field(default_factory=dict)

    @property
    def exit_code(self) -> int:
        return EXIT_CODE[self.status]

    @property
    def ok(self) -> bool:
        return self.status == STATUS_OK


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def _scalar(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> Any:
    row = conn.execute(sql, params).fetchone()
    if row is None:
        return None
    return row[0]


def _close(value: float | None, expected: float | None, tol: float = _ABS_TOL) -> bool:
    if value is None or expected is None:
        return value is expected
    return abs(value - expected) <= tol


# ---------------------------------------------------------------------------
# Structural / identity validation
# ---------------------------------------------------------------------------

def _validate_schema_presence(conn: sqlite3.Connection) -> list[str]:
    """Return failures for missing tables, append-only triggers, or indexes."""
    failures: list[str] = []
    names = {
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    for tbl in _REQUIRED_TABLES:
        if tbl not in names:
            failures.append(f"Missing required table: {tbl}")

    trigger_names = {
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'"
        ).fetchall()
    }
    for tbl in _APPEND_ONLY_TABLES:
        for action in ("update", "delete"):
            trg = f"trg_{tbl}_deny_{action}"
            if trg not in trigger_names:
                failures.append(f"Missing append-only trigger: {trg}")

    index_names = {
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    }
    for idx in _REQUIRED_INDEXES:
        if idx not in index_names:
            failures.append(f"Missing required index: {idx}")

    return failures


def _validate_identity(conn: sqlite3.Connection) -> tuple[dict | None, list[str]]:
    """Validate paper_config identity. Returns (config_row, failures)."""
    failures: list[str] = []
    row = conn.execute("SELECT * FROM paper_config WHERE id = 1").fetchone()
    if row is None:
        return None, ["paper_config row (id=1) not found"]
    cfg = dict(row)

    if cfg.get("db_schema_version") != DB_SCHEMA_VERSION:
        failures.append(
            f"db_schema_version mismatch: stored={cfg.get('db_schema_version')!r}, "
            f"expected={DB_SCHEMA_VERSION!r}"
        )
    if cfg.get("paper_contract_version") != SCHEMA_VERSION:
        failures.append(
            f"paper_contract_version mismatch: stored={cfg.get('paper_contract_version')!r}, "
            f"expected={SCHEMA_VERSION!r}"
        )
    if cfg.get("paper_engine_version") != PAPER_ENGINE_VERSION:
        failures.append(
            f"paper_engine_version mismatch: stored={cfg.get('paper_engine_version')!r}, "
            f"expected={PAPER_ENGINE_VERSION!r}"
        )
    if cfg.get("baseline_label") != BASELINE_LABEL:
        failures.append(
            f"baseline_label mismatch: stored={cfg.get('baseline_label')!r}, "
            f"expected={BASELINE_LABEL!r}"
        )

    try:
        recomputed = config_hash_from_row(row)
    except Exception as exc:  # noqa: BLE001 - report, do not crash
        recomputed = None
        failures.append(f"config_hash recomputation failed: {type(exc).__name__}: {exc}")
    if recomputed is not None and cfg.get("config_hash") != recomputed:
        failures.append(
            f"config_hash mismatch: stored={cfg.get('config_hash')!r}, "
            f"recomputed={recomputed!r}"
        )

    return cfg, failures


# ---------------------------------------------------------------------------
# Event-chain validation
# ---------------------------------------------------------------------------

def _validate_event_chain(conn: sqlite3.Connection) -> list[str]:
    failures: list[str] = []
    events = _rows(
        conn,
        "SELECT seq, batch_id, event_type, event_key, bar_ts, prev_seq "
        "FROM ledger_events ORDER BY seq",
    )
    if not events:
        return failures

    # Deterministic chain via prev_seq. seq gaps are NOT corruption — the chain is.
    prev: int | None = None
    seen_seq: set[int] = set()
    for i, ev in enumerate(events):
        seq = ev["seq"]
        if seq in seen_seq:
            failures.append(f"Duplicate event seq={seq}")
        seen_seq.add(seq)
        if i == 0:
            if ev["prev_seq"] is not None:
                failures.append(
                    f"First event seq={seq} has non-NULL prev_seq={ev['prev_seq']}"
                )
        else:
            if ev["prev_seq"] != prev:
                failures.append(
                    f"Event seq={seq} prev_seq={ev['prev_seq']} != immediately "
                    f"preceding seq {prev}"
                )
        prev = seq

    # Event type enum
    for ev in events:
        if ev["event_type"] not in _EVENT_TABLE:
            failures.append(
                f"Event seq={ev['seq']} has unknown event_type {ev['event_type']!r}"
            )

    # Unique event identity (event_type, event_key)
    identity_dupes = _rows(
        conn,
        "SELECT event_type, event_key, COUNT(*) AS cnt FROM ledger_events "
        "GROUP BY event_type, event_key HAVING cnt > 1",
    )
    for d in identity_dupes:
        failures.append(
            f"Duplicate event identity ({d['event_type']}, {d['event_key']}) x{d['cnt']}"
        )

    # 1:1 event <-> typed row.
    for et, table in _EVENT_TABLE.items():
        event_count = _scalar(
            conn,
            "SELECT COUNT(*) FROM ledger_events WHERE event_type = ?",
            (et,),
        )
        typed_count = _scalar(conn, f"SELECT COUNT(*) FROM {table}")
        if event_count != typed_count:
            failures.append(
                f"Event/typed count mismatch for {et}: events={event_count}, "
                f"typed={typed_count}"
            )
        # event without typed row
        orphan_events = _scalar(
            conn,
            f"""
            SELECT COUNT(*) FROM ledger_events e
            WHERE e.event_type = ?
              AND e.seq NOT IN (SELECT seq FROM {table})
            """,
            (et,),
        )
        if orphan_events:
            failures.append(f"{orphan_events} {et} event(s) without a {table} row")
        # typed row without matching event of this type
        orphan_typed = _scalar(
            conn,
            f"""
            SELECT COUNT(*) FROM {table} t
            WHERE t.seq NOT IN (
                SELECT seq FROM ledger_events WHERE event_type = ?
            )
            """,
            (et,),
        )
        if orphan_typed:
            failures.append(f"{orphan_typed} {table} row(s) without a matching {et} event")

    return failures


def _validate_batches(conn: sqlite3.Connection) -> list[str]:
    failures: list[str] = []
    batches = _rows(conn, "SELECT * FROM ledger_batches ORDER BY batch_id")
    for b in batches:
        bid = b["batch_id"]
        actual_count = _scalar(
            conn, "SELECT COUNT(*) FROM ledger_events WHERE batch_id = ?", (bid,)
        )
        if b["event_count"] != actual_count:
            failures.append(
                f"Batch {bid} event_count={b['event_count']} != actual "
                f"events {actual_count}"
            )
        # first/last event seq consistency (only for committed batches with events)
        if actual_count and b["committed_at"] is not None:
            seqs = _rows(
                conn,
                "SELECT MIN(seq) AS lo, MAX(seq) AS hi FROM ledger_events "
                "WHERE batch_id = ?",
                (bid,),
            )[0]
            if b["first_event_seq"] != seqs["lo"]:
                failures.append(
                    f"Batch {bid} first_event_seq={b['first_event_seq']} != "
                    f"min seq {seqs['lo']}"
                )
            if b["last_event_seq"] != seqs["hi"]:
                failures.append(
                    f"Batch {bid} last_event_seq={b['last_event_seq']} != "
                    f"max seq {seqs['hi']}"
                )
            # committed_bar_count == distinct equity bars in batch
            eq_bars = _scalar(
                conn,
                "SELECT COUNT(*) FROM equity_snapshots WHERE batch_id = ?",
                (bid,),
            )
            if b["committed_bar_count"] != eq_bars:
                failures.append(
                    f"Batch {bid} committed_bar_count={b['committed_bar_count']} != "
                    f"equity rows {eq_bars}"
                )
        # engine version / config hash consistency with paper_config
        cfg = conn.execute(
            "SELECT paper_engine_version, config_hash FROM paper_config WHERE id = 1"
        ).fetchone()
        if cfg is not None:
            if b["paper_engine_version"] != cfg["paper_engine_version"]:
                failures.append(
                    f"Batch {bid} paper_engine_version {b['paper_engine_version']!r} != "
                    f"config {cfg['paper_engine_version']!r}"
                )
            if b["config_hash"] != cfg["config_hash"]:
                failures.append(
                    f"Batch {bid} config_hash {b['config_hash']!r} != "
                    f"config {cfg['config_hash']!r}"
                )
    return failures


# ---------------------------------------------------------------------------
# Accounting-invariant validation
# ---------------------------------------------------------------------------

def _validate_arithmetic(
    conn: sqlite3.Connection, cfg: dict
) -> list[str]:
    failures: list[str] = []
    fee_bps = float(cfg["fee_bps"])
    fee_rate = fee_bps / 10_000.0
    forward_start = cfg["forward_start_ts"]
    initial_equity = float(cfg["initial_equity_usd"])
    notional = float(cfg["notional_usd"])

    # --- fills: no fill before forward_start_ts; fee arithmetic; fixed-notional baseline
    # The forward-start floor is enforced on the signal bar (the bar that produced
    # the order); the T+1 fill timestamp is derived from the next available bar and
    # is intentionally not floored here (it can precede the signal bar in out-of-
    # order/synthetic data) — this matches the Phase 2 writer reconcile check.
    fills = _rows(conn, "SELECT * FROM fills")
    for f in fills:
        if f["signal_bar_ts"] < forward_start:
            failures.append(
                f"Fill {f['fill_id']} signal_bar_ts {f['signal_bar_ts']} "
                f"< forward_start_ts {forward_start}"
            )
        expected_fee = f["fill_price"] * f["qty"] * fee_rate
        if not _close(f["fee"], expected_fee):
            failures.append(
                f"Fill {f['fill_id']} fee {f['fee']:.8f} != expected "
                f"{expected_fee:.8f}"
            )
        # fixed-notional baseline: no shorts (entry=BUY/exit=SELL), positive qty
        if f["qty"] <= 0:
            failures.append(f"Fill {f['fill_id']} non-positive qty {f['qty']}")
        if f["kind"] == "entry" and f["side"] != "BUY":
            failures.append(
                f"Fill {f['fill_id']} entry side {f['side']} != BUY (short detected)"
            )
        if f["kind"] == "exit" and f["side"] != "SELL":
            failures.append(
                f"Fill {f['fill_id']} exit side {f['side']} != SELL (short detected)"
            )
        # fixed-notional, no compounding: entry notional == config notional
        if f["kind"] == "entry":
            entry_notional = f["fill_price"] * f["qty"]
            if not _close(entry_notional, notional, tol=1e-4):
                failures.append(
                    f"Fill {f['fill_id']} entry notional {entry_notional:.6f} != "
                    f"fixed notional {notional:.6f} (compounding/sizing drift)"
                )

    # --- trades: gross/net arithmetic
    trades = _rows(conn, "SELECT * FROM trades")
    for t in trades:
        expected_net = t["gross_pnl"] - t["fees"] - t["funding"]
        if not _close(t["net_pnl"], expected_net):
            failures.append(
                f"Trade {t['trade_id']} net_pnl {t['net_pnl']:.8f} != gross-fees-funding "
                f"{expected_net:.8f}"
            )

    # --- funding: amount arithmetic (when rate available)
    funding_rows = _rows(conn, "SELECT * FROM funding")
    for fr in funding_rows:
        if fr["rate_available"]:
            expected_amount = fr["notional_usd"] * fr["funding_rate"]
            if not _close(fr["funding_amount"], expected_amount):
                failures.append(
                    f"Funding {fr['funding_id']} amount {fr['funding_amount']:.8f} != "
                    f"notional*rate {expected_amount:.8f}"
                )
        else:
            if not _close(fr["funding_amount"], 0.0):
                failures.append(
                    f"Funding {fr['funding_id']} amount {fr['funding_amount']:.8f} != 0 "
                    f"with rate_available=0"
                )

    # --- equity balance + drawdown per row (ordered by seq)
    eq = _rows(
        conn,
        "SELECT * FROM equity_snapshots ORDER BY seq",
    )
    peak = initial_equity
    for e in eq:
        expected_equity = (
            initial_equity
            + e["realized_gross_pnl"]
            - e["fees_cum"]
            - e["funding_cum"]
            + e["unrealized_pnl"]
        )
        if not _close(e["equity"], expected_equity):
            failures.append(
                f"Equity@{e['bar_ts']} {e['equity']:.8f} != initial+realized-fees-"
                f"funding+unrealized {expected_equity:.8f}"
            )
        if e["equity"] > peak:
            peak = e["equity"]
        expected_dd = (peak - e["equity"]) / peak if peak > 0 else 0.0
        if not _close(e["drawdown"], expected_dd):
            failures.append(
                f"Drawdown@{e['bar_ts']} {e['drawdown']:.8f} != expected "
                f"{expected_dd:.8f}"
            )

    return failures


def _validate_state(conn: sqlite3.Connection, cfg: dict) -> list[str]:
    failures: list[str] = []
    state = conn.execute("SELECT * FROM ledger_state WHERE id = 1").fetchone()
    if state is None:
        return ["ledger_state row (id=1) not found"]
    state = dict(state)

    eq = _rows(conn, "SELECT * FROM equity_snapshots ORDER BY seq")
    if not eq:
        return failures

    initial_equity = float(cfg["initial_equity_usd"])

    # watermark equals the latest committed equity bar
    latest_bar = max(e["bar_ts"] for e in eq)
    if state["watermark_bar_ts"] != latest_bar:
        failures.append(
            f"ledger_state.watermark_bar_ts {state['watermark_bar_ts']!r} != latest "
            f"committed equity bar {latest_bar!r}"
        )

    # Accumulators are POST-everything (the engine applies a bar's fills after its
    # pre-fill equity snapshot), so they reconcile against the full ledger-table
    # sums, not the final (pre-fill) equity snapshot.
    total_fees = _scalar(conn, "SELECT COALESCE(SUM(fee), 0.0) FROM fills")
    total_realized = _scalar(conn, "SELECT COALESCE(SUM(gross_pnl), 0.0) FROM trades")
    total_funding = _scalar(
        conn, "SELECT COALESCE(SUM(funding_amount), 0.0) FROM funding"
    )
    if not _close(state["realized_gross"], total_realized):
        failures.append(
            f"ledger_state.realized_gross {state['realized_gross']:.8f} != "
            f"SUM(trades.gross_pnl) {total_realized:.8f}"
        )
    if not _close(state["fees_cum"], total_fees):
        failures.append(
            f"ledger_state.fees_cum {state['fees_cum']:.8f} != "
            f"SUM(fills.fee) {total_fees:.8f}"
        )
    if not _close(state["funding_cum"], total_funding):
        failures.append(
            f"ledger_state.funding_cum {state['funding_cum']:.8f} != "
            f"SUM(funding.funding_amount) {total_funding:.8f}"
        )

    # peak equity matches running max over equity snapshots (and initial)
    peak = initial_equity
    for e in eq:
        if e["equity"] > peak:
            peak = e["equity"]
    if not _close(state["peak_equity"], peak):
        failures.append(
            f"ledger_state.peak_equity {state['peak_equity']:.8f} != reconstructed "
            f"peak {peak:.8f}"
        )

    return failures


def _validate_open_positions(conn: sqlite3.Connection) -> list[str]:
    """Reconstruct the open book from fills and compare to the cache.

    Validates the fields the Phase 2 writer maintains authoritatively in
    ``open_positions``: qty, entry_price, entry_fill_id, entry_bar_ts,
    entry_fill_ts. ``funding_accrued`` and ``hold_bars`` are NOT reconstructed
    here: the Phase 2 writer rebuilds ``open_positions`` from an entry/exit
    replay that does not carry the engine's per-bar funding accrual / hold-bar
    increments (it persists 0 for both), so reconstructing them would flag valid
    writer output as drift. See VERIFIER_DISCLAIMER and ADR Phase 4 follow-up.
    """
    failures: list[str] = []

    # Reconstruct open book by replaying fills in seq order.
    fills = _rows(
        conn,
        "SELECT * FROM fills ORDER BY seq",
    )
    book: dict[str, dict] = {}
    for f in fills:
        sym = f["symbol"]
        if f["kind"] == "entry":
            book[sym] = {
                "qty": f["qty"],
                "entry_price": f["fill_price"],
                "entry_fill_id": f["fill_id"],
                "entry_bar_ts": f["signal_bar_ts"],
                "entry_fill_ts": f["fill_ts"],
            }
        elif f["kind"] == "exit":
            book.pop(sym, None)

    db_positions = {
        r["symbol"]: r for r in _rows(conn, "SELECT * FROM open_positions")
    }

    # symbols present in one but not the other
    for sym in db_positions.keys() - book.keys():
        failures.append(f"open_positions has {sym} not in reconstructed open book")
    for sym in book.keys() - db_positions.keys():
        failures.append(f"Reconstructed open book has {sym} missing from open_positions")

    for sym in db_positions.keys() & book.keys():
        dbp = db_positions[sym]
        recon = book[sym]
        if not _close(dbp["qty"], recon["qty"], tol=_TIGHT_TOL):
            failures.append(f"open_positions {sym} qty {dbp['qty']} != {recon['qty']}")
        if not _close(dbp["entry_price"], recon["entry_price"], tol=_TIGHT_TOL):
            failures.append(
                f"open_positions {sym} entry_price {dbp['entry_price']} != "
                f"{recon['entry_price']}"
            )
        if dbp["entry_fill_id"] != recon["entry_fill_id"]:
            failures.append(
                f"open_positions {sym} entry_fill_id {dbp['entry_fill_id']!r} != "
                f"{recon['entry_fill_id']!r}"
            )
        if dbp["entry_bar_ts"] != recon["entry_bar_ts"]:
            failures.append(
                f"open_positions {sym} entry_bar_ts {dbp['entry_bar_ts']!r} != "
                f"{recon['entry_bar_ts']!r}"
            )
        if dbp["entry_fill_ts"] != recon["entry_fill_ts"]:
            failures.append(
                f"open_positions {sym} entry_fill_ts {dbp['entry_fill_ts']!r} != "
                f"{recon['entry_fill_ts']!r}"
            )

    return failures


def _validate_snapshot_identity(conn: sqlite3.Connection) -> list[str]:
    """Validate bar_commit_id agreement across all rows for a bar + digest form.

    NOTE: the full canonical source observation JSON is NOT persisted by the
    Phase 2 writer (only the consumed subset), so the verifier cannot
    independently recompute ``source_observation_digest`` from source data. It
    validates well-formedness and cross-row commit-id agreement instead. See
    VERIFIER_DISCLAIMER.
    """
    failures: list[str] = []

    snaps = _rows(
        conn,
        "SELECT bar_ts, snapshot_id, bar_commit_id, source_observation_digest "
        "FROM signal_snapshots",
    )
    commit_by_bar: dict[str, str] = {}
    for s in snaps:
        commit_by_bar[s["bar_ts"]] = s["bar_commit_id"]
        # writer v1 invariant: snapshot_id == bar_commit_id
        if s["snapshot_id"] != s["bar_commit_id"]:
            failures.append(
                f"signal_snapshot@{s['bar_ts']} snapshot_id {s['snapshot_id']!r} != "
                f"bar_commit_id {s['bar_commit_id']!r}"
            )
        if not _HEX16.match(s["bar_commit_id"] or ""):
            failures.append(
                f"signal_snapshot@{s['bar_ts']} bar_commit_id {s['bar_commit_id']!r} "
                f"is not a 16-char hex digest"
            )
        if not _HEX64.match(s["source_observation_digest"] or ""):
            failures.append(
                f"signal_snapshot@{s['bar_ts']} source_observation_digest "
                f"{s['source_observation_digest']!r} is not a 64-char hex digest"
            )

    # Cross-row bar_commit_id agreement: every typed row for a bar must carry the
    # same bar_commit_id as that bar's signal snapshot.
    checks = [
        ("funding", "bar_ts"),
        ("fills", "signal_bar_ts"),
        ("trades", "exit_bar_ts"),
        ("position_snapshots", "bar_ts"),
        ("equity_snapshots", "bar_ts"),
    ]
    for table, bar_col in checks:
        for r in _rows(conn, f"SELECT {bar_col} AS bar, bar_commit_id FROM {table}"):
            expected = commit_by_bar.get(r["bar"])
            if expected is None:
                failures.append(
                    f"{table} row at bar {r['bar']!r} has no matching signal snapshot"
                )
            elif r["bar_commit_id"] != expected:
                failures.append(
                    f"{table} row at bar {r['bar']!r} bar_commit_id "
                    f"{r['bar_commit_id']!r} != signal snapshot {expected!r}"
                )

    return failures


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def verify_database(db_path: str | Path | None = None) -> VerifyResult:
    """Verify a committed paper ledger DB read-only. Never writes anything."""
    db_path = get_paper_db_path(db_path)
    report: dict[str, Any] = {
        "db_path": str(db_path),
        "disclaimer": VERIFIER_DISCLAIMER,
    }

    if not Path(db_path).exists():
        report["error"] = "database file does not exist"
        return VerifyResult(STATUS_CONFIG_ERROR, [f"DB not found: {db_path}"], report)

    try:
        conn = connect_readonly(db_path)
    except Exception as exc:  # noqa: BLE001
        return VerifyResult(
            STATUS_CONFIG_ERROR,
            [f"Could not open DB read-only: {type(exc).__name__}: {exc}"],
            report,
        )

    try:
        # Confirm query-only mode is active (defends against accidental writes).
        query_only = _scalar(conn, "PRAGMA query_only")
        report["query_only"] = int(query_only) if query_only is not None else None
        if not query_only:
            return VerifyResult(
                STATUS_CONFIG_ERROR,
                ["PRAGMA query_only is not ON on the verifier connection"],
                report,
            )

        # Structural presence (tables/triggers/indexes).
        structural = _validate_schema_presence(conn)
        if structural:
            return VerifyResult(STATUS_CORRUPT, structural, report)

        # Identity / config.
        cfg, identity_failures = _validate_identity(conn)
        if identity_failures:
            return VerifyResult(STATUS_CONFIG_ERROR, identity_failures, report)
        assert cfg is not None

        # PRE_START: valid DB, nothing committed yet.
        n_batches = _scalar(conn, "SELECT COUNT(*) FROM ledger_batches")
        n_events = _scalar(conn, "SELECT COUNT(*) FROM ledger_events")
        n_equity = _scalar(conn, "SELECT COUNT(*) FROM equity_snapshots")
        watermark = _scalar(
            conn, "SELECT watermark_bar_ts FROM ledger_state WHERE id = 1"
        )
        report["batches"] = n_batches
        report["events"] = n_events
        report["equity_rows"] = n_equity
        report["watermark_bar_ts"] = watermark
        if not n_batches and not n_events and not n_equity and watermark is None:
            return VerifyResult(STATUS_PRE_START, [], report)

        # Full validation.
        failures: list[str] = []
        failures += _validate_event_chain(conn)
        failures += _validate_batches(conn)
        failures += _validate_arithmetic(conn, cfg)
        failures += _validate_state(conn, cfg)
        failures += _validate_open_positions(conn)
        failures += _validate_snapshot_identity(conn)

        report["forward_start_ts"] = cfg["forward_start_ts"]
        report["failure_count"] = len(failures)
        if failures:
            return VerifyResult(STATUS_CORRUPT, failures, report)
        return VerifyResult(STATUS_OK, [], report)
    finally:
        conn.close()


__all__ = [
    "STATUS_OK",
    "STATUS_CONFIG_ERROR",
    "STATUS_CORRUPT",
    "STATUS_PRE_START",
    "EXIT_CODE",
    "VERIFIER_DISCLAIMER",
    "VerifyResult",
    "verify_database",
]
