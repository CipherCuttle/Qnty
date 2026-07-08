# Funding-Source Metadata-Aligned Bundle Copied-DB Dry Run - 2026-07-08

Task: `FUNDING_SOURCE_RECOMMIT_COPIED_DB_METADATA_ALIGNED_BUNDLE_DRY_RUN_GIT_OWNED`

Verdict: **`FUNDING_SOURCE_RECOMMIT_COPIED_DB_METADATA_ALIGNED_BUNDLE_DRY_RUN_RECORDED_CLEAN`**

`EDGE_UNPROVEN` remains. `BLOCK_LIVE_INTEGRATION` remains. This is copied-DB
evidence only: `CLEAN_NET_OF_CARRY` means "not killed by this verifier gate" on
the copied artifact, not edge, profit, live-readiness, deployment, or promotion
approval.

## PLAN

1. Start from `origin/main`, which includes PR #108 merge commit
   `af74a4bf27b0ef3f52b88da1fe55a74c378439d0`.
2. On the VM, fetch origin and create a detached scratch worktree at current
   `origin/main`; do not checkout, pull, or modify `/srv/qnty/repo` main
   worktree.
3. Read real shadow artifacts read-only and record hashes, latest committed batch
   row, source CSV digests, and process state.
4. Copy the real DB and selected batch-17 sidecar under a fresh `/tmp` dry-run
   directory.
5. Rebuild the snapshot envelope with copied-lane metadata only, write the
   aligned sidecar under `/tmp`, build the immutable funding-source bundle under
   `/tmp`, and patch only the copied DB batch-17 snapshot reference row.
6. Run `verify_database(copied_db, source_mode="bundle")` against the copied DB
   only, then re-hash real artifacts and copied artifacts.
7. Record this docs/status receipt, verify docs-only diff, commit, push, and open
   a docs-only PR without merging it.

## CHANGESET

Git-owned change:

- `docs/status/funding_source_metadata_aligned_bundle_copied_db_dry_run_2026-07-08.md`

Runtime artifacts stayed under:

- `/tmp/qnty_metadata_aligned_bundle_copied_db_dry_run_20260708T132706Z/`

Generated VM paths included:

- copied DB:
  `/tmp/qnty_metadata_aligned_bundle_copied_db_dry_run_20260708T132706Z/paper_ledger.db`
- copied DB backup before patch:
  `/tmp/qnty_metadata_aligned_bundle_copied_db_dry_run_20260708T132706Z/paper_ledger.before_metadata_alignment_patch.db`
- staged original sidecar:
  `/tmp/qnty_metadata_aligned_bundle_copied_db_dry_run_20260708T132706Z/original_funding_source_snapshots/funding_source_snapshot_v1_8b9d80408b5aae517ba745a5072d9f7d09125572a23ea5e792e2d80e9c099d69.json`
- aligned sidecar:
  `/tmp/qnty_metadata_aligned_bundle_copied_db_dry_run_20260708T132706Z/funding_source_snapshots/funding_source_snapshot_v1_8b9d80408b5aae517ba745a5072d9f7d09125572a23ea5e792e2d80e9c099d69.json`
- immutable bundle:
  `/tmp/qnty_metadata_aligned_bundle_copied_db_dry_run_20260708T132706Z/funding_source_bundles/funding_source_bundle_v1_37f6fb596bd44d63dd7e5efee26ca08e50fcc0785561c25cc6ac384fbfd27cf4.json`
- verifier stdout/stderr:
  `/tmp/qnty_metadata_aligned_bundle_copied_db_dry_run_20260708T132706Z/verify_bundle_mode.stdout.json`
  and
  `/tmp/qnty_metadata_aligned_bundle_copied_db_dry_run_20260708T132706Z/verify_bundle_mode.stderr.txt`

## ENVIRONMENT

- VM: `ubuntu-4gb-hel1-1-qnty`, user `viktor`.
- SSH command:
  `ssh -i ~/.ssh/hetzner_qnty_key -o IdentitiesOnly=yes viktor@37.27.216.174`
- VM repo main worktree: `/srv/qnty/repo`, HEAD
  `2bd88430fe6b2881aaa2b32947002217d3e02ba5`, status
  `## main...origin/main [behind 36]`; intentionally left untouched.
- VM `origin/main`: `af74a4bf27b0ef3f52b88da1fe55a74c378439d0`.
- Scratch worktree:
  `/tmp/qnty_metadata_aligned_bundle_copied_db_dry_run_20260708T132706Z/origin_main_worktree`
  at `af74a4bf27b0ef3f52b88da1fe55a74c378439d0`, status
  `## HEAD (no branch)`, removed after the run.
- Summary recheck scratch worktree:
  `/tmp/qnty_metadata_aligned_bundle_copied_db_dry_run_20260708T132706Z/origin_main_worktree_summary_fix`,
  also removed after the recheck.
- Editable install workaround: `/srv/qnty/venv` resolves editable `quantbot`
  through a `__editable__` finder pointed at `/srv/qnty/repo`. Each VM Python
  invocation dropped that finder, prepended the scratch worktree to `sys.path`,
  and confirmed `quantbot.__file__` under the scratch worktree.

## PREFLIGHT

Real shadow artifacts, read-only:

| artifact | size | sha256 | mtime UTC |
|---|---:|---|---|
| `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db` | 172032 | `00a4817e1d49aef51398fe0022cc2f3754302bc12f445912d4eb0d0596fc21ce` | `2026-07-07T15:20:43Z` |
| `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_verify_report.json` | 3531 | `653605a76fdd0b8117c8373c9dadd3fcd41bed147778920c82f29f19f14e0ffd` | `2026-07-01T18:15:57Z` |
| selected sidecar `funding_source_snapshot_v1_8b9d8040...9d69.json` | 46630 | `7c5068afef44fc360e88bbde126d892c538973e8f98cbd32dfd0a63ae310ab66` | `2026-07-07T15:19:59Z` |

Latest committed batch row:

- batch id: `17`
- `prior_watermark_bar_ts`: `2026-07-03T08:00:00`
- `new_watermark_bar_ts`: `2026-07-05T16:00:00`
- `committed_at`: `2026-07-06T04:33:09Z`
- `git_sha`: `2bd88430fe6b2881aaa2b32947002217d3e02ba5`
- `funding_source_snapshot_path`:
  `/srv/qnty/output/paper_pnl_null_shadow_v0/funding_source_snapshots/funding_source_snapshot_v1_8b9d80408b5aae517ba745a5072d9f7d09125572a23ea5e792e2d80e9c099d69.json`
- `funding_source_snapshot_sha256`:
  `7c5068afef44fc360e88bbde126d892c538973e8f98cbd32dfd0a63ae310ab66`
- `funding_source_snapshot_bundle_sha256`:
  `8b9d80408b5aae517ba745a5072d9f7d09125572a23ea5e792e2d80e9c099d69`
- schema: `FUNDING_SOURCE_SNAPSHOT_SCHEMA_V1`
- write state: `committed`
- created at: `2026-07-07T15:16:47Z`

Source CSV context, read-only and unchanged pre/post:

| source CSV | size | sha256 | mtime UTC |
|---|---:|---|---|
| `BNBUSDT_8h_funding.csv` | 206579 | `fb9df46794667ef0b30e319f02cee2937be21f21b728121f0909566c174061ab` | `2026-07-08T08:07:03Z` |
| `BTCUSDT_8h_funding.csv` | 220964 | `872212ab3a05ab4ebb5804f9dcf805e8243a587be9436c440abd5776931f5866` | `2026-07-08T08:06:50Z` |
| `ETHUSDT_8h_funding.csv` | 219260 | `7a9510d4793a61c64ff9099e5681222d59de56738937632b322693db78c1b84d` | `2026-07-08T08:06:56Z` |
| `SOLUSDT_8h_funding.csv` | 220008 | `7938d6e17b2b443deb9bcba33f879fb80e81fc00f2defef1b43416178de392b7` | `2026-07-08T08:07:10Z` |
| `XRPUSDT_8h_funding.csv` | 213390 | `d56ad8d49aa1b2db31278c71f8eec134c29b1928192730ca62132d152487473b` | `2026-07-08T08:07:50Z` |

Process scan:

- pre-run writer/trader/live/backfill matches: `0`
- post-run writer/trader/live/backfill matches: `0`

## COPIED ARTIFACTS

- copied DB sha before patch:
  `00a4817e1d49aef51398fe0022cc2f3754302bc12f445912d4eb0d0596fc21ce`
- copied DB hash equals real DB hash before patch: `true`
- staged original sidecar sha:
  `7c5068afef44fc360e88bbde126d892c538973e8f98cbd32dfd0a63ae310ab66`
- staged original sidecar hash equals real sidecar hash: `true`

## ALIGNED SNAPSHOT

Aligned sidecar:

- path:
  `/tmp/qnty_metadata_aligned_bundle_copied_db_dry_run_20260708T132706Z/funding_source_snapshots/funding_source_snapshot_v1_8b9d80408b5aae517ba745a5072d9f7d09125572a23ea5e792e2d80e9c099d69.json`
- file sha256:
  `40e2129f727087349508e1870f1fe75fa6403d0a0eb573bbd77a03a1609590b1`
- size: `46684`
- envelope `snapshot_sha256`:
  `ba88a40d9179963d3c768865f0e9c83379843d9dc30699b67d466f82ab5cea97`
- `source_bundle_sha256`:
  `8b9d80408b5aae517ba745a5072d9f7d09125572a23ea5e792e2d80e9c099d69`
- validation reason codes: `[]`

Semantic diff from the original committed sidecar was limited to:

- `snapshot_payload.lane.output_dir`
- `snapshot_payload.snapshot_metadata.db_path_reference`
- `snapshot_sha256`

Original identity:

- `lane.output_dir`:
  `/srv/qnty/output/paper_pnl_null_shadow_v0`
- `snapshot_metadata.db_path_reference`:
  `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db`

Aligned copied-lane identity:

- `lane.output_dir`:
  `/tmp/qnty_metadata_aligned_bundle_copied_db_dry_run_20260708T132706Z`
- `snapshot_metadata.db_path_reference`:
  `/tmp/qnty_metadata_aligned_bundle_copied_db_dry_run_20260708T132706Z/paper_ledger.db`

Preserved:

- source rows and source digests
- required funding windows
- `source_bundle_sha256`
- symbols and evaluation window
- coverage decision and reason codes
- write state and committed semantics
- ledger batch id `17`
- batch watermarks
- `batch_identity_matches = true`
- `evaluation_identity_matches = true`

Unexpected diff paths: `[]`.

## BUNDLE

- path:
  `/tmp/qnty_metadata_aligned_bundle_copied_db_dry_run_20260708T132706Z/funding_source_bundles/funding_source_bundle_v1_37f6fb596bd44d63dd7e5efee26ca08e50fcc0785561c25cc6ac384fbfd27cf4.json`
- file sha256:
  `64cf415d78e5ca18544ad8f0af3a9bb55107ce39a3993c3292ebc86e6609643d`
- size: `38949`
- schema version: `FUNDING_SOURCE_BUNDLE_SCHEMA_V1`
- bundle `source_bundle_sha256`:
  `37f6fb596bd44d63dd7e5efee26ca08e50fcc0785561c25cc6ac384fbfd27cf4`
- `snapshot_bundle_sha256`:
  `8b9d80408b5aae517ba745a5072d9f7d09125572a23ea5e792e2d80e9c099d69`
- bundle `snapshot_sha256`:
  `ba88a40d9179963d3c768865f0e9c83379843d9dc30699b67d466f82ab5cea97`
- self-integrity: `OK`
- window coverage reasons: `[]`
- symbols: `BNBUSDT`, `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `XRPUSDT`
- row counts: total `59`; BNBUSDT `6`, BTCUSDT `10`, ETHUSDT `10`,
  SOLUSDT `23`, XRPUSDT `10`
- evaluation window: `2026-06-25T08:00:00Z` to `2026-07-05T16:00:00Z`

No `funding_source_bundles/` directory was created under the real shadow lane.

## COPIED DB PATCH

Backup before patch:

- `/tmp/qnty_metadata_aligned_bundle_copied_db_dry_run_20260708T132706Z/paper_ledger.before_metadata_alignment_patch.db`

Guarded copied-DB update:

- target table: `ledger_batches`
- target row: `batch_id = 17`
- `changes()`: `1`
- changed tables by content hash: `ledger_batches` only
- changed batch ids: `17` only
- changed columns: `funding_source_snapshot_path`,
  `funding_source_snapshot_sha256`
- SQLite integrity check after patch: `ok`

Changed row values:

```json
{
  "funding_source_snapshot_path": {
    "before": "/srv/qnty/output/paper_pnl_null_shadow_v0/funding_source_snapshots/funding_source_snapshot_v1_8b9d80408b5aae517ba745a5072d9f7d09125572a23ea5e792e2d80e9c099d69.json",
    "after": "/tmp/qnty_metadata_aligned_bundle_copied_db_dry_run_20260708T132706Z/funding_source_snapshots/funding_source_snapshot_v1_8b9d80408b5aae517ba745a5072d9f7d09125572a23ea5e792e2d80e9c099d69.json"
  },
  "funding_source_snapshot_sha256": {
    "before": "7c5068afef44fc360e88bbde126d892c538973e8f98cbd32dfd0a63ae310ab66",
    "after": "40e2129f727087349508e1870f1fe75fa6403d0a0eb573bbd77a03a1609590b1"
  }
}
```

Copied DB hashes:

- before patch:
  `00a4817e1d49aef51398fe0022cc2f3754302bc12f445912d4eb0d0596fc21ce`
- after patch:
  `4bb10b150a0f7687fc25ca0f8231cee3a3b24aa8d4cf9c748473bc8dc7f398f3`
- before/after verifier:
  `4bb10b150a0f7687fc25ca0f8231cee3a3b24aa8d4cf9c748473bc8dc7f398f3`
  to `4bb10b150a0f7687fc25ca0f8231cee3a3b24aa8d4cf9c748473bc8dc7f398f3`

The verifier did not mutate the copied DB.

## VERIFY

Bundle-mode verifier, copied patched DB only:

- function call:
  `verify_database("/tmp/qnty_metadata_aligned_bundle_copied_db_dry_run_20260708T132706Z/paper_ledger.db", source_mode="bundle")`
- stdout:
  `/tmp/qnty_metadata_aligned_bundle_copied_db_dry_run_20260708T132706Z/verify_bundle_mode.stdout.json`
- stdout sha256:
  `aab6f10dc22be27086ae84919efc0c1cb66e45c32387f03206514e1af6a11b76`
- stderr:
  `/tmp/qnty_metadata_aligned_bundle_copied_db_dry_run_20260708T132706Z/verify_bundle_mode.stderr.txt`
- stderr size: `0`
- stderr sha256:
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- report `failure_count`: `0`
- `funding_source_snapshot.status`: `present_valid`
- `funding_source_snapshot.reason_codes`: `[]`
- `funding_source_snapshot.selected_snapshot_path`: aligned `/tmp` sidecar
- `funding_source_snapshot.lane_output_dir`: aligned `/tmp` base
- `funding_source_snapshot.db_path_reference`: copied `/tmp` DB
- `funding_clean_carry.source_resolution_mode`: `bundle`
- `funding_clean_carry.decision`: `CLEAN_NET_OF_CARRY`
- `funding_clean_carry.status`: `clean_net_of_carry`
- `funding_clean_carry.reason_codes`: `[]`
- `funding_clean_carry.snapshot_status`: `present_valid`

Forbidden reason codes absent:

- `funding_source_file_digest_mismatch`: `false`
- `funding_source_snapshot_path_outside_snapshot_dir`: `false`
- `funding_source_snapshot_db_mismatch`: `false`

A second read-only verifier recheck was run only to capture `VerifyResult.status`
and exit code in the summary, because the first stdout capture stores the report
body but not the result container fields. The recheck used another scratch
worktree at `origin/main`, removed it afterwards, wrote
`verify_bundle_mode.recheck.stdout.json` and `verify_bundle_mode.recheck.stderr.txt`,
and produced the same stdout hash:
`aab6f10dc22be27086ae84919efc0c1cb66e45c32387f03206514e1af6a11b76`.

Recheck result:

- `VerifyResult.status`: `OK`
- `VerifyResult.exit_code`: `0`
- `VerifyResult.ok`: `true`
- `failure_count`: `0`
- failures: `[]`
- copied DB unchanged by recheck: `true`
- `funding_clean_carry_decision`: `CLEAN_NET_OF_CARRY`
- `funding_clean_carry_status`: `clean_net_of_carry`
- `funding_clean_carry_reason_codes`: `[]`
- `funding_clean_carry_source_resolution_mode`: `bundle`

## POST-RUN INTEGRITY

All checks below passed:

- real DB sha unchanged:
  `00a4817e1d49aef51398fe0022cc2f3754302bc12f445912d4eb0d0596fc21ce`
- official report sha unchanged:
  `653605a76fdd0b8117c8373c9dadd3fcd41bed147778920c82f29f19f14e0ffd`
- original real sidecar sha unchanged:
  `7c5068afef44fc360e88bbde126d892c538973e8f98cbd32dfd0a63ae310ab66`
- live source CSV hashes unchanged pre/post
- real shadow lane inventory hash unchanged:
  `3080237d57ec974a22861cbb93b931b942946897466bf91a49cdd29cacec7aab`
- no `funding_source_bundles/` directory under the real shadow lane
- generated files under the `/tmp` base only
- `/srv/qnty/repo` main worktree status unchanged:
  `## main...origin/main [behind 36]`
- scratch worktrees removed
- writer/trader/live/backfill process scan remained empty

## WHAT WAS NOT TOUCHED

No real shadow DB mutation. No prod DB mutation. No official report overwrite. No
live source CSV mutation. No service, timer, cron, or systemd mutation. No writer,
trader, live, or backfill run. No deploy. No exchange keys. No live integration.
No source-freeze. No real-lane cleanup. No `/srv/qnty/repo` main worktree
checkout/pull/reset. No generated bundle, verifier output, copied snapshot, or
copied DB file outside `/tmp`.

## EXACT COMMANDS

Local:

```bash
git fetch origin
git merge-base --is-ancestor af74a4bf27b0ef3f52b88da1fe55a74c378439d0 origin/main
git checkout -B docs/funding-source-metadata-aligned-bundle-copied-db-dry-run origin/main
gh pr list --head docs/funding-source-metadata-aligned-bundle-copied-db-dry-run --state all --json number,title,state,url,headRefName,baseRefName,updatedAt
gh repo view --json nameWithOwner,defaultBranchRef
gh auth status
```

VM primary run:

```bash
ssh -i ~/.ssh/hetzner_qnty_key -o IdentitiesOnly=yes viktor@37.27.216.174 'bash -s'
```

The SSH script executed:

```bash
set -euo pipefail
REPO=/srv/qnty/repo
LANE=/srv/qnty/output/paper_pnl_null_shadow_v0
TS=$(date -u +%Y%m%dT%H%M%SZ)
BASE=/tmp/qnty_metadata_aligned_bundle_copied_db_dry_run_${TS}
WT=${BASE}/origin_main_worktree
mkdir -p "$BASE"
printf '%s\n' "$BASE" > /tmp/qnty_metadata_aligned_dryrun_base_path.txt
cd "$REPO"
git -c safe.directory="$REPO" fetch origin
git -c safe.directory="$REPO" worktree add --detach "$WT" origin/main
BASE="$BASE" WT="$WT" REPO="$REPO" LANE="$LANE" TS="$TS" /srv/qnty/venv/bin/python
git -c safe.directory="$REPO" worktree remove --force "$WT"
```

The Python run performed these guarded operations using scratch-worktree imports:

```python
sys.meta_path = [f for f in sys.meta_path if not type(f).__module__.startswith("__editable__")]
sys.path.insert(0, WT)
import quantbot
from quantbot.paper import funding_source_bundle as fsb
from quantbot.paper.funding_source_snapshot import build_funding_source_snapshot_envelope_v1, validate_funding_source_snapshot_envelope_v1
from quantbot.paper.sqlite_verify import verify_database

shutil.copy2(REAL_DB, COPIED_DB)
shutil.copy2(orig_snapshot_path, staged_orig_snapshot)
aligned_payload = copy.deepcopy(orig_payload)
aligned_payload["lane"]["output_dir"] = str(BASE)
aligned_payload["snapshot_metadata"]["db_path_reference"] = str(COPIED_DB)
aligned_envelope = build_funding_source_snapshot_envelope_v1(aligned_payload)
validate_funding_source_snapshot_envelope_v1(aligned_envelope)
aligned_snapshot_path.write_text(json.dumps(aligned_envelope, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
bundle = fsb.build_funding_source_bundle_v1(aligned_envelope)
bundle_path = fsb.write_funding_source_bundle(bundle, BUNDLE_DIR)

connw.execute("BEGIN IMMEDIATE")
connw.execute(
    """
    UPDATE ledger_batches
    SET funding_source_snapshot_path = ?,
        funding_source_snapshot_sha256 = ?
    WHERE batch_id = ?
    """,
    (str(aligned_snapshot_path), aligned_sidecar_sha256, 17),
)
connw.execute("SELECT changes()")
connw.commit()

result = verify_database(COPIED_DB, source_mode="bundle")
```

VM summary recheck:

```bash
BASE=$(cat /tmp/qnty_metadata_aligned_dryrun_base_path.txt)
WT=${BASE}/origin_main_worktree_summary_fix
git -c safe.directory=/srv/qnty/repo fetch origin
git -c safe.directory=/srv/qnty/repo worktree add --detach "$WT" origin/main
BASE="$BASE" WT="$WT" /srv/qnty/venv/bin/python
git -c safe.directory=/srv/qnty/repo worktree remove --force "$WT"
```

Summary fetch:

```bash
BASE=$(ssh -i ~/.ssh/hetzner_qnty_key -o IdentitiesOnly=yes viktor@37.27.216.174 'cat /tmp/qnty_metadata_aligned_dryrun_base_path.txt')
scp -i ~/.ssh/hetzner_qnty_key -o IdentitiesOnly=yes viktor@37.27.216.174:${BASE}/run_summary.json /tmp/qnty_metadata_aligned_bundle_copied_db_dry_run_summary.json
python -m json.tool /tmp/qnty_metadata_aligned_bundle_copied_db_dry_run_summary.json >/tmp/qnty_metadata_aligned_bundle_copied_db_dry_run_summary.pretty.json
```

## VERDICT

`FUNDING_SOURCE_RECOMMIT_COPIED_DB_METADATA_ALIGNED_BUNDLE_DRY_RUN_RECORDED_CLEAN`

The metadata-aligned copied DB reached full-ledger `CLEAN_NET_OF_CARRY` under
`source_resolution_mode = bundle` with `VerifyResult.status = OK`,
`failure_count = 0`, `funding_clean_carry.status = clean_net_of_carry`, and
empty reason codes.

This proves the PR #108 blocker was the copied artifact's lane/DB identity, not
bundle source resolution. After the copied DB row points at a copied sidecar
under `/tmp`, and the sidecar envelope's `lane.output_dir` and
`snapshot_metadata.db_path_reference` also point at the copied lane, bundle mode
clears the full-ledger clean-carry verifier gate without reading mutable live
CSV bytes as the source of truth.

Recommended next action:

`FUNDING_SOURCE_REAL_LANE_BUNDLE_MODE_ACCEPTANCE_PLAN_GIT_OWNED` - docs-only
planning before any real-lane bundle materialization, official-report promotion,
or live-integration decision. Keep `EDGE_UNPROVEN` and `BLOCK_LIVE_INTEGRATION`
explicit; do not treat this copied-artifact clean gate as a trading approval.
