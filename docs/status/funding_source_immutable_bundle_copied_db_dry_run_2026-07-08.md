# Funding-Source Immutable Bundle — Copied-DB Dry Run (2026-07-08)

Task: `FUNDING_SOURCE_IMMUTABLE_BUNDLE_COPIED_DB_DRY_RUN_GIT_OWNED`
Branch: `docs/funding-source-immutable-bundle-copied-db-dry-run`
Runtime code: merged PR #107 (`02d2581beb7fb31affdb10d796a7fca32309d5cc`, = `origin/main`).

Verdict: **`FUNDING_SOURCE_IMMUTABLE_BUNDLE_COPIED_DB_DRY_RUN_BLOCKED`**

Guardrails preserved: `EDGE_UNPROVEN`, `BLOCK_LIVE_INTEGRATION`. `CLEAN_NET_OF_CARRY`
was **not** reached and, in any case, means only "not killed by this verifier gate",
never edge / profit / live approval.

This run corrects the prior blocked receipt (`d658c3d`), which was laptop-only with no
VM artifacts. That commit was **not** pushed; this branch was reset cleanly from
`origin/main` and this receipt was produced from a real VM copied-DB run.

---

## PLAN

1. Local git prep: fetch origin; confirm `origin/main` = PR #107 merge
   `02d2581…`; reset the dry-run branch off `origin/main` (discard the un-pushed
   blocked laptop commit `d658c3d`).
2. VM prep, read-only: SSH to VM, fetch origin, add a **detached scratch worktree**
   at `02d2581…` under `/tmp` so runtime code is exactly PR #107 without touching
   `/srv/qnty/repo`'s working tree.
3. Read-only preflight hashes: real shadow DB, official report, latest committed
   batch + DB-linked snapshot reference, live source CSV digests (context), process
   check.
4. Create `/tmp` dry-run dir; copy real shadow DB; verify copy sha == real sha.
5. Build the immutable funding-source bundle from the committed snapshot envelope
   (`quantbot.paper.funding_source_bundle`) into the copied DB's
   `funding_source_bundles/`.
6. Run the bundle-mode verifier (`verify_database(..., source_mode="bundle")`)
   against the copied DB only; capture stdout/stderr.
7. Post-run integrity: real DB / report / snapshot / CSV hashes unchanged; nothing
   written under the real shadow lane; copied DB unchanged by the verifier.
8. Record receipt; git-diff gates; commit + push + open docs-only PR.

---

## ENVIRONMENT

- VM: `37.27.216.174` (`ubuntu-4gb-hel1-1-qnty`), user `viktor`,
  key `~/.ssh/hetzner_qnty_key` (`-o IdentitiesOnly=yes`). VM UTC at start
  `2026-07-08T12:29:39Z`.
- VM repo `/srv/qnty/repo`: HEAD `2bd8843` on `main` (behind `origin/main` by 34);
  after `git fetch origin`, `origin/main` = `02d2581…` and `02d2581…` is an
  ancestor. Working tree left **untouched** (no checkout/pull on the main worktree).
- Runtime pinned via detached scratch worktree at `02d2581…` under
  `/tmp/qnty_immutable_bundle_copied_db_dry_run_20260708T123024Z/pr107_worktree`.
  The venv installs `quantbot` editable (`__editable__` finder → `/srv/qnty/repo`,
  which is behind and lacks PR #107), so each Python invocation dropped the
  editable meta-path finder and prepended the worktree; `quantbot.__file__`
  confirmed resolving to the worktree. Worktree removed afterwards
  (`git worktree remove --force`); `git worktree list` shows only the main worktree.
- No writer / trader / live / backfill process running (read-only `pgrep`).

---

## PREFLIGHT HASHES (read-only, real artifacts)

| Artifact | Size | sha256 | mtime (UTC) |
|---|---|---|---|
| real shadow DB `…/paper_pnl_null_shadow_v0/paper_ledger.db` | 172032 | `00a4817e1d49aef51398fe0022cc2f3754302bc12f445912d4eb0d0596fc21ce` | 2026-07-07 15:20:43 |
| official report `…/paper_verify_report.json` | 3531 | `653605a76fdd0b8117c8373c9dadd3fcd41bed147778920c82f29f19f14e0ffd` | 2026-07-01 18:15:57 |
| committed snapshot sidecar `funding_source_snapshot_v1_8b9d80…9d69.json` | 46630 | `7c5068afef44fc360e88bbde126d892c538973e8f98cbd32dfd0a63ae310ab66` | 2026-07-07 15:19:59 |

Latest committed batch: **17**. DB-linked snapshot reference (batch 17,
read-only):
- `funding_source_snapshot_path = /srv/qnty/output/paper_pnl_null_shadow_v0/funding_source_snapshots/funding_source_snapshot_v1_8b9d80…9d69.json`
- `funding_source_snapshot_sha256 = 7c5068af…ab66`
- `funding_source_snapshot_bundle_sha256 = 8b9d8040…9d69`

Committed snapshot envelope internal identity (read-only):
- `lane.lane_id = paper_pnl_null_shadow_v0`
- `lane.output_dir = /srv/qnty/output/paper_pnl_null_shadow_v0`
- `snapshot_metadata.db_path_reference = /srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db`
- `write_state = committed`, `ledger_batch_id = 17`,
  `batch_identity_matches = True`, `evaluation_identity_matches = True`,
  `batch_start_watermark = 2026-07-03T08:00:00`,
  `batch_end_watermark = 2026-07-05T16:00:00`.

Live source CSVs were refreshed **2026-07-08 08:07 UTC** — after batch 17
(2026-07-07). This is the intended live-CSV drift the bundle must survive, e.g.
`BTCUSDT_8h_funding.csv`: frozen snapshot digest `65c66a32…750c8e` vs live
`872212ab…f5866`.

---

## CHANGESET

- Git-owned change: **this receipt only** (docs). No production code, tests,
  fixtures, or config changed.
- Generated artifacts (VM `/tmp` only, never committed, never under the real lane):
  - copied DB `…/20260708T123024Z/paper_ledger.db` (byte-identical to real DB;
    never patched)
  - immutable bundle
    `…/funding_source_bundles/funding_source_bundle_v1_37f6fb59…7cf4.json`
  - verifier stdout/stderr JSON.

---

## BUNDLE IDENTITY (built from committed batch-17 snapshot envelope)

- path: `…/funding_source_bundles/funding_source_bundle_v1_37f6fb596bd44d63dd7e5efee26ca08e50fcc0785561c25cc6ac384fbfd27cf4.json`
- bundle file sha256: `aaa12ea0ab368cd3f34a6c30fcf37c56213cd3e1bd29751e042a7a0dbeb8414b`
- size: 38949 bytes
- schema version: `FUNDING_SOURCE_BUNDLE_SCHEMA_V1`
- `source_bundle_sha256` (content-addresses frozen rows; = filename): `37f6fb59…7cf4`
- `snapshot_bundle_sha256` (binds bundle → snapshot): `8b9d8040…9d69`
  — **equals** the DB row `funding_source_snapshot_bundle_sha256` ✓
- `snapshot_sha256` (envelope): `29e513f994330a0cf0009889c9801d110d10eae6d78726ba7d68935f4c080566`
- self-integrity `recompute_bundle_sha256 == source_bundle_sha256`: **OK**
- window coverage reasons: `[]` (all 59 required windows covered)
- row counts: total 59 — BNBUSDT 6, BTCUSDT 10, ETHUSDT 10, SOLUSDT 23, XRPUSDT 10
- symbols: BNBUSDT, BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT
- evaluation window: 2026-06-25T08:00:00Z → 2026-07-05T16:00:00Z

No bundle was written under the real shadow lane
(`…/paper_pnl_null_shadow_v0/funding_source_bundles` does not exist).

---

## VERIFY

### Rung — bundle-mode verifier against the copied DB only

`verify_database(copied_db, source_mode="bundle")` →

- `funding_clean_carry.source_resolution_mode = bundle` ✓ (bundle path exercised)
- `failure_count = 0`; arithmetic OK
- `funding_clean_carry.decision = CAVEATED_ENGINE_SEMANTICS` (**not**
  `CLEAN_NET_OF_CARRY`)
- `funding_clean_carry.status = refused_missing_snapshot`
- `reason_codes = [funding_source_snapshot_missing,
  funding_source_snapshot_path_outside_snapshot_dir, source_path_unavailable]`
- **No** `funding_source_file_digest_mismatch` / `funding_source_row_digest_mismatch`
  despite live-CSV drift.
- copied DB sha before == after verifier: **unchanged** (`00a4817e…21ce`).

### Rung — isolated proof that PR #107 bundle source-resolution works

`resolve_funding_source_bundle(copied_bundle_dir, "8b9d8040…9d69")` →
- bundle found: **True**; `reason_codes = []`
- `source_resolution_mode = bundle`, `source_bundle_sha256 = 37f6fb59…7cf4`
- returns the **frozen** BTCUSDT digest `65c66a32…750c8e`, i.e. it ignores the
  drifted live CSV `872212ab…f5866`.

Interpretation: PR #107's bundle mechanism does exactly what it was designed for —
it freezes the funding source and neutralizes the live-CSV refresh race, so the
**source-digest** gate is satisfied from frozen bytes. The copied-DB run is not
blocked by source resolution.

### The actual blocker (structural, not a bundle-mode defect)

The clean-carry gate selects the target batch's **DB-linked** snapshot and first
enforces path containment: the snapshot path must resolve under
`db_path.parent/funding_source_snapshots/`
(`sqlite_verify._resolve_db_linked_snapshot_path`). The copied DB row still points
at the **real-lane absolute** path
`/srv/qnty/output/paper_pnl_null_shadow_v0/funding_source_snapshots/…`, which is
outside the copied DB's `/tmp` parent → `funding_source_snapshot_path_outside_snapshot_dir`.

By code + envelope-field inspection, fixing only that (copy the sidecar into the
copied lane and repoint the row) would **still** be refused at the next gates in
`_classify_db_linked_funding_source_snapshot`:
- `lane.output_dir` (`/srv/qnty/output/paper_pnl_null_shadow_v0`) must equal the
  copied `db_path.parent` (`/tmp/…`) → `funding_source_snapshot_db_mismatch`;
- `snapshot_metadata.db_path_reference`
  (`/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db`) must equal the
  copied `db_path` → `funding_source_snapshot_db_mismatch`.

All **batch-identity** fields (batch 17, `batch_identity_matches`,
`evaluation_identity_matches`, watermarks) are already aligned; the only residual
blockers are the snapshot's **lane/DB location identity**, which intrinsically
encodes the real lane path and cannot match a `/tmp` copied DB.

I deliberately **did not patch the copied DB** — it stayed byte-identical to the
real DB throughout (sha `00a4817e…21ce`). The block is established from the
verifier reason codes plus code + committed-envelope inspection, without any
further copied-DB mutation.

### Post-run integrity (all read-only re-hashes)

- real DB sha256 `00a4817e…21ce` — **unchanged**
- official report sha256 `653605a7…0ffd` — **unchanged**
- committed snapshot sidecar sha256 `7c5068af…ab66` — **unchanged**
- live CSV digests **unchanged by this task** (BTCUSDT `872212ab…f5866` at pre and post)
- **no** `funding_source_bundles` directory created under the real shadow lane
- generated bundle + copied DB + verifier outputs exist **only** under
  `/tmp/qnty_immutable_bundle_copied_db_dry_run_20260708T123024Z/`

---

## WHAT WAS NOT TOUCHED

No real shadow-DB mutation; no prod-DB mutation; no official-report overwrite; no
copied-DB patch; no live source-CSV mutation; no service / timer / cron / systemd
change; no writer / trader / live / backfill / data-refresh / backfill run; no
deploy; no exchange keys; no live integration; no source-freeze; no cleanup of real
artifacts; `/srv/qnty/repo` main working tree left untouched (scratch worktree only,
then removed).

---

## EXACT COMMANDS (abridged)

```bash
# Local
git fetch origin
git rev-parse origin/main            # 02d2581…  (PR #107 merge)
git merge-base --is-ancestor 02d2581… origin/main && echo YES
git reset --hard origin/main         # discard un-pushed blocked commit d658c3d

# VM (ssh -i ~/.ssh/hetzner_qnty_key -o IdentitiesOnly=yes viktor@37.27.216.174)
cd /srv/qnty/repo
git -c safe.directory=/srv/qnty/repo fetch origin
BASE=/tmp/qnty_immutable_bundle_copied_db_dry_run_$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$BASE"
git -c safe.directory=/srv/qnty/repo worktree add --detach "$BASE/pr107_worktree" 02d2581…

LANE=/srv/qnty/output/paper_pnl_null_shadow_v0
sha256sum "$LANE/paper_ledger.db" "$LANE/paper_verify_report.json"   # preflight
cp -p "$LANE/paper_ledger.db" "$BASE/paper_ledger.db"                # copy; sha == real

# import from worktree (drop editable finder), build bundle, run verifier:
BASE="$BASE" /srv/qnty/venv/bin/python - <<'PY'
import os, sys, json, hashlib
BASE=os.environ['BASE']; WT=os.path.join(BASE,'pr107_worktree')
sys.meta_path=[f for f in sys.meta_path if not type(f).__module__.startswith('__editable__')]
sys.path.insert(0, WT)
from quantbot.paper import funding_source_bundle as fsb
from quantbot.paper.sqlite_verify import verify_database
SNAP=os.path.join(LANE,'funding_source_snapshots','funding_source_snapshot_v1_8b9d80…9d69.json')
env=json.load(open(SNAP)); bundle=fsb.build_funding_source_bundle_v1(env)
fsb.write_funding_source_bundle(bundle, os.path.join(BASE,'funding_source_bundles'))
DB=os.path.join(BASE,'paper_ledger.db')
pre=hashlib.sha256(open(DB,'rb').read()).hexdigest()
res=verify_database(DB, source_mode='bundle')
post=hashlib.sha256(open(DB,'rb').read()).hexdigest()
print(pre==post, res.report['funding_clean_carry']['status'])
PY

git -c safe.directory=/srv/qnty/repo worktree remove --force "$BASE/pr107_worktree"
```

---

## VERDICT

`FUNDING_SOURCE_IMMUTABLE_BUNDLE_COPIED_DB_DRY_RUN_BLOCKED`

- PR #107 bundle **source-resolution** is exercised and works on the VM against
  copied artifacts: it resolves the bound bundle with empty reason codes and
  supplies frozen source digests, neutralizing the live-CSV refresh race
  (no source-digest mismatch despite drift). This is a genuine positive result for
  the immutable-bundle design.
- A copied-off-host DB still **cannot** reach `CLEAN_NET_OF_CARRY`, because the
  committed snapshot envelope is bound to the **real lane** path
  (`lane.output_dir`, `db_path_reference`) and the DB row references the real-lane
  snapshot path. These lane/DB **location-identity** gates are orthogonal to source
  mode and refuse any DB moved to `/tmp`.

### Recommended next action

`FUNDING_SOURCE_RECOMMIT_COPIED_DB_METADATA_ALIGNED_BUNDLE_DRY_RUN` (separately
authorized): on the copied DB only, rebuild the snapshot envelope with
copied-lane-aligned `lane.output_dir` / `db_path_reference` (and copied
snapshot dir), recompute the file SHA, patch the copied DB row's snapshot
path + sha, keep the immutable bundle from this run, then re-run
`source_mode="bundle"`. Expectation: with the lane/DB identity gates satisfied and
the bundle supplying frozen digests, the copied DB should clear to
`CLEAN_NET_OF_CARRY`. This remains a **copied-DB** exercise — no real-lane mutation,
no live-integration, `EDGE_UNPROVEN` / `BLOCK_LIVE_INTEGRATION` preserved.

### Memory note

MemPalace `qnty` wing was available and used **recall-only**: it supplied the VM
SSH pattern (`~/.ssh/hetzner_qnty_key`, `viktor@37.27.216.174`) and prior copied-DB
recommit-blocker diagnoses (the "candidate metadata still references the real lane"
finding). Source of truth remained git, the merged PR #107 code, the VM artifacts,
and the hashes above. Nothing was written to MemPalace; no secrets/keys/raw
DBs/CSVs were stored.
