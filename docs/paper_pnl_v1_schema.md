# Paper PnL Ledger v1 — Schema Contract (`paper_pnl_v1`)

`schema_version: 1` · `engine_version: 0.2.0` · `baseline_label: fixed_notional_active_symbols_paper_v1`

This document pins the input/output contract for the **strictly additive** paper PnL
accounting layer. It converts the existing shadow observer's forward signals into
deterministic simulated fills, positions, trades, equity, and funding.

> **This is a simulation.** Every number produced by this layer is paper PnL on a
> frozen research observer. It is NOT live trading, NOT realized money, and a positive
> paper result does not prove real-money profitability or deployment readiness.
>
> **This is a fixed-notional active-symbol baseline, NOT faithful Package V2 PnL.** It
> trades a flat `$notional` per active symbol and does **not** reproduce V2's
> vol-normalized weights or portfolio-heat sizing. A green paper result does **not**
> validate the V2 vol-normalized edge. See section 8 for the full adapter contract.

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

Loaded via `quantbot.data.funding_loader.load_all_funding()`. Funding is accrued by
**actual row timestamp**: every funding event in the held interval `(bar_ts - interval,
bar_ts]` is summed (section 11). It does **not** assume one 8h-aligned value, and does not
assume symbols settle only at 00/08/16. If no funding row lands in the interval where one
is needed, `rate_available=false` and the amount is recorded as `0.0` **with the gap flag
set** — never silently zeroed without the flag.

### 1.4 Heartbeat — `forward_obs_v1/bar_decisions.jsonl`

`{bar_processed_at, commit_sha}` per run. **Heartbeat/provenance only.** Digested into
provenance and checked by the freshness gate (section 9); never parsed for signals.

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

**Funding accrual convention (v1):** funding is accrued over the **actual position holding
interval**, from the entry **fill** timestamp (the `T+1` open) to the exit **fill**
timestamp (its `T+1` exit open) / the current mark. Concretely:

- The per-bar funding window `(bar_ts - interval, bar_ts]` is **clamped** so its start is no
  earlier than the entry fill timestamp. No funding event before the position exists is ever
  charged (e.g. a 12:00 event cannot be charged against a position whose entry fills at the
  16:00 open).
- On the bar a position is first filled, the held sub-interval is zero, so **no funding row**
  is emitted for it that bar.
- A position leaving `active_symbols` at the exit-signal bar is still held until its `T+1`
  exit fill, so a **funding stub** for `(exit_signal_ts, exit_fill_ts]` is accrued at the
  exit-signal bar (`funding_id = "{symbol}|{bar_ts}|exit"`). This closes the gap between the
  exit signal and the actual exit fill.
- Multiple events (1h / 4h / off-grid) inside the held interval are all summed.

This is a deliberate v1 convention, not an exact venue match.

### 3.2 Equity definition (no double counting)

```text
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

All JSONL ledgers are **append-only**, deterministic key order, never rewritten. Every per-bar
accounting row (fills, trades, funding, positions, equity) and its consumed-signal snapshot
also carries a `bar_commit_id` (section 10) tying it to the exact consumed source row.

| File | Kind | Key fields |
| --- | --- | --- |
| `paper_config.json` | write-once | `schema_version, baseline_label, forward_start_ts, initial_equity_usd, notional_usd, leverage, fee_model, slippage_model, fill_model, funding_model, signal_source, freshness{bar_interval_hours, max_bar_staleness_hours, heartbeat_max_age_hours}, engine_version, config_hash` |
| `paper_fills.jsonl` | append | `fill_id, bar_commit_id, signal_bar_ts, fill_ts, symbol, side(BUY/SELL), kind(entry/exit), qty, open_price, fill_price, slippage_bps, fee, backfill=false` |
| `paper_position_state.json` | mutable anchor | `watermark_bar_ts, open_positions{symbol->{entry_fill_id, entry_price, qty, entry_bar_ts, funding_accrued}}, accumulators{realized_gross, fees_cum, funding_cum}` |
| `paper_positions.jsonl` | append | `bar_ts, bar_commit_id, open_symbols, num_open, gross_exposure_usd` |
| `paper_trades.jsonl` | append | `trade_id(=exit_fill_id), bar_commit_id, symbol, entry_fill_id, exit_fill_id, entry_bar_ts, exit_bar_ts, qty, entry_price, exit_price, gross_pnl, fees, funding, net_pnl, hold_bars, backfill=false` |
| `paper_equity.jsonl` | append | `bar_ts, bar_commit_id, realized_gross_pnl, unrealized_pnl, funding_cum, fees_cum, equity, drawdown, num_open` |
| `paper_funding.jsonl` | append | `funding_id(=symbol+bar_ts, or symbol+bar_ts+"\|exit" for the exit-tail stub), bar_commit_id, symbol, bar_ts, window_start, window_end, notional_usd, funding_rate(Σ of events in interval), funding_events, rate_available, funding_amount` (section 11) |
| `paper_signal_snapshots.jsonl` | append | `snapshot_id, bar_ts, bar_commit_id, bar_index, active_symbols, portfolio_heat, heat_cap_triggered, weighted_return, source_observation_digest, source_observation_mtime, run_ts, backfill=false` (section 10) |
| `paper_pnl_summary.json` | overwrite (**authoritative current-run status**) | `status(OK / RUNNING / ABORTED / CORRUPT_LEDGER / NO_ELIGIBLE_BARS_YET), baseline_label, baseline_note, closed_trades, winrate(null until closed_trades>0), realized_net_pnl, total_pnl, max_drawdown, profit_factor, expectancy, bars_elapsed, open_positions, funding_gap, funding_gap_count, current_verdict, disclaimer` (RUNNING runs carry `run_id, started_at, phase, previous_watermark` — `phase` is `preflight` for a normal run, `preflight_config_error` for the minimal stale-OK-superseding marker written when the config itself cannot be loaded; ABORTED runs add `abort_code, abort_reason, aborted_at`; CORRUPT_LEDGER runs add `reconcile_failures, reconcile_failure_count, detected_at`; NO_ELIGIBLE_BARS_YET runs add `reason, checked_at`). `CONFIG_ERROR` is a reserved persisted-summary status with `config_error, detected_at`; the current runner instead writes `RUNNING/phase=preflight_config_error` when replacing an existing stale summary. This file is the single authoritative current-run status (see § 5, run transaction): a `RUNNING` marker is written **before** the pre-run health/freshness/divergence gates (so a failed abort/corrupt publication never leaves a stale OK), and the final `OK` write is the commit marker. |
| `paper_provenance.json` | overwrite | latest run: `status(OK / ABORTED / CORRUPT_LEDGER / NO_ELIGIBLE_BARS_YET)`, `baseline_label`, input digests (`bar_decisions`, `observation_log`, OHLCV, funding), output digests (incl. `paper_signal_snapshots.jsonl`), `engine_version`, `git_sha`, `run_ts` (ABORTED runs add `abort_code, abort_reason`; CORRUPT_LEDGER runs add `reconcile_failures, reconcile_failure_count`) |
| `paper_provenance_log.jsonl` | append | one provenance record per run (incl. aborted runs) |
| `paper_receipt.md` | overwrite | human summary + loud disclaimer + baseline label + red flags (aborted runs render a 🛑 ABORTED receipt) |

---

## 5. Determinism & idempotency

- `config_hash = sha256(canonical_json_dumps(config without config_hash))` via
  `quantbot.core.determinism.canonical_json_dumps`.
- **Config load contract (`load_config`):** before the hash check, `validate_config_contract`
  rejects any stored config that does not meet the **current exact schema/engine contract**:
  it must contain all required fields (incl. `baseline_label`, `freshness{bar_interval_hours,
  max_bar_staleness_hours, heartbeat_max_age_hours}`), and match **exactly**:
  `schema_version == SCHEMA_VERSION` (an unknown/**future** `schema_version` such as `2` fails
  closed — no migration is implemented), `engine_version == EXPECTED_ENGINE_VERSION`, and
  `baseline_label == "fixed_notional_active_symbols_paper_v1"` (a wrong label such as
  `"not_the_fixed_baseline"` fails closed). An **old `0.1.0` config fails loudly** with a
  re-init hint — it must never run under the hardened provenance engine (stale
  `forward_start_ts` / contradictory provenance). Failures raise `ConfigContractError`.
  Archive/delete the stale output dir and re-init a fresh write-once config with a fresh future
  `forward_start_ts`.
- **Config contract value checks (`validate_config_contract`):** *every* required value is
  **deeply type/range-checked** — not only the freshness block — so a correctly-hashed but
  unsafe config fails closed as `ConfigContractError` (CLI exit 3) instead of writing NaN
  PnL/state or tracebacking deep in the engine:
  - `schema_version` == exact `SCHEMA_VERSION` (a true `int`, **not** `bool` — `schema_version:
    true` is rejected even though `True == 1` and `bool` is an `int` subclass);
    `engine_version`/`baseline_label`/`fill_model`/`signal_source` == their exact expected
    strings (a non-string `engine_version`/`baseline_label` is rejected); `funding_model` == the
    exact `{"type":"accrual","applied_as":"cash_flow"}` object; `fee_model`/`slippage_model` must
    be objects with the exact `type` (`flat_taker`/`fixed`).
  - `initial_equity_usd`, `notional_usd`, `leverage` must each be a **finite number > 0**;
    `fee_model.fee_bps` and `slippage_model.slippage_bps` must be **finite numbers >= 0**. All
    of `NaN`, `inf`, `-inf`, strings, `bool` (a subclass of `int`), and `null` are rejected.
  - every required `freshness` numeric (`bar_interval_hours`, `max_bar_staleness_hours`,
    `heartbeat_max_age_hours`) must be an int/float **> 0**, and an optional
    `max_future_skew_hours`, if present, must be an int/float **>= 0**.
  - `forward_start_ts` must be a **parseable ISO bar-timestamp string on the configured
    `bar_interval_hours` grid** (00/08/16 UTC). A numeric (`123`), unparseable, or off-grid
    value fails closed (it would otherwise traceback in the freshness gate or silently shift
    the no-fill boundary).
- **Run transaction / authoritative current-run status (`paper_pnl_summary.json` is the single
  source of truth, with `OK` as the commit marker):** "write the OK summary last" is **not**
  sufficient on its own (a stale prior `OK` would stay visible if a new run failed before
  re-writing it, and a state-write failure after an `OK` summary would leave a false `OK`).
  Neither is "write `RUNNING` after the pre-run gates pass": the existing-ledger health gate and
  the freshness/divergence gates each publish their own `CORRUPT_LEDGER`/`ABORTED` bundle, and
  **if that publication itself fails part-way a previous `OK` would still be visible**. So the
  `RUNNING` marker is written **before** those gates (Blocker 1). The runner runs an explicit
  transaction whose authoritative status lives in `paper_pnl_summary.json`:
  1. **`RUNNING` preflight marker before any gate or ledger/state mutation.** As the **first**
     summary write
     of a run — **before** the existing-ledger health gate, the freshness/divergence gates, and
     any snapshot/ledger/state write — the runner overwrites `paper_pnl_summary.json`
     **atomically** with `status: RUNNING` (carrying `run_id`, `started_at`, `phase: preflight`,
     `previous_watermark`, `baseline_label`). To preserve validation of the prior summary without
     reading it first, the runner atomically stages the old summary path **without parsing it**,
     writes `RUNNING`, then validates the staged prior summary during the health gate. No
     persisted ledger/state/summary content is read before `RUNNING` is visible. If the health
     gate or its `CORRUPT_LEDGER` publication fails, the authoritative path therefore remains
     `RUNNING`, never the superseded `OK`. A stale previous `OK` is superseded the instant a run
     begins, so a failed `CORRUPT_LEDGER`/`ABORTED`/`NO_ELIGIBLE_BARS_YET` publication can never
     leave the old `OK` visible. **Even a config
     load failure** invalidates a stale `OK`: if `paper_config.json` is missing/malformed, the
     runner writes a minimal `status: RUNNING` (`phase: preflight_config_error`) marker —
     **but only when a summary file already exists** (a first-run config error in a fresh dir
     writes nothing, preserving the `CONFIG_ERROR` exit-3 "no writes" contract) — then re-raises
     `ConfigContractError`.
  2. **Append + reconcile.** The bar rows are appended (snapshot-first, see § 10); `reconcile()`
     runs over the full ledger *post-mutation*. On any failure the runner writes a
     `CORRUPT_LEDGER` summary/receipt/provenance, **does not advance** the `watermark_bar_ts`/
     state, and the CLI exits **4**.
  3. **Publish bundle, then state, then the `OK` summary LAST.** The whole bundle (summary,
     receipt, provenance) is built **in memory** (provenance pins the summary's digest from its
     exact in-memory bytes). It is then published in this fixed order: provenance + receipt →
     **state/watermark** → **`OK` `paper_pnl_summary.json` LAST** (atomic temp + `os.replace`).
     The **final `OK` summary write is the single commit marker**: it appears only after
     provenance + receipt + the advanced state are already on disk.
  Failure semantics (every step): if generation or the provenance/receipt/state write fails, the
  visible status stays `RUNNING` and the watermark does not advance, so the next run reprocesses
  the batch idempotently and republishes. **State is written before the final `OK` summary**, so
  a state-write failure can no longer leave a false `OK` (the visible status is `RUNNING`). If the
  very last `OK`-summary write fails, the state may be ahead but the visible status is `RUNNING`
  (never `OK`); the next run finds no new bars, re-runs the publication, and self-heals to `OK`.
  In **no** failure case is a stale/partial/false `OK` visible. An existing partial/corrupt ledger
  can never be silently normalized into `OK`. A `RUNNING` summary that outlives one timer interval
  signals a crashed/incomplete run for operator stop/review (see `docs/ops/VM_90D_RUNBOOK.md`
  § 3.5b).
- **Fail-closed artifact reads (`CORRUPT_LEDGER`):** every persisted-artifact reader normalizes
  filesystem read failures (`PermissionError`/other `OSError`) and validates **parse AND deep
  shape** (not just "is it a JSON object" and not just "is the file parseable").
  A malformed JSONL ledger (invalid UTF-8, invalid JSON, or a valid-JSON **non-object** row such
  as `[]`/`123`/`"x"`) and a **structurally malformed/partial** JSONL row all fail closed. The
  per-row contract is **field-level and type-level**, mirroring exactly what the engine emits:
  - **required fields present** (an empty `{}` row, or one missing e.g. a fill's `fee`/`open_price`/
    `slippage_bps`/`backfill`, a snapshot's `active_symbols`, etc., is corrupt);
  - **finite numbers / exact non-negative integers** where needed (no
    `bool`/`NaN`/`inf`/`-inf`/string — e.g. a fill `fee=NaN`/`open_price=NaN`, a funding
    `funding_events=NaN`, a snapshot `weighted_return=NaN` or
    `source_observation_mtime="not-a-number"`);
  - **non-negative finite numbers** for `fee`/`slippage_bps`;
  - **non-empty strings** for ids/timestamps/symbols;
  - **lists of strings** for `open_symbols`/`active_symbols` (a scalar such as `open_symbols="AAA"`
    is corrupt);
  - **real booleans** for `backfill`/`rate_available`/`heat_cap_triggered`;
  - **enumerated** `side` ∈ {BUY, SELL} and `kind` ∈ {entry, exit}.

  The summary and state files are validated the same way. Summary validation is
  **status-specific** for `RUNNING`, `OK`, `NO_ELIGIBLE_BARS_YET`, `ABORTED`, reserved persisted
  `CONFIG_ERROR`, and `CORRUPT_LEDGER`: each status has required fields and exact field types.
  Thus a `{}`/malformed/non-object/wrong-typed `paper_pnl_summary.json` (incl. a partial
  `ABORTED`, a `RUNNING` summary with an accounting field, an `OK` summary with
  `open_positions="AAA"` or a **missing `disclaimer`**, or an unknown/wrong-typed `status`), a
  `{}`/partial/malformed `paper_position_state.json`
  (**`{}` is corrupt, never silently treated as "absent" and reinitialized**; a partial state, an
  **`open_positions` entry that is `{}`/partial**, or an **unparseable `watermark_bar_ts`** such as
  `"not-a-timestamp"` — only `""` or a parseable bar timestamp is accepted), or a pre-existing
  reconcile failure (orphan fill/snapshot, disagreeing `bar_commit_id`) all fail closed as
  `CORRUPT_LEDGER` — caught on the **pre-run existing-ledger health gate** (before any new
  snapshot/ledger/state mutation, and before any `NO_ELIGIBLE_BARS_YET` no-op or divergence abort)
  **or** the post-mutation reconcile gate. The CLI exits **4** with no traceback and requires
  operator review; the watermark is never advanced. (Per-artifact required-field/type contracts
  live in `quantbot.paper.reconcile.LEDGER_JSONL_SCHEMAS` and the `validate_summary_shape` /
  `validate_state_shape` helpers in `quantbot.paper.ledger`.)
- **`NO_ELIGIBLE_BARS_YET` no-op:** when the freshness gate returns the controlled
  `NO_ELIGIBLE_BARS_YET` (clean file, no bar past `forward_start_ts`), the runner writes a
  clearly-labeled `NO_ELIGIBLE_BARS_YET` summary/receipt/provenance and **does not** write any
  ledger row or create/mutate the position state/watermark. The CLI exits **0** (healthy
  no-op) but prints `No eligible bars yet; no ledger rows written` — never "run complete".
- **Missing/stale/malformed-config CLI behavior (`CONFIG_ERROR`):** because the invalid config
  *defines* the output contract, no valid `ABORTED` summary can be built. `load_config` normalizes
  **every** load fault to `ConfigContractError`: a **missing/unreadable** file
  (`FileNotFoundError`/other `OSError` → init guidance), **invalid UTF-8** bytes
  (`UnicodeDecodeError`), bad JSON (`JSONDecodeError`), missing
  fields, wrong schema/engine/baseline (incl. `schema_version: true`), non-finite/out-of-range
  numeric, bad fill_model/signal_source/funding_model, numeric/off-grid `forward_start_ts`, or a
  hash mismatch. `scripts/qnty-paper-accounting.py` catches that single type, prints clean
  init/archive/re-init guidance (no traceback / never exit 1), and **exits 3** writing **no**
  ledger/state/summary/provenance/receipt rows. (Exit codes: `0` `OK` run with the full
  evidence bundle published **or** `NO_ELIGIBLE_BARS_YET` no-op, `2` freshness/divergence gate
  abort with an `ABORTED` summary, `3` `CONFIG_ERROR` stale/malformed-config abort with no
  writes, `4` `CORRUPT_LEDGER` — pre-run health-gate **or** post-mutation reconcile failure,
  watermark not advanced. See `docs/ops/VM_90D_RUNBOOK.md` § 3.5b.)
- `fill_id = sha256(f"{symbol}|{signal_bar_ts}|{side}|{kind}")[:16]`.
- `trade_id = exit_fill_id`; `funding_id = f"{symbol}|{bar_ts}"` (exit-tail stub:
  `f"{symbol}|{bar_ts}|exit"`).
- Reruns are idempotent: append rows only for IDs not already present; the
  `watermark_bar_ts` in `paper_position_state.json` ensures already-resolved bars are not
  reprocessed. A byte-identical input set must yield byte-identical ledgers.

> **Provenance vs. long-term source of truth.** `paper_provenance.json` digests the
> *current* `observation_log.json`, which is a rolling 500-bar full-overwrite window. Once
> that window advances past the earliest forward bars, the live `observation_log.json` no
> longer spans the full forward history — but the append-only paper ledgers
> (`paper_fills/positions/trades/equity/funding.jsonl`) do, and they are the authoritative
> long-term record. The provenance digest pins the inputs *as seen on each run*; it is not
> expected to re-derive the entire forward history from a single later snapshot.

---

## 6. Backfill policy

No `backfill=false` record may have `fill_ts < forward_start_ts`. Historical/backfill
simulations go to `paper_pnl_v1_backfill/` only, labeled `mode=backfill_simulation`,
`backfill=true`. Forward and backfill ledgers are never merged.

## 7. 4h policy (not implemented)

Defer a 4h observer until the 8h paper ledger has >= 90 bars / 45 days of stable forward
accounting. A future 4h track needs its own observer output, paper output, config,
provenance, and a fresh `forward_start_ts`.

## 8. Baseline labeling / adapter contract

`baseline_label = fixed_notional_active_symbols_paper_v1`. This layer is an **adapter** over
the Package V2 observer's `active_symbols` set, not a reproduction of V2's PnL. State plainly
in every artifact (config, summary, receipt, provenance): this is **not** "V2 volnorm paper
PnL".

What this baseline deliberately loses vs Package V2:

- **Vol-normalized weights are not reproduced.** V2 sizes positions by inverse volatility;
  this layer does not.
- **Portfolio heat / weights are not used for sizing.** `portfolio_heat`,
  `heat_cap_triggered`, `weighted_return` are recorded for provenance only, never for sizing.
- **A fixed `$notional` per active symbol is substituted** (`qty = notional_usd /
  entry_fill_price`).
- **No compounding** — notional is flat, not a fraction of current equity.
- **No shorting** — long-only; the observer is long-only against this strategy.

Therefore the result tests **only the active-symbol fixed-notional baseline**. A green paper
PnL does **NOT** validate the V2 vol-normalized edge, and is not a live-trading or
deployment approval. A faithful V2 PnL track would require the observer to emit per-symbol
target weights; that is out of scope for v1.

## 9. Freshness gate (hard pre-run check)

Before any ledger row is written, `quantbot.paper.freshness.check_freshness` validates the
observer output. Any failure **aborts the run**: no fills/trades/equity/positions/funding/
snapshot rows are written, the watermark and state are untouched, the failure is logged
loudly to stderr, and the summary/receipt/provenance are written **clearly marked
`status: ABORTED`** with an `abort_code`. Stale/missing/malformed observer output is **never**
silently treated as a FLAT bar.

All JSON parse failures (a malformed `observation_log.json`) are converted into a controlled
abort (`MALFORMED_OBSERVATION_LOG`) **before** any uncaught exception — the ABORTED
summary/receipt/provenance are still written.

**The whole observation file needed for trust is validated — not only consumed rows.** Every
row (including **pre-`forward_start_ts`** rows) is checked for required fields, a list-of-
**strings** `active_symbols`, and a parseable, on-grid, non-duplicate, non-future `timestamp`;
the latest bar in the file must be fresh; and a configured heartbeat must be present-valid-
fresh. A stale/off-grid/duplicate/future observation therefore **aborts even before the
forward boundary** — it is never silently returned as a normal `OK`. When the whole file is
clean but **no bar has reached `forward_start_ts` yet**, the gate returns a controlled
`ok=True` / `NO_ELIGIBLE_BARS_YET` **no-op** (the engine then writes zero ledger rows); this is
distinct from a misleading `OK` and from an abort.

Checks (thresholds from `config.freshness`, defaults `bar_interval_hours=8`,
`max_bar_staleness_hours=24`, `heartbeat_max_age_hours=24`, `max_future_skew_hours=1`):

| Code | Condition |
| --- | --- |
| `MISSING_OBSERVATION_LOG` | `observation_log.json` does not exist. |
| `MALFORMED_OBSERVATION_LOG` | Not valid JSON, no `per_bar_obs` key, or **any** row (consumed or pre-forward) missing a required field (`bar_index, timestamp, active_symbols, portfolio_heat, heat_cap_triggered, weighted_return`) or whose `active_symbols` is not a **list of strings** (missing/`null`/list-of-objects/list-of-ints is **never** treated as `[]`/FLAT). |
| `EMPTY_PER_BAR_OBS` | `per_bar_obs` missing, empty, or not a list. |
| `MALFORMED_BAR_TIMESTAMP` | **Any** row's `timestamp` cannot be parsed. |
| `OFF_GRID_BAR` | **Any** bar (consumed or pre-forward, not just the last) is off the 8h grid (minute/second ≠ 0 or `hour % 8 ≠ 0`). |
| `DUPLICATE_OBSERVATION_TS` | **Any** two rows share a `timestamp` (ambiguous observation set). |
| `FUTURE_OBSERVATION` | **Any** bar is dated beyond `now + max_future_skew_hours` (a negative age must not pass as fresh). |
| `STALE_OBSERVATION` | `now - latest_bar_ts > max_bar_staleness_hours` (latest **consumed** bar if any, else latest **overall** — a dead observer aborts even pre-boundary). |
| `MALFORMED_HEARTBEAT` | `bar_decisions.jsonl` is present but unreadable / not valid JSON / a row is not an **object** (e.g. `[]`) / a row is missing `bar_processed_at` or `commit_sha` / an unparseable stamp (fail-closed, not silently "unavailable"). |
| `FUTURE_HEARTBEAT` | `bar_decisions.jsonl` heartbeat is dated beyond `now + max_future_skew_hours` (fail-closed). |
| `STALE_HEARTBEAT` | `bar_decisions.jsonl` heartbeat present, parseable, but older than `heartbeat_max_age_hours`. |
| `NO_ELIGIBLE_BARS_YET` | **`ok=True` controlled no-op** (not an abort, and **not** an `OK` accounting run): the whole file validated clean but no bar has reached `forward_start_ts`. The runner writes a clearly-labeled `NO_ELIGIBLE_BARS_YET` summary/receipt/provenance, writes **zero** ledger rows, and **does not create or mutate** the position state/watermark. The CLI exits `0` with `No eligible bars yet; no ledger rows written`. |

Only an **absent** heartbeat file is skipped (the observer may not have written one yet); a
present-but-malformed/future heartbeat **fails closed** (`MALFORMED_HEARTBEAT`/`FUTURE_HEARTBEAT`).
Heartbeat validation runs even when there are zero consumed bars.

## 10. Consumed signal snapshots (`paper_signal_snapshots.jsonl`)

`observation_log.json` is a rolling 500-bar **recompute + full-overwrite** (section 1.1 / 5),
so an already-consumed forward bar can be silently recomputed to different values on a later
run. To defeat that provenance hole, every processed bar's exact consumed source row is
frozen append-only:

- **One snapshot per consumed bar**, keyed by `snapshot_id = sha256("snap|" + bar_ts)[:16]`.
  Idempotent: a rerun appends nothing for an already-snapshotted bar. The in-memory dedupe
  set is updated as snapshots are built, so a duplicate timestamp within a single run can
  never yield two snapshots sharing one `snapshot_id` (the freshness gate also aborts
  duplicate consumed timestamps with `DUPLICATE_OBSERVATION_TS`).
- **Snapshots are never rewritten.**
- `source_observation_digest = sha256(canonical_json_dumps(full source row))` — the **entire**
  consumed `per_bar_obs` row, not a hand-picked subset. Any change to **any** field of an
  already-consumed bar (including fields the paper layer does not use for sizing) is detected.
- **Divergence gate:** before processing, every current forward obs row that already has a
  frozen snapshot is re-digested. If any differs from the frozen digest, the run aborts with
  `SIGNAL_SNAPSHOT_DIVERGENCE` **before any ledger mutation**. This catches the rolling window
  recomputing history under us.
- **Bar-level commit identity (atomicity):**
  `bar_commit_id = sha256(full consumed row + bar_ts + engine_version + config_hash)[:16]`.
  **Every** artifact written for a bar — the frozen snapshot **and** that bar's
  fills/trades/funding/positions/equity — carries the same `bar_commit_id`. Reconcile requires
  all rows for a processed bar to **agree** on it, so a partial bar (e.g. stale fills retained
  from a now-recomputed source row across a crash) can never reconcile clean against changed
  source evidence.
- **Crash-safe write order (snapshot-first):** within a run the immutable consumed-signal
  snapshot for a bar is frozen **first** (it carries the `bar_commit_id` and the full source
  digest), **then** the bar accounting rows that must agree with it, and the
  `paper_position_state.json` watermark is written **last** as the commit marker. Therefore:
  - a bar can never have fills/trades/equity **without** a matching immutable snapshot for the
    exact consumed row (the snapshot precedes them);
  - a crash **after** the snapshot but **before** the accounting rows leaves an orphan snapshot
    with no equity, which reconcile fails on loudly — and because the snapshot is already
    frozen, if the rolling observer then recomputes that bar the next run's divergence gate
    **aborts** instead of continuing;
  - a crash before the state write leaves the watermark un-advanced, so the next run
    reprocesses and idempotently completes the bar (no duplicate rows).
- **`bar_commit_id` is mandatory (never null/empty/malformed):** `reconcile` requires a
  well-formed 16-char hex `bar_commit_id` on **every** snapshot and **every** accounting row
  (fills/trades/funding/positions/equity) of a committed bar. A missing/null/empty/malformed id
  fails closed — a `None == None` comparison must never be accepted as agreement. Stripping the
  id from every (or any) row therefore fails reconcile, not passes it.
- **Reconcile orphan / partial-bar guards:** `reconcile` fails if any snapshot's `bar_ts` has
  no equity row (orphan), if any equity bar has no snapshot, if **any** accounting row
  (fill/trade/funding/positions/equity) references a `bar_ts` with no frozen snapshot
  (orphan/partial bar), or if any row's `bar_commit_id` disagrees with its snapshot. The runner
  runs this **before** publishing `OK` (reconcile-before-OK, section 5); a failure yields
  `CORRUPT_LEDGER` and the watermark is not advanced.

## 11. Funding accrual (actual rows over the held interval)

Funding is **not** assumed to be a single 8h-aligned value, and is accrued over the **actual
position holding interval** (entry fill → exit fill / current mark), not a holding-period-
shifted window. For each open position at bar `bar_ts`,
`quantbot.paper.engine.funding_in_interval` sums **every** funding event whose timestamp
falls in the (exclusive-start) window `(window_start, window_end]`:

- **Per-bar window:** `(max(bar_ts - bar_interval_hours, entry_fill_ts), bar_ts]`. The start
  is clamped to the entry fill timestamp, so **no event before the position exists is ever
  charged**. On the entry-fill bar the held sub-interval is zero and no row is emitted.
- **Exit-tail stub:** at the exit-signal bar an extra window `(exit_signal_ts, exit_fill_ts]`
  (`funding_id = "{symbol}|{bar_ts}|exit"`) is accrued, because the position is held until the
  `T+1` exit fill. It is accrued at the exit-signal bar so the bar's equity `funding_cum`
  stays exactly tied to the funding ledger sum.
- `funding_rate` in the ledger = Σ of the event rates in the window; `funding_events` = count;
  `funding_amount = notional_at_mark * funding_rate`. **Long pays when the rate is positive**
  (funding reduces net PnL).
- Multiple events inside one window (e.g. off-grid / sub-8h funding) are all accrued.
- The window start is **exclusive** so a boundary event already charged on the previous bar
  is not double-counted.
- If no event lands in a window where one is needed, `rate_available=false` and the amount is
  `0.0` **with the gap flag set** (`funding_gap`/`funding_gap_count` in the summary) — never a
  silent zero.

**Mark approximation (v1):** the funding event notional uses the position quantity times the
**available bar mark** — the `bar_ts` close for the per-bar window, and the exit-fill bar
close for the exit-tail stub (falling back to the entry price if a close is unavailable).
This is a deliberate v1 convention (mark at the bar boundary), not an exact per-event venue
mark.

## 12. Runtime / service-user hygiene

The committed systemd unit templates (`ops/systemd/qnty-paper-pnl.service`,
`qnty-shadow-run.service`) declare `User=qnty`. **The production VM currently runs these
services as `viktor`, not `qnty`** (see `docs/ops/VM_90D_RUNBOOK.md` § Service user). Do not
hardcode a VM-specific user into strategy logic. When deploying, either:

- align the paper service's `User=`/`Group=` with the **existing shadow service's** runtime
  user on the target VM, or
- ship a documented systemd drop-in override
  (`/etc/systemd/system/qnty-paper-pnl.service.d/override.conf` setting `User=`/`Group=`).

A template whose `User=` does not exist on the VM fails silently at activation — the paper
timer would never produce a ledger. The deployment must reconcile the user explicitly.
