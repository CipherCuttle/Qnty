# QNTY_PROD_FULL_WINDOW_PUBLICATION_CANDIDATE_VM_VALIDATION

- **Date:** 2026-07-09
- **Branch:** `docs/qnty-prod-full-window-publication-candidate-vm-validation`
- **Task:** `QNTY_PROD_FULL_WINDOW_PUBLICATION_CANDIDATE_VM_VALIDATION`
- **Verdict:** `QNTY_PROD_FULL_WINDOW_PUBLICATION_CANDIDATE_VM_VALIDATION_RECORDED_CLEAN`
- **Guardrails preserved:** `EDGE_UNPROVEN`, `BLOCK_LIVE_INTEGRATION`.
- **Depends on:** PR #130 merge `f8f0eefce291646152e20c5ab1c12c8a69e4c3ac`
  (`QNTY_PROD_FULL_WINDOW_REPORT_PROMOTION_SCHEMA_RECONCILIATION_IMPLEMENTED`).

## Goal

Validate the newly merged publication-schema candidate producer
(`verify_and_publish_candidate` + `--candidate-report-out` CLI) on the VM against
the **real** prod `paper_pnl_v1` lane: produce a schema-compatible candidate report
under `/tmp`, confirm it matches the official report schema and reaches
`CLEAN_NET_OF_CARRY` on the full window, and prove **zero** mutation of the prod
report / DB / CSVs / snapshots / bundles. **Candidate validation only — no promotion.**

## Environment

- VM: `viktor@37.27.216.174` (`ubuntu-4gb-hel1-1-qnty`), `/usr/bin/python3` = 3.12.3.
- `origin/main` HEAD = PR #130 merge `f8f0eefce291646152e20c5ab1c12c8a69e4c3ac`
  (confirmed local ancestor check + VM checkout HEAD).
- Scratch checkout: `/tmp/qnty_scratch_pubcand_20260709T204242Z`, `git checkout`
  pinned at `f8f0eef` (fetched from `origin`). `/srv/qnty/repo` is stale at
  `2bd8843` and was **not** used for module resolution and **not** mutated.
- Module resolution confirmed from scratch:
  `/tmp/qnty_scratch_pubcand_20260709T204242Z/quantbot/paper/sqlite_verify.py`,
  `hasattr(verify_and_publish_candidate) == True`.

## Preflight (immutability baseline)

- prod DB `paper_ledger.db` sha256 =
  `94874dab6d82701785fdf7379777b3e8a5850c3f869a42625edd90dcdc18bc11`
- official report `paper_verify_report.json` sha256 =
  `2c6af12ba74d92b52d827263225760145c5e7c2eef5b6053ff18779a8f9c10c3`
- 20 source CSVs under `/srv/qnty/repo/data` hashed; 20 snapshot files
  (incl. `funding_source_full_window_snapshot_v1_batch57.json`) + 1 bundle hashed.
- **Aggregate fingerprint** (DB + report + all CSV/snapshot/bundle hashes,
  sha256 of the concatenation) =
  `88f371a1d57eb96f8c5e10145ef009a09d5f8b1a6c276cc1ea95b6ed78d43436`
- No `writer`/`trader`/`live`/`backfill`/`data-refresh` process running
  (`NONE_RUNNING`). Next `qnty-paper-pnl.timer` fire was 3h38m out; validation
  completed well before it. Timers were **listed only**, never mutated.

## Candidate generation (under `/tmp` only)

Actual merged CLI signature requires `--db-path` (not positional) plus required
`--read-only --json`. Command run from scratch checkout:

```bash
TS=20260709T204327Z
CANDIDATE=/tmp/qnty_prod_full_window_publication_candidate_${TS}.json
PYTHONPATH="$SCRATCH" /usr/bin/python3 -m quantbot.paper.sqlite_verify \
  --read-only --json \
  --db-path  /srv/qnty/output/paper_pnl_v1/paper_ledger.db \
  --data-dir /srv/qnty/repo/data \
  --candidate-report-out "$CANDIDATE" \
  > /tmp/qnty_prod_full_window_publication_candidate_stdout_${TS}.json
```

- Exit code `0`, empty stderr. Candidate written: 62088 bytes, `/tmp` only.
- **No** `--allow-prod-lane`. **No** `paper_verify_report.json`/receipt/log written
  next to the DB (prod lane still holds only `paper_config.json` + the original
  `paper_verify_report.json`).

## Candidate validation (vs official prod report)

- Top-level key count: candidate **42** == official **42**; **KEY_SETS_EQUAL: True**
  (`only_in_candidate: []`, `only_in_official: []`).
- Required publication keys present: `authoritative`, `trusted`, `content_digests`,
  `content_sha256`, `snapshot_identity`, `verifier` — all `True`.
- `status = OK`, `failure_count = 0`, `authoritative = True`, `trusted = True`.
- `funding_clean_carry_decision = CLEAN_NET_OF_CARRY`;
  `funding_clean_carry_reason_codes = []`,
  `funding_clean_carry_batch_reason_codes = []`.
- Full-window selection (`funding_clean_carry` block):
  `full_window_scope_required = True`,
  `full_window_snapshot_selected_path =
  /srv/qnty/output/paper_pnl_v1/funding_source_snapshots/funding_source_full_window_snapshot_v1_batch57.json`,
  `funding_coverage_decision = complete`, `arithmetic_ok = True`.
- Source path via explicit data dir: `source_path_available = True`,
  `source_path_required = True`,
  `source_path_resolution_mode = explicit_data_dir`,
  `resolved_funding_source_dir = /srv/qnty/repo/data`.
- Absence checks: no `*snapshot_window_mismatch*` key present, no
  `*source_path_unavailable*` key present.

## Anti-footgun validation

- **Refuses official prod report path** as `--candidate-report-out`: exit `2`,
  `error: candidate report output must not equal the official prod report path
  /srv/qnty/output/paper_pnl_v1/paper_verify_report.json`. Official report hash
  unchanged.
- **Refuses prod-lane path without `--allow-prod-lane`**: exit `2`,
  `error: candidate report output …/qnty_footgun_test_should_not_exist.json is
  inside the prod lane dir …; refusing unless explicitly allowed`. Target file
  **confirmed absent** (fail-closed before any write).
- `--allow-prod-lane` was **never** used at any point.

## Postflight (immutability confirmation)

- prod DB sha256 =
  `94874dab6d82701785fdf7379777b3e8a5850c3f869a42625edd90dcdc18bc11` — **unchanged**.
- official report sha256 =
  `2c6af12ba74d92b52d827263225760145c5e7c2eef5b6053ff18779a8f9c10c3` — **unchanged**.
- **Aggregate fingerprint** (all CSV/snapshot/bundle) =
  `88f371a1d57eb96f8c5e10145ef009a09d5f8b1a6c276cc1ea95b6ed78d43436` —
  **identical PRE == POST → `AGGREGATE_UNCHANGED_CLEAN`**.
- Snapshot count 20, bundle count 1 — unchanged. No stray candidate/report json in
  the prod lane. No systemd service/timer touched.
- Scratch checkout removed (`SCRATCH_REMOVED`); `/srv/qnty/repo` still `2bd8843`,
  `git status` clean.

## Guardrails honored

Candidate validation only. Candidate generated **only** under `/tmp`. No
`--allow-prod-lane`. No prod report overwrite/promotion; no prod DB / CSV /
snapshot / bundle / shadow mutation; no writer/trader/live/backfill/data-refresh
run; no service/timer/cron/systemd change; no deploy; no exchange keys; no live
integration; no report hand-edited or synthesized. `EDGE_UNPROVEN` and
`BLOCK_LIVE_INTEGRATION` remain.

## Verdict

`QNTY_PROD_FULL_WINDOW_PUBLICATION_CANDIDATE_VM_VALIDATION_RECORDED_CLEAN`

The merged publication-schema candidate producer, run read-only against the real
prod `paper_pnl_v1` lane with `--data-dir`, emits a 42-key publication-schema
envelope byte-identical in key-set to the official report, reaches full-window
`CLEAN_NET_OF_CARRY`, honors its anti-footgun output guards, and mutates nothing in
prod. Actual promotion into the prod lane remains a separate, explicitly-planned
future task and was **not** performed.
