# QNTY_OFFLINE_EDGE_VALIDATION_IMPLEMENTATION_PLAN_SCOPING

**Status:** SCOPING_DOCUMENT (docs-only)
**Date:** 2026-07-09
**Author:** Architect workflow
**Parent plan:** [`docs/plans/QNTY_OFFLINE_EDGE_VALIDATION_PLAN_AFTER_CLEAN_CARRY.md`](docs/plans/QNTY_OFFLINE_EDGE_VALIDATION_PLAN_AFTER_CLEAN_CARRY.md)

---

## 0. Context Summary

### Current State

- **Prod clean-carry is SOLVED** — `CLEAN_NET_OF_CARRY` per verifier, confirmed by PR #132 execution + PR #133 post-merge audit (13/13 checks pass). See [`docs/status/qnty_prod_clean_carry_status_summary_after_report_promotion_2026-07-09.md`](docs/status/qnty_prod_clean_carry_status_summary_after_report_promotion_2026-07-09.md).
- **Edge remains `EDGE_UNPROVEN`** — No edge or profitability has been proven by the clean-carry promotion.
- **`BLOCK_LIVE_INTEGRATION` remains in effect** — No live trading, no exchange integration.
- **Long-only / 1x is the only assumed lane** — No 2x or shorting.
- **Prod forward lane (`paper_pnl_v1`) uses fixed-notional $1,000/symbol equal-weight** — This is a baseline/control lane, NOT V2 volnorm evidence.
- **V2 volnorm portfolio uses inverse-vol weighting with heat cap 1.0** — Validated historically but never run forward.
- **They are different portfolios** — Prod clean-carry is NOT evidence of V2 edge. The lane mismatch is documented in [`docs/experiments/QNTY_P0_BASELINE_CONTROL_DECISION_RECEIPT_2026-06-18.md`](docs/experiments/QNTY_P0_BASELINE_CONTROL_DECISION_RECEIPT_2026-06-18.md) and [`docs/experiments/QNTY_STRATEGY_VALIDITY_EVIDENCE_PACK_2026-06-18.md`](docs/experiments/QNTY_STRATEGY_VALIDITY_EVIDENCE_PACK_2026-06-18.md).

### Six-Stage Validation Pipeline (from parent plan)

| Stage | Purpose |
|---|---|
| A | Reconstruct V2 volnorm / heat-capped portfolio offline from bar CSVs |
| B | Apply realistic cost model (funding, spread, slippage, commission) |
| C | Walk-forward time split (split-only, no calibration) |
| D | Forward-window counterfactual replay — what V2 WOULD HAVE DONE vs `paper_pnl_v1` |
| E | Sensitivity analysis (regime breakdown, funding flip, slippage stress) |
| F | Verdict classification — `EDGE_CANDIDATE` / `NO_EDGE` / `INCONCLUSIVE` / `NEEDS_MORE_DATA` / `BLOCKED_BY_DATA_QUALITY` |

### Existing Code to Reuse

| Module | Key Functions/Classes | File |
|---|---|---|
| Volnorm portfolio | `VolatilityTracker`, `compute_vol_normed_weights()` | [`quantbot/experiment/volnorm_portfolio.py`](quantbot/experiment/volnorm_portfolio.py) |
| Walk-forward splits | `build_walkforward_splits()`, `WalkForwardSplit` | [`quantbot/experiment/walkforward.py`](quantbot/experiment/walkforward.py) |
| Walk-forward runner | `run_walkforward_experiment()` | [`quantbot/experiment/walkforward_runner.py`](quantbot/experiment/walkforward_runner.py) |
| Paper engine | `run_engine()`, `PriceBook`, `build_funding_index()`, fill model | [`quantbot/paper/engine.py`](quantbot/paper/engine.py) |
| Funding coverage | `check_funding_coverage()`, `check_funding_coverage_from_rows()`, fail-closed | [`quantbot/paper/funding_coverage.py`](quantbot/paper/funding_coverage.py) |
| Test fixtures | OHLCV CSVs with SHA256 manifests | [`tests/fixtures/`](tests/fixtures/) |

### Gaps

- No unified validation script exists
- No counterfactual replay logic (engine uses fixed-notional, not volnorm weights)
- No cost model per-symbol (spread data not formalized)
- Funding CSVs incomplete (SOLUSDT confirmed 0-row)
- Stale universe table (last populated 2025-10-01)
- No volnorm-to-engine bridge (no way to pass volnorm weights into `run_engine()`)
- No CLI contract defined
- Statistical gates not codified
- No cherry-picking prevention

### Guardrails

- `EDGE_UNPROVEN` remains until validation passes
- `BLOCK_LIVE_INTEGRATION` remains
- Long-only / 1x only
- `CLEAN_NET_OF_CARRY` ≠ edge/profit/live readiness
- No prod mutation, no DB writes, no CSV writes, no exchange keys, no live fetch

---

## 1. Executive Summary

This document is **implementation scoping only**. It defines what a future implementation PR would need to build, but:

- **No code is created in this PR.** This is a docs-only artifact.
- **No existing files are modified.**
- **No source code changes occur.**
- **No DB, CSV, or production data is touched.**

The scope is **offline validation only** — a standalone script that reads historical bar CSVs and funding CSVs, reconstructs the V2 volnorm portfolio, applies realistic costs, runs walk-forward analysis, performs counterfactual replay against the `paper_pnl_v1` baseline, runs sensitivity stress tests, and emits a verdict classification.

The following guardrails remain in full force and are not affected by this document:

| Guardrail | Status |
|---|---|
| `EDGE_UNPROVEN` | Remains until validation passes |
| `BLOCK_LIVE_INTEGRATION` | Remains |
| Long-only / 1x only | Remains |
| No prod mutation | Remains |
| No DB writes | Remains |
| No CSV writes | Remains |
| No exchange keys | Remains |
| No live fetch | Remains |

---

## 2. Proposed Future Module / File Surface

The following files **may be created** in a future implementation PR. They are listed here as aspirational targets only. **Do not create them now.**

| File | Purpose |
|---|---|
| `quantbot/experiment/offline_edge_validation.py` | Core orchestration — runs Stages A–F in sequence, produces validation receipt |
| `quantbot/experiment/offline_edge_validation_cli.py` | CLI entrypoint — argparse wrapper around the orchestration |
| `quantbot/experiment/offline_edge_schema.py` | Output schemas, typed dicts, dataclasses for validation receipt JSON |
| `quantbot/experiment/offline_cost_model.py` | Cost model helpers — per-symbol spread, slippage, commission, funding accrual |
| `tests/experiment/test_offline_edge_validation.py` | Unit tests for the orchestration logic |
| `tests/experiment/test_offline_cost_model.py` | Unit tests for the cost model |
| `tests/experiment/test_offline_edge_validation_cli.py` | CLI contract tests — flag parsing, fail-closed, prod-path rejection |
| `tests/fixtures/edge_validation_golden/` | Golden test data directory — recorded expected output for schema stability tests |
| `docs/plans/QNTY_OFFLINE_EDGE_VALIDATION_IMPLEMENTATION.md` | Future implementation doc — defines module structure, function signatures, implementation details |

---

## 3. Proposed CLI Shape

The future CLI entrypoint is defined here as a **contract specification**. It is not implemented yet.

### Invocation Shape

```bash
python -m quantbot.experiment.offline_edge_validation_cli \
  --bars-dir <path> \
  --funding-dir <path> \
  --manifest-dir <path> \
  --output-dir <path> \
  --start <YYYY-MM-DD> \
  --end <YYYY-MM-DD> \
  --baseline-paper-report <path> \
  --cost-profile baseline|stress_2x \
  --read-only
```

### Required Flags

| Flag | Type | Description |
|---|---|---|
| `--bars-dir` | `Path` | Directory containing OHLCV bar CSVs (one per symbol, e.g., `BTCUSDT_8h.csv`) |
| `--funding-dir` | `Path` | Directory containing funding rate CSVs (one per symbol) |
| `--manifest-dir` | `Path` | Directory containing SHA256 manifest JSON files for bar CSVs |
| `--output-dir` | `Path` | **Must be under `/tmp` or an explicit scratch directory.** Refuse paths under `/srv/qnty/`. |
| `--start` | `YYYY-MM-DD` | Start date for validation window (inclusive) |
| `--end` | `YYYY-MM-DD` | End date for validation window (inclusive) |
| `--read-only` | Flag | **Required.** Must be present. Script refuses to run without this flag. |

### Optional Flags

| Flag | Type | Description |
|---|---|---|
| `--baseline-paper-report` | `Path` | Path to a `paper_verify_report.json` from the prod `paper_pnl_v1` lane. Used for Stage D (counterfactual comparison). Optional — if absent, Stage D is skipped with a warning. |
| `--cost-profile` | `str` | One of `baseline` (default) or `stress_2x`. `stress_2x` doubles slippage and spread assumptions for sensitivity testing (Stage E). |

### Forbidden Flags

The following flags **must not exist** in the CLI:

- `--write` — No writer mode
- `--live` — No live mode
- `--deploy` — No deploy mode
- `--promote` — No promotion mode

### Fail-Closed Behavior

| Condition | Behavior |
|---|---|
| `--read-only` flag absent | Abort with error: `--read-only is required. Refusing to run without explicit read-only confirmation.` |
| `--output-dir` under `/srv/qnty/` | Abort with error: `--output-dir must be under /tmp or an explicit scratch directory. Refusing prod path: <path>` |
| Missing `--bars-dir` | Abort with error |
| Missing `--funding-dir` | Abort with error |
| Missing `--manifest-dir` | Abort with error |
| Missing `--start` or `--end` | Abort with error |
| `--bars-dir` does not exist | Abort with error: `Bars directory not found: <path>` |
| `--funding-dir` does not exist | Abort with error |
| `--manifest-dir` does not exist | Abort with error |
| `--start` > `--end` | Abort with error: `Start date must be before or equal to end date.` |
| `--cost-profile` is not `baseline` or `stress_2x` | Abort with error: `Invalid cost profile: <value>. Must be 'baseline' or 'stress_2x'.` |

---

## 4. Future Output Schema

The validation script will produce a single JSON receipt file. The schema is defined here as a specification.

### Top-Level Structure

```json
{
  "validation_receipt": { ... },
  "input_manifest_fingerprint": "sha256hex...",
  "cost_model_assumptions": { ... },
  "per_stage_metrics": {
    "stage_a": { ... },
    "stage_b": { ... },
    "stage_c": { ... },
    "stage_d": { ... },
    "stage_e": { ... },
    "stage_f": { ... }
  },
  "final_verdict": "EDGE_CANDIDATE | NO_EDGE | INCONCLUSIVE | NEEDS_MORE_DATA | BLOCKED_BY_DATA_QUALITY"
}
```

### `validation_receipt`

| Key | Type | Description |
|---|---|---|
| `tool_name` | `str` | `"offline_edge_validation"` |
| `tool_version` | `str` | Semver from `quantbot.version` |
| `generated_at` | `str` | ISO 8601 UTC timestamp |
| `cli_args` | `dict` | Sanitized copy of CLI arguments (passwords/full paths excluded) |
| `git_sha` | `str` | Commit hash at runtime (via `git rev-parse HEAD`) |
| `dirty_repo` | `bool` | Whether git working tree was dirty at runtime |
| `bar_count_total` | `int` | Total bars loaded across all symbols |
| `symbols_used` | `list[str]` | Symbols that actually entered the analysis |
| `symbols_dropped` | `list[str]` | Symbols dropped due to data quality or missing funding |

### `input_manifest_fingerprint`

A single SHA256 hex digest computed over the **concatenation** of:
- SHA256 of each bar CSV used (in sorted symbol order)
- SHA256 of each funding CSV used (in sorted symbol order)
- SHA256 of the CLI config (normalized JSON of all arguments)
- SHA256 of the cost-profile parameterization used

This ensures reproducibility: same inputs + same config = same fingerprint.

### `cost_model_assumptions`

| Key | Type | Description |
|---|---|---|
| `cost_profile` | `str` | `"baseline"` or `"stress_2x"` |
| `slippage_bps_per_side` | `float` | Baseline: `5.0`; stress: `10.0` |
| `commission_bps_per_side` | `float` | `5.0` (flat, unchanged in stress) |
| `spread_bps_per_side` | `dict[str, float]` | Per-symbol spread assumption in bps |
| `funding_sourced` | `list[str]` | Symbols for which funding data was available |
| `funding_missing` | `list[str]` | Symbols for which funding data was missing (causing drop or `BLOCKED_BY_DATA_QUALITY`) |
| `vol_lookback_bars` | `int` | `90` (from `quantbot/experiment/volnorm_portfolio.py`) |
| `heat_cap` | `float` | `1.0` (from `quantbot/experiment/volnorm_portfolio.py`) |

### `per_stage_metrics`

Each stage key maps to a dict. The required sub-keys per stage:

**Stage A (Reconstruction)**

| Key | Type | Description |
|---|---|---|
| `status` | `str` | `"passed"` / `"failed"` / `"blocked"` |
| `total_bars_reconstructed` | `int` | Total bars across all symbols after volnorm weighting |
| `symbols_in_portfolio` | `int` | Number of symbols that entered the portfolio |
| `mean_weight` | `float` | Mean vol-normalized weight across all bars/symbols |
| `heat_utilization` | `float` | Mean fraction of heat cap consumed across all bars |

**Stage B (Cost Model)**

| Key | Type | Description |
|---|---|---|
| `status` | `str` | `"passed"` / `"failed"` / `"blocked"` |
| `total_costs` | `dict[str, float]` | Breakdown by cost type: `funding`, `spread`, `slippage`, `commission` |
| `funding_data_gaps` | `list[str]` | Symbols with missing funding data in any bar of the window |
| `funding_coverage_pct` | `float` | Percentage of required funding windows that had data |

**Stage C (Walk-Forward Split)**

| Key | Type | Description |
|---|---|---|
| `status` | `str` | `"passed"` / `"failed"` / `"blocked"` |
| `num_splits` | `int` | Number of walk-forward splits generated |
| `train_window_bars` | `int` | Training window size in bars |
| `test_window_bars` | `int` | Test window size in bars |
| `coverage_days` | `int` | Total calendar days covered by all test windows |

**Stage D (Counterfactual Replay)**

| Key | Type | Description |
|---|---|---|
| `status` | `str` | `"passed"` / `"failed"` / `"blocked"` / `"skipped_no_baseline"` |
| `v2_net_return_pct` | `float` | V2 volnorm portfolio net return over the forward window |
| `baseline_net_return_pct` | `float` | `paper_pnl_v1` net return over the same period (from supplied baseline report, or `null` if absent) |
| `v2_vs_baseline_delta` | `float` | Difference (V2 - baseline) in net return pct |
| `v2_sharpe` | `float` | Annualized Sharpe for V2 over forward window |
| `baseline_sharpe` | `float` | Annualized Sharpe for baseline over forward window (or `null`) |
| `v2_max_drawdown` | `float` | Max drawdown for V2 over forward window |
| `baseline_max_drawdown` | `float` | Max drawdown for baseline (or `null`) |
| `outperform_baseline` | `bool` | Whether V2 beats baseline on at least 2 of 3: net return, Sharpe, max drawdown |

**Stage E (Sensitivity Analysis)**

| Key | Type | Description |
|---|---|---|
| `status` | `str` | `"passed"` / `"failed"` / `"blocked"` |
| `regime_breakdown` | `dict` | Performance bucketed by regime class (trending / choppy / etc.) |
| `funding_flip_scenarios` | `dict` | Net return under positive-only vs negative-only vs actual funding |
| `slippage_stress` | `dict[str, float]` | Net return at 5bps, 10bps, 20bps slippage |
| `passes_stress_gate` | `bool` | Whether net return stays positive at 2x slippage (10bps) |

**Stage F (Verdict Classification)**

| Key | Type | Description |
|---|---|---|
| `status` | `str` | `"passed"` / `"failed"` / `"blocked"` |
| `verdict` | `str` | One of the five verdict types |
| `gates_used` | `dict[str, bool]` | Each statistical gate and whether it passed |
| `reasoning` | `str` | Human-readable explanation of verdict |

### Edge Case: Data Quality Blocks a Stage

If a stage cannot proceed due to data quality, the following structure should be emitted:

```json
{
  "stage_a": {
    "status": "blocked",
    "blocked_by": "missing_manifest",
    "blocked_detail": "No manifest file found for SOLUSDT in manifests/",
    "blocked_at": "2026-07-09T22:40:00Z",
    "metrics": {}
  }
}
```

This causes the entire validation to short-circuit to `BLOCKED_BY_DATA_QUALITY`.

---

## 5. Stage-by-Stage Implementation Scope

### Stage A — Reconstruct V2 Volnorm / Heat-Capped Portfolio Offline

**Inputs:**
- Bar CSVs from `--bars-dir` (one per symbol, e.g., `BTCUSDT_8h.csv`)
- Manifest JSONs from `--manifest-dir` (SHA256 hashes for each CSV)
- Parameters: `VOL_LOOKBACK_BARS=90`, `HEAT_CAP=1.0`, `VOL_FLOOR=1e-6` from [`quantbot/experiment/volnorm_portfolio.py:26`](quantbot/experiment/volnorm_portfolio.py:26)

**Outputs:**
- Per-bar V2 volnorm portfolio weights (inverse-vol weighted, heat-capped)
- Per-bar equity path for the reconstructed portfolio
- Symbol-level volatility series

**Existing code to reuse:**
- [`quantbot/experiment/volnorm_portfolio.py:43`](quantbot/experiment/volnorm_portfolio.py:43) `VolatilityTracker` — rolling volatility estimation
- [`quantbot/experiment/volnorm_portfolio.py:90`](quantbot/experiment/volnorm_portfolio.py:90) `compute_vol_normed_weights()` — weight computation
- [`quantbot/data/loaders.py`](quantbot/data/loaders.py) `load_bars_from_csv()` — bar CSV loading (indirect, via existing test imports)
- SHA256 manifest verifier pattern from [`tests/test_manifest_verifier.py`](tests/test_manifest_verifier.py)

**New code needed:**
- Manifest hash verification against each CSV before loading
- Multi-symbol bar loader that loads and aligns all CSVs by timestamp
- Per-symbol `VolatilityTracker` initialization and update loop
- Weight computation at each bar
- Portfolio equity accumulator (notional = weight * total_equity)

**Tests needed:**
- Deterministic volnorm reconstruction: known bar CSV series → known weights
- Manifest hash verification: correct match passes, incorrect match fails
- Empty CSV: stage blocked
- Single-symbol reconstruction matches manual calculation
- Multi-symbol reconstruction sum of weights = 1.0 (subject to heat cap)

**Failure modes:**
- Missing CSV for a symbol in manifest → stage blocked per symbol
- Manifest hash mismatch → abort entire validation
- Zero-row CSV after verification → stage blocked per symbol
- Single symbol cannot compute vol (insufficient bars for lookback) → use vol floor, emit warning

---

### Stage B — Apply Realistic Cost Model

**Inputs:**
- V2 portfolio weights and equity path from Stage A
- Funding CSVs from `--funding-dir`
- Cost profile (`baseline` or `stress_2x`) from `--cost-profile`

**Outputs:**
- Per-bar cost breakdown (funding, spread, slippage, commission)
- Net-of-costs equity path

**Existing code to reuse:**
- [`quantbot/paper/funding_coverage.py:90`](quantbot/paper/funding_coverage.py:90) `check_funding_coverage()` — fail-closed gate for missing funding
- [`quantbot/paper/engine.py:90`](quantbot/paper/engine.py:90) `build_funding_index()` — build per-symbol sorted funding rate index
- [`quantbot/paper/engine.py`](quantbot/paper/engine.py) funding accrual logic (inline at lines ~200-250; needs extraction)

**New code needed:**
- `offline_cost_model.py` module with:
  - Per-symbol spread model (default assumptions: 2-5 bps per major symbol, 10-20 bps for altcoins)
  - Slippage function: `slippage_cost(notional, bps_per_side)` — applies to fill notional
  - Commission function: `commission_cost(notional, bps_per_side=5.0)`
  - Funding accrural: port the engine's funding logic to work on volnorm-weighted positions
  - `apply_costs()` — takes Stage A output + cost parameters → net equity path

**Tests needed:**
- Cost model math: known trades + known costs → known net PnL
- Funding accrual: known funding rate series → known accrued cost for a position
- Spread cost: known fill notional + bps → known cost
- Slippage stress: baseline vs 2x vs 4x produces expected scaling
- Commission: flat 5bps applied correctly

**Failure modes:**
- Missing funding data for a symbol over required period → `BLOCKED_BY_DATA_QUALITY` (using existing `check_funding_coverage()` gate)
- Zero-row funding CSV → flagged, stage blocked per symbol
- Negative funding rates exceed model bounds → compute anyway, flag in sensitivity

---

### Stage C — Walk-Forward Time Split

**Inputs:**
- Net-of-cost equity path from Stage B
- Parameters: train window size, test window size, step size

**Outputs:**
- List of `WalkForwardSplit` objects (train/test index ranges)
- Per-split performance metrics (net return, Sharpe, max drawdown)
- Summary across all splits

**Existing code to reuse:**
- [`quantbot/experiment/walkforward.py:28`](quantbot/experiment/walkforward.py:28) `build_walkforward_splits()` — split builder
- [`quantbot/experiment/walkforward.py:12`](quantbot/experiment/walkforward.py:12) `WalkForwardSplit` dataclass
- [`quantbot/experiment/walkforward_runner.py:47`](quantbot/experiment/walkforward_runner.py:47) `run_walkforward_experiment()` — runner (may need adaptation for volnorm input)

**New code needed:**
- Walk-forward metrics accumulator: compute per-split performance from equity path
- Split continuity check: ensure splits cover the full time range without gaps
- Summary aggregator: mean and std dev across all splits

**Tests needed:**
- Walk-forward split generation matches expected split counts for known bar count
- Per-split metric computation matches manual calculation
- Empty data → empty splits
- Insufficient bars for even one split → empty result, warning emitted

**Failure modes:**
- Fewer than 30 forward equity bars → `INCONCLUSIVE` per minimum observation criterion
- Insufficient bars to form any split → stage blocked

---

### Stage D — Forward-Window Counterfactual Replay

**Inputs:**
- V2 volnorm portfolio equity path (from Stage A + B)
- `paper_pnl_v1` baseline report (from `--baseline-paper-report`, optional)
- The forward window (bars after the walk-forward end)

**Outputs:**
- V2 counterfactual equity path over the forward window
- Comparison table: V2 vs `paper_pnl_v1` on net return, Sharpe, max drawdown
- Delta analysis: what V2 WOULD HAVE DONE vs what `paper_pnl_v1` actually did

**Existing code to reuse:**
- [`quantbot/paper/engine.py`](quantbot/paper/engine.py) — can be adapted to use volnorm weights instead of fixed-notional (the engine's fill model and funding accrual are reusable; only position sizing changes)
- [`docs/paper_pnl_v1_schema.md`](docs/paper_pnl_v1_schema.md) — baseline report schema for parsing

**New code needed:**
- **Volnorm-to-engine bridge:** A function that takes volnorm weights and produces per-symbol notional allocations compatible with the engine's `active_symbols` and `entries`/`exits` logic
- Baseline report parser: extract net return, Sharpe, max drawdown from `paper_verify_report.json`
- Comparison function: compute delta metrics and determine which portfolio outperforms

**Tests needed:**
- Counterfactual replay with known inputs matches expected output
- Baseline parser: known report JSON → correct metric extraction
- Volnorm-to-engine bridge: known weights → correct notional allocations
- No baseline report supplied → stage yields `skipped_no_baseline` status

**Failure modes:**
- No baseline report supplied → `skipped_no_baseline`, no comparison available
- Baseline report format mismatch → graceful error, stage partially blocked
- Fewer than 30 forward equity bars for V2 counterfactual → `INCONCLUSIVE`
- Fewer than 20 closed trades in forward window → `INCONCLUSIVE`

---

### Stage E — Sensitivity Analysis

**Inputs:**
- V2 portfolio equity path from Stage A (pre-cost)
- Net-of-cost equity path from Stage B
- Funding rate series from Stage B
- Regime classification (optional, from existing `regime.py` or from simple vol-based classification)

**Outputs:**
- Regime-breakdown table: net return during trending periods vs choppy periods
- Funding-flip scenarios: net return under (a) actual funding, (b) all funding rates set to zero, (c) all funding rates doubled
- Slippage stress: net return at 5bps, 10bps, 20bps
- Stress gate result: does net return stay positive at 2x slippage?

**Existing code to reuse:**
- [`quantbot/experiment/regime.py`](quantbot/experiment/regime.py) — regime classification (if applicable)
- Cost model from Stage B — reuse for stress scenarios

**New code needed:**
- Regime breakdown bucketing: slice equity path by regime type and compute per-regime metrics
- Funding flip replayer: re-run cost model with modified funding rates
- Slippage stress replayer: re-run cost model with higher slippage assumptions
- Stress gate evaluator: passes if net return > 0 at 2x slippage

**Tests needed:**
- Regime breakdown: known regime periods → correct per-regime metrics
- Funding flip: known funding series → correct recomputed costs
- Slippage stress: doubling slippage ≈ doubles slippage cost (within rounding)
- Stress gate: positive baseline → gate passes at 2x

**Failure modes:**
- Insufficient data for meaningful regime breakdown → `INCONCLUSIVE`
- Funding data gaps prevent flip analysis → partial results, warning
- Slippage stress at 20bps kills all returns → gate fails, `NO_EDGE` possible

---

### Stage F — Verdict Classification

**Inputs:**
- All stage outputs (A–E)

**Outputs:**
- Final verdict: one of `EDGE_CANDIDATE` / `NO_EDGE` / `INCONCLUSIVE` / `NEEDS_MORE_DATA` / `BLOCKED_BY_DATA_QUALITY`
- Gate-by-gate pass/fail matrix
- Human-readable reasoning

**Existing code to reuse:**
- [`quantbot/experiment/gates.py`](quantbot/experiment/gates.py) — existing gate infrastructure for reference pattern

**New code needed:**
- Verdict classification function with hardcoded gate thresholds (from parent plan §6):
  - Net return after costs > 0
  - Annualized Sharpe > 0.5
  - Max drawdown within acceptable bounds
  - Passes 2x slippage stress
  - Outperforms baseline on at least 2 of 3 metrics (if baseline available)
  - Minimum 30 forward equity bars
  - Minimum 20 closed trades
- Cherry-picking prevention check: report all symbols, all regimes, all splits
- Gate matrix builder: one row per gate, one column per stage

**Tests needed:**
- `EDGE_CANDIDATE` classification for known-positive fixture
- `NO_EDGE` classification for known-negative fixture
- `INCONCLUSIVE` for small-sample fixture
- `NEEDS_MORE_DATA` for fixture with funding gaps
- `BLOCKED_BY_DATA_QUALITY` for fixture with manifest mismatch
- All five verdict routes produce correct verdict strings

**Failure modes:**
- All classification gates are hardcoded; no tunable parameters
- Ambiguous results (e.g., passes net return but fails Sharpe) → `INCONCLUSIVE`
- Missing data from earlier stages → verdict degrades gracefully: `INCONCLUSIVE` or `NEEDS_MORE_DATA`

---

## 6. Data-Quality Gates

All gates are **fail-closed**: the validation will not silently proceed with compromised data.

| Condition | Behavior | Verdict Impact |
|---|---|---|
| **Missing CSV** | Stage blocked per symbol. Symbol is dropped from analysis. If all symbols dropped, full validation stops. | `BLOCKED_BY_DATA_QUALITY` if critical symbols dropped |
| **Zero-row CSV** | Flagged. Stage blocked per symbol. Symbol dropped. | `BLOCKED_BY_DATA_QUALITY` if symbol was expected to be in portfolio |
| **Manifest hash mismatch** | **Full abort.** No stage proceeds. Error message includes which file and expected vs actual hash. | `BLOCKED_BY_DATA_QUALITY` |
| **Missing funding coverage** | Uses [`quantbot/paper/funding_coverage.py`](quantbot/paper/funding_coverage.py) `check_funding_coverage()` gate. Symbol with missing funding for any required window is dropped. If too many symbols dropped, validation cannot proceed. | `BLOCKED_BY_DATA_QUALITY` |
| **Stale universe table** | Warning flag in output receipt. Universe table last populated ~2025-10-01. Not a blocker for offline analysis (symbols are supplied via CSVs, not universe table), but flagged. | Warning only |
| **Time-window mismatch** | Requested range vs available data. If requested range partially available: clamp to available, emit warning. If requested range entirely outside available data: abort. | Warning or `BLOCKED_BY_DATA_QUALITY` if empty |
| **Duplicate timestamps** | Rejected per bar series. Any symbol with duplicate timestamps is dropped for that stage. | `BLOCKED_BY_DATA_QUALITY` per symbol |
| **Non-monotonic timestamps** | Rejected per bar series. Any symbol with out-of-order timestamps is dropped. | `BLOCKED_BY_DATA_QUALITY` per symbol |
| **Null/NaN OHLCV values** | Rejected per bar per symbol. Bars with any null/NaN OHLCV field are dropped (not interpolated). If too many bars dropped, symbol is dropped. | `BLOCKED_BY_DATA_QUALITY` per symbol |
| **Insufficient forward bars** | For Stage D / Stage F: fewer than 30 equity bars in forward window → `INCONCLUSIVE`. Fewer than 20 closed trades → `INCONCLUSIVE`. | `INCONCLUSIVE` |

---

## 7. Test Plan

### Unit Tests

| Test | File | What It Verifies |
|---|---|---|
| Deterministic volnorm reconstruction | `tests/experiment/test_offline_cost_model.py` | Known bar CSV series → known volnorm weights (pre-computed in test) |
| Cost model math | `tests/experiment/test_offline_cost_model.py` | Known trade + known costs → computed cost matches expected |
| Manifest hash validation | `tests/experiment/test_offline_edge_validation.py` | Correct SHA256 match passes; incorrect match fails |
| Funding accrual | `tests/experiment/test_offline_cost_model.py` | Known funding rate series + known position → correct accrued funding cost |
| Commission calculation | `tests/experiment/test_offline_cost_model.py` | Known notional + known bps → correct commission |
| Slippage calculation | `tests/experiment/test_offline_cost_model.py` | Known notional + known bps → correct slippage cost |

### Integration Tests

| Test | File | What It Verifies |
|---|---|---|
| Fail-closed missing funding | `tests/experiment/test_offline_edge_validation.py` | Missing funding CSV → `BLOCKED_BY_DATA_QUALITY` verdict |
| No-mutation proof | `tests/experiment/test_offline_edge_validation.py` | Run validation on fixture dir, then check SHA256 hashes of all input files are unchanged |
| Full pipeline smoke | `tests/experiment/test_offline_edge_validation.py` | Run Stages A–F on smallest viable fixture set, verify all stages produce output |

### Golden Tests

| Test | File | What It Verifies |
|---|---|---|
| Output schema stability | `tests/experiment/test_offline_edge_validation.py` | Run on golden fixture set → compare output JSON against recorded golden output in `tests/fixtures/edge_validation_golden/` |
| Golden fixture creation | `tests/experiment/test_offline_edge_validation.py` | Script to create/update golden output when fixture data changes (requires manual review) |

### CLI Contract Tests

| Test | File | What It Verifies |
|---|---|---|
| Refuses prod lane output | `tests/experiment/test_offline_edge_validation_cli.py` | `--output-dir /srv/qnty/output/paper_pnl_v1` → exit code > 0, error message |
| Refuses prod paths for bars | `tests/experiment/test_offline_edge_validation_cli.py` | `--bars-dir /srv/qnty/...` → allowed (read-only), but output-dir check is the critical one |
| Requires `--read-only` | `tests/experiment/test_offline_edge_validation_cli.py` | Missing `--read-only` → exit code > 0 |
| Missing required flags | `tests/experiment/test_offline_edge_validation_cli.py` | Each missing required flag → appropriate error |
| Invalid date range | `tests/experiment/test_offline_edge_validation_cli.py` | `--start > --end` → error |
| Invalid cost profile | `tests/experiment/test_offline_edge_validation_cli.py` | `--cost-profile invalid` → error |

### Verdict Classification Threshold Tests

| Test | File | What It Verifies |
|---|---|---|
| `EDGE_CANDIDATE` classification | `tests/experiment/test_offline_edge_validation.py` | Construct fixture data that clearly meets all gates → verdict is `EDGE_CANDIDATE` |
| `NO_EDGE` classification | `tests/experiment/test_offline_edge_validation.py` | Construct fixture data that clearly fails all gates → verdict is `NO_EDGE` |
| `INCONCLUSIVE` classification | `tests/experiment/test_offline_edge_validation.py` | Construct fixture with small sample → verdict is `INCONCLUSIVE` |
| `NEEDS_MORE_DATA` classification | `tests/experiment/test_offline_edge_validation.py` | Construct fixture with funding gaps → verdict is `NEEDS_MORE_DATA` |
| `BLOCKED_BY_DATA_QUALITY` | `tests/experiment/test_offline_edge_validation.py` | Construct fixture with manifest mismatch → verdict is `BLOCKED_BY_DATA_QUALITY` |

---

## 8. Safety / Anti-Footgun Requirements

| Requirement | Implementation |
|---|---|
| **Default output under `/tmp`** | If `--output-dir` is not explicitly provided, default to `/tmp/qnty_edge_validation/` (with a timestamp suffix) |
| **Refuse `/srv/qnty/output/paper_pnl_v1`** | Explicit path check: if `--output-dir` resolves under `/srv/qnty/`, abort |
| **Refuse official report paths** | Same path check catches all `/srv/qnty/` paths |
| **Read-only input handles** | All input files opened with read-only mode (`open(path, 'r')` or `pathlib.Path(path).read_bytes()`). Never open input files for writing |
| **No writer mode** | The CLI has no `--write` flag. Output is JSON receipt only |
| **No live fetch** | No network calls, no exchange API calls, no data-refresh triggering |
| **No service/timer mutation** | No systemd service or timer changes |
| **No exchange keys** | No API key loading, no exchange configuration |
| **No database writes** | No SQLite connections, no DB mutations |
| **No CSV writes** | Only JSON receipt and terminal output. Input CSVs are never modified |
| **Read-only flag required** | `--read-only` flag must be present. Script refuses to run without it |
| **Output path must be explicit scratch** | `--output-dir` must resolve under `/tmp` or an explicit `/scratch` / `$SCRATCH`; if it resolves under `/srv/qnty/`, abort |

---

## 9. Acceptance Gates for Future Implementation PR

The eventual implementation PR must prove the following before merging:

| Gate | Verification Method |
|---|---|
| **All tests passing** | `pytest tests/experiment/test_offline_edge_validation*.py tests/experiment/test_offline_cost_model*.py -x --tb=short` — exit code 0 |
| **Sample fixture run deterministic** | Run CLI on `tests/fixtures/` with known start/end → output JSON receipt. Run twice: same input → same SHA256 output receipt |
| **Schema validation** | Output JSON conforms to the schema defined in Section 4 above |
| **No-mutation proof** | Compute SHA256 of all input CSVs before and after validation run. Hashes must be identical |
| **Deterministic replay** | Same inputs + same CLI args → same output receipt hash (confirmed by `sha256sum` on output) |
| **Clear verdict on fixture cases** | Known-edge fixture → `EDGE_CANDIDATE`. Known-no-edge fixture → `NO_EDGE`. Known-blocked fixture (missing manifest) → `BLOCKED_BY_DATA_QUALITY` |
| **No prod path access** | `--output-dir /srv/qnty/output/paper_pnl_v1` → CLI exits with error. Exit code > 0 |

---

## 10. Non-Goals

The following are explicitly excluded from this document and from any implementation PR derived from it:

| Non-Goal | Rationale |
|---|---|
| ❌ No implementation in this PR | This is a docs-only scoping document |
| ❌ No live / shadow deployment | `BLOCK_LIVE_INTEGRATION` remains |
| ❌ No Lane B creation | Lane B is a conceptual marker only |
| ❌ No exchange integration | No exchange keys, connectors, or orders |
| ❌ No report promotion | No promotion to official paths |
| ❌ No edge claim | `EDGE_UNPROVEN` remains |
| ❌ No 2x / shorting | Long-only / 1x only |
| ❌ No service / timer / systemd changes | No system mutation |
| ❌ No DB mutation | No SQLite reads or writes |
| ❌ No CSV mutation | Input CSVs are read-only |
| ❌ No snapshot / bundle / report write | Only JSON receipt and terminal output |
| ❌ No source code changes to existing `.py` files | Only new files may be created in implementation |
| ❌ No data refresh or fetch | Offline only — no live data |

---

## 11. Recommended Next Task

**`QNTY_OFFLINE_EDGE_VALIDATION_SCOPING_REVIEW_OR_IMPLEMENTATION_SKELETON_PLAN`**

Two possible paths:

### Path A: Review (if concerns found)
If this scoping document reveals ambiguities, missing details, or methodological concerns, produce a review document that:
1. Identifies each concern with specific section references
2. Proposes resolutions or alternative approaches
3. Recommends whether to proceed with implementation or revise the approach

### Path B: Implementation Skeleton Plan (if scoping is sound)
If this scoping document is accepted as-is, produce a skeleton implementation plan (`docs/plans/QNTY_OFFLINE_EDGE_VALIDATION_IMPLEMENTATION.md`) that:
1. Defines the exact module structure and file layout for each proposed file
2. Specifies function signatures (name, args, return types) for all public functions
3. Defines the `ArgParse` CLI structure with flag specifications
4. Specifies all dataclass/schema types for the output JSON
5. Defines test class structure for each test file
6. Still does **not implement any function bodies** — skeleton only

This skeleton plan would then be handed to a Code mode task for implementation.

---

## Guardrails Compliance

| Guardrail | Status |
|---|---|
| Docs-only | ✅ Yes |
| Plan only (no implementation) | ✅ Yes |
| No source code changes to existing `.py` files | ✅ Yes |
| No prod mutation | ✅ Yes |
| No DB mutation | ✅ Yes |
| No CSV mutation | ✅ Yes |
| No snapshot / bundle / report write | ✅ Yes |
| No writer / trader / live / backfill / data-refresh | ✅ Yes |
| No service / timer / cron / systemd mutation | ✅ Yes |
| No deploy | ✅ Yes |
| No exchange keys | ✅ Yes |
| No exchange connector integration | ✅ Yes |
| No live integration | ✅ Yes |
| No report promotion | ✅ Yes |
| No 2x / shorting approval | ✅ Yes |
| Long-only / 1x remains only assumed lane | ✅ Yes |
| `EDGE_UNPROVEN` remains | ✅ Yes |
| `BLOCK_LIVE_INTEGRATION` remains | ✅ Yes |