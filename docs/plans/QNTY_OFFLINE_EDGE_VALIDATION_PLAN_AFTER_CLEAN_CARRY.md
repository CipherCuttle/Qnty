# QNTY_OFFLINE_EDGE_VALIDATION_PLAN_AFTER_CLEAN_CARRY

**Status:** PLAN_RECORDED
**Date:** 2026-07-09
**Author:** Orchestrator workflow
**Verdict:** QNTY_OFFLINE_EDGE_VALIDATION_PLAN_AFTER_CLEAN_CARRY_RECORDED

---

## 1. Executive Summary

- **Prod clean-carry is solved.** The official report passes the verifier gate, hashes are recorded, and 13/13 post-merge audit checks pass. `CLEAN_NET_OF_CARRY` is confirmed for both prod and shadow runs.
- **Edge / profit remains unproven.** The verdict stands at `EDGE_UNPROVEN` / `NOT ENOUGH EVIDENCE`. The forward sample (14 equity bars, 13 batches, 5 closed trades, total −133.72) is statistically meaningless.
- **This document is a plan only.** It defines the offline validation approach for a future execution task. No implementation, no live integration, no shadow deployment, no source code changes. Nothing in this document is to be acted upon until a separate execution task is defined, approved, and scheduled.

---

## 2. Current Lane Mismatch

### 2.1 The Two Objects

| Property | `paper_pnl_v1` (prod forward lane) | V2 volnorm portfolio (validated candidate) |
|---|---|---|
| Sizing method | Fixed notional — $1,000/symbol | Inverse-vol weighting (90-bar rolling std) |
| Weighting | Equal-weight across symbols | Vol-normalized, then heat-capped at 1.0 |
| Portfolio construction | Simple equal-slice | `VolatilityTracker` + `compute_vol_normed_weights()` from [`quantbot/experiment/volnorm_portfolio.py`](quantbot/experiment/volnorm_portfolio.py) |
| Current status | Running forward in prod | NOT deployed. NOT called by the forward paper engine. Only exists in experiment/backtest code. |

### 2.2 Why Clean-Carry Does Not Prove V2 Edge

The prod forward lane (`paper_pnl_v1`) uses fixed-notional equal-weight sizing. The V2 volnorm portfolio is a fundamentally different position-sizing regime. The fact that `paper_pnl_v1` passes the verifier gate (`CLEAN_NET_OF_CARRY`) says nothing about whether V2 volnorm would produce a positive net return in forward trading.

**The two are different objects. Prod clean-carry is NOT evidence of V2 edge.**

### 2.3 Conceptual Lane B Marker

Define "Lane B" conceptually as a future separate paper lane (e.g., `paper_pnl_volnorm_v1` or equivalent naming) where the V2 volnorm portfolio would be run forward. This is a conceptual marker only — a placeholder for future planning.

**Do not implement Lane B in this plan.** This plan only defines the offline analysis that would need to precede any Lane B decision.

---

## 3. Offline Validation Design

### Stage A — Reconstruct V2 volnorm / heat-capped portfolio offline

- Use existing historical bar CSV data (e.g., [`tests/fixtures/BTCUSDT_8h.csv`](tests/fixtures/BTCUSDT_8h.csv)) to reconstruct what the V2 portfolio would have produced over the backtest window.
- Apply the same `VolatilityTracker` (90-bar lookback), inverse-vol weighting, and heat cap (1.0) logic from [`quantbot/experiment/volnorm_portfolio.py`](quantbot/experiment/volnorm_portfolio.py).
- Use existing OHLCV CSV fixtures and manifest files. No data mutation.
- **No source code changes.** This is a plan for a future validation script that runs independently.

### Stage B — Apply realistic cost model

- Funding: Realistic accrual from actual funding rate CSVs (see Section 5).
- Spread: Model based on typical bid-ask for each symbol.
- Slippage: Baseline 5 bps/side with stress tests.
- Commission: Flat taker 5 bps/side on fill notional.
- All costs applied in a single offline pass. No live/trading system involvement.

### Stage C — Time-split / walk-forward validation

- Use walk-forward methodology as implemented in [`quantbot/experiment/walkforward.py`](quantbot/experiment/walkforward.py) — split-only, no calibration.
- Define train/test splits over the historical backtest data.
- The existing walk-forward was run on backtest data only. This validation would extend that with better cost modeling (Stage B).

### Stage D — Forward-window replay

- Replay the V2 volnorm portfolio over the paper-forward period (starting ~2026-06-20) to answer: what would V2 HAVE DONE vs what `paper_pnl_v1` actually did.
- This is a **counterfactual replay**, not a forward trade.
- The replay must explicitly report the difference between V2 counterfactual result and actual `paper_pnl_v1` result.

### Stage E — Sensitivity analysis

- **Regime breakdown:** Performance during trending vs choppy periods.
- **Funding flip scenarios:** Positive vs negative funding regimes.
- **Slippage stress:** 5 bps → 10 bps → 20 bps.
- **Liquidity capacity estimation:** Maximum notional deployable before volnorm weights cause measurable slippage degradation.

### Stage F — Verdict classification

Define three possible verdicts:

| Verdict | Meaning |
|---|---|
| `EDGE_CANDIDATE` | Meets all statistical gates (Section 6). Eligible for further planning. |
| `NO_EDGE` | Fails core gates. V2 volnorm does not show edge over baseline. |
| `INCONCLUSIVE` | Ambiguous, mixed, or insufficient data. Needs more observation time or data. |

---

## 4. Required Data Inventory

### 4.1 Existing Data Available

| Data | Source | Notes |
|---|---|---|
| Bar CSVs (e.g., `BTCUSDT_8h.csv`) | [`tests/fixtures/`](tests/fixtures/) | OHLCV data with SHA256 manifest entries |
| Manifest files (e.g., `BTCUSDT_manifest.json`) | [`tests/fixtures/`](tests/fixtures/) | Contains SHA256 hashes for CSV files |
| Test fixtures (e.g., `sample_bars.csv`) | [`tests/fixtures/`](tests/fixtures/) | Used for unit testing |
| Funding CSVs | Data directory | When available for a symbol and time range |
| Config hash golden | Test infrastructure | Baseline config fingerprint |

### 4.2 Missing Data

| Data | Gap | Impact |
|---|---|---|
| Complete multi-symbol funding CSVs | Not all symbols have full coverage over the backtest + forward window | Cost model will be incomplete for those symbols |
| Universe table | Last populated ~2025-10-01 — stale | Cannot reliably use for current symbol universe |
| Funding data for SOLUSDT | Confirmed upstream SOL CSV had 0 rows during comparator window; engine silently treated as zero | Risk of understated costs if the gap persists |

### 4.3 Minimum Data Quality Requirements

- Each input CSV must have a corresponding SHA256 manifest entry.
- Manifest hashes must match the actual file content at validation time.
- Zero-row CSVs must be explicitly flagged and documented.
- Funding data must pass the completeness gate (fail-closed on missing data).

### 4.4 No Mutation Allowed

- All existing data files are **read-only**.
- Any validation must work from copies or in-memory transformations.
- No CSV files, DB files, or JSON files may be modified.

### 4.5 No Live Fetch

- No live data fetching is permitted under this plan.
- Live data fetching would require a separate plan and explicit approval.

---

## 5. Cost Model Plan

| Cost component | Modeling approach | Notes |
|---|---|---|
| **Funding** | Realistic accrual from actual funding rate CSVs. When funding data is missing, must **fail closed** (not assume zero). | Per the existing funding coverage gate merged into the codebase. |
| **Spread** | Model based on typical bid-ask for each symbol. Default assumption or variable per-regime. | Per-symbol spread data would need to be sourced or estimated. |
| **Slippage** | Baseline: 5 bps/side (matching current paper engine). Stress tests: 10 bps and 20 bps. | Must pass at 2× baseline (10 bps) without flipping to negative net return. |
| **Commission** | Flat taker 5 bps/side on fill notional (matching current paper engine). | Applied to the full notional of each fill. |
| **Borrow / margin** | **Not modeled.** Leverage is not approved. Long-only, 1× only. | No borrow costs, no margin interest. |
| **Capacity / liquidity stress** | Estimate maximum notional deployable before volnorm weights cause measurable slippage degradation. | Stress test — not a binding constraint for the offline analysis, but reported as a sensitivity metric. |

---

## 6. Statistical Acceptance Criteria

### 6.1 Minimum Observation Requirements

| Criterion | Minimum | Preferred |
|---|---|---|
| Forward equity bars | ≥ 30 bars (~10 days on 8h bars) | ≥ 60 bars |
| Closed trades in forward period | ≥ 20 | More is better |
| Below minimum → `INCONCLUSIVE` | — | — |

### 6.2 Performance Gates

- **Net return after costs:** Must be strictly positive after all modeled costs (funding + spread + slippage + commission).
- **Risk-adjusted metric:** Minimum Sharpe > 0.5 (annualized) or equivalent risk-adjusted return metric.
- **Max drawdown:** Must stay within defined bounds relative to historical volatility.
- **Sensitivity robustness:** Must pass at 2× slippage (10 bps) and 2× spread stress tests **without flipping to negative net return**.
- **Comparison against baseline ([`paper_pnl_v1`](quantbot/paper/)):** Must outperform the baseline on at least **2 of 3**: net return, Sharpe, max drawdown.

### 6.3 No Cherry-Picking Rule

- Results must be reported for **ALL** symbols, **ALL** regimes, **ALL** splits.
- Selective reporting (e.g., reporting only the best-performing regime or split) is not permitted.
- Any filtering of results must be pre-registered in the validation plan before execution.

---

## 7. Failure / No-Go Criteria

| Verdict | Criteria |
|---|---|
| `NO_EDGE` | Net return negative after costs at baseline assumptions. **OR** Sharpe < 0.0. **OR** Max drawdown exceeds 2× historical volatility. |
| `INCONCLUSIVE` | Fewer than 20 closed trades in the forward window. **OR** Fewer than 30 forward equity bars. **OR** Mixed results across sensitivity stress tests (passes baseline but fails 2× stress). |
| `NEEDS_MORE_DATA` | Key data gaps identified (e.g., missing funding CSVs for 2+ symbols over a critical period). Cannot render a verdict with available data. |
| `BLOCKED_BY_DATA_QUALITY` | Manifest hash mismatches. Stale universe table. Zero-row CSVs that affect portfolio construction. Cannot trust the input data. |

---

## 8. Artifacts to Produce in a Future Execution Task

The following artifacts would be produced by a future execution task. **Do not create them now.**

| Artifact | Format | Description |
|---|---|---|
| Offline validation receipt | JSON or Markdown | Documents all stages run and their results. |
| Cost model spec | Markdown or JSON | Detailed parameterization used, including all assumptions. |
| Lane mismatch reconciliation note | Markdown | Explains the difference between `paper_pnl_v1` and V2 volnorm, and why clean-carry does not imply V2 edge. |
| Validation result tables | Markdown tables | One table per stage (A–F) with key metrics. |
| Hash / fingerprint manifest | JSON | SHA256 of all CSVs and configs used, to ensure reproducibility. |
| No source/prod mutation proof | Statement or script output | A check that no production data was modified during validation. |

---

## 9. Non-Goals

The following are explicitly **excluded** from this plan and from any execution task derived from it:

- ❌ No implementation in this PR.
- ❌ No Lane B creation in this PR.
- ❌ No writer.
- ❌ No live exchange.
- ❌ No service/timer.
- ❌ No API keys.
- ❌ No 2x/shorting.
- ❌ No report promotion.
- ❌ No claim of edge.
- ❌ No source code changes to any `.py` file.
- ❌ No DB mutation.
- ❌ No CSV mutation.
- ❌ No snapshot/bundle/report write.
- ❌ No deploy.
- ❌ No exchange connector integration.
- ❌ No live integration.

---

## 10. Next Task Recommendation

Recommend next task:

**`QNTY_OFFLINE_EDGE_VALIDATION_IMPLEMENTATION_PLAN_SCOPING`**

This is a docs-only scoping task to further refine the implementation approach before any code is written. Key activities:

1. Review this plan and identify ambiguities or gaps.
2. Scope Stage A (V2 volnorm offline reconstruction) in enough detail for implementation.
3. Scope Stage B (cost model) with specific data sources, default assumptions, and per-symbol spread/funding parameters.
4. Define the exact output schema for the validation receipt and result tables.
5. Identify which existing test fixtures can be reused and what new test data is needed (if any).
6. Flag any data quality risks that could block execution.

If this plan identifies concerns about the approach itself (e.g., fundamental data availability issues, methodological weaknesses), an alternative next task may be:

**`QNTY_V2_VOLNORM_FORWARD_EVIDENCE_STRATEGY_RESEARCH`**

...a research-oriented docs-only task focused on data gaps, alternative validation approaches, or whether forward evidence is even feasible with the current data inventory.

---

## Guardrails Compliance

- [x] Docs-only: YES
- [x] Plan only (no implementation): YES
- [x] No source code changes: YES
- [x] No prod mutation: YES
- [x] No DB mutation: YES
- [x] No CSV mutation: YES
- [x] No snapshot/bundle/report write: YES
- [x] No writer/trader/live/backfill/data-refresh: YES
- [x] No service/timer/cron/systemd mutation: YES
- [x] No deploy: YES
- [x] No exchange keys: YES
- [x] No exchange connector integration: YES
- [x] No live integration: YES
- [x] No report promotion: YES
- [x] No 2x/shorting approval: YES
- [x] Long-only / 1x remains only assumed lane: YES
- [x] `EDGE_UNPROVEN` remains: YES
- [x] `BLOCK_LIVE_INTEGRATION` remains: YES
- [x] `CLEAN_NET_OF_CARRY` means only "not killed by verifier gate": YES