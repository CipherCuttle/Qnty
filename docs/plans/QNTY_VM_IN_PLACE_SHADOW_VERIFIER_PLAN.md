# QNTY VM In-Place Shadow Verifier Plan

## Status Boundary

- `EDGE_UNPROVEN` remains.
- `BLOCK_LIVE_INTEGRATION` remains.
- full-ledger `CAVEATED_ENGINE_SEMANTICS` remains.
- This is a plan only.
- This plan does not prove edge, profitability, statistical significance,
  shorting readiness, live readiness, or production deployment.
- This plan authorizes no DB mutation, writer run, trader run, live
  integration, deployment, backfill, or official report overwrite.

## Why This Plan Exists

- PR #89 refreshed shadow verifier evidence safely using a `/tmp` DB copy
  (`docs/status/shadow_verifier_fresh_receipt_2026-07-07.md`).
- The fresh verifier output contained the clean-carry fields
  (`funding_clean_carry_decision` and the related clean-carry keys).
- But that copy-location verification produced an absolute-path artifact:
  the shadow ledger stores the committed funding-source snapshot as an
  **absolute VM path**, so a verifier run from a copied DB location cannot
  resolve that path and yields `source_path_unavailable` / `CORRUPT`-style
  path artifacts rather than a clean funding-source snapshot resolution.
- A fully resolved **official** shadow verifier report therefore requires a
  future scoped **in-place** verifier run at the true VM shadow lane path,
  using **current** verifier code, so the stored absolute funding-source
  path resolves against the real VM filesystem.
- That future run touches the true VM lane path and must be designed
  carefully — with read-only guarantees and before/after integrity proof —
  **before** it is executed. This document is that design. It does not run.

## Current Known Inputs

- VM SSH command:
  `ssh -i ~/.ssh/hetzner_qnty_key -o IdentitiesOnly=yes viktor@37.27.216.174`
- VM repo path:
  `/srv/qnty/repo`
- Shadow DB path:
  `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db`
- Prod DB path:
  `/srv/qnty/output/paper_pnl_v1/paper_ledger.db`
  (read-only reference only; not required for the shadow run).
- Known stale VM repo head from a previous receipt:
  `2bd88430` (must be re-checked live in Stage A; treat as stale until proven).
- Latest local/`main` PR #89 merge SHA:
  `164e3bc83c1122c77ca031fbf591d3694a039f7a`
- Existing shadow report staleness observed in PR #89:
  - old verified-through: `2026-07-01T08:00:00`
  - current shadow watermark: `2026-07-05T16:00:00`
- Fresh `/tmp` run result (PR #89):
  - clean-carry keys present;
  - full-ledger + batch decisions `CAVEATED_ENGINE_SEMANTICS`;
  - funding source path artifact due to copied DB location (the stored
    absolute VM funding-source snapshot path was unavailable at the `/tmp`
    copy location).

### Verifier CLI as it exists on local `main` (read-only inspection)

Confirmed from `quantbot/paper/sqlite_verify.py` on
`164e3bc83c1122c77ca031fbf591d3694a039f7a`:

- Invocation: `python -m quantbot.paper.sqlite_verify`
- `--db-path` — required, must be **absolute**.
- `--read-only` — opens the DB via the immutable read-only URI contract
  `file:<abs>?mode=ro&immutable=1` plus `PRAGMA query_only=ON`.
- `--json` — **required**; emits a single JSON report to **stdout**.
- `--data-dir` — absolute path to the directory containing source funding
  CSVs; relative paths rejected; missing absolute paths fail closed through
  the JSON report. (Directly relevant to resolving the funding-source path.)
- `--strict-clean-carry` — diagnostic only; changes only the process exit
  code, never any report field.
- `--no-wal-checkpoint` — documented no-op safety flag; the CLI never runs a
  WAL checkpoint with or without it.
- The CLI reports `db_mutation_performed: false`, `wal_shm_files_created:
  false`, and `sqlite_open_mode: file_uri_mode_ro_immutable` under
  `--read-only`. It prints JSON to stdout and writes **no sidecar files**.

The future operator must re-confirm this via `--help` on the chosen code
source before running, because the run happens on the VM and the code source
selection (Stage B) determines which CLI semantics actually execute.

## Risks

- `VM_REPO_STALE` — `/srv/qnty/repo` may be pinned at an old head
  (previously `2bd88430`) lacking current clean-carry verifier semantics.
  Running the verifier from a stale VM repo would reproduce old semantics,
  not the current ones this evidence needs.
- `REPORT_OVERWRITE_RISK` — the authoritative publish path in the verifier
  module writes an official report/receipt/log. Any run that invokes the
  publisher instead of the read-only CLI could overwrite an existing
  official report. The first run must use only the read-only stdout CLI.
- `DB_MUTATION_RISK` — any non-read-only open, migration, schema-ensure, or
  writer invocation could mutate the shadow DB. Must be prevented and proven
  via before/after hash.
- `ABSOLUTE_PATH_DEPENDENCY` — the shadow ledger stores the funding-source
  snapshot as an absolute VM path. This is exactly why an in-place run is
  needed and also why the run is path-sensitive: it must execute where that
  absolute path resolves (the real VM), and `--data-dir` must point at the
  true VM funding CSV directory if required.
- `VERIFIER_OUTPUT_AMBIGUITY` — decisions may remain
  `CAVEATED_ENGINE_SEMANTICS`; the run must record exact status/decision/
  reason codes rather than being interpreted as a pass/fail edge claim.
- `EVIDENCE_PROMOTION_RISK` — a clean `/tmp` result may tempt immediate
  promotion to the official report. Promotion is explicitly out of scope for
  the verifier run and is a separate, later, reviewed task.

## Non-Negotiable Safety Rules

- no writer runs;
- no trader runs;
- no live/exchange code;
- no migrations;
- no schema ensure on a real DB;
- no DB writes;
- no deploy;
- no backfill;
- no official report overwrite in the first execution;
- verifier output first goes to `/tmp`;
- before/after size, mtime, sha256 required for the shadow DB;
- prod DB not touched unless explicitly included as read-only;
- VM repo update only in a separately scoped task, never implicit.

## Proposed Future Execution Sequence

Staged design only. No stage below is executed by this document.

### Stage A — VM Read-Only Preflight

Collect (all read-only):

- VM repo head: `git -C /srv/qnty/repo rev-parse HEAD`
- VM git status: `git -C /srv/qnty/repo status --short --branch`
- current shadow DB stat: `stat /srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db`
- current shadow DB hash: `sha256sum /srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db`
- current shadow DB latest watermark (read-only SQLite query of the batch
  watermark, opened `mode=ro`);
- existing shadow report stat + hash (locate the official report path first,
  read-only);
- current verifier version/help from the VM repo if available
  (`python -m quantbot.paper.sqlite_verify --help`);
- local current verifier code head (already known:
  `164e3bc83c1122c77ca031fbf591d3694a039f7a`).

Acceptance gates:

- shadow DB readable;
- existing report path known;
- DB hash captured;
- VM repo not dirty if the run will use the VM repo;
- current code source chosen explicitly (Stage B).

### Stage B — Choose Code Source

- **Option 1 — run verifier from the VM repo `/srv/qnty/repo`.**
  - Pro: the true absolute paths already exist on this host.
  - Con: the VM repo may be stale (e.g. `2bd88430`) and lack current
    clean-carry verifier semantics.
- **Option 2 — copy current code to `/tmp/qnty-verifier-run-<sha>` on the
  VM and run from there against the true shadow DB path.**
  - Pro: current verifier semantics; still executes on the VM so absolute
    funding-source paths resolve.
  - Con: must not update `/srv/qnty/repo`; the code copy must stay
    temporary and isolated under `/tmp`.
- **Option 3 — run the local verifier against an SSH-mounted or copied path.**
  - Pro: current code, locally.
  - Con: cannot resolve the VM absolute funding-source path if the DB is
    copied off-host; insufficient for official in-place proof (this is the
    exact limitation PR #89 already hit).

Preferred future approach: **Option 2** — copy the current verifier code to
`/tmp/qnty-verifier-run-<sha>` on the VM, run it on the VM against the true
shadow DB path in read-only/immutable mode, and write the JSON report to
`/tmp`. This combines current semantics with true-path funding-source
resolution while never mutating `/srv/qnty/repo`.

This is a **future task**, not this PR.

### Stage C — Dry-Run Verifier To `/tmp`

Future command shape (adapt only after confirming `--help` on the chosen
code source):

```
python -m quantbot.paper.sqlite_verify \
  --db-path /srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db \
  --read-only \
  --json \
  > /tmp/shadow_verify_fresh_<timestamp>.json 2> /tmp/shadow_verify_fresh_<timestamp>.err
```

If funding CSV resolution is required, additionally pass `--data-dir
<absolute VM funding CSV dir>` (absolute path only). If the CLI on the chosen
code source differs, the future operator must adapt strictly from `--help`.

Required:

- DB opened read-only/immutable (`--read-only` → `mode=ro&immutable=1` +
  `PRAGMA query_only=ON`);
- output only to `/tmp`;
- no sidecar writes (the read-only CLI writes only stdout — confirm no
  publish path is invoked);
- no official report path touched;
- capture exit code;
- capture stdout and stderr;
- capture output sha256 (`sha256sum /tmp/shadow_verify_fresh_<timestamp>.json`).

### Stage D — Post-Run Integrity

Required before/after checks:

- shadow DB size/mtime/sha256 match the Stage A capture;
- existing official report size/mtime/sha256 unchanged;
- `/srv/qnty/output` gains **no** new files;
- `/srv/qnty/repo` unchanged (Option 2 keeps all code under `/tmp`);
- no writer/trader processes ran during the window.

### Stage E — Receipt PR

A future, separate PR should:

- add a `docs/status` receipt only;
- include the command, output path, output hash, and verifier result fields;
- include clean-carry decisions and reason codes;
- include the DB integrity proof (before/after size/mtime/sha256);
- include the official-report-untouched proof;
- preserve `EDGE_UNPROVEN`, `BLOCK_LIVE_INTEGRATION`, and full-ledger
  `CAVEATED_ENGINE_SEMANTICS`.

### Stage F — Optional Official Report Promotion

A later, explicit task only — and only if the `/tmp` run is clean and
reviewed.

Rules:

- separate prompt;
- back up the old official report first;
- atomic write if approved;
- before/after report hash;
- no DB mutation;
- PR receipt documenting the official report promotion;
- do not combine with the verifier-run plan.

## Acceptance Gates For Future Execution

- current code source selected (Stage B);
- no VM repo dirty state;
- shadow DB hash captured before the run;
- verifier `--help` confirms read-only / json / stdout behavior on the chosen
  code source;
- dry-run output goes only to `/tmp`;
- no official report overwritten;
- shadow DB hash unchanged after the run;
- official report hash unchanged after the run;
- clean-carry keys present in the output;
- decision/status/reason codes recorded verbatim;
- no edge/live claims made.

## Stop Conditions

Stop and record a blocker if any of the following occur:

- the verifier CLI on the chosen code source cannot guarantee read-only mode;
- the verifier writes sidecars by default and cannot disable them;
- the VM repo is dirty or stale and the code-source decision is unresolved;
- the shadow DB hash changes;
- the official report hash changes unexpectedly;
- the verifier command requires migrations / schema writes;
- the funding-source path is still unavailable even when run on the true VM
  path (would indicate a deeper snapshot-path issue needing diagnosis);
- the output lacks clean-carry keys;
- the verifier result contradicts existing receipts in a way requiring
  diagnosis;
- any request to backfill / deploy / live trade appears.

## What This Plan Proves

- It defines a safe path for future in-place shadow verifier evidence.
- It identifies why copy-based verifier receipts (PR #89) are insufficient
  for official clean-path resolution: the stored absolute VM funding-source
  path only resolves in place.
- It narrows the remaining evidence-quality work to a single scoped,
  read-only, integrity-proven VM run.

## What This Plan Does Not Prove

- no edge;
- no profitability;
- no live readiness;
- no short readiness;
- no clean prod/shadow full-ledger guarantee;
- no official report promotion;
- no DB backfill;
- no production deployment.

## Proposed Next Prompt After This Plan Merges

`VM_SHADOW_VERIFIER_TMP_RUN_GIT_OWNED`

The next task should execute only Stages A–D (VM read-only preflight, code
source selection, `/tmp` dry-run verifier, post-run integrity) and create a
`docs/status` receipt. It must still perform **no** official report
overwrite, no DB mutation, no VM repo update, and no writer/trader/live run.

## Verdict

`VM_IN_PLACE_SHADOW_VERIFIER_PLAN_RECORDED`
