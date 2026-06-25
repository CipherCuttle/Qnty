# HEALTH RECEIPT — Post-Recovery VM Shadow-Lane Health Check (Phase 3)

> **Status: GREEN (operational plumbing only).** This is a docs-only receipt for a
> **read-only** post-recovery health check of the VM shadow lane. The check verdict was
> `VM_SHADOW_HEALTH_GREEN`. **No writer, verifier, or lane init was run by this receipt
> task.** No production mutation occurred. **No edge or profitability is claimed. Strategy
> label remains `EDGE_UNPROVEN`.** Green here means the lane plumbing is healthy after batch
> 1 — never that strategy edge exists.

---

## 1. Purpose

- Record the post-recovery, read-only shadow-lane health check as a docs-only receipt.
- The health check verdict was `VM_SHADOW_HEALTH_GREEN`.
- **This receipt task ran no writer, no verifier, and no lane init** (it only documents the
  prior read-only check).
- No production DB mutation.
- `EDGE_UNPROVEN`.

---

## 2. Context

- Local main: `c540a91` (`docs: add shadow lane recovery receipt (#26)`).
- VM shadow output path: `/srv/qnty/output/paper_pnl_null_shadow_v0`
- VM shadow DB path: `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db`
- Production DB was touched **only** by a read-only `stat`/integrity safety guard
  (no mutation).
- VM repo at `fde43a5`; this is **code-equivalent for lane behavior**. The local delta to
  `c540a91` is **docs-only receipts** (#25, #26), not code or lane behavior. The git_sha
  stamped on batch 1 is `fde43a5`, matching the VM repo.

---

## 3. Shadow DB state (read-only at check time)

- Integrity: `ok`.
- Lane identity:
  - `lane_id = paper_pnl_null_shadow_v0`
  - `strategy_id = matched_null_shadow_v0`
  - `strategy_version = 0.0.0-shadow`
  - `pre_registration_hash = null`
  - `config_hash = 32c0fbccdf46af8b50ef0e6d2da9a76657038da621ff2be1dba95d82208d5d52`
  - `config_hash_v2 = 50b1bbeff42d33f4413776ea14cc06281b275b346ab79c279baf959b58ae024c`

Table counts (actual, as observed):

| Table | Count |
| --- | --- |
| `ledger_batches` | 1 |
| `ledger_events` | 13 |
| `signal_snapshots` | 3 |
| `equity_snapshots` | 3 |
| `trades` | 1 |
| `open_positions` | 0 |
| `funding` | 1 |
| `fills` | 2 |

Batch 1 details:

- `lane_id = paper_pnl_null_shadow_v0`
- `committed_bar_count = 3`
- `event_count = 13`
- `new_watermark_bar_ts = 2026-06-25T08:00:00` (`prior_watermark_bar_ts = null`)
- `git_sha = fde43a511ef98d7292a6bd93dd9e198ea92f79fe`

Only one batch is present; its lane_id matches the lane.

---

## 4. Verifier result (read-only)

- Verifier exit code: `0`.
- `status: OK`.
- `failure_count: 0` (`failures: []`).
- Funding coverage: `complete`, verdict `CLEAN_NET_OF_CARRY`.
- Git provenance clean: `any_batch_missing_git_sha: false`, latest batch git_sha
  `fde43a511ef98d7292a6bd93dd9e198ea92f79fe`.
- Verifier disclaimer (recorded verbatim): "Verifier v1 validates SQLite ledger integrity
  and internal accounting consistency. It does not independently rederive OHLCV
  marks/unrealized PnL/exposure from source price data."

---

## 5. Forward obs state (read-only)

- Rows: `500`.
- Latest timestamp: `2026-06-25T08:00:00`.
- Age at check time: ~`9.72h`.
- On the 8h grid.
- **Note:** the latest forward obs timestamp **equals the shadow watermark**
  (`2026-06-25T08:00:00`). No bar beyond the shadow watermark was available at check time,
  so there was no new bar for a hypothetical batch 2.

---

## 6. Recovery logs (read-only)

- `writer_exit = 0`.
- Writer message: `"Committed batch 1: 3 bars, 13 events"`.
- `verify_exit = 0`.
- No stderr (writer and verifier stderr empty).

---

## 7. Production safety

- Production DB stat **unchanged** during the check (`prod_before == prod_after`:
  `mtime=1782404496 size=110592`, integrity `ok`).
- No production DB mutation.
- No write into `/srv/qnty/output/paper_pnl_v1`.
- No write into `/srv/qnty/output/forward_obs_v1`.
- No systemd / timer / service changes.
- No migration / no `ALTER`.
- No exchange keys / no orders.
- `.claude/` remains unstaged.

---

## 8. Interpretation

- The shadow lane shows **green operational health** after batch 1.
- Lane plumbing is verified end-to-end (writer → ledger → verifier).
- This is **not** a profitability signal. Paper equity/PnL numbers are internal accounting
  diagnostics only.
- This is **not** an edge claim.
- Strategy label remains `EDGE_UNPROVEN`.

---

## 9. Next gate

- **Do not run batch 2** until forward obs advances **beyond** the shadow watermark
  `2026-06-25T08:00:00`.
- The next writer batch must be **separately authorized**.
- No shadow timers yet.

---

## 10. Verdict

- `VM_SHADOW_HEALTH_GREEN_RECEIPT_READY`
- `EDGE_UNPROVEN`
- This documents healthy one-shot shadow-lane plumbing after recovery — **not** strategy edge.
