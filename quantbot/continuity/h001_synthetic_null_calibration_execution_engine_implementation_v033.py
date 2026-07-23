"""v033 H001 synthetic-null calibration execution engine implementation,
review-required transition.

This transition records only that a deterministic, synthetic-only statistic
and bootstrap-path computational core was implemented for independent review.
It was not executed. It authorizes no calibration execution, no results, no
real-data access, no scientific use, no paper trading, no shadow operation,
and no live integration.
"""

import hashlib

from . import context as c
from . import h001_numerical_conventions_activation_v032 as previous


PHASE = "candidate1_h001_synthetic_null_calibration_execution_engine_implementation_review_required"
NEXT_ACTION = "ADVERSARIAL_REVIEW_H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION_ENGINE_IMPLEMENTATION"
HANDOFF_RELPATH = f"docs/control/tasks/{c.TASK_ID}/handoff_v033.json"
BRANCH = "feat/h001-null-calibration-engine-v033"
BASE_SHA = "6fb0e9b88e16a504a9e053f53ac7e5e55b40fda8"
V032_SHA = "43d4b4f89d594d8a79804ca9a0c4227405255a12d09f380c085f193b44ccd91d"
ENGINE_RELPATH = "quantbot/experiment/h001_null_calibration_engine.py"
ENGINE_TEST_RELPATH = "tests/experiment/test_h001_null_calibration_engine.py"
LEGACY_ADAPTER_RELPATH = "quantbot/control/legacy_adapter.py"
LEGACY_ADAPTER_TEST_RELPATH = "tests/control/test_legacy_adapter.py"
ENGINE_IMPLEMENTATION_STATUS = "IMPLEMENTED_FOR_INDEPENDENT_REVIEW_ONLY"
DOMAINS = list(previous.DOMAINS)
SELECTED = list(previous.SELECTED)
CURRENT_FILES = [
    "quantbot/continuity/context.py",
    "quantbot/continuity/h001_synthetic_null_calibration_execution_engine_implementation_v033.py",
    "tests/continuity/test_cross_agent_continuity.py",
    LEGACY_ADAPTER_RELPATH,
    LEGACY_ADAPTER_TEST_RELPATH,
    "tests/control/governance_baseline.json",
]
# Protected historical evidence: the full inherited v032 inventory (which
# already recursively carries every earlier candidate, activation, and
# handoff receipt) plus the v032 handoff receipt itself. Every hash is an
# independently pinned historical value, never derived from the current
# bytes of the artifact it protects.
# v032's own newly-created activation document was bound only in v032's
# transient evidence list, never folded into its PROTECTED dict for forward
# inheritance; it is added explicitly here so the legacy adapter (which reads
# the numerical-conventions activation as one of the seven effective
# amendment roles) still finds it bound by receipt evidence at v033.
V032_ACTIVATION_SHA = "c497359a292f5a9b1333e5d881fee16c39d80f68ec1a6613f625a368532ae200"
PROTECTED = {**previous.PROTECTED, previous.HANDOFF_RELPATH: V032_SHA, previous.ACTIVATION_RELPATH: V032_ACTIVATION_SHA}
SCOPE = [ENGINE_RELPATH, ENGINE_TEST_RELPATH, HANDOFF_RELPATH, c.ACTIVE_TASK_RELPATH, *CURRENT_FILES]
BINDING = {
    "engine_path": ENGINE_RELPATH,
    "engine_test_path": ENGINE_TEST_RELPATH,
    "engine_implementation_status": ENGINE_IMPLEMENTATION_STATUS,
    "engine_implemented": True,
    "engine_executed": False,
    "engine_reviewed": False,
    "engine_wired_into_execute_calibration": False,
    "numerical_conventions_amendment_sha256": "28551aa041aff2985e0023e61516b08f528d93cf72c23c8c3541793f6f61c691",
    "rng_runtime_specification_amendment_sha256": "e52b1a4733024e4255cf771b97765cff19f7f5e59cf824732784a1abd594812f",
    "spec_freeze_candidate_sha256": "04b6ea5b7453fccf4787abb26c230e2a02a77545c741c19f6686df16fc2cb7a2",
    "review_scope": "H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION_ENGINE_IMPLEMENTATION_ONLY",
}
_DECISIONS_REMOVE = {
    "H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION_ENGINE_IMPLEMENTATION_ATTEMPT=BLOCKED_BEFORE_CHANGE",
    "H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION_ENGINE_IMPLEMENTATION_COMMIT=NONE",
    "H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION_ENGINE_IMPLEMENTATION_PR=NONE",
    "H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION_IMPLEMENTATION=NOT_IMPLEMENTED",
    "H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION_IMPLEMENTATION_BLOCKER=NONE_NUMERICAL_CONVENTIONS_EFFECTIVE",
}
_DECISIONS_ADD = {
    "H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION_ENGINE_IMPLEMENTATION_ATTEMPT=COMPLETED_FOR_INDEPENDENT_REVIEW",
    "H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION_ENGINE_IMPLEMENTATION_COMMIT=NONE_NOT_YET_COMMITTED",
    "H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION_ENGINE_IMPLEMENTATION_PR=NONE_NOT_YET_OPENED",
    "H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION_IMPLEMENTATION=IMPLEMENTED_FOR_INDEPENDENT_REVIEW_NOT_EXECUTED",
    "H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION_IMPLEMENTATION_BLOCKER=NONE_AWAITING_INDEPENDENT_REVIEW",
    "H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION_ENGINE_IMPLEMENTATION_REVIEW=REQUIRED",
    "H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION_ENGINE_WIRED_INTO_EXECUTE_CALIBRATION=FALSE",
}
DECISIONS = sorted({*[x for x in previous.DECISIONS if x not in _DECISIONS_REMOVE], *_DECISIONS_ADD})
BLOCKERS = sorted({*previous.BLOCKERS, "H001 synthetic-null calibration execution engine implementation requires independent adversarial review"})
PROHIBITIONS = sorted(
    {
        *previous.PROHIBITIONS,
        "MODIFY_PRIOR_AMENDMENTS_OR_HANDOFF_RECEIPTS_V001_THROUGH_V032",
        "EXECUTE_H001_SYNTHETIC_NULL_CALIBRATION_ENGINE",
        "WIRE_ENGINE_INTO_EXECUTE_CALIBRATION",
        "TREAT_ENGINE_IMPLEMENTATION_AS_REVIEWED_OR_AUTHORIZED",
        "MERGE_H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION_ENGINE_IMPLEMENTATION_BEFORE_INDEPENDENT_ADVERSARIAL_REVIEW",
    }
)


def _engine_implementation_expected(engine_sha256: str, engine_test_sha256: str) -> dict:
    return {
        "engine_path": ENGINE_RELPATH,
        "engine_sha256": engine_sha256,
        "engine_test_path": ENGINE_TEST_RELPATH,
        "engine_test_sha256": engine_test_sha256,
        "engine_implementation_status": ENGINE_IMPLEMENTATION_STATUS,
        "engine_implemented": True,
        "engine_executed": False,
        "engine_reviewed": False,
        "engine_wired_into_execute_calibration": False,
        "numerical_conventions_amendment_sha256": BINDING["numerical_conventions_amendment_sha256"],
        "rng_runtime_specification_amendment_sha256": BINDING["rng_runtime_specification_amendment_sha256"],
        "spec_freeze_candidate_sha256": BINDING["spec_freeze_candidate_sha256"],
        "review_scope": BINDING["review_scope"],
    }


def validate(receipt, root):
    if receipt["receipt_index"] != 33 or receipt["phase"] != PHASE or receipt["source_branch"] != BRANCH or receipt["source_head_commit"] != BASE_SHA:
        c._fail("H001 engine-implementation receipt identity or source binding is wrong")
    if receipt["predecessor"] != {"path": previous.HANDOFF_RELPATH, "sha256": V032_SHA}:
        c._fail("H001 engine-implementation predecessor is wrong")
    for field, expected in (
        ("changed_file_scope", SCOPE),
        ("next_actions", [NEXT_ACTION]),
        ("decisions", DECISIONS),
        ("blockers", BLOCKERS),
        ("prohibited_actions", PROHIBITIONS),
        ("numerical_convention_gap_inventory", DOMAINS),
        ("numerical_conventions_selected_convention_inventory", SELECTED),
        ("rng_runtime_candidate_resolved_inventory", previous.previous.previous.previous.DOMAINS),
    ):
        if receipt[field] != expected or len(receipt[field]) != len(set(receipt[field])):
            c._fail(f"H001 engine-implementation {field} drifted")
    if receipt["safety_state"] != dict(c._EXPECTED_SAFETY, real_data_execution_requested=False):
        c._fail("H001 engine-implementation safety state drifted")
    for path, digest in PROTECTED.items():
        if not (root / path).is_file() or hashlib.sha256((root / path).read_bytes()).hexdigest() != digest:
            c._fail(f"H001 engine-implementation protected evidence {path!r} hash mismatch")
    engine_bytes = (root / ENGINE_RELPATH).read_bytes()
    engine_test_bytes = (root / ENGINE_TEST_RELPATH).read_bytes()
    engine_sha256 = hashlib.sha256(engine_bytes).hexdigest()
    engine_test_sha256 = hashlib.sha256(engine_test_bytes).hexdigest()
    if receipt["engine_implementation_binding"] != _engine_implementation_expected(engine_sha256, engine_test_sha256):
        c._fail("H001 engine-implementation binding drifted")
    if receipt["evidence"] != [{"path": p, "sha256": h} for p, h in PROTECTED.items()] + [
        {"path": ENGINE_RELPATH, "sha256": engine_sha256},
        {"path": ENGINE_TEST_RELPATH, "sha256": engine_test_sha256},
    ]:
        c._fail("H001 engine-implementation evidence is wrong")
    if receipt["current_transition_files"] != [{"path": p, "sha256": hashlib.sha256((root / p).read_bytes()).hexdigest()} for p in CURRENT_FILES]:
        c._fail("H001 engine-implementation transition files drifted")
