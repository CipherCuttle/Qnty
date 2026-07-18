import ast
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from quantbot.assurance import contracts

ROOT = Path(__file__).parents[2]
DOCS = ROOT / "docs/assurance"
REVIEWS = DOCS / "reviews"
TEMPORAL_REREVIEW = REVIEWS / "h001_temporal_causality_amendment_candidate_rereview_record_v001.json"
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
    entry = {"dataset_region_id":"region-a","disclosure_kind":"DESIGNATED_DEVELOPMENT","disclosure_status":"RECORDED_APPEND_ONLY","entry_id":"entry-a","hypothesis_id":"h001","protocol_id":"protocol","recorded_at_utc":"2026-01-01T00:00:00Z","region_end_utc":"2026-01-02T00:00:00Z","region_start_utc":"2026-01-01T00:00:00Z","source_control_receipt_path":"docs/control/receipt.json","source_control_receipt_sha256":"a" * 64}
    candidate = dict(empty, entries=[entry], status="APPEND_ONLY_METADATA_DISCLOSURES")
    contracts.validate_ledger_append(contracts.canonical_json_bytes(empty), contracts.canonical_json_bytes(candidate))
    with pytest.raises(ValueError): contracts.validate_ledger_append(contracts.canonical_json_bytes(candidate), contracts.canonical_json_bytes(empty))
    bad = dict(candidate, entries=[dict(entry, returns=1)])
    with pytest.raises(ValueError): contracts.validate_holdout_disclosure_ledger(bad)

def test_ledger_append_requires_canonical_bytes_and_preserves_canonical_prefix():
    empty = json.loads(read("global_real_protocol_holdout_disclosure_ledger_v001.json"))
    entry = {"dataset_region_id":"region-a","disclosure_kind":"DESIGNATED_DEVELOPMENT","disclosure_status":"RECORDED_APPEND_ONLY","entry_id":"entry-a","hypothesis_id":"h001","protocol_id":"protocol","recorded_at_utc":"2026-01-01T00:00:00Z","region_end_utc":"2026-01-02T00:00:00Z","region_start_utc":"2026-01-01T00:00:00Z","source_control_receipt_path":"docs/control/tasks/example/handoff_v001.json","source_control_receipt_sha256":"a" * 64}
    candidate = dict(empty, entries=[entry], status="APPEND_ONLY_METADATA_DISCLOSURES")
    with pytest.raises(ValueError, match="canonical JSON bytes"):
        contracts.validate_ledger_append(empty, candidate)
    noncanonical = json.dumps(candidate).encode()
    with pytest.raises(ValueError, match="non-canonical"):
        contracts.validate_ledger_append(contracts.canonical_json_bytes(empty), noncanonical)
    first = contracts.canonical_json_bytes(candidate)
    second_entry = dict(entry, entry_id="entry-b", dataset_region_id="region-b", recorded_at_utc="2026-01-01T01:00:00Z")
    second = dict(candidate, entries=[entry, second_entry])
    contracts.validate_ledger_append(first, contracts.canonical_json_bytes(second))
    for mutated in (
        dict(candidate, entries=[]),
        dict(candidate, entries=[dict(entry, recorded_at_utc="2026-01-01T00:00:01Z")]),
        dict(candidate, entries=[dict(entry, entry_id="entry-b")]),
    ):
        with pytest.raises(ValueError):
            contracts.validate_ledger_append(first, contracts.canonical_json_bytes(mutated))
    reordered = dict(candidate, entries=[dict(reversed(list(entry.items())))])
    contracts.validate_ledger_append(first, contracts.canonical_json_bytes(reordered))
    duplicate_semantic = dict(entry, entry_id="entry-b")
    with pytest.raises(ValueError, match="semantic"):
        contracts.validate_holdout_disclosure_ledger(dict(candidate, entries=[entry, duplicate_semantic]))
    regressed = dict(candidate, entries=[entry, dict(second_entry, recorded_at_utc="2025-12-31T23:00:00Z")])
    with pytest.raises(ValueError, match="ordered"):
        contracts.validate_holdout_disclosure_ledger(regressed)

@pytest.mark.parametrize("timestamp", [
    "2026-01-01T00:00:00", "2026-01-01", "2026-01-01T02:00:00+02:00",
    "2025-12-31T19:00:00-05:00", "2026-01-01T00:00:00+00:00", "2026-01-01t00:00:00z",
    "2026-01-01T00:00Z", "2026-01-01T00:00:00.000Z", "2026-02-30T00:00:00Z", True, 1, None,
])
def test_ledger_rejects_noncanonical_timestamps(timestamp):
    empty = json.loads(read("global_real_protocol_holdout_disclosure_ledger_v001.json"))
    entry = {"dataset_region_id":"region-a","disclosure_kind":"DESIGNATED_DEVELOPMENT","disclosure_status":"RECORDED_APPEND_ONLY","entry_id":"entry-a","hypothesis_id":"h001","protocol_id":"protocol","recorded_at_utc":"2026-01-01T00:00:00Z","region_end_utc":"2026-01-02T00:00:00Z","region_start_utc":"2026-01-01T00:00:00Z","source_control_receipt_path":"docs/control/receipt.json","source_control_receipt_sha256":"a" * 64}
    with pytest.raises(ValueError):
        contracts.validate_holdout_disclosure_ledger(dict(empty, status="APPEND_ONLY_METADATA_DISCLOSURES", entries=[dict(entry, recorded_at_utc=timestamp)]))

def test_ledger_rejects_chronologically_reversed_region_even_when_strings_sort():
    empty = json.loads(read("global_real_protocol_holdout_disclosure_ledger_v001.json"))
    entry = {"dataset_region_id":"region-a","disclosure_kind":"DESIGNATED_DEVELOPMENT","disclosure_status":"RECORDED_APPEND_ONLY","entry_id":"entry-a","hypothesis_id":"h001","protocol_id":"protocol","recorded_at_utc":"2026-01-01T00:00:00Z","region_end_utc":"2026-01-01T01:00:00+01:00","region_start_utc":"2026-01-01T00:30:00+00:00","source_control_receipt_path":"docs/control/receipt.json","source_control_receipt_sha256":"a" * 64}
    with pytest.raises(ValueError):
        contracts.validate_holdout_disclosure_ledger(dict(empty, status="APPEND_ONLY_METADATA_DISCLOSURES", entries=[entry]))

@pytest.mark.parametrize("status", ["SEALED", "UNSEALED", "EXPOSED", True, 1, None])
def test_ledger_rejects_invalid_disclosure_status(status):
    empty = json.loads(read("global_real_protocol_holdout_disclosure_ledger_v001.json"))
    entry = {"dataset_region_id":"region-a","disclosure_kind":"DESIGNATED_DEVELOPMENT","disclosure_status":status,"entry_id":"entry-a","hypothesis_id":"h001","protocol_id":"protocol","recorded_at_utc":"2026-01-01T00:00:00Z","region_end_utc":"2026-01-02T00:00:00Z","region_start_utc":"2026-01-01T00:00:00Z","source_control_receipt_path":"docs/control/receipt.json","source_control_receipt_sha256":"a" * 64}
    with pytest.raises(ValueError):
        contracts.validate_holdout_disclosure_ledger(dict(empty, status="APPEND_ONLY_METADATA_DISCLOSURES", entries=[entry]))

@pytest.mark.parametrize("path", ["../../receipt.json", "docs/control/../secret.json", "/etc/passwd", "C:\\secret.json", "\\\\server\\share\\receipt.json", "file://receipt.json", "s3://bucket/receipt.json", "gs://bucket/receipt.json", "ssh://host/receipt.json", "qnty-artifact://receipt", "https://example.com/receipt.json", "docs/artifacts/receipt.json", "receipt.json", "", True, 1, None])
def test_ledger_rejects_unsafe_receipt_paths(path):
    empty = json.loads(read("global_real_protocol_holdout_disclosure_ledger_v001.json"))
    entry = {"dataset_region_id":"region-a","disclosure_kind":"DESIGNATED_DEVELOPMENT","disclosure_status":"RECORDED_APPEND_ONLY","entry_id":"entry-a","hypothesis_id":"h001","protocol_id":"protocol","recorded_at_utc":"2026-01-01T00:00:00Z","region_end_utc":"2026-01-02T00:00:00Z","region_start_utc":"2026-01-01T00:00:00Z","source_control_receipt_path":path,"source_control_receipt_sha256":"a" * 64}
    with pytest.raises(ValueError):
        contracts.validate_holdout_disclosure_ledger(dict(empty, status="APPEND_ONLY_METADATA_DISCLOSURES", entries=[entry]))

def test_ledger_status_matches_entry_state():
    empty = json.loads(read("global_real_protocol_holdout_disclosure_ledger_v001.json"))
    entry = {"dataset_region_id":"region-a","disclosure_kind":"DESIGNATED_DEVELOPMENT","disclosure_status":"RECORDED_APPEND_ONLY","entry_id":"entry-a","hypothesis_id":"h001","protocol_id":"protocol","recorded_at_utc":"2026-01-01T00:00:00Z","region_end_utc":"2026-01-02T00:00:00Z","region_start_utc":"2026-01-01T00:00:00Z","source_control_receipt_path":"docs/control/receipt.json","source_control_receipt_sha256":"a" * 64}
    with pytest.raises(ValueError): contracts.validate_holdout_disclosure_ledger(dict(empty, entries=[entry]))
    with pytest.raises(ValueError): contracts.validate_holdout_disclosure_ledger(dict(empty, status="APPEND_ONLY_METADATA_DISCLOSURES"))
    contracts.validate_holdout_disclosure_ledger(dict(empty, status="APPEND_ONLY_METADATA_DISCLOSURES", entries=[entry]))

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
                assert node.module.split(".")[0] in {"__future__", "dataclasses", "datetime", "hashlib", "json", "re", "typing", "contracts"}


def test_h001_review_records_are_canonical_and_validate():
    for name, validator in (
        ("h001_pre_data_assurance_scaffold_rereview_protocol_v001.json", contracts.validate_review_protocol_record),
        ("h001_pre_data_assurance_scaffold_rereview_packet_v001.json", contracts.validate_review_evidence_packet),
    ):
        raw = (REVIEWS / name).read_bytes()
        assert contracts.load_and_validate_assurance_scaffold(raw, validator)
        assert contracts.canonical_json_bytes(json.loads(raw)) == raw
        assert not raw.endswith(b"\n")


@pytest.mark.parametrize("mutation", [
    lambda value: value.update(status="PREREGISTERED_BEFORE_REVIEW"),
    lambda value: value.update(review_requirements=["x"]),
    lambda value: value.update(merged_main_commit_sha="0" * 40),
])
def test_h001_review_protocol_is_not_retroactively_preregistered(tmp_path, mutation):
    del tmp_path
    value = json.loads((REVIEWS / "h001_pre_data_assurance_scaffold_rereview_protocol_v001.json").read_bytes())
    mutation(value)
    with pytest.raises(ValueError):
        contracts.validate_review_protocol_record(value)


@pytest.mark.parametrize("field", ["reviewed_commit_sha", "verdict", "review_specification_hash", "stdout_artifact_hashes", "stderr_artifact_hashes"])
def test_h001_review_packet_rejects_drift(field):
    value = json.loads((REVIEWS / "h001_pre_data_assurance_scaffold_rereview_packet_v001.json").read_bytes())
    value[field] = "wrong" if field not in {"stdout_artifact_hashes", "stderr_artifact_hashes"} else ["a" * 64]
    with pytest.raises(ValueError):
        contracts.validate_review_evidence_packet(value)


@pytest.mark.parametrize("field", ["token", "real_data", "private_reasoning", "scientific_claim"])
def test_h001_review_packet_rejects_forbidden_fields(field):
    value = json.loads((REVIEWS / "h001_pre_data_assurance_scaffold_rereview_packet_v001.json").read_bytes())
    value[field] = False
    with pytest.raises(ValueError):
        contracts.validate_review_evidence_packet(value)


def test_h001_review_packet_commands_are_executable_replay_records():
    packet = json.loads((REVIEWS / "h001_pre_data_assurance_scaffold_rereview_packet_v001.json").read_bytes())
    commands = packet["commands"]
    joined = " ".join(commands)
    assert "--no-git-export" not in joined
    assert "remote CI checks" not in joined
    assert len(commands) == len(set(commands))
    # The recorded recipe is byte-identical to the independently pinned contract.
    assert commands == contracts._REVIEW_COMMANDS
    # MAJOR replayability fix: the recipe binds the actual PR #282 base, never the
    # later merged-main commit (using merged-main breaks merge-base and 16-file scope).
    assert any("BASE=28d6c70e9d7cb11c55d1afdf8b4e5ad9754f7aba" in command for command in commands)
    assert all("ae61c6162f3164e0b24dd567a6ef73bdb5ecf8ea" not in command for command in commands)
    # Detached-worktree setup and exported-tree cwd are recorded explicitly, and the
    # scope check is an exact 16-file comparison rather than a count alone.
    for marker in (
        "$HEAD", "$BASE", "git merge-base", "worktree add --detach", "cd $REVIEW_DIR", "cd $EXPORT",
        "git diff --name-only", "diff -u", "-eq 16", "sha256sum", "git archive", "! -e $EXPORT/.git",
        "PYTHONPATH=$EXPORT", "gh run list", "git status --short",
    ):
        assert any(marker in command for command in commands)
    # No command string is an absolute path, store URI, or network URL.
    assert all(not command.startswith(("/", "http://", "https://", "qnty-artifact://")) for command in commands)


def test_h001_temporal_candidate_rereview_record_is_canonical_and_strict():
    raw = TEMPORAL_REREVIEW.read_bytes()
    value = contracts.validate_h001_temporal_candidate_rereview_record(raw)
    assert value["final_verdict"] == "QNTY_H001_TEMPORAL_CAUSALITY_AMENDMENT_CANDIDATE_REREVIEW_PASSED"
    assert value["recorded_after_review"] is True
    assert value["preregistered"] is False
    assert not raw.endswith(b"\n")


def test_h001_temporal_candidate_rereview_scope_matches_historical_git_delta():
    value = json.loads(TEMPORAL_REREVIEW.read_bytes())
    expected = [
        "docs/control/active_task.json",
        "docs/control/amendments/candidate1_h001_temporal_causality_v001.json",
        "docs/control/tasks/RECOVER_OR_RETIRE_CANDIDATE1_V0_FROZEN_INPUT/handoff_v016.json",
        "quantbot/continuity/context.py", "quantbot/experiment/h001_temporal_causality.py",
        "tests/continuity/test_cross_agent_continuity.py", "tests/experiment/test_h001_temporal_causality.py",
    ]
    actual = subprocess.run(
        ["git", "diff", "--name-only", "9981a466d847305570f7e23826f0c9f40a7446a9", "74554e15f92cdb7f6c22238766bd6e1f16b60bf4"],
        check=True, capture_output=True, text=True,
    ).stdout.splitlines()
    assert actual == expected
    assert value["repair_scope"] == expected
    assert "docs/experiments/candidate1_h001_real_data_falsification_temporal_candidate_v001.json" not in value["repair_scope"]
    assert not set(value["repair_scope"]) & {str(TEMPORAL_REREVIEW), "docs/control/tasks/RECOVER_OR_RETIRE_CANDIDATE1_V0_FROZEN_INPUT/handoff_v017.json", "quantbot/assurance/contracts.py", "tests/assurance/test_contracts.py"}


@pytest.mark.parametrize("mutation", [
    lambda v: v.update(repair_scope=v["repair_scope"] + ["extra.py"]),
    lambda v: v.update(repair_scope=v["repair_scope"][:-1]),
    lambda v: v.update(repair_scope=v["repair_scope"] + [v["repair_scope"][0]]),
    lambda v: v["repair_scope"].__setitem__(0, "substituted.py"),
    lambda v: v["repair_scope"].__setitem__(0, "docs/assurance/reviews/h001_temporal_causality_amendment_candidate_rereview_record_v001.json"),
])
def test_h001_temporal_candidate_rereview_rejects_repair_scope_mutations(mutation):
    value = json.loads(TEMPORAL_REREVIEW.read_bytes())
    mutation(value)
    with pytest.raises(ValueError):
        contracts.validate_h001_temporal_candidate_rereview_record(contracts.canonical_json_bytes(value))


def test_h001_temporal_candidate_rereview_verified_export_command_is_honest():
    handoff = json.loads((ROOT / "docs/control/tasks/RECOVER_OR_RETIRE_CANDIDATE1_V0_FROZEN_INPUT/handoff_v017.json").read_bytes())
    commands = handoff["verified_commands"]
    assert 'PYTHONPATH="$EXPORT" "$PY" -m pytest tests/assurance tests/continuity -q' in commands
    assert not any("test_h001_temporal_causality.py tests/continuity" in command for command in commands)


@pytest.mark.parametrize("raw", [bytearray(TEMPORAL_REREVIEW.read_bytes()), memoryview(TEMPORAL_REREVIEW.read_bytes()), TEMPORAL_REREVIEW.read_text(), TEMPORAL_REREVIEW, object()])
def test_h001_temporal_candidate_rereview_requires_exact_bytes(raw):
    with pytest.raises(ValueError, match="exact bytes input"):
        contracts.validate_h001_temporal_candidate_rereview_record(raw)


@pytest.mark.parametrize("mutation", [
    lambda v: v.update(review_bindings=dict(v["review_bindings"], pr_number=285)),
    lambda v: v.update(final_verdict="QNTY_H001_TEMPORAL_CAUSALITY_AMENDMENT_CANDIDATE_REVIEW_FAILED"),
    lambda v: v.update(preregistered=True),
    lambda v: v.update(final_finding_counts={"blocker": 0, "major": 1, "minor": 0}),
    lambda v: v.update(non_effects=["EDGE_PROVEN"]),
    lambda v: v.update(repair_scope=v["repair_scope"] + ["unexpected.py"]),
    lambda v: v["artifact_bindings"].__setitem__(0, dict(v["artifact_bindings"][0], sha256="0" * 64)),
])
def test_h001_temporal_candidate_rereview_record_rejects_mutations(mutation):
    value = json.loads(TEMPORAL_REREVIEW.read_bytes())
    mutation(value)
    with pytest.raises(ValueError):
        contracts.validate_h001_temporal_candidate_rereview_record(contracts.canonical_json_bytes(value))


def test_h001_temporal_candidate_rereview_record_rejects_duplicate_or_noncanonical_bytes():
    raw = TEMPORAL_REREVIEW.read_bytes()
    duplicate = raw[:-1] + b',"status":"RECORDED_AFTER_REVIEW_NOT_PREREGISTERED"}'
    with pytest.raises(ValueError):
        contracts.validate_h001_temporal_candidate_rereview_record(duplicate)
    with pytest.raises(ValueError):
        contracts.validate_h001_temporal_candidate_rereview_record(json.dumps(json.loads(raw)).encode())
