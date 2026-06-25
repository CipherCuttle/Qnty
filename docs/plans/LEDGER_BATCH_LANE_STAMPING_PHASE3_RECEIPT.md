# Ledger Batch Lane Stamping — Phase 3 Implementation Receipt

Strategy label: `EDGE_UNPROVEN`

> Docs-only receipt for the minimal ledger batch lane stamping slice
> (implementation commit `4636377 Add ledger batch lane stamping`). It records what
> shipped and how it was verified. No source or test code is changed by this receipt.

## 1. Purpose

- This slice implemented **minimal ledger batch lane stamping**.
- Goal: new-lane DB committed batches carry `ledger_batches.lane_id`.
- The verifier checks batch lane consistency in lane mode.
- This is **not** `source_data_digest`.
- This is **not** a live/shadow lane run.

## 2. Files changed

- `quantbot/paper/db.py`
- `quantbot/paper/sqlite_writer.py`
- `quantbot/paper/sqlite_verify.py`
- `tests/test_paper_ledger_batch_lane_stamping.py`

## 3. Files intentionally not changed

- production configs
- VM files
- systemd / timer files
- production DB / output
- `source_data_digest` code
- `pre_registration_hash` generation
- V2 / live / shadow lane runner code

## 4. Schema change

- Added nullable `ledger_batches.lane_id TEXT` to the `CREATE TABLE` for newly-created
  DBs only.
- `DB_SCHEMA_VERSION` unchanged.
- No ALTER.
- No migration.
- Old DBs without the column remain verifiable.

## 5. Writer change

- `_insert_ledger_batch(...)` gained an optional `lane_id: str | None` parameter.
- Baseline path with `lane_id is None` preserves legacy behavior and works on DBs that
  do not have the column (the INSERT never references `lane_id`).
- Lane DB path stamps `lane_id` when `paper_config.lane_id` is non-NULL.
- The call site explicitly reads `paper_config.lane_id` from the in-transaction DB
  config row (`db_config.get("lane_id")`) and passes it down.
- No engine / strategy / runtime behavior changed.

## 6. Verifier change

- Added batch lane column detection via `PRAGMA table_info` (`_column_exists`).
- **v1 mode** (`paper_config.lane_id` NULL or its column absent):
  - old DB without `ledger_batches.lane_id` passes.
  - DB with the column and all-NULL lane IDs passes.
  - an unexpected non-NULL batch lane ID in v1 mode fails closed.
- **Lane mode** (`paper_config.lane_id` non-NULL):
  - requires the `ledger_batches.lane_id` column.
  - every committed batch row must equal `paper_config.lane_id`.
  - a NULL or mismatched batch lane ID fails closed.
- Existing batch checks remain unchanged:
  - config hash consistency
  - engine version consistency
  - watermark / event checks

## 7. Tests covered

- baseline DB still writes/verifies without lane stamping.
- new-lane DB batch insert stores `lane_id`.
- verifier passes when all lane-mode batch lane IDs match.
- verifier fails when lane-mode batch `lane_id` is NULL.
- verifier fails when lane-mode batch `lane_id` mismatches.
- old v1 DB without `ledger_batches.lane_id` column still verifies.
- v1 DB with the batch lane column and NULL values verifies.
- v1 DB with a non-NULL batch `lane_id` fails closed.
- existing verifier lane identity tests still pass.
- existing golden config hash tests still pass.

## 8. Verification results

- `tests/test_paper_ledger_batch_lane_stamping.py`: **10 passed**.
- targeted regressions: **109 passed**.
- full suite: **1242 passed**.
- `git diff --check`: clean.
- no ALTER TABLE.
- no production mutation.
- no VM / systemd / network introduced.
- grep hits classified as guardrails / pre-existing only.
- `.claude/` remained untracked.

## 9. Diff note

- The implementation commit `4636377` changed **4 files**, **390 insertions(+)**,
  **11 deletions(-)**.
- The deletions were **reviewed**: they are confined to the in-place rewrite of
  `_insert_ledger_batch(...)` (replacing the single original INSERT with the
  `lane_id is None` baseline branch plus the lane branch) and the verifier's
  `_validate_batches` return path (which now also extends with the lane-stamping check).
  **No safety check and no baseline-compatibility behavior was removed** — the baseline
  INSERT shape is preserved byte-for-byte in the `lane_id is None` branch, and all
  pre-existing batch checks (config hash, engine version, watermark/event) remain.
- Baseline compatibility is covered by focused tests (baseline insert leaves `lane_id`
  NULL; legacy DB without the column verifies; v1 DB with all-NULL column verifies) and
  by the full suite (**1242 passed**).

## 10. Scope exclusions

Explicitly excluded:

- production DB
- `/srv/qnty`
- VM / SSH
- systemd / timers / services
- migration / ALTER
- production `paper_pnl_v1`
- `source_data_digest`
- `pre_registration_hash` generation
- V2
- live / shadow lane runs
- cross-lane reporter
- live trading / keys / orders
- profitability or edge claims

## 11. Current verdict

- `EDGE_UNPROVEN`
- This proves batch identity consistency only, **not** strategy quality.

## 12. Next recommended phase

- Open a PR for this implementation + receipt.
- After merge, a **plan-only** lane config file / writer launch wrapper can be
  considered.
- Do **not** run live/shadow lanes yet.
