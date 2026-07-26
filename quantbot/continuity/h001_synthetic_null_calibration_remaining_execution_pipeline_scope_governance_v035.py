"""v035 H001 remaining synthetic-null calibration execution pipeline scope
governance.

This transition records only a reviewed decomposition of the remaining
execution pipeline (the gap between the reviewed, PASS-verdict engine core
and an executable calibration run) into named components, each classified
ALREADY_IMPLEMENTED_AND_REVIEWED, NOT_IMPLEMENTED, or OUT_OF_SCOPE. It
authorizes no implementation of any component, no wiring of the reviewed
engine into `execute_calibration`, no calibration execution, no
execution-budget change, and no scientific, paper, shadow, or live
authority. A future component may be implemented only through its own,
separate governance/candidate/independent-review/activation cycle -- this
transition never authorizes more than one component at a time.
"""

import hashlib

from . import context as c
from . import h001_synthetic_null_calibration_execution_engine_implementation_review_completion_v034 as previous

PHASE = "candidate1_h001_synthetic_null_calibration_remaining_execution_pipeline_scope_governed"
NEXT_ACTION = "SELECT_H001_REMAINING_EXECUTION_PIPELINE_FIRST_COMPONENT_FOR_INDEPENDENT_GOVERNANCE"
GOVERNANCE_RELPATH = "docs/control/amendments/candidate1_h001_synthetic_null_calibration_remaining_execution_pipeline_scope_governance_v001.json"
HANDOFF_RELPATH = f"docs/control/tasks/{c.TASK_ID}/handoff_v035.json"
BRANCH = "chore/h001-remaining-execution-pipeline-scope-governance-v035"
BASE_SHA = "1d5cb5a4b2be6aa5c844ebb0ddb5e5f39b06bcc7"
V034_SHA = "c1187bc4387bd299bdf975c411620aefb09a9b7db8040f4456f5c811b8f72037"
V034_REVIEW_SHA = "521901852d197ff19611cde14bd033e85c919a2f85c097b64ccd42f9794d6281"
COMPONENT_COUNT = 14
CURRENT_FILES = [
    "quantbot/continuity/context.py",
    "quantbot/continuity/h001_synthetic_null_calibration_remaining_execution_pipeline_scope_governance_v035.py",
    "tests/control/governance_baseline.json",
    "tests/control/test_legacy_adapter.py",
]
# Protected historical evidence: the full inherited v034 inventory plus the
# v034 handoff receipt and v034's own new review-record artifact, neither of
# which v034 folded into its own PROTECTED dict for forward inheritance
# (matching the same "own artifact bound explicitly here" pattern used when
# v033 inherited from v032).
PROTECTED = {**previous.PROTECTED, previous.HANDOFF_RELPATH: V034_SHA, previous.REVIEW_RELPATH: V034_REVIEW_SHA}
SCOPE = [GOVERNANCE_RELPATH, HANDOFF_RELPATH, c.ACTIVE_TASK_RELPATH, *CURRENT_FILES]
# Engine review/execution binding is carried forward byte-for-byte: this
# transition changes nothing about the engine's review or execution state.
BINDING = dict(previous.BINDING)
_DECISIONS_REMOVE = {"H001_REMAINING_EXECUTION_PIPELINE_SCOPE_GOVERNANCE=REQUIRED"}
_DECISIONS_ADD = {
    "H001_REMAINING_EXECUTION_PIPELINE_SCOPE_GOVERNANCE=EFFECTIVE_SCOPE_DECOMPOSITION_RECORDED",
    "H001_REMAINING_EXECUTION_PIPELINE_SCOPE_GOVERNANCE_SHA256=39b261b53b5d12cb7ebb2b2ce43462523658ad1927d4dd5284a1b624fd25d67c",
    f"H001_REMAINING_EXECUTION_PIPELINE_COMPONENT_COUNT={COMPONENT_COUNT}",
    "H001_REMAINING_EXECUTION_PIPELINE_COMPONENT_AUTHORIZED_THIS_TRANSITION=NONE",
    # H001_REMAINING_EXECUTION_PIPELINE_IMPLEMENTATION stays NOT_AUTHORIZED: this
    # transition authorizes a scope record only, never implementation.
}
DECISIONS = sorted({*[x for x in previous.DECISIONS if x not in _DECISIONS_REMOVE], *_DECISIONS_ADD})
BLOCKERS = sorted(
    {
        *(x for x in previous.BLOCKERS if x != "H001 remaining synthetic calibration execution pipeline requires separately reviewed governance decomposition before further implementation"),
        "H001 remaining synthetic calibration execution pipeline components each require their own separate governance, candidate, and independent review before implementation",
    }
)
PROHIBITIONS = sorted(
    {
        *previous.PROHIBITIONS,
        "IMPLEMENT_ANY_H001_REMAINING_EXECUTION_PIPELINE_COMPONENT_WITHOUT_ITS_OWN_SEPARATE_COMPONENT_GOVERNANCE_CANDIDATE_AND_INDEPENDENT_REVIEW",
        "AUTHORIZE_MORE_THAN_ONE_H001_REMAINING_EXECUTION_PIPELINE_COMPONENT_IN_A_SINGLE_GOVERNANCE_TRANSITION",
        "TREAT_H001_REMAINING_EXECUTION_PIPELINE_SCOPE_GOVERNANCE_AS_IMPLEMENTATION_OR_EXECUTION_AUTHORIZATION",
        "RAISE_H001_EXECUTION_BUDGET_ABOVE_ZERO",
        "MODIFY_PRIOR_AMENDMENTS_OR_HANDOFF_RECEIPTS_V001_THROUGH_V034",
    }
)
# Exact literal values copied from the confirmed v034 receipt: unchanged by
# this transition, and hardcoded here rather than re-derived through the
# module `previous` chain to keep this transition's correctness independent
# of any earlier chain's internal attribute depth.
NUMERICAL_CONVENTION_GAP_INVENTORY = [
    "HAC_AUTOCOVARIANCE_AND_STANDARD_ERROR_CONVENTION",
    "BOOTSTRAP_NULL_CENTERING_TRANSFORM",
    "BOOTSTRAP_STUDENTIZATION_CONVENTION",
    "MAXIMUM_T_EXCEEDANCE_TIE_PVALUE_AND_REJECTION_RULES",
    "STATIONARY_BOOTSTRAP_INITIAL_INDEX_AND_RNG_DRAW_ORDERING",
]
NUMERICAL_CONVENTIONS_SELECTED_CONVENTION_INVENTORY = [
    "HAC-NEWEY-WEST-BARTLETT-1TOVER-T",
    "NULL-CENTER-STATISTIC-AT-OBSERVED-MEAN",
    "STUDENTIZE-RECOMPUTE-BOOTSTRAP-SE",
    "TWO-SIDED-MAXT-PLUS-ONE-NONSTRICT",
    "SYNC-STATIONARY-PATH-BOUND-TO-ACTIVATED-RNG",
]
RNG_RUNTIME_CANDIDATE_RESOLVED_INVENTORY = [
    "NORMATIVE_RANDOM_BIT_SOURCE_AND_HIGH_LEVEL_API_BOUNDARY",
    "LOGICAL_COORDINATE_SCHEMA_AND_CANONICAL_ENCODING",
    "LOGICAL_COORDINATE_TO_PHILOX_KEY_COUNTER_AND_LANE_MAPPING",
    "EXACT_BOUNDED_INTEGER_AND_RATIONAL_BERNOULLI_MAPPING",
    "REJECTION_ATTEMPT_ISOLATION_RETRY_CAP_AND_FAIL_CLOSED_RULE",
    "NUMPY_SEED_SEQUENCE_RUNTIME_DEPENDENCY_BOUNDARY",
    "DRAW_PURPOSE_ALLOCATION_AND_STATIONARY_BOOTSTRAP_LOGICAL_ORDER",
    "PORTABILITY_SCOPE_AND_REPRODUCIBILITY_CLAIM",
]


def governance_doc_expected() -> dict:
    component_inventory = [
        {"component_id": "SYNTHETIC_DGP_SAMPLE_MATERIALIZATION", "summary": "Pure in-process generation of synthetic sample paths for the registered DGP/stress-case identifiers.", "classification": "ALREADY_IMPLEMENTED_AND_REVIEWED"},
        {"component_id": "NULL_STATISTIC_AND_STATIONARY_BOOTSTRAP_PATH_COMPUTATION", "summary": "HAC standard error, null-centered studentized statistic, and stationary-bootstrap max-T computation core.", "classification": "ALREADY_IMPLEMENTED_AND_REVIEWED"},
        {"component_id": "DETERMINISTIC_RNG_SEED_DOMAIN_BINDING", "summary": "Raw NumPy Philox draws bound to the activated RNG runtime specification and the frozen seed domain constant.", "classification": "ALREADY_IMPLEMENTED_AND_REVIEWED"},
        {"component_id": "PER_RUN_COORDINATE_AND_SEED_ORCHESTRATION", "summary": "Caller-side derivation and binding of a specific run's logical coordinates and seed material into the reviewed engine's pure functions.", "classification": "NOT_IMPLEMENTED"},
        {"component_id": "EXECUTE_CALIBRATION_WIRING", "summary": "Connecting the reviewed engine to the `execute_calibration` harness entrypoint, which currently unconditionally refuses.", "classification": "NOT_IMPLEMENTED"},
        {"component_id": "EXECUTION_BUDGET_AUTHORIZATION_MECHANISM", "summary": "Any mechanism that would raise the H001 synthetic-calibration execution budget above 0.", "classification": "OUT_OF_SCOPE"},
        {"component_id": "PIPELINE_FAILURE_AND_PARTIAL_EXECUTION_HANDLING", "summary": "Fail-closed handling of malformed inputs, hash mismatch, RNG mismatch, unexpected phase, or partial execution at the orchestration layer (distinct from the engine's internal RNG rejection retry cap, which is already implemented).", "classification": "NOT_IMPLEMENTED"},
        {"component_id": "CALIBRATION_RESULT_MATERIALIZATION", "summary": "Writing a deterministic calibration result artifact to a durable location.", "classification": "NOT_IMPLEMENTED"},
        {"component_id": "RESULT_PROVENANCE_BINDING", "summary": "Binding a materialized result to the exact spec/numerical-convention/RNG-runtime amendment hashes and run coordinates that produced it.", "classification": "NOT_IMPLEMENTED"},
        {"component_id": "CALIBRATION_EXECUTION_RECEIPT_EMISSION", "summary": "A dedicated calibration-execution receipt kind, distinct from the cross-agent continuity handoff receipt chain.", "classification": "NOT_IMPLEMENTED"},
        {"component_id": "CALIBRATION_OUTPUT_VERIFICATION", "summary": "An independent verifier over a materialized calibration result and its receipt.", "classification": "NOT_IMPLEMENTED"},
        {"component_id": "RESTART_DUPLICATE_AND_REPLAY_PREVENTION", "summary": "Guarding against duplicate or replayed execution of a bounded, single-use execution budget.", "classification": "NOT_IMPLEMENTED"},
        {"component_id": "CLEANUP_SEMANTICS_FOR_FAILED_OR_PARTIAL_RUNS", "summary": "Deterministic cleanup of partial or failed run state without silently treating it as success.", "classification": "NOT_IMPLEMENTED"},
        {"component_id": "DOWNSTREAM_SCIENTIFIC_HANDOFF", "summary": "Any use of a calibration result as scientific, market-edge, or profitability evidence.", "classification": "OUT_OF_SCOPE"},
    ]
    return {
        "allowed_actions": [
            "RECORD_H001_REMAINING_EXECUTION_PIPELINE_COMPONENT_INVENTORY_AND_CLASSIFICATION",
            "SELECT_EXACTLY_ONE_NOT_IMPLEMENTED_COMPONENT_FOR_A_FUTURE_SEPARATE_COMPONENT_GOVERNANCE_TRANSITION",
            "PREPARE_A_FUTURE_COMPONENT_GOVERNANCE_TRANSITION_FOR_INDEPENDENT_REVIEW",
        ],
        "amendment_id": "candidate1-h001-synthetic-null-calibration-remaining-execution-pipeline-scope-governance-v001",
        "amendment_kind": "qnty_h001_synthetic_null_calibration_remaining_execution_pipeline_scope_governance_amendment",
        "authorization_status": "AUTHORIZED_H001_REMAINING_EXECUTION_PIPELINE_SCOPE_DECOMPOSITION_RECORD_ONLY",
        "base_main_commit": BASE_SHA,
        "current_phase": PHASE,
        # Protocol effectiveness is independent of `legacy_adapter`'s frozen
        # v034 seven-role effective-amendment set: that set is bound by
        # explicit per-role SHA-256 digests (`_REQUIRED_EFFECTIVE_AMENDMENT_
        # ROLE_DIGESTS`) and is never populated by scanning this or any other
        # document off disk, so this field cannot affect it either way (v033
        # and v034 raised no such question -- neither produced a governance
        # amendment document at all). This v035 scope-governance transition
        # is itself an effective governance decision the moment it is merged
        # and becomes the active phase, so `effective` is `True`.
        "effective": True,
        "execution_authorized": False,
        "execution_implementation_authorized": False,
        "governed_h001_protocol_id": "real_btc_h001_funding_crowding_reversal_falsification_v0",
        "hash_bindings": {
            "engine_implementation_review_record": {"path": previous.REVIEW_RELPATH, "sha256": V034_REVIEW_SHA},
            "engine_source": {"path": "quantbot/experiment/h001_null_calibration_engine.py", "sha256": "11ce6c8f768043b285e4755cb7fba0f1a8e1d143ad4cb1889c9e0572a0b3d693"},
            "numerical_conventions_amendment": {"path": "docs/control/amendments/candidate1_h001_synthetic_null_calibration_numerical_conventions_amendment_candidate_v001.json", "sha256": "28551aa041aff2985e0023e61516b08f528d93cf72c23c8c3541793f6f61c691"},
            "predecessor_handoff": {"path": previous.HANDOFF_RELPATH, "sha256": V034_SHA},
            "rng_runtime_specification_amendment": {"path": "docs/control/amendments/candidate1_h001_synthetic_null_calibration_rng_runtime_specification_amendment_v001.json", "sha256": "e52b1a4733024e4255cf771b97765cff19f7f5e59cf824732784a1abd594812f"},
            "spec_freeze_candidate": {"path": "docs/assurance/h001_synthetic_null_calibration_spec_freeze_candidate_v001.json", "sha256": "04b6ea5b7453fccf4787abb26c230e2a02a77545c741c19f6686df16fc2cb7a2"},
        },
        "non_effects": [
            "NO_PIPELINE_COMPONENT_IMPLEMENTED", "NO_ENGINE_WIRING", "NO_CALIBRATION_EXECUTION", "NO_CALIBRATION_RESULTS",
            "NO_EXECUTION_BUDGET_CHANGE", "NO_REAL_DATA_ACCESS", "NO_ARTIFACT_OR_STORE_ACCESS", "NO_SCIENTIFIC_AUTHORITY",
            "NO_PAPER_TRADING_AUTHORITY", "NO_LIVE_AUTHORITY", "SCOPE_DECOMPOSITION_NOT_SCIENTIFIC_OR_MARKET_EVIDENCE",
            "EDGE_UNPROVEN", "BLOCK_LIVE_INTEGRATION",
        ],
        "pipeline_component_inventory": component_inventory,
        "prohibited_actions": [
            "IMPLEMENT_ANY_H001_REMAINING_EXECUTION_PIPELINE_COMPONENT_WITHOUT_ITS_OWN_SEPARATE_COMPONENT_GOVERNANCE_CANDIDATE_AND_INDEPENDENT_REVIEW",
            "AUTHORIZE_MORE_THAN_ONE_H001_REMAINING_EXECUTION_PIPELINE_COMPONENT_IN_A_SINGLE_GOVERNANCE_TRANSITION",
            "WIRE_ENGINE_INTO_EXECUTE_CALIBRATION", "EXECUTE_H001_SYNTHETIC_NULL_CALIBRATION_ENGINE", "CONSUME_H001_EXECUTION_BUDGET",
            "RAISE_H001_EXECUTION_BUDGET_ABOVE_ZERO", "ACCESS_REAL_BARS_OR_FUNDING", "ACCESS_CANDIDATE1_V0_OR_HOLDOUT",
            "ACCESS_ARTIFACT_STORES_OR_SECRETS", "CONFIGURE_DURABLE_STORES", "AUTHORIZE_REAL_DATA_INFRASTRUCTURE",
            "AUTHORIZE_SCIENTIFIC_USE", "AUTHORIZE_PAPER_TRADING", "AUTHORIZE_LIVE_INTEGRATION", "CLAIM_MARKET_EVIDENCE_OR_EDGE",
            "TREAT_THIS_SCOPE_GOVERNANCE_AS_IMPLEMENTATION_OR_EXECUTION_AUTHORIZATION",
        ],
        "results": "NONE",
        "schema_version": "0.1.0",
        "status": "EFFECTIVE_SCOPE_DECOMPOSITION_ONLY_NO_IMPLEMENTATION_AUTHORITY",
        "transition_gates": {
            "effective_frozen_specification_verified": True, "execution_authorized": False, "execution_implementation_authorized": False,
            "execution_results": "NONE", "h001_execution_budget": 0, "h001_execution_count": 0, "h001_holdout_execution_authorized": False,
            "h001_validation_execution_authorized": False, "live_authorization": False, "paper_trade_authorization": False,
            "real_data_access_authorized": False, "scientific_authorization": False, "scope_decomposition_component_count": len(component_inventory),
            "scope_decomposition_recorded": True,
        },
    }


def validate(receipt, root):
    if receipt["receipt_index"] != 35 or receipt["phase"] != PHASE or receipt["source_branch"] != BRANCH or receipt["source_head_commit"] != BASE_SHA:
        c._fail("H001 remaining-execution-pipeline scope-governance receipt identity or source binding is wrong")
    if receipt["predecessor"] != {"path": previous.HANDOFF_RELPATH, "sha256": V034_SHA}:
        c._fail("H001 remaining-execution-pipeline scope-governance predecessor is wrong")
    for field, expected in (
        ("changed_file_scope", SCOPE),
        ("next_actions", [NEXT_ACTION]),
        ("decisions", DECISIONS),
        ("blockers", BLOCKERS),
        ("prohibited_actions", PROHIBITIONS),
        ("numerical_convention_gap_inventory", NUMERICAL_CONVENTION_GAP_INVENTORY),
        ("numerical_conventions_selected_convention_inventory", NUMERICAL_CONVENTIONS_SELECTED_CONVENTION_INVENTORY),
        ("rng_runtime_candidate_resolved_inventory", RNG_RUNTIME_CANDIDATE_RESOLVED_INVENTORY),
        ("engine_implementation_binding", BINDING),
    ):
        if receipt[field] != expected:
            c._fail(f"H001 remaining-execution-pipeline scope-governance {field} drifted")
    for field, expected in (
        ("changed_file_scope", SCOPE), ("next_actions", [NEXT_ACTION]), ("decisions", DECISIONS),
        ("blockers", BLOCKERS), ("prohibited_actions", PROHIBITIONS),
    ):
        if len(receipt[field]) != len(set(receipt[field])):
            c._fail(f"H001 remaining-execution-pipeline scope-governance {field} contains duplicates")
    if receipt["safety_state"] != dict(c._EXPECTED_SAFETY, real_data_execution_requested=False):
        c._fail("H001 remaining-execution-pipeline scope-governance safety state drifted")
    for path, digest in PROTECTED.items():
        if not (root / path).is_file() or hashlib.sha256((root / path).read_bytes()).hexdigest() != digest:
            c._fail(f"H001 remaining-execution-pipeline scope-governance protected evidence {path!r} hash mismatch")
    governance_raw = (root / GOVERNANCE_RELPATH).read_bytes()
    governance_doc = c._load_canonical_document(governance_raw, "H001 remaining-execution-pipeline scope-governance document")
    if governance_doc != governance_doc_expected():
        c._fail("H001 remaining-execution-pipeline scope-governance document is malformed or does not match the recorded decomposition")
    if receipt["evidence"] != [{"path": p, "sha256": h} for p, h in PROTECTED.items()] + [{"path": GOVERNANCE_RELPATH, "sha256": hashlib.sha256(governance_raw).hexdigest()}]:
        c._fail("H001 remaining-execution-pipeline scope-governance evidence is wrong")
    if receipt["current_transition_files"] != [{"path": p, "sha256": hashlib.sha256((root / p).read_bytes()).hexdigest()} for p in CURRENT_FILES]:
        c._fail("H001 remaining-execution-pipeline scope-governance transition files drifted")
