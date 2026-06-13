"""Tests for paper-ledger SQLite substrate (Phase 1).

Covers:
- DB initialisation and schema creation
- PRAGMA verification (WAL, synchronous, foreign_keys)
- SQLite version gate
- Append-only trigger enforcement
- Mutable-state tables (ledger_state, open_positions)
- Read-only connection behaviour
- Concurrent-writer exclusion (LEDGER_BUSY)
- Transaction rollback
- config_hash stability
- Legacy-artifact and existing-DB refusal
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Allow running from repo root without installing
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from quantbot.paper.config import build_config, config_hash
from quantbot.paper.db import (
    DB_SCHEMA_VERSION,
    DEFAULT_DB_PATH,
    PAPER_ENGINE_VERSION,
    _APPEND_ONLY_TABLES,
    _legacy_artifact_paths,
    assert_sqlite_capabilities,
    config_hash_from_row,
    connect_readonly,
    connect_writer,
    get_paper_db_path,
    initialize_database,
    validate_database_identity,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _init_tmp_db(tmp_path: Path) -> Path:
    """Create a fresh DB in *tmp_path* and return the path."""
    db_path = tmp_path / "paper_ledger.db"
    config = build_config(forward_start_ts="2026-06-09T00:00:00")
    initialize_database(db_path, config)
    return db_path


def _sqlite_version_tuple() -> tuple:
    return tuple(int(p) for p in sqlite3.sqlite_version.split(".") if p.isdigit())


# ---------------------------------------------------------------------------
# Test 1: Init creates DB with correct PRAGMAs
# ---------------------------------------------------------------------------

class TestInitCreatesDBWithPragmas:
    def test_wal_mode(self, tmp_path: Path):
        db_path = _init_tmp_db(tmp_path)
        conn = connect_writer(db_path)
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        conn.close()
        assert mode.upper() == "WAL"

    def test_synchronous_full(self, tmp_path: Path):
        db_path = _init_tmp_db(tmp_path)
        conn = connect_writer(db_path)
        synch = conn.execute("PRAGMA synchronous").fetchone()[0]
        conn.close()
        # FULL = 2 in SQLite pragma synchronous
        assert synch == 2

    def test_foreign_keys_on_in_writer(self, tmp_path: Path):
        """foreign_keys pragma is connection-local; verify on a writer conn."""
        db_path = _init_tmp_db(tmp_path)
        conn = connect_writer(db_path)
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        conn.close()
        assert fk == 1


# ---------------------------------------------------------------------------
# Test 2: SQLite version gate
# ---------------------------------------------------------------------------

class TestSQLiteVersionGate:
    def test_version_too_low_raises(self):
        conn = sqlite3.connect(":memory:")
        with patch("quantbot.paper.db._sqlite_version_info", return_value=(3, 36, 0)):
            with pytest.raises(RuntimeError, match="requires >= 3.37"):
                assert_sqlite_capabilities(conn)
        conn.close()

    def test_version_exact_minimum_passes(self):
        conn = sqlite3.connect(":memory:")
        with patch("quantbot.paper.db._sqlite_version_info", return_value=(3, 37, 0)):
            assert_sqlite_capabilities(conn)  # should not raise
        conn.close()

    def test_version_above_minimum_passes(self):
        conn = sqlite3.connect(":memory:")
        with patch("quantbot.paper.db._sqlite_version_info", return_value=(3, 45, 1)):
            assert_sqlite_capabilities(conn)  # should not raise
        conn.close()


# ---------------------------------------------------------------------------
# Test 3: DB init refuses existing DB
# ---------------------------------------------------------------------------

class TestInitRefusesExistingDB:
    def test_existing_db_raises(self, tmp_path: Path):
        db_path = tmp_path / "paper_ledger.db"
        db_path.write_text("stale")
        config = build_config(forward_start_ts="2026-06-09T00:00:00")
        with pytest.raises(FileExistsError, match="already exists"):
            initialize_database(db_path, config)


# ---------------------------------------------------------------------------
# Test 4: DB init refuses legacy artifacts
# ---------------------------------------------------------------------------

class TestInitRefusesLegacyArtifacts:
    def test_legacy_config_json_detected(self, tmp_path: Path):
        (tmp_path / "paper_config.json").write_text("{}")
        found = _legacy_artifact_paths(tmp_path)
        assert any(p.name == "paper_config.json" for p in found)

    def test_legacy_fills_jsonl_detected(self, tmp_path: Path):
        (tmp_path / "paper_fills.jsonl").write_text("\n")
        found = _legacy_artifact_paths(tmp_path)
        assert any(p.name == "paper_fills.jsonl" for p in found)

    def test_no_legacy_in_empty_dir(self, tmp_path: Path):
        found = _legacy_artifact_paths(tmp_path)
        assert found == []


# ---------------------------------------------------------------------------
# Test 5: paper_config inserted and immutable
# ---------------------------------------------------------------------------

class TestPaperConfigInsertedAndImmutable:
    def test_config_row_present(self, tmp_path: Path):
        db_path = _init_tmp_db(tmp_path)
        conn = connect_readonly(db_path)
        row = conn.execute("SELECT * FROM paper_config WHERE id = 1").fetchone()
        conn.close()
        assert row is not None
        assert row["paper_engine_version"] == PAPER_ENGINE_VERSION

    def test_config_update_raises(self, tmp_path: Path):
        db_path = _init_tmp_db(tmp_path)
        conn = connect_writer(db_path)
        with pytest.raises(sqlite3.Error, match="append-only"):
            conn.execute(
                "UPDATE paper_config SET paper_engine_version = '99.0.0' WHERE id = 1"
            )
        conn.close()

    def test_config_delete_raises(self, tmp_path: Path):
        db_path = _init_tmp_db(tmp_path)
        conn = connect_writer(db_path)
        with pytest.raises(sqlite3.Error, match="append-only"):
            conn.execute("DELETE FROM paper_config WHERE id = 1")
        conn.close()


# ---------------------------------------------------------------------------
# Test 6: Append-only UPDATE/DELETE triggers abort
# ---------------------------------------------------------------------------

class TestAppendOnlyTriggers:
    APPEND_ONLY = ["paper_config"]

    @pytest.mark.parametrize("tbl", APPEND_ONLY)
    def test_update_aborts(self, tbl: str, tmp_path: Path):
        db_path = _init_tmp_db(tmp_path)
        conn = connect_writer(db_path)
        with pytest.raises(sqlite3.Error, match="append-only"):
            conn.execute("UPDATE paper_config SET paper_engine_version = 'X'")
        conn.close()

    def test_ledger_batches_update_succeeds(self, tmp_path: Path):
        """ledger_batches is now mutable (updated after commit)."""
        db_path = _init_tmp_db(tmp_path)
        conn = connect_writer(db_path)
        conn.execute(
            "INSERT INTO ledger_batches (created_at, event_count, paper_engine_version, config_hash) "
            "VALUES ('2026-01-01T00:00:00Z', 0, '0.3.0', 'dummy')"
        )
        conn.commit()
        # Should NOT raise - ledger_batches is mutable
        conn.execute("UPDATE ledger_batches SET created_at = 'X'")
        conn.commit()
        conn.close()

    def test_fills_update_aborts(self, tmp_path: Path):
        db_path = _init_tmp_db(tmp_path)
        conn = connect_writer(db_path)
        conn.execute(
            "INSERT INTO ledger_batches (created_at, event_count, paper_engine_version, config_hash) "
            "VALUES ('2026-01-01T00:00:00Z', 0, '0.3.0', 'dummy')"
        )
        conn.execute(
            "INSERT INTO ledger_events (batch_id, event_type, event_key, recorded_at) "
            "VALUES (1, 'fill', 'test_fill', '2026-01-01T00:00:00Z')"
        )
        conn.execute(
            "INSERT INTO fills (seq, batch_id, fill_id, bar_commit_id, signal_bar_ts, fill_ts, "
            "symbol, side, kind, qty, open_price, fill_price, slippage_bps, fee, backfill) "
            "VALUES (1, 1, 'f1', 'c1', '2026-01-01T00:00:00Z', '2026-01-01T08:00:00Z', "
            "'BTCUSDT', 'BUY', 'entry', 0.01, 100000.0, 100005.0, 5.0, 50.0, 0)"
        )
        conn.commit()
        with pytest.raises(sqlite3.Error, match="append-only"):
            conn.execute("UPDATE fills SET fill_price = 0")
        conn.close()

    def test_equity_snapshots_update_aborts(self, tmp_path: Path):
        db_path = _init_tmp_db(tmp_path)
        conn = connect_writer(db_path)
        conn.execute(
            "INSERT INTO ledger_batches (created_at, event_count, paper_engine_version, config_hash) "
            "VALUES ('2026-01-01T00:00:00Z', 0, '0.3.0', 'dummy')"
        )
        conn.execute(
            "INSERT INTO ledger_events (batch_id, event_type, event_key, recorded_at) "
            "VALUES (1, 'equity_snapshot', 'eq_2026-01-01', '2026-01-01T00:00:00Z')"
        )
        conn.execute(
            "INSERT INTO equity_snapshots (seq, batch_id, bar_ts, bar_commit_id, "
            "realized_gross_pnl, unrealized_pnl, funding_cum, fees_cum, equity, drawdown, num_open) "
            "VALUES (1, 1, '2026-01-01T00:00:00Z', 'c1', 0.0, 0.0, 0.0, 0.0, 10000.0, 0.0, 0)"
        )
        conn.commit()
        with pytest.raises(sqlite3.Error, match="append-only"):
            conn.execute("UPDATE equity_snapshots SET equity = 0")
        conn.close()


# ---------------------------------------------------------------------------
# Test 7: ledger_state / open_positions are NOT append-only
# ---------------------------------------------------------------------------

class TestMutableStateNotAppendOnly:
    def test_ledger_state_update_succeeds(self, tmp_path: Path):
        db_path = _init_tmp_db(tmp_path)
        conn = connect_writer(db_path)
        conn.execute(
            "UPDATE ledger_state SET watermark_bar_ts = '2026-01-01T00:00:00Z', updated_at = 'now'"
        )
        conn.commit()
        row = conn.execute("SELECT watermark_bar_ts FROM ledger_state WHERE id = 1").fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "2026-01-01T00:00:00Z"

    def test_open_positions_insert_and_update(self, tmp_path: Path):
        db_path = _init_tmp_db(tmp_path)
        conn = connect_writer(db_path)
        conn.execute(
            "INSERT INTO open_positions (symbol, entry_fill_id, entry_price, qty, "
            "entry_bar_ts, entry_fill_ts, funding_accrued, hold_bars) "
            "VALUES ('BTCUSDT', 'f1', 100000.0, 0.01, '2026-01-01T00:00:00Z', "
            "'2026-01-01T08:00:00Z', 0.0, 1)"
        )
        conn.execute(
            "UPDATE open_positions SET funding_accrued = 12.34 WHERE symbol = 'BTCUSDT'"
        )
        conn.commit()
        row = conn.execute(
            "SELECT funding_accrued FROM open_positions WHERE symbol = 'BTCUSDT'"
        ).fetchone()
        conn.close()
        assert row is not None
        assert abs(row[0] - 12.34) < 1e-6


# ---------------------------------------------------------------------------
# Test 8: Read-only connection cannot write
# ---------------------------------------------------------------------------

class TestReadOnlyConnection:
    def test_write_raises_error(self, tmp_path: Path):
        db_path = _init_tmp_db(tmp_path)
        conn = connect_readonly(db_path)
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("CREATE TABLE should_fail (x INTEGER)")
        conn.close()

    def test_query_only_pragma_set(self, tmp_path: Path):
        db_path = _init_tmp_db(tmp_path)
        conn = connect_readonly(db_path)
        val = conn.execute("PRAGMA query_only").fetchone()[0]
        conn.close()
        assert val == 1

    def test_read_works(self, tmp_path: Path):
        db_path = _init_tmp_db(tmp_path)
        conn = connect_readonly(db_path)
        row = conn.execute("SELECT paper_engine_version FROM paper_config WHERE id = 1").fetchone()
        conn.close()
        assert row is not None
        assert row[0] == PAPER_ENGINE_VERSION


# ---------------------------------------------------------------------------
# Test 9: Second writer BEGIN IMMEDIATE fails as LEDGER_BUSY
# ---------------------------------------------------------------------------

class TestSecondWriterBusy:
    def test_concurrent_writer_raises_busy(self, tmp_path: Path):
        db_path = _init_tmp_db(tmp_path)
        writer1 = connect_writer(db_path, timeout=1.0)
        writer1.execute("BEGIN IMMEDIATE")
        writer2 = connect_writer(db_path, timeout=1.0)
        with pytest.raises(sqlite3.OperationalError, match="database is locked|busy"):
            writer2.execute("BEGIN IMMEDIATE")
        writer1.execute("ROLLBACK")
        writer1.close()
        writer2.close()


# ---------------------------------------------------------------------------
# Test 10: Transaction rollback
# ---------------------------------------------------------------------------

class TestTransactionRollback:
    def test_rollback_leaves_no_batch(self, tmp_path: Path):
        db_path = _init_tmp_db(tmp_path)
        conn = connect_writer(db_path)
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT INTO ledger_batches (created_at, event_count, paper_engine_version, config_hash) "
            "VALUES ('2026-01-01T00:00:00Z', 0, '0.3.0', 'dummy')"
        )
        conn.rollback()
        count = conn.execute("SELECT COUNT(*) FROM ledger_batches").fetchone()[0]
        conn.close()
        assert count == 0


# ---------------------------------------------------------------------------
# Test 11: Simple committed insert
# ---------------------------------------------------------------------------

class TestCommittedInsert:
    def test_insert_and_commit_visible(self, tmp_path: Path):
        db_path = _init_tmp_db(tmp_path)
        conn = connect_writer(db_path)
        conn.execute(
            "INSERT INTO ledger_batches (created_at, event_count, paper_engine_version, config_hash) "
            "VALUES ('2026-01-01T00:00:00Z', 0, '0.3.0', 'dummy')"
        )
        conn.commit()
        ro = connect_readonly(db_path)
        count = ro.execute("SELECT COUNT(*) FROM ledger_batches").fetchone()[0]
        ro.close()
        conn.close()
        assert count == 1


# ---------------------------------------------------------------------------
# Test 12: First event may have prev_seq NULL
# ---------------------------------------------------------------------------

class TestFirstEventPrevSeqNull:
    def test_prev_seq_null_allowed(self, tmp_path: Path):
        db_path = _init_tmp_db(tmp_path)
        conn = connect_writer(db_path)
        conn.execute(
            "INSERT INTO ledger_batches (created_at, event_count, paper_engine_version, config_hash) "
            "VALUES ('2026-01-01T00:00:00Z', 0, '0.3.0', 'dummy')"
        )
        conn.execute(
            "INSERT INTO ledger_events (batch_id, event_type, event_key, recorded_at, prev_seq) "
            "VALUES (1, 'signal_snapshot', 'snap_2026-01-01', '2026-01-01T00:00:00Z', NULL)"
        )
        conn.commit()
        row = conn.execute("SELECT prev_seq FROM ledger_events WHERE seq = 1").fetchone()
        conn.close()
        assert row is not None
        assert row[0] is None


# ---------------------------------------------------------------------------
# Test 13: Verifier-like query sees consistent snapshot
# ---------------------------------------------------------------------------

class TestVerifierConsistentSnapshot:
    def test_repeatable_read(self, tmp_path: Path):
        db_path = _init_tmp_db(tmp_path)
        ro = connect_readonly(db_path)
        v1 = ro.execute("SELECT paper_engine_version FROM paper_config WHERE id = 1").fetchone()[0]
        v2 = ro.execute("SELECT paper_engine_version FROM paper_config WHERE id = 1").fetchone()[0]
        ro.close()
        assert v1 == v2 == PAPER_ENGINE_VERSION


# ---------------------------------------------------------------------------
# Test 14: config_hash excludes itself, stable/deterministic
# ---------------------------------------------------------------------------

class TestConfigHashStable:
    def test_hash_excludes_config_hash_field(self, tmp_path: Path):
        db_path = _init_tmp_db(tmp_path)
        conn = connect_readonly(db_path)
        row = conn.execute("SELECT * FROM paper_config WHERE id = 1").fetchone()
        cfg = dict(row)
        stored = cfg.pop("config_hash")
        recomputed = config_hash_from_row(cfg)
        conn.close()
        assert stored == recomputed, f"stored={stored!r} != recomputed={recomputed!r}"

    def test_hash_deterministic(self, tmp_path: Path):
        config = build_config(forward_start_ts="2026-06-09T00:00:00")
        h1 = config["config_hash"]
        # Re-build config with same args; hash must be identical
        config2 = build_config(forward_start_ts="2026-06-09T00:00:00")
        assert h1 == config2["config_hash"]


# ---------------------------------------------------------------------------
# Test 15: No DB files in repo root
# ---------------------------------------------------------------------------

class TestNoDBFilesInRepoRoot:
    def test_tmp_path_not_repo_root(self, tmp_path: Path):
        repo_root = Path.cwd()
        db_path = tmp_path / "test.db"
        db_path.write_text("test")
        assert db_path.exists()
        # Ensure we don't accidentally write to repo root
        assert not (repo_root / "paper_ledger.db").exists()


# ---------------------------------------------------------------------------
# Additional: validate_database_identity
# ---------------------------------------------------------------------------

class TestValidateDatabaseIdentity:
    def test_valid_db_passes(self, tmp_path: Path):
        db_path = _init_tmp_db(tmp_path)
        conn = connect_readonly(db_path)
        cfg = validate_database_identity(conn)
        conn.close()
        assert cfg["db_schema_version"] == DB_SCHEMA_VERSION
        assert cfg["paper_engine_version"] == PAPER_ENGINE_VERSION

    def test_wrong_engine_version_fails(self, tmp_path: Path):
        db_path = _init_tmp_db(tmp_path)
        # Bypass append-only trigger by using raw sqlite3 connection.
        # The trigger prevents UPDATE on paper_config, so we temporarily
        # drop the trigger, update the version, then re-create the trigger.
        raw = sqlite3.connect(str(db_path))
        raw.execute("DROP TRIGGER IF EXISTS trg_paper_config_deny_update")
        raw.execute(
            "UPDATE paper_config SET paper_engine_version = '99.0.0' WHERE id = 1"
        )
        # Re-create the append-only trigger for consistency
        raw.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_paper_config_deny_update
            BEFORE UPDATE ON paper_config
            BEGIN
                SELECT RAISE(ABORT, 'Table paper_config is append-only — UPDATE not permitted');
            END;
            """
        )
        raw.commit()
        raw.close()

        # Now validate_database_identity should raise ValueError
        conn = connect_readonly(db_path)
        with pytest.raises(ValueError, match="paper_engine_version mismatch"):
            validate_database_identity(conn)
        conn.close()


# ---------------------------------------------------------------------------
# Test 16: Initial ledger_state singleton row exists after init
# ---------------------------------------------------------------------------

class TestLedgerStateSingletonRow:
    def test_ledger_state_row_exists(self, tmp_path: Path):
        db_path = _init_tmp_db(tmp_path)
        conn = connect_readonly(db_path)
        row = conn.execute("SELECT id, watermark_bar_ts FROM ledger_state WHERE id = 1").fetchone()
        conn.close()
        assert row is not None
        assert row[0] == 1
        # watermark_bar_ts is NULL initially (set on first batch)
        assert row[1] is None

    def test_ledger_state_only_one_row(self, tmp_path: Path):
        db_path = _init_tmp_db(tmp_path)
        conn = connect_readonly(db_path)
        count = conn.execute("SELECT COUNT(*) FROM ledger_state").fetchone()[0]
        conn.close()
        assert count == 1


# ---------------------------------------------------------------------------
# Test 17: ledger_batches is now MUTABLE (not append-only)
# ---------------------------------------------------------------------------

class TestLedgerBatchesMutable:
    """ledger_batches is now mutable (updated after commit)."""
    def test_update_succeeds(self, tmp_path: Path):
        db_path = _init_tmp_db(tmp_path)
        conn = connect_writer(db_path)
        conn.execute(
            "INSERT INTO ledger_batches (created_at, event_count, paper_engine_version, config_hash) "
            "VALUES ('2026-01-01T00:00:00Z', 0, '0.3.0', 'dummy')"
        )
        conn.commit()
        # Should NOT raise - ledger_batches is mutable
        conn.execute("UPDATE ledger_batches SET created_at = 'X' WHERE batch_id = 1")
        conn.commit()
        conn.close()

    def test_delete_succeeds(self, tmp_path: Path):
        db_path = _init_tmp_db(tmp_path)
        conn = connect_writer(db_path)
        conn.execute(
            "INSERT INTO ledger_batches (created_at, event_count, paper_engine_version, config_hash) "
            "VALUES ('2026-01-01T00:00:00Z', 0, '0.3.0', 'dummy')"
        )
        conn.commit()
        # Should NOT raise - ledger_batches is mutable
        conn.execute("DELETE FROM ledger_batches WHERE batch_id = 1")
        conn.commit()
        conn.close()


# ---------------------------------------------------------------------------
# Test 18: Append-only DELETE triggers on untested historical tables
# ---------------------------------------------------------------------------

class TestAppendOnlyDeleteTriggers:
    """Verify DELETE is blocked on append-only tables that lacked DELETE coverage."""

    def _insert_minimal_batch(self, conn):
        """Insert a ledger_batches row and return its batch_id."""
        conn.execute(
            "INSERT INTO ledger_batches (created_at, event_count, paper_engine_version, config_hash) "
            "VALUES ('2026-01-01T00:00:00Z', 0, '0.3.0', 'dummy')"
        )
        conn.commit()
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def test_ledger_events_delete_raises(self, tmp_path: Path):
        db_path = _init_tmp_db(tmp_path)
        conn = connect_writer(db_path)
        batch_id = self._insert_minimal_batch(conn)
        conn.execute(
            "INSERT INTO ledger_events (batch_id, event_type, event_key, recorded_at) "
            "VALUES (?, 'signal_snapshot', 'test_key', '2026-01-01T00:00:00Z')",
            (batch_id,),
        )
        conn.commit()
        with pytest.raises(sqlite3.Error, match="append-only"):
            conn.execute("DELETE FROM ledger_events WHERE seq = 1")
        conn.close()

    def test_signal_snapshots_delete_raises(self, tmp_path: Path):
        db_path = _init_tmp_db(tmp_path)
        conn = connect_writer(db_path)
        batch_id = self._insert_minimal_batch(conn)
        conn.execute(
            "INSERT INTO ledger_events (batch_id, event_type, event_key, recorded_at) "
            "VALUES (?, 'signal_snapshot', 'snap_2026-01-01', '2026-01-01T00:00:00Z')",
            (batch_id,),
        )
        conn.execute(
            "INSERT INTO signal_snapshots "
            "(seq, batch_id, snapshot_id, bar_ts, bar_commit_id, active_symbols, "
            "heat_cap_triggered, source_observation_digest, run_ts) "
            "VALUES (1, ?, 'snap_2026-01-01', '2026-01-01T00:00:00Z', 'c1', '[]', "
            "0, 'dummy_digest', '2026-01-01T00:00:00Z')",
            (batch_id,),
        )
        conn.commit()
        with pytest.raises(sqlite3.Error, match="append-only"):
            conn.execute("DELETE FROM signal_snapshots WHERE seq = 1")
        conn.close()
