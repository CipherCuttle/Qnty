# QNTY_PROD_FULL_WINDOW_REPORT_PROMOTION_SCHEMA_RECONCILIATION_PLAN

**Date:** 2026-07-09
**Branch:** `docs/qnty-prod-full-window-report-promotion-schema-reconciliation-plan`
**Base:** `origin/main` (commit `7414783` — PR #127 merge; local HEAD `5340431` PR #128 halt receipt)
**VM:** `viktor@37.27.216.174`
**Lane:** `paper_pnl_v1`
**Type:** Plan only — **this document does not promote, generate, or replace any report**

---

## 0. Scope & guardrails (binding)

The prior execution (`QNTY_PROD_FULL_WINDOW_REPORT_PROMOTION_EXECUTION`, PR #128) **halted before
any mutation** on the plan's own schema-compatibility gate: the read-only
`python -m quantbot.paper.sqlite_verify --json` payload (36 top-level keys) is **not** a drop-in
for the published official `paper_verify_report.json` (42 top-level keys). All data/DB acceptance
gates (G1–G11) passed and the read-only candidate reached `CLEAN_NET_OF_CARRY` with empty reason
codes, but promoting the CLI payload would strip publication/provenance metadata and inject
read-only diagnostic fields — a semantic downgrade, not a replacement.

This plan defines **how a future execution task will generate a candidate report that is
schema-compatible with the published `paper_verify_report.json` while preserving full-window
clean-carry semantics**, without hand-editing or synthesizing a report. It is the prerequisite
for re-attempting `QNTY_PROD_FULL_WINDOW_REPORT_PROMOTION_EXECUTION`.

**This task MUST NOT promote or generate any report.** It records a plan only.

Hard guardrails in force for this plan and for the eventual execution:

- Plan only (this document). No report promotion. No prod report overwrite.
- Do not synthesize or hand-edit a published report.
- No prod DB mutation. No source CSV mutation. No new snapshots/bundles written. No shadow mutation.
- No writer / trader / live / backfill / data-refresh run.
- No service / timer / cron / systemd change. No deploy. No exchange keys.
- No live integration. `EDGE_UNPROVEN` remains. `BLOCK_LIVE_INTEGRATION` remains.

---

## 1. PLAN (summary)

1. Confirm the authoritative publish-schema producer and the diagnostic CLI producer are **both**
   in `quantbot/paper/sqlite_verify.py`, and that the 42/36 key gap is structural (§2–§4).
2. Decide the candidate-generation approach (§5). **Chosen: Approach A** — a read-only,
   candidate-output mode of the publication-schema producer (`_build_published_report` envelope)
   that (a) takes an explicit `--data-dir`, (b) routes verification through the same clean-carry /
   full-window parameters the read-only CLI uses, (c) computes content digests, (d) writes to an
   explicit non-prod (`/tmp`) output dir, and (e) never touches the official report.
3. Add a **schema-equality gate** (candidate top-level key set == official key set) plus the data
   gates (§6).
4. Define the tests required before any execution (§7).
5. Hand off to the execution task (§9). No code is written or run by **this** task.

---

## 2. Root cause of the schema mismatch

Both report shapes are produced by the **same module**, `quantbot/paper/sqlite_verify.py`, through
**two different assembly paths**:

| Producer | Function | Output | Shape |
|----------|----------|--------|-------|
| **Publication** (authoritative) | `verify_and_publish()` → `_build_published_report()` (line ~3311) | writes `paper_verify_report.json` / receipt / log | 42-key **envelope + metrics** |
| **Diagnostic CLI** (read-only) | `main()` → `_cli_report()` (line ~3700) via `verify_database_readonly_cli()` | prints JSON to stdout only | 36-key **raw metrics + CLI diagnostics** |

- `_build_published_report()` wraps a `VerifyResult` in a fixed authoritative **envelope**
  (`schema_version`, `verifier`, `verifier_version`, `authoritative`, `verified_at`, `db_path`,
  `status`, `exit_code`, `trusted`, `failure_count`, `failures`, `content_digests`,
  `content_sha256`, `snapshot_identity`, `current_verdict`, `disclaimer`), then merges the core
  `result.report` metrics via `report.setdefault(k, v)`. This is the published file's shape.
- `_cli_report()` does **not** wrap in that envelope. It returns `dict(result.report)` (the raw
  core metrics) plus six read-only-diagnostic keys, and prints it. Its help text is explicit: the
  CLI "never creates … `paper_verify_report.json`/receipt/log files (that is
  `verify_and_publish`'s job, not this CLI's)."

The clean full-window `CLEAN_NET_OF_CARRY` result is currently only reachable through the **CLI
path** (`verify_database_readonly_cli` → `_verify_connection` with `data_dir=<source dir>`,
`allow_db_relative_data=True`, `fail_on_source_path_unavailable=True`, and immutable read-only URI).
The **publication path** (`verify_and_publish`) calls `_verify_connection(conn, Path(db_path))` with
**no** `data_dir` and default resolution — which is why the current official report carries
`funding_clean_carry_decision = CAVEATED_ENGINE_SEMANTICS`. Additionally `verify_and_publish`
defaults its `output_dir` to the DB's directory, so an unmodified call would overwrite the prod
official report.

**Root cause, one line:** the 42-key publication envelope and the full-window clean-carry
`--data-dir` verification live on **different code paths**; no single existing path produces *both*
the publication schema *and* the clean-carry full-window result into a non-prod location.

---

## 3. Authoritative publish-schema source (documented exactly)

- Module: `quantbot/paper/sqlite_verify.py`
- Publisher function: `verify_and_publish(db_path, output_dir, *, now=None, write_log=True)`
  (~line 3498) — "the only component allowed to publish an authoritative paper status."
- Envelope builder: `_build_published_report(db_path, result, digests, now)` (~line 3311).
- Digest source: `_content_digests(conn)` (~line 3280) — requires the live validated connection.
- Report file constant: `REPORT_FILE = "paper_verify_report.json"` (line 209).
- Schema/version constants: `SCHEMA_VERSION` (imported from `quantbot.paper.__init__`, = `1`),
  `SQLITE_VERIFIER_VERSION = "1.0.0"` (line 208), `VERIFIER_DISCLAIMER` (line 197).
- Core verification (shared by both paths): `_verify_connection(conn, db_path, *, data_dir=None,
  allow_db_relative_data=True, fail_on_source_path_unavailable=False, source_mode="live-current")`
  (~line 3057). Full-window sidecar scope is **auto-selected** inside this call via
  `_full_ledger_requires_full_window_scope(conn)` when the ledger spans multiple batches.

The **diagnostic** producer to be reconciled *against* (not promoted): `main()` (~line 3719) →
`verify_database_readonly_cli()` (~line 3596) → `_cli_report()` (~line 3700). This is the current
plan §3 command; it is correct for a read-only audit but is **not** the publication producer.

---

## 4. Why 36 vs 42, and the exact key delta

Confirmed against PR #128's captured diff (official 42 keys, candidate 36 keys, 30 shared):

**In official, NOT in the read-only CLI candidate (12 — publication/provenance envelope fields):**
`authoritative`, `content_digests`, `content_sha256`, `current_verdict`, `exit_code`, `failures`
(enriched), `schema_version`, `snapshot_identity`, `trusted`, `verified_at`, `verifier`,
`verifier_version`.

All twelve are added **only** by `_build_published_report()`. `content_digests` / `content_sha256`
in particular require a `_content_digests(conn)` call that the CLI path never makes.

**In the CLI candidate, NOT in official (6 — read-only-CLI diagnostic fields):**
`db_mutation_performed`, `query_only_pragma_enabled`, `read_only`, `sqlite_open_mode`,
`verifier_cli_contract_version`, `wal_shm_files_created`.

All six are injected **only** by `_cli_report()`.

**Consequence for reconciliation:** a candidate produced by `_build_published_report()` (Approach A)
will carry all 12 envelope keys and will **not** carry the 6 CLI-only diagnostics — i.e. it targets
the official key set directly, by construction, with no hand-editing.

> **Residual key-set risk to be checked at execution (do not assume it away).** The current
> official report was published *without* `--data-dir` (CAVEATED, default source resolution). The
> candidate will be produced *with* an explicit `--data-dir` and full-window scope selected. Those
> two modes can differ not only in **values** (e.g. `source_path_resolution_mode` =
> `snapshot_provenance` vs `explicit_data_dir`; `funding_clean_carry_decision` = CAVEATED vs
> CLEAN) but potentially in **which top-level keys are present** (e.g. full-window-scope fields such
> as `full_window_scope_required` / `full_window_snapshot_selected_path`). The schema-equality gate
> (§6 G-S1) exists precisely to surface any such additive/removed keys. If the clean-carry path
> introduces top-level keys absent from the current official report, execution **stops** unless a
> documented, explicitly-approved additive schema-version migration covers them (§6 note).

---

## 5. Candidate-generation options considered

**Approach A — read-only candidate-output mode of the publication producer (CHOSEN).**
Add the smallest code change that lets the publication-schema producer run in a *candidate/staging*
mode: explicit `--data-dir`, the clean-carry / full-window verification parameters, content digests,
`_build_published_report` envelope, and an **explicit non-prod output dir** (default `/tmp`), with a
hard refusal to write into the DB's own directory or to overwrite `paper_verify_report.json`.
- *Pros:* produces the exact 42-key publication envelope by construction; single validated
  connection → correct `content_digests`; reuses all existing verification logic; read-only; no
  official-report write. Smallest honest diff.
- *Cons:* requires a small, tested code change (new params / thin wrapper + a schema-equality gate
  and an anti-overwrite guard). Must add tests.

**Approach B — post-process merge of the read-only CLI payload into the envelope.**
Take the CLI's clean-carry `result.report` and feed it through `_build_published_report()` after the
fact.
- *Rejected:* `content_digests` must be computed from the live validated connection, not
  reconstructed post-hoc; re-wrapping a detached dict risks digest/verdict skew and reintroduces the
  synthesis smell the guardrails forbid.

**Approach C — hand-edit / synthesize the published report to bridge the gap.**
- *Rejected outright:* explicitly forbidden ("Do not synthesize or hand-edit a published report").

**Approach D — promote by pointing the live `verify_and_publish` at the prod lane with the
full-window sidecar.**
- *Rejected for the candidate-generation task:* `verify_and_publish` defaults to writing into the DB
  directory; using it against prod would mutate the official report and its log — that is the
  *promotion* step, not candidate generation, and it needs the separate promotion plan's atomic
  backup/replace discipline. Candidate generation must stay read-only and non-prod.

---

## 6. Chosen approach — Approach A (definition for the execution task)

**Smallest code change required** (to be implemented and tested by the execution task, not here):

C1. **Candidate producer.** A read-only, publication-schema candidate generator — either a new
    thin function (e.g. `verify_and_publish_candidate(db_path, *, output_dir, data_dir, now=None)`)
    or explicit new keyword params on `verify_and_publish` — that:
    - opens the DB via the **immutable read-only** URI contract
      (`_open_readonly_immutable_connection`, `file:<abs>?mode=ro&immutable=1` + `query_only=ON`);
    - runs `_verify_connection(conn, db_path, data_dir=<abs source dir>,
      allow_db_relative_data=True, fail_on_source_path_unavailable=True)` (same clean-carry /
      full-window auto-scope path the CLI uses);
    - computes `_content_digests(conn)` from that same connection;
    - assembles the report via `_build_published_report()` (the 42-key envelope);
    - writes it **only** to an explicit `output_dir` that is **not** the DB's parent directory, and
      **never** writes `paper_verify_report.json`, receipt, or log into the prod lane. Recommended:
      write to `/tmp/paper_verify_report.candidate_<timestamp>.json` (a candidate filename, not the
      official `REPORT_FILE`), `write_log=False`.

C2. **Anti-overwrite guard.** The candidate producer must **refuse** (raise / non-zero exit) if the
    resolved output path equals the prod official report path or lives under the prod lane dir.

C3. **Explicit `--data-dir`.** Required, absolute; relative or missing paths fail closed.

C4. **Full-window sidecar/bundle selection.** Verified via the existing auto-scope logic; the
    candidate must record the full-window sidecar as selected (batch57 snapshot,
    `snapshot_status = present_valid`) and reason codes `[]`.

C5. **Schema-equality gate (new, part of the change or the harness).** Compare the candidate's
    top-level key set to the current official report's top-level key set.

**Acceptance gates for the future execution (candidate generation only — promotion is a separate,
already-written plan):**

*Schema gates:*
- **G-S1** Candidate top-level key set **==** current official report top-level key set — **unless**
  a documented schema-version migration is explicitly approved (see note below).
- **G-S2** Candidate preserves all publication/provenance envelope fields: `authoritative`,
  `trusted`, `verified_at`, `verifier`, `verifier_version`, `schema_version`, `content_digests`,
  `content_sha256`, `current_verdict`, `snapshot_identity`, `exit_code`, `failures`.
- **G-S3** Candidate carries **none** of the six read-only-CLI diagnostic keys
  (`db_mutation_performed`, `query_only_pragma_enabled`, `read_only`, `sqlite_open_mode`,
  `verifier_cli_contract_version`, `wal_shm_files_created`).
- **G-S4** Candidate `schema_version` equals the official report's `schema_version` (no silent
  version drift).
- **G-S5** Candidate is generated **by code** (the C1 producer), not hand-edited or synthesized.

*Semantic / data gates (carried from the promotion plan §4):*
- **G1** Candidate latest batch id == DB latest committed batch id (expect `57`).
- **G2** Candidate watermark == DB latest funding watermark (expect `2026-07-09T08:00:00`).
- **G3** Candidate `status = OK`.  **G4** `failure_count = 0`.
- **G5** `funding_clean_carry_decision = CLEAN_NET_OF_CARRY`.  **G6** reason codes `[]`.
- **G7** Full-window sidecar selected (`full_window_snapshot_selected_path` = batch57;
  `snapshot_status = present_valid`).
- **G8** `funding_source_snapshot_window_mismatch` absent.  **G9** `source_path_unavailable` absent
  (`source_path_available = True`, mode `explicit_data_dir`).

*Immutability gates:*
- **G10** Prod DB hash unchanged (`94874dab…bc11`).
- **G11** Source CSV hashes unchanged (all 20).
- **G12** Official report hash unchanged during candidate generation (`2c6af12b…10c3`) — the
  candidate lives only under `/tmp`.
- **G13** Full-window snapshot and immutable bundle hashes unchanged; no `-wal`/`-shm` created.

> **Schema-version migration note (G-S1 exception).** If, and only if, the clean-carry / full-window
> path legitimately introduces additive top-level keys not present in the current official report,
> the execution task must: (a) enumerate the exact added/removed keys, (b) get Viktor's explicit
> approval, (c) bump `schema_version` and document the migration, and (d) re-baseline G-S1 to the
> migrated key set. Absent all four, a key-set difference is a **stop condition**, not a pass.

---

## 7. Tests required before execution

To be added/green before any candidate is generated on the VM:

- **T1 — envelope shape.** Unit test: the C1 candidate producer, run against a fixture DB, returns
  a report whose top-level key set equals the `verify_and_publish` published envelope key set (all
  12 envelope keys present; none of the 6 CLI diagnostic keys present).
- **T2 — clean-carry parity.** With a fixture full-window sidecar + explicit `data_dir`, the
  candidate reaches `funding_clean_carry_decision = CLEAN_NET_OF_CARRY`, reason codes `[]`,
  full-window sidecar selected — matching the read-only CLI's result for the same inputs.
- **T3 — content digests present.** Candidate `content_digests` / `content_sha256` are non-empty and
  equal `_content_digests(conn)` for the pinned snapshot.
- **T4 — anti-overwrite guard (C2).** Producer refuses / errors when `output_dir` resolves to the DB
  parent dir or the official `paper_verify_report.json`; asserts the official file is untouched.
- **T5 — read-only invariants.** No DB mutation, no `-wal`/`-shm` sidecars, `query_only` on; DB
  bytes identical pre/post (mirror `tests/test_paper_sqlite_verify_read_only_cli_contract.py`).
- **T6 — schema-equality gate.** Given a candidate and an official-report fixture, the gate passes on
  equal key sets and fails (loudly) on any added/removed top-level key.
- **T7 — `--data-dir` contract.** Missing/relative `--data-dir` fails closed; absent source dir
  yields `source_path_unavailable` (never a silent CLEAN).

Verification ladder for the code change: import check → scoped
`tests/test_paper_sqlite_verify*.py` → `./scripts/release_smoke.sh` → full suite if broadly
relevant. State which rungs ran.

---

## 8. Exact non-goals

- No report promotion, generation, or overwrite by **this** plan task.
- No live integration, trading, leverage, or shorting.
- No writer / trader / backfill / data-refresh run.
- No service / timer / cron / systemd change. No deploy. No exchange keys.
- No shadow mutation. No new snapshots/bundles. No source CSV mutation. No prod DB mutation.
- No hand-editing or synthesizing a published report.

---

## 9. Stop conditions (for the eventual execution)

- Candidate top-level key set ≠ official key set with no approved schema-version migration (G-S1).
- Any missing publication/provenance envelope field (G-S2) or any injected CLI-diagnostic field
  (G-S3), or `schema_version` drift (G-S4).
- Candidate not clean (any of G3–G9 fails), or full-window sidecar not selected.
- `content_digests` / `content_sha256` empty or unverifiable.
- Any hash drift in prod DB, source CSVs, official report, snapshot, or bundle during candidate
  generation (G10–G13); or any `-wal`/`-shm` sidecar created.
- Anti-overwrite guard would be bypassed, or output resolves into the prod lane dir.
- Any temptation to hand-edit/synthesize to close the schema gap → **halt and escalate**.

On any stop condition: halt, make no prod writes, capture state, and record a receipt.

---

## 10. Next task after this plan

```
QNTY_PROD_FULL_WINDOW_REPORT_PROMOTION_SCHEMA_RECONCILIATION_EXECUTION
```

Implements the Approach A candidate producer (§6 C1–C5) + tests (§7), generates the
publication-schema candidate read-only into `/tmp`, and enforces the §6 gates. On green, it hands
back to `QNTY_PROD_FULL_WINDOW_REPORT_PROMOTION_EXECUTION` (the already-recorded promotion plan,
`QNTY_PROD_FULL_WINDOW_REPORT_PROMOTION_PLAN.md` §5) to back up and atomically replace the official
report with the now schema-compatible candidate.

---

## Verdict

```
QNTY_PROD_FULL_WINDOW_REPORT_PROMOTION_SCHEMA_RECONCILIATION_PLAN_RECORDED
```

Plan recorded. No report promoted, generated, or overwritten. No prod DB / source CSV / snapshot /
bundle / shadow mutation. No VM mutation by this task. No published report synthesized or
hand-edited. `EDGE_UNPROVEN` and `BLOCK_LIVE_INTEGRATION` remain in force.
