"""Canonical v049 failure record for the reviewed v048 dispatcher candidate."""

import hashlib

from . import context as c
from . import external_trust_root_dispatcher_repair_candidate_v048 as previous

PHASE = "external_trust_root_dispatcher_v1_successor_state_repair_required"
NEXT_ACTION = "CONSTRUCT_EXTERNAL_TRUST_ROOT_DISPATCHER_SUCCESSOR_STATE_REPAIR_CANDIDATE_FOR_REVIEW"
HANDOFF_RELPATH = f"docs/control/tasks/{c.TASK_ID}/handoff_v049.json"
V048_COMMIT = "1b422c6a79358f0f01f8284aae70532a703fd6e7"
V048_TREE = "734dd3cb05c9a92b92a5604024ebc3e598739f12"
V048_PARENT = "459d68c88f1a1ea71a6099f17a50ffbd860868e5"
V048_HANDOFF_SHA = "66c03c175ab2f152f8d29df3eacb19957695c53918f74910483662c91972df01"
V048_BINDING = {
    "commit": V048_COMMIT,
    "tree": V048_TREE,
    "parent": V048_PARENT,
    "handoff_path": previous.HANDOFF_RELPATH,
    "handoff_sha256": V048_HANDOFF_SHA,
    "phase_before_review": previous.PHASE,
    "review_outcome": "V048_REPAIR_REQUIRED",
    "amended": False,
    "released": False,
    "retroactively_approved": False,
    "finding": {
        "id": "H002",
        "severity": "BLOCKING",
        "class": "AUTHORITY_SUCCESSOR_STATE_LIVENESS",
        "invariant_violated": "released D must authenticate legitimate governed successor authority states while rejecting hostile successor states, without changing reviewed D bytes for every registry transition and without reopening caller-selected authority",
        "evidence": [
            "v048 pins exact v047 authority state",
            "v047 registry is empty",
            "no authenticated successor-state transition exists",
        ],
        "result": "legitimate R1 and hostile R_bad are both unreachable",
        "conclusion": "v048 repairs v046 safety but fails authority-state liveness",
    },
}
AUTHORITY = previous.previous.AUTHORITY
CURRENT_FILES = [
    "quantbot/continuity/context.py",
    "quantbot/continuity/external_trust_root_dispatcher_repair_failure_v049.py",
    "tests/continuity/test_external_trust_root_dispatcher_repair_failure_v049.py",
    "tests/control/governance_baseline.json",
]
SCOPE = [HANDOFF_RELPATH, c.ACTIVE_TASK_RELPATH, *CURRENT_FILES]
PROTECTED = {
    **previous.PROTECTED,
    previous.HANDOFF_RELPATH: V048_HANDOFF_SHA,
    "quantbot/continuity/external_trust_root_dispatcher_v1.py": "f06a1da3f6dcf31ac8657bfad3a21a019a1ebadacdca1af92db2e42cd53a99fc",
}


def validate(receipt, root):
    if receipt["receipt_index"] != 49 or receipt["phase"] != PHASE:
        c._fail("v049 dispatcher failure receipt identity drifted")
    if receipt["source_branch"] != "chore/external-trust-root-dispatcher-repair-v046" or receipt["source_head_commit"] != V048_COMMIT:
        c._fail("v049 dispatcher failure reviewed-object identity drifted")
    if receipt["predecessor"] != {"path": previous.HANDOFF_RELPATH, "sha256": V048_HANDOFF_SHA}:
        c._fail("v049 dispatcher failure predecessor is wrong")
    if receipt["changed_file_scope"] != SCOPE or receipt["next_actions"] != [NEXT_ACTION]:
        c._fail("v049 dispatcher failure scope or next action drifted")
    if receipt["v046_failed_review_binding"] != previous.previous.V046_BINDING or receipt["v048_failed_review_binding"] != V048_BINDING or receipt["authority_state"] != AUTHORITY:
        c._fail("v049 dispatcher failure finding or authority drifted")
    if receipt["safety_state"] != dict(c._EXPECTED_SAFETY, real_data_execution_requested=False):
        c._fail("v049 dispatcher failure safety drifted")
    for path, digest in PROTECTED.items():
        if not (root / path).is_file() or hashlib.sha256((root / path).read_bytes()).hexdigest() != digest:
            c._fail("v049 dispatcher failure protected reviewed evidence drifted")
    expected_current = [{"path": path, "sha256": hashlib.sha256((root / path).read_bytes()).hexdigest()} for path in CURRENT_FILES]
    if receipt["current_transition_files"] != expected_current:
        c._fail("v049 dispatcher failure transition files drifted")
