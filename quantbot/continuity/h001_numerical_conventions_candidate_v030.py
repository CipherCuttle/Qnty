"""v030 review-only numerical-conventions candidate control-plane extension."""

import hashlib

from . import context as c
from . import h001_rng_runtime_activation_v029 as previous


PHASE = "candidate1_h001_synthetic_null_calibration_numerical_conventions_amendment_candidate_review_required"
NEXT_ACTION = "ADVERSARIAL_REVIEW_H001_SYNTHETIC_NULL_CALIBRATION_NUMERICAL_CONVENTIONS_AMENDMENT_CANDIDATE"
RELPATH = "docs/control/amendments/candidate1_h001_synthetic_null_calibration_numerical_conventions_amendment_candidate_v001.json"
HANDOFF_RELPATH = f"docs/control/tasks/{c.TASK_ID}/handoff_v030.json"
BRANCH = "feat/h001-numerical-conventions-amendment-candidate"
BASE_SHA = "c4f7fac9aeccd3e87caa283cc9872bf5793c282e"
DOCUMENT_SHA = "28551aa041aff2985e0023e61516b08f528d93cf72c23c8c3541793f6f61c691"
RNG_ACTIVATION_SHA = "77b27c218670ca427e2f9589dba144731dd456cce56650222ebb37a3d5528c97"
V029_SHA = "4e192e1e13c48395a37984b7ec9e96295c3d1316f221467e8e6ead11d8c9fae1"
FROZEN_SPEC_RELPATH = "docs/assurance/h001_synthetic_null_calibration_spec_freeze_candidate_v001.json"
FROZEN_SPEC_SHA = "04b6ea5b7453fccf4787abb26c230e2a02a77545c741c19f6686df16fc2cb7a2"
GAPS = list(c._H001_NUMERICAL_CONVENTIONS_GOVERNANCE_GAPS)
SELECTED = [
    "HAC-NEWEY-WEST-BARTLETT-1TOVER-T",
    "NULL-CENTER-STATISTIC-AT-OBSERVED-MEAN",
    "STUDENTIZE-RECOMPUTE-BOOTSTRAP-SE",
    "TWO-SIDED-MAXT-PLUS-ONE-NONSTRICT",
    "SYNC-STATIONARY-PATH-BOUND-TO-ACTIVATED-RNG",
]
KAT_REFERENCE_RELPATH = "tests/assurance/test_h001_numerical_conventions_kat_reference_derivation.py"
KAT_INDEPENDENT_RELPATH = "tests/assurance/test_h001_numerical_conventions_kat_independent_derivation.py"
SCOPE = [
    RELPATH,
    HANDOFF_RELPATH,
    c.ACTIVE_TASK_RELPATH,
    "quantbot/continuity/context.py",
    "quantbot/continuity/h001_numerical_conventions_candidate_v030.py",
    "quantbot/assurance/contracts.py",
    "tests/continuity/test_cross_agent_continuity.py",
    "tests/assurance/test_contracts.py",
    KAT_REFERENCE_RELPATH,
    KAT_INDEPENDENT_RELPATH,
]
CURRENT_FILES = [
    "quantbot/continuity/context.py",
    "quantbot/continuity/h001_numerical_conventions_candidate_v030.py",
    "quantbot/assurance/contracts.py",
    "tests/continuity/test_cross_agent_continuity.py",
    "tests/assurance/test_contracts.py",
    KAT_REFERENCE_RELPATH,
    KAT_INDEPENDENT_RELPATH,
]
# Protected historical evidence: the full inherited v029 inventory (its protected
# set plus the reviewed-and-activated RNG activation document), then the v029
# handoff receipt, then this numerical-conventions candidate document. Every
# hash is an independently pinned historical value, never derived from the
# current bytes of the artifact it protects.
PROTECTED = {
    RELPATH: DOCUMENT_SHA,
    **previous.PROTECTED,
    previous.ACTIVATION_RELPATH: RNG_ACTIVATION_SHA,
    previous.HANDOFF_RELPATH: V029_SHA,
}
BLOCKERS = list(c._H001_NUMERICAL_CONVENTIONS_GOVERNANCE_BLOCKERS)
_DECISIONS_REMOVE = {
    "H001_NUMERICAL_CONVENTIONS_AMENDMENT_CANDIDATE=NOT_CREATED",
    "H001_NUMERICAL_CONVENTIONS_AMENDMENT_CANDIDATE_IMPLEMENTATION_ATTEMPT=BLOCKED_BEFORE_CHANGE",
    "H001_NUMERICAL_CONVENTIONS_CANDIDATE_BLOCKER=NONE_RNG_RUNTIME_SPECIFICATION_EFFECTIVE",
    "H001_SYNTHETIC_NULL_CALIBRATION_NUMERICAL_CONVENTIONS=INCOMPLETE_RESULT_DETERMINATIVE",
    "H001_SYNTHETIC_NULL_CALIBRATION_NUMERICAL_CONVENTIONS_AMENDMENT_CANDIDATE=NOT_CREATED",
}
_DECISIONS_ADD = {
    "H001_NUMERICAL_CONVENTIONS_AMENDMENT_CANDIDATE=CREATED_FOR_INDEPENDENT_REVIEW",
    "H001_NUMERICAL_CONVENTIONS_CANDIDATE_BLOCKER=NONE_CANDIDATE_CREATED_PENDING_INDEPENDENT_REVIEW",
    "H001_SYNTHETIC_NULL_CALIBRATION_NUMERICAL_CONVENTIONS=CANDIDATE_RESOLVED_PENDING_INDEPENDENT_REVIEW",
    "H001_SYNTHETIC_NULL_CALIBRATION_NUMERICAL_CONVENTIONS_AMENDMENT_CANDIDATE=CREATED_FOR_INDEPENDENT_REVIEW",
    "H001_SYNTHETIC_NULL_CALIBRATION_NUMERICAL_CONVENTIONS_AMENDMENT_CANDIDATE_SHA256=" + DOCUMENT_SHA,
    "H001_SYNTHETIC_NULL_CALIBRATION_NUMERICAL_CONVENTIONS_AMENDMENT_CANDIDATE_VALUES=LOCKED_FOR_REVIEW",
}
DECISIONS = sorted((set(previous.DECISIONS) - _DECISIONS_REMOVE) | _DECISIONS_ADD)
PROHIBITIONS = sorted({
    *previous.PROHIBITIONS,
    "ACTIVATE_H001_SYNTHETIC_NULL_CALIBRATION_NUMERICAL_CONVENTIONS_AMENDMENT_BEFORE_INDEPENDENT_REVIEW",
    "MAKE_H001_SYNTHETIC_NULL_CALIBRATION_NUMERICAL_CONVENTIONS_SELECTED_OR_EFFECTIVE_BEFORE_REVIEWED_ACTIVATION",
    "MODIFY_H001_SYNTHETIC_NULL_CALIBRATION_NUMERICAL_CONVENTIONS_AMENDMENT_CANDIDATE_VALUES_AFTER_LOCK",
    "MODIFY_PRIOR_AMENDMENTS_OR_HANDOFF_RECEIPTS_V001_THROUGH_V029",
})
BINDING = {
    "candidate_path": RELPATH,
    "candidate_sha256": DOCUMENT_SHA,
    "governance_amendment_path": c._H001_NUMERICAL_CONVENTIONS_GOVERNANCE_AMENDMENT_RELPATH,
    "governance_amendment_sha256": c._H001_NUMERICAL_CONVENTIONS_GOVERNANCE_AMENDMENT_SHA,
    "frozen_spec_path": FROZEN_SPEC_RELPATH,
    "frozen_spec_sha256": FROZEN_SPEC_SHA,
    "activated_rng_candidate_path": previous.BINDING["candidate_path"],
    "activated_rng_candidate_sha256": previous.DOCUMENT_SHA,
    "activated_rng_activation_path": previous.ACTIVATION_RELPATH,
    "activated_rng_activation_sha256": RNG_ACTIVATION_SHA,
    "candidate_created": True,
    "candidate_reviewed": False,
    "candidate_effective": False,
    "candidate_activated": False,
}


def validate(receipt, root):
    if receipt["receipt_index"] != 30 or receipt["phase"] != PHASE or receipt["source_branch"] != BRANCH or receipt["source_head_commit"] != BASE_SHA:
        c._fail("H001 numerical-conventions candidate receipt identity or source binding is wrong")
    if receipt["predecessor"] != {"path": previous.HANDOFF_RELPATH, "sha256": V029_SHA}:
        c._fail("H001 numerical-conventions candidate predecessor is wrong")
    for field, expected in (("changed_file_scope", SCOPE), ("next_actions", [NEXT_ACTION]), ("decisions", DECISIONS), ("blockers", BLOCKERS), ("prohibited_actions", PROHIBITIONS), ("numerical_convention_gap_inventory", GAPS), ("numerical_conventions_selected_convention_inventory", SELECTED)):
        if receipt[field] != expected or len(receipt[field]) != len(set(receipt[field])):
            c._fail(f"H001 numerical-conventions candidate {field} drifted")
    if receipt["safety_state"] != dict(c._EXPECTED_SAFETY, real_data_execution_requested=False) or receipt["candidate_binding"] != BINDING:
        c._fail("H001 numerical-conventions candidate safety or binding drifted")
    if receipt["evidence"] != [{"path": p, "sha256": h} for p, h in PROTECTED.items()]:
        c._fail("H001 numerical-conventions candidate protected evidence list must be exact, unique, and ordered")
    for path, digest in PROTECTED.items():
        if not (root / path).is_file() or hashlib.sha256((root / path).read_bytes()).hexdigest() != digest:
            c._fail(f"H001 numerical-conventions candidate protected evidence {path!r} hash mismatch")
    expected_current = [{"path": p, "sha256": hashlib.sha256((root / p).read_bytes()).hexdigest()} for p in CURRENT_FILES]
    if receipt["current_transition_files"] != expected_current:
        c._fail("H001 numerical-conventions candidate current-transition files must be exact, unique, and hash-bound")
    raw = (root / RELPATH).read_bytes()
    if hashlib.sha256(raw).hexdigest() != DOCUMENT_SHA:
        c._fail("H001 numerical-conventions candidate document hash is wrong")
    candidate = c.contracts.load_and_validate_h001_numerical_conventions_amendment_candidate(raw)
    if candidate["effective"] or candidate["activated"] or candidate["candidate_review_completed"]:
        c._fail("H001 numerical-conventions candidate claims an effect it must not have")
    if candidate["ordered_gap_inventory"] != GAPS or [row["selected_convention_id"] for row in candidate["implementability_matrix"]] != SELECTED:
        c._fail("H001 numerical-conventions candidate gap or selected-convention inventory drifted")
