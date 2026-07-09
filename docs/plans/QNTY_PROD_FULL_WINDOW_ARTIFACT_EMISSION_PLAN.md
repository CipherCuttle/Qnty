# QNTY_PROD_FULL_WINDOW_ARTIFACT_EMISSION_PLAN

**Date:** 2026-07-09
**Branch:** `docs/qnty-prod-full-window-artifact-emission-plan`
**Base:** `origin/main` (commit `0d0af9c0693137471809edb264c6b7ef222017b3` — PR #123 merge)
**VM:** `viktor@37.27.216.174`
**Lane:** `paper_pnl_v1`
**Type:** Plan only — **this document does not perform any emission**

---

## 0. Scope & guardrails (binding)

This is a **docs-only plan** for the *first* controlled prod artifact emission: creating
the full-window funding-source snapshot and its immutable bundle in the prod
`paper_pnl_v1` lane, using the CLI merged in PR #123.

**This task MUST NOT perform the emission.** Execution is deferred to the follow-up task
`QNTY_PROD_FULL_WINDOW_ARTIFACT_EMISSION_EXECUTION`.

Hard guardrails that remain in force for the eventual execution and for this plan:

- Plan only (this document). No prod snapshot written. No prod bundle written.
- No prod DB mutation. No prod report overwrite. No source CSV mutation.
- No writer / trader / live / backfill / data-refresh run.
- No service / timer / cron / systemd change. No deploy. No exchange keys.
- No prod report promotion (official report stays as-is).
- `EDGE_UNPROVEN` remains. `BLOCK_LIVE_INTEGRATION` remains.

> **Nature of the operation.** Snapshot + bundle emission is **additive**: the CLI writes
> new sidecar files into `funding_source_snapshots/` and `funding_source_bundles/`. It
> does **not** touch the ledger DB, the official verify report, or the source CSVs. The
> execution task is therefore a bounded additive write, not a mutation — but the safety
> controls below still treat the DB / report / CSVs as immutable inputs and hash-guard
> them before and after.

---

## 1. Preconditions (all must hold before execution)

| # | Precondition | How to confirm |
|---|--------------|----------------|
| P1 | PR #123 merged; CLI available in `origin/main`. | `git rev-parse origin/main` == `0d0af9c…`; `python3 -m quantbot.paper.funding_source_full_window_emit_cli --help` resolves. |
| P2 | PR #124 dry-run validation recorded. | `docs/status/qnty_full_window_emit_prod_cli_dry_run_validation_2026-07-09.md` present; dry-run returned `status: DRY_RUN`, zero artifacts, hashes unchanged. |
| P3 | Prod DB / report / source CSV hashes captured **before** execution. | See §4 preflight; store SHA256 of DB, report, and all source CSVs. |
| P4 | Safe writer window confirmed. | Confirm no scheduled writer run is imminent; the emission runs entirely inside a window where no writer/trader/backfill can start. |
| P5 | No writer / trader / live / backfill / data-refresh process running. | `pgrep -af` for writer/trader/backfill/data-refresh entrypoints returns nothing; relevant systemd timers/services confirmed idle (read-only inspection only). |
| P6 | Scratch checkout at `origin/main` resolves the CLI, **not** stale `/srv/qnty/repo`. | See §3 — verify module `__file__` points into the scratch checkout. |

If any precondition fails, **stop** and do not proceed to execution.

---

## 2. Exact prod paths

| Role | Path |
|------|------|
| DB | `/srv/qnty/output/paper_pnl_v1/paper_ledger.db` |
| Report | `/srv/qnty/output/paper_pnl_v1/paper_verify_report.json` |
| Source dir | `/srv/qnty/repo/data` |
| Output lane | `/srv/qnty/output/paper_pnl_v1` |
| Snapshot dir | `/srv/qnty/output/paper_pnl_v1/funding_source_snapshots` |
| Bundle dir | `/srv/qnty/output/paper_pnl_v1/funding_source_bundles` |

> **Note on directory names.** The CLI writes into `funding_source_snapshots/` and
> `funding_source_bundles/` (confirmed in `quantbot/paper/funding_source_full_window_emit.py`
> lines 15, 286). The PR #124 dry-run receipt referred to `funding_snapshots/` /
> `funding_bundles/`; that was a receipt-side naming typo, not a code path. The paths in
> the table above are authoritative. Both snapshot and bundle dirs are expected to be
> **absent** in prod today (dry-run receipt confirmed absence) — the emission creates them.

---

## 3. Execution command (for the execution task — do not run here)

1. Create a **fresh scratch worktree** at current `origin/main` on the VM, e.g.
   `/tmp/qnty_prod_full_window_emit_<ts>_worktree` (detached HEAD at `origin/main`).
   Do **not** modify the `/srv/qnty/repo` main worktree.
2. Install the package from the scratch checkout so the module resolves from it
   (`pip install -e . --break-system-packages`, per PR #124 environment notes).
3. **Verify module resolution before writing anything:**
   ```bash
   python3 -c 'import quantbot.paper.funding_source_full_window_emit_cli as m; print(m.__file__)'
   ```
   The printed path MUST be inside the scratch worktree, **not** `/srv/qnty/repo`.
   If it points at `/srv/qnty/repo`, **stop**.
4. Resolve the exact commit to stamp provenance:
   ```bash
   ORIGIN_MAIN_SHA=$(git -C <scratch-worktree> rev-parse HEAD)   # expect 0d0af9c…
   ```
5. Run the CLI **without `--dry-run`**, with explicit output dir:
   ```bash
   python3 -m quantbot.paper.funding_source_full_window_emit_cli \
     --db /srv/qnty/output/paper_pnl_v1/paper_ledger.db \
     --funding-source-dir /srv/qnty/repo/data \
     --output-dir /srv/qnty/output/paper_pnl_v1 \
     --qnty-git-commit <origin/main-sha>
   ```
   (`<origin/main-sha>` = `$ORIGIN_MAIN_SHA`, expected `0d0af9c0693137471809edb264c6b7ef222017b3`.)

> The DB is opened read-only by the emit path; `--output-dir` is the lane root so the CLI
> places sidecars under `funding_source_snapshots/` and `funding_source_bundles/`.

---

## 4. Required safety controls

**Preflight (before running the CLI):**

1. SHA256 all mutable inputs and record them:
   - prod DB `paper_ledger.db`
   - prod report `paper_verify_report.json`
   - every source CSV under `/srv/qnty/repo/data`
2. Record the pre-existing contents (or absence) of `funding_source_snapshots/` and
   `funding_source_bundles/`.
3. Confirm P4/P5 (safe window, no racing process) immediately before the run.

**During / write discipline:**

4. Snapshot and bundle writes must be **additive only** — new files under the two
   sidecar dirs. No existing file may be replaced.
5. No report replacement. No DB write. No CSV write. No service/timer change.

**Postflight (after the CLI exits):**

6. Re-hash prod DB, prod report, and all source CSVs; every hash MUST equal its
   preflight value.
7. Record the **exact emitted file paths and their SHA256** (snapshot sidecar + bundle).
8. Confirm no files were created outside the two expected sidecar dirs.

---

## 5. Acceptance gates (execution task passes only if ALL hold)

| # | Gate |
|---|------|
| A1 | CLI exits 0. |
| A2 | Exactly one full-window snapshot emitted, **or** an existing matching artifact detected (idempotent no-op). |
| A3 | Exactly one immutable bundle emitted, **or** an existing matching artifact detected. |
| A4 | Emitted snapshot has `snapshot_scope: full_window`. |
| A5 | Emitted snapshot window matches the full-ledger prod window. |
| A6 | Emitted provenance has an **absolute** `resolved_funding_source_dir`. |
| A7 | Bundle is content-addressed. |
| A8 | Verifier read-only candidate can select the full-window sidecar. |
| A9 | `funding_source_snapshot_window_mismatch` is gone. |
| A10 | `source_path_unavailable` is gone. |
| A11 | `CLEAN_NET_OF_CARRY` reached in candidate / read-only eval. |
| A12 | Prod DB unchanged (hash equal). |
| A13 | Prod report unchanged (hash equal). |
| A14 | Source CSVs unchanged (all hashes equal). |

> Gates A8–A11 are evaluated with the verifier in **read-only candidate mode** against the
> newly emitted sidecar — they do **not** promote or replace the official report.

---

## 6. Explicit non-goals

- No official prod report promotion.
- No live integration.
- No leverage / shorting.
- No trading.
- No source refresh.

---

## 7. Stop conditions (abort immediately if any occur)

- Any hash drift on DB, report, or source CSVs (pre vs post).
- Any writer / trader / live / backfill / data-refresh process running that could race writes.
- CLI module resolves from the wrong checkout (`/srv/qnty/repo` instead of scratch).
- Emitted files land outside `funding_source_snapshots/` or `funding_source_bundles/`.
- Prod report changes.
- Prod DB changes.
- Source CSVs change.
- Verifier still shows a window/path blocker
  (`funding_source_snapshot_window_mismatch` or `source_path_unavailable`).

On any stop condition: halt, do not attempt cleanup writes to prod, capture state, and
record a receipt describing what happened.

---

## 8. Next task after this plan

```
QNTY_PROD_FULL_WINDOW_ARTIFACT_EMISSION_EXECUTION
```

Executes this plan on the VM, performing the first controlled additive emission under the
§4 safety controls and §5 acceptance gates, and produces a receipt with the emitted file
paths + SHA256 and pre/post hash comparison.

---

## Verdict

```
QNTY_PROD_FULL_WINDOW_ARTIFACT_EMISSION_PLAN_RECORDED
```

Plan recorded. No emission performed. No prod artifacts created. No VM mutation. Prod DB,
report, and source CSVs untouched by this task. `EDGE_UNPROVEN` and
`BLOCK_LIVE_INTEGRATION` remain in force.
