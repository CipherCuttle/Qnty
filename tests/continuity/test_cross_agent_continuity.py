"""Synthetic fail-closed tests for the cross-agent continuity control plane.

No real data, no protocol execution: every tree is built from scratch in
tmp_path, plus read-only validation of the committed production control state.
"""

import ast
import copy
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
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


def copy_repo_without_runtime(source, destination):
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns(
            ".git", ".venv", ".pytest_cache", "__pycache__", "*.pyc", "tmp", "output", "data", "experiment_results"
        ),
    )
    assert not (destination / ".git").exists()
    assert not (destination / ".venv").exists()


def restore_historical_h001_inputs(destination):
    destination = Path(destination)
    design_path = destination / "docs/experiments/candidate1_h001_real_data_falsification_v0.json"
    design = json.loads(design_path.read_bytes())
    design["temporal_join_contract"]["prior_funding"] = "latest funding_time_utc <= bar[t].open_time_utc"
    design_bytes = canonical_json_bytes(design)
    assert hashlib.sha256(design_bytes).hexdigest() == "055ea162a11d4042320daeb74e153ebbd27969dd29a60c226cb84a8fc38b8900"
    design_path.write_bytes(design_bytes)

    validator_path = destination / "quantbot/experiment/h001_real_falsification_preregistration.py"
    validator = validator_path.read_bytes()
    activated_design_sha = b"c6fb8d796559c53188c10e729a2257bc593c7a80526963c97515f747820e2276"
    historical_design_sha = b"055ea162a11d4042320daeb74e153ebbd27969dd29a60c226cb84a8fc38b8900"
    strict_rule = b"latest funding_time_utc < bar[t].open_time_utc"
    historical_rule = b"latest funding_time_utc <= bar[t].open_time_utc"
    assert validator.count(activated_design_sha) == 1
    assert validator.count(strict_rule) == 1
    validator = validator.replace(activated_design_sha, historical_design_sha, 1).replace(strict_rule, historical_rule, 1)
    assert hashlib.sha256(validator).hexdigest() == "888bc4663e3d7fb9b398f944bf2b67553e8959e0173be77183ca8b288156172a"
    validator_path.write_bytes(validator)

    preregistration_path = destination / "tests/experiment/test_h001_real_falsification_preregistration.py"
    preregistration = preregistration_path.read_text(encoding="utf-8")
    activation_marker = "\n\nTEMPORAL_CANDIDATE = ROOT / "
    assert preregistration.count(activation_marker) == 1
    preregistration = preregistration[:preregistration.index(activation_marker)]
    assert preregistration.count("import hashlib\n") == 1
    preregistration = preregistration.replace("import hashlib\n", "", 1)
    historical_preregistration = preregistration.encode("utf-8")
    assert hashlib.sha256(historical_preregistration).hexdigest() == "4cf6478701f70ab7ecee4f5d84b39b042344daeb928da38d59c0389a2a8ca7c6"
    preregistration_path.write_bytes(historical_preregistration)

    temporal_test_path = destination / "tests/experiment/test_h001_temporal_causality.py"
    if not temporal_test_path.is_file():
        temporal_test_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "tests/experiment/test_h001_temporal_causality.py", temporal_test_path)
    temporal_test = temporal_test_path.read_text(encoding="utf-8")
    inverse_replacements = [
        (
            'HISTORICAL_SHA = "055ea162a11d4042320daeb74e153ebbd27969dd29a60c226cb84a8fc38b8900"\nCURRENT_SHA = "c6fb8d796559c53188c10e729a2257bc593c7a80526963c97515f747820e2276"',
            'CURRENT_SHA = "055ea162a11d4042320daeb74e153ebbd27969dd29a60c226cb84a8fc38b8900"',
        ),
        (
            'VALIDATOR_SHA = "d9326c7b73c68f3958901899f46ef11a4f529ed1954f268de06ae6e8abdcede3"',
            'VALIDATOR_SHA = "888bc4663e3d7fb9b398f944bf2b67553e8959e0173be77183ca8b288156172a"',
        ),
        ('    assert CURRENT.read_bytes() == CANDIDATE.read_bytes()\n', ''),
        (
            '    assert current["temporal_join_contract"]["prior_funding"] == "latest funding_time_utc < bar[t].open_time_utc"\n'
            '    assert current["temporal_join_contract"]["funding_cashflow_events"] == "bar[t].open_time_utc < funding_time_utc <= bar[t].close_time_utc"\n'
            '    historical = json.loads(CURRENT.read_bytes())\n'
            '    historical["temporal_join_contract"]["prior_funding"] = "latest funding_time_utc <= bar[t].open_time_utc"\n'
            '    historical_bytes = json.dumps(historical, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()\n'
            '    assert hashlib.sha256(historical_bytes).hexdigest() == HISTORICAL_SHA\n',
            '',
        ),
        ('    walk(historical, current)\n', '    walk(current, candidate)\n'),
    ]
    for old, new in inverse_replacements:
        assert temporal_test.count(old) == 1
        temporal_test = temporal_test.replace(old, new, 1)
    historical_test = temporal_test.encode("utf-8")
    assert hashlib.sha256(historical_test).hexdigest() == "0e1dea2e1ec06cea14f11455402282c56dd5ef598ed54b3ad401774d4d7ea628"
    temporal_test_path.write_bytes(historical_test)


def test_historical_restoration_is_deterministic_without_git(tmp_path, monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("historical restoration must not invoke Git")

    monkeypatch.setattr(subprocess, "check_output", fail_if_called)
    for relative_path in (
        "docs/experiments/candidate1_h001_real_data_falsification_v0.json",
        "quantbot/experiment/h001_real_falsification_preregistration.py",
        "tests/experiment/test_h001_temporal_causality.py",
        "tests/experiment/test_h001_real_falsification_preregistration.py",
    ):
        source = ROOT / relative_path
        target = tmp_path / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    restore_historical_h001_inputs(tmp_path)
    assert hashlib.sha256((tmp_path / "docs/experiments/candidate1_h001_real_data_falsification_v0.json").read_bytes()).hexdigest() == "055ea162a11d4042320daeb74e153ebbd27969dd29a60c226cb84a8fc38b8900"
    assert hashlib.sha256((tmp_path / "quantbot/experiment/h001_real_falsification_preregistration.py").read_bytes()).hexdigest() == "888bc4663e3d7fb9b398f944bf2b67553e8959e0173be77183ca8b288156172a"
    assert hashlib.sha256((tmp_path / "tests/experiment/test_h001_temporal_causality.py").read_bytes()).hexdigest() == "0e1dea2e1ec06cea14f11455402282c56dd5ef598ed54b3ad401774d4d7ea628"
    assert hashlib.sha256((tmp_path / "tests/experiment/test_h001_real_falsification_preregistration.py").read_bytes()).hexdigest() == "4cf6478701f70ab7ecee4f5d84b39b042344daeb928da38d59c0389a2a8ca7c6"


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
        "next_actions": ["CONFIGURE_TWO_DURABLE_ARTIFACT_STORES"],
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
    phase="durable_artifact_store_configuration",
):
    (root / TASK_DIR).mkdir(parents=True, exist_ok=True)
    (root / "docs/agent").mkdir(parents=True, exist_ok=True)
    (root / "docs/evidence.txt").write_bytes(EVIDENCE_BYTES)
    for name, extra in extra_receipts:
        (root / TASK_DIR / name).write_bytes(canonical_json_bytes(extra))
    receipt_bytes = canonical_json_bytes(receipt)
    (root / TASK_DIR / receipt_name).write_bytes(receipt_bytes)
    if (
        phase == "durable_artifact_store_configuration"
        and not (root / "docs/artifacts").exists()
        and "evidence" in receipt
        and receipt.get("required_artifacts")
    ):
        verified = receipt["required_artifacts"][0]["availability"] == "VERIFIED_AVAILABLE"
        first, active_receipt, record, registry = durable_artifact_receipt_and_record(verified=verified)
        del first
        del active_receipt
        artifacts = root / "docs/artifacts"
        artifacts.mkdir(parents=True)
        record_bytes = canonical_json_bytes(record)
        (artifacts / "candidate1-real-input-v0.json").write_bytes(record_bytes)
        registry_bytes = canonical_json_bytes(registry)
        (artifacts / "stores.json").write_bytes(registry_bytes)
        receipt["evidence"].extend([
            {"path": "docs/artifacts/candidate1-real-input-v0.json", "sha256": hashlib.sha256(record_bytes).hexdigest()},
            {"path": "docs/artifacts/stores.json", "sha256": hashlib.sha256(registry_bytes).hexdigest()},
        ])
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
    assert "NEXT_ACTION=CONFIGURE_TWO_DURABLE_ARTIFACT_STORES" in packet
    assert "PROTOCOL_EXECUTION=BLOCKED" in packet
    assert f"artifact_not_verified_available:{context.REQUIRED_ARTIFACT_ID}" in packet


def test_production_control_state_verifies():
    state = load_and_verify_continuity_state(ROOT)
    receipt = state["handoff_receipt"]
    assert receipt["safety_state"]["decomposition_execution_count"] == 0
    assert receipt["next_actions"] in (["IMPLEMENT_DURABLE_ARTIFACT_PLANE"], ["CONFIGURE_TWO_DURABLE_ARTIFACT_STORES"], ["IMPLEMENT_CANDIDATE1_V1_SYNTHETIC_SANDBOX_SCAFFOLD"], ["RUN_CANDIDATE1_V1_SYNTHETIC_STRATEGY_BATCH"], [context._H001_COMPLETE_NEXT_ACTION], [context._H001_DESIGN_NEXT_ACTION], [context._H001_PREREGISTERED_NEXT_ACTION], [context._H001_REVIEW_COMPLETE_NEXT_ACTION], [context._H001_PRE_DATA_NEXT_ACTION], [context._H001_SCAFFOLD_NEXT_ACTION], [context._H001_ASSURANCE_REVIEW_NEXT_ACTION], [context._H001_TEMPORAL_CANDIDATE_NEXT_ACTION], [context._H001_TEMPORAL_REVIEW_COMPLETE_NEXT_ACTION], [context._H001_TEMPORAL_ACTIVE_NEXT_ACTION], [context._H001_CALIBRATION_GOVERNANCE_NEXT_ACTION], [context._H001_CALIBRATION_CANDIDATE_NEXT_ACTION])
    packet = render_context_packet(state)
    assert "PROTOCOL_EXECUTION=BLOCKED" in packet
    assert "availability=UNAVAILABLE" in packet
    assert state["active_task"]["phase"] in (context._H001_COMPLETE_PHASE, context._H001_DESIGN_PHASE, context._H001_PREREGISTERED_PHASE, context._H001_REVIEW_COMPLETE_PHASE, context._H001_PRE_DATA_PHASE, context._H001_SCAFFOLD_PHASE, context._H001_ASSURANCE_REVIEW_COMPLETE_PHASE, context._H001_TEMPORAL_CANDIDATE_PHASE, context._H001_TEMPORAL_REVIEW_COMPLETE_PHASE, context._H001_TEMPORAL_ACTIVE_PHASE, context._H001_CALIBRATION_GOVERNANCE_PHASE, context._H001_CALIBRATION_CANDIDATE_PHASE)


def test_h001_completion_phase_verifies_and_renders_boundaries():
    state = load_and_verify_continuity_state(ROOT)
    if state["active_task"]["phase"] in (context._H001_DESIGN_PHASE, context._H001_PREREGISTERED_PHASE, context._H001_REVIEW_COMPLETE_PHASE, context._H001_PRE_DATA_PHASE, context._H001_SCAFFOLD_PHASE, context._H001_ASSURANCE_REVIEW_COMPLETE_PHASE, context._H001_TEMPORAL_CANDIDATE_PHASE, context._H001_TEMPORAL_REVIEW_COMPLETE_PHASE, context._H001_TEMPORAL_ACTIVE_PHASE, context._H001_CALIBRATION_GOVERNANCE_PHASE, context._H001_CALIBRATION_CANDIDATE_PHASE):
        pytest.skip("production tree has advanced past synthetic completion")
    assert state["active_task"]["phase"] == context._H001_COMPLETE_PHASE
    assert state["handoff_receipt"]["next_actions"] == [context._H001_COMPLETE_NEXT_ACTION]
    packet = render_context_packet(state)
    for line in (
        "H001_SYNTHETIC_STATUS=FALSIFICATION_COMPLETE_MECHANICAL_ONLY",
        "H001_BATCH_002_RECEIPT_SHA256=" + context._H001_BATCH_RECEIPT_SHA256,
        "H001_SYNTHETIC_FALSIFICATION_CONDITIONS=15/15_PASS",
        "H001_VARIANT_SELECTION=NONE",
        "H001_SCIENTIFIC_EVIDENCE=FALSE",
        "H001_REAL_FALSIFICATION_GOVERNANCE=NOT_YET_AUTHORIZED",
        "H001_REAL_DATA_ACCESS=FORBIDDEN",
        "H001_EXECUTION_AUTHORIZED=FALSE",
        "H001_PRIMARY_EXECUTION_COUNT=0",
        "H001_DURABLE_STORES_CONFIGURED=FALSE",
        "EDGE_STATUS=EDGE_UNPROVEN",
        "LIVE_STATUS=BLOCK_LIVE_INTEGRATION",
    ):
        assert line in packet


def test_h001_design_governance_phase_verifies_and_renders_boundaries():
    state = load_and_verify_continuity_state(ROOT)
    if state["active_task"]["phase"] != context._H001_DESIGN_PHASE:
        pytest.skip("production tree is before the H001 design-governance transition")
    assert state["handoff_receipt"]["next_actions"] == [context._H001_DESIGN_NEXT_ACTION]
    amendment = state["h001_design_amendment"]
    assert amendment["authorization_status"] == "AUTHORIZED_PREREGISTRATION_DESIGN_ONLY"
    assert amendment["predecessor_amendment"]["sha256"] == context._SYNTHETIC_AMENDMENT_SHA256
    packet = render_context_packet(state)
    for line in (
        "H001_REAL_FALSIFICATION_GOVERNANCE=AUTHORIZED_PREREGISTRATION_DESIGN_ONLY",
        "H001_PREREGISTRATION_DESIGN=ALLOWED",
        "H001_REAL_DATA_ACCESS=FORBIDDEN",
        "H001_REAL_DATA_EXECUTION=FORBIDDEN",
        "H001_PRIMARY_EXECUTION_BUDGET=0",
        "H001_PRIMARY_EXECUTION_COUNT=0",
        "H001_REQUIRED_DURABLE_COPIES=2",
        "H001_DURABLE_STORES_CONFIGURED=FALSE",
        "H001_SCIENTIFIC_AUTHORIZATION=FALSE",
        "H001_PAPER_TRADE_AUTHORIZATION=FALSE",
        "H001_LIVE_AUTHORIZATION=FALSE",
        "V0_AVAILABILITY=UNAVAILABLE",
        "EDGE_STATUS=EDGE_UNPROVEN",
        "LIVE_STATUS=BLOCK_LIVE_INTEGRATION",
    ):
        assert line in packet


def test_h001_preregistered_design_phase_renders_review_only_boundaries():
    state = load_and_verify_continuity_state(ROOT)
    if state["active_task"]["phase"] != context._H001_PREREGISTERED_PHASE:
        pytest.skip("production tree has not reached the preregistered design-only phase")
    assert state["handoff_receipt"]["next_actions"] == [context._H001_PREREGISTERED_NEXT_ACTION]
    packet = render_context_packet(state)
    for line in (
        "H001_REAL_FALSIFICATION_PROTOCOL=PREREGISTERED_DESIGN_ONLY",
        "H001_PROTOCOL_ID=real_btc_h001_funding_crowding_reversal_falsification_v0",
        "H001_DATA_IDENTITY=UNBOUND_DESIGN_ONLY",
        "H001_REAL_DATA_ACCESS=FORBIDDEN",
        "H001_ARTIFACT_OPERATIONS=FORBIDDEN",
        "H001_VALIDATION_EXECUTION_AUTHORIZED=FALSE",
        "H001_HOLDOUT_EXECUTION_AUTHORIZED=FALSE",
        "H001_CURRENT_EXECUTION_BUDGET=0",
        "H001_CURRENT_EXECUTION_COUNT=0",
        "H001_CANDIDATE_TRIAL_COUNT=9",
        "H001_REQUIRED_DURABLE_COPIES=2",
        "H001_DURABLE_STORES_CONFIGURED=FALSE",
        "H001_SCIENTIFIC_AUTHORIZATION=FALSE",
        "H001_PAPER_TRADE_AUTHORIZATION=FALSE",
        "H001_LIVE_AUTHORIZATION=FALSE",
        "EDGE_STATUS=EDGE_UNPROVEN",
        "LIVE_STATUS=BLOCK_LIVE_INTEGRATION",
    ):
        assert line in packet


def test_sandbox_ready_phase_still_requires_synthetic_batch_action(tmp_path):
    root = tmp_path / "repo"
    copy_repo_without_runtime(ROOT, root)
    active_path = root / "docs/control/active_task.json"
    active = json.loads(active_path.read_bytes())
    receipt_path = root / TASK_DIR / "handoff_v008.json"
    receipt = json.loads(receipt_path.read_bytes())
    for item in receipt["evidence"]:
        evidence_path = root / item["path"]
        if evidence_path.is_file():
            item["sha256"] = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    receipt_path.write_bytes(canonical_json_bytes(receipt))
    active.update(
        phase="candidate1_v1_synthetic_sandbox_ready",
        handoff_receipt_path=f"{TASK_DIR}/handoff_v008.json",
        handoff_receipt_sha256=hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
    )
    active_path.write_bytes(canonical_json_bytes(active))
    state = load_and_verify_continuity_state(root)
    assert state["handoff_receipt"]["next_actions"] == ["RUN_CANDIDATE1_V1_SYNTHETIC_STRATEGY_BATCH"]


@pytest.mark.parametrize("mutation", [
    lambda r: r["decisions"].remove(f"H001_BATCH_002_RECEIPT_SHA256={context._H001_BATCH_RECEIPT_SHA256}"),
    lambda r: r["decisions"].remove("H001_BATCH_002_STATUS=COMPLETED_MECHANICAL_ONLY"),
    lambda r: r["decisions"].remove("H001_SCIENTIFIC_EVIDENCE=FALSE"),
    lambda r: r["decisions"].remove("H001_VARIANT_SELECTION=NONE"),
    lambda r: r["decisions"].remove("H001_SYNTHETIC_FALSIFICATION_CONDITIONS=15/15_PASS"),
    lambda r: r.update(next_actions=["RUN_CANDIDATE1_V1_SYNTHETIC_STRATEGY_BATCH"]),
    lambda r: r["required_artifacts"][0].update(availability="VERIFIED_AVAILABLE", verified_copy_count=2, canonical_paths=["qnty-artifact://a", "qnty-artifact://b"]),
    lambda r: r["safety_state"].update(real_data_execution_requested=True),
    lambda r: r["safety_state"].update(decomposition_execution_count=1),
    lambda r: r["safety_state"].update(scientific_use_authorized=True),
    lambda r: r["safety_state"].update(paper_trade_authorized=True),
    lambda r: r["safety_state"].update(live_integration_authorized=True),
    lambda r: r["prohibited_actions"].remove("CREATE_OFFICIAL_V1_PROTOCOL_FROM_SANDBOX"),
])
def test_h001_completion_phase_drift_fails_closed(tmp_path, mutation):
    root = tmp_path / "repo"
    copy_repo_without_runtime(ROOT, root)
    receipt_path = root / TASK_DIR / "handoff_v009.json"
    receipt = json.loads(receipt_path.read_bytes())
    mutation(receipt)
    receipt_bytes = canonical_json_bytes(receipt)
    receipt_path.write_bytes(receipt_bytes)
    active_path = root / "docs/control/active_task.json"
    active = json.loads(active_path.read_bytes())
    active["handoff_receipt_sha256"] = hashlib.sha256(receipt_bytes).hexdigest()
    active_path.write_bytes(canonical_json_bytes(active))
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(root)


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
            canonical_paths=["qnty-artifact://store-a/sha256/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "qnty-artifact://store-b/sha256/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"],
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
    allowed = {"__future__", "hashlib", "json", "pathlib", "re", "quantbot.assurance", "quantbot.artifacts.registry"}
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
    for receipt_name in ("handoff_v002.json", "handoff_v003.json"):
        receipt_path = tmp_path / TASK_DIR / receipt_name
        receipt = json.loads(receipt_path.read_bytes())
        for item in receipt["evidence"]:
            evidence_path = tmp_path / item["path"]
            if evidence_path.is_file():
                item["sha256"] = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
        receipt_path.write_bytes(canonical_json_bytes(receipt))
    v003_path = tmp_path / TASK_DIR / "handoff_v003.json"
    v003 = json.loads(v003_path.read_bytes())
    v003["predecessor"]["sha256"] = hashlib.sha256(
        (tmp_path / TASK_DIR / "handoff_v002.json").read_bytes()
    ).hexdigest()
    v003_path.write_bytes(canonical_json_bytes(v003))
    active_path = tmp_path / "docs/control/active_task.json"
    active = json.loads(active_path.read_bytes())
    active["phase"] = "candidate1_v1_synthetic_sandbox_governance"
    active["handoff_receipt_path"] = f"{TASK_DIR}/handoff_v003.json"
    active["handoff_receipt_sha256"] = hashlib.sha256(v003_path.read_bytes()).hexdigest()
    active_path.write_bytes(canonical_json_bytes(active))
    return tmp_path


def _rewrite_receipt(root, mutate, receipt_name="handoff_v003.json"):
    path = root / TASK_DIR / receipt_name
    receipt = json.loads(path.read_bytes())
    mutate(receipt)
    data = canonical_json_bytes(receipt)
    path.write_bytes(data)
    active_path = root / "docs/control/active_task.json"
    active = json.loads(active_path.read_bytes())
    active["handoff_receipt_sha256"] = hashlib.sha256(data).hexdigest()
    active_path.write_bytes(canonical_json_bytes(active))


def _rewrite_active_phase_only(root, phase):
    active_path = root / "docs/control/active_task.json"
    active = json.loads(active_path.read_bytes())
    receipt_sha = active["handoff_receipt_sha256"]
    active["phase"] = phase
    active_path.write_bytes(canonical_json_bytes(active))
    assert json.loads(active_path.read_bytes())["handoff_receipt_sha256"] == receipt_sha


@pytest.mark.parametrize("phase", [
    "unknown_phase",
    "candidate1_v1_synthetic_sandbox_governanc",
    "frozen_input_recovery_design",
])
def test_unsupported_phase_dispatch_fails_closed(tmp_path, phase):
    root = _sandbox_fixture(tmp_path)
    _rewrite_active_phase_only(root, phase)
    with pytest.raises(ValueError, match="unsupported active phase"):
        load_and_verify_continuity_state(root)


def test_empty_phase_dispatch_fails_closed(tmp_path):
    root = _sandbox_fixture(tmp_path)
    _rewrite_active_phase_only(root, "")
    with pytest.raises(ValueError, match="active_task phase"):
        load_and_verify_continuity_state(root)


def test_durable_phase_cannot_activate_sandbox_v003(tmp_path):
    root = _sandbox_fixture(tmp_path)
    _rewrite_active_phase_only(root, "durable_artifact_store_configuration")
    with pytest.raises(ValueError, match="durable phase next action"):
        load_and_verify_continuity_state(root)


def test_sandbox_phase_cannot_activate_durable_v002(tmp_path):
    root = _sandbox_fixture(tmp_path)
    active_path = root / "docs/control/active_task.json"
    active = json.loads(active_path.read_bytes())
    receipt_path = root / TASK_DIR / "handoff_v002.json"
    active["handoff_receipt_path"] = f"{TASK_DIR}/handoff_v002.json"
    active["handoff_receipt_sha256"] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    active_path.write_bytes(canonical_json_bytes(active))
    with pytest.raises(ValueError, match="sandbox amendment"):
        load_and_verify_continuity_state(root)


def test_sandbox_phase_rejects_durable_next_action(tmp_path):
    root = _sandbox_fixture(tmp_path)
    _rewrite_receipt(root, lambda receipt: receipt.update(next_actions=["CONFIGURE_TWO_DURABLE_ARTIFACT_STORES"]))
    with pytest.raises(ValueError, match="sandbox phase next action"):
        load_and_verify_continuity_state(root)


def test_durable_phase_rejects_sandbox_next_action(tmp_path):
    root = write_durable_artifact_tree(tmp_path)
    _rewrite_receipt(root, lambda receipt: receipt.update(next_actions=[context._SANDBOX_NEXT_ACTION]), "handoff_v002.json")
    with pytest.raises(ValueError, match="durable phase next action"):
        load_and_verify_continuity_state(root)


def test_durable_phase_v002_contract_passes(tmp_path):
    state = load_and_verify_continuity_state(write_durable_artifact_tree(tmp_path))
    assert state["active_task"]["phase"] == "durable_artifact_store_configuration"
    assert "sandbox_amendment" not in state


def test_sandbox_phase_v003_contract_passes_and_renders_boundary(tmp_path):
    root = _sandbox_fixture(tmp_path)
    state = load_and_verify_continuity_state(root)
    assert "sandbox_amendment" in state
    assert "SYNTHETIC_SANDBOX_REAL_DATA=FORBIDDEN" in render_context_packet(state)


def test_valid_v003_amendment_chain_and_boundary_rendering():
    state = load_and_verify_continuity_state(ROOT)
    assert state["handoff_receipt"]["receipt_index"] >= 4
    _design_family = (context._H001_DESIGN_PHASE, context._H001_PREREGISTERED_PHASE, context._H001_REVIEW_COMPLETE_PHASE, context._H001_ASSURANCE_REVIEW_COMPLETE_PHASE)
    if state["active_task"]["phase"] == context._H001_ASSURANCE_REVIEW_COMPLETE_PHASE:
        assert "H001_PRE_DATA_ASSURANCE_SCAFFOLD_REVIEW=COMPLETED_PASSED" in render_context_packet(state)
        return
    if state["active_task"]["phase"] == context._H001_PRE_DATA_PHASE:
        assert state["h001_pre_data_amendment"]["amendment_id"] == "candidate1-h001-pre-data-assurance-v001"
        packet = render_context_packet(state)
        assert "H001_PRE_DATA_ASSURANCE_GOVERNANCE=AUTHORIZED_SCAFFOLD_ONLY" in packet
        assert "H001_REAL_DATA_ACCESS=FORBIDDEN" in packet
        return
    if state["active_task"]["phase"] == context._H001_SCAFFOLD_PHASE:
        assert state["h001_pre_data_amendment"]["amendment_id"] == "candidate1-h001-pre-data-assurance-v001"
        packet = render_context_packet(state)
        assert "H001_REAL_DATA_ACCESS=FORBIDDEN" in packet
        return
    if state["active_task"]["phase"] in (context._H001_TEMPORAL_ACTIVE_PHASE, context._H001_CALIBRATION_GOVERNANCE_PHASE, context._H001_CALIBRATION_CANDIDATE_PHASE):
        return
    if state["active_task"]["phase"] in (context._H001_TEMPORAL_CANDIDATE_PHASE, context._H001_TEMPORAL_REVIEW_COMPLETE_PHASE):
        if state["active_task"]["phase"] == context._H001_TEMPORAL_REVIEW_COMPLETE_PHASE:
            assert "H001_TEMPORAL_CAUSALITY_CANDIDATE_REVIEW=COMPLETED_PASSED" in render_context_packet(state)
            return
        packet = render_context_packet(state)
        assert "H001_TEMPORAL_CAUSALITY_AMENDMENT_CANDIDATE=IMPLEMENTED_FOR_REVIEW" in packet
        assert "H001_TEMPORAL_CAUSALITY_AMENDMENT_EFFECTIVE=FALSE" in packet
        return
    if state["active_task"]["phase"] in _design_family:
        assert state["h001_design_amendment"]["amendment_id"] == "candidate1-h001-real-falsification-design-v001"
    else:
        assert state["sandbox_amendment"]["sandbox_id"] == "candidate1-v1-synthetic-design-sandbox-v0"
    packet = render_context_packet(state)
    if state["active_task"]["phase"] == context._H001_DESIGN_PHASE:
        assert "H001_REAL_FALSIFICATION_GOVERNANCE=AUTHORIZED_PREREGISTRATION_DESIGN_ONLY" in packet
    elif state["active_task"]["phase"] == context._H001_PREREGISTERED_PHASE:
        assert "H001_REAL_FALSIFICATION_PROTOCOL=PREREGISTERED_DESIGN_ONLY" in packet
    elif state["active_task"]["phase"] == context._H001_REVIEW_COMPLETE_PHASE:
        assert "H001_PREREGISTRATION_REVIEW_STATUS=PASSED" in packet
    else:
        assert "H001_SYNTHETIC_STATUS=FALSIFICATION_COMPLETE_MECHANICAL_ONLY" in packet
    assert "H001_REAL_DATA_ACCESS=FORBIDDEN" in packet
    if state["active_task"]["phase"] in _design_family:
        assert "H001_SCIENTIFIC_AUTHORIZATION=FALSE" in packet
        assert "H001_REQUIRED_DURABLE_COPIES=2" in packet
        assert "V0_AVAILABILITY=UNAVAILABLE" in packet
    else:
        assert "H001_SCIENTIFIC_EVIDENCE=FALSE" in packet
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


# --------------------------------------------------------------------------
# H001 preregistration review-completion (phase v012)
# --------------------------------------------------------------------------

_REVIEW_COMPLETE_FILES = (
    "CLAUDE.md", "AGENTS.md", "docs/agent/START_HERE.md",
    "docs/control/active_task.json",
    "docs/control/amendments/candidate1_v1_synthetic_sandbox_v001.json",
    "docs/control/amendments/candidate1_h001_real_falsification_design_v001.json",
    "docs/artifacts/stores.json",
    "docs/artifacts/candidate1-real-input-v0.json",
    "docs/experiments/candidate1_h001_real_data_falsification_v0.json",
    "quantbot/experiment/h001_real_falsification_preregistration.py",
    "tests/experiment/test_h001_real_falsification_preregistration.py",
) + tuple(f"{TASK_DIR}/handoff_v{idx:03d}.json" for idx in range(1, 13))

_REVIEW_COMPLETE_ACTIVE_TASK = {
    "control_kind": "qnty_active_task_pointer",
    "handoff_receipt_path": f"{TASK_DIR}/handoff_v012.json",
    "handoff_receipt_sha256": "260414954f579b7b1d6c56f1c2d68dbf5796017292630c6a3b36a28c9340c326",
    "phase": context._H001_REVIEW_COMPLETE_PHASE,
    "protocol_id": PROTOCOL_ID,
    "schema_version": "0.1.0",
    "task_id": TASK_ID,
}

_EXPECTED_PRE_V013_SHA256 = {
    **{f"{TASK_DIR}/handoff_v{idx:03d}.json": sha for idx, sha in enumerate((
        "97de4e8b17eb76546b6af451c62a739b035c510c1957717201117fcb95c99998",
        "12eb5ee0a364af025414c2ef430bee44611e91010a34684ec2ebb6ca8e033640",
        "8dd9e03f6783afc6cd2a9a223aa7f4e2564d6047c023fecc76f8db22eacf0361",
        "6d01c548bceb069d7f056bc97071d21a4be9ffa8142e5084141ffde44a0c4560",
        "dc8f92ce481b1680e451bc5583af7fb0ff51fbad4f55f7c866d4c19221b133ad",
        "21593eaaf0ce199ce5903fbd4f85fac5c5f4f7b8e2a44ba42340365e484fea20",
        "64c34a7f5a1149261f0cc03689796f000b495f97ef0953e2a04fb399b4210239",
        "dc1be7a4374c5704116a5ae46c1664c9e775cc5ac7cac74bdd06421c72a3e9bf",
        "863a36a374338c3e67391f1805a639aad285dd652a6e4100b2b4d287e1b24350",
        "4a1a5287ffb8ddfd1753ea0715fc351ebef3ac1f4af77755e6acd241d81c5cc6",
        "888dd194c35df018a8b1e2d1e3786fdd6368004aae725f2e177e5b68d24dc2b6",
        "260414954f579b7b1d6c56f1c2d68dbf5796017292630c6a3b36a28c9340c326",
    ), start=1)},
    "docs/control/amendments/candidate1_v1_synthetic_sandbox_v001.json": "46100af25d0b68d374e38df9c6c1902ac02e6c8d1c2df8307f56ed2ed37e32d0",
    "docs/control/amendments/candidate1_h001_real_falsification_design_v001.json": "5e3eff235212f52480fa00ba7ffabb4d75f4160d51d359dc6e5aa6b9d1b8b1e1",
}


def _review_complete_fixture(tmp_path):
    """Copy the committed review-completion control plane verbatim.

    No hash fixups are needed: the committed receipts and evidence bytes are
    already self-consistent, so the copied tree validates as-is. Mutation tests
    then perturb only the active v012 receipt via ``_rewrite_v012``.
    """
    for relpath in _REVIEW_COMPLETE_FILES:
        target = tmp_path / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        if relpath == "docs/control/active_task.json":
            target.write_bytes(canonical_json_bytes(_REVIEW_COMPLETE_ACTIVE_TASK))
        else:
            shutil.copy2(ROOT / relpath, target)
    restore_historical_h001_inputs(tmp_path)
    return tmp_path


def _rewrite_v012(root, mutate):
    path = root / TASK_DIR / "handoff_v012.json"
    receipt = json.loads(path.read_bytes())
    mutate(receipt)
    data = canonical_json_bytes(receipt)
    path.write_bytes(data)
    active_path = root / "docs/control/active_task.json"
    active = json.loads(active_path.read_bytes())
    active["handoff_receipt_sha256"] = hashlib.sha256(data).hexdigest()
    active_path.write_bytes(canonical_json_bytes(active))


def _swap_decision(receipt, old, new):
    assert old in receipt["decisions"], f"expected decision not present: {old}"
    receipt["decisions"] = [new if d == old else d for d in receipt["decisions"]]


def _set_evidence(receipt, path, sha):
    matched = False
    for item in receipt["evidence"]:
        if item["path"] == path:
            item["sha256"] = sha
            matched = True
    assert matched, f"expected evidence path not present: {path}"


def _skip_unless_review_complete(state):
    if state["active_task"]["phase"] != context._H001_REVIEW_COMPLETE_PHASE:
        pytest.skip("production tree is not at the H001 review-completion phase")


_REVIEW_COMPLETE_RENDER_LINES = (
    "PHASE=candidate1_h001_real_falsification_preregistration_review_complete",
    "NEXT_ACTION=AUTHORIZE_H001_REAL_DATA_INFRASTRUCTURE_PREPARATION_GOVERNANCE",
    "H001_PREREGISTRATION_REVIEW_STATUS=PASSED",
    "H001_PREREGISTRATION_REVIEW_VERDICT=" + context._H001_REVIEW_VERDICT,
    "H001_PREREGISTRATION_REVIEWED_HEAD=" + context._H001_REVIEW_REVIEWED_HEAD,
    "H001_PREREGISTRATION_DESIGN_SHA256=" + context._H001_REVIEW_DESIGN_SHA256,
    "H001_PREREGISTRATION_VALIDATOR_SHA256=" + context._H001_REVIEW_VALIDATOR_SHA256,
    "H001_PREREGISTRATION_REVIEW_NAMED_PROBES=67/67_REJECTED",
    "H001_PREREGISTRATION_REVIEW_GENUINE_MUTATIONS=1136/1136_REJECTED",
    "H001_PREREGISTRATION_REVIEW_BLOCKERS=NONE",
    "H001_PREREGISTRATION_REVIEW_MAJOR_FINDINGS=NONE",
    "H001_EXTERNAL_REVIEW_IS_SCIENTIFIC_EVIDENCE=FALSE",
    "H001_REAL_DATA_ACCESS=FORBIDDEN",
    "H001_ARTIFACT_OPERATIONS=FORBIDDEN",
    "H001_CURRENT_EXECUTION_BUDGET=0",
    "H001_CURRENT_EXECUTION_COUNT=0",
    "H001_SCIENTIFIC_AUTHORIZATION=FALSE",
    "H001_PAPER_TRADE_AUTHORIZATION=FALSE",
    "H001_LIVE_AUTHORIZATION=FALSE",
    "H001_REQUIRED_DURABLE_COPIES=2",
    "H001_REAL_DATA_INFRASTRUCTURE_GOVERNANCE=NOT_YET_AUTHORIZED",
    "V0_AVAILABILITY=UNAVAILABLE",
    "EDGE_STATUS=EDGE_UNPROVEN",
    "LIVE_STATUS=BLOCK_LIVE_INTEGRATION",
)


def test_review_complete_fixture_verifies_and_renders_boundaries(tmp_path):
    root = _review_complete_fixture(tmp_path)
    state = load_and_verify_continuity_state(root)
    assert state["active_task"]["phase"] == context._H001_REVIEW_COMPLETE_PHASE
    receipt = state["handoff_receipt"]
    assert receipt["receipt_index"] == 12
    assert receipt["next_actions"] == [context._H001_REVIEW_COMPLETE_NEXT_ACTION]
    assert receipt["source_head_commit"] == context._H001_REVIEW_MERGED_MAIN_SHA
    assert receipt["source_branch"] == context._H001_REVIEW_SOURCE_BRANCH
    assert receipt["predecessor"] == {
        "path": f"{TASK_DIR}/handoff_v011.json",
        "sha256": context._H001_PREREGISTERED_HANDOFF_SHA256,
    }
    # Every authority boundary is preserved exactly.
    safety = receipt["safety_state"]
    assert safety["edge_status"] == "EDGE_UNPROVEN"
    assert safety["live_status"] == "BLOCK_LIVE_INTEGRATION"
    assert safety["scientific_use_authorized"] is False
    assert safety["paper_trade_authorized"] is False
    assert safety["live_integration_authorized"] is False
    assert safety["real_data_execution_requested"] is False
    assert safety["decomposition_execution_budget"] == 1
    assert safety["decomposition_execution_count"] == 0
    assert safety["quarantine_access"] == "forbidden"
    artifact = receipt["required_artifacts"][0]
    assert artifact["availability"] == "UNAVAILABLE"
    assert artifact["verified_copy_count"] == 0
    packet = render_context_packet(state)
    for line in _REVIEW_COMPLETE_RENDER_LINES:
        assert line in packet
    assert "PROTOCOL_EXECUTION=BLOCKED" in packet


def test_review_complete_render_distinguishes_execution_budgets(tmp_path):
    state = load_and_verify_continuity_state(_review_complete_fixture(tmp_path))
    packet = render_context_packet(state)
    # Umbrella decomposition and H001 execution budgets are labeled distinctly;
    # no bare/ambiguous "execution 0/1" appears in the H001-specific output.
    assert "UMBRELLA_DECOMPOSITION_EXECUTION=0/1" in packet
    assert "H001_EXECUTION=0/0" in packet
    assert "H001_EXECUTION=0/1" not in packet
    assert "H001_CURRENT_EXECUTION_BUDGET=0" in packet
    assert "H001_CURRENT_EXECUTION_BUDGET=1" not in packet
    assert "H001_CURRENT_EXECUTION_COUNT=1" not in packet


def test_production_review_complete_phase_verifies_and_renders():
    state = load_and_verify_continuity_state(ROOT)
    _skip_unless_review_complete(state)
    assert state["handoff_receipt"]["next_actions"] == [context._H001_REVIEW_COMPLETE_NEXT_ACTION]
    packet = render_context_packet(state)
    for line in _REVIEW_COMPLETE_RENDER_LINES:
        assert line in packet
    # The transition must not claim infrastructure governance is authorized.
    assert "H001_REAL_DATA_INFRASTRUCTURE_GOVERNANCE=AUTHORIZED" not in packet


def test_v001_through_v011_remain_byte_identical_and_chained():
    """No historical receipt was mutated by the review-completion transition:
    each predecessor's on-disk bytes must match the sha recorded by its
    successor, and v011 must equal the pinned reviewed-preregistration hash."""
    for idx in range(12, 1, -1):
        succ = json.loads((ROOT / TASK_DIR / f"handoff_v{idx:03d}.json").read_bytes())
        pred_bytes = (ROOT / succ["predecessor"]["path"]).read_bytes()
        assert hashlib.sha256(pred_bytes).hexdigest() == succ["predecessor"]["sha256"]
    v011_bytes = (ROOT / TASK_DIR / "handoff_v011.json").read_bytes()
    assert hashlib.sha256(v011_bytes).hexdigest() == context._H001_PREREGISTERED_HANDOFF_SHA256
    v001 = json.loads((ROOT / TASK_DIR / "handoff_v001.json").read_bytes())
    assert v001["predecessor"] == "GENESIS"


_HEAD_DECISION = f"H001_PREREGISTRATION_REVIEWED_HEAD={context._H001_REVIEW_REVIEWED_HEAD}"
_DESIGN_DECISION = f"H001_PREREGISTRATION_DESIGN_SHA256={context._H001_REVIEW_DESIGN_SHA256}"
_VALIDATOR_DECISION = f"H001_PREREGISTRATION_VALIDATOR_SHA256={context._H001_REVIEW_VALIDATOR_SHA256}"
_VERDICT_DECISION = f"H001_PREREGISTRATION_REVIEW_VERDICT={context._H001_REVIEW_VERDICT}"


@pytest.mark.parametrize("mutation", [
    # wrong reviewed head
    lambda r: _swap_decision(r, _HEAD_DECISION, "H001_PREREGISTRATION_REVIEWED_HEAD=" + "0" * 40),
    # wrong design hash (recorded decision and evidence binding)
    lambda r: _swap_decision(r, _DESIGN_DECISION, "H001_PREREGISTRATION_DESIGN_SHA256=" + "0" * 64),
    lambda r: _set_evidence(r, "docs/experiments/candidate1_h001_real_data_falsification_v0.json", "0" * 64),
    # wrong validator hash (recorded decision and evidence binding)
    lambda r: _swap_decision(r, _VALIDATOR_DECISION, "H001_PREREGISTRATION_VALIDATOR_SHA256=" + "0" * 64),
    lambda r: _set_evidence(r, "quantbot/experiment/h001_real_falsification_preregistration.py", "0" * 64),
    # wrong predecessor v011 evidence binding
    lambda r: _set_evidence(r, f"{TASK_DIR}/handoff_v011.json", "0" * 64),
    # failed review verdict / status
    lambda r: _swap_decision(r, _VERDICT_DECISION, "H001_PREREGISTRATION_REVIEW_VERDICT=QNTY_H001_REAL_FALSIFICATION_PREREGISTRATION_REREVIEW_FAILED"),
    lambda r: _swap_decision(r, "H001_PREREGISTRATION_REVIEW_STATUS=PASSED", "H001_PREREGISTRATION_REVIEW_STATUS=FAILED"),
    # nonzero blocker / major counts
    lambda r: _swap_decision(r, "H001_PREREGISTRATION_REVIEW_BLOCKERS=NONE", "H001_PREREGISTRATION_REVIEW_BLOCKERS=1"),
    lambda r: _swap_decision(r, "H001_PREREGISTRATION_REVIEW_MAJOR_FINDINGS=NONE", "H001_PREREGISTRATION_REVIEW_MAJOR_FINDINGS=1"),
    # wrong probe counts
    lambda r: _swap_decision(r, "H001_PREREGISTRATION_REVIEW_NAMED_PROBES=67/67_REJECTED", "H001_PREREGISTRATION_REVIEW_NAMED_PROBES=66/67_REJECTED"),
    lambda r: _swap_decision(r, "H001_PREREGISTRATION_REVIEW_GENUINE_MUTATIONS=1136/1136_REJECTED", "H001_PREREGISTRATION_REVIEW_GENUINE_MUTATIONS=1135/1136_REJECTED"),
    # wrong receipt index
    lambda r: r.update(receipt_index=13),
    lambda r: r.update(receipt_index=11),
    # wrong predecessor pointer
    lambda r: r["predecessor"].update(sha256="0" * 64),
    lambda r: r["predecessor"].update(path=f"{TASK_DIR}/handoff_v010.json"),
    # wrong next action
    lambda r: r.update(next_actions=["AUTHORIZE_SOMETHING_ELSE"]),
    lambda r: r.update(next_actions=[context._H001_PREREGISTERED_NEXT_ACTION]),
    # wrong source base SHA / branch
    lambda r: r.update(source_head_commit="0" * 40),
    lambda r: r.update(source_branch="feat/wrong-branch"),
    # changed-file scope drift (extra / missing)
    lambda r: r["changed_file_scope"].append("docs/extra.md"),
    lambda r: r["changed_file_scope"].remove("quantbot/continuity/context.py"),
    # real-data execution / authorization
    lambda r: r["safety_state"].update(real_data_execution_requested=True),
    lambda r: r["safety_state"].update(scientific_use_authorized=True),
    lambda r: r["safety_state"].update(paper_trade_authorized=True),
    lambda r: r["safety_state"].update(live_integration_authorized=True),
    lambda r: r["safety_state"].update(edge_status="EDGE_PROVEN"),
    lambda r: r["safety_state"].update(live_status="ALLOW_LIVE_INTEGRATION"),
    # artifact authorization / changed V0 availability + copy count
    lambda r: r["required_artifacts"][0].update(availability="VERIFIED_AVAILABLE", verified_copy_count=2, canonical_paths=["qnty-artifact://store-a/sha256/" + "a" * 64, "qnty-artifact://store-b/sha256/" + "a" * 64]),
    lambda r: r["required_artifacts"][0].update(verified_copy_count=2),
    # nonzero H001 execution budget / count
    lambda r: _swap_decision(r, "H001_CURRENT_EXECUTION_BUDGET=0", "H001_CURRENT_EXECUTION_BUDGET=1"),
    lambda r: _swap_decision(r, "H001_CURRENT_EXECUTION_COUNT=0", "H001_CURRENT_EXECUTION_COUNT=1"),
    # dropped review-specific and design-governance prohibitions
    lambda r: r["prohibited_actions"].remove("TREAT_EXTERNAL_REVIEW_AS_SCIENTIFIC_EVIDENCE"),
    lambda r: r["prohibited_actions"].remove("AUTHORIZE_H001_REAL_DATA_INFRASTRUCTURE_WITHOUT_SEPARATE_GOVERNANCE"),
    lambda r: r["prohibited_actions"].remove("PREREGISTER_H001_REAL_PROTOCOL_WITHOUT_SEPARATE_GOVERNANCE"),
])
def test_review_complete_drift_fails_closed(tmp_path, mutation):
    root = _review_complete_fixture(tmp_path)
    _rewrite_v012(root, mutation)
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(root)


def test_review_complete_unmutated_fixture_is_the_control(tmp_path):
    """Control: the fixture verifies before any mutation, so the drift matrix
    proves the mutation caused the rejection rather than a broken fixture."""
    load_and_verify_continuity_state(_review_complete_fixture(tmp_path))


# --------------------------------------------------------------------------
# H001 pre-data assurance governance (phase v013)
# --------------------------------------------------------------------------

_PRE_DATA_FILES = _REVIEW_COMPLETE_FILES + (
    "docs/control/amendments/candidate1_h001_pre_data_assurance_v001.json",
    f"{TASK_DIR}/handoff_v013.json",
)


def _pre_data_fixture(tmp_path):
    for relpath in _PRE_DATA_FILES + ("quantbot/continuity/context.py", "tests/continuity/test_cross_agent_continuity.py"):
        target = tmp_path / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relpath, target)
    restore_historical_h001_inputs(tmp_path)
    active_path = tmp_path / "docs/control/active_task.json"
    active = json.loads(active_path.read_bytes())
    receipt_path = tmp_path / TASK_DIR / "handoff_v013.json"
    active.update(
        phase=context._H001_PRE_DATA_PHASE,
        handoff_receipt_path=f"{TASK_DIR}/handoff_v013.json",
        handoff_receipt_sha256=hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
    )
    receipt = json.loads(receipt_path.read_bytes())
    for item in receipt["evidence"]:
        if item["path"] in {"quantbot/continuity/context.py", "tests/continuity/test_cross_agent_continuity.py"}:
            item["sha256"] = hashlib.sha256((tmp_path / item["path"]).read_bytes()).hexdigest()
    receipt_path.write_bytes(canonical_json_bytes(receipt))
    active["handoff_receipt_sha256"] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    active_path.write_bytes(canonical_json_bytes(active))
    return tmp_path


def _rewrite_v013(root, mutate):
    path = root / TASK_DIR / "handoff_v013.json"
    receipt = json.loads(path.read_bytes())
    mutate(receipt)
    data = canonical_json_bytes(receipt)
    path.write_bytes(data)
    active_path = root / "docs/control/active_task.json"
    active = json.loads(active_path.read_bytes())
    active["handoff_receipt_sha256"] = hashlib.sha256(data).hexdigest()
    active_path.write_bytes(canonical_json_bytes(active))


def _rewrite_pre_data_amendment(root, mutate):
    path = root / context.PRE_DATA_H001_AMENDMENT_RELPATH
    amendment = json.loads(path.read_bytes())
    mutate(amendment)
    path.write_bytes(canonical_json_bytes(amendment))


def test_valid_v013_pre_data_assurance_fixture_verifies_and_renders(tmp_path):
    state = load_and_verify_continuity_state(_pre_data_fixture(tmp_path))
    assert state["active_task"]["phase"] == context._H001_PRE_DATA_PHASE
    assert state["handoff_receipt"]["receipt_index"] == 13
    packet = render_context_packet(state)
    for line in (
        "H001_PRE_DATA_ASSURANCE_GOVERNANCE=AUTHORIZED_SCAFFOLD_ONLY",
        "H001_PRE_DATA_ASSURANCE_EXECUTION=NOT_AUTHORIZED",
        "H001_SYNTHETIC_NULL_CALIBRATION_SPEC_DRAFT=AUTHORIZED",
        "H001_SYNTHETIC_NULL_CALIBRATION_SPEC_FREEZE=NOT_AUTHORIZED",
        "H001_SYNTHETIC_NULL_CALIBRATION_SPEC=REQUIRED_NOT_FROZEN",
        "H001_TEMPORAL_CAUSALITY_AMENDMENT=REQUIRED_NOT_CREATED",
        "H001_TEMPORAL_CAUSALITY_TARGET=FUNDING_TIME_STRICTLY_BEFORE_DECISION",
        "H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION=NOT_AUTHORIZED",
        "H001_BOOTSTRAP_BLOCK_LENGTH_TUNING=FORBIDDEN",
        "H001_HAC_LAG_TUNING=FORBIDDEN",
        "GLOBAL_REAL_PROTOCOL_HOLDOUT_LEDGER_SCOPE=SCHEMA_ONLY",
        "GLOBAL_REAL_PROTOCOL_HOLDOUT_LEDGER_DATA_ACCESS=FORBIDDEN",
        "GLOBAL_REAL_PROTOCOL_HOLDOUT_LEDGER_BACKFILL=FORBIDDEN",
        "GLOBAL_REAL_PROTOCOL_HOLDOUT_LEDGER=REQUIRED_NOT_IMPLEMENTED",
        "H001_SYNTHETIC_STORE_CANARY_SCAFFOLD=AUTHORIZED_NOT_IMPLEMENTED",
        "H001_FAILURE_DOMAIN_EVIDENCE_SCOPE=METADATA_SCHEMA_ONLY",
        "H001_CANDIDATE_STORE_ACCESS_OR_PROBING=FORBIDDEN",
        "H001_CANDIDATE_STORE_CONFIGURATION=NOT_AUTHORIZED",
        "H001_REVIEW_PACKET_REAL_DATA_INCLUSION=FORBIDDEN",
        "H001_REVIEW_PACKET_SECRET_INCLUSION=FORBIDDEN",
        "H001_REAL_DATA_ACCESS=FORBIDDEN", "H001_EXECUTION=0/0", "UMBRELLA_DECOMPOSITION_EXECUTION=0/1",
        "V0_AVAILABILITY=UNAVAILABLE", "H001_DURABLE_STORES_CONFIGURED=FALSE",
        "H001_SCIENTIFIC_AUTHORIZATION=FALSE", "H001_PAPER_TRADE_AUTHORIZATION=FALSE", "H001_LIVE_AUTHORIZATION=FALSE",
    ):
        assert line in packet
    assert "infrastructure authorized" not in packet


@pytest.mark.parametrize("mutation", [
    lambda a: a.update(amendment_id="wrong"),
    lambda a: a.update(authorization_status="wrong"),
    lambda a: a.update(governed_h001_protocol_id="wrong"),
    lambda a: a.update(source_main_commit="0" * 40),
    lambda a: a["source_handoff"].update(sha256="0" * 64),
    lambda a: a["review_binding"].update(design_sha256="0" * 64),
    lambda a: a["review_binding"].update(validator_sha256="0" * 64),
    lambda a: a["review_binding"].update(review_verdict="FAILED"),
    lambda a: a["predecessor_amendment"].update(path="wrong"),
    lambda a: a["allowed_actions"].remove(context._H001_PRE_DATA_ALLOWED_ACTIONS[0]),
    lambda a: a["allowed_actions"].append("EXTRA"),
    lambda a: a["allowed_actions"].__setitem__(0, "DRAFT_APPEND_ONLY_H001_TEMPORAL_CAUSALITY_AMENDMENT"),
    lambda a: a["allowed_actions"].__setitem__(1, "DRAFT_AND_FREEZE_H001_SYNTHETIC_NULL_CALIBRATION_SPEC"),
    lambda a: a["allowed_actions"].__setitem__(2, "IMPLEMENT_GLOBAL_REAL_PROTOCOL_HOLDOUT_LEDGER"),
    lambda a: a["allowed_actions"].__setitem__(3, "IMPLEMENT_DURABLE_STORE_FAILURE_DOMAIN_EVIDENCE_SCHEMA"),
    lambda a: a["allowed_actions"].__setitem__(5, "IMPLEMENT_REPLAYABLE_REVIEW_EVIDENCE_PACKET_SCHEMA"),
    lambda a: a["allowed_actions"].__setitem__(6, "IMPLEMENT_SYNTHETIC_ARTIFACT_CANARY_SCAFFOLD_WITHOUT_STORE_CONFIGURATION"),
    lambda a: a["allowed_actions"].__setitem__(2, "IMPLEMENT_APPEND_ONLY_GLOBAL_REAL_PROTOCOL_HOLDOUT_DISCLOSURE_LEDGER_SCHEMA"),
    lambda a: a["allowed_actions"].__setitem__(3, "IMPLEMENT_DURABLE_STORE_FAILURE_DOMAIN_EVIDENCE_METADATA_SCHEMA"),
    lambda a: a["assurance_controls"].remove(context._H001_PRE_DATA_ASSURANCE_CONTROLS[0]),
    lambda a: a["assurance_controls"].append("EXTRA"),
    lambda a: a["assurance_controls"].remove("CALIBRATION_SPEC_FREEZE_REQUIRES_SEPARATE_GOVERNANCE"),
    lambda a: a["non_effects"].remove("DOES_NOT_AUTHORIZE_CALIBRATION_SPEC_FREEZE"),
    lambda a: a["prohibited_actions"].remove("FREEZE_H001_SYNTHETIC_NULL_CALIBRATION_SPEC"),
    lambda a: a["transition_gates"].update(temporal_causality_amendment_applied=True),
    lambda a: a["transition_gates"].update(synthetic_null_calibration_execution_authorized=True),
    lambda a: a["transition_gates"].update(bootstrap_block_length_tuning_authorized=True),
    lambda a: a["transition_gates"].update(hac_lag_tuning_authorized=True),
    lambda a: a["transition_gates"].update(candidate_store_configuration_authorized=True),
    lambda a: a["transition_gates"].update(synthetic_store_canary_execution_authorized=True),
    lambda a: a["transition_gates"].update(real_artifact_store_operations_authorized=True),
    lambda a: a["transition_gates"].update(real_data_access_authorized=True),
    lambda a: a["transition_gates"].update(validation_execution_authorized=True),
    lambda a: a["transition_gates"].update(holdout_execution_authorized=True),
    lambda a: a["transition_gates"].update(h001_primary_execution_budget=1),
    lambda a: a["transition_gates"].update(h001_primary_execution_count=1),
    lambda a: a["transition_gates"].update(scientific_authorization=True),
    lambda a: a["transition_gates"].update(paper_trade_authorization=True),
    lambda a: a["transition_gates"].update(live_authorization=True),
    lambda a: a["transition_gates"].update(synthetic_null_calibration_spec_freeze_authorized=True),
    lambda a: a["transition_gates"].update(synthetic_null_calibration_spec_frozen=True),
    lambda a: a["transition_gates"].update(global_holdout_ledger_data_access_authorized=True),
    lambda a: a["transition_gates"].update(global_holdout_ledger_backfill_authorized=True),
    lambda a: a["transition_gates"].update(global_holdout_ledger_prior_history_mutation_authorized=True),
    lambda a: a["transition_gates"].update(candidate_store_access_authorized=True),
    lambda a: a["transition_gates"].update(candidate_store_probe_authorized=True),
    lambda a: a["transition_gates"].update(candidate_store_credential_access_authorized=True),
    lambda a: a["transition_gates"].update(review_packet_real_data_inclusion_authorized=True),
    lambda a: a["transition_gates"].update(review_packet_secret_inclusion_authorized=True),
    lambda a: a["transition_gates"].update(v0_disposition_unchanged=False),
    lambda a: a.update(unexpected=True),
    lambda a: a["transition_gates"].update(unexpected=True),
    lambda a: a["transition_gates"].pop("synthetic_null_calibration_spec_freeze_authorized"),
    lambda a: a.pop("review_binding"),
])
def test_v013_amendment_drift_fails_closed(tmp_path, mutation):
    root = _pre_data_fixture(tmp_path)
    _rewrite_pre_data_amendment(root, mutation)
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(root)


@pytest.mark.parametrize("mutation", [
    lambda r: r.update(receipt_index=12),
    lambda r: r["predecessor"].update(path=f"{TASK_DIR}/handoff_v011.json"),
    lambda r: r.update(next_actions=["WRONG"]),
    lambda r: r["changed_file_scope"].append("extra.md"),
    lambda r: r["changed_file_scope"].remove("quantbot/continuity/context.py"),
    lambda r: r["safety_state"].update(real_data_execution_requested=True),
    lambda r: r["safety_state"].update(scientific_use_authorized=True),
    lambda r: r["safety_state"].update(paper_trade_authorized=True),
    lambda r: r["safety_state"].update(live_integration_authorized=True),
    lambda r: r["safety_state"].update(edge_status="EDGE_PROVEN"),
    lambda r: r["safety_state"].update(live_status="ALLOW_LIVE_INTEGRATION"),
    lambda r: r["required_artifacts"][0].update(availability="VERIFIED_AVAILABLE", verified_copy_count=2),
    lambda r: r["decisions"].remove("H001_CURRENT_EXECUTION_BUDGET=0"),
    lambda r: r["decisions"].__setitem__(r["decisions"].index("H001_CURRENT_EXECUTION_BUDGET=0"), "H001_CURRENT_EXECUTION_BUDGET=1"),
    lambda r: r["prohibited_actions"].remove("EXECUTE_H001"),
    lambda r: r.update(unknown_nested={}),
])
def test_v013_handoff_drift_fails_closed(tmp_path, mutation):
    root = _pre_data_fixture(tmp_path)
    _rewrite_v013(root, mutation)
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(root)


def test_v001_through_v012_remain_byte_identical_to_pinned_base():
    assert set(_EXPECTED_PRE_V013_SHA256) == set(
        tuple(f"{TASK_DIR}/handoff_v{idx:03d}.json" for idx in range(1, 13)) + (
            "docs/control/amendments/candidate1_v1_synthetic_sandbox_v001.json",
            "docs/control/amendments/candidate1_h001_real_falsification_design_v001.json",
        )
    )
    for relpath, expected_sha256 in _EXPECTED_PRE_V013_SHA256.items():
        assert hashlib.sha256((ROOT / relpath).read_bytes()).hexdigest() == expected_sha256


def test_implemented_assurance_scaffold_phase_renders_non_execution_boundaries():
    state = load_and_verify_continuity_state(ROOT)
    if state["active_task"]["phase"] != context._H001_SCAFFOLD_PHASE:
        pytest.skip("production tree is before the implemented assurance scaffold transition")
    packet = render_context_packet(state)
    for line in (
        "H001_TEMPORAL_CAUSALITY_AMENDMENT=CREATED_NOT_APPLIED",
        "H001_SYNTHETIC_NULL_CALIBRATION_HARNESS=IMPLEMENTED_NOT_EXECUTED",
        "H001_SYNTHETIC_NULL_CALIBRATION_RESULTS=NONE",
        "GLOBAL_REAL_PROTOCOL_HOLDOUT_LEDGER=IMPLEMENTED",
        "GLOBAL_REAL_PROTOCOL_HOLDOUT_LEDGER_STATE=EMPTY_NO_BACKFILL",
        "H001_REVIEW_EVIDENCE_PACKET_SCHEMA=IMPLEMENTED",
        "H001_REVIEW_EVIDENCE_PACKET_CREATED=FALSE",
        "H001_SYNTHETIC_ARTIFACT_CANARY_SCAFFOLD=IMPLEMENTED_NOT_EXECUTED",
        "H001_SYNTHETIC_ARTIFACT_CANARY_REGISTERED_AS_REAL_ARTIFACT=FALSE",
        "H001_PRE_DATA_ASSURANCE_SCAFFOLD_REVIEW=REQUIRED_NOT_COMPLETED",
        "H001_EXECUTION=0/0",
        "EDGE_STATUS=EDGE_UNPROVEN",
        "LIVE_STATUS=BLOCK_LIVE_INTEGRATION",
    ):
        assert line in packet

def test_repaired_assurance_scaffold_hashes_are_independently_pinned():
    state = load_and_verify_continuity_state(ROOT)
    if state["active_task"]["phase"] != context._H001_SCAFFOLD_PHASE:
        pytest.skip("production tree is before the implemented assurance scaffold transition")
    for relpath, expected in context._H001_SCAFFOLD_REPAIRED_FILE_SHA256.items():
        assert hashlib.sha256((ROOT / relpath).read_bytes()).hexdigest() == expected


def test_h001_assurance_review_completion_transition_renders_and_binds():
    state = load_and_verify_continuity_state(ROOT)
    if state["active_task"]["phase"] in (context._H001_TEMPORAL_CANDIDATE_PHASE, context._H001_TEMPORAL_REVIEW_COMPLETE_PHASE, context._H001_TEMPORAL_ACTIVE_PHASE, context._H001_CALIBRATION_GOVERNANCE_PHASE, context._H001_CALIBRATION_CANDIDATE_PHASE):
        pytest.skip("production tree has advanced to the temporal candidate phase")
    assert state["active_task"]["phase"] == context._H001_ASSURANCE_REVIEW_COMPLETE_PHASE
    assert state["handoff_receipt"]["receipt_index"] == 15
    assert state["handoff_receipt"]["review_binding"]["reviewed_pr_number"] == 282
    packet = render_context_packet(state)
    for line in (
        "H001_PRE_DATA_ASSURANCE_SCAFFOLD_REVIEW=COMPLETED_PASSED",
        "H001_PRE_DATA_ASSURANCE_SCAFFOLD_REVIEWED_HEAD=c52c607045803ab6d6e2a961f0f697aa72bf7581",
        "H001_PRE_DATA_ASSURANCE_SCAFFOLD_MERGE_COMMIT=ae61c6162f3164e0b24dd567a6ef73bdb5ecf8ea",
        "H001_REVIEW_PROTOCOL_RECORD=RECORDED_AFTER_REVIEW_NOT_PREREGISTERED",
        "H001_REVIEW_EVIDENCE_PACKET=CREATED_METADATA_ONLY",
        "H001_TEMPORAL_CAUSALITY_AMENDMENT_IMPLEMENTATION_FOR_REVIEW=AUTHORIZED",
        "H001_TEMPORAL_CAUSALITY_AMENDMENT_EFFECTIVE=FALSE",
        "H001_TEMPORAL_CAUSALITY_CURRENT_CONTRACT=UNCHANGED",
        "H001_SYNTHETIC_NULL_CALIBRATION_SPEC_FREEZE=NOT_AUTHORIZED",
        "H001_SYNTHETIC_NULL_CALIBRATION_RESULTS=NONE",
        "GLOBAL_REAL_PROTOCOL_HOLDOUT_LEDGER_STATE=EMPTY_NO_BACKFILL",
        "H001_CANDIDATE_STORE_ACCESS_OR_PROBING=FORBIDDEN",
        "H001_REAL_DATA_ACCESS=FORBIDDEN",
        "H001_EXECUTION=0/0",
        "V0_AVAILABILITY=UNAVAILABLE",
        "EDGE_UNPROVEN",
        "BLOCK_LIVE_INTEGRATION",
    ):
        assert line in packet


@pytest.mark.parametrize("mutation", [
    lambda binding: binding.update(reviewed_pr_number=True),
    lambda binding: binding.update(reviewed_implementation_head="0" * 40),
    lambda binding: binding.update(final_review_verdict="WRONG"),
    lambda binding: binding.update(review_packet_sha256="0" * 64),
])
def test_h001_assurance_review_binding_drift_fails_closed(tmp_path, mutation):
    root = tmp_path / "repo"
    copy_repo_without_runtime(ROOT, root)
    receipt_path = root / TASK_DIR / "handoff_v015.json"
    receipt = json.loads(receipt_path.read_bytes())
    mutation(receipt["review_binding"])
    receipt_path.write_bytes(canonical_json_bytes(receipt))
    active_path = root / "docs/control/active_task.json"
    active = json.loads(active_path.read_bytes())
    active["handoff_receipt_path"] = "docs/control/tasks/RECOVER_OR_RETIRE_CANDIDATE1_V0_FROZEN_INPUT/handoff_v016.json"
    active["phase"] = context._H001_TEMPORAL_CANDIDATE_PHASE
    active["handoff_receipt_sha256"] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    active_path.write_bytes(canonical_json_bytes(active))
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(root)


@pytest.mark.parametrize("mutation", [
    lambda r: r["decisions"].append("H001_REVIEW_EVIDENCE_PACKET=REQUIRED_NOT_IMPLEMENTED"),
    lambda r: r["decisions"].append("INVENTED_DECISION=TRUE"),
    lambda r: r["decisions"].pop(),
    lambda r: r["decisions"].append(r["decisions"][0]),
    lambda r: r["decisions"].append("H001_TEMPORAL_CAUSALITY_AMENDMENT_EFFECTIVE=TRUE"),
])
def test_h001_assurance_exact_decision_contract_fails_closed(tmp_path, mutation):
    root = tmp_path / "repo"
    copy_repo_without_runtime(ROOT, root)
    receipt_path = root / TASK_DIR / "handoff_v015.json"
    receipt = json.loads(receipt_path.read_bytes())
    mutation(receipt)
    receipt_path.write_bytes(canonical_json_bytes(receipt))
    active_path = root / "docs/control/active_task.json"
    active = json.loads(active_path.read_bytes())
    active["handoff_receipt_sha256"] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    active_path.write_bytes(canonical_json_bytes(active))
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(root)


@pytest.mark.parametrize("mutation", [
    lambda r: r["evidence"].remove(next(x for x in r["evidence"] if x["path"].endswith("handoff_v014.json"))),
    lambda r: next(x for x in r["evidence"] if x["path"].endswith("handoff_v014.json")).update(sha256="0" * 64),
    lambda r: r["evidence"].append({"path": f"{TASK_DIR}/handoff_v014.json", "sha256": context._H001_ASSURANCE_PROTOCOL_SHA256}),
    lambda r: r["predecessor"].update(sha256="0" * 64),
])
def test_h001_assurance_v014_evidence_binding_fails_closed(tmp_path, mutation):
    root = tmp_path / "repo"
    copy_repo_without_runtime(ROOT, root)
    receipt_path = root / TASK_DIR / "handoff_v015.json"
    receipt = json.loads(receipt_path.read_bytes())
    mutation(receipt)
    receipt_path.write_bytes(canonical_json_bytes(receipt))
    active_path = root / "docs/control/active_task.json"
    active = json.loads(active_path.read_bytes())
    active["handoff_receipt_sha256"] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    active_path.write_bytes(canonical_json_bytes(active))
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(root)


# The exact sixteen-file scope of the reviewed PR #282 (base 28d6c70 -> head c52c607).
REVIEW_PR282_SCOPE_16 = sorted([
    "docs/assurance/H001_PRE_DATA_ASSURANCE_SCAFFOLD.md",
    "docs/assurance/durable_store_failure_domain_evidence_schema_v001.json",
    "docs/assurance/global_real_protocol_holdout_disclosure_ledger_v001.json",
    "docs/assurance/h001_synthetic_null_calibration_spec_draft_v001.json",
    "docs/assurance/h001_temporal_causality_amendment_draft_v001.json",
    "docs/assurance/replayable_review_evidence_packet_schema_v001.json",
    "docs/assurance/synthetic_artifact_canary_scaffold_v001.json",
    "docs/control/active_task.json",
    f"docs/control/tasks/{TASK_ID}/handoff_v014.json",
    "quantbot/assurance/__init__.py",
    "quantbot/assurance/contracts.py",
    "quantbot/assurance/h001_null_calibration.py",
    "quantbot/continuity/context.py",
    "tests/assurance/test_contracts.py",
    "tests/assurance/test_h001_null_calibration.py",
    "tests/continuity/test_cross_agent_continuity.py",
])


def _git(args, cwd):
    return subprocess.run(
        ["git", "-c", "user.email=replay@example.com", "-c", "user.name=replay", *args],
        cwd=str(cwd), check=True, capture_output=True, text=True,
    )


def test_review_recipe_binds_corrected_base_not_merged_main():
    """The recorded recipe pins the reviewed-PR base, never the merged-main commit;
    binding merged-main was the MAJOR replayability defect this repair corrects."""
    from quantbot.assurance import contracts
    base = context._H001_SCAFFOLD_BASE_SHA          # 28d6c70... = actual PR #282 base
    merged_main = context._H001_ASSURANCE_MERGE_SHA  # ae61c61... = later merged-main commit
    head = context._H001_ASSURANCE_REVIEWED_HEAD     # c52c607... = reviewed implementation head
    assert base != merged_main and head != merged_main and base != head
    assert any(f"BASE={base}" in command for command in contracts._REVIEW_COMMANDS)
    assert all(merged_main not in command for command in contracts._REVIEW_COMMANDS)


def test_review_recipe_safe_subset_replays_in_synthetic_repo(tmp_path):
    """Independently replay the critical safe subset of the recorded recipe in a
    throwaway git repository: corrected merge-base passes, the exact sixteen-file
    scope is reproduced, a detached worktree reaches HEAD, and exported-tree imports
    resolve with cwd under the export (never from the editable install)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init", "-q", "-b", "main"], repo)
    # Base commit seeds an importable package so the exported tree is runnable.
    (repo / "quantbot").mkdir()
    (repo / "quantbot" / "__init__.py").write_text('EXPORT_TREE_MARKER = "synthetic-export-tree"\n')
    (repo / "seed.txt").write_text("seed\n")
    _git(["add", "-A"], repo)
    _git(["commit", "-q", "-m", "base"], repo)
    base = _git(["rev-parse", "HEAD"], repo).stdout.strip()
    # Head commit adds exactly the sixteen reviewed-scope files.
    for rel in REVIEW_PR282_SCOPE_16:
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"reviewed-scope:{rel}\n")
    _git(["add", "-A"], repo)
    _git(["commit", "-q", "-m", "head"], repo)
    head = _git(["rev-parse", "HEAD"], repo).stdout.strip()

    # (1) merge-base with the base commit is exactly the base commit.
    assert _git(["merge-base", base, head], repo).stdout.strip() == base
    # (2) exact sixteen-file scope reproduced (not a count-only check).
    observed = sorted(_git(["diff", "--name-only", f"{base}...{head}"], repo).stdout.split())
    assert observed == REVIEW_PR282_SCOPE_16
    assert len(observed) == 16
    # (3) a detached worktree reaches the reviewed HEAD.
    worktree = tmp_path / "wt"
    _git(["worktree", "add", "--detach", str(worktree), head], repo)
    try:
        assert _git(["rev-parse", "HEAD"], worktree).stdout.strip() == head
        # (4) git archive export contains no .git, and imports resolve from EXPORT.
        export = tmp_path / "export"
        export.mkdir()
        archive = tmp_path / "head.tar"
        _git(["archive", "--format=tar", "-o", str(archive), head], worktree)
        with tarfile.open(archive) as tar:
            tar.extractall(export, filter="data")
        assert not (export / ".git").exists()
        proc = subprocess.run(
            [sys.executable, "-c",
             "import quantbot; print(quantbot.__file__); print(quantbot.EXPORT_TREE_MARKER)"],
            cwd=str(export), capture_output=True, text=True, check=True,
        )
        resolved, marker = proc.stdout.splitlines()[:2]
        assert Path(resolved).resolve().is_relative_to(export.resolve())
        assert marker == "synthetic-export-tree"
    finally:
        _git(["worktree", "remove", "--force", str(worktree)], repo)


def _temporal_mutated_tree(tmp_path, mutate_receipt=None, mutate_amendment=None):
    root = tmp_path / "repo"
    copy_repo_without_runtime(ROOT, root)
    restore_historical_h001_inputs(root)
    receipt_path = root / TASK_DIR / "handoff_v016.json"
    receipt = json.loads(receipt_path.read_bytes())
    amendment_path = root / context._H001_TEMPORAL_CANDIDATE_AMENDMENT_RELPATH
    amendment = json.loads(amendment_path.read_bytes())
    if mutate_receipt:
        mutate_receipt(receipt)
        receipt_path.write_bytes(canonical_json_bytes(receipt))
    if mutate_amendment:
        mutate_amendment(amendment)
        amendment_path.write_bytes(canonical_json_bytes(amendment))
    active_path = root / context.ACTIVE_TASK_RELPATH
    active = json.loads(active_path.read_bytes())
    active["handoff_receipt_sha256"] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    active_path.write_bytes(canonical_json_bytes(active))
    return root


@pytest.mark.parametrize("mutate_receipt", [
    lambda r: r.update(receipt_index=15),
    lambda r: r["predecessor"].update(sha256="0" * 64),
    lambda r: r.update(source_head_commit="0" * 40),
    lambda r: r.update(next_actions=["IMPLEMENT_H001_TEMPORAL_CAUSALITY_AMENDMENT_FOR_INDEPENDENT_REVIEW"]),
    lambda r: r["changed_file_scope"].append("extra.txt"),
    lambda r: r["decisions"].append("H001_TEMPORAL_CAUSALITY_AMENDMENT_EFFECTIVE=TRUE"),
    lambda r: r.update(blockers=[]),
])
def test_temporal_candidate_receipt_mutations_fail_closed(tmp_path, mutate_receipt):
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(_temporal_mutated_tree(tmp_path, mutate_receipt=mutate_receipt))


@pytest.mark.parametrize("mutate_amendment", [
    lambda a: a.update(effective=True),
    lambda a: a.update(independent_review_completed=True),
    lambda a: a.update(current_contract_unchanged=False),
    lambda a: a["change"].update(after="latest funding_time_utc <= bar[t].open_time_utc"),
    lambda a: a["non_effects"].append("EDGE_PROVEN"),
    lambda a: a.update(unexpected_key=True),
])
def test_temporal_candidate_amendment_mutations_fail_closed(tmp_path, mutate_amendment):
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(_temporal_mutated_tree(tmp_path, mutate_amendment=mutate_amendment))


def test_temporal_candidate_production_render_is_review_only():
    state = load_and_verify_continuity_state(ROOT)
    if state["active_task"]["phase"] in (context._H001_CALIBRATION_GOVERNANCE_PHASE, context._H001_CALIBRATION_CANDIDATE_PHASE):
        pytest.skip("production tree has advanced past temporal activation")
    if state["active_task"]["phase"] == context._H001_TEMPORAL_ACTIVE_PHASE:
        packet = render_context_packet(state)
        for marker in ("H001_TEMPORAL_CAUSALITY_AMENDMENT=EFFECTIVE", "H001_TEMPORAL_CAUSALITY_ACTIVATION_EFFECTIVE=TRUE", "H001_TEMPORAL_CAUSALITY_CURRENT_CONTRACT=STRICT_LT_EFFECTIVE", "H001_TEMPORAL_CAUSALITY_CURRENT_SIGNAL_RULE=FUNDING_TIME_LT_DECISION", "H001_TEMPORAL_CAUSALITY_EQUALITY_SIGNAL_EVENT=EXCLUDED", "H001_REAL_DATA_ACCESS=FORBIDDEN", "EDGE_UNPROVEN", "BLOCK_LIVE_INTEGRATION"):
            assert marker in packet
        assert "H001_TEMPORAL_CAUSALITY_CURRENT_SIGNAL_RULE=FUNDING_TIME_LTE_DECISION" not in packet
        return
    if state["active_task"]["phase"] == context._H001_TEMPORAL_REVIEW_COMPLETE_PHASE:
        packet = render_context_packet(state)
        assert "H001_TEMPORAL_CAUSALITY_CANDIDATE_REVIEW=COMPLETED_PASSED" in packet
        assert "H001_TEMPORAL_CAUSALITY_ACTIVATION_EFFECTIVE=FALSE" in packet
        return
    assert state["active_task"]["phase"] == context._H001_TEMPORAL_CANDIDATE_PHASE
    packet = render_context_packet(state)
    for line in (
        "H001_TEMPORAL_CAUSALITY_AMENDMENT_CANDIDATE=IMPLEMENTED_FOR_REVIEW",
        "H001_TEMPORAL_CAUSALITY_AMENDMENT_CANDIDATE_REVIEW=REQUIRED_NOT_COMPLETED",
        "H001_TEMPORAL_CAUSALITY_CURRENT_CONTRACT=UNCHANGED",
        "H001_TEMPORAL_CAUSALITY_AMENDMENT_EFFECTIVE=FALSE",
        "H001_TEMPORAL_CAUSALITY_CURRENT_SIGNAL_RULE=FUNDING_TIME_LTE_DECISION",
        "H001_TEMPORAL_CAUSALITY_CANDIDATE_SIGNAL_RULE=FUNDING_TIME_LT_DECISION",
        "H001_TEMPORAL_CAUSALITY_EQUALITY_SIGNAL_EVENT=EXCLUDED_IN_CANDIDATE",
        "H001_TEMPORAL_CAUSALITY_HELD_FUNDING_RULE=UNCHANGED",
        "H001_REAL_DATA_ACCESS=FORBIDDEN", "H001_EXECUTION=0/0",
        "V0_AVAILABILITY=UNAVAILABLE", "H001_DURABLE_STORES_CONFIGURED=FALSE",
        "EDGE_UNPROVEN", "BLOCK_LIVE_INTEGRATION",
    ):
        assert line in packet


@pytest.mark.parametrize("mutate_receipt", [
    lambda r: r["evidence"].append(dict(r["evidence"][0])),
    lambda r: r["evidence"].append({"path": r["evidence"][0]["path"], "sha256": "0" * 64}),
    lambda r: r["evidence"].append({"path": "extra.txt", "sha256": EVIDENCE_SHA}),
    lambda r: r["evidence"].pop(),
    lambda r: r["evidence"][0].update(sha256="0" * 64),
    lambda r: r["evidence"][0].update(sha256="not-a-sha"),
    lambda r: r["evidence"][0].update(path="/absolute.txt"),
    lambda r: r["evidence"][0].update(path="../escape.txt"),
    lambda r: r["evidence"][0].update(path=123),
    lambda r: r["evidence"][0].update(unknown="key"),
    lambda r: r["evidence"][0].pop("sha256"),
])
def test_temporal_candidate_evidence_integrity_mutations_fail_closed(tmp_path, mutate_receipt):
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(_temporal_mutated_tree(tmp_path, mutate_receipt=mutate_receipt))


@pytest.mark.parametrize("relative_path", [
    "quantbot/experiment/h001_temporal_causality.py",
    "tests/experiment/test_h001_temporal_causality.py",
])
def test_temporal_candidate_literal_hash_bindings_reject_coordinated_evidence_mutation(tmp_path, relative_path):
    root = _temporal_mutated_tree(tmp_path)
    target = root / relative_path
    target.write_bytes(target.read_bytes() + b"\n# independent mutation probe\n")
    receipt_path = root / TASK_DIR / "handoff_v016.json"
    receipt = json.loads(receipt_path.read_bytes())
    context_entry = next(item for item in receipt["evidence"] if item["path"] == "quantbot/continuity/context.py")
    context_entry["sha256"] = hashlib.sha256((root / "quantbot/continuity/context.py").read_bytes()).hexdigest()
    continuity_tests_entry = next(item for item in receipt["evidence"] if item["path"] == "tests/continuity/test_cross_agent_continuity.py")
    continuity_tests_entry["sha256"] = hashlib.sha256((root / "tests/continuity/test_cross_agent_continuity.py").read_bytes()).hexdigest()
    entry = next(item for item in receipt["evidence"] if item["path"] == relative_path)
    entry["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    receipt_bytes = canonical_json_bytes(receipt)
    receipt_path.write_bytes(receipt_bytes)
    active_path = root / context.ACTIVE_TASK_RELPATH
    active = json.loads(active_path.read_bytes())
    active["handoff_receipt_path"] = "docs/control/tasks/RECOVER_OR_RETIRE_CANDIDATE1_V0_FROZEN_INPUT/handoff_v016.json"
    active["phase"] = context._H001_TEMPORAL_CANDIDATE_PHASE
    active["handoff_receipt_sha256"] = hashlib.sha256(receipt_bytes).hexdigest()
    active_path.write_bytes(canonical_json_bytes(active))
    with pytest.raises(ValueError, match="independent literal hash"):
        load_and_verify_continuity_state(root)


def test_production_temporal_candidate_rereview_completion_verifies_and_renders_boundary():
    state = context.load_and_verify_continuity_state(ROOT)
    if state["active_task"]["phase"] != context._H001_TEMPORAL_REVIEW_COMPLETE_PHASE:
        pytest.skip("production tree is not at the H001 temporal review-completion phase")
    packet = context.render_context_packet(state)
    for marker in (
        "H001_TEMPORAL_CAUSALITY_CANDIDATE_REVIEW=COMPLETED_PASSED",
        "H001_TEMPORAL_CAUSALITY_ACTIVATION_IMPLEMENTATION_FOR_REVIEW=AUTHORIZED",
        "H001_TEMPORAL_CAUSALITY_ACTIVATION_EFFECTIVE=FALSE",
        "H001_TEMPORAL_CAUSALITY_CURRENT_CONTRACT=UNCHANGED",
        "H001_TEMPORAL_CAUSALITY_CURRENT_SIGNAL_RULE=FUNDING_TIME_LTE_DECISION",
        "H001_TEMPORAL_CAUSALITY_CANDIDATE_SIGNAL_RULE=FUNDING_TIME_LT_DECISION",
        "H001_REAL_DATA_ACCESS=FORBIDDEN", "H001_EXECUTION=0/0", "V0_AVAILABILITY=UNAVAILABLE",
        "H001_DURABLE_STORES_CONFIGURED=FALSE", "EDGE_UNPROVEN", "BLOCK_LIVE_INTEGRATION",
    ):
        assert marker in packet


def test_temporal_review_completion_rejects_reordered_evidence_with_updated_pointer(tmp_path):
    root = tmp_path / "repo"
    copy_repo_without_runtime(ROOT, root)
    restore_historical_h001_inputs(root)
    receipt_path = root / TASK_DIR / "handoff_v017.json"
    receipt = json.loads(receipt_path.read_bytes())
    receipt["evidence"][0], receipt["evidence"][1] = receipt["evidence"][1], receipt["evidence"][0]
    receipt_bytes = canonical_json_bytes(receipt)
    receipt_path.write_bytes(receipt_bytes)
    active_path = root / context.ACTIVE_TASK_RELPATH
    active = json.loads(active_path.read_bytes())
    active["handoff_receipt_path"] = f"{TASK_DIR}/handoff_v017.json"
    active["phase"] = context._H001_TEMPORAL_REVIEW_COMPLETE_PHASE
    active["handoff_receipt_sha256"] = hashlib.sha256(receipt_bytes).hexdigest()
    active_path.write_bytes(canonical_json_bytes(active))
    with pytest.raises(ValueError, match="evidence list must be exact and ordered"):
        load_and_verify_continuity_state(root)


def test_temporal_review_completion_rejects_shortened_review_record_decision(tmp_path):
    root = tmp_path / "repo"
    copy_repo_without_runtime(ROOT, root)
    receipt_path = root / TASK_DIR / "handoff_v017.json"
    receipt = json.loads(receipt_path.read_bytes())
    receipt["decisions"].remove("H001_TEMPORAL_CAUSALITY_CANDIDATE_REVIEW_RECORD=RECORDED_AFTER_REVIEW_NOT_PREREGISTERED")
    receipt["decisions"].append("H001_CANDIDATE_REVIEW_RECORD=RECORDED_AFTER_REVIEW_NOT_PREREGISTERED")
    receipt_bytes = canonical_json_bytes(receipt)
    receipt_path.write_bytes(receipt_bytes)
    active_path = root / context.ACTIVE_TASK_RELPATH
    active = json.loads(active_path.read_bytes())
    active["handoff_receipt_sha256"] = hashlib.sha256(receipt_bytes).hexdigest()
    active_path.write_bytes(canonical_json_bytes(active))
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(root)


def _activation_mutated_tree(tmp_path, *, mutate_amendment=None, mutate_receipt=None, mutate_active=None):
    root = tmp_path / "repo"
    copy_repo_without_runtime(ROOT, root)
    active_path = root / context.ACTIVE_TASK_RELPATH
    active = json.loads(active_path.read_bytes())
    active.update(phase=context._H001_TEMPORAL_ACTIVE_PHASE, handoff_receipt_path=context._H001_TEMPORAL_ACTIVE_HANDOFF_RELPATH, handoff_receipt_sha256="5c84a84e858d70467e5f09d579bc1ec8a88fe9bd9ec1e922eefae36569d78f68")
    active_path.write_bytes(canonical_json_bytes(active))
    amendment_path = root / context._H001_TEMPORAL_ACTIVE_AMENDMENT_RELPATH
    receipt_path = root / context._H001_TEMPORAL_ACTIVE_HANDOFF_RELPATH
    if mutate_amendment is not None:
        amendment = json.loads(amendment_path.read_bytes())
        mutate_amendment(amendment)
        amendment_path.write_bytes(canonical_json_bytes(amendment))
        receipt = json.loads(receipt_path.read_bytes())
        for item in receipt["evidence"]:
            if item["path"] == context._H001_TEMPORAL_ACTIVE_AMENDMENT_RELPATH:
                item["sha256"] = hashlib.sha256(amendment_path.read_bytes()).hexdigest()
        receipt_path.write_bytes(canonical_json_bytes(receipt))
    if mutate_receipt is not None:
        receipt = json.loads(receipt_path.read_bytes())
        mutate_receipt(receipt)
        for item in receipt["evidence"]:
            if item["path"] in ("quantbot/continuity/context.py", "tests/continuity/test_cross_agent_continuity.py"):
                item["sha256"] = hashlib.sha256((root / item["path"]).read_bytes()).hexdigest()
        receipt_path.write_bytes(canonical_json_bytes(receipt))
    active = json.loads(active_path.read_bytes())
    original_active_sha = active["handoff_receipt_sha256"]
    if mutate_active is not None:
        mutate_active(active)
    if active["handoff_receipt_sha256"] == original_active_sha:
        active["handoff_receipt_sha256"] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    active_path.write_bytes(canonical_json_bytes(active))
    return root


def test_activation_production_state_renders_effective_strict_contract():
    state = load_and_verify_continuity_state(ROOT)
    if state["active_task"]["phase"] in (context._H001_CALIBRATION_GOVERNANCE_PHASE, context._H001_CALIBRATION_CANDIDATE_PHASE):
        pytest.skip("production tree has advanced past temporal activation")
    assert state["active_task"]["phase"] == context._H001_TEMPORAL_ACTIVE_PHASE
    assert state["handoff_receipt"]["receipt_index"] == 18
    assert state["handoff_receipt"]["changed_file_scope"] == context._H001_TEMPORAL_ACTIVE_SCOPE
    packet = render_context_packet(state)
    for marker in (
        "PHASE=candidate1_h001_temporal_causality_amendment_effective",
        "H001_TEMPORAL_CAUSALITY_AMENDMENT=EFFECTIVE",
        "H001_TEMPORAL_CAUSALITY_ACTIVATION_EFFECTIVE=TRUE",
        "H001_TEMPORAL_CAUSALITY_CURRENT_CONTRACT=STRICT_LT_EFFECTIVE",
        "H001_TEMPORAL_CAUSALITY_CURRENT_SIGNAL_RULE=FUNDING_TIME_LT_DECISION",
        "H001_TEMPORAL_CAUSALITY_EQUALITY_SIGNAL_EVENT=EXCLUDED",
        "H001_TEMPORAL_CAUSALITY_HELD_FUNDING_RULE=UNCHANGED",
        "H001_REAL_DATA_ACCESS=FORBIDDEN", "H001_EXECUTION=0/0",
        "H001_SYNTHETIC_NULL_CALIBRATION_SPEC_FREEZE=NOT_AUTHORIZED",
        "H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION=NOT_AUTHORIZED",
        "EDGE_UNPROVEN", "BLOCK_LIVE_INTEGRATION",
    ):
        assert marker in packet
    assert "H001_TEMPORAL_CAUSALITY_CURRENT_SIGNAL_RULE=FUNDING_TIME_LTE_DECISION" not in packet
    assert "reviewed H001 temporal causality amendment is not yet activated" not in packet


def test_activation_production_scope_is_exactly_nine_files_in_governance_order():
    state = load_and_verify_continuity_state(ROOT)
    if state["active_task"]["phase"] in (context._H001_CALIBRATION_GOVERNANCE_PHASE, context._H001_CALIBRATION_CANDIDATE_PHASE):
        pytest.skip("production tree has advanced past temporal activation")
    assert state["handoff_receipt"]["changed_file_scope"] == [
        "docs/control/amendments/candidate1_h001_temporal_causality_activation_v001.json",
        "docs/experiments/candidate1_h001_real_data_falsification_v0.json",
        "quantbot/experiment/h001_real_falsification_preregistration.py",
        "tests/experiment/test_h001_real_falsification_preregistration.py",
        f"docs/control/tasks/{TASK_ID}/handoff_v018.json",
        "docs/control/active_task.json",
        "quantbot/continuity/context.py",
        "tests/continuity/test_cross_agent_continuity.py",
        "tests/experiment/test_h001_temporal_causality.py",
    ]


@pytest.mark.parametrize("mutate, expected_error", [
    pytest.param(lambda r: r["changed_file_scope"].pop(), "H001 temporal activation changed_file_scope must be exact and ordered", id="eight-file-scope"),
    pytest.param(lambda r: r["changed_file_scope"].remove("tests/experiment/test_h001_temporal_causality.py"), "H001 temporal activation changed_file_scope must be exact and ordered", id="missing-temporal-test"),
    pytest.param(lambda r: r["changed_file_scope"].insert(0, r["changed_file_scope"].pop()), "H001 temporal activation changed_file_scope must be exact and ordered", id="temporal-test-wrong-position"),
    pytest.param(lambda r: r["changed_file_scope"].reverse(), "H001 temporal activation changed_file_scope must be exact and ordered", id="reversed-scope"),
    pytest.param(lambda r: r["changed_file_scope"].append("tests/experiment/test_h001_temporal_causality.py"), "H001 temporal activation changed_file_scope must be exact and ordered", id="duplicate-temporal-test"),
    pytest.param(lambda r: r["changed_file_scope"].append("docs/extra.md"), "H001 temporal activation changed_file_scope must be exact and ordered", id="extra-path"),
    pytest.param(lambda r: r["changed_file_scope"].__setitem__(-1, "docs/wrong.md"), "H001 temporal activation changed_file_scope must be exact and ordered", id="wrong-path"),
    pytest.param(lambda r: r["changed_file_scope"].__setitem__(-1, 123), "changed_file_scope entry must be a non-empty string", id="non-string-path"),
])
def test_activation_exact_scope_mutations_fail_at_scope_validation(tmp_path, mutate, expected_error):
    with pytest.raises(ValueError, match=expected_error):
        load_and_verify_continuity_state(_activation_mutated_tree(tmp_path, mutate_receipt=mutate))


@pytest.mark.parametrize("mutate", [
    lambda a: a.update(effective=False),
    lambda a: a.update(current_contract_changed=False),
    lambda a: a["hash_bindings"]["reviewed_candidate_design"].update(sha256="0" * 64),
    lambda a: a["review_history"].update(pr_285_merge_commit="0" * 40),
    lambda a: a["non_effects"].remove("REAL_DATA_ACCESS_FORBIDDEN"),
    lambda a: a.update(extra_key=True),
])
def test_activation_amendment_mutations_fail_closed(tmp_path, mutate):
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(_activation_mutated_tree(tmp_path, mutate_amendment=mutate))


def test_activation_amendment_duplicate_and_noncanonical_json_fail_closed(tmp_path):
    root = tmp_path / "repo"
    copy_repo_without_runtime(ROOT, root)
    path = root / context._H001_TEMPORAL_ACTIVE_AMENDMENT_RELPATH
    raw = path.read_bytes()
    path.write_bytes(raw.replace(b'"effective":true,', b'"effective":true,"effective":true,', 1))
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(root)
    path.write_bytes(raw + b"\n")
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(root)


@pytest.mark.parametrize("mutate", [
    lambda r: r.update(receipt_index=17),
    lambda r: r.update(predecessor={"path": r["predecessor"]["path"], "sha256": "0" * 64}),
    lambda r: r["changed_file_scope"].reverse(),
    lambda r: r["evidence"].reverse(),
    lambda r: r["evidence"].append(dict(r["evidence"][0])),
    lambda r: r["evidence"].pop(),
    lambda r: r["decisions"].append("H001_TEMPORAL_CAUSALITY_ACTIVATION_EFFECTIVE=FALSE"),
    lambda r: r["safety_state"].update(decomposition_execution_count=1),
])
def test_activation_handoff_mutations_fail_closed(tmp_path, mutate):
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(_activation_mutated_tree(tmp_path, mutate_receipt=mutate))


@pytest.mark.parametrize("mutate", [
    lambda a: a.update(handoff_receipt_path=context._H001_TEMPORAL_ACTIVE_HANDOFF_RELPATH.replace("v018", "v017")),
    lambda a: a.update(handoff_receipt_sha256="0" * 64),
    lambda a: a.update(phase=context._H001_TEMPORAL_REVIEW_COMPLETE_PHASE),
])
def test_activation_active_task_mutations_fail_closed(tmp_path, mutate):
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(_activation_mutated_tree(tmp_path, mutate_active=mutate))


def _calibration_governance_mutated_tree(tmp_path, *, mutate_amendment=None, mutate_receipt=None, mutate_active=None, mutate_draft=None):
    root = tmp_path / "repo"
    copy_repo_without_runtime(ROOT, root)
    amendment_path = root / context._H001_CALIBRATION_GOVERNANCE_AMENDMENT_RELPATH
    amendment = json.loads(amendment_path.read_bytes())
    if mutate_amendment:
        mutate_amendment(amendment)
    amendment_path.write_bytes(canonical_json_bytes(amendment))
    if mutate_draft:
        draft_path = root / "docs/assurance/h001_synthetic_null_calibration_spec_draft_v001.json"
        draft = json.loads(draft_path.read_bytes())
        mutate_draft(draft)
        draft_path.write_bytes(canonical_json_bytes(draft))
    # Mutate whichever receipt is currently active, so these governance-derived
    # mutations stay meaningful after the tree advances to a later phase.
    active_path = root / context.ACTIVE_TASK_RELPATH
    receipt_path = root / json.loads(active_path.read_bytes())["handoff_receipt_path"]
    receipt = json.loads(receipt_path.read_bytes())
    if mutate_receipt:
        mutate_receipt(receipt)
    for item in receipt["evidence"]:
        target = root / item["path"]
        if target.is_file():
            item["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    receipt_path.write_bytes(canonical_json_bytes(receipt))
    active = json.loads(active_path.read_bytes())
    if mutate_active:
        mutate_active(active)
    active["handoff_receipt_sha256"] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    active_path.write_bytes(canonical_json_bytes(active))
    return root


def test_calibration_governance_production_state_renders_authorized_but_unfrozen():
    state = load_and_verify_continuity_state(ROOT)
    if state["active_task"]["phase"] == context._H001_CALIBRATION_CANDIDATE_PHASE:
        pytest.skip("production tree has advanced to the freeze-candidate review phase")
    assert state["active_task"]["phase"] == context._H001_CALIBRATION_GOVERNANCE_PHASE
    assert state["handoff_receipt"]["receipt_index"] == 19
    packet = render_context_packet(state)
    for marker in (
        "PHASE=candidate1_h001_synthetic_null_calibration_spec_freeze_governance",
        "NEXT_ACTION=IMPLEMENT_H001_SYNTHETIC_NULL_CALIBRATION_SPEC_FREEZE_CANDIDATE_FOR_INDEPENDENT_REVIEW",
        "H001_SYNTHETIC_NULL_CALIBRATION_SPEC_FREEZE_GOVERNANCE=AUTHORIZED",
        "H001_SYNTHETIC_NULL_CALIBRATION_SPEC_FREEZE=NOT_EFFECTIVE",
        "H001_SYNTHETIC_NULL_CALIBRATION_SPEC_STATUS=HISTORICAL_DRAFT_UNFROZEN",
        "H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION=NOT_AUTHORIZED",
        "H001_SYNTHETIC_NULL_CALIBRATION_RESULTS=NONE",
        "H001_TEMPORAL_CAUSALITY_ACTIVATION_EFFECTIVE=TRUE",
        "H001_TEMPORAL_CAUSALITY_CURRENT_CONTRACT=STRICT_LT_EFFECTIVE",
        "H001_TEMPORAL_CAUSALITY_CURRENT_SIGNAL_RULE=FUNDING_TIME_LT_DECISION",
        "H001_REAL_DATA_ACCESS=FORBIDDEN", "H001_EXECUTION=0/0", "EDGE_UNPROVEN", "BLOCK_LIVE_INTEGRATION",
    ):
        assert marker in packet


@pytest.mark.parametrize("mutate", [
    lambda a: a.update(freeze_effective=True),
    lambda a: a.update(historical_draft_is_executable=True),
    lambda a: a["transition_gates"].update(synthetic_null_calibration_spec_frozen=True),
    lambda a: a["transition_gates"].update(calibration_execution_authorized=True),
    lambda a: a.update(calibration_results="available"),
    lambda a: a.update(real_data_access="authorized"),
    lambda a: a["transition_gates"].update(h001_execution_budget=1),
    lambda a: a["transition_gates"].update(h001_execution_count=1),
    lambda a: a.update(scientific_authorization=True),
    lambda a: a.update(paper_trade_authorization=True),
    lambda a: a.update(live_authorization=True),
    lambda a: a.update(edge_status="EDGE_PROVEN"),
    lambda a: a.update(live_status="READY"),
    lambda a: a["activated_design"].update(sha256="0" * 64),
    lambda a: a["historical_draft"].update(current_design_sha256=context._H001_CALIBRATION_GOVERNANCE_DESIGN_SHA),
    lambda a: a["activated_validator"].update(sha256="0" * 64),
    lambda a: a["historical_draft"].update(current_validator_sha256=context._H001_CALIBRATION_GOVERNANCE_VALIDATOR_SHA),
    lambda a: a["temporal_activation_amendment"].update(sha256="0" * 64),
    lambda a: a.update(later_freeze_candidate_requires_independent_review=False),
    lambda a: a["allowed_actions"].append("EXECUTE_SYNTHETIC_NULL_CALIBRATION"),
    lambda a: a["prohibited_actions"].remove("TUNE_HAC_LAG_FROM_RESULTS"),
    lambda a: a["transition_gates"].update(activated_design_binding_verified=False),
])
def test_calibration_governance_amendment_mutations_fail_closed(tmp_path, mutate):
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(_calibration_governance_mutated_tree(tmp_path, mutate_amendment=mutate))


@pytest.mark.parametrize("mutate", [
    lambda r: r.update(receipt_index=18),
    lambda r: r["predecessor"].update(sha256="0" * 64),
    lambda r: r["changed_file_scope"].reverse(),
    lambda r: r["changed_file_scope"].pop(),
    lambda r: r["changed_file_scope"].append("docs/extra.md"),
    lambda r: r["evidence"].reverse(),
    lambda r: r["evidence"].append(dict(r["evidence"][0])),
    lambda r: r["decisions"].append("EDGE_PROVEN"),
    lambda r: r["safety_state"].update(decomposition_execution_count=1),
])
def test_calibration_governance_receipt_mutations_fail_closed(tmp_path, mutate):
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(_calibration_governance_mutated_tree(tmp_path, mutate_receipt=mutate))


def test_calibration_governance_historical_draft_mutation_fails_closed(tmp_path):
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(_calibration_governance_mutated_tree(tmp_path, mutate_draft=lambda d: d.update(status="FROZEN")))


# --- H001 calibration spec freeze candidate (review required) ----------------

CANDIDATE_RELPATH = context._H001_CALIBRATION_CANDIDATE_RELPATH
HISTORICAL_DRAFT_RELPATH = "docs/assurance/h001_synthetic_null_calibration_spec_draft_v001.json"


def _calibration_candidate_mutated_tree(
    tmp_path, *, mutate_candidate=None, mutate_receipt=None, mutate_active=None,
    mutate_draft=None, mutate_validator=None,
):
    """Build a mutated tree and then refresh every dependent hash.

    Refreshing matters: without it a mutation would fail merely because a
    recorded digest went stale. Here the receipt's evidence and the active-task
    pointer are recomputed from the mutated files, so the only thing left to
    fail is the semantic invariant under test.
    """
    root = tmp_path / "repo"
    copy_repo_without_runtime(ROOT, root)
    if mutate_candidate:
        path = root / CANDIDATE_RELPATH
        value = json.loads(path.read_bytes())
        mutate_candidate(value)
        path.write_bytes(canonical_json_bytes(value))
    if mutate_draft:
        path = root / HISTORICAL_DRAFT_RELPATH
        value = json.loads(path.read_bytes())
        mutate_draft(value)
        path.write_bytes(canonical_json_bytes(value))
    if mutate_validator:
        path = root / context._H001_VALIDATOR_RELPATH
        path.write_bytes(mutate_validator(path.read_bytes()))
    receipt_path = root / context._H001_CALIBRATION_CANDIDATE_HANDOFF_RELPATH
    receipt = json.loads(receipt_path.read_bytes())
    if mutate_receipt:
        mutate_receipt(receipt)
    for item in receipt["evidence"]:
        target = root / item["path"]
        if target.is_file():
            item["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    receipt_path.write_bytes(canonical_json_bytes(receipt))
    active_path = root / context.ACTIVE_TASK_RELPATH
    active = json.loads(active_path.read_bytes())
    if mutate_active:
        mutate_active(active)
    active["handoff_receipt_sha256"] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    active_path.write_bytes(canonical_json_bytes(active))
    return root


def test_calibration_candidate_production_state_renders_review_required():
    state = load_and_verify_continuity_state(ROOT)
    assert state["active_task"]["phase"] == context._H001_CALIBRATION_CANDIDATE_PHASE
    assert state["handoff_receipt"]["receipt_index"] == 20
    packet = render_context_packet(state)
    for marker in (
        "PHASE=candidate1_h001_synthetic_null_calibration_spec_freeze_candidate_review_required",
        "NEXT_ACTION=ADVERSARIAL_REVIEW_H001_SYNTHETIC_NULL_CALIBRATION_SPEC_FREEZE_CANDIDATE",
        "H001_SYNTHETIC_NULL_CALIBRATION_SPEC_FREEZE_CANDIDATE=IMPLEMENTED",
        "H001_SYNTHETIC_NULL_CALIBRATION_SPEC_FREEZE_CANDIDATE_VALUES=LOCKED_FOR_REVIEW",
        "H001_SYNTHETIC_NULL_CALIBRATION_SPEC_FREEZE_CANDIDATE_REVIEW=REQUIRED",
        "H001_SYNTHETIC_NULL_CALIBRATION_SPEC_FREEZE=NOT_EFFECTIVE",
        "H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION=NOT_AUTHORIZED",
        "H001_SYNTHETIC_NULL_CALIBRATION_RESULTS=NONE",
        "H001_TEMPORAL_CAUSALITY_ACTIVATION_EFFECTIVE=TRUE",
        "H001_TEMPORAL_CAUSALITY_CURRENT_CONTRACT=STRICT_LT_EFFECTIVE",
        "H001_TEMPORAL_CAUSALITY_CURRENT_SIGNAL_RULE=FUNDING_TIME_LT_DECISION",
        "H001_REAL_DATA_ACCESS=FORBIDDEN",
        "H001_EXECUTION=0/0",
        "H001_CURRENT_EXECUTION_BUDGET=0",
        "H001_CURRENT_EXECUTION_COUNT=0",
        "V0_AVAILABILITY=UNAVAILABLE",
        "H001_DURABLE_STORES_CONFIGURED=FALSE",
        "H001_SCIENTIFIC_AUTHORIZATION=FALSE",
        "H001_PAPER_TRADE_AUTHORIZATION=FALSE",
        "H001_LIVE_AUTHORIZATION=FALSE",
        "EDGE_UNPROVEN",
        "BLOCK_LIVE_INTEGRATION",
    ):
        assert marker in packet
    # EDGE_PROVEN may appear only as a prohibition, never as a rendered claim.
    assert "PROHIBITED=EDGE_PROVEN" in packet
    assert "EDGE_STATUS=EDGE_PROVEN" not in packet
    assert [line for line in packet.splitlines() if line == "EDGE_PROVEN"] == []
    assert "H001_SYNTHETIC_NULL_CALIBRATION_SPEC_FREEZE=EFFECTIVE" not in packet
    assert "H001_SYNTHETIC_NULL_CALIBRATION_RESULTS=AVAILABLE" not in packet


def test_calibration_candidate_blockers_are_carried_forward_unweakened():
    state = load_and_verify_continuity_state(ROOT)
    assert set(state["handoff_receipt"]["blockers"]) == {
        "V0 remains unavailable",
        "durable stores remain unconfigured",
        "real data access remains forbidden",
        "H001 calibration specification remains unfrozen",
        "H001 synthetic calibration execution remains unauthorized",
        "EDGE_UNPROVEN",
        "BLOCK_LIVE_INTEGRATION",
    }


def test_calibration_candidate_production_scope_is_exactly_nine_files_in_order():
    state = load_and_verify_continuity_state(ROOT)
    assert state["handoff_receipt"]["changed_file_scope"] == [
        "docs/assurance/h001_synthetic_null_calibration_spec_freeze_candidate_v001.json",
        "quantbot/assurance/contracts.py",
        "quantbot/assurance/h001_null_calibration.py",
        "tests/assurance/test_contracts.py",
        "tests/assurance/test_h001_null_calibration.py",
        f"docs/control/tasks/{TASK_ID}/handoff_v020.json",
        "docs/control/active_task.json",
        "quantbot/continuity/context.py",
        "tests/continuity/test_cross_agent_continuity.py",
    ]
    assert len(state["handoff_receipt"]["changed_file_scope"]) == 9


def test_calibration_candidate_evidence_is_exact_unique_and_hash_bound():
    state = load_and_verify_continuity_state(ROOT)
    evidence = state["handoff_receipt"]["evidence"]
    paths = [item["path"] for item in evidence]
    assert paths == context._H001_CALIBRATION_CANDIDATE_EVIDENCE
    assert len(paths) == len(set(paths))
    for item in evidence:
        assert hashlib.sha256((ROOT / item["path"]).read_bytes()).hexdigest() == item["sha256"]
    for required in (
        CANDIDATE_RELPATH,
        context._H001_CALIBRATION_GOVERNANCE_AMENDMENT_RELPATH,
        f"docs/control/tasks/{TASK_ID}/handoff_v019.json",
        HISTORICAL_DRAFT_RELPATH,
        "docs/experiments/candidate1_h001_real_data_falsification_v0.json",
        "quantbot/experiment/h001_real_falsification_preregistration.py",
        context._H001_TEMPORAL_ACTIVE_AMENDMENT_RELPATH,
        "quantbot/assurance/contracts.py",
        "quantbot/assurance/h001_null_calibration.py",
        "tests/assurance/test_contracts.py",
        "tests/assurance/test_h001_null_calibration.py",
        "quantbot/continuity/context.py",
        "tests/continuity/test_cross_agent_continuity.py",
        "docs/artifacts/candidate1-real-input-v0.json",
        context.STORE_REGISTRY_RELPATH,
    ):
        assert required in paths


def test_calibration_candidate_predecessor_binds_v019_exactly():
    state = load_and_verify_continuity_state(ROOT)
    assert state["handoff_receipt"]["predecessor"] == {
        "path": f"docs/control/tasks/{TASK_ID}/handoff_v019.json",
        "sha256": "5f210c26c6c7f0b16f1df49173cae22e878071fe46d9933941d639aa37f6d59e",
    }
    assert state["handoff_receipt"]["source_head_commit"] == "6465d036af6b66ae6d845511c652d5857651bc49"
    assert state["handoff_receipt"]["source_branch"] == "feat/h001-calibration-spec-freeze-candidate"


CANDIDATE_DOCUMENT_MUTATIONS = {
    "marked_effective": lambda c: c["authorization_state"].update(specification_effective=True),
    "marked_frozen_effective": lambda c: c["authorization_state"].update(specification_frozen_effective=True),
    "review_removed": lambda c: c["authorization_state"].update(independent_review_required=False),
    "values_unlocked": lambda c: c["authorization_state"].update(candidate_values_locked_for_review=False),
    "execution_authorized": lambda c: c["authorization_state"].update(execution_authorized=True),
    "results_exposed": lambda c: c["authorization_state"].update(results_exposed=True),
    "real_data_authority": lambda c: c["authorization_state"].update(real_data_access_authorized=True),
    "h001_execution_authority": lambda c: c["authorization_state"].update(h001_validation_execution_authorized=True),
    "holdout_authority": lambda c: c["authorization_state"].update(h001_holdout_execution_authorized=True),
    "scientific_authority": lambda c: c["authorization_state"].update(scientific_authorization=True),
    "paper_authority": lambda c: c["authorization_state"].update(paper_trade_authorization=True),
    "live_authority": lambda c: c["authorization_state"].update(live_authorization=True),
    "edge_proven": lambda c: c.update(edge_status="EDGE_PROVEN"),
    "block_live_removed": lambda c: c.update(live_status="READY"),
    "wrong_governance_amendment": lambda c: c["bindings"]["governance_amendment"].update(sha256="0" * 64),
    "wrong_v019_predecessor": lambda c: c["bindings"]["source_handoff"].update(sha256="0" * 64),
    "wrong_activated_design": lambda c: c["bindings"]["activated_design"].update(sha256="0" * 64),
    "wrong_activated_validator": lambda c: c["bindings"]["activated_validator"].update(sha256="0" * 64),
    "historical_design_promoted": lambda c: c["bindings"]["activated_design"].update(sha256=context._H001_TEMPORAL_ACTIVE_HISTORICAL_DESIGN_SHA),
    "historical_validator_promoted": lambda c: c["bindings"]["activated_validator"].update(sha256=context._H001_TEMPORAL_ACTIVE_HISTORICAL_VALIDATOR_SHA),
    "historical_draft_claimed_current": lambda c: c["historical_draft"].update(is_current=True),
    "historical_draft_frozen": lambda c: c["historical_draft"].update(is_frozen=True),
    "wrong_source_main": lambda c: c["bindings"].update(source_main_commit="0" * 40),
    "wrong_seed_domain": lambda c: c["seed_contract"].update(seed_domain="h001-null-calibration/other/synthetic-only"),
    "dgp_definition": lambda c: c["required_stationary_dgps"][3].update(definition="a different exact-looking AR process with changed semantics and no shared contract"),
    "dgp_innovation_distribution": lambda c: c["required_stationary_dgps"][3].update(innovation_distribution="serially dependent innovations"),
    "dgp_initial_state_distribution": lambda c: c["required_stationary_dgps"][3].update(initial_state_distribution="deterministic zero initial states"),
    "dgp_cross_series_dependence": lambda c: c["required_stationary_dgps"][3].update(cross_series_dependence="all series share one innovation stream"),
    "dgp_temporal_independence": lambda c: c["required_stationary_dgps"][3].update(temporal_independence="innovations may be serially dependent"),
    "dgp_output_shape": lambda c: c["required_stationary_dgps"][3].update(output_shape_and_ordering="array with shape [1, 1]"),
    "dgp_axis_ordering": lambda c: c["required_stationary_dgps"][3].update(output_shape_and_ordering="[9, 2193] with interval axis before series axis"),
    "dgp_finite_value_requirement": lambda c: c["required_stationary_dgps"][3].update(finite_value_requirement="non-finite values are permitted"),
    "dgp_burn_in": lambda c: c["required_stationary_dgps"][3].update(burn_in_intervals=1),
    "dgp_discarded_observations": lambda c: c["required_stationary_dgps"][3].update(discarded_observations=1),
    "ar_innovation_independence": lambda c: c["required_stationary_dgps"][4].update(temporal_independence="shared serial innovations"),
    "garch_initialization": lambda c: c["required_stationary_dgps"][5].update(initial_state_distribution="exact invariant draw"),
    "garch_burn_in": lambda c: c["required_stationary_dgps"][5].update(burn_in_intervals=9999),
    "garch_retained_range": lambda c: c["required_stationary_dgps"][5]["parameters"].update(retained_index_range="0..2192"),
    "sample_first_timestamp": lambda c: c["synthetic_sample_contract"].update(first_interval_open_utc="2023-01-01T08:00:00Z"),
    "sample_last_open_timestamp": lambda c: c["synthetic_sample_contract"].update(last_interval_open_utc="2024-12-31T08:00:00Z"),
    "sample_exclusive_end": lambda c: c["synthetic_sample_contract"].update(exclusive_region_end_utc="2024-12-31T23:59:59Z"),
    "sample_interval_duration": lambda c: c["synthetic_sample_contract"].update(interval_duration_seconds=3600),
    "sample_length_formula": lambda c: c["synthetic_sample_contract"].update(sample_length_formula="2192"),
    "sample_output_shape": lambda c: c["synthetic_sample_contract"].update(output_shape_and_ordering="[9, 2192]"),
    "component_id_removed": lambda c: c["seed_contract"]["component_streams"]["iid_gaussian"].pop(),
    "component_id_renamed": lambda c: c["seed_contract"]["component_streams"]["iid_gaussian"].__setitem__(0, "series-0-other"),
    "component_id_added": lambda c: c["seed_contract"]["component_streams"]["iid_gaussian"].append("series-9-observations"),
    "component_payload_changed": lambda c: c["seed_contract"].update(component_payload_rule="use a shared seed"),
    "bootstrap_payload_changed": lambda c: c["seed_contract"].update(bootstrap_payload_rule="use one shared bootstrap stream"),
    "generator_sharing_enabled": lambda c: c["seed_contract"].update(stream_isolation_rule="share one mutable generator"),
    "draw_ordering_changed": lambda c: c["seed_contract"].update(draw_ordering_rule="iterate through an unordered set"),
    "unordered_traversal_allowed": lambda c: c["seed_contract"]["forbidden_randomness"].remove("unordered traversal"),
    "diagnostic_definition": lambda c: c["diagnostic_stress_cases"][0].update(definition="a different structural break definition"),
    "diagnostic_initialization": lambda c: c["diagnostic_stress_cases"][0].update(initial_state_distribution="deterministic zero"),
    "diagnostic_dependence": lambda c: c["diagnostic_stress_cases"][0].update(nine_series_construction="all series share one stream"),
    "diagnostic_output_shape": lambda c: c["diagnostic_stress_cases"][0].update(output_shape_and_ordering="shape [1, 1]"),
    "diagnostic_seed_assignment": lambda c: c["diagnostic_stress_cases"][0].update(seed_use="use wall-clock time"),
    "wrong_hac_lag": lambda c: c["registered_test_target"].update(hac_lag=22),
    "wrong_block_length": lambda c: c["registered_test_target"].update(stationary_block_length=64),
    "wrong_alpha": lambda c: c["registered_test_target"].update(familywise_alpha=0.1),
    "wrong_outer_replications": lambda c: c["registered_test_target"].update(outer_synthetic_replications=500),
    "wrong_pass_threshold": lambda c: c["pass_criterion"].update(fwer_upper_bound_threshold=0.2),
    "diagnostics_in_pass_fail": lambda c: c["pass_criterion"].update(diagnostic_cases_participate=True),
}


@pytest.mark.parametrize("name", sorted(CANDIDATE_DOCUMENT_MUTATIONS))
def test_calibration_candidate_document_mutations_fail_closed(tmp_path, name):
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(
            _calibration_candidate_mutated_tree(tmp_path, mutate_candidate=CANDIDATE_DOCUMENT_MUTATIONS[name])
        )


CANDIDATE_RECEIPT_MUTATIONS = {
    "wrong_receipt_index": lambda r: r.update(receipt_index=19),
    "wrong_predecessor_sha": lambda r: r["predecessor"].update(sha256="0" * 64),
    "wrong_predecessor_path": lambda r: r["predecessor"].update(path=f"docs/control/tasks/{TASK_ID}/handoff_v018.json"),
    "wrong_source_head": lambda r: r.update(source_head_commit="0" * 40),
    "wrong_branch": lambda r: r.update(source_branch="main"),
    "wrong_next_action": lambda r: r.update(next_actions=["FREEZE_H001_SYNTHETIC_NULL_CALIBRATION_SPEC"]),
    "extra_next_action": lambda r: r["next_actions"].append("EXECUTE_CALIBRATION"),
    "scope_reordered": lambda r: r["changed_file_scope"].reverse(),
    "scope_missing": lambda r: r["changed_file_scope"].pop(),
    "scope_extra": lambda r: r["changed_file_scope"].append("docs/extra.md"),
    "scope_duplicated": lambda r: r["changed_file_scope"].append(r["changed_file_scope"][0]),
    "evidence_reordered": lambda r: r["evidence"].reverse(),
    "evidence_missing": lambda r: r["evidence"].pop(),
    "evidence_extra": lambda r: r["evidence"].append({"path": "docs/extra.md", "sha256": "0" * 64}),
    "evidence_duplicated": lambda r: r["evidence"].append(dict(r["evidence"][0])),
    "edge_proven_decision": lambda r: r["decisions"].append("EDGE_PROVEN"),
    "freeze_effective_decision": lambda r: r["decisions"].__setitem__(13, "H001_SYNTHETIC_NULL_CALIBRATION_SPEC_FREEZE=EFFECTIVE"),
    "review_not_required_decision": lambda r: r["decisions"].__setitem__(15, "H001_SYNTHETIC_NULL_CALIBRATION_SPEC_FREEZE_CANDIDATE_REVIEW=COMPLETED"),
    "execution_budget_drift": lambda r: r["decisions"].__setitem__(3, "H001_CURRENT_EXECUTION_BUDGET=1"),
    "execution_count_drift": lambda r: r["decisions"].__setitem__(4, "H001_CURRENT_EXECUTION_COUNT=1"),
    "decisions_duplicated": lambda r: r["decisions"].append(r["decisions"][0]),
    "blocker_removed_unfrozen": lambda r: r["blockers"].remove("H001 calibration specification remains unfrozen"),
    "blocker_removed_edge": lambda r: r["blockers"].remove("EDGE_UNPROVEN"),
    "blocker_removed_live": lambda r: r["blockers"].remove("BLOCK_LIVE_INTEGRATION"),
    "safety_execution_count": lambda r: r["safety_state"].update(decomposition_execution_count=1),
    "safety_scientific": lambda r: r["safety_state"].update(scientific_use_authorized=True),
    "safety_paper": lambda r: r["safety_state"].update(paper_trade_authorized=True),
    "safety_live": lambda r: r["safety_state"].update(live_integration_authorized=True),
    "safety_real_data": lambda r: r["safety_state"].update(real_data_execution_requested=True),
    "prohibition_removed": lambda r: r["prohibited_actions"].remove("EXECUTE_H001"),
}


@pytest.mark.parametrize("name", sorted(CANDIDATE_RECEIPT_MUTATIONS))
def test_calibration_candidate_receipt_mutations_fail_closed(tmp_path, name):
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(
            _calibration_candidate_mutated_tree(tmp_path, mutate_receipt=CANDIDATE_RECEIPT_MUTATIONS[name])
        )


@pytest.mark.parametrize("mutate", [
    lambda a: a.update(phase=context._H001_CALIBRATION_GOVERNANCE_PHASE),
    lambda a: a.update(phase="candidate1_h001_synthetic_null_calibration_spec_frozen_effective"),
    lambda a: a.update(handoff_receipt_path=f"docs/control/tasks/{TASK_ID}/handoff_v019.json"),
    lambda a: a.update(task_id="OTHER_TASK"),
    lambda a: a.update(protocol_id="other_protocol"),
])
def test_calibration_candidate_active_task_mutations_fail_closed(tmp_path, mutate):
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(_calibration_candidate_mutated_tree(tmp_path, mutate_active=mutate))


def test_calibration_candidate_active_task_pointer_drift_fails_closed(tmp_path):
    root = _calibration_candidate_mutated_tree(tmp_path)
    active_path = root / context.ACTIVE_TASK_RELPATH
    active = json.loads(active_path.read_bytes())
    active["handoff_receipt_sha256"] = "0" * 64
    active_path.write_bytes(canonical_json_bytes(active))
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(root)


@pytest.mark.parametrize("mutate", [
    lambda d: d.update(status="FROZEN_EFFECTIVE"),
    lambda d: d.update(proposed_outer_replications=1),
    lambda d: d["hash_bindings"].update(current_design_sha256=context._H001_CALIBRATION_GOVERNANCE_DESIGN_SHA),
])
def test_calibration_candidate_historical_draft_changes_fail_closed(tmp_path, mutate):
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(_calibration_candidate_mutated_tree(tmp_path, mutate_draft=mutate))


@pytest.mark.parametrize("mutate_validator", [
    lambda raw: raw.replace(b"latest funding_time_utc < bar[t].open_time_utc", b"latest funding_time_utc <= bar[t].open_time_utc", 1),
    lambda raw: raw.replace(b"bar[t].open_time_utc < funding_time_utc <= bar[t].close_time_utc", b"bar[t].open_time_utc <= funding_time_utc <= bar[t].close_time_utc", 1),
])
def test_calibration_candidate_temporal_contract_reversion_fails_closed(tmp_path, mutate_validator):
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(_calibration_candidate_mutated_tree(tmp_path, mutate_validator=mutate_validator))


def test_calibration_candidate_unmutated_tree_still_verifies(tmp_path):
    """Control: the copy helper alone must not break verification, otherwise
    every mutation test above would pass for the wrong reason."""
    state = load_and_verify_continuity_state(_calibration_candidate_mutated_tree(tmp_path))
    assert state["active_task"]["phase"] == context._H001_CALIBRATION_CANDIDATE_PHASE
    assert state["handoff_receipt"]["receipt_index"] == 20
