"""Pure validation for the Candidate 1 decomposition qualification binding."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping

__all__ = ["validate_candidate1_decomposition_implementation_binding_v0"]

_SHA256 = re.compile(r"[0-9a-f]{64}")
_COMMIT = re.compile(r"[0-9a-f]{40}")
_SOURCE_DIGEST = "f4a3bfd647a2e32c25cd7dfd2531821376af2878a1a1fa1b09d8fa2f8b9aa019"
_RECEIPT_SHA = "2f36380dcc4120473718ce35a68abd2ef4952dc89205d8300d852332751f45a3"

_SOURCE_FILES = [
    {"path": "quantbot/experiment/offline_edge_real_validation.py", "sha256": "c1b34cfea9ffbf2866dc33e6f77d341e52f4a672f7a5b2dfcb21c22556e388b9"},
    {"path": "quantbot/experiment/offline_edge_input_manifest.py", "sha256": "309644fea6e3d201627bab83910bc5665e068f6200356774043cc7fe43221610"},
    {"path": "tests/experiment/test_offline_edge_candidate1_train_mechanism_decomposition.py", "sha256": "992455888aca4fd3ec2d08f9e968be584dbdcd908f544e6c8c3959c22a68cfd3"},
    {"path": "tests/experiment/test_offline_edge_first_computed_statistic.py", "sha256": "5f158e41f524947bf367c8f27f444097b9467cb5e1f0a4d90d0a565654bf7248"},
    {"path": "docs/registries/real_btc_candidate1_train_mechanism_decomposition_registry.json", "sha256": "1486c298580e6801ac38c21f0d884cfdbd00a3029cb38198611e2027230e1144"},
    {"path": "docs/status/QNTY_REAL_BTC_CANDIDATE1_TRAIN_MECHANISM_DECOMPOSITION_V0.md", "sha256": "6262c7c59658284dcca790199669ab985e23443ba48a59ec7c20cf07ad43e51a"},
]

_RECEIPT = {
    "binding_kind": "candidate1_decomposition_implementation_environment_qualification_v0", "binding_schema_version": "0.1.0",
    "precondition_state": {"this_preregistration_pr_merged": "satisfied", "separate_implementation_pr_reviewed_and_merged": "satisfied", "implementation_fingerprint_or_commit_bound": "satisfied", "final_no_computation_preflight_passed": "not_yet_satisfied"},
    "protocol_id": "real_btc_candidate1_train_mechanism_decomposition_v0",
    "qualification": {"qualification_log_manifest_sha256": "0f769a9ee15b19933cc6135ca1c6d048ac76aac6564d57ed7f2a829065e0f2d7", "focused": {"exit_code": 0, "log_sha256": "b5a386f3e65e5bcc5bf5fd4edd7d7975531a9ad25fbaf12c500ab966809e10bb", "passed": 384}, "release_smoke": {"exit_code": 0, "log_sha256": "2532d4aa4dd42d8f3895e2be342687d2692275beac09f314ddcc6cedeb0c0797", "passed": 6}, "full_suite": {"duration_seconds": 169, "exit_code": 0, "failed": 0, "log_sha256": "4cac7ae9392bab7e5b1dad9c1e0c81f8c94900672f7f5c922fa1eb8a89165267", "passed": 5081, "skipped": 0, "xfail": 0}},
    "qualified_environment": {"architecture": "x86_64", "canonical_location_context": "/home/viktor/qnty-research/candidate1-decomposition-v0", "environment_manifest_sha256": "25f92f2c99f989de7553930ef09ff34e39d9893bcf008cbfd6992a242312b213", "installed_packages_sha256": "d077b61bbda465c876573fa281a53ada997b4fa26b5794a7e0d9f2ff121a61bf", "package_count": 14, "package_lock_kind": "hash_locked_binary_wheels", "python_implementation": "CPython", "python_soabi": "cpython-312-x86_64-linux-gnu", "python_version": "3.12.3", "requirements_exact_sha256": "d077b61bbda465c876573fa281a53ada997b4fa26b5794a7e0d9f2ff121a61bf", "requirements_hashed_sha256": "164d3c6727453b29d4bf590a657bc2a39be9ec9130a6bd9b916266cc8225bae5", "wheelhouse_manifest_sha256": "41e6d87d27f3b9f717500a2e85c922ae4ba746ac46ad22e070cc7595a6593a26"},
    "qualified_implementation": {"feature_parent_sha": "e7720aa9c4fd1b2aa534b1e1119c03f6e674e9e6", "main_parent_sha": "e992f9539e7a6a352cff65d3cb1a5441547040a6", "merge_commit_sha": "6d4b0c7fd11afe614edb0d1070ef4a9637e91542", "qualified_source_files": _SOURCE_FILES, "qualified_source_manifest_sha256": "1ca8627b49e326d8fa6c55e0a52dc0d3e26e1cc96e203840ca7a77524e76d7a5"},
    "safety_snapshot": {"decomposition_execution_budget": 1, "decomposition_execution_count": 0, "decomposition_executed": False, "edge_status": "EDGE_UNPROVEN", "live_integration_authorized": False, "live_status": "BLOCK_LIVE_INTEGRATION", "paper_trade_authorized": False, "quarantine_access": "forbidden", "real_data_executed": False, "scientific_use_authorized": False},
    "source_binding_canonical_json_sha256": _SOURCE_DIGEST,
}

_BINDING = {"binding_kind": _RECEIPT["binding_kind"], "binding_receipt_path": "docs/receipts/real_btc_candidate1_train_mechanism_decomposition_v0/implementation_binding_v0.json", "binding_receipt_sha256": _RECEIPT_SHA, "qualified_environment_manifest_sha256": _RECEIPT["qualified_environment"]["environment_manifest_sha256"], "qualified_implementation_commit": _RECEIPT["qualified_implementation"]["merge_commit_sha"], "qualified_source_manifest_sha256": _RECEIPT["qualified_implementation"]["qualified_source_manifest_sha256"]}


def _same(actual: object, expected: object) -> bool:
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return set(actual) == set(expected) and all(_same(actual[key], value) for key, value in expected.items())
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(_same(a, e) for a, e in zip(actual, expected))
    return actual == expected


def _validate_digests(receipt: Mapping[str, object]) -> None:
    for value in (receipt["source_binding_canonical_json_sha256"], receipt["qualified_environment"]["environment_manifest_sha256"], receipt["qualified_implementation"]["qualified_source_manifest_sha256"], receipt["qualification"]["qualification_log_manifest_sha256"]):
        if type(value) is not str or not _SHA256.fullmatch(value):
            raise ValueError("malformed receipt digest")
    for item in receipt["qualified_implementation"]["qualified_source_files"]:
        if not _SHA256.fullmatch(item["sha256"]):
            raise ValueError("malformed source hash")
        path = item["path"]
        if not path or path.startswith("/") or ".." in path.split("/"):
            raise ValueError("source path is not repository-relative")
    for key in ("feature_parent_sha", "main_parent_sha", "merge_commit_sha"):
        if not _COMMIT.fullmatch(receipt["qualified_implementation"][key]):
            raise ValueError("malformed commit")


def validate_candidate1_decomposition_implementation_binding_v0(entry: Mapping[str, object], receipt_bytes: bytes) -> dict[str, object]:
    """Validate the canonical, non-executing Candidate 1 binding artifacts."""
    if not isinstance(entry, Mapping) or type(receipt_bytes) is not bytes:
        raise ValueError("entry must be a mapping and receipt_bytes must be bytes")
    try:
        parsed = json.loads(receipt_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("receipt is not strict UTF-8 JSON") from error
    if type(parsed) is not dict:
        raise ValueError("receipt must be a JSON object")
    canonical = json.dumps(parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    if receipt_bytes != canonical or receipt_bytes.endswith(b"\n"):
        raise ValueError("receipt is not canonical")
    if hashlib.sha256(receipt_bytes).hexdigest() != _RECEIPT_SHA or not _same(parsed, _RECEIPT):
        raise ValueError("receipt facts do not match qualification")
    _validate_digests(parsed)
    binding = entry.get("implementation_binding")
    if not _same(binding, _BINDING):
        raise ValueError("implementation binding does not match qualification")
    source = entry.get("source_binding")
    if not isinstance(source, Mapping):
        raise ValueError("source binding is missing")
    source_bytes = json.dumps(source, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    if hashlib.sha256(source_bytes).hexdigest() != _SOURCE_DIGEST or source.get("bound_implementation_sha") != "e1b493e22403a228e9d3994e7a39a0f02fbb2bcc":
        raise ValueError("historical source binding changed")
    safety = entry.get("authorization_state")
    expected_safety = {"scientific_use_authorized": False, "paper_trade_authorized": False, "live_integration_authorized": False, "edge_status": "EDGE_UNPROVEN", "live_status": "BLOCK_LIVE_INTEGRATION"}
    if type(entry.get("decomposition_execution_budget")) is not int or entry.get("decomposition_execution_budget") != 1 or type(entry.get("decomposition_execution_count")) is not int or entry.get("decomposition_execution_count") != 0 or entry.get("quarantine_access") != "forbidden" or not _same(safety, expected_safety):
        raise ValueError("registry safety state changed")
    return parsed
