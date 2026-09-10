from __future__ import annotations

import copy
import hashlib
import inspect
import json
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

import pytest

from quantbot.core.determinism import canonical_json_dumps
from quantbot.paper.h003_acceptance import accept_h003_signal_intent
from quantbot.paper import accepted_execution_intent_v2 as subject

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts" / "h003_bridge_v0"
HANDOFF = ARTIFACTS / "H003_SIGNAL_INTENT_V0.json"
RECEIPT = ARTIFACTS / "H003_ACCEPTANCE_V0.json"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_canonical(path: Path, value: dict) -> None:
    path.write_bytes((canonical_json_dumps(value) + "\n").encode("utf-8"))


def _rehash(value: dict, field: str) -> None:
    probe = copy.deepcopy(value)
    probe[field] = ""
    value[field] = hashlib.sha256(canonical_json_dumps(probe).encode("utf-8")).hexdigest()


def _historical_acceptance(tmp_path: Path) -> tuple[Path, Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    handoff = _read(HANDOFF)
    handoff["bar_window"]["last_bar_open"] = "2026-09-05T08:00:00Z"
    handoff["bar_window"]["close_of_bar_t"] = "2026-09-05T09:00:00Z"
    # The acceptance validator only requires a consistent positive count that
    # fits the declared window.  This remains an offline contract fixture; no
    # strategy or market-data code is imported.
    first = datetime(2021, 1, 1, tzinfo=timezone.utc)
    last = datetime(2026, 9, 5, 8, tzinfo=timezone.utc)
    handoff["bar_window"]["bar_count"] = (last - first).days * 24 + (last - first).seconds // 3600 + 1
    handoff["computed_at"] = "2026-09-05T09:00:00Z"
    handoff["signal"]["decision_bar_t_open"] = "2026-09-05T08:00:00Z"
    handoff["signal"]["source_bar_timestamp"] = "2026-09-05T08:00:00Z"
    handoff["signal"]["ma48"] = {"numerator": 98729, "denominator": 960}
    handoff["signal"]["ma192"] = {"numerator": 987263, "denominator": 9600}
    handoff["signal"]["raw_signal_at_t"] = 1
    handoff["signal"]["causal_target_t_plus_1"] = "LONG"
    handoff["transition"] = {
        "action": "TARGET_CHANGE", "current_target": "LONG", "previous_target": "FLAT"
    }
    assert Fraction(98729, 960) - Fraction(987263, 9600) == Fraction(9, 3200)

    handoff_path = tmp_path / "H003_SIGNAL_INTENT_V0.json"
    _rehash(handoff, "artifact_digest")
    _write_canonical(handoff_path, handoff)
    handoff_path.with_suffix(".sha256").write_text(handoff["artifact_digest"] + "\n", encoding="utf-8")

    state_dir = tmp_path / "accepted-state"
    receipt = accept_h003_signal_intent(
        handoff_path,
        handoff_path.with_suffix(".sha256"),
        artifacts_dir=state_dir,
        qnty_head=subject.QNTY_ACCEPTANCE_SOURCE_COMMIT,
    )
    receipt_path = Path(receipt["receipt_path"])
    return handoff_path, receipt_path, state_dir


def test_current_long_to_long_is_accepted_as_no_action() -> None:
    intent = subject.emit_accepted_execution_intent_v2(HANDOFF, RECEIPT, ARTIFACTS)
    assert intent["schema_name"] == "QNTY_ACCEPTED_EXECUTION_INTENT_V2"
    assert intent["decision"]["previous_target"] == "LONG"
    assert intent["decision"]["current_target"] == "LONG"
    assert intent["decision"]["transition"] == "NO_ACTION"
    assert intent["decision"]["execution_action_required"] is False
    assert intent["authority"] == subject.AUTHORITY_NONE


def test_genuine_historical_flat_to_long_is_dynamically_admitted(tmp_path: Path) -> None:
    handoff, receipt, state = _historical_acceptance(tmp_path)
    intent = subject.emit_accepted_execution_intent_v2(handoff, receipt, state)
    assert intent["decision"]["previous_target"] == "FLAT"
    assert intent["decision"]["current_target"] == "LONG"
    assert intent["decision"]["transition"] == "TARGET_CHANGE"
    assert intent["decision"]["execution_action_required"] is True
    assert intent["decision"]["effective_source_timestamp"] == "2026-09-05T08:00:00Z"


def test_same_verified_inputs_replay_byte_identically(tmp_path: Path) -> None:
    handoff, receipt, state = _historical_acceptance(tmp_path)
    first = subject.emit_accepted_execution_intent_v2(handoff, receipt, state)
    second = subject.emit_accepted_execution_intent_v2(handoff, receipt, state)
    assert first == second
    assert first["intent_digest"] == second["intent_digest"]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda h, r: h.pop("signal"),
        lambda h, r: h["upstream"].update(source_commit="0" * 40, qntylab_head="0" * 40),
        lambda h, r: h["upstream"].update(candidate_id="WRONG"),
        lambda h, r: h["upstream"].update(strategy_id="WRONG"),
        lambda h, r: h["upstream"].update(variant_id="WRONG"),
        lambda h, r: h["upstream"]["parameters"].update(fast=49),
        lambda h, r: h["signal"].update(raw_signal_at_t=-1, causal_target_t_plus_1="FLAT"),
        lambda h, r: h["transition"].update(previous_target="FLAT", action="NO_ACTION"),
        lambda h, r: h["authority"].update(execution="ALLOWED"),
    ],
)
def test_handoff_mutations_fail_closed(tmp_path: Path, mutation) -> None:
    handoff = _read(HANDOFF)
    receipt = _read(RECEIPT)
    mutation(handoff, receipt)
    path = tmp_path / "handoff.json"
    _rehash(handoff, "artifact_digest")
    _write_canonical(path, handoff)
    path.with_suffix(".sha256").write_text(handoff["artifact_digest"] + "\n", encoding="utf-8")
    receipt_path = tmp_path / "receipt.json"
    _write_canonical(receipt_path, receipt)
    with pytest.raises(subject.IntentRejected):
        subject.emit_accepted_execution_intent_v2(path, receipt_path, ARTIFACTS)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda r: r.update(decision="REJECTED"),
        lambda r: r["accepted_artifact"].update(artifact_digest="0" * 64),
        lambda r: r["accepted_artifact"].update(previous_target="FLAT"),
        lambda r: r["accepted_artifact"].update(decision_bar_t_open="2026-09-08T19:00:00Z"),
        lambda r: r["qnty_implementation"].update(commit="1" * 40),
        lambda r: r["authority"].update(capital="AVAILABLE"),
        lambda r: r["ledger"].update(record_id="H003_ACCEPTANCE_V0:" + "0" * 64),
    ],
)
def test_receipt_mutations_fail_closed(tmp_path: Path, mutation) -> None:
    receipt = _read(RECEIPT)
    mutation(receipt)
    _rehash(receipt, "receipt_digest")
    receipt_path = tmp_path / "receipt.json"
    _write_canonical(receipt_path, receipt)
    with pytest.raises(subject.IntentRejected):
        subject.emit_accepted_execution_intent_v2(HANDOFF, receipt_path, ARTIFACTS)


def test_forged_self_consistent_receipt_absent_from_state_is_rejected(tmp_path: Path) -> None:
    handoff, real_receipt, _state = _historical_acceptance(tmp_path / "real")
    forged = _read(real_receipt)
    forged["accepted_at_utc"] = "2026-09-05T09:30:00Z"
    _rehash(forged, "receipt_digest")
    forged_path = tmp_path / "forged.json"
    _write_canonical(forged_path, forged)
    empty_state = tmp_path / "empty-state"
    empty_state.mkdir()
    with pytest.raises(subject.IntentRejected, match="RECEIPT_ABSENT|ACCEPTANCE_STATE"):
        subject.emit_accepted_execution_intent_v2(handoff, forged_path, empty_state)


def test_duplicate_receipt_keys_fail_closed(tmp_path: Path) -> None:
    receipt_path = tmp_path / "duplicate.json"
    raw = RECEIPT.read_text(encoding="utf-8").replace(
        '"decision":"ACCEPTED"', '"decision":"ACCEPTED","decision":"ACCEPTED"', 1
    )
    receipt_path.write_text(raw, encoding="utf-8")
    with pytest.raises(subject.IntentRejected, match="DUPLICATE_KEY"):
        subject.emit_accepted_execution_intent_v2(HANDOFF, receipt_path, ARTIFACTS)


def test_ledger_substitution_and_contradictory_state_fail_closed(tmp_path: Path) -> None:
    handoff, receipt, state = _historical_acceptance(tmp_path)
    ledger_path = state / subject.LEDGER_FILENAME
    ledger_path.write_text(ledger_path.read_text() + ledger_path.read_text(), encoding="utf-8")
    with pytest.raises(subject.IntentRejected, match="contradictory|exactly once"):
        subject.emit_accepted_execution_intent_v2(handoff, receipt, state)


def test_unrelated_malformed_ledger_row_is_not_ignored(tmp_path: Path) -> None:
    handoff, receipt, state = _historical_acceptance(tmp_path)
    ledger_path = state / subject.LEDGER_FILENAME
    bad = json.loads(ledger_path.read_text(encoding="utf-8").splitlines()[0])
    bad["artifact_digest"] = "0" * 64
    bad["acceptance_id"] = "H003_ACCEPTANCE_V0:" + "0" * 64
    bad["decision"] = "REJECTED"
    with ledger_path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(bad, sort_keys=True) + "\n")
    with pytest.raises(subject.IntentRejected, match="invalid|accepted H003"):
        subject.emit_accepted_execution_intent_v2(handoff, receipt, state)


def test_output_has_only_directional_semantics_and_no_authority() -> None:
    source = inspect.getsource(subject)
    assert "quantbot.strategy" not in source
    assert "MovingAverage" not in source
    assert "_IMMUTABLE_H003_BINDINGS" not in source
    intent = subject.emit_accepted_execution_intent_v2(HANDOFF, RECEIPT, ARTIFACTS)
    encoded = json.dumps(intent).lower()
    for term in ("buy", "sell", "usdc", "wsol", "mint", "venue", "jupiter", "size", "slippage", "wallet", "transaction"):
        assert term not in encoded
    assert intent["authority"] == {"capital": "NONE", "execution": "FORBIDDEN", "signing": "NONE", "submission": "NONE"}


def test_output_validator_rejects_semantic_leakage_and_digest_mutation() -> None:
    intent = subject.emit_accepted_execution_intent_v2(HANDOFF, RECEIPT, ARTIFACTS)
    leaked = copy.deepcopy(intent)
    leaked["research_identity"]["candidate_id"] = "BUY"
    _rehash(leaked, "intent_digest")
    with pytest.raises(subject.IntentRejected):
        subject.validate_accepted_execution_intent_v2(leaked)
    mutated = copy.deepcopy(intent)
    mutated["intent_digest"] = "0" * 64
    with pytest.raises(subject.IntentRejected):
        subject.validate_accepted_execution_intent_v2(mutated)
