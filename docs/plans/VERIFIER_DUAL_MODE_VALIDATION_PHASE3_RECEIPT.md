# Verifier Dual-Mode Validation — Phase 3 Receipt

## 1. Purpose

- This slice added verifier dual-mode lane identity validation.
- It closes the silent gap where lane fields could be ignored.
- It is **not** writer runtime wiring.
- It is **not** batch stamping.
- It is **not** a live/shadow lane.

## 2. Files changed

- `quantbot/paper/sqlite_verify.py`
- `tests/test_paper_verify_lane_identity.py`

## 3. Files intentionally not changed

- `quantbot/paper/db.py`
- `quantbot/paper/sqlite_writer.py`
- `quantbot/paper/config.py`
- `quantbot/paper/engine.py`
- ops/systemd files
- production configs
- VM files
- production DB/output

## 4. Verifier design

- Added lane identity validation helper.
- Mode detected by lane fields, **not** DB schema version.
- v1 mode: absent/all-NULL lane fields → existing checks unchanged.
- v2/new-lane mode: lane fields present → validate `LaneIdentity`, recompute `config_hash_v2`, compare stored value.
- `db_schema_version` exact check retained.
- Existing v1 accounting checks still run.

## 5. Fail-closed behavior

- Missing `strategy_id` fails.
- Missing `strategy_version` fails.
- Missing `config_hash_v2` fails.
- Partial lane fields fail.
- Invalid `lane_id` fails.
- Baseline-impersonating lane id fails.
- `config_hash_v2` mismatch fails.
- Non-null `pre_registration_hash` fails for now because generation is deferred.

## 6. Tests covered

- Old v1 DB verifies.
- v1 DB with NULL lane fields verifies.
- New-lane DB verifies.
- Missing `strategy_id` fails.
- Missing `strategy_version` fails.
- Missing `config_hash_v2` fails.
- Lane-id-only partial fails.
- Strategy-id-only partial fails.
- Invalid `lane_id` fails.
- Baseline-impersonating lane id fails.
- `config_hash_v2` mismatch fails.
- Non-null `pre_registration_hash` fails.
- Golden v1 hash remains unchanged.

## 7. Verification results

- Verifier lane identity tests: 16 passed.
- Regression group: 22 passed.
- Full suite: 1232 passed.
- `git diff --check`: clean.
- Verifier diff additive-only.
- No edge/live grep hits.
- `sqlite_verify.py` had no production/infra grep hits.
- `.claude/` remained untracked.

## 8. Scope exclusions

- No production DB.
- No `/srv/qnty`.
- No VM/SSH.
- No systemd/timers.
- No migration/ALTER.
- No production `paper_pnl_v1`.
- No writer runtime loop changes.
- No ledger batch lane stamping.
- No source_data_digest.
- No pre_registration_hash generation.
- No V2.
- No live/shadow lanes.
- No cross-lane reporter.
- No live trading / keys / orders.
- No profitability or edge claims.

## 9. Current verdict

- `EDGE_UNPROVEN`
- This proves verifier identity safety only, not strategy quality.

## 10. Next recommended phase

- Plan-only ledger batch lane stamping.
- Do not implement batch stamping until plan is approved.
- Keep source_data_digest separate/deferred.
