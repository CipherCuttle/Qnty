"""Tests for the paper_pnl_v1 accounting layer.

Covers: round-trip fill/PnL, idempotent rerun (identical digests), missing-T+1-open
deferral, long-only invariant, funding-gap flagging, backfill exclusion, winrate-null
until closed trades, write-once config, and reconcile invariants.
"""

import json
from datetime import datetime, timedelta, timezone
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

# Deterministic "now" for the freshness gate: 5 minutes after the last grid bar, so the
# observer output is fresh regardless of the wall clock. (Hardening: section 9.)
NOW = datetime(2026, 6, 6, 16, 5, 0, tzinfo=timezone.utc)

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


def _setup(
    tmp_path, active_by_bar, forward_start_ts=TS[0], funding=None, bars=None, now=NOW
):
    out = tmp_path / "paper"
    fwd = tmp_path / "fwd"
    write_config_once(build_config(forward_start_ts=forward_start_ts), output_dir=out)
    _write_obs(fwd, _obs(active_by_bar))
    summary = run_once(
        output_dir=out,
        forward_obs_dir=fwd,
        bars_by_symbol={"AAA": _bars(bars or AAA_PRICES)},
        funding_df=funding if funding is not None else _funding_df(),
        now=now,
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
        now=NOW,
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


# ------------------------------------------------------- hardening: freshness gate


_LEDGER_FILES = [
    "paper_fills.jsonl",
    "paper_trades.jsonl",
    "paper_equity.jsonl",
    "paper_positions.jsonl",
    "paper_funding.jsonl",
    "paper_signal_snapshots.jsonl",
]


def _no_ledger_rows(out: Path) -> bool:
    return all(_read(out / name) == [] for name in _LEDGER_FILES)


def test_stale_observation_aborts_without_writing(tmp_path):
    # now is 5 days after the latest bar -> beyond the 24h staleness threshold.
    stale_now = NOW + timedelta(days=5)
    out, _, summary = _setup(
        tmp_path, [[], ["AAA"], ["AAA"], [], [], []], now=stale_now
    )
    assert summary["status"] == "ABORTED"
    assert summary["abort_code"] == "STALE_OBSERVATION"
    assert _no_ledger_rows(out)
    # an aborted run must NOT be mistaken for a FLAT result
    assert "FLAT" not in summary["current_verdict"]


def test_missing_observation_log_aborts(tmp_path):
    out = tmp_path / "paper"
    fwd = tmp_path / "fwd"
    fwd.mkdir(parents=True, exist_ok=True)
    write_config_once(build_config(forward_start_ts=TS[0]), output_dir=out)
    # no observation_log.json written
    summary = run_once(
        output_dir=out,
        forward_obs_dir=fwd,
        bars_by_symbol={"AAA": _bars(AAA_PRICES)},
        funding_df=_funding_df(),
        now=NOW,
    )
    assert summary["status"] == "ABORTED"
    assert summary["abort_code"] == "MISSING_OBSERVATION_LOG"
    assert _no_ledger_rows(out)


def test_malformed_per_bar_obs_aborts(tmp_path):
    out = tmp_path / "paper"
    fwd = tmp_path / "fwd"
    fwd.mkdir(parents=True, exist_ok=True)
    write_config_once(build_config(forward_start_ts=TS[0]), output_dir=out)
    # per_bar_obs present but rows are malformed (missing timestamp)
    (fwd / "observation_log.json").write_text(
        json.dumps({"per_bar_obs": [{"active_symbols": ["AAA"]}]}), encoding="utf-8"
    )
    summary = run_once(
        output_dir=out,
        forward_obs_dir=fwd,
        bars_by_symbol={"AAA": _bars(AAA_PRICES)},
        funding_df=_funding_df(),
        now=NOW,
    )
    assert summary["status"] == "ABORTED"
    assert summary["abort_code"] == "MALFORMED_OBSERVATION_LOG"
    assert _no_ledger_rows(out)


def test_off_grid_bar_aborts(tmp_path):
    out = tmp_path / "paper"
    fwd = tmp_path / "fwd"
    fwd.mkdir(parents=True, exist_ok=True)
    write_config_once(build_config(forward_start_ts=TS[0]), output_dir=out)
    # latest bar at 17:00 is not on the 8h grid (00/08/16)
    obs = _obs([[], ["AAA"]]) + [{"timestamp": "2026-06-06T17:00:00", "active_symbols": []}]
    (fwd / "observation_log.json").write_text(json.dumps({"per_bar_obs": obs}), encoding="utf-8")
    summary = run_once(
        output_dir=out,
        forward_obs_dir=fwd,
        bars_by_symbol={"AAA": _bars(AAA_PRICES)},
        funding_df=_funding_df(),
        now=NOW,
    )
    assert summary["status"] == "ABORTED"
    assert summary["abort_code"] == "OFF_GRID_BAR"
    assert _no_ledger_rows(out)


# --------------------------------------------- hardening: consumed-signal snapshots


def test_snapshot_written_once_per_consumed_bar(tmp_path):
    out, _, _ = _setup(tmp_path, [[], ["AAA"], ["AAA"], [], [], []])
    snaps = _read(out / "paper_signal_snapshots.jsonl")
    equity = _read(out / "paper_equity.jsonl")
    # exactly one snapshot per consumed (equity-snapshotted) bar
    assert {s["bar_ts"] for s in snaps} == {e["bar_ts"] for e in equity}
    assert len(snaps) == len(equity)
    # snapshot freezes the exact consumed source row
    for s in snaps:
        assert s["backfill"] is False
        assert "source_observation_digest" in s
        assert "active_symbols" in s and "weighted_return" in s
    assert reconcile(out) == []


def test_no_duplicate_snapshots_on_rerun(tmp_path):
    out, fwd, _ = _setup(tmp_path, [[], ["AAA"], ["AAA"], [], [], []])
    before = sha256_file(out / "paper_signal_snapshots.jsonl")
    run_once(
        output_dir=out,
        forward_obs_dir=fwd,
        bars_by_symbol={"AAA": _bars(AAA_PRICES)},
        funding_df=_funding_df(),
        now=NOW,
    )
    after = sha256_file(out / "paper_signal_snapshots.jsonl")
    assert before == after  # rerun appended nothing
    snaps = _read(out / "paper_signal_snapshots.jsonl")
    assert len({s["snapshot_id"] for s in snaps}) == len(snaps)  # no dup ids
    assert reconcile(out) == []


def test_snapshot_divergence_aborts(tmp_path):
    out, fwd, _ = _setup(tmp_path, [[], ["AAA"], ["AAA"], [], [], []])
    digests_before = {n: sha256_file(out / n) for n in _LEDGER_FILES}

    # the rolling observer window recomputes an already-consumed bar (T2) differently
    diverged = _obs([[], ["AAA"], [], [], [], []])  # T2 active_symbols changed
    (fwd / "observation_log.json").write_text(
        json.dumps({"per_bar_obs": diverged}), encoding="utf-8"
    )
    summary = run_once(
        output_dir=out,
        forward_obs_dir=fwd,
        bars_by_symbol={"AAA": _bars(AAA_PRICES)},
        funding_df=_funding_df(),
        now=NOW,
    )
    assert summary["status"] == "ABORTED"
    assert summary["abort_code"] == "SIGNAL_SNAPSHOT_DIVERGENCE"
    # no append-only ledger was rewritten
    assert {n: sha256_file(out / n) for n in _LEDGER_FILES} == digests_before


# --------------------------------------------------------- hardening: funding audit


def _funding_rows(symbol, pairs):
    """pairs: list of (iso_ts, rate)."""
    return pd.DataFrame(
        [
            {
                "symbol": symbol,
                "dt": pd.Timestamp(ts, tz="UTC"),
                "fundingRate": rate,
                "abs_rate": abs(rate),
            }
            for ts, rate in pairs
        ]
    )


def test_funding_multiple_events_in_one_interval(tmp_path):
    # Position entered at T2 open (signal at T1). Its first snapshot is T2, whose funding
    # window is (T1, T2] = (08:00, 16:00] on 2026-06-05. Place TWO funding events inside it
    # plus an off-grid one, all of which must be accrued (not just a single 8h value).
    funding = _funding_rows(
        "AAA",
        [
            ("2026-06-05T08:00:00", 0.0001),  # == window start, excluded
            ("2026-06-05T12:00:00", 0.0002),  # inside (off the 8h grid)
            ("2026-06-05T16:00:00", 0.0003),  # inside (window end)
        ],
    )
    out, _, _ = _setup(
        tmp_path, [[], ["AAA"], ["AAA"], [], [], []], funding=funding
    )
    funding_rows = _read(out / "paper_funding.jsonl")
    t2 = next(f for f in funding_rows if f["bar_ts"] == TS[2])
    assert t2["funding_events"] == 2  # 12:00 and 16:00, NOT the excluded 08:00 start
    assert abs(t2["funding_rate"] - (0.0002 + 0.0003)) < 1e-12
    assert abs(t2["funding_amount"] - t2["notional_usd"] * (0.0002 + 0.0003)) < 1e-6
    assert t2["rate_available"] is True
    assert reconcile(out) == []


# ---------------------------------------------------- hardening: baseline labeling


def test_receipt_and_summary_label_fixed_notional_baseline(tmp_path):
    out, _, summary = _setup(tmp_path, [[], ["AAA"], ["AAA"], [], [], []])
    assert summary["baseline_label"] == "fixed_notional_active_symbols_paper_v1"
    # the disclaimer must deny that a green paper result validates the V2 volnorm edge
    assert "does NOT validate the V2" in summary["disclaimer"]

    receipt = (out / "paper_receipt.md").read_text()
    assert "fixed_notional_active_symbols_paper_v1" in receipt
    assert "NOT V2 volnorm live/PnL approval" in receipt

    config = load_config(out)
    assert config["baseline_label"] == "fixed_notional_active_symbols_paper_v1"
