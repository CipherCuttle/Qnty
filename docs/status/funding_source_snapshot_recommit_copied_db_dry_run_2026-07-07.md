# QNTY Funding Source Snapshot Recommit Copied-DB Dry Run — 2026-07-07

## Status Boundary

- `EDGE_UNPROVEN` remains.
- `BLOCK_LIVE_INTEGRATION` remains.
- Real full-ledger `CAVEATED_ENGINE_SEMANTICS` remains until a real DB-linked
  verifier run proves otherwise.
- This is a copied-DB dry run only.
- This receipt does not prove edge, profitability, statistical significance,
  shorting readiness, live readiness, or production deployment.
- This receipt does not mutate real prod/shadow DBs.
- This receipt does not backfill historical rows.
- This receipt does not overwrite official reports.
- This receipt does not recommit snapshots to the real DB.
- This receipt does not run writer/trader/live code.
- This receipt does not promote `/tmp` output to official report.

## Scope

- date: 2026-07-07.
- PR #95 merge SHA: `74577ac5f190eb22b4c7bb3722c09679a18b37f9`.
- local repo head: `74577ac5f190eb22b4c7bb3722c09679a18b37f9`.
- branch name: `docs/funding-source-recommit-copied-db-dry-run`.
- output doc path:
  `docs/status/funding_source_snapshot_recommit_copied_db_dry_run_2026-07-07.md`.
- VM repo path/head/status: `/srv/qnty/repo` @
  `2bd88430fe6b2881aaa2b32947002217d3e02ba5`, status
  `## main...origin/main` before and after.
- current local code copy used on VM:
  `/tmp/qnty-copied-db-verify-74577ac5f190eb22b4c7bb3722c09679a18b37f9`.
- temp workspace path:
  `/tmp/qnty_shadow_recommit_copied_db_dry_run_20260707T025834Z`.
- copied DB path:
  `/tmp/qnty_shadow_recommit_copied_db_dry_run_20260707T025834Z/paper_ledger.copied.db`.
- full-ledger candidate snapshot path used by verifier:
  `/tmp/qnty_shadow_recommit_copied_db_dry_run_20260707T025834Z/funding_source_snapshots/funding_source_snapshot_v1_bfa6755f9edd0d24750e3d7045cfbd5c1bf02a48b96861b2182e2fb725cd1f6a.json`.
- original PR #95 full-ledger candidate path:
  `/tmp/funding_source_snapshot_candidate_full_ledger_20260707T000000Z.json`.
- shadow DB path:
  `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db`.
- prod DB path, read-only PnL only:
  `/srv/qnty/output/paper_pnl_v1/paper_ledger.db`.
- official shadow report path:
  `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_verify_report.json`.
- data dir path: `/srv/qnty/repo/data`.
- outputs were written only to `/tmp`: yes. The copied DB, candidate copy,
  verifier stdout/stderr, and evidence JSON stayed under the final temp workspace.
- a prior `/tmp`-only path-shape probe was not used as final evidence; it showed
  the verifier requires snapshots under the copied DB parent `funding_source_snapshots/`
  directory. No real artifact changed during that probe.

## Method

- Stage A source integrity: collected real shadow DB, official shadow report,
  VM repo, shadow output-dir listing/hash, candidate snapshot, and immutable
  SQLite schema/row facts before the copied-DB run.
- Stage B read-only PnL snapshot: opened prod and shadow DBs with
  `file:<path>?mode=ro&immutable=1` and `PRAGMA query_only=ON`; queried only paper
  accounting tables for a side-context PnL comparison.
- Stage C copied DB workspace: created a fresh `/tmp` workspace, copied the real
  shadow DB to `paper_ledger.copied.db`, and copied the full-ledger candidate into
  the verifier-expected `funding_source_snapshots/` subdirectory.
- Stage D copied DB patch: updated only the copied DB latest committed
  `ledger_batches` row to reference the full-ledger candidate.
- Stage E verifier run: ran current local code copied to VM `/tmp`, with
  `PYTHONPATH` pointed at that copy, against only the copied DB.
- Stage F integrity checks: re-collected real shadow DB, official report, VM repo,
  and real shadow output-dir signatures after the verifier run.
- No writes to `/srv/qnty/output`.
- No writes to `/srv/qnty/repo`.
- No official report overwrite.
- No real DB mutation.

## Source Integrity

| Artifact | size before -> after | mtime before -> after | sha256 before -> after | Match |
|---|---:|---|---|---|
| Real shadow DB | 172032 -> 172032 | 2026-07-06T04:33:40.934545Z -> same | `3cbc6e9c63c74072aa019d6a53b1f5519f369f95cec1f9c21495e307c739a897` -> same | yes |
| Official shadow report | 3531 -> 3531 | 2026-07-01T18:15:57.143526Z -> same | `653605a76fdd0b8117c8373c9dadd3fcd41bed147778920c82f29f19f14e0ffd` -> same | yes |
| VM repo | `2bd88430fe6b2881aaa2b32947002217d3e02ba5` -> same | status `## main...origin/main` -> same | n/a | yes |
| Real shadow output dir | 16 files -> 16 files | aggregate unchanged | `d4912875ac1eaf47052819f9f61204131866221f7f5d61e9e7dcbb0416e08a63` -> same | yes |

- candidate file sha256 confirmed:
  `f5efc760471d39e0f8031d31c61dfd8fd70c436d0c44e59965659d753d886a39`.
- candidate envelope `snapshot_sha256`:
  `5c635e7e08e6b6708ddf9e42c3fd3d42a7ddd9fa558ec7c395fbdadaedb14645`.
- candidate `source_bundle_sha256`:
  `bfa6755f9edd0d24750e3d7045cfbd5c1bf02a48b96861b2182e2fb725cd1f6a`.
- candidate evaluation window:
  `2026-06-25T08:00:00Z -> 2026-07-05T16:00:00Z`.
- candidate schema version: `FUNDING_SOURCE_SNAPSHOT_SCHEMA_V1`.
- candidate coverage decision: `complete`; candidate payload reason codes: `[]`.
- latest real shadow committed batch id: `17`.
- latest real shadow batch window:
  `2026-07-03T08:00:00 -> 2026-07-05T16:00:00`.
- real shadow funding symbols:
  `BNBUSDT`, `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `XRPUSDT`.
- verdict:
  `FUNDING_SOURCE_RECOMMIT_COPIED_DB_REAL_ARTIFACTS_UNCHANGED`.

## Fun PnL Snapshot — Prod vs Shadow

This section is side context only. It is paper accounting, not edge evidence.

| Lane | latest batch | latest watermark | latest equity | realized gross | realized net closed | unrealized | fees | funding | open positions | closed trades |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| prod | 49 | 2026-07-06T16:00:00 | 10336.66272307 | -36.61557032 | -43.91342549 | 387.09182301 | 9.48169221 | 4.33183741 | 5 | 7 |
| shadow | 17 | 2026-07-05T16:00:00 | 10350.80781593 | -25.40311929 | -28.58037638 | 385.13824051 | 5.48729844 | 3.44000685 | 5 | 3 |

- prod PnL vs 10000: `+336.66272307`.
- shadow PnL vs 10000: `+350.80781593`.
- lane ahead right now: shadow by `14.14509286`.
- caveat: `PAPER_ONLY_NOT_EDGE_NOT_TRADING_ADVICE`.

## Copied DB Patch

- copied DB path:
  `/tmp/qnty_shadow_recommit_copied_db_dry_run_20260707T025834Z/paper_ledger.copied.db`.
- copied DB sha before patch:
  `3cbc6e9c63c74072aa019d6a53b1f5519f369f95cec1f9c21495e307c739a897`.
- copied DB sha after patch:
  `17ff74328acbeb10b516698b8a80f18e386069de2f5e937853994cbec5c85755`.
- copied DB sha after verifier:
  `17ff74328acbeb10b516698b8a80f18e386069de2f5e937853994cbec5c85755`.
- target batch id: `17`.
- full-ledger candidate file sha:
  `f5efc760471d39e0f8031d31c61dfd8fd70c436d0c44e59965659d753d886a39`.
- full-ledger candidate bundle sha:
  `bfa6755f9edd0d24750e3d7045cfbd5c1bf02a48b96861b2182e2fb725cd1f6a`.
- patch confirmation: the SQL touched only the copied DB under `/tmp`.

Old snapshot fields:

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

New copied-DB snapshot fields:

```json
{
  "funding_source_snapshot_bundle_sha256": "bfa6755f9edd0d24750e3d7045cfbd5c1bf02a48b96861b2182e2fb725cd1f6a",
  "funding_source_snapshot_created_at": "2026-07-07T00:00:00Z",
  "funding_source_snapshot_path": "/tmp/qnty_shadow_recommit_copied_db_dry_run_20260707T025834Z/funding_source_snapshots/funding_source_snapshot_v1_bfa6755f9edd0d24750e3d7045cfbd5c1bf02a48b96861b2182e2fb725cd1f6a.json",
  "funding_source_snapshot_schema_version": "FUNDING_SOURCE_SNAPSHOT_SCHEMA_V1",
  "funding_source_snapshot_sha256": "f5efc760471d39e0f8031d31c61dfd8fd70c436d0c44e59965659d753d886a39",
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
/tmp/qnty_shadow_recommit_copied_db_dry_run_20260707T025834Z/funding_source_snapshots/funding_source_snapshot_v1_bfa6755f9edd0d24750e3d7045cfbd5c1bf02a48b96861b2182e2fb725cd1f6a.json
f5efc760471d39e0f8031d31c61dfd8fd70c436d0c44e59965659d753d886a39
bfa6755f9edd0d24750e3d7045cfbd5c1bf02a48b96861b2182e2fb725cd1f6a
FUNDING_SOURCE_SNAPSHOT_SCHEMA_V1
committed
2026-07-07T00:00:00Z
17
```

Exact fields a later recommit would need are the same six
`ledger_batches.funding_source_snapshot_*` fields. This copied run shows the SQL
shape is not enough by itself: the snapshot JSON metadata also has to be compatible
with the target DB/lane/batch, otherwise the verifier refuses the DB-linked gate.

## Copied DB Verifier Evidence

Exact command:

```bash
PYTHONPATH=/tmp/qnty-copied-db-verify-74577ac5f190eb22b4c7bb3722c09679a18b37f9 \
  /srv/qnty/venv/bin/python -m quantbot.paper.sqlite_verify \
  --db-path /tmp/qnty_shadow_recommit_copied_db_dry_run_20260707T025834Z/paper_ledger.copied.db \
  --read-only \
  --json \
  --data-dir /srv/qnty/repo/data \
  > /tmp/qnty_shadow_recommit_copied_db_dry_run_20260707T025834Z/verify_copied_db.json \
  2> /tmp/qnty_shadow_recommit_copied_db_dry_run_20260707T025834Z/verify_copied_db.err
```

- cwd:
  `/tmp/qnty-copied-db-verify-74577ac5f190eb22b4c7bb3722c09679a18b37f9`.
- python executable: `/srv/qnty/venv/bin/python`.
- exit code: `0`.
- output JSON path:
  `/tmp/qnty_shadow_recommit_copied_db_dry_run_20260707T025834Z/verify_copied_db.json`.
- output JSON size/hash:
  `12742` bytes,
  `2bed43f4c17efca68cc7aeb03ab3dd6df19c467d0fc50e7f76844a12a247c089`.
- stderr path:
  `/tmp/qnty_shadow_recommit_copied_db_dry_run_20260707T025834Z/verify_copied_db.err`.
- stderr size/hash: `0` bytes,
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
- verifier status: `OK`.
- failure_count: `0`.
- watermark: `2026-07-05T16:00:00`.
- source_path_available: `true`.
- resolved_funding_source_dir: `/srv/qnty/repo/data`.
- funding_source_snapshot_status: `present_db_or_lane_mismatch`.
- snapshot_sha256:
  `5c635e7e08e6b6708ddf9e42c3fd3d42a7ddd9fa558ec7c395fbdadaedb14645`.
- source_bundle_sha256:
  `bfa6755f9edd0d24750e3d7045cfbd5c1bf02a48b96861b2182e2fb725cd1f6a`.
- db_mutation_performed: `false`.
- sqlite_open_mode: `file_uri_mode_ro_immutable`.
- wal_shm_files_created: `false`.

Full-ledger clean-carry:

- decision: `CAVEATED_ENGINE_SEMANTICS`.
- status: `refused_db_or_lane_mismatch`.
- reason codes:
  `funding_source_snapshot_db_mismatch`,
  `funding_source_snapshot_unreferenced_or_orphaned`.
- digest/window reason code presence:
  `funding_source_file_digest_mismatch` absent;
  `funding_source_snapshot_window_mismatch` absent.
- verdict label: `COPIED_DB_FULL_LEDGER_STILL_CAVEATED`.

Batch clean-carry:

- decision: `CAVEATED_ENGINE_SEMANTICS`.
- status: `refused_db_or_lane_mismatch`.
- reason codes:
  `funding_source_batch_window_mismatch`,
  `funding_source_snapshot_unreferenced_or_orphaned`.
- verdict label:
  `COPIED_DB_BATCH_NOW_WINDOW_CAVEATED_EXPECTED` with the additional orphaned
  metadata reason above.

Verifier mismatch details:

- `lane.output_dir '/srv/qnty/output/paper_pnl_null_shadow_v0' != db directory
  '/tmp/qnty_shadow_recommit_copied_db_dry_run_20260707T025834Z'`.
- `snapshot_metadata.db_path_reference
  '/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db' != db_path
  '/tmp/qnty_shadow_recommit_copied_db_dry_run_20260707T025834Z/paper_ledger.copied.db'`.
- `snapshot_metadata.batch_start_watermark None != target batch
  prior_watermark_bar_ts '2026-07-03T08:00:00'`.
- `snapshot_metadata.batch_end_watermark None != target batch
  new_watermark_bar_ts '2026-07-05T16:00:00'`.
- `snapshot_metadata.ledger_batch_id None != target batch '17'`.

Interpretation: the copied DB row can be patched, and the verifier can find and
parse the candidate snapshot. The full-ledger digest/window caveats disappear, but
the DB-linked clean-carry gate still does not clear because the candidate envelope
metadata is not a committed reference for the copied DB and target batch.

## Clean-Carry Gate Comparison

| Evidence surface | Digest gate | Full-ledger window gate | Batch window gate | Coverage gate | DB-linked verifier gate |
|---|---|---|---|---|---|
| Real committed shadow DB currently | fails vs current refreshed source | fails full-ledger window | clears batch window | clears | caveated |
| `/tmp` pure full-ledger candidate from PR #95 | clears | clears | fails batch window by design | clears | not DB-linked |
| copied DB patched with full-ledger candidate | digest reason absent | full-ledger window reason absent | `funding_source_batch_window_mismatch` | clears | fails DB/lane/orphan metadata |

Result:

- the copied DB patch proves the six DB fields can be changed on a copied ledger.
- the verifier accepts the file hash, bundle hash, source coverage, and full-ledger
  evaluation window content.
- the verifier does not promote the copied DB to `CLEAN_NET_OF_CARRY` because the
  candidate snapshot metadata still references the real shadow lane and lacks
  target batch linkage.

## Impact On Existing Receipts

- PR #95 remains valid: its `/tmp` candidate facts still match file hash, bundle
  hash, evaluation window, and pure helper digest/window behavior.
- PR #94 tests remain valid: strict digest/window semantics are preserved.
- PR #93 plan remains valid as a conservative sequence, but the next step is now
  blocker diagnosis rather than a real DB recommit plan.
- PR #92 diagnosis remains valid: stale source digest and full-ledger window caveats
  remain real for current committed shadow evidence.
- This copied-DB dry run does not update real DB-linked snapshot references.
- This does not change official reports.
- This does not prove edge.

## Recommended Next Action

`FUNDING_SOURCE_RECOMMIT_BLOCKER_DIAGNOSIS_GIT_OWNED`

Purpose:

- diagnose the verifier's DB/lane/batch metadata requirements for a recommit path;
- determine whether a valid recommit requires rebuilding the snapshot envelope with
  target `ledger_batch_id`, batch watermarks, `lane.output_dir`, and
  `snapshot_metadata.db_path_reference` aligned to the target DB;
- determine the exact post-rewrite file SHA / envelope `snapshot_sha256` update
  sequence before any real DB mutation is planned;
- continue to make no real DB mutation until a copied-DB verifier result is clean
  for the full-ledger DB-linked gate.

Do not recommend real DB mutation from this result. The copied-DB verifier did not
clear full-ledger DB-linked clean-carry.

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

- scoped VM copied-DB dry run: completed under
  `/tmp/qnty_shadow_recommit_copied_db_dry_run_20260707T025834Z`; verifier exit
  code `0`; real shadow DB, official report, VM repo, and real shadow output dir
  unchanged.
- `.venv/bin/python -m pytest tests/test_funding_source_digest_window_semantics.py`:
  `7 passed`.
- `.venv/bin/python -m pytest tests/test_paper_sqlite_verify_batch_scoped_clean_carry.py`:
  `10 passed`.
- `.venv/bin/python -m pytest tests/test_paper_sqlite_verifier_db_linked_snapshot_selector.py`:
  `19 passed`.
- `.venv/bin/python -m pytest tests/test_funding_source_snapshot_schema.py`:
  `18 passed`.
- `.venv/bin/python -m pytest tests/test_paper_realized_attribution_reporter.py`:
  `16 passed`.
- `.venv/bin/python -m pytest tests/test_position_snapshot_symbol_unrealized_gross.py`:
  `4 passed`.
- total scoped pytest result: `74 passed`.
- `git diff --check`: passed before staging.
- `git diff --cached --check`: passed before commit.
- `git diff --cached --name-only`: exactly
  `docs/status/funding_source_snapshot_recommit_copied_db_dry_run_2026-07-07.md`.
- `git status --short --branch`: staged receipt only, plus existing untracked
  `.claude/`.

## Verdict

`FUNDING_SOURCE_RECOMMIT_COPIED_DB_DRY_RUN_RECORDED_CAVEATED`
