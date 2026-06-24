# Writer New-Lane Initialization — Phase 3 Plan (Docs Only)

**Status:** PLAN ONLY — no writer/source/test/DB/verifier changes in this phase.
**Strategy label:** `EDGE_UNPROVEN` — no profitability or edge claim is made anywhere in this document.
**Prior receipt:** `5e70f78 docs: add additive lane schema groundwork receipt`; plan output
`VERDICT: WRITER_NEW_LANE_INIT_PLAN_READY`.

---

## 1. Purpose

- Plan-only design for a future **writer new-lane initialization** path.
- Goal: initialize a **separate new-lane DB** carrying a validated lane identity.
- It must **not mutate the production baseline** (`paper_pnl_v1`).
- It is **not an implementation**: no code, no tests, no DB, no migration is added here.

---

## 2. Current writer/init path

- `initialize_database(db_path, config)` (`quantbot/paper/db.py`) creates the singleton
  `paper_config` row and the `ledger_state` row. The INSERT lists explicit columns only, so the
  additive lane columns are left NULL for the baseline.
- `paper_config.json` is written by `write_config_once(...)` (`quantbot/paper/config.py`) —
  write-once, refuses overwrite without `force`.
- The writer cross-checks the filesystem config vs the DB config using the tuple
  `(forward_start_ts, config_hash)` (`quantbot/paper/sqlite_writer.py`); a mismatch is a
  `CONFIG_ERROR`.
- Ledger batches are inserted by `_insert_ledger_batch(...)` (`quantbot/paper/sqlite_writer.py`);
  there is **no `lane_id`** on batches today.
- The current writer is **implicitly one baseline lane** (it loads config from the baseline output
  dir and requires the baseline label / engine version).
- Env vars select paths:
  - `QNTY_PAPER_OUTPUT_DIR`
  - `QNTY_PAPER_DB_PATH`

---

## 3. New-lane initialization goal

The future path should create a **separate** new-lane DB with:

- a validated `LaneIdentity`
- the frozen v1 accounting `config_hash` (consumed opaque, never rebuilt)
- a computed `config_hash_v2`
- a nullable `pre_registration_hash` (left NULL; generation deferred)
- a separate output dir
- a separate DB path
- **zero production-baseline mutation**

---

## 4. API design decision

Options compared:

1. **Extend `initialize_database(..., lane_identity=None)`** — **risky**: it overloads the
   baseline-critical function, routing every existing caller/test through new branching and
   endangering the golden/baseline path.
2. **Wrapper that calls `initialize_database` then updates lane columns** — **rejected**:
   `paper_config` is append-only protected (UPDATE triggers `RAISE(ABORT)`), so a post-hoc UPDATE
   is both impossible and exactly the mutation pattern we forbid.
3. **Sibling `initialize_lane_database(...)`** — **recommended**.

Why the sibling is recommended:

- **Safer for the baseline path** — the baseline `initialize_database` stays byte-for-byte
  unchanged, so the golden tests and existing suite are structurally insulated.
- **Inserts lane fields at creation time** (INSERT, not UPDATE).
- **Avoids post-hoc mutation** of the append-only `paper_config`.
- **Gives a natural home for the path/lane safety gates** (path refusals, `lane_id` refusal) without
  entangling them in the baseline initializer.

---

## 5. Config file strategy

- Keep `paper_config.json` (the v1 **accounting** config) **byte-compatible** — payload and
  `config_hash` unchanged.
- **Do not fold lane identity into the v1 hash payload** (`config_hash_v2` consumes the v1 hash as an
  opaque string).
- Consider a separate **`lane_identity.json`** (the validated `LaneIdentity` fields).
- Consider a separate **`lane_config_v2.json`** (`config_hash_v2` + the v1 hash it derives from).
- New-lane files live **only under the new-lane output dir**.
- The baseline `paper_config.json` is **never mutated**.

---

## 6. Writer safety gates

Future writer init must check:

- output dir **must not equal** the production baseline output dir.
- DB path **must not equal** the production baseline DB path.
- `lane_id` **must not be `paper_pnl_v1`** (already enforced by `LaneIdentity` / `validate_lane_id`).
- lane output dir / DB path **must be new**.
- the DB file **must not already exist** (`initialize_database` already raises on an existing path).
- `config_hash_v2` **recomputes** from the v1 hash + `LaneIdentity`.
- baseline golden tests **remain green**.
- **no writer run touches the production baseline**.

---

## 7. Ledger batch stamping decision

- **Defer `ledger_batches.lane_id`.**
- **Defer `source_data_digest`.**
- Batch stamping belongs to a **later writer/verifier phase**.
- Reason: batch stamping only matters once a new-lane writer **commits batches** and the verifier
  checks **per-batch lane consistency**; both are out of scope here.
- This phase is **only initialization-time identity on `paper_config`**.

---

## 8. Future tests required

(Temp DB / synthetic only.)

- temp new-lane DB initializes with lane fields **populated**.
- temp baseline DB still initializes with lane fields **NULL**.
- production baseline `lane_id` (`paper_pnl_v1`) **refused**.
- invalid `lane_id` **refused**.
- `config_hash_v2` **stored and recomputes**.
- existing baseline golden config hash **unchanged**.
- new-lane output dir / DB path **must differ from baseline defaults**.
- no production path strings.
- no migration / ALTER behavior.

---

## 9. Minimal future implementation slice

- Add the sibling `initialize_lane_database(...)`.
- Use **temp DB tests only**.
- Populate lane fields into `paper_config` **at INSERT time only**.
- **No** ledger-batch stamping.
- **No** verifier dual-mode.
- **No** live writer run.
- **No** production paths.
- Full suite must **pass**.

---

## 10. Exclusions

Explicitly excluded from this slice (this document mutates nothing of the kind):

- production DB
- `/srv/qnty`
- VM / SSH
- systemd / timers
- migration / ALTER
- production baseline mutation
- live / shadow lanes
- `source_data_digest`
- `pre_registration_hash` generation
- ledger batch lane stamping
- verifier dual-mode
- V2
- cross-lane reporter
- live trading / exchange keys / real orders
- profitability or edge claims
