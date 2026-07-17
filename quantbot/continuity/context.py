"""Fail-closed validator and renderer for the QNTY cross-agent continuity control plane.

Source of truth is the committed control state under ``docs/control/`` plus the
model-specific entrypoints (``CLAUDE.md``, ``AGENTS.md``) and the canonical shared
contract (``docs/agent/START_HERE.md``). This module never reads market data,
ledgers, or quarantine content; it only validates governance documents.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from quantbot.artifacts.registry import (
    ArtifactRegistryError,
    cross_check_receipt_artifact,
    validate_artifact_record_bytes,
    validate_operational_registry,
    validate_store_registry_bytes,
)

__all__ = [
    "canonical_json_bytes",
    "load_and_verify_continuity_state",
    "render_context_packet",
]

_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_COMMIT_RE = re.compile(r"[0-9a-f]{40}")
_RECEIPT_BASENAME_RE = re.compile(r"handoff_v[0-9]{3}\.json")

TASK_ID = "RECOVER_OR_RETIRE_CANDIDATE1_V0_FROZEN_INPUT"
PROTOCOL_ID = "real_btc_candidate1_train_mechanism_decomposition_v0"
REQUIRED_ARTIFACT_ID = "candidate1-real-input-v0"
REQUIRED_ARTIFACT_MANIFEST_SHA256 = "3dec994114769a16939afa9b0041a8162a308dcb05ca196557407b26a0d35b0d"

ACTIVE_TASK_RELPATH = "docs/control/active_task.json"
ARTIFACT_RECORDS_DIR_RELPATH = "docs/artifacts"
STORE_REGISTRY_RELPATH = "docs/artifacts/stores.json"
AMENDMENT_RELPATH = "docs/control/amendments/candidate1_v1_synthetic_sandbox_v001.json"
REAL_H001_AMENDMENT_RELPATH = "docs/control/amendments/candidate1_h001_real_falsification_design_v001.json"
PRE_DATA_H001_AMENDMENT_RELPATH = "docs/control/amendments/candidate1_h001_pre_data_assurance_v001.json"
H001_DESIGN_JSON_RELPATH = "docs/experiments/candidate1_h001_real_data_falsification_v0.json"
START_HERE_RELPATH = "docs/agent/START_HERE.md"
CLAUDE_ENTRYPOINT_RELPATH = "CLAUDE.md"
CODEX_ENTRYPOINT_RELPATH = "AGENTS.md"
CLAUDE_CONTRACT_POINTER = "@docs/agent/START_HERE.md"
CODEX_CONTRACT_POINTER = "docs/agent/START_HERE.md"
VERIFY_COMMAND = "python -m quantbot.continuity verify"

_PROHIBITED_CANONICAL_PATH_PREFIXES = ("/tmp", "/srv/qnty")

_ACTIVE_KEYS = {
    "control_kind",
    "handoff_receipt_path",
    "handoff_receipt_sha256",
    "phase",
    "protocol_id",
    "schema_version",
    "task_id",
}
_RECEIPT_KEYS = {
    "blockers",
    "changed_file_scope",
    "decisions",
    "evidence",
    "next_actions",
    "predecessor",
    "prohibited_actions",
    "protocol_id",
    "receipt_index",
    "receipt_kind",
    "required_artifacts",
    "safety_state",
    "schema_version",
    "source_branch",
    "source_head_commit",
    "task_id",
    "verified_commands",
}
_SAFETY_KEYS = {
    "decomposition_execution_budget",
    "decomposition_execution_count",
    "edge_status",
    "live_integration_authorized",
    "live_status",
    "paper_trade_authorized",
    "quarantine_access",
    "real_data_execution_requested",
    "scientific_use_authorized",
}
_ARTIFACT_KEYS = {
    "artifact_id",
    "availability",
    "canonical_paths",
    "expected_manifest_sha256",
    "verified_copy_count",
}
_EVIDENCE_KEYS = {"path", "sha256"}
_PREDECESSOR_KEYS = {"path", "sha256"}

_EXPECTED_SAFETY = {
    "decomposition_execution_budget": 1,
    "decomposition_execution_count": 0,
    "edge_status": "EDGE_UNPROVEN",
    "live_integration_authorized": False,
    "live_status": "BLOCK_LIVE_INTEGRATION",
    "paper_trade_authorized": False,
    "quarantine_access": "forbidden",
    "scientific_use_authorized": False,
}
_AVAILABILITY_STATES = ("UNAVAILABLE", "VERIFIED_AVAILABLE")
_DURABLE_PHASE = "durable_artifact_store_configuration"
_DURABLE_NEXT_ACTION = "CONFIGURE_TWO_DURABLE_ARTIFACT_STORES"
_SANDBOX_PHASE = "candidate1_v1_synthetic_sandbox_governance"
_SANDBOX_NEXT_ACTION = "IMPLEMENT_CANDIDATE1_V1_SYNTHETIC_SANDBOX_SCAFFOLD"
_SANDBOX_READY_PHASE = "candidate1_v1_synthetic_sandbox_ready"
_SANDBOX_READY_NEXT_ACTION = "RUN_CANDIDATE1_V1_SYNTHETIC_STRATEGY_BATCH"
_H001_COMPLETE_PHASE = "candidate1_h001_synthetic_falsification_complete"
_H001_COMPLETE_NEXT_ACTION = "AUTHORIZE_H001_REAL_FALSIFICATION_PREREGISTRATION_DESIGN_GOVERNANCE"
_H001_DESIGN_PHASE = "candidate1_h001_real_falsification_preregistration_design_governance"
_H001_DESIGN_NEXT_ACTION = "DRAFT_H001_REAL_FALSIFICATION_PREREGISTRATION_DESIGN"
_H001_PREREGISTERED_PHASE = "candidate1_h001_real_falsification_preregistered_design_only"
_H001_PREREGISTERED_NEXT_ACTION = "ADVERSARIAL_REVIEW_H001_REAL_FALSIFICATION_PREREGISTRATION"
_H001_REVIEW_COMPLETE_PHASE = "candidate1_h001_real_falsification_preregistration_review_complete"
_H001_REVIEW_COMPLETE_NEXT_ACTION = "AUTHORIZE_H001_REAL_DATA_INFRASTRUCTURE_PREPARATION_GOVERNANCE"
_H001_PRE_DATA_PHASE = "candidate1_h001_pre_data_assurance_governance"
_H001_PRE_DATA_NEXT_ACTION = "IMPLEMENT_H001_PRE_DATA_ASSURANCE_AND_SYNTHETIC_INFRASTRUCTURE_SCAFFOLD"
# Immutable identities recorded by the H001 preregistration review-completion
# transition. These pin the exact reviewed artifacts; the external adversarial
# review is process assurance only and is never scientific evidence.
_H001_PREREGISTERED_HANDOFF_SHA256 = "888dd194c35df018a8b1e2d1e3786fdd6368004aae725f2e177e5b68d24dc2b6"
_H001_REVIEW_MERGED_MAIN_SHA = "f9166c3f03938f0b3c0a1ea87a7260ae6eaf24b3"
_H001_REVIEW_SOURCE_BRANCH = "feat/h001-preregistration-review-completion"
_H001_REVIEW_REVIEWED_HEAD = "23653b84ab3ab21d394bbeebaac790d45c2d90c7"
_H001_REVIEW_DESIGN_SHA256 = "055ea162a11d4042320daeb74e153ebbd27969dd29a60c226cb84a8fc38b8900"
_H001_REVIEW_VALIDATOR_SHA256 = "888bc4663e3d7fb9b398f944bf2b67553e8959e0173be77183ca8b288156172a"
_H001_REVIEW_FOCUSED_TEST_SHA256 = "4cf6478701f70ab7ecee4f5d84b39b042344daeb928da38d59c0389a2a8ca7c6"
_H001_REVIEW_VERDICT = "QNTY_H001_REAL_FALSIFICATION_PREREGISTRATION_REREVIEW_PASSED"
_H001_VALIDATOR_RELPATH = "quantbot/experiment/h001_real_falsification_preregistration.py"
_H001_FOCUSED_TEST_RELPATH = "tests/experiment/test_h001_real_falsification_preregistration.py"
_H001_REVIEW_REQUIRED_DECISIONS = {
    "H001_PREREGISTRATION_REVIEW_STATUS=PASSED",
    f"H001_PREREGISTRATION_REVIEWED_HEAD={_H001_REVIEW_REVIEWED_HEAD}",
    f"H001_PREREGISTRATION_DESIGN_SHA256={_H001_REVIEW_DESIGN_SHA256}",
    f"H001_PREREGISTRATION_VALIDATOR_SHA256={_H001_REVIEW_VALIDATOR_SHA256}",
    "H001_PREREGISTRATION_REVIEW_NAMED_PROBES=67/67_REJECTED",
    "H001_PREREGISTRATION_REVIEW_GENUINE_MUTATIONS=1136/1136_REJECTED",
    "H001_PREREGISTRATION_REVIEW_BLOCKERS=NONE",
    "H001_PREREGISTRATION_REVIEW_MAJOR_FINDINGS=NONE",
    f"H001_PREREGISTRATION_REVIEW_VERDICT={_H001_REVIEW_VERDICT}",
    "H001_REAL_DATA_ACCESS=FORBIDDEN",
    "H001_ARTIFACT_OPERATIONS=FORBIDDEN",
    "H001_CURRENT_EXECUTION_BUDGET=0",
    "H001_CURRENT_EXECUTION_COUNT=0",
    "H001_SCIENTIFIC_AUTHORIZATION=FALSE",
    "H001_PAPER_TRADE_AUTHORIZATION=FALSE",
    "H001_LIVE_AUTHORIZATION=FALSE",
    "H001_REQUIRED_DURABLE_COPIES=2",
}
_H001_REVIEW_REQUIRED_PROHIBITIONS = {
    "AUTHORIZE_H001_REAL_DATA_INFRASTRUCTURE_WITHOUT_SEPARATE_GOVERNANCE",
    "TREAT_EXTERNAL_REVIEW_AS_SCIENTIFIC_EVIDENCE",
    "CONFIGURE_DURABLE_ARTIFACT_STORES",
    "GRANT_REAL_DATA_ACCESS",
    "GRANT_SCIENTIFIC_AUTHORIZATION",
}
_H001_PRE_DATA_AMENDMENT_KEYS = {
    "allowed_actions", "amendment_id", "amendment_kind", "assurance_controls",
    "authorization_scope", "authorization_status", "governed_h001_protocol_id",
    "governed_protocol_id", "non_effects", "predecessor_amendment", "prohibited_actions",
    "review_binding", "schema_version", "source_handoff", "source_main_commit",
    "strict_temporal_precedence_target", "transition_gates",
}
_H001_PRE_DATA_REVIEW_BINDING_KEYS = {
    "design_sha256", "review_verdict", "reviewed_implementation_head", "validator_sha256",
}
_H001_PRE_DATA_ALLOWED_ACTIONS = sorted([
    "DRAFT_APPEND_ONLY_H001_TEMPORAL_CAUSALITY_AMENDMENT_WITHOUT_APPLYING",
    "DRAFT_H001_SYNTHETIC_NULL_CALIBRATION_SPEC_WITHOUT_FREEZING_OR_EXECUTION",
    "IMPLEMENT_APPEND_ONLY_GLOBAL_REAL_PROTOCOL_HOLDOUT_DISCLOSURE_LEDGER_SCHEMA_WITHOUT_DATA_ACCESS_OR_BACKFILL",
    "IMPLEMENT_DURABLE_STORE_FAILURE_DOMAIN_EVIDENCE_METADATA_SCHEMA_WITHOUT_STORE_ACCESS_OR_CONFIGURATION",
    "IMPLEMENT_H001_SYNTHETIC_NULL_CALIBRATION_HARNESS_WITHOUT_EXECUTION",
    "IMPLEMENT_REPLAYABLE_REVIEW_EVIDENCE_PACKET_SCHEMA_WITHOUT_REAL_DATA_OR_SECRETS",
    "IMPLEMENT_SYNTHETIC_ARTIFACT_CANARY_SCAFFOLD_WITHOUT_STORE_CONFIGURATION_OR_EXECUTION",
    "REVIEW_H001_PRE_DATA_ASSURANCE_AND_SYNTHETIC_INFRASTRUCTURE_SCAFFOLD",
])
_H001_PRE_DATA_ASSURANCE_CONTROLS = sorted([
    "CALIBRATION_SPEC_FREEZE_REQUIRES_SEPARATE_GOVERNANCE",
    "DYNAMIC_FUNDING_INTERVAL_FIXTURES_REQUIRED", "FAILURE_DOMAIN_LABEL_SELF_ASSERTION_IS_INSUFFICIENT",
    "FAILURE_DOMAIN_SCHEMA_IMPLEMENTATION_CANNOT_PROBE_STORES",
    "FROZEN_NULL_DGP_SPEC_REQUIRED_BEFORE_CALIBRATION", "GLOBAL_HOLDOUT_DISCLOSURE_LEDGER_REQUIRED",
    "HAC_LAG_TUNING_FORBIDDEN", "INDEPENDENT_RESTORE_AND_REHASH_REQUIRED",
    "HOLDOUT_LEDGER_IMPLEMENTATION_IS_SCHEMA_ONLY", "HOLDOUT_LEDGER_REAL_DATA_ACCESS_FORBIDDEN",
    "HOLDOUT_LEDGER_RETROACTIVE_BACKFILL_FORBIDDEN",
    "MULTIPLE_FUNDING_EVENTS_PER_BAR_FIXTURES_REQUIRED", "REPLAYABLE_REVIEW_PACKET_REQUIRED",
    "REVIEW_PACKET_REAL_DATA_AND_SECRETS_FORBIDDEN",
    "STATIONARY_BOOTSTRAP_BLOCK_LENGTH_TUNING_FORBIDDEN", "STRICT_TEMPORAL_PRECEDENCE_AMENDMENT_TARGET",
    "SYNTHETIC_CANARY_CANNOT_BECOME_REAL_ARTIFACT",
])
_H001_PRE_DATA_NON_EFFECTS = sorted([
    "DOES_NOT_AUTHORIZE_CALIBRATION_SPEC_FREEZE", "DOES_NOT_AUTHORIZE_CANDIDATE_STORE_ACCESS_OR_PROBING",
    "DOES_NOT_AUTHORIZE_HOLDOUT_LEDGER_BACKFILL", "DOES_NOT_AUTHORIZE_HOLDOUT_OR_REAL_ARTIFACT_BYTE_ACCESS",
    "DOES_NOT_AUTHORIZE_NETWORK_ACCESS", "DOES_NOT_AUTHORIZE_REVIEW_PACKET_REAL_DATA_OR_SECRET_INCLUSION",
    "DOES_NOT_ACCESS_BINANCE", "DOES_NOT_ACCESS_REAL_DATA", "DOES_NOT_AMEND_THE_H001_PREREGISTRATION",
    "DOES_NOT_AUTHORIZE_ASSURANCE_EXECUTION", "DOES_NOT_AUTHORIZE_BOOTSTRAP_OR_HAC_TUNING",
    "DOES_NOT_AUTHORIZE_CANDIDATE_STORE_CONFIGURATION", "DOES_NOT_AUTHORIZE_H001_HOLDOUT",
    "DOES_NOT_AUTHORIZE_H001_VALIDATION", "DOES_NOT_AUTHORIZE_LIVE_INTEGRATION",
    "DOES_NOT_AUTHORIZE_PAPER_TRADING", "DOES_NOT_AUTHORIZE_REAL_ARTIFACT_CREATION",
    "DOES_NOT_AUTHORIZE_REAL_DATA_ACCESS", "DOES_NOT_AUTHORIZE_SCIENTIFIC_CLAIMS",
    "DOES_NOT_CHANGE_BLOCK_LIVE_INTEGRATION", "DOES_NOT_CHANGE_EDGE_UNPROVEN",
    "DOES_NOT_CHANGE_V0_ARTIFACT_STATE", "DOES_NOT_CONFIGURE_DURABLE_STORES",
    "DOES_NOT_CREATE_OR_BIND_REAL_DATA_ARTIFACTS", "DOES_NOT_INCREMENT_ANY_EXECUTION_COUNT",
    "DOES_NOT_MARK_SYNTHETIC_RESULTS_AS_MARKET_EVIDENCE", "DOES_NOT_MODIFY_EXISTING_AMENDMENTS",
    "DOES_NOT_MODIFY_EXISTING_HANDOFF_RECEIPTS", "DOES_NOT_RANK_OR_SELECT_H001_VARIANTS",
    "DOES_NOT_RECOVER_OR_RETIRE_V0",
])
_H001_PRE_DATA_REQUIRED_PROHIBITIONS = sorted(set([
    "ACCESS_HOLDOUT_OR_REAL_ARTIFACT_BYTES_FOR_LEDGER_IMPLEMENTATION", "ACCESS_OR_PROBE_CANDIDATE_STORE_ROOTS",
    "ACCESS_ANY_REAL_BARS_OR_FUNDING", "ACCESS_BINANCE_OR_ANY_MARKET_DATA_SOURCE",
    "ACCESS_CANDIDATE1_V0_INPUT_OR_QUARANTINE", "APPLY_TEMPORAL_CAUSALITY_CHANGE_WITHOUT_APPEND_ONLY_AMENDMENT",
    "CALCULATE_H001_REAL_RETURNS", "CONFIGURE_CANDIDATE_DURABLE_STORES", "CONFIGURE_DURABLE_ARTIFACT_STORES",
    "CREATE_OR_BIND_REAL_DATA_ARTIFACT", "EXECUTE_H001", "EXECUTE_H001_HOLDOUT", "EXECUTE_H001_VALIDATION",
    "EXPOSE_SYNTHETIC_NULL_CALIBRATION_RESULTS_BEFORE_SEPARATE_AUTHORIZATION", "GRANT_LIVE_INTEGRATION_AUTHORIZATION",
    "GRANT_PAPER_TRADE_AUTHORIZATION", "GRANT_REAL_DATA_ACCESS", "GRANT_SCIENTIFIC_AUTHORIZATION",
    "INCREMENT_EXECUTION_COUNTS", "MARK_CANDIDATE1_REAL_INPUT_V0_AVAILABLE", "MODIFY_EXISTING_GOVERNANCE_AMENDMENTS",
    "MODIFY_EXISTING_HANDOFF_RECEIPTS", "RANK_OR_SELECT_H001_VARIANTS", "REGISTER_SYNTHETIC_CANARY_AS_REAL_ARTIFACT",
    "RUN_SYNTHETIC_STORE_CANARY_BEFORE_SEPARATE_AUTHORIZATION", "TREAT_ASSURANCE_RESULTS_AS_MARKET_EVIDENCE",
    "TREAT_REVIEW_RESULTS_AS_SCIENTIFIC_EVIDENCE", "TUNE_BOOTSTRAP_BLOCK_LENGTH_FROM_CALIBRATION_RESULTS",
    "TUNE_HAC_LAG_FROM_CALIBRATION_RESULTS", "USE_H001_HOLDOUT_DATA", "USE_REAL_DATA_IN_ASSURANCE_SCAFFOLD",
    "ACCESS_QUARANTINE", "CLAIM_H001_HAS_MARKET_EDGE", "CHOOSE_OR_INSPECT_REAL_DATASET_BYTES",
    "CONSUME_H001_EXECUTION_BUDGET", "FREEZE_REAL_DATA", "RECOVER_OR_RETIRE_V0",
    "AUTHORIZE_H001_REAL_DATA_INFRASTRUCTURE_WITHOUT_SEPARATE_GOVERNANCE",
    "ACCESS_STORE_CREDENTIALS_OR_SECRET_CONFIGURATION", "BACKFILL_GLOBAL_HOLDOUT_LEDGER_FROM_REAL_DATA_OR_UNVERIFIED_HISTORY",
    "FREEZE_H001_SYNTHETIC_NULL_CALIBRATION_SPEC", "INCLUDE_REAL_DATA_OR_SECRETS_IN_REVIEW_EVIDENCE_PACKET",
    "MUTATE_PRIOR_HOLDOUT_LEDGER_DISCLOSURES", "QUERY_NETWORK_OR_MARKET_DATA_FOR_SCAFFOLD_IMPLEMENTATION",
]))
_H001_PRE_DATA_TRANSITION_GATES = {
    "existing_h001_design_unchanged": True, "existing_h001_validator_unchanged": True, "existing_h001_review_passed": True,
    "temporal_causality_amendment_required": True, "temporal_causality_amendment_applied": False,
    "temporal_causality_amendment_requires_independent_review": True, "synthetic_null_calibration_spec_required": True,
    "synthetic_null_calibration_spec_draft_authorized": True, "synthetic_null_calibration_spec_freeze_authorized": False,
    "synthetic_null_calibration_spec_frozen": False,
    "synthetic_null_calibration_harness_authorized": True, "synthetic_null_calibration_execution_authorized": False,
    "synthetic_null_calibration_results_exposed": False, "bootstrap_block_length_tuning_authorized": False,
    "hac_lag_tuning_authorized": False, "global_holdout_ledger_required": True, "global_holdout_ledger_implemented": False,
    "global_holdout_ledger_schema_authorized": True, "global_holdout_ledger_data_access_authorized": False,
    "global_holdout_ledger_backfill_authorized": False, "global_holdout_ledger_prior_history_mutation_authorized": False,
    "failure_domain_evidence_schema_required": True, "synthetic_store_canary_scaffold_authorized": True,
    "failure_domain_evidence_metadata_schema_authorized": True, "candidate_store_access_authorized": False,
    "candidate_store_probe_authorized": False, "candidate_store_credential_access_authorized": False,
    "candidate_store_configuration_authorized": False, "synthetic_store_canary_execution_authorized": False,
    "real_artifact_store_operations_authorized": False, "review_evidence_packet_required": True,
    "review_evidence_packet_implemented": False, "real_data_access_authorized": False,
    "review_packet_real_data_inclusion_authorized": False, "review_packet_secret_inclusion_authorized": False,
    "real_artifact_creation_authorized": False, "validation_execution_authorized": False,
    "holdout_execution_authorized": False, "h001_primary_execution_budget": 0, "h001_primary_execution_count": 0,
    "required_durable_copy_count": 2, "scientific_authorization": False, "paper_trade_authorization": False,
    "live_authorization": False, "v0_disposition_unchanged": True,
}
_H001_BUNDLE_RELPATH = "docs/sandbox/example_candidate1_v1_hypothesis_001.json"
_H001_BUNDLE_SHA256 = "322b58eb5aa7b8b02d488ab182b38420afa8390cc36e054e1c1e96558905b82e"
_H001_BATCH_RECEIPT_SHA256 = "cb634f40a27204e2465392f3d8d2aaaf8e8af6f71dacba77b8506a66e465b3d5"
_SYNTHETIC_AMENDMENT_SHA256 = "46100af25d0b68d374e38df9c6c1902ac02e6c8d1c2df8307f56ed2ed37e32d0"
_H001_DESIGN_AMENDMENT_KEYS = {
    "allowed_actions", "amendment_id", "amendment_kind", "authorization_scope",
    "authorization_status", "governed_protocol_id", "non_effects", "predecessor_amendment",
    "prohibited_actions", "schema_version", "source_accounting_contract_sha256",
    "source_hypothesis_id", "source_main_commit", "source_rule_contract_sha256",
    "source_rule_kind", "source_scenario_contract_sha256", "source_synthetic_evidence_status",
    "source_synthetic_receipt_sha256", "transition_gates",
}
_H001_DESIGN_ALLOWED_ACTIONS = [
    "DRAFT_H001_REAL_FALSIFICATION_PREREGISTRATION_DESIGN",
    "IMPLEMENT_H001_PREREGISTRATION_SCHEMA_VALIDATOR_WITHOUT_DATA_ACCESS",
    "REVIEW_H001_REAL_FALSIFICATION_PREREGISTRATION_DESIGN",
]
_H001_DESIGN_AUTHORIZATION_SCOPE = (
    "A repository-owned design document and machine-readable preregistration may be created with "
    "status PREREGISTERED_DESIGN_ONLY, provided every real-data, artifact, execution, scientific, "
    "paper-trading and live authorization remains false."
)
_H001_DESIGN_NON_EFFECTS = [
    "DOES_NOT_ACCESS_REAL_DATA",
    "DOES_NOT_AUTHORIZE_OFFICIAL_EXECUTABLE_PROTOCOL",
    "DOES_NOT_AUTHORIZE_PAPER_TRADING",
    "DOES_NOT_AUTHORIZE_PROTOCOL_EXECUTION",
    "DOES_NOT_AUTHORIZE_REAL_DATA_ACCESS",
    "DOES_NOT_AUTHORIZE_SCIENTIFIC_CLAIMS",
    "DOES_NOT_AUTHORIZE_LIVE_INTEGRATION",
    "DOES_NOT_CHANGE_BLOCK_LIVE_INTEGRATION",
    "DOES_NOT_CHANGE_EDGE_UNPROVEN",
    "DOES_NOT_CHANGE_V0_ARTIFACT_STATE",
    "DOES_NOT_CONFIGURE_DURABLE_STORES",
    "DOES_NOT_CREATE_OR_BIND_REAL_DATA_ARTIFACTS",
    "DOES_NOT_CHANGE_V0_ARTIFACT_STATE",
    "DOES_NOT_INCREMENT_ANY_EXECUTION_COUNT",
    "DOES_NOT_FREEZE_OR_SELECT_DATASET_BYTES",
    "DOES_NOT_RECOVER_OR_RETIRE_V0",
]
_H001_DESIGN_NON_EFFECTS = sorted(set(_H001_DESIGN_NON_EFFECTS))
_H001_DESIGN_PROHIBITED_ACTIONS = sorted([
    "ACCESS_ANY_REAL_BARS_OR_FUNDING",
    "ACCESS_CANDIDATE1_V0_INPUT_OR_QUARANTINE",
    "CHOOSE_OR_INSPECT_REAL_DATASET_BYTES",
    "CONFIGURE_DURABLE_ARTIFACT_STORES",
    "CREATE_OR_BIND_REAL_DATA_ARTIFACT",
    "EXECUTE_H001",
    "CALCULATE_H001_REAL_RETURNS",
    "CONSUME_H001_EXECUTION_BUDGET",
    "FREEZE_REAL_DATA",
    "GRANT_PAPER_TRADE_AUTHORIZATION",
    "GRANT_REAL_DATA_ACCESS",
    "GRANT_SCIENTIFIC_AUTHORIZATION",
    "GRANT_LIVE_INTEGRATION_AUTHORIZATION",
    "INCREMENT_EXECUTION_COUNTS",
    "CLAIM_H001_HAS_MARKET_EDGE",
    "MUTATE_EXISTING_GOVERNANCE_AMENDMENTS",
    "MUTATE_EXISTING_HANDOFF_RECEIPTS",
    "RANK_OR_SELECT_H001_VARIANTS_FROM_SYNTHETIC_OUTPUT",
    "RECOVER_OR_RETIRE_V0",
])
_H001_DESIGN_TRANSITION_GATES = {
    "synthetic_adversarial_review_completed": True,
    "synthetic_batch_002_completed": True,
    "synthetic_falsification_conditions_passed": 15,
    "synthetic_falsification_conditions_total": 15,
    "synthetic_variant_selection_performed": False,
    "preregistration_design_requires_separate_review": True,
    "real_data_access_requires_later_governance": True,
    "real_artifact_operations_require_two_qualified_durable_stores": True,
    "execution_requires_frozen_artifact_identity": True,
    "execution_requires_implementation_and_environment_binding": True,
    "execution_requires_final_no_computation_preflight": True,
    "execution_requires_explicit_later_authorization": True,
    "required_durable_copy_count": 2,
    "h001_primary_execution_budget": 0,
    "h001_primary_execution_count": 0,
    "synthetic_evidence_is_scientific_evidence": False,
    "v0_disposition_unchanged": True,
}
_H001_COMPLETION_DECISIONS = {
    "H001_HYPOTHESIS_ID=candidate1-v1-funding-crowding-reversal-h001",
    "H001_BATCH_IDENTITY=H001_SYNTHETIC_BATCH_002",
    "H001_BATCH_002_STATUS=COMPLETED_MECHANICAL_ONLY",
    f"H001_BATCH_002_RECEIPT_SHA256={_H001_BATCH_RECEIPT_SHA256}",
    "H001_RUN_FINGERPRINT=13ba5ef1180f29bc1601c6fde2f5dc7f021f66ebb87de4e3ac967ab4bc2403b7",
    "H001_RULE_CONTRACT_SHA256=62718e4dc67e3c20a904e197ac7587f8cedbbc5a91b90e6315c189fc4072396a",
    "H001_SCENARIO_CONTRACT_SHA256=cde35c4f785525dce3639e38eb37ba9f64c55cdc63d6e82c16b87d7d60df7b30",
    "H001_ACCOUNTING_CONTRACT_SHA256=922977fc74ad59ba32c848bf27977f0579a61f544d830bac64fbb25abd15436c",
    "H001_SHAPE=variants:13,scenarios:15,results:195",
    "H001_SYNTHETIC_FALSIFICATION_CONDITIONS=15/15_PASS",
    "H001_DETERMINISTIC_REPLAY=PASSED",
    "H001_RECEIPT_VERIFICATION=PASSED",
    "H001_DISTINGUISHABLE_FROM_REGISTERED_SYNTHETIC_CONTROLS=TRUE",
    "H001_SYNTHETIC_IMPLEMENTATION_BLOCKER=NONE",
    "H001_SYNTHETIC_IMPLEMENTATION_MAJOR_FINDING=NONE",
    "H001_SYNTHETIC_IMPLEMENTATION_MINOR_FINDING=NONE",
    "H001_VARIANT_SELECTION=NONE",
    "H001_SCIENTIFIC_EVIDENCE=FALSE",
    "H001_REAL_FALSIFICATION_GOVERNANCE=NOT_YET_AUTHORIZED",
}
_SANDBOX_READY_FILES = [
    ".github/workflows/qnty-sandbox.yml",
    "docs/sandbox/CANDIDATE1_V1_SYNTHETIC_SANDBOX.md",
    "docs/sandbox/example_candidate1_v1_variants.json",
    "quantbot/sandbox/__init__.py",
    "quantbot/sandbox/candidate1_v1.py",
    "quantbot/sandbox/candidate1_v1_cli.py",
    "tests/sandbox/test_candidate1_v1.py",
]
_AMENDMENT_KEYS = {
    "allowed_actions", "amendment_id", "amendment_kind", "governed_protocol_id",
    "non_effects", "prohibited_actions", "rationale", "sandbox_id", "sandbox_status",
    "schema_version", "transition_gates",
}
_SANDBOX_ALLOWED_ACTIONS = [
    "BUILD_SYNTHETIC_FIXTURES",
    "DRAFT_SYNTHETIC_ONLY_INTERFACES",
    "IMPLEMENT_SYNTHETIC_ONLY_LIFECYCLE_SCAFFOLD",
    "RECORD_ALL_EXPLORED_VARIANTS",
    "RUN_SYNTHETIC_FAILURE_INJECTION",
    "RUN_SYNTHETIC_MECHANICAL_TESTS",
]
_SANDBOX_NON_EFFECTS = [
    "DOES_NOT_AUTHORIZE_OFFICIAL_V1_PROTOCOL",
    "DOES_NOT_AUTHORIZE_REAL_ARTIFACT_IDENTITY",
    "DOES_NOT_CHANGE_V0_ARTIFACT_STATE",
    "DOES_NOT_CHANGE_V0_EXECUTION_BUDGET",
    "DOES_NOT_RECOVER_V0",
    "DOES_NOT_RETIRE_V0",
    "DOES_NOT_SATISFY_DURABLE_STORE_GATE",
    "DOES_NOT_SUPERSEDE_V0_PROHIBITIONS",
]
_SANDBOX_PROHIBITED_ACTIONS = [
    "ACCESS_ANY_REAL_BARS_OR_FUNDING",
    "ACCESS_CANDIDATE1_V0_INPUT_OR_QUARANTINE",
    "ASSIGN_OR_CONSUME_SANDBOX_EXECUTION_BUDGET",
    "CALIBRATE_SYNTHETIC_PARAMETERS_TO_UNDOCUMENTED_REAL_BTC_BEHAVIOR",
    "CLAIM_SANDBOX_OUTPUT_AS_EDGE_EVIDENCE",
    "CREATE_OFFICIAL_V1_PROTOCOL",
    "CREATE_OR_BIND_REAL_V1_ARTIFACT",
    "FREEZE_OR_SELECT_REAL_V1_DATA",
    "GRANT_SCIENTIFIC_PAPER_OR_LIVE_AUTHORIZATION",
    "PREREGISTER_REAL_V1_PROTOCOL",
    "USE_SANDBOX_OUTPUT_TO_SILENTLY_SELECT_CONFIRMATORY_HYPOTHESIS",
]
_SANDBOX_TRANSITION_GATES = {
    "independent_review_required_before_sandbox_implementation": True,
    "official_v1_protocol_requires_separate_governance": True,
    "real_artifact_operations_require_two_qualified_durable_stores": True,
    "sandbox_execution_budget": 0,
    "sandbox_outputs_are_scientific_evidence": False,
    "v0_disposition_unchanged": True,
}
_V0_REQUIRED_PROHIBITIONS = {
    "RECOVER_OR_RETIRE_V0_BEFORE_DURABLE_ARTIFACT_PLANE",
    "EXECUTE_CANDIDATE1_PROTOCOL",
    "INSPECT_REAL_BARS_OR_FUNDING_BYTES",
    "ACCESS_QUARANTINE",
    "INCREMENT_EXECUTION_COUNTS",
    "GRANT_SCIENTIFIC_PAPER_OR_LIVE_AUTHORIZATION",
}
_SANDBOX_HANDOFF_PROHIBITIONS = {
    "ACCESS_REAL_DATA_IN_SYNTHETIC_SANDBOX",
    "ASSIGN_SANDBOX_EXECUTION_BUDGET",
    "CLAIM_SANDBOX_OUTPUT_AS_EDGE_EVIDENCE",
    "CREATE_OFFICIAL_V1_PROTOCOL_FROM_SANDBOX",
    "FREEZE_OR_SELECT_REAL_V1_DATA",
    "USE_UNDOCUMENTED_REAL_MARKET_MEMORY_FOR_SYNTHETIC_CALIBRATION",
}


def canonical_json_bytes(value: object) -> bytes:
    """Canonical QNTY JSON bytes: UTF-8, sorted keys, compact, ASCII, no newline."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _fail(message: str) -> None:
    raise ValueError(f"continuity verification failed: {message}")


def _require_str(value: object, label: str) -> str:
    if type(value) is not str or not value:
        _fail(f"{label} must be a non-empty string")
    return value


def _require_int(value: object, label: str) -> int:
    if type(value) is not int:
        _fail(f"{label} must be an int (bool is not accepted)")
    return value


def _require_bool(value: object, label: str) -> bool:
    if type(value) is not bool:
        _fail(f"{label} must be a bool")
    return value


def _require_sha256(value: object, label: str) -> str:
    if type(value) is not str or not _SHA256_RE.fullmatch(value):
        _fail(f"{label} must be a lowercase hex sha256")
    return value


def _require_repo_relative(value: object, label: str) -> str:
    path = _require_str(value, label)
    if path.startswith("/") or ".." in path.split("/") or path != path.strip():
        _fail(f"{label} must be a repository-relative path")
    return path


def _require_str_list(value: object, label: str, *, minimum: int = 0) -> list:
    if type(value) is not list or len(value) < minimum:
        _fail(f"{label} must be a list with at least {minimum} entries")
    for item in value:
        _require_str(item, f"{label} entry")
    return value


def _require_exact_keys(value: object, expected: set, label: str) -> dict:
    if type(value) is not dict:
        _fail(f"{label} must be a JSON object")
    if set(value) != expected:
        missing = sorted(expected - set(value))
        extra = sorted(set(value) - expected)
        _fail(f"{label} keys mismatch (missing={missing} extra={extra})")
    return value


def _load_canonical_document(data: bytes, label: str) -> dict:
    try:
        parsed = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        _fail(f"{label} is not strict UTF-8 JSON")
    if type(parsed) is not dict:
        _fail(f"{label} must be a JSON object")
    if data.endswith(b"\n") or data != canonical_json_bytes(parsed):
        _fail(f"{label} is not canonical QNTY JSON (sorted keys, compact, ASCII, no trailing newline)")
    return parsed


def _validate_active_task(parsed: dict) -> dict:
    _require_exact_keys(parsed, _ACTIVE_KEYS, "active_task")
    if parsed["schema_version"] != "0.1.0":
        _fail("active_task schema_version is not 0.1.0")
    if parsed["control_kind"] != "qnty_active_task_pointer":
        _fail("active_task control_kind is wrong")
    if parsed["task_id"] != TASK_ID:
        _fail("active_task task_id does not match the governed task")
    if parsed["protocol_id"] != PROTOCOL_ID:
        _fail("active_task protocol_id does not match the governed protocol")
    _require_str(parsed["phase"], "active_task phase")
    receipt_path = _require_repo_relative(parsed["handoff_receipt_path"], "handoff_receipt_path")
    expected_dir = f"docs/control/tasks/{TASK_ID}/"
    if not receipt_path.startswith(expected_dir) or not _RECEIPT_BASENAME_RE.fullmatch(receipt_path[len(expected_dir):]):
        _fail("handoff_receipt_path is not docs/control/tasks/<task_id>/handoff_vNNN.json")
    _require_sha256(parsed["handoff_receipt_sha256"], "handoff_receipt_sha256")
    return parsed


def _validate_safety_state(safety: object) -> dict:
    _require_exact_keys(safety, _SAFETY_KEYS, "safety_state")
    for key, expected in _EXPECTED_SAFETY.items():
        value = safety[key]
        if type(expected) is bool:
            _require_bool(value, f"safety_state {key}")
        elif type(expected) is int:
            _require_int(value, f"safety_state {key}")
        else:
            _require_str(value, f"safety_state {key}")
        if value != expected:
            _fail(f"safety_state {key} drifted from required value {expected!r}")
    _require_bool(safety["real_data_execution_requested"], "safety_state real_data_execution_requested")
    return safety


def _validate_required_artifacts(artifacts: object) -> list:
    if type(artifacts) is not list or not artifacts:
        _fail("required_artifacts must be a non-empty list")
    seen = set()
    for artifact in artifacts:
        _require_exact_keys(artifact, _ARTIFACT_KEYS, "required_artifacts entry")
        artifact_id = _require_str(artifact["artifact_id"], "artifact_id")
        if artifact_id in seen:
            _fail("required_artifacts contains a duplicate artifact_id")
        seen.add(artifact_id)
        _require_sha256(artifact["expected_manifest_sha256"], "expected_manifest_sha256")
        availability = _require_str(artifact["availability"], "availability")
        if availability not in _AVAILABILITY_STATES:
            _fail("availability must be UNAVAILABLE or VERIFIED_AVAILABLE")
        count = _require_int(artifact["verified_copy_count"], "verified_copy_count")
        if count < 0:
            _fail("verified_copy_count must be >= 0")
        paths = _require_str_list(artifact["canonical_paths"], "canonical_paths")
        for path in paths:
            for prefix in _PROHIBITED_CANONICAL_PATH_PREFIXES:
                if path == prefix or path.startswith(prefix + "/"):
                    _fail(f"canonical artifact path {path!r} is under prohibited prefix {prefix!r}")
        if len(set(paths)) != len(paths):
            _fail("canonical_paths must be unique; duplicates cannot evidence independent copies")
        if availability == "UNAVAILABLE":
            if count != 0:
                _fail("UNAVAILABLE artifact must have verified_copy_count 0")
            if paths:
                _fail("UNAVAILABLE artifact must not record canonical paths")
        if availability == "VERIFIED_AVAILABLE":
            if count < 2:
                _fail("VERIFIED_AVAILABLE requires at least two independently verified copies")
            if len(paths) < 2:
                _fail("VERIFIED_AVAILABLE requires at least two unique canonical paths")
            if count != len(paths):
                _fail("verified_copy_count must equal the number of unique canonical paths")
    if REQUIRED_ARTIFACT_ID not in seen:
        _fail(f"required artifact record {REQUIRED_ARTIFACT_ID!r} is missing")
    for artifact in artifacts:
        if artifact["artifact_id"] == REQUIRED_ARTIFACT_ID:
            if artifact["expected_manifest_sha256"] != REQUIRED_ARTIFACT_MANIFEST_SHA256:
                _fail("required artifact expected_manifest_sha256 drifted from the frozen fingerprint")
    return artifacts


def _validate_evidence(evidence: object, root: Path, *, verify_files: bool) -> list:
    """Validate evidence entries; historical receipts skip file re-hashing because
    evidence records what was observed when the immutable receipt was written."""
    if type(evidence) is not list:
        _fail("evidence must be a list")
    for item in evidence:
        _require_exact_keys(item, _EVIDENCE_KEYS, "evidence entry")
        path = _require_repo_relative(item["path"], "evidence path")
        expected = _require_sha256(item["sha256"], "evidence sha256")
        if not verify_files:
            continue
        target = root / path
        if not target.is_file():
            _fail(f"evidence file {path!r} is missing")
        if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
            _fail(f"evidence file {path!r} does not match its recorded sha256")
    return evidence


def _validate_sandbox_amendment(receipt: dict, root: Path, *, expected_next_action: str = _SANDBOX_NEXT_ACTION) -> dict:
    path = root / AMENDMENT_RELPATH
    if not path.is_file():
        _fail(f"sandbox amendment {AMENDMENT_RELPATH} is missing")
    amendment = _load_canonical_document(path.read_bytes(), "sandbox amendment")
    _require_exact_keys(amendment, _AMENDMENT_KEYS, "sandbox amendment")
    exact_strings = {
        "schema_version": "0.1.0", "amendment_kind": "qnty_governance_amendment",
        "amendment_id": "candidate1-v1-synthetic-sandbox-v001",
        "governed_protocol_id": PROTOCOL_ID, "sandbox_id": "candidate1-v1-synthetic-design-sandbox-v0",
        "sandbox_status": "AUTHORIZED_EXPLORATORY_ENGINEERING_ONLY",
    }
    for key, expected in exact_strings.items():
        if amendment[key] != expected:
            _fail(f"sandbox amendment {key} is wrong")
    for key, expected in (("allowed_actions", _SANDBOX_ALLOWED_ACTIONS), ("non_effects", _SANDBOX_NON_EFFECTS), ("prohibited_actions", _SANDBOX_PROHIBITED_ACTIONS)):
        value = _require_str_list(amendment[key], f"sandbox amendment {key}")
        if value != expected or len(value) != len(set(value)) or value != sorted(value):
            _fail(f"sandbox amendment {key} drifted")
    gates = _require_exact_keys(amendment["transition_gates"], set(_SANDBOX_TRANSITION_GATES), "sandbox amendment transition_gates")
    if gates != _SANDBOX_TRANSITION_GATES:
        _fail("sandbox amendment transition_gates drifted")
    evidence = {item["path"]: item["sha256"] for item in receipt["evidence"]}
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if evidence.get(AMENDMENT_RELPATH) != digest:
        _fail("sandbox amendment hash is not evidenced by the active handoff receipt")
    if receipt["next_actions"] != [expected_next_action]:
        _fail("sandbox phase next action is wrong")
    if not _V0_REQUIRED_PROHIBITIONS.issubset(receipt["prohibited_actions"]):
        _fail("sandbox phase dropped an existing V0 prohibition")
    if not _SANDBOX_HANDOFF_PROHIBITIONS.issubset(receipt["prohibited_actions"]):
        _fail("sandbox phase is missing a sandbox prohibition")
    if len(receipt["required_artifacts"]) != 1 or receipt["required_artifacts"][0]["artifact_id"] != REQUIRED_ARTIFACT_ID:
        _fail("sandbox phase cannot add a V1 required artifact")
    return amendment


def _validate_ready_handoff(receipt: dict, root: Path) -> None:
    """Validate the narrow post-implementation synthetic-only transition."""
    amendment = _validate_sandbox_amendment(receipt, root, expected_next_action=_SANDBOX_READY_NEXT_ACTION)
    del amendment
    if receipt["next_actions"] != [_SANDBOX_READY_NEXT_ACTION]:
        _fail("ready sandbox phase next action is wrong")
    if receipt["required_artifacts"] != [{
        "artifact_id": REQUIRED_ARTIFACT_ID,
        "availability": "UNAVAILABLE",
        "canonical_paths": [],
        "expected_manifest_sha256": REQUIRED_ARTIFACT_MANIFEST_SHA256,
        "verified_copy_count": 0,
    }]:
        _fail("ready sandbox phase changed the required V0 artifact state")
    evidence_paths = {item["path"] for item in receipt["evidence"]}
    for path in _SANDBOX_READY_FILES + [AMENDMENT_RELPATH]:
        if path not in evidence_paths:
            _fail(f"ready sandbox handoff is missing evidence for {path}")
        target = root / path
        if not target.is_file():
            _fail(f"ready sandbox evidence file {path} is missing")
    if receipt["safety_state"]["decomposition_execution_count"] != 0:
        _fail("ready sandbox changed V0 execution count")
    if receipt["safety_state"]["scientific_use_authorized"]:
        _fail("ready sandbox granted scientific authorization")
    if "USE_SANDBOX_OUTPUT_TO_SELECT_OFFICIAL_PROTOCOL" not in receipt["prohibited_actions"]:
        _fail("ready sandbox is missing selection prohibition")
    if "RANK_OR_RECOMMEND_SYNTHETIC_VARIANTS" not in receipt["prohibited_actions"]:
        _fail("ready sandbox is missing ranking prohibition")
    if "TREAT_SYNTHETIC_RECEIPT_AS_SCIENTIFIC_EVIDENCE" not in receipt["prohibited_actions"]:
        _fail("ready sandbox is missing evidence prohibition")


def _validate_h001_completion_handoff(receipt: dict, root: Path) -> None:
    """Validate the mechanical-only completion of H001 Synthetic Batch 002."""
    _validate_sandbox_amendment(receipt, root, expected_next_action=_H001_COMPLETE_NEXT_ACTION)
    if receipt["decisions"] and not _H001_COMPLETION_DECISIONS.issubset(receipt["decisions"]):
        _fail("H001 completion handoff is missing an exact Batch 002 completion decision")
    if receipt["required_artifacts"] != [{
        "artifact_id": REQUIRED_ARTIFACT_ID,
        "availability": "UNAVAILABLE",
        "canonical_paths": [],
        "expected_manifest_sha256": REQUIRED_ARTIFACT_MANIFEST_SHA256,
        "verified_copy_count": 0,
    }]:
        _fail("H001 completion changed the required V0 artifact state")
    evidence = {item["path"]: item["sha256"] for item in receipt["evidence"]}
    if evidence.get(_H001_BUNDLE_RELPATH) != _H001_BUNDLE_SHA256:
        _fail("H001 committed synthetic bundle is missing or has the wrong sha256")
    bundle = root / _H001_BUNDLE_RELPATH
    if not bundle.is_file() or hashlib.sha256(bundle.read_bytes()).hexdigest() != _H001_BUNDLE_SHA256:
        _fail("H001 committed synthetic bundle is missing or changed")
    expected_safety = dict(_EXPECTED_SAFETY, real_data_execution_requested=False)
    if receipt["safety_state"] != expected_safety:
        _fail("H001 completion changed an execution or authorization boundary")
    required_prohibitions = {
        "ACCESS_REAL_DATA_IN_SYNTHETIC_SANDBOX", "ACCESS_QUARANTINE", "FREEZE_OR_SELECT_REAL_V1_DATA",
        "CREATE_OR_BIND_REAL_V1_ARTIFACT", "EXECUTE_H001", "CALCULATE_H001_REAL_RETURNS",
        "INCREMENT_EXECUTION_COUNTS", "GRANT_SCIENTIFIC_PAPER_OR_LIVE_AUTHORIZATION",
        "RANK_OR_SELECT_H001_VARIANTS", "TREAT_SYNTHETIC_RESULTS_AS_SCIENTIFIC_EVIDENCE",
        "CREATE_OFFICIAL_H001_REAL_PROTOCOL", "PREREGISTER_H001_REAL_PROTOCOL_WITHOUT_SEPARATE_GOVERNANCE",
        "USE_SANDBOX_OUTPUT_TO_SELECT_OFFICIAL_PROTOCOL", "REGISTER_SYNTHETIC_RECEIPT_AS_REAL_ARTIFACT",
    }
    if not required_prohibitions.issubset(receipt["prohibited_actions"]):
        _fail("H001 completion is missing a real-data or synthetic-evidence prohibition")


def _validate_h001_design_amendment(receipt: dict, root: Path, *, expected_next_action: str = _H001_DESIGN_NEXT_ACTION) -> dict:
    path = root / REAL_H001_AMENDMENT_RELPATH
    if not path.is_file():
        _fail(f"H001 design amendment {REAL_H001_AMENDMENT_RELPATH} is missing")
    amendment = _load_canonical_document(path.read_bytes(), "H001 design amendment")
    _require_exact_keys(amendment, _H001_DESIGN_AMENDMENT_KEYS, "H001 design amendment")
    exact_strings = {
        "schema_version": "0.1.0",
        "amendment_kind": "qnty_governance_transition_amendment",
        "amendment_id": "candidate1-h001-real-falsification-design-v001",
        "governed_protocol_id": PROTOCOL_ID,
        "source_hypothesis_id": "candidate1-v1-funding-crowding-reversal-h001",
        "source_rule_kind": "FUNDING_CROWDING_REVERSAL",
        "authorization_status": "AUTHORIZED_PREREGISTRATION_DESIGN_ONLY",
        "source_main_commit": "22b9c40dd2bb58d852388683625cc1a4b449cb9b",
        "source_rule_contract_sha256": "62718e4dc67e3c20a904e197ac7587f8cedbbc5a91b90e6315c189fc4072396a",
        "source_scenario_contract_sha256": "cde35c4f785525dce3639e38eb37ba9f64c55cdc63d6e82c16b87d7d60df7b30",
        "source_accounting_contract_sha256": "922977fc74ad59ba32c848bf27977f0579a61f544d830bac64fbb25abd15436c",
        "source_synthetic_receipt_sha256": _H001_BATCH_RECEIPT_SHA256,
        "source_synthetic_evidence_status": "MECHANICAL_ONLY_NOT_SCIENTIFIC_EVIDENCE",
        "authorization_scope": _H001_DESIGN_AUTHORIZATION_SCOPE,
    }
    for key, expected in exact_strings.items():
        if amendment[key] != expected:
            _fail(f"H001 design amendment {key} is wrong")
    for key in ("source_main_commit", "source_rule_contract_sha256", "source_scenario_contract_sha256", "source_accounting_contract_sha256", "source_synthetic_receipt_sha256"):
        if key == "source_main_commit":
            if not _COMMIT_RE.fullmatch(amendment[key]):
                _fail(f"H001 design amendment {key} is malformed")
        elif not _SHA256_RE.fullmatch(amendment[key]):
            _fail(f"H001 design amendment {key} is malformed")
    for key, expected in (("allowed_actions", _H001_DESIGN_ALLOWED_ACTIONS), ("non_effects", _H001_DESIGN_NON_EFFECTS), ("prohibited_actions", _H001_DESIGN_PROHIBITED_ACTIONS)):
        value = _require_str_list(amendment[key], f"H001 design amendment {key}")
        if value != expected or len(value) != len(set(value)) or value != sorted(value):
            _fail(f"H001 design amendment {key} drifted")
    predecessor = _require_exact_keys(amendment["predecessor_amendment"], {"path", "sha256"}, "H001 design amendment predecessor_amendment")
    if predecessor != {"path": AMENDMENT_RELPATH, "sha256": _SYNTHETIC_AMENDMENT_SHA256}:
        _fail("H001 design amendment predecessor_amendment drifted")
    gates = _require_exact_keys(amendment["transition_gates"], set(_H001_DESIGN_TRANSITION_GATES), "H001 design amendment transition_gates")
    if gates != _H001_DESIGN_TRANSITION_GATES:
        _fail("H001 design amendment transition_gates drifted")
    evidence = {item["path"]: item["sha256"] for item in receipt["evidence"]}
    if evidence.get(AMENDMENT_RELPATH) != _SYNTHETIC_AMENDMENT_SHA256:
        _fail("original synthetic amendment hash is not evidenced by the active handoff receipt")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if evidence.get(REAL_H001_AMENDMENT_RELPATH) != digest:
        _fail("H001 design amendment hash is not evidenced by the active handoff receipt")
    if receipt["next_actions"] != [expected_next_action]:
        _fail("H001 design phase next action is wrong")
    if receipt["required_artifacts"] != [{
        "artifact_id": REQUIRED_ARTIFACT_ID,
        "availability": "UNAVAILABLE",
        "canonical_paths": [],
        "expected_manifest_sha256": REQUIRED_ARTIFACT_MANIFEST_SHA256,
        "verified_copy_count": 0,
    }]:
        _fail("H001 design phase changed the required V0 artifact state")
    if receipt["safety_state"] != dict(_EXPECTED_SAFETY, real_data_execution_requested=False):
        _fail("H001 design phase changed an execution or authorization boundary")
    required_prohibitions = set(_H001_DESIGN_PROHIBITED_ACTIONS) | {
        "PREREGISTER_H001_REAL_PROTOCOL_WITHOUT_SEPARATE_GOVERNANCE",
        "TREAT_SYNTHETIC_RESULTS_AS_SCIENTIFIC_EVIDENCE",
    }
    if not required_prohibitions.issubset(receipt["prohibited_actions"]):
        _fail("H001 design phase is missing a required prohibition")
    return amendment


def _validate_h001_preregistered_handoff(receipt: dict, root: Path) -> dict:
    """Validate the post-preregistration, review-only handoff."""
    amendment = _validate_h001_design_amendment(
        receipt, root, expected_next_action=_H001_PREREGISTERED_NEXT_ACTION
    )
    expected_scope = {
        "docs/experiments/CANDIDATE1_H001_REAL_DATA_FALSIFICATION_V0.md",
        H001_DESIGN_JSON_RELPATH,
        "quantbot/experiment/h001_real_falsification_preregistration.py",
        "tests/experiment/test_h001_real_falsification_preregistration.py",
        "quantbot/continuity/context.py",
        "tests/continuity/test_cross_agent_continuity.py",
        f"docs/control/tasks/{TASK_ID}/handoff_v011.json",
        ACTIVE_TASK_RELPATH,
    }
    if set(receipt["changed_file_scope"]) != expected_scope:
        _fail("H001 preregistered handoff changed_file_scope is not the exact eight-file scope")
    evidence = {item["path"]: item["sha256"] for item in receipt["evidence"]}
    # active_task points back to this receipt, so its bytes cannot be included
    # without creating a circular hash. The immutable receipt itself is likewise
    # identified by active_task rather than self-evidence.
    required_evidence = expected_scope - {f"docs/control/tasks/{TASK_ID}/handoff_v011.json", ACTIVE_TASK_RELPATH}
    required_evidence |= {AMENDMENT_RELPATH, REAL_H001_AMENDMENT_RELPATH}
    if not required_evidence.issubset(evidence):
        _fail("H001 preregistered handoff is missing required evidence")
    design_path = root / H001_DESIGN_JSON_RELPATH
    if not design_path.is_file() or evidence.get(H001_DESIGN_JSON_RELPATH) != hashlib.sha256(design_path.read_bytes()).hexdigest():
        _fail("H001 preregistration design JSON hash is not evidenced")
    if receipt["receipt_index"] != 11:
        _fail("H001 preregistered handoff must be receipt index 11")
    if receipt["source_branch"] != "feat/h001-real-falsification-preregistration-v0":
        _fail("H001 preregistered handoff source branch is wrong")
    return amendment


def _validate_h001_review_complete_handoff(receipt: dict, root: Path) -> dict:
    """Validate the append-only handoff that records completion of the
    independent adversarial re-review of the H001 real-data falsification
    preregistration.

    The preregistration design, validator, experiment, artifact records, store
    registry, and both governance amendments are unchanged; this transition only
    records the passed review and advances the next action to authorizing a
    *separate* infrastructure-preparation governance amendment. The external
    review is process assurance, not scientific evidence of any market edge, and
    every real-data, artifact, execution, scientific, paper, and live boundary
    stays exactly where the preregistered-design-only phase left it.
    """
    amendment = _validate_h001_design_amendment(
        receipt, root, expected_next_action=_H001_REVIEW_COMPLETE_NEXT_ACTION
    )
    if receipt["receipt_index"] != 12:
        _fail("H001 review-completion handoff must be receipt index 12")
    if receipt["source_branch"] != _H001_REVIEW_SOURCE_BRANCH:
        _fail("H001 review-completion handoff source branch is wrong")
    if receipt["source_head_commit"] != _H001_REVIEW_MERGED_MAIN_SHA:
        _fail("H001 review-completion handoff source_head_commit must be the merged-main base SHA")
    predecessor = receipt["predecessor"]
    if (
        type(predecessor) is not dict
        or predecessor.get("path") != f"docs/control/tasks/{TASK_ID}/handoff_v011.json"
        or predecessor.get("sha256") != _H001_PREREGISTERED_HANDOFF_SHA256
    ):
        _fail("H001 review-completion predecessor must be the exact v011 preregistration receipt")
    expected_scope = {
        "quantbot/continuity/context.py",
        "tests/continuity/test_cross_agent_continuity.py",
        f"docs/control/tasks/{TASK_ID}/handoff_v012.json",
        ACTIVE_TASK_RELPATH,
    }
    if set(receipt["changed_file_scope"]) != expected_scope:
        _fail("H001 review-completion changed_file_scope is not the exact four-file scope")
    if len(receipt["changed_file_scope"]) != len(expected_scope):
        _fail("H001 review-completion changed_file_scope has duplicate entries")
    if not _H001_REVIEW_REQUIRED_DECISIONS.issubset(receipt["decisions"]):
        missing = sorted(_H001_REVIEW_REQUIRED_DECISIONS - set(receipt["decisions"]))
        _fail(f"H001 review-completion handoff is missing required review decisions {missing}")
    if not _H001_REVIEW_REQUIRED_PROHIBITIONS.issubset(receipt["prohibited_actions"]):
        _fail("H001 review-completion handoff is missing a required prohibition")
    # Bind the reviewed preregistration artifacts by their exact reviewed bytes.
    evidence = {item["path"]: item["sha256"] for item in receipt["evidence"]}
    exact_evidence = {
        H001_DESIGN_JSON_RELPATH: _H001_REVIEW_DESIGN_SHA256,
        _H001_VALIDATOR_RELPATH: _H001_REVIEW_VALIDATOR_SHA256,
        _H001_FOCUSED_TEST_RELPATH: _H001_REVIEW_FOCUSED_TEST_SHA256,
        f"docs/control/tasks/{TASK_ID}/handoff_v011.json": _H001_PREREGISTERED_HANDOFF_SHA256,
    }
    for path, expected in exact_evidence.items():
        if evidence.get(path) != expected:
            _fail(f"H001 review-completion must evidence {path!r} by its exact reviewed sha256")
    return amendment


def _validate_h001_pre_data_handoff(receipt: dict, root: Path) -> dict:
    path = root / PRE_DATA_H001_AMENDMENT_RELPATH
    if not path.is_file():
        _fail(f"H001 pre-data assurance amendment {PRE_DATA_H001_AMENDMENT_RELPATH} is missing")
    amendment = _load_canonical_document(path.read_bytes(), "H001 pre-data assurance amendment")
    _require_exact_keys(amendment, _H001_PRE_DATA_AMENDMENT_KEYS, "H001 pre-data assurance amendment")
    exact = {
        "schema_version": "0.1.0", "amendment_kind": "qnty_governance_transition_amendment",
        "amendment_id": "candidate1-h001-pre-data-assurance-v001",
        "authorization_status": "AUTHORIZED_PRE_DATA_ASSURANCE_AND_SYNTHETIC_INFRASTRUCTURE_SCAFFOLD_ONLY",
        "governed_protocol_id": PROTOCOL_ID,
        "governed_h001_protocol_id": "real_btc_h001_funding_crowding_reversal_falsification_v0",
        "source_main_commit": "9a9e6b16c372cef9dfc99ff9ccd49fdc8e16b8f4",
        "strict_temporal_precedence_target": "funding_time_utc < decision_timestamp",
    }
    for key, expected in exact.items():
        if amendment[key] != expected:
            _fail(f"H001 pre-data assurance amendment {key} is wrong")
    if amendment["authorization_scope"] != (
        "Only repository-owned schema, validator, harness, documentation and synthetic-fixture scaffolding may be implemented. "
        "All implementation must operate without network access, Binance or market-data access, holdout access, real artifact bytes, "
        "artifact-store roots, store credentials, candidate-store probing, candidate-store configuration, ledger backfill, calibration "
        "execution, calibration-result exposure or calibration-spec freezing. The scaffold may describe later work but may not perform it."
    ):
        _fail("H001 pre-data assurance authorization_scope is wrong")
    for key, expected in (("allowed_actions", _H001_PRE_DATA_ALLOWED_ACTIONS), ("assurance_controls", _H001_PRE_DATA_ASSURANCE_CONTROLS),
                          ("non_effects", _H001_PRE_DATA_NON_EFFECTS), ("prohibited_actions", _H001_PRE_DATA_REQUIRED_PROHIBITIONS)):
        value = _require_str_list(amendment[key], f"H001 pre-data assurance amendment {key}")
        if value != expected or len(value) != len(set(value)) or value != sorted(value):
            _fail(f"H001 pre-data assurance amendment {key} drifted")
    predecessor = _require_exact_keys(amendment["predecessor_amendment"], {"path", "sha256"}, "predecessor_amendment")
    if predecessor != {"path": REAL_H001_AMENDMENT_RELPATH, "sha256": "5e3eff235212f52480fa00ba7ffabb4d75f4160d51d359dc6e5aa6b9d1b8b1e1"}:
        _fail("H001 pre-data assurance predecessor amendment drifted")
    source_handoff = _require_exact_keys(amendment["source_handoff"], {"path", "sha256"}, "source_handoff")
    if source_handoff != {"path": f"docs/control/tasks/{TASK_ID}/handoff_v012.json", "sha256": "260414954f579b7b1d6c56f1c2d68dbf5796017292630c6a3b36a28c9340c326"}:
        _fail("H001 pre-data assurance source handoff drifted")
    review = _require_exact_keys(amendment["review_binding"], _H001_PRE_DATA_REVIEW_BINDING_KEYS, "review_binding")
    if review != {"design_sha256": _H001_REVIEW_DESIGN_SHA256, "validator_sha256": _H001_REVIEW_VALIDATOR_SHA256,
                  "reviewed_implementation_head": _H001_REVIEW_REVIEWED_HEAD, "review_verdict": _H001_REVIEW_VERDICT}:
        _fail("H001 pre-data assurance review binding drifted")
    gates = _require_exact_keys(amendment["transition_gates"], set(_H001_PRE_DATA_TRANSITION_GATES), "transition_gates")
    if gates != _H001_PRE_DATA_TRANSITION_GATES:
        _fail("H001 pre-data assurance transition gates drifted")
    evidence = {item["path"]: item["sha256"] for item in receipt["evidence"]}
    required_evidence = {
        PRE_DATA_H001_AMENDMENT_RELPATH: hashlib.sha256(path.read_bytes()).hexdigest(),
        f"docs/control/tasks/{TASK_ID}/handoff_v012.json": "260414954f579b7b1d6c56f1c2d68dbf5796017292630c6a3b36a28c9340c326",
        REAL_H001_AMENDMENT_RELPATH: "5e3eff235212f52480fa00ba7ffabb4d75f4160d51d359dc6e5aa6b9d1b8b1e1",
        H001_DESIGN_JSON_RELPATH: _H001_REVIEW_DESIGN_SHA256,
        _H001_VALIDATOR_RELPATH: _H001_REVIEW_VALIDATOR_SHA256,
        _H001_FOCUSED_TEST_RELPATH: _H001_REVIEW_FOCUSED_TEST_SHA256,
        "docs/artifacts/candidate1-real-input-v0.json": "9c53466fe87ecc58c46ec63dd5fdde1e947318036a6c071e837e01ebb74a1324",
        STORE_REGISTRY_RELPATH: "ac53bea147d2e6bb91e779f64e43edb7b8eb6e5531a36884bea2499e7e111148",
        "quantbot/continuity/context.py": hashlib.sha256((root / "quantbot/continuity/context.py").read_bytes()).hexdigest(),
        "tests/continuity/test_cross_agent_continuity.py": hashlib.sha256((root / "tests/continuity/test_cross_agent_continuity.py").read_bytes()).hexdigest(),
    }
    for evidence_path, expected in required_evidence.items():
        if evidence.get(evidence_path) != expected:
            _fail(f"H001 pre-data assurance missing or wrong evidence for {evidence_path}")
    if receipt["receipt_index"] != 13:
        _fail("H001 pre-data assurance handoff must be receipt index 13")
    if receipt["source_branch"] != "feat/h001-predata-assurance-governance" or receipt["source_head_commit"] != "9a9e6b16c372cef9dfc99ff9ccd49fdc8e16b8f4":
        _fail("H001 pre-data assurance handoff source identity is wrong")
    if receipt["predecessor"] != {"path": f"docs/control/tasks/{TASK_ID}/handoff_v012.json", "sha256": "260414954f579b7b1d6c56f1c2d68dbf5796017292630c6a3b36a28c9340c326"}:
        _fail("H001 pre-data assurance handoff predecessor is wrong")
    expected_scope = {ACTIVE_TASK_RELPATH, PRE_DATA_H001_AMENDMENT_RELPATH, f"docs/control/tasks/{TASK_ID}/handoff_v013.json", "quantbot/continuity/context.py", "tests/continuity/test_cross_agent_continuity.py"}
    if set(receipt["changed_file_scope"]) != expected_scope or len(receipt["changed_file_scope"]) != len(expected_scope):
        _fail("H001 pre-data assurance handoff changed_file_scope is not the exact five-file scope")
    if receipt["next_actions"] != [_H001_PRE_DATA_NEXT_ACTION]:
        _fail("H001 pre-data assurance handoff next action is wrong")
    required_decisions = {
        "H001_PRE_DATA_ASSURANCE_GOVERNANCE=AUTHORIZED_SCAFFOLD_ONLY", "H001_PRE_DATA_ASSURANCE_EXECUTION=NOT_AUTHORIZED",
        "H001_TEMPORAL_CAUSALITY_AMENDMENT=REQUIRED_NOT_CREATED", "H001_TEMPORAL_CAUSALITY_TARGET=FUNDING_TIME_STRICTLY_BEFORE_DECISION",
        "H001_SYNTHETIC_NULL_CALIBRATION_SPEC=REQUIRED_NOT_FROZEN", "H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION=NOT_AUTHORIZED",
        "H001_BOOTSTRAP_BLOCK_LENGTH_TUNING=FORBIDDEN", "H001_HAC_LAG_TUNING=FORBIDDEN",
        "GLOBAL_REAL_PROTOCOL_HOLDOUT_LEDGER=REQUIRED_NOT_IMPLEMENTED", "H001_SYNTHETIC_STORE_CANARY_SCAFFOLD=AUTHORIZED_NOT_IMPLEMENTED",
        "H001_CANDIDATE_STORE_CONFIGURATION=NOT_AUTHORIZED", "H001_REVIEW_EVIDENCE_PACKET=REQUIRED_NOT_IMPLEMENTED",
        "H001_REAL_DATA_ACCESS=FORBIDDEN", "H001_ARTIFACT_OPERATIONS=FORBIDDEN", "H001_CURRENT_EXECUTION_BUDGET=0",
        "H001_CURRENT_EXECUTION_COUNT=0", "H001_SCIENTIFIC_AUTHORIZATION=FALSE", "H001_PAPER_TRADE_AUTHORIZATION=FALSE",
        "H001_LIVE_AUTHORIZATION=FALSE", "V0_AVAILABILITY=UNAVAILABLE", "V0_VERIFIED_COPY_COUNT=0",
        "DURABLE_STORES=UNCONFIGURED", "EDGE_UNPROVEN", "BLOCK_LIVE_INTEGRATION",
    }
    if not required_decisions.issubset(receipt["decisions"]):
        _fail("H001 pre-data assurance handoff is missing required boundary decisions")
    if not set(_H001_PRE_DATA_REQUIRED_PROHIBITIONS).issubset(receipt["prohibited_actions"]):
        _fail("H001 pre-data assurance handoff is missing required prohibitions")
    if receipt["required_artifacts"] != [{"artifact_id": REQUIRED_ARTIFACT_ID, "availability": "UNAVAILABLE", "canonical_paths": [], "expected_manifest_sha256": REQUIRED_ARTIFACT_MANIFEST_SHA256, "verified_copy_count": 0}]:
        _fail("H001 pre-data assurance changed the V0 artifact state")
    if receipt["safety_state"] != dict(_EXPECTED_SAFETY, real_data_execution_requested=False):
        _fail("H001 pre-data assurance changed an execution or authorization boundary")
    return amendment


def _validate_receipt_body(parsed: dict, label: str, root: Path, *, verify_evidence_files: bool) -> int:
    """Structural fail-closed validation shared by the active receipt and every
    historical receipt in the predecessor chain. Does not validate the
    ``predecessor`` link itself; the chain walk owns that."""
    _require_exact_keys(parsed, _RECEIPT_KEYS, label)
    if parsed["schema_version"] != "0.1.0":
        _fail(f"{label} schema_version is not 0.1.0")
    if parsed["receipt_kind"] != "qnty_cross_agent_handoff_receipt":
        _fail(f"{label} receipt_kind is wrong")
    index = _require_int(parsed["receipt_index"], f"{label} receipt_index")
    if index < 1:
        _fail(f"{label} receipt_index must be >= 1")
    _require_str(parsed["source_branch"], f"{label} source_branch")
    head = parsed["source_head_commit"]
    if type(head) is not str or not _COMMIT_RE.fullmatch(head):
        _fail(f"{label} source_head_commit must be a lowercase 40-hex commit")
    _require_str_list(parsed["decisions"], f"{label} decisions", minimum=1)
    _validate_safety_state(parsed["safety_state"])
    scope = _require_str_list(parsed["changed_file_scope"], f"{label} changed_file_scope", minimum=1)
    for path in scope:
        _require_repo_relative(path, f"{label} changed_file_scope entry")
    _validate_evidence(parsed["evidence"], root, verify_files=verify_evidence_files)
    artifacts = _validate_required_artifacts(parsed["required_artifacts"])
    _require_str_list(parsed["blockers"], f"{label} blockers")
    _require_str_list(parsed["verified_commands"], f"{label} verified_commands", minimum=1)
    next_actions = parsed["next_actions"]
    if type(next_actions) is not list or len(next_actions) != 1:
        _fail(f"{label} next_actions must contain exactly one action")
    _require_str(next_actions[0], f"{label} next_actions entry")
    _require_str_list(parsed["prohibited_actions"], f"{label} prohibited_actions", minimum=1)
    if parsed["safety_state"]["real_data_execution_requested"]:
        for artifact in artifacts:
            if artifact["availability"] != "VERIFIED_AVAILABLE":
                _fail(f"{label}: real-data execution requested while a required artifact is not VERIFIED_AVAILABLE")
    return index


def _validate_receipt(parsed: dict, active: dict, root: Path) -> dict:
    _validate_receipt_body(parsed, "handoff_receipt", root, verify_evidence_files=True)
    if parsed["task_id"] != active["task_id"]:
        _fail("handoff_receipt task_id does not match active_task")
    if parsed["protocol_id"] != active["protocol_id"]:
        _fail("handoff_receipt protocol_id does not match active_task")
    phase = active["phase"]
    amendment = None
    if phase == _DURABLE_PHASE:
        if parsed["next_actions"] != [_DURABLE_NEXT_ACTION]:
            _fail("durable phase next action is wrong")
        _cross_check_artifact_records(parsed, root)
        if parsed["safety_state"]["real_data_execution_requested"]:
            try:
                validate_operational_registry(root)
            except ArtifactRegistryError as error:
                _fail(f"current artifact operational verification failed: {error}")
    elif active["phase"] == _SANDBOX_PHASE:
        _cross_check_artifact_records(parsed, root)
        amendment = _validate_sandbox_amendment(parsed, root)
    elif active["phase"] == _SANDBOX_READY_PHASE:
        _cross_check_artifact_records(parsed, root)
        _validate_ready_handoff(parsed, root)
        amendment = _validate_sandbox_amendment(parsed, root, expected_next_action=_SANDBOX_READY_NEXT_ACTION)
    elif active["phase"] == _H001_COMPLETE_PHASE:
        _cross_check_artifact_records(parsed, root)
        _validate_h001_completion_handoff(parsed, root)
        amendment = _validate_sandbox_amendment(parsed, root, expected_next_action=_H001_COMPLETE_NEXT_ACTION)
    elif active["phase"] == _H001_DESIGN_PHASE:
        _cross_check_artifact_records(parsed, root)
        amendment = _validate_h001_design_amendment(parsed, root)
    elif active["phase"] == _H001_PREREGISTERED_PHASE:
        _cross_check_artifact_records(parsed, root)
        amendment = _validate_h001_preregistered_handoff(parsed, root)
    elif active["phase"] == _H001_REVIEW_COMPLETE_PHASE:
        _cross_check_artifact_records(parsed, root)
        amendment = _validate_h001_review_complete_handoff(parsed, root)
    elif active["phase"] == _H001_PRE_DATA_PHASE:
        _cross_check_artifact_records(parsed, root)
        amendment = _validate_h001_pre_data_handoff(parsed, root)
    else:
        _fail(f"unsupported active phase {phase!r}")
    _validate_predecessor_chain(parsed, root, active["handoff_receipt_path"])
    if amendment is not None:
        parsed = dict(parsed)
        if phase in (_H001_DESIGN_PHASE, _H001_PREREGISTERED_PHASE, _H001_REVIEW_COMPLETE_PHASE):
            parsed["_validated_h001_design_amendment"] = amendment
        elif phase == _H001_PRE_DATA_PHASE:
            parsed["_validated_h001_pre_data_amendment"] = amendment
        else:
            parsed["_validated_sandbox_amendment"] = amendment
    return parsed


def _cross_check_artifact_records(receipt: dict, root: Path) -> None:
    """Cross-check the active receipt's artifact summaries against the Git-owned
    artifact records under docs/artifacts/ (durable artifact plane v1).

    Applies to the active receipt only: historical receipts predate or
    postdate the registry state and stay validated by their immutable bytes.
    Fails closed when a record or the store registry is missing, noncanonical,
    not evidenced by the active receipt, or divergent from the receipt summary.
    """
    store_registry_path = root / STORE_REGISTRY_RELPATH
    if not store_registry_path.is_file():
        _fail(f"artifact store registry {STORE_REGISTRY_RELPATH} is missing")
    try:
        store_registry = validate_store_registry_bytes(store_registry_path.read_bytes())
    except ArtifactRegistryError as error:
        _fail(f"store registry invalid: {error}")
    evidence_by_path = {item["path"]: item["sha256"] for item in receipt["evidence"]}
    store_registry_bytes = store_registry_path.read_bytes()
    store_registry_sha = hashlib.sha256(store_registry_bytes).hexdigest()
    if evidence_by_path.get(STORE_REGISTRY_RELPATH) != store_registry_sha:
        _fail("artifact store registry hash is not evidenced by the active handoff receipt")
    for artifact in receipt["required_artifacts"]:
        record_relpath = f"{ARTIFACT_RECORDS_DIR_RELPATH}/{artifact['artifact_id']}.json"
        record_path = root / record_relpath
        if not record_path.is_file():
            _fail(f"artifact record {record_relpath} is missing")
        record_bytes = record_path.read_bytes()
        record_sha = hashlib.sha256(record_bytes).hexdigest()
        if evidence_by_path.get(record_relpath) != record_sha:
            _fail(f"artifact record {record_relpath} hash is not evidenced by the active handoff receipt")
        try:
            record = validate_artifact_record_bytes(record_bytes, expected_artifact_id=artifact["artifact_id"])
            cross_check_receipt_artifact(artifact, record, store_registry)
        except ArtifactRegistryError as error:
            _fail(f"artifact record {record_relpath} invalid: {error}")


def _validate_predecessor_chain(parsed: dict, root: Path, receipt_relpath: str) -> None:
    """Iteratively walk the append-only receipt chain from the active receipt all
    the way to the explicit GENESIS state, failing closed on any broken link."""
    expected_dir = f"docs/control/tasks/{TASK_ID}/"
    visited = {receipt_relpath}
    current = parsed
    current_index = parsed["receipt_index"]
    while True:
        predecessor = current["predecessor"]
        if current_index == 1:
            if predecessor != "GENESIS":
                _fail("receipt_index 1 must declare the explicit genesis state 'GENESIS'")
            return
        if predecessor == "GENESIS":
            _fail("GENESIS is only valid at receipt_index 1")
        _require_exact_keys(predecessor, _PREDECESSOR_KEYS, "predecessor")
        path = _require_repo_relative(predecessor["path"], "predecessor path")
        if not path.startswith(expected_dir) or not _RECEIPT_BASENAME_RE.fullmatch(path[len(expected_dir):]):
            _fail("predecessor path must be docs/control/tasks/<task_id>/handoff_vNNN.json")
        if path in visited:
            _fail("predecessor chain contains a cycle or repeated receipt path")
        visited.add(path)
        expected_sha = _require_sha256(predecessor["sha256"], "predecessor sha256")
        target = root / path
        if not target.is_file():
            _fail(f"predecessor receipt {path!r} is missing")
        data = target.read_bytes()
        if hashlib.sha256(data).hexdigest() != expected_sha:
            _fail(f"predecessor receipt {path!r} bytes do not match the recorded sha256")
        previous = _load_canonical_document(data, "predecessor receipt")
        previous_index = _validate_receipt_body(previous, "predecessor receipt", root, verify_evidence_files=False)
        if previous_index != current_index - 1:
            _fail("predecessor receipt_index does not chain to this receipt")
        if previous["task_id"] != parsed["task_id"] or previous["protocol_id"] != parsed["protocol_id"]:
            _fail("predecessor identity does not match this receipt")
        current = previous
        current_index = previous_index


def _validate_entrypoints(root: Path) -> None:
    start_here = root / START_HERE_RELPATH
    if not start_here.is_file():
        _fail(f"canonical shared contract {START_HERE_RELPATH} is missing")
    if ACTIVE_TASK_RELPATH not in start_here.read_text(encoding="utf-8"):
        _fail("canonical shared contract does not point at the machine-readable control state")
    claude = root / CLAUDE_ENTRYPOINT_RELPATH
    if not claude.is_file() or CLAUDE_CONTRACT_POINTER not in claude.read_text(encoding="utf-8"):
        _fail("CLAUDE.md entrypoint is missing the canonical-contract import pointer")
    agents = root / CODEX_ENTRYPOINT_RELPATH
    if not agents.is_file():
        _fail("AGENTS.md entrypoint is missing")
    agents_text = agents.read_text(encoding="utf-8")
    if CODEX_CONTRACT_POINTER not in agents_text:
        _fail("AGENTS.md entrypoint is missing the canonical-contract pointer")
    if VERIFY_COMMAND not in agents_text:
        _fail("AGENTS.md entrypoint does not require running the context verifier")


def load_and_verify_continuity_state(root: Path) -> dict:
    """Fail-closed load of the whole continuity control plane rooted at *root*."""
    root = Path(root)
    active_path = root / ACTIVE_TASK_RELPATH
    if not active_path.is_file():
        _fail(f"{ACTIVE_TASK_RELPATH} is missing")
    active = _validate_active_task(_load_canonical_document(active_path.read_bytes(), "active_task"))
    receipt_path = root / active["handoff_receipt_path"]
    if not receipt_path.is_file():
        _fail(f"handoff receipt {active['handoff_receipt_path']!r} is missing")
    receipt_bytes = receipt_path.read_bytes()
    digest = hashlib.sha256(receipt_bytes).hexdigest()
    if digest != active["handoff_receipt_sha256"]:
        _fail("active_task pointer is stale: handoff receipt bytes do not match handoff_receipt_sha256")
    receipt = _validate_receipt(_load_canonical_document(receipt_bytes, "handoff_receipt"), active, root)
    _validate_entrypoints(root)
    return {
        "active_task": active,
        "handoff_receipt": receipt,
        "handoff_receipt_sha256": digest,
        **({"sandbox_amendment": receipt["_validated_sandbox_amendment"]} if "_validated_sandbox_amendment" in receipt else {}),
        **({"h001_design_amendment": receipt["_validated_h001_design_amendment"]} if "_validated_h001_design_amendment" in receipt else {}),
        **({"h001_pre_data_amendment": receipt["_validated_h001_pre_data_amendment"]} if "_validated_h001_pre_data_amendment" in receipt else {}),
    }


def render_context_packet(state: dict) -> str:
    """Deterministic context packet derived only from validated state."""
    active = state["active_task"]
    receipt = state["handoff_receipt"]
    safety = receipt["safety_state"]
    lines = [
        "QNTY_CONTINUITY_CONTEXT_PACKET schema=0.1.0",
        f"TASK={active['task_id']}",
        f"PROTOCOL={active['protocol_id']}",
        f"PHASE={active['phase']}",
        (
            "SAFETY"
            f" edge_status={safety['edge_status']}"
            f" live_status={safety['live_status']}"
            f" scientific_use_authorized={str(safety['scientific_use_authorized']).lower()}"
            f" paper_trade_authorized={str(safety['paper_trade_authorized']).lower()}"
            f" live_integration_authorized={str(safety['live_integration_authorized']).lower()}"
            f" execution_count={safety['decomposition_execution_count']}/{safety['decomposition_execution_budget']}"
            f" quarantine_access={safety['quarantine_access']}"
        ),
    ]
    blocked_reasons = [
        f"artifact_not_verified_available:{artifact['artifact_id']}"
        for artifact in receipt["required_artifacts"]
        if artifact["availability"] != "VERIFIED_AVAILABLE"
    ]
    if blocked_reasons:
        lines.append("PROTOCOL_EXECUTION=BLOCKED reasons=" + ",".join(sorted(blocked_reasons)))
    else:
        lines.append("PROTOCOL_EXECUTION=NOT_AUTHORIZED_HERE reasons=preregistration_preconditions_apply")
    lines.append(
        "LATEST_HANDOFF"
        f" path={active['handoff_receipt_path']}"
        f" sha256={state['handoff_receipt_sha256']}"
        f" index={receipt['receipt_index']}"
    )
    for blocker in receipt["blockers"]:
        lines.append(f"BLOCKER={blocker}")
    lines.append(f"NEXT_ACTION={receipt['next_actions'][0]}")
    for artifact in receipt["required_artifacts"]:
        lines.append(
            "REQUIRED_ARTIFACT"
            f" id={artifact['artifact_id']}"
            f" expected_manifest_sha256={artifact['expected_manifest_sha256']}"
            f" availability={artifact['availability']}"
            f" verified_copies={artifact['verified_copy_count']}"
        )
    if active["phase"] == _SANDBOX_PHASE:
        amendment = state["sandbox_amendment"]
        lines.extend([
            f"SYNTHETIC_SANDBOX id={amendment['sandbox_id']} status={amendment['sandbox_status']} execution_budget={amendment['transition_gates']['sandbox_execution_budget']}",
            "SYNTHETIC_SANDBOX_REAL_DATA=FORBIDDEN",
            f"SYNTHETIC_SANDBOX_SCIENTIFIC_EVIDENCE={str(amendment['transition_gates']['sandbox_outputs_are_scientific_evidence']).upper()}",
            "DURABLE_STORE_GATE=REQUIRED_FOR_REAL_ARTIFACT_OPERATIONS",
            "V0_DISPOSITION=UNCHANGED",
        ])
    elif active["phase"] == _SANDBOX_READY_PHASE:
        amendment = state["sandbox_amendment"]
        lines.extend([
            "SYNTHETIC_SANDBOX_IMPLEMENTATION=READY",
            "SYNTHETIC_STRATEGY_BATCH=AUTHORIZED_MECHANICAL_ONLY",
            "SYNTHETIC_VARIANT_PROVENANCE=REQUIRED",
            "SYNTHETIC_SELECTION=FORBIDDEN",
            "REAL_DATA_ACCESS=FORBIDDEN",
            "SCIENTIFIC_EVIDENCE=FALSE",
            f"SYNTHETIC_SANDBOX id={amendment['sandbox_id']} status={amendment['sandbox_status']} execution_budget={amendment['transition_gates']['sandbox_execution_budget']}",
            "SYNTHETIC_SANDBOX_REAL_DATA=FORBIDDEN",
            "SYNTHETIC_SANDBOX_SCIENTIFIC_EVIDENCE=FALSE",
            "DURABLE_STORE_GATE=REQUIRED_FOR_REAL_ARTIFACT_OPERATIONS",
            "V0_DISPOSITION=UNCHANGED",
        ])
    elif active["phase"] == _H001_COMPLETE_PHASE:
        lines.extend([
            "H001_SYNTHETIC_STATUS=FALSIFICATION_COMPLETE_MECHANICAL_ONLY",
            f"H001_BATCH_002_RECEIPT_SHA256={_H001_BATCH_RECEIPT_SHA256}",
            "H001_SYNTHETIC_FALSIFICATION_CONDITIONS=15/15_PASS",
            "H001_VARIANT_SELECTION=NONE",
            "H001_SCIENTIFIC_EVIDENCE=FALSE",
            "H001_REAL_FALSIFICATION_GOVERNANCE=NOT_YET_AUTHORIZED",
            "H001_REAL_DATA_ACCESS=FORBIDDEN",
            "H001_EXECUTION_AUTHORIZED=FALSE",
            f"H001_PRIMARY_EXECUTION_COUNT={safety['decomposition_execution_count']}",
            "H001_DURABLE_STORES_CONFIGURED=FALSE",
            "EDGE_STATUS=EDGE_UNPROVEN",
            "LIVE_STATUS=BLOCK_LIVE_INTEGRATION",
            "DURABLE_STORE_GATE=REQUIRED_FOR_REAL_ARTIFACT_OPERATIONS",
            "V0_DISPOSITION=UNCHANGED",
        ])
    elif active["phase"] == _H001_DESIGN_PHASE:
        lines.extend([
            "H001_REAL_FALSIFICATION_GOVERNANCE=AUTHORIZED_PREREGISTRATION_DESIGN_ONLY",
            "H001_PREREGISTRATION_DESIGN=ALLOWED",
            "H001_REAL_DATA_ACCESS=FORBIDDEN",
            "H001_REAL_DATA_EXECUTION=FORBIDDEN",
            "H001_PRIMARY_EXECUTION_BUDGET=0",
            "H001_PRIMARY_EXECUTION_COUNT=0",
            "H001_REQUIRED_DURABLE_COPIES=2",
            "H001_DURABLE_STORES_CONFIGURED=FALSE",
            "H001_SCIENTIFIC_AUTHORIZATION=FALSE",
            "H001_PAPER_TRADE_AUTHORIZATION=FALSE",
            "H001_LIVE_AUTHORIZATION=FALSE",
            "V0_AVAILABILITY=UNAVAILABLE",
            "EDGE_STATUS=EDGE_UNPROVEN",
            "LIVE_STATUS=BLOCK_LIVE_INTEGRATION",
        ])
    elif active["phase"] == _H001_PREREGISTERED_PHASE:
        lines.extend([
            "H001_REAL_FALSIFICATION_PROTOCOL=PREREGISTERED_DESIGN_ONLY",
            "H001_PROTOCOL_ID=real_btc_h001_funding_crowding_reversal_falsification_v0",
            "H001_DATA_IDENTITY=UNBOUND_DESIGN_ONLY",
            "H001_REAL_DATA_ACCESS=FORBIDDEN",
            "H001_ARTIFACT_OPERATIONS=FORBIDDEN",
            "H001_VALIDATION_EXECUTION_AUTHORIZED=FALSE",
            "H001_HOLDOUT_EXECUTION_AUTHORIZED=FALSE",
            "H001_CURRENT_EXECUTION_BUDGET=0",
            "H001_CURRENT_EXECUTION_COUNT=0",
            "H001_CANDIDATE_TRIAL_COUNT=9",
            "H001_REQUIRED_DURABLE_COPIES=2",
            "H001_DURABLE_STORES_CONFIGURED=FALSE",
            "H001_SCIENTIFIC_AUTHORIZATION=FALSE",
            "H001_PAPER_TRADE_AUTHORIZATION=FALSE",
            "H001_LIVE_AUTHORIZATION=FALSE",
            "V0_AVAILABILITY=UNAVAILABLE",
            "EDGE_STATUS=EDGE_UNPROVEN",
            "LIVE_STATUS=BLOCK_LIVE_INTEGRATION",
        ])
    elif active["phase"] == _H001_REVIEW_COMPLETE_PHASE:
        lines.extend([
            "H001_PREREGISTRATION_REVIEW_STATUS=PASSED",
            f"H001_PREREGISTRATION_REVIEW_VERDICT={_H001_REVIEW_VERDICT}",
            f"H001_PREREGISTRATION_REVIEWED_HEAD={_H001_REVIEW_REVIEWED_HEAD}",
            f"H001_PREREGISTRATION_DESIGN_SHA256={_H001_REVIEW_DESIGN_SHA256}",
            f"H001_PREREGISTRATION_VALIDATOR_SHA256={_H001_REVIEW_VALIDATOR_SHA256}",
            "H001_PREREGISTRATION_REVIEW_NAMED_PROBES=67/67_REJECTED",
            "H001_PREREGISTRATION_REVIEW_GENUINE_MUTATIONS=1136/1136_REJECTED",
            "H001_PREREGISTRATION_REVIEW_BLOCKERS=NONE",
            "H001_PREREGISTRATION_REVIEW_MAJOR_FINDINGS=NONE",
            "H001_EXTERNAL_REVIEW_IS_SCIENTIFIC_EVIDENCE=FALSE",
            "H001_REAL_FALSIFICATION_PROTOCOL=PREREGISTERED_DESIGN_ONLY",
            "H001_PROTOCOL_ID=real_btc_h001_funding_crowding_reversal_falsification_v0",
            "H001_DATA_IDENTITY=UNBOUND_DESIGN_ONLY",
            "H001_REAL_DATA_ACCESS=FORBIDDEN",
            "H001_ARTIFACT_OPERATIONS=FORBIDDEN",
            "H001_VALIDATION_EXECUTION_AUTHORIZED=FALSE",
            "H001_HOLDOUT_EXECUTION_AUTHORIZED=FALSE",
            # Execution budgets are rendered with distinct labels so the umbrella
            # decomposition budget can never be misread as an H001 budget.
            f"UMBRELLA_DECOMPOSITION_EXECUTION={safety['decomposition_execution_count']}/{safety['decomposition_execution_budget']}",
            "H001_EXECUTION=0/0",
            "H001_CURRENT_EXECUTION_BUDGET=0",
            "H001_CURRENT_EXECUTION_COUNT=0",
            "H001_REQUIRED_DURABLE_COPIES=2",
            "H001_DURABLE_STORES_CONFIGURED=FALSE",
            "H001_SCIENTIFIC_AUTHORIZATION=FALSE",
            "H001_PAPER_TRADE_AUTHORIZATION=FALSE",
            "H001_LIVE_AUTHORIZATION=FALSE",
            "H001_REAL_DATA_INFRASTRUCTURE_GOVERNANCE=NOT_YET_AUTHORIZED",
            "H001_REAL_DATA_INFRASTRUCTURE_PREPARATION=REQUIRES_SEPARATE_GOVERNANCE_AMENDMENT",
            "V0_AVAILABILITY=UNAVAILABLE",
            "EDGE_STATUS=EDGE_UNPROVEN",
            "LIVE_STATUS=BLOCK_LIVE_INTEGRATION",
        ])
    elif active["phase"] == _H001_PRE_DATA_PHASE:
        lines.extend([
            "H001_PRE_DATA_ASSURANCE_GOVERNANCE=AUTHORIZED_SCAFFOLD_ONLY",
            "H001_PRE_DATA_ASSURANCE_EXECUTION=NOT_AUTHORIZED",
            "H001_SYNTHETIC_NULL_CALIBRATION_SPEC_DRAFT=AUTHORIZED",
            "H001_SYNTHETIC_NULL_CALIBRATION_SPEC_FREEZE=NOT_AUTHORIZED",
            "H001_SYNTHETIC_NULL_CALIBRATION_SPEC=REQUIRED_NOT_FROZEN",
            "H001_TEMPORAL_CAUSALITY_AMENDMENT=REQUIRED_NOT_CREATED",
            "H001_TEMPORAL_CAUSALITY_TARGET=FUNDING_TIME_STRICTLY_BEFORE_DECISION",
            "H001_SYNTHETIC_NULL_CALIBRATION_EXECUTION=NOT_AUTHORIZED",
            "H001_BOOTSTRAP_BLOCK_LENGTH_TUNING=FORBIDDEN",
            "H001_HAC_LAG_TUNING=FORBIDDEN",
            "GLOBAL_REAL_PROTOCOL_HOLDOUT_LEDGER_SCOPE=SCHEMA_ONLY",
            "GLOBAL_REAL_PROTOCOL_HOLDOUT_LEDGER_DATA_ACCESS=FORBIDDEN",
            "GLOBAL_REAL_PROTOCOL_HOLDOUT_LEDGER_BACKFILL=FORBIDDEN",
            "GLOBAL_REAL_PROTOCOL_HOLDOUT_LEDGER=REQUIRED_NOT_IMPLEMENTED",
            "H001_SYNTHETIC_STORE_CANARY_SCAFFOLD=AUTHORIZED_NOT_IMPLEMENTED",
            "H001_FAILURE_DOMAIN_EVIDENCE_SCOPE=METADATA_SCHEMA_ONLY",
            "H001_CANDIDATE_STORE_ACCESS_OR_PROBING=FORBIDDEN",
            "H001_CANDIDATE_STORE_CONFIGURATION=NOT_AUTHORIZED",
            "H001_REVIEW_PACKET_REAL_DATA_INCLUSION=FORBIDDEN",
            "H001_REVIEW_PACKET_SECRET_INCLUSION=FORBIDDEN",
            "H001_REAL_DATA_ACCESS=FORBIDDEN",
            "H001_EXECUTION=0/0",
            f"UMBRELLA_DECOMPOSITION_EXECUTION={safety['decomposition_execution_count']}/{safety['decomposition_execution_budget']}",
            "V0_AVAILABILITY=UNAVAILABLE",
            "H001_DURABLE_STORES_CONFIGURED=FALSE",
            "H001_SCIENTIFIC_AUTHORIZATION=FALSE",
            "H001_PAPER_TRADE_AUTHORIZATION=FALSE",
            "H001_LIVE_AUTHORIZATION=FALSE",
        ])
    for prohibited in receipt["prohibited_actions"]:
        lines.append(f"PROHIBITED={prohibited}")
    return "\n".join(lines)
