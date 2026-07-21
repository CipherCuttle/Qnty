"""v031 reviewed-but-not-effective numerical-conventions control-plane transition."""

import hashlib

from . import context as c
from . import h001_numerical_conventions_candidate_v030 as previous


PHASE = "candidate1_h001_synthetic_null_calibration_numerical_conventions_amendment_review_completed"
NEXT_ACTION = "IMPLEMENT_H001_SYNTHETIC_NULL_CALIBRATION_NUMERICAL_CONVENTIONS_AMENDMENT_ACTIVATION_FOR_INDEPENDENT_REVIEW"
REVIEW_RELPATH = "docs/assurance/reviews/candidate1_h001_synthetic_null_calibration_numerical_conventions_amendment_candidate_review_v001.json"
HANDOFF_RELPATH = f"docs/control/tasks/{c.TASK_ID}/handoff_v031.json"
BRANCH = "chore/h001-numerical-conventions-review-completion"
BASE_SHA = "887d0da21b21b9394317bb73602b08c43648924f"
REVIEWED_PR = 304
REVIEWED_BASE = "c4f7fac9aeccd3e87caa283cc9872bf5793c282e"
REVIEWED_HEAD = "1b36de9842dcef79115da285c30a502c710e131c"
MERGED_TREE = "2f54309ea0e8c3ef61a915dfabc63ecdf81ad01a"
DOCUMENT_SHA = previous.DOCUMENT_SHA
V030_SHA = "9c545b7fcbdf07aed8ba81d8afe58df6633ab88ba4c208fc08f28bb9d9554e2a"
V030_POINTER_SHA = "f61ab28207a48a6b7c5c6ffb986ddfc2b268c401a442687eda441fcc199229d8"
DOMAINS = list(previous.GAPS)
VERIFICATION_CATEGORIES = [
    "EXACT_PR_BASE_HEAD_TREE_AND_ONE_COMMIT_SCOPE",
    "EXACT_TEN_FILE_SCOPE",
    "CANDIDATE_SHA256",
    "V030_RECEIPT_SHA256",
    "V030_ACTIVE_POINTER_SHA256",
    "CANDIDATE_SCHEMA_VALIDATION",
    "NUMERICAL_SEMANTICS_REVIEW",
    "INDEPENDENT_THIRD_ORACLE_CROSS_CHECK",
    "TWO_STRUCTURALLY_INDEPENDENT_KAT_DERIVATIONS",
    "FIXTURE_DISPATCH_AND_EXPECTED_FIELD_ASSERTION_COVERAGE",
    "ADVERSARIAL_MUTATION_REVIEW",
    "RECEIPT_AND_CONTINUITY_BINDING",
    "AUTHORITY_REVIEW",
    "FULL_REPOSITORY_SUITE",
    "NO_GIT_VERIFICATION",
    "DOCUMENTED_RELEASE_SMOKE_ADJUDICATION",
]
# Preserve every independently pinned v030 record in its repository-native
# order.  The v030 receipt is the immediate immutable predecessor, not a
# mutable transition file; the new review record is appended separately.
PROTECTED = {
    previous.RELPATH: DOCUMENT_SHA,
    previous.HANDOFF_RELPATH: V030_SHA,
    **{path: digest for path, digest in previous.PROTECTED.items() if path != previous.RELPATH},
}
CURRENT_FILES = [
    "quantbot/continuity/context.py",
    "quantbot/continuity/h001_numerical_conventions_review_completion_v031.py",
    "tests/continuity/test_cross_agent_continuity.py",
]
SCOPE = [REVIEW_RELPATH, HANDOFF_RELPATH, c.ACTIVE_TASK_RELPATH, *CURRENT_FILES]
BINDING = {
    "candidate_path": previous.RELPATH,
    "candidate_sha256": DOCUMENT_SHA,
    "candidate_created": True,
    "candidate_reviewed": True,
    "candidate_review_verdict": "PASS",
    "candidate_effective": False,
    "candidate_activated": False,
    "review_record_path": REVIEW_RELPATH,
}
DECISIONS = sorted({
    *[x for x in previous.DECISIONS if "PENDING_INDEPENDENT_REVIEW" not in x and x != "H001_SYNTHETIC_NULL_CALIBRATION_NUMERICAL_CONVENTIONS_AMENDMENT_REVIEW=NOT_COMPLETED"],
    "H001_SYNTHETIC_NULL_CALIBRATION_NUMERICAL_CONVENTIONS_AMENDMENT_REVIEW=PASSED",
    "H001_SYNTHETIC_NULL_CALIBRATION_NUMERICAL_CONVENTIONS_AMENDMENT_REVIEW_RECORD=RECORDED",
    "H001_SYNTHETIC_NULL_CALIBRATION_NUMERICAL_CONVENTIONS_AMENDMENT_CANDIDATE_REVIEWED=TRUE",
    "H001_SYNTHETIC_NULL_CALIBRATION_NUMERICAL_CONVENTIONS_AMENDMENT_ACTIVATED=FALSE",
    "H001_SYNTHETIC_NULL_CALIBRATION_NUMERICAL_CONVENTIONS_AMENDMENT_ACTIVATION_TRANSITION=AUTHORIZED_FOR_INDEPENDENT_REVIEW_ONLY",
    "H001_NUMERICAL_CONVENTIONS_CANDIDATE_BLOCKER=NONE_CANDIDATE_REVIEWED_PENDING_ACTIVATION",
    "H001_SYNTHETIC_NULL_CALIBRATION_NUMERICAL_CONVENTIONS=CANDIDATE_REVIEWED_PENDING_ACTIVATION",
})
BLOCKERS = sorted(
    [
        x
        for x in previous.BLOCKERS
        if x
        not in (
            "H001 numerical conventions amendment candidate requires independent review",
            "H001 synthetic calibration engine implementation remains blocked pending reviewed numerical conventions amendment",
        )
    ]
    + [
        "H001 numerical-conventions amendment activation transition requires independent review",
        "H001 synthetic calibration engine implementation remains blocked pending effective numerical conventions amendment",
    ]
)
PROHIBITIONS = sorted(
    [x for x in previous.PROHIBITIONS if x != "ACTIVATE_H001_SYNTHETIC_NULL_CALIBRATION_NUMERICAL_CONVENTIONS_AMENDMENT_BEFORE_INDEPENDENT_REVIEW"]
    + [
        "ACTIVATE_H001_SYNTHETIC_NULL_CALIBRATION_NUMERICAL_CONVENTIONS_AMENDMENT_BEFORE_SEPARATE_ACTIVATION_TRANSITION_IS_REVIEWED_AND_MERGED",
        "MODIFY_PRIOR_AMENDMENTS_OR_HANDOFF_RECEIPTS_V001_THROUGH_V030",
    ]
)


def _review_expected():
    return {
        "review_id": "candidate1-h001-synthetic-null-calibration-numerical-conventions-amendment-candidate-review-v001",
        "document_kind": "qnty_h001_numerical_conventions_amendment_candidate_review_record",
        "schema_version": "0.1.0",
        "status": "RECORDED_AFTER_INDEPENDENT_EXACT_HEAD_ADVERSARIAL_REVIEW_NOT_EFFECTIVE_NOT_ACTIVATED",
        "review_kind": "INDEPENDENT_EXACT_HEAD_ADVERSARIAL_REVIEW",
        "reviewed_pr": REVIEWED_PR,
        "reviewed_base_sha": REVIEWED_BASE,
        "reviewed_head_sha": REVIEWED_HEAD,
        "reviewed_commit_count": 1,
        "reviewed_changed_file_count": 10,
        "merged_commit_sha": BASE_SHA,
        "merge_parent_1_sha": REVIEWED_BASE,
        "merge_parent_2_sha": REVIEWED_HEAD,
        "merged_tree_sha": MERGED_TREE,
        "candidate_path": previous.RELPATH,
        "candidate_amendment_id": "candidate1-h001-synthetic-null-calibration-numerical-conventions-amendment-v001",
        "candidate_sha256": DOCUMENT_SHA,
        "v030_receipt_sha256": V030_SHA,
        "v030_active_pointer_sha256": V030_POINTER_SHA,
        "review_verdict": "PASS",
        "blocker_count": 0,
        "major_count": 0,
        "minor_count": 0,
        "additional_result_determinative_choice_found": False,
        "reviewed_domains": DOMAINS,
        "verification_categories": VERIFICATION_CATEGORIES,
        "review_results": {
            "numerical_kat": "93 passed",
            "contracts": "281 passed",
            "assurance": "410 passed",
            "continuity": "703 passed, 6 skipped",
            "collection": "6986 collected",
            "full_suite": "6980 passed, 6 skipped",
            "release_smoke": "IMPORT_OK, 6 passed",
            "no_git_review_set": "PASSED",
            "release_smoke_provisional_finding": "WITHDRAWN_AFTER_DOCUMENTED_ENVIRONMENT_ADJUDICATION",
        },
        "non_effects": [
            "CANDIDATE_NOT_EFFECTIVE",
            "CANDIDATE_NOT_ACTIVATED",
            "NUMERICAL_CONVENTIONS_NOT_SELECTED_OR_EFFECTIVE",
            "CALIBRATION_ENGINE_NOT_IMPLEMENTED",
            "CALIBRATION_EXECUTION_NOT_AUTHORIZED",
            "NO_CALIBRATION_RESULTS",
            "NO_REAL_DATA_ACCESS",
            "NO_SCIENTIFIC_AUTHORITY",
            "NO_PAPER_TRADING_AUTHORITY",
            "NO_LIVE_AUTHORITY",
            "EDGE_UNPROVEN",
            "BLOCK_LIVE_INTEGRATION",
            "REVIEW_RESULTS_NOT_SCIENTIFIC_EVIDENCE",
        ],
    }


def validate(receipt, root):
    if receipt["receipt_index"] != 31 or receipt["phase"] != PHASE or receipt["source_branch"] != BRANCH or receipt["source_head_commit"] != BASE_SHA:
        c._fail("H001 numerical-conventions review-completion receipt identity or source binding is wrong")
    if receipt["predecessor"] != {"path": previous.HANDOFF_RELPATH, "sha256": V030_SHA}:
        c._fail("H001 numerical-conventions review-completion predecessor is wrong")
    for field, expected in (
        ("changed_file_scope", SCOPE),
        ("next_actions", [NEXT_ACTION]),
        ("decisions", DECISIONS),
        ("blockers", BLOCKERS),
        ("prohibited_actions", PROHIBITIONS),
        ("numerical_convention_gap_inventory", DOMAINS),
        ("numerical_conventions_selected_convention_inventory", previous.SELECTED),
        ("rng_runtime_candidate_resolved_inventory", previous.previous.DOMAINS),
    ):
        if receipt[field] != expected or len(receipt[field]) != len(set(receipt[field])):
            c._fail(f"H001 numerical-conventions review-completion {field} drifted")
    if receipt["safety_state"] != dict(c._EXPECTED_SAFETY, real_data_execution_requested=False) or receipt["candidate_binding"] != BINDING:
        c._fail("H001 numerical-conventions review-completion safety or binding drifted")
    if receipt["evidence"] != [{"path": p, "sha256": h} for p, h in PROTECTED.items()] + [
        {"path": REVIEW_RELPATH, "sha256": hashlib.sha256((root / REVIEW_RELPATH).read_bytes()).hexdigest()}
    ]:
        c._fail("H001 numerical-conventions review-completion evidence is wrong")
    for path, digest in PROTECTED.items():
        if not (root / path).is_file() or hashlib.sha256((root / path).read_bytes()).hexdigest() != digest:
            c._fail(f"H001 numerical-conventions review-completion protected evidence {path!r} hash mismatch")
    if receipt["current_transition_files"] != [{"path": p, "sha256": hashlib.sha256((root / p).read_bytes()).hexdigest()} for p in CURRENT_FILES]:
        c._fail("H001 numerical-conventions review-completion transition files drifted")
    review_raw = (root / REVIEW_RELPATH).read_bytes()
    review = c._load_canonical_document(review_raw, "H001 numerical-conventions review record")
    if review != _review_expected():
        c._fail("H001 numerical-conventions review record is malformed or does not bind the independently pinned review")
    candidate = c.contracts.load_and_validate_h001_numerical_conventions_amendment_candidate((root / previous.RELPATH).read_bytes())
    if candidate["effective"] or candidate["activated"] or receipt["candidate_binding"]["candidate_effective"] or receipt["candidate_binding"]["candidate_activated"]:
        c._fail("H001 numerical-conventions review completion must not activate the candidate")
