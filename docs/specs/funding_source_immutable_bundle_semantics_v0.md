# Funding Source Immutable Bundle Semantics — Spec v0 (test-facing)

## Status Boundary

- `EDGE_UNPROVEN` remains. `BLOCK_LIVE_INTEGRATION` remains.
- This is a **spec + spec-first tests** artifact. It implements **no** production
  verifier/writer/reporter behavior. It authorizes no DB mutation, official
  report overwrite, source CSV mutation, service/timer mutation, writer/trader
  run, deploy, or live integration.
- `clean` / `CLEAN_NET_OF_CARRY` means "not killed by this verifier gate" — never
  an edge, profitability, or live-approval signal.

## Purpose

Pin the observable contract for immutable funding-source bundle semantics
**before** implementation, so the follow-on implementation PR has an unambiguous
target. This spec is the source of truth for the planned-behavior tests in
[tests/test_funding_source_immutable_bundle_semantics.py](../../tests/test_funding_source_immutable_bundle_semantics.py).

Derived from the plan recorded in PR #105
([QNTY_FUNDING_SOURCE_IMMUTABLE_SOURCE_BUNDLE_SEMANTICS_PLAN.md](../plans/QNTY_FUNDING_SOURCE_IMMUTABLE_SOURCE_BUNDLE_SEMANTICS_PLAN.md)).

## Motivating flaw (PR #103 / #104)

The clean-carry verifier resolves funding rows and per-file digests from the
**live, mutable** `data/*_8h_funding.csv` files at run time. The
`qnty-data-refresh.timer` rewrites those files on a schedule. A verifier run that
starts after a refresh reads bytes that differ from the ones the DB-linked
snapshot was committed against, so a previously clean ledger flips to
`funding_source_file_digest_mismatch`. The recorded evidence is frozen; the thing
it is checked against is not. See
`test_current_default_mode_flips_clean_to_refused_when_live_csv_drifts`, which
reproduces that flip against tmp fixtures only.

## `source_resolution_mode`

Every verifier report **must** record `source_resolution_mode`, exactly one of:

- `bundle` — funding rows and digests resolved from the pinned immutable bundle
  (durable-evidence mode; default when a valid bundle is present).
- `live-current` — funding rows and digests resolved from the live CSVs
  (drift-detection mode; must still detect current CSV drift as today).

The two modes are never silently mixed. A reader must be able to tell from the
report alone which bytes were validated.

> Note: this is **distinct** from the existing `source_path_resolution_mode`
> (`explicit_data_dir` / `snapshot_provenance` / `unavailable`), which describes
> *where a path was resolved from*, not *which frozen-vs-live material was
> validated*. Both may appear in the report.

## Bundle identity (required fields)

A funding-source bundle binds a set of canonical funding rows to a hash and to
the DB-linked snapshot. Regardless of embedded-rows vs external-chunk layout, the
bundle must carry:

- `schema_version` — versioned, e.g. `FUNDING_SOURCE_BUNDLE_SCHEMA_V1`.
- `source_bundle_sha256` — sha256 over the canonical serialization of the rows.
- `original_source_digests` — per-file sha256 of the live CSVs **as captured**
  (so drift against original source stays auditable).
- `row_counts` — total and per symbol.
- `windows` — overall `window_start` / `window_end` and, where applicable, per
  symbol; sufficient to prove full-ledger funding-window coverage.
- `symbols` — the exact covered symbol set.
- Bundle **path + hash binding** — the DB-linked snapshot stores both the bundle
  path and the bundle hash; the verifier checks the file at the path hashes to
  the recorded value (path and hash must agree).

## Canonical serialization constraints

So that `source_bundle_sha256` recomputes deterministically byte-for-byte:

- **Deterministic total order** over rows: by `symbol`, then `window_start`, then
  the existing canonical row sort key (mirrors
  `funding_source_snapshot._canonical_row_sort_key`).
- **Canonical JSON**: UTF-8, sorted object keys, no insignificant whitespace,
  `\n` line endings — mirrors `funding_source_snapshot.canonical_json`.
- **Stable numeric formatting**: funding rates serialized as their exact recorded
  string form (no float re-formatting).
- Serialization is **versioned**; a canonicalization change requires a new
  `schema_version` and old bundles stay interpretable.

`test_canonical_serialization_is_deterministic_regardless_of_input_row_order` and
`test_source_bundle_sha_reproduces_over_frozen_rows` pin the determinism half
against the existing canonical primitives (these pass today).

## Acceptance / refusal (bundle mode)

Accept `clean` (not killed by this gate) only if **all** hold: bundle present at
the recorded path; path and hash agree; schema/version valid; coverage/window
complete; symbol set matches; row counts match; funding re-sum over bundle rows
matches the ledger funding re-sum.

Refuse (planned reason codes) if any hold:

| Condition                     | Planned reason code                        |
| ----------------------------- | ------------------------------------------ |
| bundle missing (bundle mode)  | `funding_source_bundle_missing`            |
| bundle corrupt / unparseable  | `funding_source_bundle_corrupt`            |
| path/hash disagree or sha recompute fails | `funding_source_bundle_hash_mismatch` |
| window/coverage incomplete    | `funding_source_bundle_incomplete_window`  |
| bundle↔ledger re-sum mismatch | `funding_resum_mismatch` (existing code)   |

`live-current` mode with no bundle emits an explicit caveat and **must still**
raise `funding_source_file_digest_mismatch` when the live CSVs differ from the
DB-linked recorded digests. Bundle mode must not be used to hide live drift.

## Non-goals

No edge/profit/significance claim. No change to what `CLEAN_NET_OF_CARRY` means.
No live integration, deploy, backfill, writer/trader run. No mutation of any real
DB, official report, live CSV, or service. Layout choice (embedded rows vs
external chunks) is deferred to the implementation PR; this spec constrains the
observable identity fields and refusal names only.
