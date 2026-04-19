# RFB BTC Short-Horizon Forward Validation

**Date:** 2026-04-19  
**Thesis:** "RFB is a BTC-only, short-horizon, uptrend-sensitive breakout candidate"  
**Status:** PARTIALLY SUPPORTED — narrow edge, regime-dependent

---

## Validation Setup

### Data
- Fixture: `tests/fixtures/BTCUSDT_8h.csv` (2190 bars, 8h intervals)
- Actual test period: **Apr 11 — Aug 9, 2024** (not Jul-Sep 2023 as approximated)

### Cost Model
- fee_bps=10, slippage_bps=5 per side (15 bps/side total)
- Return model: per-bar compounding

### RFB BASELINE Parameters (UNCHANGED)
```python
rolling_return_period=20
return_threshold=0.05
trend_window=20
trend_threshold=0.001
allowed_trend_regimes=['uptrend']
min_hold_bars=3
```

### Windows (all use fixed train [1100, 1400))
| Window | Train | Test | Actual Period |
|--------|-------|------|--------------|
| W1 | [1100, 1400) | [1400, 1460) | Apr 11 - May 1, 2024 |
| W2 | [1100, 1400) | [1460, 1520) | May 1 - May 21, 2024 |
| W3 | [1100, 1400) | [1520, 1580) | May 21 - Jun 10, 2024 |
| W4 | [1100, 1400) | [1580, 1640) | Jun 10 - Jun 30, 2024 |
| W5 | [1100, 1400) | [1640, 1700) | Jun 30 - Jul 20, 2024 |
| W6 | [1100, 1400) | [1700, 1760) | Jul 20 - Aug 9, 2024 |

---

## Per-Window Results

| Window | Test Range | Period | BTC Δ% | Signals | Entries | Exits | Flips | Cost | Gross% | Net% | Result | Uptrend? |
|--------|------------|--------|--------|---------|---------|-------|-------|------|--------|------|--------|----------|
| W1 | [1400, 1460) | Apr 11 - May 1, 2024 | -18.74 | 1 | 1 | 1 | 0 | 2 | -1.27 | -1.57 | NEGATIVE | YES |
| W2 | [1460, 1520) | May 1 - May 21, 2024 | +19.64 | 2 | 2 | 2 | 0 | 4 | +2.34 | +1.74 | POSITIVE | YES |
| W3 | [1520, 1580) | May 21 - Jun 10, 2024 | -0.12 | 0 | 0 | 0 | 0 | 0 | 0.00 | 0.00 | ZERO_SIGNAL | N/A |
| W4 | [1580, 1640) | Jun 10 - Jun 30, 2024 | -11.25 | 0 | 0 | 0 | 0 | 0 | 0.00 | 0.00 | ZERO_SIGNAL | N/A |
| W5 | [1640, 1700) | Jun 30 - Jul 20, 2024 | +6.46 | 2 | 2 | 2 | 0 | 4 | +1.98 | +1.38 | POSITIVE | YES |
| W6 | [1700, 1760) | Jul 20 - Aug 9, 2024 | -10.92 | 0 | 0 | 0 | 0 | 0 | 0.00 | 0.00 | ZERO_SIGNAL | N/A |

---

## Aggregate Summary

| Metric | Value |
|--------|-------|
| Positive windows | 2 |
| Negative windows | 1 |
| Zero-signal windows | 3 |
| Aggregate gross return | +3.05% |
| Aggregate net return | +1.55% |
| BTC Δ over full period (Apr-Aug 2024) | **-14.56%** |

---

## Regime Validity

All 5 signals across all active windows occurred during valid uptrend regime:
- W1: 1 signal at uptrend → VALID
- W2: 2 signals at uptrend, uptrend → VALID
- W3: 0 signals (regime filter blocked all) → N/A
- W4: 0 signals (regime filter blocked all) → N/A
- W5: 2 signals at uptrend, uptrend → VALID
- W6: 0 signals (regime filter blocked all) → N/A

**Regime filter is functioning correctly** — signals are only emitted during uptrends.

---

## Key Findings

### Supports the Thesis
1. **Uptrend gate works**: All 5 signals occurred during confirmed uptrends
2. **Positive aggregate**: +1.55% net across 6 windows despite BTC being down 14.56%
3. **Positive per-window edge in active windows**: W1-W2-W5 average +0.52% per window (net)

### Falsifies / Weakens the Thesis
1. **50% zero-signal rate**: 3 of 6 windows produced no signals — regime filter too restrictive for most of the period
2. **Single losing window loses more than winners gain**: W1 net loss (-1.57%) exceeds W2+W5 net gains combined (+3.12%) on gross, but net is +0.17% for the 3 active windows
3. **BTC fell 14.56%** during the test period — strategy captured some upside but the edge is narrow
4. **Short-horizon claim unclear**: 60-bar (20-day) test windows are not truly "short" for an 8h dataset

---

## Conclusion

**VERDICT: THESIS NARROWLY SUPPORTED WITH CAVEATS**

RFB BASELINE demonstrates:
- ✓ Signals only in uptrends (regime gate functioning)
- ✓ Small but positive net return (+1.55% aggregate) in a BTC-down period (-14.56%)
- ✗ 50% of forward windows have zero signals
- ✗ Edge is narrow and may not be robust

The "short-horizon" aspect is not independently verified — all windows use the same 300-bar training set, so there's no true short-horizon adaptation test here.

**Evidence strength: MODERATE** — 6 windows is insufficient for statistical confidence. The positive aggregate is encouraging but driven by just 3 active windows.
