"""Strict, metadata-only validators for the H001 assurance scaffolds.

This module deliberately has no filesystem discovery, networking, artifact-store,
database, environment, or real-data dependencies.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime

SCHEMA_VERSION = "0.1.0"
H001_PROTOCOL_ID = "real_btc_h001_funding_crowding_reversal_falsification_v0"
H001_DESIGN_SHA256 = "055ea162a11d4042320daeb74e153ebbd27969dd29a60c226cb84a8fc38b8900"
H001_VALIDATOR_SHA256 = "888bc4663e3d7fb9b398f944bf2b67553e8959e0173be77183ca8b288156172a"
GOVERNANCE_AMENDMENT_SHA256 = "a22d0cf260f31d7104fc4d4fe96030c8666179c20c7737dfe20a59f3c7200ddc"

SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
SECRET_KEYS = {"token", "secret", "password", "credential", "private_key", "cookie", "authorization", "api_key"}
FORBIDDEN_KEYS = {"returns", "prices", "funding", "p_values", "p-values", "statistics", "performance", "strategy_ranking", "raw_data", "artifact_bytes", "store_roots", "store_uri", "credentials", "private_reasoning", "chain_of_thought", "scientific_claim", "result_payload"}

class AssuranceValidationError(ValueError):
    pass

def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")

def _fail(message: str) -> None:
    raise AssuranceValidationError(message)

def _keys(value: object, expected: set[str], label: str) -> dict:
    if type(value) is not dict or set(value) != expected:
        _fail(f"{label}: exact keys required")
    return value

def _str(value: object, label: str) -> str:
    if type(value) is not str or not value:
        _fail(f"{label}: non-empty string required")
    return value

def _sha(value: object, label: str) -> str:
    if type(value) is not str or not SHA256_RE.fullmatch(value):
        _fail(f"{label}: lowercase sha256 required")
    return value

def _list(value: object, label: str, *, sorted_unique: bool = False) -> list:
    if type(value) is not list:
        _fail(f"{label}: list required")
    if sorted_unique and value != sorted(value) or sorted_unique and len(value) != len(set(value)):
        _fail(f"{label}: sorted unique list required")
    return value

def _walk_forbidden(value: object) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if type(key) is not str:
                _fail("keys must be strings")
            low = key.lower()
            if low in SECRET_KEYS or low in FORBIDDEN_KEYS:
                _fail(f"forbidden field: {key}")
            _walk_forbidden(child)
    elif isinstance(value, list):
        for child in value:
            _walk_forbidden(child)
    elif type(value) is str:
        if value.startswith("/") or value.startswith(("http://", "https://", "qnty-artifact://")):
            _fail("absolute paths, store URIs, and network URLs are forbidden")

def _base(value: object, kind: str, ident: str, status: str, keys: set[str]) -> dict:
    data = _keys(value, keys, kind)
    if data["schema_version"] != SCHEMA_VERSION or data["document_kind"] != kind or data["document_id"] != ident or data["status"] != status:
        _fail(f"{kind}: identity or status drifted")
    _walk_forbidden(data)
    return data

def validate_temporal_amendment_draft(value: object) -> dict:
    keys = {"document_id", "document_kind", "governed_h001_protocol_id", "hash_bindings", "non_effects", "proposed_change", "status", "unchanged_held_funding_rule", "schema_version"}
    data = _base(value, "qnty_h001_temporal_causality_amendment_draft", "candidate1-h001-temporal-causality-amendment-draft-v001", "DRAFT_ONLY_NOT_EFFECTIVE", keys)
    if data["governed_h001_protocol_id"] != H001_PROTOCOL_ID:
        _fail("temporal protocol drifted")
    _keys(data["hash_bindings"], {"current_design_sha256", "current_validator_sha256", "governance_amendment_sha256"}, "hash_bindings")
    if data["hash_bindings"] != {"current_design_sha256": H001_DESIGN_SHA256, "current_validator_sha256": H001_VALIDATOR_SHA256, "governance_amendment_sha256": GOVERNANCE_AMENDMENT_SHA256}:
        _fail("temporal hash binding drifted")
    _keys(data["proposed_change"], {"current_signal_rule", "proposed_signal_rule"}, "proposed_change")
    if data["proposed_change"] != {"current_signal_rule": "funding_time_utc <= decision_timestamp", "proposed_signal_rule": "funding_time_utc < decision_timestamp"}:
        _fail("temporal proposal drifted")
    if data["unchanged_held_funding_rule"] != "decision_timestamp < funding_time_utc <= interval_close" or "CURRENT_H001_PREREGISTRATION_UNCHANGED" not in data["non_effects"]:
        _fail("temporal non-effects drifted")
    if not _list(data["non_effects"], "non_effects", sorted_unique=True) or "PROPOSED_RULE_NOT_APPLIED" not in data["non_effects"]:
        _fail("temporal non-effects must remain explicit")
    return data

def _validate_bindings(data: dict) -> None:
    binding = _keys(data["hash_bindings"], {"current_design_sha256", "current_validator_sha256", "governance_amendment_sha256"}, "hash_bindings")
    if binding != {"current_design_sha256": H001_DESIGN_SHA256, "current_validator_sha256": H001_VALIDATOR_SHA256, "governance_amendment_sha256": GOVERNANCE_AMENDMENT_SHA256}:
        _fail("H001 hash bindings drifted")

def validate_calibration_spec_draft(value: object) -> dict:
    keys = {"document_id", "document_kind", "hash_bindings", "proposed_design", "proposed_dgp_suite", "proposed_diagnostic_stress_cases", "proposed_pass_criterion", "proposed_outer_replications", "status", "schema_version"}
    data = _base(value, "qnty_h001_synthetic_null_calibration_spec_draft", "h001-synthetic-null-calibration-spec-draft-v001", "DRAFT_ONLY_UNFROZEN_NOT_EXECUTABLE", keys)
    _validate_bindings(data)
    design = _keys(data["proposed_design"], {"bootstrap_repetitions", "familywise_alpha", "h000_test_target", "hac_lag", "inner_procedure", "registered_variant_series", "stationary_block_length"}, "proposed_design")
    expected = {"bootstrap_repetitions": 10000, "familywise_alpha": 0.05, "h000_test_target": "the exact registered synchronous stationary-bootstrap maximum-t procedure", "hac_lag": 21, "inner_procedure": "stationary-bootstrap maximum-t", "registered_variant_series": 9, "stationary_block_length": 63}
    if design != expected:
        _fail("proposed calibration design drifted")
    if _list(data["proposed_dgp_suite"], "proposed_dgp_suite", sorted_unique=True) != ["IID Gaussian", "IID Student-t with df=5", "nine-series common-factor dependence", "stationary AR(1), phi=0.3", "stationary AR(1), phi=0.7", "stationary GARCH(1,1)-like volatility"]:
        _fail("required DGP suite drifted")
    if data["proposed_outer_replications"] != 2000 or _list(data["proposed_diagnostic_stress_cases"], "stress cases", sorted_unique=True) != ["autocorrelation structural break", "mean-zero regime switching", "sparse extreme outliers", "variance structural break"]:
        _fail("calibration replication or stress cases drifted")
    if data["proposed_pass_criterion"] != "for every required stationary DGP, the one-sided 95% binomial upper confidence bound for empirical FWER is <= 0.075":
        _fail("calibration pass criterion drifted")
    return data

def _entry(value: object) -> dict:
    data = _keys(value, {"dataset_region_id", "disclosure_kind", "disclosure_status", "entry_id", "hypothesis_id", "protocol_id", "recorded_at_utc", "region_end_utc", "region_start_utc", "source_control_receipt_path", "source_control_receipt_sha256"}, "ledger entry")
    _str(data["entry_id"], "entry_id"); _str(data["protocol_id"], "protocol_id"); _str(data["hypothesis_id"], "hypothesis_id"); _str(data["dataset_region_id"], "dataset_region_id")
    _sha(data["source_control_receipt_sha256"], "source_control_receipt_sha256")
    for key in ("region_start_utc", "region_end_utc", "recorded_at_utc"):
        try: datetime.fromisoformat(_str(data[key], key).replace("Z", "+00:00"))
        except ValueError: _fail(f"{key}: UTC timestamp required")
    if data["region_start_utc"] >= data["region_end_utc"]:
        _fail("region boundaries must be increasing")
    if data["disclosure_kind"] not in {"DESIGNATED_DEVELOPMENT", "DESIGNATED_VALIDATION", "DESIGNATED_HOLDOUT", "VALIDATION_STATISTIC_EXPOSED", "HOLDOUT_UNSEALED", "HOLDOUT_STATISTIC_EXPOSED", "REGION_GLOBALLY_CONSUMED", "DESCRIPTIVE_REUSE_ONLY"}:
        _fail("unknown disclosure kind")
    _walk_forbidden(data)
    return data

def validate_holdout_disclosure_ledger(value: object) -> dict:
    data = _base(value, "qnty_global_real_protocol_holdout_disclosure_ledger", "global-real-protocol-holdout-disclosure-ledger-v001", "SCHEMA_IMPLEMENTED_EMPTY_NO_BACKFILL", {"document_id", "document_kind", "entries", "status", "schema_version"})
    entries = _list(data["entries"], "entries")
    seen = set()
    for entry in entries:
        item = _entry(entry)
        if item["entry_id"] in seen: _fail("duplicate entry ID")
        seen.add(item["entry_id"])
    return data

def validate_ledger_append(previous: object, candidate: object) -> dict:
    before = validate_holdout_disclosure_ledger(previous); after = validate_holdout_disclosure_ledger(candidate)
    old = before["entries"]; new = after["entries"]
    if len(new) < len(old) or new[:len(old)] != old or len({item["entry_id"] for item in new}) != len(new):
        _fail("ledger append must preserve previous entries byte-semantically and in order")
    return after

def validate_failure_domain_evidence_schema(value: object) -> dict:
    keys = {"document_id", "document_kind", "field_definitions", "qualification_enum", "status", "schema_version"}
    data = _base(value, "qnty_durable_store_failure_domain_evidence_schema", "durable-store-failure-domain-evidence-schema-v001", "METADATA_SCHEMA_ONLY_NO_STORE_ACCESS", keys)
    if data["qualification_enum"] != ["UNASSESSED", "INSUFFICIENT", "CANDIDATE_METADATA_COMPLETE", "INDEPENDENT_REVIEW_REQUIRED", "QUALIFIED_BY_LATER_GOVERNANCE", "REJECTED"] or data["field_definitions"] != ["administrative_failure_domain_id", "credential_failure_domain_id", "deletion_propagation_domain_id", "evidence_document_hashes", "evidence_record_id", "geographic_failure_domain_id", "physical_failure_domain_id", "qualification_status", "restore_operator_domain_id", "review_status", "store_id", "backend_kind"]:
        _fail("failure-domain schema drifted")
    return data

def validate_review_packet_schema(value: object) -> dict:
    keys = {"document_id", "document_kind", "field_definitions", "forbidden_content", "status", "schema_version"}
    data = _base(value, "qnty_replayable_review_evidence_packet_schema", "replayable-review-evidence-packet-schema-v001", "SCHEMA_ONLY_NO_REVIEW_PACKET_CREATED", keys)
    if data["field_definitions"] != ["commands", "environment_identity", "finding_counts", "harness_source_hashes", "redaction_manifest", "review_id", "review_kind", "review_specification_hash", "reviewed_artifact_hashes", "reviewed_commit_sha", "stderr_artifact_hashes", "stdout_artifact_hashes", "verdict"]:
        _fail("review packet schema drifted")
    if data["forbidden_content"] != ["API tokens", "chain-of-thought", "credentials", "environment secret values", "holdout bytes", "private keys", "real dataset bytes", "scientific edge claims", "session cookies", "unredacted secret-bearing command output"]:
        _fail("review packet forbidden content drifted")
    return data

def validate_synthetic_canary_scaffold(value: object) -> dict:
    keys = {"document_id", "document_kind", "payloads", "status", "schema_version"}
    data = _base(value, "qnty_synthetic_artifact_canary_scaffold", "synthetic-artifact-canary-scaffold-v001", "SCAFFOLD_ONLY_NOT_EXECUTED", keys)
    if data["payloads"] != [{"content": "QNTY_SYNTHETIC_CANARY_ALPHA_V1", "relative_path": "alpha/payload.txt", "role": "synthetic-alpha", "sha256": hashlib.sha256(b"QNTY_SYNTHETIC_CANARY_ALPHA_V1").hexdigest(), "size": 30}, {"content_hex": "00514e5459ff", "relative_path": "beta/payload.bin", "role": "synthetic-beta", "sha256": hashlib.sha256(bytes.fromhex("00514e5459ff")).hexdigest(), "size": 6}]:
        _fail("canary descriptor drifted")
    return data

def build_synthetic_canary_payloads() -> dict[str, bytes]:
    return {"alpha/payload.txt": b"QNTY_SYNTHETIC_CANARY_ALPHA_V1", "beta/payload.bin": bytes.fromhex("00514e5459ff")}

def load_and_validate_assurance_scaffold(value: object, validator) -> dict:
    if type(value) not in (bytes, bytearray): _fail("canonical JSON bytes required")
    parsed = json.loads(bytes(value).decode("utf-8"))
    if canonical_json_bytes(parsed) != bytes(value): _fail("non-canonical JSON bytes")
    return validator(parsed)
