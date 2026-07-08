# Funding-Source Bundle-Mode Official Report Promotion Execution — 2026-07-08

Task: `FUNDING_SOURCE_BUNDLE_MODE_OFFICIAL_REPORT_PROMOTION_EXECUTION_GIT_OWNED`

Verdict: **`FUNDING_SOURCE_BUNDLE_MODE_OFFICIAL_REPORT_PROMOTION_EXECUTION_BLOCKED`**

`EDGE_UNPROVEN` remains. `BLOCK_LIVE_INTEGRATION` remains. The full-ledger
bundle-mode gate reached `CLEAN_NET_OF_CARRY`, but a candidate acceptance gate
(no `funding_source_file_digest_mismatch` anywhere in the report) did **not**
pass, so the official shadow report was **not** replaced. `CLEAN_NET_OF_CARRY`
means only "not killed by that specific full-ledger gate", not edge, profit,
live-readiness, or promotion approval.

## PLAN

1. Merge approved docs-only PR #110 (bundle-mode promotion plan) with the pinned
   head SHA, confirm `origin/main` includes the merge commit.
2. Create execution branch from `origin/main`.
3. On the VM, create a detached scratch worktree at `origin/main`; never touch
   the `/srv/qnty/repo` main worktree. Apply the editable-install workaround on
   every Python call.
4. Read-only preflight: hash the real shadow DB, official report, selected
   sidecar, and live source CSVs; capture the latest committed batch row and
   snapshot identity; inventory the real-lane bundle dir; scan for
   writer/trader/live/backfill processes.
5. Build the immutable funding-source bundle from the real committed snapshot
   envelope (PR #107 `quantbot.paper.funding_source_bundle`); write it under the
   real shadow lane `funding_source_bundles/` (allowed additive mutation).
6. Run the candidate verifier in `source_mode="bundle"` against the real shadow
   DB, write the candidate report only under `/tmp`, and evaluate every
   candidate acceptance gate. Replace the official report **only** if all gates
   pass.
7. If any gate fails: do not replace the official report; record the blocker;
   stop with a blocked verdict. Re-hash all protected artifacts.
8. Write this receipt, verify docs-only diff, commit, push, open a docs-only PR
   (do not merge).

## CHANGESET

Git-owned change (docs-only):

- `docs/status/funding_source_bundle_mode_official_report_promotion_execution_2026-07-08.md`

Real-lane artifact created (allowed additive, immutable, content-addressed):

- `/srv/qnty/output/paper_pnl_null_shadow_v0/funding_source_bundles/funding_source_bundle_v1_37f6fb596bd44d63dd7e5efee26ca08e50fcc0785561c25cc6ac384fbfd27cf4.json`
  (size `38949`, file sha256 `aaa12ea0ab368cd3f34a6c30fcf37c56213cd3e1bd29751e042a7a0dbeb8414b`)

Runtime scratch artifacts stayed under:

- `/tmp/qnty_bundle_mode_official_report_promotion_20260708T203941Z/`
  (candidate report, preflight/stage summaries, scratch worktrees — removed)

The official shadow report was **not** modified. No backup was created because no
replacement occurred.

## GIT / PR CONTEXT

- PR #110 merged: merge commit `335be053c25b173112be17631063f4185415ba98`, head
  SHA `1e45dddffbeb74e0db20e14fca9a80a6dff4dfdd`, merged 2026-07-08T20:36:56Z,
  merge method: merge commit (single file
  `docs/plans/QNTY_FUNDING_SOURCE_BUNDLE_MODE_OFFICIAL_REPORT_PROMOTION_PLAN.md`,
  +208/-0).
- `origin/main` after merge: `335be053c25b173112be17631063f4185415ba98`.
- Execution branch:
  `docs/funding-source-bundle-mode-official-report-promotion-execution`
  from `origin/main`.

## ENVIRONMENT

- VM: `ubuntu-4gb-hel1-1-qnty`, user `viktor`.
- SSH:
  `ssh -i ~/.ssh/hetzner_qnty_key -o IdentitiesOnly=yes viktor@37.27.216.174`
- VM repo main worktree: `/srv/qnty/repo`, HEAD
  `2bd88430fe6b2881aaa2b32947002217d3e02ba5`, status
  `## main...origin/main [behind 40]`; intentionally left untouched.
- VM `origin/main` after fetch: `335be053c25b173112be17631063f4185415ba98`.
- Scratch worktrees (all detached at `origin/main`, removed after use):
  - preflight: `.../origin_main_worktree`
  - candidate build/verify: `.../origin_main_worktree_stage_b`
- Editable-install workaround: `/srv/qnty/venv` resolves editable `quantbot`
  through an `__editable__` finder pointed at `/srv/qnty/repo`. Every VM Python
  call dropped that finder (`sys.meta_path` filter), prepended the scratch
  worktree to `sys.path`, and asserted `quantbot.__file__` under the scratch
  worktree
  (`/tmp/qnty_bundle_mode_official_report_promotion_20260708T203941Z/origin_main_worktree*/quantbot/__init__.py`).
- Disk: `/dev/sda1` 75G, 69G avail — sufficient.

## PREFLIGHT (read-only)

Real shadow artifacts:

| artifact | size | sha256 | mtime UTC |
|---|---:|---|---|
| `.../paper_ledger.db` | 172032 | `00a4817e1d49aef51398fe0022cc2f3754302bc12f445912d4eb0d0596fc21ce` | `2026-07-07T15:20:43Z` |
| `.../paper_verify_report.json` (official) | 3531 | `653605a76fdd0b8117c8373c9dadd3fcd41bed147778920c82f29f19f14e0ffd` | `2026-07-01T18:15:57Z` |
| selected sidecar `..._8b9d8040...9d69.json` | 46630 | `7c5068afef44fc360e88bbde126d892c538973e8f98cbd32dfd0a63ae310ab66` | `2026-07-07T15:19:59Z` |

All three match the known prior values in the task brief.

Latest committed batch (read-only, `mode=ro&immutable=1`):

- batch id `17`; write state `committed`; `committed_at` `2026-07-06T04:33:09Z`
- `funding_source_snapshot_bundle_sha256`:
  `8b9d80408b5aae517ba745a5072d9f7d09125572a23ea5e792e2d80e9c099d69`
- `funding_source_snapshot_sha256`:
  `7c5068afef44fc360e88bbde126d892c538973e8f98cbd32dfd0a63ae310ab66`
- schema `FUNDING_SOURCE_SNAPSHOT_SCHEMA_V1`
- envelope `lane.output_dir` = `/srv/qnty/output/paper_pnl_null_shadow_v0`
- envelope `snapshot_metadata.db_path_reference` =
  `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db`
- envelope top-level `snapshot_sha256` =
  `29e513f994330a0cf0009889c9801d110d10eae6d78726ba7d68935f4c080566`

Real-lane snapshot identity is natively consistent with the real lane (no
metadata alignment needed — unlike the PR #109 copied-DB dry run).

Live source CSV digests at preflight (`/srv/qnty/repo/data/`), unchanged across
the run:

| CSV | sha256 |
|---|---|
| `BNBUSDT_8h_funding.csv` | `6196489f6be9b9d662da9f0219ff939197891659ad529ab58946f5cdabb69619` |
| `BTCUSDT_8h_funding.csv` | `d3264c1ca24879ba7da440aa2c232806afbb2adea0ad3b4e306b8da9f27be59d` |
| `ETHUSDT_8h_funding.csv` | `7cd029ac80b213bd27ff20a42c41c68ca414c69006a199c735d85d024e6ab93d` |
| `SOLUSDT_8h_funding.csv` | `7037ab75774a46918c045b6433004078db2ade18cc88058a828b675f7c2724d6` |
| `XRPUSDT_8h_funding.csv` | `a24452780672d2033fc4a16c3e88ade2c4da7318927e974fbafc7af5fcb19f6f` |

`funding_source_bundles/` did not exist in the real lane before this run.
Writer/trader/live/backfill process scan: `0` matches (pre and post).

## BUNDLE (real lane)

Built from the real committed snapshot envelope with
`funding_source_bundle.build_funding_source_bundle_v1(envelope)`, written with
`ledger.write_bytes_atomic` under the real lane `funding_source_bundles/`:

- path:
  `/srv/qnty/output/paper_pnl_null_shadow_v0/funding_source_bundles/funding_source_bundle_v1_37f6fb596bd44d63dd7e5efee26ca08e50fcc0785561c25cc6ac384fbfd27cf4.json`
- file sha256: `aaa12ea0ab368cd3f34a6c30fcf37c56213cd3e1bd29751e042a7a0dbeb8414b`, size `38949`
- schema `FUNDING_SOURCE_BUNDLE_SCHEMA_V1`
- `source_bundle_sha256`:
  `37f6fb596bd44d63dd7e5efee26ca08e50fcc0785561c25cc6ac384fbfd27cf4`
  (identical to the PR #109 copied-lane bundle — source rows preserved)
- `snapshot_bundle_sha256`:
  `8b9d80408b5aae517ba745a5072d9f7d09125572a23ea5e792e2d80e9c099d69`
  (matches batch-17 `funding_source_snapshot_bundle_sha256` — binding OK)
- `snapshot_sha256`:
  `29e513f994330a0cf0009889c9801d110d10eae6d78726ba7d68935f4c080566`
  (real envelope's `snapshot_sha256`)
- self-integrity: `recompute_bundle_sha256` matches stored; `bundle_window_reasons` `[]`
- symbols: `BNBUSDT`, `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `XRPUSDT`
- row counts: total `59`; BNBUSDT `6`, BTCUSDT `10`, ETHUSDT `10`, SOLUSDT `23`, XRPUSDT `10`
- evaluation window: `2026-06-25T08:00:00Z` → `2026-07-05T16:00:00Z`

Bundle snapshot binding matched expectation; no stop condition on bundle
identity.

## CANDIDATE VERIFIER (to /tmp only)

- Literal API: `verify_database(real_shadow_db, source_mode="bundle")` →
  `status=OK`, `exit_code=0`, `ok=true`, `failures=[]`,
  `funding_clean_carry_decision=CLEAN_NET_OF_CARRY`,
  `funding_clean_carry_status=clean_net_of_carry`, reason codes `[]`.
- Publish envelope (bundle mode): reproduced `verify_and_publish`'s envelope
  builder in bundle mode — `_open_snapshot` (read-only) →
  `_verify_connection(db, source_mode="bundle")` → `_content_digests` →
  `_build_published_report` — because the sanctioned `verify_and_publish`
  hardcodes live-current mode and also writes `paper_verify_receipt.md` /
  `paper_verify_log.jsonl`, which are outside this task's allowed mutations.
  Only the report JSON would have been promoted.
- Candidate report (published envelope) written to:
  `/tmp/qnty_bundle_mode_official_report_promotion_20260708T203941Z/candidate_official_report.json`
  - candidate sha256: `aa8ff516ffc4aff0a10561296258fd07b0b5bdd9027e9732e37857aea790a22b`
  - `verified_at`: `2026-07-08T20:45:34Z`
  - top-level `status=OK`, `trusted=true`, `failure_count=0`
  - `content_sha256`: `5e8903044d9ed7cad2b07dd2e9e5a9077765069bb4bf8971127449208bc929be`
  - full-ledger `funding_clean_carry`: `decision=CLEAN_NET_OF_CARRY`,
    `status=clean_net_of_carry`, `reason_codes=[]`,
    `source_resolution_mode=bundle`, `snapshot_status=present_valid`,
    `bundle_path` = the real-lane bundle above,
    `source_bundle_sha256=37f6fb59...`, resum `status=ok`
    (`funding_rows=59`, `funding_amount_sum≈3.44000686`).

## CANDIDATE ACCEPTANCE GATE TABLE

| # | Gate | Result | Detail |
|---|------|--------|--------|
| G1 | `status = OK` | PASS | `OK` |
| G2 | `failure_count = 0` | PASS | `0` |
| G3 | `funding_clean_carry.source_resolution_mode = bundle` | PASS | `bundle` |
| G4 | full-ledger `funding_clean_carry_status = clean_net_of_carry` | PASS | `clean_net_of_carry` |
| G5 | `funding_clean_carry_decision = CLEAN_NET_OF_CARRY` | PASS | `CLEAN_NET_OF_CARRY` |
| G6 | full-ledger `funding_clean_carry_reason_codes = []` | PASS | `[]` |
| G7 | no `funding_source_file_digest_mismatch` anywhere in report | **FAIL** | present in `funding_clean_carry_batch_reason_codes[1]` |
| G8 | no `funding_source_row_digest_mismatch` / `..._snapshot_path_outside_snapshot_dir` / `..._snapshot_db_mismatch` | PASS | none present |
| G9 | report exposes bundle path / hash / source identity | PASS | `funding_clean_carry.{bundle_path, source_bundle_sha256, original_source_digests}` present |
| G10 | real DB unchanged after verifier | PASS | `00a4817e...` pre = mid = post |
| G11 | live source CSVs unchanged after verifier | PASS | all five unchanged |
| G12 | official report unchanged before replacement | PASS | `653605a7...`, size 3531 |
| G13 | literal `verify_database` matches published envelope | PASS | status/decision/reason codes match |

**Blocking gate: G7.** The forbidden string is an *active* reason code, but only
in the **batch-scoped, additive** clean-carry stamp — not the full-ledger gate.

## ROOT CAUSE OF G7 FAILURE

`funding_clean_carry_batch` (batch id `17`):

- `decision = CAVEATED_ENGINE_SEMANTICS`
- `status = refused_digest_mismatch`
- `reason_codes = [funding_source_batch_window_mismatch, funding_source_file_digest_mismatch]`
- batch evaluation window `2026-07-03T08:00:00Z` → `2026-07-05T16:00:00Z`
  (vs full-ledger `2026-06-25T08:00:00Z` → `2026-07-05T16:00:00Z`)

`_build_funding_clean_carry_batch_stamp` (`quantbot/paper/sqlite_verify.py`)
takes **no `source_mode`** parameter — the batch-scoped stamp always resolves
funding-source evidence in **live-current** mode and reads the mutable
`data/*.csv`. `source_mode="bundle"` reaches only the full-ledger stamp
(`_build_funding_clean_carry_stamp`, `sqlite_verify.py:3006-3014`); the batch
stamp is explicitly additive ("does NOT change full-ledger", `sqlite_verify.py:3026`).

The live CSV digests have drifted away from the batch-17 snapshot's captured
`full_file_sha256` digests. Snapshot-captured vs current live (examples):

| symbol | snapshot-captured (bundle) | current live CSV |
|---|---|---|
| BTCUSDT | `65c66a32ed97638bd80ac6110b484a8d96707f6d9e80d57313e2295210750c8e` | `d3264c1ca24879ba7da440aa2c232806afbb2adea0ad3b4e306b8da9f27be59d` |
| ETHUSDT | `e9b3423bd567bd1724a2d1819300b6f6c7ac8f49fa406a2b68f504996db467a9` | `7cd029ac80b213bd27ff20a42c41c68ca414c69006a199c735d85d024e6ab93d` |
| SOLUSDT | `a0980a1a1e154a2282601b98210e1d80ce7bafef0cc66ee1acbac3f66a15cf6a` | `7037ab75774a46918c045b6433004078db2ade18cc88058a828b675f7c2724d6` |

The drift is systemic: `qnty-data-refresh.timer` (last fire 2026-07-08T16:05:14Z,
next ~2026-07-09T00:05Z) keeps rewriting the live CSVs, and no committed batch
has re-snapshotted since batch 17. This is exactly the drift bundle mode is
designed to immunize the full-ledger gate against — and it does. But the
additive batch stamp has no bundle mode, so it stays caveated, and the merged
PR #110 acceptance gate #7 ("no `funding_source_file_digest_mismatch` anywhere in
report") forbids promotion while that string is present. The PR #109 copied-DB
dry run reported this string absent because at that time (13:27Z, CSV mtimes
08:07Z) the live CSVs still matched the snapshot digests.

## VERIFY / POST-RUN INTEGRITY

Official report **NOT** replaced (no backup, no atomic rename performed):

- official report unchanged: `653605a76fdd0b8117c8373c9dadd3fcd41bed147778920c82f29f19f14e0ffd`, size `3531`
- real DB unchanged: `00a4817e1d49aef51398fe0022cc2f3754302bc12f445912d4eb0d0596fc21ce`
- all five live source CSVs unchanged pre/post (values above)
- real-lane bundle dir contains exactly one file — the additive bundle
  `..._37f6fb59...json` (`aaa12ea0...`)
- writer/trader/live/backfill process scan: `0` (pre and post)
- no service/timer/cron/systemd mutation (timers listed read-only for context)
- `/srv/qnty/repo` main worktree untouched (`[behind 40]`)
- scratch worktrees removed

## WHAT WAS TOUCHED

- Created one real-lane immutable bundle file under `funding_source_bundles/`
  (allowed additive mutation; content-addressed, harmless if unused).
- Created one git-owned docs/status receipt (this file).
- Created and removed `/tmp` scratch worktrees and scratch outputs.

## WHAT WAS NOT TOUCHED

No official report overwrite (candidate gate failed). No real shadow DB
mutation. No prod DB mutation. No source CSV mutation. No service, timer, cron,
or systemd mutation. No writer/trader/live/backfill/data-refresh run. No deploy.
No exchange keys. No live integration. No source-freeze. No `paper_verify_receipt.md`
or `paper_verify_log.jsonl` write. No `/srv/qnty/repo` main worktree
checkout/pull/reset. No cleanup of real artifacts beyond `/tmp` and worktrees.
`EDGE_UNPROVEN` and `BLOCK_LIVE_INTEGRATION` unchanged.

## VERDICT

`FUNDING_SOURCE_BUNDLE_MODE_OFFICIAL_REPORT_PROMOTION_EXECUTION_BLOCKED`

The real-lane bundle-mode **full-ledger** verifier reached `CLEAN_NET_OF_CARRY`
(`status=OK`, `trusted=true`, `failure_count=0`, empty full-ledger reason codes),
proving bundle mode resolves source evidence cleanly against the real shadow DB
without reading drifted live CSV bytes. However, candidate acceptance gate #7
("no `funding_source_file_digest_mismatch` anywhere in report") failed: the
**additive, non-gating, batch-scoped** clean-carry stamp always runs
live-current and reports `funding_source_file_digest_mismatch` because the
scheduled `qnty-data-refresh` has drifted the live CSVs away from the batch-17
snapshot. Per the task's failure rule, the official report was **not** replaced
and no backup was created.

## RECOMMENDED NEXT ACTION

Docs-only decision plan (no execution) to resolve the letter-vs-intent tension in
gate #7 before any real promotion, choosing one of:

1. **Scope gate #7 to the full-ledger decision** (exclude the explicitly additive
   `funding_clean_carry_batch_*` block from the "anywhere in report" search), since
   the batch stamp is documented as non-gating and has no bundle mode. Then a
   promotion could proceed on the clean full-ledger bundle-mode verdict.
2. **Realign first**: allow a fresh committed shadow batch to re-snapshot against
   the current live CSVs (or a source-freeze), so both full-ledger and batch
   stamps are clean — requires separate authorization (writer run / source-freeze
   are currently forbidden).
3. **Extend bundle mode to the batch stamp** (code change: thread `source_mode`
   into `_build_funding_clean_carry_batch_stamp`) so batch-scoped resolution is
   also immune to live CSV drift — code change, out of this docs-only lane.

Keep `EDGE_UNPROVEN` and `BLOCK_LIVE_INTEGRATION` explicit. Do not treat the
clean full-ledger gate as trading/live approval.
