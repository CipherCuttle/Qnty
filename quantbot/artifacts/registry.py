"""Git-owned artifact records and the provider-neutral store registry (stdlib only).

An artifact record (``docs/artifacts/<artifact_id>.json``) is the single
source of truth for one frozen research input. It separates:

- portable content identity (``portable_manifest_sha256``);
- legacy protocol identities (``legacy_bindings`` -- historical, immutable,
  path-sensitive fingerprints that are *not* portable content digests);
- storage copies (``copies`` -- canonical ``qnty-artifact://`` locations plus
  per-copy object and restore verification receipts);
- availability (``UNAVAILABLE`` or ``VERIFIED_AVAILABLE``).

``VERIFIED_AVAILABLE`` fails closed unless a portable manifest identity is
bound and at least two fully verified, independently restored copies exist in
distinct stores with distinct failure domains. Directories in the same
failure domain never count as independent durable copies.

Canonical artifact locations are stable store URIs, never ephemeral
materialization paths: ``/tmp`` and ``/srv/qnty`` are workspaces or
production surfaces, never canonical storage.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from quantbot.artifacts.store import FilesystemStore, require_allowed_canonical_root

__all__ = [
    "ARTIFACT_RECORD_KIND",
    "PROHIBITED_CANONICAL_LOCATION_PREFIXES",
    "REGISTRY_SCHEMA_VERSION",
    "STORE_REGISTRY_KIND",
    "ArtifactRegistryError",
    "canonical_location",
    "cross_check_receipt_artifact",
    "validate_artifact_record_bytes",
    "validate_operational_registry",
    "validate_registry_tree",
    "validate_store_registry_bytes",
]

ARTIFACT_RECORD_KIND = "qnty_artifact_record"
STORE_REGISTRY_KIND = "qnty_artifact_store_registry"
REGISTRY_SCHEMA_VERSION = "1.0.0"

ARTIFACT_RECORDS_DIR_RELPATH = "docs/artifacts"
STORE_REGISTRY_RELPATH = "docs/artifacts/stores.json"

PROHIBITED_CANONICAL_LOCATION_PREFIXES = ("/tmp", "/srv/qnty")

_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_ARTIFACT_ID_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}")
_STORE_ID_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
_BACKEND_KIND_RE = re.compile(r"[a-z][a-z0-9_-]{0,63}")
_FAILURE_DOMAIN_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}")
_ENV_VAR_RE = re.compile(r"[A-Z][A-Z0-9_]{0,127}")
_CANONICAL_LOCATION_RE = re.compile(
    r"qnty-artifact://(?P<store_id>[a-z0-9][a-z0-9-]{0,63})/sha256/(?P<manifest_sha256>[0-9a-f]{64})"
)

_AVAILABILITY_STATES = ("UNAVAILABLE", "VERIFIED_AVAILABLE")

_RECORD_KEYS = {
    "artifact_id",
    "artifact_record_kind",
    "availability",
    "copies",
    "expected_roles",
    "legacy_bindings",
    "portable_manifest_sha256",
    "schema_version",
}
_LEGACY_BINDING_KEYS = {
    "legacy_input_manifest_fingerprint",
    "nested_first_statistic_data_binding",
    "outer_data_cut_fingerprint",
    "protocol_id",
}
_COPY_KEYS = {
    "canonical_location",
    "failure_domain",
    "manifest_sha256",
    "object_verification",
    "restore_verification",
    "store_id",
}
_OBJECT_VERIFICATION_KEYS = {"passed", "verified_object_count"}
_RESTORE_VERIFICATION_KEYS = {"passed", "restored_manifest_sha256"}

_STORE_REGISTRY_KEYS = {"schema_version", "store_registry_kind", "stores"}
_STORE_KEYS = {
    "backend_kind",
    "failure_domain",
    "read_enabled",
    "root_environment_variable",
    "store_id",
    "write_enabled",
}


class ArtifactRegistryError(ValueError):
    """Fail-closed artifact-registry violation."""


def _fail(message: str) -> None:
    raise ArtifactRegistryError(f"artifact registry violation: {message}")


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _require_exact_keys(value: object, expected: set, label: str) -> dict:
    if type(value) is not dict:
        _fail(f"{label} must be a JSON object")
    if set(value) != expected:
        missing = sorted(expected - set(value))
        extra = sorted(set(value) - expected)
        _fail(f"{label} keys mismatch (missing={missing} extra={extra})")
    return value


def _require_str(value: object, label: str, pattern: re.Pattern | None = None) -> str:
    if type(value) is not str or not value:
        _fail(f"{label} must be a non-empty string")
    if pattern is not None and not pattern.fullmatch(value):
        _fail(f"{label} value {value!r} is malformed")
    return value


def _require_sha256(value: object, label: str) -> str:
    if type(value) is not str or not _SHA256_RE.fullmatch(value):
        _fail(f"{label} must be a lowercase hex sha256")
    return value


def _require_int(value: object, label: str) -> int:
    if type(value) is not int:
        _fail(f"{label} must be an int (bool is not accepted)")
    return value


def _require_bool(value: object, label: str) -> bool:
    if type(value) is not bool:
        _fail(f"{label} must be a bool")
    return value


def _load_canonical_document(data: bytes, label: str) -> dict:
    try:
        parsed = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        _fail(f"{label} is not strict UTF-8 JSON")
    if type(parsed) is not dict:
        _fail(f"{label} must be a JSON object")
    if data.endswith(b"\n") or data != _canonical_json_bytes(parsed):
        _fail(f"{label} is not canonical QNTY JSON (sorted keys, compact, ASCII, no trailing newline)")
    return parsed


def canonical_location(store_id: str, manifest_sha256: str) -> str:
    """The stable logical location of a manifest inside one store."""
    _require_str(store_id, "store_id", _STORE_ID_RE)
    _require_sha256(manifest_sha256, "manifest_sha256")
    return f"qnty-artifact://{store_id}/sha256/{manifest_sha256}"


def _require_canonical_location(value: object, label: str) -> re.Match:
    location = _require_str(value, label)
    for prefix in PROHIBITED_CANONICAL_LOCATION_PREFIXES:
        if location == prefix or location.startswith(prefix + "/"):
            _fail(f"{label} {location!r} is under prohibited prefix {prefix!r}; workspaces are never canonical")
    match = _CANONICAL_LOCATION_RE.fullmatch(location)
    if match is None:
        _fail(f"{label} {location!r} is not a qnty-artifact://<store-id>/sha256/<manifest-sha256> URI")
    return match


# -- store registry ------------------------------------------------------


def validate_store_registry_bytes(data: bytes) -> dict:
    """Strict fail-closed validation of the provider-neutral store registry."""
    parsed = _load_canonical_document(data, "store registry")
    _require_exact_keys(parsed, _STORE_REGISTRY_KEYS, "store registry")
    if parsed["store_registry_kind"] != STORE_REGISTRY_KIND:
        _fail("store_registry_kind is wrong")
    if parsed["schema_version"] != REGISTRY_SCHEMA_VERSION:
        _fail(f"store registry schema_version is not {REGISTRY_SCHEMA_VERSION}")
    stores = parsed["stores"]
    if type(stores) is not list:
        _fail("stores must be a list (empty until real stores are configured)")
    seen_ids: set = set()
    seen_environment_variables: set = set()
    for store in stores:
        _require_exact_keys(store, _STORE_KEYS, "store entry")
        store_id = _require_str(store["store_id"], "store_id", _STORE_ID_RE)
        if store_id in seen_ids:
            _fail(f"duplicate store_id {store_id!r}")
        seen_ids.add(store_id)
        _require_str(store["backend_kind"], "backend_kind", _BACKEND_KIND_RE)
        _require_str(store["failure_domain"], "failure_domain", _FAILURE_DOMAIN_RE)
        environment_variable = _require_str(
            store["root_environment_variable"], "root_environment_variable", _ENV_VAR_RE
        )
        if environment_variable in seen_environment_variables:
            _fail(f"duplicate root_environment_variable {environment_variable!r}")
        seen_environment_variables.add(environment_variable)
        _require_bool(store["read_enabled"], "read_enabled")
        _require_bool(store["write_enabled"], "write_enabled")
    return parsed


# -- artifact records ----------------------------------------------------


def _validate_copy(copy: object, portable_manifest_sha256: str) -> dict:
    _require_exact_keys(copy, _COPY_KEYS, "copy record")
    store_id = _require_str(copy["store_id"], "copy store_id", _STORE_ID_RE)
    _require_str(copy["failure_domain"], "copy failure_domain", _FAILURE_DOMAIN_RE)
    manifest_sha = _require_sha256(copy["manifest_sha256"], "copy manifest_sha256")
    if manifest_sha != portable_manifest_sha256:
        _fail("copy manifest_sha256 does not reference the record's portable manifest")
    match = _require_canonical_location(copy["canonical_location"], "copy canonical_location")
    if match.group("store_id") != store_id:
        _fail("copy canonical_location does not embed the copy's store_id")
    if match.group("manifest_sha256") != manifest_sha:
        _fail("copy canonical_location does not embed the copy's manifest_sha256")
    object_verification = _require_exact_keys(
        copy["object_verification"], _OBJECT_VERIFICATION_KEYS, "object_verification"
    )
    if _require_bool(object_verification["passed"], "object_verification passed") is not True:
        _fail("copy has not passed full object verification")
    count = _require_int(object_verification["verified_object_count"], "verified_object_count")
    if count < 1:
        _fail("object_verification verified_object_count must be >= 1")
    restore_verification = _require_exact_keys(
        copy["restore_verification"], _RESTORE_VERIFICATION_KEYS, "restore_verification"
    )
    if _require_bool(restore_verification["passed"], "restore_verification passed") is not True:
        _fail("copy has not passed an independent restore test")
    restored_sha = _require_sha256(
        restore_verification["restored_manifest_sha256"], "restored_manifest_sha256"
    )
    if restored_sha != portable_manifest_sha256:
        _fail("copy restore test did not reproduce the portable manifest exactly")
    return copy


def validate_artifact_record_bytes(data: bytes, *, expected_artifact_id: str | None = None) -> dict:
    """Strict fail-closed validation of one Git-owned artifact record."""
    parsed = _load_canonical_document(data, "artifact record")
    _require_exact_keys(parsed, _RECORD_KEYS, "artifact record")
    if parsed["artifact_record_kind"] != ARTIFACT_RECORD_KIND:
        _fail("artifact_record_kind is wrong")
    if parsed["schema_version"] != REGISTRY_SCHEMA_VERSION:
        _fail(f"artifact record schema_version is not {REGISTRY_SCHEMA_VERSION}")
    artifact_id = _require_str(parsed["artifact_id"], "artifact_id", _ARTIFACT_ID_RE)
    if expected_artifact_id is not None and artifact_id != expected_artifact_id:
        _fail(f"artifact_id {artifact_id!r} does not match expected {expected_artifact_id!r}")
    availability = _require_str(parsed["availability"], "availability")
    if availability not in _AVAILABILITY_STATES:
        _fail("availability must be UNAVAILABLE or VERIFIED_AVAILABLE")
    legacy = _require_exact_keys(parsed["legacy_bindings"], _LEGACY_BINDING_KEYS, "legacy_bindings")
    _require_sha256(legacy["legacy_input_manifest_fingerprint"], "legacy_input_manifest_fingerprint")
    _require_sha256(legacy["outer_data_cut_fingerprint"], "outer_data_cut_fingerprint")
    _require_sha256(legacy["nested_first_statistic_data_binding"], "nested_first_statistic_data_binding")
    _require_str(legacy["protocol_id"], "legacy_bindings protocol_id")
    roles = parsed["expected_roles"]
    if type(roles) is not list or not roles:
        _fail("expected_roles must be a non-empty list of role names")
    for role in roles:
        _require_str(role, "expected_roles entry", re.compile(r"[a-z][a-z0-9_-]{0,63}"))
    if sorted(roles) != roles or len(set(roles)) != len(roles):
        _fail("expected_roles must be sorted and unique")
    portable = parsed["portable_manifest_sha256"]
    if portable is not None:
        _require_sha256(portable, "portable_manifest_sha256")
    copies = parsed["copies"]
    if type(copies) is not list:
        _fail("copies must be a list")
    if copies and portable is None:
        _fail("copies cannot exist without a bound portable_manifest_sha256")
    seen_store_ids: set = set()
    seen_locations: set = set()
    failure_domains: list = []
    for copy in copies:
        validated = _validate_copy(copy, portable)
        if validated["store_id"] in seen_store_ids:
            _fail("two copies in the same store do not count as independent copies")
        seen_store_ids.add(validated["store_id"])
        if validated["canonical_location"] in seen_locations:
            _fail("duplicate canonical_location cannot evidence independent copies")
        seen_locations.add(validated["canonical_location"])
        failure_domains.append(validated["failure_domain"])
    if availability == "UNAVAILABLE":
        if copies:
            _fail("UNAVAILABLE artifact must not record copies")
    if availability == "VERIFIED_AVAILABLE":
        if portable is None:
            _fail("VERIFIED_AVAILABLE requires a bound portable_manifest_sha256")
        if len(copies) < 2:
            _fail("VERIFIED_AVAILABLE requires at least two independently verified copies")
        if len(set(failure_domains)) < 2:
            _fail("copies share a failure domain; same-domain copies are not independent")
    return parsed


def _cross_check_copies_against_stores(record: dict, store_registry: dict) -> None:
    stores_by_id = {store["store_id"]: store for store in store_registry["stores"]}
    for copy in record["copies"]:
        store = stores_by_id.get(copy["store_id"])
        if store is None:
            _fail(f"copy references store_id {copy['store_id']!r} which is missing from the store registry")
        if store["failure_domain"] != copy["failure_domain"]:
            _fail(
                f"copy failure_domain {copy['failure_domain']!r} does not match store registry "
                f"failure_domain {store['failure_domain']!r} for store {copy['store_id']!r}"
            )


def cross_check_receipt_artifact(receipt_artifact: dict, record: dict, store_registry: dict) -> None:
    """Cross-check one handoff-receipt artifact summary against its Git-owned record.

    Fails closed on any divergence between the receipt summary and the
    artifact record: identity, legacy fingerprint, availability, copy count,
    or canonical locations.
    """
    if record["artifact_id"] != receipt_artifact["artifact_id"]:
        _fail("artifact record artifact_id differs from the handoff receipt")
    legacy = record["legacy_bindings"]["legacy_input_manifest_fingerprint"]
    if legacy != receipt_artifact["expected_manifest_sha256"]:
        _fail("artifact record legacy fingerprint differs from the handoff receipt")
    if record["availability"] != receipt_artifact["availability"]:
        _fail("artifact record availability differs from the handoff receipt")
    if len(record["copies"]) != receipt_artifact["verified_copy_count"]:
        _fail("artifact record copy count differs from the handoff receipt")
    record_locations = sorted(copy["canonical_location"] for copy in record["copies"])
    if record_locations != sorted(receipt_artifact["canonical_paths"]):
        _fail("artifact record canonical locations differ from the handoff receipt")
    if record["availability"] == "VERIFIED_AVAILABLE" and record["portable_manifest_sha256"] is None:
        _fail("portable manifest is missing while availability is VERIFIED_AVAILABLE")
    _cross_check_copies_against_stores(record, store_registry)


# -- registry tree validation ---------------------------------------------


def validate_registry_tree(root: Path) -> dict:
    """Validate the committed registry files under docs/artifacts/ as a whole."""
    root = Path(root)
    registry_path = root / STORE_REGISTRY_RELPATH
    if not registry_path.is_file():
        _fail(f"store registry {STORE_REGISTRY_RELPATH} is missing")
    store_registry = validate_store_registry_bytes(registry_path.read_bytes())
    records_dir = root / ARTIFACT_RECORDS_DIR_RELPATH
    records: dict = {}
    for path in sorted(records_dir.glob("*.json")):
        if path.name == "stores.json":
            continue
        data = path.read_bytes()
        record = validate_artifact_record_bytes(data, expected_artifact_id=path.stem)
        _cross_check_copies_against_stores(record, store_registry)
        records[record["artifact_id"]] = {
            "record": record,
            "relpath": f"{ARTIFACT_RECORDS_DIR_RELPATH}/{path.name}",
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    if not records:
        _fail("no artifact records found under docs/artifacts/")
    return {"records": records, "store_registry": store_registry}


def _filesystem_identity(root: Path) -> tuple[str, int]:
    """Return the runtime identity used to reject non-independent roots."""
    resolved = require_allowed_canonical_root(root)
    if not resolved.exists():
        _fail(f"configured store root {str(resolved)!r} does not exist")
    if not resolved.is_dir():
        _fail(f"configured store root {str(resolved)!r} is not a directory")
    try:
        return str(resolved), os.stat(resolved).st_dev
    except OSError as error:
        _fail(f"configured store root {str(resolved)!r} cannot be statted: {error}")


def validate_operational_registry(root: Path, *, registry_tree: dict | None = None) -> dict:
    """Read-only current verification for statically ``VERIFIED_AVAILABLE`` records.

    Static receipts preserve historical evidence.  This layer establishes only
    present operational availability by resolving configured roots and fully
    rehashing every referenced filesystem-store copy.
    """
    root = Path(root)
    tree = validate_registry_tree(root) if registry_tree is None else registry_tree
    stores = {store["store_id"]: store for store in tree["store_registry"]["stores"]}
    used: dict[str, tuple[dict, Path, tuple[str, int]]] = {}
    for entry in tree["records"].values():
        record = entry["record"]
        if record["availability"] != "VERIFIED_AVAILABLE":
            continue
        for copy in record["copies"]:
            store = stores[copy["store_id"]]
            if store["read_enabled"] is not True:
                _fail(f"store {store['store_id']!r} is not read-enabled for live verification")
            if store["backend_kind"] != "filesystem":
                _fail(f"store {store['store_id']!r} backend {store['backend_kind']!r} is unsupported by live verification")
            variable = store["root_environment_variable"]
            configured_root = os.environ.get(variable)
            if not configured_root:
                _fail(f"store {store['store_id']!r} environment variable {variable!r} is unset or empty")
            identity = _filesystem_identity(Path(configured_root))
            used[store["store_id"]] = (store, Path(identity[0]), identity)

    used_values = list(used.values())
    for index, (left_store, left_root, left_identity) in enumerate(used_values):
        for right_store, right_root, right_identity in used_values[index + 1:]:
            if left_store["root_environment_variable"] == right_store["root_environment_variable"]:
                _fail("independent stores share a root_environment_variable declaration")
            if left_identity[0] == right_identity[0] or os.path.samefile(left_root, right_root):
                _fail("independent stores resolve to the same filesystem root")
            if left_identity[1] == right_identity[1]:
                _fail("independent stores share a filesystem device identity")

    for entry in tree["records"].values():
        record = entry["record"]
        if record["availability"] != "VERIFIED_AVAILABLE":
            continue
        for copy in record["copies"]:
            store, configured_root, _ = used[copy["store_id"]]
            report = FilesystemStore(configured_root, canonical=True).verify_copy(copy["manifest_sha256"])
            if report["artifact_id"] != record["artifact_id"]:
                _fail(f"store {store['store_id']!r} manifest artifact_id does not match {record['artifact_id']!r}")
            if report["verified_object_count"] != copy["object_verification"]["verified_object_count"]:
                _fail(f"store {store['store_id']!r} verified object count differs from recorded evidence")
    return tree
