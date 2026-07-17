import ast
import hashlib
import json
from pathlib import Path

import pytest

from quantbot.assurance import contracts

ROOT = Path(__file__).parents[2]
DOCS = ROOT / "docs/assurance"
VALIDATORS = {
    "h001_temporal_causality_amendment_draft_v001.json": contracts.validate_temporal_amendment_draft,
    "h001_synthetic_null_calibration_spec_draft_v001.json": contracts.validate_calibration_spec_draft,
    "global_real_protocol_holdout_disclosure_ledger_v001.json": contracts.validate_holdout_disclosure_ledger,
    "durable_store_failure_domain_evidence_schema_v001.json": contracts.validate_failure_domain_evidence_schema,
    "replayable_review_evidence_packet_schema_v001.json": contracts.validate_review_packet_schema,
    "synthetic_artifact_canary_scaffold_v001.json": contracts.validate_synthetic_canary_scaffold,
}

def read(name):
    return (DOCS / name).read_bytes()

def test_committed_documents_are_canonical_and_validate():
    for name, validator in VALIDATORS.items():
        raw = read(name)
        parsed = contracts.load_and_validate_assurance_scaffold(raw, validator)
        assert contracts.canonical_json_bytes(parsed) == raw
        assert not raw.endswith(b"\n")

@pytest.mark.parametrize("name", list(VALIDATORS))
def test_unknown_missing_and_noncanonical_documents_fail(name):
    parsed = json.loads(read(name))
    validator = VALIDATORS[name]
    parsed["unknown"] = True
    with pytest.raises(ValueError): validator(parsed)
    parsed = json.loads(read(name)); parsed.pop(next(iter(parsed)))
    with pytest.raises(ValueError): validator(parsed)
    with pytest.raises(ValueError): contracts.load_and_validate_assurance_scaffold(read(name) + b"\n", validator)

def test_temporal_draft_cannot_become_effective_or_applied():
    data = json.loads(read("h001_temporal_causality_amendment_draft_v001.json"))
    data["status"] = "EFFECTIVE"
    with pytest.raises(ValueError): contracts.validate_temporal_amendment_draft(data)
    data = json.loads(read("h001_temporal_causality_amendment_draft_v001.json")); data["non_effects"].remove("PROPOSED_RULE_NOT_APPLIED")
    with pytest.raises(ValueError): contracts.validate_temporal_amendment_draft(data)

def test_calibration_draft_rejects_tuning_and_unknown_dgp():
    data = json.loads(read("h001_synthetic_null_calibration_spec_draft_v001.json"))
    data["proposed_design"]["stationary_block_length"] = 64
    with pytest.raises(ValueError): contracts.validate_calibration_spec_draft(data)
    data = json.loads(read("h001_synthetic_null_calibration_spec_draft_v001.json")); data["proposed_dgp_suite"].append("real BTC")
    with pytest.raises(ValueError): contracts.validate_calibration_spec_draft(data)

def test_ledger_is_empty_and_append_only():
    empty = json.loads(read("global_real_protocol_holdout_disclosure_ledger_v001.json"))
    assert empty["entries"] == []
    entry = {"dataset_region_id":"region-a","disclosure_kind":"DESIGNATED_DEVELOPMENT","disclosure_status":"SEALED","entry_id":"entry-a","hypothesis_id":"h001","protocol_id":"protocol","recorded_at_utc":"2026-01-01T00:00:00Z","region_end_utc":"2026-01-02T00:00:00Z","region_start_utc":"2026-01-01T00:00:00Z","source_control_receipt_path":"docs/control/receipt.json","source_control_receipt_sha256":"a" * 64}
    candidate = dict(empty, entries=[entry])
    contracts.validate_ledger_append(empty, candidate)
    with pytest.raises(ValueError): contracts.validate_ledger_append(candidate, empty)
    bad = dict(candidate, entries=[dict(entry, returns=1)])
    with pytest.raises(ValueError): contracts.validate_holdout_disclosure_ledger(bad)

def test_failure_and_review_schemas_reject_secrets_and_claims():
    failure = json.loads(read("durable_store_failure_domain_evidence_schema_v001.json"))
    failure["field_definitions"].append("absolute_path")
    with pytest.raises(ValueError): contracts.validate_failure_domain_evidence_schema(failure)
    review = json.loads(read("replayable_review_evidence_packet_schema_v001.json")); review["field_definitions"].append("token")
    with pytest.raises(ValueError): contracts.validate_review_packet_schema(review)

def test_import_boundary_is_standard_library_only():
    for path in (ROOT / "quantbot/assurance").glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(alias.name.split(".")[0] in {"dataclasses", "datetime", "hashlib", "json", "re"} for alias in node.names)
            if isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] in {"__future__", "dataclasses", "datetime", "hashlib", "json", "re", "contracts"}
