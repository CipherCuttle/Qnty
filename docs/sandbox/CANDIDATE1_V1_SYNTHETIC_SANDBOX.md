# Candidate 1 V1 synthetic sandbox

## Purpose

This is an isolated, standard-library-only software-path harness for
exploratory synthetic strategy mechanics. Its scenario magnitudes are declared
arbitrary assumptions for path coverage, not estimates of cryptocurrency
behaviour.

Synthetic success is not evidence of market edge. Synthetic failure may reveal
software or mechanism weaknesses. No variant is automatically promoted. All
explored variants remain represented in each run receipt.

## Boundaries and commands

The harness generates all observations internally. It accepts only a declarative
variant JSON bundle and writes one new receipt. It has no real-data, database,
network, artifact-store, timestamp, or arbitrary-series interface.

```bash
.venv/bin/python -m quantbot.sandbox.candidate1_v1_cli list-rules
.venv/bin/python -m quantbot.sandbox.candidate1_v1_cli list-scenarios
.venv/bin/python -m quantbot.sandbox.candidate1_v1_cli run --variants docs/sandbox/example_candidate1_v1_variants.json --out /existing/workspace/receipt.json
.venv/bin/python -m quantbot.sandbox.candidate1_v1_cli verify --receipt /existing/workspace/receipt.json
```

The output path must be new and its parent must already exist. Receipts are
exploratory workspace outputs, not QNTY artifacts and never `VERIFIED_AVAILABLE`.

## Variant schema and rules

The top-level keys are `bundle_id`, `bundle_kind`, `schema_version`, and
`variants`. Every variant has `variant_id`, `rule_kind`, `parameters`,
`rationale_kind`, and `rationale`; `GENERIC_STYLIZED_FACT` additionally requires
`source_reference`. IDs and keys are unique and strict. Decimal parameters are
strings, not JSON numbers.

The exact rule registry is `ALWAYS_FLAT`, `ALWAYS_LONG`, `ALWAYS_SHORT`,
`LAGGED_RETURN_SIGN`, `LAGGED_RETURN_FADE`, and `FUNDING_SIGN_FADE`. Decisions
use only observations strictly before the evaluated interval. No callbacks,
expressions, plugins, or user code are accepted.

## Fixed scenario registry

`FLAT_ZERO_FUNDING`, `UPTREND_ZERO_FUNDING`, `DOWNTREND_ZERO_FUNDING`,
`ALTERNATING_REVERSAL_ZERO_FUNDING`, `FLAT_POSITIVE_FUNDING`,
`FLAT_NEGATIVE_FUNDING`, and `TREND_WITH_OPPOSING_FUNDING` are fixed and ordered.

## Receipts and replay

Receipts contain the raw input digest, canonical bundle, contract fingerprints,
every variant/scenario mechanical result, safety invariants, and a
`run_fingerprint`. Verification requires canonical bytes and replays every
result. Results are sorted only by `variant_id`, then `scenario_id`; there is no
ranking, winner, recommendation, selection, or scientific metric.

To create a new batch, copy the example, change only declarative variants,
provide an explicit rationale for each, and run into a new existing workspace
directory. Repeat the run and compare bytes before verification.

## Interpretation and prohibitions

The accounting fields describe mechanical slot, component, turnover, and fixed
arbitrary transaction-cost paths. They cannot establish scientific validity,
market edge, profitability, expected live performance, or a strategy choice.
Real data selection and execution remain forbidden. Candidate 1 V0 remains
unavailable; the official V1 protocol does not exist; no paper/live authority or
sandbox execution budget is granted; `EDGE_UNPROVEN` and
`BLOCK_LIVE_INTEGRATION` remain in force.
