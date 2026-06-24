# Ledger Batch Lane Stamping — Phase 3 Plan (PLAN ONLY)

Strategy label: `EDGE_UNPROVEN`

> This document is a **plan-only** design receipt. No ledger batch stamping code,
> writer runtime change, or verifier batch-consistency check is implemented by this
> document. It records the intended future design so the implementation slice can be
> reviewed before any code is written.

## 1. Purpose

- Plan-only design for **future** ledger batch lane stamping.
- Goal: new-lane DB batches should carry `ledger_batches.lane_id`, so every batch
  self-attests which lane produced it.
- This is **not** implementation.
- This is **not** a live/shadow lane. No live trading, keys, or orders are involved.

## 2. Current state

- `paper_config` now has additive nullable lane identity fields
  (`lane_id`, `strategy_id`, `strategy_version`, `config_hash_v2`,
  `pre_registration_hash`).
- `initialize_lane_database(...)` exists and stamps lane identity onto the
  `paper_config` row for newly-created lane DBs.
- Verifier dual-mode lane identity validation is merged via **PR #17**
  (squash commit `792baa8 Add verifier lane identity validation (#17)`).
- `_insert_ledger_batch(...)` currently writes exactly these columns:
  - `created_at`
  - `started_at`
  - `prior_watermark_bar_ts`
  - `paper_engine_version`
  - `config_hash`
- `ledger_batches` has **no** `lane_id` column today. Lane identity lives only on
  `paper_config` and is not propagated to individual batches.

## 3. Desired behavior

- v1/baseline DBs keep existing behavior — byte-identical, no stamping, no new checks.
- New-lane DBs stamp **every** `ledger_batches` row with `paper_config.lane_id`.
- Verifier later checks that every committed batch lane matches `paper_config.lane_id`.
- `source_data_digest` stays **out of scope** (lane identity is not input-data
  provenance).

## 4. Schema decision

- Add a nullable `ledger_batches.lane_id TEXT` column **only to the newly-created DB
  schema** (in the `CREATE TABLE IF NOT EXISTS ledger_batches` definition).
- **No ALTER.**
- **No migration.**
- Old DBs without the column stay valid (verifier tolerates the absent column).
- Baseline DBs that have the column but hold NULL values stay valid (NULL = implicit
  v1 mode).

## 5. Writer design options

Compared options:

1. **Pass `lane_id` into `_insert_ledger_batch(...)`** — caller reads
   `paper_config.lane_id` once and passes it down. Explicit, testable, no extra
   per-insert query.
2. **Look up `lane_id` inside `_insert_ledger_batch(...)`** — self-contained but adds a
   query and hides control flow in a low-level helper.
3. **Separate wrapper / path for lane DBs** — highest divergence risk between baseline
   and lane writers.

**Recommended option:**

- Pass `lane_id: str | None` **explicitly** into `_insert_ledger_batch(...)`.
- Stamp only when `paper_config.lane_id` is non-NULL.
- Preserve baseline behavior when `lane_id is None` (INSERT shape unchanged).

This mirrors how `paper_engine_version` and `config_hash` already flow into the same
helper, and the writer already loads `paper_config` in the same transaction.

## 6. Verifier design

- Detect whether `ledger_batches.lane_id` column exists via `PRAGMA table_info`
  (no such column-detection helper exists in the verifier yet — it would be added).
- **v1 mode:**
  - Old DB without the column passes.
  - DB with the column and all-NULL batch lane IDs passes.
- **Lane mode** (`paper_config.lane_id` non-NULL):
  - Require the column exists.
  - Require all committed batch rows have
    `ledger_batches.lane_id == paper_config.lane_id`.
  - NULL or mismatched batch lane IDs **fail closed**.
- Natural hook: extend `_validate_batches`, which already cross-checks each batch's
  `paper_engine_version` / `config_hash` against `paper_config`.

## 7. Tests required (temp DBs only)

- Baseline DB still writes/verifies without lane stamping.
- New-lane DB batch insert stamps `lane_id`.
- Verifier passes when all batch lane IDs match `paper_config.lane_id`.
- Verifier fails when batch `lane_id` is NULL in a new-lane DB.
- Verifier fails when batch `lane_id` mismatches.
- Old v1 DB without `ledger_batches.lane_id` still verifies.
- No production path strings.
- No migrations / no ALTER.

## 8. Minimal future implementation slice

- Add nullable `ledger_batches.lane_id TEXT` to the `CREATE TABLE` definition only.
- Add `lane_id: str | None = None` parameter to `_insert_ledger_batch(...)`.
- Pass `lane_id` from the writer transaction after reading `paper_config.lane_id`.
- Add a verifier lane-mode batch consistency check in `_validate_batches`.
- Temp DB tests only.
- No `source_data_digest`.
- No live/shadow lane run.

## 9. Exclusions

Explicitly excluded from this plan and its future slice:

- production DB
- `/srv/qnty`
- VM / SSH
- systemd / timers / services
- migration / ALTER
- production `paper_pnl_v1`
- `source_data_digest`
- `pre_registration_hash` generation
- V2
- live / shadow lanes
- cross-lane reporter
- profitability or edge claims

## 10. Current verdict

- `EDGE_UNPROVEN`
- This is only a plan for batch identity consistency, **not** a strategy result. No
  profitability or edge claim is made or implied.
