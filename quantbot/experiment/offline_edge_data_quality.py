"""Read-only data quality preflight for offline edge CSV input directories.

Stdlib-only. No engine, exchange, DB, numpy, pandas, or file-write dependencies.
"""

import csv
import os
from pathlib import Path
from typing import Any

from quantbot.experiment.offline_edge_schema import DATA_QUALITY_PREFLIGHT_VERSION

# ── Constants ──────────────────────────────────────────────────────────

_REQUIRED_COLUMNS: set[str] = {"timestamp", "close", "volume"}
PROD_BASE = Path("/srv/qnty")

# ── Prod-path guard ────────────────────────────────────────────────────


def _refuse_prod_path(p: Path) -> None:
    """Refuse paths under /srv/qnty using commonpath boundary logic."""
    resolved = p.resolve()
    prod_boundary = PROD_BASE.resolve()
    if os.path.commonpath([str(resolved), str(prod_boundary)]) == str(prod_boundary):
        raise ValueError(f"Path resolves under production boundary: {p}")


# ── CSV-level inspection ────────────────────────────────────────────────


def inspect_csv_file(path: Path) -> dict[str, Any]:
    """Inspect a single CSV file for data quality metrics.

    Reads the file using ``csv.DictReader`` and reports row count, header
    completeness, timestamp integrity (duplicates, monotonicity), null
    cell detection, and timestamp range.

    Never raises; catches ``csv.Error`` and stores the message in the
    ``error`` key.
    """
    _refuse_prod_path(path)
    result: dict[str, Any] = {
        "path": str(path),
        "row_count": 0,
        "headers": [],
        "has_timestamp_column": False,
        "missing_required_columns": [],
        "has_duplicate_timestamps": False,
        "has_non_monotonic_timestamps": False,
        "has_null_values": False,
        "min_timestamp": None,
        "max_timestamp": None,
        "error": None,
    }

    try:
        with open(path, "r", newline="") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames or []
            result["headers"] = headers
            result["has_timestamp_column"] = "timestamp" in headers

            missing = sorted(_REQUIRED_COLUMNS - set(headers))
            result["missing_required_columns"] = missing

            rows = list(reader)
            result["row_count"] = len(rows)

            if not rows:
                return result

            timestamps: list[str] = []
            has_nulls = False
            has_ts_col = "timestamp" in headers

            for row in rows:
                # Null check across all cells — stop early once found
                if not has_nulls:
                    for val in row.values():
                        cleaned = val.strip().lower() if val else val
                        if val == "" or cleaned in ("nan", "null", "none", "na"):
                            has_nulls = True
                            break

                # Collect timestamps if the column exists
                if has_ts_col:
                    ts = row.get("timestamp", "")
                    if ts is not None and ts.strip():
                        timestamps.append(ts)

            result["has_null_values"] = has_nulls

            if timestamps and has_ts_col:
                result["has_duplicate_timestamps"] = len(timestamps) != len(
                    set(timestamps)
                )

                prev = timestamps[0]
                for ts in timestamps[1:]:
                    if ts < prev:
                        result["has_non_monotonic_timestamps"] = True
                        break
                    prev = ts

                result["min_timestamp"] = min(timestamps)
                result["max_timestamp"] = max(timestamps)

    except csv.Error as e:
        result["error"] = str(e)

    return result


# ── Directory-level inspection ─────────────────────────────────────────


def inspect_input_directory(path: Path) -> dict[str, Any]:
    """Inspect an input directory for data quality metrics.

    Resolves *path*, verifies it exists (``FileNotFoundError``) and is
    not under the production boundary (``ValueError``).  Lists regular
    files only in sorted order, runs :func:`inspect_csv_file` on each
    CSV, and aggregates results.

    Parameters
    ----------
    path : Path
        Directory path to inspect.

    Returns
    -------
    dict
        Directory-level metrics including per-file details.

    Raises
    ------
    FileNotFoundError
        If *path* does not exist.
    NotADirectoryError
        If *path* is not a directory.
    ValueError
        If *path* resolves under the production boundary.
    """
    _refuse_prod_path(path)

    resolved = path.resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Input directory does not exist: {path}")
    if not resolved.is_dir():
        raise NotADirectoryError(f"Input path is not a directory: {path}")

    csv_file_results: list[dict[str, Any]] = []
    non_csv_names: list[str] = []
    non_csv_entries: list[dict[str, Any]] = []

    for entry in sorted(resolved.iterdir()):
        if not entry.is_file():
            continue
        if entry.suffix.lower() == ".csv":
            csv_file_results.append(inspect_csv_file(entry))
        else:
            non_csv_names.append(entry.name)
            non_csv_entries.append(
                {
                    "path": str(entry),
                    "kind": "non_csv",
                    "filename": entry.name,
                }
            )

    csv_file_count = len(csv_file_results)
    non_csv_file_count = len(non_csv_names)
    total_row_count = sum(f["row_count"] for f in csv_file_results)

    # Aggregate timestamp range across all CSV files in this directory
    all_min_ts: list[str] = []
    all_max_ts: list[str] = []
    for f in csv_file_results:
        if f["min_timestamp"] is not None:
            all_min_ts.append(f["min_timestamp"])
        if f["max_timestamp"] is not None:
            all_max_ts.append(f["max_timestamp"])

    global_min = min(all_min_ts) if all_min_ts else None
    global_max = max(all_max_ts) if all_max_ts else None

    # Aggregate boolean flags (OR across files)
    has_dup = any(f["has_duplicate_timestamps"] for f in csv_file_results)
    has_non_mono = any(
        f["has_non_monotonic_timestamps"] for f in csv_file_results
    )
    has_nulls = any(f["has_null_values"] for f in csv_file_results)

    # Aggregate missing required columns (union across files)
    missing_union: set[str] = set()
    for f in csv_file_results:
        missing_union.update(f["missing_required_columns"])
    missing_sorted = sorted(missing_union)

    return {
        "directory": str(resolved),
        "file_count": csv_file_count + non_csv_file_count,
        "csv_file_count": csv_file_count,
        "non_csv_file_count": non_csv_file_count,
        "non_csv_files": non_csv_names,
        "total_row_count": total_row_count,
        "files": csv_file_results + non_csv_entries,
        "global_min_timestamp": global_min,
        "global_max_timestamp": global_max,
        "has_duplicate_timestamps": has_dup,
        "has_non_monotonic_timestamps": has_non_mono,
        "has_null_values": has_nulls,
        "missing_required_columns": missing_sorted,
    }


# ── Preflight aggregation ──────────────────────────────────────────────


def build_data_quality_preflight(paths: list[Path]) -> dict[str, Any]:
    """Run data quality preflight across multiple input directories.

    Parameters
    ----------
    paths : list[Path]
        One or more directory paths to inspect.

    Returns
    -------
    dict
        Aggregated summary with readiness flags.
    """
    if not paths:
        raise ValueError("At least one input directory path is required")
    dir_results = [inspect_input_directory(p) for p in paths]

    # Summed counts
    total_file_count = sum(d["file_count"] for d in dir_results)
    total_csv_count = sum(d["csv_file_count"] for d in dir_results)
    total_non_csv_count = sum(d["non_csv_file_count"] for d in dir_results)
    total_row_count = sum(d["total_row_count"] for d in dir_results)

    # Flatten all per-file entries
    all_files: list[dict[str, Any]] = []
    for d in dir_results:
        all_files.extend(d["files"])

    # Global timestamp range across all directories
    all_min_ts: list[str] = []
    all_max_ts: list[str] = []
    for d in dir_results:
        if d["global_min_timestamp"] is not None:
            all_min_ts.append(d["global_min_timestamp"])
        if d["global_max_timestamp"] is not None:
            all_max_ts.append(d["global_max_timestamp"])

    global_min = min(all_min_ts) if all_min_ts else None
    global_max = max(all_max_ts) if all_max_ts else None

    # Aggregate boolean flags (OR across directories)
    has_dup = any(d["has_duplicate_timestamps"] for d in dir_results)
    has_non_mono = any(
        d["has_non_monotonic_timestamps"] for d in dir_results
    )
    has_nulls = any(d["has_null_values"] for d in dir_results)

    # Aggregate missing required columns (union across directories)
    missing_union: set[str] = set()
    for d in dir_results:
        missing_union.update(d["missing_required_columns"])
    missing_sorted = sorted(missing_union)

    # ── Readiness flags (conservative defaults) ────────────────────
    csv_entries = [f for f in all_files if f.get("kind") != "non_csv"]
    has_any_rows = total_row_count > 0
    has_timestamp_col = (
        len(csv_entries) > 0
        and all(f["has_timestamp_column"] for f in csv_entries)
    )

    readiness_flags: dict[str, Any] = {
        "has_any_rows": has_any_rows,
        "has_timestamp_column": has_timestamp_col,
        "timestamps_monotonic": not has_non_mono,
        "no_duplicate_timestamps": not has_dup,
        "no_null_required_values": not has_nulls,
        "data_quality_preflight_only": True,
    }

    return {
        "data_quality_version": DATA_QUALITY_PREFLIGHT_VERSION,
        "input_directories": [str(p) for p in paths],
        "file_count": total_file_count,
        "csv_file_count": total_csv_count,
        "non_csv_file_count": total_non_csv_count,
        "total_row_count": total_row_count,
        "files": all_files,
        "global_min_timestamp": global_min,
        "global_max_timestamp": global_max,
        "has_duplicate_timestamps": has_dup,
        "has_non_monotonic_timestamps": has_non_mono,
        "has_null_values": has_nulls,
        "missing_required_columns": missing_sorted,
        "readiness_flags": readiness_flags,
    }


# ── Validation ─────────────────────────────────────────────────────────


def validate_data_quality_preflight(summary: dict[str, Any]) -> None:
    """Validate the structure of a data quality preflight summary.

    Checks that all required top-level keys and readiness flag keys
    exist, and that the version constant matches the expected value.

    Parameters
    ----------
    summary : dict
        The summary dict returned by :func:`build_data_quality_preflight`.

    Raises
    ------
    ValueError
        If any required key is missing or the version is wrong.
    """
    _REQUIRED_TOP_KEYS: set[str] = {
        "data_quality_version",
        "input_directories",
        "file_count",
        "csv_file_count",
        "non_csv_file_count",
        "total_row_count",
        "files",
        "global_min_timestamp",
        "global_max_timestamp",
        "has_duplicate_timestamps",
        "has_non_monotonic_timestamps",
        "has_null_values",
        "missing_required_columns",
        "readiness_flags",
    }

    _REQUIRED_READINESS_KEYS: set[str] = {
        "has_any_rows",
        "has_timestamp_column",
        "timestamps_monotonic",
        "no_duplicate_timestamps",
        "no_null_required_values",
        "data_quality_preflight_only",
    }

    missing_top = _REQUIRED_TOP_KEYS - summary.keys()
    if missing_top:
        raise ValueError(
            f"Missing required top-level keys: {sorted(missing_top)}"
        )

    readiness = summary.get("readiness_flags")
    if not isinstance(readiness, dict):
        raise ValueError(
            f"readiness_flags must be a dict, got {type(readiness).__name__}"
        )

    missing_readiness = _REQUIRED_READINESS_KEYS - readiness.keys()
    if missing_readiness:
        raise ValueError(
            f"Missing required readiness flag keys: {sorted(missing_readiness)}"
        )

    expected_version = DATA_QUALITY_PREFLIGHT_VERSION
    actual_version = summary.get("data_quality_version")
    if actual_version != expected_version:
        raise ValueError(
            f"data_quality_version mismatch: expected {expected_version!r}, "
            f"got {actual_version!r}"
        )