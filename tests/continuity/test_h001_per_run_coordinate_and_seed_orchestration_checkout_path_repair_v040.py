import json, hashlib, shutil
import pytest
from quantbot.continuity import context
from quantbot.continuity import h001_per_run_coordinate_and_seed_orchestration_checkout_path_repair_v040 as v040
ROOT=__import__('pathlib').Path(__file__).parents[2]
def tree(tmp_path):
 root=tmp_path/'repo'; shutil.copytree(ROOT,root,ignore=shutil.ignore_patterns('.git','.venv','__pycache__')); return root
def write(root,r):
 p=root/v040.HANDOFF_RELPATH; p.write_bytes(context.canonical_json_bytes(r)); a=json.loads((root/context.ACTIVE_TASK_RELPATH).read_bytes()); a['handoff_receipt_sha256']=hashlib.sha256(p.read_bytes()).hexdigest(); (root/context.ACTIVE_TASK_RELPATH).write_bytes(context.canonical_json_bytes(a))
def test_v040_baseline(tmp_path): context.load_and_verify_continuity_state(tree(tmp_path))
def test_v040_rejects_authority(tmp_path):
 root=tree(tmp_path); r=json.loads((root/v040.HANDOFF_RELPATH).read_bytes()); r['v039_checkout_path_repair']['orchestration_activated']=True; write(root,r)
 with pytest.raises(ValueError): context.load_and_verify_continuity_state(root)
