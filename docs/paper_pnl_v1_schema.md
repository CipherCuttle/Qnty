# Paper PnL Ledger v1 — Schema Contract (`paper_pnl_v1`)

`schema_version: 1`

This document pins the input/output contract for the **strictly additive** paper PnL
accounting layer. It converts the existing shadow observer's forward signals into
deterministic simulated fills, positions, trades, equity, and funding.

> **This is a simulation.** Every number produced by this layer is paper PnL on a
> frozen research observer. It is NOT live trading, NOT realized money, and a positive
> paper result does not prove real-money profitability or deployment readiness.

---

## 0. Non-negotiable boundaries

- Reads `/srv/qnty/output/forward_obs_v1/` **read-only**. Never writes there.
- Never edits `ops/bin/qnty-shadow-run.sh` or any observer script.
- No strategy reimplementation, no alpha changes, no live exchange access.
- Forward output dir: `/srv/qnty/output/paper_pnl_v1/`.
- Backfill output dir (separate, never merged): `/srv/qnty/output/paper_pnl_v1_backfill/`
  (`mode=backfill_simulation`, `backfill=true`).
- On the dev box these `/srv/qnty/...` paths do not exist; override with
  `QNTY_OUTPUT_DIR` / `QNTY_FORWARD_OBS_DIR` env vars for tests/local runs.

---

## 1. Consumed inputs (read-only)

### 1.1 Signal source — `forward_obs_v1/observation_log.json`
Produced by `scripts/run_validation_v2.py`. Authoritative shape (committed sample
`output/validation_v2/observation_log.json`):

```json
{
  "window_size": 500,
  "summary": { ... },
  "per_bar_obs": [
    {
      "bar_index": 4771,
      "timestamp": "2025-11-07T08:00:00",
      "active_symbols": [],
      "portfolio_heat": 0.0,
      "heat_cap_triggered": false,
      "weighted_return": 0.0
    }
  ]
}
```

Fields consumed from each `per_bar_obs[]` element:

| Field | Meaning | Use |
| --- | --- | --- |
| `timestamp` | OHLCV bar label = bar **open** time on the 8h grid (00/08/16 UTC). | Decision-bar key. |
| `active_symbols` | Symbols with an active **LONG** signal on this bar (long-only). | Target holdings. |

`portfolio_heat`, `heat_cap_triggered`, `weighted_return`, `bar_index` are NOT used for
sizing (sizing is fixed-notional; see §3). They may be copied into provenance only.

**Window semantics (critical):** `observation_log.json` is a rolling **500-bar
recompute, full-overwrite** over the historical CSVs every run. Most rows are historical
backfill. The paper layer consumes only rows with `timestamp >= forward_start_ts`.

### 1.2 Price source — `data/<SYMBOL>_8h_ohlcv.csv`
Loaded via `quantbot.data.multi_asset_loader.load_all_ohlcv()`. Header:
`timestamp,open,high,low,close,volume`. `timestamp` = bar open time. The **fill price**
for a signal at decision bar `T` is the **open of the next bar** (`T+1`), i.e. the OHLCV
row immediately after `T` for that symbol.

### 1.3 Funding source — `data/<SYMBOL>_8h_funding.csv`
Loaded via `quantbot.data.funding_loader.load_all_funding()`. Per-bar funding rate is the
most recent `fundingRate` at or before the bar timestamp. If none exists for a symbol at a
bar, `rate_available=false` and the amount is recorded as `0.0` **with the flag set** —
never silently zeroed without the flag.

### 1.4 Heartbeat — `forward_obs_v1/bar_decisions.jsonl`
`{bar_processed_at, commit_sha}` per run. **Heartbeat/provenance only.** Digested into
provenance; never parsed for signals.

---

## 2. Fill model — `next_bar_open_pessimistic`

- Signal observed at decision bar `T` (close). Earliest fill = `T+1` open. Never fill at
  `T` close.
- If `T+1` open is unavailable for **any** symbol acted on at bar `T` (e.g. `T` is the
  latest bar), the whole bar is **deferred**: nothing is written for it, the watermark is
  not advanced, and it is retried on the next run. (All-or-nothing per bar keeps the
  ledgers contiguous and append-only.)
- Adverse slippage (default `slippage_bps = 5`):
  - BUY fill price `= open * (1 + slippage_bps / 10000)`
  - SELL fill price `= open * (1 - slippage_bps / 10000)`
- Fees: flat taker `fee_bps = 5` (0.05%) per side, `fee = fill_price * qty * fee_bps/10000`.
- Funding accounted as a cash flow even though it is not used as alpha (§3).

---

## 3. Position & sizing model (v1)

- **Long-only.** Per symbol: `FLAT -> LONG` when the symbol enters `active_symbols`;
  `LONG -> FLAT` when it leaves. No SHORT, no flips (dead code against this observer).
- Same-direction repeat (already long, still active): no new fill, snapshot only.
- **Fixed notional** per active symbol: `qty = notional_usd / entry_fill_price`. No
  compounding. `leverage` recorded but defaults to `1` and does not change qty in v1.
- This is **fixed-notional paper accounting**, NOT exact replication of the observer's
  inverse-vol portfolio. Per-symbol target weights are not present in the artifact and are
  deliberately NOT inferred from `weighted_return`.

### 3.1 Timing / off-by-one
At decision bar `T`: positions opened/closed by `T`'s signal **execute at `T+1` open**.
Therefore the per-bar snapshot for bar `T` reflects the book *before* `T`'s fills (i.e.
positions from earlier decisions that executed at or before `T`'s open). Funding for bar
`T` accrues on that pre-fill book. New fills are applied after the bar-`T` snapshot and
first appear in bar `T+1`'s snapshot.

### 3.2 Equity definition (no double counting)
```
equity(T) = initial_equity_usd
          + realized_gross_cum     # Σ gross PnL of closed trades up to T
          - fees_cum               # Σ all fees paid (entry+exit closed, entry of open)
          - funding_cum            # Σ all funding paid (closed + open-so-far)
          + unrealized_gross(T)    # Σ (close(T) - entry_price) * qty over open positions
drawdown(T) = (peak(equity) - equity(T)) / peak(equity)
```
`net_pnl` of a closed trade `= gross_pnl - entry_fee - exit_fee - funding_accrued`.

---

## 4. Produced outputs (`paper_pnl_v1/`)

All JSONL ledgers are **append-only**, deterministic key order, never rewritten.

| File | Kind | Key fields |
| --- | --- | --- |
| `paper_config.json` | write-once | `schema_version, forward_start_ts, initial_equity_usd, notional_usd, leverage, fee_model, slippage_model, fill_model, funding_model, signal_source, engine_version, config_hash` |
| `paper_fills.jsonl` | append | `fill_id, signal_bar_ts, fill_ts, symbol, side(BUY/SELL), kind(entry/exit), qty, open_price, fill_price, slippage_bps, fee, backfill=false` |
| `paper_position_state.json` | mutable anchor | `watermark_bar_ts, open_positions{symbol->{entry_fill_id, entry_price, qty, entry_bar_ts, funding_accrued}}, accumulators{realized_gross, fees_cum, funding_cum}` |
| `paper_positions.jsonl` | append | `bar_ts, open_symbols, num_open, gross_exposure_usd` |
| `paper_trades.jsonl` | append | `trade_id(=exit_fill_id), symbol, entry_fill_id, exit_fill_id, entry_bar_ts, exit_bar_ts, qty, entry_price, exit_price, gross_pnl, fees, funding, net_pnl, hold_bars, backfill=false` |
| `paper_equity.jsonl` | append | `bar_ts, realized_pnl, unrealized_pnl, funding_cum, fees_cum, equity, drawdown, num_open` |
| `paper_funding.jsonl` | append | `funding_id(=symbol|bar_ts), symbol, bar_ts, notional_usd, funding_rate, rate_available, funding_amount` |
| `paper_pnl_summary.json` | overwrite | `closed_trades, winrate(null until closed_trades>0), net_pnl, max_drawdown, profit_factor, expectancy, bars_elapsed, open_positions, current_verdict, disclaimer` |
| `paper_provenance.json` | overwrite | latest run: input digests (`bar_decisions`, `observation_log`, OHLCV, funding), output digests, `engine_version`, `git_sha`, `run_ts` |
| `paper_provenance_log.jsonl` | append | one provenance record per run |
| `paper_receipt.md` | overwrite | human summary + loud disclaimer + red flags |

---

## 5. Determinism & idempotency

- `config_hash = sha256(canonical_json_dumps(config without config_hash))` via
  `quantbot.core.determinism.canonical_json_dumps`.
- `fill_id = sha256(f"{symbol}|{signal_bar_ts}|{side}|{kind}")[:16]`.
- `trade_id = exit_fill_id`; `funding_id = f"{symbol}|{bar_ts}"`.
- Reruns are idempotent: append rows only for IDs not already present; the
  `watermark_bar_ts` in `paper_position_state.json` ensures already-resolved bars are not
  reprocessed. A byte-identical input set must yield byte-identical ledgers.

---

## 6. Backfill policy
No `backfill=false` record may have `fill_ts < forward_start_ts`. Historical/backfill
simulations go to `paper_pnl_v1_backfill/` only, labeled `mode=backfill_simulation`,
`backfill=true`. Forward and backfill ledgers are never merged.

## 7. 4h policy (not implemented)
Defer a 4h observer until the 8h paper ledger has >= 90 bars / 45 days of stable forward
accounting. A future 4h track needs its own observer output, paper output, config,
provenance, and a fresh `forward_start_ts`.
