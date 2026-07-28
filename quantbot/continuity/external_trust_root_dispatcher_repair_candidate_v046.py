"""Canonical v046 repair candidate for the generic external trust-root dispatcher."""

import hashlib

from . import context as c
from . import h001_per_run_coordinate_and_seed_orchestration_checkout_path_repair_review_completion_v041 as previous

PHASE = "external_trust_root_dispatcher_v1_repair_candidate_review_required"
NEXT_ACTION = "ADVERSARIAL_REVIEW_EXTERNAL_TRUST_ROOT_DISPATCHER_REPAIR_CANDIDATE"
HANDOFF_RELPATH = f"docs/control/tasks/{c.TASK_ID}/handoff_v046.json"
BASE_SHA = "5cf88b93467e18be31158a58d0fc9fdee9a6b492"
REPAIR_COMMITS = ["48bfd4a0f2d74ef7e682003adb1064bb994fe5ff", "ea6247e19c0130d465e76230fd5d49af6f2f76d2"]
V041_SHA = "c90088efd7bc034f52c33c13f9168788e27e34e2fb91b774d8dd576afb0e3c10"
AMENDMENT_RELPATH = "docs/control/amendments/external_trust_root_dispatcher_v1_repair_candidate.json"
REGISTRY_RELPATH = "docs/control/external_trust_root_registry_v1.json"
DISPATCHER_RELPATH = "quantbot/continuity/external_trust_root_dispatcher_v1.py"
TEST_RELPATH = "tests/continuity/test_external_trust_root_dispatcher_v1.py"
CURRENT_FILES = [
    "quantbot/continuity/context.py",
    "quantbot/continuity/external_trust_root_dispatcher_repair_candidate_v046.py",
    TEST_RELPATH,
    "tests/control/governance_baseline.json",
]
SCOPE = [AMENDMENT_RELPATH, REGISTRY_RELPATH, DISPATCHER_RELPATH, TEST_RELPATH, HANDOFF_RELPATH, c.ACTIVE_TASK_RELPATH, *CURRENT_FILES[:2], "tests/control/governance_baseline.json"]
PROTECTED = {**previous.PROTECTED, previous.HANDOFF_RELPATH: V041_SHA}
V045_BINDING = {"commit": "461d4a06310af409c17d993d0f527ac85e874656", "tree": "a41cc4243ecb486b06cd8bc8507cd20240e712ab", "review_outcome": "V045_REPAIR_REQUIRED", "amended": False, "retroactively_approved": False, "released": False}
LINEAGE = {"released_governance_base": BASE_SHA, "unreviewed_construction_lineage": REPAIR_COMMITS, "rejected_review_evidence": V045_BINDING}
AUTHORITY = {"dispatcher_released": False, "trust_root_registry_empty": True, "trust_root_registered": False, "c1_semantic_trust_root_promoted": False, "c2_resolved": False, "h001_execution_budget": 0, "h001_execution_count": 0, "h001_activated": False, "h001_wired": False, "scientific_authorized": False, "real_data_access": False, "holdout_access": False}


def validate(receipt, root):
    if receipt["receipt_index"] != 46 or receipt["phase"] != PHASE or receipt["source_branch"] != "chore/external-trust-root-dispatcher-repair-v046" or receipt["source_head_commit"] != REPAIR_COMMITS[-1]:
        c._fail("v046 dispatcher repair receipt identity drifted")
    if receipt["predecessor"] != {"path": previous.HANDOFF_RELPATH, "sha256": V041_SHA}:
        c._fail("v046 dispatcher repair predecessor is wrong")
    if receipt["changed_file_scope"] != SCOPE or receipt["next_actions"] != [NEXT_ACTION]:
        c._fail("v046 dispatcher repair scope or next action drifted")
    if receipt["v045_failed_review_binding"] != V045_BINDING or receipt["construction_lineage"] != LINEAGE or receipt["authority_state"] != AUTHORITY:
        c._fail("v046 dispatcher repair lineage or authority drifted")
    if receipt["safety_state"] != dict(c._EXPECTED_SAFETY, real_data_execution_requested=False):
        c._fail("v046 dispatcher repair safety drifted")
    for path, digest in PROTECTED.items():
        if not (root / path).is_file() or hashlib.sha256((root / path).read_bytes()).hexdigest() != digest:
            c._fail("v046 dispatcher repair protected evidence drifted")
    if receipt["current_transition_files"] != [{"path": path, "sha256": hashlib.sha256((root / path).read_bytes()).hexdigest()} for path in CURRENT_FILES]:
        c._fail("v046 dispatcher repair transition files drifted")
    amendment = c._load_canonical_document((root / AMENDMENT_RELPATH).read_bytes(), "v046 dispatcher amendment")
    registry = c._load_canonical_document((root / REGISTRY_RELPATH).read_bytes(), "v046 dispatcher registry")
    if amendment["status"] != "CANDIDATE_REVIEW_REQUIRED_NOT_RELEASED" or any(amendment[key] is not False for key in ("amended", "retroactively_approved", "dispatcher_released", "trust_root_registered_now", "contains_c1_semantics")):
        c._fail("v046 dispatcher amendment grants authority")
    if registry != {"dispatcher_version": "EXTERNAL_TRUST_ROOT_DISPATCHER_V1", "lanes": {}, "registry_version": "1"}:
        c._fail("v046 dispatcher registry is not empty and fail-closed")
