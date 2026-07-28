"""Canonical v048 authority-root repair candidate for the generic dispatcher."""

import hashlib

from . import context as c
from . import external_trust_root_dispatcher_repair_failure_v047 as previous

PHASE = "external_trust_root_dispatcher_v1_authority_root_repair_candidate_review_required"
NEXT_ACTION = "ADVERSARIAL_REVIEW_EXTERNAL_TRUST_ROOT_DISPATCHER_REPAIR_CANDIDATE"
HANDOFF_RELPATH = f"docs/control/tasks/{c.TASK_ID}/handoff_v048.json"
V047_COMMIT = "459d68c88f1a1ea71a6099f17a50ffbd860868e5"
V047_TREE = "9b50297d17ebe111fbe066f7e9bd05b9eee064c9"
V047_HANDOFF_SHA = "a5c133993aeb806d4b609d7b6ad45857635390478952492e47fe022b7b80baac"
CURRENT_FILES = [
    "quantbot/continuity/context.py",
    "quantbot/continuity/external_trust_root_dispatcher_v1.py",
    "quantbot/continuity/external_trust_root_dispatcher_repair_candidate_v048.py",
    "tests/continuity/test_external_trust_root_dispatcher_v1.py",
    "tests/continuity/test_external_trust_root_dispatcher_repair_candidate_v048.py",
    "tests/control/governance_baseline.json",
]
SCOPE = [HANDOFF_RELPATH, c.ACTIVE_TASK_RELPATH, *CURRENT_FILES]
PROTECTED = {
    path: digest
    for path, digest in previous.PROTECTED.items()
    if path != previous.previous.DISPATCHER_RELPATH
}


def validate(receipt, root):
    if receipt["receipt_index"] != 48 or receipt["phase"] != PHASE:
        c._fail("v048 dispatcher repair receipt identity drifted")
    if receipt["source_branch"] != "chore/external-trust-root-dispatcher-repair-v046" or receipt["source_head_commit"] != V047_COMMIT:
        c._fail("v048 dispatcher repair reviewed-object identity drifted")
    if receipt["predecessor"] != {"path": previous.HANDOFF_RELPATH, "sha256": V047_HANDOFF_SHA}:
        c._fail("v048 dispatcher repair predecessor is wrong")
    if receipt["changed_file_scope"] != SCOPE or receipt["next_actions"] != [NEXT_ACTION]:
        c._fail("v048 dispatcher repair scope or next action drifted")
    if receipt["v046_failed_review_binding"] != previous.V046_BINDING or receipt["authority_state"] != previous.AUTHORITY:
        c._fail("v048 dispatcher repair failure binding or authority drifted")
    if receipt["safety_state"] != dict(c._EXPECTED_SAFETY, real_data_execution_requested=False):
        c._fail("v048 dispatcher repair safety drifted")
    for path, digest in PROTECTED.items():
        if not (root / path).is_file() or hashlib.sha256((root / path).read_bytes()).hexdigest() != digest:
            c._fail("v048 dispatcher repair protected failed evidence drifted")
    expected = [{"path": path, "sha256": hashlib.sha256((root / path).read_bytes()).hexdigest()} for path in CURRENT_FILES]
    if receipt["current_transition_files"] != expected:
        c._fail("v048 dispatcher repair transition files drifted")
