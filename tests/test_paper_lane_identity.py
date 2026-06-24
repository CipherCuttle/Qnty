"""Tests for the pure lane identity model (Phase 3, slice 2).

The model is deliberately disconnected from config hashing, the DB schema, the
writer, and the verifier. These tests lock its validation rules AND its purity
(no filesystem / DB / network / systemd / production-path coupling).
"""

from __future__ import annotations

import dataclasses
import inspect
from pathlib import Path

import pytest

from quantbot.paper import lane_identity as li
from quantbot.paper.lane_identity import (
    BASELINE_LANE_ID,
    LaneIdentity,
    validate_lane_id,
    validate_optional_sha256,
    validate_strategy_id,
    validate_strategy_version,
)

_HEX64 = "a" * 64  # valid 64-char lowercase hex SHA-256


# --------------------------------------------------------------------------- valid


def test_valid_identity_object():
    ident = LaneIdentity(
        lane_id="null_matched_v1",
        strategy_id="matched_null",
        strategy_version="1",
    )
    assert ident.lane_id == "null_matched_v1"
    assert ident.strategy_id == "matched_null"
    assert ident.strategy_version == "1"
    assert ident.source_data_digest is None
    assert ident.pre_registration_hash is None


def test_valid_optional_digests():
    ident = LaneIdentity(
        lane_id="null_matched_v1",
        strategy_id="matched_null",
        strategy_version="1.2.0",
        source_data_digest=_HEX64,
        pre_registration_hash="b" * 64,
    )
    assert ident.source_data_digest == _HEX64
    assert ident.pre_registration_hash == "b" * 64
    # The standalone helper accepts None and a valid digest, rejects nothing valid.
    assert validate_optional_sha256(None, "x") is None
    assert validate_optional_sha256(_HEX64, "x") == _HEX64


# ------------------------------------------------------------------ invalid ids


def test_invalid_empty_lane_id():
    with pytest.raises(ValueError):
        validate_lane_id("")
    with pytest.raises(ValueError):
        LaneIdentity(lane_id="", strategy_id="s", strategy_version="1")


def test_invalid_whitespace():
    for bad in ("lane a", "lane\ta", "lane\na", " lane", "lane "):
        with pytest.raises(ValueError):
            validate_lane_id(bad)


def test_invalid_slash_or_path_like_lane_id():
    for bad in ("lane/a", "lane\\a", "/abs/lane", "./lane"):
        with pytest.raises(ValueError):
            validate_lane_id(bad)


def test_invalid_dotdot_path_traversal():
    for bad in ("..", "../lane", "lane/..", "a..b"):
        with pytest.raises(ValueError):
            validate_lane_id(bad)


def test_invalid_uppercase_rejected():
    for bad in ("LaneA", "LANE", "Null_Matched_V1"):
        with pytest.raises(ValueError):
            validate_lane_id(bad)


def test_strategy_id_and_version_validate():
    assert validate_strategy_id("active_symbols_baseline") == "active_symbols_baseline"
    assert validate_strategy_version("1.2.0") == "1.2.0"
    for bad in ("", "Bad Id", "a/b", ".."):
        with pytest.raises((ValueError, TypeError)):
            validate_strategy_id(bad)
        with pytest.raises((ValueError, TypeError)):
            validate_strategy_version(bad)


# ------------------------------------------------------------------ invalid digests


def test_invalid_digest_length():
    for bad in ("a" * 63, "a" * 65, "abc"):
        with pytest.raises(ValueError):
            validate_optional_sha256(bad, "source_data_digest")
        with pytest.raises(ValueError):
            LaneIdentity(
                lane_id="null_matched_v1",
                strategy_id="matched_null",
                strategy_version="1",
                source_data_digest=bad,
            )


def test_invalid_digest_characters():
    # uppercase hex and non-hex characters are both rejected.
    for bad in ("A" * 64, "g" * 64, "z" * 64, ("a" * 63) + "!"):
        with pytest.raises(ValueError):
            validate_optional_sha256(bad, "pre_registration_hash")


# ----------------------------------------------------------------- immutability


def test_frozen_dataclass_immutability():
    ident = LaneIdentity(
        lane_id="null_matched_v1", strategy_id="matched_null", strategy_version="1"
    )
    assert dataclasses.is_dataclass(ident)
    with pytest.raises(dataclasses.FrozenInstanceError):
        ident.lane_id = "other"  # type: ignore[misc]


# -------------------------------------------------------------- baseline guard


def test_baseline_lane_id_not_instantiable_as_new_lane():
    assert BASELINE_LANE_ID == "paper_pnl_v1"
    with pytest.raises(ValueError):
        validate_lane_id("paper_pnl_v1")
    with pytest.raises(ValueError):
        LaneIdentity(
            lane_id="paper_pnl_v1", strategy_id="matched_null", strategy_version="1"
        )


# -------------------------------------------------------------------- purity


def _module_source() -> str:
    return Path(inspect.getsourcefile(li)).read_text(encoding="utf-8")


def test_model_does_not_import_io_or_network_modules():
    """Source must not import sqlite/systemd/network/subprocess/path-IO modules.

    The BASELINE_LANE_ID literal 'paper_pnl_v1' is a guard value (it is REJECTED,
    never used as a production path), so it is excluded from the path check below.
    """
    src = _module_source()
    forbidden_imports = (
        "import sqlite3",
        "import subprocess",
        "import socket",
        "import requests",
        "import urllib",
        "import os",
        "from os ",
        "import pathlib",
        "from pathlib",
        "open(",
    )
    for token in forbidden_imports:
        assert token not in src, f"lane_identity.py must not contain {token!r}"


def test_model_has_no_production_paths_or_infra_strings():
    src = _module_source()
    for token in ("/srv/qnty", "systemctl", "journalctl", "ssh -i"):
        assert token not in src, f"lane_identity.py must not reference {token!r}"


def test_no_profit_or_edge_claims():
    src = _module_source().lower()
    for token in ("profit guaranteed", "edge confirmed", "go live", "live trading"):
        assert token not in src
