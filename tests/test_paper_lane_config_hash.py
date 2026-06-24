"""Tests for the pure lane config hash v2 helper (Phase 3, slice 3).

Locks the v2 payload shape, determinism, sensitivity to identity, v1-hash
validation, the deliberate payload exclusions, helper purity, AND a baseline
protection test proving v1 config/hash are untouched by computing a v2 hash.
"""

from __future__ import annotations

import copy
import hashlib
import inspect
from pathlib import Path

import pytest

from quantbot.core.determinism import canonical_json_dumps
from quantbot.paper import lane_config_hash as lch
from quantbot.paper.lane_config_hash import (
    CONFIG_HASH_VERSION,
    config_hash_v2,
    config_hash_v2_payload,
)
from quantbot.paper.lane_identity import LaneIdentity

_V1 = "a" * 64  # valid 64-char lowercase hex SHA-256

_IDENT = LaneIdentity(
    lane_id="null_matched_v1",
    strategy_id="matched_null",
    strategy_version="1",
)


# --------------------------------------------------------------------- payload


def test_v2_payload_exact_shape():
    payload = config_hash_v2_payload(_V1, _IDENT)
    assert payload == {
        "config_hash_version": 2,
        "accounting_config_hash_v1": _V1,
        "lane_identity": {
            "lane_id": "null_matched_v1",
            "strategy_id": "matched_null",
            "strategy_version": "1",
        },
    }
    assert CONFIG_HASH_VERSION == 2


def test_payload_excludes_forbidden_fields():
    payload = config_hash_v2_payload(_V1, _IDENT)
    serialized = canonical_json_dumps(payload)
    for forbidden in (
        "source_data_digest",
        "pre_registration_hash",
        "paper_engine_version",
        "schema_version",
        "db_schema_version",
    ):
        assert forbidden not in payload
        assert forbidden not in payload["lane_identity"]
        # Also absent from the serialized canonical JSON (nothing nested sneaks in).
        assert forbidden not in serialized


# ------------------------------------------------------------------ hash props


def test_v2_hash_deterministic():
    assert config_hash_v2(_V1, _IDENT) == config_hash_v2(_V1, _IDENT)
    # And it is exactly sha256 over the canonical payload JSON.
    expected = hashlib.sha256(
        canonical_json_dumps(config_hash_v2_payload(_V1, _IDENT)).encode("utf-8")
    ).hexdigest()
    assert config_hash_v2(_V1, _IDENT) == expected


def test_v2_hash_changes_when_lane_id_changes():
    other = LaneIdentity(lane_id="null_matched_v2", strategy_id="matched_null", strategy_version="1")
    assert config_hash_v2(_V1, other) != config_hash_v2(_V1, _IDENT)


def test_v2_hash_changes_when_strategy_id_changes():
    other = LaneIdentity(lane_id="null_matched_v1", strategy_id="other_strategy", strategy_version="1")
    assert config_hash_v2(_V1, other) != config_hash_v2(_V1, _IDENT)


def test_v2_hash_changes_when_strategy_version_changes():
    other = LaneIdentity(lane_id="null_matched_v1", strategy_id="matched_null", strategy_version="2")
    assert config_hash_v2(_V1, other) != config_hash_v2(_V1, _IDENT)


def test_v2_hash_changes_when_v1_hash_changes():
    assert config_hash_v2("b" * 64, _IDENT) != config_hash_v2(_V1, _IDENT)


# ------------------------------------------------------------ v1 hash validation


def test_invalid_v1_hash_length_rejected():
    for bad in ("a" * 63, "a" * 65, "abc", ""):
        with pytest.raises(ValueError):
            config_hash_v2(bad, _IDENT)
        with pytest.raises(ValueError):
            config_hash_v2_payload(bad, _IDENT)


def test_invalid_v1_hash_chars_rejected():
    for bad in (("a" * 63) + "!", "g" * 64, ("a" * 60) + " abc"):
        with pytest.raises(ValueError):
            config_hash_v2(bad, _IDENT)


def test_uppercase_v1_hash_rejected():
    for bad in ("A" * 64, ("a" * 63) + "A"):
        with pytest.raises(ValueError):
            config_hash_v2(bad, _IDENT)


# ---------------------------------------------------------------- baseline guard


def test_baseline_v1_config_and_hash_unchanged_by_v2():
    """Computing a v2 hash must not recompute, alter, or depend on v1 build behavior.

    Imports build_config IN THE TEST ONLY (the helper module must not import config.py).
    """
    from quantbot.lab import fixtures as fx
    from quantbot.paper.config import build_config, config_hash

    ts = fx.grid(1)[0]
    cfg = build_config(forward_start_ts=ts)
    v1_hash_before = cfg["config_hash"]
    cfg_snapshot = copy.deepcopy(cfg)

    # Use the real v1 hash + a non-baseline lane identity.
    digest = config_hash_v2(v1_hash_before, _IDENT)
    assert len(digest) == 64

    # The v1 config dict and its hash are untouched, and still self-consistent.
    assert cfg == cfg_snapshot
    assert cfg["config_hash"] == v1_hash_before
    assert config_hash(cfg) == v1_hash_before


# -------------------------------------------------------------------- purity


def _module_source() -> str:
    return Path(inspect.getsourcefile(lch)).read_text(encoding="utf-8")


def test_helper_does_not_import_config_db_or_infra():
    src = _module_source()
    forbidden = (
        "quantbot.paper.config",
        "import sqlite3",
        "from sqlite3",
        "import subprocess",
        "import socket",
        "import requests",
        "import urllib",
        "import os",
        "from os ",
        "open(",
        "systemctl",
        "journalctl",
    )
    for token in forbidden:
        assert token not in src, f"lane_config_hash.py must not contain {token!r}"


def test_helper_has_no_production_paths_or_claims():
    src = _module_source().lower()
    for token in ("/srv/qnty", "paper_pnl_v1", "live trading", "exchange key",
                  "real order", "profit guaranteed", "edge confirmed", "go live"):
        assert token not in src, f"lane_config_hash.py must not reference {token!r}"
