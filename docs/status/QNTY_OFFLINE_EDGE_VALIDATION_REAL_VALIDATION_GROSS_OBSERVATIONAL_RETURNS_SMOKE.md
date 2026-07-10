# QNTY Offline Edge Validation — Real Data Gross Observational Returns Smoke

## Status

`BLOCKED_BY_VALIDATION_IMPLEMENTATION`

## Run ID

`QNTY_OFFLINE_EDGE_VALIDATION_REAL_VALIDATION_GROSS_OBSERVATIONAL_RETURNS_SMOKE_RECORDED_BLOCKED`

## Scope

This document records the successful execution of the merged PR #157 real-data smoke for bars-only gross close-to-close observational metadata. It records the supplied smoke result only; it does not recompute values, commit the generated receipt, copy source CSVs, or modify implementation or tests.

## PR dependency

- Requires merged PR #157: `87d50ff8fc9786e49dbc2fdb1a4aac9bb80fea60`

## Scratch

- Timestamp: `1783709050`
- Fresh scratch: `/tmp/qnty_scratch_pr157_smoke_1783709050`
- Scratch HEAD: `87d50ff8fc9786e49dbc2fdb1a4aac9bb80fea60`
- PR #157 merge confirmed included.
- `quantbot.__file__`: `/tmp/qnty_scratch_pr157_smoke_1783709050/quantbot/__init__.py`
- Scratch working tree: clean
- Source working tree: clean

## Source and staging

- Source data: `/home/swirky/DevHub/repos/Qnty/data/*.csv`
- Source CSV inventory: 20 total
  - Bars: 10
  - Funding: 10
- Staging inventory:
  - Bars symlinks: 10
  - Funding symlinks: 10
  - Copied files: 0
  - Symlinks only
  - All staging directories were under `/tmp` only
- All 20 pre-run and post-run source SHA-256 values were identical.
- Source CSVs and the generated receipt are not committed.

## Command result

- Exit status: `0`
- Stdout:

  ```text
  final_offline_verdict=BLOCKED_BY_VALIDATION_IMPLEMENTATION
  receipt_sha256=96a600ee1a93e95655522f10251722ff05facef19c39ab0f137f89fdf246d620
  receipt_path=/tmp/qnty_real_validation_gross_observational_smoke_1783709050/real_validation_receipt.json
  ```

## Receipt

- Path: `/tmp/qnty_real_validation_gross_observational_smoke_1783709050/real_validation_receipt.json`
- SHA-256: `96a600ee1a93e95655522f10251722ff05facef19c39ab0f137f89fdf246d620`
- The receipt remains under `/tmp` and is not committed.

## Receipt fields

- `validation_receipt.kind`: `qnty_offline_edge_real_validation_receipt`
- `validation_receipt.version`: `0.1.0`
- `code_commit_sha`: `87d50ff8fc9786e49dbc2fdb1a4aac9bb80fea60`
- `final_offline_verdict`: `BLOCKED_BY_VALIDATION_IMPLEMENTATION`
- `final_offline_verdict_rationale`: `schema/skeleton-only receipt; gross observational close-to-close metadata may be present, but strategy returns, PnL, Sharpe, and paper-engine calculation remain unimplemented`
- Input roles: 2
- `row_materialization`: present
- `gross_observational_returns`: present

## Gross observational returns

- `calculation_status`: `GROSS_OBSERVATIONAL_RETURNS_ONLY`
- Processed role: `bars`
- Ignored roles: `funding`
- `funding_adjusted_status`: `NOT_EXECUTED`
- Bars files processed: 10
- Total observations: 50935

### Per-file summary

| Filename | Observations | Positive | Negative | Zero | Min gross | Max gross | Mean gross |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `ADAUSDT_8h_ohlcv.csv` | 5270 | 2571 | 2672 | 27 | -0.1890890507 | 0.3109749046 | 0.0000393222 |
| `AVAXUSDT_8h_ohlcv.csv` | 5270 | 2598 | 2663 | 9 | -0.2361466326 | 0.2705976735 | 0.0004504226 |
| `BNBUSDT_8h_ohlcv.csv` | 5270 | 2741 | 2526 | 3 | -0.1538883918 | 0.1438011132 | 0.0003240158 |
| `BTCUSDT_8h_ohlcv.csv` | 5270 | 2665 | 2604 | 1 | -0.1188179885 | 0.0830236320 | 0.0002834195 |
| `DOTUSDT_8h_ohlcv.csv` | 5270 | 2612 | 2634 | 24 | -0.2758875740 | 0.1978885765 | -0.0001141144 |
| `ETHUSDT_8h_ohlcv.csv` | 5270 | 2696 | 2572 | 2 | -0.1232251823 | 0.1756332312 | 0.0002345141 |
| `LINKUSDT_8h_ohlcv.csv` | 5270 | 2654 | 2606 | 10 | -0.1914345893 | 0.1984707447 | 0.0002544847 |
| `MATICUSDT_8h_ohlcv.csv` | 3505 | 1709 | 1766 | 30 | -0.1918997107 | 0.1969920067 | 0.0001410029 |
| `SOLUSDT_8h_ohlcv.csv` | 5270 | 2642 | 2616 | 12 | -0.2919868277 | 0.2891355460 | 0.0006476830 |
| `XRPUSDT_8h_ohlcv.csv` | 5270 | 2580 | 2663 | 27 | -0.1862585477 | 0.3775975672 | 0.0004441278 |

### Per-split gross observation counts

| Split | Train observations | Validation observations |
| --- | ---: | ---: |
| `split_00` | 0 | 17560 |
| `split_01` | 17560 | 17562 |
| `split_02` | 35122 | 15813 |

## Structural assertions

- Every `required_outputs_present` value was `false`.
- Every `forbidden_calculation_status` value was `false`.
- Every `guardrail_status` value was `true`.
- Top-level `pnl` was absent.
- Top-level `sharpe` was absent.
- Top-level `edge` was absent.
- Top-level `strategy_performance` was absent.
- Exact generic `return` and `returns` keys were absent.
- `net_return_value` was absent.
- `cost_adjusted_return` was absent.
- `funding_adjusted_return` was absent.
- `price_change` was absent.
- `trade` and `trades` were absent.
- `signal` and `signals` were absent.
- `position` and `positions` were absent.
- `portfolio` was absent.
- `OFFLINE_EDGE_CANDIDATE` was absent from the final verdict.
- `EDGE_CANDIDATE` was absent everywhere in the receipt.

## Postflight

- Pre-run and post-run SHA-256 manifests for all 20 source CSVs were identical.
- The receipt SHA-256 was independently confirmed.
- The output directory contained only the receipt and was under `/tmp`.
- Both staging directories were under `/tmp`.
- No staging files were copied.
- No `/srv/qnty` input, output, or receipt reference was present.
- No scratch `output/` or repository-local `tmp/` paths were present.
- Scratch and source working trees were clean.
- No source CSV mutation occurred.
- No database path or mutation was used.
- The paper engine was not run.
- No live integration occurred.
- No exchange-key operation occurred.
- No report promotion occurred.
- No PR was opened during the smoke.

## Interpretation

The merged PR #157 scaffold can compute bars-only gross close-to-close observational metadata on real ready data. This proves descriptive gross-observation calculation plumbing only.

It does not validate edge. It does not compute PnL, Sharpe, or risk metrics. It does not apply costs or funding adjustment. It does not create trades, signals, positions, or portfolio results. It does not change `EDGE_UNPROVEN` or `BLOCK_LIVE_INTEGRATION`.

The final verdict remains `BLOCKED_BY_VALIDATION_IMPLEMENTATION`.

## Forbidden vocabulary

The following terms must not be used as claims for this smoke and appear here only to list that restriction explicitly:

- `PROFITABLE`
- `LIVE_READY`
- `DEPLOY_READY`
- `CLEAN_EDGE`
- `PRODUCTION_READY`
