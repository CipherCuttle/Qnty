# QNTY Both-Lanes PnL Read-Only Audit — 2026-07-08

**Task:** `QNTY_BOTH_LANES_PNL_READONLY_AUDIT_GIT_OWNED`
**Type:** read-only audit (docs-only receipt). No mutation, no promotion, no writer run.
**Status boundary:** `EDGE_UNPROVEN` remains. `BLOCK_LIVE_INTEGRATION` remains. This
receipt makes no alpha / profitability / edge / live-readiness claim.

Every `CLEAN_NET_OF_CARRY` statement below is scoped to an exact
gate / lane / batch / source_mode / verifier commit and is **not** a lane-wide or
promotion verdict.

---

## PLAN

Audit PnL / official-report / verifier state, read-only, for both QNTY paper lanes:

1. prod/main paper lane — `/srv/qnty/output/paper_pnl_v1`
2. null shadow paper lane — `/srv/qnty/output/paper_pnl_null_shadow_v0`

Procedure: git prep → VM read-only artifact inventory + hashes → DB schema discovery →
per-lane PnL/current-state → official-report parse + staleness → optional read-only
verifier (live-current both lanes; bundle mode for shadow) with output confined to
`/tmp` → this receipt → docs-only PR.

Guardrails honored: no real/prod DB mutation, no official-report overwrite, no source-CSV
mutation, no systemd/timer/cron mutation, no writer/trader/live/backfill/data-refresh run,
no deploy, no report promotion, no source-freeze, no cleanup of real artifacts,
`/srv/qnty/repo` main worktree not modified.

---

## Environment & git state

- **VM identity:** `viktor@37.27.216.174` — host `ubuntu-4gb-hel1-1-qnty`; audit clock
  `2026-07-08T21:03Z`.
- **VM repo `/srv/qnty/repo` HEAD (read-only, not modified/pulled):**
  `2bd88430fe6b2881aaa2b32947002217d3e02ba5` (`feat: add batch-scoped clean-carry
  verifier (#77)`). This pinned code **lacks** `SOURCE_MODE_BUNDLE`; bundle-mode
  verification therefore used origin/main code (below), never the VM repo.
- **Local audit branch:** `docs/qnty-both-lanes-pnl-readonly-audit`, cut from
  `origin/main`.
- **origin/main HEAD:** `b28ce804adcd22322cfa52e722c738a520ec08d6`
  (`docs: record bundle-mode official report promotion blocker (#111)`).
- **PR #111 merge commit** `b28ce804adcd22322cfa52e722c738a520ec08d6` confirmed an
  ancestor of `origin/main` (`git merge-base --is-ancestor` → true).
- **Verifier code used for optional runs:** origin/main `quantbot/` rsynced to a VM
  `/tmp` scratch; `quantbot/paper/sqlite_verify.py` sha256
  `7863327dd5a3800e861bcf2b04964a4a65f77aeee3bf9c07d5449ef1eb4ce910` (identical local
  ↔ VM scratch). Ran under `/srv/qnty/venv` (numpy 2.4.4, pandas 3.0.2) with the
  `__editable__` meta-path finder dropped and the scratch prepended so
  `quantbot.__file__` resolved to the scratch, not `/srv/qnty/repo`.
- **Scratch (self-owned, ephemeral, /tmp only):**
  `/tmp/qnty_both_lanes_pnl_readonly_audit_20260708T210836Z`.

---

## CHANGESET

Single tracked file added:

- `docs/status/qnty_both_lanes_pnl_readonly_audit_2026-07-08.md` (this receipt).

No other tracked change. No code/test/dependency change. No VM `/srv` write. No GitHub
state mutation beyond opening a docs-only PR.

---

## Artifact inventory & hashes (read-only)

All SQLite access via `file:<db>?mode=ro&immutable=1` + `PRAGMA query_only=ON`
(`PRAGMA quick_check` → `ok` for both DBs).

### Prod lane — `/srv/qnty/output/paper_pnl_v1`

| Artifact | Size | mtime (UTC) | sha256 |
|---|---|---|---|
| `paper_ledger.db` | 237568 | 2026-07-08T16:21:19Z | `b5ad4da01b5a73ba2c8a33cd2635cc89b3e7b450fda5b936433b4a1c3a04a02c` |
| `paper_verify_report.json` | 53019 | 2026-07-08T16:21:19Z | `f35159ad7053069ae83b13002161a00c0fb9bfc015e891d73a4cd8750c74d26a` |

- `funding_source_snapshots/`: 16 sidecars; latest
  `funding_source_snapshot_v1_3b1b11b8…json` (mtime 2026-07-08T16:21Z).
- `funding_source_bundles/`: **absent** (no bundle for prod lane).

### Shadow lane — `/srv/qnty/output/paper_pnl_null_shadow_v0`

| Artifact | Size | mtime (UTC) | sha256 |
|---|---|---|---|
| `paper_ledger.db` | 172032 | 2026-07-07T15:20:43Z | `00a4817e1d49aef51398fe0022cc2f3754302bc12f445912d4eb0d0596fc21ce` |
| `paper_verify_report.json` | 3531 | 2026-07-01T18:15:57Z | `653605a76fdd0b8117c8373c9dadd3fcd41bed147778920c82f29f19f14e0ffd` |

- `funding_source_snapshots/`: 4 sidecars; latest
  `funding_source_snapshot_v1_8b9d8040…json` (mtime 2026-07-07T15:19Z).
- `funding_source_bundles/`: 1 bundle — `funding_source_bundle_v1_37f6fb59…json`
  (38949 bytes, mtime 2026-07-08T20:44Z) — the real-lane immutable bundle referenced in
  the task brief.

### Process / timer scan (read-only)

- No `writer|trader|live|backfill|paper_pnl|sqlite_writer` process running at audit time.
- systemd timers present and scheduled (not modified): next `qnty-shadow-run`
  2026-07-09T00:11Z, next `qnty-paper-pnl` 2026-07-09T00:21Z, plus healthcheck /
  watermark-watchdog / data-refresh / health-receipt / daily-summary.
- Source CSVs in `/srv/qnty/repo/data` were refreshed 2026-07-08T16:05–16:07Z (10 symbols
  × funding+ohlcv) — this post-snapshot refresh is the origin of the live-current digest
  drift seen below. Funding-CSV sha256 digests were recorded for context (read-only).

---

## Lane-by-lane PnL / current-state (read-only)

Schema is identical across lanes (13 tables); shadow adds `lane_id` / `strategy_id` /
`config_hash_v2` / `pre_registration_hash` columns. Common config both lanes:
`initial_equity_usd=10000`, `notional_usd=1000`, `leverage=1.0`, `fee_bps=5.0`,
`baseline=fixed_notional_active_symbols_paper_v1`, `paper_engine_version=0.3.0`,
`db_schema_version=1`.

### Prod (`paper_pnl_v1`)

- **Latest committed batch:** `54`, `committed_at=2026-07-08T16:21:11Z`,
  `git_sha=2bd88430…`, `committed_bar_count=1`, watermark `…07-08T00:00 → 07-08T08:00`.
- **`ledger_state`:** watermark `2026-07-08T08:00:00`, `realized_gross=+0.5168`,
  `fees_cum=10.0003`, `funding_cum=+4.9100`, `peak_equity=10336.66`,
  `updated_at=2026-07-08T16:21:11Z`.
- **Latest `equity_snapshots`** (bar `2026-07-08T08:00`): `equity=10070.59`,
  `realized_gross_pnl=-36.6156`, `unrealized_pnl=+121.5996`, `funding_cum=+4.9100`,
  `fees_cum=9.4817`, `drawdown=0.0257`, `num_open=5`.
- **Trades** (n=8): Σgross `+0.5168`, Σfees `8.0003`, Σfunding `+1.4483`, Σnet `-8.9318`.
- **Open positions** (`open_positions` table, n=4): BNBUSDT, BTCUSDT, ETHUSDT, XRPUSDT.
  (Latest equity snapshot records `num_open=5`; the `open_positions` table holds 4 rows —
  minor internal state divergence, flagged in the discrepancy table.)
- **Latest-batch funding snapshot fields:** path
  `…/funding_source_snapshots/…3b1b11b8…json`, `snapshot_sha256=c47784d4…`,
  `bundle_sha256=3b1b11b8…`, schema `FUNDING_SOURCE_SNAPSHOT_SCHEMA_V1`,
  `write_state=committed`.

### Shadow (`paper_pnl_null_shadow_v0`, `strategy_id=matched_null_shadow_v0`)

- **Latest committed batch:** `17`, `committed_at=2026-07-06T04:33:09Z`,
  `git_sha=2bd88430…`, `committed_bar_count=7`, watermark `…07-03T08:00 → 07-05T16:00`.
- **`ledger_state`:** watermark `2026-07-05T16:00:00`, `realized_gross=-25.4031`,
  `fees_cum=5.4873`, `funding_cum=+3.4400`, `peak_equity=10350.81`,
  `updated_at=2026-07-06T04:33:09Z`.
- **Latest `equity_snapshots`** (bar `2026-07-05T16:00`): `equity=10350.81`,
  `realized_gross_pnl=-25.4031`, `unrealized_pnl=+385.1382`, `funding_cum=+3.4400`,
  `fees_cum=5.4873`, `drawdown=0.0`, `num_open=5`.
- **Trades** (n=3): Σgross `-25.4031`, Σfees `2.9873`, Σfunding `+0.1900`, Σnet `-28.5804`.
- **Open positions** (n=5): BNBUSDT, BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT.
- **Latest-batch funding snapshot fields:** path
  `…/funding_source_snapshots/…8b9d8040…json`, `snapshot_sha256=7c5068af…`,
  `bundle_sha256=8b9d8040…`, schema `FUNDING_SOURCE_SNAPSHOT_SCHEMA_V1`,
  `write_state=committed`.

> Per-symbol unrealized (`position_snapshot_symbols.unrealized_gross`) is not summarized;
> prior diagnosis (`docs/status/`) established it is stored `0.0` per row while ledger-level
> `equity_snapshots.unrealized_pnl` is nonzero — unchanged here, not re-litigated.

---

## Official report summary (read-only parse)

### Prod official report — CURRENT

- `status=OK`, `trusted=true`, `failure_count=0`, `schema_version=1`.
- `watermark_bar_ts=2026-07-08T08:00:00` = DB `ledger_state` watermark;
  `git_provenance.latest_batch_id=54` = DB latest batch. **Not stale.**
- `content_sha256=b972d2b4ade743d4afa6569099d2912e5ade4fcaeb34c14ac725cdbfc62b8aae`.
- Full-ledger `funding_clean_carry_decision=CAVEATED_ENGINE_SEMANTICS`,
  `…_status=refused_db_or_lane_mismatch`; batch-scoped
  `funding_clean_carry_batch_decision=CAVEATED_ENGINE_SEMANTICS`,
  `…_batch_status=refused_db_or_lane_mismatch`, `target_batch_id=54`.
- New-format report (includes `funding_clean_carry*` and `funding_source_snapshot`
  sections).

### Shadow official report — STALE + OLD FORMAT

- `status=OK`, `trusted=true`, `failure_count=0`, `schema_version=1`.
- `watermark_bar_ts=2026-07-01T08:00:00`; `git_provenance.latest_batch_id=11`.
  DB is at **batch 17 / watermark 2026-07-05T16:00:00** → report **lags DB by 6 batches
  and ~4.3 days of watermark**. **Stale.**
- `content_sha256=8cd3d920112b6f0b668a4d8ddcafb47e235a030e014bec11fc353f3c1dfe724c`.
- **Old format:** no `funding_clean_carry*` fields and no `funding_source_snapshot`
  section — predates the PR #77 clean-carry verifier. Carries **no** clean-carry evidence.
- Consistent with the task brief: the official shadow report was **not** replaced and
  remains old (mtime 2026-07-01T18:15Z).

---

## Optional read-only verifier (in-place, output confined to /tmp)

Verifier: origin/main `b28ce80` (`sqlite_verify.py` sha `7863327d…`). DBs opened
read-only in place; the strict CLI (`verify_database_readonly_cli`) uses
`mode=ro&immutable=1` and by contract "never creates -wal/-shm sidecars or
paper_verify_report.json/receipt/log"; `verify_database(..., source_mode="bundle")`
"Never writes anything." All emitted JSON written **only** under the `/tmp` scratch
(`out_inplace/`). No publish/write/report-replacement function was called.

| Run | Lane · batch | source_mode | full `funding_clean_carry` | batch-scoped stamp | out sha256 |
|---|---|---|---|---|---|
| prod_live_current | prod · 54 | live-current | `CAVEATED_ENGINE_SEMANTICS` / `refused_db_or_lane_mismatch` · `[funding_source_snapshot_window_mismatch]` | `CAVEATED_ENGINE_SEMANTICS` / `refused_db_or_lane_mismatch` · `[funding_source_batch_window_mismatch]` | `bee71f49…0ae3f0` |
| shadow_live_current | shadow · 17 | live-current | `CAVEATED_ENGINE_SEMANTICS` / `refused_digest_mismatch` · `[funding_source_file_digest_mismatch]` | `CAVEATED_ENGINE_SEMANTICS` / `refused_digest_mismatch` · `[batch_window_mismatch, file_digest_mismatch]` | `7e0b248f…8ea2ad` |
| shadow_bundle | shadow · 17 | bundle | **`CLEAN_NET_OF_CARRY`** / `clean_net_of_carry` · reasons `[]` | `CAVEATED_ENGINE_SEMANTICS` / `refused_digest_mismatch` · `[batch_window_mismatch, file_digest_mismatch]` | `0432889…1efcf83` |

All three runs: top-level `status=OK`, `failure_count=0`, `funding_source_snapshot.status
= present_valid`.

**Scoped clean-carry statement.** For the **shadow lane, ledger batch 17**, run with
**`source_mode="bundle"`** under origin/main verifier `b28ce80`, the **full-ledger
`funding_clean_carry` gate** returned **`CLEAN_NET_OF_CARRY`** (and
`funding_coverage_verdict=CLEAN_NET_OF_CARRY`). In the **same run**, the **batch-scoped
additive clean-carry stamp** returned **`CAVEATED_ENGINE_SEMANTICS` /
`refused_digest_mismatch`** (`funding_source_file_digest_mismatch` +
`funding_source_batch_window_mismatch`) — the batch stamp resolves funding source
live-current, so the post-snapshot CSV refresh trips it. This reproduces the exact PR #111
promotion blocker and is **not** a lane-wide or official CLEAN verdict.

> **Negative-control note.** A first pass run against DB **copies** relocated under `/tmp`
> reported `funding_source_snapshot_path_outside_snapshot_dir` / `refused_missing_snapshot`
> — an artifact of moving the DB away from the absolute snapshot path recorded in its
> batch rows, not a true verdict. The in-place run above (real absolute paths, read-only)
> is the faithful result; the copy pass was discarded.

---

## Discrepancy table

| # | Comparison | Finding |
|---|---|---|
| 1 | Prod DB vs prod official report | **Consistent / current** — report watermark & latest_batch_id (54) match DB. |
| 2 | Shadow DB vs shadow official report | **Stale** — report at batch 11 / wm 2026-07-01T08:00 vs DB batch 17 / wm 2026-07-05T16:00; report is old-format (no clean-carry fields). |
| 3 | Prod vs shadow official report | Prod = new-format, current, clean-carry present (CAVEATED). Shadow = old-format, stale, no clean-carry evidence. |
| 4 | Shadow live-current vs bundle (full gate) | live-current `CAVEATED` (`file_digest_mismatch`) → bundle **`CLEAN_NET_OF_CARRY`**. Bundle resolves the pinned immutable source; live-current trips on the post-snapshot CSV refresh. |
| 5 | Shadow bundle: full gate vs batch stamp | Full gate `CLEAN_NET_OF_CARRY`; batch-scoped stamp remains `CAVEATED` (`refused_digest_mismatch`) — the batch stamp is still live-current. **This is the promotion blocker.** |
| 6 | Prod internal: `ledger_state.realized_gross` (+0.5168, = Σtrade gross) vs `equity_snapshots.realized_gross_pnl` (−36.6156) at same watermark | Divergent definitions of "realized"; recorded, not resolved here (audit only). |
| 7 | Prod internal: latest `equity_snapshots.num_open=5` vs `open_positions` table rows=4 | Minor open-position count divergence; recorded, not resolved. |

---

## What was NOT touched

- No real/prod/shadow DB mutated (post-run sha256 of both DBs identical to pre-run:
  prod `b5ad4da0…`, shadow `00a4817e…`).
- No official report overwritten (post-run sha256 identical: prod `f35159ad…`, shadow
  `653605a7…`; shadow report mtime still 2026-07-01T18:15Z).
- No source CSV mutated; no funding snapshot/bundle written or recommitted.
- No systemd/timer/cron mutation; no writer/trader/live/backfill/data-refresh run; no
  deploy; no report promotion; no source-freeze; no cleanup of real artifacts.
- `/srv/qnty/repo` main worktree not modified, not pulled, not checked out.
- All verifier output confined to VM `/tmp` scratch; nothing written under `/srv/qnty/output`.

---

## VERIFY

- Local `git diff --check` clean; `git diff --name-only origin/main...HEAD` =
  `docs/status/qnty_both_lanes_pnl_readonly_audit_2026-07-08.md` only.
- `PRAGMA quick_check` → `ok` for both DBs; all reads `query_only=ON`.
- `/srv` immutability re-confirmed after the verifier runs (four sha256 unchanged).
- Verifier code identity confirmed by sha256 parity (local ↔ VM scratch) and
  `quantbot.__file__` under the scratch, not `/srv/qnty/repo`.

## VERDICT

`QNTY_BOTH_LANES_PNL_READONLY_AUDIT_RECORDED`

Read-only audit complete for both lanes. Prod official report is current and consistent
with its DB (clean-carry `CAVEATED_ENGINE_SEMANTICS`). The shadow official report is stale
and old-format. Bundle-mode verification reproduces, for **shadow batch 17**, a full-ledger
`funding_clean_carry` = `CLEAN_NET_OF_CARRY` while the **batch-scoped stamp stays
`CAVEATED_ENGINE_SEMANTICS` / `refused_digest_mismatch`** — the unchanged PR #111
promotion blocker. `EDGE_UNPROVEN` and `BLOCK_LIVE_INTEGRATION` remain.

### Recommended next action

The blocker is the batch-scoped additive clean-carry stamp resolving funding source
**live-current** (so the post-snapshot CSV refresh yields `file_digest_mismatch`). A
future, separately-scoped and separately-approved change would teach the **batch-scoped**
stamp to resolve against the pinned immutable **bundle** (as the full-ledger gate already
does), prove it with tests + `/tmp` receipts, and only then consider republishing the
shadow official report. No DB-touching or report-promotion action should be taken from this
audit. Independently, refreshing the shadow official report to the current DB
(batch 17 / new-format) is desirable but is a **publish** operation and out of scope here.
