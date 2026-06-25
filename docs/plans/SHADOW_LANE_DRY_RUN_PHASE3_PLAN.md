# Shadow Lane Dry Run — Phase 3 Plan

> **PLAN ONLY (docs).** No source code, no tests, no writer run, no shadow output dir, no
> VM/SSH, no production DB / `/srv/qnty/output/paper_pnl_v1`, no systemd/timers, no
> migration/ALTER, no live keys/orders. Strategy remains **EDGE_UNPROVEN**.

---

## 1. Purpose

First **real shadow-lane dry run** plan: a lane that consumes **real forward-observation
artifacts** but writes only to an **isolated shadow output dir + shadow DB**. The goal is to
prove one real cycle can:

1. initialize a separate lane (output dir + DB),
2. run exactly one writer invocation,
3. stamp `ledger_batches.lane_id`,
4. pass the read-only verifier.

No live trading. No orders. No production mutation. This is **not** an edge or profitability
claim — it exercises lane *plumbing* against real obs, nothing more.

---

## 2. Current state (landed + merged)

- lane identity model
- `config_hash_v2`
- additive lane DB fields
- `initialize_lane_database(...)`
- verifier lane identity validation
- ledger batch lane stamping
- verifier batch lane consistency
- lane config init helper / CLI (`scripts/qnty-paper-lane-init.py`)
- temp lane init E2E proof
- temp writer proof with one committed batch (`temp_lane_writer_proof_v0`)

**No real shadow lane has been run yet.**

---

## 3. Surface read findings

- Local main synced at `5b86165`; only `.claude/` untracked.
- Local `/srv/qnty` is **absent** → no production `paper_pnl_v1`, no production
  `paper_ledger.db`, no live `forward_obs_v1` locally.
- Repo `data/` contains **real** OHLCV/funding CSVs (`{SYMBOL}_8h_ohlcv.csv`,
  `{SYMBOL}_8h_funding.csv`) → usable as an explicit `--data-dir`.
- The only local observation artifact is `output/validation_v2/observation_log.json`
  (correct `per_bar_obs` shape, 500 bars).
- That obs log ends at **`2026-04-22T16:00:00`** (~2 months before now, 2026-06-25).
- Freshness gate (`quantbot/paper/freshness.py`, `quantbot/paper/config.py`) uses
  `max_bar_staleness_hours = 24` and `heartbeat_max_age_hours = 24`.
- **Therefore the local validation obs is stale** and would abort
  (`STALE_OBSERVATION`); it cannot drive a committed real shadow batch.
- The actual real shadow dry run requires **fresh** forward observations — likely from the
  VM — obtained via a **separately-approved read-only snapshot step** (no SSH in this plan).

---

## 4. Shadow lane identity

```
lane_id          = paper_pnl_null_shadow_v0
strategy_id      = matched_null_shadow_v0
strategy_version = 0.0.0-shadow
pre_registration_hash = null
```

This is a **dry-run matched-null lane, not V2**. The matched-null strategy emits empty
`active_symbols`, so the engine opens no positions and commits a flat-equity batch — it
validates init → write → stamp → verify against real obs **without** reproducing any V2
vol-normalized sizing/weights. `pre_registration_hash` stays `null` (existing sidecar
behavior; no generation). No `source_data_digest`, no V2, no cross-lane reporter.

---

## 5. Output location decision

- **Local path** is only possible if a fresh `forward_obs_v1` is copied locally read-only.
  Without fresh copied observations, the **local path is expected to block**
  (`STALE_OBSERVATION`) — the correct fail-closed outcome.
- **Future VM path — do NOT create yet:**
  - output dir: `/srv/qnty/output/paper_pnl_null_shadow_v0`
  - DB: `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db`
- Explicitly:
  - **do not create the VM path yet**
  - **do not run on VM yet**
  - **no systemd/timer yet**

---

## 6. Input / source-data strategy

- Source: existing `forward_obs_v1` artifacts.
- Use a **read-only snapshot/copy**; **never write into `forward_obs_v1`**.
- Do **not** use the production paper DB as input.
- Do **not** use exchange keys. Do **not** place orders.
- Writer requires:
  - `observation_log.json` (mandatory),
  - a `bar_decisions.jsonl` heartbeat **if present** (validated, age-gated at 24h),
  - an explicit `--data-dir`,
  - freshness within 24h.
- Avoid stale/future boundary issues by choosing an **on-grid** `forward_start_ts`
  (`{00,08,16}:00:00Z`) with **at least one eligible fresh bar** after it and within the
  24h window.

---

## 7. Future dry-run command shape (DO NOT RUN)

> Future commands only. Nothing here is executed as part of this plan.

```bash
# 1. verify clean main: HEAD == origin/main; only .claude/ untracked.
# 2. snapshot real forward obs READ-ONLY (separately-approved copy; never write forward_obs_v1):
#    cp <forward_obs_v1>/{observation_log.json,bar_decisions.jsonl} <SHADOW>/fwd_obs_snapshot/
# 3. initialize the separate lane (writer NOT run):
python scripts/qnty-paper-lane-init.py \
  --output-dir <SHADOW>/lane_out \
  --db-path    <SHADOW>/lane_out/paper_ledger.db \
  --lane-id paper_pnl_null_shadow_v0 \
  --strategy-id matched_null_shadow_v0 \
  --strategy-version 0.0.0-shadow \
  --forward-start-ts <ON_GRID_TS>
# 4. exactly ONE writer invocation, all env/args explicit:
QNTY_PAPER_OUTPUT_DIR=<SHADOW>/lane_out \
QNTY_PAPER_DB_PATH=<SHADOW>/lane_out/paper_ledger.db \
QNTY_FORWARD_OBS_DIR=<SHADOW>/fwd_obs_snapshot \
python scripts/qnty-paper-sqlite-accounting.py \
  --db-path         <SHADOW>/lane_out/paper_ledger.db \
  --forward-obs-dir <SHADOW>/fwd_obs_snapshot \
  --data-dir        <EXPLICIT_DATA_DIR> \
  --json | tee <SHADOW>/logs/writer.json
# 5. read-only verifier:
python scripts/qnty-paper-sqlite-verify.py \
  --db-path <SHADOW>/lane_out/paper_ledger.db --no-emit --json | tee <SHADOW>/logs/verify.json
# 6. read-only DB inspection: paper_config.lane_id; ledger_batches count + every
#    ledger_batches.lane_id; signal/equity/trades/funding/open_positions counts.
# 7. assert no production path touched.
# 8. assert no timer/service created.
# 9. create docs-only receipt.
```

---

## 8. Safety gates (fail-closed)

- shadow output dir must not equal `/srv/qnty/output/paper_pnl_v1`.
- shadow DB must not equal the production `paper_ledger.db`.
- `lane_id` must not be `paper_pnl_v1`.
- output dir must be absent/empty before init.
- DB path must not exist before init.
- writer command must include **all** explicit env/args (no default-path fallback).
- verifier must use `--no-emit`.
- no systemd/timer changes.
- no `ALTER TABLE`.
- no migration.
- no `.claude/` staging.
- no live keys / orders.

(The `init_lane` baseline-collision guards and `validate_lane_id` enforce the first five
gates programmatically.)

---

## 9. Acceptance criteria

**Ideal:**

- writer exits 0.
- verifier exits 0 / `OK`.
- at least one committed batch.
- every batch has `lane_id == paper_pnl_null_shadow_v0`.
- `paper_config.lane_id == paper_pnl_null_shadow_v0`.
- production DB untouched.
- no live orders.
- receipt committed.

(Null book ⇒ trades/fills/funding = 0; one equity + one signal snapshot.)

**Blocked (stop; write a blocked receipt/plan — do not improvise):**

- fresh forward observation source unavailable locally.
- data fixture/source unclear.
- freshness window cannot be met.
- any production-path collision risk.

Given current local state, the **local path is expected to be BLOCKED**; the real run
proceeds only via the separately-approved VM path.

---

## 10. Receipt plan

A future successful dry run creates `docs/plans/SHADOW_LANE_DRY_RUN_PHASE3_RECEIPT.md`,
recording:

- lane identity
- output dir / DB path
- command shape
- input source
- writer exit / status
- verifier status
- DB row counts
- `lane_id` stamping result
- no production mutation
- no timers / services
- no live trading / orders
- `EDGE_UNPROVEN`

---

## 11. Explicit exclusions

Excluded: production DB mutation; `/srv/qnty/output/paper_pnl_v1`; direct writes to
`forward_obs_v1`; VM/SSH execution in this plan; systemd/timers/services; migration/ALTER;
live exchange keys/orders; `source_data_digest`; `pre_registration_hash` generation beyond
existing `null`; V2; recurring shadow timers; cross-lane reporter; profitability or edge
claims.

---

## 12. Verdict

- `SHADOW_DRY_RUN_PLAN_READY`
- `EDGE_UNPROVEN`
- Real run **deferred** to a separately-approved VM / read-only-forward-obs step.
