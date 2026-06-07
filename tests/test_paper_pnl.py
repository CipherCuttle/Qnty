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


def _obs_row(ts, active, bar_index=0):
    """A full per_bar_obs row carrying the complete observer contract."""
    return {
        "timestamp": ts,
        "bar_index": bar_index,
        "active_symbols": list(active),
        "portfolio_heat": 0.0,
        "heat_cap_triggered": False,
        "weighted_return": 0.0,
    }


def _obs(active_by_bar):
    """active_by_bar: list of active_symbols lists aligned with TS."""
    return [
        _obs_row(ts, active, i)
        for i, (ts, active) in enumerate(zip(TS, active_by_bar))
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
    out, _, summary = _setup(
        tmp_path, [[], ["AAA"], ["AAA"], [], [], []], funding=_empty_funding_df()
    )
    funding = _read(out / "paper_funding.jsonl")
    assert funding  # accruals happened while held
    assert all(f["rate_available"] is False for f in funding)
    assert all(f["funding_amount"] == 0.0 for f in funding)
    trades = _read(out / "paper_trades.jsonl")
    assert trades[0]["funding"] == 0.0
    # funding gap exposure must be visible in the summary, not only the receipt (Blocker 6)
    assert summary["funding_gap"] is True
    assert summary["funding_gap_count"] == len(funding)
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
    obs = _obs([[], ["AAA"], ["AAA"], [], []]) + [_obs_row("2026-06-06T17:00:00", [], 5)]
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


# Held-interval funding. Position: entry signal T1 -> entry FILL at T2 open
# (2026-06-05T16:00); exit signal T4 -> exit FILL at T5 open (2026-06-06T16:00). The actual
# holding interval is (T2, T5]. Funding must be accrued over exactly that interval — never
# before the entry fill, and through the T+1 exit fill (Blocker 1 / schema § 11).
_HELD_FUNDING = [
    ("2026-06-05T12:00:00", 0.0001),  # BEFORE entry fill (in (T1,T2]) -> NOT charged
    ("2026-06-05T20:00:00", 0.0001),  # in (T2,T3]  -> charged at T3 (off-grid)
    ("2026-06-06T00:00:00", 0.0001),  # = T3        -> charged at T3
    ("2026-06-06T04:00:00", 0.0001),  # in (T3,T4]  -> charged at T4 (off-grid)
    ("2026-06-06T08:00:00", 0.0001),  # = T4        -> charged at T4
    ("2026-06-06T12:00:00", 0.0001),  # in (T4,T5]  -> charged at exit stub (off-grid)
    ("2026-06-06T16:00:00", 0.0001),  # = T5 fill   -> charged at exit stub
    ("2026-06-06T20:00:00", 0.0001),  # AFTER exit fill -> NOT charged
]
_HELD_ACTIVE = [[], ["AAA"], ["AAA"], ["AAA"], [], []]


def test_funding_event_before_entry_fill_not_charged(tmp_path):
    out, _, _ = _setup(tmp_path, _HELD_ACTIVE, funding=_funding_rows("AAA", _HELD_FUNDING))
    funding_rows = _read(out / "paper_funding.jsonl")
    # The position's first snapshot is the entry-fill bar T2 (16:00). The 12:00 event lands
    # in (T1, T2] but BEFORE the position exists -> no funding row may cover it.
    assert all(f["window_start"] >= TS[2] for f in funding_rows)
    # No accrual is attributed at/before the entry fill bar T2.
    assert not any(f["bar_ts"] == TS[2] for f in funding_rows)
    assert reconcile(out) == []


def test_funding_after_entry_and_before_exit_is_charged(tmp_path):
    out, _, _ = _setup(tmp_path, _HELD_ACTIVE, funding=_funding_rows("AAA", _HELD_FUNDING))
    funding_rows = _read(out / "paper_funding.jsonl")
    # T3 regular window (T2, T3] captures the 20:00 (off-grid) + 00:00 events.
    t3 = next(f for f in funding_rows if f["bar_ts"] == TS[3] and not f["funding_id"].endswith("|exit"))
    assert t3["funding_events"] == 2
    assert t3["rate_available"] is True
    assert reconcile(out) == []


def test_funding_between_exit_signal_and_fill_is_charged(tmp_path):
    out, _, _ = _setup(tmp_path, _HELD_ACTIVE, funding=_funding_rows("AAA", _HELD_FUNDING))
    funding_rows = _read(out / "paper_funding.jsonl")
    # The exit-tail stub covers (exit_signal=T4, exit_fill=T5]; events at 12:00 and 16:00
    # on 2026-06-06 are still held and must be charged even though the position is "leaving".
    stub = next(f for f in funding_rows if f["funding_id"].endswith("|exit"))
    assert stub["window_start"] == TS[4]
    assert stub["window_end"] == TS[5]
    assert stub["funding_events"] == 2
    assert stub["rate_available"] is True
    assert reconcile(out) == []


def test_funding_multiple_offgrid_events_summed_over_held_interval(tmp_path):
    out, _, _ = _setup(tmp_path, _HELD_ACTIVE, funding=_funding_rows("AAA", _HELD_FUNDING))
    funding_rows = _read(out / "paper_funding.jsonl")
    trades = _read(out / "paper_trades.jsonl")
    # Exactly the six in-interval events (1h/4h/off-grid) are summed; the two outside the
    # actual holding interval (before entry fill, after exit fill) are excluded.
    assert sum(f["funding_events"] for f in funding_rows) == 6
    # Long pays positive funding -> sign reduces net PnL; funding charged is positive.
    assert trades[0]["funding"] > 0
    assert abs(trades[0]["funding"] - sum(f["funding_amount"] for f in funding_rows)) < 1e-9
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


def test_provenance_includes_baseline_label(tmp_path):
    out, _, _ = _setup(tmp_path, [[], ["AAA"], ["AAA"], [], [], []])
    prov = json.loads((out / "paper_provenance.json").read_text())
    # every provenance artifact must carry the baseline label (Blocker 6 / schema § 8)
    assert prov["baseline_label"] == "fixed_notional_active_symbols_paper_v1"
    log = _read(out / "paper_provenance_log.jsonl")
    assert log and all(r.get("baseline_label") for r in log)


# --------------------------------------------------- hardening: config contract (Blocker 2)


def test_old_engine_config_fails_contract(tmp_path):
    out = tmp_path / "paper"
    out.mkdir(parents=True)
    # An old 0.1.0-style config: validated hash present but missing baseline_label/freshness
    # and a stale engine_version. It must fail loudly and demand archive/re-init.
    old = {
        "schema_version": 1,
        "engine_version": "0.1.0",
        "forward_start_ts": TS[0],
        "initial_equity_usd": 10000.0,
        "notional_usd": 1000.0,
    }
    (out / "paper_config.json").write_text(json.dumps(old), encoding="utf-8")
    with pytest.raises(ValueError) as exc:
        load_config(out)
    assert "re-init" in str(exc.value).lower() or "archive" in str(exc.value).lower()


def test_config_wrong_engine_version_fails(tmp_path):
    out = tmp_path / "paper"
    out.mkdir(parents=True)
    config = build_config(forward_start_ts=TS[0])
    config["engine_version"] = "0.1.0"  # mismatched engine
    config["config_hash"] = __import__("quantbot.paper.config", fromlist=["config_hash"]).config_hash(config)
    (out / "paper_config.json").write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(out)


# ------------------------------------------------- hardening: freshness depth (Blocker 3)


def _run(out, fwd, now=NOW):
    return run_once(
        output_dir=out,
        forward_obs_dir=fwd,
        bars_by_symbol={"AAA": _bars(AAA_PRICES)},
        funding_df=_funding_df(),
        now=now,
    )


def test_malformed_json_observation_log_aborts(tmp_path):
    out = tmp_path / "paper"
    fwd = tmp_path / "fwd"
    fwd.mkdir(parents=True, exist_ok=True)
    write_config_once(build_config(forward_start_ts=TS[0]), output_dir=out)
    (fwd / "observation_log.json").write_text("{ this is not valid json", encoding="utf-8")
    summary = _run(out, fwd)
    assert summary["status"] == "ABORTED"
    assert summary["abort_code"] == "MALFORMED_OBSERVATION_LOG"
    assert _no_ledger_rows(out)


def test_null_active_symbols_aborts(tmp_path):
    out = tmp_path / "paper"
    fwd = tmp_path / "fwd"
    fwd.mkdir(parents=True, exist_ok=True)
    write_config_once(build_config(forward_start_ts=TS[0]), output_dir=out)
    rows = _obs([[], ["AAA"], ["AAA"]])
    rows[1]["active_symbols"] = None  # null -> must NOT be interpreted as []/FLAT
    (fwd / "observation_log.json").write_text(json.dumps({"per_bar_obs": rows}), encoding="utf-8")
    summary = _run(out, fwd)
    assert summary["status"] == "ABORTED"
    assert summary["abort_code"] == "MALFORMED_OBSERVATION_LOG"
    assert _no_ledger_rows(out)


def test_missing_active_symbols_aborts(tmp_path):
    out = tmp_path / "paper"
    fwd = tmp_path / "fwd"
    fwd.mkdir(parents=True, exist_ok=True)
    write_config_once(build_config(forward_start_ts=TS[0]), output_dir=out)
    rows = _obs([[], ["AAA"], ["AAA"]])
    del rows[1]["active_symbols"]  # missing -> must abort, never default to FLAT
    (fwd / "observation_log.json").write_text(json.dumps({"per_bar_obs": rows}), encoding="utf-8")
    summary = _run(out, fwd)
    assert summary["status"] == "ABORTED"
    assert summary["abort_code"] == "MALFORMED_OBSERVATION_LOG"
    assert _no_ledger_rows(out)


def test_earlier_off_grid_row_aborts(tmp_path):
    # An off-grid row EARLIER in the consumed stream (not just the final row) must abort.
    out = tmp_path / "paper"
    fwd = tmp_path / "fwd"
    fwd.mkdir(parents=True, exist_ok=True)
    write_config_once(build_config(forward_start_ts=TS[0]), output_dir=out)
    rows = [_obs_row(TS[0], [], 0), _obs_row("2026-06-05T01:00:00", [], 1), _obs_row(TS[1], [], 2)]
    (fwd / "observation_log.json").write_text(json.dumps({"per_bar_obs": rows}), encoding="utf-8")
    summary = _run(out, fwd)
    assert summary["status"] == "ABORTED"
    assert summary["abort_code"] == "OFF_GRID_BAR"
    assert _no_ledger_rows(out)


def test_future_observation_aborts(tmp_path):
    # A future-dated (2099) on-grid bar must abort: a negative age must not pass as fresh.
    out = tmp_path / "paper"
    fwd = tmp_path / "fwd"
    fwd.mkdir(parents=True, exist_ok=True)
    write_config_once(build_config(forward_start_ts=TS[0]), output_dir=out)
    rows = _obs([[], ["AAA"]]) + [_obs_row("2099-01-01T00:00:00", [], 2)]
    (fwd / "observation_log.json").write_text(json.dumps({"per_bar_obs": rows}), encoding="utf-8")
    summary = _run(out, fwd)
    assert summary["status"] == "ABORTED"
    assert summary["abort_code"] == "FUTURE_OBSERVATION"
    assert _no_ledger_rows(out)


def test_duplicate_observation_timestamp_aborts(tmp_path):
    out = tmp_path / "paper"
    fwd = tmp_path / "fwd"
    fwd.mkdir(parents=True, exist_ok=True)
    write_config_once(build_config(forward_start_ts=TS[0]), output_dir=out)
    rows = [_obs_row(TS[0], [], 0), _obs_row(TS[1], ["AAA"], 1), _obs_row(TS[1], [], 2)]
    (fwd / "observation_log.json").write_text(json.dumps({"per_bar_obs": rows}), encoding="utf-8")
    summary = _run(out, fwd)
    assert summary["status"] == "ABORTED"
    assert summary["abort_code"] == "DUPLICATE_OBSERVATION_TS"
    assert _no_ledger_rows(out)


def test_malformed_heartbeat_fails_closed(tmp_path):
    out = tmp_path / "paper"
    fwd = tmp_path / "fwd"
    fwd.mkdir(parents=True, exist_ok=True)
    write_config_once(build_config(forward_start_ts=TS[0]), output_dir=out)
    _write_obs(fwd, _obs([[], ["AAA"], ["AAA"], [], [], []]))
    # A present-but-malformed heartbeat must abort, not be silently treated as unavailable.
    (fwd / "bar_decisions.jsonl").write_text("{ not json\n", encoding="utf-8")
    summary = _run(out, fwd)
    assert summary["status"] == "ABORTED"
    assert summary["abort_code"] == "MALFORMED_HEARTBEAT"
    assert _no_ledger_rows(out)


# -------------------------------------------- hardening: snapshot crash safety (Blocker 4/5)


def test_full_row_change_triggers_divergence(tmp_path):
    # Divergence must be measured over the FULL consumed source row, not a hand-picked
    # subset: adding/changing ANY field of an already-consumed bar must abort.
    out, fwd, _ = _setup(tmp_path, [[], ["AAA"], ["AAA"], [], [], []])
    digests_before = {n: sha256_file(out / n) for n in _LEDGER_FILES}
    rows = _obs([[], ["AAA"], ["AAA"], [], [], []])
    rows[2]["extra_observer_field"] = 123  # field outside the old selected-fields digest
    (fwd / "observation_log.json").write_text(json.dumps({"per_bar_obs": rows}), encoding="utf-8")
    summary = _run(out, fwd)
    assert summary["status"] == "ABORTED"
    assert summary["abort_code"] == "SIGNAL_SNAPSHOT_DIVERGENCE"
    assert {n: sha256_file(out / n) for n in _LEDGER_FILES} == digests_before


def test_orphan_snapshot_detected_by_reconcile(tmp_path):
    # Simulate a crash that committed a snapshot without its equity row. Reconcile must NOT
    # return [] — an orphan snapshot can never report success (Blocker 4).
    from quantbot.paper import ledger, snapshots

    out, _, _ = _setup(tmp_path, [[], ["AAA"], ["AAA"], [], [], []])
    assert reconcile(out) == []  # clean baseline
    orphan_ts = "2026-06-07T00:00:00"
    ledger.append_rows(
        out / snapshots.SNAPSHOT_FILE,
        [{"snapshot_id": snapshots.snapshot_id(orphan_ts), "bar_ts": orphan_ts, "backfill": False}],
    )
    failures = reconcile(out)
    assert any("orphan" in f.lower() for f in failures)


def test_no_snapshot_without_equity_in_clean_run(tmp_path):
    out, _, _ = _setup(tmp_path, [[], ["AAA"], ["AAA"], [], [], []])
    snaps = _read(out / "paper_signal_snapshots.jsonl")
    equity_ts = {e["bar_ts"] for e in _read(out / "paper_equity.jsonl")}
    # every committed snapshot has its equity row. The crash-safe order is snapshot-FIRST,
    # then the bar accounting rows (incl. equity), then the state watermark LAST; a clean run
    # therefore always lands the equity row for each frozen snapshot.
    assert all(s["bar_ts"] in equity_ts for s in snaps)


# -------------------------------------------------------- hardening: CLI abort (Blocker 6)


def test_cli_handles_abort_without_keyerror(tmp_path):
    import os
    import subprocess
    import sys

    repo_root = Path(__file__).resolve().parents[1]
    out = tmp_path / "paper"
    fwd = tmp_path / "fwd"
    fwd.mkdir(parents=True, exist_ok=True)
    write_config_once(build_config(forward_start_ts=TS[0]), output_dir=out)
    # no observation_log.json -> the run aborts at the freshness gate
    proc = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "qnty-paper-accounting.py"),
            "--output-dir", str(out),
            "--forward-obs-dir", str(fwd),
        ],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
        env={**os.environ, "PYTHONPATH": str(repo_root)},
    )
    assert proc.returncode == 2, proc.stderr
    assert "ABORTED" in proc.stdout
    assert "run complete" not in proc.stdout
    assert "KeyError" not in proc.stderr
    assert "bars_elapsed" not in proc.stderr


# ==========================================================================================
# ADVERSARIAL REGRESSION — Codex reproductions of the e9bd67b rejection. Each test below
# reproduces an unsafe path Codex found; none is a happy path.
# ==========================================================================================

from quantbot.paper import freshness as _freshness
from quantbot.paper import ledger as _ledger
from quantbot.paper import snapshots as _snapshots
from quantbot.paper.config import ConfigContractError, config_hash

_DEFAULT_FRESH = {
    "bar_interval_hours": 8,
    "max_bar_staleness_hours": 24,
    "heartbeat_max_age_hours": 24,
}


def _check(tmp_path, per_bar, now=NOW, forward_start_ts=TS[0], heartbeat_lines=None):
    """Call the freshness gate directly over a written observation file."""
    fwd = tmp_path / "fwd"
    fwd.mkdir(parents=True, exist_ok=True)
    obs_path = fwd / "observation_log.json"
    obs_log = {"per_bar_obs": per_bar}
    obs_path.write_text(json.dumps(obs_log), encoding="utf-8")
    if heartbeat_lines is not None:
        (fwd / "bar_decisions.jsonl").write_text(heartbeat_lines, encoding="utf-8")
    return _freshness.check_freshness(
        obs_path, obs_log, fwd, now, _DEFAULT_FRESH, forward_start_ts=forward_start_ts
    )


# ---- Blocker 1: per-bar atomic commit / partial ledger can't reconcile clean -------------


def test_orphan_fill_without_snapshot_fails_reconcile(tmp_path):
    # Simulate a crash after fills were written but before the (snapshot-first) snapshot/
    # equity/state — a partial bar. Reconcile MUST NOT return [].
    out = tmp_path / "paper"
    out.mkdir(parents=True)
    write_config_once(build_config(forward_start_ts=TS[0]), output_dir=out)
    _ledger.append_rows(
        out / "paper_fills.jsonl",
        [
            {
                "fill_id": "deadbeefdeadbeef",
                "bar_commit_id": "0000aaaa1111bbbb",
                "signal_bar_ts": TS[1],
                "fill_ts": TS[2],
                "symbol": "AAA",
                "side": "BUY",
                "kind": "entry",
                "qty": 1.0,
                "fill_price": 100.0,
                "open_price": 100.0,
                "fee": 0.0,
                "backfill": False,
            }
        ],
    )
    failures = reconcile(out)
    assert failures, "a fill with no consumed-signal snapshot must fail reconcile"
    assert any("snapshot" in f.lower() for f in failures)


def test_changed_source_after_partial_commit_aborts_next_run(tmp_path):
    # A bar's snapshot is frozen FIRST. Simulate a crash that froze the snapshot (and rolled
    # the watermark back) but never finished the bar; the rolling observer then recomputes
    # the same bar to different values. The next run MUST abort on divergence, not continue.
    out, fwd, _ = _setup(tmp_path, [[], ["AAA"], ["AAA"], [], [], []])
    assert reconcile(out) == []

    # Crash simulation: drop the last consumed bar's equity/fills (partial) and roll the
    # watermark back, but KEEP its frozen snapshot.
    equity = _read(out / "paper_equity.jsonl")
    last_bar = equity[-1]["bar_ts"]
    kept_equity = [e for e in equity if e["bar_ts"] != last_bar]
    (out / "paper_equity.jsonl").write_text(
        "".join(json.dumps(e, sort_keys=True) + "\n" for e in kept_equity), encoding="utf-8"
    )
    state = json.loads((out / "paper_position_state.json").read_text())
    state["watermark_bar_ts"] = kept_equity[-1]["bar_ts"] if kept_equity else ""
    (out / "paper_position_state.json").write_text(json.dumps(state), encoding="utf-8")

    # Source for the already-snapshotted last bar is recomputed differently.
    diverged = _obs([[], ["AAA"], ["AAA"], [], [], []])
    for row in diverged:
        if row["timestamp"] == last_bar:
            row["weighted_return"] = 0.123456  # recomputed value
    (fwd / "observation_log.json").write_text(json.dumps({"per_bar_obs": diverged}), encoding="utf-8")

    summary = _run(out, fwd)
    assert summary["status"] == "ABORTED"
    assert summary["abort_code"] == "SIGNAL_SNAPSHOT_DIVERGENCE"


def test_full_bar_commit_reconciles_and_ids_agree(tmp_path):
    # A successful full bar commit: every accounting row carries the SAME bar_commit_id as
    # its frozen snapshot, and reconcile passes.
    out, _, _ = _setup(tmp_path, [[], ["AAA"], ["AAA"], [], [], []])
    assert reconcile(out) == []
    snaps = _read(out / "paper_signal_snapshots.jsonl")
    commit_by_bar = {s["bar_ts"]: s["bar_commit_id"] for s in snaps}
    assert all(commit_by_bar.values())  # every snapshot carries a bar_commit_id
    for e in _read(out / "paper_equity.jsonl"):
        assert e["bar_commit_id"] == commit_by_bar[e["bar_ts"]]
    for f in _read(out / "paper_fills.jsonl"):
        assert f["bar_commit_id"] == commit_by_bar[f["signal_bar_ts"]]


def test_disagreeing_bar_commit_id_fails_reconcile(tmp_path):
    # If an accounting row's bar_commit_id disagrees with its snapshot (e.g. a stale row from
    # a different source version retained across a crash), reconcile MUST fail.
    out, _, _ = _setup(tmp_path, [[], ["AAA"], ["AAA"], [], [], []])
    assert reconcile(out) == []
    equity = _read(out / "paper_equity.jsonl")
    equity[-1]["bar_commit_id"] = "tamperedcommit00"
    (out / "paper_equity.jsonl").write_text(
        "".join(json.dumps(e, sort_keys=True) + "\n" for e in equity), encoding="utf-8"
    )
    failures = reconcile(out)
    assert any("bar_commit_id" in f for f in failures)


def test_idempotent_retry_no_duplicate_rows(tmp_path):
    # Retrying a fully committed bar appends nothing (no duplicate fills/snapshots/equity).
    out, fwd, _ = _setup(tmp_path, [[], ["AAA"], ["AAA"], [], [], []])
    counts_before = {
        n: len(_read(out / n))
        for n in ("paper_fills.jsonl", "paper_equity.jsonl", "paper_signal_snapshots.jsonl")
    }
    _run(out, fwd)
    counts_after = {n: len(_read(out / n)) for n in counts_before}
    assert counts_before == counts_after
    assert reconcile(out) == []


# ---- Blocker 2: freshness must validate the whole file, not just consumed rows -----------

# forward_start_ts in the FUTURE -> every TS bar is pre-forward (zero consumed).
_FUTURE_START = "2026-06-10T00:00:00"


def test_pre_forward_off_grid_row_aborts(tmp_path):
    rows = _obs([[], ["AAA"], ["AAA"], [], []]) + [_obs_row("2026-06-06T17:00:00", [], 5)]
    res = _check(tmp_path, rows, forward_start_ts=_FUTURE_START)
    assert res.aborted and res.code == "OFF_GRID_BAR"


def test_pre_forward_duplicate_timestamp_aborts(tmp_path):
    rows = [_obs_row(TS[0], [], 0), _obs_row(TS[1], ["AAA"], 1), _obs_row(TS[1], [], 2)]
    res = _check(tmp_path, rows, forward_start_ts=_FUTURE_START)
    assert res.aborted and res.code == "DUPLICATE_OBSERVATION_TS"


def test_pre_forward_stale_latest_bar_aborts(tmp_path):
    # All rows pre-forward AND the observer is dead (latest bar far older than staleness).
    stale_now = NOW + timedelta(days=5)
    res = _check(tmp_path, _obs([[], ["AAA"], ["AAA"], [], [], []]), now=stale_now, forward_start_ts=_FUTURE_START)
    assert res.aborted and res.code == "STALE_OBSERVATION"


def test_pre_forward_malformed_heartbeat_aborts(tmp_path):
    res = _check(
        tmp_path,
        _obs([[], ["AAA"], ["AAA"], [], [], []]),
        forward_start_ts=_FUTURE_START,
        heartbeat_lines="{ not json\n",
    )
    assert res.aborted and res.code == "MALFORMED_HEARTBEAT"


def test_zero_consumed_with_fresh_observation_is_controlled_no_op(tmp_path):
    # Clean, fresh, on-grid file with nothing past forward_start_ts -> controlled no-op, NOT
    # a normal misleading OK and NOT an abort.
    res = _check(tmp_path, _obs([[], ["AAA"], ["AAA"], [], [], []]), forward_start_ts=_FUTURE_START)
    assert res.ok is True
    assert res.code == "NO_ELIGIBLE_BARS_YET"
    # end-to-end: run_once is a controlled no-op — clearly labeled NO_ELIGIBLE_BARS_YET (NOT
    # a misleading OK), writes zero ledger rows, creates NO state/watermark, reconcile passes.
    out = tmp_path / "paper"
    fwd = tmp_path / "fwd"
    fwd.mkdir(parents=True, exist_ok=True)
    write_config_once(build_config(forward_start_ts=_FUTURE_START), output_dir=out)
    _write_obs(fwd, _obs([[], ["AAA"], ["AAA"], [], [], []]))
    summary = _run(out, fwd)
    assert summary["status"] == "NO_ELIGIBLE_BARS_YET"
    assert summary["status"] != "OK"
    assert summary["bars_elapsed"] == 0
    assert _no_ledger_rows(out)
    # no position state/watermark created or mutated
    assert not (out / "paper_position_state.json").exists()
    assert reconcile(out) == []


# ---- Blocker 3: malformed freshness inputs must not crash --------------------------------


def test_heartbeat_empty_array_row_fails_closed(tmp_path):
    # `[]` is valid JSON but not an object -> would AttributeError on .get; must fail closed.
    res = _check(tmp_path, _obs([[], ["AAA"], ["AAA"], [], [], []]), heartbeat_lines="[]\n")
    assert res.aborted and res.code == "MALFORMED_HEARTBEAT"


def test_heartbeat_object_missing_fields_fails_closed(tmp_path):
    res = _check(
        tmp_path,
        _obs([[], ["AAA"], ["AAA"], [], [], []]),
        heartbeat_lines=json.dumps({"bar_processed_at": "2026-06-06T16:00:00Z"}) + "\n",
    )
    assert res.aborted and res.code == "MALFORMED_HEARTBEAT"


def test_heartbeat_future_timestamp_fails_closed(tmp_path):
    future_hb = json.dumps({"bar_processed_at": "2099-01-01T00:00:00Z", "commit_sha": "abc"})
    res = _check(
        tmp_path, _obs([[], ["AAA"], ["AAA"], [], [], []]), heartbeat_lines=future_hb + "\n"
    )
    assert res.aborted and res.code == "FUTURE_HEARTBEAT"


def test_active_symbols_list_of_objects_fails_closed(tmp_path):
    rows = _obs([[], ["AAA"], ["AAA"], [], [], []])
    rows[1]["active_symbols"] = [{}]  # list, but not list of strings
    res = _check(tmp_path, rows)
    assert res.aborted and res.code == "MALFORMED_OBSERVATION_LOG"


def test_active_symbols_list_of_ints_fails_closed(tmp_path):
    rows = _obs([[], ["AAA"], ["AAA"], [], [], []])
    rows[1]["active_symbols"] = [123]
    res = _check(tmp_path, rows)
    assert res.aborted and res.code == "MALFORMED_OBSERVATION_LOG"


def test_active_symbols_valid_string_list_passes(tmp_path):
    rows = _obs([[], ["BTCUSDT"], ["BTCUSDT"], [], [], []])
    res = _check(tmp_path, rows)
    assert res.ok and res.code == "OK"


def test_valid_heartbeat_with_required_fields_passes(tmp_path):
    hb = json.dumps({"bar_processed_at": "2026-06-06T16:00:00Z", "commit_sha": "abc123"})
    res = _check(tmp_path, _obs([[], ["AAA"], ["AAA"], [], [], []]), heartbeat_lines=hb + "\n")
    assert res.ok and res.code == "OK"


# ---- Blocker 4: config contract must be exact -------------------------------------------


def test_config_future_schema_version_rejected(tmp_path):
    out = tmp_path / "paper"
    out.mkdir(parents=True)
    config = build_config(forward_start_ts=TS[0])
    config["schema_version"] = 2  # unknown/future schema -> fail closed (no migration)
    config["config_hash"] = config_hash(config)
    (out / "paper_config.json").write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(ConfigContractError):
        load_config(out)


def test_config_wrong_baseline_label_rejected(tmp_path):
    out = tmp_path / "paper"
    out.mkdir(parents=True)
    config = build_config(forward_start_ts=TS[0])
    config["baseline_label"] = "not_the_fixed_baseline"
    config["config_hash"] = config_hash(config)
    (out / "paper_config.json").write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(ConfigContractError):
        load_config(out)


def test_config_missing_freshness_rejected(tmp_path):
    out = tmp_path / "paper"
    out.mkdir(parents=True)
    config = build_config(forward_start_ts=TS[0])
    del config["freshness"]
    config["config_hash"] = config_hash(config)
    (out / "paper_config.json").write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(ConfigContractError):
        load_config(out)


# ---- Blocker 5: stale-config CLI must abort cleanly (no traceback), matching the runbook --


def test_cli_stale_config_aborts_cleanly_with_reinit_guidance(tmp_path):
    import os
    import subprocess
    import sys

    repo_root = Path(__file__).resolve().parents[1]
    out = tmp_path / "paper"
    fwd = tmp_path / "fwd"
    out.mkdir(parents=True)
    fwd.mkdir(parents=True, exist_ok=True)
    # An old 0.1.0-style config that fails the load contract.
    old = {
        "schema_version": 1,
        "engine_version": "0.1.0",
        "forward_start_ts": TS[0],
        "initial_equity_usd": 10000.0,
        "notional_usd": 1000.0,
    }
    (out / "paper_config.json").write_text(json.dumps(old), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "qnty-paper-accounting.py"),
            "--output-dir", str(out),
            "--forward-obs-dir", str(fwd),
        ],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
        env={**os.environ, "PYTHONPATH": str(repo_root)},
    )
    # Clean documented exit (3), NOT a traceback / exit 1.
    assert proc.returncode == 3, (proc.returncode, proc.stderr)
    assert "Traceback" not in proc.stderr
    assert "ConfigContractError" not in proc.stderr
    assert "ABORTED" in proc.stdout
    # Operator guidance: archive + re-init + fresh future boundary.
    assert "archive" in proc.stdout.lower()
    assert "forward-start-ts" in proc.stdout.lower() or "forward_start" in proc.stdout.lower()
    assert "future" in proc.stdout.lower()
    # No ledger / state / summary rows written.
    assert _no_ledger_rows(out)
    assert not (out / "paper_position_state.json").exists()
    assert not (out / "paper_pnl_summary.json").exists()


# ==========================================================================================
# ADVERSARIAL REGRESSION v2 — Codex reproductions of the 0a8a815 rejection. Each test below
# reproduces an unsafe path Codex found in the "evidence atomicity" commit; none is a happy
# path. A run may only emit OK if: freshness passed, config contract passed, no partial/corrupt
# existing ledger, new mutations have matching snapshots, reconcile passes after mutation, and
# the state/watermark write is last. If any fails -> fail closed.
# ==========================================================================================


def _recent_grid_bars(n: int = 3) -> list[str]:
    """Most recent `n` on-grid 8h bars at/just-before wall-clock now (UTC), oldest first.

    Used by CLI subprocess tests where `now` is the real wall clock (not injectable): the bars
    must be fresh (<= 24h old) and not future, so they pass the freshness gate end-to-end.
    """
    now = datetime.now(timezone.utc)
    latest = now.replace(hour=(now.hour // 8) * 8, minute=0, second=0, microsecond=0)
    bars = sorted(latest - timedelta(hours=8 * i) for i in range(n))
    return [b.strftime("%Y-%m-%dT%H:%M:%S") for b in bars]


def _future_grid_boundary(days_ahead: int = 5) -> str:
    """An on-grid 8h boundary `days_ahead` days after the latest recent grid bar (future)."""
    latest = datetime.strptime(_recent_grid_bars(1)[0], "%Y-%m-%dT%H:%M:%S")
    return (latest + timedelta(days=days_ahead)).strftime("%Y-%m-%dT%H:%M:%S")


def _orphan_fill_row(signal_bar_ts, fill_ts, commit_id="aaaa0000aaaa0000"):
    """A fill with no consumed-signal snapshot — a partial bar left by a simulated crash."""
    return {
        "fill_id": "deadbeefdeadbeef",
        "bar_commit_id": commit_id,
        "signal_bar_ts": signal_bar_ts,
        "fill_ts": fill_ts,
        "symbol": "AAA",
        "side": "BUY",
        "kind": "entry",
        "qty": 1.0,
        "fill_price": 100.0,
        "open_price": 100.0,
        "fee": 0.0,
        "backfill": False,
    }


# ---- Blocker 1: runner must reconcile BEFORE publishing OK --------------------------------


def test_orphan_fill_source_a_then_source_b_retry_fails_closed_not_ok(tmp_path):
    # EXACT Codex case: an orphan fill from source row A (a crash left a fill with no
    # snapshot/equity/state); the rolling observer recomputes to source B; the run retries.
    # The run MUST NOT publish OK — reconcile runs BEFORE OK, the watermark does not advance,
    # and the reconcile errors are surfaced in summary/receipt/provenance.
    out = tmp_path / "paper"
    fwd = tmp_path / "fwd"
    fwd.mkdir(parents=True, exist_ok=True)
    write_config_once(build_config(forward_start_ts=TS[0]), output_dir=out)

    # Orphan entry fill for bar TS[1] tagged with a bar_commit_id from "source row A".
    _ledger.append_rows(out / "paper_fills.jsonl", [_orphan_fill_row(TS[1], TS[2])])

    # Source B: a fresh observation set (recomputed). The leftover orphan fill from A can never
    # reconcile clean against B's frozen snapshots.
    _write_obs(fwd, _obs([[], ["AAA"], ["AAA"], [], [], []]))
    summary = _run(out, fwd)

    # summary is NOT OK
    assert summary["status"] != "OK"
    assert summary["status"] == "CORRUPT_LEDGER"
    # reconcile errors surfaced in the summary ...
    assert summary.get("reconcile_failure_count", 0) >= 1
    assert summary.get("reconcile_failures")
    # ... and in the receipt ...
    receipt = (out / "paper_receipt.md").read_text()
    assert "CORRUPT_LEDGER" in receipt
    assert any(("snapshot" in ln.lower() or "bar_commit_id" in ln) for ln in receipt.splitlines())
    # ... and in the provenance.
    prov = json.loads((out / "paper_provenance.json").read_text())
    assert prov["status"] == "CORRUPT_LEDGER"
    assert prov.get("reconcile_failure_count", 0) >= 1
    # state/watermark did NOT advance (no state file written this run).
    assert not (out / "paper_position_state.json").exists()


def test_cli_corrupt_ledger_exits_nonzero(tmp_path):
    # CLI must exit non-zero (4) and not say "run complete" when reconcile fails. Uses
    # wall-clock-fresh bars so the freshness gate passes and the run reaches reconcile.
    import os
    import subprocess
    import sys

    repo_root = Path(__file__).resolve().parents[1]
    out = tmp_path / "paper"
    fwd = tmp_path / "fwd"
    fwd.mkdir(parents=True, exist_ok=True)
    bars = _recent_grid_bars(3)
    write_config_once(build_config(forward_start_ts=bars[0]), output_dir=out)
    # Orphan fill for the middle fresh bar; AAA has no real OHLCV so the bar defers and never
    # produces a snapshot -> the orphan fill can never reconcile clean.
    _ledger.append_rows(out / "paper_fills.jsonl", [_orphan_fill_row(bars[1], bars[2])])
    rows = [_obs_row(bars[0], [], 0), _obs_row(bars[1], ["AAA"], 1), _obs_row(bars[2], ["AAA"], 2)]
    (fwd / "observation_log.json").write_text(json.dumps({"per_bar_obs": rows}), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "qnty-paper-accounting.py"),
            "--output-dir", str(out),
            "--forward-obs-dir", str(fwd),
        ],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
        env={**os.environ, "PYTHONPATH": str(repo_root)},
    )
    assert proc.returncode == 4, (proc.returncode, proc.stdout, proc.stderr)
    assert "CORRUPT_LEDGER" in proc.stdout
    assert "run complete" not in proc.stdout
    assert not (out / "paper_position_state.json").exists()


# ---- Blocker 2: bar_commit_id mandatory on every committed-bar row ------------------------


def _rewrite_jsonl(path: Path, rows):
    path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8")


_COMMIT_ROW_FILES = [
    "paper_signal_snapshots.jsonl",
    "paper_fills.jsonl",
    "paper_trades.jsonl",
    "paper_funding.jsonl",
    "paper_positions.jsonl",
    "paper_equity.jsonl",
]


def test_reconcile_fails_when_all_bar_commit_ids_missing(tmp_path):
    # EXACT Codex case: strip bar_commit_id from EVERY snapshot AND accounting row.
    # `None == None` must NOT pass as agreement; reconcile must fail.
    out, _, _ = _setup(tmp_path, [[], ["AAA"], ["AAA"], [], [], []])
    assert reconcile(out) == []
    for name in _COMMIT_ROW_FILES:
        rows = _read(out / name)
        for r in rows:
            r.pop("bar_commit_id", None)
        _rewrite_jsonl(out / name, rows)
    failures = reconcile(out)
    assert failures, "all bar_commit_id missing must fail reconcile"
    assert any("bar_commit_id" in f for f in failures)


def test_reconcile_fails_when_one_bar_commit_id_missing(tmp_path):
    out, _, _ = _setup(tmp_path, [[], ["AAA"], ["AAA"], [], [], []])
    assert reconcile(out) == []
    equity = _read(out / "paper_equity.jsonl")
    equity[-1].pop("bar_commit_id", None)  # a single row loses its id
    _rewrite_jsonl(out / "paper_equity.jsonl", equity)
    failures = reconcile(out)
    assert any("bar_commit_id" in f for f in failures)


def test_reconcile_fails_when_snapshot_bar_commit_id_empty_or_malformed(tmp_path):
    out, _, _ = _setup(tmp_path, [[], ["AAA"], ["AAA"], [], [], []])
    assert reconcile(out) == []
    snaps = _read(out / "paper_signal_snapshots.jsonl")
    snaps[0]["bar_commit_id"] = ""  # empty
    snaps[-1]["bar_commit_id"] = "not-16-hex!"  # malformed
    _rewrite_jsonl(out / "paper_signal_snapshots.jsonl", snaps)
    failures = reconcile(out)
    assert sum("bar_commit_id" in f for f in failures) >= 2


def test_reconcile_passes_with_valid_bar_commit_id_everywhere(tmp_path):
    # Positive control: a clean full bar commit reconciles, and every snapshot + accounting
    # row carries a well-formed 16-hex bar_commit_id.
    out, _, _ = _setup(tmp_path, [[], ["AAA"], ["AAA"], [], [], []])
    assert reconcile(out) == []
    for name in _COMMIT_ROW_FILES:
        for r in _read(out / name):
            cid = r.get("bar_commit_id")
            assert isinstance(cid, str) and len(cid) == 16 and all(c in "0123456789abcdef" for c in cid)


# ---- Blocker 3: NO_ELIGIBLE_BARS_YET is a labeled no-op, not OK, and mutates nothing ------


def test_no_eligible_bars_status_no_ledger_no_state(tmp_path):
    # Fresh observation but all rows before forward_start_ts -> NO_ELIGIBLE_BARS_YET.
    out = tmp_path / "paper"
    fwd = tmp_path / "fwd"
    fwd.mkdir(parents=True, exist_ok=True)
    write_config_once(build_config(forward_start_ts=_FUTURE_START), output_dir=out)
    _write_obs(fwd, _obs([[], ["AAA"], ["AAA"], [], [], []]))
    summary = _run(out, fwd)
    assert summary["status"] == "NO_ELIGIBLE_BARS_YET"
    assert summary["status"] != "OK"
    # no fills/trades/equity/positions/funding/snapshots
    assert _no_ledger_rows(out)
    # no state file created or mutated
    assert not (out / "paper_position_state.json").exists()
    # summary + receipt + provenance clearly say no eligible bars
    assert "NO_ELIGIBLE_BARS_YET" in summary["current_verdict"]
    receipt = (out / "paper_receipt.md").read_text()
    assert "NO ELIGIBLE BARS YET" in receipt
    prov = json.loads((out / "paper_provenance.json").read_text())
    assert prov["status"] == "NO_ELIGIBLE_BARS_YET"


def test_cli_no_eligible_bars_exit_zero_clean_message(tmp_path):
    # CLI exits 0 (healthy no-op) but the message must NOT imply accounting ran.
    import os
    import subprocess
    import sys

    repo_root = Path(__file__).resolve().parents[1]
    out = tmp_path / "paper"
    fwd = tmp_path / "fwd"
    fwd.mkdir(parents=True, exist_ok=True)
    bars = _recent_grid_bars(3)
    future_start = _future_grid_boundary(5)  # all recent bars are before this
    write_config_once(build_config(forward_start_ts=future_start), output_dir=out)
    rows = [_obs_row(b, [], i) for i, b in enumerate(bars)]
    (fwd / "observation_log.json").write_text(json.dumps({"per_bar_obs": rows}), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "qnty-paper-accounting.py"),
            "--output-dir", str(out),
            "--forward-obs-dir", str(fwd),
        ],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
        env={**os.environ, "PYTHONPATH": str(repo_root)},
    )
    assert proc.returncode == 0, (proc.returncode, proc.stdout, proc.stderr)
    assert "No eligible bars yet; no ledger rows written" in proc.stdout
    assert "run complete" not in proc.stdout
    assert _no_ledger_rows(out)
    assert not (out / "paper_position_state.json").exists()


# ---- Blocker 4: freshness fields must be type/range-checked in the config contract --------


def _write_hashed_config(out: Path, mutate):
    out.mkdir(parents=True, exist_ok=True)
    config = build_config(forward_start_ts=TS[0])
    mutate(config)
    config["config_hash"] = config_hash(config)  # correctly re-hashed
    (out / "paper_config.json").write_text(json.dumps(config), encoding="utf-8")


def test_config_string_freshness_value_rejected(tmp_path):
    # EXACT Codex case: a correctly-hashed config with freshness.bar_interval_hours="bad".
    def m(c):
        c["freshness"]["bar_interval_hours"] = "bad"
    _write_hashed_config(tmp_path / "paper", m)
    with pytest.raises(ConfigContractError):
        load_config(tmp_path / "paper")


def test_config_negative_freshness_value_rejected(tmp_path):
    def m(c):
        c["freshness"]["max_bar_staleness_hours"] = -1
    _write_hashed_config(tmp_path / "paper", m)
    with pytest.raises(ConfigContractError):
        load_config(tmp_path / "paper")


def test_config_zero_freshness_value_rejected(tmp_path):
    def m(c):
        c["freshness"]["bar_interval_hours"] = 0
    _write_hashed_config(tmp_path / "paper", m)
    with pytest.raises(ConfigContractError):
        load_config(tmp_path / "paper")


def test_config_missing_freshness_subfield_rejected(tmp_path):
    def m(c):
        del c["freshness"]["heartbeat_max_age_hours"]
    _write_hashed_config(tmp_path / "paper", m)
    with pytest.raises(ConfigContractError):
        load_config(tmp_path / "paper")


def test_config_bool_freshness_value_rejected(tmp_path):
    # bool is a subclass of int but is not a valid hours value -> reject.
    def m(c):
        c["freshness"]["max_bar_staleness_hours"] = True
    _write_hashed_config(tmp_path / "paper", m)
    with pytest.raises(ConfigContractError):
        load_config(tmp_path / "paper")


def test_cli_malformed_freshness_config_aborts_cleanly_no_traceback(tmp_path):
    # EXACT Codex case: previously this passed config load and the CLI exited 1 with a
    # traceback from int("bad") in the freshness gate. Now it fails the config contract and
    # the CLI exits 3 cleanly with archive/re-init guidance and NO writes.
    import os
    import subprocess
    import sys

    repo_root = Path(__file__).resolve().parents[1]
    out = tmp_path / "paper"
    fwd = tmp_path / "fwd"
    out.mkdir(parents=True)
    fwd.mkdir(parents=True, exist_ok=True)

    def m(c):
        c["freshness"]["bar_interval_hours"] = "bad"
    _write_hashed_config(out, m)

    proc = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "qnty-paper-accounting.py"),
            "--output-dir", str(out),
            "--forward-obs-dir", str(fwd),
        ],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
        env={**os.environ, "PYTHONPATH": str(repo_root)},
    )
    assert proc.returncode == 3, (proc.returncode, proc.stderr)
    assert "Traceback" not in proc.stderr
    assert "ABORTED" in proc.stdout
    assert "archive" in proc.stdout.lower()
    # No ledger / state / summary rows written.
    assert _no_ledger_rows(out)
    assert not (out / "paper_position_state.json").exists()
    assert not (out / "paper_pnl_summary.json").exists()
