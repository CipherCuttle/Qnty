# Verdict: BASE vs RFB Walkforward Comparison

**Date:** 2026-04-19
**Fixture:** BTCUSDT_8h.csv (2190 bars, 12 walkforward windows)
**Windows:** train=720, test=120, step=120, interval=8h

---

## FACTS

| Metric | BASE (fee=10/slip=5) | RFB (fee=10/slip=5) | BASE (fee=20/slip=10) | RFB (fee=20/slip=10) |
|--------|---------------------|---------------------|----------------------|----------------------|
| signal_count | 61 | 37 | 61 | 37 |
| entry_count | 61 | 37 | 61 | 37 |
| exit_count | 60 | 37 | 60 | 37 |
| flip_count | 0 | 0 | 0 | 0 |
| cost_side_count | 121 | 74 | 121 | 74 |
| gross_return_total | 0.4895 | 0.4271 | 0.4895 | 0.4271 |
| net_return_total | 0.3080 | 0.3161 | 0.1265 | 0.2051 |
| positive_windows | 9 | 10 | 6 | 9 |
| negative_windows | 3 | 2 | 6 | 3 |
| window_count | 12 | 12 | 12 | 12 |

### Signal Reduction Ratios
- RFB/BASE signal ratio: **0.607** (37/61) — RFB emits 60.7% of BASE signals
- RFB/BASE cost_side ratio: **0.612** (74/121) — consistent with signal reduction

### Net Return Ratios
- fee=10/slip=5: RFB net / BASE net = **1.026** (0.3161 / 0.3080)
- fee=20/slip=10: RFB net / BASE net = **1.621** (0.2051 / 0.1265)

### Cost Sensitivity
- BASE net @ 10/5 → 20/10: drops **58.9%** (0.3080 → 0.1265)
- RFB net @ 10/5 → 20/10: drops **35.1%** (0.3161 → 0.2051)
- RFB is more cost-robust: loses less net return when costs double

---

## ASSUMPTIONS

1. The regime filter (uptrend-only gate) genuinely suppresses signals in non-uptrend windows, rather than suppressing signals randomly.
2. Both strategies share identical gross return per signal (same underlying return capture), differing only in signal count and cost burden.
3. The 12-window walkforward structure provides sufficient statistical weight for the comparison.

---

## SPECULATION

The gross return ratio (0.872) being lower than the signal ratio (0.607) suggests RFB's retained signals capture somewhat less gross return per signal than BASE's. This could indicate the regime filter suppresses some high-quality signals while removing low-quality ones. However, the net ratio exceeding the signal ratio at both cost settings confirms the filter's cost-reduction benefit outweighs any gross-return capture loss.

---

## VERDICT

**RFB filter PASSES — it works.**

### Evidence

1. **Net return exceeds BASE at both cost settings** — RFB nets 2.6% MORE than BASE at fee=10/slip=5 and 62.1% MORE at fee=20/slip=10.
2. **Signal reduction (0.607) < net return decline (0.872 < 1.0 for gross, and >1.0 for net)** — the filter's cost savings exceed the opportunity cost of fewer signals.
3. **More positive windows under RFB** — 10/12 vs 9/12 at low costs; 9/12 vs 6/12 at high costs.
4. **Better cost robustness** — RFB degrades 35.1% when costs double, vs 58.9% for BASE.

### Recommendation

**Retain RFB over BASE.** The regime filter is not just reducing returns proportionally — it is producing superior net returns, especially under realistic cost assumptions (20/10). BASE's higher gross return doesn't compensate for its higher cost burden.

---

## CAVEATS

- This is BTCUSDT_8h only — results may not replicate across assets or intervals.
- The "uptrend" regime label is narrow; downtrend signals are entirely suppressed, which may miss profitable shorts in bear markets.
- Gross return per signal is slightly lower for RFB, suggesting some quality signals may be filtered.
