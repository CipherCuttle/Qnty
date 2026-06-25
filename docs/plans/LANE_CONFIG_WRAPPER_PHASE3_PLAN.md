# Lane Config Files & Writer Launch Wrapper — Phase 3 Plan (PLAN ONLY)

Strategy label: `EDGE_UNPROVEN`

> This is a **plan-only** design receipt. No source code, no writer run, and no
> live/shadow lane run are produced by this document. It records the intended design so
> the implementation slice can be reviewed before any code is written.

## 1. Purpose

- Plan-only design for **lane config sidecar files** and an **init-only writer launch
  wrapper**.
- No code implementation.
- No writer run.
- No live/shadow lane run.
- Strategy label remains `EDGE_UNPROVEN`.

## 2. Current state

- `LaneIdentity` exists.
- `config_hash_v2` exists.
- additive `paper_config` lane columns exist.
- `initialize_lane_database(...)` exists.
- verifier dual-mode lane identity validation exists.
- `ledger_batches.lane_id` stamping exists.
- verifier batch lane consistency exists.
- no lane config sidecar files exist yet.
- no writer launch wrapper exists yet.

## 3. Surface read findings

- `paper_output_dir()` uses `QNTY_PAPER_OUTPUT_DIR` or defaults to
  `/srv/qnty/output/paper_pnl_v1` (`quantbot/paper/__init__.py`).
- DB path uses `QNTY_PAPER_DB_PATH` or defaults to
  `/srv/qnty/output/paper_pnl_v1/paper_ledger.db` (`quantbot/paper/db.py`,
  `DEFAULT_DB_PATH` / `get_paper_db_path()`).
- `paper_config.json` is written/read through `write_config_once(...)` /
  `load_config(...)` (`quantbot/paper/config.py`), where `config_path()` resolves to
  `<output_dir>/paper_config.json`.
- the writer currently loads config through `load_config(paper_output_dir())`
  (`quantbot/paper/sqlite_writer.py`).
- the writer currently relies on env vars for redirection and has no first-class lane
  selection; the in-transaction batch stamp reads `db_config.get("lane_id")`.
- `quantbot/paper/init.py` does **not** exist.
- baseline init precedent is `scripts/qnty-paper-sqlite-init.py`.

## 4. Desired future files

Written only into a **new-lane output dir** (never the baseline dir):

- `paper_config.json`
  - unchanged v1 accounting config.
  - byte-compatible with the baseline config shape (same `build_config()` output).
- `lane_identity.json`
  - `lane_id`
  - `strategy_id`
  - `strategy_version`
- `lane_config_v2.json`
  - `accounting_config_hash_v1`
  - `config_hash_v2`
  - `pre_registration_hash: null`

## 5. Why not put lane identity in `paper_config.json`

- `paper_config.json` is write-once and hash-gated: `load_config()` recomputes
  `config_hash` over its contents and fails closed on any mismatch.
- changing it would mutate the frozen v1 accounting contract (and break the golden hash
  and the `verify.py` byte-for-byte baseline check).
- sidecar files preserve baseline/golden hash compatibility.
- DB identity already uses **additive** columns, not mutated baseline fields — the
  sidecar-file split mirrors that same decision on disk.

## 6. Wrapper / CLI design

- add an init-only CLI, likely: `scripts/qnty-paper-lane-init.py`
  (modeled on `scripts/qnty-paper-sqlite-init.py`).
- require explicit `--output-dir`.
- require explicit `--db-path`.
- accept `--lane-id`, `--strategy-id`, `--strategy-version`.
- validate with `LaneIdentity` (rejects invalid and baseline-impersonating ids).
- build the v1 accounting config with the existing `build_config(...)`.
- compute `accounting_config_hash_v1` (the frozen v1 `config_hash`).
- compute `config_hash_v2` from the v1 hash + `LaneIdentity`.
- write `paper_config.json`, `lane_identity.json`, `lane_config_v2.json`.
- call `initialize_lane_database(...)` (passing the baseline DB path so its own guard
  refuses the baseline).
- verify DB identity read-only after init (`verify_database(...)`).
- stop without running the writer.

## 7. Safety gates

- refuse the baseline output dir.
- refuse the baseline DB path.
- refuse a DB path inside the baseline output dir.
- output dir must be absent/empty unless an explicit init flag is provided.
- DB path must not already exist.
- `lane_id` must not be `paper_pnl_v1`.
- `config_hash_v2` must recompute from the v1 hash + `LaneIdentity`.
- the verifier must pass before the wrapper reports success.
- tests must use temp dirs only.
- no `/srv/qnty` in tests except as rejected/guardrail strings.
- `.claude/` must never be staged.

## 8. Tests for future implementation

- wrapper writes all three files.
- wrapper initializes a lane DB whose DB `paper_config` lane fields match the sidecar
  files.
- verifier passes immediately after initialization.
- baseline output dir refused.
- baseline DB path refused.
- invalid `lane_id` refused.
- `paper_pnl_v1` `lane_id` refused.
- existing DB path refused.
- non-empty output dir refused unless an explicit init flag.
- tampered `lane_config_v2.json` mismatch refused.
- baseline `write_config_once` / `load_config` behavior unchanged.
- no production path mutation.
- no network / subprocess.

## 9. Minimal next implementation slice

- one pure helper plus a thin CLI for **lane initialization only**.
- temp dirs only.
- no writer run.
- no systemd / timer.
- no live/shadow lane.
- no `source_data_digest`.
- no `pre_registration_hash` generation.
- full suite must pass.

## 10. Exclusions

Explicitly excluded:

- production DB
- `/srv/qnty`
- VM / SSH
- systemd / timers / services
- migration / ALTER
- production `paper_pnl_v1`
- `source_data_digest`
- `pre_registration_hash` generation
- V2
- live / shadow lane runs
- cross-lane reporter
- live trading / keys / orders
- profitability or edge claims

## 11. Current verdict

- `LANE_CONFIG_WRAPPER_PLAN_READY`
- `EDGE_UNPROVEN`
- This is only a plan for safe lane initialization.
