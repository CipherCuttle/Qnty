"""Adversarial checks for v037's governance-only authorization."""

import copy
import hashlib
import json
import shutil

import pytest

from quantbot.continuity import context
from quantbot.continuity import h001_per_run_coordinate_and_seed_orchestration_governance_v037 as v037


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


def test_v037_rejects_wrong_selected_component_or_count(tmp_path):
    root = _tree(tmp_path); doc = json.loads((root / v037.GOVERNANCE_RELPATH).read_bytes())
    doc["selected_component"]["component_id"] = "SYNTHETIC_DGP_SAMPLE_MATERIALIZATION"
    _write(root / v037.GOVERNANCE_RELPATH, doc); _fail(root)


@pytest.mark.parametrize("field", ["selected_component_implementation_authorized", "selected_component_execution_authorized", "execution_authorized", "execution_implementation_authorized"])
def test_v037_rejects_implementation_or_execution_authority(tmp_path, field):
    root = _tree(tmp_path); doc = json.loads((root / v037.GOVERNANCE_RELPATH).read_bytes())
    doc["transition_gates"][field] = True
    _write(root / v037.GOVERNANCE_RELPATH, doc); _fail(root)


def test_v037_rejects_predecessor_or_next_action_skip(tmp_path):
    root = _tree(tmp_path); receipt = json.loads((root / v037.HANDOFF_RELPATH).read_bytes())
    receipt["predecessor"] = copy.deepcopy(receipt["predecessor"]); receipt["predecessor"]["sha256"] = "0" * 64
    _write(root / v037.HANDOFF_RELPATH, receipt)
    active = json.loads((root / context.ACTIVE_TASK_RELPATH).read_bytes()); active["handoff_receipt_sha256"] = hashlib.sha256((root / v037.HANDOFF_RELPATH).read_bytes()).hexdigest()
    _write(root / context.ACTIVE_TASK_RELPATH, active); _fail(root)


def test_v037_rejects_candidate_design_or_execution_budget(tmp_path):
    root = _tree(tmp_path); doc = json.loads((root / v037.GOVERNANCE_RELPATH).read_bytes())
    doc["component_specification"] = {"seed_formula": "premature"}
    _write(root / v037.GOVERNANCE_RELPATH, doc); _fail(root)
