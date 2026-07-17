"""Synthetic fail-closed tests for the cross-agent continuity control plane.

No real data, no protocol execution: every tree is built from scratch in
tmp_path, plus read-only validation of the committed production control state.
"""

import ast
import copy
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from quantbot.continuity import context
from quantbot.continuity.context import (
    canonical_json_bytes,
    load_and_verify_continuity_state,
    render_context_packet,
)

ROOT = Path(__file__).parents[2]
TASK_ID = context.TASK_ID
PROTOCOL_ID = context.PROTOCOL_ID
TASK_DIR = f"docs/control/tasks/{TASK_ID}"

EVIDENCE_BYTES = b"synthetic evidence only\n"
EVIDENCE_SHA = hashlib.sha256(EVIDENCE_BYTES).hexdigest()

CLAUDE_TEXT = "# CLAUDE\n\n@docs/agent/START_HERE.md\n"
AGENTS_TEXT = (
    "# AGENTS\n\nRead docs/agent/START_HERE.md first, then run\n"
    "`python -m quantbot.continuity verify` and stop on failure.\n"
)
START_HERE_TEXT = "# START_HERE\n\nControl state: docs/control/active_task.json\n"


def base_receipt():
    return {
        "schema_version": "0.1.0",
        "receipt_kind": "qnty_cross_agent_handoff_receipt",
        "receipt_index": 1,
        "task_id": TASK_ID,
        "protocol_id": PROTOCOL_ID,
        "source_branch": "main",
        "source_head_commit": "d6aa7d7a4f5075e91e0a0dd26bf934cb9f8ea7da",
        "predecessor": "GENESIS",
        "decisions": ["synthetic decision"],
        "safety_state": {
            "edge_status": "EDGE_UNPROVEN",
            "live_status": "BLOCK_LIVE_INTEGRATION",
            "scientific_use_authorized": False,
            "paper_trade_authorized": False,
            "live_integration_authorized": False,
            "decomposition_execution_budget": 1,
            "decomposition_execution_count": 0,
            "quarantine_access": "forbidden",
            "real_data_execution_requested": False,
        },
        "changed_file_scope": ["docs/control/active_task.json"],
        "evidence": [{"path": "docs/evidence.txt", "sha256": EVIDENCE_SHA}],
        "required_artifacts": [
            {
                "artifact_id": context.REQUIRED_ARTIFACT_ID,
                "expected_manifest_sha256": context.REQUIRED_ARTIFACT_MANIFEST_SHA256,
                "availability": "UNAVAILABLE",
                "verified_copy_count": 0,
                "canonical_paths": [],
            }
        ],
        "blockers": ["synthetic blocker"],
        "verified_commands": ["python -m pytest tests/continuity -q"],
        "next_actions": ["IMPLEMENT_DURABLE_ARTIFACT_PLANE"],
        "prohibited_actions": ["EXECUTE_CANDIDATE1_PROTOCOL"],
    }


def write_tree(
    root,
    receipt,
    active_mutation=None,
    *,
    receipt_name="handoff_v001.json",
    claude_text=CLAUDE_TEXT,
    agents_text=AGENTS_TEXT,
    start_here_text=START_HERE_TEXT,
    extra_receipts=(),
    phase="frozen_input_recovery_design",
):
    (root / TASK_DIR).mkdir(parents=True, exist_ok=True)
    (root / "docs/agent").mkdir(parents=True, exist_ok=True)
    (root / "docs/evidence.txt").write_bytes(EVIDENCE_BYTES)
    for name, extra in extra_receipts:
        (root / TASK_DIR / name).write_bytes(canonical_json_bytes(extra))
    receipt_bytes = canonical_json_bytes(receipt)
    (root / TASK_DIR / receipt_name).write_bytes(receipt_bytes)
    active = {
        "schema_version": "0.1.0",
        "control_kind": "qnty_active_task_pointer",
        "task_id": TASK_ID,
        "protocol_id": PROTOCOL_ID,
        "phase": phase,
        "handoff_receipt_path": f"{TASK_DIR}/{receipt_name}",
        "handoff_receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
    }
    if active_mutation is not None:
        active_mutation(active)
    (root / "docs/control/active_task.json").write_bytes(canonical_json_bytes(active))
    if claude_text is not None:
        (root / "CLAUDE.md").write_text(claude_text, encoding="utf-8")
    if agents_text is not None:
        (root / "AGENTS.md").write_text(agents_text, encoding="utf-8")
    if start_here_text is not None:
        (root / "docs/agent/START_HERE.md").write_text(start_here_text, encoding="utf-8")
    return root


def durable_artifact_receipt_and_record(*, verified=False):
    """Synthetic v002 artifact-plane control state; never uses real bytes."""
    first = base_receipt()
    receipt = base_receipt()
    receipt.update(
        receipt_index=2,
        predecessor={"path": f"{TASK_DIR}/handoff_v001.json", "sha256": hashlib.sha256(canonical_json_bytes(first)).hexdigest()},
        next_actions=["CONFIGURE_TWO_DURABLE_ARTIFACT_STORES"],
    )
    portable = "a" * 64
    stores = []
    copies = []
    if verified:
        stores = [
            {"backend_kind": "filesystem", "failure_domain": "domain-a", "read_enabled": True, "root_environment_variable": "SYNTHETIC_STORE_A", "store_id": "store-a", "write_enabled": True},
            {"backend_kind": "filesystem", "failure_domain": "domain-b", "read_enabled": True, "root_environment_variable": "SYNTHETIC_STORE_B", "store_id": "store-b", "write_enabled": True},
        ]
        copies = [
            {"canonical_location": f"qnty-artifact://store-{suffix}/sha256/{portable}", "failure_domain": f"domain-{suffix}", "manifest_sha256": portable, "object_verification": {"passed": True, "verified_object_count": 1}, "restore_verification": {"passed": True, "restored_manifest_sha256": portable}, "store_id": f"store-{suffix}"}
            for suffix in ("a", "b")
        ]
        receipt["required_artifacts"][0].update(availability="VERIFIED_AVAILABLE", verified_copy_count=2, canonical_paths=[copy["canonical_location"] for copy in copies])
    record = {
        "artifact_id": context.REQUIRED_ARTIFACT_ID,
        "artifact_record_kind": "qnty_artifact_record",
        "availability": "VERIFIED_AVAILABLE" if verified else "UNAVAILABLE",
        "copies": copies,
        "expected_roles": ["bars", "funding"],
        "legacy_bindings": {"legacy_input_manifest_fingerprint": context.REQUIRED_ARTIFACT_MANIFEST_SHA256, "nested_first_statistic_data_binding": "7c8552f10cf8f72c859335a5f4af8ca36094bffed695428a9c93a1033ef86c6f", "outer_data_cut_fingerprint": "020eac5e9659138e4c66b2fb2b44020a9b894b0500f51fd935014c5b37f55224", "protocol_id": PROTOCOL_ID},
        "portable_manifest_sha256": portable if verified else None,
        "schema_version": "1.0.0",
    }
    registry = {"schema_version": "1.0.0", "store_registry_kind": "qnty_artifact_store_registry", "stores": stores}
    return first, receipt, record, registry


def write_durable_artifact_tree(root, *, verified=False):
    first, receipt, record, registry = durable_artifact_receipt_and_record(verified=verified)
    artifacts = root / "docs/artifacts"
    artifacts.mkdir(parents=True)
    record_path = artifacts / "candidate1-real-input-v0.json"
    record_bytes = canonical_json_bytes(record)
    record_path.write_bytes(record_bytes)
    registry_bytes = canonical_json_bytes(registry)
    (artifacts / "stores.json").write_bytes(registry_bytes)
    receipt["evidence"].append({"path": "docs/artifacts/candidate1-real-input-v0.json", "sha256": hashlib.sha256(record_bytes).hexdigest()})
    receipt["evidence"].append({"path": "docs/artifacts/stores.json", "sha256": hashlib.sha256(registry_bytes).hexdigest()})
    return write_tree(root, receipt, receipt_name="handoff_v002.json", extra_receipts=[("handoff_v001.json", first)], phase="durable_artifact_store_configuration")


def test_synthetic_tree_verifies_and_renders(tmp_path):
    write_tree(tmp_path, base_receipt())
    state = load_and_verify_continuity_state(tmp_path)
    packet = render_context_packet(state)
    assert "TASK=" + TASK_ID in packet
    assert "NEXT_ACTION=IMPLEMENT_DURABLE_ARTIFACT_PLANE" in packet
    assert "PROTOCOL_EXECUTION=BLOCKED" in packet
    assert f"artifact_not_verified_available:{context.REQUIRED_ARTIFACT_ID}" in packet


def test_production_control_state_verifies():
    state = load_and_verify_continuity_state(ROOT)
    receipt = state["handoff_receipt"]
    assert receipt["safety_state"]["decomposition_execution_count"] == 0
    assert receipt["next_actions"] in (["IMPLEMENT_DURABLE_ARTIFACT_PLANE"], ["CONFIGURE_TWO_DURABLE_ARTIFACT_STORES"], ["IMPLEMENT_CANDIDATE1_V1_SYNTHETIC_SANDBOX_SCAFFOLD"])
    packet = render_context_packet(state)
    assert "PROTOCOL_EXECUTION=BLOCKED" in packet
    assert "availability=UNAVAILABLE" in packet


def test_rendering_is_deterministic_and_does_not_mutate_state(tmp_path):
    write_tree(tmp_path, base_receipt())
    state_a = load_and_verify_continuity_state(tmp_path)
    state_b = load_and_verify_continuity_state(tmp_path)
    assert state_a == state_b
    before = copy.deepcopy(state_a)
    assert render_context_packet(state_a) == render_context_packet(state_a)
    assert render_context_packet(state_a) == render_context_packet(state_b)
    assert state_a == before


@pytest.mark.parametrize("key", sorted(base_receipt()))
def test_each_missing_receipt_key_fails_closed(tmp_path, key):
    receipt = base_receipt()
    receipt.pop(key)
    write_tree(tmp_path, receipt)
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(tmp_path)


@pytest.mark.parametrize("key", sorted(base_receipt()["safety_state"]))
def test_each_missing_safety_key_fails_closed(tmp_path, key):
    receipt = base_receipt()
    receipt["safety_state"].pop(key)
    write_tree(tmp_path, receipt)
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(tmp_path)


@pytest.mark.parametrize("mutation", [
    lambda r: r.update(extra_key="no"),
    lambda r: r["safety_state"].update(extra_key="no"),
    lambda r: r["required_artifacts"][0].update(extra_key="no"),
    lambda r: r["evidence"][0].update(extra_key="no"),
    lambda r: r.update(receipt_kind="wrong_kind"),
    lambda r: r.update(schema_version="9.9.9"),
    lambda r: r.update(task_id="WRONG_TASK"),
    lambda r: r.update(protocol_id="wrong_protocol"),
    lambda r: r.update(receipt_index=0),
    lambda r: r.update(receipt_index=True),
    lambda r: r.update(receipt_index="1"),
    lambda r: r.update(source_branch=""),
    lambda r: r.update(source_head_commit="D6AA7D7A4F5075E91E0A0DD26BF934CB9F8EA7DA"),
    lambda r: r.update(source_head_commit="d6aa7d7"),
    lambda r: r.update(predecessor=None),
    lambda r: r.update(predecessor={"path": f"{TASK_DIR}/handoff_v000.json", "sha256": "0" * 64}),
    lambda r: r.update(decisions=[]),
    lambda r: r.update(decisions="not a list"),
    lambda r: r.update(changed_file_scope=[]),
    lambda r: r.update(changed_file_scope=["/absolute/path"]),
    lambda r: r.update(changed_file_scope=["../escape"]),
    lambda r: r.update(verified_commands=[]),
    lambda r: r.update(next_actions=[]),
    lambda r: r.update(next_actions=["A", "B"]),
    lambda r: r.update(next_actions="IMPLEMENT_DURABLE_ARTIFACT_PLANE"),
    lambda r: r.update(prohibited_actions=[]),
    lambda r: r.update(required_artifacts=[]),
])
def test_receipt_shape_mutations_fail_closed(tmp_path, mutation):
    receipt = base_receipt()
    mutation(receipt)
    write_tree(tmp_path, receipt)
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(tmp_path)


@pytest.mark.parametrize("mutation", [
    lambda s: s.update(edge_status="EDGE_PROVEN"),
    lambda s: s.update(live_status="ALLOW_LIVE"),
    lambda s: s.update(scientific_use_authorized=True),
    lambda s: s.update(paper_trade_authorized=True),
    lambda s: s.update(live_integration_authorized=True),
    lambda s: s.update(scientific_use_authorized=0),
    lambda s: s.update(decomposition_execution_count=1),
    lambda s: s.update(decomposition_execution_count=True),
    lambda s: s.update(decomposition_execution_budget=2),
    lambda s: s.update(decomposition_execution_budget=True),
    lambda s: s.update(quarantine_access="allowed"),
    lambda s: s.update(real_data_execution_requested="false"),
])
def test_safety_state_drift_fails_closed(tmp_path, mutation):
    receipt = base_receipt()
    mutation(receipt["safety_state"])
    write_tree(tmp_path, receipt)
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(tmp_path)


@pytest.mark.parametrize("mutation", [
    lambda a: a.update(artifact_id="wrong-artifact"),
    lambda a: a.update(expected_manifest_sha256="0" * 64),
    lambda a: a.update(expected_manifest_sha256=context.REQUIRED_ARTIFACT_MANIFEST_SHA256.upper()),
    lambda a: a.update(expected_manifest_sha256="zz"),
    lambda a: a.update(availability="AVAILABLE"),
    lambda a: a.update(availability="unavailable"),
    lambda a: a.update(verified_copy_count=1),
    lambda a: a.update(verified_copy_count=True),
    lambda a: a.update(verified_copy_count=-1),
    lambda a: a.update(canonical_paths=["/tmp/candidate1"]),
    lambda a: a.update(canonical_paths=["/tmp"]),
    lambda a: a.update(canonical_paths=["/srv/qnty/inputs/candidate1"]),
    lambda a: a.update(availability="VERIFIED_AVAILABLE", verified_copy_count=1,
                       canonical_paths=["/srv/artifacts/candidate1"]),
    lambda a: a.update(availability="VERIFIED_AVAILABLE", verified_copy_count=2,
                       canonical_paths=[]),
])
def test_required_artifact_mutations_fail_closed(tmp_path, mutation):
    receipt = base_receipt()
    mutation(receipt["required_artifacts"][0])
    write_tree(tmp_path, receipt)
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(tmp_path)


def test_real_data_execution_request_with_unavailable_artifact_fails(tmp_path):
    receipt = base_receipt()
    receipt["safety_state"]["real_data_execution_requested"] = True
    write_tree(tmp_path, receipt)
    with pytest.raises(ValueError, match="not VERIFIED_AVAILABLE"):
        load_and_verify_continuity_state(tmp_path)


def test_verified_artifact_with_two_copies_allows_request_flag(tmp_path):
    root = write_durable_artifact_tree(tmp_path, verified=True)
    receipt_path = root / TASK_DIR / "handoff_v002.json"
    receipt = json.loads(receipt_path.read_bytes())
    receipt["safety_state"]["real_data_execution_requested"] = True
    receipt_data = canonical_json_bytes(receipt)
    receipt_path.write_bytes(receipt_data)
    active_path = root / "docs/control/active_task.json"
    active = json.loads(active_path.read_bytes())
    active["handoff_receipt_sha256"] = hashlib.sha256(receipt_data).hexdigest()
    active_path.write_bytes(canonical_json_bytes(active))
    with pytest.raises(ValueError, match="current artifact operational verification"):
        load_and_verify_continuity_state(root)


def test_receipt_byte_change_breaks_active_pointer(tmp_path):
    write_tree(tmp_path, base_receipt())
    receipt_path = tmp_path / TASK_DIR / "handoff_v001.json"
    receipt_path.write_bytes(receipt_path.read_bytes().replace(b"synthetic blocker", b"synthetic Blocker"))
    with pytest.raises(ValueError, match="stale"):
        load_and_verify_continuity_state(tmp_path)


def test_missing_receipt_fails_closed(tmp_path):
    write_tree(tmp_path, base_receipt())
    (tmp_path / TASK_DIR / "handoff_v001.json").unlink()
    with pytest.raises(ValueError, match="missing"):
        load_and_verify_continuity_state(tmp_path)


@pytest.mark.parametrize("tail", [b"\n", b" ", b"\t"])
def test_noncanonical_receipt_bytes_fail_even_with_matching_hash(tmp_path, tail):
    write_tree(tmp_path, base_receipt())
    receipt_path = tmp_path / TASK_DIR / "handoff_v001.json"
    data = receipt_path.read_bytes() + tail
    receipt_path.write_bytes(data)
    active_path = tmp_path / "docs/control/active_task.json"
    active = json.loads(active_path.read_bytes())
    active["handoff_receipt_sha256"] = hashlib.sha256(data).hexdigest()
    active_path.write_bytes(canonical_json_bytes(active))
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(tmp_path)


def test_pretty_printed_active_task_fails_closed(tmp_path):
    write_tree(tmp_path, base_receipt())
    active_path = tmp_path / "docs/control/active_task.json"
    active = json.loads(active_path.read_bytes())
    active_path.write_text(json.dumps(active, indent=2), encoding="utf-8")
    with pytest.raises(ValueError, match="canonical"):
        load_and_verify_continuity_state(tmp_path)


@pytest.mark.parametrize("mutation", [
    lambda a: a.update(extra_key="no"),
    lambda a: a.pop("phase"),
    lambda a: a.update(control_kind="wrong"),
    lambda a: a.update(schema_version="9.9.9"),
    lambda a: a.update(task_id="WRONG_TASK"),
    lambda a: a.update(protocol_id="wrong_protocol"),
    lambda a: a.update(phase=""),
    lambda a: a.update(handoff_receipt_path="docs/elsewhere/handoff_v001.json"),
    lambda a: a.update(handoff_receipt_path=f"{TASK_DIR}/handoff_1.json"),
    lambda a: a.update(handoff_receipt_sha256="0" * 64),
    lambda a: a.update(handoff_receipt_sha256=("0" * 63) + "G"),
    lambda a: a.update(handoff_receipt_sha256=None),
])
def test_active_task_mutations_fail_closed(tmp_path, mutation):
    write_tree(tmp_path, base_receipt(), active_mutation=mutation)
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(tmp_path)


def test_uppercase_receipt_hash_in_active_pointer_fails(tmp_path):
    def uppercase(active):
        active["handoff_receipt_sha256"] = active["handoff_receipt_sha256"].upper()

    write_tree(tmp_path, base_receipt(), active_mutation=uppercase)
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(tmp_path)


def test_evidence_tamper_and_missing_file_fail_closed(tmp_path):
    write_tree(tmp_path, base_receipt())
    evidence = tmp_path / "docs/evidence.txt"
    evidence.write_bytes(b"tampered\n")
    with pytest.raises(ValueError, match="evidence"):
        load_and_verify_continuity_state(tmp_path)
    evidence.unlink()
    with pytest.raises(ValueError, match="evidence"):
        load_and_verify_continuity_state(tmp_path)


def second_receipt(predecessor_bytes):
    receipt = base_receipt()
    receipt["receipt_index"] = 2
    receipt["predecessor"] = {
        "path": f"{TASK_DIR}/handoff_v001.json",
        "sha256": hashlib.sha256(predecessor_bytes).hexdigest(),
    }
    return receipt


def test_valid_predecessor_chain_verifies(tmp_path):
    first = base_receipt()
    first_bytes = canonical_json_bytes(first)
    write_tree(
        tmp_path,
        second_receipt(first_bytes),
        receipt_name="handoff_v002.json",
        extra_receipts=[("handoff_v001.json", first)],
    )
    state = load_and_verify_continuity_state(tmp_path)
    assert state["handoff_receipt"]["receipt_index"] == 2


@pytest.mark.parametrize("mutation", [
    lambda r: r["predecessor"].update(sha256="0" * 64),
    lambda r: r["predecessor"].update(path=f"{TASK_DIR}/handoff_v009.json"),
    lambda r: r["predecessor"].update(path="docs/elsewhere/handoff_v001.json"),
    lambda r: r["predecessor"].pop("sha256"),
    lambda r: r["predecessor"].update(extra_key="no"),
    lambda r: r.update(receipt_index=3),
    lambda r: r.update(predecessor="GENESIS"),
])
def test_predecessor_chain_mismatch_fails_closed(tmp_path, mutation):
    first = base_receipt()
    first_bytes = canonical_json_bytes(first)
    receipt = second_receipt(first_bytes)
    mutation(receipt)
    write_tree(
        tmp_path,
        receipt,
        receipt_name="handoff_v002.json",
        extra_receipts=[("handoff_v001.json", first)],
    )
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(tmp_path)


@pytest.mark.parametrize("kwargs", [
    {"claude_text": None},
    {"claude_text": "# CLAUDE\n\nno pointer here\n"},
    {"claude_text": "# CLAUDE\n\nsee docs/agent/START_HERE.md (plain mention, no @import)\n"},
    {"agents_text": None},
    {"agents_text": "# AGENTS\n\nrun `python -m quantbot.continuity verify` only\n"},
    {"agents_text": "# AGENTS\n\nRead docs/agent/START_HERE.md but never verify\n"},
    {"start_here_text": None},
    {"start_here_text": "# START_HERE\n\nno control-state pointer\n"},
])
def test_entrypoint_drift_fails_closed(tmp_path, kwargs):
    write_tree(tmp_path, base_receipt(), **kwargs)
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(tmp_path)


@pytest.mark.parametrize("mutation", [
    lambda a: a.update(availability="VERIFIED_AVAILABLE", verified_copy_count=2,
                       canonical_paths=["/archive/a"]),
    lambda a: a.update(availability="VERIFIED_AVAILABLE", verified_copy_count=2,
                       canonical_paths=["/archive/a", "/archive/a"]),
    lambda a: a.update(availability="VERIFIED_AVAILABLE", verified_copy_count=3,
                       canonical_paths=["/archive/a", "/archive/b"]),
    lambda a: a.update(availability="VERIFIED_AVAILABLE", verified_copy_count=True,
                       canonical_paths=["/archive/a", "/archive/b"]),
    lambda a: a.update(canonical_paths=["/archive/a"]),
    lambda a: a.update(canonical_paths=["/archive/a", "/archive/a", "/archive/b"]),
])
def test_copy_evidence_gaps_fail_closed(tmp_path, mutation):
    receipt = base_receipt()
    mutation(receipt["required_artifacts"][0])
    write_tree(tmp_path, receipt)
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(tmp_path)


def test_two_unique_canonical_copies_accept(tmp_path):
    receipt = base_receipt()
    receipt["required_artifacts"][0].update(
        availability="VERIFIED_AVAILABLE",
        verified_copy_count=2,
        canonical_paths=["/home/viktor/qnty-artifacts/copy-a", "/mnt/qnty-backup/copy-b"],
    )
    write_tree(tmp_path, receipt)
    state = load_and_verify_continuity_state(tmp_path)
    artifact = state["handoff_receipt"]["required_artifacts"][0]
    assert artifact["verified_copy_count"] == len(artifact["canonical_paths"]) == 2


def build_chain(tmp_path, mutate_v001=None, mutate_v002=None):
    v001 = base_receipt()
    if mutate_v001 is not None:
        mutate_v001(v001)
    v002 = base_receipt()
    v002["receipt_index"] = 2
    v002["predecessor"] = {
        "path": f"{TASK_DIR}/handoff_v001.json",
        "sha256": hashlib.sha256(canonical_json_bytes(v001)).hexdigest(),
    }
    if mutate_v002 is not None:
        mutate_v002(v002)
    v003 = base_receipt()
    v003["receipt_index"] = 3
    v003["predecessor"] = {
        "path": f"{TASK_DIR}/handoff_v002.json",
        "sha256": hashlib.sha256(canonical_json_bytes(v002)).hexdigest(),
    }
    return write_tree(
        tmp_path,
        v003,
        receipt_name="handoff_v003.json",
        extra_receipts=[("handoff_v001.json", v001), ("handoff_v002.json", v002)],
    )


def test_three_level_chain_verifies(tmp_path):
    build_chain(tmp_path)
    state = load_and_verify_continuity_state(tmp_path)
    assert state["handoff_receipt"]["receipt_index"] == 3


def test_corrupted_genesis_bytes_reject_despite_valid_immediate_link(tmp_path):
    build_chain(tmp_path)
    corrupted = base_receipt()
    corrupted["decisions"] = ["forged history"]
    (tmp_path / TASK_DIR / "handoff_v001.json").write_bytes(canonical_json_bytes(corrupted))
    with pytest.raises(ValueError, match="sha256"):
        load_and_verify_continuity_state(tmp_path)


def test_wrong_genesis_hash_recorded_in_v002_rejects(tmp_path):
    build_chain(tmp_path, mutate_v002=lambda r: r["predecessor"].update(sha256="0" * 64))
    with pytest.raises(ValueError, match="sha256"):
        load_and_verify_continuity_state(tmp_path)


def test_missing_genesis_receipt_rejects(tmp_path):
    build_chain(tmp_path)
    (tmp_path / TASK_DIR / "handoff_v001.json").unlink()
    with pytest.raises(ValueError, match="missing"):
        load_and_verify_continuity_state(tmp_path)


@pytest.mark.parametrize("mutate_v002", [
    lambda r: r.update(receipt_index=5),
    lambda r: r.update(task_id="OTHER_TASK"),
    lambda r: r.update(protocol_id="other_protocol"),
    lambda r: r.update(predecessor="GENESIS"),
    lambda r: r["predecessor"].update(path=f"{TASK_DIR}/handoff_v002.json"),
    lambda r: r["predecessor"].update(path=f"{TASK_DIR}/handoff_v003.json"),
    lambda r: r["predecessor"].update(path="docs/control/tasks/OTHER_TASK/handoff_v001.json"),
    lambda r: r["predecessor"].update(path=f"{TASK_DIR}/../escape/handoff_v001.json"),
    lambda r: r["predecessor"].update(path=f"{TASK_DIR}/notes_v001.json"),
])
def test_deep_chain_link_mutations_fail_closed(tmp_path, mutate_v002):
    build_chain(tmp_path, mutate_v002=mutate_v002)
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(tmp_path)


@pytest.mark.parametrize("mutate_v001", [
    lambda r: r.update(extra_key="no"),
    lambda r: r.update(receipt_index=True),
    lambda r: r.update(predecessor={"path": f"{TASK_DIR}/handoff_v000.json", "sha256": "0" * 64}),
    lambda r: r["safety_state"].update(decomposition_execution_count=1),
    lambda r: r["safety_state"].update(live_integration_authorized=True),
    lambda r: r.update(next_actions=["A", "B"]),
])
def test_deep_chain_genesis_receipt_mutations_fail_closed(tmp_path, mutate_v001):
    build_chain(tmp_path, mutate_v001=mutate_v001)
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(tmp_path)


def test_historical_receipt_evidence_files_are_format_checked_not_rehashed(tmp_path):
    def add_stale_evidence(receipt):
        receipt["evidence"] = [
            {"path": "docs/evidence.txt", "sha256": EVIDENCE_SHA},
            {"path": "docs/no_longer_present.txt", "sha256": "1" * 64},
        ]

    build_chain(tmp_path, mutate_v001=add_stale_evidence)
    state = load_and_verify_continuity_state(tmp_path)
    assert state["handoff_receipt"]["receipt_index"] == 3


def test_cli_verify_and_show_roundtrip(tmp_path, capsys):
    from quantbot.continuity.__main__ import main

    write_tree(tmp_path, base_receipt())
    assert main(["verify", "--root", str(tmp_path)]) == 0
    assert main(["show", "--root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "CONTINUITY_VERIFY_OK" in out
    assert "QNTY_CONTINUITY_CONTEXT_PACKET" in out
    (tmp_path / "AGENTS.md").unlink()
    assert main(["verify", "--root", str(tmp_path)]) == 1
    assert "CONTINUITY_VERIFY_FAILED" in capsys.readouterr().err


def test_validator_has_only_stdlib_imports():
    allowed = {"__future__", "hashlib", "json", "pathlib", "re", "quantbot.artifacts.registry"}
    tree = ast.parse((ROOT / "quantbot/continuity/context.py").read_text(encoding="utf-8"))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0 and node.module is not None
            modules.add(node.module)
    assert modules == allowed


def test_durable_artifact_record_and_handoff_agree(tmp_path):
    state = load_and_verify_continuity_state(write_durable_artifact_tree(tmp_path))
    assert state["handoff_receipt"]["next_actions"] == ["CONFIGURE_TWO_DURABLE_ARTIFACT_STORES"]


def test_durable_artifact_record_missing_rejects(tmp_path):
    root = write_durable_artifact_tree(tmp_path)
    (root / "docs/artifacts/candidate1-real-input-v0.json").unlink()
    with pytest.raises(ValueError, match="evidence file"):
        load_and_verify_continuity_state(root)


def test_durable_artifact_record_change_without_evidence_update_rejects(tmp_path):
    root = write_durable_artifact_tree(tmp_path)
    record_path = root / "docs/artifacts/candidate1-real-input-v0.json"
    record = json.loads(record_path.read_bytes())
    record["legacy_bindings"]["outer_data_cut_fingerprint"] = "f" * 64
    record_path.write_bytes(canonical_json_bytes(record))
    with pytest.raises(ValueError, match="evidence file"):
        load_and_verify_continuity_state(root)


def test_active_receipt_missing_store_registry_evidence_rejects(tmp_path):
    root = write_durable_artifact_tree(tmp_path)
    receipt_path = root / TASK_DIR / "handoff_v002.json"
    receipt = json.loads(receipt_path.read_bytes())
    receipt["evidence"] = [item for item in receipt["evidence"] if item["path"] != "docs/artifacts/stores.json"]
    receipt_data = canonical_json_bytes(receipt)
    receipt_path.write_bytes(receipt_data)
    active_path = root / "docs/control/active_task.json"
    active = json.loads(active_path.read_bytes())
    active["handoff_receipt_sha256"] = hashlib.sha256(receipt_data).hexdigest()
    active_path.write_bytes(canonical_json_bytes(active))
    with pytest.raises(ValueError, match="store registry hash"):
        load_and_verify_continuity_state(root)


def test_active_receipt_store_registry_mutation_rejects(tmp_path):
    root = write_durable_artifact_tree(tmp_path)
    registry_path = root / "docs/artifacts/stores.json"
    registry = json.loads(registry_path.read_bytes())
    registry["stores"].append({"backend_kind": "filesystem", "failure_domain": "domain-c", "read_enabled": True, "root_environment_variable": "SYNTHETIC_STORE_C", "store_id": "store-c", "write_enabled": True})
    registry_path.write_bytes(canonical_json_bytes(registry))
    with pytest.raises(ValueError, match="evidence file"):
        load_and_verify_continuity_state(root)


def test_durable_artifact_legacy_fingerprint_mismatch_rejects(tmp_path):
    root = write_durable_artifact_tree(tmp_path)
    record_path = root / "docs/artifacts/candidate1-real-input-v0.json"
    record = json.loads(record_path.read_bytes())
    record["legacy_bindings"]["legacy_input_manifest_fingerprint"] = "f" * 64
    data = canonical_json_bytes(record)
    record_path.write_bytes(data)
    receipt_path = root / TASK_DIR / "handoff_v002.json"
    receipt = json.loads(receipt_path.read_bytes())
    next(item for item in receipt["evidence"] if item["path"] == "docs/artifacts/candidate1-real-input-v0.json")["sha256"] = hashlib.sha256(data).hexdigest()
    receipt_data = canonical_json_bytes(receipt)
    receipt_path.write_bytes(receipt_data)
    active_path = root / "docs/control/active_task.json"
    active = json.loads(active_path.read_bytes())
    active["handoff_receipt_sha256"] = hashlib.sha256(receipt_data).hexdigest()
    active_path.write_bytes(canonical_json_bytes(active))
    with pytest.raises(ValueError, match="legacy fingerprint"):
        load_and_verify_continuity_state(root)


def test_durable_artifact_availability_and_copy_count_mismatch_rejects(tmp_path):
    root = write_durable_artifact_tree(tmp_path, verified=True)
    receipt_path = root / TASK_DIR / "handoff_v002.json"
    receipt = json.loads(receipt_path.read_bytes())
    receipt["required_artifacts"][0].update(availability="UNAVAILABLE", verified_copy_count=0, canonical_paths=[])
    receipt_data = canonical_json_bytes(receipt)
    receipt_path.write_bytes(receipt_data)
    active_path = root / "docs/control/active_task.json"
    active = json.loads(active_path.read_bytes())
    active["handoff_receipt_sha256"] = hashlib.sha256(receipt_data).hexdigest()
    active_path.write_bytes(canonical_json_bytes(active))
    with pytest.raises(ValueError, match="availability"):
        load_and_verify_continuity_state(root)


def test_durable_unavailable_state_keeps_execution_blocked(tmp_path):
    state = load_and_verify_continuity_state(write_durable_artifact_tree(tmp_path))
    assert "PROTOCOL_EXECUTION=BLOCKED" in render_context_packet(state)


def _sandbox_fixture(tmp_path):
    for relpath in (
        "CLAUDE.md", "AGENTS.md", "docs/agent/START_HERE.md",
        "docs/control/active_task.json",
        f"{TASK_DIR}/handoff_v001.json", f"{TASK_DIR}/handoff_v002.json",
        f"{TASK_DIR}/handoff_v003.json", "docs/artifacts/stores.json",
        "docs/artifacts/candidate1-real-input-v0.json",
        "docs/artifacts/README.md", ".github/workflows/qnty-artifacts.yml",
        "docs/control/amendments/candidate1_v1_synthetic_sandbox_v001.json",
        "quantbot/continuity/context.py", "tests/continuity/test_cross_agent_continuity.py",
        "quantbot/artifacts/__init__.py", "quantbot/artifacts/__main__.py",
        "quantbot/artifacts/manifest.py", "quantbot/artifacts/registry.py", "quantbot/artifacts/store.py",
        "tests/artifacts/test_manifest.py", "tests/artifacts/test_registry.py", "tests/artifacts/test_store.py",
    ):
        target = tmp_path / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relpath, target)
    return tmp_path


def _rewrite_receipt(root, mutate):
    path = root / TASK_DIR / "handoff_v003.json"
    receipt = json.loads(path.read_bytes())
    mutate(receipt)
    data = canonical_json_bytes(receipt)
    path.write_bytes(data)
    active_path = root / "docs/control/active_task.json"
    active = json.loads(active_path.read_bytes())
    active["handoff_receipt_sha256"] = hashlib.sha256(data).hexdigest()
    active_path.write_bytes(canonical_json_bytes(active))


def test_valid_v003_amendment_chain_and_boundary_rendering():
    state = load_and_verify_continuity_state(ROOT)
    assert state["handoff_receipt"]["receipt_index"] == 3
    assert state["sandbox_amendment"]["sandbox_id"] == "candidate1-v1-synthetic-design-sandbox-v0"
    packet = render_context_packet(state)
    assert "SYNTHETIC_SANDBOX id=candidate1-v1-synthetic-design-sandbox-v0 status=AUTHORIZED_EXPLORATORY_ENGINEERING_ONLY execution_budget=0" in packet
    assert "SYNTHETIC_SANDBOX_REAL_DATA=FORBIDDEN" in packet
    assert "SYNTHETIC_SANDBOX_SCIENTIFIC_EVIDENCE=FALSE" in packet
    assert "DURABLE_STORE_GATE=REQUIRED_FOR_REAL_ARTIFACT_OPERATIONS" in packet
    assert "V0_DISPOSITION=UNCHANGED" in packet
    assert "official V1 protocol" not in packet
    assert "V1 artifact" not in packet


@pytest.mark.parametrize("mutation", [
    lambda a: a.pop("amendment_id"),
    lambda a: a.update(amendment_id="wrong"),
    lambda a: a.update(sandbox_id="wrong"),
    lambda a: a.update(sandbox_status="wrong"),
    lambda a: a.update(unexpected=True),
    lambda a: a["allowed_actions"].append("DRIFT"),
    lambda a: a["non_effects"].append("DRIFT"),
    lambda a: a["prohibited_actions"].append("DRIFT"),
    lambda a: a["transition_gates"].update(extra=True),
    lambda a: a["transition_gates"].update(sandbox_execution_budget=1),
    lambda a: a["transition_gates"].update(sandbox_outputs_are_scientific_evidence=True),
    lambda a: a["transition_gates"].update(v0_disposition_unchanged=False),
])
def test_amendment_drift_fails_closed(tmp_path, mutation):
    root = _sandbox_fixture(tmp_path)
    amendment_path = root / context.AMENDMENT_RELPATH
    amendment = json.loads(amendment_path.read_bytes())
    mutation(amendment)
    amendment_path.write_bytes(canonical_json_bytes(amendment))
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(root)


def test_amendment_missing_noncanonical_or_unpinned_fails(tmp_path):
    root = _sandbox_fixture(tmp_path)
    amendment_path = root / context.AMENDMENT_RELPATH
    amendment_path.unlink()
    with pytest.raises(ValueError, match="missing"):
        load_and_verify_continuity_state(root)
    root = _sandbox_fixture(tmp_path / "noncanonical")
    amendment_path = root / context.AMENDMENT_RELPATH
    amendment_path.write_text(json.dumps(json.loads(amendment_path.read_bytes()), indent=2), encoding="utf-8")
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(root)
    root = _sandbox_fixture(tmp_path / "unpinned")
    _rewrite_receipt(root, lambda r: r["evidence"].__setitem__(
        slice(None), [item for item in r["evidence"] if item["path"] != context.AMENDMENT_RELPATH]
    ))
    with pytest.raises(ValueError, match="amendment hash"):
        load_and_verify_continuity_state(root)


@pytest.mark.parametrize("mutation", [
    lambda r: r["next_actions"].__setitem__(0, "CONFIGURE_TWO_DURABLE_ARTIFACT_STORES"),
    lambda r: r["prohibited_actions"].remove("RECOVER_OR_RETIRE_V0_BEFORE_DURABLE_ARTIFACT_PLANE"),
    lambda r: r["prohibited_actions"].remove("EXECUTE_CANDIDATE1_PROTOCOL"),
    lambda r: r["prohibited_actions"].remove("ACCESS_REAL_DATA_IN_SYNTHETIC_SANDBOX"),
    lambda r: r["required_artifacts"].append({"artifact_id": "candidate1-v1", "availability": "UNAVAILABLE", "canonical_paths": [], "expected_manifest_sha256": "0" * 64, "verified_copy_count": 0}),
    lambda r: r["required_artifacts"][0].update(availability="VERIFIED_AVAILABLE", verified_copy_count=2, canonical_paths=["/a", "/b"]),
    lambda r: r["safety_state"].update(decomposition_execution_count=1),
    lambda r: r["safety_state"].update(scientific_use_authorized=True),
])
def test_sandbox_handoff_cannot_weaken_existing_invariants(tmp_path, mutation):
    root = _sandbox_fixture(tmp_path)
    _rewrite_receipt(root, mutation)
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(root)
