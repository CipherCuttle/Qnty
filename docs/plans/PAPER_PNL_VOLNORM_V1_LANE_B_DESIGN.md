# Paper PnL Volnorm v1 Lane B Design

**Status:** design only, not implemented
**Evidence label:** `EDGE_UNPROVEN`
**Status line:** `INFRA OK / BASELINE CONTROL RUNNING / V2 EDGE UNTESTED FORWARD / LANE B PLANNED / NO LIVE`

## PLAN

Lane B is a future additive paper lane intended to test the validated Package V2 portfolio construction forward. It must not replace, reset, mutate, or reinterpret the existing `paper_pnl_v1` baseline.

Required identity:

- Lane name: `paper_pnl_volnorm_v1`
- Output dir: `/srv/qnty/output/paper_pnl_volnorm_v1`
- SQLite DB: `/srv/qnty/output/paper_pnl_volnorm_v1/paper_ledger.db`
- Baseline/control output dir that must remain untouched: `/srv/qnty/output/paper_pnl_v1`
- Evidence label in every config, receipt, verifier report, and summary: `EDGE_UNPROVEN`

Production enablement is explicitly out of scope until separately approved. No live trading, exchange keys, real orders, strategy parameter changes, or existing timer changes are part of this design.

## CHANGESET

Future implementation must be additive:

- Add a separate config and label for `paper_pnl_volnorm_v1`; do not overload `fixed_notional_active_symbols_paper_v1`.
- Add separate wrapper/env vars, for example `QNTY_VOLNORM_PAPER_OUTPUT_DIR` and `QNTY_VOLNORM_PAPER_DB_PATH`, so Lane B cannot accidentally write into `paper_pnl_v1`.
- Use a fresh `forward_start_ts`; Lane B starts from zero evidence.
- Use a separate SQLite DB with its own schema identity and verifier artifacts.
- Require non-null `git_sha` before the first committed Lane B batch. A first Lane B batch with `git_sha=None` is a hard stop.
- Add verifier and health checks from day one. The verifier must be read-only/query-only against the DB and must publish Lane B specific status artifacts in the Lane B output dir.

Required accounting stance:

- Preserve the 8h bar grid.
- Preserve no-live/no-keys/no-orders constraints.
- Match or explicitly document fill, fee, slippage, and funding semantics.
- Do not claim byte-identical validation PnL unless the execution and accounting semantics actually match.

## Target-Weight Interface

Blocking question 1: where do per-symbol V2 target weights come from?

They must come from a new additive observer artifact emitted at decision time, immediately after the V2 observer computes `compute_vol_normed_weights(...)`. The artifact must persist per-bar, per-symbol target weights, not only aggregate returns.

Blocking question 2: are those weights known at decision time, or reconstructed later?

Lane B may only use weights known at the decision bar from closed data. Post-hoc reconstruction is allowed only for read-only audit/comparator work, not as the source of committed forward Lane B fills.

Blocking question 3: does the current observer output persist enough information?

No. Current `observation_log.json` persists `active_symbols`, `portfolio_heat`, `heat_cap_triggered`, and aggregate `weighted_return`. It does not persist per-symbol target weights or enough volatility/sizing provenance to audit weights.

Blocking question 4: what additive artifact/interface is required?

Add a new observer output, separate from the existing baseline contract, with at least:

- `timestamp`
- `active_symbols`
- `target_weights` as `{symbol: weight}`
- `portfolio_heat`
- `heat_cap_triggered`
- `vol_lookback_bars`
- `heat_cap`
- `vol_floor`
- `vol_by_symbol` or an auditable digest/source for the weight inputs
- `weight_source_git_sha`
- source-observation digest

If the validation path updates volatility trackers with the current bar before computing weights, Lane B must document that exact decision-time semantic. Revising it requires explicit approval because it can alter the tested V2 package.

## Semantic Matching

Validation semantics currently differ from paper accounting semantics:

- Validation computes weighted log returns using aggregate `weighted_return`.
- Validation funding treatment uses an absolute funding penalty in the observer/validation path.
- Paper accounting fills at T+1 next open, computes explicit quantities, charges fees and slippage, and applies signed funding cash flows.

Lane B must choose one of two explicit modes before implementation:

- **Execution-faithful Lane B:** use V2 target weights as desired exposure, then apply paper T+1 fills, 5 bps fees, 5 bps slippage, and signed funding cash flows. This is preferred for forward paper evidence, but it will not be byte-identical to validation weighted log returns.
- **Validation-semantics replay:** replay weighted log returns exactly for diagnostic comparison only. This cannot be marketed as paper fills or execution-like PnL.

The first production-eligible Lane B should be execution-faithful unless a later approved design says otherwise.

## Universe Freeze

Lane B must freeze its universe in the Lane B config at first start.

Allowed universe choices:

- Use the current `2025-10-01` table entry and label it explicitly as a stale/frozen 2025-Q4 universe.
- Extend the point-in-time universe table into 2026 before Lane B starts, with documented source/provenance, then freeze that 2026 universe in the Lane B config.

Neither option may silently mutate old baseline evidence. Existing `paper_pnl_v1` remains as-run.

## Forward Null Comparators

Forward null comparators must be implemented read-only first and write only to `/tmp` or a separate scratch directory.

Required nulls:

- Always-flat: initial equity only; no fills, no fees, no funding.
- Always-long comparator: frozen Lane B universe, same bar window, matched fill timing, fee, slippage, and funding assumptions.

The comparator report must include:

- strategy return
- always-flat excess
- always-long excess
- drawdown
- fees
- funding
- bar count
- universe used
- output location

Comparator output must not mutate either `/srv/qnty/output/paper_pnl_v1` or `/srv/qnty/output/paper_pnl_volnorm_v1`.

## Hard Stops

Stop implementation immediately on any of these:

- Any design requiring editing or resetting `/srv/qnty/output/paper_pnl_v1`.
- Any design requiring edits to `/srv/qnty/output/paper_pnl_v1/paper_ledger.db`.
- Any replay, lab, scratch, or comparator output targeting `paper_pnl_v1`.
- Any live keys, real orders, or exchange mutation.
- Any strategy parameter tweak.
- Any stop/start of existing timers without separate approval.
- Any unclear per-symbol target-weight provenance.
- Any first Lane B batch with `git_sha=None`.
- Any wrapper/env-var setup where Lane B can accidentally resolve to `/srv/qnty/output/paper_pnl_v1`.

## VERIFY

Before Lane B implementation can start:

- Confirm the target-weight artifact exists and contains per-symbol weights.
- Confirm all Lane B default paths point to `/srv/qnty/output/paper_pnl_volnorm_v1`.
- Confirm every production-like command has separate Lane B env vars.
- Confirm verifier can run `--no-emit` read-only against a scratch DB.
- Confirm `git_sha` is non-null in scratch committed batches.
- Confirm docs and reports carry `EDGE_UNPROVEN`.

This design authorizes documentation and scratch planning only. It does not authorize production enablement.

## VERDICT

`VERDICT: LANE B PLANNED ONLY / EDGE_UNPROVEN / NO LIVE`
