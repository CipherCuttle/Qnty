"""Adversarial checks for v043's C1-directionality atomic repair candidate
transition: it must create exactly one review-required candidate for the
signed positive one-sided directionality repair, explicitly keep C2 an
independent unresolved blocker, never amend or retroactively approve the
rejected v042 candidate, and grant no implementation, wiring, activation, or
execution authority."""

import copy
import hashlib
import json
import shutil

import pytest

from quantbot.continuity import context
from quantbot.continuity import h001_c1_directionality_atomic_repair_candidate_v043 as v043

ROOT = __import__("pathlib").Path(__file__).parents[2]


def _tree(tmp_path):
    root = tmp_path / "repo"
    shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__"))
    return root


def _write(path, value):
    path.write_bytes(context.canonical_json_bytes(value))


def _fail(root):
    with pytest.raises(ValueError):
        context.load_and_verify_continuity_state(root)


def _ok(root):
    context.load_and_verify_continuity_state(root)


def _receipt(root):
    return json.loads((root / v043.HANDOFF_RELPATH).read_bytes())


def _write_receipt_and_repoint(root, receipt):
    _write(root / v043.HANDOFF_RELPATH, receipt)
    active = json.loads((root / context.ACTIVE_TASK_RELPATH).read_bytes())
    active["handoff_receipt_sha256"] = hashlib.sha256((root / v043.HANDOFF_RELPATH).read_bytes()).hexdigest()
    _write(root / context.ACTIVE_TASK_RELPATH, active)


def _amendment(root):
    return json.loads((root / v043.AMENDMENT_RELPATH).read_bytes())


def _write_amendment_and_reissue_evidence(root, amendment):
    raw = context.canonical_json_bytes(amendment)
    (root / v043.AMENDMENT_RELPATH).write_bytes(raw)
    receipt = _receipt(root)
    receipt["evidence"] = copy.deepcopy(receipt["evidence"])
    receipt["evidence"][-1] = {"path": v043.AMENDMENT_RELPATH, "sha256": hashlib.sha256(raw).hexdigest()}
    _write_receipt_and_repoint(root, receipt)


def test_v043_baseline_verifies(tmp_path):
    root = _tree(tmp_path)
    _ok(root)


def test_v043_baseline_amendment_matches_module_constant(tmp_path):
    root = _tree(tmp_path)
    assert _amendment(root) == v043.AMENDMENT_DOCUMENT


def test_v043_rejects_predecessor_tamper(tmp_path):
    root = _tree(tmp_path)
    receipt = _receipt(root)
    receipt["predecessor"] = copy.deepcopy(receipt["predecessor"])
    receipt["predecessor"]["sha256"] = "0" * 64
    _write_receipt_and_repoint(root, receipt)
    _fail(root)


def test_v043_rejects_predecessor_pointing_at_rejected_v042(tmp_path):
    root = _tree(tmp_path)
    receipt = _receipt(root)
    receipt["predecessor"] = {
        "path": "docs/control/tasks/RECOVER_OR_RETIRE_CANDIDATE1_V0_FROZEN_INPUT/handoff_v042.json",
        "sha256": "0" * 64,
    }
    _write_receipt_and_repoint(root, receipt)
    _fail(root)


def test_v043_rejects_receipt_index_drift(tmp_path):
    root = _tree(tmp_path)
    receipt = _receipt(root)
    receipt["receipt_index"] = 44
    _write_receipt_and_repoint(root, receipt)
    _fail(root)


def test_v043_rejects_source_mutation_after_binding(tmp_path):
    root = _tree(tmp_path)
    target = root / v043.AMENDMENT_RELPATH
    target.write_bytes(target.read_bytes() + b"\n")
    _fail(root)


def test_v043_rejects_next_action_drift_to_raw_implementation(tmp_path):
    root = _tree(tmp_path)
    receipt = _receipt(root)
    receipt["next_actions"] = ["IMPLEMENT_H001_C1_DIRECTIONALITY_ATOMIC_REPAIR"]
    _write_receipt_and_repoint(root, receipt)
    _fail(root)


@pytest.mark.parametrize("dropped", [
    "EXECUTE_H001",
    "IMPLEMENT_H001_C1_DIRECTIONALITY_ATOMIC_REPAIR_BEFORE_INDEPENDENT_REVIEW",
    "MERGE_H001_C1_DIRECTIONALITY_ATOMIC_REPAIR_CANDIDATE_BEFORE_INDEPENDENT_ADVERSARIAL_REVIEW",
    "TREAT_C1_CANDIDATE_REVIEW_AS_C2_RESOLUTION",
    "AMEND_OR_MODIFY_REJECTED_V042_CANDIDATE_COMMIT_OR_BRANCH",
    "ACTIVATE_H001_BEFORE_BOTH_C1_REVIEW_AND_C2_RESOLUTION",
])
def test_v043_rejects_dropped_prohibition(tmp_path, dropped):
    root = _tree(tmp_path)
    receipt = _receipt(root)
    receipt["prohibited_actions"] = [x for x in receipt["prohibited_actions"] if x != dropped]
    _write_receipt_and_repoint(root, receipt)
    _fail(root)


def test_v043_rejects_dropped_c2_blocker(tmp_path):
    root = _tree(tmp_path)
    receipt = _receipt(root)
    receipt["blockers"] = [
        x for x in receipt["blockers"]
        if x != "H001 activation blocked pending resolution of C2 historical funding-provenance availability"
    ]
    _write_receipt_and_repoint(root, receipt)
    _fail(root)


@pytest.mark.parametrize(("field", "value"), [
    ("decomposition_execution_budget", 2),
    ("decomposition_execution_count", 1),
    ("scientific_use_authorized", True),
    ("real_data_execution_requested", True),
    ("live_integration_authorized", True),
])
def test_v043_rejects_safety_drift(tmp_path, field, value):
    root = _tree(tmp_path)
    receipt = _receipt(root)
    receipt["safety_state"] = copy.deepcopy(receipt["safety_state"])
    receipt["safety_state"][field] = value
    _write_receipt_and_repoint(root, receipt)
    _fail(root)


def test_v043_rejects_c2_marked_in_scope(tmp_path):
    root = _tree(tmp_path)
    amendment = copy.deepcopy(v043.AMENDMENT_DOCUMENT)
    amendment["c2_status"] = copy.deepcopy(amendment["c2_status"])
    amendment["c2_status"]["in_scope_of_this_candidate"] = True
    _write_amendment_and_reissue_evidence(root, amendment)
    _fail(root)


def test_v043_rejects_c2_marked_resolved(tmp_path):
    root = _tree(tmp_path)
    amendment = copy.deepcopy(v043.AMENDMENT_DOCUMENT)
    amendment["c2_status"] = copy.deepcopy(amendment["c2_status"])
    amendment["c2_status"]["resolution_implied_by_c1_candidate"] = True
    _write_amendment_and_reissue_evidence(root, amendment)
    _fail(root)


def test_v043_rejects_temporal_join_contract_marked_modified(tmp_path):
    root = _tree(tmp_path)
    amendment = copy.deepcopy(v043.AMENDMENT_DOCUMENT)
    amendment["c2_status"] = copy.deepcopy(amendment["c2_status"])
    amendment["c2_status"]["temporal_join_contract_modified"] = True
    _write_amendment_and_reissue_evidence(root, amendment)
    _fail(root)


def test_v043_rejects_third_party_provenance_source_marked_adopted(tmp_path):
    root = _tree(tmp_path)
    amendment = copy.deepcopy(v043.AMENDMENT_DOCUMENT)
    amendment["c2_status"] = copy.deepcopy(amendment["c2_status"])
    amendment["c2_status"]["third_party_provenance_source_adopted"] = True
    _write_amendment_and_reissue_evidence(root, amendment)
    _fail(root)


def test_v043_rejects_rejected_v042_marked_amended(tmp_path):
    root = _tree(tmp_path)
    amendment = copy.deepcopy(v043.AMENDMENT_DOCUMENT)
    amendment["rejected_predecessor_candidate_binding"] = copy.deepcopy(amendment["rejected_predecessor_candidate_binding"])
    amendment["rejected_predecessor_candidate_binding"]["amended_or_modified"] = True
    _write_amendment_and_reissue_evidence(root, amendment)
    _fail(root)


def test_v043_rejects_rejected_v042_marked_retroactively_approved(tmp_path):
    root = _tree(tmp_path)
    amendment = copy.deepcopy(v043.AMENDMENT_DOCUMENT)
    amendment["rejected_predecessor_candidate_binding"] = copy.deepcopy(amendment["rejected_predecessor_candidate_binding"])
    amendment["rejected_predecessor_candidate_binding"]["retroactively_approved"] = True
    _write_amendment_and_reissue_evidence(root, amendment)
    _fail(root)


@pytest.mark.parametrize("field", [
    "candidate_review_completed", "activation_authorized", "implementation_authorized",
    "execution_authorized", "real_data_access_authorized", "holdout_execution_authorized",
    "scientific_authorized", "paper_trade_authorized", "live_authorized", "wired_into_execute_calibration",
])
def test_v043_rejects_authorization_claimed(tmp_path, field):
    root = _tree(tmp_path)
    amendment = copy.deepcopy(v043.AMENDMENT_DOCUMENT)
    amendment["authorization_state"] = copy.deepcopy(amendment["authorization_state"])
    amendment["authorization_state"][field] = True
    _write_amendment_and_reissue_evidence(root, amendment)
    _fail(root)


@pytest.mark.parametrize("field", ["h001_execution_budget", "h001_execution_count"])
def test_v043_rejects_execution_budget_or_count_raised(tmp_path, field):
    root = _tree(tmp_path)
    amendment = copy.deepcopy(v043.AMENDMENT_DOCUMENT)
    amendment["authorization_state"] = copy.deepcopy(amendment["authorization_state"])
    amendment["authorization_state"][field] = 1
    _write_amendment_and_reissue_evidence(root, amendment)
    _fail(root)


def test_v043_rejects_implementation_repair_marked_complete(tmp_path):
    root = _tree(tmp_path)
    amendment = copy.deepcopy(v043.AMENDMENT_DOCUMENT)
    amendment["dependent_repair_boundary"] = copy.deepcopy(amendment["dependent_repair_boundary"])
    amendment["dependent_repair_boundary"]["implementation_repair_complete"] = True
    _write_amendment_and_reissue_evidence(root, amendment)
    _fail(root)


def test_v043_rejects_p0_count_not_derived_from_p0_findings(tmp_path):
    root = _tree(tmp_path)
    amendment = copy.deepcopy(v043.AMENDMENT_DOCUMENT)
    amendment["audit_binding"] = copy.deepcopy(amendment["audit_binding"])
    amendment["audit_binding"]["p0_count"] = 2
    _write_amendment_and_reissue_evidence(root, amendment)
    _fail(root)


def test_v043_rejects_p0_findings_padded_to_include_c2(tmp_path):
    root = _tree(tmp_path)
    amendment = copy.deepcopy(v043.AMENDMENT_DOCUMENT)
    amendment["audit_binding"] = copy.deepcopy(amendment["audit_binding"])
    amendment["audit_binding"]["p0_findings"] = ["C1_DIRECTIONALITY_CONTRACT_RECONCILIATION", "C2_TEMPORAL_BOUNDARY_CONTRACT_RECONCILIATION"]
    amendment["audit_binding"]["p0_count"] = 2
    _write_amendment_and_reissue_evidence(root, amendment)
    _fail(root)


@pytest.mark.parametrize("field", ["h001_activated", "h001_executed", "real_data_accessed", "holdout_accessed", "repository_modified"])
def test_v043_rejects_audit_binding_claiming_access_or_authority(tmp_path, field):
    root = _tree(tmp_path)
    amendment = copy.deepcopy(v043.AMENDMENT_DOCUMENT)
    amendment["audit_binding"] = copy.deepcopy(amendment["audit_binding"])
    amendment["audit_binding"][field] = True
    _write_amendment_and_reissue_evidence(root, amendment)
    _fail(root)


def test_v043_rejects_scope_drift(tmp_path):
    root = _tree(tmp_path)
    receipt = _receipt(root)
    receipt["changed_file_scope"] = copy.deepcopy(receipt["changed_file_scope"])
    receipt["changed_file_scope"][0] = "wrong"
    _write_receipt_and_repoint(root, receipt)
    _fail(root)


def test_v043_rejects_protected_v041_handoff_tamper(tmp_path):
    root = _tree(tmp_path)
    target = root / v043.previous.HANDOFF_RELPATH
    target.write_bytes(target.read_bytes()[:-1] + b" ")
    _fail(root)
