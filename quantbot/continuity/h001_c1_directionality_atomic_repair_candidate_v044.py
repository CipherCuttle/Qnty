"""v044 H001 C1-directionality atomic repair candidate, review-required transition.

Successor to the rejected v043 candidate (commit
4e5614bc8faf39003ed947dc55fee57a71402813, independent review verdict
V043_REPAIR_REQUIRED: v043 established internal consistency but not
independent conformity -- its amendment semantics were generated from and
validated against the same module-local AMENDMENT_DOCUMENT, so a coordinated
edit of the constant plus every candidate-local hash would still verify. v043
is retained immutable as historical evidence and is neither amended nor
retroactively approved by this candidate. v043 itself was the decoupled
successor to the earlier rejected v042 (V042_REPAIR_REQUIRED); both are bound
below as historical review evidence.

This transition repairs the traceability defect without re-litigating the
underlying science: every requirement is tagged with an origin_type
(HISTORICAL_SOURCE, DERIVED_REQUIREMENT, PROSPECTIVE_SELF_DERIVED, or
STATE_DERIVED). HISTORICAL_SOURCE requirements are independently re-derived
at validation time from two documents already immutable and hash-pinned
*before this candidate exists* -- the frozen H001 registered design
(docs/experiments/candidate1_h001_real_data_falsification_v0.json, pinned
since deep history) and v041's own handoff receipt (pinned as this
candidate's predecessor) -- never from a constant this module itself defines.
An attacker who edits AMENDMENT_DOCUMENT's claimed historical values and
regenerates every candidate-local hash cannot make validate() pass, because
validate() does not consult AMENDMENT_DOCUMENT's claims to decide what the
historical facts are; it reads the pinned upstream files directly and
compares the *extracted* values against what the amendment claims.

Still implements nothing, executes nothing, wires nothing into
`execute_calibration`, and grants no implementation, execution, activation,
scientific, paper, or live authority. C2 historical funding-provenance
availability remains an independent, unresolved blocker; nothing here may be
read as implying C2 is resolved, and the temporal join / source contracts are
untouched.
"""

import hashlib

from . import context as c
from . import h001_per_run_coordinate_and_seed_orchestration_checkout_path_repair_review_completion_v041 as previous

PHASE = "candidate1_h001_c1_directionality_atomic_repair_candidate_v044_review_required"
NEXT_ACTION = "ADVERSARIAL_REVIEW_H001_C1_DIRECTIONALITY_ATOMIC_REPAIR_CANDIDATE_V044"
HANDOFF_RELPATH = f"docs/control/tasks/{c.TASK_ID}/handoff_v044.json"
AMENDMENT_RELPATH = "docs/control/amendments/candidate1_h001_c1_directionality_atomic_repair_candidate_v044_v001.json"
BRANCH = "chore/h001-c1-directionality-atomic-repair-candidate-v044"
BASE_SHA = "5cf88b93467e18be31158a58d0fc9fdee9a6b492"
V041_SHA = "c90088efd7bc034f52c33c13f9168788e27e34e2fb91b774d8dd576afb0e3c10"

REJECTED_V042_COMMIT = "6f32ad266147b84e2087b896d6726365e42e7b02"
REJECTED_V042_TREE = "fad15ebee045444fe34a6bd804a51f0e796304c0"
REJECTED_V043_COMMIT = "4e5614bc8faf39003ed947dc55fee57a71402813"
REJECTED_V043_TREE = "aed4cd7a846e4a82ce2c694a1123b572b08889b6"
REJECTED_V043_BASE = "5cf88b93467e18be31158a58d0fc9fdee9a6b492"

# --- independent historical anchors ------------------------------------
# These paths/hashes are NOT chosen freely by this candidate: both are
# already present, unchanged, in previous.PROTECTED (inherited from deep
# history), so an attacker cannot move them without also breaking the
# pre-existing, unrelated-to-this-module hash pin those files already carry.
H001_DESIGN_RELPATH = "docs/experiments/candidate1_h001_real_data_falsification_v0.json"
H001_DESIGN_SHA256 = "c6fb8d796559c53188c10e729a2257bc593c7a80526963c97515f747820e2276"
assert previous.PROTECTED[H001_DESIGN_RELPATH] == H001_DESIGN_SHA256, "H001 design anchor drifted from inherited PROTECTED chain"

CURRENT_FILES = [
    "quantbot/continuity/context.py",
    "quantbot/continuity/h001_c1_directionality_atomic_repair_candidate_v044.py",
    "tests/continuity/test_h001_c1_directionality_atomic_repair_candidate_v044.py",
    "tests/control/governance_baseline.json",
]
SCOPE = [AMENDMENT_RELPATH, HANDOFF_RELPATH, c.ACTIVE_TASK_RELPATH, *CURRENT_FILES]
PROTECTED = {**previous.PROTECTED, previous.HANDOFF_RELPATH: V041_SHA}

_ORIGIN_TYPES = {"HISTORICAL_SOURCE", "DERIVED_REQUIREMENT", "PROSPECTIVE_SELF_DERIVED", "STATE_DERIVED"}
_OWNER_AUTHORIZATION = "OWNER_AUTHORIZED_C1_TRACEABILITY_REPAIR_WORKSTREAM_POST_V043_REVIEW"

TRACE_MATRIX = [
    {
        "requirement_id": "REGISTERED_ALTERNATIVE", "origin_type": "HISTORICAL_SOURCE",
        "semantic_claim": "H001 registered alternative is one-sided: mu_i > 0",
        "source_path": H001_DESIGN_RELPATH,
        "source_pointers": ["/validation_test/alternative", "/holdout_test/alternative"],
        "claimed_value": "one-sided mean net return > 0",
        "derived_from": [], "authorized_by": None,
        "future_implementation_surface": "observed/bootstrap statistic sign convention",
        "future_verification_surface": "independent oracle: mixed signs, all positive, all negative family",
    },
    {
        "requirement_id": "FAMILY_SIZE", "origin_type": "HISTORICAL_SOURCE",
        "semantic_claim": "H001 candidate family contains exactly nine registered variants",
        "source_path": H001_DESIGN_RELPATH,
        "source_pointers": ["/validation_test/candidate_family_size", "/variant_family(length)"],
        "claimed_value": 9,
        "derived_from": [], "authorized_by": None,
        "future_implementation_surface": "family maximum computed over exactly nine bootstrap statistics",
        "future_verification_surface": "independent oracle: nine candidates",
    },
    {
        "requirement_id": "ALPHA", "origin_type": "HISTORICAL_SOURCE",
        "semantic_claim": "H001 registered familywise alpha is 0.05",
        "source_path": H001_DESIGN_RELPATH,
        "source_pointers": ["/validation_test/familywise_alpha", "/holdout_test/alpha", "/validation_eligibility/familywise_adjusted_p_lte"],
        "claimed_value": 0.05,
        "derived_from": [], "authorized_by": None,
        "future_implementation_surface": "rejection threshold applied to adjusted p-values",
        "future_verification_surface": "independent oracle: known exceedance counts at alpha=0.05",
    },
    {
        "requirement_id": "OBSERVED_STATISTIC_DIRECTION", "origin_type": "DERIVED_REQUIREMENT",
        "semantic_claim": "observed statistic must be the signed HAC-studentized t_i, not |t_i|",
        "source_path": None, "source_pointers": [], "claimed_value": "signed_HAC_studentized_t_i",
        "derived_from": ["REGISTERED_ALTERNATIVE"],
        "derivation_rule": "a one-sided alternative mu_i>0 cannot be tested by a sign-blind absolute statistic without discarding the direction the hypothesis itself asserts",
        "authorized_by": None,
        "future_implementation_surface": "compute_observed_statistics caller / sign handling",
        "future_verification_surface": "independent oracle: positive/negative asymmetry, strongly negative member",
    },
    {
        "requirement_id": "BOOTSTRAP_STATISTIC_DIRECTION", "origin_type": "DERIVED_REQUIREMENT",
        "semantic_claim": "bootstrap statistic must be signed t*_{j,b}, not |t*_{j,b}|",
        "source_path": None, "source_pointers": [], "claimed_value": "signed_HAC_studentized_tstar_j_b",
        "derived_from": ["REGISTERED_ALTERNATIVE", "OBSERVED_STATISTIC_DIRECTION"],
        "derivation_rule": "the family maximum must compare like with like; a signed observed statistic against an absolute-valued bootstrap null is not a coherent one-sided test",
        "authorized_by": None,
        "future_implementation_surface": "compute_one_bootstrap_replication",
        "future_verification_surface": "independent oracle: deterministic bootstrap coordinates",
    },
    {
        "requirement_id": "FAMILY_MAXIMUM", "origin_type": "DERIVED_REQUIREMENT",
        "semantic_claim": "family statistic is M*_b = max_j t*_{j,b} (signed maximum), not max_j |t*_{j,b}|",
        "source_path": None, "source_pointers": [], "claimed_value": "max_j_tstar_j_b",
        "derived_from": ["BOOTSTRAP_STATISTIC_DIRECTION", "FAMILY_SIZE"],
        "derivation_rule": "the upper-tail exceedance test requires the family maximum to preserve sign so a single positive candidate cannot be masked by a larger-magnitude negative one",
        "authorized_by": None,
        "future_implementation_surface": "_absmax replacement in the bootstrap replication path",
        "future_verification_surface": "independent oracle: all-negative family, single positive among strongly negative family",
    },
    {
        "requirement_id": "TAIL", "origin_type": "DERIVED_REQUIREMENT",
        "semantic_claim": "exceedance counting is upper-tail only: 1[M*_b >= t_i]",
        "source_path": None, "source_pointers": [], "claimed_value": "upper_tail_only",
        "derived_from": ["REGISTERED_ALTERNATIVE"],
        "derivation_rule": "a one-sided positive alternative implies an upper-tail rejection region",
        "authorized_by": None,
        "future_implementation_surface": "update_exceedance_counts",
        "future_verification_surface": "independent oracle: known exceedance counts",
    },
    {
        "requirement_id": "PLUS_ONE", "origin_type": "HISTORICAL_SOURCE",
        "semantic_claim": "Monte Carlo p-value uses the frozen plus-one numerator/denominator convention",
        "source_path": previous.HANDOFF_RELPATH,
        "source_pointers": ["/numerical_conventions_selected_convention_inventory"],
        "claimed_value": "PLUS-ONE-NONSTRICT",
        "derived_from": [], "authorized_by": None,
        "future_implementation_surface": "finalize_exact_pvalues",
        "future_verification_surface": "independent oracle: known exceedance counts",
    },
    {
        "requirement_id": "TIE_RULE", "origin_type": "HISTORICAL_SOURCE",
        "semantic_claim": "exceedance ties (M*_b == t_i) count as exceedance under the frozen non-strict convention",
        "source_path": previous.HANDOFF_RELPATH,
        "source_pointers": ["/numerical_conventions_selected_convention_inventory"],
        "claimed_value": "NONSTRICT",
        "derived_from": [], "authorized_by": None,
        "future_implementation_surface": "update_exceedance_counts",
        "future_verification_surface": "independent oracle: exact ties",
    },
    {
        "requirement_id": "DEPENDENCE_STRUCTURE", "origin_type": "HISTORICAL_SOURCE",
        "semantic_claim": "synchronous stationary-bootstrap path preserves cross-series dependence",
        "source_path": H001_DESIGN_RELPATH,
        "source_pointers": ["/validation_test/synchronous_resampling"],
        "claimed_value": True,
        "derived_from": [], "authorized_by": None,
        "future_implementation_surface": "shared bootstrap coordinate path (unchanged by C1)",
        "future_verification_surface": "semantic parity test: dependence preserved across signed repair",
    },
    {
        "requirement_id": "STUDENTIZATION", "origin_type": "HISTORICAL_SOURCE",
        "semantic_claim": "HAC studentization uses Newey-West/Bartlett with recomputed bootstrap SE",
        "source_path": previous.HANDOFF_RELPATH,
        "source_pointers": ["/numerical_conventions_selected_convention_inventory"],
        "claimed_value": "HAC-NEWEY-WEST-BARTLETT + STUDENTIZE-RECOMPUTE-BOOTSTRAP-SE",
        "derived_from": [], "authorized_by": None,
        "future_implementation_surface": "hac_mean/hac_gamma/hac_omega2/hac_se/stud (unchanged by C1)",
        "future_verification_surface": "semantic parity test: studentization unaffected by sign repair",
    },
    {
        "requirement_id": "ELIGIBILITY", "origin_type": "HISTORICAL_SOURCE",
        "semantic_claim": "validation eligibility gate is registered and unaffected by the C1 repair",
        "source_path": H001_DESIGN_RELPATH,
        "source_pointers": ["/validation_eligibility"],
        "claimed_value": "validation_eligibility object present",
        "derived_from": [], "authorized_by": None,
        "future_implementation_surface": "eligibility check consuming the repaired p-value (logic unchanged)",
        "future_verification_surface": "parity test: eligibility gate unaffected by directionality repair",
    },
    {
        "requirement_id": "WINNER_SELECTION", "origin_type": "DERIVED_REQUIREMENT",
        "semantic_claim": "winner selection may run only over the eligible subset; the registered none_eligible_classification proves selection is gated by eligibility",
        "source_path": None, "source_pointers": [], "claimed_value": "eligible_only_selection",
        "derived_from": ["ELIGIBILITY"],
        "derivation_rule": "validation_eligibility.none_eligible_classification=H001_FAILED_VALIDATION only makes sense if no selection occurs before eligibility is evaluated",
        "authorized_by": None,
        "future_implementation_surface": "validation_selection consumer (logic unchanged by C1)",
        "future_verification_surface": "parity test: winner-before-eligibility ordering forbidden",
    },
    {
        "requirement_id": "ATOMIC_REPAIR", "origin_type": "PROSPECTIVE_SELF_DERIVED",
        "semantic_claim": "the future C1 implementation must land as one semantically atomic reviewed unit across every bound surface; no authoritative mixed-semantic intermediate state",
        "source_path": None, "source_pointers": [], "claimed_value": "single_atomic_reviewed_unit",
        "derived_from": [], "authorized_by": _OWNER_AUTHORIZATION,
        "future_implementation_surface": "engine + tests + fixtures + fingerprints landed together",
        "future_verification_surface": "review gate: reject any partial-surface intermediate state",
    },
    {
        "requirement_id": "KATS", "origin_type": "PROSPECTIVE_SELF_DERIVED",
        "semantic_claim": "known-answer tests for the signed engine must exist and must not be generated by the engine under test",
        "source_path": None, "source_pointers": [], "claimed_value": "independent_kats_required",
        "derived_from": [], "authorized_by": _OWNER_AUTHORIZATION,
        "future_implementation_surface": "tests/experiment/test_h001_null_calibration_engine.py successors",
        "future_verification_surface": "independent oracle cross-check",
    },
    {
        "requirement_id": "FIXTURES", "origin_type": "PROSPECTIVE_SELF_DERIVED",
        "semantic_claim": "absolute-max fixtures/reference vectors must be regenerated for signed semantics, not reused",
        "source_path": None, "source_pointers": [], "claimed_value": "regeneration_required",
        "derived_from": [], "authorized_by": _OWNER_AUTHORIZATION,
        "future_implementation_surface": "engine KAT fixtures currently encoding absmax semantics",
        "future_verification_surface": "fixture regeneration diff review",
    },
    {
        "requirement_id": "FINGERPRINTS", "origin_type": "PROSPECTIVE_SELF_DERIVED",
        "semantic_claim": "result fingerprints/bindings dependent on changed engine bytes must be regenerated, not carried forward stale",
        "source_path": None, "source_pointers": [], "claimed_value": "regeneration_required",
        "derived_from": [], "authorized_by": _OWNER_AUTHORIZATION,
        "future_implementation_surface": "engine_implementation_binding successor fields",
        "future_verification_surface": "fingerprint/binding parity review",
    },
    {
        "requirement_id": "PARITY_TESTS", "origin_type": "PROSPECTIVE_SELF_DERIVED",
        "semantic_claim": "eligibility, winner-selection, holdout-gate, and document/validator semantic parity tests are required for the atomic repair",
        "source_path": None, "source_pointers": [], "claimed_value": "parity_tests_required",
        "derived_from": [], "authorized_by": _OWNER_AUTHORIZATION,
        "future_implementation_surface": "cross-artifact semantic parity suite",
        "future_verification_surface": "review gate: parity suite present and passing",
    },
    {
        "requirement_id": "INDEPENDENT_ORACLE", "origin_type": "PROSPECTIVE_SELF_DERIVED",
        "semantic_claim": "future implementation must be checked against an oracle not generated by the engine under test, covering at minimum eleven microcases",
        "source_path": None, "source_pointers": [], "claimed_value": [
            "one_candidate", "nine_candidates", "all_positive", "mixed_signs",
            "strongly_negative_member", "all_negative_family", "exact_ties", "zero_statistic",
            "deterministic_bootstrap_coordinates", "known_exceedance_counts", "candidate_order_permutation",
        ],
        "derived_from": [], "authorized_by": _OWNER_AUTHORIZATION,
        "future_implementation_surface": "independent oracle harness",
        "future_verification_surface": "oracle-vs-engine cross-check, not implemented in this candidate",
    },
    {
        "requirement_id": "C2_INDEPENDENT_BLOCKER", "origin_type": "STATE_DERIVED",
        "semantic_claim": "C2 historical funding-provenance availability remains independently blocked and unaffected by C1 candidate acceptance",
        "source_path": None, "source_pointers": [], "claimed_value": "BLOCKED_PENDING_VALIDATION",
        "derived_from": [], "authorized_by": None,
        "future_implementation_surface": "n/a -- explicitly out of scope of this candidate",
        "future_verification_surface": "runtime check: c2_status fields pinned false, C2 blocker string present",
    },
    {
        "requirement_id": "AUTHORITY_STATE", "origin_type": "STATE_DERIVED",
        "semantic_claim": "H001 calibration execution budget/count remain 0/0; the generic decomposition budget/count (0/1, unconsumed) is a separate authority domain and does not authorize H001",
        "source_path": None, "source_pointers": [], "claimed_value": "h001_execution_budget=0,h001_execution_count=0",
        "derived_from": [], "authorized_by": None,
        "future_implementation_surface": "n/a",
        "future_verification_surface": "runtime check: safety_state pinned, authorization_state all-false",
    },
]

_REQUIRED_TRACE_IDS = {
    "REGISTERED_ALTERNATIVE", "FAMILY_SIZE", "ALPHA", "OBSERVED_STATISTIC_DIRECTION",
    "BOOTSTRAP_STATISTIC_DIRECTION", "FAMILY_MAXIMUM", "TAIL", "PLUS_ONE", "TIE_RULE",
    "DEPENDENCE_STRUCTURE", "STUDENTIZATION", "ELIGIBILITY", "WINNER_SELECTION",
    "ATOMIC_REPAIR", "KATS", "FIXTURES", "FINGERPRINTS", "PARITY_TESTS",
    "INDEPENDENT_ORACLE", "C2_INDEPENDENT_BLOCKER", "AUTHORITY_STATE",
}
_CONTRADICTION_MARKERS = ("abs", "absolute", "two-sided", "two_sided", "symmetric", "TWO-SIDED")
_SIGNED_REQUIREMENT_IDS = {"OBSERVED_STATISTIC_DIRECTION", "BOOTSTRAP_STATISTIC_DIRECTION", "FAMILY_MAXIMUM", "TAIL"}


def _validate_trace_matrix_structure(matrix):
    ids = [entry["requirement_id"] for entry in matrix]
    if len(ids) != len(set(ids)):
        c._fail("H001 C1 trace matrix has duplicate requirement_id (duplicate semantic owner)")
    id_set = set(ids)
    if not _REQUIRED_TRACE_IDS.issubset(id_set):
        c._fail("H001 C1 trace matrix does not cover the required minimum requirement set")
    for entry in matrix:
        origin = entry["origin_type"]
        if origin not in _ORIGIN_TYPES:
            c._fail(f"H001 C1 trace matrix entry {entry['requirement_id']!r} has invalid origin_type")
        for dep in entry["derived_from"]:
            if dep not in id_set:
                c._fail(f"H001 C1 trace matrix entry {entry['requirement_id']!r} has orphan derived_from reference {dep!r}")
        if origin == "DERIVED_REQUIREMENT" and not entry["derived_from"]:
            c._fail(f"H001 C1 trace matrix DERIVED_REQUIREMENT {entry['requirement_id']!r} has no parent requirement")
        if origin != "DERIVED_REQUIREMENT" and entry["derived_from"]:
            c._fail(f"H001 C1 trace matrix non-derived entry {entry['requirement_id']!r} must not carry derived_from")
        if origin == "PROSPECTIVE_SELF_DERIVED" and not entry["authorized_by"]:
            c._fail(f"H001 C1 trace matrix PROSPECTIVE_SELF_DERIVED {entry['requirement_id']!r} has no authorization binding")
        if origin != "PROSPECTIVE_SELF_DERIVED" and entry["authorized_by"]:
            c._fail(f"H001 C1 trace matrix non-prospective entry {entry['requirement_id']!r} must not carry authorized_by")
        if origin == "HISTORICAL_SOURCE" and (not entry["source_path"] or not entry["source_pointers"]):
            c._fail(f"H001 C1 trace matrix HISTORICAL_SOURCE {entry['requirement_id']!r} is missing a source anchor")
        if origin != "HISTORICAL_SOURCE" and entry["source_path"]:
            c._fail(f"H001 C1 trace matrix non-historical entry {entry['requirement_id']!r} must not carry a source_path")
    for entry in matrix:
        if entry["requirement_id"] in _SIGNED_REQUIREMENT_IDS:
            claim_text = str(entry["claimed_value"]).lower() + str(entry["semantic_claim"]).lower()
            for marker in _CONTRADICTION_MARKERS:
                if marker.lower() in claim_text:
                    c._fail(f"H001 C1 trace matrix entry {entry['requirement_id']!r} contradicts the signed-directionality requirement")


def _extract_historical_anchors(root):
    """Independently re-derive every HISTORICAL_SOURCE fact from the pinned
    upstream documents. Never reads AMENDMENT_DOCUMENT or any candidate-local
    constant to decide what the historical facts are."""
    design_path = root / H001_DESIGN_RELPATH
    if not design_path.is_file():
        c._fail("H001 C1 traceability candidate historical design source is missing")
    design_raw = design_path.read_bytes()
    if hashlib.sha256(design_raw).hexdigest() != H001_DESIGN_SHA256:
        c._fail("H001 C1 traceability candidate historical design source hash drifted from the pinned anchor")
    design = c._load_canonical_document(design_raw, "H001 registered design (historical anchor)")

    handoff_path = root / previous.HANDOFF_RELPATH
    if not handoff_path.is_file():
        c._fail("H001 C1 traceability candidate historical v041 handoff is missing")
    handoff_raw = handoff_path.read_bytes()
    if hashlib.sha256(handoff_raw).hexdigest() != V041_SHA:
        c._fail("H001 C1 traceability candidate historical v041 handoff hash drifted from the pinned anchor")
    handoff = c._load_canonical_document(handoff_raw, "H001 v041 handoff (historical anchor)")

    try:
        alpha_occurrences = {
            design["validation_test"]["familywise_alpha"],
            design["holdout_test"]["alpha"],
            design["validation_eligibility"]["familywise_adjusted_p_lte"],
        }
        family_occurrences = {design["validation_test"]["candidate_family_size"], len(design["variant_family"])}
        alternative_occurrences = {design["validation_test"]["alternative"], design["holdout_test"]["alternative"]}
        synchronous_resampling = design["validation_test"]["synchronous_resampling"]
        eligibility_present = bool(design["validation_eligibility"])
        none_eligible_classification = design["validation_eligibility"]["none_eligible_classification"]
        conventions = handoff["numerical_conventions_selected_convention_inventory"]
    except (KeyError, TypeError):
        c._fail("H001 C1 traceability candidate historical anchor field missing from pinned source")

    if len(alpha_occurrences) != 1:
        c._fail("H001 C1 traceability candidate historical alpha occurrences disagree across independent fields")
    if len(family_occurrences) != 1:
        c._fail("H001 C1 traceability candidate historical family-size occurrences disagree across independent fields")
    if len(alternative_occurrences) != 1:
        c._fail("H001 C1 traceability candidate historical alternative occurrences disagree across independent fields")
    alternative = next(iter(alternative_occurrences))
    if "one-sided" not in alternative or "> 0" not in alternative:
        c._fail("H001 C1 traceability candidate historical alternative is not registered positive one-sided")
    if synchronous_resampling is not True:
        c._fail("H001 C1 traceability candidate historical synchronous_resampling flag is not true")
    if none_eligible_classification != "H001_FAILED_VALIDATION":
        c._fail("H001 C1 traceability candidate historical none_eligible_classification drifted")

    two_sided_entries = [x for x in conventions if x.startswith("TWO-SIDED-MAXT-")]
    if len(two_sided_entries) != 1:
        c._fail("H001 C1 traceability candidate historical TWO-SIDED-MAXT convention entry missing or ambiguous")
    current_maxt_convention = two_sided_entries[0]
    if not current_maxt_convention.endswith("-PLUS-ONE-NONSTRICT"):
        c._fail("H001 C1 traceability candidate historical plus-one/non-strict convention suffix missing")
    if "STUDENTIZE-RECOMPUTE-BOOTSTRAP-SE" not in conventions:
        c._fail("H001 C1 traceability candidate historical studentization convention missing")
    if not any(entry.startswith("HAC-NEWEY-WEST-BARTLETT") for entry in conventions):
        c._fail("H001 C1 traceability candidate historical HAC convention missing")
    if not any(entry.startswith("SYNC-") for entry in conventions):
        c._fail("H001 C1 traceability candidate historical synchronous-dependence convention missing")

    return {
        "alpha": next(iter(alpha_occurrences)),
        "family_size": next(iter(family_occurrences)),
        "alternative": alternative,
        "synchronous_resampling": synchronous_resampling,
        "eligibility_present": eligibility_present,
        "current_maxt_convention": current_maxt_convention,
    }


def _cross_check_historical_claims(matrix, anchors):
    by_id = {entry["requirement_id"]: entry for entry in matrix}
    if by_id["REGISTERED_ALTERNATIVE"]["claimed_value"] != anchors["alternative"]:
        c._fail("H001 C1 traceability candidate REGISTERED_ALTERNATIVE claim does not match the independently derived historical value")
    if by_id["FAMILY_SIZE"]["claimed_value"] != anchors["family_size"]:
        c._fail("H001 C1 traceability candidate FAMILY_SIZE claim does not match the independently derived historical value")
    if by_id["ALPHA"]["claimed_value"] != anchors["alpha"]:
        c._fail("H001 C1 traceability candidate ALPHA claim does not match the independently derived historical value")
    if by_id["DEPENDENCE_STRUCTURE"]["claimed_value"] != anchors["synchronous_resampling"]:
        c._fail("H001 C1 traceability candidate DEPENDENCE_STRUCTURE claim does not match the independently derived historical value")
    if by_id["ELIGIBILITY"]["claimed_value"] != "validation_eligibility object present" or not anchors["eligibility_present"]:
        c._fail("H001 C1 traceability candidate ELIGIBILITY claim does not match the independently derived historical value")
    if by_id["PLUS_ONE"]["claimed_value"] != "PLUS-ONE-NONSTRICT" or not anchors["current_maxt_convention"].endswith("PLUS-ONE-NONSTRICT"):
        c._fail("H001 C1 traceability candidate PLUS_ONE claim does not match the independently derived historical value")
    if by_id["TIE_RULE"]["claimed_value"] != "NONSTRICT" or not anchors["current_maxt_convention"].endswith("NONSTRICT"):
        c._fail("H001 C1 traceability candidate TIE_RULE claim does not match the independently derived historical value")


_DECISIONS_ADD = {
    "H001_C1_DIRECTIONALITY_ATOMIC_REPAIR_CANDIDATE_V044=CREATED_FOR_INDEPENDENT_REVIEW",
    "H001_C1_DIRECTIONALITY_ATOMIC_REPAIR_CANDIDATE_V044_VALUES=LOCKED_FOR_REVIEW",
    "H001_C1_DIRECTIONALITY_ATOMIC_REPAIR_REVIEW_V044=REQUIRED",
    "H001_C1_DIRECTIONALITY_ATOMIC_REPAIR_IMPLEMENTED=FALSE",
    "H001_C1_DIRECTIONALITY_ATOMIC_REPAIR_EXECUTED=FALSE",
    "H001_C1_DIRECTIONALITY_ATOMIC_REPAIR_WIRED_INTO_EXECUTE_CALIBRATION=FALSE",
    "H001_C1_DIRECTION_SURVIVED_INDEPENDENT_REVIEW=TRUE",
    "H001_C1_TRACEABILITY_DEFECT_FROM_V043=REPAIRED",
    "H001_C1_HISTORICAL_REQUIREMENTS_INDEPENDENTLY_ANCHORED=TRUE",
    "H001_C1_C2_DECOUPLED=TRUE",
    "H001_C1_ACCEPTANCE_DOES_NOT_IMPLY_C2_ACCEPTANCE=TRUE",
    "H001_C2_HISTORICAL_PROVENANCE_STATUS=BLOCKED_PENDING_VALIDATION",
    "H001_C2_IN_SCOPE_OF_THIS_CANDIDATE=FALSE",
    "H001_TEMPORAL_JOIN_CONTRACT=UNCHANGED",
    "H001_SOURCE_CONTRACT=UNCHANGED",
    "H001_REJECTED_V042_CANDIDATE=RETAINED_IMMUTABLE_NOT_AMENDED",
    "H001_REJECTED_V042_REVIEW_OUTCOME=V042_REPAIR_REQUIRED",
    "H001_REJECTED_V043_CANDIDATE=RETAINED_IMMUTABLE_NOT_AMENDED",
    "H001_REJECTED_V043_REVIEW_OUTCOME=V043_REPAIR_REQUIRED",
    "H001_REJECTED_V043_PRIMARY_DEFECT=CIRCULAR_SELF_VALIDATION",
    "H001_REJECTED_V043_RETROACTIVELY_APPROVED=FALSE",
}
DECISIONS = sorted({*previous.DECISIONS, *_DECISIONS_ADD})

_BLOCKERS_REMOVE = {"H001 activation blocked pending scientific-consistency audit"}
_BLOCKERS_ADD = {
    "H001 activation blocked pending independent review of the C1 directionality atomic repair candidate v044",
    "H001 activation blocked pending resolution of C2 historical funding-provenance availability",
    "H001 C1 directionality atomic repair candidate v044 requires independent adversarial review before any implementation, wiring, or execution",
}
BLOCKERS = sorted({*(x for x in previous.BLOCKERS if x not in _BLOCKERS_REMOVE), *_BLOCKERS_ADD})

PROHIBITIONS = sorted({
    *previous.PROHIBITIONS,
    "MODIFY_PRIOR_AMENDMENTS_OR_HANDOFF_RECEIPTS_V001_THROUGH_V041",
    "AMEND_OR_MODIFY_REJECTED_V042_CANDIDATE_COMMIT_OR_BRANCH",
    "AMEND_OR_MODIFY_REJECTED_V043_CANDIDATE_COMMIT_OR_BRANCH",
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
    "SUBSTITUTE_HISTORICAL_ANCHOR_SOURCE_PATH_OR_HASH_WITHOUT_SEPARATE_SCIENTIFIC_AMENDMENT",
    "TREAT_CANDIDATE_LOCAL_CANONICAL_GENERATION_AS_INDEPENDENT_SCIENTIFIC_VALIDATION",
    "IMPLEMENT_INDEPENDENT_ORACLE_IN_THIS_CANDIDATE",
    "REGENERATE_FIXTURES_IN_THIS_CANDIDATE",
})


def validate(receipt, root):
    if (
        receipt["receipt_index"] != 44
        or receipt["phase"] != PHASE
        or receipt["source_branch"] != BRANCH
        or receipt["source_head_commit"] != BASE_SHA
    ):
        c._fail("H001 C1 traceability repair candidate identity or source binding is wrong")
    if receipt["predecessor"] != {"path": previous.HANDOFF_RELPATH, "sha256": V041_SHA}:
        c._fail("H001 C1 traceability repair candidate predecessor is wrong")
    for field, expected in (
        ("changed_file_scope", SCOPE),
        ("next_actions", [NEXT_ACTION]),
        ("decisions", DECISIONS),
        ("blockers", BLOCKERS),
        ("prohibited_actions", PROHIBITIONS),
    ):
        if receipt[field] != expected or len(receipt[field]) != len(set(receipt[field])):
            c._fail(f"H001 C1 traceability repair candidate {field} drifted")
    if receipt["safety_state"] != dict(c._EXPECTED_SAFETY, real_data_execution_requested=False):
        c._fail("H001 C1 traceability repair candidate safety state drifted")
    for path, digest in PROTECTED.items():
        if not (root / path).is_file() or hashlib.sha256((root / path).read_bytes()).hexdigest() != digest:
            c._fail(f"H001 C1 traceability repair candidate protected evidence {path!r} hash mismatch")

    raw = (root / AMENDMENT_RELPATH).read_bytes()
    amendment = c._load_canonical_document(raw, "H001 C1 traceability repair candidate amendment")
    if amendment != AMENDMENT_DOCUMENT:
        c._fail("H001 C1 traceability repair candidate amendment drifted from AMENDMENT_DOCUMENT")

    matrix = amendment["trace_matrix"]
    _validate_trace_matrix_structure(matrix)
    anchors = _extract_historical_anchors(root)
    _cross_check_historical_claims(matrix, anchors)

    audit = amendment["audit_binding"]
    if audit["p0_count"] != len(audit["p0_findings"]):
        c._fail("H001 C1 traceability repair candidate p0_count is not derived from p0_findings")
    if audit["h001_activated"] or audit["h001_executed"] or audit["real_data_accessed"] or audit["holdout_accessed"] or audit["repository_modified"]:
        c._fail("H001 C1 traceability repair candidate audit_binding claims authority or access it does not have")

    c2 = amendment["c2_status"]
    if c2["in_scope_of_this_candidate"] is not False or c2["resolution_implied_by_c1_candidate"] is not False:
        c._fail("H001 C1 traceability repair candidate must not claim or imply C2 resolution")
    if c2["temporal_join_contract_modified"] is not False or c2["source_contract_modified"] is not False:
        c._fail("H001 C1 traceability repair candidate must not modify the temporal join or source contracts")
    if c2["third_party_provenance_source_adopted"] is not False:
        c._fail("H001 C1 traceability repair candidate must not adopt a third-party provenance source")

    v042_binding = amendment["rejected_v042_binding"]
    if v042_binding["rejected_commit"] != REJECTED_V042_COMMIT or v042_binding["rejected_tree"] != REJECTED_V042_TREE:
        c._fail("H001 C1 traceability repair candidate rejected-v042 binding identity drifted")
    if v042_binding["retroactively_approved"] is not False or v042_binding["amended_or_modified"] is not False:
        c._fail("H001 C1 traceability repair candidate must not amend or retroactively approve rejected v042")

    v043_binding = amendment["rejected_v043_binding"]
    if v043_binding["rejected_commit"] != REJECTED_V043_COMMIT or v043_binding["rejected_tree"] != REJECTED_V043_TREE:
        c._fail("H001 C1 traceability repair candidate rejected-v043 binding identity drifted")
    if v043_binding["retroactively_approved"] is not False or v043_binding["amended_or_modified"] is not False:
        c._fail("H001 C1 traceability repair candidate must not amend or retroactively approve rejected v043")
    if v043_binding["primary_defect"] != "CIRCULAR_SELF_VALIDATION" or v043_binding["review_outcome"] != "V043_REPAIR_REQUIRED":
        c._fail("H001 C1 traceability repair candidate rejected-v043 review-outcome binding drifted")

    auth = amendment["authorization_state"]
    if any(
        auth[k]
        for k in (
            "candidate_review_completed", "activation_authorized", "implementation_authorized",
            "execution_authorized", "real_data_access_authorized", "holdout_execution_authorized",
            "scientific_authorized", "paper_trade_authorized", "live_authorized", "wired_into_execute_calibration",
        )
    ) or auth["h001_execution_budget"] != 0 or auth["h001_execution_count"] != 0:
        c._fail("H001 C1 traceability repair candidate authorization_state claims authority it does not have")

    dependent = amendment["dependent_repair_boundary"]
    if dependent["implementation_repair_complete"] is not False or dependent["c1_implementation_authorized_by_this_candidate"] is not False:
        c._fail("H001 C1 traceability repair candidate must not claim implementation authority")
    if dependent["oracle_implemented_by_this_candidate"] is not False or dependent["fixtures_regenerated_by_this_candidate"] is not False:
        c._fail("H001 C1 traceability repair candidate must not claim oracle or fixture work it did not do")

    expected_evidence = [{"path": p, "sha256": h} for p, h in PROTECTED.items()] + [
        {"path": AMENDMENT_RELPATH, "sha256": hashlib.sha256(raw).hexdigest()}
    ]
    if receipt["evidence"] != expected_evidence:
        c._fail("H001 C1 traceability repair candidate evidence is wrong")
    if receipt["current_transition_files"] != [
        {"path": p, "sha256": hashlib.sha256((root / p).read_bytes()).hexdigest()} for p in CURRENT_FILES
    ]:
        c._fail("H001 C1 traceability repair candidate transition files drifted")


AMENDMENT_DOCUMENT = {
    "amendment_id": "candidate1-h001-c1-directionality-atomic-repair-candidate-v044-v001",
    "amendment_kind": "qnty_h001_c1_directionality_atomic_repair_candidate_v044",
    "document_id": "candidate1-h001-c1-directionality-atomic-repair-candidate-v044-v001",
    "document_kind": "qnty_h001_c1_directionality_atomic_repair_candidate_v044",
    "schema_version": "0.1.0",
    "status": "CANDIDATE_REVIEW_REQUIRED_NOT_EFFECTIVE_NOT_IMPLEMENTED",
    "governed_h001_protocol_id": "real_btc_h001_funding_crowding_reversal_falsification_v0",
    "owner_authorized_next_action": "CREATE_H001_C1_TRACEABILITY_REPAIR_CANDIDATE_V044_FOR_REVIEW",
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
    "rejected_v042_binding": {
        "rejected_commit": REJECTED_V042_COMMIT,
        "rejected_tree": REJECTED_V042_TREE,
        "review_outcome": "V042_REPAIR_REQUIRED",
        "retroactively_approved": False,
        "amended_or_modified": False,
    },
    "rejected_v043_binding": {
        "rejected_commit": REJECTED_V043_COMMIT,
        "rejected_tree": REJECTED_V043_TREE,
        "rejected_base": REJECTED_V043_BASE,
        "review_outcome": "V043_REPAIR_REQUIRED",
        "primary_defect": "CIRCULAR_SELF_VALIDATION",
        "defect_description": "amendment semantics generated from and validated against the same module-local AMENDMENT_DOCUMENT constant; coordinated mutation plus full candidate-local hash regeneration still verified",
        "c1_direction_survived_review": True,
        "retroactively_approved": False,
        "amended_or_modified": False,
        "successor_relationship": "TRACEABILITY_CORRECTED_SUCCESSOR_NOT_A_REPAIR_OF_V043",
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
    "trace_matrix": TRACE_MATRIX,
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
        "oracle_may_not_be_engine_under_test": True,
        "minimum_microcases": [
            "one_candidate", "nine_candidates", "all_positive", "mixed_signs",
            "strongly_negative_member", "all_negative_family", "exact_ties", "zero_statistic",
            "deterministic_bootstrap_coordinates", "known_exceedance_counts", "candidate_order_permutation",
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
        "oracle_implemented_by_this_candidate": False,
        "fixtures_regenerated_by_this_candidate": False,
    },
}
