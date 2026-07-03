"""Test-local schema spec for future funding source snapshots.

These tests intentionally do not import or exercise a production snapshot
builder. They pin the v1 artifact contract before implementation exists.
"""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from quantbot.paper.funding_time import FUNDING_TIMESTAMP_NORMALIZATION_SPEC_V2

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

_WINDOW_START = "2026-06-14T16:00:00Z"
_WINDOW_END = "2026-06-15T00:00:00Z"
_GENERATED_AT = "2026-06-15T00:01:00Z"
_DB_IDENTITY = "paper-ledger-db-identity-sha256"
_LANE_ID = "paper_pnl_v1"
_SOURCE_PATH = "data/SOLUSDT_8h_funding.csv"


def _parse_utc(raw: str) -> datetime:
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ms_at(raw: str, *, offset_ms: int = 0) -> int:
    return int(_parse_utc(raw).timestamp() * 1000) + offset_ms


def _dt_from_ms(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)


def _spec_canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def _spec_sha256_json(value: Any) -> str:
    return hashlib.sha256(_spec_canonical_json(value).encode("utf-8")).hexdigest()


def _spec_sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _required_window(
    *,
    symbol: str = "SOLUSDT",
    window_start: str = _WINDOW_START,
    window_end: str = _WINDOW_END,
    required_by: str = "paper_engine_funding_interval",
) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "window_start": window_start,
        "window_end": window_end,
        "required_by": required_by,
    }


def _source_row(
    *,
    symbol: str = "SOLUSDT",
    window_end: str = _WINDOW_END,
    funding_time_ms: int | None = None,
    offset_ms: int = 0,
    source_file_path: str | None = None,
    row_index: int = 1,
    funding_rate: str = "0.0001",
) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "window_end": window_end,
        "fundingTime_ms": (
            funding_time_ms
            if funding_time_ms is not None
            else _ms_at(window_end, offset_ms=offset_ms)
        ),
        "source_file_path": source_file_path or f"data/{symbol}_8h_funding.csv",
        "row_index": row_index,
        "funding_rate": funding_rate,
    }


def _same_second_at_or_after(source: datetime, endpoint: datetime) -> bool:
    delta = source - endpoint
    return timedelta(0) <= delta <= timedelta(milliseconds=999)


def _window_candidate_rows(
    source_rows: list[dict[str, Any]],
    window: dict[str, Any],
) -> list[dict[str, Any]]:
    ws = _parse_utc(window["window_start"])
    we = _parse_utc(window["window_end"])
    diagnostic_upper = we + timedelta(milliseconds=1002)
    rows = [
        row
        for row in source_rows
        if row["symbol"] == window["symbol"]
        and ws <= _dt_from_ms(int(row["fundingTime_ms"])) < diagnostic_upper
    ]
    return sorted(
        rows,
        key=lambda row: (
            row["symbol"],
            window["window_end"],
            int(row["fundingTime_ms"]),
            row["source_file_path"],
            int(row["row_index"]),
        ),
    )


def _canonical_subset_rows(
    source_rows: list[dict[str, Any]],
    required_windows: list[dict[str, Any]],
    *,
    source_file_path: str | None = None,
) -> list[dict[str, Any]]:
    selected: dict[tuple[str, str, int, str, int], dict[str, Any]] = {}
    for window in required_windows:
        for row in _window_candidate_rows(source_rows, window):
            if source_file_path is not None and row["source_file_path"] != source_file_path:
                continue
            key = (
                row["symbol"],
                window["window_end"],
                int(row["fundingTime_ms"]),
                row["source_file_path"],
                int(row["row_index"]),
            )
            selected[key] = {
                "symbol": row["symbol"],
                "window_end": window["window_end"],
                "fundingTime_ms": int(row["fundingTime_ms"]),
                "source_file_path": row["source_file_path"],
                "row_index": int(row["row_index"]),
                "funding_rate": str(row["funding_rate"]),
            }
    return [selected[key] for key in sorted(selected)]


def _spec_canonical_row_subset_sha256(
    source_rows: list[dict[str, Any]],
    required_windows: list[dict[str, Any]],
    *,
    source_file_path: str | None = None,
) -> str:
    return _spec_sha256_json(
        _canonical_subset_rows(
            source_rows,
            required_windows,
            source_file_path=source_file_path,
        )
    )


def _spec_source_row_sha256(
    row: dict[str, Any],
    window: dict[str, Any],
) -> str:
    return _spec_sha256_json(
        {
            "symbol": row["symbol"],
            "window_end": window["window_end"],
            "fundingTime_ms": int(row["fundingTime_ms"]),
            "source_file_path": row["source_file_path"],
            "row_index": int(row["row_index"]),
            "funding_rate": str(row["funding_rate"]),
        }
    )


def _window_record(
    window: dict[str, Any],
    source_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    candidates = _window_candidate_rows(source_rows, window)
    ws = _parse_utc(window["window_start"])
    we = _parse_utc(window["window_end"])
    endpoint_rows = [
        row
        for row in candidates
        if _same_second_at_or_after(_dt_from_ms(int(row["fundingTime_ms"])), we)
    ]
    open_boundary_rows = [
        row
        for row in candidates
        if _same_second_at_or_after(_dt_from_ms(int(row["fundingTime_ms"])), ws)
    ]
    inside_rows = [
        row
        for row in candidates
        if ws < _dt_from_ms(int(row["fundingTime_ms"])) <= we
    ]

    base = {
        "symbol": window["symbol"],
        "window_start": window["window_start"],
        "window_end": window["window_end"],
        "required_by": window["required_by"],
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
            "source_issue": "missing_source_row",
            "reason_codes": ["funding_source_missing"],
        }

    if len(endpoint_rows) > 1:
        return {
            **base,
            "canonical_endpoint": window["window_end"],
            "source_issue": "duplicate_canonical_endpoint",
            "reason_codes": ["funding_source_duplicate_ambiguous"],
        }

    if len(endpoint_rows) == 1:
        row = endpoint_rows[0]
        return {
            **base,
            "accepted_source_row": {
                "source_file_path": row["source_file_path"],
                "source_csv_row_index": int(row["row_index"]),
                "source_row_sha256": _spec_source_row_sha256(row, window),
            },
            "canonical_endpoint": window["window_end"],
            "raw_fundingTime_ms": int(row["fundingTime_ms"]),
            "canonical_timestamp_utc": window["window_end"],
            "funding_rate": str(row["funding_rate"]),
        }

    if open_boundary_rows:
        row = open_boundary_rows[0]
        return {
            **base,
            "canonical_endpoint": window["window_start"],
            "raw_fundingTime_ms": int(row["fundingTime_ms"]),
            "canonical_timestamp_utc": window["window_start"],
            "funding_rate": str(row["funding_rate"]),
            "source_issue": "canonicalized_to_open_boundary",
            "reason_codes": ["funding_timestamp_open_boundary"],
        }

    if inside_rows:
        row = inside_rows[0]
        return {
            **base,
            "accepted_source_row": {
                "source_file_path": row["source_file_path"],
                "source_csv_row_index": int(row["row_index"]),
                "source_row_sha256": _spec_source_row_sha256(row, window),
            },
            "raw_fundingTime_ms": int(row["fundingTime_ms"]),
            "canonical_timestamp_utc": _iso_z(_dt_from_ms(int(row["fundingTime_ms"]))),
            "funding_rate": str(row["funding_rate"]),
        }

    row = candidates[0]
    return {
        **base,
        "raw_fundingTime_ms": int(row["fundingTime_ms"]),
        "funding_rate": str(row["funding_rate"]),
        "source_issue": "outside_tolerance",
        "reason_codes": ["funding_timestamp_outside_tolerance"],
    }


def _coverage_decision(records: list[dict[str, Any]]) -> str:
    if not records:
        return "not_required"
    if all(not record["reason_codes"] for record in records):
        return "complete"
    if any(not record["reason_codes"] for record in records):
        return "partial"
    return "refused"


def _spec_build_snapshot_payload_v1(
    *,
    source_rows: list[dict[str, Any]],
    source_file_contents_by_path: dict[str, str],
    required_windows: list[dict[str, Any]],
    write_state: str = "committed",
    db_identity_hash_before: str = _DB_IDENTITY,
    lane_id: str = _LANE_ID,
    batch_identity_matches: bool = True,
) -> dict[str, Any]:
    assert write_state in WRITE_STATES_V1
    window_records = [
        _window_record(window, source_rows)
        for window in required_windows
    ]
    reason_codes = sorted(
        {
            reason
            for record in window_records
            for reason in record["reason_codes"]
        }
    )
    if _coverage_decision(window_records) == "partial":
        reason_codes.append("funding_source_partial")

    source_paths = sorted(source_file_contents_by_path)
    source_files = [
        {
            "symbol": path.split("/")[-1].split("_8h_funding.csv")[0],
            "path": path,
            "full_file_sha256": _spec_sha256_text(source_file_contents_by_path[path]),
            "canonical_row_subset_sha256": _spec_canonical_row_subset_sha256(
                source_rows,
                required_windows,
                source_file_path=path,
            ),
        }
        for path in source_paths
    ]

    payload = {
        "schema_version": FUNDING_SOURCE_SNAPSHOT_SCHEMA_V1,
        "generated_at_utc": _GENERATED_AT,
        "evaluation_window": {
            "start": required_windows[0]["window_start"],
            "end": required_windows[-1]["window_end"],
        },
        "lane": {
            "lane_id": lane_id,
            "output_dir": f"/sanitized/{lane_id}",
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
                "writer_or_verifier_command": (
                    "qnty-paper-sqlite-verify --clean-mode "
                    "--snapshot funding_source_snapshot_v1.json"
                ),
                "qnty_git_commit": "41bbc86246489c393c53c46349b8e8f5d5967522",
                "normalization_spec_version": (
                    FUNDING_TIMESTAMP_NORMALIZATION_SPEC_V2
                ),
                "generated_at_utc": _GENERATED_AT,
            },
            "agent": {
                "qnty_component_name": "quantbot.paper.funding_source_snapshot",
                "lane_id": lane_id,
                "sanitized_host_user_label": "local-test",
            },
        },
        "normalization_spec_version": FUNDING_TIMESTAMP_NORMALIZATION_SPEC_V2,
        "source_files": source_files,
        "symbols_covered": sorted({window["symbol"] for window in required_windows}),
        "required_funding_windows": window_records,
        "coverage_decision": _coverage_decision(window_records),
        "reason_codes": reason_codes,
        "source_bundle_sha256": _spec_sha256_json(source_files),
        "snapshot_metadata": {
            "write_state": write_state,
            "db_identity_hash_before": db_identity_hash_before,
            "pending_batch_id": "pending-2026-06-15T00:00:00Z",
            "ledger_batch_id": "batch-36" if write_state == "committed" else None,
            "batch_identity_matches": batch_identity_matches,
            "evaluation_identity_matches": batch_identity_matches,
        },
    }
    return payload


def _spec_build_snapshot_envelope_v1(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "snapshot_payload": payload,
        "snapshot_sha256": _spec_sha256_json(payload),
    }


def _spec_validate_snapshot_envelope_v1(
    envelope: dict[str, Any] | None,
) -> list[str]:
    if envelope is None:
        return ["funding_source_snapshot_missing"]
    if set(envelope) != {"snapshot_payload", "snapshot_sha256"}:
        return ["funding_source_snapshot_schema_unsupported"]
    payload = envelope["snapshot_payload"]
    if envelope["snapshot_sha256"] != _spec_sha256_json(payload):
        return ["funding_source_snapshot_digest_mismatch"]
    if payload.get("schema_version") != FUNDING_SOURCE_SNAPSHOT_SCHEMA_V1:
        return ["funding_source_snapshot_schema_unsupported"]
    return []


def _spec_clean_mode_decision_from_snapshot_v1(
    envelope: dict[str, Any] | None,
    *,
    expected_evaluation_window: dict[str, Any] | None = None,
    expected_lane_id: str = _LANE_ID,
    expected_db_identity_hash_before: str = _DB_IDENTITY,
    expected_source_file_sha256_by_path: dict[str, str] | None = None,
    expected_row_subset_sha256_by_path: dict[str, str] | None = None,
) -> dict[str, Any]:
    reason_codes = _spec_validate_snapshot_envelope_v1(envelope)
    if reason_codes:
        return {"clean_net_of_carry_allowed": False, "reason_codes": reason_codes}

    assert envelope is not None
    payload = envelope["snapshot_payload"]
    expected_window = expected_evaluation_window or {
        "start": _WINDOW_START,
        "end": _WINDOW_END,
    }
    if payload["evaluation_window"] != expected_window:
        reason_codes.append("funding_source_snapshot_window_mismatch")
    if (
        payload["lane"]["lane_id"] != expected_lane_id
        or payload["snapshot_metadata"]["db_identity_hash_before"]
        != expected_db_identity_hash_before
    ):
        reason_codes.append("funding_source_snapshot_db_mismatch")
    if (
        payload["snapshot_metadata"]["write_state"] != "committed"
        or not payload["snapshot_metadata"]["batch_identity_matches"]
        or not payload["snapshot_metadata"]["evaluation_identity_matches"]
    ):
        reason_codes.append("funding_source_snapshot_unreferenced_or_orphaned")

    source_files_by_path = {item["path"]: item for item in payload["source_files"]}
    if expected_source_file_sha256_by_path is not None:
        for path, expected_sha in expected_source_file_sha256_by_path.items():
            if source_files_by_path[path]["full_file_sha256"] != expected_sha:
                reason_codes.append("funding_source_file_digest_mismatch")
                break
    if expected_row_subset_sha256_by_path is not None:
        for path, expected_sha in expected_row_subset_sha256_by_path.items():
            if source_files_by_path[path]["canonical_row_subset_sha256"] != expected_sha:
                reason_codes.append("funding_source_row_digest_mismatch")
                break

    reason_codes.extend(payload["reason_codes"])
    if payload["coverage_decision"] != "complete" and not payload["reason_codes"]:
        reason_codes.append("funding_source_partial")

    return {
        "clean_net_of_carry_allowed": not reason_codes,
        "reason_codes": sorted(set(reason_codes)),
    }


def _accepted_payload() -> dict[str, Any]:
    row = _source_row(
        symbol="SOLUSDT",
        window_end=_WINDOW_END,
        offset_ms=5,
        source_file_path=_SOURCE_PATH,
    )
    csv_text = (
        "fundingTime,fundingRate,markPrice\n"
        f"{row['fundingTime_ms']},0.0001,100.0\n"
    )
    return _spec_build_snapshot_payload_v1(
        source_rows=[row],
        source_file_contents_by_path={_SOURCE_PATH: csv_text},
        required_windows=[_required_window()],
    )


def test_snapshot_envelope_hashes_only_payload_and_is_content_addressed() -> None:
    payload = _accepted_payload()
    envelope = _spec_build_snapshot_envelope_v1(payload)

    assert envelope["snapshot_sha256"] == _spec_sha256_json(payload)
    assert _spec_validate_snapshot_envelope_v1(envelope) == []

    changed_payload = copy.deepcopy(payload)
    changed_payload["required_funding_windows"][0]["funding_rate"] = "0.0002"
    changed_envelope = _spec_build_snapshot_envelope_v1(changed_payload)
    assert changed_envelope["snapshot_sha256"] != envelope["snapshot_sha256"]

    changed_outer_hash_only = copy.deepcopy(envelope)
    changed_outer_hash_only["snapshot_sha256"] = "0" * 64
    assert (
        _spec_sha256_json(changed_outer_hash_only["snapshot_payload"])
        == envelope["snapshot_sha256"]
    )
    assert _spec_validate_snapshot_envelope_v1(changed_outer_hash_only) == [
        "funding_source_snapshot_digest_mismatch"
    ]


def test_payload_and_provenance_fields_pin_schema_v1() -> None:
    payload = _accepted_payload()

    assert {
        "schema_version",
        "generated_at_utc",
        "evaluation_window",
        "lane",
        "provenance",
        "normalization_spec_version",
        "source_files",
        "symbols_covered",
        "required_funding_windows",
        "coverage_decision",
        "reason_codes",
        "source_bundle_sha256",
    } <= set(payload)
    assert payload["schema_version"] == FUNDING_SOURCE_SNAPSHOT_SCHEMA_V1
    assert (
        payload["normalization_spec_version"]
        == FUNDING_TIMESTAMP_NORMALIZATION_SPEC_V2
    )
    assert payload["coverage_decision"] == "complete"

    provenance = payload["provenance"]
    assert {"entity_inputs", "activity", "agent"} <= set(provenance)
    assert {
        "source_csv_path",
        "source_csv_sha256",
        "canonical_row_subset_sha256",
    } <= set(provenance["entity_inputs"][0])
    assert {
        "writer_or_verifier_command",
        "qnty_git_commit",
        "normalization_spec_version",
        "generated_at_utc",
    } <= set(provenance["activity"])
    assert {
        "qnty_component_name",
        "lane_id",
        "sanitized_host_user_label",
    } <= set(provenance["agent"])

    source_file = payload["source_files"][0]
    assert {"full_file_sha256", "canonical_row_subset_sha256"} <= set(source_file)
    assert payload["source_bundle_sha256"] == _spec_sha256_json(
        payload["source_files"]
    )


def test_source_digest_policy_separates_full_file_and_row_subset_hashes() -> None:
    required_windows = [_required_window()]
    accepted_row = _source_row(source_file_path=_SOURCE_PATH, offset_ms=5)
    irrelevant_row = _source_row(
        source_file_path=_SOURCE_PATH,
        window_end="2026-06-30T00:00:00Z",
        row_index=200,
    )

    base_csv = (
        "fundingTime,fundingRate,markPrice\n"
        f"{accepted_row['fundingTime_ms']},0.0001,100.0\n"
    )
    appended_csv = (
        base_csv
        +
        f"{irrelevant_row['fundingTime_ms']},0.0002,100.0\n"
    )

    assert _spec_sha256_text(base_csv) != _spec_sha256_text(appended_csv)
    assert _spec_canonical_row_subset_sha256(
        [accepted_row],
        required_windows,
        source_file_path=_SOURCE_PATH,
    ) == _spec_canonical_row_subset_sha256(
        [accepted_row, irrelevant_row],
        required_windows,
        source_file_path=_SOURCE_PATH,
    )

    changed_accepted_row = {
        **accepted_row,
        "funding_rate": "0.0009",
    }
    assert _spec_canonical_row_subset_sha256(
        [accepted_row],
        required_windows,
        source_file_path=_SOURCE_PATH,
    ) != _spec_canonical_row_subset_sha256(
        [changed_accepted_row],
        required_windows,
        source_file_path=_SOURCE_PATH,
    )


def test_canonical_row_ordering_is_stable_regardless_of_input_order() -> None:
    required_windows = [
        _required_window(symbol="BTCUSDT"),
        _required_window(symbol="ETHUSDT"),
    ]
    rows = [
        _source_row(
            symbol="ETHUSDT",
            source_file_path="data/ETHUSDT_8h_funding.csv",
            row_index=9,
            offset_ms=5,
        ),
        _source_row(
            symbol="BTCUSDT",
            source_file_path="data/BTCUSDT_8h_funding.csv",
            row_index=4,
            offset_ms=5,
        ),
    ]

    assert _spec_canonical_row_subset_sha256(rows, required_windows) == (
        _spec_canonical_row_subset_sha256(list(reversed(rows)), required_windows)
    )


def test_required_funding_window_records_all_v1_cases() -> None:
    required_windows = [
        _required_window(symbol="ACCEPTED"),
        _required_window(symbol="MISSING"),
        _required_window(symbol="DUPLICATE"),
        _required_window(symbol="OUTSIDE"),
        _required_window(symbol="OPEN"),
    ]
    source_rows = [
        _source_row(
            symbol="ACCEPTED",
            source_file_path="data/ACCEPTED_8h_funding.csv",
            offset_ms=5,
        ),
        _source_row(
            symbol="DUPLICATE",
            source_file_path="data/DUPLICATE_8h_funding.csv",
            row_index=1,
            offset_ms=0,
        ),
        _source_row(
            symbol="DUPLICATE",
            source_file_path="data/DUPLICATE_8h_funding.csv",
            row_index=2,
            offset_ms=5,
        ),
        _source_row(
            symbol="OUTSIDE",
            source_file_path="data/OUTSIDE_8h_funding.csv",
            offset_ms=1000,
        ),
        _source_row(
            symbol="OPEN",
            source_file_path="data/OPEN_8h_funding.csv",
            funding_time_ms=_ms_at(_WINDOW_START, offset_ms=5),
        ),
    ]
    file_contents = {
        f"data/{window['symbol']}_8h_funding.csv": "fundingTime,fundingRate\n"
        for window in required_windows
    }
    payload = _spec_build_snapshot_payload_v1(
        source_rows=source_rows,
        source_file_contents_by_path=file_contents,
        required_windows=required_windows,
    )

    by_symbol = {
        record["symbol"]: record
        for record in payload["required_funding_windows"]
    }
    for record in by_symbol.values():
        assert {
            "symbol",
            "window_start",
            "window_end",
            "required_by",
            "accepted_source_row",
            "canonical_endpoint",
            "raw_fundingTime_ms",
            "canonical_timestamp_utc",
            "funding_rate",
            "source_issue",
            "reason_codes",
        } <= set(record)

    assert by_symbol["ACCEPTED"]["accepted_source_row"] is not None
    assert by_symbol["ACCEPTED"]["canonical_endpoint"] == _WINDOW_END
    assert by_symbol["ACCEPTED"]["reason_codes"] == []
    assert by_symbol["MISSING"]["reason_codes"] == ["funding_source_missing"]
    assert by_symbol["DUPLICATE"]["reason_codes"] == [
        "funding_source_duplicate_ambiguous"
    ]
    assert by_symbol["OUTSIDE"]["reason_codes"] == [
        "funding_timestamp_outside_tolerance"
    ]
    assert by_symbol["OPEN"]["reason_codes"] == ["funding_timestamp_open_boundary"]


def test_reason_codes_are_pinned_schema_values() -> None:
    assert REASON_CODES_V1 == {
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


@pytest.mark.parametrize("write_state", ["pending", "orphaned"])
def test_pending_and_orphaned_snapshot_metadata_are_not_clean_evidence(
    write_state: str,
) -> None:
    payload = _spec_build_snapshot_payload_v1(
        source_rows=[
            _source_row(source_file_path=_SOURCE_PATH, offset_ms=5),
        ],
        source_file_contents_by_path={
            _SOURCE_PATH: "fundingTime,fundingRate,markPrice\n"
        },
        required_windows=[_required_window()],
        write_state=write_state,
    )
    decision = _spec_clean_mode_decision_from_snapshot_v1(
        _spec_build_snapshot_envelope_v1(payload)
    )

    assert decision["clean_net_of_carry_allowed"] is False
    assert decision["reason_codes"] == [
        "funding_source_snapshot_unreferenced_or_orphaned"
    ]


def test_committed_snapshot_requires_batch_and_evaluation_identity_match() -> None:
    payload = _spec_build_snapshot_payload_v1(
        source_rows=[
            _source_row(source_file_path=_SOURCE_PATH, offset_ms=5),
        ],
        source_file_contents_by_path={
            _SOURCE_PATH: "fundingTime,fundingRate,markPrice\n"
        },
        required_windows=[_required_window()],
        batch_identity_matches=False,
    )

    decision = _spec_clean_mode_decision_from_snapshot_v1(
        _spec_build_snapshot_envelope_v1(payload)
    )
    assert decision["clean_net_of_carry_allowed"] is False
    assert decision["reason_codes"] == [
        "funding_source_snapshot_unreferenced_or_orphaned"
    ]

    matched_payload = _accepted_payload()
    matched_decision = _spec_clean_mode_decision_from_snapshot_v1(
        _spec_build_snapshot_envelope_v1(matched_payload)
    )
    assert matched_decision == {
        "clean_net_of_carry_allowed": True,
        "reason_codes": [],
    }


def test_clean_mode_refuses_missing_snapshot() -> None:
    assert _spec_clean_mode_decision_from_snapshot_v1(None) == {
        "clean_net_of_carry_allowed": False,
        "reason_codes": ["funding_source_snapshot_missing"],
    }


def test_clean_mode_refuses_snapshot_digest_mismatch() -> None:
    envelope = _spec_build_snapshot_envelope_v1(_accepted_payload())
    envelope["snapshot_sha256"] = "bad-digest"

    assert _spec_clean_mode_decision_from_snapshot_v1(envelope) == {
        "clean_net_of_carry_allowed": False,
        "reason_codes": ["funding_source_snapshot_digest_mismatch"],
    }


def test_clean_mode_refuses_unsupported_schema() -> None:
    payload = _accepted_payload()
    payload["schema_version"] = "funding_source_snapshot_v0"

    assert _spec_clean_mode_decision_from_snapshot_v1(
        _spec_build_snapshot_envelope_v1(payload)
    ) == {
        "clean_net_of_carry_allowed": False,
        "reason_codes": ["funding_source_snapshot_schema_unsupported"],
    }


def test_clean_mode_refuses_window_mismatch() -> None:
    decision = _spec_clean_mode_decision_from_snapshot_v1(
        _spec_build_snapshot_envelope_v1(_accepted_payload()),
        expected_evaluation_window={
            "start": "2026-06-13T16:00:00Z",
            "end": "2026-06-14T00:00:00Z",
        },
    )

    assert decision == {
        "clean_net_of_carry_allowed": False,
        "reason_codes": ["funding_source_snapshot_window_mismatch"],
    }


def test_clean_mode_refuses_db_or_lane_mismatch() -> None:
    decision = _spec_clean_mode_decision_from_snapshot_v1(
        _spec_build_snapshot_envelope_v1(_accepted_payload()),
        expected_lane_id="paper_pnl_null_shadow_v0",
    )

    assert decision == {
        "clean_net_of_carry_allowed": False,
        "reason_codes": ["funding_source_snapshot_db_mismatch"],
    }


@pytest.mark.parametrize(
    ("source_rows", "expected_reason"),
    [
        (
            [
                _source_row(
                    source_file_path=_SOURCE_PATH,
                    row_index=1,
                    offset_ms=0,
                ),
                _source_row(
                    source_file_path=_SOURCE_PATH,
                    row_index=2,
                    offset_ms=5,
                ),
            ],
            "funding_source_duplicate_ambiguous",
        ),
        (
            [_source_row(source_file_path=_SOURCE_PATH, offset_ms=1000)],
            "funding_timestamp_outside_tolerance",
        ),
        ([], "funding_source_missing"),
    ],
)
def test_clean_mode_refuses_source_row_coverage_failures(
    source_rows: list[dict[str, Any]],
    expected_reason: str,
) -> None:
    payload = _spec_build_snapshot_payload_v1(
        source_rows=source_rows,
        source_file_contents_by_path={
            _SOURCE_PATH: "fundingTime,fundingRate,markPrice\n"
        },
        required_windows=[_required_window()],
    )
    decision = _spec_clean_mode_decision_from_snapshot_v1(
        _spec_build_snapshot_envelope_v1(payload)
    )

    assert decision["clean_net_of_carry_allowed"] is False
    assert expected_reason in decision["reason_codes"]


def test_clean_mode_refuses_source_file_and_row_digest_mismatches() -> None:
    payload = _accepted_payload()
    envelope = _spec_build_snapshot_envelope_v1(payload)
    source_file = payload["source_files"][0]

    file_decision = _spec_clean_mode_decision_from_snapshot_v1(
        envelope,
        expected_source_file_sha256_by_path={
            source_file["path"]: "different-full-file-sha256",
        },
    )
    assert file_decision == {
        "clean_net_of_carry_allowed": False,
        "reason_codes": ["funding_source_file_digest_mismatch"],
    }

    row_decision = _spec_clean_mode_decision_from_snapshot_v1(
        envelope,
        expected_row_subset_sha256_by_path={
            source_file["path"]: "different-row-subset-sha256",
        },
    )
    assert row_decision == {
        "clean_net_of_carry_allowed": False,
        "reason_codes": ["funding_source_row_digest_mismatch"],
    }
