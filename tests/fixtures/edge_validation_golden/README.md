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
to point to directories containing these files. The CLI will read the SHA256 of each
file as `input_manifest_fingerprint` in a future PR.