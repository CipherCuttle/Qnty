"""Durable artifact plane v1 (governance + identity layer, stdlib only).

Provider-neutral, content-addressed identity and verification for frozen
research inputs. Three layers:

- ``manifest``: portable artifact manifest v1 -- the scientific content
  identity of a role-partitioned file set. Path-free hash domain.
- ``store``: content-addressed filesystem store backend with atomic,
  fail-closed ingest / verify / restore.
- ``registry``: Git-owned artifact records and the provider-neutral store
  registry, including the two-independent-copy availability contract.

This package never reads market data, ledgers, or quarantine content and
never claims a missing artifact has been recovered.
"""

from quantbot.artifacts.manifest import (
    build_portable_manifest,
    canonical_json_bytes,
    portable_manifest_sha256,
    validate_manifest_bytes,
    validate_manifest_object,
)
from quantbot.artifacts.registry import (
    validate_artifact_record_bytes,
    validate_store_registry_bytes,
)
from quantbot.artifacts.store import FilesystemStore

__all__ = [
    "FilesystemStore",
    "build_portable_manifest",
    "canonical_json_bytes",
    "portable_manifest_sha256",
    "validate_artifact_record_bytes",
    "validate_manifest_bytes",
    "validate_manifest_object",
    "validate_store_registry_bytes",
]
