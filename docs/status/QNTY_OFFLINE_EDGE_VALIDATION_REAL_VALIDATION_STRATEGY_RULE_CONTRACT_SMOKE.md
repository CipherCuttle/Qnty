# QNTY_OFFLINE_EDGE_VALIDATION_REAL_VALIDATION_STRATEGY_RULE_CONTRACT_SMOKE

## Status

```
Status: BLOCKED_BY_VALIDATION_IMPLEMENTATION
Run ID: QNTY_OFFLINE_EDGE_VALIDATION_REAL_VALIDATION_STRATEGY_RULE_CONTRACT_SMOKE_RECORDED_BLOCKED
Commit under test: 1a6bf23c8d291e50fe79dddab473828b51a59483
Receipt SHA-256: 1bcb85fd276bb13fffe249c97920b246ddf972481a33d17753bb5269697e0097
```

## Execution Facts

- real-data smoke passed
- canonical runner used: `quantbot.experiment.offline_edge_real_validation`
- fixture CLI was not used
- scratch checkout was created under `/tmp`
- scratch HEAD matched `1a6bf23c8d291e50fe79dddab473828b51a59483`
- `quantbot.__file__` resolved inside scratch checkout
- 20 CSVs confirmed: 10 bars, 10 funding
- bars and funding were staged through `/tmp` symlink dirs preserving filenames
- all 20 source CSV SHA-256 hashes captured before execution
- all 20 source CSV SHA-256 hashes matched after execution
- CLI exited `0`
- stdout included:
  - `final_offline_verdict=BLOCKED_BY_VALIDATION_IMPLEMENTATION`
  - `receipt_sha256=1bcb85fd276bb13fffe249c97920b246ddf972481a33d17753bb5269697e0097`
  - `receipt_path=<absolute /tmp path>`
- independent SHA-256 matched stdout receipt hash
- receipt was written only under `/tmp`
- generated receipt was not committed
- scratch checkout removed
- symlink dirs removed
- source repo clean except pre-existing untracked `plans/`
- scratch worktree clean before removal
- no repo files edited during smoke
- no commit or PR created during smoke

## Receipt Facts

- `code_commit_sha = 1a6bf23c8d291e50fe79dddab473828b51a59483`
- `final_offline_verdict = BLOCKED_BY_VALIDATION_IMPLEMENTATION`
- `strategy_rule_contract_diagnostics` present
- `split_leakage_audit_diagnostics` still present

## Strategy Rule Contract Summary

| Field | Value |
|-------|-------|
| `contract_version` | `strategy-rule-contract-0.1` |
| `calculation_status` | `STRATEGY_RULE_CONTRACT_DIAGNOSTIC_ONLY` |
| `contract_status` | `CONTRACT_NOT_DEFINED` |
| `scoring_authorized` | `false` |
| `scoring_blocked_reason` | `STRATEGY_RULE_CONTRACT_NOT_DEFINED` |
| `allowed_input_roles` | `null` |
| `allowed_input_columns` | `null` |
| `forbidden_input_roles` | `null` |
| `forbidden_input_columns` | `null` |
| `forbidden_future_columns` | `null` |
| `decision_time_convention` | `null` |
| `decision_time_column` | `null` |
| `decision_time_offset` | `null` |
| `feature_lookback` | `null` |
| `feature_lookback_bars` | `null` |
| `label_horizon` | `null` |
| `label_horizon_bars` | `null` |
| `holding_period` | `null` |
| `holding_period_bars` | `null` |
| `side_semantics` | `null` |
| `side_source` | `null` |
| `notional_semantics` | `null` |
| `notional_source` | `null` |
| `notional_currency` | `null` |
| `cost_dependency` | `NOT_DEFINED` |
| `funding_dependency` | `NOT_DEFINED` |

## Scoring Prerequisites

`scoring_prerequisites_present: all 6 false`

| Field | Value |
|-------|-------|
| `decision_time_convention` | `false` |
| `feature_lookback` | `false` |
| `label_horizon` | `false` |
| `holding_period` | `false` |
| `funding_interval_exposure` | `false` |
| `cost_event_timing` | `false` |

## Guardrail Checks

- `final_offline_verdict = BLOCKED_BY_VALIDATION_IMPLEMENTATION`
- all `required_outputs_present` values false
- all `forbidden_calculation_status` values false
- all `guardrail_status` values true
- `split_leakage_audit_diagnostics` still present
- `split_scoring_safe = false`
- no `OFFLINE_EDGE_CANDIDATE`
- no `EDGE_CANDIDATE`
- no strategy definition
- no signals
- no returns/PnL/risk/edge keys
- no trades/positions/portfolio keys
- no baseline or benchmark result
- no `funding_adjusted_return`
- no `net_return_value`
- no `price_change`
- no `live_ready`
- no `deploy_ready`
- no `pbo.py` usage
- no strategy/runner/walkforward module usage
- no DB / paper-engine / live integration / exchange keys / report promotion / data refresh / service / timer / systemd activity
- no source CSV mutation
- no repository `output/` or tracked `tmp/` writes

## Interpretation

```
This smoke proves only that strategy_rule_contract_diagnostics is emitted during the real-data CLI path and that the current strategy rule contract is recorded as not defined, diagnostic-only, and insufficient for scoring.
```

**This smoke does NOT prove:**
- strategy validity
- signal validity
- decision-time safety
- feature lookback safety
- label-horizon safety
- holding-period safety
- side/notional semantics
- OOS safety
- trial manifest
- OOS seal
- symbol universe freeze
- returns
- PnL
- risk
- edge
- live readiness

## Closing

```
EDGE_UNPROVEN remains.
BLOCK_LIVE_INTEGRATION remains.
final_offline_verdict remains BLOCKED_BY_VALIDATION_IMPLEMENTATION.
strategy_rule_contract_diagnostics records CONTRACT_NOT_DEFINED.
scoring_authorized remains false.
No strategy work is authorized by this smoke.