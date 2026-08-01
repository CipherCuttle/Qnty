"""Regression coverage for the v044 review-record continuity phase."""

import hashlib
import json
import shutil
import tarfile

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
HISTORICAL_FIXTURE_DIR = ROOT / "tests/fixtures/historical_continuity_v034"
HISTORICAL_BASE_FIXTURE = (
    "base_0bd455ed.tar.gz",
    "3cee1aac26846801272480200abb66a54b62099a1c55b4c30ded23263d7837c9",
)
HISTORICAL_V024_FIXTURE = (
    "v024_90460b3e13db.tar.gz",
    "74fa22502bed4677023c2d2812408b7b0c52766f33134ca31c756b780b854933",
)


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


def _extract_historical_fixture(destination, fixture):
    filename, expected_sha256 = fixture
    archive = HISTORICAL_FIXTURE_DIR / filename
    assert _sha256(archive) == expected_sha256
    with tarfile.open(archive) as source:
        source.extractall(destination, filter="data")


def _historical_v024_tree(tmp_path):
    root = tmp_path / "historical"
    _extract_historical_fixture(root, HISTORICAL_BASE_FIXTURE)
    _extract_historical_fixture(root, HISTORICAL_V024_FIXTURE)
    receipt_path = root / context._H001_CALIBRATION_IMPLEMENTATION_BLOCKED_HANDOFF_RELPATH
    receipt = _load_json(receipt_path)
    receipt["current_transition_files"] = [
        {"path": path, "sha256": _sha256(root / path)}
        for path in context._H001_CALIBRATION_IMPLEMENTATION_BLOCKED_CURRENT_TRANSITION_FILES
    ]
    _write_json(receipt_path, receipt)
    active = {
        "control_kind": "qnty_active_task_pointer",
        "handoff_receipt_path": context._H001_CALIBRATION_IMPLEMENTATION_BLOCKED_HANDOFF_RELPATH,
        "handoff_receipt_sha256": _sha256(receipt_path),
        "phase": context._H001_CALIBRATION_IMPLEMENTATION_BLOCKED_PHASE,
        "protocol_id": context.PROTOCOL_ID,
        "schema_version": "0.1.0",
        "task_id": context.TASK_ID,
    }
    _write_json(root / context.ACTIVE_TASK_RELPATH, active)
    return root


def _verify(root):
    return context.load_and_verify_continuity_state(root)


def _fail(root):
    with pytest.raises(ValueError):
        context.load_and_verify_continuity_state(root)


def _point_to_v044_review_record_phase(root):
    active_path = root / context.ACTIVE_TASK_RELPATH
    active = _load_json(active_path)
    active["phase"] = context._V044_REVIEW_RECORDED_PHASE
    active["handoff_receipt_path"] = v044.HANDOFF_RELPATH
    active["handoff_receipt_sha256"] = "e7cbfa8659319e32a2ba233f22d9035ff0d9d85cef99d81015e4182988af31f7"
    active["review_record_path"] = REVIEW_RECORD_PATH
    active["review_record_sha256"] = REVIEW_RECORD_SHA256
    active.pop("operator_disclosure_record_path", None)
    active.pop("operator_disclosure_record_sha256", None)
    active.pop("operator_exposure_disclosure_review_record_path", None)
    active.pop("operator_exposure_disclosure_review_record_sha256", None)
    active.pop("operator_governance_decision_record_path", None)
    active.pop("operator_governance_decision_record_sha256", None)
    active.pop("operator_governance_decision_review_record_path", None)
    active.pop("operator_governance_decision_review_record_sha256", None)
    _write_json(active_path, active)


def test_historical_active_task_schema_without_review_fields_still_verifies(tmp_path):
    root = _historical_v024_tree(tmp_path)

    state = _verify(root)

    assert state["active_task"]["phase"] == context._H001_CALIBRATION_IMPLEMENTATION_BLOCKED_PHASE
    assert set(state["active_task"]) == context._BASE_ACTIVE_KEYS
    assert "review_record_path" not in state["active_task"]
    assert "review_record_sha256" not in state["active_task"]


def test_historical_active_task_rejects_review_fields_as_unauthorized_superset(tmp_path):
    root = _historical_v024_tree(tmp_path)
    active_path = root / context.ACTIVE_TASK_RELPATH
    active = _load_json(active_path)
    active["review_record_path"] = REVIEW_RECORD_PATH
    active["review_record_sha256"] = REVIEW_RECORD_SHA256
    _write_json(active_path, active)

    _fail(root)


def test_historical_active_task_unknown_extra_key_fails_closed(tmp_path):
    root = _historical_v024_tree(tmp_path)
    active_path = root / context.ACTIVE_TASK_RELPATH
    active = _load_json(active_path)
    active["unknown_extra_key"] = "forbidden"
    _write_json(active_path, active)

    _fail(root)


def test_review_record_phase_verifies_v044_handoff_without_mutating_review_record(tmp_path):
    root = _tree(tmp_path)
    _point_to_v044_review_record_phase(root)

    state = _verify(root)

    assert state["handoff_receipt"]["receipt_index"] == 44
    assert _sha256(root / REVIEW_RECORD_PATH) == REVIEW_RECORD_SHA256
    assert _sha256(root / FOCUSED_REVIEW_TEST_PATH) == FOCUSED_REVIEW_TEST_SHA256


def test_review_record_phase_reuses_exact_v044_handoff_schema(tmp_path):
    root = _tree(tmp_path)
    _point_to_v044_review_record_phase(root)
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


@pytest.mark.parametrize("field", ["review_record_path", "review_record_sha256"])
def test_review_record_phase_requires_each_review_field(tmp_path, field):
    root = _tree(tmp_path)
    active_path = root / context.ACTIVE_TASK_RELPATH
    active = _load_json(active_path)
    active.pop(field)
    _write_json(active_path, active)

    _fail(root)


def test_review_record_phase_rejects_historical_active_task_key_set(tmp_path):
    root = _tree(tmp_path)
    active_path = root / context.ACTIVE_TASK_RELPATH
    active = _load_json(active_path)
    active.pop("review_record_path")
    active.pop("review_record_sha256")
    _write_json(active_path, active)

    _fail(root)


def test_review_record_phase_wrong_review_record_path_fails_closed(tmp_path):
    root = _tree(tmp_path)
    active_path = root / context.ACTIVE_TASK_RELPATH
    active = _load_json(active_path)
    active["review_record_path"] = "docs/assurance/reviews/wrong_review_record.json"
    _write_json(active_path, active)

    _fail(root)


def test_review_record_phase_wrong_review_record_hash_fails_closed(tmp_path):
    root = _tree(tmp_path)
    active_path = root / context.ACTIVE_TASK_RELPATH
    active = _load_json(active_path)
    active["review_record_sha256"] = "0" * 64
    _write_json(active_path, active)

    _fail(root)


def test_phase_spoofing_cannot_select_review_schema_for_historical_pointer(tmp_path):
    root = _historical_v024_tree(tmp_path)
    active_path = root / context.ACTIVE_TASK_RELPATH
    active = _load_json(active_path)
    active["phase"] = context._V044_REVIEW_RECORDED_PHASE
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
    _point_to_v044_review_record_phase(root)
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
    assert authority["execution_count"] == 0
    assert authority["holdout_authorized"] is False
    assert authority["paper_trade_authorized"] is False
    assert authority["live_authorized"] is False
    assert authority["dispatcher_released"] is False
    assert authority["trust_root_registered"] is False
    assert authority["C2_resolved"] is False
    assert state["active_task"]["review_record_sha256"] == REVIEW_RECORD_SHA256
