"""Adversarial checks for v038's per-run coordinate and seed orchestration
candidate transition: it must create exactly one review-required candidate
implementation for the selected component and grant no implementation,
wiring, or execution authority."""

import copy
import hashlib
import json
import shutil

import pytest

from quantbot.continuity import context
from quantbot.continuity import h001_per_run_coordinate_and_seed_orchestration_candidate_v038 as v038


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
    return json.loads((root / v038.HANDOFF_RELPATH).read_bytes())


def _write_receipt_and_repoint(root, receipt):
    _write(root / v038.HANDOFF_RELPATH, receipt)
    active = json.loads((root / context.ACTIVE_TASK_RELPATH).read_bytes())
    active["handoff_receipt_sha256"] = hashlib.sha256((root / v038.HANDOFF_RELPATH).read_bytes()).hexdigest()
    _write(root / context.ACTIVE_TASK_RELPATH, active)


def test_v038_baseline_verifies(tmp_path):
    root = _tree(tmp_path)
    _ok(root)


@pytest.mark.parametrize("field", ["orchestration_reviewed", "orchestration_executed", "orchestration_wired_into_execute_calibration"])
def test_v038_rejects_binding_claiming_authority_it_does_not_have(tmp_path, field):
    root = _tree(tmp_path)
    receipt = _receipt(root)
    receipt["per_run_coordinate_and_seed_orchestration_binding"] = copy.deepcopy(receipt["per_run_coordinate_and_seed_orchestration_binding"])
    receipt["per_run_coordinate_and_seed_orchestration_binding"][field] = True
    _write_receipt_and_repoint(root, receipt)
    _fail(root)


def test_v038_rejects_predecessor_tamper(tmp_path):
    root = _tree(tmp_path)
    receipt = _receipt(root)
    receipt["predecessor"] = copy.deepcopy(receipt["predecessor"])
    receipt["predecessor"]["sha256"] = "0" * 64
    _write_receipt_and_repoint(root, receipt)
    _fail(root)


def test_v038_rejects_source_mutation_after_binding(tmp_path):
    root = _tree(tmp_path)
    target = root / v038.ORCH_RELPATH
    target.write_bytes(target.read_bytes() + b"\n# tampered\n")
    _fail(root)


def test_v038_rejects_test_mutation_after_binding(tmp_path):
    root = _tree(tmp_path)
    target = root / v038.ORCH_TEST_RELPATH
    target.write_bytes(target.read_bytes() + b"\n# tampered\n")
    _fail(root)


def test_v038_rejects_next_action_drift_to_raw_implementation(tmp_path):
    root = _tree(tmp_path)
    receipt = _receipt(root)
    receipt["next_actions"] = ["IMPLEMENT_H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION"]
    _write_receipt_and_repoint(root, receipt)
    _fail(root)


def test_v038_rejects_dropped_execution_prohibition(tmp_path):
    root = _tree(tmp_path)
    receipt = _receipt(root)
    receipt["prohibited_actions"] = [x for x in receipt["prohibited_actions"] if x != "EXECUTE_H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION"]
    _write_receipt_and_repoint(root, receipt)
    _fail(root)


def test_v038_rejects_dropped_implementation_prohibition(tmp_path):
    root = _tree(tmp_path)
    receipt = _receipt(root)
    receipt["prohibited_actions"] = [x for x in receipt["prohibited_actions"] if x != "IMPLEMENT_H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION"]
    _write_receipt_and_repoint(root, receipt)
    _fail(root)


def test_v038_rejects_receipt_index_drift(tmp_path):
    root = _tree(tmp_path)
    receipt = _receipt(root)
    receipt["receipt_index"] = 39
    _write_receipt_and_repoint(root, receipt)
    _fail(root)


def test_v038_rejects_safety_state_weakening(tmp_path):
    root = _tree(tmp_path)
    receipt = _receipt(root)
    receipt["safety_state"] = copy.deepcopy(receipt["safety_state"])
    receipt["safety_state"]["decomposition_execution_budget"] = 2
    _write_receipt_and_repoint(root, receipt)
    _fail(root)


def test_v038_rejects_decision_claiming_review_completed(tmp_path):
    root = _tree(tmp_path)
    receipt = _receipt(root)
    receipt["decisions"] = sorted(
        [x for x in receipt["decisions"] if x != "H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION_REVIEW=REQUIRED"]
        + ["H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION_REVIEW=PASSED"]
    )
    _write_receipt_and_repoint(root, receipt)
    _fail(root)
