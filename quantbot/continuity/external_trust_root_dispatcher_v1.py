"""Generic D-layer dispatcher; explicit-T execution is never authoritative."""
from __future__ import annotations
import hashlib, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path, PurePosixPath

VERSION="EXTERNAL_TRUST_ROOT_DISPATCHER_V1"; API="1"; REGISTRY_PATH="docs/control/external_trust_root_registry_v1.json"
# This is the immutable v047 failure-record state from which this candidate was
# constructed.  A released successor must deliberately change this binding as
# part of its own reviewed release; callers never supply its repository or SHA.
AUTHORITY_STATE_COMMIT="459d68c88f1a1ea71a6099f17a50ffbd860868e5"
class DispatchError(ValueError): pass

def _json(raw, label):
    def reject(pairs):
        d={}
        for k,v in pairs:
            if k in d: raise DispatchError(f"duplicate {label} key")
            d[k]=v
        return d
    try: return json.loads(raw, object_pairs_hook=reject)
    except (json.JSONDecodeError, DispatchError) as e: raise DispatchError(f"malformed {label}") from e

def _git_env(): return {"PATH":os.defpath,"GIT_CONFIG_NOSYSTEM":"1","GIT_CONFIG_GLOBAL":os.devnull,"GIT_CONFIG_SYSTEM":os.devnull,"GIT_NO_REPLACE_OBJECTS":"1","HOME":tempfile.gettempdir()}
def _git(repo,*args, binary=False):
    git=shutil.which("git",path=os.defpath)
    if not git: raise DispatchError("trusted git unavailable")
    try: return subprocess.check_output([git,"--no-replace-objects",*args],cwd=repo,env=_git_env(),stderr=subprocess.DEVNULL,text=not binary)
    except subprocess.CalledProcessError as e: raise DispatchError("git object lookup failed") from e
def _full_commit(repo, value):
    if type(value) is not str or len(value)!=40 or any(c not in "0123456789abcdef" for c in value): raise DispatchError("full lowercase commit SHA required")
    if _git(repo,"rev-parse",f"{value}^{{commit}}").strip()!=value: raise DispatchError("commit identity unavailable")
    return value
def _blob(repo,commit,path): return _git(repo,"show",f"{commit}:{path}",binary=True)
def _path(value):
    if type(value) is not str or not value or "\\" in value: raise DispatchError("unsafe bundle path")
    p=PurePosixPath(value)
    if p.is_absolute() or ".." in p.parts or str(p)!=value: raise DispatchError("unsafe bundle path")
    return p
def _descriptor(repo,t):
    d=_json(_blob(repo,t,"trust_root_descriptor.json"),"descriptor")
    if set(d)!={"dispatcher_version","api_version","entrypoint","files"} or d["dispatcher_version"]!=VERSION or d["api_version"]!=API or type(d["files"]) is not list or not d["files"]: raise DispatchError("descriptor schema mismatch")
    files={}
    for item in d["files"]:
        if type(item) is not dict or set(item)!={"path","sha256"} or type(item["sha256"]) is not str or len(item["sha256"])!=64 or any(c not in "0123456789abcdef" for c in item["sha256"]): raise DispatchError("bundle manifest mismatch")
        p=str(_path(item["path"]));
        if p in files: raise DispatchError("duplicate bundle path")
        files[p]=item["sha256"]
    entry=str(_path(d["entrypoint"]))
    if entry not in files: raise DispatchError("entrypoint absent from bundle")
    return entry,files
def run_verifier_from_exact_trust_root(repo, trust_root_commit, candidate_commit):
    """Non-authoritative mechanical test API. Both identities must be full SHAs."""
    repo=Path(repo).resolve(); t=_full_commit(repo,trust_root_commit); c=_full_commit(repo,candidate_commit); entry,files=_descriptor(repo,t)
    with tempfile.TemporaryDirectory(prefix="qnty-dispatcher-") as td:
        root=Path(td); bundle=root/"bundle"; bundle.mkdir()
        for path,digest in files.items():
            raw=_blob(repo,t,path)
            if hashlib.sha256(raw).hexdigest()!=digest: raise DispatchError("bundle digest mismatch")
            target=bundle/path; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(raw)
        candidate=root/"candidate"; candidate.mkdir()
        archive=root/"candidate.tar"; archive.write_bytes(_git(repo,"archive",c,binary=True))
        subprocess.run(["tar","-xf",str(archive),"-C",str(candidate),"--no-same-owner","--no-same-permissions"],check=True,env={"PATH":os.defpath})
        run=subprocess.run([sys.executable,"-I","-S",str(bundle/entry),str(candidate)],cwd=bundle,env={"PATH":os.defpath,"PYTHONNOUSERSITE":"1"},text=True,capture_output=True,timeout=15)
        if run.returncode!=0: raise DispatchError("verifier execution failed")
        result=_json(run.stdout,"result")
        if set(result)!={"status","findings"} or result["status"] not in {"VERIFIER_PASS","VERIFIER_REJECT"} or type(result["findings"]) is not list or any(type(x) is not dict for x in result["findings"]): raise DispatchError("result schema mismatch")
        return {"dispatcher_identity":VERSION,"trust_root_identity":t,"candidate_identity":c,"authoritative":False,**result}
def _registered_mechanical_result(repo, lane, candidate_commit, authority_state_commit):
    repo=Path(repo).resolve(); state=_full_commit(repo,authority_state_commit); c=_full_commit(repo,candidate_commit)
    registry=_json(_blob(repo,state,REGISTRY_PATH),"registry")
    if set(registry)!={"dispatcher_version","registry_version","lanes"} or registry["dispatcher_version"]!=VERSION or registry["registry_version"]!="1" or type(registry["lanes"]) is not dict or type(lane) is not str or not lane: raise DispatchError("registry schema mismatch")
    if lane not in registry["lanes"]: raise DispatchError("no authoritative trust root for lane")
    result=run_verifier_from_exact_trust_root(repo,registry["lanes"][lane],c)
    return {**result,"authority_state_identity":state,"lane":lane}

def verify_registered_candidate(repo, lane, candidate_commit, authority_state_commit):
    """Caller-selected registry execution, permanently mechanical-only."""
    return _registered_mechanical_result(repo, lane, candidate_commit, authority_state_commit)

def _trusted_repository_root():
    root=Path(__file__).resolve().parents[2]
    if _git(root,"rev-parse","--show-toplevel").strip()!=str(root):
        raise DispatchError("dispatcher is not installed in its trusted repository")
    return root

def verify_authoritative_candidate(lane, candidate_commit):
    """The sole authoritative route: released D -> pinned released state -> R -> T -> C."""
    repo=_trusted_repository_root()
    result=_registered_mechanical_result(repo,lane,candidate_commit,AUTHORITY_STATE_COMMIT)
    return {**result,"authoritative":True}
