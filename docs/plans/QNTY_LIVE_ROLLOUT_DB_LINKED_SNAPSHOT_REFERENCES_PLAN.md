# QNTY Live Rollout DB-Linked Snapshot References Plan

## 1. Purpose

Plan a safe docs-only rollout for bringing the DB-linked funding source
snapshot selector chain to the VM/live paper environment after the read-only
audit found that the VM repo and live DBs are older than the local
implementation.

This plan does not deploy code, mutate DBs, run writers, run migrations,
refresh data, change timers, touch `forward_obs`, or relabel current/live
ledgers.

## 2. Current live audit facts

Read-only audit facts used:

- PR #64 merged the read-only live snapshot status audit.
- Local `main` is `6c1a6a6` or newer.
- VM repo `/srv/qnty/repo` was clean but old, ending at
  `fde43a5 docs: add shadow lane dry run plan (#24)`.
- Prod DB `/srv/qnty/output/paper_pnl_v1/paper_ledger.db` exists, was 160K,
  was modified Jul 3 08:21, and `ledger_batches` had 38 rows.
- Shadow DB `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db`
  exists, was 120K, was modified Jul 2 17:09, and `ledger_batches` had 14
  rows with older `lane_id` only.
- Neither audited live DB had the `funding_source_snapshot_*` columns.
- No `funding_source_snapshots` directories were found.
- No `funding_source_snapshot_v1_*.json` sidecars were found.

Implemented locally but not deployed to the VM:

- PR #60: ledger batch snapshot reference columns.
- PR #61: writer stores snapshot references on `ledger_batches`.
- PR #62: verifier selects snapshots from ledger batch references.
- PR #63: DB-linked snapshot acceptance receipt.
- PR #64: read-only live snapshot status audit.

## 3. Why no live clean-carry claim exists

No live `CLEAN_NET_OF_CARRY` claim exists because the audited live/prod and
shadow DBs lack the DB-linked selector columns and have no committed snapshot
sidecars.

`STATUS_OK` remains an arithmetic/accounting status only. It is not a clean
funding/carry label.

`EDGE_UNPROVEN` remains preserved.

Current/live evidence remains `CAVEATED_ENGINE_SEMANTICS`.

Current/live ledgers are not `CLEAN_NET_OF_CARRY`.

No edge claim.

No profitability claim.

Old historical rows with `NULL` snapshot references remain
`CAVEATED_ENGINE_SEMANTICS` and must not be retroactively relabeled. Only
future writer-created batches after a separately authorized schema update can
possibly carry DB-linked committed snapshot references.

## 4. Rollout principle

Separate code rollout from DB mutation and separate both from writer execution.

Updating VM code alone is not enough because existing live DBs lack
`funding_source_snapshot_*` columns. Running new writer code against old DBs
should fail closed or remain caveated if columns are missing. The live DB
additive schema update is a real DB mutation and needs separate explicit
authorization.

Recommended sequence:

```txt
1. DEPLOY_VM_CODE_ONLY_NO_DB_MUTATION
2. READ_ONLY_VM_CODE_POST_DEPLOY_CHECK
3. PLAN_OR_RUN_EXPLICIT_DB_SCHEMA_ENSURE_FOR_LIVE_PAPER_DBS
4. SHADOW_ONLY_DB_LINKED_SNAPSHOT_DRY_RUN
5. READ_ONLY_SHADOW_DB_LINKED_ACCEPTANCE_AUDIT
6. PROD_PAPER_DB_LINKED_SNAPSHOT_ROLLOUT
```

## 5. Phase A: VM code update only

Goal: update `/srv/qnty/repo` to current `main` without touching DBs, writers,
services, timers, data refresh, or `forward_obs`.

Allowed later only with explicit authorization:

- confirm VM repo is clean;
- fast-forward VM `main` to `origin/main`;
- inspect recent commits;
- compile/import the DB, writer, and verifier modules.

Not allowed in Phase A:

- no writer execution;
- no schema ensure;
- no DB write;
- no prod/shadow ledger mutation;
- no service or timer change.

Phase A exit evidence:

- VM repo head matches expected current `main`;
- VM repo remains clean after code update;
- compile/import checks pass;
- DB file mtimes and read-only schema facts are not changed by code update.

## 6. Phase B: read-only post-code-update verification

Goal: prove the VM code update is present and inspect live DB schemas without
mutation.

Use Python stdlib SQLite read-only immutable URIs because the prior audit found
the VM did not have the `sqlite3` CLI.

Required read-only checks:

- `git status --short --branch` on VM;
- `git log --oneline -5` on VM;
- `python -m py_compile` for `quantbot/paper/db.py`,
  `quantbot/paper/sqlite_writer.py`, and `quantbot/paper/sqlite_verify.py`;
- immutable read-only `PRAGMA table_info(ledger_batches)` for prod and shadow
  DBs;
- no writer process invoked;
- no schema helper invoked;
- no DB mtime change attributable to verification.

Expected Phase B result before Phase C: prod and shadow DBs still lack
`funding_source_snapshot_*` columns and therefore remain
`CAVEATED_ENGINE_SEMANTICS`.

## 7. Phase C: explicit DB additive schema migration/ensure

Goal: add the six nullable `ledger_batches` snapshot reference columns to live
paper DBs only after separate explicit DB-mutation authorization.

Required columns:

```txt
funding_source_snapshot_path TEXT
funding_source_snapshot_sha256 TEXT
funding_source_snapshot_bundle_sha256 TEXT
funding_source_snapshot_schema_version TEXT
funding_source_snapshot_write_state TEXT
funding_source_snapshot_created_at TEXT
```

Phase C must be authorized separately from code deployment. It must begin with
backups or read-only DB copies for both prod and shadow DBs, followed by
read-only schema and row-count checks.

Rules:

- schema update is additive only;
- no historical row rewrite;
- no manufactured snapshot references;
- old rows remain `NULL` for the new fields;
- `NULL` snapshot references preserve `CAVEATED_ENGINE_SEMANTICS`;
- schema ensure must stop if observed columns differ from the expected contract;
- backup/copy failure blocks schema mutation.

Phase C exit evidence:

- backup/copy receipts exist before mutation;
- six expected columns exist after mutation;
- existing row counts match pre-mutation counts;
- historical rows have `NULL` snapshot references;
- no writer has run yet.

## 8. Phase D: shadow-only writer dry run

Goal: after Phase C acceptance, run only the shadow/paper null lane first under
separate explicit authorization.

Phase D is intentionally shadow-only. It must not mutate prod DB, prod output,
prod `forward_obs`, timers, or services.

Expected behavior:

- writer creates a future shadow batch only;
- sidecar path is under
  `/srv/qnty/output/paper_pnl_null_shadow_v0/funding_source_snapshots`;
- DB row references the exact sidecar path/hash/bundle/schema/write state;
- committed references can be evaluated by the verifier;
- missing, pending, mismatched, duplicate, or outside-directory references remain
  `CAVEATED_ENGINE_SEMANTICS`.

No writer command is included in this docs-only plan. A later separate
authorization must provide exact shadow command, frozen input paths, and
one-shot stop rules.

## 9. Phase E: prod paper writer continuation

Goal: continue the prod paper writer only after shadow DB-linked acceptance is
acceptable and a separate prod authorization is granted.

Prod rollout remains blocked until:

- VM code update is accepted;
- prod and shadow schema ensure is separately authorized and verified;
- shadow-only writer dry run creates acceptable DB-linked evidence;
- read-only shadow acceptance audit confirms sidecar + DB refs + verifier
  status;
- operator explicitly authorizes prod continuation.

Prod writer continuation must not retroactively clean old/current rows. It can
only create future batches that may carry DB-linked committed snapshot
references.

No prod writer command is included in this docs-only plan. A later separate
authorization must provide exact prod command, frozen input expectations, and
stop rules.

## 10. Phase F: read-only acceptance receipt

Goal: publish a read-only receipt after the authorized rollout steps have
completed.

The receipt should inspect:

- VM repo head and cleanliness;
- prod and shadow schema columns;
- row counts before and after authorized schema ensure;
- sidecar directory paths;
- selected `ledger_batches` DB references;
- sidecar file-byte hashes;
- bundle/schema/write-state agreement;
- verifier DB-linked selector status;
- funding clean-carry decision and reason codes.

The receipt must preserve:

```txt
EDGE_UNPROVEN
CAVEATED_ENGINE_SEMANTICS for current/live evidence until a future audited batch satisfies every gate
current/live historical rows are not CLEAN_NET_OF_CARRY by retroactive assertion
```

## 11. Stop conditions

Stop immediately if any of these occur:

- VM repo dirty;
- VM main diverges unexpectedly;
- local main not pushed;
- tests/py_compile fail on VM;
- live DB backup/copy cannot be made before schema mutation;
- schema columns differ from expected;
- sqlite read-only check unavailable;
- writer attempts to mutate before authorization;
- sidecar path outside `db_path.parent/funding_source_snapshots`;
- verifier cannot confirm DB-linked reference status.

## 12. Rollback / recovery

For code-only deploy issues before DB mutation, stop all rollout phases and
restore the VM repo through a separately authorized operator recovery step. Do
not run writers as a recovery action.

For schema ensure issues, prefer restoring from the pre-mutation DB backup/copy
instead of attempting ad hoc column surgery. Preserve the original DB files and
all receipts needed to prove what changed.

For shadow writer issues, stop before prod rollout. Preserve the shadow DB,
sidecar files, command transcript, and verifier output for read-only diagnosis.
Do not clean or rewrite evidence unless a later explicit recovery task
authorizes it.

For prod writer issues, stop timers/services if separately authorized by the
operator, preserve DB and sidecar state, and perform read-only diagnosis first.
Do not relabel prior rows.

## 13. Safety boundaries

This plan is docs-only.

This plan does not:

- edit production code;
- edit tests;
- edit fixtures;
- SSH to VM;
- pull VM repo;
- mutate prod DB;
- mutate shadow DB;
- mutate `forward_obs`;
- run prod writer;
- run shadow writer;
- run any writer against `/srv`;
- run data refresh;
- change systemd/timers;
- install dependencies;
- run migrations;
- touch `.claude/`;
- make an edge claim;
- make a profitability claim;
- relabel current/live ledgers as `CLEAN_NET_OF_CARRY`.

Operative labels:

```txt
EDGE_UNPROVEN
CAVEATED_ENGINE_SEMANTICS
current/live ledgers are not CLEAN_NET_OF_CARRY
```

## 14. Commands to run later, gated by authorization

These are future gated commands, not run in this docs task.

Code-only VM deploy commands:

```bash
ssh -i ~/.ssh/hetzner_qnty_key -o IdentitiesOnly=yes viktor@37.27.216.174
cd /srv/qnty/repo
git status --short --branch
git fetch origin
git checkout main
git pull --ff-only origin main
git log --oneline -5
python -m py_compile quantbot/paper/db.py
python -m py_compile quantbot/paper/sqlite_writer.py
python -m py_compile quantbot/paper/sqlite_verify.py
```

Read-only DB schema check commands:

```bash
python - <<'PY'
import sqlite3
for path in [
    "/srv/qnty/output/paper_pnl_v1/paper_ledger.db",
    "/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db",
]:
    uri = f"file:{path}?mode=ro&immutable=1"
    con = sqlite3.connect(uri, uri=True)
    con.execute("PRAGMA query_only=ON")
    cols = [r[1] for r in con.execute("PRAGMA table_info(ledger_batches)").fetchall()]
    print(path)
    print([c for c in cols if c.startswith("funding_source_snapshot_")])
    con.close()
PY
```

No DB migration commands are included here. Phase C requires a separate
DB-mutation authorization with backup/copy receipts and exact operator
commands.

No writer commands are included here. Phase D and Phase E require separate
writer authorizations with exact lane, DB path, input, and stop-rule details.

## 15. Expected outcomes

Expected outcome after Phase A and Phase B:

- VM code is current;
- DBs are not mutated;
- current/live evidence remains `CAVEATED_ENGINE_SEMANTICS`;
- no live `CLEAN_NET_OF_CARRY` claim exists.

Expected outcome after Phase C, if separately authorized:

- prod and shadow DBs have the six nullable snapshot reference columns;
- historical rows remain `NULL`;
- old/current rows remain caveated;
- no writer-created DB-linked reference exists until a writer is separately
  authorized.

Expected outcome after Phase D, if separately authorized:

- shadow-only future batch may carry a DB-linked committed snapshot reference;
- read-only verifier can select the exact sidecar from `ledger_batches`;
- any missing/pending/mismatched/ambiguous evidence remains caveated.

Expected outcome after Phase E, if separately authorized:

- prod future batches may begin carrying DB-linked committed snapshot references;
- historical/current rows before rollout remain caveated;
- any clean-carry label requires full verifier acceptance on a future audited
  batch.

## 16. Verdict

`LIVE_ROLLOUT_DB_LINKED_SNAPSHOT_REFERENCES_PLAN_READY_FOR_PR`
