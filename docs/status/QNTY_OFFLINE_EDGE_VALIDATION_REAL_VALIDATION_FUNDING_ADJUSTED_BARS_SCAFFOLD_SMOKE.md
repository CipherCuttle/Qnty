# QNTY Offline Edge Validation — Real-Data Funding-Adjusted Bars Scaffold Smoke

## Status

`BLOCKED_BY_VALIDATION_IMPLEMENTATION`

## Run ID

`QNTY_OFFLINE_EDGE_VALIDATION_REAL_VALIDATION_FUNDING_ADJUSTED_BARS_SCAFFOLD_SMOKE_RECORDED_BLOCKED`

## Dependency

- PR #175
- merge commit `e6e3210f3dc845bb68723b58e5bb83e5e52b3239`

## Execution

- scratch: `/tmp/qnty_scratch_pr175_funding_adjusted_bars_scaffold_smoke_20260711_215143`
- receipt: `/tmp/qnty_pr175_scaffold_smoke_output/real_validation_receipt.json`
- SHA-256: `345fd8311d1fe3e7a838684b0a550ce81d49446a0c3676c7c9ad43059d1b88b6`
- exit status: `0`
- stderr empty
- final verdict: `BLOCKED_BY_VALIDATION_IMPLEMENTATION`
- output directory contained exactly one JSON receipt
- 10 bars + 10 funding files staged via `/tmp` symlinks preserving filenames
- all 20 source CSV pre/post hashes matched
- scratch worktree clean and removed after verification
- source repo unchanged except pre-existing untracked `plans/`
- no stale `/srv/qnty/repo`
- `quantbot.__file__` resolved inside scratch using a clean venv without system-site editable-install shadowing

## Scaffold summary

| Field                      | Value                                              |
| --------------------------- | -------------------------------------------------- |
| calculation status         | `FUNDING_ADJUSTED_BARS_SCAFFOLD_DIAGNOSTIC_ONLY`   |
| funding application status | `DIAGNOSTIC_SCAFFOLD_ONLY_NOT_APPLIED_TO_STRATEGY` |
| readiness gate required    | `true`                                             |
| canonicalization policy    | `floor_to_second`                                  |
| source sha                 | `e6e3210f3dc845bb68723b58e5bb83e5e52b3239`         |
| symbols                    | 10                                                  |
| eligible                   | 8                                                   |
| blocked                    | 2                                                    |
| materialized               | 8                                                   |
| skipped                    | 2                                                    |

## Materialized eligible symbols

| Symbol   | Status                         | Rows | Matched | Funding present | Missing funding | Duplicate canonical funding | Sample rows |
| -------- | ------------------------------ | ---: | ------: | --------------: | --------------: | --------------------------: | ----------: |
| ADAUSDT  | `MATERIALIZED_DIAGNOSTIC_ROWS` | 5271 |    5271 |            5271 |               0 |                           0 |          10 |
| AVAXUSDT | `MATERIALIZED_DIAGNOSTIC_ROWS` | 5271 |    5271 |            5271 |               0 |                           0 |          10 |
| BNBUSDT  | `MATERIALIZED_DIAGNOSTIC_ROWS` | 5271 |    5271 |            5271 |               0 |                           0 |          10 |
| BTCUSDT  | `MATERIALIZED_DIAGNOSTIC_ROWS` | 5271 |    5271 |            5271 |               0 |                           0 |          10 |
| DOTUSDT  | `MATERIALIZED_DIAGNOSTIC_ROWS` | 5271 |    5271 |            5271 |               0 |                           0 |          10 |
| ETHUSDT  | `MATERIALIZED_DIAGNOSTIC_ROWS` | 5271 |    5271 |            5271 |               0 |                           0 |          10 |
| LINKUSDT | `MATERIALIZED_DIAGNOSTIC_ROWS` | 5271 |    5271 |            5271 |               0 |                           0 |          10 |
| XRPUSDT  | `MATERIALIZED_DIAGNOSTIC_ROWS` | 5271 |    5271 |            5271 |               0 |                           0 |          10 |

For all materialized eligible symbols:

- `readiness_status = ELIGIBLE_FOR_FUTURE_FUNDING_APPLICATION`
- `canonicalization_policy = floor_to_second`
- `first_timestamp = 2021-07-01T00:00:00Z`
- `last_timestamp = 2026-04-22T16:00:00Z`
- sample rows are capped deterministically at 10 rows
- sample rows span `bar_row_index` 0 to 5270
- funding-rate min/max/zero/positive/negative counts vary per symbol and are real observed values, but this is still not carry math or return math

## Skipped blocked symbols

| Symbol    | Status                                   | Scaffold status             | Blocked reasons                                                                                                                                                                                                        |
| --------- | ----------------------------------------- | ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| MATICUSDT | `BLOCKED_FOR_FUTURE_FUNDING_APPLICATION` | `SKIPPED_BY_READINESS_GATE` | `COUNT_MISMATCH`, `PARTIAL_CANONICAL_TIMESTAMP_SET_MATCH`, `CANONICALIZED_FUNDING_WITHOUT_BARS`, `RANGE_MISMATCH`, `EXTRA_FUNDING_OUTSIDE_BARS_RANGE`, `EMPTY_BARS_NONEMPTY_FUNDING`, `NO_CANONICAL_TIMESTAMP_MATCH` |
| SOLUSDT   | `BLOCKED_FOR_FUTURE_FUNDING_APPLICATION` | `SKIPPED_BY_READINESS_GATE` | `COUNT_MISMATCH`, `PARTIAL_CANONICAL_TIMESTAMP_SET_MATCH`, `CANONICALIZED_FUNDING_WITHOUT_BARS`, `AMBIGUOUS_NEAREST_BAR`                                                                                             |

For skipped symbols, exactly four keys were present:

- `symbol`
- `readiness_status`
- `scaffold_status`
- `blocked_reasons`

- no `sample_rows`
- no funding-rate summary fields
- no row materialization

## Sample row audit

All materialized sample rows contain exactly these seven keys:

- `timestamp`
- `canonical_funding_timestamp`
- `bar_row_index`
- `funding_row_index`
- `funding_rate`
- `funding_rate_present`
- `readiness_status`

- no OHLCV price fields
- no full row dataset emitted outside capped receipt samples

## Required interpretation

The scaffold proves that eight readiness-gated symbols have complete timestamp-aligned funding-rate row availability under `floor_to_second` canonicalization. MATICUSDT and SOLUSDT remain skipped by the readiness gate. This is not funding application to strategy. It does not approve funding-adjusted returns, strategy validity, edge, profitability, or live readiness.

- `EDGE_UNPROVEN` remains.
- `BLOCK_LIVE_INTEGRATION` remains.
- final verdict remains `BLOCKED_BY_VALIDATION_IMPLEMENTATION`.
- funding application remains scaffold-only.
- no full joined row-level dataset was produced.
- no OHLCV values were emitted.
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
- no `pnl`
- no `sharpe`
- no `drawdown`
- no `portfolio`
- no `trades`
- no `positions`
- no `signals`
- no `strategy`
- no DB, paper-engine, live integration, exchange keys, report promotion, data-refresh, service, timer, or systemd activity
- all 20 pre/post source SHA-256 hashes matched
- output directory contained only the JSON receipt
- stale `/srv/qnty/repo` was not used
