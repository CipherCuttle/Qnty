# Lane Identity / Config Schema — Phase 3 Plan

Docs-only design plan. **This is a plan, not an implementation.** No source code,
tests, DB schema, VM, or systemd changes are made by this document.

Reference plan: `PARALLEL_SHADOW_LANES_PLAN`. Predecessor receipts:
`OFFLINE_MATCHED_NULL_FIXTURE_PHASE2_RECEIPT.md`.

Strategy label remains `EDGE_UNPROVEN`.

---

## 1. Purpose

Phase 3 is a **design plan** for first-class lane identity / config schema. It is
**not an implementation**. Its reason to exist: prevent future shadow lanes from
**contaminating or impersonating the baseline** — a new lane must never mutate,
re-hash, or be mistaken for the clean production `paper_pnl_v1` lane. No
profitability or edge claim is made.

## 2. Current identity map

- `BASELINE_LABEL = "fixed_notional_active_symbols_paper_v1"` (`quantbot/paper/__init__.py`).
- Production output lane is **`paper_pnl_v1`** (its output dir / DB identity).
- `config_hash` is **SHA-256 over the canonical JSON of the config minus
  `config_hash` itself** (`quantbot/paper/config.py::config_hash`).
- Write-once config lives at **`paper_config.json`** (`write_config_once`); the
  verifier treats it as byte-immutable since the trusted baseline.
- DB identity is validated through the **`paper_config` row** (`validate_database_identity`
  in `quantbot/paper/db.py`) and **verifier checks** (`config_hash_from_row` +
  `baseline_label` check in `quantbot/paper/sqlite_verify.py`); the writer also
  cross-checks filesystem `paper_config.json` identity against the SQLite
  `paper_config` row.
- `git_sha` lives in **`ledger_batches.git_sha`** (per-batch provenance, written
  fail-closed via `resolve_git_sha()`).
- **`signal_snapshots.source_observation_digest` already exists** (per-bar digest
  of the consumed observation row).
- `bar_commit_id = sha256(consumed row + bar_ts + engine_version + config_hash)`,
  so **`bar_commit_id` depends on the config hash** — changing the v1 `config_hash`
  is dangerous because it would cascade into every snapshot/fill commit id.

Version constants today: `SCHEMA_VERSION = 1`, `DB_SCHEMA_VERSION = 1`,
`PAPER_ENGINE_VERSION = "0.3.0"`.

## 3. Future identity fields

- **`lane_id`** — stable unique key for one accounting lane and its isolated output
  dir / DB (e.g. `paper_pnl_v1`, `null_matched_v1`). Immutable for the lane's life;
  selects storage location and the verifier's expectation set. The existing
  baseline is implicitly `lane_id = "paper_pnl_v1"`.
- **`strategy_id`** — identity of the selection logic feeding the lane, independent
  of accounting params (e.g. `active_symbols_baseline`, `matched_null`).
- **`strategy_version`** — monotonic version of that strategy's selection behavior;
  bumped only when selection output can change.
- **`source_data_digest`** — deterministic digest of the exact source rows consumed
  (observations + funding + OHLCV window) for a run; proves two lanes were paired on
  identical inputs.
- **`pre_registration_hash`** — hash committed **before** a lane runs, binding the
  lane's declared intent (lane_id + strategy_id + strategy_version + config contract
  + seed policy) ahead of seeing results. Separate from `config_hash`. Absent/optional
  for the baseline (which predates pre-registration).

## 4. Backward compatibility plan

- The existing baseline **config and `config_hash` must remain byte-identical** —
  no new field may enter the v1 hashed payload.
- The **old v1 baseline DB remains valid**: read as a v1 lane with absent/null lane
  fields.
- New identity fields are **for new lanes only**.
- **No migration or `ALTER` is run against production `paper_pnl_v1`** (its DB,
  config, and output dir are never rewritten).
- The verifier should eventually support **dual-mode**:
  - **v1 baseline** — absent/null lane fields ⇒ enforce the existing baseline
    identity (`baseline_label`, v1 `config_hash`).
  - **v2 lane identity** — present lane fields ⇒ enforce `lane_id` / `strategy_id` /
    `strategy_version` consistency and the v2 hash.

## 5. Config hash strategy

- **Do not include `lane_id` / `strategy_id` (or any new field) in the existing v1
  `config_hash`** — it would change the baseline hash and cascade into every
  `bar_commit_id`.
- Introduce a future **`config_hash_v2` only for new lanes**.
- **`config_hash_v2` composes over the frozen `config_hash_v1` + lane identity**
  (e.g. hash of `{config_hash_v1, lane_id, strategy_id, strategy_version}`). v1 lanes
  never compute v2.
- **`pre_registration_hash` stays separate from `config_hash`**: `config_hash`
  attests the accounting contract; `pre_registration_hash` attests pre-committed
  lane intent + seed policy.

## 6. DB schema strategy (plan only)

- Future **nullable lane identity fields on `paper_config`** (`lane_id`,
  `strategy_id`, `strategy_version`, `pre_registration_hash`).
- Future **nullable `lane_id`** (and maybe **`source_data_digest`**) on
  `ledger_batches`.
- **Baseline rows may remain null** for all new fields (v1 `config_hash`
  recomputation ignores them — reconstruct only the v1 nested shape).
- **`source_observation_digest` already exists per bar** in `signal_snapshots`;
  `source_data_digest` is an aggregate over these, not a per-snapshot change.
- **No production DB mutation**: new columns appear only in newly-created lane DBs;
  no in-place `ALTER` against the baseline DB.

## 7. Source digest design

- `source_data_digest` should cover the **exact consumed observations** (reuse the
  existing per-bar `source_observation_digest` as the base unit).
- **Funding rows consumed** for the run window.
- **OHLCV rows consumed** for the run window.
- A **deterministic fold over the consumed row digests** (canonical-JSON SHA-256 over
  the ordered tuple of observation / funding / OHLCV digests actually read) — nothing
  more, so it is reproducible.
- **Paired lanes compare equal `source_data_digest`** later: two lanes are "paired"
  iff their `source_data_digest` values are equal.
- The **cross-lane reporter is out of scope** for this phase.

## 8. Baseline protection gates

Future implementation must prove:

- Baseline **config hash unchanged** (byte-identical golden value).
- **Old baseline DB identity validates** (schema-1, no lane columns).
- **Baseline verifier still passes** on a pre-change baseline DB fixture.
- **Baseline `paper_config.json` bytes unchanged** (write-once immutable).
- **Baseline systemd files untouched.**
- **No production output dir writes** (the `paper_pnl_v1` output dir is never
  written/relocated by lane code).

## 9. Test plan

- Golden **baseline config hash unchanged**.
- **Old schema-1 DB validates.**
- **New lane config validates** (identity fields present + v2 hash recomputes).
- **Mismatched `lane_id` fails** (between `paper_config` and `ledger_batches`).
- **Mismatched `strategy_id` fails.**
- **Changed `pre_registration_hash` fails** (vs registry).
- **`source_data_digest` mismatch fails.**
- **No production path references** (grep gate).
- **`.claude/` not staged** (status gate).

## 10. Future implementation slices (order)

1. Docs receipt.
2. Pure identity model / dataclass only (no I/O, no DB, no hashing of baseline).
3. `config_hash_v2` helper (composes over frozen `config_hash_v1`).
4. v1 baseline unchanged tests (config hash, verifier, DB identity).
5. Additive new-lane DB schema (nullable columns; no `ALTER` on baseline DB).
6. Verifier dual-mode identity checks.
7. Writer wiring **last** (no writer changes until all identity tests pass).

## 11. Exclusions

Explicitly excluded from Phase 3:

- V2 strategy.
- Shadow DB writer.
- Live lanes.
- Timers.
- VM.
- Production DB.
- Cross-lane reporter.
- Real data.
- Strategy comparison.
- Profit / edge claims.

No source code, tests, DB schema, systemd, SSH, or DB are touched by this plan.
`.claude/` is not staged. Strategy label remains `EDGE_UNPROVEN`.
