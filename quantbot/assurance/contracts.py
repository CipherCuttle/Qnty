"""Strict, metadata-only validators for the H001 assurance scaffolds.

This module deliberately has no filesystem discovery, networking, artifact-store,
database, environment, or real-data dependencies.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone

SCHEMA_VERSION = "0.1.0"
H001_PROTOCOL_ID = "real_btc_h001_funding_crowding_reversal_falsification_v0"
H001_DESIGN_SHA256 = "055ea162a11d4042320daeb74e153ebbd27969dd29a60c226cb84a8fc38b8900"
H001_VALIDATOR_SHA256 = "888bc4663e3d7fb9b398f944bf2b67553e8959e0173be77183ca8b288156172a"
GOVERNANCE_AMENDMENT_SHA256 = "a22d0cf260f31d7104fc4d4fe96030c8666179c20c7737dfe20a59f3c7200ddc"

SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
IDENTIFIER_RE = re.compile(r"[a-z0-9][a-z0-9._:-]*\Z")
CANONICAL_UTC_TIMESTAMP_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z")
CONTROL_RECEIPT_PATH_RE = re.compile(r"docs/control/(?:[A-Za-z0-9._-]+/)*[A-Za-z0-9._-]+\.json\Z")
SECRET_KEYS = {"token", "secret", "password", "credential", "private_key", "cookie", "authorization", "api_key"}
FORBIDDEN_KEYS = {"returns", "prices", "funding", "p_values", "p-values", "statistics", "performance", "strategy_ranking", "raw_data", "artifact_bytes", "store_roots", "store_uri", "credentials", "private_reasoning", "chain_of_thought", "scientific_claim", "result_payload"}
DISCLOSURE_KINDS = {"DESIGNATED_DEVELOPMENT", "DESIGNATED_VALIDATION", "DESIGNATED_HOLDOUT", "VALIDATION_STATISTIC_EXPOSED", "HOLDOUT_UNSEALED", "HOLDOUT_STATISTIC_EXPOSED", "REGION_GLOBALLY_CONSUMED", "DESCRIPTIVE_REUSE_ONLY"}
DISCLOSURE_STATUSES = {"RECORDED_APPEND_ONLY"}
LEDGER_STATUSES = {"SCHEMA_IMPLEMENTED_EMPTY_NO_BACKFILL", "APPEND_ONLY_METADATA_DISCLOSURES"}

_REVIEW_PROTOCOL_KEYS = {
    "base_commit_sha", "document_id", "document_kind", "failure_verdict", "initial_failed_review_head",
    "initial_failure_verdict", "merged_main_commit_sha", "non_effects", "pass_verdict", "prohibited_actions",
    "review_kind", "review_requirements", "reviewed_commit_sha", "schema_version", "status",
}
_REVIEW_PROTOCOL_EXPECTED = {
    "schema_version": SCHEMA_VERSION,
    "document_kind": "qnty_replayable_review_protocol_record",
    "document_id": "h001-pre-data-assurance-scaffold-rereview-protocol-v001",
    "status": "RECORDED_AFTER_REVIEW_NOT_PREREGISTERED",
    "review_kind": "INDEPENDENT_ADVERSARIAL_REREVIEW",
    "base_commit_sha": "28d6c70e9d7cb11c55d1afdf8b4e5ad9754f7aba",
    "initial_failed_review_head": "3fc6186b7644e8fbdf5f18f2f70275b20ca741d0",
    "reviewed_commit_sha": "c52c607045803ab6d6e2a961f0f697aa72bf7581",
    "merged_main_commit_sha": "ae61c6162f3164e0b24dd567a6ef73bdb5ecf8ea",
    "initial_failure_verdict": "QNTY_H001_PRE_DATA_ASSURANCE_SCAFFOLD_REVIEW_FAILED",
    "pass_verdict": "QNTY_H001_PRE_DATA_ASSURANCE_SCAFFOLD_REREVIEW_PASSED",
    "failure_verdict": "QNTY_H001_PRE_DATA_ASSURANCE_SCAFFOLD_REREVIEW_FAILED",
    "review_requirements": [
        "APPEND_ONLY_CHAIN_INTACT", "AUTHORITY_DRIFT_ABSENT", "CALIBRATION_BOUNDARY_FAIL_CLOSED",
        "CANONICAL_APPEND_VALIDATION", "CANONICAL_JSON_VALIDATION", "CONTROL_RECEIPT_PATH_CONTRACT",
        "EXACT_HEAD_AND_SCOPE", "FULL_TEST_SUITE_PASS", "NO_GIT_EXPORT_PASS", "REMOTE_CI_PASS",
        "UTC_TIMESTAMP_CONTRACT",
    ],
    "prohibited_actions": [
        "ACCESS_REAL_DATA", "ACCESS_STORES", "APPLY_TEMPORAL_CAUSALITY_AMENDMENT", "EXECUTE_CALIBRATION",
        "FREEZE_CALIBRATION_SPECIFICATION", "GRANT_SCIENTIFIC_PAPER_OR_LIVE_AUTHORITY", "RUN_SYNTHETIC_CANARY",
    ],
    "non_effects": [
        "DOES_NOT_AUTHORIZE_EXECUTION", "DOES_NOT_AUTHORIZE_REAL_DATA", "DOES_NOT_AUTHORIZE_STORE_ACCESS",
        "DOES_NOT_PROVE_MARKET_EDGE", "REVIEW_PROTOCOL_WAS_NOT_PREREGISTERED_BEFORE_REVIEW",
    ],
}
_REVIEW_PACKET_KEYS = {
    "commands", "document_id", "document_kind", "environment_identity", "finding_counts", "harness_source_hashes",
    "redaction_manifest", "review_id", "review_kind", "review_specification_hash", "reviewed_artifact_hashes",
    "reviewed_commit_sha", "schema_version", "status", "stderr_artifact_hashes", "stdout_artifact_hashes", "verdict",
}
_REVIEW_ARTIFACT_HASHES = {
    "docs/assurance/H001_PRE_DATA_ASSURANCE_SCAFFOLD.md": "2db845247b8737bce60ed1ca049552dd7fb6c0025bcaa566fbf1d928b44686aa",
    "docs/assurance/durable_store_failure_domain_evidence_schema_v001.json": "8f13f87ce97fbdf7771004e02e33809805a75338383e93c870ce564a48968985",
    "docs/assurance/global_real_protocol_holdout_disclosure_ledger_v001.json": "71b8ff5eb74461b0789eeb75388808fc787692fc6d84fad1acb573d4b36315ee",
    "docs/assurance/h001_synthetic_null_calibration_spec_draft_v001.json": "7e05a0b2b44dd4e3fbadf3e121791eb2ee76385a6b2ec6b872984cbb3510ecf6",
    "docs/assurance/h001_temporal_causality_amendment_draft_v001.json": "03c57d0c0935eb37d53ee68410935e258e3bde0f5b2c8d19048e4c1d979d5639",
    "docs/assurance/replayable_review_evidence_packet_schema_v001.json": "990052469571b2ff100180c706e0e38257fd952e32320b665753d23212cfbcbb",
    "docs/assurance/synthetic_artifact_canary_scaffold_v001.json": "45e6f95fece2328df2c39f2fce790bba37a0944ea7c5bc33b8e505820beb5392",
    "docs/control/active_task.json": "c4bd97ae3895143a930d9b873251b701aa8edb8dfd9c875b169a107e3294e0e3",
    "docs/control/tasks/RECOVER_OR_RETIRE_CANDIDATE1_V0_FROZEN_INPUT/handoff_v014.json": "96ff0d934548e02fbcfec8368829520d6add22abe83413adfbc456c009b1d117",
    "quantbot/assurance/__init__.py": "31e165747eb5cfa462237d163faab0bbacbd9eb36c815ea42d6418192a378cbe",
    "quantbot/assurance/contracts.py": "4d7c18e5e97732b08752515acb126e50c051cf71275c77b51613f3d3eb93e9aa",
    "quantbot/assurance/h001_null_calibration.py": "deaceeec03578a7f430972c8f4de2bb96798e660b0cbe64504c6fbf8da512bdd",
    "quantbot/continuity/context.py": "ff05b4165032f21ac2cd645096d2f0e5f4861175857478ed1a8c332194a1edf4",
    "tests/assurance/test_contracts.py": "0a90c085cf5dd24be277562b65ec2b0307af8c3ab73056c531fb8e0583b9e8b2",
    "tests/assurance/test_h001_null_calibration.py": "47bb18360165effc826102c84b931a51a198a994b99cc6bae24b2bf9bd87a06c",
    "tests/continuity/test_cross_agent_continuity.py": "e068e2ca6860094136bcbe21a0ae0b73041b39b963e9b0d3d3e97e7fa7fcc079",
}
_REVIEW_HARNESS_HASHES = {key: _REVIEW_ARTIFACT_HASHES[key] for key in (
    "quantbot/assurance/contracts.py", "quantbot/assurance/h001_null_calibration.py", "quantbot/continuity/context.py",
    "tests/assurance/test_contracts.py", "tests/assurance/test_h001_null_calibration.py", "tests/continuity/test_cross_agent_continuity.py",
)}
_REVIEW_COMMANDS = [
    "set -euo pipefail",
    "REPO=/home/swirky/DevHub/repos/Qnty",
    "BASE=28d6c70e9d7cb11c55d1afdf8b4e5ad9754f7aba",
    "HEAD=c52c607045803ab6d6e2a961f0f697aa72bf7581",
    "PY=$REPO/.venv/bin/python",
    "REVIEW_DIR=$(mktemp -d /tmp/qnty-pr282-rereview.XXXXXX)",
    "SCOPE_DIR=$(mktemp -d /tmp/qnty-pr282-scope.XXXXXX)",
    "EXPORT=$(mktemp -d /tmp/qnty-h001-review-export.XXXXXX)",
    "git -C $REPO worktree add --detach $REVIEW_DIR $HEAD",
    "cd $REVIEW_DIR",
    'test "$(git rev-parse HEAD)" = "$HEAD"',
    'test "$(git merge-base "$BASE" "$HEAD")" = "$BASE"',
    'git diff --name-only "$BASE...$HEAD"',
    'test "$(git diff --name-only "$BASE...$HEAD" | wc -l)" -eq 16',
    "printf '%s\\n' docs/assurance/H001_PRE_DATA_ASSURANCE_SCAFFOLD.md docs/assurance/durable_store_failure_domain_evidence_schema_v001.json docs/assurance/global_real_protocol_holdout_disclosure_ledger_v001.json docs/assurance/h001_synthetic_null_calibration_spec_draft_v001.json docs/assurance/h001_temporal_causality_amendment_draft_v001.json docs/assurance/replayable_review_evidence_packet_schema_v001.json docs/assurance/synthetic_artifact_canary_scaffold_v001.json docs/control/active_task.json docs/control/tasks/RECOVER_OR_RETIRE_CANDIDATE1_V0_FROZEN_INPUT/handoff_v014.json quantbot/assurance/__init__.py quantbot/assurance/contracts.py quantbot/assurance/h001_null_calibration.py quantbot/continuity/context.py tests/assurance/test_contracts.py tests/assurance/test_h001_null_calibration.py tests/continuity/test_cross_agent_continuity.py | sort > $SCOPE_DIR/expected-scope.txt",
    'git diff --name-only "$BASE...$HEAD" | sort > $SCOPE_DIR/observed-scope.txt',
    "diff -u $SCOPE_DIR/expected-scope.txt $SCOPE_DIR/observed-scope.txt",
    "sha256sum docs/assurance/H001_PRE_DATA_ASSURANCE_SCAFFOLD.md docs/assurance/replayable_review_evidence_packet_schema_v001.json quantbot/assurance/contracts.py quantbot/continuity/context.py",
    "$PY -m pytest tests/assurance -q",
    "$PY -m pytest tests/continuity -q",
    "$PY -m pytest tests/sandbox -q",
    "$PY -m pytest tests/artifacts -q",
    "$PY -m pytest tests/experiment/test_h001_real_falsification_preregistration.py -q",
    "$PY -m pytest -q",
    "PATH=$REPO/.venv/bin:$PATH $REPO/scripts/release_smoke.sh",
    "$PY -m quantbot.continuity verify",
    "$PY -m quantbot.continuity show",
    "$PY -m quantbot.artifacts verify-registry",
    "$PY -m quantbot.artifacts status",
    "git archive $HEAD | tar -x -C $EXPORT",
    "test ! -e $EXPORT/.git",
    "cd $EXPORT",
    "PYTHONPATH=$EXPORT $PY -m pytest tests/assurance tests/continuity -q",
    "PYTHONPATH=$EXPORT $PY -m quantbot.continuity verify",
    "PYTHONPATH=$EXPORT $PY -m quantbot.continuity show",
    "cd $REVIEW_DIR && git diff --check",
    'test -z "$(git status --short)"',
    "gh run list --repo CipherCuttle/Qnty --commit $HEAD --json name,status,conclusion,headSha",
]

def review_protocol_record() -> dict:
    return json.loads(canonical_json_bytes(_REVIEW_PROTOCOL_EXPECTED).decode("utf-8"))

def validate_review_protocol_record(value: object) -> dict:
    data = _base(value, "qnty_replayable_review_protocol_record", _REVIEW_PROTOCOL_EXPECTED["document_id"], _REVIEW_PROTOCOL_EXPECTED["status"], _REVIEW_PROTOCOL_KEYS)
    if data != _REVIEW_PROTOCOL_EXPECTED:
        _fail("review protocol record drifted or claims preregistration/freezing before review")
    for key in ("base_commit_sha", "initial_failed_review_head", "reviewed_commit_sha", "merged_main_commit_sha"):
        if type(data[key]) is not str or not re.fullmatch(r"[0-9a-f]{40}", data[key]):
            _fail(f"{key}: lowercase commit sha required")
    return data

def _validate_hash_records(value: object, expected: dict[str, str], label: str) -> None:
    records = _list(value, label)
    if records != [{"path": path, "sha256": expected[path]} for path in sorted(expected)]:
        _fail(f"{label}: exact independently pinned hash set required")
    for record in records:
        _keys(record, {"path", "sha256"}, f"{label} entry")
        if not re.fullmatch(r"[A-Za-z0-9._/-]+", record["path"]) or ".." in record["path"].split("/"):
            _fail(f"{label}: unsafe relative path")
        _sha(record["sha256"], f"{label} sha256")

def validate_review_evidence_packet(value: object) -> dict:
    data = _base(value, "qnty_replayable_review_evidence_packet", "h001-pre-data-assurance-scaffold-rereview-packet-v001", "COMPLETED_METADATA_ONLY_NO_REAL_DATA_OR_SECRETS", _REVIEW_PACKET_KEYS)
    expected = {
        "schema_version": SCHEMA_VERSION, "document_kind": "qnty_replayable_review_evidence_packet",
        "document_id": "h001-pre-data-assurance-scaffold-rereview-packet-v001", "status": "COMPLETED_METADATA_ONLY_NO_REAL_DATA_OR_SECRETS",
        "review_id": "h001-pre-data-assurance-scaffold-rereview-v001", "review_kind": "INDEPENDENT_ADVERSARIAL_REREVIEW",
        "reviewed_commit_sha": "c52c607045803ab6d6e2a961f0f697aa72bf7581", "verdict": "QNTY_H001_PRE_DATA_ASSURANCE_SCAFFOLD_REREVIEW_PASSED",
        "environment_identity": {"checkout_mode": "DETACHED_WORKTREE", "exported_tree_verified": True, "git_metadata_available": True, "network_access": "NOT_USED", "python_environment": "REPOSITORY_VENV", "reviewed_tree_source": "PINNED_COMMIT", "stdout_stderr_artifacts_persisted": False},
        "finding_counts": {"blocker": 0, "major": 0, "minor": 0},
        "redaction_manifest": {"private_reasoning_included": False, "real_data_included": False, "redaction_status": "NO_SECRET_BEARING_OUTPUT_PERSISTED", "secret_values_included": False, "stderr_persisted": False, "stdout_persisted": False},
        "stdout_artifact_hashes": [], "stderr_artifact_hashes": [], "commands": _REVIEW_COMMANDS,
    }
    if data["reviewed_commit_sha"] != expected["reviewed_commit_sha"] or data["verdict"] != expected["verdict"]:
        _fail("review packet head or verdict drifted")
    if data["environment_identity"] != expected["environment_identity"] or data["finding_counts"] != expected["finding_counts"] or data["redaction_manifest"] != expected["redaction_manifest"]:
        _fail("review packet environment, findings, or redaction metadata drifted")
    if data["commands"] != _REVIEW_COMMANDS or data["stdout_artifact_hashes"] or data["stderr_artifact_hashes"]:
        _fail("review packet commands or output hashes drifted")
    if len(data["commands"]) != len(set(data["commands"])) or any(type(command) is not str or not command for command in data["commands"]):
        _fail("review packet commands must be non-empty and unique")
    if any(token in command for command in data["commands"] for token in ("--no-git-export", "remote CI checks", "token=", "password=", "credential=")):
        _fail("review packet contains a non-replayable or secret-bearing command")
    required_markers = (
        "$HEAD", "$BASE", "BASE=28d6c70e9d7cb11c55d1afdf8b4e5ad9754f7aba", "git merge-base",
        "worktree add --detach", "cd $REVIEW_DIR", "cd $EXPORT", "git diff --name-only", "diff -u",
        "sha256sum", "git archive", "! -e $EXPORT/.git", "PYTHONPATH=$EXPORT", "gh run list", "git status --short",
    )
    if any(not any(marker in command for command in data["commands"]) for marker in required_markers):
        _fail("review packet command coverage is incomplete")
    if any(_REVIEW_PROTOCOL_EXPECTED["merged_main_commit_sha"] in command for command in data["commands"]):
        _fail("review packet replay recipe must use the reviewed-PR base, not the merged-main commit")
    _validate_hash_records(data["reviewed_artifact_hashes"], _REVIEW_ARTIFACT_HASHES, "reviewed_artifact_hashes")
    _validate_hash_records(data["harness_source_hashes"], _REVIEW_HARNESS_HASHES, "harness_source_hashes")
    expected_protocol_hash = hashlib.sha256(canonical_json_bytes(_REVIEW_PROTOCOL_EXPECTED)).hexdigest()
    if data["review_specification_hash"] != expected_protocol_hash:
        _fail("review packet protocol hash drifted")
    _sha(data["review_specification_hash"], "review_specification_hash")
    return data

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

def _identifier(value: object, label: str) -> str:
    value = _str(value, label)
    if not IDENTIFIER_RE.fullmatch(value):
        _fail(f"{label}: lowercase identifier required")
    return value

def _parse_canonical_utc_timestamp(value: object, label: str) -> datetime:
    if type(value) is not str or not CANONICAL_UTC_TIMESTAMP_RE.fullmatch(value):
        _fail(f"{label}: canonical UTC timestamp required")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as error:
        raise AssuranceValidationError(f"{label}: canonical UTC timestamp required") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(None):
        _fail(f"{label}: UTC timestamp required")
    return parsed

def _validate_control_receipt_path(value: object) -> str:
    if type(value) is not str or not CONTROL_RECEIPT_PATH_RE.fullmatch(value) or any(segment in {"", ".", ".."} for segment in value.split("/")):
        _fail("source_control_receipt_path: docs/control JSON path required")
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
    for key in ("entry_id", "protocol_id", "hypothesis_id", "dataset_region_id"):
        _identifier(data[key], key)
    if type(data["disclosure_kind"]) is not str or data["disclosure_kind"] not in DISCLOSURE_KINDS:
        _fail("unknown disclosure kind")
    if type(data["disclosure_status"]) is not str or data["disclosure_status"] not in DISCLOSURE_STATUSES:
        _fail("unknown disclosure status")
    _validate_control_receipt_path(data["source_control_receipt_path"])
    _sha(data["source_control_receipt_sha256"], "source_control_receipt_sha256")
    start = _parse_canonical_utc_timestamp(data["region_start_utc"], "region_start_utc")
    end = _parse_canonical_utc_timestamp(data["region_end_utc"], "region_end_utc")
    _parse_canonical_utc_timestamp(data["recorded_at_utc"], "recorded_at_utc")
    if start >= end:
        _fail("region boundaries must be increasing")
    _walk_forbidden(data)
    return data

def _semantic_disclosure_key(entry: dict) -> tuple[str, ...]:
    return tuple(entry[key] for key in ("protocol_id", "hypothesis_id", "dataset_region_id", "region_start_utc", "region_end_utc", "disclosure_kind"))

def _validate_ledger_entries(entries: list) -> None:
    seen_ids = set()
    seen_semantics = set()
    previous_recorded_at = None
    for entry in entries:
        item = _entry(entry)
        if item["entry_id"] in seen_ids:
            _fail("duplicate entry ID")
        seen_ids.add(item["entry_id"])
        semantic_key = _semantic_disclosure_key(item)
        if semantic_key in seen_semantics:
            _fail("duplicate semantic disclosure")
        seen_semantics.add(semantic_key)
        recorded_at = _parse_canonical_utc_timestamp(item["recorded_at_utc"], "recorded_at_utc")
        if previous_recorded_at is not None and recorded_at < previous_recorded_at:
            _fail("ledger entries must be ordered by recorded_at_utc")
        previous_recorded_at = recorded_at

def validate_holdout_disclosure_ledger(value: object) -> dict:
    data = _keys(value, {"document_id", "document_kind", "entries", "status", "schema_version"}, "qnty_global_real_protocol_holdout_disclosure_ledger")
    if data["schema_version"] != SCHEMA_VERSION or data["document_kind"] != "qnty_global_real_protocol_holdout_disclosure_ledger" or data["document_id"] != "global-real-protocol-holdout-disclosure-ledger-v001":
        _fail("qnty_global_real_protocol_holdout_disclosure_ledger: identity drifted")
    if type(data["status"]) is not str or data["status"] not in LEDGER_STATUSES:
        _fail("unknown ledger status")
    _walk_forbidden(data)
    entries = _list(data["entries"], "entries")
    if data["status"] == "SCHEMA_IMPLEMENTED_EMPTY_NO_BACKFILL" and entries:
        _fail("empty ledger status requires no entries")
    if data["status"] == "APPEND_ONLY_METADATA_DISCLOSURES" and not entries:
        _fail("populated ledger status requires entries")
    _validate_ledger_entries(entries)
    return data

def validate_ledger_append(previous: bytes, candidate: bytes) -> dict:
    if type(previous) is not bytes or type(candidate) is not bytes:
        _fail("ledger append requires canonical JSON bytes")
    before = load_and_validate_assurance_scaffold(previous, validate_holdout_disclosure_ledger)
    after = load_and_validate_assurance_scaffold(candidate, validate_holdout_disclosure_ledger)
    old = before["entries"]; new = after["entries"]
    if len(new) < len(old) or [canonical_json_bytes(item) for item in new[:len(old)]] != [canonical_json_bytes(item) for item in old]:
        _fail("ledger append must preserve previous entries byte-semantically and in order")
    if before["status"] == "SCHEMA_IMPLEMENTED_EMPTY_NO_BACKFILL" and old:
        _fail("empty ledger cannot contain prior entries")
    if len(new) > len(old) and after["status"] != "APPEND_ONLY_METADATA_DISCLOSURES":
        _fail("appended ledger must use populated status")
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


_H001_TEMPORAL_REREVIEW_RECORD_KEYS = {
    "artifact_bindings", "candidate_review_scope", "closed_findings", "document_id",
    "document_kind", "final_finding_counts", "final_verdict", "non_effects",
    "preregistered", "recorded_after_review", "repair_scope", "review_bindings",
    "review_id", "review_results", "schema_version", "status",
}
_H001_TEMPORAL_REREVIEW_ARTIFACTS = [
    {"path": "docs/control/amendments/candidate1_h001_temporal_causality_v001.json", "sha256": "2e8c07ac3ea2721e182a82ce8437cc8db4adef0f4a0ec17066d29f65314da829"},
    {"path": "docs/control/tasks/RECOVER_OR_RETIRE_CANDIDATE1_V0_FROZEN_INPUT/handoff_v016.json", "sha256": "34bff7df542af4614b082478301441c86d41126b903395485b8c0ae9028def6a"},
    {"path": "docs/experiments/candidate1_h001_real_data_falsification_temporal_candidate_v001.json", "sha256": "c6fb8d796559c53188c10e729a2257bc593c7a80526963c97515f747820e2276"},
    {"path": "quantbot/experiment/h001_temporal_causality.py", "sha256": "be3f9b4aa229309af6974efeeea458189f1bdbf2b88d28cfc4e4284bfd566f4f"},
    {"path": "tests/experiment/test_h001_temporal_causality.py", "sha256": "0e1dea2e1ec06cea14f11455402282c56dd5ef598ed54b3ad401774d4d7ea628"},
]
_H001_TEMPORAL_REREVIEW_PR_SCOPE = [
    "docs/control/active_task.json", "docs/control/amendments/candidate1_h001_temporal_causality_v001.json",
    "docs/control/tasks/RECOVER_OR_RETIRE_CANDIDATE1_V0_FROZEN_INPUT/handoff_v016.json",
    "docs/experiments/candidate1_h001_real_data_falsification_temporal_candidate_v001.json",
    "quantbot/continuity/context.py", "quantbot/experiment/h001_temporal_causality.py",
    "tests/continuity/test_cross_agent_continuity.py", "tests/experiment/test_h001_temporal_causality.py",
]
_H001_TEMPORAL_REREVIEW_REPAIR_SCOPE = [
    "docs/control/active_task.json",
    "docs/control/amendments/candidate1_h001_temporal_causality_v001.json",
    "docs/control/tasks/RECOVER_OR_RETIRE_CANDIDATE1_V0_FROZEN_INPUT/handoff_v016.json",
    "quantbot/continuity/context.py", "quantbot/experiment/h001_temporal_causality.py",
    "tests/continuity/test_cross_agent_continuity.py", "tests/experiment/test_h001_temporal_causality.py",
]
_H001_TEMPORAL_REREVIEW_NON_EFFECTS = [
    "AMENDMENT_NOT_EFFECTIVE", "BLOCK_LIVE_INTEGRATION", "CURRENT_H001_CONTRACT_UNCHANGED",
    "CURRENT_SIGNAL_RULE_REMAINS_LTE", "EDGE_UNPROVEN", "NO_ARTIFACT_OR_STORE_ACCESS",
    "NO_CALIBRATION_FREEZE_OR_EXECUTION", "NO_CANARY_EXECUTION", "NO_EXECUTION_COUNT_CONSUMED",
    "NO_H001_EXECUTION", "NO_LIVE_AUTHORITY", "NO_MARKET_EDGE_CLAIM", "NO_PAPER_TRADING_AUTHORITY",
    "NO_REAL_DATA_ACCESS", "NO_SCIENTIFIC_AUTHORITY",
]


def _reject_duplicate_json_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AssuranceValidationError("duplicate JSON key")
        result[key] = value
    return result


def validate_h001_temporal_candidate_rereview_record(raw: bytes) -> dict:
    if type(raw) is not bytes:
        _fail("exact bytes input required")
    try:
        parsed = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_json_keys)
    except (UnicodeDecodeError, json.JSONDecodeError, AssuranceValidationError) as error:
        raise AssuranceValidationError("strict UTF-8 JSON without duplicate keys required") from error
    if canonical_json_bytes(parsed) != raw:
        _fail("non-canonical JSON bytes")
    data = _base(parsed, "qnty_h001_temporal_causality_amendment_candidate_rereview_record", "candidate1-h001-temporal-causality-amendment-candidate-rereview-v001", "RECORDED_AFTER_REVIEW_NOT_PREREGISTERED", _H001_TEMPORAL_REREVIEW_RECORD_KEYS)
    if data["recorded_after_review"] is not True or data["preregistered"] is not False:
        _fail("review record must be recorded after review and not preregistered")
    if data["review_bindings"] != {
        "candidate_base_commit": "30a69ba1ba6a1908888ff1b34bdc072bd030e991", "candidate_merge_commit": "5185add2e5da5add309d2602a473c23557e3c102",
        "final_reviewed_head": "74554e15f92cdb7f6c22238766bd6e1f16b60bf4", "initial_reviewed_head": "9981a466d847305570f7e23826f0c9f40a7446a9", "pr_number": 284,
    }:
        _fail("review binding drifted")
    if data["closed_findings"] != ["PUBLIC_CANDIDATE_LOADER_ACCEPTED_MATERIAL_DOCUMENT_DRIFT", "TEMPORAL_MODULE_AND_TEST_HASHES_WERE_SELF_DERIVED"]:
        _fail("closed findings drifted")
    if data["final_verdict"] != "QNTY_H001_TEMPORAL_CAUSALITY_AMENDMENT_CANDIDATE_REREVIEW_PASSED":
        _fail("final review verdict drifted")
    if data["final_finding_counts"] != {"blocker": 0, "major": 0, "minor": 0}:
        _fail("final finding counts must be zero")
    if data["artifact_bindings"] != _H001_TEMPORAL_REREVIEW_ARTIFACTS:
        _fail("reviewed artifact bindings drifted")
    if data["candidate_review_scope"] != _H001_TEMPORAL_REREVIEW_PR_SCOPE or data["repair_scope"] != _H001_TEMPORAL_REREVIEW_REPAIR_SCOPE:
        _fail("review scope drifted")
    if data["review_results"] != {"assurance": "67 passed", "artifacts": "103 passed", "continuity": "356 passed, 7 skipped", "current_preregistration": "534 passed", "exported_temporal_continuity": "390 passed, 7 skipped", "full_suite": "6286 passed, 7 skipped", "release_smoke": "6 passed", "remote_ci": "ALL_REPORTED_CHECKS_SUCCESS", "sandbox": "53 passed", "temporal": "34 passed"}:
        _fail("review results drifted")
    if data["non_effects"] != _H001_TEMPORAL_REREVIEW_NON_EFFECTS:
        _fail("review non-effects must be sorted and unique")
    for artifact in data["artifact_bindings"]:
        _keys(artifact, {"path", "sha256"}, "artifact binding")
        _sha(artifact["sha256"], "artifact binding sha256")
        _require_repo_relative_review_path(artifact["path"])
    return data


def _require_repo_relative_review_path(path: object) -> str:
    if type(path) is not str or not re.fullmatch(r"[A-Za-z0-9._/-]+", path) or path.startswith("/") or ".." in path.split("/"):
        _fail("unsafe repository-relative review path")
    return path
