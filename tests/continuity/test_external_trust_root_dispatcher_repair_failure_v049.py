import hashlib
import json
import shutil

import pytest

from quantbot.continuity import context
from quantbot.continuity import external_trust_root_dispatcher_repair_failure_v049 as v049

ROOT = __import__("pathlib").Path(__file__).parents[2]


def _tree(tmp_path):
    root = tmp_path / "repo"
    shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__"))
    return root


def _write(root, receipt):
    path = root / v049.HANDOFF_RELPATH
    path.write_bytes(context.canonical_json_bytes(receipt))
    active = json.loads((root / context.ACTIVE_TASK_RELPATH).read_bytes())
    active["handoff_receipt_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (root / context.ACTIVE_TASK_RELPATH).write_bytes(context.canonical_json_bytes(active))


def _receipt(root):
    return json.loads((root / v049.HANDOFF_RELPATH).read_bytes())


def _reject(root):
    with pytest.raises(ValueError):
        context.load_and_verify_continuity_state(root)


def test_v049_baseline_verifies(tmp_path):
    context.load_and_verify_continuity_state(_tree(tmp_path))


@pytest.mark.parametrize(("path", "value"), [
    ("v048_failed_review_binding.commit", "0" * 40),
    ("v048_failed_review_binding.tree", "0" * 40),
    ("v048_failed_review_binding.review_outcome", "PASS"),
    ("v048_failed_review_binding.finding.class", "SAFETY_FAILURE"),
    ("v048_failed_review_binding.finding.result", "legitimate R1 is reachable"),
    ("v048_failed_review_binding.released", True),
    ("phase", "external_trust_root_dispatcher_v1_authority_root_repair_candidate_review_required"),
    ("next_actions", ["RELEASE_EXTERNAL_TRUST_ROOT_DISPATCHER"]),
    ("authority_state.dispatcher_released", True),
    ("authority_state.trust_root_registered", True),
    ("authority_state.c1_semantic_trust_root_promoted", True),
    ("authority_state.h001_execution_budget", 1),
    ("authority_state.h001_execution_count", 1),
    ("authority_state.h001_activated", True),
    ("authority_state.real_data_access", True),
    ("authority_state.holdout_access", True),
    ("authority_state.c2_resolved", True),
])
def test_v049_rejects_liveness_finding_or_authority_drift(tmp_path, path, value):
    root = _tree(tmp_path)
    receipt = _receipt(root)
    target = receipt
    parts = path.split(".")
    for part in parts[:-1]:
        target = target[part]
    target[parts[-1]] = value
    _write(root, receipt)
    _reject(root)
