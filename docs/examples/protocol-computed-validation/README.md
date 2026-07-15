# Protocol computed-validation receipt example

This is a tiny, synthetic, docs-only fixture for the frozen
`--protocol-computed-validation` path. It has one bars CSV (8 rows), one funding
CSV (8 rows), and one append-only trial-registry entry carrying a structural
split-boundary declaration. The checked-in `emitted_receipt.json` records a
receipt emitted from those inputs at commit
`d09330a`.

## Scope

Two computations run in this example, both structural provenance only:

1. **Input integrity** — role-relative source-byte fingerprinting, matching that
   fingerprint to the single frozen registry entry, and checking the declared
   purge/embargo intervals.
2. **Deterministic split materialization + leakage audit** — the fingerprinted
   bars rows are partitioned in recorded order at the pre-declared
   `split_boundary_index`, purge/embargo bands are removed, and the resulting
   train/purge/embargo/holdout partitions are audited for disjointness, holdout
   ordering, and realized purge/embargo gaps. This is **structural leakage
   auditing only** — ordinal row counts and booleans over timestamp/row order.

The split audit reads **only** the `timestamp` column and row position. It never
dereferences a price/value/outcome column (`close`, `funding_rate`, `value`,
`pnl`, `return`, `profit`, `edge`, `score`, ...). The two all-zero CLI provenance
arguments are inert fixture values required by the enclosing receipt interface;
they are not market results.

Nothing here computes returns, PnL, profit, edge, a score, performance,
p-values, confidence intervals, Sharpe, drawdown, risk, a baseline/benchmark
result, strategy decisions, or a paper/live result. Passing the leakage audit is
**not** evidence of an edge, profit, or performance — it only proves the declared
synthetic split is structurally well-formed and leakage-free by construction. The
enclosing receipt therefore remains `BLOCKED_BY_VALIDATION_IMPLEMENTATION`, its
computed result remains `EDGE_UNPROVEN`, and its guardrails retain both
`edge_unproven: true` and `block_live_integration: true`. Paper trading and live
integration remain unauthorized.

## Reproduce

Run from the repository root. First derive the expected data-cut fingerprint
from exactly the checked-in source bytes (this helper does not write a receipt):

```sh
python -c 'from pathlib import Path; from quantbot.experiment.offline_edge_real_validation import build_protocol_computed_validation_slice; s=build_protocol_computed_validation_slice(bars_dir=Path("docs/examples/protocol-computed-validation/bars"), funding_dir=Path("docs/examples/protocol-computed-validation/funding"), expected_data_cut_fingerprint=None, trial_registry_path=None); print(s["immutable_data_cut"]["actual_sha256"])'
```

It must print:

```text
4c1ffa74b28e011127ae89707d87c587e8c998ccb18936c8ec5b724e099eaf63
```

Then invoke the CLI. It writes only beneath `/tmp`:

```sh
python -m quantbot.experiment.offline_edge_real_validation \
  --read-only \
  --output-dir /tmp/qnty-protocol-computed-validation-example \
  --input-manifest-fingerprint 0000000000000000000000000000000000000000000000000000000000000000 \
  --data-quality-receipt-sha256 0000000000000000000000000000000000000000000000000000000000000000 \
  --code-commit-sha d09330a \
  --protocol-computed-validation \
  --bars-dir docs/examples/protocol-computed-validation/bars \
  --funding-dir docs/examples/protocol-computed-validation/funding \
  --expected-data-cut-fingerprint 4c1ffa74b28e011127ae89707d87c587e8c998ccb18936c8ec5b724e099eaf63 \
  --trial-registry-path docs/examples/protocol-computed-validation/trial_registry.json \
  --purge-intervals 1 \
  --embargo-intervals 1 \
  --split-boundary-index 4
```

The receipt timestamp and its byte digest vary per execution; its protocol
shape, split-audit counts, and all blocked/unauthorized states should match the
fixture.

## Split semantics

Given the bars rows in recorded order and the declared `boundary_index` (4),
`purge_intervals` (1), `embargo_intervals` (1):

- `boundary_index` is the index of the **first raw holdout row**.
- **train_eligible** = rows before `boundary_index` (rows 0–3).
- **holdout_eligible** = rows from `boundary_index` onward (rows 4–7).
- **purged** = the final `purge_intervals` rows of `train_eligible` (row 3).
- **embargoed** = the first `embargo_intervals` rows of `holdout_eligible` (row 4).
- **train** = `train_eligible` minus purged (rows 0–2, count 3).
- **holdout** = `holdout_eligible` minus embargoed (rows 5–7, count 3).

The fixture is sized so train, purge, embargo, and holdout are all non-empty;
too few rows would make the leakage audit kill.

## Fail-closed kill criteria

The input-integrity slice sets `protocol_execution_killed: true` and does not
advance authorization when any of these conditions is true:

- source inputs are absent;
- the expected data-cut fingerprint is missing or does not match the CSV bytes;
- the registry is absent, malformed, non-append-only, not registered before
  execution, has a non-matching data cut, or names a different frozen family;
- either purge or embargo is missing, non-integer, or less than one interval.

When a `--split-boundary-index` is supplied, the deterministic split leakage
audit additionally sets `leakage_audit_killed: true` (folded into
`protocol_execution_killed`) when any of these occur:

- `--split-boundary-index` is missing, non-integer, or out of range;
- purge/embargo is missing, non-integer, or less than one interval;
- the train, holdout, purge, or embargo partition is empty;
- partitions overlap;
- holdout is not strictly after train by row/timestamp order;
- the realized purge or embargo gap is smaller than the declared interval;
- timestamps are non-monotonic within the role;
- the registry has no split-boundary declaration, or its declaration does not
  match the execution argument (a changed split is a new trial).

Passing these checks is not evidence of an edge, profit, or performance. It only
proves this small structural protocol slice had the declared synthetic inputs
and a well-formed, leakage-free split.
