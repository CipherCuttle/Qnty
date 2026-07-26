"""v038 H001 per-run coordinate and seed orchestration candidate, review-required
transition.

This transition records only that a pure, deterministic caller-side
orchestration module -- deriving and binding a specific run's logical
coordinates and seed material into the already-reviewed engine's pure
functions -- was implemented for independent review. It was not executed,
not wired into `execute_calibration`, and grants no implementation,
execution, wiring, activation, budget, real-data, or scientific/paper/
shadow/live authority.
"""

import hashlib

from . import context as c
from . import h001_per_run_coordinate_and_seed_orchestration_governance_v037 as previous

PHASE = "candidate1_h001_synthetic_null_calibration_per_run_coordinate_and_seed_orchestration_candidate_review_required"
NEXT_ACTION = "ADVERSARIAL_REVIEW_H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION_CANDIDATE"
HANDOFF_RELPATH = f"docs/control/tasks/{c.TASK_ID}/handoff_v038.json"
BRANCH = "feat/h001-per-run-coordinate-seed-orchestration-candidate-v038"
BASE_SHA = "ded505a5ef0bdca8566e7b64b739a4e137057411"
V037_SHA = "a5e90ff7c80800c4eb93bda825e78d5563f1ce4aaee56b28e24afd5a2a9606ff"
ORCH_RELPATH = "quantbot/experiment/h001_per_run_coordinate_and_seed_orchestration.py"
ORCH_TEST_RELPATH = "tests/experiment/test_h001_per_run_coordinate_and_seed_orchestration.py"
ENGINE_RELPATH = "quantbot/experiment/h001_null_calibration_engine.py"
ORCHESTRATION_IMPLEMENTATION_STATUS = "IMPLEMENTED_FOR_INDEPENDENT_REVIEW_ONLY"
DOMAINS = list(previous.previous.previous.NUMERICAL_CONVENTION_GAP_INVENTORY)
SELECTED = list(previous.previous.previous.NUMERICAL_CONVENTIONS_SELECTED_CONVENTION_INVENTORY)
RNG_RESOLVED = list(previous.previous.previous.RNG_RUNTIME_CANDIDATE_RESOLVED_INVENTORY)
CURRENT_FILES = [
    "quantbot/continuity/context.py",
    "quantbot/continuity/h001_per_run_coordinate_and_seed_orchestration_candidate_v038.py",
    "tests/continuity/test_h001_per_run_coordinate_and_seed_orchestration_candidate_v038.py",
    "tests/control/governance_baseline.json",
]
PROTECTED = {
    **previous.PROTECTED,
    previous.HANDOFF_RELPATH: V037_SHA,
    previous.GOVERNANCE_RELPATH: "d71f6960dc923fb2eaf3d84653f3203634d7e0659919065dccebe09496253d69",
}
SCOPE = [ORCH_RELPATH, ORCH_TEST_RELPATH, HANDOFF_RELPATH, c.ACTIVE_TASK_RELPATH, *CURRENT_FILES]
ENGINE_BINDING = dict(previous.BINDING)
PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION_BINDING = {
    "orchestration_path": ORCH_RELPATH,
    "orchestration_test_path": ORCH_TEST_RELPATH,
    "orchestration_implementation_status": ORCHESTRATION_IMPLEMENTATION_STATUS,
    "orchestration_implemented": True,
    "orchestration_executed": False,
    "orchestration_reviewed": False,
    "orchestration_wired_into_execute_calibration": False,
    "engine_path": ENGINE_RELPATH,
    "component_id": "PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION",
    "review_scope": "H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION_CANDIDATE_IMPLEMENTATION_ONLY",
}
_DECISIONS_REMOVE = {
    "H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION_CANDIDATE=NOT_CREATED",
    "H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION_REVIEW=NOT_COMPLETED",
}
_DECISIONS_ADD = {
    "H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION_CANDIDATE=CREATED_FOR_INDEPENDENT_REVIEW",
    "H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION_CANDIDATE_VALUES=LOCKED_FOR_REVIEW",
    "H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION_REVIEW=REQUIRED",
    "H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION_EXECUTED=FALSE",
    "H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION_WIRED_INTO_EXECUTE_CALIBRATION=FALSE",
}
DECISIONS = sorted({*(x for x in previous.DECISIONS if x not in _DECISIONS_REMOVE), *_DECISIONS_ADD})
BLOCKERS = sorted({
    *(x for x in previous.BLOCKERS if x != "H001 per-run coordinate and seed orchestration candidate requires independent review before any implementation"),
    "H001 per-run coordinate and seed orchestration candidate requires independent adversarial review before any implementation, wiring, or execution",
})
PROHIBITIONS = sorted({
    *previous.PROHIBITIONS,
    "MODIFY_PRIOR_AMENDMENTS_OR_HANDOFF_RECEIPTS_V001_THROUGH_V037",
    "TREAT_H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION_CANDIDATE_AS_IMPLEMENTATION_OR_EXECUTION_AUTHORIZATION",
    "MODIFY_H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION_CANDIDATE_VALUES_AFTER_LOCK",
    "MERGE_H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION_CANDIDATE_BEFORE_INDEPENDENT_ADVERSARIAL_REVIEW",
})


def validate(receipt, root):
    if receipt["receipt_index"] != 38 or receipt["phase"] != PHASE or receipt["source_branch"] != BRANCH or receipt["source_head_commit"] != BASE_SHA:
        c._fail("H001 per-run coordinate/seed candidate receipt identity or source binding is wrong")
    if receipt["predecessor"] != {"path": previous.HANDOFF_RELPATH, "sha256": V037_SHA}:
        c._fail("H001 per-run coordinate/seed candidate predecessor is wrong")
    for field, expected in (
        ("changed_file_scope", SCOPE),
        ("next_actions", [NEXT_ACTION]),
        ("decisions", DECISIONS),
        ("blockers", BLOCKERS),
        ("prohibited_actions", PROHIBITIONS),
        ("numerical_convention_gap_inventory", DOMAINS),
        ("numerical_conventions_selected_convention_inventory", SELECTED),
        ("rng_runtime_candidate_resolved_inventory", RNG_RESOLVED),
        ("engine_implementation_binding", ENGINE_BINDING),
    ):
        if receipt[field] != expected or len(receipt[field]) != len(set(receipt[field])):
            c._fail(f"H001 per-run coordinate/seed candidate {field} drifted")
    if receipt["safety_state"] != dict(c._EXPECTED_SAFETY, real_data_execution_requested=False):
        c._fail("H001 per-run coordinate/seed candidate safety state drifted")
    for path, digest in PROTECTED.items():
        if not (root / path).is_file() or hashlib.sha256((root / path).read_bytes()).hexdigest() != digest:
            c._fail(f"H001 per-run coordinate/seed candidate protected evidence {path!r} hash mismatch")
    orch_bytes = (root / ORCH_RELPATH).read_bytes()
    orch_test_bytes = (root / ORCH_TEST_RELPATH).read_bytes()
    orch_sha256 = hashlib.sha256(orch_bytes).hexdigest()
    orch_test_sha256 = hashlib.sha256(orch_test_bytes).hexdigest()
    engine_sha256 = hashlib.sha256((root / ENGINE_RELPATH).read_bytes()).hexdigest()
    expected_binding = dict(
        PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION_BINDING,
        orchestration_sha256=orch_sha256,
        orchestration_test_sha256=orch_test_sha256,
        engine_sha256=engine_sha256,
    )
    if receipt["per_run_coordinate_and_seed_orchestration_binding"] != expected_binding:
        c._fail("H001 per-run coordinate/seed candidate binding drifted")
    if receipt["evidence"] != [{"path": p, "sha256": h} for p, h in PROTECTED.items()] + [
        {"path": ORCH_RELPATH, "sha256": orch_sha256},
        {"path": ORCH_TEST_RELPATH, "sha256": orch_test_sha256},
    ]:
        c._fail("H001 per-run coordinate/seed candidate evidence is wrong")
    if receipt["current_transition_files"] != [{"path": p, "sha256": hashlib.sha256((root / p).read_bytes()).hexdigest()} for p in CURRENT_FILES]:
        c._fail("H001 per-run coordinate/seed candidate transition files drifted")
