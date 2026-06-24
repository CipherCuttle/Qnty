# Additive New-Lane DB Schema — Phase 3 Plan (Docs Only)

**Status:** PLAN ONLY — no schema/source/test/DB/writer/verifier changes in this phase.
**Strategy label:** `EDGE_UNPROVEN` (no profitability or edge claim is made anywhere in this document).
**Prior receipts:** `4a4b10a docs: add baseline v1 golden hash proof receipt`; plan output
`VERDICT: ADDITIVE_NEW_LANE_SCHEMA_PLAN_READY`.

---

## 1. Purpose

- Plan-only design for a future **additive** new-lane DB schema.
- Describes how **future new-lane DBs** may store lane identity (lane/strategy/version + a lane-aware
  config hash) alongside the existing per-DB accounting data.
- Must **not mutate the existing production baseline** (`paper_pnl_v1`) or change golden-locked v1
  config / `config_hash` / `bar_commit_id` behavior.
- This is **not an implementation**: it adds no columns, no code, no tests, no migration, no DB.

---

## 2. Current DB schema map

Source of truth: `_SCHEMA_SQL` in `quantbot/paper/db.py`.

- **`paper_config`** — singleton (`id = 1`), append-only/immutable. Holds the frozen accounting
  identity (equity/notional/leverage, fee/slippage/funding models, fill model, signal source,
  freshness params, `forward_start_ts`) **plus the frozen accounting `config_hash`**.
- **`ledger_batches`** — mutable per-run provenance. Holds `git_sha`, `paper_engine_version`, and
  `config_hash`, plus watermark/event-range bookkeeping updated on commit.
- **`signal_snapshots`** — per-bar source provenance, including `bar_commit_id` and
  `source_observation_digest` (and `source_observation_mtime`, `snapshot_id`, `run_ts`).
- **`DB_SCHEMA_VERSION = 1`** (defined in `quantbot/paper/db.py`; paper-contract `SCHEMA_VERSION = 1`).
- **`paper_config` currently has no lane identity columns.**
- **`ledger_batches` currently has no lane identity columns.**
- The **verifier currently requires exact `db_schema_version == DB_SCHEMA_VERSION`**
  (`quantbot/paper/sqlite_verify.py`, `_validate_identity`).

---

## 3. Current key hazard

- `config_hash_from_row(...)` in `quantbot/paper/db.py` currently rebuilds the hashed
  `schema_version` field **from the stored `db_schema_version`** column.
- Therefore a future storage **schema bump to 2 could accidentally change the v1 accounting hash**,
  because the stored `db_schema_version` value flows directly into the recomputed config payload.
- **Before any schema bump**, v1 accounting-hash reconstruction must be **decoupled from storage
  `db_schema_version`**.
- The future v1 accounting hash should use **`paper_contract_version`** (the paper-contract schema
  identity, still `1`), **not `db_schema_version`** (a storage concern), for the schema-identity field.
- **Golden-hash tests must remain green** across this change — the byte value of the v1 accounting
  hash must not move.

---

## 4. Additive schema design for new-lane DBs only

Planned **nullable** additive fields on `paper_config` (new-lane DBs only):

| Column | Type | Null | Meaning |
|---|---|---|---|
| `lane_id` | TEXT | NULL | New-lane identity; `NULL` ⇒ implicit v1 baseline. Never `"paper_pnl_v1"`. |
| `strategy_id` | TEXT | NULL | Strategy identity for the lane. |
| `strategy_version` | TEXT | NULL | String version (e.g. `"1"`, `"1.2.0"`). |
| `config_hash_v2` | TEXT | NULL | Lane-aware hash; separate from the frozen v1 `config_hash`. |
| `pre_registration_hash` | TEXT | NULL | Reserved; generation deferred (not implemented now). |

Planned/**deferred** fields on `ledger_batches` (design recorded, not added in the minimal slice):

| Column | Type | Null | Meaning |
|---|---|---|---|
| `lane_id` | TEXT | NULL | Per-batch lane stamp for future cross-batch consistency checks. |
| `source_data_digest` | TEXT | NULL | Reserved; per-run input identity, not implemented now. |

Record:

- `paper_config.config_hash` **remains the frozen v1 accounting hash** (unchanged meaning).
- `config_hash_v2` is a **separate** column; it never overwrites or feeds back into the v1 hash.
- **Null lane fields ⇒ v1 mode.**
- **Non-null lane fields ⇒ future v2 / new-lane mode.**

---

## 5. Backward compatibility

- **schema-1 DBs with no lane columns remain valid** (new columns are nullable and absent from
  required-table/column checks).
- The **old v1 DB identity path remains unchanged**.
- **v1 rows do not read new lane columns.**
- **old v1 `config_hash_from_row(...)` behavior must remain byte-identical** (same fields, same order,
  hashed `schema_version` stays `1` for v1 rows).
- The **production baseline remains untouched**.

---

## 6. New-lane creation only

- Additive columns are for **newly-created lane DBs only**.
- **No in-place ALTER against the production baseline.**
- **No migration command in this slice.**
- Any **future migration tool must refuse the production baseline** unless explicitly dry-run reviewed.

---

## 7. `DB_SCHEMA_VERSION` strategy

- Future new-lane DBs **likely use `DB_SCHEMA_VERSION = 2`**.
- The verifier must eventually **read both schema 1 and schema 2**.
- **Schema 2 is required only when lane fields are present.**
- **Schema 1 means old baseline mode.**
- The **schema bump must not change the v1 accounting hash** (see §3 decoupling precondition).

---

## 8. Future writer/verifier wiring

Plan only — **no wiring now**:

- The **writer** later populates lane fields **only on new lane DB creation** (validated
  `LaneIdentity` + frozen v1 hash → `config_hash_v2`), stamping `db_schema_version = 2`. The baseline
  creation path is unchanged.
- The **verifier** later **dual-modes**:
  - **absent/null lane fields → existing v1 checks** (zero behavioral change),
  - **present lane fields → validate `LaneIdentity`, recompute `config_hash_v2`, check lane
    consistency** (e.g. all batches agree with `paper_config.lane_id`).

---

## 9. Future tests required

(Temp DBs only; no production path strings; no migration on any real/production DB.)

- schema-1 old DB still validates as v1 baseline.
- schema-2 temp DB has nullable lane columns.
- golden v1 config hash still passes.
- `config_hash_from_row(...)` decoupling preserves the golden hash.
- new-lane `paper_config` stores `lane_id`, `strategy_id`, `strategy_version`, `config_hash_v2`.
- invalid `lane_id` rejected (charset / empty / `..` / baseline impersonation).
- null lane fields do not break the old verifier.
- no production path strings.
- no migration on production DB.

---

## 10. Minimal future implementation slice

- Add schema constants / create-table columns for **new DBs only** (the nullable `paper_config`
  lane fields).
- Add `config_hash_from_row` **decoupling** so the v1 accounting hash uses `paper_contract_version`.
- Tests use **temp DB only**.
- **No writer/verifier behavior wiring** unless strictly required for schema tests.
- Baseline golden tests must remain **green**.
- Full suite must **pass**.
- **Defer** ledger-batch lane stamping, `source_data_digest`, `pre_registration_hash`, and reporter
  tables.

---

## 11. Exclusions

Explicitly excluded from this slice (this document mutates nothing of the kind):

- production DB
- `/srv/qnty`
- VM / SSH
- systemd / timers
- in-place ALTER / migration
- production baseline mutation
- writer/verifier wiring
- V2
- live/shadow lanes
- `source_data_digest` implementation
- `pre_registration_hash` implementation
- lane registry table
- lane comparison table
- cross-lane reporter
- profit / edge claims
