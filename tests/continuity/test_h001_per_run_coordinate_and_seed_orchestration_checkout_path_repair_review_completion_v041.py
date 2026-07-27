import hashlib,json,shutil
import pytest
from quantbot.continuity import context
from quantbot.continuity import h001_per_run_coordinate_and_seed_orchestration_checkout_path_repair_review_completion_v041 as v
ROOT=__import__('pathlib').Path(__file__).parents[2]
def tree(tmp_path):
 root=tmp_path/'repo'; shutil.copytree(ROOT,root,ignore=shutil.ignore_patterns('.git','.venv','__pycache__')); return root
def write(root,r):
 p=root/v.HANDOFF_RELPATH; p.write_bytes(context.canonical_json_bytes(r)); a=json.loads((root/context.ACTIVE_TASK_RELPATH).read_bytes()); a['handoff_receipt_sha256']=hashlib.sha256(p.read_bytes()).hexdigest(); (root/context.ACTIVE_TASK_RELPATH).write_bytes(context.canonical_json_bytes(a))
def test_v041_baseline(tmp_path): context.load_and_verify_continuity_state(tree(tmp_path))
@pytest.mark.parametrize('field,value',[('reviewed_commit','0'*40),('reviewed_tree','0'*40),('reviewed_v040_handoff_sha256','0'*64),('review_verdict','FAIL'),('orchestration_activated',True),('orchestration_executed',True)])
def test_v041_rejects_review_or_authority_drift(tmp_path,field,value):
 root=tree(tmp_path); r=json.loads((root/v.HANDOFF_RELPATH).read_bytes()); r['v040_review_binding'][field]=value; write(root,r)
 with pytest.raises(ValueError): context.load_and_verify_continuity_state(root)
@pytest.mark.parametrize(('field','value'),[('decomposition_execution_budget',2),('decomposition_execution_count',1),('scientific_use_authorized',True),('real_data_execution_requested',True)])
def test_v041_rejects_safety_drift(tmp_path,field,value):
 root=tree(tmp_path); r=json.loads((root/v.HANDOFF_RELPATH).read_bytes()); r['safety_state'][field]=value; write(root,r)
 with pytest.raises(ValueError): context.load_and_verify_continuity_state(root)
def test_v041_rejects_scope_drift(tmp_path):
 root=tree(tmp_path); r=json.loads((root/v.HANDOFF_RELPATH).read_bytes()); r['changed_file_scope'][0]='wrong'; write(root,r)
 with pytest.raises(ValueError): context.load_and_verify_continuity_state(root)
