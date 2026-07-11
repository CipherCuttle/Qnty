# QNTY_OFFLINE_EDGE_VALIDATION_REAL_VALIDATION_FUNDING_ADJUSTMENT_ROW_SCAFFOLD_SMOKE

## Status

`BLOCKED_BY_VALIDATION_IMPLEMENTATION`

## Run ID

`QNTY_OFFLINE_EDGE_VALIDATION_REAL_VALIDATION_FUNDING_ADJUSTMENT_ROW_SCAFFOLD_SMOKE_RECORDED_BLOCKED`

## Dependency

- PR #181
- merge commit `82bf5a05916b35df24cec27844daf67bac122e26`

## Execution

- receipt: `/tmp/qnty_funding_row_scaffold_smoke_output/real_validation_receipt.json`
- SHA-256: `a7898b6e89d3284bdd290697c82fdadce3546124ebe60734338b73a97ca8f6cb`
- exit status: `0`
- final verdict: `BLOCKED_BY_VALIDATION_IMPLEMENTATION`
- output under `/tmp`
- no repo files edited
- no PRs or commits created during smoke
- 10 OHLCV + 10 funding files staged via `/tmp` symlinks preserving filenames
- all 20 source CSV pre/post hashes matched
- source repo clean except pre-existing untracked `plans/`
- scratch worktree clean and removed
- symlink staging removed
- stale `/srv/qnty/repo` was not used

## Row scaffold summary

| Field                                 | Value                                                  |
| ------------------------------------- | ------------------------------------------------------ |
| calculation status                    | `FUNDING_ADJUSTMENT_ROW_SCAFFOLD_DIAGNOSTIC_ONLY`      |
| funding adjustment application status | `DIAGNOSTIC_ROW_SCAFFOLD_ONLY_NOT_APPLIED_TO_STRATEGY` |
| strategy application status           | `NOT_EXECUTED`                                         |
| pnl application status                | `NOT_EXECUTED`                                         |
| funding rate unit                     | `decimal_rate_not_percent`                             |
| notional policy                       | `UNIT_NOTIONAL_DIAGNOSTIC_ONLY`                        |
| side policy                           | `BOTH_HYPOTHETICAL_SIDES_DIAGNOSTIC_ONLY`              |
| sample policy                         | `CAPPED_DETERMINISTIC_SAMPLES_ONLY`                    |
| sample size per symbol                | `10`                                                   |
| eligible symbols                      | `8`                                                    |
| blocked symbols                       | `2`                                                    |
| materialized symbols                  | `8`                                                    |
| skipped symbols                       | `2`                                                    |

## Eligible symbol table

| Symbol     | scaffold_status                | row_scaffold_status                        | total_rows | sample_count |
| ---------- | ------------------------------ | ------------------------------------------ | ---------: | -----------: |
| `ADAUSDT`  | `MATERIALIZED_DIAGNOSTIC_ROWS` | `MATERIALIZED_DIAGNOSTIC_CASHFLOW_SAMPLES` |       5271 |           10 |
| `AVAXUSDT` | `MATERIALIZED_DIAGNOSTIC_ROWS` | `MATERIALIZED_DIAGNOSTIC_CASHFLOW_SAMPLES` |       5271 |           10 |
| `BNBUSDT`  | `MATERIALIZED_DIAGNOSTIC_ROWS` | `MATERIALIZED_DIAGNOSTIC_CASHFLOW_SAMPLES` |       5271 |           10 |
| `BTCUSDT`  | `MATERIALIZED_DIAGNOSTIC_ROWS` | `MATERIALIZED_DIAGNOSTIC_CASHFLOW_SAMPLES` |       5271 |           10 |
| `DOTUSDT`  | `MATERIALIZED_DIAGNOSTIC_ROWS` | `MATERIALIZED_DIAGNOSTIC_CASHFLOW_SAMPLES` |       5271 |           10 |
| `ETHUSDT`  | `MATERIALIZED_DIAGNOSTIC_ROWS` | `MATERIALIZED_DIAGNOSTIC_CASHFLOW_SAMPLES` |       5271 |           10 |
| `LINKUSDT` | `MATERIALIZED_DIAGNOSTIC_ROWS` | `MATERIALIZED_DIAGNOSTIC_CASHFLOW_SAMPLES` |       5271 |           10 |
| `XRPUSDT`  | `MATERIALIZED_DIAGNOSTIC_ROWS` | `MATERIALIZED_DIAGNOSTIC_CASHFLOW_SAMPLES` |       5271 |           10 |

## Blocked symbol table

| Symbol      | scaffold_status             | row_scaffold_status         | blocked_reasons | key count |
| ----------- | --------------------------- | --------------------------- | --------------- | --------: |
| `MATICUSDT` | `SKIPPED_BY_READINESS_GATE` | `SKIPPED_BY_READINESS_GATE` | carried forward |         4 |
| `SOLUSDT`   | `SKIPPED_BY_READINESS_GATE` | `SKIPPED_BY_READINESS_GATE` | carried forward |         4 |

## Sample checks

- 80 sample rows verified
- 8 eligible symbols × 10 samples each
- `unit_notional = "1"` for all 80
- `formula = LONG_NEGATES_FUNDING_RATE_SHORT_PRESERVES_FUNDING_RATE_TIMES_NOTIONAL` for all 80
- `application_scope = DIAGNOSTIC_SAMPLE_ONLY_NOT_STRATEGY` for all 80
- `long_cashflow_factor = -Decimal(funding_rate) * Decimal("1")` for all 80
- `short_cashflow_factor = Decimal(funding_rate) * Decimal("1")` for all 80
- `long_cashflow_factor == -short_cashflow_factor` for all 80
- all cashflow factors emitted as strings
- no `timestamp`
- no `canonical_funding_timestamp`
- no OHLCV fields
- no strategy fields
- no side key
- no notional key beyond diagnostic `unit_notional`
- no position keys

## Interpretation

This smoke proves only that `funding_adjustment_row_scaffold_diagnostics` is emitted during the real-data CLI path and that capped sample cashflow factors are computed from existing scaffold sample rows using unit notional and both hypothetical sides.

It does **not** prove funding has been applied to strategy or bars.

### Explicit limitations

- `EDGE_UNPROVEN` remains.
- `BLOCK_LIVE_INTEGRATION` remains.
- final verdict remains `BLOCKED_BY_VALIDATION_IMPLEMENTATION`.
- no funding-adjusted bars were produced.
- no full joined dataset was produced.
- no timestamps were emitted.
- no canonical funding timestamps were emitted.
- no OHLCV values were emitted.
- no real strategy side was used.
- no real notional was used.
- no side inference occurred.
- no notional inference occurred.
- no position inference occurred.
- no bar return calculation occurred.
- no funding-adjusted return calculation occurred.
- no net return calculation occurred.
- no price change calculation occurred.
- no carry calculation occurred.
- no PnL was computed.
- no Sharpe was computed.
- no drawdown was computed.
- no risk metric was computed.
- no edge candidate was produced.
- no trades, positions, signals, or portfolio logic occurred.
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