"""Pure funding source snapshot builder for future clean-carry evidence.

This module does not read or write SQLite, does not run the paper writer, and
does not emit sidecar artifacts. It only builds deterministic in-memory
snapshot payloads from caller-provided rows and local source files/content.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from quantbot.paper.funding_time import (
    ENDPOINT_SAME_SECOND_TOLERANCE_MS,
    FUNDING_TIMESTAMP_NORMALIZATION_SPEC_V2,
    REASON_ACCEPTED,
    REASON_CANONICALIZED_TO_OPEN_BOUNDARY,
    REASON_DUPLICATE_CANONICAL_ENDPOINT,
    REASON_MISSING_SOURCE_ROW,
    REASON_OUTSIDE_TOLERANCE,
    classify_funding_timestamp_for_window,
)

FUNDING_SOURCE_SNAPSHOT_SCHEMA_V1 = "FUNDING_SOURCE_SNAPSHOT_SCHEMA_V1"

REASON_CODES_V1 = {
    "funding_source_snapshot_missing",
    "funding_source_snapshot_digest_mismatch",
    "funding_source_snapshot_schema_unsupported",
    "funding_source_snapshot_window_mismatch",
    "funding_source_snapshot_db_mismatch",
    "funding_source_snapshot_unreferenced_or_orphaned",
    "funding_source_file_digest_mismatch",
    "funding_source_row_digest_mismatch",
    "funding_source_missing",
    "funding_source_partial",
    "funding_source_duplicate_ambiguous",
    "funding_timestamp_outside_tolerance",
    "funding_timestamp_open_boundary",
    "funding_resum_mismatch",
}

WRITE_STATES_V1 = {"pending", "committed", "orphaned"}

_DIAGNOSTIC_LOOKAHEAD_MS = ENDPOINT_SAME_SECOND_TOLERANCE_MS + 3
_COMPONENT_NAME = "quantbot.paper.funding_source_snapshot"


def canonical_json(value: Any) -> str:
    """Return compact, stable JSON for content-addressed hashes."""
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def sha256_bytes(value: bytes) -> str:
    """Return the SHA-256 hex digest for raw bytes."""
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    """Return the SHA-256 hex digest for UTF-8 text."""
    return sha256_bytes(value.encode("utf-8"))


def build_source_file_digest(source_file_path: str | Path) -> str:
    """Return a full source-file SHA-256 digest from local file bytes."""
    return sha256_bytes(Path(source_file_path).read_bytes())


def _parse_utc(raw: Any) -> datetime:
    if isinstance(raw, datetime):
        dt = raw
    else:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dt_from_ms(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)


def _row_get(row: Any, key: str, default: Any = None) -> Any:
    if isinstance(row, Mapping):
        return row.get(key, default)
    get = getattr(row, "get", None)
    if callable(get):
        return get(key, default)
    return getattr(row, key, default)


def _coerce_funding_time_ms(row: Any) -> int:
    raw_ms = _row_get(row, "fundingTime_ms")
    if raw_ms is None:
        raw_ms = _row_get(row, "fundingTime")
    if raw_ms is not None:
        return int(raw_ms)

    raw_dt = _row_get(row, "dt")
    if raw_dt is None:
        raw_dt = _row_get(row, "timestamp")
    if raw_dt is None:
        raise ValueError("source row missing fundingTime_ms/fundingTime/dt")
    dt = _parse_utc(raw_dt)
    return int(dt.timestamp() * 1000)


def _default_source_file_path(symbol: str) -> str:
    return f"data/{symbol}_8h_funding.csv"


def _normalized_source_row(row: Any, *, window_end: str | None = None) -> dict[str, Any]:
    symbol = str(_row_get(row, "symbol", ""))
    if not symbol:
        raise ValueError("source row missing symbol")
    source_file_path = _row_get(row, "source_file_path")
    if source_file_path is None:
        source_file_path = _row_get(row, "path")
    if source_file_path is None:
        source_file_path = _default_source_file_path(symbol)

    funding_rate = _row_get(row, "funding_rate")
    if funding_rate is None:
        funding_rate = _row_get(row, "fundingRate")
    if funding_rate is None:
        funding_rate = ""

    row_index = _row_get(row, "row_index")
    if row_index is None:
        row_index = _row_get(row, "source_csv_row_index", 0)

    normalized_window_end = (
        window_end if window_end is not None else _row_get(row, "window_end", "")
    )
    return {
        "symbol": symbol,
        "window_end": str(normalized_window_end),
        "fundingTime_ms": _coerce_funding_time_ms(row),
        "source_file_path": str(source_file_path),
        "row_index": int(row_index),
        "funding_rate": str(funding_rate),
    }


def _window_symbol(window: Mapping[str, Any]) -> str:
    return str(window["symbol"])


def _window_start(window: Mapping[str, Any]) -> str:
    return _iso_z(_parse_utc(window["window_start"]))


def _window_end(window: Mapping[str, Any]) -> str:
    return _iso_z(_parse_utc(window["window_end"]))


def _required_by(window: Mapping[str, Any]) -> str:
    return str(window.get("required_by", "paper_engine_funding_interval"))


def _candidate_rows_for_window(
    source_rows: Iterable[Any],
    window: Mapping[str, Any],
) -> list[dict[str, Any]]:
    symbol = _window_symbol(window)
    ws = _parse_utc(window["window_start"])
    we = _parse_utc(window["window_end"])
    diagnostic_upper = we + timedelta(milliseconds=_DIAGNOSTIC_LOOKAHEAD_MS)
    candidates: list[dict[str, Any]] = []

    for row in source_rows:
        normalized = _normalized_source_row(row, window_end=_window_end(window))
        if normalized["symbol"] != symbol:
            continue
        source_dt = _dt_from_ms(int(normalized["fundingTime_ms"]))
        if ws <= source_dt < diagnostic_upper:
            candidates.append(normalized)

    return sorted(candidates, key=_canonical_row_sort_key)


def _canonical_row_sort_key(row: Mapping[str, Any]) -> tuple[str, str, int, str, int]:
    return (
        str(row["symbol"]),
        str(row["window_end"]),
        int(row["fundingTime_ms"]),
        str(row["source_file_path"]),
        int(row["row_index"]),
    )


def _canonical_subset_rows(
    source_rows: Iterable[Any],
    required_windows: Iterable[Mapping[str, Any]],
    *,
    source_file_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    selected: dict[tuple[str, str, int, str, int], dict[str, Any]] = {}
    path_filter = str(source_file_path) if source_file_path is not None else None
    for window in required_windows:
        for row in _candidate_rows_for_window(source_rows, window):
            if path_filter is not None and row["source_file_path"] != path_filter:
                continue
            key = _canonical_row_sort_key(row)
            selected[key] = {
                "symbol": row["symbol"],
                "window_end": row["window_end"],
                "fundingTime_ms": int(row["fundingTime_ms"]),
                "source_file_path": row["source_file_path"],
                "row_index": int(row["row_index"]),
                "funding_rate": str(row["funding_rate"]),
            }
    return [selected[key] for key in sorted(selected)]


def build_canonical_row_subset_digest(
    source_rows: Iterable[Any],
    required_windows: Iterable[Mapping[str, Any]],
    *,
    source_file_path: str | Path | None = None,
) -> str:
    """Return stable SHA-256 for rows relevant to required funding windows."""
    rows = _canonical_subset_rows(
        list(source_rows),
        list(required_windows),
        source_file_path=source_file_path,
    )
    return sha256_text(canonical_json(rows))


def _source_row_digest(row: Mapping[str, Any], window: Mapping[str, Any]) -> str:
    canonical = {
        "symbol": str(row["symbol"]),
        "window_end": _window_end(window),
        "fundingTime_ms": int(row["fundingTime_ms"]),
        "source_file_path": str(row["source_file_path"]),
        "row_index": int(row["row_index"]),
        "funding_rate": str(row["funding_rate"]),
    }
    return sha256_text(canonical_json(canonical))


def _reason_code_for_timestamp_reason(reason: str) -> str:
    if reason == REASON_MISSING_SOURCE_ROW:
        return "funding_source_missing"
    if reason == REASON_DUPLICATE_CANONICAL_ENDPOINT:
        return "funding_source_duplicate_ambiguous"
    if reason == REASON_CANONICALIZED_TO_OPEN_BOUNDARY:
        return "funding_timestamp_open_boundary"
    if reason == REASON_OUTSIDE_TOLERANCE:
        return "funding_timestamp_outside_tolerance"
    raise ValueError(f"unsupported funding timestamp reason: {reason!r}")


def _accepted_source_row(
    row: Mapping[str, Any],
    window: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "source_file_path": str(row["source_file_path"]),
        "source_csv_row_index": int(row["row_index"]),
        "source_row_sha256": _source_row_digest(row, window),
    }


def _window_record(
    window: Mapping[str, Any],
    source_rows: Iterable[Any],
) -> dict[str, Any]:
    candidates = _candidate_rows_for_window(source_rows, window)
    ws = _parse_utc(window["window_start"])
    we = _parse_utc(window["window_end"])

    base = {
        "symbol": _window_symbol(window),
        "window_start": _window_start(window),
        "window_end": _window_end(window),
        "required_by": _required_by(window),
        "accepted_source_row": None,
        "canonical_endpoint": None,
        "raw_fundingTime_ms": None,
        "canonical_timestamp_utc": None,
        "funding_rate": None,
        "source_issue": None,
        "reason_codes": [],
    }

    if not candidates:
        return {
            **base,
            "source_issue": REASON_MISSING_SOURCE_ROW,
            "reason_codes": [_reason_code_for_timestamp_reason(REASON_MISSING_SOURCE_ROW)],
        }

    classified = [
        (
            row,
            classify_funding_timestamp_for_window(
                _dt_from_ms(int(row["fundingTime_ms"])),
                window_start=ws,
                window_end=we,
            ),
        )
        for row in candidates
    ]
    endpoint_rows = [
        row
        for row, classification in classified
        if classification.reason == REASON_ACCEPTED
        and classification.canonical_endpoint == we
    ]
    open_boundary_rows = [
        row
        for row, classification in classified
        if classification.reason == REASON_CANONICALIZED_TO_OPEN_BOUNDARY
    ]
    inside_rows = [
        row
        for row, classification in classified
        if classification.reason == REASON_ACCEPTED
        and classification.canonical_endpoint is None
    ]
    outside_rows = [
        row
        for row, classification in classified
        if classification.reason == REASON_OUTSIDE_TOLERANCE
    ]

    if len(endpoint_rows) > 1:
        return {
            **base,
            "canonical_endpoint": _window_end(window),
            "source_issue": REASON_DUPLICATE_CANONICAL_ENDPOINT,
            "reason_codes": [
                _reason_code_for_timestamp_reason(REASON_DUPLICATE_CANONICAL_ENDPOINT)
            ],
        }

    if len(endpoint_rows) == 1:
        row = endpoint_rows[0]
        return {
            **base,
            "accepted_source_row": _accepted_source_row(row, window),
            "canonical_endpoint": _window_end(window),
            "raw_fundingTime_ms": int(row["fundingTime_ms"]),
            "canonical_timestamp_utc": _window_end(window),
            "funding_rate": str(row["funding_rate"]),
        }

    if open_boundary_rows:
        row = open_boundary_rows[0]
        return {
            **base,
            "canonical_endpoint": _window_start(window),
            "raw_fundingTime_ms": int(row["fundingTime_ms"]),
            "canonical_timestamp_utc": _window_start(window),
            "funding_rate": str(row["funding_rate"]),
            "source_issue": REASON_CANONICALIZED_TO_OPEN_BOUNDARY,
            "reason_codes": [
                _reason_code_for_timestamp_reason(REASON_CANONICALIZED_TO_OPEN_BOUNDARY)
            ],
        }

    if inside_rows:
        row = inside_rows[0]
        return {
            **base,
            "accepted_source_row": _accepted_source_row(row, window),
            "raw_fundingTime_ms": int(row["fundingTime_ms"]),
            "canonical_timestamp_utc": _iso_z(_dt_from_ms(int(row["fundingTime_ms"]))),
            "funding_rate": str(row["funding_rate"]),
        }

    row = outside_rows[0] if outside_rows else candidates[0]
    return {
        **base,
        "raw_fundingTime_ms": int(row["fundingTime_ms"]),
        "funding_rate": str(row["funding_rate"]),
        "source_issue": REASON_OUTSIDE_TOLERANCE,
        "reason_codes": [_reason_code_for_timestamp_reason(REASON_OUTSIDE_TOLERANCE)],
    }


def _coverage_decision(records: list[Mapping[str, Any]]) -> str:
    if not records:
        return "not_required"
    if all(not record["reason_codes"] for record in records):
        return "complete"
    if any(not record["reason_codes"] for record in records):
        return "partial"
    return "refused"


def _source_file_symbol(path: str) -> str:
    name = Path(path).name
    if name.endswith("_8h_funding.csv"):
        return name.removesuffix("_8h_funding.csv")
    if "_" in name:
        return name.split("_", 1)[0]
    return Path(path).stem


def _source_file_digest_from_content(content: str | bytes) -> str:
    if isinstance(content, bytes):
        return sha256_bytes(content)
    return sha256_text(content)


def _source_file_records(
    *,
    source_rows: list[Any],
    required_windows: list[Mapping[str, Any]],
    source_file_contents_by_path: Mapping[str, str | bytes] | None,
    source_file_paths: Iterable[str | Path] | None,
) -> list[dict[str, Any]]:
    records_by_path: dict[str, dict[str, Any]] = {}

    if source_file_contents_by_path:
        for path, content in source_file_contents_by_path.items():
            path_s = str(path)
            records_by_path[path_s] = {
                "symbol": _source_file_symbol(path_s),
                "path": path_s,
                "full_file_sha256": _source_file_digest_from_content(content),
                "canonical_row_subset_sha256": build_canonical_row_subset_digest(
                    source_rows,
                    required_windows,
                    source_file_path=path_s,
                ),
            }

    if source_file_paths:
        for path in source_file_paths:
            path_s = str(path)
            records_by_path[path_s] = {
                "symbol": _source_file_symbol(path_s),
                "path": path_s,
                "full_file_sha256": build_source_file_digest(path),
                "canonical_row_subset_sha256": build_canonical_row_subset_digest(
                    source_rows,
                    required_windows,
                    source_file_path=path_s,
                ),
            }

    return [records_by_path[path] for path in sorted(records_by_path)]


def _evaluation_window(
    required_windows: list[Mapping[str, Any]],
    explicit: Mapping[str, Any] | None,
) -> dict[str, str | None]:
    if explicit is not None:
        return {
            "start": _iso_z(_parse_utc(explicit["start"])),
            "end": _iso_z(_parse_utc(explicit["end"])),
        }
    if not required_windows:
        return {"start": None, "end": None}
    starts = [_parse_utc(window["window_start"]) for window in required_windows]
    ends = [_parse_utc(window["window_end"]) for window in required_windows]
    return {"start": _iso_z(min(starts)), "end": _iso_z(max(ends))}


def build_funding_source_snapshot_payload_v1(
    *,
    source_rows: Iterable[Any],
    required_windows: Iterable[Mapping[str, Any]],
    generated_at_utc: str,
    lane_id: str,
    output_dir: str,
    writer_or_verifier_command: str,
    qnty_git_commit: str,
    source_file_contents_by_path: Mapping[str, str | bytes] | None = None,
    source_file_paths: Iterable[str | Path] | None = None,
    write_state: str = "committed",
    db_identity_hash_before: str | None = None,
    pending_batch_id: str | None = None,
    ledger_batch_id: str | None = None,
    batch_identity_matches: bool = True,
    evaluation_identity_matches: bool = True,
    sanitized_host_user_label: str | None = None,
    evaluation_window: Mapping[str, Any] | None = None,
    db_path_reference: str | None = None,
    batch_start_watermark: str | None = None,
    batch_end_watermark: str | None = None,
    qnty_component_name: str = _COMPONENT_NAME,
) -> dict[str, Any]:
    """Build a deterministic v1 snapshot payload from caller-provided inputs."""
    if write_state not in WRITE_STATES_V1:
        raise ValueError(f"unsupported write_state: {write_state!r}")

    rows = list(source_rows)
    windows = list(required_windows)
    generated = _iso_z(_parse_utc(generated_at_utc))
    window_records = [_window_record(window, rows) for window in windows]
    coverage_decision = _coverage_decision(window_records)
    reason_codes = sorted(
        {
            reason
            for record in window_records
            for reason in record["reason_codes"]
        }
    )
    if coverage_decision == "partial":
        reason_codes.append("funding_source_partial")

    source_files = _source_file_records(
        source_rows=rows,
        required_windows=windows,
        source_file_contents_by_path=source_file_contents_by_path,
        source_file_paths=source_file_paths,
    )

    payload = {
        "schema_version": FUNDING_SOURCE_SNAPSHOT_SCHEMA_V1,
        "generated_at_utc": generated,
        "evaluation_window": _evaluation_window(windows, evaluation_window),
        "lane": {
            "lane_id": lane_id,
            "output_dir": output_dir,
        },
        "provenance": {
            "entity_inputs": [
                {
                    "source_csv_path": item["path"],
                    "source_csv_sha256": item["full_file_sha256"],
                    "canonical_row_subset_sha256": item[
                        "canonical_row_subset_sha256"
                    ],
                }
                for item in source_files
            ],
            "activity": {
                "writer_or_verifier_command": writer_or_verifier_command,
                "qnty_git_commit": qnty_git_commit,
                "normalization_spec_version": (
                    FUNDING_TIMESTAMP_NORMALIZATION_SPEC_V2
                ),
                "generated_at_utc": generated,
            },
            "agent": {
                "qnty_component_name": qnty_component_name,
                "lane_id": lane_id,
                "sanitized_host_user_label": sanitized_host_user_label,
            },
        },
        "normalization_spec_version": FUNDING_TIMESTAMP_NORMALIZATION_SPEC_V2,
        "source_files": source_files,
        "symbols_covered": sorted({_window_symbol(window) for window in windows}),
        "required_funding_windows": window_records,
        "coverage_decision": coverage_decision,
        "reason_codes": reason_codes,
        "source_bundle_sha256": sha256_text(canonical_json(source_files)),
        "write_state": write_state,
        "snapshot_metadata": {
            "write_state": write_state,
            "db_identity_hash_before": db_identity_hash_before,
            "db_path_reference": db_path_reference,
            "batch_start_watermark": batch_start_watermark,
            "batch_end_watermark": batch_end_watermark,
            "pending_batch_id": pending_batch_id,
            "ledger_batch_id": ledger_batch_id,
            "batch_identity_matches": batch_identity_matches,
            "evaluation_identity_matches": evaluation_identity_matches,
        },
    }
    return payload


def build_funding_source_snapshot_envelope_v1(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the content-addressed envelope around a v1 snapshot payload."""
    return {
        "snapshot_payload": dict(payload),
        "snapshot_sha256": sha256_text(canonical_json(payload)),
    }


def validate_funding_source_snapshot_envelope_v1(
    envelope: Mapping[str, Any] | None,
) -> list[str]:
    """Validate the v1 envelope and return refusal reason codes."""
    if envelope is None:
        return ["funding_source_snapshot_missing"]
    if not isinstance(envelope, Mapping):
        return ["funding_source_snapshot_schema_unsupported"]
    if set(envelope) != {"snapshot_payload", "snapshot_sha256"}:
        return ["funding_source_snapshot_schema_unsupported"]

    payload = envelope.get("snapshot_payload")
    if not isinstance(payload, Mapping):
        return ["funding_source_snapshot_schema_unsupported"]
    if envelope.get("snapshot_sha256") != sha256_text(canonical_json(payload)):
        return ["funding_source_snapshot_digest_mismatch"]
    if payload.get("schema_version") != FUNDING_SOURCE_SNAPSHOT_SCHEMA_V1:
        return ["funding_source_snapshot_schema_unsupported"]
    return []


def _snapshot_metadata(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = payload.get("snapshot_metadata", {})
    if isinstance(raw, Mapping):
        return raw
    return {}


def _source_files_by_path(payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    source_files = payload.get("source_files", [])
    if not isinstance(source_files, list):
        return {}
    return {
        str(item["path"]): item
        for item in source_files
        if isinstance(item, Mapping) and "path" in item
    }


def clean_mode_decision_from_snapshot_v1(
    envelope: Mapping[str, Any] | None,
    *,
    expected_evaluation_window: Mapping[str, Any] | None = None,
    expected_lane_id: str | None = None,
    expected_db_identity_hash_before: str | None = None,
    expected_source_file_sha256_by_path: Mapping[str, str] | None = None,
    expected_row_subset_sha256_by_path: Mapping[str, str] | None = None,
    expected_pending_batch_id: str | None = None,
    expected_ledger_batch_id: str | None = None,
) -> dict[str, Any]:
    """Classify whether a snapshot would allow a future clean-mode verdict.

    This is intentionally pure and does not classify any current ledger as clean.
    It only centralizes future refusal semantics for missing, mismatched,
    ambiguous, pending, or orphaned funding source evidence.
    """
    reason_codes = validate_funding_source_snapshot_envelope_v1(envelope)
    if reason_codes:
        return {
            "clean_net_of_carry_allowed": False,
            "reason_codes": reason_codes,
        }

    assert envelope is not None
    payload = envelope["snapshot_payload"]
    assert isinstance(payload, Mapping)
    metadata = _snapshot_metadata(payload)

    if expected_evaluation_window is not None:
        expected_window = {
            "start": _iso_z(_parse_utc(expected_evaluation_window["start"])),
            "end": _iso_z(_parse_utc(expected_evaluation_window["end"])),
        }
        if payload.get("evaluation_window") != expected_window:
            reason_codes.append("funding_source_snapshot_window_mismatch")

    lane = payload.get("lane", {})
    if not isinstance(lane, Mapping):
        reason_codes.append("funding_source_snapshot_db_mismatch")
    elif expected_lane_id is not None and lane.get("lane_id") != expected_lane_id:
        reason_codes.append("funding_source_snapshot_db_mismatch")

    if (
        expected_db_identity_hash_before is not None
        and metadata.get("db_identity_hash_before") != expected_db_identity_hash_before
    ):
        reason_codes.append("funding_source_snapshot_db_mismatch")

    write_state = payload.get("write_state", metadata.get("write_state"))
    if write_state != "committed":
        reason_codes.append("funding_source_snapshot_unreferenced_or_orphaned")
    if metadata.get("batch_identity_matches") is not True:
        reason_codes.append("funding_source_snapshot_unreferenced_or_orphaned")
    if metadata.get("evaluation_identity_matches") is not True:
        reason_codes.append("funding_source_snapshot_unreferenced_or_orphaned")
    if (
        expected_pending_batch_id is not None
        and metadata.get("pending_batch_id") != expected_pending_batch_id
    ):
        reason_codes.append("funding_source_snapshot_unreferenced_or_orphaned")
    if (
        expected_ledger_batch_id is not None
        and metadata.get("ledger_batch_id") != expected_ledger_batch_id
    ):
        reason_codes.append("funding_source_snapshot_unreferenced_or_orphaned")

    source_files_by_path = _source_files_by_path(payload)
    if expected_source_file_sha256_by_path is not None:
        for path, expected_sha in expected_source_file_sha256_by_path.items():
            item = source_files_by_path.get(str(path))
            if item is None or item.get("full_file_sha256") != expected_sha:
                reason_codes.append("funding_source_file_digest_mismatch")
                break

    if expected_row_subset_sha256_by_path is not None:
        for path, expected_sha in expected_row_subset_sha256_by_path.items():
            item = source_files_by_path.get(str(path))
            if item is None or item.get("canonical_row_subset_sha256") != expected_sha:
                reason_codes.append("funding_source_row_digest_mismatch")
                break

    payload_reasons = payload.get("reason_codes", [])
    if isinstance(payload_reasons, list):
        reason_codes.extend(str(reason) for reason in payload_reasons)
    if payload.get("coverage_decision") != "complete" and not payload_reasons:
        reason_codes.append("funding_source_partial")

    source_files = payload.get("source_files")
    if not isinstance(source_files, list):
        reason_codes.append("funding_source_file_digest_mismatch")
    elif payload.get("source_bundle_sha256") != sha256_text(
        canonical_json(source_files)
    ):
        reason_codes.append("funding_source_file_digest_mismatch")

    return {
        "clean_net_of_carry_allowed": not reason_codes,
        "reason_codes": sorted(set(reason_codes)),
    }


__all__ = [
    "FUNDING_SOURCE_SNAPSHOT_SCHEMA_V1",
    "REASON_CODES_V1",
    "WRITE_STATES_V1",
    "canonical_json",
    "sha256_bytes",
    "sha256_text",
    "build_source_file_digest",
    "build_canonical_row_subset_digest",
    "build_funding_source_snapshot_payload_v1",
    "build_funding_source_snapshot_envelope_v1",
    "validate_funding_source_snapshot_envelope_v1",
    "clean_mode_decision_from_snapshot_v1",
]
