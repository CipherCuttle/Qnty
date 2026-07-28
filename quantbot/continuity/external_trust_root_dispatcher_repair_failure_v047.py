"""Canonical v047 failure record for the rejected v046 dispatcher candidate."""

import hashlib

from . import context as c
from . import external_trust_root_dispatcher_repair_candidate_v046 as previous

PHASE = "external_trust_root_dispatcher_v1_repair_required"
NEXT_ACTION = "CREATE_EXTERNAL_TRUST_ROOT_DISPATCHER_REPAIR_CANDIDATE_FOR_REVIEW"
HANDOFF_RELPATH = f"docs/control/tasks/{c.TASK_ID}/handoff_v047.json"
V046_COMMIT = "adff852b189475d51b9637c5b71e7b21f2cfb038"
V046_TREE = "83f9a3832a06adc5690cf5f4ee225e01b72af7d6"
V046_PARENT = "ea6247e19c0130d465e76230fd5d49af6f2f76d2"
V046_HANDOFF_SHA = "2cef7bbb09e8a8ea46c7d4a515962325ba5d7d5b9c56666e37162ffaa69bbb45"
V046_BINDING = {
    "commit": V046_COMMIT,
    "tree": V046_TREE,
    "parent": V046_PARENT,
    "handoff_path": previous.HANDOFF_RELPATH,
    "handoff_sha256": V046_HANDOFF_SHA,
    "phase_before_review": previous.PHASE,
    "review_outcome": "V046_REPAIR_REQUIRED",
    "amended": False,
    "released": False,
    "retroactively_approved": False,
    "finding": {
        "id": "H001",
        "severity": "BLOCKING",
        "invariant_violated": "only released registry/state can grant T authority",
        "root_cause": "caller controls authoritative repository and authority_state_commit",
        "hostile_repository_state": "fresh hostile repository and state selected through the public authoritative API",
        "hostile_result": {"authoritative": True, "status": "VERIFIER_PASS"},
        "conclusion": "strict internal verification != external authority; attacker-selected repository/state can produce authoritative PASS",
    },
}
AUTHORITY = previous.AUTHORITY
CURRENT_FILES = [
    "quantbot/continuity/context.py",
    "quantbot/continuity/external_trust_root_dispatcher_repair_failure_v047.py",
    "tests/continuity/test_external_trust_root_dispatcher_repair_failure_v047.py",
    "tests/control/governance_baseline.json",
]
SCOPE = [HANDOFF_RELPATH, c.ACTIVE_TASK_RELPATH, *CURRENT_FILES]
PROTECTED = {
    **previous.PROTECTED,
    previous.HANDOFF_RELPATH: V046_HANDOFF_SHA,
    previous.AMENDMENT_RELPATH: "4102fd99f344e77aacbb3b150bf18943f099fd7819b91aaf58e503ba7152f52b",
    previous.REGISTRY_RELPATH: "fb67aa805d155d8f1f43ddc4e70682a06b9f8388aaf98d629bc9add48100208f",
    previous.DISPATCHER_RELPATH: "fb5442173097fb567af8192c346925f6c540e3cfd995872fbaaa589f7ea472e8",
}


def validate(receipt, root):
    if receipt["receipt_index"] != 47 or receipt["phase"] != PHASE:
        c._fail("v047 dispatcher failure receipt identity drifted")
    if receipt["source_branch"] != "chore/external-trust-root-dispatcher-repair-v046" or receipt["source_head_commit"] != V046_COMMIT:
        c._fail("v047 dispatcher failure reviewed-object identity drifted")
    if receipt["predecessor"] != {"path": previous.HANDOFF_RELPATH, "sha256": V046_HANDOFF_SHA}:
        c._fail("v047 dispatcher failure predecessor is wrong")
    if receipt["changed_file_scope"] != SCOPE or receipt["next_actions"] != [NEXT_ACTION]:
        c._fail("v047 dispatcher failure scope or next action drifted")
    if receipt["v046_failed_review_binding"] != V046_BINDING or receipt["authority_state"] != AUTHORITY:
        c._fail("v047 dispatcher failure finding or authority drifted")
    if receipt["safety_state"] != dict(c._EXPECTED_SAFETY, real_data_execution_requested=False):
        c._fail("v047 dispatcher failure safety drifted")
    for path, digest in PROTECTED.items():
        if not (root / path).is_file() or hashlib.sha256((root / path).read_bytes()).hexdigest() != digest:
            c._fail("v047 dispatcher failure protected reviewed evidence drifted")
    expected_current = [{"path": path, "sha256": hashlib.sha256((root / path).read_bytes()).hexdigest()} for path in CURRENT_FILES]
    if receipt["current_transition_files"] != expected_current:
        c._fail("v047 dispatcher failure transition files drifted")
