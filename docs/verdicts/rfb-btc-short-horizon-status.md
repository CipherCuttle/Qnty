# RFB — BTC Short-Horizon Status

**Date:** 2026-04-19
**Strategy:** RegimeFilteredBreakoutStrategy BASELINE (unchanged)
**Branch:** `main` at `646c494`

---

## Current Status: BTC-only, short-horizon, uptrend-sensitive research candidate

---

## Hypothesis (Frozen)

> RFB is a BTCUSDT-only, short-horizon (≤60 bars / ~30 days on 8h), uptrend-sensitive breakout candidate. Not claimed to work broadly across BTC conditions, not claimed to generalize to ETH or other symbols.

---

## Validation Evidence

### Strict Short-Horizon Forward Sprint (Apr–Aug 2024)

6 non-overlapping 60-bar forward windows, training `[1100, 1400)`:

| Window | Test Range | Period | BTC Δ | Net Return | Result |
|--------|------------|--------|-------|------------|--------|
| W1 | [1400, 1460) | Apr 11 – May 1, 2024 | −18.74% | **−1.57%** | NEGATIVE |
| W2 | [1460, 1520) | May 1 – May 21, 2024 | +19.64% | **+1.74%** | POSITIVE |
| W3 | [1520, 1580) | May 21 – Jun 10, 2024 | −0.12% | **0.00%** | ZERO_SIGNAL |
| W4 | [1580, 1640) | Jun 10 – Jun 30, 2024 | −11.25% | **0.00%** | ZERO_SIGNAL |
| W5 | [1640, 1700) | Jun 30 – Jul 20, 2024 | +6.46% | **+1.38%** | POSITIVE |
| W6 | [1700, 1760) | Jul 20 – Aug 9, 2024 | −10.92% | **0.00%** | ZERO_SIGNAL |

**Aggregate:** 2 positive / 1 negative / 3 zero-signal | **+1.55% net** | BTC −14.56%

All signals regime-valid (uptrend only). Evidence: [`rfb-btc-short-horizon-forward-validation-2026-04-19.md`](docs/verdicts/rfb-btc-short-horizon-forward-validation-2026-04-19.md)

### Adversarial Holdout Validation (Dec 2024 – Nov 2025)

| Config | Train | Test | Windows | Net Return | BTC Δ | Result |
|--------|-------|------|---------|------------|-------|--------|--------|
| rw=10, t=5 | [1700, 2000) | [300, 1290) | 11 × 90b | **+16.50%** | −2.47% | PASS |
| rw=20, t=10 | [1700, 2000) | [300, 1200) | 5 × 180b | **−33.86%** | −2.47% | FAIL |

Evidence: [`rfb-btc-adversarial-holdout-validation-2026-04-19.md`](docs/verdicts/rfb-btc-adversarial-holdout-validation-2026-04-19.md)

### Fresh Holdout Validation

| Window | Train | Test | Period | Net Return |
|--------|-------|------|--------|------------|
| Fresh | [1700, 2000) | [2100, 2190) | Dec 2024 | **+3.50%** |

Evidence: [`rfb-btc-fresh-holdout-validation-2026-04-19.md`](docs/verdicts/rfb-btc-fresh-holdout-validation-2026-04-19.md)

---

## What Is Falsified

| Claim | Verdict | Evidence |
|-------|---------|----------|
| ETHUSDT cross-symbol generalization | ❌ FALSIFIED | Prior sprint |
| Longer-horizon robustness (rw=20, t=10) | ❌ FALSIFIED | −33.86% on adversarial holdout |
| Consistent positive returns across all BTC conditions | ❌ FALSIFIED | W1 negative despite regime-valid signal |

---

## What Is NOT Claimed

- No live-trading claims
- No cross-symbol generalization
- No parameter tuning (BASELINE fixed)
- No claim that short-horizon edge is statistically significant (6 windows insufficient)

---

## Architecture (Unchanged)

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

## Honest Assessment

### Evidence FOR the thesis:
1. **rw=10, t=5 survives adversarial holdout** (+16.50% vs BTC −2.47%) — strongest evidence
2. **Short forward sprint produces net positive** (+1.55% vs BTC −14.56%) — edge via abstention
3. **All signals regime-valid** — no regime gate bypasses detected
4. **Abstention pattern** — 3/6 zero-signal windows avoided losses in adverse conditions

### Evidence AGAINST or qualifying the thesis:
1. **Narrow edge** — single losing window (W1: −1.57%) nearly wipes out two winning windows
2. **50% zero-signal rate** — strategy is often idle, making the "candidate" label weak
3. **rw=20, t=10 fails** — longer horizons are demonstrably adverse
4. **Insufficient statistical weight** — 6 windows with 3 active is not enough for confidence
5. **Same training across all windows** — not fully independent validation

### Edge Character:
- **Mostly abstention + selective participation** — the strategy survives by not trading when regime is invalid
- **Not active capture of many windows** — only 3/6 windows produced signals
- **Genuinely surviving hostile BTC conditions** — yes, via regime gate filtering, not market timing skill

---

## Retention Status

**VERDICT: RETAINED — BTC short-horizon candidate**

Scope:
- **Symbol:** BTCUSDT only
- **Horizon:** short forward windows (≤60 bars / ~30 days on 8h)
- **Market condition:** uptrend-sensitive, abstains in non-uptrend
- **Parameter constraint:** rw=10, t=5 variant preferred; rw=20, t=10 variant fails
- **Evidence weight:** MODERATE — positive across multiple validation types but narrow edge and limited statistical weight

---

## Next Steps (Not To Do)

- Do NOT restart family search
- Do NOT add new families
- Do NOT tune strategy parameters
- Do NOT broaden architecture
- Do NOT make live-trading claims
- Do NOT reopen cross-symbol claims

## Next Steps (Honest)

1. **Accumulate more windows** — 6 windows is insufficient for statistical confidence; more short-horizon forward tests needed
2. **Test varied training splits** — current sprint uses same training across all windows; varied training would strengthen independence
3. **Monitor rw=10, t=5 in live** — if deployed, track whether abstention pattern holds in real conditions
4. **Accept the narrow scope** — RFB is a narrow, regime-filtered, abstention-based candidate, not a general BTC trading strategy
