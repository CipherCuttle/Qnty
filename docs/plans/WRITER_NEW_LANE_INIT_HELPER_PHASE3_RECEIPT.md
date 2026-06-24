# Writer New-Lane Init Helper — Phase 3 Receipt

**Commit:** `b589368 Add new lane database initialization helper` (pushed to `origin/main`).
**Prior receipt:** `c9f24a6 docs: add writer new lane init plan`.
**Strategy label:** `EDGE_UNPROVEN` — no profitability or edge claim is made anywhere in this document.

---

## 1. Purpose

- This slice added the sibling `initialize_lane_database(...)` helper.
- It initializes **separate new-lane DBs** with lane identity.
- It is **not** writer runtime wiring.
- It is **not** verifier dual-mode.
- It is **not** a live/shadow lane.

---

## 2. Files changed

- `quantbot/paper/db.py`
- `tests/test_paper_initialize_lane_database.py`

---

## 3. Files intentionally not changed

- `quantbot/paper/config.py`
- `quantbot/paper/sqlite_writer.py`
- `quantbot/paper/sqlite_verify.py`
- `quantbot/paper/engine.py`
- ops / systemd files
- production configs
- VM files
- production DB / output

---

## 4. Helper design

- Added a **sibling** `initialize_lane_database(...)`.
- Did **not** overload the baseline `initialize_database(...)`.
- The baseline initializer remains **untouched** (db.py diff is additive-only: 121 insertions, 0
  deletions).
- Lane fields are inserted at `paper_config` **creation time** (initial INSERT).
- **No post-hoc UPDATE.**
- The **append-only `paper_config` model is preserved** (an UPDATE would `RAISE(ABORT)`).

---

## 5. Stored lane fields

The new-lane `paper_config` row stores:

- `lane_id`
- `strategy_id`
- `strategy_version`
- `config_hash_v2`
- `pre_registration_hash = NULL`

---

## 6. Identity / hash behavior

- Uses a validated `LaneIdentity`.
- Rejects a baseline-impersonating `lane_id` (`paper_pnl_v1`) via existing model behavior.
- Computes `config_hash_v2` from the frozen v1 `config_hash` + `LaneIdentity` (v1 consumed opaque).
- `config_hash_from_row(...)` over the lane DB still returns the **v1 accounting hash**.
- The **v1 golden hash remains unchanged**.

---

## 7. Safety gates

- Existing DB path **refused** (`FileExistsError`).
- Supplied baseline DB path **refused** (`ValueError`).
- Invalid lane identity **refused** (model construction).
- Baseline-impersonating `lane_id` **refused** (model construction).
- Temp DB tests only.
- No production path usage.
- No migration / ALTER.

---

## 8. Tests covered

(`tests/test_paper_initialize_lane_database.py` — temp/synthetic only.)

- lane DB stores lane fields.
- stored `config_hash_v2` recomputes (from stored v1 hash + `LaneIdentity`).
- `pre_registration_hash` is NULL.
- baseline DB still has NULL lane fields.
- existing path refusal.
- baseline path refusal.
- invalid identity refusal.
- baseline-impersonation refusal.
- lane DB `config_hash_from_row` returns the v1 accounting hash.

---

## 9. Verification results

- helper tests: **9 passed**.
- regression group: **41 passed**.
- full suite: **1216 passed**.
- `git diff --check`: **clean**.
- db.py diff **additive only** (121 insertions, 0 deletions).
- **no `ALTER TABLE`**.
- grep hits: **only guardrails / pre-existing lines / rejected lane-id guard**.
- `.claude/` **remained untracked**.

---

## 10. Scope exclusions

- no production DB
- no `/srv/qnty`
- no VM / SSH
- no systemd / timers
- no migration / ALTER
- no production baseline mutation
- no writer runtime loop changes
- no verifier dual-mode
- no ledger batch lane stamping
- no `source_data_digest`
- no `pre_registration_hash` generation
- no V2
- no live / shadow lanes
- no cross-lane reporter
- no live trading / keys / orders
- no profitability or edge claims

---

## 11. Current verdict

- `EDGE_UNPROVEN`.
- This proves only **safe initialization of separate lane DB identity**, not strategy quality.

---

## 12. Next recommended phase

- **Plan-only** verifier dual-mode lane identity validation.
- Do **not** implement verifier changes until the plan is approved.
- Keep batch lane stamping **deferred** unless the plan proves it is required.
