# QNTY Funding Source Metadata-Aligned Copied-DB Dry Run — 2026-07-07

## Status Boundary

- `EDGE_UNPROVEN` remains.
- `BLOCK_LIVE_INTEGRATION` remains.
- Real full-ledger `CAVEATED_ENGINE_SEMANTICS` remains until a real DB-linked
  verifier run proves otherwise. This copied-DB result does not change the real
  shadow DB label.
- This is a copied-DB dry run only.
- This receipt does not mutate real prod/shadow DBs.
- This receipt does not overwrite official verifier reports.
- This receipt does not run writer/trader/live code.
- This receipt does not backfill historical rows.
- This receipt does not recommit snapshots to the real DB.
- This receipt is not edge, profitability, statistical-significance, shorting,
  live-readiness, or deployment evidence.

## Scope

- date: 2026-07-07.
- PR #98 merge SHA: `9f6f5e93fecdb1180ff09568305e7aac7fcb1849`.
- PR #97 merge SHA (merged in this task): `365d1b16cac0ff2264378c6d081c4dc7de1f5cd2`.
- local repo head (branch base): `365d1b16cac0ff2264378c6d081c4dc7de1f5cd2`.
- branch name: `docs/funding-source-metadata-aligned-copied-db-dry-run`.
- output doc path:
  `docs/status/funding_source_metadata_aligned_copied_db_dry_run_2026-07-07.md`.
- VM workspace:
  `/tmp/qnty_shadow_metadata_aligned_copied_db_dry_run_20260707T144147Z`.
- copied DB path:
  `/tmp/qnty_shadow_metadata_aligned_copied_db_dry_run_20260707T144147Z/paper_ledger.copied.db`.
- real shadow DB path:
  `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db`.
- official shadow report path:
  `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_verify_report.json`.
- data dir path: `/srv/qnty/repo/data`.
- current local code copied to VM `/tmp`:
  `/tmp/qnty-meta-aligned-code-365d1b16cac0ff2264378c6d081c4dc7de1f5cd2`.
- VM repo path/head/status: `/srv/qnty/repo` @
  `2bd88430fe6b2881aaa2b32947002217d3e02ba5`, status `## main...origin/main`
  (clean; **not modified**).
- MemPalace: used for **recall only** (qnty wing — recommit status, guardrails,
  PR #96/#97 blocker). Source of truth remained git, `CLAUDE.md`, `docs/status/`,
  verifier output. No new paths mined; no hooks/autosave enabled.

## Method

- PR #97 (`docs: diagnose funding source recommit blocker`) was OPEN, docs-only,
  changed only `docs/status/funding_source_recommit_blocker_diagnosis_2026-07-07.md`,
  `MERGEABLE`/`CLEAN`. Squash-merged (SHA `365d1b1`); local `main`
  fast-forwarded. PR #98 confirmed merged with `CLAUDE.md`, `.mcp.json`, and
  `docs/status/mempalace_qnty_project_mcp_config_2026-07-07.md` present on `main`.
- Metadata-aligned candidate build: on the VM, using the current **local** code
  copied to `/tmp` and the production **pure** builder plus the production writer
  glue (`build_funding_source_snapshot_payload_v1`,
  `build_funding_source_snapshot_envelope_v1`,
  `validate_funding_source_snapshot_envelope_v1`,
  `_required_funding_windows_for_snapshot`, `_read_funding_source_csv_rows`),
  under `/srv/qnty/venv/bin/python` (numpy/pandas available). Full-ledger required
  windows were derived from the copied `funding` table (read-only); source rows and
  digests from the current `/srv/qnty/repo/data` CSVs.
- Hash/build order (per PR #97 diagnosis): build payload with final copied-DB
  metadata → build envelope → compute `snapshot_sha256` (helper) → serialize JSON
  deterministically → compute sidecar **file** SHA → write sidecar under the copied
  DB parent `funding_source_snapshots/` → patch copied DB batch 17 row (file SHA in
  `funding_source_snapshot_sha256`, `source_bundle_sha256` in
  `funding_source_snapshot_bundle_sha256`) → read back row → run verifier.
- Copied DB patch: updated only the copied DB latest committed `ledger_batches`
  row (batch 17). `PRAGMA journal_mode=DELETE` kept it a single file.
- Copied DB verifier: current local code, `PYTHONPATH` at the `/tmp` copy, against
  only the copied DB, `--read-only --json --data-dir /srv/qnty/repo/data`.
- Real artifact integrity re-checked before/after.
- No writes to `/srv/qnty/output`. No writes to `/srv/qnty/repo`. No official
  report overwrite. No real DB mutation.

## Source Integrity

| Artifact | size before → after | mtime before → after | sha256 before → after | Match |
|---|---:|---|---|---|
| Real shadow DB | 172032 → 172032 | 1783312420 (2026-07-06T04:33:40Z) → same | `3cbc6e9c…c739a897` → same | ✅ |
| Official shadow report | 3531 → 3531 | 1782929757 (2026-07-01T18:15:57Z) → same | `653605a7…f14e0ffd` → same | ✅ |
| VM repo | `2bd88430…d3e02ba5` → same | status `## main...origin/main` → same | n/a | ✅ |
| Real shadow output dir (aggregate) | unchanged | unchanged | `1250f82d…fcccf770` → same | ✅ |

- Current funding CSV digests (identical before and after the run — used by both
  the build and the verifier):
  - `BNBUSDT_8h_funding.csv` `ad40bf885bb71dd43fd3dda2aafc70fd0ebcaafb31e94a9fb091110e5d170ef3`
  - `BTCUSDT_8h_funding.csv` `65c66a32ed97638bd80ac6110b484a8d96707f6d9e80d57313e2295210750c8e`
  - `ETHUSDT_8h_funding.csv` `e9b3423bd567bd1724a2d1819300b6f6c7ac8f49fa406a2b68f504996db467a9`
  - `SOLUSDT_8h_funding.csv` `a0980a1a1e154a2282601b98210e1d80ce7bafef0cc66ee1acbac3f66a15cf6a`
  - `XRPUSDT_8h_funding.csv` `2e9b5971bd324d13a4939abacfa4e921cf0850b3b70bb83d4d68909dbc00a560`
- Note: these differ from PR #95/#96 digests (`8dc595c1…`, `5369211f…`, …); the
  source CSVs were refreshed again after PR #95. The candidate was therefore
  **rebuilt** against current source, so build-time and verify-time digests stay
  internally consistent (both read the same current CSVs).
- No writer/trader/live/backfill processes were running during the run.
- verdict: `FUNDING_SOURCE_METADATA_ALIGNED_READ_ONLY_SOURCE_UNCHANGED`.

## Candidate Snapshot

- sidecar path:
  `…/funding_source_snapshots/funding_source_snapshot_v1_8b9d80408b5aae517ba745a5072d9f7d09125572a23ea5e792e2d80e9c099d69.json`.
- envelope `snapshot_sha256`:
  `2ae8d19bf94d124d217bb31a02932cd5e220865538a19849dbc842dd2b813702`.
- sidecar file sha256:
  `af8a7d04a41ffc6be167ec406cc64ecd686b11d52e99462c37ca82f98fc553db`.
- `source_bundle_sha256`:
  `8b9d80408b5aae517ba745a5072d9f7d09125572a23ea5e792e2d80e9c099d69`.
- schema version: `FUNDING_SOURCE_SNAPSHOT_SCHEMA_V1`.
- write_state: `committed`.
- created_at / generated_at_utc: `2026-07-07T14:41:47Z`.
- evaluation window (full-ledger): `2026-06-25T08:00:00Z -> 2026-07-05T16:00:00Z`.
- symbols covered: `BNBUSDT`, `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `XRPUSDT`.
- required windows: count `59`; span `2026-06-25T08:00:00 -> 2026-07-05T16:00:00`.
- coverage decision: `complete`; payload reason codes: `[]`; envelope validation:
  OK; source rows read: `27565`.
- aligned metadata:
  - `lane.lane_id` = `paper_pnl_null_shadow_v0` (= copied DB `paper_config.lane_id`;
    verifier `_expected_snapshot_lane_id`).
  - `lane.output_dir` =
    `/tmp/qnty_shadow_metadata_aligned_copied_db_dry_run_20260707T144147Z` (copied
    DB parent).
  - `snapshot_metadata.db_path_reference` = copied DB path.
  - `snapshot_metadata.ledger_batch_id` = `"17"`.
  - `snapshot_metadata.batch_start_watermark` = `2026-07-03T08:00:00`.
  - `snapshot_metadata.batch_end_watermark` = `2026-07-05T16:00:00`.
  - `snapshot_metadata.batch_identity_matches` = `true`;
    `snapshot_metadata.evaluation_identity_matches` = `true`;
    `snapshot_metadata.write_state` = `committed`.
- source file digests (payload):
  - `BNBUSDT` full `ad40bf88…d170ef3`, row-subset `8f987abc3ff9c623d3971910f26c33dfb75c247d2062c61363377819ab4feec6`
  - `BTCUSDT` full `65c66a32…750c8e`, row-subset `9f1203b1ffac7ceb200f45179b37e43d02d0ed645a9c6f7d30f4ba2325612c82`
  - `ETHUSDT` full `e9b3423b…6db467a9`, row-subset `0314efc0dfdb33e8f3f0dd55c9d06d7ee658d2201eda6d71f7269e893b8778d5`
  - `SOLUSDT` full `a0980a1a…f66a15cf6a`, row-subset `3554be0535859b7ceafd4ff422887a7999198ceaba8c65610ce96bf1c8d4f07c`
  - `XRPUSDT` full `2e9b5971…dbc00a560`, row-subset `7678c982c2383f90a08d1b5a3cbc13bd64d11e20f1fde91423aa8232ac38b1b6`

## Copied DB Patch

- copied DB path:
  `/tmp/qnty_shadow_metadata_aligned_copied_db_dry_run_20260707T144147Z/paper_ledger.copied.db`.
- copied DB sha initial (== real shadow DB):
  `3cbc6e9c63c74072aa019d6a53b1f5519f369f95cec1f9c21495e307c739a897`.
- copied DB sha after patch:
  `c3d426834be531b545b10f7e40f2a385175e1bc9afb45446dd30c77cac00ea58`.
- copied DB sha after verifier:
  `c3d426834be531b545b10f7e40f2a385175e1bc9afb45446dd30c77cac00ea58` (unchanged by
  verifier).
- target batch id: `17`; patched row count: `1`; no `-wal`/`-shm` created.

Old copied-DB snapshot fields (from real shadow batch 17):

```json
{
  "funding_source_snapshot_bundle_sha256": "1c5b433eb3adc345bdf024f20b45ffba874e77090ab5fc652f81fe169791451b",
  "funding_source_snapshot_created_at": "2026-07-06T04:33:09Z",
  "funding_source_snapshot_path": "/srv/qnty/output/paper_pnl_null_shadow_v0/funding_source_snapshots/funding_source_snapshot_v1_1c5b433eb3adc345bdf024f20b45ffba874e77090ab5fc652f81fe169791451b.json",
  "funding_source_snapshot_schema_version": "FUNDING_SOURCE_SNAPSHOT_SCHEMA_V1",
  "funding_source_snapshot_sha256": "730455698eb58e72dd7586d52f0e064350ace8dcbc077eddadeb85d740bfe8a7",
  "funding_source_snapshot_write_state": "committed"
}
```

New copied-DB snapshot fields (metadata-aligned candidate):

```json
{
  "funding_source_snapshot_bundle_sha256": "8b9d80408b5aae517ba745a5072d9f7d09125572a23ea5e792e2d80e9c099d69",
  "funding_source_snapshot_created_at": "2026-07-07T14:41:47Z",
  "funding_source_snapshot_path": "/tmp/qnty_shadow_metadata_aligned_copied_db_dry_run_20260707T144147Z/funding_source_snapshots/funding_source_snapshot_v1_8b9d80408b5aae517ba745a5072d9f7d09125572a23ea5e792e2d80e9c099d69.json",
  "funding_source_snapshot_schema_version": "FUNDING_SOURCE_SNAPSHOT_SCHEMA_V1",
  "funding_source_snapshot_sha256": "af8a7d04a41ffc6be167ec406cc64ecd686b11d52e99462c37ca82f98fc553db",
  "funding_source_snapshot_write_state": "committed"
}
```

Exact SQL:

```sql
UPDATE ledger_batches
SET funding_source_snapshot_path = ?,
    funding_source_snapshot_sha256 = ?,
    funding_source_snapshot_bundle_sha256 = ?,
    funding_source_snapshot_schema_version = ?,
    funding_source_snapshot_write_state = ?,
    funding_source_snapshot_created_at = ?
WHERE batch_id = ?
```

Parameters:

```text
/tmp/qnty_shadow_metadata_aligned_copied_db_dry_run_20260707T144147Z/funding_source_snapshots/funding_source_snapshot_v1_8b9d80408b5aae517ba745a5072d9f7d09125572a23ea5e792e2d80e9c099d69.json
af8a7d04a41ffc6be167ec406cc64ecd686b11d52e99462c37ca82f98fc553db
8b9d80408b5aae517ba745a5072d9f7d09125572a23ea5e792e2d80e9c099d69
FUNDING_SOURCE_SNAPSHOT_SCHEMA_V1
committed
2026-07-07T14:41:47Z
17
```

The verifier expects `funding_source_snapshot_sha256` = sidecar **file** SHA and
`funding_source_snapshot_bundle_sha256` = payload `source_bundle_sha256`; both were
patched accordingly.

## Copied DB Verifier Evidence

Exact command:

```bash
PYTHONPATH=/tmp/qnty-meta-aligned-code-365d1b16cac0ff2264378c6d081c4dc7de1f5cd2 \
  /srv/qnty/venv/bin/python -m quantbot.paper.sqlite_verify \
  --db-path /tmp/qnty_shadow_metadata_aligned_copied_db_dry_run_20260707T144147Z/paper_ledger.copied.db \
  --read-only \
  --json \
  --data-dir /srv/qnty/repo/data \
  > /tmp/qnty_shadow_metadata_aligned_copied_db_dry_run_20260707T144147Z/verify_copied_db.json \
  2> /tmp/qnty_shadow_metadata_aligned_copied_db_dry_run_20260707T144147Z/verify_copied_db.err
```

- cwd: `/tmp/qnty-meta-aligned-code-365d1b16cac0ff2264378c6d081c4dc7de1f5cd2`.
- PYTHONPATH: `/tmp/qnty-meta-aligned-code-365d1b16cac0ff2264378c6d081c4dc7de1f5cd2`.
- python executable: `/srv/qnty/venv/bin/python` (resolves to `/usr/bin/python3.12`).
- exit code: `0`.
- stdout path/size/sha:
  `…/verify_copied_db.json`, `10803` bytes,
  `837b5c9bbbdff6be5cd35640df9a60a1d30cd1ec35812f1080f66a98f4a5d572`.
- stderr path/size/sha:
  `…/verify_copied_db.err`, `0` bytes,
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
- verifier status: `OK`; failure_count: `0`; watermark: `2026-07-05T16:00:00`.
- `funding_source_snapshot_status`: `present_valid` (selector `ledger_batches`,
  db_linked `true`, target_batch_id `17`).
- `source_path_available`: `true`; `resolved_funding_source_dir`:
  `/srv/qnty/repo/data`.
- `db_mutation_performed`: `false`; `sqlite_open_mode`:
  `file_uri_mode_ro_immutable`; `wal_shm_files_created`: `false`.
- resum check: `status ok`, `funding_rows 59`, `funding_amount_sum 3.44000686`,
  `ledger_state_funding_cum 3.4400068507…`, `tolerance_abs 1e-06`; arithmetic OK.

Full-ledger clean-carry:

- decision: `CLEAN_NET_OF_CARRY`.
- status: `clean_net_of_carry`.
- reason codes: `[]`.
- snapshot lane_id `paper_pnl_null_shadow_v0`, lane_output_dir = copied DB parent,
  db_path_reference = copied DB, ledger_batch_id `17`.

Batch clean-carry:

- decision: `CAVEATED_ENGINE_SEMANTICS`.
- status: `refused_db_or_lane_mismatch`.
- reason codes: `funding_source_batch_window_mismatch` (only).
- batch evaluation window `2026-07-03T08:00:00Z -> 2026-07-05T16:00:00Z`;
  full-ledger window `2026-06-25T08:00:00Z -> 2026-07-05T16:00:00Z`. The
  full-ledger candidate window deliberately differs from the batch window, so the
  batch gate reports a window mismatch **by design**. The PR #96 batch
  `funding_source_snapshot_unreferenced_or_orphaned` reason is now **absent**.

Target reason-code presence (all **absent**):

- `funding_source_file_digest_mismatch`: absent.
- `funding_source_snapshot_window_mismatch`: absent.
- `funding_source_snapshot_db_mismatch`: absent.
- `funding_source_snapshot_unreferenced_or_orphaned`: absent.

Result label: `METADATA_ALIGNED_COPIED_DB_FULL_LEDGER_CLEARS`.

## Clean-Carry Gate Comparison

| Evidence surface | Digest gate | Full-ledger window | Batch window | Coverage | DB-linked verifier gate |
|---|---|---|---|---|---|
| Real committed shadow DB (current) | fails vs refreshed source | fails full-ledger window | clears batch window | complete | caveated |
| PR #95 `/tmp` pure full-ledger candidate | clears | clears | fails (by design) | complete | not DB-linked |
| PR #96 copied DB (PR #95 candidate, stale metadata) | clears | clears | batch window mismatch | complete | fails DB/lane + orphan |
| **This metadata-aligned copied DB** | **clears** | **clears** | batch window mismatch (by design) | complete | **`present_valid` → `CLEAN_NET_OF_CARRY`** |

- This run is the first to drive the **DB-linked** full-ledger clean-carry gate to
  `CLEAN_NET_OF_CARRY` on a copied DB: the six DB reference fields, the sidecar
  file/bundle/schema hashes, the lane/output_dir/db_path/watermark/ledger_batch_id
  metadata, and the full-ledger digest+window checks all align simultaneously.
- The batch gate remaining window-caveated is expected: a full-ledger snapshot
  window is not the batch watermark window under strict equality; the orphan/DB
  metadata caveats that PR #96 also carried are now gone.

## Impact On Existing Receipts

- PR #92 diagnosis remains valid: the real committed shadow snapshot is still
  stale-digest + batch-window-scoped for current source; unchanged by this run.
- PR #93 plan remains valid: this is the copied-DB dry-run step; the real DB
  recommit remains gated behind explicit later approval.
- PR #94 tests remain valid: strict digest/window semantics reproduced (54/54
  scoped tests pass).
- PR #95 remains valid: its pure full-ledger candidate cleared digest/window; this
  run extends that to the DB-linked path with aligned metadata (new digests reflect
  the later source refresh).
- PR #96 remains valid: it proved the copied DB is patchable and the sidecar
  parseable, and identified the exact DB/lane/watermark/batch metadata gaps this
  run closes.
- PR #97 diagnosis is confirmed: rebuilding the candidate envelope with copied-DB /
  batch-aligned metadata and file/bundle hashes in the correct order clears the
  DB-linked full-ledger gate.
- PR #98 config is unaffected.
- This run updates no real DB-linked snapshot reference and no official report.

## Recommended Next Action

`FUNDING_SOURCE_SNAPSHOT_REAL_DB_RECOMMIT_PLAN_GIT_OWNED`

- Purpose: plan the exact real shadow-DB recommit — backup, hash gates, exact SQL,
  rollback, and a post-recommit real-DB verifier receipt — now that a copied-DB
  dry run clears the DB-linked full-ledger clean-carry gate.
- The plan PR must still make **no** real DB mutation; it only records the
  authorized procedure and safety gates for a later, explicitly approved recommit.
- The plan must account for source-digest freshness at recommit time (the candidate
  must be rebuilt against whatever source is current when the recommit runs, exactly
  as this run rebuilt against the latest refreshed CSVs).

## Non-Goals

- no code change
- no test change
- no schema change
- no verifier / reporter / writer change
- no trader / strategy change
- no real prod/shadow DB writes
- no prod/shadow writer run
- no deployment
- no backfill
- no official report overwrite
- no live integration
- no shorting
- no trial registry change
- no null/benchmark lane changes
- no `/srv/qnty/repo` or `/srv/qnty/output` changes
- no MemPalace hooks/autosave; recall-only; no new path mining

## Verdict

`FUNDING_SOURCE_METADATA_ALIGNED_COPIED_DB_DRY_RUN_RECORDED`

The metadata-aligned copied-DB dry run drove the DB-linked full-ledger clean-carry
gate to `CLEAN_NET_OF_CARRY` with an empty reason set, while making no real DB
mutation and no official report overwrite. `EDGE_UNPROVEN`,
`BLOCK_LIVE_INTEGRATION`, and real full-ledger `CAVEATED_ENGINE_SEMANTICS` are
preserved; the real shadow DB label changes only when a real DB-linked verifier run
proves it under explicit later approval.
