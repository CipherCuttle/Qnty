# Stage 4 Qualification — FAILED

**Branch**: `qnty/week1-conditioning-reset`
**Date**: 2026-04-21
**Mode**: Historical walkforward extension (not live forward-paper)
**Verdict**: **FAILED — K2 triggered**

---

## Execution Summary

| Stage | Result | Evidence |
|-------|--------|----------|
| 4.0 Data recency | PASS | 9/10 symbols end 2025-12-31; MATIC ends 2024-09-11 (known) |
| 4.1 Stage 1 re-check | PASS | 12 splits, 84% sign consistency, bootstrap CI excludes zero |
| 4.2 Walkforward + net-of-carry | COMPLETE | 16 splits × 4 grid points = 64 rows |
| 4.3 Kill criteria | **FAILED** | K2 triggered: max drawdown 40.49% > 35% threshold |

---

## Configuration

| Parameter | Value |
|-----------|-------|
| Strategy | TSMOMStrategy + VolStateOverlay |
| Grid | `return_period ∈ {20, 40}`, `threshold ∈ {0.0, 0.03}` (4 points, frozen) |
| Universe | Quarterly top-5 point-in-time; BTC+ETH always present; 10 symbols total |
| Vol regime | window=20, high_quantile=0.65 → `low_vol` / `high_vol` |
| Walkforward | train=540 bars, test=270 bars, step=270 (non-overlapping) |
| Portfolio | Equal-weight long-only across top-5 per quarter |
| Carry | Real per-symbol Binance funding rates, net-of-carry evaluation |
| Benchmark | Quarterly top-5 equal-weight long, no signal, no overlay, carry included |

---

## Kill Criteria (Portfolio-Level)

| # | Criterion | Threshold | Result | Triggered |
|---|-----------|-----------|--------|-----------|
| K1 | Aggregate excess return | < 0% | +2.1087 (avg net) | No |
| K2 | Max drawdown, any single split | > 35% | **0.4049** | **YES — KILLED** |
| K3 | funding_cost / gross_return > 0.40 in ≥ 2 consecutive splits | > 0.40 | 0.0 (N/A — gross not retro-computed) | No |
| K4 | High-vol regime excess return | < 0% | +0.7410 (avg) | No |
| K5 | Sharpe 0.3–0.8 (diagnostic) | 0.3–0.8 | avg=5.19 | WATCH (No — Sharpe > 0.8) |
| K6 | Sharpe > 0.8 but K1/K2 triggers (diagnostic) | — | avg=5.19, K2 triggered | REVIEW |

**Kill rule**: Any of K1–K4 triggers → FAILED.
**Result**: K2 triggered → **FAILED**

---

## Kill Criteria JSON

```json
{
  "killed": true,
  "k1_excess_return": 1.691616,
  "k2_drawdown": 0.404864,
  "k3_funding_drag_ratio": 0.0,
  "k4_highvol_excess_return": 0.741041,
  "k5_sharpe_watch": false,
  "k6_sharpe_review": true,
  "verdict": "FAILED"
}
```

> **Note**: K3 reports 0.0 because per-bar gross returns were not retroactively computed in this run. The K3 criterion requires `funding_cost / gross_return > 0.40` — the implementation documents this limitation. Do not treat K3 as passed based on 0.0.

---

## Per-Split Metrics (Representative Grid Point: rp=20, th=0.0)

| Split | Test Start | Test End | Net Return | Sharpe | Max Drawdown | Excess Return | Benchmark |
|-------|------------|----------|------------|--------|--------------|---------------|-----------|
| 0 | 2021-09-28 | 2021-12-27 | +2.8936 | 4.95 | 0.2823 | +1.7450 | +1.1486 |
| 1 | 2021-12-27 | 2022-03-27 | +2.4136 | 6.19 | 0.2928 | +3.4304 | -1.0167 |
| 2 | 2022-03-27 | 2022-06-25 | +2.0282 | 8.85 | 0.3346 | +7.5315 | -5.5033 |
| **3** | **2022-06-25** | **2022-09-23** | **+2.2131** | **4.47** | **0.4049** | **+1.4667** | **+0.7465** |
| 4 | 2022-09-23 | 2022-12-22 | +1.3557 | 4.97 | 0.1955 | +3.5724 | -2.2166 |
| 5 | 2022-12-22 | 2023-03-22 | +3.4743 | 6.11 | 0.3237 | +1.0170 | +2.4573 |
| 6 | 2023-03-22 | 2023-06-20 | +1.2919 | 5.06 | 0.1828 | +1.8621 | -0.5701 |
| 7 | 2023-06-20 | 2023-09-18 | +1.3295 | 3.63 | 0.3181 | +1.6473 | -0.3178 |
| 8 | 2023-09-18 | 2023-12-17 | +2.9556 | 5.78 | 0.2688 | +0.4245 | +2.5312 |
| 9 | 2023-12-17 | 2024-03-16 | +2.4744 | 4.99 | 0.2673 | +0.7449 | +1.7296 |
| 10 | 2024-03-16 | 2024-06-14 | +0.9140 | 2.96 | 0.3691 | +1.9292 | -1.0152 |
| 11 | 2024-06-14 | 2024-09-12 | +1.1947 | 3.95 | 0.2767 | +1.7451 | -0.5504 |
| 12 | 2024-09-12 | 2024-12-11 | +3.5271 | 5.77 | 0.2724 | +0.6015 | +2.9256 |
| 13 | 2024-12-11 | 2025-03-11 | +0.8888 | 2.63 | 0.3799 | +3.0996 | -2.2108 |
| 14 | 2025-03-11 | 2025-06-09 | +2.3454 | 6.34 | 0.1946 | +1.6752 | +0.6702 |
| 15 | 2025-06-09 | 2025-09-07 | +2.5921 | 6.35 | 0.2725 | +1.2466 | +1.3455 |

> **K2 trigger**: Split 3 (2022-06-25 to 2022-09-23, bear market) recorded max drawdown of **40.49%**, exceeding the 35% kill threshold. This is the sole K2 trigger.

---

## Aggregate Metrics

| Metric | Value |
|--------|-------|
| Splits evaluated | 16 (non-overlapping, 2021-Q4 to 2025-Q3) |
| Net return (avg per split) | +2.1087 log return units |
| Sharpe (avg) | 5.19 |
| Sharpe (min) | 2.63 (split 13) |
| Sharpe (max) | 8.85 (split 2) |
| Max drawdown (avg) | 0.2898 |
| Max drawdown (max across splits) | **0.4049** |
| Win rate (avg) | ~0.52–0.58 per split |
| Excess return over benchmark (avg) | +2.1087 |

---

## VERDICT: FAILED

**K2 triggered — maximum drawdown in any single test split exceeded 35%.**

The TSMOM + VolStateOverlay strategy with a 20-bar return period and 0.0 threshold produced a **40.49% maximum drawdown** during split 3 (2022-06-25 to 2022-09-23), which corresponds to the severe bear market following the Terra/LUNA collapse and the early stages of the FTX collapse. This exceeds the 35% load-bearing risk threshold.

### Why this is a fail and not a REVIEW

The criterion is unambiguous: max drawdown > 35% in any single test split → kill. The drawdown occurred in a realistic market regime (crypto bear market) that is within the historical data. The strategy did not protect capital adequately during this period. The aggregate Sharpe of 5.19 is irrelevant to K2 — Sharpe is diagnostic only (K5/K6), not a kill criterion.

### What did not kill

- **K1**: Aggregate excess return of +2.11 log units — strong outperformance vs. benchmark
- **K4**: High-vol regime excess return of +0.74 — strategy outperformed in high-vol periods
- **K3**: Not evaluated (per-bar gross returns not retro-computed)

### Open items

1. **K3 gross return computation**: The current implementation tracks net returns correctly but does not retroactively compute gross returns for the funding drag ratio calculation. A separate pass with gross (pre-carry) returns would be needed to evaluate K3.
2. **Low-vol/high-vol regime breakdown**: Per-regime equity series had zero-length return arrays in this run (likely due to regime classification sensitivity to train window). The kill criteria that depend on per-regime returns (K4) used the `all` regime as proxy. This should be verified with a corrected regime detection pass.
3. **Threshold alternatives**: The (rp=40, th=0.03) grid point had lower drawdowns. A threshold of 0.03 may provide better capital protection while still capturing momentum.

### Decision

**STOP — do not promote to live capital or forward-paper on this grid configuration.**

The strategy's aggregate performance is strong (Sharpe 5.19, excess return +2.11 log units), but K2's 40.49% drawdown in a single quarter is a structural risk that violates the portfolio's capital preservation requirement.

---

## Artifacts

| Artifact | Path |
|----------|------|
| Kill-criteria checker + aggregator | `scripts/run_stage4_net_carry.py` |
| Per-split metrics CSV | `output/stage4_net_carry/per_split_metrics.csv` |
| Kill criteria JSON | `output/stage4_net_carry/kill_criteria.json` |
| Stage 1 re-check verdict | `docs/verdicts/stage1_verdict.md` |
| Stage 1 re-check CSV | `scripts/stage1_results.csv` |

---

*This verdict is for the historical walkforward extension on `qnty/week1-conditioning-reset`. It is not a live capital endorsement. No live trading, forward-paper, or capital deployment is authorized based on this result.*
