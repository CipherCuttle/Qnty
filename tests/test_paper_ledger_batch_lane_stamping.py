"""Ledger batch lane stamping — minimal slice (LEDGER_BATCH_LANE_STAMPING_PHASE3_PLAN).

Locks the smallest safe batch-stamping slice:

  * the writer stamps ``ledger_batches.lane_id`` only when a non-NULL lane id is passed
    (new-lane DBs); a baseline insert is byte-identical and leaves the column NULL;
  * the verifier is dual-mode — lane DBs require every committed batch be stamped with
    ``paper_config.lane_id``; v1/baseline DBs require the column be absent or NULL and
    fail closed on an unexpected stamp; legacy DBs without the column still verify.

Everything is temp-DB / synthetic only: no production DB, no `/srv/qnty`, no
`paper_pnl_v1` (except as the baseline id the lane model rejects), no migration, no
ALTER, no VM/systemd/network, no live trading. No profitability or edge claim is made
(strategy remains EDGE_UNPROVEN).
"""

from __future__ import annotations

import sqlite3

from quantbot.paper.config import build_config
from quantbot.paper.db import (
    connect_writer,
    initialize_database,
    initialize_lane_database,
)
from quantbot.paper.lane_identity import LaneIdentity
from quantbot.paper.sqlite_verify import (
    STATUS_OK,
    STATUS_PRE_START,
    _rows,
    _validate_batch_lane_stamping,
    verify_database,
)
from quantbot.paper.sqlite_writer import _insert_ledger_batch

FORWARD_START_TS = "2026-06-20T16:00:00"
LANE_ID = "shadow_vol_a"


def _identity() -> LaneIdentity:
    return LaneIdentity(lane_id=LANE_ID, strategy_id="vol_norm", strategy_version="1")


def _baseline_db(tmp_path, name="baseline.db"):
    p = tmp_path / name
    initialize_database(p, build_config(forward_start_ts=FORWARD_START_TS))
    return p


def _lane_db(tmp_path, name="lane.db"):
    p = tmp_path / name
    initialize_lane_database(
        p, build_config(forward_start_ts=FORWARD_START_TS), _identity()
    )
    return p


def _engine_and_hash(conn):
    r = conn.execute(
        "SELECT paper_engine_version, config_hash FROM paper_config WHERE id = 1"
    ).fetchone()
    return r["paper_engine_version"], r["config_hash"]


def _insert_committed_batch(conn, *, lane_id):
    """Insert one batch via the real writer helper, then mark it committed."""
    ev, ch = _engine_and_hash(conn)
    bid = _insert_ledger_batch(
        conn,
        created_at="now",
        started_at="now",
        prior_watermark=None,
        paper_engine_version=ev,
        config_hash_val=ch,
        lane_id=lane_id,
    )
    conn.execute(
        "UPDATE ledger_batches SET committed_at = 'now' WHERE batch_id = ?", (bid,)
    )
    conn.commit()
    return bid


def _legacy_conn(tmp_path, name, *, cfg_has_lane, cfg_lane_id, batch_has_lane, batch_lane):
    """Build a minimal synthetic DB with/without the additive lane columns.

    Used only to exercise column-absence branches that the real (current-schema)
    initializers can no longer produce. Pure temp file; no production schema.
    """
    p = tmp_path / name
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    cfg_cols = "id INTEGER PRIMARY KEY" + (", lane_id TEXT" if cfg_has_lane else "")
    conn.execute(f"CREATE TABLE paper_config ({cfg_cols})")
    if cfg_has_lane:
        conn.execute("INSERT INTO paper_config (id, lane_id) VALUES (1, ?)", (cfg_lane_id,))
    else:
        conn.execute("INSERT INTO paper_config (id) VALUES (1)")
    b_cols = "batch_id INTEGER PRIMARY KEY, committed_at TEXT" + (
        ", lane_id TEXT" if batch_has_lane else ""
    )
    conn.execute(f"CREATE TABLE ledger_batches ({b_cols})")
    if batch_has_lane:
        conn.execute(
            "INSERT INTO ledger_batches (batch_id, committed_at, lane_id) VALUES (1, 'now', ?)",
            (batch_lane,),
        )
    else:
        conn.execute(
            "INSERT INTO ledger_batches (batch_id, committed_at) VALUES (1, 'now')"
        )
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Writer stamping
# ---------------------------------------------------------------------------

def test_baseline_insert_leaves_lane_id_null(tmp_path):
    conn = connect_writer(_baseline_db(tmp_path))
    try:
        ev, ch = _engine_and_hash(conn)
        bid = _insert_ledger_batch(
            conn,
            created_at="now",
            started_at="now",
            prior_watermark=None,
            paper_engine_version=ev,
            config_hash_val=ch,
            lane_id=None,
        )
        conn.commit()
        row = conn.execute(
            "SELECT lane_id FROM ledger_batches WHERE batch_id = ?", (bid,)
        ).fetchone()
        assert row["lane_id"] is None
    finally:
        conn.close()


def test_new_lane_insert_stamps_lane_id(tmp_path):
    conn = connect_writer(_lane_db(tmp_path))
    try:
        ev, ch = _engine_and_hash(conn)
        bid = _insert_ledger_batch(
            conn,
            created_at="now",
            started_at="now",
            prior_watermark=None,
            paper_engine_version=ev,
            config_hash_val=ch,
            lane_id=LANE_ID,
        )
        conn.commit()
        row = conn.execute(
            "SELECT lane_id FROM ledger_batches WHERE batch_id = ?", (bid,)
        ).fetchone()
        assert row["lane_id"] == LANE_ID
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Verifier — lane mode
# ---------------------------------------------------------------------------

def test_lane_mode_all_match_passes(tmp_path):
    conn = connect_writer(_lane_db(tmp_path))
    try:
        _insert_committed_batch(conn, lane_id=LANE_ID)
        _insert_committed_batch(conn, lane_id=LANE_ID)
        batches = _rows(conn, "SELECT * FROM ledger_batches ORDER BY batch_id")
        assert _validate_batch_lane_stamping(conn, batches) == []
    finally:
        conn.close()


def test_lane_mode_null_batch_lane_fails(tmp_path):
    conn = connect_writer(_lane_db(tmp_path))
    try:
        _insert_committed_batch(conn, lane_id=None)  # unstamped batch in a lane DB
        batches = _rows(conn, "SELECT * FROM ledger_batches ORDER BY batch_id")
        failures = _validate_batch_lane_stamping(conn, batches)
        assert failures != []
        assert any("NULL" in f for f in failures)
    finally:
        conn.close()


def test_lane_mode_mismatch_batch_lane_fails(tmp_path):
    conn = connect_writer(_lane_db(tmp_path))
    try:
        _insert_committed_batch(conn, lane_id="some_other_lane")
        batches = _rows(conn, "SELECT * FROM ledger_batches ORDER BY batch_id")
        failures = _validate_batch_lane_stamping(conn, batches)
        assert any("!=" in f for f in failures)
    finally:
        conn.close()


def test_lane_mode_missing_batch_column_fails(tmp_path):
    conn = _legacy_conn(
        tmp_path,
        "lane_nocol.db",
        cfg_has_lane=True,
        cfg_lane_id=LANE_ID,
        batch_has_lane=False,
        batch_lane=None,
    )
    try:
        batches = _rows(conn, "SELECT * FROM ledger_batches ORDER BY batch_id")
        assert _validate_batch_lane_stamping(conn, batches) != []
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Verifier — v1 / baseline mode
# ---------------------------------------------------------------------------

def test_v1_with_lane_col_all_null_passes(tmp_path):
    conn = connect_writer(_baseline_db(tmp_path))
    try:
        _insert_committed_batch(conn, lane_id=None)
        batches = _rows(conn, "SELECT * FROM ledger_batches ORDER BY batch_id")
        assert _validate_batch_lane_stamping(conn, batches) == []
    finally:
        conn.close()


def test_v1_with_non_null_batch_lane_fails_closed(tmp_path):
    conn = connect_writer(_baseline_db(tmp_path))
    try:
        # Force a stamp into a baseline DB (paper_config.lane_id is NULL): unexpected.
        _insert_committed_batch(conn, lane_id=LANE_ID)
        batches = _rows(conn, "SELECT * FROM ledger_batches ORDER BY batch_id")
        assert _validate_batch_lane_stamping(conn, batches) != []
    finally:
        conn.close()


def test_legacy_db_without_batch_lane_column_passes(tmp_path):
    conn = _legacy_conn(
        tmp_path,
        "legacy.db",
        cfg_has_lane=False,
        cfg_lane_id=None,
        batch_has_lane=False,
        batch_lane=None,
    )
    try:
        batches = _rows(conn, "SELECT * FROM ledger_batches ORDER BY batch_id")
        assert _validate_batch_lane_stamping(conn, batches) == []
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Full-verify smoke: a freshly initialized baseline DB is not corrupt.
# ---------------------------------------------------------------------------

def test_baseline_db_full_verify_not_corrupt(tmp_path):
    result = verify_database(_baseline_db(tmp_path))
    assert result.status in (STATUS_OK, STATUS_PRE_START), result.failures
