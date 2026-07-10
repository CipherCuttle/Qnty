# Edge Validation Golden Fixtures

This directory will contain golden fixture files for the offline edge-validation CLI tests.

## Purpose

In future PRs, this directory will hold:

- Sample bar data (CSV) for offline edge validation runs
- Sample funding rate data (CSV) for cost modeling
- Sample manifest files (JSON) with known SHA256 fingerprints
- Expected `validation_receipt.json` outputs for golden comparison tests

## Current Status (PR A — Skeleton)

This directory is **empty** in PR A. The skeleton tests in
[`tests/experiment/test_offline_edge_validation_cli.py`](tests/experiment/test_offline_edge_validation_cli.py) create
temporary fixture files at runtime and verify that the CLI does not mutate them.

## Future Use

When the edge validation pipeline is implemented (future PRs), running:

```bash
pytest tests/experiment/ --golden-dir tests/fixtures/edge_validation_golden/
```

will compare CLI output against golden receipts stored here.

## Naming Convention

| File | Purpose |
|------|---------|
| `sample_bars.csv` | OHLCV bar data for a single symbol |
| `sample_funding.csv` | Funding rate data |
| `sample_manifest.json` | Bar/funding manifest |
| `expected_receipt.json` | Expected validation receipt output |

## Integration Tests

The fixture-only CLI contract requires `--bars-dir`, `--funding-dir`, and `--manifest-dir`
to point to directories containing these files. The CLI computes the SHA256 of each
file as `input_manifest_fingerprint` in the receipt.

## PR B — Input Manifest Inventory

Added in PR B:

| File | Purpose |
|------|---------|
| [`sample_bars.csv`](sample_bars.csv) | Deterministic OHLCV bar data (3 rows) for fingerprint tests |
| [`sample_funding.csv`](sample_funding.csv) | Deterministic funding rate data (3 rows) for fingerprint tests |
| [`sample_manifest.json`](sample_manifest.json) | Sample manifest referencing the above CSVs |

These fixtures are consumed by:
- [`offline_edge_input_manifest.py`](../../../quantbot/experiment/offline_edge_input_manifest.py) — stdlib-only helpers for hashing and discovery
- [`test_offline_edge_input_manifest.py`](../../../tests/experiment/test_offline_edge_input_manifest.py) — unit tests for the manifest module
- [`test_offline_edge_validation_cli.py`](../../../tests/experiment/test_offline_edge_validation_cli.py) — integration tests verifying CLI reads fixture dirs and computes a real fingerprint

Known golden hashes (deterministic, verified in test):

```
sample_bars.csv    SHA256 = computed at test time against fixture
sample_funding.csv SHA256 = computed at test time against fixture
```

## PR C — Cost-Model Fixtures

Added in PR C:

| File | Purpose |
|------|---------|
| [`sample_cost_model.json`](sample_cost_model.json) | Fixture-only cost-model assumptions (commission/slippage/spread bps + funding placeholder) |

These document the deterministic assumptions consumed by:
- [`offline_edge_cost_model.py`](../../../quantbot/experiment/offline_edge_cost_model.py) — stdlib-only pure cost-math helpers
- [`test_offline_edge_cost_model.py`](../../../tests/experiment/test_offline_edge_cost_model.py) — unit tests for the cost-math helpers

**Scope note:** PR C is fixture-only cost math. It does **not** compute strategy
performance, does **not** apply costs to trades, does **not** call the paper engine,
and does **not** replay real funding. The CLI verdict remains `SKELETON_ONLY`.
`EDGE_UNPROVEN` / `BLOCK_LIVE_INTEGRATION` remain in force; long-only / 1x is the
only assumed lane.

## PR D — Volnorm Reconstruction Fixtures

Added in PR D:

| File | Purpose |
|------|---------|
| [`sample_volnorm_bars.csv`](sample_volnorm_bars.csv) | Deterministic OHLCV bars (6 rows, monotonic timestamps) for fixture-only volnorm reconstruction |
| [`expected_volnorm_weights.json`](expected_volnorm_weights.json) | Golden expected output of `reconstruct_fixture_volnorm_weights` over the above bars with default params |

These fixtures are consumed by:
- [`offline_edge_volnorm.py`](../../../quantbot/experiment/offline_edge_volnorm.py) — stdlib-only helpers that rebuild a V2-*style* inverse-vol, heat-capped weight from fixture bars
- [`test_offline_edge_volnorm.py`](../../../tests/experiment/test_offline_edge_volnorm.py) — unit tests for the reconstruction helpers
- [`test_offline_edge_validation_cli.py`](../../../tests/experiment/test_offline_edge_validation_cli.py) — CLI test exercising `--volnorm-bars`

**Scope note:** PR D is a *fixture-only mirror* of the V2 volnorm concept. It is
**not** full V2: it reconstructs a single-instrument realized-vol weight from
simple returns, not the multi-symbol portfolio-heat scaling in
[`volnorm_portfolio.py`](../../../quantbot/experiment/volnorm_portfolio.py). It
does **not** compute strategy performance / PnL, generate trades, call the paper
engine, replay real funding, run walk-forward, create Lane B, or emit
`EDGE_CANDIDATE`. The CLI verdict remains `SKELETON_ONLY`. `EDGE_UNPROVEN` /
`BLOCK_LIVE_INTEGRATION` remain in force; long-only / 1x is the only assumed lane.

## PR E — Walk-Forward Replay Fixtures

Added in PR E:

| File | Purpose |
|------|---------|
| [`sample_walkforward_bars.csv`](sample_walkforward_bars.csv) | Deterministic OHLCV bars (8 rows, monotonic timestamps) — enough for 5 tiny train/test splits at `train_size=3, test_size=1` |
| [`expected_walkforward_summary.json`](expected_walkforward_summary.json) | Golden expected top-level output of `run_fixture_walkforward` over the above bars with default params |

These fixtures are consumed by:
- [`offline_edge_walkforward.py`](../../../quantbot/experiment/offline_edge_walkforward.py) — stdlib-only helpers that split fixture bars, reconstruct a fixture volnorm weight per split, apply fixture cost assumptions, and emit a toy replay summary
- [`test_offline_edge_walkforward.py`](../../../tests/experiment/test_offline_edge_walkforward.py) — unit tests for the split/replay helpers
- [`test_offline_edge_validation_cli.py`](../../../tests/experiment/test_offline_edge_validation_cli.py) — CLI test exercising `--walkforward-bars` (emits stage-B metric)

**Scope note:** PR E is a *fixture-only mirror* of the walk-forward concept in
[`walkforward.py`](../../../quantbot/experiment/walkforward.py) /
[`walkforward_runner.py`](../../../quantbot/experiment/walkforward_runner.py). It
is **not** the real runner: those modules are intentionally not imported because
they drag strategy/loader/gate/engine dependencies. Per-split numbers are
labelled `fixture_counterfactual_return` and are **not** `pnl`, **not**
`strategy_performance`, **not** `sharpe`, and **not** `edge`. It does **not**
compute strategy PnL, generate trades, call the paper engine, replay real
funding, run a full historical walk-forward, create Lane B, or emit
`EDGE_CANDIDATE`. The CLI verdict remains `SKELETON_ONLY`. `EDGE_UNPROVEN` /
`BLOCK_LIVE_INTEGRATION` remain in force; long-only / 1x is the only assumed lane.

## PR I — Data-Quality Schema Profile Fixtures (Funding)

Added in PR I, alongside the existing `data_quality_*.csv` bars-shaped
fixtures from PR G:

| File | Purpose |
|------|---------|
| [`data_quality_funding_clean.csv`](data_quality_funding_clean.csv) | Clean Binance funding-rate CSV (`symbol,fundingTime,fundingRate,markPrice`), 5 rows, monotonic |
| [`data_quality_funding_duplicate_timestamp.csv`](data_quality_funding_duplicate_timestamp.csv) | Same schema with a duplicate `fundingTime` value |
| [`data_quality_funding_non_monotonic.csv`](data_quality_funding_non_monotonic.csv) | Same schema with an out-of-order `fundingTime` value |
| [`data_quality_funding_null_funding_rate.csv`](data_quality_funding_null_funding_rate.csv) | Same schema with a null `fundingRate` cell |
| [`data_quality_funding_missing_funding_time.csv`](data_quality_funding_missing_funding_time.csv) | Missing the `fundingTime` column entirely |

These are consumed by:
- [`offline_edge_data_quality.py`](../../../quantbot/experiment/offline_edge_data_quality.py) — `SCHEMA_PROFILES["funding"]` validates against `symbol`/`fundingTime`/`fundingRate` (not `timestamp`/`close`/`volume`), and `build_data_quality_preflight_for_roles` keeps bars/funding/manifest requirements from leaking across roles
- [`test_offline_edge_data_quality.py`](../../../tests/experiment/test_offline_edge_data_quality.py) — unit tests for the funding/manifest schema profiles and role-aware readiness
- [`test_offline_edge_validation_cli.py`](../../../tests/experiment/test_offline_edge_validation_cli.py) — CLI tests exercising `--bars-dir`/`--funding-dir`/`--manifest-dir` with the correct profile per role

**Scope note:** PR I only makes the existing read-only data-quality preflight
schema-aware. It does **not** compute strategy PnL, does **not** call the
paper engine, does **not** run walk-forward, does **not** create Lane B, and
does **not** emit `EDGE_CANDIDATE`. The CLI verdict remains `SKELETON_ONLY`.
`EDGE_UNPROVEN` / `BLOCK_LIVE_INTEGRATION` remain in force; long-only / 1x is
the only assumed lane.

## Real Validation Receipt Skeleton (no new fixtures added)

Added no new fixture files here. This slice implements
[`offline_edge_real_validation.py`](../../../quantbot/experiment/offline_edge_real_validation.py)
— the schema/skeleton for the first *real* offline validation receipt
described in
[QNTY_OFFLINE_EDGE_VALIDATION_REAL_VALIDATION_EXECUTION_PLAN.md](../../../docs/status/QNTY_OFFLINE_EDGE_VALIDATION_REAL_VALIDATION_EXECUTION_PLAN.md).
Its tests in
[`test_offline_edge_real_validation.py`](../../../tests/experiment/test_offline_edge_real_validation.py)
use inline fixture data (fingerprints, timestamps) rather than files in this
directory, since the split-builder and cost-case matrix are pure functions
over opaque strings, not real bar/funding data.

**Scope note:** this slice does **not** compute returns, PnL, Sharpe, or run
any engine, and does **not** emit `OFFLINE_EDGE_CANDIDATE` — every receipt it
builds is fixed to `final_offline_verdict: BLOCKED_BY_VALIDATION_IMPLEMENTATION`.
`EDGE_UNPROVEN` / `BLOCK_LIVE_INTEGRATION` remain in force.
