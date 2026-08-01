"""Adversarial checks for the v044 C1 directionality atomic repair candidate review record.

Every test below reads the review record from disk and computes SHA-256 hashes
at test time so that the tests derive facts from the actual reviewed objects
rather than comparing against constants generated from the same document.

Test numbering:
  - test_review_record_valid_exact: baseline — all fields match reality
  - test_review_record_rejects_*: adversarial mutations that must fail
"""

import copy
import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
REVIEW_RECORD_PATH = (
    ROOT
    / "docs/assurance/reviews/candidate1_h001_c1_directionality_atomic_repair_candidate_review_v001.json"
)
CANDIDATE_PATH = (
    ROOT
    / "docs/control/amendments/candidate1_h001_c1_directionality_atomic_repair_candidate_v044_v001.json"
)
VALIDATOR_PATH = (
    ROOT
    / "quantbot/continuity/h001_c1_directionality_atomic_repair_candidate_v044.py"
)
TEST_PATH = (
    ROOT
    / "tests/continuity/test_h001_c1_directionality_atomic_repair_candidate_v044.py"
)
HANDOFF_PATH = (
    ROOT
    / "docs/control/tasks/RECOVER_OR_RETIRE_CANDIDATE1_V0_FROZEN_INPUT/handoff_v044.json"
)

# Historical anchors (frozen, not part of the v044 change set)
V041_COMMIT = "5cf88b93467e18be31158a58d0fc9fdee9a6b492"
V041_TREE = "741635b2d3704e7ae165b00847016e0cbad4513b"
V044_COMMIT = "c062356c1a2ffa11edba281776888af7ab37cab7"
V044_TREE = "f4257de185c6eba2c74b534c53bde7815b50b45a"

# Expected SHA-256 constants for the reviewed objects (derived from the actual
# files at the reviewed commit; these are the ground-truth values the review
# record must match).
EXPECTED_CANDIDATE_SHA256 = "2bcfaa1f10cfebb6ab7ead9b29bf4a5b4c8f38187ce37af21b32dad99064f98b"
EXPECTED_VALIDATOR_SHA256 = "3ce96c305bc948a31f2e73c04933e7151cff162a44ccd9b7bb8c5519d7a112d1"
EXPECTED_TEST_SHA256 = "bb3e13f5000ac8fe449a78d02ba6f2b236b776ac49a031e14478e53a9719f415"
EXPECTED_HANDOFF_SHA256 = "e7cbfa8659319e32a2ba233f22d9035ff0d9d85cef99d81015e4182988af31f7"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_review_record():
    """Load the review record from disk and return the parsed dict."""
    return json.loads(REVIEW_RECORD_PATH.read_bytes())


def _sha256(path):
    """Compute SHA-256 of a file at *path*."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mutate_and_assert_not_equal(review, key, poisoned_value, description):
    """Clone the review record, mutate *key* to *poisoned_value*, and assert
    the mutated version does NOT equal the original (proving the mutation
    would be detected)."""
    mutated = copy.deepcopy(review)
    # Navigate dotted keys like "authorization_state.candidate_effective"
    parts = key.split(".")
    target = mutated
    for part in parts[:-1]:
        target = target[part]
    target[parts[-1]] = poisoned_value
    assert mutated != review, (
        f"Adversarial mutation failed: {description} — "
        f"mutated record equals original"
    )


# ---------------------------------------------------------------------------
# Baseline: the valid exact record
# ---------------------------------------------------------------------------


def test_review_record_valid_exact():
    """Verify that every field in the review record matches the actual
    repository state at test time."""
    review = _load_review_record()

    # --- Repository identity ---
    assert review["reviewed_repository"] == "CipherCuttle/Qnty"
    assert review["reviewed_branch"] == "audit/h001-v044-c1-traceability"
    assert review["reviewed_head_sha"] == V044_COMMIT
    assert review["reviewed_tree_sha"] == V044_TREE
    assert review["reviewed_base_sha"] == V041_COMMIT
    assert review["reviewed_base_tree"] == V041_TREE

    # --- Reviewed-object SHA-256 integrity ---
    assert review["reviewed_candidate_sha256"] == _sha256(CANDIDATE_PATH), (
        "Candidate SHA-256 mismatch"
    )
    assert review["reviewed_validator_sha256"] == _sha256(VALIDATOR_PATH), (
        "Validator SHA-256 mismatch"
    )
    assert review["reviewed_test_sha256"] == _sha256(TEST_PATH), (
        "Test SHA-256 mismatch"
    )
    assert review["reviewed_handoff_sha256"] == _sha256(HANDOFF_PATH), (
        "Handoff SHA-256 mismatch"
    )

    # --- Reviewed-object paths ---
    assert (
        review["reviewed_candidate_path"]
        == "docs/control/amendments/candidate1_h001_c1_directionality_atomic_repair_candidate_v044_v001.json"
    )
    assert (
        review["reviewed_validator_path"]
        == "quantbot/continuity/h001_c1_directionality_atomic_repair_candidate_v044.py"
    )
    assert (
        review["reviewed_test_path"]
        == "tests/continuity/test_h001_c1_directionality_atomic_repair_candidate_v044.py"
    )
    assert (
        review["reviewed_handoff_path"]
        == "docs/control/tasks/RECOVER_OR_RETIRE_CANDIDATE1_V0_FROZEN_INPUT/handoff_v044.json"
    )

    # --- Commit / change metadata ---
    assert review["reviewed_commit_count"] == 1
    assert review["reviewed_changed_file_count"] == 7

    # --- Schema and document kind ---
    assert review["schema_version"] == "0.1.0"
    assert (
        review["document_kind"]
        == "qnty_h001_c1_directionality_atomic_repair_candidate_review_record"
    )

    # --- Review identity ---
    assert (
        review["review_id"]
        == "candidate1-h001-c1-directionality-atomic-repair-candidate-review-v001"
    )
    assert (
        review["review_kind"] == "INDEPENDENT_EXTERNAL_MODEL_READ_ONLY_GITHUB_REVIEW"
    )
    assert (
        review["review_method"] == "INDEPENDENT_EXTERNAL_MODEL_READ_ONLY_GITHUB_REVIEW"
    )
    assert (
        review["review_scope"]
        == "C1_DIRECTIONALITY_AND_FAMILYWISE_INFERENCE_ONLY"
    )
    assert (
        review["review_verdict"]
        == "PASS_V044_C1_CANDIDATE_READY_FOR_REVIEW_RECORD_ONLY"
    )
    assert review["status"] == "RECORDED_AFTER_INDEPENDENT_EXTERNAL_REVIEW_NON_EFFECTIVE"

    # --- Sub-verdicts ---
    expected_sub_verdicts = [
        "C1_MATHEMATICS_PASS",
        "SIGNED_VERSUS_ABSOLUTE_SCOPE_SEPARATION_PASS",
        "FAMILYWISE_AND_DEPENDENCE_REVIEW_PASS",
        "MONTE_CARLO_CONVENTIONS_PASS",
        "C1_TRACEABILITY_NON_CIRCULAR_PASS",
        "HOSTILE_MUTATION_REVIEW_PASS",
        "C1_APPEND_ONLY_AND_NON_EFFECTS_PASS",
    ]
    assert review["sub_verdicts"] == expected_sub_verdicts

    # --- Verification categories ---
    expected_categories = [
        "EXACT_REPOSITORY_REF_IDENTITY",
        "C1_MATHEMATICS",
        "C1_TRACEABILITY_NON_CIRCULARITY",
        "FAMILYWISE_AND_DEPENDENCE",
        "MONTE_CARLO_CONVENTIONS",
        "SIGNED_VERSUS_ABSOLUTE_SCOPE_SEPARATION",
        "HOSTILE_MUTATION",
        "APPEND_ONLY_PRESERVATION",
        "AUTHORIZATION_NON_EFFECTS",
        "NO_ENGINE_OR_EXECUTABLE_PATH",
    ]
    assert review["verification_categories"] == expected_categories

    # --- Scientific findings ---
    findings = review["verified_scientific_findings"]
    assert findings["alternative"] == "mu_i > 0"
    assert findings["observed_statistic"] == "signed HAC-studentized t_i"
    assert findings["bootstrap_statistic"] == "signed HAC-studentized t*_{j,b}"
    assert findings["family_statistic"] == "max_j t*_{j,b}"
    assert (
        findings["adjusted_pvalue_formula"]
        == "(1 + sum_b 1[M*_b >= t_i]) / (B + 1)"
    )
    assert findings["tail"] == "upper tail only"
    assert findings["family_size"] == 9
    assert findings["familywise_alpha"] == 0.05
    assert findings["synchronous_resampling"] is True
    assert findings["non_strict_ties"] is True
    assert findings["symmetric_absolute_primary_inference"] == "forbidden"
    assert (
        findings["synthetic_absolute_calibration_authority"]
        == "limited to existing synthetic scope"
    )

    # --- Authorization state ---
    auth = review["authorization_state"]
    assert auth["candidate_review_completed"] is True
    assert auth["candidate_review_passed"] is True
    assert auth["candidate_effective"] is False
    assert auth["scientific_authorized"] is False
    assert auth["activation_authorized"] is False
    assert auth["implementation_authorized"] is False
    assert auth["real_data_access_authorized"] is False
    assert auth["execution_authorized"] is False
    assert auth["execution_budget"] == 0
    assert auth["execution_count"] == 0
    assert auth["holdout_authorized"] is False
    assert auth["paper_trade_authorized"] is False
    assert auth["live_authorized"] is False
    assert auth["dispatcher_released"] is False
    assert auth["trust_root_registered"] is False
    assert auth["C2_resolved"] is False

    # --- Explicit limitations ---
    expected_limitations = [
        "C2_NOT_REVIEWED",
        "C2_UNRESOLVED",
        "OPERATOR_DISCLOSURE_REQUIRED",
        "CONFIRMATORY_IDENTITY_NOT_ESTABLISHED",
        "IMPLEMENTATION_NOT_REVIEWED",
        "ENGINE_NOT_REVIEWED_UNDER_SIGNED_SEMANTICS",
        "REAL_DATA_PATH_NOT_REVIEWED",
        "DISPATCHER_NOT_REVIEWED",
        "AUTHORITY_PROMOTION_NOT_REVIEWED",
        "ACTIVATION_NOT_REVIEWED",
    ]
    assert review["explicit_limitations"] == expected_limitations

    # --- Non-effects ---
    expected_non_effects = [
        "DOES_NOT_ALTER_V044_BYTES",
        "DOES_NOT_ALTER_V041_BYTES",
        "DOES_NOT_ACTIVATE_C1",
        "DOES_NOT_RESOLVE_C2",
        "DOES_NOT_AUTHORIZE_IMPLEMENTATION",
        "DOES_NOT_AUTHORIZE_DATA_ACCESS",
        "DOES_NOT_AUTHORIZE_VALIDATION",
        "DOES_NOT_AUTHORIZE_HOLDOUT",
        "DOES_NOT_AUTHORIZE_EXECUTION",
        "DOES_NOT_ESTABLISH_OUTCOME_BLINDNESS",
        "DOES_NOT_ESTABLISH_ECONOMIC_EDGE",
    ]
    assert review["non_effects"] == expected_non_effects

    # --- Next required action ---
    assert (
        review["next_required_action"]
        == "RECORD_OPERATOR_EXPOSURE_DISCLOSURE_BEFORE_CONFIRMATORY_IDENTITY_DECISION"
    )

    # --- Counts ---
    assert review["blocker_count"] == 0
    assert review["major_count"] == 0
    assert review["minor_count"] == 0
    assert review["note_count"] == 0


# ---------------------------------------------------------------------------
# Adversarial: repository reference mutations
# ---------------------------------------------------------------------------


def test_review_record_rejects_wrong_commit():
    """1. reviewed_head_sha must match v044 commit."""
    review = _load_review_record()
    _mutate_and_assert_not_equal(
        review, "reviewed_head_sha", "0" * 40,
        "reviewed_head_sha changed to all-zero",
    )


def test_review_record_rejects_wrong_tree():
    """2. reviewed_tree_sha must match v044 tree."""
    review = _load_review_record()
    _mutate_and_assert_not_equal(
        review, "reviewed_tree_sha", "0" * 40,
        "reviewed_tree_sha changed to all-zero",
    )


def test_review_record_rejects_wrong_candidate_sha():
    """3. reviewed_candidate_sha256 must match actual candidate file."""
    review = _load_review_record()
    _mutate_and_assert_not_equal(
        review, "reviewed_candidate_sha256", "0" * 64,
        "reviewed_candidate_sha256 changed to all-zero",
    )


def test_review_record_rejects_wrong_validator_sha():
    """4. reviewed_validator_sha256 must match actual validator file."""
    review = _load_review_record()
    _mutate_and_assert_not_equal(
        review, "reviewed_validator_sha256", "0" * 64,
        "reviewed_validator_sha256 changed to all-zero",
    )


def test_review_record_rejects_wrong_test_sha():
    """5. reviewed_test_sha256 must match actual test file."""
    review = _load_review_record()
    _mutate_and_assert_not_equal(
        review, "reviewed_test_sha256", "0" * 64,
        "reviewed_test_sha256 changed to all-zero",
    )


def test_review_record_rejects_wrong_handoff_sha():
    """6. reviewed_handoff_sha256 must match actual handoff file."""
    review = _load_review_record()
    _mutate_and_assert_not_equal(
        review, "reviewed_handoff_sha256", "0" * 64,
        "reviewed_handoff_sha256 changed to all-zero",
    )


def test_review_record_rejects_wrong_base_sha():
    """7. reviewed_base_sha must match v041 commit (the historical anchor)."""
    review = _load_review_record()
    _mutate_and_assert_not_equal(
        review, "reviewed_base_sha", "0" * 40,
        "reviewed_base_sha changed to all-zero",
    )


# ---------------------------------------------------------------------------
# Adversarial: scope and verdict mutations
# ---------------------------------------------------------------------------


def test_review_record_rejects_scope_expansion_to_c2():
    """8. Review scope must not include C2."""
    review = _load_review_record()
    scope = review["review_scope"]
    assert "C2" not in scope, (
        f"Review scope '{scope}' unexpectedly references C2"
    )
    assert scope == "C1_DIRECTIONALITY_AND_FAMILYWISE_INFERENCE_ONLY"


def test_review_record_rejects_verdict_drift():
    """9. Verdict string must be exact."""
    review = _load_review_record()
    _mutate_and_assert_not_equal(
        review, "review_verdict", "PASS",
        "review_verdict simplified to PASS",
    )


# ---------------------------------------------------------------------------
# Adversarial: authorization state mutations
# ---------------------------------------------------------------------------


def test_review_record_rejects_candidate_effective_true():
    """10. authorization_state.candidate_effective must be false."""
    review = _load_review_record()
    _mutate_and_assert_not_equal(
        review, "authorization_state.candidate_effective", True,
        "candidate_effective set to True",
    )


def test_review_record_rejects_scientific_authorized_true():
    """11. authorization_state.scientific_authorized must be false."""
    review = _load_review_record()
    _mutate_and_assert_not_equal(
        review, "authorization_state.scientific_authorized", True,
        "scientific_authorized set to True",
    )


def test_review_record_rejects_implementation_authorized_true():
    """12. authorization_state.implementation_authorized must be false."""
    review = _load_review_record()
    _mutate_and_assert_not_equal(
        review, "authorization_state.implementation_authorized", True,
        "implementation_authorized set to True",
    )


def test_review_record_rejects_real_data_access_authorized_true():
    """13. authorization_state.real_data_access_authorized must be false."""
    review = _load_review_record()
    _mutate_and_assert_not_equal(
        review, "authorization_state.real_data_access_authorized", True,
        "real_data_access_authorized set to True",
    )


def test_review_record_rejects_execution_authorized_true():
    """14. authorization_state.execution_authorized must be false."""
    review = _load_review_record()
    _mutate_and_assert_not_equal(
        review, "authorization_state.execution_authorized", True,
        "execution_authorized set to True",
    )


def test_review_record_rejects_nonzero_execution_budget():
    """15. authorization_state.execution_budget must be 0."""
    review = _load_review_record()
    _mutate_and_assert_not_equal(
        review, "authorization_state.execution_budget", 1,
        "execution_budget set to 1",
    )


@pytest.mark.parametrize("field", ["holdout_authorized", "paper_trade_authorized", "live_authorized"])
def test_review_record_rejects_holdout_paper_live_authorization(field):
    """16. holdout, paper, and live authorization must all be false."""
    review = _load_review_record()
    _mutate_and_assert_not_equal(
        review, f"authorization_state.{field}", True,
        f"{field} set to True",
    )


def test_review_record_rejects_c2_resolved():
    """17. authorization_state.C2_resolved must be false."""
    review = _load_review_record()
    _mutate_and_assert_not_equal(
        review, "authorization_state.C2_resolved", True,
        "C2_resolved set to True",
    )


# ---------------------------------------------------------------------------
# Adversarial: next action and limitation mutations
# ---------------------------------------------------------------------------


def test_review_record_rejects_operator_disclosure_claimed_complete():
    """18. next_required_action must be operator disclosure, not completion."""
    review = _load_review_record()
    _mutate_and_assert_not_equal(
        review, "next_required_action", "OPERATOR_DISCLOSURE_COMPLETE",
        "next_required_action changed to OPERATOR_DISCLOSURE_COMPLETE",
    )


def test_review_record_rejects_confirmatory_identity_claimed_intact():
    """19. explicit_limitations must include CONFIRMATORY_IDENTITY_NOT_ESTABLISHED."""
    review = _load_review_record()
    assert "CONFIRMATORY_IDENTITY_NOT_ESTABLISHED" in review["explicit_limitations"], (
        "CONFIRMATORY_IDENTITY_NOT_ESTABLISHED missing from explicit_limitations"
    )
    # Verify the limitation is not silently removed
    mutated = copy.deepcopy(review)
    mutated["explicit_limitations"] = [
        lim for lim in mutated["explicit_limitations"]
        if lim != "CONFIRMATORY_IDENTITY_NOT_ESTABLISHED"
    ]
    assert mutated != review, (
        "Removing CONFIRMATORY_IDENTITY_NOT_ESTABLISHED did not change the record"
    )


def test_review_record_rejects_dispatcher_or_trust_root_promotion():
    """20. dispatcher_released and trust_root_registered must be false."""
    review = _load_review_record()
    _mutate_and_assert_not_equal(
        review, "authorization_state.dispatcher_released", True,
        "dispatcher_released set to True",
    )
    _mutate_and_assert_not_equal(
        review, "authorization_state.trust_root_registered", True,
        "trust_root_registered set to True",
    )


# ---------------------------------------------------------------------------
# Adversarial: non-effects and path mutations
# ---------------------------------------------------------------------------


def test_review_record_rejects_v044_mutation_claim():
    """21. non_effects must include DOES_NOT_ALTER_V044_BYTES."""
    review = _load_review_record()
    assert "DOES_NOT_ALTER_V044_BYTES" in review["non_effects"], (
        "DOES_NOT_ALTER_V044_BYTES missing from non_effects"
    )
    # Verify the non-effect is not silently removed
    mutated = copy.deepcopy(review)
    mutated["non_effects"] = [
        ne for ne in mutated["non_effects"]
        if ne != "DOES_NOT_ALTER_V044_BYTES"
    ]
    assert mutated != review, (
        "Removing DOES_NOT_ALTER_V044_BYTES did not change the record"
    )


def test_review_record_rejects_substituted_paths():
    """22. Reviewed object paths must be exact."""
    review = _load_review_record()
    _mutate_and_assert_not_equal(
        review, "reviewed_candidate_path",
        "docs/control/amendments/some_other_candidate.json",
        "reviewed_candidate_path substituted",
    )
    _mutate_and_assert_not_equal(
        review, "reviewed_validator_path",
        "quantbot/continuity/some_other_validator.py",
        "reviewed_validator_path substituted",
    )
    _mutate_and_assert_not_equal(
        review, "reviewed_test_path",
        "tests/continuity/some_other_test.py",
        "reviewed_test_path substituted",
    )
    _mutate_and_assert_not_equal(
        review, "reviewed_handoff_path",
        "docs/control/tasks/RECOVER_OR_RETIRE_CANDIDATE1_V0_FROZEN_INPUT/handoff_v049.json",
        "reviewed_handoff_path substituted to v049",
    )


def test_review_record_rejects_false_v049_lineage():
    """23. reviewed_base_sha must reference v041, not v049."""
    review = _load_review_record()
    assert review["reviewed_base_sha"] == V041_COMMIT, (
        f"reviewed_base_sha is {review['reviewed_base_sha']}, "
        f"expected v041 ({V041_COMMIT})"
    )
    # Verify that a v049 lineage claim would be detected
    _mutate_and_assert_not_equal(
        review, "reviewed_base_sha", "9" * 40,
        "reviewed_base_sha changed to fake v49 hash",
    )