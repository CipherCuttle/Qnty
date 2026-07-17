"""Fail-closed validator and renderer for the QNTY cross-agent continuity control plane.

Source of truth is the committed control state under ``docs/control/`` plus the
model-specific entrypoints (``CLAUDE.md``, ``AGENTS.md``) and the canonical shared
contract (``docs/agent/START_HERE.md``). This module never reads market data,
ledgers, or quarantine content; it only validates governance documents.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from quantbot.artifacts.registry import (
    ArtifactRegistryError,
    cross_check_receipt_artifact,
    validate_artifact_record_bytes,
    validate_store_registry_bytes,
)

__all__ = [
    "canonical_json_bytes",
    "load_and_verify_continuity_state",
    "render_context_packet",
]

_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_COMMIT_RE = re.compile(r"[0-9a-f]{40}")
_RECEIPT_BASENAME_RE = re.compile(r"handoff_v[0-9]{3}\.json")

TASK_ID = "RECOVER_OR_RETIRE_CANDIDATE1_V0_FROZEN_INPUT"
PROTOCOL_ID = "real_btc_candidate1_train_mechanism_decomposition_v0"
REQUIRED_ARTIFACT_ID = "candidate1-real-input-v0"
REQUIRED_ARTIFACT_MANIFEST_SHA256 = "3dec994114769a16939afa9b0041a8162a308dcb05ca196557407b26a0d35b0d"

ACTIVE_TASK_RELPATH = "docs/control/active_task.json"
ARTIFACT_RECORDS_DIR_RELPATH = "docs/artifacts"
STORE_REGISTRY_RELPATH = "docs/artifacts/stores.json"
START_HERE_RELPATH = "docs/agent/START_HERE.md"
CLAUDE_ENTRYPOINT_RELPATH = "CLAUDE.md"
CODEX_ENTRYPOINT_RELPATH = "AGENTS.md"
CLAUDE_CONTRACT_POINTER = "@docs/agent/START_HERE.md"
CODEX_CONTRACT_POINTER = "docs/agent/START_HERE.md"
VERIFY_COMMAND = "python -m quantbot.continuity verify"

_PROHIBITED_CANONICAL_PATH_PREFIXES = ("/tmp", "/srv/qnty")

_ACTIVE_KEYS = {
    "control_kind",
    "handoff_receipt_path",
    "handoff_receipt_sha256",
    "phase",
    "protocol_id",
    "schema_version",
    "task_id",
}
_RECEIPT_KEYS = {
    "blockers",
    "changed_file_scope",
    "decisions",
    "evidence",
    "next_actions",
    "predecessor",
    "prohibited_actions",
    "protocol_id",
    "receipt_index",
    "receipt_kind",
    "required_artifacts",
    "safety_state",
    "schema_version",
    "source_branch",
    "source_head_commit",
    "task_id",
    "verified_commands",
}
_SAFETY_KEYS = {
    "decomposition_execution_budget",
    "decomposition_execution_count",
    "edge_status",
    "live_integration_authorized",
    "live_status",
    "paper_trade_authorized",
    "quarantine_access",
    "real_data_execution_requested",
    "scientific_use_authorized",
}
_ARTIFACT_KEYS = {
    "artifact_id",
    "availability",
    "canonical_paths",
    "expected_manifest_sha256",
    "verified_copy_count",
}
_EVIDENCE_KEYS = {"path", "sha256"}
_PREDECESSOR_KEYS = {"path", "sha256"}

_EXPECTED_SAFETY = {
    "decomposition_execution_budget": 1,
    "decomposition_execution_count": 0,
    "edge_status": "EDGE_UNPROVEN",
    "live_integration_authorized": False,
    "live_status": "BLOCK_LIVE_INTEGRATION",
    "paper_trade_authorized": False,
    "quarantine_access": "forbidden",
    "scientific_use_authorized": False,
}
_AVAILABILITY_STATES = ("UNAVAILABLE", "VERIFIED_AVAILABLE")


def canonical_json_bytes(value: object) -> bytes:
    """Canonical QNTY JSON bytes: UTF-8, sorted keys, compact, ASCII, no newline."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _fail(message: str) -> None:
    raise ValueError(f"continuity verification failed: {message}")


def _require_str(value: object, label: str) -> str:
    if type(value) is not str or not value:
        _fail(f"{label} must be a non-empty string")
    return value


def _require_int(value: object, label: str) -> int:
    if type(value) is not int:
        _fail(f"{label} must be an int (bool is not accepted)")
    return value


def _require_bool(value: object, label: str) -> bool:
    if type(value) is not bool:
        _fail(f"{label} must be a bool")
    return value


def _require_sha256(value: object, label: str) -> str:
    if type(value) is not str or not _SHA256_RE.fullmatch(value):
        _fail(f"{label} must be a lowercase hex sha256")
    return value


def _require_repo_relative(value: object, label: str) -> str:
    path = _require_str(value, label)
    if path.startswith("/") or ".." in path.split("/") or path != path.strip():
        _fail(f"{label} must be a repository-relative path")
    return path


def _require_str_list(value: object, label: str, *, minimum: int = 0) -> list:
    if type(value) is not list or len(value) < minimum:
        _fail(f"{label} must be a list with at least {minimum} entries")
    for item in value:
        _require_str(item, f"{label} entry")
    return value


def _require_exact_keys(value: object, expected: set, label: str) -> dict:
    if type(value) is not dict:
        _fail(f"{label} must be a JSON object")
    if set(value) != expected:
        missing = sorted(expected - set(value))
        extra = sorted(set(value) - expected)
        _fail(f"{label} keys mismatch (missing={missing} extra={extra})")
    return value


def _load_canonical_document(data: bytes, label: str) -> dict:
    try:
        parsed = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        _fail(f"{label} is not strict UTF-8 JSON")
    if type(parsed) is not dict:
        _fail(f"{label} must be a JSON object")
    if data.endswith(b"\n") or data != canonical_json_bytes(parsed):
        _fail(f"{label} is not canonical QNTY JSON (sorted keys, compact, ASCII, no trailing newline)")
    return parsed


def _validate_active_task(parsed: dict) -> dict:
    _require_exact_keys(parsed, _ACTIVE_KEYS, "active_task")
    if parsed["schema_version"] != "0.1.0":
        _fail("active_task schema_version is not 0.1.0")
    if parsed["control_kind"] != "qnty_active_task_pointer":
        _fail("active_task control_kind is wrong")
    if parsed["task_id"] != TASK_ID:
        _fail("active_task task_id does not match the governed task")
    if parsed["protocol_id"] != PROTOCOL_ID:
        _fail("active_task protocol_id does not match the governed protocol")
    _require_str(parsed["phase"], "active_task phase")
    receipt_path = _require_repo_relative(parsed["handoff_receipt_path"], "handoff_receipt_path")
    expected_dir = f"docs/control/tasks/{TASK_ID}/"
    if not receipt_path.startswith(expected_dir) or not _RECEIPT_BASENAME_RE.fullmatch(receipt_path[len(expected_dir):]):
        _fail("handoff_receipt_path is not docs/control/tasks/<task_id>/handoff_vNNN.json")
    _require_sha256(parsed["handoff_receipt_sha256"], "handoff_receipt_sha256")
    return parsed


def _validate_safety_state(safety: object) -> dict:
    _require_exact_keys(safety, _SAFETY_KEYS, "safety_state")
    for key, expected in _EXPECTED_SAFETY.items():
        value = safety[key]
        if type(expected) is bool:
            _require_bool(value, f"safety_state {key}")
        elif type(expected) is int:
            _require_int(value, f"safety_state {key}")
        else:
            _require_str(value, f"safety_state {key}")
        if value != expected:
            _fail(f"safety_state {key} drifted from required value {expected!r}")
    _require_bool(safety["real_data_execution_requested"], "safety_state real_data_execution_requested")
    return safety


def _validate_required_artifacts(artifacts: object) -> list:
    if type(artifacts) is not list or not artifacts:
        _fail("required_artifacts must be a non-empty list")
    seen = set()
    for artifact in artifacts:
        _require_exact_keys(artifact, _ARTIFACT_KEYS, "required_artifacts entry")
        artifact_id = _require_str(artifact["artifact_id"], "artifact_id")
        if artifact_id in seen:
            _fail("required_artifacts contains a duplicate artifact_id")
        seen.add(artifact_id)
        _require_sha256(artifact["expected_manifest_sha256"], "expected_manifest_sha256")
        availability = _require_str(artifact["availability"], "availability")
        if availability not in _AVAILABILITY_STATES:
            _fail("availability must be UNAVAILABLE or VERIFIED_AVAILABLE")
        count = _require_int(artifact["verified_copy_count"], "verified_copy_count")
        if count < 0:
            _fail("verified_copy_count must be >= 0")
        paths = _require_str_list(artifact["canonical_paths"], "canonical_paths")
        for path in paths:
            for prefix in _PROHIBITED_CANONICAL_PATH_PREFIXES:
                if path == prefix or path.startswith(prefix + "/"):
                    _fail(f"canonical artifact path {path!r} is under prohibited prefix {prefix!r}")
        if len(set(paths)) != len(paths):
            _fail("canonical_paths must be unique; duplicates cannot evidence independent copies")
        if availability == "UNAVAILABLE":
            if count != 0:
                _fail("UNAVAILABLE artifact must have verified_copy_count 0")
            if paths:
                _fail("UNAVAILABLE artifact must not record canonical paths")
        if availability == "VERIFIED_AVAILABLE":
            if count < 2:
                _fail("VERIFIED_AVAILABLE requires at least two independently verified copies")
            if len(paths) < 2:
                _fail("VERIFIED_AVAILABLE requires at least two unique canonical paths")
            if count != len(paths):
                _fail("verified_copy_count must equal the number of unique canonical paths")
    if REQUIRED_ARTIFACT_ID not in seen:
        _fail(f"required artifact record {REQUIRED_ARTIFACT_ID!r} is missing")
    for artifact in artifacts:
        if artifact["artifact_id"] == REQUIRED_ARTIFACT_ID:
            if artifact["expected_manifest_sha256"] != REQUIRED_ARTIFACT_MANIFEST_SHA256:
                _fail("required artifact expected_manifest_sha256 drifted from the frozen fingerprint")
    return artifacts


def _validate_evidence(evidence: object, root: Path, *, verify_files: bool) -> list:
    """Validate evidence entries; historical receipts skip file re-hashing because
    evidence records what was observed when the immutable receipt was written."""
    if type(evidence) is not list:
        _fail("evidence must be a list")
    for item in evidence:
        _require_exact_keys(item, _EVIDENCE_KEYS, "evidence entry")
        path = _require_repo_relative(item["path"], "evidence path")
        expected = _require_sha256(item["sha256"], "evidence sha256")
        if not verify_files:
            continue
        target = root / path
        if not target.is_file():
            _fail(f"evidence file {path!r} is missing")
        if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
            _fail(f"evidence file {path!r} does not match its recorded sha256")
    return evidence


def _validate_receipt_body(parsed: dict, label: str, root: Path, *, verify_evidence_files: bool) -> int:
    """Structural fail-closed validation shared by the active receipt and every
    historical receipt in the predecessor chain. Does not validate the
    ``predecessor`` link itself; the chain walk owns that."""
    _require_exact_keys(parsed, _RECEIPT_KEYS, label)
    if parsed["schema_version"] != "0.1.0":
        _fail(f"{label} schema_version is not 0.1.0")
    if parsed["receipt_kind"] != "qnty_cross_agent_handoff_receipt":
        _fail(f"{label} receipt_kind is wrong")
    index = _require_int(parsed["receipt_index"], f"{label} receipt_index")
    if index < 1:
        _fail(f"{label} receipt_index must be >= 1")
    _require_str(parsed["source_branch"], f"{label} source_branch")
    head = parsed["source_head_commit"]
    if type(head) is not str or not _COMMIT_RE.fullmatch(head):
        _fail(f"{label} source_head_commit must be a lowercase 40-hex commit")
    _require_str_list(parsed["decisions"], f"{label} decisions", minimum=1)
    _validate_safety_state(parsed["safety_state"])
    scope = _require_str_list(parsed["changed_file_scope"], f"{label} changed_file_scope", minimum=1)
    for path in scope:
        _require_repo_relative(path, f"{label} changed_file_scope entry")
    _validate_evidence(parsed["evidence"], root, verify_files=verify_evidence_files)
    artifacts = _validate_required_artifacts(parsed["required_artifacts"])
    _require_str_list(parsed["blockers"], f"{label} blockers")
    _require_str_list(parsed["verified_commands"], f"{label} verified_commands", minimum=1)
    next_actions = parsed["next_actions"]
    if type(next_actions) is not list or len(next_actions) != 1:
        _fail(f"{label} next_actions must contain exactly one action")
    _require_str(next_actions[0], f"{label} next_actions entry")
    _require_str_list(parsed["prohibited_actions"], f"{label} prohibited_actions", minimum=1)
    if parsed["safety_state"]["real_data_execution_requested"]:
        for artifact in artifacts:
            if artifact["availability"] != "VERIFIED_AVAILABLE":
                _fail(f"{label}: real-data execution requested while a required artifact is not VERIFIED_AVAILABLE")
    return index


def _validate_receipt(parsed: dict, active: dict, root: Path) -> dict:
    _validate_receipt_body(parsed, "handoff_receipt", root, verify_evidence_files=True)
    if parsed["task_id"] != active["task_id"]:
        _fail("handoff_receipt task_id does not match active_task")
    if parsed["protocol_id"] != active["protocol_id"]:
        _fail("handoff_receipt protocol_id does not match active_task")
    if active["phase"] == "durable_artifact_store_configuration":
        _cross_check_artifact_records(parsed, root)
    _validate_predecessor_chain(parsed, root, active["handoff_receipt_path"])
    return parsed


def _cross_check_artifact_records(receipt: dict, root: Path) -> None:
    """Cross-check the active receipt's artifact summaries against the Git-owned
    artifact records under docs/artifacts/ (durable artifact plane v1).

    Applies to the active receipt only: historical receipts predate or
    postdate the registry state and stay validated by their immutable bytes.
    Fails closed when a record or the store registry is missing, noncanonical,
    not evidenced by the active receipt, or divergent from the receipt summary.
    """
    store_registry_path = root / STORE_REGISTRY_RELPATH
    if not store_registry_path.is_file():
        _fail(f"artifact store registry {STORE_REGISTRY_RELPATH} is missing")
    try:
        store_registry = validate_store_registry_bytes(store_registry_path.read_bytes())
    except ArtifactRegistryError as error:
        _fail(f"store registry invalid: {error}")
    evidence_by_path = {item["path"]: item["sha256"] for item in receipt["evidence"]}
    for artifact in receipt["required_artifacts"]:
        record_relpath = f"{ARTIFACT_RECORDS_DIR_RELPATH}/{artifact['artifact_id']}.json"
        record_path = root / record_relpath
        if not record_path.is_file():
            _fail(f"artifact record {record_relpath} is missing")
        record_bytes = record_path.read_bytes()
        record_sha = hashlib.sha256(record_bytes).hexdigest()
        if evidence_by_path.get(record_relpath) != record_sha:
            _fail(f"artifact record {record_relpath} hash is not evidenced by the active handoff receipt")
        try:
            record = validate_artifact_record_bytes(record_bytes, expected_artifact_id=artifact["artifact_id"])
            cross_check_receipt_artifact(artifact, record, store_registry)
        except ArtifactRegistryError as error:
            _fail(f"artifact record {record_relpath} invalid: {error}")


def _validate_predecessor_chain(parsed: dict, root: Path, receipt_relpath: str) -> None:
    """Iteratively walk the append-only receipt chain from the active receipt all
    the way to the explicit GENESIS state, failing closed on any broken link."""
    expected_dir = f"docs/control/tasks/{TASK_ID}/"
    visited = {receipt_relpath}
    current = parsed
    current_index = parsed["receipt_index"]
    while True:
        predecessor = current["predecessor"]
        if current_index == 1:
            if predecessor != "GENESIS":
                _fail("receipt_index 1 must declare the explicit genesis state 'GENESIS'")
            return
        if predecessor == "GENESIS":
            _fail("GENESIS is only valid at receipt_index 1")
        _require_exact_keys(predecessor, _PREDECESSOR_KEYS, "predecessor")
        path = _require_repo_relative(predecessor["path"], "predecessor path")
        if not path.startswith(expected_dir) or not _RECEIPT_BASENAME_RE.fullmatch(path[len(expected_dir):]):
            _fail("predecessor path must be docs/control/tasks/<task_id>/handoff_vNNN.json")
        if path in visited:
            _fail("predecessor chain contains a cycle or repeated receipt path")
        visited.add(path)
        expected_sha = _require_sha256(predecessor["sha256"], "predecessor sha256")
        target = root / path
        if not target.is_file():
            _fail(f"predecessor receipt {path!r} is missing")
        data = target.read_bytes()
        if hashlib.sha256(data).hexdigest() != expected_sha:
            _fail(f"predecessor receipt {path!r} bytes do not match the recorded sha256")
        previous = _load_canonical_document(data, "predecessor receipt")
        previous_index = _validate_receipt_body(previous, "predecessor receipt", root, verify_evidence_files=False)
        if previous_index != current_index - 1:
            _fail("predecessor receipt_index does not chain to this receipt")
        if previous["task_id"] != parsed["task_id"] or previous["protocol_id"] != parsed["protocol_id"]:
            _fail("predecessor identity does not match this receipt")
        current = previous
        current_index = previous_index


def _validate_entrypoints(root: Path) -> None:
    start_here = root / START_HERE_RELPATH
    if not start_here.is_file():
        _fail(f"canonical shared contract {START_HERE_RELPATH} is missing")
    if ACTIVE_TASK_RELPATH not in start_here.read_text(encoding="utf-8"):
        _fail("canonical shared contract does not point at the machine-readable control state")
    claude = root / CLAUDE_ENTRYPOINT_RELPATH
    if not claude.is_file() or CLAUDE_CONTRACT_POINTER not in claude.read_text(encoding="utf-8"):
        _fail("CLAUDE.md entrypoint is missing the canonical-contract import pointer")
    agents = root / CODEX_ENTRYPOINT_RELPATH
    if not agents.is_file():
        _fail("AGENTS.md entrypoint is missing")
    agents_text = agents.read_text(encoding="utf-8")
    if CODEX_CONTRACT_POINTER not in agents_text:
        _fail("AGENTS.md entrypoint is missing the canonical-contract pointer")
    if VERIFY_COMMAND not in agents_text:
        _fail("AGENTS.md entrypoint does not require running the context verifier")


def load_and_verify_continuity_state(root: Path) -> dict:
    """Fail-closed load of the whole continuity control plane rooted at *root*."""
    root = Path(root)
    active_path = root / ACTIVE_TASK_RELPATH
    if not active_path.is_file():
        _fail(f"{ACTIVE_TASK_RELPATH} is missing")
    active = _validate_active_task(_load_canonical_document(active_path.read_bytes(), "active_task"))
    receipt_path = root / active["handoff_receipt_path"]
    if not receipt_path.is_file():
        _fail(f"handoff receipt {active['handoff_receipt_path']!r} is missing")
    receipt_bytes = receipt_path.read_bytes()
    digest = hashlib.sha256(receipt_bytes).hexdigest()
    if digest != active["handoff_receipt_sha256"]:
        _fail("active_task pointer is stale: handoff receipt bytes do not match handoff_receipt_sha256")
    receipt = _validate_receipt(_load_canonical_document(receipt_bytes, "handoff_receipt"), active, root)
    _validate_entrypoints(root)
    return {
        "active_task": active,
        "handoff_receipt": receipt,
        "handoff_receipt_sha256": digest,
    }


def render_context_packet(state: dict) -> str:
    """Deterministic context packet derived only from validated state."""
    active = state["active_task"]
    receipt = state["handoff_receipt"]
    safety = receipt["safety_state"]
    lines = [
        "QNTY_CONTINUITY_CONTEXT_PACKET schema=0.1.0",
        f"TASK={active['task_id']}",
        f"PROTOCOL={active['protocol_id']}",
        f"PHASE={active['phase']}",
        (
            "SAFETY"
            f" edge_status={safety['edge_status']}"
            f" live_status={safety['live_status']}"
            f" scientific_use_authorized={str(safety['scientific_use_authorized']).lower()}"
            f" paper_trade_authorized={str(safety['paper_trade_authorized']).lower()}"
            f" live_integration_authorized={str(safety['live_integration_authorized']).lower()}"
            f" execution_count={safety['decomposition_execution_count']}/{safety['decomposition_execution_budget']}"
            f" quarantine_access={safety['quarantine_access']}"
        ),
    ]
    blocked_reasons = [
        f"artifact_not_verified_available:{artifact['artifact_id']}"
        for artifact in receipt["required_artifacts"]
        if artifact["availability"] != "VERIFIED_AVAILABLE"
    ]
    if blocked_reasons:
        lines.append("PROTOCOL_EXECUTION=BLOCKED reasons=" + ",".join(sorted(blocked_reasons)))
    else:
        lines.append("PROTOCOL_EXECUTION=NOT_AUTHORIZED_HERE reasons=preregistration_preconditions_apply")
    lines.append(
        "LATEST_HANDOFF"
        f" path={active['handoff_receipt_path']}"
        f" sha256={state['handoff_receipt_sha256']}"
        f" index={receipt['receipt_index']}"
    )
    for blocker in receipt["blockers"]:
        lines.append(f"BLOCKER={blocker}")
    lines.append(f"NEXT_ACTION={receipt['next_actions'][0]}")
    for artifact in receipt["required_artifacts"]:
        lines.append(
            "REQUIRED_ARTIFACT"
            f" id={artifact['artifact_id']}"
            f" expected_manifest_sha256={artifact['expected_manifest_sha256']}"
            f" availability={artifact['availability']}"
            f" verified_copies={artifact['verified_copy_count']}"
        )
    for prohibited in receipt["prohibited_actions"]:
        lines.append(f"PROHIBITED={prohibited}")
    return "\n".join(lines)
