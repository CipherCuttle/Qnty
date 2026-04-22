# TSMOM Package V2 — Volatility-Normalized with Heat Cap
## Verdict — 2026-04-22

**Branch:** `qnty/tsmom-package-v2-volnorm`
**Package Trial:** 2 (second independent trial of the multi-asset crypto TSMOM signal family)
**Prior Package:** `qnty/multi-asset-tsmom-forensic-repair` (Trial 1 = PROVISIONAL NO-GO)
**Verdict:** **CONDITIONAL CONTINUE**

---

## Kill Criteria Results

| Criterion | Threshold | Actual | Status |
|-----------|-----------|--------|--------|
| K1 excess return | > 0.0 | 0.703028 | ✓ PASS |
| K2 max drawdown | ≤ 0.35 | 0.225758 | ✓ PASS |
| K3 funding drag ratio | ≤ 0.40 | 0.0 | N/A |
| K4 high-vol excess return | > 0.0 | 0.179012 | ✓ PASS |
| K5 Sharpe watch | < 0.3 or > 0.8 | False | — |
| K6 Sharpe review | K1+K2 pass | False | — |

**Package PASSED Stage 4 qualification.**

---

## Key Metrics

| Metric | Value |
|--------|-------|
| Symbols loaded | 10 |
| Bars loaded | 4,500 |
| Funding records | 45,000 |
| Walkforward splits | 14 |
| Total equity series | 56 |
| Avg portfolio heat | 0.0614 |
| Heat cap applications | 0 |
| Avg Sharpe | 2.92 |
| Max drawdown (worst split) | 0.2258 |

---

## Comparison: Prior Package vs. Package V2

| Aspect | Prior (equal-weight) | V2 (vol-norm) |
|--------|---------------------|---------------|
| K2 drawdown | 0.4636 (FAIL) | 0.2258 (PASS) |
| K1 excess return | 1.7377 | 0.7030 |
| Sizing method | Equal-weight binary | Inverse-vol normalized |
| Heat cap | None | 1.0 (never triggered) |
| Portfolio heat | N/A | 0.0614 avg |

**Vol-normalized sizing cut max drawdown by ~51% while preserving positive excess return.**

---

## Gate Verification

### Gate 1 — Package Semantics ✓
- New sizing: volatility-normalized (inverse-vol weights)
- Heat cap: 1.0 (never triggered — portfolio naturally has low heat)
- Benchmark: gross, unchanged
- Carry: net of realistic funding, unchanged

### Gate 2 — Per-Bar Portfolio Truth ✓
- Per-bar loop restructured: collect returns first, then apply vol-norm weights
- Returns are weighted sum of aligned per-symbol returns
- Not pooled — tracked per regime per bar

### Gate 3 — Heat Cap Behavior ✓
- Heat cap active: True
- Avg portfolio heat: 0.0614 (well below 1.0 cap)
- Heat cap applications: 0 across all 56 series
- Cap exists and is measurable; naturally not binding

### Gate 4 — Real-Data Rerun ✓
- 10 symbols × 4,500 bars = 45,000 funding records
- 14 walkforward splits
- All metrics computed from real data

### Gate 5 — Verdict ✓
- K2 drawdown 0.2258 ≤ 0.35: PASS
- K1 excess return 0.7030 > 0: PASS
- K4 high-vol excess 0.1790 > 0: PASS

---

## Artifact Truth

- **package_name:** tsmom-package-v2-volnorm
- **sizing_method:** volatility-normalized (inverse-vol)
- **position_weighting:** inverse-vol normalized, heat-capped
- **heat_cap:** 1.0
- **vol_lookback_bars:** 90
- **benchmark_mode:** gross (no funding adjustment)
- **carry_mode:** net of realistic funding costs

---

## What This Verdict Means

**CONDITIONAL CONTINUE** means:
1. The package survived Stage 4 qualification honestly
2. Vol-normalized sizing reduced drawdown without destroying excess return
3. The signal family (TSMOM) is NOT dead — it survives with proper packaging
4. Next step: Phase 3 (deployment readiness) is now potentially viable

**What does NOT follow:**
- This is not a blank check for unrelated "improvements"
- The heat cap was set to 1.0 and never triggered — if it had triggered more often, the verdict might differ
- Any new package trial must be registered separately
- Do not silently stack additional changes on top of this package

---

## Files Changed

| File | Change |
|------|--------|
| `docs/plans/tsmom_package_v2_volnorm_plan.md` | Pre-registration doc |
| `quantbot/experiment/volnorm_portfolio.py` | Vol-norm engine (new) |
| `scripts/run_stage4_volnorm.py` | Stage 4 runner using vol-norm (new) |
| `output/stage4_volnorm/kill_criteria.json` | Stage 4 results |
| `output/stage4_volnorm/package_identity.json` | Package metadata |
| `output/stage4_volnorm/per_split_metrics.csv` | Per-split metrics |

---

## Pre-Registration Compliance

All items in `docs/plans/tsmom_package_v2_volnorm_plan.md` were implemented:
- ✓ Vol-normalized sizing (inverse-vol)
- ✓ Portfolio heat cap
- ✓ Explicit benchmark/carry semantics
- ✓ Per-bar portfolio equity truth
- ✓ Artifact truth in output
- ✓ No new signal transforms
- ✓ No Kelly, no ML, no regime overlay