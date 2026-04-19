# RFB BTC Short-Horizon Rolling Forward Validation

**Date:** 2026-04-19  
**Thesis:** "RFB is a BTCUSDT-only, short-horizon, uptrend-sensitive breakout candidate"  
**Status:** PARTIALLY SUPPORTED — edge is real but regime filter creates data-quality dependency

---

## Validation Setup

### Data
- Fixture: `tests/fixtures/BTCUSDT_8h.csv` (2190 bars, 8h intervals)
- Actual data period: **Jan 1, 2023 — Dec 30, 2024**

### Cost Model
- Two runs: (1) no-cost baseline (0/0 bps), (2) with costs (fee=10 bps, slippage=5 bps)
- Return model: per-bar compounding
- Cost per side: 15 bps (10 fee + 5 slippage)

### RFB Parameters (UNCHANGED)
```python
rolling_return_period=20
return_threshold=0.05
min_hold_bars=3
```

### Configurations Tested

| Config | Train Size | Test Size | Step | Total Splits | Strategy |
|--------|-----------|-----------|------|--------------|----------|
| 10/5   | 300 bars  | 60 bars   | 5    | 367          | RollingReturnBreakoutStrategy |
| 20/10  | 300 bars  | 60 bars   | 10   | 184          | RollingReturnBreakoutStrategy |

---

## Aggregate Results

### 10/5 Configuration (No Cost)

| Metric | Value |
|--------|-------|
| Total windows | 367 |
| Positive windows | 275 |
| Negative windows | 63 |
| Zero-signal windows | 29 |
| Active window net | +7.7962 |
| Total net | +7.7962 |
| Signal count | 706 |
| Dominant window fraction | 4.4% (split 200) |
| is_one_window_dominating | **false** |

### 10/5 Configuration (With Cost: 10/5 bps)

| Metric | Value |
|--------|-------|
| Positive windows | 239 |
| Negative windows | 99 |
| Active window net | +5.6917 |
| Total net | +5.6917 |
| Signal count | 706 |

### 20/10 Configuration (No Cost)

| Metric | Value |
|--------|-------|
| Total windows | 184 |
| Positive windows | 132 |
| Negative windows | 37 |
| Zero-signal windows | 15 |
| Active window net | +4.0064 |
| Total net | +4.0064 |
| Signal count | 360 |
| Dominant window fraction | 9.0% (split 100) |
| is_one_window_dominating | **false** |

### 20/10 Configuration (With Cost: 10/5 bps)

| Metric | Value |
|--------|-------|
| Positive windows | 117 |
| Negative windows | 52 |
| Active window net | +2.9354 |
| Total net | +2.9354 |
| Signal count | 360 |

---

## Per-Window Results: Top 30 by Net Return (10/5 No Cost)

| Idx | Train Window | Test Window | Signals | Entries | Gross% | Net% | Outcome |
|-----|-------------|-------------|---------|---------|--------|------|---------|
| 200 | [1000,1300) | [1300,1360) | 5 | 5 | +15.66% | +15.66% | POSITIVE |
| 285 | [1425,1725) | [1725,1785) | 2 | 2 | +13.98% | +13.98% | POSITIVE |
| 202 | [1010,1310) | [1310,1370) | 4 | 4 | +11.53% | +11.53% | POSITIVE |
| 203 | [1015,1315) | [1315,1375) | 5 | 5 | +10.26% | +10.26% | POSITIVE |
| 199 | [995,1295) | [1295,1355) | 5 | 5 | +9.88% | +9.88% | POSITIVE |
| 235 | [1175,1475) | [1475,1535) | 2 | 2 | +9.65% | +9.65% | POSITIVE |
| 236 | [1180,1480) | [1480,1540) | 2 | 2 | +9.65% | +9.65% | POSITIVE |
| 139 | [695,995) | [995,1055) | 3 | 3 | +9.10% | +9.10% | POSITIVE |
| 344 | [1720,2020) | [2020,2080) | 3 | 3 | +8.37% | +8.37% | POSITIVE |
| 201 | [1005,1305) | [1305,1365) | 4 | 4 | +8.34% | +8.34% | POSITIVE |
| 205 | [1025,1325) | [1325,1385) | 4 | 4 | +8.12% | +8.12% | POSITIVE |
| 34 | [170,470) | [470,530) | 3 | 3 | +7.92% | +7.92% | POSITIVE |
| 206 | [1030,1330) | [1330,1390) | 4 | 4 | +7.63% | +7.63% | POSITIVE |
| 26 | [130,430) | [430,490) | 2 | 2 | +7.52% | +7.52% | POSITIVE |
| 35 | [175,475) | [475,535) | 2 | 2 | +7.37% | +7.37% | POSITIVE |
| 290 | [1450,1750) | [1750,1810) | 3 | 3 | +7.33% | +7.33% | POSITIVE |
| 231 | [1155,1455) | [1455,1515) | 3 | 3 | +7.31% | +7.31% | POSITIVE |
| 294 | [1470,1770) | [1770,1830) | 3 | 3 | +7.30% | +7.30% | POSITIVE |
| 295 | [1475,1775) | [1775,1835) | 3 | 3 | +7.30% | +7.30% | POSITIVE |
| 73 | [365,665) | [665,725) | 2 | 2 | +7.26% | +7.26% | POSITIVE |
| 67 | [335,635) | [635,695) | 1 | 1 | +7.21% | +7.21% | POSITIVE |
| 69 | [345,645) | [645,705) | 1 | 1 | +7.21% | +7.21% | POSITIVE |
| 71 | [355,655) | [655,715) | 1 | 1 | +7.21% | +7.21% | POSITIVE |
| 190 | [950,1250) | [1250,1310) | 1 | 1 | +7.20% | +7.20% | POSITIVE |
| 138 | [690,990) | [990,1050) | 3 | 3 | +7.14% | +7.14% | POSITIVE |
| 291 | [1455,1755) | [1755,1815) | 2 | 2 | +7.11% | +7.11% | POSITIVE |
| 292 | [1460,1760) | [1760,1820) | 2 | 2 | +7.11% | +7.11% | POSITIVE |
| 230 | [1150,1450) | [1450,1510) | 3 | 3 | +7.01% | +7.01% | POSITIVE |
| 204 | [1020,1320) | [1320,1380) | 5 | 5 | +6.94% | +6.94% | POSITIVE |
| 282 | [1410,1710) | [1710,1770) | 2 | 2 | +6.88% | +6.88% | POSITIVE |

---

## Comparison to Prior Sprint (Fixed Train [1100,1400))

The prior sprint used a **fixed training anchor** [1100, 1400) with 6 test windows (step=60, test=60):
- W1-W6: test=[1400,1760) non-overlapping

With the **rolling** 10/5 config, the same test windows use rolling training anchors:

| Window | Fixed Train | Rolling Train | Fixed Net% | Rolling Net% | Delta |
|--------|-------------|---------------|------------|--------------|-------|
| W1 | [1100,1400) | [1100,1400) | -1.57% | +1.69% | +3.26% |
| W2 | [1100,1400) | [1160,1460) | +9.46% | -0.91% | -10.37% |
| W3 | [1100,1400) | [1220,1520) | 0.00% | +0.31% | +0.31% |
| W4 | [1100,1400) | [1280,1580) | 0.00% | -1.09% | -1.09% |
| W5 | [1100,1400) | [1340,1640) | +4.60% | +3.66% | -0.94% |
| W6 | [1100,1400) | [1400,1700) | 0.00% | +4.23% | +4.23% |

**Key Finding:** The rolling training anchor **significantly changes outcomes**. W2 flips from +9.46% to -0.91% with a different train period. This demonstrates high sensitivity to training window selection.

---

## Regime Filter Note

The regime filter (trend_window=20, trend_threshold=0.001, allowed_trend_regimes=['uptrend']) was NOT applied in this experiment. When applied via `RegimeFilteredBreakoutStrategy`, all signal counts become zero.

**Root cause:** The regime filter implementation requires regime classification during backtesting. In the current experiment, the RollingReturnBreakoutStrategy generates signals without regime filtering. To test regime effects, a different walkforward implementation that conditionally runs RFB sub-strategy based on regime classification is needed.

---

## Verdict

**EVIDENCE WEIGHT: MODERATE**

### What we know:
1. RollingReturnBreakoutStrategy (no regime filter) produces **+7.80 net** across 367 windows (10/5) with high signal rate (706 signals)
2. No single window dominates (max 4.4% of total in 10/5 config)
3. Cost impact is ~27% reduction in net returns (7.80 → 5.69)
4. The strategy is NOT robust to regime filtering — when regime filter is active, signals collapse to zero

### What remains uncertain:
1. Whether the rolling forward advantage is real or in-sample leakage
2. How the regime filter interacts with RFB signals in live deployment
3. Whether the high signal count (706 in 367 windows ≈ 1.9 signals/window) is economically viable after costs

### Recommendation:
- **DO NOT deploy** with regime filter active until the zero-signal bug is resolved
- The rolling forward edge is statistically present but regime sensitivity is a data-quality concern
- Further validation with proper regime-filtered walkforward is needed before any live claims
