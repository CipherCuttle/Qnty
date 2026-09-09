"""Emit Qnty's bounded accepted-execution-intent contract.

This module consumes two untrusted, already-produced artifacts:

* the immutable H003_SIGNAL_INTENT_V0 handoff; and
* the immutable H003_ACCEPTANCE_V0 acceptance receipt.

It validates their binding and emits a deterministic Qnty-owned intent. The
intent is an economic target transition only. It deliberately contains no
venue, instrument, quote, sizing, signing, submission, wallet, or capital
authority semantics.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from quantbot.core.determinism import canonical_json_dumps
from quantbot.paper.ledger import write_bytes_atomic

SCHEMA_NAME = "QNTY_ACCEPTED_EXECUTION_INTENT_V1"
SCHEMA_VERSION = "V1"
HANDOFF_SCHEMA = "H003_SIGNAL_INTENT_V0"
ACCEPTANCE_SCHEMA = "H003_ACCEPTANCE_V0"
QNTY_REPOSITORY = "CipherCuttle/Qnty"
QNTYLAB_REPOSITORY = "CipherCuttle/QntyLab"
CANONICAL_QNTY_COMMIT = "cfee758e9b37037c0f6ef33ea43e43df55cf5f2a"
CANONICAL_QNTYLAB_COMMIT = "d7ed51f02e2e9a0a5fde74b54f6b8b9174847c7c"
CANONICAL_HANDOFF_DIGEST = "ca4c90ad3bde51ac5fc6b9dd709bb8b55c1bf26ea602a4ece7f4c4428c5222b1"
CANONICAL_HANDOFF_FILE_SHA256 = "e5a5143cdbac37a0d0769feefef85cbaa54134cdfa0c3568c20f8fec5d2d2f74"
CANONICAL_ACCEPTANCE_RECEIPT_DIGEST = "f6132405f5231a9a31c1e9401c9505deafe08bcdd9d22a504c70b6955450547b"
CANONICAL_EFFECTIVE_SOURCE_TIMESTAMP = "2026-09-08T20:00:00Z"
FLAT_LONG_HANDOFF_DIGEST = "3f0ba9233fd37dacc23a7e64aa3201570bc5843a52378ea76ad3c26d3c8b0903"
FLAT_LONG_RECEIPT_DIGEST = "47cda89f311ae11861b80953a8f88469ca62aa751c5b7afe534437c12239f0cc"
LONG_FLAT_HANDOFF_DIGEST = "cd1486488d8f02e36fc58aaa4fde64409b8f92d4951097ce5eec434b23c2db09"
LONG_FLAT_RECEIPT_DIGEST = "d90e7d78405a368d7064797c27aef9ba8f27387617006a9e6d3d064a5fb17a54"
CANONICAL_ACCEPTANCE_COMMIT = "0cc8fe3b863b2deea548cb01268419c359ff89eb"
CANONICAL_CANDIDATE = "CANDIDATE_H003_MA_48_192_LONG_FLAT"
CANONICAL_STRATEGY = "H003_moving_average"
CANONICAL_VARIANT = "variant_00eb140f03a5f6ab40600160"
CANONICAL_SOURCE_SEMANTIC = "BINANCE_SPOT_SOLUSDT_1H"
ACCEPTANCE_REASON = "H003_SIGNAL_INTENT_V0_VALIDATED_FAIL_CLOSED"

AUTHORITY_NONE = {
    "capital": "NONE",
    "execution": "FORBIDDEN",
    "signing": "NONE",
    "submission": "NONE",
}

_SHA256 = re.compile(r"\A[0-9a-f]{64}\Z")
_GIT_SHA = re.compile(r"\A[0-9a-f]{40}\Z")
_IMMUTABLE_H003_BINDINGS = {
    (CANONICAL_HANDOFF_DIGEST, CANONICAL_ACCEPTANCE_RECEIPT_DIGEST): ("LONG", "LONG"),
    (FLAT_LONG_HANDOFF_DIGEST, FLAT_LONG_RECEIPT_DIGEST): ("FLAT", "LONG"),
    (LONG_FLAT_HANDOFF_DIGEST, LONG_FLAT_RECEIPT_DIGEST): ("LONG", "FLAT"),
}


class IntentRejected(ValueError):
    """Raised whenever an input or immutable output fails closed."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _reject_float(value: Any, where: str) -> None:
    if isinstance(value, float):
        raise IntentRejected("FLOAT_INPUT", f"{where} contains a JSON float")
    if isinstance(value, Mapping):
        for key, child in value.items():
            _reject_float(child, f"{where}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_float(child, f"{where}[{index}]")


def _float_literal(value: str) -> None:
    raise IntentRejected("FLOAT_INPUT", f"JSON float literal {value!r} is forbidden")


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise IntentRejected("DUPLICATE_KEY", f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _load(value: Any, label: str) -> dict[str, Any]:
    """Load a strict object from a path, JSON bytes/text, or mapping."""
    if isinstance(value, Path):
        try:
            raw = value.read_bytes()
        except OSError as exc:
            raise IntentRejected("INPUT_UNREADABLE", f"{label}: {exc}") from exc
    elif isinstance(value, (bytes, bytearray)):
        raw = bytes(value)
    elif isinstance(value, str):
        raw = value.encode("utf-8")
    elif isinstance(value, Mapping):
        _reject_float(value, label)
        raw = canonical_json_dumps(dict(value)).encode("utf-8")
    else:
        raise IntentRejected("INPUT_TYPE", f"{label} must be a path, JSON, or object")

    try:
        text = raw.decode("utf-8")
        parsed = json.loads(
            text, parse_float=_float_literal, object_pairs_hook=_no_duplicate_keys
        )
    except IntentRejected:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IntentRejected("INPUT_JSON", f"{label} is not strict UTF-8 JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise IntentRejected("INPUT_SHAPE", f"{label} must be a JSON object")
    _reject_float(parsed, label)
    return parsed


def _exact_keys(value: Any, expected: set[str], where: str) -> None:
    if not isinstance(value, dict):
        raise IntentRejected("SCHEMA_INVALID", f"{where} must be an object")
    actual = set(value)
    if actual != expected:
        raise IntentRejected(
            "SCHEMA_FIELDS",
            f"{where} keys differ; missing={sorted(expected - actual)} unknown={sorted(actual - expected)}",
        )


def _sha(value: Any, where: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise IntentRejected("DIGEST_INVALID", f"{where} must be lowercase sha256")
    return value


def _git_sha(value: Any, where: str) -> str:
    if not isinstance(value, str) or not _GIT_SHA.fullmatch(value):
        raise IntentRejected("PROVENANCE_INVALID", f"{where} must be a full lowercase git sha")
    return value


def _digest(value: dict[str, Any], field: str) -> str:
    probe = dict(value)
    probe[field] = ""
    return hashlib.sha256(canonical_json_dumps(probe).encode("utf-8")).hexdigest()


def _utc(value: Any, where: str) -> datetime:
    if not isinstance(value, str):
        raise IntentRejected("TIMESTAMP_INVALID", f"{where} must be a string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise IntentRejected("TIMESTAMP_INVALID", f"{where} is not ISO-8601 UTC") from exc
    if parsed.utcoffset() is None:
        raise IntentRejected("TIMESTAMP_INVALID", f"{where} must include a UTC offset")
    return parsed


def _expected_transition(previous_target: str, current_target: str) -> tuple[str, bool]:
    if previous_target not in {"LONG", "FLAT"} or current_target not in {"LONG", "FLAT"}:
        raise IntentRejected("TARGET_INVALID", "transition targets must be LONG or FLAT")
    changed = previous_target != current_target
    return ("TARGET_CHANGE" if changed else "NO_ACTION", changed)


def _validate_handoff(value: Any) -> dict[str, Any]:
    handoff = _load(value, "handoff")
    expected = {
        "artifact_digest", "authority", "bar_window", "close_series", "computed_at",
        "computed_at_rule", "phase", "schema_name", "schema_version", "signal",
        "transition", "upstream",
    }
    _exact_keys(handoff, expected, "handoff")
    if handoff["schema_name"] != HANDOFF_SCHEMA or handoff["schema_version"] != "V0":
        raise IntentRejected("HANDOFF_SCHEMA", "handoff schema/version is not H003_SIGNAL_INTENT_V0/V0")
    if handoff["phase"] != "QNTY_H003_SOL_TO_QNTYSPOT_SHADOW_BRIDGE_V0":
        raise IntentRejected("HANDOFF_PROVENANCE", "handoff phase is not the frozen H003 bridge")
    declared = _sha(handoff["artifact_digest"], "handoff.artifact_digest")
    if (
        declared not in {pair[0] for pair in _IMMUTABLE_H003_BINDINGS}
        or _digest(handoff, "artifact_digest") != declared
    ):
        raise IntentRejected("HANDOFF_DIGEST", "handoff digest is not an immutable canonical H003 fixture")
    if handoff["authority"] != AUTHORITY_NONE:
        raise IntentRejected("AUTHORITY_ESCALATION", "handoff authority is not the frozen no-authority block")
    if not isinstance(handoff["computed_at_rule"], str) or not handoff["computed_at_rule"]:
        raise IntentRejected("HANDOFF_SCHEMA", "computed_at_rule must be non-empty")
    _utc(handoff["computed_at"], "handoff.computed_at")

    upstream = handoff["upstream"]
    _exact_keys(
        upstream,
        {"candidate_id", "strategy_id", "strategy_version", "variant_id", "parameters",
         "source_commit", "source_repository", "source_semantic", "qntylab_head"},
        "handoff.upstream",
    )
    if upstream["candidate_id"] != CANONICAL_CANDIDATE:
        raise IntentRejected("PROVENANCE_MISMATCH", "candidate_id is not canonical")
    if upstream["strategy_id"] != CANONICAL_STRATEGY:
        raise IntentRejected("PROVENANCE_MISMATCH", "strategy_id is not canonical")
    if upstream["variant_id"] != CANONICAL_VARIANT:
        raise IntentRejected("PROVENANCE_MISMATCH", "variant_id is not canonical")
    if upstream["source_repository"] != QNTYLAB_REPOSITORY:
        raise IntentRejected("PROVENANCE_MISMATCH", "source_repository is not QntyLab")
    if upstream["source_semantic"] != CANONICAL_SOURCE_SEMANTIC:
        raise IntentRejected("PROVENANCE_MISMATCH", "source_semantic is not canonical")
    if _git_sha(upstream["qntylab_head"], "handoff.upstream.qntylab_head") != CANONICAL_QNTYLAB_COMMIT:
        raise IntentRejected("PROVENANCE_MISMATCH", "QntyLab commit is not canonical")
    if upstream["source_commit"] != CANONICAL_QNTYLAB_COMMIT:
        raise IntentRejected("PROVENANCE_MISMATCH", "source_commit is not canonical")
    parameters = upstream["parameters"]
    _exact_keys(parameters, {"fast", "slow", "mode"}, "handoff.upstream.parameters")
    if parameters != {"fast": 48, "slow": 192, "mode": "long_flat"}:
        raise IntentRejected("PROVENANCE_MISMATCH", "H003 parameters are not canonical")

    close_series = handoff["close_series"]
    _exact_keys(close_series, {"digest_rule", "path", "sha256"}, "handoff.close_series")
    if close_series["path"] != "data/raw/SOLUSDT-1h.csv" or close_series["digest_rule"] != (
        "sha256 of data/raw/SOLUSDT-1h.csv file bytes (equals manifest sha256)"
    ):
        raise IntentRejected("PROVENANCE_MISMATCH", "close-series source is not canonical")
    _sha(close_series["sha256"], "handoff.close_series.sha256")

    signal = handoff["signal"]
    _exact_keys(
        signal,
        {"causal_target_t_plus_1", "decision_bar_t_open", "decision_rule", "ma192", "ma48",
         "raw_signal_at_t", "source_bar_timestamp"},
        "handoff.signal",
    )
    if signal["causal_target_t_plus_1"] not in {"LONG", "FLAT"}:
        raise IntentRejected("TARGET_INVALID", "causal target must be LONG or FLAT")
    if signal["raw_signal_at_t"] not in {-1, 0, 1} or isinstance(signal["raw_signal_at_t"], bool):
        raise IntentRejected("HANDOFF_SCHEMA", "raw signal must be -1, 0, or 1")
    expected_target = "LONG" if signal["raw_signal_at_t"] == 1 else "FLAT"
    if signal["causal_target_t_plus_1"] != expected_target:
        raise IntentRejected("PROVENANCE_MISMATCH", "raw signal and causal target disagree")
    source_timestamp = _utc(signal["source_bar_timestamp"], "handoff.signal.source_bar_timestamp")
    if source_timestamp != _utc(signal["decision_bar_t_open"], "handoff.signal.decision_bar_t_open"):
        raise IntentRejected("PROVENANCE_MISMATCH", "source and decision timestamps disagree")
    transition = handoff["transition"]
    _exact_keys(transition, {"action", "current_target", "previous_target"}, "handoff.transition")
    expected_transition, _ = _expected_transition(
        transition["previous_target"], transition["current_target"]
    )
    if transition["current_target"] != signal["causal_target_t_plus_1"]:
        raise IntentRejected("PROVENANCE_MISMATCH", "transition current target disagrees with signal")
    if transition["action"] != expected_transition:
        raise IntentRejected("PROVENANCE_MISMATCH", "transition action is not derived correctly")
    return handoff


def _validate_receipt(value: Any, handoff: dict[str, Any]) -> dict[str, Any]:
    receipt = _load(value, "acceptance receipt")
    expected = {
        "acceptance_reason", "accepted_artifact", "accepted_at_utc", "authority", "decision",
        "ledger", "phase", "qnty_head_at_acceptance", "qnty_implementation", "receipt_digest",
        "schema_name", "schema_version", "validators",
    }
    _exact_keys(receipt, expected, "acceptance receipt")
    declared = _sha(receipt["receipt_digest"], "receipt.receipt_digest")
    if (
        declared not in {pair[1] for pair in _IMMUTABLE_H003_BINDINGS}
        or _digest(receipt, "receipt_digest") != declared
    ):
        raise IntentRejected("RECEIPT_DIGEST", "acceptance receipt digest is not an immutable canonical H003 fixture")
    if receipt["schema_name"] != ACCEPTANCE_SCHEMA or receipt["schema_version"] != "V0":
        raise IntentRejected("RECEIPT_SCHEMA", "acceptance receipt schema/version is unexpected")
    if receipt["decision"] != "ACCEPTED":
        raise IntentRejected("ACCEPTANCE_REJECTED", "only ACCEPTED receipts can emit an intent")
    if receipt["acceptance_reason"] != ACCEPTANCE_REASON:
        raise IntentRejected("RECEIPT_SCHEMA", "acceptance reason is not canonical")
    if receipt["authority"] != AUTHORITY_NONE:
        raise IntentRejected("AUTHORITY_ESCALATION", "acceptance receipt grants authority")
    _utc(receipt["accepted_at_utc"], "receipt.accepted_at_utc")
    if receipt["phase"] != "QNTY_H003_SOL_TO_QNTYSPOT_SHADOW_BRIDGE_V0":
        raise IntentRejected("RECEIPT_PROVENANCE", "receipt phase is not canonical")

    accepted = receipt["accepted_artifact"]
    _exact_keys(
        accepted,
        {"artifact_digest", "artifact_file_sha256", "current_target", "decision_bar_t_open",
         "previous_target", "schema_name", "signal_causal_target_t_plus_1", "source_path",
         "source_repo", "upstream_qntylab_head", "upstream_source_commit"},
        "receipt.accepted_artifact",
    )
    binding = _IMMUTABLE_H003_BINDINGS.get((accepted["artifact_digest"], receipt["receipt_digest"]))
    if accepted["artifact_digest"] != handoff["artifact_digest"] or binding is None:
        raise IntentRejected("RECEIPT_BINDING", "receipt is not bound to supplied handoff digest")
    _sha(accepted["artifact_file_sha256"], "receipt.accepted_artifact.artifact_file_sha256")
    if accepted["schema_name"] != HANDOFF_SCHEMA or accepted["source_repo"] != "QntySpot":
        raise IntentRejected("RECEIPT_BINDING", "receipt handoff identity is not canonical")
    if accepted["source_path"] != "qualifications/h003_bridge_v0/H003_SIGNAL_INTENT_V0.json":
        raise IntentRejected("RECEIPT_BINDING", "receipt handoff path is not canonical")
    if accepted["upstream_qntylab_head"] != CANONICAL_QNTYLAB_COMMIT or accepted["upstream_source_commit"] != CANONICAL_QNTYLAB_COMMIT:
        raise IntentRejected("RECEIPT_PROVENANCE", "receipt upstream commit is not canonical")
    signal = handoff["signal"]
    transition = handoff["transition"]
    if accepted["signal_causal_target_t_plus_1"] != signal["causal_target_t_plus_1"]:
        raise IntentRejected("RECEIPT_BINDING", "receipt causal target disagrees with handoff")
    if accepted["previous_target"] != transition["previous_target"] or accepted["current_target"] != transition["current_target"]:
        raise IntentRejected("RECEIPT_BINDING", "receipt targets disagree with handoff")
    if (accepted["previous_target"], accepted["current_target"]) != binding:
        raise IntentRejected("RECEIPT_BINDING", "receipt target pair is not the bound immutable fixture")
    if accepted["decision_bar_t_open"] != signal["source_bar_timestamp"]:
        raise IntentRejected("RECEIPT_BINDING", "receipt source timestamp disagrees with handoff")

    implementation = receipt["qnty_implementation"]
    _exact_keys(implementation, {"commit", "repository", "version"}, "receipt.qnty_implementation")
    if implementation != {"commit": CANONICAL_ACCEPTANCE_COMMIT, "repository": QNTY_REPOSITORY, "version": ACCEPTANCE_SCHEMA}:
        raise IntentRejected("RECEIPT_PROVENANCE", "receipt acceptance implementation lineage is not canonical")
    if receipt["qnty_head_at_acceptance"] != CANONICAL_ACCEPTANCE_COMMIT:
        raise IntentRejected("RECEIPT_PROVENANCE", "receipt Qnty head is not canonical")
    validators = receipt["validators"]
    if not isinstance(validators, dict) or set(validators) != {"authority_block", "byte_sidecar", "canonical_digest", "provenance", "schema"}:
        raise IntentRejected("RECEIPT_SCHEMA", "receipt validator set is not canonical")
    if any(not isinstance(entry, dict) or entry.get("status") != "PASS" for entry in validators.values()):
        raise IntentRejected("RECEIPT_SCHEMA", "receipt contains a failed validator")
    ledger = receipt["ledger"]
    _exact_keys(ledger, {"append_machinery", "id_field", "path", "record_id", "rows_appended_this_run"}, "receipt.ledger")
    if ledger["id_field"] != "acceptance_id" or ledger["path"] != "h003_acceptance_ledger.jsonl" or ledger["rows_appended_this_run"] != 1:
        raise IntentRejected("RECEIPT_SCHEMA", "receipt ledger binding is not canonical")
    if ledger["record_id"] != f"{ACCEPTANCE_SCHEMA}:{accepted['artifact_digest']}":
        raise IntentRejected("RECEIPT_BINDING", "receipt ledger record is not bound to handoff")
    return receipt


def emit_accepted_execution_intent(handoff: Any, acceptance_receipt: Any) -> dict[str, Any]:
    """Validate canonical H003 inputs and return one deterministic intent."""
    handoff_obj = _validate_handoff(handoff)
    receipt = _validate_receipt(acceptance_receipt, handoff_obj)
    transition = handoff_obj["transition"]
    _, changed = _expected_transition(transition["previous_target"], transition["current_target"])
    intent: dict[str, Any] = {
        "schema_name": SCHEMA_NAME,
        "schema_version": SCHEMA_VERSION,
        "intent_digest": "",
        "provenance": {
            "qnty_repository": QNTY_REPOSITORY,
            "qnty_source_commit": CANONICAL_QNTY_COMMIT,
            "qnty_acceptance_schema": ACCEPTANCE_SCHEMA,
            "qnty_acceptance_receipt_digest": receipt["receipt_digest"],
            "qntylab_repository": QNTYLAB_REPOSITORY,
            "qntylab_source_commit": CANONICAL_QNTYLAB_COMMIT,
            "upstream_handoff_schema": HANDOFF_SCHEMA,
            "upstream_handoff_digest": handoff_obj["artifact_digest"],
        },
        "research_identity": {
            "candidate_id": handoff_obj["upstream"]["candidate_id"],
            "strategy_id": handoff_obj["upstream"]["strategy_id"],
            "variant_id": handoff_obj["upstream"]["variant_id"],
            "parameters": handoff_obj["upstream"]["parameters"],
            "source_semantic": handoff_obj["upstream"]["source_semantic"],
        },
        "decision": {
            "previous_target": transition["previous_target"],
            "current_target": transition["current_target"],
            "transition": "TARGET_CHANGE" if changed else "NO_ACTION",
            "execution_action_required": changed,
            "effective_source_timestamp": handoff_obj["signal"]["source_bar_timestamp"],
        },
        "authority": dict(AUTHORITY_NONE),
    }
    intent["intent_digest"] = _digest(intent, "intent_digest")
    return intent


def _validate_output(value: Any) -> dict[str, Any]:
    intent = _load(value, "intent")
    _exact_keys(
        intent,
        {"authority", "decision", "intent_digest", "provenance", "research_identity",
         "schema_name", "schema_version"},
        "intent",
    )
    if intent["schema_name"] != SCHEMA_NAME or intent["schema_version"] != SCHEMA_VERSION:
        raise IntentRejected("OUTPUT_INVALID", "intent schema/version is unexpected")
    declared = _sha(intent["intent_digest"], "intent.intent_digest")
    if _digest(intent, "intent_digest") != declared:
        raise IntentRejected("OUTPUT_INVALID", "intent digest does not authenticate its content")
    if intent["authority"] != AUTHORITY_NONE:
        raise IntentRejected("AUTHORITY_ESCALATION", "intent authority is not the no-authority block")
    provenance = intent["provenance"]
    _exact_keys(
        provenance,
        {"qnty_acceptance_receipt_digest", "qnty_acceptance_schema", "qnty_repository",
         "qnty_source_commit", "qntylab_repository", "qntylab_source_commit",
         "upstream_handoff_digest", "upstream_handoff_schema"},
        "intent.provenance",
    )
    if (
        provenance["qnty_repository"] != QNTY_REPOSITORY
        or provenance["qnty_source_commit"] != CANONICAL_QNTY_COMMIT
        or provenance["qnty_acceptance_schema"] != ACCEPTANCE_SCHEMA
        or provenance["qntylab_repository"] != QNTYLAB_REPOSITORY
        or provenance["qntylab_source_commit"] != CANONICAL_QNTYLAB_COMMIT
        or provenance["upstream_handoff_schema"] != HANDOFF_SCHEMA
    ):
        raise IntentRejected("OUTPUT_INVALID", "intent provenance is not canonical")
    _sha(provenance["qnty_acceptance_receipt_digest"], "intent.provenance.qnty_acceptance_receipt_digest")
    _sha(provenance["upstream_handoff_digest"], "intent.provenance.upstream_handoff_digest")
    binding = _IMMUTABLE_H003_BINDINGS.get(
        (
            provenance["upstream_handoff_digest"],
            provenance["qnty_acceptance_receipt_digest"],
        )
    )
    if (
        provenance["upstream_handoff_digest"],
        provenance["qnty_acceptance_receipt_digest"],
    ) not in _IMMUTABLE_H003_BINDINGS:
        raise IntentRejected("OUTPUT_INVALID", "intent provenance is not bound to an immutable H003 fixture")
    identity = intent["research_identity"]
    _exact_keys(
        identity,
        {"candidate_id", "parameters", "source_semantic", "strategy_id", "variant_id"},
        "intent.research_identity",
    )
    if (
        identity["candidate_id"] != CANONICAL_CANDIDATE
        or identity["strategy_id"] != CANONICAL_STRATEGY
        or identity["variant_id"] != CANONICAL_VARIANT
        or identity["source_semantic"] != CANONICAL_SOURCE_SEMANTIC
        or identity["parameters"] != {"fast": 48, "mode": "long_flat", "slow": 192}
    ):
        raise IntentRejected("OUTPUT_INVALID", "intent research identity is not canonical")
    decision = intent["decision"]
    _exact_keys(
        decision,
        {"current_target", "effective_source_timestamp", "execution_action_required",
         "previous_target", "transition"},
        "intent.decision",
    )
    expected_transition, changed = _expected_transition(
        decision["previous_target"], decision["current_target"]
    )
    if (
        binding != (decision["previous_target"], decision["current_target"])
        or decision["effective_source_timestamp"] != CANONICAL_EFFECTIVE_SOURCE_TIMESTAMP
    ):
        raise IntentRejected("OUTPUT_INVALID", "intent decision is not bound to its immutable H003 fixture")
    if (
        decision["transition"] != expected_transition
        or decision["execution_action_required"] is not changed
    ):
        raise IntentRejected("OUTPUT_INVALID", "intent transition is not derived from targets")
    _utc(decision["effective_source_timestamp"], "intent.decision.effective_source_timestamp")
    return intent


def write_accepted_execution_intent(intent: Mapping[str, Any], artifact_path: Path, sidecar_path: Path) -> None:
    """Persist an intent immutably; repeated identical writes are exact no-ops."""
    candidate = _validate_output(intent)
    data = (canonical_json_dumps(candidate) + "\n").encode("utf-8")
    sidecar = (candidate["intent_digest"] + "\n").encode("ascii")
    artifact_path = Path(artifact_path)
    sidecar_path = Path(sidecar_path)
    if artifact_path.exists() or sidecar_path.exists():
        if not artifact_path.exists() or not sidecar_path.exists() or artifact_path.read_bytes() != data or sidecar_path.read_bytes() != sidecar:
            raise IntentRejected("OUTPUT_CONFLICT", "existing intent artifact is not byte-identical")
        return
    write_bytes_atomic(artifact_path, data)
    write_bytes_atomic(sidecar_path, sidecar)


__all__ = [
    "AUTHORITY_NONE", "CANONICAL_QNTY_COMMIT", "CANONICAL_QNTYLAB_COMMIT", "IntentRejected",
    "SCHEMA_NAME", "emit_accepted_execution_intent", "write_accepted_execution_intent",
]
