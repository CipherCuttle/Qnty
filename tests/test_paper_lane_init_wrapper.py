"""Temp-safe new-lane init wrapper (LANE_CONFIG_WRAPPER_PHASE3_PLAN, minimal slice).

Locks the smallest safe lane-init helper `init_lane(...)`:

  * writes `paper_config.json` (unchanged v1, still loadable) + `lane_identity.json` +
    `lane_config_v2.json` sidecars, initializes the lane DB, and verifies it read-only;
  * fails closed on baseline-path collisions, invalid/baseline lane ids, and pre-existing
    targets;
  * never runs the writer.

Everything is `tmp_path` / synthetic only: no production DB, no `/srv/qnty` (only as the
rejected baseline guardrail), no `paper_pnl_v1` lane (rejected), no migration, no ALTER,
no writer run, no network/subprocess. No profitability or edge claim is made (strategy
remains EDGE_UNPROVEN).
"""

from __future__ import annotations

import json

import pytest

from quantbot.paper import paper_output_dir
from quantbot.paper.config import load_config
from quantbot.paper.db import DEFAULT_DB_PATH, connect_readonly
from quantbot.paper.lane_config_hash import config_hash_v2
from quantbot.paper.lane_identity import LaneIdentity
from quantbot.paper.lane_init import init_lane
from quantbot.paper.sqlite_verify import STATUS_OK, STATUS_PRE_START, verify_database

FORWARD_START_TS = "2026-06-20T16:00:00"
_OK = (STATUS_OK, STATUS_PRE_START)


def _args(tmp_path, **over):
    out = over.pop("output_dir", tmp_path / "lane_out")
    db = over.pop("db_path", out / "paper_ledger.db")
    base = dict(
        output_dir=out,
        db_path=db,
        lane_id="shadow_vol_a",
        strategy_id="vol_norm",
        strategy_version="1",
        forward_start_ts=FORWARD_START_TS,
    )
    base.update(over)
    return base


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_init_writes_all_three_files_and_verifies(tmp_path):
    res = init_lane(**_args(tmp_path))
    assert res.paper_config_path.exists()
    assert res.lane_identity_path.exists()
    assert res.lane_config_v2_path.exists()
    assert res.verify_status in _OK


def test_paper_config_is_loadable_and_has_no_lane_fields(tmp_path):
    res = init_lane(**_args(tmp_path))
    cfg = load_config(res.output_dir)
    assert cfg["forward_start_ts"] == FORWARD_START_TS
    for k in ("lane_id", "strategy_id", "strategy_version", "config_hash_v2"):
        assert k not in cfg


def test_lane_identity_json_has_exact_fields(tmp_path):
    res = init_lane(**_args(tmp_path))
    data = json.loads(res.lane_identity_path.read_text())
    assert data == {
        "lane_id": "shadow_vol_a",
        "strategy_id": "vol_norm",
        "strategy_version": "1",
    }


def test_lane_config_v2_json_fields(tmp_path):
    res = init_lane(**_args(tmp_path))
    data = json.loads(res.lane_config_v2_path.read_text())
    assert set(data) == {
        "accounting_config_hash_v1",
        "config_hash_v2",
        "pre_registration_hash",
    }
    assert data["pre_registration_hash"] is None
    assert data["accounting_config_hash_v1"] == res.accounting_config_hash_v1
    identity = LaneIdentity(
        lane_id="shadow_vol_a", strategy_id="vol_norm", strategy_version="1"
    )
    assert data["config_hash_v2"] == config_hash_v2(
        data["accounting_config_hash_v1"], identity
    )


def test_db_paper_config_row_matches_sidecars(tmp_path):
    res = init_lane(**_args(tmp_path))
    conn = connect_readonly(res.db_path)
    try:
        row = dict(conn.execute("SELECT * FROM paper_config WHERE id = 1").fetchone())
    finally:
        conn.close()
    assert row["lane_id"] == "shadow_vol_a"
    assert row["strategy_id"] == "vol_norm"
    assert row["strategy_version"] == "1"
    assert row["config_hash_v2"] == res.config_hash_v2
    assert row["config_hash"] == res.accounting_config_hash_v1


def test_verifier_passes_immediately_after_init(tmp_path):
    res = init_lane(**_args(tmp_path))
    assert verify_database(res.db_path).status in _OK


# ---------------------------------------------------------------------------
# Fail-closed safety gates
# ---------------------------------------------------------------------------

def test_rejects_baseline_output_dir(tmp_path):
    with pytest.raises(ValueError):
        init_lane(**_args(tmp_path, output_dir=paper_output_dir()))


def test_rejects_baseline_db_path(tmp_path):
    with pytest.raises(ValueError):
        init_lane(**_args(tmp_path, db_path=DEFAULT_DB_PATH))


def test_rejects_db_inside_baseline_output_dir(tmp_path):
    with pytest.raises(ValueError):
        init_lane(
            **_args(tmp_path, db_path=paper_output_dir() / "sub" / "paper_ledger.db")
        )


def test_rejects_invalid_lane_id(tmp_path):
    with pytest.raises(ValueError):
        init_lane(**_args(tmp_path, lane_id="Bad Id"))


def test_rejects_baseline_lane_id(tmp_path):
    with pytest.raises(ValueError):
        init_lane(**_args(tmp_path, lane_id="paper_pnl_v1"))


def test_rejects_existing_db_path(tmp_path):
    db = tmp_path / "exists.db"
    db.write_text("x", encoding="utf-8")
    with pytest.raises(FileExistsError):
        init_lane(**_args(tmp_path, output_dir=tmp_path / "lane_out", db_path=db))


def test_rejects_nonempty_output_dir_with_preexisting_config(tmp_path):
    out = tmp_path / "lane_out"
    out.mkdir()
    (out / "paper_config.json").write_text("{}", encoding="utf-8")
    with pytest.raises(FileExistsError):
        init_lane(**_args(tmp_path, output_dir=out, db_path=out / "paper_ledger.db"))


def test_refused_init_writes_nothing_for_baseline_lane_id(tmp_path):
    # A gate that fires before any FS write must leave the output dir untouched.
    out = tmp_path / "lane_out"
    with pytest.raises(ValueError):
        init_lane(**_args(tmp_path, output_dir=out, lane_id="paper_pnl_v1"))
    assert not out.exists()
