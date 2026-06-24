# Baseline v1 Golden-Hash Proof — Phase 3 Slice Receipt

Docs-only receipt for the test-only golden-hash proof landed in commit
`aec9417 Add baseline v1 config hash golden tests`.

Reference plan: `BASELINE_V1_GOLDEN_HASH_PROOF_PHASE3_PLAN.md`.

Strategy label remains `EDGE_UNPROVEN`.

---

## 1. Purpose

This slice added **test-only golden proof** for the v1 baseline config / hash
identity. It **locks current v1 behavior** before any future DB schema, writer,
verifier, or lane wiring, so a later change that would perturb the clean baseline
fails loudly. **It is not a strategy result.** No profitability or edge claim is
made.

## 2. File added

- `tests/test_paper_config_hash_golden.py`

## 3. Files intentionally NOT changed

- `quantbot/paper/config.py`
- `quantbot/paper/db.py`
- `quantbot/paper/snapshots.py`
- `quantbot/paper/sqlite_writer.py`
- `quantbot/paper/sqlite_verify.py`
- `quantbot/paper/engine.py`
- DB schema files
- ops / systemd files
- production configs
- VM files
- production lane / output

## 4. Locked values

- `FORWARD_START_TS = "2026-06-20T16:00:00"` (fixed, on-grid 00/08/16 UTC).
- `EXPECTED_CONFIG_HASH = 1d61c1c7…74561b` (64-char SHA-256 hex).
- `EXPECTED_BAR_COMMIT_ID = 7ae63522a23b65fc`.
- **Note:** `EXPECTED_BAR_COMMIT_ID` is a **16-char truncated hex** string, matching
  `bar_commit_id(...)` (which truncates the SHA-256 with `[:16]`) — it is NOT a full
  SHA-256.

## 5. Tests covered

- Full `build_config(...)` dict-shape lock (full dict equality + constant sanity).
- `config_hash(build_config(...))` equals the 64-char golden.
- `config_hash_from_row(...)` over a synthetic flat v1 row equals the same golden.
- Old v1 row without lane fields reconstructs correctly.
- `bar_commit_id(...)` equals the fixed 16-char golden.
- `config_hash_v2(...)` does **not** mutate / recompute the v1 config or v1 hash.

## 6. Data / source safety

- Synthetic in-memory dict row only.
- No production DB.
- No SQLite file.
- No `/srv/qnty`.
- No VM.
- No systemd.
- No production lane / output.

## 7. Verification results

- Focused golden tests: **6 passed**.
- Lane config hash + lane identity regression: **28 passed**.
- Full suite via `.venv/bin/python -m pytest -q`: **1200 passed**.
- `git diff --check`: clean.
- Claims grep: no hits.
- Infra grep: only one clearly-negated docstring guardrail
  (`no production DB, no /srv/qnty, no SQLite`).
- `.claude/` remained untracked.

## 8. Scope exclusions

- No source code changes.
- No config changes.
- No DB schema.
- No migrations.
- No writer changes.
- No verifier changes.
- No V2.
- No live / shadow lanes.
- No `source_data_digest`.
- No `pre_registration_hash`.
- No VM / systemd / production DB.
- No live trading / exchange keys / real orders.
- No profitability or edge claim.

## 9. Current verdict

`EDGE_UNPROVEN`

This proof locks identity behavior only; it says nothing about strategy quality.

## 10. Next recommended phase

- **Plan-only** additive new-lane DB schema design.
- Do not implement schema yet.
- Keep the baseline `paper_pnl_v1` immutable.
