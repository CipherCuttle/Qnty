"""Read-only data quality preflight for offline edge CSV input directories.

Stdlib-only. No engine, exchange, DB, numpy, pandas, or file-write dependencies.
"""

import csv
import json
import os
from pathlib import Path
from typing import Any

from quantbot.experiment.offline_edge_schema import DATA_QUALITY_PREFLIGHT_VERSION

# ── Constants ──────────────────────────────────────────────────────────

# Schema-aware data-quality profiles.  Bars/OHLCV and Binance funding-rate
# CSVs have different real column shapes; validating funding files against
# the bars required-column set was wrongly failing readiness for funding
# coverage that is actually structurally fine.  Each profile defines its own
# required columns and timestamp column so requirements never leak across
# roles (see build_data_quality_preflight_for_roles).
SCHEMA_PROFILES: dict[str, dict[str, Any]] = {
    "bars": {
        "required_columns": {"timestamp", "close", "volume"},
        "timestamp_column": "timestamp",
    },
    "funding": {
        # Binance funding-rate CSV shape: symbol,fundingTime,fundingRate,markPrice
        "required_columns": {"symbol", "fundingTime", "fundingRate"},
        "timestamp_column": "fundingTime",
    },
    "manifest": {
        # Light structural check only — no OHLCV/funding columns required.
        "required_columns": set(),
        "timestamp_column": None,
    },
}

_REQUIRED_COLUMNS: set[str] = SCHEMA_PROFILES["bars"]["required_columns"]
PROD_BASE = Path("/srv/qnty")

# ── Prod-path guard ────────────────────────────────────────────────────


def _refuse_prod_path(p: Path) -> None:
    """Refuse paths under /srv/qnty using commonpath boundary logic."""
    resolved = p.resolve()
    prod_boundary = PROD_BASE.resolve()
    if os.path.commonpath([str(resolved), str(prod_boundary)]) == str(prod_boundary):
        raise ValueError(f"Path resolves under production boundary: {p}")


# ── CSV-level inspection ────────────────────────────────────────────────


def inspect_csv_file(path: Path, profile: str = "bars") -> dict[str, Any]:
    """Inspect a single CSV file for data quality metrics.

    Reads the file using ``csv.DictReader`` and reports row count, header
    completeness, timestamp integrity (duplicates, monotonicity), null
    cell detection, and timestamp range — all relative to *profile*'s
    required columns and timestamp column (see :data:`SCHEMA_PROFILES`).
    Defaults to the ``"bars"`` profile for backward compatibility.

    ``has_null_values`` (and therefore the ``no_null_required_values``
    readiness flag) reflects nulls in *required* columns only — a null in an
    optional column (e.g. funding's ``markPrice``) never fails readiness.
    Nulls are still tracked per-column for visibility via ``null_columns``
    (all columns with a null cell), ``null_required_columns`` (the subset
    that are required), and ``optional_null_columns`` (the subset that are
    not).

    Never raises for malformed CSV content; catches ``csv.Error`` and
    stores the message in the ``error`` key. Raises ``ValueError`` for an
    unknown *profile* (fail closed on caller error).
    """
    _refuse_prod_path(path)
    if profile not in SCHEMA_PROFILES:
        raise ValueError(
            f"Unknown data-quality profile: {profile!r}. "
            f"Allowed: {sorted(SCHEMA_PROFILES)}"
        )
    profile_config = SCHEMA_PROFILES[profile]
    required_columns: set[str] = profile_config["required_columns"]
    timestamp_column: str | None = profile_config["timestamp_column"]

    result: dict[str, Any] = {
        "path": str(path),
        "profile": profile,
        "required_columns": sorted(required_columns),
        "timestamp_column": timestamp_column,
        "row_count": 0,
        "headers": [],
        "has_timestamp_column": timestamp_column is None,
        "missing_required_columns": [],
        "has_duplicate_timestamps": False,
        "has_non_monotonic_timestamps": False,
        "has_null_values": False,
        "null_columns": [],
        "null_required_columns": [],
        "optional_null_columns": [],
        "min_timestamp": None,
        "max_timestamp": None,
        "error": None,
    }

    try:
        with open(path, "r", newline="") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames or []
            result["headers"] = headers
            has_ts_col = timestamp_column is not None and timestamp_column in headers
            result["has_timestamp_column"] = (
                True if timestamp_column is None else has_ts_col
            )

            missing = sorted(required_columns - set(headers))
            result["missing_required_columns"] = missing

            rows = list(reader)
            result["row_count"] = len(rows)

            if not rows:
                return result

            timestamps: list[str] = []
            null_columns: set[str] = set()

            for row in rows:
                # Track which columns have a null/empty cell anywhere in the
                # file. Every column is checked (for visibility), but only
                # nulls in *required* columns feed readiness (has_null_values
                # / no_null_required_values) — an optional column such as
                # funding's markPrice must not block readiness.
                for col, val in row.items():
                    if col is None:
                        continue
                    cleaned = val.strip().lower() if val else val
                    if val == "" or cleaned in ("nan", "null", "none", "na"):
                        null_columns.add(col)

                # Collect timestamps if the profile's timestamp column exists
                if has_ts_col:
                    ts = row.get(timestamp_column, "")
                    if ts is not None and ts.strip():
                        timestamps.append(ts)

            null_required_columns = sorted(null_columns & required_columns)
            optional_null_columns = sorted(null_columns - required_columns)
            result["null_columns"] = sorted(null_columns)
            result["null_required_columns"] = null_required_columns
            result["optional_null_columns"] = optional_null_columns
            result["has_null_values"] = bool(null_required_columns)

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


def _inspect_manifest_json_file(path: Path) -> dict[str, Any]:
    """Light, stdlib-only structural check for a manifest JSON file.

    Refuses paths resolving under the production boundary (``/srv/qnty``),
    same as :func:`inspect_csv_file` — protects against a manifest directory
    entry (direct call or symlink) resolving into a prod path. Otherwise
    never raises; malformed JSON is reported via the ``error`` key.
    Does not require any OHLCV/funding columns — manifest files are not CSVs.
    """
    _refuse_prod_path(path)
    result: dict[str, Any] = {
        "path": str(path),
        "kind": "manifest_json",
        "filename": path.name,
        "is_valid_json": False,
        "top_level_key_count": None,
        "error": None,
    }
    try:
        with open(path, "r") as f:
            data = json.load(f)
        result["is_valid_json"] = True
        if isinstance(data, (dict, list)):
            result["top_level_key_count"] = len(data)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
        result["error"] = str(e)
    return result


# ── Directory-level inspection ─────────────────────────────────────────


def inspect_input_directory(path: Path, profile: str = "bars") -> dict[str, Any]:
    """Inspect an input directory for data quality metrics.

    Resolves *path*, verifies it exists (``FileNotFoundError``) and is
    not under the production boundary (``ValueError``).  Lists regular
    files only in sorted order, runs :func:`inspect_csv_file` on each
    CSV using *profile*'s schema (see :data:`SCHEMA_PROFILES`), and
    aggregates results. Defaults to the ``"bars"`` profile for backward
    compatibility. For the ``"manifest"`` profile, ``.json`` files get a
    light stdlib-only structural check instead of being treated as opaque
    non-CSV entries.

    Parameters
    ----------
    path : Path
        Directory path to inspect.
    profile : str
        Schema profile to validate CSV files against — one of
        ``SCHEMA_PROFILES`` (``"bars"``, ``"funding"``, ``"manifest"``).

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
        If *path* resolves under the production boundary, or *profile* is
        unknown.
    """
    _refuse_prod_path(path)
    if profile not in SCHEMA_PROFILES:
        raise ValueError(
            f"Unknown data-quality profile: {profile!r}. "
            f"Allowed: {sorted(SCHEMA_PROFILES)}"
        )

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
            csv_file_results.append(inspect_csv_file(entry, profile=profile))
        elif profile == "manifest" and entry.suffix.lower() == ".json":
            non_csv_names.append(entry.name)
            non_csv_entries.append(_inspect_manifest_json_file(entry))
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
        "profile": profile,
        "required_columns": sorted(SCHEMA_PROFILES[profile]["required_columns"]),
        "timestamp_column": SCHEMA_PROFILES[profile]["timestamp_column"],
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


def build_data_quality_preflight(
    paths: list[Path], profile: str = "bars"
) -> dict[str, Any]:
    """Run data quality preflight across multiple input directories.

    All *paths* are validated against the same *profile* (defaults to
    ``"bars"`` for backward compatibility). To validate bars, funding, and
    manifest directories against their own distinct schemas in one preflight
    call, use :func:`build_data_quality_preflight_for_roles` instead.

    Parameters
    ----------
    paths : list[Path]
        One or more directory paths to inspect.
    profile : str
        Schema profile applied to every directory in *paths*.

    Returns
    -------
    dict
        Aggregated summary with readiness flags.
    """
    if not paths:
        raise ValueError("At least one input directory path is required")
    dir_results = [inspect_input_directory(p, profile=profile) for p in paths]

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
    csv_entries = [
        f for f in all_files if f.get("kind") not in ("non_csv", "manifest_json")
    ]
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


def build_data_quality_preflight_for_roles(
    bars_dir: Path | None = None,
    funding_dir: Path | None = None,
    manifest_dir: Path | None = None,
) -> dict[str, Any]:
    """Role-aware data quality preflight.

    Unlike :func:`build_data_quality_preflight`, each directory is inspected
    against its own schema profile (bars/funding/manifest — see
    :data:`SCHEMA_PROFILES`), so requirements never leak across roles: a
    funding directory is not penalized for missing ``close``/``volume``, and
    a bars directory is not penalized for missing ``fundingTime``.

    At least one of *bars_dir*, *funding_dir*, *manifest_dir* is required.

    Returns
    -------
    dict
        Same top-level keys as :func:`build_data_quality_preflight` (so
        :func:`validate_data_quality_preflight` still applies), plus
        ``roles`` (per-role directory results), ``missing_required_columns_by_role``,
        and a ``readiness_flags["by_role"]`` breakdown.
    """
    role_dirs: list[tuple[str, Path]] = []
    if bars_dir is not None:
        role_dirs.append(("bars", bars_dir))
    if funding_dir is not None:
        role_dirs.append(("funding", funding_dir))
    if manifest_dir is not None:
        role_dirs.append(("manifest", manifest_dir))

    if not role_dirs:
        raise ValueError("At least one input directory path is required")

    roles: dict[str, dict[str, Any] | None] = {
        "bars": None,
        "funding": None,
        "manifest": None,
    }
    dir_results: list[dict[str, Any]] = []
    for role, role_path in role_dirs:
        dir_result = inspect_input_directory(role_path, profile=role)
        roles[role] = dir_result
        dir_results.append(dir_result)

    total_file_count = sum(d["file_count"] for d in dir_results)
    total_csv_count = sum(d["csv_file_count"] for d in dir_results)
    total_non_csv_count = sum(d["non_csv_file_count"] for d in dir_results)
    total_row_count = sum(d["total_row_count"] for d in dir_results)

    all_files: list[dict[str, Any]] = []
    for d in dir_results:
        all_files.extend(d["files"])

    all_min_ts: list[str] = []
    all_max_ts: list[str] = []
    for d in dir_results:
        if d["global_min_timestamp"] is not None:
            all_min_ts.append(d["global_min_timestamp"])
        if d["global_max_timestamp"] is not None:
            all_max_ts.append(d["global_max_timestamp"])
    global_min = min(all_min_ts) if all_min_ts else None
    global_max = max(all_max_ts) if all_max_ts else None

    has_dup = any(d["has_duplicate_timestamps"] for d in dir_results)
    has_non_mono = any(d["has_non_monotonic_timestamps"] for d in dir_results)
    has_nulls = any(d["has_null_values"] for d in dir_results)

    missing_by_role: dict[str, list[str]] = {}
    for role, dir_result in roles.items():
        if dir_result is not None:
            missing_by_role[role] = dir_result["missing_required_columns"]
    missing_union: set[str] = set()
    for cols in missing_by_role.values():
        missing_union.update(cols)

    # Role-aware readiness: each present role's gates are evaluated using
    # only that role's own schema profile — no cross-role column leakage.
    readiness_by_role: dict[str, dict[str, Any]] = {}
    for role, dir_result in roles.items():
        if dir_result is None:
            continue
        csv_entries = [
            f
            for f in dir_result["files"]
            if f.get("kind") not in ("non_csv", "manifest_json")
        ]
        readiness_by_role[role] = {
            "has_any_rows": dir_result["total_row_count"] > 0,
            "has_timestamp_column": (
                len(csv_entries) == 0
                or all(f["has_timestamp_column"] for f in csv_entries)
            ),
            "timestamps_monotonic": not dir_result["has_non_monotonic_timestamps"],
            "no_duplicate_timestamps": not dir_result["has_duplicate_timestamps"],
            "no_null_required_values": not dir_result["has_null_values"],
            "missing_required_columns": dir_result["missing_required_columns"],
        }

    readiness_flags: dict[str, Any] = {
        "has_any_rows": total_row_count > 0,
        "has_timestamp_column": (
            all(r["has_timestamp_column"] for r in readiness_by_role.values())
            if readiness_by_role
            else False
        ),
        "timestamps_monotonic": not has_non_mono,
        "no_duplicate_timestamps": not has_dup,
        "no_null_required_values": not has_nulls,
        "data_quality_preflight_only": True,
        "by_role": readiness_by_role,
    }

    return {
        "data_quality_version": DATA_QUALITY_PREFLIGHT_VERSION,
        "input_directories": [str(p) for _, p in role_dirs],
        "roles": roles,
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
        "missing_required_columns": sorted(missing_union),
        "missing_required_columns_by_role": missing_by_role,
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