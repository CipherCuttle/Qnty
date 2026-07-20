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


_H001_CALIBRATION_REREVIEW_RECORD_KEYS = {
    "artifact_bindings", "candidate_review_scope", "closed_findings", "document_id",
    "document_kind", "final_finding_counts", "final_verdict", "non_effects",
    "preregistered", "recorded_after_review", "repair_scope", "review_bindings",
    "review_history", "review_id", "review_results", "schema_version",
    "semantic_review_results", "status",
}
_H001_CALIBRATION_REREVIEW_ARTIFACTS = [
    {"path": "docs/assurance/h001_synthetic_null_calibration_spec_freeze_candidate_v001.json", "sha256": "04b6ea5b7453fccf4787abb26c230e2a02a77545c741c19f6686df16fc2cb7a2"},
    {"path": "quantbot/assurance/contracts.py", "sha256": "f4a5f783d1ae4276326a2056734377961cec4b5a927487febc91f5aca732a340"},
    {"path": "quantbot/assurance/h001_null_calibration.py", "sha256": "1bddb607041409c991b1f0b609fced17916d6c7c08d311db2706b4734f7e9c34"},
    {"path": "tests/assurance/test_contracts.py", "sha256": "92c4e8dd8bcdf2dbcc6c1b09d8ad4044ac53156e316b160f2e9bd61f2b66d549"},
    {"path": "tests/assurance/test_h001_null_calibration.py", "sha256": "60d0d09236c9e4e49b722fa0402b934e0a799b101ec605608f683cd1137b2e37"},
    {"path": "docs/control/tasks/RECOVER_OR_RETIRE_CANDIDATE1_V0_FROZEN_INPUT/handoff_v020.json", "sha256": "6c9a429d2644b8e6fd9f59ee71585994fb6439ff6451ec41e22cdc7b338969a4"},
    {"path": "docs/control/amendments/candidate1_h001_synthetic_null_calibration_spec_freeze_governance_v001.json", "sha256": "9e633c6bfc551bfc4efd9b8da2d986d018dac1d1c6a70cf96fc39b97adfb72b3"},
    {"path": "docs/assurance/h001_synthetic_null_calibration_spec_draft_v001.json", "sha256": "7e05a0b2b44dd4e3fbadf3e121791eb2ee76385a6b2ec6b872984cbb3510ecf6"},
    {"path": "docs/experiments/candidate1_h001_real_data_falsification_v0.json", "sha256": "c6fb8d796559c53188c10e729a2257bc593c7a80526963c97515f747820e2276"},
    {"path": "quantbot/experiment/h001_real_falsification_preregistration.py", "sha256": "d9326c7b73c68f3958901899f46ef11a4f529ed1954f268de06ae6e8abdcede3"},
    {"path": "docs/control/amendments/candidate1_h001_temporal_causality_activation_v001.json", "sha256": "b60f322650c5b83500b89ad9914b50cd2eb200cbae573670d307b5a72190ee1b"},
]
_H001_CALIBRATION_REREVIEW_PR_SCOPE = [
    "docs/assurance/h001_synthetic_null_calibration_spec_freeze_candidate_v001.json",
    "docs/control/active_task.json",
    "docs/control/tasks/RECOVER_OR_RETIRE_CANDIDATE1_V0_FROZEN_INPUT/handoff_v020.json",
    "quantbot/assurance/contracts.py", "quantbot/assurance/h001_null_calibration.py",
    "quantbot/continuity/context.py", "tests/assurance/test_contracts.py",
    "tests/assurance/test_h001_null_calibration.py", "tests/continuity/test_cross_agent_continuity.py",
]
_H001_CALIBRATION_REREVIEW_REPAIR_SCOPE = [
    "docs/assurance/h001_synthetic_null_calibration_spec_freeze_candidate_v001.json",
    "docs/control/active_task.json",
    "docs/control/tasks/RECOVER_OR_RETIRE_CANDIDATE1_V0_FROZEN_INPUT/handoff_v020.json",
    "quantbot/assurance/contracts.py", "quantbot/continuity/context.py",
    "tests/assurance/test_contracts.py", "tests/continuity/test_cross_agent_continuity.py",
]
_H001_CALIBRATION_REREVIEW_NON_EFFECTS = [
    "SPECIFICATION_NOT_EFFECTIVE", "SPECIFICATION_REMAINS_UNFROZEN", "CALIBRATION_EXECUTION_NOT_AUTHORIZED",
    "CALIBRATION_NOT_EXECUTED", "NO_CALIBRATION_RESULTS", "NO_REAL_DATA_ACCESS", "NO_ARTIFACT_OR_STORE_ACCESS",
    "NO_EXECUTION_COUNT_CONSUMED", "NO_SCIENTIFIC_AUTHORITY", "NO_PAPER_TRADING_AUTHORITY", "NO_LIVE_AUTHORITY",
    "EDGE_UNPROVEN", "BLOCK_LIVE_INTEGRATION", "REVIEW_RESULTS_NOT_MARKET_EVIDENCE",
    "REVIEW_RESULTS_NOT_CALIBRATION_EVIDENCE",
]
_H001_CALIBRATION_REREVIEW_RESULTS = {
    "assurance": "200 passed", "focused_continuity": "526 passed, 12 skipped", "continuity": "526 passed, 12 skipped",
    "sandbox": "53 passed", "artifacts": "103 passed", "temporal": "34 passed", "current_preregistration": "538 passed",
    "full_suite": "6593 passed, 12 skipped", "release_smoke": "6 passed", "exported_assurance_continuity": "726 passed, 12 skipped",
    "semantic_mutation_probes": "27/27 rejected", "remote_ci": "ALL_REPORTED_CHECKS_SUCCESS",
}
_H001_CALIBRATION_REREVIEW_SEMANTICS = {
    "sample_boundary_review": "PASSED",
    "garch_review": "PASSED_WITH_EXPLICIT_DETERMINISTIC_BURN_IN_APPROXIMATION",
    "rng_substream_review": "PASSED", "exact_semantics_review": "PASSED", "harness_fail_closed_review": "PASSED",
}
_H001_CALIBRATION_REREVIEW_CLOSED_FINDINGS = [
    "DGP_STRESS_AND_SAMPLE_SEMANTICS_NOT_VALIDATED_EXACTLY",
    "GARCH_INITIALIZATION_NOT_FULLY_PINNED",
    "SAMPLE_LENGTH_ENDPOINT_CONVENTION_AMBIGUOUS",
    "RNG_COMPONENT_SUBSTREAMS_AND_DRAW_ORDER_UNDER_SPECIFIED",
]
_H001_CALIBRATION_REREVIEW_HISTORICAL_FINDINGS = [
    {"finding_id": "DGP_STRESS_AND_SAMPLE_SEMANTICS_NOT_VALIDATED_EXACTLY", "severity": "BLOCKER"},
    {"finding_id": "GARCH_INITIALIZATION_NOT_FULLY_PINNED", "severity": "MAJOR"},
    {"finding_id": "SAMPLE_LENGTH_ENDPOINT_CONVENTION_AMBIGUOUS", "severity": "MAJOR"},
    {"finding_id": "RNG_COMPONENT_SUBSTREAMS_AND_DRAW_ORDER_UNDER_SPECIFIED", "severity": "MAJOR"},
]
_H001_CALIBRATION_REREVIEW_HISTORY = [
    {
        "reviewed_head": "806b230bedeff32f7f84ad4b7127c606de74686f",
        "verdict": "QNTY_H001_SYNTHETIC_NULL_CALIBRATION_SPEC_FREEZE_CANDIDATE_REREVIEW_FAILED",
        "finding_counts": {"blocker": 1, "major": 3, "minor": 0},
        "findings": _H001_CALIBRATION_REREVIEW_HISTORICAL_FINDINGS,
        "historical": True,
    },
    {
        "reviewed_head": "d79f8908d55e8dd9d5f33b9f174e01d8796e02fe",
        "verdict": "QNTY_H001_SYNTHETIC_NULL_CALIBRATION_SPEC_FREEZE_CANDIDATE_REPAIRED_REREVIEW_PASSED",
        "finding_counts": {"blocker": 0, "major": 0, "minor": 0},
        "findings": [],
        "historical": False,
    },
]


def validate_h001_synthetic_null_calibration_spec_freeze_candidate_rereview_record(value: object) -> dict:
    """Validate the H001 freeze-candidate rereview as metadata only."""
    data = _base(
        value,
        "qnty_h001_synthetic_null_calibration_spec_freeze_candidate_rereview_record",
        "h001-synthetic-null-calibration-spec-freeze-candidate-repaired-rereview-v001",
        "RECORDED_AFTER_REVIEW_NOT_EFFECTIVE_NOT_EXECUTABLE",
        _H001_CALIBRATION_REREVIEW_RECORD_KEYS,
    )
    if data["recorded_after_review"] is not True or data["preregistered"] is not False:
        _fail("H001 calibration rereview record status drifted")
    if data["final_verdict"] != "QNTY_H001_SYNTHETIC_NULL_CALIBRATION_SPEC_FREEZE_CANDIDATE_REPAIRED_REREVIEW_PASSED":
        _fail("H001 calibration rereview final verdict drifted")
    if data["final_finding_counts"] != {"blocker": 0, "major": 0, "minor": 0}:
        _fail("H001 calibration rereview final findings must be zero")
    if data["review_bindings"] != {
        "pr_number": 288,
        "candidate_base_commit": "6465d036af6b66ae6d845511c652d5857651bc49",
        "initial_failed_reviewed_head": "806b230bedeff32f7f84ad4b7127c606de74686f",
        "repair_commit": "d79f8908d55e8dd9d5f33b9f174e01d8796e02fe",
        "final_reviewed_head": "d79f8908d55e8dd9d5f33b9f174e01d8796e02fe",
        "candidate_merge_commit": "841ae1b43ca69e8290311b7c0fb6f803513a7df5",
    }:
        _fail("H001 calibration rereview PR bindings drifted")
    if data["artifact_bindings"] != _H001_CALIBRATION_REREVIEW_ARTIFACTS:
        _fail("H001 calibration rereview immutable bindings drifted")
    if data["candidate_review_scope"] != _H001_CALIBRATION_REREVIEW_PR_SCOPE or data["repair_scope"] != _H001_CALIBRATION_REREVIEW_REPAIR_SCOPE:
        _fail("H001 calibration rereview scope drifted")
    if data["closed_findings"] != _H001_CALIBRATION_REREVIEW_CLOSED_FINDINGS:
        _fail("H001 calibration rereview closed findings drifted")
    failed_review, passing_review = data["review_history"]
    if failed_review["finding_counts"] != {"blocker": 1, "major": 3, "minor": 0}:
        _fail("H001 calibration historical finding counts drifted")
    if failed_review["findings"] != _H001_CALIBRATION_REREVIEW_HISTORICAL_FINDINGS:
        _fail("H001 calibration historical finding severities drifted")
    if passing_review["finding_counts"] != {"blocker": 0, "major": 0, "minor": 0} or passing_review["findings"] != []:
        _fail("H001 calibration passing review findings drifted")
    if data["review_history"] != _H001_CALIBRATION_REREVIEW_HISTORY:
        _fail("H001 calibration rereview history drifted")
    if data["review_results"] != _H001_CALIBRATION_REREVIEW_RESULTS or data["semantic_review_results"] != _H001_CALIBRATION_REREVIEW_SEMANTICS:
        _fail("H001 calibration rereview results drifted")
    if data["non_effects"] != _H001_CALIBRATION_REREVIEW_NON_EFFECTS:
        _fail("H001 calibration rereview non-effects drifted")
    for binding in data["artifact_bindings"]:
        _keys(binding, {"path", "sha256"}, "H001 calibration rereview artifact binding")
        _require_repo_relative_review_path(binding["path"])
        _sha(binding["sha256"], "H001 calibration rereview artifact sha256")
    return data


def load_and_validate_h001_synthetic_null_calibration_spec_freeze_candidate_rereview_record(raw: bytes) -> dict:
    """Strict UTF-8, duplicate-key rejecting, canonical byte-level loader."""
    if type(raw) is not bytes:
        _fail("exact bytes input required")
    try:
        parsed = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_json_keys)
    except (UnicodeDecodeError, json.JSONDecodeError, AssuranceValidationError) as error:
        raise AssuranceValidationError("strict UTF-8 JSON without duplicate keys required") from error
    if canonical_json_bytes(parsed) != raw:
        _fail("non-canonical JSON bytes")
    return validate_h001_synthetic_null_calibration_spec_freeze_candidate_rereview_record(parsed)


def _require_repo_relative_review_path(path: object) -> str:
    if type(path) is not str or not re.fullmatch(r"[A-Za-z0-9._/-]+", path) or path.startswith("/") or ".." in path.split("/"):
        _fail("unsafe repository-relative review path")
    return path


# --- H001 synthetic-null calibration specification freeze candidate ----------
#
# The freeze candidate is a review artifact only. Validation here is strictly
# metadata-only: it inspects the supplied document and nothing else. It performs
# no filesystem discovery, no networking, no artifact-store or quarantine
# access, no environment reads, no simulation, no bootstrap, and it never
# produces a calibration result. `H001_DESIGN_SHA256` / `H001_VALIDATOR_SHA256`
# above are the *historical* pre-activation hashes carried by the historical
# draft; the freeze candidate must bind the activated hashes below instead, and
# presenting either historical hash as a current binding is rejected.
H001_ACTIVATED_DESIGN_SHA256 = "c6fb8d796559c53188c10e729a2257bc593c7a80526963c97515f747820e2276"
H001_ACTIVATED_VALIDATOR_SHA256 = "d9326c7b73c68f3958901899f46ef11a4f529ed1954f268de06ae6e8abdcede3"
H001_FREEZE_GOVERNANCE_AMENDMENT_SHA256 = "9e633c6bfc551bfc4efd9b8da2d986d018dac1d1c6a70cf96fc39b97adfb72b3"
H001_FREEZE_CANDIDATE_SOURCE_MAIN = "6465d036af6b66ae6d845511c652d5857651bc49"
H001_FREEZE_CANDIDATE_PREDECESSOR_SHA256 = "5f210c26c6c7f0b16f1df49173cae22e878071fe46d9933941d639aa37f6d59e"
H001_HISTORICAL_CALIBRATION_DRAFT_SHA256 = "7e05a0b2b44dd4e3fbadf3e121791eb2ee76385a6b2ec6b872984cbb3510ecf6"
H001_FREEZE_CANDIDATE_DOCUMENT_ID = "h001-synthetic-null-calibration-spec-freeze-candidate-v001"
H001_FREEZE_CANDIDATE_DOCUMENT_KIND = "qnty_h001_synthetic_null_calibration_spec_freeze_candidate"
H001_FREEZE_CANDIDATE_STATUS = "FREEZE_CANDIDATE_FOR_INDEPENDENT_REVIEW_NOT_EFFECTIVE_NOT_EXECUTABLE"
H001_FREEZE_CANDIDATE_SEED_DOMAIN = "h001-null-calibration/h001-synthetic-null-calibration-spec-freeze-candidate-v001/synthetic-only"

_FREEZE_CANDIDATE_KEYS = {
    "authorization_state", "bindings", "diagnostic_case_policy", "diagnostic_stress_cases", "document_id",
    "document_kind", "edge_status", "governed_h001_protocol_id", "historical_draft", "live_status",
    "locked_for_review_meaning", "non_effects", "pass_criterion", "registered_test_target",
    "required_stationary_dgps", "schema_version", "seed_contract", "status", "synthetic_sample_contract",
}
# Exactly the two claims a review candidate may assert, and every authority it
# must continue to deny. Anything true in the second group is a fail-closed
# authorization drift, not a reviewable difference of opinion.
_FREEZE_CANDIDATE_AUTHORIZED_TRUE = ("candidate_values_locked_for_review", "independent_review_required")
_FREEZE_CANDIDATE_AUTHORIZED_FALSE = (
    "execution_authorized", "h001_holdout_execution_authorized", "h001_validation_execution_authorized",
    "live_authorization", "paper_trade_authorization", "real_data_access_authorized", "results_exposed",
    "scientific_authorization", "specification_effective", "specification_frozen_effective",
)
_FREEZE_CANDIDATE_BINDINGS = {
    "governance_amendment": ("docs/control/amendments/candidate1_h001_synthetic_null_calibration_spec_freeze_governance_v001.json", H001_FREEZE_GOVERNANCE_AMENDMENT_SHA256),
    "source_handoff": ("docs/control/tasks/RECOVER_OR_RETIRE_CANDIDATE1_V0_FROZEN_INPUT/handoff_v019.json", H001_FREEZE_CANDIDATE_PREDECESSOR_SHA256),
    "activated_design": ("docs/experiments/candidate1_h001_real_data_falsification_v0.json", H001_ACTIVATED_DESIGN_SHA256),
    "activated_validator": ("quantbot/experiment/h001_real_falsification_preregistration.py", H001_ACTIVATED_VALIDATOR_SHA256),
    "temporal_activation_amendment": ("docs/control/amendments/candidate1_h001_temporal_causality_activation_v001.json", "b60f322650c5b83500b89ad9914b50cd2eb200cbae573670d307b5a72190ee1b"),
}
_FREEZE_CANDIDATE_TEST_TARGET = {
    "registered_variant_series": 9,
    "test_target": "exact registered synchronous stationary-bootstrap maximum-t procedure",
    "inner_procedure": "synchronous stationary-bootstrap maximum-t",
    "bootstrap_repetitions": 10000,
    "outer_synthetic_replications": 2000,
    "stationary_block_length": 63,
    "hac_lag": 21,
    "familywise_alpha": 0.05,
    "variant_family_unchanged": True,
    "selection_rule_unchanged": True,
}
_FREEZE_CANDIDATE_PASS_CRITERION = {
    "statement": "for every required stationary DGP, the one-sided 95% exact binomial upper confidence bound for empirical FWER is <= 0.075",
    "binomial_interval_method": "one-sided exact Clopper-Pearson upper bound",
    "binomial_interval_is_exact": True,
    "binomial_confidence_level": 0.95,
    "fwer_upper_bound_threshold": 0.075,
    "fwer_event_definition": "at least one of the nine null series is rejected by the exact registered familywise validation test at alpha 0.05",
    "empirical_fwer_definition": "the number of outer replications containing an FWER event divided by 2000",
    "applies_to": "every required stationary DGP",
    "diagnostic_cases_participate": False,
}
_FREEZE_CANDIDATE_SEED_CONTRACT = {
    "seed_domain": H001_FREEZE_CANDIDATE_SEED_DOMAIN,
    "payload_encoding": "UTF-8",
    "outer_index_base": 0,
    "outer_payload_rule": 'seed_domain + ":" + dgp_id + ":outer:" + zero-based outer replication index',
    "bootstrap_payload_rule": 'seed_domain + ":" + dgp_id + ":outer:" + zero-based outer replication index + ":bootstrap"',
    "digest_algorithm": "SHA-256",
    "seed_integer_rule": "the integer represented by the first 16 lowercase hexadecimal characters of the SHA-256 digest",
    "seed_integer_bits": 64,
    "rng_algorithm": "numpy.random.Philox",
    "rng_wrapper": "numpy.random.Generator",
    "rng_dependency": "numpy",
    "rng_dependency_already_available": True,
    "new_or_updated_dependencies": False,
    "wall_clock_seeds_allowed": False,
    "os_entropy_allowed": False,
    "random_fallback_allowed": False,
    "retry_dependent_seeds_allowed": False,
    "environment_dependent_seeds_allowed": False,
    "result_dependent_reseeding_allowed": False,
}
_FREEZE_CANDIDATE_NONDETERMINISM_FLAGS = (
    "environment_dependent_seeds_allowed", "os_entropy_allowed", "random_fallback_allowed",
    "result_dependent_reseeding_allowed", "retry_dependent_seeds_allowed", "wall_clock_seeds_allowed",
)
_FREEZE_CANDIDATE_EXPECTED_SECTION_SHA256 = {
    "synthetic_sample_contract": "16ff3a433e14fdb9385621f6b8427f2e660b91ba92c712de5b99a798f48c965b",
    "seed_contract": "39c4d3126e711e0b8e5e92e8763f9e6bbbf5c1fabcdd90454ba65a59e0bcb7e2",
    "required_stationary_dgps": "cc56a8cffa3803fbfba132bc04aa391276e248b01f7633b3e02d62bb4be1b0b4",
    "diagnostic_stress_cases": "297ea1fcd79c70ee4074923bf25817138b3b4ae25a8fa195446c7c95d378c642",
    "diagnostic_case_policy": "aaa2815590d27e870f17de0176e550e3e1d795eafdc18ec32ec645d010d67f42",
}
_FREEZE_CANDIDATE_SAMPLE_CONTRACT = {
    "sample_length_intervals": 2193,
    "series_count": 9,
    "cadence": "8h",
    "registered_validation_start_utc": "2023-01-01T00:00:00Z",
    "registered_validation_end_utc": "2024-12-31T23:59:59Z",
    "theoretical_mean_zero_required": True,
    "synthetic_only": True,
    "real_data_used": False,
}
_FREEZE_CANDIDATE_DGP_KEYS = {
    "burn_in_intervals", "cross_series_dependence", "definition", "dgp_id", "discarded_observations",
    "factor_loading", "finite_value_requirement", "initial_state_distribution", "innovation_distribution",
    "output_shape_and_ordering", "parameters", "role", "theoretical_mean", "theoretical_mean_zero",
    "variance_normalization",
}
# Exact, executable-later parameters. Every value is fixed by this contract, so
# no discretionary parameter survives into a later execution authorization.
_FREEZE_CANDIDATE_DGP_PARAMETERS = {
    "iid_gaussian": {"mean": 0.0, "variance": 1.0},
    "iid_student_t_df5_standardized": {"degrees_of_freedom": 5, "scale_factor": "sqrt(3/5)", "standardized_variance": 1.0},
    "nine_series_common_factor_dependence": {"common_factor_loading": "sqrt(0.5)", "idiosyncratic_loading": "sqrt(0.5)", "implied_pairwise_correlation": 0.5},
    "stationary_ar1_phi_0p3": {"phi": 0.3, "innovation_variance": 0.91, "stationary_variance": 1.0},
    "stationary_ar1_phi_0p7": {"phi": 0.7, "innovation_variance": 0.51, "stationary_variance": 1.0},
    "stationary_garch11_like": {"omega": 0.05, "alpha": 0.05, "beta": 0.9, "initial_conditional_variance": 1.0, "unconditional_variance": 1.0, "persistence": 0.95},
}
_FREEZE_CANDIDATE_STRESS_KEYS = {
    "authorized_for_tuning", "case_id", "definition", "finite_value_requirement", "initial_state_distribution",
    "nine_series_construction", "output_shape_and_ordering", "parameters", "part_of_formal_pass_fail", "role",
    "seed_use", "theoretical_mean", "theoretical_mean_zero",
}
_FREEZE_CANDIDATE_STRESS_PARAMETERS = {
    "autocorrelation_structural_break": {"phi_before_transition": 0.0, "phi_after_transition": 0.8, "transition_interval_index": 1097, "innovation_variance_before_transition": 1.0, "innovation_variance_after_transition": 0.36},
    "mean_zero_regime_switching": {"low_state_variance": 0.25, "high_state_variance": 4.0, "transition_probability_low_to_high": 0.02, "transition_probability_high_to_low": 0.02, "initial_state_probability_low": 0.5, "initial_state_probability_high": 0.5},
    "sparse_extreme_outliers": {"outlier_probability": 0.002, "outlier_magnitude": 10.0, "outlier_sign_rule": "+1 with probability 0.5 and -1 with probability 0.5, independently of the base series", "base_distribution": "N(0,1)", "contamination_replaces_base_value": True},
    "variance_structural_break": {"variance_before_transition": 1.0, "variance_after_transition": 9.0, "transition_interval_index": 1097},
}
_FREEZE_CANDIDATE_TUNING_LOCKS = [
    "DGP_PARAMETERS", "FAMILYWISE_ALPHA", "HAC_LAG", "PASS_THRESHOLD", "SELECTION_RULE",
    "STATIONARY_BLOCK_LENGTH", "TEST_STATISTIC", "VARIANT_FAMILY",
]
_FREEZE_CANDIDATE_NON_EFFECTS = [
    "BLOCK_LIVE_INTEGRATION", "CALIBRATION_NOT_EXECUTED", "CANDIDATE_NOT_EFFECTIVE",
    "DIAGNOSTIC_CASES_EXCLUDED_FROM_PASS_FAIL", "EDGE_UNPROVEN",
    "HISTORICAL_DRAFT_REMAINS_HISTORICAL_AND_UNFROZEN", "INDEPENDENT_REVIEW_REQUIRED",
    "NO_CALIBRATION_RESULTS_GENERATED", "NO_EXECUTION_COUNT_CONSUMED", "NO_LIVE_AUTHORITY",
    "NO_MARKET_EDGE_CLAIM", "NO_PAPER_TRADING_AUTHORITY", "NO_REAL_DATA_ACCESS",
    "NO_SCIENTIFIC_AUTHORITY", "NO_STORE_OR_QUARANTINE_ACCESS", "REGISTERED_H001_DESIGN_UNCHANGED",
    "REGISTERED_VARIANT_FAMILY_UNCHANGED",
]
# A definition short enough to be a bare label is rejected outright; the freeze
# candidate may not carry label-only DGPs the way the historical draft does.
_FREEZE_CANDIDATE_MIN_DEFINITION_CHARS = 120
_FREEZE_CANDIDATE_FORBIDDEN_SEED_TOKENS = (
    "wall clock", "wall-clock", "time.time", "datetime.now", "os.urandom", "entropy", "getrandbits",
    "secrets.", "unseeded", "system time", "nondeterministic", "retry", "reseed",
)


def _require_exact_bool(value: object, expected: bool, label: str) -> None:
    if value is not True and value is not False:
        _fail(f"{label}: explicit boolean required")
    if value is not expected:
        _fail(f"{label}: must be {str(expected).lower()}")


def _freeze_candidate_binding(value: object, key: str) -> None:
    binding = _keys(value, {"path", "sha256"}, f"freeze candidate {key} binding")
    _require_repo_relative_review_path(binding["path"])
    _sha(binding["sha256"], f"freeze candidate {key} sha256")
    if key in ("activated_design", "activated_validator") and binding["sha256"] in (H001_DESIGN_SHA256, H001_VALIDATOR_SHA256):
        _fail(f"freeze candidate {key}: historical pre-activation hash presented as the current activated hash")
    if (binding["path"], binding["sha256"]) != _FREEZE_CANDIDATE_BINDINGS[key]:
        _fail(f"freeze candidate {key} binding is wrong")


def _validate_freeze_candidate_historical_draft(value: object) -> None:
    keys = {
        "is_current", "is_effective", "is_executable", "is_frozen", "observation",
        "obsolete_pre_activation_design_sha256", "obsolete_pre_activation_validator_sha256", "path",
        "preserved_unmodified", "remains_historical", "sha256", "status",
    }
    draft = _keys(value, keys, "freeze candidate historical draft")
    if draft["path"] != "docs/assurance/h001_synthetic_null_calibration_spec_draft_v001.json" or draft["sha256"] != H001_HISTORICAL_CALIBRATION_DRAFT_SHA256:
        _fail("freeze candidate historical draft binding is wrong")
    if draft["status"] != "DRAFT_ONLY_UNFROZEN_NOT_EXECUTABLE":
        _fail("freeze candidate historical draft status drifted")
    for key in ("is_current", "is_effective", "is_executable", "is_frozen"):
        _require_exact_bool(draft[key], False, f"historical draft {key}")
    for key in ("preserved_unmodified", "remains_historical"):
        _require_exact_bool(draft[key], True, f"historical draft {key}")
    if draft["obsolete_pre_activation_design_sha256"] != H001_DESIGN_SHA256 or draft["obsolete_pre_activation_validator_sha256"] != H001_VALIDATOR_SHA256:
        _fail("freeze candidate historical draft obsolete hashes drifted")
    if draft["obsolete_pre_activation_design_sha256"] == H001_ACTIVATED_DESIGN_SHA256 or draft["obsolete_pre_activation_validator_sha256"] == H001_ACTIVATED_VALIDATOR_SHA256:
        _fail("freeze candidate historical draft claims the activated hashes as its own bindings")
    for marker in ("historical", "unfrozen", "ineffective", "non-executable", "obsolete"):
        if marker not in _str(draft["observation"], "historical draft observation"):
            _fail("freeze candidate historical draft observation is incomplete")


def _validate_freeze_candidate_seed_contract(value: object) -> None:
    if hashlib.sha256(canonical_json_bytes(value)).hexdigest() != _FREEZE_CANDIDATE_EXPECTED_SECTION_SHA256["seed_contract"]:
        _fail("freeze candidate seed derivation contract is not the exact frozen structure")


def _validate_freeze_candidate_dgps(value: object) -> list[str]:
    if hashlib.sha256(canonical_json_bytes(value)).hexdigest() != _FREEZE_CANDIDATE_EXPECTED_SECTION_SHA256["required_stationary_dgps"]:
        _fail("required_stationary_dgps is not the exact frozen structure")
    return [entry["dgp_id"] for entry in value]


def _validate_freeze_candidate_stress_cases(value: object, dgp_ids: list[str]) -> None:
    if hashlib.sha256(canonical_json_bytes(value)).hexdigest() != _FREEZE_CANDIDATE_EXPECTED_SECTION_SHA256["diagnostic_stress_cases"]:
        _fail("diagnostic_stress_cases is not the exact frozen structure")
    if any(entry["case_id"] in dgp_ids for entry in value):
        _fail("diagnostic stress case included in the formal pass/fail DGP suite")


def validate_calibration_spec_freeze_candidate(value: object) -> dict:
    """Validate the H001 null-calibration freeze candidate, metadata only.

    Accepts a parsed document. `load_and_validate_calibration_spec_freeze_candidate`
    is the byte-level entry point that additionally rejects duplicate JSON keys
    and non-canonical bytes. Nothing here reads the filesystem, the network, any
    artifact store, or any environment value, and nothing here executes, tunes,
    or reports a calibration.
    """
    data = _base(value, H001_FREEZE_CANDIDATE_DOCUMENT_KIND, H001_FREEZE_CANDIDATE_DOCUMENT_ID, H001_FREEZE_CANDIDATE_STATUS, _FREEZE_CANDIDATE_KEYS)
    if data["governed_h001_protocol_id"] != H001_PROTOCOL_ID:
        _fail("freeze candidate governed protocol drifted")
    if data["edge_status"] != "EDGE_UNPROVEN" or data["live_status"] != "BLOCK_LIVE_INTEGRATION":
        _fail("freeze candidate safety status drifted")
    if "EDGE_PROVEN" in canonical_json_bytes(data).decode("ascii"):
        _fail("freeze candidate asserts EDGE_PROVEN")

    auth = _keys(data["authorization_state"], set(_FREEZE_CANDIDATE_AUTHORIZED_TRUE) | set(_FREEZE_CANDIDATE_AUTHORIZED_FALSE), "freeze candidate authorization_state")
    for key in _FREEZE_CANDIDATE_AUTHORIZED_TRUE:
        _require_exact_bool(auth[key], True, f"authorization_state {key}")
    for key in _FREEZE_CANDIDATE_AUTHORIZED_FALSE:
        _require_exact_bool(auth[key], False, f"authorization_state {key}")
    meaning = _str(data["locked_for_review_meaning"], "locked_for_review_meaning")
    if "does not mean" not in meaning or "effective" not in meaning:
        _fail("freeze candidate must state that locking values for review does not make the specification effective")

    bindings = _keys(data["bindings"], set(_FREEZE_CANDIDATE_BINDINGS) | {"source_main_commit"}, "freeze candidate bindings")
    if type(bindings["source_main_commit"]) is not str or not re.fullmatch(r"[0-9a-f]{40}", bindings["source_main_commit"]):
        _fail("freeze candidate source_main_commit: lowercase commit sha required")
    if bindings["source_main_commit"] != H001_FREEZE_CANDIDATE_SOURCE_MAIN:
        _fail("freeze candidate source main commit is wrong")
    for key in _FREEZE_CANDIDATE_BINDINGS:
        _freeze_candidate_binding(bindings[key], key)
    _validate_freeze_candidate_historical_draft(data["historical_draft"])

    target = _keys(data["registered_test_target"], set(_FREEZE_CANDIDATE_TEST_TARGET), "freeze candidate registered_test_target")
    for key, expected in _FREEZE_CANDIDATE_TEST_TARGET.items():
        if target[key] != expected or type(target[key]) is not type(expected):
            _fail(f"registered_test_target {key} is wrong")
    criterion = _keys(data["pass_criterion"], set(_FREEZE_CANDIDATE_PASS_CRITERION), "freeze candidate pass_criterion")
    _require_exact_bool(criterion["binomial_interval_is_exact"], True, "pass_criterion binomial_interval_is_exact")
    _require_exact_bool(criterion["diagnostic_cases_participate"], False, "pass_criterion diagnostic_cases_participate")
    for key, expected in _FREEZE_CANDIDATE_PASS_CRITERION.items():
        if criterion[key] != expected or type(criterion[key]) is not type(expected):
            _fail(f"pass_criterion {key} is wrong or the interval method is ambiguous")

    _validate_freeze_candidate_seed_contract(data["seed_contract"])
    if hashlib.sha256(canonical_json_bytes(data["synthetic_sample_contract"])).hexdigest() != _FREEZE_CANDIDATE_EXPECTED_SECTION_SHA256["synthetic_sample_contract"]:
        _fail("synthetic_sample_contract is not the exact frozen structure")

    dgp_ids = _validate_freeze_candidate_dgps(data["required_stationary_dgps"])
    _validate_freeze_candidate_stress_cases(data["diagnostic_stress_cases"], dgp_ids)
    if hashlib.sha256(canonical_json_bytes(data["diagnostic_case_policy"])).hexdigest() != _FREEZE_CANDIDATE_EXPECTED_SECTION_SHA256["diagnostic_case_policy"]:
        _fail("diagnostic_case_policy is not the exact frozen structure")
    if _list(data["non_effects"], "non_effects", sorted_unique=True) != _FREEZE_CANDIDATE_NON_EFFECTS:
        _fail("freeze candidate non-effects drifted")
    return data


def load_and_validate_calibration_spec_freeze_candidate(raw: bytes) -> dict:
    """Byte-level freeze-candidate entry point: strict UTF-8, no duplicate JSON
    keys, canonical bytes, then the full metadata-only validation above."""
    if type(raw) is not bytes:
        _fail("exact bytes input required")
    try:
        parsed = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_json_keys)
    except (UnicodeDecodeError, json.JSONDecodeError, AssuranceValidationError) as error:
        raise AssuranceValidationError("strict UTF-8 JSON without duplicate keys required") from error
    if canonical_json_bytes(parsed) != raw:
        _fail("non-canonical JSON bytes")
    return validate_calibration_spec_freeze_candidate(parsed)


# --- H001 synthetic-null calibration specification freeze activation ---------
#
# This amendment changes only the governed effective status of the immutable
# review candidate. It does not copy, rewrite, or execute that candidate.
H001_CALIBRATION_ACTIVATION_AMENDMENT_ID = "candidate1-h001-synthetic-null-calibration-spec-freeze-activation-v001"
H001_CALIBRATION_ACTIVATION_AMENDMENT_KIND = "qnty_h001_synthetic_null_calibration_spec_freeze_activation_amendment"
H001_CALIBRATION_ACTIVATION_STATUS = "ACTIVATED_AFTER_INDEPENDENT_REVIEW"
H001_CALIBRATION_ACTIVATION_BASE_MAIN_COMMIT = "8b4548ac556a4260926cab7e2cb387040e396487"
H001_CALIBRATION_EFFECTIVE_SPECIFICATION_SHA256 = "04b6ea5b7453fccf4787abb26c230e2a02a77545c741c19f6686df16fc2cb7a2"
H001_CALIBRATION_REREVIEW_RECORD_SHA256 = "8614fa4b1c49fc665107c42ec900d9c998562dff236333a9dcdd38628a341fe0"
H001_CALIBRATION_V021_SHA256 = "1ed0282d4ffbe90cf5d8c56988745ef2359105bef1e76424381fa5d99b183b8b"
H001_CALIBRATION_ACTIVATION_GOVERNANCE_SHA256 = "9e633c6bfc551bfc4efd9b8da2d986d018dac1d1c6a70cf96fc39b97adfb72b3"
H001_CALIBRATION_ACTIVATED_DESIGN_SHA256 = "c6fb8d796559c53188c10e729a2257bc593c7a80526963c97515f747820e2276"
H001_CALIBRATION_ACTIVATED_VALIDATOR_SHA256 = "d9326c7b73c68f3958901899f46ef11a4f529ed1954f268de06ae6e8abdcede3"
H001_CALIBRATION_TEMPORAL_ACTIVATION_SHA256 = "b60f322650c5b83500b89ad9914b50cd2eb200cbae573670d307b5a72190ee1b"

_H001_CALIBRATION_ACTIVATION_KEYS = {
    "amendment_id", "amendment_kind", "authorization_state", "base_main_commit",
    "candidate_review_completed", "candidate_review_recorded", "effective",
    "document_id", "document_kind", "effective_specification", "frozen_values",
    "governed_h001_protocol_id", "hash_bindings", "non_effects", "review_history",
    "schema_version", "status",
}
_H001_CALIBRATION_ACTIVATION_AUTH_KEYS = {
    "execution_authorized", "execution_implementation_authorized", "h001_holdout_execution_authorized",
    "h001_validation_execution_authorized", "live_authorization", "paper_trade_authorization",
    "real_data_access_authorized", "results_exposed", "scientific_authorization",
    "specification_effective", "specification_frozen_effective",
}
_H001_CALIBRATION_ACTIVATION_HASH_BINDINGS = {
    "effective_specification": (
        "docs/assurance/h001_synthetic_null_calibration_spec_freeze_candidate_v001.json",
        H001_CALIBRATION_EFFECTIVE_SPECIFICATION_SHA256,
    ),
    "candidate_rereview_record": (
        "docs/assurance/reviews/h001_synthetic_null_calibration_spec_freeze_candidate_rereview_record_v001.json",
        H001_CALIBRATION_REREVIEW_RECORD_SHA256,
    ),
    "handoff_v021": (
        "docs/control/tasks/RECOVER_OR_RETIRE_CANDIDATE1_V0_FROZEN_INPUT/handoff_v021.json",
        H001_CALIBRATION_V021_SHA256,
    ),
    "freeze_governance_amendment": (
        "docs/control/amendments/candidate1_h001_synthetic_null_calibration_spec_freeze_governance_v001.json",
        H001_CALIBRATION_ACTIVATION_GOVERNANCE_SHA256,
    ),
    "historical_calibration_draft": (
        "docs/assurance/h001_synthetic_null_calibration_spec_draft_v001.json",
        H001_HISTORICAL_CALIBRATION_DRAFT_SHA256,
    ),
    "activated_h001_design": (
        "docs/experiments/candidate1_h001_real_data_falsification_v0.json",
        H001_CALIBRATION_ACTIVATED_DESIGN_SHA256,
    ),
    "activated_h001_validator": (
        "quantbot/experiment/h001_real_falsification_preregistration.py",
        H001_CALIBRATION_ACTIVATED_VALIDATOR_SHA256,
    ),
    "temporal_activation_amendment": (
        "docs/control/amendments/candidate1_h001_temporal_causality_activation_v001.json",
        H001_CALIBRATION_TEMPORAL_ACTIVATION_SHA256,
    ),
}
_H001_CALIBRATION_ACTIVATION_REVIEW_HISTORY = {
    "candidate_base_commit": "6465d036af6b66ae6d845511c652d5857651bc49",
    "candidate_failed_reviewed_head": "806b230bedeff32f7f84ad4b7127c606de74686f",
    "candidate_final_reviewed_head": "d79f8908d55e8dd9d5f33b9f174e01d8796e02fe",
    "candidate_merge_commit": "841ae1b43ca69e8290311b7c0fb6f803513a7df5",
    "candidate_pr_number": 288,
    "review_record_final_reviewed_head": "276b0e0dad49a7c10517d01f7fd9aebd4947050b",
    "review_record_merge_commit": "8b4548ac556a4260926cab7e2cb387040e396487",
    "review_record_pr_number": 289,
}
_H001_CALIBRATION_ACTIVATION_FROZEN_VALUES = {
    "bootstrap_repetitions": 10000,
    "familywise_alpha": 0.05,
    "fwer_upper_bound_threshold": 0.075,
    "hac_lag": 21,
    "outer_synthetic_replications": 2000,
    "registered_variant_series": 9,
    "rng": "numpy.random.Generator using numpy.random.Philox",
    "sample_length_intervals": 2193,
    "stationary_block_length": 63,
    "binomial_method": "one-sided exact Clopper-Pearson upper bound",
}
_H001_CALIBRATION_ACTIVATION_NON_EFFECTS = [
    "CALIBRATION_EXECUTION_NOT_AUTHORIZED",
    "CALIBRATION_EXECUTION_IMPLEMENTATION_NOT_AUTHORIZED",
    "CALIBRATION_NOT_EXECUTED",
    "NO_CALIBRATION_RESULTS",
    "NO_REAL_DATA_ACCESS",
    "NO_ARTIFACT_OR_STORE_ACCESS",
    "NO_EXECUTION_COUNT_CONSUMED",
    "NO_H001_VALIDATION_EXECUTION",
    "NO_H001_HOLDOUT_EXECUTION",
    "NO_SCIENTIFIC_AUTHORITY",
    "NO_PAPER_TRADING_AUTHORITY",
    "NO_LIVE_AUTHORITY",
    "REVIEW_RESULTS_NOT_CALIBRATION_RESULTS",
    "CALIBRATION_RESULTS_NOT_MARKET_EVIDENCE",
    "EDGE_UNPROVEN",
    "BLOCK_LIVE_INTEGRATION",
]


def _validate_activation_hash_binding(value: object, key: str) -> None:
    binding = _keys(value, {"path", "sha256"}, f"H001 activation {key} binding")
    _require_repo_relative_review_path(binding["path"])
    _sha(binding["sha256"], f"H001 activation {key} sha256")
    if (binding["path"], binding["sha256"]) != _H001_CALIBRATION_ACTIVATION_HASH_BINDINGS[key]:
        _fail(f"H001 activation {key} hash binding drifted")


def validate_h001_synthetic_null_calibration_spec_freeze_activation(value: object) -> dict:
    """Validate the effective freeze amendment without filesystem or execution access."""
    data = _base(
        value,
        H001_CALIBRATION_ACTIVATION_AMENDMENT_KIND,
        H001_CALIBRATION_ACTIVATION_AMENDMENT_ID,
        H001_CALIBRATION_ACTIVATION_STATUS,
        _H001_CALIBRATION_ACTIVATION_KEYS,
    )
    if data["base_main_commit"] != H001_CALIBRATION_ACTIVATION_BASE_MAIN_COMMIT or data["governed_h001_protocol_id"] != H001_PROTOCOL_ID:
        _fail("H001 activation identity or base-main binding drifted")
    if data["amendment_id"] != H001_CALIBRATION_ACTIVATION_AMENDMENT_ID or data["amendment_kind"] != H001_CALIBRATION_ACTIVATION_AMENDMENT_KIND:
        _fail("H001 activation amendment identity drifted")
    _require_exact_bool(data["candidate_review_completed"], True, "candidate_review_completed")
    _require_exact_bool(data["candidate_review_recorded"], True, "candidate_review_recorded")
    for key in ("effective",):
        _require_exact_bool(data[key], True, key)
    auth = _keys(data["authorization_state"], _H001_CALIBRATION_ACTIVATION_AUTH_KEYS, "H001 activation authorization_state")
    for key in _H001_CALIBRATION_ACTIVATION_AUTH_KEYS:
        _require_exact_bool(auth[key], key in {"specification_effective", "specification_frozen_effective"}, f"authorization_state {key}")
    effective = _keys(data["effective_specification"], {"document_id", "path", "sha256", "source_status", "source_status_explanation"}, "H001 effective specification")
    if effective != {
        "document_id": H001_FREEZE_CANDIDATE_DOCUMENT_ID,
        "path": _H001_CALIBRATION_ACTIVATION_HASH_BINDINGS["effective_specification"][0],
        "sha256": H001_CALIBRATION_EFFECTIVE_SPECIFICATION_SHA256,
        "source_status": H001_FREEZE_CANDIDATE_STATUS,
        "source_status_explanation": "The immutable candidate artifact retains its historical source status. This activation amendment changes its governed effective status without mutating its bytes.",
    }:
        _fail("H001 effective specification identity drifted")
    bindings = _keys(data["hash_bindings"], set(_H001_CALIBRATION_ACTIVATION_HASH_BINDINGS), "H001 activation hash_bindings")
    for key in _H001_CALIBRATION_ACTIVATION_HASH_BINDINGS:
        _validate_activation_hash_binding(bindings[key], key)
    history = _keys(data["review_history"], set(_H001_CALIBRATION_ACTIVATION_REVIEW_HISTORY), "H001 activation review_history")
    if history != _H001_CALIBRATION_ACTIVATION_REVIEW_HISTORY:
        _fail("H001 activation candidate and review-record history drifted")
    frozen = _keys(data["frozen_values"], set(_H001_CALIBRATION_ACTIVATION_FROZEN_VALUES), "H001 activation frozen_values")
    if frozen != _H001_CALIBRATION_ACTIVATION_FROZEN_VALUES:
        _fail("H001 activation frozen values drifted")
    if data["non_effects"] != _H001_CALIBRATION_ACTIVATION_NON_EFFECTS or "SPECIFICATION_REMAINS_UNFROZEN" in data["non_effects"]:
        _fail("H001 activation non-effects drifted")
    return data


def load_and_validate_h001_synthetic_null_calibration_spec_freeze_activation(raw: bytes) -> dict:
    """Strict UTF-8, duplicate-key rejecting, canonical byte-level activation loader."""
    if type(raw) is not bytes:
        _fail("exact bytes input required")
    try:
        parsed = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_json_keys)
    except (UnicodeDecodeError, json.JSONDecodeError, AssuranceValidationError) as error:
        raise AssuranceValidationError("strict UTF-8 JSON without duplicate keys required") from error
    if canonical_json_bytes(parsed) != raw:
        _fail("non-canonical JSON bytes")
    return validate_h001_synthetic_null_calibration_spec_freeze_activation(parsed)


# --- H001 RNG-runtime specification amendment candidate (appended by the v027 transition) ---

H001_RNG_CANDIDATE_ID = "candidate1-h001-synthetic-null-calibration-rng-runtime-specification-amendment-v001"
H001_RNG_CANDIDATE_KIND = "qnty_h001_synthetic_null_calibration_rng_runtime_specification_amendment_candidate"
H001_RNG_CANDIDATE_STATUS = "IMPLEMENTED_FOR_INDEPENDENT_REVIEW_NOT_EFFECTIVE"
H001_RNG_SELECTED_ARCHITECTURE = "RAW_NUMPY_PHILOX_WITH_REPOSITORY_OWNED_DETERMINISTIC_MAPPINGS"
H001_RNG_SEED_DOMAIN = "h001-null-calibration/h001-synthetic-null-calibration-spec-freeze-candidate-v001/synthetic-only"
H001_RNG_GOVERNANCE_AMENDMENT_SHA256 = "da27f06effb8321da84ee9f44ff90b810e8c36491d729387b4e820e14f0d8c36"
H001_RNG_FROZEN_SPEC_SHA256 = "04b6ea5b7453fccf4787abb26c230e2a02a77545c741c19f6686df16fc2cb7a2"
H001_RNG_SPEC_ACTIVATION_SHA256 = "3fa3d21492645baba8a1fd7fd5fbe8a601ccccec1371e5e7a81faff430c2ab48"
H001_RNG_V026_RECEIPT_SHA256 = "fd62b1f648b50817b8c664fb38f9e1e685876981cb425d5daf29b78e14e13d2c"
H001_RNG_RETRY_CAP = 8
H001_RNG_SAMPLE_LENGTH = 2193
H001_RNG_TWO_POW_64 = 1 << 64

H001_RNG_DOMAINS = [
    "NORMATIVE_RANDOM_BIT_SOURCE_AND_HIGH_LEVEL_API_BOUNDARY",
    "LOGICAL_COORDINATE_SCHEMA_AND_CANONICAL_ENCODING",
    "LOGICAL_COORDINATE_TO_PHILOX_KEY_COUNTER_AND_LANE_MAPPING",
    "EXACT_BOUNDED_INTEGER_AND_RATIONAL_BERNOULLI_MAPPING",
    "REJECTION_ATTEMPT_ISOLATION_RETRY_CAP_AND_FAIL_CLOSED_RULE",
    "NUMPY_SEED_SEQUENCE_RUNTIME_DEPENDENCY_BOUNDARY",
    "DRAW_PURPOSE_ALLOCATION_AND_STATIONARY_BOOTSTRAP_LOGICAL_ORDER",
    "PORTABILITY_SCOPE_AND_REPRODUCIBILITY_CLAIM",
]
H001_RNG_SOURCE_CLASSIFICATIONS = {
    "SOURCE_SUPPORTED_CHOICE", "REPOSITORY_SPECIFIC_DETERMINISTIC_CHOICE",
    "IMPLEMENTATION_DETAIL", "SCIENTIFIC_ASSUMPTION",
}
H001_RNG_FAILURE_CATEGORIES = {
    "H001_RNG_FORBIDDEN_HIGH_LEVEL_API", "H001_RNG_INVALID_COORDINATE",
    "H001_RNG_COORDINATE_OUT_OF_DOMAIN", "H001_RNG_ADDRESSING_VIOLATION",
    "H001_RNG_INVALID_BOUND", "H001_RNG_INVALID_RATIONAL",
    "H001_RNG_RETRY_CAP_EXHAUSTED", "H001_RNG_UNKNOWN_DRAW_PURPOSE",
    "H001_RNG_SEED_SEQUENCE_BOUNDARY_VIOLATION", "H001_RNG_PORTABILITY_CLAIM_VIOLATION",
}
H001_RNG_DRAW_PURPOSES = {"INITIAL_INDEX": 1, "RESTART_DECISION": 2, "RESTART_INDEX": 3}
H001_RNG_COORDINATE_FIELDS = [
    "protocol_seed_domain", "dgp_or_case_id", "outer_replication_index",
    "bootstrap_replication_index", "draw_purpose", "sample_position", "attempt_index",
]
H001_RNG_FIXTURE_IDS = {
    "KAT-PAYLOAD-001", "KAT-PAYLOAD-002", "KAT-HISTORICAL-SEEDSEQUENCE-001",
    "KAT-RAW-001", "KAT-RAW-002", "KAT-RAW-003", "KAT-RAW-004", "KAT-RAW-005",
    "KAT-RAW-006", "KAT-RAW-007", "KAT-RAW-008", "KAT-RAW-009",
    "KAT-BOUNDED-N1-001", "KAT-BOUNDED-N63-001", "KAT-BOUNDED-N2193-001", "KAT-BOUNDED-NMAX-001",
    "KAT-RETRY-001", "KAT-EXHAUSTION-001",
    "KAT-BERNOULLI-TRUE-001", "KAT-BERNOULLI-FALSE-001", "KAT-BERNOULLI-P0-001", "KAT-BERNOULLI-P1Q1-001",
    "KAT-PATH-001", "KAT-PATH-002",
}
H001_RNG_RESEARCH_DERIVED_SEED = "17221696974678360913"
H001_RNG_RESEARCH_RAW_WORDS = [
    "15467181228313756398", "16652732221003594432",
    "2070436752386381772", "4733267601814909029",
]
H001_RNG_MATRIX_COLUMNS = {
    "domain", "normative_rule", "source_classification", "input_domain",
    "canonical_encoding", "algorithm", "edge_cases", "failure_category",
    "known_answer_fixture_ids", "implementation_test_ids", "rejected_alternatives",
    "additional_choice_required", "independent_review_must_fail_if_additional_choice_remains",
}
H001_RNG_CANDIDATE_KEYS = {
    "amendment_id", "amendment_kind", "schema_version", "status", "effective", "activated",
    "independent_review_required", "independent_review_completed", "governed_h001_protocol_id",
    "base_main_commit", "authority_non_effects", "hash_bindings", "amendment_scope",
    "selected_architecture", "alternative_adjudication", "domain_resolution_order",
    "domain_resolutions", "implementability_matrix", "draw_purpose_registry",
    "logical_coordinate_schema", "philox_binding", "exact_bounded_integer",
    "exact_rational_bernoulli", "rejection_isolation_and_retry_cap",
    "stationary_bootstrap_logical_order", "seed_sequence_decision",
    "portability_and_reproducibility", "primary_sources", "known_answer_fixtures",
    "fixture_policy", "unique_result_gate", "non_effects",
}
H001_RNG_EXPECTED_AUTHORITY_NON_EFFECTS = {
    "calibration_engine_implemented": False,
    "calibration_execution_authorized": False,
    "calibration_execution_count": 0,
    "calibration_execution_budget": 0,
    "calibration_results_available": False,
    "candidate_created": True,
    "candidate_reviewed": False,
    "candidate_effective": False,
    "candidate_activated": False,
    "edge_status": "EDGE_UNPROVEN",
    "live_status": "BLOCK_LIVE_INTEGRATION",
    "real_data_access": False,
    "scientific_authorization_granted": False,
    "paper_trade_authorization_granted": False,
    "live_authorization_granted": False,
}
H001_RNG_PLACEHOLDER_MARKERS = ("TBD", "TODO", "FIXME", "PLACEHOLDER", "implementation-defined", "library default")
H001_RNG_PRIMARY_SOURCE_IDS = [
    "OFFICIAL_NUMPY_PHILOX_DOCUMENTATION",
    "OFFICIAL_NUMPY_COMPATIBILITY_POLICY",
    "OFFICIAL_NUMPY_RANDOM_RAW_DOCUMENTATION",
    "SALMON_MORAES_DROR_SHAW_COUNTER_BASED_RNGS",
    "POLITIS_ROMANO_STATIONARY_BOOTSTRAP",
    "CANONICAL_EXACT_BOUNDED_INTEGER_SOURCE",
]


def _rng_uint64_str(value: object, label: str, *, maximum: int = (1 << 64) - 1) -> int:
    if type(value) is not str or not value or (len(value) > 1 and value[0] == "0") or not value.isdigit():
        _fail(f"{label}: canonical decimal string required")
    number = int(value)
    if number > maximum:
        _fail(f"{label}: value exceeds the supported domain")
    return number


def _rng_bounded_int(value: object, label: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or isinstance(value, bool) or value < minimum or value > maximum:
        _fail(f"{label}: integer in {minimum}..{maximum} required")
    return value


def _rng_payload_fixture(fixture: object, label: str) -> dict:
    data = _keys(fixture, {
        "dgp_or_case_id", "outer_replication_index", "bootstrap_replication_index",
        "payload_string", "payload_utf8_sha256", "derived_seed64",
        "philox_key_word_0", "philox_key_word_1",
    }, label)
    dgp = _identifier(data["dgp_or_case_id"], f"{label} dgp_or_case_id")
    outer = _rng_bounded_int(data["outer_replication_index"], f"{label} outer_replication_index", 0, 1999)
    boot = _rng_bounded_int(data["bootstrap_replication_index"], f"{label} bootstrap_replication_index", 0, 9999)
    payload = _str(data["payload_string"], f"{label} payload_string")
    if payload != f"{H001_RNG_SEED_DOMAIN}:{dgp}:outer:{outer}:bootstrap:{boot}":
        _fail(f"{label}: payload_string does not follow the frozen grammar")
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    if _sha(data["payload_utf8_sha256"], f"{label} payload_utf8_sha256") != digest:
        _fail(f"{label}: payload digest is not reproducible from the payload string")
    if _rng_uint64_str(data["derived_seed64"], f"{label} derived_seed64") != int(digest[0:16], 16):
        _fail(f"{label}: derived_seed64 breaks the frozen seed_integer_rule")
    if data["philox_key_word_0"] != data["derived_seed64"]:
        _fail(f"{label}: philox_key_word_0 must equal the frozen derived seed")
    if _rng_uint64_str(data["philox_key_word_1"], f"{label} philox_key_word_1") != int(digest[16:32], 16):
        _fail(f"{label}: philox_key_word_1 does not extend the digest")
    return data


def _rng_counter_consistent(fixture: dict, label: str) -> None:
    purpose = _str(fixture["draw_purpose"], f"{label} draw_purpose")
    if purpose not in H001_RNG_DRAW_PURPOSES:
        _fail(f"{label}: unknown draw purpose")
    position = _rng_bounded_int(fixture["sample_position"], f"{label} sample_position", 0, H001_RNG_SAMPLE_LENGTH - 1)
    attempt = _rng_bounded_int(fixture["attempt_index"], f"{label} attempt_index", 0, H001_RNG_RETRY_CAP - 1)
    expected = attempt | (H001_RNG_DRAW_PURPOSES[purpose] << 8) | (position << 16)
    if _rng_uint64_str(fixture["counter_word_0"], f"{label} counter_word_0") != expected:
        _fail(f"{label}: counter_word_0 does not match the packed coordinate")


def _rng_accepted_words(words: object, n: int, label: str) -> tuple:
    if type(words) is not list or not words or len(words) > H001_RNG_RETRY_CAP:
        _fail(f"{label}: raw_words_consumed must be a bounded non-empty list")
    limit = H001_RNG_TWO_POW_64 - (H001_RNG_TWO_POW_64 % n)
    parsed = [_rng_uint64_str(word, f"{label} raw word") for word in words]
    for rejected in parsed[:-1]:
        if rejected < limit:
            _fail(f"{label}: a rejected raw word is below the acceptance limit")
    if parsed[-1] >= limit:
        _fail(f"{label}: the accepted raw word is not below the acceptance limit")
    return parsed, limit


def _rng_bounded_fixture(fixture: object, label: str) -> None:
    data = _keys(fixture, {
        "payload_fixture", "draw_purpose", "sample_position", "bound_n", "acceptance_limit",
        "raw_words_consumed", "accepted_attempt_index", "result",
    }, label)
    n = _rng_uint64_str(data["bound_n"], f"{label} bound_n", maximum=H001_RNG_TWO_POW_64)
    if n < 1:
        _fail(f"{label}: bound_n must be at least 1")
    parsed, limit = _rng_accepted_words(data["raw_words_consumed"], n, label)
    if _rng_uint64_str(data["acceptance_limit"], f"{label} acceptance_limit", maximum=H001_RNG_TWO_POW_64) != limit:
        _fail(f"{label}: acceptance_limit is not 2**64 - (2**64 mod n)")
    accepted = _rng_bounded_int(data["accepted_attempt_index"], f"{label} accepted_attempt_index", 0, H001_RNG_RETRY_CAP - 1)
    if accepted != len(parsed) - 1:
        _fail(f"{label}: accepted_attempt_index does not match the consumed words")
    if _rng_uint64_str(data["result"], f"{label} result") != parsed[-1] % n:
        _fail(f"{label}: result is not the accepted word reduced modulo n")


def _rng_bernoulli_fixture(fixture: object, label: str) -> None:
    data = _keys(fixture, {
        "payload_fixture", "draw_purpose", "sample_position", "probability_numerator",
        "probability_denominator", "raw_words_consumed", "uniform_value", "comparison", "result",
    }, label)
    if data["draw_purpose"] != "RESTART_DECISION":
        _fail(f"{label}: Bernoulli fixtures must use the RESTART_DECISION purpose")
    q = _rng_bounded_int(data["probability_denominator"], f"{label} probability_denominator", 1, (1 << 63))
    p = _rng_bounded_int(data["probability_numerator"], f"{label} probability_numerator", 0, q)
    parsed, _limit = _rng_accepted_words(data["raw_words_consumed"], q, label)
    uniform = _rng_uint64_str(data["uniform_value"], f"{label} uniform_value")
    if uniform != parsed[-1] % q:
        _fail(f"{label}: uniform_value is not the accepted word reduced modulo q")
    if type(data["result"]) is not bool or data["result"] != (uniform < p):
        _fail(f"{label}: result does not equal the strict integer comparison uniform < p")
    if _str(data["comparison"], f"{label} comparison") != f"{uniform} < {p}":
        _fail(f"{label}: comparison transcript drifted")


def _rng_path_fixture(fixture: object, label: str, *, wraparound_required: bool) -> None:
    data = _keys(fixture, {
        "payload_fixture", "sample_length", "index_path", "index_path_canonical_json_sha256",
        "restart_positions", "restart_count", "wraparound_continuation_positions",
    }, label)
    if data["sample_length"] != H001_RNG_SAMPLE_LENGTH:
        _fail(f"{label}: sample_length drifted from the frozen contract")
    path = data["index_path"]
    if type(path) is not list or len(path) != H001_RNG_SAMPLE_LENGTH:
        _fail(f"{label}: index_path must contain exactly {H001_RNG_SAMPLE_LENGTH} entries")
    for index in path:
        _rng_bounded_int(index, f"{label} index_path entry", 0, H001_RNG_SAMPLE_LENGTH - 1)
    restarts = data["restart_positions"]
    if type(restarts) is not list or restarts != sorted(set(restarts)):
        _fail(f"{label}: restart_positions must be strictly increasing and unique")
    for position in restarts:
        _rng_bounded_int(position, f"{label} restart position", 1, H001_RNG_SAMPLE_LENGTH - 1)
    if data["restart_count"] != len(restarts):
        _fail(f"{label}: restart_count does not match restart_positions")
    restart_set = set(restarts)
    for t in range(1, H001_RNG_SAMPLE_LENGTH):
        if t not in restart_set and path[t] != (path[t - 1] + 1) % H001_RNG_SAMPLE_LENGTH:
            _fail(f"{label}: continuation step at position {t} breaks the wraparound successor rule")
    wraps = data["wraparound_continuation_positions"]
    expected_wraps = [
        t for t in range(1, H001_RNG_SAMPLE_LENGTH)
        if t not in restart_set and path[t] == 0 and path[t - 1] == H001_RNG_SAMPLE_LENGTH - 1
    ]
    if type(wraps) is not list or wraps != expected_wraps:
        _fail(f"{label}: wraparound_continuation_positions do not match the path")
    if wraparound_required and not wraps:
        _fail(f"{label}: a wraparound-exhibiting path fixture is required")
    if _sha(data["index_path_canonical_json_sha256"], f"{label} path sha") != hashlib.sha256(canonical_json_bytes(path)).hexdigest():
        _fail(f"{label}: index_path canonical hash is not reproducible")


def _rng_scan_placeholders(value: object) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            _rng_scan_placeholders(key)
            _rng_scan_placeholders(child)
    elif isinstance(value, list):
        for child in value:
            _rng_scan_placeholders(child)
    elif type(value) is str:
        for marker in H001_RNG_PLACEHOLDER_MARKERS:
            if marker in value:
                _fail(f"unresolved placeholder marker {marker!r} in candidate text")


def validate_h001_rng_runtime_amendment_candidate(value: object) -> dict:
    data = _keys(value, H001_RNG_CANDIDATE_KEYS, "H001 RNG-runtime amendment candidate")
    if data["amendment_id"] != H001_RNG_CANDIDATE_ID or data["amendment_kind"] != H001_RNG_CANDIDATE_KIND:
        _fail("H001 RNG candidate identity drifted")
    if data["schema_version"] != SCHEMA_VERSION or data["status"] != H001_RNG_CANDIDATE_STATUS:
        _fail("H001 RNG candidate schema or status drifted")
    if data["governed_h001_protocol_id"] != H001_PROTOCOL_ID:
        _fail("H001 RNG candidate protocol drifted")
    commit = data["base_main_commit"]
    if type(commit) is not str or not re.fullmatch(r"[0-9a-f]{40}", commit):
        _fail("H001 RNG candidate base_main_commit must be a lowercase 40-hex commit")
    for field, expected in (("effective", False), ("activated", False), ("independent_review_completed", False), ("independent_review_required", True)):
        if data[field] is not expected:
            _fail(f"H001 RNG candidate {field} must be {expected}")
    non_effect_state = _keys(data["authority_non_effects"], set(H001_RNG_EXPECTED_AUTHORITY_NON_EFFECTS), "H001 RNG candidate authority_non_effects")
    for key, expected in H001_RNG_EXPECTED_AUTHORITY_NON_EFFECTS.items():
        actual = non_effect_state[key]
        if type(expected) is bool:
            if actual is not expected:
                _fail(f"H001 RNG candidate authority_non_effects {key} drifted from the non-effective contract")
        elif type(expected) is int:
            if type(actual) is not int or actual != expected:
                _fail(f"H001 RNG candidate authority_non_effects {key} drifted from the non-effective contract")
        elif actual != expected:
            _fail(f"H001 RNG candidate authority_non_effects {key} drifted from the non-effective contract")
    bindings = _keys(data["hash_bindings"], {"governing_amendment", "frozen_calibration_spec_candidate", "spec_freeze_activation", "v026_receipt"}, "H001 RNG candidate hash_bindings")
    expected_bindings = {
        "governing_amendment": ("docs/control/amendments/candidate1_h001_synthetic_null_calibration_rng_runtime_specification_amendment_governance_v001.json", H001_RNG_GOVERNANCE_AMENDMENT_SHA256),
        "frozen_calibration_spec_candidate": ("docs/assurance/h001_synthetic_null_calibration_spec_freeze_candidate_v001.json", H001_RNG_FROZEN_SPEC_SHA256),
        "spec_freeze_activation": ("docs/control/amendments/candidate1_h001_synthetic_null_calibration_spec_freeze_activation_v001.json", H001_RNG_SPEC_ACTIVATION_SHA256),
        "v026_receipt": ("docs/control/tasks/RECOVER_OR_RETIRE_CANDIDATE1_V0_FROZEN_INPUT/handoff_v026.json", H001_RNG_V026_RECEIPT_SHA256),
    }
    for name, (path, digest) in expected_bindings.items():
        if _keys(bindings[name], {"path", "sha256"}, f"H001 RNG candidate hash binding {name}") != {"path": path, "sha256": digest}:
            _fail(f"H001 RNG candidate hash binding {name} drifted")
    if data["selected_architecture"] != H001_RNG_SELECTED_ARCHITECTURE:
        _fail("H001 RNG candidate selected architecture drifted")
    adjudication = _keys(data["alternative_adjudication"], {
        "alternative_a_high_level_generator_api",
        "alternative_b_raw_numpy_philox_with_repository_owned_mappings",
        "alternative_c_native_repository_philox",
    }, "H001 RNG candidate alternative_adjudication")
    for name, decision in (
        ("alternative_a_high_level_generator_api", "REJECTED"),
        ("alternative_b_raw_numpy_philox_with_repository_owned_mappings", "SELECTED"),
        ("alternative_c_native_repository_philox", "REJECTED_AS_NORMATIVE_RUNTIME_RETAINED_AS_TEST_ONLY_VERIFIER"),
    ):
        entry = adjudication[name]
        if type(entry) is not dict or entry.get("decision") != decision:
            _fail(f"H001 RNG candidate adjudication for {name} drifted")
    if data["domain_resolution_order"] != H001_RNG_DOMAINS:
        _fail("H001 RNG candidate domain inventory must match the governed order exactly")
    resolutions = data["domain_resolutions"]
    matrix = data["implementability_matrix"]
    if type(resolutions) is not list or len(resolutions) != len(H001_RNG_DOMAINS):
        _fail("H001 RNG candidate domain_resolutions must cover every governed domain exactly once")
    if type(matrix) is not list or len(matrix) != len(H001_RNG_DOMAINS):
        _fail("H001 RNG candidate implementability matrix must cover every governed domain exactly once")
    fixtures = data["known_answer_fixtures"]
    if type(fixtures) is not dict or set(fixtures) != H001_RNG_FIXTURE_IDS:
        _fail("H001 RNG candidate known-answer fixture inventory drifted")
    for index, (resolution, row) in enumerate(zip(resolutions, matrix)):
        domain = H001_RNG_DOMAINS[index]
        resolution = _keys(resolution, {
            "domain", "normative_rule", "source_classification", "failure_category",
            "additional_choice_required", "independent_review_must_fail_if_additional_choice_remains",
        }, f"H001 RNG candidate domain resolution {domain}")
        row = _keys(row, H001_RNG_MATRIX_COLUMNS, f"H001 RNG candidate matrix row {domain}")
        if resolution["domain"] != domain or row["domain"] != domain:
            _fail("H001 RNG candidate domain rows are out of governed order")
        if resolution["additional_choice_required"] is not False or row["additional_choice_required"] is not False:
            _fail("H001 RNG candidate leaves an additional result-determinative choice open")
        if resolution["independent_review_must_fail_if_additional_choice_remains"] is not True or row["independent_review_must_fail_if_additional_choice_remains"] is not True:
            _fail("H001 RNG candidate weakened the additional-choice review gate")
        if resolution["source_classification"] not in H001_RNG_SOURCE_CLASSIFICATIONS or row["source_classification"] not in H001_RNG_SOURCE_CLASSIFICATIONS:
            _fail("H001 RNG candidate source classification is unknown")
        if row["source_classification"] == "IMPLEMENTATION_DETAIL":
            _fail("H001 RNG candidate classifies a result-determinative rule as an implementation detail")
        if resolution["failure_category"] not in H001_RNG_FAILURE_CATEGORIES or row["failure_category"] not in H001_RNG_FAILURE_CATEGORIES:
            _fail("H001 RNG candidate failure category is unknown")
        if resolution["normative_rule"] != row["normative_rule"] or resolution["source_classification"] != row["source_classification"] or resolution["failure_category"] != row["failure_category"]:
            _fail("H001 RNG candidate domain resolution and matrix row diverge")
        _str(row["normative_rule"], f"H001 RNG candidate matrix normative_rule {domain}")
        _str(row["input_domain"], f"H001 RNG candidate matrix input_domain {domain}")
        _str(row["canonical_encoding"], f"H001 RNG candidate matrix canonical_encoding {domain}")
        _str(row["algorithm"], f"H001 RNG candidate matrix algorithm {domain}")
        for list_field in ("edge_cases", "rejected_alternatives"):
            entries = row[list_field]
            if type(entries) is not list or not entries:
                _fail(f"H001 RNG candidate matrix {list_field} for {domain} must be a non-empty list")
            for entry in entries:
                _str(entry, f"H001 RNG candidate matrix {list_field} entry for {domain}")
        fixture_ids = _list(row["known_answer_fixture_ids"], f"H001 RNG candidate matrix fixtures for {domain}", sorted_unique=True)
        if not fixture_ids or not set(fixture_ids) <= H001_RNG_FIXTURE_IDS:
            _fail(f"H001 RNG candidate matrix fixtures for {domain} must name bound known-answer fixtures")
        test_ids = _list(row["implementation_test_ids"], f"H001 RNG candidate matrix tests for {domain}", sorted_unique=True)
        if not test_ids:
            _fail(f"H001 RNG candidate matrix tests for {domain} must not be empty")
        for test_id in test_ids:
            _str(test_id, f"H001 RNG candidate matrix test id for {domain}")
            if not test_id.startswith("tests/") or "::" not in test_id:
                _fail(f"H001 RNG candidate matrix test id for {domain} must be a pytest node id under tests/")
    registry = _keys(data["draw_purpose_registry"], {
        "registry_is_closed", "raw_word_sharing_across_purposes", "unknown_purpose_failure_category",
        "purposes", "unused_logical_draws", "future_purposes",
    }, "H001 RNG candidate draw_purpose_registry")
    if registry["registry_is_closed"] is not True:
        _fail("H001 RNG candidate draw-purpose registry must be closed")
    if registry["raw_word_sharing_across_purposes"] != "FORBIDDEN":
        _fail("H001 RNG candidate permits raw-word sharing across purposes")
    if registry["unknown_purpose_failure_category"] != "H001_RNG_UNKNOWN_DRAW_PURPOSE":
        _fail("H001 RNG candidate unknown-purpose failure category drifted")
    purposes = registry["purposes"]
    if type(purposes) is not list or len(purposes) != len(H001_RNG_DRAW_PURPOSES):
        _fail("H001 RNG candidate draw-purpose registry must contain exactly the governed purposes")
    seen_purpose_ids = []
    for entry, (name, purpose_id) in zip(purposes, H001_RNG_DRAW_PURPOSES.items()):
        entry = _keys(entry, {
            "purpose", "purpose_id", "meaning", "permitted_coordinate_fields",
            "sample_position_domain", "conditionally_evaluated",
        }, f"H001 RNG candidate draw purpose {name}")
        if entry["purpose"] != name or entry["purpose_id"] != purpose_id:
            _fail("H001 RNG candidate draw-purpose identifiers drifted")
        if entry["purpose_id"] in seen_purpose_ids:
            _fail("H001 RNG candidate draw-purpose identifiers are duplicated")
        seen_purpose_ids.append(entry["purpose_id"])
        if entry["permitted_coordinate_fields"] != H001_RNG_COORDINATE_FIELDS:
            _fail(f"H001 RNG candidate permitted coordinate fields drifted for {name}")
        if type(entry["conditionally_evaluated"]) is not bool or entry["conditionally_evaluated"] is not (name == "RESTART_INDEX"):
            _fail(f"H001 RNG candidate conditional-evaluation flag drifted for {name}")
    schema = _keys(data["logical_coordinate_schema"], {
        "fields", "field_order", "injectivity", "unexpected_field_behaviour", "environment_independence",
    }, "H001 RNG candidate logical_coordinate_schema")
    fields = schema["fields"]
    if type(fields) is not list or [entry.get("field") if type(entry) is dict else None for entry in fields] != H001_RNG_COORDINATE_FIELDS:
        _fail("H001 RNG candidate coordinate fields must match the governed schema exactly")
    field_bounds = {
        "outer_replication_index": (0, 1999), "bootstrap_replication_index": (0, 9999),
        "draw_purpose": (1, 3), "sample_position": (0, 2192), "attempt_index": (0, 7),
    }
    for entry in fields:
        name = entry["field"]
        if name == "protocol_seed_domain" and entry.get("value") != H001_RNG_SEED_DOMAIN:
            _fail("H001 RNG candidate seed-domain constant drifted")
        if name in field_bounds and (entry.get("minimum"), entry.get("maximum")) != field_bounds[name]:
            _fail(f"H001 RNG candidate bounds drifted for coordinate field {name}")
    binding = _keys(data["philox_binding"], {
        "block_function", "round_count", "counter_width_bits", "key_width_bits", "counter_word_order",
        "key_derivation", "counter_derivation", "lane_rule", "numpy_realization", "numpy_realization_reason",
        "reserved_address_ranges", "maximum_address_space", "collision_prohibition", "truncation_rationale",
    }, "H001 RNG candidate philox_binding")
    if binding["round_count"] != 10 or binding["counter_width_bits"] != 256 or binding["key_width_bits"] != 128:
        _fail("H001 RNG candidate Philox parameters drifted")
    if "Philox4x64-10" not in binding["block_function"]:
        _fail("H001 RNG candidate block function drifted")
    if "random_raw(4)[0]" not in binding["numpy_realization"] or "(counter_integer - 1) mod 2**256" not in binding["numpy_realization"]:
        _fail("H001 RNG candidate numpy realization binding drifted")
    if "lane 0" not in binding["lane_rule"]:
        _fail("H001 RNG candidate lane rule drifted")
    bounded = _keys(data["exact_bounded_integer"], {
        "pseudocode", "arithmetic_width", "accepted_interval", "return_type", "unbiasedness_argument",
        "n_equals_1", "n_equals_2_pow_64", "invalid_bounds", "prohibitions",
    }, "H001 RNG candidate exact_bounded_integer")
    prohibitions = _keys(bounded["prohibitions"], {
        "plain_modulo_without_rejection", "floating_point_arithmetic",
        "cross_coordinate_retry_consumption", "biased_fallback_after_exhaustion",
    }, "H001 RNG candidate bounded-integer prohibitions")
    for name, marker in prohibitions.items():
        if marker != "FORBIDDEN":
            _fail(f"H001 RNG candidate bounded-integer prohibition {name} is not FORBIDDEN")
    pseudocode = _list(bounded["pseudocode"], "H001 RNG candidate bounded-integer pseudocode")
    pseudocode_text = "\n".join(_str(line, "H001 RNG candidate pseudocode line") for line in pseudocode)
    for required in ("limit = 2**64 - (2**64 mod n)", "if x < limit: return x mod n", "H001_RNG_RETRY_CAP_EXHAUSTED"):
        if required not in pseudocode_text:
            _fail("H001 RNG candidate bounded-integer pseudocode lost a required exact rule")
    if "float" in pseudocode_text.lower():
        _fail("H001 RNG candidate bounded-integer pseudocode mentions floating point")
    bernoulli_spec = _keys(data["exact_rational_bernoulli"], {
        "pseudocode", "numerator_domain", "denominator_domain", "reduction_requirement",
        "comparison_operator", "output_type", "boundary_behaviour",
        "governed_restart_probability", "floating_point_thresholds",
    }, "H001 RNG candidate exact_rational_bernoulli")
    if bernoulli_spec["comparison_operator"] != "strict less-than on exact integers":
        _fail("H001 RNG candidate Bernoulli comparison operator drifted")
    if bernoulli_spec["floating_point_thresholds"] != "FORBIDDEN":
        _fail("H001 RNG candidate permits floating-point Bernoulli thresholds")
    restart = _keys(bernoulli_spec["governed_restart_probability"], {"numerator", "denominator", "source"}, "H001 RNG candidate governed restart probability")
    if restart["numerator"] != 1 or restart["denominator"] != 63:
        _fail("H001 RNG candidate governed restart probability is not exactly 1/63")
    isolation = _keys(data["rejection_isolation_and_retry_cap"], {
        "structural_isolation_argument", "retry_cap", "retry_cap_configurable", "retry_cap_rationale",
        "worst_governed_rejection_probability", "governed_rejection_probabilities",
        "exhaustion_probability_bound", "exhaustion_failure_category", "fail_closed_behaviour",
    }, "H001 RNG candidate rejection_isolation_and_retry_cap")
    if isolation["retry_cap"] != H001_RNG_RETRY_CAP or type(isolation["retry_cap"]) is not int:
        _fail("H001 RNG candidate retry cap drifted from the governed exact value")
    if isolation["retry_cap_configurable"] is not False:
        _fail("H001 RNG candidate leaves the retry cap configurable")
    if isolation["exhaustion_failure_category"] != "H001_RNG_RETRY_CAP_EXHAUSTED":
        _fail("H001 RNG candidate exhaustion failure category drifted")
    order = _keys(data["stationary_bootstrap_logical_order"], {
        "sample_length", "index_domain", "position_numbering", "bootstrap_replication_numbering",
        "outer_replication_numbering", "algorithm", "position_zero_rule", "restart_decision_timing",
        "restart_index_allocation", "wraparound_rule", "logical_versus_physical_order",
        "shared_synchronous_path",
    }, "H001 RNG candidate stationary_bootstrap_logical_order")
    if order["sample_length"] != H001_RNG_SAMPLE_LENGTH:
        _fail("H001 RNG candidate bootstrap sample length drifted")
    algorithm_text = "\n".join(_str(line, "H001 RNG candidate bootstrap algorithm line") for line in _list(order["algorithm"], "H001 RNG candidate bootstrap algorithm"))
    for required in ("uniform_bounded(coordinate(INITIAL_INDEX, position 0), 2193)", "bernoulli_rational(coordinate(RESTART_DECISION, position t), 1, 63)", "(b[t-1] + 1) mod 2193"):
        if required not in algorithm_text:
            _fail("H001 RNG candidate bootstrap logical order lost a required exact rule")
    decision = _keys(data["seed_sequence_decision"], {
        "selected_option", "seed_sequence_in_normative_bootstrap_index_path", "component_stream_layer",
        "compatibility_with_frozen_contract",
    }, "H001 RNG candidate seed_sequence_decision")
    if decision["selected_option"] != "DIRECT_DETERMINISTIC_PHILOX_KEY_COUNTER_CONSTRUCTION_FOR_NORMATIVE_BOOTSTRAP_INDEX_PATH":
        _fail("H001 RNG candidate SeedSequence decision drifted")
    if decision["seed_sequence_in_normative_bootstrap_index_path"] is not False:
        _fail("H001 RNG candidate reintroduces SeedSequence into the normative path")
    layer = _keys(decision["component_stream_layer"], {
        "decision", "rule", "declared_boundary", "outside_boundary_behaviour", "observed_runtime_evidence",
    }, "H001 RNG candidate component-stream layer")
    if layer["decision"] != "RETAINED_WITH_DECLARED_RUNTIME_BOUNDARY":
        _fail("H001 RNG candidate component-stream SeedSequence boundary drifted")
    portability = _keys(data["portability_and_reproducibility"], {
        "bootstrap_index_path_claim", "component_stream_claim",
        "cross_language_reproducibility_claimed", "claim_scope_note",
    }, "H001 RNG candidate portability_and_reproducibility")
    if portability["cross_language_reproducibility_claimed"] is not False:
        _fail("H001 RNG candidate makes an unproven cross-language reproducibility claim")
    gate = _keys(data["unique_result_gate"], {
        "requirement", "additional_choice_required", "independent_review_must_fail_if_additional_choice_remains",
    }, "H001 RNG candidate unique_result_gate")
    if gate["additional_choice_required"] is not False or gate["independent_review_must_fail_if_additional_choice_remains"] is not True:
        _fail("H001 RNG candidate unique-result gate drifted")
    for fragment in ("TWO_INDEPENDENT_IMPLEMENTERS", "IDENTICAL_RAW_WORDS", "STATIONARY_BOOTSTRAP_INDEX_SEQUENCES", "WITHOUT_ANY_ADDITIONAL_RESULT_DETERMINATIVE_CHOICE"):
        if fragment not in _str(gate["requirement"], "H001 RNG candidate unique-result requirement"):
            _fail("H001 RNG candidate unique-result requirement lost a required fragment")
    sources = data["primary_sources"]
    if type(sources) is not list or [entry.get("source_id") if type(entry) is dict else None for entry in sources] != H001_RNG_PRIMARY_SOURCE_IDS:
        _fail("H001 RNG candidate primary-source inventory drifted")
    for entry in sources:
        entry = _keys(entry, {
            "source_id", "citation", "url_without_scheme", "what_the_source_guarantees",
            "what_the_source_does_not_guarantee", "what_qnty_chooses", "why_qnty_chooses_it",
            "rejected_alternatives",
        }, "H001 RNG candidate primary source")
        for field in ("citation", "url_without_scheme", "what_the_source_guarantees", "what_the_source_does_not_guarantee", "what_qnty_chooses", "why_qnty_chooses_it"):
            _str(entry[field], f"H001 RNG candidate primary source {field}")
        rejected = entry["rejected_alternatives"]
        if type(rejected) is not list or not rejected:
            _fail("H001 RNG candidate primary source must record rejected alternatives")
    policy = _keys(data["fixture_policy"], {
        "static_after_candidate_creation", "expected_values_must_not_be_generated_by_implementation_under_test",
        "two_structurally_independent_derivations_required", "derivation_a", "derivation_b",
        "supported_test_bound_note",
    }, "H001 RNG candidate fixture_policy")
    for field in ("static_after_candidate_creation", "expected_values_must_not_be_generated_by_implementation_under_test", "two_structurally_independent_derivations_required"):
        if policy[field] is not True:
            _fail(f"H001 RNG candidate fixture policy {field} must be true")
    payload_1 = _rng_payload_fixture(fixtures["KAT-PAYLOAD-001"], "H001 RNG candidate KAT-PAYLOAD-001")
    _rng_payload_fixture(fixtures["KAT-PAYLOAD-002"], "H001 RNG candidate KAT-PAYLOAD-002")
    if payload_1["derived_seed64"] != H001_RNG_RESEARCH_DERIVED_SEED:
        _fail("H001 RNG candidate lost the reconstructed research derived seed")
    historical = _keys(fixtures["KAT-HISTORICAL-SEEDSEQUENCE-001"], {
        "numpy_version_observed", "seed_sequence_entropy", "seed_sequence_generate_state_4_uint64",
        "philox_seedsequence_key_words", "first_four_random_raw_words", "role", "normative",
    }, "H001 RNG candidate historical SeedSequence fixture")
    if historical["normative"] is not False:
        _fail("H001 RNG candidate historical SeedSequence fixture must remain non-normative")
    if historical["seed_sequence_entropy"] != H001_RNG_RESEARCH_DERIVED_SEED or historical["first_four_random_raw_words"] != H001_RNG_RESEARCH_RAW_WORDS:
        _fail("H001 RNG candidate historical research values drifted")
    for fixture_id in ("KAT-RAW-001", "KAT-RAW-002", "KAT-RAW-003", "KAT-RAW-004", "KAT-RAW-005", "KAT-RAW-006", "KAT-RAW-007", "KAT-RAW-008", "KAT-RAW-009"):
        fixture = _keys(fixtures[fixture_id], {
            "payload_fixture", "draw_purpose", "sample_position", "attempt_index",
            "counter_word_0", "block_words", "normative_lane0_word",
        }, f"H001 RNG candidate {fixture_id}")
        if fixture["payload_fixture"] not in ("payload_1", "payload_2"):
            _fail(f"H001 RNG candidate {fixture_id} references an unknown payload fixture")
        _rng_counter_consistent(fixture, f"H001 RNG candidate {fixture_id}")
        block = fixture["block_words"]
        if type(block) is not list or len(block) != 4:
            _fail(f"H001 RNG candidate {fixture_id} must bind all four block lanes")
        for word in block:
            _rng_uint64_str(word, f"H001 RNG candidate {fixture_id} block word")
        if fixture["normative_lane0_word"] != block[0]:
            _fail(f"H001 RNG candidate {fixture_id} normative word is not lane 0")
    for fixture_id, expected_n in (("KAT-BOUNDED-N1-001", 1), ("KAT-BOUNDED-N63-001", 63), ("KAT-BOUNDED-N2193-001", 2193), ("KAT-BOUNDED-NMAX-001", H001_RNG_TWO_POW_64)):
        fixture = fixtures[fixture_id]
        _rng_bounded_fixture(fixture, f"H001 RNG candidate {fixture_id}")
        if int(fixture["bound_n"]) != expected_n:
            _fail(f"H001 RNG candidate {fixture_id} bound drifted")
    retry = _keys(fixtures["KAT-RETRY-001"], {
        "payload_fixture", "draw_purpose", "sample_position", "bound_n", "acceptance_limit",
        "raw_words_consumed", "rejected_attempt_indices", "accepted_attempt_index", "result",
    }, "H001 RNG candidate KAT-RETRY-001")
    retry_n = _rng_uint64_str(retry["bound_n"], "H001 RNG candidate retry bound", maximum=H001_RNG_TWO_POW_64)
    retry_words, retry_limit = _rng_accepted_words(retry["raw_words_consumed"], retry_n, "H001 RNG candidate KAT-RETRY-001")
    if len(retry_words) < 2:
        _fail("H001 RNG candidate retry fixture must contain at least one genuine rejection")
    if _rng_uint64_str(retry["acceptance_limit"], "H001 RNG candidate retry limit", maximum=H001_RNG_TWO_POW_64) != retry_limit:
        _fail("H001 RNG candidate retry acceptance limit drifted")
    if retry["rejected_attempt_indices"] != list(range(len(retry_words) - 1)) or retry["accepted_attempt_index"] != len(retry_words) - 1:
        _fail("H001 RNG candidate retry attempt bookkeeping drifted")
    if _rng_uint64_str(retry["result"], "H001 RNG candidate retry result") != retry_words[-1] % retry_n:
        _fail("H001 RNG candidate retry result drifted")
    exhaustion = _keys(fixtures["KAT-EXHAUSTION-001"], {
        "payload_fixture", "draw_purpose", "sample_position", "bound_n", "acceptance_limit",
        "raw_words_all_rejected", "failure_category",
    }, "H001 RNG candidate KAT-EXHAUSTION-001")
    exhaustion_n = _rng_uint64_str(exhaustion["bound_n"], "H001 RNG candidate exhaustion bound", maximum=H001_RNG_TWO_POW_64)
    exhaustion_limit = H001_RNG_TWO_POW_64 - (H001_RNG_TWO_POW_64 % exhaustion_n)
    if _rng_uint64_str(exhaustion["acceptance_limit"], "H001 RNG candidate exhaustion limit", maximum=H001_RNG_TWO_POW_64) != exhaustion_limit:
        _fail("H001 RNG candidate exhaustion acceptance limit drifted")
    rejected_words = exhaustion["raw_words_all_rejected"]
    if type(rejected_words) is not list or len(rejected_words) != H001_RNG_RETRY_CAP:
        _fail("H001 RNG candidate exhaustion fixture must consume exactly the retry cap")
    for word in rejected_words:
        if _rng_uint64_str(word, "H001 RNG candidate exhaustion word") < exhaustion_limit:
            _fail("H001 RNG candidate exhaustion fixture contains an accepted word")
    if exhaustion["failure_category"] != "H001_RNG_RETRY_CAP_EXHAUSTED":
        _fail("H001 RNG candidate exhaustion failure category drifted")
    for fixture_id in ("KAT-BERNOULLI-TRUE-001", "KAT-BERNOULLI-FALSE-001", "KAT-BERNOULLI-P0-001", "KAT-BERNOULLI-P1Q1-001"):
        _rng_bernoulli_fixture(fixtures[fixture_id], f"H001 RNG candidate {fixture_id}")
    if fixtures["KAT-BERNOULLI-TRUE-001"]["result"] is not True or fixtures["KAT-BERNOULLI-FALSE-001"]["result"] is not False:
        _fail("H001 RNG candidate Bernoulli truth fixtures drifted")
    if fixtures["KAT-BERNOULLI-P0-001"]["result"] is not False or fixtures["KAT-BERNOULLI-P1Q1-001"]["result"] is not True:
        _fail("H001 RNG candidate Bernoulli boundary fixtures drifted")
    _rng_path_fixture(fixtures["KAT-PATH-001"], "H001 RNG candidate KAT-PATH-001", wraparound_required=False)
    _rng_path_fixture(fixtures["KAT-PATH-002"], "H001 RNG candidate KAT-PATH-002", wraparound_required=True)
    non_effects = _list(data["non_effects"], "H001 RNG candidate non_effects", sorted_unique=True)
    for required in ("BLOCK_LIVE_INTEGRATION", "EDGE_UNPROVEN", "CANDIDATE_NOT_EFFECTIVE", "CANDIDATE_NOT_ACTIVATED", "CALIBRATION_EXECUTION_NOT_AUTHORIZED", "INDEPENDENT_REVIEW_REQUIRED", "NO_REAL_DATA_ACCESS"):
        if required not in non_effects:
            _fail(f"H001 RNG candidate non_effects lost {required}")
    _walk_forbidden(data)
    _rng_scan_placeholders(data)
    return data


def load_and_validate_h001_rng_runtime_amendment_candidate(raw: bytes) -> dict:
    if type(raw) is not bytes:
        _fail("exact bytes input required")
    try:
        parsed = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_json_keys)
    except (UnicodeDecodeError, json.JSONDecodeError, AssuranceValidationError) as error:
        raise AssuranceValidationError("strict UTF-8 JSON without duplicate keys required") from error
    if canonical_json_bytes(parsed) != raw:
        _fail("non-canonical JSON bytes")
    return validate_h001_rng_runtime_amendment_candidate(parsed)
