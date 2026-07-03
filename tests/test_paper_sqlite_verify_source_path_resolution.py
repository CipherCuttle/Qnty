"""Test-only contract for SQLite verifier source path resolution.

These tests specify future CLI behavior for deterministic funding source path
resolution. They use tmp SQLite DBs, tmp CSVs, and tmp sidecars only. They do
not touch /srv, do not run prod or shadow writers, do not mutate forward_obs,
and do not implement production verifier behavior.

Required source path order:
  A. explicit --data-dir absolute path
  B. committed snapshot/provenance source path, when implemented
  C. fail closed with source_path_unavailable

No cwd-relative ``data`` fallback is an accepted source.
"""

from __future__ import annotations

import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from quantbot.core.determinism import sha256_file
from quantbot.paper.funding_source_snapshot import (
    build_funding_source_snapshot_envelope_v1,
    build_funding_source_snapshot_payload_v1,
)
from tests.test_paper_sqlite_funding_coverage import (
    _build_funding_db,
    _funding_rows_complete,
    _tmp_csv_complete,
)
from tests.test_paper_sqlite_verifier_clean_net_of_carry_gate import (
    _GENERATED_AT,
    _GIT_SHA,
    _add_latest_equity_snapshot,
    _required_windows,
    _set_latest_batch_snapshot_reference,
    _write_snapshot,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_XFAIL_REASON = "deterministic verifier source path resolution not implemented yet"

_SOURCE_PATH_UNAVAILABLE = "source_path_unavailable"
_MISLEADING_SOURCE_REASON_CODES = {
    "funding_source_file_digest_mismatch",
    "funding_source_row_digest_mismatch",
    "funding_source_coverage_not_complete",
    "funding_source_missing",
    "funding_source_partial",
    "missing_source_row",
}

_REQUIRED_READ_ONLY_JSON_FIELDS = {
    "status",
    "funding_clean_carry_decision",
    "funding_clean_carry_status",
    "funding_clean_carry_reason_codes",
    "funding_source_snapshot_status",
    "funding_source_snapshot",
    "read_only",
    "db_path",
    "db_mutation_performed",
    "query_only_pragma_enabled",
    "wal_shm_files_created",
    "verifier_cli_contract_version",
    "resolved_funding_source_dir",
    "source_path_resolution_mode",
}


def _run_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "quantbot.paper.sqlite_verify", *args],
        cwd=str(cwd or _REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )


def _run_cli_json(
    *args: str,
    cwd: Path | None = None,
) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    proc = _run_cli(*args, cwd=cwd)
    assert proc.stdout.strip(), proc.stderr
    return proc, json.loads(proc.stdout)


def _source_rows_from_csv_dir(csv_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(csv_dir.glob("*_8h_funding.csv")):
        symbol = path.name.removesuffix("_8h_funding.csv")
        snapshot_path = f"data/{path.name}"
        with path.open("r", newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row_index, row in enumerate(reader, start=1):
                rows.append(
                    {
                        "symbol": symbol,
                        "fundingTime_ms": int(row["fundingTime"]),
                        "source_file_path": snapshot_path,
                        "row_index": row_index,
                        "funding_rate": str(row["fundingRate"]),
                    }
                )
    return rows


def _source_file_contents_by_snapshot_path(csv_dir: Path) -> dict[str, str]:
    return {
        f"data/{path.name}": path.read_text(encoding="utf-8")
        for path in sorted(csv_dir.glob("*_8h_funding.csv"))
    }


def _db_with_relative_snapshot_source_paths(
    tmp_path: Path,
    *,
    snapshot_provenance_data_dir: bool = False,
) -> tuple[Path, Path]:
    """Create a tmp DB whose sidecar records ``data/*.csv`` source paths.

    The real CSV files live outside ``db_path.parent / "data"``. Future verifier
    code must therefore use explicit or committed provenance source resolution
    and must not be able to pass by accident through DB-relative source files.
    """
    db_path = _build_funding_db(tmp_path, _funding_rows_complete())
    _add_latest_equity_snapshot(db_path)
    csv_dir = _tmp_csv_complete(tmp_path).resolve()

    payload = build_funding_source_snapshot_payload_v1(
        source_rows=_source_rows_from_csv_dir(csv_dir),
        source_file_contents_by_path=_source_file_contents_by_snapshot_path(csv_dir),
        source_file_paths=None,
        required_windows=_required_windows(),
        generated_at_utc=_GENERATED_AT,
        lane_id="paper_pnl_v1",
        output_dir=str(db_path.parent),
        writer_or_verifier_command="local synthetic source path resolution test",
        qnty_git_commit=_GIT_SHA,
        write_state="committed",
        db_identity_hash_before="local-synthetic-before",
        pending_batch_id="pending-local-synthetic",
        ledger_batch_id="1",
        batch_identity_matches=True,
        evaluation_identity_matches=True,
        db_path_reference=str(db_path),
        batch_start_watermark=None,
        batch_end_watermark="2026-06-15T08:00:00",
        sanitized_host_user_label="local-test",
    )
    if snapshot_provenance_data_dir:
        payload["provenance"]["source_path_resolution"] = {
            "mode": "snapshot_provenance",
            "resolved_funding_source_dir": str(csv_dir),
        }
    envelope = build_funding_source_snapshot_envelope_v1(payload)
    snapshot_path = _write_snapshot(db_path, envelope)
    _set_latest_batch_snapshot_reference(db_path, snapshot_path, envelope)

    assert not (db_path.parent / "data").exists()
    return db_path, csv_dir


def _db_dir_entries(db_path: Path) -> set[str]:
    return {path.name for path in db_path.parent.iterdir()}


def _assert_no_db_side_effects(
    db_path: Path,
    *,
    before_sha256: str,
    before_entries: set[str],
) -> None:
    assert sha256_file(db_path) == before_sha256
    created = _db_dir_entries(db_path) - before_entries
    assert not any(name.endswith("-wal") or name.endswith("-shm") for name in created)


def _assert_read_only_json_contract(report: dict[str, Any], db_path: Path) -> None:
    missing = _REQUIRED_READ_ONLY_JSON_FIELDS - set(report)
    assert missing == set()
    assert report["read_only"] is True
    assert report["db_path"] == str(db_path)
    assert report["db_mutation_performed"] is False
    assert report["query_only_pragma_enabled"] is True
    assert report["wal_shm_files_created"] is False


def _all_reason_codes(report: dict[str, Any]) -> set[str]:
    codes: set[str] = set()
    for key in ("funding_clean_carry_reason_codes",):
        raw = report.get(key)
        if isinstance(raw, list):
            codes.update(str(item) for item in raw)

    for section_name in ("funding_clean_carry", "funding_source_snapshot"):
        section = report.get(section_name)
        if not isinstance(section, dict):
            continue
        for key in ("reason_codes", "future_clean_mode_reason_codes"):
            raw = section.get(key)
            if isinstance(raw, list):
                codes.update(str(item) for item in raw)
    return codes


def _assert_source_path_unavailable_without_misleading_codes(
    report: dict[str, Any],
) -> None:
    reason_codes = _all_reason_codes(report)
    assert _SOURCE_PATH_UNAVAILABLE in reason_codes
    assert reason_codes.isdisjoint(_MISLEADING_SOURCE_REASON_CODES)


@pytest.mark.xfail(strict=True, reason=_XFAIL_REASON)
def test_absolute_data_dir_makes_cli_cwd_independent(tmp_path: Path) -> None:
    db_path, data_dir = _db_with_relative_snapshot_source_paths(tmp_path)
    arbitrary_cwd = tmp_path / "arbitrary_cwd"
    arbitrary_cwd.mkdir()
    before_sha256 = sha256_file(db_path)
    before_entries = _db_dir_entries(db_path)

    repo_proc, repo_report = _run_cli_json(
        "--db-path",
        str(db_path),
        "--read-only",
        "--json",
        "--data-dir",
        str(data_dir),
        cwd=_REPO_ROOT,
    )
    arbitrary_proc, arbitrary_report = _run_cli_json(
        "--db-path",
        str(db_path),
        "--read-only",
        "--json",
        "--data-dir",
        str(data_dir),
        cwd=arbitrary_cwd,
    )

    assert repo_proc.returncode == 0, repo_proc.stderr
    assert arbitrary_proc.returncode == 0, arbitrary_proc.stderr
    assert repo_report == arbitrary_report
    _assert_read_only_json_contract(repo_report, db_path)
    assert repo_report["resolved_funding_source_dir"] == str(data_dir)
    assert repo_report["source_path_resolution_mode"] == "explicit_data_dir"
    _assert_no_db_side_effects(
        db_path,
        before_sha256=before_sha256,
        before_entries=before_entries,
    )


@pytest.mark.xfail(strict=True, reason=_XFAIL_REASON)
def test_relative_data_dir_is_rejected(tmp_path: Path) -> None:
    db_path, _data_dir = _db_with_relative_snapshot_source_paths(tmp_path)
    before_sha256 = sha256_file(db_path)
    before_entries = _db_dir_entries(db_path)

    proc = _run_cli(
        "--db-path",
        str(db_path),
        "--read-only",
        "--json",
        "--data-dir",
        "data",
        cwd=_REPO_ROOT,
    )

    assert proc.returncode != 0
    assert "absolute" in (proc.stderr + proc.stdout).lower()
    _assert_no_db_side_effects(
        db_path,
        before_sha256=before_sha256,
        before_entries=before_entries,
    )


@pytest.mark.xfail(strict=True, reason=_XFAIL_REASON)
def test_missing_data_dir_fails_closed_even_when_cwd_has_data(
    tmp_path: Path,
) -> None:
    db_path, data_dir = _db_with_relative_snapshot_source_paths(tmp_path)
    fallback_cwd = tmp_path / "cwd_with_data"
    fallback_cwd.mkdir()
    shutil.copytree(data_dir, fallback_cwd / "data")
    before_sha256 = sha256_file(db_path)
    before_entries = _db_dir_entries(db_path)

    proc, report = _run_cli_json(
        "--db-path",
        str(db_path),
        "--read-only",
        "--json",
        cwd=fallback_cwd,
    )

    assert proc.returncode != 0
    assert report["resolved_funding_source_dir"] is None
    assert report["source_path_resolution_mode"] == "unavailable"
    _assert_source_path_unavailable_without_misleading_codes(report)
    _assert_no_db_side_effects(
        db_path,
        before_sha256=before_sha256,
        before_entries=before_entries,
    )


@pytest.mark.xfail(strict=True, reason=_XFAIL_REASON)
def test_unavailable_absolute_data_dir_fails_closed_without_digest_codes(
    tmp_path: Path,
) -> None:
    db_path, _data_dir = _db_with_relative_snapshot_source_paths(tmp_path)
    missing_data_dir = (tmp_path / "missing_data").resolve()
    before_sha256 = sha256_file(db_path)
    before_entries = _db_dir_entries(db_path)

    proc, report = _run_cli_json(
        "--db-path",
        str(db_path),
        "--read-only",
        "--json",
        "--data-dir",
        str(missing_data_dir),
        cwd=_REPO_ROOT,
    )

    assert proc.returncode != 0
    assert report["resolved_funding_source_dir"] == str(missing_data_dir)
    assert report["source_path_resolution_mode"] == "explicit_data_dir"
    _assert_source_path_unavailable_without_misleading_codes(report)
    _assert_no_db_side_effects(
        db_path,
        before_sha256=before_sha256,
        before_entries=before_entries,
    )


@pytest.mark.xfail(strict=True, reason=_XFAIL_REASON)
def test_snapshot_provenance_source_path_is_used_when_data_dir_absent(
    tmp_path: Path,
) -> None:
    db_path, data_dir = _db_with_relative_snapshot_source_paths(
        tmp_path,
        snapshot_provenance_data_dir=True,
    )
    arbitrary_cwd = tmp_path / "provenance_cwd"
    arbitrary_cwd.mkdir()
    before_sha256 = sha256_file(db_path)
    before_entries = _db_dir_entries(db_path)

    proc, report = _run_cli_json(
        "--db-path",
        str(db_path),
        "--read-only",
        "--json",
        cwd=arbitrary_cwd,
    )

    assert proc.returncode == 0, proc.stderr
    _assert_read_only_json_contract(report, db_path)
    assert report["resolved_funding_source_dir"] == str(data_dir)
    assert report["source_path_resolution_mode"] == "snapshot_provenance"
    _assert_no_db_side_effects(
        db_path,
        before_sha256=before_sha256,
        before_entries=before_entries,
    )
