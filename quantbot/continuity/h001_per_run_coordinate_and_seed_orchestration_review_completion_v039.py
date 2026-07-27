"""v039 review completion; reviewed only, never effective or activated."""
import hashlib
from . import context as c
from . import h001_per_run_coordinate_and_seed_orchestration_candidate_v038 as previous

PHASE="candidate1_h001_synthetic_null_calibration_per_run_coordinate_and_seed_orchestration_review_completed"
NEXT_ACTION="IMPLEMENT_H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION_ACTIVATION_FOR_INDEPENDENT_REVIEW"
REVIEW_RELPATH="docs/assurance/reviews/candidate1_h001_synthetic_null_calibration_per_run_coordinate_and_seed_orchestration_candidate_review_v001.json"
HANDOFF_RELPATH=f"docs/control/tasks/{c.TASK_ID}/handoff_v039.json"
BRANCH="chore/h001-per-run-coordinate-seed-orchestration-review-completion-v039"
BASE_SHA="dc9289bab786b53047038021f409a610d6e6c845"
V038_SHA="91470a63f99522f0c83cd693059014441884ca254b7f0074fc17387ac53a8aff"
REVIEW_SHA="9197e96582ffb04cb3c7f2a8b766a57809bd7c0f1378abb15c6f20d09784d81d"
CURRENT_FILES=["quantbot/continuity/context.py",__file__.split("/qnty-v039/")[-1],"tests/continuity/test_h001_per_run_coordinate_and_seed_orchestration_review_completion_v039.py","tests/control/governance_baseline.json"]
SCOPE=[REVIEW_RELPATH,HANDOFF_RELPATH,c.ACTIVE_TASK_RELPATH,*CURRENT_FILES]
PROTECTED={**previous.PROTECTED,previous.HANDOFF_RELPATH:V038_SHA,previous.ORCH_RELPATH:hashlib.sha256(__import__('pathlib').Path(__file__).parents[2].joinpath(previous.ORCH_RELPATH).read_bytes()).hexdigest(),previous.ORCH_TEST_RELPATH:hashlib.sha256(__import__('pathlib').Path(__file__).parents[2].joinpath(previous.ORCH_TEST_RELPATH).read_bytes()).hexdigest()}
BINDING={**previous.PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION_BINDING,"orchestration_reviewed":True,"orchestration_review_verdict":"PASS","orchestration_effective":False,"orchestration_activated":False,"review_record_path":REVIEW_RELPATH,"implementation_status":"ADMINISTRATIVE_REVIEW_COMPLETED_NOT_EFFECTIVE_NOT_ACTIVATED"}
DECISIONS=sorted({*(x for x in previous.DECISIONS if x!="H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION_REVIEW=REQUIRED"),"H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION_REVIEW=PASSED","H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION_REVIEW_RECORD=RECORDED","H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION_REVIEWED=TRUE","H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION_EFFECTIVE=FALSE","H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION_ACTIVATED=FALSE","H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION_ACTIVATION_TRANSITION=AUTHORIZED_FOR_INDEPENDENT_REVIEW_ONLY"})
BLOCKERS=sorted({*(x for x in previous.BLOCKERS if "candidate requires independent adversarial review" not in x),"H001 per-run coordinate and seed orchestration activation transition requires independent review"})
PROHIBITIONS=sorted({*previous.PROHIBITIONS,"ACTIVATE_H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION_BEFORE_SEPARATE_ACTIVATION_TRANSITION_IS_REVIEWED_AND_MERGED","MODIFY_PRIOR_AMENDMENTS_OR_HANDOFF_RECEIPTS_V001_THROUGH_V038"})

def validate(receipt,root):
 if receipt["receipt_index"]!=39 or receipt["phase"]!=PHASE or receipt["source_branch"]!=BRANCH or receipt["source_head_commit"]!=BASE_SHA:c._fail("H001 per-run review-completion identity drifted")
 if receipt["predecessor"]!={"path":previous.HANDOFF_RELPATH,"sha256":V038_SHA}:c._fail("H001 per-run review-completion predecessor is wrong")
 for k,v in (("changed_file_scope",SCOPE),("next_actions",[NEXT_ACTION]),("decisions",DECISIONS),("blockers",BLOCKERS),("prohibited_actions",PROHIBITIONS),("per_run_coordinate_and_seed_orchestration_binding",BINDING)):
  if receipt[k]!=v:c._fail(f"H001 per-run review-completion {k} drifted")
 if receipt["safety_state"]!=dict(c._EXPECTED_SAFETY,real_data_execution_requested=False):c._fail("H001 per-run review-completion safety drifted")
 for p,h in PROTECTED.items():
  if not (root/p).is_file() or hashlib.sha256((root/p).read_bytes()).hexdigest()!=h:c._fail("H001 per-run review-completion protected evidence drifted")
 raw=(root/REVIEW_RELPATH).read_bytes()
 if hashlib.sha256(raw).hexdigest()!=REVIEW_SHA:c._fail("H001 per-run review record hash drifted")
 review=c._load_canonical_document(raw,"H001 per-run review record")
 if review.get("review_verdict")!="PASS" or any(review.get(k)!=0 for k in ("blocker_count","major_count","minor_count")) or review.get("reviewed_head_sha")!="1bbeadb4c30cae19db1644bb54178f79536c168e" or review.get("reviewed_tree_sha")!="57107e3f12899474973bee6cad2a79c6acd0015f" or review.get("reviewed_pr")!=322 or review.get("merge_commit_sha")!="77208b58d1bd086f9bbb917eca91cc57148c4b8e":c._fail("H001 per-run review record binding is wrong")
 expected=[{"path":p,"sha256":h} for p,h in PROTECTED.items()]+[{"path":REVIEW_RELPATH,"sha256":REVIEW_SHA}]
 if receipt["evidence"]!=expected:c._fail("H001 per-run review-completion evidence is wrong")
 if receipt["current_transition_files"]!=[{"path":p,"sha256":hashlib.sha256((root/p).read_bytes()).hexdigest()} for p in CURRENT_FILES]:c._fail("H001 per-run review-completion transition files drifted")
 if any(receipt["per_run_coordinate_and_seed_orchestration_binding"][x] for x in ("orchestration_effective","orchestration_activated","orchestration_executed","orchestration_wired_into_execute_calibration")):c._fail("H001 per-run review completion cannot activate or execute")
