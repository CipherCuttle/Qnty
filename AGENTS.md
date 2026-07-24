# QNTY — agent entrypoint (Codex and compatible agents)

This file is a map, not the contract. The canonical shared contract lives at
`docs/agent/START_HERE.md` and the machine-readable task state lives under
`docs/control/`.

Read `docs/agent/START_HERE.md` in full, then classify the request before any
protocol bootstrap. `PROTOCOL_LANE` requires
`.venv/bin/python -m quantbot.continuity verify` and
`.venv/bin/python -m quantbot.continuity show`, the validated `NEXT_ACTION`,
and its required handoff.

Permanent safety constraints limit scientific/runtime actions; they do not
globally block bounded `ADMIN_LANE` work. Do not return a generic blocked
verdict unless the requested action itself is prohibited, integrity-invalid,
directly prevented, or the lane is genuinely ambiguous. Never create a handoff
receipt for `ADMIN_LANE` work.

Git, `docs/`, and verifier output outrank MemPalace, chat history, and any
local notes.
