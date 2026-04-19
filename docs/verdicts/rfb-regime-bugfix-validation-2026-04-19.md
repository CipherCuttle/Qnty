# RFB Regime-State Bug Fix — Validation Sprint Results

**Date:** 2026-04-19  
**Branch:** `qnty/rfb-regime-bugfix`  
**Fix:** Cap `_rfb_bars` to `trend_window + 1` bars (was unbounded)

---

## 1. FACTS

### Bug Identified
- **Location:** [`quantbot/strategy/regime_filtered_breakout.py:49-52`](quantbot/strategy/regime_filtered_breakout.py:49)
- **Bug:** `_rfb_bars.append(bar)` grew unbounded — no truncation
- **Effect:** `compute_log_returns(self._rfb_bars)` used ALL accumulated bars instead of only the recent window
- **Contamination:** After 300-bar warmup, regime was computed over 300 bars instead of 20, mixing training-period gains with holdout-period data

### Fix Applied
```python
# Store bar for regime computation
self._rfb_bars.append(bar)
# Keep trend_window+1 bars so we get trend_window log returns
# (log returns count = bars - 1, and regime needs len(log_rets) >= window)
if len(self._rfb_bars) > self.trend_window + 1:
    self._rfb_bars = self._rfb_bars[-(self.trend_window + 1) :]
```

**Note:** The truncation target is `trend_window + 1` (not `trend_window`) because `compute_trend_regime` requires `len(log_returns) >= window`. With `trend_window` bars → `trend_window - 1` log returns (insufficient). Need `trend_window + 1` bars → `trend_window` log returns (sufficient).

### Regression Tests Added
Added `TestRFBRegimeBoundedness` class with 3 tests proving:
1. `_rfb_bars` never exceeds `trend_window + 1`
2. Regime uses only recent window (stale bars don't contaminate)
3. Sideways holdout after uptrend warmup produces zero signals

**All 11 tests pass** (8 original + 3 regression).

### Fresh BTC Holdout (bars [2100, 2190))
| Metric | Buggy (original) | Fixed (corrected) |
|--------|-----------------|-------------------|
| _rfb_bars bounded | NO (grew to 300) | YES (capped at 21) |
| Signals | 3 | 3 |
| Regime@bar[2138] | sideways (BUG) | uptrend (valid) |
| Gross return | TBR | -4.51% |
| Net return | +9.18% | **-5.41%** |

**Key finding:** Original verdict predicted 0 signals with fix — this was INCORRECT. The sideways signal in buggy run was caused by a DIFFERENT mechanism (mixed training/holdout regime contamination), not because bounded bars would suppress it. With bounded `_rfb_bars`, all 3 signals remain and are regime-valid (uptrend).

### BTC Walkforward (step=100, 18 splits)
| Metric | Buggy | Fixed |
|--------|-------|-------|
| Gate | PASS | PASS |
| Signals | 31 | 31 |
| Signals per split | [1,0,1,0,1,4,3,2,2,2,0,1,2,2,1,4,1,4] | **IDENTICAL** |
| Net return | +24.96% | **IDENTICAL** |

**Walkforward results are UNCHANGED** because each walkforward split fresh-warms independently. The `_rfb_bars` contamination bug only affects continuous runs (warmup → holdout), not independent split evaluation.

---

## 2. ASSUMPTIONS

- The fix correctly implements the intended rolling-window behavior for regime computation
- Walkforward fresh-warm per split is the intended design (not a bug workaround)
- The holdout's -5.41% net return reflects the strategy's genuine performance on that data

---

## 3. SPECULATION

- The +9.18% buggy holdout return was partially earned from regime-contaminated signals
- The -5.41% corrected holdout return is the honest figure
- The strategy's holdout performance is genuinely poor, but this is one window only

---

## 4. PLAN

1. ✅ Bug identified and confirmed
2. ✅ Minimal fix applied (2 lines + comment)
3. ✅ 3 regression tests added proving boundedness and non-contamination
4. ✅ Fresh BTC holdout re-run with corrected code
5. ✅ BTC walkforward re-run with corrected code (identical results)
6. ⬜ Update verdict chain
7. ⬜ Final judgment

---

## 5. CHANGESET

### `quantbot/strategy/regime_filtered_breakout.py`
- Lines 49-52: Added truncation to `trend_window + 1`

### `tests/test_regime_filtered_breakout.py`
- Fixed off-by-one test data (30→50 bars, 25→50 bars to ensure `len(log_rets) >= window`)
- Added `TestRFBRegimeBoundedness` class with 3 regression tests

---

## 6. VERIFY

### Unit Tests
```
11 passed in 0.03s
```

### BTC Walkforward (corrected)
```
gate: PASS, signals: 31
signals per split: [1,0,1,0,1,4,3,2,2,2,0,1,2,2,1,4,1,4]
```

### Fresh BTC Holdout (corrected)
```
3 signals, all regime=uptrend (valid)
Net return: -5.41%
_rfb_bars bounded throughout: OK
```

---

## 7. VERDICT

### Was the bug real?
**YES.** `_rfb_bars` grew unbounded, contaminating regime computation with stale historical bars.

### Does corrected RFB survive fresh BTC holdout?
**NO.** -5.41% net return. The holdout fails regardless of the bug — the strategy's BTC performance on that window is genuinely poor.

### Does corrected RFB survive BTC walkforward?
**YES.** +24.96% net return, gate PASS, identical to buggy run.

### Does it remain BTC-only?
**UNCHANGED.** No cross-symbol claims warranted.

### Should RFB be archived?
**NO — but the holdout verdict must be corrected.**

The walkforward PASS (+24.96%) is the stronger evidence because:
- 18 independent splits vs 1 contiguous holdout window
- Each split fresh-warms (bug has no effect on walkforward)
- Results are reproducible and stable

**However:** The holdout FAIL (-5.41%) replaces the buggy +9.18% figure. Prior holdout validation documents INCORRECT behavior. The corrected holdout verdict is: **FAIL — strategy does not survive that particular holdout window**.

### Prior Verdicts — Status
| Document | Status | Notes |
|----------|--------|-------|
| `rfb-btc-holdout-validation-2026-04-19.md` | **SUPERSEDED** | Buggy behavior documented; corrected results differ |
| `rfb-btc-harsher-validation-2026-04-19.md` | **VALID** | Walkforward unaffected by fix; results unchanged |
| `rfb-refinement-verdict.md` | **VALID** | Walkforward results unchanged |

### Bottom Line
RFB survives walkforward validation. The regime-state bug is fixed. The fresh holdout failure (-5.41%) is genuine poor performance, not a bug artifact. RFB remains a BTC-only research candidate with the corrected understanding that its holdout performance is mixed.
