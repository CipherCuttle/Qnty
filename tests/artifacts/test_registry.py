"""Synthetic tests for Git-owned artifact records and store registry v1."""

import copy
import hashlib

import pytest

from quantbot.artifacts.manifest import canonical_json_bytes
from quantbot.artifacts.registry import (
    ArtifactRegistryError,
    canonical_location,
    cross_check_receipt_artifact,
    validate_artifact_record_bytes,
    validate_store_registry_bytes,
)

LEGACY = "3dec994114769a16939afa9b0041a8162a308dcb05ca196557407b26a0d35b0d"
PORTABLE = "a" * 64


def stores():
    return {
        "schema_version": "1.0.0",
        "store_registry_kind": "qnty_artifact_store_registry",
        "stores": [
            {"backend_kind": "filesystem", "failure_domain": "domain-a", "read_enabled": True, "root_environment_variable": "SYNTHETIC_STORE_A", "store_id": "store-a", "write_enabled": True},
            {"backend_kind": "filesystem", "failure_domain": "domain-b", "read_enabled": True, "root_environment_variable": "SYNTHETIC_STORE_B", "store_id": "store-b", "write_enabled": True},
        ],
    }


def record(*, availability="UNAVAILABLE", copies=None):
    copies = [] if copies is None else copies
    return {
        "artifact_id": "candidate1-real-input-v0",
        "artifact_record_kind": "qnty_artifact_record",
        "availability": availability,
        "copies": copies,
        "expected_roles": ["bars", "funding"],
        "legacy_bindings": {"legacy_input_manifest_fingerprint": LEGACY, "nested_first_statistic_data_binding": "7c8552f10cf8f72c859335a5f4af8ca36094bffed695428a9c93a1033ef86c6f", "outer_data_cut_fingerprint": "020eac5e9659138e4c66b2fb2b44020a9b894b0500f51fd935014c5b37f55224", "protocol_id": "real_btc_candidate1_train_mechanism_decomposition_v0"},
        "portable_manifest_sha256": PORTABLE if copies else None,
        "schema_version": "1.0.0",
    }


def copy_record(store_id, domain):
    return {"canonical_location": canonical_location(store_id, PORTABLE), "failure_domain": domain, "manifest_sha256": PORTABLE, "object_verification": {"passed": True, "verified_object_count": 3}, "restore_verification": {"passed": True, "restored_manifest_sha256": PORTABLE}, "store_id": store_id}


def receipt_summary(availability="UNAVAILABLE", copies=()):
    return {"artifact_id": "candidate1-real-input-v0", "availability": availability, "canonical_paths": [item["canonical_location"] for item in copies], "expected_manifest_sha256": LEGACY, "verified_copy_count": len(copies)}


def validate(value):
    return validate_artifact_record_bytes(canonical_json_bytes(value), expected_artifact_id="candidate1-real-input-v0")


def test_unavailable_zero_copies_passes_and_portable_manifest_is_null():
    parsed = validate(record())
    assert parsed["availability"] == "UNAVAILABLE"
    assert parsed["copies"] == []
    assert parsed["portable_manifest_sha256"] is None


def test_unavailable_with_copy_rejects():
    with pytest.raises(ArtifactRegistryError, match="UNAVAILABLE"):
        validate(record(copies=[copy_record("store-a", "domain-a")]))


def test_verified_available_requires_two_independent_verified_restored_copies():
    one = [copy_record("store-a", "domain-a")]
    with pytest.raises(ArtifactRegistryError, match="at least two"):
        validate(record(availability="VERIFIED_AVAILABLE", copies=one))
    two = [copy_record("store-a", "domain-a"), copy_record("store-b", "domain-b")]
    parsed = validate(record(availability="VERIFIED_AVAILABLE", copies=two))
    cross_check_receipt_artifact(receipt_summary("VERIFIED_AVAILABLE", two), parsed, validate_store_registry_bytes(canonical_json_bytes(stores())))


@pytest.mark.parametrize("mutation", [
    lambda copies: copies.__setitem__(1, copy_record("store-a", "domain-b")),
    lambda copies: copies.__setitem__(1, {**copy_record("store-b", "domain-b"), "canonical_location": canonical_location("store-a", PORTABLE)}),
    lambda copies: copies.__setitem__(1, copy_record("store-b", "domain-a")),
    lambda copies: copies[0]["object_verification"].update(passed=False),
    lambda copies: copies[0]["restore_verification"].update(restored_manifest_sha256="b" * 64),
])
def test_verified_copy_independence_and_receipts_are_required(mutation):
    copies = [copy_record("store-a", "domain-a"), copy_record("store-b", "domain-b")]
    mutation(copies)
    with pytest.raises(ArtifactRegistryError):
        validate(record(availability="VERIFIED_AVAILABLE", copies=copies))


def test_cross_check_rejects_missing_store_and_legacy_or_copy_count_drift():
    copies = [copy_record("store-a", "domain-a"), copy_record("store-b", "domain-b")]
    parsed = validate(record(availability="VERIFIED_AVAILABLE", copies=copies))
    bad_stores = stores()
    bad_stores["stores"] = bad_stores["stores"][:1]
    with pytest.raises(ArtifactRegistryError, match="missing from the store registry"):
        cross_check_receipt_artifact(receipt_summary("VERIFIED_AVAILABLE", copies), parsed, validate_store_registry_bytes(canonical_json_bytes(bad_stores)))
    bad_receipt = receipt_summary("VERIFIED_AVAILABLE", copies)
    bad_receipt["expected_manifest_sha256"] = "f" * 64
    with pytest.raises(ArtifactRegistryError, match="legacy fingerprint"):
        cross_check_receipt_artifact(bad_receipt, parsed, validate_store_registry_bytes(canonical_json_bytes(stores())))
    bad_receipt = receipt_summary("VERIFIED_AVAILABLE", copies)
    bad_receipt["verified_copy_count"] = 1
    with pytest.raises(ArtifactRegistryError, match="copy count"):
        cross_check_receipt_artifact(bad_receipt, parsed, validate_store_registry_bytes(canonical_json_bytes(stores())))


def test_registry_documents_are_canonical_and_strict():
    with pytest.raises(ArtifactRegistryError, match="canonical"):
        validate_artifact_record_bytes(canonical_json_bytes(record()) + b"\n")
    malformed = copy.deepcopy(stores())
    malformed["stores"][0]["read_enabled"] = 1
    with pytest.raises(ArtifactRegistryError, match="bool"):
        validate_store_registry_bytes(canonical_json_bytes(malformed))
    malformed = copy.deepcopy(stores())
    malformed["stores"].append(copy.deepcopy(malformed["stores"][0]))
    with pytest.raises(ArtifactRegistryError, match="duplicate"):
        validate_store_registry_bytes(canonical_json_bytes(malformed))


def test_legacy_fingerprint_is_preserved_exactly():
    assert validate(record())["legacy_bindings"]["legacy_input_manifest_fingerprint"] == LEGACY
    assert hashlib.sha256(canonical_json_bytes(record())).hexdigest() == hashlib.sha256(canonical_json_bytes(record())).hexdigest()
