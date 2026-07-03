# QNTY Batch-Scoped Clean-Carry Verifier Plan

## 1. Purpose

Plan a docs-only change path for the SQLite clean-carry verifier after the prod
root-cause audit showed that DB-linked funding source snapshots are emitted per
ledger batch while the strict verifier currently compares one sidecar against
the full funding-table span.

This plan does not implement code, does not mutate prod or shadow state, and
does not relabel prod/current ledgers as `CLEAN_NET_OF_CARRY`. `EDGE_UNPROVEN`
and `CAVEATED_ENGINE_SEMANTICS` remain preserved.

## 2. Context

PR #72 added the prod clean-carry caveat root-cause audit at `d73bd02`. The
audit result was:

```txt
STRICT_READ_ONLY_PROD_VERIFIER_AUDIT_CAVEATED
ROOT_CAUSE_BATCH_VS_LEDGER_WINDOW_SEMANTICS
```

Manual and strict read-only findings showed:

- Prod batch 39 has a structurally valid DB-linked snapshot sidecar.
- The sidecar file SHA matches the DB reference.
- The envelope validates.
- Bundle, schema, and write state are committed and coherent.
- Funding re-sum/arithmetic is OK.
- The sidecar `evaluation_window` is `2026-07-03T00:00:00Z` to
  `2026-07-03T08:00:00Z`.
- The sidecar `coverage_decision` is `complete`.
- Running the verifier from `/srv/qnty/repo` matched the 4/4 required source
  windows for the latest sidecar.
- The remaining strict reason code was
  `funding_source_snapshot_window_mismatch`.

Current interpretation stays conservative: no edge claim, no profitability
claim, `EDGE_UNPROVEN` remains preserved, prod/current remains
`CAVEATED_ENGINE_SEMANTICS`, and current ledgers are not
`CLEAN_NET_OF_CARRY`.

## 3. Current verifier semantics

`quantbot/paper/sqlite_verify.py` currently selects the latest committed
`ledger_batches` row as the clean-carry target batch and reads its DB-linked
funding snapshot reference from the `funding_source_snapshot_*` columns.

The verifier already refuses unsafe snapshot evidence when the DB reference is
missing, incomplete, outside the expected snapshot directory, duplicated,
digest-mismatched, schema-unsupported, pending, orphaned, lane-mismatched, or
batch-identity-mismatched.

However, the strict clean-carry gate then calls
`clean_mode_decision_from_snapshot_v1` with:

```txt
expected_evaluation_window = MIN(funding.window_start), MAX(funding.window_end)
```

That is full-ledger funding-table semantics. It expects one selected sidecar to
declare an `evaluation_window` covering the whole ledger funding history, not
only the target batch.

The current report fields collapse that outcome into one strict decision:

```txt
funding_clean_carry_decision: CLEAN_NET_OF_CARRY | CAVEATED_ENGINE_SEMANTICS
funding_clean_carry_status: clean_net_of_carry | refused_*
funding_clean_carry_reason_codes: [...]
```

Those fields must not be overloaded with a new implicit scope.

## 4. Current writer snapshot semantics

`quantbot/paper/funding_source_snapshot.py` builds snapshot payloads from the
caller-provided `required_funding_windows`. Its `_evaluation_window()` derives
the payload window from those required windows unless an explicit window is
provided.

The writer path therefore emits incremental, per-batch snapshots. The relevant
snapshot metadata already carries batch identity fields such as:

```txt
ledger_batch_id
pending_batch_id
batch_start_watermark
batch_end_watermark
batch_identity_matches
evaluation_identity_matches
write_state
db_path_reference
```

For prod batch 39, the sidecar window matched the batch watermark range:

```txt
prior_watermark_bar_ts: 2026-07-03T00:00:00
new_watermark_bar_ts:   2026-07-03T08:00:00
sidecar evaluation_window: 2026-07-03T00:00:00Z to 2026-07-03T08:00:00Z
```

That is the expected writer behavior. It is not evidence that the writer should
emit a full-ledger sidecar for every latest batch.

## 5. Root cause from prod audit

The root cause used by this plan is:

```txt
ROOT_CAUSE_BATCH_VS_LEDGER_WINDOW_SEMANTICS
```

The strict verifier compares a per-batch-scoped writer sidecar against a
full-ledger-scoped expected window. These semantics disagree by construction.
After the cwd/source-path effect was isolated by running from `/srv/qnty/repo`,
coverage and digest reasons disappeared, while
`funding_source_snapshot_window_mismatch` remained.

Therefore a latest batch sidecar can be structurally valid, source-complete, and
arithmetically coherent while still refusing the current full-ledger
`CLEAN_NET_OF_CARRY` gate.

## 6. Separate cwd/source-path bug

The prod audit also found a separate verifier defect:

```txt
_resolve_funding_csv_dir/_snapshot_source_file_path silently fall back to
cwd-relative data paths.
```

When the verifier ran from `/home/viktor`, it looked for `data/*.csv` relative
to that cwd and produced misleading:

```txt
funding_source_coverage_not_complete
funding_source_file_digest_mismatch
funding_source_row_digest_mismatch
missing_source_row
```

When the same verifier ran from `/srv/qnty/repo`, the source rows resolved and
the report reduced to the true structural blocker:

```txt
funding_source_snapshot_window_mismatch
```

The source-path bug must be fixed before any future acceptance claim, because
verifier evidence cannot depend on cwd.

## 7. Why full-ledger clean-carry is too strict for latest batch sidecars

The full funding table spans `2026-06-21` through `2026-07-03T08:00:00` across
36 funding rows and 39 batches. The latest DB-linked snapshot sidecar covers
only the evaluated batch window, `2026-07-03T00:00:00Z` to
`2026-07-03T08:00:00Z`.

Requiring the latest sidecar to equal the full funding-table span is too strict
for the current writer model because:

- One latest sidecar cannot contain historical source evidence for batches that
  were committed before DB-linked snapshot references existed.
- Old `ledger_batches` rows with NULL snapshot reference columns remain
  historical evidence gaps for full-ledger clean-carry.
- A batch-scoped writer can correctly prove the latest batch without proving the
  full ledger.
- Full-ledger evidence requires either committed DB-linked source evidence for
  every relevant historical funding window or a separate retroactive
  snapshot/backfill receipt.

## 8. Proposed batch-scoped clean-carry definition

Introduce two explicit clean-carry scopes. The recommended report model is to
add explicit scope fields rather than redefine the existing decision:

```txt
funding_clean_carry_batch_decision:
  CLEAN_NET_OF_CARRY_BATCH | CAVEATED_ENGINE_SEMANTICS
funding_clean_carry_batch_status:
  clean_net_of_carry_batch | refused_*
funding_clean_carry_batch_reason_codes:
  [...]

funding_clean_carry_full_ledger_decision:
  CLEAN_NET_OF_CARRY_FULL_LEDGER | CAVEATED_ENGINE_SEMANTICS
funding_clean_carry_full_ledger_status:
  clean_net_of_carry_full_ledger | refused_*
funding_clean_carry_full_ledger_reason_codes:
  [...]
```

Equivalent explicit fields are acceptable, for example:

```txt
funding_clean_carry_scope: batch | full_ledger
funding_clean_carry_decision: CLEAN_NET_OF_CARRY | CAVEATED_ENGINE_SEMANTICS
```

But the old unscoped `funding_clean_carry_decision` must not silently change
meaning. During migration, keep the legacy field conservative or mark its scope
explicitly in JSON so no consumer can confuse batch clean evidence with
full-ledger clean evidence.

Batch-scoped clean-carry may pass only for the evaluated ledger batch if:

- The evaluated ledger batch has a non-null DB-linked snapshot reference.
- The sidecar path resolves under
  `db_path.parent / "funding_source_snapshots"`.
- The sidecar file SHA matches the DB reference.
- The envelope validates.
- The source bundle SHA matches the DB reference.
- The schema version matches the DB reference.
- DB `write_state` and sidecar `write_state` are `committed`.
- The sidecar `evaluation_window` equals the evaluated batch
  `prior_watermark_bar_ts` to `new_watermark_bar_ts` range, not the full ledger
  funding span.
- Required funding windows inside that batch window have complete source
  coverage.
- Source file and row digests match for that batch window.
- Arithmetic status is OK.
- An independent funding re-sum for the evaluated batch or an independently
  checked cumulative state transition matches documented tolerance.

## 9. Required verifier report fields

The JSON report should make scope impossible to miss. Add or equivalent fields:

```txt
funding_clean_carry_batch_decision
funding_clean_carry_batch_status
funding_clean_carry_batch_reason_codes
funding_clean_carry_batch_scope: batch
funding_clean_carry_batch_target_batch_id
funding_clean_carry_batch_window
funding_clean_carry_batch_expected_window_source: ledger_batches_watermarks
funding_clean_carry_batch_snapshot_window
funding_clean_carry_batch_source_coverage_decision
funding_clean_carry_batch_resum_check

funding_clean_carry_full_ledger_decision
funding_clean_carry_full_ledger_status
funding_clean_carry_full_ledger_reason_codes
funding_clean_carry_full_ledger_scope: full_ledger
funding_clean_carry_full_ledger_window
funding_clean_carry_full_ledger_historical_snapshot_gap_count
funding_clean_carry_full_ledger_null_snapshot_batch_ids

resolved_funding_source_dir
funding_source_path_resolution_mode
funding_source_path_resolution_reason
```

The report should also keep the existing snapshot detail block:

```txt
funding_source_snapshot
funding_source_snapshot_status
funding_source_snapshot.selected_snapshot_path
funding_source_snapshot.target_batch_id
funding_source_snapshot.reason_codes
```

## 10. Required CLI/source-path behavior

Plan prerequisite implementation:

```txt
TEST_ONLY_SQLITE_VERIFY_SOURCE_PATH_RESOLUTION
IMPLEMENT_SQLITE_VERIFY_SOURCE_PATH_RESOLUTION
```

Required behavior:

- The verifier CLI must not depend on cwd.
- The verifier must resolve source data paths deterministically.
- Prefer an explicit `--data-dir` option for CLI invocations.
- If an explicit `--data-dir` is absent, prefer a source path recorded in the
  sidecar/provenance or another committed provenance field.
- Do not silently fall back to cwd-relative `data`.
- If the source path is unavailable, fail closed with
  `source_path_unavailable`.
- The JSON report must include `resolved_funding_source_dir`.
- The JSON report must include how the path was resolved, for example
  `funding_source_path_resolution_mode`.
- Missing or mismatched source paths must not be reported as misleading digest
  or coverage reason codes unless the verifier actually resolved and read the
  intended source files.

This source-path fix should land before batch-scoped clean-carry logic so future
audits can distinguish true source evidence failures from path resolution
failures.

## 11. Batch-scoped acceptance gates

A future read-only prod batch-scoped clean-carry audit may accept only if all
batch gates pass:

- The verifier code under audit is deployed intentionally and recorded by commit.
- The verifier CLI runs read-only with `--db-path`, `--read-only`, `--json`,
  `--strict-clean-carry`, and deterministic source path resolution.
- The JSON report includes `resolved_funding_source_dir`.
- The evaluated `target_batch_id` is explicit.
- The target batch has a complete DB-linked snapshot reference.
- The sidecar is selected by the DB reference, not by directory scan alone.
- The sidecar path is under the expected snapshot directory.
- The DB-recorded sidecar SHA matches sidecar bytes.
- Envelope validation returns no errors.
- Bundle SHA, schema version, and write state match between DB and sidecar.
- Sidecar metadata matches DB path, lane, and batch identity.
- Sidecar `evaluation_window` equals the target batch watermark range.
- Required funding windows in that batch window are complete.
- Source file and row digests match for that batch window.
- Arithmetic status is OK.
- The independent batch or cumulative transition re-sum is within documented
  tolerance.
- The report explicitly says batch scope and does not imply full-ledger scope.

## 12. Full-ledger clean-carry remains separate

Full-ledger clean-carry remains refused unless the verifier can prove every
relevant historical funding window has committed DB-linked source evidence, or
unless a separate retroactive snapshot/backfill receipt exists and is accepted
by an explicit full-ledger gate.

The full-ledger decision should use a separate result:

```txt
funding_clean_carry_full_ledger_decision:
  CLEAN_NET_OF_CARRY_FULL_LEDGER | CAVEATED_ENGINE_SEMANTICS
```

For the currently observed prod ledger, full-ledger clean-carry remains
`CAVEATED_ENGINE_SEMANTICS` because older rows and batches lack DB-linked
snapshot references. A passing batch-scoped result must not relabel
prod/current ledgers as full-ledger `CLEAN_NET_OF_CARRY`.

## 13. Historical ledger treatment

Historical rows with NULL snapshot references remain caveated for full-ledger
purposes. They should be reported explicitly rather than hidden behind a latest
batch success.

Recommended historical report fields:

```txt
funding_clean_carry_full_ledger_historical_snapshot_gap_count
funding_clean_carry_full_ledger_null_snapshot_batch_ids
funding_clean_carry_full_ledger_first_unproven_window_start
funding_clean_carry_full_ledger_last_unproven_window_end
```

If a future backfill path is designed, it should be separate from this plan and
should require its own docs plan, test-only PR, implementation PR, read-only
audit, and acceptance receipt. Until then, historical un-snapshotted windows
preserve `CAVEATED_ENGINE_SEMANTICS`.

## 14. Failure modes/refusal reasons

Batch-scoped clean-carry should fail closed with explicit refusal reasons:

- `funding_source_snapshot_missing`: target batch has NULL or incomplete DB
  snapshot reference fields.
- `funding_source_snapshot_path_outside_snapshot_dir`: referenced sidecar is
  not under `db_path.parent / "funding_source_snapshots"`.
- `funding_source_snapshot_path_traversal`: referenced path is unsafe.
- `funding_source_snapshot_digest_mismatch`: sidecar bytes do not match DB SHA.
- `funding_source_file_digest_mismatch`: resolved source file digest or source
  bundle digest does not match expected evidence.
- `funding_source_row_digest_mismatch`: canonical row subset digest does not
  match expected evidence.
- `funding_source_snapshot_schema_unsupported`: schema version is unsupported or
  differs from the DB reference.
- `funding_source_snapshot_payload_invalid`: envelope or payload validation
  fails.
- `funding_source_snapshot_unreferenced_or_orphaned`: DB or sidecar write state
  is not committed, or batch identity is not coherent.
- `funding_source_snapshot_db_mismatch`: lane, DB path, or metadata identity is
  not coherent.
- `funding_source_snapshot_batch_window_mismatch`: sidecar window does not equal
  the target batch watermark range.
- `source_path_unavailable`: source data path cannot be resolved
  deterministically.
- `funding_source_coverage_not_complete`: required funding windows inside the
  batch window are not complete after deterministic source resolution.
- `funding_resum_mismatch`: batch or cumulative transition re-sum differs beyond
  tolerance.
- `funding_full_ledger_historical_snapshot_gap`: full-ledger scope has older
  funding windows without committed DB-linked source evidence.

The verifier should avoid mapping `source_path_unavailable` into digest or
coverage mismatch codes. Digest and row mismatch codes should mean the intended
source files were resolved and read.

## 15. Test plan

Add tests before implementation, using tmp DBs and tmp CSVs only:

- Verifier result is identical from arbitrary cwd and repo cwd when `--data-dir`
  or sidecar source path is available.
- Missing source dir fails closed with `source_path_unavailable`.
- No silent cwd fallback.
- Latest prod-like batch sidecar window can pass batch-scoped gates.
- The same DB remains full-ledger caveated because historical rows lack
  DB-linked snapshots.
- Batch-scoped clean does not imply full-ledger clean.
- Old NULL rows remain caveated.
- Digest mismatch inside the batch window refuses batch clean.
- Batch window mismatch refuses batch clean.
- Cumulative re-sum mismatch refuses batch clean.

Suggested test-only PR names:

```txt
TEST_ONLY_SQLITE_VERIFY_SOURCE_PATH_RESOLUTION
TEST_ONLY_BATCH_SCOPED_CLEAN_CARRY_VERIFIER
```

The tests should assert report field names and refusal reason codes, not only
boolean pass/fail outcomes.

## 16. Implementation PR sequence

Recommended conservative sequence:

```txt
1. TEST_ONLY_SQLITE_VERIFY_SOURCE_PATH_RESOLUTION
2. IMPLEMENT_SQLITE_VERIFY_SOURCE_PATH_RESOLUTION
3. TEST_ONLY_BATCH_SCOPED_CLEAN_CARRY_VERIFIER
4. IMPLEMENT_BATCH_SCOPED_CLEAN_CARRY_VERIFIER
5. DEPLOY_VM_CODE_ONLY_FOR_BATCH_SCOPED_VERIFIER
6. READ_ONLY_PROD_BATCH_SCOPED_CLEAN_CARRY_AUDIT
7. ADD_BATCH_SCOPED_CLEAN_CARRY_ACCEPTANCE_RECEIPT
```

Do not recommend immediate prod relabeling. The first prod-facing result after
deployment should be a read-only audit. Any acceptance receipt must preserve the
scope split and must state that batch-scoped clean evidence does not imply
full-ledger clean evidence.

## 17. Safety boundaries

This plan is docs-only. It does not:

- Edit production code.
- Edit tests.
- Run the prod writer.
- Run the shadow writer.
- Mutate prod DB.
- Mutate shadow DB.
- Mutate `forward_obs`.
- SSH to the VM.
- Run migrations.
- Run schema ensure helpers.
- Run data refresh.
- Change timers or systemd.
- Install dependencies.
- Touch `.claude/`.
- Make an edge claim.
- Make a profitability claim.
- Relabel prod/current ledgers as `CLEAN_NET_OF_CARRY`.

`EDGE_UNPROVEN` remains preserved. `CAVEATED_ENGINE_SEMANTICS` remains preserved
for prod/current full-ledger interpretation.

## 18. Verdict

```txt
BATCH_SCOPED_CLEAN_CARRY_VERIFIER_PLAN_READY_FOR_PR
```
