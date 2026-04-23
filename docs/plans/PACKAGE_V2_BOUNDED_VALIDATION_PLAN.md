# Package V2 — Bounded Validation Plan

**Branch:** `qnty/tsmom-package-v2-volnorm`
**Created:** 2026-04-22
**Status:** VALIDATION PROTOCOL — NOT YET STARTED

---

## 1. Purpose

Package V2 entered this validation window because:

- The prior equal-weight package (Trial 1, `qnty/multi-asset-tsmom-forensic-repair`) **failed** K2 with max drawdown 0.4636 > 0.35 threshold
- Package V2 (Trial 2) was independently registered, pre-specified, and executed on the same signal family
- Package V2 **passed** Stage 4 qualification on `qnty/tsmom-package-v2-volnorm` with K2 drawdown 0.2258 ≤ 0.35
- Package V2 is **not merged to `main`** — it lives on its own branch with 2 commits ahead of the merge base
- **Redesign is not authorized.** The next honest step is bounded validation, not mutation.

Validation is the correct next phase because the package survived its gate honestly. It is not a blank check, and it is not a live deployment.

---

## 2. Current Package V2 Truth

The following facts are frozen and represent the current Package V2 state as of commit `eb2d2ab` on `qnty/tsmom-package-v2-volnorm`:

| Component | Value |
|-----------|-------|
| **Package name** | `tsmom-package-v2-volnorm` |
| **Sizing method** | volatility-normalized (inverse-vol) |
| **Heat cap** | 1.0 (never triggered in Stage 4; avg heat 0.0614) |
| **Vol lookback** | 90 bars (~30 days at 8h) |
| **Benchmark mode** | gross (no funding adjustment) |
| **Carry mode** | net of realistic funding costs |
| **K1 excess return** | 0.703028 (PASS) |
| **K2 max drawdown** | 0.225758 (PASS) |
| **K3 funding drag** | 0.0 (N/A — K3 unavailable) |
| **K4 high-vol excess return** | 0.179012 (PASS) |
| **Stage 4 verdict** | CONDITIONAL CONTINUE |
| **K3 status** | explicitly unavailable; caveat noted |
| **Signal family** | TSMOM multi-asset crypto (10 symbols) |
| **Strategy posture** | net of realistic funding |
| **Deployment readiness** | NOT deployment-ready |

Package V2 is CONDITIONAL CONTINUE — not a promotion, not a failure.

---

## 3. What Remains Frozen During Validation

The following components **must not change** during the validation window:

- Signal family (TSMOM multi-asset breakout logic)
- Threshold grid (all thresholds identical to Package V2 Stage 4 run)
- Universe logic (10 crypto pairs, 8h bars)
- Vol-normalized sizing logic (inverse-vol weights, 90-bar lookback, vol floor 1e-6)
- Heat cap setting (1.0)
- Benchmark interpretation (gross, unchanged)
- Carry interpretation (net of realistic funding, unchanged)
- No new filters
- No overlays
- No Kelly / fractional Kelly
- No RAMOM
- No ML
- No package mutation of any kind

If any of the above appears to change during validation, it is a **scope violation** and must be flagged before proceeding.

---

## 4. Validation Mode: Bounded Paper Observation

**Mode chosen:** Bounded paper observation against a fresh holdout window.

**Justification:**

- Package V2 has been evaluated on the historical walkforward splits (14 splits, ~4,500 bars)
- A fresh holdout window that was **not part of the Stage 4 training/selection** process provides an honest out-of-sample test
- Shadow mode is not viable because there is no live trading infrastructure in this repo
- Replay against fresh holdout data is the smallest honest validation mechanism available
- This mode does not require live infrastructure, does not touch `main`, and does not mutate Package V2

**What this mode does NOT do:**
- It does not simulate live execution
- It does not account for slippage, latency, or fill assumptions beyond what the Stage 4 artifacts already encode
- It does not promote Package V2 to deployment-ready

The validation run must be registered and produces a bounded observation receipt.

---

## 5. Validation Window

**Window:** The most recent **~500 bars** (approximately 6–8 weeks at 8h resolution) of out-of-sample holdout data, held back from the Stage 4 walkforward.

**Why 500 bars:**
- Long enough to span a meaningful market regime (trending, ranging,/vol expansion)
- Short enough to be clearly distinct from the Stage 4 training window
- Not so long that it quietly becomes "observe forever"
- Provides at minimum 60–80 bars per split for observable behavior

**Why this window is bounded:**
- Exactly N bars defined before the run starts
- A hard stop at the window boundary — no automatic extension
- Post-window decision required before any further observation

**What happens at the boundary:**
- The window closes
- Metrics are summed and compared to stop/go criteria
- A verdict document is produced
- No further observation occurs without an explicit new decision

---

## 6. Metrics to Observe

All metrics are computed on the validation window only.

### Primary kill-criteria proxies (observed, not enforced)

| Metric | Observation |
|--------|-------------|
| Realized max drawdown | Must remain ≤ 0.35 to be consistent with CONDITIONAL CONTINUE posture |
| Realized excess return over benchmark | Must remain > 0.0 to be consistent with K1 pass |
| Realized Sharpe ratio | Not a kill criterion but observed for stability signal |

### Secondary behavioral metrics

| Metric | Observation |
|--------|-------------|
| Portfolio heat behavior | Did avg heat stay well below cap? Did cap trigger? |
| Concentration | Did inverse-vol sizing produce sensible weights across symbols? |
| Drawdown stability | Was drawdown smooth or did it cluster in specific splits? |
| Vol regime sensitivity | Did high-vol periods behave as expected under vol-norm sizing? |

### Caveat observation

| Item | Flag if observed |
|------|------------------|
| K3 funding drag becomes measurable | If K3 becomes measurable and > 0.40, flag as interpretation problem |
| Benchmark semantics interference | If gross benchmark causes apparent "excess return" that disappears under net benchmark, document explicitly |
| Heat cap binding events | If heat cap triggers in the validation window, log frequency and magnitude |

**No new dashboard.** Observation is logged in a single validation receipt file.

---

## 7. Stop / Go Rules

These are **unambiguous and crisp.**

### GO — continue Package V2 as current lead

All three of:
- Realized max drawdown ≤ 0.35 in the validation window
- Realized excess return > 0.0 in the validation window
- No heat cap cascade failures or anomalous concentration events

### FAIL — revert toward provisional no-go

Any one of:
- Realized max drawdown **>** 0.35 in the validation window
- Realized excess return **≤** 0.0 in the validation window
- Heat cap triggers in >5% of bars (signals the cap value is wrong for current regime)

### INCONCLUSIVE — pause and reassess

Any one of:
- Validation window contains fewer than 200 bars (insufficient data to teach anything)
- Market regime in validation window is so extreme it cannot be reasonably interpreted (e.g., exchange shutdown, extreme black swan)
- Benchmark/K3 semantics create documented ambiguity that makes excess return interpretation impossible without new assumptions

**There is no "monitor and adjust" or "evaluate holistically" escape hatch.** If evidence falls into INCONCLUSIVE, the only allowed moves are: (a) accept the ambiguity and close the window, or (b) open one narrowly justified follow-up issue.

---

## 8. Required Outputs

The validation run must produce:

### 8.1 Package identity snapshot
File: `output/validation_v2/package_identity.json`

Must contain the frozen Package V2 identity (same fields as `output/stage4_volnorm/package_identity.json`).

### 8.2 Bounded validation run receipt
File: `output/validation_v2/validation_receipt.md`

Must contain:
- Validation window definition (start bar index, end bar index, bar count)
- Date of run
- Branch/commit used
- Confirmation that no package components were mutated since the Stage 4 run

### 8.3 Observation log
File: `output/validation_v2/observation_log.json`

Must contain per-bar or per-split observations of:
- Realized equity curve (final value, max drawdown, Sharpe proxy)
- Heat cap trigger count
- Per-symbol realized returns
- Excess return over gross benchmark

### 8.4 Drawdown / equity summary
File: `output/validation_v2/drawdown_summary.json`

Must contain:
- Max drawdown (realized)
- Excess return (realized)
- Sharpe proxy
- Comparison to Stage 4 results

### 8.5 Caveat note
File: `output/validation_v2/caveat_note.md`

If benchmark/K3 semantics create interpretation problems, this file documents them explicitly. If no problems, file is a one-line confirmation: "No benchmark/K3 interpretation problems observed."

---

## 9. Forbidden Moves During Validation

The following are explicitly prohibited during the validation window:

- ❌ Changing any sizing, threshold, signal, or universe component
- ❌ Adjusting heat cap value mid-window
- ❌ Switching benchmark interpretation from gross to net (or vice versa)
- ❌ Stacking additional overlays or filters on top of Package V2
- ❌ Introducing Kelly, fractional Kelly, or RAMOM sizing
- ❌ Using the validation window as a tuning set for Package V2 parameters
- ❌ Extending the validation window without an explicit post-window decision
- ❌ Promoting Package V2 to deployment-ready based on partial window results
- ❌ Claiming the validation run as proof of live edge

Any observed violation must be flagged before proceeding.

---

## 10. End-of-Window Decisions

After the validation window closes, exactly one of the following decisions is allowed:

### Decision A: Continue Package V2 as current lead
**Trigger:** GO criteria met (all three conditions satisfied)
**Action:** Package V2 remains on `qnty/tsmom-package-v2-volnorm` as the current leading candidate. An explicit decision memo is published. No automatic merge to `main` occurs without a separate authorization.

### Decision B: Revert toward provisional no-go
**Trigger:** FAIL criteria met (any one condition)
**Action:** Package V2 is marked provisional no-go. A failure memo documents what failed and why. The signal family is not dead — only this packaging failed.

### Decision C: Pause
**Trigger:** INCONCLUSIVE criteria met
**Action:** Window is closed with an ambiguity memo. No further observation until an explicit follow-up issue is opened and approved.

### Decision D: Open one narrowly justified follow-up issue
**Trigger:** Any decision (A, B, or C) may generate one follow-up issue
**Action:** One GitHub issue is opened with:
- Exact question the follow-up would answer
- Why it cannot be answered within the current validation window
- Explicit scope of what is allowed in the follow-up

**No open-ended "iterate more" is permitted.** If the follow-up is not authorized, the window remains closed.

---

## GitHub-Issue-Ready Text Block

```markdown
## Package V2 — Bounded Validation Window

**Branch:** `qnty/tsmom-package-v2-volnorm`
**Current status:** CONDITIONAL CONTINUE (passed Stage 4 K2 with drawdown 0.2258 ≤ 0.35)
**Validation mode:** Bounded paper observation against fresh holdout window (~500 bars, 8h resolution)

### Background
- Package V2 (Trial 2) uses inverse-vol normalized sizing with heat cap
- Prior equal-weight package (Trial 1) failed K2 (drawdown 0.4636 > 0.35)
- Package V2 passed Stage 4 qualification honestly with pre-registered components
- Package V2 is NOT on `main` — it exists on `qnty/tsmom-package-v2-volnorm`
- Redesign is not authorized; validation is the smallest honest next step

### Validation window
- ~500 bars of holdout data not used in Stage 4 training/selection
- Window defined before run starts; hard stop at boundary
- No automatic extension

### Stop/go criteria
GO if all three: realized max drawdown ≤ 0.35 AND realized excess return > 0.0 AND no heat cap cascade failures
FAIL if any one: realized max drawdown > 0.35 OR realized excess return ≤ 0.0 OR heat cap triggers in >5% of bars
INCONCLUSIVE if: insufficient bars (<200) OR extreme black swan OR benchmark/K3 ambiguity

### Required outputs
- `output/validation_v2/package_identity.json`
- `output/validation_v2/validation_receipt.md`
- `output/validation_v2/observation_log.json`
- `output/validation_v2/drawdown_summary.json`
- `output/validation_v2/caveat_note.md`

### Decisions after window
- GO → Package V2 continues as current lead (no auto-merge)
- FAIL → Package V2 reverts to provisional no-go
- INCONCLUSIVE → Pause; one narrowly justified follow-up issue only

### Forbidden during window
Any package mutation: sizing, thresholds, signals, universe, heat cap changes, Kelly, RAMOM, overlays.

**This issue is for tracking only. Do not take any action on this issue until the validation window closes.**
```
