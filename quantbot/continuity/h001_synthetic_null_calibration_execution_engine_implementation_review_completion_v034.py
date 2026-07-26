"""v034 administrative exact-head review completion for the H001 engine core."""

import hashlib

from . import context as c
from . import h001_synthetic_null_calibration_execution_engine_implementation_v033 as previous

PHASE = "candidate1_h001_synthetic_null_calibration_execution_engine_implementation_review_completed"
NEXT_ACTION = "AUTHORIZE_H001_SYNTHETIC_NULL_CALIBRATION_REMAINING_EXECUTION_PIPELINE_SCOPE_GOVERNANCE"
REVIEW_RELPATH = "docs/assurance/reviews/candidate1_h001_synthetic_null_calibration_execution_engine_implementation_review_v001.json"
HANDOFF_RELPATH = f"docs/control/tasks/{c.TASK_ID}/handoff_v034.json"
BRANCH = "chore/h001-calibration-engine-review-completion-v034"
BASE_SHA = "0bd455ed236fe69ecca6484e3c9318070db889f0"
REVIEWED_BASE = "6fb0e9b88e16a504a9e053f53ac7e5e55b40fda8"
REVIEWED_HEAD = "3a08a1f7f6a7bb046647c5566a03c1d36a495e75"
REVIEWED_TREE = "fb04e70d041971142f0798cbb1902adfd866aea8"
V033_SHA = "fc97ec857ed1fdd0ff5ddecd639c1f7346c1bb8e6f84d0804d1cd675b55ca035"
V033_POINTER_SHA = "920bb38978076cddbeab9188419503a98e16c801e45d38b5ea87aa3fc6c9640e"
CURRENT_FILES = [
    "quantbot/continuity/context.py",
    "quantbot/continuity/h001_synthetic_null_calibration_execution_engine_implementation_review_completion_v034.py",
    "tests/continuity/test_cross_agent_continuity.py",
    "quantbot/control/legacy_adapter.py",
    "tests/control/test_legacy_adapter.py",
    "tests/control/governance_baseline.json",
    "tests/control/debt_allowlist.json",
    "tests/control/hygiene_ast.py",
    "tests/control/test_no_historical_source_reconstruction.py",
    "tests/fixtures/historical_continuity_v034/base_0bd455ed.tar.gz",
    "tests/fixtures/historical_continuity_v034/v024_90460b3e13db.tar.gz",
    "tests/fixtures/historical_continuity_v034/v025_6ced3c374671.tar.gz",
    "tests/fixtures/historical_continuity_v034/v026_83c8511022f1.tar.gz",
    "tests/fixtures/historical_continuity_v034/v027_31ae06eba2d1.tar.gz",
    "tests/fixtures/historical_continuity_v034/v028_5879173f5be7.tar.gz",
    "tests/fixtures/historical_continuity_v034/v029_65b2fe30d63e.tar.gz",
    "tests/fixtures/historical_continuity_v034/v030_c4f7fac9aecc.tar.gz",
    "tests/fixtures/historical_continuity_v034/v031_887d0da21b21.tar.gz",
    "tests/fixtures/historical_continuity_v034/v032_afada1090c53.tar.gz",
    "tests/fixtures/historical_continuity_v034/v033_6fb0e9b88e16.tar.gz",
]
SCOPE = [REVIEW_RELPATH, HANDOFF_RELPATH, c.ACTIVE_TASK_RELPATH, *CURRENT_FILES]
PROTECTED = {**previous.PROTECTED, previous.HANDOFF_RELPATH: V033_SHA, previous.ENGINE_RELPATH: hashlib.sha256(__import__('pathlib').Path(__file__).parents[2].joinpath(previous.ENGINE_RELPATH).read_bytes()).hexdigest(), previous.ENGINE_TEST_RELPATH: hashlib.sha256(__import__('pathlib').Path(__file__).parents[2].joinpath(previous.ENGINE_TEST_RELPATH).read_bytes()).hexdigest()}
BINDING = {**previous.BINDING, "engine_reviewed": True, "engine_review_verdict": "PASS", "review_record_path": REVIEW_RELPATH, "implementation_status": "ADMINISTRATIVE_REVIEW_COMPLETED_NOT_EXECUTABLE"}
DECISIONS = sorted({*[x for x in previous.DECISIONS if x not in {"H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION_ENGINE_IMPLEMENTATION_REVIEW=REQUIRED", "H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION_IMPLEMENTATION_BLOCKER=NONE_AWAITING_INDEPENDENT_REVIEW"}], "H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION_ENGINE_IMPLEMENTATION_REVIEW=PASSED", "H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION_ENGINE_IMPLEMENTATION_REVIEW_RECORD=RECORDED", "H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION_ENGINE_REVIEWED=TRUE", "H001_SYNTHETIC_NULL_CALIBRATION_ENGINE_EXECUTION=NOT_AUTHORIZED", "H001_REMAINING_EXECUTION_PIPELINE_SCOPE_GOVERNANCE=REQUIRED", "H001_REMAINING_EXECUTION_PIPELINE_IMPLEMENTATION=NOT_AUTHORIZED"})
BLOCKERS = sorted({*(x for x in previous.BLOCKERS if x != "H001 synthetic-null calibration execution engine implementation requires independent adversarial review"), "H001 remaining synthetic calibration execution pipeline requires separately reviewed governance decomposition before further implementation"})
PROHIBITIONS = sorted({*previous.PROHIBITIONS, "IMPLEMENT_REMAINING_H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION_PIPELINE_COMPONENTS_BEFORE_SEPARATE_SCOPE_GOVERNANCE_TRANSITION_IS_REVIEWED_AND_MERGED", "TREAT_ENGINE_REVIEW_COMPLETION_AS_CALIBRATION_EXECUTION_AUTHORIZATION", "TREAT_ENGINE_REVIEW_COMPLETION_AS_SCIENTIFIC_FWER_PROFITABILITY_OR_EDGE_EVIDENCE", "MODIFY_PRIOR_AMENDMENTS_OR_HANDOFF_RECEIPTS_V001_THROUGH_V033"})

def _review_expected():
    return {"review_id":"candidate1-h001-synthetic-null-calibration-execution-engine-implementation-review-v001","document_kind":"qnty_h001_synthetic_null_calibration_execution_engine_implementation_review_record","schema_version":"0.1.0","status":"RECORDED_AFTER_INDEPENDENT_EXACT_HEAD_ADVERSARIAL_REVIEW_NOT_EXECUTABLE","review_kind":"INDEPENDENT_EXACT_HEAD_ADVERSARIAL_REVIEW","reviewed_pr":314,"reviewed_base_sha":REVIEWED_BASE,"reviewed_head_sha":REVIEWED_HEAD,"reviewed_tree_sha":REVIEWED_TREE,"reviewed_commit_count":1,"reviewed_changed_file_count":10,"merge_commit_sha":BASE_SHA,"ordered_merge_parent_shas":[REVIEWED_BASE,REVIEWED_HEAD],"merged_tree_sha":REVIEWED_TREE,"engine_path":previous.ENGINE_RELPATH,"engine_sha256":PROTECTED[previous.ENGINE_RELPATH],"engine_test_path":previous.ENGINE_TEST_RELPATH,"engine_test_sha256":PROTECTED[previous.ENGINE_TEST_RELPATH],"v033_receipt_sha256":V033_SHA,"v033_active_pointer_sha256":V033_POINTER_SHA,"review_verdict":"PASS","blocker_count":0,"major_count":0,"minor_count":0,"note_count":0,"verification_categories":["EXACT_HEAD_IDENTITY","TARGETED_ENGINE_ASSURANCE_LADDER","FULL_REPOSITORY_SUITE","CONTINUITY","RELEASE_SMOKE","NO_CALIBRATION_EXECUTION"],"review_results":{"targeted_engine_assurance_ladder":"210 passed","assurance":"410 passed","engine":"81 passed","continuity":"800 passed, 6 skipped","control":"292 passed, 1 skipped","release_smoke":"IMPORT_OK, 6 passed","full_suite":"7450 passed, 7 skipped","calibration_execution":"NOT_PERFORMED","review_worktree":"CLEAN","reviewer_made_modifications":"NONE"},"non_effects":["ENGINE_NOT_EXECUTED","ENGINE_NOT_WIRED_INTO_EXECUTE_CALIBRATION","CALIBRATION_EXECUTION_NOT_AUTHORIZED","NO_CALIBRATION_RESULTS","NO_REAL_DATA_ACCESS","NO_SCIENTIFIC_AUTHORITY","NO_PAPER_TRADING_AUTHORITY","NO_SHADOW_AUTHORITY","NO_LIVE_AUTHORITY","EDGE_UNPROVEN","BLOCK_LIVE_INTEGRATION","REVIEW_RESULTS_NOT_SCIENTIFIC_OR_MARKET_EDGE_EVIDENCE"]}

def validate(receipt, root):
    if receipt["receipt_index"] != 34 or receipt["phase"] != PHASE or receipt["source_branch"] != BRANCH or receipt["source_head_commit"] != BASE_SHA: c._fail("H001 engine review-completion receipt identity or source binding is wrong")
    if receipt["predecessor"] != {"path": previous.HANDOFF_RELPATH, "sha256": V033_SHA}: c._fail("H001 engine review-completion predecessor is wrong")
    for field, expected in (("changed_file_scope",SCOPE),("next_actions",[NEXT_ACTION]),("decisions",DECISIONS),("blockers",BLOCKERS),("prohibited_actions",PROHIBITIONS),("numerical_convention_gap_inventory",previous.DOMAINS),("numerical_conventions_selected_convention_inventory",previous.SELECTED),("rng_runtime_candidate_resolved_inventory",previous.previous.previous.previous.previous.DOMAINS),("engine_implementation_binding",BINDING)):
        if receipt[field] != expected or (isinstance(expected,list) and len(receipt[field]) != len(set(receipt[field]))): c._fail(f"H001 engine review-completion {field} drifted")
    if receipt["safety_state"] != dict(c._EXPECTED_SAFETY, real_data_execution_requested=False): c._fail("H001 engine review-completion safety state drifted")
    for path,digest in PROTECTED.items():
        if not (root/path).is_file() or hashlib.sha256((root/path).read_bytes()).hexdigest()!=digest: c._fail(f"H001 engine review-completion protected evidence {path!r} hash mismatch")
    review_raw=(root/REVIEW_RELPATH).read_bytes(); review=c._load_canonical_document(review_raw,"H001 engine review record")
    if review != _review_expected(): c._fail("H001 engine review record is malformed or does not bind the independently pinned review")
    if receipt["evidence"] != [{"path":p,"sha256":h} for p,h in PROTECTED.items()]+[{"path":REVIEW_RELPATH,"sha256":hashlib.sha256(review_raw).hexdigest()}]: c._fail("H001 engine review-completion evidence is wrong")
    if receipt["current_transition_files"] != [{"path":p,"sha256":hashlib.sha256((root/p).read_bytes()).hexdigest()} for p in CURRENT_FILES]: c._fail("H001 engine review-completion transition files drifted")
