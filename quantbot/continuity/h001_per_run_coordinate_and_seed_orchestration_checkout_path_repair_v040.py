"""v040 successor repair for the v039 checkout-path validator defect."""
import hashlib
from . import context as c
from . import h001_per_run_coordinate_and_seed_orchestration_review_completion_v039 as previous

PHASE="candidate1_h001_synthetic_null_calibration_per_run_coordinate_and_seed_orchestration_checkout_path_repair_review_required"
NEXT_ACTION="ADVERSARIAL_REVIEW_H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION_CHECKOUT_PATH_REPAIR"
HANDOFF_RELPATH=f"docs/control/tasks/{c.TASK_ID}/handoff_v040.json"
BRANCH="fix/h001-v039-checkout-path-repair-v040"
V039_SHA="687c4dcc07e3e850a4e7e43c41687aecad5a46c8690380af2243181f7e656644"
REPAIR_BINDING={"reviewed_v039_commit":"f6737f188e82fb61b366131eacb137059132b2af","reviewed_v039_tree":"79bc3dc860ee56b8d0a27a61071dc1db62b34385","failed_pr_merge_ref":"d710e6caad86c082476f3dbaf1f414661d018545","merge_tree":"79bc3dc860ee56b8d0a27a61071dc1db62b34385","v039_handoff_sha256":V039_SHA,"root_cause_class":"ENVIRONMENT_DEPENDENCY_DEFECT","defect_mechanism":"checkout_name_specific_path_derivation","repair_status":"IMPLEMENTED_FOR_INDEPENDENT_REVIEW","orchestration_effective":False,"orchestration_activated":False,"orchestration_executed":False,"orchestration_wired_into_execute_calibration":False}
CURRENT_FILES=["quantbot/continuity/context.py","quantbot/continuity/h001_per_run_coordinate_and_seed_orchestration_review_completion_v039.py","tests/continuity/test_h001_per_run_coordinate_and_seed_orchestration_review_completion_v039.py","quantbot/continuity/h001_per_run_coordinate_and_seed_orchestration_checkout_path_repair_v040.py","tests/continuity/test_h001_per_run_coordinate_and_seed_orchestration_checkout_path_repair_v040.py","tests/control/governance_baseline.json"]
SCOPE=[HANDOFF_RELPATH,c.ACTIVE_TASK_RELPATH,*CURRENT_FILES]
PROTECTED={**previous.PROTECTED,previous.HANDOFF_RELPATH:V039_SHA,previous.REVIEW_RELPATH:previous.REVIEW_SHA}
DECISIONS=sorted({*(x for x in previous.DECISIONS if x!="H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION_ACTIVATION_TRANSITION=AUTHORIZED_FOR_INDEPENDENT_REVIEW_ONLY"),"H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION_CHECKOUT_PATH_REPAIR=IMPLEMENTED_FOR_INDEPENDENT_REVIEW","H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION_EFFECTIVE=FALSE","H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION_ACTIVATED=FALSE","H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION_EXECUTED=FALSE","H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION_WIRED_INTO_EXECUTE_CALIBRATION=FALSE"})
BLOCKERS=sorted({*(x for x in previous.BLOCKERS if "activation transition requires independent review" not in x),"H001 per-run coordinate and seed orchestration checkout-path repair requires independent review"})
PROHIBITIONS=sorted({*previous.PROHIBITIONS,"ACTIVATE_H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION_BEFORE_CHECKOUT_PATH_REPAIR_IS_INDEPENDLY_REVIEWED_AND_MERGED","MODIFY_PRIOR_AMENDMENTS_OR_HANDOFF_RECEIPTS_V001_THROUGH_V039"})

def validate(receipt,root):
 if receipt["receipt_index"]!=40 or receipt["phase"]!=PHASE or receipt["source_branch"]!=BRANCH or receipt["source_head_commit"]!="f6737f188e82fb61b366131eacb137059132b2af":c._fail("H001 checkout-path repair identity drifted")
 if receipt["predecessor"]!={"path":previous.HANDOFF_RELPATH,"sha256":V039_SHA}:c._fail("H001 checkout-path repair predecessor is wrong")
 for k,v in (("changed_file_scope",SCOPE),("next_actions",[NEXT_ACTION]),("decisions",DECISIONS),("blockers",BLOCKERS),("prohibited_actions",PROHIBITIONS),("v039_checkout_path_repair",REPAIR_BINDING)):
  if receipt[k]!=v:c._fail(f"H001 checkout-path repair {k} drifted")
 if receipt["safety_state"]!=dict(c._EXPECTED_SAFETY,real_data_execution_requested=False):c._fail("H001 checkout-path repair safety drifted")
 for p,h in PROTECTED.items():
  if not (root/p).is_file() or hashlib.sha256((root/p).read_bytes()).hexdigest()!=h:c._fail("H001 checkout-path repair protected evidence drifted")
 if receipt["current_transition_files"]!=[{"path":p,"sha256":hashlib.sha256((root/p).read_bytes()).hexdigest()} for p in CURRENT_FILES]:c._fail("H001 checkout-path repair transition files drifted")
 if any(receipt["v039_checkout_path_repair"][x] for x in ("orchestration_effective","orchestration_activated","orchestration_executed","orchestration_wired_into_execute_calibration")):c._fail("H001 checkout-path repair cannot activate or execute")
