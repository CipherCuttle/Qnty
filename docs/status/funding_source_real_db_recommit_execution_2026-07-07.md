# QNTY Funding Source Real-DB Recommit Execution — 2026-07-07

## Status Boundary

- The real shadow DB was intentionally updated in **only** the six
  `funding_source_snapshot_*` reference fields of the latest committed
  `ledger_batches` row (batch `17`); of those six, four changed value and two
  (`schema_version`, `write_state`) were already at their target values.
- Exactly **one** new funding-source snapshot sidecar JSON was intentionally
  added under the real shadow lane `funding_source_snapshots/` directory.
- The official verifier report was **not** overwritten.
- No writer / trader / live / backfill run occurred.
- No code / test / schema / verifier / reporter / writer change.
- No prod DB mutation.
- No live / shorting / deployment / edge / profitability claim.
- `EDGE_UNPROVEN` remains.
- `BLOCK_LIVE_INTEGRATION` remains.
- The real full-ledger clean-carry gate is now `CLEAN_NET_OF_CARRY` **because the
  real DB-linked verifier proved it read-only** (see Verifier Evidence). This is
  "not killed by this gate", not trading approval.
- The official report remains **stale** until a separate, explicitly-approved
  promotion task; `OFFICIAL_REPORT_PROMOTION_BLOCKED` stands.

## Scope

- date: 2026-07-07.
- PR #99 merge SHA: `2f7412fdf2fd2bfe197832eab17101c568984162`.
- PR #100 merge SHA: `2227dcaf8f460a6b35f0ca5aba229793e89edeea`.
- local repo head (branch base = `main` incl. PR #100):
  `2227dcaf8f460a6b35f0ca5aba229793e89edeea`.
- branch: `docs/funding-source-real-db-recommit-execution`.
- output doc:
  `docs/status/funding_source_real_db_recommit_execution_2026-07-07.md`.
- VM workspace: `/tmp/qnty_real_shadow_recommit_20260707T150748Z`.
- backup dir: `/tmp/qnty_real_shadow_recommit_backup_20260707T150748Z`.
- current local code copied to VM `/tmp`:
  `/tmp/qnty-real-recommit-code-20260707T150748Z` (funding-snapshot modules
  byte-identical to VM repo head `2bd88430…`; see Method).
- real shadow DB: `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db`.
- official report:
  `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_verify_report.json`.
- sidecar written:
  `/srv/qnty/output/paper_pnl_null_shadow_v0/funding_source_snapshots/funding_source_snapshot_v1_8b9d80408b5aae517ba745a5072d9f7d09125572a23ea5e792e2d80e9c099d69.json`.
- data dir: `/srv/qnty/repo/data`.
- verifier output (post-recommit):
  `/tmp/qnty_real_shadow_recommit_20260707T150748Z/verify_real_shadow_db_after_recommit.json`.
- MemPalace: **recall only** (qnty wing — batch-17 identity, recommit status,
  `EDGE_UNPROVEN`/`BLOCK_LIVE_INTEGRATION` guardrails). Source of truth remained
  git, `CLAUDE.md`, `docs/status/`, `docs/plans/`, verifier output. No new paths
  mined; no hooks/autosave enabled.

## Method

- Local `main` was fast-forwarded to `origin/main` = PR #100 merge SHA
  `2227dcaf…` (preflight step 1 requires local main to include PR #100). Branch
  `docs/funding-source-real-db-recommit-execution` was cut from it.
- The candidate was built with the **production** pure builder + writer glue
  (`build_funding_source_snapshot_payload_v1`,
  `build_funding_source_snapshot_envelope_v1`,
  `validate_funding_source_snapshot_envelope_v1`,
  `_required_funding_windows_for_snapshot`, `_read_funding_source_csv_rows`),
  from the current **local** code copied to VM `/tmp`, under
  `/srv/qnty/venv/bin/python`. `quantbot/paper/funding_source_snapshot.py` is
  unchanged vs VM head `2bd88430…`; the two writer glue helpers used sit in an
  unchanged region of `sqlite_writer.py` (its diffs vs `2bd88430…` are in
  `_build_signal_snapshots_for_bars` / `run_sqlite_accounting`, not the snapshot
  helpers). VM module hashes matched local byte-for-byte.
- Full-ledger required windows were derived from the real `funding` table
  (read-only, `mode=ro&immutable=1`); source rows/digests from current
  `/srv/qnty/repo/data` CSVs.
- Hash/build order (per PR #97/#99): build payload with final real-DB metadata →
  build envelope → `snapshot_sha256` → deterministic JSON serialization
  (`json.dump(ensure_ascii=True, indent=2, sort_keys=True)` + `"\n"`, matching
  `_write_json_atomic`) → sidecar **file** sha256 → `source_bundle_sha256`.
- The candidate was proven equivalent to the PR #99 metadata-aligned copied-DB
  candidate: identical `source_bundle_sha256`, `required_funding_windows`,
  `source_files`, `evaluation_window`, `symbols_covered`, `coverage_decision`,
  `reason_codes`; a recursive payload diff showed the **only** differing leaf
  paths are the five intended ones (`generated_at_utc`,
  `provenance.activity.generated_at_utc`,
  `provenance.activity.writer_or_verifier_command`, `lane.output_dir`,
  `snapshot_metadata.db_path_reference`).
- The real DB was patched in one guarded transaction (single row, change-count
  and select-back checked), then verified read-only with output to `/tmp` only.
- No writes to `/srv/qnty/repo`. No official report overwrite.

## Preflight

- Local `main` includes PR #100 merge SHA `2227dcaf…`: **OK** (fast-forwarded
  from PR #99 `2f7412f`; `origin/main` = `2227dcaf…`).
- VM repo `/srv/qnty/repo` head `2bd88430fe6b2881aaa2b32947002217d3e02ba5`,
  status `## main...origin/main` (clean; **not modified**).
- Real shadow DB exists: size `172032`, mtime `1783312420`
  (`2026-07-06T04:33:40Z`), sha256 `3cbc6e9c…c739a897` (== PR #99 baseline).
- Official report exists: size `3531`, mtime `1782929757`
  (`2026-07-01T18:15:57Z`), sha256 `653605a7…f14e0ffd` (== PR #99 baseline).
- Funding CSVs present with digests (identical before and after the run):
  - `BNBUSDT_8h_funding.csv` `ad40bf88…d170ef3`
  - `BTCUSDT_8h_funding.csv` `65c66a32…750c8e`
  - `ETHUSDT_8h_funding.csv` `e9b3423b…6db467a9`
  - `SOLUSDT_8h_funding.csv` `a0980a1a…f66a15cf6a`
  - `XRPUSDT_8h_funding.csv` `2e9b5971…dbc00a560`
- No writer / trader / live / backfill process running.
- Latest committed batch identity (real DB, read-only): `MAX(batch_id)=17`,
  `COUNT=17`; batch 17 `prior_watermark_bar_ts=2026-07-03T08:00:00`,
  `new_watermark_bar_ts=2026-07-05T16:00:00`, `committed_at=2026-07-06T04:33:09Z`
  — matches the PR #99 assumption.
- Disk: `/` 69G available (`5%` used).
- Pre-patch read-only verifier baseline (bracketed by DB sha; DB **unchanged**
  `3cbc6e9c…` before/after): status `OK`, failure_count `0`, full-ledger
  clean-carry `CAVEATED_ENGINE_SEMANTICS` with reason codes
  `[funding_source_file_digest_mismatch, funding_source_snapshot_window_mismatch]`
  — the expected current stale-snapshot state.

## Backup

- Backup dir: `/tmp/qnty_real_shadow_recommit_backup_20260707T150748Z`.
- `paper_ledger.db` backup sha256 `3cbc6e9c…c739a897` **==** original real DB
  sha256 — verified.
- `paper_verify_report.json` backup sha256 `653605a7…f14e0ffd` **==** original
  official report sha256 — verified.
- `funding_source_snapshots.listing.txt` + `funding_source_snapshots.sha256.txt`
  written under `/tmp` (pre-run 3-file directory state captured).

## Candidate Snapshot

- sidecar name:
  `funding_source_snapshot_v1_8b9d80408b5aae517ba745a5072d9f7d09125572a23ea5e792e2d80e9c099d69.json`.
- envelope `snapshot_sha256`:
  `29e513f994330a0cf0009889c9801d110d10eae6d78726ba7d68935f4c080566`.
- sidecar **file** sha256:
  `7c5068afef44fc360e88bbde126d892c538973e8f98cbd32dfd0a63ae310ab66`.
- `source_bundle_sha256`:
  `8b9d80408b5aae517ba745a5072d9f7d09125572a23ea5e792e2d80e9c099d69`
  (**identical** to the PR #99 copied-DB candidate — the source CSVs and required
  windows are unchanged).
- sidecar size: `46630` bytes.
- schema: `FUNDING_SOURCE_SNAPSHOT_SCHEMA_V1`; write_state: `committed`.
- generated_at_utc / created_at: `2026-07-07T15:16:47Z`.
- evaluation window (full-ledger): `2026-06-25T08:00:00Z → 2026-07-05T16:00:00Z`.
- symbols: `BNBUSDT, BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT`.
- required windows: count `59`.
- coverage decision: `complete`; payload reason codes: `[]`; envelope
  validation: `[]`.
- aligned metadata:
  - `lane.lane_id = paper_pnl_null_shadow_v0`.
  - `lane.output_dir = /srv/qnty/output/paper_pnl_null_shadow_v0`.
  - `snapshot_metadata.db_path_reference =
    /srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db`.
  - `snapshot_metadata.ledger_batch_id = "17"`.
  - `snapshot_metadata.batch_start_watermark = 2026-07-03T08:00:00`;
    `batch_end_watermark = 2026-07-05T16:00:00`.
  - `batch_identity_matches = true`; `evaluation_identity_matches = true`;
    `write_state = committed`; `db_identity_hash_before = null`.
- source file digests (payload): full-file digests match the preflight CSV
  digests above; row-subset digests match the PR #99 candidate.
- equivalence to PR #99 candidate: only differing payload leaf paths are
  `generated_at_utc`, `provenance.activity.generated_at_utc`,
  `provenance.activity.writer_or_verifier_command`, `lane.output_dir`,
  `snapshot_metadata.db_path_reference`.

## Real DB Patch

- target: `ledger_batches` batch_id `17` (latest committed).
- DB sha **before patch**: `3cbc6e9c…c739a897`.
- DB sha **after patch**:
  `00a4817e1d49aef51398fe0022cc2f3754302bc12f445912d4eb0d0596fc21ce`.
- row update count: `1`; select-back equalled intended values; committed.
- persistent journal mode: `WAL`. The patch used one `BEGIN IMMEDIATE …
  COMMIT`; SQLite's checkpoint-on-last-close flushed the change into the main DB
  file and removed the **pre-existing stale** `paper_ledger.db-wal` (0 bytes) and
  `paper_ledger.db-shm` — so there is now **no** `-wal`/`-shm` residue. Journal
  mode was not changed.

Before row (batch 17):

```json
{
  "funding_source_snapshot_path": "/srv/qnty/output/paper_pnl_null_shadow_v0/funding_source_snapshots/funding_source_snapshot_v1_1c5b433eb3adc345bdf024f20b45ffba874e77090ab5fc652f81fe169791451b.json",
  "funding_source_snapshot_sha256": "730455698eb58e72dd7586d52f0e064350ace8dcbc077eddadeb85d740bfe8a7",
  "funding_source_snapshot_bundle_sha256": "1c5b433eb3adc345bdf024f20b45ffba874e77090ab5fc652f81fe169791451b",
  "funding_source_snapshot_schema_version": "FUNDING_SOURCE_SNAPSHOT_SCHEMA_V1",
  "funding_source_snapshot_write_state": "committed",
  "funding_source_snapshot_created_at": "2026-07-06T04:33:09Z"
}
```

After row (batch 17):

```json
{
  "funding_source_snapshot_path": "/srv/qnty/output/paper_pnl_null_shadow_v0/funding_source_snapshots/funding_source_snapshot_v1_8b9d80408b5aae517ba745a5072d9f7d09125572a23ea5e792e2d80e9c099d69.json",
  "funding_source_snapshot_sha256": "7c5068afef44fc360e88bbde126d892c538973e8f98cbd32dfd0a63ae310ab66",
  "funding_source_snapshot_bundle_sha256": "8b9d80408b5aae517ba745a5072d9f7d09125572a23ea5e792e2d80e9c099d69",
  "funding_source_snapshot_schema_version": "FUNDING_SOURCE_SNAPSHOT_SCHEMA_V1",
  "funding_source_snapshot_write_state": "committed",
  "funding_source_snapshot_created_at": "2026-07-07T15:16:47Z"
}
```

Exact SQL:

```sql
BEGIN IMMEDIATE;
UPDATE ledger_batches
SET funding_source_snapshot_path = ?,
    funding_source_snapshot_sha256 = ?,
    funding_source_snapshot_bundle_sha256 = ?,
    funding_source_snapshot_schema_version = ?,
    funding_source_snapshot_write_state = ?,
    funding_source_snapshot_created_at = ?
WHERE batch_id = ?;   -- 17; guard: changes() must == 1 else ROLLBACK
SELECT funding_source_snapshot_path, funding_source_snapshot_sha256,
       funding_source_snapshot_bundle_sha256, funding_source_snapshot_schema_version,
       funding_source_snapshot_write_state, funding_source_snapshot_created_at
FROM ledger_batches WHERE batch_id = 17;   -- verify == intended else ROLLBACK
COMMIT;
```

- fields changed **in value**: `funding_source_snapshot_path`,
  `funding_source_snapshot_sha256`, `funding_source_snapshot_bundle_sha256`,
  `funding_source_snapshot_created_at`. `funding_source_snapshot_schema_version`
  and `funding_source_snapshot_write_state` were set but already held their
  target values.
- semantic whole-DB diff (backup vs patched, all 13 tables): **exactly one
  differing row** — `ledger_batches` batch 17 — differing columns exactly the
  four above; all other tables byte-identical.

## Verifier Evidence

Exact command:

```bash
PYTHONPATH=/tmp/qnty-real-recommit-code-20260707T150748Z \
  /srv/qnty/venv/bin/python -m quantbot.paper.sqlite_verify \
  --db-path /srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db \
  --read-only --json --data-dir /srv/qnty/repo/data \
  > /tmp/qnty_real_shadow_recommit_20260707T150748Z/verify_real_shadow_db_after_recommit.json \
  2> /tmp/qnty_real_shadow_recommit_20260707T150748Z/verify_real_shadow_db_after_recommit.err
```

- exit code: `0`.
- stdout: `verify_real_shadow_db_after_recommit.json`, `17083` bytes, sha256
  `a244d89d7695af473aea5595f20038b8293812891a7bced2c7245c8170e877a5`.
- stderr: `verify_real_shadow_db_after_recommit.err`, `0` bytes, sha256
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
- status: `OK`; failure_count: `0`; watermark: `2026-07-05T16:00:00`.
- `db_mutation_performed`: `false`; `sqlite_open_mode`:
  `file_uri_mode_ro_immutable`; `wal_shm_files_created`: `false`;
  `read_only`: `true`.
- real DB sha **unchanged by verifier**: `00a4817e…` before and after the
  verifier run.
- `funding_source_snapshot_status`: `present_valid`; selector `ledger_batches`;
  `db_linked: true`; `target_batch_id: 17`; `candidate_count: 4`;
  `evaluation_identity_matches: true`; `batch_identity_matches: true`.
- selected snapshot: `selected_snapshot_path` = the new
  `…/funding_source_snapshot_v1_8b9d8040….json`; `file_sha256 7c5068af…`;
  `source_bundle_sha256 8b9d8040…`; `db_path_reference` = real DB;
  `lane_output_dir` = real shadow lane dir.
- `resolved_funding_source_dir`: `/srv/qnty/repo/data`;
  `source_path_available: true`.
- resum check: `status ok`, `funding_rows 59`, `funding_amount_sum 3.44000686`,
  `ledger_state_funding_cum 3.4400068507…`, `latest_equity_funding_cum
  3.44000685`, `tolerance_abs 1e-06`, `reason_codes []`.

Full-ledger clean-carry:

- decision: `CLEAN_NET_OF_CARRY`; status: `clean_net_of_carry`;
  reason codes: `[]`.

Batch clean-carry:

- decision: `CAVEATED_ENGINE_SEMANTICS`; status: `refused_db_or_lane_mismatch`;
  reason codes: `[funding_source_batch_window_mismatch]` (only) — a full-ledger
  window is not the batch watermark window under strict equality, **by design**.

Target reason-code presence (all **absent** in the full-ledger set):

- `funding_source_file_digest_mismatch`: absent.
- `funding_source_snapshot_window_mismatch`: absent.
- `funding_source_snapshot_db_mismatch`: absent.
- `funding_source_snapshot_unreferenced_or_orphaned`: absent.

- official report **unchanged** during/after the run; verifier output written
  only under `/tmp`.

## Post-Run Integrity

| Artifact | before → after | Match |
|---|---|---|
| Real shadow DB sha256 | `3cbc6e9c…c739a897` → `00a4817e…96fc21ce` | changed **only** by the intended batch-17 patch |
| Real shadow DB size | `172032` → `172032` | ✅ |
| Official report sha256 | `653605a7…f14e0ffd` → `653605a7…f14e0ffd` | ✅ unchanged |
| Official report size/mtime | `3531` / `2026-07-01T18:15:57Z` → same | ✅ unchanged |
| Source CSV digests (×5) | unchanged | ✅ |
| VM repo `/srv/qnty/repo` | `2bd88430…` `## main...origin/main` → same | ✅ unchanged |
| `-wal` / `-shm` residue | stale files present → **none** | no residue |
| Writer/trader/live/backfill | none → none | ✅ |

- shadow output dir: gained **exactly one** intended sidecar JSON
  (`…8b9d8040….json`); the pre-existing stale `paper_ledger.db-wal`/`-shm`
  transient files were removed by SQLite's checkpoint-on-close; no other files
  added; official `paper_verify_report.json` / `paper_verify_receipt.md` /
  `paper_verify_log.jsonl` untouched.
- verifier output exists only under `/tmp`.

## Impact On Existing Receipts

- PR #99 copied-DB proof is now **promoted to the real shadow DB reference
  state**: the same metadata + hash recipe, rebuilt against the real DB paths,
  drove the real DB-linked full-ledger clean-carry gate to `CLEAN_NET_OF_CARRY`
  with reason codes `[]`.
- The real full-ledger `CAVEATED_ENGINE_SEMANTICS` label (PR #92 diagnosis,
  reproduced in this run's pre-patch baseline) is **cleared** by this run for the
  full-ledger gate, as proven by the real DB-linked verifier.
- The batch clean-carry remains `CAVEATED_ENGINE_SEMANTICS` with only
  `funding_source_batch_window_mismatch` — expected/by-design.
- The **official report remains stale** (still the `2026-07-01` report); it is
  updated only by a separate, explicitly-approved promotion task.
- `EDGE_UNPROVEN` and `BLOCK_LIVE_INTEGRATION` remain.

## Recommended Next Action

`FUNDING_SOURCE_SHADOW_OFFICIAL_REPORT_PROMOTION_PLAN_GIT_OWNED`

- Purpose: plan the separate, explicitly-approved promotion of the official
  shadow verifier report now that the real DB-linked full-ledger gate is
  `CLEAN_NET_OF_CARRY`, with its own before/after report hashes and review.
- Promotion must remain its own scoped task; `OFFICIAL_REPORT_PROMOTION_BLOCKED`
  stands until then.

## Non-Goals

- no code change; no test change; no schema change.
- no verifier / reporter / writer logic change.
- no trader / strategy change.
- no prod DB mutation.
- no official report overwrite.
- no writer / trader / live run; no backfill; no deployment.
- no live integration; no shorting; no trial-registry change.
- no null / benchmark lane change.
- no `/srv/qnty/repo` change.
- no edge / profitability / statistical-significance / live-readiness claim.
- MemPalace recall-only; no hooks/autosave; no new path mining.

## Verdict

`FUNDING_SOURCE_REAL_DB_RECOMMIT_EXECUTION_RECORDED`

The explicitly-approved real shadow-DB funding-source snapshot recommit was
executed: one new sidecar JSON was written under the shadow lane, and exactly one
`ledger_batches` row (batch 17) had its six `funding_source_snapshot_*` reference
fields set (four changed value), inside a guarded single-row transaction with a
verified hash-matching backup. The real DB-linked verifier, run read-only with
output to `/tmp` only, returned status `OK`, full-ledger clean-carry
`CLEAN_NET_OF_CARRY` with reason codes `[]`, all four target caveats absent, and
the batch gate caveated only by the by-design `funding_source_batch_window_mismatch`.
The official report was not overwritten and remains stale until a separate
promotion; the prod DB, `/srv/qnty/repo`, source CSVs, and all other DB rows are
unchanged. `EDGE_UNPROVEN` and `BLOCK_LIVE_INTEGRATION` remain.
