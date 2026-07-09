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