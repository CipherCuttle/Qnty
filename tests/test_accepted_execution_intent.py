from __future__ import annotations

import copy
import hashlib
import inspect
import json
from pathlib import Path

import pytest

from quantbot.core.determinism import canonical_json_dumps
from quantbot.paper import accepted_execution_intent as subject

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts" / "h003_bridge_v0"
HANDOFF_PATH = ARTIFACTS / "H003_SIGNAL_INTENT_V0.json"
RECEIPT_PATH = ARTIFACTS / "H003_ACCEPTANCE_V0.json"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _rehash(value: dict, field: str) -> None:
    probe = copy.deepcopy(value)
    probe[field] = ""
    value[field] = hashlib.sha256(
        canonical_json_dumps(probe).encode("utf-8")
    ).hexdigest()


def _inputs() -> tuple[dict, dict]:
    return _read(HANDOFF_PATH), _read(RECEIPT_PATH)


def _bound_inputs(previous: str | None = None, current: str | None = None) -> tuple[dict, dict]:
    handoff, receipt = _inputs()
    if previous is not None:
        handoff["transition"]["previous_target"] = previous
    if current is not None:
        handoff["transition"]["current_target"] = current
        handoff["signal"]["causal_target_t_plus_1"] = current
        handoff["signal"]["raw_signal_at_t"] = 1 if current == "LONG" else -1
    handoff["transition"]["action"] = (
        "NO_ACTION"
        if handoff["transition"]["previous_target"] == handoff["transition"]["current_target"]
        else "TARGET_CHANGE"
    )
    _rehash(handoff, "artifact_digest")
    accepted = receipt["accepted_artifact"]
    accepted["artifact_digest"] = handoff["artifact_digest"]
    accepted["signal_causal_target_t_plus_1"] = handoff["signal"]["causal_target_t_plus_1"]
    accepted["previous_target"] = handoff["transition"]["previous_target"]
    accepted["current_target"] = handoff["transition"]["current_target"]
    accepted["decision_bar_t_open"] = handoff["signal"]["source_bar_timestamp"]
    receipt["ledger"]["record_id"] = f"H003_ACCEPTANCE_V0:{handoff['artifact_digest']}"
    _rehash(receipt, "receipt_digest")
    return handoff, receipt


def test_canonical_accepted_h003_emits_current_no_action_intent() -> None:
    handoff, receipt = _inputs()
    intent = subject.emit_accepted_execution_intent(handoff, receipt)
    assert intent["schema_name"] == "QNTY_ACCEPTED_EXECUTION_INTENT_V1"
    assert intent["decision"] == {
        "current_target": "LONG",
        "effective_source_timestamp": "2026-09-08T20:00:00Z",
        "execution_action_required": False,
        "previous_target": "LONG",
        "transition": "NO_ACTION",
    }
    assert intent["authority"] == subject.AUTHORITY_NONE


def test_flat_to_flat_is_valid_no_action_without_execution_authority() -> None:
    assert subject._expected_transition("FLAT", "FLAT") == ("NO_ACTION", False)


def test_current_artifact_is_canonical_and_replays_byte_identically() -> None:
    handoff, receipt = _inputs()
    first = subject.emit_accepted_execution_intent(handoff, receipt)
    second = subject.emit_accepted_execution_intent(copy.deepcopy(handoff), copy.deepcopy(receipt))
    assert first == second
    output = _read(ARTIFACTS / "QNTY_ACCEPTED_EXECUTION_INTENT_V1.json")
    assert output == first
    assert (ARTIFACTS / "QNTY_ACCEPTED_EXECUTION_INTENT_V1.sha256").read_text().strip() == first["intent_digest"]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda h, r: r.update(decision="REJECTED"),
        lambda h, r: r.update(receipt_digest="0" * 64),
        lambda h, r: h.update(artifact_digest="0" * 64),
        lambda h, r: h["upstream"].update(qntylab_head="0" * 40),
        lambda h, r: h["upstream"].update(candidate_id="SUBSTITUTED"),
        lambda h, r: h["upstream"].update(strategy_id="SUBSTITUTED"),
        lambda h, r: h["upstream"]["parameters"].update(fast=49),
        lambda h, r: h["transition"].update(previous_target="FLAT"),
        lambda h, r: r["accepted_artifact"].update(decision_bar_t_open="2026-09-08T19:00:00Z"),
        lambda h, r: h["authority"].update(execution="ALLOWED"),
        lambda h, r: r["authority"].update(capital="AVAILABLE"),
    ],
)
def test_untrusted_mutations_fail_closed(mutation) -> None:
    handoff, receipt = _inputs()
    mutation(handoff, receipt)
    with pytest.raises(subject.IntentRejected):
        subject.emit_accepted_execution_intent(handoff, receipt)


def test_flat_to_long_requires_action_but_never_emits_buy_or_sell() -> None:
    handoff, receipt = _bound_inputs(previous="FLAT", current="LONG")
    intent = subject.emit_accepted_execution_intent(handoff, receipt)
    assert intent["decision"]["transition"] == "TARGET_CHANGE"
    assert intent["decision"]["execution_action_required"] is True
    assert "BUY" not in json.dumps(intent)
    assert "SELL" not in json.dumps(intent)


def test_long_to_flat_requires_action_but_never_emits_buy_or_sell() -> None:
    handoff, receipt = _bound_inputs(previous="LONG", current="FLAT")
    intent = subject.emit_accepted_execution_intent(handoff, receipt)
    assert intent["decision"]["transition"] == "TARGET_CHANGE"
    assert intent["decision"]["execution_action_required"] is True
    assert "BUY" not in json.dumps(intent)
    assert "SELL" not in json.dumps(intent)


def test_self_rehashed_provenance_substitution_is_not_a_fixture() -> None:
    handoff, receipt = _inputs()
    handoff["close_series"]["path"] = "substituted.csv"
    _rehash(handoff, "artifact_digest")
    with pytest.raises(subject.IntentRejected, match="HANDOFF_DIGEST"):
        subject.emit_accepted_execution_intent(handoff, receipt)


def test_output_has_no_qntyspot_execution_semantics() -> None:
    handoff, receipt = _inputs()
    intent = subject.emit_accepted_execution_intent(handoff, receipt)
    encoded = json.dumps(intent)
    assert "mint" not in encoded.lower()
    assert "venue" not in encoded.lower()
    assert "jupiter" not in encoded.lower()
    assert "side" not in {key.lower() for key in intent}
    assert "wallet" not in encoded.lower()
    assert "private_key" not in encoded.lower()
    assert "signed_transaction" not in encoded.lower()


def test_write_is_idempotent_and_conflicts_fail_closed(tmp_path: Path) -> None:
    handoff, receipt = _inputs()
    intent = subject.emit_accepted_execution_intent(handoff, receipt)
    artifact = tmp_path / "intent.json"
    sidecar = tmp_path / "intent.sha256"
    subject.write_accepted_execution_intent(intent, artifact, sidecar)
    before = artifact.read_bytes(), sidecar.read_bytes()
    subject.write_accepted_execution_intent(intent, artifact, sidecar)
    assert (artifact.read_bytes(), sidecar.read_bytes()) == before
    mutated = copy.deepcopy(intent)
    mutated["decision"]["transition"] = "TARGET_CHANGE"
    with pytest.raises(subject.IntentRejected, match="OUTPUT_INVALID"):
        subject.write_accepted_execution_intent(mutated, artifact, sidecar)
    substituted = copy.deepcopy(intent)
    substituted["provenance"]["upstream_handoff_digest"] = "0" * 64
    _rehash(substituted, "intent_digest")
    with pytest.raises(subject.IntentRejected, match="OUTPUT_INVALID"):
        subject.write_accepted_execution_intent(substituted, artifact, sidecar)
    forged_decision = copy.deepcopy(intent)
    forged_decision["decision"]["previous_target"] = "FLAT"
    forged_decision["decision"]["transition"] = "TARGET_CHANGE"
    forged_decision["decision"]["execution_action_required"] = True
    _rehash(forged_decision, "intent_digest")
    with pytest.raises(subject.IntentRejected, match="OUTPUT_INVALID"):
        subject.write_accepted_execution_intent(forged_decision, artifact, sidecar)
    forged_timestamp = copy.deepcopy(intent)
    forged_timestamp["decision"]["effective_source_timestamp"] = "2099-01-01T00:00:00Z"
    _rehash(forged_timestamp, "intent_digest")
    with pytest.raises(subject.IntentRejected, match="OUTPUT_INVALID"):
        subject.write_accepted_execution_intent(forged_timestamp, artifact, sidecar)


def test_producer_does_not_import_or_recompute_strategy() -> None:
    source = inspect.getsource(subject)
    assert "quantbot.strategy" not in source
    assert "MovingAverage" not in source
    assert "rolling" not in source.lower()
