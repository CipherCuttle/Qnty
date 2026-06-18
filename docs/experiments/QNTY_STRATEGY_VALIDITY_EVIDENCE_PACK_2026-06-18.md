# QNTY — Strategy-Validity Evidence Pack

**Prepared:** 2026-06-18 (UTC)
**Prepared by:** Repo Claude (read-only forensic pass)
**Audience:** Browser Claude (hostile research / literature review next)
**Pinned commit (main/VM):** `5821b67dea1f5483f8188a9e3c11169efcfb6f5c`
**Scope:** Evidence-gathering only. No strategy changes, no tuning, no deploys, no live trading, no production mutation. Local read-only inspection + the operator-supplied live paper state.
**Evidence label:** `EDGE_UNPROVEN`
**Status line:** `INFRA OK / BASELINE CONTROL RUNNING / V2 EDGE UNTESTED FORWARD / LANE B PLANNED / NO LIVE`

> ⚠️ This pack makes **no profitability claim** and recommends **no live trading**. It exists to let Browser Claude judge whether the strategy is solid enough to keep *observing* on paper, or whether we are footgunning ourselves.

---

## 1. Executive Summary

**Infrastructure is healthy. Strategy edge is unproven. The single most important finding is a lane mismatch.**

The thing that was *validated* and the thing that is *running forward on paper are not the same portfolio.*

- The **validation/“GO” verdict** (excess_return +2.49, Sharpe 2.9, net_return +50%) is a **rolling re-backtest** over a fixed 500-bar historical window using a **vol-normalized, heat-capped, inverse-vol weighted** portfolio.
- The **forward paper lane** consumes only the *set of active symbols* from that observer and runs a **fixed-notional ($1,000/symbol, equal-weight, 1× leverage, long-only)** accounting engine. It does **not** apply the vol-normed weights or the heat cap. By the engine's own label it is a `"fixed-notional active-symbol baseline, NOT V2 volnorm PnL"`.

So the forward paper PnL (currently **−1.56%**) is a *different object* from the validated metric. It is admissible as forward evidence **about the fixed-notional baseline only**, not about the V2 volnorm package that earned the GO.

Second-order findings:
- The "forward observer" is literally `scripts/run_validation_v2.py` re-run each 8h cycle — i.e. **a rolling re-backtest, not an independent live signal.** The GO verdict it emits is in-window backtest, not forward evidence.
- The benchmark used for "excess return" is a **gross always-long equal-weight** basket that lost ~−199% (log) over the window. Beating a catastrophic benchmark is weak evidence of edge.
- The accounting engine itself is **unusually well-hardened** (T+1 fills, closed-bar-only, append-only, multi-gate reconcile, independent replay cross-check PASS). Data integrity is strong; the doubt is about *edge*, not *bookkeeping*.
- **Forward sample is tiny** (≈13 batches / single-digit-to-low-tens of committed forward bars). Nothing here can support an edge claim either way.

**Bottom line for the verdict:** see §13. Short version — **NOT ENOUGH EVIDENCE** to judge edge, and the **lane mismatch must be resolved or explicitly accepted** before the forward paper number is read as a verdict on the validated strategy.

---

## 2. Current Live Paper Status (operator-supplied, post-recovery)

| Field | Value |
|---|---|
| seq | 119 |
| batch_id | 13 |
| bar_ts (watermark) | `2026-06-18T08:00:00` |
| equity | `9844.23336216` |
| PnL | `-155.76663784` |
| PnL % | ≈ `-1.56%` |
| drawdown | `0.04339174` (≈4.34%) |
| realized_gross_pnl | `-54.60100392` |
| unrealized_pnl | `-96.05136018` |
| funding_cum | `0.14157424` |
| fees_cum | `4.9726995` |
| num_open | 4 |

Initial equity = `$10,000` (`DEFAULT_INITIAL_EQUITY_USD`, [quantbot/paper/config.py:25](../../quantbot/paper/config.py#L25)).

**Read of the numbers:** the loss is almost entirely **mark-to-market (unrealized −96.05)** plus **realized −54.60**. **Costs are negligible** — fees `4.97`, funding `+0.14`. This is **not** a fee/funding-bleed loss; it is **directional/momentum loss** (long-only momentum into a chop/down tape). The operator snapshot's `num_open=4` was a **pre-fill** count at that bar; §2A confirms true post-fill current exposure is 2 × $1,000 ≈ **0.20× net**.

> These figures live in the production paper DB on the VM (`/srv/qnty/output/paper_pnl_v1/paper_ledger.db`). **As of §2A below they have now been read-only-confirmed directly from the VM.**

---

## 2A. VM-Confirmed Forward Decomposition (pulled read-only 2026-06-18T17:xx UTC)

> Source: read-only SQLite snapshot of `/srv/qnty/output/paper_pnl_v1/paper_ledger.db` (`mode=ro`, `query_only=1`). **Production was not mutated.** The production ledger is a **SQLite DB**, not the JSONL files the original §12 commands assumed — those commands have been superseded by the SQLite reads recorded here.

### Verifier status (authoritative)
- `paper_verify_report.json`: **status `OK`, failure_count `0`, exit_code `0`**, `verified_at 2026-06-18T17:09:47Z`, `verifier sqlite v1.0.0`, content_sha256 `3acc0328…`.
- Verifier **self-disclaimer (verbatim):** *"Verifier v1 validates SQLite ledger integrity and internal accounting consistency. It does **not** independently rederive OHLCV marks/unrealized PnL/exposure from source price data."* → **this directly confirms footgun F7** (ledger checks itself, not independent marks).

### Config / provenance
| Field | Value |
|---|---|
| **forward_start_ts** | **`2026-06-14T00:00:00Z`** |
| engine_version | `0.3.0` (all 13 batches) |
| config_hash | `fcad39ff…` (identical across all batches — **no config drift**) |
| baseline_label | `fixed_notional_active_symbols_paper_v1` (confirms F1: this is the fixed-notional baseline, not volnorm) |
| **batch git_sha** | **`None` for every batch** — ⚠️ batches do **not** record the commit they ran at, so the DB cannot self-attest it ran at `5821b67` (new minor footgun **F17**). |
| batch 13 | committed `2026-06-18T17:00:07Z`, `committed_bar_count=2` (the **recovery catch-up** of bars `06-18T00:00` + `06-18T08:00` after the PR #15 incident). |

### Forward sample size & integrity
- **Forward bars (equity rows): exactly 14.** Events: **119** (`ledger_events` seq **1…119, contiguous, no gaps**). Batches: **13**.
- **First bar:** `2026-06-14T00:00:00` · **Last bar:** `2026-06-18T08:00:00`.
- **Monotonicity: CLEAN** — bar_ts strictly sorted, all unique, **zero off-grid** timestamps (all on 00/08/16 UTC).
- **Contamination: NONE** — `paper_pnl_v1/` contains only `paper_config.json`, `paper_ledger.db` (+`-wal` 0 bytes, +`-shm`), `paper_verify_{log.jsonl,receipt.md,report.json}`. No JSONL ledger files, no lab/replay artifacts, no stray output. (Confirms F13/F14 empirically.)

### Equity / drawdown path (all 14 bars)
| seq | batch | bar_ts | equity | realized* | unrealized* | drawdown | num_open* |
|---|---|---|---|---|---|---|---|
| 8 | 1 | 06-14T00:00 | 10000.00 | 0.00 | 0.00 | 0.0000 | 0 |
| 17 | 2 | 06-14T08:00 | 9956.03 | 0.00 | −41.56 | 0.0044 | 5 |
| 25 | 3 | 06-14T16:00 | 10051.41 | −19.62 | +74.39 | 0.0000 | 3 |
| 31 | 4 | 06-15T00:00 | 10036.93 | −19.62 | +60.94 | 0.0014 | 5 |
| 39 | 5 | 06-15T08:00 | **10290.77 (peak)** | −19.62 | +314.79 | 0.0000 | 5 |
| 47 | 6 | 06-15T16:00 | 10184.25 | −19.62 | +208.24 | 0.0104 | 5 |
| 55 | 7 | 06-16T00:00 | 10173.80 | −19.62 | +197.89 | 0.0114 | 5 |
| 63 | 8 | 06-16T08:00 | 10116.85 | −19.62 | +140.87 | 0.0169 | 5 |
| 71 | 9 | 06-16T16:00 | 10127.78 | −19.62 | +151.83 | 0.0158 | 5 |
| 79 | 10 | 06-17T00:00 | 10112.98 | −19.62 | +137.14 | 0.0173 | 5 |
| 87 | 11 | 06-17T08:00 | 10118.97 | −19.62 | +143.12 | 0.0167 | 5 |
| 95 | 12 | 06-17T16:00 | 10031.32 | −19.62 | +55.48 | 0.0252 | 5 |
| 106 | 13 | 06-18T00:00 | 10000.31 | −19.62 | +24.59 | 0.0282 | 5 |
| 119 | 13 | 06-18T08:00 | **9844.23** | −54.60 | −96.05 | **0.0434** | 4 |

\* `realized`/`unrealized`/`num_open` in each row are the engine's **pre-fill** snapshot for that bar (marks taken before that bar's entries/exits execute at T+1). See reconciliation note below.
- **Peak equity `10290.77` (+2.91%) at `06-15T08:00`; min/last `9844.23` (−1.56%).** Max drawdown `0.04339174` from that peak. So the book **ran up ~+2.9% on day 2 on unrealized, then gave it all back and went negative** — confirms the §6 hypothesis that peak was above $10k.

### Trades (all 5 closed — **every one a loser; zero winners**)
| Rank | symbol | entry → exit | hold (bars) | gross | fees | funding | **net_pnl** |
|---|---|---|---|---|---|---|---|
| Worst | XRPUSDT | 06-14T16:00 → 06-18T08:00 | 11 | −41.37 | 0.98 | −0.14 | **−42.21** |
| 2 | BNBUSDT | 06-14T00:00 → 06-18T00:00 | 12 | −34.98 | 0.98 | +0.27 | **−36.23** |
| 3 | BTCUSDT | 06-14T00:00 → 06-18T08:00 | 13 | −32.87 | 0.98 | −0.09 | **−33.76** |
| 4 | XRPUSDT | 06-14T00:00 → 06-14T08:00 | 1 | −10.94 | 0.99 | −0.08 | **−11.86** |
| Best | ETHUSDT | 06-14T00:00 → 06-14T08:00 | 1 | −8.68 | 1.00 | −0.02 | **−9.65** |

- Closed-trade totals: **sum_net `−133.72`**, sum_fees `4.94`, sum_funding `−0.07`. **All closed trades lost; the "best" trade still lost −9.65.**

### Current TRUE open positions — **2, not 4**
The operator summary's `num_open=4` is the **pre-fill count of the last bar's snapshot** (BTC/ETH/SOL/XRP marked at `06-18T08:00` close). At that same bar **BTC and XRP exited** (booked as the two largest-hold trades above), leaving:

| symbol | qty | entry_price | entry_bar_ts | hold_bars | funding_accrued |
|---|---|---|---|---|---|
| SOLUSDT | 14.65757809 | 68.224095 | 06-14T00:00 | 13 | 0.0 |
| ETHUSDT | 0.57950778 | 1725.60237 | 06-14T16:00 | 11 | 0.20702342 |

→ **True current exposure ≈ 2 × $1,000 ≈ $2,000 gross long on $9,844 equity ≈ 0.20× net** (even lower than the 0.41× estimated in §7).

### Reconciliation note (why operator-summary fields ≠ accumulators)
The engine snapshots equity **pre-fill**, so the **last published equity row lags the running accumulators by one bar's fills**:
| Quantity | Last equity snapshot (seq 119, pre-fill) | `ledger_state` accumulator (post-fill) |
|---|---|---|
| realized_gross | −54.60 | **−128.85** |
| fees_cum | 4.97 | **5.94** |
| funding_cum | 0.142 | 0.142 |
| peak_equity | — | 10290.77 |
Both are internally consistent: the operator quoted the **published snapshot** (−54.60 realized, 4 open, 4.97 fees); the **accumulators** reflect that BTC+XRP also exited at the final bar (adding −74.24 gross, +1.0 entry-fees-on-remaining). The published **equity 9844.23 / −1.56% / drawdown 0.0434 are correct and verifier-OK as the bar-close mark.**

---

## 3. Strategy Mechanics (plain English + exact pointers)

**What it is:** a **long-only, time-series-momentum (TSMOM)** crypto strategy with a volatility-regime overlay, validated as a vol-normalized heat-capped portfolio, but *run forward* as a fixed-notional equal-weight baseline.

| Aspect | Behaviour | Source |
|---|---|---|
| **Signal source (validated)** | TSMOM: `long` iff `log(close_t / close_{t-20}) > threshold`, else flat. Grid point used = `rp=20, th=0.0` (pure sign of 20-bar log return). | [tsmom_strategy.py:57](../../quantbot/strategy/tsmom_strategy.py#L57), [run_validation_v2.py:214](../../scripts/run_validation_v2.py#L214) |
| **Vol-regime overlay** | Tags each signal `low_vol`/`high_vol` via 20-bar stdev quantile (q=0.65). In the current code path the overlay **tags but does not suppress** signals (both regimes update vol trackers; no regime gate drops the signal). | [vol_state_overlay.py](../../quantbot/strategy/vol_state_overlay.py), [run_validation_v2.py:279](../../scripts/run_validation_v2.py#L279) |
| **Direction** | **Long-only.** No short leg anywhere in the executed path. | [tsmom_strategy.py:80](../../quantbot/strategy/tsmom_strategy.py#L80), engine entries are `BUY` only [engine.py:414](../../quantbot/paper/engine.py#L414) |
| **Universe / symbols** | Quarterly point-in-time top-5. Latest table entry is `2025-10-01` → **BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT, BNBUSDT**. Table is **not populated past 2025-10-01** (see footgun F8). | [quarterly_universe.py](../../quantbot/data/quarterly_universe.py) |
| **Portfolio construction (validated)** | Inverse-vol weights, normalized to sum 1, then heat-cap scaled. | [volnorm_portfolio.py:90](../../quantbot/experiment/volnorm_portfolio.py#L90) |
| **Portfolio construction (forward paper)** | **Fixed notional $1,000 per active symbol, equal weight. Heat cap and inverse-vol weights are NOT applied.** | [engine.py:417](../../quantbot/paper/engine.py#L417), [config.py:323](../../quantbot/paper/config.py#L323) |
| **Position sizing** | `qty = notional / fill_price`, `notional = $1,000`. | [engine.py:417](../../quantbot/paper/engine.py#L417) |
| **Leverage** | `1.0`. | [config.py:27](../../quantbot/paper/config.py#L27) |
| **Bar interval** | 8h grid (00/08/16 UTC). | [config.py:34](../../quantbot/paper/config.py#L34) |
| **Fill model** | `next_bar_open_pessimistic` — fills at **T+1 open**, entries `× (1+slip)`, exits `× (1−slip)`. | [engine.py:415-417](../../quantbot/paper/engine.py#L415), [engine.py:358-360](../../quantbot/paper/engine.py#L358) |
| **Fees** | Flat taker **5 bps/side** on fill notional, both entry and exit. | [config.py:28](../../quantbot/paper/config.py#L28), [engine.py:363](../../quantbot/paper/engine.py#L363) |
| **Slippage** | Fixed **5 bps/side**. | [config.py:29](../../quantbot/paper/config.py#L29) |
| **Funding** | Accrual model, applied as cash flow. Long pays when rate>0; accrued over actual hold interval `(entry_fill_ts, mark]` incl. an exit-tail stub through the T+1 exit fill. | [engine.py:256](../../quantbot/paper/engine.py#L256), [engine.py:283](../../quantbot/paper/engine.py#L283) |
| **Freshness gates** | Aborts if newest observer bar older than 24h or heartbeat older than 24h; off-grid/missing/malformed observer output → hard abort, no rows written. | [config.py:35-36](../../quantbot/paper/config.py#L35), [freshness.py](../../quantbot/paper/freshness.py), [runner.py:318](../../quantbot/paper/runner.py#L318) |
| **Heat cap / risk control** | Heat cap = 1.0 in the *validation* engine only; **not enforced in the paper engine.** No per-trade stop. Implicit risk control = small fixed notional + flat-on-loss-of-signal exits. | [volnorm_portfolio.py:29](../../quantbot/experiment/volnorm_portfolio.py#L29) |
| **Entry rule** | Symbol enters (`desired − current`) when it appears in observer `active_symbols`. | [engine.py:222](../../quantbot/paper/engine.py#L222) |
| **Exit rule** | Symbol exits (`current − desired`) when it drops out of `active_symbols` (i.e. momentum signal goes flat). **No stop-loss, no take-profit, no time stop** — exit is purely signal-driven. | [engine.py:223](../../quantbot/paper/engine.py#L223) |

**Equity definition (forward paper):**
`equity = initial + realized_gross − fees_cum − funding_cum + unrealized` — [engine.py:323](../../quantbot/paper/engine.py#L323).

---

## 4. Evidence Inventory (file paths)

### Local repo artifacts present
| Artifact | Path | What it is | Admissibility |
|---|---|---|---|
| Validation verdict | [output/validation_v2/verdict.json](../../output/validation_v2/verdict.json) | "GO", excess 2.49, dd 0.111 | **Backtest** (rolling 500-bar window) |
| Validation drawdown summary | [output/validation_v2/drawdown_summary.json](../../output/validation_v2/drawdown_summary.json) | net_return 0.502, sharpe 2.909, benchmark −1.988 | **Backtest** |
| Observation log | [output/validation_v2/observation_log.json](../../output/validation_v2/observation_log.json) | 500 `per_bar_obs` rows, window `2025-11-07 → 2026-04-22` | **Backtest feed** (becomes forward feed via copy) |
| Caveat note | [output/validation_v2/caveat_note.md](../../output/validation_v2/caveat_note.md) | Benchmark/K3 caveats | Diagnostic |
| Package identity | [output/validation_v2/package_identity.json](../../output/validation_v2/package_identity.json) | volnorm package id | Reference |
| Stage 4 kill criteria | [output/stage4_volnorm/kill_criteria.json](../../output/stage4_volnorm/kill_criteria.json) | dd 0.226, excess 0.703 | **Backtest (prior stage)** |
| Lab cross-check | [output/lab/cross_check/20260614T212058Z/cross_check_report.json](../../output/lab/cross_check/20260614T212058Z/cross_check_report.json) | "engine and independent replay agree row-by-row", verdict PASS | **Integrity (good)** |
| Project state | [docs/CURRENT_STATE.md](../../docs/CURRENT_STATE.md) | "shadow-only, not deployment-ready, K3 caveated" | Reference |
| Boundaries | [docs/PROJECT_BOUNDARIES.md](../../docs/PROJECT_BOUNDARIES.md) | Qnty vs Franken/THT0 separation | Reference |

### Live artifacts NOT in local repo (on VM only)
- `/srv/qnty/output/paper_pnl_v1/paper_ledger.db` — **authoritative production paper state** for the baseline/control lane. §2A was confirmed by read-only SQLite access (`mode=ro`, `query_only=1`).
- `/srv/qnty/output/paper_pnl_v1/paper_verify_report.json`, `paper_verify_log.jsonl`, `paper_verify_receipt.md` — verifier receipts/status for the SQLite ledger.
- Historical JSONL names from earlier drafts (`paper_equity.jsonl`, `paper_trades.jsonl`, `paper_funding.jsonl`, `paper_position_state.json`, `paper_pnl_summary.json`, `paper_provenance.json`) are **superseded/non-authoritative for this production lane unless regenerated from SQLite into a separate scratch/read-only report**. Do not treat them as live truth and do not write any replay/lab output into `/srv/qnty/output/paper_pnl_v1`.

### Local data
- `data/<SYM>_8h_ohlcv.csv` — 10-symbol 8h OHLCV. Local copy ends **`2026-04-22T16:00:00`** (5,272 BTC rows). The VM's copy is fresher (driven by `qnty-data-refresh`); local data **cannot** reproduce the current forward window.

---

## 5. Backtest / Validation / Shadow / Forward Paper — Separation

**This is the crux. Keep these four lanes strictly apart.**

| Lane | What generates it | Window | Portfolio | Numbers | Admissible as forward edge? |
|---|---|---|---|---|---|
| **Backtest (Stage 4)** | `run_stage4_volnorm.py` | Full history splits | volnorm + heat cap | dd 0.226, excess 0.703 | ❌ No — in-sample staging |
| **Validation ("GO")** | `run_validation_v2.py` | Last **500 closed bars** (rolling) | volnorm + heat cap | excess 2.49, Sharpe 2.9, net +50%, bench −1.99 | ❌ No — rolling re-backtest over a *historical* window |
| **Shadow / forward observer** | `ops/bin/qnty-shadow-run.sh` → **re-runs `run_validation_v2.py`** each 8h, copies `observation_log.json` into `forward_obs_v1/` | Latest closed bar appended | volnorm (in observer) | per-bar `active_symbols` + diagnostic `weighted_return` | ⚠️ Diagnostic only — it is a *re-backtest*, the GO label it emits is **not** forward |
| **Forward paper (TRUE forward)** | `quantbot/paper/runner.py` consuming `active_symbols` once per new bar, committed append-only | One new bar per cycle, watermark-gated | **fixed-notional equal-weight (NOT volnorm)** | **−1.56%, dd 4.3%** | ✅ Yes — but **about the fixed-notional baseline, not the validated volnorm package** |

**Critical separation facts:**
1. The **shadow observer is the validation backtest re-run** ([qnty-shadow-run.sh:36](../../ops/bin/qnty-shadow-run.sh#L36)). Its "GO" verdict is a property of a historical window, recomputed each cycle. **Do not read the GO as forward.**
2. The **forward paper lane uses a different portfolio** (fixed $1k/symbol) than the lane that earned the GO (volnorm/heat-capped). **The forward number does not confirm or refute the validated metric.**
3. The only **true forward** evidence is the paper ledger PnL (§2/§6). It is admissible, but (a) tiny sample and (b) about the baseline portfolio.

**Contaminated / inadmissible-as-edge:** Stage 4, validation GO, shadow weighted_return. **Admissible (with caveats):** forward paper ledger only.

---

## 6. Forward PnL Decomposition

From the operator-supplied live state (§2), then reconciled against the VM-confirmed SQLite ledger (§2A). Per-bar/per-symbol history should be read from `paper_ledger.db` in read-only mode; earlier JSONL-oriented follow-ups are superseded.

### Aggregate decomposition (current)
| Component | Value | Note |
|---|---|---|
| Initial equity | `10000.00000000` | |
| + realized_gross_pnl | `-54.60100392` | closed-trade directional loss |
| − fees_cum | `4.97269950` | ≈0.05% of equity — negligible |
| − funding_cum | `0.14157424` | longs paid a tiny net positive funding |
| + unrealized_pnl | `-96.05136018` | open MTM loss (dominant) |
| **= equity** | **`9844.23336216`** | |
| **= total PnL** | **`-155.76663784`** (−1.56%) | |

### Attribution
- **~62% of the loss is unrealized** (open positions under water) and **~35% realized** — i.e. the strategy is **structurally long into a falling/choppy tape**, not bleeding on costs.
- **Costs are ~3.3% of the total loss.** Fee/funding modelling is therefore *not* the thing producing the negative number; direction is.
- **Loss is structural-directional, not one-off:** with realized and unrealized both negative and several positions marked pre-fill, this looks like persistent long-momentum exposure that the tape is not rewarding — consistent with long-only momentum in a non-trending/down regime. §2A confirms all 5 closed trades were losers.

### Drawdown
- Reported `drawdown = 0.04339174` (4.34%) vs equity-based PnL of −1.56%. The drawdown is larger than current PnL%, implying **peak equity was above $10k earlier** (there was an up-leg, then a deeper retrace). This is consistent with the PR #14/#15 era reconciliation work on peak-equity (commit `89548de` "Fix paper drawdown peak-equity reconciliation").
- Drawdown is **well inside** the validation kill threshold (K2 = 0.35). No risk-limit breach.

> Tables above are reconstructable in full from the SQLite ledger on the VM. Earlier JSONL-based reconstruction notes are superseded by §2A.

---

## 7. Current Open Positions Summary

The operator snapshot's `num_open=4` is the **pre-fill snapshot count** for the final published equity row. At that same bar, BTC and XRP exited. The SQLite-confirmed **true current post-fill open positions are 2**:

| symbol | qty | entry_price | entry_bar_ts | hold_bars | funding_accrued |
|---|---|---|---|---|---|
| SOLUSDT | 14.65757809 | 68.224095 | 06-14T00:00 | 13 | 0.0 |
| ETHUSDT | 0.57950778 | 1725.60237 | 06-14T16:00 | 11 | 0.20702342 |

True gross exposure is therefore about **2 × $1,000 = $2,000** on `$9,844` equity, or about **0.20× net long**. The `paper_pnl_v1` number remains real baseline/control ledger evidence, but it is not evidence for V2 volnorm sizing.

---

## 8. Drawdown Analysis

- Current drawdown **4.34%**, max-DD kill threshold **0.35** (35%) — ~8× headroom. No structural risk-control concern at current exposure.
- The shallow drawdown is a **function of small fixed exposure** (about 0.20× true current post-fill exposure; the final published row's 0.41× was pre-fill), not of strategy skill. A higher-exposure (e.g. the validated heat-cap=1.0) sizing would produce materially larger swings — another reason the forward paper number understates the *validated* portfolio's risk.
- The SQLite-confirmed drawdown path peaks at `10290.77` on `2026-06-15T08:00:00` and ends/mins at `9844.23` on `2026-06-18T08:00:00`; max drawdown is `0.04339174`. Single-point drawdown claims should cite the full §2A path.

---

## 9. Known Accounting Incident — and why data was NOT corrupted

**Incident:** A paper accounting bug in `net_pnl` derivation (fixed in **PR #15**, commit `5821b67` "Fix paper net PnL canonicalization"). An attempted **seq=104 never committed.**

**Why the ledger was not corrupted (mechanism, confirmed in code):**
1. `net_pnl` is now derived from the **same rounded components that are persisted** (`canonical_net_pnl(gross, fees, funding)` = `round8(round8(gross) − round8(fees) − round8(funding))`) — [engine.py:33](../../quantbot/paper/engine.py#L33). The in-transaction verifier rejects any row where `ABS(net − (gross − fees − funding)) > 1e-8`. The pre-fix path could drift past that gate, so the bad row was **rejected at write time**, not silently stored.
2. The runner advances the **watermark/state LAST**, only after a full `reconcile()` **and** a `final_integrity_gate()` pass over the persisted ledgers — [runner.py:416](../../quantbot/paper/runner.py#L416), [runner.py:501](../../quantbot/paper/runner.py#L501). A failed row → `CORRUPT_LEDGER` status, **watermark NOT advanced**, next run reprocesses idempotently ([runner.py:172](../../quantbot/paper/runner.py#L172)).
3. Ledgers are **append-only with id-dedupe** ([runner.py:400](../../quantbot/paper/runner.py#L400)); the rejected seq=104 left no committed mutation. Recovery re-ran and advanced cleanly to seq 119.
4. Independent corroboration: the **lab cross-check** ("engine and independent replay agree row-by-row", PASS — §4) re-derives the ledger from source via a separate replay engine and found **zero disagreements**.

**Net:** the bad row failed closed at the write gate; append-only + watermark-last semantics meant no partial state survived. Production recovery succeeded; timer re-enabled; lane back on autopilot. **No evidence of silent corruption.**

> Residual caveat: the cross-check re-derives from the **same OHLCV source**, so it proves *arithmetic* consistency, not *external price truth* (see F11).

---

## 10. Footguns / Red Flags (red-team)

Ranked by importance for the edge question.

| # | Footgun | Status | Evidence |
|---|---|---|---|
| **F1** | **Validation lane ≠ paper lane (portfolio mismatch)** | 🔴 **CONFIRMED, HIGH** | Validated = volnorm + heat cap; forward paper = fixed $1k/symbol equal-weight, no heat cap. [config.py:323](../../quantbot/paper/config.py#L323), [engine.py:417](../../quantbot/paper/engine.py#L417). The GO does not describe what's running forward. |
| **F2** | **"GO" verdict is backtest, not forward** | 🔴 **CONFIRMED, HIGH** | Shadow observer = `run_validation_v2.py` re-run ([qnty-shadow-run.sh:36](../../ops/bin/qnty-shadow-run.sh#L36)); verdict computed over a rolling **historical** 500-bar window. A "GO based on shadow/backtest rather than forward paper." |
| **F3** | **Misleading benchmark** | 🟠 CONFIRMED, MED | "Excess return" benchmarks against a **gross always-long** basket that lost −199% (log) over the window ([drawdown_summary.json](../../output/validation_v2/drawdown_summary.json)). Beating a crashing benchmark ≠ edge. Benchmark is gross; strategy is carry-net — asymmetric comparison (caveat_note acknowledges). |
| **F4** | **Too few forward observations** | 🔴 **CONFIRMED, HIGH** | ≈13 batches / seq 119; single-digit-to-low-tens of committed forward bars. No statistical power for any edge sign. |
| **F5** | **Null baseline / benchmark not on the forward lane** | 🟠 LIKELY, MED | Forward paper has no parallel always-flat or always-long null to compare against; we cannot tell if −1.56% beat or lagged "do nothing" without the forward benchmark series. |
| **F6** | **Long-only momentum in a down/choppy regime** | 🟠 STRUCTURAL | Loss is directional (unreal −96, realized −54), not cost-driven. Long-only has no way to profit from the down move it's exposed to. |
| **F7** | **Ledger validates itself, not independent marks** | 🟠 PARTIAL | Reconcile re-derives net from stored components and ties equity to accumulators; marks come from the **same** OHLCV CSVs. Lab cross-check mitigates *arithmetic* but not *price-source* independence. |
| **F8** | **Stale universe table** | 🟡 LOW-MED | `QUARTERLY_UNIVERSES` populated only through `2025-10-01` ([quarterly_universe.py](../../quantbot/data/quarterly_universe.py)); a mid-2026 forward window silently reuses the 2025-Q4 top-5. Not point-in-time-correct for 2026. |
| **F9** | **Timestamp string comparison in watermark dedupe** | 🟡 LOW | Eligibility uses parsed instants (correct, [engine.py:203](../../quantbot/paper/engine.py#L203)), but `if ts <= watermark` is a **string** compare ([engine.py:211](../../quantbot/paper/engine.py#L211)). Safe only while the `%Y-%m-%dT%H:%M:%S` format is uniform; fragile if a `Z`-suffixed or offset ts ever enters. |
| **F10** | **Funding treatment differs across lanes** | 🟡 LOW | Observer diagnostic uses `abs(funding)*3` (symmetric penalty, [run_validation_v2.py:269](../../scripts/run_validation_v2.py#L269)); paper engine uses **signed** funding (longs pay when >0). Paper ignores the observer's `weighted_return`, so no direct corruption, but the lanes are not funding-comparable. |
| **F11** | **No exogenous price oracle** | 🟡 LOW | Same as F7 — a bad OHLCV refresh would mark the book wrong and reconcile would still pass. Mitigated by data-refresh provenance but not independently re-derived against a second venue. |
| **F12** | Lookahead / open-candle | 🟢 **NOT FOUND** | Fills at **T+1 open**, marks at **T close**; observer uses `filter_closed_bars` (full 8h interval must have closed) — [run_validation_v2.py:135](../../scripts/run_validation_v2.py#L135). Commits `8c7cdf7`/`b371228` previously fixed closed-candle/determinism. No lookahead in the executed path. |
| **F13** | Duplicate events / skipped seqs / open-candle publishing | 🟢 **NOT FOUND — VM CONFIRMED** | §2A confirms events seq 1…119 contiguous, 14 unique strictly sorted forward bars, zero off-grid timestamps. |
| **F14** | Replay/lab contamination of forward output | 🟢 **NOT FOUND — VM CONFIRMED** | Lab writes to `output/lab/cross_check/`; shadow writes only `forward_obs_v1/`; paper writes only `paper_pnl_v1/`. §2A confirms no stray files under `paper_pnl_v1/`. |
| **F15** | Overfitting / parameter mining | 🟡 LATENT | Grid is pre-declared 4-point and frozen ([tsmom_strategy.py:20](../../quantbot/strategy/tsmom_strategy.py#L20)); validation uses the single `rp=20,th=0` point. Low mining surface, but the *vol-quantile 0.65*, *heat cap 1.0*, *vol lookback 90* were chosen at Stage 4 — provenance of those choices is for Browser Claude to interrogate. |
| **F16** | Randomized delay / timer / watermark issues | 🟢 ADDRESSED | Watchdog + one-cycle watermark-lag fix (`2d144cf`) and watermark watchdog (`80b1614`) exist; 8h grace window logic in `quantbot/sidecars/time_bars.py`. Confirm watchdog status = OK on VM (§12). |

---

## 11. What Is Still Unknown / Still Needs Review

VM-read unknowns from the original draft are now partially closed by §2A:

- **Closed by §2A:** `forward_start_ts` (`2026-06-14T00:00:00Z`), exact committed forward bars (14), per-trade decomposition (5 closed trades, all losers), drawdown path, monotonicity, contamination check, verifier status, and true current post-fill open positions.
- **Reclassified by P0/P1 docs:** `paper_pnl_v1` is a fixed-notional baseline/control lane only; Lane B (`paper_pnl_volnorm_v1`) is planned but not implemented; V2 edge remains `EDGE_UNPROVEN`.

Still open:

1. **Forward null/benchmark series** — how did −1.56% compare to always-flat and always-long over the same forward bars?
2. Whether the **2026 universe** should differ from the 2025-Q4 top-5 (F8), and what universe should be frozen at Lane B start.
3. Independent **price-source corroboration** of the marks (F7/F11).
4. Provenance/justification of Stage-4 hyperparameters (vol quantile, heat cap, lookback) — overfitting interrogation (F15).
5. Exact additive observer artifact needed for Lane B per-symbol V2 target weights. The current observer output is insufficient for Lane B sizing unless it emits auditable decision-time target weights/provenance.

---

## 12. SQLite-Aware Follow-Ups

The original JSONL-oriented command list is **superseded**. The authoritative forward state is the SQLite DB at `/srv/qnty/output/paper_pnl_v1/paper_ledger.db`.

All future VM checks must be **read-only**:

- Open SQLite with `mode=ro` and `PRAGMA query_only=1`, or use an equivalent read-only snapshot.
- Write any reports, receipts, scratch extracts, null comparator outputs, or replay/cross-check outputs only to `/tmp` or a separate scratch/output directory.
- Never write replay/lab/scratch output into `/srv/qnty/output/paper_pnl_v1`.
- Do not edit, reset, vacuum, migrate, or otherwise mutate `/srv/qnty/output/paper_pnl_v1/paper_ledger.db`.
- Do not start/stop timers or manually run `qnty-paper-pnl.service`.

Remaining useful read-only follow-ups:

1. Build an always-flat and always-long forward null comparator over the same 14 baseline bars, writing only to `/tmp` or a separate scratch dir.
2. Re-run or extend independent replay checks only into a temp output directory, never into `paper_pnl_v1`.
3. Add an additive observer artifact for Lane B target weights before any `paper_pnl_volnorm_v1` implementation.
4. Confirm future batches record a non-null `git_sha` before Lane B starts; a Lane B first batch with `git_sha=None` is a hard stop.

---

## 13. Final Local Verdict

### `EDGE_UNPROVEN` / `NOT ENOUGH EVIDENCE` (to judge strategy edge)

**Reasoning:**
- **Infrastructure / data integrity: PASS — now VM-confirmed (§2A).** Verifier status `OK`/0 failures; 14 forward bars, events seq 1…119 contiguous, zero off-grid timestamps, no duplicate bars, no output contamination. The accounting engine is hardened (T+1 fills, closed-bar-only, append-only, multi-gate reconcile + final integrity gate, independent replay cross-check PASS). The PR #15 incident failed closed (batch 13 cleanly caught up 2 bars) and did not corrupt the ledger. New provenance gap **F17**: batches record `git_sha=None`, so the DB cannot self-attest the running commit (config_hash is stable across all batches, which partially mitigates).
- **Strategy edge: UNPROVEN and currently unmeasurable** because:
  1. **The validated portfolio is not the one running forward** (F1) — the GO describes volnorm+heat-cap; the forward paper is fixed-notional equal-weight.
  2. **The "GO" is a rolling backtest, not forward evidence** (F2), benchmarked against a crashing basket (F3).
  3. **The forward sample is far too small** (F4) to establish edge in either direction.
  4. The forward loss (−1.56%) is **directional, not cost-driven**, and is a long-only momentum book into an unfavourable regime — expected to be negative there, and therefore **not itself disqualifying**.

**Why not "PARK":** nothing here shows the baseline machinery is *broken* — the loss is small, costs are negligible, drawdown is 8× inside limits, and the machinery is sound. **Why not "PLAUSIBLE TO CONTINUE" as V2 evidence:** the one number that *is* admissible (forward paper) measures a *different portfolio* than the one that was validated, over too short a window. We literally do not yet have a clean forward read on the validated V2 strategy.

**Recommended next step (for the operator / Browser Claude, not executed here):**
1. Treat `paper_pnl_v1` as **baseline/control evidence only**. It does not validate or invalidate V2 volnorm.
2. Keep `INFRA OK / BASELINE CONTROL RUNNING / V2 EDGE UNTESTED FORWARD / LANE B PLANNED / NO LIVE`.
3. Stand up a **read-only forward null/always-long comparator** on the same forward bars (F5) so −1.56% becomes interpretable.
4. Before Lane B implementation, require an additive decision-time target-weight artifact and a separate `/srv/qnty/output/paper_pnl_volnorm_v1` SQLite lane with non-null `git_sha`.
5. Hand F2/F3/F15 to Browser Claude for hostile literature review (long-only crypto TSMOM edge, benchmark choice, hyperparameter provenance).

**No profitability claim is made. No live trading is recommended. Strategy edge remains unproven. Continued *paper* observation is baseline/control observation only until additive Lane B exists.**

---

*End of evidence pack. Generated read-only against the local repo at commit `5821b67`; key forward facts were VM-confirmed through read-only SQLite inspection of `/srv/qnty/output/paper_pnl_v1/paper_ledger.db`.*
