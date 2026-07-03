# QNTY Live Schema Ensure Receipt

## 1. Purpose

Task: `ADD_LIVE_SCHEMA_ENSURE_RECEIPT`

Record the explicit live paper DB schema ensure that added or confirmed the
nullable `funding_source_snapshot_*` columns on the prod and shadow SQLite
paper ledgers.

This receipt preserves the caveat boundary before any writer dry run.

## 2. Scope

This is a docs-only receipt for a VM operation that already completed after a
code-only deploy.

In scope:

- record the reported target DBs;
- record the reported backup artifacts;
- record the schema ensure result;
- record prod and shadow postcheck facts;
- record sidecar absence;
- preserve safety boundaries and current/live caveats.

Out of scope for this receipt:

- VM access;
- prod DB mutation;
- shadow DB mutation;
- writer execution;
- migration execution;
- schema ensure helper execution;
- data refresh;
- timer or systemd changes;
- `forward_obs` mutation;
- `.claude/` changes;
- edge claims;
- profitability claims.

## 3. Preconditions

The explicit DB schema ensure was run on the VM after a code-only deploy.

Reported VM repo state at execution time:

```txt
/srv/qnty/repo
clean at d4b9e94 docs: add live rollout plan for db-linked snapshot references (#65)
```

This receipt does not independently access the VM, rerun the ensure, or mutate
any live DB.

## 4. Target DBs

The schema ensure targeted these SQLite paper ledgers:

```txt
/srv/qnty/output/paper_pnl_v1/paper_ledger.db
/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db
```

## 5. Backup artifacts

Backups reported before the ensure:

```txt
/srv/qnty/output/paper_pnl_v1/paper_ledger.db.before_snapshot_columns.20260703T133855Z.bak
/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db.before_snapshot_columns.20260703T133855Z.bak
```

## 6. Schema ensure result

Reported result:

```txt
VERDICT: LIVE_PAPER_DB_SNAPSHOT_COLUMNS_ENSURED
```

Immutable pre-observation found the six required columns were already present
on both DBs, so the earlier `snapshot columns: []` state was stale at execution
time.

`ensure_ledger_batch_snapshot_reference_columns(con)` was run once per target
DB.

Before and after column lists were identical and complete.

Required nullable snapshot reference columns:

```txt
funding_source_snapshot_path TEXT NULL
funding_source_snapshot_sha256 TEXT NULL
funding_source_snapshot_bundle_sha256 TEXT NULL
funding_source_snapshot_schema_version TEXT NULL
funding_source_snapshot_write_state TEXT NULL
funding_source_snapshot_created_at TEXT NULL
```

## 7. Prod DB postcheck

Prod DB:

```txt
/srv/qnty/output/paper_pnl_v1/paper_ledger.db
```

Reported postcheck:

```txt
ledger_batches rows: 38
missing required snapshot columns: []
spec_mismatches: {}
all six required snapshot columns are TEXT NULL
null_counts for all six required columns = 38
```

The prod historical rows remain NULL for the snapshot reference fields.

## 8. Shadow DB postcheck

Shadow DB:

```txt
/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db
```

Reported postcheck:

```txt
ledger_batches rows: 14
missing required snapshot columns: []
spec_mismatches: {}
all six required snapshot columns are TEXT NULL
null_counts for all six required columns = 14
```

The shadow historical rows remain NULL for the snapshot reference fields.

## 9. Sidecar check

Reported sidecar check:

```txt
no funding_source_snapshot_v1_*.json files found
no funding_source_snapshots directories found under /srv/qnty/output
```

The schema ensure did not create sidecars.

## 10. What was not done

Reported non-actions:

- no prod writer;
- no shadow writer;
- no `/srv` writer;
- no data refresh;
- no timer/systemd change;
- no dependency install;
- no WAL checkpoint;
- no `forward_obs` mutation;
- no data backfill;
- no sidecar creation;
- no old/current row relabeling.

## 11. Interpretation

`EDGE_UNPROVEN` is preserved.

Current/live evidence remains `CAVEATED_ENGINE_SEMANTICS`.

Current/live ledgers are not `CLEAN_NET_OF_CARRY`.

The newly confirmed nullable columns are necessary schema support for future
DB-linked snapshot references. They are not, by themselves, clean funding/carry
evidence.

NULL historical snapshot reference fields do not prove clean carry and must not
retroactively relabel old or current rows.

No edge claim.

No profitability claim.

## 12. Next safe step

```txt
SHADOW_ONLY_DB_LINKED_SNAPSHOT_DRY_RUN
```

This requires separate explicit authorization because it runs a writer against
the shadow paper DB.

## 13. Verdict

```txt
LIVE_PAPER_DB_SNAPSHOT_COLUMNS_ENSURED
```
