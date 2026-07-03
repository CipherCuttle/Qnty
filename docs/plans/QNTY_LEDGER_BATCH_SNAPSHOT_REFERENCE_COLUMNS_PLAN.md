# QNTY Ledger Batch Snapshot Reference Columns Plan

Task: `PLAN_LEDGER_BATCH_SNAPSHOT_REFERENCE_COLUMNS`

## 1. Purpose

Create a docs-only design decision for making SQLite `ledger_batches` the
deterministic selector authority for funding source snapshot sidecars.

Design conclusion:

```txt
DB is selector authority.
Sidecar is evidence payload.
Hashes bind DB <-> sidecar.
Old/current live ledgers stay caveated.
```

This plan does not implement code, run writers, run migrations, mutate any DB,
or relabel current/live ledgers.

## 2. Context

The funding source snapshot work already moved QNTY toward receipt-grade
funding/carry evidence by adding deterministic JSON sidecars and strict verifier
refusal modes. The remaining decision is how a verifier selects exactly one
sidecar for an evaluated committed ledger batch.

SQLite gives atomic commit guarantees inside a database transaction. The JSON
sidecar lives outside SQLite. A sidecar-only selector cannot fully remove the
DB/file dual-write ambiguity because the sidecar and DB row cannot be committed
as one SQLite unit.

The safest v1 design is a local transactional-outbox-style pattern:

```txt
- DB transaction stores durable selector/reference.
- Sidecar stores content-addressed provenance payload.
- Verifier binds them by path + snapshot sha + bundle sha + schema + lane/window identity.
- If any part is missing, pending, ambiguous, or mismatched, clean-carry is refused.
```

Current state remains:

```txt
EDGE_STATUS: EDGE_UNPROVEN
current/live funding verdict: CAVEATED_ENGINE_SEMANTICS
current/live ledgers are not CLEAN_NET_OF_CARRY
```

## 3. Current Implemented State

Already implemented:

```txt
- funding source snapshot schema/spec
- pure funding source snapshot builder
- SQLite writer emits pending snapshot sidecars
- SQLite verifier reads snapshot sidecars
- strict verifier CLEAN_NET_OF_CARRY gate exists
- acceptance receipt merged
- tmp-only synthetic tests can return CLEAN_NET_OF_CARRY only when committed snapshot identity, complete source coverage, digest checks, arithmetic OK, and re-sum proof all exist
```

Observed repository shape:

- `ledger_batches` currently records batch identity, provenance, watermarks,
  event counts, `config_hash`, and nullable `lane_id`.
- The snapshot builder produces deterministic payloads with
  `schema_version`, `source_bundle_sha256`, `write_state`, DB/window/lane
  metadata, and an envelope `snapshot_sha256`.
- The writer emits a JSON sidecar under
  `<db_dir>/funding_source_snapshots/` before durable DB inserts and currently
  uses `write_state=pending`.
- The verifier reads sidecars as diagnostic evidence, refuses ambiguous
  directory-only selection, and keeps arithmetic status separate from
  clean-carry decisioning.

## 4. Remaining Selector Problem

Known blocker:

```txt
writer emits write_state=pending
no committed-state update exists
no durable DB-linked selector exists
multiple sidecars can remain ambiguous
old/current live ledgers must not be relabeled
```

Without a durable DB selector, clean-mode can only infer candidates from the
sidecar directory. That leaves open these unsafe states:

- multiple sidecars exist for one DB directory;
- a pending/orphaned sidecar exists after a later DB failure;
- a sidecar has plausible hashes but no committed batch link;
- a valid-looking sidecar is for a different lane, DB path, or evaluation
  window;
- current/live ledgers lack historical committed snapshot references.

## 5. Why Sidecar-Only Is Insufficient

A sidecar-only selector is insufficient because JSON files are outside SQLite's
transaction boundary.

Sidecar atomic rename can make the JSON write locally well-formed, but it does
not atomically bind that JSON file to the `ledger_batches` row. The writer can
successfully write a sidecar and then fail the DB transaction. The writer can
commit the DB and then fail the committed sidecar rewrite. Directory scans also
cannot distinguish the intended batch selector when more than one matching
sidecar is present.

Therefore a sidecar-only selector cannot fully solve the DB/file dual-write
ambiguity. It remains useful as evidence payload, but not as selector authority.

## 6. Why `ledger_batches` Should Be Selector Authority

`ledger_batches` is the correct v1 selector authority because it is the durable
row that represents the committed batch. Storing the snapshot reference on that
same row lets the writer persist the selector inside the same SQLite transaction
as the batch write, ledger events, typed rows, state update, and commit metadata.

This makes the verifier flow deterministic:

```txt
1. Select the evaluated/latest ledger_batches row.
2. Read the snapshot reference fields on that row.
3. Load exactly that sidecar.
4. Bind DB <-> sidecar with path, snapshot sha, bundle sha, schema, lane, DB, batch, and window checks.
5. Refuse clean-carry on any absence, mismatch, pending state, ambiguity, or arithmetic/re-sum failure.
```

The sidecar remains the provenance payload. The DB row decides which payload is
eligible for the evaluated batch.

## 7. Why A Dedicated Snapshot Table Is Not Needed For V1

A dedicated snapshot table is not needed for v1 because the current relationship
is one committed `ledger_batches` row to at most one funding source snapshot
reference.

Adding a table first would introduce extra joins, new uniqueness rules, and
multi-row consistency invariants before the product needs them. The v1 problem
is not snapshot inventory management. It is deterministic selection for a single
evaluated batch.

A dedicated table can be revisited later if QNTY needs:

- multiple snapshot artifacts per batch;
- historical rewrite/audit trails for failed state transitions;
- snapshot reuse across batches;
- asynchronous reconciliation workers;
- richer outbox processing state than a few batch-level reference fields.

Until then, nullable columns on `ledger_batches` are the smallest durable schema
surface that solves selector ambiguity.

## 8. Proposed Nullable `ledger_batches` Columns

Recommended v1 columns:

```txt
funding_source_snapshot_path TEXT NULL
funding_source_snapshot_sha256 TEXT NULL
funding_source_snapshot_bundle_sha256 TEXT NULL
funding_source_snapshot_schema_version TEXT NULL
funding_source_snapshot_write_state TEXT NULL
funding_source_snapshot_created_at TEXT NULL
```

Optional later columns if implementation proves they reduce verifier work or
receipt ambiguity:

```txt
funding_source_snapshot_payload_sha256 TEXT NULL
funding_source_snapshot_reason_codes_json TEXT NULL
```

Column intent:

- `funding_source_snapshot_path`: exact path selected by the DB row.
- `funding_source_snapshot_sha256`: SHA-256 of the sidecar envelope or file
  content as defined by the implementation contract.
- `funding_source_snapshot_bundle_sha256`: payload source bundle digest.
- `funding_source_snapshot_schema_version`: expected snapshot schema version.
- `funding_source_snapshot_write_state`: DB-side state observed or intended for
  the selected snapshot.
- `funding_source_snapshot_created_at`: timestamp for snapshot reference
  creation.
- `funding_source_snapshot_payload_sha256`: optional direct payload digest if
  the file hash and envelope `snapshot_sha256` need separate names.
- `funding_source_snapshot_reason_codes_json`: optional cached payload reason
  codes for reporting only, not a substitute for verifier recomputation.

All fields are nullable. `NULL` means no committed DB-linked snapshot reference
exists for that batch.

## 9. Writer State Machine

Recommended writer state machine:

```txt
1. Run engine in memory.
2. Run funding source coverage gate.
3. Build snapshot payload.
4. Write sidecar atomically as write_state=pending.
5. Begin SQLite transaction.
6. Insert ledger batch + ledger rows + related state.
7. Store snapshot path/hash/bundle/schema/write_state on ledger_batches inside the same transaction.
8. Commit SQLite transaction.
9. Atomically rewrite/rename sidecar as write_state=committed.
10. Optionally update ledger_batches funding_source_snapshot_write_state from pending -> committed in a small follow-up transaction.
```

The important invariant is step 7: the durable selector/reference is written to
`ledger_batches` inside the same transaction as the durable batch mutation.

The optional step 10 must be designed fail-closed. A DB row that still says
`pending` after the sidecar rewrite is not clean evidence unless a later
implementation explicitly defines and tests a different rule.

## 10. Verifier Selector Rules

Verifier selector rules:

```txt
- clean-carry never selected by directory scan alone
- verifier starts from latest/evaluated ledger_batches row
- if snapshot reference fields are NULL, refuse clean
- load exact referenced sidecar
- recompute sidecar sha256
- compare to DB snapshot sha256
- validate envelope digest
- compare source bundle sha
- compare schema version
- compare lane/db/evaluation window/batch identity
- require committed write_state
- require complete source coverage
- require independent funding re-sum match
```

Additional v1 selector details:

- unrelated sidecars in the directory are ignored for clean-mode when the DB row
  has an exact reference;
- the selected sidecar must still be validated, not trusted from the DB fields
  alone;
- a missing referenced file refuses clean;
- a digest mismatch refuses clean;
- an unsupported schema refuses clean;
- lane, DB path, output directory, evaluation window, batch watermark, and batch
  identity mismatch refuse clean;
- if the verifier observes duplicate or multiple matching DB-linked references
  for the same evaluated batch/window identity, it refuses clean rather than
  picking one.

## 11. Atomicity And Dual-Write Failure Handling

Failure handling:

```txt
pending sidecar write fails:
  abort before DB mutation

DB transaction fails:
  leave sidecar pending/orphaned; verifier refuses clean

DB commit succeeds but committed sidecar rewrite fails:
  DB can point to pending snapshot; verifier refuses clean

sidecar committed rewrite succeeds but DB write_state update fails:
  verifier requires both DB reference and sidecar payload to agree; refuse clean unless explicitly designed otherwise

multiple sidecars exist:
  verifier uses DB reference hash/path as selector; unrelated sidecars ignored for clean-mode

DB references missing file:
  refuse clean

DB references digest mismatch:
  refuse clean

old batch has NULL reference fields:
  CAVEATED_ENGINE_SEMANTICS, never retroactive clean
```

This is intentionally fail-closed. The plan accepts that DB/file dual writes can
land in partial states. The verifier's job is to detect those states and preserve
the caveat.

## 12. Clean-Carry Implications

This design can support `CLEAN_NET_OF_CARRY` for future writer-created batches
only after implementation and successful verification.

It does not support retroactive `CLEAN_NET_OF_CARRY` for old/current live
ledgers unless a valid historical snapshot/reference exists, which currently it
does not.

Current/live ledgers remain `CAVEATED_ENGINE_SEMANTICS`.

`EDGE_UNPROVEN` remains unchanged.

Clean-carry still requires all existing strict gates:

- arithmetic status OK;
- complete source coverage;
- committed DB-linked snapshot reference;
- digest-valid sidecar and payload;
- source bundle agreement;
- source file and row-subset digest agreement;
- DB/window/lane/batch identity agreement;
- independent funding re-sum match;
- no pending, orphaned, ambiguous, missing, or mismatched evidence.

## 13. Migration/Backward Compatibility

The implementation PR should add the schema change additively with nullable
columns. Existing rows with `NULL` reference fields must remain readable and
caveated.

Backward compatibility rules:

- old DBs without the columns must remain readable or be migrated safely before
  verification;
- adding columns must not rewrite historical batch semantics;
- old rows with `NULL` reference fields are not clean evidence;
- no retroactive update should manufacture snapshot references for old/current
  live ledgers;
- a missing column, missing reference, or `NULL` field maps to a clean-carry
  refusal and preserves `CAVEATED_ENGINE_SEMANTICS`.

This plan does not run a migration.

## 14. Historical/Current Live Ledger Treatment

Historical and current/live ledgers must remain caveated unless they already
have a valid committed DB-linked historical snapshot/reference and pass all
strict verifier gates.

Current/live evidence remains:

```txt
EDGE_UNPROVEN
CAVEATED_ENGINE_SEMANTICS
current/live ledgers are not CLEAN_NET_OF_CARRY
```

Old/current live ledgers must not be relabeled by assertion, by sidecar directory
presence, by arithmetic verifier `OK`, or by mutable current source CSV state.

## 15. Tests Required For Next PR

Tests required for the next implementation PR:

```txt
1. migration/additive schema creates nullable fields
2. old DBs without fields remain readable or are migrated safely
3. writer stores snapshot reference on ledger_batches inside DB transaction
4. pending sidecar write failure aborts before DB mutation
5. DB transaction failure leaves pending/orphaned sidecar and verifier refuses clean
6. DB commit success + committed sidecar rewrite success allows synthetic clean-carry
7. committed sidecar rewrite failure refuses clean
8. missing referenced sidecar refuses clean
9. referenced sidecar sha mismatch refuses clean
10. source bundle sha mismatch refuses clean
11. multiple unrelated sidecars do not confuse verifier when DB reference is exact
12. multiple matching/duplicate references refuse clean
13. old ledger batch with NULL snapshot fields remains CAVEATED_ENGINE_SEMANTICS
14. manual explicit --db-path stores sidecar under db_path.parent and DB reference points there
15. independent re-sum mismatch still refuses clean
```

Tests should stay local and synthetic unless a later receipt explicitly
authorizes read-only VM evidence collection. No `/srv`, prod DB, shadow DB,
`forward_obs`, service, timer, data-refresh, or writer mutation is authorized by
this docs-only plan.

## 16. Proposed Implementation PR Sequence

Recommended PR sequence:

```txt
1. TEST_ONLY_LEDGER_BATCH_SNAPSHOT_REFERENCE_SCHEMA
2. IMPLEMENT_LEDGER_BATCH_SNAPSHOT_REFERENCE_COLUMNS
3. IMPLEMENT_WRITER_SNAPSHOT_REFERENCE_TRANSACTION
4. IMPLEMENT_VERIFIER_DB_LINKED_SNAPSHOT_SELECTOR
5. ADD_DB_LINKED_SNAPSHOT_ACCEPTANCE_RECEIPT
```

Sequence intent:

- First pin the schema and refusal contract with tests.
- Then add nullable schema fields safely.
- Then store the DB selector in the writer transaction.
- Then make the verifier select by DB reference instead of directory scan alone.
- Finally publish a receipt that reports future evidence without relabeling
  old/current live ledgers.

## 17. Safety Boundaries

This plan is docs-only.

This plan does not:

- edit production code;
- edit tests;
- edit fixtures;
- run prod writer;
- run shadow writer;
- run any writer against `/srv`;
- SSH to VM;
- mutate prod DB;
- mutate shadow DB;
- mutate `forward_obs`;
- run data refresh;
- change systemd/timers;
- install dependencies;
- run migrations;
- edit `.claude/`;
- make an edge claim;
- make a profitability claim;
- relabel current/live ledgers as `CLEAN_NET_OF_CARRY`.

The operative labels remain:

```txt
EDGE_UNPROVEN
CAVEATED_ENGINE_SEMANTICS
current/live ledgers are not CLEAN_NET_OF_CARRY
```

## 18. Verdict

```txt
LEDGER_BATCH_SNAPSHOT_REFERENCE_COLUMNS_PLAN_READY_FOR_PR
```
