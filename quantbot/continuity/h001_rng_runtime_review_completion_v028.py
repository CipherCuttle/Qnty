"""v028 reviewed-but-not-effective RNG-runtime control-plane transition."""

import hashlib

from . import context as c
from . import h001_rng_runtime_candidate_v027 as previous


PHASE = "candidate1_h001_synthetic_null_calibration_rng_runtime_specification_amendment_review_completed"
NEXT_ACTION = "IMPLEMENT_H001_SYNTHETIC_NULL_CALIBRATION_RNG_RUNTIME_SPECIFICATION_AMENDMENT_ACTIVATION_FOR_INDEPENDENT_REVIEW"
REVIEW_RELPATH = "docs/assurance/reviews/candidate1_h001_synthetic_null_calibration_rng_runtime_specification_amendment_candidate_review_v001.json"
HANDOFF_RELPATH = f"docs/control/tasks/{c.TASK_ID}/handoff_v028.json"
BRANCH = "chore/h001-rng-runtime-review-completion"
BASE_SHA = "5879173f5be7b78fdbffc60127fd833078b91e4d"
REVIEWED_BASE = "31ae06eba2d17132642639a98a83728414dd75aa"
REVIEWED_HEAD = "c7284aa9baae3323eb25de2340d184198221cb92"
MERGED_TREE = "0bf7f6c5e57cd8b68f8ca2e77fa705331944b6f7"
DOCUMENT_SHA = "e52b1a4733024e4255cf771b97765cff19f7f5e59cf824732784a1abd594812f"
V027_SHA = "a1af7929a6f7fa1cd91cb0d0545f6f5ecaf4a4258621f8c6e67e046c0336873f"
V027_POINTER_SHA = "72fcb9480775097528c41737e2e226127b08b9cc6b874c468507cd6efaed0457"
DOMAINS = list(c._H001_RNG_CANDIDATE_DOMAINS)
VERIFICATION_CATEGORIES = [
    "EXACT_PR_BASE_HEAD_AND_ONE_COMMIT_SCOPE", "EXACT_TEN_FILE_SCOPE", "CANDIDATE_SHA256", "V027_RECEIPT_SHA256", "V027_ACTIVE_POINTER_SHA256", "V026_PREDECESSOR_SHA256", "PAYLOAD_KEY_INDEPENDENT_RECONSTRUCTION", "COORDINATE_INJECTIVITY", "NUMPY_PHILOX_COUNTER_REALIZATION", "PHILOX4X64_10_BLOCK_AND_LANE_MAPPING", "EXACT_BOUNDED_INTEGER_MAPPING", "EXACT_RATIONAL_BERNOULLI_1_OVER_63", "RETRY_ISOLATION_AND_FINITE_CAP", "COMPLETE_STATIONARY_BOOTSTRAP_PATHS", "TWO_STRUCTURALLY_INDEPENDENT_DERIVATIONS", "CANDIDATE_VALIDATOR_MUTATION_COVERAGE", "PROTECTED_EVIDENCE_ATTACKER_REFRESH_REJECTION", "CONTINUITY_VERIFICATION", "FULL_REPOSITORY_SUITE", "NO_GIT_OPERATION",
]
# Preserve every independently pinned v027 record in its repository-native
# order.  The v027 receipt is the immediate immutable predecessor, not a
# mutable transition file; the new review record is appended separately.
PROTECTED = {
    c._H001_RNG_CANDIDATE_RELPATH: DOCUMENT_SHA,
    c._H001_RNG_CANDIDATE_HANDOFF_RELPATH: V027_SHA,
    **{path: digest for path, digest in previous.PROTECTED.items() if path != c._H001_RNG_CANDIDATE_RELPATH},
}
CURRENT_FILES = ["quantbot/continuity/context.py", "quantbot/continuity/h001_rng_runtime_review_completion_v028.py", "tests/continuity/test_cross_agent_continuity.py"]
SCOPE = [REVIEW_RELPATH, HANDOFF_RELPATH, c.ACTIVE_TASK_RELPATH, *CURRENT_FILES]
BINDING = {"candidate_path": c._H001_RNG_CANDIDATE_RELPATH, "candidate_sha256": DOCUMENT_SHA, "candidate_created": True, "candidate_reviewed": True, "candidate_review_verdict": "PASS", "candidate_effective": False, "candidate_activated": False, "review_record_path": REVIEW_RELPATH}
DECISIONS = sorted({*[x for x in c._H001_RNG_CANDIDATE_DECISIONS if "PENDING_INDEPENDENT_REVIEW" not in x and x != "H001_RNG_RUNTIME_SPECIFICATION_AMENDMENT_REVIEW=NOT_COMPLETED"], "H001_RNG_RUNTIME_SPECIFICATION_AMENDMENT_REVIEW=PASSED", "H001_RNG_RUNTIME_SPECIFICATION_AMENDMENT_REVIEW_RECORD=RECORDED", "H001_RNG_RUNTIME_SPECIFICATION_AMENDMENT_CANDIDATE_REVIEWED=TRUE", "H001_RNG_RUNTIME_SPECIFICATION_AMENDMENT_EFFECTIVE=FALSE", "H001_RNG_RUNTIME_SPECIFICATION_AMENDMENT_ACTIVATED=FALSE", "H001_RNG_RUNTIME_SPECIFICATION_AMENDMENT_ACTIVATION_TRANSITION=AUTHORIZED_FOR_INDEPENDENT_REVIEW_ONLY"})
BLOCKERS = sorted([x for x in c._H001_RNG_CANDIDATE_BLOCKERS if "candidate requires independent review" not in x] + ["H001 RNG-runtime amendment activation transition requires independent review", "H001 numerical conventions amendment candidate remains blocked pending effective RNG-runtime specification amendment"])
PROHIBITIONS = sorted([x for x in c._H001_RNG_CANDIDATE_PROHIBITIONS if x != "ACTIVATE_H001_SYNTHETIC_NULL_CALIBRATION_RNG_RUNTIME_SPECIFICATION_AMENDMENT_BEFORE_INDEPENDENT_REVIEW"] + ["ACTIVATE_H001_SYNTHETIC_NULL_CALIBRATION_RNG_RUNTIME_SPECIFICATION_AMENDMENT_BEFORE_SEPARATE_ACTIVATION_TRANSITION_IS_REVIEWED_AND_MERGED", "MODIFY_PRIOR_AMENDMENTS_OR_HANDOFF_RECEIPTS_V001_THROUGH_V027"])


def _review_expected():
    return {"review_id": "candidate1-h001-synthetic-null-calibration-rng-runtime-specification-amendment-candidate-review-v001", "document_kind": "qnty_h001_rng_runtime_specification_amendment_candidate_review_record", "schema_version": "0.1.0", "status": "RECORDED_AFTER_INDEPENDENT_EXACT_HEAD_ADVERSARIAL_REVIEW_NOT_EFFECTIVE_NOT_ACTIVATED", "review_kind": "INDEPENDENT_EXACT_HEAD_ADVERSARIAL_REVIEW", "reviewed_pr": 298, "reviewed_base_sha": REVIEWED_BASE, "reviewed_head_sha": REVIEWED_HEAD, "reviewed_commit_count": 1, "reviewed_changed_file_count": 10, "merged_commit_sha": BASE_SHA, "merge_parent_1_sha": REVIEWED_BASE, "merge_parent_2_sha": REVIEWED_HEAD, "merged_tree_sha": MERGED_TREE, "candidate_path": c._H001_RNG_CANDIDATE_RELPATH, "candidate_amendment_id": "candidate1-h001-synthetic-null-calibration-rng-runtime-specification-amendment-v001", "candidate_sha256": DOCUMENT_SHA, "v027_receipt_sha256": V027_SHA, "v027_active_pointer_sha256": V027_POINTER_SHA, "review_verdict": "PASS", "blocker_count": 0, "major_count": 0, "minor_count": 0, "additional_result_determinative_choice_found": False, "reviewed_domains": DOMAINS, "verification_categories": VERIFICATION_CATEGORIES, "review_results": {"kat": "18 passed", "contract_module": "248 passed", "cross_agent_module": "689 passed, 6 skipped", "full_suite": "6840 passed, 6 skipped", "no_git_review_set": "955 passed, 6 skipped"}, "non_effects": ["CANDIDATE_NOT_EFFECTIVE", "CANDIDATE_NOT_ACTIVATED", "CALIBRATION_ENGINE_NOT_IMPLEMENTED", "CALIBRATION_EXECUTION_NOT_AUTHORIZED", "NO_CALIBRATION_RESULTS", "NO_REAL_DATA_ACCESS", "NO_SCIENTIFIC_AUTHORITY", "NO_PAPER_TRADING_AUTHORITY", "NO_LIVE_AUTHORITY", "EDGE_UNPROVEN", "BLOCK_LIVE_INTEGRATION", "REVIEW_RESULTS_NOT_SCIENTIFIC_EVIDENCE"]}


def validate(receipt, root):
    if receipt["receipt_index"] != 28 or receipt["phase"] != PHASE or receipt["source_branch"] != BRANCH or receipt["source_head_commit"] != BASE_SHA:
        c._fail("H001 RNG-runtime review-completion receipt identity or source binding is wrong")
    if receipt["predecessor"] != {"path": c._H001_RNG_CANDIDATE_HANDOFF_RELPATH, "sha256": V027_SHA}:
        c._fail("H001 RNG-runtime review-completion predecessor is wrong")
    for field, expected in (("changed_file_scope", SCOPE), ("next_actions", [NEXT_ACTION]), ("decisions", DECISIONS), ("blockers", BLOCKERS), ("prohibited_actions", PROHIBITIONS), ("rng_runtime_candidate_resolved_inventory", DOMAINS)):
        if receipt[field] != expected or len(receipt[field]) != len(set(receipt[field])):
            c._fail(f"H001 RNG-runtime review-completion {field} drifted")
    if receipt["safety_state"] != dict(c._EXPECTED_SAFETY, real_data_execution_requested=False) or receipt["candidate_binding"] != BINDING:
        c._fail("H001 RNG-runtime review-completion safety or binding drifted")
    if receipt["evidence"] != [{"path": p, "sha256": h} for p, h in PROTECTED.items()] + [{"path": REVIEW_RELPATH, "sha256": hashlib.sha256((root / REVIEW_RELPATH).read_bytes()).hexdigest()}]:
        c._fail("H001 RNG-runtime review-completion evidence is wrong")
    for path, digest in PROTECTED.items():
        if not (root / path).is_file() or hashlib.sha256((root / path).read_bytes()).hexdigest() != digest:
            c._fail(f"H001 RNG-runtime review-completion protected evidence {path!r} hash mismatch")
    if receipt["current_transition_files"] != [{"path": p, "sha256": hashlib.sha256((root / p).read_bytes()).hexdigest()} for p in CURRENT_FILES]:
        c._fail("H001 RNG-runtime review-completion transition files drifted")
    review_raw = (root / REVIEW_RELPATH).read_bytes()
    # Review records historically use a final text newline; their payload must
    # otherwise remain the canonical JSON representation.
    review = c._load_canonical_document(review_raw.rstrip(b"\n"), "H001 RNG-runtime review record")
    if review != _review_expected():
        c._fail("H001 RNG-runtime review record is malformed or does not bind the independently pinned review")
    candidate = c.contracts.load_and_validate_h001_rng_runtime_amendment_candidate((root / c._H001_RNG_CANDIDATE_RELPATH).read_bytes())
    if candidate["effective"] or candidate["activated"] or receipt["candidate_binding"]["candidate_effective"] or receipt["candidate_binding"]["candidate_activated"]:
        c._fail("H001 RNG-runtime review completion must not activate the candidate")
