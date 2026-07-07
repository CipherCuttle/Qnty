# QNTY Funding Source Recommit Blocker Diagnosis — 2026-07-07

## Status Boundary

- `EDGE_UNPROVEN` remains.
- `BLOCK_LIVE_INTEGRATION` remains.
- Real full-ledger `CAVEATED_ENGINE_SEMANTICS` remains.
- This is diagnosis only.
- This receipt does not prove edge, profitability, statistical significance,
  shorting readiness, live readiness, or production deployment.
- This receipt does not mutate real prod/shadow DBs.
- This receipt does not backfill historical rows.
- This receipt does not overwrite official reports.
- This receipt does not recommit snapshots to the real DB.
- This receipt does not run writer/trader/live code.

## Scope

- date: 2026-07-07.
- PR #96 merge SHA:
  `c1419f6c0ee8bd9b119fa274b4987e17f352d09c`.
- local repo head:
  `c1419f6c0ee8bd9b119fa274b4987e17f352d09c`.
- branch name:
  `docs/funding-source-recommit-blocker-diagnosis`.
- output doc path:
  `docs/status/funding_source_recommit_blocker_diagnosis_2026-07-07.md`.
- VM was accessed read-only: yes. The only VM operations in this diagnosis were
  `git status`/`git rev-parse` on `/srv/qnty/repo`, `find`/JSON reads under the
  PR #96 `/tmp` workspace, and immutable/query-only SQLite reads against the
  copied DB under `/tmp`.
- PR #96 `/tmp` workspace was available on the VM:
  `/tmp/qnty_shadow_recommit_copied_db_dry_run_20260707T025834Z`.
- Real prod/shadow DBs opened in this diagnosis: no.
- Real prod/shadow DBs mutated in this diagnosis: no.
- `/srv/qnty/repo` modified: no; it was observed at
  `2bd88430fe6b2881aaa2b32947002217d3e02ba5` with status
  `## main...origin/main`.
- Output written outside this git receipt: no.

## Method

- Confirmed PR #96 merge state and updated local `main` to the PR #96 merge SHA.
- Inspected current verifier/snapshot/writer code and the focused tests read-only.
- Inspected the merged PR #96 receipt read-only.
- Inspected PR #96 `/tmp` artifacts on the VM read-only:
  copied DB, candidate snapshot JSON, verifier JSON, and path layout.
- Built the metadata matrix from current verifier requirements and PR #96 actuals.
- Diagnosed hash/build order from current builder, writer, verifier, and tests.
- Did not mutate real DBs, run writer/trader/live code, deploy, backfill, or
  overwrite official reports.

## PR #96 Blocker Summary

- The copied DB patch worked mechanically: latest copied batch `17` referenced
  the candidate sidecar path, file SHA, bundle SHA, schema version, write state,
  and created timestamp.
- The verifier found and parsed the copied sidecar under the copied DB parent
  `funding_source_snapshots/` directory.
- The copied DB row used the correct sidecar file SHA:
  `f5efc760471d39e0f8031d31c61dfd8fd70c436d0c44e59965659d753d886a39`.
- Full-ledger digest/window reason codes disappeared:
  `funding_source_file_digest_mismatch` absent and
  `funding_source_snapshot_window_mismatch` absent.
- The verifier still refused DB-linked clean-carry because the candidate envelope
  metadata remained attached to the real shadow lane/DB and lacked target batch
  identity/watermarks for copied batch `17`.
- This means the candidate content was good enough for source digest and
  full-ledger window gates, but its attachment metadata was invalid for the
  copied DB verifier gate.

## Code Path Findings

- Snapshot reason codes are schema-pinned in
  `quantbot/paper/funding_source_snapshot.py:29-44`, including
  `funding_source_snapshot_db_mismatch` and
  `funding_source_snapshot_unreferenced_or_orphaned`.
- `build_funding_source_snapshot_payload_v1` defines the required envelope
  payload fields in `quantbot/paper/funding_source_snapshot.py:477-580`:
  `schema_version`, `evaluation_window`, `lane.output_dir`,
  `source_bundle_sha256`, `write_state`, and `snapshot_metadata` fields including
  `db_path_reference`, `batch_start_watermark`, `batch_end_watermark`,
  `pending_batch_id`, and `ledger_batch_id`.
- `build_funding_source_snapshot_envelope_v1` computes envelope
  `snapshot_sha256` from canonical payload JSON in
  `quantbot/paper/funding_source_snapshot.py:583-590`; validation recomputes it
  in `quantbot/paper/funding_source_snapshot.py:593-608`.
- `clean_mode_decision_from_snapshot_v1` emits:
  `funding_source_snapshot_db_mismatch` for lane/DB identity mismatch
  (`quantbot/paper/funding_source_snapshot.py:669-679`);
  `funding_source_snapshot_unreferenced_or_orphaned` for non-committed,
  identity, pending, or ledger-batch mismatch
  (`quantbot/paper/funding_source_snapshot.py:681-697`);
  digest/source reasons in `quantbot/paper/funding_source_snapshot.py:699-726`.
- The verifier requires sidecars below `db_path.parent/funding_source_snapshots`
  via `_funding_source_snapshot_dir` and `_resolve_db_linked_snapshot_path` in
  `quantbot/paper/sqlite_verify.py:1600-1601` and
  `quantbot/paper/sqlite_verify.py:1680-1702`.
- The DB-linked selector starts at the latest committed `ledger_batches` row via
  `_funding_clean_carry_target_batch` in
  `quantbot/paper/sqlite_verify.py:1634-1653`.
- The six DB reference columns are
  `funding_source_snapshot_path`, `funding_source_snapshot_sha256`,
  `funding_source_snapshot_bundle_sha256`,
  `funding_source_snapshot_schema_version`,
  `funding_source_snapshot_write_state`, and
  `funding_source_snapshot_created_at`
  (`quantbot/paper/sqlite_verify.py:1624-1631`).
- `_classify_db_linked_funding_source_snapshot` validates the DB row -> sidecar
  path -> sidecar file SHA -> envelope -> bundle/schema/write state -> lane,
  DB path, batch id, and batch watermarks in
  `quantbot/paper/sqlite_verify.py:1755-1941`.
- File SHA semantics are explicit:
  `funding_source_snapshot_sha256` is compared to the on-disk sidecar bytes in
  `quantbot/paper/sqlite_verify.py:1803-1812`; envelope `snapshot_sha256` is
  validated separately in `quantbot/paper/sqlite_verify.py:1825-1829`.
- Lane/DB/batch mismatch details are appended in
  `quantbot/paper/sqlite_verify.py:1876-1927`:
  lane output dir must equal `str(db_path.parent)`, metadata
  `db_path_reference` must equal `str(db_path)`, metadata `ledger_batch_id`
  must equal the target batch id, and metadata watermarks must equal the target
  batch's prior/new watermarks when present.
- `funding_source_batch_window_mismatch` is emitted by the batch-scoped clean
  gate when the snapshot evaluation window does not equal the target batch
  window; current code translates snapshot window mismatch to batch-window
  mismatch in `quantbot/paper/sqlite_verify.py:2705-2730`.
- `_clean_carry_status_from_reasons` maps DB/window mismatch reasons, including
  `funding_source_batch_window_mismatch`, to
  `refused_db_or_lane_mismatch` in
  `quantbot/paper/sqlite_verify.py:2408-2434`.
- The current writer already uses the correct production build order:
  pending metadata and envelope in `quantbot/paper/sqlite_writer.py:1248-1307`,
  committed metadata rewrite and envelope rebuild in
  `quantbot/paper/sqlite_writer.py:1321-1349`, then DB row update with final
  file SHA in `quantbot/paper/sqlite_writer.py:313-338` and
  `quantbot/paper/sqlite_writer.py:2029-2054`.
- The writer-compatible sidecar filename uses `source_bundle_sha256` in
  `quantbot/paper/sqlite_writer.py:1297-1300`. The verifier follows the DB row
  path and checks containment under the expected snapshot directory; it does not
  decode the hash from the filename as the acceptance source of truth.
- Tests verify these contracts:
  exact committed DB references can return clean in a tmp synthetic DB
  (`tests/test_paper_sqlite_verifier_db_linked_snapshot_selector.py:261-279`);
  lane mismatch refuses with `funding_source_snapshot_db_mismatch`
  (`tests/test_paper_sqlite_verifier_db_linked_snapshot_selector.py:210-218`);
  batch identity mismatch refuses with
  `funding_source_snapshot_unreferenced_or_orphaned`
  (`tests/test_paper_sqlite_verifier_db_linked_snapshot_selector.py:221-232`);
  batch-scoped clean compares to latest batch watermarks, not the full ledger
  (`tests/test_paper_sqlite_verify_batch_scoped_clean_carry.py:225-291`);
  envelope hashes only payload content
  (`tests/test_funding_source_snapshot_schema.py:391-410`).

## PR #96 Artifact Findings

- Copied DB path:
  `/tmp/qnty_shadow_recommit_copied_db_dry_run_20260707T025834Z/paper_ledger.copied.db`.
- Copied DB parent directory:
  `/tmp/qnty_shadow_recommit_copied_db_dry_run_20260707T025834Z`.
- Snapshot sidecar path:
  `/tmp/qnty_shadow_recommit_copied_db_dry_run_20260707T025834Z/funding_source_snapshots/funding_source_snapshot_v1_bfa6755f9edd0d24750e3d7045cfbd5c1bf02a48b96861b2182e2fb725cd1f6a.json`.
- Copied DB latest batch row:
  batch `17`, prior watermark `2026-07-03T08:00:00`, new watermark
  `2026-07-05T16:00:00`.
- Copied DB reference values:
  path = the `/tmp/.../funding_source_snapshots/...json` sidecar;
  file SHA =
  `f5efc760471d39e0f8031d31c61dfd8fd70c436d0c44e59965659d753d886a39`;
  bundle SHA =
  `bfa6755f9edd0d24750e3d7045cfbd5c1bf02a48b96861b2182e2fb725cd1f6a`;
  schema = `FUNDING_SOURCE_SNAPSHOT_SCHEMA_V1`;
  write state = `committed`;
  created_at = `2026-07-07T00:00:00Z`.
- Candidate snapshot facts:
  sidecar file SHA =
  `f5efc760471d39e0f8031d31c61dfd8fd70c436d0c44e59965659d753d886a39`;
  envelope `snapshot_sha256` =
  `5c635e7e08e6b6708ddf9e42c3fd3d42a7ddd9fa558ec7c395fbdadaedb14645`;
  `source_bundle_sha256` =
  `bfa6755f9edd0d24750e3d7045cfbd5c1bf02a48b96861b2182e2fb725cd1f6a`;
  schema = `FUNDING_SOURCE_SNAPSHOT_SCHEMA_V1`;
  payload reason codes = `[]`;
  coverage decision = `complete`;
  evaluation window =
  `2026-06-25T08:00:00Z -> 2026-07-05T16:00:00Z`.
- Candidate lane/metadata actuals:
  `lane.lane_id = paper_pnl_null_shadow_v0`;
  `lane.output_dir = /srv/qnty/output/paper_pnl_null_shadow_v0`;
  `snapshot_metadata.db_path_reference =
  /srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db`;
  `snapshot_metadata.ledger_batch_id = null`;
  `snapshot_metadata.batch_start_watermark = null`;
  `snapshot_metadata.batch_end_watermark = null`;
  `snapshot_metadata.pending_batch_id = null`;
  `snapshot_metadata.write_state = committed`;
  `batch_identity_matches = true`;
  `evaluation_identity_matches = true`.
- Verifier status:
  `status = OK`, `failure_count = 0`, `source_path_available = true`,
  `source_path_resolution_mode = explicit_data_dir`.
- Full-ledger clean-carry:
  decision `CAVEATED_ENGINE_SEMANTICS`, status
  `refused_db_or_lane_mismatch`, reason codes
  `funding_source_snapshot_db_mismatch` and
  `funding_source_snapshot_unreferenced_or_orphaned`.
- Batch clean-carry:
  decision `CAVEATED_ENGINE_SEMANTICS`, status
  `refused_db_or_lane_mismatch`, reason codes
  `funding_source_batch_window_mismatch` and
  `funding_source_snapshot_unreferenced_or_orphaned`.
- Full verifier mismatch details:
  `lane.output_dir '/srv/qnty/output/paper_pnl_null_shadow_v0' != db directory
  '/tmp/qnty_shadow_recommit_copied_db_dry_run_20260707T025834Z'`;
  `snapshot_metadata.db_path_reference
  '/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db' != db_path
  '/tmp/qnty_shadow_recommit_copied_db_dry_run_20260707T025834Z/paper_ledger.copied.db'`;
  `snapshot_metadata.batch_start_watermark None != target batch
  prior_watermark_bar_ts '2026-07-03T08:00:00'`;
  `snapshot_metadata.batch_end_watermark None != target batch
  new_watermark_bar_ts '2026-07-05T16:00:00'`;
  orphan reason `snapshot_metadata.ledger_batch_id None != target batch '17'`.

## Required Metadata Matrix

| Field | Source of expected value | PR #96 actual value | Required value for copied-DB dry run | Required value for future real-shadow recommit | Failure reason code if mismatched | Hash impact if changed |
|---|---|---|---|---|---|---|
| snapshot path | `ledger_batches.funding_source_snapshot_path`; verifier resolves under `db_path.parent/funding_source_snapshots` | `/tmp/qnty_shadow_recommit_copied_db_dry_run_20260707T025834Z/funding_source_snapshots/funding_source_snapshot_v1_bfa6755f9edd0d24750e3d7045cfbd5c1bf02a48b96861b2182e2fb725cd1f6a.json` | Under copied DB parent `funding_source_snapshots/`, exactly as referenced by copied DB row | Under `/srv/qnty/output/paper_pnl_null_shadow_v0/funding_source_snapshots/` if a future real recommit is explicitly authorized and still targets the current real shadow lane | missing/outside/traversal path maps to snapshot missing; duplicate path maps to ambiguous | Moving identical bytes does not change file hash; changing metadata inside the file does |
| snapshot file sha256 | actual bytes of selected sidecar | `f5efc760471d39e0f8031d31c61dfd8fd70c436d0c44e59965659d753d886a39`, matched DB row | SHA of final serialized sidecar after metadata finalization | SHA of final serialized real-shadow sidecar after metadata finalization | `funding_source_snapshot_digest_mismatch` | This is the file hash; it must be recomputed after writing bytes |
| envelope `snapshot_sha256` | canonical JSON SHA of `snapshot_payload` | `5c635e7e08e6b6708ddf9e42c3fd3d42a7ddd9fa558ec7c395fbdadaedb14645`, valid for stale metadata | Recomputed after copied DB metadata is finalized | Recomputed after real-shadow metadata is finalized | `funding_source_snapshot_digest_mismatch` | Any payload metadata/content change changes this hash |
| `source_bundle_sha256` | canonical JSON SHA of `source_files`; DB row must match payload | `bfa6755f9edd0d24750e3d7045cfbd5c1bf02a48b96861b2182e2fb725cd1f6a`, matched DB row | Same if source files/source rows stay unchanged | Same if source files/source rows stay unchanged; must re-read if data changes | `funding_source_file_digest_mismatch` | Changes only when `source_files` content changes, not from DB metadata alone |
| schema version | payload schema and DB row | `FUNDING_SOURCE_SNAPSHOT_SCHEMA_V1` | `FUNDING_SOURCE_SNAPSHOT_SCHEMA_V1` | `FUNDING_SOURCE_SNAPSHOT_SCHEMA_V1` | `funding_source_snapshot_schema_unsupported` | Changing schema changes payload/envelope/file hash |
| write_state | DB row, payload, and `snapshot_metadata.write_state` | `committed` in all observed places | `committed` in DB row, payload, and metadata | `committed` in DB row, payload, and metadata | `funding_source_snapshot_unreferenced_or_orphaned` | Changing payload/metadata write state changes envelope/file hash |
| `snapshot_metadata.db_path_reference` | `str(db_path)` passed to verifier | `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db` | `/tmp/qnty_shadow_recommit_copied_db_dry_run_20260707T025834Z/paper_ledger.copied.db` | `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db`, if the real shadow DB is explicitly authorized | `funding_source_snapshot_db_mismatch` | Payload field; changing it changes envelope/file hash |
| `snapshot_metadata.ledger_batch_id` | latest committed target batch id selected from copied DB | `null` | `"17"` for the PR #96 copied DB | current target batch id at the time of any authorized real-shadow recommit; PR #96 context was `"17"` | `funding_source_snapshot_unreferenced_or_orphaned` | Payload field; changing it changes envelope/file hash |
| `snapshot_metadata.batch_start_watermark` | target batch `prior_watermark_bar_ts` | `null` | `2026-07-03T08:00:00` | current target batch prior watermark at the time of authorized real-shadow recommit; PR #96 context was `2026-07-03T08:00:00` | `funding_source_snapshot_db_mismatch` in DB-linked snapshot report | Payload field; changing it changes envelope/file hash |
| `snapshot_metadata.batch_end_watermark` | target batch `new_watermark_bar_ts` | `null` | `2026-07-05T16:00:00` | current target batch new watermark at the time of authorized real-shadow recommit; PR #96 context was `2026-07-05T16:00:00` | `funding_source_snapshot_db_mismatch` in DB-linked snapshot report | Payload field; changing it changes envelope/file hash |
| `snapshot_metadata.pending_batch_id` | not enforced by current verifier for committed acceptance | `null` | not required for copied committed acceptance; writer-generated committed snapshots may retain their pending id | not required for committed acceptance unless future code supplies an expected pending id | none observed for current committed verifier path | Payload field if changed; changing it changes envelope/file hash |
| `batch_identity_matches` | snapshot metadata boolean | `true` | `true` | `true` | `funding_source_snapshot_unreferenced_or_orphaned` | Payload field; changing it changes envelope/file hash |
| `evaluation_identity_matches` | snapshot metadata boolean | `true` | `true` | `true` | `funding_source_snapshot_unreferenced_or_orphaned` | Payload field; changing it changes envelope/file hash |
| `lane.output_dir` | `str(db_path.parent)` | `/srv/qnty/output/paper_pnl_null_shadow_v0` | `/tmp/qnty_shadow_recommit_copied_db_dry_run_20260707T025834Z` | `/srv/qnty/output/paper_pnl_null_shadow_v0`, if real shadow recommit is explicitly authorized | `funding_source_snapshot_db_mismatch` | Payload field; changing it changes envelope/file hash |
| `lane.lane_id` | verifier config expected lane id | `paper_pnl_null_shadow_v0`, matched expected lane | `paper_pnl_null_shadow_v0` for copied shadow config | `paper_pnl_null_shadow_v0` for real shadow | `funding_source_snapshot_db_mismatch` | Payload field; changing it changes envelope/file hash |
| batch evaluation window | `_batch_evaluation_window` from latest committed target batch | PR #96 snapshot evaluation window was full-ledger, not batch-scoped | Required for batch clean only: `2026-07-03T08:00:00Z -> 2026-07-05T16:00:00Z` | Current target batch prior/new window if batch clean is intended | `funding_source_batch_window_mismatch` | Payload field; changing it changes envelope/file hash |
| full-ledger evaluation window | `_funding_evaluation_window(conn)` over full committed funding ledger | `2026-06-25T08:00:00Z -> 2026-07-05T16:00:00Z`, matched full-ledger gate | Required for full-ledger clean: `2026-06-25T08:00:00Z -> 2026-07-05T16:00:00Z` for the copied DB | Current full-ledger funding span if real shadow recommit is authorized | `funding_source_snapshot_window_mismatch` | Payload field; changing it changes envelope/file hash |

## Hash-Order / Build-Order Diagnosis

Required sequence for a copied-DB full-ledger clean-carry dry run:

1. Read the copied DB target batch and source rows read-only or from copied
   artifacts.
2. Build the payload with final copied-DB metadata already set:
   `lane.output_dir = str(copied_db.parent)`,
   `snapshot_metadata.db_path_reference = str(copied_db)`,
   `snapshot_metadata.ledger_batch_id = "17"`,
   `snapshot_metadata.batch_start_watermark = "2026-07-03T08:00:00"`,
   `snapshot_metadata.batch_end_watermark = "2026-07-05T16:00:00"`,
   committed write states, matching identity booleans, and the intended
   full-ledger evaluation window.
3. Build the envelope and compute envelope `snapshot_sha256` after metadata is
   final.
4. Serialize the final envelope deterministically as the writer does
   (`ensure_ascii=True`, `indent=2`, `sort_keys=True`, trailing newline).
5. Compute the final sidecar file SHA from the final bytes on disk.
6. Write the snapshot under copied DB parent
   `funding_source_snapshots/`; writer-compatible naming uses
   `funding_source_snapshot_v1_<source_bundle_sha256>.json`.
7. Update only the copied DB latest target batch row with:
   final sidecar path, final file SHA, payload `source_bundle_sha256`, schema
   version, `committed` write state, and created_at.
8. Run the verifier against only the copied DB.

Hash conclusions:

- Changing metadata changes the payload, therefore changes envelope
  `snapshot_sha256`.
- Changing metadata changes the serialized sidecar bytes, therefore changes the
  sidecar file SHA.
- Moving an unchanged sidecar file to a different path does not itself change
  the file SHA, but a path-aligned copied-DB sidecar must change metadata values
  such as `lane.output_dir` and `db_path_reference`; those metadata changes do
  change the hashes.
- DB row `funding_source_snapshot_sha256` expects the sidecar file-byte SHA, not
  envelope `snapshot_sha256`.
- Envelope `snapshot_sha256` is still validated independently from the file SHA.
- DB row `funding_source_snapshot_bundle_sha256` expects payload
  `source_bundle_sha256`.
- The filename should use `source_bundle_sha256` for writer compatibility, but
  verifier acceptance is driven by the exact DB row path, sidecar containment,
  file SHA, envelope validation, and metadata.
- The candidate path must live under the copied DB parent
  `funding_source_snapshots/`; PR #96 satisfied this final layout requirement.
- PR #96 used the file SHA correctly and used the source bundle SHA correctly.
- PR #96 did not rebuild the envelope after aligning copied DB metadata. It
  reused a valid full-ledger candidate envelope whose metadata still described
  the real shadow DB and omitted batch linkage.

Root-cause classification:

- Wrong `db_path_reference`: yes, caused
  `funding_source_snapshot_db_mismatch`.
- Wrong `lane.output_dir`: yes, caused
  `funding_source_snapshot_db_mismatch`.
- Missing `ledger_batch_id`: yes, caused
  `funding_source_snapshot_unreferenced_or_orphaned`.
- Missing batch start/end watermarks: yes, caused DB-linked mismatch details and
  `funding_source_snapshot_db_mismatch`.
- Snapshot path not under expected lane/copy directory: no for the final PR #96
  copied run; the sidecar lived under copied DB parent `funding_source_snapshots/`.
- Hash-order problem after metadata rewrite: no evidence. The problem is that
  the metadata rewrite did not happen. A metadata rewrite would require
  recomputing envelope and file hashes before patching the copied DB row.
- Verifier expecting sidecar under a specific relative directory: yes. It expects
  the DB-referenced sidecar to resolve under `db_path.parent/funding_source_snapshots`.
- Batch clean-carry additionally failed because the reused candidate was a
  full-ledger snapshot, while the batch-scoped gate compares the snapshot
  evaluation window to the target batch window.

## Does This Require Production Code Change?

`NO_PROD_CHANGE_REQUIRED_YET`

Evidence:

- Current tests already prove an exact committed DB reference can return
  `CLEAN_NET_OF_CARRY` in a tmp synthetic DB.
- Current writer code already builds pending metadata, rewrites committed
  metadata with `ledger_batch_id`, rebuilds the envelope, computes the final file
  SHA, and only then updates the DB reference row.
- PR #96 failed at copied-artifact construction, not at an identified verifier
  implementation gap: the copied DB row pointed to a sidecar whose metadata still
  referenced the real shadow DB and had no target batch id/watermarks.
- A new copied-DB dry run should rebuild the candidate envelope with copied DB
  and target batch metadata aligned before computing hashes and patching the
  copied DB row.

Open caveat:

- A single full-ledger snapshot is expected to target the full-ledger
  clean-carry gate. It will not also satisfy batch-scoped clean-carry unless its
  evaluation window is batch-scoped or the design provides a separate batch
  snapshot reference. The next dry run should state whether it is proving
  full-ledger DB-linked clean-carry only or both full-ledger and batch-scoped
  clean-carry.

## Recommended Next Action

`FUNDING_SOURCE_RECOMMIT_COPIED_DB_METADATA_ALIGNED_DRY_RUN_GIT_OWNED`

Purpose:

- rebuild the candidate full-ledger snapshot with metadata aligned to the copied
  DB and batch `17`;
- compute envelope `snapshot_sha256` and sidecar file SHA after metadata
  finalization;
- patch only the copied DB row;
- run verifier against only the copied DB;
- expect full-ledger DB-linked clean-carry to clear unless a new, currently
  unseen verifier requirement appears.

Do not recommend real DB mutation yet.

## Impact On Existing Receipts

- PR #96 remains valid: it proved copied DB patch mechanics, sidecar discovery,
  parsing, file SHA, bundle SHA, source digest, and full-ledger window behavior.
- PR #95 remains valid: the pure full-ledger candidate can clear digest/window
  gates in helper evaluation.
- PR #94 tests remain valid: digest/window semantics remain pinned.
- PR #92 diagnosis remains valid: stale current committed evidence still must
  not be relabeled as clean.
- This receipt does not prove edge.
- This receipt does not change official reports.

## Non-Goals

- no code change
- no test change
- no schema change
- no verifier code change
- no reporter change
- no writer change
- no trader change
- no strategy change
- no real DB writes
- no prod/shadow writer run
- no deployment
- no backfill
- no official report overwrite
- no live integration
- no shorting
- no trial registry
- no null/benchmark lane changes

## Verification Before Commit

- code/test inspection as scoped above: completed.
- PR #96 artifact inspection: completed against the VM `/tmp` copied-DB
  workspace; copied DB opened with immutable/query-only SQLite URI only.
- `.venv/bin/python -m pytest tests/test_funding_source_digest_window_semantics.py`:
  `7 passed`.
- `.venv/bin/python -m pytest tests/test_paper_sqlite_verifier_db_linked_snapshot_selector.py`:
  `19 passed`.
- `.venv/bin/python -m pytest tests/test_paper_sqlite_verify_batch_scoped_clean_carry.py`:
  `10 passed`.
- `.venv/bin/python -m pytest tests/test_funding_source_snapshot_schema.py`:
  `18 passed`.
- `git diff --check`: passed.
- `git diff --name-only` with intent-to-add before staging: exactly
  `docs/status/funding_source_recommit_blocker_diagnosis_2026-07-07.md`.
- `git diff --cached --name-only` before commit: exactly
  `docs/status/funding_source_recommit_blocker_diagnosis_2026-07-07.md`.
- `git diff --name-only main...HEAD` after local commit: exactly
  `docs/status/funding_source_recommit_blocker_diagnosis_2026-07-07.md`.
- `git status --short --branch`: one staged diagnosis receipt before commit,
  plus existing untracked `.claude/`.

## Verdict

`FUNDING_SOURCE_RECOMMIT_BLOCKER_DIAGNOSIS_RECORDED`
