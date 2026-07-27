"""v041 records independent review of the immutable v040 repair candidate."""
import hashlib
from . import context as c
from . import h001_per_run_coordinate_and_seed_orchestration_checkout_path_repair_v040 as previous

PHASE="candidate1_h001_synthetic_null_calibration_per_run_coordinate_and_seed_orchestration_checkout_path_repair_review_completed"
NEXT_ACTION="AUDIT_H001_SCIENTIFIC_CONTRACT_CONSISTENCY_BEFORE_ACTIVATION"
HANDOFF_RELPATH=f"docs/control/tasks/{c.TASK_ID}/handoff_v041.json"
REVIEW_RELPATH="docs/assurance/reviews/candidate1_h001_synthetic_null_calibration_per_run_coordinate_and_seed_orchestration_checkout_path_repair_review_v001.json"
BRANCH="chore/h001-v040-checkout-path-repair-review-completion-v041"
V040_SHA="7a370d1ad4025ff8c0513b217c4646a7667150370bb76d02ae3eb740a454df75"
REVIEW_BINDING={"reviewed_commit":"c49de19664d02a804dfbe102647724416d635de0","reviewed_tree":"c2c65875dfcdc640e07debbde2d4049ef3e7f60f","reviewed_v040_handoff_sha256":V040_SHA,"review_verdict":"PASS_READY_TO_RECORD_REVIEW","review_record_path":REVIEW_RELPATH,"orchestration_effective":False,"orchestration_activated":False,"orchestration_executed":False,"orchestration_wired_into_execute_calibration":False}
CURRENT_FILES=["quantbot/continuity/context.py","quantbot/continuity/h001_per_run_coordinate_and_seed_orchestration_checkout_path_repair_review_completion_v041.py","tests/continuity/test_h001_per_run_coordinate_and_seed_orchestration_checkout_path_repair_review_completion_v041.py","tests/control/governance_baseline.json"]
SCOPE=[REVIEW_RELPATH,HANDOFF_RELPATH,c.ACTIVE_TASK_RELPATH,*CURRENT_FILES]
PROTECTED={**previous.PROTECTED,previous.HANDOFF_RELPATH:V040_SHA}
DECISIONS=sorted({*previous.DECISIONS,"H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION_CHECKOUT_PATH_REPAIR_REVIEW=PASSED","H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION_ACTIVATION=BLOCKED_PENDING_SCIENTIFIC_CONSISTENCY_AUDIT"})
BLOCKERS=sorted({*(x for x in previous.BLOCKERS if "checkout-path repair requires independent review" not in x),"H001 activation blocked pending scientific-consistency audit"})
PROHIBITIONS=sorted({*previous.PROHIBITIONS,"ACTIVATE_H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION_BEFORE_SCIENTIFIC_CONSISTENCY_AUDIT"})
def validate(receipt,root):
 if receipt["receipt_index"]!=41 or receipt["phase"]!=PHASE or receipt["source_branch"]!=BRANCH or receipt["source_head_commit"]!="c49de19664d02a804dfbe102647724416d635de0":c._fail("H001 repair review-completion identity drifted")
 if receipt["predecessor"]!={"path":previous.HANDOFF_RELPATH,"sha256":V040_SHA}:c._fail("H001 repair review-completion predecessor is wrong")
 for k,v in (("changed_file_scope",SCOPE),("next_actions",[NEXT_ACTION]),("decisions",DECISIONS),("blockers",BLOCKERS),("prohibited_actions",PROHIBITIONS),("v040_review_binding",REVIEW_BINDING)):
  if receipt[k]!=v:c._fail(f"H001 repair review-completion {k} drifted")
 if receipt["safety_state"]!=dict(c._EXPECTED_SAFETY,real_data_execution_requested=False):c._fail("H001 repair review-completion safety drifted")
 for p,h in PROTECTED.items():
  if not (root/p).is_file() or hashlib.sha256((root/p).read_bytes()).hexdigest()!=h:c._fail("H001 repair review-completion protected evidence drifted")
 raw=(root/REVIEW_RELPATH).read_bytes(); review=c._load_canonical_document(raw,"H001 repair review record")
 if review!={"document_kind":"qnty_h001_checkout_path_repair_review_record","reviewed_commit":"c49de19664d02a804dfbe102647724416d635de0","reviewed_tree":"c2c65875dfcdc640e07debbde2d4049ef3e7f60f","reviewed_v040_handoff_sha256":V040_SHA,"review_verdict":"PASS_READY_TO_RECORD_REVIEW","schema_version":"0.1.0"}:c._fail("H001 repair review record drifted")
 if receipt["current_transition_files"]!=[{"path":p,"sha256":hashlib.sha256((root/p).read_bytes()).hexdigest()} for p in CURRENT_FILES]:c._fail("H001 repair review-completion transition files drifted")
 if any(receipt["v040_review_binding"][x] for x in ("orchestration_effective","orchestration_activated","orchestration_executed","orchestration_wired_into_execute_calibration")):c._fail("H001 repair review completion cannot activate or execute")
