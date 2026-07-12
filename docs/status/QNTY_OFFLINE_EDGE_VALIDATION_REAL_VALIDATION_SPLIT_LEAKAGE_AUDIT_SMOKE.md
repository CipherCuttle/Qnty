# QNTY_OFFLINE_EDGE_VALIDATION_REAL_VALIDATION_SPLIT_LEAKAGE_AUDIT_SMOKE

## Status

Status: BLOCKED_BY_VALIDATION_IMPLEMENTATION
Run ID: QNTY_OFFLINE_EDGE_VALIDATION_REAL_VALIDATION_SPLIT_LEAKAGE_AUDIT_SMOKE_RECORDED_BLOCKED
Commit under test: 3644c151ce99d074272f92991102c8fec67f8048
Receipt SHA-256: 16968884ec97c67daabb416414d2dafc262b95c4defb7e2a21cdee090a14108c

## Execution Facts

- real-data smoke passed
- canonical runner used: `quantbot.experiment.offline_edge_real_validation`
- fixture CLI was not used
- scratch checkout was created under `/tmp`
- scratch HEAD matched `3644c151ce99d074272f92991102c8fec67f8048`
- `quantbot.__file__` resolved inside scratch checkout
- 20 CSVs confirmed:
  - 10 bars
  - 10 funding
- bars and funding were staged through `/tmp` symlink dirs preserving filenames
- all 20 source CSV SHA-256 hashes captured before execution
- all 20 source CSV SHA-256 hashes matched after execution
- CLI exited `0`
- stdout included:
  - `final_offline_verdict=BLOCKED_BY_VALIDATION_IMPLEMENTATION`
  - `receipt_sha256=16968884ec97c67daabb416414d2dafc262b95c4defb7e2a21cdee090a14108c`
  - `receipt_path=<absolute /tmp path>`
- independent `sha256sum` matched stdout receipt hash
- receipt was written only under `/tmp`
- generated receipt was removed after verification
- scratch checkout removed
- symlink dirs removed
- output dir removed
- source repo clean except pre-existing untracked `plans/`
- scratch worktree clean before removal
- no repo files edited during smoke
- no commit or PR created during smoke

## Receipt Facts

- code_commit_sha = 3644c151ce99d074272f92991102c8fec67f8048
- final_offline_verdict = BLOCKED_BY_VALIDATION_IMPLEMENTATION
- split_leakage_audit_diagnostics present

## Split Leakage Audit Summary

| Field | Value |
|-------|-------|
| audit_version | split-leakage-audit-0.1 |
| calculation_status | SPLIT_LEAKAGE_AUDIT_DIAGNOSTIC_ONLY |
| split_leakage_audit_status | SPLIT_LEAKAGE_AUDIT_INSUFFICIENT_FOR_SCORING |
| split_builder_inspected | materialize_split_definitions_from_inventory |
| split_count | 3 |
| purge_gap_seconds | 0 |
| embargo_gap_seconds | 0 |
| windows_adjacent | true |
| train_validation_overlap_detected | false |
| oos_seal_present | false |
| trial_manifest_present | false |
| symbol_universe_frozen | false |
| split_scoring_safe | false |
| per_symbol | null |

### Scoring Prerequisites Present

All 6 false:

| Prerequisite | Value |
|-------------|-------|
| decision_time_convention | false |
| feature_lookback | false |
| label_horizon | false |
| holding_period | false |
| funding_interval_exposure | false |
| cost_event_timing | false |

### Leakage Risk Register

All 6 true:

| Risk | Value |
|------|-------|
| temporal_purge_leakage | true |
| embargo_leakage | true |
| same_bar_lookahead | true |
| future_bar_leakage | true |
| symbol_universe_leakage | true |
| no_independent_oos_seal | true |

## Per-Split Table

| Split | boundary_gap_seconds | train_validation_overlap | validation_row_count_status | calculation_status |
|-------|---------------------|-------------------------|----------------------------|-------------------|
| split_00 | 0 | false | NOT_COMPUTED_IN_SPLIT_LEAKAGE_AUDIT | NOT_EXECUTED |
| split_01 | 0 | false | NOT_COMPUTED_IN_SPLIT_LEAKAGE_AUDIT | NOT_EXECUTED |
| split_02 | 0 | false | NOT_COMPUTED_IN_SPLIT_LEAKAGE_AUDIT | NOT_EXECUTED |

All 3 per_split entries were present with all required fields.

## Guardrail Checks

- final_offline_verdict = BLOCKED_BY_VALIDATION_IMPLEMENTATION
- all required_outputs_present values false
- all forbidden_calculation_status values false
- all guardrail_status values true
- no OFFLINE_EDGE_CANDIDATE
- no EDGE_CANDIDATE
- no split_scoring_safe = true
- no pass/safe/candidate status in audit
- no strategy/PnL/returns/risk/edge keys
- no funding_adjusted_return
- no net_return_value
- no price_change
- no DB / paper-engine / live integration / exchange keys / report promotion / data refresh / service / timer / systemd activity
- no source CSV mutation
- no repository output/ or tracked tmp/ writes

## Interpretation

This smoke proves only that split_leakage_audit_diagnostics is emitted during the real-data CLI path and that the current split windows are recorded as diagnostic-only and insufficient for scoring.

This smoke does **not** prove:

- purge/embargo splits
- split scoring safety
- OOS safety
- strategy readiness
- OOS seal
- trial manifest
- symbol universe freeze
- signal validity
- position validity
- returns
- PnL
- risk
- edge
- live readiness

## Closing

EDGE_UNPROVEN remains.
BLOCK_LIVE_INTEGRATION remains.
final_offline_verdict remains BLOCKED_BY_VALIDATION_IMPLEMENTATION.
Current split windows are usable for inventory/funding diagnostics only.
Current split windows are insufficient for strategy scoring.
No strategy work is authorized by this smoke.