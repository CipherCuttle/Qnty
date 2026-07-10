# QNTY Offline Edge Validation — Real-Data Preflight Runbook

Status: docs-only runbook. No code in this PR. Not executed as part of this PR.

For a recorded example capture result, see
[QNTY_OFFLINE_EDGE_VALIDATION_REAL_DATA_PREFLIGHT_READY_RECEIPT.md](QNTY_OFFLINE_EDGE_VALIDATION_REAL_DATA_PREFLIGHT_READY_RECEIPT.md).

## 1. Purpose

This is a **manual, read-only runbook** for a human (or an explicitly instructed
agent) to later check whether a set of real offline data directories (bars,
funding, manifest CSVs) are *structurally* ready to be fed into a future
offline edge-validation run — nothing more.

Explicitly, this runbook and the procedure it describes:

- **is not edge validation** — it does not decide whether any strategy has an
  edge.
- **is not a profit claim** — no PnL, Sharpe, return, or edge number is
  produced or implied.
- **does not run the paper engine** — no `quantbot.paper` import, no ledger,
  no trade simulation.
- **does not run walk-forward** — no real historical walk-forward replay;
  only the existing fixture-only walk-forward stage exists in the CLI and is
  out of scope here.
- **does not promote reports** — nothing under `output/` or any
  `/srv/qnty/...` path is written, read for promotion, or copied.
- **does not touch live systems** — no exchange keys, no exchange connector,
  no timers/services/cron, no deploy.

The only thing this runbook produces is a `validation_receipt.json` with
`final_verdict: SKELETON_ONLY`, plus a `data_quality_preflight_summary` that a
human reads to decide readiness using the vocabulary in §6.

## 2. Preconditions

Before running anything, confirm all of the following:

- `git status` is clean on the branch you intend to run from.
- You have a **fresh scratch checkout** of `origin/main` (not your working
  tree with uncommitted changes), e.g.:

  ```
  SCRATCH="/tmp/qnty_scratch_$(date +%s)"
  git clone --depth 1 --branch main <this-repo-remote-url> "$SCRATCH"
  ```

- No dirty repo-local module resolution: run from the scratch checkout only,
  and verify `quantbot.__file__` resolves under `$SCRATCH`, not under your
  normal working directory:

  ```
  PYTHONPATH="$SCRATCH" python -c "import quantbot; print(quantbot.__file__)"
  ```

  The printed path must start with `$SCRATCH`.

- `--output-dir` will be under `/tmp` (the CLI enforces this and exits 3
  otherwise — see §8).
- Input directories (`--bars-dir`, `--funding-dir`, `--manifest-dir`) are
  **explicit, human-chosen paths** and must **not** resolve under
  `/srv/qnty` (the CLI's prod-path guard refuses this and exits 3 — see §8).
- No exchange API keys are set in the environment.
- No live services/timers (systemd units, cron jobs) are started, stopped,
  or edited as part of this procedure.
- No files are staged under `tmp/` in the repo (only the fresh `/tmp` scratch
  output directory is used).

## 3. Safe command template

Run only the existing, already-merged `offline_edge_validation_cli`
(`quantbot/experiment/offline_edge_validation_cli.py`) in read-only,
data-quality-preflight mode:

```bash
TS="$(date +%s)"
PYTHONPATH="$SCRATCH" python -m quantbot.experiment.offline_edge_validation_cli \
  --read-only \
  --output-dir "/tmp/qnty_offline_edge_real_data_preflight_${TS}" \
  --bars-dir "<EXPLICIT_OFFLINE_BARS_DIR>" \
  --funding-dir "<EXPLICIT_OFFLINE_FUNDING_DIR>" \
  --manifest-dir "<EXPLICIT_OFFLINE_MANIFEST_DIR>" \
  --data-quality-preflight
```

Notes:

- The `<EXPLICIT_...>` placeholders **must remain placeholders** in this
  document. Do not fill them in here or commit any real path.
- Do not substitute `/srv/qnty` or any path under it for any of the three
  input directories — the CLI will refuse it (exit code 3).
- Do not add `--full-fixture-receipt` in combination with real (non-fixture)
  directories as a way to get a "final" verdict — the resulting receipt is
  still `SKELETON_ONLY` and must not be read as anything else. Using
  `--data-quality-preflight` alone against real directories is sufficient for
  this runbook's purpose.
- Do not add any command that copies the resulting receipt into `output/`,
  `/srv/qnty`, or any path matching `paper_verify_report.json` /
  `official_report` — those are refused by the CLI's own guard and must not
  be worked around.
- At least one of `--bars-dir`, `--funding-dir`, `--manifest-dir` is required
  when `--data-quality-preflight` is set; omitting all three is a usage error
  (exit 1), not a silent no-op.

## 4. Receipt expectations

After the command in §3 completes, inspect
`/tmp/qnty_offline_edge_real_data_preflight_${TS}/validation_receipt.json`
and confirm:

- `final_verdict` == `"SKELETON_ONLY"`.
- `data_quality_preflight_summary` key exists and is a non-null object.
- If any of `--bars-dir` / `--funding-dir` / `--manifest-dir` were provided,
  `input_manifest_fingerprint` is **not** the placeholder value
  (`PLACEHOLDER_SKELETON_NO_OP`) — it is a real fingerprint string.
- `per_stage_metrics` contains an entry for the data-quality stage (stage id
  `DATA_QUALITY_STAGE_ID` / stage name `DATA_QUALITY_STAGE_NAME`, as defined
  in `quantbot/experiment/offline_edge_schema.py`), often referred to
  informally as "stage C".
- There is **no** top-level `pnl`, `sharpe`, `edge`, or
  `strategy_performance` key anywhere in the receipt.
- There is **no** occurrence of the string `EDGE_CANDIDATE` anywhere in the
  receipt.
- If you used `--full-fixture-receipt` on top of the fixture-only inputs
  (separately from the real-data preflight — see §3), its own guardrail
  fields (e.g. `final_verdict_rationale` stating "No edge claim made. No
  live integration. No strategy PnL.") remain present and unchanged.

## 5. Data-quality gates

Read `data_quality_preflight_summary` and treat the following as the
conservative readiness gates. Field names below match
`quantbot/experiment/offline_edge_data_quality.py`:

- `total_row_count > 0`
- `csv_file_count > 0`
- `readiness_flags.has_timestamp_column` is `true`
- `readiness_flags.no_duplicate_timestamps` is `true` (i.e.
  `has_duplicate_timestamps` is `false` at the directory level)
- `readiness_flags.timestamps_monotonic` is `true` (i.e.
  `has_non_monotonic_timestamps` is `false`)
- `readiness_flags.no_null_required_values` is `true` (i.e.
  `has_null_values` is `false`)
- `missing_required_columns` is empty (`[]`) across all inspected files
- `global_min_timestamp` and `global_max_timestamp` are both present
  (non-null)
- The span between `global_min_timestamp` and `global_max_timestamp` is wide
  enough to justify a later, separately-scoped validation run (no fixed
  threshold is prescribed here — use judgment and record the span in your
  notes)
- Funding coverage is either present and inspected (`--funding-dir` was
  supplied and its files pass the same gates above) or explicitly recorded
  as missing/not-yet-available — do not silently treat an omitted
  `--funding-dir` as "funding is fine"

All gates must be considered together; a single failing gate is enough to
block readiness per §6.

## 6. Verdict vocabulary

When a human reviews the receipt against §5, record **only** one of these
three verdicts:

- `DATA_READY_FOR_OFFLINE_VALIDATION` — all gates in §5 pass.
- `DATA_NOT_READY_FOR_OFFLINE_VALIDATION` — one or more gates fail, but the
  data is inspectable and the gap is understood (e.g. missing funding
  coverage, insufficient timestamp span).
- `BLOCKED_BY_DATA_QUALITY` — a hard structural problem prevents any
  reasonable path forward without re-sourcing or repairing the input data
  (e.g. zero rows, no timestamp column at all, pervasive null required
  values).

This verdict is **advisory documentation for the human**, separate from and
in addition to the CLI's own `final_verdict: SKELETON_ONLY` in the receipt.
It never overrides or upgrades the receipt's own verdict.

**Explicitly forbidden** in any note, commit message, or artifact produced
from this runbook: `EDGE_CANDIDATE`, `PROFITABLE`, `LIVE_READY`,
`CLEAN_EDGE`, `DEPLOY_READY`. None of these are legitimate outputs of a
data-quality preflight. `EDGE_UNPROVEN` and `BLOCK_LIVE_INTEGRATION` remain
the standing project-wide guardrails regardless of this runbook's outcome.
Long-only / 1x remains the only assumed lane unless separately proven
elsewhere. `CLEAN_NET_OF_CARRY`, if it appears elsewhere in this project,
means only "not killed by verifier gate" — never edge, profit, or live
readiness — and is unrelated to the data-quality verdicts above.

## 7. Postflight checks

After recording a verdict, confirm:

- The output receipt's file hash is recorded in your notes (e.g.
  `sha256sum "/tmp/qnty_offline_edge_real_data_preflight_${TS}/validation_receipt.json"`).
- The `input_manifest_fingerprint` value from §4 is recorded alongside the
  verdict.
- No DB file hash anywhere under the real repo/output tree changed
  (`git status` / out-of-band DB check, as applicable — this procedure never
  opens a DB).
- No CSV file hash in the real input directories changed (this procedure is
  read-only against those directories; verify with `sha256sum` before/after
  if you want a hard check).
- No path under `output/` or `/srv/qnty` was created, modified, or read for
  promotion.
- No systemd unit, timer, or cron entry was touched.
- No files were created outside `/tmp` (check `git status` in the real repo
  working tree — it must be unchanged, and no stray files should appear
  under the repo).
- `git status` in the real repo is clean except for the intended docs change
  from this PR.

## 8. Failure modes

Expected, already-implemented failure modes you may hit while following §3:

- **Prod path refusal (exit 3)** — `--output-dir` resolves under `/srv/qnty`,
  or any of `--bars-dir` / `--funding-dir` / `--manifest-dir` resolves under
  `/srv/qnty`, or `--output-dir` does not resolve under `/tmp`. Message:
  `Refusing prod path: ...` or `FATAL: Output directory must be under
  ('/tmp',), got: ...`.
- **Missing input directory** — the CLI's `--data-quality-preflight` flag
  requires at least one of `--bars-dir` / `--funding-dir` / `--manifest-dir`;
  omitting all three exits 1 with `ERROR: --data-quality-preflight requires
  at least one of --bars-dir, --funding-dir, or --manifest-dir`. If one of
  those flags points at a directory path that does not exist on disk,
  `offline_edge_data_quality.inspect_input_directory` raises
  `FileNotFoundError` and the CLI exits nonzero **before** any
  `validation_receipt.json` is written — the error is not converted into a
  receipt-level field, and there is no partial or partial-error receipt to
  inspect for this case. If you hit this, fix the path (or create/provide
  the intended offline directory) and rerun the command in §3 from scratch.
- **Missing timestamp column** — surfaces as
  `readiness_flags.has_timestamp_column: false` and/or a non-empty
  `missing_required_columns` list; treat per §5/§6, do not treat as a script
  bug.
- **Duplicate timestamps** — surfaces as
  `readiness_flags.no_duplicate_timestamps: false`
  (`has_duplicate_timestamps: true` at the directory level).
- **Non-monotonic timestamps** — surfaces as
  `readiness_flags.timestamps_monotonic: false`
  (`has_non_monotonic_timestamps: true`).
- **Null required values** — surfaces as
  `readiness_flags.no_null_required_values: false`
  (`has_null_values: true`).
- **Empty row count** — `total_row_count == 0`; treat as
  `BLOCKED_BY_DATA_QUALITY` per §6 unless the directory was intentionally
  empty for a documented reason.
- **Accidental stale module resolution** — if `quantbot.__file__` (per §2)
  resolves to your normal working tree instead of `$SCRATCH`, stop and fix
  `PYTHONPATH` / working directory before proceeding; results from a stale
  checkout are not valid for this runbook.

## 9. Acceptance

This PR is accepted if:

- It is docs-only (no `quantbot/`, `tests/`, `scripts/`, or `ops/` changes).
- No code changes are included.
- The runbook above is explicit enough that a later human or explicitly
  instructed agent could execute the real-data preflight safely without
  further clarification.
- No real prod paths appear anywhere in this document (only the literal
  `/srv/qnty` prefix as a *negative* example, and placeholder tokens like
  `<EXPLICIT_OFFLINE_BARS_DIR>`).
- No report-promotion commands appear anywhere in this document.
- No forbidden edge-claim vocabulary (§6) appears anywhere in this document
  except as an explicit "forbidden" listing.
