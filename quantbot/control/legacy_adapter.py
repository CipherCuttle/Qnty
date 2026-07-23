"""Pure projection of the frozen legacy continuity packet into control state.

The current legacy packet is receipt index 32.  The one documented mapping is
``state_revision = receipt_index + 1``: index 32 therefore projects to revision
33.  Inputs are documents supplied by the caller; this module does not inspect
the repository, environment, process, network, or Git state.

Amendment semantic identity is derived only from the explicit
``amendment_kind`` field each amendment document declares, never from its
path, basename, suffix, or directory.  Paths are used only for safe-path
validation, duplicate detection, receipt evidence lookup, exact SHA-256 byte
binding, and provenance.

The real guarantees this module provides:

* Exact role-to-content binding freezes the six currently effective
  amendments: each required semantic role must be supplied by a document
  whose raw bytes hash to that role's pinned SHA-256 digest, computed once
  from the actual current effective amendment bytes.  This is the primary
  amendment-integrity boundary -- it is independent of path, filename,
  ordering, or the receipt's own evidence bookkeeping, and it fails closed on
  any byte change, any role swap, or any relocation that also changes bytes.
* A finite, explicit leaf-field authority classifier is defense-in-depth on
  top of that binding, and is the *only* protection for the source receipt
  (which is not pinned to a single frozen content hash).  It recognizes
  authority-bearing fields by exact key name and a small set of key
  suffixes, normalized to ASCII lowercase; every recognized leaf must hold
  exactly `False` or one of a small set of safe deny strings.  It does not
  and cannot enumerate every conceivable future authority-bearing field name
  -- an unrecognized field name is defense-in-depth blind spot, not a
  guarantee -- so the role-to-content binding above remains the load-bearing
  control for amendments.
* Administrative exceptions (fields that legitimately carry a non-deny
  value, e.g. an implementation-authorized marker or a review-stage status
  string) are finite, exact-key, exact-value allowlists derived from the
  actual frozen packet.  They can never authorize runtime, scientific,
  paper, shadow, live, or real-data operations: the projected control state
  below is built entirely from literal deny constants and never reads an
  authority value out of the supplied documents.
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
_GOVERNED_H001_PROTOCOL_ID = "real_btc_h001_funding_crowding_reversal_falsification_v0"
_CURRENT_RECEIPT_INDEX = 32

# The smallest finite adapter-local semantic-role mapping supported by the six
# currently effective amendments' own explicit `amendment_kind` fields.  Each
# required current role must be supplied by exactly one effective amendment.
_REQUIRED_EFFECTIVE_AMENDMENT_ROLES = frozenset(
    {
        "qnty_h001_temporal_causality_activation_amendment",
        "qnty_h001_synthetic_null_calibration_spec_freeze_activation_amendment",
        "qnty_h001_synthetic_null_calibration_execution_governance_amendment",
        "qnty_h001_synthetic_null_calibration_numerical_conventions_amendment_governance",
        "qnty_h001_synthetic_null_calibration_rng_runtime_specification_amendment_governance",
        "qnty_h001_rng_runtime_specification_amendment_activation_amendment",
        "qnty_h001_numerical_conventions_amendment_activation_amendment",
    }
)

# Exact SHA-256 of the actual current effective amendment bytes, one per
# required role, computed once from the frozen packet at the pinned source
# head commit.  This is the primary amendment-integrity boundary: unlike the
# structural classifier below, it is not a defense-in-depth heuristic -- any
# byte difference from the pinned digest fails closed, regardless of what
# fields the mutated content does or does not contain, and regardless of
# whether the receipt's own evidence hash was also (mis)updated to match.
_REQUIRED_EFFECTIVE_AMENDMENT_ROLE_DIGESTS = {
    "qnty_h001_temporal_causality_activation_amendment": "b60f322650c5b83500b89ad9914b50cd2eb200cbae573670d307b5a72190ee1b",
    "qnty_h001_synthetic_null_calibration_spec_freeze_activation_amendment": "3fa3d21492645baba8a1fd7fd5fbe8a601ccccec1371e5e7a81faff430c2ab48",
    "qnty_h001_synthetic_null_calibration_execution_governance_amendment": "23b98106326b655ec334e54eaf1757d24f77ab643a64efeddad7226801ad16a5",
    "qnty_h001_synthetic_null_calibration_numerical_conventions_amendment_governance": "b6309ef438129fd49218ab12a086996286b90408d2d97189a3ce8b9ed680e649",
    "qnty_h001_synthetic_null_calibration_rng_runtime_specification_amendment_governance": "da27f06effb8321da84ee9f44ff90b810e8c36491d729387b4e820e14f0d8c36",
    "qnty_h001_rng_runtime_specification_amendment_activation_amendment": "77b27c218670ca427e2f9589dba144731dd456cce56650222ebb37a3d5528c97",
    "qnty_h001_numerical_conventions_amendment_activation_amendment": "c497359a292f5a9b1333e5d881fee16c39d80f68ec1a6613f625a368532ae200",
}

# Structural, field-aware runtime-authority validation.
#
# Every recognized field is looked up by its exact key name (normalized to
# ASCII lowercase); its value is then required to equal one of a small set
# of known-safe (deny/administrative) values.  This is defense-in-depth: it
# protects the source receipt (which has no per-document content-hash
# binding) and backs up the amendment role-to-content binding above.  It is
# necessarily a finite, explicit enumeration -- it does not claim to catch
# every conceivable future authority-bearing field name, only the ones
# listed here plus the small set of recognized suffixes.
_AUTHORITY_DENY_ONLY_FIELDS = frozenset(
    {
        "execution_authorized",
        "h001_holdout_execution_authorized",
        "h001_validation_execution_authorized",
        "live_authorization",
        "live_integration_authorized",
        "paper_trade_authorization",
        "paper_trade_authorized",
        "real_data_access_authorized",
        "results_exposed",
        "scientific_authorization",
        "scientific_use_authorized",
        "calibration_execution_authorized",
        "calibration_execution_performed",
        "calibration_engine_implemented",
        "live_authorization_granted",
        "paper_trade_authorization_granted",
        "scientific_authorization_granted",
    }
)

# Any field name ending in one of these suffixes (matched on the ASCII
# lowercase form of the key) is treated as runtime-authority bearing
# structurally -- by key, never by scanning its value's text.
_AUTHORITY_FIELD_SUFFIXES = ("_authorized", "_authorization", "_permission", "_authority", "_granted")

# Fields that legitimately carry a non-deny boolean value as administrative
# or implementation-only evidence and must never be treated as
# runtime-authority escalation, even though their name matches an authority
# suffix above.  Still required to be an actual bool (true or false).
_ADMINISTRATIVE_ALLOW_BOOLEAN_FIELDS = frozenset(
    {
        "execution_implementation_authorized",
        "rng_runtime_amendment_governance_authorized",
    }
)

# Fields that carry an administrative status *string*, never a boolean deny
# value.  Recognized by exact key name; the value must equal one of a
# finite, exact allowlist of the current frozen packet's legitimate values
# (see `_ADMINISTRATIVE_STATUS_ALLOWED_VALUES`), never merely "contain" a
# review-stage word such as ONLY, REVIEW, CANDIDATE, or PROPOSED.
_ADMINISTRATIVE_STATUS_FIELDS = frozenset({"authorization_status"})

_ADMINISTRATIVE_STATUS_ALLOWED_VALUES = frozenset(
    {
        "AUTHORIZED_H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION_IMPLEMENTATION_FOR_INDEPENDENT_REVIEW_ONLY",
        "AUTHORIZED_H001_SYNTHETIC_NULL_CALIBRATION_NUMERICAL_CONVENTIONS_AMENDMENT_CANDIDATE_FOR_INDEPENDENT_REVIEW_ONLY",
        "AUTHORIZED_H001_SYNTHETIC_NULL_CALIBRATION_RNG_RUNTIME_SPECIFICATION_AMENDMENT_CANDIDATE_FOR_INDEPENDENT_REVIEW_ONLY",
    }
)

_STRING_AUTHORITY_SAFE_VALUES = frozenset({"DENIED", "FORBIDDEN", "NOT_AUTHORIZED", "UNAUTHORIZED", "NONE"})

_ASCII_LOWER_TABLE = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")

# `KEY=VALUE` decision tokens (as used in `source_receipt.decisions`) are
# matched by key, exact-value allow-listed, never substring-scanned.
_DECISION_KEY_ALLOWED_VALUES = {
    "EDGE_STATUS": {"EDGE_UNPROVEN"},
    "LIVE_STATUS": {"BLOCK_LIVE_INTEGRATION"},
    "H001_EXECUTION": {"0/0"},
    "H001_REAL_DATA_ACCESS": {"FORBIDDEN"},
    "REAL_DATA_ACCESS": {"FORBIDDEN"},
    "H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION": {"NOT_AUTHORIZED"},
    "SYNTHETIC_NULL_CALIBRATION_EXECUTION": {"NOT_AUTHORIZED"},
    "SYNTHETIC_CALIBRATION_EXECUTION": {"NOT_AUTHORIZED"},
    "SYNTHETIC_CALIBRATION_EXECUTABLE": {"FALSE", "NOT_EXECUTABLE"},
    "SCIENTIFIC_USE": {"NOT_AUTHORIZED"},
    "SCIENTIFIC_AUTHORIZATION": {"NOT_AUTHORIZED", "FALSE"},
    "PAPER_EXECUTION": {"DENIED", "NOT_AUTHORIZED"},
    "PAPER_TRADE_AUTHORIZATION": {"DENIED", "NOT_AUTHORIZED", "FALSE"},
    "SHADOW_EXECUTION": {"DENIED", "NOT_AUTHORIZED"},
    "LIVE_EXECUTION": {"DENIED", "NOT_AUTHORIZED"},
    "LIVE_INTEGRATION_AUTHORIZED": {"DENIED", "NOT_AUTHORIZED", "FALSE"},
    "RUNTIME_PERMISSION": set(),  # no value is legitimate on this key
}

# `KEY=VALUE` (or bare-token) decisions that are purely administrative and
# never carry runtime authority regardless of value, e.g. review-stage markers.
_ADMINISTRATIVE_DECISION_KEY_PREFIXES = ("NEXT_ACTIONS", "REVIEW_STATUS", "REVIEW_VERDICT")


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


def _ascii_lower(key: str) -> str:
    return key.translate(_ASCII_LOWER_TABLE)


def _classify_authority_leaf(key: str, item: object, path: str) -> None:
    """Classify a single dict leaf by its exact (ASCII-lowercased) key name.

    Three finite, explicit categories, checked in order:
    1. Known administrative booleans: must be an actual bool (either value).
    2. Known administrative status strings: must equal one of a finite exact
       allowlist of the current frozen packet's legitimate values.
    3. Known deny-only authority fields (exact name or recognized suffix):
       must be exactly `False` or one of the safe deny strings.
    Anything not matching one of these three categories is not classified
    here at all -- it is not scanned for keyword text.  Ordinary grouping
    containers under such a key are recursed into by the caller; a recognized
    authority-like key, however, must be a scalar leaf and rejects a dict or
    list rather than broadening the frozen packet's accepted input language.
    """
    normalized = _ascii_lower(key)
    if normalized in _ADMINISTRATIVE_ALLOW_BOOLEAN_FIELDS:
        if type(item) is not bool:
            _fail("LEGACY_WRONG_TYPE", path, "administrative authorization field must be a boolean")
        return
    if normalized in _ADMINISTRATIVE_STATUS_FIELDS:
        if type(item) is not str or item not in _ADMINISTRATIVE_STATUS_ALLOWED_VALUES:
            _fail("LEGACY_AUTHORITY_ESCALATION", path, "administrative status is not an exact frozen allowed value")
        return
    if normalized in _AUTHORITY_DENY_ONLY_FIELDS or normalized.endswith(_AUTHORITY_FIELD_SUFFIXES):
        if type(item) is bool:
            if item is not False:
                _fail("LEGACY_AUTHORITY_ESCALATION", path, "runtime-authority field is not false")
        elif type(item) is str:
            if item not in _STRING_AUTHORITY_SAFE_VALUES:
                _fail("LEGACY_AUTHORITY_ESCALATION", path, "runtime-authority field is not a safe deny value")
        else:
            _fail("LEGACY_AUTHORITY_ESCALATION", path, "runtime-authority field has unexpected type")


def _check_boolean_authority_fields(value: object, path: str) -> None:
    """Recursively require known runtime-authority leaf fields to be deny-safe.

    Recognition is by exact (ASCII-lowercased) key name, never by scanning a
    value's text: a suffix such as "_ONLY" appended to an escalating string
    on a *recognized* field cannot hide it, because the comparison is exact
    membership in a finite allowed set.  Unrecognized grouping containers are
    recursed into, so an authority-bearing scalar leaf nested under an
    unrecognized container name (e.g. a `..._non_effects` grouping) is still
    classified individually.  A recognized authority-like key is required to
    be a scalar leaf; a dict or list at that key fails closed as an unexpected
    authority-field type and is not a supported deny-safe container form.
    """
    if isinstance(value, dict):
        for key, item in value.items():
            child_path = f"{path}.{key}"
            _classify_authority_leaf(key, item, child_path)
            _check_boolean_authority_fields(item, child_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _check_boolean_authority_fields(item, f"{path}[{index}]")


def _check_decision_tokens(decisions: object, path: str) -> None:
    """Structurally validate `KEY=VALUE` / bare decision tokens by exact key+value."""
    if not isinstance(decisions, list):
        return
    for index, token in enumerate(decisions):
        if type(token) is not str:
            continue
        key, sep, value = token.partition("=")
        if not sep:
            continue
        if any(key.startswith(prefix) for prefix in _ADMINISTRATIVE_DECISION_KEY_PREFIXES):
            continue
        if key in _DECISION_KEY_ALLOWED_VALUES and value not in _DECISION_KEY_ALLOWED_VALUES[key]:
            _fail("LEGACY_AUTHORITY_ESCALATION", f"{path}[{index}]", f"decision token escalates runtime authority: {token!r}")


def _check_authority_structure(value: dict, path: str) -> None:
    _check_boolean_authority_fields(value, path)
    decisions = value.get("decisions")
    if decisions is not None:
        _check_decision_tokens(decisions, f"{path}.decisions")
    next_actions = value.get("next_actions")
    if next_actions is not None and not isinstance(next_actions, list):
        _fail("LEGACY_WRONG_TYPE", f"{path}.next_actions", "must be a list when present")


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
    _check_authority_structure(receipt, "source_receipt")


def _validate_amendments_container(amendments: object) -> tuple["LegacyDocument", ...]:
    """Validate the public `amendments` input before any sorting (Defect 3)."""
    if type(amendments) is not tuple:
        _fail("LEGACY_WRONG_TYPE", "amendments", "must be a tuple")
    for index, item in enumerate(amendments):
        label = f"amendments[{index}]"
        if type(item) is not LegacyDocument:
            _fail("LEGACY_WRONG_TYPE", label, "must be a LegacyDocument")
        _safe_path(item.path, f"{label}.path")
        if type(item.raw) is not bytes:
            _fail("LEGACY_WRONG_TYPE", f"{label}.raw", "must be bytes")
    paths = [item.path for item in amendments]
    if len(paths) != len(set(paths)):
        _fail("DUPLICATE_AMENDMENT_PATH", "amendments", "duplicate amendment path")
    return tuple(sorted(amendments, key=lambda item: item.path))


def _validate_amendments(amendments: tuple["LegacyDocument", ...], receipt: dict) -> None:
    evidence = {
        item.get("path"): item.get("sha256")
        for item in _required(receipt, "evidence", "source_receipt", list)
        if type(item) is dict and type(item.get("path")) is str and type(item.get("sha256")) is str
    }
    roles: dict[str, str] = {}
    for document in amendments:
        parsed = _load(document, "amendment")
        if parsed.get("effective") is not True:
            continue
        # 1-2. Derive and validate the semantic role from the explicit field.
        role = parsed.get("amendment_kind")
        if type(role) is not str or not role or role not in _REQUIRED_EFFECTIVE_AMENDMENT_ROLES:
            _fail("LEGACY_UNKNOWN_AMENDMENT_ROLE", document.path, f"unknown or missing effective amendment role: {role!r}")
        # 3. Optional `document_kind` consistency.
        document_kind = parsed.get("document_kind")
        if document_kind is not None and document_kind != role:
            _fail("LEGACY_AMENDMENT_ROLE_CONFLICT", document.path, "amendment_kind and document_kind disagree")
        if role in roles:
            _fail("LEGACY_DUPLICATE_AMENDMENT_ROLE", document.path, f"role already supplied by {roles[role]!r}")
        # 4. Governed protocol identity.
        if parsed.get("governed_h001_protocol_id") != _GOVERNED_H001_PROTOCOL_ID:
            _fail("LEGACY_IDENTITY_MISMATCH", document.path, "wrong governed H001 protocol")
        _check_authority_structure(parsed, "amendment")
        # 5. Receipt evidence path + SHA-256 binding.
        if evidence.get(document.path) != hashlib.sha256(document.raw).hexdigest():
            _fail("LEGACY_REQUIRED_EVIDENCE_MISSING", document.path, "receipt does not bind exact amendment bytes")
        # 6. Independent exact role-to-content binding: the primary
        # amendment-integrity boundary, checked regardless of path or of
        # what the receipt's own evidence hash says.
        if hashlib.sha256(document.raw).hexdigest() != _REQUIRED_EFFECTIVE_AMENDMENT_ROLE_DIGESTS[role]:
            _fail("LEGACY_AMENDMENT_CONTENT_MISMATCH", document.path, f"amendment bytes do not match the frozen digest for role {role!r}")
        roles[role] = document.path
    missing = _REQUIRED_EFFECTIVE_AMENDMENT_ROLES - roles.keys()
    if missing:
        _fail("LEGACY_REQUIRED_EVIDENCE_MISSING", "amendments", f"current effective amendment set is incomplete: missing roles {sorted(missing)}")


def project_legacy_control_state(*, active_task: LegacyDocument, source_receipt: LegacyDocument, amendments: tuple[LegacyDocument, ...], source_head_commit: str) -> ControlState:
    """Project explicit, validated current legacy records into deny-only state."""
    active = _load(active_task, "active_task")
    receipt = _load(source_receipt, "source_receipt")
    amendments = _validate_amendments_container(amendments)
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
        _fail("LEGACY_REVISION_MISMATCH", "source_receipt.receipt_index", "current mapping requires receipt index 32")
    _require_safety(receipt)
    _validate_amendments(amendments, receipt)
    binding = _required(receipt, "candidate_binding", "source_receipt", dict)
    proposal_ref = _safe_path(_required(binding, "candidate_path", "source_receipt.candidate_binding", str), "source_receipt.candidate_binding.candidate_path")
    if binding.get("candidate_effective") is not True or binding.get("candidate_activated") is not True:
        _fail("LEGACY_AMENDMENT_CONFLICT", "source_receipt.candidate_binding", "current packet must bind the activated effective candidate")
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
