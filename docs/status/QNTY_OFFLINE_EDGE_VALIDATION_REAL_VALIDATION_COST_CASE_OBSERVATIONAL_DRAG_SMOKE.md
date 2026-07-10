# QNTY Offline Edge Validation — Real Data Cost-Case Observational Drag Smoke

Status: `BLOCKED_BY_VALIDATION_IMPLEMENTATION`

Run ID: `QNTY_OFFLINE_EDGE_VALIDATION_REAL_VALIDATION_COST_CASE_OBSERVATIONAL_DRAG_SMOKE_RECORDED_BLOCKED`

This docs-only receipt records the successful real-data smoke of the cost-case
observational-drag scaffold merged in PR #159. It transcribes the completed
smoke result; it does not rerun the command or compute new values.

## PR dependency

- Requires merged PR #159: `8f2f7d0664f6b31aeb03eb10a5c1d95767fc164c`.

## Scratch

- Fresh scratch: `/tmp/qnty_scratch_pr159_smoke_1783710783`
- Scratch HEAD: `8f2f7d0664f6b31aeb03eb10a5c1d95767fc164c`
- PR #159 merge commit was confirmed as scratch HEAD/ancestor.
- `quantbot.__file__`: `/tmp/qnty_scratch_pr159_smoke_1783710783/quantbot/__init__.py`
- Scratch Git status was clean.

## Source and staging

- Source CSVs: 20 total (10 OHLCV and 10 funding).
- Bars staging: `/tmp/qnty_real_validation_bars_1783710783` (10 symlinks).
- Funding staging: `/tmp/qnty_real_validation_funding_1783710783` (10 symlinks).
- Staging contained symlinks only.
- All 20 pre/post source SHA-256 values were identical.
- No source CSVs or generated receipt are committed.

## Command result

- Exit status: `0`
- Standard output:

```text
final_offline_verdict=BLOCKED_BY_VALIDATION_IMPLEMENTATION
receipt_sha256=7b4a72e5d180ce8fb1122a686f216db5bc8699c04860872fb9e48a3013933544
receipt_path=/tmp/qnty_real_validation_cost_drag_smoke_1783710783/real_validation_receipt.json
```

## Receipt

- Path: `/tmp/qnty_real_validation_cost_drag_smoke_1783710783/real_validation_receipt.json`
- SHA-256: `7b4a72e5d180ce8fb1122a686f216db5bc8699c04860872fb9e48a3013933544`
- The receipt remains under `/tmp` and is not committed.

Recorded receipt fields:

- `validation_receipt.kind`: `qnty_offline_edge_real_validation_receipt`
- `validation_receipt.version`: `0.1.0`
- `code_commit_sha`: `8f2f7d0664f6b31aeb03eb10a5c1d95767fc164c`
- `final_offline_verdict`: `BLOCKED_BY_VALIDATION_IMPLEMENTATION`
- `final_offline_verdict_rationale`: schema/skeleton-only receipt with
  observational close-to-close metadata; no strategy returns, PnL, Sharpe,
  paper-engine calculation, or edge/profit/live-readiness claim
- `input_inventory`: present
- `row_materialization`: present
- `gross_observational_returns`: present
- `cost_case_observational_drag`: present
- Drag `calculation_status`: `DESCRIPTIVE_OBSERVATIONAL_DRAG_ONLY`

## Cost-case drag summary

| Case | Drag bps/observation | Files | Gross observations |
|---|---:|---:|---:|
| low | 9.0 | 10 | 50935 |
| base | 22.0 | 10 | 50935 |
| high | 44.0 | 10 | 50935 |

## Base-case per-file summary

| Filename | Count | Mean | Min | Max |
|---|---:|---:|---:|---:|
| ADAUSDT_8h_ohlcv.csv | 5270 | -0.002160677839 | -0.191289050722 | 0.308774904591 |
| AVAXUSDT_8h_ohlcv.csv | 5270 | -0.001749577433 | -0.238346632566 | 0.268397673486 |
| BNBUSDT_8h_ohlcv.csv | 5270 | -0.001875984220 | -0.156088391768 | 0.141601113219 |
| BTCUSDT_8h_ohlcv.csv | 5270 | -0.001916580491 | -0.121017988510 | 0.080823632031 |
| DOTUSDT_8h_ohlcv.csv | 5270 | -0.002314114413 | -0.278087573964 | 0.195688576510 |
| ETHUSDT_8h_ohlcv.csv | 5270 | -0.001965485939 | -0.125425182319 | 0.173433231204 |
| LINKUSDT_8h_ohlcv.csv | 5270 | -0.001945515268 | -0.193634589282 | 0.196270744681 |
| MATICUSDT_8h_ohlcv.csv | 3505 | -0.002058997081 | -0.194099710704 | 0.194792006731 |
| SOLUSDT_8h_ohlcv.csv | 5270 | -0.001552316984 | -0.294186827662 | 0.286935545957 |
| XRPUSDT_8h_ohlcv.csv | 5270 | -0.001755872234 | -0.188458547704 | 0.375397567157 |

## Base-case split counts

| Split | Train observations | Validation observations |
|---|---:|---:|
| split_00 | 0 | 17560 |
| split_01 | 17560 | 17562 |
| split_02 | 35122 | 15813 |

## Structural assertions

- `required_outputs_present`: all false.
- `forbidden_calculation_status`: all false.
- `guardrail_status`: all true.
- Recursive forbidden-key and candidate-string assertions passed.
- Top-level `pnl`, `sharpe`, `edge`, and `strategy_performance` were absent.
- Generic `return`/`returns` were absent as keys.
- `net_return_value`, `cost_adjusted_return`, `funding_adjusted_return`, and
  `price_change` were absent.
- `trade`/`trades`, `signal`/`signals`, `position`/`positions`, and `portfolio`
  were absent.
- `OFFLINE_EDGE_CANDIDATE` was absent from the final verdict.
- `EDGE_CANDIDATE` was absent everywhere.

## Postflight

- Pre/post SHA-256 values were identical for all 20 source CSVs.
- The only generated file was the receipt under `/tmp`.
- There was no scratch `output/` directory.
- Scratch Git status was clean, with zero modified or untracked files.
- No repository `tmp/` files or output files were generated.
- There were no `/srv/qnty` references or accesses.
- There were no DB paths or mutations and no CSV mutations.
- No paper engine or live integration was used.
- No exchange keys were used.
- No report was promoted.

## Interpretation

The merged PR #159 scaffold can apply descriptive low/base/high cost-drag
assumptions over real-data gross observational close-to-close summaries. This
proves cost-drag calculation plumbing only.

It does not validate edge, compute PnL, compute Sharpe, compute risk metrics,
apply funding adjustment, or create trades, signals, positions, or portfolio
results. It does not change `EDGE_UNPROVEN` or `BLOCK_LIVE_INTEGRATION`.

The final verdict remains `BLOCKED_BY_VALIDATION_IMPLEMENTATION`.

## Forbidden vocabulary

The following terms are forbidden as claims and are listed here only to make
that restriction explicit:

- `PROFITABLE`
- `LIVE_READY`
- `DEPLOY_READY`
- `CLEAN_EDGE`
- `PRODUCTION_READY`
