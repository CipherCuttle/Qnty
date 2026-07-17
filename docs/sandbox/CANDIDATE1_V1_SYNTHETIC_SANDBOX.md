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

## Accounting semantics

For a scenario with `N` observations there are `N-1` evaluated intervals indexed
`t = 0 .. N-2`; interval `t` spans observations `t` and `t+1`. Each rule chooses
`position(t)` in `{-1, 0, 1}` **before** interval `t`, reading only observations
with index strictly less than `t`, and holds it across the whole interval. The
initial position is flat: `position(-1) = 0`.

Per interval:

- `price_component(t) = position(t) * (price[t+1] - price[t])`
- `funding_component(t) = -position(t) * funding[t]`
- `cost(t) = transaction_cost * abs(position(t) - position(t-1))`, with
  `position(-1) = 0`, so entering from the initial flat state is charged
- `net(t) = price_component(t) + funding_component(t) - cost(t)`

`turnover_count` is the number of intervals where `position(t) != position(t-1)`
(again `position(-1) = 0`). **Terminal liquidation is excluded**: the position
held over the final evaluated interval is not flattened and incurs no terminal
closing transaction cost.

Slot counts are `active_slot_count` (positions in `{-1, 1}`), `long_slot_count`
(`+1`), `short_slot_count` (`-1`), and `flat_slot_count` (`0`). They satisfy
`active_slot_count == long_slot_count + short_slot_count` and
`active_slot_count + flat_slot_count == N-1`. Every reported mean divides its
summed component by the evaluated-interval count `N-1`. `transaction_cost` is a
declared arbitrary constant for mechanical path coverage, not a market estimate.

## Receipts and replay

Receipts contain the raw input digest, canonical bundle, contract fingerprints,
every variant/scenario mechanical result, safety invariants, and a
`run_fingerprint`. Results are sorted only by `variant_id`, then `scenario_id`;
there is no ranking, winner, recommendation, selection, or scientific metric.

`raw_input_sha256` records the SHA-256 of the original variant bundle bytes as
submitted; `canonical_bundle_sha256` identifies the semantic bundle after
canonicalisation, so equivalent pretty/compact inputs share it. The
`rule_contract_sha256` and `accounting_contract_sha256` fingerprints bind the
full machine-readable rule and accounting contracts (rule IDs, parameter
schemas and ranges, deadband and warm-up semantics, the decision information
set, and every component/turnover/timing formula above); they change whenever
those generic mechanical assumptions change.

Verification requires exact canonical bytes, checks every SHA-256 field is a
lowercase 64-character hex string, re-validates the embedded bundle and contract
fingerprints, and deterministically replays every result. Receipt verification
therefore proves deterministic self-consistency and exact replay only — it is
**not** a cryptographic signature or any form of external authentication, and it
asserts nothing about market behaviour.

To create a new batch, copy the example, change only declarative variants,
provide an explicit rationale for each, and run into a new existing workspace
directory. Repeat the run and compare bytes before verification.

Publication is atomic and fail-closed: the parent directory must already exist,
the destination must not exist, canonical bytes are written to a temporary file
in the same directory, flushed and fsynced, then published with no-overwrite
semantics and read back. A run never reports success unless the final file
exists with exactly the canonical bytes, and an interrupted or failed run leaves
no partial destination. The CLI exit codes are `0` success, `2` input/bundle
validation failure, `3` receipt verification failure, and `4` output
publication failure; expected failures print a short message with no traceback.

## Interpretation and prohibitions

The accounting fields describe mechanical slot, component, turnover, and fixed
arbitrary transaction-cost paths. They cannot establish scientific validity,
market edge, profitability, expected live performance, or a strategy choice.
Real data selection and execution remain forbidden. Candidate 1 V0 remains
unavailable; the official V1 protocol does not exist; no paper/live authority or
sandbox execution budget is granted; `EDGE_UNPROVEN` and
`BLOCK_LIVE_INTEGRATION` remain in force.
