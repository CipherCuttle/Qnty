import copy, hashlib, json, shutil
import pytest
from quantbot.continuity import context
from quantbot.continuity import h001_per_run_coordinate_and_seed_orchestration_review_completion_v039 as v039
ROOT=__import__('pathlib').Path(__file__).parents[2]
def tree(tmp_path):
 root=tmp_path/'repo'; shutil.copytree(ROOT,root,ignore=shutil.ignore_patterns('.git','.venv','__pycache__')); return root
def write(root,r):
 p=root/v039.HANDOFF_RELPATH; p.write_bytes(context.canonical_json_bytes(r)); a=json.loads((root/context.ACTIVE_TASK_RELPATH).read_bytes()); a['handoff_receipt_sha256']=hashlib.sha256(p.read_bytes()).hexdigest(); (root/context.ACTIVE_TASK_RELPATH).write_bytes(context.canonical_json_bytes(a))
def fail(root):
 with pytest.raises(ValueError): context.load_and_verify_continuity_state(root)
def test_v039_baseline(tmp_path): context.load_and_verify_continuity_state(tree(tmp_path))
@pytest.mark.parametrize('field',['orchestration_effective','orchestration_activated','orchestration_executed','orchestration_wired_into_execute_calibration'])
def test_v039_rejects_authority(tmp_path,field):
 root=tree(tmp_path); r=json.loads((root/v039.HANDOFF_RELPATH).read_bytes()); r['per_run_coordinate_and_seed_orchestration_binding'][field]=True; write(root,r); fail(root)
def test_v039_rejects_wrong_next_action(tmp_path):
 root=tree(tmp_path); r=json.loads((root/v039.HANDOFF_RELPATH).read_bytes()); r['next_actions']=['EXECUTE_H001_PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION']; write(root,r); fail(root)
def test_v039_rejects_review_substitution(tmp_path):
 root=tree(tmp_path); p=root/v039.REVIEW_RELPATH; p.write_bytes(p.read_bytes()+b' '); fail(root)
def test_v039_rejects_candidate_mutation(tmp_path):
 root=tree(tmp_path); p=root/v039.previous.ORCH_RELPATH; p.write_bytes(p.read_bytes()+b'\n# tampered\n'); fail(root)
