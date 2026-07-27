import copy,hashlib,json,shutil
import pytest
from quantbot.continuity import context
from quantbot.continuity import h001_scientific_contract_reconciliation_candidate_v042 as v
ROOT=__import__('pathlib').Path(__file__).parents[2]
def tree(tmp_path):
 root=tmp_path/'repo';shutil.copytree(ROOT,root,ignore=shutil.ignore_patterns('.git','.venv','__pycache__'));return root
def write(root,r):
 p=root/v.HANDOFF_RELPATH;p.write_bytes(context.canonical_json_bytes(r));a=json.loads((root/context.ACTIVE_TASK_RELPATH).read_bytes());a['handoff_receipt_sha256']=hashlib.sha256(p.read_bytes()).hexdigest();(root/context.ACTIVE_TASK_RELPATH).write_bytes(context.canonical_json_bytes(a))
def fail(root):
 with pytest.raises(ValueError):context.load_and_verify_continuity_state(root)
def receipt(root):return json.loads((root/v.HANDOFF_RELPATH).read_bytes())
def test_v042_baseline(tmp_path):context.load_and_verify_continuity_state(tree(tmp_path))
@pytest.mark.parametrize(('path','value'),[(('proposed_c1','primary_family_statistic'),'max_abs_tstar'),(('proposed_c1','family_size'),8),(('proposed_c1','familywise_alpha'),.1),(('proposed_c2','funding_availability_rule'),'funding_timestamp <= decision_timestamp'),(('authorization_state','activation_authorized'),True),(('authorization_state','candidate_review_completed'),True),(('authorization_state','real_data_access_authorized'),True),(('dependent_repair_boundary','implementation_repair_complete'),True)])
def test_v042_rejects_semantic_or_authority_drift(tmp_path,path,value):
 root=tree(tmp_path);a=json.loads((root/v.AMENDMENT_RELPATH).read_bytes());a[path[0]][path[1]]=value;(root/v.AMENDMENT_RELPATH).write_bytes(context.canonical_json_bytes(a));fail(root)
def test_v042_rejects_missing_p0_finding(tmp_path):
 root=tree(tmp_path);a=json.loads((root/v.AMENDMENT_RELPATH).read_bytes());a['audit_binding']['p0_findings'].pop();(root/v.AMENDMENT_RELPATH).write_bytes(context.canonical_json_bytes(a));fail(root)
def test_v042_rejects_wrong_audited_commit(tmp_path):
 root=tree(tmp_path);a=json.loads((root/v.AMENDMENT_RELPATH).read_bytes());a['audit_binding']['audited_commit']='0'*40;(root/v.AMENDMENT_RELPATH).write_bytes(context.canonical_json_bytes(a));fail(root)
def test_v042_rejects_next_action_drift(tmp_path):
 root=tree(tmp_path);r=receipt(root);r['next_actions']=['IMPLEMENT_H001_SCIENTIFIC_CONTRACT_RECONCILIATION_DEPENDENT_REPAIRS'];write(root,r);fail(root)
