"""Additive new-lane schema groundwork (ADDITIVE_NEW_LANE_DB_SCHEMA_PHASE3_PLAN).

Locks the smallest safe slice of new-lane schema groundwork:

  1. `config_hash_from_row(...)` reconstructs the v1 accounting hash from the PAPER
     CONTRACT version, not the storage `db_schema_version`. A future storage-schema
     bump (db_schema_version 1 -> 2) therefore can NOT perturb the frozen v1 hash.
  2. Newly-created DBs carry nullable additive lane columns on `paper_config`, NULL
     for the baseline. They are reserved only — never populated here.

Everything is synthetic / temp-DB only: no production DB, no `/srv/qnty`, no
`paper_pnl_v1`, no migration, no ALTER, no VM/systemd/network. The writer is not
wired and the verifier is not dual-moded. No profitability or edge claim is made
(strategy remains EDGE_UNPROVEN).
"""

from __future__ import annotations

from quantbot.paper.config import build_config, config_hash
from quantbot.paper.db import (
    config_hash_from_row,
    connect_readonly,
    initialize_database,
)

# On-grid (16:00 UTC) deterministic timestamp, matching the golden-proof fixture.
FORWARD_START_TS = "2026-06-20T16:00:00"

# The additive lane columns reserved on paper_config (new-lane DBs only).
LANE_COLUMNS = (
    "lane_id",
    "strategy_id",
    "strategy_version",
    "config_hash_v2",
    "pre_registration_hash",
)


def _golden_v1_hash() -> str:
    """The frozen v1 accounting hash, derived from the canonical builder."""
    return config_hash(build_config(forward_start_ts=FORWARD_START_TS))


def _flat_row(**overrides) -> dict:
    """A flat paper_config-shaped row carrying exactly the v1 accounting fields."""
    row = {
        "db_schema_version": 1,
        "paper_contract_version": 1,
        "paper_engine_version": "0.3.0",
        "baseline_label": "fixed_notional_active_symbols_paper_v1",
        "forward_start_ts": FORWARD_START_TS,
        "initial_equity_usd": 10000.0,
        "notional_usd": 1000.0,
        "leverage": 1.0,
        "fee_type": "flat_taker",
        "fee_bps": 5.0,
        "slippage_type": "fixed",
        "slippage_bps": 5.0,
        "funding_type": "accrual",
        "funding_applied_as": "cash_flow",
        "fill_model": "next_bar_open_pessimistic",
        "signal_source": "observation_log.json:per_bar_obs",
        "freshness_bar_interval_hours": 8,
        "freshness_max_bar_staleness_hours": 24.0,
        "freshness_heartbeat_max_age_hours": 24.0,
        "config_hash": _golden_v1_hash(),
    }
    row.update(overrides)
    return row


# ---------------------------------------------------------------------------
# 1. config_hash_from_row decoupling
# ---------------------------------------------------------------------------

def test_config_hash_from_row_matches_golden_for_schema1_row():
    assert config_hash_from_row(_flat_row()) == _golden_v1_hash()


def test_legacy_row_without_paper_contract_version_falls_back_to_db_schema_version():
    # A legacy/synthetic row that predates the paper_contract_version column must
    # still reconstruct the golden hash via the db_schema_version fallback.
    row = _flat_row()
    del row["paper_contract_version"]
    assert "paper_contract_version" not in row
    assert config_hash_from_row(row) == _golden_v1_hash()


def test_storage_schema_bump_does_not_change_v1_hash():
    # The decoupling guarantee: db_schema_version=2 (future storage schema) with
    # paper_contract_version=1 (frozen accounting contract) yields the SAME hash.
    row = _flat_row(db_schema_version=2, paper_contract_version=1)
    assert config_hash_from_row(row) == _golden_v1_hash()


def test_lane_columns_present_on_row_do_not_affect_v1_hash():
    # Even if a row carried populated lane fields, the v1 reconstruction ignores them.
    row = _flat_row(
        lane_id="some_lane",
        strategy_id="some_strategy",
        strategy_version="1",
        config_hash_v2="f" * 64,
        pre_registration_hash="a" * 64,
    )
    assert config_hash_from_row(row) == _golden_v1_hash()


# ---------------------------------------------------------------------------
# 2. Additive nullable lane columns on newly-created DBs
# ---------------------------------------------------------------------------

def test_new_db_has_nullable_lane_columns(tmp_path):
    db_path = tmp_path / "lane_schema.db"
    initialize_database(db_path, build_config(forward_start_ts=FORWARD_START_TS))

    conn = connect_readonly(db_path)
    try:
        info = {r["name"]: r for r in conn.execute("PRAGMA table_info(paper_config)")}
    finally:
        conn.close()

    for col in LANE_COLUMNS:
        assert col in info, f"new DB paper_config is missing additive column {col!r}"
        # notnull == 0 means the column is nullable; dflt_value is NULL (no default).
        assert info[col]["notnull"] == 0, f"{col} must be nullable"
        assert info[col]["dflt_value"] is None, f"{col} must have no default"


def test_baseline_row_has_null_lane_fields(tmp_path):
    db_path = tmp_path / "lane_baseline.db"
    initialize_database(db_path, build_config(forward_start_ts=FORWARD_START_TS))

    conn = connect_readonly(db_path)
    try:
        cols = ", ".join(LANE_COLUMNS)
        row = conn.execute(
            f"SELECT {cols} FROM paper_config WHERE id = 1"
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    for col in LANE_COLUMNS:
        assert row[col] is None, f"baseline {col} must be NULL (unpopulated)"


def test_new_db_baseline_hash_recomputes_unchanged(tmp_path):
    # A freshly created baseline DB row (now carrying paper_contract_version and the
    # nullable lane columns) must still recompute to the golden v1 hash.
    db_path = tmp_path / "lane_recompute.db"
    initialize_database(db_path, build_config(forward_start_ts=FORWARD_START_TS))

    conn = connect_readonly(db_path)
    try:
        row = conn.execute("SELECT * FROM paper_config WHERE id = 1").fetchone()
    finally:
        conn.close()

    assert config_hash_from_row(row) == row["config_hash"] == _golden_v1_hash()
