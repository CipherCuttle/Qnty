# QNTY Offline Edge Validation — Real-Data Preflight Ready Receipt

Status: `DATA_READY_FOR_OFFLINE_VALIDATION`

This is a **docs-only receipt record**. It documents the result of one
real-data preflight capture run performed per the procedure in
[QNTY_OFFLINE_EDGE_VALIDATION_REAL_DATA_PREFLIGHT_RUNBOOK.md](QNTY_OFFLINE_EDGE_VALIDATION_REAL_DATA_PREFLIGHT_RUNBOOK.md)
after PR #147 (schema-aware data-quality profiles for bars/funding/manifest).
It contains no code changes.

## 1. Important disclaimers

- This is **data-quality readiness only**.
- This is **not edge validation**.
- This is **not a profit claim**.
- This is **not live readiness**.
- **No PnL was computed.**
- **No paper engine was run.**
- **No real walk-forward was run.**
- **No report was promoted.**
- `EDGE_UNPROVEN` remains active.
- `BLOCK_LIVE_INTEGRATION` remains active.

## 2. Run identifier

```
QNTY_OFFLINE_EDGE_VALIDATION_REAL_DATA_PREFLIGHT_AFTER_SCHEMA_PROFILES_RECORDED_READY
```

## 3. PR dependency

- Requires merged PR #147 (schema-aware data-quality profiles for
  bars/funding/manifest).
- Scratch checkout `HEAD` / `origin/main` at capture time:
  `49aff3f85b6b903c3f6234b41c1c2de8e03b63ab`

## 4. Receipt provenance

- Receipt path was under `/tmp` only (never committed):
  `/tmp/qnty_offline_edge_real_data_preflight_after_schema_profiles_1783690231/validation_receipt.json`
- Receipt file `sha256`:
  `65463bf7dc255f632bdb32b3d5b3f9fd457afac5b48317d8aa7ecef0739544c3`
- The receipt itself is **not** committed to this repo.

## 5. Input

- Source directory: `/home/swirky/DevHub/repos/Qnty/data/*.csv`
- 20 CSVs total:
  - 10 `*_ohlcv.csv` (bars role)
  - 10 `*_funding.csv` (funding role)
- Source data is gitignored (`.gitignore: data/`) and was not committed.
- Source data was **not** located under `/srv/qnty`.
- Symlink-only staging was used under `/tmp` for the capture run (no real
  CSVs were copied).
- No manifest directory was available for this run; manifest coverage was
  omitted / recorded as missing, not silently treated as present.

## 6. Receipt summary

- `final_verdict`: `SKELETON_ONLY`
- Advisory verdict (per runbook §6): `DATA_READY_FOR_OFFLINE_VALIDATION`
- `input_manifest_fingerprint`:
  `3dec994114769a16939afa9b0041a8162a308dcb05ca196557407b26a0d35b0d`
- `total_row_count`: `103730`
  - bars row count: `50945`
  - funding row count: `52785`
- `csv_file_count`: `20`
- `global_min_timestamp`: `1625097600000` (2021-07-01)
- `global_max_timestamp`: `2026-04-22T16:00:00`

## 7. Readiness flags

Aggregate:

- `has_any_rows`: `true`
- `has_timestamp_column`: `true`
- `timestamps_monotonic`: `true`
- `no_duplicate_timestamps`: `true`
- `no_null_required_values`: `true`
- `has_duplicate_timestamps`: `false`
- `has_non_monotonic_timestamps`: `false`
- `has_null_values`: `false`
- `missing_required_columns`: `[]`
- `missing_required_columns_by_role`: `{bars: [], funding: []}`

Bars role: all readiness gates `true`; `missing_required_columns: []`.

Funding role: all readiness gates `true`; `missing_required_columns: []`.
Funding schema was checked as `symbol` / `fundingTime` / `fundingRate`;
`markPrice` is optional and was fully populated in this run.

## 8. Forbidden checks (confirmed absent)

- No top-level `pnl` key.
- No top-level `sharpe` key.
- No top-level `edge` key.
- No top-level `strategy_performance` key.
- `EDGE_CANDIDATE` does not appear anywhere in the receipt.

## 9. Postflight checks (confirmed)

- Pre/post `sha256` of all 20 source CSVs identical (source data untouched).
- Repo `git status` clean apart from this docs-only change.
- No DB files touched.
- No `output/` write.
- `/srv/qnty` did not exist on the capture host and was not touched.
- No timers/services/cron touched.
- No `tmp/` repo files created or staged.
- Receipt preserved under `/tmp` only; not committed to this repo.

## 10. Interpretation

The prior `DATA_NOT_READY_FOR_OFFLINE_VALIDATION` result was caused by the
old generic OHLCV schema being applied to Binance funding files, which
produced spurious missing/invalid-column failures for funding CSVs. After
PR #147, bars and funding are validated with role-aware schema profiles:

- bars are validated as OHLCV.
- funding is validated as the Binance funding-rate schema
  (`symbol` / `fundingTime` / `fundingRate`, with `markPrice` optional).

Therefore the offline data in `/home/swirky/DevHub/repos/Qnty/data/` is
**structurally ready** for a future, separately-scoped offline
edge-validation step. This receipt makes no claim about that future step's
outcome.

## 11. Explicit non-claims

The following vocabulary is **forbidden** anywhere in this document or any
artifact derived from this preflight, except as this explicit "forbidden"
listing:

- `EDGE_CANDIDATE`
- `PROFITABLE`
- `LIVE_READY`
- `CLEAN_EDGE`
- `DEPLOY_READY`

None of these are legitimate outputs of a data-quality preflight.
`EDGE_UNPROVEN` and `BLOCK_LIVE_INTEGRATION` remain the standing
project-wide guardrails regardless of this receipt's advisory verdict.

## 12. Verification performed for this PR

- `git diff --check` — no whitespace errors.
- `git diff --name-only origin/main...HEAD` — docs-only change confirmed.
- Confirmed no `/tmp` receipt committed.
- Confirmed no real CSVs committed.
- Confirmed no `quantbot/`, `tests/`, `scripts/`, or `ops/` changes.
- Confirmed no `CLAUDE.md` changes.
- Confirmed no stray `tmp/` files.
