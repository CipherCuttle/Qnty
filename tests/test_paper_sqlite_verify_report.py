"""Tests for the authoritative SQLite verifier PUBLICATION layer (verify_and_publish).

Authority model (ADR 0001): the committed ``paper_ledger.db`` and the accounting writer's
returned status code are RAW accounting artifacts / a runner status only. The single
authoritative paper status is the latest ``paper_verify_report.json``, written ONLY by the
read-only verifier. A paper run is trusted IFF that report's ``status == OK``.

These exercise the adversarial cases that the multi-file JSONL TOCTOU loop kept losing, now on
the single-file DB + dedicated read-only publisher:

  1. corrupt ledger                       => verifier report CORRUPT
  2. malformed state                      => verifier report CORRUPT
  3. forged runner OK (sidecar) ignored   => verifier derives status from the DB, not the sidecar
  4. modified trade after the writer      => verifier report CORRUPT
  5. clean writer output                  => verifier report OK (+ artifacts published)
  6. verifier OK then DB mutated          => the NEXT verification flips the report to CORRUPT
  7. stale/incompatible config            => verifier report CONFIG_ERROR (never OK)

The DB is only ever read (read-only / query-only); the publisher writes ONLY its own
paper_verify_* artifacts next to the DB.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from quantbot.paper.sqlite_verify import (
    LOG_FILE,
    RECEIPT_FILE,
    REPORT_FILE,
    STATUS_CONFIG_ERROR,
    STATUS_CORRUPT,
    STATUS_OK,
    STATUS_PRE_START,
    verify_and_publish,
    verify_database,
)

# Reuse the committed-DB fixtures + corruption helpers from the core verifier test module.
from tests.test_paper_sqlite_verify import (  # noqa: E402
    NOW,
    _clean_db,
    _init_db,
    _mutate,
    _scalar,
    _trade_db,
)


@pytest.fixture(autouse=True)
def _freeze_writer_now(monkeypatch):
    """Pin the writer's freshness clock so the in-process writer fixtures are deterministic."""
    monkeypatch.setattr("quantbot.paper.sqlite_writer._now", lambda: NOW)


def _report_on_disk(out: Path) -> dict:
    return json.loads((out / REPORT_FILE).read_text())


# --------------------------------------------------------------------------- clean OK


def test_clean_db_publishes_ok(tmp_path: Path):
    db_path = _clean_db(tmp_path)
    out = db_path.parent
    result = verify_and_publish(db_path)
    assert result.status == STATUS_OK, result.failures
    # The authoritative artifacts were published.
    assert (out / REPORT_FILE).exists()
    assert (out / RECEIPT_FILE).exists()
    assert (out / LOG_FILE).exists()
    report = _report_on_disk(out)
    assert report["status"] == STATUS_OK
    assert report["authoritative"] is True
    assert report["trusted"] is True
    assert report["verifier"] == "sqlite"
    # Content digests are recorded ("output digests").
    assert report["content_sha256"]
    assert report["content_digests"]["ledger_events"]
    assert report["snapshot_identity"]["content_sha256"] == report["content_sha256"]
    assert "exact validated SQLite read snapshot" in report["snapshot_identity"]["meaning"]
    # The receipt states the authority model.
    receipt = (out / RECEIPT_FILE).read_text()
    assert "AUTHORITATIVE" in receipt
    assert "trusted **iff**" in receipt
    # The audit log got exactly one row.
    log_lines = [l for l in (out / LOG_FILE).read_text().splitlines() if l.strip()]
    assert len(log_lines) == 1
    assert json.loads(log_lines[0])["status"] == STATUS_OK


# --------------------------------------------------------------------------- (1) corrupt ledger


def test_corrupt_ledger_publishes_corrupt(tmp_path: Path):
    db_path = _clean_db(tmp_path)
    out = db_path.parent
    seq = _scalar(db_path, "SELECT seq FROM equity_snapshots ORDER BY seq DESC LIMIT 1")
    _mutate(db_path, "UPDATE equity_snapshots SET equity = equity + 100 WHERE seq = ?", (seq,))
    result = verify_and_publish(db_path)
    assert result.status == STATUS_CORRUPT, result.failures
    report = _report_on_disk(out)
    assert report["status"] == STATUS_CORRUPT
    assert report["trusted"] is False
    assert report["failure_count"] >= 1


# --------------------------------------------------------------------------- (2) malformed state


def test_malformed_state_publishes_corrupt(tmp_path: Path):
    db_path = _clean_db(tmp_path)
    out = db_path.parent
    _mutate(db_path, "UPDATE ledger_state SET fees_cum = fees_cum + 123 WHERE id = 1")
    result = verify_and_publish(db_path)
    assert result.status == STATUS_CORRUPT, result.failures
    assert _report_on_disk(out)["trusted"] is False


# ----------------------------------------------- (3) forged runner OK sidecar is ignored


def test_forged_runner_ok_sidecar_is_ignored(tmp_path: Path):
    """A sidecar paper_pnl_summary.json claiming OK must NOT yield a verifier OK.

    The DB is a valid PRE_START (no committed eligible bars). The verifier derives status purely
    from the committed DB, so a runner/legacy convenience file claiming OK is ignored.
    """
    db_path = _init_db(tmp_path)  # empty -> PRE_START
    out = db_path.parent
    forged = {"status": "OK", "current_verdict": "stale OK", "realized_net_pnl": 9999.0}
    (out / "paper_pnl_summary.json").write_text(json.dumps(forged), encoding="utf-8")
    result = verify_and_publish(db_path)
    assert result.status == STATUS_PRE_START
    assert result.status != STATUS_OK
    report = _report_on_disk(out)
    assert report["status"] == STATUS_PRE_START
    assert report["trusted"] is False


# --------------------------------------------------------------------------- (4) modified trade


def test_modified_trade_after_writer_publishes_corrupt(tmp_path: Path):
    db_path = _trade_db(tmp_path)
    out = db_path.parent
    _mutate(db_path, "UPDATE trades SET net_pnl = net_pnl + 1234.5")
    result = verify_and_publish(db_path)
    assert result.status == STATUS_CORRUPT, result.failures
    assert _report_on_disk(out)["status"] == STATUS_CORRUPT


# ----------------------------------------------- (6) OK then mutate -> next verify CORRUPT


def test_ok_then_db_mutated_next_verify_is_corrupt(tmp_path: Path):
    db_path = _trade_db(tmp_path)
    out = db_path.parent
    first = verify_and_publish(db_path)
    assert first.status == STATUS_OK, first.failures
    ok_digest = _report_on_disk(out)["content_sha256"]

    # Mutate a committed row AFTER the OK. The next verification recomputes from the now-current
    # DB and fails closed; the published report flips to CORRUPT and the content digest changes.
    _mutate(db_path, "UPDATE trades SET net_pnl = net_pnl + 5.0")
    second = verify_and_publish(db_path)
    assert second.status == STATUS_CORRUPT, second.failures
    report = _report_on_disk(out)
    assert report["status"] == STATUS_CORRUPT
    assert report["trusted"] is False
    assert report["content_sha256"] != ok_digest


def test_mutation_during_digest_cannot_mix_verdict_and_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A concurrent commit cannot create an OK report with a digest from another DB state."""
    db_path = _trade_db(tmp_path)
    out = db_path.parent

    import quantbot.paper.sqlite_verify as sqlite_verify

    original = sqlite_verify._table_digest
    mutated = False

    def mutate_then_digest(conn: sqlite3.Connection, table: str) -> str:
        nonlocal mutated
        if not mutated:
            mutated = True
            _mutate(db_path, "UPDATE trades SET net_pnl = net_pnl + 5.0")
        return original(conn, table)

    monkeypatch.setattr(sqlite_verify, "_table_digest", mutate_then_digest)
    first = verify_and_publish(db_path)
    assert first.status == STATUS_OK, first.failures
    first_report = _report_on_disk(out)
    assert first_report["snapshot_identity"]["content_sha256"] == first_report["content_sha256"]

    monkeypatch.setattr(sqlite_verify, "_table_digest", original)
    second = verify_and_publish(db_path)
    second_report = _report_on_disk(out)
    assert second.status == STATUS_CORRUPT
    assert second_report["content_sha256"] != first_report["content_sha256"]


# --------------------------------------------------------------------------- (7) stale config


def test_stale_incompatible_config_publishes_config_error(tmp_path: Path):
    db_path = _clean_db(tmp_path)
    out = db_path.parent
    _mutate(db_path, "UPDATE paper_config SET paper_engine_version = '9.9.9' WHERE id = 1")
    result = verify_and_publish(db_path)
    assert result.status == STATUS_CONFIG_ERROR, result.failures
    report = _report_on_disk(out)
    assert report["status"] == STATUS_CONFIG_ERROR
    assert report["status"] != STATUS_OK
    assert report["trusted"] is False


def test_bad_config_hash_publishes_config_error(tmp_path: Path):
    db_path = _clean_db(tmp_path)
    out = db_path.parent
    _mutate(db_path, "UPDATE paper_config SET config_hash = 'deadbeef' WHERE id = 1")
    result = verify_and_publish(db_path)
    assert result.status == STATUS_CONFIG_ERROR, result.failures
    assert _report_on_disk(out)["trusted"] is False


# --------------------------------------------------------------------------- read-only guarantee


def test_publish_does_not_mutate_the_db(tmp_path: Path):
    db_path = _clean_db(tmp_path)
    before = db_path.read_bytes()
    verify_and_publish(db_path)
    # The committed DB file is untouched by the publisher (it only writes its own artifacts).
    assert db_path.read_bytes() == before


def test_pure_verify_database_writes_no_artifact(tmp_path: Path):
    db_path = _clean_db(tmp_path)
    out = db_path.parent
    verify_database(db_path)
    # The pure check publishes nothing — only verify_and_publish does.
    assert not (out / REPORT_FILE).exists()
    assert not (out / RECEIPT_FILE).exists()


def test_custom_output_dir_keeps_artifacts_off_the_db_dir(tmp_path: Path):
    db_path = _clean_db(tmp_path)
    sink = tmp_path / "verify_out"
    verify_and_publish(db_path, output_dir=sink)
    assert (sink / REPORT_FILE).exists()
    assert not (db_path.parent / REPORT_FILE).exists()


# --------------------------------------------------------------------------- log appends per run


def test_log_appends_one_row_per_verification(tmp_path: Path):
    db_path = _clean_db(tmp_path)
    out = db_path.parent
    verify_and_publish(db_path)
    verify_and_publish(db_path)
    verify_and_publish(db_path)
    log_lines = [l for l in (out / LOG_FILE).read_text().splitlines() if l.strip()]
    assert len(log_lines) == 3
    assert all(json.loads(l)["status"] == STATUS_OK for l in log_lines)
