# Shadow Context

_Last updated: 2026-04-09T20:12:08.827Z_

## Project
- Name: Qnty
- Archetype: quant-research
- Repo Root: /home/swirky/DevHub/repos/Qnty
- Branch: master
- Dirty State: dirty

## Current Focus
- Active File: unknown
- Visible Files: none
- Current Goal: unknown
- Current Blocker: unknown
- Suggested Next Step: inspect repo and establish current state

## Recent Decisions
- none yet

## Last Verdict
- PLAN: unknown
- CHANGESET: unknown
- VERIFY: unknown
- VERDICT: unknown

## Verified Facts
- Current branch is master
- Working tree is dirty

## Recent Terminal Signals
- [end] source /home/swirky/DevHub/repos/Qnty/.venv/bin/activate (exit=0)
- [start] source /home/swirky/DevHub/repos/Qnty/.venv/bin/activate
- [end] cd /home/swirky/DevHub/repos/Qnty source .venv/bin/activate python -c "import quantbot; print(quantbot.__file__)" pytest -q (exit=2)

## Recent Diagnostics
- .roo/shadow_context.md:5 warning MD022/blanks-around-headings: Headings should be surrounded by blank lines [Expected: 1; Actual: 0; Below]
- .roo/shadow_context.md:6 warning MD032/blanks-around-lists: Lists should be surrounded by blank lines
- .roo/shadow_context.md:12 warning MD022/blanks-around-headings: Headings should be surrounded by blank lines [Expected: 1; Actual: 0; Below]
- .roo/shadow_context.md:13 warning MD032/blanks-around-lists: Lists should be surrounded by blank lines
- .roo/shadow_context.md:19 warning MD022/blanks-around-headings: Headings should be surrounded by blank lines [Expected: 1; Actual: 0; Below]

## Important Constraints
- separate facts from assumptions
- prefer replayable checks
- no claims without evidence

## Recent Commits
- 47a5d23 Commit 4: add minimal strategy interface with Signal contract, NoOp default, ThresholdStrategy toy, signal_count in receipt
- 44ebd6a Commit 3: add end-to-end deterministic replay runner with manifest verification, receipt emission, and e2e tests
- 138fa7e Commit 2: minimal deterministic data path - manifest verifier, CSV loader, bar types, replay runner
- c835a3e fix: add explicit package discovery to pyproject.toml
- 635b7a3 Commit 1: Gate45 cleanroom bootstrap
