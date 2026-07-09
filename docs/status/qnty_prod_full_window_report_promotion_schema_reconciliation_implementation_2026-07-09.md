# QNTY_PROD_FULL_WINDOW_REPORT_PROMOTION_SCHEMA_RECONCILIATION_IMPLEMENTED

- **Date:** 2026-07-09
- **Branch:** `feature/qnty-publish-schema-candidate-report-output`
- **Task:** `QNTY_PROD_FULL_WINDOW_REPORT_PROMOTION_SCHEMA_RECONCILIATION_IMPLEMENTATION`
- **Verdict:** `QNTY_PROD_FULL_WINDOW_REPORT_PROMOTION_SCHEMA_RECONCILIATION_IMPLEMENTED`
- **Guardrails preserved:** `EDGE_UNPROVEN`, `BLOCK_LIVE_INTEGRATION`.

## Problem (recap)

`quantbot/paper/sqlite_verify.py` had two disjoint assembly paths:

- **Published report:** `verify_and_publish()` → `_build_published_report()` — the
  authoritative 42-key envelope (`authoritative` / `trusted` / `content_digests` /
  `snapshot_identity` / `verifier` / …). Opens the DB via `_open_snapshot`
  (plain `mode=ro`) and does **not** accept `--data-dir`.
- **Diagnostic CLI:** `main()` → `_cli_report()` — a narrower diagnostics shape.
  Accepts `--data-dir` and the immutable read-only URI, so a full-window
  `CLEAN_NET_OF_CARRY` was reachable **only** here, in a shape that is not the
  publication schema.

Net effect: the clean full-window verdict could not be expressed in a
publication-schema-compatible report without hand-synthesizing one (forbidden).

## Change

Added a **candidate publication** layer to `sqlite_verify.py` that reuses the
authoritative envelope builder, honors `--data-dir`, and writes only to a vetted
non-prod path — never publishing/overwriting the prod report.

New public surface:

- `verify_and_publish_candidate(db_path, candidate_report_out, *, data_dir=None,
  now=None, allow_prod_lane=False) -> (VerifyResult, Path)`
  - Opens the DB via `_open_readonly_immutable_connection`
    (`file:<abs>?mode=ro&immutable=1` + `PRAGMA query_only=ON`).
  - Runs `_verify_connection(..., data_dir=…, fail_on_source_path_unavailable=True)`
    → preserves full-window snapshot/bundle selection + clean-carry semantics.
  - Builds the envelope with the **same** `_build_published_report()` used by
    `verify_and_publish` (schema never hand-duplicated).
  - Writes **only** the candidate json (no `REPORT_FILE`/`RECEIPT_FILE`/`LOG_FILE`).
- `assert_safe_candidate_output_path(path, *, allow_prod_lane=False)` — anti-footgun:
  refuses empty/relative paths, the exact `OFFICIAL_PROD_REPORT_PATH`
  (`/srv/qnty/output/paper_pnl_v1/paper_verify_report.json`), any path inside
  `PROD_LANE_DIR` (unless `allow_prod_lane`), and a nonexistent parent that is not
  under `/tmp` (only `/tmp` parents are auto-created). Fails closed.
- `compare_published_report_schema(...)` / `assert_candidate_report_schema(...)` —
  top-level key-set schema gate vs a reference published report, with
  `allow_missing` / `allow_extra` whitelists reserved for an explicitly-planned
  future migration.
- CLI flags: `--candidate-report-out <path>` (+ existing `--data-dir`) and
  `--allow-prod-lane`. In candidate mode `main()` writes the envelope to the
  vetted path and echoes it to stdout (with a non-persisted `candidate_report_path`
  convenience key; the on-disk file keeps the exact 42-key schema).

## Verification ladder

1. Import check — `IMPORT_OK`; candidate symbols import.
2. New tests — `tests/test_paper_sqlite_verify_candidate_publication.py`: **12 passed**.
   Covers: authoritative-envelope reuse, candidate keys == reference published
   report keys, schema-gate missing/extra detection, `--data-dir` →
   `explicit_data_dir` + `source_path_available`, refuses official report path,
   refuses prod-lane path unless allowed, no prod-artifact publish, full-window
   `CLEAN_NET_OF_CARRY` preserved in candidate mode, and `verify_and_publish`
   regression (still publishes report/receipt/log).
3. Existing sqlite_verify suites — `clean_net_of_carry_gate`,
   `source_path_resolution`, `batch_scoped_clean_carry`, `read_only_cli_contract`,
   `git_provenance` all pass. The 26 failures in `test_paper_sqlite_verify.py` /
   `test_paper_sqlite_verify_report.py` are **pre-existing on `main`** (writer
   fixture reads a relative `data/…` CSV that requires a specific cwd) — identical
   failure set before and after this change; not introduced here.
4. End-to-end CLI smoke — `--candidate-report-out` under `/tmp` → exit 0, 42 keys,
   `authoritative:true`, `source_path_available:true`, `explicit_data_dir`, and no
   `paper_verify_report.json` written next to the DB.
5. `git diff --check` — clean.

## Guardrails honored

No prod report promotion/overwrite; no prod DB / CSV / snapshot / bundle / shadow
mutation; no writer/trader/live/backfill/data-refresh run; no service/timer/cron/
systemd change; no deploy; no exchange keys; no published report hand-edited or
synthesized. All tests operate on tmp-path fixtures. `EDGE_UNPROVEN` and
`BLOCK_LIVE_INTEGRATION` remain.

## Not done (out of scope, by design)

Actual promotion of a clean full-window candidate into the prod lane
(`allow_prod_lane` opt-in path) is a separate, explicitly-planned future task.
This change only makes a schema-compatible candidate **producible** to `/tmp`.
