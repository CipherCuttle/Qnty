# Verifier Dual-Mode Lane Identity Validation — Phase 3 Plan (Docs Only)

**Status:** PLAN ONLY — no verifier/source/test/DB changes in this phase.
**Strategy label:** `EDGE_UNPROVEN` — no profitability or edge claim is made anywhere in this document.
**Prior receipt:** `6f62658 docs: add writer new lane init helper receipt`; plan output
`VERDICT: VERIFIER_DUAL_MODE_PLAN_READY`.

---

## 1. Purpose

- Plan-only design for **verifier dual-mode lane identity validation**.
- Goal: let the verifier **distinguish old v1 baseline DBs from future new-lane DBs** and validate
  each appropriately.
- It is **not an implementation**: no verifier code, no tests, no DB, no migration is added here.

---

## 2. Current verifier identity path

(`_validate_identity` in `quantbot/paper/sqlite_verify.py`.)

- The verifier reads `paper_config WHERE id = 1`.
- It currently enforces `db_schema_version`, `paper_contract_version`, `paper_engine_version`, and
  `baseline_label` (all exact-equality checks).
- It recomputes the v1 hash using `config_hash_from_row(...)` and compares it to the stored
  `config_hash`.
- It **currently ignores the lane fields** if present — a new-lane DB passes as if it were v1, with
  `config_hash_v2` never validated.
- This **silent gap is what the future dual-mode verifier must close**.

---

## 3. Mode detection decision

- Detect mode by the **lane fields**, especially `paper_config.lane_id`.
- **Do not** detect mode by `db_schema_version`.
- **v1 mode:** lane fields absent or all NULL.
- **v2/new-lane mode:** `lane_id` non-null (or **any** lane identity field non-null).
- The **production baseline remains v1 mode** (it has no/NULL lane fields).

---

## 4. v1 mode behavior

- Run the existing checks **exactly as today**.
- The **golden v1 config hash behavior is unchanged**.
- Old DBs with no lane columns **pass**.
- DBs with lane columns all NULL **pass**.
- Any **partial non-null lane field must not silently degrade to v1** (it is routed to v2 mode and
  then fails closed if incomplete — see §6).

---

## 5. v2/new-lane behavior

- Run **all existing v1 accounting checks first** (engine/contract/`baseline_label`/`config_hash`
  recompute) — the v1 accounting config is still the shared frozen contract.
- Validate `LaneIdentity(lane_id, strategy_id, strategy_version)` (reject-only model).
- Recompute `config_hash_v2(stored config_hash, identity)`.
- Compare the recomputed value to the stored `paper_config.config_hash_v2`.
- Require `pre_registration_hash` **NULL for now** (generation is deferred).
- **Do not validate `ledger_batches.lane_id`** yet (batch stamping is deferred — §8).

---

## 6. Fail-closed states

- `lane_id` present but `strategy_id` missing → **fail**.
- `strategy_id` present but `lane_id` missing → **fail**.
- `strategy_version` missing → **fail**.
- `config_hash_v2` missing in v2 mode → **fail**.
- invalid `lane_id` (charset / empty / `..`) → **fail**.
- baseline-impersonating `lane_id` (`paper_pnl_v1`) → **fail**.
- `config_hash_v2` mismatch (recomputed ≠ stored) → **fail**.
- non-null `pre_registration_hash` for now → **fail**.
- partial lane columns → **fail**.
- old v1 DB with no lane columns → **pass**.

Discriminator rule: **any** of `{lane_id, strategy_id, strategy_version, config_hash_v2}` non-null
routes to v2 mode, where **all** of them are required — so mixed states fail closed instead of
silently degrading to v1.

---

## 7. DB schema version strategy

- Keep the exact `db_schema_version == DB_SCHEMA_VERSION` check for now.
- Current new-lane DBs still use **schema version 1** (no schema bump in the groundwork).
- Mode detection by **lane fields** (not schema version) avoids making the production baseline invalid.
- **No schema bump in this phase.**

---

## 8. Ledger batch decision

- **Do not validate `ledger_batches.lane_id`** yet.
- Batch lane stamping **does not exist** (the writer inserts no `lane_id` on batches).
- Per-batch lane consistency belongs to a **later phase paired with writer batch stamping** (producer
  and check land together).
- `source_data_digest` remains **out of scope**.

---

## 9. Future tests required

(Temp DB / synthetic only.)

- old v1 temp DB still verifies.
- new-lane temp DB verifies with correct `LaneIdentity` and `config_hash_v2`.
- missing `strategy_id` fails.
- missing `strategy_version` fails.
- missing `config_hash_v2` fails.
- invalid `lane_id` fails.
- baseline-impersonating lane id fails.
- `config_hash_v2` mismatch fails.
- non-null `pre_registration_hash` fails.
- partial lane fields fail.
- no production path strings.
- no migration / ALTER behavior.

---

## 10. Minimal future implementation slice

- Modify the **verifier identity validation only**.
- Add verifier tests over **temp DBs only**.
- **No** writer runtime loop changes.
- **No** batch stamping.
- **No** `source_data_digest`.
- **No** `pre_registration_hash` generation.
- Baseline golden tests + full suite must **pass**.

---

## 11. Exclusions

Explicitly excluded from this slice (this document mutates nothing of the kind):

- production DB
- `/srv/qnty`
- VM / SSH
- systemd / timers
- migration / ALTER
- production baseline mutation
- writer runtime loop changes
- ledger batch lane stamping
- `source_data_digest`
- `pre_registration_hash` generation
- V2
- live / shadow lanes
- cross-lane reporter
- live trading / exchange keys / real orders
- profitability or edge claims
