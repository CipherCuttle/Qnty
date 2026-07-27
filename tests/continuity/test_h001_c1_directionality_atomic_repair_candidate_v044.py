"""Adversarial checks for v044's C1 traceability repair candidate.

v043 was reviewed REPAIR_REQUIRED: its amendment semantics were generated
from and validated against the same module-local AMENDMENT_DOCUMENT, so a
coordinated edit of the constant plus every candidate-local hash still
verified. This suite's primary job is to prove that defect is actually
fixed here: every mutation below performs a *legitimate* coordinated edit
(mutate content, regenerate every candidate-local hash and receipt exactly
as an editor with write access would) and never touches the two upstream
historical anchors (the frozen H001 design document and v041's own handoff
receipt). If verification still passes after such a mutation, the fix has
not worked.
"""

import copy
import hashlib
import json
import shutil

import pytest

from quantbot.continuity import context
from quantbot.continuity import h001_c1_directionality_atomic_repair_candidate_v044 as v044

ROOT = __import__("pathlib").Path(__file__).parents[2]


def _tree(tmp_path):
    root = tmp_path / "repo"
    shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__"))
    return root


def _write(path, value):
    path.write_bytes(context.canonical_json_bytes(value))


def _fail(root):
    with pytest.raises(ValueError):
        context.load_and_verify_continuity_state(root)


def _ok(root):
    context.load_and_verify_continuity_state(root)


def _receipt(root):
    return json.loads((root / v044.HANDOFF_RELPATH).read_bytes())


def _write_receipt_and_repoint(root, receipt):
    _write(root / v044.HANDOFF_RELPATH, receipt)
    active = json.loads((root / context.ACTIVE_TASK_RELPATH).read_bytes())
    active["handoff_receipt_sha256"] = hashlib.sha256((root / v044.HANDOFF_RELPATH).read_bytes()).hexdigest()
    _write(root / context.ACTIVE_TASK_RELPATH, active)


def _amendment(root):
    return json.loads((root / v044.AMENDMENT_RELPATH).read_bytes())


def _write_amendment_and_reissue_evidence(root, amendment):
    """Legitimate coordinated rebinding: write the mutated amendment,
    recompute its hash, and reissue the receipt's evidence entry to match --
    exactly what an editor with full write access to the candidate would do.
    Never touches the historical anchor files."""
    raw = context.canonical_json_bytes(amendment)
    (root / v044.AMENDMENT_RELPATH).write_bytes(raw)
    receipt = _receipt(root)
    receipt["evidence"] = copy.deepcopy(receipt["evidence"])
    receipt["evidence"][-1] = {"path": v044.AMENDMENT_RELPATH, "sha256": hashlib.sha256(raw).hexdigest()}
    _write_receipt_and_repoint(root, receipt)


def _trace_entry(amendment, requirement_id):
    for entry in amendment["trace_matrix"]:
        if entry["requirement_id"] == requirement_id:
            return entry
    raise KeyError(requirement_id)


# --- baseline -------------------------------------------------------------

def test_v044_baseline_verifies(tmp_path):
    root = _tree(tmp_path)
    _ok(root)


def test_v044_baseline_amendment_matches_module_constant(tmp_path):
    root = _tree(tmp_path)
    assert _amendment(root) == v044.AMENDMENT_DOCUMENT


def test_v044_trace_matrix_covers_required_minimum_set(tmp_path):
    root = _tree(tmp_path)
    amendment = _amendment(root)
    ids = {entry["requirement_id"] for entry in amendment["trace_matrix"]}
    assert v044._REQUIRED_TRACE_IDS.issubset(ids)
    assert len(ids) == len(amendment["trace_matrix"])  # no duplicate semantic owner


# --- Phase 4: coordinated scientific-anchor mutations ----------------------
# Each of these performs a full legitimate rebind (mutate + regenerate every
# candidate-local hash) without touching the historical anchor files, and
# must still fail.

def test_v044_rejects_coordinated_alpha_drift(tmp_path):
    root = _tree(tmp_path)
    amendment = copy.deepcopy(v044.AMENDMENT_DOCUMENT)
    _trace_entry(amendment, "ALPHA")["claimed_value"] = 0.10
    amendment["proposed_c1"] = copy.deepcopy(amendment["proposed_c1"])
    amendment["proposed_c1"]["familywise_alpha"] = 0.10
    _write_amendment_and_reissue_evidence(root, amendment)
    _fail(root)


@pytest.mark.parametrize("value", [8, 10])
def test_v044_rejects_coordinated_family_size_drift(tmp_path, value):
    root = _tree(tmp_path)
    amendment = copy.deepcopy(v044.AMENDMENT_DOCUMENT)
    _trace_entry(amendment, "FAMILY_SIZE")["claimed_value"] = value
    amendment["proposed_c1"] = copy.deepcopy(amendment["proposed_c1"])
    amendment["proposed_c1"]["family_size"] = value
    _write_amendment_and_reissue_evidence(root, amendment)
    _fail(root)


def test_v044_rejects_coordinated_hypothesis_drift_to_two_sided(tmp_path):
    root = _tree(tmp_path)
    amendment = copy.deepcopy(v044.AMENDMENT_DOCUMENT)
    _trace_entry(amendment, "REGISTERED_ALTERNATIVE")["claimed_value"] = "two-sided mean net return != 0"
    _write_amendment_and_reissue_evidence(root, amendment)
    _fail(root)


def test_v044_rejects_coordinated_hypothesis_drift_to_negative(tmp_path):
    root = _tree(tmp_path)
    amendment = copy.deepcopy(v044.AMENDMENT_DOCUMENT)
    _trace_entry(amendment, "REGISTERED_ALTERNATIVE")["claimed_value"] = "one-sided mean net return < 0"
    _write_amendment_and_reissue_evidence(root, amendment)
    _fail(root)


@pytest.mark.parametrize("requirement_id,poisoned_value", [
    ("OBSERVED_STATISTIC_DIRECTION", "absolute_HAC_studentized_abs_t_i"),
    ("BOOTSTRAP_STATISTIC_DIRECTION", "absolute_HAC_studentized_abs_tstar_j_b"),
    ("FAMILY_MAXIMUM", "max_j_abs_tstar_j_b"),
])
def test_v044_rejects_coordinated_statistic_drift_to_absolute(tmp_path, requirement_id, poisoned_value):
    root = _tree(tmp_path)
    amendment = copy.deepcopy(v044.AMENDMENT_DOCUMENT)
    _trace_entry(amendment, requirement_id)["claimed_value"] = poisoned_value
    _write_amendment_and_reissue_evidence(root, amendment)
    _fail(root)


def test_v044_rejects_coordinated_tail_drift_to_symmetric(tmp_path):
    root = _tree(tmp_path)
    amendment = copy.deepcopy(v044.AMENDMENT_DOCUMENT)
    _trace_entry(amendment, "TAIL")["claimed_value"] = "symmetric_two_sided"
    _write_amendment_and_reissue_evidence(root, amendment)
    _fail(root)


def test_v044_rejects_coordinated_c2_drift_to_resolved(tmp_path):
    root = _tree(tmp_path)
    amendment = copy.deepcopy(v044.AMENDMENT_DOCUMENT)
    amendment["c2_status"] = copy.deepcopy(amendment["c2_status"])
    amendment["c2_status"]["historical_provenance_status"] = "RESOLVED"
    amendment["c2_status"]["resolution_implied_by_c1_candidate"] = True
    _write_amendment_and_reissue_evidence(root, amendment)
    _fail(root)


@pytest.mark.parametrize("field,value", [
    ("rejected_commit", "0" * 40),
    ("rejected_tree", "0" * 40),
    ("review_outcome", "V043_ACCEPTED"),
])
def test_v044_rejects_rejected_v043_binding_drift(tmp_path, field, value):
    root = _tree(tmp_path)
    amendment = copy.deepcopy(v044.AMENDMENT_DOCUMENT)
    amendment["rejected_v043_binding"] = copy.deepcopy(amendment["rejected_v043_binding"])
    amendment["rejected_v043_binding"][field] = value
    _write_amendment_and_reissue_evidence(root, amendment)
    _fail(root)


def test_v044_rejects_rejected_v043_marked_amended(tmp_path):
    root = _tree(tmp_path)
    amendment = copy.deepcopy(v044.AMENDMENT_DOCUMENT)
    amendment["rejected_v043_binding"] = copy.deepcopy(amendment["rejected_v043_binding"])
    amendment["rejected_v043_binding"]["amended_or_modified"] = True
    _write_amendment_and_reissue_evidence(root, amendment)
    _fail(root)


def test_v044_rejects_rejected_v043_marked_retroactively_approved(tmp_path):
    root = _tree(tmp_path)
    amendment = copy.deepcopy(v044.AMENDMENT_DOCUMENT)
    amendment["rejected_v043_binding"] = copy.deepcopy(amendment["rejected_v043_binding"])
    amendment["rejected_v043_binding"]["retroactively_approved"] = True
    _write_amendment_and_reissue_evidence(root, amendment)
    _fail(root)


@pytest.mark.parametrize("field", [
    "candidate_review_completed", "activation_authorized", "implementation_authorized",
    "execution_authorized", "real_data_access_authorized", "holdout_execution_authorized",
    "scientific_authorized", "paper_trade_authorized", "live_authorized", "wired_into_execute_calibration",
])
def test_v044_rejects_coordinated_authority_drift(tmp_path, field):
    root = _tree(tmp_path)
    amendment = copy.deepcopy(v044.AMENDMENT_DOCUMENT)
    amendment["authorization_state"] = copy.deepcopy(amendment["authorization_state"])
    amendment["authorization_state"][field] = True
    _write_amendment_and_reissue_evidence(root, amendment)
    _fail(root)


@pytest.mark.parametrize("field", ["h001_execution_budget", "h001_execution_count"])
def test_v044_rejects_coordinated_h001_budget_drift(tmp_path, field):
    root = _tree(tmp_path)
    amendment = copy.deepcopy(v044.AMENDMENT_DOCUMENT)
    amendment["authorization_state"] = copy.deepcopy(amendment["authorization_state"])
    amendment["authorization_state"][field] = 1
    _write_amendment_and_reissue_evidence(root, amendment)
    _fail(root)


# --- Phase 5: historical source-anchor substitution ------------------------
# The amendment's own claimed source_path/source_pointers must not be
# trusted; validate() ignores them for the real check and uses hardcoded
# module constants + inherited PROTECTED hashes instead.

def test_v044_rejects_source_path_substitution_in_trace_entry(tmp_path):
    root = _tree(tmp_path)
    amendment = copy.deepcopy(v044.AMENDMENT_DOCUMENT)
    entry = _trace_entry(amendment, "ALPHA")
    entry["source_path"] = "docs/control/active_task.json"
    entry["source_pointers"] = ["/schema_version"]
    _write_amendment_and_reissue_evidence(root, amendment)
    _fail(root)


def test_v044_rejects_historical_design_document_content_mutation(tmp_path):
    """If the historical design file itself is mutated (even matching what
    the amendment now claims), the pre-existing inherited PROTECTED hash for
    that exact path must still catch it -- this is the anti-substitution
    backstop, independent of anything this candidate's own module defines."""
    root = _tree(tmp_path)
    target = root / v044.H001_DESIGN_RELPATH
    doc = json.loads(target.read_bytes())
    doc["validation_test"]["familywise_alpha"] = 0.10
    doc["holdout_test"]["alpha"] = 0.10
    doc["validation_eligibility"]["familywise_adjusted_p_lte"] = 0.10
    target.write_bytes(context.canonical_json_bytes(doc))
    # even if the amendment is coordinately updated to match:
    amendment = copy.deepcopy(v044.AMENDMENT_DOCUMENT)
    _trace_entry(amendment, "ALPHA")["claimed_value"] = 0.10
    amendment["proposed_c1"] = copy.deepcopy(amendment["proposed_c1"])
    amendment["proposed_c1"]["familywise_alpha"] = 0.10
    _write_amendment_and_reissue_evidence(root, amendment)
    _fail(root)


def test_v044_rejects_v041_handoff_convention_inventory_substitution(tmp_path):
    """Mutating v041's own already-pinned handoff (the PLUS_ONE/TIE_RULE
    anchor) must fail via the pre-existing protected-hash check, regardless
    of what the amendment claims."""
    root = _tree(tmp_path)
    target = root / v044.previous.HANDOFF_RELPATH
    doc = json.loads(target.read_bytes())
    doc["numerical_conventions_selected_convention_inventory"] = [
        x.replace("NONSTRICT", "STRICT") for x in doc["numerical_conventions_selected_convention_inventory"]
    ]
    target.write_bytes(context.canonical_json_bytes(doc))
    _fail(root)


# --- eligibility / winner-selection ordering, structural trace checks -----

def test_v044_rejects_eligibility_ordering_drift(tmp_path):
    root = _tree(tmp_path)
    amendment = copy.deepcopy(v044.AMENDMENT_DOCUMENT)
    _trace_entry(amendment, "WINNER_SELECTION")["claimed_value"] = "winner_selected_before_eligibility"
    _trace_entry(amendment, "WINNER_SELECTION")["derived_from"] = []
    _write_amendment_and_reissue_evidence(root, amendment)
    _fail(root)


def test_v044_rejects_orphan_derived_requirement(tmp_path):
    root = _tree(tmp_path)
    amendment = copy.deepcopy(v044.AMENDMENT_DOCUMENT)
    amendment["trace_matrix"] = copy.deepcopy(amendment["trace_matrix"])
    for entry in amendment["trace_matrix"]:
        if entry["requirement_id"] == "FAMILY_MAXIMUM":
            entry["derived_from"] = entry["derived_from"] + ["NONEXISTENT_REQUIREMENT"]
    _write_amendment_and_reissue_evidence(root, amendment)
    _fail(root)


def test_v044_rejects_duplicate_requirement_id(tmp_path):
    root = _tree(tmp_path)
    amendment = copy.deepcopy(v044.AMENDMENT_DOCUMENT)
    amendment["trace_matrix"] = copy.deepcopy(amendment["trace_matrix"]) + [copy.deepcopy(amendment["trace_matrix"][0])]
    _write_amendment_and_reissue_evidence(root, amendment)
    _fail(root)


def test_v044_rejects_prospective_requirement_without_authorization(tmp_path):
    root = _tree(tmp_path)
    amendment = copy.deepcopy(v044.AMENDMENT_DOCUMENT)
    _trace_entry(amendment, "INDEPENDENT_ORACLE")["authorized_by"] = None
    _write_amendment_and_reissue_evidence(root, amendment)
    _fail(root)


def test_v044_rejects_historical_requirement_missing_source_anchor(tmp_path):
    root = _tree(tmp_path)
    amendment = copy.deepcopy(v044.AMENDMENT_DOCUMENT)
    _trace_entry(amendment, "ALPHA")["source_path"] = None
    _write_amendment_and_reissue_evidence(root, amendment)
    _fail(root)


def test_v044_requires_all_negative_family_and_order_permutation_oracle_cases(tmp_path):
    root = _tree(tmp_path)
    amendment = _amendment(root)
    cases = set(_trace_entry(amendment, "INDEPENDENT_ORACLE")["claimed_value"])
    assert {"all_negative_family", "candidate_order_permutation"}.issubset(cases)


def test_v044_rejects_oracle_case_dropped(tmp_path):
    root = _tree(tmp_path)
    amendment = copy.deepcopy(v044.AMENDMENT_DOCUMENT)
    entry = _trace_entry(amendment, "INDEPENDENT_ORACLE")
    entry["claimed_value"] = [x for x in entry["claimed_value"] if x != "all_negative_family"]
    _write_amendment_and_reissue_evidence(root, amendment)
    _fail(root)


# --- structural / predecessor / identity, mirroring v038/v041/v043 pattern -

def test_v044_rejects_predecessor_tamper(tmp_path):
    root = _tree(tmp_path)
    receipt = _receipt(root)
    receipt["predecessor"] = copy.deepcopy(receipt["predecessor"])
    receipt["predecessor"]["sha256"] = "0" * 64
    _write_receipt_and_repoint(root, receipt)
    _fail(root)


def test_v044_rejects_predecessor_pointing_at_rejected_v043(tmp_path):
    root = _tree(tmp_path)
    receipt = _receipt(root)
    receipt["predecessor"] = {
        "path": "docs/control/tasks/RECOVER_OR_RETIRE_CANDIDATE1_V0_FROZEN_INPUT/handoff_v043.json",
        "sha256": "0" * 64,
    }
    _write_receipt_and_repoint(root, receipt)
    _fail(root)


def test_v044_rejects_receipt_index_drift(tmp_path):
    root = _tree(tmp_path)
    receipt = _receipt(root)
    receipt["receipt_index"] = 45
    _write_receipt_and_repoint(root, receipt)
    _fail(root)


def test_v044_rejects_next_action_drift_to_raw_implementation(tmp_path):
    root = _tree(tmp_path)
    receipt = _receipt(root)
    receipt["next_actions"] = ["IMPLEMENT_H001_C1_DIRECTIONALITY_ATOMIC_REPAIR"]
    _write_receipt_and_repoint(root, receipt)
    _fail(root)


@pytest.mark.parametrize("dropped", [
    "EXECUTE_H001",
    "IMPLEMENT_H001_C1_DIRECTIONALITY_ATOMIC_REPAIR_BEFORE_INDEPENDENT_REVIEW",
    "MERGE_H001_C1_DIRECTIONALITY_ATOMIC_REPAIR_CANDIDATE_BEFORE_INDEPENDENT_ADVERSARIAL_REVIEW",
    "TREAT_C1_CANDIDATE_REVIEW_AS_C2_RESOLUTION",
    "AMEND_OR_MODIFY_REJECTED_V043_CANDIDATE_COMMIT_OR_BRANCH",
    "SUBSTITUTE_HISTORICAL_ANCHOR_SOURCE_PATH_OR_HASH_WITHOUT_SEPARATE_SCIENTIFIC_AMENDMENT",
    "ACTIVATE_H001_BEFORE_BOTH_C1_REVIEW_AND_C2_RESOLUTION",
])
def test_v044_rejects_dropped_prohibition(tmp_path, dropped):
    root = _tree(tmp_path)
    receipt = _receipt(root)
    receipt["prohibited_actions"] = [x for x in receipt["prohibited_actions"] if x != dropped]
    _write_receipt_and_repoint(root, receipt)
    _fail(root)


def test_v044_rejects_dropped_c2_blocker(tmp_path):
    root = _tree(tmp_path)
    receipt = _receipt(root)
    receipt["blockers"] = [
        x for x in receipt["blockers"]
        if x != "H001 activation blocked pending resolution of C2 historical funding-provenance availability"
    ]
    _write_receipt_and_repoint(root, receipt)
    _fail(root)


@pytest.mark.parametrize(("field", "value"), [
    ("decomposition_execution_budget", 2),
    ("decomposition_execution_count", 1),
    ("scientific_use_authorized", True),
    ("real_data_execution_requested", True),
    ("live_integration_authorized", True),
])
def test_v044_rejects_safety_drift(tmp_path, field, value):
    root = _tree(tmp_path)
    receipt = _receipt(root)
    receipt["safety_state"] = copy.deepcopy(receipt["safety_state"])
    receipt["safety_state"][field] = value
    _write_receipt_and_repoint(root, receipt)
    _fail(root)


def test_v044_rejects_scope_drift(tmp_path):
    root = _tree(tmp_path)
    receipt = _receipt(root)
    receipt["changed_file_scope"] = copy.deepcopy(receipt["changed_file_scope"])
    receipt["changed_file_scope"][0] = "wrong"
    _write_receipt_and_repoint(root, receipt)
    _fail(root)


def test_v044_rejects_protected_v041_handoff_tamper(tmp_path):
    root = _tree(tmp_path)
    target = root / v044.previous.HANDOFF_RELPATH
    target.write_bytes(target.read_bytes()[:-1] + b" ")
    _fail(root)


def test_v044_rejects_source_mutation_after_binding(tmp_path):
    root = _tree(tmp_path)
    target = root / v044.AMENDMENT_RELPATH
    target.write_bytes(target.read_bytes() + b"\n")
    _fail(root)
