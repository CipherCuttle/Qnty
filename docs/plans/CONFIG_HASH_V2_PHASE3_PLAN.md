# config_hash_v2 — Phase 3 Plan

Docs-only design plan. **This is a plan, not an implementation.** No source code,
tests, DB schema, writer, verifier, VM, or systemd changes are made by this
document.

Reference plan: `LANE_IDENTITY_PHASE3_PLAN.md` (slice 3 — `config_hash_v2` helper).
Predecessor: pure model in `quantbot/paper/lane_identity.py`
(`LANE_IDENTITY_MODEL_PHASE3_RECEIPT.md`).

Strategy label remains `EDGE_UNPROVEN`.

---

## 1. Purpose

Plan-only design for a future `config_hash_v2`. It exists to give **new shadow
lanes a lane-aware identity**. It **must not change the existing v1 baseline config
hash**: the production baseline `paper_pnl_v1` and its `config_hash` stay
byte-identical. No profitability or edge claim is made.

## 2. Existing v1 hash contract

- Built by **`config_hash(config)`** in `quantbot/paper/config.py`.
- **SHA-256 over the canonical JSON of the config, excluding `config_hash` itself.**
- Fields included (the canonical v1 payload):
  - `schema_version`
  - `engine_version`
  - `baseline_label`
  - `forward_start_ts`
  - `initial_equity_usd`
  - `notional_usd`
  - `leverage`
  - `fee_model`
  - `slippage_model`
  - `fill_model`
  - `funding_model`
  - `signal_source`
  - `freshness`
- Persisted in **`paper_config.json`** (filesystem write-once) and the SQLite
  **`paper_config.config_hash`** column.
- Recomputed by **`load_config`** (filesystem reload check) and
  **`config_hash_from_row`** (DB-row recomputation in the verifier).
- Used as an input to **`bar_commit_id`**
  (`sha256(consumed row + bar_ts + engine_version + config_hash)`).
- **Changing the v1 hash would cascade into snapshot/fill identity** (every
  `signal_snapshots` / `fills` `bar_commit_id`), so v1 must remain frozen.

## 3. `config_hash_v2` meaning

- `config_hash_v2` is **for new lanes only**.
- It **composes over the frozen `accounting_config_hash_v1`** (consumes the existing
  v1 hash as an opaque string; never recomputes or alters it).
- It **binds lane identity**:
  - `lane_id`
  - `strategy_id`
  - `strategy_version`
- It **does not redefine the accounting contract** (the accounting payload lives
  entirely inside the referenced v1 hash).
- It **does not include source data**.
- It **does not include `pre_registration_hash`**.

## 4. Proposed canonical payload

```json
{
  "config_hash_version": 2,
  "accounting_config_hash_v1": "<existing_v1_hash>",
  "lane_identity": {
    "lane_id": "...",
    "strategy_id": "...",
    "strategy_version": "..."
  }
}
```

`config_hash_v2` = SHA-256 over the canonical JSON of this payload (same canonical
serialization machinery used by the v1 hash, for determinism).

## 5. Explicit exclusions from the v2 payload

- **`source_data_digest`** — per-run / per-window input identity, **not** static
  config identity. Including it would make the lane's config identity change every
  run; it belongs to a separate per-run/per-batch digest.
- **`pre_registration_hash`** — a separate experiment commitment. Excluded to avoid
  **circularity**: a pre-registration may commit to the config hash, so the config
  hash must not depend on it.
- **`paper_engine_version`** — **already inside the v1 hash** (transitively bound via
  `accounting_config_hash_v1`); re-adding it would double-count and risk drift.
- **`schema_version`** — **already inside the v1 hash** (same reason).
- **`db_schema_version`** — a **storage concern**, not lane/accounting identity, and
  this slice touches no DB.

## 6. `pre_registration_hash` separation

- `config_hash_v2` proves **"this lane = this accounting contract + this strategy
  identity"** (a static identity).
- `pre_registration_hash` proves **"these parameters / seed policy were committed
  before the run"** (a time-ordered commitment).
- **Parameter changes** create a new pre-registration commitment (and change
  `config_hash_v2` via its identity / v1-hash inputs).
- **Source-data changes** are captured by a future **`source_data_digest`**, not by
  either config hash.

## 7. Future function design (plan only)

- Future module: **`quantbot/paper/lane_config_hash.py`**.
- Future pure functions:

```python
def config_hash_v2_payload(accounting_config_hash_v1: str, identity: LaneIdentity) -> dict: ...
def config_hash_v2(accounting_config_hash_v1: str, identity: LaneIdentity) -> str: ...
```

- Module must be **pure**:
  - no DB
  - no env vars
  - no file I/O
  - no network
  - **no import from `config.py`** if avoidable (so it cannot perturb v1 behavior)
  - **consume the v1 hash as a string, never recompute or alter v1 behavior**
- `accounting_config_hash_v1` should be validated as a 64-char lowercase hex SHA-256
  string (required, not optional). Identity is supplied as a validated
  `LaneIdentity`.

## 8. Baseline protection gates

Future implementation must prove:

- Current v1 `config_hash` output **unchanged** (byte-identical golden value).
- `build_config(...)` output **unchanged** (golden dict).
- `config_hash_from_row(...)` **unchanged** for old (schema-1, no lane columns) rows.
- Baseline `bar_commit_id` **unchanged** for identical inputs.
- Old baseline DB identity still validates.
- **No production `paper_pnl_v1` mutation.**
- **No DB schema change in this slice.**

## 9. Test plan

- v1 config hash golden **unchanged**.
- v2 hash **deterministic** (same inputs → same hash).
- v2 hash **changes when `lane_id` changes**.
- v2 hash **changes when `strategy_id` changes**.
- v2 hash **changes when `strategy_version` changes**.
- v2 **rejects an invalid v1 hash** (wrong length / non-hex / uppercase).
- payload **excludes `source_data_digest`** (assert key absent).
- payload **excludes `pre_registration_hash`** (assert key absent).
- **no I/O / DB / env / network imports** (source-scan purity test).
- **no production path strings**.

## 10. Smallest future implementation slice

- Add `quantbot/paper/lane_config_hash.py`.
- Add `tests/test_paper_lane_config_hash.py`.
- **No `config.py` modification** if avoidable (v1 hash consumed as a passed-in
  string).
- No DB schema.
- No writer / verifier.
- No baseline mutation.

## 11. Exclusions

Explicitly excluded from this slice:

- DB schema.
- Migrations.
- Writer changes.
- Verifier changes.
- V2 strategy.
- Live lanes.
- VM.
- systemd / timers.
- Production DB.
- Source digest implementation.
- Pre-registration hash implementation.
- Cross-lane reporter.
- Profit / edge claims.

No source code, tests, DB schema, writer, verifier, systemd, SSH, or DB are touched
by this plan. Existing `config_hash`, `build_config`, and `config_hash_from_row` are
not modified. `.claude/` is not staged. Strategy label remains `EDGE_UNPROVEN`.
