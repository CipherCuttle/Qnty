"""Tests for the SQLite *writer* post-engine / pre-insert funding fail-closed gate.

This is the production-path counterpart of
``tests/test_paper_runner_funding_coverage.py`` (which covers the legacy JSONL
runner). Production is:

    qnty-paper-pnl.service
      -> ops/bin/qnty-paper-pnl-run.sh
      -> scripts/qnty-paper-sqlite-accounting.py
      -> quantbot.paper.sqlite_writer.run_sqlite_accounting
      -> /srv/qnty/output/paper_pnl_v1/paper_ledger.db

so the gate that actually protects the live SQLite ledger lives in
``quantbot.paper.sqlite_writer``. These tests drive ``run_sqlite_accounting``
end to end against a real tmp SQLite DB.

DESIGN: the gate runs AFTER ``run_engine`` (pure compute; no DB writes) and
BEFORE any insert / watermark advance. The engine is the single authority on
which windows actually REQUIRE funding — it only emits a funding row for a
genuinely-held, non-zero interval — so a ``result.funding`` row with
``rate_available == False`` is required-but-missing. The gate aborts on that and
rolls back, so nothing is written. A legitimate deferral (entry/zero-held bar)
emits no funding row and therefore never aborts (no over-fire).

Four tests:

  1. test_writer_aborts_when_required_funding_missing
     A held position crosses funding boundaries with an empty funding_df (the
     silent-skip load_all_funding produces for a missing CSV) -> the engine
     accrues funding rows with rate_available=False -> STATUS_ABORTED /
     FUNDING_COVERAGE_MISSING.
  2. test_writer_proceeds_when_required_funding_complete
     Same held position with complete funding_df -> writer commits (STATUS_OK),
     no funding abort.
  3. test_writer_no_sqlite_mutation_on_funding_abort
     After a funding abort: no batch / event / trade / equity / funding rows and
     the watermark is NOT advanced (still NULL).
  4. test_writer_does_not_overfire_on_deferred_entry_bar
     Regression for the over-fire the pre-engine gate caused: a first eligible
     entry bar with an EMPTY funding_df must NOT abort (zero held interval -> no
     funding row -> no required funding). This is the unit-level analogue of
     tests/test_paper_pnl_wrapper.py::TestEndToEndPreStart.

All tests use ``tmp_path`` only — no repo output, no ``/srv/qnty``, no VM paths,
no production DB.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from quantbot.data.types import Bar
from quantbot.paper.config import build_config, write_config_once
from quantbot.paper.db import connect_readonly, initialize_database
from quantbot.paper.sqlite_writer import (
    STATUS_ABORTED,
    STATUS_OK,
    run_sqlite_accounting,
)

# ---------------------------------------------------------------------------
# Deterministic 8h grid (mirrors tests/test_paper_sqlite_writer.py)
# ---------------------------------------------------------------------------
_GRID_BASE = datetime(2026, 6, 6, 16, 0, 0, tzinfo=timezone.utc)
TS = [
    (_GRID_BASE - timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%S")
    for h in [0, 8, 16, 24, 32, 40]
]
NOW = _GRID_BASE + timedelta(minutes=5)
SYMBOL = "AAAUSDT"
AAA_PRICES = [
    (100.0, 100.0),
    (100.0, 110.0),
    (120.0, 130.0),
    (140.0, 150.0),
    (160.0, 170.0),
    (180.0, 190.0),
]
# forward_start that yields a multi-bar HELD position (the engine accrues funding
# over its held intervals). Empirically TS[3] commits 4 bars / 3 funding rows.
FWD_HELD = TS[3]
# forward_start at the newest bar: a single entry bar that defers / accrues nothing.
FWD_ENTRY_ONLY = TS[0]


@pytest.fixture(autouse=True)
def _freeze_writer_now(monkeypatch):
    """Pin the writer's clock so the freshness gate is deterministic."""
    monkeypatch.setattr("quantbot.paper.sqlite_writer._now", lambda: NOW)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_bars(symbol: str = SYMBOL) -> list[Bar]:
    return [
        Bar(
            timestamp=ts,
            open=o,
            high=max(o, c),
            low=min(o, c),
            close=c,
            volume=1.0,
        )
        for ts, (o, c) in zip(TS, AAA_PRICES)
    ]


def _funding_df_complete(symbol: str = SYMBOL, rate: float = 0.0001) -> pd.DataFrame:
    """funding_df with one row per grid bar for ``symbol`` (covers every window)."""
    rows = [
        {
            "symbol": symbol,
            "dt": pd.Timestamp(ts, tz="UTC"),
            "fundingRate": rate,
            "abs_rate": abs(rate),
        }
        for ts in TS
    ]
    return pd.DataFrame(rows)


def _funding_df_missing_symbol() -> pd.DataFrame:
    """An empty funding_df — exactly what load_all_funding yields when the active
    symbol's CSV is absent (the silent-skip the gate must catch)."""
    return pd.DataFrame(columns=["symbol", "dt", "fundingRate", "abs_rate"])


def _write_observation_log(tmp_path: Path, per_bar_obs: list[dict]) -> Path:
    obs_dir = tmp_path / "forward_obs_v1"
    obs_dir.mkdir(parents=True, exist_ok=True)
    (obs_dir / "observation_log.json").write_text(
        json.dumps({"per_bar_obs": per_bar_obs}, indent=2), encoding="utf-8"
    )
    return obs_dir


def _make_obs(ts: str, active_symbols: list[str], bar_index: int = 0) -> dict:
    return {
        "timestamp": ts,
        "bar_index": bar_index,
        "active_symbols": active_symbols,
        "portfolio_heat": 0.0,
        "heat_cap_triggered": False,
        "weighted_return": 0.0,
    }


def _config(forward_start_ts: str):
    return build_config(
        forward_start_ts=forward_start_ts,
        initial_equity_usd=10000.0,
        notional_usd=1000.0,
        fee_bps=5.0,
        slippage_bps=5.0,
        max_bar_staleness_hours=72.0,
    )


def _init_test_db(tmp_path: Path, forward_start_ts: str) -> Path:
    db_path = tmp_path / "paper" / "paper_ledger.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    config = _config(forward_start_ts)
    write_config_once(config, output_dir=db_path.parent)
    initialize_database(db_path, config)
    return db_path


def _run(db_path: Path, obs_dir: Path, funding_df: pd.DataFrame, forward_start_ts: str):
    """Drive run_sqlite_accounting with patched loaders (bars present, funding as given).

    The patched load_config MUST match the DB-stored config identity, so it is
    built from the same forward_start_ts the DB was initialised with.
    """
    p_ohlcv = patch(
        "quantbot.paper.sqlite_writer.load_all_ohlcv",
        return_value={SYMBOL: _make_bars()},
    )
    p_funding = patch(
        "quantbot.paper.sqlite_writer.load_all_funding",
        return_value=funding_df,
    )
    p_config = patch(
        "quantbot.paper.sqlite_writer.load_config",
        return_value=_config(forward_start_ts),
    )
    with p_ohlcv, p_funding, p_config:
        return run_sqlite_accounting(db_path=db_path, forward_obs_dir=obs_dir)


def _assert_no_accounting_rows(db_path: Path) -> None:
    conn = connect_readonly(db_path)
    try:
        for table in ("ledger_batches", "ledger_events", "trades", "equity_snapshots", "funding"):
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            assert count == 0, f"{table} must be empty after funding abort, got {count}"
        watermark = conn.execute(
            "SELECT watermark_bar_ts FROM ledger_state WHERE id = 1"
        ).fetchone()[0]
        assert watermark is None, f"watermark must NOT advance on funding abort, got {watermark!r}"
    finally:
        conn.close()


# --------------------------------------------------------------------- test 1


def test_writer_aborts_when_required_funding_missing(tmp_path: Path):
    db_path = _init_test_db(tmp_path, FWD_HELD)
    obs = [_make_obs(ts, [SYMBOL], i) for i, ts in enumerate(TS)]
    obs_dir = _write_observation_log(tmp_path, obs)

    status, msg = _run(db_path, obs_dir, _funding_df_missing_symbol(), FWD_HELD)

    assert status == STATUS_ABORTED, f"expected ABORTED, got {status}: {msg}"
    assert "FUNDING_COVERAGE_MISSING" in msg, msg


# --------------------------------------------------------------------- test 2


def test_writer_proceeds_when_required_funding_complete(tmp_path: Path):
    db_path = _init_test_db(tmp_path, FWD_HELD)
    obs = [_make_obs(ts, [SYMBOL], i) for i, ts in enumerate(TS)]
    obs_dir = _write_observation_log(tmp_path, obs)

    status, msg = _run(db_path, obs_dir, _funding_df_complete(), FWD_HELD)

    assert status == STATUS_OK, f"expected OK with complete funding, got {status}: {msg}"
    assert "FUNDING_COVERAGE_MISSING" not in msg, msg
    # Sanity: the committed batch actually carried available funding rows (so the
    # test is exercising the held-interval path, not a vacuous no-funding commit).
    conn = connect_readonly(db_path)
    try:
        avail = conn.execute(
            "SELECT COUNT(*) FROM funding WHERE rate_available = 1"
        ).fetchone()[0]
    finally:
        conn.close()
    assert avail >= 1, "expected at least one available funding row in the committed batch"


# --------------------------------------------------------------------- test 3


def test_writer_no_sqlite_mutation_on_funding_abort(tmp_path: Path):
    """The load-bearing production proof: a funding abort leaves the SQLite ledger
    unmutated — no batch/event/trade/equity/funding rows, watermark un-advanced —
    because the gate rolls back before any INSERT."""
    db_path = _init_test_db(tmp_path, FWD_HELD)
    obs = [_make_obs(ts, [SYMBOL], i) for i, ts in enumerate(TS)]
    obs_dir = _write_observation_log(tmp_path, obs)

    status, msg = _run(db_path, obs_dir, _funding_df_missing_symbol(), FWD_HELD)

    assert status == STATUS_ABORTED, f"expected ABORTED, got {status}: {msg}"
    _assert_no_accounting_rows(db_path)


# --------------------------------------------------------------------- test 4


def test_writer_does_not_overfire_on_deferred_entry_bar(tmp_path: Path):
    """Regression: a first eligible entry bar with EMPTY funding_df must NOT abort.

    The entry bar's held interval is zero (the engine clamps eff_start to
    entry_fill_ts and skips), so no funding row is emitted and no funding is
    required. The pre-engine gate wrongly aborted this (it demanded the entry
    bar's backward window); the post-engine gate must not. Unit-level analogue of
    tests/test_paper_pnl_wrapper.py::TestEndToEndPreStart."""
    db_path = _init_test_db(tmp_path, FWD_ENTRY_ONLY)
    obs = [_make_obs(ts, [SYMBOL], i) for i, ts in enumerate(TS)]
    obs_dir = _write_observation_log(tmp_path, obs)

    status, msg = _run(db_path, obs_dir, _funding_df_missing_symbol(), FWD_ENTRY_ONLY)

    assert status != STATUS_ABORTED, f"must not abort an entry-only bar, got {status}: {msg}"
    assert "FUNDING_COVERAGE_MISSING" not in msg, msg


# ---------------------------------------------------------------------------
# Gate-predicate tests: parsed-datetime duration + malformed fail-closed.
#
# These patch run_engine to return controlled funding rows so the duration guard
# (window_start < window_end on PARSED UTC datetimes, never a string compare) and
# the malformed-fail-closed branch can be exercised deterministically — the real
# engine only ever emits well-formed bar-ts strings, so a malformed row cannot be
# produced end to end.
# ---------------------------------------------------------------------------

from types import SimpleNamespace  # noqa: E402


def _fake_engine_result(funding_rows: list[dict]) -> SimpleNamespace:
    """An EngineResult-shaped stub carrying only what the gate reads.

    ``equity`` is empty so that, if the gate does NOT abort, the writer takes the
    existing empty-result path (PRE_START on a fresh ledger) — never a spurious
    commit. The gate inspects ``result.funding`` before that path is reached.
    """
    return SimpleNamespace(
        funding=funding_rows,
        equity=[],
        fills=[],
        trades=[],
        positions=[],
        deferred_bar_ts=None,
    )


def _run_with_engine_funding(tmp_path: Path, funding_rows: list[dict]):
    """Drive run_sqlite_accounting with run_engine patched to emit ``funding_rows``."""
    db_path = _init_test_db(tmp_path, FWD_HELD)
    obs = [_make_obs(ts, [SYMBOL], i) for i, ts in enumerate(TS)]
    obs_dir = _write_observation_log(tmp_path, obs)
    p_ohlcv = patch(
        "quantbot.paper.sqlite_writer.load_all_ohlcv", return_value={SYMBOL: _make_bars()}
    )
    p_funding = patch(
        "quantbot.paper.sqlite_writer.load_all_funding", return_value=_funding_df_complete()
    )
    p_config = patch(
        "quantbot.paper.sqlite_writer.load_config", return_value=_config(FWD_HELD)
    )
    p_engine = patch(
        "quantbot.paper.sqlite_writer.run_engine",
        return_value=_fake_engine_result(funding_rows),
    )
    with p_ohlcv, p_funding, p_config, p_engine:
        status, msg = run_sqlite_accounting(db_path=db_path, forward_obs_dir=obs_dir)
    return status, msg, db_path


def _missing_row(window_start: str, window_end: str) -> dict:
    return {
        "funding_id": f"{SYMBOL}|{window_start}",
        "symbol": SYMBOL,
        "bar_ts": window_end,
        "window_start": window_start,
        "window_end": window_end,
        "rate_available": False,
        "funding_amount": 0.0,
        "funding_rate": 0.0,
        "funding_events": 0,
    }


def test_gate_positive_duration_missing_row_aborts(tmp_path: Path):
    """A positive-duration (window_start < window_end) row with rate_available=False
    is required-but-missing -> abort + no mutation."""
    row = _missing_row("2026-06-05T16:00:00", "2026-06-06T00:00:00")
    status, msg, db_path = _run_with_engine_funding(tmp_path, [row])
    assert status == STATUS_ABORTED, f"expected ABORTED, got {status}: {msg}"
    assert "FUNDING_COVERAGE_MISSING" in msg, msg
    _assert_no_accounting_rows(db_path)


def test_gate_degenerate_inverted_row_does_not_abort(tmp_path: Path):
    """A degenerate/inverted exit-stub row (window_end <= window_start) charges zero
    funding and must NOT trigger FUNDING_COVERAGE_MISSING — proven on PARSED datetimes
    (a naive string compare would mis-order these)."""
    # window_end strictly before window_start (inverted).
    row = _missing_row("2026-06-06T00:00:00", "2026-06-05T16:00:00")
    status, msg, _db = _run_with_engine_funding(tmp_path, [row])
    assert status != STATUS_ABORTED, f"degenerate row must not abort, got {status}: {msg}"
    assert "FUNDING_COVERAGE_MISSING" not in msg, msg


def test_gate_equal_endpoints_zero_duration_does_not_abort(tmp_path: Path):
    """A zero-duration row (window_start == window_end) is an empty interval and must
    NOT abort."""
    row = _missing_row("2026-06-06T00:00:00", "2026-06-06T00:00:00")
    status, msg, _db = _run_with_engine_funding(tmp_path, [row])
    assert status != STATUS_ABORTED, f"zero-duration row must not abort, got {status}: {msg}"
    assert "FUNDING_COVERAGE_MISSING" not in msg, msg


def test_gate_malformed_timestamp_missing_row_fails_closed(tmp_path: Path):
    """A missing-funding row whose timestamps do NOT parse cannot be proven a benign
    degenerate stub, so it must fail CLOSED (abort), never silently pass. No mutation."""
    row = _missing_row("not-a-timestamp", "also-bad")
    status, msg, db_path = _run_with_engine_funding(tmp_path, [row])
    assert status == STATUS_ABORTED, f"malformed row must fail closed, got {status}: {msg}"
    assert "FUNDING_COVERAGE_MISSING" in msg, msg
    _assert_no_accounting_rows(db_path)
