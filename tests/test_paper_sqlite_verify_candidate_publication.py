"""Tests for the candidate publication path of the SQLite verifier.

QNTY_PROD_FULL_WINDOW_REPORT_PROMOTION_SCHEMA_RECONCILIATION_IMPLEMENTATION.

The official published report is assembled by ``verify_and_publish`` ->
``_build_published_report`` (the authoritative 42-key envelope). The read-only
diagnostic CLI emits a different, narrower diagnostics shape. A clean full-window
``CLEAN_NET_OF_CARRY`` was reachable only via the read-only path (with explicit
``--data-dir``), so it could not be expressed in the publication schema.

``verify_and_publish_candidate`` closes that gap safely: it reuses the SAME
authoritative envelope builder, honors an explicit ``data_dir`` for full-window
clean-carry, writes ONLY a candidate json to a vetted NON-PROD path, and never
publishes/overwrites the prod report/receipt/log. These tests pin exactly those
properties. No prod artifact, DB, CSV, snapshot, or bundle is touched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from quantbot.paper.sqlite_verify import (
    LOG_FILE,
    OFFICIAL_PROD_REPORT_PATH,
    PROD_LANE_DIR,
    RECEIPT_FILE,
    REPORT_FILE,
    STATUS_OK,
    CandidateOutputRefused,
    assert_candidate_report_schema,
    assert_safe_candidate_output_path,
    compare_published_report_schema,
    verify_and_publish,
    verify_and_publish_candidate,
)
from quantbot.paper.funding_status import CLEAN_NET_OF_CARRY

# Reuse the CLEAN-reaching full-window fixtures from the clean-carry gate module.
from tests.test_paper_sqlite_verifier_clean_net_of_carry_gate import (  # noqa: E402
    _add_latest_equity_snapshot,
    _committed_snapshot,
    _db_with_complete_source,
    _set_latest_batch_snapshot_reference,
    _write_snapshot,
)


def _clean_carry_db(tmp_path: Path) -> Path:
    """Build a STATUS_OK DB whose full-window gate reaches CLEAN_NET_OF_CARRY."""
    db_path = _db_with_complete_source(tmp_path)
    _add_latest_equity_snapshot(db_path)
    envelope = _committed_snapshot(db_path)
    snapshot_path = _write_snapshot(db_path, envelope)
    _set_latest_batch_snapshot_reference(db_path, snapshot_path, envelope)
    return db_path


# --------------------------------------------------------------------------
# Envelope reuse + schema equality
# --------------------------------------------------------------------------

def test_candidate_uses_authoritative_published_envelope(tmp_path: Path) -> None:
    """The candidate report carries the authoritative envelope markers that only
    ``_build_published_report`` stamps (verifier/authoritative/snapshot_identity),
    i.e. it went through the published-report builder, not the diagnostic path."""
    db_path = _db_with_complete_source(tmp_path)
    out = tmp_path / "cand" / "candidate_report.json"

    result, out_path = verify_and_publish_candidate(db_path, out)

    assert result.status == STATUS_OK, result.failures
    on_disk = json.loads(Path(out_path).read_text())
    assert on_disk["verifier"] == "sqlite"
    assert on_disk["authoritative"] is True
    assert "snapshot_identity" in on_disk
    assert "content_digests" in on_disk
    assert on_disk["exit_code"] == 0


def test_candidate_top_level_keys_equal_reference_published_report(
    tmp_path: Path,
) -> None:
    db_path = _db_with_complete_source(tmp_path)

    reference = verify_and_publish(db_path, tmp_path / "pub").report
    _, out_path = verify_and_publish_candidate(
        db_path, tmp_path / "cand" / "candidate_report.json"
    )
    candidate = json.loads(Path(out_path).read_text())

    comparison = compare_published_report_schema(candidate, reference)
    assert comparison.ok, (comparison.missing_keys, comparison.extra_keys)
    # And the helper's assert form does not raise.
    assert_candidate_report_schema(candidate, reference)
    assert set(candidate.keys()) == set(reference.keys())


def test_schema_gate_detects_missing_and_extra_keys() -> None:
    reference = {"a": 1, "b": 2, "c": 3}
    candidate = {"a": 1, "d": 9}  # missing b,c ; extra d

    comparison = compare_published_report_schema(candidate, reference)
    assert not comparison.ok
    assert comparison.missing_keys == frozenset({"b", "c"})
    assert comparison.extra_keys == frozenset({"d"})

    with pytest.raises(CandidateOutputRefused):
        assert_candidate_report_schema(candidate, reference)

    # Whitelisting the differences makes it pass (explicit migration scenario).
    assert_candidate_report_schema(
        candidate,
        reference,
        allow_missing=frozenset({"b", "c"}),
        allow_extra=frozenset({"d"}),
    )


# --------------------------------------------------------------------------
# --data-dir reaches source-path-available mode
# --------------------------------------------------------------------------

def test_explicit_data_dir_reaches_source_path_available(tmp_path: Path) -> None:
    db_path = _db_with_complete_source(tmp_path)
    data_dir = db_path.parent / "data"
    assert data_dir.is_dir()

    result, out_path = verify_and_publish_candidate(
        db_path,
        tmp_path / "cand" / "candidate_report.json",
        data_dir=data_dir,
    )

    report = json.loads(Path(out_path).read_text())
    assert report["source_path_available"] is True
    assert report["source_path_resolution_mode"] == "explicit_data_dir"
    assert result.status == STATUS_OK, result.failures


# --------------------------------------------------------------------------
# Anti-footgun path guards
# --------------------------------------------------------------------------

def test_refuses_official_prod_report_path() -> None:
    with pytest.raises(CandidateOutputRefused, match="official prod report path"):
        assert_safe_candidate_output_path(OFFICIAL_PROD_REPORT_PATH)


def test_refuses_prod_lane_output_unless_allowed(tmp_path: Path) -> None:
    inside_prod = PROD_LANE_DIR / "some_candidate.json"
    with pytest.raises(CandidateOutputRefused, match="prod lane"):
        assert_safe_candidate_output_path(inside_prod)
    # Explicit opt-in is accepted (parent already exists in prod; guard is the
    # containment check, not the exact-official-path check).
    allowed = assert_safe_candidate_output_path(inside_prod, allow_prod_lane=True)
    assert allowed == inside_prod
    # ...but the exact official report path is refused even with the opt-in.
    with pytest.raises(CandidateOutputRefused, match="official prod report path"):
        assert_safe_candidate_output_path(
            OFFICIAL_PROD_REPORT_PATH, allow_prod_lane=True
        )


def test_refuses_relative_and_empty_paths() -> None:
    with pytest.raises(CandidateOutputRefused):
        assert_safe_candidate_output_path("relative/candidate.json")
    with pytest.raises(CandidateOutputRefused):
        assert_safe_candidate_output_path("")


def test_refuses_nonexistent_parent_outside_tmp() -> None:
    with pytest.raises(CandidateOutputRefused, match="not under /tmp"):
        assert_safe_candidate_output_path("/srv/does-not-exist-xyz/candidate.json")


def test_creates_parent_only_under_tmp() -> None:
    target = Path("/tmp/qnty_candidate_pub_test_dir/nested/candidate_report.json")
    # Clean any prior run.
    if target.parent.exists():
        for child in sorted(target.parent.rglob("*"), reverse=True):
            child.unlink() if child.is_file() else child.rmdir()
    resolved = assert_safe_candidate_output_path(target)
    assert resolved.parent.is_dir()
    # Cleanup.
    for child in sorted(target.parent.parent.rglob("*"), reverse=True):
        child.unlink() if child.is_file() else child.rmdir()
    target.parent.parent.rmdir()


# --------------------------------------------------------------------------
# Read-only candidate mode does not publish / mutate the authoritative report
# --------------------------------------------------------------------------

def test_candidate_mode_does_not_publish_prod_artifacts(tmp_path: Path) -> None:
    db_path = _db_with_complete_source(tmp_path)
    out = tmp_path / "cand" / "candidate_report.json"

    verify_and_publish_candidate(db_path, out)

    # Only the candidate json exists; no authoritative report/receipt/log was
    # written next to the DB (that is verify_and_publish's job, not this path's).
    db_dir = db_path.parent
    assert not (db_dir / REPORT_FILE).exists()
    assert not (db_dir / RECEIPT_FILE).exists()
    assert not (db_dir / LOG_FILE).exists()
    assert out.exists()


# --------------------------------------------------------------------------
# Full-window clean-carry semantics preserved under candidate publication
# --------------------------------------------------------------------------

def test_full_window_clean_carry_remains_clean_in_candidate_mode(
    tmp_path: Path,
) -> None:
    db_path = _clean_carry_db(tmp_path)
    out = tmp_path / "cand" / "candidate_report.json"

    result, out_path = verify_and_publish_candidate(db_path, out)

    assert result.status == STATUS_OK, result.failures
    report = json.loads(Path(out_path).read_text())
    assert report["funding_clean_carry_decision"] == CLEAN_NET_OF_CARRY
    assert report["funding_coverage_verdict"] == CLEAN_NET_OF_CARRY
    assert report["funding_clean_carry_reason_codes"] == []


# --------------------------------------------------------------------------
# Regression: verify_and_publish behavior unchanged
# --------------------------------------------------------------------------

def test_verify_and_publish_still_publishes_prod_artifacts(tmp_path: Path) -> None:
    db_path = _db_with_complete_source(tmp_path)
    out_dir = tmp_path / "pub"

    result = verify_and_publish(db_path, out_dir)

    assert result.status == STATUS_OK, result.failures
    assert (out_dir / REPORT_FILE).exists()
    assert (out_dir / RECEIPT_FILE).exists()
    assert (out_dir / LOG_FILE).exists()
    published = json.loads((out_dir / REPORT_FILE).read_text())
    assert published["authoritative"] is True
