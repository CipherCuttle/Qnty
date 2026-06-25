# RECOVERY RECEIPT — First VM Shadow-Lane Dry-Run Recovery (Phase 3)

> **Status: RECOVERY SUCCEEDED (plumbing only).** This records the recovery of the first VM
> shadow-lane dry-run after the prior blocked attempt. The shadow lane moved from `PRE_START`
> / 0 batches to **one verified shadow batch**. **No success of strategy is claimed. No edge
> or profitability is claimed. Strategy label remains `EDGE_UNPROVEN`.** Proving lane plumbing
> here proves plumbing only — never edge.

---

## 1. Purpose

- Recover the first VM shadow-lane dry run against the **already-initialized** shadow DB.
- The existing shadow DB was **reused**; **no lane init was rerun**.
- **Exactly one** recovery writer invocation was run.
- The project **venv Python** (`/srv/qnty/venv/bin/python`) was used for writer, verifier,
  and all inspection.
- **No production DB mutation.** No timers/services touched. No live trading/orders.
- Strategy label remains `EDGE_UNPROVEN`.

---

## 2. Prior block context

- The first VM shadow-lane writer attempt **failed before the engine run** with
  `ModuleNotFoundError: No module named 'pandas'`.
- Root cause: the writer was launched with bare `/usr/bin/python3`, which has no `pandas`;
  the project venv was not used by that attempt's command.
- That blocked receipt was already merged in **PR #25**
  (`50443e6 docs: add shadow lane dry run blocked receipt`).
- Consequence of that attempt: no engine run, no committed batch — shadow DB remained
  `PRE_START` with zero batches.

> Note on this recovery: the first execution of the recovery writer step aborted **before any
> writer invocation** at exit 127, due to a shell-quoting bug in a temporary local env file
> (`prod_before.env` held the stat string `1782404496 110592`, whose embedded space broke
> `source`). This was a runbook/temp-file bug, **not** a QNTY code bug and **not** a writer
> failure — the writer never ran (empty logs dir, shadow DB still 0 batches, prod DB stat
> unchanged). The single writer invocation was therefore not consumed. The step was re-run
> with the prod before-stat captured directly via `stat` instead of sourcing the malformed
> file, and a guard asserting `writer_exit.txt` did not already exist. The writer then ran
> **exactly once**.

---

## 3. Recovery preflight (read-only)

- VM host: `ubuntu-4gb-hel1-1-qnty`; preflight time (UTC): `2026-06-25T17:26:43Z`.
- Production timer-window guard: `timer_window_ok`.
- VM repo commit: `fde43a5` (lane-capable; `head=fde43a511ef98d7292a6bd93dd9e198ea92f79fe`).
- Interpreter: `/srv/qnty/venv/bin/python`, `pandas` import OK (version `3.0.2`).
- Existing shadow DB before recovery:
  - integrity `ok`
  - `ledger_batches_count = 0`
  - `paper_config.lane_id = paper_pnl_null_shadow_v0`
  - `strategy_id = matched_null_shadow_v0`, `strategy_version = 0.0.0-shadow`
  - `pre_registration_hash = null`
  - `config_hash = 32c0fbccdf46af8b50ef0e6d2da9a76657038da621ff2be1dba95d82208d5d52`
  - `config_hash_v2 = 50b1bbeff42d33f4413776ea14cc06281b275b346ab79c279baf959b58ae024c`
- Forward obs fresh: `rows=500`, `last_ts=2026-06-25T08:00:00`, `age_hours=9.445`, on 8h grid.
- Data dir: `ohlcv_count=10`, `funding_count=10`.
- Read-only forward obs snapshot path: `/tmp/qnty_shadow_recovery_run_v0/fwd_obs_snapshot`
  (copied out; no write into `forward_obs_v1`).
- Production DB before stat: `mtime=1782404496 size=110592`, integrity `ok` (read-only).

Computed from the snapshot:

| Field | Value |
| --- | --- |
| `FORWARD_START_TS` | `2026-06-25T00:00:00` |
| `OBS_LAST_TS` | `2026-06-25T08:00:00` |
| `OBS_AGE_HOURS` | `9.446` |
| `OBS_ROWS` | `500` |

---

## 4. Command shape

- **No lane init command** was run.
- **One** writer command, using venv Python:
  - `/srv/qnty/venv/bin/python scripts/qnty-paper-sqlite-accounting.py`
  - args: `--db-path <shadow_db> --forward-obs-dir <snapshot> --data-dir <data> --json`
  - env: `QNTY_PAPER_OUTPUT_DIR`, `QNTY_PAPER_DB_PATH`, `QNTY_FORWARD_OBS_DIR`.
- **One** verifier command, using venv Python:
  - `/srv/qnty/venv/bin/python scripts/qnty-paper-sqlite-verify.py --db-path <shadow_db> --no-emit --json`
- DB inspection: read-only (`sqlite3` `mode=ro` URI) via venv Python.

---

## 5. Writer result

- Writer **exit code: 0**.
- Writer JSON status:
  - `status_code: 0`
  - `status_message: "Committed batch 1: 3 bars, 13 events"`
- No rerun.

---

## 6. Verifier result

- Verifier **exit code: 0**.
- `status: OK`.
- `failure_count: 0`, `failures: []`.
- Report highlights:
  - `batches: 1`, `events: 13`, `equity_rows: 3`, `query_only: 1`
  - `watermark_bar_ts: 2026-06-25T08:00:00`
  - `forward_start_ts: 2026-06-24T16:00:00`
  - `funding_coverage.decision: complete`, `funding_coverage_verdict: CLEAN_NET_OF_CARRY`
  - `git_provenance.latest_batch_git_sha: fde43a511ef98d7292a6bd93dd9e198ea92f79fe`,
    `any_batch_missing_git_sha: false`
  - Verifier disclaimer (recorded verbatim): "Verifier v1 validates SQLite ledger integrity
    and internal accounting consistency. It does not independently rederive OHLCV
    marks/unrealized PnL/exposure from source price data."

---

## 7. DB inspection (read-only, after writer)

- `paper_config.lane_id = paper_pnl_null_shadow_v0`
  (unchanged `strategy_id = matched_null_shadow_v0`, `strategy_version = 0.0.0-shadow`,
  `pre_registration_hash = null`).
- `ledger_batches` count: **1**.
- Batch 1:
  - `lane_id = paper_pnl_null_shadow_v0`
  - `committed_bar_count = 3`, `event_count = 13`
  - `prior_watermark_bar_ts = null`, `new_watermark_bar_ts = 2026-06-25T08:00:00`
  - `git_sha = fde43a511ef98d7292a6bd93dd9e198ea92f79fe`
  - `created_at = started_at = 2026-06-25T17:28:20Z`

Table counts (actual):

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

These are recorded as observed; nothing is overstated.

---

## 8. Production safety

- Production DB before/after stat **unchanged**: `mtime=1782404496 size=110592`
  (`prod_before == prod_after`).
- No `/srv/qnty/output/paper_pnl_v1` mutation; production writer not run.
- No write into `/srv/qnty/output/forward_obs_v1` (snapshot was a read-only copy out).
- No systemd / timer / service changes.
- No migration / no `ALTER`.
- No exchange keys / no orders.
- `.claude/` remains unstaged.

---

## 9. Scope / exclusions (explicit)

- No live trading.
- No real orders.
- No `source_data_digest`.
- No `pre_registration_hash` generation beyond the existing `null` sidecar behavior.
- No V2.
- No recurring shadow timers.
- No cross-lane reporter.
- No edge / profitability claim.

---

## 10. Verdict

- `VM_SHADOW_RECOVERY_RECEIPT_READY`
- `EDGE_UNPROVEN`
- This proves **one-shot lane recovery/plumbing only** — the shadow lane advanced from
  `PRE_START` / 0 batches to one verified batch. It proves **no** strategy edge and **no**
  profitability.
