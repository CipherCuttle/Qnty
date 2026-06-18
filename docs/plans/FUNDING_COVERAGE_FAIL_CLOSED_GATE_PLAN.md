# Funding Coverage Fail-Closed Gate — Plan

**Date:** 2026-06-18
**Lane scope:** `paper_pnl_v1` (and any future QNTY paper lane)
**Status:** Plan — docs-only; no code lands in this commit. This
document only specifies the future implementation requirements.
**Companion receipt:**
[`QNTY_FUNDING_COVERAGE_GAP_RECEIPT_2026-06-18.md`](../experiments/QNTY_FUNDING_COVERAGE_GAP_RECEIPT_2026-06-18.md)
**Supersedes:** nothing. This plan adds a hard pre-batch gate on top
of existing engine semantics. It does not change the engine
semantics of the existing `paper_pnl_v1` run.

---

## 1. Motivation

The VM funding-gap forensic (see companion receipt) confirmed that:

- the funding loader silently skips symbols whose CSV is missing or
  empty
  ([`quantbot/data/funding_loader.py:37-58`](../../quantbot/data/funding_loader.py:37-58));
- the upstream funding fetch has no completeness gate
  ([`scripts/fetch_funding_rest.py:138-156`](../../scripts/fetch_funding_rest.py:138-156));
- the paper engine treats missing funding as `0.0` with
  `rate_available=False`
  ([`quantbot/paper/engine.py:107-134`](../../quantbot/paper/engine.py:107-134));
- the SQLite verifier accepts `rate_available=0, funding_amount=0.0`
  rows unconditionally as long as arithmetic consistency holds
  ([`quantbot/paper/sqlite_verify.py:505-520`](../../quantbot/paper/sqlite_verify.py:505-520)).

Consequence: a batch can be **internally consistent** and still be
**non-evidentiary** for net-of-carry claims. This plan specifies a
fail-closed gate that prevents that ambiguity from silently
propagating into comparator verdicts.

---

## 2. Hard constraints carried forward

- `paper_ledger.db` is not mutated retroactively.
- `/srv/qnty/output/paper_pnl_v1` is not written to retroactively.
- No live trading, exchange keys, or real orders.
- No silent substitution of zero for required funding.
- No "edge confirmed" or "profitability" language in any
  implementation PR that lands against this plan.

---

## 3. Pre-batch coverage determination (gate input)

Before any paper batch is allowed to commit rows to a paper ledger,
the batch runner must determine, in this order:

1. **Set of required funding intervals.** For every symbol that is
   held at any point during the batch window, and for every symbol
   that opens or continues a position in the batch window, compute
   the set of expected funding intervals given the symbol's funding
   cadence (e.g. 8h on Binance perps for the standard symbols used in
   this repo).

2. **Per-symbol source funding CSV coverage.** For each required
   symbol, check that the corresponding funding CSV under the
   configured data root exists, is non-empty, and contains a row
   whose timestamp falls within each required funding interval.

3. **Decision.** A batch is **fail-closed** if any required symbol
   is missing source coverage for any required funding interval. In
   that case, the batch must either:
   - **abort before any ledger write**, or
   - **mark the batch as non-evidentiary** and refuse to feed it
     into any clean net-of-carry comparator.

   Silent substitution of zero for required funding is **not**
   permitted under this gate.

4. **Evidence to record.** The pre-batch coverage decision must be
   persisted alongside the batch as part of the batch provenance
   receipt (path, contents, and format defined in §5), so that
   downstream consumers can tell at a glance whether a given batch
   is clean net-of-carry or only engine-semantically consistent.

---

## 4. Verifier v2 reporting (gate output)

The verifier that runs against a paper batch must report, at minimum:

- total funding rows for the batch;
- number of funding rows with `rate_available=0`;
- number of expected funding intervals that are missing from the
  source CSV per symbol, with the missing intervals listed;
- per-symbol coverage completeness flag
  (`complete` / `partial` / `missing` / `not_required`);
- overall batch classification, one of:
  - `CLEAN_NET_OF_CARRY` — required funding is fully covered and
    arithmetic is consistent;
  - `CAVEATED_ENGINE_SEMANTICS` — arithmetic is consistent but
    required funding is not fully covered (label:
    `missing_funding_treated_as_zero_like_current_engine_not_net_of_carry_clean`);
  - `CAVEATED_EX_FUNDING` — funding excluded from the PnL
    aggregation (label:
    `funding_excluded_not_net_of_carry_comparable`);
  - `FAIL` — arithmetic is not consistent, or a hard pre-batch gate
    was bypassed.

`CLEAN_NET_OF_CARRY` must not be reachable on a batch that has any
missing required funding interval.

---

## 5. Provenance and receipt format

A new provenance field is required on every batch receipt:

- `funding_coverage_decision`: one of `complete`, `partial`,
  `missing`, `not_required`.
- `funding_coverage_report_path`: filesystem path to the per-batch
  funding coverage report (CSV or JSON; exact format is decided in
  the implementation PR, not in this docs commit).
- `funding_coverage_diagnostic_label`: one of the two caveated
  labels in §4, or empty if the batch is `CLEAN_NET_OF_CARRY`.

Old `paper_pnl_v1` evidence will **not** be retroactively tagged. A
separate receipt, if added later, will apply the caveat label only at
the receipt layer, not in the DB.

---

## 6. Test plan (must be added with the implementation PR)

The implementation PR must include, at minimum, the following test
fixtures and tests. None of these are added in this docs commit.

Fixtures:

- `missing_sol_funding` — a batch window where SOL funding CSV is
  empty for the entire window.
- `complete_funding` — a batch window where every required symbol
  has full funding CSV coverage at the symbol's expected cadence.
- `partial_per_symbol_gap` — a batch window where BTC funding is
  complete and SOL funding has a single missing interval.

Tests:

- **Missing SOL funding**: the gate fails closed. The batch is
  either aborted or marked non-evidentiary. Verifier reports
  `CAVEATED_ENGINE_SEMANTICS` with the missing SOL intervals listed.
  `CLEAN_NET_OF_CARRY` is unreachable for this batch.
- **Complete funding**: the gate passes. The verifier reports
  `CLEAN_NET_OF_CARRY`.
- **Partial per-symbol gap**: the gate fails closed for SOL only.
  The verifier reports per-symbol coverage (`complete` for BTC,
  `partial` for SOL) and an overall `CAVEATED_ENGINE_SEMANTICS`
  classification.
- **Verifier catches missing coverage**: an explicit test that a
  batch whose funding CSV is missing for a required symbol is
  classified as `CAVEATED_ENGINE_SEMANTICS` (or aborted), and is
  refused classification as `CLEAN_NET_OF_CARRY`.
- **Existing arithmetic consistency still works**: a regression
  test confirming that the gate does not change the engine's
  existing arithmetic consistency behavior for `rate_available=0`
  rows; it only adds a coverage check on top.

The implementation PR must not delete or weaken any existing
arithmetic-consistency test.

---

## 7. Sequencing and lane dependencies

- **Lane B cannot start** until this gate exists in code, is covered
  by the §6 test plan, and has been observed to pass on a non-empty
  batch.
- **Clean net-of-carry comparator** (V2 vs baseline under
  `CLEAN_NET_OF_CARRY`) cannot run until either:
  - the funding source is repaired and a future paper batch produces
    a `CLEAN_NET_OF_CARRY` classification, or
  - a documented re-run with full source funding coverage produces
    a `CLEAN_NET_OF_CARRY` classification.
- **Engine-semantics comparator** may be run only under the explicit
  diagnostic label
  `missing_funding_treated_as_zero_like_current_engine_not_net_of_carry_clean`.
- **Ex-funding diagnostic** may be run only under the explicit
  diagnostic label
  `funding_excluded_not_net_of_carry_comparable`.

---

## 8. Out of scope for this plan

- Implementation of the gate itself (separate PR; not in this docs
  commit).
- Any code change to `engine.py`, `funding_loader.py`,
  `fetch_funding_rest.py`, `sqlite_verify.py`, or
  `sqlite_writer.py` (the implementation PR will propose those
  changes; this docs commit only specifies the requirements).
- Strategy parameter changes.
- Lane B implementation.
- Any live-trading, exchange-key, or real-order surface.

---

## 9. Status

- Plan: **drafted, not implemented**.
- Companion receipt: **drafted**, see
  [`QNTY_FUNDING_COVERAGE_GAP_RECEIPT_2026-06-18.md`](../experiments/QNTY_FUNDING_COVERAGE_GAP_RECEIPT_2026-06-18.md).
- Lane B: **blocked** until the gate is implemented, tested, and
  observed to pass.
