# Package Hypothesis A: TSMOM Package V2 — Volatility-Normalized with Heat Cap

**Branch:** `qnty/tsmom-package-v2-volnorm`
**Created:** 2026-04-22
**Package Trial Count:** Incremented by 1 (this is the second package trial)

---

## 1. Hypothesis

Volatility-normalized sizing plus explicit portfolio heat cap will reduce package drawdown enough to keep K2 max drawdown ≤ 0.35 without destroying excess return over the benchmark.

---

## 2. What Stays Frozen

- **Signal family:** Current multi-asset crypto TSMOM line (same as forensic-repair branch)
- **Threshold grid / chosen package path:** Unchanged from prior package
- **Universe logic:** Same 8 crypto pairs (BTC, ETH, BNB, SOL, ADA, AVAX, DOT, LINK, MATIC, XRP) with 8h bars
- **No new signal transforms:** Signal entry/exit logic unchanged
- **No new overlays:** No regime filter additions
- **No threshold changes:** All thresholds identical to prior package

---

## 3. What Changes

### Only These Components May Change:

1. **Position sizing / weighting logic:**
   - Replace equal-notional sizing with volatility-normalized sizing
   - Each position sized by: `base_size = target_risk / symbol_volatility_estimate`
   - Use simplest defensible vol estimate: rolling standard deviation of returns

2. **Portfolio heat cap:**
   - Add explicit maximum aggregate exposure / risk budget
   - When total risk contribution exceeds cap, scale all positions proportionally
   - Cap value: to be determined empirically but documented explicitly

3. **Portfolio equity construction:**
   - Ensure true per-bar portfolio return engine
   - Returns computed as weighted sum of aligned per-symbol returns

4. **Benchmark/carry semantics:**
   - Keep explicit and honest
   - Benchmark mode: gross (no funding adjustment in benchmark)
   - Carry mode: net of realistic borrow/funding costs
   - Document whether carry is symmetric between long/short

---

## 4. Benchmark Semantics

| Component | Treatment |
|-----------|-----------|
| Benchmark | Gross return, no funding adjustment |
| Carry | Net of realistic funding costs |
| Carry symmetry | Long/short symmetric carry burden |
| Funding rate source | Realistic borrow rates from market data |

---

## 5. Kill Criteria

- **K2 max drawdown > 0.35 = FAIL** (unchanged)
- All other applicable criteria from prior Stage 4 remain
- No relaxed escape hatches
- No post-hoc threshold drift

---

## 6. Trial Accounting

- **Package trial count:** 2 (this branch = second trial)
- **Prior package:** `qnty/multi-asset-tsmom-forensic-repair` = trial 1 (PROVISIONAL NO-GO)
- This branch is an independent re-test of the same signal family with different packaging

---

## 7. Success Condition

Package survives Stage 4 qualification with:
- K2 max drawdown ≤ 0.35
- Excess return over benchmark preserved
- Carry semantics honest and documented
- Heat cap behavior measurable and logged

---

## 8. Failure Condition

- K2 max drawdown > 0.35 on honest rerun
- Package deemed PROVISIONAL NO-GO
- No automatic progression to Phase 3 or Phase 4 ideas
- Single-trial discipline maintained

---

## 9. Scope Violations (Do Not Add)

- ❌ risk-adjusted momentum score
- ❌ fractional Kelly or Kelly-derived sizing
- ❌ capital-protection overlay
- ❌ regime brake
- ❌ ML / nonlinear signal logic
- ❌ universe expansion
- ❌ threshold changes
- ❌ signal formula changes

If tempted to add one of these, stop and report scope violation.

---

## 10. Implementation Target

Eckhardt/Turtle-style transferable principles (narrow sense only):
- Volatility-normalized position sizing
- Portfolio heat cap
- Explicit risk budgeting

Do NOT import Turtle mythology beyond these three components.
