"""Read-only SQLite verifier CLI/API contract.

This file specifies AND verifies an explicit, safe, read-only CLI surface for
``python -m quantbot.paper.sqlite_verify``. It exists because a prior
read-only prod DB-linked snapshot acceptance audit
(``docs/plans/QNTY_READ_ONLY_PROD_DB_LINKED_SNAPSHOT_ACCEPTANCE_AUDIT.md``)
found that ``sqlite_verify --help`` produced no useful DB-path/read-only
contract, so the strict verifier had to be skipped for that audit.

``python -m quantbot.paper.sqlite_verify`` now has an argparse entry point
(``main`` in ``quantbot/paper/sqlite_verify.py``) implementing the CLI surface
below.

Required CLI surface:
  --db-path <absolute path>   required; no implicit prod path in CLI mode
  --read-only                 opens via file:<abs>?mode=ro&immutable=1 (or
                               equivalent) and sets PRAGMA query_only=ON
  --json                      emit a single JSON report to stdout

Required JSON report fields (existing verifier fields, additive):
  status
  funding_clean_carry_decision
  funding_clean_carry_status
  funding_clean_carry_reason_codes
  funding_source_snapshot_status
  funding_source_snapshot

Required JSON read-only markers (this contract):
  read_only               bool, true when --read-only was used
  db_path                 str, absolute path echoed back
  db_mutation_performed   bool, must be false
  query_only_pragma_enabled  bool, must be true under --read-only
  wal_shm_files_created   bool, must be false

Required safety properties, independent of JSON fields:
  - relative --db-path is rejected (nonzero exit)
  - --db-path is required in CLI mode (nonzero exit without it)
  - no DB file is created/modified/deleted
  - no -wal / -shm sibling files are created
  - no schema-ensure helpers run (a DB missing tables is reported, not fixed)
  - no writer runs (no paper_verify_report.json / receipt / log side effect —
    that is verify_and_publish's job, not this CLI)

This file never touches /srv, never runs the prod/shadow writer, never
mutates forward_obs, and only ever opens tmp SQLite DBs created by the
existing test fixtures in this suite.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

from quantbot.core.determinism import sha256_file
from quantbot.paper.funding_status import (
    CAVEATED_ENGINE_SEMANTICS,
    CLEAN_NET_OF_CARRY,
)
from quantbot.paper.sqlite_verify import (
    FUNDING_CLEAN_CARRY_STATUS_CLEAN,
    FUNDING_CLEAN_CARRY_STATUS_REFUSED_DIGEST_MISMATCH,
    FUNDING_CLEAN_CARRY_STATUS_REFUSED_MISSING_SNAPSHOT,
    FUNDING_CLEAN_CARRY_STATUS_REFUSED_PENDING_OR_ORPHANED,
    STATUS_OK,
)
from tests.test_paper_sqlite_verifier_clean_net_of_carry_gate import (
    _committed_snapshot,
    _db_with_complete_source,
)
from tests.test_paper_sqlite_verifier_db_linked_snapshot_selector import (
    _attach_snapshot,
    _db_ready_for_db_linked_clean,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "quantbot.paper.sqlite_verify", *args],
        cwd=str(cwd or _REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )


def _side_car_files(db_path: Path) -> set[str]:
    return {p.name for p in db_path.parent.iterdir()}


def _run_cli_json(db_path: Path, *extra_args: str) -> dict[str, Any]:
    proc = _run_cli(
        "--db-path", str(db_path), "--read-only", "--json", *extra_args
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_help_exits_zero_and_documents_required_flags() -> None:
    proc = _run_cli("--help")

    assert proc.returncode == 0
    assert "--db-path" in proc.stdout
    assert "--read-only" in proc.stdout
    assert "--json" in proc.stdout


def test_db_path_required_for_cli_verification() -> None:
    proc = _run_cli("--read-only", "--json")

    assert proc.returncode != 0
    assert "--db-path" in (proc.stderr + proc.stdout)


def test_relative_db_path_is_rejected(tmp_path: Path) -> None:
    db_path = _db_with_complete_source(tmp_path)
    relative = db_path.relative_to(_REPO_ROOT) if db_path.is_relative_to(
        _REPO_ROOT
    ) else Path("relative_only.db")

    proc = _run_cli(
        "--db-path", str(relative), "--read-only", "--json", cwd=_REPO_ROOT
    )

    assert proc.returncode != 0
    assert "absolute" in (proc.stderr + proc.stdout).lower()


def test_cli_does_not_create_modify_or_delete_db_file(tmp_path: Path) -> None:
    db_path = _db_ready_for_db_linked_clean(tmp_path)
    before_sha = sha256_file(db_path)
    before_mtime = db_path.stat().st_mtime_ns

    report = _run_cli_json(db_path)

    after_sha = sha256_file(db_path)
    after_mtime = db_path.stat().st_mtime_ns

    assert before_sha == after_sha
    assert before_mtime == after_mtime
    assert report["db_mutation_performed"] is False


def test_cli_does_not_create_wal_or_shm_files(tmp_path: Path) -> None:
    db_path = _db_ready_for_db_linked_clean(tmp_path)
    before = _side_car_files(db_path)

    report = _run_cli_json(db_path)

    after = _side_car_files(db_path)
    created = after - before
    wal_shm_created = any(
        name.endswith("-wal") or name.endswith("-shm") for name in created
    )

    assert wal_shm_created is False
    assert report["wal_shm_files_created"] is False


def test_cli_read_only_sets_query_only_pragma(tmp_path: Path) -> None:
    db_path = _db_ready_for_db_linked_clean(tmp_path)

    report = _run_cli_json(db_path)

    assert report["read_only"] is True
    assert report["query_only_pragma_enabled"] is True
    assert report["db_path"] == str(db_path)


def test_cli_does_not_run_schema_ensure_helpers(tmp_path: Path) -> None:
    """A DB with no tables at all must be reported, not silently fixed up."""
    db_path = tmp_path / "empty.db"
    conn = sqlite3.connect(str(db_path))
    conn.close()
    before_size = db_path.stat().st_size

    proc = _run_cli("--db-path", str(db_path), "--read-only", "--json")
    report = json.loads(proc.stdout)

    after_size = db_path.stat().st_size
    conn = sqlite3.connect(str(db_path))
    try:
        table_count = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0]
    finally:
        conn.close()

    assert table_count == 0
    assert after_size == before_size
    assert report["status"] != STATUS_OK


def test_cli_does_not_run_writers_or_publish_side_cars(tmp_path: Path) -> None:
    db_path = _db_ready_for_db_linked_clean(tmp_path)
    before = _side_car_files(db_path)

    _run_cli_json(db_path)

    after = _side_car_files(db_path)
    created = after - before
    forbidden = {
        "paper_verify_report.json",
        "paper_verify_receipt.md",
        "paper_verify_log.jsonl",
    }

    assert created.isdisjoint(forbidden)


def test_json_report_contains_required_verifier_fields(tmp_path: Path) -> None:
    db_path = _db_ready_for_db_linked_clean(tmp_path)
    envelope = _committed_snapshot(db_path)
    _attach_snapshot(db_path, envelope)

    report = _run_cli_json(db_path)

    for field in (
        "status",
        "funding_clean_carry_decision",
        "funding_clean_carry_status",
        "funding_clean_carry_reason_codes",
        "funding_source_snapshot_status",
        "funding_source_snapshot",
        "read_only",
        "db_path",
        "db_mutation_performed",
    ):
        assert field in report, f"missing required field: {field}"


def test_valid_committed_snapshot_returns_clean_net_of_carry_via_cli(
    tmp_path: Path,
) -> None:
    db_path = _db_ready_for_db_linked_clean(tmp_path)
    envelope = _committed_snapshot(db_path)
    _attach_snapshot(db_path, envelope)

    report = _run_cli_json(db_path)

    assert report["status"] == STATUS_OK
    assert report["funding_clean_carry_status"] == FUNDING_CLEAN_CARRY_STATUS_CLEAN
    assert report["funding_clean_carry_decision"] == CLEAN_NET_OF_CARRY
    assert report["funding_clean_carry_reason_codes"] == []


def test_missing_snapshot_returns_caveated_refused_via_cli(tmp_path: Path) -> None:
    db_path = _db_ready_for_db_linked_clean(tmp_path)

    report = _run_cli_json(db_path)

    assert report["funding_clean_carry_decision"] == CAVEATED_ENGINE_SEMANTICS
    assert report["funding_clean_carry_status"] == (
        FUNDING_CLEAN_CARRY_STATUS_REFUSED_MISSING_SNAPSHOT
    )
    assert "funding_source_snapshot_missing" in report["funding_clean_carry_reason_codes"]


def test_pending_snapshot_returns_caveated_refused_via_cli(tmp_path: Path) -> None:
    db_path = _db_ready_for_db_linked_clean(tmp_path)
    envelope = _committed_snapshot(db_path, write_state="pending")
    _attach_snapshot(db_path, envelope)

    report = _run_cli_json(db_path)

    assert report["funding_clean_carry_decision"] == CAVEATED_ENGINE_SEMANTICS
    assert report["funding_clean_carry_status"] == (
        FUNDING_CLEAN_CARRY_STATUS_REFUSED_PENDING_OR_ORPHANED
    )


def test_mismatched_db_file_sha_returns_caveated_refused_via_cli(
    tmp_path: Path,
) -> None:
    db_path = _db_ready_for_db_linked_clean(tmp_path)
    envelope = _committed_snapshot(db_path)
    _attach_snapshot(db_path, envelope, funding_source_snapshot_sha256="0" * 64)

    report = _run_cli_json(db_path)

    assert report["funding_clean_carry_decision"] == CAVEATED_ENGINE_SEMANTICS
    assert report["funding_clean_carry_status"] == (
        FUNDING_CLEAN_CARRY_STATUS_REFUSED_DIGEST_MISMATCH
    )
