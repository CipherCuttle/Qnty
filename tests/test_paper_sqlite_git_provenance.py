"""Tests for evidence-grade git-SHA provenance on SQLite paper batches.

Two halves:

WRITER (production path: run_sqlite_accounting):
  1. A new committed batch records the current repo HEAD git SHA.
  2. The writer NEVER commits a batch with git_sha=None: if the SHA cannot be
     resolved it fails closed (STATUS_ABORTED) before any ledger mutation.

VERIFIER / REPORT (read-only operator-facing output):
  3. Historical batches with git_sha=None stay readable and OK, reported as
     unprovenanced/caveated evidence (NOT corruption).
  4. The published report exposes the latest batch git_sha.
  5. The published report + receipt expose a missing-git_sha count and a loud
     warning when provenance is missing.
  6. Regression lock: the published (operator-facing) report carries
     funding_coverage_verdict — the field the deployed VM report was missing
     even though the in-memory VerifyResult had it.

All tests use tmp_path only — no repo output, no /srv/qnty, no production DB.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from quantbot.paper.db import connect_readonly
from quantbot.paper.funding_status import CLEAN_NET_OF_CARRY
from quantbot.paper.provenance import resolve_git_sha
from quantbot.paper.sqlite_verify import (
    RECEIPT_FILE,
    REPORT_FILE,
    STATUS_OK,
    verify_and_publish,
    verify_database,
)
from quantbot.paper.sqlite_writer import STATUS_ABORTED, STATUS_OK as WRITER_OK

# Reuse the production-path writer harness and the funding-DB builder verbatim.
from tests.test_paper_sqlite_writer_funding_coverage import (
    FWD_HELD,
    TS,
    NOW,
    SYMBOL,
    _funding_df_complete,
    _init_test_db,
    _make_obs,
    _run,
    _write_observation_log,
)
from tests.test_paper_sqlite_funding_coverage import (
    _build_funding_db,
    _funding_rows_complete,
    _publish_csvs,
    _tmp_csv_complete,
)

_FULL_SHA_RE = re.compile(r"\A[0-9a-f]{40}\Z")


@pytest.fixture(autouse=True)
def _freeze_writer_now(monkeypatch):
    """Pin the writer's clock so the freshness gate is deterministic.

    (The autouse fixture in the imported harness module does NOT apply here.)
    """
    monkeypatch.setattr("quantbot.paper.sqlite_writer._now", lambda: NOW)


def _latest_batch_git_sha(db_path: Path):
    conn = connect_readonly(db_path)
    try:
        return conn.execute(
            "SELECT git_sha FROM ledger_batches ORDER BY batch_id DESC LIMIT 1"
        ).fetchone()[0]
    finally:
        conn.close()


def _batch_count(db_path: Path) -> int:
    conn = connect_readonly(db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM ledger_batches").fetchone()[0]
    finally:
        conn.close()


# =========================================================================
# WRITER
# =========================================================================

def test_writer_records_current_git_sha(tmp_path: Path):
    """A committed batch carries the resolved repo HEAD SHA (full 40-hex)."""
    db_path = _init_test_db(tmp_path, FWD_HELD)
    obs = [_make_obs(ts, [SYMBOL], i) for i, ts in enumerate(TS)]
    obs_dir = _write_observation_log(tmp_path, obs)

    status, msg = _run(db_path, obs_dir, _funding_df_complete(), FWD_HELD)
    assert status == WRITER_OK, f"expected OK, got {status}: {msg}"

    sha = _latest_batch_git_sha(db_path)
    assert sha is not None, "committed batch must carry a git_sha"
    assert _FULL_SHA_RE.match(sha), f"git_sha must be full 40-hex, got {sha!r}"
    # It must be the actual repo HEAD, not a placeholder.
    assert sha == resolve_git_sha()


def test_writer_aborts_when_git_sha_unresolved(tmp_path: Path, monkeypatch):
    """If git SHA cannot be resolved, the writer fails closed with NO mutation.

    No silent git_sha=None batch is ever committed.
    """
    monkeypatch.setattr(
        "quantbot.paper.sqlite_writer.resolve_git_sha", lambda: None
    )
    db_path = _init_test_db(tmp_path, FWD_HELD)
    obs = [_make_obs(ts, [SYMBOL], i) for i, ts in enumerate(TS)]
    obs_dir = _write_observation_log(tmp_path, obs)

    status, msg = _run(db_path, obs_dir, _funding_df_complete(), FWD_HELD)

    assert status == STATUS_ABORTED, f"expected ABORTED, got {status}: {msg}"
    assert "GIT_SHA_UNRESOLVED" in msg, msg
    # Fail-closed: no batch row written, watermark not advanced.
    assert _batch_count(db_path) == 0
    conn = connect_readonly(db_path)
    try:
        wm = conn.execute(
            "SELECT watermark_bar_ts FROM ledger_state WHERE id = 1"
        ).fetchone()[0]
    finally:
        conn.close()
    assert wm is None, f"watermark must not advance on git-sha abort, got {wm!r}"


# =========================================================================
# VERIFIER / REPORT
# =========================================================================

def test_verifier_caveats_historical_null_git_sha(tmp_path: Path):
    """A pre-provenance batch (git_sha=NULL) stays readable + OK, reported as
    unprovenanced historical evidence — never CORRUPT."""
    db_path = _build_funding_db(tmp_path, _funding_rows_complete())
    _publish_csvs(db_path, _tmp_csv_complete(tmp_path))

    result = verify_database(db_path)
    assert result.status == STATUS_OK, result.failures  # NOT flipped to CORRUPT

    gp = result.report["git_provenance"]
    assert gp["latest_batch_git_sha"] is None
    assert gp["latest_batch_git_sha_missing"] is True
    assert gp["any_batch_missing_git_sha"] is True
    assert gp["batches_missing_git_sha"] >= 1
    assert result.report["git_provenance_warning"]  # loud, non-empty

    # The unprovenanced row is still readable.
    conn = connect_readonly(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM ledger_batches").fetchone()[0] >= 1
    finally:
        conn.close()


def test_published_report_exposes_latest_batch_git_sha(tmp_path: Path):
    """A writer-built batch -> the published JSON exposes the real latest SHA and
    no missing-provenance warning."""
    db_path = _init_test_db(tmp_path, FWD_HELD)
    obs = [_make_obs(ts, [SYMBOL], i) for i, ts in enumerate(TS)]
    obs_dir = _write_observation_log(tmp_path, obs)
    status, msg = _run(db_path, obs_dir, _funding_df_complete(), FWD_HELD)
    assert status == WRITER_OK, msg

    verify_and_publish(db_path)
    report = json.loads((db_path.parent / REPORT_FILE).read_text())

    gp = report["git_provenance"]
    assert _FULL_SHA_RE.match(gp["latest_batch_git_sha"])
    assert gp["latest_batch_git_sha"] == resolve_git_sha()
    assert gp["latest_batch_git_sha_missing"] is False
    assert gp["any_batch_missing_git_sha"] is False
    assert gp["batches_missing_git_sha"] == 0
    assert report["git_provenance_warning"] is None


def test_published_report_and_receipt_warn_on_missing_git_sha(tmp_path: Path):
    """A NULL-provenance batch -> the published JSON exposes the missing count and
    a warning, and the receipt renders a Git provenance section with the warning."""
    db_path = _build_funding_db(tmp_path, _funding_rows_complete())
    _publish_csvs(db_path, _tmp_csv_complete(tmp_path))

    verify_and_publish(db_path)
    report = json.loads((db_path.parent / REPORT_FILE).read_text())
    receipt = (db_path.parent / RECEIPT_FILE).read_text()

    assert report["git_provenance"]["batches_missing_git_sha"] >= 1
    assert report["git_provenance"]["latest_batch_git_sha_missing"] is True
    warning = report["git_provenance_warning"]
    assert warning and "UNPROVENANCED_LATEST_BATCH" in warning

    assert "## Git provenance" in receipt
    assert "Latest batch git_sha: (missing)" in receipt
    assert "UNPROVENANCED_LATEST_BATCH" in receipt


def test_published_report_contains_funding_coverage_verdict(tmp_path: Path):
    """Regression lock for the VM gap: the operator-facing PUBLISHED report (not
    just the in-memory VerifyResult) must carry funding_coverage_verdict."""
    db_path = _build_funding_db(tmp_path, _funding_rows_complete())
    _publish_csvs(db_path, _tmp_csv_complete(tmp_path))

    verify_and_publish(db_path)
    report = json.loads((db_path.parent / REPORT_FILE).read_text())

    assert "funding_coverage_verdict" in report
    assert report["funding_coverage_verdict"] == CLEAN_NET_OF_CARRY
    assert "funding_coverage" in report
