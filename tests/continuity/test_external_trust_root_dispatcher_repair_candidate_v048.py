import hashlib
import json
import shutil

import pytest

from quantbot.continuity import context
from quantbot.continuity import external_trust_root_dispatcher_repair_candidate_v048 as v048

ROOT = __import__("pathlib").Path(__file__).parents[2]


def _tree(tmp_path):
    root = tmp_path / "repo"
    shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__"))
    return root


def _write(root, receipt):
    path = root / v048.HANDOFF_RELPATH
    path.write_bytes(context.canonical_json_bytes(receipt))
    active = json.loads((root / context.ACTIVE_TASK_RELPATH).read_bytes())
    active["handoff_receipt_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (root / context.ACTIVE_TASK_RELPATH).write_bytes(context.canonical_json_bytes(active))


def test_v048_baseline_verifies(tmp_path):
    context.load_and_verify_continuity_state(_tree(tmp_path))


@pytest.mark.parametrize(("path", "value"), [
    ("source_head_commit", "0" * 40),
    ("v046_failed_review_binding.finding.hostile_result.authoritative", False),
    ("phase", "wrong"),
    ("next_actions", ["RELEASE_EXTERNAL_TRUST_ROOT_DISPATCHER"]),
    ("authority_state.dispatcher_released", True),
    ("authority_state.trust_root_registered", True),
])
def test_v048_rejects_lineage_or_authority_drift(tmp_path, path, value):
    root = _tree(tmp_path)
    receipt = json.loads((root / v048.HANDOFF_RELPATH).read_bytes())
    target = receipt
    for part in path.split(".")[:-1]:
        target = target[part]
    target[path.split(".")[-1]] = value
    _write(root, receipt)
    with pytest.raises(ValueError):
        context.load_and_verify_continuity_state(root)
