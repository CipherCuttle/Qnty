"""Regression coverage for the H001 operator governance decision record."""

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


def _decision(root):
    return _load_json(root / context._H001_OPERATOR_GOVERNANCE_DECISION_RELPATH)


def _receipt(root):
    return _load_json(root / context._H001_OPERATOR_GOVERNANCE_DECISION_HANDOFF_RELPATH)


def _rewrite_decision(root, decision):
    _write_json(root / context._H001_OPERATOR_GOVERNANCE_DECISION_RELPATH, decision)


def _rewrite_receipt_and_active(root, receipt):
    receipt_path = root / context._H001_OPERATOR_GOVERNANCE_DECISION_HANDOFF_RELPATH
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


def test_v048_operator_decision_records_combined_conservative_decision(tmp_path):
    root = _tree(tmp_path)

    state = context.load_and_verify_continuity_state(root)
    decision = _decision(root)
    receipt = _receipt(root)

    assert state["active_task"]["phase"] == context._H001_OPERATOR_GOVERNANCE_DECISION_RECORDED_PHASE
    assert state["handoff_receipt"]["next_actions"] == ["FRESH_HOSTILE_REVIEW_OF_H001_OPERATOR_GOVERNANCE_DECISION"]
    assert decision["operator_decision_recorded"] is True
    assert decision["operator_decision_state"] == context._H001_OPERATOR_GOVERNANCE_DECISION_STATE
    assert decision["decision_components"] == [
        "RECLASSIFY_HISTORICAL_PERIOD_AS_EXPLORATORY",
        "REQUIRE_FRESH_FORWARD_CONFIRMATION",
        "DEFER_CANDIDATE_EFFECTIVENESS",
    ]
    assert receipt["h001_operator_governance_decision_binding"]["decision_record_sha256"] == context._H001_OPERATOR_GOVERNANCE_DECISION_SHA256


def test_v048_evidentiary_classification_is_exploratory_without_overclaiming(tmp_path):
    root = _tree(tmp_path)
    context.load_and_verify_continuity_state(root)
    evidence = _decision(root)["evidentiary_classification"]

    assert evidence["historical_h001_evidence_classification"] == "EXPLORATORY"
    assert evidence["historical_h001_evidence_pristine_confirmatory"] is False
    assert evidence["historical_h001_evidence_invalid_or_useless"] is False
    assert evidence["contamination_proven"] is False
    assert evidence["non_exposure_proven"] is False
    assert "exploratory_evidence" in evidence["permitted_uses"]
    assert "economic_edge" in evidence["prohibited_claims"]


def test_v048_fresh_confirmation_c2_and_candidate_effectiveness_state(tmp_path):
    root = _tree(tmp_path)
    context.load_and_verify_continuity_state(root)
    decision = _decision(root)

    assert decision["fresh_confirmation_requirement"]["fresh_forward_confirmation_required"] is True
    assert decision["fresh_confirmation_requirement"]["confirmation_must_be_governed_by_frozen_specification_before_outcomes"] is True
    assert decision["candidate_effectiveness"] == {
        "candidate_effective": False,
        "candidate_preserved": True,
        "effectiveness_state": "DEFERRED",
        "rejected": False,
        "retired": False,
    }
    assert decision["C2_state"]["C2_resolved"] is False
    assert decision["C2_state"]["prospective_resolution_required_before_confirmation"] is True
    assert decision["C2_state"]["selected_boundary_rule"] == "NONE_SELECTED"
    assert decision["C2_state"]["candidate_boundary_rules_under_consideration"] == [
        "funding_time_utc < bar_open",
        "funding_time_utc <= bar_open",
    ]


def test_v048_authority_matrix_remains_non_effective_and_zero_execution(tmp_path):
    root = _tree(tmp_path)
    context.load_and_verify_continuity_state(root)
    authority = _decision(root)["authority_state"]

    assert authority["candidate_review_completed"] is True
    assert authority["candidate_review_passed"] is True
    assert authority["operator_exposure_disclosure_recorded"] is True
    assert authority["operator_exposure_disclosure_review_completed"] is True
    assert authority["operator_exposure_disclosure_review_passed"] is True
    assert authority["operator_decision_recorded"] is True
    for key in (
        "candidate_effective",
        "scientific_authorized",
        "activation_authorized",
        "implementation_authorized",
        "real_data_access_authorized",
        "execution_authorized",
        "C2_resolved",
        "holdout_authorized",
        "paper_trade_authorized",
        "live_authorized",
        "dispatcher_released",
        "trust_root_registered",
    ):
        assert authority[key] is False
    assert authority["execution_budget"] == 0
    assert authority["execution_count"] == 0


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("operator_decision_state", "PENDING"),
        ("decision_components.0", "APPROVE_NEXT_GOVERNANCE_STEP_WITH_EXPOSURE_LIMITATIONS"),
        ("decision_components.1", "DEFER"),
        ("candidate_effectiveness.candidate_effective", True),
        ("candidate_effectiveness.effectiveness_state", "EFFECTIVE"),
        ("candidate_effectiveness.rejected", True),
        ("candidate_effectiveness.retired", True),
        ("evidentiary_classification.historical_h001_evidence_classification", "CONFIRMATORY"),
        ("evidentiary_classification.historical_h001_evidence_pristine_confirmatory", True),
        ("evidentiary_classification.historical_h001_evidence_invalid_or_useless", True),
        ("evidentiary_classification.contamination_proven", True),
        ("evidentiary_classification.non_exposure_proven", True),
        ("fresh_confirmation_requirement.fresh_forward_confirmation_required", False),
        ("C2_state.C2_resolved", True),
        ("C2_state.selected_boundary_rule", "funding_time_utc < bar_open"),
        ("C2_state.selected_boundary_rule", "funding_time_utc <= bar_open"),
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
        ("predecessor_bindings.operator_exposure_disclosure.sha256", "0" * 64),
        ("predecessor_bindings.operator_exposure_disclosure_hostile_review.sha256", "0" * 64),
        ("predecessor_bindings.current_handoff.sha256", "0" * 64),
    ],
)
def test_v048_decision_mutations_fail_closed(tmp_path, path, value):
    root = _tree(tmp_path)
    decision = copy.deepcopy(_decision(root))
    _set_path(decision, path, value)

    _rewrite_decision(root, decision)

    _fail(root)


def test_v048_missing_decision_component_fails_closed(tmp_path):
    root = _tree(tmp_path)
    decision = copy.deepcopy(_decision(root))
    decision["decision_components"].pop()
    _rewrite_decision(root, decision)

    _fail(root)


def test_v048_unknown_extra_keys_fail_closed(tmp_path):
    root = _tree(tmp_path)
    decision = copy.deepcopy(_decision(root))
    decision["unknown_extra_key"] = True
    _rewrite_decision(root, decision)

    _fail(root)


def test_v048_active_decision_record_binding_fails_closed(tmp_path):
    root = _tree(tmp_path)
    active_path = root / context.ACTIVE_TASK_RELPATH
    active = _load_json(active_path)
    active["operator_governance_decision_record_sha256"] = "0" * 64
    _write_json(active_path, active)

    _fail(root)


def test_v048_receipt_wrong_decision_binding_fails_closed(tmp_path):
    root = _tree(tmp_path)
    receipt = _receipt(root)
    receipt["h001_operator_governance_decision_binding"]["fresh_forward_confirmation_required"] = False
    _rewrite_receipt_and_active(root, receipt)

    _fail(root)


def test_v048_historical_phases_and_protected_hashes_remain_valid(tmp_path):
    root = _tree(tmp_path)
    active_path = root / context.ACTIVE_TASK_RELPATH
    active = _load_json(active_path)
    active["phase"] = context._H001_OPERATOR_EXPOSURE_DISCLOSURE_REVIEW_PASSED_PHASE
    active["handoff_receipt_path"] = context._H001_OPERATOR_EXPOSURE_DISCLOSURE_REVIEW_HANDOFF_RELPATH
    active["handoff_receipt_sha256"] = "e82eefad6e05c0ef1487c36cf4a8c4976de6c9025c87ff3728ba9bd490f2209d"
    active.pop("operator_governance_decision_record_path")
    active.pop("operator_governance_decision_record_sha256")
    receipt_path = root / context._H001_OPERATOR_EXPOSURE_DISCLOSURE_REVIEW_HANDOFF_RELPATH
    receipt = _load_json(receipt_path)
    receipt["current_transition_files"] = [
        {"path": path, "sha256": hashlib.sha256((root / path).read_bytes()).hexdigest()}
        for path in context._H001_OPERATOR_EXPOSURE_DISCLOSURE_REVIEW_CURRENT_FILES
    ]
    for item in receipt["evidence"]:
        if item["path"] in context._H001_OPERATOR_EXPOSURE_DISCLOSURE_REVIEW_CURRENT_FILES:
            item["sha256"] = hashlib.sha256((root / item["path"]).read_bytes()).hexdigest()
    _write_json(receipt_path, receipt)
    active["handoff_receipt_sha256"] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    _write_json(active_path, active)

    state = context.load_and_verify_continuity_state(root)

    assert state["active_task"]["phase"] == context._H001_OPERATOR_EXPOSURE_DISCLOSURE_REVIEW_PASSED_PHASE

    expected = {
        context._H001_OPERATOR_EXPOSURE_DISCLOSURE_RELPATH: context._H001_OPERATOR_EXPOSURE_DISCLOSURE_SHA256,
        context._H001_OPERATOR_EXPOSURE_DISCLOSURE_HANDOFF_RELPATH: "13ed0644ca3f43fc9e1223627f8cb67518602d94c5bb0e9cbaa57125db9a340f",
        context._H001_OPERATOR_EXPOSURE_DISCLOSURE_REVIEW_RECORD_RELPATH: context._H001_OPERATOR_EXPOSURE_DISCLOSURE_REVIEW_RECORD_SHA256,
        context._V044_CONTINUITY_REPAIR_REVIEW_RECORD_RELPATH: context._V044_CONTINUITY_REPAIR_REVIEW_RECORD_SHA256,
        context._V044_CONTINUITY_REPAIR_REVIEW_HANDOFF_RELPATH: "64e73fa56ed831dcf7a2c1a450dafa2f66258790261f47e50793ac4a2a968a3c",
        context._V044_REVIEW_RECORD_RELPATH: context._V044_REVIEW_RECORD_SHA256,
        context._v044.AMENDMENT_RELPATH: context._H001_OPERATOR_GOVERNANCE_DECISION_PROTECTED_HASHES["v044_amendment"],
        "quantbot/continuity/h001_c1_directionality_atomic_repair_candidate_v044.py": context._H001_OPERATOR_GOVERNANCE_DECISION_PROTECTED_HASHES["v044_validator"],
        "tests/continuity/test_h001_c1_directionality_atomic_repair_candidate_v044.py": context._H001_OPERATOR_GOVERNANCE_DECISION_PROTECTED_HASHES["v044_test"],
        "tests/assurance/test_h001_c1_directionality_atomic_repair_candidate_review_record.py": context._H001_OPERATOR_GOVERNANCE_DECISION_PROTECTED_HASHES["focused_review_test"],
    }
    for path, digest in expected.items():
        assert hashlib.sha256((root / path).read_bytes()).hexdigest() == digest
