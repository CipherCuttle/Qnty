# QNTY_OFFLINE_EDGE_VALIDATION_REAL_VALIDATION_FUNDING_APPLICATION_READINESS_GATE_SMOKE

**Status:** `BLOCKED_BY_VALIDATION_IMPLEMENTATION`

**Run ID:** `QNTY_OFFLINE_EDGE_VALIDATION_REAL_VALIDATION_FUNDING_APPLICATION_READINESS_GATE_SMOKE_RECORDED_BLOCKED`

## Dependency

- PR #173
- merge commit `4eb0d0cec04f7dad0f691edbb11d5a941170820c`

## Execution

- scratch: `/tmp/qnty_scratch_pr173_readiness_gate_smoke_20260711T003751Z`
- receipt: `/tmp/qnty_scratch_pr173_readiness_gate_smoke_20260711T003751Z/output/real_validation_receipt.json`
- SHA-256: `c5f39487203ca0c6a405c9aa1f1f4c3341a52258835a6859ce7883ffe260228d`
- exit status: `0`
- stderr empty
- final verdict: `BLOCKED_BY_VALIDATION_IMPLEMENTATION`
- output directory contained exactly one JSON receipt
- 10 bars + 10 funding files staged via `/tmp` symlinks preserving filenames
- all 20 source CSV pre/post hashes matched
- scratch worktree clean and removed after verification
- source repo unchanged except pre-existing untracked `plans/`
- no stale `/srv/qnty/repo`

## Readiness Gate Summary

| Field | Value |
|----------------------|------------------------------------------------------------------|
| calculation status | `FUNDING_APPLICATION_READINESS_GATE_DIAGNOSTIC_ONLY` |
| funding application | `NOT_EXECUTED` |
| readiness policy | `STRICT_CANONICAL_TIMESTAMP_EXACT_MATCH_NO_COLLISION_NO_AMBIGUITY` |
| canonicalization policy | `floor_to_second` |
| symbols | 10 |
| eligible | 8 |
| blocked | 2 |

## Per-Symbol Table

| Symbol | Status | Bars | Canon funding | Matched | Funding extra | Ambiguous | Range |
|--------|--------|-----:|--------------:|--------:|--------------:|----------:|-----------------------|
| ADAUSDT | Eligible | 5271 | 5271 | 5271 | 0 | 0 | Matching |
| AVAXUSDT | Eligible | 5271 | 5271 | 5271 | 0 | 0 | Matching |
| BNBUSDT | Eligible | 5271 | 5271 | 5271 | 0 | 0 | Matching |
| BTCUSDT | Eligible | 5271 | 5271 | 5271 | 0 | 0 | Matching |
| DOTUSDT | Eligible | 5271 | 5271 | 5271 | 0 | 0 | Matching |
| ETHUSDT | Eligible | 5271 | 5271 | 5271 | 0 | 0 | Matching |
| LINKUSDT | Eligible | 5271 | 5271 | 5271 | 0 | 0 | Matching |
| MATICUSDT | Blocked | 3506 | 5271 | 3506 | 1765 | 0 | Bars end before funding |
| SOLUSDT | Blocked | 5271 | 5346 | 5271 | 75 | 26 | Matching |
| XRPUSDT | Eligible | 5271 | 5271 | 5271 | 0 | 0 | Matching |

## Interpretation

The readiness gate classified eight symbols as eligible for a future funding-application step and two symbols as blocked. This is **not** funding application. It does **not** approve funding-adjusted bars, strategy validity, edge, profitability, or live readiness.

### Eligible Symbols

- ADAUSDT
- AVAXUSDT
- BNBUSDT
- BTCUSDT
- DOTUSDT
- ETHUSDT
- LINKUSDT
- XRPUSDT

### Blocked Symbols

- MATICUSDT
- SOLUSDT

#### MATIC Blocked Reasons

- count mismatch
- partial canonical matching
- funding timestamps without bars
- range mismatch
- 1,765 funding timestamps outside bars range
- empty-bars/non-empty-funding terminal window

#### SOL Blocked Reasons

- count mismatch
- partial canonical matching
- 75 extra canonicalized funding timestamps
- 26 ambiguous nearest-bar cases

### Per-Split Summary

- all 40 non-empty partitions for the eight clean symbols were eligible
- all ten `split_00/train` partitions were eligible with `EMPTY_BOTH_NOT_BLOCKING`
- MATIC blockers appeared in:
  - `split_01/validation`
  - `split_02/train`
  - `split_02/validation`
- SOL blockers appeared in:
  - `split_00/validation`
  - `split_01/train`
  - `split_02/train`
- other MATIC/SOL partitions were correctly eligible
- no corpus symbol names were hardcoded in the validation module

## Explicit Statements

- `EDGE_UNPROVEN` remains.
- `BLOCK_LIVE_INTEGRATION` remains.
- funding application remains blocked.
- no funding-adjusted bars were produced.
- no joined row-level dataset was produced.
- no funding-rate math was performed.
- no carry math was performed.
- no price math was performed.
- no return math was performed.
- no strategy, trade, signal, position, PnL, Sharpe, drawdown, risk, portfolio, edge, or live-readiness metric was computed.
- no live readiness is implied.

## Guardrails

- final verdict remained `BLOCKED_BY_VALIDATION_IMPLEMENTATION`
- all `required_outputs_present` values were false
- all `forbidden_calculation_status` values were false
- all `guardrail_status` values were true
- no `funding_adjusted_return`
- no `net_return_value`
- no `price_change`
- no `OFFLINE_EDGE_CANDIDATE`
- no `EDGE_CANDIDATE`
- no DB, paper-engine, live integration, exchange keys, report promotion, data-refresh, service, timer, or systemd activity
- all 20 pre/post source SHA-256 hashes matched
- output directory contained only the JSON receipt
- stale `/srv/qnty/repo` was not used