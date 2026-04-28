# Contributing

## Evidence-first contributions

Qnty is a falsification-first research repo. Contributions should be evidence-first:

- Claims must be proportionate to evidence.
- Provide artifacts, receipts, or reproducible steps.
- State uncertainty honestly when evidence is incomplete.

## No alpha or profitability claims without artifacts

Do not claim a strategy is profitable, has edge, or is ready for deployment without:

- Clear backtest or validation artifacts
- Explicit caveats and limitations
- Acknowledgment of what remains unknown

## No live trading additions in normal PRs

Live trading integrations, exchange connectors, or capital-deployment features are out of scope for normal pull requests. Discuss in an issue first if you believe there is a strong research reason.

## Tests and smoke checks

- Include or update tests for code changes.
- Ensure `./scripts/release_smoke.sh` passes before opening a PR.
- Prefer deterministic tests that can be reproduced by others.

## Keep Qnty separate from Franken / THT0

- Qnty is the research / falsification layer.
- Franken is a separate paper-flow / reconciliation shell.
- THT0 is a separate strategy stack.

Do not blur these boundaries in documentation or code comments.
