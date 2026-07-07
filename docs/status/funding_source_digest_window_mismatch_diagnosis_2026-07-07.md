# QNTY Funding Source Digest/Window Mismatch Diagnosis — 2026-07-07

## Status Boundary

- `EDGE_UNPROVEN` remains.
- `BLOCK_LIVE_INTEGRATION` remains.
- Full-ledger `CAVEATED_ENGINE_SEMANTICS` remains.
- This is diagnosis only.
- This receipt does not prove edge, profitability, statistical significance,
  shorting readiness, live readiness, or production deployment.
- This receipt does not mutate prod/shadow DBs.
- This receipt does not backfill historical rows.
- This receipt does not overwrite official reports.
- This receipt does not run writer/trader/live code.
- This receipt does not promote `/tmp` verifier output to an official report.

## Scope

- Date: 2026-07-07.
- PR #91 merge SHA: `b0f5f18b13ade4c9dbe278f247ca31c962403057`.
- Local repo head: `b0f5f18b13ade4c9dbe278f247ca31c962403057`.
- Branch: `docs/funding-source-mismatch-diagnosis`.
- Output doc path:
  `docs/status/funding_source_digest_window_mismatch_diagnosis_2026-07-07.md`.
- VM repo path: `/srv/qnty/repo`.
  - Observed VM repo head: `2bd88430fe6b2881aaa2b32947002217d3e02ba5`
    (unchanged before/after; still stale relative to current clean-carry
    verifier semantics, exactly as in PR #91).
  - Observed VM repo status: `## main...origin/main` (clean, not dirty).
- Shadow DB path: `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db`.
- Official shadow report path:
  `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_verify_report.json`.
- Data dir path: `/srv/qnty/repo/data`.
- Prod DB accessed: **No**. `PROD_DB_NOT_ACCESSED_BY_THIS_RECEIPT`.
- Verifier rerun or PR #91 output reused: **Reused** PR #91 `/tmp` output
  (`/tmp/shadow_verify_fresh_20260707T010858Z.json`, still present on the VM).
  No new verifier run was performed for this diagnosis.
- Temporary files written only to `/tmp`: **Yes** — the only scripts used were
  local scratchpad Python piped over SSH stdin to the VM interpreter; nothing
  was written under `/srv/qnty/repo` or `/srv/qnty/output`.

## Method

- **Source integrity method.** Before diagnosis, captured `stat` (size, mtime)
  and `sha256sum` of the shadow DB and the official shadow report, plus VM repo
  head/status, the funding-source snapshot sidecar directory listing, the
  shadow lane directory listing, and the `data/` funding CSV listing. After
  diagnosis, re-`stat` + re-`sha256` of the shadow DB and official report and
  re-checked VM repo head/status; compared before/after.
- **Read-only DB introspection.** Opened the shadow DB via the same read-only
  path the verifier uses: SQLite URI `file:<abs>?mode=ro&immutable=1` with
  `PRAGMA query_only=ON`. Introspected `ledger_batches` columns via
  `PRAGMA table_info`, read the latest committed batch's funding-source
  snapshot reference columns, and read the `funding` table window
  (`MIN(window_start)`, `MAX(window_end)`) and distinct symbols. No write cursor
  was opened; no `-wal`/`-shm` was created.
- **Verifier JSON extraction.** Read PR #91's retained `/tmp` verifier output
  and extracted the full-ledger and batch clean-carry objects, snapshot object,
  source-path resolution fields, digest fields, and window fields.
- **Digest recomputation method.** Read the committed funding-source snapshot
  sidecar JSON (referenced by `ledger_batches.funding_source_snapshot_path`),
  extracted the per-file `full_file_sha256` values and `source_bundle_sha256`,
  and recomputed the current `sha256` of each source CSV under
  `/srv/qnty/repo/data`. Recomputed the bundle digest two ways using the
  verifier's own canonicalization (`json.dumps(..., sort_keys=True,
  separators=(",",":"))` over the `source_files` list, per
  `funding_source_snapshot.py`): once over the stored file digests (must equal
  the stored bundle) and once over the current file digests.
- **Window comparison method.** Compared the committed snapshot's
  `evaluation_window` against (a) the full-ledger expected window
  (`_funding_evaluation_window` = `MIN(window_start)`/`MAX(window_end)` of the
  `funding` table) and (b) the batch-scoped window (batch 17
  `prior_watermark_bar_ts` -> `new_watermark_bar_ts`).
- **Post-run / post-diagnosis integrity checks.** Re-hashed shadow DB and
  official report; re-checked VM repo head/status. All matched.
- No writes to `/srv/qnty/output`. No writes to `/srv/qnty/repo`. No official
  report overwrite. No DB mutation.

## Source Integrity

- Shadow DB:
  - before: size `172032`, mtime `1783312420`,
    sha256 `3cbc6e9c63c74072aa019d6a53b1f5519f369f95cec1f9c21495e307c739a897`
  - after: size `172032`, mtime `1783312420`,
    sha256 `3cbc6e9c63c74072aa019d6a53b1f5519f369f95cec1f9c21495e307c739a897`
  - match status: **MATCH** (size, mtime, sha256 all equal).
- Official shadow report:
  - before: size `3531`, mtime `1782929757`,
    sha256 `653605a76fdd0b8117c8373c9dadd3fcd41bed147778920c82f29f19f14e0ffd`
  - after: size `3531`, mtime `1782929757`,
    sha256 `653605a76fdd0b8117c8373c9dadd3fcd41bed147778920c82f29f19f14e0ffd`
  - match status: **MATCH** (size, mtime, sha256 all equal).
- VM repo:
  - before head/status: `2bd88430fe6b2881aaa2b32947002217d3e02ba5`,
    `## main...origin/main` (clean).
  - after head/status: `2bd88430fe6b2881aaa2b32947002217d3e02ba5`,
    `## main...origin/main` (clean).
  - match status: **MATCH**.
- Data dir files inspected (read-only, `stat` + `sha256` only; no writes):
  ten `*_8h_funding.csv` files under `/srv/qnty/repo/data`; the five funding
  symbols actually referenced by the committed snapshot / `funding` table are
  `BNBUSDT`, `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `XRPUSDT`. All source CSVs carry
  mtimes of `2026-07-07 00:06–00:07 UTC` (see below), i.e. **after** the
  committed snapshot and shadow DB were written on `2026-07-06 04:33 UTC`.
- Verdict: `FUNDING_SOURCE_DIAGNOSIS_READ_ONLY_CONFIRMED`.

## DB Snapshot Facts

Actual table/column names and values.

- Snapshot reference lives on table **`ledger_batches`** (columns confirmed via
  `PRAGMA table_info`): `funding_source_snapshot_path`,
  `funding_source_snapshot_sha256`, `funding_source_snapshot_bundle_sha256`,
  `funding_source_snapshot_schema_version`, `funding_source_snapshot_write_state`,
  `funding_source_snapshot_created_at`. The snapshot **payload/envelope** itself
  is a JSON sidecar on disk under
  `<lane_dir>/funding_source_snapshots/`, not an inline DB blob.
- Latest committed batch (the full-ledger clean-carry target):
  - `batch_id` = `17`
  - `prior_watermark_bar_ts` = `2026-07-03T08:00:00`
  - `new_watermark_bar_ts` = `2026-07-05T16:00:00`
  - `committed_at` = `2026-07-06T04:33:09Z`
  - `funding_source_snapshot_path` =
    `/srv/qnty/output/paper_pnl_null_shadow_v0/funding_source_snapshots/funding_source_snapshot_v1_1c5b433eb3adc345bdf024f20b45ffba874e77090ab5fc652f81fe169791451b.json`
  - `funding_source_snapshot_sha256` (DB column) =
    `730455698eb58e72dd7586d52f0e064350ace8dcbc077eddadeb85d740bfe8a7`
  - `funding_source_snapshot_bundle_sha256` (DB column) =
    `1c5b433eb3adc345bdf024f20b45ffba874e77090ab5fc652f81fe169791451b`
  - `funding_source_snapshot_schema_version` = `FUNDING_SOURCE_SNAPSHOT_SCHEMA_V1`
  - `funding_source_snapshot_write_state` = `committed`
  - `funding_source_snapshot_created_at` = `2026-07-06T04:33:09Z`
- Committed snapshot sidecar payload (from the referenced JSON):
  - envelope `snapshot_sha256` = `7f14e2afc38d260c6da6b2cabc9c6f683474ec6e6599219c03e0190f0ff84fad`
    (this is the verifier's `snapshot_sha256`; note it differs from the DB
    `funding_source_snapshot_sha256` column value `730455698…` — the DB column
    and the content-addressed envelope digest are distinct fields, and this
    difference is **not** one of the clean-carry refusal reasons observed).
  - `source_bundle_sha256` = `1c5b433eb3adc345bdf024f20b45ffba874e77090ab5fc652f81fe169791451b`
    (matches the DB `funding_source_snapshot_bundle_sha256` column).
  - `evaluation_window` = `{start: 2026-07-03T08:00:00Z, end: 2026-07-05T16:00:00Z}`.
  - `symbols_covered` = `[BNBUSDT, BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT]`.
  - `coverage_decision` = `complete`; payload `reason_codes` = `[]`.
  - `write_state` = `committed`.
  - `required_funding_windows` count = `33`; span
    `2026-07-03T08:00:00Z` -> `2026-07-05T16:00:00Z`.
  - `snapshot_metadata`: `batch_start_watermark` = `2026-07-03T08:00:00`,
    `batch_end_watermark` = `2026-07-05T16:00:00`, `ledger_batch_id` = `17`,
    `pending_batch_id` = `pending-17e25621da6aa3f5a7b836c8`,
    `db_path_reference` =
    `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db`.
  - Per-file stored digests (committed snapshot):
    - `BNBUSDT_8h_funding.csv`: `4a5f4aaa184e70ee0c5801d9e23ea432996f9efcaf1b18a7b0432d1474519fbb`
    - `BTCUSDT_8h_funding.csv`: `fc55f193453e6986693410ec216061d79d1124fb311a1f054be309eb2cc69c24`
    - `ETHUSDT_8h_funding.csv`: `6e8dc79ff138b20422d1fde839b806abcb2db0a4380b112d87056e7708419323`
    - `SOLUSDT_8h_funding.csv`: `919743bfe48d5315fd32352572af8ccd0ad319a7e1dd6722678b8dc1ab0cfe8c`
    - `XRPUSDT_8h_funding.csv`: `f65912dc39c23d015f2e38016cc577d045b38a97d2cffcb0fdde53f57c9ad6d0`
- `funding` table window (full-ledger expected evaluation window):
  `MIN(window_start)` = `2026-06-25T08:00:00`,
  `MAX(window_end)` = `2026-07-05T16:00:00`, `59` rows, symbols
  `[BNBUSDT, BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT]`.
- Committed batch count: `17`.
- Source path stored in DB reference: the sidecar path above under the shadow
  lane; the per-file source paths inside the payload are absolute
  `/srv/qnty/repo/data/<SYMBOL>_8h_funding.csv`.
- Nothing material was missing/unavailable: the snapshot reference columns are
  all present and populated; the sidecar exists and parses.

## Verifier JSON Facts

- Verifier JSON source path: `/tmp/shadow_verify_fresh_20260707T010858Z.json`
  (PR #91 output, reused — verifier was **not** rerun for this diagnosis).
- Full-ledger clean-carry: decision `CAVEATED_ENGINE_SEMANTICS`, status
  `refused_digest_mismatch`, reason codes
  `["funding_source_file_digest_mismatch", "funding_source_snapshot_window_mismatch"]`.
- Batch clean-carry: decision `CAVEATED_ENGINE_SEMANTICS`, status
  `refused_digest_mismatch`, reason codes
  `["funding_source_file_digest_mismatch"]`.
- Snapshot status: `present_valid`.
- `source_path_available`: `true`.
- `resolved_funding_source_dir`: `/srv/qnty/repo/data`.
- `snapshot_sha256`: `7f14e2afc38d260c6da6b2cabc9c6f683474ec6e6599219c03e0190f0ff84fad`.
- `source_bundle_sha256`: `1c5b433eb3adc345bdf024f20b45ffba874e77090ab5fc652f81fe169791451b`.
- `funding_source_coverage_verdict`: `CLEAN_NET_OF_CARRY`.
- Arithmetic / resum status: `arithmetic_ok = true`, `arithmetic_status = OK`,
  `funding_coverage_decision = complete`, resum `status = ok`
  (`funding_rows = 59`, `funding_amount_sum = 3.44000686`,
  `ledger_state_funding_cum = 3.4400068507041306`,
  `latest_equity_funding_cum = 3.44000685`, `tolerance_abs = 1e-06`,
  resum `reason_codes = []`).
- Window fields (decisive):
  - Committed snapshot `evaluation_window`:
    `{start: 2026-07-03T08:00:00Z, end: 2026-07-05T16:00:00Z}`.
  - Batch object `evaluation_window` (batch 17 watermark window):
    `{start: 2026-07-03T08:00:00Z, end: 2026-07-05T16:00:00Z}` — **matches**
    the snapshot window, which is why the batch gate raises **no** window
    mismatch.
  - Batch object `full_ledger_evaluation_window`:
    `{start: 2026-06-25T08:00:00Z, end: 2026-07-05T16:00:00Z}` — the full-ledger
    expected window, whose **start** (`2026-06-25T08:00:00Z`) differs from the
    snapshot window start (`2026-07-03T08:00:00Z`); this is the source of the
    full-ledger `funding_source_snapshot_window_mismatch`.
- Snapshot object `selected_snapshot_path` = the batch-17 sidecar above;
  `target_batch_id` = `17`.

## Current Source File Digest Facts

- Data dir path: `/srv/qnty/repo/data`.
- Files included (the five funding CSVs referenced by the committed snapshot):
- Per-file current `sha256` vs committed stored `sha256` (all **MISMATCH**):

  | file | stored (committed) | current (VM data dir) | mtime (epoch) |
  |---|---|---|---|
  | `BNBUSDT_8h_funding.csv` | `4a5f4aaa184e70ee…` | `8dc595c1675c555b…` | `1783382811` |
  | `BTCUSDT_8h_funding.csv` | `fc55f193453e6986…` | `5369211f7a333126…` | `1783382798` |
  | `ETHUSDT_8h_funding.csv` | `6e8dc79ff138b204…` | `edf516720f364b7b…` | `1783382805` |
  | `SOLUSDT_8h_funding.csv` | `919743bfe48d5315…` | `b9c4b9608c17fce0…` | `1783382817` |
  | `XRPUSDT_8h_funding.csv` | `f65912dc39c23d01…` | `96e0b42ac2ef06d5…` | `1783382853` |

  Full current digests:
  - `BNBUSDT`: `8dc595c1675c555b3e82a61e4d633b5c25ea6219fa0c30acaaf76b6592d10a5b`
  - `BTCUSDT`: `5369211f7a33312608bc57bc5de0123ed05fd576c7eb56ae49baa1ce28f96e57`
  - `ETHUSDT`: `edf516720f364b7ba1193e1ffacfb45bfa2e60d02126b84607576b6f2a9caa4c`
  - `SOLUSDT`: `b9c4b9608c17fce0b48b3fa4c8357997a35f0dc0268682ed2a2f4da1fdeabe22`
  - `XRPUSDT`: `96e0b42ac2ef06d5b623a31c2c9a9f380738004d71d27d53abe65116192fce01`
- All five current source-CSV mtimes are `2026-07-07 00:06–00:07 UTC`
  (epochs `1783382798`–`1783382853`), i.e. **~19.5 hours after** the committed
  snapshot / shadow DB (`2026-07-06 04:33:09Z`, epoch `1783312389`) and after
  the shadow DB mtime (`1783312420`). The source files were refreshed after the
  snapshot was committed.
- Canonicalization method: reused the verifier's own bundle canonicalization
  (`sha256_text(canonical_json(source_files))` with
  `json.dumps(sort_keys=True, separators=(",",":"), ensure_ascii=True)` from
  `quantbot/paper/funding_source_snapshot.py`), and the same per-file
  full-bytes `sha256` used by `build_source_file_digest`. Canonicalization is
  **not** ambiguous here:
  - Recomputing the bundle over the committed snapshot's **stored** `source_files`
    reproduces the stored `source_bundle_sha256`
    (`1c5b433eb3adc345…` == `1c5b433eb3adc345…`): the committed snapshot is
    internally consistent.
  - Recomputing the bundle after substituting the **current** file digests
    yields `738b0237f450e8aa…`, which does **not** equal the stored bundle
    `1c5b433eb3adc345…`.
- Match/mismatch summary: current bundle **does not** match the verifier's /
  committed `source_bundle_sha256`; every current per-file digest **differs**
  from the committed stored digest.

## Digest Mismatch Diagnosis

Labels:

- `CURRENT_SOURCE_FILES_CHANGED_AFTER_SNAPSHOT` — **primary, confirmed.**
- `COMMITTED_SNAPSHOT_DIGEST_STALE` — corollary (the committed snapshot's
  per-file and bundle digests are now stale relative to the refreshed source
  files).

Evidence:

- All five source CSVs have mtimes `2026-07-07 00:06–00:07 UTC`, strictly after
  the committed snapshot's `created_at` (`2026-07-06T04:33:09Z`).
- Every current per-file `sha256` differs from the committed stored digest.
- The committed snapshot is internally consistent (stored `source_files`
  reproduce the stored `source_bundle_sha256`), so this is not a
  canonicalization defect — hence **not** `VERIFIER_BUNDLE_CANONICALIZATION_UNCLEAR`.
- The path resolved correctly to `/srv/qnty/repo/data` with all five expected
  files present — hence **not** `WRONG_DATA_DIR_FOR_VERIFIER` and **not**
  `MISSING_OR_EXTRA_SOURCE_FILES`.
- The verifier recomputes the expected digest from the **current** source files
  and compares against the committed snapshot; because the current files changed,
  `DB_EXPECTED_DIGEST_DIFFERS_FROM_CURRENT_SOURCE` is true *as a consequence* of
  `CURRENT_SOURCE_FILES_CHANGED_AFTER_SNAPSHOT` (the committed evidence is the
  source of truth; the live files drifted away from it). The root cause is the
  post-snapshot source-file refresh, not a wrong or corrupt DB accounting value.

This is an **evidence/provenance** mismatch, not an arithmetic or DB-accounting
error: PR #91 established `arithmetic_ok = true`, resum `status = ok`, and
`funding_coverage_decision = complete`.

## Window Mismatch Diagnosis

Labels:

- Full-ledger: `SNAPSHOT_WINDOW_DOES_NOT_COVER_LEDGER` — **primary, confirmed.**
- Batch scope: `WINDOW_OK_BUT_VERIFIER_RULE_STRICT` — the batch window matches
  the snapshot window exactly, so no window mismatch is raised at batch scope;
  the batch caveat is digest-only.

Evidence:

- Committed snapshot `evaluation_window` =
  `{2026-07-03T08:00:00Z -> 2026-07-05T16:00:00Z}` — this is **batch-17-scoped**
  (`prior_watermark_bar_ts` -> `new_watermark_bar_ts`), confirmed by matching
  `snapshot_metadata.batch_start_watermark` / `batch_end_watermark`.
- Full-ledger expected window (`_funding_evaluation_window` =
  `MIN(window_start)`/`MAX(window_end)` of the `funding` table) =
  `{2026-06-25T08:00:00Z -> 2026-07-05T16:00:00Z}`.
- The **end** aligns exactly with the shadow watermark
  `2026-07-05T16:00:00` — so the snapshot is **not** stale relative to the
  latest bar, and this is **not** `SNAPSHOT_WINDOW_STALE`.
- The **start** differs: the committed snapshot begins at `2026-07-03T08:00:00Z`
  (batch 17 only), whereas the full-ledger funding span begins at
  `2026-06-25T08:00:00Z`. The committed snapshot therefore does not cover the
  full-ledger funding window; the full-ledger gate compares `evaluation_window`
  by equality (`clean_mode_decision_from_snapshot_v1`), so a batch-scoped
  snapshot can never satisfy the full-span expectation. Window semantics are
  clear from the code and metadata — **not** `WINDOW_SEMANTICS_UNCLEAR`.

## Impact On Existing Receipts

- PR #91 (`docs/status/vm_shadow_verifier_tmp_run_receipt_2026-07-07.md`)
  remains valid: it correctly ran the current verifier in-place against the true
  shadow DB path, resolved the PR #89 path artifact, and correctly reported the
  residual `refused_digest_mismatch` caveat. This diagnosis explains that
  caveat.
- PR #89 (`docs/status/shadow_verifier_fresh_receipt_2026-07-07.md`) remains
  valid: it disclosed the copy-location path artifact, now resolved by PR #91.
- PR #85 stale shadow verifier diagnosis remains historically valid.
- This diagnosis explains **why** full-ledger `CAVEATED_ENGINE_SEMANTICS`
  persists after path resolution: two independent provenance gaps — (1) the
  committed funding-source snapshot's file digests are stale because the source
  CSVs were refreshed after the snapshot was committed
  (`funding_source_file_digest_mismatch`), and (2) the committed snapshot is
  batch-scoped and does not span the full-ledger funding window
  (`funding_source_snapshot_window_mismatch`).
- This does **not** change edge/live status: `EDGE_UNPROVEN` and
  `BLOCK_LIVE_INTEGRATION` remain.
- This does **not** promote or overwrite any official report (the official
  shadow report is byte-for-byte unchanged, still reads
  `watermark_bar_ts = 2026-07-01T08:00:00`).

## Recommended Next Action

**`FUNDING_SOURCE_SNAPSHOT_RECOMMIT_PLAN`** (docs-only planning task), with
`OFFICIAL_REPORT_PROMOTION_BLOCKED` kept in force until it is resolved.

Why:

- The digest mismatch is a pure freshness/provenance issue: the source CSVs are
  refreshed (apparently by a data cron, mtimes `2026-07-07 00:06–00:07 UTC`)
  after the funding-source snapshot is committed, so the committed evidence goes
  stale. Arithmetic, coverage, and resum are already clean. The conservative fix
  is to plan a **recommit** of the funding-source snapshot that (a) is built
  against the current source files and (b) is committed atomically with (or
  digest-pinned to) the shadow batch it describes, so the source files cannot
  drift between snapshot build and batch commit. This must be planned first,
  docs-only, **without** mutating the DB, running the writer, or overwriting the
  official report.
- The window mismatch has an additional structural dimension the recommit plan
  must address: the emitted snapshot is batch-scoped, but the full-ledger gate
  compares against the entire `funding`-table span by equality. A batch-scoped
  recommit alone will clear the **batch** caveat but not the **full-ledger**
  window mismatch. The plan should therefore explicitly decide whether the
  full-ledger gate should consume a full-span snapshot, or whether the
  full-ledger window rule should be reconsidered — which may spin off a separate
  `VERIFIER_DIGEST_SEMANTICS_TESTS` task **before** any operational change.
- Until a fresh, digest-valid, window-covering committed snapshot exists,
  `OFFICIAL_REPORT_PROMOTION_BLOCKED` stands: the `/tmp` verifier output must not
  be promoted to the official report.

The recommendation explicitly avoids: DB mutation, writer runs, official report
overwrite, live/trader changes, and backfill.

## Non-Goals

- no code change
- no test change
- no schema change
- no verifier code change
- no reporter change
- no writer change
- no trader change
- no strategy change
- no DB writes
- no prod/shadow writer run
- no deployment
- no backfill
- no official report overwrite
- no live integration
- no shorting
- no trial registry
- no null/benchmark lane changes

## Verdict

`FUNDING_SOURCE_DIGEST_WINDOW_MISMATCH_DIAGNOSIS_RECORDED`

The scoped read-only diagnosis confirmed that the residual full-ledger and batch
`CAVEATED_ENGINE_SEMANTICS` (`refused_digest_mismatch`) after PR #91's path
resolution is an evidence/provenance issue, not an arithmetic or DB-accounting
error. The committed funding-source snapshot's per-file and bundle digests are
stale because the source CSVs were refreshed after commit
(`CURRENT_SOURCE_FILES_CHANGED_AFTER_SNAPSHOT`), and the committed snapshot is
batch-scoped and does not cover the full-ledger funding window
(`SNAPSHOT_WINDOW_DOES_NOT_COVER_LEDGER`). No DB was mutated, no official report
was overwritten, `/srv/qnty/repo` and the shadow lane are byte-for-byte
unchanged, and shadow DB / official report hashes match before and after.
`EDGE_UNPROVEN` and `BLOCK_LIVE_INTEGRATION` remain.
