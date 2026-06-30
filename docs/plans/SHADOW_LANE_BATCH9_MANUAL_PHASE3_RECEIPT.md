# Shadow Lane Batch9 Manual One-Bar — Phase 3 Receipt

**Verdict:** `SHADOW_BATCH9_ONE_BAR_COMMITTED_RECEIPT_READY_FOR_PR`
**Strategy label:** `EDGE_UNPROVEN`
**Funding verdict:** `CAVEATED_ENGINE_SEMANTICS` (NOT `CLEAN_NET_OF_CARRY`)

---

## 1. Authorization Context

This is a **separate explicit authorization** (`AUTHORIZE_SHADOW_BATCH9_ONE_BAR_WRITER_ONCE`)
that followed the read-only batch9 readiness gate. It advanced the shadow lane by
**exactly one 8h bar** against the existing shadow lane database. The run:

- reused the existing shadow DB (no recreate / reset / migration),
- executed **exactly one** shadow writer invocation (the only authorized attempt),
- read forward observations from a **frozen `/tmp` snapshot** of `forward_obs_v1`,
- did **not** mutate the production DB,
- did **not** mutate the live forward observer directory,
- touched **no** systemd timers / services,
- placed **no** live trades and used **no** exchange keys.

Strategy remains `EDGE_UNPROVEN`. All equity / PnL figures are **paper
diagnostics only** and constitute no profitability or edge claim.

---

## 2. Readiness Gate Result

The preceding read-only gate returned:

```txt
VERDICT: SHADOW_BATCH9_READY_FOR_SEPARATE_AUTHORIZATION
```

Gate facts carried into this authorization:

| Field                          | Value                  |
| ------------------------------ | ---------------------- |
| Shadow watermark (pre)         | `2026-06-30T00:00:00`  |
| forward_obs latest             | `2026-06-30T08:00:00`  |
| Prod watermark (situational)   | `2026-06-30T08:00:00`  |
| Gap                            | one 8h bar             |
| Expected bars to add           | 1                      |
| Unauthorized batch9            | none                   |
| Integrity / verifier / lane / mutation checks | all passed |

---

## 3. Preflight & Command Shape

**Local main SHA:** `34720dca65fdc21f5ac92f44b40979810c7876e2`
(HEAD == origin/main; only untracked `.claude/`).
**VM repo SHA:** `fde43a511ef98d7292a6bd93dd9e198ea92f79fe`.
**VM venv Python:** `/srv/qnty/venv/bin/python`.
**Timer window:** clear — VM `2026-06-30T17:41Z`; all writer services
(`qnty-shadow-run`, `qnty-paper-pnl`, `qnty-data-refresh`) inactive; next runs
Wed `2026-07-01 00:05–00:20Z` (~6h+ away).

**Safety snapshots before** (md5 / size / mtime):

| Target                | md5         | size     | mtime (UTC)            |
| --------------------- | ----------- | -------- | ---------------------- |
| prod DB               | `922b2785…` | `139264` | `2026-06-30T16:20:36Z` |
| shadow DB             | `fb74b6d5…` | `110592` | `2026-06-30T09:28:36Z` |
| live forward_obs (per-file fingerprint) | 9 files, matched gate | — | — |

**Frozen forward_obs snapshot path:**
`/tmp/qnty_shadow_batch9_manual_run_v0/forward_obs_v1_frozen`
— copied from `/srv/qnty/output/forward_obs_v1`, 9 files byte-identical to live,
`observation_log.json` 500 rows, latest bar `2026-06-30T08:00:00` (confirmed exact match).

**Shadow lane config:**
`/srv/qnty/output/paper_pnl_null_shadow_v0/paper_config.json` present
(`forward_start_ts=2026-06-24T16:00:00`, `config_hash=32c0fbcc…`, matches DB).

**Required env var:** `QNTY_PAPER_OUTPUT_DIR=/srv/qnty/output/paper_pnl_null_shadow_v0`
(required: without it the writer resolves `paper_config.json` from the production
dir and aborts with `CONFIG_ERROR`; the four CLI flags do not select the lane).

**Exact writer command shape (one invocation, run from `/srv/qnty/repo`):**

```bash
QNTY_PAPER_OUTPUT_DIR=/srv/qnty/output/paper_pnl_null_shadow_v0 \
/srv/qnty/venv/bin/python scripts/qnty-paper-sqlite-accounting.py \
  --db-path /srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db \
  --forward-obs-dir /tmp/qnty_shadow_batch9_manual_run_v0/forward_obs_v1_frozen \
  --data-dir /srv/qnty/repo/data \
  --json
```

Verifier run read-only with `--no-emit --json`. DB inspection over a read-only
SQLite connection (`mode=ro`).

---

## 4. Writer Result

- **Exit code:** `0`
- **stdout:** `{"status_code": 0, "status_message": "Committed batch 9: 1 bars, 4 events"}`
- No rerun performed (single invocation only).

---

## 5. Verifier Result (after writer)

- **Exit code:** `0` — **Status:** `OK` — **failure_count:** `0`
- **Batches:** `9`
- **Watermark:** `2026-06-30T08:00:00`
- **Funding verdict:** `CAVEATED_ENGINE_SEMANTICS` (preserved)
- **Funding diagnostic label:**
  `missing_funding_treated_as_zero_like_current_engine_not_net_of_carry_clean`
- Missing window still: `SOLUSDT|2026-06-27T08:00:00|exit` (known caveat;
  7 funding rows, 7 required intervals, 0 rate_available_zero).
- git provenance: latest batch git_sha
  `fde43a511ef98d7292a6bd93dd9e198ea92f79fe`, no unprovenanced batches.

---

## 6. DB Inspection (after writer, read-only)

- **paper_config.lane_id:** `paper_pnl_null_shadow_v0`
  (`strategy_id=matched_null_shadow_v0`, `strategy_version=0.0.0-shadow`)
- **Batch count after:** `9`; **batch_id=9 occurs exactly once**; max batch_id `9`.
- **integrity_check:** `ok`; single distinct `lane_id`.
- No batch with watermark `> 2026-06-30T08:00:00`.

| batch | prior watermark        | new watermark          | committed_bars | events |
| ----- | ---------------------- | ---------------------- | -------------- | ------ |
| 1     | `null`                 | `2026-06-25T08:00:00`  | 3              | 13     |
| 2     | `2026-06-25T08:00:00`  | `2026-06-26T00:00:00`  | 2              | 7      |
| 3     | `2026-06-26T00:00:00`  | `2026-06-26T08:00:00`  | 1              | 3      |
| 4     | `2026-06-26T08:00:00`  | `2026-06-27T00:00:00`  | 2              | 8      |
| 5     | `2026-06-27T00:00:00`  | `2026-06-28T00:00:00`  | 3              | 13     |
| 6     | `2026-06-28T00:00:00`  | `2026-06-29T00:00:00`  | 3              | 9      |
| 7     | `2026-06-29T00:00:00`  | `2026-06-29T08:00:00`  | 1              | 4      |
| 8     | `2026-06-29T08:00:00`  | `2026-06-30T00:00:00`  | 2              | 7      |
| **9** | `2026-06-30T00:00:00`  | `2026-06-30T08:00:00`  | **1**          | **4**  |

**Batch9:** `committed_bar_count=1`, `event_count=4`,
`lane_id=paper_pnl_null_shadow_v0`,
`git_sha=fde43a511ef98d7292a6bd93dd9e198ea92f79fe`,
`created_at=2026-06-30T17:42:02Z`,
`first_event_seq=65`, `last_event_seq=68`.

**Key counts after:**

| table             | count |
| ----------------- | ----- |
| ledger_batches    | 9     |
| ledger_events     | 68    |
| signal_snapshots  | 18    |
| equity_snapshots  | 18    |
| trades            | 2     |
| open_positions    | 1     |
| funding           | 7     |
| fills             | 5     |

Latest equity snapshot (`bar_ts=2026-06-30T08:00:00`, batch 9,
`bar_commit_id=af912f46a94e5b13`): equity `9968.31293555`, realized_gross_pnl
`-17.81922092`, fees_cum `2.49109039`, funding_cum `0.32461813`, unrealized_pnl
`-11.052135`, drawdown `0.00316871`, num_open `1` — **paper diagnostics only**.

---

## 7. Safety

- **Production DB unchanged:** before/after md5 `922b2785…` (identical);
  size `139264`, mtime `2026-06-30T16:20:36Z` unchanged. (sha256 after:
  `a270992e…`.)
- **Live forward_obs unchanged:** before/after per-file fingerprint identical
  across all 9 files. Frozen `/tmp` snapshot used as the writer's only input.
- **Shadow DB changed only by the authorized writer:** md5 `fb74b6d5…` →
  `672119803b…`; size `110592` → `110592`; mtime `2026-06-30T09:28:36Z` →
  `2026-06-30T17:42:03Z`. (sha256 after: `b08f584e…`.)
- No systemd / timer / service changes.
- No migration, no `ALTER`, no DB reset, no deleted outputs.
- No package installs, no lane init, no VM git pull before run.
- No exchange keys, no orders.
- `.claude/` left untouched / untracked.

---

## 8. Scope / Exclusions

- No live trading, no real orders, no exchange keys.
- No profitability or edge claim. Strategy remains `EDGE_UNPROVEN`.
- Funding verdict remains `CAVEATED_ENGINE_SEMANTICS` (not `CLEAN_NET_OF_CARRY`).
- No strategy parameter changes. No V2 engine work. No recurring shadow timers.

---

## 9. Interpretation

The batch9 one-bar commit demonstrates continued **manual shadow-lane accounting**
over one additional closed bar (`2026-06-30T08:00:00`), bringing the shadow
watermark level with forward_obs and prod (`2026-06-30T08:00:00`), with internal
accounting consistency intact and full git provenance. It does **not** prove
strategy edge. All PnL / equity values are paper diagnostics only.

---

## 10. Verdict

`SHADOW_BATCH9_ONE_BAR_COMMITTED_RECEIPT_READY_FOR_PR`
`EDGE_UNPROVEN`
