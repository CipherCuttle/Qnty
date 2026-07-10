# QNTY Offline Edge Validation — Real Validation Execution Plan

Status: `PLAN_ONLY`

This is a **docs-only execution plan**. It plans the first real, read-only
offline validation run after data-quality preflight passed. It does not
run that validation, compute any PnL, modify any code, promote any report,
or claim edge / profit / live readiness.

## 1. Purpose

This document is the execution plan for a **future** first real offline
validation run against the structurally-ready real bars/funding data. It
defines the question that run must answer, the outputs it must produce,
the verdict vocabulary it may use, the acceptance gates for a positive
result, and the failure/refusal criteria that must block it.

**This document is not the execution itself.** No validation run happens
in this PR. No CLI in this plan has necessarily been implemented yet (see
§9). Nothing in this document changes `EDGE_UNPROVEN` or
`BLOCK_LIVE_INTEGRATION`, which remain the standing project-wide
guardrails.

## 2. Current preconditions

- PR #147 merged schema-aware data-quality profiles for bars/funding/manifest
  (`feat/qnty-offline-edge-validation-data-quality-schema-profiles`).
- PR #148 recorded `DATA_READY_FOR_OFFLINE_VALIDATION` in
  [QNTY_OFFLINE_EDGE_VALIDATION_REAL_DATA_PREFLIGHT_READY_RECEIPT.md](QNTY_OFFLINE_EDGE_VALIDATION_REAL_DATA_PREFLIGHT_READY_RECEIPT.md).
- Real data **structurally passed** preflight (data-quality readiness only;
  not edge validation, not a profit claim, not live readiness).
- `input_manifest_fingerprint`:
  `3dec994114769a16939afa9b0041a8162a308dcb05ca196557407b26a0d35b0d`
- Preflight receipt `sha256`:
  `65463bf7dc255f632bdb32b3d5b3f9fd457afac5b48317d8aa7ecef0739544c3`
- `total_row_count`: `103730`
  - bars row count: `50945`
  - funding row count: `52785`
- `csv_file_count`: `20`

## 3. Non-goals / forbidden outcomes

This plan, and the future run it describes, must **not**:

- perform any live integration
- promote any report
- deploy anything
- use any exchange keys
- run any writer/trader service
- touch Lane B
- use leverage or shorting
- claim live readiness
- claim profit
- emit `EDGE_CANDIDATE` unless a later, separately implemented validator
  actually proves the defined gates in a separate PR/run
- clear `EDGE_UNPROVEN` before that future execution — it **remains active**
- clear `BLOCK_LIVE_INTEGRATION` before that future execution — it
  **remains active**

## 4. Validation question

The future real offline validation run must answer exactly this question,
and no broader claim:

> Given the structurally ready offline bars/funding data, does the V2
> logic produce a clean, cost-adjusted, out-of-sample offline result under
> conservative assumptions?

This is a question the future run investigates, not a claim this document
makes.

## 5. Required validation outputs

The future run's receipt must be written under `/tmp` only (never
committed) and must contain, at minimum:

- input fingerprint (must match §2's `input_manifest_fingerprint`, or the
  run must record why it differs)
- data-quality receipt hash reference (§2's preflight receipt `sha256`)
- code commit SHA the run executed against
- cost assumptions (commission, slippage, spread, funding treatment)
- split definitions (in-sample / out-of-sample boundaries)
- number of bars used
- number of symbols used
- number of closed trades or candidate decisions
- gross return, if implemented
- net return after costs, if implemented
- max drawdown, if implemented
- Sharpe or a comparable risk-adjusted metric, if implemented
- funding treatment (included / explicitly excluded and why)
- slippage/commission assumptions (explicit numeric values)
- sensitivity cases (at least a low/base/high cost-case matrix)
- baseline comparison (e.g. buy-and-hold or a defined naive baseline)
- final offline verdict, using only the vocabulary in §6

## 6. Verdict vocabulary

The future run may only emit one of these final verdicts:

- `OFFLINE_EDGE_CANDIDATE`
- `NO_EDGE`
- `INCONCLUSIVE`
- `BLOCKED_BY_VALIDATION_IMPLEMENTATION`
- `BLOCKED_BY_DATA_QUALITY_REGRESSION`

`OFFLINE_EDGE_CANDIDATE` is **not** `EDGE_CANDIDATE`. It must only mean an
offline candidate survived the defined gates in §7 under the stated
conservative assumptions. It must **never** be read or reported as a live
readiness, deployment, or profitability claim.

The following vocabulary is forbidden anywhere in that future run's
receipt or any derived artifact:

- `PROFITABLE`
- `LIVE_READY`
- `DEPLOY_READY`
- `CLEAN_EDGE`
- `PRODUCTION_READY`

## 7. Acceptance gates for `OFFLINE_EDGE_CANDIDATE`

The future run may only emit `OFFLINE_EDGE_CANDIDATE` if **all** of the
following hold:

- data-quality preflight still passes against the current input
- no prod path is used for input or output
- no live/exchange imports are present anywhere in the executed code path
- no database is mutated
- position sizing is long-only / 1x only
- funding is either included in the cost model or explicitly accounted for
  and excluded with a stated reason
- transaction costs are included: commission, slippage, spread, funding
- sample size is sufficient:
  - at least 30 bars per included symbol, or stricter if a later, more
    detailed implementation plan specifies a stricter bound
  - at least 20 closed trades / candidate decisions, otherwise the run must
    emit `INCONCLUSIVE` rather than `OFFLINE_EDGE_CANDIDATE`
- net return after costs is `> 0`
- Sharpe or a comparable risk-adjusted metric is `> 0.5`
- max drawdown is recorded (no threshold implied beyond recording it)
- the result survives at least 2 of 3 defined cost-sensitivity cases
- a baseline comparison is included
- all artifacts are receipt-hashed
- no forbidden top-level keys from previous skeleton-phase receipts appear,
  unless intentionally introduced in the real validator together with
  schema documentation for the new key

If any gate is not met, the run must emit `NO_EDGE` or `INCONCLUSIVE` as
appropriate — never `OFFLINE_EDGE_CANDIDATE`.

## 8. Failure / refusal criteria

The future run must stop, or classify its result as blocked, if any of the
following occur:

- the input fingerprint differs unexpectedly from §2's recorded value
- data-quality readiness regresses relative to the §2 preflight
- funding coverage is missing where required
- module resolution is stale (e.g. a cached/old build of `quantbot` is
  imported)
- the output path is not under `/tmp`
- any path resolves under `/srv/qnty`
- any DB write, file write outside `/tmp`, or report-promotion path appears
- engine imports are broader than what this plan or its follow-on
  implementation plan explicitly scopes
- any live/exchange code appears on the executed path
- the sample is too small per §7's thresholds
- transaction costs are not included
- the baseline comparison is missing
- sensitivity cases are missing

In any of these cases the correct verdict is
`BLOCKED_BY_VALIDATION_IMPLEMENTATION` or
`BLOCKED_BY_DATA_QUALITY_REGRESSION`, not a partial or qualified
`OFFLINE_EDGE_CANDIDATE`.

## 9. Safe command shape

The CLI referenced below **may not exist yet**. This PR does not implement
it. The shape is documented only so a future implementation PR has a
concrete, safety-reviewed target to build toward — it is a placeholder,
not an instruction to run today:

```bash
PYTHONPATH="$SCRATCH" python -m quantbot.experiment.<FUTURE_OFFLINE_VALIDATION_CLI> \
  --read-only \
  --output-dir "/tmp/qnty_offline_edge_validation_${TS}" \
  --bars-dir "<SAFE_BARS_DIR>" \
  --funding-dir "<SAFE_FUNDING_DIR>" \
  --input-fingerprint "3dec994114769a16939afa9b0041a8162a308dcb05ca196557407b26a0d35b0d" \
  --cost-case "base"
```

Notes:

- `<FUTURE_OFFLINE_VALIDATION_CLI>` does not exist in `quantbot/` as of this
  PR. It must be implemented in a separate, later PR before this command
  can be run for real.
- `--read-only` and an `/tmp`-only `--output-dir` are non-negotiable parts
  of the shape, not optional flags.
- `--input-fingerprint` must match §2's recorded fingerprint, or the run
  must explicitly justify and record the mismatch per §8.

## 10. Next implementation slice

The recommended next code PR, after this docs-only plan, should scope
**only**:

- the real validation receipt schema (fields from §5, with types and
  required/optional status documented)
- no engine integration yet, unless a later plan explicitly scopes it
- a deterministic split builder using the already-ready data from §2
- the cost-case sensitivity matrix (§7's "2 of 3 cases" structure)
- output under `/tmp` only
- a verdict that remains `BLOCKED_BY_VALIDATION_IMPLEMENTATION` until the
  actual return/risk calculation exists — i.e. that PR should not attempt
  to emit `OFFLINE_EDGE_CANDIDATE` or `NO_EDGE` itself

## 11. Verification performed for this PR

- `git diff --check` — no whitespace errors.
- `git diff --name-only origin/main...HEAD` — docs-only change confirmed.
- Confirmed no code changes (no `quantbot/`, `tests/`, `scripts/`, or
  `ops/` changes).
- Confirmed no `/tmp` receipt committed.
- Confirmed no real CSVs committed.
- Confirmed no `CLAUDE.md` changes.
- Confirmed no stray `tmp/` files.

## 12. Verdict

`QNTY_OFFLINE_EDGE_VALIDATION_REAL_VALIDATION_EXECUTION_PLAN_RECORDED`

This PR records a plan only. `EDGE_UNPROVEN` and `BLOCK_LIVE_INTEGRATION`
remain active. No validation was run. No PnL was computed. No code was
changed. No report was promoted.
