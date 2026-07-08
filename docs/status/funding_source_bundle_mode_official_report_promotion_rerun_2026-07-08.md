# Funding-Source Bundle-Mode Official Shadow Report Promotion — Rerun After PR #113

**Task:** `FUNDING_SOURCE_BUNDLE_MODE_OFFICIAL_REPORT_PROMOTION_RERUN_AFTER_BATCH_STAMP_FIX_GIT_OWNED`
**Date (UTC):** 2026-07-08
**Verdict:** `FUNDING_SOURCE_BUNDLE_MODE_OFFICIAL_REPORT_PROMOTION_RERUN_BLOCKED`

Guardrails preserved: `EDGE_UNPROVEN`, `BLOCK_LIVE_INTEGRATION`. `CLEAN_NET_OF_CARRY`
means only "not killed by this verifier gate" — not edge/profit/live approval.

---

## PLAN

Re-run the real shadow official report promotion in **bundle mode** after PR #113
merged, expecting the batch-scoped clean-carry stamp to now honor
`source_mode="bundle"` and pass alongside the full-ledger clean-carry gate. Produce a
candidate report to `/tmp` first; back up and atomically replace the official shadow
report **only if all acceptance gates pass**; otherwise stop with a blocked verdict.
Reuse the existing immutable full-ledger bundle from the PR #111 attempt. Read-only on
all real DBs/CSVs; docs-only change in git.

## CHANGESET

Git (docs-only):

- **Added:** `docs/status/funding_source_bundle_mode_official_report_promotion_rerun_2026-07-08.md` (this receipt).
- No source/code/dependency/config changes. No application behavior change.

Real lane: **nothing mutated.** The official shadow report was **not** backed up and
**not** replaced (blocked before steps 6–7). Only `/tmp` scratch artifacts and a VM
scratch worktree were created (and the worktree removed at the end).

---

## VERIFY

### PR #113 provenance
- Merge commit `b44f3def743c9043ab57351e86caf57c52ab39a4` confirmed ancestor of
  `origin/main` both locally and on the VM.
- Local promotion branch `docs/funding-source-bundle-mode-official-report-promotion-rerun`
  created at `b44f3def743c9043ab57351e86caf57c52ab39a4`.

### VM identity & runtime
- Host: `ubuntu-4gb-hel1-1-qnty`, user `viktor`, `37.27.216.174`.
- `/srv/qnty/repo` main worktree **not** checked out/pulled/modified (stayed at local
  `main` = `2bd8843`).
- Scratch worktree: `/srv/qnty/scratch_wt_bundle_rerun_20260708` **detached** at
  `b44f3def743c9043ab57351e86caf57c52ab39a4` (PR #113 code). Removed at end.

### Editable-install workaround (VM `/srv/qnty/venv`)
In every Python call: dropped `__editable__` meta-path finders, prepended the scratch
worktree to `sys.path`, and asserted
`quantbot.__file__ == /srv/qnty/scratch_wt_bundle_rerun_20260708/quantbot/__init__.py`.
Confirmed (numpy 2.4.4, pandas 3.0.2).

### Preflight hashes (read-only)
| Artifact | sha256 / value |
|---|---|
| Real shadow DB `paper_ledger.db` | `00a4817e1d49aef51398fe0022cc2f3754302bc12f445912d4eb0d0596fc21ce` (matches expected anchor; size 172032) |
| Official shadow report `paper_verify_report.json` (stale) | `653605a76fdd0b8117c8373c9dadd3fcd41bed147778920c82f29f19f14e0ffd` (matches expected anchor; size 3531) |
| Immutable bundle (file content) | `aaa12ea0ab368cd3f34a6c30fcf37c56213cd3e1bd29751e042a7a0dbeb8414b` |
| Process scan (writer/trader/live/backfill) | `NO_WRITER_TRADER_LIVE_BACKFILL` |

Source funding CSVs are current/mutated (mtime 2026-07-08); this is expected — bundle
mode is precisely what decouples the verdict from the mutable CSVs.

### Bundle identity (step 4 — reuse, verified; no rebuild)
- File: `.../funding_source_bundles/funding_source_bundle_v1_37f6fb59...27cf4.json`
- `bundle_payload.source_bundle_sha256 = 37f6fb596bd44d63dd7e5efee26ca08e50fcc0785561c25cc6ac384fbfd27cf4` (matches expected bundle source sha)
- `bundle_payload.snapshot_bundle_sha256 = 8b9d80408b5aae517ba745a5072d9f7d09125572a23ea5e792e2d80e9c099d69` (matches expected snapshot bundle sha)
- `recompute_bundle_sha256(bundle_payload) == source_bundle_sha256` → **self-consistent**
- `bundle_window_reasons(bundle_payload) == []`
- Bundle evaluation window: **`2026-06-25T08:00:00Z → 2026-07-05T16:00:00Z`** (full-ledger scope)

### DB → snapshot → bundle binding (batch 17, read-only)
- `ledger_batches` batch_id **17** is the latest committed row (`committed_at 2026-07-06T04:33:09Z`, lane `paper_pnl_null_shadow_v0`).
- `funding_source_snapshot_sha256 = 7c5068afef44fc360e88bbde126d892c538973e8f98cbd32dfd0a63ae310ab66` (matches expected sidecar sha).
- `funding_source_snapshot_bundle_sha256 = 8b9d80408b5aae517ba745a5072d9f7d09125572a23ea5e792e2d80e9c099d69` → equals the bundle's `snapshot_bundle_sha256`. **Binding valid.**
- Snapshot path: `.../funding_source_snapshots/funding_source_snapshot_v1_8b9d8040...c099d69.json`, `write_state=committed`.

### Candidate verifier run (to `/tmp`, real DB read in place, immutable read-only)
- Method: replicated `verify_and_publish`'s published envelope
  (`_verify_connection(conn, db, source_mode="bundle")` + `_content_digests` +
  `_build_published_report`) — because `verify_and_publish` itself hardwires
  `live-current` and takes no `source_mode`. Real DB opened via
  `file:<abs>?mode=ro&immutable=1` **in place** (no DB copy — avoids the known
  copied-DB false-CAVEATED snapshot-resolution hazard). Written to `/tmp` with the same
  `ledger.write_json_atomic` serializer.
- Candidate path: `/tmp/qnty_bundle_rerun_candidate_20260708/paper_verify_report.candidate.json`
- Candidate sha256: `cb623072d4838bce24ef6b6bba01936a99ec5101224a39c3584f31232acf6a93`

### Candidate acceptance gate table
| Gate | Expected | Observed | Pass |
|---|---|---|---|
| verifier status | `OK` | `OK` | ✅ |
| failure_count | `0` | `0` | ✅ |
| trusted | true | true | ✅ |
| full-ledger `source_resolution_mode` | `bundle` | `bundle` | ✅ |
| full-ledger `funding_clean_carry_decision` | `CLEAN_NET_OF_CARRY` | `CLEAN_NET_OF_CARRY` | ✅ |
| full-ledger reason_codes | `[]` | `[]` | ✅ |
| full-ledger resum_check | ok | ok (59 rows, sum 3.44000686) | ✅ |
| batch stamp `source_resolution_mode` | `bundle` | `bundle` | ✅ |
| batch stamp: no `funding_source_file_digest_mismatch` | absent | absent | ✅ |
| no `funding_source_row_digest_mismatch` | absent | absent | ✅ |
| no `funding_source_snapshot_path_outside_snapshot_dir` | absent | absent | ✅ |
| no `funding_source_snapshot_db_mismatch` | absent | absent | ✅ |
| report exposes bundle path/hash/source identity | yes | yes | ✅ |
| real DB hash unchanged after run | `00a4817e…21ce` | `00a4817e…21ce` | ✅ |
| source CSV hashes unchanged | unchanged | unchanged | ✅ |
| official report hash unchanged before replacement | `653605a7…0ffd` | `653605a7…0ffd` | ✅ |
| **batch stamp clean (bundle-mode)** — Goal requirement | `CLEAN_NET_OF_CARRY` | **`CAVEATED_ENGINE_SEMANTICS`** | ❌ |

### The blocker
The batch-scoped stamp for batch 17:

```
funding_clean_carry_batch_decision  = CAVEATED_ENGINE_SEMANTICS
funding_clean_carry_batch_status    = refused_db_or_lane_mismatch
funding_clean_carry_batch_reason_codes = ["funding_source_batch_window_mismatch"]
  batch evaluation_window       = 2026-07-03T08:00:00Z → 2026-07-05T16:00:00Z
  full_ledger evaluation_window = 2026-06-25T08:00:00Z → 2026-07-05T16:00:00Z
  source_resolution_mode        = bundle   (PR #113 fix confirmed working)
```

PR #113 **did** fix its target defect: the batch stamp now resolves via
`source_resolution_mode=bundle`, and the prior PR #111 blocker
(`funding_source_file_digest_mismatch` from comparing against mutated live CSVs) is
**gone**. However, honoring bundle mode exposed a **distinct, new** blocker: the reused
immutable bundle is **full-ledger-scoped** (`2026-06-25 → 2026-07-05`), while the
batch-scoped clean-carry gate applies a **strict-equality window check** against batch
17's narrower window (`2026-07-03 → 2026-07-05`). A full-ledger bundle window is a
superset of the batch window, so the strict-equality gate emits
`funding_source_batch_window_mismatch → refused_db_or_lane_mismatch`.

This is the exact inverse of the documented Problem B (a batch-scoped snapshot is valid
for the batch gate but not full-ledger): a full-ledger bundle is valid for the
full-ledger gate but not for the batch stamp. One full-ledger bundle **cannot** satisfy
both strict-equality gates simultaneously. Resolving this requires either a
batch-window-scoped bundle for batch 17 (a real-lane artifact build, out of scope for a
docs-only promotion and beyond "reuse the existing bundle") or a verifier change to make
the batch window gate accept a covering superset window — neither of which this task
authorizes.

Because the Goal explicitly requires **both** gates to pass and the post-replacement
verification requires "batch stamp clean / bundle-mode", the candidate does **not** meet
promotion criteria. Per procedure, the official report was **not** backed up and **not**
replaced.

### What was touched
- Created + removed VM scratch worktree `/srv/qnty/scratch_wt_bundle_rerun_20260708`.
- Wrote `/tmp` scratch: `gen_candidate.py`, candidate report, stdout/stderr.
- Added this receipt in git.

### What was NOT touched
- No real shadow DB mutation (`00a4817e…21ce` unchanged; no new `-wal`/`-shm`; pre-existing `-shm`/`-wal` untouched).
- No prod DB, no source CSV, no snapshot, no bundle mutation.
- Official shadow report **unchanged** (`653605a7…0ffd`) — **not** backed up, **not** replaced.
- No service/timer/cron/systemd; no writer/trader/live/backfill/data-refresh; no deploy; no `/srv/qnty/repo` main worktree change.

---

## VERDICT

`FUNDING_SOURCE_BUNDLE_MODE_OFFICIAL_REPORT_PROMOTION_RERUN_BLOCKED`

Full-ledger clean-carry passes cleanly under bundle mode
(`CLEAN_NET_OF_CARRY`, reason_codes `[]`). PR #113's batch-stamp bundle-mode fix is
confirmed working (no more `funding_source_file_digest_mismatch`). Promotion remains
blocked by a **new** batch-scoped `funding_source_batch_window_mismatch`: the reused
immutable bundle is full-ledger-scoped and the batch gate requires strict window
equality with batch 17's window. Official shadow report stays stale.

### Recommended next action
Choose one and route it as its own (code/artifact-owning, not docs-only) task:
1. **Build a batch-17-window-scoped immutable bundle** (window `2026-07-03 → 2026-07-05`)
   bound to batch 17's committed snapshot, keep the full-ledger bundle for the
   full-ledger gate, and confirm the batch stamp resolves the batch-scoped bundle. Then
   rerun this promotion.
2. **OR** relax the verifier's batch window gate to accept a covering superset bundle
   window (with a spec + tests pinning the intended semantics), land it via PR, then
   rerun this promotion.

Until then: `EDGE_UNPROVEN` and `BLOCK_LIVE_INTEGRATION` stand; shadow official report
remains stale/caveated; no promotion.
