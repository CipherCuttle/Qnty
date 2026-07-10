# QNTY Offline Edge Validation — Real Data Row Materialization + Split Assignment Smoke

## Status

`BLOCKED_BY_VALIDATION_IMPLEMENTATION`

## Run ID

`QNTY_OFFLINE_EDGE_VALIDATION_REAL_VALIDATION_ROW_MATERIALIZATION_SPLIT_ASSIGNMENT_SMOKE_RECORDED_BLOCKED_AFTER_SYMLINK_REPAIR`

## Scope

This document records the post-repair real-data row-materialization and split-assignment smoke only. The smoke materialized assignment metadata; it did not execute strategy validation or promote any report.

## PR dependencies

- Requires merged PR #154: `72f950400c93b8c68832dbc46f815ce71dbf189c`
- Requires merged PR #155: `e4a14039cc165fd1d58f0aef67d3e641c1d29c83`

## Scratch

- Fresh scratch: `/tmp/qnty_scratch_pr155_smoke_1783706948`
- Scratch HEAD: `e4a14039cc165fd1d58f0aef67d3e641c1d29c83`
- HEAD subject: `Merge pull request #155...`
- `quantbot.__file__`: `/tmp/qnty_scratch_pr155_smoke_1783706948/quantbot/__init__.py`
- Scratch git status: clean
- Source repository status: clean

## Source and staging

- Source data: `/home/swirky/DevHub/repos/Qnty/data/*.csv`
- Source CSV inventory: 20 total
  - Bars: 10
  - Funding: 10
  - Unclassified: 0
- Staging inventory:
  - Bars symlinks: 10
  - Funding symlinks: 10
  - Copied regular files: 0
  - Invalid symlink targets: 0
  - All staging directories were under `/tmp` only
- All 20 pre-run and post-run source SHA-256 values were identical.
- Source CSVs and the generated receipt are not committed.

## Command result

- Exit status: `0`
- Stdout verdict: `BLOCKED_BY_VALIDATION_IMPLEMENTATION`
- Receipt path: `/tmp/qnty_real_validation_row_materialization_smoke_1783706948/real_validation_receipt.json`
- Receipt SHA-256: `98806174089a3de2c0cd01aa1c5fee10de58aae50b1f702f1030142f3074d699`

The receipt path is recorded for traceability only. The receipt remains under `/tmp` and is not part of this repository change.

## Receipt fields

- `validation_receipt.kind`: `qnty_offline_edge_real_validation_receipt`
- `validation_receipt.version`: `0.1.0`
- `code_commit_sha`: `e4a14039cc165fd1d58f0aef67d3e641c1d29c83`
- `final_offline_verdict`: `BLOCKED_BY_VALIDATION_IMPLEMENTATION`
- `final_offline_verdict_rationale`: `BLOCKED_BY_VALIDATION_IMPLEMENTATION: this is a schema/skeleton-only receipt. No returns, PnL, Sharpe, or paper-engine calculation has been implemented yet. No edge/profit/live-readiness claim is made.`
- Input roles: 2
- Bars files: 10
- Funding files: 10
- `split_definitions` count: 3

## Structural assertions

- Every `required_outputs_present` value was `false`.
- Every `forbidden_calculation_status` value was `false`.
- Every `guardrail_status` value was `true`.
- Top-level `pnl`, `sharpe`, `edge`, and `strategy_performance` were absent.
- `return`, `returns`, `gross_return_value`, `net_return_value`, and `price_change` were absent as keys.
- `trade`, `trades`, `signal`, `signals`, `position`, and `positions` were absent as keys.
- `OFFLINE_EDGE_CANDIDATE` was absent from the final verdict.
- `EDGE_CANDIDATE` was absent everywhere.

## Row materialization

- Present: yes
- `metadata_only`: `true`
- `calculation_status`: `NOT_EXECUTED`
- Every role/file `calculation_status`: `NOT_EXECUTED`
- Files covered:
  - Bars: 10
  - Funding: 10
- Files with `unassigned_rows > 0`: none

## Timestamp policy

- `empty_timestamp`: `UNASSIGNED`
- `malformed_timestamp`: `FAIL_CLOSED`
- `window_start`: `INCLUSIVE`
- `window_end`: `EXCLUSIVE_EXCEPT_FINAL_VALIDATION_INCLUSIVE`

## Role row totals

| Role | Total rows | Assigned rows | Unassigned rows |
| --- | ---: | ---: | ---: |
| Bars | 50,945 | 50,945 | 0 |
| Funding | 52,785 | 52,785 | 0 |

## Per-split row counts

| Role | Split | Train rows | Validation rows |
| --- | --- | ---: | ---: |
| Bars | `split_00` | 0 | 17,570 |
| Bars | `split_01` | 17,570 | 17,562 |
| Bars | `split_02` | 35,132 | 15,813 |
| Funding | `split_00` | 0 | 17,645 |
| Funding | `split_01` | 17,645 | 17,570 |
| Funding | `split_02` | 35,215 | 17,570 |

## Postflight

- All 20 source CSV SHA-256 values were identical before and after the run; the hash diff was empty.
- Run output contained one file, entirely under `/tmp`.
- Both symlink directories were under `/tmp`; all 20 links targeted source CSVs.
- No `/srv/qnty` paths were referenced.
- Scratch contained no `output/` or `tmp/` entries.
- Scratch and source repository statuses were clean.
- No database or source CSV mutation occurred.
- No returns, PnL, Sharpe, risk, price-change, or funding-adjusted-return calculation occurred.
- No trade, signal, or position calculation occurred.
- The paper engine was not run.
- No exchange-key setup, live integration, report promotion, or PR creation occurred during the smoke.

## Interpretation

The merged PR #154 row-materialization feature, after the PR #155 symlink-containment repair, can assign all real ready bars and funding rows into deterministic split windows. This proves row-assignment metadata readiness only.

It does not validate edge. It does not compute returns, PnL, Sharpe, risk metrics, price movement, or funding-adjusted returns. It does not create trades, signals, or positions. It does not run the paper engine. It does not change `EDGE_UNPROVEN` or `BLOCK_LIVE_INTEGRATION`.

The final offline verdict remains `BLOCKED_BY_VALIDATION_IMPLEMENTATION` because the receipt is schema/skeleton-only and the prohibited strategy-performance calculations are not implemented or executed.

## Forbidden vocabulary

The following terms are forbidden as claims for this smoke and appear here only to make that restriction explicit:

- `PROFITABLE`
- `LIVE_READY`
- `DEPLOY_READY`
- `CLEAN_EDGE`
- `PRODUCTION_READY`
