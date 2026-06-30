# Shadow Lane Batch8 Manual 16h Catch-Up — Phase 3 Receipt

**Verdict:** `SHADOW_BATCH8_16H_CATCHUP_COMMITTED_RECEIPT_READY_FOR_PR`
**Strategy label:** `EDGE_UNPROVEN`
**Funding verdict:** `CAVEATED_ENGINE_SEMANTICS` (NOT `CLEAN_NET_OF_CARRY`)

---

## 1. Purpose

Manually re-authorized shadow-lane **batch8 16h catch-up** (two 8h bars) against
the existing shadow lane database. The run:

- reused the existing shadow DB (no recreate / reset / migration),
- executed **exactly one** shadow writer invocation (the only re-authorized attempt),
- read forward observations from a **frozen snapshot** of `forward_obs_v1`,
- did **not** mutate the production DB,
- did **not** mutate the live forward observer directory,
- touched **no** systemd timers / services,
- placed **no** live trades and used **no** exchange keys.

Strategy remains `EDGE_UNPROVEN`. All equity / PnL figures are **paper
diagnostics only** and constitute no profitability or edge claim.

---

## 2. Previous Failed Attempt and Root Cause

A prior single writer attempt under the first batch8 authorization failed
**safely**:

- Exit `status_code 3 CONFIG_ERROR`, aborted at the pre-write identity gate
  **before committing anything**.
- **Root cause:** `QNTY_PAPER_OUTPUT_DIR` was unset, so the writer resolved its
  filesystem `paper_config.json` via `paper_output_dir()`, which defaults to the
  **production** dir `/srv/qnty/output/paper_pnl_v1`
  (`quantbot/paper/sqlite_writer.py:975-978`). It loaded the prod config
  (`forward_start_ts=2026-06-20T16:00:00`, `config_hash=1d61c1c7…`) and rejected
  it against the shadow DB row (`forward_start_ts=2026-06-24T16:00:00`,
  `config_hash=32c0fbcc…`).
- Prod DB, shadow DB, and live forward_obs were byte-unchanged. No batch8 was
  created. Shadow remained at 7 batches / watermark `2026-06-29T08:00:00`.
- This was **not** corruption and **not** a strategy result.

The four writer CLI flags do not select the lane config; the lane is chosen by
`QNTY_PAPER_OUTPUT_DIR`. This run sets it explicitly (§4).

---

## 3. Refreshed Re-Authorization Context

This is a fresh explicit authorization, superseding the failed attempt. It is the
**only** re-authorized writer attempt.

| Field                  | Value                  |
| ---------------------- | ---------------------- |
| Shadow watermark (pre) | `2026-06-29T08:00:00`  |
| forward_obs latest     | `2026-06-30T00:00:00`  |
| Gap                    | 16h = two 8h bars      |
| Expected bars to add   | 2                      |

Expected available bars (two 8h bars):
- `2026-06-29T16:00:00`
- `2026-06-30T00:00:00`

---

## 4. Preflight & Command Shape

**Local main SHA:** `d0a23639ed1423d509620fc87d3de64ba8a264f7`
(HEAD == origin/main; only untracked `.claude/`).
**VM repo SHA:** `fde43a511ef98d7292a6bd93dd9e198ea92f79fe`.
**VM venv Python:** `/srv/qnty/venv/bin/python`.
**Timer window:** clear — VM `2026-06-30T09:28Z`; all writer services
(`qnty-shadow-run`, `qnty-paper-pnl`, `qnty-data-refresh`) inactive; next runs
16:05–16:20Z (~7h away).

**Safety snapshots before** (sha256 / size / mtime):

| Target                | sha256 (prefix) | size     | mtime        |
| --------------------- | --------------- | -------- | ------------ |
| prod DB               | `3b5f314d…`     | `139264` | `1782807720` |
| shadow DB             | `e82ffd2e…`     | `110592` | `1782766383` |
| live forward_obs (combined fingerprint) | `6edb3e08…` | — | — |

**Frozen forward_obs snapshot path:**
`/tmp/qnty_shadow_batch8_manual_run_v0/forward_obs_v1_frozen`
— 500 rows, latest bar `2026-06-30T00:00:00` (confirmed exact match).

**Shadow lane config:**
`/srv/qnty/output/paper_pnl_null_shadow_v0/paper_config.json` present
(`forward_start_ts=2026-06-24T16:00:00`, `config_hash=32c0fbcc…`, matches DB).

**Required env var:** `QNTY_PAPER_OUTPUT_DIR=/srv/qnty/output/paper_pnl_null_shadow_v0`

**Exact writer command shape (one invocation, run from `/srv/qnty/repo`):**

```bash
QNTY_PAPER_OUTPUT_DIR=/srv/qnty/output/paper_pnl_null_shadow_v0 \
/srv/qnty/venv/bin/python scripts/qnty-paper-sqlite-accounting.py \
  --db-path /srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db \
  --forward-obs-dir /tmp/qnty_shadow_batch8_manual_run_v0/forward_obs_v1_frozen \
  --data-dir /srv/qnty/repo/data \
  --json
```

Verifier run read-only with `--no-emit --json`. DB inspection over a read-only
SQLite connection (`mode=ro&immutable=1`).

---

## 5. Writer Result

- **Exit code:** `0`
- **stdout:** `{"status_code": 0, "status_message": "Committed batch 8: 2 bars, 7 events"}`
- No rerun performed (single invocation only).

---

## 6. Verifier Result (after writer)

- **Exit code:** `0` — **Status:** `OK` — **failure_count:** `0`
- **Batches:** `8`
- **Watermark:** `2026-06-30T00:00:00`
- **Funding verdict:** `CAVEATED_ENGINE_SEMANTICS` (preserved)
- **Funding diagnostic label:**
  `missing_funding_treated_as_zero_like_current_engine_not_net_of_carry_clean`
- Missing window still: `SOLUSDT|2026-06-27T08:00:00|exit` (known caveat;
  6 funding rows, 6 required intervals, 0 rate_available_zero).
- git provenance: latest batch git_sha
  `fde43a511ef98d7292a6bd93dd9e198ea92f79fe`, no unprovenanced batches.

---

## 7. DB Inspection (after writer, read-only)

- **paper_config.lane_id:** `paper_pnl_null_shadow_v0`
  (`strategy_id=matched_null_shadow_v0`, `strategy_version=0.0.0-shadow`)
- **Batch count after:** `8`; **batch_id=8 occurs exactly once**; max batch_id `8`.
- No batch with watermark `> 2026-06-30T00:00:00`.

| batch | prior watermark        | new watermark          | committed_bars | events |
| ----- | ---------------------- | ---------------------- | -------------- | ------ |
| 1     | `null`                 | `2026-06-25T08:00:00`  | 3              | 13     |
| 2     | `2026-06-25T08:00:00`  | `2026-06-26T00:00:00`  | 2              | 7      |
| 3     | `2026-06-26T00:00:00`  | `2026-06-26T08:00:00`  | 1              | 3      |
| 4     | `2026-06-26T08:00:00`  | `2026-06-27T00:00:00`  | 2              | 8      |
| 5     | `2026-06-27T00:00:00`  | `2026-06-28T00:00:00`  | 3              | 13     |
| 6     | `2026-06-28T00:00:00`  | `2026-06-29T00:00:00`  | 3              | 9      |
| 7     | `2026-06-29T00:00:00`  | `2026-06-29T08:00:00`  | 1              | 4      |
| **8** | `2026-06-29T08:00:00`  | `2026-06-30T00:00:00`  | **2**          | **7**  |

**Batch8:** `committed_bar_count=2`, `event_count=7`,
`lane_id=paper_pnl_null_shadow_v0`,
`git_sha=fde43a511ef98d7292a6bd93dd9e198ea92f79fe`,
`created_at=2026-06-30T09:28:34Z`.

**Key counts after:**

| table             | count |
| ----------------- | ----- |
| ledger_batches    | 8     |
| ledger_events     | 64    |
| signal_snapshots  | 17    |
| equity_snapshots  | 17    |
| trades            | 2     |
| open_positions    | 1     |
| funding           | 6     |
| fills             | 5     |

Latest equity snapshot (`2026-06-30T00:00:00`, batch 8): equity
`9982.32368362`, realized_gross_pnl `-17.81922092`, fees_cum `2.49109039`,
funding_cum `0.24842959`, unrealized_pnl `2.88242452`, num_open `1` — **paper
diagnostics only**.

---

## 8. Safety

- **Production DB unchanged:** before/after sha256 `3b5f314d…`, size `139264`,
  mtime `1782807720` (identical).
- **Live forward_obs unchanged:** before/after combined fingerprint `6edb3e08…`
  (identical). Frozen `/tmp` snapshot used as writer input.
- **Shadow DB changed only by the authorized writer:** sha256
  `e82ffd2e…` → `8b4900f8…`, size `110592` → `110592`,
  mtime `1782766383` → `1782811716`.
- No systemd / timer / service changes.
- No migration, no `ALTER`, no DB reset, no deleted outputs.
- No package installs, no lane init, no VM git pull before run.
- No exchange keys, no orders.
- `.claude/` left untouched / untracked.

---

## 9. Scope / Exclusions

- No live trading, no real orders, no exchange keys.
- No profitability or edge claim. Strategy remains `EDGE_UNPROVEN`.
- Funding verdict remains `CAVEATED_ENGINE_SEMANTICS` (not `CLEAN_NET_OF_CARRY`).
- No strategy parameter changes. No V2 engine work. No recurring shadow timers.

---

## 10. Interpretation

The batch8 16h catch-up demonstrates continued **manual shadow-lane accounting**
over two additional closed bars (`2026-06-29T16:00:00`, `2026-06-30T00:00:00`),
bringing the shadow watermark level with forward_obs (`2026-06-30T00:00:00`),
with internal accounting consistency intact and full git provenance. It does
**not** prove strategy edge. All PnL / equity values are paper diagnostics only.

---

## 11. Verdict

`SHADOW_BATCH8_16H_CATCHUP_COMMITTED_RECEIPT_READY_FOR_PR`
`EDGE_UNPROVEN`
