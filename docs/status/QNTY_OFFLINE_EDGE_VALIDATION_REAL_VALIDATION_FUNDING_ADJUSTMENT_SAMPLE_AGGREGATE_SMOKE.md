# QNTY_OFFLINE_EDGE_VALIDATION_REAL_VALIDATION_FUNDING_ADJUSTMENT_SAMPLE_AGGREGATE_SMOKE

## Status

`BLOCKED_BY_VALIDATION_IMPLEMENTATION`

## Run ID

`QNTY_OFFLINE_EDGE_VALIDATION_REAL_VALIDATION_FUNDING_ADJUSTMENT_SAMPLE_AGGREGATE_SMOKE_RECORDED_BLOCKED`

## Commit under test

`2cbb4aa8194ca2ab54bf8e3d798a453ce83df044`

## Dependency

- PR #183
- merge commit `2cbb4aa8194ca2ab54bf8e3d798a453ce83df044`

## Execution

- real-data smoke passed
- used the `offline_edge_real_validation` module directly
- `offline_edge_validation_cli` remains a skeleton / fixture runner and was **not** used for this smoke
- Receipt SHA-256: `a4e0dcb90fcdc737d7fa6c94dbaf9f74b3a5367f180b5e6058882807fd7825a4`
- final verdict: `BLOCKED_BY_VALIDATION_IMPLEMENTATION`
- output under `/tmp`
- 20 CSV files staged via `/tmp` symlinks preserving filenames
  - 10 OHLCV
  - 10 funding
- all 20 source CSV pre/post SHA-256 hashes matched
- no repo files edited during smoke
- no commit or PR created during smoke
- no generated JSON receipt committed
- scratch checkout removed
- symlink staging removed

## Receipt facts

- `code_commit_sha = 2cbb4aa8194ca2ab54bf8e3d798a453ce83df044`
- `final_offline_verdict = BLOCKED_BY_VALIDATION_IMPLEMENTATION`
- all 10 diagnostic sections present
- `funding_adjustment_sample_aggregate_diagnostics` present

## Sample aggregate summary

| Field                                 | Value                                                       |
| ------------------------------------- | ----------------------------------------------------------- |
| calculation status                    | `FUNDING_ADJUSTMENT_SAMPLE_AGGREGATE_DIAGNOSTIC_ONLY`       |
| funding adjustment application status | `DIAGNOSTIC_SAMPLE_AGGREGATE_ONLY_NOT_APPLIED_TO_STRATEGY`  |
| strategy application status           | `NOT_EXECUTED`                                              |
| pnl application status                | `NOT_EXECUTED`                                              |
| requires row scaffold diagnostics     | `true`                                                      |
| row scaffold section required         | `funding_adjustment_row_scaffold_diagnostics`              |
| aggregation scope                     | `CAPPED_SAMPLE_ROWS_ONLY`                                   |
| full dataset aggregation status       | `NOT_EXECUTED`                                              |
| funding rate unit                     | `decimal_rate_not_percent`                                  |
| notional policy                       | `UNIT_NOTIONAL_DIAGNOSTIC_ONLY`                             |
| side policy                           | `BOTH_HYPOTHETICAL_SIDES_DIAGNOSTIC_ONLY`                   |
| sample policy                         | `CAPPED_DETERMINISTIC_SAMPLES_ONLY`                         |
| eligible symbol count                 | `8`                                                         |
| blocked symbol count                  | `2`                                                         |
| materialized symbol count             | `8`                                                         |
| skipped symbol count                  | `2`                                                         |
| total sample row count                | `80`                                                        |
| global long cashflow factor sum       | `-0.00295408`                                               |
| global short cashflow factor sum      | `0.00295408`                                                |
| global long/short sum check           | `0` semantically (rendered as `0E-8`)                       |

## Eligible symbol table

For each eligible symbol: `aggregate_status = MATERIALIZED_DIAGNOSTIC_SAMPLE_AGGREGATES`,
`sample_row_count = 10`,
`application_scope = DIAGNOSTIC_CAPPED_SAMPLE_AGGREGATE_ONLY_NOT_STRATEGY`. The long and
short aggregate cashflow sums are exact `Decimal` opposites and `long_short_sum_check` is
`Decimal` zero. No sample rows, timestamps, canonical timestamps, OHLCV, strategy side,
notional inference, or position fields are emitted.

| Symbol     | aggregate_status                          | sample_row_count | application_scope                                     | long_short_sum_check |
| ---------- | ----------------------------------------- | ---------------: | ----------------------------------------------------- | -------------------- |
| `ADAUSDT`  | `MATERIALIZED_DIAGNOSTIC_SAMPLE_AGGREGATES` |               10 | `DIAGNOSTIC_CAPPED_SAMPLE_AGGREGATE_ONLY_NOT_STRATEGY` | `Decimal` zero       |
| `AVAXUSDT` | `MATERIALIZED_DIAGNOSTIC_SAMPLE_AGGREGATES` |               10 | `DIAGNOSTIC_CAPPED_SAMPLE_AGGREGATE_ONLY_NOT_STRATEGY` | `Decimal` zero       |
| `BNBUSDT`  | `MATERIALIZED_DIAGNOSTIC_SAMPLE_AGGREGATES` |               10 | `DIAGNOSTIC_CAPPED_SAMPLE_AGGREGATE_ONLY_NOT_STRATEGY` | `Decimal` zero       |
| `BTCUSDT`  | `MATERIALIZED_DIAGNOSTIC_SAMPLE_AGGREGATES` |               10 | `DIAGNOSTIC_CAPPED_SAMPLE_AGGREGATE_ONLY_NOT_STRATEGY` | `Decimal` zero       |
| `DOTUSDT`  | `MATERIALIZED_DIAGNOSTIC_SAMPLE_AGGREGATES` |               10 | `DIAGNOSTIC_CAPPED_SAMPLE_AGGREGATE_ONLY_NOT_STRATEGY` | `Decimal` zero       |
| `ETHUSDT`  | `MATERIALIZED_DIAGNOSTIC_SAMPLE_AGGREGATES` |               10 | `DIAGNOSTIC_CAPPED_SAMPLE_AGGREGATE_ONLY_NOT_STRATEGY` | `Decimal` zero       |
| `LINKUSDT` | `MATERIALIZED_DIAGNOSTIC_SAMPLE_AGGREGATES` |               10 | `DIAGNOSTIC_CAPPED_SAMPLE_AGGREGATE_ONLY_NOT_STRATEGY` | `Decimal` zero       |
| `XRPUSDT`  | `MATERIALIZED_DIAGNOSTIC_SAMPLE_AGGREGATES` |               10 | `DIAGNOSTIC_CAPPED_SAMPLE_AGGREGATE_ONLY_NOT_STRATEGY` | `Decimal` zero       |

## Blocked symbol table

For each blocked symbol: `aggregate_status = SKIPPED_BY_READINESS_GATE`,
`blocked_reasons` present, and exactly 3 keys (`symbol`, `aggregate_status`,
`blocked_reasons`). No cashflow aggregates and no sample rows are emitted.

| Symbol      | aggregate_status            | blocked_reasons | key count |
| ----------- | --------------------------- | --------------- | --------: |
| `MATICUSDT` | `SKIPPED_BY_READINESS_GATE` | present         |         3 |
| `SOLUSDT`   | `SKIPPED_BY_READINESS_GATE` | present         |         3 |

## Aggregate checks

- 80 capped diagnostic sample rows aggregated (8 eligible symbols × 10 samples each)
- per symbol, long and short aggregate cashflow sums are exact `Decimal` opposites
- per symbol, `long_short_sum_check` is `Decimal` zero
- `global_long_cashflow_factor_sum = -0.00295408`
- `global_short_cashflow_factor_sum = 0.00295408`
- `global_long_short_sum_check = 0` semantically, rendered as `0E-8`
- no individual sample rows emitted in the aggregate section
- no full-dataset aggregate
- no `timestamp`
- no `canonical_funding_timestamp`
- no OHLCV fields
- no strategy side
- no notional inference
- no position fields

## Interpretation

This smoke proves only that `funding_adjustment_sample_aggregate_diagnostics` is emitted
during the real-data CLI path and that aggregate summaries are computed over capped
diagnostic samples only.

### Explicit limitations — this smoke does **not** prove

- full-dataset aggregate
- funding-adjusted bars
- full joined dataset
- timestamps / canonical timestamps
- OHLCV output
- real strategy side
- real notional
- side inference
- notional inference
- position inference
- bar return
- funding-adjusted return
- net return
- price change
- carry calculation
- PnL
- Sharpe
- drawdown
- risk metric
- edge candidate
- trades
- positions
- signals
- portfolio logic
- live readiness

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

## Closing status

```text
EDGE_UNPROVEN remains.
BLOCK_LIVE_INTEGRATION remains.
final_offline_verdict remains BLOCKED_BY_VALIDATION_IMPLEMENTATION.
Funding diagnostics are diagnostic-complete pending separate governance ADR; no 6L funding-only layer is recommended.
```
