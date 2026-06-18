# QNTY P0 Baseline-Control Decision Receipt

**Prepared:** 2026-06-18
**Pinned commit:** `5821b67dea1f5483f8188a9e3c11169efcfb6f5c`
**Evidence label:** `EDGE_UNPROVEN`
**Status line:** `INFRA OK / BASELINE CONTROL RUNNING / V2 EDGE UNTESTED FORWARD / LANE B PLANNED / NO LIVE`

## PLAN

This is a docs-only decision receipt. It reclassifies the existing forward paper lane without changing code, timers, services, strategy parameters, or production output.

The current `paper_pnl_v1` lane is valid forward ledger evidence for the `fixed_notional_active_symbols_paper_v1` baseline/control only. It is not forward evidence for the validated Package V2 vol-normalized, inverse-vol weighted, heat-capped portfolio.

No live trading is authorized. No exchange keys, real orders, deploys, timer changes, DB resets, or writes to `/srv/qnty/output/paper_pnl_v1` are authorized by this receipt.

## CHANGESET

Decision:

- Reclassify `paper_pnl_v1` as fixed-notional baseline/control evidence only.
- Preserve the existing running baseline as-is. The existing timer remains untouched.
- Treat the current fixed-notional PnL as real ledger evidence, but statistically tiny and not diagnostic of strategy edge.
- Keep the V2 forward edge classification at `EDGE_UNPROVEN`.
- Plan a future additive Lane B, tentatively `paper_pnl_volnorm_v1`, but do not implement or enable it here.

Current evidence read:

- Infrastructure and accounting integrity recovered: the production SQLite verifier report is `OK` with `failure_count=0` per the strategy-validity evidence pack.
- The baseline sample remains tiny: 14 forward equity bars, 13 batches, and 5 closed trades at the time of the evidence pack.
- The baseline result is negative, but this is not a verdict on V2 volnorm edge because the running paper lane does not apply V2 target weights or heat-cap sizing.

## VERIFY

Evidence map:

- `quantbot/paper/__init__.py` defines `BASELINE_LABEL = "fixed_notional_active_symbols_paper_v1"` and states that vol-normalized weights, portfolio heat, and weights are not used for sizing.
- `quantbot/paper/config.py` builds the paper config with the baseline label and comments that it is a fixed-notional active-symbol baseline, not V2 volnorm PnL.
- `quantbot/paper/engine.py` consumes `active_symbols`, computes entries/exits from desired-vs-current sets, and sizes entries as `qty = notional / fill_price`.
- `docs/paper_pnl_v1_schema.md` section 8 states the adapter contract: `paper_pnl_v1` is not V2 volnorm paper PnL, and a green paper result does not validate the V2 vol-normalized edge.
- `docs/ADR/0001-paper-sqlite-ledger.md` preserves the fixed-notional baseline contract under the SQLite migration and explicitly disclaims Package V2 volnorm proof.
- `docs/experiments/QNTY_STRATEGY_VALIDITY_EVIDENCE_PACK_2026-06-18.md` records the lane mismatch, the verifier-OK forward decomposition, and the current edge verdict as not enough evidence.

What this receipt does not do:

- It does not change `/srv/qnty/output/paper_pnl_v1`.
- It does not edit or reset `/srv/qnty/output/paper_pnl_v1/paper_ledger.db`.
- It does not run `qnty-paper-pnl.service`.
- It does not start or stop timers.
- It does not write replay, lab, scratch, or comparator output into `paper_pnl_v1`.
- It does not tweak strategy parameters.

## VERDICT

`paper_pnl_v1` remains a real, running, fixed-notional baseline/control lane. It is not a V2 volnorm forward test.

`VERDICT: EDGE_UNPROVEN / BASELINE CONTROL RUNNING / LANE B PLANNED / NO LIVE`
