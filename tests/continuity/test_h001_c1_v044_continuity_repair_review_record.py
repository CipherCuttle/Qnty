"""Regression coverage for recording the v044 continuity-repair review pass."""

import copy
import hashlib
import json
import shutil

import pytest

from quantbot.continuity import context


ROOT = __import__("pathlib").Path(__file__).parents[2]


def _tree(tmp_path):
    root = tmp_path / "repo"
    shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__"))
    return root


def _write_json(path, value):
    path.write_bytes(context.canonical_json_bytes(value))


def _load_json(path):
    return json.loads(path.read_bytes())


def _fail(root):
    with pytest.raises(ValueError):
        context.load_and_verify_continuity_state(root)


def _record(root):
    return _load_json(root / context._V044_CONTINUITY_REPAIR_REVIEW_RECORD_RELPATH)


def _receipt(root):
    return _load_json(root / context._V044_CONTINUITY_REPAIR_REVIEW_HANDOFF_RELPATH)


def _rewrite_record(root, record):
    path = root / context._V044_CONTINUITY_REPAIR_REVIEW_RECORD_RELPATH
    _write_json(path, record)


def _rewrite_receipt_and_active(root, receipt):
    receipt_path = root / context._V044_CONTINUITY_REPAIR_REVIEW_HANDOFF_RELPATH
    _write_json(receipt_path, receipt)
    active_path = root / context.ACTIVE_TASK_RELPATH
    active = _load_json(active_path)
    active["handoff_receipt_sha256"] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    _write_json(active_path, active)


def test_v045_review_pass_record_binds_candidate_and_evidence(tmp_path):
    root = _tree(tmp_path)

    state = context.load_and_verify_continuity_state(root)
    record = _record(root)
    receipt = _receipt(root)

    assert state["active_task"]["phase"] == context._V044_CONTINUITY_REPAIR_REVIEW_PASSED_PHASE
    assert state["handoff_receipt"]["next_actions"] == ["H001_OPERATOR_EXPOSURE_DISCLOSURE_V1"]
    assert record["candidate_binding"] == {
        "candidate_commit": "7d2644bff33865c0b2a6ed6e1a0c27686c0f47ec",
        "candidate_parent": "cd82a7dc0ba29a02845a764c249ae6154dc4475b",
        "candidate_tree": "3032fecba8ba1a58835728b2543e8f7b683a56cb",
        "changed_files": [
            "quantbot/continuity/context.py",
            "tests/continuity/test_cross_agent_continuity.py",
            "tests/continuity/test_h001_c1_v044_review_record_phase_repair.py",
        ],
    }
    assert record["review_verdict"] == "PASS_ACTIVE_TASK_PHASE_SCHEMA_REPAIR_SAFE"
    assert record["test_evidence"]["full_continuity_collection"] == {"collected": 903, "return_code": 0}
    assert record["test_evidence"]["full_continuity_suite"] == {"failed": 0, "passed": 903, "return_code": 0}
    assert record["protected_hashes"] == context._V044_CONTINUITY_REPAIR_PROTECTED_HASHES
    assert receipt["h001_c1_v044_continuity_repair_review_binding"]["review_completed"] is True
    assert receipt["h001_c1_v044_continuity_repair_review_binding"]["review_passed"] is True


def test_v045_authority_c2_and_operator_state_remain_non_effective(tmp_path):
    root = _tree(tmp_path)
    context.load_and_verify_continuity_state(root)
    record = _record(root)
    authority = record["authorization_state"]

    assert authority["candidate_review_completed"] is True
    assert authority["candidate_review_passed"] is True
    for key in (
        "candidate_effective",
        "scientific_authorized",
        "activation_authorized",
        "implementation_authorized",
        "real_data_access_authorized",
        "execution_authorized",
        "holdout_authorized",
        "paper_trade_authorized",
        "live_authorized",
        "dispatcher_released",
        "trust_root_registered",
        "C2_resolved",
    ):
        assert authority[key] is False
    assert authority["execution_budget"] == 0
    assert authority["execution_count"] == 0
    assert record["operator_exposure_disclosure_recorded"] is False
    assert record["operator_decision_state"] == "PENDING"


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("candidate_binding.candidate_commit", "0" * 40),
        ("candidate_binding.candidate_tree", "0" * 40),
        ("candidate_binding.candidate_parent", "0" * 40),
        ("candidate_binding.changed_files", ["quantbot/continuity/context.py"]),
        ("review_verdict", "PASS"),
        ("protected_hashes.v044_amendment", "0" * 64),
        ("authorization_state.candidate_effective", True),
        ("authorization_state.scientific_authorized", True),
        ("authorization_state.activation_authorized", True),
        ("authorization_state.implementation_authorized", True),
        ("authorization_state.real_data_access_authorized", True),
        ("authorization_state.execution_authorized", True),
        ("authorization_state.holdout_authorized", True),
        ("authorization_state.paper_trade_authorized", True),
        ("authorization_state.live_authorized", True),
        ("authorization_state.dispatcher_released", True),
        ("authorization_state.trust_root_registered", True),
        ("authorization_state.C2_resolved", True),
        ("authorization_state.execution_budget", 1),
        ("authorization_state.execution_count", 1),
        ("operator_exposure_disclosure_recorded", True),
        ("operator_decision_state", "APPROVED"),
    ],
)
def test_v045_review_record_mutations_fail_closed(tmp_path, path, value):
    root = _tree(tmp_path)
    record = _record(root)
    mutated = copy.deepcopy(record)
    target = mutated
    parts = path.split(".")
    for part in parts[:-1]:
        target = target[part]
    target[parts[-1]] = value

    _rewrite_record(root, mutated)

    _fail(root)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("review_record_path", "docs/assurance/reviews/wrong.json"),
        ("review_record_sha256", "0" * 64),
    ],
)
def test_v045_active_review_record_binding_fails_closed(tmp_path, field, value):
    root = _tree(tmp_path)
    active_path = root / context.ACTIVE_TASK_RELPATH
    active = _load_json(active_path)
    active[field] = value
    _write_json(active_path, active)

    _fail(root)


def test_v045_receipt_wrong_next_action_fails_closed(tmp_path):
    root = _tree(tmp_path)
    receipt = _receipt(root)
    receipt["next_actions"] = ["ACTIVATE_H001"]
    _rewrite_receipt_and_active(root, receipt)

    _fail(root)


def test_v045_receipt_review_hash_substitution_fails_closed(tmp_path):
    root = _tree(tmp_path)
    receipt = _receipt(root)
    receipt["h001_c1_v044_continuity_repair_review_binding"]["review_record_sha256"] = "0" * 64
    _rewrite_receipt_and_active(root, receipt)

    _fail(root)


def test_historical_v044_review_record_phase_remains_valid(tmp_path):
    root = _tree(tmp_path)
    active_path = root / context.ACTIVE_TASK_RELPATH
    active = _load_json(active_path)
    active["phase"] = context._V044_REVIEW_RECORDED_PHASE
    active["handoff_receipt_path"] = context._v044.HANDOFF_RELPATH
    active["handoff_receipt_sha256"] = "e7cbfa8659319e32a2ba233f22d9035ff0d9d85cef99d81015e4182988af31f7"
    active["review_record_path"] = context._V044_REVIEW_RECORD_RELPATH
    active["review_record_sha256"] = context._V044_REVIEW_RECORD_SHA256
    _write_json(active_path, active)

    state = context.load_and_verify_continuity_state(root)

    assert state["active_task"]["phase"] == context._V044_REVIEW_RECORDED_PHASE
