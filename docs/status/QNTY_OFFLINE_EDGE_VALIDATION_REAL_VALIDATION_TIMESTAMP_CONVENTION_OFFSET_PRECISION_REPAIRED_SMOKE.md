# QNTY_OFFLINE_EDGE_VALIDATION_REAL_VALIDATION_TIMESTAMP_CONVENTION_OFFSET_PRECISION_REPAIRED_SMOKE

## Status

`BLOCKED_BY_VALIDATION_IMPLEMENTATION`

## Run ID

`QNTY_OFFLINE_EDGE_VALIDATION_REAL_VALIDATION_TIMESTAMP_CONVENTION_OFFSET_PRECISION_REPAIRED_SMOKE_RECORDED_BLOCKED`

## Dependency

- PR #169
- merge commit `b45ce42ca05aa8817691afc861c5efd7a4988be1`

## Scratch / Execution

- scratch worktree: `/tmp/qnty_scratch_pr169_precision_repaired_timestamp_convention_smoke_1783722558`
- scratch HEAD: `b45ce42ca05aa8817691afc861c5efd7a4988be1`
- `quantbot.__file__` resolved inside scratch
- real 20-file CSV corpus from `/home/swirky/DevHub/repos/Qnty/data/*_8h_ohlcv.csv` and `*_8h_funding.csv`
- staged through `/tmp`-only symlinks preserving real filenames
- 10 bars files + 10 funding files
- command used both `--bars-dir` and `--funding-dir`
- `--split-count 3`
- exit code `0`
- output directory contained only `real_validation_receipt.json`
- pre/post SHA-256 of all 20 source CSVs matched

## Receipt

- path: `/tmp/qnty_timestamp_convention_receipt_1783722558/real_validation_receipt.json`
- SHA-256: `4a38fae7c0d2c9cb3c89572616b94dbca4bbf13b95fdf497731f35855bb2b52f`
- printed and independently calculated hashes matched
- `code_commit_sha`: `b45ce42ca05aa8817691afc861c5efd7a4988be1`
- receipt remained under `/tmp` and must not be committed

## Top-Level Timestamp Convention Summary

- `calculation_status`: `FUNDING_TO_BARS_TIMESTAMP_CONVENTION_DIAGNOSTIC_ONLY`
- `timestamp_match_policy`: `DIAGNOSTIC_EXACT_AND_SHIFTED_UTC_TIMESTAMP_SETS_ONLY`
- `funding_application_status`: `NOT_EXECUTED`
- `symbol_count`: 10
- `candidate_offsets`: `-24h`, `-16h`, `-12h`, `-8h`, `-4h`, `-1h`, `0h`, `+1h`, `+4h`, `+8h`, `+12h`, `+16h`, `+24h`

## Main Finding

The precision-repaired diagnostic shows that the previously observed exact-timestamp mismatches are explained by sub-second funding timestamp jitter for all bars-unmatched rows in the smoke:

- `nearest_delta_zero_microseconds_count`: 0 across all symbols
- `nearest_delta_subsecond_nonzero_count`: equals `nearest_delta_sample_size` for all symbols
- maximum observed absolute nearest delta: 47,000 microseconds / 47ms
- most common nearest delta: 1,000 microseconds / 1ms

### Per-Symbol Table

| Symbol    | Bars timestamps | Funding timestamps | 0h exact matched | Bars unmatched at 0h | Best offset | Matched at best | Nearest delta sample | Zero µs | Subsecond nonzero | Max abs µs | Most common µs |
| --------- | --------------: | -----------------: | ---------------: | -------------------: | ----------- | --------------: | -------------------: | ------: | ----------------: | ---------: | -------------: |
| ADAUSDT   |            5271 |               5271 |             2909 |                 2362 | 0h          |            2909 |                 2362 |       0 |              2362 |      47000 |           1000 |
| AVAXUSDT  |            5271 |               5271 |             2909 |                 2362 | 0h          |            2909 |                 2362 |       0 |              2362 |      47000 |           1000 |
| BNBUSDT   |            5271 |               5271 |             2909 |                 2362 | 0h          |            2909 |                 2362 |       0 |              2362 |      47000 |           1000 |
| BTCUSDT   |            5271 |               5271 |             2909 |                 2362 | 0h          |            2909 |                 2362 |       0 |              2362 |      47000 |           1000 |
| DOTUSDT   |            5271 |               5271 |             2909 |                 2362 | 0h          |            2909 |                 2362 |       0 |              2362 |      47000 |           1000 |
| ETHUSDT   |            5271 |               5271 |             2909 |                 2362 | 0h          |            2909 |                 2362 |       0 |              2362 |      47000 |           1000 |
| LINKUSDT  |            5271 |               5271 |             2909 |                 2362 | 0h          |            2909 |                 2362 |       0 |              2362 |      47000 |           1000 |
| MATICUSDT |            3506 |               5271 |             1875 |                 1631 | +24h        |            2167 |                 1631 |       0 |              1631 |      47000 |           1000 |
| SOLUSDT   |            5271 |               5346 |             2909 |                 2362 | 0h          |            2909 |                 2362 |       0 |              2362 |      47000 |           1000 |
| XRPUSDT   |            5271 |               5271 |             2909 |                 2362 | 0h          |            2909 |                 2362 |       0 |              2362 |      47000 |           1000 |

### Histogram / Jitter Summary

- 33 distinct delta-magnitude bins across all symbols
- representative distribution:

  - 1ms: 530
  - 2ms: 469
  - 3ms: 375
  - 4ms: 292
  - 5ms: 206
  - 6ms: 132
  - 7ms: 87
  - 8ms: 61
  - 9ms: 47
  - 10–19ms: 339 total
  - 20–47ms: 23 total
- 70.6% under 10ms
- 96.1% under 20ms
- 100% under 50ms

### MATIC Notes

- MATIC has 3506 bars and 5271 funding rows.
- MATIC bars end around 2024-09-11 while funding extends to 2026-04-22.
- MATIC's bars-unmatched rows in the overlapping region are also sub-second jitter.
- MATIC's +24h candidate offset improves matched count from 1875 to 2167, but this does not prove the source cause.
- Do not claim or speculate that MATIC came from Kraken, Binance, or any specific exchange source unless the receipt proves it. The receipt does not prove source cause.

### SOL Notes

- SOL has 5271 bars and 5346 funding rows.
- SOL has 75 extra funding rows beyond the normal bars count.
- SOL's bars-unmatched rows are also sub-second jitter.
- The 75 extra funding rows remain a separate structural issue from sub-second jitter.

## Interpretation

The smoke proves the precision-repaired nearest-delta diagnostic executes against the real 20-file corpus and correctly preserves signed microsecond deltas. It shows that the bars-unmatched rows under exact datetime equality are explained by sub-second funding timestamp jitter in this corpus, with maximum observed nearest delta 47ms.

This supports a future timestamp canonicalization diagnostic, but does not itself approve timestamp canonicalization, funding application, funding-adjusted bars, strategy validity, edge, profitability, or live readiness.

### Explicit State

- `EDGE_UNPROVEN` remains.
- `BLOCK_LIVE_INTEGRATION` remains.
- funding application remains blocked.
- timestamp canonicalization is not yet approved.
- no funding-adjusted bars were produced.
- no joined row-level dataset was produced.
- no strategy, trade, position, PnL, Sharpe, risk, portfolio, return, or edge metric was computed.
- no live readiness is implied.

## Guardrails

- final verdict remained `BLOCKED_BY_VALIDATION_IMPLEMENTATION`
- all six `required_outputs_present` values were false
- all five `forbidden_calculation_status` values were false
- all four `guardrail_status` values were true
- no PnL, Sharpe, edge, strategy-performance, risk, trade, signal, position, or portfolio calculation keys
- no exact generic `return` or `returns` keys
- no `funding_adjusted_return`
- no `net_return_value`
- no `price_change`
- no `OFFLINE_EDGE_CANDIDATE`
- no `EDGE_CANDIDATE`
- no DB, paper-engine, live integration, exchange keys, report promotion, data-refresh, service, timer, or systemd activity
- all 20 pre/post source SHA-256 hashes matched
- source repo git status was clean
- scratch worktree was clean before removal
- output directory contained only the JSON receipt
- scratch worktree was removed after run
- stale `/srv/qnty/repo` was not used as source of truth
