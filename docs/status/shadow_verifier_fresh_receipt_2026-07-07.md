# QNTY Shadow Verifier Fresh Receipt — 2026-07-07

## Status Boundary

- `EDGE_UNPROVEN` remains. Nothing in this receipt claims, implies, or is
  designed to manufacture an edge claim for any lane or variant.
- `BLOCK_LIVE_INTEGRATION` remains. No live exchange integration, no live
  capital, no live-readiness implication.
- Full-ledger `CAVEATED_ENGINE_SEMANTICS` remains. The fresh verifier pass
  recorded here returns `funding_clean_carry_decision = CAVEATED_ENGINE_SEMANTICS`
  for both the full-ledger and batch gates, so the label is preserved, not
  changed. Even a `CLEAN_NET_OF_CARRY` result would not prove edge.
- **This receipt is evidence-quality only.** It records read-only fresh
  verifier output for the current shadow ledger and compares it to the stale
  shadow verifier report diagnosed in PR #85.
- This receipt does **not** prove edge, profitability, statistical
  significance, shorting readiness, live readiness, or production deployment.
- This receipt does **not** mutate prod/shadow DBs.
- This receipt does **not** backfill historical rows.
- This receipt does **not** run writer/trader/live code.

---

## Scope

- **Date:** 2026-07-07.
- **Local repo head:** `250653a3a9cc4d7341a1f598fdc5f89405d3e575` (`main`
  fast-forwarded to `origin/main` after PR #88 merged; this receipt branch cut
  from it).
- **PR #88 merge SHA / `main` head inspected:**
  `250653a3a9cc4d7341a1f598fdc5f89405d3e575` (PR #88 confirmed `MERGED`;
  `main` contains `docs/status/position_symbol_unrealized_writer_receipt_2026-07-07.md`).
- **Branch name:** `docs/shadow-verifier-fresh-receipt`.
- **Exact output doc path:** `docs/status/shadow_verifier_fresh_receipt_2026-07-07.md`.
- **Shadow DB path:** `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db`.
- **Prod DB inspected:** No. Only the prod `paper_verify_report.json` artifact
  was read read-only (see Impact / prod comparison). The prod ledger DB file was
  not opened.
- **VM repo inspected:** Yes, read-only. VM repo head
  (`/srv/qnty/repo`) = `2bd88430fe6b2881aaa2b32947002217d3e02ba5` — stale
  (predates PR #86/#87/#88). **Not modified, not pulled, not updated.**
- **Verifier run from:** local **current** code at `main` head `250653a`, not
  VM code. The VM lacks `sqlite3` and its repo is stale, so the current
  clean-carry verifier semantics only exist locally.
- **Verifier output written only to `/tmp`:** Yes. The read-only CLI emits its
  JSON report to stdout only (it writes no `paper_verify_report.json`, receipt,
  log, or `-wal`/`-shm` sidecars); stdout was redirected to a file under the
  session `/tmp` scratchpad.

---

## Method

- **Read-only VM commands used.** Over SSH (`ssh -i ~/.ssh/hetzner_qnty_key -o
  IdentitiesOnly=yes viktor@37.27.216.174`): `git -C /srv/qnty/repo rev-parse
  HEAD`, `stat -c "%n size=%s mtime=%Y"`, `sha256sum`, `ls -la`, and read-only
  `python3 json.load` of the existing shadow and prod `paper_verify_report.json`
  artifacts. No writes were issued to the VM.
- **DB copy method.** The shadow ledger was copied to the local `/tmp`
  scratchpad with `scp` (read-only pull). The lane's
  `funding_source_snapshots/*.json` files were also copied so the mirrored copy
  reproduced the on-VM lane directory layout. The copied `paper_ledger.db`
  sha256 equals the source (`3cbc6e9c…`), confirming a faithful copy.
- **Verifier command used.**
  `.venv/bin/python -m quantbot.paper.sqlite_verify --db-path <tmp-copy> --read-only --json`.
  This CLI opens the DB via `file:<abs>?mode=ro&immutable=1` with
  `PRAGMA query_only=ON`, reuses the same structural / arithmetic / funding
  clean-carry gate as the publisher, and prints exactly one JSON report to
  stdout. It never writes the DB, never runs schema-ensure/migration/writer
  code, and never creates report/receipt/log or `-wal`/`-shm` files.
- **Read-only SQLite method.** DB watermark queries were issued locally against
  the `/tmp` copy via `sqlite3.connect("file:<abs>?mode=ro…", uri=True)` +
  `PRAGMA query_only=ON`, using only `SELECT`/`MAX`/`COUNT`. No
  `INSERT`/`UPDATE`/`DELETE`.
- **Before/after hash method.** `stat -c "%n size=%s mtime=%Y"` + `sha256sum`
  were run on the live VM shadow DB immediately before the first read and again
  after the last read, then compared for byte identity.
- **Temporary files created and whether deleted.** Under the session `/tmp`
  scratchpad: `shadow_ledger_copy.db` (+ transient `-wal`/`-shm` sidecars from
  the first non-immutable read-only watermark query, on the copy only),
  `shadow_existing_report.json`, `fresh_shadow_report.json`,
  `fresh_shadow_report_v2.json`, and a `lane_copy/…` mirror with the DB copy and
  `funding_source_snapshots/`. All live only under `/tmp` and are disposable; no
  copy or output was written into the repo or the VM output tree.
- **No writes to `/srv/qnty/output`.** Confirmed — only `scp` reads and
  read-only shell/SQLite/`json.load`.
- **No writes to `/srv/qnty/repo`.** Confirmed — VM repo inspected with
  `rev-parse` only; not pulled or modified.

---

## Source Integrity

**Shadow DB — `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db`**

| | size (bytes) | mtime (epoch) | sha256 |
|---|---|---|---|
| before | 172032 | 1783312420 | `3cbc6e9c63c74072aa019d6a53b1f5519f369f95cec1f9c21495e307c739a897` |
| after  | 172032 | 1783312420 | `3cbc6e9c63c74072aa019d6a53b1f5519f369f95cec1f9c21495e307c739a897` |

Byte-identical before and after all reads (size, mtime, sha256 unchanged). The
hash also equals the shadow hash recorded in PR #85's diagnosis — the shadow
ledger has not advanced since that diagnosis, so this receipt reads the same
bytes.

**Verdict: `SHADOW_DB_READ_ONLY_CONFIRMED`.**

**Prod DB:** `PROD_DB_NOT_ACCESSED_BY_THIS_RECEIPT`. The prod ledger DB file was
not opened. Only the prod `paper_verify_report.json` artifact was read read-only
for the optional freshness comparison below.

---

## Existing Shadow Report Staleness

- **Existing report path:**
  `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_verify_report.json`
- **Existing report mtime:** `1782929757` (epoch); report `verified_at` =
  `2026-07-01T18:15:57Z`.
- **Existing report size:** 3531 bytes.
- **Existing report verified-through timestamp (`watermark_bar_ts`):**
  `2026-07-01T08:00:00`.
- **Current shadow DB watermark (`equity_snapshots` max `bar_ts`):**
  `2026-07-05T16:00:00` (34 equity rows; latest `ledger_batches.batch_id` = 17).
- **Staleness gap:** `2026-07-01T08:00:00` → `2026-07-05T16:00:00`
  = **4 days 8 hours**.
- **Clean-carry field presence:** **absent.** The stale report has 27 keys and
  **zero** `funding_clean_carry_*` keys; its funding label lives only in the
  older `funding_coverage_verdict = CAVEATED_ENGINE_SEMANTICS` /
  `funding_coverage_diagnostic_label =
  missing_funding_treated_as_zero_like_current_engine_not_net_of_carry_clean`
  fields. It predates the PR #77 clean-carry verifier fields and the current
  shadow DB watermark.

**Verdict: `EXISTING_SHADOW_REPORT_STALE_CONFIRMED`.**

---

## Fresh Shadow Verifier Evidence

- **Verifier command:**
  `.venv/bin/python -m quantbot.paper.sqlite_verify --db-path
  <tmp>/lane_copy/paper_pnl_null_shadow_v0/paper_ledger.db --read-only --json`.
- **Verifier output path under `/tmp`:**
  `…/scratchpad/fresh_shadow_report_v2.json` (stdout redirect; an earlier
  snapshot-dir-absent run was saved to `…/scratchpad/fresh_shadow_report.json`).
- **DB copy path used:**
  `…/scratchpad/lane_copy/paper_pnl_null_shadow_v0/paper_ledger.db`
  (sha256 `3cbc6e9c…`, equal to the live shadow DB), with the lane's
  `funding_source_snapshots/*.json` mirrored beside it.
- **Verifier verdict/status:** `status = CORRUPT`, `exit_code = 4`,
  `failures = ["source_path_unavailable"]`. **This top-level status is a copy-
  location artifact, not a ledger-integrity finding** (see interpretation
  below): the DB's committed funding-source-snapshot reference is an absolute VM
  path (`/srv/qnty/output/paper_pnl_null_shadow_v0/funding_source_snapshots/…`)
  that cannot resolve from any `/tmp` copy location, so the source-path check
  fails closed. The independent arithmetic re-sum check passed
  (`resum_check.status = ok`).
- **Verified-through timestamp / `watermark_bar_ts`:** `2026-07-05T16:00:00`.
- **Shadow DB watermark:** `2026-07-05T16:00:00` (matches — fresh output is at
  the current watermark, closing the 4d8h staleness gap as evidence).
- **Latest batch id:** 17 (`funding_clean_carry_batch.target_batch_id = 17`).
- **Full-ledger clean-carry decision/status/reason codes:**
  - `funding_clean_carry_decision = CAVEATED_ENGINE_SEMANTICS`
  - `funding_clean_carry_status = refused_missing_snapshot`
  - `funding_clean_carry_reason_codes = [funding_source_snapshot_missing,
    funding_source_snapshot_path_outside_snapshot_dir, source_path_unavailable]`
- **Batch clean-carry decision/status/reason codes:**
  - `funding_clean_carry_batch_decision = CAVEATED_ENGINE_SEMANTICS`
  - `funding_clean_carry_batch_status = refused_source_coverage_issue`
  - `funding_clean_carry_batch_reason_codes =
    [funding_source_snapshot_path_outside_snapshot_dir, source_path_unavailable]`
- **Clean-carry key presence:** **present.** The fresh output contains all 8
  `funding_clean_carry_*` keys (`funding_clean_carry`,
  `funding_clean_carry_batch`, `funding_clean_carry_batch_decision`,
  `funding_clean_carry_batch_reason_codes`, `funding_clean_carry_batch_status`,
  `funding_clean_carry_decision`, `funding_clean_carry_reason_codes`,
  `funding_clean_carry_status`) that were entirely absent from the stale report.
- **Any refusal/mismatch/caveat reason:** the clean-carry gate refuses to award
  `CLEAN_NET_OF_CARRY` because the DB-linked committed snapshot cannot be read
  from the copy location. The DB reference itself is intact and committed on the
  VM: `funding_source_snapshot_write_state = committed`, path
  `…/funding_source_snapshot_v1_1c5b433eb3adc345bdf024f20b45ffba874e77090ab5fc652f81fe169791451b.json`,
  `created_at = 2026-07-06T04:33:09Z`. The arithmetic re-sum is internally
  consistent: `funding_rows = 59`, `funding_amount_sum ≈ 3.44000686`,
  `ledger_state_funding_cum ≈ 3.44000685`, `latest_equity_funding_cum ≈
  3.44000685`, `tolerance_abs = 1e-06`, `status = ok`.
- **Does fresh output now contain the clean-carry fields missing from the stale
  report?** **Yes.** The field-absence debt from PR #85 is resolved as
  *evidence*: the current verifier populates the full clean-carry field set for
  the current shadow watermark, and both the full-ledger and batch gates decide
  `CAVEATED_ENGINE_SEMANTICS`.

**Important limitation.** Because the shadow DB stores the committed snapshot's
*absolute* VM path, current verifier semantics can only fully resolve that
snapshot when run at the true lane path on the VM. Running against a `/tmp` copy
therefore always adds `source_path_unavailable` /
`funding_source_snapshot_path_outside_snapshot_dir` and a fail-closed `CORRUPT`
top-level status. This receipt records the copy-based fresh output honestly and
does **not** claim `CLEAN_NET_OF_CARRY`; obtaining a fully-resolved
official shadow report would require running current code at the true lane path
on the VM, which is out of scope here (no `/srv/qnty/repo` update, no in-place
report overwrite). The decision that matters for the status boundary —
`CAVEATED_ENGINE_SEMANTICS` — is preserved regardless, and matches prod's fresh
`funding_clean_carry_decision` (below).

**Verdict: `FRESH_SHADOW_VERIFIER_OUTPUT_RECORDED`.**

---

## Impact On Existing Receipts

- **PR #82** manual realized attribution snapshot (2026-07-06) remains valid.
- **PR #84** reporter parity receipt remains valid.
- **PR #85** stale-shadow diagnosis remains valid — this receipt confirms it:
  the shadow report is stale (verified-through `2026-07-01T08:00:00` vs
  watermark `2026-07-05T16:00:00`) and carries zero clean-carry keys, exactly as
  diagnosed.
- **PR #88** post-fix per-symbol unrealized writer receipt remains valid.
- This receipt only addresses the **stale shadow verifier evidence** gap. It
  records fresh clean-carry field presence and decision as evidence; it does
  **not** retroactively change the old shadow report artifact, which still lives
  unchanged on the VM at
  `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_verify_report.json`.
- **Optional prod comparison (read-only, prod report artifact only).** The prod
  `paper_verify_report.json` is fresh: `verified_at = 2026-07-06T16:20:46Z`,
  `watermark_bar_ts = 2026-07-06T08:00:00`, `status = OK`, 8 clean-carry keys
  present, and `funding_clean_carry_decision = CAVEATED_ENGINE_SEMANTICS`. So
  even a fully-resolved fresh report (prod's) carries `CAVEATED_ENGINE_SEMANTICS`
  — confirming that the shadow copy's `CAVEATED_ENGINE_SEMANTICS` decision is the
  expected label, not an artifact, and that the artifact is confined to the
  copy-only `source_path_unavailable` reason codes.
- This receipt does **not** prove edge.

---

## Non-Goals

- no code change
- no test change
- no schema change
- no verifier code change
- no reporter change
- no writer change
- no trader change
- no strategy change
- no DB writes except the temporary `/tmp` copy/output used for the read-only
  verifier pass
- no prod/shadow writer run
- no deployment
- no backfill
- no live integration
- no shorting
- no trial registry change
- no null/benchmark lane change

---

## Verdict

`SHADOW_VERIFIER_FRESH_RECEIPT_RECORDED`

- Existing shadow report: `EXISTING_SHADOW_REPORT_STALE_CONFIRMED`.
- Fresh shadow verifier output: `FRESH_SHADOW_VERIFIER_OUTPUT_RECORDED`
  (clean-carry fields now present; full-ledger and batch decisions
  `CAVEATED_ENGINE_SEMANTICS`; top-level `CORRUPT` is a copy-location
  `source_path_unavailable` artifact, not a ledger-integrity finding).
- Source integrity: `SHADOW_DB_READ_ONLY_CONFIRMED`;
  `PROD_DB_NOT_ACCESSED_BY_THIS_RECEIPT`.
- `EDGE_UNPROVEN`, `BLOCK_LIVE_INTEGRATION`, and full-ledger
  `CAVEATED_ENGINE_SEMANTICS` all preserved.
