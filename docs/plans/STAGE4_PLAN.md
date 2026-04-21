# Stage 4 Plan — Branch Qualification: Multi-Asset TSMOM Walkforward Extension

## FACTS

1. Current date: **2026-04-21** (UTC+2 Stockholm).
2. Branch: `qnty/week1-conditioning-reset`, dirty state. Last commits fc84702 / c5538ee / 674165c.
3. Prior stages: Stage 1 **PASS**, Stage 2 **CONTINUE** (mixed stress results — open items not yet resolved).
4. Strategy: **TSMOMStrategy + VolStateOverlay**. Frozen 4-point grid: `return_period ∈ {20, 40}`, `threshold ∈ {0.0, 0.03}`. Long-only (flat when threshold not met). Not RFB. Not BTC-only.
5. Universe: **quarterly top-5 point-in-time** — BTC+ETH always present, remaining 3 slots by trailing volume. Symbols: BTC, ETH, XRP, LINK, DOT, BNB, ADA, MATIC, SOL, AVAX.
6. Vol regime: window=20, high_quantile=0.65 → `low_vol` / `high_vol`. Trend-regime is deferred to a future stage candidate.
7. Walkforward structure: train=540 bars (≈1 quarter), test=270 bars (≈0.5 quarter), step=270 (non-overlapping quarters).
8. Portfolio: equal-weight long-only across top-5 symbols per quarter.
9. Carry: real per-symbol Binance funding rates, net-of-carry evaluation.
10. **Data is present on disk**: `data/{SYMBOL}_8h_ohlcv.csv` and `data/{SYMBOL}_8h_funding.csv` for all 10 symbols. `load_all_ohlcv()` returns all 10 symbols with 5478 bars each (MATIC: 4049). No data acquisition needed.
11. The THT0 Shadow adapter is excluded — verdict is SHADOW FAIL / DO NOT USE.
12. `scripts/run_base_forward_paper.py` uses `RollingReturnBreakoutStrategy` on BTCUSDT only — it is RFB-contaminated and excluded from this plan.
13. What exists: `quantbot/experiment/walkforward_runner.py`, `quantbot/experiment/stage1_diagnostics.py`, `quantbot/experiment/stage2_stress_diagnostics.py`, `quantbot/experiment/portfolio_evaluator.py`.
14. What does not yet exist: a kill-criteria checker script for the walkforward extension output, a combined net-of-carry walkforward extension report.

---

## ASSUMPTIONS

1. **Mode — Historical Walkforward Extension**: Stage 4 extends the existing multi-asset walkforward analysis by running the frozen 4-point grid across all available walkforward splits, covering the full date range of the existing OHLCV files. This is **not** a live forward-paper run. Live forward-paper (live trading from current date) is a separate subsequent stage and is not part of this plan.
2. **Config — Single Frozen Grid, Pre-Registered**: The 4-point grid is already frozen in [`quantbot/strategy/tsmom_strategy.py`](quantbot/strategy/tsmom_strategy.py) as `TSMOM_GRID`. No parameter search or expansion. Stage 4 validates the frozen grid across all walkforward splits.
3. **Benchmark — Quarterly Top-5 Equal-Weight Long (No Signal)**: The benchmark is a long-only equal-weight portfolio of the same top-5 quarterly universe, with no TSMOM signal and no vol-state overlay. It rebalances quarterly. It is the natural apples-to-apples comparison because it holds the same instruments with the same weights but without any signal. Carry is included in both strategy and benchmark for fair comparison.
4. **Data recency**: The OHLCV and funding files exist and are populated. Their end-of-data date is verified in Stage 4.0. No fetching is required unless recency check reveals a gap.
5. **Kill criteria are branch-specific**: Criteria apply to the multi-asset TSMOM + VolStateOverlay portfolio-level aggregate on `qnty/week1-conditioning-reset`. Not applicable to RFB, not applicable to single-asset.

---

## SPECULATION

1. The OHLCV files may not extend to 2026-04-21 — they may end earlier (e.g., 2025-Q4). Stage 4.0's recency check will confirm this. If they end before the current date and historical extension is the chosen mode, this is acceptable as long as the walkforward has meaningful test coverage.
2. Sharpe is deprioritized as a primary kill criterion because it is hypersensitive to the return accumulation window and can pass/fail on a single outlier bar. It is retained as a secondary diagnostic only.
3. Funding drag is meaningful only relative to gross edge. A 6% funding drag on a 20% gross-return portfolio is structurally different from the same drag on a 4% gross-return portfolio. The revised K3 reflects this.

---

## PLAN

### Stage 4.0 — Data Recency Verification

**Purpose**: Confirm the existing OHLCV and funding files are sufficient for the walkforward extension. No fetching unless recency check fails.

1. Run:
   ```python
   python -c "
   from quantbot.data.multi_asset_loader import load_all_ohlcv
   from quantbot.data.funding_loader import load_funding
   bars = load_all_ohlcv()
   for sym, df in bars.items():
       print(f'{sym}: {df.index[0]} to {df.index[-1]}, {len(df)} bars')
   "
   ```
2. Record the end-of-data date for each symbol.
3. If any symbol's data ends before 2025-06-01 → Stage 4 is blocked; write a data recency failure verdict and stop.
4. If data ends between 2025-06-01 and 2025-12-01 → acceptable for historical walkforward extension; note in plan.
5. If data ends 2025-12-01 or later → proceed.

**Verification**: End-of-data date for majority of symbols (≥ 8/10) is 2025-06-01 or later.

---

### Stage 4.1 — Re-Run Stage 1 Diagnostics with Full Multi-Asset Data

**Purpose**: Confirm the Stage 1 PASS verdict still holds with the complete 10-symbol dataset. This is a sanity check before the walkforward extension.

Execution:
```
python scripts/run_stage1.py
```

Pass criteria (unchanged):
- ≥ 60% of vol-regime × grid-cell combinations beat the benchmark
- Bootstrap confidence interval excludes zero for the majority of regime combinations
- ≥ 5 trials per regime

**Failure handling**: If Stage 1 returns FAIL → write `docs/verdicts/stage4_stage1_recheck_FAILED.md` and stop. Do not proceed to Stage 4.2.

**Verification**: `docs/verdicts/stage4_stage1_recheck.md` written with PASS verdict.

---

### Stage 4.2 — Walkforward Extension with Net-of-Carry Evaluation

**Purpose**: Extend the walkforward across all available splits. Evaluate the frozen 4-point grid with real per-symbol funding costs.

1. Run the walkforward runner with net-of-carry enabled for all 10 symbols across all non-overlapping splits.
2. Output per-split: total return, Sharpe, max drawdown, win rate, funding cost drag, per-regime breakdown.
3. Compare each split's strategy performance against the quarterly top-5 equal-weight long benchmark (same universe, no signal, no overlay).
4. Aggregate across splits: simple average of per-split metrics (equal weight per split, not per bar).

**What must still be built**:
- A script or module that reads the walkforward output and produces a combined net-of-carry report with per-split and aggregate metrics. This does not yet exist as a single artifact.

**Verification**: All non-overlapping walkforward splits complete. No NaN in equity series. Per-split CSVs with SHA256 manifests written.

---

### Stage 4.3 — Kill Criteria (Portfolio-Level, Branch-Specific)

These criteria apply to the **portfolio-level aggregate** across all walkforward test splits. Not individual symbols. Not individual splits in isolation. Sharpe is **secondary / diagnostic only** — it does not kill.

| # | Criterion | Threshold | Rationale |
|---|-----------|-----------|-----------|
| K1 | **Aggregate test-period excess return over benchmark** | < 0% (strategy underperforms its benchmark in aggregate) | The strategy must demonstrably add value over the naive top-5 equal-weight long. If it cannot beat its own benchmark net-of-carry, there is no reason to run it. |
| K2 | **Max drawdown in any single test split** | > 35% from peak | Load-bearing risk. Long-only multi-asset portfolio should not produce 35%+ drawdowns in a single quarter unless the signal is broken. |
| K3 | **Funding drag relative to gross edge** | `funding_cost / gross_return > 0.40` in ≥ 2 consecutive test splits | Funding costs are only disqualifying if they consume more than 40% of gross edge in consecutive quarters. Below 40% means the strategy is still earning its carry. A 6% drag on 20% gross is tolerable; the same 6% on 5% gross is not. |
| K4 | **High-vol regime excess return** | < 0% in high_vol splits specifically | Vol-state overlay earns its keep in high_vol periods. If the strategy underperforms its benchmark specifically in high_vol regimes, the overlay is not protective when it matters most. |

**K5 (diagnostic-only, non-killing)**: Aggregate Sharpe 0.3–0.8 → **WATCH — review required**. Record in verdict without killing.

**K6 (diagnostic-only, non-killing)**: Sharpe > 0.8 but K1 or K2 triggers → **Review required** — strong Sharpe does not override a drawdown blow-up or negative excess return.

**Kill rule**: **Any of K1–K4 triggers → FAILED**. K5/K6 are diagnostic only and do not kill independently.

**No kill on**: isolated single-split losing streak, single-symbol blowup in isolation, vol-regime transition events in isolation, Sharpe values from splits with fewer than 90 bars, Sharpe below threshold as a standalone criterion.

**Verification**: Kill-criteria checker reads walkforward extension output and outputs:
```json
{
  "killed": bool,
  "k1_excess_return": float,
  "k2_drawdown": float,
  "k3_funding_drag_ratio": float,
  "k4_highvol_excess_return": float,
  "k5_sharpe_watch": bool,
  "k6_sharpe_review": bool,
  "verdict": "PASSED|FAILED|WATCH|REVIEW"
}
```

---

### Stage 4.4 — Verdict

1. **If K1–K4 triggers**: write `docs/verdicts/stage4_qualification_FAILED.md` — evidence-first, no spin. Include which criteria triggered, per-split breakdown, net-of-carry metrics, kill-criteria JSON output.
2. **If no K1–K4 triggers**: write `docs/verdicts/stage4_qualification_PASSED.md` — aggregate metrics, per-regime breakdown, net-of-carry summary, K5/K6 diagnostic status. Explicitly state: this is a walkforward extension verdict, not a live capital endorsement.
3. **In both cases**: record exact grid config, vol regime settings, walkforward coverage (date range of splits), end-of-data dates per symbol, kill-criteria JSON output.

---

## What Exists vs What Must Still Be Built

| Component | Status |
|-----------|--------|
| `quantbot/strategy/tsmom_strategy.py` (TSMOM_GRID) | Exists |
| `quantbot/strategy/vol_state_overlay.py` | Exists |
| `quantbot/data/quarterly_universe.py` | Exists |
| `quantbot/experiment/walkforward_runner.py` | Exists |
| `quantbot/experiment/stage1_diagnostics.py` | Exists |
| `quantbot/experiment/portfolio_evaluator.py` | Exists |
| `quantbot/experiment/stage2_stress_diagnostics.py` | Exists |
| `scripts/run_stage1.py` | Exists |
| `scripts/run_stage2_stress.py` | Exists |
| 10-symbol OHLCV + funding data on disk | Exists |
| Kill-criteria checker for walkforward extension output | **Must be built** |
| Combined net-of-carry walkforward extension report | **Must be built** |

---

## What This Plan Does NOT Include

- No live forward-paper execution from 2026-04-22.
- No new runner build (existing walkforward_runner is sufficient; only the kill-criteria checker and report aggregator are new).
- No THT0 / shadow adapter material.
- No RFB naming or BTC-only assumptions.
- No multi-config tournament.
- No live capital deployment.
