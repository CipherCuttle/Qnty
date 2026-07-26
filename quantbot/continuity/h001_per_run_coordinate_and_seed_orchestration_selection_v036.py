"""v036 selects one H001 remaining-pipeline component for separate governance.

The selected component remains NOT_IMPLEMENTED.  This transition grants no
implementation, execution, wiring, candidate, review, activation, budget, or
scientific/trading authority.
"""

import hashlib

from . import context as c
from . import h001_synthetic_null_calibration_remaining_execution_pipeline_scope_governance_v035 as previous

PHASE = "candidate1_h001_synthetic_null_calibration_per_run_coordinate_and_seed_orchestration_selected_for_independent_governance"
NEXT_ACTION = "AUTHORIZE_H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION_GOVERNANCE"
GOVERNANCE_RELPATH = "docs/control/amendments/candidate1_h001_synthetic_null_calibration_per_run_coordinate_and_seed_orchestration_selection_governance_v001.json"
HANDOFF_RELPATH = f"docs/control/tasks/{c.TASK_ID}/handoff_v036.json"
BRANCH = "chore/h001-per-run-coordinate-seed-orchestration-selection-v036"
BASE_SHA = "8d79433d96ff6b32bb5af3fa56bb26ad26b0cdb8"
V035_SHA = "e8975ae78a34e8e5c15dfbbc41fddf29355c3603f0ded75e3a54bcaf883f1c88"
SELECTED_COMPONENT_ID = "PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION"
CURRENT_FILES = [
    "quantbot/continuity/context.py",
    "quantbot/continuity/h001_per_run_coordinate_and_seed_orchestration_selection_v036.py",
    "tests/continuity/test_h001_per_run_coordinate_and_seed_orchestration_selection_v036.py",
    "tests/control/governance_baseline.json",
]
PROTECTED = {**previous.PROTECTED, previous.HANDOFF_RELPATH: V035_SHA, previous.GOVERNANCE_RELPATH: "39b261b53b5d12cb7ebb2b2ce43462523658ad1927d4dd5284a1b624fd25d67c"}
SCOPE = [GOVERNANCE_RELPATH, HANDOFF_RELPATH, c.ACTIVE_TASK_RELPATH, *CURRENT_FILES]
BINDING = dict(previous.BINDING)
_DECISIONS_ADD = {
    f"H001_REMAINING_EXECUTION_PIPELINE_COMPONENT_SELECTED_FOR_INDEPENDENT_GOVERNANCE={SELECTED_COMPONENT_ID}",
    "H001_REMAINING_EXECUTION_PIPELINE_SELECTED_COMPONENT_COUNT=1",
    "H001_REMAINING_EXECUTION_PIPELINE_SELECTED_COMPONENT_IMPLEMENTATION=NOT_AUTHORIZED",
    "H001_REMAINING_EXECUTION_PIPELINE_SELECTED_COMPONENT_EXECUTION=NOT_AUTHORIZED",
}
DECISIONS = sorted({*previous.DECISIONS, *_DECISIONS_ADD})
BLOCKERS = sorted({*previous.BLOCKERS, "H001 per-run coordinate and seed orchestration requires its own governance transition before any candidate or implementation"})
PROHIBITIONS = sorted({
    *previous.PROHIBITIONS,
    "MODIFY_PRIOR_AMENDMENTS_OR_HANDOFF_RECEIPTS_V001_THROUGH_V035",
    "IMPLEMENT_H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION",
    "EXECUTE_H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION",
    "TREAT_H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION_SELECTION_AS_IMPLEMENTATION_OR_EXECUTION_AUTHORIZATION",
})


def selection_doc_expected() -> dict:
    inventory = previous.governance_doc_expected()["pipeline_component_inventory"]
    selected = [item for item in inventory if item["component_id"] == SELECTED_COMPONENT_ID]
    return {
        "allowed_actions": [
            "RECORD_EXACTLY_ONE_H001_REMAINING_EXECUTION_PIPELINE_COMPONENT_SELECTION",
            "PREPARE_SEPARATE_INDEPENDENT_GOVERNANCE_FOR_THE_SELECTED_COMPONENT_ONLY",
        ],
        "amendment_id": "candidate1-h001-synthetic-null-calibration-per-run-coordinate-and-seed-orchestration-selection-governance-v001",
        "amendment_kind": "qnty_h001_synthetic_null_calibration_remaining_execution_pipeline_component_selection_governance_amendment",
        "authorization_status": "SELECTED_FOR_SEPARATE_INDEPENDENT_GOVERNANCE_ONLY_NO_IMPLEMENTATION_OR_EXECUTION_AUTHORITY",
        "base_main_commit": BASE_SHA,
        "current_phase": PHASE,
        "effective": True,
        "hash_bindings": {
            "predecessor_handoff": {"path": previous.HANDOFF_RELPATH, "sha256": V035_SHA},
            "scope_governance": {"path": previous.GOVERNANCE_RELPATH, "sha256": PROTECTED[previous.GOVERNANCE_RELPATH]},
        },
        "non_effects": [
            "NO_COMPONENT_IMPLEMENTED", "NO_CANDIDATE_CREATED", "NO_REVIEW_COMPLETED", "NO_ACTIVATION", "NO_ENGINE_WIRING",
            "NO_CALIBRATION_EXECUTION", "NO_CALIBRATION_RESULTS", "NO_EXECUTION_BUDGET_CHANGE", "NO_REAL_DATA_ACCESS",
            "NO_SCIENTIFIC_AUTHORITY", "NO_PAPER_TRADING_AUTHORITY", "NO_SHADOW_TRADING_AUTHORITY", "NO_LIVE_AUTHORITY",
            "EDGE_UNPROVEN", "BLOCK_LIVE_INTEGRATION",
        ],
        "pipeline_component_inventory": inventory,
        "selected_component": selected[0],
        "selected_component_count": len(selected),
        "selection_status": "SELECTED_FOR_SEPARATE_INDEPENDENT_GOVERNANCE_ONLY",
        "status": "EFFECTIVE_SINGLE_COMPONENT_SELECTION_NO_IMPLEMENTATION_OR_EXECUTION_AUTHORITY",
        "transition_gates": {
            "execution_authorized": False, "execution_implementation_authorized": False,
            "h001_execution_budget": 0, "h001_execution_count": 0, "live_authorization": False,
            "paper_trade_authorization": False, "real_data_access_authorized": False, "scientific_authorization": False,
            "selected_component_count": len(selected), "selected_component_implementation_authorized": False,
            "selected_component_execution_authorized": False,
        },
    }


def validate(receipt, root):
    if receipt["receipt_index"] != 36 or receipt["phase"] != PHASE or receipt["source_branch"] != BRANCH or receipt["source_head_commit"] != BASE_SHA:
        c._fail("H001 per-run coordinate/seed selection receipt identity or source binding is wrong")
    if receipt["predecessor"] != {"path": previous.HANDOFF_RELPATH, "sha256": V035_SHA}:
        c._fail("H001 per-run coordinate/seed selection predecessor is wrong")
    for field, expected in (("changed_file_scope", SCOPE), ("next_actions", [NEXT_ACTION]), ("decisions", DECISIONS), ("blockers", BLOCKERS), ("prohibited_actions", PROHIBITIONS), ("numerical_convention_gap_inventory", previous.NUMERICAL_CONVENTION_GAP_INVENTORY), ("numerical_conventions_selected_convention_inventory", previous.NUMERICAL_CONVENTIONS_SELECTED_CONVENTION_INVENTORY), ("rng_runtime_candidate_resolved_inventory", previous.RNG_RUNTIME_CANDIDATE_RESOLVED_INVENTORY), ("engine_implementation_binding", BINDING)):
        if receipt[field] != expected or len(receipt[field]) != len(set(receipt[field])):
            c._fail(f"H001 per-run coordinate/seed selection {field} drifted")
    if receipt["safety_state"] != dict(c._EXPECTED_SAFETY, real_data_execution_requested=False):
        c._fail("H001 per-run coordinate/seed selection safety state drifted")
    for path, digest in PROTECTED.items():
        if not (root / path).is_file() or hashlib.sha256((root / path).read_bytes()).hexdigest() != digest:
            c._fail(f"H001 per-run coordinate/seed selection protected evidence {path!r} hash mismatch")
    raw = (root / GOVERNANCE_RELPATH).read_bytes()
    if c._load_canonical_document(raw, "H001 per-run coordinate/seed selection document") != selection_doc_expected():
        c._fail("H001 per-run coordinate/seed selection document is malformed")
    expected_evidence = [{"path": p, "sha256": h} for p, h in PROTECTED.items()] + [{"path": GOVERNANCE_RELPATH, "sha256": hashlib.sha256(raw).hexdigest()}]
    if receipt["evidence"] != expected_evidence:
        c._fail("H001 per-run coordinate/seed selection evidence is wrong")
    if receipt["current_transition_files"] != [{"path": p, "sha256": hashlib.sha256((root / p).read_bytes()).hexdigest()} for p in CURRENT_FILES]:
        c._fail("H001 per-run coordinate/seed selection transition files drifted")
