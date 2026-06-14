"""Read-only SQLite paper ledger verifier (Phase 3).

Opens ``paper_ledger.db`` read-only (URI ``mode=ro`` + ``PRAGMA query_only=ON``)
and validates the committed DB state from the typed tables. The verifier never
writes the DB and never touches VM / live output.

Two entry points:

  - :func:`verify_database` — the pure read-only check. Returns a ``VerifyResult``
    and writes NOTHING.
  - :func:`verify_and_publish` — the authoritative publisher. Pins one read-only
    SQLite snapshot for validation + digesting, then writes its OWN artifacts
    (``paper_verify_report.json`` + ``paper_verify_receipt.md`` +
    ``paper_verify_log.jsonl``) atomically next to the DB. This is the only
    component allowed to publish an authoritative paper status.

Authority model (ADR 0001): the committed DB and the accounting writer's returned
status code are RAW accounting artifacts / a runner status only. The single
authoritative paper status is the latest ``paper_verify_report.json`` for its exact
recorded SQLite snapshot digest; a paper run is trusted IFF that report's
``status == OK``. If the DB is mutated after an OK, the next verification recomputes
the consistency invariants + content digests from the then-current DB and fails
closed -> CORRUPT.

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

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quantbot.paper import (
    BASELINE_LABEL,
    PAPER_ENGINE_VERSION,
    SCHEMA_VERSION,
)
from quantbot.paper import ledger
from quantbot.paper.freshness import parse_bar_utc
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

# Authoritative-publication layer (ADR 0001 authority model). The committed DB and the
# writer's returned status code are RAW accounting artifacts / a runner status only. The
# single authoritative paper status is the latest paper_verify_report.json, written ONLY by
# this read-only verifier. The verifier reads the DB read-only and writes only its own
# paper_verify_* artifacts next to the DB (never the DB, never any runner artifact).
SQLITE_VERIFIER_VERSION = "1.0.0"
REPORT_FILE = "paper_verify_report.json"   # authoritative latest terminal report
RECEIPT_FILE = "paper_verify_receipt.md"   # human receipt for the latest verdict
LOG_FILE = "paper_verify_log.jsonl"        # append-only audit trail (NON-gating)

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
        # A committed batch must carry at least one event: an empty committed
        # batch is corruption, not a healthy no-op (the writer rolls back when
        # there is nothing to commit).
        if b["committed_at"] is not None and actual_count == 0:
            failures.append(f"Batch {bid} committed with zero events")
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
    notional = float(cfg["notional_usd"])

    # --- fills: no fill before forward_start_ts; fee arithmetic; fixed-notional baseline
    # The forward-start floor is enforced on the signal bar (the bar that produced
    # the order); the T+1 fill timestamp is derived from the next available bar and
    # is intentionally not floored here (it can precede the signal bar in out-of-
    # order/synthetic data) — this matches the Phase 2 writer reconcile check.
    fills = _rows(conn, "SELECT * FROM fills")
    # Parse the boundary once; compare instants, not raw strings. A boundary fill stores a
    # naive signal_bar_ts ('...T00:00:00') while forward_start_ts carries a trailing Z, so a
    # lexicographic compare would wrongly flag a fill AT forward_start_ts as before it.
    forward_start_dt = parse_bar_utc(forward_start)
    for f in fills:
        try:
            before_boundary = parse_bar_utc(f["signal_bar_ts"]) < forward_start_dt
        except (TypeError, ValueError):
            before_boundary = True  # unparseable signal_bar_ts -> fail closed
        if before_boundary:
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

    # NOTE: trade lifecycle arithmetic lives in _validate_trades (it derives
    # gross/fees/funding from the underlying fills + funding ledger, not from the
    # trade row's own self-consistent fields). Equity cumulative reconciliation
    # lives in _validate_equity_cumulative (it recomputes realized/fees/funding
    # from history rather than trusting the equity row's own fields).

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

    return failures


def _validate_trades(conn: sqlite3.Connection) -> list[str]:
    """Verify the full trade lifecycle from the underlying fills + funding ledger.

    A trade row is NOT trusted on its own fields: every component is re-derived
    from the entry/exit fills it references and from the funding ledger for the
    held interval. Fabricated trades (fake fill ids, arbitrary gross/funding)
    therefore fail even when the trade row is internally self-consistent.
    """
    failures: list[str] = []
    fills_by_id = {f["fill_id"]: f for f in _rows(conn, "SELECT * FROM fills")}
    trades = _rows(conn, "SELECT * FROM trades")

    for t in trades:
        tid = t["trade_id"]
        entry = fills_by_id.get(t["entry_fill_id"])
        exit_ = fills_by_id.get(t["exit_fill_id"])

        if entry is None:
            failures.append(
                f"Trade {tid} entry_fill_id {t['entry_fill_id']!r} not found in fills"
            )
        if exit_ is None:
            failures.append(
                f"Trade {tid} exit_fill_id {t['exit_fill_id']!r} not found in fills"
            )

        if entry is not None:
            if entry["kind"] != "entry" or entry["side"] != "BUY":
                failures.append(
                    f"Trade {tid} entry fill {entry['fill_id']} is not (entry, BUY): "
                    f"kind={entry['kind']!r}, side={entry['side']!r}"
                )
            if entry["symbol"] != t["symbol"]:
                failures.append(
                    f"Trade {tid} entry fill symbol {entry['symbol']!r} != trade "
                    f"symbol {t['symbol']!r}"
                )
            if not _close(t["qty"], entry["qty"], tol=_TIGHT_TOL):
                failures.append(
                    f"Trade {tid} qty {t['qty']} != entry fill qty {entry['qty']}"
                )
        if exit_ is not None:
            if exit_["kind"] != "exit" or exit_["side"] != "SELL":
                failures.append(
                    f"Trade {tid} exit fill {exit_['fill_id']} is not (exit, SELL): "
                    f"kind={exit_['kind']!r}, side={exit_['side']!r}"
                )
            if exit_["symbol"] != t["symbol"]:
                failures.append(
                    f"Trade {tid} exit fill symbol {exit_['symbol']!r} != trade "
                    f"symbol {t['symbol']!r}"
                )
            if not _close(t["qty"], exit_["qty"], tol=_TIGHT_TOL):
                failures.append(
                    f"Trade {tid} qty {t['qty']} != exit fill qty {exit_['qty']}"
                )

        if entry is not None and exit_ is not None:
            # gross_pnl derived from fill prices (long-only baseline).
            expected_gross = (exit_["fill_price"] - entry["fill_price"]) * t["qty"]
            if not _close(t["gross_pnl"], expected_gross):
                failures.append(
                    f"Trade {tid} gross_pnl {t['gross_pnl']:.8f} != "
                    f"(exit_price-entry_price)*qty {expected_gross:.8f}"
                )
            # fees = entry fee + exit fee.
            expected_fees = entry["fee"] + exit_["fee"]
            if not _close(t["fees"], expected_fees):
                failures.append(
                    f"Trade {tid} fees {t['fees']:.8f} != entry_fee+exit_fee "
                    f"{expected_fees:.8f}"
                )

        # funding = aggregation of the funding ledger over the held interval
        # (entry_bar_ts, exit_bar_ts] for this symbol (v1 semantics: a single
        # position per symbol, so the windows of sequential trades are disjoint).
        agg = _scalar(
            conn,
            """
            SELECT COALESCE(SUM(funding_amount), 0.0) FROM funding
            WHERE symbol = ? AND bar_ts > ? AND bar_ts <= ?
            """,
            (t["symbol"], t["entry_bar_ts"], t["exit_bar_ts"]),
        )
        if not _close(t["funding"], agg):
            failures.append(
                f"Trade {tid} funding {t['funding']:.8f} != funding-ledger "
                f"aggregation over ({t['entry_bar_ts']}, {t['exit_bar_ts']}] "
                f"{agg:.8f}"
            )

        # net = gross - fees - funding (using the trade's own components).
        expected_net = t["gross_pnl"] - t["fees"] - t["funding"]
        if not _close(t["net_pnl"], expected_net):
            failures.append(
                f"Trade {tid} net_pnl {t['net_pnl']:.8f} != gross-fees-funding "
                f"{expected_net:.8f}"
            )

    return failures


def _validate_equity_cumulative(conn: sqlite3.Connection, cfg: dict) -> list[str]:
    """Reconcile each equity row's cumulative fields against ledger history.

    The equity row's realized_gross_pnl / fees_cum / funding_cum are NOT trusted:
    they are recomputed from the trade / fill / funding ledgers up to each bar, so
    a coordinated mutation of realized PnL + equity + peak cannot pass. The
    unrealized mark is taken from the row as-is (the verifier does not rederive
    OHLCV marks — see VERIFIER_DISCLAIMER), but every other input is rederived.

    Cumulative semantics match the engine's per-bar ordering: the equity snapshot
    for bar B is taken PRE-fill, so it reflects fills/realized strictly before B,
    and funding accrued up to and including B.
    """
    failures: list[str] = []
    initial_equity = float(cfg["initial_equity_usd"])
    eq = _rows(conn, "SELECT * FROM equity_snapshots ORDER BY bar_ts")
    peak = initial_equity
    for e in eq:
        bar = e["bar_ts"]
        realized = _scalar(
            conn,
            "SELECT COALESCE(SUM(gross_pnl), 0.0) FROM trades WHERE exit_bar_ts < ?",
            (bar,),
        )
        fees_cum = _scalar(
            conn,
            "SELECT COALESCE(SUM(fee), 0.0) FROM fills WHERE signal_bar_ts < ?",
            (bar,),
        )
        funding_cum = _scalar(
            conn,
            "SELECT COALESCE(SUM(funding_amount), 0.0) FROM funding WHERE bar_ts <= ?",
            (bar,),
        )
        if not _close(e["realized_gross_pnl"], realized):
            failures.append(
                f"Equity@{bar} realized_gross_pnl {e['realized_gross_pnl']:.8f} != "
                f"SUM(trades.gross_pnl WHERE exit_bar_ts<{bar}) {realized:.8f}"
            )
        if not _close(e["fees_cum"], fees_cum):
            failures.append(
                f"Equity@{bar} fees_cum {e['fees_cum']:.8f} != "
                f"SUM(fills.fee WHERE signal_bar_ts<{bar}) {fees_cum:.8f}"
            )
        if not _close(e["funding_cum"], funding_cum):
            failures.append(
                f"Equity@{bar} funding_cum {e['funding_cum']:.8f} != "
                f"SUM(funding WHERE bar_ts<={bar}) {funding_cum:.8f}"
            )
        expected_equity = (
            initial_equity + realized - fees_cum - funding_cum + e["unrealized_pnl"]
        )
        if not _close(e["equity"], expected_equity):
            failures.append(
                f"Equity@{bar} {e['equity']:.8f} != initial+realized-fees-funding+"
                f"unrealized {expected_equity:.8f} (recomputed from history)"
            )
        if expected_equity > peak:
            peak = expected_equity
        expected_dd = (peak - expected_equity) / peak if peak > 0 else 0.0
        if not _close(e["drawdown"], expected_dd):
            failures.append(
                f"Drawdown@{bar} {e['drawdown']:.8f} != expected {expected_dd:.8f}"
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
    """Reconstruct the open book from the ledger and compare to the cache.

    Every field the engine needs to resume a position across runs is rederived
    and checked: qty, entry_price, entry_fill_id, entry_bar_ts, entry_fill_ts,
    entry_fee, funding_accrued and hold_bars. The reconstruction is taken from
    the fill book, the funding ledger and the equity bar count — NOT from the
    open_positions row — so a tampered restart cache is caught.
    """
    failures: list[str] = []

    # Reconstruct open book by replaying fills in (signal-bar, seq) order.
    fills = _rows(conn, "SELECT * FROM fills ORDER BY signal_bar_ts, seq")
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
                "entry_fee": f["fee"],
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
        # entry_fee rebuilt from the entry fill the engine resumes against.
        if not _close(dbp["entry_fee"], recon["entry_fee"], tol=_TIGHT_TOL):
            failures.append(
                f"open_positions {sym} entry_fee {dbp['entry_fee']} != entry fill fee "
                f"{recon['entry_fee']}"
            )
        # hold_bars = number of committed equity bars after the entry signal bar
        # (the engine increments hold_bars on every PRE-fill snapshot the position
        # is in the book, i.e. bars strictly after entry_bar_ts).
        recon_hold = _scalar(
            conn,
            "SELECT COUNT(*) FROM equity_snapshots WHERE bar_ts > ?",
            (recon["entry_bar_ts"],),
        )
        if dbp["hold_bars"] != recon_hold:
            failures.append(
                f"open_positions {sym} hold_bars {dbp['hold_bars']} != equity bars "
                f"after entry {recon_hold}"
            )
        # funding_accrued = funding ledger for this symbol since the entry bar
        # (no exit-tail yet — the position is still open).
        recon_funding = _scalar(
            conn,
            "SELECT COALESCE(SUM(funding_amount), 0.0) FROM funding "
            "WHERE symbol = ? AND bar_ts > ?",
            (sym, recon["entry_bar_ts"]),
        )
        if not _close(dbp["funding_accrued"], recon_funding):
            failures.append(
                f"open_positions {sym} funding_accrued {dbp['funding_accrued']:.8f} != "
                f"funding ledger since entry {recon_funding:.8f}"
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
# Durable event <-> typed-row relationship validation
# ---------------------------------------------------------------------------

# event_type -> (typed table, natural-key column or None, bar column, symbol column)
_TYPED_KEY: dict[str, tuple[str, str | None, str, str | None]] = {
    "signal_snapshot": ("signal_snapshots", "snapshot_id", "bar_ts", None),
    "funding": ("funding", "funding_id", "bar_ts", "symbol"),
    "fill": ("fills", "fill_id", "signal_bar_ts", "symbol"),
    "trade": ("trades", "trade_id", "exit_bar_ts", "symbol"),
    "position_snapshot": ("position_snapshots", None, "bar_ts", None),
    "equity_snapshot": ("equity_snapshots", None, "bar_ts", None),
}


def _validate_event_typed_consistency(conn: sqlite3.Connection) -> list[str]:
    """Validate that each event's key/batch/bar/symbol match its typed row.

    Beyond seq/type presence (already covered by the event-chain check) this
    confirms the event_key equals the typed row's natural key, that the event's
    batch_id / bar_ts / symbol agree with the typed row, so an event cannot be
    silently re-pointed at a different row of the same type.
    """
    failures: list[str] = []
    for et, (table, keycol, barcol, symcol) in _TYPED_KEY.items():
        rows = _rows(
            conn,
            f"""
            SELECT e.seq AS eseq, e.event_key AS ekey, e.bar_ts AS ebar,
                   e.symbol AS esym, e.batch_id AS ebatch, t.*
            FROM ledger_events e
            JOIN {table} t ON t.seq = e.seq
            WHERE e.event_type = ?
            """,
            (et,),
        )
        for r in rows:
            seq = r["eseq"]
            if keycol is not None:
                natural = r[keycol]
            else:
                prefix = "pos" if et == "position_snapshot" else "eq"
                natural = f"{prefix}|{r['bar_ts']}"
            if r["ekey"] != natural:
                failures.append(
                    f"{et} event seq={seq} event_key {r['ekey']!r} != natural key "
                    f"{natural!r}"
                )
            if r["ebatch"] != r["batch_id"]:
                failures.append(
                    f"{et} event seq={seq} batch_id {r['ebatch']} != typed row "
                    f"batch_id {r['batch_id']}"
                )
            if r["ebar"] != r[barcol]:
                failures.append(
                    f"{et} event seq={seq} bar_ts {r['ebar']!r} != typed row "
                    f"{barcol} {r[barcol]!r}"
                )
            if symcol is not None:
                if r["esym"] != r[symcol]:
                    failures.append(
                        f"{et} event seq={seq} symbol {r['esym']!r} != typed row "
                        f"symbol {r[symcol]!r}"
                    )
            else:
                if r["esym"] is not None:
                    failures.append(
                        f"{et} event seq={seq} symbol {r['esym']!r} should be NULL"
                    )
    return failures


def _validate_position_snapshots(conn: sqlite3.Connection) -> list[str]:
    """Validate each position_snapshot against its child symbol rows + the book.

    For every position_snapshot: ``num_open`` equals both the open_symbols JSON
    length and the child-row count; the child symbols equal the open_symbols
    JSON; and each child row's (qty, entry_price, entry_fill_id, entry_bar_ts)
    matches the pre-fill open book reconstructed from the fill ledger at that bar.

    The child ``unrealized_gross`` / position exposure are NOT re-derived (they
    depend on OHLCV marks the verifier does not rederive — see
    VERIFIER_DISCLAIMER); only the structural / fill-derived fields are checked.
    """
    failures: list[str] = []
    ps_rows = _rows(conn, "SELECT * FROM position_snapshots ORDER BY bar_ts")
    children: dict[int, list[dict]] = {}
    for c in _rows(conn, "SELECT * FROM position_snapshot_symbols"):
        children.setdefault(c["snapshot_seq"], []).append(c)

    fills_by_bar: dict[str, list[dict]] = {}
    for f in _rows(conn, "SELECT * FROM fills ORDER BY signal_bar_ts, seq"):
        fills_by_bar.setdefault(f["signal_bar_ts"], []).append(f)

    book: dict[str, dict] = {}
    for ps in ps_rows:
        bar = ps["bar_ts"]
        try:
            open_symbols = json.loads(ps["open_symbols"])
        except (ValueError, TypeError):
            failures.append(f"position_snapshot@{bar} open_symbols is not valid JSON")
            open_symbols = []
        child = children.get(ps["seq"], [])
        child_syms = sorted(c["symbol"] for c in child)

        if ps["num_open"] != len(open_symbols):
            failures.append(
                f"position_snapshot@{bar} num_open {ps['num_open']} != "
                f"len(open_symbols) {len(open_symbols)}"
            )
        if ps["num_open"] != len(child):
            failures.append(
                f"position_snapshot@{bar} num_open {ps['num_open']} != "
                f"position_snapshot_symbols count {len(child)}"
            )
        if child_syms != sorted(open_symbols):
            failures.append(
                f"position_snapshot@{bar} child symbols {child_syms} != "
                f"open_symbols {sorted(open_symbols)}"
            )
        # open_symbols must equal the reconstructed pre-fill book at this bar.
        if sorted(book.keys()) != sorted(open_symbols):
            failures.append(
                f"position_snapshot@{bar} open_symbols {sorted(open_symbols)} != "
                f"reconstructed open book {sorted(book.keys())}"
            )

        child_by_sym = {c["symbol"]: c for c in child}
        for sym, pos in book.items():
            c = child_by_sym.get(sym)
            if c is None:
                continue  # already flagged via child_syms mismatch
            if not _close(c["qty"], pos["qty"], tol=_TIGHT_TOL):
                failures.append(
                    f"position_snapshot@{bar} {sym} qty {c['qty']} != {pos['qty']}"
                )
            if not _close(c["entry_price"], pos["entry_price"], tol=_TIGHT_TOL):
                failures.append(
                    f"position_snapshot@{bar} {sym} entry_price {c['entry_price']} != "
                    f"{pos['entry_price']}"
                )
            if c["entry_fill_id"] != pos["entry_fill_id"]:
                failures.append(
                    f"position_snapshot@{bar} {sym} entry_fill_id "
                    f"{c['entry_fill_id']!r} != {pos['entry_fill_id']!r}"
                )
            if c["entry_bar_ts"] != pos["entry_bar_ts"]:
                failures.append(
                    f"position_snapshot@{bar} {sym} entry_bar_ts "
                    f"{c['entry_bar_ts']!r} != {pos['entry_bar_ts']!r}"
                )

        # Advance the book by this bar's fills (exits then entries, matching the
        # engine) so the NEXT bar's pre-fill snapshot reconstructs correctly.
        bar_fills = fills_by_bar.get(bar, [])
        for f in bar_fills:
            if f["kind"] == "exit":
                book.pop(f["symbol"], None)
        for f in bar_fills:
            if f["kind"] == "entry":
                book[f["symbol"]] = {
                    "qty": f["qty"],
                    "entry_price": f["fill_price"],
                    "entry_fill_id": f["fill_id"],
                    "entry_bar_ts": f["signal_bar_ts"],
                }

    return failures


def _validate_foreign_keys(conn: sqlite3.Connection) -> list[str]:
    """Run SQLite's own foreign-key integrity check over the whole DB."""
    failures: list[str] = []
    for row in conn.execute("PRAGMA foreign_key_check").fetchall():
        # columns: (table, rowid, parent, fkid)
        failures.append(
            f"Foreign key violation: table {row[0]!r} rowid {row[1]} -> "
            f"{row[2]!r} (fk #{row[3]})"
        )
    return failures


# ---------------------------------------------------------------------------
# PRE_START state validation
# ---------------------------------------------------------------------------

_LEDGER_TABLES = [
    "ledger_batches",
    "ledger_events",
    "signal_snapshots",
    "fills",
    "trades",
    "funding",
    "position_snapshots",
    "position_snapshot_symbols",
    "equity_snapshots",
    "open_positions",
]


def _ledger_table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {t: _scalar(conn, f"SELECT COUNT(*) FROM {t}") for t in _LEDGER_TABLES}


def _validate_initial_state(conn: sqlite3.Connection, cfg: dict) -> list[str]:
    """A PRE_START DB must hold a valid INITIAL ledger_state singleton.

    Corrupt pre-start state (non-NULL watermark, non-zero accumulators, wrong
    peak) must NOT be reported as PRE_START — it is CORRUPT.
    """
    failures: list[str] = []
    state = conn.execute("SELECT * FROM ledger_state WHERE id = 1").fetchone()
    if state is None:
        return ["ledger_state row (id=1) not found"]
    state = dict(state)
    initial_equity = float(cfg["initial_equity_usd"])
    if state["watermark_bar_ts"] is not None:
        failures.append(
            f"pre-start ledger_state.watermark_bar_ts {state['watermark_bar_ts']!r} "
            f"!= NULL"
        )
    for col in ("realized_gross", "fees_cum", "funding_cum"):
        if not _close(state[col], 0.0):
            failures.append(f"pre-start ledger_state.{col} {state[col]:.8f} != 0")
    if not _close(state["peak_equity"], initial_equity):
        failures.append(
            f"pre-start ledger_state.peak_equity {state['peak_equity']:.8f} != "
            f"initial_equity {initial_equity:.8f}"
        )
    return failures


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def _verify_connection(conn: sqlite3.Connection, db_path: Path) -> VerifyResult:
    """Verify the single read snapshot currently held by ``conn``."""
    report: dict[str, Any] = {
        "db_path": str(db_path),
        "disclaimer": VERIFIER_DISCLAIMER,
    }
    # Confirm query-only mode is active (defends against accidental writes).
    try:
        query_only = _scalar(conn, "PRAGMA query_only")
        report["query_only"] = int(query_only) if query_only is not None else None
        if not query_only:
            return VerifyResult(
                STATUS_CONFIG_ERROR,
                ["PRAGMA query_only is not ON on the verifier connection"],
                report,
            )

        structural = _validate_schema_presence(conn)
        if structural:
            return VerifyResult(STATUS_CORRUPT, structural, report)

        cfg, identity_failures = _validate_identity(conn)
        if identity_failures:
            return VerifyResult(STATUS_CONFIG_ERROR, identity_failures, report)
        assert cfg is not None
    except sqlite3.DatabaseError as exc:
        return VerifyResult(
            STATUS_CONFIG_ERROR,
            [f"DB is not readable as a paper ledger: {type(exc).__name__}: {exc}"],
            report,
        )

    try:
        counts = _ledger_table_counts(conn)
        report["batches"] = counts["ledger_batches"]
        report["events"] = counts["ledger_events"]
        report["equity_rows"] = counts["equity_snapshots"]
        report["watermark_bar_ts"] = _scalar(
            conn, "SELECT watermark_bar_ts FROM ledger_state WHERE id = 1"
        )

        if all(v == 0 for v in counts.values()):
            state_failures = _validate_initial_state(conn, cfg)
            if state_failures:
                report["failure_count"] = len(state_failures)
                return VerifyResult(STATUS_CORRUPT, state_failures, report)
            report["forward_start_ts"] = cfg["forward_start_ts"]
            report["failure_count"] = 0
            return VerifyResult(STATUS_PRE_START, [], report)

        failures: list[str] = []
        failures += _validate_foreign_keys(conn)
        failures += _validate_event_chain(conn)
        failures += _validate_event_typed_consistency(conn)
        failures += _validate_batches(conn)
        failures += _validate_arithmetic(conn, cfg)
        failures += _validate_trades(conn)
        failures += _validate_equity_cumulative(conn, cfg)
        failures += _validate_state(conn, cfg)
        failures += _validate_open_positions(conn)
        failures += _validate_position_snapshots(conn)
        failures += _validate_snapshot_identity(conn)
    except (sqlite3.DatabaseError, ValueError, TypeError) as exc:
        return VerifyResult(
            STATUS_CORRUPT,
            [f"Verification query failed: {type(exc).__name__}: {exc}"],
            report,
        )

    report["forward_start_ts"] = cfg["forward_start_ts"]
    report["failure_count"] = len(failures)
    if failures:
        return VerifyResult(STATUS_CORRUPT, failures, report)
    return VerifyResult(STATUS_OK, [], report)


def _open_snapshot(db_path: Path) -> sqlite3.Connection:
    """Open and pin one read-only SQLite snapshot for validation and digesting."""
    conn = connect_readonly(db_path)
    conn.execute("BEGIN")
    # The first read pins the WAL snapshot for all subsequent verifier queries.
    conn.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
    return conn


def verify_database(db_path: str | Path | None = None) -> VerifyResult:
    """Verify one committed paper-ledger snapshot read-only. Never writes anything."""
    db_path = get_paper_db_path(db_path)
    report = {"db_path": str(db_path), "disclaimer": VERIFIER_DISCLAIMER}
    if not Path(db_path).exists():
        report["error"] = "database file does not exist"
        return VerifyResult(STATUS_CONFIG_ERROR, [f"DB not found: {db_path}"], report)
    try:
        conn = _open_snapshot(Path(db_path))
    except sqlite3.Error as exc:
        return VerifyResult(
            STATUS_CONFIG_ERROR,
            [f"Could not open DB read-only: {type(exc).__name__}: {exc}"],
            report,
        )
    try:
        return _verify_connection(conn, Path(db_path))
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Authoritative publication (writes paper_verify_report.json / receipt / log)
# ---------------------------------------------------------------------------

def _now_utc_str(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _table_digest(conn: sqlite3.Connection, table: str) -> str:
    """Order-independent sha256 of every row in a committed table (read-only).

    Rows are canonicalized (sorted-key JSON) and then themselves sorted, so the digest is a
    stable fingerprint of the committed CONTENT regardless of physical rowid order. ``table``
    is always a hardcoded schema constant (never user input), so the f-string SQL is safe.
    """
    rows = [dict(r) for r in conn.execute(f"SELECT * FROM {table}").fetchall()]
    canon = sorted(json.dumps(r, sort_keys=True, default=str) for r in rows)
    h = hashlib.sha256()
    for line in canon:
        h.update(line.encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def _content_digests(conn: sqlite3.Connection) -> dict[str, str]:
    """Digest the same pinned read snapshot used for the verdict."""
    try:
        per_table: dict[str, str] = {}
        for table in _REQUIRED_TABLES:
            per_table[table] = _table_digest(conn, table)
    except sqlite3.DatabaseError:
        return {}
    combined = hashlib.sha256()
    for table in _REQUIRED_TABLES:
        combined.update(f"{table}:{per_table[table]}\n".encode("utf-8"))
    per_table["content_sha256"] = combined.hexdigest()
    return per_table


_VERDICT_LINE: dict[str, str] = {
    STATUS_OK: (
        "OK (simulation) — the committed SQLite paper ledger verified consistent read-only; "
        "this paper_verify_report.json is the authoritative paper status"
    ),
    STATUS_CORRUPT: "CORRUPT — integrity failure(s); the paper run is NOT trusted",
    STATUS_CONFIG_ERROR: (
        "CONFIG_ERROR — the DB/config identity is invalid/stale/unloadable; nothing can be "
        "verified against it"
    ),
    STATUS_PRE_START: (
        "PRE_START — a valid pre-start DB with no committed eligible bars yet; nothing to certify"
    ),
}


def _build_published_report(
    db_path: Path,
    result: VerifyResult,
    digests: dict[str, str],
    now: datetime | None,
) -> dict[str, Any]:
    """Wrap a VerifyResult in the authoritative report envelope (the on-disk report shape)."""
    status = result.status
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "verifier": "sqlite",
        "verifier_version": SQLITE_VERIFIER_VERSION,
        "authoritative": True,
        "verified_at": _now_utc_str(now),
        "db_path": str(db_path),
        "status": status,
        "exit_code": result.exit_code,
        # A paper run is trusted IFF this is true.
        "trusted": status == STATUS_OK,
        "failure_count": len(result.failures),
        "failures": list(result.failures),
        "content_digests": digests,
        "content_sha256": digests.get("content_sha256"),
        "snapshot_identity": {
            "content_sha256": digests.get("content_sha256"),
            "meaning": "authoritative verdict for this exact validated SQLite read snapshot",
        },
        "current_verdict": _VERDICT_LINE.get(status, status),
        "disclaimer": VERIFIER_DISCLAIMER,
    }
    # Carry forward the read-only metrics the core verifier collected (batches/events/equity/
    # watermark/forward_start_ts/config identity), without letting them shadow the envelope.
    for k, v in result.report.items():
        report.setdefault(k, v)
    return report


def _render_receipt(report: dict[str, Any]) -> str:
    status = report["status"]
    icon = {
        STATUS_OK: "✅",
        STATUS_CORRUPT: "🛑",
        STATUS_CONFIG_ERROR: "🛑",
        STATUS_PRE_START: "⏳",
    }.get(status, "❓")
    lines = [
        "# Paper PnL v1 — SQLite Verifier Receipt (AUTHORITATIVE)",
        "",
        f"> **{report['disclaimer']}**",
        "",
        f"## {icon} {status}",
        "",
        "- The latest `paper_verify_report.json` is the **authoritative** paper status. The "
        "committed `paper_ledger.db` and the accounting writer's returned status code are RAW "
        "accounting artifacts / a runner status only — NOT proof of a trusted run. A paper run "
        "is trusted **iff** this report's `status == OK`.",
        f"- Verified (UTC): {report['verified_at']}",
        f"- Verifier: {report['verifier']} v{report['verifier_version']}",
        f"- DB: {report['db_path']}",
        f"- Committed batches/events/equity rows: "
        f"{report.get('batches', '?')}/{report.get('events', '?')}/{report.get('equity_rows', '?')}",
        f"- forward_start_ts: {report.get('forward_start_ts', 'unknown')}",
        f"- Content digest: {report.get('content_sha256') or 'n/a'}",
        f"- Verdict: {report['current_verdict']}",
        "",
    ]
    if report["failures"]:
        lines.append(f"## Failures ({report['failure_count']})")
        for f in report["failures"]:
            lines.append(f"- {f}")
        lines.append("")
    return "\n".join(lines)


def verify_and_publish(
    db_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    *,
    now: datetime | None = None,
    write_log: bool = True,
) -> VerifyResult:
    """Verify the DB read-only and PUBLISH the authoritative report/receipt/log atomically.

    This is the only component allowed to publish an authoritative paper status. It validates and
    computes content digests through one pinned read-only SQLite snapshot, then writes:

      - ``paper_verify_report.json``  (authoritative latest terminal report)
      - ``paper_verify_receipt.md``   (human receipt)
      - ``paper_verify_log.jsonl``    (append-only audit trail; NON-gating) when ``write_log``

    Artifacts go to ``output_dir`` (default: the DB's directory). The DB is only ever read
    (read-only / query-only); no runner artifact is mutated. The receipt is written first and the
    authoritative report last, so a crash mid-publish leaves the prior report in place rather than a
    truncated/false one. The returned ``VerifyResult.report`` is the published envelope.
    """
    db_path = get_paper_db_path(db_path)
    out = Path(output_dir) if output_dir is not None else Path(db_path).parent

    report_seed = {"db_path": str(db_path), "disclaimer": VERIFIER_DISCLAIMER}
    if not Path(db_path).exists():
        result = VerifyResult(STATUS_CONFIG_ERROR, [f"DB not found: {db_path}"], report_seed)
        digests: dict[str, str] = {}
    else:
        try:
            conn = _open_snapshot(Path(db_path))
        except sqlite3.Error as exc:
            result = VerifyResult(
                STATUS_CONFIG_ERROR,
                [f"Could not open DB read-only: {type(exc).__name__}: {exc}"],
                report_seed,
            )
            digests = {}
        else:
            try:
                result = _verify_connection(conn, Path(db_path))
                digests = _content_digests(conn)
                if result.status == STATUS_OK and not digests.get("content_sha256"):
                    result = VerifyResult(
                        STATUS_CORRUPT,
                        ["Could not digest the validated SQLite snapshot"],
                        result.report,
                    )
            finally:
                conn.close()
    report = _build_published_report(Path(db_path), result, digests, now)

    out.mkdir(parents=True, exist_ok=True)
    ledger.write_text_atomic(out / RECEIPT_FILE, _render_receipt(report))
    ledger.write_json_atomic(out / REPORT_FILE, report)
    if write_log:
        ledger.append_rows(
            out / LOG_FILE,
            [{
                "verified_at": report["verified_at"],
                "status": report["status"],
                "trusted": report["trusted"],
                "failure_count": report["failure_count"],
                "content_sha256": report.get("content_sha256"),
                "verifier_version": SQLITE_VERIFIER_VERSION,
            }],
        )

    result.report = report
    return result


__all__ = [
    "STATUS_OK",
    "STATUS_CONFIG_ERROR",
    "STATUS_CORRUPT",
    "STATUS_PRE_START",
    "EXIT_CODE",
    "VERIFIER_DISCLAIMER",
    "SQLITE_VERIFIER_VERSION",
    "REPORT_FILE",
    "RECEIPT_FILE",
    "LOG_FILE",
    "VerifyResult",
    "verify_database",
    "verify_and_publish",
]
