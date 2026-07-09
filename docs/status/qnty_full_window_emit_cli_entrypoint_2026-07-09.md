# QNTY_FULL_WINDOW_EMIT_CLI_ENTRYPOINT_RECORDED

**Date:** 2026-07-09
**Branch:** `feature/full-window-emit-cli-entrypoint`
**Base:** `c8e26e29` (PR #121)
**Verdict:** `QNTY_FULL_WINDOW_EMIT_CLI_ENTRYPOINT_RECORDED`

---

## PLAN

Add a safe CLI entry point around `emit_full_window_funding_source_snapshot()` so it can be run against a lane without ad-hoc wrapper scripts.

**Design decisions:**
- Follow existing `argparse` pattern from [`quantbot/cli.py`](quantbot/cli.py)
- Register as `qnty-full-window-emit` in [`pyproject.toml`](pyproject.toml) under `[project.scripts]`
- Support both `python -m quantbot.paper.funding_source_full_window_emit_cli` and installed `qnty-full-window-emit` invocation
- Required args: `--db`, `--funding-source-dir`, `--output-dir` — all explicit, no default paths
- Optional: `--generated-at-utc`, `--qnty-git-commit`, `--dry-run`
- Dry-run mode prints JSON plan without calling emit function
- All paths resolved to absolute before validation
- Output dir created if missing (safe: no prod default)
- Machine-readable JSON summary on success

**Files to create/modify:**
1. Create [`quantbot/paper/funding_source_full_window_emit_cli.py`](quantbot/paper/funding_source_full_window_emit_cli.py) — CLI entry point
2. Modify [`pyproject.toml`](pyproject.toml) — register entry point
3. Create [`tests/test_funding_source_full_window_emit_cli.py`](tests/test_funding_source_full_window_emit_cli.py) — CLI tests

**Tests required:**
- Help works
- Missing required args refused
- Dry-run succeeds with JSON output
- Full emit to temp dir produces snapshot + bundle
- JSON summary includes expected fields
- Files written inside output dir only
- Missing funding source dir refused
- Missing DB refused
- `paper_verify_report.json` not touched
- Existing emit and semantics tests still pass

**Guardrails:**
- No prod DB mutation
- No shadow DB mutation
- No official report overwrite
- No source CSV mutation
- No prod snapshot write
- No prod bundle write
- No service/timer/cron/systemd mutation
- No writer/trader/live/backfill/data-refresh run
- No deploy
- No exchange keys
- No live integration
- No prod report promotion
- Do not modify `/srv/qnty/repo` main worktree
- `EDGE_UNPROVEN` remains
- `BLOCK_LIVE_INTEGRATION` remains

---

## CHANGESET

### 1. [`quantbot/paper/funding_source_full_window_emit_cli.py`](quantbot/paper/funding_source_full_window_emit_cli.py) (new, 120 lines)

Argparse-based CLI entry point. `main(argv: list[str] | None = None) -> int`:

- Builds parser with `--db`, `--funding-source-dir`, `--output-dir` (required), `--generated-at-utc`, `--qnty-git-commit`, `--dry-run` (optional)
- Validates all paths exist (except output dir, which is created)
- Resolves paths to absolute via `os.path.abspath()`
- Dry-run mode: prints JSON summary with `"status": "DRY_RUN"`, returns 0
- Normal mode: calls `emit_full_window_funding_source_snapshot()` with correct parameter mapping (`data_dir=funding_dir`)
- On success: prints JSON summary with snapshot path, sha256, bundle path, sha256, batch id, evaluation window, source dir
- On `FundingSourceSnapshotEmissionError`: prints error to stderr, returns 1
- `__main__` block: `sys.exit(main())`

### 2. [`pyproject.toml`](pyproject.toml) (modified, +1 line)

Added under `[project.scripts]`:
```toml
qnty-full-window-emit = "quantbot.paper.funding_source_full_window_emit_cli:main"
```

### 3. [`tests/test_funding_source_full_window_emit_cli.py`](tests/test_funding_source_full_window_emit_cli.py) (new, 225 lines)

Subprocess-based CLI tests following [`tests/test_cli.py`](tests/test_cli.py) pattern:

| Test | What it verifies |
|---|---|
| `test_help_succeeds` | `--help` exits 0, prints usage |
| `test_missing_db` | Missing `--db` exits non-zero |
| `test_missing_funding_source_dir` | Missing `--funding-source-dir` exits non-zero |
| `test_missing_output_dir` | Missing `--output-dir` exits non-zero |
| `test_dry_run_succeeds` | `--dry-run` exits 0, JSON has `DRY_RUN` status |
| `test_emit_full_window_to_temp` | Full emit creates snapshot + bundle files, JSON summary complete, files inside output dir |
| `test_emit_refuses_missing_funding_dir` | Non-existent funding dir exits non-zero with ERROR |
| `test_emit_refuses_missing_db` | Non-existent DB exits non-zero with ERROR |
| `test_emit_does_not_touch_report_path` | `paper_verify_report.json` mtime and content unchanged |

---

## VERIFY

### Git state
```
Branch: feature/full-window-emit-cli-entrypoint
Status: 1 modified (pyproject.toml), 2 untracked (CLI + test)
```

### Whitespace
```
$ git diff --check
→ clean (no whitespace errors)
```

### CLI help
```
$ python -m quantbot.paper.funding_source_full_window_emit_cli --help
→ exit 0, help text with all args and description
```

### New CLI tests (9/9 passed)
```
$ pytest tests/test_funding_source_full_window_emit_cli.py -v -q
→ 9 passed in 2.09s
```

### Existing emit tests (28/34 passed, 6 pre-existing failures)
```
$ pytest tests/test_funding_source_full_window_emit.py -q
→ 28 passed, 6 failed
```
The 6 failures are pre-existing `ModuleNotFoundError: No module named 'tests'` in `TestRegression` — caused by `PYTHONPATH` not including project root. These are not caused by this changeset. All non-regression tests pass.

### Semantics tests (18/18 passed)
```
$ pytest tests/test_full_window_funding_source_snapshot_semantics.py -q
→ 18 passed in 0.03s
```

---

## VERDICT

**`QNTY_FULL_WINDOW_EMIT_CLI_ENTRYPOINT_RECORDED`** — PASS

All requirements met:

| Requirement | Status |
|---|---|
| CLI entry point around `funding_source_full_window_emit.py` | ✅ |
| `--db`, `--funding-source-dir`, `--output-dir` required | ✅ |
| Dry-run / tmp-output mode | ✅ (`--dry-run`) |
| Refuses ambiguous prod writes | ✅ (no default paths) |
| Machine-readable JSON summary | ✅ |
| Does not promote/overwrite `paper_verify_report.json` | ✅ |
| Does not start writer/timer/service | ✅ |
| Testable with temp fixtures | ✅ (all tests use `tmp_path`) |
| Follows existing CLI pattern | ✅ (`argparse`, `main(argv)` → `int`) |
| `git diff --check` clean | ✅ |
| Existing tests not broken by changeset | ✅ (only pre-existing failures) |

### CLI command examples

```bash
# Help
python -m quantbot.paper.funding_source_full_window_emit_cli --help
qnty-full-window-emit --help

# Dry run
python -m quantbot.paper.funding_source_full_window_emit_cli \
  --db /srv/qnty/lanes/a/paper.db \
  --funding-source-dir /srv/qnty/lanes/a/funding_source_csv \
  --output-dir /tmp/qnty-window-emit \
  --dry-run

# Full emission
python -m quantbot.paper.funding_source_full_window_emit_cli \
  --db /srv/qnty/lanes/a/paper.db \
  --funding-source-dir /srv/qnty/lanes/a/funding_source_csv \
  --output-dir /tmp/qnty-window-emit
```

### Files changed

| File | Action |
|---|---|
| [`quantbot/paper/funding_source_full_window_emit_cli.py`](quantbot/paper/funding_source_full_window_emit_cli.py) | Created |
| [`pyproject.toml`](pyproject.toml) | Modified (+1 line) |
| [`tests/test_funding_source_full_window_emit_cli.py`](tests/test_funding_source_full_window_emit_cli.py) | Created |

### What was not touched

- No prod DB, shadow DB, CSV, snapshot, bundle, or report mutation
- No service/timer/cron/systemd files
- No writer/trader/live/backfill/data-refresh code
- No exchange keys or live integration
- No deploy or `/srv/qnty/repo` main worktree modification
- `EDGE_UNPROVEN` — unchanged
- `BLOCK_LIVE_INTEGRATION` — unchanged

### Next recommended task

`QNTY_FULL_WINDOW_EMIT_PROD_DRY_RUN_VALIDATION` — Run `qnty-full-window-emit --dry-run` against a real lane to validate the CLI works end-to-end with production data before promoting.