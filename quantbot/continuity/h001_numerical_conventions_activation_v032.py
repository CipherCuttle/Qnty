"""v032 proposed effective numerical-conventions control-plane activation transition."""

import hashlib

from . import context as c
from . import h001_numerical_conventions_review_completion_v031 as previous


PHASE = "candidate1_h001_synthetic_null_calibration_numerical_conventions_amendment_effective"
NEXT_ACTION = "IMPLEMENT_H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION_ENGINE_FOR_INDEPENDENT_REVIEW"
ACTIVATION_RELPATH = "docs/control/amendments/candidate1_h001_synthetic_null_calibration_numerical_conventions_amendment_activation_v001.json"
HANDOFF_RELPATH = f"docs/control/tasks/{c.TASK_ID}/handoff_v032.json"
BRANCH = "feat/h001-numerical-conventions-amendment-activation"
BASE_SHA = "1ffd46cd8b906d6886281becfc3b7172581e630c"
DOCUMENT_SHA = previous.DOCUMENT_SHA
REVIEW_SHA = "38f52ef4b118ac9e6c43023a92d3d8f1dfff7ca0d110b38c5f0d7962a611fceb"
V031_SHA = "bf790c2b8a63794b5870bc739648e82cbb4614ea73aff916da1198d18d7c5386"
DOMAINS = list(previous.DOMAINS)
SELECTED = list(previous.previous.SELECTED)
PR305_MERGE_PARENT_1 = previous.BASE_SHA
PR305_MERGE_PARENT_2 = "20a4ae293cb335434902a8dd9f6e6fc25657d2ac"
PR305_MERGED_TREE = "b8746eed78309ab7d16868e85cafd01a74fff82b"
CURRENT_FILES = [
    "quantbot/continuity/context.py",
    "quantbot/continuity/h001_numerical_conventions_activation_v032.py",
    "tests/continuity/test_cross_agent_continuity.py",
]
# Protected historical evidence: the full inherited v031 inventory (which already
# recursively carries the candidate, the RNG-runtime candidate/activation, and
# every earlier handoff receipt) plus the numerical-conventions review record and
# the v031 handoff receipt itself. Every hash is an independently pinned
# historical value, never derived from the current bytes of the artifact it
# protects.
PROTECTED = {**previous.PROTECTED, previous.REVIEW_RELPATH: REVIEW_SHA, previous.HANDOFF_RELPATH: V031_SHA}
SCOPE = [ACTIVATION_RELPATH, HANDOFF_RELPATH, c.ACTIVE_TASK_RELPATH, *CURRENT_FILES]
BINDING = {
    "candidate_path": previous.previous.RELPATH,
    "candidate_amendment_id": "candidate1-h001-synthetic-null-calibration-numerical-conventions-amendment-v001",
    "candidate_sha256": DOCUMENT_SHA,
    "candidate_created": True,
    "candidate_reviewed": True,
    "candidate_review_verdict": "PASS",
    "candidate_effective": True,
    "candidate_activated": True,
    "review_record_path": previous.REVIEW_RELPATH,
    "review_record_sha256": REVIEW_SHA,
    "activation_scope": "H001_SYNTHETIC_NULL_CALIBRATION_NUMERICAL_CONVENTIONS_ONLY",
}
_DECISIONS_REMOVE = {
    "H001_SYNTHETIC_NULL_CALIBRATION_NUMERICAL_CONVENTIONS_AMENDMENT_ACTIVATED=FALSE",
    "H001_SYNTHETIC_NULL_CALIBRATION_NUMERICAL_CONVENTIONS_AMENDMENT_ACTIVATION_TRANSITION=AUTHORIZED_FOR_INDEPENDENT_REVIEW_ONLY",
    "H001_SYNTHETIC_NULL_CALIBRATION_NUMERICAL_CONVENTIONS_EFFECTIVE=FALSE",
    "H001_SYNTHETIC_NULL_CALIBRATION_NUMERICAL_CONVENTIONS_SELECTED=FALSE",
    "H001_NUMERICAL_CONVENTIONS_EFFECTIVE=FALSE",
    "H001_NUMERICAL_CONVENTIONS_SELECTED=FALSE",
    "H001_NUMERICAL_CONVENTIONS_CANDIDATE_BLOCKER=NONE_CANDIDATE_REVIEWED_PENDING_ACTIVATION",
    "H001_SYNTHETIC_NULL_CALIBRATION_NUMERICAL_CONVENTIONS=CANDIDATE_REVIEWED_PENDING_ACTIVATION",
    "H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION_IMPLEMENTATION_BLOCKER=PENDING_REVIEWED_NUMERICAL_CONVENTIONS_AMENDMENT",
}
_DECISIONS_ADD = {
    "H001_SYNTHETIC_NULL_CALIBRATION_NUMERICAL_CONVENTIONS_AMENDMENT_ACTIVATED=TRUE",
    "H001_SYNTHETIC_NULL_CALIBRATION_NUMERICAL_CONVENTIONS_AMENDMENT_ACTIVATION_TRANSITION=EFFECTIVE_AFTER_INDEPENDENT_REVIEW_AND_MERGE",
    "H001_SYNTHETIC_NULL_CALIBRATION_NUMERICAL_CONVENTIONS_EFFECTIVE=TRUE",
    "H001_SYNTHETIC_NULL_CALIBRATION_NUMERICAL_CONVENTIONS_SELECTED=TRUE",
    "H001_NUMERICAL_CONVENTIONS_EFFECTIVE=TRUE",
    "H001_NUMERICAL_CONVENTIONS_SELECTED=TRUE",
    "H001_NUMERICAL_CONVENTIONS_CANDIDATE_BLOCKER=NONE_NUMERICAL_CONVENTIONS_EFFECTIVE",
    "H001_SYNTHETIC_NULL_CALIBRATION_NUMERICAL_CONVENTIONS=EFFECTIVE_AND_ACTIVATED",
    "H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION_IMPLEMENTATION_BLOCKER=NONE_NUMERICAL_CONVENTIONS_EFFECTIVE",
}
DECISIONS = sorted({*[x for x in previous.DECISIONS if x not in _DECISIONS_REMOVE], *_DECISIONS_ADD})
BLOCKERS = sorted(
    x
    for x in previous.BLOCKERS
    if x
    not in (
        "H001 numerical-conventions amendment activation transition requires independent review",
        "H001 synthetic calibration engine implementation remains blocked pending effective numerical conventions amendment",
    )
)
PROHIBITIONS = sorted(
    {
        *[
            x
            for x in previous.PROHIBITIONS
            if x
            not in (
                "MAKE_H001_SYNTHETIC_NULL_CALIBRATION_NUMERICAL_CONVENTIONS_EFFECTIVE",
                "MAKE_H001_SYNTHETIC_NULL_CALIBRATION_NUMERICAL_CONVENTIONS_SELECTED_OR_EFFECTIVE_BEFORE_REVIEWED_ACTIVATION",
                "IMPLEMENT_H001_SYNTHETIC_NULL_CALIBRATION_ENGINE",
            )
        ],
        "MODIFY_PRIOR_AMENDMENTS_OR_HANDOFF_RECEIPTS_V001_THROUGH_V031",
    }
)


def _activation_expected():
    return {
        "schema_version": "0.1.0",
        "document_id": "candidate1-h001-synthetic-null-calibration-numerical-conventions-amendment-activation-v001",
        "amendment_id": "candidate1-h001-synthetic-null-calibration-numerical-conventions-amendment-activation-v001",
        "document_kind": "qnty_h001_numerical_conventions_amendment_activation_amendment",
        "amendment_kind": "qnty_h001_numerical_conventions_amendment_activation_amendment",
        "status": "ACTIVATED_AFTER_INDEPENDENT_REVIEW",
        "effective": True,
        "activated": True,
        "activation_scope": "H001_SYNTHETIC_NULL_CALIBRATION_NUMERICAL_CONVENTIONS_ONLY",
        "governed_h001_protocol_id": "real_btc_h001_funding_crowding_reversal_falsification_v0",
        "effective_candidate": {
            "path": previous.previous.RELPATH,
            "amendment_id": BINDING["candidate_amendment_id"],
            "sha256": DOCUMENT_SHA,
            "source_status": "CANDIDATE_REVIEWED_PASS_NOT_EFFECTIVE_NOT_ACTIVATED",
        },
        "review_record": {"path": previous.REVIEW_RELPATH, "sha256": REVIEW_SHA, "verdict": "PASS"},
        "review_history": {
            "pr_304_reviewed_base": previous.REVIEWED_BASE,
            "pr_304_reviewed_head": previous.REVIEWED_HEAD,
            "pr_304_merge_commit": previous.BASE_SHA,
            "pr_304_merged_tree": previous.MERGED_TREE,
            "pr_305_reviewed_base": previous.BASE_SHA,
            "pr_305_reviewed_head": PR305_MERGE_PARENT_2,
            "pr_305_merge_commit": BASE_SHA,
            "pr_305_merge_parent_1": PR305_MERGE_PARENT_1,
            "pr_305_merge_parent_2": PR305_MERGE_PARENT_2,
            "pr_305_merged_tree": PR305_MERGED_TREE,
            "pr_305_blocker_count": 0,
            "pr_305_major_count": 0,
            "pr_305_minor_count": 0,
            "pr_305_verdict": "PASS",
        },
        "activated_domains": DOMAINS,
        "activated_selected_conventions": SELECTED,
        "no_result_determinative_choice_remains_within_numerical_conventions_scope": True,
        "authority_non_effects": {
            "calibration_engine_implemented": False,
            "calibration_execution_authorized": False,
            "calibration_execution_budget": 0,
            "calibration_execution_count": 0,
            "calibration_results_available": False,
            "real_data_access": False,
            "scientific_authorization_granted": False,
            "paper_trade_authorization_granted": False,
            "live_authorization_granted": False,
            "edge_status": "EDGE_UNPROVEN",
            "live_status": "BLOCK_LIVE_INTEGRATION",
        },
        "next_action_after_activation": NEXT_ACTION,
    }


def validate(receipt, root):
    if receipt["receipt_index"] != 32 or receipt["phase"] != PHASE or receipt["source_branch"] != BRANCH or receipt["source_head_commit"] != BASE_SHA:
        c._fail("H001 numerical-conventions activation receipt identity or source binding is wrong")
    if receipt["predecessor"] != {"path": previous.HANDOFF_RELPATH, "sha256": V031_SHA}:
        c._fail("H001 numerical-conventions activation predecessor is wrong")
    for field, expected in (
        ("changed_file_scope", SCOPE),
        ("next_actions", [NEXT_ACTION]),
        ("decisions", DECISIONS),
        ("blockers", BLOCKERS),
        ("prohibited_actions", PROHIBITIONS),
        ("numerical_convention_gap_inventory", DOMAINS),
        ("numerical_conventions_selected_convention_inventory", SELECTED),
        ("rng_runtime_candidate_resolved_inventory", previous.previous.previous.DOMAINS),
    ):
        if receipt[field] != expected or len(receipt[field]) != len(set(receipt[field])):
            c._fail(f"H001 numerical-conventions activation {field} drifted")
    if receipt["safety_state"] != dict(c._EXPECTED_SAFETY, real_data_execution_requested=False) or receipt["candidate_binding"] != BINDING:
        c._fail("H001 numerical-conventions activation safety or binding drifted")
    for path, digest in PROTECTED.items():
        if not (root / path).is_file() or hashlib.sha256((root / path).read_bytes()).hexdigest() != digest:
            c._fail(f"H001 numerical-conventions activation protected evidence {path!r} hash mismatch")
    if receipt["evidence"] != [{"path": p, "sha256": h} for p, h in PROTECTED.items()] + [
        {"path": ACTIVATION_RELPATH, "sha256": hashlib.sha256((root / ACTIVATION_RELPATH).read_bytes()).hexdigest()}
    ]:
        c._fail("H001 numerical-conventions activation evidence is wrong")
    if receipt["current_transition_files"] != [{"path": p, "sha256": hashlib.sha256((root / p).read_bytes()).hexdigest()} for p in CURRENT_FILES]:
        c._fail("H001 numerical-conventions activation transition files drifted")
    activation_raw = (root / ACTIVATION_RELPATH).read_bytes()
    if c._load_canonical_document(activation_raw, "H001 numerical-conventions activation") != _activation_expected():
        c._fail("H001 numerical-conventions activation document is malformed or does not bind the reviewed candidate")
    candidate = c.contracts.load_and_validate_h001_numerical_conventions_amendment_candidate((root / previous.previous.RELPATH).read_bytes())
    if candidate["effective"] or candidate["activated"]:
        c._fail("H001 numerical-conventions activation must not mutate the immutable frozen candidate document")
