"""Immutable funding-source bundle semantics (v1).

A funding-source *bundle* is an immutable, content-addressed freeze of the
funding rows a committed snapshot was built against. It exists so the clean-carry
verifier can validate against frozen bytes instead of the live, mutable
``data/*_8h_funding.csv`` files, which are rewritten on a schedule
(``qnty-data-refresh.timer``) and therefore race any verifier run (see PR #104).

Design (see ``docs/specs/funding_source_immutable_bundle_semantics_v0.md``):

* The bundle freezes the canonical funding rows extracted from the committed
  snapshot envelope's window records, plus the per-file source digests recorded
  at capture time.
* ``source_bundle_sha256`` content-addresses the frozen canonical rows; the
  bundle file is named by it. Recomputing that hash over the stored rows is the
  self-integrity check (tamper a row -> hash no longer recomputes).
* ``snapshot_bundle_sha256`` binds the bundle to a specific committed snapshot
  (it equals that snapshot payload's own ``source_bundle_sha256`` over
  ``source_files``), so a verifier can find the bundle that belongs to the
  ledger it is checking.

This module only *builds*, *writes*, and *resolves/validates* bundles. It never
touches a DB, a live CSV, a report, or a service. All hashing reuses the
existing deterministic snapshot primitives so bundle identity matches the
snapshot's canonicalization byte-for-byte.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from quantbot.paper.funding_source_snapshot import (
    SNAPSHOT_SCOPE_BATCH,
    canonical_json,
    sha256_text,
)

FUNDING_SOURCE_BUNDLE_SCHEMA_V1 = "FUNDING_SOURCE_BUNDLE_SCHEMA_V1"
BUNDLE_FILENAME_PREFIX = "funding_source_bundle_v1_"

# Refusal reason codes surfaced by the clean-carry gate in bundle mode. These
# are the names the spec (and PR #106 spec-first tests) pin.
BUNDLE_REASON_MISSING = "funding_source_bundle_missing"
BUNDLE_REASON_CORRUPT = "funding_source_bundle_corrupt"
BUNDLE_REASON_HASH_MISMATCH = "funding_source_bundle_hash_mismatch"
BUNDLE_REASON_INCOMPLETE_WINDOW = "funding_source_bundle_incomplete_window"

BUNDLE_REFUSAL_REASONS = frozenset(
    {
        BUNDLE_REASON_MISSING,
        BUNDLE_REASON_CORRUPT,
        BUNDLE_REASON_HASH_MISMATCH,
        BUNDLE_REASON_INCOMPLETE_WINDOW,
    }
)


def _canonical_row_sort_key(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("symbol") or ""),
        str(row.get("window_start") or ""),
        str(row.get("window_end") or ""),
    )


def _frozen_canonical_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Reconstruct the frozen funding rows from the snapshot's window records.

    Only windows with an accepted source row (a resolved ``funding_rate``) are
    frozen; the funding rate string is preserved verbatim so bundle identity is
    reproducible and drift is detectable.
    """
    window_records = payload.get("required_funding_windows")
    rows: list[dict[str, Any]] = []
    if not isinstance(window_records, list):
        return rows
    for record in window_records:
        if not isinstance(record, Mapping):
            continue
        accepted = record.get("accepted_source_row")
        if not isinstance(accepted, Mapping) or record.get("funding_rate") is None:
            continue
        rows.append(
            {
                "symbol": str(record.get("symbol") or ""),
                "window_start": str(record.get("window_start") or ""),
                "window_end": str(record.get("window_end") or ""),
                "funding_rate": str(record.get("funding_rate")),
                "raw_fundingTime_ms": record.get("raw_fundingTime_ms"),
                "source_file_path": str(accepted.get("source_file_path") or ""),
                "source_csv_row_index": accepted.get("source_csv_row_index"),
                "source_row_sha256": accepted.get("source_row_sha256"),
            }
        )
    return sorted(rows, key=_canonical_row_sort_key)


def _required_windows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    window_records = payload.get("required_funding_windows")
    required: list[dict[str, Any]] = []
    if not isinstance(window_records, list):
        return required
    for record in window_records:
        if not isinstance(record, Mapping):
            continue
        required.append(
            {
                "symbol": str(record.get("symbol") or ""),
                "window_start": str(record.get("window_start") or ""),
                "window_end": str(record.get("window_end") or ""),
                "required_by": str(record.get("required_by") or ""),
            }
        )
    return required


def _resolved_funding_source_dir(payload: Mapping[str, Any]) -> str | None:
    """Return the absolute resolved funding source dir recorded in the snapshot."""
    provenance = payload.get("provenance")
    if isinstance(provenance, Mapping):
        resolution = provenance.get("source_path_resolution")
        if isinstance(resolution, Mapping):
            raw = resolution.get("resolved_funding_source_dir")
            if isinstance(raw, str) and raw:
                return raw
    metadata = payload.get("snapshot_metadata")
    if isinstance(metadata, Mapping):
        raw = metadata.get("resolved_funding_source_dir")
        if isinstance(raw, str) and raw:
            return raw
    return None


def _digests_by_path(payload: Mapping[str, Any], field: str) -> dict[str, str]:
    source_files = payload.get("source_files")
    out: dict[str, str] = {}
    if not isinstance(source_files, list):
        return out
    for item in source_files:
        if not isinstance(item, Mapping):
            continue
        path = item.get("path")
        value = item.get(field)
        if isinstance(path, str) and isinstance(value, str):
            out[path] = value
    return out


def recompute_bundle_sha256(bundle_payload: Mapping[str, Any]) -> str:
    """Content-address the frozen canonical rows exactly as at build time."""
    rows = bundle_payload.get("canonical_rows")
    if not isinstance(rows, list):
        rows = []
    return sha256_text(canonical_json(rows))


def build_funding_source_bundle_v1(envelope: Mapping[str, Any]) -> dict[str, Any]:
    """Build an immutable funding-source bundle from a committed snapshot envelope."""
    payload = envelope.get("snapshot_payload")
    if not isinstance(payload, Mapping):
        raise ValueError("envelope has no snapshot_payload mapping")

    canonical_rows = _frozen_canonical_rows(payload)
    by_symbol: dict[str, int] = {}
    for row in canonical_rows:
        by_symbol[row["symbol"]] = by_symbol.get(row["symbol"], 0) + 1

    bundle_payload = {
        "source_bundle_sha256": sha256_text(canonical_json(canonical_rows)),
        "canonical_rows": canonical_rows,
        "original_source_digests": _digests_by_path(payload, "full_file_sha256"),
        "row_subset_digests": _digests_by_path(payload, "canonical_row_subset_sha256"),
        "symbols": list(payload.get("symbols_covered") or []),
        "row_counts": {"total": len(canonical_rows), "by_symbol": by_symbol},
        "evaluation_window": payload.get("evaluation_window"),
        # Carry the explicit snapshot scope (batch default) and absolute source
        # dir through the bundle so a full-window snapshot yields a full-window
        # bundle without any ambiguous multi-snapshot discovery. These fields do
        # not participate in ``source_bundle_sha256`` (which content-addresses
        # only ``canonical_rows``), so existing bundle identity is unchanged.
        "snapshot_scope": payload.get("snapshot_scope", SNAPSHOT_SCOPE_BATCH),
        "resolved_funding_source_dir": _resolved_funding_source_dir(payload),
        "required_windows": _required_windows(payload),
        # Bind this bundle to the committed snapshot it was frozen from.
        "snapshot_bundle_sha256": payload.get("source_bundle_sha256"),
        "snapshot_sha256": envelope.get("snapshot_sha256"),
    }
    return {
        "schema_version": FUNDING_SOURCE_BUNDLE_SCHEMA_V1,
        "bundle_payload": bundle_payload,
    }


def bundle_filename(source_bundle_sha256: str) -> str:
    return f"{BUNDLE_FILENAME_PREFIX}{source_bundle_sha256}.json"


def bundle_path(directory: str | Path, source_bundle_sha256: str) -> Path:
    return Path(directory) / bundle_filename(source_bundle_sha256)


def write_funding_source_bundle(
    bundle: Mapping[str, Any],
    directory: str | Path,
) -> Path:
    """Write a bundle to ``directory``, content-addressed by its stored hash.

    The filename uses the stored ``source_bundle_sha256`` verbatim (it is not
    recomputed), so a tampered bundle keeps its original name and the verifier's
    recompute check catches the mismatch.
    """
    payload = bundle.get("bundle_payload")
    if not isinstance(payload, Mapping):
        raise ValueError("bundle has no bundle_payload mapping")
    sha = payload.get("source_bundle_sha256")
    if not isinstance(sha, str):
        raise ValueError("bundle_payload has no source_bundle_sha256")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = bundle_path(directory, sha)
    path.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _validate_bundle_structure(obj: Any) -> bool:
    if not isinstance(obj, Mapping):
        return False
    if obj.get("schema_version") != FUNDING_SOURCE_BUNDLE_SCHEMA_V1:
        return False
    payload = obj.get("bundle_payload")
    if not isinstance(payload, Mapping):
        return False
    if not isinstance(payload.get("canonical_rows"), list):
        return False
    if not isinstance(payload.get("source_bundle_sha256"), str):
        return False
    return True


def bundle_window_reasons(bundle_payload: Mapping[str, Any]) -> list[str]:
    """Refuse if the frozen rows do not cover every required funding window."""
    required = {
        (w.get("symbol"), w.get("window_start"), w.get("window_end"))
        for w in (bundle_payload.get("required_windows") or [])
        if isinstance(w, Mapping)
    }
    covered = {
        (r.get("symbol"), r.get("window_start"), r.get("window_end"))
        for r in (bundle_payload.get("canonical_rows") or [])
        if isinstance(r, Mapping)
    }
    if required - covered:
        return [BUNDLE_REASON_INCOMPLETE_WINDOW]
    return []


def resolve_funding_source_bundle(
    bundle_dir: str | Path,
    expected_snapshot_bundle_sha256: str | None,
) -> tuple[dict[str, Any] | None, list[str], dict[str, Any]]:
    """Locate and validate the bundle bound to a committed snapshot.

    Returns ``(bundle_payload | None, reason_codes, identity)``. ``identity``
    always carries ``source_resolution_mode='bundle'`` and, when a bound bundle
    is found, its path, hash, and captured source digests. ``reason_codes`` is
    empty only when a bound, self-consistent, fully-covering bundle is found.
    """
    identity: dict[str, Any] = {"source_resolution_mode": "bundle"}
    directory = Path(bundle_dir)
    if not directory.is_dir():
        return None, [BUNDLE_REASON_MISSING], identity

    files = sorted(directory.glob(f"{BUNDLE_FILENAME_PREFIX}*.json"))
    if not files:
        return None, [BUNDLE_REASON_MISSING], identity

    corrupt_seen = False
    for path in files:
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            corrupt_seen = True
            continue
        if not _validate_bundle_structure(obj):
            corrupt_seen = True
            continue
        bundle_payload = obj["bundle_payload"]
        if (
            expected_snapshot_bundle_sha256 is not None
            and bundle_payload.get("snapshot_bundle_sha256")
            != expected_snapshot_bundle_sha256
        ):
            # A structurally valid bundle for a different snapshot; keep looking.
            continue

        identity.update(
            {
                "bundle_path": str(path),
                "source_bundle_sha256": bundle_payload.get("source_bundle_sha256"),
                "original_source_digests": bundle_payload.get(
                    "original_source_digests"
                )
                or {},
            }
        )
        reasons: list[str] = []
        if recompute_bundle_sha256(bundle_payload) != bundle_payload.get(
            "source_bundle_sha256"
        ):
            reasons.append(BUNDLE_REASON_HASH_MISMATCH)
        reasons.extend(bundle_window_reasons(bundle_payload))
        return bundle_payload, reasons, identity

    if corrupt_seen:
        return None, [BUNDLE_REASON_CORRUPT], identity
    return None, [BUNDLE_REASON_MISSING], identity


__all__ = [
    "FUNDING_SOURCE_BUNDLE_SCHEMA_V1",
    "BUNDLE_FILENAME_PREFIX",
    "BUNDLE_REASON_MISSING",
    "BUNDLE_REASON_CORRUPT",
    "BUNDLE_REASON_HASH_MISMATCH",
    "BUNDLE_REASON_INCOMPLETE_WINDOW",
    "BUNDLE_REFUSAL_REASONS",
    "build_funding_source_bundle_v1",
    "write_funding_source_bundle",
    "bundle_filename",
    "bundle_path",
    "recompute_bundle_sha256",
    "bundle_window_reasons",
    "resolve_funding_source_bundle",
]
