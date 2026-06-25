# Lane Config Init Wrapper — Phase 3 Implementation Receipt

Strategy label: `EDGE_UNPROVEN`

> Docs-only receipt for the temp-safe lane init wrapper slice (implementation commit
> `7ef48b3 Add lane config init wrapper`). It records what shipped and how it was
> verified. No source or test code is changed by this receipt.

## 1. Purpose

- This slice implemented a **temp-safe lane init wrapper**.
- It writes lane sidecar files and initializes a lane DB.
- It verifies the lane DB read-only after initialization.
- It does **not** run the writer.
- It does **not** create or run a real shadow lane.

## 2. Files changed

- `quantbot/paper/lane_init.py`
- `scripts/qnty-paper-lane-init.py`
- `tests/test_paper_lane_init_wrapper.py`

## 3. Files intentionally not changed

- production configs
- VM files
- systemd / timer files
- production DB / output
- writer runtime loop
- `source_data_digest` code
- `pre_registration_hash` generation beyond the `null` sidecar field
- V2 / live / shadow lane runner code
- cross-lane reporter

## 4. Helper behavior

- `init_lane(...)` requires explicit `output_dir` and `db_path`.
- accepts:
  - `lane_id`
  - `strategy_id`
  - `strategy_version`
  - v1 accounting args including `forward_start_ts`
- builds the v1 config using the existing `build_config(...)`.
- validates identity with `LaneIdentity(...)`.
- computes:
  - `accounting_config_hash_v1`
  - `config_hash_v2`
- writes:
  - `paper_config.json`
  - `lane_identity.json`
  - `lane_config_v2.json`
- calls:
  - `initialize_lane_database(..., baseline_db_path=DEFAULT_DB_PATH)`
- performs read-only post-init checks (stored `lane_id` / `config_hash` /
  `config_hash_v2` match, and the read-only verifier passes).
- returns a structured result with paths and hashes.

## 5. Sidecar files

- `paper_config.json`
  - unchanged v1 accounting config only.
  - remains loadable with `load_config(...)`.
  - no lane fields added.
- `lane_identity.json`
  - `lane_id`
  - `strategy_id`
  - `strategy_version`
- `lane_config_v2.json`
  - `accounting_config_hash_v1`
  - `config_hash_v2`
  - `pre_registration_hash: null`

## 6. CLI behavior

- new script: `scripts/qnty-paper-lane-init.py`
- requires explicit:
  - `--output-dir`
  - `--db-path`
  - `--lane-id`
  - `--strategy-id`
  - `--strategy-version`
  - `--forward-start-ts`
- exposes accounting args comparable to the sqlite init script where appropriate.
- prints a safe summary only.
- exits with a refusal code on unsafe input.
- never imports / invokes the writer.
- never starts a writer cycle.
- never touches systemd / timers.

## 7. Safety gates

- refuses the baseline output dir.
- refuses the baseline DB path.
- refuses a DB path inside the baseline output dir.
- refuses an existing DB path.
- refuses a non-empty / existing output conflict.
- refuses an existing `paper_config.json`.
- refuses existing sidecar files.
- refuses an invalid lane id.
- refuses the `paper_pnl_v1` lane id.
- recomputes `config_hash_v2`.
- post-init DB checks must pass before success.
- no env defaults for lane init.
- explicit paths only.

## 8. Tests covered

- helper writes all three files.
- `paper_config.json` is loadable.
- `lane_identity.json` has the exact identity fields.
- `lane_config_v2.json` has v1 hash, v2 hash, and `pre_registration_hash: null`.
- lane DB `paper_config` row has matching lane fields.
- read-only verifier passes after init.
- baseline output dir rejected.
- baseline DB path rejected.
- DB path inside baseline output dir rejected.
- invalid lane id rejected.
- `paper_pnl_v1` lane id rejected.
- existing DB path rejected.
- pre-existing sidecar / config file rejected.
- no writer run invoked.
- no production path mutation.
- no network / subprocess.

## 9. Verification results

- `tests/test_paper_lane_init_wrapper.py`: **14 passed**.
- targeted regressions: **40 passed**.
- full suite: **1256 passed**.
- `git diff --check`: clean.
- claims grep: no hits.
- source module + CLI infra grep: zero hits.
- test infra hits were only disclaimers / the rejected lane id.
- no writer run.
- no production mutation.
- no VM / systemd / network.
- no ALTER.
- `.claude/` remained untracked.

## 10. Scope exclusions

Explicitly excluded:

- production DB
- `/srv/qnty`
- VM / SSH
- systemd / timers / services
- migration / ALTER
- production `paper_pnl_v1`
- writer run
- real shadow output directory
- `source_data_digest`
- `pre_registration_hash` generation beyond the `null` sidecar
- V2
- live / shadow lane runs
- cross-lane reporter
- live trading / keys / orders
- profitability or edge claims

## 11. Current verdict

- `EDGE_UNPROVEN`
- This proves temp-safe lane initialization only, **not** strategy quality.
- No live/shadow lane has been run.

## 12. Next recommended phase

- Open a PR for this implementation + receipt.
- After merge, a **plan-only** temp end-to-end proof may be considered:
  lane init → verify DB → maybe synthetic / batchless checks only.
- Do **not** run live/shadow lanes yet.
