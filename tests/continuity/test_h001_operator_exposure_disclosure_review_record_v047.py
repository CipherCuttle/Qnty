"""Regression coverage for recording the H001 operator disclosure hostile-review pass."""

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
    return _load_json(root / context._H001_OPERATOR_EXPOSURE_DISCLOSURE_REVIEW_RECORD_RELPATH)


def _receipt(root):
    return _load_json(root / context._H001_OPERATOR_EXPOSURE_DISCLOSURE_REVIEW_HANDOFF_RELPATH)


def _disclosure(root):
    return _load_json(root / context._H001_OPERATOR_EXPOSURE_DISCLOSURE_RELPATH)


def _rewrite_record(root, record):
    _write_json(root / context._H001_OPERATOR_EXPOSURE_DISCLOSURE_REVIEW_RECORD_RELPATH, record)


def _rewrite_receipt_and_active(root, receipt):
    receipt_path = root / context._H001_OPERATOR_EXPOSURE_DISCLOSURE_REVIEW_HANDOFF_RELPATH
    _write_json(receipt_path, receipt)
    active_path = root / context.ACTIVE_TASK_RELPATH
    active = _load_json(active_path)
    active["handoff_receipt_sha256"] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    _write_json(active_path, active)


def _set_path(value, path, replacement):
    target = value
    parts = path.split(".")
    for part in parts[:-1]:
        target = target[int(part)] if part.isdigit() else target[part]
    last = parts[-1]
    if last.isdigit():
        target[int(last)] = replacement
    else:
        target[last] = replacement


def test_v047_review_pass_record_binds_candidate_disclosure_handoff_and_evidence(tmp_path):
    root = _tree(tmp_path)

    state = context.load_and_verify_continuity_state(root)
    record = _record(root)
    receipt = _receipt(root)
    disclosure = _disclosure(root)

    assert state["active_task"]["phase"] == context._H001_OPERATOR_EXPOSURE_DISCLOSURE_REVIEW_PASSED_PHASE
    assert state["handoff_receipt"]["next_actions"] == ["H001_OPERATOR_GOVERNANCE_DECISION_V1"]
    assert record["review_verdict"] == "PASS_OPERATOR_EXPOSURE_DISCLOSURE_SAFE_FOR_DECISION"
    assert record["candidate_binding"] == {
        "changed_files": context._H001_OPERATOR_EXPOSURE_DISCLOSURE_REVIEW_CHANGED_FILES,
        "reviewed_commit": "24ecd2b182cf1ae5d6ee57221f47698b72391597",
        "reviewed_parent": "22aa96c43a0689be6e505de6f1c8a1c91e474ab3",
        "reviewed_tree": "ce9b8a84c7e6d6b4fbf2b160d7f72df7d19e420c",
    }
    assert record["disclosure_binding"]["reviewed_disclosure_path"] == context._H001_OPERATOR_EXPOSURE_DISCLOSURE_RELPATH
    assert record["disclosure_binding"]["reviewed_disclosure_sha256"] == context._H001_OPERATOR_EXPOSURE_DISCLOSURE_SHA256
    assert record["disclosure_binding"]["reviewed_handoff_path"] == context._H001_OPERATOR_EXPOSURE_DISCLOSURE_HANDOFF_RELPATH
    assert record["disclosure_binding"]["reviewed_handoff_sha256"] == "13ed0644ca3f43fc9e1223627f8cb67518602d94c5bb0e9cbaa57125db9a340f"
    assert record["operator_exposure_disclosure_review_completed"] is True
    assert record["operator_exposure_disclosure_review_passed"] is True
    assert receipt["h001_operator_exposure_disclosure_review_binding"]["review_completed"] is True
    assert receipt["h001_operator_exposure_disclosure_review_binding"]["review_passed"] is True
    assert receipt["h001_operator_exposure_disclosure_review_binding"]["review_record_sha256"] == context._H001_OPERATOR_EXPOSURE_DISCLOSURE_REVIEW_RECORD_SHA256
    assert record["test_evidence"]["focused_suites"] == {"failed": 0, "passed": 100, "return_code": 0}
    assert record["test_evidence"]["full_continuity_collection"] == {"collected": 962, "return_code": 0}
    assert record["test_evidence"]["full_continuity_suite"] == {"failed": 0, "passed": 962, "skipped": 0, "return_code": 0}
    assert [item["answer"] for item in disclosure["answers"]] == ["UNCERTAIN"] * 7
    assert [item["confidence"] for item in disclosure["answers"]] == ["LOW", "LOW", "LOW", "LOW", "LOW", "MEDIUM", "MEDIUM"]
    assert disclosure["conclusions"] == context._H001_OPERATOR_EXPOSURE_DISCLOSURE_CONCLUSIONS


def test_v047_authority_c2_and_operator_decision_remain_pending_and_non_effective(tmp_path):
    root = _tree(tmp_path)
    context.load_and_verify_continuity_state(root)
    record = _record(root)
    authority = record["authority_state"]

    assert record["operator_exposure_disclosure_recorded"] is True
    assert record["operator_exposure_disclosure_review_completed"] is True
    assert record["operator_exposure_disclosure_review_passed"] is True
    assert record["operator_decision_state"] == "PENDING"
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


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("candidate_binding.reviewed_commit", "0" * 40),
        ("candidate_binding.reviewed_tree", "0" * 40),
        ("candidate_binding.reviewed_parent", "0" * 40),
        ("disclosure_binding.reviewed_disclosure_path", "docs/assurance/operator_disclosures/wrong.json"),
        ("disclosure_binding.reviewed_disclosure_sha256", "0" * 64),
        ("disclosure_binding.reviewed_handoff_path", "docs/control/tasks/RECOVER_OR_RETIRE_CANDIDATE1_V0_FROZEN_INPUT/handoff_v045.json"),
        ("disclosure_binding.reviewed_handoff_sha256", "0" * 64),
        ("review_verdict", "FAIL"),
        ("operator_exposure_disclosure_review_completed", False),
        ("operator_exposure_disclosure_review_passed", False),
        ("operator_decision_state", "APPROVE_NEXT_GOVERNANCE_STEP_WITH_EXPOSURE_LIMITATIONS"),
        ("authority_state.candidate_effective", True),
        ("authority_state.scientific_authorized", True),
        ("authority_state.activation_authorized", True),
        ("authority_state.implementation_authorized", True),
        ("authority_state.real_data_access_authorized", True),
        ("authority_state.execution_authorized", True),
        ("authority_state.execution_budget", 1),
        ("authority_state.execution_count", 1),
        ("authority_state.C2_resolved", True),
        ("authority_state.holdout_authorized", True),
        ("authority_state.paper_trade_authorized", True),
        ("authority_state.live_authorized", True),
        ("authority_state.dispatcher_released", True),
        ("authority_state.trust_root_registered", True),
        ("hostile_mutation_evidence.0.result", "PASS"),
        ("protected_hashes.v046_disclosure", "0" * 64),
    ],
)
def test_v047_review_record_mutations_fail_closed(tmp_path, path, value):
    root = _tree(tmp_path)
    record = _record(root)
    mutated = copy.deepcopy(record)
    _set_path(mutated, path, value)

    _rewrite_record(root, mutated)

    _fail(root)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("operator_exposure_disclosure_review_record_path", "docs/assurance/reviews/wrong.json"),
        ("operator_exposure_disclosure_review_record_sha256", "0" * 64),
    ],
)
def test_v047_active_review_record_binding_fails_closed(tmp_path, field, value):
    root = _tree(tmp_path)
    active_path = root / context.ACTIVE_TASK_RELPATH
    active = _load_json(active_path)
    active[field] = value
    _write_json(active_path, active)

    _fail(root)


def test_v047_receipt_wrong_next_action_or_selected_decision_fails_closed(tmp_path):
    root = _tree(tmp_path)
    receipt = _receipt(root)
    receipt["next_actions"] = ["APPROVE_NEXT_GOVERNANCE_STEP_WITH_EXPOSURE_LIMITATIONS"]
    _rewrite_receipt_and_active(root, receipt)

    _fail(root)


def test_v047_receipt_wrong_review_hash_fails_closed(tmp_path):
    root = _tree(tmp_path)
    receipt = _receipt(root)
    receipt["h001_operator_exposure_disclosure_review_binding"]["review_record_sha256"] = "0" * 64
    _rewrite_receipt_and_active(root, receipt)

    _fail(root)


def test_v047_review_record_unknown_extra_key_fails_closed(tmp_path):
    root = _tree(tmp_path)
    record = _record(root)
    record["unknown_extra_key"] = True
    _rewrite_record(root, record)

    _fail(root)


def test_v047_historical_v044_and_v046_phases_remain_valid(tmp_path):
    root = _tree(tmp_path)
    active_path = root / context.ACTIVE_TASK_RELPATH
    active = _load_json(active_path)
    active["phase"] = context._V044_REVIEW_RECORDED_PHASE
    active["handoff_receipt_path"] = context._v044.HANDOFF_RELPATH
    active["handoff_receipt_sha256"] = "e7cbfa8659319e32a2ba233f22d9035ff0d9d85cef99d81015e4182988af31f7"
    active["review_record_path"] = context._V044_REVIEW_RECORD_RELPATH
    active["review_record_sha256"] = context._V044_REVIEW_RECORD_SHA256
    active.pop("operator_disclosure_record_path")
    active.pop("operator_disclosure_record_sha256")
    active.pop("operator_exposure_disclosure_review_record_path")
    active.pop("operator_exposure_disclosure_review_record_sha256")
    _write_json(active_path, active)

    state = context.load_and_verify_continuity_state(root)

    assert state["active_task"]["phase"] == context._V044_REVIEW_RECORDED_PHASE

    root = _tree(tmp_path / "v046")
    active_path = root / context.ACTIVE_TASK_RELPATH
    active = _load_json(active_path)
    active["phase"] = context._H001_OPERATOR_EXPOSURE_DISCLOSURE_RECORDED_PHASE
    active["handoff_receipt_path"] = context._H001_OPERATOR_EXPOSURE_DISCLOSURE_HANDOFF_RELPATH
    active.pop("operator_exposure_disclosure_review_record_path")
    active.pop("operator_exposure_disclosure_review_record_sha256")
    receipt_path = root / context._H001_OPERATOR_EXPOSURE_DISCLOSURE_HANDOFF_RELPATH
    receipt = _load_json(receipt_path)
    receipt["current_transition_files"] = [
        {"path": path, "sha256": hashlib.sha256((root / path).read_bytes()).hexdigest()}
        for path in context._H001_OPERATOR_EXPOSURE_DISCLOSURE_CURRENT_FILES
    ]
    _write_json(receipt_path, receipt)
    active["handoff_receipt_sha256"] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    _write_json(active_path, active)

    state = context.load_and_verify_continuity_state(root)

    assert state["active_task"]["phase"] == context._H001_OPERATOR_EXPOSURE_DISCLOSURE_RECORDED_PHASE


def test_v047_previously_protected_hashes_remain_unchanged(tmp_path):
    root = _tree(tmp_path)
    context.load_and_verify_continuity_state(root)
    expected = {
        context._H001_OPERATOR_EXPOSURE_DISCLOSURE_RELPATH: "edcd90cf43e860e6db998c6a45cd352b70071f3a795a53e04442b6d1a9b0932e",
        context._H001_OPERATOR_EXPOSURE_DISCLOSURE_HANDOFF_RELPATH: "13ed0644ca3f43fc9e1223627f8cb67518602d94c5bb0e9cbaa57125db9a340f",
        context._V044_CONTINUITY_REPAIR_REVIEW_RECORD_RELPATH: "b2fdb537fd60ecbfc87966fc369439392c8ad303b61b89ea10fa5ba0d5183042",
        context._V044_CONTINUITY_REPAIR_REVIEW_HANDOFF_RELPATH: "64e73fa56ed831dcf7a2c1a450dafa2f66258790261f47e50793ac4a2a968a3c",
        context._V044_REVIEW_RECORD_RELPATH: "6773f7b69ae0c5c9093ed49eb3a7667ebc141df2f11ee0086b4b26d93ea452c6",
        "tests/assurance/test_h001_c1_directionality_atomic_repair_candidate_review_record.py": "df26801684def7723787e2ac59866cdb90607eedf53303a664b37b586d9315cb",
        context._v044.AMENDMENT_RELPATH: "2bcfaa1f10cfebb6ab7ead9b29bf4a5b4c8f38187ce37af21b32dad99064f98b",
        "quantbot/continuity/h001_c1_directionality_atomic_repair_candidate_v044.py": "3ce96c305bc948a31f2e73c04933e7151cff162a44ccd9b7bb8c5519d7a112d1",
        "tests/continuity/test_h001_c1_directionality_atomic_repair_candidate_v044.py": "bb3e13f5000ac8fe449a78d02ba6f2b236b776ac49a031e14478e53a9719f415",
    }

    for path, digest in expected.items():
        assert hashlib.sha256((root / path).read_bytes()).hexdigest() == digest
