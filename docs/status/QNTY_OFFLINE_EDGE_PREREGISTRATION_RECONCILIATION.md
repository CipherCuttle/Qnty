# QNTY_OFFLINE_EDGE_PREREGISTRATION_RECONCILIATION

## Status

```text
RECONCILIATION_ONLY — NO_STRATEGY_SCORING
```

- `EDGE_UNPROVEN` remains.
- `BLOCK_LIVE_INTEGRATION` remains.
- `final_offline_verdict = BLOCKED_BY_VALIDATION_IMPLEMENTATION` remains.
- This document proves no edge, no profitability, no strategy validity, and no
  live readiness.
- This document authorizes no source-code behavior change.

This is a governance bridge, not a protocol merge. It records which parts of the
existing preregistration and attribution prior art the offline-edge CSV replay
ladder may later reuse, which parts it must not import directly, and which
machine-readable artifacts must exist before any strategy signal is scored. It
changes no runtime behavior and unlocks no verdict.

---

## Purpose

The existing preregistration and attribution documents are governance prior art
for a related paper/forward research program (realized-attribution measurement,
short-side hypothesis, forward experiment governance). The offline-edge ladder is
a separate track: a raw CSV replay validation harness driven by
`quantbot/experiment/offline_edge_real_validation.py`, currently frozen at
funding diagnostics (step 6) with strategy work (steps 7–10) blocked.

Because both tracks concern honest, falsifiable evaluation under the same
`EDGE_UNPROVEN` / `BLOCK_LIVE_INTEGRATION` boundaries, the prior-art docs carry
reusable governance discipline. But they were written for a forward/paper track
against a live-ledger measurement contract — not for offline CSV replay — so
their *conclusions*, *lanes*, and *runners* are not transferable. This note maps
what can be reused, what cannot be reused directly, and what must be
machine-encoded later before strategy scoring.

```text
This document reconciles governance; it does not merge protocols, implement a
runner, score a strategy, or authorize a verdict.
```

---

## Source documents reviewed

1. **`docs/ADR/0002-offline-edge-entrypoint-verdict-pbo-strategy-gate.md`**
   - Names `quantbot/experiment/offline_edge_real_validation.py` the canonical
     real-data offline-edge runner (`real_validation_receipt.json`,
     `final_offline_verdict`, recursive prod-path and forbidden-key guardrails,
     `/tmp` boundary, sha256 digest).
   - Keeps `quantbot/experiment/offline_edge_validation_cli.py` a deliberately
     separate fixture / skeleton harness (`validation_receipt.json`,
     `SKELETON_ONLY`) — divergence is intentional, not drift to be unified.
   - Quarantines `quantbot/experiment/pbo.py` (a path-dispersion / z-score proxy)
     from any verdict-bearing offline-edge validation path.
   - Declares funding diagnostics diagnostic-complete (no 6L funding-only layer).
   - Blocks strategy work behind preregistration reconciliation, split leakage
     audit, trial manifest, and OOS-seal gates.

2. **`docs/research/preregistered_forward_experiment_plan.md`** (v1.0.0,
   2026-07-06)
   - Docs-only preregistration / governance plan; implements no runner, registry,
     lane, or code.
   - Freezes metrics, horizons, nulls, promotion gates, and kill criteria *before*
     scoring to prevent moving goalposts (the preregistration discipline behind
     Reality-Check / SPA-style honesty).
   - Governs a related **forward/paper** research track — not offline CSV replay —
     and sits above the measurement contract and the short-side hypothesis.

3. **`docs/status/realized_attribution_spec.md`** (v1.0.0, 2026-07-06)
   - Measurement contract for realized vs unrealized attribution; defines the
     reporting language and the accounting decomposition (realized/unrealized
     split, funding and fees explicit, `N_closed` mandatory, `1e-6` identity
     tolerance, read-only IO).
   - Produces no numbers itself. Should inform a *later* net / PnL attribution
     vocabulary for offline-edge, but it does not itself validate offline CSV
     edge — it describes a live-ledger accounting contract, not a CSV replay proof.

4. **`docs/research/short_v3_carry_harvest_downtrend.md`** (v1.0.0, 2026-07-06)
   - Concrete short-side hypothesis prior art (`short_v3_carry_harvest_downtrend`:
     harvest positive funding while short in downtrends), with eligibility rules,
     mandatory nulls, an `N_closed_short` sample floor, and promotion gates.
   - Docs-only: implements and authorizes no shorting. Must **not** be treated as
     an implemented offline-edge strategy; it may become a registered candidate
     only through a later offline-edge trial manifest.

5. **`docs/plans/QNTY_REALIZED_ATTRIBUTION_AND_SHORTING_RESEARCH_FOUNDATION.md`**
   (2026-07-06)
   - Plan of record for the related realized-attribution / shorting research
     foundation; sequenced the three-PR forward-track program
     (spec → hypothesis → forward experiment plan).
   - Should remain a separate track unless explicitly bridged; its facts
     (green equity is mostly unrealized long exposure; realized gross PnL is
     negative) are live-ledger observations, not offline CSV replay results.

---

## Scope distinction

| Track | Purpose | Data source | Status | May be reused by offline-edge? | Limitation |
|---|---|---|---|---|---|
| Offline-edge CSV replay ladder | Validate historical raw-CSV edge under a fail-closed apparatus | Real CSV files (replay) | Frozen at step 6 (funding diagnostics); steps 7–10 blocked | N/A (this is the track) | No strategy, no OOS scoring, no verdict; `BLOCKED_BY_VALIDATION_IMPLEMENTATION` |
| Forward/paper realized attribution track | Define measurement language and forward-experiment governance for paper lanes | Live/paper SQLite ledger | Docs-only prior art (spec + prereg plan v1.0.0) | Governance discipline / reporting vocabulary only | Not executable offline-edge proof; paper-lane conclusions are not CSV replay conclusions |
| Short V3 hypothesis research | Preregistered short-side hypothesis design | None (design only) | Docs-only hypothesis (v1.0.0) | As a *candidate* only via a future trial manifest | Not a scored offline-edge strategy; shorting unimplemented and unauthorized |
| Fixture / skeleton validation CLI | Synthetic / golden-fixture harness behavior | Synthetic fixtures | Separate, `SKELETON_ONLY` | Not for real-data validation | Different schema/verdict/filename by design; weaker guardrail depth bounded to synthetic data |
| Existing `pbo.py` proxy diagnostic | Path-dispersion / z-score heuristic | Prior code | Quarantined | Not for verdict-bearing PBO | Not Bailey-style CSCV/PBO; a new validated CSCV is required for any edge verdict |

Key conclusions:

- Offline-edge CSV replay is the **only** track currently relevant to validating
  historical raw-CSV edge.
- Forward/paper docs provide **governance language and reporting discipline**, not
  executable offline-edge proof.
- Short V3 is **hypothesis prior art**, not a scored offline-edge candidate.
- The fixture CLI is **synthetic / golden-fixture support**, not real-data
  validation.
- The existing `pbo.py` is **quarantined** and cannot be used for verdict-bearing
  PBO.

---

## What offline-edge may inherit

The offline-edge ladder may *later* inherit the following governance concepts
(as discipline, not as conclusions):

- **Status boundaries:**
  - `EDGE_UNPROVEN`
  - `BLOCK_LIVE_INTEGRATION`
  - no live-readiness language
- **Preregistration discipline:**
  - metrics frozen before scoring
  - horizons frozen before scoring
  - nulls defined before scoring
  - kill criteria defined before scoring
  - promotion gates defined before scoring
- **Trial counting:**
  - every evaluated variant counted
  - no post-hoc omission of failed variants
- **Null / benchmark expectations:**
  - randomized-entry or exposure-matched nulls
  - benchmark lanes or benchmark rules
- **Reporting discipline:**
  - realized vs unrealized separation
  - gross / cost / funding / net decomposition (later, once returns exist)
  - limitations stated with every receipt
- **No-goal discipline:**
  - no live trading
  - no leverage authorization
  - no paper-engine promotion from offline CSV receipts

---

## What offline-edge must not inherit directly

The offline-edge ladder must **not** import any of the following as-is:

- no direct import of paper-engine semantics
- no direct import of paper lane results
- no direct import of live/paper ledger conclusions
- no direct import of Short V3 as a validated strategy
- no direct use of `pbo.py` as verdict-bearing PBO
- no direct promotion path from offline CSV replay to live/paper readiness
- no use of realized attribution docs as proof of historical CSV edge
- no OOS scoring without a sealed offline-edge manifest

---

## Required machine-encoded artifacts before strategy scoring

Prose governance is **not enough**. The prior-art docs describe rules in natural
language; the offline-edge apparatus is fail-closed and receipt-driven, so its
governance must be machine-readable and hash-checkable. Before any strategy
signal is scored, offline-edge needs the following future diagnostic artifacts
(none implemented by this PR):

1. **`strategy_rule_contract_diagnostics`**
   - allowed inputs
   - forbidden inputs
   - timestamp relation of inputs to decision time
   - side semantics
   - notional semantics
   - complexity budget
   - no scoring

2. **`trial_manifest_diagnostics`**
   - strategy candidates
   - parameter grids
   - symbol universe
   - split policy
   - cost / funding cases
   - nulls
   - benchmarks
   - trial count
   - manifest SHA-256
   - no scoring

3. **`oos_seal_diagnostics`**
   - OOS windows
   - seal timestamp
   - seal hash
   - no parameter selection after OOS peeking
   - no scoring

4. **`split_leakage_audit_diagnostics`**
   - purge / embargo assumptions
   - overlapping-label risk
   - timestamp-leakage risk
   - symbol-universe leakage risk
   - same-bar / future-bar leakage risk
   - no scoring

5. **`null_benchmark_contract_diagnostics`**
   - null definition
   - benchmark definition
   - exposure matching policy
   - randomized-entry policy if used
   - no scoring

All five are future work. This PR implements none of them.

---

## Required gates before future phases

```text
Before strategy signals:
- preregistration reconciliation recorded
- split leakage audit recorded
- strategy rule contract recorded
- allowed/forbidden inputs recorded
- no OOS scoring

Before position lifecycle:
- strategy signal contract exists
- side semantics recorded
- notional semantics recorded
- funding/cost dependency recorded
- no PnL

Before gross/net return:
- trial manifest exists
- OOS seal exists
- split leakage audit passes or blocks
- null/benchmark contract exists
- no verdict promotion

Before risk/Sharpe/DSR/PBO:
- returns exist under sealed manifest
- trial count recorded before scoring
- sample length known
- return moments available
- real CSCV/PBO implementation exists
- existing pbo.py remains quarantined

Before final offline verdict:
- all above gates pass
- multiple-testing adjustment recorded
- null/benchmark comparison recorded
- no forbidden key scans fail
- verdict promotion PR explicitly scoped
```

---

## Conflicts and resolutions

| Potential conflict | Resolution |
|---|---|
| Forward/paper docs discuss paper lanes; offline-edge uses raw CSV replay. | Inherit reporting discipline, not paper-lane conclusions. |
| Short V3 hypothesis exists; offline-edge has no strategy yet. | Short V3 may become a future registered candidate only via a trial manifest. |
| Existing `pbo.py` exists but is a proxy. | Quarantine from the verdict path; a future CSCV/PBO must be new / validated. |
| Fixture CLI exists with a separate schema. | Keep the fixture CLI separate; the real runner is canonical for real data. |
| Realized attribution spec defines PnL decomposition. | Use later as reporting vocabulary only, after a position / net-return layer exists. |

---

## Non-goals

- no code changes
- no schema changes
- no verdict changes
- no strategy implementation
- no signal generation
- no trial manifest implementation
- no OOS seal implementation
- no split audit implementation
- no PBO implementation
- no DSR implementation
- no return / PnL / risk computation
- no edge candidate
- no live-readiness implication

---

## Final reconciliation decision

```text
The offline-edge ladder may reuse governance discipline from the preregistration and attribution docs, but it must not import paper-lane conclusions, Short V3 conclusions, or proxy PBO diagnostics as proof.
Before strategy scoring, the offline-edge ladder requires its own machine-readable strategy contract, trial manifest, OOS seal, split leakage audit, and null/benchmark contract.
EDGE_UNPROVEN remains.
BLOCK_LIVE_INTEGRATION remains.
final_offline_verdict remains BLOCKED_BY_VALIDATION_IMPLEMENTATION.
```
