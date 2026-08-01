"""Regression coverage for recording the H001 operator governance decision hostile-review pass."""

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
    return _load_json(root / context._H001_OPERATOR_GOVERNANCE_DECISION_REVIEW_RECORD_RELPATH)


def _receipt(root):
    return _load_json(root / context._H001_OPERATOR_GOVERNANCE_DECISION_REVIEW_HANDOFF_RELPATH)


def _decision(root):
    return _load_json(root / context._H001_OPERATOR_GOVERNANCE_DECISION_RELPATH)


def _rewrite_record(root, record):
    _write_json(root / context._H001_OPERATOR_GOVERNANCE_DECISION_REVIEW_RECORD_RELPATH, record)


def _rewrite_receipt_and_active(root, receipt):
    receipt_path = root / context._H001_OPERATOR_GOVERNANCE_DECISION_REVIEW_HANDOFF_RELPATH
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


def test_v049_review_pass_binds_candidate_decision_handoff_verdict_and_state(tmp_path):
    root = _tree(tmp_path)

    state = context.load_and_verify_continuity_state(root)
    record = _record(root)
    receipt = _receipt(root)

    assert state["active_task"]["phase"] == context._H001_OPERATOR_GOVERNANCE_DECISION_REVIEW_PASSED_PHASE
    assert state["handoff_receipt"]["next_actions"] == [
        "CONSTRUCT_PROSPECTIVE_H001_C2_RESOLUTION_CANDIDATE_FOR_REVIEW"
    ]
    assert receipt["receipt_index"] == 49
    assert record["review_kind"] == "H001_OPERATOR_GOVERNANCE_DECISION_HOSTILE_REVIEW"
    assert record["review_verdict"] == "PASS_H001_OPERATOR_GOVERNANCE_DECISION_SAFE"
    assert record["operator_decision_review_completed"] is True
    assert record["operator_decision_review_passed"] is True
    assert record["candidate_binding"] == {
        "reviewed_commit": "76216e0d6cf22101a6c1318cd9e02ba0beda61d3",
        "reviewed_parent": "6be95460735718eaf28d7d3e775baf2db98ecc6c",
        "reviewed_tree": "d562d5ea22509c34cc7981f23ff3183051e9eae6",
    }
    assert record["decision_binding"] == {
        "reviewed_decision_path": context._H001_OPERATOR_GOVERNANCE_DECISION_RELPATH,
        "reviewed_decision_sha256": context._H001_OPERATOR_GOVERNANCE_DECISION_SHA256,
    }
    assert record["handoff_binding"] == {
        "reviewed_handoff_path": context._H001_OPERATOR_GOVERNANCE_DECISION_HANDOFF_RELPATH,
        "reviewed_handoff_sha256": "4c5a192fb5f393891ea53482624a45b2a7461bb7e82331476a049226ed97ae1e",
    }
    assert receipt["h001_operator_governance_decision_review_binding"]["review_record_sha256"] == (
        context._H001_OPERATOR_GOVERNANCE_DECISION_REVIEW_RECORD_SHA256
    )


def test_v049_decision_semantics_authority_and_c2_remain_non_effective(tmp_path):
    root = _tree(tmp_path)
    context.load_and_verify_continuity_state(root)
    record = _record(root)
    decision = _decision(root)

    assert record["decision_components"] == [
        "RECLASSIFY_HISTORICAL_PERIOD_AS_EXPLORATORY",
        "REQUIRE_FRESH_FORWARD_CONFIRMATION",
        "DEFER_CANDIDATE_EFFECTIVENESS",
    ]
    assert record["evidentiary_classification"] == decision["evidentiary_classification"]
    assert record["evidentiary_classification"]["historical_h001_evidence_classification"] == "EXPLORATORY"
    assert record["fresh_confirmation_requirement"]["fresh_forward_confirmation_required"] is True
    assert record["candidate_effectiveness"] == {
        "candidate_effective": False,
        "candidate_preserved": True,
        "effectiveness_state": "DEFERRED",
        "rejected": False,
        "retired": False,
    }
    assert record["C2_state"]["C2_resolved"] is False
    assert record["C2_state"]["selected_boundary_rule"] == "NONE_SELECTED"
    authority = record["authority_state"]
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
    assert authority["operator_decision_review_completed"] is True
    assert authority["operator_decision_review_passed"] is True


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("candidate_binding.reviewed_commit", "0" * 40),
        ("candidate_binding.reviewed_tree", "0" * 40),
        ("candidate_binding.reviewed_parent", "0" * 40),
        ("decision_binding.reviewed_decision_path", "docs/assurance/operator_decisions/wrong.json"),
        ("decision_binding.reviewed_decision_sha256", "0" * 64),
        ("handoff_binding.reviewed_handoff_path", "docs/control/tasks/RECOVER_OR_RETIRE_CANDIDATE1_V0_FROZEN_INPUT/handoff_v047.json"),
        ("handoff_binding.reviewed_handoff_sha256", "0" * 64),
        ("review_verdict", "FAIL"),
        ("operator_decision_review_completed", False),
        ("operator_decision_review_passed", False),
        ("decision_components.0", "RECLASSIFY_HISTORICAL_PERIOD_AS_CONFIRMATORY"),
        ("evidentiary_classification.historical_h001_evidence_classification", "CONFIRMATORY"),
        ("evidentiary_classification.historical_h001_evidence_classification", "INVALID"),
        ("evidentiary_classification.historical_h001_evidence_invalid_or_useless", True),
        ("evidentiary_classification.historical_h001_evidence_pristine_confirmatory", True),
        ("evidentiary_classification.contamination_proven", True),
        ("evidentiary_classification.non_exposure_proven", True),
        ("fresh_confirmation_requirement.fresh_forward_confirmation_required", False),
        ("candidate_effectiveness.candidate_effective", True),
        ("candidate_effectiveness.effectiveness_state", "EFFECTIVE"),
        ("candidate_effectiveness.rejected", True),
        ("candidate_effectiveness.retired", True),
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
        ("hostile_mutation_evidence.0.result", "PASS"),
        ("protected_hashes.operator_decision", "0" * 64),
        ("protected_hashes.v048_handoff", "0" * 64),
    ],
)
def test_v049_review_record_mutations_fail_closed(tmp_path, path, value):
    root = _tree(tmp_path)
    record = copy.deepcopy(_record(root))
    _set_path(record, path, value)

    _rewrite_record(root, record)

    _fail(root)


def test_v049_missing_decision_component_fails_closed(tmp_path):
    root = _tree(tmp_path)
    record = copy.deepcopy(_record(root))
    record["decision_components"].pop()
    _rewrite_record(root, record)

    _fail(root)


def test_v049_edge_or_blindness_overclaim_fails_closed(tmp_path):
    root = _tree(tmp_path)
    record = copy.deepcopy(_record(root))
    record["evidentiary_classification"]["prohibited_claims"].remove("economic_edge")
    record["review_conclusions"].append("ECONOMIC_EDGE_ESTABLISHED")
    _rewrite_record(root, record)

    _fail(root)


def test_v049_unknown_extra_key_fails_closed(tmp_path):
    root = _tree(tmp_path)
    record = copy.deepcopy(_record(root))
    record["unknown_extra_key"] = True
    _rewrite_record(root, record)

    _fail(root)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("operator_governance_decision_review_record_path", "docs/assurance/reviews/wrong.json"),
        ("operator_governance_decision_review_record_sha256", "0" * 64),
    ],
)
def test_v049_active_review_record_binding_fails_closed(tmp_path, field, value):
    root = _tree(tmp_path)
    active_path = root / context.ACTIVE_TASK_RELPATH
    active = _load_json(active_path)
    active[field] = value
    _write_json(active_path, active)

    _fail(root)


def test_v049_receipt_wrong_review_hash_or_next_action_fails_closed(tmp_path):
    root = _tree(tmp_path)
    receipt = _receipt(root)
    receipt["h001_operator_governance_decision_review_binding"]["review_record_sha256"] = "0" * 64
    _rewrite_receipt_and_active(root, receipt)

    _fail(root)

    root = _tree(tmp_path / "next")
    receipt = _receipt(root)
    receipt["next_actions"] = ["EXECUTE_H001"]
    _rewrite_receipt_and_active(root, receipt)

    _fail(root)


def test_v049_historical_continuity_phases_remain_valid(tmp_path):
    root = _tree(tmp_path)
    active_path = root / context.ACTIVE_TASK_RELPATH
    active = _load_json(active_path)
    active["phase"] = context._H001_OPERATOR_GOVERNANCE_DECISION_RECORDED_PHASE
    active["handoff_receipt_path"] = context._H001_OPERATOR_GOVERNANCE_DECISION_HANDOFF_RELPATH
    active["handoff_receipt_sha256"] = "4c5a192fb5f393891ea53482624a45b2a7461bb7e82331476a049226ed97ae1e"
    active.pop("operator_governance_decision_review_record_path")
    active.pop("operator_governance_decision_review_record_sha256")
    receipt_path = root / context._H001_OPERATOR_GOVERNANCE_DECISION_HANDOFF_RELPATH
    receipt = _load_json(receipt_path)
    receipt["current_transition_files"] = [
        {"path": path, "sha256": hashlib.sha256((root / path).read_bytes()).hexdigest()}
        for path in context._H001_OPERATOR_GOVERNANCE_DECISION_CURRENT_FILES
    ]
    for item in receipt["evidence"]:
        if item["path"] in context._H001_OPERATOR_GOVERNANCE_DECISION_CURRENT_FILES:
            item["sha256"] = hashlib.sha256((root / item["path"]).read_bytes()).hexdigest()
    _write_json(receipt_path, receipt)
    active["handoff_receipt_sha256"] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    _write_json(active_path, active)

    state = context.load_and_verify_continuity_state(root)

    assert state["active_task"]["phase"] == context._H001_OPERATOR_GOVERNANCE_DECISION_RECORDED_PHASE


def test_v049_protected_hashes_remain_unchanged(tmp_path):
    root = _tree(tmp_path)
    context.load_and_verify_continuity_state(root)
    expected = {
        context._H001_OPERATOR_GOVERNANCE_DECISION_RELPATH: "ef3d26eff6adf684d33591af15c0cc8488ddc2f5dac6b94b08d39d5ee7aa5e8e",
        context._H001_OPERATOR_GOVERNANCE_DECISION_HANDOFF_RELPATH: "4c5a192fb5f393891ea53482624a45b2a7461bb7e82331476a049226ed97ae1e",
        context._H001_OPERATOR_EXPOSURE_DISCLOSURE_REVIEW_RECORD_RELPATH: "3d54af162be4f7a18fd88a871fc1771514dbbb832bc8e145f50544916f041ee6",
        context._H001_OPERATOR_EXPOSURE_DISCLOSURE_REVIEW_HANDOFF_RELPATH: "e82eefad6e05c0ef1487c36cf4a8c4976de6c9025c87ff3728ba9bd490f2209d",
        context._H001_OPERATOR_EXPOSURE_DISCLOSURE_RELPATH: "edcd90cf43e860e6db998c6a45cd352b70071f3a795a53e04442b6d1a9b0932e",
        context._H001_OPERATOR_EXPOSURE_DISCLOSURE_HANDOFF_RELPATH: "13ed0644ca3f43fc9e1223627f8cb67518602d94c5bb0e9cbaa57125db9a340f",
        context._V044_CONTINUITY_REPAIR_REVIEW_RECORD_RELPATH: "b2fdb537fd60ecbfc87966fc369439392c8ad303b61b89ea10fa5ba0d5183042",
        context._V044_CONTINUITY_REPAIR_REVIEW_HANDOFF_RELPATH: "64e73fa56ed831dcf7a2c1a450dafa2f66258790261f47e50793ac4a2a968a3c",
        context._V044_REVIEW_RECORD_RELPATH: "6773f7b69ae0c5c9093ed49eb3a7667ebc141df2f11ee0086b4b26d93ea452c6",
        context._v044.AMENDMENT_RELPATH: "2bcfaa1f10cfebb6ab7ead9b29bf4a5b4c8f38187ce37af21b32dad99064f98b",
        "quantbot/continuity/h001_c1_directionality_atomic_repair_candidate_v044.py": "3ce96c305bc948a31f2e73c04933e7151cff162a44ccd9b7bb8c5519d7a112d1",
        "tests/continuity/test_h001_c1_directionality_atomic_repair_candidate_v044.py": "bb3e13f5000ac8fe449a78d02ba6f2b236b776ac49a031e14478e53a9719f415",
    }

    for path, digest in expected.items():
        assert hashlib.sha256((root / path).read_bytes()).hexdigest() == digest
