# Lane Identity Model — Phase 3 Slice Receipt

Docs-only receipt for the pure lane identity model landed in commit
`8effe2d Add pure paper lane identity model`.

Reference plan: `LANE_IDENTITY_PHASE3_PLAN.md` (slice 2 — pure identity model only).

Strategy label remains `EDGE_UNPROVEN`.

---

## 1. Purpose

This slice implemented **only a pure lane identity model**. It is a **foundation**
for future first-class lane identity. It is **not connected** to the DB schema, the
writer, the verifier, config hashing, or any production lane. Its reason to exist is
a safe, validated value object so future shadow lanes cannot contaminate or
impersonate the clean baseline. No profitability or edge claim is made.

## 2. Files added

- `quantbot/paper/lane_identity.py`
- `tests/test_paper_lane_identity.py`

## 3. Files intentionally NOT changed

- `quantbot/paper/config.py`
- `quantbot/paper/db.py`
- `quantbot/paper/sqlite_writer.py`
- `quantbot/paper/sqlite_verify.py`
- `quantbot/paper/engine.py`
- ops / systemd files
- production configs
- VM files
- production `paper_pnl_v1`

## 4. Model design

- Frozen `LaneIdentity` dataclass (validated on construction; immutable after).
- Fields:
  - `lane_id`
  - `strategy_id`
  - `strategy_version`
  - optional `source_data_digest`
  - optional `pre_registration_hash`
- Stdlib only (`dataclasses` + `re`).
- No I/O.
- No DB.
- No env vars.
- No network.
- No path operations.

## 5. Validation rules

- Non-empty `lane_id` / `strategy_id` / `strategy_version`.
- Conservative charset `[a-z0-9._-]`.
- Rejects whitespace.
- Rejects uppercase.
- Rejects slashes (forward and back).
- Rejects absolute / path-like values.
- Rejects `..` (path traversal).
- Rejects `paper_pnl_v1` as a new non-baseline lane identity (the production
  baseline is implicit v1 and is not instantiated through this model).
- Optional digests must be `None` or a lowercase 64-char SHA-256 hex string.
- Reject-only: values are never silently normalized/mutated.

## 6. Tests covered

- Valid identity object.
- Valid optional digests.
- Empty values reject.
- Whitespace rejects.
- Slash / path-like rejects.
- `..` rejects.
- Uppercase rejects.
- Invalid digest length rejects.
- Invalid digest characters reject.
- Frozen dataclass immutability.
- Baseline-impersonation guard (`paper_pnl_v1` refused).
- Purity scans for forbidden I/O / network / infra tokens.
- No production paths.
- No profit / edge claims.

## 7. Verification results

- Focused identity tests passed: **15**.
- Matched-null regression passed: **12**.
- Full suite via `.venv/bin/python -m pytest -q` passed: **1181**.
- `git diff --check` clean.
- Grep hits were guardrails / negations only (the rejected `paper_pnl_v1` guard
  constant and the purity-test forbidden-token lists; no production DB / network /
  VM / systemd behavior).
- `.claude/` remained untracked.

## 8. Scope exclusions

- No DB schema.
- No migrations.
- No writer changes.
- No verifier changes.
- No `config_hash_v2`.
- No V2.
- No shadow DB writer.
- No cross-lane reporter.
- No VM.
- No systemd.
- No production `paper_pnl_v1`.
- No live trading / exchange keys / real orders.
- No profitability or edge claim.

## 9. Current verdict

`EDGE_UNPROVEN`

This model proves only pure identity validation, **not** strategy quality.

## 10. Next recommended phase

- **Plan-only** `config_hash_v2` helper design.
- Do not implement until the plan is approved.
- Baseline v1 config hash must remain **byte-identical**.
