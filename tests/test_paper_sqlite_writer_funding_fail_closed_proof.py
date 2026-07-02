"""SQLite writer funding-source fail-closed proof tests.

These tests use only tmp SQLite DBs, tmp forward-observation logs, and tmp
OHLCV/funding CSVs. They never touch /srv, production DBs, shadow DBs, or
forward_obs.

The writer fails closed when the engine sees required funding with no source
event at all, and when the shared funding timestamp normalizer rejects source
CSV rows before durable SQLite mutation.
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from quantbot.paper.config import build_config, write_config_once
from quantbot.paper.db import connect_readonly, initialize_database
from quantbot.paper.sqlite_writer import (
    STATUS_ABORTED,
    STATUS_OK,
    run_sqlite_accounting,
)

SYMBOL = "BTCUSDT"
GRID_START = datetime(2026, 6, 5, 0, 0, 0, tzinfo=timezone.utc)
GRID_TIMES = [GRID_START + timedelta(hours=8 * i) for i in range(6)]
TS = [dt.strftime("%Y-%m-%dT%H:%M:%S") for dt in GRID_TIMES]
FWD_HELD = TS[0]
NOW = GRID_TIMES[-1] + timedelta(minutes=5)

# With an always-active symbol, the first bar enters, the second bar has a
# zero-duration held interval, and these later endpoints require funding.
REQUIRED_FUNDING_ENDPOINTS = TS[2:]


@pytest.fixture(autouse=True)
def _freeze_writer_now(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("quantbot.paper.sqlite_writer._now", lambda: NOW)


def _ms_at(ts: str, *, offset_ms: int = 0) -> int:
    dt = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000) + offset_ms


def _config() -> dict:
    return build_config(
        forward_start_ts=FWD_HELD,
        initial_equity_usd=10000.0,
        notional_usd=1000.0,
        fee_bps=5.0,
        slippage_bps=5.0,
        max_bar_staleness_hours=72.0,
    )


def _init_test_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    output_dir = tmp_path / "paper"
    output_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("QNTY_PAPER_OUTPUT_DIR", str(output_dir))

    config = _config()
    write_config_once(config, output_dir=output_dir)
    db_path = output_dir / "paper_ledger.db"
    initialize_database(db_path, config)
    return db_path


def _write_observation_log(tmp_path: Path) -> Path:
    obs_dir = tmp_path / "forward_obs_v1"
    obs_dir.mkdir(parents=True, exist_ok=True)
    per_bar_obs = [
        {
            "timestamp": ts,
            "bar_index": i,
            "active_symbols": [SYMBOL],
            "portfolio_heat": 0.0,
            "heat_cap_triggered": False,
            "weighted_return": 0.0,
        }
        for i, ts in enumerate(TS)
    ]
    (obs_dir / "observation_log.json").write_text(
        json.dumps({"per_bar_obs": per_bar_obs}, indent=2),
        encoding="utf-8",
    )
    return obs_dir


def _write_ohlcv_csv(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    csv_path = data_dir / f"{SYMBOL}_8h_ohlcv.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        for i, ts in enumerate(TS):
            open_price = 100.0 + (i * 10.0)
            close_price = open_price + 5.0
            writer.writerow(
                [
                    ts,
                    open_price,
                    max(open_price, close_price),
                    min(open_price, close_price),
                    close_price,
                    1.0,
                ]
            )


def _write_funding_csv(data_dir: Path, funding_times_ms: list[int]) -> None:
    csv_path = data_dir / f"{SYMBOL}_8h_funding.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["fundingTime", "fundingRate", "markPrice"])
        for ms in funding_times_ms:
            writer.writerow([ms, "0.0001", "100.0"])


def _run_writer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    funding_times_ms: list[int] | None,
) -> tuple[int, str, Path]:
    db_path = _init_test_db(tmp_path, monkeypatch)
    obs_dir = _write_observation_log(tmp_path)
    data_dir = tmp_path / "data"
    _write_ohlcv_csv(data_dir)
    if funding_times_ms is not None:
        _write_funding_csv(data_dir, funding_times_ms)

    status, msg = run_sqlite_accounting(
        db_path=db_path,
        forward_obs_dir=obs_dir,
        data_dir=data_dir,
    )
    return status, msg, db_path


def _funding_times_with_endpoint_offset(offset_ms: int) -> list[int]:
    return [_ms_at(ts, offset_ms=offset_ms) for ts in REQUIRED_FUNDING_ENDPOINTS]


def _funding_times_with_duplicate_canonical_endpoints() -> list[int]:
    rows: list[int] = []
    for ts in REQUIRED_FUNDING_ENDPOINTS:
        rows.append(_ms_at(ts))
        rows.append(_ms_at(ts, offset_ms=5))
    return rows


def _assert_no_durable_mutation(db_path: Path) -> None:
    conn = connect_readonly(db_path)
    try:
        for table in (
            "ledger_batches",
            "ledger_events",
            "signal_snapshots",
            "funding",
            "fills",
            "trades",
            "position_snapshots",
            "equity_snapshots",
            "open_positions",
        ):
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            assert count == 0, (
                f"{table} must stay empty after funding abort, got {count}"
            )

        state = conn.execute(
            """
            SELECT watermark_bar_ts, realized_gross, fees_cum, funding_cum
            FROM ledger_state
            WHERE id = 1
            """
        ).fetchone()
        assert state["watermark_bar_ts"] is None
        assert state["realized_gross"] == 0.0
        assert state["fees_cum"] == 0.0
        assert state["funding_cum"] == 0.0
    finally:
        conn.close()


def _assert_committed_funding_rows(db_path: Path) -> None:
    conn = connect_readonly(db_path)
    try:
        batch_count = conn.execute("SELECT COUNT(*) FROM ledger_batches").fetchone()[0]
        funding_count = conn.execute("SELECT COUNT(*) FROM funding").fetchone()[0]
        unavailable_count = conn.execute(
            "SELECT COUNT(*) FROM funding WHERE rate_available = 0"
        ).fetchone()[0]
    finally:
        conn.close()

    assert batch_count == 1
    assert funding_count == len(REQUIRED_FUNDING_ENDPOINTS)
    assert unavailable_count == 0


def test_writer_fails_closed_before_db_mutation_when_source_csv_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    status, msg, db_path = _run_writer(
        tmp_path,
        monkeypatch,
        funding_times_ms=None,
    )

    assert status == STATUS_ABORTED, f"expected ABORTED, got {status}: {msg}"
    assert "FUNDING_COVERAGE_MISSING" in msg, msg
    _assert_no_durable_mutation(db_path)


@pytest.mark.parametrize("offset_ms", [0, 5, 9])
def test_writer_accepts_endpoint_and_endpoint_jitter_before_db_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    offset_ms: int,
) -> None:
    status, msg, db_path = _run_writer(
        tmp_path,
        monkeypatch,
        funding_times_ms=_funding_times_with_endpoint_offset(offset_ms),
    )

    assert status == STATUS_OK, (
        f"expected OK for +{offset_ms}ms jitter, got {status}: {msg}"
    )
    assert "FUNDING_COVERAGE_MISSING" not in msg, msg
    _assert_committed_funding_rows(db_path)


def test_writer_fails_closed_before_db_mutation_when_source_row_outside_tolerance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    status, msg, db_path = _run_writer(
        tmp_path,
        monkeypatch,
        funding_times_ms=_funding_times_with_endpoint_offset(11),
    )

    assert status == STATUS_ABORTED, (
        f"expected ABORTED for +11ms source rows, got {status}: {msg}"
    )
    assert "FUNDING_COVERAGE_MISSING" in msg, msg
    assert "outside_tolerance" in msg, msg
    _assert_no_durable_mutation(db_path)


def test_writer_fails_closed_before_db_mutation_when_source_rows_are_ambiguous(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    status, msg, db_path = _run_writer(
        tmp_path,
        monkeypatch,
        funding_times_ms=_funding_times_with_duplicate_canonical_endpoints(),
    )

    assert status == STATUS_ABORTED, (
        f"expected ABORTED for duplicate source rows, got {status}: {msg}"
    )
    assert "FUNDING_COVERAGE_MISSING" in msg, msg
    assert "duplicate_canonical_endpoint" in msg, msg
    _assert_no_durable_mutation(db_path)
