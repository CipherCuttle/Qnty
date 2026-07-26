"""v037 authorizes one review-required governance candidate, and nothing more."""

import hashlib

from . import context as c
from . import h001_per_run_coordinate_and_seed_orchestration_selection_v036 as previous


PHASE = "candidate1_h001_synthetic_null_calibration_per_run_coordinate_and_seed_orchestration_governance"
NEXT_ACTION = "IMPLEMENT_H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION_CANDIDATE_FOR_INDEPENDENT_REVIEW"
GOVERNANCE_RELPATH = "docs/control/amendments/candidate1_h001_synthetic_null_calibration_per_run_coordinate_and_seed_orchestration_governance_v001.json"
HANDOFF_RELPATH = f"docs/control/tasks/{c.TASK_ID}/handoff_v037.json"
BRANCH = "chore/h001-per-run-coordinate-seed-orchestration-governance-v037"
BASE_SHA = "1a59c5b63217edf7a3c36a27628976978fec6dac"
V036_SHA = "999be45f2716f2e77c4b7e71397d771b4fccd7bee8eddfb6bd22afb5a880b0c9"
SELECTED_COMPONENT_ID = previous.SELECTED_COMPONENT_ID
CURRENT_FILES = [
    "quantbot/continuity/context.py",
    "quantbot/continuity/h001_per_run_coordinate_and_seed_orchestration_governance_v037.py",
    "tests/continuity/test_h001_per_run_coordinate_and_seed_orchestration_governance_v037.py",
    "tests/control/governance_baseline.json",
]
PROTECTED = {
    **previous.PROTECTED,
    previous.HANDOFF_RELPATH: V036_SHA,
    previous.GOVERNANCE_RELPATH: "fef00c14f6e24828c2413d7e8c73de9d16c12d45beaf45a2f1c8697c0fe13776",
}
SCOPE = [GOVERNANCE_RELPATH, HANDOFF_RELPATH, c.ACTIVE_TASK_RELPATH, *CURRENT_FILES]
BINDING = dict(previous.BINDING)
DECISIONS = sorted({
    *previous.DECISIONS,
    f"H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION_GOVERNANCE=AUTHORIZED_CANDIDATE_FOR_INDEPENDENT_REVIEW_ONLY",
    "H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION_CANDIDATE=NOT_CREATED",
    "H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION_REVIEW=NOT_COMPLETED",
})
BLOCKERS = sorted({
    *(x for x in previous.BLOCKERS if x != "H001 per-run coordinate and seed orchestration requires its own governance transition before any candidate or implementation"),
    "H001 per-run coordinate and seed orchestration candidate requires independent review before any implementation",
})
PROHIBITIONS = sorted({
    *previous.PROHIBITIONS,
    "MODIFY_PRIOR_AMENDMENTS_OR_HANDOFF_RECEIPTS_V001_THROUGH_V036",
    "TREAT_H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION_GOVERNANCE_AS_IMPLEMENTATION_OR_EXECUTION_AUTHORIZATION",
    "CREATE_H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION_CANDIDATE_BEFORE_GOVERNANCE_TRANSITION_IS_MERGED",
})


def governance_doc_expected() -> dict:
    selected = previous.selection_doc_expected()["selected_component"]
    return {
        "allowed_actions": ["CREATE_ONE_REVIEW_REQUIRED_GOVERNANCE_CANDIDATE_FOR_THE_SELECTED_COMPONENT_ONLY", "SUBMIT_THAT_CANDIDATE_FOR_INDEPENDENT_REVIEW"],
        "amendment_id": "candidate1-h001-synthetic-null-calibration-per-run-coordinate-and-seed-orchestration-governance-v001",
        "amendment_kind": "qnty_h001_synthetic_null_calibration_remaining_execution_pipeline_component_governance_authorization",
        "authorization_status": "AUTHORIZED_SELECTED_COMPONENT_GOVERNANCE_CANDIDATE_FOR_INDEPENDENT_REVIEW_ONLY",
        "base_main_commit": BASE_SHA,
        "current_phase": PHASE,
        "effective": True,
        "hash_bindings": {"predecessor_handoff": {"path": previous.HANDOFF_RELPATH, "sha256": V036_SHA}, "selection_governance": {"path": previous.GOVERNANCE_RELPATH, "sha256": PROTECTED[previous.GOVERNANCE_RELPATH]}},
        "non_effects": ["NO_COMPONENT_SPECIFICATION", "NO_COMPONENT_IMPLEMENTED", "NO_CANDIDATE_CREATED", "NO_REVIEW_COMPLETED", "NO_ACTIVATION", "NO_ENGINE_WIRING", "NO_CALIBRATION_EXECUTION", "NO_CALIBRATION_RESULTS", "NO_EXECUTION_BUDGET_CHANGE", "NO_REAL_DATA_ACCESS", "NO_SCIENTIFIC_AUTHORITY", "NO_PAPER_TRADING_AUTHORITY", "NO_SHADOW_TRADING_AUTHORITY", "NO_LIVE_AUTHORITY", "EDGE_UNPROVEN", "BLOCK_LIVE_INTEGRATION"],
        "selected_component": selected,
        "selected_component_count": 1,
        "status": "EFFECTIVE_SELECTED_COMPONENT_GOVERNANCE_AUTHORIZATION_ONLY",
        "transition_gates": {"candidate_created": False, "candidate_review_completed": False, "execution_authorized": False, "execution_implementation_authorized": False, "h001_execution_budget": 0, "h001_execution_count": 0, "live_authorization": False, "paper_trade_authorization": False, "real_data_access_authorized": False, "scientific_authorization": False, "selected_component_count": 1, "selected_component_execution_authorized": False, "selected_component_implementation_authorized": False},
    }


def validate(receipt, root):
    if receipt["receipt_index"] != 37 or receipt["phase"] != PHASE or receipt["source_branch"] != BRANCH or receipt["source_head_commit"] != BASE_SHA:
        c._fail("H001 per-run coordinate/seed governance receipt identity or source binding is wrong")
    if receipt["predecessor"] != {"path": previous.HANDOFF_RELPATH, "sha256": V036_SHA}:
        c._fail("H001 per-run coordinate/seed governance predecessor is wrong")
    for field, expected in (("changed_file_scope", SCOPE), ("next_actions", [NEXT_ACTION]), ("decisions", DECISIONS), ("blockers", BLOCKERS), ("prohibited_actions", PROHIBITIONS), ("numerical_convention_gap_inventory", previous.previous.NUMERICAL_CONVENTION_GAP_INVENTORY), ("numerical_conventions_selected_convention_inventory", previous.previous.NUMERICAL_CONVENTIONS_SELECTED_CONVENTION_INVENTORY), ("rng_runtime_candidate_resolved_inventory", previous.previous.RNG_RUNTIME_CANDIDATE_RESOLVED_INVENTORY), ("engine_implementation_binding", BINDING)):
        if receipt[field] != expected or len(receipt[field]) != len(set(receipt[field])):
            c._fail(f"H001 per-run coordinate/seed governance {field} drifted")
    if receipt["safety_state"] != dict(c._EXPECTED_SAFETY, real_data_execution_requested=False):
        c._fail("H001 per-run coordinate/seed governance safety state drifted")
    for path, digest in PROTECTED.items():
        if not (root / path).is_file() or hashlib.sha256((root / path).read_bytes()).hexdigest() != digest:
            c._fail(f"H001 per-run coordinate/seed governance protected evidence {path!r} hash mismatch")
    raw = (root / GOVERNANCE_RELPATH).read_bytes()
    if c._load_canonical_document(raw, "H001 per-run coordinate/seed governance document") != governance_doc_expected():
        c._fail("H001 per-run coordinate/seed governance document is malformed")
    expected_evidence = [{"path": p, "sha256": h} for p, h in PROTECTED.items()] + [{"path": GOVERNANCE_RELPATH, "sha256": hashlib.sha256(raw).hexdigest()}]
    if receipt["evidence"] != expected_evidence:
        c._fail("H001 per-run coordinate/seed governance evidence is wrong")
    if receipt["current_transition_files"] != [{"path": p, "sha256": hashlib.sha256((root / p).read_bytes()).hexdigest()} for p in CURRENT_FILES]:
        c._fail("H001 per-run coordinate/seed governance transition files drifted")
