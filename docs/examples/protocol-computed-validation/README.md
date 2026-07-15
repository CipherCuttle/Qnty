# Protocol computed-validation receipt example

This is a tiny, synthetic, docs-only fixture for the frozen
`--protocol-computed-validation` path. It has one bars CSV (8 rows), one funding
CSV (8 rows), and one append-only trial-registry entry carrying a structural
split-boundary declaration, a holdout seal declaration, and an execution
packet lock declaration. The checked-in `emitted_receipt.json` records a
receipt emitted from those inputs at commit
`d09330a`.

## Scope

Four computations run in this example, all structural provenance only:

1. **Input integrity** — role-relative source-byte fingerprinting, matching that
   fingerprint to the single frozen registry entry, and checking the declared
   purge/embargo intervals.
2. **Deterministic split materialization + leakage audit** — the fingerprinted
   bars rows are partitioned in recorded order at the pre-declared
   `split_boundary_index`, purge/embargo bands are removed, and the resulting
   train/purge/embargo/holdout partitions are audited for disjointness, holdout
   ordering, and realized purge/embargo gaps. This is **structural leakage
   auditing only** — ordinal row counts and booleans over timestamp/row order.
3. **Holdout seal fingerprint** — a SHA-256 hash of the exact raw row bytes of
   the holdout partition identified by step 2 (`bars`, plus `funding` here
   because its 8 rows align 1:1 with the bars rows), recorded as a
   `holdout_seal_state` of `sealed` / `mismatch` / `not_sealed`. This is a
   **content-blind, write-once attestation** that the holdout partition has
   not been altered since it was sealed — it never decodes, compares, or
   aggregates a price/value/outcome column, and it computes nothing about the
   partition's contents beyond a byte digest.
4. **Execution packet lock** — a SHA-256 hash-of-hashes
   (`execution_packet_fingerprint`) over exactly seven already-registered
   identity fields, in one fixed, documented order:
   `candidate_family_declaration_hash`, `null_family_declaration_hash`,
   `data_cut_fingerprint`, `split_boundary_declaration_hash`,
   `holdout_seal_fingerprint`, `code_commit_hash`, `protocol_version`.
   Compared against an append-only registry `execution_packet_declaration`,
   this yields `packet_lock_state` of `locked` / `mismatch` / `not_locked`.
   This is a **content-blind, write-once attestation that all seven already
   -registered artifacts still refer to the same trial** — it never creates,
   selects, or modifies a candidate, null, split, or holdout, never reads a
   price/value/outcome, and is never an authorization
   (`paper_trade_authorized` / `live_integration_authorized` stay `false`
   regardless of `packet_lock_state`).

The split audit reads **only** the `timestamp` column and row position, and the
seal fingerprint hashes **only** opaque raw row bytes. Neither dereferences a
price/value/outcome column (`close`, `funding_rate`, `value`, `pnl`, `return`,
`profit`, `edge`, `score`, ...). The two all-zero CLI provenance arguments are
inert fixture values required by the enclosing receipt interface; they are not
market results.

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

Whenever a split boundary was supplied, the holdout seal fingerprint additionally
sets `holdout_seal_killed: true` (folded into `protocol_execution_killed`) when
any of these occur:

- the upstream split leakage audit is absent, killed, or not passed;
- the holdout byte span cannot be resolved (row-count mismatch against the
  audited split, missing/unreadable source rows);
- a supplied non-bars role (e.g. `funding`) cannot be deterministically
  aligned to the bars-derived holdout partition (different row count or
  timestamp sequence) — the seal step fails closed rather than guessing;
- no registry `holdout_seal_declaration` exists yet (the computed fingerprint
  is only a candidate for a future append-only registry write, not a durable
  seal — `holdout_seal_state: not_sealed`);
- a registry `holdout_seal_declaration` is present but missing a required
  field (`holdout_seal_fingerprint`, `sealed_at_boundary_index`,
  `purge_intervals`, `embargo_intervals`);
- a registry `holdout_seal_declaration` is bound to a different
  boundary/purge/embargo than the one just audited;
- a recomputed fingerprint diverges from a complete, matching registry
  declaration (`holdout_seal_state: mismatch`) — this is the tamper-detection
  case: the holdout bytes changed since the declaration was registered.

Absent any registered `holdout_seal_declaration`, a passing run still computes
the fingerprint, but it is only a **candidate** value, not a durable seal:
`holdout_seal_state: not_sealed`, `holdout_seal_killed: true`,
`kill_criteria.registry_declaration_absent: true`, `registry_seal_fingerprint:
null`. The holdout only becomes `sealed` once that candidate fingerprint has
been written to the registry as a `holdout_seal_declaration` (append-only,
same trial, `honest_trial_count` unchanged) and a subsequent run's recomputed
fingerprint matches it exactly, with a matching boundary/purge/embargo. This
module never writes to the registry itself.

Whenever both the split-leakage audit and the holdout seal are present, the
execution packet lock additionally sets `packet_lock_killed: true` (folded
into `protocol_execution_killed`) when any of these occur:

- the upstream split-leakage audit is absent, not passed, or killed;
- the upstream holdout seal is absent, not `sealed`, or killed;
- any of the seven constituent identity fields is missing (e.g. no registered
  `candidate_family`/`null_family`, no split-boundary declaration, or no
  `code_commit_hash` supplied);
- no registry `execution_packet_declaration` exists yet (the computed
  `execution_packet_fingerprint` is only a candidate value, not a durable
  lock — `packet_lock_state: not_locked`,
  `kill_criteria.execution_packet_declaration_absent: true`);
- a registry `execution_packet_declaration` is present but missing one of the
  seven required constituent fields or `execution_packet_fingerprint`
  (`kill_criteria.execution_packet_declaration_incomplete: true`);
- a declared constituent no longer matches the current registry-authoritative
  value for that artifact — a stale reference, e.g. the packet declares a
  `holdout_seal_fingerprint` that no longer matches the current seal
  (`packet_lock_state: mismatch`,
  `kill_criteria.execution_packet_declaration_stale: true`);
- a recomputed `execution_packet_fingerprint` diverges from a complete,
  matching registry declaration (`packet_lock_state: mismatch`,
  `kill_criteria.execution_packet_fingerprint_mismatch: true`).

Absent any registered `execution_packet_declaration`, a passing run still
computes the candidate fingerprint, but `packet_lock_state` stays
`not_locked` and `packet_lock_killed` stays `true` until that candidate value
has been written to the registry as an `execution_packet_declaration`
(append-only, same trial, `honest_trial_count` unchanged, recording all seven
constituent hashes/strings verbatim plus a `locked_at` value — a deterministic
placeholder string in this fixture, since the module avoids wall-clock
timestamps in registered declarations) and a subsequent run's recomputed
fingerprint matches it exactly. This module never writes to the registry
itself. `packet_lock_state: locked` is a structural consistency attestation
only, never an authorization: `paper_trade_authorized` and
`live_integration_authorized` stay `false` regardless of `packet_lock_state`.

Passing these checks is not evidence of an edge, profit, or performance. It only
proves this small structural protocol slice had the declared synthetic inputs,
a well-formed leakage-free split, that the holdout bytes match what was last
sealed, and that all seven bound identity artifacts still refer to the same
trial.
