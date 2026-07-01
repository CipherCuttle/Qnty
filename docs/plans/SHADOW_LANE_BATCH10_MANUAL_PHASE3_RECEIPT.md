# Shadow Lane Batch10 Manual 16h Catch-up — Phase 3 Receipt

**Verdict:** `SHADOW_BATCH10_16H_CATCHUP_COMMITTED_RECEIPT_READY_FOR_PR`
**Strategy label:** `EDGE_UNPROVEN`
**Funding verdict:** `CAVEATED_ENGINE_SEMANTICS` (NOT `CLEAN_NET_OF_CARRY`)

---

## 1. Authorization Context

This is a **separate explicit authorization** (`AUTHORIZE_SHADOW_BATCH10_16H_CATCHUP_WRITER_ONCE`)
that followed a **refreshed** read-only batch10 readiness gate. It advanced the
shadow lane by **exactly two 8h bars** (a 16h catch-up) against the existing
shadow lane database. The run:

- reused the existing shadow DB (no recreate / reset / migration),
- executed **exactly one** shadow writer invocation (the only authorized attempt),
- read forward observations from a **frozen `/tmp` snapshot** of `forward_obs_v1`,
- did **not** mutate the production DB,
- did **not** mutate the live forward observer directory,
- touched **no** systemd timers / services,
- placed **no** live trades and used **no** exchange keys.

Strategy remains `EDGE_UNPROVEN`. All equity / PnL figures are **paper
diagnostics only** and constitute no profitability or edge claim.

### 1a. Prior Blocked Timer-Window Attempt

An earlier batch10 one-bar writer authorization was **blocked before any writer
ran** because the VM was too close to the 08:xx UTC production timer cluster:

```txt
VERDICT: SHADOW_BATCH10_ONE_BAR_BLOCKED_TIMER_WINDOW_NO_WRITER_RUN
```

That blocked attempt created **no** writer run, **no** snapshot, **no** receipt,
**no** branch, and **no** commit. Shadow remained at 9 batches with watermark
`2026-06-30T08:00:00`. During the block window the 08:xx timer cluster advanced
forward_obs one further 8h bar (to `2026-07-01T00:00:00`), so the old **one-bar**
authorization became **void** and was **not** reused. This receipt documents the
fresh two-bar (16h) authorization that replaced it.

---

## 2. Readiness Gate Result

The preceding refreshed read-only gate returned:

```txt
VERDICT: SHADOW_BATCH10_NOT_READY: gate stale; refreshed authorization required for 16h catch-up
```

Gate facts carried into this authorization:

| Field                          | Value                  |
| ------------------------------ | ---------------------- |
| Shadow watermark (pre)         | `2026-06-30T08:00:00`  |
| forward_obs latest             | `2026-07-01T00:00:00`  |
| Prod watermark (situational)   | `2026-07-01T00:00:00`  |
| Gap                            | 16h = two 8h bars      |
| Expected bars to add           | 2                      |
| Available bars                 | `2026-06-30T16:00:00`, `2026-07-01T00:00:00` |
| Unauthorized batch10           | none                   |
| Integrity / verifier / lane / mutation checks | all passed |

---

## 3. Preflight & Command Shape

**Local main SHA:** `dcbe1aadd36526816c2c86feaa2394e7e905a633`
(HEAD == origin/main; only untracked `.claude/`).
**VM repo SHA:** `fde43a511ef98d7292a6bd93dd9e198ea92f79fe`.
**VM venv Python:** `/srv/qnty/venv/bin/python`.
**Timer window:** clear — VM `2026-07-01T09:37Z`; all writer services
(`qnty-shadow-run`, `qnty-paper-pnl`, `qnty-data-refresh`) inactive; next runs
Wed `2026-07-01 16:05–16:21Z` (~6.5h away). The prior 08:xx cluster had already
fired (last `qnty-health-receipt` at `08:31Z`, ~1h before this run).

**Safety snapshots before** (sha256 / size / mtime):

| Target                | sha256      | size     | mtime (UTC)            |
| --------------------- | ----------- | -------- | ---------------------- |
| prod DB               | `4d428a41…` | `139264` | `2026-07-01T08:20:55Z` |
| shadow DB             | `b08f584e…` | `110592` | `2026-06-30T17:42:03Z` |
| live forward_obs (aggregate fingerprint) | `5569f21c…` (9 files) | — | — |

**Frozen forward_obs snapshot path:**
`/tmp/qnty_shadow_batch10_manual_run_v0/forward_obs_v1_frozen`
— copied from `/srv/qnty/output/forward_obs_v1`, 9 files byte-identical to live,
`observation_log.json` 500 rows, latest bar `2026-07-01T00:00:00` (confirmed exact match).

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
  --forward-obs-dir /tmp/qnty_shadow_batch10_manual_run_v0/forward_obs_v1_frozen \
  --data-dir /srv/qnty/repo/data \
  --json
```

Verifier run read-only with `--no-emit --json`. DB inspection over a read-only
SQLite connection (`mode=ro`).

---

## 4. Writer Result

- **Exit code:** `0`
- **stdout:** `{"status_code": 0, "status_message": "Committed batch 10: 2 bars, 8 events"}`
- No rerun performed (single invocation only).

Matches the expected result:

```txt
lane: paper_pnl_null_shadow_v0
batch_id: 10
prior watermark: 2026-06-30T08:00:00
new watermark: 2026-07-01T00:00:00
committed_bar_count: 2
```

---

## 5. Verifier Result (after writer)

- **Exit code:** `0` — **Status:** `OK` — **failure_count:** `0`
- **Batches:** `10`
- **Watermark:** `2026-07-01T00:00:00`
- **query_only:** `1` (pure read-only, `--no-emit`, nothing published)
- **Funding verdict:** `CAVEATED_ENGINE_SEMANTICS` (preserved)
- **Funding diagnostic label:**
  `missing_funding_treated_as_zero_like_current_engine_not_net_of_carry_clean`
- Missing windows still (known caveat): `SOLUSDT|2026-06-27T08:00:00|exit` and
  `SOLUSDT|2026-06-30T16:00:00` (9 funding rows, 9 required intervals,
  0 rate_available_zero).
- git provenance: latest batch git_sha
  `fde43a511ef98d7292a6bd93dd9e198ea92f79fe`, no unprovenanced batches.

---

## 6. DB Inspection (after writer, read-only)

- **paper_config.lane_id:** `paper_pnl_null_shadow_v0`
  (`strategy_id=matched_null_shadow_v0`, `strategy_version=0.0.0-shadow`)
- **Batch count after:** `10`; **batch_id=10 occurs exactly once**; max batch_id `10`.
- **integrity_check:** `ok`; single distinct `lane_id`.
- No batch with watermark `> 2026-07-01T00:00:00`.

| batch  | prior watermark        | new watermark          | committed_bars | events |
| ------ | ---------------------- | ---------------------- | -------------- | ------ |
| 1      | `null`                 | `2026-06-25T08:00:00`  | 3              | 13     |
| 2      | `2026-06-25T08:00:00`  | `2026-06-26T00:00:00`  | 2              | 7      |
| 3      | `2026-06-26T00:00:00`  | `2026-06-26T08:00:00`  | 1              | 3      |
| 4      | `2026-06-26T08:00:00`  | `2026-06-27T00:00:00`  | 2              | 8      |
| 5      | `2026-06-27T00:00:00`  | `2026-06-28T00:00:00`  | 3              | 13     |
| 6      | `2026-06-28T00:00:00`  | `2026-06-29T00:00:00`  | 3              | 9      |
| 7      | `2026-06-29T00:00:00`  | `2026-06-29T08:00:00`  | 1              | 4      |
| 8      | `2026-06-29T08:00:00`  | `2026-06-30T00:00:00`  | 2              | 7      |
| 9      | `2026-06-30T00:00:00`  | `2026-06-30T08:00:00`  | 1              | 4      |
| **10** | `2026-06-30T08:00:00`  | `2026-07-01T00:00:00`  | **2**          | **8**  |

**Batch10:** `committed_bar_count=2`, `event_count=8`,
`lane_id=paper_pnl_null_shadow_v0`,
`git_sha=fde43a511ef98d7292a6bd93dd9e198ea92f79fe`,
`created_at=2026-07-01T09:37:02Z`, `committed_at=2026-07-01T09:37:02Z`,
`first_event_seq=69`, `last_event_seq=76`.

**Key counts after:**

| table             | count |
| ----------------- | ----- |
| ledger_batches    | 10    |
| ledger_events     | 76    |
| signal_snapshots  | 20    |
| equity_snapshots  | 20    |
| trades            | 2     |
| open_positions    | 1     |
| funding           | 9     |
| fills             | 5     |

Latest equity snapshot (`bar_ts=2026-07-01T00:00:00`, batch 10,
`bar_commit_id=c51bc8f81ea11713`): equity `9991.5443494`, realized_gross_pnl
`-17.81922092`, fees_cum `2.49109039`, funding_cum `0.4978528`, unrealized_pnl
`12.35251351`, drawdown `0.00084557`, num_open `1` — **paper diagnostics only**.

---

## 7. Safety

- **Production DB unchanged:** before/after sha256 `4d428a41…` (identical);
  size `139264`, mtime `2026-07-01T08:20:55Z` unchanged.
- **Live forward_obs unchanged:** before/after aggregate fingerprint `5569f21c…`
  identical across all 9 files. Frozen `/tmp` snapshot used as the writer's only input.
- **Shadow DB changed only by the authorized writer:** sha256 `b08f584e…` →
  `27948ca0…`; size `110592` → `110592`; watermark updated to
  `2026-07-01T00:00:00` at `2026-07-01T09:37:02Z`.
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

The batch10 two-bar (16h) catch-up commit demonstrates continued **manual
shadow-lane accounting** over two additional closed bars
(`2026-06-30T16:00:00` and `2026-07-01T00:00:00`), bringing the shadow watermark
level with forward_obs and prod (`2026-07-01T00:00:00`), with internal accounting
consistency intact and full git provenance. It does **not** prove strategy edge.
All PnL / equity values are paper diagnostics only.

---

## 10. Verdict

`SHADOW_BATCH10_16H_CATCHUP_COMMITTED_RECEIPT_READY_FOR_PR`
`EDGE_UNPROVEN`
