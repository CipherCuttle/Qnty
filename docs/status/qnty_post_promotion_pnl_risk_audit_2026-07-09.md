# QNTY Post-Promotion PnL & Risk Audit (read-only)

**Task:** `QNTY_POST_PROMOTION_PNL_RISK_AUDIT_GIT_OWNED`
**Date (UTC):** 2026-07-09
**Verdict:** `QNTY_POST_PROMOTION_PNL_RISK_AUDIT_RECORDED`
**Strategy label:** `EDGE_UNPROVEN` (unchanged) · `BLOCK_LIVE_INTEGRATION` (unchanged)

Read-only post-promotion audit across the QNTY prod and null-shadow paper lanes,
run after the PR #116 clean bundle-mode shadow official-report promotion
(`073aeaf43c16f4c741262cf5eb487f16aee1a6ca`). No writer/trader/live/backfill ran.
All equity/PnL figures are **paper diagnostics only** and constitute no
profitability or edge claim.

---

## PLAN

1. Git prep: fetch, confirm PR #116 merge commit on `origin/main`, branch off it.
2. VM read-only prep (SSH, `mode=ro`, `PRAGMA query_only=ON`).
3. Artifact inventory (DBs, official reports, snapshots/bundles/backups) with sha256.
4. Report freshness (report vs DB latest batch/watermark) per lane.
5. PnL / exposure / risk summary per lane (schema discovered first).
6. Prod vs shadow comparison.
7. Optional read-only verifier rerun — **skipped** (rationale below).
8. `2x / Shorting Readiness — NOT APPROVED` section.
9. Docs-only receipt (this file).

---

## CHANGESET

Single added file (docs-only):

- `docs/status/qnty_post_promotion_pnl_risk_audit_2026-07-09.md`

No code, no config, no VM artifact, no report, no DB, no CSV, no bundle,
no service/timer changed.

---

## VERIFY

### Environment / identity

| Item | Value |
|---|---|
| VM | `viktor@37.27.216.174` (`ubuntu-4gb-hel1-1-qnty`), uid 1000 |
| VM time at audit | `2026-07-09T08:27:36Z` |
| VM repo HEAD (`/srv/qnty/repo`, untouched) | `2bd88430fe6b2881aaa2b32947002217d3e02ba5` |
| Local branch | `docs/qnty-post-promotion-pnl-risk-audit` |
| Local HEAD / base | `073aeaf43c16f4c741262cf5eb487f16aee1a6ca` (PR #116 merge) |
| `origin/main` contains PR #116 merge | yes |

**SQLite access note:** used `file:<db>?mode=ro` + `PRAGMA query_only=ON` rather than
`immutable=1`. The prod lane DB is **live-written** (active `-wal`/`-shm`; `qnty-paper-pnl.timer`
committed batch 56 at 08:20:35Z today). `immutable=1` asserts the file never changes and can
return inconsistent reads against a live WAL; `mode=ro` is equally non-mutating but honors
locking/WAL. Reads were taken inside the safe window (next prod writer ~16:00Z).

### Process / service scan

- No `writer`/`trader`/`live`/`backfill`/`accounting` process running at audit time.
- Active timers (unchanged, read-only listing): `qnty-paper-pnl` (last 08:20:34Z, next 16:21Z),
  `qnty-data-refresh` (last 08:05Z, next 16:05Z), `qnty-shadow-run` (last 08:10Z — shadow DB
  unchanged since Jul 7 15:20, i.e. no-commit gate), `qnty-watermark-watchdog`,
  `qnty-healthcheck`, `qnty-health-receipt`, `qnty-daily-summary`. **None mutated.**

### Artifact inventory (sha256, read-only)

**Prod lane — `/srv/qnty/output/paper_pnl_v1`**

| Artifact | Size | mtime (UTC) | sha256 |
|---|---|---|---|
| `paper_ledger.db` | 245760 | 2026-07-09 08:20:40 | `4b947febc8373ca065f9fdd5b8705dd311a1e2feba73e71cb714e6e73e432773` |
| `paper_verify_report.json` | 58289 | 2026-07-09 08:20:40 | `5bd406d6f4b2f8fa8c71d5f91c9e2865e997bcf917ddb9e359fecc7df9071d00` |
| `funding_source_snapshots/` | — | — | 18 snapshot sidecars (latest `aded2f13…` Jul 9 08:20) |
| `funding_source_bundles/` | — | — | absent |
| `backups/` | — | — | absent |

**Shadow lane — `/srv/qnty/output/paper_pnl_null_shadow_v0`**

| Artifact | Size | mtime (UTC) | sha256 |
|---|---|---|---|
| `paper_ledger.db` | 172032 | 2026-07-07 15:20:43 | `00a4817e1d49aef51398fe0022cc2f3754302bc12f445912d4eb0d0596fc21ce` |
| `paper_verify_report.json` | 20900 | 2026-07-08 23:31:48 | `9985842ac4488c4109c5d5f4652096c01fcaa9f2d7b2716ec5e464af2c739e91` |
| `funding_source_snapshots/` | — | — | 4 sidecars (latest `8b9d8040…` Jul 7 15:19) |
| `funding_source_bundles/` | — | — | 1 bundle `funding_source_bundle_v1_37f6fb59…json` (content sha `aaa12ea0ab368cd3f34a6c30fcf37c56213cd3e1bd29751e042a7a0dbeb8414b`) |
| `backups/` | — | — | 1 pre-promotion report backup (see below) |

Source CSVs under `/srv/qnty/repo/data` (10 symbols × ohlcv+funding) were refreshed
today 08:05–08:07Z by `qnty-data-refresh` — **context only, not mutated by this audit.**

### Report freshness (report vs DB latest committed row)

**Prod (`paper_pnl_v1`) — LIVE, default source mode**

| Field | Report | DB latest |
|---|---|---|
| latest batch id | 56 | 56 |
| watermark | `2026-07-09T00:00:00` | `2026-07-09T00:00:00` |
| committed_at | verified_at `2026-07-09T08:20:40Z` | `2026-07-09T08:20:35Z` |
| batch git_sha | `2bd88430…` | `2bd88430…` |
| status / trusted / failure_count | `OK` / `True` / `0` | — |
| source_path_resolution_mode | `unavailable` | — |
| funding_clean_carry_decision | `CAVEATED_ENGINE_SEMANTICS` | — |
| clean_carry status | `refused_db_or_lane_mismatch` | — |
| clean_carry reason codes | `funding_source_snapshot_window_mismatch`, `source_path_unavailable` | — |

→ **Report matches DB (fresh).** Prod remains `CAVEATED_ENGINE_SEMANTICS` under default
source resolution (`source_path_available=False`) — the known engine-semantics caveat,
**not** a failure (`status=OK`, `failure_count=0`).

**Shadow (`paper_pnl_null_shadow_v0`) — bundle-mode promoted report**

| Field | Report | DB latest |
|---|---|---|
| latest batch id | 17 | 17 |
| watermark | `2026-07-05T16:00:00` | `2026-07-05T16:00:00` |
| committed_at | — | `2026-07-06T04:33:09Z` |
| batch git_sha | `2bd88430…` | `2bd88430…` |
| failure_count | `0` | — |
| source_path_resolution_mode | `snapshot_provenance` | — |
| funding_clean_carry_decision | `CLEAN_NET_OF_CARRY` | — |
| batch clean_carry decision | `CLEAN_NET_OF_CARRY` | — |
| clean_carry reason codes | `[]` | — |
| bundle linkage | `clean_mode_gate=db_linked_ledger_batches_reference`, `source_bundle_sha256=8b9d8040…`, `target_batch_id=17`, `batch_identity_matches=True`, `coverage_decision=complete` | — |

→ **Report matches DB batch 17 / watermark 2026-07-05T16:00:00 (fresh).**
Exposes bundle-linked clean-carry gate. **Confirmed NOT the old batch-11 report.**

**Promotion provenance (backup of replaced report):**
`backups/paper_verify_report_20260708T232217Z_653605a7…json` = the pre-promotion report:
`batches=11`, `watermark=2026-07-01T08:00:00`, `funding_clean_carry_decision=None` (unset),
`source_path_resolution_mode=None`. PR #116 atomically replaced this stale batch-11 report
with the fresh batch-17 bundle-mode CLEAN report.

### PnL / exposure / risk summary

Shared config (both lanes): `initial_equity=10000.0`, `notional=1000.0`,
**`leverage=1.0`**, `fee_bps=5.0`, `funding_applied_as=cash_flow`,
baseline `fixed_notional_active_symbols_paper_v1`.

**Prod (`paper_pnl_v1`) @ batch 56 / bar 2026-07-09T00:00:00**

| Metric | Value |
|---|---|
| equity (NAV) | `10150.70` |
| realized_gross | `0.5168` |
| unrealized_pnl | `165.4423` |
| funding_cum (carry) | `5.2548` |
| fees_cum | `10.0003` |
| peak_equity | `10336.66` |
| current drawdown / max | `0.0180` / `0.0257` |
| closed trades (n / net) | `8` / `-8.9318` (all long) |
| fills (entry/exit) | `20` (12 BUY / 8 SELL) |
| open positions | `4` long — BTC, ETH, XRP, BNB |
| long / short / gross notional | `4000.00` / `0.00` / `4000.00` |
| symbols traded | BNB, BTC, ETH, SOL, XRP |
| funding rows / unavailable | `118` / `0` |
| short exposure / leverage>1 | **none** / **no** |

**Shadow (`paper_pnl_null_shadow_v0`) @ batch 17 / bar 2026-07-05T16:00:00**

| Metric | Value |
|---|---|
| equity (NAV) | `10350.81` |
| realized_gross | `-25.4031` |
| unrealized_pnl | `385.1382` |
| funding_cum (carry) | `3.4400` |
| fees_cum | `5.4873` |
| peak_equity | `10350.81` |
| current drawdown / max | `0.0` / `0.0063` |
| closed trades (n / net) | `3` / `-28.5804` (all long) |
| fills (entry/exit) | `11` (8 BUY / 3 SELL) |
| open positions | `5` long — SOL, BTC, ETH, XRP, BNB |
| long / short / gross notional | `5000.00` / `0.00` / `5000.00` |
| symbols traded | BNB, BTC, ETH, SOL, XRP |
| funding rows / unavailable | `59` / `0` |
| short exposure / leverage>1 | **none** / **no** |

Absent in schema for both lanes (stated, not guessed): no margin/liquidation columns,
no short/borrow columns, no explicit leverage>1 path. `drawdown` is present and reported.

### Prod vs shadow comparison

| Dimension | Prod `paper_pnl_v1` | Shadow `paper_pnl_null_shadow_v0` |
|---|---|---|
| latest batch / watermark | 56 / `2026-07-09T00:00:00` | 17 / `2026-07-05T16:00:00` |
| report freshness | fresh (matches DB) | fresh (matches DB, post-#116) |
| report status | `OK`, trusted, 0 failures | `failure_count=0` |
| source resolution mode | `unavailable` (default) | `snapshot_provenance` (bundle-linked) |
| clean-carry decision | `CAVEATED_ENGINE_SEMANTICS` | `CLEAN_NET_OF_CARRY` |
| clean-carry reasons | window_mismatch, source_path_unavailable | `[]` |
| equity (NAV) | `10150.70` | `10350.81` |
| realized_gross | `0.5168` | `-25.4031` |
| unrealized_pnl | `165.4423` | `385.1382` |
| funding_cum | `5.2548` | `3.4400` |
| fees_cum | `10.0003` | `5.4873` |
| max drawdown | `0.0257` | `0.0063` |
| closed trades / net | 8 / `-8.9318` | 3 / `-28.5804` |
| open positions | 4 long | 5 long |
| gross notional | `4000.00` | `5000.00` |
| short exposure | none | none |
| leverage field today | `1.0` | `1.0` |

**Comparability caveat:** the two lanes are **not directly PnL-comparable**. They have
different forward start (prod `2026-06-20T16:00`, shadow `2026-06-24T16:00`) and are at
different watermarks (prod ~3.3 days ahead). The shadow lane is a manually-advanced
null-shadow research lane, not a mirror of prod. Figures are paper diagnostics only.

### Official shadow report freshness after PR #116 — confirmed

- Now: batch 17, watermark `2026-07-05T16:00:00`, `CLEAN_NET_OF_CARRY`, bundle-linked
  (`source_bundle_sha256=8b9d8040…`, `batch_identity_matches=True`, reason_codes `[]`).
- Was (backup): batch 11, watermark `2026-07-01T08:00:00`, clean_carry unset.
- Real shadow DB unchanged since Jul 7 15:20 (sha `00a4817e…`).
- `CLEAN_NET_OF_CARRY` here is scoped strictly to: **lane** `paper_pnl_null_shadow_v0`,
  **report** `paper_verify_report.json`, **gate** full + batch clean-carry,
  **source_mode** bundle/`snapshot_provenance`, **batch 17**. It does **not** extend to
  the prod lane, which remains `CAVEATED_ENGINE_SEMANTICS`.

### Optional read-only verifier rerun — SKIPPED

Step 7 is optional and was **not run**. Rationale: (a) both official reports are already
fresh verifier outputs (prod verified 08:20:40Z; shadow is the #116-promoted bundle report);
(b) the prod DB is live-written with an active WAL, so a rerun during the live window adds
risk without new signal; (c) a scratch-worktree rerun would require the editable-install
meta-path workaround. No verifier code executed; no `/tmp` outputs produced.

---

## 2x / Shorting Readiness — NOT APPROVED

- **Does current code/report prove live-readiness?** **No.** `EDGE_UNPROVEN` and
  `BLOCK_LIVE_INTEGRATION` both remain. Reports are paper diagnostics; prod clean-carry is
  `CAVEATED_ENGINE_SEMANTICS`.
- **Does the paper ledger support short exposure?** **Not observed.** Both lanes: 100% long,
  `short_notional=0.00`, all trades qty>0, no short/borrow columns in schema.
- **Does the paper ledger support leverage/margin/liquidation?** **Not observed.**
  `leverage=1.0` in `paper_config`; no margin, liquidation, or maintenance columns exist.
- **Gates still needed before paper-only 2x/shorting:** explicit paper-only short/leverage
  design PR; risk model / margin / liquidation semantics; max-notional and max-leverage caps;
  position-sizing rules; funding/borrow/carry semantics for shorts; drawdown kill switch;
  tests for long/short/leverage PnL math; simulator receipts; no exchange keys.
- **Gates still needed before live:** many successful shadow receipts; risk limits;
  kill switch; reconciliation; latency/slippage checks; exchange sandbox or dry-run bridge;
  explicit human approval; separate live-integration PR; `BLOCK_LIVE_INTEGRATION` removed
  only by explicit future decision.

This audit does **not** recommend or enable real 2x leverage or real shorting.

---

## What was NOT touched

Real prod DB · real shadow DB · official reports (both lanes) · source CSVs ·
source snapshots · funding bundles · promotion backups · `/srv/qnty/repo` main worktree ·
systemd services/timers/cron · no writer/trader/live/backfill/data-refresh/deploy ·
no exchange keys · no report promotion · no source-freeze · no artifact cleanup.
All VM access was read-only (`mode=ro`, `query_only=ON`).

---

## VERDICT

`QNTY_POST_PROMOTION_PNL_RISK_AUDIT_RECORDED`
`EDGE_UNPROVEN` · `BLOCK_LIVE_INTEGRATION`

**Recommended next action:** No live action. Prod's `CAVEATED_ENGINE_SEMANTICS` is a
source-path-resolution caveat (default mode), not a failure — if a clean prod clean-carry
signal is wanted, the follow-up is to evaluate prod under bundle/snapshot-provenance source
mode (read-only), mirroring the shadow lane, in a separate docs-owned task. Shadow lane
remains cleanly promoted at batch 17; continue manual shadow catch-up cadence as authorized.
