"""Regression tests: forward_start_ts eligibility must normalize timestamps.

Observer per_bar_obs timestamps are naive ISO ('2026-06-14T00:00:00'); paper_config's
forward_start_ts carries a trailing UTC 'Z' ('2026-06-14T00:00:00Z'). A lexicographic
string compare puts the naive form strictly BEFORE its own trailing-Z form, so a bar at
exactly forward_start_ts was wrongly excluded — the freshness gate returned
NO_ELIGIBLE_BARS_YET / the SQLite writer returned PRE_START even though a bar had reached
the boundary. These tests pin the fix: every forward_start_ts eligibility comparison parses
both forms into timezone-aware UTC datetimes before comparing.

All tests use tmp_path only — no repo output, no /srv/qnty, no VM paths.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from quantbot.data.types import Bar
from quantbot.paper.config import build_config, config_hash, write_config_once
from quantbot.paper.db import connect_readonly, initialize_database
from quantbot.paper.engine import new_state, run_engine
from quantbot.paper.freshness import check_freshness, parse_bar_utc
from quantbot.paper.sqlite_writer import (
    STATUS_OK,
    STATUS_PRE_START,
    run_sqlite_accounting,
)
from quantbot.paper.sqlite_verify import STATUS_OK as V_STATUS_OK, verify_database

# Reuse the SQLite writer-test fixtures (timestamps, bars, observation-log builders).
from tests.test_paper_sqlite_writer import (  # noqa: E402
    NOW,
    SYMBOL,
    TS,
    _make_cfg,
    _make_obs,
    _patch_data_loaders,
    _write_observation_log,
)

# The boundary scenario from the bug report: a config with a trailing Z and an observer
# bar at exactly that instant in naive form.
FWD_Z = "2026-06-14T00:00:00Z"
BAR_AT_FWD = "2026-06-14T00:00:00"      # naive observer form of the same instant
BAR_BEFORE_FWD = "2026-06-13T16:00:00"  # one 8h grid bar before the boundary
NOW_AT_FWD = datetime(2026, 6, 14, 0, 5, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _freeze_writer_now(monkeypatch):
    """Pin the SQLite writer's clock to NOW for the in-process writer runs below."""
    monkeypatch.setattr("quantbot.paper.sqlite_writer._now", lambda: NOW)


# --------------------------------------------------------------------------- helpers


def _obs_row(ts: str, active=(), bar_index: int = 0) -> dict:
    return {
        "timestamp": ts,
        "bar_index": bar_index,
        "active_symbols": list(active),
        "portfolio_heat": 0.0,
        "heat_cap_triggered": False,
        "weighted_return": 0.0,
    }


def _write_obs_log(obs_dir: Path, rows: list[dict]) -> Path:
    obs_dir.mkdir(parents=True, exist_ok=True)
    path = obs_dir / "observation_log.json"
    path.write_text(json.dumps({"per_bar_obs": rows}), encoding="utf-8")
    return path


# ----------------------------------------------------------------- 1. the helper itself


def test_parse_bar_utc_normalizes_naive_and_z_to_same_instant():
    assert parse_bar_utc(BAR_AT_FWD) == parse_bar_utc(FWD_Z)
    # The bug it defeats: the raw string compare treats the boundary bar as "before".
    assert (BAR_AT_FWD >= FWD_Z) is False  # documents the latent lexicographic bug
    assert parse_bar_utc(BAR_AT_FWD) >= parse_bar_utc(FWD_Z)  # the correct verdict
    assert parse_bar_utc(BAR_BEFORE_FWD) < parse_bar_utc(FWD_Z)


def test_parse_bar_utc_fails_closed_on_malformed():
    # Malformed / wrong-grid-format / non-str must raise, never silently pass.
    with pytest.raises(ValueError):
        parse_bar_utc("2026-06-14")
    with pytest.raises(ValueError):
        parse_bar_utc("not-a-timestamp")
    with pytest.raises(TypeError):
        parse_bar_utc(None)  # type: ignore[arg-type]


# ----------------------------------------------------------- 2. freshness eligibility gate


def test_freshness_bar_at_forward_start_is_eligible(tmp_path: Path):
    """config forward_start_ts has trailing Z; obs bar is naive at the same instant."""
    obs_dir = tmp_path / "fwd"
    rows = [_obs_row(BAR_AT_FWD)]
    obs_path = _write_obs_log(obs_dir, rows)
    result = check_freshness(
        obs_path, {"per_bar_obs": rows}, obs_dir, NOW_AT_FWD, {}, forward_start_ts=FWD_Z
    )
    assert result.ok
    # Eligible -> a normal OK, NOT the pre-start no-op.
    assert result.code == "OK", f"boundary bar should be eligible, got {result.code}"


def test_freshness_bar_before_forward_start_is_not_eligible(tmp_path: Path):
    obs_dir = tmp_path / "fwd"
    rows = [_obs_row(BAR_BEFORE_FWD)]
    obs_path = _write_obs_log(obs_dir, rows)
    result = check_freshness(
        obs_path, {"per_bar_obs": rows}, obs_dir, NOW_AT_FWD, {}, forward_start_ts=FWD_Z
    )
    assert result.ok  # clean file, just nothing eligible yet
    assert result.code == "NO_ELIGIBLE_BARS_YET"


def test_freshness_mixed_only_boundary_and_later_are_consumed(tmp_path: Path):
    obs_dir = tmp_path / "fwd"
    rows = [_obs_row(BAR_BEFORE_FWD, bar_index=0), _obs_row(BAR_AT_FWD, bar_index=1)]
    obs_path = _write_obs_log(obs_dir, rows)
    result = check_freshness(
        obs_path, {"per_bar_obs": rows}, obs_dir, NOW_AT_FWD, {}, forward_start_ts=FWD_Z
    )
    assert result.ok and result.code == "OK"
    assert result.latest_bar_ts == BAR_AT_FWD


# ------------------------------------------------------------- 3. engine forward filter


def _run_engine_for(forward_start_ts: str, obs_ts: str):
    config = build_config(forward_start_ts=forward_start_ts)
    bars = {"AAA": [Bar(timestamp=obs_ts, open=100.0, high=100.0, low=100.0,
                        close=100.0, volume=1.0)]}
    state = new_state(config["initial_equity_usd"])
    return run_engine(config, [_obs_row(obs_ts)], bars, None, state)


def test_engine_processes_bar_at_forward_start_with_trailing_z():
    result = _run_engine_for(FWD_Z, BAR_AT_FWD)
    assert [e["bar_ts"] for e in result.equity] == [BAR_AT_FWD], (
        "boundary bar must be processed despite naive-vs-Z formatting"
    )


def test_engine_excludes_bar_before_forward_start():
    result = _run_engine_for(FWD_Z, BAR_BEFORE_FWD)
    assert result.equity == [], "a pre-boundary bar must not be processed"


# -------------------------------------------------- 4. end-to-end fresh-start (SQLite path)


def _init_db_with_fwd(tmp_path: Path, forward_start_ts: str) -> Path:
    db_path = tmp_path / "paper" / "paper_ledger.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    config = build_config(
        forward_start_ts=forward_start_ts,
        initial_equity_usd=10000.0,
        notional_usd=1000.0,
        fee_bps=5.0,
        slippage_bps=5.0,
        max_bar_staleness_hours=72.0,
    )
    write_config_once(config, output_dir=db_path.parent)
    initialize_database(db_path, config)
    return db_path


def _run_writer_with_fwd(tmp_path: Path, db_path: Path, forward_start_ts: str,
                         per_bar_obs: list[dict]):
    obs_dir = _write_observation_log(tmp_path, per_bar_obs)
    cfg = _make_cfg()
    cfg["forward_start_ts"] = forward_start_ts
    cfg["config_hash"] = config_hash(cfg)
    p1, p2 = _patch_data_loaders(tmp_path)
    with p1, p2:
        with patch("quantbot.paper.sqlite_writer.load_config", return_value=cfg):
            return run_sqlite_accounting(db_path=db_path, forward_obs_dir=obs_dir)


def test_fresh_start_trailing_z_commits_boundary_bar_not_pre_start(tmp_path: Path):
    """The exact failing scenario: fresh DB/config forward_start_ts has trailing Z, the
    observation_log carries the boundary bar in naive form. The run must commit a batch
    for that bar and must NOT return PRE_START purely because of the timestamp-format
    mismatch. The boundary bar carries an active symbol, so it also produces a fill whose
    signal_bar_ts == forward_start_ts (instant-equal): the forward-start floor must accept
    it rather than flag it as 'before forward_start_ts'.
    """
    fwd_z = TS[0] + "Z"  # newest grid bar, with trailing Z (mirrors paper_config.json)
    db_path = _init_db_with_fwd(tmp_path, fwd_z)
    per_bar_obs = [_make_obs(ts, [SYMBOL], i) for i, ts in enumerate(TS)]

    status, msg = _run_writer_with_fwd(tmp_path, db_path, fwd_z, per_bar_obs)

    assert status != STATUS_PRE_START, f"regressed to PRE_START on format mismatch: {msg}"
    assert status == STATUS_OK, f"expected OK committed batch, got {status}: {msg}"

    conn = connect_readonly(db_path)
    try:
        watermark = conn.execute(
            "SELECT watermark_bar_ts FROM ledger_state WHERE id = 1"
        ).fetchone()[0]
        committed = conn.execute(
            "SELECT bar_ts FROM equity_snapshots"
        ).fetchall()
        fill_sig = conn.execute(
            "SELECT signal_bar_ts FROM fills"
        ).fetchall()
    finally:
        conn.close()

    assert watermark == TS[0], f"watermark should advance to the boundary bar, got {watermark!r}"
    assert [r[0] for r in committed] == [TS[0]]
    # Boundary fill committed at the forward-start instant (naive), not rejected.
    assert [r[0] for r in fill_sig] == [TS[0]]


def test_fresh_start_trailing_z_verifies_ok(tmp_path: Path):
    """The committed boundary batch must also pass the read-only verifier — i.e. neither
    the writer's in-transaction reconcile nor the verifier's arithmetic gate flags the
    boundary fill as 'signal_bar_ts < forward_start_ts' due to the trailing-Z mismatch.
    """
    fwd_z = TS[0] + "Z"
    db_path = _init_db_with_fwd(tmp_path, fwd_z)
    per_bar_obs = [_make_obs(ts, [SYMBOL], i) for i, ts in enumerate(TS)]
    status, msg = _run_writer_with_fwd(tmp_path, db_path, fwd_z, per_bar_obs)
    assert status == STATUS_OK, msg

    result = verify_database(db_path)
    assert result.status == V_STATUS_OK, (
        f"verifier should pass for the boundary batch, got {result.status}: "
        f"{getattr(result, 'failures', None)}"
    )
