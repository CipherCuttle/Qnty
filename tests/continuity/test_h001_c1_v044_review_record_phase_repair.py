"""Regression coverage for the v044 review-record continuity phase."""

import hashlib
import json
import shutil

import pytest

from quantbot.continuity import context
from quantbot.continuity import h001_c1_directionality_atomic_repair_candidate_v044 as v044


ROOT = __import__("pathlib").Path(__file__).parents[2]
REVIEW_RECORD_PATH = (
    "docs/assurance/reviews/"
    "candidate1_h001_c1_directionality_atomic_repair_candidate_review_v001.json"
)
REVIEW_RECORD_SHA256 = "6773f7b69ae0c5c9093ed49eb3a7667ebc141df2f11ee0086b4b26d93ea452c6"
FOCUSED_REVIEW_TEST_PATH = (
    "tests/assurance/"
    "test_h001_c1_directionality_atomic_repair_candidate_review_record.py"
)
FOCUSED_REVIEW_TEST_SHA256 = "df26801684def7723787e2ac59866cdb90607eedf53303a664b37b586d9315cb"


def _tree(tmp_path):
    root = tmp_path / "repo"
    shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__"))
    return root


def _write_json(path, value):
    path.write_bytes(context.canonical_json_bytes(value))


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path):
    return json.loads(path.read_bytes())


def _verify(root):
    return context.load_and_verify_continuity_state(root)


def _fail(root):
    with pytest.raises(ValueError):
        context.load_and_verify_continuity_state(root)


def test_review_record_phase_verifies_v044_handoff_without_mutating_review_record(tmp_path):
    root = _tree(tmp_path)

    state = _verify(root)

    assert state["handoff_receipt"]["receipt_index"] == 44
    assert _sha256(root / REVIEW_RECORD_PATH) == REVIEW_RECORD_SHA256
    assert _sha256(root / FOCUSED_REVIEW_TEST_PATH) == FOCUSED_REVIEW_TEST_SHA256


def test_review_record_phase_reuses_exact_v044_handoff_schema(tmp_path):
    root = _tree(tmp_path)
    receipt_path = root / v044.HANDOFF_RELPATH
    receipt = _load_json(receipt_path)
    receipt["unauthorized_extra_key"] = True
    _write_json(receipt_path, receipt)
    active_path = root / context.ACTIVE_TASK_RELPATH
    active = _load_json(active_path)
    active["handoff_receipt_sha256"] = _sha256(receipt_path)
    _write_json(active_path, active)

    _fail(root)


def test_review_record_phase_still_rejects_v044_semantic_drift(tmp_path):
    root = _tree(tmp_path)
    amendment_path = root / v044.AMENDMENT_RELPATH
    amendment = _load_json(amendment_path)
    amendment["proposed_c1"]["family_size"] = 8
    _write_json(amendment_path, amendment)

    _fail(root)


def test_review_record_phase_active_task_unknown_key_fails_closed(tmp_path):
    root = _tree(tmp_path)
    active_path = root / context.ACTIVE_TASK_RELPATH
    active = _load_json(active_path)
    active["operator_disclosure_completed"] = True
    _write_json(active_path, active)

    _fail(root)


def test_review_record_phase_rejects_review_record_authority_escalation(tmp_path):
    root = _tree(tmp_path)
    review_path = root / REVIEW_RECORD_PATH
    review = _load_json(review_path)
    review["authorization_state"]["execution_budget"] = 1
    _write_json(review_path, review)

    _fail(root)


def test_review_record_phase_preserves_c1_and_c2_authority_bindings(tmp_path):
    root = _tree(tmp_path)
    state = _verify(root)
    review = _load_json(root / REVIEW_RECORD_PATH)
    authority = review["authorization_state"]

    assert review["reviewed_candidate_sha256"] == _sha256(root / v044.AMENDMENT_RELPATH)
    assert review["reviewed_validator_sha256"] == _sha256(
        root / "quantbot/continuity/h001_c1_directionality_atomic_repair_candidate_v044.py"
    )
    assert review["verified_scientific_findings"]["tail"] == "upper tail only"
    assert review["verified_scientific_findings"]["family_size"] == 9
    assert authority["candidate_review_completed"] is True
    assert authority["candidate_review_passed"] is True
    assert authority["candidate_effective"] is False
    assert authority["scientific_authorized"] is False
    assert authority["activation_authorized"] is False
    assert authority["implementation_authorized"] is False
    assert authority["real_data_access_authorized"] is False
    assert authority["execution_authorized"] is False
    assert authority["execution_budget"] == 0
    assert authority["C2_resolved"] is False
    assert state["active_task"]["review_record_sha256"] == REVIEW_RECORD_SHA256
