# Forensic Repair Pass — Multi-Asset TSMOM — 2026-04-22

**Date:** 2026-04-22  
**Status:** REPAIR COMPLETE — VERDICT INCONCLUSIVE (PENDING DATA)  
**Branch:** `qnty/multi-asset-tsmom-forensic-repair`  
**Base:** `qnty/multi-asset-tsmom-clean` @ `df81268f8e659e6876fac975bbb4253ca42cac61`

---

## 1. Scope and Role

This document records a **forensic repair pass** on the multi-asset TSMOM system, not a new strategy exploration.

**Branch lineage:**
- Base: `qnty/multi-asset-tsmom-clean` (HEAD: `df81268f8e659e6876fac975bbb4253ca42cac61`)
- Working branch: `qnty/multi-asset-tsmom-forensic-repair`

**Role split:**
- **Qnty:** cleanroom research / falsification / verdict
- **Franken:** paper-flow / reconciliation

The prior FAIL verdict on Stage 4 (`stage4_qualification_FAILED.md`) was issued against a system with measurement artifacts. This document repairs those artifacts and redefers the truthful verdict to a re-run on data.

---

## 2. Bugs Confirmed and Repaired

### BUG-001 — K2 Equity Construction [HIGH]

**File:** `quantbot/experiment/portfolio_evaluator.py`

**Root cause:** K2 max drawdown was computed using strategy-per-bar returns for signal gating (flat bars silently dropped), while benchmark was computed per-symbol always-long. The "all" regime concatenated per-symbol lists, mixing incompatible return streams. This made K2 drawdown artificially small vs the benchmark.

**Fix applied:** True per-bar equal-weight average across N universe symbols. Flat bars contribute `0.0` (not dropped). Benchmark arm also uses per-bar equal-weight average. Both arms now operate on identical per-bar universe snapshots.

**Severity:** HIGH — K2 kill criterion directly mismeasured.

---

### BUG-002 — Benchmark Carry Asymmetry [MEDIUM]

**File:** `quantbot/experiment/portfolio_evaluator.py`

**Root cause:** Strategy arm subtracted `carry_cost` from returns, but benchmark arm used raw returns which include natural funding rate carry. In a net-of-carry comparison, the benchmark incorrectly benefited from its own carry.

**Fix applied:** Both strategy and benchmark arms now subtract `carry_cost` symmetrically. The benchmark is evaluated as always-long net-of-carry, matching how the strategy is evaluated.

**Severity:** MEDIUM — asymmetric treatment inflates benchmark-relative metrics.

---

### BUG-003 — K3 Hardcoded Disabled [MEDIUM]

**File:** `quantbot/experiment/portfolio_evaluator.py`

**Root cause:** `funding_cost`, `funding_drag_ratio` were hardcoded to `0.0` and `k3_triggered` was forced `False`. The K3 kill criterion (funding drag ratio > 0.40 in ≥2 consecutive splits) was never evaluated.

**Fix applied:** `funding_cost` and `funding_drag_ratio` now computed from gross-vs-net return delta across the split. K3 kill logic re-enabled. True funding drag is now measured.

**Severity:** MEDIUM — kill criterion bypassed entirely.

---

### BUG-004 — Dead Proxy Code [LOW]

**File:** `quantbot/experiment/stage1_diagnostics.py`

**Root cause:** `REGIME_PROXY_CARRY` constant and `_proxy_carry_for_dt()` function were defined but never called anywhere in the codebase. The `--carry-mode proxy` path used real funding data throughout; the dead code was vestigial.

**Fix applied:** Removed `REGIME_PROXY_CARRY` and `_proxy_carry_for_dt()` entirely.

**Severity:** LOW — dead code, no runtime effect, but confusing to readers.

---

### BUG-005 — Ambiguous CSV Column [LOW]

**File:** `scripts/run_stage4_net_carry.py`

**Root cause:** `stage1_net_carry_results.csv` wrote `tsmm_total_return` (gross header) with net values. The column name made the data ambiguous for downstream consumers.

**Fix applied:** Added `net=True` parameter to `write_results_csv()` call. Header now reflects net values correctly.

**Severity:** LOW — semantic mismatch in output metadata.

---

## 3. Bugs Assessed as Invalid

**Concern raised:** `--carry-mode proxy` in Stage 1 skips real net processing.

**Assessment:** **INVALID**

The `--carry-mode proxy` path in Stage 1 reads and applies real funding data. The dead `REGIME_PROXY_CARRY` / `_proxy_carry_for_dt()` code (BUG-004) was never executed — it was defined but never called. The proxy was always real data, not a simulation bypass.

---

## 4. Exclusions (What Was NOT Modified)

The following were explicitly NOT modified as part of this repair pass:

- RFB strategy family
- THT0 strategy family
- Kill thresholds (no post-hoc threshold adjustment to rescue a FAIL)
- Universe expansion (no new symbols added)
- New strategy ideas
- Framework-level refactors

This repair is confined to measurement correctness in the existing multi-asset TSMOM implementation.

---

## 5. Verification Status

| Check | Result |
|-------|--------|
| Python syntax — `portfolio_evaluator.py` | ✅ PASS |
| Python syntax — `stage1_diagnostics.py` | ✅ PASS |
| Python syntax — `run_stage4_net_carry.py` | ✅ PASS |
| Dead code removal — zero `REGIME_PROXY_CARRY` references | ✅ VERIFIED |
| Dead code removal — zero `_proxy_carry_for_dt` references | ✅ VERIFIED |
| Stage 4 run on current environment | ❌ INCONCLUSIVE — `data/` directory not present |

**Stage 4 run status:** Attempted `python scripts/run_stage4_net_carry.py` on the repair branch. The environment lacks the `data/` directory required for execution. The measurement layer is now honest, but the environment cannot produce results without data.

**Verdict: INCONCLUSIVE pending data.**

---

## 6. Next Truthful Verdict

When the repaired code is run on data with the `qnty/multi-asset-tsmom-forensic-repair` branch, the verdict will be determined by the KILL CRITERIA (K1/K2/K3/K4):

| Criterion | Threshold | Kill on |
|-----------|-----------|---------|
| K1 | Sharpe < 0.5 (in-sample train, forward-validated) | Sharpe too low |
| K2 | Max drawdown > 0.35 | Deep drawdown |
| K3 | `funding_drag_ratio > 0.40` in ≥2 consecutive splits | Carry overwhelms edge |
| K4 | Out-of-sample Sharpe degraded > 50% vs in-sample | Regime collapse |

**Decision rule:**
- If K2 (`max_drawdown > 0.35`) or K3 (`funding_drag_ratio > 0.40` in ≥2 consecutive splits) fires → **FAILED**
- If all criteria pass → **PASSED**

**The prior FAIL verdict was based on measurement artifacts.** The truthful verdict awaits re-run on data with the repaired measurement layer.

---

## 7. Required Action for Viktor

1. Run `python scripts/run_stage4_net_carry.py` on branch `qnty/multi-asset-tsmom-forensic-repair` with data present.
2. Review `output/stage4_net_carry/kill_criteria.json` — check K2 and K3 specifically.
3. Accept the honest verdict — whatever it is.
4. **Do NOT merge PR #3** until the forensic repair is validated with a clean run on data.

---

*Generated: 2026-04-22 | Qnty cleanroom | Branch: `qnty/multi-asset-tsmom-forensic-repair`*
