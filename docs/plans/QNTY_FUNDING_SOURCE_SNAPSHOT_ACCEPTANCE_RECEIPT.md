# QNTY Funding Source Snapshot Acceptance Receipt

## 1. Purpose

Task: `ADD_FUNDING_SOURCE_SNAPSHOT_ACCEPTANCE_RECEIPT`

Summarize what the funding source snapshot and clean-carry repair sequence now
proves, what remains synthetic only, and why current/live ledgers are still not
relabeled as `CLEAN_NET_OF_CARRY`.

Current interpretation remains:

```txt
EDGE_STATUS: EDGE_UNPROVEN
current/live funding verdict: CAVEATED_ENGINE_SEMANTICS
current/live ledgers are not CLEAN_NET_OF_CARRY
```

This receipt makes no edge claim and no profitability claim.

## 2. Scope

This is a docs-only acceptance receipt.

In scope:

- summarize the merged funding source snapshot implementation state;
- summarize local synthetic test proof;
- preserve current/live caveats;
- recommend the next implementation decision.

Out of scope:

- production code edits;
- test edits;
- fixture edits;
- prod writer runs;
- shadow writer runs;
- any writer run against `/srv`;
- VM access;
- prod or shadow DB mutation;
- `forward_obs` mutation;
- data refresh;
- systemd/timer changes;
- dependency installation;
- migrations;
- `.claude/` changes.

## 3. Current repository state

Preflight for this receipt:

```txt
branch before receipt branch: main
receipt branch: docs/funding-source-snapshot-acceptance-receipt
HEAD: f5300d51aa6a664d5236d452ef58689219706f87
main: f5300d51aa6a664d5236d452ef58689219706f87
origin/main: f5300d51aa6a664d5236d452ef58689219706f87
remote origin/main: f5300d51aa6a664d5236d452ef58689219706f87
main == origin/main: yes
HEAD is f5300d5 or newer: yes
tracked tree clean before receipt: yes
allowed untracked before receipt: .claude/
```

Required prerequisite files were present:

```txt
docs/plans/QNTY_FUNDING_SOURCE_SNAPSHOT_RECEIPT_PLAN.md
docs/plans/QNTY_CLEAN_NET_OF_CARRY_REPAIR_PLAN.md
quantbot/paper/funding_source_snapshot.py
quantbot/paper/sqlite_writer.py
quantbot/paper/sqlite_verify.py
tests/test_funding_source_snapshot_schema.py
tests/test_paper_sqlite_writer_source_snapshot_emission.py
tests/test_paper_sqlite_verifier_source_snapshot_read.py
tests/test_paper_sqlite_verifier_clean_net_of_carry_gate.py
```

This follows the merged repair sequence:

```txt
PR #51 funding source snapshot receipt plan merged
PR #52 funding source snapshot schema spec merged
funding source snapshot builder merged
PR #54 writer source snapshot sidecar emission merged
PR #55 sqlite verifier source snapshot read merged
PR #56 verifier clean net of carry gate merged
```

## 4. What is now implemented

The repository now has a pure funding source snapshot builder in
`quantbot/paper/funding_source_snapshot.py`. It builds deterministic v1 payloads
from caller-provided source rows, required windows, source files/content,
normalization metadata, lane metadata, DB/evaluation identity metadata, and
write state.

The SQLite writer now emits a funding source snapshot sidecar before durable DB
inserts. The sidecar is written under the evaluated DB directory, using an atomic
temp-write/rename flow. Snapshot emission failure aborts before ledger mutation.

The SQLite verifier now reads funding source snapshot sidecars as diagnostic
provenance, classifies snapshot state, and keeps arithmetic status separate from
snapshot evidence.

The strict clean-carry gate now combines arithmetic status, source coverage,
snapshot status, source digest checks, window/lane linkage checks, and an
independent funding re-sum before allowing `CLEAN_NET_OF_CARRY`.

## 5. What is proven by tests

Local synthetic tests prove the following:

- the snapshot envelope is content-addressed and validates its payload hash;
- schema v1 pins provenance, normalization version, source file digests,
  canonical row-subset digests, required windows, write state, and reason codes;
- pending and orphaned snapshots are not clean evidence;
- missing, digest-mismatched, unsupported-schema, DB/lane-mismatched,
  ambiguous-multiple, source-coverage, and re-sum-mismatch cases refuse clean;
- writer happy path emits a valid `write_state=pending` sidecar;
- writer sidecar emission failure aborts before durable DB mutation;
- writer atomic rename failure leaves durable DB tables and final JSON unchanged;
- writer funding coverage aborts do not emit a sidecar;
- verifier snapshot reads are diagnostic-only and do not alter arithmetic status;
- a tmp-only synthetic DB can return `CLEAN_NET_OF_CARRY` only when a valid
  committed snapshot, complete source coverage, arithmetic OK, and re-sum proof
  exist.

Verification commands run for this receipt:

```txt
python -m pytest tests/test_funding_source_snapshot_schema.py -q
18 passed

python -m pytest tests/test_paper_sqlite_verifier_source_snapshot_read.py -q
11 passed

python -m pytest tests/test_paper_sqlite_verifier_clean_net_of_carry_gate.py -q
14 passed

python -m pytest tests/test_paper_sqlite_funding_coverage.py -q
5 passed

python -m py_compile quantbot/paper/funding_source_snapshot.py
passed

python -m py_compile quantbot/paper/sqlite_writer.py
passed

python -m py_compile quantbot/paper/sqlite_verify.py
passed

/tmp/qnty-pr50-pandas-test/bin/python -m pytest tests/test_paper_sqlite_writer_source_snapshot_emission.py -q
7 passed

/tmp/qnty-pr50-pandas-test/bin/python -m pytest tests/test_paper_sqlite_writer_funding_fail_closed_proof.py -q
9 passed

/tmp/qnty-pr50-pandas-test/bin/python -m pytest tests/test_paper_sqlite_writer_funding_coverage.py -q
8 passed
```

## 6. What remains synthetic only

The system can now represent and verify `CLEAN_NET_OF_CARRY` in tmp-only
synthetic tests when a valid committed snapshot and arithmetic proof exist.

That proof is not a current/live ledger relabel. The clean case exists only in
local tmp DB, tmp CSV, and tmp sidecar fixtures. It does not prove that any
current/live prod or shadow ledger has a committed, DB-linked, digest-valid
funding source snapshot for its historical batches.

No read-only live acceptance run was performed for this receipt.

## 7. Why current/live ledgers remain `CAVEATED_ENGINE_SEMANTICS`

Current/live ledgers remain `CAVEATED_ENGINE_SEMANTICS` because:

- no read-only live acceptance run was performed;
- current writer sidecars are pending by design;
- there is no durable DB schema link/selector from ledger batch to snapshot
  sidecar;
- multiple sidecars can remain ambiguous without schema linkage;
- no retroactive snapshot exists for old live batches;
- the current/live evidence has not been proven through the strict clean-carry
  gate.

Therefore `CAVEATED_ENGINE_SEMANTICS` remains the correct current/live funding
verdict.

## 8. Why current/live ledgers are not `CLEAN_NET_OF_CARRY`

Current/live ledgers are not relabeled as `CLEAN_NET_OF_CARRY`.

The clean label requires, for the evaluated ledger/window:

- arithmetic OK;
- complete source coverage;
- one committed, DB-linked, digest-valid funding source snapshot;
- non-ambiguous sidecar selection;
- source file and canonical row-subset digest agreement;
- DB/window/lane identity agreement;
- independent funding re-sum agreement.

The current/live ledgers do not have receipt-grade proof for those requirements.
Pending sidecars are not enough. Mutable current source CSV state is not enough.
A verifier arithmetic OK result is not enough. Complete source coverage without
a committed DB-linked snapshot is not enough.

## 9. Writer sidecar behavior

The writer sidecar behavior is conservative:

- snapshot emission occurs before durable DB inserts;
- sidecars are written under `<db_dir>/funding_source_snapshots/`;
- explicit `db_path` controls the sidecar directory;
- emission failure aborts before ledger mutation;
- funding coverage aborts do not emit sidecars;
- the current writer emits `write_state=pending`;
- `ledger_batch_id` is not populated by the current pending writer path;
- the pending sidecar is intentionally not clean-carry evidence.

If the later DB commit fails, a sidecar can be orphaned. If multiple sidecars
exist, DB schema v1 has no durable selector to choose one cleanly.

## 10. Verifier snapshot read behavior

The verifier reads sidecars from the evaluated DB directory and classifies them
as diagnostic/provenance evidence.

Observed statuses include:

```txt
missing
present_valid
present_digest_mismatch
present_schema_unsupported
present_payload_invalid
present_db_or_lane_mismatch
present_pending_or_orphaned
present_ambiguous_multiple
```

Snapshot read behavior does not change arithmetic verifier status. Missing,
pending, orphaned, ambiguous, mismatched, invalid, or digest-mismatched
snapshots preserve `CAVEATED_ENGINE_SEMANTICS` for clean-carry decisioning.

## 11. Clean-carry gate behavior

The clean-carry gate is stricter than the older source coverage stamp.

It refuses `CLEAN_NET_OF_CARRY` when any of the following are present:

- arithmetic status is not OK;
- source coverage is not complete;
- source snapshot is missing;
- snapshot digest is mismatched;
- snapshot schema is unsupported or invalid;
- DB/lane/window identity mismatches;
- snapshot is pending or orphaned;
- multiple snapshot sidecars are ambiguous;
- source rows are missing, partial, duplicate, outside tolerance, or open-boundary
  caveated;
- source file or row-subset digests mismatch;
- independent funding re-sum mismatches.

Only the tmp-only synthetic case with complete source coverage, valid committed
snapshot identity, matching digests, arithmetic OK, and re-sum agreement reaches
`CLEAN_NET_OF_CARRY`.

## 12. Independent funding re-sum behavior

The verifier now independently sums `funding.funding_amount` and compares the
result to:

```txt
ledger_state.funding_cum
latest equity_snapshots.funding_cum
```

If those values do not agree within verifier tolerance, the clean-carry gate
adds `funding_resum_mismatch` and refuses `CLEAN_NET_OF_CARRY`.

This is local synthetic verifier proof. It is not a live acceptance result for
current/prod/shadow ledgers.

## 13. Remaining blockers

Remaining blockers:

- writer currently emits `write_state=pending`;
- no committed-state update or DB-linked selector exists;
- no VM read-only acceptance receipt has been run;
- no retroactive snapshot exists for old live batches;
- current/live ledgers must not be relabeled.

These blockers preserve:

```txt
EDGE_UNPROVEN
CAVEATED_ENGINE_SEMANTICS
current/live ledgers are not CLEAN_NET_OF_CARRY
```

## 14. Next recommended implementation decision

Recommendation:

```txt
B. PLAN_DB_LINKED_SNAPSHOT_SELECTOR
```

Rationale:

Before adding more writer mutation logic, decide how a committed ledger batch is
durably linked to exactly one funding source snapshot. The open design question
is whether the selector belongs in `ledger_batches` metadata, a dedicated
snapshot table, or another explicit schema-backed linkage.

This docs-only decision should resolve how to avoid ambiguous sidecars and how a
future verifier proves that a particular committed batch/window selected a
particular snapshot.

## 15. Safety boundaries

This receipt does not:

- claim edge;
- claim profitability;
- claim live `CLEAN_NET_OF_CARRY`;
- claim take-profit readiness;
- claim shorting readiness;
- run a prod writer;
- run a shadow writer;
- run any writer against `/srv`;
- inspect or mutate VM state;
- mutate prod DB, shadow DB, or `forward_obs`;
- refresh data;
- change services or timers;
- install dependencies;
- run migrations;
- edit `.claude/`.

The operative labels remain:

```txt
EDGE_UNPROVEN
CAVEATED_ENGINE_SEMANTICS
current/live ledgers are not CLEAN_NET_OF_CARRY
```

## 16. Verdict

```txt
FUNDING_SOURCE_SNAPSHOT_ACCEPTANCE_RECEIPT_READY_FOR_PR
```
