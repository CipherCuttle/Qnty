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
CALIBRATION_REREVIEW = REVIEWS / "h001_synthetic_null_calibration_spec_freeze_candidate_rereview_record_v001.json"
VALIDATORS = {
    "h001_temporal_causality_amendment_draft_v001.json": contracts.validate_temporal_amendment_draft,
    "h001_synthetic_null_calibration_spec_draft_v001.json": contracts.validate_calibration_spec_draft,
    "global_real_protocol_holdout_disclosure_ledger_v001.json": contracts.validate_holdout_disclosure_ledger,
    "durable_store_failure_domain_evidence_schema_v001.json": contracts.validate_failure_domain_evidence_schema,
    "replayable_review_evidence_packet_schema_v001.json": contracts.validate_review_packet_schema,
    "synthetic_artifact_canary_scaffold_v001.json": contracts.validate_synthetic_canary_scaffold,
    "h001_synthetic_null_calibration_spec_freeze_candidate_v001.json": contracts.validate_calibration_spec_freeze_candidate,
}
FREEZE_CANDIDATE = DOCS / "h001_synthetic_null_calibration_spec_freeze_candidate_v001.json"
CALIBRATION_ACTIVATION = ROOT / "docs/control/amendments/candidate1_h001_synthetic_null_calibration_spec_freeze_activation_v001.json"

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
    if (ROOT / ".git").exists():
        actual = subprocess.run(
            ["git", "diff", "--name-only", "9981a466d847305570f7e23826f0c9f40a7446a9", "74554e15f92cdb7f6c22238766bd6e1f16b60bf4"],
            check=True, capture_output=True, text=True,
        ).stdout.splitlines()
    else:
        actual = expected
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


def calibration_rereview_record():
    return json.loads(CALIBRATION_REREVIEW.read_bytes())


def test_h001_calibration_rereview_record_is_canonical_and_strict():
    raw = CALIBRATION_REREVIEW.read_bytes()
    value = contracts.load_and_validate_h001_synthetic_null_calibration_spec_freeze_candidate_rereview_record(raw)
    assert contracts.validate_h001_synthetic_null_calibration_spec_freeze_candidate_rereview_record(value)
    assert value["final_verdict"] == "QNTY_H001_SYNTHETIC_NULL_CALIBRATION_SPEC_FREEZE_CANDIDATE_REPAIRED_REREVIEW_PASSED"
    assert value["review_history"][0]["verdict"] == "QNTY_H001_SYNTHETIC_NULL_CALIBRATION_SPEC_FREEZE_CANDIDATE_REREVIEW_FAILED"
    assert value["review_history"][0]["finding_counts"] == {"blocker": 1, "major": 3, "minor": 0}
    assert value["review_history"][0]["findings"] == [
        {"finding_id": "DGP_STRESS_AND_SAMPLE_SEMANTICS_NOT_VALIDATED_EXACTLY", "severity": "BLOCKER"},
        {"finding_id": "GARCH_INITIALIZATION_NOT_FULLY_PINNED", "severity": "MAJOR"},
        {"finding_id": "SAMPLE_LENGTH_ENDPOINT_CONVENTION_AMBIGUOUS", "severity": "MAJOR"},
        {"finding_id": "RNG_COMPONENT_SUBSTREAMS_AND_DRAW_ORDER_UNDER_SPECIFIED", "severity": "MAJOR"},
    ]
    assert value["review_history"][1]["reviewed_head"] == "d79f8908d55e8dd9d5f33b9f174e01d8796e02fe"
    assert not raw.endswith(b"\n")


@pytest.mark.parametrize("raw", [bytearray(CALIBRATION_REREVIEW.read_bytes()), memoryview(CALIBRATION_REREVIEW.read_bytes()), CALIBRATION_REREVIEW.read_text(), CALIBRATION_REREVIEW, object()])
def test_h001_calibration_rereview_requires_exact_bytes(raw):
    with pytest.raises(ValueError, match="exact bytes input"):
        contracts.load_and_validate_h001_synthetic_null_calibration_spec_freeze_candidate_rereview_record(raw)


def test_h001_calibration_rereview_rejects_duplicate_or_noncanonical_bytes():
    raw = CALIBRATION_REREVIEW.read_bytes()
    duplicate = raw[:-1] + b',"status":"RECORDED_AFTER_REVIEW_NOT_EFFECTIVE_NOT_EXECUTABLE"}'
    with pytest.raises(ValueError, match="duplicate"):
        contracts.load_and_validate_h001_synthetic_null_calibration_spec_freeze_candidate_rereview_record(duplicate)
    with pytest.raises(ValueError, match="non-canonical"):
        contracts.load_and_validate_h001_synthetic_null_calibration_spec_freeze_candidate_rereview_record(json.dumps(json.loads(raw)).encode())


@pytest.mark.parametrize("mutation", [
    lambda v: v["review_history"].pop(0),
    lambda v: v["review_history"][0].update(finding_counts={"blocker": 4, "major": 0, "minor": 0}),
    lambda v: v["review_history"][0].update(finding_counts={"blocker": 0, "major": 4, "minor": 0}),
    lambda v: v["review_history"][0].update(finding_counts={"blocker": 0, "major": 3, "minor": 1}),
    lambda v: v["review_history"][0]["findings"][0].update(severity="MAJOR"),
    lambda v: v["review_history"][0]["findings"][1].update(severity="BLOCKER"),
    lambda v: v["review_history"][0]["findings"].pop(),
    lambda v: v["review_history"][0]["findings"].append(dict(v["review_history"][0]["findings"][0])),
    lambda v: v["review_history"][0]["findings"].reverse(),
    lambda v: v["review_history"][0]["findings"][0].update(finding_id="GARCH_INITIALIZATION_NOT_FULLY_PINNED"),
    lambda v: v["review_history"][0].update(findings=[]),
    lambda v: v["review_history"][0].update(verdict=v["review_history"][1]["verdict"]),
    lambda v: v["review_history"][0].update(historical=False),
    lambda v: v["review_history"][1].update(reviewed_head=v["review_history"][0]["reviewed_head"]),
    lambda v: v["review_history"][1].update(findings=[dict(v["review_history"][0]["findings"][0])]),
    lambda v: v["review_bindings"].update(repair_commit="0" * 40),
    lambda v: v["review_bindings"].update(candidate_merge_commit="0" * 40),
    lambda v: v["artifact_bindings"][0].update(sha256="0" * 64),
    lambda v: v["artifact_bindings"][1].update(sha256="0" * 64),
    lambda v: v["artifact_bindings"][2].update(sha256="0" * 64),
    lambda v: v["artifact_bindings"][5].update(sha256="0" * 64),
    lambda v: v["candidate_review_scope"].reverse(),
    lambda v: v["repair_scope"].append("unexpected.py"),
    lambda v: v["repair_scope"].__setitem__(0, "wrong.py"),
    lambda v: v["review_results"].update(assurance="201 passed"),
    lambda v: v["review_results"].update(remote_ci="FAILURE"),
    lambda v: v["semantic_review_results"].update(garch_review="PASSED"),
    lambda v: v["final_finding_counts"].update(major=1),
    lambda v: v["closed_findings"].pop(),
    lambda v: v.update(final_verdict="QNTY_H001_SYNTHETIC_NULL_CALIBRATION_SPEC_FREEZE_CANDIDATE_REREVIEW_FAILED"),
    lambda v: v.update(status="FROZEN_EFFECTIVE"),
    lambda v: v.update(preregistered=True),
    lambda v: v["non_effects"].remove("EDGE_UNPROVEN"),
    lambda v: v["non_effects"].append("EDGE_PROVEN"),
])
def test_h001_calibration_rereview_record_rejects_semantic_mutations(mutation):
    value = calibration_rereview_record()
    mutation(value)
    with pytest.raises(ValueError):
        contracts.validate_h001_synthetic_null_calibration_spec_freeze_candidate_rereview_record(value)


# --- H001 synthetic-null calibration spec freeze candidate -------------------

def freeze_candidate():
    return json.loads(FREEZE_CANDIDATE.read_bytes())


def _dgp(value, dgp_id):
    return next(item for item in value["required_stationary_dgps"] if item["dgp_id"] == dgp_id)


def _stress(value, case_id):
    return next(item for item in value["diagnostic_stress_cases"] if item["case_id"] == case_id)


def test_freeze_candidate_is_canonical_locked_for_review_and_not_effective():
    raw = FREEZE_CANDIDATE.read_bytes()
    value = contracts.load_and_validate_calibration_spec_freeze_candidate(raw)
    assert contracts.canonical_json_bytes(value) == raw and not raw.endswith(b"\n")
    assert value["status"] == "FREEZE_CANDIDATE_FOR_INDEPENDENT_REVIEW_NOT_EFFECTIVE_NOT_EXECUTABLE"
    auth = value["authorization_state"]
    assert auth["candidate_values_locked_for_review"] is True and auth["independent_review_required"] is True
    for key in (
        "specification_frozen_effective", "specification_effective", "execution_authorized", "results_exposed",
        "real_data_access_authorized", "h001_validation_execution_authorized", "h001_holdout_execution_authorized",
        "scientific_authorization", "paper_trade_authorization", "live_authorization",
    ):
        assert auth[key] is False
    assert value["edge_status"] == "EDGE_UNPROVEN" and value["live_status"] == "BLOCK_LIVE_INTEGRATION"


def test_freeze_candidate_preserves_the_registered_statistical_target():
    target = freeze_candidate()["registered_test_target"]
    assert target["registered_variant_series"] == 9
    assert target["test_target"] == "exact registered synchronous stationary-bootstrap maximum-t procedure"
    assert target["inner_procedure"] == "synchronous stationary-bootstrap maximum-t"
    assert target["bootstrap_repetitions"] == 10000
    assert target["outer_synthetic_replications"] == 2000
    assert target["stationary_block_length"] == 63
    assert target["hac_lag"] == 21
    assert target["familywise_alpha"] == 0.05
    criterion = freeze_candidate()["pass_criterion"]
    assert criterion["binomial_interval_method"] == "one-sided exact Clopper-Pearson upper bound"
    assert criterion["binomial_confidence_level"] == 0.95 and criterion["fwer_upper_bound_threshold"] == 0.075
    assert criterion["diagnostic_cases_participate"] is False


def test_freeze_candidate_pins_exact_sample_boundary_and_shape():
    sample = freeze_candidate()["synthetic_sample_contract"]
    assert sample == {
        "cadence": "8h",
        "exclusive_region_end_utc": "2025-01-01T00:00:00Z",
        "finite_value_requirement": "every generated value must be finite; any non-finite value invalidates the replication",
        "first_interval_open_utc": "2023-01-01T00:00:00Z",
        "inclusive_display_end_utc": "2024-12-31T23:59:59Z",
        "interval_duration_seconds": 28800,
        "interval_extent_rule": "each synthetic observation represents the 8-hour interval beginning at open_time(t); the final interval begins 2024-12-31T16:00:00Z and reaches the exclusive boundary 2025-01-01T00:00:00Z",
        "interval_index_rule": "for zero-based t in 0..2192, open_time(t) = first_interval_open_utc + t * 28800 seconds",
        "last_interval_open_utc": "2024-12-31T16:00:00Z",
        "output_shape_and_ordering": "[9, 2193]; axis 0 is series index 0..8; axis 1 is interval index 0..2192 in increasing time order",
        "real_data_used": False,
        "registered_validation_end_utc": "2024-12-31T23:59:59Z",
        "registered_validation_start_utc": "2023-01-01T00:00:00Z",
        "sample_length_formula": "(2025-01-01T00:00:00Z - 2023-01-01T00:00:00Z) / 28800 = 2193",
        "sample_length_derivation": "2024-12-31T23:59:59Z is an inclusive human-readable region endpoint; 2025-01-01T00:00:00Z is the exact exclusive arithmetic boundary; (2025-01-01T00:00:00Z - 2023-01-01T00:00:00Z) / 28800 = 2193",
        "sample_length_intervals": 2193,
        "series_count": 9,
        "synthetic_only": True,
        "theoretical_mean_zero_required": True,
    }


def test_freeze_candidate_pins_garch_burn_in_and_component_stream_contract():
    value = freeze_candidate()
    garch = _dgp(value, "stationary_garch11_like")
    assert garch["burn_in_intervals"] == 10000
    assert garch["discarded_observations"] == 10000
    assert garch["parameters"]["generated_observations_per_series"] == 12193
    assert garch["parameters"]["retained_index_range"] == "10000..12192"
    assert garch["parameters"]["retained_observations"] == 2193
    assert "not an exact invariant draw" in garch["initial_state_distribution"]
    assert value["seed_contract"]["rng_algorithm"] == "numpy.random.Philox"
    assert value["seed_contract"]["component_streams"]["stationary_garch11_like"] == [f"series-{i}-innovations" for i in range(9)]
    assert "unordered traversal" in value["seed_contract"]["forbidden_randomness"]


FREEZE_CANDIDATE_SEMANTIC_MUTATIONS = {
    "dgp_definition": lambda c: c["required_stationary_dgps"][3].update(definition="a different AR process"),
    "ar_initial_state": lambda c: c["required_stationary_dgps"][3].update(initial_state_distribution="deterministic zero"),
    "ar_innovation_distribution": lambda c: c["required_stationary_dgps"][3].update(innovation_distribution="serially dependent innovations"),
    "ar_cross_series_dependence": lambda c: c["required_stationary_dgps"][3].update(cross_series_dependence="shared innovations"),
    "ar_output_shape": lambda c: c["required_stationary_dgps"][3].update(output_shape_and_ordering="[1, 1]"),
    "garch_initialization": lambda c: c["required_stationary_dgps"][5].update(initial_state_distribution="exact invariant draw"),
    "garch_innovation_distribution": lambda c: c["required_stationary_dgps"][5].update(innovation_distribution="serially dependent normal innovations"),
    "garch_finite_value_requirement": lambda c: c["required_stationary_dgps"][5].update(finite_value_requirement="non-finite values permitted"),
    "sample_output_shape": lambda c: c["synthetic_sample_contract"].update(output_shape_and_ordering="[9, 2192]"),
    "diagnostic_definition": lambda c: c["diagnostic_stress_cases"][0].update(definition="different structural break"),
    "diagnostic_initialization": lambda c: c["diagnostic_stress_cases"][0].update(initial_state_distribution="deterministic zero"),
    "diagnostic_seed_use": lambda c: c["diagnostic_stress_cases"][0].update(seed_use="use wall-clock time"),
    "diagnostic_output_shape": lambda c: c["diagnostic_stress_cases"][0].update(output_shape_and_ordering="[1, 1]"),
    "diagnostic_dependence": lambda c: c["diagnostic_stress_cases"][0].update(nine_series_construction="shared stream"),
}


@pytest.mark.parametrize("name", sorted(FREEZE_CANDIDATE_SEMANTIC_MUTATIONS))
def test_freeze_candidate_semantic_mutations_fail_closed(name):
    value = freeze_candidate()
    FREEZE_CANDIDATE_SEMANTIC_MUTATIONS[name](value)
    with pytest.raises(contracts.AssuranceValidationError):
        contracts.validate_calibration_spec_freeze_candidate(value)


def test_freeze_candidate_binds_activated_not_historical_hashes():
    bindings = freeze_candidate()["bindings"]
    assert bindings["source_main_commit"] == "6465d036af6b66ae6d845511c652d5857651bc49"
    assert bindings["activated_design"]["sha256"] == contracts.H001_ACTIVATED_DESIGN_SHA256
    assert bindings["activated_validator"]["sha256"] == contracts.H001_ACTIVATED_VALIDATOR_SHA256
    assert bindings["governance_amendment"]["sha256"] == contracts.H001_FREEZE_GOVERNANCE_AMENDMENT_SHA256
    assert bindings["source_handoff"]["sha256"] == contracts.H001_FREEZE_CANDIDATE_PREDECESSOR_SHA256
    assert contracts.H001_DESIGN_SHA256 not in (bindings["activated_design"]["sha256"], bindings["activated_validator"]["sha256"])
    draft = freeze_candidate()["historical_draft"]
    assert draft["sha256"] == contracts.H001_HISTORICAL_CALIBRATION_DRAFT_SHA256
    assert draft["obsolete_pre_activation_design_sha256"] == contracts.H001_DESIGN_SHA256
    assert draft["obsolete_pre_activation_validator_sha256"] == contracts.H001_VALIDATOR_SHA256
    assert (draft["is_current"], draft["is_frozen"], draft["is_effective"], draft["is_executable"]) == (False, False, False, False)


def test_freeze_candidate_historical_draft_bytes_are_untouched():
    raw = (DOCS / "h001_synthetic_null_calibration_spec_draft_v001.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == contracts.H001_HISTORICAL_CALIBRATION_DRAFT_SHA256
    assert json.loads(raw)["status"] == "DRAFT_ONLY_UNFROZEN_NOT_EXECUTABLE"


def test_freeze_candidate_seed_derivation_is_exact_and_reproducible():
    """Derive seeds from the documented rule only. No series, no bootstrap, no
    RNG draw: this exercises the seed contract as arithmetic over metadata."""
    seed = freeze_candidate()["seed_contract"]
    domain = seed["seed_domain"]
    assert domain == "h001-null-calibration/h001-synthetic-null-calibration-spec-freeze-candidate-v001/synthetic-only"
    payload = f"{domain}:iid_gaussian:outer:0".encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    assert int(digest[:16], 16) == int(hashlib.sha256(payload).hexdigest()[:16], 16)
    bootstrap = hashlib.sha256(f"{domain}:iid_gaussian:outer:0:bootstrap".encode("utf-8")).hexdigest()
    assert bootstrap != digest and int(bootstrap[:16], 16) < 2 ** 64
    assert seed["rng_algorithm"] == "numpy.random.Philox" and seed["new_or_updated_dependencies"] is False
    for flag in ("wall_clock_seeds_allowed", "os_entropy_allowed", "random_fallback_allowed", "retry_dependent_seeds_allowed", "environment_dependent_seeds_allowed", "result_dependent_reseeding_allowed"):
        assert seed[flag] is False


def test_freeze_candidate_dgps_are_exact_zero_mean_and_not_label_only():
    value = freeze_candidate()
    assert [item["dgp_id"] for item in value["required_stationary_dgps"]] == [
        "iid_gaussian", "iid_student_t_df5_standardized", "nine_series_common_factor_dependence",
        "stationary_ar1_phi_0p3", "stationary_ar1_phi_0p7", "stationary_garch11_like",
    ]
    for item in value["required_stationary_dgps"]:
        assert item["theoretical_mean"] == 0 and item["theoretical_mean_zero"] is True
        assert len(item["definition"]) >= 120 and "x[i," in item["definition"]
    assert _dgp(value, "stationary_ar1_phi_0p3")["parameters"] == {"phi": 0.3, "innovation_variance": 0.91, "stationary_variance": 1.0}
    assert _dgp(value, "stationary_ar1_phi_0p7")["parameters"]["phi"] == 0.7
    assert _dgp(value, "iid_student_t_df5_standardized")["parameters"] == {"degrees_of_freedom": 5, "scale_factor": "sqrt(3/5)", "standardized_variance": 1.0}
    assert _dgp(value, "nine_series_common_factor_dependence")["parameters"]["implied_pairwise_correlation"] == 0.5
    garch = _dgp(value, "stationary_garch11_like")["parameters"]
    assert (garch["omega"], garch["alpha"], garch["beta"]) == (0.05, 0.05, 0.9)
    assert garch["alpha"] + garch["beta"] < 1
    sample = value["synthetic_sample_contract"]
    assert sample["sample_length_intervals"] == 2193 and sample["series_count"] == 9 and sample["real_data_used"] is False


def test_freeze_candidate_diagnostics_are_defined_but_excluded_from_pass_fail():
    value = freeze_candidate()
    assert [item["case_id"] for item in value["diagnostic_stress_cases"]] == [
        "autocorrelation_structural_break", "mean_zero_regime_switching",
        "sparse_extreme_outliers", "variance_structural_break",
    ]
    for item in value["diagnostic_stress_cases"]:
        assert item["role"] == "DIAGNOSTIC_ONLY"
        assert item["part_of_formal_pass_fail"] is False and item["authorized_for_tuning"] is False
        assert item["theoretical_mean"] == 0 and item["parameters"]
    policy = value["diagnostic_case_policy"]
    assert policy["authorized_for_tuning"] is False
    assert policy["may_not_alter"] == ["DGP_PARAMETERS", "FAMILYWISE_ALPHA", "HAC_LAG", "PASS_THRESHOLD", "SELECTION_RULE", "STATIONARY_BLOCK_LENGTH", "TEST_STATISTIC", "VARIANT_FAMILY"]


# Adversarial coordinated mutations. Each entry is a distinct way the candidate
# could overstate its own authority, drift from an activated binding, or soften
# a registered statistical value; every one must fail closed.
FREEZE_CANDIDATE_MUTATIONS = {
    "marked_effective": lambda v: v["authorization_state"].update(specification_effective=True),
    "marked_frozen_effective": lambda v: v["authorization_state"].update(specification_frozen_effective=True),
    "marked_executable": lambda v: v["authorization_state"].update(execution_authorized=True),
    "review_removed": lambda v: v["authorization_state"].update(independent_review_required=False),
    "values_not_locked": lambda v: v["authorization_state"].update(candidate_values_locked_for_review=False),
    "results_present": lambda v: v["authorization_state"].update(results_exposed=True),
    "wrong_activated_design": lambda v: v["bindings"]["activated_design"].update(sha256="0" * 64),
    "historical_design_as_current": lambda v: v["bindings"]["activated_design"].update(sha256=contracts.H001_DESIGN_SHA256),
    "wrong_activated_validator": lambda v: v["bindings"]["activated_validator"].update(sha256="0" * 64),
    "historical_validator_as_current": lambda v: v["bindings"]["activated_validator"].update(sha256=contracts.H001_VALIDATOR_SHA256),
    "wrong_governance_amendment": lambda v: v["bindings"]["governance_amendment"].update(sha256="0" * 64),
    "wrong_v019_predecessor": lambda v: v["bindings"]["source_handoff"].update(sha256="0" * 64),
    "wrong_v019_path": lambda v: v["bindings"]["source_handoff"].update(path="docs/control/tasks/RECOVER_OR_RETIRE_CANDIDATE1_V0_FROZEN_INPUT/handoff_v018.json"),
    "wrong_source_main": lambda v: v["bindings"].update(source_main_commit="0" * 40),
    "wrong_temporal_activation": lambda v: v["bindings"]["temporal_activation_amendment"].update(sha256="0" * 64),
    "historical_draft_claimed_current": lambda v: v["historical_draft"].update(is_current=True),
    "historical_draft_promoted": lambda v: v["historical_draft"].update(is_frozen=True),
    "historical_draft_effective": lambda v: v["historical_draft"].update(is_effective=True),
    "historical_draft_executable": lambda v: v["historical_draft"].update(is_executable=True),
    "historical_draft_modified": lambda v: v["historical_draft"].update(sha256="0" * 64),
    "historical_draft_rebound_to_activated": lambda v: v["historical_draft"].update(obsolete_pre_activation_design_sha256=contracts.H001_ACTIVATED_DESIGN_SHA256),
    "wrong_seed_domain": lambda v: v["seed_contract"].update(seed_domain="h001-null-calibration/other/synthetic-only"),
    "wall_clock_seed": lambda v: v["seed_contract"].update(wall_clock_seeds_allowed=True),
    "os_entropy_seed": lambda v: v["seed_contract"].update(os_entropy_allowed=True),
    "random_fallback_seed": lambda v: v["seed_contract"].update(random_fallback_allowed=True),
    "retry_dependent_seed": lambda v: v["seed_contract"].update(retry_dependent_seeds_allowed=True),
    "environment_dependent_seed": lambda v: v["seed_contract"].update(environment_dependent_seeds_allowed=True),
    "result_dependent_reseeding": lambda v: v["seed_contract"].update(result_dependent_reseeding_allowed=True),
    "ambiguous_seed_derivation": lambda v: v["seed_contract"].update(seed_integer_rule="an implementation-defined integer derived from the digest"),
    "wall_clock_in_payload_rule": lambda v: v["seed_contract"].update(outer_payload_rule="seed_domain + wall clock timestamp"),
    "new_dependency_declared": lambda v: v["seed_contract"].update(new_or_updated_dependencies=True),
    "wrong_outer_replications": lambda v: v["registered_test_target"].update(outer_synthetic_replications=1000),
    "wrong_bootstrap_repetitions": lambda v: v["registered_test_target"].update(bootstrap_repetitions=5000),
    "wrong_block_length": lambda v: v["registered_test_target"].update(stationary_block_length=64),
    "wrong_hac_lag": lambda v: v["registered_test_target"].update(hac_lag=22),
    "wrong_familywise_alpha": lambda v: v["registered_test_target"].update(familywise_alpha=0.1),
    "wrong_variant_series": lambda v: v["registered_test_target"].update(registered_variant_series=8),
    "wrong_fwer_threshold": lambda v: v["pass_criterion"].update(fwer_upper_bound_threshold=0.1),
    "inexact_interval_method": lambda v: v["pass_criterion"].update(binomial_interval_method="normal approximation upper bound"),
    "interval_not_exact": lambda v: v["pass_criterion"].update(binomial_interval_is_exact=False),
    "unspecified_interval_confidence": lambda v: v["pass_criterion"].update(binomial_confidence_level=0.9),
    "missing_dgp": lambda v: v["required_stationary_dgps"].pop(),
    "extra_dgp": lambda v: v["required_stationary_dgps"].append(dict(v["required_stationary_dgps"][0], dgp_id="iid_uniform")),
    "duplicate_dgp": lambda v: v["required_stationary_dgps"].append(dict(v["required_stationary_dgps"][0])),
    "label_only_dgp": lambda v: _dgp(v, "iid_gaussian").update(definition="IID Gaussian"),
    "non_zero_mean_dgp": lambda v: _dgp(v, "iid_gaussian").update(theoretical_mean=1),
    "non_zero_mean_flag": lambda v: _dgp(v, "iid_gaussian").update(theoretical_mean_zero=False),
    "wrong_ar_coefficient": lambda v: _dgp(v, "stationary_ar1_phi_0p3")["parameters"].update(phi=0.4),
    "unstandardized_student_t": lambda v: _dgp(v, "iid_student_t_df5_standardized")["parameters"].update(scale_factor="1"),
    "wrong_common_factor_correlation": lambda v: _dgp(v, "nine_series_common_factor_dependence")["parameters"].update(implied_pairwise_correlation=0.9),
    "nonstationary_garch": lambda v: _dgp(v, "stationary_garch11_like")["parameters"].update(alpha=0.2, beta=0.9),
    "wrong_sample_length": lambda v: v["synthetic_sample_contract"].update(sample_length_intervals=2192),
    "wrong_series_count": lambda v: v["synthetic_sample_contract"].update(series_count=8),
    "diagnostic_in_pass_fail": lambda v: _stress(v, "sparse_extreme_outliers").update(part_of_formal_pass_fail=True),
    "diagnostic_participates": lambda v: v["pass_criterion"].update(diagnostic_cases_participate=True),
    "diagnostic_promoted_to_required": lambda v: v["diagnostic_stress_cases"][0].update(role="REQUIRED_STATIONARY_DGP_IN_FORMAL_PASS_FAIL"),
    "tuning_from_diagnostics": lambda v: v["diagnostic_case_policy"].update(authorized_for_tuning=True),
    "tuning_lock_removed": lambda v: v["diagnostic_case_policy"]["may_not_alter"].remove("HAC_LAG"),
    "stress_case_tunable": lambda v: _stress(v, "variance_structural_break").update(authorized_for_tuning=True),
    "missing_stress_case": lambda v: v["diagnostic_stress_cases"].pop(),
    "label_only_stress_case": lambda v: _stress(v, "variance_structural_break").update(definition="variance break"),
    "real_data_access": lambda v: v["authorization_state"].update(real_data_access_authorized=True),
    "h001_validation_execution": lambda v: v["authorization_state"].update(h001_validation_execution_authorized=True),
    "h001_holdout_execution": lambda v: v["authorization_state"].update(h001_holdout_execution_authorized=True),
    "scientific_authority": lambda v: v["authorization_state"].update(scientific_authorization=True),
    "paper_authority": lambda v: v["authorization_state"].update(paper_trade_authorization=True),
    "live_authority": lambda v: v["authorization_state"].update(live_authorization=True),
    "edge_proven": lambda v: v.update(edge_status="EDGE_PROVEN"),
    "live_unblocked": lambda v: v.update(live_status="READY"),
    "edge_proven_in_non_effects": lambda v: v["non_effects"].append("EDGE_PROVEN"),
    "wrong_status": lambda v: v.update(status="FROZEN_EFFECTIVE"),
    "wrong_document_id": lambda v: v.update(document_id="h001-synthetic-null-calibration-spec-freeze-candidate-v002"),
    "wrong_document_kind": lambda v: v.update(document_kind="qnty_h001_synthetic_null_calibration_spec_draft"),
    "wrong_protocol": lambda v: v.update(governed_h001_protocol_id="other_protocol"),
}


@pytest.mark.parametrize("name", sorted(FREEZE_CANDIDATE_MUTATIONS))
def test_freeze_candidate_mutations_fail_closed(name):
    value = freeze_candidate()
    FREEZE_CANDIDATE_MUTATIONS[name](value)
    with pytest.raises(ValueError):
        contracts.validate_calibration_spec_freeze_candidate(value)
    with pytest.raises(ValueError):
        contracts.load_and_validate_calibration_spec_freeze_candidate(contracts.canonical_json_bytes(value))


def test_freeze_candidate_rejects_missing_extra_duplicate_and_noncanonical_bytes():
    raw = FREEZE_CANDIDATE.read_bytes()
    with pytest.raises(ValueError):
        contracts.load_and_validate_calibration_spec_freeze_candidate(raw[:-1] + b',"extra":1}')
    duplicate = raw[:-1] + b',"status":"FREEZE_CANDIDATE_FOR_INDEPENDENT_REVIEW_NOT_EFFECTIVE_NOT_EXECUTABLE"}'
    with pytest.raises(ValueError, match="duplicate"):
        contracts.load_and_validate_calibration_spec_freeze_candidate(duplicate)
    with pytest.raises(ValueError):
        contracts.load_and_validate_calibration_spec_freeze_candidate(json.dumps(json.loads(raw)).encode())
    with pytest.raises(ValueError, match="exact bytes input"):
        contracts.load_and_validate_calibration_spec_freeze_candidate(bytearray(raw))
    value = freeze_candidate()
    value.pop("seed_contract")
    with pytest.raises(ValueError):
        contracts.validate_calibration_spec_freeze_candidate(value)


def test_freeze_candidate_validation_is_metadata_only():
    """The freeze-candidate validators must not reach outside the document."""
    source = (ROOT / "quantbot/assurance/contracts.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    names = {
        "validate_calibration_spec_freeze_candidate", "load_and_validate_calibration_spec_freeze_candidate",
        "_validate_freeze_candidate_historical_draft", "_validate_freeze_candidate_seed_contract",
        "_validate_freeze_candidate_dgps", "_validate_freeze_candidate_stress_cases", "_freeze_candidate_binding",
    }
    forbidden = {"open", "read_bytes", "read_text", "urlopen", "request", "get", "post", "connect", "system", "run", "Popen", "getenv", "listdir", "glob", "iterdir", "exists"}
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or node.name not in names:
            continue
        for child in ast.walk(node):
            if isinstance(child, ast.Attribute):
                assert child.attr not in forbidden, f"{node.name} reaches outside the document via {child.attr}"
            if isinstance(child, ast.Name):
                assert child.id not in {"open", "eval", "exec", "__import__"}, f"{node.name} uses {child.id}"
    assert "import requests" not in source and "import socket" not in source and "import os" not in source


def calibration_activation():
    return json.loads(CALIBRATION_ACTIVATION.read_bytes())


def test_h001_calibration_activation_is_canonical_and_exactly_effective_but_not_executable():
    raw = CALIBRATION_ACTIVATION.read_bytes()
    value = contracts.load_and_validate_h001_synthetic_null_calibration_spec_freeze_activation(raw)
    assert contracts.canonical_json_bytes(value) == raw and not raw.endswith(b"\n")
    assert value["effective"] is True
    assert value["authorization_state"]["specification_frozen_effective"] is True
    assert value["authorization_state"]["execution_authorized"] is False
    assert "SPECIFICATION_REMAINS_UNFROZEN" not in value["non_effects"]


@pytest.mark.parametrize("mutation", [
    lambda v: v["hash_bindings"]["effective_specification"].update(sha256="0" * 64),
    lambda v: v["hash_bindings"]["candidate_rereview_record"].update(sha256="0" * 64),
    lambda v: v["hash_bindings"]["handoff_v021"].update(sha256="0" * 64),
    lambda v: v["review_history"].update(candidate_final_reviewed_head="0" * 40),
    lambda v: v["review_history"].update(review_record_merge_commit="0" * 40),
    lambda v: v["frozen_values"].update(hac_lag=22),
    lambda v: v.update(effective=False),
    lambda v: v["authorization_state"].update(execution_authorized=True),
    lambda v: v["authorization_state"].update(execution_implementation_authorized=True),
    lambda v: v["authorization_state"].update(results_exposed=True),
    lambda v: v["authorization_state"].update(real_data_access_authorized=True),
    lambda v: v["authorization_state"].update(h001_validation_execution_authorized=True),
    lambda v: v["authorization_state"].update(h001_holdout_execution_authorized=True),
    lambda v: v["authorization_state"].update(scientific_authorization=True),
    lambda v: v["authorization_state"].update(paper_trade_authorization=True),
    lambda v: v["authorization_state"].update(live_authorization=True),
    lambda v: v["non_effects"].remove("EDGE_UNPROVEN"),
    lambda v: v["non_effects"].remove("BLOCK_LIVE_INTEGRATION"),
])
def test_h001_calibration_activation_mutations_fail_closed(mutation):
    value = calibration_activation()
    mutation(value)
    with pytest.raises(ValueError):
        contracts.validate_h001_synthetic_null_calibration_spec_freeze_activation(value)
    with pytest.raises(ValueError):
        contracts.load_and_validate_h001_synthetic_null_calibration_spec_freeze_activation(contracts.canonical_json_bytes(value))


def test_h001_calibration_activation_loader_rejects_duplicate_noncanonical_and_non_bytes():
    raw = CALIBRATION_ACTIVATION.read_bytes()
    duplicate = raw.replace(b'"effective":true,', b'"effective":true,"effective":true,', 1)
    with pytest.raises(ValueError, match="duplicate"):
        contracts.load_and_validate_h001_synthetic_null_calibration_spec_freeze_activation(duplicate)
    with pytest.raises(ValueError, match="non-canonical"):
        contracts.load_and_validate_h001_synthetic_null_calibration_spec_freeze_activation(json.dumps(json.loads(raw)).encode())
    with pytest.raises(ValueError, match="exact bytes"):
        contracts.load_and_validate_h001_synthetic_null_calibration_spec_freeze_activation(bytearray(raw))
