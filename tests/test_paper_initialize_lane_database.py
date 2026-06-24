"""New-lane DB initialization helper (WRITER_NEW_LANE_INIT_PHASE3_PLAN, minimal slice).

Locks the smallest safe sibling initializer `initialize_lane_database(...)`:

  * it populates the additive `paper_config` lane columns at INSERT time (never via a
    post-hoc UPDATE — `paper_config` is append-only);
  * it composes `config_hash_v2` from the frozen v1 accounting hash + a validated
    `LaneIdentity`, leaving `pre_registration_hash` NULL;
  * it refuses baseline impersonation, an existing DB file, and the baseline DB path;
  * it never perturbs the baseline `initialize_database(...)` path or the v1 golden hash.

Everything is temp-DB / synthetic only: no production DB, no `/srv/qnty`, no migration,
no ALTER, no writer run, no verifier. No profitability or edge claim is made (strategy
remains EDGE_UNPROVEN).
"""

from __future__ import annotations

import pytest

from quantbot.paper.config import build_config, config_hash
from quantbot.paper.db import (
    config_hash_from_row,
    connect_readonly,
    initialize_database,
    initialize_lane_database,
)
from quantbot.paper.lane_config_hash import config_hash_v2
from quantbot.paper.lane_identity import LaneIdentity

# On-grid (16:00 UTC) deterministic timestamp, matching the golden-proof fixture.
FORWARD_START_TS = "2026-06-20T16:00:00"

LANE_COLUMNS = (
    "lane_id",
    "strategy_id",
    "strategy_version",
    "config_hash_v2",
    "pre_registration_hash",
)


def _identity() -> LaneIdentity:
    return LaneIdentity(
        lane_id="shadow_vol_a",
        strategy_id="vol_norm",
        strategy_version="1",
    )


def _read_config_row(db_path):
    conn = connect_readonly(db_path)
    try:
        return conn.execute("SELECT * FROM paper_config WHERE id = 1").fetchone()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# New-lane initialization populates lane fields
# ---------------------------------------------------------------------------

def test_lane_db_initializes_and_stores_lane_fields(tmp_path):
    config = build_config(forward_start_ts=FORWARD_START_TS)
    identity = _identity()
    db_path = tmp_path / "lane.db"

    initialize_lane_database(db_path, config, identity)

    row = _read_config_row(db_path)
    assert row["lane_id"] == "shadow_vol_a"
    assert row["strategy_id"] == "vol_norm"
    assert row["strategy_version"] == "1"
    assert row["config_hash_v2"] is not None
    assert len(row["config_hash_v2"]) == 64


def test_stored_config_hash_v2_recomputes_from_stored_v1_hash(tmp_path):
    config = build_config(forward_start_ts=FORWARD_START_TS)
    identity = _identity()
    db_path = tmp_path / "lane.db"

    initialize_lane_database(db_path, config, identity)

    row = _read_config_row(db_path)
    # The stored v2 hash recomputes from the stored v1 accounting hash + identity.
    assert row["config_hash_v2"] == config_hash_v2(row["config_hash"], identity)


def test_pre_registration_hash_is_null(tmp_path):
    config = build_config(forward_start_ts=FORWARD_START_TS)
    db_path = tmp_path / "lane.db"

    initialize_lane_database(db_path, config, _identity())

    row = _read_config_row(db_path)
    assert row["pre_registration_hash"] is None


def test_lane_db_config_hash_from_row_is_v1_accounting_hash(tmp_path):
    config = build_config(forward_start_ts=FORWARD_START_TS)
    db_path = tmp_path / "lane.db"

    initialize_lane_database(db_path, config, _identity())

    row = _read_config_row(db_path)
    # Despite populated lane columns, the v1 reconstruction is unchanged.
    assert config_hash_from_row(row) == config["config_hash"] == config_hash(config)


# ---------------------------------------------------------------------------
# Baseline path is untouched
# ---------------------------------------------------------------------------

def test_baseline_initializer_still_leaves_lane_fields_null(tmp_path):
    config = build_config(forward_start_ts=FORWARD_START_TS)
    db_path = tmp_path / "baseline.db"

    initialize_database(db_path, config)

    row = _read_config_row(db_path)
    for col in LANE_COLUMNS:
        assert row[col] is None, f"baseline {col} must remain NULL"


# ---------------------------------------------------------------------------
# Safety gates
# ---------------------------------------------------------------------------

def test_invalid_lane_identity_rejected():
    # LaneIdentity validation is reject-only; an invalid lane_id never constructs.
    with pytest.raises(ValueError):
        LaneIdentity(lane_id="Bad Id", strategy_id="s", strategy_version="1")


def test_baseline_impersonating_lane_id_rejected():
    with pytest.raises(ValueError):
        LaneIdentity(lane_id="paper_pnl_v1", strategy_id="s", strategy_version="1")


def test_existing_db_path_refused(tmp_path):
    config = build_config(forward_start_ts=FORWARD_START_TS)
    db_path = tmp_path / "lane.db"
    initialize_lane_database(db_path, config, _identity())

    with pytest.raises(FileExistsError):
        initialize_lane_database(db_path, config, _identity())


def test_baseline_db_path_refused_when_supplied(tmp_path):
    config = build_config(forward_start_ts=FORWARD_START_TS)
    baseline_db_path = tmp_path / "baseline.db"

    with pytest.raises(ValueError):
        initialize_lane_database(
            baseline_db_path, config, _identity(), baseline_db_path=baseline_db_path
        )
    # The refused call must not have created the file.
    assert not baseline_db_path.exists()
