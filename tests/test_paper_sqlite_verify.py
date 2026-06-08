"""Tests for the Phase 3 read-only SQLite paper ledger verifier.

All tests use tmp_path only — no repo output, no /srv/qnty, no VM paths.
Clean fixtures are produced by running the Phase 2 writer on a temp DB.
Corruption is injected by dropping the append-only triggers on a writer
connection and mutating committed rows directly.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure repo root is on sys.path.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from quantbot.paper.config import build_config, write_config_once
from quantbot.paper.db import _TRIGGER_SQL, connect_readonly, initialize_database
from quantbot.paper.sqlite_writer import STATUS_OK, run_sqlite_accounting
from quantbot.paper.sqlite_verify import (
    STATUS_CONFIG_ERROR,
    STATUS_CORRUPT,
    STATUS_OK as V_STATUS_OK,
    STATUS_PRE_START,
    verify_database,
)

# Reuse the writer-test fixtures (timestamps, bars, observation log builders).
from tests.test_paper_sqlite_writer import (  # noqa: E402
    AAA_PRICES,
    SYMBOL,
    TS,
    _make_cfg,
    _make_obs,
    _patch_data_loaders,
    _write_observation_log,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _init_db(tmp_path: Path, forward_start_ts: str = "") -> Path:
    """Initialize an empty (PRE_START) DB and return its path."""
    db_path = tmp_path / "paper" / "paper_ledger.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if not forward_start_ts:
        forward_start_ts = TS[0]
    config = build_config(
        forward_start_ts=forward_start_ts,
        initial_equity_usd=10000.0,
        notional_usd=1000.0,
        fee_bps=5.0,
        slippage_bps=5.0,
    )
    write_config_once(config, output_dir=db_path.parent)
    initialize_database(db_path, config)
    return db_path


def _run_writer(tmp_path: Path, db_path: Path, forward_start_ts: str) -> None:
    per_bar_obs = [_make_obs(ts, [SYMBOL], i) for i, ts in enumerate(TS)]
    obs_dir = _write_observation_log(tmp_path, per_bar_obs)
    cfg = _make_cfg()
    cfg["forward_start_ts"] = forward_start_ts
    p1, p2 = _patch_data_loaders(tmp_path)
    with p1, p2:
        with patch("quantbot.paper.sqlite_writer.load_config", return_value=cfg):
            status, msg = run_sqlite_accounting(db_path=db_path, forward_obs_dir=obs_dir)
    assert status == STATUS_OK, f"writer did not return OK: {status}: {msg}"


def _clean_db(tmp_path: Path) -> Path:
    """Minimal committed (OK) DB: one bar, one entry fill, one open position.

    forward_start_ts = TS[0] (the newest bar) makes exactly one bar eligible.
    """
    db_path = _init_db(tmp_path, forward_start_ts=TS[0])
    _run_writer(tmp_path, db_path, TS[0])
    return db_path


def _funding_db(tmp_path: Path) -> Path:
    """Committed (OK) DB with real funding rows.

    forward_start_ts = TS[4] makes 5 bars eligible; the held position accrues
    four funding rows across the run.
    """
    db_path = _init_db(tmp_path, forward_start_ts=TS[4])
    _run_writer(tmp_path, db_path, TS[4])
    return db_path


# active at the three oldest eligible bars, then removed -> a real exit + trade.
_ENTRY_EXIT_ACTIVES = {
    TS[5]: [SYMBOL], TS[4]: [SYMBOL], TS[3]: [SYMBOL],
    TS[2]: [], TS[1]: [], TS[0]: [],
}


def _run_writer_obs(tmp_path: Path, db_path: Path, forward_start_ts: str,
                    per_bar_obs: list[dict]) -> tuple[int, str]:
    obs_dir = _write_observation_log(tmp_path, per_bar_obs)
    cfg = _make_cfg()
    cfg["forward_start_ts"] = forward_start_ts
    p1, p2 = _patch_data_loaders(tmp_path)
    with p1, p2:
        with patch("quantbot.paper.sqlite_writer.load_config", return_value=cfg):
            return run_sqlite_accounting(db_path=db_path, forward_obs_dir=obs_dir)


def _trade_db(tmp_path: Path) -> Path:
    """Writer-produced DB with a real entry->exit->trade in a single run.

    forward_start_ts = TS[4]; the symbol is active for the three oldest eligible
    bars then removed, so the engine emits one entry fill, one exit fill, and the
    closing trade that references them.
    """
    db_path = _init_db(tmp_path, forward_start_ts=TS[4])
    per_bar_obs = [_make_obs(ts, _ENTRY_EXIT_ACTIVES[ts], i) for i, ts in enumerate(TS)]
    status, msg = _run_writer_obs(tmp_path, db_path, TS[4], per_bar_obs)
    assert status == STATUS_OK, f"writer did not return OK: {status}: {msg}"
    # Sanity: this fixture really does carry a committed trade backed by 2 fills.
    assert _scalar(db_path, "SELECT COUNT(*) FROM trades") == 1
    assert _scalar(db_path, "SELECT COUNT(*) FROM fills") == 2
    return db_path


def _restart_trade_db(tmp_path: Path) -> Path:
    """Writer-produced DB where the trade spans TWO runs (restart exit).

    Run 1 commits the entry and holds the position; run 2 (after the symbol is
    removed) loads the position from open_positions and emits the exit + trade.
    """
    db_path = _init_db(tmp_path, forward_start_ts=TS[4])
    # Run 1: only the three oldest bars present, symbol active -> entry + hold.
    obs1 = [_make_obs(ts, [SYMBOL], i) for i, ts in enumerate([TS[5], TS[4], TS[3]])]
    s1, m1 = _run_writer_obs(tmp_path, db_path, TS[4], obs1)
    assert s1 == STATUS_OK, m1
    assert _scalar(db_path, "SELECT COUNT(*) FROM open_positions") == 1
    # Run 2: append the exit bar -> exit + trade emitted from restart state.
    obs2 = obs1 + [_make_obs(TS[2], [], 3)]
    s2, m2 = _run_writer_obs(tmp_path, db_path, TS[4], obs2)
    assert s2 == STATUS_OK, m2
    assert _scalar(db_path, "SELECT COUNT(*) FROM trades") == 1
    assert _scalar(db_path, "SELECT COUNT(*) FROM ledger_batches") == 2
    return db_path


def _inject_trade(
    db_path: Path, *, gross: float, fees: float, funding: float, net: float
) -> int:
    """Inject a self-consistent (or deliberately inconsistent) trade event+row.

    The Phase 2 writer cannot currently emit trades (any exit trips its own
    "Orphan typed rows in fills" reconcile), so trade-path verification is
    exercised by injecting a trade keyed to an existing committed bar and
    patching the batch count + realized_gross accumulator so a *consistent*
    trade leaves the DB OK. Returns the new event seq.
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        for (name,) in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'"
        ).fetchall():
            conn.execute(f"DROP TRIGGER IF EXISTS {name}")
        bar_ts = TS[0]
        commit = conn.execute(
            "SELECT bar_commit_id FROM signal_snapshots WHERE bar_ts = ?", (bar_ts,)
        ).fetchone()[0]
        batch_id = conn.execute("SELECT batch_id FROM ledger_batches LIMIT 1").fetchone()[0]
        max_seq = conn.execute("SELECT MAX(seq) FROM ledger_events").fetchone()[0]
        cur = conn.execute(
            "INSERT INTO ledger_events (batch_id, event_type, event_key, recorded_at, "
            "bar_ts, symbol, prev_seq) VALUES (?, 'trade', 'injtrade', "
            "'2026-01-01T00:00:00', ?, ?, ?)",
            (batch_id, bar_ts, SYMBOL, max_seq),
        )
        seq = cur.lastrowid
        conn.execute(
            "INSERT INTO trades (seq, batch_id, trade_id, bar_commit_id, symbol, "
            "entry_fill_id, exit_fill_id, entry_bar_ts, exit_bar_ts, qty, entry_price, "
            "exit_price, gross_pnl, fees, funding, net_pnl, hold_bars, backfill) "
            "VALUES (?, ?, 'injtrade', ?, ?, 'e', 'x', ?, ?, 1.0, 100.0, 110.0, "
            "?, ?, ?, ?, 1, 0)",
            (seq, batch_id, commit, SYMBOL, bar_ts, bar_ts, gross, fees, funding, net),
        )
        conn.execute(
            "UPDATE ledger_batches SET event_count = event_count + 1, "
            "last_event_seq = ? WHERE batch_id = ?",
            (seq, batch_id),
        )
        conn.execute(
            "UPDATE ledger_state SET realized_gross = realized_gross + ? WHERE id = 1",
            (gross,),
        )
        conn.executescript(_TRIGGER_SQL)
        conn.commit()
        return seq
    finally:
        conn.close()


def _mutate(db_path: Path, sql: str, params: tuple = ()) -> None:
    """Mutate committed rows by dropping append-only triggers first.

    The verifier is read-only; this corruption helper uses a *separate* writer
    connection so tests can simulate a tampered/corrupt DB.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys=OFF")
        for (name,) in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'"
        ).fetchall():
            conn.execute(f"DROP TRIGGER IF EXISTS {name}")
        conn.execute(sql, params)
        # Restore append-only triggers so structural validation still passes — the
        # point of these fixtures is to corrupt *data*, not to strip the schema.
        conn.executescript(_TRIGGER_SQL)
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Test 1: PRE_START
# ---------------------------------------------------------------------------

class TestPreStart:
    def test_empty_db_is_pre_start(self, tmp_path: Path):
        db_path = _init_db(tmp_path)
        result = verify_database(db_path)
        assert result.status == STATUS_PRE_START, result.failures
        assert result.exit_code == 5

    def test_pre_start_no_failures(self, tmp_path: Path):
        db_path = _init_db(tmp_path)
        result = verify_database(db_path)
        assert result.failures == []


# ---------------------------------------------------------------------------
# Test 2: clean writer output verifies OK
# ---------------------------------------------------------------------------

class TestCleanOk:
    def test_clean_db_is_ok(self, tmp_path: Path):
        db_path = _clean_db(tmp_path)
        result = verify_database(db_path)
        assert result.status == V_STATUS_OK, result.failures
        assert result.exit_code == 0
        assert result.failures == []

    def test_report_contains_disclaimer(self, tmp_path: Path):
        db_path = _clean_db(tmp_path)
        result = verify_database(db_path)
        assert "does not independently rederive OHLCV" in result.report["disclaimer"]

    def test_funding_bearing_db_is_ok(self, tmp_path: Path):
        db_path = _funding_db(tmp_path)
        result = verify_database(db_path)
        assert result.status == V_STATUS_OK, result.failures
        # Sanity: this fixture really does carry funding rows.
        assert _scalar(db_path, "SELECT COUNT(*) FROM funding") >= 1

    def test_writer_produced_trade_is_ok(self, tmp_path: Path):
        # Real entry->exit->trade produced by the writer (not an injected trade).
        db_path = _trade_db(tmp_path)
        result = verify_database(db_path)
        assert result.status == V_STATUS_OK, result.failures

    def test_writer_produced_restart_trade_is_ok(self, tmp_path: Path):
        # Trade that spans two writer runs (restart exit) verifies OK.
        db_path = _restart_trade_db(tmp_path)
        result = verify_database(db_path)
        assert result.status == V_STATUS_OK, result.failures


# ---------------------------------------------------------------------------
# Test 3: read-only / query-only
# ---------------------------------------------------------------------------

class TestReadOnly:
    def test_query_only_reported_on(self, tmp_path: Path):
        db_path = _clean_db(tmp_path)
        result = verify_database(db_path)
        assert result.report["query_only"] == 1

    def test_verifier_connection_cannot_write(self, tmp_path: Path):
        db_path = _clean_db(tmp_path)
        conn = connect_readonly(db_path)
        try:
            with pytest.raises(sqlite3.OperationalError):
                conn.execute(
                    "INSERT INTO ledger_state (id, updated_at) VALUES (2, 'x')"
                )
        finally:
            conn.close()

    def test_verifier_creates_no_db_side_effects(self, tmp_path: Path):
        db_path = _clean_db(tmp_path)
        before = {p.name for p in db_path.parent.iterdir()}
        verify_database(db_path)
        after = {p.name for p in db_path.parent.iterdir()}
        # Only SQLite-managed db/wal/shm + paper_config.json allowed.
        assert after <= before | {
            "paper_ledger.db-wal",
            "paper_ledger.db-shm",
        }


# ---------------------------------------------------------------------------
# Test 4: bad DB identity -> CONFIG_ERROR
# ---------------------------------------------------------------------------

class TestBadIdentity:
    def test_missing_db_file(self, tmp_path: Path):
        result = verify_database(tmp_path / "nope.db")
        assert result.status == STATUS_CONFIG_ERROR

    def test_wrong_schema_version(self, tmp_path: Path):
        db_path = _clean_db(tmp_path)
        _mutate(db_path, "UPDATE paper_config SET db_schema_version = 99 WHERE id = 1")
        result = verify_database(db_path)
        assert result.status == STATUS_CONFIG_ERROR, result.failures

    def test_wrong_engine_version(self, tmp_path: Path):
        db_path = _clean_db(tmp_path)
        _mutate(
            db_path,
            "UPDATE paper_config SET paper_engine_version = '9.9.9' WHERE id = 1",
        )
        result = verify_database(db_path)
        assert result.status == STATUS_CONFIG_ERROR, result.failures

    def test_bad_config_hash(self, tmp_path: Path):
        db_path = _clean_db(tmp_path)
        _mutate(db_path, "UPDATE paper_config SET config_hash = 'deadbeef' WHERE id = 1")
        result = verify_database(db_path)
        assert result.status == STATUS_CONFIG_ERROR, result.failures

    def test_wrong_baseline_label(self, tmp_path: Path):
        db_path = _clean_db(tmp_path)
        _mutate(db_path, "UPDATE paper_config SET baseline_label = 'bogus' WHERE id = 1")
        result = verify_database(db_path)
        assert result.status == STATUS_CONFIG_ERROR, result.failures


# ---------------------------------------------------------------------------
# Test 5: event chain corruption -> CORRUPT
# ---------------------------------------------------------------------------

class TestEventChainCorruption:
    def test_broken_prev_seq(self, tmp_path: Path):
        db_path = _clean_db(tmp_path)
        # Break the chain: point a middle event's prev_seq at a bogus value.
        seqs = _seqs(db_path)
        mid = seqs[len(seqs) // 2]
        _mutate(db_path, "UPDATE ledger_events SET prev_seq = 999999 WHERE seq = ?", (mid,))
        result = verify_database(db_path)
        assert result.status == STATUS_CORRUPT, result.failures

    def test_first_event_prev_seq_not_null(self, tmp_path: Path):
        db_path = _clean_db(tmp_path)
        first = _seqs(db_path)[0]
        _mutate(db_path, "UPDATE ledger_events SET prev_seq = ? WHERE seq = ?", (first, first))
        result = verify_database(db_path)
        assert result.status == STATUS_CORRUPT, result.failures


# ---------------------------------------------------------------------------
# Test 6: event / typed-row mismatch -> CORRUPT
# ---------------------------------------------------------------------------

class TestEventTypeMismatch:
    def test_event_without_typed_row(self, tmp_path: Path):
        db_path = _clean_db(tmp_path)
        # Delete a fills typed row but keep its ledger_events 'fill' event.
        seq = _scalar(db_path, "SELECT seq FROM fills ORDER BY seq LIMIT 1")
        assert seq is not None, "fixture should have at least one fill"
        _mutate(db_path, "DELETE FROM fills WHERE seq = ?", (seq,))
        result = verify_database(db_path)
        assert result.status == STATUS_CORRUPT, result.failures

    def test_typed_row_without_event(self, tmp_path: Path):
        db_path = _clean_db(tmp_path)
        # Insert a stray fills row pointing at an equity event's seq.
        eq_seq = _scalar(db_path, "SELECT seq FROM equity_snapshots ORDER BY seq LIMIT 1")
        batch_id = _scalar(db_path, "SELECT batch_id FROM ledger_batches LIMIT 1")
        _mutate(
            db_path,
            """
            INSERT INTO fills (
                seq, batch_id, fill_id, bar_commit_id, signal_bar_ts, fill_ts,
                symbol, side, kind, qty, open_price, fill_price, slippage_bps, fee
            ) VALUES (?, ?, 'stray', 'x', ?, ?, 'AAAUSDT', 'BUY', 'entry',
                      1.0, 1.0, 1.0, 0.0, 0.0)
            """,
            (eq_seq, batch_id, TS[0], TS[1]),
        )
        result = verify_database(db_path)
        assert result.status == STATUS_CORRUPT, result.failures


# ---------------------------------------------------------------------------
# Test 7: batch count mismatch -> CORRUPT
# ---------------------------------------------------------------------------

class TestBatchCountMismatch:
    def test_event_count_mutated(self, tmp_path: Path):
        db_path = _clean_db(tmp_path)
        _mutate(db_path, "UPDATE ledger_batches SET event_count = event_count + 7")
        result = verify_database(db_path)
        assert result.status == STATUS_CORRUPT, result.failures

    def test_committed_bar_count_mutated(self, tmp_path: Path):
        db_path = _clean_db(tmp_path)
        _mutate(db_path, "UPDATE ledger_batches SET committed_bar_count = 999")
        result = verify_database(db_path)
        assert result.status == STATUS_CORRUPT, result.failures


# ---------------------------------------------------------------------------
# Test 8: fill fee corruption -> CORRUPT
# ---------------------------------------------------------------------------

class TestFillFeeCorruption:
    def test_fee_mutated(self, tmp_path: Path):
        db_path = _clean_db(tmp_path)
        seq = _scalar(db_path, "SELECT seq FROM fills ORDER BY seq LIMIT 1")
        _mutate(db_path, "UPDATE fills SET fee = fee + 1.0 WHERE seq = ?", (seq,))
        result = verify_database(db_path)
        assert result.status == STATUS_CORRUPT, result.failures


# ---------------------------------------------------------------------------
# Test 9: trade arithmetic corruption -> CORRUPT
# ---------------------------------------------------------------------------

class TestTradeCorruption:
    # All trade-lifecycle corruption is exercised against a WRITER-PRODUCED trade
    # (real entry/exit fills + funding ledger), so the verifier derives every
    # component instead of trusting the trade row's own fields.

    def test_net_pnl_mutated(self, tmp_path: Path):
        db_path = _trade_db(tmp_path)
        _mutate(db_path, "UPDATE trades SET net_pnl = net_pnl + 5.0")
        result = verify_database(db_path)
        assert result.status == STATUS_CORRUPT, result.failures

    def test_gross_pnl_mutated(self, tmp_path: Path):
        # Arbitrary gross that no longer matches (exit_price-entry_price)*qty.
        db_path = _trade_db(tmp_path)
        _mutate(db_path, "UPDATE trades SET gross_pnl = gross_pnl + 5.0, net_pnl = net_pnl + 5.0")
        result = verify_database(db_path)
        assert result.status == STATUS_CORRUPT, result.failures

    def test_funding_field_mutated(self, tmp_path: Path):
        # Arbitrary funding that no longer matches the funding-ledger aggregation.
        db_path = _trade_db(tmp_path)
        _mutate(db_path, "UPDATE trades SET funding = funding + 5.0, net_pnl = net_pnl - 5.0")
        result = verify_database(db_path)
        assert result.status == STATUS_CORRUPT, result.failures

    def test_fees_field_mutated(self, tmp_path: Path):
        # fees no longer equals entry_fee + exit_fee.
        db_path = _trade_db(tmp_path)
        _mutate(db_path, "UPDATE trades SET fees = fees + 5.0, net_pnl = net_pnl - 5.0")
        result = verify_database(db_path)
        assert result.status == STATUS_CORRUPT, result.failures

    def test_qty_mutated(self, tmp_path: Path):
        # Trade qty no longer matches the entry/exit fill qty.
        db_path = _trade_db(tmp_path)
        _mutate(db_path, "UPDATE trades SET qty = qty + 1.0")
        result = verify_database(db_path)
        assert result.status == STATUS_CORRUPT, result.failures

    def test_fake_entry_fill_id(self, tmp_path: Path):
        # entry_fill_id pointing at a non-existent fill must be CORRUPT.
        db_path = _trade_db(tmp_path)
        _mutate(db_path, "UPDATE trades SET entry_fill_id = 'nonexistent'")
        result = verify_database(db_path)
        assert result.status == STATUS_CORRUPT, result.failures
        assert any("not found in fills" in f for f in result.failures)

    def test_fake_exit_fill_id(self, tmp_path: Path):
        db_path = _trade_db(tmp_path)
        _mutate(db_path, "UPDATE trades SET exit_fill_id = 'nonexistent'")
        result = verify_database(db_path)
        assert result.status == STATUS_CORRUPT, result.failures
        assert any("not found in fills" in f for f in result.failures)

    def test_fabricated_trade_with_fake_fills(self, tmp_path: Path):
        # A self-consistent trade row keyed to a real bar but referencing fake
        # fill ids (the old "injected consistent trade") is now CORRUPT.
        db_path = _clean_db(tmp_path)
        _inject_trade(db_path, gross=10.0, fees=0.1, funding=0.05, net=9.85)
        result = verify_database(db_path)
        assert result.status == STATUS_CORRUPT, result.failures
        assert any("not found in fills" in f for f in result.failures)


# ---------------------------------------------------------------------------
# Test 10: funding corruption -> CORRUPT
# ---------------------------------------------------------------------------

class TestFundingCorruption:
    # Uses the real funding-bearing writer fixture (4 funding rows).
    def test_funding_amount_mutated(self, tmp_path: Path):
        db_path = _funding_db(tmp_path)
        _mutate(db_path, "UPDATE funding SET funding_amount = funding_amount + 0.5")
        result = verify_database(db_path)
        assert result.status == STATUS_CORRUPT, result.failures

    def test_funding_rate_mutated(self, tmp_path: Path):
        db_path = _funding_db(tmp_path)
        _mutate(
            db_path,
            "UPDATE funding SET funding_rate = funding_rate + 0.01 WHERE rate_available = 1",
        )
        result = verify_database(db_path)
        assert result.status == STATUS_CORRUPT, result.failures


# ---------------------------------------------------------------------------
# Test 11: equity corruption -> CORRUPT
# ---------------------------------------------------------------------------

class TestEquityCorruption:
    def test_equity_mutated(self, tmp_path: Path):
        db_path = _clean_db(tmp_path)
        seq = _scalar(db_path, "SELECT seq FROM equity_snapshots ORDER BY seq DESC LIMIT 1")
        _mutate(db_path, "UPDATE equity_snapshots SET equity = equity + 100 WHERE seq = ?", (seq,))
        result = verify_database(db_path)
        assert result.status == STATUS_CORRUPT, result.failures

    def test_drawdown_mutated(self, tmp_path: Path):
        db_path = _clean_db(tmp_path)
        seq = _scalar(db_path, "SELECT seq FROM equity_snapshots ORDER BY seq DESC LIMIT 1")
        _mutate(db_path, "UPDATE equity_snapshots SET drawdown = 0.5 WHERE seq = ?", (seq,))
        result = verify_database(db_path)
        assert result.status == STATUS_CORRUPT, result.failures


# ---------------------------------------------------------------------------
# Test 12: state corruption -> CORRUPT
# ---------------------------------------------------------------------------

class TestStateCorruption:
    def test_wrong_watermark(self, tmp_path: Path):
        db_path = _clean_db(tmp_path)
        _mutate(db_path, "UPDATE ledger_state SET watermark_bar_ts = '1999-01-01T00:00:00' WHERE id = 1")
        result = verify_database(db_path)
        assert result.status == STATUS_CORRUPT, result.failures

    def test_wrong_accumulator(self, tmp_path: Path):
        db_path = _clean_db(tmp_path)
        _mutate(db_path, "UPDATE ledger_state SET fees_cum = fees_cum + 123 WHERE id = 1")
        result = verify_database(db_path)
        assert result.status == STATUS_CORRUPT, result.failures

    def test_wrong_peak_equity(self, tmp_path: Path):
        db_path = _clean_db(tmp_path)
        _mutate(db_path, "UPDATE ledger_state SET peak_equity = peak_equity + 5000 WHERE id = 1")
        result = verify_database(db_path)
        assert result.status == STATUS_CORRUPT, result.failures


# ---------------------------------------------------------------------------
# Test 13: open positions corruption -> CORRUPT
# ---------------------------------------------------------------------------

class TestOpenPositionsCorruption:
    def _require_open(self, db_path: Path):
        if _scalar(db_path, "SELECT COUNT(*) FROM open_positions") == 0:
            pytest.skip("fixture produced no open positions")

    def test_wrong_qty(self, tmp_path: Path):
        db_path = _clean_db(tmp_path)
        self._require_open(db_path)
        _mutate(db_path, "UPDATE open_positions SET qty = qty + 1.0")
        result = verify_database(db_path)
        assert result.status == STATUS_CORRUPT, result.failures

    def test_wrong_entry_price(self, tmp_path: Path):
        db_path = _clean_db(tmp_path)
        self._require_open(db_path)
        _mutate(db_path, "UPDATE open_positions SET entry_price = entry_price + 1.0")
        result = verify_database(db_path)
        assert result.status == STATUS_CORRUPT, result.failures

    def test_wrong_entry_fill_id(self, tmp_path: Path):
        db_path = _clean_db(tmp_path)
        self._require_open(db_path)
        _mutate(db_path, "UPDATE open_positions SET entry_fill_id = 'bogus'")
        result = verify_database(db_path)
        assert result.status == STATUS_CORRUPT, result.failures

    def test_wrong_entry_bar_ts(self, tmp_path: Path):
        db_path = _clean_db(tmp_path)
        self._require_open(db_path)
        _mutate(db_path, "UPDATE open_positions SET entry_bar_ts = '1999-01-01T00:00:00'")
        result = verify_database(db_path)
        assert result.status == STATUS_CORRUPT, result.failures

    # NOTE: funding_accrued / hold_bars are intentionally NOT reconstructed by
    # the verifier — the Phase 2 writer does not persist them into open_positions
    # (it stores 0 from an entry/exit replay), so reconstructing them would flag
    # valid writer output as drift. See the verifier docstring + ADR Phase 4.


# ---------------------------------------------------------------------------
# Test 14: snapshot corruption -> CORRUPT
# ---------------------------------------------------------------------------

class TestSnapshotCorruption:
    def test_bar_commit_id_mutated(self, tmp_path: Path):
        db_path = _clean_db(tmp_path)
        seq = _scalar(db_path, "SELECT seq FROM signal_snapshots ORDER BY seq LIMIT 1")
        _mutate(
            db_path,
            "UPDATE signal_snapshots SET bar_commit_id = '0000000000000000' WHERE seq = ?",
            (seq,),
        )
        result = verify_database(db_path)
        assert result.status == STATUS_CORRUPT, result.failures

    def test_source_observation_digest_mutated(self, tmp_path: Path):
        db_path = _clean_db(tmp_path)
        seq = _scalar(db_path, "SELECT seq FROM signal_snapshots ORDER BY seq LIMIT 1")
        _mutate(
            db_path,
            "UPDATE signal_snapshots SET source_observation_digest = 'tampered' WHERE seq = ?",
            (seq,),
        )
        result = verify_database(db_path)
        assert result.status == STATUS_CORRUPT, result.failures

    def test_equity_bar_commit_id_mismatch(self, tmp_path: Path):
        db_path = _clean_db(tmp_path)
        seq = _scalar(db_path, "SELECT seq FROM equity_snapshots ORDER BY seq LIMIT 1")
        _mutate(
            db_path,
            "UPDATE equity_snapshots SET bar_commit_id = 'ffffffffffffffff' WHERE seq = ?",
            (seq,),
        )
        result = verify_database(db_path)
        assert result.status == STATUS_CORRUPT, result.failures


# ---------------------------------------------------------------------------
# Test 15: fill before forward_start_ts -> CORRUPT
# ---------------------------------------------------------------------------

class TestFillBeforeForwardStart:
    # NOTE: the forward-start floor is enforced on the *signal* bar (the bar that
    # produced the order), matching the Phase 2 writer reconcile check. The T+1
    # fill timestamp is not floored (it can legitimately precede the signal bar in
    # synthetic/out-of-order data), so only signal_bar_ts is asserted here.
    def test_signal_bar_ts_before_forward_start(self, tmp_path: Path):
        db_path = _clean_db(tmp_path)
        seq = _scalar(db_path, "SELECT seq FROM fills ORDER BY seq LIMIT 1")
        _mutate(
            db_path,
            "UPDATE fills SET signal_bar_ts = '1999-01-01T00:00:00' WHERE seq = ?",
            (seq,),
        )
        result = verify_database(db_path)
        assert result.status == STATUS_CORRUPT, result.failures


# ---------------------------------------------------------------------------
# Test 16: CLI
# ---------------------------------------------------------------------------

class TestCli:
    def _run(self, *args: str):
        return subprocess.run(
            [sys.executable, "scripts/qnty-paper-sqlite-verify.py", *args],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )

    def test_help_exits_zero(self):
        r = self._run("--help")
        assert r.returncode == 0
        assert "usage" in r.stdout.lower()
        assert "Traceback" not in r.stderr

    def test_cli_pre_start_exit_5(self, tmp_path: Path):
        db_path = _init_db(tmp_path)
        r = self._run("--db-path", str(db_path))
        assert r.returncode == 5, r.stdout + r.stderr
        assert "Traceback" not in r.stderr

    def test_cli_clean_exit_0(self, tmp_path: Path):
        db_path = _clean_db(tmp_path)
        r = self._run("--db-path", str(db_path))
        assert r.returncode == 0, r.stdout + r.stderr
        assert "Traceback" not in r.stderr

    def test_cli_corrupt_exit_4(self, tmp_path: Path):
        db_path = _clean_db(tmp_path)
        _mutate(db_path, "UPDATE ledger_state SET fees_cum = fees_cum + 999 WHERE id = 1")
        r = self._run("--db-path", str(db_path))
        assert r.returncode == 4, r.stdout + r.stderr
        assert "Traceback" not in r.stderr

    def test_cli_json_mode(self, tmp_path: Path):
        db_path = _clean_db(tmp_path)
        r = self._run("--db-path", str(db_path), "--json")
        assert r.returncode == 0, r.stdout + r.stderr
        payload = json.loads(r.stdout)
        assert payload["status"] == "OK"
        assert payload["exit_code"] == 0


# ---------------------------------------------------------------------------
# Test 17: no artifacts
# ---------------------------------------------------------------------------

class TestNoArtifacts:
    def test_no_jsonl_or_report_files(self, tmp_path: Path):
        db_path = _clean_db(tmp_path)
        verify_database(db_path)
        paper_dir = db_path.parent
        assert list(paper_dir.glob("*.jsonl")) == []
        for f in paper_dir.iterdir():
            if f.is_file():
                assert f.name.endswith(".db") or f.name.endswith(".db-wal") or \
                    f.name.endswith(".db-shm") or f.name == "paper_config.json", (
                    f"Unexpected artifact: {f.name}"
                )


# ---------------------------------------------------------------------------
# Test 18: PRE_START hardening — corrupt pre-start state / empty committed batch
# ---------------------------------------------------------------------------

class TestPreStartHardening:
    def test_corrupt_pre_start_state_is_corrupt(self, tmp_path: Path):
        # Empty ledger, but ledger_state is NOT a valid initial singleton.
        db_path = _init_db(tmp_path)
        _mutate(db_path, "UPDATE ledger_state SET realized_gross = 123.0 WHERE id = 1")
        result = verify_database(db_path)
        assert result.status == STATUS_CORRUPT, result.failures

    def test_corrupt_pre_start_watermark_is_corrupt(self, tmp_path: Path):
        db_path = _init_db(tmp_path)
        _mutate(
            db_path,
            "UPDATE ledger_state SET watermark_bar_ts = '2026-01-01T00:00:00' WHERE id = 1",
        )
        result = verify_database(db_path)
        assert result.status == STATUS_CORRUPT, result.failures

    def test_committed_empty_batch_is_corrupt(self, tmp_path: Path):
        # A committed ledger_batches row with no events is corruption, not OK.
        db_path = _init_db(tmp_path)
        _mutate(
            db_path,
            "INSERT INTO ledger_batches (created_at, committed_at, event_count, "
            "committed_bar_count, paper_engine_version, config_hash) "
            "SELECT 'now', 'now', 0, 0, paper_engine_version, config_hash "
            "FROM paper_config WHERE id = 1",
        )
        result = verify_database(db_path)
        assert result.status == STATUS_CORRUPT, result.failures
        assert any("zero events" in f for f in result.failures)


# ---------------------------------------------------------------------------
# Test 19: event <-> typed-row relationship consistency
# ---------------------------------------------------------------------------

class TestEventTypedConsistency:
    def test_event_key_mismatch(self, tmp_path: Path):
        db_path = _clean_db(tmp_path)
        _mutate(
            db_path,
            "UPDATE ledger_events SET event_key = 'tampered' WHERE event_type = 'fill'",
        )
        result = verify_database(db_path)
        assert result.status == STATUS_CORRUPT, result.failures

    def test_event_batch_mismatch(self, tmp_path: Path):
        db_path = _clean_db(tmp_path)
        # Add a second valid batch row so FK stays satisfied, then point the
        # fill's typed row at it while its event keeps the original batch_id.
        _mutate(
            db_path,
            "INSERT INTO ledger_batches (created_at, committed_at, event_count, "
            "committed_bar_count, paper_engine_version, config_hash) "
            "SELECT 'now', 'now', 1, 1, paper_engine_version, config_hash "
            "FROM paper_config WHERE id = 1",
        )
        new_batch = _scalar(db_path, "SELECT MAX(batch_id) FROM ledger_batches")
        _mutate(db_path, "UPDATE fills SET batch_id = ?", (new_batch,))
        result = verify_database(db_path)
        assert result.status == STATUS_CORRUPT, result.failures

    def test_event_symbol_mismatch(self, tmp_path: Path):
        db_path = _clean_db(tmp_path)
        _mutate(db_path, "UPDATE fills SET symbol = 'ZZZUSDT'")
        result = verify_database(db_path)
        assert result.status == STATUS_CORRUPT, result.failures

    def test_event_bar_mismatch(self, tmp_path: Path):
        db_path = _clean_db(tmp_path)
        # Move an equity row's bar_ts: event_key (eq|<bar>) and event.bar_ts no
        # longer match the typed row.
        seq = _scalar(db_path, "SELECT seq FROM equity_snapshots ORDER BY seq LIMIT 1")
        _mutate(
            db_path,
            "UPDATE equity_snapshots SET bar_ts = '2099-01-01T00:00:00' WHERE seq = ?",
            (seq,),
        )
        result = verify_database(db_path)
        assert result.status == STATUS_CORRUPT, result.failures


# ---------------------------------------------------------------------------
# Test 20: position_snapshot / position_snapshot_symbols validation
# ---------------------------------------------------------------------------

class TestPositionSnapshots:
    def test_funding_db_has_child_rows(self, tmp_path: Path):
        db_path = _funding_db(tmp_path)
        assert _scalar(db_path, "SELECT COUNT(*) FROM position_snapshot_symbols") >= 1

    def test_wrong_child_symbol(self, tmp_path: Path):
        db_path = _funding_db(tmp_path)
        _mutate(db_path, "UPDATE position_snapshot_symbols SET symbol = 'ZZZUSDT'")
        result = verify_database(db_path)
        assert result.status == STATUS_CORRUPT, result.failures

    def test_wrong_child_qty(self, tmp_path: Path):
        db_path = _funding_db(tmp_path)
        _mutate(db_path, "UPDATE position_snapshot_symbols SET qty = qty + 1.0")
        result = verify_database(db_path)
        assert result.status == STATUS_CORRUPT, result.failures

    def test_missing_child_row(self, tmp_path: Path):
        db_path = _funding_db(tmp_path)
        seq = _scalar(
            db_path, "SELECT snapshot_seq FROM position_snapshot_symbols LIMIT 1"
        )
        _mutate(
            db_path,
            "DELETE FROM position_snapshot_symbols WHERE snapshot_seq = ?",
            (seq,),
        )
        result = verify_database(db_path)
        assert result.status == STATUS_CORRUPT, result.failures

    def test_wrong_num_open(self, tmp_path: Path):
        db_path = _funding_db(tmp_path)
        seq = _scalar(
            db_path,
            "SELECT seq FROM position_snapshots WHERE num_open > 0 ORDER BY seq LIMIT 1",
        )
        _mutate(db_path, "UPDATE position_snapshots SET num_open = 99 WHERE seq = ?", (seq,))
        result = verify_database(db_path)
        assert result.status == STATUS_CORRUPT, result.failures


# ---------------------------------------------------------------------------
# Test 21: equity cumulative reconciliation (coordinated mutation)
# ---------------------------------------------------------------------------

class TestEquityCumulative:
    def test_coordinated_realized_equity_peak_mutation(self, tmp_path: Path):
        # Bump realized_gross_pnl + equity together (keeps the row internally
        # self-consistent) AND peak in ledger_state. The recompute-from-trades
        # still catches it because realized is rederived from the trade ledger.
        db_path = _trade_db(tmp_path)
        seq = _scalar(db_path, "SELECT seq FROM equity_snapshots ORDER BY seq DESC LIMIT 1")
        _mutate(
            db_path,
            "UPDATE equity_snapshots SET realized_gross_pnl = realized_gross_pnl + 50.0, "
            "equity = equity + 50.0 WHERE seq = ?",
            (seq,),
        )
        _mutate(db_path, "UPDATE ledger_state SET peak_equity = peak_equity + 50.0 WHERE id = 1")
        result = verify_database(db_path)
        assert result.status == STATUS_CORRUPT, result.failures

    def test_fees_cum_field_mutation(self, tmp_path: Path):
        db_path = _trade_db(tmp_path)
        seq = _scalar(db_path, "SELECT seq FROM equity_snapshots ORDER BY seq DESC LIMIT 1")
        _mutate(
            db_path,
            "UPDATE equity_snapshots SET fees_cum = fees_cum + 10.0, "
            "equity = equity - 10.0 WHERE seq = ?",
            (seq,),
        )
        result = verify_database(db_path)
        assert result.status == STATUS_CORRUPT, result.failures


# ---------------------------------------------------------------------------
# Test 22: open_positions restart fields (funding_accrued / hold_bars / entry_fee)
# ---------------------------------------------------------------------------

class TestOpenPositionsRestartFields:
    def test_funding_db_open_position_has_accrual(self, tmp_path: Path):
        db_path = _funding_db(tmp_path)
        row = _scalar(
            db_path, "SELECT funding_accrued FROM open_positions LIMIT 1"
        )
        assert row is not None and abs(row) > 0.0

    def test_wrong_funding_accrued(self, tmp_path: Path):
        db_path = _funding_db(tmp_path)
        _mutate(db_path, "UPDATE open_positions SET funding_accrued = funding_accrued + 1.0")
        result = verify_database(db_path)
        assert result.status == STATUS_CORRUPT, result.failures

    def test_wrong_hold_bars(self, tmp_path: Path):
        db_path = _funding_db(tmp_path)
        _mutate(db_path, "UPDATE open_positions SET hold_bars = hold_bars + 5")
        result = verify_database(db_path)
        assert result.status == STATUS_CORRUPT, result.failures

    def test_wrong_entry_fee(self, tmp_path: Path):
        db_path = _funding_db(tmp_path)
        _mutate(db_path, "UPDATE open_positions SET entry_fee = entry_fee + 1.0")
        result = verify_database(db_path)
        assert result.status == STATUS_CORRUPT, result.failures


# ---------------------------------------------------------------------------
# Test 23: malformed DB does not traceback
# ---------------------------------------------------------------------------

class TestMalformedDb:
    def test_non_sqlite_file_is_config_error(self, tmp_path: Path):
        bogus = tmp_path / "not_a_db.db"
        bogus.write_text("this is not a sqlite database", encoding="utf-8")
        result = verify_database(bogus)
        assert result.status == STATUS_CONFIG_ERROR, result.failures

    def test_cli_non_sqlite_file_no_traceback(self, tmp_path: Path):
        bogus = tmp_path / "not_a_db.db"
        bogus.write_text("garbage bytes not sqlite", encoding="utf-8")
        r = subprocess.run(
            [sys.executable, "scripts/qnty-paper-sqlite-verify.py", "--db-path", str(bogus)],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        assert r.returncode == 3, r.stdout + r.stderr
        assert "Traceback" not in r.stderr


# ---------------------------------------------------------------------------
# Shared scalar/seq helpers (read-only)
# ---------------------------------------------------------------------------

def _scalar(db_path: Path, sql: str, params: tuple = ()):
    conn = connect_readonly(db_path)
    try:
        row = conn.execute(sql, params).fetchone()
        return None if row is None else row[0]
    finally:
        conn.close()


def _seqs(db_path: Path) -> list[int]:
    conn = connect_readonly(db_path)
    try:
        return [r[0] for r in conn.execute("SELECT seq FROM ledger_events ORDER BY seq").fetchall()]
    finally:
        conn.close()
