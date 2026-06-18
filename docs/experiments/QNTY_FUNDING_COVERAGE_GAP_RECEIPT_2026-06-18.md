# QNTY Funding Coverage Gap — Receipt

**Date:** 2026-06-18
**Lane:** `paper_pnl_v1` (baseline/control evidence only)
**Author:** QNTY orchestrator (continuation from VM funding-gap forensic)
**Status:** Receipt — docs-only, no implementation in this commit
**Companion plan:** [`FUNDING_COVERAGE_FAIL_CLOSED_GATE_PLAN.md`](../plans/FUNDING_COVERAGE_FAIL_CLOSED_GATE_PLAN.md)

---

## 1. Purpose

This receipt records what the VM funding-gap forensic actually proved
and what it did **not** prove, so that downstream claims about
`paper_pnl_v1`, V2 volnorm edge, and Lane B eligibility stay
proportionate to evidence.

This is a docs-only artifact. No code, no DB, no service, no data
refresh, and no write to `/srv/qnty/output/paper_pnl_v1` was performed
to produce this receipt.

---

## 2. Facts established by the VM forensic

The VM forensic (script: `.claude/qnty_funding_gap_forensic_vm_v0.sh`)
confirmed the following against the live VM state at the time of the
forensic:

- `paper_ledger.db` `sha256` is **unchanged** from the value recorded
  in the prior baseline/control receipt. The existing baseline ledger
  was not corrupted by the forensic, by any comparison step, or by
  any later inspection.
- No production file under `/srv/qnty/...` had its content changed by
  the forensic or by anything that followed it.
- The SOLUSDT upstream funding CSV (the comparator-input source for
  SOL funding coverage) contained **0 rows** in the comparator window.
- The SOLUSDT funding entries inside `paper_ledger.db` were **11/11**
  with `rate_available=0` for the comparator window.
- The paper engine treats missing funding as a `0.0` funding amount
  with `rate_available=False`
  ([`quantbot/paper/engine.py:107-134`](../../quantbot/paper/engine.py:107-134)).
- The funding loader silently skips symbols whose CSV is missing or
  empty
  ([`quantbot/data/funding_loader.py:37-58`](../../quantbot/data/funding_loader.py:37-58)).
- The upstream funding fetch has no completeness gate: an empty or
  missing CSV is not treated as a hard error
  ([`scripts/fetch_funding_rest.py:138-156`](../../scripts/fetch_funding_rest.py:138-156)).
- The SQLite verifier accepts `rate_available=0, funding_amount=0.0`
  rows unconditionally as long as arithmetic consistency holds
  ([`quantbot/paper/sqlite_verify.py:505-520`](../../quantbot/paper/sqlite_verify.py:505-520)).

---

## 3. What this does and does not mean

### 3.1 What it means

- The existing `paper_pnl_v1` ledger is **internally consistent**
  under current engine semantics: the rows it contains are
  arithmetically self-consistent and pass the existing verifier.
- A "verifier OK" outcome on `paper_pnl_v1` therefore certifies
  **internal consistency only**, not funding source coverage and not
  net-of-carry cleanliness.
- The `paper_ledger.db` artifact is suitable for use as a
  baseline/control reference for the engine-semantics comparator,
  with the explicit caveats in §4, but it is **not** clean
  net-of-carry evidence.

### 3.2 What it does not mean

- It does **not** mean the V2 volnorm edge is confirmed. The V2 edge
  remains `EDGE_UNPROVEN`.
- It does **not** mean the existing `paper_pnl_v1` result
  (`~ -1.56%`) is clean of funding carry. SOL funding was missing
  from the comparator window, and the engine silently treated that
  gap as zero.
- It does **not** mean the funding source is complete. The forensic
  demonstrates the opposite: at least one symbol (SOL) had zero
  source rows in the comparator window.
- It does **not** mean Lane B is unblocked. Lane B remains blocked
  until a fail-closed funding coverage gate exists and passes.

---

## 4. Categorization of `paper_pnl_v1`

- `paper_pnl_v1` is **baseline/control evidence only** under the
  existing fixed-notional semantics.
- `paper_pnl_v1` is **not** clean net-of-carry evidence.
- `paper_pnl_v1` does **not** validate or invalidate V2 volnorm.
- `paper_pnl_v1` may be used, with explicit caveats, as:
  - the engine-semantics comparator input, under the diagnostic label
    `missing_funding_treated_as_zero_like_current_engine_not_net_of_carry_clean`,
    and
  - the ex-funding comparator input, under the diagnostic label
    `funding_excluded_not_net_of_carry_comparable`.
- `paper_pnl_v1` must **not** be presented as a clean net-of-carry
  comparator input until funding coverage is repaired or complete.

---

## 5. Downstream consequences

- V2 edge classification: `EDGE_UNPROVEN` (unchanged).
- Lane B: **blocked** until the fail-closed funding coverage gate
  exists and passes (see companion plan).
- Clean net-of-carry comparator: **not eligible to run** until
  funding coverage is repaired or complete.
- No live trading path is implied, planned, or enabled by this
  receipt.

---

## 6. No-mutation attestation

This receipt was produced without:

- editing `paper_ledger.db` or any other production DB;
- writing into `/srv/qnty/output/paper_pnl_v1` (or any subpath);
- starting, stopping, or otherwise touching production services or
  systemd timers;
- manually running `qnty-paper-pnl.service`;
- refreshing upstream data;
- implementing Lane B;
- implementing the funding coverage gate itself;
- modifying strategy parameters;
- adding live trading, exchange keys, or real orders.

---

## 7. Required follow-on (docs only, no code yet)

- Companion plan:
  [`FUNDING_COVERAGE_FAIL_CLOSED_GATE_PLAN.md`](../plans/FUNDING_COVERAGE_FAIL_CLOSED_GATE_PLAN.md).
- No DB edits will be made to old `paper_pnl_v1` evidence. Any later
  decision to add a caveat marker to old rows will be a separate
  receipt, not a retroactive DB mutation.

---

## 8. Status

- VM forensic: **complete and confirmed**.
- Baseline ledger: **not corrupted**.
- Existing paper PnL: **internally consistent only**, not clean
  net-of-carry.
- V2 edge: `EDGE_UNPROVEN`.
- Lane B: **blocked**.
- Live trading: **no**.
