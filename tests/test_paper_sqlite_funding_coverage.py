"""Tests for the SQLite verifier funding-coverage stamp.

Five tests, mirroring docs/plans/FUNDING_COVERAGE_FAIL_CLOSED_GATE_PLAN.md §6:

  1. test_sqlite_complete_funding_is_clean_net_of_carry — every funding row is
     backed by a source CSV row.
  2. test_sqlite_missing_sol_funding_is_caveated_engine_semantics — BTC backed,
     SOL rows have rate_available=0 / funding_amount=0.0 and the source SOL CSV
     is empty.
  3. test_sqlite_partial_per_symbol_gap_is_detected — BTC complete, SOL partial.
  4. test_sqlite_arithmetic_status_unchanged_by_coverage_block — pins the
     additive invariant: even when coverage says CAVEATED, the existing
     arithmetic ``status`` stays STATUS_OK.
  5. test_jsonl_path_still_works — regression smoke for the legacy JSONL
     ``check_funding_coverage`` entry point after the refactor.

Legacy JSONL path tests live in ``tests/test_funding_coverage.py``.
Runner pre-batch abort tests are follow-on (out of scope here).

All tests use ``tmp_path`` only — no repo output, no ``/srv/qnty``, no VM
paths. The funding rows are inserted with raw ``sqlite3`` so we can control
the per-row shape exactly, mirroring the ``_inject_trade`` helper in
``tests/test_paper_sqlite_verify.py``.
"""

from __future__ import annotations

import json
import hashlib
import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

# Ensure repo root is on sys.path so the package import works without install.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from quantbot.paper import PAPER_ENGINE_VERSION
from quantbot.paper.config import build_config, config_hash, write_config_once
from quantbot.paper.db import _TRIGGER_SQL, initialize_database
from quantbot.paper.funding_coverage import (
    check_funding_coverage,
)
from quantbot.paper.funding_status import (
    CAVEATED_ENGINE_SEMANTICS,
    CAVEATED_ENGINE_SEMANTICS_LABEL,
    CLEAN_NET_OF_CARRY,
    COVERAGE_COMPLETE,
    COVERAGE_MISSING,
    COVERAGE_PARTIAL,
)
from quantbot.paper.sqlite_verify import (
    STATUS_OK,
    verify_database,
)

FIXTURES = Path(__file__).parent / "fixtures"

# ---------------------------------------------------------------------------
# CSV helpers (mirrors tests/test_funding_coverage.py)
# ---------------------------------------------------------------------------

def _copy_btc_csv(dst: Path) -> None:
    """Copy the BTC funding CSV fixture to ``dst`` (creates parent dirs)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURES / "data" / "BTCUSDT_8h_funding.csv", dst)


def _write_sol_csv(dst: Path, content_lines: list[str]) -> None:
    """Write a SOL funding CSV at ``dst`` with the given (header + rows) lines."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text("\n".join(content_lines) + "\n", encoding="utf-8")


def _tmp_csv_with_sol(tmp_path: Path, sol_lines: list[str]) -> Path:
    """tmp_path/csv dir with the BTC fixture (2 rows) + a synthetic SOL CSV.

    The BTC fixture's ``fundingTime`` rows are 2026-06-14T08:00:00 and
    2026-06-14T16:00:00 UTC. We deliberately use a fresh SOL CSV per test so
    the SOL windows line up with the per-test funding rows.
    """
    d = tmp_path / "csv"
    d.mkdir()
    _copy_btc_csv(d / "BTCUSDT_8h_funding.csv")
    _write_sol_csv(d / "SOLUSDT_8h_funding.csv", sol_lines)
    return d


def _tmp_csv_complete(tmp_path: Path) -> Path:
    return _tmp_csv_with_sol(tmp_path, _sol_csv_full())


def _tmp_csv_sol_header_only(tmp_path: Path) -> Path:
    return _tmp_csv_with_sol(tmp_path, _sol_csv_header_only())


def _tmp_csv_sol_one_row(tmp_path: Path) -> Path:
    return _tmp_csv_with_sol(tmp_path, _sol_csv_one_row())


# ---------------------------------------------------------------------------
# DB builder: a fresh SQLite DB with raw funding rows + matching signal snapshots
# ---------------------------------------------------------------------------

def _build_funding_db(tmp_path: Path, funding_rows: list[dict]) -> Path:
    """Build a fresh SQLite DB carrying the given funding rows + matching events.

    Each ``funding_rows`` entry must include: ``funding_id``, ``symbol``,
    ``bar_ts``, ``window_start``, ``window_end``, ``notional_usd``,
    ``funding_rate``, ``funding_events``, ``rate_available`` (0/1),
    ``funding_amount``. The DB is initialised with the standard schema (incl.
    all append-only triggers), then the triggers are dropped so we can insert
    raw ``funding`` + ``signal_snapshots`` + ``ledger_events`` rows directly
    (mirroring ``_inject_trade`` in ``tests/test_paper_sqlite_verify.py``).
    The signal_snapshot rows are inserted so the cross-row ``bar_commit_id``
    agreement check passes; their ``bar_commit_id`` matches the funding row's
    ``bar_commit_id`` for that bar.
    """
    db_path = tmp_path / "paper" / "paper_ledger.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    config = build_config(
        forward_start_ts="2026-06-14T00:00:00",
        initial_equity_usd=10000.0,
        notional_usd=1000.0,
        fee_bps=5.0,
        slippage_bps=5.0,
        max_bar_staleness_hours=72.0,
    )
    write_config_once(config, output_dir=db_path.parent)
    initialize_database(db_path, config)

    conn = sqlite3.connect(str(db_path))
    try:
        # Drop append-only triggers so we can write raw rows.
        for (name,) in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'"
        ).fetchall():
            conn.execute(f"DROP TRIGGER IF EXISTS {name}")

        # Distinct bar_ts values for signal_snapshot insertion (one snapshot per
        # bar; multiple funding rows can share the same bar_ts/snapshot).
        unique_bars = sorted({row["bar_ts"] for row in funding_rows})
        n_snapshots = len(unique_bars)
        n_funding = len(funding_rows)
        n_events = n_snapshots + n_funding
        cur = conn.execute(
            "INSERT INTO ledger_batches (created_at, committed_at, event_count, "
            "committed_bar_count, paper_engine_version, config_hash) "
            "VALUES ('2026-06-14T00:00:00', '2026-06-14T00:00:00', ?, 0, ?, ?)",
            (
                n_events,
                PAPER_ENGINE_VERSION,
                config_hash(config),
            ),
        )
        batch_id = cur.lastrowid

        prev_seq: int | None = None
        first_seq: int | None = None
        last_seq: int | None = None

        def bar_ts_to_commit_id(bar_ts: str) -> str:
            return hashlib.sha256(bar_ts.encode()).hexdigest()[:16]

        # Pass 1: insert one signal_snapshot event + typed row per unique bar_ts.
        for bar_ts in unique_bars:
            snapshot_id = bar_ts_to_commit_id(bar_ts)
            source_digest = "0" * 64

            cur = conn.execute(
                "INSERT INTO ledger_events (batch_id, event_type, event_key, "
                "recorded_at, bar_ts, symbol, prev_seq) VALUES "
                "(?, 'signal_snapshot', ?, '2026-06-14T00:00:00', ?, NULL, ?)",
                (batch_id, snapshot_id, bar_ts, prev_seq),
            )
            snapshot_event_seq = cur.lastrowid
            if first_seq is None:
                first_seq = snapshot_event_seq
            prev_seq = snapshot_event_seq

            conn.execute(
                "INSERT INTO signal_snapshots (seq, batch_id, snapshot_id, bar_ts, "
                "bar_commit_id, bar_index, active_symbols, portfolio_heat, "
                "heat_cap_triggered, weighted_return, source_observation_digest, "
                "source_observation_mtime, run_ts) VALUES "
                "(?, ?, ?, ?, ?, 0, '[]', 0.0, 0, 0.0, ?, "
                "'2026-06-14T00:00:00', '2026-06-14T00:00:00')",
                (
                    snapshot_event_seq,
                    batch_id,
                    snapshot_id,
                    bar_ts,
                    snapshot_id,
                    source_digest,
                ),
            )

        # Pass 2: insert one funding event + typed row per funding row.
        for row in funding_rows:
            bar_ts = row["bar_ts"]
            funding_id = row["funding_id"]
            symbol = row["symbol"]
            bar_commit_id = bar_ts_to_commit_id(bar_ts)

            cur = conn.execute(
                "INSERT INTO ledger_events (batch_id, event_type, event_key, "
                "recorded_at, bar_ts, symbol, prev_seq) VALUES "
                "(?, 'funding', ?, '2026-06-14T00:00:00', ?, ?, ?)",
                (batch_id, funding_id, bar_ts, symbol, prev_seq),
            )
            funding_event_seq = cur.lastrowid
            prev_seq = funding_event_seq
            last_seq = funding_event_seq

            conn.execute(
                "INSERT INTO funding (seq, batch_id, funding_id, bar_commit_id, "
                "symbol, bar_ts, window_start, window_end, notional_usd, "
                "funding_rate, funding_events, rate_available, funding_amount) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    funding_event_seq,
                    batch_id,
                    funding_id,
                    bar_commit_id,
                    symbol,
                    bar_ts,
                    row["window_start"],
                    row["window_end"],
                    row["notional_usd"],
                    row["funding_rate"],
                    row["funding_events"],
                    row["rate_available"],
                    row["funding_amount"],
                ),
            )

        # Update batch first/last seq (event_count already set above).
        conn.execute(
            "UPDATE ledger_batches SET first_event_seq = ?, last_event_seq = ? "
            "WHERE batch_id = ?",
            (first_seq, last_seq, batch_id),
        )

        # Restore append-only triggers so structural validation passes.
        conn.executescript(_TRIGGER_SQL)
        conn.commit()
    finally:
        conn.close()

    return db_path


def _publish_csvs(db_path: Path, csv_dir: Path) -> None:
    """Copy a tmp CSV dir to ``<db_path.parent>/data`` so the verifier sees it."""
    target_data = db_path.parent / "data"
    if target_data.exists():
        shutil.rmtree(target_data)
    shutil.copytree(csv_dir, target_data)


# ---------------------------------------------------------------------------
# Funding-row builders + matching CSVs
#
# Each test owns its own CSV set so the windows align by construction:
#   - BTC + SOL share the SAME bar_ts grid (so the BTC fixture can be reused
#     by every test via ``_copy_btc_csv``).
#   - We write small synthetic SOL CSVs under tmp_path/csv/.
# ---------------------------------------------------------------------------

_NOTIONAL = 1000.0
_RATE = 0.0001

# Bar grid mirrors tests/fixtures/data/BTCUSDT_8h_funding.csv:
#   BTC fixture rows are at 2026-06-14T08:00:00 and 2026-06-14T16:00:00 UTC.
# SOL uses the synthetic CSVs we write per test (see _sol_csv_*).
_BTC_TS_A = "2026-06-14T08:00:00"
_BTC_TS_B = "2026-06-14T16:00:00"
_BTC_WIN_A = ("2026-06-14T00:00:00", _BTC_TS_A)
_BTC_WIN_B = (_BTC_TS_A, _BTC_TS_B)

_SOL_TS_A = "2026-06-15T00:00:00"
_SOL_TS_B = "2026-06-15T08:00:00"
_SOL_TS_C = "2026-06-15T16:00:00"
_SOL_WIN_A = (_BTC_TS_B, _SOL_TS_A)
_SOL_WIN_B = (_SOL_TS_A, _SOL_TS_B)
_SOL_WIN_C = (_SOL_TS_B, _SOL_TS_C)

# fundingTime (ms) for SOL windows (the right endpoint):
_FT_A = 1781481600000  # 2026-06-15T00:00:00 UTC (backs _SOL_WIN_A)
_FT_B = 1781510400000  # 2026-06-15T08:00:00 UTC (backs _SOL_WIN_B)
_FT_C = 1781539200000  # 2026-06-15T16:00:00 UTC (would back _SOL_WIN_C if present)


def _row(symbol: str, bar_ts: str, win: tuple[str, str], *, rate_available: int = 1) -> dict:
    return {
        "funding_id": f"{symbol}|{bar_ts}",
        "symbol": symbol,
        "bar_ts": bar_ts,
        "window_start": win[0],
        "window_end": win[1],
        "notional_usd": _NOTIONAL,
        "funding_rate": _RATE if rate_available else 0.0,
        "funding_events": 1 if rate_available else 0,
        "rate_available": rate_available,
        "funding_amount": _NOTIONAL * _RATE if rate_available else 0.0,
    }


def _btc(bar_ts: str, win: tuple[str, str], *, rate_available: int = 1) -> dict:
    return _row("BTCUSDT", bar_ts, win, rate_available=rate_available)


def _sol(bar_ts: str, win: tuple[str, str], *, rate_available: int = 1) -> dict:
    return _row("SOLUSDT", bar_ts, win, rate_available=rate_available)


def _funding_rows_complete() -> list[dict]:
    """2 BTC + 2 SOL rows; every window backed by its symbol CSV."""
    return [
        _btc(_BTC_TS_A, _BTC_WIN_A),
        _btc(_BTC_TS_B, _BTC_WIN_B),
        _sol(_SOL_TS_A, _SOL_WIN_A),
        _sol(_SOL_TS_B, _SOL_WIN_B),
    ]


def _funding_rows_missing_sol() -> list[dict]:
    """2 BTC rows backed; 2 SOL rows with rate_available=0 / amount=0.0 and an
    empty SOL CSV. Arithmetic check still passes (rate_available=0 with
    funding_amount=0.0 is the documented engine semantics); coverage collapses
    SOL to MISSING."""
    return [
        _btc(_BTC_TS_A, _BTC_WIN_A),
        _btc(_BTC_TS_B, _BTC_WIN_B),
        _sol(_SOL_TS_A, _SOL_WIN_A, rate_available=0),
        _sol(_SOL_TS_B, _SOL_WIN_B, rate_available=0),
    ]


def _funding_rows_partial_sol() -> list[dict]:
    """2 BTC rows backed; 3 SOL rows where only 1 of 3 windows has a CSV row."""
    return [
        _btc(_BTC_TS_A, _BTC_WIN_A),
        _btc(_BTC_TS_B, _BTC_WIN_B),
        _sol(_SOL_TS_A, _SOL_WIN_A),
        _sol(_SOL_TS_B, _SOL_WIN_B),
        _sol(_SOL_TS_C, _SOL_WIN_C),
    ]


def _sol_csv_full() -> list[str]:
    """SOL CSV that fully backs windows A and B."""
    return [
        "fundingTime,fundingRate,markPrice",
        f"{_FT_A},0.0001,150.0",
        f"{_FT_B},0.0001,151.0",
    ]


def _sol_csv_header_only() -> list[str]:
    """Empty SOL CSV (header only)."""
    return ["fundingTime,fundingRate,markPrice"]


def _sol_csv_one_row() -> list[str]:
    """SOL CSV with one row backing only window A."""
    return [
        "fundingTime,fundingRate,markPrice",
        f"{_FT_A},0.0001,150.0",
    ]


# ---------------------------------------------------------------------------
# Test 1: complete funding -> CLEAN_NET_OF_CARRY
# ---------------------------------------------------------------------------

def test_sqlite_complete_funding_is_clean_net_of_carry(tmp_path):
    """Every funding row is backed by a source CSV row.

    The arithmetic check passes (rate_available=1, funding_amount=notional*rate),
    the coverage check classifies every symbol as COMPLETE, and the verifier
    stamps CLEAN_NET_OF_CARRY with an empty diagnostic label.
    """
    csv_dir = _tmp_csv_complete(tmp_path)
    db_path = _build_funding_db(tmp_path, _funding_rows_complete())
    _publish_csvs(db_path, csv_dir)

    result = verify_database(db_path)
    assert result.status == STATUS_OK, result.failures
    assert result.report["funding_coverage_verdict"] == CLEAN_NET_OF_CARRY
    assert result.report["funding_coverage_diagnostic_label"] == ""
    assert result.report["funding_coverage"]["decision"] == COVERAGE_COMPLETE
    assert result.report["funding_coverage"]["per_symbol"] == {
        "BTCUSDT": COVERAGE_COMPLETE,
        "SOLUSDT": COVERAGE_COMPLETE,
    }


# ---------------------------------------------------------------------------
# Test 2: missing SOL -> CAVEATED_ENGINE_SEMANTICS
# ---------------------------------------------------------------------------

def test_sqlite_missing_sol_funding_is_caveated_engine_semantics(tmp_path):
    """BTC backed, SOL rate_available=0 with funding_amount=0.0; SOL CSV empty.

    The existing arithmetic check still passes (rate_available=0 with
    funding_amount=0.0 is the documented engine semantics), but the coverage
    stamp collapses to CAVEATED_ENGINE_SEMANTICS with the documented label.
    CLEAN_NET_OF_CARRY must NOT be reachable.
    """
    csv_dir = _tmp_csv_sol_header_only(tmp_path)
    db_path = _build_funding_db(tmp_path, _funding_rows_missing_sol())
    _publish_csvs(db_path, csv_dir)

    result = verify_database(db_path)
    assert result.status == STATUS_OK, result.failures
    assert result.report["funding_coverage_verdict"] == CAVEATED_ENGINE_SEMANTICS
    assert (
        result.report["funding_coverage_diagnostic_label"]
        == CAVEATED_ENGINE_SEMANTICS_LABEL
    )
    assert result.report["funding_coverage"]["per_symbol"]["SOLUSDT"] == COVERAGE_MISSING
    assert result.report["funding_coverage"]["decision"] == COVERAGE_MISSING
    assert result.report["funding_coverage_verdict"] != CLEAN_NET_OF_CARRY


# ---------------------------------------------------------------------------
# Test 3: partial SOL -> CAVEATED_ENGINE_SEMANTICS
# ---------------------------------------------------------------------------

def test_sqlite_partial_per_symbol_gap_is_detected(tmp_path):
    """BTC complete, SOL partial (1 of 3 windows backed by CSV).

    Coverage decision = partial; verdict = CAVEATED_ENGINE_SEMANTICS; SOL
    per-symbol decision = "partial".
    """
    csv_dir = _tmp_csv_sol_one_row(tmp_path)
    db_path = _build_funding_db(tmp_path, _funding_rows_partial_sol())
    _publish_csvs(db_path, csv_dir)

    result = verify_database(db_path)
    assert result.status == STATUS_OK, result.failures
    assert result.report["funding_coverage"]["per_symbol"]["SOLUSDT"] == COVERAGE_PARTIAL
    assert result.report["funding_coverage"]["decision"] == COVERAGE_PARTIAL
    assert result.report["funding_coverage_verdict"] == CAVEATED_ENGINE_SEMANTICS
    assert (
        result.report["funding_coverage_diagnostic_label"]
        == CAVEATED_ENGINE_SEMANTICS_LABEL
    )


# ---------------------------------------------------------------------------
# Test 4: arithmetic status is unchanged by the coverage block (additive gate)
# ---------------------------------------------------------------------------

def test_sqlite_arithmetic_status_unchanged_by_coverage_block(tmp_path):
    """Reuse the missing-SOL fixture; even when coverage says CAVEATED, the
    existing arithmetic ``status`` is still STATUS_OK.

    This pins the additive invariant: the coverage stamp must NOT demote a
    clean arithmetic run to FAIL.
    """
    csv_dir = _tmp_csv_sol_header_only(tmp_path)
    db_path = _build_funding_db(tmp_path, _funding_rows_missing_sol())
    _publish_csvs(db_path, csv_dir)

    result = verify_database(db_path)
    # Arithmetic status stays OK; the stamp is purely additive.
    assert result.status == STATUS_OK, result.failures
    assert result.report["funding_coverage_verdict"] == CAVEATED_ENGINE_SEMANTICS
    # And the explicit non-demotion invariant.
    assert result.status != "FAIL"
    assert result.status != "CORRUPT"


# ---------------------------------------------------------------------------
# Test 5: legacy JSONL path still works (regression smoke after the refactor)
# ---------------------------------------------------------------------------

def test_jsonl_path_still_works(tmp_path):
    """Smoke that the JSONL ``check_funding_coverage`` (not the new
    ``check_funding_coverage_from_rows``) still works after the refactor.

    This is the regression guard requested in the task spec.
    """
    csv_dir = _tmp_csv_complete(tmp_path)
    report = check_funding_coverage(
        FIXTURES / "funding_coverage_complete.jsonl",
        csv_dir,
    )
    assert report.overall_decision == COVERAGE_COMPLETE
    assert report.per_symbol == {
        "BTCUSDT": COVERAGE_COMPLETE,
        "SOLUSDT": COVERAGE_COMPLETE,
    }
    assert report.total_funding_rows == 4
    assert report.total_rate_available_zero == 0
    assert report.missing_windows == []