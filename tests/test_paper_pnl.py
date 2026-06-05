"""Tests for the paper_pnl_v1 accounting layer.

Covers: round-trip fill/PnL, idempotent rerun (identical digests), missing-T+1-open
deferral, long-only invariant, funding-gap flagging, backfill exclusion, winrate-null
until closed trades, write-once config, and reconcile invariants.
"""

import json
from pathlib import Path

import pandas as pd
import pytest

from quantbot.core.determinism import sha256_file
from quantbot.data.types import Bar
from quantbot.paper.config import build_config, write_config_once, load_config
from quantbot.paper.reconcile import reconcile
from quantbot.paper.runner import run_once

# 8h grid, 6 bars T0..T5
TS = [
    "2026-06-05T00:00:00",
    "2026-06-05T08:00:00",
    "2026-06-05T16:00:00",
    "2026-06-06T00:00:00",
    "2026-06-06T08:00:00",
    "2026-06-06T16:00:00",
]

# Rising AAA prices: (open, close) per bar
AAA_PRICES = [
    (100.0, 100.0),
    (100.0, 110.0),
    (120.0, 130.0),
    (140.0, 150.0),
    (160.0, 170.0),
    (180.0, 190.0),
]


def _bars(prices):
    out = []
    for ts, (o, c) in zip(TS, prices):
        out.append(Bar(timestamp=ts, open=o, high=max(o, c), low=min(o, c), close=c, volume=1.0))
    return out


def _funding_df(symbol="AAA", rate=0.0001):
    rows = []
    for ts in TS:
        rows.append(
            {
                "symbol": symbol,
                "dt": pd.Timestamp(ts, tz="UTC"),
                "fundingRate": rate,
                "abs_rate": abs(rate),
            }
        )
    return pd.DataFrame(rows)


def _empty_funding_df():
    return pd.DataFrame(columns=["symbol", "dt", "fundingRate", "abs_rate"])


def _write_obs(forward_dir: Path, per_bar_obs):
    forward_dir.mkdir(parents=True, exist_ok=True)
    (forward_dir / "observation_log.json").write_text(
        json.dumps({"per_bar_obs": per_bar_obs}), encoding="utf-8"
    )


def _obs(active_by_bar):
    """active_by_bar: list of active_symbols lists aligned with TS."""
    return [
        {"timestamp": ts, "active_symbols": active}
        for ts, active in zip(TS, active_by_bar)
    ]


def _setup(tmp_path, active_by_bar, forward_start_ts=TS[0], funding=None, bars=None):
    out = tmp_path / "paper"
    fwd = tmp_path / "fwd"
    write_config_once(build_config(forward_start_ts=forward_start_ts), output_dir=out)
    _write_obs(fwd, _obs(active_by_bar))
    summary = run_once(
        output_dir=out,
        forward_obs_dir=fwd,
        bars_by_symbol={"AAA": _bars(bars or AAA_PRICES)},
        funding_df=funding if funding is not None else _funding_df(),
    )
    return out, fwd, summary


def _read(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# --------------------------------------------------------------------------- tests


def test_round_trip_fill_and_pnl(tmp_path):
    out, _, summary = _setup(tmp_path, [[], ["AAA"], ["AAA"], [], [], []])

    fills = _read(out / "paper_fills.jsonl")
    trades = _read(out / "paper_trades.jsonl")

    assert len(fills) == 2
    entry = next(f for f in fills if f["kind"] == "entry")
    exit_ = next(f for f in fills if f["kind"] == "exit")
    assert entry["side"] == "BUY" and exit_["side"] == "SELL"
    # entry executes at T2 open (120) + slippage; exit at T4 open (160) - slippage
    assert entry["open_price"] == 120.0
    assert exit_["open_price"] == 160.0
    assert entry["fill_ts"] == TS[2]
    assert exit_["fill_ts"] == TS[4]

    assert len(trades) == 1
    t = trades[0]
    assert t["hold_bars"] == 2  # held during T2 and T3 bars
    assert abs(t["net_pnl"] - (t["gross_pnl"] - t["fees"] - t["funding"])) < 1e-9
    assert t["gross_pnl"] > 0  # rising prices
    # trade entry/exit prices tie to the referenced fills' fill_price
    assert t["entry_price"] == entry["fill_price"]
    assert t["exit_price"] == exit_["fill_price"]

    # equity field is realized GROSS (named accordingly), not net
    equity = _read(out / "paper_equity.jsonl")
    assert equity and all("realized_gross_pnl" in e for e in equity)
    assert all("realized_pnl" not in e for e in equity)

    assert summary["closed_trades"] == 1
    assert summary["winrate"] == 1.0
    assert reconcile(out) == []


def test_idempotent_rerun_identical_digests(tmp_path):
    out, fwd, _ = _setup(tmp_path, [[], ["AAA"], ["AAA"], [], [], []])

    deterministic = [
        "paper_fills.jsonl",
        "paper_trades.jsonl",
        "paper_funding.jsonl",
        "paper_positions.jsonl",
        "paper_equity.jsonl",
        "paper_pnl_summary.json",
        "paper_position_state.json",
    ]
    before = {n: sha256_file(out / n) for n in deterministic}

    # second run over the same inputs must not change any ledger
    run_once(
        output_dir=out,
        forward_obs_dir=fwd,
        bars_by_symbol={"AAA": _bars(AAA_PRICES)},
        funding_df=_funding_df(),
    )
    after = {n: sha256_file(out / n) for n in deterministic}
    assert before == after
    assert reconcile(out) == []


def test_missing_next_bar_open_defers(tmp_path):
    # entry signal lands on the last bar T5 -> no T+1 open -> defer
    out, _, _ = _setup(tmp_path, [[], [], [], [], [], ["AAA"]])
    fills = _read(out / "paper_fills.jsonl")
    assert all(f["signal_bar_ts"] != TS[5] for f in fills)
    state = json.loads((out / "paper_position_state.json").read_text())
    assert state["watermark_bar_ts"] < TS[5]
    assert reconcile(out) == []


def test_long_only_invariant(tmp_path):
    out, _, _ = _setup(tmp_path, [[], ["AAA"], [], ["AAA"], [], []])
    fills = _read(out / "paper_fills.jsonl")
    # entries are always BUY, exits always SELL; never a short entry
    for f in fills:
        assert (f["kind"], f["side"]) in {("entry", "BUY"), ("exit", "SELL")}
    assert reconcile(out) == []


def test_funding_gap_flagged_not_silently_zeroed(tmp_path):
    out, _, _ = _setup(
        tmp_path, [[], ["AAA"], ["AAA"], [], [], []], funding=_empty_funding_df()
    )
    funding = _read(out / "paper_funding.jsonl")
    assert funding  # accruals happened while held
    assert all(f["rate_available"] is False for f in funding)
    assert all(f["funding_amount"] == 0.0 for f in funding)
    trades = _read(out / "paper_trades.jsonl")
    assert trades[0]["funding"] == 0.0
    assert reconcile(out) == []


def test_backfill_excluded_before_forward_start(tmp_path):
    # forward_start at T2: signals at T0/T1 must be ignored
    out, _, _ = _setup(
        tmp_path,
        [["AAA"], ["AAA"], ["AAA"], [], [], []],
        forward_start_ts=TS[2],
    )
    fills = _read(out / "paper_fills.jsonl")
    assert fills, "expected a forward entry at/after forward_start_ts"
    assert all(f["signal_bar_ts"] >= TS[2] for f in fills)
    assert all(f["fill_ts"] >= TS[2] for f in fills)
    assert reconcile(out) == []


def test_winrate_null_until_closed_trades(tmp_path):
    # entry but never exits within the window -> no closed trades
    out, _, summary = _setup(tmp_path, [[], ["AAA"], ["AAA"], ["AAA"], ["AAA"], ["AAA"]])
    assert summary["closed_trades"] == 0
    assert summary["winrate"] is None
    assert reconcile(out) == []


def test_config_write_once_and_hash_validation(tmp_path):
    out = tmp_path / "paper"
    config = build_config(forward_start_ts=TS[0])
    write_config_once(config, output_dir=out)

    # write-once: refuse overwrite without force
    with pytest.raises(FileExistsError):
        write_config_once(config, output_dir=out)
    write_config_once(config, output_dir=out, force=True)  # force ok

    # tamper detection
    path = out / "paper_config.json"
    data = json.loads(path.read_text())
    data["notional_usd"] = data["notional_usd"] + 1.0
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load_config(out)
