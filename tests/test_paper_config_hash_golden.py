"""Baseline v1 golden-hash proof (Phase 3 — BASELINE_V1_GOLDEN_HASH_PROOF_PHASE3_PLAN).

A safety gate that LOCKS the existing v1 baseline identity behavior with golden
constants, BEFORE any future schema / writer / verifier / lane wiring. If a later
change perturbs the clean production baseline (`build_config` shape, `config_hash`,
`config_hash_from_row` reconstruction, or `bar_commit_id`), these tests fail loudly.

All inputs are synthetic and in-memory: no production DB, no `/srv/qnty`, no SQLite
file opened. The goldens are intentionally coupled to SCHEMA_VERSION=1,
PAPER_ENGINE_VERSION="0.3.0", and the baseline label — a constant change SHOULD break
this test (that is the point of the gate). No profitability or edge claim is made.

Golden constants were generated once by running the current functions and are asserted
verbatim thereafter; nothing here mutates any config, row, or module state.
"""

from __future__ import annotations

import copy

from quantbot.paper import BASELINE_LABEL, PAPER_ENGINE_VERSION, SCHEMA_VERSION
from quantbot.paper.config import build_config, config_hash
from quantbot.paper.db import config_hash_from_row
from quantbot.paper.lane_config_hash import config_hash_v2
from quantbot.paper.lane_identity import LaneIdentity
from quantbot.paper.snapshots import bar_commit_id

# Fixed, deterministic, on-grid (00/08/16 UTC) timestamp for the locked config.
FORWARD_START_TS = "2026-06-20T16:00:00"
BAR_TS = "2026-06-20T16:00:00"

# Golden values (generated once from the current functions; frozen thereafter).
EXPECTED_CONFIG_HASH = "1d61c1c779107ad194ca12febe620685bbc730edf75a766467fb45c05a74561b"
EXPECTED_BAR_COMMIT_ID = "7ae63522a23b65fc"

# The exact canonical v1 config dict build_config must produce for FORWARD_START_TS.
EXPECTED_CONFIG = {
    "schema_version": 1,
    "engine_version": "0.3.0",
    "baseline_label": "fixed_notional_active_symbols_paper_v1",
    "forward_start_ts": FORWARD_START_TS,
    "initial_equity_usd": 10000.0,
    "notional_usd": 1000.0,
    "leverage": 1.0,
    "fee_model": {"type": "flat_taker", "fee_bps": 5.0},
    "slippage_model": {"type": "fixed", "slippage_bps": 5.0},
    "fill_model": "next_bar_open_pessimistic",
    "funding_model": {"type": "accrual", "applied_as": "cash_flow"},
    "signal_source": "observation_log.json:per_bar_obs",
    "freshness": {
        "bar_interval_hours": 8,
        "max_bar_staleness_hours": 24.0,
        "heartbeat_max_age_hours": 24.0,
    },
    "config_hash": EXPECTED_CONFIG_HASH,
}

# Synthetic flat v1 paper_config row (the columns config_hash_from_row reads).
# Deliberately carries NO lane fields — an old schema-1 baseline row must still
# reconstruct to the same golden hash.
SYNTHETIC_V1_ROW = {
    "db_schema_version": 1,
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
    "config_hash": EXPECTED_CONFIG_HASH,
}

# Fixed consumed signal row for the bar_commit_id lock.
CONSUMED_OBS = {"active_symbols": ["AAA", "BBB"]}

# A non-baseline lane identity used only to prove v2 does not perturb v1.
_NON_BASELINE_IDENTITY = LaneIdentity(
    lane_id="null_matched_v1",
    strategy_id="matched_null",
    strategy_version="1",
)


def test_build_config_full_dict_shape_locked():
    cfg = build_config(forward_start_ts=FORWARD_START_TS)
    assert cfg == EXPECTED_CONFIG
    # Sanity: the constants the goldens are coupled to are still in force.
    assert SCHEMA_VERSION == 1
    assert PAPER_ENGINE_VERSION == "0.3.0"
    assert BASELINE_LABEL == "fixed_notional_active_symbols_paper_v1"


def test_config_hash_matches_golden():
    cfg = build_config(forward_start_ts=FORWARD_START_TS)
    assert config_hash(cfg) == EXPECTED_CONFIG_HASH
    assert len(EXPECTED_CONFIG_HASH) == 64


def test_config_hash_from_row_matches_golden():
    # Reconstruction from a flat row must reproduce the same golden hash.
    assert config_hash_from_row(SYNTHETIC_V1_ROW) == EXPECTED_CONFIG_HASH


def test_old_v1_row_without_lane_fields_reconstructs():
    # No lane identity columns are present, and none are needed.
    for lane_field in ("lane_id", "strategy_id", "strategy_version",
                       "source_data_digest", "pre_registration_hash"):
        assert lane_field not in SYNTHETIC_V1_ROW
    assert config_hash_from_row(SYNTHETIC_V1_ROW) == EXPECTED_CONFIG_HASH


def test_bar_commit_id_matches_golden():
    bcid = bar_commit_id(CONSUMED_OBS, BAR_TS, PAPER_ENGINE_VERSION, EXPECTED_CONFIG_HASH)
    assert bcid == EXPECTED_BAR_COMMIT_ID
    # bar_commit_id is a 16-char truncated hex string, NOT a full SHA-256.
    assert len(EXPECTED_BAR_COMMIT_ID) == 16
    assert len(bcid) == 16


def test_config_hash_v2_does_not_mutate_or_recompute_v1():
    cfg = build_config(forward_start_ts=FORWARD_START_TS)
    v1_hash_before = cfg["config_hash"]
    cfg_snapshot = copy.deepcopy(cfg)

    digest = config_hash_v2(v1_hash_before, _NON_BASELINE_IDENTITY)
    assert len(digest) == 64

    # v1 config dict and its hash are untouched and still self-consistent.
    assert cfg == cfg_snapshot
    assert cfg["config_hash"] == v1_hash_before == EXPECTED_CONFIG_HASH
    assert config_hash(cfg) == EXPECTED_CONFIG_HASH
