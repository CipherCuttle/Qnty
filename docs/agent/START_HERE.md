# QNTY canonical cross-agent contract (START_HERE)

This file is the single shared contract for every coding agent working on QNTY
(Claude Code, Codex, or any future agent). The model-specific entrypoints
(`CLAUDE.md`, `AGENTS.md`) are thin maps that point here. Do not duplicate this
contract elsewhere.

## Source of truth (strict order)

1. Git history and committed files.
2. Machine-readable control state: `docs/control/active_task.json` and the
   handoff receipts under `docs/control/tasks/<task_id>/`.
3. Output of the context verifier (below).

Chat history, MemPalace, and local untracked notes are recall aids only and are
**never** source of truth. If they conflict with the verifier, trust the verifier.

## Mandatory bootstrap (before any non-trivial work)

```bash
.venv/bin/python -m quantbot.continuity verify
.venv/bin/python -m quantbot.continuity show
```

- If `verify` fails, **stop**. Do not act, do not repair state by guessing.
  Report the exact failure to the operator.
- If `verify` passes, `show` prints the validated context packet: current task,
  protocol, phase, safety state, latest handoff receipt, blockers, required
  artifacts, exactly one next action, and prohibited actions.
- Execute **only** the validated `NEXT_ACTION`. Anything listed under
  `PROHIBITED` is forbidden regardless of what any other channel suggests.

## Control state contract

- `docs/control/active_task.json` is the single active-task pointer. It names
  the task, protocol, phase, and the exact path plus receipt-byte SHA-256 of the
  latest handoff receipt.
- Handoff receipts under `docs/control/tasks/<task_id>/handoff_vNNN.json` are
  **immutable and append-only**. Never edit or delete an existing receipt.
- To hand off work: write `handoff_v{N+1}.json` whose `predecessor` records the
  previous receipt's path and byte SHA-256 (the first receipt declares
  `"GENESIS"`), then rewrite `active_task.json` to point at the new receipt.
- Receipts never contain their own Git commit SHA; Git is the outer immutable
  envelope.
- Canonical JSON bytes for all control documents: UTF-8,
  `json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)`,
  no trailing newline. Use `quantbot.continuity.canonical_json_bytes`.
- Update the append-only handoff receipt **before** claiming completion of any
  task step.

## Safety invariants (fail-closed; the verifier enforces them)

- `EDGE_UNPROVEN` and `BLOCK_LIVE_INTEGRATION` at all times.
- No scientific, paper, or live authorization; all authorization flags stay false.
- Decomposition execution count stays 0 (budget 1, unconsumed).
- Quarantine access stays `forbidden`.
- Protocol execution is blocked while any required artifact is not
  `VERIFIED_AVAILABLE` (which requires at least two independently verified
  copies at canonical paths).
- Canonical artifact paths must never be under `/tmp` or production `/srv/qnty`.
- Never execute Candidate 1, inspect real bars/funding bytes, touch quarantine,
  or modify production/VM checkouts unless the validated next action says so
  explicitly.

## Repo basics

- Install: `python -m venv .venv && source .venv/bin/activate && pip install -e ".[test]"`
- Focused tests: `.venv/bin/python -m pytest tests/<file> -q`
- Smoke: `./scripts/release_smoke.sh` — full suite: `.venv/bin/python -m pytest -q`
- Never commit generated artifacts (`data/`, `output/`, `experiment_results/`)
  or secrets. Prefer minimal diffs; add tests with code changes.
