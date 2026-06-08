# ADR 0001 — Migrate paper PnL v1 from JSONL + snapshot verifier to a SQLite/WAL ledger

- **Status:** Accepted (Phase 1 substrate implemented; Phase 2 writer implemented 2026-06-08; Phase 3 read-only verifier implemented 2026-06-08; **Phase 3.5 writer/verifier correctness fixes implemented 2026-06-08**). Runtime code implemented in `quantbot/paper/db.py`, `quantbot/paper/sqlite_writer.py`, `quantbot/paper/sqlite_verify.py` and tested in `tests/test_paper_sqlite.py`, `tests/test_paper_sqlite_writer.py`, `tests/test_paper_sqlite_verify.py`. The SQLite verifier is a **parallel** implementation (it does not replace the JSONL verifier) and is **not** the VM default path. **Phase 3 is implemented but NOT approved to proceed to Phase 4 until the Phase 3.5 fixes (§ 8d) pass adversarial review; writer exit/restart correctness is now a prerequisite for Phase 4. No deployment readiness is claimed.**
- **Date:** 2026-06-08
- **Scope:** `quantbot/paper/`, `scripts/qnty-paper-*`, `scripts/paper_*`,
  `ops/bin/qnty-paper-pnl-*.sh`, `docs/paper_pnl_v1_schema.md`,
  `docs/ops/VM_90D_RUNBOOK.md`.
- **Supersedes for paper PnL:** the JSONL + frozen-snapshot verifier + trusted-OK-baseline
  + multi-file provenance publication authority model documented in
  `docs/paper_pnl_v1_schema.md` §5/§5a/§10/§11. That model stays in effect until the SQLite
  path is implemented and proven (Phases 1–5 below); this ADR only fixes the target design.

---

## 1. Context

Paper PnL v1 (`paper_pnl_v1`) is a strictly additive simulation layer that converts the
read-only shadow observer's forward signals into deterministic simulated fills, trades,
positions, equity, and funding. It is a **fixed-notional active-symbol baseline, not a
faithful Package V2 vol-normalized reproduction**, it is **not live trading**, and a green
paper result proves nothing about real-money profitability or deployment readiness. Those
disclaimers carry forward unchanged.

The current persistence design is append-only JSONL ledgers plus a homemade authority stack:
a runner that writes `RUNNING`/`OK` summaries, a frozen-snapshot copier, a read-only verifier
over that snapshot, a trusted-OK baseline JSON, and a multi-file provenance/receipt publication
protocol (see `docs/paper_pnl_v1_schema.md` §5, §5a, §10, §11).

A hardening loop against adversarial review (Codex) repeatedly surfaced classes of holes that
are **structural to the JSONL + multi-file-authority design**, not one-off bugs:

- **TOCTOU** between freshness check, ledger read, and write.
- **Stale `OK`** surviving a failed/partial publication of a later result.
- **Mutable-file** windows: append-only files are still byte-mutable between steps.
- **Digest / commit-ordering** ambiguity across separate files.
- **Wrapper** gaps: a wrapper certifying an old ledger after an accounting failure.
- **Authority-model** confusion: which file is the source of truth, and when.

Each fix added another guard file or ordering rule, increasing the surface area rather than
shrinking it. The decision is to stop patching the JSONL/snapshot/baseline machinery and move
the durability + atomicity + single-writer + read-consistency guarantees into SQLite, where
they are primitives rather than hand-rolled protocols.

---

## 2. Decision

Replace the JSONL + snapshot-verifier + trusted-baseline + provenance-publication machinery
with a **single SQLite/WAL database** using **typed normalized tables plus a minimal ordered
event index**, a **transactional writer**, and a **read-only / query-only verifier**.

- **One logical DB file** per output family:
  - default path `/srv/qnty/output/paper_pnl_v1/paper_ledger.db`
  - sidecars `paper_ledger.db-wal` and `paper_ledger.db-shm` are **SQLite-managed** (do not
    hand-edit, do not copy independently — see §10 backup rules).
- **`QNTY_PAPER_DB_PATH`** is the single canonical path env var, used by init, accounting,
  verifier, and wrapper. Default as above.
- **`DB_SCHEMA_VERSION = 1`.**
- **Paper contract v1 is unchanged** (`schema_version: 1`, `baseline_label:
  fixed_notional_active_symbols_paper_v1`).
- **Paper engine version bumps to `0.3.0`** to mark the storage/authority change.
- PRAGMAs / connection settings:
  - `PRAGMA journal_mode=WAL`
  - `PRAGMA synchronous=FULL`
  - `PRAGMA foreign_keys=ON`
  - `STRICT` tables (requires SQLite **3.37+**; init fails loudly on older versions)
  - writer transactions use `BEGIN IMMEDIATE`
  - verifier opens the DB with URI `mode=ro` **and** sets `PRAGMA query_only=ON`
- The writer commits **complete batches transactionally**. The verifier is **read-only and
  query-only**.
- **Removed by this design** (in later phases): homemade snapshot copier, trusted-OK baseline
  JSON, and the multi-file OK publication protocol.

### Explicitly NOT claimed

No public tamper-proof / security claims. No external audit guarantee. No cryptographic
signing. No claim of faithful Package V2 volnorm replication. No live-trading authorization.

---

## 3. Threat model (authoritative for the SQLite design)

### In scope (the design must defend against these)

- accidental corruption
- crash mid-write
- partial writes
- accidental concurrent writer/verifier
- stale config
- malformed / corrupt ledger state
- internal accounting inconsistency

### Out of scope (explicitly not defended against)

- a malicious root/user with filesystem write access
- adversarial tamper-proof *public* evidence
- external audit guarantees
- cryptographic signing
- full independent OHLCV mark re-derivation (unless implemented in a later phase)
- live-trading approval
- profitability proof
- Package V2 volnorm proof

### What the SQLite paper ledger proves

- local crash safety
- transaction atomicity
- single-writer behavior
- schema validity
- internal accounting consistency
- fixed-notional active-symbol baseline simulation **only**

### What it does NOT prove

- tamper resistance
- external auditability
- observer correctness
- real-money profitability
- deployment readiness
- live-trading readiness
- faithful Package V2 volnorm PnL
- independent OHLCV mark / unrealized / exposure re-derivation (unless implemented later)

---

## 4. Schema (DB_SCHEMA_VERSION = 1)

All tables are `STRICT`. Foreign keys on. Numeric columns are typed; timestamps stored as
canonical UTC ISO-8601 strings (matching the existing observer/observation contract). No
column accepts `NaN`/`inf`; integer columns reject `bool`.

### 4.1 `paper_config` — DB identity / config (singleton, immutable)

Singleton row (enforced by a fixed primary key, e.g. `id = 1`) holding the flattened, typed
config that defines the output contract:

- `db_schema_version`
- `paper_contract_version`
- `paper_engine_version`
- `baseline_label`
- `forward_start_ts`
- `initial_equity_usd`
- `notional_usd`
- `leverage`
- fee model fields
- slippage model fields
- funding model fields
- fill model
- signal source
- freshness fields
- `created_at`
- `config_hash`

Immutability is enforced with `BEFORE UPDATE` and `BEFORE DELETE` triggers that raise. The
config is validated against the exact v1 contract on every open (versions, baseline label,
finite/typed numbers, hash match).

### 4.2 `ledger_batches` — transaction batches (append-only)

One row per committed accounting transaction; the foreign-key anchor for all events:

- `batch_id`
- `created_at`
- `started_at` / `committed_at` (if useful)
- `git_sha`
- `prior_watermark_bar_ts`
- `new_watermark_bar_ts`
- `first_event_seq`
- `last_event_seq`
- `event_count`
- `committed_bar_count`
- `paper_engine_version`
- `config_hash`

Append-only (insert-only triggers; no update/delete).

### 4.3 `ledger_events` — minimal ordered event index (append-only)

- `seq INTEGER PRIMARY KEY AUTOINCREMENT`
- `batch_id` (FK → `ledger_batches`)
- `event_type`
- `event_key`
- `recorded_at`
- `bar_ts`
- `symbol`
- `prev_seq`

Constraints: fixed `event_type` check constraint; unique event identity
(`(event_type, event_key)` and/or per-bar uniqueness); insert-only triggers; indexes on
`event_type`, `bar_ts`, `symbol`, `batch_id`.

**Ordering invariant:** `prev_seq` is the durable ordering link. The verifier checks that
`prev_seq` points to the immediately preceding observed event. **Numeric `seq` gaps alone are
NOT corruption** — SQLite `AUTOINCREMENT` does not guarantee gap-free numbering (rolled-back
inserts can consume values). The chain, not the integer spacing, is authoritative.

**Canonical event insertion order** (deterministic, for reproducible `seq`/`prev_seq` chains):

1. sort by bar timestamp, then by event type in this order:
2. `signal_snapshot`
3. `funding`
4. `fill`
5. `trade`
6. `position_snapshot`
7. `equity_snapshot`
8. event keys sorted within each type.

### 4.4 Typed ledgers (append-only, typed constraints, FKs)

- `signal_snapshots` (see §4.6)
- `fills`
- `trades`
- `funding`
- `position_snapshots`
- `position_snapshot_symbols`
- `equity_snapshots`

Each main row references **exactly one** matching `ledger_events.seq` / event identity. All
are append-only with typed constraints and foreign keys to `ledger_events` and
`ledger_batches`.

### 4.5 Current state (mutable singleton/cache)

- `ledger_state` — singleton: watermark bar ts, accumulators, peak equity, drawdown, etc.
- `open_positions` — current open positions cache.

These are updated **only inside the same transaction** as the event/typed-ledger inserts.
The typed ledgers + events are the **durable historical record**; state is a transactional
**restart/cache anchor**. The verifier must be able to **detect state/cache drift** by
recomputing state from the ledgers and comparing.

### 4.6 Source snapshot (`signal_snapshots`)

Stores the canonical full source observation JSON, its source digest, the bar timestamp, and
the `bar_commit_id`. The verifier **recomputes** the digest and commit ID from the stored
canonical JSON and compares — reusing the existing `snapshots.py` digest/`bar_commit_id`
functions.

---

## 5. Transaction flow (writer)

1. Validate DB identity, schema, config, and **external observer freshness**.
2. Load OHLCV/funding inputs **before** taking the writer transaction.
3. `BEGIN IMMEDIATE`.
4. Re-read config, existing snapshots, and current state **inside** the transaction.
5. Check source-observation divergence.
6. Run the **unchanged deterministic engine**.
7. Insert the complete event batch and typed rows.
8. Update `ledger_state` / `open_positions`.
9. Run structural + arithmetic reconciliation against the **uncommitted transaction view**.
10. Commit **only if every check passes**.
11. Any exception, mismatch, or crash **rolls back the entire batch** (no partial state).
12. A valid DB with no committed eligible bars returns **`PRE_START`**.
13. An aborted freshness/divergence check **never mutates the DB**.

This collapses the JSONL "write `RUNNING` first, publish bundle, write `OK` last" protocol
into one atomic transaction: there is no stale-`OK`-survives-failed-publish window because
there is no multi-file publish — either the batch commits or it does not.

---

## 6. Public interfaces

- **`QNTY_PAPER_DB_PATH`**, default `/srv/qnty/output/paper_pnl_v1/paper_ledger.db`.
- **Init CLI** (future): `scripts/qnty-paper-sqlite-init.py --forward-start-ts ... --db-path ...`
  - creates a fresh database
  - **refuses** an existing database
  - **refuses** legacy paper artifacts unless the operator explicitly archives/removes them
- **Accounting CLI** (implemented): `scripts/qnty-paper-sqlite-accounting.py --db-path ...`
  - writes transactionally
  - exit codes match writer status codes
  - no JSONL artifacts created
  - no VM interaction
- **Verifier CLI** (adapted): `scripts/paper_verify.py --db-path ... [--json]`
  - opens the DB read-only / query-only
  - prints its report to **stdout only**
  - does **not** write verifier reports in v1 unless explicitly decided later

### Exit codes

**Accounting** (`qnty-paper-sqlite-accounting.py`):

| code | status | meaning |
| --- | --- | --- |
| `0` | `OK` | complete batch committed atomically |
| `2` | `ABORTED` | freshness/divergence gate aborted; DB unmutated |
| `3` | `CONFIG_ERROR` | DB/config identity invalid (missing/stale/malformed/version/hash) |
| `4` | `CORRUPT_LEDGER` | persisted ledger/state failed a structural or reconcile invariant |
| `5` | `PRE_START` | valid DB, no committed eligible bars yet (no bar ≥ `forward_start_ts`) |
| `6` | `LEDGER_BUSY` | could not acquire the writer lock (`BEGIN IMMEDIATE` failed; concurrent writer) |

**Verifier** (`paper_verify.py`):

| code | status | meaning |
| --- | --- | --- |
| `0` | `OK` | DB verified consistent |
| `3` | `CONFIG_ERROR` | DB/config identity invalid |
| `4` | `CORRUPT` | a verification invariant failed |
| `5` | `PRE_START` | valid DB, no committed eligible bars yet |

> `PRE_START` replaces the JSONL `NO_ELIGIBLE_BARS_YET` healthy-no-op. There is no `RUNNING`
> persisted status in the SQLite model: an in-flight transaction is uncommitted and therefore
> invisible to any reader; a crashed transaction rolls back and leaves no marker.

### Wrapper policy

- The wrapper succeeds **only** for a matching `OK/OK` (accounting OK + verifier OK) or a
  documented `PRE_START/PRE_START`.
- **Every other result fails the service.**
- No wrapper may certify a stale old ledger after an accounting failure.

---

## 7. Keep / Replace / Add / Delete / Adapt map

### Keep (reuse as-is)

- deterministic fill/funding/PnL logic in `engine.py`
- freshness validation (`freshness.py`)
- config construction/validation/hash logic where reusable (`config.py`)
- snapshot digest and `bar_commit_id` functions (`snapshots.py`)
- baseline label, disclaimer, and summary arithmetic

### Replace

- `runner.py` persistence → one SQLite transaction
- `reconcile.py` → storage-independent accounting checks over typed DB rows
- `verify.py` → read-only DB verification
- config file loading/writing → DB config access

### Add (later phases)

- `quantbot/paper/db.py` (Phase 1 — IMPLEMENTED)
- `quantbot/paper/sqlite_writer.py` (Phase 2 — IMPLEMENTED)
- `quantbot/paper/reporting.py`
- `scripts/qnty-paper-sqlite-init.py` (Phase 1 — IMPLEMENTED)
- `scripts/qnty-paper-sqlite-accounting.py` (Phase 2 — IMPLEMENTED)
- `tests/test_paper_sqlite.py` (Phase 1 — IMPLEMENTED)
- `tests/test_paper_sqlite_writer.py` (Phase 2 — IMPLEMENTED)

### Delete / deprecate (later phases, only after SQLite path is proven)

- JSONL I/O in `ledger.py`
- digest/publication machinery in `provenance.py`
- verifier snapshot copier
- `verify_runs`
- trusted baseline
- persisted runner summary/state/provenance/receipt files
- JSONL-specific authority tests
- remove or deprecate `scripts/paper_reconcile.py` (avoid a second verifier implementation)

### Adapt (later phases)

- accounting/verifier CLIs
- `ops/bin/qnty-paper-pnl-init.sh` (`scripts/qnty-paper-pnl-init.sh`)
- `ops/bin/qnty-paper-pnl-run.sh`
- package path helpers
- service comments
- `docs/paper_pnl_v1_schema.md`
- `docs/ops/VM_90D_RUNBOOK.md`

---

## 8. Implementation phases

This ADR is **Phase 0** and authorizes design only. Each later phase requires explicit
approval and must leave the targeted paper suites + full repo suite green before the next.

- **Phase 0 — schema only (this ADR):** SQLite design/DDL, final threat model, schema,
  transaction flow, statuses, migration decision. **No runtime changes.**
- **Phase 1 — substrate (IMPLEMENTED):** `db.py`, init CLI, schema, triggers, indexes,
  path handling, SQLite version gate, isolated DB tests. See § 8a for Phase 1 decisions.
- **Phase 2 — writer (IMPLEMENTED 2026-06-08):** `sqlite_writer.py`, accounting CLI,
  transaction flow with reconciliation, event chain implementation, idempotency via watermark.
  See § 8b for Phase 2 details.
- **Phase 3 — verifier (IMPLEMENTED 2026-06-08):** read-only / query-only SQLite verifier
  (`sqlite_verify.py` + `scripts/qnty-paper-sqlite-verify.py`) that validates committed DB
  state from the typed tables; arithmetic/structural invariants ported; snapshot/trusted-baseline
  authority not used. Added as a parallel implementation alongside the JSONL verifier (the JSONL
  verifier and its tests are NOT removed yet — that is Phase 4). See § 8c.
- **Phase 3.5 — writer/verifier correctness fix (IMPLEMENTED 2026-06-08):** closes the
  adversarial-review blockers that made Phase 3 unsafe to advance: the verifier could return
  OK/PRE_START for corrupt accounting, and the writer could not preserve or exit positions
  across runs. **Phase 4 is NOT authorized until these fixes pass adversarial review.** See § 8d.
- **Phase 4 — ops/docs:** update wrapper/status matrix/init shell/service comments/docs;
  remove unused JSONL/provenance modules; remove legacy artifact generation **only after** the
  SQLite path is proven.
- **Phase 5 — adversarial review:** targeted fault injection, full suite, schema review,
  wrapper review, backup-path review. **No VM deployment decision until approved.**

### 8a. Phase 1 clarifications (implemented)

- **`prev_seq` NULL:** the first event in `ledger_events` may have `prev_seq = NULL`.
  This is intentional — it marks the start of the chain. The verifier must accept
  `prev_seq IS NULL` for exactly one event (the first).
- **`config_hash` excludes itself:** the `config_hash` field is NOT included when
  computing the hash. The `config_hash_from_row()` function reconstructs the canonical
  config dict (excluding `config_hash`) and delegates to `quantbot.paper.config.config_hash`.
- **Mutable state is cache:** `ledger_state` and `open_positions` are explicitly mutable
  (no append-only triggers). They are a transactional restart/cache anchor only. The
  verifier MUST detect state/cache drift by recomputing state from the ledgers.
- **Trigger error type:** append-only triggers raise `sqlite3.IntegrityError` (not
  `OperationalError`) because the trigger uses `RAISE(ABORT, ...)`. Both are subclasses
  of `sqlite3.Error`.

### 8b. Phase 2 clarifications (implemented 2026-06-08)

**Implementation files:**
- `quantbot/paper/sqlite_writer.py` — `run_sqlite_accounting(db_path, forward_obs_dir, data_dir)`
- `scripts/qnty-paper-sqlite-accounting.py` — CLI wrapper
- `tests/test_paper_sqlite_writer.py` — 29 tests at Phase 2 (extended by Phase 3.5 with the
  entry→exit / restart trade-lifecycle cases)

**Transaction flow:**
1. `BEGIN IMMEDIATE`
2. Load config, state, snapshots inside transaction
3. Check source-observation divergence
4. Run deterministic engine (unchanged)
5. Insert complete event batch + typed rows
6. Update `ledger_state` / `open_positions`
7. Run 14 reconciliation checks inside transaction
8. Commit only if all checks pass
9. Any exception → full rollback (no partial state)

**Event chain implementation:**
- `seq INTEGER PRIMARY KEY AUTOINCREMENT` with `prev_seq` linking
- Deterministic order: bar_ts → event_type order (signal_snapshot, funding, fill, trade, position_snapshot, equity_snapshot) → event_key
- Verifier checks chain integrity (gaps in `seq` are NOT corruption; chain integrity is authoritative)

**Reconciliation checks (inside transaction, before commit):**
1. Fill fee/slippage arithmetic
2. Trade gross/net arithmetic
3. Internal funding arithmetic
4. Equity balance check
5. Drawdown calculation
6. State accumulators (watermark, peak equity)
7. Open position details
8. Batch event count matches
9. Event type/key uniqueness
10. Foreign key consistency
11. Config hash match
12. Source snapshot digest verification
13. Bar commit ID verification
14. Watermark progression

**Status codes:**
| code | status | meaning |
| --- | --- | --- |
| `0` | `OK` | complete batch committed atomically |
| `2` | `ABORTED` | freshness/divergence gate aborted; DB unmutated |
| `3` | `CONFIG_ERROR` | DB/config identity invalid |
| `4` | `CORRUPT_LEDGER` | persisted ledger/state failed a structural or reconcile invariant |
| `5` | `PRE_START` | valid DB, no committed eligible bars yet |
| `6` | `LEDGER_BUSY` | could not acquire writer lock |

**Idempotency:**
- Watermark in `ledger_state` prevents re-processing same bars
- `prior_watermark_bar_ts` → `new_watermark_bar_ts` tracks progression

**Crash safety:**
- Full rollback on any exception (Python or SQLite)
- No partial writes visible to readers
- WAL mode ensures crash recovery

**CLI script (`scripts/qnty-paper-sqlite-accounting.py`):**
- Arguments: `--db-path`, `--forward-obs-dir`, `--data-dir`, `--json`
- Environment variable: `QNTY_PAPER_DB_PATH` (fallback default)
- Exit codes match writer status codes exactly
- No JSONL artifacts created
- No VM interaction
- JSON output mode for programmatic use

**Test coverage:**
- 29 tests in `tests/test_paper_sqlite_writer.py` at Phase 2 (Phase 3.5 adds the
  entry→exit / restart trade-lifecycle cases)
- All 16+ required test cases from ADR §9 implemented
- Existing tests (`test_paper_sqlite.py`, `test_paper_pnl.py`) still pass
- Test fixtures use `tmp_path` only, no VM dependencies
- Tests cover: transaction atomicity, rollback, idempotency, reconciliation, status codes, event chain, crash safety

**What Phase 2 does NOT do:**
- Does not modify `runner.py` or `verify.py` (those remain JSONL-based)
- Does not replace JSONL runner yet (that's Phase 3)
- Does not enable timers or touch VM
- Does not make SQLite writer the default path yet
- Does not implement the verifier (Phase 3)
- Does not remove JSONL artifacts or legacy code

**Phase 3 note (historical — superseded):** this section originally recorded Phase 3 as
PLANNED/NOT STARTED. Phase 3 has since been implemented (see § 8c) and then hardened by
Phase 3.5 (see § 8d). The verifier does NOT update the production wrapper or remove the JSONL
authority — that remains Phase 4 and is not yet authorized.

### 8c. Phase 3 clarifications (implemented 2026-06-08)

**Implementation files:**
- `quantbot/paper/sqlite_verify.py` — `verify_database(db_path) -> VerifyResult`
- `scripts/qnty-paper-sqlite-verify.py` — CLI wrapper (`--db-path`, `--json`, `--verbose`,
  `QNTY_PAPER_DB_PATH` fallback)
- `tests/test_paper_sqlite_verify.py` — tmp_path only; no VM/`/srv/qnty` paths (extended by
  Phase 3.5 with trade-lifecycle, position-snapshot, cumulative-equity, restart-field,
  PRE_START-hardening and malformed-DB cases)

**Verifier statuses / exit codes:**

| code | status | meaning |
| --- | --- | --- |
| `0` | `OK` | DB verified consistent |
| `3` | `CONFIG_ERROR` | DB/config identity invalid (missing file, schema/engine/baseline/hash) |
| `4` | `CORRUPT` | a structural or accounting invariant failed |
| `5` | `PRE_START` | valid DB, no committed batches/events/equity and `watermark_bar_ts` NULL |

**Verifier flow (as hardened by Phase 3.5):** open read-only (`mode=ro` + `PRAGMA
query_only=ON`) → confirm `query_only` → structural presence (tables/append-only
triggers/indexes) → identity/config-hash → (malformed/non-SQLite file short-circuits to
CONFIG_ERROR) → PRE_START only on a fully-empty ledger with a valid initial state singleton
→ `PRAGMA foreign_key_check` → event chain → event↔typed-row key/batch/bar/symbol consistency
→ batches → fill/funding arithmetic → trade lifecycle → cumulative equity → state → open
positions → position snapshots → snapshot identity. It never writes the DB and never writes
any report/JSONL artifact.

**Checks implemented (Phase 3 baseline; see § 8d for the Phase 3.5 hardening):** deterministic
`prev_seq` chain (first event NULL, gaps are not corruption), event-type enum, unique event
identity, 1:1 event↔typed-row, batch `event_count` / `first`/`last_event_seq` /
`committed_bar_count`, batch engine-version & config-hash agreement, no fill before
`forward_start_ts` (on the signal bar), fill-fee arithmetic, trade arithmetic, funding amount
arithmetic, equity balance & drawdown, `ledger_state` accumulators vs ledger-table sums,
watermark = latest committed equity bar, peak-equity reconstruction, `open_positions`
reconstructed from the fill book, cross-row `bar_commit_id` agreement + `snapshot_id ==
bar_commit_id`, digest well-formedness, and the fixed-notional baseline (no shorts, fixed
notional per entry / no compounding).

**Verifier v1 limitations (documented, by design):**
- It does **not** independently rederive OHLCV marks / unrealized PnL / exposure from source
  price data (out-of-scope per §3). The CLI/result carry the disclaimer verbatim:
  *"Verifier v1 validates SQLite ledger integrity and internal accounting consistency. It does
  not independently rederive OHLCV marks/unrealized PnL/exposure from source price data."*
- It does **not** recompute `source_observation_digest` from a canonical source JSON, because
  the Phase 2 writer persists only the consumed subset of each observation, not the full
  canonical row. The verifier validates digest well-formedness and cross-row `bar_commit_id`
  agreement instead.

**Findings surfaced during Phase 3 — RESOLVED in Phase 3.5 (§ 8d):**
- The Phase 2 writer **could not emit trades/exits** (any exit tripped its own
  *"Orphan typed rows in fills"* reconcile). **Fixed in Phase 3.5:** the writer keys the
  inserted-event map by `(event_type, event_key)` (an exit fill and its closing trade share an
  id), resolves each event's `bar_ts` from its anchoring bar, and chains `prev_seq` across
  batches. The writer now emits real entry→exit→trade rows in a single run and across a restart.
- The Phase 2 writer did **not** persist `funding_accrued` / `hold_bars` / `entry_fee` into
  `open_positions`. **Fixed in Phase 3.5:** `open_positions` gains an `entry_fee` column, the
  writer persists the engine's authoritative open book (funding/hold/fee), and the verifier
  now reconstructs and validates all three from the ledger.

**What Phase 3 does NOT do** (Phase 3.5 later modifies `sqlite_writer.py` / `db.py` —
see § 8d — but neither phase touches the items below): does not modify `runner.py` /
`verify.py`; does not update the production wrapper, systemd units, or VM default path; does
not remove the JSONL verifier, its tests, or any legacy artifact generation; does not enable
timers or touch the VM. It does **not** establish deployment readiness.

### 8d. Phase 3.5 clarifications (writer/verifier correctness fix, implemented 2026-06-08)

Phase 3.5 closes the adversarial-review blockers (`NEEDS FIX BEFORE PHASE 4`): the Phase 3
verifier could return OK/PRE_START for corrupt accounting, and the Phase 2 writer could not
safely preserve or exit positions across runs.

**Schema (`db.py`):**
- `open_positions` gains an `entry_fee REAL NOT NULL DEFAULT 0.0` column so a position can be
  resumed losslessly across runs (the engine's exit path needs `entry_fee` /
  `funding_accrued` / `hold_bars`).

**Writer (`sqlite_writer.py`):**
- The inserted-event map is keyed by `(event_type, event_key)` — an exit fill and its closing
  trade share the same id, so keying by the bare id misrouted the typed rows
  (*"Orphan typed rows in fills"*). This is the root-cause fix for the broken exit path.
- `ledger_events.bar_ts` and the deterministic chain order are resolved per row type
  (fills key off the signal bar, trades off the exit bar) instead of a bare
  `attrs.get("bar_ts")` that was `None` for fills/trades.
- The in-transaction reconcile chains `prev_seq` across batches (the batch's first event links
  to the prior global event, NULL only for the very first event ever).
- `open_positions` persists the engine's authoritative open book (entry_fee / funding_accrued
  / hold_bars), not the lossy entry/exit replay.
- The per-bar position-snapshot walk is seeded with the restart open book, so a restart
  batch's `position_snapshots` agree with the `position_snapshot_symbols` child rows.
- An empty batch is never committed (the writer rolls back when there is nothing to commit).

**Verifier (`sqlite_verify.py`):**
- **PRE_START** is allowed only for a fully-empty ledger (no batches/events/typed/open rows)
  whose `ledger_state` is a valid initial singleton (NULL watermark, zero accumulators,
  peak = initial equity). Corrupt pre-start state is CORRUPT. A **committed empty batch** is
  CORRUPT.
- **Trade lifecycle** is re-derived from the underlying fills + funding ledger, not the trade
  row's own fields: entry/exit fills must exist with the right kind/side/symbol/qty;
  `gross_pnl == (exit_price − entry_price) × qty`; `fees == entry_fee + exit_fee`; `funding`
  equals the funding-ledger aggregation over the held interval; `net == gross − fees −
  funding`. Fake fill ids and arbitrary gross/funding are CORRUPT.
- **Durable relationships:** `PRAGMA foreign_key_check`; each event's `event_key` matches the
  typed row's natural key and its `batch_id` / `bar_ts` / `symbol` agree with the typed row;
  every `position_snapshot` has exactly the expected `position_snapshot_symbols` and
  `num_open` equals that count and the `open_symbols` length, reconstructed from the fill book.
- **Cumulative equity** is recomputed from history: `realized_gross` from trades closed before
  the bar, `fees_cum` from fills before the bar, `funding_cum` from funding up to the bar, then
  equity and running peak/drawdown — so a coordinated mutation of realized/equity/peak is
  caught. The unrealized mark is still taken from the row (not rederived from OHLCV).
- **open_positions** restart fields are validated from the ledger: `entry_fee` from the entry
  fill, `hold_bars` from the count of committed equity bars after the entry bar, and
  `funding_accrued` from the funding ledger since entry.
- **Malformed DBs** no longer traceback: a non-SQLite / unreadable file is CONFIG_ERROR; a
  query/parse error during consistency checks is CORRUPT. The CLI exits with the status code
  and prints no traceback.

**Verifier v1 limitations are unchanged and remain explicit:** no independent OHLCV mark /
unrealized-PnL / exposure re-derivation; no live-trading approval; no Package V2 volnorm proof.
Phase 3.5 establishes **no** deployment readiness — Phase 4 remains unauthorized until these
fixes pass adversarial review.

---

## 9. Acceptance gates (for later phases)

- Init verifies WAL, `synchronous=FULL`, foreign keys, STRICT support, schema identity,
  indexes, and immutable triggers.
- `UPDATE`/`DELETE` against `paper_config`, `ledger_batches`, `ledger_events`, and the typed
  ledgers all abort.
- A complete writer batch commits atomically.
- Injected exceptions after inserts/state changes leave **no** new batch, events, or state.
- A second `BEGIN IMMEDIATE` writer fails cleanly as `LEDGER_BUSY`.
- A concurrent read-only verifier sees a consistent committed snapshot.
- Read-only / query-only verifier write attempts fail.
- Verifier catches: broken event chains, event/type mismatches, batch counts, schema/config
  versions, malformed source JSON, commit-ID disagreement.
- Verifier catches: broken fill fee/slippage arithmetic, trade gross/net arithmetic, internal
  funding arithmetic, equity balance/drawdown, state accumulators, watermark, peak equity, and
  open-position details.
- Funding verification is limited to persisted rates/windows/amounts and trade aggregation.
- Verifier **explicitly reports** that OHLCV mark and unrealized-PnL re-derivation are **not
  implemented**.
- Wrapper tests cover every accounting/verifier exit-code combination and succeed only on
  `OK/OK` or documented `PRE_START/PRE_START`.
- Existing engine/freshness/divergence/funding/fill-timing/idempotency/baseline-label tests
  remain.
- Obsolete JSONL publication/whitespace/tamper-baseline tests are **replaced**, not
  mechanically preserved.
- Targeted paper suites and the complete repo suite pass before implementation moves beyond
  each phase.

---

## 10. Migration & backup rules

- Do **not** import legacy JSONL or the stale VM `paper_config.json`. There is **no** JSONL
  import / compatibility migration.
- Future deployment must **archive/remove the entire stale `/srv/qnty/output/paper_pnl_v1/`**
  and initialize a fresh DB with a **future UTC 8-hour boundary** as `forward_start_ts` (never
  reuse a stale forward start).
- **WAL backup safety:** raw-copying only `paper_ledger.db` while the writer is active is
  **unsafe** — committed data may still live in `paper_ledger.db-wal`. Use the **SQLite backup
  API**, or **stop the writer and checkpoint** before copying. Backup restoration must be
  tested.
- Documentation to update in later phases: rewrite `docs/paper_pnl_v1_schema.md` around the
  SQLite authority model and this local threat model; update `docs/ops/VM_90D_RUNBOOK.md` to
  remove JSONL/verifier-authority language and document the new statuses/commands. Keep the
  fixed-notional / non-V2 / no-live-trading disclaimers.

---

## 11. Risks & mitigations

| Risk | Mitigation |
| --- | --- |
| Large migration diff | Isolate by phase; preserve engine/freshness logic. |
| Regression risk | Existing paper/full suites must pass after each phase. |
| Engine/DB mismatch | One typed adapter; reconcile inside the transaction before commit. |
| Determinism loss | Explicit query ordering, canonical source JSON, deterministic event order, stable event keys. |
| DB path mismatch | One canonical `QNTY_PAPER_DB_PATH` used by init, runner, verifier, wrapper. |
| WAL backup omission | Document backup API/checkpoint; test backup restoration. |
| SQLite compatibility | Require SQLite **3.37+** for STRICT; init fails loudly on older versions. |
| Trigger overconfidence | Verifier checks trigger/schema presence; malicious filesystem/root modification remains out of scope. |
| Mutable-state overconfidence | State is cache/anchor; typed ledgers/events are the durable record; verifier checks state against ledgers. |

---

## 12. Explicit non-goals

No live trading. No orders. No credentials. No wallet access. No strategy changes. No observer
changes. No Package V2 volnorm claims. No malicious-root resistance. No cryptographic signing.
No tamper-proof public evidence. No external audit guarantee. No JSONL import or compatibility
migration. No persisted authoritative verifier report / trusted-OK baseline / homemade snapshot
copier. No independent OHLCV mark re-derivation in this migration.

---

## 13. Consequences

- The paper-PnL durability/atomicity/single-writer/read-consistency guarantees move from
  hand-rolled multi-file protocols to SQLite primitives, shrinking the attack/bug surface that
  the adversarial review kept reopening.
- The authority model becomes: **the committed DB is the record; the read-only verifier reports
  on it.** There is no trusted-OK baseline, no snapshot copier, and no multi-file publication
  ordering to get wrong.
- The migration is large and staged; until the SQLite path is implemented and proven, the
  existing JSONL model in `docs/paper_pnl_v1_schema.md` remains authoritative and the **paper
  timer on the VM stays disabled** (the VM holds only a stale `paper_config.json`; no real
  paper ledgers exist).
- **Phase 2 update (2026-06-08):** SQLite writer implemented with transactional accounting,
  event chain, reconciliation checks, and idempotency. SQLite writer is not yet the default
  path; JSONL runner still used in production.
- **Phase 3 update (2026-06-08):** read-only / query-only SQLite verifier implemented as a
  parallel implementation alongside the JSONL verifier (see § 8c). It does not update the
  production wrapper or remove JSONL authority (that is Phase 4).
- **Phase 3.5 update (2026-06-08):** writer/verifier correctness fixes closing the adversarial
  blockers (see § 8d) — the writer now emits and resumes entry→exit→trade lifecycles, and the
  verifier no longer passes corrupt accounting as OK/PRE_START. **Phase 4 remains unauthorized
  until Phase 3.5 passes adversarial review.** No deployment readiness is claimed; the paper
  timer on the VM stays disabled and the JSONL runner is still used in production.
