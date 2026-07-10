# QNTY Offline Edge Validation Real Validation Funding-to-Bars Alignment Diagnostics Smoke

## Status

`BLOCKED_BY_VALIDATION_IMPLEMENTATION`

Run ID: `QNTY_OFFLINE_EDGE_VALIDATION_REAL_VALIDATION_FUNDING_TO_BARS_ALIGNMENT_DIAGNOSTICS_SMOKE_RECORDED_BLOCKED`

## Dependency

- PR #164
- Merge commit `81efa8c5ae8cca3be7a5113c59184db436688154`

## Scratch and execution

- Scratch worktree: `/tmp/qnty_scratch_pr164_smoke_1783716084`
- Scratch HEAD: `81efa8c5ae8cca3be7a5113c59184db436688154`
- `quantbot.__file__` resolved inside the scratch worktree.
- Execution exited `0` with empty stderr.
- Inputs comprised 10 bars CSVs and 10 funding CSVs, exposed through 20 valid `/tmp`-only staging symlinks.

## Receipt

- Path: `/tmp/qnty_real_validation_funding_bars_alignment_smoke_1783716084/real_validation_receipt.json`
- SHA-256: `5417667a27c4119ce058893931aa30572fd61bf486ab6097d789493a54902d84`
- The printed and independently calculated hashes matched.
- The output directory contained only the JSON receipt.
- The receipt remains under `/tmp` and must not be committed.

## Alignment summary

- `calculation_status`: `FUNDING_TO_BARS_ALIGNMENT_DIAGNOSTIC_ONLY`
- `symbol_count`: 10
- `complete_symbol_count`: 10
- `diagnostic_symbol_count`: 0
- `outlier_symbol_count`: 1
- Absolute funding-rate outlier threshold: `0.01`
- All expected symbols paired, with no missing or extra normalized symbols.
- Bars and funding each had zero unassigned rows.
- SOLUSDT was the sole outlier, with minimum funding rate `-0.02`.

| Symbol | Bars filename | Funding filename | Coverage status | Outlier | Material count divergence or observation |
| --- | --- | --- | --- | --- | --- |
| ADAUSDT | `ADAUSDT_8h_ohlcv.csv` | `ADAUSDT_8h_funding.csv` | `COMPLETE` | false | 5,271 bars rows; 5,271 funding rows |
| AVAXUSDT | `AVAXUSDT_8h_ohlcv.csv` | `AVAXUSDT_8h_funding.csv` | `COMPLETE` | false | 5,271 bars rows; 5,271 funding rows |
| BNBUSDT | `BNBUSDT_8h_ohlcv.csv` | `BNBUSDT_8h_funding.csv` | `COMPLETE` | false | 5,271 bars rows; 5,271 funding rows |
| BTCUSDT | `BTCUSDT_8h_ohlcv.csv` | `BTCUSDT_8h_funding.csv` | `COMPLETE` | false | 5,271 bars rows; 5,271 funding rows |
| DOTUSDT | `DOTUSDT_8h_ohlcv.csv` | `DOTUSDT_8h_funding.csv` | `COMPLETE` | false | 5,271 bars rows; 5,271 funding rows |
| ETHUSDT | `ETHUSDT_8h_ohlcv.csv` | `ETHUSDT_8h_funding.csv` | `COMPLETE` | false | 5,271 bars rows; 5,271 funding rows |
| LINKUSDT | `LINKUSDT_8h_ohlcv.csv` | `LINKUSDT_8h_funding.csv` | `COMPLETE` | false | 5,271 bars rows; 5,271 funding rows |
| MATICUSDT | `MATICUSDT_8h_ohlcv.csv` | `MATICUSDT_8h_funding.csv` | `COMPLETE` | false | 3,506 bars rows versus 5,271 funding rows; split divergence detailed below |
| SOLUSDT | `SOLUSDT_8h_ohlcv.csv` | `SOLUSDT_8h_funding.csv` | `COMPLETE` | true | 5,271 bars rows versus 5,346 funding observations/rows; 75 additional funding rows; minimum funding rate `-0.02` |
| XRPUSDT | `XRPUSDT_8h_ohlcv.csv` | `XRPUSDT_8h_funding.csv` | `COMPLETE` | false | 5,271 bars rows; 5,271 funding rows |

## Limitations

1. `coverage_status=COMPLETE` currently means zero unassigned rows; it does not prove timestamp-by-timestamp joinability.
2. MATIC split data diverges: split_01 has 1,749 bars validation rows versus 1,757 funding validation rows, and split_02 has 0 bars validation rows versus 1,757 funding validation rows.
3. SOL funding history is longer: the bars total pattern corresponds to 5,271 rows, funding has 5,346 observations/rows, and the difference is 75 funding rows.
4. These differences are diagnostic evidence only.
5. This smoke does not establish exact temporal alignment, funding-adjusted returns, strategy validity, edge, profitability, or live readiness.
6. A temporal joinability/coverage hardening slice is required before funding can be applied to bars.

## Guardrails

- All six `required_outputs_present` values were false.
- All five `forbidden_calculation_status` values were false.
- All four `guardrail_status` values were true.
- The receipt contained no PnL, Sharpe, risk, strategy, trades, signals, positions, or portfolio data.
- It contained no generic `return` or `returns` keys and no `OFFLINE_EDGE_CANDIDATE` or `EDGE_CANDIDATE` marker.
- There was no source mutation; all 20 pre/post SHA-256 hashes matched.
- The source and scratch worktrees remained clean.
- There was no DB, paper engine, live integration, exchange-key, report-promotion, refresh, service, timer, or systemd activity.

## Interpretation

The smoke proves that real-style bar and funding filenames normalize and pair by symbol, and that existing split/count/outlier metadata can be emitted.

It does not prove timestamp-level joinability or permit funding adjustment. `EDGE_UNPROVEN` and `BLOCK_LIVE_INTEGRATION` remain.
