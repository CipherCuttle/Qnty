# QNTY Offline Edge Validation — Real Data Input Inventory + Split Materialization Smoke

**Status:** `BLOCKED_BY_VALIDATION_IMPLEMENTATION`

**Run ID:** `QNTY_OFFLINE_EDGE_VALIDATION_REAL_VALIDATION_INPUT_INVENTORY_SPLIT_SMOKE_RECORDED_BLOCKED`

**Date:** 2026-07-10

---

## PR Dependency

- Requires merged PR #152.
- PR #152 merge commit: `03f0cc256ff14f5cb2997b4dda2407c85e61a82f`.

## Scratch Environment

- Fresh scratch: `/tmp/qnty_scratch_pr152_smoke_1783698729`.
- Scratch HEAD: `03f0cc256ff14f5cb2997b4dda2407c85e61a82f`.
- `quantbot.__file__` resolved under scratch at
  `/tmp/qnty_scratch_pr152_smoke_1783698729/quantbot/__init__.py`.
- PR #152 merge confirmed included: `true`.
- Scratch git status: clean.

## Source and Staging

- Source data: `/home/swirky/DevHub/repos/Qnty/data/*.csv`.
- Source inventory: 20 CSVs total, comprising 10 bars files and 10 funding
  files.
- Staging inventory: 20 symlinks and zero copied files.
- All staging directories were under `/tmp` only.
- All 20 preflight and postflight source SHA-256 values were identical.
- No source CSV or generated receipt is committed by this documentation PR.

## Command Result

| Field | Value |
|---|---|
| Exit code | `0` |
| `final_offline_verdict` | `BLOCKED_BY_VALIDATION_IMPLEMENTATION` |
| `receipt_sha256` | `1124b6fd30c8226b5f60d545bf69f8b972c2ecf45ae0a288adc20313fc102b89` |
| `receipt_path` | `/tmp/qnty_real_validation_inventory_split_smoke_1783698729/real_validation_receipt.json` |

## Receipt Summary

- Receipt path:
  `/tmp/qnty_real_validation_inventory_split_smoke_1783698729/real_validation_receipt.json`.
- The receipt remained under `/tmp` only and is not committed.
- Receipt SHA-256:
  `1124b6fd30c8226b5f60d545bf69f8b972c2ecf45ae0a288adc20313fc102b89`.

### Receipt Fields

| Field | Value |
|---|---|
| `validation_receipt.kind` | `qnty_offline_edge_real_validation_receipt` |
| `validation_receipt.version` | `0.1.0` |
| `input_manifest_fingerprint` | `3dec994114769a16939afa9b0041a8162a308dcb05ca196557407b26a0d35b0d` |
| `data_quality_receipt_sha256` | `65463bf7dc255f632bdb32b3d5b3f9fd457afac5b48317d8aa7ecef0739544c3` |
| `code_commit_sha` | `03f0cc256ff14f5cb2997b4dda2407c85e61a82f` |
| `final_offline_verdict` | `BLOCKED_BY_VALIDATION_IMPLEMENTATION` |
| `final_offline_verdict_rationale` | Schema/skeleton-only; returns, PnL, Sharpe, and paper-engine calculations are unimplemented; no edge/profit/live-readiness claim. |

## Input Inventory

The receipt contains two input roles.

| Role | CSV files | Total size (bytes) | Minimum timestamp | Maximum timestamp | Aggregate role fingerprint |
|---|---:|---:|---|---|---|
| `bars` | 10 | 3,041,364 | `2021-07-01T00:00:00Z` | `2026-04-22T16:00:00Z` | `e112f2df89e989cea85696e544b15e66a10ca6a92dc5311f550ed07122e76390` |
| `funding` | 10 | 2,064,501 | `2021-07-01T00:00:00Z` | `2026-04-22T16:00:00Z` | `46e3c5142fcf0a80e1285fce50eb5a78d7da50fa65cff5ef9bccaf5cbde40017` |

## Split Definitions

The receipt materializes three split definitions.

| Split | Train start | Train end | Validation end |
|---|---|---|---|
| `split_00` | `2021-07-01T00:00:00Z` | `2021-07-01T00:00:00Z` | `2023-02-06T13:20:00Z` |
| `split_01` | — | `2023-02-06T13:20:00Z` | `2024-09-14T02:40:00Z` |
| `split_02` | — | `2024-09-14T02:40:00Z` | `2026-04-22T16:00:00Z` |

For every split:

- `calculation_status` is `NOT_EXECUTED`.
- `bars_file_count` is `10`.
- `funding_file_count` is `10`.

## Cost Cases

| Case | Commission bps per side | Slippage bps per side | Spread bps per side | Funding included | Calculation status |
|---|---:|---:|---:|---|---|
| `low` | 2.0 | 2.0 | 0.5 | yes | `NOT_EXECUTED` |
| `base` | 5.0 | 5.0 | 1.0 | yes | `NOT_EXECUTED` |
| `high` | 10.0 | 10.0 | 2.0 | yes | `NOT_EXECUTED` |

## Structural Assertions

- `required_outputs_present`: all `false`.
- `forbidden_calculation_status`: all `false`.
- `guardrail_status`: all `true`.
- Top-level `pnl` is absent.
- Top-level `sharpe` is absent.
- Top-level `edge` is absent.
- Top-level `strategy_performance` is absent.
- `return` is absent as a key.
- `returns` is absent as a key.
- `gross_return_value` is absent as a key.
- `net_return_value` is absent as a key.
- `OFFLINE_EDGE_CANDIDATE` is absent from the final verdict.
- `EDGE_CANDIDATE` is absent everywhere.

## Postflight

- [x] All 20 preflight and postflight source SHA-256 values are identical.
- [x] Output was under `/tmp` only.
- [x] Staging directories were under `/tmp` only.
- [x] Staging contained 20 symlinks and zero regular copied files.
- [x] No `/srv/qnty` input, output, or receipt reference, and no executed
  `/srv/qnty` access.
- [x] No `output/` write in scratch.
- [x] Scratch git status clean.
- [x] No scratch `tmp/` entries.
- [x] No CSV mutation.
- [x] No DB mutation.
- [x] No paper engine execution.
- [x] No live integration.
- [x] Exchange credential environment-variable count: `0`.
- [x] No report promotion.
- [x] No PR was opened during the smoke.

## Interpretation

The merged PR #152 CLI can inventory real ready data and materialize
deterministic split metadata. This proves only metadata readiness for a future
validator.

It does not validate edge. It does not compute returns, PnL, Sharpe, or risk
metrics. It does not change `EDGE_UNPROVEN` or `BLOCK_LIVE_INTEGRATION`.

## Forbidden Vocabulary

The following terms are listed only as forbidden vocabulary and are not claims:

- `PROFITABLE`
- `LIVE_READY`
- `DEPLOY_READY`
- `CLEAN_EDGE`
- `PRODUCTION_READY`

## Verification Checklist

- [x] `git diff --check` passes.
- [x] `git diff --name-only origin/main...HEAD` shows only this status document.
- [x] Docs-only change; no code changes.
- [x] No tests changes.
- [x] No `CLAUDE.md` changes.
- [x] No `/tmp` receipt committed.
- [x] No real CSVs committed.
- [x] No tmp files committed.

## Expected Verdict

`QNTY_OFFLINE_EDGE_VALIDATION_REAL_VALIDATION_INPUT_INVENTORY_SPLIT_SMOKE_DOC_RECORDED`
