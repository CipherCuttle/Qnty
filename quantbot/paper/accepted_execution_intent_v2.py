"""Emit the dynamically-proven Qnty accepted-execution-intent V2 contract.

V2 consumes an H003 handoff and receipt as untrusted files, then requires the
receipt to be present in Qnty's durable H003 acceptance state.  A receipt's
self-authenticating digest is therefore necessary but not sufficient: the
persisted receipt and its append-only acceptance row must agree exactly.

This module carries no execution, signing, venue, wallet, or capital authority.
It intentionally has no event-specific digest allowlist.  H003 field
validation is delegated to the canonical Qnty acceptance validator, while the
durable-state proof is performed here before an intent is emitted.
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
from quantbot.paper import ledger
from quantbot.paper.h003_acceptance import (
    ACCEPTANCE_DECISION,
    ACCEPTANCE_REASON,
    ARTIFACT_SOURCE_PATH,
    ARTIFACT_SOURCE_REPO,
    CANONICAL_QNTYLAB_COMMIT,
    PHASE,
    QNTY_IMPLEMENTATION_VERSION,
    RECEIPT_AUTHORITY,
    RECEIPT_FILENAME,
    RECEIPT_SCHEMA_NAME,
    RECEIPT_SIDECAR_FILENAME,
    SCHEMA_NAME as HANDOFF_SCHEMA,
    validate_h003_signal_intent,
)

SCHEMA_NAME = "QNTY_ACCEPTED_EXECUTION_INTENT_V2"
SCHEMA_VERSION = "V2"
QNTY_REPOSITORY = "CipherCuttle/Qnty"
QNTYLAB_REPOSITORY = "CipherCuttle/QntyLab"
LEDGER_FILENAME = "h003_acceptance_ledger.jsonl"
LEDGER_RECORD_SCHEMA = "H003_ACCEPTANCE_RECORD_V0"
QNTY_ACCEPTANCE_SOURCE_COMMIT = "0cc8fe3b863b2deea548cb01268419c359ff89eb"

AUTHORITY_NONE = {
    "capital": "NONE",
    "execution": "FORBIDDEN",
    "signing": "NONE",
    "submission": "NONE",
}

_SHA256 = re.compile(r"\A[0-9a-f]{64}\Z")
_RECEIPT_FIELDS = {
    "acceptance_reason", "accepted_artifact", "accepted_at_utc", "authority", "decision",
    "ledger", "phase", "qnty_head_at_acceptance", "qnty_implementation", "receipt_digest",
    "schema_name", "schema_version", "validators",
}
_ACCEPTED_ARTIFACT_FIELDS = {
    "artifact_digest", "artifact_file_sha256", "current_target", "decision_bar_t_open",
    "previous_target", "schema_name", "signal_causal_target_t_plus_1", "source_path",
    "source_repo", "upstream_qntylab_head", "upstream_source_commit",
}
_RECEIPT_LEDGER_FIELDS = {
    "append_machinery", "id_field", "path", "record_id", "rows_appended_this_run",
}
_IMPLEMENTATION_FIELDS = {"commit", "repository", "version"}
_LEDGER_FIELDS = {
    "acceptance_id", "acceptance_reason", "accepted_at_utc", "artifact_digest",
    "artifact_file_sha256", "artifact_schema", "artifact_source_path", "artifact_source_repo",
    "authority", "decision", "phase", "qnty_head_at_acceptance", "schema_name",
    "upstream_qntylab_head", "upstream_source_commit",
}
_FORBIDDEN_TERMS = (
    "buy", "sell", "usdc", "wsol", "mint", "venue", "jupiter", "size", "slippage",
    "wallet", "private_key", "signed_transaction", "transaction",
)


class IntentRejected(ValueError):
    """Raised whenever V2 input, state, or output fails closed."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _no_float(value: str) -> None:
    raise IntentRejected("FLOAT_INPUT", f"JSON float literal {value!r} is forbidden")


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise IntentRejected("DUPLICATE_KEY", f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_floats(value: Any, where: str) -> None:
    if isinstance(value, float):
        raise IntentRejected("FLOAT_INPUT", f"{where} contains a JSON float")
    if isinstance(value, Mapping):
        for key, child in value.items():
            _reject_floats(child, f"{where}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_floats(child, f"{where}[{index}]")


def _load_object(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise IntentRejected("INPUT_UNREADABLE", f"{label}: {exc}") from exc
    try:
        parsed = json.loads(
            raw.decode("utf-8"), parse_float=_no_float, object_pairs_hook=_no_duplicate_keys
        )
    except IntentRejected:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IntentRejected("INPUT_JSON", f"{label} is not strict UTF-8 JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise IntentRejected("INPUT_SHAPE", f"{label} must be a JSON object")
    _reject_floats(parsed, label)
    if raw != (canonical_json_dumps(parsed) + "\n").encode("utf-8"):
        raise IntentRejected("NON_CANONICAL_BYTES", f"{label} is not canonical JSON bytes")
    return parsed, raw


def _exact(value: Any, expected: set[str], where: str) -> None:
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


def _utc(value: Any, where: str) -> datetime:
    if not isinstance(value, str):
        raise IntentRejected("TIMESTAMP_INVALID", f"{where} must be a string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise IntentRejected("TIMESTAMP_INVALID", f"{where} is not ISO-8601") from exc
    if parsed.utcoffset() is None:
        raise IntentRejected("TIMESTAMP_INVALID", f"{where} must include a UTC offset")
    return parsed


def _digest(value: dict[str, Any], field: str) -> str:
    probe = dict(value)
    probe[field] = ""
    return hashlib.sha256(canonical_json_dumps(probe).encode("utf-8")).hexdigest()


def _path(value: Any, label: str) -> Path:
    if not isinstance(value, (Path, str)):
        raise IntentRejected("INPUT_TYPE", f"{label} must be a filesystem path")
    return Path(value)


def _validate_handoff(path: Path) -> tuple[dict[str, Any], str]:
    sidecar = path.with_suffix(".sha256")
    try:
        handoff, _validators, file_sha = validate_h003_signal_intent(path, sidecar)
    except Exception as exc:
        # Preserve the canonical machine-readable reason while avoiding a
        # dependency on the acceptance exception type in the V2 contract.
        if hasattr(exc, "code") and hasattr(exc, "detail"):
            raise IntentRejected(str(exc.code), str(exc.detail)) from exc
        raise IntentRejected("HANDOFF_INVALID", str(exc)) from exc
    return handoff, file_sha


def _validate_receipt(receipt: dict[str, Any], handoff: dict[str, Any], handoff_file_sha: str) -> None:
    _exact(receipt, _RECEIPT_FIELDS, "acceptance receipt")
    if receipt["schema_name"] != RECEIPT_SCHEMA_NAME or receipt["schema_version"] != "V0":
        raise IntentRejected("RECEIPT_SCHEMA", "receipt schema/version is not H003_ACCEPTANCE_V0/V0")
    declared = _sha(receipt["receipt_digest"], "receipt.receipt_digest")
    if _digest(receipt, "receipt_digest") != declared:
        raise IntentRejected("RECEIPT_DIGEST", "receipt digest does not recompute")
    if receipt["decision"] != ACCEPTANCE_DECISION:
        raise IntentRejected("ACCEPTANCE_REJECTED", "only ACCEPTED receipts can emit an intent")
    if receipt["acceptance_reason"] != ACCEPTANCE_REASON or receipt["authority"] != RECEIPT_AUTHORITY:
        raise IntentRejected("RECEIPT_PROVENANCE", "receipt reason or authority block is not canonical")
    if receipt["phase"] != PHASE:
        raise IntentRejected("RECEIPT_PROVENANCE", "receipt phase is not canonical")
    _utc(receipt["accepted_at_utc"], "receipt.accepted_at_utc")

    accepted = receipt["accepted_artifact"]
    _exact(accepted, _ACCEPTED_ARTIFACT_FIELDS, "receipt.accepted_artifact")
    if accepted["artifact_digest"] != handoff["artifact_digest"]:
        raise IntentRejected("RECEIPT_BINDING", "receipt is not bound to supplied handoff digest")
    if accepted["artifact_file_sha256"] != handoff_file_sha:
        raise IntentRejected("RECEIPT_BINDING", "receipt file digest differs from supplied handoff bytes")
    if accepted["schema_name"] != HANDOFF_SCHEMA or accepted["source_repo"] != ARTIFACT_SOURCE_REPO:
        raise IntentRejected("RECEIPT_BINDING", "receipt handoff identity is not canonical")
    if accepted["source_path"] != ARTIFACT_SOURCE_PATH:
        raise IntentRejected("RECEIPT_BINDING", "receipt handoff path is not canonical")
    if accepted["upstream_qntylab_head"] != CANONICAL_QNTYLAB_COMMIT or accepted["upstream_source_commit"] != CANONICAL_QNTYLAB_COMMIT:
        raise IntentRejected("RECEIPT_PROVENANCE", "receipt QntyLab commit is not canonical")
    transition = handoff["transition"]
    signal = handoff["signal"]
    if accepted["signal_causal_target_t_plus_1"] != signal["causal_target_t_plus_1"]:
        raise IntentRejected("RECEIPT_BINDING", "receipt target differs from handoff signal")
    if accepted["previous_target"] != transition["previous_target"] or accepted["current_target"] != transition["current_target"]:
        raise IntentRejected("RECEIPT_BINDING", "receipt transition differs from handoff")
    if accepted["decision_bar_t_open"] != signal["source_bar_timestamp"]:
        raise IntentRejected("RECEIPT_BINDING", "receipt timestamp differs from handoff")

    implementation = receipt["qnty_implementation"]
    _exact(implementation, _IMPLEMENTATION_FIELDS, "receipt.qnty_implementation")
    expected_implementation = {
        "commit": QNTY_ACCEPTANCE_SOURCE_COMMIT,
        "repository": QNTY_REPOSITORY,
        "version": QNTY_IMPLEMENTATION_VERSION,
    }
    if implementation != expected_implementation or receipt["qnty_head_at_acceptance"] != QNTY_ACCEPTANCE_SOURCE_COMMIT:
        raise IntentRejected("RECEIPT_PROVENANCE", "receipt acceptance implementation identity is not canonical")

    validators = receipt["validators"]
    if not isinstance(validators, dict) or not validators or any(
        not isinstance(item, dict) or item.get("status") != "PASS" for item in validators.values()
    ):
        raise IntentRejected("RECEIPT_SCHEMA", "receipt contains a failed or missing validator")
    ledger_binding = receipt["ledger"]
    _exact(ledger_binding, _RECEIPT_LEDGER_FIELDS, "receipt.ledger")
    if ledger_binding["path"] != LEDGER_FILENAME or ledger_binding["id_field"] != "acceptance_id":
        raise IntentRejected("RECEIPT_SCHEMA", "receipt ledger path/id field is not canonical")
    expected_record_id = f"{RECEIPT_SCHEMA_NAME}:{handoff['artifact_digest']}"
    if ledger_binding["record_id"] != expected_record_id or ledger_binding["rows_appended_this_run"] != 1:
        raise IntentRejected("RECEIPT_BINDING", "receipt ledger record is not deterministically bound")


def _load_acceptance_ledger(path: Path) -> list[dict[str, Any]]:
    try:
        raw = path.read_bytes()
    except (OSError, UnicodeError) as exc:
        raise IntentRejected("ACCEPTANCE_STATE_UNREADABLE", f"acceptance ledger: {exc}") from exc
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(
                line.decode("utf-8"), parse_float=_no_float, object_pairs_hook=_no_duplicate_keys
            )
        except IntentRejected:
            raise
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise IntentRejected("ACCEPTANCE_STATE_INVALID", f"ledger line {line_number} is invalid JSON") from exc
        if not isinstance(row, dict):
            raise IntentRejected("ACCEPTANCE_STATE_INVALID", f"ledger line {line_number} is not an object")
        _reject_floats(row, f"ledger line {line_number}")
        _exact(row, _LEDGER_FIELDS, f"ledger line {line_number}")
        if row["schema_name"] != LEDGER_RECORD_SCHEMA or row["artifact_schema"] != HANDOFF_SCHEMA:
            raise IntentRejected("ACCEPTANCE_STATE_INVALID", f"ledger line {line_number} has an invalid schema")
        if row["phase"] != PHASE or row["decision"] != ACCEPTANCE_DECISION:
            raise IntentRejected("ACCEPTANCE_STATE_INVALID", f"ledger line {line_number} is not an accepted H003 record")
        if row["artifact_source_repo"] != ARTIFACT_SOURCE_REPO or row["artifact_source_path"] != ARTIFACT_SOURCE_PATH:
            raise IntentRejected("ACCEPTANCE_STATE_INVALID", f"ledger line {line_number} has an invalid artifact source")
        if row["acceptance_reason"] != ACCEPTANCE_REASON or row["authority"] != RECEIPT_AUTHORITY:
            raise IntentRejected("ACCEPTANCE_STATE_INVALID", f"ledger line {line_number} has invalid acceptance provenance")
        _sha(row["artifact_digest"], f"ledger line {line_number}.artifact_digest")
        _sha(row["artifact_file_sha256"], f"ledger line {line_number}.artifact_file_sha256")
        if row["qnty_head_at_acceptance"] != QNTY_ACCEPTANCE_SOURCE_COMMIT:
            raise IntentRejected("ACCEPTANCE_STATE_INVALID", f"ledger line {line_number} has an invalid Qnty implementation")
        if row["upstream_qntylab_head"] != CANONICAL_QNTYLAB_COMMIT or row["upstream_source_commit"] != CANONICAL_QNTYLAB_COMMIT:
            raise IntentRejected("ACCEPTANCE_STATE_INVALID", f"ledger line {line_number} has an invalid QntyLab provenance")
        if row["acceptance_id"] != f"{RECEIPT_SCHEMA_NAME}:{row['artifact_digest']}":
            raise IntentRejected("ACCEPTANCE_STATE_INVALID", f"ledger line {line_number} id is not bound to its artifact")
        _utc(row["accepted_at_utc"], f"ledger line {line_number}.accepted_at_utc")
        rows.append(row)
    if not rows:
        raise IntentRejected("RECEIPT_ABSENT", "canonical Qnty acceptance ledger is empty")
    ids = [row["acceptance_id"] for row in rows]
    digests = [row["artifact_digest"] for row in rows]
    if len(ids) != len(set(ids)) or len(digests) != len(set(digests)):
        raise IntentRejected("ACCEPTANCE_STATE_INVALID", "acceptance ledger contains contradictory duplicate identities")
    return rows


def _verify_durable_acceptance(
    receipt: dict[str, Any], handoff: dict[str, Any], state_dir: Path
) -> None:
    if not state_dir.is_dir():
        raise IntentRejected("RECEIPT_ABSENT", "canonical Qnty acceptance state directory is absent")
    persisted_receipt_path = state_dir / RECEIPT_FILENAME
    persisted_sidecar_path = state_dir / RECEIPT_SIDECAR_FILENAME
    if not persisted_receipt_path.is_file():
        raise IntentRejected("RECEIPT_ABSENT", "canonical Qnty acceptance receipt is absent")
    persisted, _persisted_bytes = _load_object(persisted_receipt_path, "persisted acceptance receipt")
    if persisted != receipt:
        raise IntentRejected("ACCEPTANCE_STATE_INVALID", "supplied receipt does not match persisted Qnty receipt")
    digest = _sha(persisted["receipt_digest"], "persisted receipt.receipt_digest")
    try:
        sidecar_bytes = persisted_sidecar_path.read_bytes()
    except (OSError, UnicodeError) as exc:
        raise IntentRejected("ACCEPTANCE_STATE_UNREADABLE", f"receipt sidecar: {exc}") from exc
    if sidecar_bytes != (digest + "\n").encode("ascii"):
        raise IntentRejected("ACCEPTANCE_STATE_INVALID", "persisted receipt sidecar does not match receipt")

    rows = _load_acceptance_ledger(state_dir / LEDGER_FILENAME)
    record_id = receipt["ledger"]["record_id"]
    matches = [row for row in rows if row["acceptance_id"] == record_id]
    if len(matches) != 1:
        raise IntentRejected("RECEIPT_ABSENT", "receipt is not present exactly once in Qnty acceptance state")
    row = matches[0]
    accepted = receipt["accepted_artifact"]
    expected = {
        "acceptance_id": record_id,
        "schema_name": LEDGER_RECORD_SCHEMA,
        "phase": PHASE,
        "decision": ACCEPTANCE_DECISION,
        "accepted_at_utc": receipt["accepted_at_utc"],
        "artifact_schema": HANDOFF_SCHEMA,
        "artifact_digest": handoff["artifact_digest"],
        "artifact_file_sha256": accepted["artifact_file_sha256"],
        "artifact_source_repo": ARTIFACT_SOURCE_REPO,
        "artifact_source_path": ARTIFACT_SOURCE_PATH,
        "upstream_qntylab_head": CANONICAL_QNTYLAB_COMMIT,
        "upstream_source_commit": CANONICAL_QNTYLAB_COMMIT,
        "acceptance_reason": ACCEPTANCE_REASON,
        "qnty_head_at_acceptance": QNTY_ACCEPTANCE_SOURCE_COMMIT,
        "authority": RECEIPT_AUTHORITY,
    }
    if row != expected:
        raise IntentRejected("ACCEPTANCE_STATE_INVALID", "ledger row is not bound to supplied receipt and handoff")


def emit_accepted_execution_intent_v2(
    handoff: Path | str,
    acceptance_receipt: Path | str,
    acceptance_state_dir: Path | str,
) -> dict[str, Any]:
    """Validate the dynamic provenance chain and return one deterministic V2 intent."""
    handoff_path = _path(handoff, "handoff")
    receipt_path = _path(acceptance_receipt, "acceptance receipt")
    state_dir = _path(acceptance_state_dir, "acceptance state")
    handoff_obj, handoff_file_sha = _validate_handoff(handoff_path)
    receipt_obj, _ = _load_object(receipt_path, "acceptance receipt")
    _validate_receipt(receipt_obj, handoff_obj, handoff_file_sha)
    _verify_durable_acceptance(receipt_obj, handoff_obj, state_dir)

    transition = handoff_obj["transition"]
    changed = transition["previous_target"] != transition["current_target"]
    intent: dict[str, Any] = {
        "schema_name": SCHEMA_NAME,
        "schema_version": SCHEMA_VERSION,
        "intent_digest": "",
        "provenance": {
            "qnty_repository": QNTY_REPOSITORY,
            "qnty_acceptance_source_commit": QNTY_ACCEPTANCE_SOURCE_COMMIT,
            "qnty_acceptance_schema": RECEIPT_SCHEMA_NAME,
            "qnty_acceptance_receipt_digest": receipt_obj["receipt_digest"],
            "qnty_acceptance_record_id": receipt_obj["ledger"]["record_id"],
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


def _reject_forbidden_terms(value: Any, where: str = "intent") -> None:
    if isinstance(value, str):
        lowered = value.lower()
        if any(term in lowered for term in _FORBIDDEN_TERMS):
            raise IntentRejected("OUTPUT_INVALID", f"forbidden execution semantic in {where}")
    elif isinstance(value, Mapping):
        for key, child in value.items():
            _reject_forbidden_terms(key, f"{where}.key")
            _reject_forbidden_terms(child, f"{where}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_forbidden_terms(child, f"{where}[{index}]")


def validate_accepted_execution_intent_v2(value: Any) -> dict[str, Any]:
    """Validate an emitted V2 object without consulting external state."""
    if not isinstance(value, Mapping):
        raise IntentRejected("OUTPUT_INVALID", "intent must be an object")
    _reject_floats(value, "intent")
    intent = dict(value)
    _exact(intent, {"authority", "decision", "intent_digest", "provenance", "research_identity", "schema_name", "schema_version"}, "intent")
    if intent["schema_name"] != SCHEMA_NAME or intent["schema_version"] != SCHEMA_VERSION:
        raise IntentRejected("OUTPUT_INVALID", "intent schema/version is unexpected")
    declared = _sha(intent["intent_digest"], "intent.intent_digest")
    if _digest(intent, "intent_digest") != declared:
        raise IntentRejected("OUTPUT_INVALID", "intent digest does not authenticate content")
    if intent["authority"] != AUTHORITY_NONE:
        raise IntentRejected("AUTHORITY_ESCALATION", "intent authority is not the no-authority block")
    _reject_forbidden_terms(intent)
    provenance = intent["provenance"]
    _exact(provenance, {"qnty_acceptance_receipt_digest", "qnty_acceptance_record_id", "qnty_acceptance_schema", "qnty_acceptance_source_commit", "qnty_repository", "qntylab_repository", "qntylab_source_commit", "upstream_handoff_digest", "upstream_handoff_schema"}, "intent.provenance")
    if provenance["qnty_repository"] != QNTY_REPOSITORY or provenance["qnty_acceptance_schema"] != RECEIPT_SCHEMA_NAME or provenance["qnty_acceptance_source_commit"] != QNTY_ACCEPTANCE_SOURCE_COMMIT or provenance["qntylab_repository"] != QNTYLAB_REPOSITORY or provenance["qntylab_source_commit"] != CANONICAL_QNTYLAB_COMMIT or provenance["upstream_handoff_schema"] != HANDOFF_SCHEMA:
        raise IntentRejected("OUTPUT_INVALID", "intent provenance is not canonical")
    _sha(provenance["qnty_acceptance_receipt_digest"], "intent.provenance.qnty_acceptance_receipt_digest")
    _sha(provenance["upstream_handoff_digest"], "intent.provenance.upstream_handoff_digest")
    if not isinstance(provenance["qnty_acceptance_record_id"], str) or provenance["qnty_acceptance_record_id"] != f"{RECEIPT_SCHEMA_NAME}:{provenance['upstream_handoff_digest']}":
        raise IntentRejected("OUTPUT_INVALID", "intent acceptance record id is not bound to handoff")

    identity = intent["research_identity"]
    _exact(identity, {"candidate_id", "parameters", "source_semantic", "strategy_id", "variant_id"}, "intent.research_identity")
    if identity["candidate_id"] != "CANDIDATE_H003_MA_48_192_LONG_FLAT" or identity["strategy_id"] != "H003_moving_average" or identity["variant_id"] != "variant_00eb140f03a5f6ab40600160" or identity["source_semantic"] != "BINANCE_SPOT_SOLUSDT_1H" or identity["parameters"] != {"fast": 48, "mode": "long_flat", "slow": 192}:
        raise IntentRejected("OUTPUT_INVALID", "intent research identity is not canonical")
    decision = intent["decision"]
    _exact(decision, {"current_target", "effective_source_timestamp", "execution_action_required", "previous_target", "transition"}, "intent.decision")
    if decision["previous_target"] not in {"LONG", "FLAT"} or decision["current_target"] not in {"LONG", "FLAT"}:
        raise IntentRejected("OUTPUT_INVALID", "intent targets are invalid")
    changed = decision["previous_target"] != decision["current_target"]
    if decision["transition"] != ("TARGET_CHANGE" if changed else "NO_ACTION") or decision["execution_action_required"] is not changed:
        raise IntentRejected("OUTPUT_INVALID", "intent transition is not derived from targets")
    _utc(decision["effective_source_timestamp"], "intent.decision.effective_source_timestamp")
    return intent


def write_accepted_execution_intent_v2(intent: Mapping[str, Any], artifact_path: Path, sidecar_path: Path) -> None:
    """Persist a validated V2 intent; repeated identical writes are no-ops."""
    candidate = validate_accepted_execution_intent_v2(intent)
    data = (canonical_json_dumps(candidate) + "\n").encode("utf-8")
    sidecar = (candidate["intent_digest"] + "\n").encode("ascii")
    if artifact_path.exists() or sidecar_path.exists():
        if not artifact_path.exists() or not sidecar_path.exists() or artifact_path.read_bytes() != data or sidecar_path.read_bytes() != sidecar:
            raise IntentRejected("OUTPUT_CONFLICT", "existing V2 intent is not byte-identical")
        return
    ledger.write_bytes_atomic(Path(artifact_path), data)
    ledger.write_bytes_atomic(Path(sidecar_path), sidecar)


__all__ = [
    "AUTHORITY_NONE", "IntentRejected", "SCHEMA_NAME", "SCHEMA_VERSION",
    "emit_accepted_execution_intent_v2", "validate_accepted_execution_intent_v2",
    "write_accepted_execution_intent_v2",
]
