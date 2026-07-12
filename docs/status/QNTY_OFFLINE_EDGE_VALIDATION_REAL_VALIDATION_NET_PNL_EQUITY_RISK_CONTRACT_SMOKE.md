# QNTY_OFFLINE_EDGE_VALIDATION_REAL_VALIDATION_NET_PNL_EQUITY_RISK_CONTRACT_SMOKE

## Status

Status: BLOCKED_BY_VALIDATION_IMPLEMENTATION
Run ID: QNTY_OFFLINE_EDGE_VALIDATION_REAL_VALIDATION_NET_PNL_EQUITY_RISK_CONTRACT_SMOKE_RECORDED_BLOCKED
Commit under test: 65c29017f354fb362fca3503ba3117d0d944a8b9
Receipt SHA-256: 4e1c5e25d26f47fee0e741dd28f7aba45080c56359b769fb91e63bbcef075618

## Execution Facts

- real-data smoke passed
- canonical runner used: quantbot.experiment.offline_edge_real_validation
- fixture CLI was not used
- scratch checkout was created under /tmp/qnty_scratch_pr202_net_pnl_equity_risk_smoke_20260712_214046
- scratch HEAD matched 65c29017f354fb362fca3503ba3117d0d944a8b9
- quantbot.__file__ resolved inside scratch checkout
- 20 CSVs confirmed:
  - 10 bars
  - 10 funding
- bars and funding were staged through /tmp symlink dirs preserving filenames
- bars symlink dir: /tmp/qnty_bars_symlink_20260712_214351
- funding symlink dir: /tmp/qnty_funding_symlink_20260712_214351
- all 20 source CSV SHA-256 hashes captured before execution
- all 20 source CSV SHA-256 hashes matched after execution
- input_manifest_fingerprint = 80916c4cd2cdd79a8ba5f37c1c23797b57561ef9a7e9307b35beb6f2dffd6183
- data_quality_receipt_sha256 = f55adddbbaa0e07c70f5ef4a443a1b5f1a3fec637b93fe005bae26b903718177
- CLI exited 0
- stderr empty
- stdout included:
  - final_offline_verdict=BLOCKED_BY_VALIDATION_IMPLEMENTATION
  - receipt_sha256=4e1c5e25d26f47fee0e741dd28f7aba45080c56359b769fb91e63bbcef075618
  - receipt_path=/tmp/qnty_output_20260712_214351/real_validation_receipt.json
- independent SHA-256 matched stdout receipt hash
- receipt was written only under /tmp
- generated receipt was not committed
- scratch checkout removed
- symlink dirs removed
- all /tmp artifacts removed after verification
- source repo clean except pre-existing untracked plans/
- scratch worktree clean before removal
- output dir contained only real_validation_receipt.json
- no repo files edited during smoke
- no commit or PR created during smoke

## Receipt Facts

- code_commit_sha = 65c29017f354fb362fca3503ba3117d0d944a8b9
- input_manifest_fingerprint = 80916c4cd2cdd79a8ba5f37c1c23797b57561ef9a7e9307b35beb6f2dffd6183
- data_quality_receipt_sha256 = f55adddbbaa0e07c70f5ef4a443a1b5f1a3fec637b93fe005bae26b903718177
- final_offline_verdict = BLOCKED_BY_VALIDATION_IMPLEMENTATION
- net_pnl_equity_risk_contract_diagnostics present
- strategy_rule_contract_diagnostics still present
- trial_manifest_diagnostics still present
- oos_seal_diagnostics still present
- null_benchmark_contract_diagnostics still present
- multiple_testing_control_diagnostics still present
- trade_position_simulation_contract_diagnostics still present
- split_leakage_audit_diagnostics still present

## Net PnL Equity Risk Contract Summary

| Field | Value |
|-------|-------|
| contract_version | net-pnl-equity-risk-contract-0.1 |
| calculation_status | NET_PNL_EQUITY_RISK_CONTRACT_DIAGNOSTIC_ONLY |
| net_pnl_equity_risk_contract_status | NET_PNL_EQUITY_RISK_CONTRACT_NOT_DEFINED |
| net_pnl_equity_risk_contract_present | false |
| net_pnl_equity_risk_contract_hash | null |
| net_pnl_equity_risk_contract_source | null |
| scoring_authorized | false |
| scoring_blocked_reason | NET_PNL_EQUITY_RISK_CONTRACT_NOT_DEFINED |
| capital_base_policy_defined | false |
| capital_base_policy | NOT_DEFINED |
| net_accounting_policy_defined | false |
| net_accounting_policy | NOT_DEFINED |
| realized_unrealized_policy_defined | false |
| realized_unrealized_policy | NOT_DEFINED |
| cost_inclusion_dependency_satisfied | false |
| funding_inclusion_dependency_satisfied | false |
| simulator_dependency_satisfied | false |
| mark_to_market_policy_defined | false |
| mark_to_market_policy | NOT_DEFINED |
| equity_curve_policy_defined | false |
| equity_curve_policy | NOT_DEFINED |
| aggregation_policy_defined | false |
| aggregation_policy | NOT_DEFINED |
| drawdown_policy_defined | false |
| drawdown_policy | NOT_DEFINED |
| exposure_policy_defined | false |
| exposure_policy | NOT_DEFINED |
| risk_measure_policy_defined | false |
| risk_measure_policy | NOT_DEFINED |
| benchmark_comparison_dependency_satisfied | false |
| final_verdict_scoring_dependency_satisfied | false |
| strategy_rule_contract_dependency_satisfied | false |
| trial_manifest_dependency_satisfied | false |
| oos_seal_dependency_satisfied | false |
| null_benchmark_contract_dependency_satisfied | false |
| multiple_testing_control_dependency_satisfied | false |
| trade_position_simulation_contract_dependency_satisfied | false |
| split_scoring_safe_dependency_satisfied | false |

## Prerequisites

| Prerequisite | Satisfied |
|--------------|-----------|
| strategy_rule_contract | false |
| trial_manifest | false |
| oos_seal | false |
| null_benchmark_contract | false |
| multiple_testing_control | false |
| trade_position_simulation_contract | false |
| split_scoring_safe | false |
| capital_base_policy | false |
| net_accounting_policy | false |
| realized_unrealized_policy | false |
| cost_inclusion_policy | false |
| funding_inclusion_policy | false |
| mark_to_market_policy | false |
| equity_curve_policy | false |
| aggregation_policy | false |
| drawdown_policy | false |
| exposure_policy | false |
| risk_measure_policy | false |
| benchmark_comparison_policy | false |
| final_verdict_scoring_policy | false |

## Guardrail Checks

- final_offline_verdict = BLOCKED_BY_VALIDATION_IMPLEMENTATION
- all required_outputs_present values false
- all forbidden_calculation_status values false
- all guardrail_status values true
- strategy_rule_contract_diagnostics.contract_status = CONTRACT_NOT_DEFINED
- trial_manifest_diagnostics.trial_manifest_status = TRIAL_MANIFEST_NOT_DEFINED
- oos_seal_diagnostics.oos_seal_status = OOS_SEAL_NOT_DEFINED
- null_benchmark_contract_diagnostics.null_benchmark_contract_status = NULL_BENCHMARK_CONTRACT_NOT_DEFINED
- multiple_testing_control_diagnostics.multiple_testing_control_status = MULTIPLE_TESTING_CONTROL_NOT_DEFINED
- trade_position_simulation_contract_diagnostics.trade_position_simulation_contract_status = TRADE_POSITION_SIMULATION_CONTRACT_NOT_DEFINED
- split_leakage_audit_diagnostics.split_scoring_safe = false
- forbidden exact-key recursive scan passed with zero violations
- no pnl
- no returns
- no return
- no sharpe
- no drawdown
- no risk
- no edge
- no strategy_performance
- no trade/trades
- no signal/signals
- no position/positions
- no portfolio
- no baseline_result
- no benchmark_result
- no profitable
- no live_ready
- no deploy_ready
- no OFFLINE_EDGE_CANDIDATE
- no EDGE_CANDIDATE
- no funding_adjusted_return
- no net_return_value
- no price_change
- no p_value
- no confidence_interval
- no score
- no metric
- no performance
- no profit
- no order/orders
- no fill/fills
- no execution/executions
- no cost_adjusted_return
- no gross_return_value
- no equity
- no equity_curve
- no pbo.py usage
- no strategy/runner/walkforward module usage
- no paper/exchange/execution/live code usage
- no accounting implementation activity
- no capital base formula/value
- no mark-to-market formula
- no equity curve computation
- no drawdown computation
- no risk-measure computation
- no benchmark comparison computation
- no final scoring rule computation
- no signal/trade/position/order/fill/execution activity
- no return/PnL/Sharpe/drawdown/risk/edge/portfolio computation
- no DB / paper-engine / live integration / exchange keys / report promotion / data refresh / service / timer / systemd activity
- no source CSV mutation
- no repository output/ or tracked tmp/ writes
- output dir contained only real_validation_receipt.json

## Interpretation

This smoke proves only that net_pnl_equity_risk_contract_diagnostics is emitted during the real-data CLI path and records that no net PnL/equity/risk contract is defined, no accounting/risk policies exist, no benchmark/final-scoring dependencies are satisfied, and scoring remains unauthorized.

This smoke does NOT prove:

- returns validity
- PnL validity
- equity-curve validity
- drawdown validity
- risk validity
- Sharpe validity
- volatility validity
- exposure validity
- benchmark comparison correctness
- OOS safety
- strategy validity
- signal validity
- trade validity
- position validity
- order validity
- fill validity
- execution validity
- edge
- live readiness

## Closing

EDGE_UNPROVEN remains.
BLOCK_LIVE_INTEGRATION remains.
final_offline_verdict remains BLOCKED_BY_VALIDATION_IMPLEMENTATION.
net_pnl_equity_risk_contract_diagnostics records NET_PNL_EQUITY_RISK_CONTRACT_NOT_DEFINED.
net_pnl_equity_risk_contract_present remains false.
capital_base_policy_defined remains false.
net_accounting_policy_defined remains false.
realized_unrealized_policy_defined remains false.
cost_inclusion_dependency_satisfied remains false.
funding_inclusion_dependency_satisfied remains false.
simulator_dependency_satisfied remains false.
mark_to_market_policy_defined remains false.
equity_curve_policy_defined remains false.
aggregation_policy_defined remains false.
drawdown_policy_defined remains false.
exposure_policy_defined remains false.
risk_measure_policy_defined remains false.
benchmark_comparison_dependency_satisfied remains false.
final_verdict_scoring_dependency_satisfied remains false.
scoring_authorized remains false.
No returns, PnL, equity curve, drawdown, risk, benchmark comparison, edge, final scoring, or live readiness is authorized by this smoke.
