# QNTY Offline Edge Validation — Real Data Funding Observational Adjustment Smoke

Status: `BLOCKED_BY_VALIDATION_IMPLEMENTATION`

Run ID: `QNTY_OFFLINE_EDGE_VALIDATION_REAL_VALIDATION_FUNDING_OBSERVATIONAL_ADJUSTMENT_SMOKE_RECORDED_BLOCKED`

This docs-only receipt records the successful real-data smoke of the funding
observational-adjustment scaffold merged in PR #161. It transcribes the
completed smoke result; it does not rerun the command or compute new values.

## PR dependency

- Requires merged PR #161: `5baa6f17c935f5604a92466ed7ffbe92977829fc`.

## Scratch

- Fresh scratch: `/tmp/qnty_scratch_pr161_smoke_1783712514`
- Scratch HEAD: `5baa6f17c935f5604a92466ed7ffbe92977829fc`
- PR #161 merge commit was included, and scratch HEAD was the merge commit.
- `quantbot.__file__`: `/tmp/qnty_scratch_pr161_smoke_1783712514/quantbot/__init__.py`
- Scratch Git status was clean.

## Source and staging

- Source CSVs: 20 total (10 OHLCV/bars and 10 funding).
- Bars staging contained 10 symlinks.
- Funding staging contained 10 symlinks.
- Source hashes were captured before execution for all 20 files.
- All 20 pre/post source SHA-256 values were identical.
- Output and symlink directories were confined to `/tmp`.
- Symlinks still targeted the correct source-role files.
- No source CSVs or generated receipt are committed.

## Command result

- Exit status: `0`
- Standard output:

```text
final_offline_verdict=BLOCKED_BY_VALIDATION_IMPLEMENTATION
receipt_sha256=f15f710087411653b7fd20ceb94a03f5f8623b448ff53b5f085f862d4b4607b0
receipt_path=/tmp/qnty_real_validation_funding_observational_smoke_1783712514/real_validation_receipt.json
```

## Receipt

- Path: `/tmp/qnty_real_validation_funding_observational_smoke_1783712514/real_validation_receipt.json`
- SHA-256: `f15f710087411653b7fd20ceb94a03f5f8623b448ff53b5f085f862d4b4607b0`
- The receipt hash matched standard output.
- The receipt remains under `/tmp` and is not committed.

Recorded receipt fields:

- `validation_receipt.kind`: `qnty_offline_edge_real_validation_receipt`
- `validation_receipt.version`: `0.1.0`
- `code_commit_sha`: `5baa6f17c935f5604a92466ed7ffbe92977829fc`
- `final_offline_verdict`: `BLOCKED_BY_VALIDATION_IMPLEMENTATION`
- `final_offline_verdict_rationale`: schema/skeleton-only receipt; no strategy
  returns, PnL, Sharpe, paper-engine calculation, or edge/profit/live-readiness
  claim
- `input_inventory`: present
- `row_materialization`: present
- `gross_observational_returns`: present
- `cost_case_observational_drag`: present
- `funding_observational_adjustments`: present
- `required_outputs_present`: all false
- `forbidden_calculation_status`: all false
- `guardrail_status`: all true

## Funding observational adjustments

- `calculation_status`: `FUNDING_OBSERVATIONAL_ADJUSTMENT_ONLY`
- `processed_role`: `funding`
- `ignored_roles`: `bars`
- `bars_adjusted_status`: `NOT_EXECUTED`
- Funding files: 10
- Total observations: 52785

## Per-file funding summary

| File | Observations | Positive | Negative | Zero | Min | Max | Mean |
|---|---:|---:|---:|---:|---:|---:|---:|
| ADAUSDT | 5271 | 4082 | 1189 | 0 | -0.00137741 | 0.0012723 | 6.63409884272434e-05 |
| AVAXUSDT | 5271 | 3710 | 1560 | 1 | -0.00351003 | 0.00152602 | 4.458377727186492e-05 |
| BNBUSDT | 5271 | 949 | 1488 | 2834 | -0.00208684 | 0.00110313 | -5.3467655093910075e-05 |
| BTCUSDT | 5271 | 4494 | 777 | 0 | -0.00119172 | 0.00088148 | 6.929507114399545e-05 |
| DOTUSDT | 5271 | 3212 | 2059 | 0 | -0.00331019 | 0.00104196 | 5.796977803073422e-06 |
| ETHUSDT | 5271 | 4399 | 872 | 0 | -0.00301937 | 0.00113675 | 6.662276797571618e-05 |
| LINKUSDT | 5271 | 4576 | 695 | 0 | -0.00102351 | 0.00115808 | 8.524993170176437e-05 |
| MATICUSDT | 5271 | 4456 | 815 | 0 | -0.00217745 | 0.0045 | 8.109849554164296e-05 |
| SOLUSDT | 5346 | 3755 | 1591 | 0 | -0.02 | 0.00121532 | -2.651555742611298e-05 |
| XRPUSDT | 5271 | 4044 | 1227 | 0 | -0.00219334 | 0.0011 | 6.689260861316638e-05 |

The SOLUSDT minimum funding rate of `-0.02` is recorded as observed metadata
only, not as an error or strategy conclusion.

## Per-split aggregate observation counts

| Split | Train observations | Validation observations |
|---|---:|---:|
| split_00 | 0 | 17645 |
| split_01 | 17645 | 17570 |
| split_02 | 35215 | 17570 |

## Forbidden-content inspection

- Top-level `pnl`, `sharpe`, `edge`, and `strategy_performance` were absent.
- Exact generic keys `return` and `returns` were absent recursively.
- `net_return_value`, `cost_adjusted_return`, `funding_adjusted_return`, and
  `price_change` were absent.
- `trade`/`trades`, `signal`/`signals`, `position`/`positions`, and `portfolio`
  were absent.
- `OFFLINE_EDGE_CANDIDATE` was absent from the final verdict.
- `EDGE_CANDIDATE` was absent throughout the receipt.

## Postflight

- Pre/post SHA-256 values were identical for all 20 source CSVs.
- The only emitted validation artifact was `real_validation_receipt.json`.
- No DB or CSV files were emitted.
- No `/srv/qnty` reference appeared in command output or the receipt.
- There were no scratch `output/` writes or scratch-local `tmp/` directory.
- Scratch Git status was clean.
- No paper engine was executed.
- No exchange-key or live integration was used.
- No report was promoted.
- No PR was opened during the smoke.

## Interpretation

The merged PR #161 scaffold can read and summarize real funding CSV
observations by deterministic split windows. This proves funding observational
metadata plumbing only.

It does not validate edge, compute PnL, compute Sharpe, compute risk metrics,
compute funding-adjusted strategy results, or create trades, signals,
positions, or portfolio results. It does not change `EDGE_UNPROVEN` or
`BLOCK_LIVE_INTEGRATION`.

The final verdict remains `BLOCKED_BY_VALIDATION_IMPLEMENTATION`.

## Forbidden vocabulary

The following terms are forbidden as claims and are listed here only to make
that restriction explicit:

- `PROFITABLE`
- `LIVE_READY`
- `DEPLOY_READY`
- `CLEAN_EDGE`
- `PRODUCTION_READY`
