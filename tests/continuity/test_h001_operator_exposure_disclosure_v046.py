"""Regression coverage for the H001 operator exposure disclosure transition."""

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


def _disclosure(root):
    return _load_json(root / context._H001_OPERATOR_EXPOSURE_DISCLOSURE_RELPATH)


def _receipt(root):
    return _load_json(root / context._H001_OPERATOR_EXPOSURE_DISCLOSURE_HANDOFF_RELPATH)


def _rewrite_disclosure(root, disclosure):
    _write_json(root / context._H001_OPERATOR_EXPOSURE_DISCLOSURE_RELPATH, disclosure)


def _rewrite_receipt_and_active(root, receipt):
    receipt_path = root / context._H001_OPERATOR_EXPOSURE_DISCLOSURE_HANDOFF_RELPATH
    _write_json(receipt_path, receipt)
    active_path = root / context.ACTIVE_TASK_RELPATH
    active = _load_json(active_path)
    active["handoff_receipt_sha256"] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    _write_json(active_path, active)


def test_v046_disclosure_records_all_answers_as_uncertain(tmp_path):
    root = _tree(tmp_path)

    state = context.load_and_verify_continuity_state(root)
    disclosure = _disclosure(root)
    answers = disclosure["answers"]

    assert state["active_task"]["phase"] == context._H001_OPERATOR_EXPOSURE_DISCLOSURE_REVIEW_PASSED_PHASE
    assert state["handoff_receipt"]["next_actions"] == ["H001_OPERATOR_GOVERNANCE_DECISION_V1"]
    assert disclosure["allowed_answer_states"] == ["KNOWN_NO", "KNOWN_YES", "UNCERTAIN"]
    assert [item["answer"] for item in answers] == ["UNCERTAIN"] * 7
    assert [item["confidence"] for item in answers] == ["LOW", "LOW", "LOW", "LOW", "LOW", "MEDIUM", "MEDIUM"]
    assert all(item["answer"] is not False for item in answers)
    assert all(item["answer"] not in {"false", "no", "clean", "blind", "unexposed", "passed"} for item in answers)


def test_v046_disclosure_semantics_and_conclusions_are_conservative(tmp_path):
    root = _tree(tmp_path)
    context.load_and_verify_continuity_state(root)
    disclosure = _disclosure(root)

    assert "STRICT_OUTCOME_BLINDNESS_NOT_ESTABLISHED" in disclosure["conclusions"]
    assert "OUTCOME_CONTAMINATION_NOT_PROVEN" in disclosure["conclusions"]
    assert "OUTCOME_NON_EXPOSURE_NOT_PROVEN" in disclosure["conclusions"]
    assert "NO_KNOWN_DELIBERATE_OPERATOR_OUTCOME_TUNING" in disclosure["conclusions"]
    assert "UNKNOWN_AGENT_OR_ARTIFACT_EXPOSURE_REMAINS" in disclosure["conclusions"]
    assert "STRICT_OUTCOME_BLINDNESS_ESTABLISHED" not in disclosure["conclusions"]
    assert "OUTCOME_CONTAMINATION_PROVEN" not in disclosure["conclusions"]
    assert "does not prove contamination occurred" in disclosure["semantics"]["UNCERTAIN"]


def test_v046_disclosure_authority_and_decision_state(tmp_path):
    root = _tree(tmp_path)
    context.load_and_verify_continuity_state(root)
    disclosure = _disclosure(root)
    authority = disclosure["authority_state"]

    assert disclosure["operator_exposure_disclosure_recorded"] is True
    assert disclosure["operator_decision_state"] == "PENDING"
    assert disclosure["future_operator_choices"] == [
        "APPROVE_NEXT_GOVERNANCE_STEP_WITH_EXPOSURE_LIMITATIONS",
        "REQUIRE_FRESH_FORWARD_CONFIRMATION",
        "RECLASSIFY_HISTORICAL_PERIOD_AS_EXPLORATORY",
        "DEFER",
        "REJECT_OR_RETIRE",
    ]
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
    ("field", "value"),
    [
        ("operator_disclosure_record_path", "docs/assurance/operator_disclosures/wrong.json"),
        ("operator_disclosure_record_sha256", "0" * 64),
    ],
)
def test_v046_active_disclosure_binding_fails_closed(tmp_path, field, value):
    root = _tree(tmp_path)
    active_path = root / context.ACTIVE_TASK_RELPATH
    active = _load_json(active_path)
    active[field] = value
    _write_json(active_path, active)

    _fail(root)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("answers.0.answer", "KNOWN_NO"),
        ("answers.1.answer", False),
        ("answers.2.confidence", "HIGH"),
        ("operator", "SomeoneElse"),
        ("disclosure_date", "2026-08-02"),
        ("operator_decision_state", "APPROVE_NEXT_GOVERNANCE_STEP_WITH_EXPOSURE_LIMITATIONS"),
        ("operator_exposure_disclosure_recorded", False),
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
    ],
)
def test_v046_disclosure_mutations_fail_closed(tmp_path, path, value):
    root = _tree(tmp_path)
    disclosure = _disclosure(root)
    mutated = copy.deepcopy(disclosure)
    target = mutated
    parts = path.split(".")
    for part in parts[:-1]:
        target = target[int(part)] if part.isdigit() else target[part]
    last = parts[-1]
    if last.isdigit():
        target[int(last)] = value
    else:
        target[last] = value

    _rewrite_disclosure(root, mutated)

    _fail(root)


def test_v046_receipt_wrong_next_action_or_selected_decision_fails_closed(tmp_path):
    root = _tree(tmp_path)
    receipt = _receipt(root)
    receipt["next_actions"] = ["APPROVE_NEXT_GOVERNANCE_STEP_WITH_EXPOSURE_LIMITATIONS"]
    _rewrite_receipt_and_active(root, receipt)

    _fail(root)


def test_v046_receipt_wrong_disclosure_hash_fails_closed(tmp_path):
    root = _tree(tmp_path)
    receipt = _receipt(root)
    receipt["h001_operator_exposure_disclosure_binding"]["disclosure_record_sha256"] = "0" * 64
    _rewrite_receipt_and_active(root, receipt)

    _fail(root)


def test_v046_previous_review_artifacts_remain_byte_identical(tmp_path):
    root = _tree(tmp_path)
    context.load_and_verify_continuity_state(root)
    expected = {
        context._V044_REVIEW_RECORD_RELPATH: "6773f7b69ae0c5c9093ed49eb3a7667ebc141df2f11ee0086b4b26d93ea452c6",
        "tests/assurance/test_h001_c1_directionality_atomic_repair_candidate_review_record.py": "df26801684def7723787e2ac59866cdb90607eedf53303a664b37b586d9315cb",
        context._v044.AMENDMENT_RELPATH: "2bcfaa1f10cfebb6ab7ead9b29bf4a5b4c8f38187ce37af21b32dad99064f98b",
        "quantbot/continuity/h001_c1_directionality_atomic_repair_candidate_v044.py": "3ce96c305bc948a31f2e73c04933e7151cff162a44ccd9b7bb8c5519d7a112d1",
        "tests/continuity/test_h001_c1_directionality_atomic_repair_candidate_v044.py": "bb3e13f5000ac8fe449a78d02ba6f2b236b776ac49a031e14478e53a9719f415",
        context._V044_CONTINUITY_REPAIR_REVIEW_RECORD_RELPATH: "b2fdb537fd60ecbfc87966fc369439392c8ad303b61b89ea10fa5ba0d5183042",
        context._V044_CONTINUITY_REPAIR_REVIEW_HANDOFF_RELPATH: "64e73fa56ed831dcf7a2c1a450dafa2f66258790261f47e50793ac4a2a968a3c",
    }

    for path, digest in expected.items():
        assert hashlib.sha256((root / path).read_bytes()).hexdigest() == digest


def test_v046_historical_v044_review_phase_remains_valid(tmp_path):
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
    active.pop("operator_exposure_disclosure_review_record_path", None)
    active.pop("operator_exposure_disclosure_review_record_sha256", None)
    _write_json(active_path, active)

    state = context.load_and_verify_continuity_state(root)

    assert state["active_task"]["phase"] == context._V044_REVIEW_RECORDED_PHASE
