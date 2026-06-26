# Shadow Lane Batch 3 — Manual Phase 3 Receipt

Status: `VM_SHADOW_BATCH3_MANUAL_RECEIPT_READY`
Strategy label: `EDGE_UNPROVEN`

## 1. Purpose

Docs-only receipt for a manually authorized shadow-lane **batch 3**.

- Existing shadow DB reused — no lane init rerun.
- Exactly **one** batch3 writer invocation.
- Frozen forward-obs snapshot used (not live `forward_obs_v1`).
- No production DB mutation.
- No `forward_obs_v1` mutation.
- No timers / services touched.
- No live trading / orders.
- Strategy remains `EDGE_UNPROVEN`.

## 2. Authorization context

- Prior read-only readiness gate returned: `SHADOW_BATCH3_READY_FOR_SEPARATE_AUTHORIZATION`.
- Shadow watermark before batch3: `2026-06-26T00:00:00`.
- Forward obs latest before batch3: `2026-06-26T08:00:00`.
- Forward obs was exactly **8h ahead** of the shadow watermark and on the 8h grid (00/08/16 UTC).

## 3. Preflight (read-only except `/tmp` snapshot/log dir)

- Local main SHA: `a819a2976d5d5642a1f46eceb44cee411afa15ca` (`HEAD == origin/main`).
- VM repo SHA: `fde43a511ef98d7292a6bd93dd9e198ea92f79fe` (code-equivalent for lane behavior; later local commits are docs-only receipts).
- venv Python: `/srv/qnty/venv/bin/python`.
- pandas import OK: `3.0.2`.
- Timer window OK: `timer_window_ok=true` (UTC `2026-06-26T19:35:18Z`, clear of 00:20 / 08:20 / 16:20 prod timers).
- Production DB before stat: `mtime=1782490922 size=118784`.
- Shadow DB before stat: `mtime=1782468357 size=102400`.
- Forward obs before stat: `mtime=1782490545 size=132908`.
- Shadow DB integrity OK: `PRAGMA integrity_check = ok`.
- Shadow `paper_config.lane_id` correct: `paper_pnl_null_shadow_v0`.
- Exactly **2** existing authorized shadow batches before batch3; both with correct `lane_id`.
- Shadow verifier OK before writer: `status=OK`, `failure_count=0`, `CLEAN_NET_OF_CARRY`.
- Production verifier OK before writer (safety read only): `status=OK`, `failure_count=0`.
- Frozen snapshot path: `/tmp/qnty_shadow_batch3_manual_run_v0/fwd_obs_snapshot`.
  - Snapshot rows: `500`; snapshot last ts: `2026-06-26T08:00:00`.

## 4. Command shape

- One writer command using `/srv/qnty/venv/bin/python`:
  `scripts/qnty-paper-sqlite-accounting.py --json`
  - `--db-path` → shadow DB (`/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db`).
  - `--forward-obs-dir` → frozen snapshot (`/tmp/qnty_shadow_batch3_manual_run_v0/fwd_obs_snapshot`), **not** live `forward_obs_v1`.
  - `--data-dir /srv/qnty/repo/data`.
- Verifier command run with `--no-emit --json` (read-only).
- DB inspection performed read-only (`mode=ro` URI).

## 5. Writer result

- Writer exit code: `0`.
- Writer stdout summary: `Committed batch 3: 1 bars, 3 events` (`status_code: 0`).
- No rerun.

## 6. Verifier result

- Verifier exit code: `0`.
- Verifier status: `OK`.
- Failure count: `0` (no failures).
- Funding / net-of-carry verdict: `CLEAN_NET_OF_CARRY` (funding coverage `complete`, SOLUSDT complete).

## 7. DB inspection (after writer, read-only)

- `paper_config.lane_id`: `paper_pnl_null_shadow_v0`.
- Ledger batch count after: `3`.
- Batch watermark details:
  - Batch 1: `prior=null` → `new=2026-06-25T08:00:00`, committed_bar_count=3, event_count=13.
  - Batch 2: `prior=2026-06-25T08:00:00` → `new=2026-06-26T00:00:00`, committed_bar_count=2, event_count=7.
  - Batch 3: `prior=2026-06-26T00:00:00` → `new=2026-06-26T08:00:00`, committed_bar_count=**1**, event_count=**3**, git_sha=`fde43a5…`, created_at=`2026-06-26T19:36:04Z`.
- Table counts:
  - `ledger_batches`: 3
  - `ledger_events`: 23
  - `signal_snapshots`: 6
  - `equity_snapshots`: 6
  - `trades`: 1
  - `open_positions`: 1
  - `funding`: 1
  - `fills`: 3
- Latest equity snapshot (paper diagnostic only): `bar_ts=2026-06-26T08:00:00`, `equity=9970.24338739`, `unrealized_pnl=17.58563749`, `realized_gross_pnl=-45.91133828`, `num_open=1`, `drawdown=0.00297566`. Values recorded as observed; not overstated.

## 8. Safety

- Production DB before/after stat **unchanged**: `1782490922 118784` → `1782490922 118784`.
- Live forward_obs before/after stat **unchanged**: `1782490545 132908` → `1782490545 132908`.
- Shadow DB changed only because the authorized batch3 writer ran: `mtime 1782468357 → 1782502566`, `size 102400 → 102400`.
- No write into `paper_pnl_v1`.
- No write into live `forward_obs_v1`.
- No systemd / timer / service changes.
- No migration / ALTER.
- No exchange keys / orders.
- `.claude/` left unstaged.

## 9. Scope / exclusions

- No live trading.
- No real orders.
- No `source_data_digest`.
- No V2.
- No recurring shadow timers.
- No cross-lane reporter.
- No edge / profitability claim.

## 10. Interpretation

- Batch3 proves continued manual shadow-lane accounting / plumbing over the next closed bar (`2026-06-26T08:00:00`).
- This does **not** prove strategy edge.
- All PnL / equity figures are **paper diagnostic only**.
- `EDGE_UNPROVEN`.

## 11. Verdict

- `VM_SHADOW_BATCH3_MANUAL_RECEIPT_READY`
- `EDGE_UNPROVEN`
