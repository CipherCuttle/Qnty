"""Executable spec for per-symbol unrealized attribution.

Pins the *intended* semantics of ``position_snapshot_symbols.unrealized_gross``
(PR C of ``docs/plans/QNTY_SHADOW_VERIFIER_AND_POSITION_UNREALIZED_DIAGNOSIS_PLAN.md``).

Diagnosis on record: the writer stores ``unrealized_gross = 0.0`` for *every*
child row on both prod and shadow lanes, while ledger-level
``equity_snapshots.unrealized_pnl`` is nonzero and identity-consistent. The
intended behavior is that a moved open position records its per-symbol
unrealized PnL contribution ``(mark - entry_price) * qty``, and that the
per-symbol figures aggregate to the ledger-level unrealized within tolerance.

This file is tests-only — it does not modify the writer, reporter, schema, or
any prod/shadow ledger. Every scenario is built end-to-end through the real
writer against a throwaway SQLite DB under ``tmp_path``.
"""

from __future__ import annotations

import csv
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure repo root is importable (mirrors the sibling writer test module).
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from quantbot.paper.config import build_config, config_hash, write_config_once
from quantbot.paper.db import connect_readonly, initialize_database
from quantbot.paper.sqlite_writer import STATUS_OK, run_sqlite_accounting

TOL = 1e-6

# ---------------------------------------------------------------------------
# Deterministic 8h grid + frozen writer clock (mirrors test_paper_sqlite_writer).
# ---------------------------------------------------------------------------

_GRID_BASE = datetime(2026, 6, 6, 16, 0, 0, tzinfo=timezone.utc)
# Newest-first, then reversed to the oldest-first order real CSV loaders expect.
TS = [
    (_GRID_BASE - timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%S")
    for h in [0, 8, 16, 24, 32, 40]
]
ASC_TS = list(reversed(TS))  # oldest -> newest
NOW = _GRID_BASE + timedelta(minutes=5)

# Position enters at the first eligible bar and is never removed, so it stays
# open through the last committed bar (a moved, open position to attribute).
FORWARD_START = ASC_TS[1]

# Rising (o, c) pairs keyed by timestamp -> a long that moves off its entry.
_RISING = [
    (100.0, 100.0),
    (100.0, 110.0),
    (120.0, 130.0),
    (140.0, 150.0),
    (160.0, 170.0),
    (180.0, 190.0),
]
_RISING_BY_TS = dict(zip(TS, _RISING))

# Real-universe symbols (BTC/ETH are guaranteed members) so the genuine loaders
# read our CSVs instead of skipping them.
SYMBOL_A = "BTCUSDT"
SYMBOL_B = "ETHUSDT"


@pytest.fixture(autouse=True)
def _freeze_writer_now(monkeypatch):
    """Pin the writer's clock so the freshness gate is reproducible."""
    monkeypatch.setattr("quantbot.paper.sqlite_writer._now", lambda: NOW)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _rising_bars() -> list[tuple[float, float, float, float]]:
    """(open, high, low, close) per ASC_TS bar for a rising long."""
    return [
        (o, max(o, c), min(o, c), c)
        for o, c in (_RISING_BY_TS[ts] for ts in ASC_TS)
    ]


def _flat_marked_bars() -> list[tuple[float, float, float, float]]:
    """Bars where the mark equals the entry fill price -> zero true unrealized.

    A long fills at open * (1 + 5bps) = 100.05 under the 5bps slippage model, so
    a close of 100.05 makes mark == entry and the position's unrealized is a
    *genuine* 0.0 (entry and mark are equal), not a writer that failed to
    populate the field.
    """
    return [(100.0, 100.05, 100.0, 100.05) for _ in ASC_TS]


def _write_ohlcv(data_dir: Path, symbol: str, bars) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    with open(data_dir / f"{symbol}_8h_ohlcv.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        for ts, (o, h, l, c) in zip(ASC_TS, bars):
            w.writerow([ts, o, h, l, c, 1.0])


def _write_funding(data_dir: Path, symbol: str, rate: float = 0.0) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    with open(data_dir / f"{symbol}_8h_funding.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["fundingTime", "fundingRate"])
        for ts in ASC_TS:
            w.writerow([int(datetime.fromisoformat(ts).timestamp() * 1000), rate])


def _write_obs_log(tmp_path: Path, active_symbols: list[str]) -> Path:
    import json

    per_bar_obs = [
        {
            "timestamp": ts,
            "bar_index": i,
            # Every eligible bar keeps the symbols active -> enter and hold.
            "active_symbols": list(active_symbols),
            "portfolio_heat": 0.0,
            "heat_cap_triggered": False,
            "weighted_return": 0.0,
        }
        for i, ts in enumerate(ASC_TS)
    ]
    obs_dir = tmp_path / "forward_obs_v1"
    obs_dir.mkdir(parents=True, exist_ok=True)
    (obs_dir / "observation_log.json").write_text(
        json.dumps({"per_bar_obs": per_bar_obs}, indent=2), encoding="utf-8"
    )
    return obs_dir


def _make_config():
    cfg = build_config(
        forward_start_ts=FORWARD_START,
        initial_equity_usd=10000.0,
        notional_usd=1000.0,
        fee_bps=5.0,
        slippage_bps=5.0,
        max_bar_staleness_hours=72.0,
    )
    cfg["config_hash"] = config_hash(cfg)
    return cfg


def _build_open_position_db(
    tmp_path: Path, bars_by_symbol: dict[str, list], *, funding_rate: float = 0.0
) -> Path:
    """Run the real writer to a committed batch with open, marked positions.

    Returns the db_path. Asserts the writer returned OK so a broken fixture
    surfaces as a hard error rather than a misleading expected failure.
    """
    config = _make_config()
    db_path = tmp_path / "paper" / "paper_ledger.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    write_config_once(config, output_dir=db_path.parent)
    initialize_database(db_path, config)

    data_dir = tmp_path / "data"
    for symbol, bars in bars_by_symbol.items():
        _write_ohlcv(data_dir, symbol, bars)
        _write_funding(data_dir, symbol, rate=funding_rate)

    obs_dir = _write_obs_log(tmp_path, list(bars_by_symbol.keys()))

    # Use the REAL loaders (data_dir threaded in); only load_config is patched
    # so config identity resolves without touching a production output dir.
    with patch("quantbot.paper.sqlite_writer.load_config", return_value=config):
        status, msg = run_sqlite_accounting(
            db_path=db_path, forward_obs_dir=obs_dir, data_dir=data_dir
        )
    assert status == STATUS_OK, f"fixture writer did not commit: {status}: {msg}"
    return db_path


def _latest_snapshot_children(conn):
    row = conn.execute(
        "SELECT seq FROM position_snapshots ORDER BY seq DESC LIMIT 1"
    ).fetchone()
    assert row is not None, "expected a position_snapshot to exist"
    return conn.execute(
        "SELECT symbol, qty, entry_price, unrealized_gross "
        "FROM position_snapshot_symbols WHERE snapshot_seq = ? ORDER BY symbol",
        (row["seq"],),
    ).fetchall()


def _latest_ledger_unrealized(conn) -> float:
    return conn.execute(
        "SELECT unrealized_pnl FROM equity_snapshots ORDER BY seq DESC LIMIT 1"
    ).fetchone()["unrealized_pnl"]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def single_moved_db(tmp_path: Path) -> Path:
    return _build_open_position_db(tmp_path, {SYMBOL_A: _rising_bars()})


@pytest.fixture
def multi_moved_db(tmp_path: Path) -> Path:
    return _build_open_position_db(
        tmp_path, {SYMBOL_A: _rising_bars(), SYMBOL_B: _rising_bars()}
    )


@pytest.fixture
def flat_marked_db(tmp_path: Path) -> Path:
    return _build_open_position_db(tmp_path, {SYMBOL_A: _flat_marked_bars()})


# ---------------------------------------------------------------------------
# Specs
# ---------------------------------------------------------------------------

def test_moved_long_position_records_nonzero_unrealized(single_moved_db: Path):
    """A moved open long records nonzero per-symbol unrealized, not 0.0.

    Illustrative contract (real qty is sized from notional): qty=2, entry=100,
    mark=110 => unrealized_gross = (110 - 100) * 2 = 20. Here a single open
    symbol means its per-symbol unrealized must equal the ledger-level figure.
    """
    conn = connect_readonly(single_moved_db)
    try:
        ledger_unrealized = _latest_ledger_unrealized(conn)
        children = _latest_snapshot_children(conn)

        # Preconditions that hold under current behavior: one open, moved position.
        assert len(children) == 1
        assert abs(ledger_unrealized) > TOL, "fixture should move the position"

        child = children[0]
        # The gap: today this is 0.0. Expected: the per-symbol contribution.
        assert abs(child["unrealized_gross"]) > TOL
        assert child["unrealized_gross"] == pytest.approx(ledger_unrealized, abs=TOL)
    finally:
        conn.close()


def test_latest_snapshot_unrealized_sum_matches_ledger(multi_moved_db: Path):
    """Sum of per-symbol unrealized in the latest snapshot == ledger unrealized."""
    conn = connect_readonly(multi_moved_db)
    try:
        ledger_unrealized = _latest_ledger_unrealized(conn)
        children = _latest_snapshot_children(conn)

        assert len(children) == 2, "both open positions must be represented"
        assert abs(ledger_unrealized) > TOL

        child_sum = sum(c["unrealized_gross"] for c in children)
        assert child_sum == pytest.approx(ledger_unrealized, abs=TOL)
    finally:
        conn.close()


def test_each_open_symbol_carries_its_own_unrealized(multi_moved_db: Path):
    """With multiple open symbols, each carries its own nonzero contribution."""
    conn = connect_readonly(multi_moved_db)
    try:
        ledger_unrealized = _latest_ledger_unrealized(conn)
        children = _latest_snapshot_children(conn)

        assert {c["symbol"] for c in children} == {SYMBOL_A, SYMBOL_B}
        for c in children:
            assert abs(c["unrealized_gross"]) > TOL, (
                f"{c['symbol']} should carry its own per-symbol unrealized"
            )
        assert sum(c["unrealized_gross"] for c in children) == pytest.approx(
            ledger_unrealized, abs=TOL
        )
    finally:
        conn.close()


def test_flat_position_zero_unrealized_is_consistent_with_ledger(flat_marked_db: Path):
    """A genuinely flat open position (mark == entry) is a legitimate 0.0.

    This is the control for the specs above: 0.0 is only correct because entry
    and mark are equal (ledger unrealized is also 0.0), *not* because the writer
    failed to populate the field. It passes under current behavior and must keep
    passing after any fix — a fix that reports nonzero here would be wrong.
    """
    conn = connect_readonly(flat_marked_db)
    try:
        ledger_unrealized = _latest_ledger_unrealized(conn)
        children = _latest_snapshot_children(conn)

        assert len(children) == 1
        # Mark == entry, so the true per-symbol unrealized is zero on both sides.
        assert ledger_unrealized == pytest.approx(0.0, abs=TOL)
        assert children[0]["unrealized_gross"] == pytest.approx(0.0, abs=TOL)
        assert children[0]["unrealized_gross"] == pytest.approx(
            ledger_unrealized, abs=TOL
        )
    finally:
        conn.close()
