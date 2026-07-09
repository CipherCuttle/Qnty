# QNTY Risk and Readiness Gap Analysis — After CLEAN_NET_OF_CARRY

**Date:** 2026-07-09
**Receipt:** `docs/status/qnty_risk_readiness_gap_analysis_after_clean_carry_2026-07-09.md`
**Branch:** `docs/qnty-risk-readiness-gap-analysis-after-clean-carry`
**Status:** GAP_ANALYSIS_RECORDED — NOT a readiness approval

---

## 1. Executive Summary

**Current status:** The prod official report has reached [`CLEAN_NET_OF_CARRY`](docs/status/qnty_prod_clean_carry_status_summary_after_report_promotion_2026-07-09.md) under full-window source state. This means the publication-schema verifier gate — which checks that funding-source snapshots, bundle digests, and ledger rows are internally consistent and that the DB hash matches the report — has passed with zero failure codes. The infrastructure pipeline (snapshot → bundle → candidate → promotion → audit) is functional and auditable.

**Non-status:** Edge/profit/live readiness is **NOT** proven. [`CLEAN_NET_OF_CARRY`](https://github.com/CipherCuttle/Qnty/blob/main/docs/plans/QNTY_CLEAN_NET_OF_CARRY_REPAIR_PLAN.md) means only "not killed by verifier gate." It says nothing about:
- Whether the strategy generates excess returns after costs
- Whether forward performance replicates backtest expectations
- Whether the system is safe to attach to real exchange connectivity
- Whether operational procedures can survive production conditions

**Current hard blocks (unchanged from prior receipts):**
- [`EDGE_UNPROVEN`](docs/experiments/QNTY_STRATEGY_VALIDITY_EVIDENCE_PACK_2026-06-18.md) — No forward edge evidence for the validated V2 vol-normalized portfolio
- [`BLOCK_LIVE_INTEGRATION`](docs/status/qnty_clean_carry_known_limitations_2026-07-08.md) — Live exchange connectivity is explicitly blocked

**This document is a gap analysis, not a readiness approval.** It inventories what evidence exists, what is missing, and what would need to be true before any shadow/live/risk-review step could be considered.

---

## 2. Current Proven Baseline

The following has been verified and independently audited as of 2026-07-09:

| Artifact | Value | Source |
|---|---|---|
| Prod official report SHA256 | `3de74774f715b2b20948e303c1dfb179498ab573ed0b53269ea3b650f608bcc2` | [`docs/status/qnty_prod_clean_carry_status_summary_after_report_promotion_2026-07-09.md`](docs/status/qnty_prod_clean_carry_status_summary_after_report_promotion_2026-07-09.md) |
| Backup report SHA256 | `2c6af12ba74d92b52d827263225760145c5e7c2eef5b6053ff18779a8f9c10c3` | [`docs/status/qnty_prod_full_window_report_promotion_execution_v2_2026-07-09.md`](docs/status/qnty_prod_full_window_report_promotion_execution_v2_2026-07-09.md) |
| Prod DB SHA256 | `94874dab6d82701785fdf7379777b3e8a5850c3f869a42625edd90dcdc18bc11` | [`docs/status/qnty_prod_full_window_report_promotion_post_merge_audit_2026-07-09.md`](docs/status/qnty_prod_full_window_report_promotion_post_merge_audit_2026-07-09.md) |
| Full-window sidecar | `funding_source_full_window_snapshot_v1_batch57.json` | [`docs/status/qnty_prod_full_window_artifact_emission_execution_2026-07-09.md`](docs/status/qnty_prod_full_window_artifact_emission_execution_2026-07-09.md) |
| Bundle sha256 | `af27385a...` | Same as above |
| `source_path_resolution_mode` | `explicit_data_dir` | Verifier gate output |
| Verifier `status` | `OK` | Same |
| Verifier `failure_count` | `0` | Same |
| `funding_clean_carry_decision` | `CLEAN_NET_OF_CARRY` | Same |
| Verifier `funding_clean_carry_reason_codes` | `[]` (empty) | Same |
| 42-key publication schema | Confirmed | [`docs/status/qnty_prod_full_window_publication_candidate_vm_validation_2026-07-09.md`](docs/status/qnty_prod_full_window_publication_candidate_vm_validation_2026-07-09.md) |
| Pre/post promotion aggregate fingerprint | Identical (`88f371a1...`) | Same |
| Post-merge audit checks | 13/13 pass | [`docs/status/qnty_prod_full_window_report_promotion_post_merge_audit_2026-07-09.md`](docs/status/qnty_prod_full_window_report_promotion_post_merge_audit_2026-07-09.md) |
| No `.tmp_*` files | Confirmed | Same |
| No systemd disturbance | Confirmed | Same |
| Writer/trader/live/backfill processes | None spawned | [`docs/status/qnty_prod_full_window_report_promotion_execution_v2_2026-07-09.md`](docs/status/qnty_prod_full_window_report_promotion_execution_v2_2026-07-09.md) |

---

## 3. Gap Inventory

### Legend
- **HARD_BLOCK:** Cannot proceed to shadow/live without this artifact. Evidence gap is existential.
- **SOFT_BLOCK:** Should be addressed before next major milestone, but a path exists without it.
- **INFO:** Not blocking but useful context for downstream decisions.

| # | Category | Current Status | Evidence Available | Missing Evidence | Required Next Artifact | Blocker Level |
|---|---|---|---|---|---|---|
| 1 | **Strategy edge/profit evidence** | `EDGE_UNPROVEN`. Baseline control running on `paper_pnl_v1` (fixed-notional equal-weight, not the validated V2 volnorm portfolio). | [`QNTY_STRATEGY_VALIDITY_EVIDENCE_PACK`](docs/experiments/QNTY_STRATEGY_VALIDITY_EVIDENCE_PACK_2026-06-18.md) documents the lane mismatch. V2 volnorm passed in-sample/backtest validation. | Forward edge evidence for the actual V2 volnorm/heat-capped portfolio on paper. 14 forward equity bars and 5 closed trades (all losing) are statistically meaningless. | Offline edge-validation plan + Lane B paper execution for additive V2 volnorm forward evidence. | **HARD_BLOCK** |
| 2 | **Out-of-sample validation** | Done for V2 backtest (adversarial holdout, fresh holdout, harsher validation, short-horizon forward). Not done for paper-forward V2. | [`rfb-btc-adversarial-holdout-validation`](docs/verdicts/rfb-btc-adversarial-holdout-validation-2026-04-19.md), `rfb-btc-fresh-holdout-validation`, `rfb-btc-harsher-validation`, `rfb-btc-short-horizon-forward-validation`. | Out-of-sample evidence for the V2 portfolio that is running live-forward (even on paper). Current paper v1 is a different portfolio. | Lane B execution with V2 volnorm portfolio, then time-split validation of forward segment. | **HARD_BLOCK** |
| 3 | **Walk-forward / time-split validation** | V2 backtest walk-forward exists but does not cover paper-forward period. | [`quantbot/experiment/walkforward_runner.py`](quantbot/experiment/walkforward_runner.py), [`quantbot/experiment/walkforward.py`](quantbot/experiment/walkforward.py), stage4 results. | Walk-forward over the paper-forward window with the actual forward portfolio (V2 volnorm on Lane B). | Walk-forward plan for Lane B forward segment. | **SOFT_BLOCK** |
| 4 | **Regime sensitivity** | Baseline tested across limited regimes in backtest. Not tested in current forward regime (mid-2026). | Stage2 stress diagnostics, regime classification in backtest data. | Analysis of how the V2 portfolio behaves under current market regime (rate cycle, vol environment, correlation structure). | Regime sensitivity analysis for the forward period, including regime-change detection plan. | **SOFT_BLOCK** |
| 5 | **Slippage/spread/fee realism** | Not modeled in paper v1. Funding costs are captured but execution costs (spread, slippage, commission) are zero. | Paper engine captures funding payments via CSV snapshots. | Realistic execution cost model: spread (bid/ask), slippage (market impact), exchange commission, settlement costs. No evidence that zero-slippage assumption holds. | Slippage sensitivity analysis plan + execution cost model specification. | **HARD_BLOCK** |
| 6 | **Funding-rate persistence risk** | Funding coverage gap documented. SOLUSDT CSV had 0 rows in comparator window; engine silently treated as zero. | [`QNTY_FUNDING_COVERAGE_GAP_RECEIPT`](docs/experiments/QNTY_FUNDING_COVERAGE_GAP_RECEIPT_2026-06-18.md). [`funding_coverage.py`](quantbot/paper/funding_coverage.py) fail-closed gate merged. | Analysis of funding-rate persistence across regimes. What happens if funding flips negative for extended periods? How sensitive is the strategy to funding-rate assumptions? | Funding-rate persistence sensitivity analysis. | **SOFT_BLOCK** |
| 7 | **Liquidity/capacity limits** | Not analyzed. Strategy runs on perpetual futures with no position-size limits relative to market depth. | None. | Market-depth analysis by symbol. Maximum position size before slippage becomes material. Capacity ceiling for the strategy. | Liquidity/capacity analysis plan. | **INFO** |
| 8 | **Drawdown/risk-of-ruin analysis** | Drawdown observed in paper v1: 4.34% max drawdown, equity 9844.23 (−1.56%) from 10000 start. Not analyzed for V2. | Paper v1 equity curve (14 bars). V2 backtest drawdown statistics. | Forward-facing drawdown distribution, risk-of-ruin probability, expected max drawdown for V2 volnorm portfolio under realistic assumptions (with slippage/fees). | Drawdown and risk-of-ruin analysis plan. | **SOFT_BLOCK** |
| 9 | **Position sizing policy** | Not formalized. Current `paper_pnl_v1` uses fixed-notional equal-weight. V2 volnorm uses vol-normalized/heat-capped sizing. No written policy. | [`quantbot/paper/engine.py`](quantbot/paper/engine.py) implements current sizing. [`quantbot/experiment/volnorm_portfolio.py`](quantbot/experiment/volnorm_portfolio.py) implements volnorm. | Formal position sizing policy document specifying: sizing method, volatility targeting parameters, heat limits, rebalancing frequency, minimum position size, maximum concentration. | Position sizing policy specification. | **SOFT_BLOCK** |
| 10 | **Kill-switch policy** | Not documented. No automated kill-switch exists. | None. | Written kill-switch policy: conditions for manual/automated shutdown, who can trigger, what happens to open positions, recovery procedure. No kill-switch code exists. | Kill-switch policy specification + kill-switch implementation plan. | **HARD_BLOCK** |
| 11 | **Data freshness / data drift detection** | Not implemented. Paper engine uses CSV files refreshed by timer. No drift detection between data sources. | [`qnty-data-refresh.service`](ops/systemd/qnty-data-refresh.service) / `.timer` exists. [`watermark_watchdog.py`](scripts/watermark_watchdog.py) partially covers. | Written data freshness SLA. Automated data drift detection (comparing live-current vs snapshot digests). Alert on stale data. | Data freshness SLO specification + drift detection plan. | **SOFT_BLOCK** |
| 12 | **Exchange integration safety** | Not analyzed. `BLOCK_LIVE_INTEGRATION` prevents any exchange connectivity. | None. | Exchange integration specification: API key management, rate limiting, error handling, position reconciliation, fail-closed behavior, circuit breakers. | Exchange integration safety plan (to be written when BLOCK_LIVE_INTEGRATION is reconsidered). | **HARD_BLOCK** |
| 13 | **Order execution safety** | No order execution exists. Paper engine processes funding events only. | None. | Order execution specification: order types, timeout/retry policy, partial fill handling, error recovery, maximum order size, price validity checks. | Order execution safety plan. | **HARD_BLOCK** |
| 14 | **Reconciliation and ledger correctness** | Ledger reconciliation exists for paper v1. Internal discrepancies flagged (realized_gross vs equity_snapshots.realized_gross_pnl mismatch). | [`qnty_both_lanes_pnl_readonly_audit`](docs/status/qnty_both_lanes_pnl_readonly_audit_2026-07-08.md) documents: prod `ledger_state.realized_gross` (+0.5168) vs `equity_snapshots.realized_gross_pnl` (−36.6156) at same watermark; prod `num_open=5` vs `open_positions` rows=4. | Resolution of documented internal discrepancies. Reconciliation SOP for production (not just paper). | Reconciliation SOP + discrepancy resolution. | **SOFT_BLOCK** |
| 15 | **Alerting/observability** | Basic: health-receipt service, watermark-watchdog, healthcheck timer. No real-time alerting. | [`qnty-health-receipt.service`](ops/systemd/qnty-health-receipt.service), [`qnty-watermark-watchdog.service`](ops/systemd/qnty-watermark-watchdog.service), [`qnty-healthcheck.service`](ops/systemd/qnty-healthcheck.service). | Real-time alerting for: stale data, verifier failures, unexpected drawdown, exchange connectivity loss, position reconciliation failures. Incident response runbook. | Alerting/observability specification. | **SOFT_BLOCK** |
| 16 | **Operational rollback** | Report promotion has atomic rollback (backup report preserved). No operational rollback for paper engine state. | Backup report hash preserved. Promotion procedure includes pre/post fingerprints. | Paper engine rollback procedure: how to revert to a known-good state, what happens to intermediate batches, how to recover from corrupted DB or snapshot. | Operational rollback plan. | **INFO** |
| 17 | **Shadow deployment criteria** | Not defined. No written criteria for what would trigger or permit shadow deployment. | None. | Written shadow deployment criteria: what evidence artifacts must exist, what gates must pass, what monitoring must be in place, who authorizes. | Shadow deployment criteria specification. | **HARD_BLOCK** |
| 18 | **Live deployment criteria** | Not defined. `BLOCK_LIVE_INTEGRATION` explicitly prevents consideration. | None. | Written live deployment criteria: all shadow gates must pass, edge must be proven, kill-switch must exist, alerting must be in place, exchange integration must be reviewed. | Live deployment criteria specification (to be written when BLOCK_LIVE_INTEGRATION is reconsidered). | **HARD_BLOCK** |

---

## 4. Guardrail Lift Criteria

The following guardrails remain in effect. This section defines what evidence would need to exist **before** each guardrail could be reconsidered. It does **not** recommend lifting any guardrail — only documents the evidence gates.

### 4.1 `EDGE_UNPROVEN`

**Current state:** No forward edge evidence exists for the V2 vol-normalized/heat-capped portfolio. The running baseline (`paper_pnl_v1`) is a fixed-notional equal-weight portfolio — different from the validated strategy. All 5 closed trades are losses (−133.72 total).

**Evidence gates that would need to pass before reconsideration:**
1. Lane B (`paper_pnl_volnorm_v1` or equivalent) must be initialized and executing the V2 volnorm portfolio forward.
2. Minimum forward observation window: at least 30 equity bars (currently 14) under the V2 volnorm portfolio.
3. Net profit positive after all costs (funding + estimated slippage + commission).
4. Sharpe ratio > 0.5 (annualized) over the forward window.
5. Max drawdown within pre-specified bounds.
6. All 5 baseline loss trades must be explainable as statistical noise or regime-specific, not structural flaw.
7. Walk-forward validation on the forward segment must not contradict the edge claim.

### 4.2 `BLOCK_LIVE_INTEGRATION`

**Current state:** Live exchange connectivity is explicitly blocked. No exchange API keys exist. No exchange connector code has been reviewed.

**Evidence gates that would need to pass before reconsideration:**
1. `EDGE_UNPROVEN` must be lifted first (edge must be proven).
2. Shadow deployment must have been running successfully for at least 30 days.
3. Kill-switch policy and implementation must exist and be tested.
4. Exchange integration safety plan must be written and reviewed.
5. Order execution safety plan must be written and reviewed.
6. Alerting/observability must be in place.
7. Reconciliation SOP must exist and be tested.
8. A formal risk review must have been conducted and documented.

### 4.3 No 2x/Shorting

**Current state:** All positions are long-only, leverage = 1.0, no margin/liquidation schema columns exist.

**Evidence gates that would need to pass before reconsideration:**
1. Long-only 1x edge must be proven (see 4.1).
2. A separate research document must analyze whether 2x or shorting improves risk-adjusted returns (not just gross returns).
3. Margin requirements, liquidation risk, and funding cost asymmetry must be modeled.
4. Separate validation must be done for short-side edge.
5. Position sizing policy must be updated to cover leverage and short positions.

### 4.4 No Exchange Keys

**Current state:** No exchange API keys are stored or used. No exchange connector code exists.

**Evidence gates that would need to pass before reconsideration:**
1. `BLOCK_LIVE_INTEGRATION` must be lifted first.
2. All exchange integration safety requirements must be met.
3. API key management must follow documented security procedures (hardware-backed secrets, minimal permissions, key rotation).
4. No exchange keys may be stored in the repo, environment, or any location accessible to non-authorized operators.

### 4.5 No Writer/Live/Backfill/Data-Refresh

**Current state:** Writer mode (`--writer`, `--allow-prod-lane`), live trading, backfill, and data-refresh are all blocked.

**Evidence gates that would need to pass before reconsideration:**
1. `EDGE_UNPROVEN` must be lifted.
2. Shadow deployment criteria must be met.
3. Live deployment criteria must be met.
4. Each specific operation (writer, backfill, data-refresh mutation) must have its own risk assessment.

---

## 5. Decision Matrix

| Gate | Current Status | Rationale | Source |
|---|---|---|---|
| Prod clean-carry report | **CLEAN** | Publication-schema verifier passed with 0 failures, 0 reason codes. Post-merge audit 13/13 pass. | [`qnty_prod_clean_carry_status_summary`](docs/status/qnty_prod_clean_carry_status_summary_after_report_promotion_2026-07-09.md) |
| Shadow clean-carry | **CLEAN** | Prior shadow promotion receipts (PR #116 chain) reached `CLEAN_NET_OF_CARRY` for shadow lane. | [`qnty_post_promotion_pnl_risk_audit`](docs/status/qnty_post_promotion_pnl_risk_audit_2026-07-09.md) |
| Edge/profit evidence | **UNPROVEN** | Running baseline is not the validated portfolio. 14 forward bars, 5 losing trades. No statistical significance. | [`QNTY_STRATEGY_VALIDITY_EVIDENCE_PACK`](docs/experiments/QNTY_STRATEGY_VALIDITY_EVIDENCE_PACK_2026-06-18.md) |
| Shadow deployment | **BLOCKED** | No shadow deployment criteria defined. 8 HARD_BLOCK gaps remain (edge, kill-switch, exchange safety, order execution, shadow criteria, live criteria, slippage). | This document, §3 |
| Live integration | **BLOCKED** | `BLOCK_LIVE_INTEGRATION` is explicit and unchanged. All evidence gates in §4.2 are unmet. | Prior receipts |
| 2x/shorting | **BLOCKED** | Long-only 1x edge not proven. No short-side analysis exists. No margin/liquidation schema. | [`qnty_post_promotion_pnl_risk_audit`](docs/status/qnty_post_promotion_pnl_risk_audit_2026-07-09.md) |
| Exchange integration | **BLOCKED** | No exchange keys, no connector code, no integration safety plan. | This document, §3 row 12 |
| **Next allowed work** | **Docs-only validation planning / offline analysis planning** | Only documentation and offline analysis are permitted. No implementation, no mutation, no deployment. | This document |

### Gap Inventory Summary

| Blocker Level | Count | Categories |
|---|---|---|
| **HARD_BLOCK** | 8 | 1 (edge), 2 (OOS), 5 (slippage), 10 (kill-switch), 12 (exchange safety), 13 (order execution), 17 (shadow criteria), 18 (live criteria) |
| **SOFT_BLOCK** | 8 | 3 (walk-forward), 4 (regime), 6 (funding persistence), 8 (drawdown/ruin), 9 (position sizing), 11 (data drift), 14 (reconciliation), 15 (alerting) |
| **INFO** | 2 | 7 (liquidity), 16 (rollback) |
| **TOTAL** | **18** | |

---

## 6. Recommended Next Concrete Milestone

### `QNTY_OFFLINE_EDGE_VALIDATION_PLAN_AFTER_CLEAN_CARRY`

The smallest safe next step is a **docs-only plan for offline edge validation** — not implementation. This plan should specify:

1. **Lane B initialization:** What code changes are needed to initialize a second paper lane (`paper_pnl_volnorm_v1`) running the V2 vol-normalized/heat-capped portfolio. No mutation — just a plan.
2. **Forward observation requirements:** Minimum bar count, minimum time window, statistical significance thresholds before any edge claim could be evaluated.
3. **Slippage/fee model:** How to estimate realistic execution costs for the offline analysis. Define the model; do not implement it.
4. **Data requirements:** What additional data (if any) is needed beyond what CSV refresh provides.
5. **Success criteria:** What would need to be true for the offline edge analysis to produce a credible edge/not-edge verdict.
6. **Kill-switch spec:** What conditions would trigger automatic or manual shutdown — definition only, not implementation.
7. **No-go gates:** What conditions would cause the offline edge analysis to abort with INCONCLUSIVE or NO_EDGE.

**Do not implement anything.** Produce only a markdown plan document. The plan's verdict would be `QNTY_OFFLINE_EDGE_VALIDATION_PLAN_AFTER_CLEAN_CARRY_RECORDED`.

---

## Appendices

### A. Artifact Chain Reference

| Step | Artifact | PR | Status |
|---|---|---|---|
| 1 | Full-window snapshot semantics + writer emission | PR #120/#121 | Merged |
| 2 | CLI entrypoint for full-window emission | PR #123 | Merged |
| 3 | Emission CLI merged to main | PR #125 (5e08c86f) | Merged |
| 4 | Prod artifact emission (snapshot + bundle) | PR #126 | Executed |
| 5 | Schema reconciliation (verify_and_publish_candidate) | PR #130 | Merged |
| 6 | VM validation of publication candidate | PR #131 | Completed |
| 7 | Official report promotion (42-key, CLEAN_NET_OF_CARRY) | PR #132 | Executed |
| 8 | Post-merge audit (13/13) | PR #133 | Completed |
| 9 | Clean-carry status summary | PR #134 | Merged |
| 10 | **Risk/readiness gap analysis** | **PR #135 (this PR)** | **Open, unmerged** |

### B. Active Hard Blocks (unchanged)

- `EDGE_UNPROVEN` — first recorded in [`QNTY_STRATEGY_VALIDITY_EVIDENCE_PACK`](docs/experiments/QNTY_STRATEGY_VALIDITY_EVIDENCE_PACK_2026-06-18.md)
- `BLOCK_LIVE_INTEGRATION` — explicit across all subsequent receipts
- Long-only / 1x remains the only assumed lane

### C. Verdict

```
QNTY_RISK_AND_READINESS_GAP_ANALYSIS_AFTER_CLEAN_CARRY_RECORDED