# BLOCKED RECEIPT — First VM Shadow-Lane Dry-Run Attempt (Phase 3)

> **Status: BLOCKED.** This is a *blocked* receipt, not a success receipt. It records the
> first VM shadow-lane dry-run attempt: what ran, what did not run, and why it blocked.
> **No success is claimed. No edge or profitability is claimed. Strategy label remains
> `EDGE_UNPROVEN`.** Proving lane plumbing here would, at best, prove plumbing — never edge.
> The attempt did not even reach a committed batch.

---

## 1. Purpose

- Document the first VM shadow-lane dry-run attempt, which was **BLOCKED**.
- State precisely what succeeded (pre-run safety + lane init) and what failed (the single
  writer invocation) and why (an environment/runbook mismatch).
- Provide a plan-only recovery path for a future, separately authorized attempt.
- Make **no** success claim and **no** edge/profitability claim. `EDGE_UNPROVEN`.

---

## 2. Attempt context

- Local repo commit: `fde43a5` (branch `phase3/shadow-lane-dry-run-receipt`).
- VM repo commit: `fde43a5` (`HEAD == origin/main`).
- VM host: `ubuntu-4gb-hel1-1-qnty`.
- Attempt time (UTC): `2026-06-25T16:03:36Z`.
- Shadow output path: `/srv/qnty/output/paper_pnl_null_shadow_v0`
- Shadow DB path: `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db`
- Run root (temp logs/snapshot): `/tmp/qnty_shadow_dry_run_v0`
- Source forward obs (read-only source): `/srv/qnty/output/forward_obs_v1`
- Forward obs snapshot (read-only copy): `/tmp/qnty_shadow_dry_run_v0/fwd_obs_snapshot`
- Data dir: `/srv/qnty/repo/data` (10 OHLCV CSVs + 10 funding CSVs).

Computed from the snapshot:

| Field | Value |
| --- | --- |
| `FORWARD_START_TS` | `2026-06-24T16:00:00` |
| `OBS_LAST_TS` | `2026-06-25T00:00:00` |
| `OBS_AGE_HOURS` | `16.060` |
| `OBS_ROWS` | `500` |

Lane identity used at init:

- `lane_id = paper_pnl_null_shadow_v0`
- `strategy_id = matched_null_shadow_v0`
- `strategy_version = 0.0.0-shadow`
- `pre_registration_hash = null` (existing `null` sidecar behavior; no new generation)

---

## 3. What succeeded

- Pre-run safety checks passed:
  - Production timer-window guard: `timer_window_ok`.
  - VM repo synced and verified at `fde43a5` (`HEAD == origin/main`).
  - Lane tooling present (`scripts/qnty-paper-lane-init.py`, `quantbot/paper/lane_init.py`).
  - Production DB before: integrity `ok`, `mtime=1782375609 size=110592`.
  - Shadow path **absent** before the run (precondition satisfied).
  - Forward obs present and fresh (`OBS_AGE_HOURS=16.060`, on the 8h grid).
  - Heartbeat / bar decisions present (`bar_decisions_present`).
  - Data CSVs present (`ohlcv_count=10`, `funding_count=10`).
- Forward obs snapshot copied **read-only** into `/tmp/qnty_shadow_dry_run_v0/fwd_obs_snapshot`
  (no write into `forward_obs_v1`).
- Shadow lane initialized successfully (writer NOT run by init):
  - `verify_status: PRE_START`
  - shadow DB created at `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db`
  - lane identity / config sidecars written:
    `paper_config.json`, `lane_identity.json`, `lane_config_v2.json`
  - `accounting_config_hash_v1: 32c0fbccdf46af8b50ef0e6d2da9a76657038da621ff2be1dba95d82208d5d52`
  - `config_hash_v2: 50b1bbeff42d33f4413776ea14cc06281b275b346ab79c279baf959b58ae024c`

---

## 4. What failed

- **Exactly one** writer invocation was attempted. It was **not** rerun.
- Writer failed with **exit code 1**.
- Root cause: `ModuleNotFoundError: No module named 'pandas'`.
- Import location: `quantbot/data/funding_loader.py:13` (`import pandas as pd`),
  reached transitively via `quantbot/paper/sqlite_writer.py` at import time.
- Cause classification: **environment / runbook mismatch.** The writer was launched with
  bare `/usr/bin/python3`, which has no `pandas`. The project venv
  `/srv/qnty/venv/bin/python` exists but was **not** used by this attempt's command.
- Consequence of an import-time failure:
  - The writer **did not reach `run_sqlite_accounting`**.
  - **No engine run** occurred.
  - **No batches were committed.**

---

## 5. Verification after failure (read-only)

- Verifier: exit `5`, `status: PRE_START`, `failure_count: 0`, `batches: 0`
  (consistent with nothing committed).
- Read-only DB inspection of the shadow DB:
  - `ledger_batches_count = 0`
  - `paper_config.lane_id = 'paper_pnl_null_shadow_v0'`
  - `ledger_batches` columns include `lane_id`
    (`batch_id, created_at, started_at, committed_at, git_sha, prior_watermark_bar_ts,
    new_watermark_bar_ts, first_event_seq, last_event_seq, event_count,
    committed_bar_count, paper_engine_version, config_hash, lane_id`).
  - **No `status` column** exists in `ledger_batches`. The original inline inspection query
    selected a `status` column and raised `no such column: status`; that query was simply
    too broad and is **not** a defect in the lane DB. The corrected read-only recheck above
    confirms the real schema and the zero-batch state.

---

## 6. Production safety

- Production DB mtime/size **unchanged** before and after: `mtime=1782375609 size=110592`,
  integrity `ok` (rechecked read-only after the failure).
- **No production DB mutation.**
- No write to `/srv/qnty/output/paper_pnl_v1`.
- No write into `/srv/qnty/output/forward_obs_v1` (snapshot was a read-only copy out).
- No systemd / timer / service changes.
- No migration / no `ALTER`.
- No exchange keys / no orders.
- `.claude/` remains unstaged.

---

## 7. Shadow state after block

- The shadow directory `/srv/qnty/output/paper_pnl_null_shadow_v0` **exists** and must
  **not** be treated as absent by any future step.
- The shadow DB is **initialized but `PRE_START`** with **zero ledger batches**.
- Do **not** delete it casually. Do **not** archive it.
- Do **not** rerun the writer without a new, separately authorized recovery plan.

---

## 8. Recovery plan (PLAN ONLY — not executed here)

> Plan-only. No SSH, no writer run, no lane init, no shadow-path mutation is performed by
> this receipt. The following describes a *future* authorized attempt.

The next authorized attempt should be a **recovery attempt against the already-initialized
shadow DB**, not a fresh absent-path init.

**Read-only preconditions to verify first:**

- VM repo still at `fde43a5`.
- `/srv/qnty/venv/bin/python` exists.
- `/srv/qnty/venv/bin/python -c "import pandas"` succeeds.
- Shadow DB has **zero** ledger batches.
- `paper_config.lane_id == paper_pnl_null_shadow_v0`.
- Production DB mtime captured (for an unchanged before/after assertion).
- Forward obs latest bar and heartbeat are still fresh.

**Recovery run (exactly one writer invocation):**

- Run the writer using `/srv/qnty/venv/bin/python` (the venv that has pandas) — **not**
  bare `/usr/bin/python3`.
- Do **not** run lane init again.
- Do **not** delete or recreate the shadow path.
- Use a **fresh read-only** forward obs snapshot.
- Use explicit environment + arguments:
  - `QNTY_PAPER_OUTPUT_DIR`
  - `QNTY_PAPER_DB_PATH`
  - `QNTY_FORWARD_OBS_DIR`
  - `--forward-obs-dir`
  - `--data-dir`
- Run the read-only verifier with `--no-emit --json`.
- Inspect the DB read-only.
- Confirm production DB mtime is unchanged.
- If successful, create the success receipt.
- If blocked again, **no rerun**.

---

## 9. Exclusions (explicit)

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

- `VM_SHADOW_DRY_RUN_BLOCKED_RECEIPT_READY`
- `EDGE_UNPROVEN`
- This blocked attempt proves only that lane init works and that the writer command used the
  wrong interpreter. It proves **no** lane plumbing end-to-end and **no** strategy edge.
