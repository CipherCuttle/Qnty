"""Regression coverage for the prospective H001 C2 resolution requirements candidate."""

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


def _candidate(root):
    return _load_json(root / context._H001_C2_RESOLUTION_CANDIDATE_RELPATH)


def _receipt(root):
    return _load_json(root / context._H001_C2_RESOLUTION_CANDIDATE_HANDOFF_RELPATH)


def _rewrite_candidate(root, candidate):
    _write_json(root / context._H001_C2_RESOLUTION_CANDIDATE_RELPATH, candidate)


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


def test_v050_candidate_is_prospective_and_non_effective(tmp_path):
    root = _tree(tmp_path)

    state = context.load_and_verify_continuity_state(root)
    candidate = _candidate(root)
    receipt = _receipt(root)

    assert state["active_task"]["phase"] == context._H001_C2_RESOLUTION_CANDIDATE_CONSTRUCTED_PHASE
    assert state["handoff_receipt"]["next_actions"] == ["FRESH_HOSTILE_REVIEW_OF_H001_C2_RESOLUTION_CANDIDATE"]
    assert candidate["status"] == "CANDIDATE_REVIEW_REQUIRED_NOT_EFFECTIVE_NOT_RESOLVING_C2"
    assert receipt["h001_c2_resolution_candidate_binding"]["candidate_record_sha256"] == context._H001_C2_RESOLUTION_CANDIDATE_SHA256
    assert receipt["h001_c2_resolution_candidate_binding"]["review_completed"] is False
    assert receipt["h001_c2_resolution_candidate_binding"]["review_passed"] is False


def test_v050_boundary_rule_is_not_selected_by_this_candidate(tmp_path):
    root = _tree(tmp_path)
    context.load_and_verify_continuity_state(root)
    boundary = _candidate(root)["boundary_rule"]

    assert boundary["selected_boundary_rule"] == "NONE_SELECTED"
    assert boundary["selection_authority_excludes_this_candidate"] is True
    assert boundary["candidate_boundary_rules_under_consideration"] == [
        "funding_time_utc < bar_open",
        "funding_time_utc <= bar_open",
    ]
    for required in (
        "causal/event-time semantics",
        "source timestamps",
        "exchange mechanics",
        "predeclared treatment of equal timestamps",
    ):
        assert required in boundary["required_selection_bases"]
    for forbidden in ("PnL", "returns", "Sharpe ratio", "which choice makes H001 perform better"):
        assert forbidden in boundary["prohibited_selection_bases"]


def test_v050_requirements_distinguish_historical_from_prospective_provenance(tmp_path):
    root = _tree(tmp_path)
    context.load_and_verify_continuity_state(root)
    requirements = _candidate(root)["c2_resolution_requirements"]

    historical = requirements["historical_provenance_claims"]
    assert historical["current_status"] == "UNVERIFIABLE_WHILE_V0_UNAVAILABLE"
    assert "TREAT_UNAVAILABILITY_AS_CONTAMINATION_PROOF" in historical["prohibited_treatment"]
    assert "TREAT_UNAVAILABILITY_AS_NON_EXPOSURE_PROOF" in historical["prohibited_treatment"]

    prospective = requirements["prospective_provenance_requirements"]
    assert prospective["must_be_satisfied_before_confirmation"] is True
    assert prospective["required_elements"] == [
        "source_identity",
        "artifact_identity",
        "availability",
        "independent_verification",
        "authority_to_rely_on_provenance",
    ]

    disclosure = requirements["operator_disclosure"]
    assert disclosure["role"] == "GOVERNANCE_INPUT_ONLY_NOT_A_PROVENANCE_FINDING"
    assert "TREAT_OPERATOR_DISCLOSURE_AS_C2_RESOLUTION" in disclosure["prohibited_treatment"]

    availability = requirements["availability"]
    assert availability["current_state"] == "UNAVAILABLE"
    assert availability["current_verified_copy_count"] == 0

    independent_verification = requirements["independent_verification"]
    assert independent_verification["reviewer_independence_required"] == "EXTERNAL_TO_RECORDING_SESSION"
    assert independent_verification["candidate_local_digest_or_canonicalization_is_not_verification"] is True

    authority = requirements["authority_to_rely_on_provenance"]
    assert authority["granted_by_this_candidate"] is False
    assert authority["self_granting_forbidden"] is True


def test_v050_authority_matrix_remains_non_effective_and_zero_execution(tmp_path):
    root = _tree(tmp_path)
    context.load_and_verify_continuity_state(root)
    authority = _candidate(root)["authority_state"]

    for key in (
        "C2_resolved",
        "activation_authorized",
        "candidate_effective",
        "dispatcher_released",
        "execution_authorized",
        "holdout_authorized",
        "implementation_authorized",
        "live_authorized",
        "paper_trade_authorized",
        "real_data_access_authorized",
        "scientific_authorized",
        "trust_root_registered",
    ):
        assert authority[key] is False
    assert authority["execution_budget"] == 0
    assert authority["execution_count"] == 0


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("status", "C2_RESOLVED"),
        ("boundary_rule.selected_boundary_rule", "funding_time_utc < bar_open"),
        ("boundary_rule.selected_boundary_rule", "funding_time_utc <= bar_open"),
        ("boundary_rule.selection_authority_excludes_this_candidate", False),
        ("c2_resolution_requirements.authority_to_rely_on_provenance.granted_by_this_candidate", True),
        ("c2_resolution_requirements.availability.current_state", "VERIFIED_AVAILABLE"),
        ("c2_resolution_requirements.availability.current_verified_copy_count", 2),
        ("c2_resolution_requirements.contamination_risk.current_state", "NON_EXPOSURE_PROVEN"),
        ("c2_resolution_requirements.historical_provenance_claims.current_status", "PRISTINE_CONFIRMATORY"),
        ("c2_resolution_requirements.independent_verification.candidate_local_digest_or_canonicalization_is_not_verification", False),
        ("authority_state.candidate_effective", True),
        ("authority_state.C2_resolved", True),
        ("authority_state.scientific_authorized", True),
        ("authority_state.activation_authorized", True),
        ("authority_state.implementation_authorized", True),
        ("authority_state.real_data_access_authorized", True),
        ("authority_state.execution_authorized", True),
        ("authority_state.execution_budget", 1),
        ("authority_state.execution_count", 1),
        ("authority_state.holdout_authorized", True),
        ("authority_state.paper_trade_authorized", True),
        ("authority_state.live_authorized", True),
        ("authority_state.dispatcher_released", True),
        ("authority_state.trust_root_registered", True),
        ("predecessor_bindings.current_handoff.sha256", "0" * 64),
        ("predecessor_bindings.operator_governance_decision.sha256", "0" * 64),
        ("predecessor_bindings.operator_governance_decision_hostile_review.sha256", "0" * 64),
    ],
)
def test_v050_candidate_mutations_fail_closed(tmp_path, path, value):
    root = _tree(tmp_path)
    candidate = copy.deepcopy(_candidate(root))
    _set_path(candidate, path, value)

    _rewrite_candidate(root, candidate)

    _fail(root)


def test_v050_unknown_extra_keys_fail_closed(tmp_path):
    root = _tree(tmp_path)
    candidate = copy.deepcopy(_candidate(root))
    candidate["unknown_extra_key"] = True
    _rewrite_candidate(root, candidate)

    _fail(root)


def test_v050_non_effects_cannot_be_shortened(tmp_path):
    root = _tree(tmp_path)
    candidate = copy.deepcopy(_candidate(root))
    candidate["non_effects"].pop()
    _rewrite_candidate(root, candidate)

    _fail(root)


def test_v050_active_candidate_record_binding_fails_closed(tmp_path):
    root = _tree(tmp_path)
    active_path = root / context.ACTIVE_TASK_RELPATH
    active = _load_json(active_path)
    active["h001_c2_resolution_candidate_record_sha256"] = "0" * 64
    _write_json(active_path, active)

    _fail(root)


def test_v050_receipt_wrong_candidate_binding_fails_closed(tmp_path):
    root = _tree(tmp_path)
    receipt_path = root / context._H001_C2_RESOLUTION_CANDIDATE_HANDOFF_RELPATH
    receipt = _load_json(receipt_path)
    receipt["h001_c2_resolution_candidate_binding"]["review_passed"] = True
    _write_json(receipt_path, receipt)
    active_path = root / context.ACTIVE_TASK_RELPATH
    active = _load_json(active_path)
    active["handoff_receipt_sha256"] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    _write_json(active_path, active)

    _fail(root)
