"""Focused tests for H003_SIGNAL_INTENT_V0 downstream acceptance (Subtask D).

Covers: valid acceptance, idempotent re-acceptance (no-op), tampered-artifact
rejection (digest mismatch, no partial writes), float-in-artifact rejection,
and missing-field rejection. The acceptance decision must be Qnty's own,
fail-closed, and must never write a ledger row or receipt for a rejected
artifact.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from quantbot.core.determinism import canonical_json_dumps
from quantbot.paper.h003_acceptance import (
    AcceptanceRejected,
    CANONICAL_QNTYLAB_COMMIT,
    accept_h003_signal_intent,
)

QNTY_HEAD = "a" * 40
NOW = datetime(2026, 9, 8, 21, 30, 0, tzinfo=timezone.utc)


def _valid_artifact() -> dict:
    return {
        "schema_name": "H003_SIGNAL_INTENT_V0",
        "schema_version": "V0",
        "phase": "QNTY_H003_SOL_TO_QNTYSPOT_SHADOW_BRIDGE_V0",
        "upstream": {
            "candidate_id": "CANDIDATE_H003_MA_48_192_LONG_FLAT",
            "strategy_id": "H003_moving_average",
            "strategy_version": "existing-qntylab-strategies-v1",
            "variant_id": "variant_00eb140f03a5f6ab40600160",
            "parameters": {"fast": 48, "slow": 192, "mode": "long_flat"},
            "source_semantic": "BINANCE_SPOT_SOLUSDT_1H",
            "source_repository": "CipherCuttle/QntyLab",
            "source_commit": CANONICAL_QNTYLAB_COMMIT,
            "qntylab_head": CANONICAL_QNTYLAB_COMMIT,
        },
        "bar_window": {
            "first_bar_open": "2021-01-01T00:00:00Z",
            "last_bar_open": "2026-09-08T20:00:00Z",
            "bar_count": 49831,
            "close_of_bar_t": "2026-09-08T21:00:00Z",
        },
        "close_series": {
            "digest_rule": "sha256 of data/raw/SOLUSDT-1h.csv file bytes",
            "path": "data/raw/SOLUSDT-1h.csv",
            "sha256": "c" * 64,
        },
        "signal": {
            "ma48": {"numerator": 5209, "denominator": 50},
            "ma192": {"numerator": 1975003, "denominator": 19200},
            "raw_signal_at_t": 1,
            "causal_target_t_plus_1": "LONG",
            "decision_bar_t_open": "2026-09-08T20:00:00Z",
            "decision_rule": "sign(ma48 - ma192) at close of bar t, clamped by long_flat",
            "source_bar_timestamp": "2026-09-08T20:00:00Z",
        },
        "transition": {
            "action": "NO_ACTION",
            "current_target": "LONG",
            "previous_target": "LONG",
        },
        "computed_at": "2026-09-08T21:03:17.228114Z",
        "computed_at_rule": "manifest retrieved_at (deterministic replay; no wall clock)",
        "authority": {
            "capital": "NONE",
            "execution": "FORBIDDEN",
            "signing": "NONE",
            "submission": "NONE",
        },
        "artifact_digest": "",
    }


def _canonical_digest(artifact: dict) -> str:
    probe = dict(artifact)
    probe["artifact_digest"] = ""
    return hashlib.sha256(canonical_json_dumps(probe).encode("utf-8")).hexdigest()


def _write_artifact(tmp_path: Path, artifact: dict) -> tuple[Path, Path]:
    artifact_path = tmp_path / "H003_SIGNAL_INTENT_V0.json"
    sidecar_path = tmp_path / "H003_SIGNAL_INTENT_V0.sha256"
    artifact_path.write_bytes((canonical_json_dumps(artifact) + "\n").encode("utf-8"))
    sidecar_path.write_text(artifact["artifact_digest"] + "\n", encoding="utf-8")
    return artifact_path, sidecar_path


def _make_valid_fixture(tmp_path: Path) -> tuple[Path, Path]:
    artifact = _valid_artifact()
    artifact["artifact_digest"] = _canonical_digest(artifact)
    return _write_artifact(tmp_path, artifact)


def _accept(tmp_path: Path, artifact_path: Path, sidecar_path: Path) -> dict:
    return accept_h003_signal_intent(
        artifact_path,
        sidecar_path,
        artifacts_dir=tmp_path / "artifacts" / "h003_bridge_v0",
        now=NOW,
        qnty_head=QNTY_HEAD,
    )


def test_valid_acceptance(tmp_path: Path) -> None:
    artifact_path, sidecar_path = _make_valid_fixture(tmp_path)
    result = _accept(tmp_path, artifact_path, sidecar_path)

    assert result["decision"] == "ACCEPTED"
    assert result["idempotent_no_op"] is False
    assert result["artifact_digest"] == _canonical_digest(_valid_artifact() | {"artifact_digest": ""})

    artifacts_dir = tmp_path / "artifacts" / "h003_bridge_v0"
    receipt_path = artifacts_dir / "H003_ACCEPTANCE_V0.json"
    sidecar = artifacts_dir / "H003_ACCEPTANCE_V0.sha256"
    ledger_path = artifacts_dir / "h003_acceptance_ledger.jsonl"
    assert receipt_path.exists() and sidecar.exists() and ledger_path.exists()

    # Exactly one id-keyed ledger row, via the existing append-only machinery.
    rows = [json.loads(line) for line in ledger_path.read_text().splitlines() if line.strip()]
    assert len(rows) == 1
    assert rows[0]["acceptance_id"] == f"H003_ACCEPTANCE_V0:{result['artifact_digest']}"
    assert rows[0]["decision"] == "ACCEPTED"
    assert rows[0]["authority"] == {"capital": "NONE", "execution": "FORBIDDEN", "signing": "NONE", "submission": "NONE"}

    # Receipt: canonical bytes, digest discipline identical to the upstream
    # artifact (sha256 over canonical JSON with receipt_digest=""), no floats.
    receipt = json.loads(receipt_path.read_text())
    assert receipt["schema_name"] == "H003_ACCEPTANCE_V0"
    assert receipt["decision"] == "ACCEPTED"
    assert receipt["accepted_artifact"]["artifact_digest"] == result["artifact_digest"]
    assert receipt["qnty_head_at_acceptance"] == QNTY_HEAD
    assert receipt["ledger"]["record_id"] == rows[0]["acceptance_id"]
    assert receipt["authority"] == {"capital": "NONE", "execution": "FORBIDDEN", "signing": "NONE", "submission": "NONE"}
    assert receipt["accepted_artifact"]["upstream_source_commit"] == CANONICAL_QNTYLAB_COMMIT
    assert receipt["qnty_implementation"]["version"] == "H003_ACCEPTANCE_V0"
    assert receipt["acceptance_reason"] == "H003_SIGNAL_INTENT_V0_VALIDATED_FAIL_CLOSED"
    assert all(v["status"] == "PASS" for v in receipt["validators"].values())
    probe = dict(receipt)
    probe["receipt_digest"] = ""
    expected = hashlib.sha256(canonical_json_dumps(probe).encode("utf-8")).hexdigest()
    assert receipt["receipt_digest"] == expected
    assert sidecar.read_text().strip() == expected
    assert receipt_path.read_bytes() == (canonical_json_dumps(receipt) + "\n").encode("utf-8")
    assert "FLOAT_IN_ARTIFACT" not in receipt_path.read_text()
    _assert_no_floats(receipt)


def _assert_no_floats(obj: object) -> None:
    if isinstance(obj, float):
        pytest.fail(f"float leaked into receipt: {obj!r}")
    if isinstance(obj, dict):
        for value in obj.values():
            _assert_no_floats(value)
    elif isinstance(obj, list):
        for value in obj:
            _assert_no_floats(value)


def test_idempotent_reacceptance_is_noop(tmp_path: Path) -> None:
    artifact_path, sidecar_path = _make_valid_fixture(tmp_path)
    first = _accept(tmp_path, artifact_path, sidecar_path)

    artifacts_dir = tmp_path / "artifacts" / "h003_bridge_v0"
    receipt_before = (artifacts_dir / "H003_ACCEPTANCE_V0.json").read_bytes()
    ledger_before = (artifacts_dir / "h003_acceptance_ledger.jsonl").read_bytes()

    second = _accept(tmp_path, artifact_path, sidecar_path)
    assert second["decision"] == "ACCEPTED"
    assert second["idempotent_no_op"] is True
    assert second["acceptance_id"] == first["acceptance_id"]

    assert (artifacts_dir / "h003_acceptance_ledger.jsonl").read_bytes() == ledger_before
    assert (artifacts_dir / "H003_ACCEPTANCE_V0.json").read_bytes() == receipt_before
    rows = [
        json.loads(line)
        for line in (artifacts_dir / "h003_acceptance_ledger.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert len(rows) == 1


def test_existing_acceptance_state_is_verified_before_noop(tmp_path: Path) -> None:
    artifact_path, sidecar_path = _make_valid_fixture(tmp_path)
    _accept(tmp_path, artifact_path, sidecar_path)

    receipt_path = tmp_path / "artifacts" / "h003_bridge_v0" / "H003_ACCEPTANCE_V0.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["decision"] = "REJECTED"
    receipt_path.write_text(canonical_json_dumps(receipt) + "\n", encoding="utf-8")

    with pytest.raises(AcceptanceRejected) as excinfo:
        _accept(tmp_path, artifact_path, sidecar_path)
    assert excinfo.value.code == "ACCEPTANCE_STATE_INVALID"


def test_tampered_artifact_rejected_and_no_partial_writes(tmp_path: Path) -> None:
    artifact_path, sidecar_path = _make_valid_fixture(tmp_path)
    text = artifact_path.read_text()
    # Any byte change (here: flip the causal target) must break the canonical
    # digest and be REJECTED — the artifact is frozen.
    tampered = text.replace('"causal_target_t_plus_1":"LONG"', '"causal_target_t_plus_1":"FLAT"')
    assert tampered != text
    artifact_path.write_text(tampered)

    with pytest.raises(AcceptanceRejected) as excinfo:
        _accept(tmp_path, artifact_path, sidecar_path)
    assert excinfo.value.code == "DIGEST_MISMATCH"

    artifacts_dir = tmp_path / "artifacts" / "h003_bridge_v0"
    assert not (artifacts_dir / "h003_acceptance_ledger.jsonl").exists()
    assert not (artifacts_dir / "H003_ACCEPTANCE_V0.json").exists()
    assert not (artifacts_dir / "H003_ACCEPTANCE_V0.sha256").exists()


def test_float_in_artifact_rejected(tmp_path: Path) -> None:
    artifact_path, sidecar_path = _make_valid_fixture(tmp_path)
    text = artifact_path.read_text()
    floated = text.replace('"numerator":5209', '"numerator":5209.5')
    assert floated != text
    artifact_path.write_text(floated)

    with pytest.raises(AcceptanceRejected) as excinfo:
        _accept(tmp_path, artifact_path, sidecar_path)
    assert excinfo.value.code == "FLOAT_IN_ARTIFACT"

    artifacts_dir = tmp_path / "artifacts" / "h003_bridge_v0"
    assert not (artifacts_dir / "h003_acceptance_ledger.jsonl").exists()


def test_missing_field_rejected(tmp_path: Path) -> None:
    artifact = _valid_artifact()
    # Self-consistent fixture: the digest is computed over the artifact as it
    # will be parsed, so the missing-field schema fault (not a digest fault)
    # is what fires.
    del artifact["close_series"]
    artifact["artifact_digest"] = _canonical_digest(artifact)
    artifact_path, sidecar_path = _write_artifact(tmp_path, artifact)

    with pytest.raises(AcceptanceRejected) as excinfo:
        _accept(tmp_path, artifact_path, sidecar_path)
    assert excinfo.value.code == "SCHEMA_FIELDS"
    assert "close_series" in excinfo.value.detail

    artifacts_dir = tmp_path / "artifacts" / "h003_bridge_v0"
    assert not (artifacts_dir / "h003_acceptance_ledger.jsonl").exists()


def test_sidecar_mismatch_rejected(tmp_path: Path) -> None:
    artifact_path, sidecar_path = _make_valid_fixture(tmp_path)
    sidecar_path.write_text("0" * 64 + "\n", encoding="utf-8")
    with pytest.raises(AcceptanceRejected) as excinfo:
        _accept(tmp_path, artifact_path, sidecar_path)
    assert excinfo.value.code == "SIDECAR_MISMATCH"


def test_authority_escalation_rejected(tmp_path: Path) -> None:
    artifact = _valid_artifact()
    artifact["authority"]["execution"] = "ALLOWED"
    artifact["artifact_digest"] = _canonical_digest(artifact)
    artifact_path, sidecar_path = _write_artifact(tmp_path, artifact)
    with pytest.raises(AcceptanceRejected) as excinfo:
        _accept(tmp_path, artifact_path, sidecar_path)
    assert excinfo.value.code == "AUTHORITY_BLOCK_INVALID"


def test_noncanonical_upstream_commit_rejected(tmp_path: Path) -> None:
    artifact = _valid_artifact()
    artifact["upstream"]["source_commit"] = "b" * 40
    artifact["upstream"]["qntylab_head"] = "b" * 40
    artifact["artifact_digest"] = _canonical_digest(artifact)
    artifact_path, sidecar_path = _write_artifact(tmp_path, artifact)

    with pytest.raises(AcceptanceRejected) as excinfo:
        _accept(tmp_path, artifact_path, sidecar_path)
    assert excinfo.value.code == "UPSTREAM_COMMIT_NOT_CANONICAL"
