# QNTY Read-Only Live Snapshot Status Audit

## 1. Purpose

Record the current live/prod and shadow SQLite paper ledger status after the
DB-linked funding source snapshot selector chain landed on repository `main`.

This audit is status-only. It does not attempt to make current/live evidence
clean, does not make an edge claim, and does not make a profitability claim.

## 2. Scope

Audited paths:

- Local repo: `/home/swirky/DevHub/repos/Qnty`
- VM repo: `/srv/qnty/repo`
- Prod ledger DB: `/srv/qnty/output/paper_pnl_v1/paper_ledger.db`
- Shadow ledger DB: `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db`
- Forward observation path noted but not read or mutated:
  `/srv/qnty/output/forward_obs_v1`

The local repository was confirmed at the merged selector chain:

- `cf85ade docs: add db-linked snapshot acceptance receipt (#63)`
- `f5d1b92 feat: select funding snapshots from ledger batch references (#62)`
- `8933f22 feat: store snapshot references on ledger batches (#61)`
- `1eb35b0 feat: add ledger batch snapshot reference columns (#60)`
- `da5286e test: specify ledger batch snapshot reference schema (#59)`

The VM repository was read-only inspected and was older than the merged local
chain:

- `fde43a5 docs: add shadow lane dry run plan (#24)`
- `5b86165 docs: add lane writer temp proof receipt (#23)`
- `cb95ff9 docs: add lane config init temp e2e receipt (#22)`
- `c53c6ef Add lane config init wrapper (#21)`
- `8750422 docs: add lane config wrapper plan (#20)`

## 3. Commands Run

Local preflight:

```bash
cd /home/swirky/DevHub/repos/Qnty
git fetch origin
git checkout main
git pull --ff-only origin main
git status --short --branch
git log --oneline -5
git checkout -b docs/read-only-live-snapshot-status-audit
```

Observed local state:

```text
## main...origin/main
?? .claude/
cf85ade docs: add db-linked snapshot acceptance receipt (#63)
f5d1b92 feat: select funding snapshots from ledger batch references (#62)
8933f22 feat: store snapshot references on ledger batches (#61)
1eb35b0 feat: add ledger batch snapshot reference columns (#60)
da5286e test: specify ledger batch snapshot reference schema (#59)
```

VM identity and repository status:

```bash
ssh -i ~/.ssh/hetzner_qnty_key -o IdentitiesOnly=yes viktor@37.27.216.174
hostname
date -u
cd /srv/qnty/repo
git status --short --branch
git log --oneline -5
ls -lah /srv/qnty/output/paper_pnl_v1/paper_ledger.db
ls -lah /srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db
find /srv/qnty/output -maxdepth 3 -type d -name funding_source_snapshots -print
```

Observed VM state:

```text
hostname: ubuntu-4gb-hel1-1-qnty
date -u: Fri Jul  3 12:29:54 UTC 2026
repo status: ## main...origin/main
prod DB: -rw-r--r-- 1 viktor viktor 160K Jul  3 08:21 /srv/qnty/output/paper_pnl_v1/paper_ledger.db
shadow DB: -rw-r--r-- 1 viktor viktor 120K Jul  2 17:09 /srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db
funding_source_snapshots dirs: none found
```

The VM did not have the `sqlite3` CLI installed:

```text
sqlite3: command not found
```

Schema inspection was therefore performed with Python stdlib `sqlite3` using
explicit immutable read-only SQLite URIs and `PRAGMA query_only=ON`:

```text
file:/srv/qnty/output/paper_pnl_v1/paper_ledger.db?mode=ro&immutable=1
file:/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db?mode=ro&immutable=1
```

Sidecar discovery:

```bash
find /srv/qnty/output/paper_pnl_v1 -maxdepth 4 -path '*funding_source_snapshots*' -type f -name 'funding_source_snapshot_v1_*.json' -printf '%p %s bytes\n' 2>/dev/null || true
find /srv/qnty/output/paper_pnl_null_shadow_v0 -maxdepth 4 -path '*funding_source_snapshots*' -type f -name 'funding_source_snapshot_v1_*.json' -printf '%p %s bytes\n' 2>/dev/null || true
```

Verifier help inspection:

```bash
cd /srv/qnty/repo
/srv/qnty/venv/bin/python -m quantbot.paper.sqlite_verify --help || true
```

## 4. Safety Boundaries

Observed safety boundaries:

- No prod writer was run.
- No shadow writer was run.
- No writer was run against `/srv`.
- No prod DB mutation was performed.
- No shadow DB mutation was performed.
- No `forward_obs` mutation was performed.
- No data refresh was run.
- No systemd or timer command was run.
- No dependency installation was performed.
- No migration was run.
- No schema ensure helper was run against live DBs.
- No WAL checkpoint was run.
- No helper or environment path resolution was used for DB paths.
- DB reads used absolute paths and explicit immutable read-only SQLite URIs
  where SQLite access was available.

## 5. Prod DB Schema Status

Prod DB:

```text
/srv/qnty/output/paper_pnl_v1/paper_ledger.db
```

Prod `ledger_batches` columns:

```text
batch_id
created_at
started_at
committed_at
git_sha
prior_watermark_bar_ts
new_watermark_bar_ts
first_event_seq
last_event_seq
event_count
committed_bar_count
paper_engine_version
config_hash
```

Prod `ledger_batches` row count observed read-only: `38`.

Prod status:

```text
live DB schema predates DB-linked snapshot reference columns
therefore live DB-linked selector cannot prove CLEAN_NET_OF_CARRY
CAVEATED_ENGINE_SEMANTICS remains
```

## 6. Shadow DB Schema Status

Shadow DB:

```text
/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db
```

Shadow `ledger_batches` columns:

```text
batch_id
created_at
started_at
committed_at
git_sha
prior_watermark_bar_ts
new_watermark_bar_ts
first_event_seq
last_event_seq
event_count
committed_bar_count
paper_engine_version
config_hash
lane_id
```

Shadow `ledger_batches` row count observed read-only: `14`.

Shadow status:

```text
shadow DB schema predates DB-linked snapshot reference columns
therefore shadow DB-linked selector cannot prove CLEAN_NET_OF_CARRY
CAVEATED_ENGINE_SEMANTICS remains
```

## 7. Snapshot Sidecar Discovery

No `funding_source_snapshots` directories were found under
`/srv/qnty/output` with `-maxdepth 3`.

No `funding_source_snapshot_v1_*.json` sidecars were found under:

- `/srv/qnty/output/paper_pnl_v1`
- `/srv/qnty/output/paper_pnl_null_shadow_v0`

## 8. Ledger Batch DB-Linked Reference Status

The DB-linked funding source snapshot reference columns were absent from both
audited ledgers:

```text
funding_source_snapshot_path
funding_source_snapshot_sha256
funding_source_snapshot_bundle_sha256
funding_source_snapshot_schema_version
funding_source_snapshot_write_state
funding_source_snapshot_created_at
```

Because these columns do not exist in either audited live/prod or shadow
`ledger_batches` table, no latest committed batch row can carry a DB-linked
funding source snapshot reference in the audited DBs.

Current live/prod and shadow ledgers therefore do not have DB-linked committed
funding source snapshot references.

## 9. Verifier Status

Verifier execution was skipped for read-only safety.

Reason: the required help inspection command returned no help text or explicit
evidence that the VM verifier supports an explicit DB path read-only mode for
this audit surface. Since support could not be confirmed from help output, no
verifier was run.

## 10. Interpretation

`EDGE_UNPROVEN` remains preserved.

Current/live evidence remains `CAVEATED_ENGINE_SEMANTICS`.

Current/live ledgers are not relabeled as `CLEAN_NET_OF_CARRY`.

No edge claim.

No profitability claim.

No writer, migration, DB mutation, refresh, timer, or `forward_obs` mutation was
performed.

## 11. Verdict

`READ_ONLY_LIVE_SNAPSHOT_STATUS_AUDIT_CAVEATED`
