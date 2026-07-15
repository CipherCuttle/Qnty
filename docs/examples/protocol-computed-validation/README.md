# Protocol computed-validation receipt example

This is a tiny, synthetic, docs-only fixture for the frozen
`--protocol-computed-validation` path. It has one bars CSV, one funding CSV,
and one append-only trial-registry entry. The checked-in
`emitted_receipt.json` records a receipt emitted from those inputs at commit
`bb2ed1beb5e84ff22f8f5e6c6b55fef0d9f8bda3`.

## Scope

The only computation in this example is the data-cut/input-integrity protocol
slice: role-relative source-byte fingerprinting, matching that fingerprint to
the single frozen registry entry, and checking the declared purge/embargo
intervals. The two all-zero CLI provenance arguments are inert fixture values
required by the enclosing receipt interface; they are not market results.

Nothing here computes returns, PnL, edge, a score, strategy decisions, or a
paper/live result. The enclosing receipt therefore remains
`BLOCKED_BY_VALIDATION_IMPLEMENTATION`, its computed result remains
`EDGE_UNPROVEN`, and its guardrails retain both `edge_unproven: true` and
`block_live_integration: true`. Paper trading and live integration remain
unauthorized.

## Reproduce

Run from the repository root. First derive the expected data-cut fingerprint
from exactly the checked-in source bytes (this helper does not write a receipt):

```sh
python -c 'from pathlib import Path; from quantbot.experiment.offline_edge_real_validation import build_protocol_computed_validation_slice; s=build_protocol_computed_validation_slice(bars_dir=Path("docs/examples/protocol-computed-validation/bars"), funding_dir=Path("docs/examples/protocol-computed-validation/funding"), expected_data_cut_fingerprint=None, trial_registry_path=None); print(s["immutable_data_cut"]["actual_sha256"])'
```

It must print:

```text
023ad07777f72596bedbe852a781c6f54938f106a0379747c956d83f93207abc
```

Then invoke the CLI. It writes only beneath `/tmp`:

```sh
python -m quantbot.experiment.offline_edge_real_validation \
  --read-only \
  --output-dir /tmp/qnty-protocol-computed-validation-example \
  --input-manifest-fingerprint 0000000000000000000000000000000000000000000000000000000000000000 \
  --data-quality-receipt-sha256 0000000000000000000000000000000000000000000000000000000000000000 \
  --code-commit-sha bb2ed1beb5e84ff22f8f5e6c6b55fef0d9f8bda3 \
  --protocol-computed-validation \
  --bars-dir docs/examples/protocol-computed-validation/bars \
  --funding-dir docs/examples/protocol-computed-validation/funding \
  --expected-data-cut-fingerprint 023ad07777f72596bedbe852a781c6f54938f106a0379747c956d83f93207abc \
  --trial-registry-path docs/examples/protocol-computed-validation/trial_registry.json \
  --purge-intervals 1 \
  --embargo-intervals 1
```

The receipt timestamp and its byte digest vary per execution; its protocol
shape and all blocked/unauthorized states should match the fixture.

## Fail-closed kill criteria

The computed slice sets `protocol_execution_killed: true` and does not advance
authorization when any of these conditions is true:

- source inputs are absent;
- the expected data-cut fingerprint is missing or does not match the CSV bytes;
- the registry is absent, malformed, non-append-only, not registered before
  execution, has a non-matching data cut, or names a different frozen family;
- either purge or embargo is missing, non-integer, or less than one interval.

Passing those integrity checks is not evidence of an edge. It only proves this
small protocol slice had the declared synthetic inputs.
