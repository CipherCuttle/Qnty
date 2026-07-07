# Qnty — Claude Code project memory

Qnty is a cleanroom crypto quant **research harness** (Python >=3.10, package
`quantbot`). It is shadow-only research: **not a trading bot, not live-capital
approved.** Claims must stay proportionate to evidence.

## Stack & layout
- Python >=3.10; deps: numpy, pandas, requests; tests: pytest. No TS/frontend, no CI,
  no linter/formatter configured.
- `quantbot/` — package (core, data, paper, exec, strategy, replay, experiment, ...).
- `scripts/`, `ops/bin/`, `ops/systemd/` — operator tooling (paper PnL, verify, health).
- `tests/` — pytest suite (72 files). `docs/` — receipts, ADRs, status, boundaries.
- Generated & git-ignored (never commit): `data/`, `output/`, `experiment_results/`.

## Commands
- Install: `python -m venv .venv && source .venv/bin/activate && pip install -e ".[test]"`
- Run tests (venv): `.venv/bin/python -m pytest tests/<file> -q`
- Full suite: `.venv/bin/python -m pytest -q`
- Smoke: `./scripts/release_smoke.sh`

## Verification ladder (cheap -> expensive; run before any final verdict)
1. Import check: `python -c "import quantbot, numpy, pandas, requests; print('IMPORT_OK')"`
2. Scoped tests for the files you touched: `.venv/bin/python -m pytest tests/test_<area>.py -q`
3. Smoke: `./scripts/release_smoke.sh`
4. Full suite only when broadly relevant: `.venv/bin/python -m pytest -q`
5. `git diff --check` and confirm `git diff --cached --name-only` matches intent.

State exactly which rungs you ran; if you skipped one, say why.

## Guardrails (repo-specific — do not violate)
- **No live trading / no capital deployment / no exchange connectors** in normal work.
- **Never mutate a real prod/shadow SQLite ledger** (`output/**/paper_ledger.db`). For any
  verifier/ledger experiment: copy the DB to `/tmp` and operate there; open real DBs
  read-only (`mode=ro&immutable=1`). Never overwrite official reports under `output/`.
- **Do not commit generated artifacts** (`data/`, `output/`, `experiment_results/`) or
  secrets (`.env*`, `*.pem`, `*.key`).
- **Keep Qnty / Franken / THT0 separate** — Franken/THT0 references are legacy
  integration-boundary artifacts, not part of Qnty (see docs/PROJECT_BOUNDARIES.md).
- **Evidence-first:** no alpha/profitability/edge/deployment claims without artifacts and
  explicit caveats. `GO`/`PASSED`/`SURVIVED` mean "not killed by this test", not approval.
- Prefer minimal diffs. Update/add tests with code changes.

## Plugin usage
- Relevant: code-review (review diffs), github (PR/issue read; don't mutate GH state
  unasked), security-guidance, hookify, claude-md-management.
- Not applicable here: frontend-design, playwright, typescript-lsp (no UI/TS).
- context7 only if a numpy/pandas/requests API is genuinely uncertain.

## Memory / MemPalace

Use MemPalace only as a recall aid, not source of truth. Source of truth is git,
`CLAUDE.md`, `docs/status/`, `docs/plans/`, and verifier output.

At session start or before non-trivial QNTY work, if MemPalace MCP/tools are available
(project-scoped server `mempalace-qnty` in `.mcp.json`), query the `qnty` wing for:
- current next QNTY task
- `EDGE_UNPROVEN` / `BLOCK_LIVE_INTEGRATION` guardrails
- latest funding-source recommit / copied-DB status
- relevant prior receipt or plan

Do not mine new paths unless Viktor explicitly asks.
Do not mine generated/sensitive paths: `data/`, `output/`, `experiment_results/`,
`.env*`, `*.pem`, `*.key`, `*.db`, `.venv/`, `.git/`, raw logs, or repo root.
Do not enable hooks or autosave by default.
If MemPalace conflicts with git/docs/verifier output, trust git/docs/verifier.

## Context / limits hygiene

Preserve work quality and safety, but avoid dragging unnecessary context.

- At the start of a session, read this file and use MemPalace `qnty` recall for the
  current task instead of relying on huge prior chat context.
- Use `/compact` after completing a coherent phase, before switching from investigation
  to implementation, or when context is getting large. Before compacting, write a short
  checkpoint: current branch, open PR, changed files, key findings, commands run,
  blockers, and next action.
- Use `/clear` when switching to an unrelated task after the checkpoint/PR state is saved.
- Prefer targeted file reads, `rg`, and specific tests over broad repo scans.
- Do not spawn subagents by default. Use subagents only when parallel investigation
  clearly saves time or when the user asks. State why a subagent is needed.
- Avoid `/run` unless the task genuinely needs a skill/workflow. Prefer normal targeted
  commands for QNTY docs, tests, verifier receipts, and PR review.
- Keep final reports compact but complete: PLAN -> CHANGESET -> VERIFY -> VERDICT, with
  exact changed files and commands.
- Never reduce safety checks to save tokens. Guardrails, DB immutability checks, hash
  checks, and verifier receipts are mandatory when relevant.

## Final response format for non-trivial work
PLAN -> CHANGESET -> VERIFY -> VERDICT.
