"""Prospective H001 scientific-contract reconciliation candidate, review required."""
import hashlib
from . import context as c
from . import h001_per_run_coordinate_and_seed_orchestration_checkout_path_repair_review_completion_v041 as previous

PHASE="candidate1_h001_scientific_contract_reconciliation_candidate_review_required"
NEXT_ACTION="ADVERSARIAL_REVIEW_H001_SCIENTIFIC_CONTRACT_RECONCILIATION_CANDIDATE"
HANDOFF_RELPATH=f"docs/control/tasks/{c.TASK_ID}/handoff_v042.json"
AMENDMENT_RELPATH="docs/control/amendments/candidate1_h001_scientific_contract_reconciliation_candidate_v001.json"
BRANCH="chore/h001-scientific-contract-reconciliation-v042"
BASE_SHA="5cf88b93467e18be31158a58d0fc9fdee9a6b492"
V041_SHA="c90088efd7bc034f52c33c13f9168788e27e34e2fb91b774d8dd576afb0e3c10"
CURRENT_FILES=["quantbot/continuity/context.py","quantbot/continuity/h001_scientific_contract_reconciliation_candidate_v042.py","tests/continuity/test_h001_scientific_contract_reconciliation_candidate_v042.py","tests/control/governance_baseline.json"]
SCOPE=[AMENDMENT_RELPATH,HANDOFF_RELPATH,c.ACTIVE_TASK_RELPATH,*CURRENT_FILES]
PROTECTED={**previous.PROTECTED,previous.HANDOFF_RELPATH:V041_SHA}
DECISIONS=sorted({*previous.DECISIONS,"H001_SCIENTIFIC_CONTRACT_RECONCILIATION_CANDIDATE=CREATED_FOR_INDEPENDENT_REVIEW","H001_SCIENTIFIC_CONTRACT_RECONCILIATION_REVIEW=REQUIRED","H001_SCIENTIFIC_CONTRACT_RECONCILIATION_ACTIVATION=PROHIBITED_PENDING_INDEPENDENT_REVIEW","H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION_ACTIVATION=BLOCKED_PENDING_SCIENTIFIC_CONTRACT_RECONCILIATION"})
BLOCKERS=sorted({*(x for x in previous.BLOCKERS if x != "H001 activation blocked pending scientific-consistency audit"),"H001 scientific-contract reconciliation candidate requires independent adversarial review","H001 activation blocked pending reviewed scientific-contract reconciliation and separate dependent implementation repair"})
PROHIBITIONS=sorted({*previous.PROHIBITIONS,"ACTIVATE_H001_SCIENTIFIC_CONTRACT_RECONCILIATION_BEFORE_INDEPENDENT_REVIEW","IMPLEMENT_H001_SCIENTIFIC_CONTRACT_RECONCILIATION_DEPENDENT_REPAIRS_BEFORE_INDEPENDENT_REVIEW","MODIFY_H001_SCIENTIFIC_CONTRACT_RECONCILIATION_CANDIDATE_VALUES_AFTER_LOCK","MODIFY_PRIOR_AMENDMENTS_OR_HANDOFF_RECEIPTS_V001_THROUGH_V041","TREAT_H001_SCIENTIFIC_CONTRACT_RECONCILIATION_CANDIDATE_AS_IMPLEMENTATION_OR_EXECUTION_AUTHORIZATION"})

def validate(receipt,root):
 if receipt["receipt_index"]!=42 or receipt["phase"]!=PHASE or receipt["source_branch"]!=BRANCH or receipt["source_head_commit"]!=BASE_SHA:c._fail("H001 scientific-contract reconciliation candidate identity drifted")
 if receipt["predecessor"]!={"path":previous.HANDOFF_RELPATH,"sha256":V041_SHA}:c._fail("H001 scientific-contract reconciliation candidate predecessor drifted")
 for k,v in (("changed_file_scope",SCOPE),("next_actions",[NEXT_ACTION]),("decisions",DECISIONS),("blockers",BLOCKERS),("prohibited_actions",PROHIBITIONS)):
  if receipt[k]!=v:c._fail(f"H001 scientific-contract reconciliation candidate {k} drifted")
 if receipt["safety_state"]!=dict(c._EXPECTED_SAFETY,real_data_execution_requested=False):c._fail("H001 scientific-contract reconciliation candidate safety drifted")
 for p,h in PROTECTED.items():
  if not (root/p).is_file() or hashlib.sha256((root/p).read_bytes()).hexdigest()!=h:c._fail("H001 scientific-contract reconciliation protected evidence drifted")
 raw=(root/AMENDMENT_RELPATH).read_bytes(); a=c._load_canonical_document(raw,"H001 scientific-contract reconciliation amendment")
 if a["status"]!="CANDIDATE_REVIEW_REQUIRED_NOT_EFFECTIVE_NOT_IMPLEMENTED" or a["audit_binding"]["audited_commit"]!=BASE_SHA or a["audit_binding"]["verdict"]!="REPAIR_REQUIRED_BEFORE_ACTIVATION" or a["audit_binding"]["p0_findings"]!=["C1_DIRECTIONALITY_CONTRACT_RECONCILIATION","C2_TEMPORAL_BOUNDARY_CONTRACT_RECONCILIATION"]:c._fail("H001 scientific-contract reconciliation audit binding drifted")
 c1=a["proposed_c1"]; c2=a["proposed_c2"]; auth=a["authorization_state"]
 if c1!={"alternative":"H_A,i: mu_i > 0","family_size":9,"familywise_alpha":0.05,"observed_statistic":"signed_HAC_studentized_t_i","primary_family_statistic":"max_j_tstar_j_b","primary_pvalue":"(1 + sum_b 1[Mstar_b >= t_i]) / (B + 1)","symmetric_absolute_primary_inference_forbidden":True} or c2!={"decision_time_equality_available":False,"funding_availability_rule":"funding_timestamp < decision_timestamp"}:c._fail("H001 scientific-contract reconciliation semantics drifted")
 if any(auth[k] for k in ("activation_authorized","candidate_review_completed","execution_authorized","live_authorized","paper_trade_authorized","real_data_access_authorized","scientific_authorized","wired_into_execute_calibration")) or auth["h001_execution_budget"]!=0 or auth["h001_execution_count"]!=0 or a["dependent_repair_boundary"]["implementation_repair_complete"]:c._fail("H001 scientific-contract reconciliation authority drifted")
 expected_evidence=[{"path":p,"sha256":h} for p,h in PROTECTED.items()]+[{"path":AMENDMENT_RELPATH,"sha256":hashlib.sha256(raw).hexdigest()}]
 if receipt["evidence"]!=expected_evidence:c._fail("H001 scientific-contract reconciliation evidence drifted")
 if receipt["current_transition_files"] != [{"path": p, "sha256": hashlib.sha256((root / p).read_bytes()).hexdigest()} for p in CURRENT_FILES]: c._fail("H001 scientific-contract reconciliation transition files drifted")
