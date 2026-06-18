"""Tests for the funding-coverage fail-closed gate (quantbot.paper.funding_coverage).

Legacy JSONL verifier path tests — the SQLite verifier path lives in
``tests/test_paper_sqlite_funding_coverage.py``. Runner pre-batch abort tests are
follow-on (out of scope here).

Six tests, per docs/plans/FUNDING_COVERAGE_FAIL_CLOSED_GATE_PLAN.md §5:

  1. test_complete_funding_is_clean_net_of_carry — every window is backed by source CSV.
  2. test_missing_sol_funding_is_caveated_engine_semantics — every SOL window missing.
  3. test_partial_per_symbol_gap_is_detected — BTC complete, SOL partial.
  4. test_verifier_rate_available_zero_marks_not_clean — complete fixture with one
     dropped CSV row exposes a gap without changing rate_available in the ledger.
  5. test_missing_funding_cannot_reach_clean_net_of_carry (regression) — through the
     real verifier: a snapshot with missing source coverage yields a CAVEATED verdict
     and the documented diagnostic label.
  6. test_label_roundtrip — pins the contract surface (constants from funding_status).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from quantbot.paper.funding_coverage import (
    check_funding_coverage,
)
from quantbot.paper.funding_status import (
    CAVEATED_ENGINE_SEMANTICS,
    CAVEATED_ENGINE_SEMANTICS_LABEL,
    CAVEATED_EX_FUNDING,
    CAVEATED_EX_FUNDING_LABEL,
    CLEAN_NET_OF_CARRY,
    COVERAGE_COMPLETE,
    COVERAGE_MISSING,
    COVERAGE_NOT_REQUIRED,
    COVERAGE_PARTIAL,
    FAIL,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _copy_btc_csv(dst: Path) -> None:
    """Copy the BTC funding CSV fixture to ``dst`` (creates parent dirs)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURES / "data" / "BTCUSDT_8h_funding.csv", dst)


def _write_sol_csv(dst: Path, content_lines: list[str]) -> None:
    """Write a SOL funding CSV at ``dst`` with the given (header + rows) lines."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text("\n".join(content_lines) + "\n", encoding="utf-8")


# ----- helper: a fresh tmp CSV dir that satisfies the COMPLETE fixture ------------

def _tmp_csv_complete(tmp_path: Path) -> Path:
    """tmp_path/csv dir with BTC (2 rows) + SOL (2 rows) — full coverage."""
    d = tmp_path / "csv"
    d.mkdir()
    _copy_btc_csv(d / "BTCUSDT_8h_funding.csv")
    _write_sol_csv(
        d / "SOLUSDT_8h_funding.csv",
        [
            "fundingTime,fundingRate,markPrice",
            "1781481600000,0.0001,150.0",  # 2026-06-15T00:00:00 UTC
            "1781510400000,0.0001,151.0",  # 2026-06-15T08:00:00 UTC
        ],
    )
    return d


def _tmp_csv_sol_header_only(tmp_path: Path) -> Path:
    """tmp_path/csv dir with BTC (2 rows) + SOL (header only)."""
    d = tmp_path / "csv"
    d.mkdir()
    _copy_btc_csv(d / "BTCUSDT_8h_funding.csv")
    _write_sol_csv(d / "SOLUSDT_8h_funding.csv", ["fundingTime,fundingRate,markPrice"])
    return d


def _tmp_csv_sol_one_row(tmp_path: Path) -> Path:
    """tmp_path/csv dir with BTC (2 rows) + SOL (header + 1 row at 2026-06-14T16:00:00)."""
    d = tmp_path / "csv"
    d.mkdir()
    _copy_btc_csv(d / "BTCUSDT_8h_funding.csv")
    _write_sol_csv(
        d / "SOLUSDT_8h_funding.csv",
        [
            "fundingTime,fundingRate,markPrice",
            "1781452800000,0.0001,150.0",  # 2026-06-14T16:00:00 UTC — backs SOL window (08:00, 16:00]
        ],
    )
    return d


# ============================================================ test 1

def test_complete_funding_is_clean_net_of_carry(tmp_path):
    """All required funding intervals backed by source CSVs → overall_decision = complete.

    Drives the CLEAN_NET_OF_CARRY verdict path (architect §4.2).
    """
    csv_dir = _tmp_csv_complete(tmp_path)
    report = check_funding_coverage(
        FIXTURES / "funding_coverage_complete.jsonl", csv_dir
    )
    assert report.overall_decision == COVERAGE_COMPLETE
    assert report.per_symbol == {"BTCUSDT": COVERAGE_COMPLETE, "SOLUSDT": COVERAGE_COMPLETE}
    assert report.total_funding_rows == 4
    assert report.total_rate_available_zero == 0
    assert report.total_required_intervals == 4
    assert report.missing_windows == []


# ============================================================ test 2

def test_missing_sol_funding_is_caveated_engine_semantics(tmp_path):
    """SOL has rate_available=0 for every window → SOL = MISSING.

    Drives the CAVEATED_ENGINE_SEMANTICS path with the documented diagnostic label.
    """
    csv_dir = _tmp_csv_sol_header_only(tmp_path)
    report = check_funding_coverage(
        FIXTURES / "funding_coverage_missing_sol.jsonl", csv_dir
    )
    assert report.per_symbol == {"BTCUSDT": COVERAGE_COMPLETE, "SOLUSDT": COVERAGE_MISSING}
    # Overall follows the worst symbol: any MISSING → MISSING.
    assert report.overall_decision == COVERAGE_MISSING
    assert report.total_funding_rows == 4
    assert report.total_rate_available_zero == 2
    assert len(report.missing_windows) == 2
    assert {m.symbol for m in report.missing_windows} == {"SOLUSDT"}
    # The gate module does NOT compute the verdict itself; that's the verifier's job.
    # But test 5 exercises the verifier integration.


# ============================================================ test 3

def test_partial_per_symbol_gap_is_detected(tmp_path):
    """SOL has 3 windows backed by 1 CSV row → SOL = PARTIAL.

    Drives the CAVEATED_ENGINE_SEMANTICS path for a partial per-symbol gap.
    """
    csv_dir = _tmp_csv_sol_one_row(tmp_path)
    report = check_funding_coverage(
        FIXTURES / "funding_coverage_partial_sol.jsonl", csv_dir
    )
    assert report.per_symbol == {"BTCUSDT": COVERAGE_COMPLETE, "SOLUSDT": COVERAGE_PARTIAL}
    assert report.overall_decision == COVERAGE_PARTIAL
    assert report.total_funding_rows == 5
    assert len(report.missing_windows) == 2
    assert {m.symbol for m in report.missing_windows} == {"SOLUSDT"}


# ============================================================ test 4

def test_verifier_rate_available_zero_marks_not_clean(tmp_path):
    """Complete ledger + one dropped SOL CSV row exposes a gap without changing rate_available.

    Asserts that ``missing_windows`` is non-empty when the source CSV fails to back a
    window whose ledger row had ``rate_available=1``. ``total_rate_available_zero``
    must reflect the count from the JSONL ledger (0 here, since the complete fixture
    is fully ``rate_available=1``).
    """
    csv_dir = _tmp_csv_sol_one_row(tmp_path)
    report = check_funding_coverage(
        FIXTURES / "funding_coverage_complete.jsonl", csv_dir
    )
    assert report.missing_windows, "expected a missing window when a SOL CSV row is dropped"
    assert {m.symbol for m in report.missing_windows} == {"SOLUSDT"}
    assert report.total_rate_available_zero == 0  # complete ledger: all rate_available=1


# ============================================================ test 5 (regression via verify)

def test_missing_funding_cannot_reach_clean_net_of_carry(tmp_path):
    """Through the real verifier: a snapshot whose AAA funding has no source CSV must
    never reach CLEAN_NET_OF_CARRY — it must be stamped CAVEATED_ENGINE_SEMANTICS with
    the documented diagnostic label.

    Uses the existing _clean_run helper from tests/test_paper_verify.py to create a
    complete frozen snapshot, then bootstraps the trusted baseline so the verifier can
    reach STATUS_OK (the gate only emits CAVEATED_* labels when status is OK).
    """
    # Lazy import to avoid hard dependency on the heavyweight paper test fixtures
    # at module-collection time.
    from tests.test_paper_verify import _clean_run  # noqa: WPS433 (test-local import)

    out = _clean_run(tmp_path)
    # AAA has rate_available=1 in the JSONL (because _funding_df() supplies AAA rates),
    # but no AAA funding CSV exists in the repo data dir or anywhere — so AAA
    # coverage = MISSING → verdict = CAVEATED_ENGINE_SEMANTICS. The gate emits the
    # CAVEATED label ONLY when status == STATUS_OK, so we must bootstrap the trusted
    # baseline explicitly here.
    from quantbot.paper.verify import verify

    report = verify(out, bootstrap=True)
    assert report["status"] == "OK", report.get("failures", [])
    assert report["funding_coverage_verdict"] != CLEAN_NET_OF_CARRY
    assert report["funding_coverage_verdict"] == CAVEATED_ENGINE_SEMANTICS
    assert (
        report["funding_coverage_diagnostic_label"] == CAVEATED_ENGINE_SEMANTICS_LABEL
    )
    # The decision must be one of the documented coverage values (AAA has no CSV so MISSING).
    assert report["funding_coverage"]["decision"] in {
        COVERAGE_PARTIAL,
        COVERAGE_MISSING,
    }
    # The diagnostic label is empty when CLEAN, so its presence here is itself the assertion.
    assert report["funding_coverage_diagnostic_label"] != ""
    assert CLEAN_NET_OF_CARRY not in report["funding_coverage_verdict"]


# ============================================================ test 6 (contract pin)

@pytest.mark.parametrize(
    ("symbol", "expected"),
    [
        (CLEAN_NET_OF_CARRY, "CLEAN_NET_OF_CARRY"),
        (CAVEATED_ENGINE_SEMANTICS, "CAVEATED_ENGINE_SEMANTICS"),
        (CAVEATED_EX_FUNDING, "CAVEATED_EX_FUNDING"),
        (FAIL, "FAIL"),
        (
            CAVEATED_ENGINE_SEMANTICS_LABEL,
            "missing_funding_treated_as_zero_like_current_engine_not_net_of_carry_clean",
        ),
        (
            CAVEATED_EX_FUNDING_LABEL,
            "funding_excluded_not_net_of_carry_comparable",
        ),
        (COVERAGE_COMPLETE, "complete"),
        (COVERAGE_PARTIAL, "partial"),
        (COVERAGE_MISSING, "missing"),
        (COVERAGE_NOT_REQUIRED, "not_required"),
    ],
)
def test_label_roundtrip(symbol: str, expected: str) -> None:
    """Pin the literal contract surface — the verifier, tests, and receipt all import
    these symbols by name and the literal strings are part of the public contract.
    """
    assert symbol == expected
