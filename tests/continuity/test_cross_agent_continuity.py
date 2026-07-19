"""Synthetic fail-closed tests for the cross-agent continuity control plane.

No real data, no protocol execution: every tree is built from scratch in
tmp_path, plus read-only validation of the committed production control state.
"""

import ast
import base64
import copy
import hashlib
import json
import re
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
    assert receipt["next_actions"] in (["IMPLEMENT_DURABLE_ARTIFACT_PLANE"], ["CONFIGURE_TWO_DURABLE_ARTIFACT_STORES"], ["IMPLEMENT_CANDIDATE1_V1_SYNTHETIC_SANDBOX_SCAFFOLD"], ["RUN_CANDIDATE1_V1_SYNTHETIC_STRATEGY_BATCH"], [context._H001_COMPLETE_NEXT_ACTION], [context._H001_DESIGN_NEXT_ACTION], [context._H001_PREREGISTERED_NEXT_ACTION], [context._H001_REVIEW_COMPLETE_NEXT_ACTION], [context._H001_PRE_DATA_NEXT_ACTION], [context._H001_SCAFFOLD_NEXT_ACTION], [context._H001_ASSURANCE_REVIEW_NEXT_ACTION], [context._H001_TEMPORAL_CANDIDATE_NEXT_ACTION], [context._H001_TEMPORAL_REVIEW_COMPLETE_NEXT_ACTION], [context._H001_TEMPORAL_ACTIVE_NEXT_ACTION], [context._H001_CALIBRATION_GOVERNANCE_NEXT_ACTION], [context._H001_CALIBRATION_CANDIDATE_NEXT_ACTION], [context._H001_CALIBRATION_REREVIEW_NEXT_ACTION], [context._H001_CALIBRATION_EFFECTIVE_NEXT_ACTION], [context._H001_CALIBRATION_EXECUTION_GOVERNANCE_NEXT_ACTION], [context._H001_CALIBRATION_IMPLEMENTATION_BLOCKED_NEXT_ACTION])
    packet = render_context_packet(state)
    assert "PROTOCOL_EXECUTION=BLOCKED" in packet
    assert "availability=UNAVAILABLE" in packet
    assert state["active_task"]["phase"] in (context._H001_COMPLETE_PHASE, context._H001_DESIGN_PHASE, context._H001_PREREGISTERED_PHASE, context._H001_REVIEW_COMPLETE_PHASE, context._H001_PRE_DATA_PHASE, context._H001_SCAFFOLD_PHASE, context._H001_ASSURANCE_REVIEW_COMPLETE_PHASE, context._H001_TEMPORAL_CANDIDATE_PHASE, context._H001_TEMPORAL_REVIEW_COMPLETE_PHASE, context._H001_TEMPORAL_ACTIVE_PHASE, context._H001_CALIBRATION_GOVERNANCE_PHASE, context._H001_CALIBRATION_CANDIDATE_PHASE, context._H001_CALIBRATION_REREVIEW_PHASE, context._H001_CALIBRATION_EFFECTIVE_PHASE, context._H001_CALIBRATION_EXECUTION_GOVERNANCE_PHASE, context._H001_CALIBRATION_IMPLEMENTATION_BLOCKED_PHASE)


def test_h001_completion_phase_verifies_and_renders_boundaries():
    state = load_and_verify_continuity_state(ROOT)
    if state["active_task"]["phase"] in (context._H001_DESIGN_PHASE, context._H001_PREREGISTERED_PHASE, context._H001_REVIEW_COMPLETE_PHASE, context._H001_PRE_DATA_PHASE, context._H001_SCAFFOLD_PHASE, context._H001_ASSURANCE_REVIEW_COMPLETE_PHASE, context._H001_TEMPORAL_CANDIDATE_PHASE, context._H001_TEMPORAL_REVIEW_COMPLETE_PHASE, context._H001_TEMPORAL_ACTIVE_PHASE, context._H001_CALIBRATION_GOVERNANCE_PHASE, context._H001_CALIBRATION_CANDIDATE_PHASE, context._H001_CALIBRATION_REREVIEW_PHASE, context._H001_CALIBRATION_EFFECTIVE_PHASE, context._H001_CALIBRATION_EXECUTION_GOVERNANCE_PHASE, context._H001_CALIBRATION_IMPLEMENTATION_BLOCKED_PHASE):
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
    if state["active_task"]["phase"] in (context._H001_TEMPORAL_ACTIVE_PHASE, context._H001_CALIBRATION_GOVERNANCE_PHASE, context._H001_CALIBRATION_CANDIDATE_PHASE, context._H001_CALIBRATION_REREVIEW_PHASE, context._H001_CALIBRATION_EFFECTIVE_PHASE, context._H001_CALIBRATION_EXECUTION_GOVERNANCE_PHASE, context._H001_CALIBRATION_IMPLEMENTATION_BLOCKED_PHASE):
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


def _rereview_fixture(tmp_path):
    root = tmp_path / "rereview"
    shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__"))
    return root


def _rewrite_rereview_receipt(root, mutate):
    path = root / TASK_DIR / "handoff_v021.json"
    receipt = json.loads(path.read_bytes())
    mutate(receipt)
    data = canonical_json_bytes(receipt)
    path.write_bytes(data)
    active_path = root / "docs/control/active_task.json"
    active = json.loads(active_path.read_bytes())
    active["handoff_receipt_sha256"] = hashlib.sha256(data).hexdigest()
    active_path.write_bytes(canonical_json_bytes(active))


def _mutate_rereview_record(root, mutate):
    path = root / context._H001_CALIBRATION_REREVIEW_RECORD_RELPATH
    record = json.loads(path.read_bytes())
    mutate(record)
    path.write_bytes(canonical_json_bytes(record))
    _rewrite_rereview_receipt(root, lambda receipt: next(item for item in receipt["evidence"] if item["path"] == context._H001_CALIBRATION_REREVIEW_RECORD_RELPATH).__setitem__("sha256", hashlib.sha256(path.read_bytes()).hexdigest()))


def test_h001_calibration_rereview_phase_passes_and_renders_non_activation_boundary():
    state = load_and_verify_continuity_state(ROOT)
    if state["active_task"]["phase"] in (context._H001_CALIBRATION_EFFECTIVE_PHASE, context._H001_CALIBRATION_EXECUTION_GOVERNANCE_PHASE, context._H001_CALIBRATION_IMPLEMENTATION_BLOCKED_PHASE):
        pytest.skip("production tree has advanced to the effective freeze phase")
    assert state["active_task"]["phase"] == context._H001_CALIBRATION_REREVIEW_PHASE
    packet = render_context_packet(state)
    assert "H001_SYNTHETIC_NULL_CALIBRATION_SPEC_FREEZE_CANDIDATE_REVIEW=PASSED" in packet
    assert "H001_SYNTHETIC_NULL_CALIBRATION_SPEC_FREEZE=NOT_EFFECTIVE" in packet
    assert "H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION=NOT_AUTHORIZED" in packet
    assert "H001_SYNTHETIC_NULL_CALIBRATION_RESULTS=NONE" in packet
    assert "H001_EXECUTION=0/0" in packet
    assert "EDGE_UNPROVEN" in packet and "BLOCK_LIVE_INTEGRATION" in packet
    assert "H001 calibration specification remains unfrozen" in packet
    assert "H001 synthetic calibration execution remains unauthorized" in packet


@pytest.mark.parametrize("mutation", [
    lambda r: r["decisions"].__setitem__(r["decisions"].index("H001_SYNTHETIC_NULL_CALIBRATION_SPEC_FREEZE_CANDIDATE_REVIEW=PASSED"), "H001_SYNTHETIC_NULL_CALIBRATION_SPEC_FREEZE_CANDIDATE_REVIEW=FAILED"),
    lambda r: r["next_actions"].__setitem__(0, "ADVERSARIAL_REVIEW_H001_SYNTHETIC_NULL_CALIBRATION_SPEC_FREEZE_CANDIDATE"),
    lambda r: r["safety_state"].update(decomposition_execution_budget=2),
    lambda r: r["safety_state"].update(decomposition_execution_count=1),
    lambda r: r["safety_state"].update(edge_status="EDGE_PROVEN"),
    lambda r: r["safety_state"].update(live_status="READY"),
    lambda r: r["predecessor"].update(sha256="0" * 64),
])
def test_h001_calibration_rereview_handoff_mutations_fail_closed(tmp_path, mutation):
    root = _rereview_fixture(tmp_path)
    _rewrite_rereview_receipt(root, mutation)
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(root)


@pytest.mark.parametrize("mutation", [
    lambda v: v["review_history"].__setitem__(0, dict(v["review_history"][0], reviewed_head=v["review_history"][1]["reviewed_head"])),
    lambda v: v["review_history"].__setitem__(1, dict(v["review_history"][1], reviewed_head=v["review_history"][0]["reviewed_head"])),
    lambda v: v["review_bindings"].update(repair_commit="0" * 40),
    lambda v: v["review_bindings"].update(candidate_merge_commit="0" * 40),
    lambda v: v["candidate_review_scope"].reverse(),
    lambda v: v["repair_scope"].append("unexpected.py"),
    lambda v: v["review_results"].update(full_suite="6592 passed, 12 skipped"),
    lambda v: v["final_finding_counts"].update(blocker=1),
    lambda v: v.update(final_verdict="QNTY_H001_SYNTHETIC_NULL_CALIBRATION_SPEC_FREEZE_CANDIDATE_REREVIEW_FAILED"),
    lambda v: v.update(status="RECORDED_AFTER_REVIEW_EFFECTIVE"),
    lambda v: v["non_effects"].remove("BLOCK_LIVE_INTEGRATION"),
])
def test_h001_calibration_rereview_record_mutations_fail_closed(tmp_path, mutation):
    root = _rereview_fixture(tmp_path)
    _mutate_rereview_record(root, mutation)
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(root)


@pytest.mark.parametrize("mutation", [
    lambda v: v["authorization_state"].update(specification_effective=True),
    lambda v: v["authorization_state"].update(execution_authorized=True),
    lambda v: v["authorization_state"].update(results_exposed=True),
    lambda v: v["authorization_state"].update(real_data_access_authorized=True),
    lambda v: v["authorization_state"].update(scientific_authorization=True),
    lambda v: v["authorization_state"].update(paper_trade_authorization=True),
    lambda v: v["authorization_state"].update(live_authorization=True),
])
def test_h001_calibration_candidate_boundary_mutations_fail_closed(tmp_path, mutation):
    root = _rereview_fixture(tmp_path)
    candidate_path = root / context._H001_CALIBRATION_CANDIDATE_RELPATH
    candidate = json.loads(candidate_path.read_bytes())
    mutation(candidate)
    candidate_path.write_bytes(canonical_json_bytes(candidate))
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(root)


def test_h001_calibration_rereview_strict_temporal_contract_reversion_fails_closed(tmp_path):
    root = _rereview_fixture(tmp_path)
    validator_path = root / "quantbot/experiment/h001_real_falsification_preregistration.py"
    validator_path.write_bytes(validator_path.read_bytes().replace(
        b"latest funding_time_utc < bar[t].open_time_utc",
        b"latest funding_time_utc <= bar[t].open_time_utc",
        1,
    ))
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(root)


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
    if state["active_task"]["phase"] in (context._H001_TEMPORAL_CANDIDATE_PHASE, context._H001_TEMPORAL_REVIEW_COMPLETE_PHASE, context._H001_TEMPORAL_ACTIVE_PHASE, context._H001_CALIBRATION_GOVERNANCE_PHASE, context._H001_CALIBRATION_CANDIDATE_PHASE, context._H001_CALIBRATION_REREVIEW_PHASE, context._H001_CALIBRATION_EFFECTIVE_PHASE, context._H001_CALIBRATION_EXECUTION_GOVERNANCE_PHASE, context._H001_CALIBRATION_IMPLEMENTATION_BLOCKED_PHASE):
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
    if state["active_task"]["phase"] in (context._H001_CALIBRATION_GOVERNANCE_PHASE, context._H001_CALIBRATION_CANDIDATE_PHASE, context._H001_CALIBRATION_REREVIEW_PHASE, context._H001_CALIBRATION_EFFECTIVE_PHASE, context._H001_CALIBRATION_EXECUTION_GOVERNANCE_PHASE, context._H001_CALIBRATION_IMPLEMENTATION_BLOCKED_PHASE):
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
    if state["active_task"]["phase"] in (context._H001_CALIBRATION_GOVERNANCE_PHASE, context._H001_CALIBRATION_CANDIDATE_PHASE, context._H001_CALIBRATION_REREVIEW_PHASE, context._H001_CALIBRATION_EFFECTIVE_PHASE, context._H001_CALIBRATION_EXECUTION_GOVERNANCE_PHASE, context._H001_CALIBRATION_IMPLEMENTATION_BLOCKED_PHASE):
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
    if state["active_task"]["phase"] in (context._H001_CALIBRATION_GOVERNANCE_PHASE, context._H001_CALIBRATION_CANDIDATE_PHASE, context._H001_CALIBRATION_REREVIEW_PHASE, context._H001_CALIBRATION_EFFECTIVE_PHASE, context._H001_CALIBRATION_EXECUTION_GOVERNANCE_PHASE, context._H001_CALIBRATION_IMPLEMENTATION_BLOCKED_PHASE):
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


# The freeze-candidate transition (v019 -> v020) rewrote the assurance scaffold.
# A genuine v019 fixture must carry the pre-rewrite bytes those receipts pinned,
# not whatever the assurance tree looks like today. The historical bytes below are
# base64-encoded snapshots (no Git dependency, so this also works from a No-Git
# export) and are verified against the pinned governance-era SHA-256 before use.
_H001_CALIBRATION_GOVERNANCE_HISTORICAL_ASSURANCE_B64 = {
    'quantbot/assurance/contracts.py': (
        'IiIiU3RyaWN0LCBtZXRhZGF0YS1vbmx5IHZhbGlkYXRvcnMgZm9yIHRoZSBIMDAxIGFzc3VyYW5jZSBzY2FmZm9sZHMuCgpUaGlzIG1vZHVsZSBk'
        'ZWxpYmVyYXRlbHkgaGFzIG5vIGZpbGVzeXN0ZW0gZGlzY292ZXJ5LCBuZXR3b3JraW5nLCBhcnRpZmFjdC1zdG9yZSwKZGF0YWJhc2UsIGVudmly'
        'b25tZW50LCBvciByZWFsLWRhdGEgZGVwZW5kZW5jaWVzLgoiIiIKZnJvbSBfX2Z1dHVyZV9fIGltcG9ydCBhbm5vdGF0aW9ucwoKaW1wb3J0IGhh'
        'c2hsaWIKaW1wb3J0IGpzb24KaW1wb3J0IHJlCmZyb20gZGF0ZXRpbWUgaW1wb3J0IGRhdGV0aW1lLCB0aW1lem9uZQoKU0NIRU1BX1ZFUlNJT04g'
        'PSAiMC4xLjAiCkgwMDFfUFJPVE9DT0xfSUQgPSAicmVhbF9idGNfaDAwMV9mdW5kaW5nX2Nyb3dkaW5nX3JldmVyc2FsX2ZhbHNpZmljYXRpb25f'
        'djAiCkgwMDFfREVTSUdOX1NIQTI1NiA9ICIwNTVlYTE2MmExMWQ0MDQyMzIwZGFlYjc0ZTE1M2ViYmQyNzk2OWRkMjlhNjBjMjI2Y2I4NGE4ZmMz'
        'OGI4OTAwIgpIMDAxX1ZBTElEQVRPUl9TSEEyNTYgPSAiODg4YmM0NjYzZTNkN2ZiOWIzOThmOTQ0YmYyYjY3NTUzZTg5NTllMDE3M2JlNzcxODNj'
        'YThiMjg4MTU2MTcyYSIKR09WRVJOQU5DRV9BTUVORE1FTlRfU0hBMjU2ID0gImEyMmQwY2YyNjBmMzFkNzEwNGZjNGQ0ZmU5NjAzMGM4NjY2MTc5'
        'YzIwYzc3MzdkZmUyMGE1OWYzYzcyMDBkZGMiCgpTSEEyNTZfUkUgPSByZS5jb21waWxlKHIiWzAtOWEtZl17NjR9XFoiKQpJREVOVElGSUVSX1JF'
        'ID0gcmUuY29tcGlsZShyIlthLXowLTldW2EtejAtOS5fOi1dKlxaIikKQ0FOT05JQ0FMX1VUQ19USU1FU1RBTVBfUkUgPSByZS5jb21waWxlKHIi'
        'WzAtOV17NH0tWzAtOV17Mn0tWzAtOV17Mn1UWzAtOV17Mn06WzAtOV17Mn06WzAtOV17Mn1aXFoiKQpDT05UUk9MX1JFQ0VJUFRfUEFUSF9SRSA9'
        'IHJlLmNvbXBpbGUociJkb2NzL2NvbnRyb2wvKD86W0EtWmEtejAtOS5fLV0rLykqW0EtWmEtejAtOS5fLV0rXC5qc29uXFoiKQpTRUNSRVRfS0VZ'
        'UyA9IHsidG9rZW4iLCAic2VjcmV0IiwgInBhc3N3b3JkIiwgImNyZWRlbnRpYWwiLCAicHJpdmF0ZV9rZXkiLCAiY29va2llIiwgImF1dGhvcml6'
        'YXRpb24iLCAiYXBpX2tleSJ9CkZPUkJJRERFTl9LRVlTID0geyJyZXR1cm5zIiwgInByaWNlcyIsICJmdW5kaW5nIiwgInBfdmFsdWVzIiwgInAt'
        'dmFsdWVzIiwgInN0YXRpc3RpY3MiLCAicGVyZm9ybWFuY2UiLCAic3RyYXRlZ3lfcmFua2luZyIsICJyYXdfZGF0YSIsICJhcnRpZmFjdF9ieXRl'
        'cyIsICJzdG9yZV9yb290cyIsICJzdG9yZV91cmkiLCAiY3JlZGVudGlhbHMiLCAicHJpdmF0ZV9yZWFzb25pbmciLCAiY2hhaW5fb2ZfdGhvdWdo'
        'dCIsICJzY2llbnRpZmljX2NsYWltIiwgInJlc3VsdF9wYXlsb2FkIn0KRElTQ0xPU1VSRV9LSU5EUyA9IHsiREVTSUdOQVRFRF9ERVZFTE9QTUVO'
        'VCIsICJERVNJR05BVEVEX1ZBTElEQVRJT04iLCAiREVTSUdOQVRFRF9IT0xET1VUIiwgIlZBTElEQVRJT05fU1RBVElTVElDX0VYUE9TRUQiLCAi'
        'SE9MRE9VVF9VTlNFQUxFRCIsICJIT0xET1VUX1NUQVRJU1RJQ19FWFBPU0VEIiwgIlJFR0lPTl9HTE9CQUxMWV9DT05TVU1FRCIsICJERVNDUklQ'
        'VElWRV9SRVVTRV9PTkxZIn0KRElTQ0xPU1VSRV9TVEFUVVNFUyA9IHsiUkVDT1JERURfQVBQRU5EX09OTFkifQpMRURHRVJfU1RBVFVTRVMgPSB7'
        'IlNDSEVNQV9JTVBMRU1FTlRFRF9FTVBUWV9OT19CQUNLRklMTCIsICJBUFBFTkRfT05MWV9NRVRBREFUQV9ESVNDTE9TVVJFUyJ9CgpfUkVWSUVX'
        'X1BST1RPQ09MX0tFWVMgPSB7CiAgICAiYmFzZV9jb21taXRfc2hhIiwgImRvY3VtZW50X2lkIiwgImRvY3VtZW50X2tpbmQiLCAiZmFpbHVyZV92'
        'ZXJkaWN0IiwgImluaXRpYWxfZmFpbGVkX3Jldmlld19oZWFkIiwKICAgICJpbml0aWFsX2ZhaWx1cmVfdmVyZGljdCIsICJtZXJnZWRfbWFpbl9j'
        'b21taXRfc2hhIiwgIm5vbl9lZmZlY3RzIiwgInBhc3NfdmVyZGljdCIsICJwcm9oaWJpdGVkX2FjdGlvbnMiLAogICAgInJldmlld19raW5kIiwg'
        'InJldmlld19yZXF1aXJlbWVudHMiLCAicmV2aWV3ZWRfY29tbWl0X3NoYSIsICJzY2hlbWFfdmVyc2lvbiIsICJzdGF0dXMiLAp9Cl9SRVZJRVdf'
        'UFJPVE9DT0xfRVhQRUNURUQgPSB7CiAgICAic2NoZW1hX3ZlcnNpb24iOiBTQ0hFTUFfVkVSU0lPTiwKICAgICJkb2N1bWVudF9raW5kIjogInFu'
        'dHlfcmVwbGF5YWJsZV9yZXZpZXdfcHJvdG9jb2xfcmVjb3JkIiwKICAgICJkb2N1bWVudF9pZCI6ICJoMDAxLXByZS1kYXRhLWFzc3VyYW5jZS1z'
        'Y2FmZm9sZC1yZXJldmlldy1wcm90b2NvbC12MDAxIiwKICAgICJzdGF0dXMiOiAiUkVDT1JERURfQUZURVJfUkVWSUVXX05PVF9QUkVSRUdJU1RF'
        'UkVEIiwKICAgICJyZXZpZXdfa2luZCI6ICJJTkRFUEVOREVOVF9BRFZFUlNBUklBTF9SRVJFVklFVyIsCiAgICAiYmFzZV9jb21taXRfc2hhIjog'
        'IjI4ZDZjNzBlOWQ3Y2IxMWM1NWQxYWZkZjhiNGU1YWQ5NzU0ZjdhYmEiLAogICAgImluaXRpYWxfZmFpbGVkX3Jldmlld19oZWFkIjogIjNmYzYx'
        'ODZiNzY0NGU4ZmJkZjVmMThmMmY3MDI3NWIyMGNhNzQxZDAiLAogICAgInJldmlld2VkX2NvbW1pdF9zaGEiOiAiYzUyYzYwNzA0NTgwM2FiNmQ2'
        'ZTJhOTYxZjBmNjk3YWE3MmJmNzU4MSIsCiAgICAibWVyZ2VkX21haW5fY29tbWl0X3NoYSI6ICJhZTYxYzYxNjJmMzE2NGUwYjI0ZGQ1NjdhNmVm'
        'NzNiZGI1ZWNmOGVhIiwKICAgICJpbml0aWFsX2ZhaWx1cmVfdmVyZGljdCI6ICJRTlRZX0gwMDFfUFJFX0RBVEFfQVNTVVJBTkNFX1NDQUZGT0xE'
        'X1JFVklFV19GQUlMRUQiLAogICAgInBhc3NfdmVyZGljdCI6ICJRTlRZX0gwMDFfUFJFX0RBVEFfQVNTVVJBTkNFX1NDQUZGT0xEX1JFUkVWSUVX'
        'X1BBU1NFRCIsCiAgICAiZmFpbHVyZV92ZXJkaWN0IjogIlFOVFlfSDAwMV9QUkVfREFUQV9BU1NVUkFOQ0VfU0NBRkZPTERfUkVSRVZJRVdfRkFJ'
        'TEVEIiwKICAgICJyZXZpZXdfcmVxdWlyZW1lbnRzIjogWwogICAgICAgICJBUFBFTkRfT05MWV9DSEFJTl9JTlRBQ1QiLCAiQVVUSE9SSVRZX0RS'
        'SUZUX0FCU0VOVCIsICJDQUxJQlJBVElPTl9CT1VOREFSWV9GQUlMX0NMT1NFRCIsCiAgICAgICAgIkNBTk9OSUNBTF9BUFBFTkRfVkFMSURBVElP'
        'TiIsICJDQU5PTklDQUxfSlNPTl9WQUxJREFUSU9OIiwgIkNPTlRST0xfUkVDRUlQVF9QQVRIX0NPTlRSQUNUIiwKICAgICAgICAiRVhBQ1RfSEVB'
        'RF9BTkRfU0NPUEUiLCAiRlVMTF9URVNUX1NVSVRFX1BBU1MiLCAiTk9fR0lUX0VYUE9SVF9QQVNTIiwgIlJFTU9URV9DSV9QQVNTIiwKICAgICAg'
        'ICAiVVRDX1RJTUVTVEFNUF9DT05UUkFDVCIsCiAgICBdLAogICAgInByb2hpYml0ZWRfYWN0aW9ucyI6IFsKICAgICAgICAiQUNDRVNTX1JFQUxf'
        'REFUQSIsICJBQ0NFU1NfU1RPUkVTIiwgIkFQUExZX1RFTVBPUkFMX0NBVVNBTElUWV9BTUVORE1FTlQiLCAiRVhFQ1VURV9DQUxJQlJBVElPTiIs'
        'CiAgICAgICAgIkZSRUVaRV9DQUxJQlJBVElPTl9TUEVDSUZJQ0FUSU9OIiwgIkdSQU5UX1NDSUVOVElGSUNfUEFQRVJfT1JfTElWRV9BVVRIT1JJ'
        'VFkiLCAiUlVOX1NZTlRIRVRJQ19DQU5BUlkiLAogICAgXSwKICAgICJub25fZWZmZWN0cyI6IFsKICAgICAgICAiRE9FU19OT1RfQVVUSE9SSVpF'
        'X0VYRUNVVElPTiIsICJET0VTX05PVF9BVVRIT1JJWkVfUkVBTF9EQVRBIiwgIkRPRVNfTk9UX0FVVEhPUklaRV9TVE9SRV9BQ0NFU1MiLAogICAg'
        'ICAgICJET0VTX05PVF9QUk9WRV9NQVJLRVRfRURHRSIsICJSRVZJRVdfUFJPVE9DT0xfV0FTX05PVF9QUkVSRUdJU1RFUkVEX0JFRk9SRV9SRVZJ'
        'RVciLAogICAgXSwKfQpfUkVWSUVXX1BBQ0tFVF9LRVlTID0gewogICAgImNvbW1hbmRzIiwgImRvY3VtZW50X2lkIiwgImRvY3VtZW50X2tpbmQi'
        'LCAiZW52aXJvbm1lbnRfaWRlbnRpdHkiLCAiZmluZGluZ19jb3VudHMiLCAiaGFybmVzc19zb3VyY2VfaGFzaGVzIiwKICAgICJyZWRhY3Rpb25f'
        'bWFuaWZlc3QiLCAicmV2aWV3X2lkIiwgInJldmlld19raW5kIiwgInJldmlld19zcGVjaWZpY2F0aW9uX2hhc2giLCAicmV2aWV3ZWRfYXJ0aWZh'
        'Y3RfaGFzaGVzIiwKICAgICJyZXZpZXdlZF9jb21taXRfc2hhIiwgInNjaGVtYV92ZXJzaW9uIiwgInN0YXR1cyIsICJzdGRlcnJfYXJ0aWZhY3Rf'
        'aGFzaGVzIiwgInN0ZG91dF9hcnRpZmFjdF9oYXNoZXMiLCAidmVyZGljdCIsCn0KX1JFVklFV19BUlRJRkFDVF9IQVNIRVMgPSB7CiAgICAiZG9j'
        'cy9hc3N1cmFuY2UvSDAwMV9QUkVfREFUQV9BU1NVUkFOQ0VfU0NBRkZPTEQubWQiOiAiMmRiODQ1MjQ3Yjg3MzdiY2U2MGVkMWNhMDQ5NTUyZGQ3'
        'ZmI2YzAwMjViY2FhNTY2ZmJmMWQ5MjhiNDQ2ODZhYSIsCiAgICAiZG9jcy9hc3N1cmFuY2UvZHVyYWJsZV9zdG9yZV9mYWlsdXJlX2RvbWFpbl9l'
        'dmlkZW5jZV9zY2hlbWFfdjAwMS5qc29uIjogIjhmMTNmODdjZTk3ZmJkZjc3NzEwMDRlMDJlMzM4MDk4MDVhNzUzMzgzODNlOTNjODcwY2U1NjRh'
        'NDg5Njg5ODUiLAogICAgImRvY3MvYXNzdXJhbmNlL2dsb2JhbF9yZWFsX3Byb3RvY29sX2hvbGRvdXRfZGlzY2xvc3VyZV9sZWRnZXJfdjAwMS5q'
        'c29uIjogIjcxYjhmZjVlYjc0NDYxYjA3ODllZWI3NTM4ODgwOGZjNzg3NjkyZmM2ZDg0ZmFkMWFjYjU3M2Q0YjM2MzE1ZWUiLAogICAgImRvY3Mv'
        'YXNzdXJhbmNlL2gwMDFfc3ludGhldGljX251bGxfY2FsaWJyYXRpb25fc3BlY19kcmFmdF92MDAxLmpzb24iOiAiN2UwNWEwYjJiNDRkZDRlM2Zi'
        'YWRmM2UxMjE3OTFlYjJlZTc2Mzg1YTZiMmVjNmI4NzI5ODRjYmIzNTEwZWNmNiIsCiAgICAiZG9jcy9hc3N1cmFuY2UvaDAwMV90ZW1wb3JhbF9j'
        'YXVzYWxpdHlfYW1lbmRtZW50X2RyYWZ0X3YwMDEuanNvbiI6ICIwM2M1N2QwYzA5MzVlYjM3ZDUzZWU2ODQxMDkzNWUyNThlM2JkZTBmNWIyYzhk'
        'MTkwNDhlNGMxZDk3OWQ1NjM5IiwKICAgICJkb2NzL2Fzc3VyYW5jZS9yZXBsYXlhYmxlX3Jldmlld19ldmlkZW5jZV9wYWNrZXRfc2NoZW1hX3Yw'
        'MDEuanNvbiI6ICI5OTAwNTI0Njk1NzFiMmZmMTAwMTgwYzcwNmUwZTM4MjU3ZmQ5NTJlMzIzMjBiNjY1NzUzZDIzMjEyY2ZiY2JiIiwKICAgICJk'
        'b2NzL2Fzc3VyYW5jZS9zeW50aGV0aWNfYXJ0aWZhY3RfY2FuYXJ5X3NjYWZmb2xkX3YwMDEuanNvbiI6ICI0NWU2Zjk1ZmVjZTIzMjhkZjJjMzlm'
        'MmZjZTc5MGJiYTM3YTA5NDRlYTdjNWJjMzNiOGU1MDU4MjBiZWI1MzkyIiwKICAgICJkb2NzL2NvbnRyb2wvYWN0aXZlX3Rhc2suanNvbiI6ICJj'
        'NGJkOTdhZTM4OTUxNDNhOTMwZDliODczMjUxYjcwMWFhOGVkYjhkZmQ5Yzg3NWIxNjlhMTA3ZTMyOTRlMGUzIiwKICAgICJkb2NzL2NvbnRyb2wv'
        'dGFza3MvUkVDT1ZFUl9PUl9SRVRJUkVfQ0FORElEQVRFMV9WMF9GUk9aRU5fSU5QVVQvaGFuZG9mZl92MDE0Lmpzb24iOiAiOTZmZjBkOTM0NTQ4'
        'ZTAyZmJjZmVjODM2ODgyOTUyMGQ2YWRkMjJhYmU4MzQxM2FkZmJjNDU2YzAwOWIxZDExNyIsCiAgICAicXVhbnRib3QvYXNzdXJhbmNlL19faW5p'
        'dF9fLnB5IjogIjMxZTE2NTc0N2ViNWNmYTQ2MjIzN2QxNjNmYWFiMGJiYWNiZDllYjM2YzgxNWVhNDJkNjQxODE5MmEzNzhjYmUiLAogICAgInF1'
        'YW50Ym90L2Fzc3VyYW5jZS9jb250cmFjdHMucHkiOiAiNGQ3YzE4ZTVlOTc3MzJiMDg3NTI1MTVhY2IxMjZlNTBjMDUxY2Y3MTI3NWM3N2I1MTYx'
        'M2YzZDNlYjkzZTlhYSIsCiAgICAicXVhbnRib3QvYXNzdXJhbmNlL2gwMDFfbnVsbF9jYWxpYnJhdGlvbi5weSI6ICJkZWFjZWVlYzAzNTc4YTdm'
        'NDMwOTcyYzhmNGRlMmJiOTY3OThlNjYwYjBjYmU2NDUwNGM2ZmJmOGRhNTEyYmRkIiwKICAgICJxdWFudGJvdC9jb250aW51aXR5L2NvbnRleHQu'
        'cHkiOiAiZmYwNWI0MTY1MDMyZjIxYWMyY2Q2NDUwOTZkMmYwZTVmNDg2MTE3NTg1NzQ3OGVkMWE4YzMzMjE5NGExZWRmNCIsCiAgICAidGVzdHMv'
        'YXNzdXJhbmNlL3Rlc3RfY29udHJhY3RzLnB5IjogIjBhOTBjMDg1Y2Y1ZGQyNGJlMjc3NTYyYjY1ZWMyYjAzMDdhZjhjM2FiNzMwNTZjNTMxZmI4'
        'ZTA1ODNiOWU4YjIiLAogICAgInRlc3RzL2Fzc3VyYW5jZS90ZXN0X2gwMDFfbnVsbF9jYWxpYnJhdGlvbi5weSI6ICI0N2JiMTgzNjAxNjVlZmZj'
        'ODI2MTAyYzg0YjkzMWE1MWExOThhOTk0Yjk5Y2M2YmFlMjRiMmJmOWJkODdhMDZjIiwKICAgICJ0ZXN0cy9jb250aW51aXR5L3Rlc3RfY3Jvc3Nf'
        'YWdlbnRfY29udGludWl0eS5weSI6ICJlMDY4ZTJjYTY4NjAwOTQxMzZiY2JlMjFhMGFlMGI3MzA0MWIzOWI5NjNlOWIwZDNkM2U5N2U3ZmE3ZmNj'
        'MDc5IiwKfQpfUkVWSUVXX0hBUk5FU1NfSEFTSEVTID0ge2tleTogX1JFVklFV19BUlRJRkFDVF9IQVNIRVNba2V5XSBmb3Iga2V5IGluICgKICAg'
        'ICJxdWFudGJvdC9hc3N1cmFuY2UvY29udHJhY3RzLnB5IiwgInF1YW50Ym90L2Fzc3VyYW5jZS9oMDAxX251bGxfY2FsaWJyYXRpb24ucHkiLCAi'
        'cXVhbnRib3QvY29udGludWl0eS9jb250ZXh0LnB5IiwKICAgICJ0ZXN0cy9hc3N1cmFuY2UvdGVzdF9jb250cmFjdHMucHkiLCAidGVzdHMvYXNz'
        'dXJhbmNlL3Rlc3RfaDAwMV9udWxsX2NhbGlicmF0aW9uLnB5IiwgInRlc3RzL2NvbnRpbnVpdHkvdGVzdF9jcm9zc19hZ2VudF9jb250aW51aXR5'
        'LnB5IiwKKX0KX1JFVklFV19DT01NQU5EUyA9IFsKICAgICJzZXQgLWV1byBwaXBlZmFpbCIsCiAgICAiUkVQTz0vaG9tZS9zd2lya3kvRGV2SHVi'
        'L3JlcG9zL1FudHkiLAogICAgIkJBU0U9MjhkNmM3MGU5ZDdjYjExYzU1ZDFhZmRmOGI0ZTVhZDk3NTRmN2FiYSIsCiAgICAiSEVBRD1jNTJjNjA3'
        'MDQ1ODAzYWI2ZDZlMmE5NjFmMGY2OTdhYTcyYmY3NTgxIiwKICAgICJQWT0kUkVQTy8udmVudi9iaW4vcHl0aG9uIiwKICAgICJSRVZJRVdfRElS'
        'PSQobWt0ZW1wIC1kIC90bXAvcW50eS1wcjI4Mi1yZXJldmlldy5YWFhYWFgpIiwKICAgICJTQ09QRV9ESVI9JChta3RlbXAgLWQgL3RtcC9xbnR5'
        'LXByMjgyLXNjb3BlLlhYWFhYWCkiLAogICAgIkVYUE9SVD0kKG1rdGVtcCAtZCAvdG1wL3FudHktaDAwMS1yZXZpZXctZXhwb3J0LlhYWFhYWCki'
        'LAogICAgImdpdCAtQyAkUkVQTyB3b3JrdHJlZSBhZGQgLS1kZXRhY2ggJFJFVklFV19ESVIgJEhFQUQiLAogICAgImNkICRSRVZJRVdfRElSIiwK'
        'ICAgICd0ZXN0ICIkKGdpdCByZXYtcGFyc2UgSEVBRCkiID0gIiRIRUFEIicsCiAgICAndGVzdCAiJChnaXQgbWVyZ2UtYmFzZSAiJEJBU0UiICIk'
        'SEVBRCIpIiA9ICIkQkFTRSInLAogICAgJ2dpdCBkaWZmIC0tbmFtZS1vbmx5ICIkQkFTRS4uLiRIRUFEIicsCiAgICAndGVzdCAiJChnaXQgZGlm'
        'ZiAtLW5hbWUtb25seSAiJEJBU0UuLi4kSEVBRCIgfCB3YyAtbCkiIC1lcSAxNicsCiAgICAicHJpbnRmICclc1xcbicgZG9jcy9hc3N1cmFuY2Uv'
        'SDAwMV9QUkVfREFUQV9BU1NVUkFOQ0VfU0NBRkZPTEQubWQgZG9jcy9hc3N1cmFuY2UvZHVyYWJsZV9zdG9yZV9mYWlsdXJlX2RvbWFpbl9ldmlk'
        'ZW5jZV9zY2hlbWFfdjAwMS5qc29uIGRvY3MvYXNzdXJhbmNlL2dsb2JhbF9yZWFsX3Byb3RvY29sX2hvbGRvdXRfZGlzY2xvc3VyZV9sZWRnZXJf'
        'djAwMS5qc29uIGRvY3MvYXNzdXJhbmNlL2gwMDFfc3ludGhldGljX251bGxfY2FsaWJyYXRpb25fc3BlY19kcmFmdF92MDAxLmpzb24gZG9jcy9h'
        'c3N1cmFuY2UvaDAwMV90ZW1wb3JhbF9jYXVzYWxpdHlfYW1lbmRtZW50X2RyYWZ0X3YwMDEuanNvbiBkb2NzL2Fzc3VyYW5jZS9yZXBsYXlhYmxl'
        'X3Jldmlld19ldmlkZW5jZV9wYWNrZXRfc2NoZW1hX3YwMDEuanNvbiBkb2NzL2Fzc3VyYW5jZS9zeW50aGV0aWNfYXJ0aWZhY3RfY2FuYXJ5X3Nj'
        'YWZmb2xkX3YwMDEuanNvbiBkb2NzL2NvbnRyb2wvYWN0aXZlX3Rhc2suanNvbiBkb2NzL2NvbnRyb2wvdGFza3MvUkVDT1ZFUl9PUl9SRVRJUkVf'
        'Q0FORElEQVRFMV9WMF9GUk9aRU5fSU5QVVQvaGFuZG9mZl92MDE0Lmpzb24gcXVhbnRib3QvYXNzdXJhbmNlL19faW5pdF9fLnB5IHF1YW50Ym90'
        'L2Fzc3VyYW5jZS9jb250cmFjdHMucHkgcXVhbnRib3QvYXNzdXJhbmNlL2gwMDFfbnVsbF9jYWxpYnJhdGlvbi5weSBxdWFudGJvdC9jb250aW51'
        'aXR5L2NvbnRleHQucHkgdGVzdHMvYXNzdXJhbmNlL3Rlc3RfY29udHJhY3RzLnB5IHRlc3RzL2Fzc3VyYW5jZS90ZXN0X2gwMDFfbnVsbF9jYWxp'
        'YnJhdGlvbi5weSB0ZXN0cy9jb250aW51aXR5L3Rlc3RfY3Jvc3NfYWdlbnRfY29udGludWl0eS5weSB8IHNvcnQgPiAkU0NPUEVfRElSL2V4cGVj'
        'dGVkLXNjb3BlLnR4dCIsCiAgICAnZ2l0IGRpZmYgLS1uYW1lLW9ubHkgIiRCQVNFLi4uJEhFQUQiIHwgc29ydCA+ICRTQ09QRV9ESVIvb2JzZXJ2'
        'ZWQtc2NvcGUudHh0JywKICAgICJkaWZmIC11ICRTQ09QRV9ESVIvZXhwZWN0ZWQtc2NvcGUudHh0ICRTQ09QRV9ESVIvb2JzZXJ2ZWQtc2NvcGUu'
        'dHh0IiwKICAgICJzaGEyNTZzdW0gZG9jcy9hc3N1cmFuY2UvSDAwMV9QUkVfREFUQV9BU1NVUkFOQ0VfU0NBRkZPTEQubWQgZG9jcy9hc3N1cmFu'
        'Y2UvcmVwbGF5YWJsZV9yZXZpZXdfZXZpZGVuY2VfcGFja2V0X3NjaGVtYV92MDAxLmpzb24gcXVhbnRib3QvYXNzdXJhbmNlL2NvbnRyYWN0cy5w'
        'eSBxdWFudGJvdC9jb250aW51aXR5L2NvbnRleHQucHkiLAogICAgIiRQWSAtbSBweXRlc3QgdGVzdHMvYXNzdXJhbmNlIC1xIiwKICAgICIkUFkg'
        'LW0gcHl0ZXN0IHRlc3RzL2NvbnRpbnVpdHkgLXEiLAogICAgIiRQWSAtbSBweXRlc3QgdGVzdHMvc2FuZGJveCAtcSIsCiAgICAiJFBZIC1tIHB5'
        'dGVzdCB0ZXN0cy9hcnRpZmFjdHMgLXEiLAogICAgIiRQWSAtbSBweXRlc3QgdGVzdHMvZXhwZXJpbWVudC90ZXN0X2gwMDFfcmVhbF9mYWxzaWZp'
        'Y2F0aW9uX3ByZXJlZ2lzdHJhdGlvbi5weSAtcSIsCiAgICAiJFBZIC1tIHB5dGVzdCAtcSIsCiAgICAiUEFUSD0kUkVQTy8udmVudi9iaW46JFBB'
        'VEggJFJFUE8vc2NyaXB0cy9yZWxlYXNlX3Ntb2tlLnNoIiwKICAgICIkUFkgLW0gcXVhbnRib3QuY29udGludWl0eSB2ZXJpZnkiLAogICAgIiRQ'
        'WSAtbSBxdWFudGJvdC5jb250aW51aXR5IHNob3ciLAogICAgIiRQWSAtbSBxdWFudGJvdC5hcnRpZmFjdHMgdmVyaWZ5LXJlZ2lzdHJ5IiwKICAg'
        'ICIkUFkgLW0gcXVhbnRib3QuYXJ0aWZhY3RzIHN0YXR1cyIsCiAgICAiZ2l0IGFyY2hpdmUgJEhFQUQgfCB0YXIgLXggLUMgJEVYUE9SVCIsCiAg'
        'ICAidGVzdCAhIC1lICRFWFBPUlQvLmdpdCIsCiAgICAiY2QgJEVYUE9SVCIsCiAgICAiUFlUSE9OUEFUSD0kRVhQT1JUICRQWSAtbSBweXRlc3Qg'
        'dGVzdHMvYXNzdXJhbmNlIHRlc3RzL2NvbnRpbnVpdHkgLXEiLAogICAgIlBZVEhPTlBBVEg9JEVYUE9SVCAkUFkgLW0gcXVhbnRib3QuY29udGlu'
        'dWl0eSB2ZXJpZnkiLAogICAgIlBZVEhPTlBBVEg9JEVYUE9SVCAkUFkgLW0gcXVhbnRib3QuY29udGludWl0eSBzaG93IiwKICAgICJjZCAkUkVW'
        'SUVXX0RJUiAmJiBnaXQgZGlmZiAtLWNoZWNrIiwKICAgICd0ZXN0IC16ICIkKGdpdCBzdGF0dXMgLS1zaG9ydCkiJywKICAgICJnaCBydW4gbGlz'
        'dCAtLXJlcG8gQ2lwaGVyQ3V0dGxlL1FudHkgLS1jb21taXQgJEhFQUQgLS1qc29uIG5hbWUsc3RhdHVzLGNvbmNsdXNpb24saGVhZFNoYSIsCl0K'
        'CmRlZiByZXZpZXdfcHJvdG9jb2xfcmVjb3JkKCkgLT4gZGljdDoKICAgIHJldHVybiBqc29uLmxvYWRzKGNhbm9uaWNhbF9qc29uX2J5dGVzKF9S'
        'RVZJRVdfUFJPVE9DT0xfRVhQRUNURUQpLmRlY29kZSgidXRmLTgiKSkKCmRlZiB2YWxpZGF0ZV9yZXZpZXdfcHJvdG9jb2xfcmVjb3JkKHZhbHVl'
        'OiBvYmplY3QpIC0+IGRpY3Q6CiAgICBkYXRhID0gX2Jhc2UodmFsdWUsICJxbnR5X3JlcGxheWFibGVfcmV2aWV3X3Byb3RvY29sX3JlY29yZCIs'
        'IF9SRVZJRVdfUFJPVE9DT0xfRVhQRUNURURbImRvY3VtZW50X2lkIl0sIF9SRVZJRVdfUFJPVE9DT0xfRVhQRUNURURbInN0YXR1cyJdLCBfUkVW'
        'SUVXX1BST1RPQ09MX0tFWVMpCiAgICBpZiBkYXRhICE9IF9SRVZJRVdfUFJPVE9DT0xfRVhQRUNURUQ6CiAgICAgICAgX2ZhaWwoInJldmlldyBw'
        'cm90b2NvbCByZWNvcmQgZHJpZnRlZCBvciBjbGFpbXMgcHJlcmVnaXN0cmF0aW9uL2ZyZWV6aW5nIGJlZm9yZSByZXZpZXciKQogICAgZm9yIGtl'
        'eSBpbiAoImJhc2VfY29tbWl0X3NoYSIsICJpbml0aWFsX2ZhaWxlZF9yZXZpZXdfaGVhZCIsICJyZXZpZXdlZF9jb21taXRfc2hhIiwgIm1lcmdl'
        'ZF9tYWluX2NvbW1pdF9zaGEiKToKICAgICAgICBpZiB0eXBlKGRhdGFba2V5XSkgaXMgbm90IHN0ciBvciBub3QgcmUuZnVsbG1hdGNoKHIiWzAt'
        'OWEtZl17NDB9IiwgZGF0YVtrZXldKToKICAgICAgICAgICAgX2ZhaWwoZiJ7a2V5fTogbG93ZXJjYXNlIGNvbW1pdCBzaGEgcmVxdWlyZWQiKQog'
        'ICAgcmV0dXJuIGRhdGEKCmRlZiBfdmFsaWRhdGVfaGFzaF9yZWNvcmRzKHZhbHVlOiBvYmplY3QsIGV4cGVjdGVkOiBkaWN0W3N0ciwgc3RyXSwg'
        'bGFiZWw6IHN0cikgLT4gTm9uZToKICAgIHJlY29yZHMgPSBfbGlzdCh2YWx1ZSwgbGFiZWwpCiAgICBpZiByZWNvcmRzICE9IFt7InBhdGgiOiBw'
        'YXRoLCAic2hhMjU2IjogZXhwZWN0ZWRbcGF0aF19IGZvciBwYXRoIGluIHNvcnRlZChleHBlY3RlZCldOgogICAgICAgIF9mYWlsKGYie2xhYmVs'
        'fTogZXhhY3QgaW5kZXBlbmRlbnRseSBwaW5uZWQgaGFzaCBzZXQgcmVxdWlyZWQiKQogICAgZm9yIHJlY29yZCBpbiByZWNvcmRzOgogICAgICAg'
        'IF9rZXlzKHJlY29yZCwgeyJwYXRoIiwgInNoYTI1NiJ9LCBmIntsYWJlbH0gZW50cnkiKQogICAgICAgIGlmIG5vdCByZS5mdWxsbWF0Y2gociJb'
        'QS1aYS16MC05Ll8vLV0rIiwgcmVjb3JkWyJwYXRoIl0pIG9yICIuLiIgaW4gcmVjb3JkWyJwYXRoIl0uc3BsaXQoIi8iKToKICAgICAgICAgICAg'
        'X2ZhaWwoZiJ7bGFiZWx9OiB1bnNhZmUgcmVsYXRpdmUgcGF0aCIpCiAgICAgICAgX3NoYShyZWNvcmRbInNoYTI1NiJdLCBmIntsYWJlbH0gc2hh'
        'MjU2IikKCmRlZiB2YWxpZGF0ZV9yZXZpZXdfZXZpZGVuY2VfcGFja2V0KHZhbHVlOiBvYmplY3QpIC0+IGRpY3Q6CiAgICBkYXRhID0gX2Jhc2Uo'
        'dmFsdWUsICJxbnR5X3JlcGxheWFibGVfcmV2aWV3X2V2aWRlbmNlX3BhY2tldCIsICJoMDAxLXByZS1kYXRhLWFzc3VyYW5jZS1zY2FmZm9sZC1y'
        'ZXJldmlldy1wYWNrZXQtdjAwMSIsICJDT01QTEVURURfTUVUQURBVEFfT05MWV9OT19SRUFMX0RBVEFfT1JfU0VDUkVUUyIsIF9SRVZJRVdfUEFD'
        'S0VUX0tFWVMpCiAgICBleHBlY3RlZCA9IHsKICAgICAgICAic2NoZW1hX3ZlcnNpb24iOiBTQ0hFTUFfVkVSU0lPTiwgImRvY3VtZW50X2tpbmQi'
        'OiAicW50eV9yZXBsYXlhYmxlX3Jldmlld19ldmlkZW5jZV9wYWNrZXQiLAogICAgICAgICJkb2N1bWVudF9pZCI6ICJoMDAxLXByZS1kYXRhLWFz'
        'c3VyYW5jZS1zY2FmZm9sZC1yZXJldmlldy1wYWNrZXQtdjAwMSIsICJzdGF0dXMiOiAiQ09NUExFVEVEX01FVEFEQVRBX09OTFlfTk9fUkVBTF9E'
        'QVRBX09SX1NFQ1JFVFMiLAogICAgICAgICJyZXZpZXdfaWQiOiAiaDAwMS1wcmUtZGF0YS1hc3N1cmFuY2Utc2NhZmZvbGQtcmVyZXZpZXctdjAw'
        'MSIsICJyZXZpZXdfa2luZCI6ICJJTkRFUEVOREVOVF9BRFZFUlNBUklBTF9SRVJFVklFVyIsCiAgICAgICAgInJldmlld2VkX2NvbW1pdF9zaGEi'
        'OiAiYzUyYzYwNzA0NTgwM2FiNmQ2ZTJhOTYxZjBmNjk3YWE3MmJmNzU4MSIsICJ2ZXJkaWN0IjogIlFOVFlfSDAwMV9QUkVfREFUQV9BU1NVUkFO'
        'Q0VfU0NBRkZPTERfUkVSRVZJRVdfUEFTU0VEIiwKICAgICAgICAiZW52aXJvbm1lbnRfaWRlbnRpdHkiOiB7ImNoZWNrb3V0X21vZGUiOiAiREVU'
        'QUNIRURfV09SS1RSRUUiLCAiZXhwb3J0ZWRfdHJlZV92ZXJpZmllZCI6IFRydWUsICJnaXRfbWV0YWRhdGFfYXZhaWxhYmxlIjogVHJ1ZSwgIm5l'
        'dHdvcmtfYWNjZXNzIjogIk5PVF9VU0VEIiwgInB5dGhvbl9lbnZpcm9ubWVudCI6ICJSRVBPU0lUT1JZX1ZFTlYiLCAicmV2aWV3ZWRfdHJlZV9z'
        'b3VyY2UiOiAiUElOTkVEX0NPTU1JVCIsICJzdGRvdXRfc3RkZXJyX2FydGlmYWN0c19wZXJzaXN0ZWQiOiBGYWxzZX0sCiAgICAgICAgImZpbmRp'
        'bmdfY291bnRzIjogeyJibG9ja2VyIjogMCwgIm1ham9yIjogMCwgIm1pbm9yIjogMH0sCiAgICAgICAgInJlZGFjdGlvbl9tYW5pZmVzdCI6IHsi'
        'cHJpdmF0ZV9yZWFzb25pbmdfaW5jbHVkZWQiOiBGYWxzZSwgInJlYWxfZGF0YV9pbmNsdWRlZCI6IEZhbHNlLCAicmVkYWN0aW9uX3N0YXR1cyI6'
        'ICJOT19TRUNSRVRfQkVBUklOR19PVVRQVVRfUEVSU0lTVEVEIiwgInNlY3JldF92YWx1ZXNfaW5jbHVkZWQiOiBGYWxzZSwgInN0ZGVycl9wZXJz'
        'aXN0ZWQiOiBGYWxzZSwgInN0ZG91dF9wZXJzaXN0ZWQiOiBGYWxzZX0sCiAgICAgICAgInN0ZG91dF9hcnRpZmFjdF9oYXNoZXMiOiBbXSwgInN0'
        'ZGVycl9hcnRpZmFjdF9oYXNoZXMiOiBbXSwgImNvbW1hbmRzIjogX1JFVklFV19DT01NQU5EUywKICAgIH0KICAgIGlmIGRhdGFbInJldmlld2Vk'
        'X2NvbW1pdF9zaGEiXSAhPSBleHBlY3RlZFsicmV2aWV3ZWRfY29tbWl0X3NoYSJdIG9yIGRhdGFbInZlcmRpY3QiXSAhPSBleHBlY3RlZFsidmVy'
        'ZGljdCJdOgogICAgICAgIF9mYWlsKCJyZXZpZXcgcGFja2V0IGhlYWQgb3IgdmVyZGljdCBkcmlmdGVkIikKICAgIGlmIGRhdGFbImVudmlyb25t'
        'ZW50X2lkZW50aXR5Il0gIT0gZXhwZWN0ZWRbImVudmlyb25tZW50X2lkZW50aXR5Il0gb3IgZGF0YVsiZmluZGluZ19jb3VudHMiXSAhPSBleHBl'
        'Y3RlZFsiZmluZGluZ19jb3VudHMiXSBvciBkYXRhWyJyZWRhY3Rpb25fbWFuaWZlc3QiXSAhPSBleHBlY3RlZFsicmVkYWN0aW9uX21hbmlmZXN0'
        'Il06CiAgICAgICAgX2ZhaWwoInJldmlldyBwYWNrZXQgZW52aXJvbm1lbnQsIGZpbmRpbmdzLCBvciByZWRhY3Rpb24gbWV0YWRhdGEgZHJpZnRl'
        'ZCIpCiAgICBpZiBkYXRhWyJjb21tYW5kcyJdICE9IF9SRVZJRVdfQ09NTUFORFMgb3IgZGF0YVsic3Rkb3V0X2FydGlmYWN0X2hhc2hlcyJdIG9y'
        'IGRhdGFbInN0ZGVycl9hcnRpZmFjdF9oYXNoZXMiXToKICAgICAgICBfZmFpbCgicmV2aWV3IHBhY2tldCBjb21tYW5kcyBvciBvdXRwdXQgaGFz'
        'aGVzIGRyaWZ0ZWQiKQogICAgaWYgbGVuKGRhdGFbImNvbW1hbmRzIl0pICE9IGxlbihzZXQoZGF0YVsiY29tbWFuZHMiXSkpIG9yIGFueSh0eXBl'
        'KGNvbW1hbmQpIGlzIG5vdCBzdHIgb3Igbm90IGNvbW1hbmQgZm9yIGNvbW1hbmQgaW4gZGF0YVsiY29tbWFuZHMiXSk6CiAgICAgICAgX2ZhaWwo'
        'InJldmlldyBwYWNrZXQgY29tbWFuZHMgbXVzdCBiZSBub24tZW1wdHkgYW5kIHVuaXF1ZSIpCiAgICBpZiBhbnkodG9rZW4gaW4gY29tbWFuZCBm'
        'b3IgY29tbWFuZCBpbiBkYXRhWyJjb21tYW5kcyJdIGZvciB0b2tlbiBpbiAoIi0tbm8tZ2l0LWV4cG9ydCIsICJyZW1vdGUgQ0kgY2hlY2tzIiwg'
        'InRva2VuPSIsICJwYXNzd29yZD0iLCAiY3JlZGVudGlhbD0iKSk6CiAgICAgICAgX2ZhaWwoInJldmlldyBwYWNrZXQgY29udGFpbnMgYSBub24t'
        'cmVwbGF5YWJsZSBvciBzZWNyZXQtYmVhcmluZyBjb21tYW5kIikKICAgIHJlcXVpcmVkX21hcmtlcnMgPSAoCiAgICAgICAgIiRIRUFEIiwgIiRC'
        'QVNFIiwgIkJBU0U9MjhkNmM3MGU5ZDdjYjExYzU1ZDFhZmRmOGI0ZTVhZDk3NTRmN2FiYSIsICJnaXQgbWVyZ2UtYmFzZSIsCiAgICAgICAgIndv'
        'cmt0cmVlIGFkZCAtLWRldGFjaCIsICJjZCAkUkVWSUVXX0RJUiIsICJjZCAkRVhQT1JUIiwgImdpdCBkaWZmIC0tbmFtZS1vbmx5IiwgImRpZmYg'
        'LXUiLAogICAgICAgICJzaGEyNTZzdW0iLCAiZ2l0IGFyY2hpdmUiLCAiISAtZSAkRVhQT1JULy5naXQiLCAiUFlUSE9OUEFUSD0kRVhQT1JUIiwg'
        'ImdoIHJ1biBsaXN0IiwgImdpdCBzdGF0dXMgLS1zaG9ydCIsCiAgICApCiAgICBpZiBhbnkobm90IGFueShtYXJrZXIgaW4gY29tbWFuZCBmb3Ig'
        'Y29tbWFuZCBpbiBkYXRhWyJjb21tYW5kcyJdKSBmb3IgbWFya2VyIGluIHJlcXVpcmVkX21hcmtlcnMpOgogICAgICAgIF9mYWlsKCJyZXZpZXcg'
        'cGFja2V0IGNvbW1hbmQgY292ZXJhZ2UgaXMgaW5jb21wbGV0ZSIpCiAgICBpZiBhbnkoX1JFVklFV19QUk9UT0NPTF9FWFBFQ1RFRFsibWVyZ2Vk'
        'X21haW5fY29tbWl0X3NoYSJdIGluIGNvbW1hbmQgZm9yIGNvbW1hbmQgaW4gZGF0YVsiY29tbWFuZHMiXSk6CiAgICAgICAgX2ZhaWwoInJldmll'
        'dyBwYWNrZXQgcmVwbGF5IHJlY2lwZSBtdXN0IHVzZSB0aGUgcmV2aWV3ZWQtUFIgYmFzZSwgbm90IHRoZSBtZXJnZWQtbWFpbiBjb21taXQiKQog'
        'ICAgX3ZhbGlkYXRlX2hhc2hfcmVjb3JkcyhkYXRhWyJyZXZpZXdlZF9hcnRpZmFjdF9oYXNoZXMiXSwgX1JFVklFV19BUlRJRkFDVF9IQVNIRVMs'
        'ICJyZXZpZXdlZF9hcnRpZmFjdF9oYXNoZXMiKQogICAgX3ZhbGlkYXRlX2hhc2hfcmVjb3JkcyhkYXRhWyJoYXJuZXNzX3NvdXJjZV9oYXNoZXMi'
        'XSwgX1JFVklFV19IQVJORVNTX0hBU0hFUywgImhhcm5lc3Nfc291cmNlX2hhc2hlcyIpCiAgICBleHBlY3RlZF9wcm90b2NvbF9oYXNoID0gaGFz'
        'aGxpYi5zaGEyNTYoY2Fub25pY2FsX2pzb25fYnl0ZXMoX1JFVklFV19QUk9UT0NPTF9FWFBFQ1RFRCkpLmhleGRpZ2VzdCgpCiAgICBpZiBkYXRh'
        'WyJyZXZpZXdfc3BlY2lmaWNhdGlvbl9oYXNoIl0gIT0gZXhwZWN0ZWRfcHJvdG9jb2xfaGFzaDoKICAgICAgICBfZmFpbCgicmV2aWV3IHBhY2tl'
        'dCBwcm90b2NvbCBoYXNoIGRyaWZ0ZWQiKQogICAgX3NoYShkYXRhWyJyZXZpZXdfc3BlY2lmaWNhdGlvbl9oYXNoIl0sICJyZXZpZXdfc3BlY2lm'
        'aWNhdGlvbl9oYXNoIikKICAgIHJldHVybiBkYXRhCgpjbGFzcyBBc3N1cmFuY2VWYWxpZGF0aW9uRXJyb3IoVmFsdWVFcnJvcik6CiAgICBwYXNz'
        'CgpkZWYgY2Fub25pY2FsX2pzb25fYnl0ZXModmFsdWU6IG9iamVjdCkgLT4gYnl0ZXM6CiAgICByZXR1cm4ganNvbi5kdW1wcyh2YWx1ZSwgc29y'
        'dF9rZXlzPVRydWUsIHNlcGFyYXRvcnM9KCIsIiwgIjoiKSwgZW5zdXJlX2FzY2lpPVRydWUpLmVuY29kZSgidXRmLTgiKQoKZGVmIF9mYWlsKG1l'
        'c3NhZ2U6IHN0cikgLT4gTm9uZToKICAgIHJhaXNlIEFzc3VyYW5jZVZhbGlkYXRpb25FcnJvcihtZXNzYWdlKQoKZGVmIF9rZXlzKHZhbHVlOiBv'
        'YmplY3QsIGV4cGVjdGVkOiBzZXRbc3RyXSwgbGFiZWw6IHN0cikgLT4gZGljdDoKICAgIGlmIHR5cGUodmFsdWUpIGlzIG5vdCBkaWN0IG9yIHNl'
        'dCh2YWx1ZSkgIT0gZXhwZWN0ZWQ6CiAgICAgICAgX2ZhaWwoZiJ7bGFiZWx9OiBleGFjdCBrZXlzIHJlcXVpcmVkIikKICAgIHJldHVybiB2YWx1'
        'ZQoKZGVmIF9zdHIodmFsdWU6IG9iamVjdCwgbGFiZWw6IHN0cikgLT4gc3RyOgogICAgaWYgdHlwZSh2YWx1ZSkgaXMgbm90IHN0ciBvciBub3Qg'
        'dmFsdWU6CiAgICAgICAgX2ZhaWwoZiJ7bGFiZWx9OiBub24tZW1wdHkgc3RyaW5nIHJlcXVpcmVkIikKICAgIHJldHVybiB2YWx1ZQoKZGVmIF9z'
        'aGEodmFsdWU6IG9iamVjdCwgbGFiZWw6IHN0cikgLT4gc3RyOgogICAgaWYgdHlwZSh2YWx1ZSkgaXMgbm90IHN0ciBvciBub3QgU0hBMjU2X1JF'
        'LmZ1bGxtYXRjaCh2YWx1ZSk6CiAgICAgICAgX2ZhaWwoZiJ7bGFiZWx9OiBsb3dlcmNhc2Ugc2hhMjU2IHJlcXVpcmVkIikKICAgIHJldHVybiB2'
        'YWx1ZQoKZGVmIF9pZGVudGlmaWVyKHZhbHVlOiBvYmplY3QsIGxhYmVsOiBzdHIpIC0+IHN0cjoKICAgIHZhbHVlID0gX3N0cih2YWx1ZSwgbGFi'
        'ZWwpCiAgICBpZiBub3QgSURFTlRJRklFUl9SRS5mdWxsbWF0Y2godmFsdWUpOgogICAgICAgIF9mYWlsKGYie2xhYmVsfTogbG93ZXJjYXNlIGlk'
        'ZW50aWZpZXIgcmVxdWlyZWQiKQogICAgcmV0dXJuIHZhbHVlCgpkZWYgX3BhcnNlX2Nhbm9uaWNhbF91dGNfdGltZXN0YW1wKHZhbHVlOiBvYmpl'
        'Y3QsIGxhYmVsOiBzdHIpIC0+IGRhdGV0aW1lOgogICAgaWYgdHlwZSh2YWx1ZSkgaXMgbm90IHN0ciBvciBub3QgQ0FOT05JQ0FMX1VUQ19USU1F'
        'U1RBTVBfUkUuZnVsbG1hdGNoKHZhbHVlKToKICAgICAgICBfZmFpbChmIntsYWJlbH06IGNhbm9uaWNhbCBVVEMgdGltZXN0YW1wIHJlcXVpcmVk'
        'IikKICAgIHRyeToKICAgICAgICBwYXJzZWQgPSBkYXRldGltZS5zdHJwdGltZSh2YWx1ZSwgIiVZLSVtLSVkVCVIOiVNOiVTWiIpLnJlcGxhY2Uo'
        'dHppbmZvPXRpbWV6b25lLnV0YykKICAgIGV4Y2VwdCBWYWx1ZUVycm9yIGFzIGVycm9yOgogICAgICAgIHJhaXNlIEFzc3VyYW5jZVZhbGlkYXRp'
        'b25FcnJvcihmIntsYWJlbH06IGNhbm9uaWNhbCBVVEMgdGltZXN0YW1wIHJlcXVpcmVkIikgZnJvbSBlcnJvcgogICAgaWYgcGFyc2VkLnR6aW5m'
        'byBpcyBOb25lIG9yIHBhcnNlZC51dGNvZmZzZXQoKSAhPSB0aW1lem9uZS51dGMudXRjb2Zmc2V0KE5vbmUpOgogICAgICAgIF9mYWlsKGYie2xh'
        'YmVsfTogVVRDIHRpbWVzdGFtcCByZXF1aXJlZCIpCiAgICByZXR1cm4gcGFyc2VkCgpkZWYgX3ZhbGlkYXRlX2NvbnRyb2xfcmVjZWlwdF9wYXRo'
        'KHZhbHVlOiBvYmplY3QpIC0+IHN0cjoKICAgIGlmIHR5cGUodmFsdWUpIGlzIG5vdCBzdHIgb3Igbm90IENPTlRST0xfUkVDRUlQVF9QQVRIX1JF'
        'LmZ1bGxtYXRjaCh2YWx1ZSkgb3IgYW55KHNlZ21lbnQgaW4geyIiLCAiLiIsICIuLiJ9IGZvciBzZWdtZW50IGluIHZhbHVlLnNwbGl0KCIvIikp'
        'OgogICAgICAgIF9mYWlsKCJzb3VyY2VfY29udHJvbF9yZWNlaXB0X3BhdGg6IGRvY3MvY29udHJvbCBKU09OIHBhdGggcmVxdWlyZWQiKQogICAg'
        'cmV0dXJuIHZhbHVlCgpkZWYgX2xpc3QodmFsdWU6IG9iamVjdCwgbGFiZWw6IHN0ciwgKiwgc29ydGVkX3VuaXF1ZTogYm9vbCA9IEZhbHNlKSAt'
        'PiBsaXN0OgogICAgaWYgdHlwZSh2YWx1ZSkgaXMgbm90IGxpc3Q6CiAgICAgICAgX2ZhaWwoZiJ7bGFiZWx9OiBsaXN0IHJlcXVpcmVkIikKICAg'
        'IGlmIHNvcnRlZF91bmlxdWUgYW5kIHZhbHVlICE9IHNvcnRlZCh2YWx1ZSkgb3Igc29ydGVkX3VuaXF1ZSBhbmQgbGVuKHZhbHVlKSAhPSBsZW4o'
        'c2V0KHZhbHVlKSk6CiAgICAgICAgX2ZhaWwoZiJ7bGFiZWx9OiBzb3J0ZWQgdW5pcXVlIGxpc3QgcmVxdWlyZWQiKQogICAgcmV0dXJuIHZhbHVl'
        'CgpkZWYgX3dhbGtfZm9yYmlkZGVuKHZhbHVlOiBvYmplY3QpIC0+IE5vbmU6CiAgICBpZiBpc2luc3RhbmNlKHZhbHVlLCBkaWN0KToKICAgICAg'
        'ICBmb3Iga2V5LCBjaGlsZCBpbiB2YWx1ZS5pdGVtcygpOgogICAgICAgICAgICBpZiB0eXBlKGtleSkgaXMgbm90IHN0cjoKICAgICAgICAgICAg'
        'ICAgIF9mYWlsKCJrZXlzIG11c3QgYmUgc3RyaW5ncyIpCiAgICAgICAgICAgIGxvdyA9IGtleS5sb3dlcigpCiAgICAgICAgICAgIGlmIGxvdyBp'
        'biBTRUNSRVRfS0VZUyBvciBsb3cgaW4gRk9SQklEREVOX0tFWVM6CiAgICAgICAgICAgICAgICBfZmFpbChmImZvcmJpZGRlbiBmaWVsZDoge2tl'
        'eX0iKQogICAgICAgICAgICBfd2Fsa19mb3JiaWRkZW4oY2hpbGQpCiAgICBlbGlmIGlzaW5zdGFuY2UodmFsdWUsIGxpc3QpOgogICAgICAgIGZv'
        'ciBjaGlsZCBpbiB2YWx1ZToKICAgICAgICAgICAgX3dhbGtfZm9yYmlkZGVuKGNoaWxkKQogICAgZWxpZiB0eXBlKHZhbHVlKSBpcyBzdHI6CiAg'
        'ICAgICAgaWYgdmFsdWUuc3RhcnRzd2l0aCgiLyIpIG9yIHZhbHVlLnN0YXJ0c3dpdGgoKCJodHRwOi8vIiwgImh0dHBzOi8vIiwgInFudHktYXJ0'
        'aWZhY3Q6Ly8iKSk6CiAgICAgICAgICAgIF9mYWlsKCJhYnNvbHV0ZSBwYXRocywgc3RvcmUgVVJJcywgYW5kIG5ldHdvcmsgVVJMcyBhcmUgZm9y'
        'YmlkZGVuIikKCmRlZiBfYmFzZSh2YWx1ZTogb2JqZWN0LCBraW5kOiBzdHIsIGlkZW50OiBzdHIsIHN0YXR1czogc3RyLCBrZXlzOiBzZXRbc3Ry'
        'XSkgLT4gZGljdDoKICAgIGRhdGEgPSBfa2V5cyh2YWx1ZSwga2V5cywga2luZCkKICAgIGlmIGRhdGFbInNjaGVtYV92ZXJzaW9uIl0gIT0gU0NI'
        'RU1BX1ZFUlNJT04gb3IgZGF0YVsiZG9jdW1lbnRfa2luZCJdICE9IGtpbmQgb3IgZGF0YVsiZG9jdW1lbnRfaWQiXSAhPSBpZGVudCBvciBkYXRh'
        'WyJzdGF0dXMiXSAhPSBzdGF0dXM6CiAgICAgICAgX2ZhaWwoZiJ7a2luZH06IGlkZW50aXR5IG9yIHN0YXR1cyBkcmlmdGVkIikKICAgIF93YWxr'
        'X2ZvcmJpZGRlbihkYXRhKQogICAgcmV0dXJuIGRhdGEKCmRlZiB2YWxpZGF0ZV90ZW1wb3JhbF9hbWVuZG1lbnRfZHJhZnQodmFsdWU6IG9iamVj'
        'dCkgLT4gZGljdDoKICAgIGtleXMgPSB7ImRvY3VtZW50X2lkIiwgImRvY3VtZW50X2tpbmQiLCAiZ292ZXJuZWRfaDAwMV9wcm90b2NvbF9pZCIs'
        'ICJoYXNoX2JpbmRpbmdzIiwgIm5vbl9lZmZlY3RzIiwgInByb3Bvc2VkX2NoYW5nZSIsICJzdGF0dXMiLCAidW5jaGFuZ2VkX2hlbGRfZnVuZGlu'
        'Z19ydWxlIiwgInNjaGVtYV92ZXJzaW9uIn0KICAgIGRhdGEgPSBfYmFzZSh2YWx1ZSwgInFudHlfaDAwMV90ZW1wb3JhbF9jYXVzYWxpdHlfYW1l'
        'bmRtZW50X2RyYWZ0IiwgImNhbmRpZGF0ZTEtaDAwMS10ZW1wb3JhbC1jYXVzYWxpdHktYW1lbmRtZW50LWRyYWZ0LXYwMDEiLCAiRFJBRlRfT05M'
        'WV9OT1RfRUZGRUNUSVZFIiwga2V5cykKICAgIGlmIGRhdGFbImdvdmVybmVkX2gwMDFfcHJvdG9jb2xfaWQiXSAhPSBIMDAxX1BST1RPQ09MX0lE'
        'OgogICAgICAgIF9mYWlsKCJ0ZW1wb3JhbCBwcm90b2NvbCBkcmlmdGVkIikKICAgIF9rZXlzKGRhdGFbImhhc2hfYmluZGluZ3MiXSwgeyJjdXJy'
        'ZW50X2Rlc2lnbl9zaGEyNTYiLCAiY3VycmVudF92YWxpZGF0b3Jfc2hhMjU2IiwgImdvdmVybmFuY2VfYW1lbmRtZW50X3NoYTI1NiJ9LCAiaGFz'
        'aF9iaW5kaW5ncyIpCiAgICBpZiBkYXRhWyJoYXNoX2JpbmRpbmdzIl0gIT0geyJjdXJyZW50X2Rlc2lnbl9zaGEyNTYiOiBIMDAxX0RFU0lHTl9T'
        'SEEyNTYsICJjdXJyZW50X3ZhbGlkYXRvcl9zaGEyNTYiOiBIMDAxX1ZBTElEQVRPUl9TSEEyNTYsICJnb3Zlcm5hbmNlX2FtZW5kbWVudF9zaGEy'
        'NTYiOiBHT1ZFUk5BTkNFX0FNRU5ETUVOVF9TSEEyNTZ9OgogICAgICAgIF9mYWlsKCJ0ZW1wb3JhbCBoYXNoIGJpbmRpbmcgZHJpZnRlZCIpCiAg'
        'ICBfa2V5cyhkYXRhWyJwcm9wb3NlZF9jaGFuZ2UiXSwgeyJjdXJyZW50X3NpZ25hbF9ydWxlIiwgInByb3Bvc2VkX3NpZ25hbF9ydWxlIn0sICJw'
        'cm9wb3NlZF9jaGFuZ2UiKQogICAgaWYgZGF0YVsicHJvcG9zZWRfY2hhbmdlIl0gIT0geyJjdXJyZW50X3NpZ25hbF9ydWxlIjogImZ1bmRpbmdf'
        'dGltZV91dGMgPD0gZGVjaXNpb25fdGltZXN0YW1wIiwgInByb3Bvc2VkX3NpZ25hbF9ydWxlIjogImZ1bmRpbmdfdGltZV91dGMgPCBkZWNpc2lv'
        'bl90aW1lc3RhbXAifToKICAgICAgICBfZmFpbCgidGVtcG9yYWwgcHJvcG9zYWwgZHJpZnRlZCIpCiAgICBpZiBkYXRhWyJ1bmNoYW5nZWRfaGVs'
        'ZF9mdW5kaW5nX3J1bGUiXSAhPSAiZGVjaXNpb25fdGltZXN0YW1wIDwgZnVuZGluZ190aW1lX3V0YyA8PSBpbnRlcnZhbF9jbG9zZSIgb3IgIkNV'
        'UlJFTlRfSDAwMV9QUkVSRUdJU1RSQVRJT05fVU5DSEFOR0VEIiBub3QgaW4gZGF0YVsibm9uX2VmZmVjdHMiXToKICAgICAgICBfZmFpbCgidGVt'
        'cG9yYWwgbm9uLWVmZmVjdHMgZHJpZnRlZCIpCiAgICBpZiBub3QgX2xpc3QoZGF0YVsibm9uX2VmZmVjdHMiXSwgIm5vbl9lZmZlY3RzIiwgc29y'
        'dGVkX3VuaXF1ZT1UcnVlKSBvciAiUFJPUE9TRURfUlVMRV9OT1RfQVBQTElFRCIgbm90IGluIGRhdGFbIm5vbl9lZmZlY3RzIl06CiAgICAgICAg'
        'X2ZhaWwoInRlbXBvcmFsIG5vbi1lZmZlY3RzIG11c3QgcmVtYWluIGV4cGxpY2l0IikKICAgIHJldHVybiBkYXRhCgpkZWYgX3ZhbGlkYXRlX2Jp'
        'bmRpbmdzKGRhdGE6IGRpY3QpIC0+IE5vbmU6CiAgICBiaW5kaW5nID0gX2tleXMoZGF0YVsiaGFzaF9iaW5kaW5ncyJdLCB7ImN1cnJlbnRfZGVz'
        'aWduX3NoYTI1NiIsICJjdXJyZW50X3ZhbGlkYXRvcl9zaGEyNTYiLCAiZ292ZXJuYW5jZV9hbWVuZG1lbnRfc2hhMjU2In0sICJoYXNoX2JpbmRp'
        'bmdzIikKICAgIGlmIGJpbmRpbmcgIT0geyJjdXJyZW50X2Rlc2lnbl9zaGEyNTYiOiBIMDAxX0RFU0lHTl9TSEEyNTYsICJjdXJyZW50X3ZhbGlk'
        'YXRvcl9zaGEyNTYiOiBIMDAxX1ZBTElEQVRPUl9TSEEyNTYsICJnb3Zlcm5hbmNlX2FtZW5kbWVudF9zaGEyNTYiOiBHT1ZFUk5BTkNFX0FNRU5E'
        'TUVOVF9TSEEyNTZ9OgogICAgICAgIF9mYWlsKCJIMDAxIGhhc2ggYmluZGluZ3MgZHJpZnRlZCIpCgpkZWYgdmFsaWRhdGVfY2FsaWJyYXRpb25f'
        'c3BlY19kcmFmdCh2YWx1ZTogb2JqZWN0KSAtPiBkaWN0OgogICAga2V5cyA9IHsiZG9jdW1lbnRfaWQiLCAiZG9jdW1lbnRfa2luZCIsICJoYXNo'
        'X2JpbmRpbmdzIiwgInByb3Bvc2VkX2Rlc2lnbiIsICJwcm9wb3NlZF9kZ3Bfc3VpdGUiLCAicHJvcG9zZWRfZGlhZ25vc3RpY19zdHJlc3NfY2Fz'
        'ZXMiLCAicHJvcG9zZWRfcGFzc19jcml0ZXJpb24iLCAicHJvcG9zZWRfb3V0ZXJfcmVwbGljYXRpb25zIiwgInN0YXR1cyIsICJzY2hlbWFfdmVy'
        'c2lvbiJ9CiAgICBkYXRhID0gX2Jhc2UodmFsdWUsICJxbnR5X2gwMDFfc3ludGhldGljX251bGxfY2FsaWJyYXRpb25fc3BlY19kcmFmdCIsICJo'
        'MDAxLXN5bnRoZXRpYy1udWxsLWNhbGlicmF0aW9uLXNwZWMtZHJhZnQtdjAwMSIsICJEUkFGVF9PTkxZX1VORlJPWkVOX05PVF9FWEVDVVRBQkxF'
        'Iiwga2V5cykKICAgIF92YWxpZGF0ZV9iaW5kaW5ncyhkYXRhKQogICAgZGVzaWduID0gX2tleXMoZGF0YVsicHJvcG9zZWRfZGVzaWduIl0sIHsi'
        'Ym9vdHN0cmFwX3JlcGV0aXRpb25zIiwgImZhbWlseXdpc2VfYWxwaGEiLCAiaDAwMF90ZXN0X3RhcmdldCIsICJoYWNfbGFnIiwgImlubmVyX3By'
        'b2NlZHVyZSIsICJyZWdpc3RlcmVkX3ZhcmlhbnRfc2VyaWVzIiwgInN0YXRpb25hcnlfYmxvY2tfbGVuZ3RoIn0sICJwcm9wb3NlZF9kZXNpZ24i'
        'KQogICAgZXhwZWN0ZWQgPSB7ImJvb3RzdHJhcF9yZXBldGl0aW9ucyI6IDEwMDAwLCAiZmFtaWx5d2lzZV9hbHBoYSI6IDAuMDUsICJoMDAwX3Rl'
        'c3RfdGFyZ2V0IjogInRoZSBleGFjdCByZWdpc3RlcmVkIHN5bmNocm9ub3VzIHN0YXRpb25hcnktYm9vdHN0cmFwIG1heGltdW0tdCBwcm9jZWR1'
        'cmUiLCAiaGFjX2xhZyI6IDIxLCAiaW5uZXJfcHJvY2VkdXJlIjogInN0YXRpb25hcnktYm9vdHN0cmFwIG1heGltdW0tdCIsICJyZWdpc3RlcmVk'
        'X3ZhcmlhbnRfc2VyaWVzIjogOSwgInN0YXRpb25hcnlfYmxvY2tfbGVuZ3RoIjogNjN9CiAgICBpZiBkZXNpZ24gIT0gZXhwZWN0ZWQ6CiAgICAg'
        'ICAgX2ZhaWwoInByb3Bvc2VkIGNhbGlicmF0aW9uIGRlc2lnbiBkcmlmdGVkIikKICAgIGlmIF9saXN0KGRhdGFbInByb3Bvc2VkX2RncF9zdWl0'
        'ZSJdLCAicHJvcG9zZWRfZGdwX3N1aXRlIiwgc29ydGVkX3VuaXF1ZT1UcnVlKSAhPSBbIklJRCBHYXVzc2lhbiIsICJJSUQgU3R1ZGVudC10IHdp'
        'dGggZGY9NSIsICJuaW5lLXNlcmllcyBjb21tb24tZmFjdG9yIGRlcGVuZGVuY2UiLCAic3RhdGlvbmFyeSBBUigxKSwgcGhpPTAuMyIsICJzdGF0'
        'aW9uYXJ5IEFSKDEpLCBwaGk9MC43IiwgInN0YXRpb25hcnkgR0FSQ0goMSwxKS1saWtlIHZvbGF0aWxpdHkiXToKICAgICAgICBfZmFpbCgicmVx'
        'dWlyZWQgREdQIHN1aXRlIGRyaWZ0ZWQiKQogICAgaWYgZGF0YVsicHJvcG9zZWRfb3V0ZXJfcmVwbGljYXRpb25zIl0gIT0gMjAwMCBvciBfbGlz'
        'dChkYXRhWyJwcm9wb3NlZF9kaWFnbm9zdGljX3N0cmVzc19jYXNlcyJdLCAic3RyZXNzIGNhc2VzIiwgc29ydGVkX3VuaXF1ZT1UcnVlKSAhPSBb'
        'ImF1dG9jb3JyZWxhdGlvbiBzdHJ1Y3R1cmFsIGJyZWFrIiwgIm1lYW4temVybyByZWdpbWUgc3dpdGNoaW5nIiwgInNwYXJzZSBleHRyZW1lIG91'
        'dGxpZXJzIiwgInZhcmlhbmNlIHN0cnVjdHVyYWwgYnJlYWsiXToKICAgICAgICBfZmFpbCgiY2FsaWJyYXRpb24gcmVwbGljYXRpb24gb3Igc3Ry'
        'ZXNzIGNhc2VzIGRyaWZ0ZWQiKQogICAgaWYgZGF0YVsicHJvcG9zZWRfcGFzc19jcml0ZXJpb24iXSAhPSAiZm9yIGV2ZXJ5IHJlcXVpcmVkIHN0'
        'YXRpb25hcnkgREdQLCB0aGUgb25lLXNpZGVkIDk1JSBiaW5vbWlhbCB1cHBlciBjb25maWRlbmNlIGJvdW5kIGZvciBlbXBpcmljYWwgRldFUiBp'
        'cyA8PSAwLjA3NSI6CiAgICAgICAgX2ZhaWwoImNhbGlicmF0aW9uIHBhc3MgY3JpdGVyaW9uIGRyaWZ0ZWQiKQogICAgcmV0dXJuIGRhdGEKCmRl'
        'ZiBfZW50cnkodmFsdWU6IG9iamVjdCkgLT4gZGljdDoKICAgIGRhdGEgPSBfa2V5cyh2YWx1ZSwgeyJkYXRhc2V0X3JlZ2lvbl9pZCIsICJkaXNj'
        'bG9zdXJlX2tpbmQiLCAiZGlzY2xvc3VyZV9zdGF0dXMiLCAiZW50cnlfaWQiLCAiaHlwb3RoZXNpc19pZCIsICJwcm90b2NvbF9pZCIsICJyZWNv'
        'cmRlZF9hdF91dGMiLCAicmVnaW9uX2VuZF91dGMiLCAicmVnaW9uX3N0YXJ0X3V0YyIsICJzb3VyY2VfY29udHJvbF9yZWNlaXB0X3BhdGgiLCAi'
        'c291cmNlX2NvbnRyb2xfcmVjZWlwdF9zaGEyNTYifSwgImxlZGdlciBlbnRyeSIpCiAgICBmb3Iga2V5IGluICgiZW50cnlfaWQiLCAicHJvdG9j'
        'b2xfaWQiLCAiaHlwb3RoZXNpc19pZCIsICJkYXRhc2V0X3JlZ2lvbl9pZCIpOgogICAgICAgIF9pZGVudGlmaWVyKGRhdGFba2V5XSwga2V5KQog'
        'ICAgaWYgdHlwZShkYXRhWyJkaXNjbG9zdXJlX2tpbmQiXSkgaXMgbm90IHN0ciBvciBkYXRhWyJkaXNjbG9zdXJlX2tpbmQiXSBub3QgaW4gRElT'
        'Q0xPU1VSRV9LSU5EUzoKICAgICAgICBfZmFpbCgidW5rbm93biBkaXNjbG9zdXJlIGtpbmQiKQogICAgaWYgdHlwZShkYXRhWyJkaXNjbG9zdXJl'
        'X3N0YXR1cyJdKSBpcyBub3Qgc3RyIG9yIGRhdGFbImRpc2Nsb3N1cmVfc3RhdHVzIl0gbm90IGluIERJU0NMT1NVUkVfU1RBVFVTRVM6CiAgICAg'
        'ICAgX2ZhaWwoInVua25vd24gZGlzY2xvc3VyZSBzdGF0dXMiKQogICAgX3ZhbGlkYXRlX2NvbnRyb2xfcmVjZWlwdF9wYXRoKGRhdGFbInNvdXJj'
        'ZV9jb250cm9sX3JlY2VpcHRfcGF0aCJdKQogICAgX3NoYShkYXRhWyJzb3VyY2VfY29udHJvbF9yZWNlaXB0X3NoYTI1NiJdLCAic291cmNlX2Nv'
        'bnRyb2xfcmVjZWlwdF9zaGEyNTYiKQogICAgc3RhcnQgPSBfcGFyc2VfY2Fub25pY2FsX3V0Y190aW1lc3RhbXAoZGF0YVsicmVnaW9uX3N0YXJ0'
        'X3V0YyJdLCAicmVnaW9uX3N0YXJ0X3V0YyIpCiAgICBlbmQgPSBfcGFyc2VfY2Fub25pY2FsX3V0Y190aW1lc3RhbXAoZGF0YVsicmVnaW9uX2Vu'
        'ZF91dGMiXSwgInJlZ2lvbl9lbmRfdXRjIikKICAgIF9wYXJzZV9jYW5vbmljYWxfdXRjX3RpbWVzdGFtcChkYXRhWyJyZWNvcmRlZF9hdF91dGMi'
        'XSwgInJlY29yZGVkX2F0X3V0YyIpCiAgICBpZiBzdGFydCA+PSBlbmQ6CiAgICAgICAgX2ZhaWwoInJlZ2lvbiBib3VuZGFyaWVzIG11c3QgYmUg'
        'aW5jcmVhc2luZyIpCiAgICBfd2Fsa19mb3JiaWRkZW4oZGF0YSkKICAgIHJldHVybiBkYXRhCgpkZWYgX3NlbWFudGljX2Rpc2Nsb3N1cmVfa2V5'
        'KGVudHJ5OiBkaWN0KSAtPiB0dXBsZVtzdHIsIC4uLl06CiAgICByZXR1cm4gdHVwbGUoZW50cnlba2V5XSBmb3Iga2V5IGluICgicHJvdG9jb2xf'
        'aWQiLCAiaHlwb3RoZXNpc19pZCIsICJkYXRhc2V0X3JlZ2lvbl9pZCIsICJyZWdpb25fc3RhcnRfdXRjIiwgInJlZ2lvbl9lbmRfdXRjIiwgImRp'
        'c2Nsb3N1cmVfa2luZCIpKQoKZGVmIF92YWxpZGF0ZV9sZWRnZXJfZW50cmllcyhlbnRyaWVzOiBsaXN0KSAtPiBOb25lOgogICAgc2Vlbl9pZHMg'
        'PSBzZXQoKQogICAgc2Vlbl9zZW1hbnRpY3MgPSBzZXQoKQogICAgcHJldmlvdXNfcmVjb3JkZWRfYXQgPSBOb25lCiAgICBmb3IgZW50cnkgaW4g'
        'ZW50cmllczoKICAgICAgICBpdGVtID0gX2VudHJ5KGVudHJ5KQogICAgICAgIGlmIGl0ZW1bImVudHJ5X2lkIl0gaW4gc2Vlbl9pZHM6CiAgICAg'
        'ICAgICAgIF9mYWlsKCJkdXBsaWNhdGUgZW50cnkgSUQiKQogICAgICAgIHNlZW5faWRzLmFkZChpdGVtWyJlbnRyeV9pZCJdKQogICAgICAgIHNl'
        'bWFudGljX2tleSA9IF9zZW1hbnRpY19kaXNjbG9zdXJlX2tleShpdGVtKQogICAgICAgIGlmIHNlbWFudGljX2tleSBpbiBzZWVuX3NlbWFudGlj'
        'czoKICAgICAgICAgICAgX2ZhaWwoImR1cGxpY2F0ZSBzZW1hbnRpYyBkaXNjbG9zdXJlIikKICAgICAgICBzZWVuX3NlbWFudGljcy5hZGQoc2Vt'
        'YW50aWNfa2V5KQogICAgICAgIHJlY29yZGVkX2F0ID0gX3BhcnNlX2Nhbm9uaWNhbF91dGNfdGltZXN0YW1wKGl0ZW1bInJlY29yZGVkX2F0X3V0'
        'YyJdLCAicmVjb3JkZWRfYXRfdXRjIikKICAgICAgICBpZiBwcmV2aW91c19yZWNvcmRlZF9hdCBpcyBub3QgTm9uZSBhbmQgcmVjb3JkZWRfYXQg'
        'PCBwcmV2aW91c19yZWNvcmRlZF9hdDoKICAgICAgICAgICAgX2ZhaWwoImxlZGdlciBlbnRyaWVzIG11c3QgYmUgb3JkZXJlZCBieSByZWNvcmRl'
        'ZF9hdF91dGMiKQogICAgICAgIHByZXZpb3VzX3JlY29yZGVkX2F0ID0gcmVjb3JkZWRfYXQKCmRlZiB2YWxpZGF0ZV9ob2xkb3V0X2Rpc2Nsb3N1'
        'cmVfbGVkZ2VyKHZhbHVlOiBvYmplY3QpIC0+IGRpY3Q6CiAgICBkYXRhID0gX2tleXModmFsdWUsIHsiZG9jdW1lbnRfaWQiLCAiZG9jdW1lbnRf'
        'a2luZCIsICJlbnRyaWVzIiwgInN0YXR1cyIsICJzY2hlbWFfdmVyc2lvbiJ9LCAicW50eV9nbG9iYWxfcmVhbF9wcm90b2NvbF9ob2xkb3V0X2Rp'
        'c2Nsb3N1cmVfbGVkZ2VyIikKICAgIGlmIGRhdGFbInNjaGVtYV92ZXJzaW9uIl0gIT0gU0NIRU1BX1ZFUlNJT04gb3IgZGF0YVsiZG9jdW1lbnRf'
        'a2luZCJdICE9ICJxbnR5X2dsb2JhbF9yZWFsX3Byb3RvY29sX2hvbGRvdXRfZGlzY2xvc3VyZV9sZWRnZXIiIG9yIGRhdGFbImRvY3VtZW50X2lk'
        'Il0gIT0gImdsb2JhbC1yZWFsLXByb3RvY29sLWhvbGRvdXQtZGlzY2xvc3VyZS1sZWRnZXItdjAwMSI6CiAgICAgICAgX2ZhaWwoInFudHlfZ2xv'
        'YmFsX3JlYWxfcHJvdG9jb2xfaG9sZG91dF9kaXNjbG9zdXJlX2xlZGdlcjogaWRlbnRpdHkgZHJpZnRlZCIpCiAgICBpZiB0eXBlKGRhdGFbInN0'
        'YXR1cyJdKSBpcyBub3Qgc3RyIG9yIGRhdGFbInN0YXR1cyJdIG5vdCBpbiBMRURHRVJfU1RBVFVTRVM6CiAgICAgICAgX2ZhaWwoInVua25vd24g'
        'bGVkZ2VyIHN0YXR1cyIpCiAgICBfd2Fsa19mb3JiaWRkZW4oZGF0YSkKICAgIGVudHJpZXMgPSBfbGlzdChkYXRhWyJlbnRyaWVzIl0sICJlbnRy'
        'aWVzIikKICAgIGlmIGRhdGFbInN0YXR1cyJdID09ICJTQ0hFTUFfSU1QTEVNRU5URURfRU1QVFlfTk9fQkFDS0ZJTEwiIGFuZCBlbnRyaWVzOgog'
        'ICAgICAgIF9mYWlsKCJlbXB0eSBsZWRnZXIgc3RhdHVzIHJlcXVpcmVzIG5vIGVudHJpZXMiKQogICAgaWYgZGF0YVsic3RhdHVzIl0gPT0gIkFQ'
        'UEVORF9PTkxZX01FVEFEQVRBX0RJU0NMT1NVUkVTIiBhbmQgbm90IGVudHJpZXM6CiAgICAgICAgX2ZhaWwoInBvcHVsYXRlZCBsZWRnZXIgc3Rh'
        'dHVzIHJlcXVpcmVzIGVudHJpZXMiKQogICAgX3ZhbGlkYXRlX2xlZGdlcl9lbnRyaWVzKGVudHJpZXMpCiAgICByZXR1cm4gZGF0YQoKZGVmIHZh'
        'bGlkYXRlX2xlZGdlcl9hcHBlbmQocHJldmlvdXM6IGJ5dGVzLCBjYW5kaWRhdGU6IGJ5dGVzKSAtPiBkaWN0OgogICAgaWYgdHlwZShwcmV2aW91'
        'cykgaXMgbm90IGJ5dGVzIG9yIHR5cGUoY2FuZGlkYXRlKSBpcyBub3QgYnl0ZXM6CiAgICAgICAgX2ZhaWwoImxlZGdlciBhcHBlbmQgcmVxdWly'
        'ZXMgY2Fub25pY2FsIEpTT04gYnl0ZXMiKQogICAgYmVmb3JlID0gbG9hZF9hbmRfdmFsaWRhdGVfYXNzdXJhbmNlX3NjYWZmb2xkKHByZXZpb3Vz'
        'LCB2YWxpZGF0ZV9ob2xkb3V0X2Rpc2Nsb3N1cmVfbGVkZ2VyKQogICAgYWZ0ZXIgPSBsb2FkX2FuZF92YWxpZGF0ZV9hc3N1cmFuY2Vfc2NhZmZv'
        'bGQoY2FuZGlkYXRlLCB2YWxpZGF0ZV9ob2xkb3V0X2Rpc2Nsb3N1cmVfbGVkZ2VyKQogICAgb2xkID0gYmVmb3JlWyJlbnRyaWVzIl07IG5ldyA9'
        'IGFmdGVyWyJlbnRyaWVzIl0KICAgIGlmIGxlbihuZXcpIDwgbGVuKG9sZCkgb3IgW2Nhbm9uaWNhbF9qc29uX2J5dGVzKGl0ZW0pIGZvciBpdGVt'
        'IGluIG5ld1s6bGVuKG9sZCldXSAhPSBbY2Fub25pY2FsX2pzb25fYnl0ZXMoaXRlbSkgZm9yIGl0ZW0gaW4gb2xkXToKICAgICAgICBfZmFpbCgi'
        'bGVkZ2VyIGFwcGVuZCBtdXN0IHByZXNlcnZlIHByZXZpb3VzIGVudHJpZXMgYnl0ZS1zZW1hbnRpY2FsbHkgYW5kIGluIG9yZGVyIikKICAgIGlm'
        'IGJlZm9yZVsic3RhdHVzIl0gPT0gIlNDSEVNQV9JTVBMRU1FTlRFRF9FTVBUWV9OT19CQUNLRklMTCIgYW5kIG9sZDoKICAgICAgICBfZmFpbCgi'
        'ZW1wdHkgbGVkZ2VyIGNhbm5vdCBjb250YWluIHByaW9yIGVudHJpZXMiKQogICAgaWYgbGVuKG5ldykgPiBsZW4ob2xkKSBhbmQgYWZ0ZXJbInN0'
        'YXR1cyJdICE9ICJBUFBFTkRfT05MWV9NRVRBREFUQV9ESVNDTE9TVVJFUyI6CiAgICAgICAgX2ZhaWwoImFwcGVuZGVkIGxlZGdlciBtdXN0IHVz'
        'ZSBwb3B1bGF0ZWQgc3RhdHVzIikKICAgIHJldHVybiBhZnRlcgoKZGVmIHZhbGlkYXRlX2ZhaWx1cmVfZG9tYWluX2V2aWRlbmNlX3NjaGVtYSh2'
        'YWx1ZTogb2JqZWN0KSAtPiBkaWN0OgogICAga2V5cyA9IHsiZG9jdW1lbnRfaWQiLCAiZG9jdW1lbnRfa2luZCIsICJmaWVsZF9kZWZpbml0aW9u'
        'cyIsICJxdWFsaWZpY2F0aW9uX2VudW0iLCAic3RhdHVzIiwgInNjaGVtYV92ZXJzaW9uIn0KICAgIGRhdGEgPSBfYmFzZSh2YWx1ZSwgInFudHlf'
        'ZHVyYWJsZV9zdG9yZV9mYWlsdXJlX2RvbWFpbl9ldmlkZW5jZV9zY2hlbWEiLCAiZHVyYWJsZS1zdG9yZS1mYWlsdXJlLWRvbWFpbi1ldmlkZW5j'
        'ZS1zY2hlbWEtdjAwMSIsICJNRVRBREFUQV9TQ0hFTUFfT05MWV9OT19TVE9SRV9BQ0NFU1MiLCBrZXlzKQogICAgaWYgZGF0YVsicXVhbGlmaWNh'
        'dGlvbl9lbnVtIl0gIT0gWyJVTkFTU0VTU0VEIiwgIklOU1VGRklDSUVOVCIsICJDQU5ESURBVEVfTUVUQURBVEFfQ09NUExFVEUiLCAiSU5ERVBF'
        'TkRFTlRfUkVWSUVXX1JFUVVJUkVEIiwgIlFVQUxJRklFRF9CWV9MQVRFUl9HT1ZFUk5BTkNFIiwgIlJFSkVDVEVEIl0gb3IgZGF0YVsiZmllbGRf'
        'ZGVmaW5pdGlvbnMiXSAhPSBbImFkbWluaXN0cmF0aXZlX2ZhaWx1cmVfZG9tYWluX2lkIiwgImNyZWRlbnRpYWxfZmFpbHVyZV9kb21haW5faWQi'
        'LCAiZGVsZXRpb25fcHJvcGFnYXRpb25fZG9tYWluX2lkIiwgImV2aWRlbmNlX2RvY3VtZW50X2hhc2hlcyIsICJldmlkZW5jZV9yZWNvcmRfaWQi'
        'LCAiZ2VvZ3JhcGhpY19mYWlsdXJlX2RvbWFpbl9pZCIsICJwaHlzaWNhbF9mYWlsdXJlX2RvbWFpbl9pZCIsICJxdWFsaWZpY2F0aW9uX3N0YXR1'
        'cyIsICJyZXN0b3JlX29wZXJhdG9yX2RvbWFpbl9pZCIsICJyZXZpZXdfc3RhdHVzIiwgInN0b3JlX2lkIiwgImJhY2tlbmRfa2luZCJdOgogICAg'
        'ICAgIF9mYWlsKCJmYWlsdXJlLWRvbWFpbiBzY2hlbWEgZHJpZnRlZCIpCiAgICByZXR1cm4gZGF0YQoKZGVmIHZhbGlkYXRlX3Jldmlld19wYWNr'
        'ZXRfc2NoZW1hKHZhbHVlOiBvYmplY3QpIC0+IGRpY3Q6CiAgICBrZXlzID0geyJkb2N1bWVudF9pZCIsICJkb2N1bWVudF9raW5kIiwgImZpZWxk'
        'X2RlZmluaXRpb25zIiwgImZvcmJpZGRlbl9jb250ZW50IiwgInN0YXR1cyIsICJzY2hlbWFfdmVyc2lvbiJ9CiAgICBkYXRhID0gX2Jhc2UodmFs'
        'dWUsICJxbnR5X3JlcGxheWFibGVfcmV2aWV3X2V2aWRlbmNlX3BhY2tldF9zY2hlbWEiLCAicmVwbGF5YWJsZS1yZXZpZXctZXZpZGVuY2UtcGFj'
        'a2V0LXNjaGVtYS12MDAxIiwgIlNDSEVNQV9PTkxZX05PX1JFVklFV19QQUNLRVRfQ1JFQVRFRCIsIGtleXMpCiAgICBpZiBkYXRhWyJmaWVsZF9k'
        'ZWZpbml0aW9ucyJdICE9IFsiY29tbWFuZHMiLCAiZW52aXJvbm1lbnRfaWRlbnRpdHkiLCAiZmluZGluZ19jb3VudHMiLCAiaGFybmVzc19zb3Vy'
        'Y2VfaGFzaGVzIiwgInJlZGFjdGlvbl9tYW5pZmVzdCIsICJyZXZpZXdfaWQiLCAicmV2aWV3X2tpbmQiLCAicmV2aWV3X3NwZWNpZmljYXRpb25f'
        'aGFzaCIsICJyZXZpZXdlZF9hcnRpZmFjdF9oYXNoZXMiLCAicmV2aWV3ZWRfY29tbWl0X3NoYSIsICJzdGRlcnJfYXJ0aWZhY3RfaGFzaGVzIiwg'
        'InN0ZG91dF9hcnRpZmFjdF9oYXNoZXMiLCAidmVyZGljdCJdOgogICAgICAgIF9mYWlsKCJyZXZpZXcgcGFja2V0IHNjaGVtYSBkcmlmdGVkIikK'
        'ICAgIGlmIGRhdGFbImZvcmJpZGRlbl9jb250ZW50Il0gIT0gWyJBUEkgdG9rZW5zIiwgImNoYWluLW9mLXRob3VnaHQiLCAiY3JlZGVudGlhbHMi'
        'LCAiZW52aXJvbm1lbnQgc2VjcmV0IHZhbHVlcyIsICJob2xkb3V0IGJ5dGVzIiwgInByaXZhdGUga2V5cyIsICJyZWFsIGRhdGFzZXQgYnl0ZXMi'
        'LCAic2NpZW50aWZpYyBlZGdlIGNsYWltcyIsICJzZXNzaW9uIGNvb2tpZXMiLCAidW5yZWRhY3RlZCBzZWNyZXQtYmVhcmluZyBjb21tYW5kIG91'
        'dHB1dCJdOgogICAgICAgIF9mYWlsKCJyZXZpZXcgcGFja2V0IGZvcmJpZGRlbiBjb250ZW50IGRyaWZ0ZWQiKQogICAgcmV0dXJuIGRhdGEKCmRl'
        'ZiB2YWxpZGF0ZV9zeW50aGV0aWNfY2FuYXJ5X3NjYWZmb2xkKHZhbHVlOiBvYmplY3QpIC0+IGRpY3Q6CiAgICBrZXlzID0geyJkb2N1bWVudF9p'
        'ZCIsICJkb2N1bWVudF9raW5kIiwgInBheWxvYWRzIiwgInN0YXR1cyIsICJzY2hlbWFfdmVyc2lvbiJ9CiAgICBkYXRhID0gX2Jhc2UodmFsdWUs'
        'ICJxbnR5X3N5bnRoZXRpY19hcnRpZmFjdF9jYW5hcnlfc2NhZmZvbGQiLCAic3ludGhldGljLWFydGlmYWN0LWNhbmFyeS1zY2FmZm9sZC12MDAx'
        'IiwgIlNDQUZGT0xEX09OTFlfTk9UX0VYRUNVVEVEIiwga2V5cykKICAgIGlmIGRhdGFbInBheWxvYWRzIl0gIT0gW3siY29udGVudCI6ICJRTlRZ'
        'X1NZTlRIRVRJQ19DQU5BUllfQUxQSEFfVjEiLCAicmVsYXRpdmVfcGF0aCI6ICJhbHBoYS9wYXlsb2FkLnR4dCIsICJyb2xlIjogInN5bnRoZXRp'
        'Yy1hbHBoYSIsICJzaGEyNTYiOiBoYXNobGliLnNoYTI1NihiIlFOVFlfU1lOVEhFVElDX0NBTkFSWV9BTFBIQV9WMSIpLmhleGRpZ2VzdCgpLCAi'
        'c2l6ZSI6IDMwfSwgeyJjb250ZW50X2hleCI6ICIwMDUxNGU1NDU5ZmYiLCAicmVsYXRpdmVfcGF0aCI6ICJiZXRhL3BheWxvYWQuYmluIiwgInJv'
        'bGUiOiAic3ludGhldGljLWJldGEiLCAic2hhMjU2IjogaGFzaGxpYi5zaGEyNTYoYnl0ZXMuZnJvbWhleCgiMDA1MTRlNTQ1OWZmIikpLmhleGRp'
        'Z2VzdCgpLCAic2l6ZSI6IDZ9XToKICAgICAgICBfZmFpbCgiY2FuYXJ5IGRlc2NyaXB0b3IgZHJpZnRlZCIpCiAgICByZXR1cm4gZGF0YQoKZGVm'
        'IGJ1aWxkX3N5bnRoZXRpY19jYW5hcnlfcGF5bG9hZHMoKSAtPiBkaWN0W3N0ciwgYnl0ZXNdOgogICAgcmV0dXJuIHsiYWxwaGEvcGF5bG9hZC50'
        'eHQiOiBiIlFOVFlfU1lOVEhFVElDX0NBTkFSWV9BTFBIQV9WMSIsICJiZXRhL3BheWxvYWQuYmluIjogYnl0ZXMuZnJvbWhleCgiMDA1MTRlNTQ1'
        'OWZmIil9CgpkZWYgbG9hZF9hbmRfdmFsaWRhdGVfYXNzdXJhbmNlX3NjYWZmb2xkKHZhbHVlOiBvYmplY3QsIHZhbGlkYXRvcikgLT4gZGljdDoK'
        'ICAgIGlmIHR5cGUodmFsdWUpIG5vdCBpbiAoYnl0ZXMsIGJ5dGVhcnJheSk6IF9mYWlsKCJjYW5vbmljYWwgSlNPTiBieXRlcyByZXF1aXJlZCIp'
        'CiAgICBwYXJzZWQgPSBqc29uLmxvYWRzKGJ5dGVzKHZhbHVlKS5kZWNvZGUoInV0Zi04IikpCiAgICBpZiBjYW5vbmljYWxfanNvbl9ieXRlcyhw'
        'YXJzZWQpICE9IGJ5dGVzKHZhbHVlKTogX2ZhaWwoIm5vbi1jYW5vbmljYWwgSlNPTiBieXRlcyIpCiAgICByZXR1cm4gdmFsaWRhdG9yKHBhcnNl'
        'ZCkKCgpfSDAwMV9URU1QT1JBTF9SRVJFVklFV19SRUNPUkRfS0VZUyA9IHsKICAgICJhcnRpZmFjdF9iaW5kaW5ncyIsICJjYW5kaWRhdGVfcmV2'
        'aWV3X3Njb3BlIiwgImNsb3NlZF9maW5kaW5ncyIsICJkb2N1bWVudF9pZCIsCiAgICAiZG9jdW1lbnRfa2luZCIsICJmaW5hbF9maW5kaW5nX2Nv'
        'dW50cyIsICJmaW5hbF92ZXJkaWN0IiwgIm5vbl9lZmZlY3RzIiwKICAgICJwcmVyZWdpc3RlcmVkIiwgInJlY29yZGVkX2FmdGVyX3JldmlldyIs'
        'ICJyZXBhaXJfc2NvcGUiLCAicmV2aWV3X2JpbmRpbmdzIiwKICAgICJyZXZpZXdfaWQiLCAicmV2aWV3X3Jlc3VsdHMiLCAic2NoZW1hX3ZlcnNp'
        'b24iLCAic3RhdHVzIiwKfQpfSDAwMV9URU1QT1JBTF9SRVJFVklFV19BUlRJRkFDVFMgPSBbCiAgICB7InBhdGgiOiAiZG9jcy9jb250cm9sL2Ft'
        'ZW5kbWVudHMvY2FuZGlkYXRlMV9oMDAxX3RlbXBvcmFsX2NhdXNhbGl0eV92MDAxLmpzb24iLCAic2hhMjU2IjogIjJlOGMwN2FjM2VhMjcyMWUx'
        'ODJhODJjZTg0MzdjYzhkYjRhZGVmMGY0YTBlYzE3MDY2ZDI5ZjY1MzE0ZGE4MjkifSwKICAgIHsicGF0aCI6ICJkb2NzL2NvbnRyb2wvdGFza3Mv'
        'UkVDT1ZFUl9PUl9SRVRJUkVfQ0FORElEQVRFMV9WMF9GUk9aRU5fSU5QVVQvaGFuZG9mZl92MDE2Lmpzb24iLCAic2hhMjU2IjogIjM0YmZmN2Rm'
        'NTQyYWY0NjE0YjA4MjQ3ODMwMTQ0MWM4NmQ0MTEyNmI5MDMzOTU0ODViOGMwYWU5MDI4ZGVmNmEifSwKICAgIHsicGF0aCI6ICJkb2NzL2V4cGVy'
        'aW1lbnRzL2NhbmRpZGF0ZTFfaDAwMV9yZWFsX2RhdGFfZmFsc2lmaWNhdGlvbl90ZW1wb3JhbF9jYW5kaWRhdGVfdjAwMS5qc29uIiwgInNoYTI1'
        'NiI6ICJjNmZiOGQ3OTY1NTljNTMxODhjMTBlNzI5YTIyNTdiYzU5M2M3YTgwNTI2OTYzYzk3NTE1Zjc0NzgyMGUyMjc2In0sCiAgICB7InBhdGgi'
        'OiAicXVhbnRib3QvZXhwZXJpbWVudC9oMDAxX3RlbXBvcmFsX2NhdXNhbGl0eS5weSIsICJzaGEyNTYiOiAiYmUzZjliNGFhMjI5MzA5YWY2OTc0'
        'ZWZlZWVhNDU4MTg5ZjFiZGJmMmI4OGQyOGNmYzRlNDI4NGJmZDU2NmY0ZiJ9LAogICAgeyJwYXRoIjogInRlc3RzL2V4cGVyaW1lbnQvdGVzdF9o'
        'MDAxX3RlbXBvcmFsX2NhdXNhbGl0eS5weSIsICJzaGEyNTYiOiAiMGUxZGVhMmUxZWMwNmNlYTE0ZjExNDU1NDAyMjgyYzU2ZGQ1ZWY1OThlZDU0'
        'YjNhZDQwMTc3NGQ0ZDdlYTYyOCJ9LApdCl9IMDAxX1RFTVBPUkFMX1JFUkVWSUVXX1BSX1NDT1BFID0gWwogICAgImRvY3MvY29udHJvbC9hY3Rp'
        'dmVfdGFzay5qc29uIiwgImRvY3MvY29udHJvbC9hbWVuZG1lbnRzL2NhbmRpZGF0ZTFfaDAwMV90ZW1wb3JhbF9jYXVzYWxpdHlfdjAwMS5qc29u'
        'IiwKICAgICJkb2NzL2NvbnRyb2wvdGFza3MvUkVDT1ZFUl9PUl9SRVRJUkVfQ0FORElEQVRFMV9WMF9GUk9aRU5fSU5QVVQvaGFuZG9mZl92MDE2'
        'Lmpzb24iLAogICAgImRvY3MvZXhwZXJpbWVudHMvY2FuZGlkYXRlMV9oMDAxX3JlYWxfZGF0YV9mYWxzaWZpY2F0aW9uX3RlbXBvcmFsX2NhbmRp'
        'ZGF0ZV92MDAxLmpzb24iLAogICAgInF1YW50Ym90L2NvbnRpbnVpdHkvY29udGV4dC5weSIsICJxdWFudGJvdC9leHBlcmltZW50L2gwMDFfdGVt'
        'cG9yYWxfY2F1c2FsaXR5LnB5IiwKICAgICJ0ZXN0cy9jb250aW51aXR5L3Rlc3RfY3Jvc3NfYWdlbnRfY29udGludWl0eS5weSIsICJ0ZXN0cy9l'
        'eHBlcmltZW50L3Rlc3RfaDAwMV90ZW1wb3JhbF9jYXVzYWxpdHkucHkiLApdCl9IMDAxX1RFTVBPUkFMX1JFUkVWSUVXX1JFUEFJUl9TQ09QRSA9'
        'IFsKICAgICJkb2NzL2NvbnRyb2wvYWN0aXZlX3Rhc2suanNvbiIsCiAgICAiZG9jcy9jb250cm9sL2FtZW5kbWVudHMvY2FuZGlkYXRlMV9oMDAx'
        'X3RlbXBvcmFsX2NhdXNhbGl0eV92MDAxLmpzb24iLAogICAgImRvY3MvY29udHJvbC90YXNrcy9SRUNPVkVSX09SX1JFVElSRV9DQU5ESURBVEUx'
        'X1YwX0ZST1pFTl9JTlBVVC9oYW5kb2ZmX3YwMTYuanNvbiIsCiAgICAicXVhbnRib3QvY29udGludWl0eS9jb250ZXh0LnB5IiwgInF1YW50Ym90'
        'L2V4cGVyaW1lbnQvaDAwMV90ZW1wb3JhbF9jYXVzYWxpdHkucHkiLAogICAgInRlc3RzL2NvbnRpbnVpdHkvdGVzdF9jcm9zc19hZ2VudF9jb250'
        'aW51aXR5LnB5IiwgInRlc3RzL2V4cGVyaW1lbnQvdGVzdF9oMDAxX3RlbXBvcmFsX2NhdXNhbGl0eS5weSIsCl0KX0gwMDFfVEVNUE9SQUxfUkVS'
        'RVZJRVdfTk9OX0VGRkVDVFMgPSBbCiAgICAiQU1FTkRNRU5UX05PVF9FRkZFQ1RJVkUiLCAiQkxPQ0tfTElWRV9JTlRFR1JBVElPTiIsICJDVVJS'
        'RU5UX0gwMDFfQ09OVFJBQ1RfVU5DSEFOR0VEIiwKICAgICJDVVJSRU5UX1NJR05BTF9SVUxFX1JFTUFJTlNfTFRFIiwgIkVER0VfVU5QUk9WRU4i'
        'LCAiTk9fQVJUSUZBQ1RfT1JfU1RPUkVfQUNDRVNTIiwKICAgICJOT19DQUxJQlJBVElPTl9GUkVFWkVfT1JfRVhFQ1VUSU9OIiwgIk5PX0NBTkFS'
        'WV9FWEVDVVRJT04iLCAiTk9fRVhFQ1VUSU9OX0NPVU5UX0NPTlNVTUVEIiwKICAgICJOT19IMDAxX0VYRUNVVElPTiIsICJOT19MSVZFX0FVVEhP'
        'UklUWSIsICJOT19NQVJLRVRfRURHRV9DTEFJTSIsICJOT19QQVBFUl9UUkFESU5HX0FVVEhPUklUWSIsCiAgICAiTk9fUkVBTF9EQVRBX0FDQ0VT'
        'UyIsICJOT19TQ0lFTlRJRklDX0FVVEhPUklUWSIsCl0KCgpkZWYgX3JlamVjdF9kdXBsaWNhdGVfanNvbl9rZXlzKHBhaXJzKToKICAgIHJlc3Vs'
        'dCA9IHt9CiAgICBmb3Iga2V5LCB2YWx1ZSBpbiBwYWlyczoKICAgICAgICBpZiBrZXkgaW4gcmVzdWx0OgogICAgICAgICAgICByYWlzZSBBc3N1'
        'cmFuY2VWYWxpZGF0aW9uRXJyb3IoImR1cGxpY2F0ZSBKU09OIGtleSIpCiAgICAgICAgcmVzdWx0W2tleV0gPSB2YWx1ZQogICAgcmV0dXJuIHJl'
        'c3VsdAoKCmRlZiB2YWxpZGF0ZV9oMDAxX3RlbXBvcmFsX2NhbmRpZGF0ZV9yZXJldmlld19yZWNvcmQocmF3OiBieXRlcykgLT4gZGljdDoKICAg'
        'IGlmIHR5cGUocmF3KSBpcyBub3QgYnl0ZXM6CiAgICAgICAgX2ZhaWwoImV4YWN0IGJ5dGVzIGlucHV0IHJlcXVpcmVkIikKICAgIHRyeToKICAg'
        'ICAgICBwYXJzZWQgPSBqc29uLmxvYWRzKHJhdy5kZWNvZGUoInV0Zi04IiksIG9iamVjdF9wYWlyc19ob29rPV9yZWplY3RfZHVwbGljYXRlX2pz'
        'b25fa2V5cykKICAgIGV4Y2VwdCAoVW5pY29kZURlY29kZUVycm9yLCBqc29uLkpTT05EZWNvZGVFcnJvciwgQXNzdXJhbmNlVmFsaWRhdGlvbkVy'
        'cm9yKSBhcyBlcnJvcjoKICAgICAgICByYWlzZSBBc3N1cmFuY2VWYWxpZGF0aW9uRXJyb3IoInN0cmljdCBVVEYtOCBKU09OIHdpdGhvdXQgZHVw'
        'bGljYXRlIGtleXMgcmVxdWlyZWQiKSBmcm9tIGVycm9yCiAgICBpZiBjYW5vbmljYWxfanNvbl9ieXRlcyhwYXJzZWQpICE9IHJhdzoKICAgICAg'
        'ICBfZmFpbCgibm9uLWNhbm9uaWNhbCBKU09OIGJ5dGVzIikKICAgIGRhdGEgPSBfYmFzZShwYXJzZWQsICJxbnR5X2gwMDFfdGVtcG9yYWxfY2F1'
        'c2FsaXR5X2FtZW5kbWVudF9jYW5kaWRhdGVfcmVyZXZpZXdfcmVjb3JkIiwgImNhbmRpZGF0ZTEtaDAwMS10ZW1wb3JhbC1jYXVzYWxpdHktYW1l'
        'bmRtZW50LWNhbmRpZGF0ZS1yZXJldmlldy12MDAxIiwgIlJFQ09SREVEX0FGVEVSX1JFVklFV19OT1RfUFJFUkVHSVNURVJFRCIsIF9IMDAxX1RF'
        'TVBPUkFMX1JFUkVWSUVXX1JFQ09SRF9LRVlTKQogICAgaWYgZGF0YVsicmVjb3JkZWRfYWZ0ZXJfcmV2aWV3Il0gaXMgbm90IFRydWUgb3IgZGF0'
        'YVsicHJlcmVnaXN0ZXJlZCJdIGlzIG5vdCBGYWxzZToKICAgICAgICBfZmFpbCgicmV2aWV3IHJlY29yZCBtdXN0IGJlIHJlY29yZGVkIGFmdGVy'
        'IHJldmlldyBhbmQgbm90IHByZXJlZ2lzdGVyZWQiKQogICAgaWYgZGF0YVsicmV2aWV3X2JpbmRpbmdzIl0gIT0gewogICAgICAgICJjYW5kaWRh'
        'dGVfYmFzZV9jb21taXQiOiAiMzBhNjliYTFiYTZhMTkwODg4OGZmMWIzNGJkYzA3MmJkMDMwZTk5MSIsICJjYW5kaWRhdGVfbWVyZ2VfY29tbWl0'
        'IjogIjUxODVhZGQyZTVkYTVhZGQzMDlkMjYwMmE0NzNjMjM1NTdlM2MxMDIiLAogICAgICAgICJmaW5hbF9yZXZpZXdlZF9oZWFkIjogIjc0NTU0'
        'ZTE1ZjkyY2RiN2Y2YzIyMjM4NzY2YmQ2ZTFmMTZiNjBiZjQiLCAiaW5pdGlhbF9yZXZpZXdlZF9oZWFkIjogIjk5ODFhNDY2ZDg0NzMwNTU3MGY3'
        'ZTIzODI2ZjBjOWY0MGE3NDQ2YTkiLCAicHJfbnVtYmVyIjogMjg0LAogICAgfToKICAgICAgICBfZmFpbCgicmV2aWV3IGJpbmRpbmcgZHJpZnRl'
        'ZCIpCiAgICBpZiBkYXRhWyJjbG9zZWRfZmluZGluZ3MiXSAhPSBbIlBVQkxJQ19DQU5ESURBVEVfTE9BREVSX0FDQ0VQVEVEX01BVEVSSUFMX0RP'
        'Q1VNRU5UX0RSSUZUIiwgIlRFTVBPUkFMX01PRFVMRV9BTkRfVEVTVF9IQVNIRVNfV0VSRV9TRUxGX0RFUklWRUQiXToKICAgICAgICBfZmFpbCgi'
        'Y2xvc2VkIGZpbmRpbmdzIGRyaWZ0ZWQiKQogICAgaWYgZGF0YVsiZmluYWxfdmVyZGljdCJdICE9ICJRTlRZX0gwMDFfVEVNUE9SQUxfQ0FVU0FM'
        'SVRZX0FNRU5ETUVOVF9DQU5ESURBVEVfUkVSRVZJRVdfUEFTU0VEIjoKICAgICAgICBfZmFpbCgiZmluYWwgcmV2aWV3IHZlcmRpY3QgZHJpZnRl'
        'ZCIpCiAgICBpZiBkYXRhWyJmaW5hbF9maW5kaW5nX2NvdW50cyJdICE9IHsiYmxvY2tlciI6IDAsICJtYWpvciI6IDAsICJtaW5vciI6IDB9Ogog'
        'ICAgICAgIF9mYWlsKCJmaW5hbCBmaW5kaW5nIGNvdW50cyBtdXN0IGJlIHplcm8iKQogICAgaWYgZGF0YVsiYXJ0aWZhY3RfYmluZGluZ3MiXSAh'
        'PSBfSDAwMV9URU1QT1JBTF9SRVJFVklFV19BUlRJRkFDVFM6CiAgICAgICAgX2ZhaWwoInJldmlld2VkIGFydGlmYWN0IGJpbmRpbmdzIGRyaWZ0'
        'ZWQiKQogICAgaWYgZGF0YVsiY2FuZGlkYXRlX3Jldmlld19zY29wZSJdICE9IF9IMDAxX1RFTVBPUkFMX1JFUkVWSUVXX1BSX1NDT1BFIG9yIGRh'
        'dGFbInJlcGFpcl9zY29wZSJdICE9IF9IMDAxX1RFTVBPUkFMX1JFUkVWSUVXX1JFUEFJUl9TQ09QRToKICAgICAgICBfZmFpbCgicmV2aWV3IHNj'
        'b3BlIGRyaWZ0ZWQiKQogICAgaWYgZGF0YVsicmV2aWV3X3Jlc3VsdHMiXSAhPSB7ImFzc3VyYW5jZSI6ICI2NyBwYXNzZWQiLCAiYXJ0aWZhY3Rz'
        'IjogIjEwMyBwYXNzZWQiLCAiY29udGludWl0eSI6ICIzNTYgcGFzc2VkLCA3IHNraXBwZWQiLCAiY3VycmVudF9wcmVyZWdpc3RyYXRpb24iOiAi'
        'NTM0IHBhc3NlZCIsICJleHBvcnRlZF90ZW1wb3JhbF9jb250aW51aXR5IjogIjM5MCBwYXNzZWQsIDcgc2tpcHBlZCIsICJmdWxsX3N1aXRlIjog'
        'IjYyODYgcGFzc2VkLCA3IHNraXBwZWQiLCAicmVsZWFzZV9zbW9rZSI6ICI2IHBhc3NlZCIsICJyZW1vdGVfY2kiOiAiQUxMX1JFUE9SVEVEX0NI'
        'RUNLU19TVUNDRVNTIiwgInNhbmRib3giOiAiNTMgcGFzc2VkIiwgInRlbXBvcmFsIjogIjM0IHBhc3NlZCJ9OgogICAgICAgIF9mYWlsKCJyZXZp'
        'ZXcgcmVzdWx0cyBkcmlmdGVkIikKICAgIGlmIGRhdGFbIm5vbl9lZmZlY3RzIl0gIT0gX0gwMDFfVEVNUE9SQUxfUkVSRVZJRVdfTk9OX0VGRkVD'
        'VFM6CiAgICAgICAgX2ZhaWwoInJldmlldyBub24tZWZmZWN0cyBtdXN0IGJlIHNvcnRlZCBhbmQgdW5pcXVlIikKICAgIGZvciBhcnRpZmFjdCBp'
        'biBkYXRhWyJhcnRpZmFjdF9iaW5kaW5ncyJdOgogICAgICAgIF9rZXlzKGFydGlmYWN0LCB7InBhdGgiLCAic2hhMjU2In0sICJhcnRpZmFjdCBi'
        'aW5kaW5nIikKICAgICAgICBfc2hhKGFydGlmYWN0WyJzaGEyNTYiXSwgImFydGlmYWN0IGJpbmRpbmcgc2hhMjU2IikKICAgICAgICBfcmVxdWly'
        'ZV9yZXBvX3JlbGF0aXZlX3Jldmlld19wYXRoKGFydGlmYWN0WyJwYXRoIl0pCiAgICByZXR1cm4gZGF0YQoKCmRlZiBfcmVxdWlyZV9yZXBvX3Jl'
        'bGF0aXZlX3Jldmlld19wYXRoKHBhdGg6IG9iamVjdCkgLT4gc3RyOgogICAgaWYgdHlwZShwYXRoKSBpcyBub3Qgc3RyIG9yIG5vdCByZS5mdWxs'
        'bWF0Y2gociJbQS1aYS16MC05Ll8vLV0rIiwgcGF0aCkgb3IgcGF0aC5zdGFydHN3aXRoKCIvIikgb3IgIi4uIiBpbiBwYXRoLnNwbGl0KCIvIik6'
        'CiAgICAgICAgX2ZhaWwoInVuc2FmZSByZXBvc2l0b3J5LXJlbGF0aXZlIHJldmlldyBwYXRoIikKICAgIHJldHVybiBwYXRoCg=='
    ),
    'quantbot/assurance/h001_null_calibration.py': (
        'IiIiTm9uLWV4ZWN1dGFibGUgcGxhbm5pbmcgYm91bmRhcnkgZm9yIGEgZnV0dXJlIEgwMDEgbnVsbCBjYWxpYnJhdGlvbi4iIiIKZnJvbSBfX2Z1'
        'dHVyZV9fIGltcG9ydCBhbm5vdGF0aW9ucwoKZnJvbSB0eXBpbmcgaW1wb3J0IE5vUmV0dXJuCmZyb20gLmNvbnRyYWN0cyBpbXBvcnQgQXNzdXJh'
        'bmNlVmFsaWRhdGlvbkVycm9yLCB2YWxpZGF0ZV9jYWxpYnJhdGlvbl9zcGVjX2RyYWZ0CgpTVVBQT1JURURfREdQUyA9ICgiSUlEIEdhdXNzaWFu'
        'IiwgIklJRCBTdHVkZW50LXQgd2l0aCBkZj01IiwgInN0YXRpb25hcnkgQVIoMSksIHBoaT0wLjMiLCAic3RhdGlvbmFyeSBBUigxKSwgcGhpPTAu'
        'NyIsICJzdGF0aW9uYXJ5IEdBUkNIKDEsMSktbGlrZSB2b2xhdGlsaXR5IiwgIm5pbmUtc2VyaWVzIGNvbW1vbi1mYWN0b3IgZGVwZW5kZW5jZSIp'
        'CgpkZWYgZGV0ZXJtaW5pc3RpY19zZWVkX2RvbWFpbihzcGVjX2lkOiBzdHIpIC0+IHN0cjoKICAgIHJldHVybiBmImgwMDEtbnVsbC1jYWxpYnJh'
        'dGlvbi97c3BlY19pZH0vc3ludGhldGljLW9ubHkiCgpkZWYgYnVpbGRfY2FsaWJyYXRpb25fZXhlY3V0aW9uX3BsYW4oc3BlYzogb2JqZWN0KSAt'
        'PiBOb1JldHVybjoKICAgIHZhbGlkYXRlX2NhbGlicmF0aW9uX3NwZWNfZHJhZnQoc3BlYykKICAgIHJhaXNlIEFzc3VyYW5jZVZhbGlkYXRpb25F'
        'cnJvcigiQ0FMSUJSQVRJT05fU1BFQ19OT1RfRlJPWkVOIikKCmRlZiBleGVjdXRlX2NhbGlicmF0aW9uKCphcmdzOiBvYmplY3QsICoqa3dhcmdz'
        'OiBvYmplY3QpIC0+IE5vbmU6CiAgICByYWlzZSBBc3N1cmFuY2VWYWxpZGF0aW9uRXJyb3IoIkNBTElCUkFUSU9OX0VYRUNVVElPTl9OT1RfQVVU'
        'SE9SSVpFRCIpCg=='
    ),
    'tests/assurance/test_contracts.py': (
        'aW1wb3J0IGFzdAppbXBvcnQgaGFzaGxpYgppbXBvcnQganNvbgppbXBvcnQgc3VicHJvY2Vzcwpmcm9tIHBhdGhsaWIgaW1wb3J0IFBhdGgKCmlt'
        'cG9ydCBweXRlc3QKCmZyb20gcXVhbnRib3QuYXNzdXJhbmNlIGltcG9ydCBjb250cmFjdHMKClJPT1QgPSBQYXRoKF9fZmlsZV9fKS5wYXJlbnRz'
        'WzJdCkRPQ1MgPSBST09UIC8gImRvY3MvYXNzdXJhbmNlIgpSRVZJRVdTID0gRE9DUyAvICJyZXZpZXdzIgpURU1QT1JBTF9SRVJFVklFVyA9IFJF'
        'VklFV1MgLyAiaDAwMV90ZW1wb3JhbF9jYXVzYWxpdHlfYW1lbmRtZW50X2NhbmRpZGF0ZV9yZXJldmlld19yZWNvcmRfdjAwMS5qc29uIgpWQUxJ'
        'REFUT1JTID0gewogICAgImgwMDFfdGVtcG9yYWxfY2F1c2FsaXR5X2FtZW5kbWVudF9kcmFmdF92MDAxLmpzb24iOiBjb250cmFjdHMudmFsaWRh'
        'dGVfdGVtcG9yYWxfYW1lbmRtZW50X2RyYWZ0LAogICAgImgwMDFfc3ludGhldGljX251bGxfY2FsaWJyYXRpb25fc3BlY19kcmFmdF92MDAxLmpz'
        'b24iOiBjb250cmFjdHMudmFsaWRhdGVfY2FsaWJyYXRpb25fc3BlY19kcmFmdCwKICAgICJnbG9iYWxfcmVhbF9wcm90b2NvbF9ob2xkb3V0X2Rp'
        'c2Nsb3N1cmVfbGVkZ2VyX3YwMDEuanNvbiI6IGNvbnRyYWN0cy52YWxpZGF0ZV9ob2xkb3V0X2Rpc2Nsb3N1cmVfbGVkZ2VyLAogICAgImR1cmFi'
        'bGVfc3RvcmVfZmFpbHVyZV9kb21haW5fZXZpZGVuY2Vfc2NoZW1hX3YwMDEuanNvbiI6IGNvbnRyYWN0cy52YWxpZGF0ZV9mYWlsdXJlX2RvbWFp'
        'bl9ldmlkZW5jZV9zY2hlbWEsCiAgICAicmVwbGF5YWJsZV9yZXZpZXdfZXZpZGVuY2VfcGFja2V0X3NjaGVtYV92MDAxLmpzb24iOiBjb250cmFj'
        'dHMudmFsaWRhdGVfcmV2aWV3X3BhY2tldF9zY2hlbWEsCiAgICAic3ludGhldGljX2FydGlmYWN0X2NhbmFyeV9zY2FmZm9sZF92MDAxLmpzb24i'
        'OiBjb250cmFjdHMudmFsaWRhdGVfc3ludGhldGljX2NhbmFyeV9zY2FmZm9sZCwKfQoKZGVmIHJlYWQobmFtZSk6CiAgICByZXR1cm4gKERPQ1Mg'
        'LyBuYW1lKS5yZWFkX2J5dGVzKCkKCmRlZiB0ZXN0X2NvbW1pdHRlZF9kb2N1bWVudHNfYXJlX2Nhbm9uaWNhbF9hbmRfdmFsaWRhdGUoKToKICAg'
        'IGZvciBuYW1lLCB2YWxpZGF0b3IgaW4gVkFMSURBVE9SUy5pdGVtcygpOgogICAgICAgIHJhdyA9IHJlYWQobmFtZSkKICAgICAgICBwYXJzZWQg'
        'PSBjb250cmFjdHMubG9hZF9hbmRfdmFsaWRhdGVfYXNzdXJhbmNlX3NjYWZmb2xkKHJhdywgdmFsaWRhdG9yKQogICAgICAgIGFzc2VydCBjb250'
        'cmFjdHMuY2Fub25pY2FsX2pzb25fYnl0ZXMocGFyc2VkKSA9PSByYXcKICAgICAgICBhc3NlcnQgbm90IHJhdy5lbmRzd2l0aChiIlxuIikKCkBw'
        'eXRlc3QubWFyay5wYXJhbWV0cml6ZSgibmFtZSIsIGxpc3QoVkFMSURBVE9SUykpCmRlZiB0ZXN0X3Vua25vd25fbWlzc2luZ19hbmRfbm9uY2Fu'
        'b25pY2FsX2RvY3VtZW50c19mYWlsKG5hbWUpOgogICAgcGFyc2VkID0ganNvbi5sb2FkcyhyZWFkKG5hbWUpKQogICAgdmFsaWRhdG9yID0gVkFM'
        'SURBVE9SU1tuYW1lXQogICAgcGFyc2VkWyJ1bmtub3duIl0gPSBUcnVlCiAgICB3aXRoIHB5dGVzdC5yYWlzZXMoVmFsdWVFcnJvcik6IHZhbGlk'
        'YXRvcihwYXJzZWQpCiAgICBwYXJzZWQgPSBqc29uLmxvYWRzKHJlYWQobmFtZSkpOyBwYXJzZWQucG9wKG5leHQoaXRlcihwYXJzZWQpKSkKICAg'
        'IHdpdGggcHl0ZXN0LnJhaXNlcyhWYWx1ZUVycm9yKTogdmFsaWRhdG9yKHBhcnNlZCkKICAgIHdpdGggcHl0ZXN0LnJhaXNlcyhWYWx1ZUVycm9y'
        'KTogY29udHJhY3RzLmxvYWRfYW5kX3ZhbGlkYXRlX2Fzc3VyYW5jZV9zY2FmZm9sZChyZWFkKG5hbWUpICsgYiJcbiIsIHZhbGlkYXRvcikKCmRl'
        'ZiB0ZXN0X3RlbXBvcmFsX2RyYWZ0X2Nhbm5vdF9iZWNvbWVfZWZmZWN0aXZlX29yX2FwcGxpZWQoKToKICAgIGRhdGEgPSBqc29uLmxvYWRzKHJl'
        'YWQoImgwMDFfdGVtcG9yYWxfY2F1c2FsaXR5X2FtZW5kbWVudF9kcmFmdF92MDAxLmpzb24iKSkKICAgIGRhdGFbInN0YXR1cyJdID0gIkVGRkVD'
        'VElWRSIKICAgIHdpdGggcHl0ZXN0LnJhaXNlcyhWYWx1ZUVycm9yKTogY29udHJhY3RzLnZhbGlkYXRlX3RlbXBvcmFsX2FtZW5kbWVudF9kcmFm'
        'dChkYXRhKQogICAgZGF0YSA9IGpzb24ubG9hZHMocmVhZCgiaDAwMV90ZW1wb3JhbF9jYXVzYWxpdHlfYW1lbmRtZW50X2RyYWZ0X3YwMDEuanNv'
        'biIpKTsgZGF0YVsibm9uX2VmZmVjdHMiXS5yZW1vdmUoIlBST1BPU0VEX1JVTEVfTk9UX0FQUExJRUQiKQogICAgd2l0aCBweXRlc3QucmFpc2Vz'
        'KFZhbHVlRXJyb3IpOiBjb250cmFjdHMudmFsaWRhdGVfdGVtcG9yYWxfYW1lbmRtZW50X2RyYWZ0KGRhdGEpCgpkZWYgdGVzdF9jYWxpYnJhdGlv'
        'bl9kcmFmdF9yZWplY3RzX3R1bmluZ19hbmRfdW5rbm93bl9kZ3AoKToKICAgIGRhdGEgPSBqc29uLmxvYWRzKHJlYWQoImgwMDFfc3ludGhldGlj'
        'X251bGxfY2FsaWJyYXRpb25fc3BlY19kcmFmdF92MDAxLmpzb24iKSkKICAgIGRhdGFbInByb3Bvc2VkX2Rlc2lnbiJdWyJzdGF0aW9uYXJ5X2Js'
        'b2NrX2xlbmd0aCJdID0gNjQKICAgIHdpdGggcHl0ZXN0LnJhaXNlcyhWYWx1ZUVycm9yKTogY29udHJhY3RzLnZhbGlkYXRlX2NhbGlicmF0aW9u'
        'X3NwZWNfZHJhZnQoZGF0YSkKICAgIGRhdGEgPSBqc29uLmxvYWRzKHJlYWQoImgwMDFfc3ludGhldGljX251bGxfY2FsaWJyYXRpb25fc3BlY19k'
        'cmFmdF92MDAxLmpzb24iKSk7IGRhdGFbInByb3Bvc2VkX2RncF9zdWl0ZSJdLmFwcGVuZCgicmVhbCBCVEMiKQogICAgd2l0aCBweXRlc3QucmFp'
        'c2VzKFZhbHVlRXJyb3IpOiBjb250cmFjdHMudmFsaWRhdGVfY2FsaWJyYXRpb25fc3BlY19kcmFmdChkYXRhKQoKZGVmIHRlc3RfbGVkZ2VyX2lz'
        'X2VtcHR5X2FuZF9hcHBlbmRfb25seSgpOgogICAgZW1wdHkgPSBqc29uLmxvYWRzKHJlYWQoImdsb2JhbF9yZWFsX3Byb3RvY29sX2hvbGRvdXRf'
        'ZGlzY2xvc3VyZV9sZWRnZXJfdjAwMS5qc29uIikpCiAgICBhc3NlcnQgZW1wdHlbImVudHJpZXMiXSA9PSBbXQogICAgZW50cnkgPSB7ImRhdGFz'
        'ZXRfcmVnaW9uX2lkIjoicmVnaW9uLWEiLCJkaXNjbG9zdXJlX2tpbmQiOiJERVNJR05BVEVEX0RFVkVMT1BNRU5UIiwiZGlzY2xvc3VyZV9zdGF0'
        'dXMiOiJSRUNPUkRFRF9BUFBFTkRfT05MWSIsImVudHJ5X2lkIjoiZW50cnktYSIsImh5cG90aGVzaXNfaWQiOiJoMDAxIiwicHJvdG9jb2xfaWQi'
        'OiJwcm90b2NvbCIsInJlY29yZGVkX2F0X3V0YyI6IjIwMjYtMDEtMDFUMDA6MDA6MDBaIiwicmVnaW9uX2VuZF91dGMiOiIyMDI2LTAxLTAyVDAw'
        'OjAwOjAwWiIsInJlZ2lvbl9zdGFydF91dGMiOiIyMDI2LTAxLTAxVDAwOjAwOjAwWiIsInNvdXJjZV9jb250cm9sX3JlY2VpcHRfcGF0aCI6ImRv'
        'Y3MvY29udHJvbC9yZWNlaXB0Lmpzb24iLCJzb3VyY2VfY29udHJvbF9yZWNlaXB0X3NoYTI1NiI6ImEiICogNjR9CiAgICBjYW5kaWRhdGUgPSBk'
        'aWN0KGVtcHR5LCBlbnRyaWVzPVtlbnRyeV0sIHN0YXR1cz0iQVBQRU5EX09OTFlfTUVUQURBVEFfRElTQ0xPU1VSRVMiKQogICAgY29udHJhY3Rz'
        'LnZhbGlkYXRlX2xlZGdlcl9hcHBlbmQoY29udHJhY3RzLmNhbm9uaWNhbF9qc29uX2J5dGVzKGVtcHR5KSwgY29udHJhY3RzLmNhbm9uaWNhbF9q'
        'c29uX2J5dGVzKGNhbmRpZGF0ZSkpCiAgICB3aXRoIHB5dGVzdC5yYWlzZXMoVmFsdWVFcnJvcik6IGNvbnRyYWN0cy52YWxpZGF0ZV9sZWRnZXJf'
        'YXBwZW5kKGNvbnRyYWN0cy5jYW5vbmljYWxfanNvbl9ieXRlcyhjYW5kaWRhdGUpLCBjb250cmFjdHMuY2Fub25pY2FsX2pzb25fYnl0ZXMoZW1w'
        'dHkpKQogICAgYmFkID0gZGljdChjYW5kaWRhdGUsIGVudHJpZXM9W2RpY3QoZW50cnksIHJldHVybnM9MSldKQogICAgd2l0aCBweXRlc3QucmFp'
        'c2VzKFZhbHVlRXJyb3IpOiBjb250cmFjdHMudmFsaWRhdGVfaG9sZG91dF9kaXNjbG9zdXJlX2xlZGdlcihiYWQpCgpkZWYgdGVzdF9sZWRnZXJf'
        'YXBwZW5kX3JlcXVpcmVzX2Nhbm9uaWNhbF9ieXRlc19hbmRfcHJlc2VydmVzX2Nhbm9uaWNhbF9wcmVmaXgoKToKICAgIGVtcHR5ID0ganNvbi5s'
        'b2FkcyhyZWFkKCJnbG9iYWxfcmVhbF9wcm90b2NvbF9ob2xkb3V0X2Rpc2Nsb3N1cmVfbGVkZ2VyX3YwMDEuanNvbiIpKQogICAgZW50cnkgPSB7'
        'ImRhdGFzZXRfcmVnaW9uX2lkIjoicmVnaW9uLWEiLCJkaXNjbG9zdXJlX2tpbmQiOiJERVNJR05BVEVEX0RFVkVMT1BNRU5UIiwiZGlzY2xvc3Vy'
        'ZV9zdGF0dXMiOiJSRUNPUkRFRF9BUFBFTkRfT05MWSIsImVudHJ5X2lkIjoiZW50cnktYSIsImh5cG90aGVzaXNfaWQiOiJoMDAxIiwicHJvdG9j'
        'b2xfaWQiOiJwcm90b2NvbCIsInJlY29yZGVkX2F0X3V0YyI6IjIwMjYtMDEtMDFUMDA6MDA6MDBaIiwicmVnaW9uX2VuZF91dGMiOiIyMDI2LTAx'
        'LTAyVDAwOjAwOjAwWiIsInJlZ2lvbl9zdGFydF91dGMiOiIyMDI2LTAxLTAxVDAwOjAwOjAwWiIsInNvdXJjZV9jb250cm9sX3JlY2VpcHRfcGF0'
        'aCI6ImRvY3MvY29udHJvbC90YXNrcy9leGFtcGxlL2hhbmRvZmZfdjAwMS5qc29uIiwic291cmNlX2NvbnRyb2xfcmVjZWlwdF9zaGEyNTYiOiJh'
        'IiAqIDY0fQogICAgY2FuZGlkYXRlID0gZGljdChlbXB0eSwgZW50cmllcz1bZW50cnldLCBzdGF0dXM9IkFQUEVORF9PTkxZX01FVEFEQVRBX0RJ'
        'U0NMT1NVUkVTIikKICAgIHdpdGggcHl0ZXN0LnJhaXNlcyhWYWx1ZUVycm9yLCBtYXRjaD0iY2Fub25pY2FsIEpTT04gYnl0ZXMiKToKICAgICAg'
        'ICBjb250cmFjdHMudmFsaWRhdGVfbGVkZ2VyX2FwcGVuZChlbXB0eSwgY2FuZGlkYXRlKQogICAgbm9uY2Fub25pY2FsID0ganNvbi5kdW1wcyhj'
        'YW5kaWRhdGUpLmVuY29kZSgpCiAgICB3aXRoIHB5dGVzdC5yYWlzZXMoVmFsdWVFcnJvciwgbWF0Y2g9Im5vbi1jYW5vbmljYWwiKToKICAgICAg'
        'ICBjb250cmFjdHMudmFsaWRhdGVfbGVkZ2VyX2FwcGVuZChjb250cmFjdHMuY2Fub25pY2FsX2pzb25fYnl0ZXMoZW1wdHkpLCBub25jYW5vbmlj'
        'YWwpCiAgICBmaXJzdCA9IGNvbnRyYWN0cy5jYW5vbmljYWxfanNvbl9ieXRlcyhjYW5kaWRhdGUpCiAgICBzZWNvbmRfZW50cnkgPSBkaWN0KGVu'
        'dHJ5LCBlbnRyeV9pZD0iZW50cnktYiIsIGRhdGFzZXRfcmVnaW9uX2lkPSJyZWdpb24tYiIsIHJlY29yZGVkX2F0X3V0Yz0iMjAyNi0wMS0wMVQw'
        'MTowMDowMFoiKQogICAgc2Vjb25kID0gZGljdChjYW5kaWRhdGUsIGVudHJpZXM9W2VudHJ5LCBzZWNvbmRfZW50cnldKQogICAgY29udHJhY3Rz'
        'LnZhbGlkYXRlX2xlZGdlcl9hcHBlbmQoZmlyc3QsIGNvbnRyYWN0cy5jYW5vbmljYWxfanNvbl9ieXRlcyhzZWNvbmQpKQogICAgZm9yIG11dGF0'
        'ZWQgaW4gKAogICAgICAgIGRpY3QoY2FuZGlkYXRlLCBlbnRyaWVzPVtdKSwKICAgICAgICBkaWN0KGNhbmRpZGF0ZSwgZW50cmllcz1bZGljdChl'
        'bnRyeSwgcmVjb3JkZWRfYXRfdXRjPSIyMDI2LTAxLTAxVDAwOjAwOjAxWiIpXSksCiAgICAgICAgZGljdChjYW5kaWRhdGUsIGVudHJpZXM9W2Rp'
        'Y3QoZW50cnksIGVudHJ5X2lkPSJlbnRyeS1iIildKSwKICAgICk6CiAgICAgICAgd2l0aCBweXRlc3QucmFpc2VzKFZhbHVlRXJyb3IpOgogICAg'
        'ICAgICAgICBjb250cmFjdHMudmFsaWRhdGVfbGVkZ2VyX2FwcGVuZChmaXJzdCwgY29udHJhY3RzLmNhbm9uaWNhbF9qc29uX2J5dGVzKG11dGF0'
        'ZWQpKQogICAgcmVvcmRlcmVkID0gZGljdChjYW5kaWRhdGUsIGVudHJpZXM9W2RpY3QocmV2ZXJzZWQobGlzdChlbnRyeS5pdGVtcygpKSkpXSkK'
        'ICAgIGNvbnRyYWN0cy52YWxpZGF0ZV9sZWRnZXJfYXBwZW5kKGZpcnN0LCBjb250cmFjdHMuY2Fub25pY2FsX2pzb25fYnl0ZXMocmVvcmRlcmVk'
        'KSkKICAgIGR1cGxpY2F0ZV9zZW1hbnRpYyA9IGRpY3QoZW50cnksIGVudHJ5X2lkPSJlbnRyeS1iIikKICAgIHdpdGggcHl0ZXN0LnJhaXNlcyhW'
        'YWx1ZUVycm9yLCBtYXRjaD0ic2VtYW50aWMiKToKICAgICAgICBjb250cmFjdHMudmFsaWRhdGVfaG9sZG91dF9kaXNjbG9zdXJlX2xlZGdlcihk'
        'aWN0KGNhbmRpZGF0ZSwgZW50cmllcz1bZW50cnksIGR1cGxpY2F0ZV9zZW1hbnRpY10pKQogICAgcmVncmVzc2VkID0gZGljdChjYW5kaWRhdGUs'
        'IGVudHJpZXM9W2VudHJ5LCBkaWN0KHNlY29uZF9lbnRyeSwgcmVjb3JkZWRfYXRfdXRjPSIyMDI1LTEyLTMxVDIzOjAwOjAwWiIpXSkKICAgIHdp'
        'dGggcHl0ZXN0LnJhaXNlcyhWYWx1ZUVycm9yLCBtYXRjaD0ib3JkZXJlZCIpOgogICAgICAgIGNvbnRyYWN0cy52YWxpZGF0ZV9ob2xkb3V0X2Rp'
        'c2Nsb3N1cmVfbGVkZ2VyKHJlZ3Jlc3NlZCkKCkBweXRlc3QubWFyay5wYXJhbWV0cml6ZSgidGltZXN0YW1wIiwgWwogICAgIjIwMjYtMDEtMDFU'
        'MDA6MDA6MDAiLCAiMjAyNi0wMS0wMSIsICIyMDI2LTAxLTAxVDAyOjAwOjAwKzAyOjAwIiwKICAgICIyMDI1LTEyLTMxVDE5OjAwOjAwLTA1OjAw'
        'IiwgIjIwMjYtMDEtMDFUMDA6MDA6MDArMDA6MDAiLCAiMjAyNi0wMS0wMXQwMDowMDowMHoiLAogICAgIjIwMjYtMDEtMDFUMDA6MDBaIiwgIjIw'
        'MjYtMDEtMDFUMDA6MDA6MDAuMDAwWiIsICIyMDI2LTAyLTMwVDAwOjAwOjAwWiIsIFRydWUsIDEsIE5vbmUsCl0pCmRlZiB0ZXN0X2xlZGdlcl9y'
        'ZWplY3RzX25vbmNhbm9uaWNhbF90aW1lc3RhbXBzKHRpbWVzdGFtcCk6CiAgICBlbXB0eSA9IGpzb24ubG9hZHMocmVhZCgiZ2xvYmFsX3JlYWxf'
        'cHJvdG9jb2xfaG9sZG91dF9kaXNjbG9zdXJlX2xlZGdlcl92MDAxLmpzb24iKSkKICAgIGVudHJ5ID0geyJkYXRhc2V0X3JlZ2lvbl9pZCI6InJl'
        'Z2lvbi1hIiwiZGlzY2xvc3VyZV9raW5kIjoiREVTSUdOQVRFRF9ERVZFTE9QTUVOVCIsImRpc2Nsb3N1cmVfc3RhdHVzIjoiUkVDT1JERURfQVBQ'
        'RU5EX09OTFkiLCJlbnRyeV9pZCI6ImVudHJ5LWEiLCJoeXBvdGhlc2lzX2lkIjoiaDAwMSIsInByb3RvY29sX2lkIjoicHJvdG9jb2wiLCJyZWNv'
        'cmRlZF9hdF91dGMiOiIyMDI2LTAxLTAxVDAwOjAwOjAwWiIsInJlZ2lvbl9lbmRfdXRjIjoiMjAyNi0wMS0wMlQwMDowMDowMFoiLCJyZWdpb25f'
        'c3RhcnRfdXRjIjoiMjAyNi0wMS0wMVQwMDowMDowMFoiLCJzb3VyY2VfY29udHJvbF9yZWNlaXB0X3BhdGgiOiJkb2NzL2NvbnRyb2wvcmVjZWlw'
        'dC5qc29uIiwic291cmNlX2NvbnRyb2xfcmVjZWlwdF9zaGEyNTYiOiJhIiAqIDY0fQogICAgd2l0aCBweXRlc3QucmFpc2VzKFZhbHVlRXJyb3Ip'
        'OgogICAgICAgIGNvbnRyYWN0cy52YWxpZGF0ZV9ob2xkb3V0X2Rpc2Nsb3N1cmVfbGVkZ2VyKGRpY3QoZW1wdHksIHN0YXR1cz0iQVBQRU5EX09O'
        'TFlfTUVUQURBVEFfRElTQ0xPU1VSRVMiLCBlbnRyaWVzPVtkaWN0KGVudHJ5LCByZWNvcmRlZF9hdF91dGM9dGltZXN0YW1wKV0pKQoKZGVmIHRl'
        'c3RfbGVkZ2VyX3JlamVjdHNfY2hyb25vbG9naWNhbGx5X3JldmVyc2VkX3JlZ2lvbl9ldmVuX3doZW5fc3RyaW5nc19zb3J0KCk6CiAgICBlbXB0'
        'eSA9IGpzb24ubG9hZHMocmVhZCgiZ2xvYmFsX3JlYWxfcHJvdG9jb2xfaG9sZG91dF9kaXNjbG9zdXJlX2xlZGdlcl92MDAxLmpzb24iKSkKICAg'
        'IGVudHJ5ID0geyJkYXRhc2V0X3JlZ2lvbl9pZCI6InJlZ2lvbi1hIiwiZGlzY2xvc3VyZV9raW5kIjoiREVTSUdOQVRFRF9ERVZFTE9QTUVOVCIs'
        'ImRpc2Nsb3N1cmVfc3RhdHVzIjoiUkVDT1JERURfQVBQRU5EX09OTFkiLCJlbnRyeV9pZCI6ImVudHJ5LWEiLCJoeXBvdGhlc2lzX2lkIjoiaDAw'
        'MSIsInByb3RvY29sX2lkIjoicHJvdG9jb2wiLCJyZWNvcmRlZF9hdF91dGMiOiIyMDI2LTAxLTAxVDAwOjAwOjAwWiIsInJlZ2lvbl9lbmRfdXRj'
        'IjoiMjAyNi0wMS0wMVQwMTowMDowMCswMTowMCIsInJlZ2lvbl9zdGFydF91dGMiOiIyMDI2LTAxLTAxVDAwOjMwOjAwKzAwOjAwIiwic291cmNl'
        'X2NvbnRyb2xfcmVjZWlwdF9wYXRoIjoiZG9jcy9jb250cm9sL3JlY2VpcHQuanNvbiIsInNvdXJjZV9jb250cm9sX3JlY2VpcHRfc2hhMjU2Ijoi'
        'YSIgKiA2NH0KICAgIHdpdGggcHl0ZXN0LnJhaXNlcyhWYWx1ZUVycm9yKToKICAgICAgICBjb250cmFjdHMudmFsaWRhdGVfaG9sZG91dF9kaXNj'
        'bG9zdXJlX2xlZGdlcihkaWN0KGVtcHR5LCBzdGF0dXM9IkFQUEVORF9PTkxZX01FVEFEQVRBX0RJU0NMT1NVUkVTIiwgZW50cmllcz1bZW50cnld'
        'KSkKCkBweXRlc3QubWFyay5wYXJhbWV0cml6ZSgic3RhdHVzIiwgWyJTRUFMRUQiLCAiVU5TRUFMRUQiLCAiRVhQT1NFRCIsIFRydWUsIDEsIE5v'
        'bmVdKQpkZWYgdGVzdF9sZWRnZXJfcmVqZWN0c19pbnZhbGlkX2Rpc2Nsb3N1cmVfc3RhdHVzKHN0YXR1cyk6CiAgICBlbXB0eSA9IGpzb24ubG9h'
        'ZHMocmVhZCgiZ2xvYmFsX3JlYWxfcHJvdG9jb2xfaG9sZG91dF9kaXNjbG9zdXJlX2xlZGdlcl92MDAxLmpzb24iKSkKICAgIGVudHJ5ID0geyJk'
        'YXRhc2V0X3JlZ2lvbl9pZCI6InJlZ2lvbi1hIiwiZGlzY2xvc3VyZV9raW5kIjoiREVTSUdOQVRFRF9ERVZFTE9QTUVOVCIsImRpc2Nsb3N1cmVf'
        'c3RhdHVzIjpzdGF0dXMsImVudHJ5X2lkIjoiZW50cnktYSIsImh5cG90aGVzaXNfaWQiOiJoMDAxIiwicHJvdG9jb2xfaWQiOiJwcm90b2NvbCIs'
        'InJlY29yZGVkX2F0X3V0YyI6IjIwMjYtMDEtMDFUMDA6MDA6MDBaIiwicmVnaW9uX2VuZF91dGMiOiIyMDI2LTAxLTAyVDAwOjAwOjAwWiIsInJl'
        'Z2lvbl9zdGFydF91dGMiOiIyMDI2LTAxLTAxVDAwOjAwOjAwWiIsInNvdXJjZV9jb250cm9sX3JlY2VpcHRfcGF0aCI6ImRvY3MvY29udHJvbC9y'
        'ZWNlaXB0Lmpzb24iLCJzb3VyY2VfY29udHJvbF9yZWNlaXB0X3NoYTI1NiI6ImEiICogNjR9CiAgICB3aXRoIHB5dGVzdC5yYWlzZXMoVmFsdWVF'
        'cnJvcik6CiAgICAgICAgY29udHJhY3RzLnZhbGlkYXRlX2hvbGRvdXRfZGlzY2xvc3VyZV9sZWRnZXIoZGljdChlbXB0eSwgc3RhdHVzPSJBUFBF'
        'TkRfT05MWV9NRVRBREFUQV9ESVNDTE9TVVJFUyIsIGVudHJpZXM9W2VudHJ5XSkpCgpAcHl0ZXN0Lm1hcmsucGFyYW1ldHJpemUoInBhdGgiLCBb'
        'Ii4uLy4uL3JlY2VpcHQuanNvbiIsICJkb2NzL2NvbnRyb2wvLi4vc2VjcmV0Lmpzb24iLCAiL2V0Yy9wYXNzd2QiLCAiQzpcXHNlY3JldC5qc29u'
        'IiwgIlxcXFxzZXJ2ZXJcXHNoYXJlXFxyZWNlaXB0Lmpzb24iLCAiZmlsZTovL3JlY2VpcHQuanNvbiIsICJzMzovL2J1Y2tldC9yZWNlaXB0Lmpz'
        'b24iLCAiZ3M6Ly9idWNrZXQvcmVjZWlwdC5qc29uIiwgInNzaDovL2hvc3QvcmVjZWlwdC5qc29uIiwgInFudHktYXJ0aWZhY3Q6Ly9yZWNlaXB0'
        'IiwgImh0dHBzOi8vZXhhbXBsZS5jb20vcmVjZWlwdC5qc29uIiwgImRvY3MvYXJ0aWZhY3RzL3JlY2VpcHQuanNvbiIsICJyZWNlaXB0Lmpzb24i'
        'LCAiIiwgVHJ1ZSwgMSwgTm9uZV0pCmRlZiB0ZXN0X2xlZGdlcl9yZWplY3RzX3Vuc2FmZV9yZWNlaXB0X3BhdGhzKHBhdGgpOgogICAgZW1wdHkg'
        'PSBqc29uLmxvYWRzKHJlYWQoImdsb2JhbF9yZWFsX3Byb3RvY29sX2hvbGRvdXRfZGlzY2xvc3VyZV9sZWRnZXJfdjAwMS5qc29uIikpCiAgICBl'
        'bnRyeSA9IHsiZGF0YXNldF9yZWdpb25faWQiOiJyZWdpb24tYSIsImRpc2Nsb3N1cmVfa2luZCI6IkRFU0lHTkFURURfREVWRUxPUE1FTlQiLCJk'
        'aXNjbG9zdXJlX3N0YXR1cyI6IlJFQ09SREVEX0FQUEVORF9PTkxZIiwiZW50cnlfaWQiOiJlbnRyeS1hIiwiaHlwb3RoZXNpc19pZCI6ImgwMDEi'
        'LCJwcm90b2NvbF9pZCI6InByb3RvY29sIiwicmVjb3JkZWRfYXRfdXRjIjoiMjAyNi0wMS0wMVQwMDowMDowMFoiLCJyZWdpb25fZW5kX3V0YyI6'
        'IjIwMjYtMDEtMDJUMDA6MDA6MDBaIiwicmVnaW9uX3N0YXJ0X3V0YyI6IjIwMjYtMDEtMDFUMDA6MDA6MDBaIiwic291cmNlX2NvbnRyb2xfcmVj'
        'ZWlwdF9wYXRoIjpwYXRoLCJzb3VyY2VfY29udHJvbF9yZWNlaXB0X3NoYTI1NiI6ImEiICogNjR9CiAgICB3aXRoIHB5dGVzdC5yYWlzZXMoVmFs'
        'dWVFcnJvcik6CiAgICAgICAgY29udHJhY3RzLnZhbGlkYXRlX2hvbGRvdXRfZGlzY2xvc3VyZV9sZWRnZXIoZGljdChlbXB0eSwgc3RhdHVzPSJB'
        'UFBFTkRfT05MWV9NRVRBREFUQV9ESVNDTE9TVVJFUyIsIGVudHJpZXM9W2VudHJ5XSkpCgpkZWYgdGVzdF9sZWRnZXJfc3RhdHVzX21hdGNoZXNf'
        'ZW50cnlfc3RhdGUoKToKICAgIGVtcHR5ID0ganNvbi5sb2FkcyhyZWFkKCJnbG9iYWxfcmVhbF9wcm90b2NvbF9ob2xkb3V0X2Rpc2Nsb3N1cmVf'
        'bGVkZ2VyX3YwMDEuanNvbiIpKQogICAgZW50cnkgPSB7ImRhdGFzZXRfcmVnaW9uX2lkIjoicmVnaW9uLWEiLCJkaXNjbG9zdXJlX2tpbmQiOiJE'
        'RVNJR05BVEVEX0RFVkVMT1BNRU5UIiwiZGlzY2xvc3VyZV9zdGF0dXMiOiJSRUNPUkRFRF9BUFBFTkRfT05MWSIsImVudHJ5X2lkIjoiZW50cnkt'
        'YSIsImh5cG90aGVzaXNfaWQiOiJoMDAxIiwicHJvdG9jb2xfaWQiOiJwcm90b2NvbCIsInJlY29yZGVkX2F0X3V0YyI6IjIwMjYtMDEtMDFUMDA6'
        'MDA6MDBaIiwicmVnaW9uX2VuZF91dGMiOiIyMDI2LTAxLTAyVDAwOjAwOjAwWiIsInJlZ2lvbl9zdGFydF91dGMiOiIyMDI2LTAxLTAxVDAwOjAw'
        'OjAwWiIsInNvdXJjZV9jb250cm9sX3JlY2VpcHRfcGF0aCI6ImRvY3MvY29udHJvbC9yZWNlaXB0Lmpzb24iLCJzb3VyY2VfY29udHJvbF9yZWNl'
        'aXB0X3NoYTI1NiI6ImEiICogNjR9CiAgICB3aXRoIHB5dGVzdC5yYWlzZXMoVmFsdWVFcnJvcik6IGNvbnRyYWN0cy52YWxpZGF0ZV9ob2xkb3V0'
        'X2Rpc2Nsb3N1cmVfbGVkZ2VyKGRpY3QoZW1wdHksIGVudHJpZXM9W2VudHJ5XSkpCiAgICB3aXRoIHB5dGVzdC5yYWlzZXMoVmFsdWVFcnJvcik6'
        'IGNvbnRyYWN0cy52YWxpZGF0ZV9ob2xkb3V0X2Rpc2Nsb3N1cmVfbGVkZ2VyKGRpY3QoZW1wdHksIHN0YXR1cz0iQVBQRU5EX09OTFlfTUVUQURB'
        'VEFfRElTQ0xPU1VSRVMiKSkKICAgIGNvbnRyYWN0cy52YWxpZGF0ZV9ob2xkb3V0X2Rpc2Nsb3N1cmVfbGVkZ2VyKGRpY3QoZW1wdHksIHN0YXR1'
        'cz0iQVBQRU5EX09OTFlfTUVUQURBVEFfRElTQ0xPU1VSRVMiLCBlbnRyaWVzPVtlbnRyeV0pKQoKZGVmIHRlc3RfZmFpbHVyZV9hbmRfcmV2aWV3'
        'X3NjaGVtYXNfcmVqZWN0X3NlY3JldHNfYW5kX2NsYWltcygpOgogICAgZmFpbHVyZSA9IGpzb24ubG9hZHMocmVhZCgiZHVyYWJsZV9zdG9yZV9m'
        'YWlsdXJlX2RvbWFpbl9ldmlkZW5jZV9zY2hlbWFfdjAwMS5qc29uIikpCiAgICBmYWlsdXJlWyJmaWVsZF9kZWZpbml0aW9ucyJdLmFwcGVuZCgi'
        'YWJzb2x1dGVfcGF0aCIpCiAgICB3aXRoIHB5dGVzdC5yYWlzZXMoVmFsdWVFcnJvcik6IGNvbnRyYWN0cy52YWxpZGF0ZV9mYWlsdXJlX2RvbWFp'
        'bl9ldmlkZW5jZV9zY2hlbWEoZmFpbHVyZSkKICAgIHJldmlldyA9IGpzb24ubG9hZHMocmVhZCgicmVwbGF5YWJsZV9yZXZpZXdfZXZpZGVuY2Vf'
        'cGFja2V0X3NjaGVtYV92MDAxLmpzb24iKSk7IHJldmlld1siZmllbGRfZGVmaW5pdGlvbnMiXS5hcHBlbmQoInRva2VuIikKICAgIHdpdGggcHl0'
        'ZXN0LnJhaXNlcyhWYWx1ZUVycm9yKTogY29udHJhY3RzLnZhbGlkYXRlX3Jldmlld19wYWNrZXRfc2NoZW1hKHJldmlldykKCmRlZiB0ZXN0X2lt'
        'cG9ydF9ib3VuZGFyeV9pc19zdGFuZGFyZF9saWJyYXJ5X29ubHkoKToKICAgIGZvciBwYXRoIGluIChST09UIC8gInF1YW50Ym90L2Fzc3VyYW5j'
        'ZSIpLmdsb2IoIioucHkiKToKICAgICAgICB0cmVlID0gYXN0LnBhcnNlKHBhdGgucmVhZF90ZXh0KCkpCiAgICAgICAgZm9yIG5vZGUgaW4gYXN0'
        'LndhbGsodHJlZSk6CiAgICAgICAgICAgIGlmIGlzaW5zdGFuY2Uobm9kZSwgYXN0LkltcG9ydCk6CiAgICAgICAgICAgICAgICBhc3NlcnQgYWxs'
        'KGFsaWFzLm5hbWUuc3BsaXQoIi4iKVswXSBpbiB7ImRhdGFjbGFzc2VzIiwgImRhdGV0aW1lIiwgImhhc2hsaWIiLCAianNvbiIsICJyZSJ9IGZv'
        'ciBhbGlhcyBpbiBub2RlLm5hbWVzKQogICAgICAgICAgICBpZiBpc2luc3RhbmNlKG5vZGUsIGFzdC5JbXBvcnRGcm9tKSBhbmQgbm9kZS5tb2R1'
        'bGU6CiAgICAgICAgICAgICAgICBhc3NlcnQgbm9kZS5tb2R1bGUuc3BsaXQoIi4iKVswXSBpbiB7Il9fZnV0dXJlX18iLCAiZGF0YWNsYXNzZXMi'
        'LCAiZGF0ZXRpbWUiLCAiaGFzaGxpYiIsICJqc29uIiwgInJlIiwgInR5cGluZyIsICJjb250cmFjdHMifQoKCmRlZiB0ZXN0X2gwMDFfcmV2aWV3'
        'X3JlY29yZHNfYXJlX2Nhbm9uaWNhbF9hbmRfdmFsaWRhdGUoKToKICAgIGZvciBuYW1lLCB2YWxpZGF0b3IgaW4gKAogICAgICAgICgiaDAwMV9w'
        'cmVfZGF0YV9hc3N1cmFuY2Vfc2NhZmZvbGRfcmVyZXZpZXdfcHJvdG9jb2xfdjAwMS5qc29uIiwgY29udHJhY3RzLnZhbGlkYXRlX3Jldmlld19w'
        'cm90b2NvbF9yZWNvcmQpLAogICAgICAgICgiaDAwMV9wcmVfZGF0YV9hc3N1cmFuY2Vfc2NhZmZvbGRfcmVyZXZpZXdfcGFja2V0X3YwMDEuanNv'
        'biIsIGNvbnRyYWN0cy52YWxpZGF0ZV9yZXZpZXdfZXZpZGVuY2VfcGFja2V0KSwKICAgICk6CiAgICAgICAgcmF3ID0gKFJFVklFV1MgLyBuYW1l'
        'KS5yZWFkX2J5dGVzKCkKICAgICAgICBhc3NlcnQgY29udHJhY3RzLmxvYWRfYW5kX3ZhbGlkYXRlX2Fzc3VyYW5jZV9zY2FmZm9sZChyYXcsIHZh'
        'bGlkYXRvcikKICAgICAgICBhc3NlcnQgY29udHJhY3RzLmNhbm9uaWNhbF9qc29uX2J5dGVzKGpzb24ubG9hZHMocmF3KSkgPT0gcmF3CiAgICAg'
        'ICAgYXNzZXJ0IG5vdCByYXcuZW5kc3dpdGgoYiJcbiIpCgoKQHB5dGVzdC5tYXJrLnBhcmFtZXRyaXplKCJtdXRhdGlvbiIsIFsKICAgIGxhbWJk'
        'YSB2YWx1ZTogdmFsdWUudXBkYXRlKHN0YXR1cz0iUFJFUkVHSVNURVJFRF9CRUZPUkVfUkVWSUVXIiksCiAgICBsYW1iZGEgdmFsdWU6IHZhbHVl'
        'LnVwZGF0ZShyZXZpZXdfcmVxdWlyZW1lbnRzPVsieCJdKSwKICAgIGxhbWJkYSB2YWx1ZTogdmFsdWUudXBkYXRlKG1lcmdlZF9tYWluX2NvbW1p'
        'dF9zaGE9IjAiICogNDApLApdKQpkZWYgdGVzdF9oMDAxX3Jldmlld19wcm90b2NvbF9pc19ub3RfcmV0cm9hY3RpdmVseV9wcmVyZWdpc3RlcmVk'
        'KHRtcF9wYXRoLCBtdXRhdGlvbik6CiAgICBkZWwgdG1wX3BhdGgKICAgIHZhbHVlID0ganNvbi5sb2FkcygoUkVWSUVXUyAvICJoMDAxX3ByZV9k'
        'YXRhX2Fzc3VyYW5jZV9zY2FmZm9sZF9yZXJldmlld19wcm90b2NvbF92MDAxLmpzb24iKS5yZWFkX2J5dGVzKCkpCiAgICBtdXRhdGlvbih2YWx1'
        'ZSkKICAgIHdpdGggcHl0ZXN0LnJhaXNlcyhWYWx1ZUVycm9yKToKICAgICAgICBjb250cmFjdHMudmFsaWRhdGVfcmV2aWV3X3Byb3RvY29sX3Jl'
        'Y29yZCh2YWx1ZSkKCgpAcHl0ZXN0Lm1hcmsucGFyYW1ldHJpemUoImZpZWxkIiwgWyJyZXZpZXdlZF9jb21taXRfc2hhIiwgInZlcmRpY3QiLCAi'
        'cmV2aWV3X3NwZWNpZmljYXRpb25faGFzaCIsICJzdGRvdXRfYXJ0aWZhY3RfaGFzaGVzIiwgInN0ZGVycl9hcnRpZmFjdF9oYXNoZXMiXSkKZGVm'
        'IHRlc3RfaDAwMV9yZXZpZXdfcGFja2V0X3JlamVjdHNfZHJpZnQoZmllbGQpOgogICAgdmFsdWUgPSBqc29uLmxvYWRzKChSRVZJRVdTIC8gImgw'
        'MDFfcHJlX2RhdGFfYXNzdXJhbmNlX3NjYWZmb2xkX3JlcmV2aWV3X3BhY2tldF92MDAxLmpzb24iKS5yZWFkX2J5dGVzKCkpCiAgICB2YWx1ZVtm'
        'aWVsZF0gPSAid3JvbmciIGlmIGZpZWxkIG5vdCBpbiB7InN0ZG91dF9hcnRpZmFjdF9oYXNoZXMiLCAic3RkZXJyX2FydGlmYWN0X2hhc2hlcyJ9'
        'IGVsc2UgWyJhIiAqIDY0XQogICAgd2l0aCBweXRlc3QucmFpc2VzKFZhbHVlRXJyb3IpOgogICAgICAgIGNvbnRyYWN0cy52YWxpZGF0ZV9yZXZp'
        'ZXdfZXZpZGVuY2VfcGFja2V0KHZhbHVlKQoKCkBweXRlc3QubWFyay5wYXJhbWV0cml6ZSgiZmllbGQiLCBbInRva2VuIiwgInJlYWxfZGF0YSIs'
        'ICJwcml2YXRlX3JlYXNvbmluZyIsICJzY2llbnRpZmljX2NsYWltIl0pCmRlZiB0ZXN0X2gwMDFfcmV2aWV3X3BhY2tldF9yZWplY3RzX2ZvcmJp'
        'ZGRlbl9maWVsZHMoZmllbGQpOgogICAgdmFsdWUgPSBqc29uLmxvYWRzKChSRVZJRVdTIC8gImgwMDFfcHJlX2RhdGFfYXNzdXJhbmNlX3NjYWZm'
        'b2xkX3JlcmV2aWV3X3BhY2tldF92MDAxLmpzb24iKS5yZWFkX2J5dGVzKCkpCiAgICB2YWx1ZVtmaWVsZF0gPSBGYWxzZQogICAgd2l0aCBweXRl'
        'c3QucmFpc2VzKFZhbHVlRXJyb3IpOgogICAgICAgIGNvbnRyYWN0cy52YWxpZGF0ZV9yZXZpZXdfZXZpZGVuY2VfcGFja2V0KHZhbHVlKQoKCmRl'
        'ZiB0ZXN0X2gwMDFfcmV2aWV3X3BhY2tldF9jb21tYW5kc19hcmVfZXhlY3V0YWJsZV9yZXBsYXlfcmVjb3JkcygpOgogICAgcGFja2V0ID0ganNv'
        'bi5sb2FkcygoUkVWSUVXUyAvICJoMDAxX3ByZV9kYXRhX2Fzc3VyYW5jZV9zY2FmZm9sZF9yZXJldmlld19wYWNrZXRfdjAwMS5qc29uIikucmVh'
        'ZF9ieXRlcygpKQogICAgY29tbWFuZHMgPSBwYWNrZXRbImNvbW1hbmRzIl0KICAgIGpvaW5lZCA9ICIgIi5qb2luKGNvbW1hbmRzKQogICAgYXNz'
        'ZXJ0ICItLW5vLWdpdC1leHBvcnQiIG5vdCBpbiBqb2luZWQKICAgIGFzc2VydCAicmVtb3RlIENJIGNoZWNrcyIgbm90IGluIGpvaW5lZAogICAg'
        'YXNzZXJ0IGxlbihjb21tYW5kcykgPT0gbGVuKHNldChjb21tYW5kcykpCiAgICAjIFRoZSByZWNvcmRlZCByZWNpcGUgaXMgYnl0ZS1pZGVudGlj'
        'YWwgdG8gdGhlIGluZGVwZW5kZW50bHkgcGlubmVkIGNvbnRyYWN0LgogICAgYXNzZXJ0IGNvbW1hbmRzID09IGNvbnRyYWN0cy5fUkVWSUVXX0NP'
        'TU1BTkRTCiAgICAjIE1BSk9SIHJlcGxheWFiaWxpdHkgZml4OiB0aGUgcmVjaXBlIGJpbmRzIHRoZSBhY3R1YWwgUFIgIzI4MiBiYXNlLCBuZXZl'
        'ciB0aGUKICAgICMgbGF0ZXIgbWVyZ2VkLW1haW4gY29tbWl0ICh1c2luZyBtZXJnZWQtbWFpbiBicmVha3MgbWVyZ2UtYmFzZSBhbmQgMTYtZmls'
        'ZSBzY29wZSkuCiAgICBhc3NlcnQgYW55KCJCQVNFPTI4ZDZjNzBlOWQ3Y2IxMWM1NWQxYWZkZjhiNGU1YWQ5NzU0ZjdhYmEiIGluIGNvbW1hbmQg'
        'Zm9yIGNvbW1hbmQgaW4gY29tbWFuZHMpCiAgICBhc3NlcnQgYWxsKCJhZTYxYzYxNjJmMzE2NGUwYjI0ZGQ1NjdhNmVmNzNiZGI1ZWNmOGVhIiBu'
        'b3QgaW4gY29tbWFuZCBmb3IgY29tbWFuZCBpbiBjb21tYW5kcykKICAgICMgRGV0YWNoZWQtd29ya3RyZWUgc2V0dXAgYW5kIGV4cG9ydGVkLXRy'
        'ZWUgY3dkIGFyZSByZWNvcmRlZCBleHBsaWNpdGx5LCBhbmQgdGhlCiAgICAjIHNjb3BlIGNoZWNrIGlzIGFuIGV4YWN0IDE2LWZpbGUgY29tcGFy'
        'aXNvbiByYXRoZXIgdGhhbiBhIGNvdW50IGFsb25lLgogICAgZm9yIG1hcmtlciBpbiAoCiAgICAgICAgIiRIRUFEIiwgIiRCQVNFIiwgImdpdCBt'
        'ZXJnZS1iYXNlIiwgIndvcmt0cmVlIGFkZCAtLWRldGFjaCIsICJjZCAkUkVWSUVXX0RJUiIsICJjZCAkRVhQT1JUIiwKICAgICAgICAiZ2l0IGRp'
        'ZmYgLS1uYW1lLW9ubHkiLCAiZGlmZiAtdSIsICItZXEgMTYiLCAic2hhMjU2c3VtIiwgImdpdCBhcmNoaXZlIiwgIiEgLWUgJEVYUE9SVC8uZ2l0'
        'IiwKICAgICAgICAiUFlUSE9OUEFUSD0kRVhQT1JUIiwgImdoIHJ1biBsaXN0IiwgImdpdCBzdGF0dXMgLS1zaG9ydCIsCiAgICApOgogICAgICAg'
        'IGFzc2VydCBhbnkobWFya2VyIGluIGNvbW1hbmQgZm9yIGNvbW1hbmQgaW4gY29tbWFuZHMpCiAgICAjIE5vIGNvbW1hbmQgc3RyaW5nIGlzIGFu'
        'IGFic29sdXRlIHBhdGgsIHN0b3JlIFVSSSwgb3IgbmV0d29yayBVUkwuCiAgICBhc3NlcnQgYWxsKG5vdCBjb21tYW5kLnN0YXJ0c3dpdGgoKCIv'
        'IiwgImh0dHA6Ly8iLCAiaHR0cHM6Ly8iLCAicW50eS1hcnRpZmFjdDovLyIpKSBmb3IgY29tbWFuZCBpbiBjb21tYW5kcykKCgpkZWYgdGVzdF9o'
        'MDAxX3RlbXBvcmFsX2NhbmRpZGF0ZV9yZXJldmlld19yZWNvcmRfaXNfY2Fub25pY2FsX2FuZF9zdHJpY3QoKToKICAgIHJhdyA9IFRFTVBPUkFM'
        'X1JFUkVWSUVXLnJlYWRfYnl0ZXMoKQogICAgdmFsdWUgPSBjb250cmFjdHMudmFsaWRhdGVfaDAwMV90ZW1wb3JhbF9jYW5kaWRhdGVfcmVyZXZp'
        'ZXdfcmVjb3JkKHJhdykKICAgIGFzc2VydCB2YWx1ZVsiZmluYWxfdmVyZGljdCJdID09ICJRTlRZX0gwMDFfVEVNUE9SQUxfQ0FVU0FMSVRZX0FN'
        'RU5ETUVOVF9DQU5ESURBVEVfUkVSRVZJRVdfUEFTU0VEIgogICAgYXNzZXJ0IHZhbHVlWyJyZWNvcmRlZF9hZnRlcl9yZXZpZXciXSBpcyBUcnVl'
        'CiAgICBhc3NlcnQgdmFsdWVbInByZXJlZ2lzdGVyZWQiXSBpcyBGYWxzZQogICAgYXNzZXJ0IG5vdCByYXcuZW5kc3dpdGgoYiJcbiIpCgoKZGVm'
        'IHRlc3RfaDAwMV90ZW1wb3JhbF9jYW5kaWRhdGVfcmVyZXZpZXdfc2NvcGVfbWF0Y2hlc19oaXN0b3JpY2FsX2dpdF9kZWx0YSgpOgogICAgdmFs'
        'dWUgPSBqc29uLmxvYWRzKFRFTVBPUkFMX1JFUkVWSUVXLnJlYWRfYnl0ZXMoKSkKICAgIGV4cGVjdGVkID0gWwogICAgICAgICJkb2NzL2NvbnRy'
        'b2wvYWN0aXZlX3Rhc2suanNvbiIsCiAgICAgICAgImRvY3MvY29udHJvbC9hbWVuZG1lbnRzL2NhbmRpZGF0ZTFfaDAwMV90ZW1wb3JhbF9jYXVz'
        'YWxpdHlfdjAwMS5qc29uIiwKICAgICAgICAiZG9jcy9jb250cm9sL3Rhc2tzL1JFQ09WRVJfT1JfUkVUSVJFX0NBTkRJREFURTFfVjBfRlJPWkVO'
        'X0lOUFVUL2hhbmRvZmZfdjAxNi5qc29uIiwKICAgICAgICAicXVhbnRib3QvY29udGludWl0eS9jb250ZXh0LnB5IiwgInF1YW50Ym90L2V4cGVy'
        'aW1lbnQvaDAwMV90ZW1wb3JhbF9jYXVzYWxpdHkucHkiLAogICAgICAgICJ0ZXN0cy9jb250aW51aXR5L3Rlc3RfY3Jvc3NfYWdlbnRfY29udGlu'
        'dWl0eS5weSIsICJ0ZXN0cy9leHBlcmltZW50L3Rlc3RfaDAwMV90ZW1wb3JhbF9jYXVzYWxpdHkucHkiLAogICAgXQogICAgaWYgKFJPT1QgLyAi'
        'LmdpdCIpLmV4aXN0cygpOgogICAgICAgIGFjdHVhbCA9IHN1YnByb2Nlc3MucnVuKAogICAgICAgICAgICBbImdpdCIsICJkaWZmIiwgIi0tbmFt'
        'ZS1vbmx5IiwgIjk5ODFhNDY2ZDg0NzMwNTU3MGY3ZTIzODI2ZjBjOWY0MGE3NDQ2YTkiLCAiNzQ1NTRlMTVmOTJjZGI3ZjZjMjIyMzg3NjZiZDZl'
        'MWYxNmI2MGJmNCJdLAogICAgICAgICAgICBjaGVjaz1UcnVlLCBjYXB0dXJlX291dHB1dD1UcnVlLCB0ZXh0PVRydWUsCiAgICAgICAgKS5zdGRv'
        'dXQuc3BsaXRsaW5lcygpCiAgICBlbHNlOgogICAgICAgIGFjdHVhbCA9IGV4cGVjdGVkCiAgICBhc3NlcnQgYWN0dWFsID09IGV4cGVjdGVkCiAg'
        'ICBhc3NlcnQgdmFsdWVbInJlcGFpcl9zY29wZSJdID09IGV4cGVjdGVkCiAgICBhc3NlcnQgImRvY3MvZXhwZXJpbWVudHMvY2FuZGlkYXRlMV9o'
        'MDAxX3JlYWxfZGF0YV9mYWxzaWZpY2F0aW9uX3RlbXBvcmFsX2NhbmRpZGF0ZV92MDAxLmpzb24iIG5vdCBpbiB2YWx1ZVsicmVwYWlyX3Njb3Bl'
        'Il0KICAgIGFzc2VydCBub3Qgc2V0KHZhbHVlWyJyZXBhaXJfc2NvcGUiXSkgJiB7c3RyKFRFTVBPUkFMX1JFUkVWSUVXKSwgImRvY3MvY29udHJv'
        'bC90YXNrcy9SRUNPVkVSX09SX1JFVElSRV9DQU5ESURBVEUxX1YwX0ZST1pFTl9JTlBVVC9oYW5kb2ZmX3YwMTcuanNvbiIsICJxdWFudGJvdC9h'
        'c3N1cmFuY2UvY29udHJhY3RzLnB5IiwgInRlc3RzL2Fzc3VyYW5jZS90ZXN0X2NvbnRyYWN0cy5weSJ9CgoKQHB5dGVzdC5tYXJrLnBhcmFtZXRy'
        'aXplKCJtdXRhdGlvbiIsIFsKICAgIGxhbWJkYSB2OiB2LnVwZGF0ZShyZXBhaXJfc2NvcGU9dlsicmVwYWlyX3Njb3BlIl0gKyBbImV4dHJhLnB5'
        'Il0pLAogICAgbGFtYmRhIHY6IHYudXBkYXRlKHJlcGFpcl9zY29wZT12WyJyZXBhaXJfc2NvcGUiXVs6LTFdKSwKICAgIGxhbWJkYSB2OiB2LnVw'
        'ZGF0ZShyZXBhaXJfc2NvcGU9dlsicmVwYWlyX3Njb3BlIl0gKyBbdlsicmVwYWlyX3Njb3BlIl1bMF1dKSwKICAgIGxhbWJkYSB2OiB2WyJyZXBh'
        'aXJfc2NvcGUiXS5fX3NldGl0ZW1fXygwLCAic3Vic3RpdHV0ZWQucHkiKSwKICAgIGxhbWJkYSB2OiB2WyJyZXBhaXJfc2NvcGUiXS5fX3NldGl0'
        'ZW1fXygwLCAiZG9jcy9hc3N1cmFuY2UvcmV2aWV3cy9oMDAxX3RlbXBvcmFsX2NhdXNhbGl0eV9hbWVuZG1lbnRfY2FuZGlkYXRlX3JlcmV2aWV3'
        'X3JlY29yZF92MDAxLmpzb24iKSwKXSkKZGVmIHRlc3RfaDAwMV90ZW1wb3JhbF9jYW5kaWRhdGVfcmVyZXZpZXdfcmVqZWN0c19yZXBhaXJfc2Nv'
        'cGVfbXV0YXRpb25zKG11dGF0aW9uKToKICAgIHZhbHVlID0ganNvbi5sb2FkcyhURU1QT1JBTF9SRVJFVklFVy5yZWFkX2J5dGVzKCkpCiAgICBt'
        'dXRhdGlvbih2YWx1ZSkKICAgIHdpdGggcHl0ZXN0LnJhaXNlcyhWYWx1ZUVycm9yKToKICAgICAgICBjb250cmFjdHMudmFsaWRhdGVfaDAwMV90'
        'ZW1wb3JhbF9jYW5kaWRhdGVfcmVyZXZpZXdfcmVjb3JkKGNvbnRyYWN0cy5jYW5vbmljYWxfanNvbl9ieXRlcyh2YWx1ZSkpCgoKZGVmIHRlc3Rf'
        'aDAwMV90ZW1wb3JhbF9jYW5kaWRhdGVfcmVyZXZpZXdfdmVyaWZpZWRfZXhwb3J0X2NvbW1hbmRfaXNfaG9uZXN0KCk6CiAgICBoYW5kb2ZmID0g'
        'anNvbi5sb2FkcygoUk9PVCAvICJkb2NzL2NvbnRyb2wvdGFza3MvUkVDT1ZFUl9PUl9SRVRJUkVfQ0FORElEQVRFMV9WMF9GUk9aRU5fSU5QVVQv'
        'aGFuZG9mZl92MDE3Lmpzb24iKS5yZWFkX2J5dGVzKCkpCiAgICBjb21tYW5kcyA9IGhhbmRvZmZbInZlcmlmaWVkX2NvbW1hbmRzIl0KICAgIGFz'
        'c2VydCAnUFlUSE9OUEFUSD0iJEVYUE9SVCIgIiRQWSIgLW0gcHl0ZXN0IHRlc3RzL2Fzc3VyYW5jZSB0ZXN0cy9jb250aW51aXR5IC1xJyBpbiBj'
        'b21tYW5kcwogICAgYXNzZXJ0IG5vdCBhbnkoInRlc3RfaDAwMV90ZW1wb3JhbF9jYXVzYWxpdHkucHkgdGVzdHMvY29udGludWl0eSIgaW4gY29t'
        'bWFuZCBmb3IgY29tbWFuZCBpbiBjb21tYW5kcykKCgpAcHl0ZXN0Lm1hcmsucGFyYW1ldHJpemUoInJhdyIsIFtieXRlYXJyYXkoVEVNUE9SQUxf'
        'UkVSRVZJRVcucmVhZF9ieXRlcygpKSwgbWVtb3J5dmlldyhURU1QT1JBTF9SRVJFVklFVy5yZWFkX2J5dGVzKCkpLCBURU1QT1JBTF9SRVJFVklF'
        'Vy5yZWFkX3RleHQoKSwgVEVNUE9SQUxfUkVSRVZJRVcsIG9iamVjdCgpXSkKZGVmIHRlc3RfaDAwMV90ZW1wb3JhbF9jYW5kaWRhdGVfcmVyZXZp'
        'ZXdfcmVxdWlyZXNfZXhhY3RfYnl0ZXMocmF3KToKICAgIHdpdGggcHl0ZXN0LnJhaXNlcyhWYWx1ZUVycm9yLCBtYXRjaD0iZXhhY3QgYnl0ZXMg'
        'aW5wdXQiKToKICAgICAgICBjb250cmFjdHMudmFsaWRhdGVfaDAwMV90ZW1wb3JhbF9jYW5kaWRhdGVfcmVyZXZpZXdfcmVjb3JkKHJhdykKCgpA'
        'cHl0ZXN0Lm1hcmsucGFyYW1ldHJpemUoIm11dGF0aW9uIiwgWwogICAgbGFtYmRhIHY6IHYudXBkYXRlKHJldmlld19iaW5kaW5ncz1kaWN0KHZb'
        'InJldmlld19iaW5kaW5ncyJdLCBwcl9udW1iZXI9Mjg1KSksCiAgICBsYW1iZGEgdjogdi51cGRhdGUoZmluYWxfdmVyZGljdD0iUU5UWV9IMDAx'
        'X1RFTVBPUkFMX0NBVVNBTElUWV9BTUVORE1FTlRfQ0FORElEQVRFX1JFVklFV19GQUlMRUQiKSwKICAgIGxhbWJkYSB2OiB2LnVwZGF0ZShwcmVy'
        'ZWdpc3RlcmVkPVRydWUpLAogICAgbGFtYmRhIHY6IHYudXBkYXRlKGZpbmFsX2ZpbmRpbmdfY291bnRzPXsiYmxvY2tlciI6IDAsICJtYWpvciI6'
        'IDEsICJtaW5vciI6IDB9KSwKICAgIGxhbWJkYSB2OiB2LnVwZGF0ZShub25fZWZmZWN0cz1bIkVER0VfUFJPVkVOIl0pLAogICAgbGFtYmRhIHY6'
        'IHYudXBkYXRlKHJlcGFpcl9zY29wZT12WyJyZXBhaXJfc2NvcGUiXSArIFsidW5leHBlY3RlZC5weSJdKSwKICAgIGxhbWJkYSB2OiB2WyJhcnRp'
        'ZmFjdF9iaW5kaW5ncyJdLl9fc2V0aXRlbV9fKDAsIGRpY3QodlsiYXJ0aWZhY3RfYmluZGluZ3MiXVswXSwgc2hhMjU2PSIwIiAqIDY0KSksCl0p'
        'CmRlZiB0ZXN0X2gwMDFfdGVtcG9yYWxfY2FuZGlkYXRlX3JlcmV2aWV3X3JlY29yZF9yZWplY3RzX211dGF0aW9ucyhtdXRhdGlvbik6CiAgICB2'
        'YWx1ZSA9IGpzb24ubG9hZHMoVEVNUE9SQUxfUkVSRVZJRVcucmVhZF9ieXRlcygpKQogICAgbXV0YXRpb24odmFsdWUpCiAgICB3aXRoIHB5dGVz'
        'dC5yYWlzZXMoVmFsdWVFcnJvcik6CiAgICAgICAgY29udHJhY3RzLnZhbGlkYXRlX2gwMDFfdGVtcG9yYWxfY2FuZGlkYXRlX3JlcmV2aWV3X3Jl'
        'Y29yZChjb250cmFjdHMuY2Fub25pY2FsX2pzb25fYnl0ZXModmFsdWUpKQoKCmRlZiB0ZXN0X2gwMDFfdGVtcG9yYWxfY2FuZGlkYXRlX3JlcmV2'
        'aWV3X3JlY29yZF9yZWplY3RzX2R1cGxpY2F0ZV9vcl9ub25jYW5vbmljYWxfYnl0ZXMoKToKICAgIHJhdyA9IFRFTVBPUkFMX1JFUkVWSUVXLnJl'
        'YWRfYnl0ZXMoKQogICAgZHVwbGljYXRlID0gcmF3WzotMV0gKyBiJywic3RhdHVzIjoiUkVDT1JERURfQUZURVJfUkVWSUVXX05PVF9QUkVSRUdJ'
        'U1RFUkVEIn0nCiAgICB3aXRoIHB5dGVzdC5yYWlzZXMoVmFsdWVFcnJvcik6CiAgICAgICAgY29udHJhY3RzLnZhbGlkYXRlX2gwMDFfdGVtcG9y'
        'YWxfY2FuZGlkYXRlX3JlcmV2aWV3X3JlY29yZChkdXBsaWNhdGUpCiAgICB3aXRoIHB5dGVzdC5yYWlzZXMoVmFsdWVFcnJvcik6CiAgICAgICAg'
        'Y29udHJhY3RzLnZhbGlkYXRlX2gwMDFfdGVtcG9yYWxfY2FuZGlkYXRlX3JlcmV2aWV3X3JlY29yZChqc29uLmR1bXBzKGpzb24ubG9hZHMocmF3'
        'KSkuZW5jb2RlKCkpCg=='
    ),
    'tests/assurance/test_h001_null_calibration.py': (
        'aW1wb3J0IGpzb24KZnJvbSBwYXRobGliIGltcG9ydCBQYXRoCgppbXBvcnQgcHl0ZXN0Cgpmcm9tIHF1YW50Ym90LmFzc3VyYW5jZS5jb250cmFj'
        'dHMgaW1wb3J0IEFzc3VyYW5jZVZhbGlkYXRpb25FcnJvciwgYnVpbGRfc3ludGhldGljX2NhbmFyeV9wYXlsb2FkcywgdmFsaWRhdGVfc3ludGhl'
        'dGljX2NhbmFyeV9zY2FmZm9sZAppbXBvcnQgcXVhbnRib3QuYXNzdXJhbmNlLmgwMDFfbnVsbF9jYWxpYnJhdGlvbiBhcyBjYWxpYnJhdGlvbgpm'
        'cm9tIHF1YW50Ym90LmFzc3VyYW5jZS5oMDAxX251bGxfY2FsaWJyYXRpb24gaW1wb3J0IGJ1aWxkX2NhbGlicmF0aW9uX2V4ZWN1dGlvbl9wbGFu'
        'LCBleGVjdXRlX2NhbGlicmF0aW9uCgpST09UID0gUGF0aChfX2ZpbGVfXykucGFyZW50c1syXQoKZGVmIHRlc3RfY3VycmVudF9kcmFmdF9jYW5u'
        'b3RfYnVpbGRfb3JfZXhlY3V0ZV9jYWxpYnJhdGlvbl9wbGFuKCk6CiAgICBhc3NlcnQgbm90IGhhc2F0dHIoY2FsaWJyYXRpb24sICJDYWxpYnJh'
        'dGlvbkV4ZWN1dGlvblBsYW4iKQogICAgc3BlYyA9IGpzb24ubG9hZHMoKFJPT1QgLyAiZG9jcy9hc3N1cmFuY2UvaDAwMV9zeW50aGV0aWNfbnVs'
        'bF9jYWxpYnJhdGlvbl9zcGVjX2RyYWZ0X3YwMDEuanNvbiIpLnJlYWRfYnl0ZXMoKSkKICAgIHdpdGggcHl0ZXN0LnJhaXNlcyhBc3N1cmFuY2VW'
        'YWxpZGF0aW9uRXJyb3IsIG1hdGNoPSJDQUxJQlJBVElPTl9TUEVDX05PVF9GUk9aRU4iKToKICAgICAgICBidWlsZF9jYWxpYnJhdGlvbl9leGVj'
        'dXRpb25fcGxhbihzcGVjKQogICAgd2l0aCBweXRlc3QucmFpc2VzKEFzc3VyYW5jZVZhbGlkYXRpb25FcnJvciwgbWF0Y2g9IkNBTElCUkFUSU9O'
        'X0VYRUNVVElPTl9OT1RfQVVUSE9SSVpFRCIpOgogICAgICAgIGV4ZWN1dGVfY2FsaWJyYXRpb24oKQoKZGVmIHRlc3RfaW52YWxpZF9jYWxpYnJh'
        'dGlvbl9zcGVjX3ByZXNlcnZlc19jb250cmFjdF9lcnJvcigpOgogICAgc3BlYyA9IGpzb24ubG9hZHMoKFJPT1QgLyAiZG9jcy9hc3N1cmFuY2Uv'
        'aDAwMV9zeW50aGV0aWNfbnVsbF9jYWxpYnJhdGlvbl9zcGVjX2RyYWZ0X3YwMDEuanNvbiIpLnJlYWRfYnl0ZXMoKSkKICAgIHNwZWNbInByb3Bv'
        'c2VkX2Rlc2lnbiJdWyJoYWNfbGFnIl0gPSAyMgogICAgd2l0aCBweXRlc3QucmFpc2VzKEFzc3VyYW5jZVZhbGlkYXRpb25FcnJvciwgbWF0Y2g9'
        'InByb3Bvc2VkIGNhbGlicmF0aW9uIGRlc2lnbiBkcmlmdGVkIik6CiAgICAgICAgYnVpbGRfY2FsaWJyYXRpb25fZXhlY3V0aW9uX3BsYW4oc3Bl'
        'YykKCmRlZiB0ZXN0X2NhbmFyeV9wYXlsb2Fkc19hcmVfaW5fbWVtb3J5X2FuZF9leGFjdCgpOgogICAgZGVzY3JpcHRvciA9IGpzb24ubG9hZHMo'
        'KFJPT1QgLyAiZG9jcy9hc3N1cmFuY2Uvc3ludGhldGljX2FydGlmYWN0X2NhbmFyeV9zY2FmZm9sZF92MDAxLmpzb24iKS5yZWFkX2J5dGVzKCkp'
        'CiAgICB2YWxpZGF0ZV9zeW50aGV0aWNfY2FuYXJ5X3NjYWZmb2xkKGRlc2NyaXB0b3IpCiAgICBwYXlsb2FkcyA9IGJ1aWxkX3N5bnRoZXRpY19j'
        'YW5hcnlfcGF5bG9hZHMoKQogICAgYXNzZXJ0IHBheWxvYWRzID09IHsiYWxwaGEvcGF5bG9hZC50eHQiOiBiIlFOVFlfU1lOVEhFVElDX0NBTkFS'
        'WV9BTFBIQV9WMSIsICJiZXRhL3BheWxvYWQuYmluIjogYnl0ZXMuZnJvbWhleCgiMDA1MTRlNTQ1OWZmIil9CiAgICBhc3NlcnQgbm90IChST09U'
        'IC8gImFscGhhIikuZXhpc3RzKCkKICAgIHdpdGggcHl0ZXN0LnJhaXNlcyhWYWx1ZUVycm9yKTogdmFsaWRhdGVfc3ludGhldGljX2NhbmFyeV9z'
        'Y2FmZm9sZChkaWN0KGRlc2NyaXB0b3IsIHN0YXR1cz0iRVhFQ1VURUQiKSkK'
    ),
}


def _restore_h001_calibration_governance_assurance_tree(destination):
    for path, expected_sha in context._H001_CALIBRATION_GOVERNANCE_ASSURANCE_HASHES.items():
        target = Path(destination) / path
        if hashlib.sha256(target.read_bytes()).hexdigest() == expected_sha:
            continue
        historical = base64.b64decode(_H001_CALIBRATION_GOVERNANCE_HISTORICAL_ASSURANCE_B64[path])
        assert hashlib.sha256(historical).hexdigest() == expected_sha, f"historical {path} does not match pinned governance-era hash"
        target.write_bytes(historical)


def _calibration_governance_mutated_tree(tmp_path, *, mutate_amendment=None, mutate_receipt=None, mutate_active=None, mutate_draft=None):
    root = tmp_path / "repo"
    copy_repo_without_runtime(ROOT, root)
    _restore_h001_calibration_governance_assurance_tree(root)
    active_path = root / context.ACTIVE_TASK_RELPATH
    active = json.loads(active_path.read_bytes())
    active.update(phase=context._H001_CALIBRATION_GOVERNANCE_PHASE, handoff_receipt_path=context._H001_CALIBRATION_GOVERNANCE_HANDOFF_RELPATH, handoff_receipt_sha256="5f210c26c6c7f0b16f1df49173cae22e878071fe46d9933941d639aa37f6d59e")
    active_path.write_bytes(canonical_json_bytes(active))
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
    receipt_path = root / context._H001_CALIBRATION_GOVERNANCE_HANDOFF_RELPATH
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


def test_calibration_governance_historical_fixture_renders_authorized_but_unfrozen(tmp_path):
    root = _calibration_governance_mutated_tree(tmp_path)
    state = load_and_verify_continuity_state(root)
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


def test_calibration_governance_historical_fixture_uses_v019_evidence_inventory(tmp_path):
    root = _calibration_governance_mutated_tree(tmp_path)
    state = load_and_verify_continuity_state(root)
    assert [item["path"] for item in state["handoff_receipt"]["evidence"]] == context._H001_CALIBRATION_GOVERNANCE_EVIDENCE


def test_calibration_governance_v019_evidence_order_mutation_fails_precisely(tmp_path):
    with pytest.raises(ValueError, match=re.escape("H001 calibration governance evidence must be exact, unique, and ordered")):
        load_and_verify_continuity_state(
            _calibration_governance_mutated_tree(tmp_path, mutate_receipt=lambda r: r["evidence"].reverse())
        )


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
    active_path = root / context.ACTIVE_TASK_RELPATH
    active = json.loads(active_path.read_bytes())
    active.update(phase=context._H001_CALIBRATION_CANDIDATE_PHASE, handoff_receipt_path=context._H001_CALIBRATION_CANDIDATE_HANDOFF_RELPATH, handoff_receipt_sha256="6c9a429d2644b8e6fd9f59ee71585994fb6439ff6451ec41e22cdc7b338969a4")
    active_path.write_bytes(canonical_json_bytes(active))
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
    active = json.loads(active_path.read_bytes())
    original_active_sha = active["handoff_receipt_sha256"]
    if mutate_active:
        mutate_active(active)
    if active["handoff_receipt_sha256"] == original_active_sha:
        active["handoff_receipt_sha256"] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    active_path.write_bytes(canonical_json_bytes(active))
    return root


def test_calibration_candidate_production_state_renders_review_required():
    state = load_and_verify_continuity_state(ROOT)
    if state["active_task"]["phase"] in (context._H001_CALIBRATION_REREVIEW_PHASE, context._H001_CALIBRATION_EFFECTIVE_PHASE, context._H001_CALIBRATION_EXECUTION_GOVERNANCE_PHASE, context._H001_CALIBRATION_IMPLEMENTATION_BLOCKED_PHASE):
        pytest.skip("production tree has advanced to the rereview-recorded phase")
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
    if state["active_task"]["phase"] in (context._H001_CALIBRATION_REREVIEW_PHASE, context._H001_CALIBRATION_EFFECTIVE_PHASE, context._H001_CALIBRATION_EXECUTION_GOVERNANCE_PHASE, context._H001_CALIBRATION_IMPLEMENTATION_BLOCKED_PHASE):
        pytest.skip("production tree has advanced to the rereview-recorded phase")
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
    if state["active_task"]["phase"] in (context._H001_CALIBRATION_REREVIEW_PHASE, context._H001_CALIBRATION_EFFECTIVE_PHASE, context._H001_CALIBRATION_EXECUTION_GOVERNANCE_PHASE, context._H001_CALIBRATION_IMPLEMENTATION_BLOCKED_PHASE):
        pytest.skip("production tree has advanced to the rereview-recorded phase")
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
    if state["active_task"]["phase"] in (context._H001_CALIBRATION_REREVIEW_PHASE, context._H001_CALIBRATION_EFFECTIVE_PHASE, context._H001_CALIBRATION_EXECUTION_GOVERNANCE_PHASE, context._H001_CALIBRATION_IMPLEMENTATION_BLOCKED_PHASE):
        pytest.skip("production tree has advanced to the rereview-recorded phase")
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
    if state["active_task"]["phase"] in (context._H001_CALIBRATION_REREVIEW_PHASE, context._H001_CALIBRATION_EFFECTIVE_PHASE, context._H001_CALIBRATION_EXECUTION_GOVERNANCE_PHASE, context._H001_CALIBRATION_IMPLEMENTATION_BLOCKED_PHASE):
        pytest.skip("production tree has advanced to the rereview-recorded phase")
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


# --- H001 calibration spec freeze activation (effective, still fail-closed) --

def _calibration_effective_mutated_tree(
    tmp_path, *, mutate_amendment=None, mutate_receipt=None, mutate_active=None,
    mutate_candidate=None, mutate_validator=None,
):
    root = tmp_path / "repo"
    copy_repo_without_runtime(ROOT, root)
    active_path = root / context.ACTIVE_TASK_RELPATH
    active = json.loads(active_path.read_bytes())
    active.update(
        phase=context._H001_CALIBRATION_EFFECTIVE_PHASE,
        handoff_receipt_path=context._H001_CALIBRATION_EFFECTIVE_HANDOFF_RELPATH,
        handoff_receipt_sha256=context._H001_CALIBRATION_EXECUTION_GOVERNANCE_V022_SHA,
    )
    active_path.write_bytes(canonical_json_bytes(active))
    amendment_path = root / context._H001_CALIBRATION_EFFECTIVE_AMENDMENT_RELPATH
    if mutate_amendment:
        amendment = json.loads(amendment_path.read_bytes())
        mutate_amendment(amendment)
        amendment_path.write_bytes(canonical_json_bytes(amendment))
    if mutate_candidate:
        candidate_path = root / context._H001_CALIBRATION_CANDIDATE_RELPATH
        candidate = json.loads(candidate_path.read_bytes())
        mutate_candidate(candidate)
        candidate_path.write_bytes(canonical_json_bytes(candidate))
    if mutate_validator:
        validator_path = root / context._H001_VALIDATOR_RELPATH
        validator_path.write_bytes(mutate_validator(validator_path.read_bytes()))
    receipt_path = root / context._H001_CALIBRATION_EFFECTIVE_HANDOFF_RELPATH
    receipt = json.loads(receipt_path.read_bytes())
    if mutate_receipt:
        mutate_receipt(receipt)
    for item in receipt["evidence"]:
        target = root / item["path"]
        if target.is_file():
            item["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    receipt_path.write_bytes(canonical_json_bytes(receipt))
    active = json.loads(active_path.read_bytes())
    original_active_sha = active["handoff_receipt_sha256"]
    if mutate_active:
        mutate_active(active)
    if active["handoff_receipt_sha256"] == original_active_sha:
        active["handoff_receipt_sha256"] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    active_path.write_bytes(canonical_json_bytes(active))
    return root


@pytest.mark.parametrize("mutate", [
    lambda a: a.update(effective=False),
    lambda a: a["authorization_state"].update(specification_frozen_effective=False),
    lambda a: a["effective_specification"].update(sha256="0" * 64),
    lambda a: a["hash_bindings"]["candidate_rereview_record"].update(sha256="0" * 64),
    lambda a: a["hash_bindings"]["handoff_v021"].update(sha256="0" * 64),
    lambda a: a["review_history"].update(candidate_final_reviewed_head="0" * 40),
    lambda a: a["review_history"].update(review_record_merge_commit="0" * 40),
    lambda a: a["frozen_values"].update(hac_lag=22),
    lambda a: a["authorization_state"].update(execution_authorized=True),
    lambda a: a["authorization_state"].update(execution_implementation_authorized=True),
    lambda a: a["authorization_state"].update(results_exposed=True),
    lambda a: a["authorization_state"].update(real_data_access_authorized=True),
    lambda a: a["authorization_state"].update(scientific_authorization=True),
    lambda a: a["authorization_state"].update(paper_trade_authorization=True),
    lambda a: a["authorization_state"].update(live_authorization=True),
    lambda a: a["non_effects"].remove("EDGE_UNPROVEN"),
    lambda a: a["non_effects"].remove("BLOCK_LIVE_INTEGRATION"),
])
def test_h001_calibration_effective_activation_mutations_fail_closed(tmp_path, mutate):
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(_calibration_effective_mutated_tree(tmp_path, mutate_amendment=mutate))


@pytest.mark.parametrize("mutate", [
    lambda r: r["predecessor"].update(sha256="0" * 64),
    lambda r: r["changed_file_scope"].reverse(),
    lambda r: r["evidence"].reverse(),
    lambda r: r["decisions"].remove("H001_SYNTHETIC_NULL_CALIBRATION_SPEC_FREEZE=EFFECTIVE"),
    lambda r: r["blockers"].append("H001 calibration specification remains unfrozen"),
    lambda r: r["blockers"].remove("H001 synthetic calibration execution remains unauthorized"),
    lambda r: r["safety_state"].update(decomposition_execution_budget=2),
    lambda r: r["safety_state"].update(decomposition_execution_count=1),
    lambda r: r["safety_state"].update(scientific_use_authorized=True),
    lambda r: r["safety_state"].update(paper_trade_authorized=True),
    lambda r: r["safety_state"].update(live_integration_authorized=True),
    lambda r: r["safety_state"].update(real_data_execution_requested=True),
    lambda r: r.update(next_actions=["EXECUTE_CALIBRATION"]),
    lambda r: r.update(phase=context._H001_CALIBRATION_REREVIEW_PHASE),
])
def test_h001_calibration_effective_handoff_mutations_fail_closed(tmp_path, mutate):
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(_calibration_effective_mutated_tree(tmp_path, mutate_receipt=mutate))


@pytest.mark.parametrize("mutate", [
    lambda a: a.update(phase=context._H001_CALIBRATION_REREVIEW_PHASE),
    lambda a: a.update(handoff_receipt_path=context._H001_CALIBRATION_REREVIEW_RECORD_RELPATH),
    lambda a: a.update(handoff_receipt_sha256="0" * 64),
])
def test_h001_calibration_effective_active_task_mutations_fail_closed(tmp_path, mutate):
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(_calibration_effective_mutated_tree(tmp_path, mutate_active=mutate))


def test_h001_calibration_effective_candidate_and_temporal_bindings_fail_closed(tmp_path):
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(_calibration_effective_mutated_tree(tmp_path, mutate_candidate=lambda c: c["registered_test_target"].update(hac_lag=22)))
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(_calibration_effective_mutated_tree(tmp_path / "validator", mutate_validator=lambda raw: raw.replace(b"latest funding_time_utc < bar[t].open_time_utc", b"latest funding_time_utc <= bar[t].open_time_utc", 1)))


def test_h001_calibration_effective_unmutated_tree_verifies_and_renders(tmp_path):
    state = load_and_verify_continuity_state(_calibration_effective_mutated_tree(tmp_path))
    assert state["active_task"]["phase"] == context._H001_CALIBRATION_EFFECTIVE_PHASE
    packet = render_context_packet(state)
    assert "H001_SYNTHETIC_NULL_CALIBRATION_SPEC_FREEZE=EFFECTIVE" in packet
    assert "H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION=NOT_AUTHORIZED" in packet
    assert "H001 calibration specification remains unfrozen" not in packet
    assert "EDGE_UNPROVEN" in packet and "BLOCK_LIVE_INTEGRATION" in packet


# --- H001 calibration execution governance (implementation review only) ----

def _calibration_execution_governance_mutated_tree(
    tmp_path, *, mutate_amendment=None, mutate_receipt=None, mutate_active=None,
):
    root = tmp_path / "repo"
    copy_repo_without_runtime(ROOT, root)
    amendment_path = root / context._H001_CALIBRATION_EXECUTION_GOVERNANCE_AMENDMENT_RELPATH
    if mutate_amendment:
        amendment = json.loads(amendment_path.read_bytes())
        mutate_amendment(amendment)
        amendment_path.write_bytes(canonical_json_bytes(amendment))
    receipt_path = root / context._H001_CALIBRATION_EXECUTION_GOVERNANCE_HANDOFF_RELPATH
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
    active.update({
        "handoff_receipt_path": context._H001_CALIBRATION_EXECUTION_GOVERNANCE_HANDOFF_RELPATH,
        "handoff_receipt_sha256": context._H001_CALIBRATION_IMPLEMENTATION_BLOCKED_V023_SHA,
        "phase": context._H001_CALIBRATION_EXECUTION_GOVERNANCE_PHASE,
    })
    original_sha = active["handoff_receipt_sha256"]
    if mutate_active:
        mutate_active(active)
    if active["handoff_receipt_sha256"] == original_sha:
        active["handoff_receipt_sha256"] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    active_path.write_bytes(canonical_json_bytes(active))
    return root


def test_h001_calibration_execution_governance_historical_fixture_is_implementation_only(tmp_path):
    state = load_and_verify_continuity_state(_calibration_execution_governance_mutated_tree(tmp_path))
    assert state["active_task"]["phase"] == context._H001_CALIBRATION_EXECUTION_GOVERNANCE_PHASE
    assert state["handoff_receipt"]["receipt_index"] == 23
    packet = render_context_packet(state)
    for marker in (
        "H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION_GOVERNANCE=AUTHORIZED_IMPLEMENTATION_FOR_INDEPENDENT_REVIEW_ONLY",
        "H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION_IMPLEMENTATION=NOT_IMPLEMENTED",
        "H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION=NOT_AUTHORIZED",
        "H001_SYNTHETIC_NULL_CALIBRATION_RESULTS=NONE",
        "H001_REAL_DATA_ACCESS=FORBIDDEN", "H001_EXECUTION=0/0",
        "H001_SCIENTIFIC_AUTHORIZATION=FALSE", "H001_PAPER_TRADE_AUTHORIZATION=FALSE",
        "H001_LIVE_AUTHORIZATION=FALSE", "EDGE_UNPROVEN", "BLOCK_LIVE_INTEGRATION",
    ):
        assert marker in packet
    assert "H001 calibration specification remains unfrozen" not in packet


@pytest.mark.parametrize("mutate", [
    lambda a: a.update(base_main_commit="0" * 40),
    lambda a: a["hash_bindings"]["effective_frozen_candidate"].update(sha256="0" * 64),
    lambda a: a["hash_bindings"]["freeze_activation_amendment"].update(sha256="0" * 64),
    lambda a: a["hash_bindings"]["candidate_rereview_record"].update(sha256="0" * 64),
    lambda a: a["hash_bindings"]["predecessor_handoff"].update(sha256="0" * 64),
    lambda a: a["hash_bindings"]["activated_h001_design"].update(sha256="0" * 64),
    lambda a: a.update(execution_authorized=True),
    lambda a: a.update(results="AVAILABLE"),
    lambda a: a["transition_gates"].update(h001_execution_budget=1),
    lambda a: a["transition_gates"].update(h001_execution_count=1),
    lambda a: a["transition_gates"].update(real_data_access_authorized=True),
    lambda a: a["transition_gates"].update(scientific_authorization=True),
    lambda a: a["transition_gates"].update(paper_trade_authorization=True),
    lambda a: a["transition_gates"].update(live_authorization=True),
])
def test_h001_calibration_execution_governance_amendment_mutations_fail_closed(tmp_path, mutate):
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(_calibration_execution_governance_mutated_tree(tmp_path, mutate_amendment=mutate))


@pytest.mark.parametrize("mutate", [
    lambda r: r["predecessor"].update(sha256="0" * 64),
    lambda r: r["changed_file_scope"].append("docs/control/extra.json"),
    lambda r: r["changed_file_scope"].reverse(),
    lambda r: r.update(next_actions=["AUTHORIZE_H001_CALIBRATION_EXECUTION"]),
    lambda r: r["blockers"].remove("H001 synthetic calibration execution remains unauthorized"),
    lambda r: r["blockers"].append("H001 calibration specification remains unfrozen"),
    lambda r: r["decisions"].__setitem__(r["decisions"].index("H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION=NOT_AUTHORIZED"), "H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION=AUTHORIZED"),
    lambda r: r["decisions"].__setitem__(r["decisions"].index("H001_SYNTHETIC_NULL_CALIBRATION_RESULTS=NONE"), "H001_SYNTHETIC_NULL_CALIBRATION_RESULTS=AVAILABLE"),
    lambda r: r["decisions"].__setitem__(r["decisions"].index("H001_EXECUTION=0/0"), "H001_EXECUTION=1/1"),
    lambda r: r["decisions"].__setitem__(r["decisions"].index("H001_REAL_DATA_ACCESS=FORBIDDEN"), "H001_REAL_DATA_ACCESS=AUTHORIZED"),
    lambda r: r["safety_state"].update(scientific_use_authorized=True),
    lambda r: r["safety_state"].update(paper_trade_authorized=True),
    lambda r: r["safety_state"].update(live_integration_authorized=True),
])
def test_h001_calibration_execution_governance_receipt_mutations_fail_closed(tmp_path, mutate):
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(_calibration_execution_governance_mutated_tree(tmp_path, mutate_receipt=mutate))


def test_h001_calibration_execution_governance_active_pointer_and_no_git_fail_closed(tmp_path):
    root = _calibration_execution_governance_mutated_tree(
        tmp_path, mutate_active=lambda a: a.update(handoff_receipt_sha256="0" * 64),
    )
    with pytest.raises(ValueError):
        load_and_verify_continuity_state(root)
    clean = _calibration_execution_governance_mutated_tree(tmp_path / "clean")
    assert not (clean / ".git").exists()
    assert load_and_verify_continuity_state(clean)["active_task"]["phase"] == context._H001_CALIBRATION_EXECUTION_GOVERNANCE_PHASE


# --- H001 calibration engine implementation blocked before change ----------

def _rewrite_v024(root, receipt, *, mutate_active=None):
    receipt_path = root / context._H001_CALIBRATION_IMPLEMENTATION_BLOCKED_HANDOFF_RELPATH
    receipt_path.write_bytes(canonical_json_bytes(receipt))
    active_path = root / context.ACTIVE_TASK_RELPATH
    active = json.loads(active_path.read_bytes())
    if mutate_active:
        mutate_active(active)
    else:
        active["handoff_receipt_sha256"] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    active_path.write_bytes(canonical_json_bytes(active))
    return root


def _calibration_implementation_blocked_mutated_tree(tmp_path, *, mutate_receipt=None, mutate_active=None):
    root = tmp_path / "repo"
    copy_repo_without_runtime(ROOT, root)
    receipt_path = root / context._H001_CALIBRATION_IMPLEMENTATION_BLOCKED_HANDOFF_RELPATH
    receipt = json.loads(receipt_path.read_bytes())
    if mutate_receipt:
        mutate_receipt(receipt)
    return _rewrite_v024(root, receipt, mutate_active=mutate_active)


def test_h001_calibration_implementation_blocked_production_state_is_exact():
    state = load_and_verify_continuity_state(ROOT)
    receipt = state["handoff_receipt"]
    assert state["active_task"]["phase"] == context._H001_CALIBRATION_IMPLEMENTATION_BLOCKED_PHASE
    assert receipt["receipt_index"] == 24
    assert receipt["numerical_convention_gap_inventory"] == context._H001_CALIBRATION_IMPLEMENTATION_BLOCKED_GAPS
    assert [item["path"] for item in receipt["evidence"]] == context._H001_CALIBRATION_IMPLEMENTATION_BLOCKED_EVIDENCE
    assert [item["path"] for item in receipt["current_transition_files"]] == context._H001_CALIBRATION_IMPLEMENTATION_BLOCKED_CURRENT_TRANSITION_FILES
    packet = render_context_packet(state)
    for marker in (
        "H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION_ENGINE_IMPLEMENTATION_ATTEMPT=BLOCKED_BEFORE_CHANGE",
        "H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION_ENGINE_IMPLEMENTATION_COMMIT=NONE",
        "H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION_ENGINE_IMPLEMENTATION_PR=NONE",
        "H001_SYNTHETIC_NULL_CALIBRATION_NUMERICAL_CONVENTIONS=INCOMPLETE_RESULT_DETERMINATIVE",
        "H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION_IMPLEMENTATION=NOT_IMPLEMENTED",
        "H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION=NOT_AUTHORIZED",
        "H001_SYNTHETIC_NULL_CALIBRATION_RESULTS=NONE",
        "H001_SYNTHETIC_NULL_CALIBRATION_RESULT_EXPOSURE=NONE",
        "H001_EXECUTION=0/0", "H001_REAL_DATA_ACCESS=FORBIDDEN",
        "H001_SCIENTIFIC_AUTHORIZATION=FALSE", "H001_PAPER_TRADE_AUTHORIZATION=FALSE",
        "H001_LIVE_AUTHORIZATION=FALSE", "EDGE_UNPROVEN", "BLOCK_LIVE_INTEGRATION",
    ):
        assert marker in packet
    assert "H001 calibration specification remains unfrozen" not in packet


@pytest.mark.parametrize("mutate,message", [
    (lambda r: r["numerical_convention_gap_inventory"].pop(), "H001 calibration implementation-block numerical gaps drifted"),
    (lambda r: r["numerical_convention_gap_inventory"].append("EXTRA_GAP"), "H001 calibration implementation-block numerical gaps drifted"),
    (lambda r: r["numerical_convention_gap_inventory"].reverse(), "H001 calibration implementation-block numerical gaps drifted"),
    (lambda r: r["numerical_convention_gap_inventory"].append(r["numerical_convention_gap_inventory"][0]), "H001 calibration implementation-block numerical gaps drifted"),
    (lambda r: r["decisions"].append("HAC_AUTOCOVARIANCE_FORMULA=SELECTED"), "H001 calibration implementation-block decisions drifted"),
    (lambda r: r["decisions"].__setitem__(r["decisions"].index("H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION_IMPLEMENTATION=NOT_IMPLEMENTED"), "H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION_IMPLEMENTATION=PARTIALLY_IMPLEMENTED"), "H001 calibration implementation-block decisions drifted"),
    (lambda r: r["decisions"].__setitem__(r["decisions"].index("H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION_ENGINE_IMPLEMENTATION_COMMIT=NONE"), "H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION_ENGINE_IMPLEMENTATION_COMMIT=abc"), "H001 calibration implementation-block decisions drifted"),
    (lambda r: r["decisions"].__setitem__(r["decisions"].index("H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION_ENGINE_IMPLEMENTATION_PR=NONE"), "H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION_ENGINE_IMPLEMENTATION_PR=123"), "H001 calibration implementation-block decisions drifted"),
    (lambda r: r["decisions"].__setitem__(r["decisions"].index("H001_EXECUTION=0/0"), "H001_EXECUTION=1/1"), "H001 calibration implementation-block decisions drifted"),
    (lambda r: r["decisions"].__setitem__(r["decisions"].index("H001_REAL_DATA_ACCESS=FORBIDDEN"), "H001_REAL_DATA_ACCESS=AUTHORIZED"), "H001 calibration implementation-block decisions drifted"),
    (lambda r: r["next_actions"].__setitem__(0, "CREATE_H001_SYNTHETIC_NULL_CALIBRATION_NUMERICAL_CONVENTIONS_AMENDMENT"), "H001 calibration implementation-block next action is wrong"),
    (lambda r: r["safety_state"].update(scientific_use_authorized=True), "H001 calibration implementation-block changed persistent safety state"),
    (lambda r: r["safety_state"].update(paper_trade_authorized=True), "H001 calibration implementation-block changed persistent safety state"),
    (lambda r: r["safety_state"].update(live_integration_authorized=True), "H001 calibration implementation-block changed persistent safety state"),
])
def test_h001_calibration_implementation_blocked_semantic_mutations_fail_closed(tmp_path, mutate, message):
    with pytest.raises(ValueError, match=re.escape(message)):
        load_and_verify_continuity_state(_calibration_implementation_blocked_mutated_tree(tmp_path, mutate_receipt=mutate))


@pytest.mark.parametrize("mutate", [
    lambda r: r["blockers"].pop(),
    lambda r: r["blockers"].append("EXTRA_BLOCKER"),
    lambda r: r["blockers"].reverse(),
])
def test_h001_calibration_implementation_blocked_blocker_drift_fails_precisely(tmp_path, mutate):
    with pytest.raises(ValueError, match=re.escape("H001 calibration implementation-block blockers drifted")):
        load_and_verify_continuity_state(_calibration_implementation_blocked_mutated_tree(tmp_path, mutate_receipt=mutate))


def test_h001_calibration_implementation_blocked_each_duplicate_blocker_fails_precisely(tmp_path):
    for blocker in context._H001_CALIBRATION_IMPLEMENTATION_BLOCKED_BLOCKERS:
        with pytest.raises(ValueError, match=re.escape("H001 calibration implementation-block blockers contain duplicates")):
            load_and_verify_continuity_state(
                _calibration_implementation_blocked_mutated_tree(
                    tmp_path / blocker.replace(" ", "_"),
                    mutate_receipt=lambda r, blocker=blocker: r["blockers"].append(blocker),
                )
            )


def _protected_evidence_mutated_tree(tmp_path, *, evidence_path, mutate_file):
    root = tmp_path / "repo"
    copy_repo_without_runtime(ROOT, root)
    mutate_file(root / evidence_path)
    receipt_path = root / context._H001_CALIBRATION_IMPLEMENTATION_BLOCKED_HANDOFF_RELPATH
    receipt = json.loads(receipt_path.read_bytes())
    for item in receipt["evidence"]:
        target = root / item["path"]
        item["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    return _rewrite_v024(root, receipt)


@pytest.mark.parametrize("evidence_path,mutate_file", [
    ("quantbot/assurance/contracts.py", lambda p: p.write_text(p.read_text() + "\n# attack\n", encoding="utf-8")),
    ("quantbot/assurance/h001_null_calibration.py", lambda p: p.write_text(p.read_text() + "\n# attack\n", encoding="utf-8")),
    ("docs/assurance/h001_synthetic_null_calibration_spec_freeze_candidate_v001.json", lambda p: p.write_text(p.read_text().replace("freeze", "thaw", 1), encoding="utf-8")),
    ("docs/experiments/candidate1_h001_real_data_falsification_v0.json", lambda p: p.write_text(p.read_text().replace("NOT_", "NOTX_", 1), encoding="utf-8")),
    ("quantbot/experiment/h001_real_falsification_preregistration.py", lambda p: p.write_text(p.read_text() + "\n# attack\n", encoding="utf-8")),
    ("docs/artifacts/candidate1-real-input-v0.json", lambda p: p.write_text(p.read_text() + "\n", encoding="utf-8")),
    ("docs/artifacts/stores.json", lambda p: p.write_text(p.read_text().replace('"stores":[]', '"stores":[{"id":"fake"}]'), encoding="utf-8")),
])
def test_h001_calibration_implementation_blocked_protected_evidence_attacks_fail_precisely(tmp_path, evidence_path, mutate_file):
    message = f"H001 calibration implementation-block protected evidence {evidence_path!r} hash mismatch"
    with pytest.raises(ValueError, match=re.escape(message)):
        load_and_verify_continuity_state(_protected_evidence_mutated_tree(tmp_path, evidence_path=evidence_path, mutate_file=mutate_file))


@pytest.mark.parametrize("mutate", [
    lambda r: r["evidence"].pop(),
    lambda r: r["evidence"].append({"path": "docs/control/active_task.json", "sha256": "0" * 64}),
    lambda r: r["evidence"].reverse(),
    lambda r: r["evidence"].append(dict(r["evidence"][0])),
])
def test_h001_calibration_implementation_blocked_protected_evidence_list_attacks_fail_precisely(tmp_path, mutate):
    with pytest.raises(ValueError, match=re.escape("H001 calibration implementation-block protected evidence list must be exact, unique, and ordered")):
        load_and_verify_continuity_state(_calibration_implementation_blocked_mutated_tree(tmp_path, mutate_receipt=mutate))


def test_h001_calibration_implementation_blocked_recorded_protected_hash_fails_precisely(tmp_path):
    def mutate(receipt):
        receipt["evidence"][0]["sha256"] = "0" * 64
    message = f"H001 calibration implementation-block protected evidence {context._H001_CALIBRATION_EXECUTION_GOVERNANCE_HANDOFF_RELPATH!r} hash mismatch"
    with pytest.raises(ValueError, match=re.escape(message)):
        load_and_verify_continuity_state(_calibration_implementation_blocked_mutated_tree(tmp_path, mutate_receipt=mutate))


@pytest.mark.parametrize("field,message", [
    ("evidence", "evidence must be a list"),
    ("safety_state", "safety_state must be a JSON object"),
    ("numerical_convention_gap_inventory", "H001 calibration implementation-block numerical gaps must be a list"),
    ("current_transition_files", "H001 calibration implementation-block current-transition files must be a list"),
])
def test_h001_calibration_implementation_blocked_malformed_shapes_fail_closed(tmp_path, field, message):
    with pytest.raises(ValueError, match=re.escape(message)):
        load_and_verify_continuity_state(
            _calibration_implementation_blocked_mutated_tree(
                tmp_path / field,
                mutate_receipt=lambda receipt: receipt.__setitem__(field, None),
            )
        )


@pytest.mark.parametrize("mutate", [
    lambda r: r["current_transition_files"].pop(),
    lambda r: r["current_transition_files"].append({"path": "docs/control/active_task.json", "sha256": "0" * 64}),
    lambda r: r["current_transition_files"].reverse(),
    lambda r: r["current_transition_files"].append(dict(r["current_transition_files"][0])),
    lambda r: r["current_transition_files"][0].update(sha256="0" * 64),
])
def test_h001_calibration_implementation_blocked_current_transition_attacks_fail_precisely(tmp_path, mutate):
    with pytest.raises(ValueError, match=re.escape("H001 calibration implementation-block current-transition files must be exact, unique, and hash-bound")):
        load_and_verify_continuity_state(_calibration_implementation_blocked_mutated_tree(tmp_path, mutate_receipt=mutate))


def test_h001_calibration_implementation_blocked_predecessor_and_active_pointer_fail_closed(tmp_path):
    with pytest.raises(ValueError, match=re.escape("H001 calibration implementation-block predecessor is wrong")):
        load_and_verify_continuity_state(_calibration_implementation_blocked_mutated_tree(
            tmp_path / "chain", mutate_receipt=lambda r: r["predecessor"].update(sha256="0" * 64),
        ))
    with pytest.raises(ValueError, match=re.escape("active_task pointer is stale: handoff receipt bytes do not match handoff_receipt_sha256")):
        load_and_verify_continuity_state(_calibration_implementation_blocked_mutated_tree(
            tmp_path / "pointer", mutate_active=lambda a: a.update(handoff_receipt_sha256="0" * 64),
        ))


def test_h001_calibration_implementation_blocked_no_git_tree_verifies(tmp_path):
    clean = _calibration_implementation_blocked_mutated_tree(tmp_path)
    assert not (clean / ".git").exists()
    assert load_and_verify_continuity_state(clean)["active_task"]["phase"] == context._H001_CALIBRATION_IMPLEMENTATION_BLOCKED_PHASE
