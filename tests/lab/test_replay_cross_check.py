"""T4 (CROSS_CHECK) + T5 (disagreement classifier).

T4 — Highest-power falsifier: an independent zero-dep (numpy/pandas) replay re-derives
marks, unrealized PnL, fees, funding, exposure and equity straight from per_bar_obs + OHLCV
+ funding, and is compared row-by-row to the production `run_engine`. This directly attacks
the verifier's documented blind spot (it re-derives invariants FROM the DB, not from source
OHLCV): a bug baked into the engine — and therefore the ledger — surfaces as a disagreement
instead of being re-validated cleanly.

T5 — When the engines disagree, the diff is a *measured quantity* triaged into
{QNTY_BUG_CANDIDATE, CHECKER_BUG_CANDIDATE, SPEC_AMBIGUITY, TIMESTAMP_FILL_COST_MISMATCH}.
A disagreement is NEVER auto-blamed on QNTY.

CLEAN agreement => witness harder to fool (PASS). No edge/profitability claim is made.

Diagnostic lane: CROSS_CHECK. FORWARD remains authoritative.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from quantbot.lab import fixtures as fx
from quantbot.lab.cross_check import (
    CHECKER_BUG_CANDIDATE,
    QNTY_BUG_CANDIDATE,
    SPEC_AMBIGUITY,
    TIMESTAMP_FILL_COST_MISMATCH,
    classify_disagreement,
    compare,
    cross_check,
)
from quantbot.lab.replay_engine import run_replay
from quantbot.paper.engine import new_state, run_engine

REPO_ROOT = Path(__file__).resolve().parents[2]
TS6 = fx.grid(6)


def _run_both(cfg, obs, bars, funding):
    state = new_state(cfg["initial_equity_usd"])
    eng = run_engine(cfg, obs, bars, funding, state)
    rep = run_replay(cfg, obs, bars, funding, initial_equity_usd=cfg["initial_equity_usd"])
    return eng, rep


# ============================================================== T4: CLEAN cross-check


def test_round_trip_cross_check_is_clean() -> None:
    s = fx.round_trip_scenario()
    report = cross_check(s["config"], s["per_bar_obs"], s["bars_by_symbol"], s["funding_df"])
    assert report.clean, report.disagreements
    assert report.verdict == "PASS"
    assert report.by_class == {}


def test_no_trade_window_is_clean() -> None:
    cfg = fx.config(forward_start_ts=TS6[0])
    obs = fx.obs_log([[]] * 6, TS6)
    bars = {"AAA": fx.rising_bars(TS6)}
    report = cross_check(cfg, obs, bars, None)
    assert report.clean and report.verdict == "PASS"


def test_funding_gap_window_is_clean() -> None:
    """Empty funding (gap) must be re-derived identically (0 amount, gap-flagged)."""
    cfg = fx.config(forward_start_ts=TS6[0])
    obs = fx.obs_log([[], ["AAA"], ["AAA"], [], [], []], TS6)
    bars = {"AAA": fx.rising_bars(TS6)}
    report = cross_check(cfg, obs, bars, fx.empty_funding_df())
    assert report.clean, report.disagreements
    assert report.verdict == "PASS"


def test_multi_symbol_overlapping_positions_is_clean() -> None:
    cfg = fx.config(forward_start_ts=TS6[0])
    obs = fx.obs_log(
        [[], ["AAA"], ["AAA", "BBB"], ["BBB"], ["BBB"], []], TS6
    )
    bars = {
        "AAA": fx.bars([(100, 101), (101, 99), (99, 104), (104, 108), (108, 107), (107, 110)], TS6),
        "BBB": fx.bars([(50, 51), (51, 53), (53, 52), (52, 49), (49, 55), (55, 54)], TS6),
    }
    funding = fx.funding_df("AAA", [(t, 0.0002) for t in TS6])
    report = cross_check(cfg, obs, bars, funding)
    assert report.clean, report.disagreements
    assert report.verdict == "PASS"


def test_deferral_boundary_agrees() -> None:
    """Signal on the last bar (no T+1 open) -> both engines defer the same bar."""
    cfg = fx.config(forward_start_ts=TS6[0])
    obs = fx.obs_log([[], [], [], [], [], ["AAA"]], TS6)
    bars = {"AAA": fx.rising_bars(TS6)}
    eng, rep = _run_both(cfg, obs, bars, None)
    assert eng.deferred_bar_ts == rep.deferred_bar_ts == TS6[5]
    report = cross_check(cfg, obs, bars, None)
    assert report.clean, report.disagreements


def test_field_level_equivalence_explicit() -> None:
    """Spell out the per-field agreement the verifier itself cannot check (DB-only)."""
    s = fx.round_trip_scenario()
    eng, rep = _run_both(s["config"], s["per_bar_obs"], s["bars_by_symbol"], s["funding_df"])
    eq_e = {e["bar_ts"]: e for e in eng.equity}
    eq_r = {e["bar_ts"]: e for e in rep.equity}
    assert set(eq_e) == set(eq_r)
    for ts in eq_e:
        for fld in ("realized_gross_pnl", "unrealized_pnl", "funding_cum", "fees_cum",
                    "equity", "num_open"):
            assert eq_e[ts][fld] == eq_r[ts][fld], (ts, fld, eq_e[ts][fld], eq_r[ts][fld])
    # Fills agree on price/qty/fee/timing.
    fk = lambda f: (f["signal_bar_ts"], f["symbol"], f["kind"])
    fe = {fk(f): f for f in eng.fills}
    fr = {fk(f): f for f in rep.fills}
    assert set(fe) == set(fr)
    for k in fe:
        for fld in ("fill_ts", "qty", "open_price", "fill_price", "fee"):
            assert fe[k][fld] == fr[k][fld], (k, fld)


# ============================================================== T5: classifier coverage


def test_classifier_cost_field_is_timestamp_fill_cost() -> None:
    for fld in ("open_price", "fill_price", "qty", "fee", "fill_ts", "gross_exposure_usd"):
        assert classify_disagreement(fld, None, None, 10000.0) == TIMESTAMP_FILL_COST_MISMATCH


def test_classifier_funding_field_is_spec_ambiguity() -> None:
    for fld in ("funding_cum", "funding_amount", "funding_rate", "funding_events"):
        assert classify_disagreement(fld, None, None, 10000.0) == SPEC_AMBIGUITY


def test_classifier_inconsistent_engine_equity_is_qnty_candidate() -> None:
    initial = 10000.0
    engine_row = {  # equity does NOT satisfy the identity -> production is internally wrong
        "realized_gross_pnl": 0.0, "fees_cum": 0.0, "funding_cum": 0.0,
        "unrealized_pnl": 0.0, "equity": 12345.0,
    }
    replay_row = {  # self-consistent
        "realized_gross_pnl": 0.0, "fees_cum": 0.0, "funding_cum": 0.0,
        "unrealized_pnl": 0.0, "equity": 10000.0,
    }
    assert classify_disagreement("equity", engine_row, replay_row, initial) == QNTY_BUG_CANDIDATE


def test_classifier_inconsistent_replay_equity_is_checker_candidate() -> None:
    initial = 10000.0
    engine_row = {
        "realized_gross_pnl": 0.0, "fees_cum": 0.0, "funding_cum": 0.0,
        "unrealized_pnl": 0.0, "equity": 10000.0,
    }
    replay_row = {  # checker's own arithmetic is broken
        "realized_gross_pnl": 0.0, "fees_cum": 0.0, "funding_cum": 0.0,
        "unrealized_pnl": 0.0, "equity": 99999.0,
    }
    assert classify_disagreement("equity", engine_row, replay_row, initial) == CHECKER_BUG_CANDIDATE


def test_classifier_both_consistent_but_differ_is_spec_ambiguity() -> None:
    initial = 10000.0
    engine_row = {  # consistent at 10000
        "realized_gross_pnl": 0.0, "fees_cum": 0.0, "funding_cum": 0.0,
        "unrealized_pnl": 0.0, "equity": 10000.0,
    }
    replay_row = {  # consistent at 10001 (different definition of unrealized)
        "realized_gross_pnl": 0.0, "fees_cum": 0.0, "funding_cum": 0.0,
        "unrealized_pnl": 1.0, "equity": 10001.0,
    }
    assert classify_disagreement("equity", engine_row, replay_row, initial) == SPEC_AMBIGUITY


def test_classifier_unknown_field_never_blames_qnty() -> None:
    assert classify_disagreement("totally_unknown_field", None, None, 10000.0) != QNTY_BUG_CANDIDATE
    assert classify_disagreement("num_open", None, None, 10000.0) == SPEC_AMBIGUITY


# ----- injected real disagreements through compare() (not auto-blamed on QNTY) -----


def _clean_results():
    s = fx.round_trip_scenario()
    eng, rep = _run_both(s["config"], s["per_bar_obs"], s["bars_by_symbol"], s["funding_df"])
    return s, eng, rep


def test_injected_fill_price_diff_is_cost_mismatch() -> None:
    _, eng, rep = _clean_results()
    # Corrupt the engine's first fill price -> a pure fill/cost disagreement.
    eng.fills[0]["fill_price"] = round(eng.fills[0]["fill_price"] + 1.0, 8)
    diffs = compare(eng, rep, 10000.0)
    cost = [d for d in diffs if d.field == "fill_price"]
    assert cost and all(d.classification == TIMESTAMP_FILL_COST_MISMATCH for d in cost)
    # And never silently blamed on QNTY.
    assert all(d.classification != QNTY_BUG_CANDIDATE for d in cost)


def test_injected_engine_equity_inconsistency_is_qnty_candidate() -> None:
    _, eng, rep = _clean_results()
    # Break ONLY the engine's equity number (components untouched) -> internal inconsistency.
    eng.equity[-1]["equity"] = round(eng.equity[-1]["equity"] + 5.0, 8)
    diffs = compare(eng, rep, 10000.0)
    eqd = [d for d in diffs if d.field == "equity"]
    assert eqd and all(d.classification == QNTY_BUG_CANDIDATE for d in eqd)


def test_injected_replay_equity_inconsistency_is_checker_candidate() -> None:
    _, eng, rep = _clean_results()
    rep.equity[-1]["equity"] = round(rep.equity[-1]["equity"] + 5.0, 8)
    diffs = compare(eng, rep, 10000.0)
    eqd = [d for d in diffs if d.field == "equity"]
    assert eqd and all(d.classification == CHECKER_BUG_CANDIDATE for d in eqd)


def test_injected_funding_diff_is_spec_ambiguity() -> None:
    _, eng, rep = _clean_results()
    eng.equity[-1]["funding_cum"] = round(eng.equity[-1]["funding_cum"] + 0.01, 8)
    diffs = compare(eng, rep, 10000.0)
    fd = [d for d in diffs if d.field == "funding_cum"]
    assert fd and all(d.classification == SPEC_AMBIGUITY for d in fd)


# ============================================================== CLI on recorded fixture


def test_cross_check_cli_on_recorded_fixture(tmp_path) -> None:
    """Drive the documented CLI on a recorded observer bundle; writes only under output/lab/."""
    payload = fx.to_payload(fx.round_trip_scenario())
    fixture = tmp_path / "recorded_obs.json"
    fixture.write_text(json.dumps(payload), encoding="utf-8")
    out = tmp_path / "output" / "lab" / "cross_check"  # contains 'output/lab' -> allowed

    proc = subprocess.run(
        [sys.executable, "-m", "quantbot.lab.cross_check",
         "--obs-fixture", str(fixture), "--out", str(out), "--json"],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
    )
    assert proc.returncode == 0, proc.stderr
    assert "verdict=PASS" in proc.stdout
    # The report landed under output/lab only.
    reports = list(out.glob("*/cross_check_report.json"))
    assert len(reports) == 1
    report = json.loads(reports[0].read_text())
    assert report["clean"] is True and report["verdict"] == "PASS"


def test_cross_check_cli_refuses_to_write_outside_output_lab(tmp_path) -> None:
    payload = fx.to_payload(fx.round_trip_scenario())
    fixture = tmp_path / "recorded_obs.json"
    fixture.write_text(json.dumps(payload), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-m", "quantbot.lab.cross_check",
         "--obs-fixture", str(fixture), "--out", str(tmp_path / "somewhere_else")],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
    )
    assert proc.returncode != 0
    assert "refusing to write outside output/lab" in (proc.stderr + proc.stdout)
