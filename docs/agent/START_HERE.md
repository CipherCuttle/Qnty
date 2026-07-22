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
- `PROHIBITED` actions are absolute in every work lane.
- Classify the requested work under the lane rules below before acting.

## Work lanes and authority

### `PROTOCOL_LANE`

Work is in `PROTOCOL_LANE` if it advances or mutates protocol authority or state,
including any action that:

- executes Candidate 1 or another scientific protocol;
- accesses real, quarantined, production, or otherwise protected data;
- changes scientific state, execution count/budget, or runtime authorization;
- changes `docs/control/active_task.json`, a handoff receipt, an amendment, or
  continuity transition logic;
- enables or modifies paper, shadow, or live execution behavior.

In `PROTOCOL_LANE`:

- execute only the validated `NEXT_ACTION`;
- never perform anything listed under `PROHIBITED`;
- append the required immutable handoff receipt and update the active-task pointer
  before claiming completion.

### `ADMIN_LANE`

An explicitly requested, bounded administrative-maintenance task may proceed in
`ADMIN_LANE` even when it is not the validated `NEXT_ACTION`, but only when all of
the following are true:

- it does not execute the protocol or access protected data;
- it does not alter scientific state, execution counts/budgets, or runtime
  authorization;
- it does not modify active control records, handoff receipts, amendments, or
  continuity transition logic;
- it does not enable, invoke, or weaken guards around paper, shadow, or live
  execution;
- it does not perform anything listed under `PROHIBITED`;
- its exact files and intended effects are stated before mutation.

Examples include read-only PR review, CI/test/hygiene repair, repair of an
existing bounded PR, agent-contract maintenance, and additive replacement-control
tooling that remains unreachable from runtime.

`NEXT_ACTION` is evidence about the next permitted protocol-state transition; it
is not a universal scheduler for unrelated administrative maintenance.

`ADMIN_LANE` work must not append a handoff receipt or rewrite
`docs/control/active_task.json`. Report the lane, exact changed paths, and proof
that protocol/scientific/runtime state remained unchanged.

If lane classification is ambiguous, stop and report the ambiguity rather than
assuming `ADMIN_LANE`.

## Control state contract

- `docs/control/active_task.json` is the single active-task pointer. It names
  the task, protocol, phase, and the exact path plus receipt-byte SHA-256 of the
  latest handoff receipt.
- Handoff receipts under `docs/control/tasks/<task_id>/handoff_vNNN.json` are
  **immutable and append-only**. Never edit or delete an existing receipt.
- For `PROTOCOL_LANE` handoff work: write `handoff_v{N+1}.json` whose
  `predecessor` records the previous receipt's path and byte SHA-256 (the first
  receipt declares `"GENESIS"`), then rewrite `active_task.json` to point at the
  new receipt.
- Receipts never contain their own Git commit SHA; Git is the outer immutable
  envelope.
- Canonical JSON bytes for all control documents: UTF-8,
  `json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)`,
  no trailing newline. Use `quantbot.continuity.canonical_json_bytes`.
- Update the append-only handoff receipt **before** claiming completion of any
  `PROTOCOL_LANE` task step.

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

When the active phase is `candidate1_v1_synthetic_sandbox_governance`, the
machine-readable amendment is authoritative for the exploratory engineering
sandbox only. Real-data and scientific operations remain blocked, and the
existing V0 recovery/retirement prohibition remains active.

## Durable artifact-plane invariants

- `HASHED DOES NOT MEAN PRESERVED`: a fingerprint does not prove a durable copy
  exists.
- `/tmp` is workspace, never canonical storage; neither is `/srv/qnty`.
- Legacy path-sensitive fingerprints are historical protocol bindings, not
  portable content identities.
- No real-data protocol proceeds without a portable manifest, and no artifact
  is `VERIFIED_AVAILABLE` without two independently restored durable copies.
- Agents resolve artifact identity through Git-owned artifact records under
  `docs/artifacts/`, never from a local path or chat history.

## Repo basics

- Install: `python -m venv .venv && source .venv/bin/activate && pip install -e ".[test]"`
- Focused tests: `.venv/bin/python -m pytest tests/<file> -q`
- Smoke: `./scripts/release_smoke.sh` — full suite: `.venv/bin/python -m pytest -q`
- Never commit generated artifacts (`data/`, `output/`, `experiment_results/`)
  or secrets. Prefer minimal diffs; add tests with code changes.
