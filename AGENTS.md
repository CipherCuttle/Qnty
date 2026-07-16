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
4. Execute only the single validated `NEXT_ACTION` from `show`. Never perform
   anything listed under `PROHIBITED`.
5. Write/update the append-only handoff receipt under
   `docs/control/tasks/<task_id>/` (per the contract) **before** claiming
   completion.

Git, `docs/`, and verifier output outrank MemPalace, chat history, and any
local notes.
