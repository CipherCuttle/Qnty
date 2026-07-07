# QNTY Funding Source Real-DB Recommit Plan

Plan for a future, explicitly-approved recommit of the funding-source snapshot
into the **real** shadow DB, now that the PR #99 metadata-aligned **copied**-DB
dry run drove the DB-linked full-ledger clean-carry gate to `CLEAN_NET_OF_CARRY`.

This document is **plan-only**. It authorizes nothing. It records the exact
execution path, safety gates, backup/rollback, pre/post hashes, verifier commands,
acceptance criteria, stop conditions, and promotion boundaries so a later,
separately-approved execution task can run without improvising.

## 1. Status Boundary

- This is a **plan only**. No execution occurs in this PR.
- No real prod/shadow DB mutation in this PR.
- No official verifier report overwrite in this PR.
- No writer / trader / live run.
- No backfill of historical rows.
- No edge, profitability, statistical-significance, live-readiness, shorting, or
  deployment claims.
- `EDGE_UNPROVEN` is preserved.
- `BLOCK_LIVE_INTEGRATION` is preserved.
- Real full-ledger `CAVEATED_ENGINE_SEMANTICS` remains until a future,
  explicitly-approved real-DB-linked verifier run proves otherwise. The PR #99
  copied-DB result does **not** change the real shadow DB label.
- `GO` / `PASSED` / `SURVIVED` / `CLEAN_NET_OF_CARRY` mean "not killed by this
  gate", not trading approval.

## 2. Why This Plan Exists

Evidence chain that makes a real-DB recommit *plannable* (but not yet authorized):

- **PR #92** (`docs: diagnose funding source digest window mismatch`, merge SHA
  `0e6c96ae0d044c17348747dc8cdcf6918a8e7344`) diagnosed the real committed shadow
  snapshot's two independent provenance gaps: a **stale source digest**
  (`funding_source_file_digest_mismatch` —
  `CURRENT_SOURCE_FILES_CHANGED_AFTER_SNAPSHOT` /
  `COMMITTED_SNAPSHOT_DIGEST_STALE`, source CSVs refreshed after commit) and a
  **full-ledger window mismatch** (`funding_source_snapshot_window_mismatch` —
  `SNAPSHOT_WINDOW_DOES_NOT_COVER_LEDGER`; the committed snapshot is batch-scoped,
  not full-ledger). Arithmetic / resum / coverage were already OK.
- **PR #95** (`docs: record funding source snapshot tmp rebuild receipt`, merge
  SHA `74577ac5f190eb22b4c7bb3722c09679a18b37f9`) built **pure `/tmp`** candidate
  full-ledger snapshots that cleared the digest and window gates, but were not
  DB-linked.
- **PR #96** (`docs: record funding source snapshot copied DB dry run`) patched a
  **copied** DB with the PR #95 candidate: it cleared digest/window and proved the
  copied DB is patchable and the sidecar parseable, but the candidate carried
  **stale metadata** and failed the DB/lane checks
  (`funding_source_snapshot_db_mismatch`) and orphan check
  (`funding_source_snapshot_unreferenced_or_orphaned`).
- **PR #97** (`docs: diagnose funding source recommit blocker`, merge SHA
  `365d1b16cac0ff2264378c6d081c4dc7de1f5cd2`) diagnosed the required
  **metadata alignment and hash-build order**: the candidate envelope must be
  rebuilt with copied-DB / batch-aligned metadata and the file/bundle hashes
  computed in the correct order.
- **PR #99** (`docs: record metadata aligned copied DB dry run`, merge SHA
  `2f7412fdf2fd2bfe197832eab17101c568984162`) rebuilt the candidate with aligned
  metadata against the **current** source CSVs and drove the DB-linked full-ledger
  clean-carry gate on the **copied** DB to `CLEAN_NET_OF_CARRY` with reason codes
  `[]`, all four target caveats absent, no real DB mutation.

Therefore: a real shadow-DB recommit is now **plannable** because a copied-DB dry
run has proven the exact metadata + hash recipe clears the DB-linked full-ledger
gate. It is **not yet authorized**; this document is the conservative procedure a
later approved task must follow.

## 3. Real Target Artifacts

Real VM paths (documented for the future execution task; opened read-only /
immutable only, if at all, by this plan):

- Real shadow DB:
  `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db`
- Shadow lane output dir:
  `/srv/qnty/output/paper_pnl_null_shadow_v0`
- Funding snapshot (sidecar) dir:
  `/srv/qnty/output/paper_pnl_null_shadow_v0/funding_source_snapshots`
- Official verifier report:
  `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_verify_report.json`
- VM repo:
  `/srv/qnty/repo`
- Data dir (source funding CSVs):
  `/srv/qnty/repo/data`

Known real-artifact fingerprints captured read-only in PR #99 (baseline for the
future execution's before-hash comparison; must be re-captured at execution time
since source may drift):

- Real shadow DB: size `172032`, mtime `2026-07-06T04:33:40Z`, sha256
  `3cbc6e9c…c739a897`.
- Official shadow report: size `3531`, mtime `2026-07-01T18:15:57Z`, sha256
  `653605a7…f14e0ffd`.
- Real shadow output dir aggregate: `1250f82d…fcccf770`.

## 4. Preconditions For Future Execution

The future execution task must verify and record all of the following **before**
any mutation:

- Local `main` includes the PR #99 merge SHA
  `2f7412fdf2fd2bfe197832eab17101c568984162`.
- VM repo (`/srv/qnty/repo`) path / head SHA / `git status` recorded (expected
  clean; PR #99 saw `2bd88430fe6b2881aaa2b32947002217d3e02ba5`,
  `## main...origin/main`).
- Real shadow DB exists at the target path.
- Official verifier report exists at the target path.
- Funding source CSVs exist under `/srv/qnty/repo/data` (BNBUSDT, BTCUSDT, ETHUSDT,
  SOLUSDT, XRPUSDT `_8h_funding.csv`).
- No writer / trader / backfill / live process is running.
- Current source-file digests recorded **at execution time** (they drift — PR #99
  digests already differ from PR #95/#96; the candidate must be rebuilt against
  whatever CSVs are current when the recommit runs).
- A backup directory prepared under `/tmp` (or another explicitly-named safe backup
  path).
- Real shadow DB **before** hash / mtime / size captured.
- Official report **before** hash / mtime / size captured.
- Shadow output dir **before** aggregate captured.
- Enough disk space for backup + `/tmp` temp outputs.

If any precondition fails or cannot be established, **stop** and do not proceed
(see §9).

## 5. Backup / Rollback Plan

**Backup (before any mutation):**

- Backup location:
  `/tmp/qnty_real_shadow_recommit_backup_<timestamp>/`
- Files to create in the backup dir:
  - copy of the real shadow DB (`paper_ledger.db`);
  - copy of the official verifier report (`paper_verify_report.json`);
  - a copy / directory listing (names + sizes + mtimes + sha256) of the existing
    `funding_source_snapshots/` sidecar directory metadata.
- Backup hash verification: the backup DB sha256 **must equal** the original real
  DB sha256 captured in §4 before mutation. If they differ, the backup is invalid
  — **stop**.

**Rollback procedure (if anything goes wrong after mutation):**

1. Immediately stop if any writer / trader / live / backfill process is found
   running.
2. Restore the real shadow DB from the backup copy (overwrite the mutated DB with
   the verified backup).
3. Restore the official report from backup **only if it was touched by mistake**
   (it must never be touched during recommit; see §10).
4. Restore / leave the snapshot sidecar directory according to the documented
   state: if a new sidecar was written but the DB was rolled back, remove the
   orphaned sidecar so the directory matches the pre-run listing.
5. Re-run the verifier **read-only** against the restored DB and confirm it
   returns to the pre-run state.
6. Record a rollback receipt (hashes before / after / restored, commands, reason).

**Stop conditions if backup cannot be created or verified:** do not mutate the
real DB at all. A recommit without a verified, hash-matching backup is forbidden.

## 6. Real Recommit Execution Outline

Future execution sequence (**do not run now**):

1. Copy the current local code to VM `/tmp` (do not modify `/srv/qnty/repo`).
2. Read the real shadow DB **immutable / read-only** (`mode=ro&immutable=1`) to
   derive the latest committed batch identity and the full-ledger funding window.
3. Build a metadata-aligned **full-ledger** snapshot candidate for the **real**
   shadow DB (not a copied DB), using the production pure builder + writer glue
   (`build_funding_source_snapshot_payload_v1`,
   `build_funding_source_snapshot_envelope_v1`,
   `validate_funding_source_snapshot_envelope_v1`,
   `_required_funding_windows_for_snapshot`, `_read_funding_source_csv_rows`).
4. Metadata must align (per PR #99, adapted to real paths):
   - `lane.lane_id = paper_pnl_null_shadow_v0`
   - `lane.output_dir = /srv/qnty/output/paper_pnl_null_shadow_v0`
   - `snapshot_metadata.db_path_reference =
     /srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db`
   - `snapshot_metadata.ledger_batch_id = latest committed batch id`
     (PR #99 assumption: `"17"` — re-confirm at execution time)
   - `batch_start_watermark` / `batch_end_watermark` = the latest committed batch's
     prior / new watermarks (PR #99: `2026-07-03T08:00:00` → `2026-07-05T16:00:00`)
   - evaluation window = **full-ledger** funding window (PR #99:
     `2026-06-25T08:00:00Z → 2026-07-05T16:00:00Z`)
   - source digests = **current** `/srv/qnty/repo/data` CSVs at execution time
   - `batch_identity_matches = true`, `evaluation_identity_matches = true`,
     `write_state = committed`
5. Compute hashes in the correct order (per PR #97 diagnosis / PR #99 method):
   - build payload with final real-DB metadata
   - build envelope
   - compute envelope `snapshot_sha256` (helper)
   - deterministic JSON serialization
   - compute sidecar **file** sha256
   - source bundle sha256 (`source_bundle_sha256`)
6. Write the sidecar JSON under:
   `/srv/qnty/output/paper_pnl_null_shadow_v0/funding_source_snapshots/`
   (`PRAGMA journal_mode=DELETE` semantics — no `-wal`/`-shm` residue on the DB).
7. Patch the latest committed batch row in the real shadow DB with the six
   `funding_source_snapshot_*` fields (see §7).
8. Run the verifier against the real shadow DB:
   `quantbot.paper.sqlite_verify` with `--read-only --json
   --data-dir /srv/qnty/repo/data`, writing output to **`/tmp` first**, never to
   the official report path.
9. Compare:
   - full-ledger clean-carry decision / reason codes;
   - batch clean-carry decision / reason codes;
   - `db_mutation_performed` false during verifier (verifier opens read-only);
   - real DB **after** hash changed **only** due to the intended six-field row
     update (vs the §4 before hash and the post-patch hash);
   - official report unchanged.
10. **Do not** promote `/tmp` verifier output to the official report in the same
    step. Promotion is a separate, separately-approved task (§10).

## 7. Exact SQL Shape

For a **future explicitly-approved execution only**. Adapted from the PR #99
copied-DB patch. Must run inside a transaction; must update exactly one latest
committed batch row; after update, select the row back and verify all six fields;
if the row count `!= 1`, rollback immediately.

The six columns (verified against the schema in `quantbot/paper/db.py:50-57`,
`LEDGER_BATCH_SNAPSHOT_REFERENCE_COLUMNS`):

- `funding_source_snapshot_path` — sidecar path under the real
  `funding_source_snapshots/` dir
- `funding_source_snapshot_sha256` — sidecar **file** sha256
- `funding_source_snapshot_bundle_sha256` — payload `source_bundle_sha256`
- `funding_source_snapshot_schema_version` — `FUNDING_SOURCE_SNAPSHOT_SCHEMA_V1`
- `funding_source_snapshot_write_state` — `committed`
- `funding_source_snapshot_created_at` — snapshot `generated_at_utc` (ISO-8601 Z)

The verifier expects `funding_source_snapshot_sha256` = sidecar **file** SHA and
`funding_source_snapshot_bundle_sha256` = payload `source_bundle_sha256`.

```sql
BEGIN;

UPDATE ledger_batches
SET funding_source_snapshot_path = ?,
    funding_source_snapshot_sha256 = ?,
    funding_source_snapshot_bundle_sha256 = ?,
    funding_source_snapshot_schema_version = ?,
    funding_source_snapshot_write_state = ?,
    funding_source_snapshot_created_at = ?
WHERE batch_id = ?;   -- latest committed batch id (PR #99: 17; re-confirm)

-- Guard: exactly one row must have been updated.
-- If changes() != 1  -> ROLLBACK immediately and stop.

-- Select the row back and verify all six fields equal the intended values.
SELECT funding_source_snapshot_path,
       funding_source_snapshot_sha256,
       funding_source_snapshot_bundle_sha256,
       funding_source_snapshot_schema_version,
       funding_source_snapshot_write_state,
       funding_source_snapshot_created_at
FROM ledger_batches
WHERE batch_id = ?;

-- Only COMMIT if row count == 1 and all six fields match.
COMMIT;   -- else ROLLBACK
```

Parameter order matches the `SET` clause, with the target `batch_id` last.

## 8. Acceptance Criteria For Future Execution

The future execution is acceptable **only if all** hold:

- real DB backup created and hash-verified (backup sha == original sha);
- official report backup / hash verified;
- no writer / trader / live / backfill processes during the run;
- source digests stable during the run (identical before and after);
- sidecar validates (`validate_funding_source_snapshot_envelope_v1` OK; payload
  reason codes `[]`; coverage `complete`);
- the DB row patch touches **exactly one** row;
- real shadow DB hash changes **only after** the intended DB update (matches the
  post-patch hash, not the before hash; unchanged by the verifier read-only run);
- official report hash **unchanged**;
- VM repo (`/srv/qnty/repo`) unchanged;
- shadow output dir gains **exactly one** intended sidecar JSON and nothing else;
- verifier status `OK`; `failure_count` `0`;
- full-ledger clean-carry decision: `CLEAN_NET_OF_CARRY`;
- full-ledger reason codes: `[]`;
- target caveats **absent**:
  - `funding_source_file_digest_mismatch`
  - `funding_source_snapshot_window_mismatch`
  - `funding_source_snapshot_db_mismatch`
  - `funding_source_snapshot_unreferenced_or_orphaned`
- batch clean-carry may remain `CAVEATED_ENGINE_SEMANTICS` with **only**
  `funding_source_batch_window_mismatch` (by design — a full-ledger window is not
  the batch watermark window); no other unexpected caveats;
- the execution receipt PR records all hashes, exact commands, and diffs.

## 9. Stop Conditions

Execution must **stop** (and roll back if already mutated) if any of these occur:

- backup cannot be created or hash-verified;
- any writer / trader / live / backfill process is running;
- the latest committed batch identity differs unexpectedly from the PR #99
  assumption (batch `17`) and cannot be reconciled;
- funding CSVs change during the run (source drift mid-execution);
- the candidate fails envelope validation / coverage;
- the row update count `!= 1`;
- the sidecar path or hash mismatches the DB reference fields;
- the verifier reports unexpected reason codes (anything beyond the allowed batch
  `funding_source_batch_window_mismatch`);
- the official report is modified accidentally;
- `/srv/qnty/repo` changes;
- any output outside the intended paths changes;
- source / digest semantics differ from the PR #99 recipe.

## 10. Official Report Promotion Policy

- The official report
  (`/srv/qnty/output/paper_pnl_null_shadow_v0/paper_verify_report.json`) must
  **not** be overwritten during the recommit execution.
- The recommit execution first produces `/tmp` verifier output plus a docs receipt.
- Only a **later, separate, explicitly-approved** task may promote / update the
  official report.
- Official report promotion must be its own scoped task with its own before/after
  report hashes and review. `OFFICIAL_REPORT_PROMOTION_BLOCKED` stands until then.

## 11. Expected Future PR Sequence

1. `FUNDING_SOURCE_SNAPSHOT_REAL_DB_RECOMMIT_EXECUTION_GIT_OWNED`
   - the explicit real-DB mutation task;
   - backup + recommit + `/tmp` verifier receipt;
   - **no** official report overwrite.
2. `FUNDING_SOURCE_SHADOW_OFFICIAL_REPORT_PROMOTION_PLAN_GIT_OWNED`
   - only if the recommit succeeded.
3. `FUNDING_SOURCE_SHADOW_OFFICIAL_REPORT_PROMOTION_EXECUTION_GIT_OWNED`
   - optional, separate approval.
4. Then return to paper-experiment / shorting-hypothesis planning.

## 12. Non-Goals

- no execution
- no real DB mutation
- no official report overwrite
- no writer / trader / live run
- no backfill
- no code change
- no test change
- no schema change
- no verifier / reporter / writer change
- no edge / profitability / live / shorting / deployment claims

## Verdict

`FUNDING_SOURCE_REAL_DB_RECOMMIT_PLAN_RECORDED`

This plan records the exact, auditable, conservative procedure — preconditions,
backup / rollback, hash-ordered candidate build, transaction-guarded single-row
SQL patch, `/tmp`-only verifier run, acceptance criteria, stop conditions, and
report-promotion boundaries — for a future, explicitly-approved real shadow-DB
funding-source snapshot recommit, following the PR #99 metadata-aligned copied-DB
dry run that reached DB-linked full-ledger `CLEAN_NET_OF_CARRY`. No real DB is
mutated, no official report is overwritten, and no writer/trader/live/backfill is
run by this plan. `EDGE_UNPROVEN`, `BLOCK_LIVE_INTEGRATION`, and real full-ledger
`CAVEATED_ENGINE_SEMANTICS` are preserved.
