"""SQLite paper accounting writer (Phase 2).

Implements the transactional writer for the paper ledger. Processes forward
observer signals and writes all ledger rows inside a single BEGIN IMMEDIATE
transaction, with full reconciliation before commit.

The writer is NOT the authority on a trusted run. It only commits raw accounting
artifacts to the DB and RETURNS a runner status code; it publishes no authoritative
``OK`` artifact. Authoritative paper trust is the read-only verifier's
``paper_verify_report.json`` (``sqlite_verify.verify_and_publish``) — a returned
``OK`` here means "this batch committed", not "this run is trusted".

Status codes (RUNNER STATUS ONLY — matching the JSONL runner contract):
  0 = OK
  2 = ABORTED
  3 = CONFIG_ERROR
  4 = CORRUPT_LEDGER
  5 = PRE_START
  6 = LEDGER_BUSY

See docs/ADR/0001-paper-sqlite-ledger.md and docs/paper_pnl_v1_schema.md.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quantbot.data.multi_asset_loader import load_all_ohlcv
from quantbot.data.funding_loader import load_all_funding
from quantbot.data.types import Bar
from quantbot.paper import (
    BASELINE_LABEL,
    PAPER_ENGINE_VERSION,
    forward_obs_dir as default_forward_obs_dir,
    paper_output_dir,
)
from quantbot.paper.config import config_hash, load_config
from quantbot.paper.db import (
    PAPER_ENGINE_VERSION as DB_PAPER_ENGINE_VERSION,
    connect_writer,
    get_paper_db_path,
    validate_database_identity,
)
from quantbot.paper.engine import (
    build_funding_index,
    fill_id,
    funding_in_interval,
    new_state,
    run_engine,
)
from quantbot.paper.freshness import check_freshness
from quantbot.paper.snapshots import (
    bar_commit_id,
    check_divergence,
    consumed_row_digest,
)

# ---------------------------------------------------------------------------
# Clock seam (patchable for deterministic tests)
# ---------------------------------------------------------------------------

def _now() -> datetime:
    """Return the current UTC time.

    A single indirection so tests can pin the writer's clock (freshness gate +
    run_ts) to a fixed instant, making the suite reproducible regardless of the
    wall clock. Production code calls this with no patching.
    """
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EVENT_TYPE_ORDER: list[str] = [
    "signal_snapshot",
    "funding",
    "fill",
    "trade",
    "position_snapshot",
    "equity_snapshot",
]

EVENT_TYPE_RANK: dict[str, int] = {
    et: i for i, et in enumerate(EVENT_TYPE_ORDER)
}

# Status code constants
STATUS_OK = 0
STATUS_ABORTED = 2
STATUS_CONFIG_ERROR = 3
STATUS_CORRUPT_LEDGER = 4
STATUS_PRE_START = 5
STATUS_LEDGER_BUSY = 6


# ---------------------------------------------------------------------------
# Helpers: event-chain construction
# ---------------------------------------------------------------------------

def _event_key(event_type: str, **attrs: Any) -> str:
    """Deterministic event key matching the JSONL id conventions."""
    if event_type == "signal_snapshot":
        return attrs["snapshot_id"]
    if event_type == "funding":
        return attrs["funding_id"]
    if event_type == "fill":
        return attrs["fill_id"]
    if event_type == "trade":
        return attrs["trade_id"]
    if event_type == "position_snapshot":
        return f"pos|{attrs['bar_ts']}"
    if event_type == "equity_snapshot":
        return f"eq|{attrs['bar_ts']}"
    raise ValueError(f"Unknown event_type: {event_type}")


def _event_bar_ts(event_type: str, attrs: dict[str, Any]) -> str | None:
    """Return the bar a row belongs to, for ledger_events.bar_ts + chain order.

    The engine names the anchoring bar differently per row type (fills key off
    the *signal* bar, trades off the *exit* bar); ``ledger_events.bar_ts`` and
    the deterministic chain order both need the resolved bar, not a bare
    ``attrs.get('bar_ts')`` which is ``None`` for fills/trades.
    """
    if event_type == "fill":
        return attrs.get("signal_bar_ts")
    if event_type == "trade":
        return attrs.get("exit_bar_ts")
    return attrs.get("bar_ts")


def _sort_events_for_chain(
    signal_snapshots: list[dict],
    funding_rows: list[dict],
    fill_rows: list[dict],
    trade_rows: list[dict],
    position_snapshots: list[dict],
    equity_snapshots: list[dict],
) -> list[tuple[str, dict[str, Any]]]:
    """Return [(event_type, attrs), ...] in deterministic chain order.

    Order: by resolved bar_ts, then by EVENT_TYPE_ORDER rank.
    Within each type, keys are sorted deterministically.
    """
    events: list[tuple[str, int, str, str, dict[str, Any]]] = []

    def _add(event_type: str, rows: list[dict]) -> None:
        rank = EVENT_TYPE_RANK[event_type]
        for row in rows:
            key = _event_key(event_type, **row)
            bar = _event_bar_ts(event_type, row) or ""
            events.append((event_type, rank, bar, key, row))

    _add("signal_snapshot", signal_snapshots)
    _add("funding", funding_rows)
    _add("fill", fill_rows)
    _add("trade", trade_rows)
    _add("position_snapshot", position_snapshots)
    _add("equity_snapshot", equity_snapshots)

    # bar_ts first, then event-type rank, then key — deterministic and stable.
    events.sort(key=lambda x: (x[2], x[1], x[3]))

    return [(et, attrs) for et, _, _, _, attrs in events]


# ---------------------------------------------------------------------------
# Helpers: DB write helpers (inside transaction).
# ---------------------------------------------------------------------------

def _insert_ledger_batch(
    conn: sqlite3.Connection,
    created_at: str,
    started_at: str | None,
    prior_watermark: str | None,
    paper_engine_version: str,
    config_hash_val: str,
) -> int:
    """Insert a ledger_batches row; return the new batch_id."""
    cur = conn.execute(
        """
        INSERT INTO ledger_batches (
            created_at, started_at, prior_watermark_bar_ts,
            paper_engine_version, config_hash
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (created_at, started_at, prior_watermark, paper_engine_version, config_hash_val),
    )
    return cur.lastrowid  # type: ignore[no-any-return]


def _update_batch_on_commit(
    conn: sqlite3.Connection,
    batch_id: int,
    committed_at: str,
    new_watermark: str | None,
    first_event_seq: int | None,
    last_event_seq: int | None,
    event_count: int,
    committed_bar_count: int,
    git_sha: str | None,
) -> None:
    conn.execute(
        """
        UPDATE ledger_batches
        SET committed_at = ?,
            new_watermark_bar_ts = ?,
            first_event_seq = ?,
            last_event_seq = ?,
            event_count = ?,
            committed_bar_count = ?,
            git_sha = ?
        WHERE batch_id = ?
        """,
        (
            committed_at,
            new_watermark,
            first_event_seq,
            last_event_seq,
            event_count,
            committed_bar_count,
            git_sha,
            batch_id,
        ),
    )


def _insert_typed_rows_for_bar(
    conn: sqlite3.Connection,
    batch_id: int,
    bar_ts: str,
    bar_commit_id: str,
    engine_result: Any,
    event_seq_by_key: dict[str, int],
    signal_snapshots_for_bar: list[dict],
    funding_for_bar: list[dict],
    fills_for_bar: list[dict],
    trades_for_bar: list[dict],
    position_snapshot_for_bar: dict | None,
    equity_snapshot_for_bar: dict | None,
    open_positions_after: dict[str, dict],
) -> None:
    """Insert all typed rows for one committed bar.

    `event_seq_by_key` maps (event_type, event_key) -> ledger_events.seq
    (already inserted). The key is the (type, key) PAIR, not the key alone:
    an exit fill and its closing trade share the same id, so keying by the
    bare event_key would collide and misroute the typed rows.
    """
    # signal_snapshots
    for snap in signal_snapshots_for_bar:
        seq = event_seq_by_key[("signal_snapshot", _event_key("signal_snapshot", **snap))]
        conn.execute(
            """
            INSERT INTO signal_snapshots (
                seq, batch_id, snapshot_id, bar_ts, bar_commit_id,
                bar_index, active_symbols, portfolio_heat,
                heat_cap_triggered, weighted_return,
                source_observation_digest, source_observation_mtime, run_ts
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                seq,
                batch_id,
                snap["snapshot_id"],
                snap["bar_ts"],
                snap["bar_commit_id"],
                snap.get("bar_index"),
                json.dumps(sorted(snap.get("active_symbols", []))),
                snap.get("portfolio_heat"),
                1 if snap.get("heat_cap_triggered") else 0,
                snap.get("weighted_return"),
                snap.get("source_observation_digest", ""),
                snap.get("source_observation_mtime"),
                snap.get("run_ts", ""),
            ),
        )

    # funding
    for f in funding_for_bar:
        seq = event_seq_by_key[("funding", _event_key("funding", **f))]
        conn.execute(
            """
            INSERT INTO funding (
                seq, batch_id, funding_id, bar_commit_id, symbol,
                bar_ts, window_start, window_end, notional_usd,
                funding_rate, funding_events, rate_available, funding_amount
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                seq,
                batch_id,
                f["funding_id"],
                f["bar_commit_id"],
                f["symbol"],
                f["bar_ts"],
                f["window_start"],
                f["window_end"],
                f["notional_usd"],
                f["funding_rate"],
                f["funding_events"],
                1 if f["rate_available"] else 0,
                f["funding_amount"],
            ),
        )

    # fills
    for fl in fills_for_bar:
        seq = event_seq_by_key[("fill", _event_key("fill", **fl))]
        conn.execute(
            """
            INSERT INTO fills (
                seq, batch_id, fill_id, bar_commit_id, signal_bar_ts,
                fill_ts, symbol, side, kind, qty, open_price,
                fill_price, slippage_bps, fee, backfill
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                seq,
                batch_id,
                fl["fill_id"],
                fl["bar_commit_id"],
                fl["signal_bar_ts"],
                fl["fill_ts"],
                fl["symbol"],
                fl["side"],
                fl["kind"],
                fl["qty"],
                fl["open_price"],
                fl["fill_price"],
                fl["slippage_bps"],
                fl["fee"],
                1 if fl.get("backfill") else 0,
            ),
        )

    # trades
    for tr in trades_for_bar:
        seq = event_seq_by_key[("trade", _event_key("trade", **tr))]
        conn.execute(
            """
            INSERT INTO trades (
                seq, batch_id, trade_id, bar_commit_id, symbol,
                entry_fill_id, exit_fill_id, entry_bar_ts, exit_bar_ts,
                qty, entry_price, exit_price, gross_pnl, fees,
                funding, net_pnl, hold_bars, backfill
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                seq,
                batch_id,
                tr["trade_id"],
                tr["bar_commit_id"],
                tr["symbol"],
                tr["entry_fill_id"],
                tr["exit_fill_id"],
                tr["entry_bar_ts"],
                tr["exit_bar_ts"],
                tr["qty"],
                tr["entry_price"],
                tr["exit_price"],
                tr["gross_pnl"],
                tr["fees"],
                tr["funding"],
                tr["net_pnl"],
                tr["hold_bars"],
                1 if tr.get("backfill") else 0,
            ),
        )

    # position_snapshot (+ symbols child table)
    if position_snapshot_for_bar:
        seq = event_seq_by_key[
            ("position_snapshot", _event_key("position_snapshot", **position_snapshot_for_bar))
        ]
        ps = position_snapshot_for_bar
        conn.execute(
            """
            INSERT INTO position_snapshots (
                seq, batch_id, bar_ts, bar_commit_id,
                open_symbols, num_open
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                seq,
                batch_id,
                ps["bar_ts"],
                ps["bar_commit_id"],
                json.dumps(sorted(ps.get("open_symbols", []))),
                ps.get("num_open", 0),
            ),
        )
        # child rows
        for sym, pos in sorted(open_positions_after.items()):
            unrealized_gross = pos.get("unrealized_gross", 0.0)
            conn.execute(
                """
                INSERT INTO position_snapshot_symbols (
                    snapshot_seq, symbol, qty, entry_price,
                    entry_fill_id, entry_bar_ts, unrealized_gross
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    seq,
                    sym,
                    pos["qty"],
                    pos["entry_price"],
                    pos["entry_fill_id"],
                    pos["entry_bar_ts"],
                    unrealized_gross,
                ),
            )

    # equity_snapshot
    if equity_snapshot_for_bar:
        seq = event_seq_by_key[
            ("equity_snapshot", _event_key("equity_snapshot", **equity_snapshot_for_bar))
        ]
        eq = equity_snapshot_for_bar
        conn.execute(
            """
            INSERT INTO equity_snapshots (
                seq, batch_id, bar_ts, bar_commit_id,
                realized_gross_pnl, unrealized_pnl, funding_cum,
                fees_cum, equity, drawdown, num_open
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                seq,
                batch_id,
                eq["bar_ts"],
                eq["bar_commit_id"],
                eq["realized_gross_pnl"],
                eq["unrealized_pnl"],
                eq["funding_cum"],
                eq["fees_cum"],
                eq["equity"],
                eq["drawdown"],
                eq["num_open"],
            ),
        )


# ---------------------------------------------------------------------------
# Helpers: build snapshots for SQLite (matching JSONL runner semantics).
# ---------------------------------------------------------------------------

def _build_signal_snapshots_for_bars(
    per_bar_obs: list[dict],
    processed_bar_ts: set[str],
    engine_version: str,
    config_hash_val: str,
) -> list[dict]:
    """Build signal_snapshot rows for bars that got new accounting.

    Mirrors snapshots.build_snapshots() but returns dicts suitable
    for SQLite insertion.
    """
    results: list[dict] = []
    for obs in per_bar_obs:
        ts = obs["timestamp"]
        if ts not in processed_bar_ts:
            continue
        commit_id = bar_commit_id(obs, ts, engine_version, config_hash_val)
        snap_id = commit_id  # snapshot_id = bar_commit_id for v1
        results.append(
            {
                "snapshot_id": snap_id,
                "bar_ts": ts,
                "bar_commit_id": commit_id,
                "bar_index": obs.get("bar_index"),
                "active_symbols": sorted(obs.get("active_symbols", [])),
                "portfolio_heat": obs.get("portfolio_heat", 0.0),
                "heat_cap_triggered": bool(obs.get("heat_cap_triggered", False)),
                "weighted_return": obs.get("weighted_return", 0.0),
                "source_observation_digest": consumed_row_digest(obs),
                "source_observation_mtime": None,
                "run_ts": _now().strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )
    return results


def _group_engine_result_by_bar(
    engine_result: Any,
    per_bar_obs: list[dict],
    engine_version: str,
    config_hash_val: str,
    prior_open_positions: dict[str, dict] | None = None,
) -> list[dict]:
    """Group engine result rows into per-bar dicts for SQLite insertion.

    Returns a list of dicts, one per bar that was committed, each carrying:
      bar_ts, bar_commit_id,
      signal_snapshots, funding, fills, trades,
      position_snapshot, equity_snapshot,
      open_positions_after

    ``prior_open_positions`` seeds the per-bar open-book walk with the positions
    already open at the START of this run (loaded from the DB on a restart), so
    the per-bar position_snapshots reflect carried-over positions — not an empty
    book. Without it, a restart batch's position_snapshots would disagree with
    the (correctly seeded) position_snapshot_symbols child rows.
    """
    # Build bar_commit_id lookup
    commit_id_by_ts: dict[str, str] = {}
    for obs in per_bar_obs:
        ts = obs["timestamp"]
        commit_id_by_ts[ts] = bar_commit_id(obs, ts, engine_version, config_hash_val)

    # Index engine result rows by bar_ts
    equity_by_ts: dict[str, dict] = {}
    for eq in engine_result.equity:
        equity_by_ts[eq["bar_ts"]] = eq

    funding_by_ts: dict[str, list[dict]] = {}
    for f in engine_result.funding:
        funding_by_ts.setdefault(f["bar_ts"], []).append(f)

    fills_by_ts: dict[str, list[dict]] = {}
    for fl in engine_result.fills:
        ts = fl["signal_bar_ts"]
        fills_by_ts.setdefault(ts, []).append(fl)

    trades_by_ts: dict[str, list[dict]] = {}
    for tr in engine_result.trades:
        ts = tr["exit_bar_ts"]
        trades_by_ts.setdefault(ts, []).append(tr)

    # Walk in sorted order, tracking open_positions incrementally. Seed with the
    # positions already open at the start of this run (restart state) so the
    # per-bar pre-fill snapshots include carried-over positions.
    sorted_ts = sorted(equity_by_ts.keys())
    open_positions: dict[str, dict] = {
        sym: dict(pos) for sym, pos in (prior_open_positions or {}).items()
    }
    bars: list[dict] = []

    for ts in sorted_ts:
        eq = equity_by_ts[ts]
        commit_id = commit_id_by_ts.get(ts, "")

        # Build position_snapshot (pre-fill book = current open_positions)
        pos_snap = {
            "bar_ts": ts,
            "bar_commit_id": commit_id,
            "open_symbols": sorted(open_positions.keys()),
            "num_open": len(open_positions),
        }

        bar_dict: dict[str, Any] = {
            "bar_ts": ts,
            "bar_commit_id": commit_id,
            "signal_snapshots": _build_signal_snapshots_for_bars(
                [obs for obs in per_bar_obs if obs["timestamp"] == ts],
                {ts},
                engine_version,
                config_hash_val,
            ),
            "funding": funding_by_ts.get(ts, []),
            "fills": fills_by_ts.get(ts, []),
            "trades": trades_by_ts.get(ts, []),
            "position_snapshot": pos_snap,
            "equity_snapshot": eq,
            "open_positions_after": dict(open_positions),
        }
        bars.append(bar_dict)

        # Apply fills for this bar to open_positions (post-snapshot)
        for fl in fills_by_ts.get(ts, []):
            sym = fl["symbol"]
            if fl["kind"] == "entry":
                open_positions[sym] = {
                    "entry_fill_id": fl["fill_id"],
                    "entry_price": fl["fill_price"],
                    "qty": fl["qty"],
                    "entry_bar_ts": ts,
                    "entry_fill_ts": fl["fill_ts"],
                    "funding_accrued": 0.0,
                    "entry_fee": fl["fee"],
                    "hold_bars": 0,
                    "unrealized_gross": 0.0,
                }
            elif fl["kind"] == "exit":
                open_positions.pop(sym, None)

    return bars


# ---------------------------------------------------------------------------
# Reconciliation inside transaction (before commit).
# ---------------------------------------------------------------------------

def _reconcile_batch_inside_tx(
    conn: sqlite3.Connection,
    batch_id: int,
    event_count_expected: int,
    events_inserted: list[tuple[str, str, str, str | None]],
    typed_row_counts: dict[str, int],
    open_positions_reconstructed: dict[str, dict],
    state_accumulators: dict[str, float],
    peak_equity: float,
    initial_equity: float,
    fee_bps: float,
) -> list[str]:
    """Run reconciliation checks BEFORE commit. Return list of failure strings."""
    failures: list[str] = []

    # 1. Batch event count matches inserted rows
    row = conn.execute(
        "SELECT COUNT(*) AS cnt FROM ledger_events WHERE batch_id = ?",
        (batch_id,),
    ).fetchone()
    if row and row["cnt"] != event_count_expected:
        failures.append(
            f"Batch event count mismatch: expected {event_count_expected}, "
            f"got {row['cnt']}"
        )

    # 2. Event type / typed row counts match
    for et in EVENT_TYPE_ORDER:
        expected = typed_row_counts.get(et, 0)
        actual = conn.execute(
            "SELECT COUNT(*) AS cnt FROM ledger_events WHERE batch_id = ? AND event_type = ?",
            (batch_id, et),
        ).fetchone()["cnt"]
        if expected != actual:
            failures.append(
                f"Event type {et} count mismatch: expected {expected}, got {actual}"
            )

    # 3. prev_seq chain coherence (across batches). The batch's first event must
    # link to the immediately preceding GLOBAL event (NULL only if it is the very
    # first event ever); subsequent events link to their predecessor in-batch.
    events = conn.execute(
        "SELECT seq, prev_seq FROM ledger_events WHERE batch_id = ? ORDER BY seq",
        (batch_id,),
    ).fetchall()
    if events:
        first = events[0]
        global_pred = conn.execute(
            "SELECT MAX(seq) FROM ledger_events WHERE seq < ?", (first["seq"],)
        ).fetchone()[0]
        if first["prev_seq"] != global_pred:
            failures.append(
                f"First batch event seq={first['seq']} prev_seq={first['prev_seq']} "
                f"!= global predecessor {global_pred}"
            )
        prev = first["seq"]
        for erow in events[1:]:
            if erow["prev_seq"] != prev:
                failures.append(
                    f"Event seq={erow['seq']} prev_seq={erow['prev_seq']} "
                    f"!= expected {prev}"
                )
            prev = erow["seq"]

    # 4. Every typed row references valid event
    for et in EVENT_TYPE_ORDER:
        table = {
            "signal_snapshot": "signal_snapshots",
            "funding": "funding",
            "fill": "fills",
            "trade": "trades",
            "position_snapshot": "position_snapshots",
            "equity_snapshot": "equity_snapshots",
        }[et]
        orphans = conn.execute(
            f"""
            SELECT COUNT(*) AS cnt FROM {table}
            WHERE batch_id = ? AND seq NOT IN (
                SELECT seq FROM ledger_events WHERE batch_id = ? AND event_type = ?
            )
            """,
            (batch_id, batch_id, et),
        ).fetchone()
        if orphans and orphans["cnt"] > 0:
            failures.append(f"Orphan typed rows in {table} for batch {batch_id}")

    # 5. Every event has exactly one typed row
    for et in EVENT_TYPE_ORDER:
        table = {
            "signal_snapshot": "signal_snapshots",
            "funding": "funding",
            "fill": "fills",
            "trade": "trades",
            "position_snapshot": "position_snapshots",
            "equity_snapshot": "equity_snapshots",
        }[et]
        event_count = conn.execute(
            "SELECT COUNT(*) AS cnt FROM ledger_events WHERE batch_id = ? AND event_type = ?",
            (batch_id, et),
        ).fetchone()["cnt"]
        typed_count = conn.execute(
            f"SELECT COUNT(*) AS cnt FROM {table} WHERE batch_id = ?",
            (batch_id,),
        ).fetchone()["cnt"]
        if event_count != typed_count:
            failures.append(
                f"Event/typed row count mismatch for {et}: "
                f"events={event_count}, typed={typed_count}"
            )

    # 6. No fill before forward_start_ts
    cfg = conn.execute("SELECT forward_start_ts FROM paper_config WHERE id = 1").fetchone()
    if cfg:
        fwd = cfg["forward_start_ts"]
        pre = conn.execute(
            """
            SELECT COUNT(*) AS cnt FROM fills f
            JOIN ledger_events e ON e.seq = f.seq
            WHERE e.batch_id = ? AND f.signal_bar_ts < ?
            """,
            (batch_id, fwd),
        ).fetchone()
        if pre and pre["cnt"] > 0:
            failures.append(f"Found {pre['cnt']} fills before forward_start_ts {fwd}")

    # 7. Fill fee arithmetic: fee = fill_price * qty * fee_bps / 10000
    fee_rate = fee_bps / 10_000.0
    bad_fees = conn.execute(
        """
        SELECT f.seq, f.fill_price, f.qty, f.fee
        FROM fills f
        JOIN ledger_events e ON e.seq = f.seq
        WHERE e.batch_id = ?
          AND ABS(f.fee - (f.fill_price * f.qty * ?)) > 1e-8
        """,
        (batch_id, fee_rate),
    ).fetchall()
    for row in bad_fees:
        expected_fee = row["fill_price"] * row["qty"] * fee_rate
        failures.append(
            f"Fill fee mismatch seq={row['seq']}: "
            f"expected {expected_fee:.8f}, got {row['fee']:.8f}"
        )

    # 8. Trade gross/net arithmetic
    bad_trades = conn.execute(
        """
        SELECT t.seq, t.gross_pnl, t.fees, t.funding, t.net_pnl
        FROM trades t
        JOIN ledger_events e ON e.seq = t.seq
        WHERE e.batch_id = ?
          AND ABS(t.net_pnl - (t.gross_pnl - t.fees - t.funding)) > 1e-8
        """,
        (batch_id,),
    ).fetchall()
    for row in bad_trades:
        failures.append(
            f"Trade net_pnl mismatch seq={row['seq']}: "
            f"gross={row['gross_pnl']}, fees={row['fees']}, "
            f"funding={row['funding']}, net={row['net_pnl']}"
        )

    # 9. Funding amount arithmetic: amount = notional_usd * funding_rate
    bad_funding = conn.execute(
        """
        SELECT f.seq, f.notional_usd, f.funding_rate, f.funding_amount, f.rate_available
        FROM funding f
        JOIN ledger_events e ON e.seq = f.seq
        WHERE e.batch_id = ? AND f.rate_available = 1
          AND ABS(f.funding_amount - (f.notional_usd * f.funding_rate)) > 1e-8
        """,
        (batch_id,),
    ).fetchall()
    for row in bad_funding:
        expected_amount = row["notional_usd"] * row["funding_rate"]
        failures.append(
            f"Funding amount mismatch seq={row['seq']}: "
            f"expected {expected_amount:.8f}, got {row['funding_amount']:.8f}"
        )

    # 10. Equity balance arithmetic
    eq_rows = conn.execute(
        """
        SELECT eq.equity, eq.realized_gross_pnl, eq.unrealized_pnl,
               eq.funding_cum, eq.fees_cum
        FROM equity_snapshots eq
        JOIN ledger_events e ON e.seq = eq.seq
        WHERE e.batch_id = ?
        ORDER BY eq.seq
        """,
        (batch_id,),
    ).fetchall()
    for erow in eq_rows:
        expected_equity = (
            initial_equity
            + erow["realized_gross_pnl"]
            - erow["fees_cum"]
            - erow["funding_cum"]
            + erow["unrealized_pnl"]
        )
        if abs(erow["equity"] - expected_equity) > 1e-6:
            failures.append(
                f"Equity balance mismatch: expected {expected_equity:.8f}, "
                f"got {erow['equity']:.8f}"
            )

    # 11. Drawdown arithmetic
    peak = initial_equity
    eq_all = conn.execute(
        """
        SELECT eq.equity, eq.drawdown
        FROM equity_snapshots eq
        JOIN ledger_events e ON e.seq = eq.seq
        WHERE e.batch_id = ?
        ORDER BY eq.seq
        """,
        (batch_id,),
    ).fetchall()
    for erow in eq_all:
        if erow["equity"] > peak:
            peak = erow["equity"]
        expected_dd = (peak - erow["equity"]) / peak if peak > 0 else 0.0
        if abs(erow["drawdown"] - expected_dd) > 1e-8:
            failures.append(
                f"Drawdown mismatch: expected {expected_dd:.8f}, "
                f"got {erow['drawdown']:.8f}"
            )

    # 12. ledger_state accumulators match
    state = conn.execute("SELECT * FROM ledger_state WHERE id = 1").fetchone()
    if state:
        if abs(state["realized_gross"] - state_accumulators.get("realized_gross", 0.0)) > 1e-8:
            failures.append("ledger_state.realized_gross mismatch after batch")
        if abs(state["fees_cum"] - state_accumulators.get("fees_cum", 0.0)) > 1e-8:
            failures.append("ledger_state.fees_cum mismatch after batch")
        if abs(state["funding_cum"] - state_accumulators.get("funding_cum", 0.0)) > 1e-8:
            failures.append("ledger_state.funding_cum mismatch after batch")
        if peak > 0 and abs(state["peak_equity"] - peak) > 1e-8:
            failures.append("ledger_state.peak_equity mismatch after batch")

    # 13. open_positions matches reconstructed
    db_positions = {
        row["symbol"]: dict(row)
        for row in conn.execute("SELECT * FROM open_positions").fetchall()
    }
    for sym, pos in open_positions_reconstructed.items():
        if sym not in db_positions:
            failures.append(f"open_positions: symbol {sym} missing after batch")
        else:
            db_pos = db_positions[sym]
            if abs(db_pos["qty"] - pos["qty"]) > 1e-8:
                failures.append(f"open_positions: qty mismatch for {sym}")
            if abs(db_pos["entry_price"] - pos["entry_price"]) > 1e-8:
                failures.append(f"open_positions: entry_price mismatch for {sym}")

    # 14. watermark equals latest committed equity bar
    latest_eq = conn.execute(
        """
        SELECT eq.bar_ts FROM equity_snapshots eq
        JOIN ledger_events e ON e.seq = eq.seq
        WHERE e.batch_id = ?
        ORDER BY eq.seq DESC LIMIT 1
        """,
        (batch_id,),
    ).fetchone()
    state = conn.execute("SELECT watermark_bar_ts FROM ledger_state WHERE id = 1").fetchone()
    if latest_eq and state:
        if state["watermark_bar_ts"] != latest_eq["bar_ts"]:
            failures.append(
                f"Watermark mismatch: state={state['watermark_bar_ts']}, "
                f"latest_equity={latest_eq['bar_ts']}"
            )

    return failures


# ---------------------------------------------------------------------------
# Main entry point.
# ---------------------------------------------------------------------------

def run_sqlite_accounting(
    db_path: str | Path | None = None,
    forward_obs_dir: Path | None = None,
    data_dir: Path | None = None,
) -> tuple[int, str]:
    """Run one SQLite paper accounting pass.

    Args:
        db_path: Path to the SQLite ledger DB. Uses get_paper_db_path() if None.
        forward_obs_dir: Path to observation_log.json directory.
        data_dir: Path to data directory for OHLCV/funding CSVs.
                    Patches quantbot.data.multi_asset_loader._DATA_DIR
                    and quantbot.data.funding_loader._DATA_DIR so the
                    existing load_all_ohlcv/load_all_funding helpers read
                    from the specified directory.

    Returns (status_code, status_message).

    Status codes:
      0  OK
      2  ABORTED
      3  CONFIG_ERROR
      4  CORRUPT_LEDGER
      5  PRE_START
      6  LEDGER_BUSY
    """
    db_path = get_paper_db_path(db_path)
    obs_dir = forward_obs_dir or default_forward_obs_dir()
    now = _now()
    created_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    # === PATCH DATA_DIR INTO EXISTING LOADERS =========================
    if data_dir is not None:
        import quantbot.data.multi_asset_loader as _ma
        import quantbot.data.funding_loader as _fl
        _orig_multi = _ma._DATA_DIR
        _orig_funding = _fl._DATA_DIR
        _ma._DATA_DIR = Path(data_dir)
        _fl._DATA_DIR = Path(data_dir)
    else:
        _orig_multi = None
        _orig_funding = None

    try:
        # === CONFIG (fail closed) =================================================
        try:
            # Resolve the paper config dir via paper_output_dir() so the writer honors
            # QNTY_PAPER_OUTPUT_DIR (testability seam). Production default is unchanged:
            # paper_output_dir() returns /srv/qnty/output/paper_pnl_v1 when the env is unset.
            config = load_config(paper_output_dir())
        except Exception as exc:
            return STATUS_CONFIG_ERROR, f"Config error: {exc}"

        # === CONNECT + BEGIN IMMEDIATE =========================================
        try:
            conn = connect_writer(db_path, timeout=5.0)
        except Exception as exc:
            return STATUS_CONFIG_ERROR, f"DB connection failed: {exc}"

        try:
            # Try BEGIN IMMEDIATE; if it fails, DB is locked by another writer
            try:
                conn.execute("BEGIN IMMEDIATE")
            except sqlite3.OperationalError as exc:
                conn.close()
                msg = str(exc).lower()
                if "lock" in msg or "busy" in msg:
                    return STATUS_LEDGER_BUSY, f"Could not acquire write lock: {exc}"
                return STATUS_CONFIG_ERROR, f"BEGIN IMMEDIATE failed: {exc}"

            # === RE-READ DB CONFIG + STATE INSIDE TRANSACTION =====================
            try:
                db_config = validate_database_identity(conn)
            except Exception as exc:
                conn.rollback()
                conn.close()
                return STATUS_CONFIG_ERROR, f"DB identity invalid: {exc}"

            fs_identity = (
                config.get("forward_start_ts"),
                config.get("config_hash"),
            )
            db_identity = (
                db_config.get("forward_start_ts"),
                db_config.get("config_hash"),
            )
            if fs_identity != db_identity:
                conn.rollback()
                conn.close()
                return (
                    STATUS_CONFIG_ERROR,
                    "Filesystem paper_config.json identity does not match SQLite paper_config "
                    f"(filesystem forward_start_ts/config_hash={fs_identity!r}, "
                    f"database={db_identity!r})",
                )

            state_row = conn.execute("SELECT * FROM ledger_state WHERE id = 1").fetchone()
            if state_row is None:
                conn.rollback()
                conn.close()
                return STATUS_CORRUPT_LEDGER, "ledger_state row (id=1) not found"

            watermark = state_row["watermark_bar_ts"] or ""
            acc = {
                "realized_gross": state_row["realized_gross"],
                "fees_cum": state_row["fees_cum"],
                "funding_cum": state_row["funding_cum"],
            }
            peak_equity = state_row["peak_equity"] or float(config.get("initial_equity_usd", 10000.0))

            forward_start_ts = db_config["forward_start_ts"]
            initial_equity = float(db_config["initial_equity_usd"])
            notional = float(db_config.get("notional_usd", 1000.0))
            fee_bps = float(db_config.get("fee_bps", 5.0))
            engine_version = DB_PAPER_ENGINE_VERSION
            cfg_hash = db_config["config_hash"]

            # === LOAD INPUTS =========================================================
            obs_path = obs_dir / "observation_log.json"
            if not obs_path.exists():
                conn.rollback()
                conn.close()
                return STATUS_ABORTED, f"observation_log.json not found: {obs_path}"

            try:
                with open(obs_path, encoding="utf-8") as fh:
                    obs_log = json.load(fh)
            except Exception as exc:
                conn.rollback()
                conn.close()
                return STATUS_ABORTED, f"Malformed observation_log.json: {exc}"

            # Freshness gate
            freshness_cfg = config.get("freshness", {})
            fresh = check_freshness(
                obs_path, obs_log, obs_dir, now, freshness_cfg,
                forward_start_ts=forward_start_ts,
            )
            if fresh.aborted:
                conn.rollback()
                conn.close()
                return STATUS_ABORTED, f"{fresh.code}: {fresh.reason}"

            if fresh.code == "NO_ELIGIBLE_BARS_YET":
                conn.rollback()
                conn.close()
                return STATUS_PRE_START, fresh.reason

            per_bar_obs = obs_log.get("per_bar_obs", [])

            # === DIVERGENCE CHECK (missing from initial implementation) =============
            # Read existing signal snapshots from DB for divergence check
            existing_snapshots = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT ss.* FROM signal_snapshots ss
                    JOIN ledger_events e ON e.seq = ss.seq
                    ORDER BY ss.bar_ts
                    """
                ).fetchall()
            ]
            divergence = check_divergence(existing_snapshots, per_bar_obs)
            if divergence:
                conn.rollback()
                conn.close()
                return STATUS_ABORTED, f"SIGNAL_SNAPSHOT_DIVERGENCE: {divergence}"

            # Build state dict for engine (matching JSONL runner)
            engine_state: dict[str, Any] = {
                "watermark_bar_ts": watermark,
                "open_positions": {
                    row["symbol"]: dict(row)
                    for row in conn.execute("SELECT * FROM open_positions").fetchall()
                },
                "accumulators": acc,
                "peak_equity": peak_equity,
                "bars_elapsed": 0,
            }
            # Snapshot the open book BEFORE the engine mutates it — needed to seed
            # the per-bar position snapshots for a restart batch.
            prior_open_positions = {
                sym: dict(pos) for sym, pos in engine_state["open_positions"].items()
            }

            # Load market data (using patched data_dir if provided)
            bars_by_symbol: dict[str, list[Bar]] | None = load_all_ohlcv()
            funding_df = load_all_funding()

            # Build engine config (matching config.py build_config output)
            engine_config: dict[str, Any] = {
                "forward_start_ts": forward_start_ts,
                "initial_equity_usd": initial_equity,
                "notional_usd": notional,
                "leverage": db_config.get("leverage", 1.0),
                "fee_model": {"type": "flat_taker", "fee_bps": fee_bps},
                "slippage_model": {
                    "type": "fixed",
                    "slippage_bps": db_config.get("slippage_bps", 5.0),
                },
                "funding_model": {
                    "type": db_config.get("funding_type", "accrual"),
                    "applied_as": db_config.get("funding_applied_as", "cash_flow"),
                },
                "fill_model": db_config.get("fill_model", "next_bar_open_pessimistic"),
                "signal_source": db_config.get("signal_source", "observation_log.json:per_bar_obs"),
                "engine_version": engine_version,
                "config_hash": cfg_hash,
                "freshness": freshness_cfg,
            }

            # === RUN ENGINE =====================================================
            result = run_engine(engine_config, per_bar_obs, bars_by_symbol, funding_df, engine_state)

            if not result.equity:
                # No bar produced an equity snapshot this run — either everything
                # is up to date or the next eligible bar deferred on a missing T+1
                # open. Either way there is nothing to commit; never write an empty
                # batch (the verifier treats a committed empty batch as CORRUPT).
                conn.rollback()
                conn.close()
                return STATUS_OK, "No new bars to process"

            # === INSERT INTO DB INSIDE TRANSACTION ==========================
            batch_id = _insert_ledger_batch(
                conn,
                created_at=created_at,
                started_at=created_at,
                prior_watermark=watermark or None,
                paper_engine_version=engine_version,
                config_hash_val=cfg_hash,
            )

            # Build the event chain for all new rows
            processed_bar_ts = {eq["bar_ts"] for eq in result.equity}

            # Build per-bar data (seeded with the restart open book)
            bars_data = _group_engine_result_by_bar(
                result, per_bar_obs, engine_version, cfg_hash, prior_open_positions
            )

            # Build signal snapshots list
            all_signal_snapshots = _build_signal_snapshots_for_bars(
                per_bar_obs, processed_bar_ts, engine_version, cfg_hash
            )
            snapshot_by_ts: dict[str, dict] = {}
            for snap in all_signal_snapshots:
                snapshot_by_ts[snap["bar_ts"]] = snap

            # Collect all events across all bars, sorted
            all_funding: list[dict] = []
            all_fills: list[dict] = []
            all_trades: list[dict] = []
            all_position_snapshots: list[dict] = []
            all_equity_snapshots: list[dict] = []

            for bar_dict in bars_data:
                ts = bar_dict["bar_ts"]
                all_funding.extend(bar_dict["funding"])
                all_fills.extend(bar_dict["fills"])
                all_trades.extend(bar_dict["trades"])
                if bar_dict["position_snapshot"]:
                    all_position_snapshots.append(bar_dict["position_snapshot"])
                if bar_dict["equity_snapshot"]:
                    all_equity_snapshots.append(bar_dict["equity_snapshot"])

            # Sort into event chain
            event_chain = _sort_events_for_chain(
                all_signal_snapshots,
                all_funding,
                all_fills,
                all_trades,
                all_position_snapshots,
                all_equity_snapshots,
            )

            # Insert ledger_events (first pass)
            # Keyed by (event_type, event_key): an exit fill and its closing
            # trade share the same id, so the bare key is not unique.
            event_seq_by_key: dict[tuple[str, str], int] = {}
            prev_seq: int | None = None

            # Get the max seq so far (for prev_seq chaining across batches)
            max_seq_row = conn.execute(
                "SELECT seq FROM ledger_events ORDER BY seq DESC LIMIT 1"
            ).fetchone()
            if max_seq_row:
                prev_seq = max_seq_row["seq"]

            for event_type, attrs in event_chain:
                event_key = _event_key(event_type, **attrs)
                cur = conn.execute(
                    """
                    INSERT INTO ledger_events (
                        batch_id, event_type, event_key, recorded_at,
                        bar_ts, symbol, prev_seq
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        batch_id,
                        event_type,
                        event_key,
                        created_at,
                        _event_bar_ts(event_type, attrs),
                        attrs.get("symbol"),
                        prev_seq,
                    ),
                )
                seq = cur.lastrowid
                event_seq_by_key[(event_type, event_key)] = seq
                prev_seq = seq

            # Insert typed rows (second pass)
            # Reconstruct open_positions as we walk bars
            replay_positions: dict[str, dict] = {
                row["symbol"]: dict(row)
                for row in conn.execute("SELECT * FROM open_positions").fetchall()
            }

            for bar_dict in bars_data:
                ts = bar_dict["bar_ts"]
                commit_id = bar_dict["bar_commit_id"]

                # signal snapshots for this bar
                snap = snapshot_by_ts.get(ts)
                snap_rows = [snap] if snap else []

                # funding/fills/trades for this bar
                fund_rows = bar_dict["funding"]
                fill_rows = bar_dict["fills"]
                trade_rows = bar_dict["trades"]

                # position snapshot (pre-fill book)
                pos_snap = bar_dict["position_snapshot"]

                # equity snapshot
                eq_row = bar_dict["equity_snapshot"]

                _insert_typed_rows_for_bar(
                    conn, batch_id, ts, commit_id, result,
                    event_seq_by_key,
                    snap_rows, fund_rows, fill_rows, trade_rows,
                    pos_snap, eq_row, replay_positions,
                )

                # Apply fills to replay_positions (post-snapshot)
                for fl in fill_rows:
                    sym = fl["symbol"]
                    if fl["kind"] == "entry":
                        replay_positions[sym] = {
                            "entry_fill_id": fl["fill_id"],
                            "entry_price": fl["fill_price"],
                            "qty": fl["qty"],
                            "entry_bar_ts": ts,
                            "entry_fill_ts": fl["fill_ts"],
                            "funding_accrued": 0.0,
                            "entry_fee": fl["fee"],
                            "hold_bars": 0,
                            "unrealized_gross": 0.0,
                        }
                    elif fl["kind"] == "exit":
                        replay_positions.pop(sym, None)

            # === UPDATE LEDGER_STATE =============================================
            new_watermark = watermark
            if result.equity:
                new_watermark = max(eq["bar_ts"] for eq in result.equity)

            # Update accumulators from engine state
            final_acc = engine_state["accumulators"]
            final_peak = engine_state["peak_equity"]

            conn.execute(
                """
                UPDATE ledger_state
                SET watermark_bar_ts = ?,
                    realized_gross = ?,
                    fees_cum = ?,
                    funding_cum = ?,
                    peak_equity = ?,
                    updated_at = ?
                WHERE id = 1
                """,
                (
                    new_watermark or None,
                    final_acc.get("realized_gross", 0.0),
                    final_acc.get("fees_cum", 0.0),
                    final_acc.get("funding_cum", 0.0),
                    final_peak,
                    created_at,
                ),
            )

            # === UPDATE OPEN_POSITIONS (delete all, re-insert) =====================
            # Persist the engine's authoritative open book (NOT the entry/exit
            # replay): the engine carries the per-bar funding_accrued, hold_bars
            # and entry_fee the exit path needs to resume the position losslessly
            # across runs. The replay only knows fills and would store 0 for
            # funding/hold and lose entry_fee.
            final_open_positions = engine_state["open_positions"]
            conn.execute("DELETE FROM open_positions")
            for sym, pos in final_open_positions.items():
                # The engine's authoritative open book MUST carry the fields the
                # exit path needs to resume a position losslessly across runs. A
                # missing entry_fee / funding_accrued / hold_bars is an internal
                # accounting bug, NOT a tolerable default: persisting a silent 0.0
                # would corrupt a later exit's fee/funding/hold arithmetic. Fail
                # closed so the whole batch rolls back (CORRUPT_LEDGER).
                for _field in ("entry_fee", "funding_accrued", "hold_bars"):
                    if _field not in pos:
                        raise ValueError(
                            f"open position {sym!r} is missing required field "
                            f"{_field!r} in the engine open book; refusing to "
                            f"persist a silent default"
                        )
                conn.execute(
                    """
                    INSERT INTO open_positions (
                        symbol, entry_fill_id, entry_price, qty,
                        entry_bar_ts, entry_fill_ts, entry_fee,
                        funding_accrued, hold_bars
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sym,
                        pos["entry_fill_id"],
                        pos["entry_price"],
                        pos["qty"],
                        pos["entry_bar_ts"],
                        pos["entry_fill_ts"],
                        pos["entry_fee"],
                        pos["funding_accrued"],
                        pos["hold_bars"],
                    ),
                )

            # === RECONCILE INSIDE TRANSACTION (BEFORE COMMIT) =====================
            event_count = len(event_chain)
            typed_counts: dict[str, int] = {}
            for et, _ in event_chain:
                typed_counts[et] = typed_counts.get(et, 0) + 1

            recon_failures = _reconcile_batch_inside_tx(
                conn, batch_id, event_count, event_chain,
                typed_counts, final_open_positions,
                final_acc, final_peak, initial_equity, fee_bps,
            )

            if recon_failures:
                conn.rollback()
                conn.close()
                return (
                    STATUS_CORRUPT_LEDGER,
                    f"Reconciliation failed: {'; '.join(recon_failures[:3])}",
                )

            # === UPDATE BATCH AS COMMITTED ========================================
            first_seq = None
            last_seq = None
            if event_chain:
                first_et, first_attrs = event_chain[0]
                last_et, last_attrs = event_chain[-1]
                first_seq = event_seq_by_key.get(
                    (first_et, _event_key(first_et, **first_attrs))
                )
                last_seq = event_seq_by_key.get(
                    (last_et, _event_key(last_et, **last_attrs))
                )

            committed_bar_count = len(result.equity) if result.equity else 0

            _update_batch_on_commit(
                conn, batch_id,
                committed_at=created_at,
                new_watermark=new_watermark or None,
                first_event_seq=first_seq,
                last_event_seq=last_seq,
                event_count=event_count,
                committed_bar_count=committed_bar_count,
                git_sha=None,
            )

            # === COMMIT ============================================================
            conn.commit()
            conn.close()

            return STATUS_OK, (
                f"Committed batch {batch_id}: {committed_bar_count} bars, "
                f"{event_count} events"
            )

        except Exception as exc:
            try:
                conn.rollback()
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass
            return STATUS_CORRUPT_LEDGER, f"Unhandled error: {type(exc).__name__}: {exc}"

    finally:
        # Restore original _DATA_DIR if we patched it
        if data_dir is not None and _orig_multi is not None:
            import quantbot.data.multi_asset_loader as _ma
            import quantbot.data.funding_loader as _fl
            _ma._DATA_DIR = _orig_multi
            _fl._DATA_DIR = _orig_funding


# ---------------------------------------------------------------------------
# Module-level exports.
# ---------------------------------------------------------------------------

__all__ = [
    "STATUS_OK",
    "STATUS_ABORTED",
    "STATUS_CONFIG_ERROR",
    "STATUS_CORRUPT_LEDGER",
    "STATUS_PRE_START",
    "STATUS_LEDGER_BUSY",
    "run_sqlite_accounting",
]
