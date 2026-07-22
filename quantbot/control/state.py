"""Deny-only canonical control-state validator (schema 1.0.0).

Pure, standard-library-only validation of a canonical QNTY control-state
document. This module performs no file, network, Git, GitHub, environment,
or process access, and does not read receipts or amendments. Receipt-chain
validation remains the responsibility of the existing continuity subsystem.
"""

import json
import re
from dataclasses import dataclass
from enum import Enum

SUPPORTED_SCHEMA_VERSION = "1.0.0"
REQUIRED_CONTROL_KIND = "qnty_control_state"
REQUIRED_HYPOTHESIS_ID = "H001"

_TOP_KEYS = frozenset(
    {
        "control_kind",
        "schema_version",
        "state_revision",
        "protocol_id",
        "scientific_state",
        "administrative_state",
        "runtime_authorization",
        "provenance",
    }
)
_SCIENTIFIC_KEYS = frozenset(
    {
        "hypothesis_id",
        "edge_status",
        "live_status",
        "real_data_access",
        "synthetic_calibration_execution",
        "execution_count",
        "execution_budget",
    }
)
_ADMINISTRATIVE_KEYS = frozenset({"workflow_status", "proposal_ref", "superseded_by"})
_RUNTIME_KEYS = frozenset(
    {
        "public_data_fetch",
        "h001_real_data_fetch",
        "synthetic_calibration",
        "paper_execution",
        "shadow_execution",
        "live_execution",
    }
)
_PROVENANCE_KEYS = frozenset(
    {"source_receipt_path", "source_receipt_sha256", "source_head_commit"}
)

_GLOB_CHARS = frozenset("*?[]{}")


class ControlStateValidationError(ValueError):
    def __init__(self, code: str, path: str, message: str):
        super().__init__(f"{code} at {path}: {message}")
        self.code = code
        self.path = path


class RuntimeAction(str, Enum):
    PUBLIC_DATA_FETCH = "public_data_fetch"
    H001_REAL_DATA_FETCH = "h001_real_data_fetch"
    SYNTHETIC_CALIBRATION = "synthetic_calibration"
    PAPER_EXECUTION = "paper_execution"
    SHADOW_EXECUTION = "shadow_execution"
    LIVE_EXECUTION = "live_execution"


@dataclass(frozen=True)
class ScientificState:
    hypothesis_id: str
    edge_status: str
    live_status: str
    real_data_access: str
    synthetic_calibration_execution: str
    execution_count: int
    execution_budget: int


@dataclass(frozen=True)
class AdministrativeState:
    workflow_status: str
    proposal_ref: str
    superseded_by: str | None


@dataclass(frozen=True)
class RuntimeAuthorization:
    public_data_fetch: str
    h001_real_data_fetch: str
    synthetic_calibration: str
    paper_execution: str
    shadow_execution: str
    live_execution: str


@dataclass(frozen=True)
class Provenance:
    source_receipt_path: str
    source_receipt_sha256: str
    source_head_commit: str


@dataclass(frozen=True)
class ControlState:
    control_kind: str
    schema_version: str
    state_revision: int
    protocol_id: str
    scientific_state: ScientificState
    administrative_state: AdministrativeState
    runtime_authorization: RuntimeAuthorization
    provenance: Provenance


@dataclass(frozen=True)
class AuthorizationDecision:
    action: RuntimeAction
    authorized: bool
    reason: str
    state_revision: int


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _fail(code: str, path: str, message: str) -> None:
    raise ControlStateValidationError(code, path, message)


def _duplicate_key_pairs_hook(pairs):
    seen = set()
    obj = {}
    for key, value in pairs:
        if key in seen:
            _fail("DUPLICATE_KEY", "$", f"duplicate key: {key!r}")
        seen.add(key)
        obj[key] = value
    return obj


def _require_exact_keys(obj: object, expected_keys: frozenset, path: str) -> None:
    if type(obj) is not dict:
        _fail("WRONG_TYPE", path, "expected an object")
    obj_keys = set(obj)
    missing = sorted(expected_keys - obj_keys)
    if missing:
        _fail("MISSING_FIELD", f"{path}.{missing[0]}", f"missing required field(s): {missing}")
    unknown = sorted(obj_keys - expected_keys)
    if unknown:
        _fail("UNKNOWN_FIELD", f"{path}.{unknown[0]}", f"unknown field(s): {unknown}")


def _require_str(obj: dict, key: str, path: str) -> str:
    value = obj[key]
    if type(value) is not str:
        _fail("WRONG_TYPE", f"{path}.{key}", "expected a string")
    return value


def _require_nonempty_str(obj: dict, key: str, path: str) -> str:
    value = _require_str(obj, key, path)
    if not value:
        _fail("INVALID_LITERAL", f"{path}.{key}", "must be non-empty")
    return value


def _require_literal(obj: dict, key: str, path: str, expected: str) -> str:
    value = _require_str(obj, key, path)
    if value != expected:
        _fail("INVALID_LITERAL", f"{path}.{key}", f"must be exactly {expected!r}")
    return value


def _require_int(obj: dict, key: str, path: str) -> int:
    value = obj[key]
    if type(value) is not int:
        _fail("WRONG_TYPE", f"{path}.{key}", "expected an integer")
    return value


def _require_positive_revision(obj: dict, key: str, path: str) -> int:
    value = _require_int(obj, key, path)
    if value <= 0:
        _fail("INVALID_REVISION", f"{path}.{key}", "must be a positive integer")
    return value


def _require_zero(obj: dict, key: str, path: str) -> int:
    value = _require_int(obj, key, path)
    if value != 0:
        _fail("INVALID_LITERAL", f"{path}.{key}", "must be exactly 0")
    return value


def _require_optional_str(obj: dict, key: str, path: str) -> str | None:
    value = obj[key]
    if value is not None and type(value) is not str:
        _fail("WRONG_TYPE", f"{path}.{key}", "expected a string or null")
    return value


def _is_safe_relative_path(value: str) -> bool:
    if not value:
        return False
    if "\\" in value:
        return False
    if value.startswith("/") or value.startswith("//"):
        return False
    if re.match(r"^[A-Za-z]:", value):
        return False
    if "://" in value:
        return False
    if any(ch in _GLOB_CHARS for ch in value):
        return False
    if ".." in value.split("/"):
        return False
    return True


def _require_safe_path(obj: dict, key: str, path: str) -> str:
    value = _require_nonempty_str(obj, key, path)
    if not _is_safe_relative_path(value):
        _fail("INVALID_PATH", f"{path}.{key}", "must be a safe repository-relative path")
    return value


def _require_sha256(obj: dict, key: str, path: str) -> str:
    value = _require_str(obj, key, path)
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        _fail("INVALID_SHA256", f"{path}.{key}", "must be 64 lowercase hex characters")
    return value


def _require_commit_sha(obj: dict, key: str, path: str) -> str:
    value = _require_str(obj, key, path)
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        _fail("INVALID_COMMIT_SHA", f"{path}.{key}", "must be 40 lowercase hex characters")
    return value


def _validate_scientific_state(obj: object, path: str) -> ScientificState:
    _require_exact_keys(obj, _SCIENTIFIC_KEYS, path)
    return ScientificState(
        hypothesis_id=_require_literal(obj, "hypothesis_id", path, REQUIRED_HYPOTHESIS_ID),
        edge_status=_require_literal(obj, "edge_status", path, "EDGE_UNPROVEN"),
        live_status=_require_literal(obj, "live_status", path, "BLOCK_LIVE_INTEGRATION"),
        real_data_access=_require_literal(obj, "real_data_access", path, "FORBIDDEN"),
        synthetic_calibration_execution=_require_literal(
            obj, "synthetic_calibration_execution", path, "NOT_AUTHORIZED"
        ),
        execution_count=_require_zero(obj, "execution_count", path),
        execution_budget=_require_zero(obj, "execution_budget", path),
    )


def _validate_administrative_state(obj: object, path: str) -> AdministrativeState:
    _require_exact_keys(obj, _ADMINISTRATIVE_KEYS, path)
    return AdministrativeState(
        workflow_status=_require_nonempty_str(obj, "workflow_status", path),
        proposal_ref=_require_safe_path(obj, "proposal_ref", path),
        superseded_by=_require_optional_str(obj, "superseded_by", path),
    )


def _validate_runtime_authorization(obj: object, path: str) -> RuntimeAuthorization:
    _require_exact_keys(obj, _RUNTIME_KEYS, path)
    return RuntimeAuthorization(
        **{key: _require_literal(obj, key, path, "DENIED") for key in _RUNTIME_KEYS}
    )


def _validate_provenance(obj: object, path: str) -> Provenance:
    _require_exact_keys(obj, _PROVENANCE_KEYS, path)
    return Provenance(
        source_receipt_path=_require_safe_path(obj, "source_receipt_path", path),
        source_receipt_sha256=_require_sha256(obj, "source_receipt_sha256", path),
        source_head_commit=_require_commit_sha(obj, "source_head_commit", path),
    )


def _validate_root(value: object) -> ControlState:
    _require_exact_keys(value, _TOP_KEYS, "$")
    return ControlState(
        control_kind=_require_literal(value, "control_kind", "$", REQUIRED_CONTROL_KIND),
        schema_version=_require_schema_version(value, "$"),
        state_revision=_require_positive_revision(value, "state_revision", "$"),
        protocol_id=_require_nonempty_str(value, "protocol_id", "$"),
        scientific_state=_validate_scientific_state(value["scientific_state"], "$.scientific_state"),
        administrative_state=_validate_administrative_state(
            value["administrative_state"], "$.administrative_state"
        ),
        runtime_authorization=_validate_runtime_authorization(
            value["runtime_authorization"], "$.runtime_authorization"
        ),
        provenance=_validate_provenance(value["provenance"], "$.provenance"),
    )


def _require_schema_version(obj: dict, path: str) -> str:
    value = _require_str(obj, "schema_version", path)
    if value != SUPPORTED_SCHEMA_VERSION:
        _fail(
            "UNSUPPORTED_SCHEMA_VERSION",
            f"{path}.schema_version",
            f"unsupported schema version: {value!r}",
        )
    return value


def load_and_validate_control_state(raw: bytes) -> ControlState:
    if type(raw) is not bytes:
        _fail("WRONG_TYPE", "$", "raw input must be bytes")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        _fail("INVALID_JSON", "$", f"invalid utf-8: {exc}")
    try:
        value = json.loads(text, object_pairs_hook=_duplicate_key_pairs_hook)
    except json.JSONDecodeError as exc:
        _fail("INVALID_JSON", "$", str(exc))
    if _canonical_json_bytes(value) != raw:
        _fail("NON_CANONICAL_JSON", "$", "raw bytes are not canonical JSON")
    return _validate_root(value)


def _revalidate(state: ControlState) -> ControlState:
    """Re-run schema validation on a ControlState's own field content.

    A ControlState (or any nested frozen dataclass) can be forged with
    dataclasses.replace() without ever passing through
    load_and_validate_control_state(). Python's type system alone cannot
    distinguish a forged instance from a genuinely validated one, so this
    rebuilds an explicit plain mapping from the dataclass fields and pushes
    it back through the same schema validators used on first load.
    """
    if (
        type(state) is not ControlState
        or type(state.scientific_state) is not ScientificState
        or type(state.administrative_state) is not AdministrativeState
        or type(state.runtime_authorization) is not RuntimeAuthorization
        or type(state.provenance) is not Provenance
    ):
        raise TypeError("expected a ControlState produced by load_and_validate_control_state")
    mapping = {
        "control_kind": state.control_kind,
        "schema_version": state.schema_version,
        "state_revision": state.state_revision,
        "protocol_id": state.protocol_id,
        "scientific_state": {
            "hypothesis_id": state.scientific_state.hypothesis_id,
            "edge_status": state.scientific_state.edge_status,
            "live_status": state.scientific_state.live_status,
            "real_data_access": state.scientific_state.real_data_access,
            "synthetic_calibration_execution": state.scientific_state.synthetic_calibration_execution,
            "execution_count": state.scientific_state.execution_count,
            "execution_budget": state.scientific_state.execution_budget,
        },
        "administrative_state": {
            "workflow_status": state.administrative_state.workflow_status,
            "proposal_ref": state.administrative_state.proposal_ref,
            "superseded_by": state.administrative_state.superseded_by,
        },
        "runtime_authorization": {
            "public_data_fetch": state.runtime_authorization.public_data_fetch,
            "h001_real_data_fetch": state.runtime_authorization.h001_real_data_fetch,
            "synthetic_calibration": state.runtime_authorization.synthetic_calibration,
            "paper_execution": state.runtime_authorization.paper_execution,
            "shadow_execution": state.runtime_authorization.shadow_execution,
            "live_execution": state.runtime_authorization.live_execution,
        },
        "provenance": {
            "source_receipt_path": state.provenance.source_receipt_path,
            "source_receipt_sha256": state.provenance.source_receipt_sha256,
            "source_head_commit": state.provenance.source_head_commit,
        },
    }
    return _validate_root(mapping)


def authorize(state: ControlState, action: RuntimeAction) -> AuthorizationDecision:
    if not isinstance(state, ControlState):
        raise TypeError("authorize() requires a validated ControlState")
    if not isinstance(action, RuntimeAction):
        raise TypeError("authorize() requires a RuntimeAction enum member")
    validated = _revalidate(state)
    return AuthorizationDecision(
        action=action,
        authorized=False,
        reason="schema_version 1.0.0 is a deny-only bootstrap; all runtime actions are denied",
        state_revision=validated.state_revision,
    )


def validate_transition(previous: ControlState, candidate: ControlState) -> None:
    if not isinstance(previous, ControlState) or not isinstance(candidate, ControlState):
        raise TypeError("validate_transition() requires validated ControlState values")
    previous = _revalidate(previous)
    candidate = _revalidate(candidate)
    if previous.control_kind != candidate.control_kind:
        _fail("IDENTITY_CHANGED", "$.control_kind", "control_kind must not change across a transition")
    if previous.schema_version != candidate.schema_version:
        _fail("IDENTITY_CHANGED", "$.schema_version", "schema_version must not change across a transition")
    if previous.protocol_id != candidate.protocol_id:
        _fail("IDENTITY_CHANGED", "$.protocol_id", "protocol_id must not change across a transition")
    if previous.scientific_state.hypothesis_id != candidate.scientific_state.hypothesis_id:
        _fail(
            "IDENTITY_CHANGED",
            "$.scientific_state.hypothesis_id",
            "hypothesis_id must not change across a transition",
        )
    if candidate.state_revision <= previous.state_revision:
        _fail("STALE_REVISION", "$.state_revision", "candidate revision must be strictly greater than previous revision")
    if candidate.state_revision != previous.state_revision + 1:
        _fail("REVISION_GAP", "$.state_revision", "candidate revision must be exactly previous + 1")
