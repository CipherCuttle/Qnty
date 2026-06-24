# Additive Lane Schema Groundwork — Phase 3 Receipt

**Commit:** `e093ea1 Add additive lane schema groundwork` (pushed to `origin/main`).
**Prior receipt:** `e741cf8 docs: add additive new lane db schema plan`.
**Strategy label:** `EDGE_UNPROVEN` — no profitability or edge claim is made anywhere in this document.

---

## 1. Purpose

- This slice implemented **additive schema groundwork** and **v1 accounting-hash decoupling**.
- It is **not** writer/verifier wiring.
- It is **not** a migration.
- It **does not touch production DBs**.

---

## 2. Files changed

- `quantbot/paper/db.py`
- `tests/test_paper_additive_lane_schema.py`

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

## 4. Schema groundwork added

Five **nullable** additive columns were added to the `paper_config` CREATE TABLE for
**newly-created DBs only**:

- `lane_id`
- `strategy_id`
- `strategy_version`
- `config_hash_v2`
- `pre_registration_hash`

Record:

- All five are **nullable** (no `NOT NULL`, no default).
- **Baseline rows leave them NULL** (a NULL `lane_id` means implicit v1 mode).
- **No writer population yet.**
- **No verifier dual-mode yet.**
- **No ledger-batch lane stamping yet.**

---

## 5. Critical decoupling

- `config_hash_from_row(...)` now reconstructs the v1 accounting config using
  **`paper_contract_version`** for the schema-identity field.
- It **falls back to `db_schema_version`** for legacy/synthetic rows that predate the
  `paper_contract_version` column.
- This **prevents a future storage-schema bump** (e.g. `db_schema_version` 1 → 2 for
  new-lane DBs) from **silently changing the v1 accounting hash**.
- The **golden v1 hash remains unchanged** (byte-for-byte).

---

## 6. DB / version decisions

- `DB_SCHEMA_VERSION` **remains 1** in this slice.
- **No schema bump yet.**
- **No migration.**
- **No ALTER.**
- New columns are **only part of newly-created DB schema**.
- The **existing production baseline is not modified**.

---

## 7. Tests covered

(`tests/test_paper_additive_lane_schema.py` — temp/synthetic only.)

- schema-1 synthetic row still produces the golden hash.
- legacy row missing `paper_contract_version` still produces the golden hash via fallback.
- synthetic row with `db_schema_version=2` and `paper_contract_version=1` still produces the
  **same** golden hash.
- temp initialized DB contains the nullable lane columns.
- default baseline `paper_config` row has lane fields NULL.
- recomputation from a fresh baseline DB row remains golden.
- no production paths.
- no migration / ALTER behavior.

---

## 8. Verification results

- additive lane schema tests: **8 passed**.
- golden + lane suite: **34 passed**.
- full suite: **1207 passed**.
- `git diff --check`: **clean**.
- edge/live grep: **no hits**.
- implementation/prod grep: **only guardrails / pre-existing lines**.
- `.claude/` **remained untracked**.

---

## 9. Scope exclusions

- no production DB
- no `/srv/qnty`
- no VM / SSH
- no systemd / timers
- no ALTER / migration
- no production baseline mutation
- no writer lane population
- no verifier dual-mode lane validation
- no V2
- no live / shadow lanes
- no `source_data_digest`
- no `pre_registration_hash` generation
- no cross-lane reporter
- no live trading / keys / orders
- no profitability or edge claims

---

## 10. Current verdict

- `EDGE_UNPROVEN`.
- This proves **schema groundwork and v1 hash preservation only**, not strategy quality.

---

## 11. Next recommended phase

- **Plan-only** writer new-lane initialization path.
- Do **not** implement writer wiring yet until the plan is approved.
- Keep verifier dual-mode as a **separate later phase** unless unavoidable.
