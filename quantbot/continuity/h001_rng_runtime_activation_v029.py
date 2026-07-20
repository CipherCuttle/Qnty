"""v029 proposed effective RNG-runtime control-plane transition."""

import hashlib

from . import context as c
from . import h001_rng_runtime_review_completion_v028 as previous


PHASE = "candidate1_h001_synthetic_null_calibration_rng_runtime_specification_amendment_effective"
NEXT_ACTION = "IMPLEMENT_H001_SYNTHETIC_NULL_CALIBRATION_NUMERICAL_CONVENTIONS_AMENDMENT_CANDIDATE_FOR_INDEPENDENT_REVIEW"
ACTIVATION_RELPATH = "docs/control/amendments/candidate1_h001_synthetic_null_calibration_rng_runtime_specification_amendment_activation_v001.json"
HANDOFF_RELPATH = f"docs/control/tasks/{c.TASK_ID}/handoff_v029.json"
BRANCH = "feat/h001-rng-runtime-amendment-activation"
BASE_SHA = "65b2fe30d63e58b5d06ebcf549e5905913f87073"
DOCUMENT_SHA = "e52b1a4733024e4255cf771b97765cff19f7f5e59cf824732784a1abd594812f"
REVIEW_SHA = "2c718622d76ed30faf8823c681e4d0e9c794e8e5b6dd9624d8cc437afb9758fb"
V028_SHA = "624b8a12861de21fb2fda4a7d2fe25bba2f9e46912531c7f443730bf576cefa8"
DOMAINS = list(c._H001_RNG_CANDIDATE_DOMAINS)
CURRENT_FILES = ["quantbot/continuity/context.py", "quantbot/continuity/h001_rng_runtime_activation_v029.py", "tests/continuity/test_cross_agent_continuity.py"]
PROTECTED = {**previous.PROTECTED, previous.REVIEW_RELPATH: REVIEW_SHA, previous.HANDOFF_RELPATH: V028_SHA}
SCOPE = [ACTIVATION_RELPATH, HANDOFF_RELPATH, c.ACTIVE_TASK_RELPATH, *CURRENT_FILES]
BINDING = {"candidate_path": c._H001_RNG_CANDIDATE_RELPATH, "candidate_amendment_id": "candidate1-h001-synthetic-null-calibration-rng-runtime-specification-amendment-v001", "candidate_sha256": DOCUMENT_SHA, "candidate_created": True, "candidate_reviewed": True, "candidate_review_verdict": "PASS", "candidate_effective": True, "candidate_activated": True, "review_record_path": previous.REVIEW_RELPATH, "review_record_sha256": REVIEW_SHA, "activation_scope": "H001_RNG_RUNTIME_SPECIFICATION_ONLY"}
DECISIONS = sorted({*[x for x in previous.DECISIONS if x not in {"H001_RNG_RUNTIME_SPECIFICATION_AMENDMENT_EFFECTIVE=FALSE", "H001_RNG_RUNTIME_SPECIFICATION_AMENDMENT_ACTIVATED=FALSE", "H001_RNG_RUNTIME_SPECIFICATION_AMENDMENT_ACTIVATION_TRANSITION=AUTHORIZED_FOR_INDEPENDENT_REVIEW_ONLY", "H001_NUMERICAL_CONVENTIONS_CANDIDATE_BLOCKER=PENDING_REVIEWED_RNG_RUNTIME_SPECIFICATION_AMENDMENT"}], "H001_RNG_RUNTIME_SPECIFICATION_AMENDMENT_EFFECTIVE=TRUE", "H001_RNG_RUNTIME_SPECIFICATION_AMENDMENT_ACTIVATED=TRUE", "H001_RNG_RUNTIME_SPECIFICATION_AMENDMENT_ACTIVATION_TRANSITION=EFFECTIVE_AFTER_INDEPENDENT_REVIEW_AND_MERGE", "H001_NUMERICAL_CONVENTIONS_CANDIDATE_BLOCKER=NONE_RNG_RUNTIME_SPECIFICATION_EFFECTIVE"})
BLOCKERS = sorted(set(x for x in previous.BLOCKERS if "RNG-runtime amendment activation transition" not in x and "pending effective RNG-runtime specification amendment" not in x))
PROHIBITIONS = sorted({*[x for x in previous.PROHIBITIONS if x != "MAKE_H001_SYNTHETIC_NULL_CALIBRATION_RNG_RUNTIME_SPECIFICATION_AMENDMENT_EFFECTIVE"], "MODIFY_PRIOR_AMENDMENTS_OR_HANDOFF_RECEIPTS_V001_THROUGH_V028"})


def _activation_expected():
    return {"schema_version": "0.1.0", "document_id": "candidate1-h001-synthetic-null-calibration-rng-runtime-specification-amendment-activation-v001", "amendment_id": "candidate1-h001-synthetic-null-calibration-rng-runtime-specification-amendment-activation-v001", "document_kind": "qnty_h001_rng_runtime_specification_amendment_activation_amendment", "amendment_kind": "qnty_h001_rng_runtime_specification_amendment_activation_amendment", "status": "ACTIVATED_AFTER_INDEPENDENT_REVIEW", "effective": True, "activated": True, "activation_scope": "H001_RNG_RUNTIME_SPECIFICATION_ONLY", "governed_h001_protocol_id": "real_btc_h001_funding_crowding_reversal_falsification_v0", "effective_candidate": {"path": c._H001_RNG_CANDIDATE_RELPATH, "amendment_id": BINDING["candidate_amendment_id"], "sha256": DOCUMENT_SHA, "source_status": "CANDIDATE_REVIEWED_PASS_NOT_EFFECTIVE_NOT_ACTIVATED"}, "review_record": {"path": previous.REVIEW_RELPATH, "sha256": REVIEW_SHA, "verdict": "PASS"}, "review_history": {"pr_298_reviewed_base": previous.REVIEWED_BASE, "pr_298_reviewed_head": previous.REVIEWED_HEAD, "pr_298_merge_commit": previous.BASE_SHA, "pr_299_reviewed_head": "c93423e4819c358a4c64ac045676884ca657fdda", "pr_299_merge_commit": BASE_SHA}, "activated_domains": DOMAINS, "no_result_determinative_choice_remains_within_rng_runtime_scope": True, "authority_non_effects": {"calibration_engine_implemented": False, "calibration_execution_authorized": False, "calibration_execution_budget": 0, "calibration_execution_count": 0, "calibration_results_available": False, "real_data_access": False, "scientific_authorization_granted": False, "paper_trade_authorization_granted": False, "live_authorization_granted": False, "edge_status": "EDGE_UNPROVEN", "live_status": "BLOCK_LIVE_INTEGRATION"}, "next_action_after_activation": NEXT_ACTION}


def validate(receipt, root):
    if receipt["receipt_index"] != 29 or receipt["phase"] != PHASE or receipt["source_branch"] != BRANCH or receipt["source_head_commit"] != BASE_SHA:
        c._fail("H001 RNG-runtime activation receipt identity or source binding is wrong")
    if receipt["predecessor"] != {"path": previous.HANDOFF_RELPATH, "sha256": V028_SHA}:
        c._fail("H001 RNG-runtime activation predecessor is wrong")
    for field, expected in (("changed_file_scope", SCOPE), ("next_actions", [NEXT_ACTION]), ("decisions", DECISIONS), ("blockers", BLOCKERS), ("prohibited_actions", PROHIBITIONS), ("rng_runtime_candidate_resolved_inventory", DOMAINS)):
        if receipt[field] != expected or len(receipt[field]) != len(set(receipt[field])):
            c._fail(f"H001 RNG-runtime activation {field} drifted")
    if receipt["safety_state"] != dict(c._EXPECTED_SAFETY, real_data_execution_requested=False) or receipt["candidate_binding"] != BINDING:
        c._fail("H001 RNG-runtime activation safety or binding drifted")
    for path, digest in PROTECTED.items():
        if not (root / path).is_file() or hashlib.sha256((root / path).read_bytes()).hexdigest() != digest:
            c._fail(f"H001 RNG-runtime activation protected evidence {path!r} hash mismatch")
    if receipt["evidence"] != [{"path": p, "sha256": h} for p, h in PROTECTED.items()] + [{"path": ACTIVATION_RELPATH, "sha256": hashlib.sha256((root / ACTIVATION_RELPATH).read_bytes()).hexdigest()}]:
        c._fail("H001 RNG-runtime activation evidence is wrong")
    if receipt["current_transition_files"] != [{"path": p, "sha256": hashlib.sha256((root / p).read_bytes()).hexdigest()} for p in CURRENT_FILES]:
        c._fail("H001 RNG-runtime activation transition files drifted")
    if c._load_canonical_document((root / ACTIVATION_RELPATH).read_bytes(), "H001 RNG-runtime activation") != _activation_expected():
        c._fail("H001 RNG-runtime activation document is malformed or does not bind the reviewed candidate")
