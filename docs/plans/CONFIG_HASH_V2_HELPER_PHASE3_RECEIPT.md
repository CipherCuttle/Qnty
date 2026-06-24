# config_hash_v2 Helper — Phase 3 Slice Receipt

Docs-only receipt for the pure `config_hash_v2` helper landed in commit
`15134dc Add pure lane config hash v2 helper`.

Reference plan: `CONFIG_HASH_V2_PHASE3_PLAN.md` (slice 3 — pure helper only).

Strategy label remains `EDGE_UNPROVEN`.

---

## 1. Purpose

This slice implemented **only the pure `config_hash_v2` helper**. It is a
**foundation** for future new-lane identity. It is **not connected** to `config.py`,
the DB schema, the writer, the verifier, `source_data_digest`,
`pre_registration_hash`, or any production lane. Its reason to exist is a pure,
auditable composition of a lane-aware identity hash over a frozen v1 accounting hash,
so the production baseline stays byte-identical. No profitability or edge claim is
made.

## 2. Files added

- `quantbot/paper/lane_config_hash.py`
- `tests/test_paper_lane_config_hash.py`

## 3. Files intentionally NOT changed

- `quantbot/paper/config.py`
- `quantbot/paper/db.py`
- `quantbot/paper/sqlite_writer.py`
- `quantbot/paper/sqlite_verify.py`
- `quantbot/paper/engine.py`
- DB schema files
- ops / systemd files
- production configs
- VM files
- production `paper_pnl_v1`

## 4. Helper design

- `config_hash_v2_payload(accounting_config_hash_v1, identity)`
- `config_hash_v2(accounting_config_hash_v1, identity)`
- Exact payload:

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

- SHA-256 over canonical JSON (`canonical_json_dumps`).
- Consumes the v1 hash as a validated string.
- Imports `LaneIdentity` (from `quantbot.paper.lane_identity`).
- Does **not** import `config.py`.
- Does **not** call `build_config`.
- Does **not** call the existing `config_hash`.
- Does **not** alter v1 behavior.

## 5. Explicit exclusions from the helper payload

- No `source_data_digest`.
- No `pre_registration_hash`.
- No `paper_engine_version`.
- No `schema_version`.
- No `db_schema_version`.

## 6. Validation / purity rules

- `accounting_config_hash_v1` must be a lowercase 64-char SHA-256 hex string.
- Uppercase v1 hash rejected.
- Invalid length rejected.
- Invalid characters rejected.
- No I/O.
- No DB.
- No env vars.
- No network.
- No production paths.

## 7. Tests covered

- Exact payload shape.
- Deterministic hash.
- Explicit SHA-256 expected value.
- Hash changes when `lane_id` changes.
- Hash changes when `strategy_id` changes.
- Hash changes when `strategy_version` changes.
- Hash changes when the v1 hash changes.
- Invalid v1 hash length rejects.
- Invalid v1 hash characters reject.
- Uppercase v1 hash rejects.
- Payload excludes `source_data_digest`.
- Payload excludes `pre_registration_hash`.
- Payload excludes engine / schema / db versions.
- Helper purity scan (no config / db / infra imports; no production paths/claims).
- Baseline-protection test: uses `build_config` **in the test only** to prove the v1
  config dict and v1 hash are unchanged (and still self-consistent) after computing
  a v2 hash.

## 8. Verification results

- Focused helper tests: **13 passed**.
- Lane identity + matched-null regression: **27 passed**.
- Full suite via `.venv/bin/python -m pytest -q`: **1194 passed**.
- `git diff --check`: clean.
- Claims grep hits were test-only guardrails / negations.
- Infra grep hits were test-only guardrails / negations (the permitted test-only
  `build_config` import + the purity-test forbidden-token lists).
- Helper module had **zero** infra / claim grep hits.
- `.claude/` remained untracked.

## 9. Scope exclusions

- No DB schema.
- No migrations.
- No writer changes.
- No verifier changes.
- No `source_data_digest`.
- No `pre_registration_hash` implementation.
- No V2.
- No shadow DB writer.
- No cross-lane reporter.
- No VM.
- No systemd.
- No production `paper_pnl_v1`.
- No live trading / exchange keys / real orders.
- No profitability or edge claim.

## 10. Current verdict

`EDGE_UNPROVEN`

This helper proves only pure lane-aware config identity hashing, **not** strategy
quality.

## 11. Next recommended phase

- **Plan-only** baseline v1 unchanged / golden-hash proof slice.
- Do not implement DB schema yet.
- Do not connect the helper to `config.py` / writer / verifier yet.
