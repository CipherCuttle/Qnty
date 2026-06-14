"""T3 (ADVERSARIAL) — the forward_start_ts boundary bar commits EXACTLY once.

The observer emits naive timestamps ('...T00:00:00'); paper_config's forward_start_ts may
carry a trailing 'Z' ('...T00:00:00Z'). A lexicographic compare sorts the naive form BEFORE
its own Z form, which once silently DROPPED the boundary bar. This falsifier pins both
directions of the failure: the boundary bar at exactly forward_start_ts must be committed
once — never skipped, never duplicated — under BOTH timestamp representations, and reruns
must be idempotent. The independent replay must agree.

A failure = an off-by-one at the live boundary baked into the ledger. STOP.

Diagnostic lane: ADVERSARIAL. No edge claim.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from quantbot.lab import fixtures as fx
from quantbot.lab.cross_check import cross_check
from quantbot.lab.replay_engine import run_replay
from quantbot.paper.engine import new_state, run_engine
from quantbot.paper.freshness import check_freshness

TS = fx.grid(4)  # T0 (before) .. T3
BOUNDARY = TS[1]
NOW = datetime(2026, 6, 5, 16, 5, 0, tzinfo=timezone.utc)  # 5 min after the latest obs bar (T2)


def _bars(symbol="AAA"):
    return {symbol: fx.rising_bars(TS)}


@pytest.mark.parametrize("fwd", [BOUNDARY, BOUNDARY + "Z"])
def test_boundary_bar_committed_exactly_once_no_active(fwd: str) -> None:
    """No fills: every eligible bar still produces exactly one equity row keyed by bar_ts."""
    cfg = fx.config(forward_start_ts=fwd)
    obs = fx.obs_log([[], [], [], []], TS)
    state = new_state(cfg["initial_equity_usd"])
    result = run_engine(cfg, obs, _bars(), None, state)

    eq_ts = [e["bar_ts"] for e in result.equity]
    # Bar before the boundary is excluded; boundary + later are included, each once.
    assert TS[0] not in eq_ts
    assert eq_ts.count(BOUNDARY) == 1, f"boundary committed {eq_ts.count(BOUNDARY)}x: {eq_ts}"
    assert eq_ts == [TS[1], TS[2], TS[3]]


@pytest.mark.parametrize("fwd", [BOUNDARY, BOUNDARY + "Z"])
def test_boundary_fill_committed_once_signal_at_boundary(fwd: str) -> None:
    """Active at the boundary -> exactly one entry fill whose signal_bar_ts == boundary."""
    cfg = fx.config(forward_start_ts=fwd)
    obs = fx.obs_log([[], ["AAA"], [], []], TS)  # active exactly at the boundary bar
    state = new_state(cfg["initial_equity_usd"])
    result = run_engine(cfg, obs, _bars(), None, state)

    entry_signals = [f["signal_bar_ts"] for f in result.fills if f["kind"] == "entry"]
    assert entry_signals.count(BOUNDARY) == 1, entry_signals
    # The fill is the boundary instant (naive), accepted under both fwd forms.
    assert all(f["fill_ts"] >= BOUNDARY for f in result.fills)


@pytest.mark.parametrize("fwd", [BOUNDARY, BOUNDARY + "Z"])
def test_boundary_is_eligible_not_pre_start(tmp_path, fwd: str) -> None:
    """The freshness gate must rate the boundary bar OK, not NO_ELIGIBLE_BARS_YET."""
    obs_dir = tmp_path / "fwd"
    obs_dir.mkdir(parents=True)
    rows = fx.obs_log([[], [], []], [TS[0], TS[1], TS[2]])
    obs_path = obs_dir / "observation_log.json"
    obs_path.write_text(json.dumps({"per_bar_obs": rows}), encoding="utf-8")
    res = check_freshness(obs_path, {"per_bar_obs": rows}, obs_dir, NOW, {},
                          forward_start_ts=fwd)
    assert res.ok and res.code == "OK", (res.code, fwd)
    assert res.latest_bar_ts == TS[2]


@pytest.mark.parametrize("fwd", [BOUNDARY, BOUNDARY + "Z"])
def test_rerun_is_idempotent_boundary_not_duplicated(fwd: str) -> None:
    """A second engine pass with the advanced state must append no new boundary row."""
    cfg = fx.config(forward_start_ts=fwd)
    obs = fx.obs_log([[], ["AAA"], [], []], TS)
    state = new_state(cfg["initial_equity_usd"])

    first = run_engine(cfg, obs, _bars(), None, state)
    assert [e["bar_ts"] for e in first.equity].count(BOUNDARY) == 1

    # Same state (watermark advanced) -> the boundary is already past the watermark.
    second = run_engine(cfg, obs, _bars(), None, state)
    assert second.equity == [], "rerun re-emitted bars past the watermark"
    assert second.fills == []


@pytest.mark.parametrize("fwd", [BOUNDARY, BOUNDARY + "Z"])
def test_naive_and_z_select_the_same_boundary_set(fwd: str) -> None:
    """The naive and Z forms must select an identical processed-bar set."""
    cfg = fx.config(forward_start_ts=fwd)
    obs = fx.obs_log([[], ["AAA"], [], []], TS)
    state = new_state(cfg["initial_equity_usd"])
    result = run_engine(cfg, obs, _bars(), None, state)
    assert [e["bar_ts"] for e in result.equity] == [TS[1], TS[2], TS[3]]


def test_replay_agrees_at_boundary_under_both_forms() -> None:
    """Independent replay reproduces the boundary commit identically under naive and Z."""
    obs = fx.obs_log([[], ["AAA"], [], []], TS)
    naive = run_replay(fx.config(forward_start_ts=BOUNDARY), obs, _bars(), None)
    zform = run_replay(fx.config(forward_start_ts=BOUNDARY + "Z"), obs, _bars(), None)
    assert [e["bar_ts"] for e in naive.equity] == [e["bar_ts"] for e in zform.equity]
    assert [e["bar_ts"] for e in naive.equity] == [TS[1], TS[2], TS[3]]

    # And the cross-check (engine vs replay) is CLEAN at the boundary.
    report = cross_check(fx.config(forward_start_ts=BOUNDARY + "Z"), obs, _bars(), None)
    assert report.clean, report.disagreements
    assert report.verdict == "PASS"
