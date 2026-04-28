# Project Boundaries

## What belongs to Qnty

Qnty is the **research / falsification layer**. It contains:

- Deterministic paper-replay engines
- Kill criteria and validation receipts
- Shadow-observation workflows
- Backtest and diagnostic harnesses

## What does NOT belong to Qnty

- **Franken** is a separate paper-flow / reconciliation shell.
- **THT0** is a separate strategy stack.

## Franken references in this repo

You will see `Franken` mentioned in:

- `quantbot/experiment/calibration.py` — data structures for importing Franken reconciliation records
- `quantbot/experiment/index.py` — promotion contract logic that references external Franken calibration data
- Tests that verify Franken calibration ingestion
- Historical verdicts and plans that mention Franken as a separate system

These are **legacy / integration-boundary artifacts**. They exist to define the interface between Qnty and Franken, but they are not claims that Franken is part of Qnty or that Qnty requires Franken to function.

## THT0 references in this repo

You will see `THT0` mentioned in:

- Historical plans and verdicts that evaluated THT0 strategy variants
- Comments noting where THT0 adapters were excluded

These are historical research artifacts. THT0 is a separate strategy stack and is not part of the public Qnty v0.1 research preview.
