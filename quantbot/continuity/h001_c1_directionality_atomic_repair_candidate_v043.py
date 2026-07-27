"""v043 H001 C1-directionality atomic repair candidate, review-required transition.

Successor to the rejected v042 joint scientific-contract reconciliation
candidate (commit 6f32ad266147b84e2087b896d6726365e42e7b02, independent review
verdict V042_REPAIR_REQUIRED). v042 is retained immutable as historical
evidence and is neither amended nor retroactively approved by this candidate.

This transition decouples the C1 directionality repair from the still-unresolved
C2 temporal-provenance question: it records only that a positive one-sided,
signed-maxT statistical contract was specified for independent review. It
implements nothing, executes nothing, wires nothing into `execute_calibration`,
and grants no implementation, execution, activation, scientific, paper, or live
authority. C2 historical funding-provenance availability remains an independent,
unresolved blocker; nothing in this transition may be read as implying C2 is
resolved, and the temporal join / source contracts are untouched.
"""

import hashlib

from . import context as c
from . import h001_per_run_coordinate_and_seed_orchestration_checkout_path_repair_review_completion_v041 as previous

PHASE = "candidate1_h001_c1_directionality_atomic_repair_candidate_review_required"
NEXT_ACTION = "ADVERSARIAL_REVIEW_H001_C1_DIRECTIONALITY_ATOMIC_REPAIR_CANDIDATE"
HANDOFF_RELPATH = f"docs/control/tasks/{c.TASK_ID}/handoff_v043.json"
AMENDMENT_RELPATH = "docs/control/amendments/candidate1_h001_c1_directionality_atomic_repair_candidate_v001.json"
BRANCH = "chore/h001-c1-directionality-atomic-repair-candidate-v043"
BASE_SHA = "5cf88b93467e18be31158a58d0fc9fdee9a6b492"
V041_SHA = "c90088efd7bc034f52c33c13f9168788e27e34e2fb91b774d8dd576afb0e3c10"
REJECTED_V042_COMMIT = "6f32ad266147b84e2087b896d6726365e42e7b02"
REJECTED_V042_TREE = "fad15ebee045444fe34a6bd804a51f0e796304c0"

CURRENT_FILES = [
    "quantbot/continuity/context.py",
    "quantbot/continuity/h001_c1_directionality_atomic_repair_candidate_v043.py",
    "tests/continuity/test_h001_c1_directionality_atomic_repair_candidate_v043.py",
    "tests/control/governance_baseline.json",
]
SCOPE = [AMENDMENT_RELPATH, HANDOFF_RELPATH, c.ACTIVE_TASK_RELPATH, *CURRENT_FILES]
PROTECTED = {**previous.PROTECTED, previous.HANDOFF_RELPATH: V041_SHA}

# Single source of truth for the amendment document: the file on disk at
# AMENDMENT_RELPATH must serialize (via c.canonical_json_bytes) to exactly
# this value. validate() below re-derives and checks this, so the two can
# never silently drift apart.
AMENDMENT_DOCUMENT = {
    "amendment_id": "candidate1-h001-c1-directionality-atomic-repair-candidate-v001",
    "amendment_kind": "qnty_h001_c1_directionality_atomic_repair_candidate",
    "document_id": "candidate1-h001-c1-directionality-atomic-repair-candidate-v001",
    "document_kind": "qnty_h001_c1_directionality_atomic_repair_candidate",
    "schema_version": "0.1.0",
    "status": "CANDIDATE_REVIEW_REQUIRED_NOT_EFFECTIVE_NOT_IMPLEMENTED",
    "governed_h001_protocol_id": "real_btc_h001_funding_crowding_reversal_falsification_v0",
    "owner_authorized_next_action": "CREATE_H001_C1_DIRECTIONALITY_ATOMIC_REPAIR_CANDIDATE_FOR_REVIEW",
    "predecessor_handoff": {
        "path": previous.HANDOFF_RELPATH,
        "sha256": V041_SHA,
    },
    "audit_binding": {
        "audited_commit": BASE_SHA,
        "verdict": "C1_REPAIR_REQUIRED_BEFORE_ACTIVATION",
        "p0_findings": ["C1_DIRECTIONALITY_CONTRACT_RECONCILIATION"],
        "p0_count": 1,
        "h001_activated": False,
        "h001_executed": False,
        "real_data_accessed": False,
        "holdout_accessed": False,
        "repository_modified": False,
    },
    "rejected_predecessor_candidate_binding": {
        "rejected_commit": REJECTED_V042_COMMIT,
        "rejected_tree": REJECTED_V042_TREE,
        "review_outcome": "V042_REPAIR_REQUIRED",
        "retroactively_approved": False,
        "amended_or_modified": False,
        "successor_relationship": "DECOUPLED_C1_ONLY_SUCCESSOR_NOT_A_REPAIR_OF_V042",
        "c1_direction_survived_review": True,
        "c2_carried_forward_unresolved": True,
    },
    "c2_status": {
        "in_scope_of_this_candidate": False,
        "historical_provenance_status": "BLOCKED_PENDING_VALIDATION",
        "temporal_join_contract_modified": False,
        "source_contract_modified": False,
        "third_party_provenance_source_adopted": False,
        "resolution_implied_by_c1_candidate": False,
    },
    "proposed_c1": {
        "alternative": "H_A,i: mu_i > 0",
        "family_size": 9,
        "familywise_alpha": 0.05,
        "observed_statistic": "signed_HAC_studentized_t_i",
        "bootstrap_statistic": "signed_HAC_studentized_tstar_j_b",
        "primary_family_statistic": "max_j_tstar_j_b",
        "primary_pvalue": "(1 + sum_b 1[Mstar_b >= t_i]) / (B + 1)",
        "tie_rule": "non_strict_greater_equal_counts_as_exceedance",
        "plus_one_convention": "numerator_and_denominator_both_plus_one_frozen",
        "tail": "upper_tail_only",
        "symmetric_absolute_primary_inference_forbidden": True,
        "negative_statistic_cannot_become_positive_evidence": True,
    },
    "atomic_repair_unit": {
        "surfaces": [
            "observed_signed_hac_statistic",
            "bootstrap_signed_hac_statistic",
            "synchronous_family_maximum",
            "positive_tail_adjusted_pvalue",
            "plus_one_numerator_denominator_convention",
            "non_strict_tie_convention",
            "rejection_rule",
            "validation_eligibility",
            "winner_selection_interaction",
            "kats",
            "fixtures",
            "fingerprints_and_bindings",
            "semantic_parity_tests",
            "relevant_validators_and_document_contract_parity",
        ],
        "single_commit_or_single_unactivated_reviewed_candidate_required": True,
        "forbidden_intermediate_states": [
            "signed_engine_with_absolute_fixtures",
            "signed_maxt_with_two_sided_eligibility",
            "new_pvalues_with_stale_fingerprints",
        ],
    },
    "independent_oracle_requirement": {
        "self_validation_only_forbidden": True,
        "minimum_microcases": [
            "one_candidate", "nine_candidates", "all_positive", "mixed_signs",
            "strongly_negative_member", "exact_ties", "zero_statistic",
            "deterministic_bootstrap_coordinates", "known_exceedance_counts",
        ],
    },
    "fwer_claim_boundary": {
        "registered_target_familywise_alpha": 0.05,
        "implemented_procedure": "signed_single_step_synchronous_maxT_with_registered_studentization_and_monte_carlo_convention",
        "calibration_evidence_required_separately": True,
        "strong_fwer_universal_claim_forbidden": True,
    },
    "authorization_state": {
        "candidate_review_completed": False,
        "activation_authorized": False,
        "implementation_authorized": False,
        "execution_authorized": False,
        "real_data_access_authorized": False,
        "holdout_execution_authorized": False,
        "scientific_authorized": False,
        "paper_trade_authorized": False,
        "live_authorized": False,
        "wired_into_execute_calibration": False,
        "h001_execution_budget": 0,
        "h001_execution_count": 0,
    },
    "dependent_repair_boundary": {
        "implementation_repair_complete": False,
        "c1_implementation_authorized_by_this_candidate": False,
    },
}

_DECISIONS_ADD = {
    "H001_C1_DIRECTIONALITY_ATOMIC_REPAIR_CANDIDATE=CREATED_FOR_INDEPENDENT_REVIEW",
    "H001_C1_DIRECTIONALITY_ATOMIC_REPAIR_CANDIDATE_VALUES=LOCKED_FOR_REVIEW",
    "H001_C1_DIRECTIONALITY_ATOMIC_REPAIR_REVIEW=REQUIRED",
    "H001_C1_DIRECTIONALITY_ATOMIC_REPAIR_IMPLEMENTED=FALSE",
    "H001_C1_DIRECTIONALITY_ATOMIC_REPAIR_EXECUTED=FALSE",
    "H001_C1_DIRECTIONALITY_ATOMIC_REPAIR_WIRED_INTO_EXECUTE_CALIBRATION=FALSE",
    "H001_C1_DIRECTION_SURVIVED_INDEPENDENT_REVIEW=TRUE",
    "H001_C1_C2_DECOUPLED=TRUE",
    "H001_C1_ACCEPTANCE_DOES_NOT_IMPLY_C2_ACCEPTANCE=TRUE",
    "H001_C2_HISTORICAL_PROVENANCE_STATUS=BLOCKED_PENDING_VALIDATION",
    "H001_C2_IN_SCOPE_OF_THIS_CANDIDATE=FALSE",
    "H001_TEMPORAL_JOIN_CONTRACT=UNCHANGED",
    "H001_SOURCE_CONTRACT=UNCHANGED",
    "H001_REJECTED_V042_CANDIDATE=RETAINED_IMMUTABLE_NOT_AMENDED",
    "H001_REJECTED_V042_REVIEW_OUTCOME=V042_REPAIR_REQUIRED",
    "H001_REJECTED_V042_RETROACTIVELY_APPROVED=FALSE",
}
DECISIONS = sorted({*previous.DECISIONS, *_DECISIONS_ADD})

_BLOCKERS_REMOVE = {"H001 activation blocked pending scientific-consistency audit"}
_BLOCKERS_ADD = {
    "H001 activation blocked pending independent review of the C1 directionality atomic repair candidate",
    "H001 activation blocked pending resolution of C2 historical funding-provenance availability",
    "H001 C1 directionality atomic repair candidate requires independent adversarial review before any implementation, wiring, or execution",
}
BLOCKERS = sorted({*(x for x in previous.BLOCKERS if x not in _BLOCKERS_REMOVE), *_BLOCKERS_ADD})

PROHIBITIONS = sorted({
    *previous.PROHIBITIONS,
    "MODIFY_PRIOR_AMENDMENTS_OR_HANDOFF_RECEIPTS_V001_THROUGH_V041",
    "AMEND_OR_MODIFY_REJECTED_V042_CANDIDATE_COMMIT_OR_BRANCH",
    "TREAT_H001_C1_DIRECTIONALITY_ATOMIC_REPAIR_CANDIDATE_AS_IMPLEMENTATION_OR_EXECUTION_AUTHORIZATION",
    "MODIFY_H001_C1_DIRECTIONALITY_ATOMIC_REPAIR_CANDIDATE_VALUES_AFTER_LOCK",
    "MERGE_H001_C1_DIRECTIONALITY_ATOMIC_REPAIR_CANDIDATE_BEFORE_INDEPENDENT_ADVERSARIAL_REVIEW",
    "IMPLEMENT_H001_C1_DIRECTIONALITY_ATOMIC_REPAIR_BEFORE_INDEPENDENT_REVIEW",
    "TREAT_C1_CANDIDATE_REVIEW_AS_C2_RESOLUTION",
    "TREAT_C1_CANDIDATE_AS_C2_HISTORICAL_PROVENANCE_VALIDATION",
    "MODIFY_TEMPORAL_JOIN_CONTRACT_IN_THIS_CANDIDATE",
    "MODIFY_H001_SOURCE_CONTRACT_IN_THIS_CANDIDATE",
    "ADOPT_THIRD_PARTY_PROVENANCE_SOURCE_WITHOUT_SEPARATE_AMENDMENT",
    "ACTIVATE_H001_BEFORE_BOTH_C1_REVIEW_AND_C2_RESOLUTION",
})


def validate(receipt, root):
    if (
        receipt["receipt_index"] != 43
        or receipt["phase"] != PHASE
        or receipt["source_branch"] != BRANCH
        or receipt["source_head_commit"] != BASE_SHA
    ):
        c._fail("H001 C1 directionality atomic repair candidate identity or source binding is wrong")
    if receipt["predecessor"] != {"path": previous.HANDOFF_RELPATH, "sha256": V041_SHA}:
        c._fail("H001 C1 directionality atomic repair candidate predecessor is wrong")
    for field, expected in (
        ("changed_file_scope", SCOPE),
        ("next_actions", [NEXT_ACTION]),
        ("decisions", DECISIONS),
        ("blockers", BLOCKERS),
        ("prohibited_actions", PROHIBITIONS),
    ):
        if receipt[field] != expected or len(receipt[field]) != len(set(receipt[field])):
            c._fail(f"H001 C1 directionality atomic repair candidate {field} drifted")
    if receipt["safety_state"] != dict(c._EXPECTED_SAFETY, real_data_execution_requested=False):
        c._fail("H001 C1 directionality atomic repair candidate safety state drifted")
    for path, digest in PROTECTED.items():
        if not (root / path).is_file() or hashlib.sha256((root / path).read_bytes()).hexdigest() != digest:
            c._fail(f"H001 C1 directionality atomic repair candidate protected evidence {path!r} hash mismatch")

    raw = (root / AMENDMENT_RELPATH).read_bytes()
    amendment = c._load_canonical_document(raw, "H001 C1 directionality atomic repair candidate amendment")
    if amendment != AMENDMENT_DOCUMENT:
        c._fail("H001 C1 directionality atomic repair candidate amendment drifted from AMENDMENT_DOCUMENT")

    audit = amendment["audit_binding"]
    if audit["p0_count"] != len(audit["p0_findings"]):
        c._fail("H001 C1 directionality atomic repair candidate p0_count is not derived from p0_findings")
    if audit["h001_activated"] or audit["h001_executed"] or audit["real_data_accessed"] or audit["holdout_accessed"] or audit["repository_modified"]:
        c._fail("H001 C1 directionality atomic repair candidate audit_binding claims authority or access it does not have")

    c2 = amendment["c2_status"]
    if c2["in_scope_of_this_candidate"] is not False or c2["resolution_implied_by_c1_candidate"] is not False:
        c._fail("H001 C1 directionality atomic repair candidate must not claim or imply C2 resolution")
    if c2["temporal_join_contract_modified"] is not False or c2["source_contract_modified"] is not False:
        c._fail("H001 C1 directionality atomic repair candidate must not modify the temporal join or source contracts")
    if c2["third_party_provenance_source_adopted"] is not False:
        c._fail("H001 C1 directionality atomic repair candidate must not adopt a third-party provenance source")

    rejected = amendment["rejected_predecessor_candidate_binding"]
    if rejected["rejected_commit"] != REJECTED_V042_COMMIT or rejected["rejected_tree"] != REJECTED_V042_TREE:
        c._fail("H001 C1 directionality atomic repair candidate rejected-v042 binding identity drifted")
    if rejected["retroactively_approved"] is not False or rejected["amended_or_modified"] is not False:
        c._fail("H001 C1 directionality atomic repair candidate must not amend or retroactively approve rejected v042")

    auth = amendment["authorization_state"]
    if any(
        auth[k]
        for k in (
            "candidate_review_completed", "activation_authorized", "implementation_authorized",
            "execution_authorized", "real_data_access_authorized", "holdout_execution_authorized",
            "scientific_authorized", "paper_trade_authorized", "live_authorized", "wired_into_execute_calibration",
        )
    ) or auth["h001_execution_budget"] != 0 or auth["h001_execution_count"] != 0:
        c._fail("H001 C1 directionality atomic repair candidate authorization_state claims authority it does not have")

    dependent = amendment["dependent_repair_boundary"]
    if dependent["implementation_repair_complete"] is not False or dependent["c1_implementation_authorized_by_this_candidate"] is not False:
        c._fail("H001 C1 directionality atomic repair candidate must not claim implementation authority")

    expected_evidence = [{"path": p, "sha256": h} for p, h in PROTECTED.items()] + [
        {"path": AMENDMENT_RELPATH, "sha256": hashlib.sha256(raw).hexdigest()}
    ]
    if receipt["evidence"] != expected_evidence:
        c._fail("H001 C1 directionality atomic repair candidate evidence is wrong")
    if receipt["current_transition_files"] != [
        {"path": p, "sha256": hashlib.sha256((root / p).read_bytes()).hexdigest()} for p in CURRENT_FILES
    ]:
        c._fail("H001 C1 directionality atomic repair candidate transition files drifted")
