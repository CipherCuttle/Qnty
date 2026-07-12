# ADR 0003 — Offline Edge Receipt Auditor Boundary

**Status:** ACCEPTED — DOCS_ONLY_GOVERNANCE_BOUNDARY

---

## Context

The QNTY offline-edge validation ladder has progressed through diagnostics and
governance documentation but remains at a blocked verdict. The following
posture is unchanged:

- `EDGE_UNPROVEN` remains.
- `BLOCK_LIVE_INTEGRATION` remains.
- `final_offline_verdict = BLOCKED_BY_VALIDATION_IMPLEMENTATION` remains.

The current offline-edge ladder consists of steps 1–10:

1. Input inventory & split smoke
2. Row materialization & split assignment smoke
3. Timestamp convention & offset precision smoke
4. Funding-to-bars temporal joinability smoke
5. Funding adjustment arithmetic scaffold smoke
6. Funding adjustment row scaffold smoke
7. Funding application readiness gate smoke
8. Split leakage audit diagnostics
9. Strategy rule contract diagnostics
10. Real-data preflight ready receipt

Recent merged PRs:

- **PR #189** — strategy_rule_contract_diagnostics (diagnostics section in
  offline-edge receipt)
- **PR #190** — real-data smoke docs receipt (docs-only smoke receipt recording)

This ADR exists to prevent future agent drift before deeper work on:

- strategy rule contract
- trial manifest
- OOS seal
- scoring
- PBO / DSR
- verdict promotion

Without an explicit boundary, there is risk that future work conflates
review, critique, or diagnostic output with evidence of edge.

---

## Core Decision

```
BUILD ONLY THE BOUNDARY NOW.
DO NOT BUILD THE TOOL YET.
RENAME "LEARNER" TO "OFFLINE EDGE RECEIPT AUDITOR."
```

Use the name **Offline Edge Receipt Auditor**.

---

## Forbidden Names

The following names are explicitly forbidden for this concept:

- Learner
- Socratic Learner
- AI Learner
- self-learning reviewer
- AI trading coach
- strategy critic
- alpha reviewer

**Reason:** `"Learner" implies optimization, parameter search, strategy
improvement, or adaptive alpha. "Receipt Auditor" implies read-only
bureaucratic blockage.`

---

## Definition

The **Offline Edge Receipt Auditor** is defined as:

> A read-only, non-binding, hostile governance reviewer over existing QNTY
> offline-edge receipts.

It is **NOT**:

- an AI trading brain
- a strategy optimizer
- a parameter tuner
- a signal reviewer
- a PnL reviewer
- a Sharpe reviewer
- a paper-trading assistant
- a live-trading assistant
- a verdict input
- a canonical-runner dependency

---

## Preserved Verdict Posture

```
EDGE_UNPROVEN remains.
BLOCK_LIVE_INTEGRATION remains.
final_offline_verdict = BLOCKED_BY_VALIDATION_IMPLEMENTATION remains.
This ADR proves no edge, no profitability, no risk metric, and no live readiness.
This ADR authorizes no source-code behavior change.
```

---

## Allowed Behavior

The future auditor may only:

- summarize blockers
- list missing evidence
- identify leakage risks
- identify overfit risks
- ask Socratic / falsification questions
- propose deterministic diagnostics
- preserve blocked-state warnings
- add reasons to stay blocked

---

## Forbidden Behavior

The future auditor may **NOT**:

- remove blockers
- change verdicts
- promote `final_offline_verdict`
- propose strategy parameters
- propose entry rules
- propose exit rules
- propose position sizing
- suggest optimization
- suggest tuning
- inspect or interpret PnL
- inspect or interpret Sharpe
- inspect or interpret drawdown
- inspect or interpret risk metrics
- claim edge
- claim paper-readiness
- claim live-readiness
- recommend exchange integration
- recommend paper-engine integration
- recommend live integration
- call an LLM API from the canonical runner
- mutate source CSVs
- mutate DBs
- mutate receipts
- mutate generated outputs
- import or depend on `quantbot/experiment/pbo.py`
- be imported by `quantbot/experiment/offline_edge_real_validation.py`
- become part of the verdict path

---

## Roadmap Placement

This ADR lands:

> after funding diagnostics / split leakage audit / strategy-rule-contract
> diagnostic work
> before trial manifest / OOS seal / scoring / trade simulation / net PnL /
> DSR / PBO / verdict promotion

---

## Future Phases

```
Phase 0 docs-only ADR: allowed now
Prompt-pack generator: deferred
Review receipt validator: deferred
Canonical runner integration: killed under current constraints
Strategy optimizer: killed
Autonomous trader: killed
```

No future executable auditor phase is authorized by this ADR.
Any future executable phase requires a separate ADR and PR.

---

## Architecture Boundary

**Safe location now:**
`docs/ADR/0003-offline-edge-receipt-auditor-boundary.md`

**Forbidden locations (for this PR):**

- `quantbot/experiment/offline_edge_real_validation.py`
- `quantbot/experiment/offline_edge_validation_cli.py`
- `quantbot/experiment/pbo.py`
- `tests/experiment/test_offline_edge_real_validation.py`
- `quantbot/strategy/**`
- `quantbot/experiment/runner.py`
- `quantbot/experiment/walkforward_runner.py`
- `quantbot/experiment/portfolio_evaluator.py`
- any Python file

---

## Rationale

Repeated strategy trials, hidden LLM-assisted iteration, and narrative
post-hoc review can create false confidence. The academic literature
documents multiple mechanisms by which apparent edge can arise from
methodological weakness:

- **White Reality Check / data snooping** — multiple tests inflate false
  discovery rates.
- **Hansen SPA test** — a more robust test for data-snooped performance.
- **Deflated Sharpe Ratio** — adjusts Sharpe for multiple testing,
  non-Normal returns, and sample length.
- **Probability of Backtest Overfitting / CSCV** — measures how much
  strategy selection is driven by noise.
- **Harvey-Liu-Zhu multiple testing in finance** — higher t-ratio thresholds
  required when many factors are tested.
- **López de Prado purged K-fold / embargo / CPCV** — prevents leakage
  across train/test splits in time series.
- **Kapoor-Narayanan leakage and reproducibility** — documents subtle
  information leakage in ML backtesting pipelines.
- **Reflexion / Self-Refine risks for iterative LLM loops** — repeated
  LLM critique of the same output can create illusory improvement.
- **LLM-as-judge bias / self-preference** — LLM evaluators favor outputs
  that match their own style or content.

The auditor may identify missing evidence and reasons to stay blocked.
The auditor may not convert review language into evidence of edge.
Deterministic receipts, hashes, tests, preregistered gates, and explicit
verdict policy remain source of truth.

---

## Cybernetic Loop

### Bad loop (forbidden by this ADR)

```
receipt → LLM critique → tweak strategy → rerun → better in-sample story → hidden overfit
```

### Allowed loop

```
receipt → auditor says KEEP_BLOCKED / MISSING_EVIDENCE → human chooses
deterministic diagnostic → separate PR → still blocked unless explicit
future gate passes
```

---

## Kill Criteria

The auditor concept is killed if future work attempts to:

- add Python in this ADR PR
- add an LLM API call
- connect to the canonical runner
- use auditor output as a verdict input
- generate strategy parameters
- generate entry / exit rules
- generate position sizing
- evaluate PnL
- evaluate Sharpe
- evaluate drawdown
- evaluate risk
- evaluate edge
- weaken `EDGE_UNPROVEN`
- weaken `BLOCK_LIVE_INTEGRATION`
- import `pbo.py`
- create a paper / live integration wedge

---

The auditor may add reasons to stay blocked; it may not create reasons to proceed.