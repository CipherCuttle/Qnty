# ADR 0002 — QNTY Offline-Edge Entrypoint, Verdict, PBO, and Strategy-Gate Canonicalization

- **Date:** 2026-07-12
- **Scope:** governance boundary for the offline-edge validation ladder
  (`quantbot/experiment/offline_edge_real_validation.py`,
  `quantbot/experiment/offline_edge_validation_cli.py`,
  `quantbot/experiment/pbo.py`). Docs-only; authorizes no source-code behavior change.
- **Supersedes:** nothing. This ADR freezes boundaries that were previously implicit.

---

## Status

`ACCEPTED — DOCS_ONLY_GOVERNANCE_BOUNDARY`

- `EDGE_UNPROVEN` remains.
- `BLOCK_LIVE_INTEGRATION` remains.
- `final_offline_verdict = BLOCKED_BY_VALIDATION_IMPLEMENTATION` remains.
- This ADR proves no edge, no profitability, and no live readiness.
- This ADR authorizes no source-code behavior change.

This is a governance record. It writes down which entrypoint, receipt filename,
verdict vocabulary, and guardrail set are canonical, and which statistical
prerequisites gate strategy work. It changes no runtime behavior and unlocks no
verdict.

---

## Context

The offline-edge ladder is transitioning from funding diagnostics toward strategy
validation. Strategy work (signals, simulation, PnL, edge verdict) must **not** begin
until the governance boundaries below are explicit, because an honest out-of-sample
(OOS) verdict is only meaningful on top of a canonical, leakage-audited apparatus.
Recording these boundaries now prevents a future feature PR from silently diverging a
schema, weakening a guardrail, or promoting a proxy diagnostic into a scoring path.

Current ladder state:

```text
1. Raw CSV inventory / hashes                          done
2. Deterministic splits                                done
3. Row assignment                                      done
4. Gross observational returns scaffold                done
5. Cost drag scaffold                                  done
6. Funding diagnostics / adjustment scaffolding        diagnostic-complete
7. Strategy rules                                       not started
8. Trade / position simulation                         not started
9. Net PnL / equity / risk                             not started
10. Final offline edge verdict                         not started
```

Funding sub-ladder closeout:

```text
6A. funding inventory / alignment                      done
6B. timestamp joinability / convention / canonicalize  done
6C. readiness gate: 8 eligible, 2 blocked              done
6D. funding-adjusted bars scaffold                     done, diagnostic only
6E. policy contract                                    done
6F. fixture arithmetic scaffold                        done
6G. real-data row scaffold samples                     done
6H. row scaffold smoke + docs receipt                  done
6I. sample aggregate diagnostics                       done
6J. sample aggregate real-data smoke                   done
6K. sample aggregate docs receipt                      done
```

The step-6 closeout is anchored by the most recent real-data smoke receipt
(`QNTY_OFFLINE_EDGE_VALIDATION_REAL_VALIDATION_FUNDING_ADJUSTMENT_SAMPLE_AGGREGATE_SMOKE_RECORDED_BLOCKED`),
recorded at:

```text
code_commit_sha  = 2cbb4aa8194ca2ab54bf8e3d798a453ce83df044
receipt_sha256   = a4e0dcb90fcdc737d7fa6c94dbaf9f74b3a5367f180b5e6058882807fd7825a4
final_offline_verdict = BLOCKED_BY_VALIDATION_IMPLEMENTATION
```

Funding closeout policy:

```text
No 6L funding-only layer is recommended.
Funding diagnostics are frozen unless a later consumer exposes a concrete blocker.
```

Applying funding to returns — rather than exposing it as a diagnostic — crosses into
strategy/PnL territory, which is blocked. Funding work therefore stops here until a
downstream position-lifecycle consumer surfaces a concrete, named blocker.

---

## Decision 1 — Canonical real-data runner

```text
quantbot/experiment/offline_edge_real_validation.py
```

is the canonical real-data offline-edge validation runner.

Canonical real-data contract:

- output filename: `real_validation_receipt.json`
- stdout fields:
  - `final_offline_verdict=...`
  - `receipt_sha256=...`
  - `receipt_path=...`
- receipt key: `final_offline_verdict`
- current allowed verdict: `BLOCKED_BY_VALIDATION_IMPLEMENTATION`
- guardrails:
  - `/tmp` output boundary
  - source CSV pre/post hash discipline
  - recursive prod-path guard
  - forbidden top-level / calculation key guards
  - no live / exchange / paper-engine writes
  - no report promotion
  - no strategy / PnL / edge fields before explicit gates

Any real-data smoke, receipt, or verdict for the offline-edge ladder flows through this
runner and this contract. The guardrails above are model-risk controls (independent,
fail-closed, documented) and may be extended but not weakened.

---

## Decision 2 — Fixture CLI remains separate for now

```text
quantbot/experiment/offline_edge_validation_cli.py
```

is a deliberately separate fixture / skeleton harness for synthetic and golden-fixture
behavior.

Fixture contract:

- fixture-only / skeleton mode
- output filename: `validation_receipt.json`
- verdict vocabulary includes `SKELETON_ONLY`
- not the canonical real-data runner
- not used for real-data smoke receipts
- not used for strategy / PnL / edge validation

The two runners legitimately differ (real vs synthetic data, different receipt
filename, different verdict vocabulary, different guardrail depth). This divergence is
**intentional**, not drift to be reconciled.

```text
Do not unify the fixture CLI with the real-data runner in this ADR.
Do not delete or rewrite the fixture CLI.
Do not change fixture receipt schema in this ADR.
Any future adapter/refusal/unification work must be separately scoped.
```

Position: **defer unification until a concrete need appears** (for example, a caller
that genuinely requires the real schema from the fixture path). Do not converge the
schemas speculatively.

---

## Decision 3 — PBO proxy quarantine

```text
quantbot/experiment/pbo.py
```

is **not** canonical Bailey-style CSCV/PBO for offline-edge verdicts. It is a path
dispersion / z-score heuristic, not a paired in-sample/out-of-sample combinatorially
symmetric cross-validation.

- It may remain as prior / proxy diagnostic code.
- It must not be imported into any offline-edge scoring or verdict path.
- It must not produce or support an `OFFLINE_EDGE_CANDIDATE` verdict.
- Any future PBO used for an edge verdict must be a new, validated, receipt-backed
  CSCV/PBO implementation.

```text
The existing pbo.py is quarantined from verdict-bearing offline-edge validation.
```

---

## Decision 4 — Statistical gates before strategy / PnL / edge

Before any strategy signals:

- entrypoint boundary documented (this ADR)
- funding diagnostics frozen
- split leakage audit planned
- allowed inputs / forbidden inputs defined
- strategy rule contract defined
- no OOS scoring
- no returns / PnL / risk

Before OOS scoring:

- OOS window sealed and hash-recorded
- trial manifest exists
- trial count recorded before scoring
- symbol universe frozen
- split policy fixed
- purge / embargo / leakage assumptions audited
- nulls and benchmarks preregistered

Before a PnL / risk / edge verdict:

- cost / funding application contract consumed by the position lifecycle
- net return computation implemented under receipt guardrails
- Deflated Sharpe inputs available:
  - trial count
  - sample length
  - return distribution moments
- real CSCV/PBO or an equivalent overfitting diagnostic available
- multiple-testing adjustment policy available
- null / benchmark comparisons available
- no verdict promotion without an explicit PR

---

## Literature-backed rationale

Each item below is tied to a concrete QNTY gate, not general theory.

- **Bailey & López de Prado — Deflated Sharpe Ratio.** A Sharpe ratio selected from
  many trials is biased upward and must be deflated for the number of trials, sample
  length, and non-normality (skew/kurtosis) of returns. In QNTY, any future edge/Sharpe
  claim is gated behind a DSR that consumes an honest trial count from the trial
  manifest — hence the "trial count recorded before scoring" and "DSR inputs available"
  gates in Decision 4.

- **Bailey, Borwein, López de Prado & Zhu — Probability of Backtest Overfitting
  (CSCV).** PBO is computed by combinatorially symmetric cross-validation over paired
  IS/OOS splits. This is exactly what `pbo.py` is *not*; Decision 3 quarantines the
  proxy and requires a real CSCV before any `OFFLINE_EDGE_CANDIDATE` can exist.

- **White — Reality Check.** When multiple candidate models are evaluated, a
  data-snooping-robust test is required instead of per-model p-values. In QNTY, the
  moment more than one strategy configuration is scored, the "multiple-testing
  adjustment policy available" gate applies.

- **Hansen — Superior Predictive Ability (SPA) test.** A less conservative,
  more powerful companion to White's Reality Check for comparing many models against a
  benchmark. QNTY's null/benchmark comparison gate is intended to use SPA/Reality Check
  rather than naive per-config significance.

- **Harvey, Liu & Zhu — multiple testing in the cross-section of expected returns.**
  After many trials, an ordinary t-stat threshold (t > 2) is far too lenient; the bar
  must rise (t > 3.0 territory) with an explicit multiple-testing haircut. QNTY
  pre-registers this haircut so no naive t-stat unlocks a verdict.

- **López de Prado — purged K-fold, embargo, CPCV.** Overlapping financial labels leak
  information across naive CV folds, inflating measured performance. QNTY's step-2
  "deterministic splits" predate any purge/embargo requirement and must be audited for
  leakage *before* strategy — the "split leakage audit planned" and "purge/embargo/
  leakage assumptions audited" gates.

- **Kapoor & Narayanan — data leakage and reproducibility.** A leakage taxonomy shows
  that leakage produces over-optimistic, non-reproducible results across many published
  studies, and recommends model-info-sheet documentation. QNTY adopts a leakage
  checklist / confounder register as a diagnostic before signals touch splits.

- **CRISP-DM / CRISP-ML(Q).** A lifecycle with explicit quality gates separating data
  understanding, modeling, evaluation, and deployment. QNTY frames the ladder as such a
  lifecycle and refuses to skip the data→modeling→evaluation gate ordering; strategy
  (modeling) cannot precede a clean data/split (data understanding) foundation.

- **Preregistration / registered reports / preanalysis plans.** Hypotheses, metrics,
  nulls, and the analysis plan must be fixed before OOS data is seen. QNTY's offline
  steps 7–10 must obey preregistered nulls/gates/kill-criteria; the "nulls and
  benchmarks preregistered" gate and the reconciliation note (next PR) enforce this.

---

## Existing governance docs

Governance/preregistration prior art already exists and must be reconciled later, not
blindly imported:

- `docs/research/preregistered_forward_experiment_plan.md`
- `docs/status/realized_attribution_spec.md`

```text
These documents are governance/preregistration prior art for a related paper/forward
research track. The offline-edge ladder must reconcile with them before strategy
scoring, but this ADR does not merge or rewrite them.
```

These govern a related *forward paper* experiment track; the offline ladder is CSV
replay. The reconciliation maps one onto the other — it does not merge them.

---

## Never-batch rules

Each of the following must land as its own single-purpose PR, never bundled with
feature work:

- verdict vocabulary changes
- receipt schema version changes
- guardrail scanner changes
- output path rule changes
- PBO / DSR implementation
- OOS seal definition
- trial manifest definition
- split leakage / purge / embargo policy
- strategy rule definition
- strategy scoring
- PnL / risk computation
- verdict promotion

---

## What this ADR explicitly does not do

- no code changes
- no CLI unification
- no schema unification
- no fixture CLI rewrite
- no PBO implementation
- no DSR implementation
- no split leakage audit implementation
- no strategy rule implementation
- no signal generation
- no position simulation
- no returns
- no PnL
- no Sharpe
- no drawdown
- no risk
- no edge candidate
- no live readiness

---

## Next recommended PRs

```text
1. docs: ADR offline-edge entrypoint/verdict/PBO/strategy gates          this PR
2. docs: reconcile offline-edge ladder with preregistration docs
3. docs or diagnostic: split leakage / purge-embargo audit
4. scripts/tests: canonical real-runner smoke wrapper
5. diagnostics: strategy rule contract, no scoring
6. diagnostics: trial manifest + OOS seal, no scoring
7. diagnostics: purged/embargo split implementation if audit requires it
8. diagnostics: strategy signal scaffold, no returns
9. diagnostics: position lifecycle scaffold, no PnL
10. only later: gross/net return, risk, DSR/PBO, verdict path
```

---

## Final decision

```text
Funding diagnostics are diagnostic-complete.
The canonical real-data runner is offline_edge_real_validation.py.
The fixture CLI remains separate and fixture-only.
The existing pbo.py is quarantined from verdict-bearing validation.
Strategy work is blocked until preregistration reconciliation, split leakage audit,
trial manifest, and OOS-seal gates exist.
EDGE_UNPROVEN remains.
BLOCK_LIVE_INTEGRATION remains.
```
