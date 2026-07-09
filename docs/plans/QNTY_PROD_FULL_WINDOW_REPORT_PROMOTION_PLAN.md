# QNTY_PROD_FULL_WINDOW_REPORT_PROMOTION_PLAN

**Date:** 2026-07-09
**Branch:** `docs/qnty-prod-full-window-report-promotion-plan`
**Base:** `origin/main` (commit `5ba505b` — PR #126 merge / execution receipt)
**VM:** `viktor@37.27.216.174`
**Lane:** `paper_pnl_v1`
**Type:** Plan only — **this document does not promote or replace any report**

---

## 0. Scope & guardrails (binding)

This is a **docs-only plan** for promoting the prod `paper_verify_report.json` to the
clean full-window-source **candidate** report. The full-window snapshot + immutable bundle
were emitted additively in `QNTY_PROD_FULL_WINDOW_ARTIFACT_EMISSION_EXECUTION` (PR #126,
merge `dcd028f`), and a read-only candidate verify reached `CLEAN_NET_OF_CARRY` with empty
reason codes. The official published prod report was **not** replaced at that time — it
remains the pre-full-window artifact (sha256 `2c6af12b…10c3`). This plan defines how the
follow-up execution task will replace it, safely and reversibly, with the clean candidate.

**This task MUST NOT promote the report.** Promotion is deferred to the follow-up task
`QNTY_PROD_FULL_WINDOW_REPORT_PROMOTION_EXECUTION`.

Hard guardrails in force for this plan and for the eventual execution:

- Plan only (this document). No report promotion. No prod report overwrite.
- No prod DB mutation. No source CSV mutation. No new snapshots/bundles written.
- No writer / trader / live / backfill / data-refresh run.
- No service / timer / cron / systemd change. No deploy. No exchange keys.
- No live integration. `EDGE_UNPROVEN` remains. `BLOCK_LIVE_INTEGRATION` remains.

> **Nature of the operation.** Report promotion is a **single-file replacement**: the
> official `paper_verify_report.json` is backed up, then atomically replaced by a candidate
> report generated read-only from the already-emitted full-window sidecar. It does **not**
> touch the ledger DB, the source CSVs, or the emitted snapshot/bundle. Those remain
> immutable inputs and are hash-guarded before and after. The only intended state change is
> the report file itself (plus a new timestamped backup).

---

## 1. Preconditions (all must hold before execution)

| # | Precondition | How to confirm |
|---|--------------|----------------|
| P1 | PR #126 merged; execution receipt recorded. | `git merge-base --is-ancestor dcd028f origin/main`; `docs/status/qnty_prod_full_window_artifact_emission_execution_2026-07-09.md` present, verdict `…EXECUTION_RECORDED_CLEAN`. |
| P2 | Full-window snapshot exists in prod lane. | `funding_source_snapshots/funding_source_full_window_snapshot_v1_batch57.json` present; `snapshot_sha256 = 37ef84f3…a6bb`. |
| P3 | Immutable bundle exists in prod lane. | `funding_source_bundles/funding_source_bundle_v1_0a66bb38…8704.json` present; content-addressed `source_bundle_sha256 = 0a66bb38…8704`. |
| P4 | Read-only candidate reaches `CLEAN_NET_OF_CARRY`. | Re-run §3 candidate verify; `funding_clean_carry_decision = CLEAN_NET_OF_CARRY`, reason codes `[]`. |
| P5 | Prod DB / official report / source CSV hashes captured **before** promotion. | See §4 preflight; store SHA256 of DB, official report, all source CSVs. Expect DB `94874dab…bc11`, official report `2c6af12b…10c3`. |
| P6 | No writer / trader / live / backfill / data-refresh process running. | `pgrep -af` for those entrypoints returns nothing; `qnty-paper-pnl` / `qnty-data-refresh` / `qnty-shadow-run` timers confirmed not imminent (read-only inspection only). |
| P7 | Scratch checkout at `origin/main` resolves the verifier, **not** stale `/srv/qnty/repo`. | Module `__file__` points into the scratch worktree (venv is editable-pinned to stale repo — use `/usr/bin/python3` + `PYTHONPATH=<scratch>`, per PR #126 env notes). |

If any precondition fails, **stop** and do not proceed to execution.

---

## 2. Exact prod paths

| Role | Path |
|------|------|
| DB | `/srv/qnty/output/paper_pnl_v1/paper_ledger.db` |
| Official prod report | `/srv/qnty/output/paper_pnl_v1/paper_verify_report.json` |
| Backup report | `/srv/qnty/output/paper_pnl_v1/paper_verify_report.json.bak_<timestamp>` |
| Candidate report (staged **first** under `/tmp`) | `/tmp/paper_verify_report.candidate_<timestamp>.json` |
| Source dir | `/srv/qnty/repo/data` |
| Full-window snapshot | `/srv/qnty/output/paper_pnl_v1/funding_source_snapshots/funding_source_full_window_snapshot_v1_batch57.json` |
| Immutable bundle | `/srv/qnty/output/paper_pnl_v1/funding_source_bundles/funding_source_bundle_v1_0a66bb38…8704.json` |

`<timestamp>` = UTC `YYYYmmddTHHMMSSZ`, identical string for the backup and the candidate of
a given promotion run.

---

## 3. Required command — generate the candidate report (read-only, explicit source dir)

Produce the candidate **into `/tmp` first**; the official report is **not** touched in this
step. The read-only immutable verifier has no write mode, so its `--json` stdout is captured
to the staged candidate path:

```bash
PYTHONPATH=<scratch> /usr/bin/python3 -m quantbot.paper.sqlite_verify \
  --db-path /srv/qnty/output/paper_pnl_v1/paper_ledger.db \
  --data-dir /srv/qnty/repo/data \
  --read-only --json --strict-clean-carry \
  > /tmp/paper_verify_report.candidate_<timestamp>.json
```

- `--read-only` opens `file:<abs>?mode=ro&immutable=1` + `PRAGMA query_only=ON`; it never
  writes `paper_verify_report.json`, receipt, log, `-wal`, or `-shm`.
- `--data-dir /srv/qnty/repo/data` supplies the funding source dir explicitly. Per the PR #126
  documented nuance, the full-window absolute provenance is only consulted when the source dir
  is provided this way; the standard `scripts/qnty-paper-sqlite-verify.py` (no `--data-dir`)
  still reports `source_path_unavailable` and MUST NOT be used to generate the candidate.
- **Do not replace the official report in this step.** The candidate exists only under `/tmp`
  until every §4 gate passes.

> Schema note for the execution task: confirm the captured `--json` payload is a complete
> verify-report document schema-compatible with the current official
> `paper_verify_report.json` (same top-level keys / report shape). If the read-only `--json`
> shape is not a drop-in for the published report schema, **stop** and escalate — do not
> hand-edit or synthesize a report.

---

## 4. Acceptance gates (promotion proceeds only if ALL hold)

Preflight — capture and record before anything else:

- SHA256 of prod DB, official report, and every source CSV under `/srv/qnty/repo/data`.
- Read the DB latest committed batch id and latest funding watermark
  (`SELECT MAX(batch_id) …`; `SELECT MAX(window_end) FROM funding`).

Candidate gates (all evaluated against the staged `/tmp` candidate):

| # | Gate |
|---|------|
| G1 | Candidate latest batch id **equals** DB latest committed batch id (expect `57`). |
| G2 | Candidate latest watermark **equals** DB latest funding watermark (expect `2026-07-09T08:00:00`). |
| G3 | Candidate `status = OK`. |
| G4 | Candidate `failure_count = 0`. |
| G5 | Candidate `funding_clean_carry_decision = CLEAN_NET_OF_CARRY`. |
| G6 | Candidate `funding_clean_carry_reason_codes = []`. |
| G7 | Full-window sidecar **selected** (`full_window_snapshot_selected_path` = batch57 snapshot; `snapshot_status = present_valid`). |
| G8 | `funding_source_snapshot_window_mismatch` **absent** from reason codes. |
| G9 | `source_path_unavailable` **absent** (`source_path_available = True`, mode `explicit_data_dir`). |
| G10 | Prod DB hash **unchanged** vs preflight (`94874dab…bc11`). |
| G11 | Source CSV hashes **unchanged** vs preflight (all 10 funding + ohlcv). |
| G12 | Existing official report backed up (§5 step 1) **before** any replacement. |

If any gate fails, **stop**; do not replace the official report; record a receipt.

---

## 5. Promotion procedure (only after all §4 gates pass)

1. **Backup:** copy the existing official report to a timestamped backup:
   `cp -p /srv/qnty/output/paper_pnl_v1/paper_verify_report.json \
        /srv/qnty/output/paper_pnl_v1/paper_verify_report.json.bak_<timestamp>`
   Record backup sha256; it MUST equal the preflight official-report hash (`2c6af12b…10c3`).
2. **Atomic replace:** copy the staged candidate to a temp file **on the same filesystem** as
   the report, then `mv` (atomic rename) it into place as
   `/srv/qnty/output/paper_pnl_v1/paper_verify_report.json`. No in-place edit; no partial write.
3. **Verify replacement:** sha256 of the now-official report **equals** the candidate sha256.
4. **Verify backup integrity:** sha256 of the backup **equals** the preflight official-report
   hash (`2c6af12b…10c3`).

Only the report file and the new backup change. Nothing else is written.

---

## 6. Postflight (after replacement)

| Check | Expected |
|-------|----------|
| Prod DB `paper_ledger.db` hash | **UNCHANGED** (`94874dab…bc11`) |
| Source CSVs (all 10 funding + 10 ohlcv) | **UNCHANGED** vs preflight |
| Full-window snapshot `…batch57.json` | **UNCHANGED** (`37ef84f3…a6bb`) |
| Immutable bundle `…0a66bb38…8704.json` | **UNCHANGED** (`0a66bb38…8704`) |
| Official report | **EQUALS** candidate (hash match) |
| Backup `…bak_<timestamp>` | **EXISTS**, hash = preflight official report |
| systemd/cron timers | **UNCHANGED** (read-out only) |
| Writer/trader/live/backfill/data-refresh | none spawned during the operation |

Finally, **read the now-official report** and confirm the clean status is published:
`status = OK`, `failure_count = 0`, `funding_clean_carry_decision = CLEAN_NET_OF_CARRY`,
reason codes `[]`.

---

## 7. Explicit non-goals

- No live integration.
- No trading.
- No leverage / shorting.
- No writer / backfill / data-refresh.
- No service / timer / cron / systemd change.

---

## 8. Stop conditions (abort immediately if any occur)

- Any hash drift **except** the intended official-report replacement (DB, source CSVs,
  snapshot, or bundle changes).
- Candidate is not clean (any of G3–G9 fails).
- Candidate / source-dir resolution is caveated (`source_path_unavailable`,
  `funding_source_snapshot_window_mismatch`, or wrong-invocation reliance on
  `scripts/qnty-paper-sqlite-verify.py`).
- Backup step fails, or backup hash ≠ preflight official-report hash.
- Atomic replace fails, or the replace is non-atomic / partial.
- Report after replace does **not** equal the candidate.

On any stop condition: halt, do **not** attempt further prod writes, restore from the backup
if a partial replace occurred, capture state, and record a receipt describing what happened.

---

## 9. Next task after this plan

```
QNTY_PROD_FULL_WINDOW_REPORT_PROMOTION_EXECUTION
```

Executes this plan on the VM: generates the candidate read-only, enforces the §4 gates,
backs up and atomically replaces the official report, and produces a receipt with the
candidate / backup / final-report hashes and the pre/post immutability comparison.

---

## Verdict

```
QNTY_PROD_FULL_WINDOW_REPORT_PROMOTION_PLAN_RECORDED
```

Plan recorded. No report promoted. No prod report overwritten. No prod DB / source CSV /
snapshot / bundle mutation. No VM mutation by this task. `EDGE_UNPROVEN` and
`BLOCK_LIVE_INTEGRATION` remain in force.
