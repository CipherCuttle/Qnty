"""v027 review-only RNG-runtime candidate control-plane extension."""

import hashlib

from . import context as c


PHASE = "candidate1_h001_synthetic_null_calibration_rng_runtime_specification_amendment_candidate_review_required"
NEXT_ACTION = "ADVERSARIAL_REVIEW_H001_SYNTHETIC_NULL_CALIBRATION_RNG_RUNTIME_SPECIFICATION_AMENDMENT_CANDIDATE"
RELPATH = "docs/control/amendments/candidate1_h001_synthetic_null_calibration_rng_runtime_specification_amendment_v001.json"
HANDOFF_RELPATH = f"docs/control/tasks/{c.TASK_ID}/handoff_v027.json"
BRANCH = "feat/h001-rng-runtime-amendment-candidate"
BASE_SHA = "31ae06eba2d17132642639a98a83728414dd75aa"
DOCUMENT_SHA = "e52b1a4733024e4255cf771b97765cff19f7f5e59cf824732784a1abd594812f"
V026_SHA = "fd62b1f648b50817b8c664fb38f9e1e685876981cb425d5daf29b78e14e13d2c"
ARCHITECTURE = "RAW_NUMPY_PHILOX_WITH_REPOSITORY_OWNED_DETERMINISTIC_MAPPINGS"
DOMAINS = list(c._H001_RNG_RUNTIME_GOVERNANCE_DOMAINS)
GAPS = list(c._H001_RNG_RUNTIME_GOVERNANCE_GAPS)
SCOPE = [RELPATH, HANDOFF_RELPATH, c.ACTIVE_TASK_RELPATH, "quantbot/continuity/context.py", "quantbot/continuity/h001_rng_runtime_candidate_v027.py", "quantbot/assurance/contracts.py", "tests/continuity/test_cross_agent_continuity.py", "tests/assurance/test_contracts.py", "tests/assurance/test_h001_rng_runtime_kat_numpy_derivation.py", "tests/assurance/test_h001_rng_runtime_kat_reference_derivation.py"]
CURRENT_FILES = ["quantbot/continuity/context.py", "quantbot/continuity/h001_rng_runtime_candidate_v027.py", "quantbot/assurance/contracts.py", "tests/continuity/test_cross_agent_continuity.py", "tests/assurance/test_contracts.py", "tests/assurance/test_h001_rng_runtime_kat_numpy_derivation.py", "tests/assurance/test_h001_rng_runtime_kat_reference_derivation.py"]
PROTECTED = {
    RELPATH: DOCUMENT_SHA,
    c._H001_RNG_RUNTIME_GOVERNANCE_HANDOFF_RELPATH: V026_SHA,
    c._H001_RNG_RUNTIME_GOVERNANCE_AMENDMENT_RELPATH: c._H001_RNG_RUNTIME_GOVERNANCE_AMENDMENT_SHA,
    c._H001_NUMERICAL_CONVENTIONS_GOVERNANCE_HANDOFF_RELPATH: "70ca9d1d0184828abc039df3c6ffcffec3d41065c8c5142ebfe44571283e0d80",
    c._H001_NUMERICAL_CONVENTIONS_GOVERNANCE_AMENDMENT_RELPATH: c._H001_NUMERICAL_CONVENTIONS_GOVERNANCE_AMENDMENT_SHA,
    c._H001_CALIBRATION_IMPLEMENTATION_BLOCKED_HANDOFF_RELPATH: c._H001_NUMERICAL_CONVENTIONS_GOVERNANCE_V024_SHA,
    c._H001_CALIBRATION_EXECUTION_GOVERNANCE_HANDOFF_RELPATH: c._H001_CALIBRATION_IMPLEMENTATION_BLOCKED_V023_SHA,
    c._H001_CALIBRATION_EXECUTION_GOVERNANCE_AMENDMENT_RELPATH: c._H001_CALIBRATION_EXECUTION_GOVERNANCE_AMENDMENT_SHA,
    c._H001_CALIBRATION_EFFECTIVE_HANDOFF_RELPATH: c._H001_CALIBRATION_EXECUTION_GOVERNANCE_V022_SHA,
    c._H001_CALIBRATION_EFFECTIVE_AMENDMENT_RELPATH: c._H001_CALIBRATION_EFFECTIVE_AMENDMENT_SHA,
    c._H001_CALIBRATION_CANDIDATE_RELPATH: c._H001_CALIBRATION_EFFECTIVE_CANDIDATE_SHA,
    c._H001_CALIBRATION_REREVIEW_RECORD_RELPATH: c._H001_CALIBRATION_EFFECTIVE_REREVIEW_SHA,
    f"docs/control/tasks/{c.TASK_ID}/handoff_v021.json": c._H001_CALIBRATION_EFFECTIVE_V021_SHA,
    c._H001_CALIBRATION_GOVERNANCE_AMENDMENT_RELPATH: c._H001_CALIBRATION_EFFECTIVE_GOVERNANCE_SHA,
    "docs/assurance/h001_synthetic_null_calibration_spec_draft_v001.json": c._H001_CALIBRATION_EFFECTIVE_DRAFT_SHA,
    c.H001_DESIGN_JSON_RELPATH: c._H001_CALIBRATION_EFFECTIVE_DESIGN_SHA,
    "quantbot/experiment/h001_real_falsification_preregistration.py": c._H001_CALIBRATION_EFFECTIVE_VALIDATOR_SHA,
    c._H001_TEMPORAL_ACTIVE_AMENDMENT_RELPATH: c._H001_CALIBRATION_EFFECTIVE_TEMPORAL_SHA,
    "quantbot/assurance/h001_null_calibration.py": c._H001_CALIBRATION_IMPLEMENTATION_BLOCKED_CALIBRATION_HARNESS_SHA,
    "tests/assurance/test_h001_null_calibration.py": c._H001_CALIBRATION_IMPLEMENTATION_BLOCKED_TEST_CALIBRATION_SHA,
    "docs/artifacts/candidate1-real-input-v0.json": c._H001_CALIBRATION_IMPLEMENTATION_BLOCKED_ARTIFACT_SHA,
    c.STORE_REGISTRY_RELPATH: c._H001_CALIBRATION_IMPLEMENTATION_BLOCKED_STORES_SHA,
    "pyproject.toml": "bb9386d11b2139308226ab6eac5d978743fdde059056c2b6fbfc0983382a361a",
}
BLOCKERS = list(c._H001_RNG_RUNTIME_GOVERNANCE_BLOCKERS)
DECISIONS = sorted([*[x for x in c._H001_RNG_RUNTIME_GOVERNANCE_DECISIONS if x not in ("H001_RNG_RUNTIME_CONTRACT=UNRESOLVED", "H001_RNG_RUNTIME_SPECIFICATION_AMENDMENT_CANDIDATE=NOT_CREATED")], "H001_RNG_RUNTIME_CONTRACT=CANDIDATE_RESOLVED_PENDING_INDEPENDENT_REVIEW", "H001_RNG_RUNTIME_SPECIFICATION_AMENDMENT_CANDIDATE=CREATED_FOR_INDEPENDENT_REVIEW", "H001_RNG_RUNTIME_SPECIFICATION_AMENDMENT_CANDIDATE_SHA256=" + DOCUMENT_SHA, "H001_RNG_RUNTIME_SPECIFICATION_AMENDMENT_CANDIDATE_VALUES=LOCKED_FOR_REVIEW", "H001_RNG_RUNTIME_SPECIFICATION_AMENDMENT_ACTIVATED=FALSE", "H001_RNG_RUNTIME_CANDIDATE_SELECTED_ARCHITECTURE=" + ARCHITECTURE])
PROHIBITIONS = sorted([*c._H001_RNG_RUNTIME_GOVERNANCE_PROHIBITIONS, "ACTIVATE_H001_SYNTHETIC_NULL_CALIBRATION_RNG_RUNTIME_SPECIFICATION_AMENDMENT_BEFORE_INDEPENDENT_REVIEW", "MODIFY_H001_RNG_RUNTIME_SPECIFICATION_AMENDMENT_CANDIDATE_VALUES_AFTER_LOCK", "MODIFY_PRIOR_AMENDMENTS_OR_HANDOFF_RECEIPTS_V001_THROUGH_V026"])
BINDING = {"candidate_path": RELPATH, "candidate_sha256": DOCUMENT_SHA, "governance_amendment_path": c._H001_RNG_RUNTIME_GOVERNANCE_AMENDMENT_RELPATH, "governance_amendment_sha256": c._H001_RNG_RUNTIME_GOVERNANCE_AMENDMENT_SHA, "selected_architecture": ARCHITECTURE, "candidate_created": True, "candidate_reviewed": False, "candidate_effective": False, "candidate_activated": False}


def validate(receipt, root):
    if receipt["receipt_index"] != 27 or receipt["phase"] != PHASE or receipt["source_branch"] != BRANCH or receipt["source_head_commit"] != BASE_SHA:
        c._fail("H001 RNG-runtime candidate receipt identity or source binding is wrong")
    if receipt["predecessor"] != {"path": c._H001_RNG_RUNTIME_GOVERNANCE_HANDOFF_RELPATH, "sha256": V026_SHA}:
        c._fail("H001 RNG-runtime candidate predecessor is wrong")
    for field, expected in (("changed_file_scope", SCOPE), ("next_actions", [NEXT_ACTION]), ("decisions", DECISIONS), ("blockers", BLOCKERS), ("prohibited_actions", PROHIBITIONS), ("numerical_convention_gap_inventory", GAPS), ("rng_runtime_candidate_resolved_inventory", DOMAINS)):
        if receipt[field] != expected or len(receipt[field]) != len(set(receipt[field])):
            c._fail(f"H001 RNG-runtime candidate {field} drifted")
    if receipt["safety_state"] != dict(c._EXPECTED_SAFETY, real_data_execution_requested=False) or receipt["candidate_binding"] != BINDING:
        c._fail("H001 RNG-runtime candidate safety or binding drifted")
    if receipt["evidence"] != [{"path": p, "sha256": h} for p, h in PROTECTED.items()]:
        c._fail("H001 RNG-runtime candidate protected evidence list must be exact, unique, and ordered")
    for path, digest in PROTECTED.items():
        if not (root / path).is_file() or hashlib.sha256((root / path).read_bytes()).hexdigest() != digest:
            c._fail(f"H001 RNG-runtime candidate protected evidence {path!r} hash mismatch")
    expected_current = [{"path": p, "sha256": hashlib.sha256((root / p).read_bytes()).hexdigest()} for p in CURRENT_FILES]
    if receipt["current_transition_files"] != expected_current:
        c._fail("H001 RNG-runtime candidate current-transition files must be exact, unique, and hash-bound")
    raw = (root / RELPATH).read_bytes()
    if hashlib.sha256(raw).hexdigest() != DOCUMENT_SHA:
        c._fail("H001 RNG-runtime candidate document hash is wrong")
    candidate = c.contracts.load_and_validate_h001_rng_runtime_amendment_candidate(raw)
    if candidate["effective"] or candidate["activated"] or candidate["independent_review_completed"] or candidate["selected_architecture"] != ARCHITECTURE:
        c._fail("H001 RNG-runtime candidate claims an effect it must not have")
