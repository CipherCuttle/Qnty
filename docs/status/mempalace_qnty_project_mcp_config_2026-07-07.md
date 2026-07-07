# QNTY MemPalace Project MCP Config — 2026-07-07

Task: `MEMPALACE_QNTY_PROJECT_MCP_CONFIG_GIT_OWNED`

## Status Boundary
- `EDGE_UNPROVEN` remains.
- `BLOCK_LIVE_INTEGRATION` remains.
- Docs/config only. No application/source/test/dependency changes.
- No prod/shadow DB was mutated. No writer/trader/live code ran.
- No official report was overwritten. No backfill.

## What was added
- Project-scoped MCP config at repo root: `.mcp.json`.
  - Server name: `mempalace-qnty`
  - Transport: `stdio`
  - Command: `mempalace-mcp` (resolved via PATH; installed as an isolated uv tool)
  - Args: none — server uses the local default palace (`~/.mempalace/palace`, local
    Chroma backend). No `--palace` / `--backend` override, no external backend.
- `CLAUDE.md`: added a concise `Memory / MemPalace` section (recall-only guidance,
  no-mining and no-hooks/autosave rules, source-of-truth precedence).

## Wing scoping note
The MemPalace MCP server (`mempalace-mcp`) has no server-level `--wing` flag; wing is a
per-query parameter (`mempalace search --wing qnty`). Scoping to the `qnty` wing is
therefore done at query time by the caller, as instructed in `CLAUDE.md`, not baked into
the server config.

## How it was validated
- `claude mcp add --scope project mempalace-qnty -- mempalace-mcp` wrote `.mcp.json`.
- `claude mcp list` → `mempalace-qnty: mempalace-mcp - ✓ Connected`.
- `claude mcp get mempalace-qnty` → `Scope: Project config (shared via .mcp.json)`,
  `Status: ✓ Connected`.
- Smoke searches against the `qnty` wing returned expected receipts (funding-source
  recommit blocker diagnosis, EDGE_UNPROVEN / BLOCK_LIVE_INTEGRATION, acceptance
  receipt). Read-only searches only.

## What was NOT done (guardrails held)
- No hooks installed.
- No autosave enabled.
- No new mining — only read-only smoke searches were run.
- No generated/sensitive paths mined (`data/`, `output/`, `experiment_results/`,
  `.env*`, `*.pem`, `*.key`, `*.db`, `.venv/`, `.git/`, raw logs, repo root).
- No external MemPalace backend enabled (local Chroma only).
- No global Claude config changed — config is project-scoped and repo-shared.
- No QNTY application behavior changed.

## Security posture (accepted tradeoffs)
- Repo-scoped `.mcp.json` registers a local dev tool. Claude Code does **not**
  auto-run project-scoped servers: each user is prompted to approve `.mcp.json`
  servers per-project before they execute (reset via
  `claude mcp reset-project-choices`). So committing this does not silently execute
  code on clone — it is opt-in per contributor.
- `command: mempalace-mcp` resolves via PATH (intended: an isolated uv-tool install,
  not pinned to a user-specific absolute path that would break other checkouts). The
  server talks only to the local Chroma palace; no network / external backend.
- This is a solo research repo; the registration is a personal recall aid, not a
  supply-chain dependency of `quantbot`. To revoke: `claude mcp remove mempalace-qnty
  -s project` and delete `.mcp.json`.

## Source-of-truth rule
MemPalace is recall-only. Source of truth is git, `CLAUDE.md`, `docs/status/`,
`docs/plans/`, and verifier output. On conflict, trust git/docs/verifier.

## Context / limits hygiene

`CLAUDE.md` also records a conservative context-hygiene policy:
use MemPalace recall instead of carrying giant sessions, compact after coherent phases,
clear between unrelated tasks, avoid default subagents, and avoid `/run` unless needed.
This is cost hygiene only; safety checks and verifier gates must not be skipped.
