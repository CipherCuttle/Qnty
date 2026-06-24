"""Verifier dual-mode lane identity validation (VERIFIER_DUAL_MODE_LANE_IDENTITY_PHASE3_PLAN).

Locks the smallest safe verifier slice:

  * v1 mode (no/NULL lane fields) — existing baseline checks are byte-identical and pass;
  * v2/new-lane mode (lane fields present) — require all four core fields, validate the
    `LaneIdentity`, and recompute `config_hash_v2` from the frozen v1 hash;
  * fail closed on partial/invalid/mismatched lane state and on a non-NULL
    `pre_registration_hash` (generation is deferred);
  * `ledger_batches.lane_id` is NOT checked yet (batch stamping deferred).

Real-DB cases use temp DBs built by `initialize_database` / `initialize_lane_database`.
Fail-closed mixed states (which the append-only writer cannot produce) are exercised on
the pure `_validate_lane_identity(cfg)` helper with synthetic row dicts. No production DB,
no `/srv/qnty`, no migration, no ALTER. No profitability or edge claim (EDGE_UNPROVEN).
"""

from __future__ import annotations

from quantbot.paper.config import build_config, config_hash
from quantbot.paper.db import (
    connect_readonly,
    initialize_database,
    initialize_lane_database,
)
from quantbot.paper.lane_config_hash import config_hash_v2
from quantbot.paper.lane_identity import LaneIdentity
from quantbot.paper.sqlite_verify import _validate_identity, _validate_lane_identity

FORWARD_START_TS = "2026-06-20T16:00:00"


def _identity() -> LaneIdentity:
    return LaneIdentity(
        lane_id="shadow_vol_a",
        strategy_id="vol_norm",
        strategy_version="1",
    )


def _v1_hash() -> str:
    return config_hash(build_config(forward_start_ts=FORWARD_START_TS))


def _valid_lane_cfg(**overrides) -> dict:
    """A synthetic paper_config-shaped dict for a valid new-lane row."""
    identity = _identity()
    v1 = _v1_hash()
    cfg = {
        "config_hash": v1,
        "lane_id": identity.lane_id,
        "strategy_id": identity.strategy_id,
        "strategy_version": identity.strategy_version,
        "config_hash_v2": config_hash_v2(v1, identity),
        "pre_registration_hash": None,
    }
    cfg.update(overrides)
    return cfg


def _identity_failures(db_path) -> list[str]:
    conn = connect_readonly(db_path)
    try:
        _cfg, failures = _validate_identity(conn)
    finally:
        conn.close()
    return failures


# ---------------------------------------------------------------------------
# Real temp-DB cases (full _validate_identity over a connection)
# ---------------------------------------------------------------------------

def test_old_v1_db_still_verifies(tmp_path):
    db_path = tmp_path / "baseline.db"
    initialize_database(db_path, build_config(forward_start_ts=FORWARD_START_TS))
    assert _identity_failures(db_path) == []


def test_v1_db_with_null_lane_fields_passes(tmp_path):
    # initialize_database creates the lane columns and leaves them NULL.
    db_path = tmp_path / "baseline_null.db"
    initialize_database(db_path, build_config(forward_start_ts=FORWARD_START_TS))

    conn = connect_readonly(db_path)
    try:
        row = dict(conn.execute("SELECT * FROM paper_config WHERE id = 1").fetchone())
    finally:
        conn.close()
    for f in ("lane_id", "strategy_id", "strategy_version", "config_hash_v2"):
        assert row[f] is None
    assert _identity_failures(db_path) == []


def test_new_lane_db_verifies(tmp_path):
    db_path = tmp_path / "lane.db"
    initialize_lane_database(
        db_path, build_config(forward_start_ts=FORWARD_START_TS), _identity()
    )
    assert _identity_failures(db_path) == []


# ---------------------------------------------------------------------------
# v1 mode helper behavior
# ---------------------------------------------------------------------------

def test_helper_v1_mode_all_null_passes():
    cfg = {
        "config_hash": _v1_hash(),
        "lane_id": None,
        "strategy_id": None,
        "strategy_version": None,
        "config_hash_v2": None,
        "pre_registration_hash": None,
    }
    assert _validate_lane_identity(cfg) == []


def test_helper_legacy_row_without_lane_columns_passes():
    # A pre-groundwork schema-1 row dict simply has no lane keys at all.
    cfg = {"config_hash": _v1_hash()}
    assert _validate_lane_identity(cfg) == []


def test_valid_new_lane_cfg_passes():
    assert _validate_lane_identity(_valid_lane_cfg()) == []


# ---------------------------------------------------------------------------
# Fail-closed states (synthetic row dicts)
# ---------------------------------------------------------------------------

def test_missing_strategy_id_fails():
    assert _validate_lane_identity(_valid_lane_cfg(strategy_id=None)) != []


def test_missing_strategy_version_fails():
    assert _validate_lane_identity(_valid_lane_cfg(strategy_version=None)) != []


def test_missing_config_hash_v2_fails():
    assert _validate_lane_identity(_valid_lane_cfg(config_hash_v2=None)) != []


def test_lane_id_present_but_strategy_id_missing_fails():
    cfg = {
        "config_hash": _v1_hash(),
        "lane_id": "shadow_vol_a",
        "strategy_id": None,
        "strategy_version": None,
        "config_hash_v2": None,
        "pre_registration_hash": None,
    }
    assert _validate_lane_identity(cfg) != []


def test_strategy_id_present_but_lane_id_missing_fails():
    cfg = {
        "config_hash": _v1_hash(),
        "lane_id": None,
        "strategy_id": "vol_norm",
        "strategy_version": None,
        "config_hash_v2": None,
        "pre_registration_hash": None,
    }
    assert _validate_lane_identity(cfg) != []


def test_invalid_lane_id_fails():
    assert _validate_lane_identity(_valid_lane_cfg(lane_id="Bad Id")) != []


def test_baseline_impersonating_lane_id_fails():
    # config_hash_v2 cannot even be computed for paper_pnl_v1; the model rejects it.
    cfg = _valid_lane_cfg(lane_id="paper_pnl_v1")
    assert _validate_lane_identity(cfg) != []


def test_config_hash_v2_mismatch_fails():
    assert _validate_lane_identity(_valid_lane_cfg(config_hash_v2="f" * 64)) != []


def test_non_null_pre_registration_hash_fails():
    assert _validate_lane_identity(_valid_lane_cfg(pre_registration_hash="a" * 64)) != []


def test_partial_only_pre_registration_hash_in_v1_mode_fails():
    cfg = {
        "config_hash": _v1_hash(),
        "lane_id": None,
        "strategy_id": None,
        "strategy_version": None,
        "config_hash_v2": None,
        "pre_registration_hash": "a" * 64,
    }
    assert _validate_lane_identity(cfg) != []
