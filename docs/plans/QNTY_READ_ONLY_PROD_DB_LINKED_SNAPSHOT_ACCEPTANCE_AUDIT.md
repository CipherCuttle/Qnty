# QNTY Read-Only Prod DB-Linked Snapshot Acceptance Audit

## 1. Purpose

Perform a strictly read-only audit of the existing prod timer-created DB-linked
funding source snapshot batch/sidecar observed after the shadow dry run
(`docs/plans` receipt for PR #67). This determines whether the prod timer's
most recent ledger batch has valid, coherent DB-linked snapshot evidence
without running any writer or mutating prod state.

## 2. Scope

Read-only inspection only:

- No writer run (prod or shadow).
- No mutation of prod DB, shadow DB, or `forward_obs`.
- No data refresh, migration, or schema-ensure helper run.
- No systemd/timer changes.
- No dependency installs.
- No WAL checkpoint.
- SQLite accessed via explicit absolute path with a read-only immutable URI
  (`file:...?mode=ro&immutable=1`) and `PRAGMA query_only=ON`.

## 3. VM/repo state

VM repo at `/srv/qnty/repo` was checked read-only prior to inspection:

```txt
## main...origin/main
d4b9e94 docs: add live rollout plan for db-linked snapshot references (#65)
6c1a6a6 docs: add read-only live snapshot status audit (#64)
cf85ade docs: add db-linked snapshot acceptance receipt (#63)
f5d1b92 feat: select funding snapshots from ledger batch references (#62)
8933f22 feat: store snapshot references on ledger batches (#61)
```

Working tree was clean (no local modifications). Compile checks passed for
all four target modules:

```txt
quantbot/paper/db.py                        -> COMPILE_OK
quantbot/paper/funding_source_snapshot.py    -> COMPILE_OK
quantbot/paper/sqlite_writer.py              -> COMPILE_OK
quantbot/paper/sqlite_verify.py              -> COMPILE_OK
```

Local repo (this branch) was cut from `main` at `c8a475c` (PR #67, shadow
db-linked dry run receipt), consistent with the "current known state" in this
task's brief.

## 4. Prod DB target

```txt
/srv/qnty/output/paper_pnl_v1/paper_ledger.db
```

Accessed via `file:` URI with `mode=ro&immutable=1` and `PRAGMA query_only=ON`
for the entire inspection session. `PRAGMA integrity_check` returned `ok`.

## 5. Read-only commands

Executed exactly as specified in the audit brief:

- `git status --short --branch` / `git log --oneline -5` on the VM repo.
- Four `py_compile` checks against the target modules.
- `sha256sum` of the prod DB, taken before and after inspection.
- A read-only Python inspection script (matching the brief verbatim) that
  opens the DB via an immutable read-only URI, reads the latest
  `ledger_batches` row, reads and hashes the referenced sidecar file, and
  calls `validate_funding_source_snapshot_envelope_v1` on the parsed
  envelope.
- `find` listing of sidecar files under
  `/srv/qnty/output/paper_pnl_v1/funding_source_snapshots/`.
- `python -m quantbot.paper.sqlite_verify --help` (informational only).

No writer entry point was imported or invoked at any point.

## 6. Latest prod ledger batch reference

`ledger_batches` row count: **39** (matches the shadow dry run observation).

Latest row (`rowid = 39`):

```txt
funding_source_snapshot_path:            /srv/qnty/output/paper_pnl_v1/funding_source_snapshots/funding_source_snapshot_v1_05db004f04572a5ecb288014d7c411767f1d95c9df0271f0bdb49eb68dfae3ea.json
funding_source_snapshot_sha256:          47ef15d30c0aa383114a1839e6ec73c224dc33506335a36553101f8f4d43ea77
funding_source_snapshot_bundle_sha256:   05db004f04572a5ecb288014d7c411767f1d95c9df0271f0bdb49eb68dfae3ea
funding_source_snapshot_schema_version:  FUNDING_SOURCE_SNAPSHOT_SCHEMA_V1
funding_source_snapshot_write_state:     committed
funding_source_snapshot_created_at:      2026-07-03T16:21:35Z
```

`missing_snapshot_columns`: `[]` — all six required `ledger_batches` columns
are present in the live schema.

## 7. Sidecar file/hash status

- Sidecar path resolves under the expected root
  (`/srv/qnty/output/paper_pnl_v1/funding_source_snapshots/`) — confirmed via
  `expected_root in sidecar.parents`.
- `sidecar_exists`: **True**.
- `sidecar_size_bytes`: 7104.
- `sidecar_mtime`: 2026-07-03 16:21:40 UTC (consistent with the shadow dry
  run's observation of a pre-existing prod sidecar created by the prod
  paper-pnl timer, prior to the 18:56 UTC shadow session start).
- File bytes SHA-256 (`actual_file_sha`):
  `47ef15d30c0aa383114a1839e6ec73c224dc33506335a36553101f8f4d43ea77`
- DB-recorded SHA-256 (`funding_source_snapshot_sha256`):
  `47ef15d30c0aa383114a1839e6ec73c224dc33506335a36553101f8f4d43ea77`
- **`file_sha_matches_db`: True.**

The `find`-based sidecar listing under the expected root shows exactly one
matching sidecar file, with size and timestamp matching the values read by
the inspection script.

## 8. Envelope validation status

- Envelope top-level keys: `snapshot_payload`, `snapshot_sha256`.
- `validate_funding_source_snapshot_envelope_v1(envelope)` was called against
  the parsed envelope and returned an **empty list** (`[]`) — i.e., no
  validation errors reported by the existing verifier function.
- No exception was raised during validation.

## 9. Bundle/schema/write-state status

```txt
bundle_sha_matches_db:        True
schema_version_matches_db:    True
db_write_state_committed:     True
sidecar_write_state_committed: True
```

Payload lane: `{"lane_id": "paper_pnl_v1", "output_dir": "/srv/qnty/output/paper_pnl_v1"}`.
Payload evaluation window: `2026-07-03T00:00:00Z` → `2026-07-03T08:00:00Z`.
Payload reason codes: `[]` (none flagged).

## 10. Funding re-sum/arithmetic status

Read-only aggregate queries against the live prod DB (no writes):

```txt
funding_sum_all (SUM(funding_amount) over `funding`):  1.58617019
latest ledger_state.funding_cum:                       1.586170210203532
latest equity_snapshots.funding_cum:                    1.58617021
```

All three values agree to within ~2e-8, consistent with ordinary
floating-point accumulation noise across independently maintained running
totals, not a material arithmetic discrepancy. This is an observational
consistency check only — it is **not** a full clean-carry determination,
which requires the dedicated verifier.

## 11. Verifier status

`python -m quantbot.paper.sqlite_verify --help` was run as an informational,
read-only probe. It exited with code `0` but produced **no stdout or stderr
output** — no usage text, no argument list, no indication of explicit DB path
handling or read-only behavior.

Per the audit's hard safety rule ("Only run verifier if the source/help
clearly shows explicit DB path and read-only behavior. If unclear, skip and
document skipped"), this is inconclusive. The verifier was **not invoked**
beyond this `--help` probe.

**Verifier status: SKIPPED (help output did not clearly establish safe,
explicit read-only DB-path invocation).**

## 12. Prod DB immutability check

```txt
sha256 before: 5274a1cfbdcdf9810197e3e60ff43d6bd93a2f4ea5c376182314c4d35b53fdd3
sha256 after:  5274a1cfbdcdf9810197e3e60ff43d6bd93a2f4ea5c376182314c4d35b53fdd3
```

Identical — the prod DB file was not mutated during this audit.

## 13. Interpretation

All manual DB-linked snapshot checks pass:

- The latest prod `ledger_batches` row (39 of 39) carries a complete,
  well-formed DB-linked snapshot reference.
- The referenced sidecar file exists under the expected root.
- The sidecar's file bytes SHA-256 exactly matches the DB-recorded SHA-256.
- The envelope parses and passes `validate_funding_source_snapshot_envelope_v1`
  with zero reported errors.
- Bundle hash, schema version, and write-state are coherent between the DB
  row and the sidecar payload, and both report `committed`.
- Funding totals across `funding`, `ledger_state`, and `equity_snapshots`
  agree to within floating-point noise.
- The prod DB file hash is unchanged before and after this audit.

However, the dedicated `sqlite_verify` verifier could not be safely invoked
because its `--help` output did not clearly demonstrate explicit DB-path and
read-only behavior. Per the audit's interpretation rules, this means the
result is **not** a full clean-carry determination — the manual read-only
checks are valid and consistent, but the strict verifier path that would be
required to relabel prod as `CLEAN_NET_OF_CARRY` was not exercised.

## 14. Verdict

```txt
READ_ONLY_PROD_DB_LINKED_SNAPSHOT_AUDIT_DB_SIDECAR_VALID_VERIFIER_SKIPPED
```

No edge claim.
No profitability claim.
EDGE_UNPROVEN remains preserved.
This audit does not run a writer and does not mutate prod DB.
CLEAN_NET_OF_CARRY is only reported if the strict read-only verifier path confirms it; otherwise prod remains CAVEATED_ENGINE_SEMANTICS or verifier-skipped.
