import hashlib,json,os,subprocess
import pytest
from quantbot.continuity.external_trust_root_dispatcher_v1 import DispatchError,VERSION,run_verifier_from_exact_trust_root,verify_registered_candidate
from quantbot.continuity import context
from quantbot.continuity import external_trust_root_dispatcher_repair_candidate_v046 as v046
import shutil
def sh(r,*a): return subprocess.check_output(a,cwd=r,text=True).strip()
def commit(r,files):
 for p,b in files.items(): x=r/p;x.parent.mkdir(parents=True,exist_ok=True);x.write_bytes(b)
 sh(r,"git","add",".");sh(r,"git","-c","user.email=a@b","-c","user.name=a","commit","-m","x");return sh(r,"git","rev-parse","HEAD")
def fixture(tmp_path, code=b'import json;print(json.dumps({"status":"VERIFIER_PASS","findings":[]}))'):
 r=tmp_path/str(len(list(tmp_path.iterdir())));sh(tmp_path,'git','init',str(r)); d={"dispatcher_version":VERSION,"api_version":"1","entrypoint":"verify.py","files":[{"path":"verify.py","sha256":hashlib.sha256(code).hexdigest()}]};t=commit(r,{"trust_root_descriptor.json":json.dumps(d).encode(),"verify.py":code});c=commit(r,{"candidate.json":b'{}'});return r,t,c
def test_mechanical_is_not_authoritative_and_empty_registry_fails_closed(tmp_path):
 r,t,c=fixture(tmp_path);assert run_verifier_from_exact_trust_root(r,t,c)['authoritative'] is False
 reg=commit(r,{"docs/control/external_trust_root_registry_v1.json":json.dumps({"dispatcher_version":VERSION,"registry_version":"1","lanes":{}}).encode()})
 with pytest.raises(DispatchError): verify_registered_candidate(r,'any',c,reg)
def test_nonzero_duplicate_and_bad_result_reject(tmp_path):
 for code in (b'import json;print(json.dumps({"status":"VERIFIER_PASS","findings":[]}));raise SystemExit(1)',b'print("{\\"status\\":\\"VERIFIER_REJECT\\",\\"status\\":\\"VERIFIER_PASS\\",\\"findings\\":[]}")',b'import json;print(json.dumps({"status":"VERIFIER_PASS","findings":"x"}))'):
  r,t,c=fixture(tmp_path,code)
  with pytest.raises(DispatchError): run_verifier_from_exact_trust_root(r,t,c)
def test_full_sha_descriptor_and_git_environment_are_strict(tmp_path,monkeypatch):
 r,t,c=fixture(tmp_path); monkeypatch.setenv('GIT_DIR','/nope'); monkeypatch.setenv('PATH','/nope')
 assert run_verifier_from_exact_trust_root(r,t,c)['status']=='VERIFIER_PASS'
 with pytest.raises(DispatchError): run_verifier_from_exact_trust_root(r,t[:8],c)
 monkeypatch.undo()
 bad=commit(r,{"trust_root_descriptor.json":json.dumps({"dispatcher_version":VERSION,"api_version":"999","entrypoint":"verify.py","files":[]}).encode()})
 with pytest.raises(DispatchError): run_verifier_from_exact_trust_root(r,bad,c)
def test_registered_mapping_derives_t_and_candidate_cannot_supply_it(tmp_path):
 r,t,c=fixture(tmp_path)
 state=commit(r,{"docs/control/external_trust_root_registry_v1.json":json.dumps({"dispatcher_version":VERSION,"registry_version":"1","lanes":{"generic":t}}).encode()})
 assert verify_registered_candidate(r,"generic",c,state)["trust_root_identity"]==t
 with pytest.raises(DispatchError): verify_registered_candidate(r,"other",c,state)

ROOT = __import__("pathlib").Path(__file__).parents[2]
def _tree(tmp_path):
 root=tmp_path/"repo"; shutil.copytree(ROOT,root,ignore=shutil.ignore_patterns(".git",".venv","__pycache__")); return root
def _write(root, receipt):
 path=root/v046.HANDOFF_RELPATH; path.write_bytes(context.canonical_json_bytes(receipt))
 active=json.loads((root/context.ACTIVE_TASK_RELPATH).read_bytes()); active["handoff_receipt_sha256"]=hashlib.sha256(path.read_bytes()).hexdigest(); (root/context.ACTIVE_TASK_RELPATH).write_bytes(context.canonical_json_bytes(active))
def _receipt(root): return json.loads((root/v046.HANDOFF_RELPATH).read_bytes())
def _reject(root):
 with pytest.raises(ValueError): context.load_and_verify_continuity_state(root)
def test_v046_baseline_verifies(tmp_path): context.load_and_verify_continuity_state(_tree(tmp_path))
@pytest.mark.parametrize(("path","value"),[("v045_failed_review_binding.commit","0"*40),("v045_failed_review_binding.tree","0"*40),("v045_failed_review_binding.review_outcome","PASS"),("v045_failed_review_binding.retroactively_approved",True),("phase","wrong"),("next_actions",["RELEASE_EXTERNAL_TRUST_ROOT_DISPATCHER"]),("authority_state.dispatcher_released",True),("authority_state.trust_root_registered",True),("authority_state.c1_semantic_trust_root_promoted",True),("authority_state.h001_execution_budget",1),("authority_state.h001_execution_count",1),("authority_state.h001_activated",True),("authority_state.real_data_access",True),("authority_state.holdout_access",True),("authority_state.c2_resolved",True)])
def test_v046_rejects_failed_review_or_authority_drift(tmp_path,path,value):
 root=_tree(tmp_path); receipt=_receipt(root); target=receipt
 parts=path.split(".")
 for part in parts[:-1]: target=target[part]
 target[parts[-1]]=value; _write(root,receipt); _reject(root)
