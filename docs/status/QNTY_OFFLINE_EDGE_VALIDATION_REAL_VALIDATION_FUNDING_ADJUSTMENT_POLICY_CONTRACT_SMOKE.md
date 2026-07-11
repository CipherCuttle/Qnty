# QNTY Offline Edge Validation — Real-Data Funding Adjustment Policy Contract Smoke

**Status:** `BLOCKED_BY_VALIDATION_IMPLEMENTATION`

**Run ID:** `QNTY_OFFLINE_EDGE_VALIDATION_REAL_VALIDATION_FUNDING_ADJUSTMENT_POLICY_CONTRACT_SMOKE_RECORDED_BLOCKED`

## Dependency

- PR #177
- merge commit `a0c62e2bbdc110ba52d0ea393a6cbe660dfd15d4`

## Execution

- scratch: `/tmp/qnty_scratch_pr177_funding_adjustment_policy_contract_smoke_20260711_222613`
- receipt: `/tmp/qnty_pr177_policy_contract_smoke/output/real_validation_receipt.json`
- SHA-256: `02f90fa469f456c4198ca21fddc548d3d674e16256330e0cd6c83ccc3aba2920`
- exit status: `0`
- stderr empty
- final verdict: `BLOCKED_BY_VALIDATION_IMPLEMENTATION`
- output directory contained exactly one JSON receipt
- 10 bars + 10 funding files staged via `/tmp` symlinks preserving filenames
- all 20 source CSV pre/post hashes matched
- scratch worktree clean and removed after verification
- source repo unchanged except pre-existing untracked `plans/`
- no stale `/srv/qnty/repo`
- `quantbot.__file__` resolved inside scratch using isolated `.venv_scratch`, avoiding editable-install shadowing

## Policy contract summary

| Field                                 | Value                                                |
| ------------------------------------- | ----------------------------------------------------- |
| calculation status                    | `FUNDING_ADJUSTMENT_POLICY_CONTRACT_DIAGNOSTIC_ONLY` |
| funding adjustment application status | `NOT_EXECUTED`                                       |
| strategy application status           | `NOT_EXECUTED`                                       |
| pnl application status                | `NOT_EXECUTED`                                       |
| requires scaffold diagnostics         | `true`                                                |
| scaffold section required             | `funding_adjusted_bars_scaffold_diagnostics`         |
| canonicalization policy required      | `floor_to_second`                                    |
| funding rate column                   | `fundingRate`                                        |
| funding rate unit                     | `decimal_rate_not_percent`                           |
| funding rate annualization status     | `NOT_ANNUALIZED`                                     |
| timestamp match policy                | `EXACT_CANONICAL_FUNDING_TIMESTAMP_TO_BAR_TIMESTAMP` |
| eligible symbols                      | 8                                                     |
| blocked symbols                       | 2                                                     |
| policy symbols                        | 10                                                    |

## Policy subsections

All five policy subsections matched expected values:

1. `timestamp_policy_contract`
   - source: `SCAFFOLD_OUTPUT_ONLY`
   - canonicalization required: `floor_to_second`
   - future match rule: `EXACT_CANONICAL_FUNDING_TIMESTAMP_TO_BAR_TIMESTAMP`
   - nearest-neighbor matching allowed: false
   - forward fill allowed: false
   - backfill allowed: false
   - interpolation allowed: false
   - timezone inference allowed: false
   - exchange clock inference allowed: false

2. `eligibility_policy_contract`
   - eligible scaffold status required: `MATERIALIZED_DIAGNOSTIC_ROWS`
   - skipped scaffold status carried forward: `SKIPPED_BY_READINESS_GATE`
   - blocked reasons carried forward: true
   - hardcoded symbol list used: false

3. `funding_rate_policy_contract`
   - funding rate column: `fundingRate`
   - funding rate unit: `decimal_rate_not_percent`
   - annualization allowed: false
   - compounding allowed: false
   - missing rate inference allowed: false
   - fail closed on missing or invalid: true

4. `position_side_policy_contract`
   - long side contract: `LONG_PAYS_POSITIVE_FUNDING_RECEIVES_NEGATIVE_FUNDING`
   - short side contract: `SHORT_RECEIVES_POSITIVE_FUNDING_PAYS_NEGATIVE_FUNDING`
   - position side source required: `FUTURE_STRATEGY_POSITION_SIDE_REQUIRED`
   - position side inference status: `NOT_EXECUTED`
   - position side application status: `NOT_EXECUTED`
   - this is contract text only; no long/short side was inferred or applied

5. `output_policy_contract`
   - may summarize eligible/skipped symbols: true
   - may include policy strings and validation flags: true
   - emits full row dataset: false
   - emits OHLCV values: false
   - emits row-level adjusted values: false
   - emits strategy values: false
   - emits performance values: false

## Per-symbol policy table (eligible)

| Symbol   | Policy status                                   | Rows | Matched | Funding present | Missing funding | Duplicate canonical funding |
| -------- | ------------------------------------------------ | ---: | ------: | --------------: | --------------: | --------------------------: |
| ADAUSDT  | `ELIGIBLE_FOR_FUTURE_FUNDING_ADJUSTMENT_POLICY` | 5271 |    5271 |            5271 |               0 |                           0 |
| AVAXUSDT | `ELIGIBLE_FOR_FUTURE_FUNDING_ADJUSTMENT_POLICY` | 5271 |    5271 |            5271 |               0 |                           0 |
| BNBUSDT  | `ELIGIBLE_FOR_FUTURE_FUNDING_ADJUSTMENT_POLICY` | 5271 |    5271 |            5271 |               0 |                           0 |
| BTCUSDT  | `ELIGIBLE_FOR_FUTURE_FUNDING_ADJUSTMENT_POLICY` | 5271 |    5271 |            5271 |               0 |                           0 |
| DOTUSDT  | `ELIGIBLE_FOR_FUTURE_FUNDING_ADJUSTMENT_POLICY` | 5271 |    5271 |            5271 |               0 |                           0 |
| ETHUSDT  | `ELIGIBLE_FOR_FUTURE_FUNDING_ADJUSTMENT_POLICY` | 5271 |    5271 |            5271 |               0 |                           0 |
| LINKUSDT | `ELIGIBLE_FOR_FUTURE_FUNDING_ADJUSTMENT_POLICY` | 5271 |    5271 |            5271 |               0 |                           0 |
| XRPUSDT  | `ELIGIBLE_FOR_FUTURE_FUNDING_ADJUSTMENT_POLICY` | 5271 |    5271 |            5271 |               0 |                           0 |

For every eligible/materialized symbol, the receipt records:

- `scaffold_status = MATERIALIZED_DIAGNOSTIC_ROWS`
- `canonicalization_policy = floor_to_second`
- `funding_rate_column = fundingRate`
- `funding_rate_unit = decimal_rate_not_percent`
- `timestamp_match_policy = EXACT_CANONICAL_FUNDING_TIMESTAMP_TO_BAR_TIMESTAMP`
- `row_availability_status = COMPLETE`
- future application required inputs:
  - `explicit_position_side = FUTURE_STRATEGY_POSITION_SIDE_REQUIRED`
  - `notional_or_size_source = FUTURE_STRATEGY_NOTIONAL_SOURCE_REQUIRED`
  - `strategy_rule_source = FUTURE_STRATEGY_RULE_SOURCE_REQUIRED`

## Blocked/skipped symbols

| Symbol    | Scaffold status             | Policy status               |
| --------- | ---------------------------- | ---------------------------- |
| MATICUSDT | `SKIPPED_BY_READINESS_GATE` | `BLOCKED_BY_READINESS_GATE` |
| SOLUSDT   | `SKIPPED_BY_READINESS_GATE` | `BLOCKED_BY_READINESS_GATE` |

For blocked/skipped symbols:

- blocked reasons were carried forward
- no row samples
- no funding-rate summary
- no future application inputs
- exactly four keys were present: `symbol`, `scaffold_status`, `policy_status`, `blocked_reasons`

## Required interpretation

The smoke proves the policy-contract section survives the real 20-file corpus and correctly inherits the same 8 eligible / 2 blocked symbol split from the scaffold. It defines future funding-adjustment rules but does not perform funding adjustment. No long/short side, notional, size, or strategy rule is inferred. All future calculation prerequisites remain explicit.

- `EDGE_UNPROVEN` remains.
- `BLOCK_LIVE_INTEGRATION` remains.
- final verdict remains `BLOCKED_BY_VALIDATION_IMPLEMENTATION`.
- funding adjustment application remains `NOT_EXECUTED`.
- strategy application remains `NOT_EXECUTED`.
- PnL application remains `NOT_EXECUTED`.
- no full joined row-level dataset was produced.
- no OHLCV values were emitted.
- no row-level adjusted values were emitted.
- no strategy values were emitted.
- no performance values were emitted.
- no strategy returns were computed.
- no bar returns were computed.
- no funding-adjusted returns were computed.
- no net returns were computed.
- no PnL was computed.
- no Sharpe was computed.
- no drawdown was computed.
- no risk metric was computed.
- no edge candidate was produced.
- no strategy, trade, signal, position, or portfolio logic was executed.
- no live readiness is implied.

## Guardrails

- final verdict remained `BLOCKED_BY_VALIDATION_IMPLEMENTATION`
- all `required_outputs_present` values were false
- all `forbidden_calculation_status` values were false
- all `guardrail_status` values were true
- no `OFFLINE_EDGE_CANDIDATE`
- no `EDGE_CANDIDATE`
- no `funding_adjusted_return`
- no `net_return_value`
- no `price_change`
- no DB, paper-engine, live integration, exchange keys, report promotion, data-refresh, service, timer, or systemd activity
- all 20 pre/post source SHA-256 hashes matched
- output directory contained only the JSON receipt
- stale `/srv/qnty/repo` was not used
