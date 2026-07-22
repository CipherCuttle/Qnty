# QNTY — agent entrypoint (Codex and compatible agents)

This file is a map, not the contract. The canonical shared contract lives at
`docs/agent/START_HERE.md` and the machine-readable task state lives under
`docs/control/`.

Before any non-trivial work you MUST:

1. Read `docs/agent/START_HERE.md` in full.
2. Run the context verifier:
   `.venv/bin/python -m quantbot.continuity verify`
   (then `.venv/bin/python -m quantbot.continuity show` for the context packet).
3. If `verify` fails: **stop immediately**, change nothing, and report the exact
   failure. Do not guess or reconstruct task state from memory or chat.
4. Classify the task using the canonical lane rules:
   - `PROTOCOL_LANE` work must match the single validated `NEXT_ACTION` and must
     never perform anything listed under `PROHIBITED`.
   - explicitly requested bounded `ADMIN_LANE` maintenance may proceed outside
     `NEXT_ACTION` only when it cannot affect protocol, scientific, protected-data,
     or runtime authority and does not touch active control records.
   - `PROHIBITED` remains absolute in both lanes.
5. For `PROTOCOL_LANE`, write/update the append-only handoff receipt under
   `docs/control/tasks/<task_id>/` before claiming completion. Do not create a
   handoff receipt for `ADMIN_LANE` work.

Git, `docs/`, and verifier output outrank MemPalace, chat history, and any
local notes.
