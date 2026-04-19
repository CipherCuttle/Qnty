# RFB Canonical Status

**Date:** 2026-04-19
**Strategy:** RegimeFilteredBreakoutStrategy (RFB) — PRIMARY CANDIDATE
**Branch:** `main`

---

## Current Status: PRIMARY BTC-ONLY HYPOTHESIS

**RFB is the primary candidate. BASE (RollingReturnBreakoutStrategy) is the secondary comparator.**

RFB beats BASE net-of-costs in apples-to-apples BTC forward comparison.

---

## What Is Fixed (Canonical)

| Item | Status | Evidence |
|------|--------|---------|
| Economics fix (cost double-counting) | ✅ Fixed on main | [`a1265af`](origin/main) |
| RFB regime-state bug (`_rfb_bars` unbounded) | ✅ Fixed | [`quantbot/strategy/regime_filtered_breakout.py:49-53`](quantbot/strategy/regime_filtered_breakout.py:49) |
| RFB walkforward registration | ✅ Fixed | [`walkforward_runner.py`](quantbot/experiment/walkforward_runner.py) import |
| Regression tests | ✅ Added | [`tests/test_regime_filtered_breakout.py`](tests/test_regime_filtered_breakout.py) |

---

## Apples-to-Apples BTC Comparison: RFB vs BASE

**Evidence:** [`base-vs-rfb-apples-to-apples-2026-04-19.md`](docs/verdicts/base-vs-rfb-apples-to-apples-2026-04-19.md)
**Fixture:** BTCUSDT_8h.csv (2190 bars, 12 walkforward windows)

| Metric | BASE (fee=10/slip=5) | RFB (fee=10/slip=5) | BASE (fee=20/slip=10) | RFB (fee=20/slip=10) |
|--------|---------------------|---------------------|----------------------|----------------------|
| signal_count | 61 | 37 | 61 | 37 |
| net_return_total | 0.3080 | **0.3161** | 0.1265 | **0.2051** |
| positive_windows | 9/12 | **10/12** | 6/12 | **9/12** |

**Key ratios:**
- RFB/BASE net @ 10/5: **1.026** (RFB wins by 2.6%)
- RFB/BASE net @ 20/10: **1.621** (RFB wins by 62.1%)
- RFB cost robustness: degrades 35.1% when costs double vs 58.9% for BASE

**VERDICT:** RFB wins net-of-costs at both cost settings. The regime filter is not just reducing signals proportionally — it produces superior net returns, especially under realistic cost assumptions (20/10).

---

## Validation Results (Corrected)

| Evidence | Result | Notes |
|----------|--------|-------|
| Walkforward (step=100, 18 splits) | **+22.93% net** | [`rfb-btc-harsher-validation-2026-04-19.md`](docs/verdicts/rfb-btc-harsher-validation-2026-04-19.md) |
| Walkforward (step=90, 21 splits, CLI) | **+42.54% net** | [`rfb-regime-bugfix-validation-2026-04-19.md`](docs/verdicts/rfb-regime-bugfix-validation-2026-04-19.md) |
| Fresh holdout [2100,2190) | **+3.50% net** | Per-bar compounding (corrected from buggy -5.41%) |
| Rolling holdout 10/5 [2000,2090) | **+2.61% net** | [`rfb-btc-rolling-holdout-validation-2026-04-19.md`](docs/verdicts/rfb-btc-rolling-holdout-validation-2026-04-19.md) |
| Rolling holdout 10/5 [2090,2180) | **+1.11% net** | Same doc |
| Rolling holdout 20/10 [2000,2180) | **+6.10% net** | Same doc |
| Regime gate correctness | ✅ All signals valid | All signals emitted during uptrend regime |

---

## What Is Falsified

| Claim | Verdict | Evidence |
|-------|---------|---------|
| ETHUSDT cross-symbol generalization | ❌ FALSIFIED | Per prior sprint results |
| explicit `high_vol` regime-gate refinement | ❌ FALSIFIED | Per [`rfb-refinement-verdict.md`](docs/verdicts/rfb-refinement-verdict.md) |
| BASE over RFB net-of-costs | ❌ FALSIFIED | Apples-to-apples comparison: RFB wins |

---

## What Is NOT Claimed

- No live-trading claims
- No cross-symbol generalization (BTC-only)
- No parameter tuning (BASELINE fixed)
- No new family work justified
- No further parameter tuning justified

---

## Architecture

```
RegimeFilteredBreakoutStrategy
├── trend_window: 20
├── trend_threshold: 0.001
├── allowed_trend_regimes: ['uptrend']
└── _rfb_bars: capped to trend_window+1 (bug fix)
    └── parent: RollingReturnBreakoutStrategy
        ├── rolling_return_period: 20
        ├── return_threshold: 0.05
        └── min_hold_bars: 3
```

---

## Key Finding

The prior fresh holdout result of **-5.41%** was computed with an inconsistent return model (trade-level, no compounding). The corrected per-bar compounding model (matching walkforward_runner) yields **+3.50%** — a positive result.

See: [`rfb-btc-rolling-holdout-validation-2026-04-19.md`](docs/verdicts/rfb-btc-rolling-holdout-validation-2026-04-19.md)

---

## History of Verdicts

| Doc | Status | Notes |
|-----|--------|-------|
| `rfb-refinement-verdict.md` | VALID | Walkforward results unchanged by bug fix |
| `rfb-btc-harsher-validation-2026-04-19.md` | VALID | 10/5 and 20/10 walkforward results valid |
| `rfb-regime-bugfix-validation-2026-04-19.md` | VALID | Bug fix confirmed, corrected holdout = +3.50% |
| `rfb-btc-holdout-validation-2026-04-19.md` | SUPERSEDED | Documented buggy behavior; corrected results in rolling-holdout doc |
| `rfb-btc-rolling-holdout-validation-2026-04-19.md` | CURRENT | Most comprehensive holdout validation |
| `base-vs-rfb-apples-to-apples-2026-04-19.md` | CURRENT | Apples-to-apples comparison: RFB wins |
