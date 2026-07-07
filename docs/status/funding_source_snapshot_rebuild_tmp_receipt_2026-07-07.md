# QNTY Funding Source Snapshot Rebuild Tmp Receipt — 2026-07-07

## Status Boundary

- `EDGE_UNPROVEN` remains.
- `BLOCK_LIVE_INTEGRATION` remains.
- full-ledger `CAVEATED_ENGINE_SEMANTICS` remains until a real DB-linked verifier
  run proves otherwise.
- This is a `/tmp` candidate rebuild receipt only.
- This receipt does not prove edge, profitability, statistical significance,
  shorting readiness, live readiness, or production deployment.
- This receipt does not mutate prod/shadow DBs.
- This receipt does not backfill historical rows.
- This receipt does not overwrite official reports.
- This receipt does not recommit snapshots to the real DB.
- This receipt does not run writer/trader/live code.
- This receipt does not promote `/tmp` output to an official report.

## Scope

- date: 2026-07-07.
- PR #94 merge SHA: `df37594179b7a40cc554dec751d49744e5c760d7`.
- local repo head: `df37594179b7a40cc554dec751d49744e5c760d7` (branch tip before this
  receipt commit; branched from updated `main`).
- branch name: `docs/funding-source-snapshot-rebuild-tmp-receipt`.
- output doc path: `docs/status/funding_source_snapshot_rebuild_tmp_receipt_2026-07-07.md`.
- VM repo path/head/status: `/srv/qnty/repo` @ `2bd88430fe6b2881aaa2b32947002217d3e02ba5`,
  status `## main...origin/main` (clean; **not modified** by this task).
- temp code path: `/tmp/qnty-snapshot-rebuild-df37594179b7a40cc554dec751d49744e5c760d7`
  (current local `quantbot/` package copied to VM `/tmp`; no `.git`, no `.venv`,
  no output DBs; **retained**).
- shadow DB path: `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db`.
- official shadow report path:
  `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_verify_report.json`.
- data dir path: `/srv/qnty/repo/data`.
- prod DB accessed: **no**. Shadow DB opened **read-only/immutable** only
  (`file:...?mode=ro&immutable=1` + `PRAGMA query_only=ON`). No writer ran.
- outputs written only to `/tmp`: **yes** (candidate + diagnostic JSON under `/tmp`;
  **retained**, listed below).

## Method

- **Stage A — source integrity.** Collected before/after `size`, `mtime`, `sha256`
  for the shadow DB and official shadow report; VM repo `head`/`status`; full shadow
  lane output-dir listing; and current funding-source CSV `size`/`mtime`/`sha256`.
- **Stage B — code source.** Copied the current **local** `quantbot/` package (PR #94
  merge SHA) to VM `/tmp`, not the stale VM repo code. Excluded `.git`, `.venv`,
  `__pycache__`, and output DBs. No dependencies installed; no package managers used.
- **Stage C — candidate build.** Built two candidate snapshots from **current VM
  source CSVs** using the production **pure** builder helpers
  (`build_funding_source_snapshot_payload_v1`,
  `build_funding_source_snapshot_envelope_v1`, `build_source_file_digest`,
  `validate_funding_source_snapshot_envelope_v1`). Required funding windows and
  source-row lists were derived from the shadow `funding` table (read-only) and the
  current CSVs. Candidate JSON written **only** under `/tmp`.
- **Stage D — clean-carry evaluation.** Evaluated each candidate against both the
  batch expected window and the full-ledger expected window with the production
  `clean_mode_decision_from_snapshot_v1` helper, using current source-file digests as
  the digest expectation. Also re-evaluated the currently committed batch-17 snapshot
  against current digests to reproduce the PR #92 caveat.
- **Stage E — integrity checks.** Re-checked all Stage A artifacts and confirmed the
  shadow lane output dir gained no new files.
- read-only DB method: `sqlite3.connect("file:<path>?mode=ro&immutable=1", uri=True)`
  followed by `PRAGMA query_only=ON`. No `INSERT`/`UPDATE`/`DELETE`/`ATTACH`.
- No writes to `/srv/qnty/output`. No writes to `/srv/qnty/repo`. No official report
  overwrite. No DB mutation.

## Source Integrity

| Artifact | size (before → after) | mtime (before → after) | sha256 (before → after) | Match |
|---|---|---|---|---|
| Shadow DB | 172032 → 172032 | 1783312420 → 1783312420 (2026-07-06T04:33:40Z) | `3cbc6e9c…c739a897` → same | ✅ |
| Official shadow report | 3531 → 3531 | 1782929757 → 1782929757 (2026-07-01T18:15:57Z) | `653605a7…f14e0ffd` → same | ✅ |
| VM repo head | — | — | `2bd88430…d3e02ba5` → same (status clean) | ✅ |

- Shadow DB sha256 (before == after): `3cbc6e9c63c74072aa019d6a53b1f5519f369f95cec1f9c21495e307c739a897`.
- Official report sha256 (before == after): `653605a76fdd0b8117c8373c9dadd3fcd41bed147778920c82f29f19f14e0ffd`.
- Data dir files inspected (current, read-only): the 5 funding CSVs referenced by the
  shadow `funding` table — `BNBUSDT`, `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `XRPUSDT`
  `_8h_funding.csv` under `/srv/qnty/repo/data`. Current per-file sha256:
  - `BNBUSDT_8h_funding.csv` `8dc595c1675c555b3e82a61e4d633b5c25ea6219fa0c30acaaf76b6592d10a5b`
  - `BTCUSDT_8h_funding.csv` `5369211f7a33312608bc57bc5de0123ed05fd576c7eb56ae49baa1ce28f96e57`
  - `ETHUSDT_8h_funding.csv` `edf516720f364b7ba1193e1ffacfb45bfa2e60d02126b84607576b6f2a9caa4c`
  - `SOLUSDT_8h_funding.csv` `b9c4b9608c17fce0b48b3fa4c8357997a35f0dc0268682ed2a2f4da1fdeabe22`
  - `XRPUSDT_8h_funding.csv` `96e0b42ac2ef06d5b623a31c2c9a9f380738004d71d27d53abe65116192fce01`
- Shadow lane output dir: **unchanged** — identical file listing before/after; no new
  files created; `find -newermt 2026-07-07T02:30Z` under the lane dir returned empty.
- verdict: `FUNDING_SOURCE_SNAPSHOT_REBUILD_TMP_READ_ONLY_CONFIRMED`.

## Current Inputs

- latest batch id: **17** (`committed_at` 2026-07-06T04:33:09Z, `git_sha`
  `2bd88430fe6b2881aaa2b32947002217d3e02ba5`).
- prior watermark → new watermark: `2026-07-03T08:00:00` → `2026-07-05T16:00:00`
  (`ledger_state.watermark_bar_ts` = `2026-07-05T16:00:00`).
- batch window: `2026-07-03T08:00:00Z -> 2026-07-05T16:00:00Z` (33 funding rows).
- full-ledger funding window: `2026-06-25T08:00:00Z -> 2026-07-05T16:00:00Z`
  (59 funding rows, all `rate_available=1`, i.e. funding coverage complete).
- symbols (funding table): `BNBUSDT`, `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `XRPUSDT`.
- source files: the 5 CSVs above; current per-file digests as listed under Source
  Integrity.
- current source bundle digest (full-ledger candidate):
  `bfa6755f9edd0d24750e3d7045cfbd5c1bf02a48b96861b2182e2fb725cd1f6a`.
- latest committed snapshot (batch 17):
  - path: `…/funding_source_snapshots/funding_source_snapshot_v1_1c5b433eb3adc345bdf024f20b45ffba874e77090ab5fc652f81fe169791451b.json`
  - file sha256: `730455698eb58e72dd7586d52f0e064350ace8dcbc077eddadeb85d740bfe8a7`
  - bundle sha256: `1c5b433eb3adc345bdf024f20b45ffba874e77090ab5fc652f81fe169791451b`
  - envelope `snapshot_sha256`: `7f14e2afc38d260c6da6b2cabc9c6f683474ec6e6599219c03e0190f0ff84fad`
  - evaluation_window: `2026-07-03T08:00:00Z -> 2026-07-05T16:00:00Z` (**batch-scoped**)
  - write_state: `committed`; coverage_decision: `complete`.
- comparison to PR #92 diagnosis: **confirmed**. The committed batch-17 snapshot's
  stored source-file digests differ from **all** current CSV digests (source refresh
  after commit), and its evaluation window is the batch window, not the full-ledger
  span. Re-evaluating it against current digests + the full-ledger window reproduces
  `funding_source_file_digest_mismatch` + `funding_source_snapshot_window_mismatch`.

## Candidate Batch Snapshot

- output path: `/tmp/funding_source_snapshot_candidate_batch_20260707T000000Z.json`.
- size: 28289 bytes; file sha256:
  `abb959c0a50f16b2df078bef4121da4df13b21499dcddca93ff36ef32f648ab7`.
- envelope `snapshot_sha256`:
  `5eed8e36ef7fb0b95dc33fcdb9170c79fce819a49e7752823a4f86fde756664c`.
- source_bundle_sha256:
  `738b0237f450e8aa4c70803a5428e6515278db138dfc4c5f94e694e99d2274c9`.
- evaluation window: `2026-07-03T08:00:00Z -> 2026-07-05T16:00:00Z`.
- symbols covered: `BNBUSDT`, `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `XRPUSDT`.
- required windows: count 33; span `2026-07-03T08:00:00 -> 2026-07-05T16:00:00`.
- coverage decision: `complete`; payload reason codes: none; envelope validation: OK.
- per-file digest summary: all 5 `full_file_sha256` equal the current CSV digests
  (digest gate would clear against current source).
- dry-run/write_state status: the candidate lives **only** under `/tmp`; no DB
  reference updated. `write_state` is the fixed enum `{pending, committed, orphaned}`
  — there is no `tmp`/`dry-run` value — so it is stamped `committed` **solely to
  isolate the digest/window/coverage gates** (matching PR #94 pinned semantics). This
  is a candidate-content field, not a DB commit.
- batch evaluation result: `clean_net_of_carry_allowed = true`, reason_codes `[]`.
- full-ledger evaluation result: `clean_net_of_carry_allowed = false`, reason_codes
  `[funding_source_snapshot_window_mismatch]` (digest gate clears; window gate fails
  by design).
- verdict: `TMP_REBUILD_BATCH_CANDIDATE_CLEARS_BATCH_ONLY`.

## Candidate Full-Ledger Snapshot

- output path: `/tmp/funding_source_snapshot_candidate_full_ledger_20260707T000000Z.json`.
- size: 46623 bytes; file sha256:
  `f5efc760471d39e0f8031d31c61dfd8fd70c436d0c44e59965659d753d886a39`.
- envelope `snapshot_sha256`:
  `5c635e7e08e6b6708ddf9e42c3fd3d42a7ddd9fa558ec7c395fbdadaedb14645`.
- source_bundle_sha256:
  `bfa6755f9edd0d24750e3d7045cfbd5c1bf02a48b96861b2182e2fb725cd1f6a`.
- evaluation window: `2026-06-25T08:00:00Z -> 2026-07-05T16:00:00Z`.
- symbols covered: `BNBUSDT`, `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `XRPUSDT`.
- required windows: count 59; span `2026-06-25T08:00:00 -> 2026-07-05T16:00:00`.
- coverage decision: `complete`; payload reason codes: none; envelope validation: OK.
- per-file digest summary: all 5 `full_file_sha256` equal the current CSV digests
  (digest gate clears against current source).
- full-ledger evaluation result: `clean_net_of_carry_allowed = true`, reason_codes
  `[]` (digest gate and full-ledger window gate both clear).
- batch evaluation result (relevant): `clean_net_of_carry_allowed = false`,
  reason_codes `[funding_source_snapshot_window_mismatch]` (a full-ledger-scoped
  window does not equal the batch window under the strict-equality gate).
- verdict: `TMP_REBUILD_FULL_LEDGER_CANDIDATE_CLEARS_DIGEST_WINDOW`.

## Clean-Carry Gate Comparison

| Snapshot | Digest gate (vs current source) | Batch window gate | Full-ledger window gate | Coverage gate |
|---|---|---|---|---|
| Committed batch-17 (PR #92) | ❌ mismatch (source refreshed) | ✅ (batch-scoped) | ❌ window mismatch | ✅ complete |
| `/tmp` batch candidate | ✅ match | ✅ clears | ❌ window mismatch (by design) | ✅ complete |
| `/tmp` full-ledger candidate | ✅ match | ❌ window mismatch | ✅ clears | ✅ complete |

- Only the `/tmp` full-ledger candidate produces an **empty** reason set (the sole
  promotable state). It is still evidence-only and not attached to any DB.
- The committed batch-17 snapshot fails the digest gate purely because the current
  CSVs changed after it was committed (evidence/provenance caveat, not an arithmetic
  or coverage defect), exactly as PR #92 diagnosed and PR #94 pinned.

## Impact On Existing Receipts

- PR #94 tests remain valid — this run empirically reproduces the pinned semantics
  (batch clears batch-only; full-ledger clears both gates; stale digest refuses;
  any digest/window caveat blocks promotion). 74/74 pinned tests pass locally.
- PR #93 plan remains valid — this is step 2 (`/tmp` snapshot rebuild receipt) of the
  conservative sequence; step 3 (copied-DB dry run) and step 4 (real DB recommit under
  explicit later approval) are untouched.
- PR #92 diagnosis remains valid — the committed snapshot is batch-scoped and its
  source digests are stale versus current CSVs; both are confirmed here.
- This receipt provides candidate evidence only.
- This does not update the DB-linked snapshot reference.
- This does not change official reports.
- This does not prove edge.

## Recommended Next Action

`FUNDING_SOURCE_SNAPSHOT_RECOMMIT_COPIED_DB_DRY_RUN_GIT_OWNED`

- apply the full-ledger candidate snapshot to a **copied** shadow DB only;
- run the current verifier against the copied DB;
- prove the digest/window gate can clear on a **DB-linked** path (not just the pure
  in-memory helper), while still making **no** real DB mutation;
- do **not** recommit to the real DB until a copied-DB dry run exists and is clean.

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

## Verdict

`FUNDING_SOURCE_SNAPSHOT_REBUILD_TMP_RECEIPT_RECORDED_CAVEATED`

Caveat: the VM's system Python 3.12 lacks `pandas`, so the writer module
(`quantbot.paper.sqlite_writer`) could not be imported to reuse its two glue helpers
(`_required_funding_windows_for_snapshot`, `_read_funding_source_csv_rows`). The
experiment used **faithful in-script reimplementations** of that trivial glue (window
de-duplication from `funding` rows; CSV row reading with the same
`symbol/fundingTime_ms/source_file_path/row_index/funding_rate` shape). The
**core** snapshot builder and clean-carry helper are the genuine production pure
functions from the copied local code. The glue reimplementation was validated against
the DB (33 batch / 59 full required windows; coverage `complete` for both) and does not
change any gate outcome. All results are evidence-only; `EDGE_UNPROVEN`,
`BLOCK_LIVE_INTEGRATION`, and full-ledger `CAVEATED_ENGINE_SEMANTICS` are preserved.

Supporting `/tmp` artifacts (retained, VM-local, non-official):

- `/tmp/funding_source_snapshot_candidate_batch_20260707T000000Z.json`
  sha256 `abb959c0a50f16b2df078bef4121da4df13b21499dcddca93ff36ef32f648ab7`
- `/tmp/funding_source_snapshot_candidate_full_ledger_20260707T000000Z.json`
  sha256 `f5efc760471d39e0f8031d31c61dfd8fd70c436d0c44e59965659d753d886a39`
- `/tmp/funding_source_snapshot_rebuild_diagnostic_20260707T000000Z.json`
  sha256 `29371a4b0456d4e2dc5214d8d3d6f895c9248e874f004072bc30c35be093d136`
- `/tmp/qnty-snapshot-rebuild-df37594179b7a40cc554dec751d49744e5c760d7/` (code copy)
