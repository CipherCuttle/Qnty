# Baseline v1 Unchanged / Golden-Hash Proof — Phase 3 Plan

Docs-only plan. **This is a plan, not an implementation.** No source code, tests,
DB schema, writer, verifier, VM, or systemd changes are made by this document, and
no golden-hash tests are written yet.

Reference plan: `CONFIG_HASH_V2_PHASE3_PLAN.md`. Predecessor receipt:
`CONFIG_HASH_V2_HELPER_PHASE3_RECEIPT.md`.

Strategy label remains `EDGE_UNPROVEN`.

---

## 1. Purpose

Plan-only receipt for proving the v1 baseline config / hash / commit-id identity
remains **unchanged**. This is a **safety gate** before any future schema, writer,
verifier, or lane wiring: it locks the existing behavior with golden values so a
later change that would perturb the clean baseline fails loudly. **It does not
implement tests yet.** No profitability or edge claim is made.

## 2. Current v1 identity contract

- **`build_config(...)` output shape must stay fixed** (`quantbot/paper/config.py`).
  It is deterministic for a fixed `forward_start_ts` (constants + defaults + the
  passed timestamp; no clock or randomness).
- **`config_hash(...)` is SHA-256 over the canonical JSON of the config excluding
  `config_hash` itself** (64-char lowercase hex).
- **`config_hash_from_row(...)` reconstructs the v1 config from a flat DB row**
  (`quantbot/paper/db.py`) and re-hashes; it must match `config_hash(build_config())`
  for an equivalent row.
- **`bar_commit_id(...)` hashes** the consumed row + bar timestamp + engine version +
  config hash (`quantbot/paper/snapshots.py`).
- **`bar_commit_id(...)` returns a 16-character truncated hex string**, not a full
  SHA-256 (the digest is truncated with `[:16]`).
- **Baseline label behavior must remain unchanged**
  (`BASELINE_LABEL = "fixed_notional_active_symbols_paper_v1"`).

## 3. What must be locked

- v1 `build_config(...)` full dict shape.
- v1 `config_hash(...)` output.
- v1 `config_hash_from_row(...)` reconstruction.
- v1 `bar_commit_id(...)`.
- Old schema-1 baseline DB identity path (a row without lane fields still
  validates / reconstructs).
- Baseline label behavior.

## 4. Golden-values strategy

- Use **one deterministic fixed on-grid `forward_start_ts`** (all other params at
  `build_config` defaults).
- **Hardcode the expected full v1 config dict** (full dict equality, not just key
  presence).
- **Hardcode the expected v1 `config_hash`** (64-char hex).
- **Hardcode the expected 16-char `bar_commit_id`** for fixed inputs.
- Use **synthetic / in-memory DB row data only** for `config_hash_from_row`.
- **Do not use the production DB.**
- **Do not use `/srv/qnty`.**
- **Generate the constants during implementation** by running the current functions
  once, pasting the outputs, then asserting against those constants thereafter. The
  goldens are intentionally coupled to `SCHEMA_VERSION = 1`,
  `PAPER_ENGINE_VERSION = "0.3.0"`, and the baseline label — a constant change
  *should* break the test loudly (that is the point of the gate).

## 5. Future test file

Plan to add later: **`tests/test_paper_config_hash_golden.py`** (there is currently
no dedicated golden config-hash test; existing tests recompute `config_hash` but
never assert a hardcoded constant).

## 6. Future tests

- `build_config(forward_start_ts=...)` equals the expected full dict.
- `config_hash(build_config(...))` equals the fixed golden.
- `config_hash_from_row(...)` over a synthetic v1 row equals the same golden.
- `bar_commit_id(...)` over a fixed consumed row + bar_ts + engine version + config
  hash equals the fixed 16-char golden.
- `config_hash_v2(...)` does **not** mutate / recompute the v1 config.
- An old v1 row without lane fields reconstructs / validates.
- No production path strings in the test.

## 7. Baseline protection gates

The slice must prove:

- v1 config hash **byte-identical**.
- v1 config dict shape unchanged.
- v1 DB-row reconstruction unchanged.
- v1 bar commit ID unchanged.
- No production `paper_pnl_v1` touched.
- No DB schema change.
- No VM / systemd access.

## 8. Smallest future implementation slice

- Add the **test file only** (`tests/test_paper_config_hash_golden.py`).
- No source code changes if possible.
- No docs except the later receipt.
- Full suite must pass.
- Grep must prove no production paths.

## 9. Verification commands for future implementation

```bash
cd /home/swirky/DevHub/repos/Qnty
git status --short --branch
.venv/bin/pytest tests/test_paper_config_hash_golden.py -q
.venv/bin/pytest tests/test_paper_lane_config_hash.py tests/test_paper_lane_identity.py -q
.venv/bin/python -m pytest -q
git diff --check
grep -RInE "live trading|exchange key|real order|profit guaranteed|edge confirmed|go live" \
  tests/test_paper_config_hash_golden.py 2>/dev/null || true
grep -RInE "/srv/qnty|paper_pnl_v1|sqlite3|systemctl|journalctl|ssh -i|subprocess|socket|requests|urllib" \
  tests/test_paper_config_hash_golden.py 2>/dev/null || true
git status --short --branch
```

Classification note for the slice: prefer a plain dict / in-memory row built without
any file so the `sqlite3` token never appears; any `/srv/qnty` or production-DB path
is unacceptable.

## 10. Exclusions

Explicitly excluded:

- Production DB.
- `/srv/qnty`.
- VM / SSH.
- systemd / timers.
- Schema mutation.
- Migrations.
- Writer / verifier wiring.
- V2.
- Live / shadow lanes.
- `source_data_digest`.
- `pre_registration_hash`.
- Shadow DB writer.
- Cross-lane reporter.
- Profit / edge claims.

No source code, tests, DB schema, writer, verifier, systemd, SSH, or DB are touched
by this plan. `config.py`, `db.py`, `snapshots.py`, `sqlite_writer.py`,
`sqlite_verify.py`, and `engine.py` are not modified. `.claude/` is not staged.
Strategy label remains `EDGE_UNPROVEN`.
