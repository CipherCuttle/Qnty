# QNTY VM Shadow Verifier Tmp Run Receipt — 2026-07-07

## Status Boundary

- `EDGE_UNPROVEN` remains.
- `BLOCK_LIVE_INTEGRATION` remains.
- Full-ledger `CAVEATED_ENGINE_SEMANTICS` remains. The in-place run resolved
  the PR #89 funding-source *path-availability* artifact, but the full-ledger
  and batch clean-carry decisions are still `CAVEATED_ENGINE_SEMANTICS`
  (`refused_digest_mismatch`). Even where a sub-field reads
  `CLEAN_NET_OF_CARRY`, this receipt does **not** prove edge.
- This receipt is evidence-quality only.
- This receipt does not prove edge, profitability, statistical significance,
  shorting readiness, live readiness, or production deployment.
- This receipt does not mutate prod/shadow DBs.
- This receipt does not backfill historical rows.
- This receipt does not overwrite official reports.
- This receipt does not run writer/trader/live code.
- This receipt does not promote `/tmp` verifier output to an official report.

## Scope

- Date: 2026-07-07.
- PR #90 merge SHA: `8bda4f76323f11843f1b539e30e11a613c01515a`.
- Local repo head: `8bda4f76323f11843f1b539e30e11a613c01515a`.
- Branch: `docs/vm-shadow-verifier-tmp-run-receipt`.
- Output doc path: `docs/status/vm_shadow_verifier_tmp_run_receipt_2026-07-07.md`.
- VM repo path: `/srv/qnty/repo`.
  - Observed VM repo head: `2bd88430fe6b2881aaa2b32947002217d3e02ba5` (**stale**,
    lacks current clean-carry verifier semantics — as predicted by the plan).
  - Observed VM repo status: `## main...origin/main` (clean, not dirty).
- Chosen code source: **Option 2** — current local verifier code copied to a
  temporary VM `/tmp` directory (VM repo intentionally not updated).
- Temp code path on VM:
  `/tmp/qnty-verifier-run-8bda4f76323f11843f1b539e30e11a613c01515a`
  (extracted, used, then removed after evidence capture).
- Shadow DB path: `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db`.
- Official shadow report path:
  `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_verify_report.json`.
- Prod DB accessed: **No**. `PROD_DB_NOT_ACCESSED_BY_THIS_RECEIPT`.
- Verifier output written only to `/tmp`: **Yes**.

## Method

- **Stage A — VM read-only preflight.** Collected VM repo head/status, shadow
  DB stat + sha256, pre-existing `-wal`/`-shm` sidecar stat + sha256, official
  report stat + sha256 + verified-through (`watermark_bar_ts`), funding source
  snapshot directory listing, and confirmed available Python. All commands
  read-only; no DB opened in write mode.
- **Stage B — code-source choice.** The VM repo is stale (`2bd88430`) and has
  no `.venv`, so Option 1 (run from VM repo) would reproduce old semantics.
  Option 3 (copy DB off-host) is exactly what produced the PR #89
  path-unavailable artifact. Chose **Option 2**: `git archive HEAD` of current
  local code (tracked files only; no `.git`, `.venv`, caches, or output DBs),
  `scp` to VM, extracted under `/tmp/qnty-verifier-run-<sha>`. The verifier and
  its full transitive `quantbot` import graph use **only Python stdlib** (no
  third-party deps), so system `/usr/bin/python3` (3.12.3) with
  `PYTHONPATH=/tmp/qnty-verifier-run-<sha>` runs it without installing anything.
  Confirmed `--help` from the `/tmp` code source before running.
- **Stage C — verifier command.** Ran the read-only CLI against the true shadow
  DB path with `--read-only --json --data-dir /srv/qnty/repo/data`, redirecting
  stdout to a `/tmp` JSON file and stderr to a `/tmp` err file. No strict flag
  used, so the JSON is captured regardless of caveat.
- **Stage D — integrity checks.** Re-stat + re-hash shadow DB, official report,
  and `-wal`/`-shm`; compared before/after; scanned the shadow output dir for
  new files; re-checked VM repo head/status; checked for recently modified
  files under `/srv/qnty/repo`; checked for writer/trader processes.
- Read-only SQLite method: verifier opens the DB via
  `file:<abs>?mode=ro&immutable=1` with `PRAGMA query_only=ON`
  (`sqlite_open_mode = file_uri_mode_ro_immutable`, `query_only = 1`).
- Before/after hash method: `sha256sum` + `stat -c '%n size=%s mtime=%Y'`.
- No writes to `/srv/qnty/output`: confirmed (no new files; hashes unchanged).
- No writes to `/srv/qnty/repo`: confirmed (head unchanged; no recent files).
- No official report overwrite: confirmed (report hash/mtime/size unchanged).
- No DB mutation: confirmed (shadow DB hash/mtime/size unchanged).

## VM Preflight Evidence

- VM repo head: `2bd88430fe6b2881aaa2b32947002217d3e02ba5`.
- VM repo status: `## main...origin/main` (clean).
- Shadow DB before:
  - size: `172032`
  - mtime (epoch): `1783312420` (`2026-07-06 04:33:40 UTC`)
  - sha256: `3cbc6e9c63c74072aa019d6a53b1f5519f369f95cec1f9c21495e307c739a897`
- Pre-existing sidecars before (not created by this run):
  - `paper_ledger.db-wal`: size `0`, mtime `1783358530`,
    sha256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
    (empty-file digest)
  - `paper_ledger.db-shm`: size `32768`, mtime `1783363030`,
    sha256 `fd4c9fda9cd3f9ae7c962b0ddf37232294d55580e1aa165aa06129b8549389eb`
- Shadow watermark (verifier + resum): `2026-07-05T16:00:00`.
- Shadow batches count: `17`; equity rows: `34`; funding resum rows: `59`.
- Official report path:
  `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_verify_report.json`.
- Official report before:
  - size: `3531`
  - mtime (epoch): `1782929757` (`2026-07-01 18:15:57 UTC`)
  - sha256: `653605a76fdd0b8117c8373c9dadd3fcd41bed147778920c82f29f19f14e0ffd`
- Existing official report verified-through (`watermark_bar_ts`):
  `2026-07-01T08:00:00` (stale vs. current shadow watermark
  `2026-07-05T16:00:00`; consistent with PR #89). Existing report
  `status = OK`, `funding_coverage_verdict = CAVEATED_ENGINE_SEMANTICS`.
- Verifier help confirmation from chosen `/tmp` code source: `--help` exit 0;
  confirmed `--db-path`, `--read-only`, `--json`, `--data-dir`,
  `--strict-clean-carry` (diagnostic exit-code only), `--no-wal-checkpoint`
  (no-op). Help text states the CLI never writes the DB, never runs
  schema-ensure/migration/writer code, and never creates `-wal`/`-shm` or
  `paper_verify_report.json`/receipt/log sidecars.

## Verifier Run

- Exact command (VM):

  ```bash
  cd /tmp/qnty-verifier-run-8bda4f76323f11843f1b539e30e11a613c01515a
  PYTHONPATH=/tmp/qnty-verifier-run-8bda4f76323f11843f1b539e30e11a613c01515a \
    /usr/bin/python3 -m quantbot.paper.sqlite_verify \
    --db-path /srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db \
    --read-only \
    --json \
    --data-dir /srv/qnty/repo/data \
    > /tmp/shadow_verify_fresh_20260707T010858Z.json \
    2> /tmp/shadow_verify_fresh_20260707T010858Z.err
  ```

- cwd: `/tmp/qnty-verifier-run-8bda4f76323f11843f1b539e30e11a613c01515a`.
- Python executable: `/usr/bin/python3` (Python 3.12.3).
- `PYTHONPATH`: `/tmp/qnty-verifier-run-8bda4f76323f11843f1b539e30e11a613c01515a`.
- Exit code: `0`.
- stdout JSON path: `/tmp/shadow_verify_fresh_20260707T010858Z.json`.
- stderr path: `/tmp/shadow_verify_fresh_20260707T010858Z.err`.
- stdout JSON size: `15064`;
  sha256: `7fc9dab64b15ecb380c1d571e8f254d47eb98c6229b1b2b5a8acbccff88a3da0`.
- stderr size: `0` (empty; empty-file
  sha256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`).
- Output retained/deleted: `/tmp` JSON + err **retained** as temporary,
  non-official evidence (explicitly not an official report).
- Temporary code copy retained/deleted: **deleted** after evidence capture
  (`/tmp/qnty-verifier-run-<sha>` and the transfer tarball removed).

## Fresh VM In-Place Verifier Evidence

Actual values from `/tmp/shadow_verify_fresh_20260707T010858Z.json`:

- Top-level verifier `status`: `OK`.
- `failure_count`: `0`; `failures`: `null`.
- Watermark / verified-through (`watermark_bar_ts`): `2026-07-05T16:00:00`.
- Batches count: `17`; equity rows: `34`.
- Clean-carry keys present: **Yes** — `funding_clean_carry`,
  `funding_clean_carry_decision`, `funding_clean_carry_status`,
  `funding_clean_carry_reason_codes`, `funding_clean_carry_batch`,
  `funding_clean_carry_batch_decision`, `funding_clean_carry_batch_status`,
  `funding_clean_carry_batch_reason_codes` all present.
- Full-ledger clean-carry decision: `CAVEATED_ENGINE_SEMANTICS`.
- Full-ledger clean-carry status: `refused_digest_mismatch`.
- Full-ledger clean-carry reason codes:
  `["funding_source_file_digest_mismatch", "funding_source_snapshot_window_mismatch"]`.
- Batch clean-carry decision: `CAVEATED_ENGINE_SEMANTICS`.
- Batch clean-carry status: `refused_digest_mismatch`.
- Batch clean-carry reason codes: `["funding_source_file_digest_mismatch"]`.
- `db_mutation_performed`: `false`.
- `sqlite_open_mode`: `file_uri_mode_ro_immutable`.
- `wal_shm_files_created`: `false`.
- `read_only`: `true`; `query_only`: `1`; `query_only_pragma_enabled`: `true`.
- `verifier_cli_contract_version`: `1.0.0`.
- `source_path_unavailable` appears: **No** (absent — the JSON does not contain
  the string `source_path_unavailable`).
- Top-level `CORRUPT` appears: **No** (the JSON does not contain `CORRUPT`).
- Funding-source path resolution (the PR #89 artifact):
  - `source_path_required`: `true`; `source_path_available`: `true`.
  - `source_path_resolution_mode`: `explicit_data_dir`.
  - `resolved_funding_source_dir`: `/srv/qnty/repo/data`.
  - `funding_source_snapshot_status`: `present_valid`.
  - `funding_source_coverage_verdict`: `CLEAN_NET_OF_CARRY`.
- Arithmetic / funding resum (from `funding_clean_carry`):
  - `arithmetic_ok`: `true`; `arithmetic_status`: `OK`.
  - `funding_coverage_decision`: `complete`.
  - resum `status`: `ok`; `funding_rows`: `59`; `funding_amount_sum`:
    `3.44000686`; `ledger_state_funding_cum`: `3.4400068507041306`;
    `latest_equity_funding_cum`: `3.44000685`; `tolerance_abs`: `1e-06`;
    resum `reason_codes`: `[]`.
  - `snapshot_status`: `present_valid`;
    `snapshot_sha256`: `7f14e2afc38d260c6da6b2cabc9c6f683474ec6e6599219c03e0190f0ff84fad`;
    `source_bundle_sha256`: `1c5b433eb3adc345bdf024f20b45ffba874e77090ab5fc652f81fe169791451b`.
- Caveat/refusal reason: even though the funding source snapshot now resolves
  in-place (`present_valid`, path available) and arithmetic/coverage/resum are
  clean, clean-carry is still refused because of a **digest mismatch** between
  the committed funding-source snapshot and the live source files
  (`funding_source_file_digest_mismatch`) plus a snapshot **window** mismatch
  (`funding_source_snapshot_window_mismatch`). The clean label requires one
  committed, DB-linked, digest-valid snapshot plus an independent re-sum; the
  digest/window mismatch preserves `CAVEATED_ENGINE_SEMANTICS`. This is a
  *different, deeper* diagnosis than PR #89's copy-location path-unavailability
  artifact, which is now eliminated.

Verdict for this section: `VM_SHADOW_VERIFIER_TMP_OUTPUT_RECORDED_CAVEATED`.

## Post-Run Integrity

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
- Pre-existing `-wal`/`-shm`: unchanged (both hashes and mtimes equal
  before/after); `wal_shm_files_created = false`.
- `/srv/qnty/output` (shadow lane) unchanged: **confirmed** — the shadow lane
  directory listing is byte-for-byte the same set of files before and after; no
  new files created.
  - Note: a 15-minute `find` under `/srv/qnty/output` reported one modified
    file, `/srv/qnty/output/paper_pnl_v1/paper_ledger.db-shm` — the **prod**
    lane's shm. This is independent background VM activity on the prod lane; it
    was **not** touched by this receipt (this run only opened the shadow DB
    path, read-only). `PROD_DB_NOT_ACCESSED_BY_THIS_RECEIPT`.
- `/srv/qnty/repo` unchanged: **confirmed** — head still
  `2bd88430fe6b2881aaa2b32947002217d3e02ba5`, status clean, no files modified
  under the repo (excluding `.git`) in the run window.
- No writer/trader/live process ran: **confirmed** (`ps` scan found none).
- Verdict: `VM_SHADOW_DB_AND_REPORT_READ_ONLY_CONFIRMED`.

## Impact On Existing Receipts

- PR #89 copy-based fresh verifier receipt
  (`docs/status/shadow_verifier_fresh_receipt_2026-07-07.md`) remains valid: it
  correctly captured clean-carry keys and correctly disclosed the
  copy-location path artifact.
- This receipt **resolves** the PR #89 absolute-path artifact: run in-place on
  the VM with `--data-dir /srv/qnty/repo/data`, the funding-source snapshot now
  resolves (`source_path_available = true`, `funding_source_snapshot_status =
  present_valid`, `resolved_funding_source_dir = /srv/qnty/repo/data`), and
  `source_path_unavailable` / `CORRUPT` no longer appear. It also **further
  diagnoses** the remaining caveat: with the path resolved, the residual reason
  for `CAVEATED_ENGINE_SEMANTICS` is a funding-source digest/window mismatch,
  not path unavailability.
- PR #85 stale shadow verifier diagnosis remains historically valid.
- This does not retroactively change any official report (the official shadow
  report is byte-for-byte unchanged and still reads
  `watermark_bar_ts = 2026-07-01T08:00:00`).
- This does not backfill DB rows.
- This does not prove edge.

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

`VM_SHADOW_VERIFIER_TMP_RUN_RECEIPT_RECORDED_CAVEATED`

The scoped VM in-place read-only verifier run completed (exit 0), wrote output
only to `/tmp`, mutated no DB, overwrote no official report, and left
`/srv/qnty/repo` and `/srv/qnty/output` (shadow lane) unchanged. It resolved
the PR #89 funding-source path-availability artifact but preserved full-ledger
and batch `CAVEATED_ENGINE_SEMANTICS` (`refused_digest_mismatch`).
`EDGE_UNPROVEN` and `BLOCK_LIVE_INTEGRATION` remain.
