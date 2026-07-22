"""Pure projection of the frozen legacy continuity packet into control state.

The current legacy packet is receipt index 31.  The one documented mapping is
``state_revision = receipt_index + 1``: index 31 therefore projects to revision
32.  Inputs are documents supplied by the caller; this module does not inspect
the repository, environment, process, network, or Git state.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from .state import ControlState, load_and_validate_control_state

_PATH_RE = re.compile(r"^(?!/)(?!.*(?:^|/)\.\.(?:/|$))[A-Za-z0-9._/-]+$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_TASK_ID = "RECOVER_OR_RETIRE_CANDIDATE1_V0_FROZEN_INPUT"
_PROTOCOL_ID = "real_btc_candidate1_train_mechanism_decomposition_v0"
_CURRENT_RECEIPT_INDEX = 31
_REQUIRED_EFFECTIVE_AMENDMENTS = frozenset(
    {
        "docs/control/amendments/candidate1_h001_temporal_causality_activation_v001.json",
        "docs/control/amendments/candidate1_h001_synthetic_null_calibration_spec_freeze_activation_v001.json",
        "docs/control/amendments/candidate1_h001_synthetic_null_calibration_execution_governance_v001.json",
        "docs/control/amendments/candidate1_h001_synthetic_null_calibration_numerical_conventions_amendment_governance_v001.json",
        "docs/control/amendments/candidate1_h001_synthetic_null_calibration_rng_runtime_specification_amendment_governance_v001.json",
        "docs/control/amendments/candidate1_h001_synthetic_null_calibration_rng_runtime_specification_amendment_activation_v001.json",
    }
)


@dataclass(frozen=True)
class LegacyDocument:
    path: str
    raw: bytes


class LegacyAdapterError(ValueError):
    def __init__(self, code: str, path: str, message: str):
        super().__init__(f"{code} at {path}: {message}")
        self.code = code
        self.path = path


def _fail(code: str, path: str, message: str) -> None:
    raise LegacyAdapterError(code, path, message)


def _safe_path(path: object, label: str) -> str:
    if type(path) is not str or not _PATH_RE.fullmatch(path) or "\\" in path:
        _fail("INVALID_LEGACY_PATH", label, "must be a safe repository-relative path")
    return path


def _load(document: LegacyDocument, label: str) -> dict:
    if type(document) is not LegacyDocument:
        _fail("LEGACY_WRONG_TYPE", label, "must be a LegacyDocument")
    _safe_path(document.path, f"{label}.path")
    if type(document.raw) is not bytes:
        _fail("LEGACY_WRONG_TYPE", f"{label}.raw", "must be bytes")

    def no_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                _fail("DUPLICATE_LEGACY_KEY", label, f"duplicate key: {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(document.raw.decode("utf-8"), object_pairs_hook=no_duplicates)
    except UnicodeDecodeError as exc:
        _fail("INVALID_LEGACY_JSON", label, str(exc))
    except json.JSONDecodeError as exc:
        _fail("INVALID_LEGACY_JSON", label, str(exc))
    if type(value) is not dict:
        _fail("LEGACY_WRONG_TYPE", label, "top-level document must be an object")
    return value


def _required(obj: dict, key: str, path: str, expected_type: type | None = None):
    if key not in obj:
        _fail("LEGACY_MISSING_FIELD", f"{path}.{key}", "missing required field")
    value = obj[key]
    if expected_type is not None and type(value) is not expected_type:
        _fail("LEGACY_WRONG_TYPE", f"{path}.{key}", f"must be {expected_type.__name__}")
    return value


def _has_authority_claim(value: object) -> bool:
    if isinstance(value, dict):
        return any(_has_authority_claim(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_authority_claim(item) for item in value)
    if type(value) is not str:
        return False
    upper = value.upper()
    return any(word in upper for word in ("PERMITTED", "APPROVED", "ENABLED", "LIVE-CAPABLE")) or (
        "AUTHORIZED" in upper and "ONLY" not in upper and "NOT_AUTHORIZED" not in upper and "UNAUTHORIZED" not in upper
    ) or ("EXECUTABLE" in upper and "NOT_EXECUTABLE" not in upper)


def _require_safety(receipt: dict) -> None:
    safety = _required(receipt, "safety_state", "source_receipt", dict)
    expected = {
        "edge_status": "EDGE_UNPROVEN",
        "live_status": "BLOCK_LIVE_INTEGRATION",
        "decomposition_execution_count": 0,
        "scientific_use_authorized": False,
        "paper_trade_authorized": False,
        "live_integration_authorized": False,
    }
    for key, required_value in expected.items():
        if _required(safety, key, "source_receipt.safety_state") != required_value:
            _fail("LEGACY_AUTHORITY_ESCALATION", f"source_receipt.safety_state.{key}", "contradicts frozen safety state")
    decisions = _required(receipt, "decisions", "source_receipt", list)
    required_decisions = {
        "EDGE_UNPROVEN", "BLOCK_LIVE_INTEGRATION", "H001_EXECUTION=0/0",
        "H001_REAL_DATA_ACCESS=FORBIDDEN", "H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION=NOT_AUTHORIZED",
    }
    if not required_decisions <= set(decisions):
        _fail("LEGACY_REQUIRED_EVIDENCE_MISSING", "source_receipt.decisions", "missing frozen safety evidence")
    if _has_authority_claim(receipt):
        _fail("LEGACY_AUTHORITY_ESCALATION", "source_receipt", "receipt claims authority")


def _validate_amendments(amendments: tuple[LegacyDocument, ...], receipt: dict) -> None:
    seen = set()
    supplied = set()
    evidence = {
        item.get("path"): item.get("sha256")
        for item in _required(receipt, "evidence", "source_receipt", list)
        if type(item) is dict and type(item.get("path")) is str and type(item.get("sha256")) is str
    }
    for document in sorted(amendments, key=lambda item: item.path):
        if document.path in seen:
            _fail("DUPLICATE_AMENDMENT_PATH", document.path, "duplicate amendment path")
        seen.add(document.path)
        parsed = _load(document, "amendment")
        effective = parsed.get("effective") is True
        if effective:
            supplied.add(document.path)
            if document.path not in _REQUIRED_EFFECTIVE_AMENDMENTS:
                _fail("LEGACY_AMENDMENT_CONFLICT", document.path, "unexpected simultaneously effective amendment")
            if parsed.get("governed_h001_protocol_id") != "real_btc_h001_funding_crowding_reversal_falsification_v0":
                _fail("LEGACY_IDENTITY_MISMATCH", document.path, "wrong governed H001 protocol")
            if _has_authority_claim(parsed):
                _fail("LEGACY_AUTHORITY_ESCALATION", document.path, "amendment claims runtime authority")
            if evidence.get(document.path) != hashlib.sha256(document.raw).hexdigest():
                _fail("LEGACY_REQUIRED_EVIDENCE_MISSING", document.path, "receipt does not bind exact amendment bytes")
    if supplied != _REQUIRED_EFFECTIVE_AMENDMENTS:
        _fail("LEGACY_REQUIRED_EVIDENCE_MISSING", "amendments", "current effective amendment set is incomplete")


def project_legacy_control_state(*, active_task: LegacyDocument, source_receipt: LegacyDocument, amendments: tuple[LegacyDocument, ...], source_head_commit: str) -> ControlState:
    """Project explicit, validated current legacy records into deny-only state."""
    active = _load(active_task, "active_task")
    receipt = _load(source_receipt, "source_receipt")
    if active_task.path != "docs/control/active_task.json":
        _fail("LEGACY_UNKNOWN_DOCUMENT", active_task.path, "expected active-task pointer")
    if _required(active, "control_kind", "active_task", str) != "qnty_active_task_pointer":
        _fail("LEGACY_IDENTITY_MISMATCH", "active_task.control_kind", "wrong active-task kind")
    if _required(active, "task_id", "active_task", str) != _TASK_ID or _required(active, "protocol_id", "active_task", str) != _PROTOCOL_ID:
        _fail("LEGACY_IDENTITY_MISMATCH", "active_task", "wrong task or protocol")
    if _required(active, "handoff_receipt_path", "active_task", str) != source_receipt.path:
        _fail("ACTIVE_RECEIPT_MISMATCH", "active_task.handoff_receipt_path", "does not identify supplied receipt")
    actual_hash = hashlib.sha256(source_receipt.raw).hexdigest()
    if _required(active, "handoff_receipt_sha256", "active_task", str) != actual_hash:
        _fail("ACTIVE_RECEIPT_MISMATCH", "active_task.handoff_receipt_sha256", "does not bind supplied receipt bytes")
    if type(source_head_commit) is not str or not _COMMIT_RE.fullmatch(source_head_commit):
        _fail("LEGACY_WRONG_TYPE", "source_head_commit", "must be a lowercase 40-hex commit")
    if _required(receipt, "task_id", "source_receipt", str) != _TASK_ID or _required(receipt, "protocol_id", "source_receipt", str) != _PROTOCOL_ID:
        _fail("LEGACY_IDENTITY_MISMATCH", "source_receipt", "wrong task or protocol")
    index = _required(receipt, "receipt_index", "source_receipt", int)
    if index != _CURRENT_RECEIPT_INDEX:
        _fail("LEGACY_REVISION_MISMATCH", "source_receipt.receipt_index", "current mapping requires receipt index 31")
    _require_safety(receipt)
    _validate_amendments(amendments, receipt)
    binding = _required(receipt, "candidate_binding", "source_receipt", dict)
    proposal_ref = _safe_path(_required(binding, "candidate_path", "source_receipt.candidate_binding", str), "source_receipt.candidate_binding.candidate_path")
    if binding.get("candidate_effective") is not False:
        _fail("LEGACY_AMENDMENT_CONFLICT", "source_receipt.candidate_binding.candidate_effective", "candidate must remain non-effective")
    projected = {
        "control_kind": "qnty_control_state", "schema_version": "1.0.0", "state_revision": index + 1,
        "protocol_id": _PROTOCOL_ID,
        "scientific_state": {"hypothesis_id": "H001", "edge_status": "EDGE_UNPROVEN", "live_status": "BLOCK_LIVE_INTEGRATION", "real_data_access": "FORBIDDEN", "synthetic_calibration_execution": "NOT_AUTHORIZED", "execution_count": 0, "execution_budget": 0},
        "administrative_state": {"workflow_status": "UNDER_REVIEW", "proposal_ref": proposal_ref, "superseded_by": None},
        "runtime_authorization": {"public_data_fetch": "DENIED", "h001_real_data_fetch": "DENIED", "synthetic_calibration": "DENIED", "paper_execution": "DENIED", "shadow_execution": "DENIED", "live_execution": "DENIED"},
        "provenance": {"source_receipt_path": source_receipt.path, "source_receipt_sha256": actual_hash, "source_head_commit": source_head_commit},
    }
    raw = json.dumps(projected, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return load_and_validate_control_state(raw)
