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

## Work-lane classification (before bootstrap)

Classify the requested work before invoking the continuity bootstrap. Chat
history is not authoritative for protocol state, but it can identify the
requested work for this classification.

### `ADMIN_LANE`

Ordinary code review, tests, documentation, CI repair, bounded refactoring, and
repository hygiene default to `ADMIN_LANE` when they do not mutate protocol
authority or execute protected operations. Bounded implementation also belongs
here when it cannot mutate protocol authority or access protected data.
`ADMIN_LANE` work:

- does not require a valid protocol `NEXT_ACTION`;
- must not rewrite `docs/control/active_task.json`, handoff receipts,
  amendments, scientific state, execution budgets/counts, or artifact
  availability;
- must not change real-data, paper, shadow, or live authorization, or runtime
  guards;
- must not access protected data or enable, invoke, or weaken paper, shadow, or
  live execution guards; and
- remains subject to every `PROHIBITED` action and scientific safety constraint.

Report the lane, exact changed paths, and proof that protocol/scientific/runtime
state remained unchanged. Do not append a handoff receipt for `ADMIN_LANE` work.

### `PROTOCOL_LANE`

Work is in `PROTOCOL_LANE` if it advances or mutates protocol authority or
state, including protocol execution, protected-data access, changes to control
records or transition logic, scientific state, execution authorization, or
paper/shadow/live behavior.

## Protocol bootstrap

```bash
.venv/bin/python -m quantbot.continuity verify
.venv/bin/python -m quantbot.continuity show
```

- For `PROTOCOL_LANE`, if `verify` fails, **stop**. Do not act or repair state
  by guessing; report the exact failure to the operator. A failed verifier
  blocks protocol work, not unrelated `ADMIN_LANE` work.
- If `verify` passes, `show` prints the validated context packet: current task,
  protocol, phase, safety state, latest handoff receipt, blockers, required
  artifacts, exactly one next action, and prohibited actions.
- `PROHIBITED` actions are absolute in every work lane. `EDGE_UNPROVEN`,
  `BLOCK_LIVE_INTEGRATION`, and other persistent scientific safety constraints
  limit permissible actions, but do not by themselves mean all repository work
  is blocked.
- In `PROTOCOL_LANE`, execute only the validated `NEXT_ACTION`, never perform a
  `PROHIBITED` action, and append the required immutable handoff receipt and
  update the active-task pointer before claiming completion.

## Safety constraints and verdicts

The following are `SAFETY_CONSTRAINTS`, not universal workflow blockers:
`EDGE_UNPROVEN`, `BLOCK_LIVE_INTEGRATION`, real-data or quarantine prohibition,
scientific/paper/live authorization false, execution unauthorized, durable
stores unconfigured, and V0 unavailable. They remain absolute boundaries for
the actions they describe; they do not globally block bounded `ADMIN_LANE`
work.

Do not return generic `VERDICT_BLOCKED` merely because a context packet includes
one of those constraints. Report work blocked only when the requested action is
explicitly prohibited, a requested protocol transition fails integrity
verification, a condition directly prevents that requested action, or lane
classification is genuinely ambiguous.

Use exactly one final verdict: `READY_TO_WORK`, `READY_FOR_REVIEW`,
`BLOCKED_BY_INTEGRITY_ERROR`, `BLOCKED_BY_ACTION_SPECIFIC_CONDITION`,
`PROHIBITED_ACTION`, or `AMBIGUOUS_LANE`.

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

## Long-running command ownership

Start only one instance of a logical long-running command. Record enough
ownership evidence to identify it: PID or process group, command, working
directory, a durable output log when needed, and its final exit status. A tool
or terminal timeout, silent terminal, detached output, or compacted response
does not prove that the process exited.

Poll the owned process and its log with bounded, one-shot status checks instead
of starting another instance; avoid indefinite terminal polling or `sleep`
loops. Before retrying, prove that the previous process exited, or terminate
its exact process group and confirm termination. Never run concurrent retries
of the same full test suite.

Never infer pass or failure without a captured final exit code. If process
ownership or exit evidence is lost, report the run as `unverifiable`. Clean
temporary files only when they are confirmed inactive and scoped to the
abandoned run. This is behavioral guidance: use durable logs and ownership
evidence when appropriate for long-running commands, not mandatory
infrastructure for every short command.

## Pytest temp-root hygiene

Manual, full-suite, and audit pytest runs must use pytest's default,
system-`/tmp`-backed `tmp_path` (plain `pytest ...`, no `TMPDIR=` and no
`--basetemp=`). This is required, not just conventional: some tests are
path-sensitive to a prohibited-prefix check keyed on `/tmp`, and pointing
`--basetemp` outside `/tmp` has been shown to flip their outcome (see
`tests/control/test_basetemp_path_sensitivity_debt.py`). Pytest also
self-manages retention of its own `/tmp`-backed basetemp; a hand-rolled
persistent temp root does not get that cleanup.

A persistent cache-backed root (anything under `~/.cache/` or similar,
reused across runs) is forbidden for pytest temp state at any scope. If a
task genuinely needs an explicit, owned temp root outside pytest's default
(e.g. a one-off review export or scope diff), create it fresh under `/tmp`
with `mktemp -d /tmp/qnty-<purpose>.XXXXXX`, use a `trap ... EXIT INT TERM`
cleanup that removes only that path, and never redirect it under `~/.cache`
or any other durable location.

Heavy suites (e.g. the continuity/control tests) can leave several GiB of
scratch under `/tmp` for the run's duration. Before a full-suite or heavy
audit run, verify the host has adequate free `/tmp` capacity; if capacity is
tight, treat that as an operational concern to resolve by freeing space or
scheduling the run elsewhere — never by redirecting pytest's temp root to a
persistent `~/.cache` path, and not by broadly deleting `/tmp` contents you
do not own.

## Review/task worktree lifecycle

Ad hoc review, rereview, or audit worktrees (typically created under `/tmp`
via `git worktree add --detach`) are scratch, not durable state, and are not
cleaned up automatically. Before removing one, independently prove all of
the following:

- the relevant task or PR is complete/merged;
- the worktree's HEAD is safely preserved/reachable as required (e.g. an
  ancestor of the merged commit);
- `git status --short` in the worktree is empty;
- there are zero untracked files in the worktree;
- no process is actively using the checkout.

Only once all of those hold, remove it with the plain form:

```bash
git worktree remove <worktree-path>
```

If plain `git worktree remove` refuses, **stop** — do not fall back to
`--force` merely to make cleanup succeed. `--force` discards the normal
safety checks (dirty state, untracked files) and is not a routine cleanup
step; treat a refusal as a signal to investigate, not an obstacle to
override.

Never remove a worktree you did not create, and never remove one that has
not been proven merged and clean by that verification. Do not run
`git worktree prune` or otherwise batch-remove worktrees you have not
individually verified.

## Repo basics

- Install: `python -m venv .venv && source .venv/bin/activate && pip install -e ".[test]"`
- Focused tests: `.venv/bin/python -m pytest tests/<file> -q`
- Smoke: `./scripts/release_smoke.sh` — full suite: `.venv/bin/python -m pytest -q`
- Never commit generated artifacts (`data/`, `output/`, `experiment_results/`)
  or secrets. Prefer minimal diffs; add tests with code changes.
