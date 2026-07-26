"""Adversarial checks for v036's single-component governance selection."""

import copy
import hashlib
import json
import shutil

import pytest

from quantbot.continuity import context
from quantbot.continuity import h001_per_run_coordinate_and_seed_orchestration_selection_v036 as v036


ROOT = __import__("pathlib").Path(__file__).parents[2]


def _tree(tmp_path):
    root = tmp_path / "repo"
    shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__"))
    return root


def _receipt(root):
    return json.loads((root / v036.HANDOFF_RELPATH).read_bytes())


def _write_canonical(path, value):
    path.write_bytes(context.canonical_json_bytes(value))


def _expect_failure(root):
    with pytest.raises(ValueError):
        context.load_and_verify_continuity_state(root)


def test_v036_rejects_selection_of_wrong_or_already_implemented_component(tmp_path):
    root = _tree(tmp_path); document = json.loads((root / v036.GOVERNANCE_RELPATH).read_bytes())
    document["selected_component"] = next(item for item in document["pipeline_component_inventory"] if item["classification"] == "ALREADY_IMPLEMENTED_AND_REVIEWED")
    _write_canonical(root / v036.GOVERNANCE_RELPATH, document); _expect_failure(root)


def test_v036_rejects_out_of_scope_or_multiple_component_selection(tmp_path):
    root = _tree(tmp_path); document = json.loads((root / v036.GOVERNANCE_RELPATH).read_bytes())
    document["selected_component_count"] = 2
    _write_canonical(root / v036.GOVERNANCE_RELPATH, document); _expect_failure(root)


@pytest.mark.parametrize("field", ["selected_component_implementation_authorized", "selected_component_execution_authorized"])
def test_v036_rejects_authority_expansion(tmp_path, field):
    root = _tree(tmp_path); document = json.loads((root / v036.GOVERNANCE_RELPATH).read_bytes())
    document["transition_gates"][field] = True
    _write_canonical(root / v036.GOVERNANCE_RELPATH, document); _expect_failure(root)


def test_v036_rejects_predecessor_or_selection_tampering(tmp_path):
    root = _tree(tmp_path); receipt = _receipt(root)
    receipt["predecessor"] = copy.deepcopy(receipt["predecessor"]); receipt["predecessor"]["sha256"] = "0" * 64
    _write_canonical(root / v036.HANDOFF_RELPATH, receipt)
    active = json.loads((root / context.ACTIVE_TASK_RELPATH).read_bytes()); active["handoff_receipt_sha256"] = hashlib.sha256((root / v036.HANDOFF_RELPATH).read_bytes()).hexdigest()
    _write_canonical(root / context.ACTIVE_TASK_RELPATH, active); _expect_failure(root)


def test_v036_rejects_implementation_next_action(tmp_path):
    root = _tree(tmp_path); receipt = _receipt(root); receipt["next_actions"] = ["IMPLEMENT_H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION"]
    _write_canonical(root / v036.HANDOFF_RELPATH, receipt)
    active = json.loads((root / context.ACTIVE_TASK_RELPATH).read_bytes()); active["handoff_receipt_sha256"] = hashlib.sha256((root / v036.HANDOFF_RELPATH).read_bytes()).hexdigest()
    _write_canonical(root / context.ACTIVE_TASK_RELPATH, active); _expect_failure(root)
