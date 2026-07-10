"""Real offline validation receipt skeleton for offline edge validation.

Scope boundary (do not violate) — see
docs/status/QNTY_OFFLINE_EDGE_VALIDATION_REAL_VALIDATION_EXECUTION_PLAN.md:

This module builds the *schema and first descriptive calculation scaffold*
for the real offline validation receipt. It only computes close-to-close gross
observational metadata. It does **not**:

- compute strategy, net, cost-adjusted, or funding-adjusted returns
- compute PnL
- compute Sharpe or any risk-adjusted metric
- run the paper engine
- import any live/exchange code
- emit ``OFFLINE_EDGE_CANDIDATE`` (that constant exists only for
  schema/refusal tests — see ``offline_edge_schema.py``)
- claim edge, profit, or live readiness

Every receipt built by this module has ``final_offline_verdict`` fixed to
``BLOCKED_BY_VALIDATION_IMPLEMENTATION`` and every
``forbidden_calculation_status`` flag fixed to ``False``. Stdlib only —
no pandas, numpy, engine, exchange, ccxt, sqlite, or paper imports.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from quantbot.experiment.offline_edge_schema import (
    BLOCKED_BY_DATA_QUALITY_REGRESSION,
    BLOCKED_BY_VALIDATION_IMPLEMENTATION,
    INCONCLUSIVE,
    NO_EDGE,
    OFFLINE_EDGE_CANDIDATE,
)

__all__ = [
    "build_real_validation_receipt",
    "build_deterministic_split_definitions",
    "build_cost_case_matrix",
    "validate_real_validation_receipt",
    "write_real_validation_receipt",
    "build_real_validation_input_inventory",
    "materialize_split_definitions_from_inventory",
    "materialize_input_rows_for_splits",
    "materialize_gross_observational_returns",
    "materialize_cost_case_observational_drag",
    "materialize_funding_observational_adjustments",
]

RECEIPT_SCHEMA_KIND: str = "qnty_offline_edge_real_validation_receipt"
RECEIPT_SCHEMA_VERSION: str = "0.1.0"

# Only these final verdicts are recognized by this schema's validator.
ALLOWED_FINAL_VERDICTS = frozenset(
    {
        OFFLINE_EDGE_CANDIDATE,
        NO_EDGE,
        INCONCLUSIVE,
        BLOCKED_BY_VALIDATION_IMPLEMENTATION,
        BLOCKED_BY_DATA_QUALITY_REGRESSION,
    }
)

# This PR (receipt skeleton) may only ever emit this verdict.
_SKELETON_ALLOWED_VERDICTS = frozenset({BLOCKED_BY_VALIDATION_IMPLEMENTATION})

# Top-level keys that must never appear on a receipt from this module.
FORBIDDEN_TOP_LEVEL_KEYS = frozenset({"pnl", "sharpe", "edge", "strategy_performance"})

# Keys that must never appear at any nesting level in a receipt.
FORBIDDEN_CALCULATION_KEYS = frozenset(
    {
        "pnl",
        "sharpe",
        "edge",
        "strategy_performance",
        "return",
        "returns",
        "gross_observational_return",
        "gross_return_value",
        "net_return_value",
        "cost_adjusted_return",
        "funding_adjusted_return",
        "price_change",
        "trade",
        "trades",
        "signal",
        "signals",
        "position",
        "positions",
        "portfolio",
        "live_ready",
        "deploy_ready",
        "profitable",
    }
)

PROD_BASE = Path("/srv/qnty")
TMP_BASE = Path("/tmp")


# ── Path guards ─────────────────────────────────────────────────────────


def _resolve(path: Path) -> Path:
    return path.resolve()


def _is_under(resolved: Path, base: Path) -> bool:
    base_resolved = base.resolve()
    try:
        common = os.path.commonpath([str(resolved), str(base_resolved)])
    except ValueError:
        return False
    return common == str(base_resolved)


def _refuse_if_prod_path(resolved: Path) -> None:
    if _is_under(resolved, PROD_BASE):
        raise ValueError(f"Refusing path under prod base {PROD_BASE}: {resolved}")


def _refuse_if_not_tmp(resolved: Path) -> None:
    if not _is_under(resolved, TMP_BASE):
        raise ValueError(f"Refusing path not under /tmp: {resolved}")


def _assert_no_prod_paths_in_receipt(value: Any, path: str = "$") -> None:
    """Recursively scan *value* for any occurrence of PROD_BASE (/srv/qnty).

    Scans dict values, list/tuple values, and string values.

    For strings:
    - If the string contains ``/srv/qnty/`` as a substring, reject immediately
      with ``AssertionError``.
    - If the string looks like an absolute path, resolve it via ``_resolve``
      and reject if it resolves under ``PROD_BASE`` using
      ``os.path.commonpath`` boundary logic.
    - Sibling safety: ``/srv/qnty2`` must NOT be falsely rejected by the
      boundary check (``/srv/qnty/`` with trailing slash avoids false
      positives on ``/srv/qnty2/...``).

    For other types (int, float, bool, None): skip.
    """
    if isinstance(value, str):
        # Raw substring check with trailing slash for sibling safety.
        if "/srv/qnty/" in value:
            raise AssertionError(
                f"Receipt field {path!r} contains PROD_BASE path: {value!r}"
            )
        # Boundary check for absolute paths.
        if value.startswith("/"):
            try:
                resolved = _resolve(Path(value))
                if _is_under(resolved, PROD_BASE):
                    raise AssertionError(
                        f"Receipt field {path!r} resolves under PROD_BASE: {value!r}"
                    )
            except (OSError, ValueError):
                pass
    elif isinstance(value, dict):
        for key, v in value.items():
            _assert_no_prod_paths_in_receipt(v, path + "." + key)
    elif isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            _assert_no_prod_paths_in_receipt(v, path + "[" + str(i) + "]")


# ── Timestamp helpers ───────────────────────────────────────────────────


def _parse_timestamp(ts: str) -> datetime:
    """Parse an ISO-8601 or Unix epoch timestamp as a UTC datetime.

    Digit-only values are treated as epoch milliseconds when they contain
    at least 13 digits (or exceed a 10-digit epoch-seconds range), otherwise
    as epoch seconds. Naive ISO timestamps are deterministically interpreted
    as UTC.
    """
    value = ts.strip()
    if value.isdigit():
        epoch_value = int(value)
        if len(value) >= 13 or epoch_value > 10_000_000_000:
            epoch_value /= 1000
        return datetime.fromtimestamp(epoch_value, tz=timezone.utc)

    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_timestamp(dt: datetime) -> str:
    """Format a datetime as ISO-8601 UTC string ending in 'Z'."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Input inventory ─────────────────────────────────────────────────────


def _build_role_inventory(
    role: str,
    directory: Path,
    timestamp_column: str,
) -> dict[str, Any]:
    """Build the inventory dict for a single role (bars or funding).

    *role* is ``"bars"`` or ``"funding"``.
    *directory* is the resolved ``Path`` containing CSV files.
    *timestamp_column* is the column name to scan for metadata
    (``"timestamp"`` for bars, ``"fundingTime"`` for funding).

    Returns a dict with keys:
    - role, directory, csv_file_count, filenames, total_size_bytes, files,
      aggregate_role_fingerprint
    - each file entry has: filename, size_bytes, sha256
    - each file entry also has: row_count, min_timestamp, max_timestamp,
      has_timestamp_column

    No price columns are parsed. No returns/PnL/Sharpe are computed.
    """
    csv_paths: list[Path] = []
    filenames: list[str] = []
    files: list[dict[str, Any]] = []
    total_size_bytes: int = 0
    sha256_digests: list[str] = []

    for csv_path in sorted(directory.glob("*.csv")):
        resolved_csv = csv_path.resolve()
        _refuse_if_prod_path(resolved_csv)
        if not resolved_csv.is_file():
            continue

        csv_paths.append(csv_path)
        filename = csv_path.name
        filenames.append(filename)
        size_bytes = resolved_csv.stat().st_size
        total_size_bytes += size_bytes

        # SHA256 of file content.
        sha256_hex = hashlib.sha256(resolved_csv.read_bytes()).hexdigest()
        sha256_digests.append(sha256_hex)

        # Timestamp metadata (CSV header scan, timestamp column only).
        row_count: int = 0
        min_timestamp_dt: datetime | None = None
        max_timestamp_dt: datetime | None = None
        has_timestamp_column: bool = False

        with open(resolved_csv, newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                # Empty file — no columns at all.
                pass
            else:
                # Case-insensitive column lookup.
                col_lower_map = {h.lower(): h for h in reader.fieldnames}
                target_lower = timestamp_column.lower()
                actual_col = col_lower_map.get(target_lower)

                if actual_col is not None:
                    has_timestamp_column = True
                    for row_number, row in enumerate(reader, start=2):
                        row_count += 1
                        ts_val = row.get(actual_col)
                        if ts_val is not None and ts_val.strip():
                            ts_val = ts_val.strip()
                            try:
                                parsed_ts = _parse_timestamp(ts_val)
                            except (OverflowError, OSError, ValueError) as exc:
                                raise ValueError(
                                    f"Malformed timestamp in {filename} row "
                                    f"{row_number}, column {actual_col}: {ts_val!r}"
                                ) from exc
                            if min_timestamp_dt is None or parsed_ts < min_timestamp_dt:
                                min_timestamp_dt = parsed_ts
                            if max_timestamp_dt is None or parsed_ts > max_timestamp_dt:
                                max_timestamp_dt = parsed_ts
                else:
                    # Column not found — still count rows but no timestamp info.
                    for _ in reader:
                        row_count += 1

        file_entry: dict[str, Any] = {
            "filename": filename,
            "size_bytes": size_bytes,
            "sha256": sha256_hex,
            "row_count": row_count,
            "min_timestamp": (
                _format_timestamp(min_timestamp_dt)
                if min_timestamp_dt is not None
                else None
            ),
            "max_timestamp": (
                _format_timestamp(max_timestamp_dt)
                if max_timestamp_dt is not None
                else None
            ),
            "has_timestamp_column": has_timestamp_column,
        }
        files.append(file_entry)

    # Aggregate fingerprint: SHA256 of sorted concatenation of per-file digests.
    sorted_digests = sorted(sha256_digests)
    concatenated = "".join(sorted_digests).encode("utf-8")
    aggregate_fingerprint = hashlib.sha256(concatenated).hexdigest()

    return {
        "role": role,
        "directory": str(directory),
        "csv_file_count": len(csv_paths),
        "filenames": filenames,
        "total_size_bytes": total_size_bytes,
        "files": files,
        "aggregate_role_fingerprint": aggregate_fingerprint,
    }


def build_real_validation_input_inventory(
    *,
    bars_dir: Path,
    funding_dir: Path | None = None,
) -> dict[str, Any]:
    """Build an input inventory from real CSV data directories.

    Enumerates CSV files in *bars_dir* (and optionally *funding_dir*),
    records file metadata (size, SHA256), timestamp metadata (min/max per
    file), and computes an aggregate role fingerprint.

    Refuses paths under ``/srv/qnty`` and nonexistent directories.

    No returns/PnL/Sharpe are computed. No price columns are parsed.
    """
    # Guard checks.
    bars_resolved = bars_dir.resolve()
    _refuse_if_prod_path(bars_resolved)
    if not bars_resolved.is_dir():
        raise ValueError(f"bars_dir does not exist: {bars_resolved}")

    funding_resolved: Path | None = None
    if funding_dir is not None:
        funding_resolved = funding_dir.resolve()
        _refuse_if_prod_path(funding_resolved)
        if not funding_resolved.is_dir():
            raise ValueError(f"funding_dir does not exist: {funding_resolved}")

    roles: list[dict[str, Any]] = [
        _build_role_inventory("bars", bars_resolved, "timestamp"),
    ]
    if funding_resolved is not None:
        roles.append(
            _build_role_inventory("funding", funding_resolved, "fundingTime")
        )

    return {
        "roles": roles,
    }


# ── Split builder skeleton ──────────────────────────────────────────────


def build_deterministic_split_definitions(
    *,
    global_min_timestamp: str,
    global_max_timestamp: str,
    split_count: int = 3,
) -> list[dict[str, Any]]:
    """Build deterministic placeholder split definitions.

    This does **not** inspect any real data file and does **not** compute
    returns. It only partitions the provided ``[global_min_timestamp,
    global_max_timestamp]`` bounds (treated as opaque strings) into
    ``split_count`` deterministic, evenly-labeled placeholder windows, each
    marked ``calculation_status: NOT_EXECUTED``.
    """
    if split_count < 1:
        raise ValueError(f"split_count must be >= 1, got {split_count}")

    splits: list[dict[str, Any]] = []
    for i in range(split_count):
        splits.append(
            {
                "split_id": f"split_{i:02d}",
                "train_window": {
                    "start": global_min_timestamp,
                    "end": global_max_timestamp,
                },
                "validation_window": {
                    "start": global_min_timestamp,
                    "end": global_max_timestamp,
                },
                "split_index": i,
                "split_count": split_count,
                "calculation_status": "NOT_EXECUTED",
            }
        )
    return splits


def _derive_global_timestamp_bounds(
    inventory: dict[str, Any],
) -> tuple[str, str, int, int]:
    """Derive global min/max timestamp and file counts from inventory.

    Returns ``(global_min_str, global_max_str, bars_file_count,
    funding_file_count)``.

    Raises ``ValueError`` if no timestamp data is available.
    """
    global_min: datetime | None = None
    global_max: datetime | None = None
    bars_file_count: int = 0
    funding_file_count: int = 0

    roles = inventory.get("roles", [])
    for role_entry in roles:
        role = role_entry.get("role", "")
        files = role_entry.get("files", [])
        if role == "bars":
            bars_file_count = len(files)
        elif role == "funding":
            funding_file_count = len(files)

        for file_entry in files:
            fmin = file_entry.get("min_timestamp")
            fmax = file_entry.get("max_timestamp")
            if fmin is not None:
                parsed_min = _parse_timestamp(fmin)
                if global_min is None or parsed_min < global_min:
                    global_min = parsed_min
            if fmax is not None:
                parsed_max = _parse_timestamp(fmax)
                if global_max is None or parsed_max > global_max:
                    global_max = parsed_max

    if global_min is None or global_max is None:
        raise ValueError(
            "Cannot derive global timestamp bounds from inventory: "
            "no timestamp data available"
        )

    return (
        _format_timestamp(global_min),
        _format_timestamp(global_max),
        bars_file_count,
        funding_file_count,
    )


def materialize_split_definitions_from_inventory(
    *,
    inventory: dict[str, Any],
    split_count: int = 3,
) -> list[dict[str, Any]]:
    """Derive deterministic split definitions from an input inventory.

    Extracts global min/max timestamps from the inventory's per-file
    timestamp metadata, partitions the time range into equal segments,
    and creates expanding-window split definitions.

    Each split i gets:
    - a validation window covering one segment
    - a training window covering everything before the validation window

    No returns/PnL/Sharpe fields are included.
    """
    if split_count < 1:
        raise ValueError(f"split_count must be >= 1, got {split_count}")

    global_min_str, global_max_str, bars_file_count, funding_file_count = (
        _derive_global_timestamp_bounds(inventory)
    )

    global_min_dt = _parse_timestamp(global_min_str)
    global_max_dt = _parse_timestamp(global_max_str)
    total_seconds = (global_max_dt - global_min_dt).total_seconds()
    segment_duration = total_seconds / split_count

    # Build segment boundaries.
    boundaries: list[str] = []
    for i in range(split_count + 1):
        boundary_dt = global_min_dt + timedelta(seconds=i * segment_duration)
        boundaries.append(_format_timestamp(boundary_dt))

    splits: list[dict[str, Any]] = []
    for i in range(split_count):
        train_start = boundaries[0]
        train_end = boundaries[i]  # up to start of validation segment
        val_start = boundaries[i]
        val_end = boundaries[i + 1]

        splits.append(
            {
                "split_id": f"split_{i:02d}",
                "split_index": i,
                "split_count": split_count,
                "train_window": {
                    "start": train_start,
                    "end": train_end,
                },
                "validation_window": {
                    "start": val_start,
                    "end": val_end,
                },
                "calculation_status": "NOT_EXECUTED",
                "bars_file_count": bars_file_count,
                "funding_file_count": funding_file_count,
            }
        )

    return splits


# ── Row assignment metadata ──────────────────────────────────────────


_ROLE_TIMESTAMP_COLUMNS = {
    "bars": "timestamp",
    "funding": "fundingTime",
}


def _timestamp_in_window(
    timestamp: datetime,
    *,
    start: datetime,
    end: datetime,
    include_end: bool = False,
) -> bool:
    """Return whether *timestamp* is in a deterministic split window."""
    if include_end:
        return start <= timestamp <= end
    return start <= timestamp < end


def materialize_input_rows_for_splits(
    *,
    inventory: dict,
    split_definitions: list[dict],
) -> dict:
    """Count inventoried timestamp rows assigned to existing split windows.

    Only the role-specific timestamp column is accessed. Empty timestamp cells
    and rows outside every window are counted as unassigned; malformed
    timestamps fail closed, matching inventory construction. Windows are
    start-inclusive and end-exclusive, except the final validation window,
    whose end is inclusive so the inventoried global maximum is covered.

    The result contains coverage metadata only. It performs no calculations
    and does not retain timestamps or any non-timestamp CSV values.
    """
    if not split_definitions:
        raise ValueError("split_definitions must not be empty")

    windows: list[dict[str, Any]] = []
    final_validation_index = max(
        range(len(split_definitions)),
        key=lambda index: split_definitions[index].get("split_index", index),
    )
    for index, split in enumerate(split_definitions):
        try:
            train = split["train_window"]
            validation = split["validation_window"]
            windows.append(
                {
                    "split_id": str(split["split_id"]),
                    "train_start": _parse_timestamp(str(train["start"])),
                    "train_end": _parse_timestamp(str(train["end"])),
                    "validation_start": _parse_timestamp(str(validation["start"])),
                    "validation_end": _parse_timestamp(str(validation["end"])),
                    "include_validation_end": index == final_validation_index,
                }
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid split definition at index {index}") from exc

    role_results: list[dict[str, Any]] = []
    for role_entry in inventory.get("roles", []):
        role = role_entry.get("role")
        timestamp_column = _ROLE_TIMESTAMP_COLUMNS.get(role)
        if timestamp_column is None:
            raise ValueError(f"Unsupported inventoried role: {role!r}")

        role_directory = Path(str(role_entry.get("directory", ""))).resolve()
        _refuse_if_prod_path(role_directory)
        if not role_directory.is_dir():
            raise ValueError(f"Inventoried role directory is missing: {role_directory}")

        role_split_counts = {
            window["split_id"]: {"train_rows": 0, "validation_rows": 0}
            for window in windows
        }
        file_results: list[dict[str, Any]] = []
        role_total_rows = 0
        role_assigned_rows = 0

        for file_entry in role_entry.get("files", []):
            filename = file_entry.get("filename")
            if not isinstance(filename, str) or not filename:
                raise ValueError(f"Invalid inventoried filename for role {role!r}")

            filename_path = Path(filename)
            if filename_path.is_absolute() or "/" in filename or ".." in filename:
                raise ValueError(
                    f"Inventoried filename must be a simple filename: {filename!r}"
                )

            inventoried_path = role_directory / filename
            if inventoried_path.parent != role_directory:
                raise ValueError(
                    f"Inventoried file path is outside role directory: {filename}"
                )
            if not inventoried_path.exists():
                raise ValueError(f"Inventoried file is missing: {inventoried_path}")

            resolved_file = inventoried_path.resolve()
            _refuse_if_prod_path(resolved_file)
            if (
                not _is_under(resolved_file, role_directory)
                and not inventoried_path.is_symlink()
            ):
                raise ValueError(
                    f"Inventoried file resolves outside role directory: {filename}"
                )
            if not resolved_file.is_file():
                raise ValueError(f"Inventoried path is not a file: {resolved_file}")

            inventoried_sha256 = file_entry.get("sha256")
            reopened_sha256 = hashlib.sha256(resolved_file.read_bytes()).hexdigest()
            if reopened_sha256 != inventoried_sha256:
                raise ValueError(
                    f"Inventoried SHA256 changed for {filename}: "
                    f"expected {inventoried_sha256}, found {reopened_sha256}"
                )

            per_split_counts = {
                window["split_id"]: {"train_rows": 0, "validation_rows": 0}
                for window in windows
            }
            total_rows = 0
            assigned_rows = 0

            with open(resolved_file, newline="") as csv_file:
                reader = csv.reader(csv_file)
                header = next(reader, None)
                timestamp_index: int | None = None
                if header is not None:
                    header_lookup = {name.lower(): i for i, name in enumerate(header)}
                    timestamp_index = header_lookup.get(timestamp_column.lower())

                for row_number, row in enumerate(reader, start=2):
                    total_rows += 1
                    timestamp_value = (
                        row[timestamp_index].strip()
                        if timestamp_index is not None and timestamp_index < len(row)
                        else ""
                    )
                    if not timestamp_value:
                        continue
                    try:
                        timestamp = _parse_timestamp(timestamp_value)
                    except (OverflowError, OSError, ValueError) as exc:
                        raise ValueError(
                            f"Malformed timestamp in {filename} row {row_number}, "
                            f"column {timestamp_column}: {timestamp_value!r}"
                        ) from exc

                    row_was_assigned = False
                    for window in windows:
                        split_counts = per_split_counts[window["split_id"]]
                        if _timestamp_in_window(
                            timestamp,
                            start=window["train_start"],
                            end=window["train_end"],
                        ):
                            split_counts["train_rows"] += 1
                            row_was_assigned = True
                        if _timestamp_in_window(
                            timestamp,
                            start=window["validation_start"],
                            end=window["validation_end"],
                            include_end=window["include_validation_end"],
                        ):
                            split_counts["validation_rows"] += 1
                            row_was_assigned = True
                    if row_was_assigned:
                        assigned_rows += 1

            inventoried_rows = file_entry.get("row_count")
            if inventoried_rows is not None and total_rows != inventoried_rows:
                raise ValueError(
                    f"Inventoried row count changed for {filename}: "
                    f"expected {inventoried_rows}, found {total_rows}"
                )

            split_counts_list = []
            for window in windows:
                split_id = window["split_id"]
                counts = per_split_counts[split_id]
                split_counts_list.append({"split_id": split_id, **counts})
                role_split_counts[split_id]["train_rows"] += counts["train_rows"]
                role_split_counts[split_id]["validation_rows"] += counts[
                    "validation_rows"
                ]

            file_results.append(
                {
                    "role": role,
                    "filename": filename,
                    "timestamp_column": timestamp_column,
                    "total_rows": total_rows,
                    "assigned_rows": assigned_rows,
                    "unassigned_rows": total_rows - assigned_rows,
                    "per_split_counts": split_counts_list,
                    "calculation_status": "NOT_EXECUTED",
                }
            )
            role_total_rows += total_rows
            role_assigned_rows += assigned_rows

        role_results.append(
            {
                "role": role,
                "total_rows": role_total_rows,
                "assigned_rows": role_assigned_rows,
                "unassigned_rows": role_total_rows - role_assigned_rows,
                "files": file_results,
                "per_split_counts": [
                    {"split_id": window["split_id"], **role_split_counts[window["split_id"]]}
                    for window in windows
                ],
                "calculation_status": "NOT_EXECUTED",
            }
        )

    return {
        "metadata_only": True,
        "timestamp_policy": {
            "empty_timestamp": "UNASSIGNED",
            "malformed_timestamp": "FAIL_CLOSED",
            "window_start": "INCLUSIVE",
            "window_end": "EXCLUSIVE_EXCEPT_FINAL_VALIDATION_INCLUSIVE",
        },
        "roles": role_results,
        "calculation_status": "NOT_EXECUTED",
    }


# ── Gross observational return metadata ────────────────────────────────


def _gross_return_summary(values: list[float]) -> dict[str, Any]:
    """Summarize close-to-close observations without strategy semantics."""
    return {
        "observation_count": len(values),
        "positive_count": sum(value > 0.0 for value in values),
        "negative_count": sum(value < 0.0 for value in values),
        "zero_count": sum(value == 0.0 for value in values),
        "min_gross_return": min(values) if values else None,
        "max_gross_return": max(values) if values else None,
        "mean_gross_return": math.fsum(values) / len(values) if values else None,
    }


def materialize_gross_observational_returns(
    *,
    inventory: dict,
    split_definitions: list[dict],
) -> dict:
    """Materialize bars-only close-to-close descriptive return metadata.

    Each observation is ``(close_t / close_t_minus_1) - 1`` and is assigned to
    train/validation windows by the current row timestamp. Files must retain
    their inventoried SHA256, timestamps must be strictly increasing, and only
    the timestamp and close columns are accessed. Funding inventory entries are
    recorded as ignored and are never opened.
    """
    if not split_definitions:
        raise ValueError("split_definitions must not be empty")

    windows: list[dict[str, Any]] = []
    final_validation_index = max(
        range(len(split_definitions)),
        key=lambda index: split_definitions[index].get("split_index", index),
    )
    for index, split in enumerate(split_definitions):
        try:
            train = split["train_window"]
            validation = split["validation_window"]
            windows.append(
                {
                    "split_id": str(split["split_id"]),
                    "train_start": _parse_timestamp(str(train["start"])),
                    "train_end": _parse_timestamp(str(train["end"])),
                    "validation_start": _parse_timestamp(str(validation["start"])),
                    "validation_end": _parse_timestamp(str(validation["end"])),
                    "include_validation_end": index == final_validation_index,
                }
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid split definition at index {index}") from exc

    file_results: list[dict[str, Any]] = []
    ignored_roles: list[str] = []
    for role_entry in inventory.get("roles", []):
        role = role_entry.get("role")
        if role != "bars":
            ignored_roles.append(str(role))
            continue

        role_directory = Path(str(role_entry.get("directory", ""))).resolve()
        _refuse_if_prod_path(role_directory)
        if not role_directory.is_dir():
            raise ValueError(f"Inventoried bars directory is missing: {role_directory}")

        for file_entry in role_entry.get("files", []):
            filename = file_entry.get("filename")
            if not isinstance(filename, str) or not filename:
                raise ValueError("Invalid inventoried filename for role 'bars'")
            filename_path = Path(filename)
            if filename_path.is_absolute() or "/" in filename or ".." in filename:
                raise ValueError(
                    f"Inventoried filename must be a simple filename: {filename!r}"
                )

            inventoried_path = role_directory / filename
            if inventoried_path.parent != role_directory:
                raise ValueError(
                    f"Inventoried file path is outside role directory: {filename}"
                )
            if not inventoried_path.exists():
                raise ValueError(f"Inventoried file is missing: {inventoried_path}")

            resolved_file = inventoried_path.resolve()
            _refuse_if_prod_path(resolved_file)
            if (
                not _is_under(resolved_file, role_directory)
                and not inventoried_path.is_symlink()
            ):
                raise ValueError(
                    f"Inventoried file resolves outside role directory: {filename}"
                )
            if not resolved_file.is_file():
                raise ValueError(f"Inventoried path is not a file: {resolved_file}")

            inventoried_sha256 = file_entry.get("sha256")
            reopened_sha256 = hashlib.sha256(resolved_file.read_bytes()).hexdigest()
            if reopened_sha256 != inventoried_sha256:
                raise ValueError(
                    f"Inventoried SHA256 changed for {filename}: "
                    f"expected {inventoried_sha256}, found {reopened_sha256}"
                )

            observations: list[tuple[datetime, float]] = []
            previous_timestamp: datetime | None = None
            previous_close: float | None = None
            total_rows = 0
            with open(resolved_file, newline="") as csv_file:
                reader = csv.reader(csv_file)
                header = next(reader, None)
                if header is None:
                    raise ValueError(f"Missing CSV header in {filename}")
                header_lookup = {name.lower(): i for i, name in enumerate(header)}
                timestamp_index = header_lookup.get("timestamp")
                close_index = header_lookup.get("close")
                if timestamp_index is None:
                    raise ValueError(f"Missing timestamp column in {filename}")
                if close_index is None:
                    raise ValueError(f"Missing close column in {filename}")

                for row_number, row in enumerate(reader, start=2):
                    total_rows += 1
                    timestamp_value = (
                        row[timestamp_index].strip()
                        if timestamp_index < len(row)
                        else ""
                    )
                    close_value = (
                        row[close_index].strip() if close_index < len(row) else ""
                    )
                    try:
                        timestamp = _parse_timestamp(timestamp_value)
                    except (OverflowError, OSError, ValueError) as exc:
                        raise ValueError(
                            f"Malformed timestamp in {filename} row {row_number}: "
                            f"{timestamp_value!r}"
                        ) from exc
                    try:
                        close = float(close_value)
                    except ValueError as exc:
                        raise ValueError(
                            f"Malformed close in {filename} row {row_number}: "
                            f"{close_value!r}"
                        ) from exc
                    if not math.isfinite(close):
                        raise ValueError(
                            f"Malformed close in {filename} row {row_number}: "
                            f"{close_value!r}"
                        )
                    if previous_timestamp is not None and timestamp <= previous_timestamp:
                        raise ValueError(
                            f"Non-monotonic timestamp in {filename} row {row_number}: "
                            f"{timestamp_value!r}"
                        )
                    if previous_close is not None:
                        if previous_close == 0.0:
                            raise ValueError(
                                f"Zero prior close in {filename} row {row_number}"
                            )
                        gross_return = (close / previous_close) - 1.0
                        if not math.isfinite(gross_return):
                            raise ValueError(
                                f"Non-finite gross observation in {filename} row "
                                f"{row_number}"
                            )
                        observations.append((timestamp, gross_return))
                    previous_timestamp = timestamp
                    previous_close = close

            inventoried_rows = file_entry.get("row_count")
            if inventoried_rows is not None and total_rows != inventoried_rows:
                raise ValueError(
                    f"Inventoried row count changed for {filename}: "
                    f"expected {inventoried_rows}, found {total_rows}"
                )

            per_split_windows: list[dict[str, Any]] = []
            for window in windows:
                train_values = [
                    value
                    for timestamp, value in observations
                    if _timestamp_in_window(
                        timestamp,
                        start=window["train_start"],
                        end=window["train_end"],
                    )
                ]
                validation_values = [
                    value
                    for timestamp, value in observations
                    if _timestamp_in_window(
                        timestamp,
                        start=window["validation_start"],
                        end=window["validation_end"],
                        include_end=window["include_validation_end"],
                    )
                ]
                per_split_windows.append(
                    {
                        "split_id": window["split_id"],
                        "train_window": _gross_return_summary(train_values),
                        "validation_window": _gross_return_summary(validation_values),
                        "calculation_status": "GROSS_OBSERVATIONAL_RETURNS_ONLY",
                    }
                )

            file_results.append(
                {
                    "role": "bars",
                    "filename": filename,
                    "timestamp_column": "timestamp",
                    "close_column": "close",
                    **_gross_return_summary([value for _, value in observations]),
                    "per_split_windows": per_split_windows,
                    "calculation_status": "GROSS_OBSERVATIONAL_RETURNS_ONLY",
                }
            )

    return {
        "processed_role": "bars",
        "ignored_roles": ignored_roles,
        "files": file_results,
        "funding_adjusted_status": "NOT_EXECUTED",
        "calculation_status": "GROSS_OBSERVATIONAL_RETURNS_ONLY",
    }


# ── Cost-case matrix skeleton ────────────────────────────────────────────


def _cost_drag_summary(summary: dict, drag_fraction: float) -> dict[str, Any]:
    """Describe an existing gross summary after subtracting an assumption."""
    count = summary.get("observation_count")
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise ValueError("gross observation_count must be a non-negative integer")

    def adjusted(source_key: str) -> float | None:
        value = summary.get(source_key)
        if value is None:
            return None
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"gross {source_key} must be numeric or null")
        result = float(value) - drag_fraction
        if not math.isfinite(result):
            raise ValueError(f"gross {source_key} must be finite")
        return result

    return {
        "gross_observation_count": count,
        "gross_minus_drag_observation_mean": adjusted("mean_gross_return"),
        "gross_minus_drag_observation_min": adjusted("min_gross_return"),
        "gross_minus_drag_observation_max": adjusted("max_gross_return"),
    }


def materialize_cost_case_observational_drag(
    *, gross_observational_returns: dict, cost_cases: list[dict]
) -> dict:
    """Apply descriptive round-trip cost assumptions to gross observations.

    This consumes only the already-materialized gross receipt section and does
    no I/O. Each per-side assumption is doubled to describe a two-sided drag
    for one close-to-close observation.
    """
    files = gross_observational_returns.get("files")
    if not isinstance(files, list):
        raise ValueError("gross_observational_returns.files must be a list")

    cases: list[dict[str, Any]] = []
    for case in cost_cases:
        case_name = case.get("cost_case")
        if not isinstance(case_name, str) or not case_name:
            raise ValueError("cost case name must be a non-empty string")
        components: list[float] = []
        for key in (
            "commission_bps_per_side",
            "slippage_bps_per_side",
            "spread_bps_per_side",
        ):
            value = case.get(key)
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
                or value < 0.0
            ):
                raise ValueError(f"cost case {case_name!r} has invalid {key}")
            components.append(float(value))
        drag_bps = 2.0 * math.fsum(components)
        drag_fraction = drag_bps / 10_000.0

        file_summaries: list[dict[str, Any]] = []
        for file_summary in files:
            windows = file_summary.get("per_split_windows")
            if not isinstance(windows, list):
                raise ValueError("gross per_split_windows must be a list")
            split_summaries = [
                {
                    "split_id": window.get("split_id"),
                    "train_window": _cost_drag_summary(
                        window.get("train_window", {}), drag_fraction
                    ),
                    "validation_window": _cost_drag_summary(
                        window.get("validation_window", {}), drag_fraction
                    ),
                }
                for window in windows
            ]
            file_summaries.append(
                {
                    "filename": file_summary.get("filename"),
                    **_cost_drag_summary(file_summary, drag_fraction),
                    "per_split_windows": split_summaries,
                }
            )
        cases.append(
            {
                "cost_case": case_name,
                "assumed_drag_bps_per_observation": drag_bps,
                "files": file_summaries,
                "calculation_status": "DESCRIPTIVE_OBSERVATIONAL_DRAG_ONLY",
            }
        )

    return {
        "cost_cases": cases,
        "calculation_status": "DESCRIPTIVE_OBSERVATIONAL_DRAG_ONLY",
    }


# ── Funding observational adjustment metadata ─────────────────────────


def _funding_rate_summary(values: list[float]) -> dict[str, Any]:
    """Summarize observed funding rates without strategy semantics."""
    return {
        "observation_count": len(values),
        "positive_count": sum(value > 0.0 for value in values),
        "negative_count": sum(value < 0.0 for value in values),
        "zero_count": sum(value == 0.0 for value in values),
        "min_funding_rate": min(values) if values else None,
        "max_funding_rate": max(values) if values else None,
        "mean_funding_rate": math.fsum(values) / len(values) if values else None,
    }


def materialize_funding_observational_adjustments(
    *, inventory: dict, split_definitions: list[dict]
) -> dict:
    """Materialize funding-only descriptive metadata by split window.

    Only ``fundingTime`` and ``fundingRate`` are accessed. Inventoried files
    must retain their SHA256, timestamps must be strictly increasing, and bars
    inventory entries are recorded as ignored and never opened. This does not
    adjust bars or calculate strategy or portfolio results.
    """
    if not split_definitions:
        raise ValueError("split_definitions must not be empty")

    windows: list[dict[str, Any]] = []
    final_validation_index = max(
        range(len(split_definitions)),
        key=lambda index: split_definitions[index].get("split_index", index),
    )
    for index, split in enumerate(split_definitions):
        try:
            train = split["train_window"]
            validation = split["validation_window"]
            windows.append(
                {
                    "split_id": str(split["split_id"]),
                    "train_start": _parse_timestamp(str(train["start"])),
                    "train_end": _parse_timestamp(str(train["end"])),
                    "validation_start": _parse_timestamp(str(validation["start"])),
                    "validation_end": _parse_timestamp(str(validation["end"])),
                    "include_validation_end": index == final_validation_index,
                }
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid split definition at index {index}") from exc

    file_results: list[dict[str, Any]] = []
    ignored_roles: list[str] = []
    for role_entry in inventory.get("roles", []):
        role = role_entry.get("role")
        if role != "funding":
            ignored_roles.append(str(role))
            continue

        role_directory = Path(str(role_entry.get("directory", ""))).resolve()
        _refuse_if_prod_path(role_directory)
        if not role_directory.is_dir():
            raise ValueError(
                f"Inventoried funding directory is missing: {role_directory}"
            )

        for file_entry in role_entry.get("files", []):
            filename = file_entry.get("filename")
            if not isinstance(filename, str) or not filename:
                raise ValueError("Invalid inventoried filename for role 'funding'")
            filename_path = Path(filename)
            if filename_path.is_absolute() or "/" in filename or ".." in filename:
                raise ValueError(
                    f"Inventoried filename must be a simple filename: {filename!r}"
                )

            inventoried_path = role_directory / filename
            if inventoried_path.parent != role_directory:
                raise ValueError(
                    f"Inventoried file path is outside role directory: {filename}"
                )
            if not inventoried_path.exists():
                raise ValueError(f"Inventoried file is missing: {inventoried_path}")

            resolved_file = inventoried_path.resolve()
            _refuse_if_prod_path(resolved_file)
            if (
                not _is_under(resolved_file, role_directory)
                and not inventoried_path.is_symlink()
            ):
                raise ValueError(
                    f"Inventoried file resolves outside role directory: {filename}"
                )
            if not resolved_file.is_file():
                raise ValueError(f"Inventoried path is not a file: {resolved_file}")

            inventoried_sha256 = file_entry.get("sha256")
            reopened_sha256 = hashlib.sha256(resolved_file.read_bytes()).hexdigest()
            if reopened_sha256 != inventoried_sha256:
                raise ValueError(
                    f"Inventoried SHA256 changed for {filename}: "
                    f"expected {inventoried_sha256}, found {reopened_sha256}"
                )

            observations: list[tuple[datetime, float]] = []
            previous_timestamp: datetime | None = None
            total_rows = 0
            with open(resolved_file, newline="") as csv_file:
                reader = csv.reader(csv_file)
                header = next(reader, None)
                if header is None:
                    raise ValueError(f"Missing CSV header in {filename}")
                header_lookup = {name.lower(): i for i, name in enumerate(header)}
                timestamp_index = header_lookup.get("fundingtime")
                rate_index = header_lookup.get("fundingrate")
                if timestamp_index is None:
                    raise ValueError(f"Missing fundingTime column in {filename}")
                if rate_index is None:
                    raise ValueError(f"Missing fundingRate column in {filename}")

                for row_number, row in enumerate(reader, start=2):
                    total_rows += 1
                    timestamp_value = (
                        row[timestamp_index].strip()
                        if timestamp_index < len(row)
                        else ""
                    )
                    rate_value = row[rate_index].strip() if rate_index < len(row) else ""
                    try:
                        timestamp = _parse_timestamp(timestamp_value)
                    except (OverflowError, OSError, ValueError) as exc:
                        raise ValueError(
                            f"Malformed fundingTime in {filename} row {row_number}: "
                            f"{timestamp_value!r}"
                        ) from exc
                    try:
                        funding_rate = float(rate_value)
                    except ValueError as exc:
                        raise ValueError(
                            f"Malformed fundingRate in {filename} row {row_number}: "
                            f"{rate_value!r}"
                        ) from exc
                    if not math.isfinite(funding_rate):
                        raise ValueError(
                            f"Malformed fundingRate in {filename} row {row_number}: "
                            f"{rate_value!r}"
                        )
                    if previous_timestamp is not None and timestamp <= previous_timestamp:
                        raise ValueError(
                            f"Non-monotonic fundingTime in {filename} row {row_number}: "
                            f"{timestamp_value!r}"
                        )
                    observations.append((timestamp, funding_rate))
                    previous_timestamp = timestamp

            inventoried_rows = file_entry.get("row_count")
            if inventoried_rows is not None and total_rows != inventoried_rows:
                raise ValueError(
                    f"Inventoried row count changed for {filename}: "
                    f"expected {inventoried_rows}, found {total_rows}"
                )

            per_split_windows: list[dict[str, Any]] = []
            for window in windows:
                train_values = [
                    value
                    for timestamp, value in observations
                    if _timestamp_in_window(
                        timestamp,
                        start=window["train_start"],
                        end=window["train_end"],
                    )
                ]
                validation_values = [
                    value
                    for timestamp, value in observations
                    if _timestamp_in_window(
                        timestamp,
                        start=window["validation_start"],
                        end=window["validation_end"],
                        include_end=window["include_validation_end"],
                    )
                ]
                per_split_windows.append(
                    {
                        "split_id": window["split_id"],
                        "train_window": _funding_rate_summary(train_values),
                        "validation_window": _funding_rate_summary(validation_values),
                        "calculation_status": "FUNDING_OBSERVATIONAL_ADJUSTMENT_ONLY",
                    }
                )

            file_results.append(
                {
                    "role": "funding",
                    "filename": filename,
                    "timestamp_column": "fundingTime",
                    "funding_rate_column": "fundingRate",
                    **_funding_rate_summary([value for _, value in observations]),
                    "per_split_windows": per_split_windows,
                    "calculation_status": "FUNDING_OBSERVATIONAL_ADJUSTMENT_ONLY",
                }
            )

    return {
        "processed_role": "funding",
        "ignored_roles": ignored_roles,
        "files": file_results,
        "bars_adjusted_status": "NOT_EXECUTED",
        "calculation_status": "FUNDING_OBSERVATIONAL_ADJUSTMENT_ONLY",
    }


def build_cost_case_matrix() -> list[dict[str, Any]]:
    """Build the low/base/high cost-case sensitivity matrix skeleton.

    ``base`` mirrors the existing cost-model assumptions used elsewhere in
    this repo (5 bps commission/slippage per side, 1 bps spread per side).
    ``low`` and ``high`` are conservative skeleton-only bracketing
    assumptions, not derived from any measured execution data. No costs
    are actually applied here — ``calculation_status`` stays
    ``NOT_EXECUTED`` for every case.
    """
    return [
        {
            "cost_case": "low",
            "commission_bps_per_side": 2.0,
            "slippage_bps_per_side": 2.0,
            "spread_bps_per_side": 0.5,
            "funding_included": True,
            "calculation_status": "NOT_EXECUTED",
        },
        {
            "cost_case": "base",
            "commission_bps_per_side": 5.0,
            "slippage_bps_per_side": 5.0,
            "spread_bps_per_side": 1.0,
            "funding_included": True,
            "calculation_status": "NOT_EXECUTED",
        },
        {
            "cost_case": "high",
            "commission_bps_per_side": 10.0,
            "slippage_bps_per_side": 10.0,
            "spread_bps_per_side": 2.0,
            "funding_included": True,
            "calculation_status": "NOT_EXECUTED",
        },
    ]


# ── Receipt builder ──────────────────────────────────────────────────────


def _default_rationale(output_status: str) -> str:
    if output_status == BLOCKED_BY_VALIDATION_IMPLEMENTATION:
        return (
            "BLOCKED_BY_VALIDATION_IMPLEMENTATION: this is a schema/skeleton-only "
            "receipt. Gross observational close-to-close metadata may be present, "
            "but no strategy returns, PnL, Sharpe, or paper-engine calculation has "
            "been implemented. No edge/profit/live-readiness claim is made."
        )
    return f"{output_status}: skeleton receipt, no calculation implemented."


def build_real_validation_receipt(
    *,
    input_manifest_fingerprint: str,
    data_quality_receipt_sha256: str,
    code_commit_sha: str,
    split_definitions: list[dict[str, Any]],
    cost_cases: list[dict[str, Any]],
    output_status: str = BLOCKED_BY_VALIDATION_IMPLEMENTATION,
    rationale: str | None = None,
    input_inventory: dict[str, Any] | None = None,
    row_materialization: dict | None = None,
    gross_observational_returns: dict | None = None,
    cost_case_observational_drag: dict | None = None,
    funding_observational_adjustments: dict | None = None,
) -> dict[str, Any]:
    """Build the real offline validation receipt skeleton.

    This is a pure function: it performs no I/O, computes no PnL/Sharpe, and
    does not run any engine. ``output_status`` defaults to and
    (in this PR) must remain ``BLOCKED_BY_VALIDATION_IMPLEMENTATION`` —
    ``OFFLINE_EDGE_CANDIDATE`` is rejected by ``validate_real_validation_receipt``
    at this phase.

    If *input_inventory* is provided, it is included in the receipt under
    the ``input_inventory`` key, and *split_definitions* is overridden with
    definitions derived from the inventory via
    ``materialize_split_definitions_from_inventory``.
    """
    if rationale is None:
        rationale = _default_rationale(output_status)

    # If input_inventory is provided, derive split_definitions from it.
    effective_split_definitions = split_definitions
    if input_inventory is not None:
        effective_split_definitions = materialize_split_definitions_from_inventory(
            inventory=input_inventory,
            split_count=len(split_definitions) if split_definitions else 3,
        )

    receipt: dict[str, Any] = {
        "validation_receipt": {
            "kind": RECEIPT_SCHEMA_KIND,
            "version": RECEIPT_SCHEMA_VERSION,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        },
        "input_manifest_fingerprint": input_manifest_fingerprint,
        "data_quality_receipt_sha256": data_quality_receipt_sha256,
        "code_commit_sha": code_commit_sha,
        "split_definitions": effective_split_definitions,
        "cost_cases": cost_cases,
        "required_outputs_present": {
            "gross_return": False,
            "net_return_after_costs": False,
            "max_drawdown": False,
            "sharpe_or_risk_metric": False,
            "baseline_comparison": False,
            "sensitivity_cases": False,
        },
        "forbidden_calculation_status": {
            "returns_computed": False,
            "pnl_computed": False,
            "sharpe_computed": False,
            "paper_engine_run": False,
            "live_integration_used": False,
        },
        "guardrail_status": {
            "edge_unproven": True,
            "block_live_integration": True,
            "no_report_promotion": True,
            "output_under_tmp_only": True,
        },
        "final_offline_verdict": output_status,
        "final_offline_verdict_rationale": rationale,
    }

    if input_inventory is not None:
        receipt["input_inventory"] = input_inventory
    if row_materialization is not None:
        receipt["row_materialization"] = row_materialization
    if gross_observational_returns is not None:
        receipt["gross_observational_returns"] = gross_observational_returns
    if cost_case_observational_drag is not None:
        receipt["cost_case_observational_drag"] = cost_case_observational_drag
    if funding_observational_adjustments is not None:
        receipt["funding_observational_adjustments"] = funding_observational_adjustments

    return receipt


# ── Validation ────────────────────────────────────────────────────────────


_REQUIRED_TOP_LEVEL_KEYS = frozenset(
    {
        "validation_receipt",
        "input_manifest_fingerprint",
        "data_quality_receipt_sha256",
        "code_commit_sha",
        "split_definitions",
        "cost_cases",
        "required_outputs_present",
        "forbidden_calculation_status",
        "guardrail_status",
        "final_offline_verdict",
        "final_offline_verdict_rationale",
    }
)

_REQUIRED_GUARDRAIL_KEYS = frozenset(
    {
        "edge_unproven",
        "block_live_integration",
        "no_report_promotion",
        "output_under_tmp_only",
    }
)

_REQUIRED_FORBIDDEN_CALC_KEYS = frozenset(
    {
        "returns_computed",
        "pnl_computed",
        "sharpe_computed",
        "paper_engine_run",
        "live_integration_used",
    }
)


def _assert_no_forbidden_calculation_keys(value: Any, path: str = "$") -> None:
    """Recursively scan *value* for any key matching a forbidden calculation pattern.

    Forbidden patterns (exact dict key match):
    ``pnl``, ``sharpe``, ``edge``, ``strategy_performance``,
    ``return``, ``returns``, ``gross_return_value``, ``net_return_value``,
    ``price_change``, ``trade``, ``trades``, ``signal``, ``signals``,
    ``position``, ``positions``, ``portfolio``, ``live_ready``,
    ``deploy_ready``, and ``profitable``.

    Raises ``ValueError`` if any forbidden key is found at any nesting level.
    """
    if isinstance(value, dict):
        for key, v in value.items():
            gross_observation_key_allowed = (
                key == "gross_observational_return"
                and path.startswith("$.gross_observational_returns")
            )
            if key in FORBIDDEN_CALCULATION_KEYS and not gross_observation_key_allowed:
                raise ValueError(
                    f"Forbidden calculation key found at {path}.{key!r}"
                )
            _assert_no_forbidden_calculation_keys(v, path + "." + key)
    elif isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            _assert_no_forbidden_calculation_keys(v, path + "[" + str(i) + "]")


def validate_real_validation_receipt(receipt: dict[str, Any]) -> None:
    """Validate a real-validation receipt dict.

    Raises ``ValueError`` for any of: missing required top-level keys,
    a forbidden top-level key (``pnl``/``sharpe``/``edge``/
    ``strategy_performance``), a ``final_offline_verdict`` outside the
    allowed vocabulary, ``OFFLINE_EDGE_CANDIDATE`` at this skeleton phase,
    a missing/false ``guardrail_status`` entry, a missing/true
    ``forbidden_calculation_status`` entry, or an ``output_path`` that is
    not under ``/tmp`` or that resolves under ``/srv/qnty``.

    Also recursively scans for forbidden calculation keys at any nesting
    level (``pnl``, ``sharpe``, ``edge``, ``strategy_performance``,
    ``return``, ``returns``, ``gross_return_value``, ``net_return_value``,
    ``price_change``, ``trade``, ``trades``, ``signal``, ``signals``,
    ``position``, and ``positions``).
    """
    missing = _REQUIRED_TOP_LEVEL_KEYS - set(receipt.keys())
    if missing:
        raise ValueError(f"Missing required keys: {sorted(missing)}")

    forbidden_present = FORBIDDEN_TOP_LEVEL_KEYS & set(receipt.keys())
    if forbidden_present:
        raise ValueError(f"Forbidden top-level keys present: {sorted(forbidden_present)}")

    verdict = receipt["final_offline_verdict"]
    if verdict not in ALLOWED_FINAL_VERDICTS:
        raise ValueError(
            f"final_offline_verdict '{verdict}' is not in allowed vocabulary: "
            f"{sorted(ALLOWED_FINAL_VERDICTS)}"
        )
    if verdict not in _SKELETON_ALLOWED_VERDICTS:
        raise ValueError(
            f"final_offline_verdict '{verdict}' is not allowed in the "
            f"receipt-skeleton phase. Only {sorted(_SKELETON_ALLOWED_VERDICTS)} "
            "may be emitted until a real validator is implemented."
        )

    guardrail_status = receipt.get("guardrail_status")
    if not isinstance(guardrail_status, dict):
        raise ValueError("guardrail_status must be a dict")
    missing_guardrails = _REQUIRED_GUARDRAIL_KEYS - set(guardrail_status.keys())
    if missing_guardrails:
        raise ValueError(f"Missing guardrail_status keys: {sorted(missing_guardrails)}")
    for key in _REQUIRED_GUARDRAIL_KEYS:
        if guardrail_status[key] is not True:
            raise ValueError(f"guardrail_status['{key}'] must be True, got {guardrail_status[key]!r}")

    forbidden_calc = receipt.get("forbidden_calculation_status")
    if not isinstance(forbidden_calc, dict):
        raise ValueError("forbidden_calculation_status must be a dict")
    missing_calc = _REQUIRED_FORBIDDEN_CALC_KEYS - set(forbidden_calc.keys())
    if missing_calc:
        raise ValueError(f"Missing forbidden_calculation_status keys: {sorted(missing_calc)}")
    for key in _REQUIRED_FORBIDDEN_CALC_KEYS:
        if forbidden_calc[key] is not False:
            raise ValueError(
                f"forbidden_calculation_status['{key}'] must be False, got {forbidden_calc[key]!r}"
            )

    output_path = receipt.get("output_path")
    if output_path is not None:
        resolved = Path(str(output_path)).resolve()
        _refuse_if_prod_path(resolved)
        _refuse_if_not_tmp(resolved)

    _assert_no_prod_paths_in_receipt(receipt)

    # Recursive scan for forbidden calculation keys at any nesting level.
    _assert_no_forbidden_calculation_keys(receipt)


# ── Output writer ─────────────────────────────────────────────────────────


def write_real_validation_receipt(receipt: dict[str, Any], output_path: Path) -> str:
    """Validate and write *receipt* as JSON to *output_path* under ``/tmp`` only.

    Returns the SHA256 hex digest of the exact bytes written. Refuses to
    write anywhere that does not resolve under ``/tmp``, and refuses any
    path resolving under ``/srv/qnty``.
    """
    validate_real_validation_receipt(receipt)

    resolved = output_path.resolve()
    _refuse_if_prod_path(resolved)
    _refuse_if_not_tmp(resolved)

    resolved.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(receipt, indent=2)
    with open(resolved, "w") as f:
        f.write(payload)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ── CLI skeleton ───────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Real offline validation receipt skeleton (no-op). "
            "Emits BLOCKED_BY_VALIDATION_IMPLEMENTATION only."
        )
    )
    parser.add_argument("--read-only", action="store_true", required=True)
    parser.add_argument("--output-dir", required=True, help="Must resolve under /tmp.")
    parser.add_argument("--input-manifest-fingerprint", required=True)
    parser.add_argument("--data-quality-receipt-sha256", required=True)
    parser.add_argument("--code-commit-sha", required=True)
    parser.add_argument(
        "--global-min-timestamp",
        default=None,
        help="Required if --bars-dir is not provided.",
    )
    parser.add_argument(
        "--global-max-timestamp",
        default=None,
        help="Required if --bars-dir is not provided.",
    )
    parser.add_argument("--split-count", type=int, default=3)
    parser.add_argument(
        "--bars-dir",
        default=None,
        type=str,
        help="Path to bars CSV directory. Alternative to --global-min/--global-max.",
    )
    parser.add_argument(
        "--funding-dir",
        default=None,
        type=str,
        help="Optional path to funding CSV directory (used with --bars-dir).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir).resolve()
    try:
        _refuse_if_prod_path(output_dir)
        _refuse_if_not_tmp(output_dir)
    except ValueError as exc:
        print(f"FATAL: {exc}")
        return 3

    cost_cases = build_cost_case_matrix()

    if args.bars_dir is not None:
        # Inventory-based path: derive everything from real data directories.
        bars_dir = Path(args.bars_dir)
        funding_dir = Path(args.funding_dir) if args.funding_dir else None

        try:
            inventory = build_real_validation_input_inventory(
                bars_dir=bars_dir,
                funding_dir=funding_dir,
            )
            split_definitions = materialize_split_definitions_from_inventory(
                inventory=inventory,
                split_count=args.split_count,
            )
            row_materialization = materialize_input_rows_for_splits(
                inventory=inventory,
                split_definitions=split_definitions,
            )
            gross_observational_returns = materialize_gross_observational_returns(
                inventory=inventory,
                split_definitions=split_definitions,
            )
            cost_case_observational_drag = materialize_cost_case_observational_drag(
                gross_observational_returns=gross_observational_returns,
                cost_cases=cost_cases,
            )
            funding_observational_adjustments = (
                materialize_funding_observational_adjustments(
                    inventory=inventory,
                    split_definitions=split_definitions,
                )
            )
        except ValueError as exc:
            print(f"FATAL: offline materialization failed: {exc}")
            return 4

        receipt = build_real_validation_receipt(
            input_manifest_fingerprint=args.input_manifest_fingerprint,
            data_quality_receipt_sha256=args.data_quality_receipt_sha256,
            code_commit_sha=args.code_commit_sha,
            split_definitions=split_definitions,
            cost_cases=cost_cases,
            input_inventory=inventory,
            row_materialization=row_materialization,
            gross_observational_returns=gross_observational_returns,
            cost_case_observational_drag=cost_case_observational_drag,
            funding_observational_adjustments=funding_observational_adjustments,
        )
    else:
        # Legacy path: use CLI-provided timestamp bounds.
        if args.global_min_timestamp is None or args.global_max_timestamp is None:
            print(
                "FATAL: --global-min-timestamp and --global-max-timestamp are "
                "required when --bars-dir is not provided."
            )
            return 5

        split_definitions = build_deterministic_split_definitions(
            global_min_timestamp=args.global_min_timestamp,
            global_max_timestamp=args.global_max_timestamp,
            split_count=args.split_count,
        )

        receipt = build_real_validation_receipt(
            input_manifest_fingerprint=args.input_manifest_fingerprint,
            data_quality_receipt_sha256=args.data_quality_receipt_sha256,
            code_commit_sha=args.code_commit_sha,
            split_definitions=split_definitions,
            cost_cases=cost_cases,
        )

    output_path = output_dir / "real_validation_receipt.json"
    digest = write_real_validation_receipt(receipt, output_path)

    print(f"final_offline_verdict={receipt['final_offline_verdict']}")
    print(f"receipt_sha256={digest}")
    print(f"receipt_path={output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
