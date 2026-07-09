# QNTY Prod Provenance Clean-Carry — Read-Only Evaluation

**Task:** `QNTY_PROD_PROVENANCE_CLEAN_CARRY_READONLY_EVALUATION_GIT_OWNED`
**Date (UTC):** 2026-07-09
**Verdict:** `QNTY_PROD_PROVENANCE_CLEAN_CARRY_READONLY_EVALUATION_RECORDED`
**Strategy label:** `EDGE_UNPROVEN` (unchanged) · `BLOCK_LIVE_INTEGRATION` (unchanged)

Read-only evaluation of whether the **prod** paper lane `paper_pnl_v1` can reach a
clean funding/carry signal (`CLEAN_NET_OF_CARRY`) under snapshot / bundle / provenance
source resolution, analogous to the shadow lane, **without mutating** the prod DB,
official prod report, source CSVs, snapshots, bundles, services, or writer state.

This is an **evaluation only.** It does **not** authorize prod report replacement,
bundle creation, source-freeze, writer runs, live trading, leverage, or shorting.
All figures/labels are paper diagnostics; no profitability or edge claim is made.

---

## PLAN

1. Git prep: fetch, confirm PR #117 merge on `origin/main`, branch off it.
2. VM read-only prep (SSH, `mode=ro`, `PRAGMA query_only=ON`; no `immutable=1` on live-WAL DB).
3. Prod artifact inventory (DB, report, snapshots, bundles, backups) with sha256/mtime/size + WAL state.
4. Prod DB latest committed batch + snapshot/bundle reference fields.
5. Prod official report parse (status, clean-carry decision/reasons, source-path resolution).
6. Snapshot provenance evaluation (sidecar identity, window, source digests, self-resolvability).
7. Bundle/provenance feasibility under current verifier code (read-only, no bundle creation).
8. Optional read-only verifier/probe — **skipped** (rationale below).
9. Decision matrix.
10. `2x / Shorting Readiness — STILL NOT APPROVED`.
11. Docs-only receipt (this file).

---

## CHANGESET

Single added file (docs-only):

- `docs/status/qnty_prod_provenance_clean_carry_readonly_evaluation_2026-07-09.md`

No code, no config, no VM artifact, no report, no DB, no CSV, no bundle,
no service/timer changed.

---

## VERIFY

### Environment / identity

| Item | Value |
|---|---|
| VM | `viktor@37.27.216.174` (`ubuntu-4gb-hel1-1-qnty`), uid 1000 |
| VM time at eval | `2026-07-09T08:38:33Z` |
| VM repo HEAD (`/srv/qnty/repo`, untouched) | `2bd88430fe6b2881aaa2b32947002217d3e02ba5` |
| Local branch | `docs/qnty-prod-provenance-clean-carry-readonly-evaluation` |
| Local HEAD / base = `origin/main` | `cd009a4b673cafbee1866cf0b11b6aa006871ee6` (PR #117 merge) |
| `origin/main` contains PR #117 merge | yes |

**Exact commands (read-only):**
```
git fetch origin
git checkout -b docs/qnty-prod-provenance-clean-carry-readonly-evaluation cd009a4b673cafbee1866cf0b11b6aa006871ee6
ssh -i ~/.ssh/hetzner_qnty_key -o IdentitiesOnly=yes viktor@37.27.216.174
# SQLite reads: sqlite3.connect("file:<db>?mode=ro", uri=True); PRAGMA query_only=ON
```

**SQLite access note:** used `file:<db>?mode=ro` + `PRAGMA query_only=ON`. Prod DB is
live-written by `qnty-paper-pnl.timer` (last commit 08:20:35Z; next run 16:21Z). The `-wal`
was checkpointed to **0 bytes** at read time. Reads taken inside the safe window (~08:38Z,
next prod writer ~16:21Z). `immutable=1` avoided (would risk inconsistent reads vs a live WAL).

### Process / service scan

- No `writer`/`trader`/`live`/`backfill`/`accounting`/`data-refresh` process running at eval time.
- Timers listed read-only (unchanged, none mutated): `qnty-paper-pnl` (last 08:20:34Z, next 16:21:08Z),
  `qnty-data-refresh` (last 08:05Z, next 16:05Z), `qnty-shadow-run` (last 08:10Z, next 16:10Z),
  `qnty-watermark-watchdog`, `qnty-healthcheck`, `qnty-health-receipt`, `qnty-daily-summary`.

### Prod artifact inventory (sha256, read-only) — `/srv/qnty/output/paper_pnl_v1`

| Artifact | Size | mtime (UTC) | sha256 |
|---|---|---|---|
| `paper_ledger.db` | 245760 | 2026-07-09 08:20:40 | `4b947febc8373ca065f9fdd5b8705dd311a1e2feba73e71cb714e6e73e432773` |
| `paper_ledger.db-wal` | **0** | 2026-07-09 08:20 | (checkpointed / empty) |
| `paper_ledger.db-shm` | 32768 | 2026-07-09 08:31 | — |
| `paper_verify_report.json` | 58289 | 2026-07-09 08:20:40 | `5bd406d6f4b2f8fa8c71d5f91c9e2865e997bcf917ddb9e359fecc7df9071d00` |
| `funding_source_snapshots/` | — | — | 18 sidecars (latest `aded2f13…`, file-byte sha `e1a3084733e594e1…`) |
| **`funding_source_bundles/`** | — | — | **ABSENT** |
| `backups/` | — | — | **absent** |
| `paper_ledger.db.before_snapshot_columns.*.bak` | 163840 ×2 | 2026-07-03 | pre-snapshot-column backups (context only) |

DB/report sha256 and mtime are **identical to the PR #117 audit** — prod lane unchanged
since batch 56. Live source CSVs are at `/srv/qnty/repo/data/` (10 symbols; **separate tree**
from the output lane; refreshed today 08:05Z; not mutated by this eval).

### Prod DB — latest committed batch (read-only)

| Field | Value |
|---|---|
| batch_id | `56` |
| committed_at | `2026-07-09T08:20:35Z` |
| git_sha | `2bd88430fe6b2881aaa2b32947002217d3e02ba5` |
| prior→new watermark | `2026-07-08T16:00:00` → `2026-07-09T00:00:00` |
| batch range (count/min/max) | `56` / `1` / `56` (watermarks `2026-06-20T16:00:00` … `2026-07-09T00:00:00`) |
| `funding_source_snapshot_write_state` | `committed` |
| `funding_source_snapshot_path` | `…/funding_source_snapshots/funding_source_snapshot_v1_aded2f13….json` |
| `funding_source_snapshot_sha256` (file-byte) | `e1a3084733e594e1833b93e72079ce621c133e12b0ef01563abeb011249a6315` |
| `funding_source_snapshot_bundle_sha256` (content-addr) | `aded2f1348f3a198372d9916e242df84fe76dd2cc5f504f6c0e7a6f24cc0b698` |
| `funding_source_snapshot_schema_version` | `FUNDING_SOURCE_SNAPSHOT_SCHEMA_V1` |

Snapshot columns are populated for the **latest 18 committed batches (39–56)**; batches 1–38
predate the snapshot columns (`NULL`). **Every committed batch's snapshot covers only its own
8h batch window** (e.g. batch 56 → `2026-07-08T16:00 → 2026-07-09T00:00`). **No snapshot covers
the full-ledger evaluation window.**

### Prod official report — freshness + clean-carry (read-only)

| Field | Value |
|---|---|
| status / trusted / failure_count | `OK` / `true` / `0` |
| latest batch / watermark | `56` / `2026-07-09T00:00:00` → **matches DB (fresh)** |
| `git_provenance.latest_batch_git_sha` | `2bd88430…` (0 unprovenanced batches) |
| `source_path_resolution_mode` | `unavailable` |
| `source_path_available` / `source_path_required` | `false` / `true` |
| `resolved_funding_source_dir` | `null` |
| `funding_source_snapshot_status` | `present_valid` (candidate_count 18, target `batch_identity_matches=true`) |
| `funding_clean_carry_decision` | `CAVEATED_ENGINE_SEMANTICS` |
| `funding_clean_carry_status` | `refused_db_or_lane_mismatch` |
| `funding_clean_carry_reason_codes` (full-ledger) | `["funding_source_snapshot_window_mismatch", "source_path_unavailable"]` |
| `funding_clean_carry_batch_decision` | `CAVEATED_ENGINE_SEMANTICS` |
| `funding_clean_carry_batch_status` | `refused_source_coverage_issue` |
| `funding_clean_carry_batch_reason_codes` | `["source_path_unavailable"]` |
| full-ledger evaluation window | `2026-06-21T00:00:00Z` → `2026-07-09T00:00:00Z` |
| batch-56 evaluation window | `2026-07-08T16:00:00Z` → `2026-07-09T00:00:00Z` |

→ **Report is fresh** (matches DB batch 56 / watermark). Prod remains
`CAVEATED_ENGINE_SEMANTICS` under **default (`live-current`) source mode** — a
source-path-resolution caveat, **not** a failure (`status=OK`, `failure_count=0`).

### Snapshot provenance evaluation (batch-56 sidecar `aded2f13…`)

Sidecar file-byte sha256 `e1a3084733e594e1…` **matches the DB `funding_source_snapshot_sha256`**
(DB↔sidecar byte link valid). Payload (`snapshot_payload`) findings:

- `schema_version = FUNDING_SOURCE_SNAPSHOT_SCHEMA_V1`, `write_state = committed`,
  `coverage_decision = complete`, `reason_codes = []`.
- `lane = {lane_id: paper_pnl_v1, output_dir: /srv/qnty/output/paper_pnl_v1}` — **prod lane, correct.**
- `snapshot_metadata`: `db_path_reference = /srv/qnty/output/paper_pnl_v1/paper_ledger.db`,
  `ledger_batch_id = 56`, `batch_identity_matches = true`, `evaluation_identity_matches = true`.
- `evaluation_window = {2026-07-08T16:00:00Z → 2026-07-09T00:00:00Z}` — **single-batch only.**
- `symbols_covered = [BNBUSDT, BTCUSDT, ETHUSDT, XRPUSDT]` (the 4 open longs; SOL closed).
- `source_files` + `provenance.entity_inputs` carry `full_file_sha256` / `canonical_row_subset_sha256`
  / `source_csv_sha256`, and `required_funding_windows` embed `accepted_source_row`
  (source_csv_row_index + source_row_sha256) — i.e. the snapshot **does embed source digests**.

**Self-resolvability of source path (why default mode is `unavailable`):** the verifier's
`_resolve_funding_source_dir` (`quantbot/paper/sqlite_verify.py:1479`) tries, in order:
(1) explicit `--data-dir` — not passed; (2) `snapshot_provenance` via
`provenance.source_path_resolution.resolved_funding_source_dir` **or** a single common
*absolute* parent of source paths — prod snapshot **has no `source_path_resolution` key**, and
all `source_files` / `entity_inputs.source_csv_path` are **relative** (`data/BNBUSDT_8h_funding.csv`),
so `_single_absolute_parent` returns `None`; (3) `<db.parent>/data` — **`/srv/qnty/output/paper_pnl_v1/data`
does not exist**. → falls through to `UNAVAILABLE`. This exactly reproduces the official
`source_path_resolution_mode=unavailable`, `source_path_unavailable`.

### Bundle / provenance feasibility (read-only, current verifier code `origin/main`)

Current verifier supports two source modes (`quantbot/paper/sqlite_verify.py:160-162`):
`SOURCE_MODE_LIVE_CURRENT = "live-current"` (default) and `SOURCE_MODE_BUNDLE = "bundle"`.

- **`bundle` mode:** `_bundle_source_digest_expectations` resolves from
  `<db.parent>/funding_source_bundles` (`sqlite_verify.py:2420`). **Prod has no
  `funding_source_bundles/` dir** → `resolve_funding_source_bundle` returns no payload →
  `refused_bundle`. **Not achievable read-only** without creating a prod bundle (**forbidden here**).
- **`snapshot_provenance` resolution:** cannot self-resolve prod source path (no
  `resolved_funding_source_dir`, relative paths — see above). **Not achievable from existing prod artifacts.**
- **`live-current` + explicit `--data-dir /srv/qnty/repo/data`:** would make the source path
  *available* (EXPLICIT_DATA_DIR mode) but reads **mutable, refreshed-today CSVs** — the exact
  drift-prone path the immutable bundle was designed to avoid; digest-match vs the committed
  snapshot is not guaranteed after a refresh. Even on success it clears only the **batch-56
  window** scope — **not** the full-ledger scope.
- **Full-ledger scope, independent of source path:** blocked structurally by
  `funding_source_snapshot_window_mismatch` — **no single committed prod snapshot covers
  `2026-06-21T00:00 → 2026-07-09T00:00`**; each covers one 8h batch. A covering artifact
  (full-window snapshot or an immutable full-window bundle, as the shadow lane has) **does not
  exist** in the prod lane.

**Exact blockers to a clean prod full-ledger signal (read-only, today):**
1. No prod `funding_source_bundles/` (bundle mode → `refused_bundle`).
2. No committed prod snapshot covering the full-ledger window (full-ledger → `snapshot_window_mismatch`).
3. Prod snapshots store **relative** source paths and no `resolved_funding_source_dir`, and the
   CSVs live in a separate `/srv/qnty/repo/data` tree → default `source_path_unavailable`.

**Conclusion:** prod `paper_pnl_v1` **cannot reach `CLEAN_NET_OF_CARRY` (full-ledger) read-only
from existing artifacts.** The exact missing artifact = an **immutable, content-addressed prod
funding-source bundle covering the full-ledger window**, bound to the committed snapshots
(analogous to the shadow lane's bundle). Creating it is **out of scope** for this evaluation.

### Optional read-only verifier / probe — SKIPPED

Step 8 was **not run**. Rationale: (a) the decisive facts are read **directly from artifacts**
(bundle dir absent; snapshot provenance lacks `resolved_funding_source_dir` + relative paths;
no snapshot covers the full-ledger window) — a code run adds no new signal; (b) running the
verifier **in-place** would write into the prod lane (**forbidden**); (c) running against a
**`/tmp` copy** is known to give a **false `CAVEATED`** — the committed snapshot stores an
*absolute* VM path that resolves outside a copied lane dir (see
`verifier-copied-db-breaks-snapshot-resolution` prior receipt); (d) running `live-current`
with explicit `--data-dir` reads mutable refreshed CSVs (drift-prone) and only ever touches
batch scope. No verifier code executed; no `/tmp` outputs produced; editable-install workaround
not needed.

---

## Decision matrix — possible next actions

| Option | Mutations required | Risk | Expected benefit | Live/trading readiness impact |
|---|---|---|---|---|
| **A. Do nothing** (recommended) | none | none | prod stays fresh; honest `CAVEATED_ENGINE_SEMANTICS` (default-mode source-resolution caveat, not a failure) preserved | none |
| **B. Build immutable prod full-window funding-source bundle** | writes `funding_source_bundles/` + bundle file into prod lane (artifact write) | writing into prod lane; must be immutable/content-addressed; needs a full-ledger-window source capture (per-batch snapshots don't cover it); requires separate explicit plan | could enable bundle-mode full-ledger clean eval like shadow | none (paper) — **out of scope here** |
| **C. Writer/verifier change: record absolute `resolved_funding_source_dir` + covering window in snapshot provenance** | code + tests; changes future writer output (not retroactive for batches 39–56) | code-change risk; needs review + tests; separate PR | future prod batches self-resolve source path → clears batch-scope `source_path_unavailable` | none (paper) — separate PR |
| **D. `live-current` probe with explicit `--data-dir /srv/qnty/repo/data`** | none if read-only + `/tmp` output, but reads mutable live CSVs | drift-prone; digest match not guaranteed post-refresh; batch-scope only; not promotable | minimal batch-scope diagnostic | none |
| **E. Replace prod official report** | overwrite official prod report | **forbidden here**; only valid after a separate explicit promotion plan **and** a bundle exists | none until B done | none |
| **F. Do not touch live/writer** (baseline) | none | none | preserves live/writer state | none |

**Recommended next action:** **A + F — no live action, no artifact mutation.** Prod's
`CAVEATED_ENGINE_SEMANTICS` is a source-path-resolution caveat under default (`live-current`)
mode, **not** a failure. To pursue a clean prod full-ledger carry signal analogous to the
shadow lane, the follow-up is a **separate docs-owned plan** that (1) builds an immutable,
content-addressed prod funding-source bundle covering the full-ledger window bound to the
committed snapshots, then (2) runs the verifier in `bundle` mode read-only, then (3) only after
review, a **separate** promotion plan — optionally alongside Option C so future prod batches
self-resolve their source path. **None of B/C/E is authorized by this evaluation.**

---

## 2x / Shorting Readiness — STILL NOT APPROVED

- This prod provenance evaluation **does not authorize** 2x leverage or shorting.
- Current audited lanes are **1x, long-only**: prod `paper_config` `leverage=1.0`; batch-56
  positions 100% long (BTC/ETH/XRP/BNB), `short_notional=0.00`; no margin/liquidation/short
  columns observed in schema.
- Short / leverage work remains a **separate paper-only design task** after any provenance
  cleanup, not enabled here.
- `EDGE_UNPROVEN` remains. `BLOCK_LIVE_INTEGRATION` remains.

---

## What was NOT touched

Real prod DB · official prod report · prod source snapshots · prod backups · source CSVs
(`/srv/qnty/repo/data`) · `/srv/qnty/repo` main worktree · systemd services/timers/cron ·
no writer/trader/live/backfill/data-refresh/deploy · no exchange keys · **no bundle created**
(prod `funding_source_bundles/` remains absent) · no report promotion · no source-freeze ·
no artifact cleanup · no verifier code executed. All VM access read-only (`mode=ro`,
`query_only=ON`); no `/tmp` outputs produced.

---

## VERDICT

`QNTY_PROD_PROVENANCE_CLEAN_CARRY_READONLY_EVALUATION_RECORDED`
`EDGE_UNPROVEN` · `BLOCK_LIVE_INTEGRATION`

**Finding:** Prod `paper_pnl_v1` **cannot reach `CLEAN_NET_OF_CARRY` (full-ledger) read-only
from existing artifacts.** Blockers: (1) no prod funding-source bundle (`bundle` mode →
`refused_bundle`); (2) no committed snapshot covers the full-ledger window (`snapshot_window_mismatch`);
(3) prod snapshots use relative source paths with no `resolved_funding_source_dir` and CSVs live
in a separate tree (`source_path_unavailable`). The exact missing artifact is an **immutable,
content-addressed prod full-window funding-source bundle** bound to the committed snapshots —
whose creation is **out of scope** here.

**Scope of any clean claim:** the only `CLEAN_NET_OF_CARRY` in the system remains strictly
scoped to **lane** `paper_pnl_null_shadow_v0`, **report** `paper_verify_report.json`, **gate**
full + batch clean-carry, **source_mode** bundle/`snapshot_provenance`, **batch 17**. It does
**not** extend to the prod lane, which remains `CAVEATED_ENGINE_SEMANTICS`.

**Recommended next action:** No live action (Options A + F). Prod's caveat is a default-mode
source-resolution caveat, not a failure. Pursue a clean prod signal only via a separate
docs-owned bundle-build + read-only bundle-mode eval + separate promotion plan.
