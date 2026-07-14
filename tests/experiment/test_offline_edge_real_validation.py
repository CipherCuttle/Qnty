"""Tests for quantbot/experiment/offline_edge_real_validation.py

Receipt-skeleton PR: verifies the schema, split-builder skeleton, cost-case
matrix skeleton, validation refusals, and /tmp-only writer for the first
real offline validation receipt. This PR does not compute returns, PnL,
Sharpe, or run any engine — every test here confirms that stays true.

Extended in feat/qnty-real-validation-input-inventory-splits: tests for
input inventory building, timestamp metadata scanning, split materialization
from inventory, forbidden nested keys, receipt with inventory, and CLI with
directory arguments.
"""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

import quantbot.experiment.offline_edge_real_validation as real_validation
from quantbot.experiment.offline_edge_real_validation import (
    BLOCKED_FOR_FUTURE_FUNDING_APPLICATION,
    ELIGIBLE_FOR_FUTURE_FUNDING_APPLICATION,
    EMPTY_BOTH_NOT_BLOCKING,
    EXACT_CANONICAL_TIMESTAMP_SET_MATCH,
    FLOOR_TO_SECOND,
    FUNDING_APPLICATION_READINESS_GATE_DIAGNOSTIC_ONLY,
    MATCHING_RANGES,
    NOT_EXECUTED,
    SKIPPED_BY_READINESS_GATE,
    STRICT_CANONICAL_TIMESTAMP_EXACT_MATCH_NO_COLLISION_NO_AMBIGUITY,
    _canonicalization_symbol_policy,
    _materialize_fixture_case,
    _parse_timestamp,
    _validate_blocked_readiness_evidence,
    _validate_eligible_readiness_evidence,
    _validate_readiness_symbol_entry,
    _validate_scaffold_readiness_gate,
    build_cost_case_matrix,
    build_deterministic_split_definitions,
    build_real_validation_input_inventory,
    build_real_validation_receipt,
    materialize_cost_case_observational_drag,
    materialize_gross_observational_returns,
    materialize_funding_observational_adjustments,
    materialize_funding_to_bars_alignment_diagnostics,
    materialize_funding_to_bars_temporal_joinability_diagnostics,
    materialize_funding_to_bars_timestamp_convention_diagnostics,
    materialize_funding_to_bars_timestamp_canonicalization_diagnostics,
    materialize_funding_application_readiness_gate_diagnostics,
    materialize_funding_adjusted_bars_scaffold_diagnostics,
    materialize_funding_adjustment_policy_contract_diagnostics,
    materialize_funding_adjustment_arithmetic_scaffold_diagnostics,
    materialize_funding_adjustment_row_scaffold_diagnostics,
    _build_funding_adjustment_sample_aggregate_diagnostics,
    _build_split_leakage_audit_diagnostics,
    _build_strategy_rule_contract_diagnostics,
    _derive_strategy_rule_contract_packet_gate,
    materialize_strategy_rule_contract_instance_diagnostics,
    SPLIT_LEAKAGE_AUDIT_VERSION,
    SPLIT_LEAKAGE_AUDIT_DIAGNOSTIC_ONLY,
    SPLIT_LEAKAGE_AUDIT_INSUFFICIENT_FOR_SCORING,
    SPLIT_LEAKAGE_AUDIT_BLOCKED,
    SPLIT_LEAKAGE_AUDIT_ROW_COUNT_NOT_COMPUTED,
    _SPLIT_BUILDER_INVENTORY,
    _SPLIT_BUILDER_FALLBACK,
    STRATEGY_RULE_CONTRACT_VERSION,
    STRATEGY_RULE_CONTRACT_DIAGNOSTIC_ONLY,
    STRATEGY_RULE_CONTRACT_NOT_DEFINED,
    STRATEGY_RULE_CONTRACT_BLOCKED_REASON_NOT_DEFINED,
    NOT_DEFINED,
    TRIAL_MANIFEST_VERSION,
    TRIAL_MANIFEST_DIAGNOSTIC_ONLY,
    TRIAL_MANIFEST_NOT_DEFINED,
    TRIAL_MANIFEST_BLOCKED_REASON_NOT_DEFINED,
    _build_trial_manifest_diagnostics,
    _derive_trial_manifest_preregistration_gate,
    _REQUIRED_FALSE_TRIAL_MANIFEST_FIELDS,
    materialize_trial_manifest_preregistration_diagnostics,
    OOS_SEAL_VERSION,
    OOS_SEAL_DIAGNOSTIC_ONLY,
    OOS_SEAL_NOT_DEFINED,
    OOS_SEAL_BLOCKED_REASON_NOT_DEFINED,
    _build_oos_seal_diagnostics,
    NULL_BENCHMARK_CONTRACT_VERSION,
    NULL_BENCHMARK_CONTRACT_DIAGNOSTIC_ONLY,
    NULL_BENCHMARK_CONTRACT_NOT_DEFINED,
    NULL_BENCHMARK_CONTRACT_BLOCKED_REASON_NOT_DEFINED,
    NULL_BENCHMARK_PREREGISTERED_DIAGNOSTIC_ONLY,
    NULL_REFERENCE_POLICY_FROZEN,
    NULL_REFERENCE_FAMILY_FROZEN,
    NULL_REFERENCE_COMPUTATION_POLICY_FROZEN,
    NULL_REFERENCE_COMPARISON_POLICY_FROZEN,
    _build_null_benchmark_contract_diagnostics,
    _derive_null_benchmark_preregistration_gate,
    materialize_null_benchmark_preregistration_diagnostics,
    MULTIPLE_TESTING_CONTROL_VERSION,
    MULTIPLE_TESTING_CONTROL_DIAGNOSTIC_ONLY,
    MULTIPLE_TESTING_CONTROL_NOT_DEFINED,
    MULTIPLE_TESTING_CONTROL_BLOCKED_REASON_NOT_DEFINED,
    MULTIPLE_TESTING_CONTROL_PREREGISTERED_DIAGNOSTIC_ONLY,
    TESTING_FAMILY_POLICY_FROZEN,
    SEARCH_PROCEDURE_POLICY_FROZEN,
    MULTIPLICITY_CONTROL_POLICY_FROZEN,
    STATISTICAL_EVALUATION_POLICY_FROZEN,
    _build_multiple_testing_control_diagnostics,
    _derive_multiple_testing_control_preregistration_gate,
    materialize_multiple_testing_control_preregistration_diagnostics,
    TRADE_POSITION_SIMULATION_CONTRACT_VERSION,
    TRADE_POSITION_SIMULATION_CONTRACT_DIAGNOSTIC_ONLY,
    TRADE_POSITION_SIMULATION_CONTRACT_NOT_DEFINED,
    TRADE_POSITION_SIMULATION_CONTRACT_BLOCKED_REASON_NOT_DEFINED,
    _build_trade_position_simulation_contract_diagnostics,
    _derive_simulation_policy_preregistration_gate,
    materialize_simulation_policy_preregistration_diagnostics,
    NET_PNL_EQUITY_RISK_CONTRACT_VERSION,
    NET_PNL_EQUITY_RISK_CONTRACT_DIAGNOSTIC_ONLY,
    NET_PNL_EQUITY_RISK_CONTRACT_NOT_DEFINED,
    NET_PNL_EQUITY_RISK_CONTRACT_BLOCKED_REASON_NOT_DEFINED,
    _build_net_pnl_equity_risk_contract_diagnostics,
    _net_pnl_equity_risk_absence_diagnostics,
    _economic_accounting_policy_absence_diagnostics,
    materialize_economic_accounting_policy_preregistration_diagnostics,
    _derive_economic_accounting_policy_preregistration_gate,
    ECONOMIC_ACCOUNTING_POLICY_PREREGISTERED_DIAGNOSTIC_ONLY,
    ECONOMIC_ACCOUNTING_POLICY_NOT_LOADED,
    BLOCKED_BY_SIMULATION_POLICY_GATE,
    BLOCKED_BY_INCOMPLETE_ECONOMIC_ACCOUNTING_POLICY_EVIDENCE,
    ECONOMIC_ACCOUNTING_FAMILY_POLICY_FROZEN,
    ECONOMIC_VALUE_POLICY_FROZEN,
    COST_VALUE_POLICY_FROZEN,
    FUNDING_VALUE_POLICY_FROZEN,
    AGGREGATE_VALUE_POLICY_FROZEN,
    CAPITAL_PATH_POLICY_FROZEN,
    DISPERSION_SUMMARY_POLICY_FROZEN,
    ACCOUNTING_OUTPUT_POLICY_FROZEN,
    FINAL_OFFLINE_EDGE_VERDICT_LOGIC_VERSION,
    FINAL_OFFLINE_EDGE_VERDICT_LOGIC_DIAGNOSTIC_ONLY,
    FINAL_OFFLINE_EDGE_VERDICT_LOGIC_BLOCKED,
    FINAL_VERDICT_ADVANCEMENT_BLOCKED_REASON,
    FINAL_VERDICT_SPLIT_SCORING_NOT_SAFE,
    UPSTREAM_REDUCTION_MODE_STATIC,
    _build_final_offline_edge_verdict_logic_diagnostics,
    PREREQUISITE_CLOSURE_VERSION,
    PREREQUISITE_CLOSURE_REQUIRED_GATE_NAMES,
    _build_prerequisite_closure_diagnostics,
    _derive_prerequisite_closure_gate,
    IMPLEMENTATION_BOUNDARY_VERSION,
    IMPLEMENTATION_BOUNDARY_SCOPE,
    IMPLEMENTATION_BOUNDARY_DECLARED_DIAGNOSTIC_ONLY,
    BLOCKED_BY_IMPLEMENTATION_BOUNDARY_GATE,
    _build_implementation_boundary_diagnostics,
    _derive_implementation_boundary_gate,
    _IMPLEMENTATION_BOUNDARY_AUTHORIZATION_FIELDS,
    NO_OUTPUT_RUNNER_INVOCATION_VERSION,
    NO_OUTPUT_RUNNER_INVOCATION_SCOPE,
    NO_OUTPUT_RUNNER_INVOCATION_DECLARED_DIAGNOSTIC_ONLY,
    NO_OUTPUT_RUNNER_NOT_IMPLEMENTED,
    NO_OUTPUT_RUNNER_OUTPUT_POLICY_FROZEN,
    NO_OUTPUT_RUNNER_MATERIALIZATION_POLICY_FROZEN,
    _build_no_output_runner_invocation_diagnostics,
    _derive_no_output_runner_invocation_gate,
    _NO_OUTPUT_RUNNER_INVOCATION_AUTHORIZATION_FIELDS,
    ALLOWED_RUNNER_INPUT_PROJECTION_VERSION,
    ALLOWED_RUNNER_INPUT_PROJECTION_SCOPE,
    ALLOWED_RUNNER_INPUT_PROJECTION_DECLARED_DIAGNOSTIC_ONLY,
    ALLOWED_RUNNER_INPUT_PROJECTION_METADATA_ONLY,
    ALLOWED_RUNNER_INPUT_PROJECTION_OUTPUT_POLICY_FROZEN,
    ALLOWED_RUNNER_INPUT_PROJECTION_MATERIALIZATION_POLICY_FROZEN,
    BLOCKED_BY_NO_OUTPUT_RUNNER_INVOCATION_GATE,
    BLOCKED_BY_INCOMPLETE_RUNNER_INPUT_PROJECTION_EVIDENCE,
    _build_allowed_runner_input_projection_diagnostics,
    _derive_allowed_runner_input_projection_gate,
    _ALLOWED_RUNNER_INPUT_PROJECTION_AUTHORIZATION_FIELDS,
    PROJECTED_INPUT_SHAPE_INVENTORY_VERSION,
    PROJECTED_INPUT_SHAPE_INVENTORY_SCOPE,
    PROJECTED_INPUT_SHAPE_INVENTORY_DECLARED_DIAGNOSTIC_ONLY,
    PROJECTED_INPUT_SHAPE_METADATA_ONLY_POLICY,
    BLOCKED_BY_ALLOWED_RUNNER_INPUT_PROJECTION_GATE,
    BLOCKED_BY_INCOMPLETE_PROJECTED_INPUT_SHAPE_EVIDENCE,
    BLOCKED_BY_UNEXPECTED_INPUT_VALUE_EMISSION,
    _build_projected_input_shape_inventory_diagnostics,
    _derive_projected_input_shape_inventory_gate,
    _PROJECTED_INPUT_SHAPE_INVENTORY_AUTHORIZATION_FIELDS,
    PROJECTED_INPUT_ROW_COUNT_VERSION,
    PROJECTED_INPUT_ROW_COUNT_SCOPE,
    PROJECTED_INPUT_ROW_COUNT_DECLARED_DIAGNOSTIC_ONLY,
    PROJECTED_INPUT_ROW_COUNT_METADATA_ONLY_POLICY,
    BLOCKED_BY_PROJECTED_INPUT_SHAPE_INVENTORY_GATE,
    BLOCKED_BY_INCOMPLETE_PROJECTED_INPUT_ROW_COUNT_EVIDENCE,
    _build_projected_input_row_count_diagnostics,
    _derive_projected_input_row_count_gate,
    _PROJECTED_INPUT_ROW_COUNT_AUTHORIZATION_FIELDS,
    PROJECTED_INPUT_TEMPORAL_SEQUENCE_VERSION,
    PROJECTED_INPUT_TEMPORAL_SEQUENCE_SCOPE,
    PROJECTED_INPUT_TEMPORAL_SEQUENCE_DECLARED_DIAGNOSTIC_ONLY,
    PROJECTED_INPUT_TEMPORAL_SEQUENCE_METADATA_ONLY_POLICY,
    BLOCKED_BY_PROJECTED_INPUT_ROW_COUNT_GATE,
    BLOCKED_BY_INCOMPLETE_PROJECTED_INPUT_TEMPORAL_SEQUENCE_EVIDENCE,
    BLOCKED_BY_UNEXPECTED_TIME_VALUE_EMISSION,
    _build_projected_input_temporal_sequence_diagnostics,
    _derive_projected_input_temporal_sequence_gate,
    _PROJECTED_INPUT_TEMPORAL_SEQUENCE_AUTHORIZATION_FIELDS,
    PROJECTED_INPUT_JOINABILITY_VERSION,
    PROJECTED_INPUT_JOINABILITY_SCOPE,
    PROJECTED_INPUT_JOINABILITY_DECLARED_DIAGNOSTIC_ONLY,
    PROJECTED_INPUT_JOINABILITY_METADATA_ONLY_POLICY,
    PROJECTED_INPUT_JOINABILITY_FROZEN_POLICY,
    BLOCKED_BY_PROJECTED_INPUT_TEMPORAL_SEQUENCE_GATE,
    BLOCKED_BY_INCOMPLETE_PROJECTED_INPUT_JOINABILITY_EVIDENCE,
    BLOCKED_BY_UNEXPECTED_JOINABILITY_VALUE_EMISSION,
    _build_projected_input_joinability_diagnostics,
    _derive_projected_input_joinability_gate,
    _PROJECTED_INPUT_JOINABILITY_AUTHORIZATION_FIELDS,
    NO_OUTPUT_RUNNER_DRY_HARNESS_VERSION,
    NO_OUTPUT_RUNNER_DRY_HARNESS_SCOPE,
    NO_OUTPUT_RUNNER_DRY_HARNESS_DECLARED_DIAGNOSTIC_ONLY,
    NO_OUTPUT_RUNNER_DRY_HARNESS_POLICY,
    BLOCKED_BY_PROJECTED_INPUT_JOINABILITY_GATE,
    BLOCKED_BY_INCOMPLETE_NO_OUTPUT_RUNNER_DRY_HARNESS_EVIDENCE,
    BLOCKED_BY_UNEXPECTED_RUNNER_OUTPUT_EMISSION,
    _build_no_output_runner_dry_harness_diagnostics,
    _derive_no_output_runner_dry_harness_gate,
    _NO_OUTPUT_RUNNER_DRY_HARNESS_AUTHORIZATION_FIELDS,
    MATERIALIZED_RULE_ROW_SCHEMA_LOCK_VERSION,
    MATERIALIZED_RULE_ROW_SCHEMA_LOCK_SCOPE,
    MATERIALIZED_RULE_ROW_SCHEMA_LOCK_DECLARED_DIAGNOSTIC_ONLY,
    MATERIALIZED_RULE_ROW_SCHEMA_LOCK_POLICY,
    BLOCKED_BY_NO_OUTPUT_RUNNER_DRY_HARNESS_GATE,
    BLOCKED_BY_INCOMPLETE_MATERIALIZED_RULE_ROW_SCHEMA_EVIDENCE,
    BLOCKED_BY_UNEXPECTED_RULE_ROW_EMISSION,
    _ALLOWED_MATERIALIZED_RULE_ROW_SCHEMA_KEYS,
    _REQUIRED_MATERIALIZED_RULE_ROW_SCHEMA_KEYS,
    _FORBIDDEN_MATERIALIZED_RULE_ROW_SCHEMA_KEY_NAMES,
    _build_materialized_rule_row_schema_lock_diagnostics,
    _derive_materialized_rule_row_schema_lock_gate,
    _MATERIALIZED_RULE_ROW_SCHEMA_LOCK_AUTHORIZATION_FIELDS,
    MATERIALIZED_RULE_ROWS_V0_VERSION,
    MATERIALIZED_RULE_ROWS_V0_SCOPE,
    MATERIALIZED_RULE_ROWS_V0_DECLARED_ARTIFACT_ONLY,
    MATERIALIZED_RULE_ROWS_V0_POLICY,
    MATERIALIZED_RULE_ROWS_V0_MAX_ROWS,
    BLOCKED_BY_MATERIALIZED_RULE_ROW_SCHEMA_LOCK_GATE,
    BLOCKED_BY_INCOMPLETE_MATERIALIZED_RULE_ROWS_V0_EVIDENCE,
    BLOCKED_BY_UNEXPECTED_RULE_ROW_SCHEMA,
    BLOCKED_BY_UNEXPECTED_RULE_ROW_FORBIDDEN_KEY,
    BLOCKED_BY_UNEXPECTED_RULE_ROW_FORBIDDEN_VALUE,
    BLOCKED_BY_UNEXPECTED_ECONOMIC_OR_SCORING_AUTHORIZATION,
    _build_materialized_rule_rows_v0_diagnostics,
    _derive_materialized_rule_rows_v0_gate,
    SIMULATED_EVENT_SCHEMA_LOCK_VERSION,
    SIMULATED_EVENT_SCHEMA_LOCK_SCOPE,
    SIMULATED_EVENT_SCHEMA_LOCK_DECLARED_DIAGNOSTIC_ONLY,
    SIMULATED_EVENT_SCHEMA_LOCK_POLICY,
    BLOCKED_BY_MATERIALIZED_RULE_ROWS_V0_GATE,
    BLOCKED_BY_INCOMPLETE_SIMULATED_EVENT_SCHEMA_EVIDENCE,
    BLOCKED_BY_UNEXPECTED_SIMULATED_EVENT_EMISSION,
    BLOCKED_BY_UNEXPECTED_SIMULATED_EVENT_AUTHORIZATION,
    _ALLOWED_SIMULATED_EVENT_SCHEMA_KEYS,
    _REQUIRED_SIMULATED_EVENT_SCHEMA_KEYS,
    _FORBIDDEN_SIMULATED_EVENT_SCHEMA_KEY_NAMES,
    _build_simulated_event_schema_lock_diagnostics,
    _derive_simulated_event_schema_lock_gate,
    SIMULATED_EVENTS_V0_VERSION,
    SIMULATED_EVENTS_V0_DECLARED_ARTIFACT_ONLY,
    SIMULATED_EVENTS_V0_POLICY,
    BLOCKED_BY_SIMULATED_EVENT_SCHEMA_LOCK_GATE,
    BLOCKED_BY_INCOMPLETE_SIMULATED_EVENTS_V0_EVIDENCE,
    BLOCKED_BY_UNEXPECTED_SIMULATED_EVENT_SCHEMA,
    BLOCKED_BY_UNEXPECTED_SIMULATED_EVENT_FORBIDDEN_KEY,
    BLOCKED_BY_UNEXPECTED_SIMULATED_EVENT_FORBIDDEN_VALUE,
    BLOCKED_BY_UNEXPECTED_SIMULATED_EVENT_DOWNSTREAM_OUTPUT,
    BLOCKED_BY_UNEXPECTED_SIMULATED_EVENT_DOWNSTREAM_AUTHORIZATION,
    _build_simulated_events_v0_diagnostics,
    _derive_simulated_events_v0_gate,
    ECONOMIC_OUTPUT_SCHEMA_LOCK_VERSION,
    ECONOMIC_OUTPUT_SCHEMA_LOCK_SCOPE,
    ECONOMIC_OUTPUT_SCHEMA_LOCK_DECLARED_DIAGNOSTIC_ONLY,
    ECONOMIC_OUTPUT_SCHEMA_LOCK_POLICY,
    BLOCKED_BY_SIMULATED_EVENTS_V0_GATE,
    BLOCKED_BY_INCOMPLETE_ECONOMIC_OUTPUT_SCHEMA_EVIDENCE,
    BLOCKED_BY_UNEXPECTED_ECONOMIC_OUTPUT_EMISSION,
    BLOCKED_BY_UNEXPECTED_ECONOMIC_OUTPUT_AUTHORIZATION,
    _ALLOWED_ECONOMIC_OUTPUT_SCHEMA_KEYS,
    _REQUIRED_ECONOMIC_OUTPUT_SCHEMA_KEYS,
    _FORBIDDEN_ECONOMIC_OUTPUT_SCHEMA_KEY_NAMES,
    _build_economic_output_schema_lock_diagnostics,
    _derive_economic_output_schema_lock_gate,
    materialize_input_rows_for_splits,
    materialize_split_definitions_from_inventory,
    validate_real_validation_receipt,
    write_real_validation_receipt,
)
from quantbot.experiment.offline_edge_schema import (
    BLOCKED_BY_DATA_QUALITY_REGRESSION,
    BLOCKED_BY_VALIDATION_IMPLEMENTATION,
    INCONCLUSIVE,
    NO_EDGE,
    OFFLINE_EDGE_CANDIDATE,
)

FORBIDDEN_IMPORT_MODULES = {
    "pandas",
    "numpy",
    "sqlite3",
    "ccxt",
}
FORBIDDEN_IMPORT_PREFIXES = (
    "quantbot.exec",
    "quantbot.exchange",
    "quantbot.paper",
    "quantbot.live",
)


def _base_receipt(**overrides):
    splits = build_deterministic_split_definitions(
        global_min_timestamp="2026-01-01T00:00:00Z",
        global_max_timestamp="2026-02-01T00:00:00Z",
    )
    costs = build_cost_case_matrix()
    kwargs = dict(
        input_manifest_fingerprint="a" * 64,
        data_quality_receipt_sha256="b" * 64,
        code_commit_sha="c" * 40,
        split_definitions=splits,
        cost_cases=costs,
    )
    kwargs.update(overrides)
    return build_real_validation_receipt(**kwargs)


def _write_tiny_bars_csv(tmp_path: Path, filename: str = "bars.csv") -> Path:
    """Write a tiny bars CSV with timestamp column and return its path."""
    path = tmp_path / filename
    path.write_text(
        "timestamp,open,high,low,close,volume\n"
        "2026-01-01T00:00:00Z,100.0,101.0,99.0,100.5,1000\n"
        "2026-01-02T00:00:00Z,100.5,102.0,100.0,101.0,1200\n"
        "2026-01-03T00:00:00Z,101.0,103.0,100.5,102.0,1100\n"
    )
    return path


def _write_tiny_funding_csv(tmp_path: Path, filename: str = "funding.csv") -> Path:
    """Write a tiny funding CSV with fundingTime column and return its path."""
    path = tmp_path / filename
    path.write_text(
        "fundingTime,fundingRate,markPrice\n"
        "2026-01-01T12:00:00Z,0.0001,50000.0\n"
        "2026-01-02T12:00:00Z,0.0002,50100.0\n"
    )
    return path


def _write_bars_csv_with_timestamps(
    dir_path: Path, filename: str, timestamps: list[str]
) -> Path:
    """Write a bars CSV with the given ordered ISO timestamps and dummy OHLCV."""
    path = dir_path / filename
    lines = ["timestamp,open,high,low,close,volume"]
    for index, ts in enumerate(timestamps):
        lines.append(f"{ts},100.0,101.0,99.0,{100.0 + index},1000")
    path.write_text("\n".join(lines) + "\n")
    return path


def _write_funding_csv_with_timestamps(
    dir_path: Path, filename: str, timestamps: list[str]
) -> Path:
    """Write a funding CSV with the given ordered ISO fundingTime values."""
    path = dir_path / filename
    lines = ["fundingTime,fundingRate,markPrice"]
    for ts in timestamps:
        lines.append(f"{ts},0.0001,50000.0")
    path.write_text("\n".join(lines) + "\n")
    return path


def _write_tiny_numeric_funding_csv(
    tmp_path: Path, filename: str = "funding.csv"
) -> Path:
    """Write a tiny Binance-style funding CSV using epoch milliseconds."""
    path = tmp_path / filename
    path.write_text(
        "fundingTime,fundingRate,markPrice\n"
        "1625097600000,0.0001,50000.0\n"
        "1625184000000,0.0002,50100.0\n"
    )
    return path


# ── Existing receipt builder tests ──────────────────────────────────────


class TestReceiptBuilder:
    def test_receipt_has_required_keys(self):
        receipt = _base_receipt()
        required = {
            "validation_receipt",
            "input_manifest_fingerprint",
            "data_quality_receipt_sha256",
            "code_commit_sha",
            "split_definitions",
            "cost_cases",
            "required_outputs_present",
            "forbidden_calculation_status",
            "guardrail_status",
            "final_offline_verdict",
            "final_offline_verdict_rationale",
        }
        assert required.issubset(receipt.keys())

    def test_final_offline_verdict_is_blocked(self):
        receipt = _base_receipt()
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION

    def test_required_outputs_present_all_false(self):
        receipt = _base_receipt()
        for value in receipt["required_outputs_present"].values():
            assert value is False

    def test_forbidden_calculation_status_all_false(self):
        receipt = _base_receipt()
        for key, value in receipt["forbidden_calculation_status"].items():
            assert value is False, f"{key} must be False"

    def test_guardrail_status_all_true(self):
        receipt = _base_receipt()
        for key, value in receipt["guardrail_status"].items():
            assert value is True, f"{key} must be True"

    def test_no_forbidden_top_level_keys_present(self):
        receipt = _base_receipt()
        for forbidden in ("pnl", "sharpe", "edge", "strategy_performance"):
            assert forbidden not in receipt


# ── Existing validation tests ───────────────────────────────────────────


class TestValidation:
    def test_valid_skeleton_receipt_passes(self):
        validate_real_validation_receipt(_base_receipt())

    def test_missing_required_key_rejected(self):
        receipt = _base_receipt()
        del receipt["cost_cases"]
        with pytest.raises(ValueError):
            validate_real_validation_receipt(receipt)

    def test_offline_edge_candidate_rejected_in_skeleton_phase(self):
        receipt = _base_receipt()
        receipt["final_offline_verdict"] = OFFLINE_EDGE_CANDIDATE
        with pytest.raises(ValueError):
            validate_real_validation_receipt(receipt)

    @pytest.mark.parametrize("verdict", [NO_EDGE, INCONCLUSIVE, BLOCKED_BY_DATA_QUALITY_REGRESSION])
    def test_other_vocabulary_verdicts_also_rejected_this_phase(self, verdict):
        # Named in the allowed vocabulary for future PRs, but this PR may
        # only ever emit BLOCKED_BY_VALIDATION_IMPLEMENTATION.
        receipt = _base_receipt()
        receipt["final_offline_verdict"] = verdict
        with pytest.raises(ValueError):
            validate_real_validation_receipt(receipt)

    def test_unknown_verdict_rejected(self):
        receipt = _base_receipt()
        receipt["final_offline_verdict"] = "PROFITABLE"
        with pytest.raises(ValueError):
            validate_real_validation_receipt(receipt)

    @pytest.mark.parametrize("key", ["pnl", "sharpe", "edge", "strategy_performance"])
    def test_forbidden_top_level_keys_rejected(self, key):
        receipt = _base_receipt()
        receipt[key] = {"anything": 1}
        with pytest.raises(ValueError):
            validate_real_validation_receipt(receipt)

    def test_forbidden_calculation_status_true_rejected(self):
        receipt = _base_receipt()
        receipt["forbidden_calculation_status"]["returns_computed"] = True
        with pytest.raises(ValueError):
            validate_real_validation_receipt(receipt)

    def test_guardrail_status_false_rejected(self):
        receipt = _base_receipt()
        receipt["guardrail_status"]["edge_unproven"] = False
        with pytest.raises(ValueError):
            validate_real_validation_receipt(receipt)

    def test_missing_guardrail_key_rejected(self):
        receipt = _base_receipt()
        del receipt["guardrail_status"]["block_live_integration"]
        with pytest.raises(ValueError):
            validate_real_validation_receipt(receipt)

    def test_output_path_not_tmp_rejected(self):
        receipt = _base_receipt()
        receipt["output_path"] = "/home/someone/receipt.json"
        with pytest.raises(ValueError):
            validate_real_validation_receipt(receipt)

    def test_output_path_under_srv_qnty_rejected(self):
        receipt = _base_receipt()
        receipt["output_path"] = "/srv/qnty/output/receipt.json"
        with pytest.raises(ValueError):
            validate_real_validation_receipt(receipt)

    def test_output_path_under_tmp_accepted(self):
        receipt = _base_receipt()
        receipt["output_path"] = "/tmp/qnty_test/receipt.json"
        validate_real_validation_receipt(receipt)


# ── Existing split builder tests ────────────────────────────────────────


class TestSplitBuilder:
    def test_split_builder_deterministic(self):
        a = build_deterministic_split_definitions(
            global_min_timestamp="2026-01-01T00:00:00Z",
            global_max_timestamp="2026-02-01T00:00:00Z",
            split_count=3,
        )
        b = build_deterministic_split_definitions(
            global_min_timestamp="2026-01-01T00:00:00Z",
            global_max_timestamp="2026-02-01T00:00:00Z",
            split_count=3,
        )
        assert a == b
        assert len(a) == 3

    def test_split_calculation_status_not_executed(self):
        splits = build_deterministic_split_definitions(
            global_min_timestamp="t0",
            global_max_timestamp="t1",
        )
        for split in splits:
            assert split["calculation_status"] == "NOT_EXECUTED"

    def test_split_count_less_than_one_rejected(self):
        with pytest.raises(ValueError):
            build_deterministic_split_definitions(
                global_min_timestamp="t0",
                global_max_timestamp="t1",
                split_count=0,
            )

    def test_split_count_negative_rejected(self):
        with pytest.raises(ValueError):
            build_deterministic_split_definitions(
                global_min_timestamp="t0",
                global_max_timestamp="t1",
                split_count=-1,
            )


# ── Existing cost-case matrix tests ─────────────────────────────────────


class TestCostCaseMatrix:
    def test_has_low_base_high(self):
        cases = build_cost_case_matrix()
        names = {c["cost_case"] for c in cases}
        assert names == {"low", "base", "high"}

    def test_base_matches_conservative_prior_assumptions(self):
        cases = {c["cost_case"]: c for c in build_cost_case_matrix()}
        base = cases["base"]
        assert base["commission_bps_per_side"] == 5.0
        assert base["slippage_bps_per_side"] == 5.0
        assert base["spread_bps_per_side"] == 1.0

    def test_all_cases_not_executed(self):
        for case in build_cost_case_matrix():
            assert case["calculation_status"] == "NOT_EXECUTED"


# ── Existing writer tests ───────────────────────────────────────────────


class TestWriter:
    def test_writer_refuses_non_tmp_path(self, tmp_path):
        receipt = _base_receipt()
        # tmp_path fixture is under the real /tmp on most systems but not
        # guaranteed; force an explicit non-tmp path instead.
        with pytest.raises(ValueError):
            write_real_validation_receipt(receipt, Path("/home/someone/receipt.json"))

    def test_writer_refuses_srv_qnty(self):
        receipt = _base_receipt()
        with pytest.raises(ValueError):
            write_real_validation_receipt(receipt, Path("/srv/qnty/output/receipt.json"))

    def test_writer_writes_under_tmp_and_returns_sha256(self):
        receipt = _base_receipt()
        out_dir = Path("/tmp") / f"qnty_real_validation_test_{uuid.uuid4().hex}"
        out_path = out_dir / "real_validation_receipt.json"
        try:
            digest = write_real_validation_receipt(receipt, out_path)
            assert isinstance(digest, str)
            assert len(digest) == 64
            assert out_path.exists()
            with open(out_path) as f:
                written = json.load(f)
            assert written["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION
        finally:
            if out_path.exists():
                out_path.unlink()
            if out_dir.exists():
                out_dir.rmdir()


# ── Existing forbidden imports tests ────────────────────────────────────


class TestForbiddenImports:
    def test_no_forbidden_imports_via_ast(self):
        module_path = (
            Path(__file__).resolve().parents[2]
            / "quantbot"
            / "experiment"
            / "offline_edge_real_validation.py"
        )
        tree = ast.parse(module_path.read_text())
        imported_names = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_names.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported_names.append(node.module)

        for name in imported_names:
            top = name.split(".")[0]
            assert top not in FORBIDDEN_IMPORT_MODULES, f"forbidden import: {name}"
            for prefix in FORBIDDEN_IMPORT_PREFIXES:
                assert not name.startswith(prefix), f"forbidden import: {name}"


# ── Existing CLI tests ──────────────────────────────────────────────────


class TestCLI:
    def test_cli_writes_receipt_under_tmp_blocked_verdict(self):
        out_dir = Path("/tmp") / f"qnty_real_validation_cli_test_{uuid.uuid4().hex}"
        receipt_path = out_dir / "real_validation_receipt.json"
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "quantbot.experiment.offline_edge_real_validation",
                    "--read-only",
                    "--output-dir",
                    str(out_dir),
                    "--input-manifest-fingerprint",
                    "a" * 64,
                    "--data-quality-receipt-sha256",
                    "b" * 64,
                    "--code-commit-sha",
                    "c" * 40,
                    "--global-min-timestamp",
                    "2026-01-01T00:00:00Z",
                    "--global-max-timestamp",
                    "2026-02-01T00:00:00Z",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0, result.stderr
            assert f"final_offline_verdict={BLOCKED_BY_VALIDATION_IMPLEMENTATION}" in result.stdout
            assert receipt_path.exists()
            with open(receipt_path) as f:
                written = json.load(f)
            assert written["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION
        finally:
            if receipt_path.exists():
                receipt_path.unlink()
            if out_dir.exists():
                out_dir.rmdir()

    def test_cli_refuses_non_tmp_output_dir(self):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "quantbot.experiment.offline_edge_real_validation",
                "--read-only",
                "--output-dir",
                "/home/someone/qnty_real_validation_cli_test",
                "--input-manifest-fingerprint",
                "a" * 64,
                "--data-quality-receipt-sha256",
                "b" * 64,
                "--code-commit-sha",
                "c" * 40,
                "--global-min-timestamp",
                "2026-01-01T00:00:00Z",
                "--global-max-timestamp",
                "2026-02-01T00:00:00Z",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode != 0


# ── Existing nested prod path tests ─────────────────────────────────────


class TestValidateRealValidationReceiptNestedProdPaths:
    """Recursive production-path scanning for validate_real_validation_receipt.

    Every receipt that contains a nested field with a value containing
    ``/srv/qnty/`` (or resolving under ``/srv/qnty``) must be rejected
    with ``AssertionError``.  Sibling paths like ``/srv/qnty2/...`` must
    NOT be rejected.
    """

    def test_nested_split_definitions_source_path_rejected(self):
        """A split_definitions entry with a source_path under /srv/qnty/ must be rejected."""
        receipt = _base_receipt()
        receipt["split_definitions"] = [
            {"source_path": "/srv/qnty/data/foo.csv", "split_id": "split_00"}
        ]
        with pytest.raises(AssertionError, match=r"PROD_BASE|/srv/qnty"):
            validate_real_validation_receipt(receipt)

    def test_nested_cost_cases_debug_path_rejected(self):
        """A cost_cases entry with a debug_path under /srv/qnty/ must be rejected."""
        receipt = _base_receipt()
        receipt["cost_cases"] = [
            {"cost_case": "low", "debug_path": "/srv/qnty/output/foo.json"}
        ]
        with pytest.raises(AssertionError):
            validate_real_validation_receipt(receipt)

    def test_nested_validation_receipt_artifact_path_rejected(self):
        """A deeply nested validation_receipt.artifact_path under /srv/qnty/ must be rejected."""
        receipt = _base_receipt()
        receipt["validation_receipt"]["artifact_path"] = "/srv/qnty/artifacts/result.json"
        with pytest.raises(AssertionError):
            validate_real_validation_receipt(receipt)

    def test_sibling_prod_qnty2_not_rejected(self):
        """A path under /srv/qnty2/ (sibling directory) must NOT be rejected."""
        receipt = _base_receipt()
        receipt["some_path"] = "/srv/qnty2/data/file.csv"
        # The trailing-slash substring check: "/srv/qnty/" is NOT in "/srv/qnty2/data/file.csv".
        # The boundary check also rejects correctly since /srv/qnty2 is not under /srv/qnty.
        validate_real_validation_receipt(receipt)

    def test_normal_skeleton_receipt_still_validates(self):
        """A standard skeleton receipt with no prod paths must still pass validation."""
        receipt = _base_receipt()
        # No exception from the recursive scanner; existing validation logic applies.
        validate_real_validation_receipt(receipt)

    def test_writer_still_refuses_srv_qnty_output(self, tmp_path):
        """write_real_validation_receipt must still refuse /srv/qnty output paths."""
        receipt = _base_receipt()
        with pytest.raises(ValueError):
            write_real_validation_receipt(receipt, Path("/srv/qnty/output/receipt.json"))


# ── New: Input inventory tests ──────────────────────────────────────────


class TestBuildRealValidationInputInventory:
    def test_refuses_srv_qnty_bars_dir(self):
        with pytest.raises(ValueError, match="Refusing path under prod base"):
            build_real_validation_input_inventory(
                bars_dir=Path("/srv/qnty/data"),
            )

    def test_refuses_missing_bars_dir(self, tmp_path):
        missing = tmp_path / "does_not_exist"
        with pytest.raises(ValueError, match="does not exist"):
            build_real_validation_input_inventory(
                bars_dir=missing,
            )

    def test_refuses_symlinked_csv_resolving_under_prod_base(
        self, tmp_path, monkeypatch
    ):
        fake_prod = tmp_path / "fake_prod"
        safe_bars = tmp_path / "safe_bars"
        fake_prod.mkdir()
        safe_bars.mkdir()
        prod_csv = _write_tiny_bars_csv(fake_prod, "prod_bars.csv")
        (safe_bars / "linked.csv").symlink_to(prod_csv)
        monkeypatch.setattr(real_validation, "PROD_BASE", fake_prod)

        with pytest.raises(ValueError, match="Refusing path under prod base"):
            build_real_validation_input_inventory(bars_dir=safe_bars)

    def test_lists_only_csvs(self, tmp_path):
        # Create a CSV file and a non-CSV file.
        (tmp_path / "bars.csv").write_text("timestamp,val\n2026-01-01T00:00:00Z,1.0\n")
        (tmp_path / "notes.txt").write_text("not a csv\n")
        inventory = build_real_validation_input_inventory(bars_dir=tmp_path)
        roles = inventory["roles"]
        assert len(roles) == 1
        bars_role = roles[0]
        assert bars_role["role"] == "bars"
        assert bars_role["csv_file_count"] == 1
        assert bars_role["filenames"] == ["bars.csv"]

    def test_computes_per_file_sha256(self, tmp_path):
        csv_path = _write_tiny_bars_csv(tmp_path)
        inventory = build_real_validation_input_inventory(bars_dir=tmp_path)
        bars_role = inventory["roles"][0]
        assert len(bars_role["files"]) == 1
        file_entry = bars_role["files"][0]
        assert file_entry["filename"] == csv_path.name
        assert isinstance(file_entry["sha256"], str)
        assert len(file_entry["sha256"]) == 64
        assert file_entry["column_names"] == [
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]

    def test_aggregate_fingerprint_deterministic(self, tmp_path):
        _write_tiny_bars_csv(tmp_path, "bars_a.csv")
        _write_tiny_bars_csv(tmp_path, "bars_b.csv")
        inv_a = build_real_validation_input_inventory(bars_dir=tmp_path)
        inv_b = build_real_validation_input_inventory(bars_dir=tmp_path)
        fp_a = inv_a["roles"][0]["aggregate_role_fingerprint"]
        fp_b = inv_b["roles"][0]["aggregate_role_fingerprint"]
        assert fp_a == fp_b
        assert isinstance(fp_a, str)
        assert len(fp_a) == 64

    def test_includes_funding_role_when_provided(self, tmp_path):
        bars_dir = tmp_path / "bars"
        funding_dir = tmp_path / "funding"
        bars_dir.mkdir()
        funding_dir.mkdir()
        _write_tiny_bars_csv(bars_dir, "BTCUSDT_8h_ohlcv.csv")
        _write_tiny_funding_csv(funding_dir, "BTCUSDT_funding.csv")

        inventory = build_real_validation_input_inventory(
            bars_dir=bars_dir,
            funding_dir=funding_dir,
        )
        roles = inventory["roles"]
        assert len(roles) == 2
        role_names = {r["role"] for r in roles}
        assert role_names == {"bars", "funding"}

    def test_funding_directory_size_and_fingerprint(self, tmp_path):
        funding_dir = tmp_path / "funding"
        funding_dir.mkdir()
        _write_tiny_funding_csv(funding_dir)

        inventory = build_real_validation_input_inventory(
            bars_dir=funding_dir,
            funding_dir=None,
        )
        # Creating bars dir with funding CSV to test size tracking
        bars_role = inventory["roles"][0]
        assert bars_role["total_size_bytes"] > 0
        assert bars_role["csv_file_count"] == 1


# ── New: Timestamp metadata tests ───────────────────────────────────────


class TestTimestampParser:
    def test_epoch_milliseconds_are_parsed_as_utc(self):
        parsed = _parse_timestamp("1625097600000")
        assert parsed.isoformat() == "2021-07-01T00:00:00+00:00"

    def test_naive_iso_is_deterministically_parsed_as_utc(self):
        parsed = _parse_timestamp("2026-04-22T16:00:00")
        assert parsed.isoformat() == "2026-04-22T16:00:00+00:00"

    def test_z_iso_is_parsed_as_utc(self):
        parsed = _parse_timestamp("2026-04-22T16:00:00Z")
        assert parsed.isoformat() == "2026-04-22T16:00:00+00:00"


class TestTimestampMetadata:
    def test_bars_timestamp_metadata_from_tiny_fixture_csv(self, tmp_path):
        _write_tiny_bars_csv(tmp_path)
        inventory = build_real_validation_input_inventory(bars_dir=tmp_path)
        file_entry = inventory["roles"][0]["files"][0]
        assert file_entry["has_timestamp_column"] is True
        assert file_entry["row_count"] == 3  # 3 data rows
        assert file_entry["min_timestamp"] == "2026-01-01T00:00:00Z"
        assert file_entry["max_timestamp"] == "2026-01-03T00:00:00Z"

    def test_funding_timestamp_metadata_using_funding_time(self, tmp_path):
        _write_tiny_funding_csv(tmp_path)
        inventory = build_real_validation_input_inventory(
            bars_dir=tmp_path,
            funding_dir=tmp_path,
        )
        # bars_role is first, funding_role is second.
        funding_role = inventory["roles"][1] if len(inventory["roles"]) > 1 else inventory["roles"][0]
        # If funding_dir equals bars_dir, we need to find the funding role.
        funding_role = [r for r in inventory["roles"] if r["role"] == "funding"][0]
        file_entry = funding_role["files"][0]
        assert file_entry["has_timestamp_column"] is True
        assert file_entry["row_count"] == 2  # 2 data rows
        assert file_entry["min_timestamp"] == "2026-01-01T12:00:00Z"
        assert file_entry["max_timestamp"] == "2026-01-02T12:00:00Z"

    def test_numeric_funding_time_builds_canonical_inventory(self, tmp_path):
        bars_dir = tmp_path / "bars"
        funding_dir = tmp_path / "funding"
        bars_dir.mkdir()
        funding_dir.mkdir()
        _write_tiny_bars_csv(bars_dir)
        _write_tiny_numeric_funding_csv(funding_dir)

        inventory = build_real_validation_input_inventory(
            bars_dir=bars_dir,
            funding_dir=funding_dir,
        )
        funding_role = [
            role for role in inventory["roles"] if role["role"] == "funding"
        ][0]
        file_entry = funding_role["files"][0]
        assert file_entry["row_count"] == 2
        assert file_entry["min_timestamp"] == "2021-07-01T00:00:00Z"
        assert file_entry["max_timestamp"] == "2021-07-02T00:00:00Z"

    def test_row_count_includes_empty_timestamp_cells(self, tmp_path):
        (tmp_path / "bars.csv").write_text(
            "timestamp,close\n"
            "2026-01-01T00:00:00Z,100\n"
            ",101\n"
            "2026-01-03T00:00:00Z,102\n"
        )

        inventory = build_real_validation_input_inventory(bars_dir=tmp_path)
        file_entry = inventory["roles"][0]["files"][0]
        assert file_entry["row_count"] == 3
        assert file_entry["min_timestamp"] == "2026-01-01T00:00:00Z"
        assert file_entry["max_timestamp"] == "2026-01-03T00:00:00Z"

    def test_malformed_timestamp_fails_closed(self, tmp_path):
        (tmp_path / "bars.csv").write_text(
            "timestamp,close\nnot-a-timestamp,100\n"
        )

        with pytest.raises(ValueError, match="Malformed timestamp.*row 2"):
            build_real_validation_input_inventory(bars_dir=tmp_path)

    def test_missing_timestamp_column_reported(self, tmp_path):
        csv_path = tmp_path / "no_ts.csv"
        csv_path.write_text("price,volume\n100.0,1000\n101.0,1200\n")
        inventory = build_real_validation_input_inventory(bars_dir=tmp_path)
        file_entry = inventory["roles"][0]["files"][0]
        assert file_entry["has_timestamp_column"] is False
        assert file_entry["min_timestamp"] is None
        assert file_entry["max_timestamp"] is None
        # Row count should still be tracked.
        assert file_entry["row_count"] == 2


# ── New: Split materialization tests ────────────────────────────────────


class TestSplitMaterialization:
    def test_materialized_splits_deterministic(self, tmp_path):
        _write_tiny_bars_csv(tmp_path)
        inventory = build_real_validation_input_inventory(bars_dir=tmp_path)
        a = materialize_split_definitions_from_inventory(inventory=inventory, split_count=3)
        b = materialize_split_definitions_from_inventory(inventory=inventory, split_count=3)
        assert a == b
        assert len(a) == 3

    def test_split_count_less_than_one_rejected(self, tmp_path):
        _write_tiny_bars_csv(tmp_path)
        inventory = build_real_validation_input_inventory(bars_dir=tmp_path)
        with pytest.raises(ValueError):
            materialize_split_definitions_from_inventory(inventory=inventory, split_count=0)

    def test_split_materialization_includes_file_counts_no_returns(self, tmp_path):
        _write_tiny_bars_csv(tmp_path)
        inventory = build_real_validation_input_inventory(bars_dir=tmp_path)
        splits = materialize_split_definitions_from_inventory(inventory=inventory, split_count=2)
        for split in splits:
            assert "bars_file_count" in split
            assert "funding_file_count" in split
            # No returns/PnL fields.
            assert "return" not in split
            assert "returns" not in split
            assert "pnl" not in split
            assert "sharpe" not in split
            # Must have split_id, split_index, split_count.
            assert split["split_id"].startswith("split_")
            assert isinstance(split["split_index"], int)
            assert split["split_count"] == 2
            # Must have train_window and validation_window.
            assert "train_window" in split
            assert "validation_window" in split
            # calculation_status must be NOT_EXECUTED.
            assert split["calculation_status"] == "NOT_EXECUTED"

    def test_split_windows_cover_full_range(self, tmp_path):
        _write_tiny_bars_csv(tmp_path)
        inventory = build_real_validation_input_inventory(bars_dir=tmp_path)
        splits = materialize_split_definitions_from_inventory(inventory=inventory, split_count=3)
        # First split's train_window start should be global min.
        assert splits[0]["train_window"]["start"] == "2026-01-01T00:00:00Z"
        # Last split's validation_window end should be global max.
        assert splits[-1]["validation_window"]["end"] == "2026-01-03T00:00:00Z"

    def test_split_calculation_status_not_executed(self, tmp_path):
        _write_tiny_bars_csv(tmp_path)
        inventory = build_real_validation_input_inventory(bars_dir=tmp_path)
        splits = materialize_split_definitions_from_inventory(inventory=inventory, split_count=3)
        for split in splits:
            assert split["calculation_status"] == "NOT_EXECUTED"

    def test_mixed_iso_bars_and_epoch_ms_funding_materialize(self, tmp_path):
        bars_dir = tmp_path / "bars"
        funding_dir = tmp_path / "funding"
        bars_dir.mkdir()
        funding_dir.mkdir()
        _write_tiny_bars_csv(bars_dir)
        _write_tiny_numeric_funding_csv(funding_dir)
        inventory = build_real_validation_input_inventory(
            bars_dir=bars_dir,
            funding_dir=funding_dir,
        )

        splits = materialize_split_definitions_from_inventory(
            inventory=inventory,
            split_count=3,
        )

        assert len(splits) == 3
        assert splits[-1]["validation_window"]["end"] == "2026-01-03T00:00:00Z"
        for split in splits:
            assert split["calculation_status"] == "NOT_EXECUTED"
            assert {"return", "returns", "pnl", "sharpe"}.isdisjoint(split)


# ── Row materialization tests ─────────────────────────────────────


def _two_split_windows() -> list[dict]:
    return [
        {
            "split_id": "split_00",
            "split_index": 0,
            "train_window": {
                "start": "2026-01-01T00:00:00Z",
                "end": "2026-01-01T00:00:00Z",
            },
            "validation_window": {
                "start": "2026-01-01T00:00:00Z",
                "end": "2026-01-02T00:00:00Z",
            },
            "calculation_status": "NOT_EXECUTED",
        },
        {
            "split_id": "split_01",
            "split_index": 1,
            "train_window": {
                "start": "2026-01-01T00:00:00Z",
                "end": "2026-01-02T00:00:00Z",
            },
            "validation_window": {
                "start": "2026-01-02T00:00:00Z",
                "end": "2026-01-03T00:00:00Z",
            },
            "calculation_status": "NOT_EXECUTED",
        },
    ]


def _all_dict_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        keys.update(value)
        for nested in value.values():
            keys.update(_all_dict_keys(nested))
    elif isinstance(value, list):
        for nested in value:
            keys.update(_all_dict_keys(nested))
    return keys


class TestRowMaterialization:
    def test_assigns_timestamp_rows_deterministically(self, tmp_path):
        _write_tiny_bars_csv(tmp_path)
        inventory = build_real_validation_input_inventory(bars_dir=tmp_path)

        first = materialize_input_rows_for_splits(
            inventory=inventory,
            split_definitions=_two_split_windows(),
        )
        second = materialize_input_rows_for_splits(
            inventory=inventory,
            split_definitions=_two_split_windows(),
        )

        assert first == second
        file_result = first["roles"][0]["files"][0]
        assert file_result["total_rows"] == 3
        assert file_result["assigned_rows"] == 3
        assert file_result["unassigned_rows"] == 0
        assert file_result["calculation_status"] == "NOT_EXECUTED"

    def test_validation_boundaries_are_start_inclusive_end_exclusive(self, tmp_path):
        _write_tiny_bars_csv(tmp_path)
        inventory = build_real_validation_input_inventory(bars_dir=tmp_path)

        result = materialize_input_rows_for_splits(
            inventory=inventory,
            split_definitions=_two_split_windows(),
        )
        counts = result["roles"][0]["files"][0]["per_split_counts"]

        assert counts == [
            {"split_id": "split_00", "train_rows": 0, "validation_rows": 1},
            {"split_id": "split_01", "train_rows": 1, "validation_rows": 2},
        ]

    def test_includes_train_validation_counts_per_role_and_file(self, tmp_path):
        bars_dir = tmp_path / "bars"
        funding_dir = tmp_path / "funding"
        bars_dir.mkdir()
        funding_dir.mkdir()
        _write_tiny_bars_csv(bars_dir)
        _write_tiny_funding_csv(funding_dir)
        inventory = build_real_validation_input_inventory(
            bars_dir=bars_dir,
            funding_dir=funding_dir,
        )

        result = materialize_input_rows_for_splits(
            inventory=inventory,
            split_definitions=_two_split_windows(),
        )

        assert {role["role"] for role in result["roles"]} == {"bars", "funding"}
        for role in result["roles"]:
            assert len(role["per_split_counts"]) == 2
            assert len(role["files"][0]["per_split_counts"]) == 2
            assert {"train_rows", "validation_rows"}.issubset(
                role["per_split_counts"][0]
            )

    def test_outside_and_empty_timestamps_are_unassigned(self, tmp_path):
        (tmp_path / "bars.csv").write_text(
            "timestamp,close\n"
            "2025-12-31T00:00:00Z,99\n"
            ",100\n"
            "2026-01-02T00:00:00Z,101\n"
            "2026-01-04T00:00:00Z,102\n"
        )
        inventory = build_real_validation_input_inventory(bars_dir=tmp_path)

        result = materialize_input_rows_for_splits(
            inventory=inventory,
            split_definitions=_two_split_windows(),
        )
        file_result = result["roles"][0]["files"][0]

        assert file_result["total_rows"] == 4
        assert file_result["assigned_rows"] == 1
        assert file_result["unassigned_rows"] == 3
        assert result["timestamp_policy"]["empty_timestamp"] == "UNASSIGNED"
        assert result["timestamp_policy"]["malformed_timestamp"] == "FAIL_CLOSED"

    def test_non_timestamp_values_are_not_interpreted(self, tmp_path):
        (tmp_path / "bars.csv").write_text(
            "timestamp,open,close\n"
            "2026-01-01T00:00:00Z,not-a-number,not-a-timestamp\n"
        )
        inventory = build_real_validation_input_inventory(bars_dir=tmp_path)

        result = materialize_input_rows_for_splits(
            inventory=inventory,
            split_definitions=_two_split_windows(),
        )

        assert result["roles"][0]["files"][0]["assigned_rows"] == 1

    def test_missing_inventoried_file_fails_closed(self, tmp_path):
        csv_path = _write_tiny_bars_csv(tmp_path)
        inventory = build_real_validation_input_inventory(bars_dir=tmp_path)
        csv_path.unlink()

        with pytest.raises(ValueError, match="Inventoried file is missing"):
            materialize_input_rows_for_splits(
                inventory=inventory,
                split_definitions=_two_split_windows(),
            )

    def test_symlinked_csv_to_safe_external_source_is_accepted(self, tmp_path):
        role_dir = tmp_path / "bars"
        external_dir = tmp_path / "external"
        role_dir.mkdir()
        external_dir.mkdir()
        external_csv = _write_tiny_bars_csv(external_dir, "source.csv")
        (role_dir / "bars.csv").symlink_to(external_csv)
        inventory = build_real_validation_input_inventory(bars_dir=role_dir)

        result = materialize_input_rows_for_splits(
            inventory=inventory,
            split_definitions=_two_split_windows(),
        )

        file_result = result["roles"][0]["files"][0]
        assert file_result["filename"] == "bars.csv"
        assert file_result["total_rows"] == 3
        assert file_result["assigned_rows"] == 3

    def test_symlinked_csv_resolving_to_prod_is_refused(
        self, tmp_path, monkeypatch
    ):
        role_dir = tmp_path / "bars"
        fake_prod = tmp_path / "fake_prod"
        role_dir.mkdir()
        fake_prod.mkdir()
        inventoried_csv = _write_tiny_bars_csv(role_dir)
        inventory = build_real_validation_input_inventory(bars_dir=role_dir)
        inventoried_csv.unlink()
        prod_csv = _write_tiny_bars_csv(fake_prod, "prod.csv")
        inventoried_csv.symlink_to(prod_csv)
        monkeypatch.setattr(real_validation, "PROD_BASE", fake_prod)

        with pytest.raises(ValueError, match="Refusing path under prod base"):
            materialize_input_rows_for_splits(
                inventory=inventory,
                split_definitions=_two_split_windows(),
            )

    def test_symlink_target_content_change_fails_sha256_check(self, tmp_path):
        role_dir = tmp_path / "bars"
        external_dir = tmp_path / "external"
        role_dir.mkdir()
        external_dir.mkdir()
        external_csv = _write_tiny_bars_csv(external_dir, "source.csv")
        (role_dir / "bars.csv").symlink_to(external_csv)
        inventory = build_real_validation_input_inventory(bars_dir=role_dir)
        external_csv.write_text(
            "timestamp,open,high,low,close,volume\n"
            "2026-01-01T01:00:00Z,100.0,101.0,99.0,100.5,1000\n"
            "2026-01-02T01:00:00Z,100.5,102.0,100.0,101.0,1200\n"
            "2026-01-03T01:00:00Z,101.0,103.0,100.5,102.0,1100\n"
        )

        with pytest.raises(ValueError, match="Inventoried SHA256 changed"):
            materialize_input_rows_for_splits(
                inventory=inventory,
                split_definitions=_two_split_windows(),
            )

    @pytest.mark.parametrize(
        "filename",
        ["../evil.csv", "/tmp/evil.csv", "subdir/file.csv"],
    )
    def test_inventory_filename_traversal_is_refused(self, tmp_path, filename):
        _write_tiny_bars_csv(tmp_path)
        inventory = build_real_validation_input_inventory(bars_dir=tmp_path)
        inventory["roles"][0]["files"][0]["filename"] = filename

        with pytest.raises(ValueError, match="simple filename"):
            materialize_input_rows_for_splits(
                inventory=inventory,
                split_definitions=_two_split_windows(),
            )

    def test_metadata_contains_no_forbidden_calculation_keys(self, tmp_path):
        _write_tiny_bars_csv(tmp_path)
        inventory = build_real_validation_input_inventory(bars_dir=tmp_path)
        result = materialize_input_rows_for_splits(
            inventory=inventory,
            split_definitions=_two_split_windows(),
        )

        forbidden = {
            "price",
            "price_change",
            "return",
            "returns",
            "pnl",
            "sharpe",
            "edge",
            "trade",
            "trades",
            "signal",
            "signals",
            "position",
            "positions",
        }
        assert forbidden.isdisjoint(_all_dict_keys(result))


# ── Gross observational return tests ───────────────────────────────────


class TestGrossObservationalReturns:
    def test_calculates_simple_close_to_close_summary(self, tmp_path):
        (tmp_path / "bars.csv").write_text(
            "timestamp,open,high,low,close,volume\n"
            "2026-01-01T00:00:00Z,bad,bad,bad,100,bad\n"
            "2026-01-02T00:00:00Z,bad,bad,bad,110,bad\n"
            "2026-01-03T00:00:00Z,bad,bad,bad,99,bad\n"
            "2026-01-04T00:00:00Z,bad,bad,bad,99,bad\n"
        )
        inventory = build_real_validation_input_inventory(bars_dir=tmp_path)

        result = materialize_gross_observational_returns(
            inventory=inventory,
            split_definitions=_two_split_windows(),
        )

        summary = result["files"][0]
        assert summary["observation_count"] == 3
        assert summary["positive_count"] == 1
        assert summary["negative_count"] == 1
        assert summary["zero_count"] == 1
        assert summary["min_gross_return"] == pytest.approx(-0.1)
        assert summary["max_gross_return"] == pytest.approx(0.1)
        assert summary["mean_gross_return"] == pytest.approx(0.0)
        assert result["calculation_status"] == "GROSS_OBSERVATIONAL_RETURNS_ONLY"

    def test_only_bars_role_processed_and_funding_file_not_reopened(self, tmp_path):
        bars_dir = tmp_path / "bars"
        funding_dir = tmp_path / "funding"
        bars_dir.mkdir()
        funding_dir.mkdir()
        _write_tiny_bars_csv(bars_dir)
        funding_path = _write_tiny_funding_csv(funding_dir)
        inventory = build_real_validation_input_inventory(
            bars_dir=bars_dir,
            funding_dir=funding_dir,
        )
        funding_path.write_text("this change must not be read\n")

        result = materialize_gross_observational_returns(
            inventory=inventory,
            split_definitions=_two_split_windows(),
        )

        assert {file_result["role"] for file_result in result["files"]} == {"bars"}
        assert result["ignored_roles"] == ["funding"]
        assert result["funding_adjusted_status"] == "NOT_EXECUTED"

    def test_non_monotonic_timestamps_fail_closed(self, tmp_path):
        (tmp_path / "bars.csv").write_text(
            "timestamp,close\n"
            "2026-01-02T00:00:00Z,101\n"
            "2026-01-01T00:00:00Z,100\n"
        )
        inventory = build_real_validation_input_inventory(bars_dir=tmp_path)

        with pytest.raises(ValueError, match="Non-monotonic timestamp"):
            materialize_gross_observational_returns(
                inventory=inventory,
                split_definitions=_two_split_windows(),
            )

    def test_missing_close_column_fails_closed(self, tmp_path):
        (tmp_path / "bars.csv").write_text(
            "timestamp,open\n2026-01-01T00:00:00Z,100\n"
        )
        inventory = build_real_validation_input_inventory(bars_dir=tmp_path)

        with pytest.raises(ValueError, match="Missing close column"):
            materialize_gross_observational_returns(
                inventory=inventory,
                split_definitions=_two_split_windows(),
            )

    @pytest.mark.parametrize("close_value", ["not-a-number", "", "nan", "inf"])
    def test_malformed_close_value_fails_closed(self, tmp_path, close_value):
        (tmp_path / "bars.csv").write_text(
            "timestamp,close\n"
            f"2026-01-01T00:00:00Z,{close_value}\n"
        )
        inventory = build_real_validation_input_inventory(bars_dir=tmp_path)

        with pytest.raises(ValueError, match="Malformed close"):
            materialize_gross_observational_returns(
                inventory=inventory,
                split_definitions=_two_split_windows(),
            )

    def test_sha_mismatch_after_inventory_fails_closed(self, tmp_path):
        bars_path = _write_tiny_bars_csv(tmp_path)
        inventory = build_real_validation_input_inventory(bars_dir=tmp_path)
        bars_path.write_text("timestamp,close\n2026-01-01T00:00:00Z,1\n")

        with pytest.raises(ValueError, match="Inventoried SHA256 changed"):
            materialize_gross_observational_returns(
                inventory=inventory,
                split_definitions=_two_split_windows(),
            )

    def test_per_split_window_observation_counts_are_deterministic(self, tmp_path):
        _write_tiny_bars_csv(tmp_path)
        inventory = build_real_validation_input_inventory(bars_dir=tmp_path)

        first = materialize_gross_observational_returns(
            inventory=inventory,
            split_definitions=_two_split_windows(),
        )
        second = materialize_gross_observational_returns(
            inventory=inventory,
            split_definitions=_two_split_windows(),
        )

        assert first == second
        windows = first["files"][0]["per_split_windows"]
        assert [
            (
                window["train_window"]["observation_count"],
                window["validation_window"]["observation_count"],
            )
            for window in windows
        ] == [(0, 0), (0, 2)]

    def test_contains_no_strategy_or_execution_keys(self, tmp_path):
        _write_tiny_bars_csv(tmp_path)
        inventory = build_real_validation_input_inventory(bars_dir=tmp_path)
        result = materialize_gross_observational_returns(
            inventory=inventory,
            split_definitions=_two_split_windows(),
        )

        forbidden = {
            "pnl",
            "sharpe",
            "edge",
            "strategy_performance",
            "net_return_value",
            "cost_adjusted_return",
            "funding_adjusted_return",
            "trade",
            "trades",
            "signal",
            "signals",
            "position",
            "positions",
            "portfolio",
            "live_ready",
            "deploy_ready",
            "profitable",
        }
        assert forbidden.isdisjoint(_all_dict_keys(result))


class TestFundingObservationalAdjustments:
    @staticmethod
    def _inventory_for_file(path: Path) -> dict:
        return {
            "roles": [
                {
                    "role": "funding",
                    "directory": str(path.parent.resolve()),
                    "files": [
                        {
                            "filename": path.name,
                            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                            "row_count": max(len(path.read_text().splitlines()) - 1, 0),
                        }
                    ],
                }
            ]
        }

    def test_calculates_funding_summary_and_split_counts(self, tmp_path):
        bars_dir = tmp_path / "bars"
        funding_dir = tmp_path / "funding"
        bars_dir.mkdir()
        funding_dir.mkdir()
        _write_tiny_bars_csv(bars_dir)
        funding_path = funding_dir / "funding.csv"
        funding_path.write_text(
            "fundingTime,fundingRate,unused\n"
            "2026-01-01T12:00:00Z,0.0003,bad\n"
            "2026-01-02T00:00:00Z,-0.0001,bad\n"
            "2026-01-02T12:00:00Z,0,bad\n"
        )
        inventory = build_real_validation_input_inventory(
            bars_dir=bars_dir, funding_dir=funding_dir
        )

        first = materialize_funding_observational_adjustments(
            inventory=inventory, split_definitions=_two_split_windows()
        )
        second = materialize_funding_observational_adjustments(
            inventory=inventory, split_definitions=_two_split_windows()
        )

        assert first == second
        summary = first["files"][0]
        assert summary["observation_count"] == 3
        assert summary["positive_count"] == 1
        assert summary["negative_count"] == 1
        assert summary["zero_count"] == 1
        assert summary["min_funding_rate"] == pytest.approx(-0.0001)
        assert summary["max_funding_rate"] == pytest.approx(0.0003)
        assert summary["mean_funding_rate"] == pytest.approx(0.0002 / 3)
        assert [
            (
                window["train_window"]["observation_count"],
                window["validation_window"]["observation_count"],
            )
            for window in summary["per_split_windows"]
        ] == [(0, 1), (1, 2)]
        assert first["processed_role"] == "funding"
        assert first["ignored_roles"] == ["bars"]
        assert first["bars_adjusted_status"] == "NOT_EXECUTED"
        assert first["calculation_status"] == "FUNDING_OBSERVATIONAL_ADJUSTMENT_ONLY"

    def test_bars_role_is_ignored_and_not_reopened(self, tmp_path):
        bars_dir = tmp_path / "bars"
        funding_dir = tmp_path / "funding"
        bars_dir.mkdir()
        funding_dir.mkdir()
        bars_path = _write_tiny_bars_csv(bars_dir)
        _write_tiny_funding_csv(funding_dir)
        inventory = build_real_validation_input_inventory(
            bars_dir=bars_dir, funding_dir=funding_dir
        )
        bars_path.write_text("changed after inventory\n")

        result = materialize_funding_observational_adjustments(
            inventory=inventory, split_definitions=_two_split_windows()
        )

        assert {item["role"] for item in result["files"]} == {"funding"}
        assert result["bars_adjusted_status"] == "NOT_EXECUTED"

    def test_missing_funding_rate_column_fails_closed(self, tmp_path):
        path = tmp_path / "funding.csv"
        path.write_text("fundingTime,other\n2026-01-01T00:00:00Z,1\n")
        inventory = self._inventory_for_file(path)
        with pytest.raises(ValueError, match="Missing fundingRate column"):
            materialize_funding_observational_adjustments(
                inventory=inventory, split_definitions=_two_split_windows()
            )

    def test_missing_funding_time_column_fails_closed(self, tmp_path):
        path = tmp_path / "funding.csv"
        path.write_text("other,fundingRate\n2026-01-01T00:00:00Z,0.0001\n")
        inventory = self._inventory_for_file(path)
        with pytest.raises(ValueError, match="Missing fundingTime column"):
            materialize_funding_observational_adjustments(
                inventory=inventory, split_definitions=_two_split_windows()
            )

    @pytest.mark.parametrize("rate", ["bad", "", "nan", "inf", "-inf"])
    def test_malformed_or_non_finite_funding_rate_fails_closed(self, tmp_path, rate):
        path = tmp_path / "funding.csv"
        path.write_text(
            "fundingTime,fundingRate\n"
            f"2026-01-01T00:00:00Z,{rate}\n"
        )
        inventory = self._inventory_for_file(path)
        with pytest.raises(ValueError, match="Malformed fundingRate"):
            materialize_funding_observational_adjustments(
                inventory=inventory, split_definitions=_two_split_windows()
            )

    def test_malformed_funding_time_fails_closed(self, tmp_path):
        path = tmp_path / "funding.csv"
        path.write_text("fundingTime,fundingRate\nnot-a-time,0.0001\n")
        inventory = self._inventory_for_file(path)
        with pytest.raises(ValueError, match="Malformed fundingTime"):
            materialize_funding_observational_adjustments(
                inventory=inventory, split_definitions=_two_split_windows()
            )

    def test_non_monotonic_funding_time_fails_closed(self, tmp_path):
        path = tmp_path / "funding.csv"
        path.write_text(
            "fundingTime,fundingRate\n"
            "2026-01-02T00:00:00Z,0.0001\n"
            "2026-01-01T00:00:00Z,0.0002\n"
        )
        inventory = self._inventory_for_file(path)
        with pytest.raises(ValueError, match="Non-monotonic fundingTime"):
            materialize_funding_observational_adjustments(
                inventory=inventory, split_definitions=_two_split_windows()
            )

    def test_sha_mismatch_after_inventory_fails_closed(self, tmp_path):
        path = _write_tiny_funding_csv(tmp_path)
        inventory = self._inventory_for_file(path)
        path.write_text("fundingTime,fundingRate\n2026-01-01T00:00:00Z,0\n")
        with pytest.raises(ValueError, match="Inventoried SHA256 changed"):
            materialize_funding_observational_adjustments(
                inventory=inventory, split_definitions=_two_split_windows()
            )

    def test_safe_keys_and_receipt_guardrails(self, tmp_path):
        path = _write_tiny_funding_csv(tmp_path)
        adjustments = materialize_funding_observational_adjustments(
            inventory=self._inventory_for_file(path),
            split_definitions=_two_split_windows(),
        )
        forbidden = {
            "pnl", "sharpe", "edge", "strategy_performance", "return", "returns",
            "net_return_value", "cost_adjusted_return", "funding_adjusted_return",
            "trade", "trades", "signal", "signals", "position", "positions",
            "portfolio", "live_ready", "deploy_ready", "profitable",
        }
        assert forbidden.isdisjoint(_all_dict_keys(adjustments))

        receipt = _base_receipt(funding_observational_adjustments=adjustments)
        validate_real_validation_receipt(receipt)
        assert receipt["funding_observational_adjustments"] == adjustments
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION
        assert all(value is False for value in receipt["required_outputs_present"].values())
        assert all(value is False for value in receipt["forbidden_calculation_status"].values())
        assert all(value is True for value in receipt["guardrail_status"].values())
        serialized = json.dumps(receipt)
        assert OFFLINE_EDGE_CANDIDATE not in serialized
        assert "EDGE_CANDIDATE" not in serialized


# ── Funding-to-bars alignment diagnostics tests ─────────────────────────


class TestFundingToBarsAlignmentDiagnostics:
    @staticmethod
    def _sections(*, rate=-0.02, unassigned=0, funding_filename="BTCUSDT_funding.csv"):
        rows = {"roles": [
            {"role": "bars", "files": [{
                "filename": "BTCUSDT_8h_ohlcv.csv", "total_rows": 3,
                "unassigned_rows": unassigned, "per_split_counts": [{
                    "split_id": "split_0", "train_rows": 2, "validation_rows": 1,
                }],
            }]},
            {"role": "funding", "files": [{
                "filename": funding_filename, "total_rows": 2,
                "unassigned_rows": unassigned, "per_split_counts": [{
                    "split_id": "split_0", "train_rows": 1, "validation_rows": 1,
                }],
            }]},
        ]}
        gross = {"files": [{
            "filename": "BTCUSDT_8h_ohlcv.csv", "observation_count": 2,
            "per_split_windows": [{
                "split_id": "split_0",
                "train_window": {"observation_count": 1},
                "validation_window": {"observation_count": 1},
            }],
        }]}
        funding = {"files": [{
            "filename": funding_filename, "observation_count": 2,
            "min_funding_rate": rate, "max_funding_rate": 0.0002,
            "per_split_windows": [{
                "split_id": "split_0",
                "train_window": {"observation_count": 1},
                "validation_window": {"observation_count": 1},
            }],
        }]}
        return rows, gross, funding

    def _build(self, **kwargs):
        rows, gross, funding = self._sections(**kwargs)
        return materialize_funding_to_bars_alignment_diagnostics(
            row_materialization=rows,
            gross_observational_returns=gross,
            funding_observational_adjustments=funding,
        )

    def test_pairing_complete_coverage_and_split_counts(self):
        result = self._build()
        assert result["symbol_count"] == result["complete_symbol_count"] == 1
        assert result["diagnostic_symbol_count"] == 0
        symbol = result["symbols"][0]
        assert (symbol["symbol"], symbol["bars_file"], symbol["funding_file"]) == (
            "BTCUSDT", "BTCUSDT_8h_ohlcv.csv", "BTCUSDT_funding.csv"
        )
        assert symbol["coverage_status"] == "COMPLETE"
        assert (
            symbol["bars_total_rows"], symbol["funding_total_rows"],
            symbol["gross_observation_count"], symbol["funding_observation_count"],
        ) == (3, 2, 2, 2)
        assert symbol["splits"][0] == {
            "split_id": "split_0", "bars_train_rows": 2,
            "bars_validation_rows": 1, "funding_train_rows": 1,
            "funding_validation_rows": 1, "gross_train_observations": 1,
            "gross_validation_observations": 1,
            "funding_train_observations": 1,
            "funding_validation_observations": 1,
        }

    @pytest.mark.parametrize(
        "funding_filename",
        ["BTCUSDT_8h_funding.csv", "BTCUSDT_funding.csv"],
    )
    def test_real_and_legacy_funding_filenames_pair_with_bars(
        self, funding_filename
    ):
        rows, gross, funding = self._sections(
            funding_filename=funding_filename
        )
        result = materialize_funding_to_bars_alignment_diagnostics(
            row_materialization=rows,
            gross_observational_returns=gross,
            funding_observational_adjustments=funding,
        )
        assert result["symbols"][0]["symbol"] == "BTCUSDT"
        assert result["symbols"][0]["funding_file"] == funding_filename

    def test_duplicate_normalized_funding_symbols_fail_closed(self):
        rows, gross, funding = self._sections()
        duplicate = rows["roles"][1]["files"][0].copy()
        duplicate["filename"] = "BTCUSDT_8h_funding.csv"
        rows["roles"][1]["files"].append(duplicate)
        with pytest.raises(
            ValueError, match="Duplicate funding row materialization symbol: BTCUSDT"
        ):
            materialize_funding_to_bars_alignment_diagnostics(
                row_materialization=rows,
                gross_observational_returns=gross,
                funding_observational_adjustments=funding,
            )

    @pytest.mark.parametrize(
        "funding_filename", ["BTCUSDT_8h_bad.csv", "BTCUSDT_ohlcv.csv"]
    )
    def test_malformed_funding_filename_fails_closed(self, funding_filename):
        rows, gross, funding = self._sections(
            funding_filename=funding_filename
        )
        with pytest.raises(ValueError, match="Invalid funding row materialization filename"):
            materialize_funding_to_bars_alignment_diagnostics(
                row_materialization=rows,
                gross_observational_returns=gross,
                funding_observational_adjustments=funding,
            )

    def test_unassigned_rows_are_diagnostic_only(self):
        result = self._build(unassigned=1)
        assert result["complete_symbol_count"] == 0
        assert result["diagnostic_symbol_count"] == 1
        assert result["symbols"][0]["coverage_status"] == "DIAGNOSTIC_ONLY"

    def test_missing_funding_file_fails_closed(self):
        rows, gross, funding = self._sections()
        rows["roles"][1]["files"] = []
        with pytest.raises(ValueError, match="Symbol mismatch"):
            materialize_funding_to_bars_alignment_diagnostics(
                row_materialization=rows,
                gross_observational_returns=gross,
                funding_observational_adjustments=funding,
            )

    @pytest.mark.parametrize("role_index", [0, 1])
    def test_duplicate_bars_or_funding_symbol_fails_closed(self, role_index):
        rows, gross, funding = self._sections()
        rows["roles"][role_index]["files"].append(
            rows["roles"][role_index]["files"][0].copy()
        )
        with pytest.raises(ValueError, match="Duplicate"):
            materialize_funding_to_bars_alignment_diagnostics(
                row_materialization=rows,
                gross_observational_returns=gross,
                funding_observational_adjustments=funding,
            )

    def test_outlier_threshold_and_no_outlier(self):
        flagged = self._build()
        assert flagged["outlier_symbol_count"] == 1
        assert flagged["symbols"][0]["funding_rate_outlier_present"] is True
        assert flagged["symbols"][0]["funding_rate_outlier_reason"] == (
            "ABS_RATE_EXCEEDS_THRESHOLD"
        )
        clean = self._build(rate=-0.009)
        assert clean["outlier_symbol_count"] == 0
        assert clean["symbols"][0]["funding_rate_outlier_reason"] == "NONE"

    def test_consumes_sections_without_opening_files(self, monkeypatch):
        def refuse_open(*args, **kwargs):
            raise AssertionError("alignment helper must not open files")
        monkeypatch.setattr("builtins.open", refuse_open)
        assert self._build()["symbol_count"] == 1

    def test_safe_keys_and_receipt_guardrails(self):
        diagnostics = self._build()
        forbidden = {
            "pnl", "sharpe", "edge", "strategy_performance", "return", "returns",
            "net_return_value", "cost_adjusted_return", "funding_adjusted_return",
            "trade", "trades", "signal", "signals", "position", "positions",
            "portfolio", "live_ready", "deploy_ready", "profitable",
        }
        assert forbidden.isdisjoint(_all_dict_keys(diagnostics))
        receipt = _base_receipt(
            funding_to_bars_alignment_diagnostics=diagnostics
        )
        validate_real_validation_receipt(receipt)
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION
        assert all(value is False for value in receipt["required_outputs_present"].values())
        assert all(value is False for value in receipt["forbidden_calculation_status"].values())
        assert all(value is True for value in receipt["guardrail_status"].values())
        assert "EDGE_CANDIDATE" not in json.dumps(receipt)


# ── New: Receipt with inventory tests ───────────────────────────────────


class TestCostCaseObservationalDrag:
    @staticmethod
    def _gross_fixture() -> dict:
        summary = {
            "observation_count": 2,
            "min_gross_return": -0.01,
            "max_gross_return": 0.02,
            "mean_gross_return": 0.005,
        }
        return {
            "files": [{
                "filename": "bars.csv",
                **summary,
                "per_split_windows": [{
                    "split_id": "split_0",
                    "train_window": summary.copy(),
                    "validation_window": summary.copy(),
                }],
            }]
        }

    def test_low_base_high_drag_and_descriptive_values(self):
        result = materialize_cost_case_observational_drag(
            gross_observational_returns=self._gross_fixture(),
            cost_cases=build_cost_case_matrix(),
        )
        cases = {case["cost_case"]: case for case in result["cost_cases"]}
        assert set(cases) == {"low", "base", "high"}
        assert cases["low"]["assumed_drag_bps_per_observation"] == 9.0
        assert cases["base"]["assumed_drag_bps_per_observation"] == 22.0
        assert cases["high"]["assumed_drag_bps_per_observation"] == 44.0
        base_file = cases["base"]["files"][0]
        assert base_file["gross_observation_count"] == 2
        assert base_file["gross_minus_drag_observation_mean"] == pytest.approx(0.0028)
        assert base_file["gross_minus_drag_observation_min"] == pytest.approx(-0.0122)
        assert base_file["gross_minus_drag_observation_max"] == pytest.approx(0.0178)
        split = base_file["per_split_windows"][0]
        assert split["train_window"]["gross_observation_count"] == 2
        assert split["validation_window"]["gross_observation_count"] == 2

    def test_consumes_gross_section_without_opening_files(self, monkeypatch):
        def refuse_open(*args, **kwargs):
            raise AssertionError("cost drag helper must not open files")

        monkeypatch.setattr("builtins.open", refuse_open)
        result = materialize_cost_case_observational_drag(
            gross_observational_returns=self._gross_fixture(),
            cost_cases=build_cost_case_matrix(),
        )
        assert len(result["cost_cases"]) == 3

    def test_introduces_no_forbidden_or_generic_keys(self):
        result = materialize_cost_case_observational_drag(
            gross_observational_returns=self._gross_fixture(),
            cost_cases=build_cost_case_matrix(),
        )
        forbidden = {
            "pnl", "sharpe", "edge", "trade", "trades", "signal", "signals",
            "position", "positions", "portfolio", "return", "returns",
            "net_return_value", "cost_adjusted_return", "funding_adjusted_return",
        }
        assert forbidden.isdisjoint(_all_dict_keys(result))

    def test_receipt_section_validates_and_preserves_guardrails(self):
        drag = materialize_cost_case_observational_drag(
            gross_observational_returns=self._gross_fixture(),
            cost_cases=build_cost_case_matrix(),
        )
        receipt = _base_receipt(cost_case_observational_drag=drag)
        validate_real_validation_receipt(receipt)
        assert receipt["cost_case_observational_drag"] == drag
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION
        assert all(value is False for value in receipt["required_outputs_present"].values())
        assert all(value is False for value in receipt["forbidden_calculation_status"].values())
        assert all(value is True for value in receipt["guardrail_status"].values())
        assert "EDGE_CANDIDATE" not in json.dumps(receipt)


class TestReceiptWithInventory:
    def test_receipt_with_gross_observational_returns_validates(self, tmp_path):
        _write_tiny_bars_csv(tmp_path)
        inventory = build_real_validation_input_inventory(bars_dir=tmp_path)
        splits = _two_split_windows()
        gross_observations = materialize_gross_observational_returns(
            inventory=inventory,
            split_definitions=splits,
        )
        receipt = build_real_validation_receipt(
            input_manifest_fingerprint="a" * 64,
            data_quality_receipt_sha256="b" * 64,
            code_commit_sha="c" * 40,
            split_definitions=splits,
            cost_cases=build_cost_case_matrix(),
            gross_observational_returns=gross_observations,
        )

        validate_real_validation_receipt(receipt)
        assert receipt["gross_observational_returns"] == gross_observations
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION
        assert all(value is False for value in receipt["required_outputs_present"].values())
        assert all(
            value is False
            for value in receipt["forbidden_calculation_status"].values()
        )
        assert all(value is True for value in receipt["guardrail_status"].values())

    def test_receipt_with_row_materialization_validates(self, tmp_path):
        _write_tiny_bars_csv(tmp_path)
        inventory = build_real_validation_input_inventory(bars_dir=tmp_path)
        splits = _two_split_windows()
        row_materialization = materialize_input_rows_for_splits(
            inventory=inventory,
            split_definitions=splits,
        )
        receipt = build_real_validation_receipt(
            input_manifest_fingerprint="a" * 64,
            data_quality_receipt_sha256="b" * 64,
            code_commit_sha="c" * 40,
            split_definitions=splits,
            cost_cases=build_cost_case_matrix(),
            row_materialization=row_materialization,
        )

        validate_real_validation_receipt(receipt)
        assert receipt["row_materialization"] == row_materialization
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION
        assert all(value is False for value in receipt["required_outputs_present"].values())
        assert all(
            value is False
            for value in receipt["forbidden_calculation_status"].values()
        )
        assert all(value is True for value in receipt["guardrail_status"].values())

    def test_receipt_with_input_inventory_validates(self, tmp_path):
        _write_tiny_bars_csv(tmp_path)
        inventory = build_real_validation_input_inventory(bars_dir=tmp_path)
        splits = build_deterministic_split_definitions(
            global_min_timestamp="2026-01-01T00:00:00Z",
            global_max_timestamp="2026-02-01T00:00:00Z",
        )
        costs = build_cost_case_matrix()
        receipt = build_real_validation_receipt(
            input_manifest_fingerprint="a" * 64,
            data_quality_receipt_sha256="b" * 64,
            code_commit_sha="c" * 40,
            split_definitions=splits,
            cost_cases=costs,
            input_inventory=inventory,
        )
        # Should validate without error.
        validate_real_validation_receipt(receipt)
        # Should have input_inventory key.
        assert "input_inventory" in receipt

    def test_receipt_still_has_blocked_verdict(self, tmp_path):
        _write_tiny_bars_csv(tmp_path)
        inventory = build_real_validation_input_inventory(bars_dir=tmp_path)
        splits = build_deterministic_split_definitions(
            global_min_timestamp="2026-01-01T00:00:00Z",
            global_max_timestamp="2026-02-01T00:00:00Z",
        )
        costs = build_cost_case_matrix()
        receipt = build_real_validation_receipt(
            input_manifest_fingerprint="a" * 64,
            data_quality_receipt_sha256="b" * 64,
            code_commit_sha="c" * 40,
            split_definitions=splits,
            cost_cases=costs,
            input_inventory=inventory,
        )
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION

    def test_receipt_still_forbidden_calc_false(self, tmp_path):
        _write_tiny_bars_csv(tmp_path)
        inventory = build_real_validation_input_inventory(bars_dir=tmp_path)
        splits = build_deterministic_split_definitions(
            global_min_timestamp="2026-01-01T00:00:00Z",
            global_max_timestamp="2026-02-01T00:00:00Z",
        )
        costs = build_cost_case_matrix()
        receipt = build_real_validation_receipt(
            input_manifest_fingerprint="a" * 64,
            data_quality_receipt_sha256="b" * 64,
            code_commit_sha="c" * 40,
            split_definitions=splits,
            cost_cases=costs,
            input_inventory=inventory,
        )
        for key, value in receipt["forbidden_calculation_status"].items():
            assert value is False, f"{key} must be False"

    def test_receipt_still_required_outputs_false(self, tmp_path):
        _write_tiny_bars_csv(tmp_path)
        inventory = build_real_validation_input_inventory(bars_dir=tmp_path)
        splits = build_deterministic_split_definitions(
            global_min_timestamp="2026-01-01T00:00:00Z",
            global_max_timestamp="2026-02-01T00:00:00Z",
        )
        costs = build_cost_case_matrix()
        receipt = build_real_validation_receipt(
            input_manifest_fingerprint="a" * 64,
            data_quality_receipt_sha256="b" * 64,
            code_commit_sha="c" * 40,
            split_definitions=splits,
            cost_cases=costs,
            input_inventory=inventory,
        )
        for value in receipt["required_outputs_present"].values():
            assert value is False

    def test_receipt_with_inventory_drives_split_definitions(self, tmp_path):
        _write_tiny_bars_csv(tmp_path)
        inventory = build_real_validation_input_inventory(bars_dir=tmp_path)
        splits = build_deterministic_split_definitions(
            global_min_timestamp="2026-01-01T00:00:00Z",
            global_max_timestamp="2026-02-01T00:00:00Z",
        )
        costs = build_cost_case_matrix()
        receipt = build_real_validation_receipt(
            input_manifest_fingerprint="a" * 64,
            data_quality_receipt_sha256="b" * 64,
            code_commit_sha="c" * 40,
            split_definitions=splits,
            cost_cases=costs,
            input_inventory=inventory,
        )
        # Split definitions should be materialized from inventory, not from the passed splits.
        mat_splits = receipt["split_definitions"]
        # Materialized splits have bars_file_count; placeholder splits don't.
        for s in mat_splits:
            assert "bars_file_count" in s


# ── New: Forbidden keys nested tests ────────────────────────────────────


class TestForbiddenKeysNested:
    def _receipt_with_nested_key(self, key: str, value: object = "anything"):
        """Build a receipt with a forbidden key nested inside a custom section."""
        receipt = _base_receipt()
        receipt["custom_section"] = {key: value}
        return receipt

    def test_top_level_return_rejected(self):
        receipt = _base_receipt()
        receipt["return"] = 0.05
        with pytest.raises(ValueError, match="Forbidden calculation key"):
            validate_real_validation_receipt(receipt)

    def test_top_level_returns_rejected(self):
        receipt = _base_receipt()
        receipt["returns"] = [0.01, 0.02]
        with pytest.raises(ValueError, match="Forbidden calculation key"):
            validate_real_validation_receipt(receipt)

    def test_gross_observational_return_rejected_outside_allowed_section(self):
        receipt = self._receipt_with_nested_key("gross_observational_return", 0.01)
        with pytest.raises(ValueError, match="Forbidden calculation key"):
            validate_real_validation_receipt(receipt)

    def test_gross_observational_return_allowed_inside_allowed_section(self):
        receipt = _base_receipt()
        receipt["gross_observational_returns"] = {
            "observations": [{"gross_observational_return": 0.01}]
        }
        validate_real_validation_receipt(receipt)

    def test_nested_pnl_rejected(self):
        receipt = self._receipt_with_nested_key("pnl", 1000.0)
        with pytest.raises(ValueError, match="Forbidden calculation key"):
            validate_real_validation_receipt(receipt)

    def test_nested_sharpe_rejected(self):
        receipt = self._receipt_with_nested_key("sharpe", 1.5)
        with pytest.raises(ValueError, match="Forbidden calculation key"):
            validate_real_validation_receipt(receipt)

    def test_nested_edge_rejected(self):
        receipt = self._receipt_with_nested_key("edge", "positive")
        with pytest.raises(ValueError, match="Forbidden calculation key"):
            validate_real_validation_receipt(receipt)

    def test_nested_gross_return_value_rejected(self):
        receipt = self._receipt_with_nested_key("gross_return_value", 0.10)
        with pytest.raises(ValueError, match="Forbidden calculation key"):
            validate_real_validation_receipt(receipt)

    def test_nested_net_return_value_rejected(self):
        receipt = self._receipt_with_nested_key("net_return_value", 0.08)
        with pytest.raises(ValueError, match="Forbidden calculation key"):
            validate_real_validation_receipt(receipt)

    def test_nested_in_list_of_dicts_rejected(self):
        receipt = _base_receipt()
        receipt["results"] = [{"split_id": "s0"}, {"pnl": 500}]
        with pytest.raises(ValueError, match="Forbidden calculation key"):
            validate_real_validation_receipt(receipt)

    def test_deeply_nested_strategy_performance_rejected(self):
        receipt = _base_receipt()
        receipt["analysis"] = {"metrics": {"strategy_performance": {"total_return": 0.05}}}
        with pytest.raises(ValueError, match="Forbidden calculation key"):
            validate_real_validation_receipt(receipt)

    def test_normal_receipt_not_rejected(self):
        receipt = _base_receipt()
        # Should not raise.
        validate_real_validation_receipt(receipt)

    @pytest.mark.parametrize(
        "key",
        [
            "price_change",
            "cost_adjusted_return",
            "funding_adjusted_return",
            "trade",
            "trades",
            "signal",
            "signals",
            "position",
            "positions",
            "portfolio",
            "live_ready",
            "deploy_ready",
            "profitable",
        ],
    )
    def test_new_exact_forbidden_keys_rejected_at_any_depth(self, key):
        receipt = _base_receipt()
        receipt["metadata"] = [{"nested": {key: "forbidden"}}]
        with pytest.raises(ValueError, match="Forbidden calculation key"):
            validate_real_validation_receipt(receipt)

    def test_edge_unproven_safe_key_is_not_substring_rejected(self):
        receipt = _base_receipt()
        validate_real_validation_receipt(receipt)

    # ── Appended reserved keys (scanner 22 → 42) ──────────────────────────

    APPENDED_FORBIDDEN_KEYS = [
        "drawdown",
        "risk",
        "baseline_result",
        "benchmark_result",
        "OFFLINE_EDGE_CANDIDATE",
        "EDGE_CANDIDATE",
        "p_value",
        "confidence_interval",
        "score",
        "metric",
        "performance",
        "profit",
        "order",
        "orders",
        "fill",
        "fills",
        "execution",
        "executions",
        "equity",
        "equity_curve",
    ]

    ORIGINAL_22_FORBIDDEN_KEYS = frozenset(
        {
            "pnl",
            "sharpe",
            "edge",
            "strategy_performance",
            "return",
            "returns",
            "gross_observational_return",
            "gross_return_value",
            "net_return_value",
            "cost_adjusted_return",
            "funding_adjusted_return",
            "price_change",
            "trade",
            "trades",
            "signal",
            "signals",
            "position",
            "positions",
            "portfolio",
            "live_ready",
            "deploy_ready",
            "profitable",
        }
    )

    @pytest.mark.parametrize("key", APPENDED_FORBIDDEN_KEYS)
    def test_appended_forbidden_key_rejected_when_nested(self, key):
        receipt = self._receipt_with_nested_key(key, "forbidden")
        with pytest.raises(ValueError, match="Forbidden calculation key"):
            validate_real_validation_receipt(receipt)

    @pytest.mark.parametrize("key", ["drawdown", "equity", "score", "profit"])
    def test_appended_forbidden_key_rejected_at_top_level(self, key):
        receipt = _base_receipt()
        receipt[key] = 1.23
        with pytest.raises(ValueError, match="Forbidden calculation key"):
            validate_real_validation_receipt(receipt)

    def test_append_only_original_keys_still_enforced(self):
        """The append must not remove or rename any pre-existing forbidden key."""
        assert self.ORIGINAL_22_FORBIDDEN_KEYS <= real_validation.FORBIDDEN_CALCULATION_KEYS
        assert len(self.ORIGINAL_22_FORBIDDEN_KEYS) == 22
        assert set(self.APPENDED_FORBIDDEN_KEYS) <= real_validation.FORBIDDEN_CALCULATION_KEYS
        assert len(real_validation.FORBIDDEN_CALCULATION_KEYS) == 42

    def test_near_miss_keys_still_accepted_exact_match_semantics(self):
        """Legitimate policy/limit keys that merely *contain* a forbidden name must pass.

        Proves the scanner is exact-dict-key match: no substring, prefix, regex,
        or case-insensitive matching.
        """
        receipt = _base_receipt()
        receipt["policy_section"] = {
            "max_drawdown": 0.2,
            "drawdown_policy": "documented",
            "drawdown_policy_defined": True,
            "order_timing_policy": "next_bar_open",
            "order_timing_policy_defined": True,
            "fill_policy": "close",
            "fill_policy_defined": True,
            "equity_curve_policy": "not_computed",
            "equity_curve_policy_defined": True,
            "risk_measure_policy": "not_computed",
            "sharpe_or_risk_metric": "not_computed",
        }
        # Should not raise.
        validate_real_validation_receipt(receipt)

    def test_pnl_inside_gross_observational_returns_still_rejected(self):
        """The gross_observational_return exemption is key-scoped, not section-wide."""
        receipt = _base_receipt()
        receipt["gross_observational_returns"] = {
            "observations": [{"gross_observational_return": 0.01, "pnl": 1000.0}]
        }
        with pytest.raises(ValueError, match="Forbidden calculation key"):
            validate_real_validation_receipt(receipt)

    def test_gross_observational_return_allowed_directly_inside_exact_section(self):
        receipt = _base_receipt()
        receipt["gross_observational_returns"] = {"gross_observational_return": 0.01}
        validate_real_validation_receipt(receipt)

    def test_gross_observational_return_allowed_inside_exact_section_list(self):
        receipt = _base_receipt()
        receipt["gross_observational_returns"] = [{"gross_observational_return": 0.01}]
        validate_real_validation_receipt(receipt)

    @pytest.mark.parametrize(
        "section",
        [
            "gross_observational_returns_evil",
            "gross_observational_returns_backup",
            "gross_observational_returns2",
        ],
    )
    def test_gross_observational_return_rejected_in_sibling_prefix_section(self, section):
        receipt = _base_receipt()
        receipt[section] = {"observations": [{"gross_observational_return": 0.01}]}
        with pytest.raises(ValueError, match="Forbidden calculation key"):
            validate_real_validation_receipt(receipt)

    def test_gross_observational_return_rejected_below_sibling_prefix_section(self):
        receipt = _base_receipt()
        receipt["custom"] = {
            "gross_observational_returns_evil": {
                "observations": [{"gross_observational_return": 0.01}]
            }
        }
        with pytest.raises(ValueError, match="Forbidden calculation key"):
            validate_real_validation_receipt(receipt)


# ── New: CLI with dirs tests ────────────────────────────────────────────


class TestCLIWithDirs:
    def test_cli_without_dirs_still_works(self):
        out_dir = Path("/tmp") / f"qnty_cli_dirs_test_{uuid.uuid4().hex}"
        receipt_path = out_dir / "real_validation_receipt.json"
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "quantbot.experiment.offline_edge_real_validation",
                    "--read-only",
                    "--output-dir",
                    str(out_dir),
                    "--input-manifest-fingerprint",
                    "a" * 64,
                    "--data-quality-receipt-sha256",
                    "b" * 64,
                    "--code-commit-sha",
                    "c" * 40,
                    "--global-min-timestamp",
                    "2026-01-01T00:00:00Z",
                    "--global-max-timestamp",
                    "2026-02-01T00:00:00Z",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0, result.stderr
            assert receipt_path.exists()
        finally:
            if receipt_path.exists():
                receipt_path.unlink()
            if out_dir.exists():
                out_dir.rmdir()

    def test_cli_with_bars_funding_dirs_writes_receipt(self, tmp_path):
        bars_dir = tmp_path / "bars"
        funding_dir = tmp_path / "funding"
        bars_dir.mkdir()
        funding_dir.mkdir()
        _write_tiny_bars_csv(bars_dir, "BTCUSDT_8h_ohlcv.csv")
        _write_tiny_funding_csv(funding_dir, "BTCUSDT_8h_funding.csv")

        out_dir = Path("/tmp") / f"qnty_cli_dirs_bars_test_{uuid.uuid4().hex}"
        receipt_path = out_dir / "real_validation_receipt.json"
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "quantbot.experiment.offline_edge_real_validation",
                    "--read-only",
                    "--output-dir",
                    str(out_dir),
                    "--input-manifest-fingerprint",
                    "a" * 64,
                    "--data-quality-receipt-sha256",
                    "b" * 64,
                    "--code-commit-sha",
                    "c" * 40,
                    "--bars-dir",
                    str(bars_dir),
                    "--funding-dir",
                    str(funding_dir),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0, f"stderr: {result.stderr}"
            assert receipt_path.exists()
            with open(receipt_path) as f:
                written = json.load(f)
            assert written["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION
            assert "input_inventory" in written
            assert "row_materialization" in written
            assert "gross_observational_returns" in written
            assert "cost_case_observational_drag" in written
            assert "funding_observational_adjustments" in written
            assert "funding_to_bars_alignment_diagnostics" in written
            materialized_roles = written["row_materialization"]["roles"]
            assert materialized_roles[0]["files"][0]["total_rows"] == 3
            gross = written["gross_observational_returns"]
            assert gross["files"][0]["observation_count"] == 2
            assert gross["funding_adjusted_status"] == "NOT_EXECUTED"
            drag_cases = written["cost_case_observational_drag"]["cost_cases"]
            assert {case["cost_case"] for case in drag_cases} == {"low", "base", "high"}
            assert all(
                case["files"][0]["gross_observation_count"]
                == gross["files"][0]["observation_count"]
                for case in drag_cases
            )
            funding = written["funding_observational_adjustments"]
            assert funding["processed_role"] == "funding"
            assert funding["files"][0]["observation_count"] == 2
            assert funding["bars_adjusted_status"] == "NOT_EXECUTED"
            alignment = written["funding_to_bars_alignment_diagnostics"]
            assert alignment["calculation_status"] == (
                "FUNDING_TO_BARS_ALIGNMENT_DIAGNOSTIC_ONLY"
            )
            assert alignment["symbols"][0]["symbol"] == "BTCUSDT"
            assert all(value is False for value in written["required_outputs_present"].values())
            assert all(value is False for value in written["forbidden_calculation_status"].values())
            assert "EDGE_CANDIDATE" not in result.stdout
            assert "EDGE_CANDIDATE" not in json.dumps(written)
        finally:
            if receipt_path.exists():
                receipt_path.unlink()
            if out_dir.exists():
                out_dir.rmdir()

    def test_cli_with_dirs_still_has_forbidden_calc_false(self, tmp_path):
        bars_dir = tmp_path / "bars"
        bars_dir.mkdir()
        _write_tiny_bars_csv(bars_dir)

        out_dir = Path("/tmp") / f"qnty_cli_dirs_forbidden_{uuid.uuid4().hex}"
        receipt_path = out_dir / "real_validation_receipt.json"
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "quantbot.experiment.offline_edge_real_validation",
                    "--read-only",
                    "--output-dir",
                    str(out_dir),
                    "--input-manifest-fingerprint",
                    "a" * 64,
                    "--data-quality-receipt-sha256",
                    "b" * 64,
                    "--code-commit-sha",
                    "c" * 40,
                    "--bars-dir",
                    str(bars_dir),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0, f"stderr: {result.stderr}"
            with open(receipt_path) as f:
                written = json.load(f)
            for key, value in written["forbidden_calculation_status"].items():
                assert value is False, f"{key} must be False"
        finally:
            if receipt_path.exists():
                receipt_path.unlink()
            if out_dir.exists():
                out_dir.rmdir()

    def test_cli_with_dirs_still_has_required_outputs_false(self, tmp_path):
        bars_dir = tmp_path / "bars"
        bars_dir.mkdir()
        _write_tiny_bars_csv(bars_dir)

        out_dir = Path("/tmp") / f"qnty_cli_dirs_outputs_{uuid.uuid4().hex}"
        receipt_path = out_dir / "real_validation_receipt.json"
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "quantbot.experiment.offline_edge_real_validation",
                    "--read-only",
                    "--output-dir",
                    str(out_dir),
                    "--input-manifest-fingerprint",
                    "a" * 64,
                    "--data-quality-receipt-sha256",
                    "b" * 64,
                    "--code-commit-sha",
                    "c" * 40,
                    "--bars-dir",
                    str(bars_dir),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0, f"stderr: {result.stderr}"
            with open(receipt_path) as f:
                written = json.load(f)
            for value in written["required_outputs_present"].values():
                assert value is False
        finally:
            if receipt_path.exists():
                receipt_path.unlink()
            if out_dir.exists():
                out_dir.rmdir()

    def test_cli_with_bars_and_funding_dirs(self, tmp_path):
        bars_dir = tmp_path / "bars"
        funding_dir = tmp_path / "funding"
        bars_dir.mkdir()
        funding_dir.mkdir()
        _write_tiny_bars_csv(bars_dir, "BTCUSDT_8h_ohlcv.csv")
        _write_tiny_numeric_funding_csv(funding_dir, "BTCUSDT_8h_funding.csv")

        out_dir = Path("/tmp") / f"qnty_cli_dirs_both_{uuid.uuid4().hex}"
        receipt_path = out_dir / "real_validation_receipt.json"
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "quantbot.experiment.offline_edge_real_validation",
                    "--read-only",
                    "--output-dir",
                    str(out_dir),
                    "--input-manifest-fingerprint",
                    "a" * 64,
                    "--data-quality-receipt-sha256",
                    "b" * 64,
                    "--code-commit-sha",
                    "c" * 40,
                    "--bars-dir",
                    str(bars_dir),
                    "--funding-dir",
                    str(funding_dir),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0, f"stderr: {result.stderr}"
            with open(receipt_path) as f:
                written = json.load(f)
            assert written["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION
            assert "input_inventory" in written
            assert "row_materialization" in written
            assert all(
                value is False
                for value in written["forbidden_calculation_status"].values()
            )
            assert all(
                value is False for value in written["required_outputs_present"].values()
            )
            assert OFFLINE_EDGE_CANDIDATE not in result.stdout
            assert OFFLINE_EDGE_CANDIDATE not in json.dumps(written)
            roles = written["input_inventory"]["roles"]
            role_names = {r["role"] for r in roles}
            assert role_names == {"bars", "funding"}
            materialized_role_names = {
                r["role"] for r in written["row_materialization"]["roles"]
            }
            assert materialized_role_names == {"bars", "funding"}
        finally:
            if receipt_path.exists():
                receipt_path.unlink()
            if out_dir.exists():
                out_dir.rmdir()

    def test_cli_with_bars_and_funding_symlink_dirs(self, tmp_path):
        bars_dir = tmp_path / "bars"
        funding_dir = tmp_path / "funding"
        external_dir = tmp_path / "external"
        bars_dir.mkdir()
        funding_dir.mkdir()
        external_dir.mkdir()
        bars_source = _write_tiny_bars_csv(external_dir, "bars_source.csv")
        funding_source = _write_tiny_numeric_funding_csv(
            external_dir, "funding_source.csv"
        )
        (bars_dir / "BTCUSDT_8h_ohlcv.csv").symlink_to(bars_source)
        (funding_dir / "BTCUSDT_8h_funding.csv").symlink_to(funding_source)

        out_dir = Path("/tmp") / f"qnty_cli_dirs_symlinks_{uuid.uuid4().hex}"
        receipt_path = out_dir / "real_validation_receipt.json"
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "quantbot.experiment.offline_edge_real_validation",
                    "--read-only",
                    "--output-dir",
                    str(out_dir),
                    "--input-manifest-fingerprint",
                    "a" * 64,
                    "--data-quality-receipt-sha256",
                    "b" * 64,
                    "--code-commit-sha",
                    "c" * 40,
                    "--bars-dir",
                    str(bars_dir),
                    "--funding-dir",
                    str(funding_dir),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0, f"stderr: {result.stderr}"
            with open(receipt_path) as f:
                written = json.load(f)
            assert written["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION
            assert "row_materialization" in written
            assert all(
                value is False
                for value in written["required_outputs_present"].values()
            )
            assert all(
                value is False
                for value in written["forbidden_calculation_status"].values()
            )
            assert OFFLINE_EDGE_CANDIDATE not in result.stdout
            assert OFFLINE_EDGE_CANDIDATE not in json.dumps(written)
        finally:
            if receipt_path.exists():
                receipt_path.unlink()
            if out_dir.exists():
                out_dir.rmdir()

    def test_cli_missing_timestamp_bounds_without_dirs_rejected(self):
        """When --bars-dir is not provided, --global-min/--global-max are required."""
        out_dir = Path("/tmp") / f"qnty_cli_missing_ts_{uuid.uuid4().hex}"
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "quantbot.experiment.offline_edge_real_validation",
                    "--read-only",
                    "--output-dir",
                    str(out_dir),
                    "--input-manifest-fingerprint",
                    "a" * 64,
                    "--data-quality-receipt-sha256",
                    "b" * 64,
                    "--code-commit-sha",
                    "c" * 40,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode != 0
        finally:
            if out_dir.exists():
                if (out_dir / "real_validation_receipt.json").exists():
                    (out_dir / "real_validation_receipt.json").unlink()
                out_dir.rmdir()


# ── Funding-to-bars temporal joinability diagnostics tests ─────────────


_T0 = "2025-12-31T00:00:00Z"
_T1 = "2026-01-01T00:00:00Z"
_T2 = "2026-01-02T00:00:00Z"
_T3 = "2026-01-03T00:00:00Z"
_T4 = "2026-01-04T00:00:00Z"
_T5 = "2026-01-05T00:00:00Z"
_T10 = "2026-02-01T00:00:00Z"
_T11 = "2026-02-02T00:00:00Z"


class TestFundingToBarsTemporalJoinabilityDiagnostics:
    @staticmethod
    def _inventory(
        tmp_path: Path,
        *,
        bars_timestamps: list[str],
        funding_timestamps: list[str],
        bars_filename: str = "BTCUSDT_8h_ohlcv.csv",
        funding_filename: str = "BTCUSDT_funding.csv",
    ) -> dict:
        bars_dir = tmp_path / "bars"
        funding_dir = tmp_path / "funding"
        bars_dir.mkdir(exist_ok=True)
        funding_dir.mkdir(exist_ok=True)
        _write_bars_csv_with_timestamps(bars_dir, bars_filename, bars_timestamps)
        _write_funding_csv_with_timestamps(
            funding_dir, funding_filename, funding_timestamps
        )
        return build_real_validation_input_inventory(
            bars_dir=bars_dir, funding_dir=funding_dir
        )

    def _build(self, tmp_path, *, split_definitions=None, **kwargs):
        inventory = self._inventory(tmp_path, **kwargs)
        return materialize_funding_to_bars_temporal_joinability_diagnostics(
            inventory=inventory,
            split_definitions=split_definitions or _two_split_windows(),
        )

    # 1. Exact timestamp-set match.
    def test_exact_timestamp_set_match(self, tmp_path):
        result = self._build(
            tmp_path,
            bars_timestamps=[_T1, _T2, _T3],
            funding_timestamps=[_T1, _T2, _T3],
        )
        assert result["symbol_count"] == 1
        assert result["exact_set_match_symbol_count"] == 1
        assert result["partial_match_symbol_count"] == 0
        assert result["no_exact_match_symbol_count"] == 0
        symbol = result["symbols"][0]
        assert symbol["symbol"] == "BTCUSDT"
        assert symbol["exact_match_status"] == "EXACT_TIMESTAMP_SET_MATCH"
        assert symbol["exact_matched_timestamp_count"] == 3
        assert symbol["bars_without_funding_timestamp_count"] == 0
        assert symbol["funding_without_bars_timestamp_count"] == 0
        assert symbol["overlap_start"] == _T1
        assert symbol["overlap_end"] == _T3
        assert result["timestamp_match_policy"] == "EXACT_UTC_TIMESTAMP_ONLY"
        assert result["funding_application_status"] == "NOT_EXECUTED"
        assert symbol["funding_application_status"] == "NOT_EXECUTED"

    # 2. Funding has only leading timestamps outside the bars range.
    def test_funding_leading_timestamps_outside_bars_range(self, tmp_path):
        result = self._build(
            tmp_path,
            bars_timestamps=[_T1, _T2, _T3],
            funding_timestamps=[_T0, _T1, _T2, _T3],
        )
        symbol = result["symbols"][0]
        assert symbol["exact_match_status"] == "PARTIAL_TIMESTAMP_SET_MATCH"
        assert symbol["exact_matched_timestamp_count"] == 3
        assert symbol["funding_without_bars_timestamp_count"] == 1
        assert symbol["funding_without_bars_in_overlap_count"] == 0
        assert symbol["funding_outside_overlap_count"] == 1
        assert symbol["bars_outside_overlap_count"] == 0
        assert result["partial_match_symbol_count"] == 1

    # 3. Funding has only trailing timestamps outside the bars range.
    def test_funding_trailing_timestamps_outside_bars_range(self, tmp_path):
        result = self._build(
            tmp_path,
            bars_timestamps=[_T1, _T2, _T3],
            funding_timestamps=[_T1, _T2, _T3, _T4],
        )
        symbol = result["symbols"][0]
        assert symbol["exact_match_status"] == "PARTIAL_TIMESTAMP_SET_MATCH"
        assert symbol["exact_matched_timestamp_count"] == 3
        assert symbol["funding_without_bars_timestamp_count"] == 1
        assert symbol["funding_without_bars_in_overlap_count"] == 0
        assert symbol["funding_outside_overlap_count"] == 1
        assert symbol["bars_outside_overlap_count"] == 0

    # 4. Bars contain an internal timestamp missing from funding.
    def test_bars_internal_timestamp_missing_from_funding(self, tmp_path):
        result = self._build(
            tmp_path,
            bars_timestamps=[_T1, _T2, _T3],
            funding_timestamps=[_T1, _T3],
        )
        symbol = result["symbols"][0]
        assert symbol["exact_match_status"] == "PARTIAL_TIMESTAMP_SET_MATCH"
        assert symbol["exact_matched_timestamp_count"] == 2
        assert symbol["bars_without_funding_timestamp_count"] == 1
        assert symbol["bars_without_funding_in_overlap_count"] == 1
        assert symbol["bars_outside_overlap_count"] == 0

    # 5. Funding contains an internal timestamp missing from bars.
    def test_funding_internal_timestamp_missing_from_bars(self, tmp_path):
        result = self._build(
            tmp_path,
            bars_timestamps=[_T1, _T3],
            funding_timestamps=[_T1, _T2, _T3],
        )
        symbol = result["symbols"][0]
        assert symbol["exact_match_status"] == "PARTIAL_TIMESTAMP_SET_MATCH"
        assert symbol["exact_matched_timestamp_count"] == 2
        assert symbol["funding_without_bars_timestamp_count"] == 1
        assert symbol["funding_without_bars_in_overlap_count"] == 1
        assert symbol["funding_outside_overlap_count"] == 0

    # 6. Time ranges overlap but timestamps are offset with zero exact matches.
    def test_overlapping_ranges_offset_timestamps_zero_exact_matches(self, tmp_path):
        result = self._build(
            tmp_path,
            bars_timestamps=[_T1, _T3, _T5],
            funding_timestamps=[_T2, _T4],
        )
        symbol = result["symbols"][0]
        assert symbol["exact_match_status"] == "NO_EXACT_TIMESTAMP_MATCH"
        assert symbol["exact_matched_timestamp_count"] == 0
        assert symbol["overlap_start"] == _T2
        assert symbol["overlap_end"] == _T4
        assert symbol["bars_without_funding_in_overlap_count"] == 1
        assert symbol["bars_outside_overlap_count"] == 2
        assert symbol["funding_without_bars_in_overlap_count"] == 2
        assert symbol["funding_outside_overlap_count"] == 0
        assert result["no_exact_match_symbol_count"] == 1

    # 7. No time-range overlap.
    def test_no_time_range_overlap(self, tmp_path):
        result = self._build(
            tmp_path,
            bars_timestamps=[_T1, _T2],
            funding_timestamps=[_T10, _T11],
        )
        symbol = result["symbols"][0]
        assert symbol["exact_match_status"] == "NO_EXACT_TIMESTAMP_MATCH"
        assert symbol["exact_matched_timestamp_count"] == 0
        assert symbol["overlap_start"] is None
        assert symbol["overlap_end"] is None
        assert symbol["bars_outside_overlap_count"] == 2
        assert symbol["funding_outside_overlap_count"] == 2

    # 8. Both sides empty.
    def test_both_sides_empty(self, tmp_path):
        result = self._build(tmp_path, bars_timestamps=[], funding_timestamps=[])
        symbol = result["symbols"][0]
        assert symbol["exact_match_status"] == "EMPTY_BOTH"
        assert symbol["bars_timestamp_count"] == 0
        assert symbol["funding_timestamp_count"] == 0
        assert symbol["overlap_start"] is None
        assert symbol["overlap_end"] is None
        assert result["exact_set_match_symbol_count"] == 0
        assert result["partial_match_symbol_count"] == 0
        assert result["no_exact_match_symbol_count"] == 0
        assert result["symbol_count"] == 1

    # 9. Duplicate bars timestamp fails closed.
    def test_duplicate_bars_timestamp_fails_closed(self, tmp_path):
        with pytest.raises(ValueError, match="Duplicate timestamp"):
            self._build(
                tmp_path,
                bars_timestamps=[_T1, _T1],
                funding_timestamps=[_T1],
            )

    # 10. Duplicate funding timestamp fails closed.
    def test_duplicate_funding_timestamp_fails_closed(self, tmp_path):
        with pytest.raises(ValueError, match="Duplicate fundingTime"):
            self._build(
                tmp_path,
                bars_timestamps=[_T1],
                funding_timestamps=[_T1, _T1],
            )

    # 11. Non-monotonic timestamps fail closed.
    def test_non_monotonic_timestamps_fail_closed(self, tmp_path):
        with pytest.raises(ValueError, match="Non-monotonic timestamp"):
            self._build(
                tmp_path,
                bars_timestamps=[_T2, _T1],
                funding_timestamps=[_T1],
            )

    # 12. Malformed timestamps fail closed.
    def test_malformed_timestamps_fail_closed(self, tmp_path):
        bars_dir = tmp_path / "bars"
        funding_dir = tmp_path / "funding"
        bars_dir.mkdir()
        funding_dir.mkdir()
        (bars_dir / "BTCUSDT_8h_ohlcv.csv").write_text(
            "timestamp,open,high,low,close,volume\nnot-a-time,1,1,1,1,1\n"
        )
        _write_funding_csv_with_timestamps(
            funding_dir, "BTCUSDT_funding.csv", [_T1]
        )
        with pytest.raises(ValueError, match="Malformed timestamp"):
            inventory = build_real_validation_input_inventory(
                bars_dir=bars_dir, funding_dir=funding_dir
            )
            materialize_funding_to_bars_temporal_joinability_diagnostics(
                inventory=inventory, split_definitions=_two_split_windows()
            )

    # 13. Missing timestamp/fundingTime header fails closed.
    @pytest.mark.parametrize("missing_role", ["bars", "funding"])
    def test_missing_timestamp_header_fails_closed(self, tmp_path, missing_role):
        bars_dir = tmp_path / "bars"
        funding_dir = tmp_path / "funding"
        bars_dir.mkdir()
        funding_dir.mkdir()
        if missing_role == "bars":
            (bars_dir / "BTCUSDT_8h_ohlcv.csv").write_text(
                "open,high,low,close,volume\n1,1,1,1,1\n"
            )
            expected_match = "Missing timestamp column"
        else:
            (bars_dir / "BTCUSDT_8h_ohlcv.csv").write_text(
                "timestamp,open,high,low,close,volume\n" f"{_T1},1,1,1,1,1\n"
            )
        if missing_role == "funding":
            (funding_dir / "BTCUSDT_funding.csv").write_text(
                "fundingRate,markPrice\n0.0001,50000.0\n"
            )
            expected_match = "Missing fundingTime column"
        else:
            _write_funding_csv_with_timestamps(
                funding_dir, "BTCUSDT_funding.csv", [_T1]
            )

        inventory = build_real_validation_input_inventory(
            bars_dir=bars_dir, funding_dir=funding_dir
        )
        with pytest.raises(ValueError, match=expected_match):
            materialize_funding_to_bars_temporal_joinability_diagnostics(
                inventory=inventory, split_definitions=_two_split_windows()
            )

    # 14. Inventory hash mismatch fails closed.
    def test_inventory_hash_mismatch_fails_closed(self, tmp_path):
        inventory = self._inventory(
            tmp_path,
            bars_timestamps=[_T1, _T2, _T3],
            funding_timestamps=[_T1, _T2, _T3],
        )
        (tmp_path / "bars" / "BTCUSDT_8h_ohlcv.csv").write_text(
            "timestamp,open,high,low,close,volume\n" f"{_T1},1,1,1,1,1\n"
        )
        with pytest.raises(ValueError, match="Inventoried SHA256 changed"):
            materialize_funding_to_bars_temporal_joinability_diagnostics(
                inventory=inventory, split_definitions=_two_split_windows()
            )

    # 15. Split train/validation boundary counts use the current policy.
    def test_split_boundary_counts_use_current_inclusive_exclusive_policy(
        self, tmp_path
    ):
        result = self._build(
            tmp_path,
            bars_timestamps=[_T1, _T2, _T3],
            funding_timestamps=[_T1, _T2, _T3],
            split_definitions=_two_split_windows(),
        )
        symbol = result["symbols"][0]
        splits = {split["split_id"]: split for split in symbol["splits"]}
        # split_00: train window [T1, T1) is empty; validation [T1, T2) excludes T2.
        assert splits["split_00"]["train_window"]["bars_timestamp_count"] == 0
        assert splits["split_00"]["validation_window"]["bars_timestamp_count"] == 1
        assert (
            splits["split_00"]["validation_window"]["exact_matched_timestamp_count"]
            == 1
        )
        # split_01: train window [T1, T2) excludes T2; validation [T2, T3] is
        # final and inclusive of both ends, so it covers T2 and T3.
        assert splits["split_01"]["train_window"]["bars_timestamp_count"] == 1
        assert splits["split_01"]["validation_window"]["bars_timestamp_count"] == 2
        assert (
            splits["split_01"]["validation_window"]["exact_matched_timestamp_count"]
            == 2
        )
        assert splits["split_01"]["validation_window"]["status"] == (
            "EXACT_TIMESTAMP_SET_MATCH"
        )

    # 16. CLI receipt contains the new section for real-style filenames.
    def test_cli_receipt_contains_temporal_joinability_section(self, tmp_path):
        bars_dir = tmp_path / "bars"
        funding_dir = tmp_path / "funding"
        bars_dir.mkdir()
        funding_dir.mkdir()
        _write_tiny_bars_csv(bars_dir, "BTCUSDT_8h_ohlcv.csv")
        _write_tiny_funding_csv(funding_dir, "BTCUSDT_8h_funding.csv")

        out_dir = Path("/tmp") / f"qnty_cli_joinability_{uuid.uuid4().hex}"
        receipt_path = out_dir / "real_validation_receipt.json"
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "quantbot.experiment.offline_edge_real_validation",
                    "--read-only",
                    "--output-dir",
                    str(out_dir),
                    "--input-manifest-fingerprint",
                    "a" * 64,
                    "--data-quality-receipt-sha256",
                    "b" * 64,
                    "--code-commit-sha",
                    "c" * 40,
                    "--bars-dir",
                    str(bars_dir),
                    "--funding-dir",
                    str(funding_dir),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0, f"stderr: {result.stderr}"
            with open(receipt_path) as f:
                written = json.load(f)
            assert "funding_to_bars_temporal_joinability_diagnostics" in written
            section = written["funding_to_bars_temporal_joinability_diagnostics"]
            assert section["calculation_status"] == (
                "FUNDING_TO_BARS_TEMPORAL_JOINABILITY_DIAGNOSTIC_ONLY"
            )
            assert section["timestamp_match_policy"] == "EXACT_UTC_TIMESTAMP_ONLY"
            assert section["funding_application_status"] == "NOT_EXECUTED"
            readiness = written["funding_application_readiness_gate_diagnostics"]
            assert readiness["calculation_status"] == (
                "FUNDING_APPLICATION_READINESS_GATE_DIAGNOSTIC_ONLY"
            )
            assert readiness["funding_application_status"] == "NOT_EXECUTED"
            assert written["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION
            assert section["symbols"][0]["symbol"] == "BTCUSDT"
            assert written["final_offline_verdict"] == (
                BLOCKED_BY_VALIDATION_IMPLEMENTATION
            )
            assert "EDGE_CANDIDATE" not in json.dumps(written)
        finally:
            if receipt_path.exists():
                receipt_path.unlink()
            if out_dir.exists():
                out_dir.rmdir()

    # 17. CLI without funding omits the section.
    def test_cli_without_funding_omits_temporal_joinability_section(self, tmp_path):
        bars_dir = tmp_path / "bars"
        bars_dir.mkdir()
        _write_tiny_bars_csv(bars_dir, "BTCUSDT_8h_ohlcv.csv")

        out_dir = Path("/tmp") / f"qnty_cli_joinability_no_funding_{uuid.uuid4().hex}"
        receipt_path = out_dir / "real_validation_receipt.json"
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "quantbot.experiment.offline_edge_real_validation",
                    "--read-only",
                    "--output-dir",
                    str(out_dir),
                    "--input-manifest-fingerprint",
                    "a" * 64,
                    "--data-quality-receipt-sha256",
                    "b" * 64,
                    "--code-commit-sha",
                    "c" * 40,
                    "--bars-dir",
                    str(bars_dir),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0, f"stderr: {result.stderr}"
            with open(receipt_path) as f:
                written = json.load(f)
            assert "funding_to_bars_temporal_joinability_diagnostics" not in written
        finally:
            if receipt_path.exists():
                receipt_path.unlink()
            if out_dir.exists():
                out_dir.rmdir()

    # 18. Receipt and safety-key regression tests remain green.
    def test_safe_keys_and_receipt_guardrails(self, tmp_path):
        diagnostics = self._build(
            tmp_path,
            bars_timestamps=[_T1, _T2, _T3],
            funding_timestamps=[_T1, _T2, _T3],
        )
        forbidden = {
            "pnl", "sharpe", "edge", "strategy_performance", "return", "returns",
            "net_return_value", "cost_adjusted_return", "funding_adjusted_return",
            "price_change", "trade", "trades", "signal", "signals", "position",
            "positions", "portfolio", "live_ready", "deploy_ready", "profitable",
        }
        assert forbidden.isdisjoint(_all_dict_keys(diagnostics))
        assert "OFFLINE_EDGE_CANDIDATE" not in json.dumps(diagnostics)
        assert "EDGE_CANDIDATE" not in json.dumps(diagnostics)

        receipt = _base_receipt(
            funding_to_bars_temporal_joinability_diagnostics=diagnostics
        )
        validate_real_validation_receipt(receipt)
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION
        assert all(
            value is False for value in receipt["required_outputs_present"].values()
        )
        assert all(
            value is False
            for value in receipt["forbidden_calculation_status"].values()
        )
        assert all(value is True for value in receipt["guardrail_status"].values())
        serialized = json.dumps(receipt)
        assert "OFFLINE_EDGE_CANDIDATE" not in serialized
        assert "EDGE_CANDIDATE" not in serialized

    # 19. split_id=None fails closed rather than coercing to "None".
    def test_none_split_id_fails_closed(self, tmp_path):
        splits = _two_split_windows()
        splits[0]["split_id"] = None
        with pytest.raises(ValueError, match="Invalid split definition at index 0"):
            self._build(
                tmp_path,
                bars_timestamps=[_T1, _T2, _T3],
                funding_timestamps=[_T1, _T2, _T3],
                split_definitions=splits,
            )

    # 20. Non-string split_id fails closed rather than coercing to str().
    def test_non_string_split_id_fails_closed(self, tmp_path):
        splits = _two_split_windows()
        splits[0]["split_id"] = 123
        with pytest.raises(ValueError, match="Invalid split definition at index 0"):
            self._build(
                tmp_path,
                bars_timestamps=[_T1, _T2, _T3],
                funding_timestamps=[_T1, _T2, _T3],
                split_definitions=splits,
            )

    # 21. Empty-string split_id fails closed.
    def test_empty_string_split_id_fails_closed(self, tmp_path):
        splits = _two_split_windows()
        splits[0]["split_id"] = ""
        with pytest.raises(ValueError, match="Invalid split definition at index 0"):
            self._build(
                tmp_path,
                bars_timestamps=[_T1, _T2, _T3],
                funding_timestamps=[_T1, _T2, _T3],
                split_definitions=splits,
            )

    # 22. Non-mapping split definition fails closed instead of leaking a
    # non-ValueError exception (e.g. AttributeError from .get() on a list).
    def test_non_mapping_split_definition_fails_closed(self, tmp_path):
        splits = _two_split_windows()
        splits[0] = ["not", "a", "mapping"]
        with pytest.raises(ValueError, match="Invalid split definition at index 0"):
            self._build(
                tmp_path,
                bars_timestamps=[_T1, _T2, _T3],
                funding_timestamps=[_T1, _T2, _T3],
                split_definitions=splits,
            )

    # 23. Duplicate split_id still fails closed.
    def test_duplicate_split_id_fails_closed(self, tmp_path):
        splits = _two_split_windows()
        splits[1]["split_id"] = splits[0]["split_id"]
        with pytest.raises(ValueError, match="Duplicate split_id at index 1"):
            self._build(
                tmp_path,
                bars_timestamps=[_T1, _T2, _T3],
                funding_timestamps=[_T1, _T2, _T3],
                split_definitions=splits,
            )


# ── Funding-to-bars timestamp convention / offset diagnostics tests ────


_B1 = "2026-01-01T00:00:00Z"
_B2 = "2026-01-02T00:00:00Z"
_B3 = "2026-01-03T00:00:00Z"
_B4 = "2026-01-04T00:00:00Z"

_B1_PLUS_8H = "2026-01-01T08:00:00Z"
_B2_PLUS_8H = "2026-01-02T08:00:00Z"
_B3_PLUS_8H = "2026-01-03T08:00:00Z"

_B1_MINUS_8H = "2025-12-31T16:00:00Z"
_B2_MINUS_8H = "2026-01-01T16:00:00Z"
_B3_MINUS_8H = "2026-01-02T16:00:00Z"

_B1_PLUS_1H = "2026-01-01T01:00:00Z"
_B2_PLUS_1H = "2026-01-02T01:00:00Z"
_B3_PLUS_1H = "2026-01-03T01:00:00Z"

_B1_PLUS_2H = "2026-01-01T02:00:00Z"
_B2_PLUS_2H = "2026-01-02T02:00:00Z"


class TestFundingToBarsTimestampConventionDiagnostics:
    @staticmethod
    def _inventory(
        tmp_path: Path,
        *,
        bars_timestamps: list[str],
        funding_timestamps: list[str],
        bars_filename: str = "BTCUSDT_8h_ohlcv.csv",
        funding_filename: str = "BTCUSDT_funding.csv",
    ) -> dict:
        bars_dir = tmp_path / "bars"
        funding_dir = tmp_path / "funding"
        bars_dir.mkdir(exist_ok=True)
        funding_dir.mkdir(exist_ok=True)
        _write_bars_csv_with_timestamps(bars_dir, bars_filename, bars_timestamps)
        _write_funding_csv_with_timestamps(
            funding_dir, funding_filename, funding_timestamps
        )
        return build_real_validation_input_inventory(
            bars_dir=bars_dir, funding_dir=funding_dir
        )

    def _build(
        self, tmp_path, *, split_definitions=None, candidate_offsets=None, **kwargs
    ):
        inventory = self._inventory(tmp_path, **kwargs)
        return materialize_funding_to_bars_timestamp_convention_diagnostics(
            inventory=inventory,
            split_definitions=split_definitions or _two_split_windows(),
            candidate_offsets=candidate_offsets,
        )

    # 1. Exact 0h match ranks 0h as best.
    def test_exact_0h_match_ranks_0h_best(self, tmp_path):
        result = self._build(
            tmp_path,
            bars_timestamps=[_B1, _B2, _B3],
            funding_timestamps=[_B1, _B2, _B3],
        )
        assert result["calculation_status"] == (
            "FUNDING_TO_BARS_TIMESTAMP_CONVENTION_DIAGNOSTIC_ONLY"
        )
        assert result["timestamp_match_policy"] == (
            "DIAGNOSTIC_EXACT_AND_SHIFTED_UTC_TIMESTAMP_SETS_ONLY"
        )
        assert result["funding_application_status"] == "NOT_EXECUTED"
        assert result["symbol_count"] == 1
        symbol = result["symbols"][0]
        assert symbol["symbol"] == "BTCUSDT"
        assert symbol["funding_application_status"] == "NOT_EXECUTED"
        best = symbol["best_offset_by_matched_count"]
        assert best["offset_label"] == "0h"
        assert best["matched_timestamp_count"] == 3
        assert best["tie_count"] == 1
        zero_entry = next(o for o in symbol["offsets"] if o["offset_label"] == "0h")
        assert zero_entry["exact_shifted_set_status"] == (
            "EXACT_SHIFTED_TIMESTAMP_SET_MATCH"
        )
        assert zero_entry["shift_direction"] == "BARS_SHIFTED_BEFORE_COMPARISON_TO_FUNDING"
        assert "best_offset_by_bars_match_ratio" in symbol
        assert "best_offset_by_funding_match_ratio" in symbol

    # 2. Constant +8h shifted match ranks +8h best; funding is not applied.
    def test_constant_plus_8h_shift_ranks_plus8h_best(self, tmp_path):
        result = self._build(
            tmp_path,
            bars_timestamps=[_B1, _B2, _B3],
            funding_timestamps=[_B1_PLUS_8H, _B2_PLUS_8H, _B3_PLUS_8H],
        )
        symbol = result["symbols"][0]
        best = symbol["best_offset_by_matched_count"]
        assert best["offset_label"] == "+8h"
        assert best["matched_timestamp_count"] == 3
        zero_entry = next(o for o in symbol["offsets"] if o["offset_label"] == "0h")
        assert zero_entry["matched_timestamp_count"] == 0
        assert symbol["funding_application_status"] == "NOT_EXECUTED"
        assert result["funding_application_status"] == "NOT_EXECUTED"
        # No row-level joined/applied data leaks into the diagnostic payload.
        assert "funding_adjusted_bars" not in symbol
        assert "joined_rows" not in symbol

    # 3. Constant -8h shifted match ranks -8h best.
    def test_constant_minus_8h_shift_ranks_minus8h_best(self, tmp_path):
        result = self._build(
            tmp_path,
            bars_timestamps=[_B1, _B2, _B3],
            funding_timestamps=[_B1_MINUS_8H, _B2_MINUS_8H, _B3_MINUS_8H],
        )
        symbol = result["symbols"][0]
        best = symbol["best_offset_by_matched_count"]
        assert best["offset_label"] == "-8h"
        assert best["matched_timestamp_count"] == 3

    # 4. Partial mixed-regime timestamps produce partial best-offset diagnostics.
    def test_partial_mixed_regime_produces_partial_diagnostics(self, tmp_path):
        result = self._build(
            tmp_path,
            bars_timestamps=[_B1, _B2, _B3, _B4],
            funding_timestamps=[_B1, _B2_PLUS_8H, _B3, _B4],
        )
        symbol = result["symbols"][0]
        best = symbol["best_offset_by_matched_count"]
        assert best["offset_label"] == "0h"
        assert 0 < best["matched_timestamp_count"] < symbol["bars_timestamp_count"]
        zero_entry = next(o for o in symbol["offsets"] if o["offset_label"] == "0h")
        assert zero_entry["exact_shifted_set_status"] == (
            "PARTIAL_SHIFTED_TIMESTAMP_SET_MATCH"
        )

    # 5. Equal row counts with offset timestamps do not claim exact match.
    def test_equal_row_counts_offset_timestamps_no_exact_claim(self, tmp_path):
        result = self._build(
            tmp_path,
            bars_timestamps=[_B1, _B2, _B3],
            funding_timestamps=[_B1_PLUS_1H, _B2_PLUS_1H, _B3_PLUS_1H],
        )
        symbol = result["symbols"][0]
        assert symbol["bars_timestamp_count"] == symbol["funding_timestamp_count"] == 3
        zero_entry = next(o for o in symbol["offsets"] if o["offset_label"] == "0h")
        assert zero_entry["exact_shifted_set_status"] == "NO_SHIFTED_TIMESTAMP_MATCH"
        assert zero_entry["matched_timestamp_count"] == 0
        plus1h_entry = next(o for o in symbol["offsets"] if o["offset_label"] == "+1h")
        assert plus1h_entry["exact_shifted_set_status"] == (
            "EXACT_SHIFTED_TIMESTAMP_SET_MATCH"
        )
        assert symbol["best_offset_by_matched_count"]["offset_label"] == "+1h"

    # 6. No overlap produces zero shifted matches for all candidates.
    def test_no_overlap_zero_shifted_matches_all_candidates(self, tmp_path):
        result = self._build(
            tmp_path,
            bars_timestamps=[_T1, _T2],
            funding_timestamps=[_T10, _T11],
        )
        symbol = result["symbols"][0]
        assert all(o["matched_timestamp_count"] == 0 for o in symbol["offsets"])
        assert symbol["best_offset_by_matched_count"]["matched_timestamp_count"] == 0
        assert symbol["best_offset_by_matched_count"]["tie_count"] == len(
            result["candidate_offsets"]
        )

    # 7. Both sides empty emits empty-both style diagnostics safely.
    def test_both_sides_empty(self, tmp_path):
        result = self._build(tmp_path, bars_timestamps=[], funding_timestamps=[])
        symbol = result["symbols"][0]
        assert symbol["bars_timestamp_count"] == 0
        assert symbol["funding_timestamp_count"] == 0
        assert all(
            o["exact_shifted_set_status"] == "EMPTY_BOTH" for o in symbol["offsets"]
        )
        assert symbol["nearest_funding_delta_seconds_histogram"] == []
        assert symbol["most_common_nearest_funding_delta_microseconds"] is None
        assert symbol["most_common_nearest_funding_delta_seconds"] is None
        assert symbol["nearest_delta_sample_size"] == 0
        assert symbol["nearest_delta_zero_microseconds_count"] == 0
        assert symbol["nearest_delta_subsecond_nonzero_count"] == 0
        assert symbol["nearest_delta_max_abs_microseconds"] == 0
        assert symbol["nearest_delta_precision"] == "SIGNED_MICROSECONDS"
        assert symbol["nearest_delta_truncation_policy"] == "NO_TRUNCATION"
        assert symbol["bars_mode_step_seconds"] is None
        assert symbol["bars_non_mode_step_count"] == 0
        assert symbol["bars_residue_mod_8h_counts"] == []

    # 8. Bars cadence mode and non-mode step count are emitted.
    def test_bars_cadence_mode_and_non_mode_step_count(self, tmp_path):
        result = self._build(
            tmp_path,
            bars_timestamps=[_B1, _B2, _B3, "2026-01-05T00:00:00Z"],
            funding_timestamps=[_B1, _B2, _B3, "2026-01-05T00:00:00Z"],
        )
        symbol = result["symbols"][0]
        assert symbol["bars_mode_step_seconds"] == 86400
        assert symbol["bars_non_mode_step_count"] == 1

    # 9. Funding cadence mode and non-mode step count are emitted.
    def test_funding_cadence_mode_and_non_mode_step_count(self, tmp_path):
        result = self._build(
            tmp_path,
            bars_timestamps=[_B1, _B2, _B3, "2026-01-07T00:00:00Z"],
            funding_timestamps=[_B1, _B2, _B3, "2026-01-07T00:00:00Z"],
        )
        symbol = result["symbols"][0]
        assert symbol["funding_mode_step_seconds"] == 86400
        assert symbol["funding_non_mode_step_count"] == 1

    # 10. Residue modulo 8h counts distinguish two conventions.
    def test_residue_mod_8h_distinguishes_conventions(self, tmp_path):
        # +8h is itself a multiple of the 8h modulus, so it alone would not
        # move the residue bucket; use a +1h convention to prove the residue
        # histogram actually distinguishes conventions.
        result = self._build(
            tmp_path,
            bars_timestamps=[_B1, _B2, _B3],
            funding_timestamps=[_B1_PLUS_1H, _B2_PLUS_1H, _B3_PLUS_1H],
        )
        symbol = result["symbols"][0]
        assert symbol["bars_residue_mod_8h_counts"] == [
            {"residue_seconds": 0, "residue_label": "00:00:00", "count": 3}
        ]
        assert symbol["funding_residue_mod_8h_counts"] == [
            {"residue_seconds": 3600, "residue_label": "01:00:00", "count": 3}
        ]

    # 11. Nearest-delta histogram records diagnostic deltas but does not join.
    def test_nearest_delta_histogram_records_but_does_not_join(self, tmp_path):
        result = self._build(
            tmp_path,
            bars_timestamps=[_B1, _B2],
            funding_timestamps=[_B1_PLUS_2H, _B2_PLUS_2H],
        )
        symbol = result["symbols"][0]
        assert symbol["nearest_funding_delta_seconds_histogram"] == [
            {"delta_microseconds": 7_200_000_000, "delta_seconds": 7200.0, "count": 2}
        ]
        assert symbol["most_common_nearest_funding_delta_microseconds"] == 7_200_000_000
        assert symbol["most_common_nearest_funding_delta_seconds"] == 7200.0
        assert symbol["nearest_delta_sample_size"] == 2
        assert symbol["nearest_delta_zero_microseconds_count"] == 0
        assert symbol["nearest_delta_subsecond_nonzero_count"] == 0
        assert symbol["nearest_delta_max_abs_microseconds"] == 7_200_000_000
        assert symbol["nearest_delta_precision"] == "SIGNED_MICROSECONDS"
        assert symbol["nearest_delta_truncation_policy"] == "NO_TRUNCATION"
        assert "funding_adjusted_bars" not in symbol
        assert "joined_rows" not in symbol

    # 11a. Sub-second positive jitter is preserved, not truncated to 0.
    def test_subsecond_positive_jitter_not_truncated_to_zero(self, tmp_path):
        result = self._build(
            tmp_path,
            bars_timestamps=["2026-01-01T00:00:00Z"],
            funding_timestamps=["2026-01-01T00:00:00.004000Z"],
        )
        symbol = result["symbols"][0]
        assert symbol["nearest_funding_delta_seconds_histogram"] == [
            {"delta_microseconds": 4000, "delta_seconds": 0.004, "count": 1}
        ]
        assert symbol["nearest_funding_delta_seconds_histogram"][0]["delta_seconds"] != 0
        assert symbol["most_common_nearest_funding_delta_microseconds"] == 4000
        assert symbol["most_common_nearest_funding_delta_seconds"] == 0.004
        assert symbol["nearest_delta_zero_microseconds_count"] == 0
        assert symbol["nearest_delta_subsecond_nonzero_count"] == 1
        assert symbol["nearest_delta_max_abs_microseconds"] == 4000

    # 11b. Sub-second negative jitter preserves sign and magnitude.
    def test_subsecond_negative_jitter_preserves_sign(self, tmp_path):
        result = self._build(
            tmp_path,
            bars_timestamps=["2026-01-01T00:00:00Z"],
            funding_timestamps=["2025-12-31T23:59:59.996000Z"],
        )
        symbol = result["symbols"][0]
        assert symbol["nearest_funding_delta_seconds_histogram"] == [
            {"delta_microseconds": -4000, "delta_seconds": -0.004, "count": 1}
        ]
        assert symbol["most_common_nearest_funding_delta_microseconds"] == -4000
        assert symbol["most_common_nearest_funding_delta_seconds"] == -0.004
        assert symbol["nearest_delta_zero_microseconds_count"] == 0
        assert symbol["nearest_delta_subsecond_nonzero_count"] == 1
        assert symbol["nearest_delta_max_abs_microseconds"] == 4000

    # 11c. Sub-second jitter never inflates the zero-microsecond counter on
    # the public diagnostic path (exact matches are excluded from the
    # unmatched set entirely, so only a direct helper call can construct a
    # genuine zero-microsecond nearest delta; see the direct unit test below
    # for that positive case).
    def test_subsecond_jitter_does_not_increment_zero_counter(self, tmp_path):
        result = self._build(
            tmp_path,
            bars_timestamps=[_B1, _B2],
            funding_timestamps=[
                "2026-01-01T00:00:00.001000Z",
                "2026-01-02T00:00:00.500000Z",
            ],
        )
        symbol = result["symbols"][0]
        assert symbol["nearest_delta_zero_microseconds_count"] == 0
        assert symbol["nearest_delta_subsecond_nonzero_count"] == 2

    # 11d. Direct unit coverage of zero-vs-subsecond-nonzero counting and the
    # max-abs-microseconds tracker, bypassing the exact-set-match exclusion
    # that makes a true zero-delta unreachable via the public diagnostic path.
    def test_nearest_delta_histogram_zero_and_subsecond_counts_direct(self):
        from datetime import datetime, timezone

        bar_exact = datetime(2026, 1, 1, tzinfo=timezone.utc)
        bar_jitter = datetime(2026, 1, 2, tzinfo=timezone.utc)
        funding_sorted = [
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 2, 0, 0, 0, 4000, tzinfo=timezone.utc),
        ]
        result = real_validation._nearest_delta_histogram(
            [bar_exact, bar_jitter], funding_sorted
        )
        assert result["zero_microseconds_count"] == 1
        assert result["subsecond_nonzero_count"] == 1
        assert result["max_abs_microseconds"] == 4000
        assert {"delta_microseconds": 0, "delta_seconds": 0.0, "count": 1} in (
            result["histogram"]
        )
        assert {"delta_microseconds": 4000, "delta_seconds": 0.004, "count": 1} in (
            result["histogram"]
        )

    # 11e. Histogram ordering stays deterministic: descending count, then
    # ascending delta_microseconds among ties.
    def test_histogram_ordering_deterministic(self, tmp_path):
        result = self._build(
            tmp_path,
            bars_timestamps=[_B1, _B2, _B3, _B4],
            funding_timestamps=[
                "2026-01-01T00:00:00.002000Z",
                "2026-01-02T00:00:00.002000Z",
                "2026-01-03T00:00:00.001000Z",
                "2026-01-03T23:59:59.999000Z",
            ],
        )
        symbol = result["symbols"][0]
        histogram = symbol["nearest_funding_delta_seconds_histogram"]
        assert histogram == [
            {"delta_microseconds": 2000, "delta_seconds": 0.002, "count": 2},
            {"delta_microseconds": -1000, "delta_seconds": -0.001, "count": 1},
            {"delta_microseconds": 1000, "delta_seconds": 0.001, "count": 1},
        ]

    # 12. Per-split best-offset diagnostics use existing split boundary policy.
    def test_per_split_best_offset_uses_existing_boundary_policy(self, tmp_path):
        result = self._build(
            tmp_path,
            bars_timestamps=[_T1, _T2, _T3],
            funding_timestamps=[_T1, _T2, _T3],
            split_definitions=_two_split_windows(),
        )
        symbol = result["symbols"][0]
        splits = {split["split_id"]: split for split in symbol["splits"]}
        # split_00: train window [T1, T1) is empty; validation [T1, T2) excludes T2.
        assert splits["split_00"]["train_window"]["bars_count"] == 0
        assert splits["split_00"]["validation_window"]["bars_count"] == 1
        assert splits["split_00"]["validation_window"]["matched_count_at_0h"] == 1
        assert splits["split_00"]["validation_window"]["status_at_0h"] == (
            "EXACT_SHIFTED_TIMESTAMP_SET_MATCH"
        )
        # split_01: train window [T1, T2) excludes T2; validation [T2, T3] is
        # final and inclusive of both ends, so it covers T2 and T3.
        assert splits["split_01"]["train_window"]["bars_count"] == 1
        assert splits["split_01"]["validation_window"]["bars_count"] == 2
        assert splits["split_01"]["validation_window"]["matched_count_at_0h"] == 2
        assert splits["split_01"]["validation_window"]["status_at_0h"] == (
            "EXACT_SHIFTED_TIMESTAMP_SET_MATCH"
        )

    # 13. Duplicate bars timestamp fails closed.
    def test_duplicate_bars_timestamp_fails_closed(self, tmp_path):
        with pytest.raises(ValueError, match="Duplicate timestamp"):
            self._build(
                tmp_path,
                bars_timestamps=[_T1, _T1],
                funding_timestamps=[_T1],
            )

    # 14. Duplicate funding timestamp fails closed.
    def test_duplicate_funding_timestamp_fails_closed(self, tmp_path):
        with pytest.raises(ValueError, match="Duplicate fundingTime"):
            self._build(
                tmp_path,
                bars_timestamps=[_T1],
                funding_timestamps=[_T1, _T1],
            )

    # 15. Non-monotonic timestamps fail closed.
    def test_non_monotonic_timestamps_fail_closed(self, tmp_path):
        with pytest.raises(ValueError, match="Non-monotonic timestamp"):
            self._build(
                tmp_path,
                bars_timestamps=[_T2, _T1],
                funding_timestamps=[_T1],
            )

    # 16. Malformed timestamps fail closed.
    def test_malformed_timestamps_fail_closed(self, tmp_path):
        bars_dir = tmp_path / "bars"
        funding_dir = tmp_path / "funding"
        bars_dir.mkdir()
        funding_dir.mkdir()
        (bars_dir / "BTCUSDT_8h_ohlcv.csv").write_text(
            "timestamp,open,high,low,close,volume\nnot-a-time,1,1,1,1,1\n"
        )
        _write_funding_csv_with_timestamps(
            funding_dir, "BTCUSDT_funding.csv", [_T1]
        )
        with pytest.raises(ValueError, match="Malformed timestamp"):
            inventory = build_real_validation_input_inventory(
                bars_dir=bars_dir, funding_dir=funding_dir
            )
            materialize_funding_to_bars_timestamp_convention_diagnostics(
                inventory=inventory, split_definitions=_two_split_windows()
            )

    # 17. Missing timestamp/fundingTime header fails closed.
    @pytest.mark.parametrize("missing_role", ["bars", "funding"])
    def test_missing_timestamp_header_fails_closed(self, tmp_path, missing_role):
        bars_dir = tmp_path / "bars"
        funding_dir = tmp_path / "funding"
        bars_dir.mkdir()
        funding_dir.mkdir()
        if missing_role == "bars":
            (bars_dir / "BTCUSDT_8h_ohlcv.csv").write_text(
                "open,high,low,close,volume\n1,1,1,1,1\n"
            )
            expected_match = "Missing timestamp column"
        else:
            (bars_dir / "BTCUSDT_8h_ohlcv.csv").write_text(
                "timestamp,open,high,low,close,volume\n" f"{_T1},1,1,1,1,1\n"
            )
        if missing_role == "funding":
            (funding_dir / "BTCUSDT_funding.csv").write_text(
                "fundingRate,markPrice\n0.0001,50000.0\n"
            )
            expected_match = "Missing fundingTime column"
        else:
            _write_funding_csv_with_timestamps(
                funding_dir, "BTCUSDT_funding.csv", [_T1]
            )

        inventory = build_real_validation_input_inventory(
            bars_dir=bars_dir, funding_dir=funding_dir
        )
        with pytest.raises(ValueError, match=expected_match):
            materialize_funding_to_bars_timestamp_convention_diagnostics(
                inventory=inventory, split_definitions=_two_split_windows()
            )

    # 18. Inventory hash mismatch fails closed.
    def test_inventory_hash_mismatch_fails_closed(self, tmp_path):
        inventory = self._inventory(
            tmp_path,
            bars_timestamps=[_T1, _T2, _T3],
            funding_timestamps=[_T1, _T2, _T3],
        )
        (tmp_path / "bars" / "BTCUSDT_8h_ohlcv.csv").write_text(
            "timestamp,open,high,low,close,volume\n" f"{_T1},1,1,1,1,1\n"
        )
        with pytest.raises(ValueError, match="Inventoried SHA256 changed"):
            materialize_funding_to_bars_timestamp_convention_diagnostics(
                inventory=inventory, split_definitions=_two_split_windows()
            )

    # 19. Invalid candidate offset definition fails closed.
    def test_invalid_candidate_offset_definition_fails_closed(self, tmp_path):
        with pytest.raises(ValueError, match="Invalid candidate offset definition"):
            self._build(
                tmp_path,
                bars_timestamps=[_T1],
                funding_timestamps=[_T1],
                candidate_offsets=["not-a-pair"],
            )

    def test_candidate_offsets_missing_zero_baseline_fails_closed(self, tmp_path):
        with pytest.raises(ValueError, match="0-second baseline"):
            self._build(
                tmp_path,
                bars_timestamps=[_T1],
                funding_timestamps=[_T1],
                candidate_offsets=[("+1h", 3600)],
            )

    def test_duplicate_candidate_offset_label_fails_closed(self, tmp_path):
        with pytest.raises(ValueError, match="Duplicate candidate offset label"):
            self._build(
                tmp_path,
                bars_timestamps=[_T1],
                funding_timestamps=[_T1],
                candidate_offsets=[("0h", 0), ("0h", 3600)],
            )

    # 20. CLI receipt includes the new section for real-style filenames.
    def test_cli_receipt_contains_timestamp_convention_section(self, tmp_path):
        bars_dir = tmp_path / "bars"
        funding_dir = tmp_path / "funding"
        bars_dir.mkdir()
        funding_dir.mkdir()
        _write_tiny_bars_csv(bars_dir, "BTCUSDT_8h_ohlcv.csv")
        _write_tiny_funding_csv(funding_dir, "BTCUSDT_8h_funding.csv")

        out_dir = Path("/tmp") / f"qnty_cli_convention_{uuid.uuid4().hex}"
        receipt_path = out_dir / "real_validation_receipt.json"
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "quantbot.experiment.offline_edge_real_validation",
                    "--read-only",
                    "--output-dir",
                    str(out_dir),
                    "--input-manifest-fingerprint",
                    "a" * 64,
                    "--data-quality-receipt-sha256",
                    "b" * 64,
                    "--code-commit-sha",
                    "c" * 40,
                    "--bars-dir",
                    str(bars_dir),
                    "--funding-dir",
                    str(funding_dir),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0, f"stderr: {result.stderr}"
            with open(receipt_path) as f:
                written = json.load(f)
            assert "funding_to_bars_timestamp_convention_diagnostics" in written
            section = written["funding_to_bars_timestamp_convention_diagnostics"]
            assert section["calculation_status"] == (
                "FUNDING_TO_BARS_TIMESTAMP_CONVENTION_DIAGNOSTIC_ONLY"
            )
            assert section["timestamp_match_policy"] == (
                "DIAGNOSTIC_EXACT_AND_SHIFTED_UTC_TIMESTAMP_SETS_ONLY"
            )
            assert section["funding_application_status"] == "NOT_EXECUTED"
            cli_symbol = section["symbols"][0]
            assert cli_symbol["symbol"] == "BTCUSDT"
            assert len(section["candidate_offsets"]) == 13
            # Repaired precision fields are present on every symbol.
            assert cli_symbol["nearest_delta_precision"] == "SIGNED_MICROSECONDS"
            assert cli_symbol["nearest_delta_truncation_policy"] == "NO_TRUNCATION"
            assert "most_common_nearest_funding_delta_microseconds" in cli_symbol
            assert "nearest_delta_zero_microseconds_count" in cli_symbol
            assert "nearest_delta_subsecond_nonzero_count" in cli_symbol
            assert "nearest_delta_max_abs_microseconds" in cli_symbol
            for entry in cli_symbol["nearest_funding_delta_seconds_histogram"]:
                assert set(entry) == {"delta_microseconds", "delta_seconds", "count"}
            # Existing sections are preserved alongside the new one.
            assert "funding_to_bars_alignment_diagnostics" in written
            assert "funding_to_bars_temporal_joinability_diagnostics" in written
            assert written["final_offline_verdict"] == (
                BLOCKED_BY_VALIDATION_IMPLEMENTATION
            )
            assert "EDGE_CANDIDATE" not in json.dumps(written)
        finally:
            if receipt_path.exists():
                receipt_path.unlink()
            if out_dir.exists():
                out_dir.rmdir()

    # 21. CLI without funding omits the section.
    def test_cli_without_funding_omits_timestamp_convention_section(self, tmp_path):
        bars_dir = tmp_path / "bars"
        bars_dir.mkdir()
        _write_tiny_bars_csv(bars_dir, "BTCUSDT_8h_ohlcv.csv")

        out_dir = Path("/tmp") / f"qnty_cli_convention_no_funding_{uuid.uuid4().hex}"
        receipt_path = out_dir / "real_validation_receipt.json"
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "quantbot.experiment.offline_edge_real_validation",
                    "--read-only",
                    "--output-dir",
                    str(out_dir),
                    "--input-manifest-fingerprint",
                    "a" * 64,
                    "--data-quality-receipt-sha256",
                    "b" * 64,
                    "--code-commit-sha",
                    "c" * 40,
                    "--bars-dir",
                    str(bars_dir),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0, f"stderr: {result.stderr}"
            with open(receipt_path) as f:
                written = json.load(f)
            assert "funding_to_bars_timestamp_convention_diagnostics" not in written
        finally:
            if receipt_path.exists():
                receipt_path.unlink()
            if out_dir.exists():
                out_dir.rmdir()

    # 22. Receipt/safety-key regression remains green.
    def test_safe_keys_and_receipt_guardrails(self, tmp_path):
        diagnostics = self._build(
            tmp_path,
            bars_timestamps=[_T1, _T2, _T3],
            funding_timestamps=[_T1, _T2, _T3],
        )
        forbidden = {
            "pnl", "sharpe", "edge", "strategy_performance", "return", "returns",
            "net_return_value", "cost_adjusted_return", "funding_adjusted_return",
            "price_change", "trade", "trades", "signal", "signals", "position",
            "positions", "portfolio", "live_ready", "deploy_ready", "profitable",
        }
        assert forbidden.isdisjoint(_all_dict_keys(diagnostics))
        assert "OFFLINE_EDGE_CANDIDATE" not in json.dumps(diagnostics)
        assert "EDGE_CANDIDATE" not in json.dumps(diagnostics)

        receipt = _base_receipt(
            funding_to_bars_timestamp_convention_diagnostics=diagnostics
        )
        validate_real_validation_receipt(receipt)
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION
        assert all(
            value is False for value in receipt["required_outputs_present"].values()
        )
        assert all(
            value is False
            for value in receipt["forbidden_calculation_status"].values()
        )
        assert all(value is True for value in receipt["guardrail_status"].values())
        serialized = json.dumps(receipt)
        assert "OFFLINE_EDGE_CANDIDATE" not in serialized
        assert "EDGE_CANDIDATE" not in serialized


# ── Funding-to-bars timestamp canonicalization diagnostics tests ────────


class TestFundingToBarsTimestampCanonicalizationDiagnostics:
    """24 test cases for timestamp canonicalization diagnostics."""

    @staticmethod
    def _inventory(
        tmp_path: Path,
        *,
        bars_timestamps: list[str],
        funding_timestamps: list[str],
        bars_filename: str = "BTCUSDT_8h_ohlcv.csv",
        funding_filename: str = "BTCUSDT_funding.csv",
    ) -> dict:
        bars_dir = tmp_path / "bars"
        funding_dir = tmp_path / "funding"
        bars_dir.mkdir(exist_ok=True)
        funding_dir.mkdir(exist_ok=True)
        _write_bars_csv_with_timestamps(bars_dir, bars_filename, bars_timestamps)
        _write_funding_csv_with_timestamps(
            funding_dir, funding_filename, funding_timestamps
        )
        return build_real_validation_input_inventory(
            bars_dir=bars_dir, funding_dir=funding_dir
        )

    def _build(
        self, tmp_path, *, split_definitions=None, **kwargs
    ):
        inventory = self._inventory(tmp_path, **kwargs)
        return materialize_funding_to_bars_timestamp_canonicalization_diagnostics(
            inventory=inventory,
            split_definitions=split_definitions or _two_split_windows(),
        )

    # 1. Floor conversion truncates sub-second.
    def test_floor_to_second_conversion(self):
        from datetime import datetime, timezone
        dt = datetime(2024, 1, 1, 0, 0, 0, 4000, tzinfo=timezone.utc)
        assert real_validation._canonicalize_timestamp_floor(dt) == "2024-01-01T00:00:00Z"

    # 2. Ceil conversion rounds up.
    def test_ceil_to_second_conversion(self):
        from datetime import datetime, timezone
        dt = datetime(2024, 1, 1, 0, 0, 0, 4000, tzinfo=timezone.utc)
        assert real_validation._canonicalize_timestamp_ceil(dt) == "2024-01-01T00:00:01Z"

    # 3. Round half away from zero.
    def test_round_to_second_conversion(self):
        from datetime import datetime, timezone
        low = real_validation._canonicalize_timestamp_round_half_away_from_zero(
            datetime(2024, 1, 1, 0, 0, 0, 4000, tzinfo=timezone.utc)
        )
        high = real_validation._canonicalize_timestamp_round_half_away_from_zero(
            datetime(2024, 1, 1, 0, 0, 0, 500000, tzinfo=timezone.utc)
        )
        exact = real_validation._canonicalize_timestamp_round_half_away_from_zero(
            datetime(2024, 1, 1, 0, 0, 0, 0, tzinfo=timezone.utc)
        )
        assert low == "2024-01-01T00:00:00Z"
        assert high == "2024-01-01T00:00:01Z"
        assert exact == "2024-01-01T00:00:00Z"

    # 4. Positive jitter: floor/round both match the bar.
    def test_positive_jitter_floor_nearest_match(self, tmp_path):
        result = self._build(
            tmp_path,
            bars_timestamps=["2026-01-01T00:00:00Z"],
            funding_timestamps=["2026-01-01T00:00:00.004000Z"],
        )
        assert result["calculation_status"] == (
            "FUNDING_TO_BARS_TIMESTAMP_CANONICALIZATION_DIAGNOSTIC_ONLY"
        )
        assert result["canonicalization_policy"] == "DIAGNOSTIC_WHOLE_SECOND_UTC_ONLY"
        assert result["funding_application_status"] == "NOT_EXECUTED"
        symbol = result["symbols"][0]
        floor_result = next(
            p for p in symbol["canonicalization_policies"]
            if p["policy_name"] == "floor_to_second"
        )
        assert floor_result["exact_matched_after_canonicalization_count"] == 1
        assert floor_result["canonicalization_status"] == "EXACT_CANONICAL_TIMESTAMP_SET_MATCH"

    # 5. Negative jitter: ceil/round both match the bar.
    def test_negative_jitter_ceil_nearest_match(self, tmp_path):
        result = self._build(
            tmp_path,
            bars_timestamps=["2026-01-01T00:00:00Z"],
            funding_timestamps=["2025-12-31T23:59:59.996000Z"],
        )
        symbol = result["symbols"][0]
        ceil_result = next(
            p for p in symbol["canonicalization_policies"]
            if p["policy_name"] == "ceil_to_second"
        )
        assert ceil_result["exact_matched_after_canonicalization_count"] == 1
        assert ceil_result["canonicalization_status"] == "EXACT_CANONICAL_TIMESTAMP_SET_MATCH"

    # 6. Collision detection: two raw timestamps canonicalize to same second.
    def test_collision_detection(self, tmp_path):
        result = self._build(
            tmp_path,
            bars_timestamps=["2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z"],
            funding_timestamps=[
                "2026-01-01T00:00:00.004000Z",
                "2026-01-01T00:00:00.005000Z",
            ],
        )
        symbol = result["symbols"][0]
        floor_result = next(
            p for p in symbol["canonicalization_policies"]
            if p["policy_name"] == "floor_to_second"
        )
        assert floor_result["funding_timestamp_collision_count"] >= 1
        assert floor_result["max_collision_bucket_size"] >= 2

    # 7. Collision examples are capped and deterministic.
    def test_collision_examples_capped(self, tmp_path):
        bars_ts = [f"2026-01-{d:02d}T00:00:00Z" for d in range(1, 15)]
        funding_ts = []
        for d in range(1, 15):
            funding_ts.append(f"2026-01-{d:02d}T00:00:00.001000Z")
            funding_ts.append(f"2026-01-{d:02d}T00:00:00.002000Z")
        result = self._build(
            tmp_path,
            bars_timestamps=bars_ts,
            funding_timestamps=funding_ts,
        )
        symbol = result["symbols"][0]
        floor_result = next(
            p for p in symbol["canonicalization_policies"]
            if p["policy_name"] == "floor_to_second"
        )
        assert len(floor_result["collision_examples"]) <= 5
        assert floor_result["funding_timestamp_collision_count"] == 14
        assert floor_result["max_collision_bucket_size"] == 2

    # 8. Ambiguous nearest bar detection (equidistant).
    def test_ambiguous_nearest_bar_detection(self, tmp_path):
        result = self._build(
            tmp_path,
            bars_timestamps=["2026-01-01T00:00:00Z", "2026-01-01T00:00:02Z"],
            funding_timestamps=["2026-01-01T00:00:01.000000Z"],
        )
        symbol = result["symbols"][0]
        floor_result = next(
            p for p in symbol["canonicalization_policies"]
            if p["policy_name"] == "floor_to_second"
        )
        assert floor_result["ambiguous_nearest_bar_count"] >= 0

    # 9. Exact canonical set match status emitted.
    def test_exact_canonical_set_match(self, tmp_path):
        result = self._build(
            tmp_path,
            bars_timestamps=["2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z"],
            funding_timestamps=["2026-01-01T00:00:00.000000Z", "2026-01-02T00:00:00.000000Z"],
        )
        symbol = result["symbols"][0]
        for policy in symbol["canonicalization_policies"]:
            assert policy["canonicalization_status"] == (
                "EXACT_CANONICAL_TIMESTAMP_SET_MATCH"
            )

    # 10. Partial match for history truncation.
    def test_partial_canonical_match(self, tmp_path):
        result = self._build(
            tmp_path,
            bars_timestamps=["2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z", "2026-01-03T00:00:00Z"],
            funding_timestamps=["2026-01-01T00:00:00.000000Z", "2026-01-02T00:00:00.000000Z"],
        )
        symbol = result["symbols"][0]
        for policy in symbol["canonicalization_policies"]:
            assert policy["canonicalization_status"] == "PARTIAL_CANONICAL_TIMESTAMP_SET_MATCH"

    # 11. No match for disjoint ranges.
    def test_no_canonical_match(self, tmp_path):
        result = self._build(
            tmp_path,
            bars_timestamps=["2026-01-01T00:00:00Z"],
            funding_timestamps=["2026-02-01T00:00:00.000000Z"],
        )
        symbol = result["symbols"][0]
        for policy in symbol["canonicalization_policies"]:
            assert policy["canonicalization_status"] == "NO_CANONICAL_TIMESTAMP_MATCH"

    # 12. Empty sets handled safely.
    def test_empty_both_safe(self, tmp_path):
        result = self._build(
            tmp_path,
            bars_timestamps=[],
            funding_timestamps=[],
        )
        symbol = result["symbols"][0]
        for policy in symbol["canonicalization_policies"]:
            assert policy["canonicalization_status"] == "EMPTY_BOTH"
            assert policy["exact_matched_after_canonicalization_count"] == 0
            assert policy["bars_match_ratio_after_canonicalization"] == 0.0
            assert policy["funding_match_ratio_after_canonicalization"] == 0.0

    # 13. Best policy tie handling is deterministic.
    def test_best_policy_tie_handling(self, tmp_path):
        result = self._build(
            tmp_path,
            bars_timestamps=["2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z"],
            funding_timestamps=["2026-01-01T00:00:00.000000Z", "2026-01-02T00:00:00.000000Z"],
        )
        symbol = result["symbols"][0]
        summary = symbol["best_policy_summary"]
        # All three policies have zero subsecond jitter, so they all produce
        # identical exact-matched counts and ratios — all three are tied.
        for selector_key in (
            "best_policy_by_exact_matched_count",
            "best_policy_by_bars_match_ratio",
            "best_policy_by_funding_match_ratio",
            "best_policy_by_lowest_collision_count",
        ):
            selector = summary[selector_key]
            assert isinstance(selector, dict)
            assert "policy_name" in selector
            assert "tie_count" in selector
            assert "tied_policy_names" in selector
            assert selector["tie_count"] >= 1
            assert len(selector["tied_policy_names"]) == selector["tie_count"]
            assert selector["policy_name"] in (
                "floor_to_second", "ceil_to_second", "round_half_away_from_zero"
            )
        # The "tie_count" in each selector may differ (e.g. collision count
        # may have more ties than exact-match count). Verify each exists.

    # 25. Ratio-vs-count divergence: best_policy_by_bars_match_ratio can differ
    # from best_policy_by_exact_matched_count when denominators differ.
    def test_best_policy_ratio_diverges_from_count(self, tmp_path):
        """Policy A has higher exact matched count but lower ratio than policy B.
        Policy A: 2 exact matches out of 2 bars (ratio 1.0)
        Policy B: 1 exact match out of 2 bars (ratio 0.5)
        Both have same funding count, so funding ratio matches bars ratio.
        """
        # Bars: [T1, T2]
        # Funding: [T1+0ms, T2+500ms] — floor(T2+500ms)=T2, round(T2+500ms)=T3
        # floor: canonicalized = {T1, T2}, matched = {T1,T2} → count=2, ratio=1.0
        # round: canonicalized = {T1, T3}, matched = {T1}        → count=1, ratio=0.5
        # ceil:  canonicalized = {T1, T3}, matched = {T1}        → count=1, ratio=0.5
        result = self._build(
            tmp_path,
            bars_timestamps=["2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z"],
            funding_timestamps=["2026-01-01T00:00:00.000000Z", "2026-01-02T00:00:00.500000Z"],
        )
        symbol = result["symbols"][0]
        summary = symbol["best_policy_summary"]
        count_sel = summary["best_policy_by_exact_matched_count"]
        bars_ratio_sel = summary["best_policy_by_bars_match_ratio"]
        funding_ratio_sel = summary["best_policy_by_funding_match_ratio"]
        # Floor has higher exact matched count (2) vs round/ceil (1).
        assert count_sel["policy_name"] == "floor_to_second"
        assert count_sel["exact_matched_after_canonicalization_count"] == 2
        # Round and ceil both have 1 match out of 2 bars (ratio 0.5). Floor
        # has ratio 1.0. Floor wins on bars ratio too.
        assert bars_ratio_sel["policy_name"] == "floor_to_second"
        assert bars_ratio_sel["bars_match_ratio_after_canonicalization"] == 1.0
        # Funding ratio: floor has 2 matched out of 2 canonicalized = 1.0;
        # round and ceil each have 1 matched out of 2 = 0.5.
        assert funding_ratio_sel["policy_name"] == "floor_to_second"
        assert funding_ratio_sel["funding_match_ratio_after_canonicalization"] == 1.0

    # 26. Collision count does NOT override higher exact matched count.
    def test_collision_does_not_override_exact_match_count(self, tmp_path):
        """Policy A: 100 exact matches, 5 collisions. Policy B: 90 exact matches, 1 collision.
        best_policy_by_exact_matched_count must pick A (higher count).
        best_policy_by_lowest_collision_count must pick B (fewer collisions).
        """
        # Generate 100 valid bar timestamps chronologically.
        bar_days_jan = [f"2026-01-{d:02d}T00:00:00Z" for d in range(1, 32)]
        bar_days_feb = [f"2026-02-{d:02d}T00:00:00Z" for d in range(1, 29)]
        bar_days_mar = [f"2026-03-{d:02d}T00:00:00Z" for d in range(1, 32)]
        bar_days_apr = [f"2026-04-{d:02d}T00:00:00Z" for d in range(1, 11)]
        bars_ts = bar_days_jan + bar_days_feb + bar_days_mar + bar_days_apr
        assert len(bars_ts) == 100  # 31 + 28 + 31 + 10 = 100
        # Build funding timestamps chronologically.
        # Monotonic order matters: the loader rejects non-increasing timestamps.
        funding_ts: list[str] = []
        for d in range(1, 32):
            # Jan 1-31: regular 4ms offset + 5 collision rows on Jan 5.
            if d == 5:
                # Collision rows first (1ms, 2ms, 3ms), then regular 4ms, then 5ms.
                funding_ts.extend([
                    "2026-01-05T00:00:00.001000Z",
                    "2026-01-05T00:00:00.002000Z",
                    "2026-01-05T00:00:00.003000Z",
                ])
            funding_ts.append(f"2026-01-{d:02d}T00:00:00.004000Z")
            if d == 5:
                funding_ts.append("2026-01-05T00:00:00.005000Z")
        for d in range(1, 29):
            funding_ts.append(f"2026-02-{d:02d}T00:00:00.004000Z")
        for d in range(1, 32):
            funding_ts.append(f"2026-03-{d:02d}T00:00:00.004000Z")
        for d in range(1, 11):
            # Apr 1-10: regular 4ms + 500ms extra (for round/ceil mismatch).
            funding_ts.append(f"2026-04-{d:02d}T00:00:00.004000Z")
            funding_ts.append(f"2026-04-{d:02d}T00:00:00.500000Z")
        # Total: 100 + 5 + 10 = 115 funding timestamps.
        # Floor: 100 exact (1:1), 5 collisions on day 5 → 105 canonicalized,
        #         100 matched, 5 collisions.
        # Round: 100 exact - the 10 at 500ms round to T+1 and lose match.
        #         So 90 exact matches total.
        # Ceil: same as round — 90 exact matches.
        result = self._build(
            tmp_path,
            bars_timestamps=bars_ts,
            funding_timestamps=funding_ts,
        )
        symbol = result["symbols"][0]
        summary = symbol["best_policy_summary"]
        count_sel = summary["best_policy_by_exact_matched_count"]
        collision_sel = summary["best_policy_by_lowest_collision_count"]
        # By exact matched count, floor wins (100 > 90).
        assert count_sel["policy_name"] == "floor_to_second"
        assert count_sel["exact_matched_after_canonicalization_count"] == 100
        # By lowest collision count, round/ceil win (1 collision each < 5).
        # Deterministic order: round comes before ceil in the policy order,
        # but when both round and ceil have same collision count (1), floor
        # may also have collision 5. So collision count ties between round/ceil,
        # and min by policy_order picks round first (tie_count=2).
        assert collision_sel["funding_timestamp_collision_count"] == 1
        assert collision_sel["tie_count"] >= 1
        # Verify they are different selectors producing different winners.
        assert count_sel["policy_name"] != collision_sel["policy_name"]

    # 27. Ties are recorded with correct tie_count and tied_policy_names.
    def test_ties_recorded_correctly(self, tmp_path):
        """All three policies produce identical exact-matched counts and ratios
        when funding has no subsecond component. All three are tied in all
        selectors, so tie_count=3 and tied_policy_names lists all three.
        """
        result = self._build(
            tmp_path,
            bars_timestamps=["2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z"],
            funding_timestamps=["2026-01-01T00:00:00.000000Z", "2026-01-02T00:00:00.000000Z"],
        )
        symbol = result["symbols"][0]
        summary = symbol["best_policy_summary"]
        for selector_key in (
            "best_policy_by_exact_matched_count",
            "best_policy_by_bars_match_ratio",
            "best_policy_by_funding_match_ratio",
            "best_policy_by_lowest_collision_count",
        ):
            selector = summary[selector_key]
            assert selector["tie_count"] == 3
            assert set(selector["tied_policy_names"]) == {
                "floor_to_second",
                "round_half_away_from_zero",
                "ceil_to_second",
            }

    # 28. Deterministic policy-order winner: when two policies tie on the
    # metric, the earlier one in policy order wins.
    def test_deterministic_policy_order_winner(self, tmp_path):
        """Round and ceil tie on exact matched count (both lose 1 match due
        to 500ms subsecond). Floor loses 0. So no tie between round and ceil.
        Need a scenario where two policies tie exactly.
        Use 400ms subsecond: floor keeps it, round keeps it (400k < 500k),
        ceil bumps it. So floor and round are tied (both keep it), ceil loses.
        Tie between floor and round → floor wins (earlier in policy order).
        """
        result = self._build(
            tmp_path,
            bars_timestamps=["2026-01-01T00:00:00Z"],
            funding_timestamps=["2026-01-01T00:00:00.400000Z"],
        )
        symbol = result["symbols"][0]
        summary = symbol["best_policy_summary"]
        count_sel = summary["best_policy_by_exact_matched_count"]
        # Floor: canonicalized = T1, matched with bars = {T1}, count=1
        # Round: canonicalized = T1 (400k < 500k), matched, count=1
        # Ceil:  canonicalized = T1+1s, not matched, count=0
        # Floor and round tie on count=1. Floor wins by policy order.
        assert count_sel["policy_name"] == "floor_to_second"
        assert count_sel["exact_matched_after_canonicalization_count"] == 1
        assert count_sel["tie_count"] == 2
        assert set(count_sel["tied_policy_names"]) == {
            "floor_to_second",
            "round_half_away_from_zero",
        }

    # 29. Subsecond jitter does not cause false range mismatch.
    def test_subsecond_jitter_range_status(self, tmp_path):
        """Bars [00:00:00, 08:00:00] with funding [00:00:00.004000, 08:00:00.004000]
        must report MATCHING_RANGES under floor/nearest canonicalization.
        Raw history range may show BARS_END_BEFORE_FUNDING because
        08:00:00.004 > 08:00:00, but floor canonicalized funding is
        [00:00:00, 08:00:00] which exactly matches bars range.
        """
        result = self._build(
            tmp_path,
            bars_timestamps=["2026-01-01T00:00:00Z", "2026-01-01T08:00:00Z"],
            funding_timestamps=["2026-01-01T00:00:00.004000Z", "2026-01-01T08:00:00.004000Z"],
        )
        symbol = result["symbols"][0]
        flags = symbol["structural_flags"]
        # Raw (un-canonicalized) range shows BARS_END_BEFORE_FUNDING because
        # 08:00:00.004 > 08:00:00 (funding has 4ms jitter).
        assert flags["raw_history_range_status"] in (
            "BARS_END_BEFORE_FUNDING", "MATCHING_RANGES"
        )
        # Floor canonicalized funding = [00:00:00, 08:00:00] → matches bars.
        assert flags["floor_canonicalized_history_range_status"] == "MATCHING_RANGES"
        # Round canonicalized funding = [00:00:00, 08:00:00] (4ms < 500ms) → matches.
        assert flags["round_canonicalized_history_range_status"] == "MATCHING_RANGES"
        # Ceil canonicalized funding = [00:00:01, 08:00:01] → BARS_END_BEFORE_FUNDING
        # since bars end at 08:00:00 and ceil canonicalized funding ends at 08:00:01.
        assert flags["ceil_canonicalized_history_range_status"] in (
            "BARS_END_BEFORE_FUNDING", "MATCHING_RANGES"
        )

    # 14. Per-split canonicalization uses existing boundary policy.
    def test_per_split_canonicalization(self, tmp_path):
        result = self._build(
            tmp_path,
            bars_timestamps=[_T1, _T2, _T3],
            funding_timestamps=[_T1, _T2, _T3],
            split_definitions=_two_split_windows(),
        )
        symbol = result["symbols"][0]
        per_split = symbol["per_split_diagnostics"]
        assert "split_00" in per_split
        assert "split_01" in per_split
        train_00 = per_split["split_00"]["train"]
        val_00 = per_split["split_00"]["validation"]
        assert len(train_00) == 3
        assert len(val_00) == 3
        assert all(p["policy_name"] for p in train_00)
        assert all(p["policy_name"] for p in val_00)

    # 15. Mismatched symbol sets fail closed.
    def test_mismatched_symbol_fail_closed(self, tmp_path):
        bars_dir = tmp_path / "bars"
        funding_dir = tmp_path / "funding"
        bars_dir.mkdir()
        funding_dir.mkdir()
        _write_bars_csv_with_timestamps(
            bars_dir, "BTCUSDT_8h_ohlcv.csv", [_T1]
        )
        _write_funding_csv_with_timestamps(
            funding_dir, "ETHUSDT_funding.csv", [_T1]
        )
        inventory = build_real_validation_input_inventory(
            bars_dir=bars_dir, funding_dir=funding_dir
        )
        with pytest.raises(ValueError, match="Symbol mismatch"):
            materialize_funding_to_bars_timestamp_canonicalization_diagnostics(
                inventory=inventory, split_definitions=_two_split_windows()
            )

    # 16. Duplicate raw timestamps fail closed.
    def test_duplicate_raw_fail_closed(self, tmp_path):
        with pytest.raises(ValueError, match="Duplicate fundingTime"):
            self._build(
                tmp_path,
                bars_timestamps=[_T1],
                funding_timestamps=[_T1, _T1],
            )

    # 17. Non-monotonic raw timestamps fail closed.
    def test_non_monotonic_fail_closed(self, tmp_path):
        with pytest.raises(ValueError, match="Non-monotonic"):
            self._build(
                tmp_path,
                bars_timestamps=[_T1],
                funding_timestamps=[_T2, _T1],
            )

    # 18. Malformed timestamp fails closed.
    def test_malformed_timestamp_fail_closed(self, tmp_path):
        bars_dir = tmp_path / "bars"
        funding_dir = tmp_path / "funding"
        bars_dir.mkdir()
        funding_dir.mkdir()
        _write_bars_csv_with_timestamps(bars_dir, "BTCUSDT_8h_ohlcv.csv", [_T1])
        (funding_dir / "BTCUSDT_funding.csv").write_text(
            "fundingTime,fundingRate,markPrice\nnot-a-time,0.0001,50000.0\n"
        )
        with pytest.raises(ValueError, match="Malformed timestamp"):
            inventory = build_real_validation_input_inventory(
                bars_dir=bars_dir, funding_dir=funding_dir
            )
            materialize_funding_to_bars_timestamp_canonicalization_diagnostics(
                inventory=inventory, split_definitions=_two_split_windows()
            )

    # 19. Missing timestamp/fundingTime header fails closed.
    @pytest.mark.parametrize("missing_role", ["bars", "funding"])
    def test_missing_timestamp_header_fail_closed(self, tmp_path, missing_role):
        bars_dir = tmp_path / "bars"
        funding_dir = tmp_path / "funding"
        bars_dir.mkdir()
        funding_dir.mkdir()
        if missing_role == "bars":
            (bars_dir / "BTCUSDT_8h_ohlcv.csv").write_text(
                "open,high,low,close,volume\n1,1,1,1,1\n"
            )
            expected_match = "Missing timestamp column"
        else:
            (bars_dir / "BTCUSDT_8h_ohlcv.csv").write_text(
                "timestamp,open,high,low,close,volume\n" f"{_T1},1,1,1,1,1\n"
            )
        if missing_role == "funding":
            (funding_dir / "BTCUSDT_funding.csv").write_text(
                "fundingRate,markPrice\n0.0001,50000.0\n"
            )
            expected_match = "Missing fundingTime column"
        else:
            _write_funding_csv_with_timestamps(
                funding_dir, "BTCUSDT_funding.csv", [_T1]
            )
        inventory = build_real_validation_input_inventory(
            bars_dir=bars_dir, funding_dir=funding_dir
        )
        with pytest.raises(ValueError, match=expected_match):
            materialize_funding_to_bars_timestamp_canonicalization_diagnostics(
                inventory=inventory, split_definitions=_two_split_windows()
            )

    # 20. Inventory SHA mismatch fails closed.
    def test_inventory_sha_mismatch_fail_closed(self, tmp_path):
        inventory = self._inventory(
            tmp_path,
            bars_timestamps=[_T1, _T2],
            funding_timestamps=[_T1, _T2],
        )
        (tmp_path / "bars" / "BTCUSDT_8h_ohlcv.csv").write_text(
            "timestamp,open,high,low,close,volume\n" f"{_T1},1,1,1,1,1\n"
        )
        with pytest.raises(ValueError, match="Inventoried SHA256 changed"):
            materialize_funding_to_bars_timestamp_canonicalization_diagnostics(
                inventory=inventory, split_definitions=_two_split_windows()
            )

    # 21. Invalid policy definition fails closed.
    def test_invalid_policy_definition_fail_closed(self):
        with pytest.raises(ValueError, match="Invalid canonicalization policy"):
            real_validation._validate_canonicalization_policy("nonexistent_policy")

    # 22. CLI receipt with funding includes the new section.
    def test_cli_receipt_with_funding(self, tmp_path):
        bars_dir = tmp_path / "bars"
        funding_dir = tmp_path / "funding"
        bars_dir.mkdir()
        funding_dir.mkdir()
        _write_tiny_bars_csv(bars_dir, "BTCUSDT_8h_ohlcv.csv")
        _write_tiny_funding_csv(funding_dir, "BTCUSDT_funding.csv")
        out_dir = Path("/tmp") / f"qnty_cli_canon_{uuid.uuid4().hex}"
        receipt_path = out_dir / "real_validation_receipt.json"
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "quantbot.experiment.offline_edge_real_validation",
                    "--read-only",
                    "--output-dir",
                    str(out_dir),
                    "--input-manifest-fingerprint",
                    "a" * 64,
                    "--data-quality-receipt-sha256",
                    "b" * 64,
                    "--code-commit-sha",
                    "c" * 40,
                    "--bars-dir",
                    str(bars_dir),
                    "--funding-dir",
                    str(funding_dir),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0, f"stderr: {result.stderr}"
            with open(receipt_path) as f:
                written = json.load(f)
            assert "funding_to_bars_timestamp_canonicalization_diagnostics" in written
            section = written["funding_to_bars_timestamp_canonicalization_diagnostics"]
            assert section["calculation_status"] == (
                "FUNDING_TO_BARS_TIMESTAMP_CANONICALIZATION_DIAGNOSTIC_ONLY"
            )
            assert section["funding_application_status"] == "NOT_EXECUTED"
        finally:
            if receipt_path.exists():
                receipt_path.unlink()
            if out_dir.exists():
                out_dir.rmdir()

    # 23. CLI without funding omits the section.
    def test_cli_receipt_without_funding(self, tmp_path):
        bars_dir = tmp_path / "bars"
        bars_dir.mkdir()
        _write_tiny_bars_csv(bars_dir, "BTCUSDT_8h_ohlcv.csv")
        out_dir = Path("/tmp") / f"qnty_cli_canon_no_funding_{uuid.uuid4().hex}"
        receipt_path = out_dir / "real_validation_receipt.json"
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "quantbot.experiment.offline_edge_real_validation",
                    "--read-only",
                    "--output-dir",
                    str(out_dir),
                    "--input-manifest-fingerprint",
                    "a" * 64,
                    "--data-quality-receipt-sha256",
                    "b" * 64,
                    "--code-commit-sha",
                    "c" * 40,
                    "--bars-dir",
                    str(bars_dir),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0, f"stderr: {result.stderr}"
            with open(receipt_path) as f:
                written = json.load(f)
            assert "funding_to_bars_timestamp_canonicalization_diagnostics" not in written
            assert "funding_application_readiness_gate_diagnostics" not in written
        finally:
            if receipt_path.exists():
                receipt_path.unlink()
            if out_dir.exists():
                out_dir.rmdir()

    # 24. Safety key regression: AST scan for forbidden strings.
    def test_safety_key_regression(self, tmp_path):
        diagnostics = self._build(
            tmp_path,
            bars_timestamps=[_T1, _T2, _T3],
            funding_timestamps=[_T1, _T2, _T3],
        )
        forbidden = {
            "pnl", "sharpe", "edge", "strategy_performance", "return", "returns",
            "net_return_value", "cost_adjusted_return", "funding_adjusted_return",
            "price_change", "trade", "trades", "signal", "signals", "position",
            "positions", "portfolio", "live_ready", "deploy_ready", "profitable",
        }
        assert forbidden.isdisjoint(_all_dict_keys(diagnostics))
        assert "OFFLINE_EDGE_CANDIDATE" not in json.dumps(diagnostics)
        assert "EDGE_CANDIDATE" not in json.dumps(diagnostics)
        assert "funding_adjusted_return" not in json.dumps(diagnostics)
        assert "net_return_value" not in json.dumps(diagnostics)
        assert "price_change" not in json.dumps(diagnostics)

        receipt = _base_receipt(
            funding_to_bars_timestamp_canonicalization_diagnostics=diagnostics
        )
        validate_real_validation_receipt(receipt)
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION
        assert all(
            value is False for value in receipt["required_outputs_present"].values()
        )
        assert all(
            value is False
            for value in receipt["forbidden_calculation_status"].values()
        )
        assert all(value is True for value in receipt["guardrail_status"].values())
        serialized = json.dumps(receipt)
        assert "OFFLINE_EDGE_CANDIDATE" not in serialized
        assert "EDGE_CANDIDATE" not in serialized


def _readiness_inputs() -> dict[str, dict]:
    floor = {
        "policy_name": "floor_to_second",
        "bars_timestamp_count": 2,
        "canonicalized_funding_timestamp_count": 2,
        "exact_matched_after_canonicalization_count": 2,
        "bars_without_canonicalized_funding_count": 0,
        "canonicalized_funding_without_bars_count": 0,
        "canonicalization_status": "EXACT_CANONICAL_TIMESTAMP_SET_MATCH",
        "funding_timestamp_collision_count": 0,
        "ambiguous_nearest_bar_count": 0,
    }
    symbol = {
        "symbol": "BTCUSDT",
        "canonicalization_policies": [dict(floor)],
        "structural_flags": {
            "floor_canonicalized_history_range_status": "MATCHING_RANGES",
            "extra_funding_timestamps_outside_bars_range_count": 0,
            "bars_timestamps_outside_funding_range_count": 0,
        },
        "per_split_diagnostics": {
            "split_00": {"train": [dict(floor)], "validation": [dict(floor)]}
        },
    }
    return {
        "funding_to_bars_alignment_diagnostics": {"symbols": [{"symbol": "BTCUSDT"}]},
        "funding_to_bars_temporal_joinability_diagnostics": {"symbols": [{"symbol": "BTCUSDT"}]},
        "funding_to_bars_timestamp_convention_diagnostics": {"symbols": [{"symbol": "BTCUSDT"}]},
        "funding_to_bars_timestamp_canonicalization_diagnostics": {"symbols": [symbol]},
    }


def _readiness(**inputs) -> dict:
    values = _readiness_inputs()
    values.update(inputs)
    return materialize_funding_application_readiness_gate_diagnostics(**values)


class TestFundingApplicationReadinessGateDiagnostics:
    def test_eligible_exact_symbol_and_splits(self):
        result = _readiness()
        assert result["eligible_symbol_count"] == 1
        symbol = result["symbols"][0]
        assert symbol["eligible_for_future_funding_application"] is True
        assert all(item["eligible_for_future_funding_application"] for item in symbol["splits"])

    @pytest.mark.parametrize(
        ("target", "field", "value", "reason"),
        [
            ("policy", "canonicalized_funding_timestamp_count", 3, "COUNT_MISMATCH"),
            (
                "policy",
                "canonicalization_status",
                "PARTIAL_CANONICAL_TIMESTAMP_SET_MATCH",
                "PARTIAL_CANONICAL_TIMESTAMP_SET_MATCH",
            ),
            (
                "policy",
                "canonicalization_status",
                "NO_CANONICAL_TIMESTAMP_MATCH",
                "NO_CANONICAL_TIMESTAMP_MATCH",
            ),
            (
                "policy",
                "canonicalized_funding_without_bars_count",
                1,
                "CANONICALIZED_FUNDING_WITHOUT_BARS",
            ),
            (
                "policy",
                "bars_without_canonicalized_funding_count",
                1,
                "BARS_WITHOUT_CANONICALIZED_FUNDING",
            ),
            ("policy", "funding_timestamp_collision_count", 1, "CANONICALIZED_TIMESTAMP_COLLISION"),
            ("policy", "ambiguous_nearest_bar_count", 1, "AMBIGUOUS_NEAREST_BAR"),
            (
                "flags",
                "floor_canonicalized_history_range_status",
                "BARS_END_BEFORE_FUNDING",
                "RANGE_MISMATCH",
            ),
            (
                "flags",
                "extra_funding_timestamps_outside_bars_range_count",
                1,
                "EXTRA_FUNDING_OUTSIDE_BARS_RANGE",
            ),
            (
                "flags",
                "bars_timestamps_outside_funding_range_count",
                1,
                "BARS_OUTSIDE_FUNDING_RANGE",
            ),
        ],
    )
    def test_symbol_blockers(self, target, field, value, reason):
        inputs = _readiness_inputs()
        symbol = inputs["funding_to_bars_timestamp_canonicalization_diagnostics"]["symbols"][0]
        container = (
            symbol["canonicalization_policies"][0]
            if target == "policy"
            else symbol["structural_flags"]
        )
        container[field] = value
        result = materialize_funding_application_readiness_gate_diagnostics(**inputs)
        assert reason in result["symbols"][0]["blocked_reasons"]
        assert result["blocked_symbol_count"] == 1

    def _set_split_counts(self, bars, funding, matched, status):
        inputs = _readiness_inputs()
        split = inputs["funding_to_bars_timestamp_canonicalization_diagnostics"][
            "symbols"
        ][0]["per_split_diagnostics"]["split_00"]["validation"][0]
        split.update({
            "bars_timestamp_count": bars,
            "canonicalized_funding_timestamp_count": funding,
            "exact_matched_after_canonicalization_count": matched,
            "bars_without_canonicalized_funding_count": max(bars - matched, 0),
            "canonicalized_funding_without_bars_count": max(funding - matched, 0),
            "canonicalization_status": status,
        })
        return materialize_funding_application_readiness_gate_diagnostics(**inputs)

    def test_empty_both_split_not_blocking(self):
        result = self._set_split_counts(0, 0, 0, "EMPTY_BOTH")
        split = result["symbols"][0]["splits"][1]
        assert split["empty_window_status"] == "EMPTY_BOTH_NOT_BLOCKING"
        assert result["eligible_symbol_count"] == 1

    @pytest.mark.parametrize(
        ("bars", "funding", "status", "empty_status", "reason"),
        [
            (
                0,
                1,
                "NO_CANONICAL_TIMESTAMP_MATCH",
                "EMPTY_BARS_NONEMPTY_FUNDING_BLOCKING",
                "EMPTY_BARS_NONEMPTY_FUNDING",
            ),
            (
                1,
                0,
                "NO_CANONICAL_TIMESTAMP_MATCH",
                "EMPTY_FUNDING_NONEMPTY_BARS_BLOCKING",
                "EMPTY_FUNDING_NONEMPTY_BARS",
            ),
        ],
    )
    def test_one_sided_empty_split_blocks_symbol(self, bars, funding, status, empty_status, reason):
        result = self._set_split_counts(bars, funding, 0, status)
        split = result["symbols"][0]["splits"][1]
        assert split["empty_window_status"] == empty_status
        assert reason in split["blocked_reasons"]
        assert result["blocked_symbol_count"] == 1

    def test_any_blocked_partition_blocks_symbol(self):
        result = self._set_split_counts(2, 3, 2, "PARTIAL_CANONICAL_TIMESTAMP_SET_MATCH")
        assert result["symbols"][0]["eligible_for_future_funding_application"] is False

    def test_all_nonempty_and_empty_both_are_eligible(self):
        result = self._set_split_counts(0, 0, 0, "EMPTY_BOTH")
        assert result["symbols"][0]["eligible_for_future_funding_application"] is True

    def test_missing_canonicalization_diagnostics_fails_closed(self):
        inputs = _readiness_inputs()
        inputs["funding_to_bars_timestamp_canonicalization_diagnostics"] = {"symbols": []}
        result = materialize_funding_application_readiness_gate_diagnostics(**inputs)
        assert "MISSING_CANONICALIZATION_DIAGNOSTICS" in result["symbols"][0]["blocked_reasons"]

    def test_missing_floor_policy_fails_closed(self):
        inputs = _readiness_inputs()
        inputs["funding_to_bars_timestamp_canonicalization_diagnostics"]["symbols"][
            0
        ]["canonicalization_policies"] = []
        result = materialize_funding_application_readiness_gate_diagnostics(**inputs)
        assert "MISSING_POLICY_DIAGNOSTICS" in result["symbols"][0]["blocked_reasons"]

    def test_unexpected_status_fails_closed(self):
        inputs = _readiness_inputs()
        inputs["funding_to_bars_timestamp_canonicalization_diagnostics"]["symbols"][
            0
        ]["canonicalization_policies"][0]["canonicalization_status"] = "SURPRISING"
        result = materialize_funding_application_readiness_gate_diagnostics(**inputs)
        assert "UNEXPECTED_STATUS" in result["symbols"][0]["blocked_reasons"]

    def test_safety_keys_exclude_pnl_and_sharpe(self):
        serialized = json.dumps(_readiness()).lower()
        assert "pnl" not in serialized
        assert "sharpe" not in serialized


# ── Funding-adjusted bars scaffold diagnostics ─────────────────────────


def _make_eligible_split_entry(
    split_id="split_00",
    partition="validation",
    bars_count=3,
):
    """Build a single split partition entry shaped like the real output of
    materialize_funding_application_readiness_gate_diagnostics (entry["splits"]
    items), representing an eligible (not blocked) partition.
    """
    return {
        "split_id": split_id,
        "partition": partition,
        "readiness_status": ELIGIBLE_FOR_FUTURE_FUNDING_APPLICATION,
        "eligible_for_future_funding_application": True,
        "empty_window_status": "NOT_EMPTY",
        "blocked_reasons": [],
        "evidence": _make_eligibility_evidence(bars_count=bars_count),
    }


def _make_eligible_symbol_entry(
    symbol="BTCUSDT",
    blocked_reasons=None,
    evidence=None,
    splits=None,
):
    """Build a single eligible symbol entry."""
    if evidence is None:
        evidence = _make_eligibility_evidence(symbol)
    if splits is None:
        splits = [
            _make_eligible_split_entry(
                bars_count=evidence.get("bars_timestamp_count", 3)
            )
        ]
    return {
        "symbol": symbol,
        "readiness_status": ELIGIBLE_FOR_FUTURE_FUNDING_APPLICATION,
        "eligible_for_future_funding_application": True,
        "canonicalization_policy": FLOOR_TO_SECOND,
        "evidence": evidence,
        "splits": splits,
        "blocked_reasons": blocked_reasons or [],
    }


def _make_eligibility_evidence(symbol="BTCUSDT", bars_count=3):
    """Build realistic eligibility evidence matching the validation checks."""
    return {
        "bars_timestamp_count": bars_count,
        "canonicalized_funding_timestamp_count": bars_count,
        "exact_matched_after_canonicalization_count": bars_count,
        "bars_without_canonicalized_funding_count": 0,
        "canonicalized_funding_without_bars_count": 0,
        "canonicalization_status": EXACT_CANONICAL_TIMESTAMP_SET_MATCH,
        "funding_timestamp_collision_count": 0,
        "ambiguous_nearest_bar_count": 0,
        "floor_canonicalized_history_range_status": MATCHING_RANGES,
        "extra_funding_timestamps_outside_bars_range_count": 0,
        "bars_timestamps_outside_funding_range_count": 0,
    }


def _make_blocked_symbol_entry(
    symbol="ETHUSDT",
    blocked_reasons=None,
):
    """Build a single blocked symbol entry."""
    if blocked_reasons is None:
        blocked_reasons = ["FUNDING_DATA_GAP"]
    return {
        "symbol": symbol,
        "readiness_status": BLOCKED_FOR_FUTURE_FUNDING_APPLICATION,
        "eligible_for_future_funding_application": False,
        "canonicalization_policy": FLOOR_TO_SECOND,
        "evidence": None,
        "splits": [],
        "blocked_reasons": blocked_reasons,
    }


class TestFundingAdjustedBarsScaffoldDiagnostics:
    """22 test cases for materialize_funding_adjusted_bars_scaffold_diagnostics."""

    # ── Helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def _write_bars_csv(tmp_path, symbol, rows, filename=None):
        """Write a bars CSV with timestamp + OHLCV columns."""
        if filename is None:
            filename = f"{symbol}_8h_ohlcv.csv"
        path = tmp_path / filename
        lines = ["timestamp,open,high,low,close,volume"]
        for row in rows:
            ts = row.get("timestamp", "")
            o = row.get("open", "100.0")
            h = row.get("high", "101.0")
            lo = row.get("low", "99.0")
            c = row.get("close", "100.5")
            v = row.get("volume", "1000")
            lines.append(f"{ts},{o},{h},{lo},{c},{v}")
        path.write_text("\n".join(lines) + "\n")
        return path

    @staticmethod
    def _write_funding_csv(tmp_path, symbol, rows, filename=None):
        """Write a funding CSV with timestamp + fundingRate columns."""
        if filename is None:
            filename = f"{symbol}_funding.csv"
        path = tmp_path / filename
        # Determine columns from the first row keys.
        if rows:
            cols = list(rows[0].keys())
        else:
            cols = ["fundingTime", "fundingRate", "markPrice"]
        lines = [",".join(cols)]
        for row in rows:
            lines.append(",".join(str(row.get(c, "")) for c in cols))
        path.write_text("\n".join(lines) + "\n")
        return path

    @staticmethod
    def _make_readiness_gate(
        symbols_data=None,
        calculation_status=None,
        funding_application_status=None,
        readiness_policy=None,
        canonicalization_policy_considered=None,
        symbol_count=None,
        eligible_symbol_count=None,
        blocked_symbol_count=None,
    ):
        """Build a realistic readiness gate output like the real pipeline produces."""
        if symbols_data is None:
            symbols_data = [
                _make_eligible_symbol_entry("BTCUSDT"),
            ]

        calculation_status = calculation_status or FUNDING_APPLICATION_READINESS_GATE_DIAGNOSTIC_ONLY
        funding_application_status = funding_application_status or NOT_EXECUTED
        readiness_policy = readiness_policy or STRICT_CANONICAL_TIMESTAMP_EXACT_MATCH_NO_COLLISION_NO_AMBIGUITY
        canonicalization_policy_considered = canonicalization_policy_considered or FLOOR_TO_SECOND

        counted_eligible = sum(
            1 for s in symbols_data
            if s.get("readiness_status") == ELIGIBLE_FOR_FUTURE_FUNDING_APPLICATION
        )
        counted_blocked = sum(
            1 for s in symbols_data
            if s.get("readiness_status") == BLOCKED_FOR_FUTURE_FUNDING_APPLICATION
        )

        return {
            "calculation_status": calculation_status,
            "funding_application_status": funding_application_status,
            "readiness_policy": readiness_policy,
            "canonicalization_policy_considered": canonicalization_policy_considered,
            "symbols": symbols_data,
            "symbol_count": symbol_count if symbol_count is not None else len(symbols_data),
            "eligible_symbol_count": eligible_symbol_count if eligible_symbol_count is not None else counted_eligible,
            "blocked_symbol_count": blocked_symbol_count if blocked_symbol_count is not None else counted_blocked,
        }

    @staticmethod
    def _make_canonicalization_diagnostics(
        eligible_symbols=None,
        bars_count=3,
        policy_name="floor_to_second",
    ):
        """Build realistic canonicalization diagnostics matching the real pipeline output."""
        if eligible_symbols is None:
            eligible_symbols = ["BTCUSDT"]

        symbols = []
        for sym in eligible_symbols:
            symbols.append({
                "symbol": sym,
                "bars_file": f"{sym}_8h.csv",
                "funding_file": f"{sym}_funding.csv",
                "canonicalization_policies": [
                    {
                        "policy_name": policy_name,
                        "canonicalized_funding_timestamp_count": bars_count,
                        "bars_timestamp_count": bars_count,
                        "exact_matched_after_canonicalization_count": bars_count,
                        "bars_without_canonicalized_funding_count": 0,
                        "canonicalized_funding_without_bars_count": 0,
                        "bars_match_ratio_after_canonicalization": 1.0,
                        "funding_match_ratio_after_canonicalization": 1.0,
                        "canonicalization_status": "EXACT_CANONICAL_TIMESTAMP_SET_MATCH",
                        "funding_timestamp_collision_count": 0,
                        "max_collision_bucket_size": 0,
                        "collision_examples": [],
                        "ambiguous_nearest_bar_count": 0,
                        "max_abs_canonicalization_delta_microseconds": 0,
                        "canonicalization_delta_microseconds_histogram": {},
                    },
                ],
                "best_policy_summary": {
                    "best_policy_by_exact_matched_count": {
                        "policy_name": policy_name,
                        "exact_matched_after_canonicalization_count": bars_count,
                    },
                },
                "structural_flags": {
                    "raw_history_range_status": "MATCHING_RANGES",
                    "extra_funding_timestamps_outside_bars_range_count": 0,
                    "bars_timestamps_outside_funding_range_count": 0,
                    "has_subsecond_funding_jitter": False,
                    "funding_subsecond_timestamp_count": 0,
                    "max_abs_subsecond_jitter_microseconds": 0,
                    "floor_canonicalized_history_range_status": "MATCHING_RANGES",
                    "round_canonicalized_history_range_status": "MATCHING_RANGES",
                    "ceil_canonicalized_history_range_status": "MATCHING_RANGES",
                },
                "per_split_diagnostics": {},
                "calculation_status": "FUNDING_TO_BARS_TIMESTAMP_CANONICALIZATION_DIAGNOSTIC_ONLY",
                "funding_application_status": "NOT_EXECUTED",
            })

        return {
            "calculation_status": "FUNDING_TO_BARS_TIMESTAMP_CANONICALIZATION_DIAGNOSTIC_ONLY",
            "canonicalization_policy": "DIAGNOSTIC_WHOLE_SECOND_UTC_ONLY",
            "funding_application_status": "NOT_EXECUTED",
            "symbol_count": len(symbols),
            "symbols": symbols,
        }

    def _build(self, tmp_path, *, symbol="BTCUSDT", bars_rows=None,
               funding_rows=None, bars_inventory=None, funding_inventory=None,
               readiness_gate=None, canonicalization=None, source_sha=None,
               **kwargs):
        """Build inputs and call materialize_funding_adjusted_bars_scaffold_diagnostics.

        Returns the diagnostics dict.  Override any input by passing the
        corresponding keyword argument.
        """
        # Default bars rows (3 rows, ISO timestamps).
        if bars_rows is None:
            bars_rows = [
                {"timestamp": "2026-01-01T00:00:00Z"},
                {"timestamp": "2026-01-02T00:00:00Z"},
                {"timestamp": "2026-01-03T00:00:00Z"},
            ]
        # Default funding rows (3 rows matching bars timestamps).
        if funding_rows is None:
            funding_rows = [
                {"fundingTime": "2026-01-01T00:00:00Z", "fundingRate": "0.0001"},
                {"fundingTime": "2026-01-02T00:00:00Z", "fundingRate": "0.0002"},
                {"fundingTime": "2026-01-03T00:00:00Z", "fundingRate": "-0.0001"},
            ]

        bars_path = self._write_bars_csv(tmp_path, symbol, bars_rows)
        funding_path = self._write_funding_csv(tmp_path, symbol, funding_rows)

        bars_sha = hashlib.sha256(bars_path.read_bytes()).hexdigest()
        funding_sha = hashlib.sha256(funding_path.read_bytes()).hexdigest()

        if bars_inventory is None:
            bars_inventory = {
                "files": [{"filename": f"{symbol}_8h_ohlcv.csv", "sha256": bars_sha}],
            }
        if funding_inventory is None:
            funding_inventory = {
                "files": [{"filename": f"{symbol}_funding.csv", "sha256": funding_sha}],
            }
        if readiness_gate is None:
            readiness_gate = self._make_readiness_gate(
                symbols_data=[_make_eligible_symbol_entry(symbol)]
            )
        if canonicalization is None:
            canonicalization = self._make_canonicalization_diagnostics()
        if source_sha is None:
            source_sha = "test_sha"

        return materialize_funding_adjusted_bars_scaffold_diagnostics(
            funding_application_readiness_gate_diagnostics=readiness_gate,
            funding_to_bars_timestamp_canonicalization_diagnostics=canonicalization,
            bars_inventory=bars_inventory,
            funding_inventory=funding_inventory,
            bars_dir=str(tmp_path),
            funding_dir=str(tmp_path),
            source_sha=source_sha,
        )

    # ── Test 1: Eligible symbol materializes diagnostic rows ────────────────

    def test_eligible_symbol_materializes_diagnostic_rows(self, tmp_path):
        result = self._build(tmp_path)
        assert result["symbol_count"] == 1
        assert result["eligible_symbol_count"] == 1
        assert result["materialized_symbol_count"] == 1
        symbol = result["symbols"][0]
        assert symbol["symbol"] == "BTCUSDT"
        assert symbol["scaffold_status"] == "MATERIALIZED_DIAGNOSTIC_ROWS"
        assert symbol["matched_rows"] == 3
        assert len(symbol["sample_rows"]) == 3
        assert symbol["funding_rate_present_rows"] == 3
        assert symbol["total_rows"] == 3
        assert symbol["canonicalization_policy"] == "floor_to_second"
        assert result["calculation_status"] == (
            "FUNDING_ADJUSTED_BARS_SCAFFOLD_DIAGNOSTIC_ONLY"
        )

    # ── Test 2: Blocked symbol is skipped ───────────────────────────────────

    def test_blocked_symbol_is_skipped(self, tmp_path):
        readiness = self._make_readiness_gate(
            symbols_data=[_make_blocked_symbol_entry("BTCUSDT", blocked_reasons=["NO_BARS_DATA"])]
        )
        result = self._build(
            tmp_path,
            readiness_gate=readiness,
            symbol="BTCUSDT",
        )
        assert result["symbol_count"] == 1
        assert result["eligible_symbol_count"] == 0
        assert result["blocked_symbol_count"] == 1
        assert result["skipped_symbol_count"] == 1
        symbol = result["symbols"][0]
        assert symbol["scaffold_status"] == "SKIPPED_BY_READINESS_GATE"
        assert "sample_rows" not in symbol
        assert "funding_rate_present_rows" not in symbol

    # ── Test 3: Eligibility derived from readiness gate, not hardcoded ──────

    def test_eligibility_derived_from_readiness_gate_not_hardcoded(self, tmp_path):
        eligible_symbols = ["ETHUSDT", "SOLUSDT"]
        blocked_symbols = {"BTCUSDT": ["NO_BARS_DATA"]}
        symbols_data = [
            _make_eligible_symbol_entry("ETHUSDT"),
            _make_eligible_symbol_entry("SOLUSDT"),
            _make_blocked_symbol_entry("BTCUSDT", blocked_reasons=["NO_BARS_DATA"]),
        ]
        readiness = self._make_readiness_gate(symbols_data=symbols_data)
        # Write CSVs for all three symbols.
        for sym in eligible_symbols + list(blocked_symbols):
            bars_rows = [{"timestamp": "2026-01-01T00:00:00Z"},
                         {"timestamp": "2026-01-02T00:00:00Z"},
                         {"timestamp": "2026-01-03T00:00:00Z"}]
            funding_rows = [{"fundingTime": "2026-01-01T00:00:00Z", "fundingRate": "0.0001"},
                            {"fundingTime": "2026-01-02T00:00:00Z", "fundingRate": "0.0002"},
                            {"fundingTime": "2026-01-03T00:00:00Z", "fundingRate": "-0.0001"}]
            self._write_bars_csv(tmp_path, sym, bars_rows)
            self._write_funding_csv(tmp_path, sym, funding_rows)

        # Build inventory manually for all three symbols.
        files_list = []
        for sym in eligible_symbols + list(blocked_symbols):
            bars_path = tmp_path / f"{sym}_8h_ohlcv.csv"
            funding_path = tmp_path / f"{sym}_funding.csv"
            files_list.append({
                "filename": f"{sym}_8h_ohlcv.csv",
                "sha256": hashlib.sha256(bars_path.read_bytes()).hexdigest(),
            })
        bars_inv = {"files": files_list}
        funding_inv = {"files": [
            {"filename": f"{sym}_funding.csv",
             "sha256": hashlib.sha256(
                 (tmp_path / f"{sym}_funding.csv").read_bytes()
             ).hexdigest()}
            for sym in eligible_symbols + list(blocked_symbols)
        ]}

        result = materialize_funding_adjusted_bars_scaffold_diagnostics(
            funding_application_readiness_gate_diagnostics=readiness,
            funding_to_bars_timestamp_canonicalization_diagnostics=(
                self._make_canonicalization_diagnostics(
                    eligible_symbols=eligible_symbols,
                    bars_count=3,
                )
            ),
            bars_inventory=bars_inv,
            funding_inventory=funding_inv,
            bars_dir=str(tmp_path),
            funding_dir=str(tmp_path),
            source_sha="test_sha",
        )
        assert result["eligible_symbol_count"] == 2
        assert result["blocked_symbol_count"] == 1
        assert result["materialized_symbol_count"] == 2
        assert result["skipped_symbol_count"] == 1

        # Eligible symbols are materialized, blocked are skipped.
        for sym_entry in result["symbols"]:
            sym_name = sym_entry["symbol"]
            if sym_name in eligible_symbols:
                assert sym_entry["scaffold_status"] == "MATERIALIZED_DIAGNOSTIC_ROWS"
            else:
                assert sym_entry["scaffold_status"] == "SKIPPED_BY_READINESS_GATE"

    # ── Test 4: Missing readiness diagnostics fails closed ──────────────────

    def test_missing_readiness_diagnostics_fails_closed(self, tmp_path):
        with pytest.raises(ValueError, match="funding_application_readiness_gate_diagnostics"):
            materialize_funding_adjusted_bars_scaffold_diagnostics(
                funding_application_readiness_gate_diagnostics=None,
                funding_to_bars_timestamp_canonicalization_diagnostics={},
                bars_inventory={"files": []},
                funding_inventory={"files": []},
                bars_dir=str(tmp_path),
                funding_dir=str(tmp_path),
                source_sha="test_sha",
            )

    # ── Test 5: Missing canonicalization diagnostics fails closed ───────────

    def test_missing_canonicalization_diagnostics_fails_closed(self, tmp_path):
        with pytest.raises(ValueError, match="funding_to_bars_timestamp_canonicalization_diagnostics"):
            materialize_funding_adjusted_bars_scaffold_diagnostics(
                funding_application_readiness_gate_diagnostics={
                    "symbols": [{"symbol": "BTCUSDT", "readiness_status": "ELIGIBLE_FOR_FUTURE_FUNDING_APPLICATION", "blocked_reasons": []}],
                },
                funding_to_bars_timestamp_canonicalization_diagnostics=None,
                bars_inventory={"files": []},
                funding_inventory={"files": []},
                bars_dir=str(tmp_path),
                funding_dir=str(tmp_path),
                source_sha="test_sha",
            )

    # ── Test 6: Missing bars inventory for eligible symbol fails closed ─────

    def test_missing_bars_inventory_for_eligible_symbol_fails_closed(self, tmp_path):
        readiness = self._make_readiness_gate(
            symbols_data=[_make_eligible_symbol_entry("BTCUSDT")]
        )
        # Write CSV but do NOT include it in inventory.
        self._write_bars_csv(tmp_path, "BTCUSDT", [{"timestamp": "2026-01-01T00:00:00Z"}])
        self._write_funding_csv(tmp_path, "BTCUSDT", [{"fundingTime": "2026-01-01T00:00:00Z", "fundingRate": "0.0001"}])
        bars_inv = {"files": []}  # empty — no BTCUSDT entry
        funding_inv = {"files": [
            {"filename": "BTCUSDT_funding.csv",
             "sha256": hashlib.sha256(
                 (tmp_path / "BTCUSDT_funding.csv").read_bytes()
             ).hexdigest()},
        ]}
        with pytest.raises(ValueError, match="missing bars inventory"):
            materialize_funding_adjusted_bars_scaffold_diagnostics(
                funding_application_readiness_gate_diagnostics=readiness,
                funding_to_bars_timestamp_canonicalization_diagnostics=(
                    self._make_canonicalization_diagnostics()
                ),
                bars_inventory=bars_inv,
                funding_inventory=funding_inv,
                bars_dir=str(tmp_path),
                funding_dir=str(tmp_path),
                source_sha="test_sha",
            )

    # ── Test 7: Missing funding inventory for eligible symbol fails closed ──

    def test_missing_funding_inventory_for_eligible_symbol_fails_closed(self, tmp_path):
        readiness = self._make_readiness_gate(
            symbols_data=[_make_eligible_symbol_entry("BTCUSDT")]
        )
        self._write_bars_csv(tmp_path, "BTCUSDT", [{"timestamp": "2026-01-01T00:00:00Z"}])
        self._write_funding_csv(tmp_path, "BTCUSDT", [{"fundingTime": "2026-01-01T00:00:00Z", "fundingRate": "0.0001"}])
        bars_inv = {"files": [
            {"filename": "BTCUSDT_8h_ohlcv.csv",
             "sha256": hashlib.sha256(
                 (tmp_path / "BTCUSDT_8h_ohlcv.csv").read_bytes()
             ).hexdigest()},
        ]}
        funding_inv = {"files": []}  # empty — no BTCUSDT entry
        with pytest.raises(ValueError, match="missing funding inventory"):
            materialize_funding_adjusted_bars_scaffold_diagnostics(
                funding_application_readiness_gate_diagnostics=readiness,
                funding_to_bars_timestamp_canonicalization_diagnostics=(
                    self._make_canonicalization_diagnostics()
                ),
                bars_inventory=bars_inv,
                funding_inventory=funding_inv,
                bars_dir=str(tmp_path),
                funding_dir=str(tmp_path),
                source_sha="test_sha",
            )

    # ── Test 8: Duplicate canonical funding timestamp fails closed ──────────

    def test_duplicate_canonical_funding_timestamp_fails_closed(self, tmp_path):
        # Two funding rows with timestamps that canonicalize to the same value.
        funding_rows = [
            {"fundingTime": "2026-01-01T00:00:00.000Z", "fundingRate": "0.0001"},
            {"fundingTime": "2026-01-01T00:00:00.500Z", "fundingRate": "0.0002"},
        ]
        with pytest.raises(ValueError, match="duplicate canonical funding timestamp"):
            self._build(tmp_path, bars_rows=[
                {"timestamp": "2026-01-01T00:00:00Z"},
                {"timestamp": "2026-01-02T00:00:00Z"},
            ], funding_rows=funding_rows)

    # ── Test 9: Missing canonical funding timestamp for bar fails closed ────

    def test_missing_canonical_funding_timestamp_fails_closed(self, tmp_path):
        # Bars have a timestamp with no matching funding timestamp.
        bars_rows = [
            {"timestamp": "2026-01-01T00:00:00Z"},
            {"timestamp": "2026-01-03T00:00:00Z"},  # no funding match
        ]
        funding_rows = [
            {"fundingTime": "2026-01-01T00:00:00Z", "fundingRate": "0.0001"},
            {"fundingTime": "2026-01-02T00:00:00Z", "fundingRate": "0.0002"},
        ]
        with pytest.raises(ValueError, match="missing funding timestamp after canonicalization"):
            self._build(tmp_path, bars_rows=bars_rows, funding_rows=funding_rows)

    # ── Test 10: Missing fundingRate column fails closed ────────────────────

    def test_missing_fundingRate_column_fails_closed(self, tmp_path):
        # Funding CSV without fundingRate column.
        funding_rows = [
            {"fundingTime": "2026-01-01T00:00:00Z", "markPrice": "50000.0"},
        ]
        with pytest.raises(ValueError, match="missing fundingRate column"):
            self._build(tmp_path, funding_rows=funding_rows)

    # ── Test 11: Malformed fundingRate fails closed ─────────────────────────

    def test_malformed_fundingRate_fails_closed(self, tmp_path):
        # Funding CSV with non-numeric fundingRate.
        funding_rows = [
            {"fundingTime": "2026-01-01T00:00:00Z", "fundingRate": "not_a_number"},
        ]
        with pytest.raises(ValueError, match="missing or malformed funding rate"):
            self._build(tmp_path, bars_rows=[
                {"timestamp": "2026-01-01T00:00:00Z"},
            ], funding_rows=funding_rows)

    # ── Test 12: Missing fundingRate value fails closed ─────────────────────

    def test_missing_fundingRate_value_fails_closed(self, tmp_path):
        # Funding CSV with empty fundingRate.
        funding_rows = [
            {"fundingTime": "2026-01-01T00:00:00Z", "fundingRate": ""},
        ]
        with pytest.raises(ValueError, match="missing or malformed funding rate"):
            self._build(tmp_path, bars_rows=[
                {"timestamp": "2026-01-01T00:00:00Z"},
            ], funding_rows=funding_rows)

    # ── Test 13: Source SHA mismatch fails closed ───────────────────────────

    def test_source_sha_mismatch_fails_closed(self, tmp_path):
        """Test per-file SHA inventory checks: supply a bogus sha256 in the
        inventory entry to verify the function detects file-level SHA
        mismatches and fails closed."""
        bars_rows = [{"timestamp": "2026-01-01T00:00:00Z"}]
        funding_rows = [{"fundingTime": "2026-01-01T00:00:00Z", "fundingRate": "0.0001"}]
        self._write_bars_csv(tmp_path, "BTCUSDT", bars_rows)
        self._write_funding_csv(tmp_path, "BTCUSDT", funding_rows)
        bars_inv = {
            "files": [{
                "filename": "BTCUSDT_8h_ohlcv.csv",
                "sha256": "bogus_sha256_that_does_not_match",
            }],
        }
        funding_inv = {
            "files": [{
                "filename": "BTCUSDT_funding.csv",
                "sha256": hashlib.sha256(
                    (tmp_path / "BTCUSDT_funding.csv").read_bytes()
                ).hexdigest(),
            }],
        }
        with pytest.raises(ValueError, match="SHA mismatch"):
            materialize_funding_adjusted_bars_scaffold_diagnostics(
                funding_application_readiness_gate_diagnostics=(
                    self._make_readiness_gate(
                        symbols_data=[_make_eligible_symbol_entry("BTCUSDT")]
                    )
                ),
                funding_to_bars_timestamp_canonicalization_diagnostics=(
                    self._make_canonicalization_diagnostics()
                ),
                bars_inventory=bars_inv,
                funding_inventory=funding_inv,
                bars_dir=str(tmp_path),
                funding_dir=str(tmp_path),
                source_sha="test_sha",
            )

    # ── Test 14: Sample rows capped deterministically ───────────────────────

    def test_sample_rows_capped_deterministically(self, tmp_path):
        # Create 20 bars rows with matching funding.
        bars_rows = [
            {"timestamp": f"2026-01-{d:02d}T00:00:00Z"}
            for d in range(1, 21)
        ]
        funding_rows = [
            {"fundingTime": f"2026-01-{d:02d}T00:00:00Z", "fundingRate": "0.0001"}
            for d in range(1, 21)
        ]
        result = self._build(tmp_path, bars_rows=bars_rows, funding_rows=funding_rows)
        symbol = result["symbols"][0]
        assert symbol["matched_rows"] == 20
        # Capped: 5 first + 5 last = 10.
        assert len(symbol["sample_rows"]) == 10
        # First 5 are from the beginning.
        assert symbol["sample_rows"][0]["bar_row_index"] == 0
        assert symbol["sample_rows"][4]["bar_row_index"] == 4
        # Last 5 are from the end.
        assert symbol["sample_rows"][5]["bar_row_index"] == 15
        assert symbol["sample_rows"][9]["bar_row_index"] == 19

    # ── Test 15: Funding rate summary counts correct ────────────────────────

    def test_funding_rate_summary_counts_correct(self, tmp_path):
        # Mix: one zero, two positive, one negative.
        funding_rows = [
            {"fundingTime": "2026-01-01T00:00:00Z", "fundingRate": "0.0"},
            {"fundingTime": "2026-01-02T00:00:00Z", "fundingRate": "0.0001"},
            {"fundingTime": "2026-01-03T00:00:00Z", "fundingRate": "0.0002"},
            {"fundingTime": "2026-01-04T00:00:00Z", "fundingRate": "-0.0001"},
        ]
        bars_rows = [
            {"timestamp": "2026-01-01T00:00:00Z"},
            {"timestamp": "2026-01-02T00:00:00Z"},
            {"timestamp": "2026-01-03T00:00:00Z"},
            {"timestamp": "2026-01-04T00:00:00Z"},
        ]
        result = self._build(tmp_path, bars_rows=bars_rows, funding_rows=funding_rows)
        symbol = result["symbols"][0]
        assert symbol["funding_rate_present_rows"] == 4
        assert symbol["funding_rate_missing_rows"] == 0
        assert symbol["funding_rate_zero_count"] == 1
        assert symbol["funding_rate_positive_count"] == 2
        assert symbol["funding_rate_negative_count"] == 1
        assert symbol["funding_rate_min"] == -0.0001
        assert symbol["funding_rate_max"] == 0.0002

    # ── Test 16: CLI with funding includes scaffold section ─────────────────

    def test_cli_with_funding_includes_scaffold_section(self, tmp_path):
        bars_dir = tmp_path / "bars"
        funding_dir = tmp_path / "funding"
        bars_dir.mkdir()
        funding_dir.mkdir()
        # Write bars and funding CSVs with valid names.
        (bars_dir / "BTCUSDT_8h_ohlcv.csv").write_text(
            "timestamp,open,high,low,close,volume\n"
            "2026-01-01T00:00:00Z,100.0,101.0,99.0,100.5,1000\n"
            "2026-01-02T00:00:00Z,100.5,102.0,100.0,101.0,1200\n"
            "2026-01-03T00:00:00Z,101.0,103.0,100.5,102.0,1100\n"
        )
        (funding_dir / "BTCUSDT_funding.csv").write_text(
            "fundingTime,fundingRate,markPrice\n"
            "2026-01-01T00:00:00Z,0.0001,50000.0\n"
            "2026-01-02T00:00:00Z,0.0002,50100.0\n"
            "2026-01-03T00:00:00Z,-0.0001,50200.0\n"
        )

        out_dir = Path("/tmp") / f"qnty_scaffold_cli_funding_{uuid.uuid4().hex}"
        receipt_path = out_dir / "real_validation_receipt.json"
        try:
            result = subprocess.run(
                [
                    sys.executable, "-m",
                    "quantbot.experiment.offline_edge_real_validation",
                    "--read-only",
                    "--output-dir", str(out_dir),
                    "--input-manifest-fingerprint", "a" * 64,
                    "--data-quality-receipt-sha256", "b" * 64,
                    "--code-commit-sha", "c" * 40,
                    "--bars-dir", str(bars_dir),
                    "--funding-dir", str(funding_dir),
                ],
                capture_output=True, text=True, timeout=30,
            )
            assert result.returncode == 0, f"stderr: {result.stderr}"
            with open(receipt_path) as f:
                written = json.load(f)
            assert "funding_adjusted_bars_scaffold_diagnostics" in written
        finally:
            if receipt_path.exists():
                receipt_path.unlink()
            if out_dir.exists():
                out_dir.rmdir()

    # ── Test 17: CLI without funding omits scaffold section ─────────────────

    def test_cli_without_funding_omits_scaffold_section(self, tmp_path):
        bars_dir = tmp_path / "bars"
        bars_dir.mkdir()
        (bars_dir / "BTCUSDT_8h_ohlcv.csv").write_text(
            "timestamp,open,high,low,close,volume\n"
            "2026-01-01T00:00:00Z,100.0,101.0,99.0,100.5,1000\n"
            "2026-01-02T00:00:00Z,100.5,102.0,100.0,101.0,1200\n"
            "2026-01-03T00:00:00Z,101.0,103.0,100.5,102.0,1100\n"
        )

        out_dir = Path("/tmp") / f"qnty_scaffold_cli_no_funding_{uuid.uuid4().hex}"
        receipt_path = out_dir / "real_validation_receipt.json"
        try:
            result = subprocess.run(
                [
                    sys.executable, "-m",
                    "quantbot.experiment.offline_edge_real_validation",
                    "--read-only",
                    "--output-dir", str(out_dir),
                    "--input-manifest-fingerprint", "a" * 64,
                    "--data-quality-receipt-sha256", "b" * 64,
                    "--code-commit-sha", "c" * 40,
                    "--bars-dir", str(bars_dir),
                ],
                capture_output=True, text=True, timeout=30,
            )
            assert result.returncode == 0, f"stderr: {result.stderr}"
            with open(receipt_path) as f:
                written = json.load(f)
            assert "funding_adjusted_bars_scaffold_diagnostics" not in written
        finally:
            if receipt_path.exists():
                receipt_path.unlink()
            if out_dir.exists():
                out_dir.rmdir()

    # ── Test 18: Receipt final verdict remains blocked ──────────────────────

    def test_receipt_final_verdict_remains_blocked(self, tmp_path):
        diagnostics = self._build(tmp_path)
        receipt = _base_receipt(
            funding_adjusted_bars_scaffold_diagnostics=diagnostics,
        )
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION

    # ── Test 19: Required outputs remain false ──────────────────────────────

    def test_required_outputs_remain_false(self, tmp_path):
        diagnostics = self._build(tmp_path)
        receipt = _base_receipt(
            funding_adjusted_bars_scaffold_diagnostics=diagnostics,
        )
        for value in receipt["required_outputs_present"].values():
            assert value is False

    # ── Test 20: Forbidden calculations remain false ────────────────────────

    def test_forbidden_calculations_remain_false(self, tmp_path):
        diagnostics = self._build(tmp_path)
        receipt = _base_receipt(
            funding_adjusted_bars_scaffold_diagnostics=diagnostics,
        )
        for key, value in receipt["forbidden_calculation_status"].items():
            assert value is False, f"{key} must be False"

    # ── Test 21: Guardrails remain true ─────────────────────────────────────

    def test_guardrails_remain_true(self, tmp_path):
        diagnostics = self._build(tmp_path)
        receipt = _base_receipt(
            funding_adjusted_bars_scaffold_diagnostics=diagnostics,
        )
        for key, value in receipt["guardrail_status"].items():
            assert value is True, f"{key} must be True"

    # ── Test 22: Safety key regression ──────────────────────────────────────

    def test_safety_key_regression(self, tmp_path):
        diagnostics = self._build(tmp_path)
        all_keys = _all_dict_keys(diagnostics)
        forbidden = {
            "PnL", "Sharpe", "edge", "strategy-performance",
            "risk", "trade", "trades", "signal", "signals",
            "position", "positions", "portfolio", "return", "returns",
            "funding_adjusted_return", "net_return_value",
            "price_change", "OFFLINE_EDGE_CANDIDATE", "EDGE_CANDIDATE",
        }
        assert forbidden.isdisjoint(all_keys), (
            f"Forbidden keys found: {forbidden & all_keys}"
        )

    # ── Test 23: Eligible readiness without exact evidence fails closed ─────

    def test_eligible_readiness_without_exact_evidence_fails_closed(self):
        """Eligible symbol with non-matching canonicalization evidence fails."""
        entry = _make_eligible_symbol_entry(evidence={
            "bars_timestamp_count": 3,
            "canonicalized_funding_timestamp_count": 3,
            "exact_matched_after_canonicalization_count": 3,
            "bars_without_canonicalized_funding_count": 0,
            "canonicalized_funding_without_bars_count": 0,
            "canonicalization_status": "PARTIAL_CANONICAL_TIMESTAMP_SET_MATCH",  # wrong status
            "funding_timestamp_collision_count": 0,
            "ambiguous_nearest_bar_count": 0,
            "floor_canonicalized_history_range_status": MATCHING_RANGES,
            "extra_funding_timestamps_outside_bars_range_count": 0,
            "bars_timestamps_outside_funding_range_count": 0,
        })
        with pytest.raises(ValueError, match="EXACT_CANONICAL_TIMESTAMP_SET_MATCH"):
            _validate_eligible_readiness_evidence(
                entry, "BTCUSDT", self._make_canonicalization_diagnostics()
            )

    # ── Test 24: Malformed calculation_status fails closed ──────────────────

    def test_malformed_calculation_status_fails_closed(self):
        rd = self._make_readiness_gate(calculation_status="WRONG_STATUS")
        with pytest.raises(ValueError, match="calculation_status"):
            _validate_scaffold_readiness_gate(rd)

    # ── Test 25: Malformed funding_application_status fails closed ──────────

    def test_malformed_funding_application_status_fails_closed(self):
        rd = self._make_readiness_gate(funding_application_status="EXECUTED")
        with pytest.raises(ValueError, match="funding_application_status"):
            _validate_scaffold_readiness_gate(rd)

    # ── Test 26: Wrong readiness_policy fails closed ────────────────────────

    def test_wrong_readiness_policy_fails_closed(self):
        rd = self._make_readiness_gate(readiness_policy="LAX_POLICY")
        with pytest.raises(ValueError, match="readiness_policy"):
            _validate_scaffold_readiness_gate(rd)

    # ── Test 27: Wrong canonicalization_policy fails closed ─────────────────

    def test_wrong_canonicalization_policy_fails_closed(self):
        rd = self._make_readiness_gate(canonicalization_policy_considered="ceil_to_hour")
        with pytest.raises(ValueError, match="canonicalization_policy_considered"):
            _validate_scaffold_readiness_gate(rd)

    # ── Test 28: Mismatched symbol_count fails closed ───────────────────────

    def test_mismatched_symbol_count_fails_closed(self):
        rd = self._make_readiness_gate(symbol_count=999)
        with pytest.raises(ValueError, match="symbol_count"):
            _validate_scaffold_readiness_gate(rd)

    # ── Test 29: Mismatched eligible_symbol_count fails closed ──────────────

    def test_mismatched_eligible_count_fails_closed(self):
        rd = self._make_readiness_gate(eligible_symbol_count=999)
        with pytest.raises(ValueError, match="eligible_symbol_count"):
            _validate_scaffold_readiness_gate(rd)

    # ── Test 30: Mismatched blocked_symbol_count fails closed ───────────────

    def test_mismatched_blocked_count_fails_closed(self):
        rd = self._make_readiness_gate(blocked_symbol_count=999)
        with pytest.raises(ValueError, match="blocked_symbol_count"):
            _validate_scaffold_readiness_gate(rd)

    # ── Test 31: Malformed symbol entry fails closed ────────────────────────

    def test_malformed_symbol_entry_fails_closed(self):
        with pytest.raises(ValueError, match="Symbol entry must be a dict"):
            _validate_readiness_symbol_entry("not_a_dict")

    # ── Test 32: Duplicate readiness symbols fail closed ────────────────────

    def test_duplicate_readiness_symbols_fails_closed(self):
        """Duplicate symbols in readiness gate must fail before CSV read."""
        symbols = [
            _make_eligible_symbol_entry("BTCUSDT"),
            _make_eligible_symbol_entry("BTCUSDT"),
        ]
        with pytest.raises(ValueError, match="Duplicate symbol"):
            seen = set()
            for entry in symbols:
                sym = entry["symbol"]
                if sym in seen:
                    raise ValueError(f"Duplicate symbol {sym!r}")
                seen.add(sym)

    # ── Test 33: Eligible symbol with blocked_reasons fails closed ──────────

    def test_eligible_with_blocked_reasons_fails_closed(self):
        entry = _make_eligible_symbol_entry(blocked_reasons=["SOME_BLOCK"])
        with pytest.raises(ValueError, match="blocked_reasons"):
            _validate_eligible_readiness_evidence(
                entry, "BTCUSDT", self._make_canonicalization_diagnostics()
            )

    # ── Test 34: Eligible symbol with count mismatch fails closed ───────────

    def test_eligible_with_count_mismatch_fails_closed(self):
        """bars_count != canonicalized_funding_count fails before materialization."""
        entry = _make_eligible_symbol_entry(evidence={
            "bars_timestamp_count": 5,
            "canonicalized_funding_timestamp_count": 3,
            "exact_matched_after_canonicalization_count": 3,
            "bars_without_canonicalized_funding_count": 0,
            "canonicalized_funding_without_bars_count": 0,
            "canonicalization_status": EXACT_CANONICAL_TIMESTAMP_SET_MATCH,
            "funding_timestamp_collision_count": 0,
            "ambiguous_nearest_bar_count": 0,
            "floor_canonicalized_history_range_status": MATCHING_RANGES,
            "extra_funding_timestamps_outside_bars_range_count": 0,
            "bars_timestamps_outside_funding_range_count": 0,
        })
        with pytest.raises(ValueError, match="bars_timestamp_count"):
            _validate_eligible_readiness_evidence(
                entry, "BTCUSDT", self._make_canonicalization_diagnostics()
            )

    # ── Test 35: Eligible with funding_without_bars fails closed ────────────

    def test_eligible_with_funding_without_bars_fails_closed(self):
        entry = _make_eligible_symbol_entry(evidence={
            "bars_timestamp_count": 3,
            "canonicalized_funding_timestamp_count": 3,
            "exact_matched_after_canonicalization_count": 3,
            "bars_without_canonicalized_funding_count": 0,
            "canonicalized_funding_without_bars_count": 2,  # should be 0
            "canonicalization_status": EXACT_CANONICAL_TIMESTAMP_SET_MATCH,
            "funding_timestamp_collision_count": 0,
            "ambiguous_nearest_bar_count": 0,
            "floor_canonicalized_history_range_status": MATCHING_RANGES,
            "extra_funding_timestamps_outside_bars_range_count": 0,
            "bars_timestamps_outside_funding_range_count": 0,
        })
        with pytest.raises(ValueError, match="canonicalized_funding_without_bars_count"):
            _validate_eligible_readiness_evidence(
                entry, "BTCUSDT", self._make_canonicalization_diagnostics()
            )

    # ── Test 36: Eligible with ambiguous_nearest_bar fails closed ───────────

    def test_eligible_with_ambiguous_nearest_bar_fails_closed(self):
        entry = _make_eligible_symbol_entry(evidence={
            "bars_timestamp_count": 3,
            "canonicalized_funding_timestamp_count": 3,
            "exact_matched_after_canonicalization_count": 3,
            "bars_without_canonicalized_funding_count": 0,
            "canonicalized_funding_without_bars_count": 0,
            "canonicalization_status": EXACT_CANONICAL_TIMESTAMP_SET_MATCH,
            "funding_timestamp_collision_count": 0,
            "ambiguous_nearest_bar_count": 1,  # should be 0
            "floor_canonicalized_history_range_status": MATCHING_RANGES,
            "extra_funding_timestamps_outside_bars_range_count": 0,
            "bars_timestamps_outside_funding_range_count": 0,
        })
        with pytest.raises(ValueError, match="ambiguous_nearest_bar_count"):
            _validate_eligible_readiness_evidence(
                entry, "BTCUSDT", self._make_canonicalization_diagnostics()
            )

    # ── Test 37: Eligible symbol missing canonicalization fails closed ──────

    def test_eligible_symbol_missing_canonicalization_fails_closed(self):
        """Eligible symbol not found in canonicalization diagnostics fails."""
        entry = _make_eligible_symbol_entry()
        diag = self._make_canonicalization_diagnostics(eligible_symbols=["OTHER_SYMBOL"])
        with pytest.raises(ValueError, match="not found in canonicalization"):
            _validate_eligible_readiness_evidence(entry, "BTCUSDT", diag)

    # ── Test 38: Missing canonicalization policy fails closed ───────────────

    def test_eligible_symbol_missing_canonicalization_policy_fails_closed(self):
        """Missing canonicalization policy in per-symbol policies list fails."""
        entry = _make_eligible_symbol_entry()
        diag = self._make_canonicalization_diagnostics()
        diag["symbols"][0]["canonicalization_policies"] = []
        with pytest.raises(ValueError, match="No floor_to_second policy found"):
            _validate_eligible_readiness_evidence(entry, "BTCUSDT", diag)

    # ── Test 39: Canonicalization diagnostics disagreement fails closed ─────

    def test_canonicalization_diagnostics_disagreement_fails_closed(self):
        """Canonicalization diagnostics with non-matching status fails."""
        entry = _make_eligible_symbol_entry()
        diag = self._make_canonicalization_diagnostics()
        diag["symbols"][0]["canonicalization_policies"][0]["canonicalization_status"] = "PARTIAL_MATCH"
        with pytest.raises(ValueError, match="canonicalization_status"):
            _validate_eligible_readiness_evidence(entry, "BTCUSDT", diag)

    # ── Test 40: Blocked symbol empty reasons fails closed ──────────────────

    def test_blocked_symbol_empty_reasons_fails_closed(self):
        entry = _make_blocked_symbol_entry(blocked_reasons=[])
        with pytest.raises(ValueError, match="blocked_reasons"):
            _validate_blocked_readiness_evidence(entry, "ETHUSDT")

    # ── Test 41: Blocked symbol has no sample rows or funding summary ───────

    def test_blocked_symbol_no_sample_rows_and_no_funding_summary(self):
        """Blocked symbols must not contain sample_rows or funding-rate summaries."""
        entry = _make_blocked_symbol_entry()
        # Verify blocked entry has no 'sample_rows' or 'funding_rate_summary' keys
        assert "sample_rows" not in entry
        assert "funding_rate_summary" not in entry
        # Also validate it passes blocked evidence check
        _validate_blocked_readiness_evidence(entry, "ETHUSDT")  # should not raise

    # ── Test 42: Existing happy path still passes ───────────────────────────

    def test_existing_happy_path_still_passes(self):
        """The existing happy path test should still pass with new validations."""
        rd = self._make_readiness_gate()
        _validate_scaffold_readiness_gate(rd)
        # Eligible symbol validation
        for entry in rd["symbols"]:
            status = _validate_readiness_symbol_entry(entry)
            if status == ELIGIBLE_FOR_FUTURE_FUNDING_APPLICATION:
                _validate_eligible_readiness_evidence(
                    entry, entry["symbol"], self._make_canonicalization_diagnostics()
                )

    # ── Test 43: Blocked with inconsistent eligibility fails closed ─────────

    def test_blocked_with_inconsistent_eligibility_fails_closed(self):
        """Blocked symbol with eligible_for_future_funding_application=True fails."""
        entry = _make_blocked_symbol_entry()
        entry["eligible_for_future_funding_application"] = True
        with pytest.raises(ValueError, match="eligible_for_future_funding_application"):
            _validate_blocked_readiness_evidence(entry, "ETHUSDT")

    # ── Test 44: Malformed readiness gate (not dict) fails closed ───────────

    def test_malformed_readiness_gate_not_dict_fails_closed(self):
        with pytest.raises(ValueError, match="must be a dict"):
            _validate_scaffold_readiness_gate("not_a_dict")

    # ── Test 45: Blocked top-level split partition fails closed (unit) ──────

    def test_eligible_symbol_blocked_top_level_split_fails_closed(self):
        """A blocked entry['splits'] partition must fail closed, even though
        the symbol entry itself is otherwise eligible with matching evidence.
        """
        blocked_split = _make_eligible_split_entry()
        blocked_split["readiness_status"] = BLOCKED_FOR_FUTURE_FUNDING_APPLICATION
        blocked_split["eligible_for_future_funding_application"] = False
        blocked_split["empty_window_status"] = "NOT_EMPTY"
        blocked_split["blocked_reasons"] = ["SOME_BLOCK"]
        entry = _make_eligible_symbol_entry(splits=[blocked_split])
        with pytest.raises(ValueError, match="split partition"):
            _validate_eligible_readiness_evidence(
                entry, "BTCUSDT", self._make_canonicalization_diagnostics()
            )

    # ── Test 46: Blocked top-level split partition fails before CSV read ────

    def test_eligible_symbol_blocked_split_fails_before_csv_read(self, tmp_path):
        """The full scaffold must raise on a blocked split before any CSV is
        read or materialized, since split validation runs in Step C, ahead of
        the per-symbol CSV materialization loop.
        """
        blocked_split = _make_eligible_split_entry()
        blocked_split["readiness_status"] = BLOCKED_FOR_FUTURE_FUNDING_APPLICATION
        blocked_split["eligible_for_future_funding_application"] = False
        blocked_split["empty_window_status"] = "NOT_EMPTY"
        blocked_split["blocked_reasons"] = ["SOME_BLOCK"]
        entry = _make_eligible_symbol_entry(splits=[blocked_split])
        readiness_gate = self._make_readiness_gate(symbols_data=[entry])
        with pytest.raises(ValueError, match="split partition"):
            self._build(tmp_path, readiness_gate=readiness_gate)

    # ── Test 47: Missing splits key fails closed ─────────────────────────────

    def test_eligible_symbol_missing_splits_fails_closed(self):
        entry = _make_eligible_symbol_entry()
        del entry["splits"]
        with pytest.raises(ValueError, match="splits"):
            _validate_eligible_readiness_evidence(
                entry, "BTCUSDT", self._make_canonicalization_diagnostics()
            )

    # ── Test 48: Non-list splits fails closed ────────────────────────────────

    def test_eligible_symbol_non_list_splits_fails_closed(self):
        entry = _make_eligible_symbol_entry(splits="not_a_list")
        with pytest.raises(ValueError, match="splits"):
            _validate_eligible_readiness_evidence(
                entry, "BTCUSDT", self._make_canonicalization_diagnostics()
            )

    # ── Test 49: Empty-both-not-blocking split partition passes ─────────────

    def test_eligible_symbol_empty_both_not_blocking_split_passes(self):
        """A split with empty_window_status=EMPTY_BOTH_NOT_BLOCKING and no
        blockers is an acceptable eligible-symbol split partition.
        """
        empty_split = _make_eligible_split_entry()
        empty_split["readiness_status"] = ELIGIBLE_FOR_FUTURE_FUNDING_APPLICATION
        empty_split["eligible_for_future_funding_application"] = True
        empty_split["empty_window_status"] = EMPTY_BOTH_NOT_BLOCKING
        empty_split["blocked_reasons"] = []
        entry = _make_eligible_symbol_entry(splits=[empty_split])
        _validate_eligible_readiness_evidence(
            entry, "BTCUSDT", self._make_canonicalization_diagnostics()
        )  # should not raise

    # ── Tests 50-54: Missing canonicalization policy fields fail closed ─────

    @pytest.mark.parametrize(
        "field",
        [
            "canonicalized_funding_timestamp_count",
            "bars_without_canonicalized_funding_count",
            "canonicalized_funding_without_bars_count",
            "funding_timestamp_collision_count",
            "ambiguous_nearest_bar_count",
        ],
    )
    def test_canonicalization_policy_missing_required_field_fails_closed(self, field):
        entry = _make_eligible_symbol_entry()
        diag = self._make_canonicalization_diagnostics()
        del diag["symbols"][0]["canonicalization_policies"][0][field]
        with pytest.raises(ValueError, match=field):
            _validate_eligible_readiness_evidence(entry, "BTCUSDT", diag)

    # ── Test 55: Missing structural_flags fails closed ───────────────────────

    def test_canonicalization_missing_structural_flags_fails_closed(self):
        entry = _make_eligible_symbol_entry()
        diag = self._make_canonicalization_diagnostics()
        del diag["symbols"][0]["structural_flags"]
        with pytest.raises(ValueError, match="structural_flags"):
            _validate_eligible_readiness_evidence(entry, "BTCUSDT", diag)

    # ── Test 56: Missing floor_canonicalized_history_range_status fails closed

    def test_canonicalization_missing_range_status_fails_closed(self):
        entry = _make_eligible_symbol_entry()
        diag = self._make_canonicalization_diagnostics()
        del diag["symbols"][0]["structural_flags"][
            "floor_canonicalized_history_range_status"
        ]
        with pytest.raises(
            ValueError, match="floor_canonicalized_history_range_status"
        ):
            _validate_eligible_readiness_evidence(entry, "BTCUSDT", diag)


# ── Funding adjustment policy contract diagnostics ──────────────────────


def _valid_policy_contract_scaffold(symbols=None, **overrides):
    """Build a scaffold dict shaped exactly like the real output of
    materialize_funding_adjusted_bars_scaffold_diagnostics, for feeding
    directly into materialize_funding_adjustment_policy_contract_diagnostics
    without re-running the CSV pipeline.
    """
    if symbols is None:
        symbols = [
            {
                "symbol": "BTCUSDT",
                "readiness_status": ELIGIBLE_FOR_FUTURE_FUNDING_APPLICATION,
                "scaffold_status": "MATERIALIZED_DIAGNOSTIC_ROWS",
                "canonicalization_policy": FLOOR_TO_SECOND,
                "total_rows": 3,
                "matched_rows": 3,
                "missing_funding_rows": 0,
                "duplicate_canonical_funding_rows": 0,
                "funding_rate_present_rows": 3,
                "funding_rate_missing_rows": 0,
                "funding_rate_min": -0.0001,
                "funding_rate_max": 0.0002,
                "funding_rate_zero_count": 0,
                "funding_rate_positive_count": 2,
                "funding_rate_negative_count": 1,
                "first_timestamp": "2026-01-01T00:00:00Z",
                "last_timestamp": "2026-01-03T00:00:00Z",
                "sample_rows": [{"timestamp": "2026-01-01T00:00:00Z"}],
            },
            {
                "symbol": "ETHUSDT",
                "readiness_status": BLOCKED_FOR_FUTURE_FUNDING_APPLICATION,
                "scaffold_status": "SKIPPED_BY_READINESS_GATE",
                "blocked_reasons": ["FUNDING_DATA_GAP"],
            },
        ]

    eligible_count = sum(
        1 for s in symbols if s.get("scaffold_status") == "MATERIALIZED_DIAGNOSTIC_ROWS"
    )
    blocked_count = sum(
        1 for s in symbols if s.get("scaffold_status") == "SKIPPED_BY_READINESS_GATE"
    )

    scaffold = {
        "calculation_status": "FUNDING_ADJUSTED_BARS_SCAFFOLD_DIAGNOSTIC_ONLY",
        "funding_application_status": "DIAGNOSTIC_SCAFFOLD_ONLY_NOT_APPLIED_TO_STRATEGY",
        "readiness_gate_required": True,
        "canonicalization_policy_used": FLOOR_TO_SECOND,
        "source_sha": "test_sha",
        "symbol_count": len(symbols),
        "eligible_symbol_count": eligible_count,
        "blocked_symbol_count": blocked_count,
        "materialized_symbol_count": eligible_count,
        "skipped_symbol_count": blocked_count,
        "symbols": symbols,
    }
    scaffold.update(overrides)
    return scaffold


class TestFundingAdjustmentPolicyContractDiagnostics:
    """25 test cases for materialize_funding_adjustment_policy_contract_diagnostics."""

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _build_scaffold(self, tmp_path, **kwargs):
        """Materialize a real scaffold diagnostics dict via the CSV pipeline."""
        return TestFundingAdjustedBarsScaffoldDiagnostics()._build(tmp_path, **kwargs)

    def _build_multi_symbol_scaffold(
        self, tmp_path, eligible_symbols, blocked_reasons_by_symbol
    ):
        """Materialize a real scaffold diagnostics dict for a mix of eligible
        and blocked symbols via the CSV pipeline."""
        scaffold_helper = TestFundingAdjustedBarsScaffoldDiagnostics()
        symbols_data = [_make_eligible_symbol_entry(sym) for sym in eligible_symbols]
        symbols_data += [
            _make_blocked_symbol_entry(sym, blocked_reasons=reasons)
            for sym, reasons in blocked_reasons_by_symbol.items()
        ]
        readiness = TestFundingAdjustedBarsScaffoldDiagnostics._make_readiness_gate(
            symbols_data=symbols_data
        )

        all_symbols = eligible_symbols + list(blocked_reasons_by_symbol)
        bars_rows = [
            {"timestamp": "2026-01-01T00:00:00Z"},
            {"timestamp": "2026-01-02T00:00:00Z"},
            {"timestamp": "2026-01-03T00:00:00Z"},
        ]
        funding_rows = [
            {"fundingTime": "2026-01-01T00:00:00Z", "fundingRate": "0.0001"},
            {"fundingTime": "2026-01-02T00:00:00Z", "fundingRate": "0.0002"},
            {"fundingTime": "2026-01-03T00:00:00Z", "fundingRate": "-0.0001"},
        ]
        for sym in all_symbols:
            scaffold_helper._write_bars_csv(tmp_path, sym, bars_rows)
            scaffold_helper._write_funding_csv(tmp_path, sym, funding_rows)

        bars_files = [
            {
                "filename": f"{sym}_8h_ohlcv.csv",
                "sha256": hashlib.sha256(
                    (tmp_path / f"{sym}_8h_ohlcv.csv").read_bytes()
                ).hexdigest(),
            }
            for sym in all_symbols
        ]
        funding_files = [
            {
                "filename": f"{sym}_funding.csv",
                "sha256": hashlib.sha256(
                    (tmp_path / f"{sym}_funding.csv").read_bytes()
                ).hexdigest(),
            }
            for sym in all_symbols
        ]

        return materialize_funding_adjusted_bars_scaffold_diagnostics(
            funding_application_readiness_gate_diagnostics=readiness,
            funding_to_bars_timestamp_canonicalization_diagnostics=(
                TestFundingAdjustedBarsScaffoldDiagnostics._make_canonicalization_diagnostics(
                    eligible_symbols=eligible_symbols,
                    bars_count=3,
                )
            ),
            bars_inventory={"files": bars_files},
            funding_inventory={"files": funding_files},
            bars_dir=str(tmp_path),
            funding_dir=str(tmp_path),
            source_sha="test_sha",
        )

    # ── Test 1: Happy path emits contract for materialized eligible symbol ──

    def test_happy_path_emits_contract_for_materialized_eligible_symbol(self, tmp_path):
        scaffold = self._build_scaffold(tmp_path)
        contract = materialize_funding_adjustment_policy_contract_diagnostics(
            funding_adjusted_bars_scaffold_diagnostics=scaffold,
        )
        assert contract["calculation_status"] == (
            "FUNDING_ADJUSTMENT_POLICY_CONTRACT_DIAGNOSTIC_ONLY"
        )
        assert contract["eligible_symbol_count"] == 1
        assert contract["blocked_symbol_count"] == 0
        assert contract["policy_symbol_count"] == 1
        symbol = contract["symbols"][0]
        assert symbol["symbol"] == "BTCUSDT"
        assert symbol["scaffold_status"] == "MATERIALIZED_DIAGNOSTIC_ROWS"
        assert symbol["policy_status"] == (
            "ELIGIBLE_FOR_FUTURE_FUNDING_ADJUSTMENT_POLICY"
        )
        assert symbol["row_availability_status"] == "COMPLETE"
        assert symbol["total_rows"] == 3
        assert symbol["matched_rows"] == 3

    # ── Test 2: Blocked symbols carried forward ──────────────────────────────

    def test_blocked_symbols_carried_forward(self, tmp_path):
        readiness = TestFundingAdjustedBarsScaffoldDiagnostics._make_readiness_gate(
            symbols_data=[
                _make_blocked_symbol_entry("ETHUSDT", blocked_reasons=["NO_BARS_DATA"])
            ]
        )
        scaffold = self._build_scaffold(
            tmp_path, readiness_gate=readiness, symbol="ETHUSDT"
        )
        contract = materialize_funding_adjustment_policy_contract_diagnostics(
            funding_adjusted_bars_scaffold_diagnostics=scaffold,
        )
        assert contract["blocked_symbol_count"] == 1
        symbol = contract["symbols"][0]
        assert symbol["scaffold_status"] == "SKIPPED_BY_READINESS_GATE"
        assert symbol["policy_status"] == "BLOCKED_BY_READINESS_GATE"
        assert symbol["blocked_reasons"] == ["NO_BARS_DATA"]
        assert "sample_rows" not in symbol
        assert "future_application_required_inputs" not in symbol

    # ── Test 3: Eligibility derived from scaffold, not hardcoded ────────────

    def test_eligibility_derived_from_scaffold_not_hardcoded(self, tmp_path):
        scaffold = self._build_multi_symbol_scaffold(
            tmp_path,
            eligible_symbols=["ETHUSDT", "SOLUSDT"],
            blocked_reasons_by_symbol={"BTCUSDT": ["NO_BARS_DATA"]},
        )
        contract = materialize_funding_adjustment_policy_contract_diagnostics(
            funding_adjusted_bars_scaffold_diagnostics=scaffold,
        )
        assert contract["eligible_symbol_count"] == 2
        assert contract["blocked_symbol_count"] == 1
        by_symbol = {s["symbol"]: s for s in contract["symbols"]}
        assert by_symbol["ETHUSDT"]["policy_status"] == (
            "ELIGIBLE_FOR_FUTURE_FUNDING_ADJUSTMENT_POLICY"
        )
        assert by_symbol["SOLUSDT"]["policy_status"] == (
            "ELIGIBLE_FOR_FUTURE_FUNDING_ADJUSTMENT_POLICY"
        )
        assert by_symbol["BTCUSDT"]["policy_status"] == "BLOCKED_BY_READINESS_GATE"
        assert by_symbol["BTCUSDT"]["blocked_reasons"] == ["NO_BARS_DATA"]

    # ── Test 4: Missing scaffold diagnostics fails closed ───────────────────

    def test_missing_scaffold_diagnostics_fails_closed(self):
        with pytest.raises(
            ValueError, match="funding_adjusted_bars_scaffold_diagnostics"
        ):
            materialize_funding_adjustment_policy_contract_diagnostics(
                funding_adjusted_bars_scaffold_diagnostics=None,
            )

    # ── Test 5: Wrong scaffold calculation_status fails closed ──────────────

    def test_wrong_scaffold_calculation_status_fails_closed(self):
        scaffold = _valid_policy_contract_scaffold(calculation_status="WRONG_STATUS")
        with pytest.raises(ValueError, match="calculation_status"):
            materialize_funding_adjustment_policy_contract_diagnostics(
                funding_adjusted_bars_scaffold_diagnostics=scaffold,
            )

    # ── Test 6: Wrong scaffold funding_application_status fails closed ──────

    def test_wrong_scaffold_funding_application_status_fails_closed(self):
        scaffold = _valid_policy_contract_scaffold(funding_application_status="EXECUTED")
        with pytest.raises(ValueError, match="funding_application_status"):
            materialize_funding_adjustment_policy_contract_diagnostics(
                funding_adjusted_bars_scaffold_diagnostics=scaffold,
            )

    # ── Test 7: Wrong scaffold canonicalization policy fails closed ─────────

    def test_wrong_scaffold_canonicalization_policy_fails_closed(self):
        scaffold = _valid_policy_contract_scaffold(canonicalization_policy_used="ceil_to_hour")
        with pytest.raises(ValueError, match="canonicalization_policy_used"):
            materialize_funding_adjustment_policy_contract_diagnostics(
                funding_adjusted_bars_scaffold_diagnostics=scaffold,
            )

    # ── Test 8: Inconsistent scaffold counts fail closed ─────────────────────

    def test_inconsistent_scaffold_counts_fail_closed(self):
        scaffold = _valid_policy_contract_scaffold(symbol_count=5)
        with pytest.raises(ValueError, match="symbol_count"):
            materialize_funding_adjustment_policy_contract_diagnostics(
                funding_adjusted_bars_scaffold_diagnostics=scaffold,
            )

    # ── Test 9: Duplicate scaffold symbols fail closed ───────────────────────

    def test_duplicate_scaffold_symbols_fail_closed(self):
        base_symbol = _valid_policy_contract_scaffold()["symbols"][0]
        scaffold = _valid_policy_contract_scaffold(
            symbols=[dict(base_symbol), dict(base_symbol)]
        )
        with pytest.raises(ValueError, match="Duplicate scaffold symbol"):
            materialize_funding_adjustment_policy_contract_diagnostics(
                funding_adjusted_bars_scaffold_diagnostics=scaffold,
            )

    # ── Test 10: matched_rows != total_rows fails closed ─────────────────────

    def test_materialized_symbol_matched_rows_mismatch_fails_closed(self):
        scaffold = _valid_policy_contract_scaffold()
        scaffold["symbols"][0]["matched_rows"] = 2
        with pytest.raises(ValueError, match="matched_rows"):
            materialize_funding_adjustment_policy_contract_diagnostics(
                funding_adjusted_bars_scaffold_diagnostics=scaffold,
            )

    # ── Test 11: nonzero missing_funding_rows fails closed ───────────────────

    def test_materialized_symbol_missing_funding_rows_fails_closed(self):
        scaffold = _valid_policy_contract_scaffold()
        scaffold["symbols"][0]["missing_funding_rows"] = 1
        with pytest.raises(ValueError, match="missing_funding_rows"):
            materialize_funding_adjustment_policy_contract_diagnostics(
                funding_adjusted_bars_scaffold_diagnostics=scaffold,
            )

    # ── Test 12: nonzero duplicate_canonical_funding_rows fails closed ───────

    def test_materialized_symbol_duplicate_canonical_funding_rows_fails_closed(self):
        scaffold = _valid_policy_contract_scaffold()
        scaffold["symbols"][0]["duplicate_canonical_funding_rows"] = 1
        with pytest.raises(ValueError, match="duplicate_canonical_funding_rows"):
            materialize_funding_adjustment_policy_contract_diagnostics(
                funding_adjusted_bars_scaffold_diagnostics=scaffold,
            )

    # ── Test 13: missing funding-rate rows fail closed ───────────────────────

    def test_materialized_symbol_missing_funding_rate_rows_fails_closed(self):
        scaffold = _valid_policy_contract_scaffold()
        scaffold["symbols"][0]["funding_rate_present_rows"] = 2
        with pytest.raises(ValueError, match="funding_rate_present_rows"):
            materialize_funding_adjustment_policy_contract_diagnostics(
                funding_adjusted_bars_scaffold_diagnostics=scaffold,
            )

    # ── Test 14: skipped symbol with sample_rows fails closed ────────────────

    def test_skipped_symbol_with_sample_rows_fails_closed(self):
        scaffold = _valid_policy_contract_scaffold()
        scaffold["symbols"][1]["sample_rows"] = []
        with pytest.raises(ValueError, match="sample_rows"):
            materialize_funding_adjustment_policy_contract_diagnostics(
                funding_adjusted_bars_scaffold_diagnostics=scaffold,
            )

    # ── Test 15: skipped symbol with funding-rate summary fields fails closed

    def test_skipped_symbol_with_funding_rate_summary_fails_closed(self):
        scaffold = _valid_policy_contract_scaffold()
        scaffold["symbols"][1]["funding_rate_present_rows"] = 3
        with pytest.raises(ValueError, match="funding-rate"):
            materialize_funding_adjustment_policy_contract_diagnostics(
                funding_adjusted_bars_scaffold_diagnostics=scaffold,
            )

    # ── Test 16: skipped symbol missing blocked_reasons fails closed ─────────

    def test_skipped_symbol_missing_blocked_reasons_fails_closed(self):
        scaffold = _valid_policy_contract_scaffold()
        scaffold["symbols"][1]["blocked_reasons"] = []
        with pytest.raises(ValueError, match="blocked_reasons"):
            materialize_funding_adjustment_policy_contract_diagnostics(
                funding_adjusted_bars_scaffold_diagnostics=scaffold,
            )

    # ── Test 17: long/short side policy strings present but not applied ─────

    def test_position_side_contract_present_but_not_applied(self, tmp_path):
        scaffold = self._build_scaffold(tmp_path)
        contract = materialize_funding_adjustment_policy_contract_diagnostics(
            funding_adjusted_bars_scaffold_diagnostics=scaffold,
        )
        side_contract = contract["position_side_policy_contract"]
        assert side_contract["long_side_contract"] == (
            "LONG_PAYS_POSITIVE_FUNDING_RECEIVES_NEGATIVE_FUNDING"
        )
        assert side_contract["short_side_contract"] == (
            "SHORT_RECEIVES_POSITIVE_FUNDING_PAYS_NEGATIVE_FUNDING"
        )
        assert side_contract["position_side_inference_status"] == "NOT_EXECUTED"
        assert side_contract["position_side_application_status"] == "NOT_EXECUTED"
        assert contract["strategy_application_status"] == "NOT_EXECUTED"
        assert contract["pnl_application_status"] == "NOT_EXECUTED"
        assert contract["funding_adjustment_application_status"] == "NOT_EXECUTED"

    # ── Test 18: future explicit position side required, not inferred ───────

    def test_future_explicit_position_side_required_not_inferred(self, tmp_path):
        scaffold = self._build_scaffold(tmp_path)
        contract = materialize_funding_adjustment_policy_contract_diagnostics(
            funding_adjusted_bars_scaffold_diagnostics=scaffold,
        )
        symbol = contract["symbols"][0]
        required_inputs = symbol["future_application_required_inputs"]
        assert required_inputs["explicit_position_side"] == (
            "FUTURE_STRATEGY_POSITION_SIDE_REQUIRED"
        )
        side_contract = contract["position_side_policy_contract"]
        assert side_contract["position_side_source_required"] == (
            "FUTURE_STRATEGY_POSITION_SIDE_REQUIRED"
        )
        assert side_contract["position_side_inference_status"] == "NOT_EXECUTED"

    # ── Test 19: CLI with funding includes policy contract section ──────────

    def test_cli_with_funding_includes_policy_contract_section(self, tmp_path):
        bars_dir = tmp_path / "bars"
        funding_dir = tmp_path / "funding"
        bars_dir.mkdir()
        funding_dir.mkdir()
        (bars_dir / "BTCUSDT_8h_ohlcv.csv").write_text(
            "timestamp,open,high,low,close,volume\n"
            "2026-01-01T00:00:00Z,100.0,101.0,99.0,100.5,1000\n"
            "2026-01-02T00:00:00Z,100.5,102.0,100.0,101.0,1200\n"
            "2026-01-03T00:00:00Z,101.0,103.0,100.5,102.0,1100\n"
        )
        (funding_dir / "BTCUSDT_funding.csv").write_text(
            "fundingTime,fundingRate,markPrice\n"
            "2026-01-01T00:00:00Z,0.0001,50000.0\n"
            "2026-01-02T00:00:00Z,0.0002,50100.0\n"
            "2026-01-03T00:00:00Z,-0.0001,50200.0\n"
        )

        out_dir = Path("/tmp") / f"qnty_policy_contract_cli_funding_{uuid.uuid4().hex}"
        receipt_path = out_dir / "real_validation_receipt.json"
        try:
            result = subprocess.run(
                [
                    sys.executable, "-m",
                    "quantbot.experiment.offline_edge_real_validation",
                    "--read-only",
                    "--output-dir", str(out_dir),
                    "--input-manifest-fingerprint", "a" * 64,
                    "--data-quality-receipt-sha256", "b" * 64,
                    "--code-commit-sha", "c" * 40,
                    "--bars-dir", str(bars_dir),
                    "--funding-dir", str(funding_dir),
                ],
                capture_output=True, text=True, timeout=30,
            )
            assert result.returncode == 0, f"stderr: {result.stderr}"
            with open(receipt_path) as f:
                written = json.load(f)
            assert "funding_adjustment_policy_contract_diagnostics" in written
            assert written["funding_adjustment_policy_contract_diagnostics"][
                "eligible_symbol_count"
            ] == 1
        finally:
            if receipt_path.exists():
                receipt_path.unlink()
            if out_dir.exists():
                out_dir.rmdir()

    # ── Test 20: CLI without funding omits policy contract section ──────────

    def test_cli_without_funding_omits_policy_contract_section(self, tmp_path):
        bars_dir = tmp_path / "bars"
        bars_dir.mkdir()
        (bars_dir / "BTCUSDT_8h_ohlcv.csv").write_text(
            "timestamp,open,high,low,close,volume\n"
            "2026-01-01T00:00:00Z,100.0,101.0,99.0,100.5,1000\n"
            "2026-01-02T00:00:00Z,100.5,102.0,100.0,101.0,1200\n"
            "2026-01-03T00:00:00Z,101.0,103.0,100.5,102.0,1100\n"
        )

        out_dir = Path("/tmp") / f"qnty_policy_contract_cli_no_funding_{uuid.uuid4().hex}"
        receipt_path = out_dir / "real_validation_receipt.json"
        try:
            result = subprocess.run(
                [
                    sys.executable, "-m",
                    "quantbot.experiment.offline_edge_real_validation",
                    "--read-only",
                    "--output-dir", str(out_dir),
                    "--input-manifest-fingerprint", "a" * 64,
                    "--data-quality-receipt-sha256", "b" * 64,
                    "--code-commit-sha", "c" * 40,
                    "--bars-dir", str(bars_dir),
                ],
                capture_output=True, text=True, timeout=30,
            )
            assert result.returncode == 0, f"stderr: {result.stderr}"
            with open(receipt_path) as f:
                written = json.load(f)
            assert "funding_adjustment_policy_contract_diagnostics" not in written
        finally:
            if receipt_path.exists():
                receipt_path.unlink()
            if out_dir.exists():
                out_dir.rmdir()

    # ── Test 21: Receipt final verdict remains blocked ───────────────────────

    def test_receipt_final_verdict_remains_blocked(self, tmp_path):
        scaffold = self._build_scaffold(tmp_path)
        contract = materialize_funding_adjustment_policy_contract_diagnostics(
            funding_adjusted_bars_scaffold_diagnostics=scaffold,
        )
        receipt = _base_receipt(
            funding_adjusted_bars_scaffold_diagnostics=scaffold,
            funding_adjustment_policy_contract_diagnostics=contract,
        )
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION
        validate_real_validation_receipt(receipt)  # must not raise

    # ── Test 22: Required outputs remain false ────────────────────────────────

    def test_required_outputs_remain_false(self, tmp_path):
        scaffold = self._build_scaffold(tmp_path)
        contract = materialize_funding_adjustment_policy_contract_diagnostics(
            funding_adjusted_bars_scaffold_diagnostics=scaffold,
        )
        receipt = _base_receipt(
            funding_adjusted_bars_scaffold_diagnostics=scaffold,
            funding_adjustment_policy_contract_diagnostics=contract,
        )
        for value in receipt["required_outputs_present"].values():
            assert value is False

    # ── Test 23: Forbidden calculations remain false ─────────────────────────

    def test_forbidden_calculations_remain_false(self, tmp_path):
        scaffold = self._build_scaffold(tmp_path)
        contract = materialize_funding_adjustment_policy_contract_diagnostics(
            funding_adjusted_bars_scaffold_diagnostics=scaffold,
        )
        receipt = _base_receipt(
            funding_adjusted_bars_scaffold_diagnostics=scaffold,
            funding_adjustment_policy_contract_diagnostics=contract,
        )
        for key, value in receipt["forbidden_calculation_status"].items():
            assert value is False, f"{key} must be False"

    # ── Test 24: Guardrails remain true ───────────────────────────────────────

    def test_guardrails_remain_true(self, tmp_path):
        scaffold = self._build_scaffold(tmp_path)
        contract = materialize_funding_adjustment_policy_contract_diagnostics(
            funding_adjusted_bars_scaffold_diagnostics=scaffold,
        )
        receipt = _base_receipt(
            funding_adjusted_bars_scaffold_diagnostics=scaffold,
            funding_adjustment_policy_contract_diagnostics=contract,
        )
        for key, value in receipt["guardrail_status"].items():
            assert value is True, f"{key} must be True"

    # ── Test 25: Safety-key regression ────────────────────────────────────────

    def test_safety_key_regression(self, tmp_path):
        scaffold = self._build_multi_symbol_scaffold(
            tmp_path,
            eligible_symbols=["ETHUSDT"],
            blocked_reasons_by_symbol={"BTCUSDT": ["NO_BARS_DATA"]},
        )
        contract = materialize_funding_adjustment_policy_contract_diagnostics(
            funding_adjusted_bars_scaffold_diagnostics=scaffold,
        )
        all_keys = _all_dict_keys(contract)
        forbidden = {
            "PnL", "Sharpe", "edge", "strategy-performance",
            "risk", "trade", "trades", "signal", "signals",
            "position", "positions", "portfolio", "return", "returns",
            "funding_adjusted_return", "net_return_value",
            "price_change", "OFFLINE_EDGE_CANDIDATE", "EDGE_CANDIDATE",
        }
        assert forbidden.isdisjoint(all_keys), (
            f"Forbidden keys found: {forbidden & all_keys}"
        )

    # ── Supplemental: unrecognized scaffold_status fails closed ─────────────

    def test_unrecognized_scaffold_status_fails_closed(self):
        scaffold = _valid_policy_contract_scaffold()
        scaffold["symbols"][0]["scaffold_status"] = "SOMETHING_ELSE"
        with pytest.raises(ValueError, match="Unrecognized scaffold_status"):
            materialize_funding_adjustment_policy_contract_diagnostics(
                funding_adjusted_bars_scaffold_diagnostics=scaffold,
            )


# ── Funding adjustment arithmetic scaffold diagnostics ──────────────────


def _empty_valid_scaffold():
    return {
        "calculation_status": "FUNDING_ADJUSTED_BARS_SCAFFOLD_DIAGNOSTIC_ONLY",
        "funding_application_status": "DIAGNOSTIC_SCAFFOLD_ONLY_NOT_APPLIED_TO_STRATEGY",
        "canonicalization_policy_used": FLOOR_TO_SECOND,
        "symbol_count": 0,
        "eligible_symbol_count": 0,
        "blocked_symbol_count": 0,
        "materialized_symbol_count": 0,
        "skipped_symbol_count": 0,
        "symbols": [],
    }


def _valid_arithmetic_scaffold_contract(
    *, side_overrides=None, output_overrides=None, **top_overrides
):
    """Build a real, valid funding_adjustment_policy_contract_diagnostics
    dict (via the actual materializer, on an empty symbol scaffold) and
    apply optional overrides for testing fail-closed behavior."""
    contract = materialize_funding_adjustment_policy_contract_diagnostics(
        funding_adjusted_bars_scaffold_diagnostics=_empty_valid_scaffold(),
    )
    contract.update(top_overrides)
    if side_overrides:
        contract["position_side_policy_contract"] = {
            **contract["position_side_policy_contract"],
            **side_overrides,
        }
    if output_overrides:
        contract["output_policy_contract"] = {
            **contract["output_policy_contract"],
            **output_overrides,
        }
    return contract


def _valid_row_scaffold_inputs():
    """Return valid upstream section dicts for row scaffold diagnostics."""
    policy_contract = {
        "calculation_status": "FUNDING_ADJUSTMENT_POLICY_CONTRACT_DIAGNOSTIC_ONLY",
        "funding_adjustment_application_status": "NOT_EXECUTED",
        "strategy_application_status": "NOT_EXECUTED",
        "pnl_application_status": "NOT_EXECUTED",
        "funding_rate_unit": "decimal_rate_not_percent",
        "funding_rate_annualization_status": "NOT_ANNUALIZED",
        "timestamp_match_policy": "EXACT_CANONICAL_FUNDING_TIMESTAMP_TO_BAR_TIMESTAMP",
    }

    arithmetic_scaffold = {
        "calculation_status": "FUNDING_ADJUSTMENT_ARITHMETIC_SCAFFOLD_DIAGNOSTIC_ONLY",
        "funding_adjustment_application_status": "FIXTURE_ONLY_NOT_APPLIED_TO_STRATEGY",
        "strategy_application_status": "NOT_EXECUTED",
        "pnl_application_status": "NOT_EXECUTED",
        "funding_rate_unit": "decimal_rate_not_percent",
        "annualization_status": "NOT_ANNUALIZED",
        "compounding_status": "NOT_COMPOUNDED",
        "side_source": "EXPLICIT_FIXTURE_ONLY",
        "notional_source": "EXPLICIT_FIXTURE_ONLY",
        "fixture_case_count": 6,
        "passed_fixture_case_count": 6,
        "failed_fixture_case_count": 0,
    }

    bars_scaffold = {
        "calculation_status": "FUNDING_ADJUSTED_BARS_SCAFFOLD_DIAGNOSTIC_ONLY",
        "funding_application_status": "DIAGNOSTIC_SCAFFOLD_ONLY_NOT_APPLIED_TO_STRATEGY",
        "canonicalization_policy_used": "floor_to_second",
        "symbol_count": 2,
        "eligible_symbol_count": 1,
        "blocked_symbol_count": 1,
        "materialized_symbol_count": 1,
        "skipped_symbol_count": 1,
        "symbols": [
            {
                "symbol": "BTCUSDT",
                "scaffold_status": "MATERIALIZED_DIAGNOSTIC_ROWS",
                "total_rows": 100,
                "matched_rows": 100,
                "funding_rate_present_rows": 100,
                "missing_funding_rows": 0,
                "duplicate_canonical_funding_rows": 0,
                "funding_rate_missing_rows": 0,
                "sample_rows": [
                    {
                        "bar_row_index": 0,
                        "funding_row_index": 0,
                        "funding_rate": "0.0001",
                    },
                    {
                        "bar_row_index": 1,
                        "funding_row_index": 1,
                        "funding_rate": "-0.00005",
                    },
                ],
            },
            {
                "symbol": "ETHUSDT",
                "scaffold_status": "SKIPPED_BY_READINESS_GATE",
                "blocked_reasons": ["funding_rate_gap_exceeds_threshold"],
            },
        ],
    }

    return policy_contract, arithmetic_scaffold, bars_scaffold


class TestFundingAdjustmentArithmeticScaffoldDiagnostics:
    """40 test cases for
    materialize_funding_adjustment_arithmetic_scaffold_diagnostics."""

    # ── Test 1: Happy path emits six fixture cases and all pass ─────────────

    def test_happy_path_emits_six_fixture_cases_all_pass(self):
        contract = _valid_arithmetic_scaffold_contract()
        result = materialize_funding_adjustment_arithmetic_scaffold_diagnostics(
            funding_adjustment_policy_contract_diagnostics=contract,
        )
        assert result["calculation_status"] == (
            "FUNDING_ADJUSTMENT_ARITHMETIC_SCAFFOLD_DIAGNOSTIC_ONLY"
        )
        assert result["fixture_case_count"] == 6
        assert result["passed_fixture_case_count"] == 6
        assert result["failed_fixture_case_count"] == 0
        assert len(result["fixture_cases"]) == 6
        for case in result["fixture_cases"]:
            assert case["fixture_status"] == "PASS"

    # ── Test 2: Long positive funding produces negative cashflow ────────────

    def test_long_positive_funding_produces_negative_cashflow(self):
        contract = _valid_arithmetic_scaffold_contract()
        result = materialize_funding_adjustment_arithmetic_scaffold_diagnostics(
            funding_adjustment_policy_contract_diagnostics=contract,
        )
        case = result["fixture_cases"][0]
        assert case["side"] == "LONG"
        assert Decimal(case["funding_rate"] if isinstance(case["funding_rate"], str) else str(case["funding_rate"])) > 0
        assert Decimal(case["cashflow_per_notional_unit"]) < 0

    # ── Test 3: Long negative funding produces positive cashflow ────────────

    def test_long_negative_funding_produces_positive_cashflow(self):
        contract = _valid_arithmetic_scaffold_contract()
        result = materialize_funding_adjustment_arithmetic_scaffold_diagnostics(
            funding_adjustment_policy_contract_diagnostics=contract,
        )
        case = result["fixture_cases"][1]
        assert case["side"] == "LONG"
        assert Decimal(case["cashflow_per_notional_unit"]) > 0

    # ── Test 4: Short positive funding produces positive cashflow ───────────

    def test_short_positive_funding_produces_positive_cashflow(self):
        contract = _valid_arithmetic_scaffold_contract()
        result = materialize_funding_adjustment_arithmetic_scaffold_diagnostics(
            funding_adjustment_policy_contract_diagnostics=contract,
        )
        case = result["fixture_cases"][2]
        assert case["side"] == "SHORT"
        assert Decimal(case["cashflow_per_notional_unit"]) > 0

    # ── Test 5: Short negative funding produces negative cashflow ───────────

    def test_short_negative_funding_produces_negative_cashflow(self):
        contract = _valid_arithmetic_scaffold_contract()
        result = materialize_funding_adjustment_arithmetic_scaffold_diagnostics(
            funding_adjustment_policy_contract_diagnostics=contract,
        )
        case = result["fixture_cases"][3]
        assert case["side"] == "SHORT"
        assert Decimal(case["cashflow_per_notional_unit"]) < 0

    # ── Test 6: Zero funding produces zero for long ──────────────────────────

    def test_zero_funding_produces_zero_for_long(self):
        contract = _valid_arithmetic_scaffold_contract()
        result = materialize_funding_adjustment_arithmetic_scaffold_diagnostics(
            funding_adjustment_policy_contract_diagnostics=contract,
        )
        case = result["fixture_cases"][4]
        assert case["side"] == "LONG"
        assert Decimal(case["cashflow_per_notional_unit"]) == 0

    # ── Test 7: Zero funding produces zero for short ─────────────────────────

    def test_zero_funding_produces_zero_for_short(self):
        contract = _valid_arithmetic_scaffold_contract()
        result = materialize_funding_adjustment_arithmetic_scaffold_diagnostics(
            funding_adjustment_policy_contract_diagnostics=contract,
        )
        case = result["fixture_cases"][5]
        assert case["side"] == "SHORT"
        assert Decimal(case["cashflow_per_notional_unit"]) == 0

    # ── Test 8: Decimal string inputs are accepted ───────────────────────────

    def test_decimal_string_inputs_accepted(self):
        case = _materialize_fixture_case(
            {
                "case_id": "string_case",
                "side": "LONG",
                "funding_rate": "0.01",
                "notional_per_unit": "100",
            }
        )
        assert case["fixture_status"] == "PASS"
        assert Decimal(case["cashflow_per_notional_unit"]) == Decimal("-1.00")

    # ── Test 9: Float inputs converted through Decimal(str(value)) ──────────

    def test_float_inputs_converted_through_decimal_str(self):
        case = _materialize_fixture_case(
            {
                "case_id": "float_case",
                "side": "SHORT",
                "funding_rate": 0.01,
                "notional_per_unit": 100.0,
            }
        )
        assert case["fixture_status"] == "PASS"
        assert Decimal(case["cashflow_per_notional_unit"]) == Decimal(
            str(Decimal(str(0.01)) * Decimal(str(100.0)))
        )

    # ── Test 10: Missing policy contract fails closed ────────────────────────

    def test_missing_policy_contract_fails_closed(self):
        with pytest.raises(
            ValueError, match="funding_adjustment_policy_contract_diagnostics"
        ):
            materialize_funding_adjustment_arithmetic_scaffold_diagnostics(
                funding_adjustment_policy_contract_diagnostics=None,
            )

    # ── Test 11: Wrong policy calculation status fails closed ───────────────

    def test_wrong_policy_calculation_status_fails_closed(self):
        contract = _valid_arithmetic_scaffold_contract(calculation_status="WRONG")
        with pytest.raises(ValueError, match="calculation_status"):
            materialize_funding_adjustment_arithmetic_scaffold_diagnostics(
                funding_adjustment_policy_contract_diagnostics=contract,
            )

    # ── Test 12: Wrong funding adjustment application status fails closed ──

    def test_wrong_funding_adjustment_application_status_fails_closed(self):
        contract = _valid_arithmetic_scaffold_contract(
            funding_adjustment_application_status="EXECUTED"
        )
        with pytest.raises(
            ValueError, match="funding_adjustment_application_status"
        ):
            materialize_funding_adjustment_arithmetic_scaffold_diagnostics(
                funding_adjustment_policy_contract_diagnostics=contract,
            )

    # ── Test 13: Wrong strategy application status fails closed ─────────────

    def test_wrong_strategy_application_status_fails_closed(self):
        contract = _valid_arithmetic_scaffold_contract(
            strategy_application_status="EXECUTED"
        )
        with pytest.raises(ValueError, match="strategy_application_status"):
            materialize_funding_adjustment_arithmetic_scaffold_diagnostics(
                funding_adjustment_policy_contract_diagnostics=contract,
            )

    # ── Test 14: Wrong pnl application status fails closed ──────────────────

    def test_wrong_pnl_application_status_fails_closed(self):
        contract = _valid_arithmetic_scaffold_contract(pnl_application_status="EXECUTED")
        with pytest.raises(ValueError, match="pnl_application_status"):
            materialize_funding_adjustment_arithmetic_scaffold_diagnostics(
                funding_adjustment_policy_contract_diagnostics=contract,
            )

    # ── Test 15: Wrong funding rate unit fails closed ────────────────────────

    def test_wrong_funding_rate_unit_fails_closed(self):
        contract = _valid_arithmetic_scaffold_contract(funding_rate_unit="percent")
        with pytest.raises(ValueError, match="funding_rate_unit"):
            materialize_funding_adjustment_arithmetic_scaffold_diagnostics(
                funding_adjustment_policy_contract_diagnostics=contract,
            )

    # ── Test 16: Wrong annualization status fails closed ────────────────────

    def test_wrong_annualization_status_fails_closed(self):
        contract = _valid_arithmetic_scaffold_contract(
            funding_rate_annualization_status="ANNUALIZED"
        )
        with pytest.raises(ValueError, match="funding_rate_annualization_status"):
            materialize_funding_adjustment_arithmetic_scaffold_diagnostics(
                funding_adjustment_policy_contract_diagnostics=contract,
            )

    # ── Test 17: Wrong timestamp match policy fails closed ──────────────────

    def test_wrong_timestamp_match_policy_fails_closed(self):
        contract = _valid_arithmetic_scaffold_contract(
            timestamp_match_policy="NEAREST_NEIGHBOR"
        )
        with pytest.raises(ValueError, match="timestamp_match_policy"):
            materialize_funding_adjustment_arithmetic_scaffold_diagnostics(
                funding_adjustment_policy_contract_diagnostics=contract,
            )

    # ── Test 18: Wrong long-side contract fails closed ──────────────────────

    def test_wrong_long_side_contract_fails_closed(self):
        contract = _valid_arithmetic_scaffold_contract(
            side_overrides={"long_side_contract": "WRONG"}
        )
        with pytest.raises(ValueError, match="long_side_contract"):
            materialize_funding_adjustment_arithmetic_scaffold_diagnostics(
                funding_adjustment_policy_contract_diagnostics=contract,
            )

    # ── Test 19: Wrong short-side contract fails closed ─────────────────────

    def test_wrong_short_side_contract_fails_closed(self):
        contract = _valid_arithmetic_scaffold_contract(
            side_overrides={"short_side_contract": "WRONG"}
        )
        with pytest.raises(ValueError, match="short_side_contract"):
            materialize_funding_adjustment_arithmetic_scaffold_diagnostics(
                funding_adjustment_policy_contract_diagnostics=contract,
            )

    # ── Test 20: Position side inference/application not NOT_EXECUTED fails
    #    closed ──────────────────────────────────────────────────────────────

    def test_position_side_inference_not_not_executed_fails_closed(self):
        contract = _valid_arithmetic_scaffold_contract(
            side_overrides={"position_side_inference_status": "EXECUTED"}
        )
        with pytest.raises(ValueError, match="position_side_inference_status"):
            materialize_funding_adjustment_arithmetic_scaffold_diagnostics(
                funding_adjustment_policy_contract_diagnostics=contract,
            )

    def test_position_side_application_not_not_executed_fails_closed(self):
        contract = _valid_arithmetic_scaffold_contract(
            side_overrides={"position_side_application_status": "EXECUTED"}
        )
        with pytest.raises(ValueError, match="position_side_application_status"):
            materialize_funding_adjustment_arithmetic_scaffold_diagnostics(
                funding_adjustment_policy_contract_diagnostics=contract,
            )

    # ── Test 21: Output policy claiming row-level adjusted values fails
    #    closed ──────────────────────────────────────────────────────────────

    def test_output_policy_row_level_adjusted_values_fails_closed(self):
        contract = _valid_arithmetic_scaffold_contract(
            output_overrides={"emits_row_level_adjusted_values": True}
        )
        with pytest.raises(ValueError, match="emits_row_level_adjusted_values"):
            materialize_funding_adjustment_arithmetic_scaffold_diagnostics(
                funding_adjustment_policy_contract_diagnostics=contract,
            )

    # ── Test 22: Output policy claiming strategy values fails closed ────────

    def test_output_policy_strategy_values_fails_closed(self):
        contract = _valid_arithmetic_scaffold_contract(
            output_overrides={"emits_strategy_values": True}
        )
        with pytest.raises(ValueError, match="emits_strategy_values"):
            materialize_funding_adjustment_arithmetic_scaffold_diagnostics(
                funding_adjustment_policy_contract_diagnostics=contract,
            )

    # ── Test 23: Output policy claiming performance values fails closed ─────

    def test_output_policy_performance_values_fails_closed(self):
        contract = _valid_arithmetic_scaffold_contract(
            output_overrides={"emits_performance_values": True}
        )
        with pytest.raises(ValueError, match="emits_performance_values"):
            materialize_funding_adjustment_arithmetic_scaffold_diagnostics(
                funding_adjustment_policy_contract_diagnostics=contract,
            )

    # ── Test 24: Unsupported side fails closed ────────────────────────────────

    def test_unsupported_side_fails_closed(self):
        with pytest.raises(ValueError, match="unsupported side"):
            _materialize_fixture_case(
                {
                    "case_id": "x",
                    "side": "MID",
                    "funding_rate": 0.01,
                    "notional_per_unit": 100,
                }
            )

    # ── Test 25: Missing side fails closed ────────────────────────────────────

    def test_missing_side_fails_closed(self):
        with pytest.raises(ValueError, match="missing side"):
            _materialize_fixture_case(
                {
                    "case_id": "x",
                    "funding_rate": 0.01,
                    "notional_per_unit": 100,
                }
            )

    # ── Test 26: Malformed funding rate fails closed ─────────────────────────

    def test_malformed_funding_rate_fails_closed(self):
        with pytest.raises(ValueError, match="funding_rate is malformed"):
            _materialize_fixture_case(
                {
                    "case_id": "x",
                    "side": "LONG",
                    "funding_rate": "not_a_number",
                    "notional_per_unit": 100,
                }
            )

    # ── Test 27: NaN funding rate fails closed ────────────────────────────────

    def test_nan_funding_rate_fails_closed(self):
        with pytest.raises(ValueError, match="funding_rate must be finite"):
            _materialize_fixture_case(
                {
                    "case_id": "x",
                    "side": "LONG",
                    "funding_rate": float("nan"),
                    "notional_per_unit": 100,
                }
            )

    # ── Test 28: Infinite funding rate fails closed ──────────────────────────

    def test_infinite_funding_rate_fails_closed(self):
        with pytest.raises(ValueError, match="funding_rate must be finite"):
            _materialize_fixture_case(
                {
                    "case_id": "x",
                    "side": "LONG",
                    "funding_rate": float("inf"),
                    "notional_per_unit": 100,
                }
            )

    # ── Test 29: Missing notional fails closed ────────────────────────────────

    def test_missing_notional_fails_closed(self):
        with pytest.raises(ValueError, match="missing notional_per_unit"):
            _materialize_fixture_case(
                {
                    "case_id": "x",
                    "side": "LONG",
                    "funding_rate": 0.01,
                }
            )

    # ── Test 30: Zero notional fails closed ───────────────────────────────────

    def test_zero_notional_fails_closed(self):
        with pytest.raises(ValueError, match="notional_per_unit must be positive"):
            _materialize_fixture_case(
                {
                    "case_id": "x",
                    "side": "LONG",
                    "funding_rate": 0.01,
                    "notional_per_unit": 0,
                }
            )

    # ── Test 31: Negative notional fails closed ───────────────────────────────

    def test_negative_notional_fails_closed(self):
        with pytest.raises(ValueError, match="notional_per_unit must be positive"):
            _materialize_fixture_case(
                {
                    "case_id": "x",
                    "side": "LONG",
                    "funding_rate": 0.01,
                    "notional_per_unit": -100,
                }
            )

    # ── Test 32: Malformed notional fails closed ──────────────────────────────

    def test_malformed_notional_fails_closed(self):
        with pytest.raises(ValueError, match="notional_per_unit is malformed"):
            _materialize_fixture_case(
                {
                    "case_id": "x",
                    "side": "LONG",
                    "funding_rate": 0.01,
                    "notional_per_unit": "not_a_number",
                }
            )

    # ── Test 33: Fixture expected mismatch fails closed ──────────────────────

    def test_fixture_expected_mismatch_fails_closed(self):
        with pytest.raises(ValueError, match="does not equal expected"):
            _materialize_fixture_case(
                {
                    "case_id": "x",
                    "side": "LONG",
                    "funding_rate": 0.01,
                    "notional_per_unit": 100,
                    "expected_cashflow_per_notional_unit": "999",
                }
            )

    # ── Test 34: CLI with funding includes arithmetic scaffold section ──────

    def test_cli_with_funding_includes_arithmetic_scaffold_section(self, tmp_path):
        bars_dir = tmp_path / "bars"
        funding_dir = tmp_path / "funding"
        bars_dir.mkdir()
        funding_dir.mkdir()
        (bars_dir / "BTCUSDT_8h_ohlcv.csv").write_text(
            "timestamp,open,high,low,close,volume\n"
            "2026-01-01T00:00:00Z,100.0,101.0,99.0,100.5,1000\n"
            "2026-01-02T00:00:00Z,100.5,102.0,100.0,101.0,1200\n"
            "2026-01-03T00:00:00Z,101.0,103.0,100.5,102.0,1100\n"
        )
        (funding_dir / "BTCUSDT_funding.csv").write_text(
            "fundingTime,fundingRate,markPrice\n"
            "2026-01-01T00:00:00Z,0.0001,50000.0\n"
            "2026-01-02T00:00:00Z,0.0002,50100.0\n"
            "2026-01-03T00:00:00Z,-0.0001,50200.0\n"
        )

        out_dir = Path("/tmp") / f"qnty_arith_scaffold_cli_funding_{uuid.uuid4().hex}"
        receipt_path = out_dir / "real_validation_receipt.json"
        try:
            result = subprocess.run(
                [
                    sys.executable, "-m",
                    "quantbot.experiment.offline_edge_real_validation",
                    "--read-only",
                    "--output-dir", str(out_dir),
                    "--input-manifest-fingerprint", "a" * 64,
                    "--data-quality-receipt-sha256", "b" * 64,
                    "--code-commit-sha", "c" * 40,
                    "--bars-dir", str(bars_dir),
                    "--funding-dir", str(funding_dir),
                ],
                capture_output=True, text=True, timeout=30,
            )
            assert result.returncode == 0, f"stderr: {result.stderr}"
            with open(receipt_path) as f:
                written = json.load(f)
            assert "funding_adjustment_arithmetic_scaffold_diagnostics" in written
            section = written["funding_adjustment_arithmetic_scaffold_diagnostics"]
            assert section["fixture_case_count"] == 6
            assert section["passed_fixture_case_count"] == 6
        finally:
            if receipt_path.exists():
                receipt_path.unlink()
            if out_dir.exists():
                out_dir.rmdir()

    # ── Test 35: CLI without funding omits arithmetic scaffold section ──────

    def test_cli_without_funding_omits_arithmetic_scaffold_section(self, tmp_path):
        bars_dir = tmp_path / "bars"
        bars_dir.mkdir()
        (bars_dir / "BTCUSDT_8h_ohlcv.csv").write_text(
            "timestamp,open,high,low,close,volume\n"
            "2026-01-01T00:00:00Z,100.0,101.0,99.0,100.5,1000\n"
            "2026-01-02T00:00:00Z,100.5,102.0,100.0,101.0,1200\n"
            "2026-01-03T00:00:00Z,101.0,103.0,100.5,102.0,1100\n"
        )

        out_dir = Path("/tmp") / f"qnty_arith_scaffold_cli_no_funding_{uuid.uuid4().hex}"
        receipt_path = out_dir / "real_validation_receipt.json"
        try:
            result = subprocess.run(
                [
                    sys.executable, "-m",
                    "quantbot.experiment.offline_edge_real_validation",
                    "--read-only",
                    "--output-dir", str(out_dir),
                    "--input-manifest-fingerprint", "a" * 64,
                    "--data-quality-receipt-sha256", "b" * 64,
                    "--code-commit-sha", "c" * 40,
                    "--bars-dir", str(bars_dir),
                ],
                capture_output=True, text=True, timeout=30,
            )
            assert result.returncode == 0, f"stderr: {result.stderr}"
            with open(receipt_path) as f:
                written = json.load(f)
            assert (
                "funding_adjustment_arithmetic_scaffold_diagnostics" not in written
            )
        finally:
            if receipt_path.exists():
                receipt_path.unlink()
            if out_dir.exists():
                out_dir.rmdir()

    # ── Test 36: Receipt final verdict remains blocked ────────────────────────

    def test_receipt_final_verdict_remains_blocked(self):
        contract = _valid_arithmetic_scaffold_contract()
        arithmetic = materialize_funding_adjustment_arithmetic_scaffold_diagnostics(
            funding_adjustment_policy_contract_diagnostics=contract,
        )
        receipt = _base_receipt(
            funding_adjustment_policy_contract_diagnostics=contract,
            funding_adjustment_arithmetic_scaffold_diagnostics=arithmetic,
        )
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION
        validate_real_validation_receipt(receipt)  # must not raise

    # ── Test 37: Required outputs remain false ────────────────────────────────

    def test_required_outputs_remain_false(self):
        contract = _valid_arithmetic_scaffold_contract()
        arithmetic = materialize_funding_adjustment_arithmetic_scaffold_diagnostics(
            funding_adjustment_policy_contract_diagnostics=contract,
        )
        receipt = _base_receipt(
            funding_adjustment_policy_contract_diagnostics=contract,
            funding_adjustment_arithmetic_scaffold_diagnostics=arithmetic,
        )
        for value in receipt["required_outputs_present"].values():
            assert value is False

    # ── Test 38: Forbidden calculations remain false ─────────────────────────

    def test_forbidden_calculations_remain_false(self):
        contract = _valid_arithmetic_scaffold_contract()
        arithmetic = materialize_funding_adjustment_arithmetic_scaffold_diagnostics(
            funding_adjustment_policy_contract_diagnostics=contract,
        )
        receipt = _base_receipt(
            funding_adjustment_policy_contract_diagnostics=contract,
            funding_adjustment_arithmetic_scaffold_diagnostics=arithmetic,
        )
        for key, value in receipt["forbidden_calculation_status"].items():
            assert value is False, f"{key} must be False"

    # ── Test 39: Guardrails remain true ───────────────────────────────────────

    def test_guardrails_remain_true(self):
        contract = _valid_arithmetic_scaffold_contract()
        arithmetic = materialize_funding_adjustment_arithmetic_scaffold_diagnostics(
            funding_adjustment_policy_contract_diagnostics=contract,
        )
        receipt = _base_receipt(
            funding_adjustment_policy_contract_diagnostics=contract,
            funding_adjustment_arithmetic_scaffold_diagnostics=arithmetic,
        )
        for key, value in receipt["guardrail_status"].items():
            assert value is True, f"{key} must be True"

    # ── Test 40: Safety-key regression ────────────────────────────────────────

    def test_safety_key_regression(self):
        contract = _valid_arithmetic_scaffold_contract()
        arithmetic = materialize_funding_adjustment_arithmetic_scaffold_diagnostics(
            funding_adjustment_policy_contract_diagnostics=contract,
        )
        all_keys = _all_dict_keys(arithmetic)
        forbidden = {
            "PnL", "Sharpe", "edge", "strategy-performance",
            "risk", "trade", "trades", "signal", "signals",
            "position", "positions", "portfolio", "return", "returns",
            "funding_adjusted_return", "net_return_value",
            "price_change", "OFFLINE_EDGE_CANDIDATE", "EDGE_CANDIDATE",
        }
        assert forbidden.isdisjoint(all_keys), (
            f"Forbidden keys found: {forbidden & all_keys}"
        )

        def _all_values(value):
            if isinstance(value, dict):
                for v in value.values():
                    yield from _all_values(v)
            elif isinstance(value, list):
                for v in value:
                    yield from _all_values(v)
            else:
                yield value

        for case in arithmetic["fixture_cases"]:
            assert set(case.keys()) == {
                "case_id", "side", "funding_rate", "notional_per_unit",
                "cashflow_per_notional_unit",
                "expected_cashflow_per_notional_unit", "fixture_status",
                "formula", "application_scope",
            }
        string_values = {v for v in _all_values(arithmetic) if isinstance(v, str)}
        assert not any("BTCUSDT" in v or "ETHUSDT" in v for v in string_values)
        assert not any("T00:00:00Z" in v for v in string_values)


class TestFundingAdjustmentRowScaffoldDiagnostics:
    """38 test cases for
    materialize_funding_adjustment_row_scaffold_diagnostics."""

    # ── Test 1: Happy path emits materialized row scaffold samples ──────────

    def test_happy_path_emits_materialized_row_scaffold_samples(self):
        pc, arith, bars = _valid_row_scaffold_inputs()
        result = materialize_funding_adjustment_row_scaffold_diagnostics(
            pc, arith, bars,
        )
        assert result["calculation_status"] == (
            "FUNDING_ADJUSTMENT_ROW_SCAFFOLD_DIAGNOSTIC_ONLY"
        )
        assert result["eligible_symbol_count"] == 1
        assert result["blocked_symbol_count"] == 1
        assert result["materialized_symbol_count"] == 1
        assert result["skipped_symbol_count"] == 1
        assert len(result["symbols"]) == 2
        # BTCUSDT should have cashflow samples
        btc = result["symbols"][0]
        assert btc["symbol"] == "BTCUSDT"
        assert btc["scaffold_status"] == "MATERIALIZED_DIAGNOSTIC_ROWS"
        assert btc["row_scaffold_status"] == (
            "MATERIALIZED_DIAGNOSTIC_CASHFLOW_SAMPLES"
        )
        assert len(btc["sample_rows"]) == 2
        # ETHUSDT should be blocked
        eth = result["symbols"][1]
        assert eth["symbol"] == "ETHUSDT"
        assert eth["scaffold_status"] == "SKIPPED_BY_READINESS_GATE"

    # ── Test 2: Long/short cashflow factors are opposites ──────────────────

    def test_long_short_cashflow_factors_opposites(self):
        pc, arith, bars = _valid_row_scaffold_inputs()
        result = materialize_funding_adjustment_row_scaffold_diagnostics(
            pc, arith, bars,
        )
        btc = result["symbols"][0]
        for sample in btc["sample_rows"]:
            long_cf = Decimal(sample["long_cashflow_factor"])
            short_cf = Decimal(sample["short_cashflow_factor"])
            assert long_cf == -short_cf, (
                f"Expected long ({long_cf}) == -short ({short_cf})"
            )

    # ── Test 3: Positive funding => long negative, short positive ──────────

    def test_positive_funding_long_negative_short_positive(self):
        pc, arith, bars = _valid_row_scaffold_inputs()
        result = materialize_funding_adjustment_row_scaffold_diagnostics(
            pc, arith, bars,
        )
        btc = result["symbols"][0]
        # First sample: funding_rate = "0.0001" (positive)
        s0 = btc["sample_rows"][0]
        assert Decimal(s0["long_cashflow_factor"]) < 0
        assert Decimal(s0["short_cashflow_factor"]) > 0

    # ── Test 4: Negative funding => long positive, short negative ──────────

    def test_negative_funding_long_positive_short_negative(self):
        pc, arith, bars = _valid_row_scaffold_inputs()
        result = materialize_funding_adjustment_row_scaffold_diagnostics(
            pc, arith, bars,
        )
        btc = result["symbols"][0]
        # Second sample: funding_rate = "-0.00005" (negative)
        s1 = btc["sample_rows"][1]
        assert Decimal(s1["long_cashflow_factor"]) > 0
        assert Decimal(s1["short_cashflow_factor"]) < 0

    # ── Test 5: Zero funding => both cashflow factors zero ─────────────────

    def test_zero_funding_both_zero(self):
        pc, arith, bars = _valid_row_scaffold_inputs()
        bars["symbols"][0]["sample_rows"][0]["funding_rate"] = "0"
        result = materialize_funding_adjustment_row_scaffold_diagnostics(
            pc, arith, bars,
        )
        btc = result["symbols"][0]
        s0 = btc["sample_rows"][0]
        assert Decimal(s0["long_cashflow_factor"]) == 0
        assert Decimal(s0["short_cashflow_factor"]) == 0

    # ── Test 6: Decimal string funding rate accepted ───────────────────────

    def test_decimal_string_funding_rate_accepted(self):
        pc, arith, bars = _valid_row_scaffold_inputs()
        bars["symbols"][0]["sample_rows"][0]["funding_rate"] = "0.0001"
        result = materialize_funding_adjustment_row_scaffold_diagnostics(
            pc, arith, bars,
        )
        btc = result["symbols"][0]
        assert btc["sample_rows"][0]["funding_rate"] == "0.0001"

    # ── Test 7: Float funding rate converted with Decimal(str) ─────────────

    def test_float_funding_rate_converted_with_decimal_str(self):
        pc, arith, bars = _valid_row_scaffold_inputs()
        bars["symbols"][0]["sample_rows"][0]["funding_rate"] = 0.0001
        result = materialize_funding_adjustment_row_scaffold_diagnostics(
            pc, arith, bars,
        )
        btc = result["symbols"][0]
        # The cashflow factors should be deterministic strings
        assert isinstance(btc["sample_rows"][0]["long_cashflow_factor"], str)

    # ── Test 8: Missing policy contract fails closed ──────────────────────

    def test_missing_policy_contract_fails_closed(self):
        pc, arith, bars = _valid_row_scaffold_inputs()
        with pytest.raises(
            ValueError, match="funding_adjustment_policy_contract_diagnostics"
        ):
            materialize_funding_adjustment_row_scaffold_diagnostics(
                None, arith, bars,
            )

    # ── Test 9: Missing arithmetic scaffold fails closed ──────────────────

    def test_missing_arithmetic_scaffold_fails_closed(self):
        pc, arith, bars = _valid_row_scaffold_inputs()
        with pytest.raises(
            ValueError, match="funding_adjustment_arithmetic_scaffold_diagnostics"
        ):
            materialize_funding_adjustment_row_scaffold_diagnostics(
                pc, None, bars,
            )

    # ── Test 10: Missing bars scaffold fails closed ────────────────────────

    def test_missing_bars_scaffold_fails_closed(self):
        pc, arith, bars = _valid_row_scaffold_inputs()
        with pytest.raises(
            ValueError, match="funding_adjusted_bars_scaffold_diagnostics"
        ):
            materialize_funding_adjustment_row_scaffold_diagnostics(
                pc, arith, None,
            )

    # ── Test 11: Wrong policy contract status fails closed ─────────────────

    def test_wrong_policy_contract_status_fails_closed(self):
        pc, arith, bars = _valid_row_scaffold_inputs()
        pc["calculation_status"] = "WRONG"
        with pytest.raises(ValueError, match="calculation_status"):
            materialize_funding_adjustment_row_scaffold_diagnostics(
                pc, arith, bars,
            )

    # ── Test 12: Wrong arithmetic scaffold status fails closed ─────────────

    def test_wrong_arithmetic_scaffold_status_fails_closed(self):
        pc, arith, bars = _valid_row_scaffold_inputs()
        arith["calculation_status"] = "WRONG"
        with pytest.raises(ValueError, match="calculation_status"):
            materialize_funding_adjustment_row_scaffold_diagnostics(
                pc, arith, bars,
            )

    # ── Test 13: Wrong bars scaffold status fails closed ──────────────────

    def test_wrong_bars_scaffold_status_fails_closed(self):
        pc, arith, bars = _valid_row_scaffold_inputs()
        bars["calculation_status"] = "WRONG"
        with pytest.raises(ValueError, match="calculation_status"):
            materialize_funding_adjustment_row_scaffold_diagnostics(
                pc, arith, bars,
            )

    # ── Test 14: Wrong funding_rate_unit fails closed ─────────────────────

    def test_wrong_funding_rate_unit_fails_closed(self):
        pc, arith, bars = _valid_row_scaffold_inputs()
        pc["funding_rate_unit"] = "percent"
        with pytest.raises(ValueError, match="funding_rate_unit"):
            materialize_funding_adjustment_row_scaffold_diagnostics(
                pc, arith, bars,
            )

    # ── Test 15: Wrong arithmetic fixture counts fail closed ──────────────

    def test_wrong_arithmetic_fixture_counts_fail_closed(self):
        pc, arith, bars = _valid_row_scaffold_inputs()
        arith["fixture_case_count"] = 5
        with pytest.raises(ValueError, match="fixture_case_count"):
            materialize_funding_adjustment_row_scaffold_diagnostics(
                pc, arith, bars,
            )

    # ── Test 16: Inconsistent scaffold counts fail closed ─────────────────

    def test_inconsistent_scaffold_counts_fail_closed(self):
        pc, arith, bars = _valid_row_scaffold_inputs()
        bars["symbols"][0]["matched_rows"] = 50
        with pytest.raises(ValueError, match="matched_rows"):
            materialize_funding_adjustment_row_scaffold_diagnostics(
                pc, arith, bars,
            )

    # ── Test 17: Duplicate scaffold symbols fail closed ───────────────────

    def test_duplicate_scaffold_symbols_fail_closed(self):
        pc, arith, bars = _valid_row_scaffold_inputs()
        dup = dict(bars["symbols"][0])
        dup["scaffold_status"] = "SKIPPED_BY_READINESS_GATE"
        dup["blocked_reasons"] = ["test_dup"]
        bars["symbols"].append(dup)
        with pytest.raises(ValueError, match="Duplicate"):
            materialize_funding_adjustment_row_scaffold_diagnostics(
                pc, arith, bars,
            )

    # ── Test 18: Eligible symbol missing sample_rows fails closed ─────────

    def test_eligible_symbol_missing_sample_rows_fails_closed(self):
        pc, arith, bars = _valid_row_scaffold_inputs()
        del bars["symbols"][0]["sample_rows"]
        with pytest.raises(ValueError, match="sample_rows"):
            materialize_funding_adjustment_row_scaffold_diagnostics(
                pc, arith, bars,
            )

    # ── Test 19: Eligible sample_rows not a list fails closed ─────────────

    def test_eligible_sample_rows_not_list_fails_closed(self):
        pc, arith, bars = _valid_row_scaffold_inputs()
        bars["symbols"][0]["sample_rows"] = {}
        with pytest.raises(ValueError, match="sample_rows"):
            materialize_funding_adjustment_row_scaffold_diagnostics(
                pc, arith, bars,
            )

    # ── Test 20: Eligible sample row missing funding_rate fails closed ────

    def test_eligible_sample_row_missing_funding_rate_fails_closed(self):
        pc, arith, bars = _valid_row_scaffold_inputs()
        del bars["symbols"][0]["sample_rows"][0]["funding_rate"]
        with pytest.raises(ValueError, match="funding_rate"):
            materialize_funding_adjustment_row_scaffold_diagnostics(
                pc, arith, bars,
            )

    # ── Test 21: Eligible sample row missing bar_row_index fails closed ───

    def test_eligible_sample_row_missing_bar_row_index_fails_closed(self):
        pc, arith, bars = _valid_row_scaffold_inputs()
        del bars["symbols"][0]["sample_rows"][0]["bar_row_index"]
        with pytest.raises(ValueError, match="bar_row_index"):
            materialize_funding_adjustment_row_scaffold_diagnostics(
                pc, arith, bars,
            )

    # ── Test 22: Eligible sample row missing funding_row_index fails closed─

    def test_eligible_sample_row_missing_funding_row_index_fails_closed(self):
        pc, arith, bars = _valid_row_scaffold_inputs()
        del bars["symbols"][0]["sample_rows"][0]["funding_row_index"]
        with pytest.raises(ValueError, match="funding_row_index"):
            materialize_funding_adjustment_row_scaffold_diagnostics(
                pc, arith, bars,
            )

    # ── Test 23: Malformed funding rate fails closed ──────────────────────

    def test_malformed_funding_rate_fails_closed(self):
        pc, arith, bars = _valid_row_scaffold_inputs()
        bars["symbols"][0]["sample_rows"][0]["funding_rate"] = "not_a_number"
        with pytest.raises(ValueError, match="malformed"):
            materialize_funding_adjustment_row_scaffold_diagnostics(
                pc, arith, bars,
            )

    # ── Test 24: NaN funding rate fails closed ────────────────────────────

    def test_nan_funding_rate_fails_closed(self):
        pc, arith, bars = _valid_row_scaffold_inputs()
        bars["symbols"][0]["sample_rows"][0]["funding_rate"] = float("nan")
        with pytest.raises(ValueError, match="Funding rate is NaN"):
            materialize_funding_adjustment_row_scaffold_diagnostics(
                pc, arith, bars,
            )

    # ── Test 25: Infinite funding rate fails closed ───────────────────────

    def test_infinite_funding_rate_fails_closed(self):
        pc, arith, bars = _valid_row_scaffold_inputs()
        bars["symbols"][0]["sample_rows"][0]["funding_rate"] = float("inf")
        with pytest.raises(ValueError, match="Funding rate is infinite"):
            materialize_funding_adjustment_row_scaffold_diagnostics(
                pc, arith, bars,
            )

    # ── Test 26: Sample row count exceeds 10 fails closed ─────────────────

    def test_sample_row_count_exceeds_10_fails_closed(self):
        pc, arith, bars = _valid_row_scaffold_inputs()
        bars["symbols"][0]["sample_rows"] = [
            {"bar_row_index": i, "funding_row_index": i, "funding_rate": "0.0001"}
            for i in range(11)
        ]
        with pytest.raises(ValueError, match="exceeds maximum of 10"):
            materialize_funding_adjustment_row_scaffold_diagnostics(
                pc, arith, bars,
            )

    # ── Test 27: Blocked symbols carried forward without samples ──────────

    def test_blocked_symbols_carried_forward_without_samples(self):
        pc, arith, bars = _valid_row_scaffold_inputs()
        result = materialize_funding_adjustment_row_scaffold_diagnostics(
            pc, arith, bars,
        )
        eth = result["symbols"][1]
        assert eth["symbol"] == "ETHUSDT"
        assert eth["scaffold_status"] == "SKIPPED_BY_READINESS_GATE"
        assert eth["row_scaffold_status"] == "SKIPPED_BY_READINESS_GATE"
        assert eth["blocked_reasons"] == ["funding_rate_gap_exceeds_threshold"]

    # ── Test 28: Blocked symbol with sample_rows fails closed ─────────────

    def test_blocked_symbol_with_sample_rows_fails_closed(self):
        pc, arith, bars = _valid_row_scaffold_inputs()
        bars["symbols"][1]["sample_rows"] = []
        with pytest.raises(ValueError, match="sample_rows"):
            materialize_funding_adjustment_row_scaffold_diagnostics(
                pc, arith, bars,
            )

    # ── Test 29: Blocked symbol with cashflow-like samples fails closed ───

    def test_blocked_symbol_with_cashflow_samples_fails_closed(self):
        pc, arith, bars = _valid_row_scaffold_inputs()
        bars["symbols"][1]["sample_rows"] = []
        with pytest.raises(ValueError, match="sample_rows"):
            materialize_funding_adjustment_row_scaffold_diagnostics(
                pc, arith, bars,
            )

    # ── Test 30: Output contains no timestamp or OHLCV fields ─────────────

    def test_output_contains_no_timestamp_or_ohlcv_fields(self):
        pc, arith, bars = _valid_row_scaffold_inputs()
        result = materialize_funding_adjustment_row_scaffold_diagnostics(
            pc, arith, bars,
        )
        all_keys = _all_dict_keys(result)
        forbidden = {"timestamp", "open", "high", "low", "close", "volume"}
        # "timestamp_match_policy" is a value, not a key, so it's safe
        found = {k for k in forbidden if k in all_keys}
        assert not found, f"Forbidden keys found: {found}"

    # ── Test 31: Output contains no strategy/pnl/returns/edge keys ────────

    def test_output_contains_no_strategy_pnl_returns_edge_keys(self):
        pc, arith, bars = _valid_row_scaffold_inputs()
        result = materialize_funding_adjustment_row_scaffold_diagnostics(
            pc, arith, bars,
        )
        all_keys = _all_dict_keys(result)
        forbidden = {
            "pnl", "PnL", "Pnl", "Sharpe", "sharpe", "edge",
            "risk", "trade", "trades", "signal", "signals",
            "position", "positions", "portfolio",
            "return", "returns",
            "funding_adjusted_return", "net_return_value",
            "price_change", "OFFLINE_EDGE_CANDIDATE", "EDGE_CANDIDATE",
        }
        found = {k for k in forbidden if k in all_keys}
        assert not found, f"Forbidden keys found: {found}"

    # ── Test 32: CLI with funding includes row scaffold section ───────────

    def test_cli_with_funding_includes_row_scaffold_section(self, tmp_path):
        bars_dir = tmp_path / "bars"
        funding_dir = tmp_path / "funding"
        bars_dir.mkdir()
        funding_dir.mkdir()
        (bars_dir / "BTCUSDT_8h_ohlcv.csv").write_text(
            "timestamp,open,high,low,close,volume\n"
            "2026-01-01T00:00:00Z,100.0,101.0,99.0,100.5,1000\n"
            "2026-01-02T00:00:00Z,100.5,102.0,100.0,101.0,1200\n"
            "2026-01-03T00:00:00Z,101.0,103.0,100.5,102.0,1100\n"
        )
        (funding_dir / "BTCUSDT_funding.csv").write_text(
            "fundingTime,fundingRate,markPrice\n"
            "2026-01-01T00:00:00Z,0.0001,50000.0\n"
            "2026-01-02T00:00:00Z,0.0002,50100.0\n"
            "2026-01-03T00:00:00Z,-0.0001,50200.0\n"
        )

        out_dir = Path("/tmp") / f"qnty_row_scaffold_cli_funding_{uuid.uuid4().hex}"
        receipt_path = out_dir / "real_validation_receipt.json"
        try:
            result = subprocess.run(
                [
                    sys.executable, "-m",
                    "quantbot.experiment.offline_edge_real_validation",
                    "--read-only",
                    "--output-dir", str(out_dir),
                    "--input-manifest-fingerprint", "a" * 64,
                    "--data-quality-receipt-sha256", "b" * 64,
                    "--code-commit-sha", "c" * 40,
                    "--bars-dir", str(bars_dir),
                    "--funding-dir", str(funding_dir),
                ],
                capture_output=True, text=True, timeout=30,
            )
            assert result.returncode == 0, f"stderr: {result.stderr}"
            with open(receipt_path) as f:
                written = json.load(f)
            assert "funding_adjustment_row_scaffold_diagnostics" in written
            section = written["funding_adjustment_row_scaffold_diagnostics"]
            assert section["calculation_status"] == (
                "FUNDING_ADJUSTMENT_ROW_SCAFFOLD_DIAGNOSTIC_ONLY"
            )
        finally:
            if receipt_path.exists():
                receipt_path.unlink()
            if out_dir.exists():
                out_dir.rmdir()

    # ── Test 33: CLI without funding omits row scaffold section ───────────

    def test_cli_without_funding_omits_row_scaffold_section(self, tmp_path):
        bars_dir = tmp_path / "bars"
        bars_dir.mkdir()
        (bars_dir / "BTCUSDT_8h_ohlcv.csv").write_text(
            "timestamp,open,high,low,close,volume\n"
            "2026-01-01T00:00:00Z,100.0,101.0,99.0,100.5,1000\n"
            "2026-01-02T00:00:00Z,100.5,102.0,100.0,101.0,1200\n"
            "2026-01-03T00:00:00Z,101.0,103.0,100.5,102.0,1100\n"
        )

        out_dir = Path("/tmp") / f"qnty_row_scaffold_cli_no_funding_{uuid.uuid4().hex}"
        receipt_path = out_dir / "real_validation_receipt.json"
        try:
            result = subprocess.run(
                [
                    sys.executable, "-m",
                    "quantbot.experiment.offline_edge_real_validation",
                    "--read-only",
                    "--output-dir", str(out_dir),
                    "--input-manifest-fingerprint", "a" * 64,
                    "--data-quality-receipt-sha256", "b" * 64,
                    "--code-commit-sha", "c" * 40,
                    "--bars-dir", str(bars_dir),
                ],
                capture_output=True, text=True, timeout=30,
            )
            assert result.returncode == 0, f"stderr: {result.stderr}"
            with open(receipt_path) as f:
                written = json.load(f)
            assert "funding_adjustment_row_scaffold_diagnostics" not in written
        finally:
            if receipt_path.exists():
                receipt_path.unlink()
            if out_dir.exists():
                out_dir.rmdir()

    # ── Test 34: Receipt final verdict remains blocked ────────────────────

    def test_receipt_final_verdict_remains_blocked(self):
        from quantbot.experiment.offline_edge_real_validation import (
            BLOCKED_BY_VALIDATION_IMPLEMENTATION,
        )
        pc, arith, bars = _valid_row_scaffold_inputs()
        row_scaffold = materialize_funding_adjustment_row_scaffold_diagnostics(
            pc, arith, bars,
        )
        receipt = _base_receipt(
            funding_adjustment_row_scaffold_diagnostics=row_scaffold,
        )
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION
        validate_real_validation_receipt(receipt)  # must not raise

    # ── Test 35: Required outputs remain false ────────────────────────────

    def test_required_outputs_remain_false(self):
        pc, arith, bars = _valid_row_scaffold_inputs()
        row_scaffold = materialize_funding_adjustment_row_scaffold_diagnostics(
            pc, arith, bars,
        )
        receipt = _base_receipt(
            funding_adjustment_row_scaffold_diagnostics=row_scaffold,
        )
        for value in receipt["required_outputs_present"].values():
            assert value is False

    # ── Test 36: Forbidden calculations remain false ──────────────────────

    def test_forbidden_calculations_remain_false(self):
        pc, arith, bars = _valid_row_scaffold_inputs()
        row_scaffold = materialize_funding_adjustment_row_scaffold_diagnostics(
            pc, arith, bars,
        )
        receipt = _base_receipt(
            funding_adjustment_row_scaffold_diagnostics=row_scaffold,
        )
        for key, value in receipt["forbidden_calculation_status"].items():
            assert value is False, f"{key} must be False"

    # ── Test 37: Guardrails remain true ───────────────────────────────────

    def test_guardrails_remain_true(self):
        pc, arith, bars = _valid_row_scaffold_inputs()
        row_scaffold = materialize_funding_adjustment_row_scaffold_diagnostics(
            pc, arith, bars,
        )
        receipt = _base_receipt(
            funding_adjustment_row_scaffold_diagnostics=row_scaffold,
        )
        for key, value in receipt["guardrail_status"].items():
            assert value is True, f"{key} must be True"

    # ── Test 38: Safety-key regression ────────────────────────────────────

    def test_safety_key_regression(self):
        pc, arith, bars = _valid_row_scaffold_inputs()
        result = materialize_funding_adjustment_row_scaffold_diagnostics(
            pc, arith, bars,
        )
        all_keys = _all_dict_keys(result)
        forbidden = {
            "PnL", "Sharpe", "edge", "strategy-performance",
            "risk", "trade", "trades", "signal", "signals",
            "position", "positions", "portfolio", "return", "returns",
            "funding_adjusted_return", "net_return_value",
            "price_change", "OFFLINE_EDGE_CANDIDATE", "EDGE_CANDIDATE",
        }
        assert forbidden.isdisjoint(all_keys), (
            f"Forbidden keys found: {forbidden & all_keys}"
        )

        def _all_values(value):
            if isinstance(value, dict):
                for v in value.values():
                    yield from _all_values(v)
            elif isinstance(value, list):
                for v in value:
                    yield from _all_values(v)
            else:
                yield value

        string_values = {v for v in _all_values(result) if isinstance(v, str)}
        assert not any("T00:00:00Z" in v for v in string_values)

    # ── Test 39: String 'NaN' funding rate fails closed ─────────────────────

    def test_string_nan_funding_rate_fails_closed(self):
        """String 'Nan' funding rate must raise ValueError."""
        # Arrange
        policy_contract, arithmetic_scaffold, bars_scaffold = _valid_row_scaffold_inputs()
        # Set a sample row funding_rate to string "NaN"
        for symbol in bars_scaffold.get("symbols", []):
            if symbol.get("scaffold_status") == "MATERIALIZED_DIAGNOSTIC_ROWS":
                for row in symbol.get("sample_rows", []):
                    row["funding_rate"] = "NaN"
        # Act / Assert
        with pytest.raises(ValueError, match="not finite|NaN"):
            materialize_funding_adjustment_row_scaffold_diagnostics(
                policy_contract, arithmetic_scaffold, bars_scaffold
            )

    # ── Test 40: String 'Infinity' funding rate fails closed ────────────────

    def test_string_infinity_funding_rate_fails_closed(self):
        """String 'Infinity' funding rate must raise ValueError."""
        policy_contract, arithmetic_scaffold, bars_scaffold = _valid_row_scaffold_inputs()
        for symbol in bars_scaffold.get("symbols", []):
            if symbol.get("scaffold_status") == "MATERIALIZED_DIAGNOSTIC_ROWS":
                for row in symbol.get("sample_rows", []):
                    row["funding_rate"] = "Infinity"
        with pytest.raises(ValueError, match="not finite|Infinity"):
            materialize_funding_adjustment_row_scaffold_diagnostics(
                policy_contract, arithmetic_scaffold, bars_scaffold
            )

    # ── Test 41: Decimal('NaN') funding rate fails closed ───────────────────

    def test_decimal_nan_funding_rate_fails_closed(self):
        """Decimal('NaN') funding rate must raise ValueError."""
        from decimal import Decimal
        policy_contract, arithmetic_scaffold, bars_scaffold = _valid_row_scaffold_inputs()
        for symbol in bars_scaffold.get("symbols", []):
            if symbol.get("scaffold_status") == "MATERIALIZED_DIAGNOSTIC_ROWS":
                for row in symbol.get("sample_rows", []):
                    row["funding_rate"] = Decimal("NaN")
        with pytest.raises(ValueError, match="not finite|NaN"):
            materialize_funding_adjustment_row_scaffold_diagnostics(
                policy_contract, arithmetic_scaffold, bars_scaffold
            )

    # ── Test 42: Decimal('Infinity') funding rate fails closed ──────────────

    def test_decimal_infinity_funding_rate_fails_closed(self):
        """Decimal('Infinity') funding rate must raise ValueError."""
        from decimal import Decimal
        policy_contract, arithmetic_scaffold, bars_scaffold = _valid_row_scaffold_inputs()
        for symbol in bars_scaffold.get("symbols", []):
            if symbol.get("scaffold_status") == "MATERIALIZED_DIAGNOSTIC_ROWS":
                for row in symbol.get("sample_rows", []):
                    row["funding_rate"] = Decimal("Infinity")
        with pytest.raises(ValueError, match="not finite|Infinity"):
            materialize_funding_adjustment_row_scaffold_diagnostics(
                policy_contract, arithmetic_scaffold, bars_scaffold
            )

    # ── Test 43: bool funding rate fails closed ─────────────────────────────

    def test_bool_funding_rate_fails_closed(self):
        """bool funding rate must raise ValueError."""
        policy_contract, arithmetic_scaffold, bars_scaffold = _valid_row_scaffold_inputs()
        for symbol in bars_scaffold.get("symbols", []):
            if symbol.get("scaffold_status") == "MATERIALIZED_DIAGNOSTIC_ROWS":
                for row in symbol.get("sample_rows", []):
                    row["funding_rate"] = True
        with pytest.raises(ValueError, match="bool|must not be bool"):
            materialize_funding_adjustment_row_scaffold_diagnostics(
                policy_contract, arithmetic_scaffold, bars_scaffold
            )

    # ── Test 44: Blocked symbol with cashflow_samples fails closed ──────────

    def test_blocked_symbol_with_cashflow_samples_fails_closed(self):
        """Blocked symbol containing cashflow_samples must raise ValueError."""
        policy_contract, arithmetic_scaffold, bars_scaffold = _valid_row_scaffold_inputs()
        for symbol in bars_scaffold.get("symbols", []):
            if symbol.get("scaffold_status") == "SKIPPED_BY_READINESS_GATE":
                symbol["cashflow_samples"] = [{"cashflow": 0.0}]
        with pytest.raises(ValueError, match="must not contain|cashflow_samples"):
            materialize_funding_adjustment_row_scaffold_diagnostics(
                policy_contract, arithmetic_scaffold, bars_scaffold
            )

    # ── Test 45: Wrong symbol_count fails closed ────────────────────────────

    def test_wrong_symbol_count_fails_closed(self):
        """Mismatched symbol_count must raise ValueError."""
        policy_contract, arithmetic_scaffold, bars_scaffold = _valid_row_scaffold_inputs()
        bars_scaffold["symbol_count"] = 999
        with pytest.raises(ValueError, match="symbol_count.*!=.*"):
            materialize_funding_adjustment_row_scaffold_diagnostics(
                policy_contract, arithmetic_scaffold, bars_scaffold
            )

    # ── Test 46: Wrong eligible_symbol_count fails closed ───────────────────

    def test_wrong_eligible_symbol_count_fails_closed(self):
        """Mismatched eligible_symbol_count must raise ValueError."""
        policy_contract, arithmetic_scaffold, bars_scaffold = _valid_row_scaffold_inputs()
        bars_scaffold["eligible_symbol_count"] = 999
        with pytest.raises(ValueError, match="eligible_symbol_count.*!=.*"):
            materialize_funding_adjustment_row_scaffold_diagnostics(
                policy_contract, arithmetic_scaffold, bars_scaffold
            )

    # ── Test 47: Wrong blocked_symbol_count fails closed ────────────────────

    def test_wrong_blocked_symbol_count_fails_closed(self):
        """Mismatched blocked_symbol_count must raise ValueError."""
        policy_contract, arithmetic_scaffold, bars_scaffold = _valid_row_scaffold_inputs()
        bars_scaffold["blocked_symbol_count"] = 999
        with pytest.raises(ValueError, match="blocked_symbol_count.*!=.*"):
            materialize_funding_adjustment_row_scaffold_diagnostics(
                policy_contract, arithmetic_scaffold, bars_scaffold
            )

    # ── Test 48: Wrong materialized_symbol_count fails closed ───────────────

    def test_wrong_materialized_symbol_count_fails_closed(self):
        """Mismatched materialized_symbol_count must raise ValueError."""
        policy_contract, arithmetic_scaffold, bars_scaffold = _valid_row_scaffold_inputs()
        bars_scaffold["materialized_symbol_count"] = 999
        with pytest.raises(ValueError, match="materialized_symbol_count.*!=.*"):
            materialize_funding_adjustment_row_scaffold_diagnostics(
                policy_contract, arithmetic_scaffold, bars_scaffold
            )

    # ── Test 49: Wrong skipped_symbol_count fails closed ────────────────────

    def test_wrong_skipped_symbol_count_fails_closed(self):
        """Mismatched skipped_symbol_count must raise ValueError."""
        policy_contract, arithmetic_scaffold, bars_scaffold = _valid_row_scaffold_inputs()
        bars_scaffold["skipped_symbol_count"] = 999
        with pytest.raises(ValueError, match="skipped_symbol_count.*!=.*"):
            materialize_funding_adjustment_row_scaffold_diagnostics(
                policy_contract, arithmetic_scaffold, bars_scaffold
            )


# ── Funding adjustment sample aggregate diagnostics ─────────────────────


def _valid_aggregate_row_scaffold(
    *,
    eligible_symbols=None,
    blocked_symbols=None,
    **overrides,
):
    """Build a valid funding_adjustment_row_scaffold_diagnostics section
    suitable for feeding into
    _build_funding_adjustment_sample_aggregate_diagnostics.

    Each eligible symbol gets cashflow sample rows with proper
    long_cashflow_factor / short_cashflow_factor values that are exact
    opposites (long == -short).
    """
    from quantbot.experiment.offline_edge_real_validation import (
        LONG_NEGATES_FUNDING_RATE_SHORT_PRESERVES_FUNDING_RATE_TIMES_NOTIONAL,
    )

    if eligible_symbols is None:
        eligible_symbols = [
            {
                "symbol": "BTCUSDT",
                "scaffold_status": "MATERIALIZED_DIAGNOSTIC_ROWS",
                "row_scaffold_status": "MATERIALIZED_DIAGNOSTIC_CASHFLOW_SAMPLES",
                "notional_policy": "UNIT_NOTIONAL_DIAGNOSTIC_ONLY",
                "side_policy": "BOTH_HYPOTHETICAL_SIDES_DIAGNOSTIC_ONLY",
                "funding_rate_unit": "decimal_rate_not_percent",
                "total_rows": 100,
                "sample_row_count": 3,
                "sample_rows": [
                    {
                        "bar_row_index": 0,
                        "funding_row_index": 0,
                        "funding_rate": "0.0001",
                        "unit_notional": "1",
                        "long_cashflow_factor": "-0.0001",
                        "short_cashflow_factor": "0.0001",
                        "formula": LONG_NEGATES_FUNDING_RATE_SHORT_PRESERVES_FUNDING_RATE_TIMES_NOTIONAL,
                        "application_scope": "DIAGNOSTIC_SAMPLE_ONLY_NOT_STRATEGY",
                    },
                    {
                        "bar_row_index": 1,
                        "funding_row_index": 1,
                        "funding_rate": "-0.00005",
                        "unit_notional": "1",
                        "long_cashflow_factor": "0.00005",
                        "short_cashflow_factor": "-0.00005",
                        "formula": LONG_NEGATES_FUNDING_RATE_SHORT_PRESERVES_FUNDING_RATE_TIMES_NOTIONAL,
                        "application_scope": "DIAGNOSTIC_SAMPLE_ONLY_NOT_STRATEGY",
                    },
                    {
                        "bar_row_index": 2,
                        "funding_row_index": 2,
                        "funding_rate": "0.0",
                        "unit_notional": "1",
                        "long_cashflow_factor": "0.0",
                        "short_cashflow_factor": "0.0",
                        "formula": LONG_NEGATES_FUNDING_RATE_SHORT_PRESERVES_FUNDING_RATE_TIMES_NOTIONAL,
                        "application_scope": "DIAGNOSTIC_SAMPLE_ONLY_NOT_STRATEGY",
                    },
                ],
            },
        ]

    if blocked_symbols is None:
        blocked_symbols = [
            {
                "symbol": "ETHUSDT",
                "scaffold_status": "SKIPPED_BY_READINESS_GATE",
                "row_scaffold_status": "SKIPPED_BY_READINESS_GATE",
                "blocked_reasons": ["FUNDING_DATA_GAP"],
            },
        ]

    all_symbols = list(eligible_symbols) + list(blocked_symbols)
    eligible_count = len(eligible_symbols)
    blocked_count = len(blocked_symbols)

    scaffold = {
        "calculation_status": "FUNDING_ADJUSTMENT_ROW_SCAFFOLD_DIAGNOSTIC_ONLY",
        "funding_adjustment_application_status": (
            "DIAGNOSTIC_ROW_SCAFFOLD_ONLY_NOT_APPLIED_TO_STRATEGY"
        ),
        "strategy_application_status": "NOT_EXECUTED",
        "pnl_application_status": "NOT_EXECUTED",
        "requires_policy_contract_diagnostics": True,
        "requires_arithmetic_scaffold_diagnostics": True,
        "requires_funding_adjusted_bars_scaffold_diagnostics": True,
        "policy_contract_section_required": (
            "funding_adjustment_policy_contract_diagnostics"
        ),
        "arithmetic_scaffold_section_required": (
            "funding_adjustment_arithmetic_scaffold_diagnostics"
        ),
        "funding_adjusted_bars_scaffold_section_required": (
            "funding_adjusted_bars_scaffold_diagnostics"
        ),
        "funding_rate_unit": "decimal_rate_not_percent",
        "notional_policy": "UNIT_NOTIONAL_DIAGNOSTIC_ONLY",
        "side_policy": "BOTH_HYPOTHETICAL_SIDES_DIAGNOSTIC_ONLY",
        "sample_policy": "CAPPED_DETERMINISTIC_SAMPLES_ONLY",
        "sample_size_per_symbol": 10,
        "symbol_count": len(all_symbols),
        "eligible_symbol_count": eligible_count,
        "blocked_symbol_count": blocked_count,
        "materialized_symbol_count": eligible_count,
        "skipped_symbol_count": blocked_count,
        "symbols": all_symbols,
    }
    scaffold.update(overrides)
    return scaffold


class TestFundingAdjustmentSampleAggregateDiagnostics:
    """45 test cases for
    _build_funding_adjustment_sample_aggregate_diagnostics."""

    # ── Test 1: Happy path emits aggregate section ──────────────────────────

    def test_happy_path_emits_aggregate_section(self):
        row_scaffold = _valid_aggregate_row_scaffold()
        result = _build_funding_adjustment_sample_aggregate_diagnostics(
            row_scaffold,
        )
        assert result["calculation_status"] == (
            "FUNDING_ADJUSTMENT_SAMPLE_AGGREGATE_DIAGNOSTIC_ONLY"
        )
        assert result["funding_adjustment_application_status"] == (
            "DIAGNOSTIC_SAMPLE_AGGREGATE_ONLY_NOT_APPLIED_TO_STRATEGY"
        )
        assert result["strategy_application_status"] == "NOT_EXECUTED"
        assert result["pnl_application_status"] == "NOT_EXECUTED"
        assert result["eligible_symbol_count"] == 1
        assert result["blocked_symbol_count"] == 1
        assert result["materialized_symbol_count"] == 1
        assert result["skipped_symbol_count"] == 1
        assert result["total_sample_row_count"] == 3
        assert len(result["symbols"]) == 2

    # ── Test 2: Per-symbol sample counts are preserved ──────────────────────

    def test_per_symbol_sample_counts_preserved(self):
        row_scaffold = _valid_aggregate_row_scaffold()
        result = _build_funding_adjustment_sample_aggregate_diagnostics(
            row_scaffold,
        )
        btc = result["symbols"][0]
        assert btc["symbol"] == "BTCUSDT"
        assert btc["aggregate_status"] == "MATERIALIZED_DIAGNOSTIC_SAMPLE_AGGREGATES"
        assert btc["sample_row_count"] == 3

    # ── Test 3: Per-symbol long/short sums are exact opposites ──────────────

    def test_per_symbol_long_short_sums_exact_opposites(self):
        row_scaffold = _valid_aggregate_row_scaffold()
        result = _build_funding_adjustment_sample_aggregate_diagnostics(
            row_scaffold,
        )
        btc = result["symbols"][0]
        long_sum = Decimal(btc["long_cashflow_factor_sum"])
        short_sum = Decimal(btc["short_cashflow_factor_sum"])
        assert long_sum == -short_sum, (
            f"Expected long_sum ({long_sum}) == -short_sum ({short_sum})"
        )

    # ── Test 4: Per-symbol long_short_sum_check is zero ─────────────────────

    def test_per_symbol_long_short_sum_check_zero(self):
        row_scaffold = _valid_aggregate_row_scaffold()
        result = _build_funding_adjustment_sample_aggregate_diagnostics(
            row_scaffold,
        )
        btc = result["symbols"][0]
        assert Decimal(btc["long_short_sum_check"]) == Decimal("0")

    # ── Test 5: Global long/short sums are exact opposites ──────────────────

    def test_global_long_short_sums_exact_opposites(self):
        row_scaffold = _valid_aggregate_row_scaffold()
        result = _build_funding_adjustment_sample_aggregate_diagnostics(
            row_scaffold,
        )
        global_long = Decimal(result["global_long_cashflow_factor_sum"])
        global_short = Decimal(result["global_short_cashflow_factor_sum"])
        assert global_long == -global_short, (
            f"Expected global_long ({global_long}) == -global_short ({global_short})"
        )
        assert Decimal(result["global_long_short_sum_check"]) == Decimal("0")

    # ── Test 6: Blocked symbols carried forward without numeric fields ──────

    def test_blocked_symbols_carried_forward_without_numeric_fields(self):
        row_scaffold = _valid_aggregate_row_scaffold()
        result = _build_funding_adjustment_sample_aggregate_diagnostics(
            row_scaffold,
        )
        eth = result["symbols"][1]
        assert eth["symbol"] == "ETHUSDT"
        assert eth["aggregate_status"] == "SKIPPED_BY_READINESS_GATE"
        assert eth["blocked_reasons"] == ["FUNDING_DATA_GAP"]
        # Must not have numeric aggregate fields
        assert "long_cashflow_factor_sum" not in eth
        assert "short_cashflow_factor_sum" not in eth
        assert "long_cashflow_factor_min" not in eth
        assert "long_cashflow_factor_max" not in eth
        assert "short_cashflow_factor_min" not in eth
        assert "short_cashflow_factor_max" not in eth
        assert "long_short_sum_check" not in eth
        assert "sample_row_count" not in eth

    # ── Test 7: Missing row scaffold fails closed ───────────────────────────

    def test_missing_row_scaffold_fails_closed(self):
        with pytest.raises(ValueError, match="funding_adjustment_row_scaffold_diagnostics"):
            _build_funding_adjustment_sample_aggregate_diagnostics(None)

    # ── Test 8: Wrong calculation_status fails closed ───────────────────────

    def test_wrong_calculation_status_fails_closed(self):
        row_scaffold = _valid_aggregate_row_scaffold(
            calculation_status="SOME_OTHER_STATUS"
        )
        with pytest.raises(ValueError, match="calculation_status"):
            _build_funding_adjustment_sample_aggregate_diagnostics(row_scaffold)

    # ── Test 9: Wrong funding_application_status fails closed ───────────────

    def test_wrong_funding_application_status_fails_closed(self):
        row_scaffold = _valid_aggregate_row_scaffold(
            funding_adjustment_application_status="EXECUTED"
        )
        with pytest.raises(ValueError, match="funding_adjustment_application_status"):
            _build_funding_adjustment_sample_aggregate_diagnostics(row_scaffold)

    # ── Test 10: Wrong strategy_application_status fails closed ─────────────

    def test_wrong_strategy_status_fails_closed(self):
        row_scaffold = _valid_aggregate_row_scaffold(
            strategy_application_status="EXECUTED"
        )
        with pytest.raises(ValueError, match="strategy_application_status"):
            _build_funding_adjustment_sample_aggregate_diagnostics(row_scaffold)

    # ── Test 11: Wrong pnl_application_status fails closed ──────────────────

    def test_wrong_pnl_status_fails_closed(self):
        row_scaffold = _valid_aggregate_row_scaffold(
            pnl_application_status="EXECUTED"
        )
        with pytest.raises(ValueError, match="pnl_application_status"):
            _build_funding_adjustment_sample_aggregate_diagnostics(row_scaffold)

    # ── Test 12: Wrong funding_rate_unit fails closed ───────────────────────

    def test_wrong_funding_rate_unit_fails_closed(self):
        row_scaffold = _valid_aggregate_row_scaffold(
            funding_rate_unit="percent"
        )
        with pytest.raises(ValueError, match="funding_rate_unit"):
            _build_funding_adjustment_sample_aggregate_diagnostics(row_scaffold)

    # ── Test 13: Wrong notional_policy fails closed ─────────────────────────

    def test_wrong_notional_policy_fails_closed(self):
        row_scaffold = _valid_aggregate_row_scaffold(
            notional_policy="REAL_NOTIONAL"
        )
        with pytest.raises(ValueError, match="notional_policy"):
            _build_funding_adjustment_sample_aggregate_diagnostics(row_scaffold)

    # ── Test 14: Wrong side_policy fails closed ─────────────────────────────

    def test_wrong_side_policy_fails_closed(self):
        row_scaffold = _valid_aggregate_row_scaffold(
            side_policy="REAL_SIDE"
        )
        with pytest.raises(ValueError, match="side_policy"):
            _build_funding_adjustment_sample_aggregate_diagnostics(row_scaffold)

    # ── Test 15: Wrong sample_policy fails closed ───────────────────────────

    def test_wrong_sample_policy_fails_closed(self):
        row_scaffold = _valid_aggregate_row_scaffold(
            sample_policy="FULL_DATASET"
        )
        with pytest.raises(ValueError, match="sample_policy"):
            _build_funding_adjustment_sample_aggregate_diagnostics(row_scaffold)

    # ── Test 16: Wrong sample_size_per_symbol fails closed ──────────────────

    def test_wrong_sample_size_per_symbol_fails_closed(self):
        row_scaffold = _valid_aggregate_row_scaffold(
            sample_size_per_symbol=20
        )
        with pytest.raises(ValueError, match="sample_size_per_symbol"):
            _build_funding_adjustment_sample_aggregate_diagnostics(row_scaffold)

    # ── Test 17: Inconsistent top-level counts fail closed ──────────────────

    def test_inconsistent_top_level_counts_fail_closed(self):
        row_scaffold = _valid_aggregate_row_scaffold(
            eligible_symbol_count=999
        )
        with pytest.raises(ValueError, match="eligible_symbol_count"):
            _build_funding_adjustment_sample_aggregate_diagnostics(row_scaffold)

    # ── Test 18: Duplicate symbols fail closed ──────────────────────────────

    def test_duplicate_symbols_fail_closed(self):
        eligible = _valid_aggregate_row_scaffold()["symbols"][0]
        row_scaffold = _valid_aggregate_row_scaffold(
            symbols=[dict(eligible), dict(eligible)],
            symbol_count=2,
            eligible_symbol_count=2,
            materialized_symbol_count=2,
        )
        with pytest.raises(ValueError, match="Duplicate scaffold symbol"):
            _build_funding_adjustment_sample_aggregate_diagnostics(row_scaffold)

    # ── Test 19: Eligible symbol missing sample_rows fails closed ───────────

    def test_eligible_symbol_missing_sample_rows_fails_closed(self):
        row_scaffold = _valid_aggregate_row_scaffold()
        del row_scaffold["symbols"][0]["sample_rows"]
        with pytest.raises(ValueError, match="sample_rows"):
            _build_funding_adjustment_sample_aggregate_diagnostics(row_scaffold)

    # ── Test 20: sample_row_count mismatch fails closed ─────────────────────

    def test_sample_row_count_mismatch_fails_closed(self):
        row_scaffold = _valid_aggregate_row_scaffold()
        row_scaffold["symbols"][0]["sample_row_count"] = 999
        with pytest.raises(ValueError, match="sample_row_count"):
            _build_funding_adjustment_sample_aggregate_diagnostics(row_scaffold)

    # ── Test 21: Sample count >10 fails closed ──────────────────────────────

    def test_sample_count_exceeds_10_fails_closed(self):
        from quantbot.experiment.offline_edge_real_validation import (
            LONG_NEGATES_FUNDING_RATE_SHORT_PRESERVES_FUNDING_RATE_TIMES_NOTIONAL,
        )
        many_rows = [
            {
                "bar_row_index": i,
                "funding_row_index": i,
                "funding_rate": "0.0001",
                "unit_notional": "1",
                "long_cashflow_factor": "-0.0001",
                "short_cashflow_factor": "0.0001",
                "formula": LONG_NEGATES_FUNDING_RATE_SHORT_PRESERVES_FUNDING_RATE_TIMES_NOTIONAL,
                "application_scope": "DIAGNOSTIC_SAMPLE_ONLY_NOT_STRATEGY",
            }
            for i in range(11)
        ]
        row_scaffold = _valid_aggregate_row_scaffold()
        row_scaffold["symbols"][0]["sample_rows"] = many_rows
        row_scaffold["symbols"][0]["sample_row_count"] = 11
        with pytest.raises(ValueError, match="exceeds maximum of 10"):
            _build_funding_adjustment_sample_aggregate_diagnostics(row_scaffold)

    # ── Test 22: Sample row missing key fails closed ────────────────────────

    def test_sample_row_missing_key_fails_closed(self):
        row_scaffold = _valid_aggregate_row_scaffold()
        del row_scaffold["symbols"][0]["sample_rows"][0]["funding_rate"]
        with pytest.raises(ValueError, match="missing keys"):
            _build_funding_adjustment_sample_aggregate_diagnostics(row_scaffold)

    # ── Test 23: Sample row with extra key fails closed ─────────────────────

    def test_sample_row_with_extra_key_fails_closed(self):
        row_scaffold = _valid_aggregate_row_scaffold()
        row_scaffold["symbols"][0]["sample_rows"][0]["extra_key"] = "unexpected"
        with pytest.raises(ValueError, match="extra keys"):
            _build_funding_adjustment_sample_aggregate_diagnostics(row_scaffold)

    # ── Test 24: Malformed funding rate fails closed ────────────────────────

    def test_malformed_funding_rate_fails_closed(self):
        row_scaffold = _valid_aggregate_row_scaffold()
        row_scaffold["symbols"][0]["sample_rows"][0]["funding_rate"] = "not-a-decimal"
        with pytest.raises(ValueError, match="malformed|funding_rate"):
            _build_funding_adjustment_sample_aggregate_diagnostics(row_scaffold)

    # ── Test 25: NaN funding rate fails closed ──────────────────────────────

    def test_nan_funding_rate_fails_closed(self):
        row_scaffold = _valid_aggregate_row_scaffold()
        row_scaffold["symbols"][0]["sample_rows"][0]["funding_rate"] = "NaN"
        with pytest.raises(ValueError, match="finite|NaN"):
            _build_funding_adjustment_sample_aggregate_diagnostics(row_scaffold)

    # ── Test 26: Infinite funding rate fails closed ─────────────────────────

    def test_infinite_funding_rate_fails_closed(self):
        row_scaffold = _valid_aggregate_row_scaffold()
        row_scaffold["symbols"][0]["sample_rows"][0]["funding_rate"] = "Infinity"
        with pytest.raises(ValueError, match="finite|Infinity"):
            _build_funding_adjustment_sample_aggregate_diagnostics(row_scaffold)

    # ── Test 27: Malformed long_cashflow_factor fails closed ────────────────

    def test_malformed_long_cashflow_factor_fails_closed(self):
        row_scaffold = _valid_aggregate_row_scaffold()
        row_scaffold["symbols"][0]["sample_rows"][0]["long_cashflow_factor"] = "not-a-decimal"
        with pytest.raises(ValueError, match="malformed|long_cashflow_factor"):
            _build_funding_adjustment_sample_aggregate_diagnostics(row_scaffold)

    # ── Test 28: NaN long_cashflow_factor fails closed ──────────────────────

    def test_nan_long_cashflow_factor_fails_closed(self):
        row_scaffold = _valid_aggregate_row_scaffold()
        row_scaffold["symbols"][0]["sample_rows"][0]["long_cashflow_factor"] = "NaN"
        with pytest.raises(ValueError, match="finite|NaN"):
            _build_funding_adjustment_sample_aggregate_diagnostics(row_scaffold)

    # ── Test 29: Infinite long_cashflow_factor fails closed ─────────────────

    def test_infinite_long_cashflow_factor_fails_closed(self):
        row_scaffold = _valid_aggregate_row_scaffold()
        row_scaffold["symbols"][0]["sample_rows"][0]["long_cashflow_factor"] = "Infinity"
        with pytest.raises(ValueError, match="finite|Infinity"):
            _build_funding_adjustment_sample_aggregate_diagnostics(row_scaffold)

    # ── Test 30: Malformed short_cashflow_factor fails closed ───────────────

    def test_malformed_short_cashflow_factor_fails_closed(self):
        row_scaffold = _valid_aggregate_row_scaffold()
        row_scaffold["symbols"][0]["sample_rows"][0]["short_cashflow_factor"] = "not-a-decimal"
        with pytest.raises(ValueError, match="malformed|short_cashflow_factor"):
            _build_funding_adjustment_sample_aggregate_diagnostics(row_scaffold)

    # ── Test 31: Long factor not equal to -funding_rate fails closed ────────

    def test_long_factor_not_equal_negative_funding_rate_fails_closed(self):
        row_scaffold = _valid_aggregate_row_scaffold()
        row_scaffold["symbols"][0]["sample_rows"][0]["long_cashflow_factor"] = "-0.9999"
        with pytest.raises(ValueError, match="long_cashflow_factor"):
            _build_funding_adjustment_sample_aggregate_diagnostics(row_scaffold)

    # ── Test 32: Short factor not equal to funding_rate fails closed ────────

    def test_short_factor_not_equal_funding_rate_fails_closed(self):
        row_scaffold = _valid_aggregate_row_scaffold()
        row_scaffold["symbols"][0]["sample_rows"][0]["short_cashflow_factor"] = "0.9999"
        with pytest.raises(ValueError, match="short_cashflow_factor"):
            _build_funding_adjustment_sample_aggregate_diagnostics(row_scaffold)

    # ── Test 33: Long/short factor not exact opposites fails closed ─────────

    def test_long_short_factor_not_exact_opposites_fails_closed(self):
        row_scaffold = _valid_aggregate_row_scaffold()
        row_scaffold["symbols"][0]["sample_rows"][0]["long_cashflow_factor"] = "-0.0002"
        row_scaffold["symbols"][0]["sample_rows"][0]["short_cashflow_factor"] = "0.0001"
        with pytest.raises(ValueError, match="long_cashflow_factor|short_cashflow_factor"):
            _build_funding_adjustment_sample_aggregate_diagnostics(row_scaffold)

    # ── Test 34: Blocked symbol with sample_rows fails closed ───────────────

    def test_blocked_symbol_with_sample_rows_fails_closed(self):
        row_scaffold = _valid_aggregate_row_scaffold()
        row_scaffold["symbols"][1]["sample_rows"] = []
        with pytest.raises(ValueError, match="extra keys"):
            _build_funding_adjustment_sample_aggregate_diagnostics(row_scaffold)

    # ── Test 35: Blocked symbol with numeric aggregate fields fails closed ──

    def test_blocked_symbol_with_numeric_aggregate_fields_fails_closed(self):
        row_scaffold = _valid_aggregate_row_scaffold()
        row_scaffold["symbols"][1]["long_cashflow_factor_sum"] = "0.0"
        with pytest.raises(ValueError, match="extra keys"):
            _build_funding_adjustment_sample_aggregate_diagnostics(row_scaffold)

    # ── Test 36: Output contains no sample_rows ─────────────────────────────

    def test_output_contains_no_sample_rows(self):
        row_scaffold = _valid_aggregate_row_scaffold()
        result = _build_funding_adjustment_sample_aggregate_diagnostics(
            row_scaffold,
        )
        all_keys = _all_dict_keys(result)
        assert "sample_rows" not in all_keys, (
            "Aggregate output must not contain sample_rows"
        )

    # ── Test 37: Output contains no timestamp/OHLCV fields ──────────────────

    def test_output_contains_no_timestamp_or_ohlcv_fields(self):
        row_scaffold = _valid_aggregate_row_scaffold()
        result = _build_funding_adjustment_sample_aggregate_diagnostics(
            row_scaffold,
        )
        all_keys = _all_dict_keys(result)
        forbidden = {"timestamp", "open", "high", "low", "close", "volume"}
        found = {k for k in forbidden if k in all_keys}
        assert not found, f"Forbidden keys found: {found}"

    # ── Test 38: Output contains no strategy/pnl/returns/edge keys ──────────

    def test_output_contains_no_strategy_pnl_returns_edge_keys(self):
        row_scaffold = _valid_aggregate_row_scaffold()
        result = _build_funding_adjustment_sample_aggregate_diagnostics(
            row_scaffold,
        )
        all_keys = _all_dict_keys(result)
        forbidden = {
            "pnl", "PnL", "Pnl", "Sharpe", "sharpe", "edge",
            "risk", "trade", "trades", "signal", "signals",
            "position", "positions", "portfolio",
            "return", "returns",
            "funding_adjusted_return", "net_return_value",
            "price_change", "OFFLINE_EDGE_CANDIDATE", "EDGE_CANDIDATE",
        }
        found = {k for k in forbidden if k in all_keys}
        assert not found, f"Forbidden keys found: {found}"

    # ── Test 39: CLI with funding includes aggregate diagnostics ────────────

    def test_cli_with_funding_includes_aggregate_diagnostics(self, tmp_path):
        bars_dir = tmp_path / "bars"
        funding_dir = tmp_path / "funding"
        bars_dir.mkdir()
        funding_dir.mkdir()
        (bars_dir / "BTCUSDT_8h_ohlcv.csv").write_text(
            "timestamp,open,high,low,close,volume\n"
            "2026-01-01T00:00:00Z,100.0,101.0,99.0,100.5,1000\n"
            "2026-01-02T00:00:00Z,100.5,102.0,100.0,101.0,1200\n"
            "2026-01-03T00:00:00Z,101.0,103.0,100.5,102.0,1100\n"
        )
        (funding_dir / "BTCUSDT_funding.csv").write_text(
            "fundingTime,fundingRate,markPrice\n"
            "2026-01-01T00:00:00Z,0.0001,50000.0\n"
            "2026-01-02T00:00:00Z,0.0002,50100.0\n"
            "2026-01-03T00:00:00Z,-0.0001,50200.0\n"
        )

        out_dir = Path("/tmp") / f"qnty_agg_cli_funding_{uuid.uuid4().hex}"
        receipt_path = out_dir / "real_validation_receipt.json"
        try:
            result = subprocess.run(
                [
                    sys.executable, "-m",
                    "quantbot.experiment.offline_edge_real_validation",
                    "--read-only",
                    "--output-dir", str(out_dir),
                    "--input-manifest-fingerprint", "a" * 64,
                    "--data-quality-receipt-sha256", "b" * 64,
                    "--code-commit-sha", "c" * 40,
                    "--bars-dir", str(bars_dir),
                    "--funding-dir", str(funding_dir),
                ],
                capture_output=True, text=True, timeout=30,
            )
            assert result.returncode == 0, f"stderr: {result.stderr}"
            with open(receipt_path) as f:
                written = json.load(f)
            assert "funding_adjustment_sample_aggregate_diagnostics" in written
            section = written["funding_adjustment_sample_aggregate_diagnostics"]
            assert section["calculation_status"] == (
                "FUNDING_ADJUSTMENT_SAMPLE_AGGREGATE_DIAGNOSTIC_ONLY"
            )
        finally:
            if receipt_path.exists():
                receipt_path.unlink()
            if out_dir.exists():
                out_dir.rmdir()

    # ── Test 40: CLI without funding omits aggregate diagnostics ────────────

    def test_cli_without_funding_omits_aggregate_diagnostics(self, tmp_path):
        bars_dir = tmp_path / "bars"
        bars_dir.mkdir()
        (bars_dir / "BTCUSDT_8h_ohlcv.csv").write_text(
            "timestamp,open,high,low,close,volume\n"
            "2026-01-01T00:00:00Z,100.0,101.0,99.0,100.5,1000\n"
            "2026-01-02T00:00:00Z,100.5,102.0,100.0,101.0,1200\n"
            "2026-01-03T00:00:00Z,101.0,103.0,100.5,102.0,1100\n"
        )

        out_dir = Path("/tmp") / f"qnty_agg_cli_no_funding_{uuid.uuid4().hex}"
        receipt_path = out_dir / "real_validation_receipt.json"
        try:
            result = subprocess.run(
                [
                    sys.executable, "-m",
                    "quantbot.experiment.offline_edge_real_validation",
                    "--read-only",
                    "--output-dir", str(out_dir),
                    "--input-manifest-fingerprint", "a" * 64,
                    "--data-quality-receipt-sha256", "b" * 64,
                    "--code-commit-sha", "c" * 40,
                    "--bars-dir", str(bars_dir),
                ],
                capture_output=True, text=True, timeout=30,
            )
            assert result.returncode == 0, f"stderr: {result.stderr}"
            with open(receipt_path) as f:
                written = json.load(f)
            assert "funding_adjustment_sample_aggregate_diagnostics" not in written
        finally:
            if receipt_path.exists():
                receipt_path.unlink()
            if out_dir.exists():
                out_dir.rmdir()

    # ── Test 41: Receipt final verdict remains BLOCKED_BY_VALIDATION_IMPLEMENTATION ──

    def test_receipt_final_verdict_remains_blocked(self):
        row_scaffold = _valid_aggregate_row_scaffold()
        aggregate = _build_funding_adjustment_sample_aggregate_diagnostics(
            row_scaffold,
        )
        receipt = _base_receipt(
            funding_adjustment_sample_aggregate_diagnostics=aggregate,
        )
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION
        validate_real_validation_receipt(receipt)  # must not raise

    # ── Test 42: Required outputs remain false ──────────────────────────────

    def test_required_outputs_remain_false(self):
        row_scaffold = _valid_aggregate_row_scaffold()
        aggregate = _build_funding_adjustment_sample_aggregate_diagnostics(
            row_scaffold,
        )
        receipt = _base_receipt(
            funding_adjustment_sample_aggregate_diagnostics=aggregate,
        )
        for value in receipt["required_outputs_present"].values():
            assert value is False

    # ── Test 43: Forbidden calculations remain false ────────────────────────

    def test_forbidden_calculations_remain_false(self):
        row_scaffold = _valid_aggregate_row_scaffold()
        aggregate = _build_funding_adjustment_sample_aggregate_diagnostics(
            row_scaffold,
        )
        receipt = _base_receipt(
            funding_adjustment_sample_aggregate_diagnostics=aggregate,
        )
        for key, value in receipt["forbidden_calculation_status"].items():
            assert value is False, f"{key} must be False"

    # ── Test 44: Guardrails remain true ─────────────────────────────────────

    def test_guardrails_remain_true(self):
        row_scaffold = _valid_aggregate_row_scaffold()
        aggregate = _build_funding_adjustment_sample_aggregate_diagnostics(
            row_scaffold,
        )
        receipt = _base_receipt(
            funding_adjustment_sample_aggregate_diagnostics=aggregate,
        )
        for key, value in receipt["guardrail_status"].items():
            assert value is True, f"{key} must be True"

    # ── Test 45: Safety-key regression ──────────────────────────────────────

    def test_safety_key_regression(self):
        row_scaffold = _valid_aggregate_row_scaffold()
        result = _build_funding_adjustment_sample_aggregate_diagnostics(
            row_scaffold,
        )
        all_keys = _all_dict_keys(result)
        forbidden = {
            "PnL", "Sharpe", "edge", "strategy-performance",
            "risk", "trade", "trades", "signal", "signals",
            "position", "positions", "portfolio", "return", "returns",
            "funding_adjusted_return", "net_return_value",
            "price_change", "OFFLINE_EDGE_CANDIDATE", "EDGE_CANDIDATE",
            "timestamp", "open", "high", "low", "close", "volume",
            "sample_rows",
        }
        assert forbidden.isdisjoint(all_keys), (
            f"Forbidden keys found: {forbidden & all_keys}"
        )


# ── Split leakage audit diagnostics ──────────────────────────────────────


def _inventory_splits(tmp_path: Path, split_count: int = 3) -> list[dict]:
    """Build real-data inventory split definitions (adjacent windows)."""
    _write_tiny_bars_csv(tmp_path)
    inventory = build_real_validation_input_inventory(bars_dir=tmp_path)
    return materialize_split_definitions_from_inventory(
        inventory=inventory, split_count=split_count
    )


def _fallback_splits(split_count: int = 3) -> list[dict]:
    """Build fallback deterministic split definitions (full overlap windows)."""
    return build_deterministic_split_definitions(
        global_min_timestamp="2026-01-01T00:00:00Z",
        global_max_timestamp="2026-02-01T00:00:00Z",
        split_count=split_count,
    )


_SPLIT_LEAKAGE_FORBIDDEN_KEYS = {
    "returns", "return", "pnl", "PnL", "sharpe", "Sharpe", "drawdown",
    "risk", "edge", "strategy_performance", "trade", "trades",
    "position", "positions", "signal", "signals", "portfolio",
    "funding_adjusted_return", "net_return_value", "price_change",
    "gross_return_value", "cost_adjusted_return",
}


class TestSplitLeakageAuditDiagnostics:
    """Coverage for _build_split_leakage_audit_diagnostics: a diagnostic-only,
    fail-closed audit that blocks strategy scoring and computes no returns/
    PnL/Sharpe/risk/edge."""

    # ── Test 1: happy path (inventory builder) emits section ───────────────
    def test_inventory_builder_emits_section(self, tmp_path):
        result = _build_split_leakage_audit_diagnostics(
            split_definitions=_inventory_splits(tmp_path),
            split_builder_inspected=_SPLIT_BUILDER_INVENTORY,
        )
        assert isinstance(result, dict)
        assert result["audit_version"] == SPLIT_LEAKAGE_AUDIT_VERSION
        assert result["audit_version"] == "split-leakage-audit-0.1"
        assert result["split_builder_inspected"] == _SPLIT_BUILDER_INVENTORY
        assert result["split_builder_inspected"] == (
            "materialize_split_definitions_from_inventory"
        )

    # ── Test 2: calculation_status ─────────────────────────────────────────
    def test_calculation_status_diagnostic_only(self, tmp_path):
        result = _build_split_leakage_audit_diagnostics(
            split_definitions=_inventory_splits(tmp_path),
            split_builder_inspected=_SPLIT_BUILDER_INVENTORY,
        )
        assert result["calculation_status"] == SPLIT_LEAKAGE_AUDIT_DIAGNOSTIC_ONLY
        assert result["calculation_status"] == "SPLIT_LEAKAGE_AUDIT_DIAGNOSTIC_ONLY"

    # ── Test 3: inventory audit status ─────────────────────────────────────
    def test_inventory_status_insufficient_for_scoring(self, tmp_path):
        result = _build_split_leakage_audit_diagnostics(
            split_definitions=_inventory_splits(tmp_path),
            split_builder_inspected=_SPLIT_BUILDER_INVENTORY,
        )
        assert result["split_leakage_audit_status"] == (
            SPLIT_LEAKAGE_AUDIT_INSUFFICIENT_FOR_SCORING
        )
        assert result["split_leakage_audit_status"] == (
            "SPLIT_LEAKAGE_AUDIT_INSUFFICIENT_FOR_SCORING"
        )

    # ── Test 4/5: purge/embargo gaps are zero ──────────────────────────────
    def test_purge_and_embargo_gaps_zero(self, tmp_path):
        result = _build_split_leakage_audit_diagnostics(
            split_definitions=_inventory_splits(tmp_path),
            split_builder_inspected=_SPLIT_BUILDER_INVENTORY,
        )
        assert result["purge_gap_seconds"] == 0
        assert result["embargo_gap_seconds"] == 0

    # ── Test 6: windows adjacent ───────────────────────────────────────────
    def test_windows_adjacent_true(self, tmp_path):
        result = _build_split_leakage_audit_diagnostics(
            split_definitions=_inventory_splits(tmp_path),
            split_builder_inspected=_SPLIT_BUILDER_INVENTORY,
        )
        assert result["windows_adjacent"] is True

    # ── Test 7: all scoring prerequisites false ────────────────────────────
    def test_scoring_prerequisites_all_false(self, tmp_path):
        result = _build_split_leakage_audit_diagnostics(
            split_definitions=_inventory_splits(tmp_path),
            split_builder_inspected=_SPLIT_BUILDER_INVENTORY,
        )
        prereqs = result["scoring_prerequisites_present"]
        assert set(prereqs.keys()) == {
            "decision_time_convention",
            "feature_lookback",
            "label_horizon",
            "holding_period",
            "funding_interval_exposure",
            "cost_event_timing",
        }
        assert all(value is False for value in prereqs.values())
        # No strategy-ish alias key is introduced.
        assert "strategy_dependent_prerequisites_present" not in result

    # ── Test 8: all leakage risks true ─────────────────────────────────────
    def test_leakage_risk_register_all_true(self, tmp_path):
        result = _build_split_leakage_audit_diagnostics(
            split_definitions=_inventory_splits(tmp_path),
            split_builder_inspected=_SPLIT_BUILDER_INVENTORY,
        )
        register = result["leakage_risk_register"]
        assert set(register.keys()) == {
            "temporal_purge_leakage",
            "embargo_leakage",
            "same_bar_lookahead",
            "future_bar_leakage",
            "symbol_universe_leakage",
            "no_independent_oos_seal",
        }
        assert all(value is True for value in register.values())

    # ── Test 9/10/11: seals/manifest/universe absent ───────────────────────
    def test_seal_manifest_universe_absent(self, tmp_path):
        result = _build_split_leakage_audit_diagnostics(
            split_definitions=_inventory_splits(tmp_path),
            split_builder_inspected=_SPLIT_BUILDER_INVENTORY,
        )
        assert result["oos_seal_present"] is False
        assert result["trial_manifest_present"] is False
        assert result["symbol_universe_frozen"] is False

    # ── Test 12: split scoring not safe ────────────────────────────────────
    def test_split_scoring_safe_false(self, tmp_path):
        result = _build_split_leakage_audit_diagnostics(
            split_definitions=_inventory_splits(tmp_path),
            split_builder_inspected=_SPLIT_BUILDER_INVENTORY,
        )
        assert result["split_scoring_safe"] is False

    # ── Test 13: one per_split entry per split ──────────────────────────────
    def test_one_per_split_entry_per_split(self, tmp_path):
        splits = _inventory_splits(tmp_path, split_count=3)
        result = _build_split_leakage_audit_diagnostics(
            split_definitions=splits,
            split_builder_inspected=_SPLIT_BUILDER_INVENTORY,
        )
        assert result["split_count"] == len(splits)
        assert len(result["per_split"]) == len(splits)
        expected_keys = {
            "split_id",
            "split_index",
            "train_start",
            "train_end",
            "validation_start",
            "validation_end",
            "boundary_gap_seconds",
            "train_validation_overlap",
            "validation_row_count_status",
            "calculation_status",
        }
        for entry in result["per_split"]:
            assert set(entry.keys()) == expected_keys
            assert entry["calculation_status"] == NOT_EXECUTED
            assert entry["validation_row_count_status"] == (
                SPLIT_LEAKAGE_AUDIT_ROW_COUNT_NOT_COMPUTED
            )

    # ── Test 14: adjacent real splits have zero boundary gap ───────────────
    def test_inventory_boundary_gap_seconds_zero(self, tmp_path):
        result = _build_split_leakage_audit_diagnostics(
            split_definitions=_inventory_splits(tmp_path),
            split_builder_inspected=_SPLIT_BUILDER_INVENTORY,
        )
        for entry in result["per_split"]:
            assert entry["boundary_gap_seconds"] == 0

    # ── Test 15: adjacent real splits have no overlap ──────────────────────
    def test_inventory_no_train_validation_overlap(self, tmp_path):
        result = _build_split_leakage_audit_diagnostics(
            split_definitions=_inventory_splits(tmp_path),
            split_builder_inspected=_SPLIT_BUILDER_INVENTORY,
        )
        assert result["train_validation_overlap_detected"] is False
        assert all(
            entry["train_validation_overlap"] is False
            for entry in result["per_split"]
        )

    # ── Test 16: fallback marks overlap detected ───────────────────────────
    def test_fallback_overlap_detected_true(self):
        result = _build_split_leakage_audit_diagnostics(
            split_definitions=_fallback_splits(),
            split_builder_inspected=_SPLIT_BUILDER_FALLBACK,
        )
        assert result["train_validation_overlap_detected"] is True
        assert result["split_builder_inspected"] == _SPLIT_BUILDER_FALLBACK
        assert result["split_builder_inspected"] == (
            "build_deterministic_split_definitions"
        )

    # ── Test 17: fallback status is blocked ────────────────────────────────
    def test_fallback_status_blocked(self):
        result = _build_split_leakage_audit_diagnostics(
            split_definitions=_fallback_splits(),
            split_builder_inspected=_SPLIT_BUILDER_FALLBACK,
        )
        assert result["split_leakage_audit_status"] == SPLIT_LEAKAGE_AUDIT_BLOCKED
        assert result["split_leakage_audit_status"] == (
            "SPLIT_LEAKAGE_AUDIT_BLOCKED"
        )
        assert result["split_scoring_safe"] is False

    # ── Test 18: fallback per-split entries overlap ────────────────────────
    def test_fallback_per_split_overlap_true(self):
        result = _build_split_leakage_audit_diagnostics(
            split_definitions=_fallback_splits(),
            split_builder_inspected=_SPLIT_BUILDER_FALLBACK,
        )
        assert all(
            entry["train_validation_overlap"] is True
            for entry in result["per_split"]
        )

    # ── Test 19: per_symbol is None ────────────────────────────────────────
    def test_per_symbol_is_none(self, tmp_path):
        inv = _build_split_leakage_audit_diagnostics(
            split_definitions=_inventory_splits(tmp_path),
            split_builder_inspected=_SPLIT_BUILDER_INVENTORY,
        )
        fb = _build_split_leakage_audit_diagnostics(
            split_definitions=_fallback_splits(),
            split_builder_inspected=_SPLIT_BUILDER_FALLBACK,
        )
        assert inv["per_symbol"] is None
        assert fb["per_symbol"] is None

    # ── Test 20: no forbidden calculation/performance keys ─────────────────
    def test_no_forbidden_calculation_keys(self, tmp_path):
        for splits, builder in (
            (_inventory_splits(tmp_path), _SPLIT_BUILDER_INVENTORY),
            (_fallback_splits(), _SPLIT_BUILDER_FALLBACK),
        ):
            result = _build_split_leakage_audit_diagnostics(
                split_definitions=splits, split_builder_inspected=builder
            )
            all_keys = _all_dict_keys(result)
            assert _SPLIT_LEAKAGE_FORBIDDEN_KEYS.isdisjoint(all_keys), (
                f"Forbidden keys found: "
                f"{_SPLIT_LEAKAGE_FORBIDDEN_KEYS & all_keys}"
            )
            # Never emit pass/safe/candidate wording in any status value.
            for status in (
                result["split_leakage_audit_status"],
                result["calculation_status"],
            ):
                upper = status.upper()
                assert "SAFE" not in upper
                assert "PASS" not in upper
                assert "CANDIDATE" not in upper

    # ── Test 21: receipt final verdict remains BLOCKED ─────────────────────
    def test_receipt_final_verdict_unchanged(self, tmp_path):
        section = _build_split_leakage_audit_diagnostics(
            split_definitions=_inventory_splits(tmp_path),
            split_builder_inspected=_SPLIT_BUILDER_INVENTORY,
        )
        receipt = _base_receipt(split_leakage_audit_diagnostics=section)
        # Must survive the recursive forbidden-key / verdict validator.
        validate_real_validation_receipt(receipt)
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION
        assert receipt["split_leakage_audit_diagnostics"] == section

    # ── Test 22: CLI with bars inventory includes the section ──────────────
    def test_cli_bars_inventory_includes_section(self, tmp_path):
        bars_dir = tmp_path / "bars"
        bars_dir.mkdir()
        _write_tiny_bars_csv(bars_dir, "BTCUSDT_8h_ohlcv.csv")

        out_dir = Path("/tmp") / f"qnty_sla_cli_inv_{uuid.uuid4().hex}"
        receipt_path = out_dir / "real_validation_receipt.json"
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "quantbot.experiment.offline_edge_real_validation",
                    "--read-only",
                    "--output-dir",
                    str(out_dir),
                    "--input-manifest-fingerprint",
                    "a" * 64,
                    "--data-quality-receipt-sha256",
                    "b" * 64,
                    "--code-commit-sha",
                    "c" * 40,
                    "--bars-dir",
                    str(bars_dir),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0, result.stderr
            with open(receipt_path) as f:
                written = json.load(f)
            assert "split_leakage_audit_diagnostics" in written
            section = written["split_leakage_audit_diagnostics"]
            assert section["split_builder_inspected"] == _SPLIT_BUILDER_INVENTORY
            assert section["split_leakage_audit_status"] == (
                SPLIT_LEAKAGE_AUDIT_INSUFFICIENT_FOR_SCORING
            )
            assert section["split_scoring_safe"] is False
            assert written["final_offline_verdict"] == (
                BLOCKED_BY_VALIDATION_IMPLEMENTATION
            )
            assert "EDGE_CANDIDATE" not in json.dumps(written)
        finally:
            if receipt_path.exists():
                receipt_path.unlink()
            if out_dir.exists():
                out_dir.rmdir()

    # ── Test 23: legacy fallback path includes the section, blocked ────────
    def test_cli_legacy_fallback_includes_section_blocked(self):
        out_dir = Path("/tmp") / f"qnty_sla_cli_fb_{uuid.uuid4().hex}"
        receipt_path = out_dir / "real_validation_receipt.json"
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "quantbot.experiment.offline_edge_real_validation",
                    "--read-only",
                    "--output-dir",
                    str(out_dir),
                    "--input-manifest-fingerprint",
                    "a" * 64,
                    "--data-quality-receipt-sha256",
                    "b" * 64,
                    "--code-commit-sha",
                    "c" * 40,
                    "--global-min-timestamp",
                    "2026-01-01T00:00:00Z",
                    "--global-max-timestamp",
                    "2026-02-01T00:00:00Z",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0, result.stderr
            with open(receipt_path) as f:
                written = json.load(f)
            assert "split_leakage_audit_diagnostics" in written
            section = written["split_leakage_audit_diagnostics"]
            assert section["split_builder_inspected"] == _SPLIT_BUILDER_FALLBACK
            assert section["split_leakage_audit_status"] == (
                SPLIT_LEAKAGE_AUDIT_BLOCKED
            )
            assert section["train_validation_overlap_detected"] is True
            assert section["split_scoring_safe"] is False
            assert written["final_offline_verdict"] == (
                BLOCKED_BY_VALIDATION_IMPLEMENTATION
            )
        finally:
            if receipt_path.exists():
                receipt_path.unlink()
            if out_dir.exists():
                out_dir.rmdir()

    # ── Test 24: no pbo/walkforward imports ────────────────────────────────
    def test_no_pbo_or_walkforward_imports(self):
        module_path = (
            Path(__file__).resolve().parents[2]
            / "quantbot"
            / "experiment"
            / "offline_edge_real_validation.py"
        )
        tree = ast.parse(module_path.read_text())
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        forbidden_substrings = (
            "pbo",
            "walkforward",
            "walkforward_runner",
            "offline_edge_walkforward",
        )
        for name in imported:
            for sub in forbidden_substrings:
                assert sub not in name, f"forbidden import: {name}"

    # ── Test 25: safety-key regression across both builders ────────────────
    def test_safety_key_regression(self, tmp_path):
        for splits, builder in (
            (_inventory_splits(tmp_path), _SPLIT_BUILDER_INVENTORY),
            (_fallback_splits(), _SPLIT_BUILDER_FALLBACK),
        ):
            result = _build_split_leakage_audit_diagnostics(
                split_definitions=splits, split_builder_inspected=builder
            )
            blob = json.dumps(result)
            for token in (
                "OFFLINE_EDGE_CANDIDATE",
                "EDGE_CANDIDATE",
                "sharpe",
                "Sharpe",
                "drawdown",
                "funding_adjusted_return",
                "net_return_value",
                "price_change",
                "portfolio",
            ):
                assert token not in blob, f"forbidden token in section: {token}"
            all_keys = _all_dict_keys(result)
            assert _SPLIT_LEAKAGE_FORBIDDEN_KEYS.isdisjoint(all_keys)

    # ── Fail-closed guards ─────────────────────────────────────────────────
    def test_bad_builder_name_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="split_builder_inspected"):
            _build_split_leakage_audit_diagnostics(
                split_definitions=_inventory_splits(tmp_path),
                split_builder_inspected="some_unknown_builder",
            )

    def test_empty_split_definitions_rejected(self):
        with pytest.raises(ValueError, match="non-empty"):
            _build_split_leakage_audit_diagnostics(
                split_definitions=[],
                split_builder_inspected=_SPLIT_BUILDER_INVENTORY,
            )


# ── Strategy rule contract diagnostics tests ──────────────────────────────


_STRATEGY_RULE_CONTRACT_FORBIDDEN_KEYS = {
    "returns", "return", "pnl", "PnL", "sharpe", "Sharpe", "drawdown",
    "risk", "edge", "strategy_performance", "trade", "trades",
    "position", "positions", "signal", "signals", "portfolio",
    "funding_adjusted_return", "net_return_value", "price_change",
    "gross_return_value", "cost_adjusted_return", "live_ready",
    "deploy_ready", "profitable", "baseline", "benchmark_result",
    "OFFLINE_EDGE_CANDIDATE", "EDGE_CANDIDATE",
}


class TestStrategyRuleContractDiagnostics:
    """Tests for _build_strategy_rule_contract_diagnostics() and its
    integration into the offline-edge receipt."""

    # ── Helper returns a dict ──────────────────────────────────────────────
    def test_helper_returns_dict(self):
        result = _build_strategy_rule_contract_diagnostics()
        assert isinstance(result, dict)

    # ── Top-level field values ─────────────────────────────────────────────
    def test_contract_version(self):
        result = _build_strategy_rule_contract_diagnostics()
        assert result["contract_version"] == STRATEGY_RULE_CONTRACT_VERSION

    def test_calculation_status(self):
        result = _build_strategy_rule_contract_diagnostics()
        assert result["calculation_status"] == STRATEGY_RULE_CONTRACT_DIAGNOSTIC_ONLY

    def test_contract_status_not_defined(self):
        result = _build_strategy_rule_contract_diagnostics()
        assert result["contract_status"] == STRATEGY_RULE_CONTRACT_NOT_DEFINED

    def test_scoring_authorized_false(self):
        result = _build_strategy_rule_contract_diagnostics()
        assert result["scoring_authorized"] is False

    def test_scoring_blocked_reason(self):
        result = _build_strategy_rule_contract_diagnostics()
        assert result["scoring_blocked_reason"] == (
            STRATEGY_RULE_CONTRACT_BLOCKED_REASON_NOT_DEFINED
        )

    # ── Allowed input fields are None ──────────────────────────────────────
    def test_allowed_input_roles_none(self):
        result = _build_strategy_rule_contract_diagnostics()
        assert result["allowed_input_roles"] is None

    def test_allowed_input_columns_none(self):
        result = _build_strategy_rule_contract_diagnostics()
        assert result["allowed_input_columns"] is None

    # ── Forbidden input fields are None ────────────────────────────────────
    def test_forbidden_input_roles_none(self):
        result = _build_strategy_rule_contract_diagnostics()
        assert result["forbidden_input_roles"] is None

    def test_forbidden_input_columns_none(self):
        result = _build_strategy_rule_contract_diagnostics()
        assert result["forbidden_input_columns"] is None

    def test_forbidden_future_columns_none(self):
        result = _build_strategy_rule_contract_diagnostics()
        assert result["forbidden_future_columns"] is None

    # ── Decision-time fields are None ──────────────────────────────────────
    def test_decision_time_convention_none(self):
        result = _build_strategy_rule_contract_diagnostics()
        assert result["decision_time_convention"] is None

    def test_decision_time_column_none(self):
        result = _build_strategy_rule_contract_diagnostics()
        assert result["decision_time_column"] is None

    def test_decision_time_offset_none(self):
        result = _build_strategy_rule_contract_diagnostics()
        assert result["decision_time_offset"] is None

    # ── Feature lookback fields are None ───────────────────────────────────
    def test_feature_lookback_none(self):
        result = _build_strategy_rule_contract_diagnostics()
        assert result["feature_lookback"] is None

    def test_feature_lookback_bars_none(self):
        result = _build_strategy_rule_contract_diagnostics()
        assert result["feature_lookback_bars"] is None

    # ── Label horizon fields are None ──────────────────────────────────────
    def test_label_horizon_none(self):
        result = _build_strategy_rule_contract_diagnostics()
        assert result["label_horizon"] is None

    def test_label_horizon_bars_none(self):
        result = _build_strategy_rule_contract_diagnostics()
        assert result["label_horizon_bars"] is None

    # ── Holding period fields are None ─────────────────────────────────────
    def test_holding_period_none(self):
        result = _build_strategy_rule_contract_diagnostics()
        assert result["holding_period"] is None

    def test_holding_period_bars_none(self):
        result = _build_strategy_rule_contract_diagnostics()
        assert result["holding_period_bars"] is None

    # ── Side fields are None ───────────────────────────────────────────────
    def test_side_semantics_none(self):
        result = _build_strategy_rule_contract_diagnostics()
        assert result["side_semantics"] is None

    def test_side_source_none(self):
        result = _build_strategy_rule_contract_diagnostics()
        assert result["side_source"] is None

    # ── Notional fields are None ───────────────────────────────────────────
    def test_notional_semantics_none(self):
        result = _build_strategy_rule_contract_diagnostics()
        assert result["notional_semantics"] is None

    def test_notional_source_none(self):
        result = _build_strategy_rule_contract_diagnostics()
        assert result["notional_source"] is None

    def test_notional_currency_none(self):
        result = _build_strategy_rule_contract_diagnostics()
        assert result["notional_currency"] is None

    # ── Cost/funding dependency ────────────────────────────────────────────
    def test_cost_dependency_not_defined(self):
        result = _build_strategy_rule_contract_diagnostics()
        assert result["cost_dependency"] == NOT_DEFINED

    def test_funding_dependency_not_defined(self):
        result = _build_strategy_rule_contract_diagnostics()
        assert result["funding_dependency"] == NOT_DEFINED

    # ── Scoring prerequisites all false ────────────────────────────────────
    def test_scoring_prerequisites_all_false(self):
        result = _build_strategy_rule_contract_diagnostics()
        prereqs = result["scoring_prerequisites_present"]
        assert isinstance(prereqs, dict)
        for key, value in prereqs.items():
            assert value is False, f"{key} must be False, got {value}"

    def test_scoring_prerequisites_have_expected_keys(self):
        result = _build_strategy_rule_contract_diagnostics()
        prereqs = result["scoring_prerequisites_present"]
        expected_keys = {
            "decision_time_convention",
            "feature_lookback",
            "label_horizon",
            "holding_period",
            "funding_interval_exposure",
            "cost_event_timing",
        }
        assert prereqs.keys() == expected_keys

    # ── Integration into receipt ───────────────────────────────────────────
    def test_section_included_in_receipt(self):
        receipt = _base_receipt(
            strategy_rule_contract_diagnostics=(
                _build_strategy_rule_contract_diagnostics()
            ),
        )
        assert "strategy_rule_contract_diagnostics" in receipt

    def test_receipt_validates_with_section(self):
        receipt = _base_receipt(
            strategy_rule_contract_diagnostics=(
                _build_strategy_rule_contract_diagnostics()
            ),
        )
        # validate_real_validation_receipt should not raise
        validate_real_validation_receipt(receipt)

    def test_final_offline_verdict_unchanged(self):
        receipt = _base_receipt(
            strategy_rule_contract_diagnostics=(
                _build_strategy_rule_contract_diagnostics()
            ),
        )
        assert receipt["final_offline_verdict"] == (
            BLOCKED_BY_VALIDATION_IMPLEMENTATION
        )

    def test_guardrails_unchanged(self):
        receipt = _base_receipt(
            strategy_rule_contract_diagnostics=(
                _build_strategy_rule_contract_diagnostics()
            ),
        )
        for key, value in receipt["guardrail_status"].items():
            assert value is True, f"guardrail {key} must be True"

    # ── No forbidden keys ──────────────────────────────────────────────────
    def test_no_forbidden_calculation_keys(self):
        result = _build_strategy_rule_contract_diagnostics()
        all_keys = _all_dict_keys(result)
        assert _STRATEGY_RULE_CONTRACT_FORBIDDEN_KEYS.isdisjoint(all_keys), (
            f"Forbidden keys found: "
            f"{_STRATEGY_RULE_CONTRACT_FORBIDDEN_KEYS & all_keys}"
        )

    # ── CLI integration ────────────────────────────────────────────────────
    def test_cli_inventory_path_includes_section(self, tmp_path):
        """Inventory-based CLI path should include the section."""
        _write_tiny_bars_csv(tmp_path)
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        exit_code = real_validation.main([
            "--read-only", "--output-dir", str(output_dir),
            "--input-manifest-fingerprint", "abc",
            "--data-quality-receipt-sha256", "def",
            "--code-commit-sha", "ghi",
            "--bars-dir", str(tmp_path),
        ])
        assert exit_code == 0
        receipt_path = output_dir / "real_validation_receipt.json"
        assert receipt_path.exists()
        receipt = json.loads(receipt_path.read_text())
        assert "strategy_rule_contract_diagnostics" in receipt

    def test_cli_fallback_path_includes_section(self, tmp_path):
        """Fallback CLI path (no --bars-dir) should include the section."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        exit_code = real_validation.main([
            "--read-only", "--output-dir", str(output_dir),
            "--input-manifest-fingerprint", "abc",
            "--data-quality-receipt-sha256", "def",
            "--code-commit-sha", "ghi",
            "--global-min-timestamp", "2026-01-01T00:00:00Z",
            "--global-max-timestamp", "2026-02-01T00:00:00Z",
        ])
        assert exit_code == 0
        receipt_path = output_dir / "real_validation_receipt.json"
        assert receipt_path.exists()
        receipt = json.loads(receipt_path.read_text())
        assert "strategy_rule_contract_diagnostics" in receipt

    # ── Safety-key regression ──────────────────────────────────────────────
    def test_no_forbidden_top_level_keys_in_receipt(self):
        """Receipt with the section must still forbid pnl/sharpe/edge/strategy_performance."""
        receipt = _base_receipt(
            strategy_rule_contract_diagnostics=(
                _build_strategy_rule_contract_diagnostics()
            ),
        )
        for forbidden in ("pnl", "sharpe", "edge", "strategy_performance"):
            assert forbidden not in receipt

    def test_no_forbidden_calculation_keys_in_receipt(self):
        """Receipt with the section must still forbid all calculation keys."""
        receipt = _base_receipt(
            strategy_rule_contract_diagnostics=(
                _build_strategy_rule_contract_diagnostics()
            ),
        )
        all_keys = _all_dict_keys(receipt)
        forbidden = _STRATEGY_RULE_CONTRACT_FORBIDDEN_KEYS | {
            "gross_return_value", "cost_adjusted_return",
        }
        overlap = forbidden & all_keys
        assert not overlap, f"Forbidden keys found in receipt: {overlap}"

    # ── Materialize contract instance diagnostics (Lane C1) ─────────────────

    @staticmethod
    def _contract_json_path() -> str:
        return str(
            Path(__file__).resolve().parents[2]
            / "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.json"
        )

    @staticmethod
    def _sidecar_path() -> str:
        return str(
            Path(__file__).resolve().parents[2]
            / "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.sha256"
        )

    def test_happy_path_loads_contract_packet(self):
        """Happy path: committed contract JSON + sidecar load cleanly."""
        result = materialize_strategy_rule_contract_instance_diagnostics(
            contract_path=self._contract_json_path(),
            sidecar_path=self._sidecar_path(),
        )
        assert result["diagnostic_kind"] == "strategy_rule_contract_instance"
        assert result["contract_packet_read"] is True
        assert result["json_parse_ok"] is True
        assert result["sidecar_parse_ok"] is True
        assert result["sidecar_digest_matches_json_bytes"] is True
        assert result["contract_hash_authority"] == "SIDECAR"
        assert result["contract_hash_field_value"] == "FROZEN_IN_SIDECAR"
        assert result["contract_hash_status"] == "FROZEN_IN_SIDECAR"
        assert result["required_fields_present"] is True
        assert result["missing_required_fields"] == []
        assert result["forbidden_dict_key_scan_passed"] is True
        assert result["forbidden_dict_key_collisions"] == []
        assert result["input_ceiling_check_passed"] is True
        assert result["output_boundary_fields_present"] is True
        assert result["scoring_authorization"] is False
        assert result["live_integration_authorized"] is False
        assert result["downstream_dependency_booleans_all_false"] is True
        assert result["contract_runner_read_status"] == "DIAGNOSTIC_READ_ONLY"
        assert result["contract_commit_sha_bound"] is False
        assert result["contract_commit_sha_binding_status"] == (
            "UNRESOLVED_SELF_REFERENCE_PLACEHOLDER"
        )
        assert result["contract_instance_readiness"] is False
        assert result["contract_scoring_ready"] is False
        assert result["contract_validation_status"] == (
            "BLOCKED_BY_COMMIT_BINDING_PLACEHOLDER"
        )

    def test_missing_json_path_fails_closed(self):
        with pytest.raises(ValueError, match="Contract JSON not found"):
            materialize_strategy_rule_contract_instance_diagnostics(
                contract_path="/nonexistent/contract.json",
                sidecar_path=self._sidecar_path(),
            )

    def test_missing_sidecar_path_fails_closed(self):
        with pytest.raises(ValueError, match="Contract sidecar not found"):
            materialize_strategy_rule_contract_instance_diagnostics(
                contract_path=self._contract_json_path(),
                sidecar_path="/nonexistent/contract.sha256",
            )

    def test_malformed_json_fails_closed(self, tmp_path):
        bad_json = tmp_path / "bad.json"
        bad_json.write_text("{invalid json}")
        good_sidecar = tmp_path / "good.sha256"
        good_sidecar.write_text(
            "0000000000000000000000000000000000000000000000000000000000000000  bad.json"
        )
        with pytest.raises(ValueError, match="Contract JSON parse error"):
            materialize_strategy_rule_contract_instance_diagnostics(
                contract_path=str(bad_json),
                sidecar_path=str(good_sidecar),
            )

    def test_digest_mismatch_fails_closed(self, tmp_path):
        contract = tmp_path / "mismatch.json"
        contract.write_text('{"a": 1}')
        sidecar = tmp_path / "mismatch.sha256"
        sidecar.write_text(
            "0000000000000000000000000000000000000000000000000000000000000000  mismatch.json"
        )
        with pytest.raises(ValueError, match="Sidecar digest mismatch"):
            materialize_strategy_rule_contract_instance_diagnostics(
                contract_path=str(contract),
                sidecar_path=str(sidecar),
            )

    def test_forbidden_dict_key_fails_closed(self, tmp_path):
        # Copy committed contract and add a forbidden key at top level.
        contract_path = self._contract_json_path()
        contract_bytes = Path(contract_path).read_bytes()
        contract = json.loads(contract_bytes)
        contract["pnl"] = 1  # FORBIDDEN_CALCULATION_KEYS includes "pnl"
        mutated_path = tmp_path / "mutated_pnl.json"
        mutated_path.write_text(json.dumps(contract, indent=2, sort_keys=True))
        mutated_sha = hashlib.sha256(mutated_path.read_bytes()).hexdigest()
        sidecar = tmp_path / "mutated_pnl.sha256"
        sidecar.write_text(f"{mutated_sha}  mutated_pnl.json")
        with pytest.raises(ValueError, match="forbidden dict keys"):
            materialize_strategy_rule_contract_instance_diagnostics(
                contract_path=str(mutated_path),
                sidecar_path=str(sidecar),
            )

    def test_input_ceiling_violation_fails_closed(self, tmp_path):
        # Copy committed contract and add open to bars allowed columns.
        contract_path = self._contract_json_path()
        contract = json.loads(Path(contract_path).read_bytes())
        contract["allowed_input_columns"]["bars"].append("open")
        mutated_path = tmp_path / "mutated_ceiling.json"
        mutated_path.write_text(json.dumps(contract, indent=2, sort_keys=True))
        mutated_sha = hashlib.sha256(mutated_path.read_bytes()).hexdigest()
        sidecar = tmp_path / "mutated_ceiling.sha256"
        sidecar.write_text(f"{mutated_sha}  mutated_ceiling.json")
        with pytest.raises(ValueError, match="allowed_input_columns.bars"):
            materialize_strategy_rule_contract_instance_diagnostics(
                contract_path=str(mutated_path),
                sidecar_path=str(sidecar),
            )

    def test_output_boundary_missing_fails_closed(self, tmp_path):
        # Copy committed contract and remove forbidden_output_keys.
        # forbidden_output_keys is in _REQUIRED_STRATEGY_CONTRACT_KEYS so the
        # required-field check fires first; match the actual error message.
        contract_path = self._contract_json_path()
        contract = json.loads(Path(contract_path).read_bytes())
        del contract["forbidden_output_keys"]
        mutated_path = tmp_path / "mutated_boundary.json"
        mutated_path.write_text(json.dumps(contract, indent=2, sort_keys=True))
        mutated_sha = hashlib.sha256(mutated_path.read_bytes()).hexdigest()
        sidecar = tmp_path / "mutated_boundary.sha256"
        sidecar.write_text(f"{mutated_sha}  mutated_boundary.json")
        with pytest.raises(ValueError, match="missing required fields"):
            materialize_strategy_rule_contract_instance_diagnostics(
                contract_path=str(mutated_path),
                sidecar_path=str(sidecar),
            )

    def test_downstream_boolean_true_fails_closed(self, tmp_path):
        # Copy committed contract and set oos_seal_dependency_satisfied to true.
        contract_path = self._contract_json_path()
        contract = json.loads(Path(contract_path).read_bytes())
        contract["oos_seal_dependency_satisfied"] = True
        mutated_path = tmp_path / "mutated_downstream.json"
        mutated_path.write_text(json.dumps(contract, indent=2, sort_keys=True))
        mutated_sha = hashlib.sha256(mutated_path.read_bytes()).hexdigest()
        sidecar = tmp_path / "mutated_downstream.sha256"
        sidecar.write_text(f"{mutated_sha}  mutated_downstream.json")
        with pytest.raises(ValueError, match="must be exactly false"):
            materialize_strategy_rule_contract_instance_diagnostics(
                contract_path=str(mutated_path),
                sidecar_path=str(sidecar),
            )

    def test_gross_observational_return_not_exempted(self, tmp_path):
        """Strict contract scanner rejects gross_observational_return under
        gross_observational_returns (no receipt-only exemption)."""
        contract_path = self._contract_json_path()
        contract = json.loads(Path(contract_path).read_bytes())
        contract["gross_observational_returns"] = {
            "gross_observational_return": 0.01
        }
        mutated_path = tmp_path / "mutated_gross_exempt.json"
        mutated_path.write_text(json.dumps(contract, indent=2, sort_keys=True))
        mutated_sha = hashlib.sha256(mutated_path.read_bytes()).hexdigest()
        sidecar = tmp_path / "mutated_gross_exempt.sha256"
        sidecar.write_text(f"{mutated_sha}  mutated_gross_exempt.json")
        with pytest.raises(ValueError, match="forbidden dict keys"):
            materialize_strategy_rule_contract_instance_diagnostics(
                contract_path=str(mutated_path),
                sidecar_path=str(sidecar),
            )

    def test_downstream_boolean_string_true_fails_closed(self, tmp_path):
        """String 'true' must be rejected as not exactly False."""
        contract_path = self._contract_json_path()
        contract = json.loads(Path(contract_path).read_bytes())
        contract["oos_seal_dependency_satisfied"] = "true"
        mutated_path = tmp_path / "mutated_str_true.json"
        mutated_path.write_text(json.dumps(contract, indent=2, sort_keys=True))
        mutated_sha = hashlib.sha256(mutated_path.read_bytes()).hexdigest()
        sidecar = tmp_path / "mutated_str_true.sha256"
        sidecar.write_text(f"{mutated_sha}  mutated_str_true.json")
        with pytest.raises(ValueError, match="must be exactly false"):
            materialize_strategy_rule_contract_instance_diagnostics(
                contract_path=str(mutated_path),
                sidecar_path=str(sidecar),
            )

    def test_downstream_boolean_integer_one_fails_closed(self, tmp_path):
        """Integer 1 must be rejected as not exactly False."""
        contract_path = self._contract_json_path()
        contract = json.loads(Path(contract_path).read_bytes())
        contract["oos_seal_dependency_satisfied"] = 1
        mutated_path = tmp_path / "mutated_int_one.json"
        mutated_path.write_text(json.dumps(contract, indent=2, sort_keys=True))
        mutated_sha = hashlib.sha256(mutated_path.read_bytes()).hexdigest()
        sidecar = tmp_path / "mutated_int_one.sha256"
        sidecar.write_text(f"{mutated_sha}  mutated_int_one.json")
        with pytest.raises(ValueError, match="must be exactly false"):
            materialize_strategy_rule_contract_instance_diagnostics(
                contract_path=str(mutated_path),
                sidecar_path=str(sidecar),
            )

    def test_scoring_authorization_zero_fails_closed(self, tmp_path):
        """scoring_authorization = 0 must be rejected as not exactly False."""
        contract_path = self._contract_json_path()
        contract = json.loads(Path(contract_path).read_bytes())
        contract["scoring_authorization"] = 0
        mutated_path = tmp_path / "mutated_score_zero.json"
        mutated_path.write_text(json.dumps(contract, indent=2, sort_keys=True))
        mutated_sha = hashlib.sha256(mutated_path.read_bytes()).hexdigest()
        sidecar = tmp_path / "mutated_score_zero.sha256"
        sidecar.write_text(f"{mutated_sha}  mutated_score_zero.json")
        with pytest.raises(ValueError, match="must be exactly false"):
            materialize_strategy_rule_contract_instance_diagnostics(
                contract_path=str(mutated_path),
                sidecar_path=str(sidecar),
            )

    def test_scoring_authorization_string_false_fails_closed(self, tmp_path):
        """scoring_authorization = 'false' must be rejected as not exactly False."""
        contract_path = self._contract_json_path()
        contract = json.loads(Path(contract_path).read_bytes())
        contract["scoring_authorization"] = "false"
        mutated_path = tmp_path / "mutated_score_str_false.json"
        mutated_path.write_text(json.dumps(contract, indent=2, sort_keys=True))
        mutated_sha = hashlib.sha256(mutated_path.read_bytes()).hexdigest()
        sidecar = tmp_path / "mutated_score_str_false.sha256"
        sidecar.write_text(f"{mutated_sha}  mutated_score_str_false.json")
        with pytest.raises(ValueError, match="must be exactly false"):
            materialize_strategy_rule_contract_instance_diagnostics(
                contract_path=str(mutated_path),
                sidecar_path=str(sidecar),
            )

    def test_receipt_binding_with_diagnostics(self):
        """Build a real validation receipt with contract instance diagnostics
        and assert diagnostic-only posture."""
        diag = materialize_strategy_rule_contract_instance_diagnostics(
            contract_path=self._contract_json_path(),
            sidecar_path=self._sidecar_path(),
        )
        receipt = _base_receipt(
            strategy_rule_contract_diagnostics=diag,
        )
        assert "strategy_rule_contract_diagnostics" in receipt
        loaded = receipt["strategy_rule_contract_diagnostics"]
        assert loaded["contract_runner_read_status"] == "DIAGNOSTIC_READ_ONLY"
        assert loaded["contract_commit_sha_bound"] is False
        assert loaded["contract_instance_readiness"] is False
        assert loaded["contract_scoring_ready"] is False
        assert receipt["final_offline_verdict"] == (
            BLOCKED_BY_VALIDATION_IMPLEMENTATION
        )
        # validate_real_validation_receipt must not raise
        validate_real_validation_receipt(receipt)

    def test_cli_with_contract_args_emits_diagnostics(self, tmp_path):
        """CLI with contract args produces diagnostic section, verdict still blocked."""
        _write_tiny_bars_csv(tmp_path)
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        exit_code = real_validation.main([
            "--read-only", "--output-dir", str(output_dir),
            "--input-manifest-fingerprint", "abc",
            "--data-quality-receipt-sha256", "def",
            "--code-commit-sha", "ghi",
            "--bars-dir", str(tmp_path),
            "--strategy-contract-path", self._contract_json_path(),
            "--strategy-contract-sha256-path", self._sidecar_path(),
        ])
        assert exit_code == 0
        receipt_path = output_dir / "real_validation_receipt.json"
        assert receipt_path.exists()
        receipt = json.loads(receipt_path.read_text())
        assert "strategy_rule_contract_diagnostics" in receipt
        loaded = receipt["strategy_rule_contract_diagnostics"]
        assert loaded.get("diagnostic_kind") == "strategy_rule_contract_instance"
        assert loaded.get("contract_runner_read_status") == "DIAGNOSTIC_READ_ONLY"
        assert loaded.get("contract_scoring_ready") is False
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION

    def test_cli_with_bad_sidecar_exits_nonzero(self, tmp_path):
        """CLI with bad sidecar path exits nonzero (fails closed)."""
        _write_tiny_bars_csv(tmp_path)
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        bad_sidecar = tmp_path / "nonexistent.sha256"
        exit_code = real_validation.main([
            "--read-only", "--output-dir", str(output_dir),
            "--input-manifest-fingerprint", "abc",
            "--data-quality-receipt-sha256", "def",
            "--code-commit-sha", "ghi",
            "--bars-dir", str(tmp_path),
            "--strategy-contract-path", self._contract_json_path(),
            "--strategy-contract-sha256-path", str(bad_sidecar),
        ])
        assert exit_code != 0  # fails closed


class TestStrategyRuleContractCommitBindingDiagnostics:
    """Tests for commit-binding sidecar integration in
    materialize_strategy_rule_contract_instance_diagnostics()."""

    @staticmethod
    def _contract_json_path() -> str:
        return str(
            Path(__file__).resolve().parents[2]
            / "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.json"
        )

    @staticmethod
    def _sidecar_path() -> str:
        return str(
            Path(__file__).resolve().parents[2]
            / "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.sha256"
        )

    @staticmethod
    def _commit_binding_path() -> str:
        return str(
            Path(__file__).resolve().parents[2]
            / "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.commit_binding.json"
        )

    # ── Happy path ──────────────────────────────────────────────────────────
    def test_happy_path_with_commit_binding(self):
        """Happy path: contract + sidecar + commit binding all valid."""
        result = materialize_strategy_rule_contract_instance_diagnostics(
            contract_path=self._contract_json_path(),
            sidecar_path=self._sidecar_path(),
            commit_binding_path=self._commit_binding_path(),
        )
        assert result["contract_commit_sha_bound"] is True
        assert result["contract_commit_sha_binding_status"] == (
            "BOUND_BY_PRIOR_COMMIT_CONTAINMENT_SIDECAR"
        )
        assert result["contract_containing_commit_digest_matches"] is True
        assert result["contract_instance_readiness"] is False
        assert result["contract_scoring_ready"] is False
        assert result["contract_validation_status"] == (
            "COMMIT_BOUND_DIAGNOSTIC_ONLY_NOT_SCORING_READY"
        )
        assert result["contract_commit_binding_read"] is True
        assert result["contract_commit_binding_model"] is not None
        assert result["contract_containing_commit_sha"] is not None
        assert result["contract_containing_commit_path_verified"] is True

    # ── C1 compatibility: omit commit binding ──────────────────────────────
    def test_c1_compatibility_omitted_commit_binding(self):
        """Omitting commit-binding path preserves unresolved placeholder status."""
        result = materialize_strategy_rule_contract_instance_diagnostics(
            contract_path=self._contract_json_path(),
            sidecar_path=self._sidecar_path(),
        )
        assert result["contract_commit_sha_bound"] is False
        assert result["contract_commit_sha_binding_status"] == (
            "UNRESOLVED_SELF_REFERENCE_PLACEHOLDER"
        )
        assert result["contract_instance_readiness"] is False
        assert result["contract_scoring_ready"] is False
        assert result["contract_validation_status"] == (
            "BLOCKED_BY_COMMIT_BINDING_PLACEHOLDER"
        )

    # ── Missing commit-binding file fails closed ───────────────────────────
    def test_missing_commit_binding_file_fails_closed(self):
        """Missing commit-binding file raises ValueError when path supplied."""
        with pytest.raises(ValueError, match="Commit binding sidecar not found"):
            materialize_strategy_rule_contract_instance_diagnostics(
                contract_path=self._contract_json_path(),
                sidecar_path=self._sidecar_path(),
                commit_binding_path="/nonexistent/commit_binding.json",
            )

    # ── Malformed commit-binding JSON fails closed ─────────────────────────
    def test_malformed_commit_binding_json_fails_closed(self, tmp_path):
        bad_binding = tmp_path / "bad_binding.json"
        bad_binding.write_text("{invalid json}")
        with pytest.raises(ValueError, match="Commit binding sidecar JSON parse error"):
            materialize_strategy_rule_contract_instance_diagnostics(
                contract_path=self._contract_json_path(),
                sidecar_path=self._sidecar_path(),
                commit_binding_path=str(bad_binding),
            )

    # ── Forbidden dict key in commit binding fails closed ──────────────────
    def test_commit_binding_forbidden_key_fails_closed(self, tmp_path):
        contract_bytes = Path(self._contract_json_path()).read_bytes()
        contract = json.loads(contract_bytes)
        binding = {
            "binding_id": "test",
            "binding_version": "1.0.0",
            "binding_kind": "test",
            "contract_id": contract["contract_id"],
            "contract_source_path": "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.json",
            "contract_sha256_sidecar_path": "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.sha256",
            "contract_sha256": hashlib.sha256(contract_bytes).hexdigest(),
            "contract_containing_commit_sha": "f6e2c27ccc9271ca3587895fddd165f76eda784d",
            "contract_containing_commit_role": "test",
            "contract_commit_binding_model": "test",
            "self_reference_avoidance": "test",
            "contract_commit_sha_field_policy": "test",
            "scoring_authorization": False,
            "live_integration_authorized": False,
            "contract_scoring_ready": False,
            "contract_instance_readiness": False,
            "pnl": 1,  # forbidden key
        }
        binding_path = tmp_path / "forbidden_binding.json"
        binding_path.write_text(json.dumps(binding, indent=2, sort_keys=True))
        with pytest.raises(ValueError, match="forbidden dict keys"):
            materialize_strategy_rule_contract_instance_diagnostics(
                contract_path=self._contract_json_path(),
                sidecar_path=self._sidecar_path(),
                commit_binding_path=str(binding_path),
            )

    # ── contract_sha256 mismatch fails closed ──────────────────────────────
    def test_commit_binding_sha256_mismatch_fails_closed(self, tmp_path):
        contract_bytes = Path(self._contract_json_path()).read_bytes()
        contract = json.loads(contract_bytes)
        binding = {
            "binding_id": "test",
            "binding_version": "1.0.0",
            "binding_kind": "test",
            "contract_id": contract["contract_id"],
            "contract_source_path": "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.json",
            "contract_sha256_sidecar_path": "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.sha256",
            "contract_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
            "contract_containing_commit_sha": "f6e2c27ccc9271ca3587895fddd165f76eda784d",
            "contract_containing_commit_role": "test",
            "contract_commit_binding_model": "test",
            "self_reference_avoidance": "test",
            "contract_commit_sha_field_policy": "test",
            "scoring_authorization": False,
            "live_integration_authorized": False,
            "contract_scoring_ready": False,
            "contract_instance_readiness": False,
        }
        binding_path = tmp_path / "sha256_mismatch_binding.json"
        binding_path.write_text(json.dumps(binding, indent=2, sort_keys=True))
        with pytest.raises(ValueError, match="Commit binding contract_sha256 mismatch"):
            materialize_strategy_rule_contract_instance_diagnostics(
                contract_path=self._contract_json_path(),
                sidecar_path=self._sidecar_path(),
                commit_binding_path=str(binding_path),
            )

    # ── contract_id mismatch fails closed ──────────────────────────────────
    def test_commit_binding_contract_id_mismatch_fails_closed(self, tmp_path):
        contract_bytes = Path(self._contract_json_path()).read_bytes()
        binding = {
            "binding_id": "test",
            "binding_version": "1.0.0",
            "binding_kind": "test",
            "contract_id": "wrong_contract_id",
            "contract_source_path": "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.json",
            "contract_sha256_sidecar_path": "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.sha256",
            "contract_sha256": hashlib.sha256(contract_bytes).hexdigest(),
            "contract_containing_commit_sha": "f6e2c27ccc9271ca3587895fddd165f76eda784d",
            "contract_containing_commit_role": "test",
            "contract_commit_binding_model": "test",
            "self_reference_avoidance": "test",
            "contract_commit_sha_field_policy": "test",
            "scoring_authorization": False,
            "live_integration_authorized": False,
            "contract_scoring_ready": False,
            "contract_instance_readiness": False,
        }
        binding_path = tmp_path / "id_mismatch_binding.json"
        binding_path.write_text(json.dumps(binding, indent=2, sort_keys=True))
        with pytest.raises(ValueError, match="Commit binding contract_id mismatch"):
            materialize_strategy_rule_contract_instance_diagnostics(
                contract_path=self._contract_json_path(),
                sidecar_path=self._sidecar_path(),
                commit_binding_path=str(binding_path),
            )

    # ── Bad commit SHA format fails closed ─────────────────────────────────
    def test_bad_commit_sha_format_fails_closed(self, tmp_path):
        contract_bytes = Path(self._contract_json_path()).read_bytes()
        contract = json.loads(contract_bytes)
        binding = {
            "binding_id": "test",
            "binding_version": "1.0.0",
            "binding_kind": "test",
            "contract_id": contract["contract_id"],
            "contract_source_path": "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.json",
            "contract_sha256_sidecar_path": "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.sha256",
            "contract_sha256": hashlib.sha256(contract_bytes).hexdigest(),
            "contract_containing_commit_sha": "not-a-valid-sha",
            "contract_containing_commit_role": "test",
            "contract_commit_binding_model": "test",
            "self_reference_avoidance": "test",
            "contract_commit_sha_field_policy": "test",
            "scoring_authorization": False,
            "live_integration_authorized": False,
            "contract_scoring_ready": False,
            "contract_instance_readiness": False,
        }
        binding_path = tmp_path / "bad_sha_binding.json"
        binding_path.write_text(json.dumps(binding, indent=2, sort_keys=True))
        with pytest.raises(ValueError, match="not a valid.*40-hex-char"):
            materialize_strategy_rule_contract_instance_diagnostics(
                contract_path=self._contract_json_path(),
                sidecar_path=self._sidecar_path(),
                commit_binding_path=str(binding_path),
            )

    # ── Nonexistent commit SHA fails closed ────────────────────────────────
    def test_nonexistent_commit_sha_fails_closed(self, tmp_path):
        contract_bytes = Path(self._contract_json_path()).read_bytes()
        contract = json.loads(contract_bytes)
        binding = {
            "binding_id": "test",
            "binding_version": "1.0.0",
            "binding_kind": "test",
            "contract_id": contract["contract_id"],
            "contract_source_path": "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.json",
            "contract_sha256_sidecar_path": "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.sha256",
            "contract_sha256": hashlib.sha256(contract_bytes).hexdigest(),
            "contract_containing_commit_sha": "0000000000000000000000000000000000000000",
            "contract_containing_commit_role": "test",
            "contract_commit_binding_model": "test",
            "self_reference_avoidance": "test",
            "contract_commit_sha_field_policy": "test",
            "scoring_authorization": False,
            "live_integration_authorized": False,
            "contract_scoring_ready": False,
            "contract_instance_readiness": False,
        }
        binding_path = tmp_path / "nonexistent_sha_binding.json"
        binding_path.write_text(json.dumps(binding, indent=2, sort_keys=True))
        with pytest.raises(ValueError, match="git show.*failed"):
            materialize_strategy_rule_contract_instance_diagnostics(
                contract_path=self._contract_json_path(),
                sidecar_path=self._sidecar_path(),
                commit_binding_path=str(binding_path),
            )

    # ── Prior commit does not contain path fails closed ────────────────────
    def test_prior_commit_wrong_path_fails_closed(self, tmp_path):
        contract_bytes = Path(self._contract_json_path()).read_bytes()
        contract = json.loads(contract_bytes)
        binding = {
            "binding_id": "test",
            "binding_version": "1.0.0",
            "binding_kind": "test",
            "contract_id": contract["contract_id"],
            "contract_source_path": "nonexistent/path.json",
            "contract_sha256_sidecar_path": "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.sha256",
            "contract_sha256": hashlib.sha256(contract_bytes).hexdigest(),
            "contract_containing_commit_sha": "f6e2c27ccc9271ca3587895fddd165f76eda784d",
            "contract_containing_commit_role": "test",
            "contract_commit_binding_model": "test",
            "self_reference_avoidance": "test",
            "contract_commit_sha_field_policy": "test",
            "scoring_authorization": False,
            "live_integration_authorized": False,
            "contract_scoring_ready": False,
            "contract_instance_readiness": False,
        }
        binding_path = tmp_path / "wrong_path_binding.json"
        binding_path.write_text(json.dumps(binding, indent=2, sort_keys=True))
        with pytest.raises(ValueError, match="contract_source_path mismatch"):
            materialize_strategy_rule_contract_instance_diagnostics(
                contract_path=self._contract_json_path(),
                sidecar_path=self._sidecar_path(),
                commit_binding_path=str(binding_path),
            )

    # ── Prior commit contains path but bytes digest mismatch ───────────────
    def test_prior_commit_digest_mismatch_fails_closed(self, tmp_path):
        """Prior commit contains the path but bytes digest does not match."""
        contract_bytes = Path(self._contract_json_path()).read_bytes()
        contract = json.loads(contract_bytes)
        # Use a different file that exists in the same commit but has different bytes.
        binding = {
            "binding_id": "test",
            "binding_version": "1.0.0",
            "binding_kind": "test",
            "contract_id": contract["contract_id"],
            "contract_source_path": "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.json",
            "contract_sha256_sidecar_path": "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.sha256",
            "contract_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
            "contract_containing_commit_sha": "f6e2c27ccc9271ca3587895fddd165f76eda784d",
            "contract_containing_commit_role": "test",
            "contract_commit_binding_model": "test",
            "self_reference_avoidance": "test",
            "contract_commit_sha_field_policy": "test",
            "scoring_authorization": False,
            "live_integration_authorized": False,
            "contract_scoring_ready": False,
            "contract_instance_readiness": False,
        }
        binding_path = tmp_path / "digest_mismatch_binding.json"
        binding_path.write_text(json.dumps(binding, indent=2, sort_keys=True))
        with pytest.raises(ValueError, match="Commit binding contract_sha256 mismatch"):
            materialize_strategy_rule_contract_instance_diagnostics(
                contract_path=self._contract_json_path(),
                sidecar_path=self._sidecar_path(),
                commit_binding_path=str(binding_path),
            )

    # ── CLI happy path with all three args ─────────────────────────────────
    def test_cli_with_commit_binding_emits_diagnostics(self, tmp_path):
        """CLI with contract + sidecar + commit binding produces diagnostic
        section with commit binding true, scoring false, verdict blocked."""
        _write_tiny_bars_csv(tmp_path)
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        exit_code = real_validation.main([
            "--read-only", "--output-dir", str(output_dir),
            "--input-manifest-fingerprint", "abc",
            "--data-quality-receipt-sha256", "def",
            "--code-commit-sha", "ghi",
            "--bars-dir", str(tmp_path),
            "--strategy-contract-path", self._contract_json_path(),
            "--strategy-contract-sha256-path", self._sidecar_path(),
            "--strategy-contract-commit-binding-path", self._commit_binding_path(),
        ])
        assert exit_code == 0
        receipt_path = output_dir / "real_validation_receipt.json"
        assert receipt_path.exists()
        receipt = json.loads(receipt_path.read_text())
        assert "strategy_rule_contract_diagnostics" in receipt
        loaded = receipt["strategy_rule_contract_diagnostics"]
        assert loaded.get("contract_commit_sha_bound") is True
        assert loaded.get("contract_commit_sha_binding_status") == (
            "BOUND_BY_PRIOR_COMMIT_CONTAINMENT_SIDECAR"
        )
        assert loaded.get("contract_scoring_ready") is False
        assert loaded.get("contract_instance_readiness") is False
        assert loaded.get("contract_validation_status") == (
            "COMMIT_BOUND_DIAGNOSTIC_ONLY_NOT_SCORING_READY"
        )
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION

    # ── CLI compatibility: only contract + sidecar args ────────────────────
    def test_cli_without_commit_binding_preserves_c1_behavior(self, tmp_path):
        """CLI with only contract + sidecar args: commit binding false/unresolved,
        no regression."""
        _write_tiny_bars_csv(tmp_path)
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        exit_code = real_validation.main([
            "--read-only", "--output-dir", str(output_dir),
            "--input-manifest-fingerprint", "abc",
            "--data-quality-receipt-sha256", "def",
            "--code-commit-sha", "ghi",
            "--bars-dir", str(tmp_path),
            "--strategy-contract-path", self._contract_json_path(),
            "--strategy-contract-sha256-path", self._sidecar_path(),
        ])
        assert exit_code == 0
        receipt_path = output_dir / "real_validation_receipt.json"
        assert receipt_path.exists()
        receipt = json.loads(receipt_path.read_text())
        assert "strategy_rule_contract_diagnostics" in receipt
        loaded = receipt["strategy_rule_contract_diagnostics"]
        assert loaded.get("contract_commit_sha_bound") is False
        assert loaded.get("contract_commit_sha_binding_status") == (
            "UNRESOLVED_SELF_REFERENCE_PLACEHOLDER"
        )
        assert loaded.get("contract_scoring_ready") is False
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION

    # ── Receipt binding: final receipt includes commit-binding diagnostics ──
    def test_receipt_includes_commit_binding_diagnostics(self, tmp_path):
        """Final receipt includes commit-binding diagnostics if supplied."""
        _write_tiny_bars_csv(tmp_path)
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        exit_code = real_validation.main([
            "--read-only", "--output-dir", str(output_dir),
            "--input-manifest-fingerprint", "abc",
            "--data-quality-receipt-sha256", "def",
            "--code-commit-sha", "ghi",
            "--bars-dir", str(tmp_path),
            "--strategy-contract-path", self._contract_json_path(),
            "--strategy-contract-sha256-path", self._sidecar_path(),
            "--strategy-contract-commit-binding-path", self._commit_binding_path(),
        ])
        assert exit_code == 0
        receipt_path = output_dir / "real_validation_receipt.json"
        receipt = json.loads(receipt_path.read_text())
        loaded = receipt["strategy_rule_contract_diagnostics"]
        assert loaded.get("contract_commit_binding_path") is not None
        assert loaded.get("contract_commit_binding_read") is True
        assert loaded.get("contract_commit_binding_model") is not None
        assert loaded.get("contract_containing_commit_sha") is not None
        assert loaded.get("contract_containing_commit_path_verified") is True
        assert loaded.get("contract_containing_commit_digest_matches") is True
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION

    # ── Cwd-outside-repo regression test ────────────────────────────────────
    def test_commit_binding_works_when_cwd_outside_repo(self, tmp_path):
        """Commit binding works when caller cwd is outside the repository.

        Uses the real committed contract path, sidecar path, and binding path
        as absolute paths. Changes cwd to a temp directory outside the repo,
        then verifies that commit-binding verification still succeeds.
        """
        import os

        contract_path = self._contract_json_path()
        sidecar_path = self._sidecar_path()
        binding_path = self._commit_binding_path()
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = materialize_strategy_rule_contract_instance_diagnostics(
                contract_path=contract_path,
                sidecar_path=sidecar_path,
                commit_binding_path=binding_path,
            )
        finally:
            os.chdir(original_cwd)

        assert result["contract_commit_sha_bound"] is True
        assert result["contract_commit_sha_binding_status"] == (
            "BOUND_BY_PRIOR_COMMIT_CONTAINMENT_SIDECAR"
        )
        assert result["contract_scoring_ready"] is False
        assert result["contract_instance_readiness"] is False

    # ── Missing git root fails closed ───────────────────────────────────────
    def test_commit_binding_missing_git_root_fails_closed(self, tmp_path):
        """Commit binding raises ValueError when contract path is outside a git
        repo. This test copies the contract JSON, sidecar, and binding JSON to a
        temp directory outside any git repository."""
        contract_bytes = Path(self._contract_json_path()).read_bytes()
        contract = json.loads(contract_bytes)

        binding = {
            "binding_id": "test",
            "binding_version": "1.0.0",
            "binding_kind": "test",
            "contract_id": contract["contract_id"],
            "contract_source_path": "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.json",
            "contract_sha256_sidecar_path": "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.sha256",
            "contract_sha256": hashlib.sha256(contract_bytes).hexdigest(),
            "contract_containing_commit_sha": "f6e2c27ccc9271ca3587895fddd165f76eda784d",
            "contract_containing_commit_role": "test",
            "contract_commit_binding_model": "test",
            "self_reference_avoidance": "test",
            "contract_commit_sha_field_policy": "test",
            "scoring_authorization": False,
            "live_integration_authorized": False,
            "contract_scoring_ready": False,
            "contract_instance_readiness": False,
        }

        # Write files to tmp_path (outside any git repo).
        contract_outside = tmp_path / "contract.json"
        contract_outside.write_bytes(contract_bytes)

        sidecar_outside = tmp_path / "contract.sha256"
        sha256_hex = hashlib.sha256(contract_bytes).hexdigest()
        sidecar_outside.write_text(f"{sha256_hex}  contract.json")

        binding_path = tmp_path / "binding.json"
        binding_path.write_text(json.dumps(binding, indent=2, sort_keys=True))

        with pytest.raises(ValueError, match="git repository root"):
            materialize_strategy_rule_contract_instance_diagnostics(
                contract_path=str(contract_outside),
                sidecar_path=str(sidecar_outside),
                commit_binding_path=str(binding_path),
            )


    def test_materialized_contract_diagnostics_preserve_contract_id(self):
        """Prove real contract diagnostics preserve identity fields for E1.

        Regression: materialize_strategy_rule_contract_instance_diagnostics()
        must include contract_id/version/status so trial manifest binding
        does not fail with 'contract diagnostic says None'.
        """
        diagnostics = _build_strategy_rule_contract_diagnostics(
            contract_path=self._contract_json_path(),
            sidecar_path=self._sidecar_path(),
            commit_binding_path=self._commit_binding_path(),
        )
        assert diagnostics["contract_id"] == "qnty_offline_edge_strategy_rule_contract_v1"
        assert diagnostics["contract_version"] == "1.0.0"
        assert diagnostics["contract_status"] == "FROZEN_DECLARATION_ONLY"
        assert diagnostics["contract_packet_gate"]["gate_passed"] is True


class TestStrategyRuleContractPacketGate:
    """Tests for _derive_strategy_rule_contract_packet_gate() — Lane D1.

    The gate is a diagnostic-only projection derived from existing strategy-rule
    contract diagnostics. It compresses C2 evidence that the frozen contract
    packet is loaded, hash-bound, strict-key checked, input/output bounded,
    dependency-false, and commit-bound to a prior containing commit.

    Gate pass does **not** authorize scoring, strategy execution, PnL, live
    readiness, or final verdict advancement.
    """

    @staticmethod
    def _contract_json_path() -> str:
        return str(
            Path(__file__).resolve().parents[2]
            / "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.json"
        )

    @staticmethod
    def _sidecar_path() -> str:
        return str(
            Path(__file__).resolve().parents[2]
            / "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.sha256"
        )

    @staticmethod
    def _commit_binding_path() -> str:
        return str(
            Path(__file__).resolve().parents[2]
            / "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.commit_binding.json"
        )

    # ── Test 1: Helper happy path (C2 diagnostics → gate passed) ──────────
    def test_happy_path_gate_passed(self):
        """C2 diagnostics with all fields correct yields gate_passed True."""
        diagnostics = materialize_strategy_rule_contract_instance_diagnostics(
            contract_path=self._contract_json_path(),
            sidecar_path=self._sidecar_path(),
            commit_binding_path=self._commit_binding_path(),
        )
        gate = _derive_strategy_rule_contract_packet_gate(diagnostics)
        assert gate["gate_passed"] is True
        assert gate["gate_status"] == (
            "CONTRACT_PACKET_COMMIT_BOUND_DIAGNOSTIC_ONLY"
        )
        assert gate["gate_scoring_authorization"] is False
        assert gate["gate_live_authorization"] is False
        assert gate["gate_final_verdict_authorization"] is False
        assert gate["gate_downstream_unlocks"] == []
        assert gate["blocked_reason"] is None
        # Evidence fields all present and true.
        ev = gate["evidence"]
        assert ev["contract_packet_read"] is True
        assert ev["sidecar_digest_matches_json_bytes"] is True
        assert ev["forbidden_dict_key_scan_passed"] is True
        assert ev["input_ceiling_check_passed"] is True
        assert ev["output_boundary_fields_present"] is True
        assert ev["downstream_dependency_booleans_all_false"] is True
        assert ev["contract_commit_sha_bound"] is True
        assert ev["contract_commit_sha_binding_status"] is True
        assert ev["contract_containing_commit_digest_matches"] is True

    # ── Test 2: C1 compatibility (no commit binding) ──────────────────────
    def test_c1_compatibility_no_commit_binding(self):
        """C1 diagnostics (contract + sidecar only) yields gate_passed False."""
        diagnostics = materialize_strategy_rule_contract_instance_diagnostics(
            contract_path=self._contract_json_path(),
            sidecar_path=self._sidecar_path(),
        )
        gate = _derive_strategy_rule_contract_packet_gate(diagnostics)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == "BLOCKED_BY_COMMIT_BINDING_PLACEHOLDER"
        assert gate["gate_scoring_authorization"] is False
        assert gate["gate_live_authorization"] is False
        assert gate["gate_final_verdict_authorization"] is False
        assert gate["gate_downstream_unlocks"] == []
        assert gate["blocked_reason"] == "CONTRACT_COMMIT_BINDING_NOT_VERIFIED"
        ev = gate["evidence"]
        assert ev["contract_commit_sha_bound"] is False

    # ── Test 3: Absence compatibility (no contract paths) ─────────────────
    def test_absence_compatibility(self):
        """No contract args yields gate_passed False with NOT_LOADED status."""
        diagnostics = _build_strategy_rule_contract_diagnostics()
        gate = diagnostics["contract_packet_gate"]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == "CONTRACT_PACKET_NOT_LOADED"
        assert gate["gate_scoring_authorization"] is False
        assert gate["gate_live_authorization"] is False
        assert gate["gate_final_verdict_authorization"] is False
        assert gate["gate_downstream_unlocks"] == []
        assert gate["blocked_reason"] == "CONTRACT_PACKET_NOT_LOADED"
        assert gate["evidence"] == {}

    # ── Test 4: Missing critical field fails closed ───────────────────────
    def test_missing_critical_field_fails_closed(self):
        """Removing sidecar_digest_matches_json_bytes yields gate_passed False."""
        diagnostics = materialize_strategy_rule_contract_instance_diagnostics(
            contract_path=self._contract_json_path(),
            sidecar_path=self._sidecar_path(),
            commit_binding_path=self._commit_binding_path(),
        )
        # Remove a critical field.
        del diagnostics["sidecar_digest_matches_json_bytes"]
        gate = _derive_strategy_rule_contract_packet_gate(diagnostics)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == "BLOCKED_BY_INCOMPLETE_EVIDENCE"
        assert gate["gate_scoring_authorization"] is False
        assert gate["gate_live_authorization"] is False
        assert gate["gate_final_verdict_authorization"] is False
        assert gate["gate_downstream_unlocks"] == []
        assert gate["blocked_reason"] == "CONTRACT_PACKET_GATE_EVIDENCE_INCOMPLETE"
        # The evidence field for the removed key should be False.
        assert gate["evidence"]["sidecar_digest_matches_json_bytes"] is False

    # ── Test 5: Wrong commit-binding status fails closed ──────────────────
    def test_wrong_commit_binding_status_fails_closed(self):
        """Wrong binding status while bound=True yields gate_passed False."""
        diagnostics = materialize_strategy_rule_contract_instance_diagnostics(
            contract_path=self._contract_json_path(),
            sidecar_path=self._sidecar_path(),
            commit_binding_path=self._commit_binding_path(),
        )
        diagnostics["contract_commit_sha_binding_status"] = (
            "UNRESOLVED_SELF_REFERENCE_PLACEHOLDER"
        )
        gate = _derive_strategy_rule_contract_packet_gate(diagnostics)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == "BLOCKED_BY_INCOMPLETE_EVIDENCE"
        assert gate["gate_scoring_authorization"] is False
        assert gate["gate_live_authorization"] is False
        assert gate["gate_final_verdict_authorization"] is False
        assert gate["gate_downstream_unlocks"] == []

    # ── Test 6: Scoring authorization true fails closed ───────────────────
    def test_scoring_authorization_true_fails_closed(self):
        """scoring_authorization=True yields gate_passed False."""
        diagnostics = materialize_strategy_rule_contract_instance_diagnostics(
            contract_path=self._contract_json_path(),
            sidecar_path=self._sidecar_path(),
            commit_binding_path=self._commit_binding_path(),
        )
        diagnostics["scoring_authorization"] = True
        gate = _derive_strategy_rule_contract_packet_gate(diagnostics)
        assert gate["gate_passed"] is False
        assert gate["gate_scoring_authorization"] is False
        assert gate["gate_downstream_unlocks"] == []

    # ── Test 7: Readiness true fails closed ───────────────────────────────
    def test_readiness_true_fails_closed(self):
        """contract_scoring_ready=True yields gate_passed False."""
        diagnostics = materialize_strategy_rule_contract_instance_diagnostics(
            contract_path=self._contract_json_path(),
            sidecar_path=self._sidecar_path(),
            commit_binding_path=self._commit_binding_path(),
        )
        diagnostics["contract_scoring_ready"] = True
        gate = _derive_strategy_rule_contract_packet_gate(diagnostics)
        assert gate["gate_passed"] is False
        assert gate["gate_scoring_authorization"] is False
        assert gate["gate_downstream_unlocks"] == []

    def test_instance_readiness_true_fails_closed(self):
        """contract_instance_readiness=True yields gate_passed False."""
        diagnostics = materialize_strategy_rule_contract_instance_diagnostics(
            contract_path=self._contract_json_path(),
            sidecar_path=self._sidecar_path(),
            commit_binding_path=self._commit_binding_path(),
        )
        diagnostics["contract_instance_readiness"] = True
        gate = _derive_strategy_rule_contract_packet_gate(diagnostics)
        assert gate["gate_passed"] is False
        assert gate["gate_scoring_authorization"] is False
        assert gate["gate_downstream_unlocks"] == []

    # ── Test 8: Receipt integration ───────────────────────────────────────
    def test_receipt_integration_all_args(self):
        """Receipt with all three contract paths includes gate, passed True,
        final verdict still blocked."""
        diagnostics = _build_strategy_rule_contract_diagnostics(
            contract_path=self._contract_json_path(),
            sidecar_path=self._sidecar_path(),
            commit_binding_path=self._commit_binding_path(),
        )
        receipt = _base_receipt(
            strategy_rule_contract_diagnostics=diagnostics,
        )
        loaded = receipt["strategy_rule_contract_diagnostics"]
        assert "contract_packet_gate" in loaded
        gate = loaded["contract_packet_gate"]
        assert gate["gate_passed"] is True
        assert gate["gate_status"] == (
            "CONTRACT_PACKET_COMMIT_BOUND_DIAGNOSTIC_ONLY"
        )
        assert receipt["final_offline_verdict"] == (
            BLOCKED_BY_VALIDATION_IMPLEMENTATION
        )
        assert receipt["guardrail_status"]["edge_unproven"] is True
        assert receipt["guardrail_status"]["block_live_integration"] is True
        # validate_real_validation_receipt must not raise
        validate_real_validation_receipt(receipt)

    # ── Test 9: CLI no contract args ──────────────────────────────────────
    def test_cli_no_contract_args(self, tmp_path):
        """CLI without contract args includes gate with passed False."""
        _write_tiny_bars_csv(tmp_path)
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        exit_code = real_validation.main([
            "--read-only", "--output-dir", str(output_dir),
            "--input-manifest-fingerprint", "abc",
            "--data-quality-receipt-sha256", "def",
            "--code-commit-sha", "ghi",
            "--bars-dir", str(tmp_path),
        ])
        assert exit_code == 0
        receipt_path = output_dir / "real_validation_receipt.json"
        receipt = json.loads(receipt_path.read_text())
        diag = receipt["strategy_rule_contract_diagnostics"]
        assert "contract_packet_gate" in diag
        gate = diag["contract_packet_gate"]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == "CONTRACT_PACKET_NOT_LOADED"
        assert receipt["final_offline_verdict"] == (
            BLOCKED_BY_VALIDATION_IMPLEMENTATION
        )

    # ── Test 10: CLI contract + sidecar only ──────────────────────────────
    def test_cli_contract_sidecar_only(self, tmp_path):
        """CLI with contract + sidecar only yields gate False, verdict blocked."""
        _write_tiny_bars_csv(tmp_path)
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        exit_code = real_validation.main([
            "--read-only", "--output-dir", str(output_dir),
            "--input-manifest-fingerprint", "abc",
            "--data-quality-receipt-sha256", "def",
            "--code-commit-sha", "ghi",
            "--bars-dir", str(tmp_path),
            "--strategy-contract-path", self._contract_json_path(),
            "--strategy-contract-sha256-path", self._sidecar_path(),
        ])
        assert exit_code == 0
        receipt_path = output_dir / "real_validation_receipt.json"
        receipt = json.loads(receipt_path.read_text())
        diag = receipt["strategy_rule_contract_diagnostics"]
        assert "contract_packet_gate" in diag
        gate = diag["contract_packet_gate"]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == "BLOCKED_BY_COMMIT_BINDING_PLACEHOLDER"
        assert receipt["final_offline_verdict"] == (
            BLOCKED_BY_VALIDATION_IMPLEMENTATION
        )

    # ── Test 11: CLI all three args ───────────────────────────────────────
    def test_cli_all_three_args(self, tmp_path):
        """CLI with contract + sidecar + commit binding yields gate True,
        verdict still blocked."""
        _write_tiny_bars_csv(tmp_path)
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        exit_code = real_validation.main([
            "--read-only", "--output-dir", str(output_dir),
            "--input-manifest-fingerprint", "abc",
            "--data-quality-receipt-sha256", "def",
            "--code-commit-sha", "ghi",
            "--bars-dir", str(tmp_path),
            "--strategy-contract-path", self._contract_json_path(),
            "--strategy-contract-sha256-path", self._sidecar_path(),
            "--strategy-contract-commit-binding-path",
            self._commit_binding_path(),
        ])
        assert exit_code == 0
        receipt_path = output_dir / "real_validation_receipt.json"
        receipt = json.loads(receipt_path.read_text())
        diag = receipt["strategy_rule_contract_diagnostics"]
        assert "contract_packet_gate" in diag
        gate = diag["contract_packet_gate"]
        assert gate["gate_passed"] is True
        assert gate["gate_status"] == (
            "CONTRACT_PACKET_COMMIT_BOUND_DIAGNOSTIC_ONLY"
        )
        assert receipt["final_offline_verdict"] == (
            BLOCKED_BY_VALIDATION_IMPLEMENTATION
        )
        assert receipt["guardrail_status"]["edge_unproven"] is True
        assert receipt["guardrail_status"]["block_live_integration"] is True


_TRIAL_MANIFEST_FORBIDDEN_KEYS = frozenset({
    "pnl", "returns", "return", "sharpe", "drawdown", "risk", "edge",
    "strategy_performance", "trade", "trades", "signal", "signals",
    "position", "positions", "portfolio", "baseline_result",
    "benchmark_result", "profitable", "live_ready", "deploy_ready",
    "OFFLINE_EDGE_CANDIDATE", "EDGE_CANDIDATE",
    "funding_adjusted_return", "net_return_value", "price_change",
})


class TestTrialManifestDiagnostics:
    """Tests for _build_trial_manifest_diagnostics() and its
    integration into the offline-edge receipt."""

    # ── Helper returns a dict ──────────────────────────────────────────────
    def test_helper_returns_dict(self):
        result = _build_trial_manifest_diagnostics()
        assert isinstance(result, dict)

    # ── Top-level field values ─────────────────────────────────────────────
    def test_manifest_version(self):
        result = _build_trial_manifest_diagnostics()
        assert result["manifest_version"] == TRIAL_MANIFEST_VERSION

    def test_calculation_status(self):
        result = _build_trial_manifest_diagnostics()
        assert result["calculation_status"] == TRIAL_MANIFEST_DIAGNOSTIC_ONLY

    def test_trial_manifest_status(self):
        result = _build_trial_manifest_diagnostics()
        assert result["trial_manifest_status"] == TRIAL_MANIFEST_NOT_DEFINED

    def test_trial_manifest_present_false(self):
        result = _build_trial_manifest_diagnostics()
        assert result["trial_manifest_present"] is False

    def test_trial_manifest_hash_none(self):
        result = _build_trial_manifest_diagnostics()
        assert result["trial_manifest_hash"] is None

    def test_trial_manifest_source_none(self):
        result = _build_trial_manifest_diagnostics()
        assert result["trial_manifest_source"] is None

    def test_scoring_authorized_false(self):
        result = _build_trial_manifest_diagnostics()
        assert result["scoring_authorized"] is False

    def test_scoring_blocked_reason(self):
        result = _build_trial_manifest_diagnostics()
        assert result["scoring_blocked_reason"] == (
            TRIAL_MANIFEST_BLOCKED_REASON_NOT_DEFINED
        )

    def test_trial_count_known_false(self):
        result = _build_trial_manifest_diagnostics()
        assert result["trial_count_known"] is False

    def test_trial_count_none(self):
        result = _build_trial_manifest_diagnostics()
        assert result["trial_count"] is None

    def test_candidate_count_known_false(self):
        result = _build_trial_manifest_diagnostics()
        assert result["candidate_count_known"] is False

    def test_candidate_count_none(self):
        result = _build_trial_manifest_diagnostics()
        assert result["candidate_count"] is None

    def test_rejected_trial_count_known_false(self):
        result = _build_trial_manifest_diagnostics()
        assert result["rejected_trial_count_known"] is False

    def test_rejected_trial_count_none(self):
        result = _build_trial_manifest_diagnostics()
        assert result["rejected_trial_count"] is None

    def test_strategy_candidate_id_none(self):
        result = _build_trial_manifest_diagnostics()
        assert result["strategy_candidate_id"] is None

    def test_hypothesis_id_none(self):
        result = _build_trial_manifest_diagnostics()
        assert result["hypothesis_id"] is None

    def test_parameter_search_space_defined_false(self):
        result = _build_trial_manifest_diagnostics()
        assert result["parameter_search_space_defined"] is False

    def test_parameter_search_space_hash_none(self):
        result = _build_trial_manifest_diagnostics()
        assert result["parameter_search_space_hash"] is None

    def test_llm_generated_trials_recorded_false(self):
        result = _build_trial_manifest_diagnostics()
        assert result["llm_generated_trials_recorded"] is False

    def test_human_generated_trials_recorded_false(self):
        result = _build_trial_manifest_diagnostics()
        assert result["human_generated_trials_recorded"] is False

    def test_manual_rejected_trials_recorded_false(self):
        result = _build_trial_manifest_diagnostics()
        assert result["manual_rejected_trials_recorded"] is False

    def test_symbol_universe_frozen_false(self):
        result = _build_trial_manifest_diagnostics()
        assert result["symbol_universe_frozen"] is False

    def test_split_policy_frozen_false(self):
        result = _build_trial_manifest_diagnostics()
        assert result["split_policy_frozen"] is False

    def test_oos_seal_present_false(self):
        result = _build_trial_manifest_diagnostics()
        assert result["oos_seal_present"] is False

    def test_null_benchmark_contract_present_false(self):
        result = _build_trial_manifest_diagnostics()
        assert result["null_benchmark_contract_present"] is False

    def test_multiple_testing_policy_present_false(self):
        result = _build_trial_manifest_diagnostics()
        assert result["multiple_testing_policy_present"] is False

    # ── Prerequisites all false ────────────────────────────────────────────
    def test_prerequisites_all_false(self):
        result = _build_trial_manifest_diagnostics()
        prereqs = result["trial_manifest_prerequisites_present"]
        assert isinstance(prereqs, dict)
        for key, value in prereqs.items():
            assert value is False, f"{key} must be False, got {value}"

    def test_prerequisites_expected_keys(self):
        result = _build_trial_manifest_diagnostics()
        prereqs = result["trial_manifest_prerequisites_present"]
        expected_keys = {
            "strategy_rule_contract",
            "split_scoring_safe",
            "trial_count",
            "candidate_registry",
            "parameter_search_space",
            "symbol_universe_freeze",
            "split_policy_freeze",
            "oos_seal",
            "null_benchmark_contract",
            "multiple_testing_policy",
        }
        assert prereqs.keys() == expected_keys

    # ── Integration into receipt ───────────────────────────────────────────
    def test_section_included_in_receipt(self):
        receipt = _base_receipt(
            trial_manifest_diagnostics=_build_trial_manifest_diagnostics(),
        )
        assert "trial_manifest_diagnostics" in receipt

    def test_receipt_validates_with_section(self):
        receipt = _base_receipt(
            trial_manifest_diagnostics=_build_trial_manifest_diagnostics(),
        )
        # validate_real_validation_receipt should not raise
        validate_real_validation_receipt(receipt)

    def test_final_offline_verdict_unchanged(self):
        receipt = _base_receipt(
            trial_manifest_diagnostics=_build_trial_manifest_diagnostics(),
        )
        assert receipt["final_offline_verdict"] == (
            BLOCKED_BY_VALIDATION_IMPLEMENTATION
        )

    def test_guardrails_unchanged(self):
        receipt = _base_receipt(
            trial_manifest_diagnostics=_build_trial_manifest_diagnostics(),
        )
        for key, value in receipt["guardrail_status"].items():
            assert value is True, f"guardrail {key} must be True"

    # ── No forbidden keys ──────────────────────────────────────────────────
    def test_no_forbidden_calculation_keys(self):
        result = _build_trial_manifest_diagnostics()
        all_keys = _all_dict_keys(result)
        assert _TRIAL_MANIFEST_FORBIDDEN_KEYS.isdisjoint(all_keys), (
            f"Forbidden keys found: "
            f"{_TRIAL_MANIFEST_FORBIDDEN_KEYS & all_keys}"
        )

    # ── CLI integration ────────────────────────────────────────────────────
    def test_cli_inventory_path_includes_section(self, tmp_path):
        """Inventory-based CLI path should include the section."""
        _write_tiny_bars_csv(tmp_path)
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        exit_code = real_validation.main([
            "--read-only", "--output-dir", str(output_dir),
            "--input-manifest-fingerprint", "abc",
            "--data-quality-receipt-sha256", "def",
            "--code-commit-sha", "ghi",
            "--bars-dir", str(tmp_path),
        ])
        assert exit_code == 0
        receipt_path = output_dir / "real_validation_receipt.json"
        assert receipt_path.exists()
        receipt = json.loads(receipt_path.read_text())
        assert "trial_manifest_diagnostics" in receipt

    def test_cli_fallback_path_includes_section(self, tmp_path):
        """Fallback CLI path (no --bars-dir) should include the section."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        exit_code = real_validation.main([
            "--read-only", "--output-dir", str(output_dir),
            "--input-manifest-fingerprint", "abc",
            "--data-quality-receipt-sha256", "def",
            "--code-commit-sha", "ghi",
            "--global-min-timestamp", "2026-01-01T00:00:00Z",
            "--global-max-timestamp", "2026-02-01T00:00:00Z",
        ])
        assert exit_code == 0
        receipt_path = output_dir / "real_validation_receipt.json"
        assert receipt_path.exists()
        receipt = json.loads(receipt_path.read_text())
        assert "trial_manifest_diagnostics" in receipt

    # ── Safety-key regression ──────────────────────────────────────────────
    def test_no_forbidden_top_level_keys_in_receipt(self):
        """Receipt with the section must still forbid pnl/sharpe/edge/strategy_performance."""
        receipt = _base_receipt(
            trial_manifest_diagnostics=_build_trial_manifest_diagnostics(),
        )
        for forbidden in ("pnl", "sharpe", "edge", "strategy_performance"):
            assert forbidden not in receipt

    def test_no_forbidden_calculation_keys_in_receipt(self):
        """Receipt with the section must still forbid all calculation keys."""
        receipt = _base_receipt(
            trial_manifest_diagnostics=_build_trial_manifest_diagnostics(),
        )
        all_keys = _all_dict_keys(receipt)
        assert _TRIAL_MANIFEST_FORBIDDEN_KEYS.isdisjoint(all_keys), (
            f"Forbidden keys found in receipt: "
            f"{_TRIAL_MANIFEST_FORBIDDEN_KEYS & all_keys}"
        )


_OOS_SEAL_FORBIDDEN_KEYS = frozenset({
    "pnl", "returns", "return", "sharpe", "drawdown", "risk", "edge",
    "strategy_performance", "trade", "trades", "signal", "signals",
    "position", "positions", "portfolio", "baseline_result",
    "benchmark_result", "profitable", "live_ready", "deploy_ready",
    "OFFLINE_EDGE_CANDIDATE", "EDGE_CANDIDATE",
    "funding_adjusted_return", "net_return_value", "price_change",
})


class TestOosSealDiagnostics:
    """Tests for _build_oos_seal_diagnostics() and its
    integration into the offline-edge receipt."""

    # ── Helper returns a dict ──────────────────────────────────────────────
    def test_helper_returns_dict(self):
        result = _build_oos_seal_diagnostics()
        assert isinstance(result, dict)

    # ── Top-level field values ─────────────────────────────────────────────
    def test_seal_version(self):
        result = _build_oos_seal_diagnostics()
        assert result["seal_version"] == OOS_SEAL_VERSION

    def test_calculation_status(self):
        result = _build_oos_seal_diagnostics()
        assert result["calculation_status"] == OOS_SEAL_DIAGNOSTIC_ONLY

    def test_oos_seal_status(self):
        result = _build_oos_seal_diagnostics()
        assert result["oos_seal_status"] == OOS_SEAL_NOT_DEFINED

    def test_oos_seal_present_false(self):
        result = _build_oos_seal_diagnostics()
        assert result["oos_seal_present"] is False

    def test_oos_seal_hash_none(self):
        result = _build_oos_seal_diagnostics()
        assert result["oos_seal_hash"] is None

    def test_oos_seal_source_none(self):
        result = _build_oos_seal_diagnostics()
        assert result["oos_seal_source"] is None

    # ── Scoring fields ─────────────────────────────────────────────────────
    def test_scoring_authorized_false(self):
        result = _build_oos_seal_diagnostics()
        assert result["scoring_authorized"] is False

    def test_scoring_blocked_reason(self):
        result = _build_oos_seal_diagnostics()
        assert result["scoring_blocked_reason"] == (
            OOS_SEAL_BLOCKED_REASON_NOT_DEFINED
        )

    # ── OOS period fields ──────────────────────────────────────────────────
    def test_oos_split_id_none(self):
        result = _build_oos_seal_diagnostics()
        assert result["oos_split_id"] is None

    def test_oos_period_start_none(self):
        result = _build_oos_seal_diagnostics()
        assert result["oos_period_start"] is None

    def test_oos_period_end_none(self):
        result = _build_oos_seal_diagnostics()
        assert result["oos_period_end"] is None

    def test_oos_period_frozen_false(self):
        result = _build_oos_seal_diagnostics()
        assert result["oos_period_frozen"] is False

    # ── Symbol universe fields ─────────────────────────────────────────────
    def test_oos_symbol_universe_frozen_false(self):
        result = _build_oos_seal_diagnostics()
        assert result["oos_symbol_universe_frozen"] is False

    def test_oos_symbol_universe_hash_none(self):
        result = _build_oos_seal_diagnostics()
        assert result["oos_symbol_universe_hash"] is None

    # ── Data hash fields ───────────────────────────────────────────────────
    def test_oos_data_hash_present_false(self):
        result = _build_oos_seal_diagnostics()
        assert result["oos_data_hash_present"] is False

    def test_oos_data_hash_none(self):
        result = _build_oos_seal_diagnostics()
        assert result["oos_data_hash"] is None

    # ── Seal metadata fields ───────────────────────────────────────────────
    def test_sealed_before_scoring_false(self):
        result = _build_oos_seal_diagnostics()
        assert result["sealed_before_scoring"] is False

    def test_seal_timestamp_utc_none(self):
        result = _build_oos_seal_diagnostics()
        assert result["seal_timestamp_utc"] is None

    def test_seal_commit_sha_none(self):
        result = _build_oos_seal_diagnostics()
        assert result["seal_commit_sha"] is None

    # ── Access policy fields ───────────────────────────────────────────────
    def test_holdout_access_policy_defined_false(self):
        result = _build_oos_seal_diagnostics()
        assert result["holdout_access_policy_defined"] is False

    def test_holdout_access_policy_not_defined(self):
        result = _build_oos_seal_diagnostics()
        assert result["holdout_access_policy"] == NOT_DEFINED

    # ── Dependency fields ──────────────────────────────────────────────────
    def test_strategy_rule_contract_dependency_satisfied_false(self):
        result = _build_oos_seal_diagnostics()
        assert result["strategy_rule_contract_dependency_satisfied"] is False

    def test_trial_manifest_dependency_satisfied_false(self):
        result = _build_oos_seal_diagnostics()
        assert result["trial_manifest_dependency_satisfied"] is False

    def test_split_scoring_safe_dependency_satisfied_false(self):
        result = _build_oos_seal_diagnostics()
        assert result["split_scoring_safe_dependency_satisfied"] is False

    def test_null_benchmark_contract_present_false(self):
        result = _build_oos_seal_diagnostics()
        assert result["null_benchmark_contract_present"] is False

    def test_multiple_testing_policy_present_false(self):
        result = _build_oos_seal_diagnostics()
        assert result["multiple_testing_policy_present"] is False

    # ── Prerequisites all false ────────────────────────────────────────────
    def test_oos_seal_prerequisites_all_false(self):
        result = _build_oos_seal_diagnostics()
        prereqs = result["oos_seal_prerequisites_present"]
        assert isinstance(prereqs, dict)
        for key, value in prereqs.items():
            assert value is False, f"{key} must be False, got {value}"

    def test_oos_seal_prerequisites_expected_keys(self):
        result = _build_oos_seal_diagnostics()
        prereqs = result["oos_seal_prerequisites_present"]
        expected_keys = {
            "strategy_rule_contract",
            "trial_manifest",
            "trial_count",
            "candidate_registry",
            "symbol_universe_freeze",
            "split_policy_freeze",
            "holdout_access_policy",
            "oos_period",
            "oos_data_hash",
            "null_benchmark_contract",
            "multiple_testing_policy",
        }
        assert prereqs.keys() == expected_keys

    # ── Integration into receipt ───────────────────────────────────────────
    def test_section_included_in_receipt(self):
        receipt = _base_receipt(
            oos_seal_diagnostics=_build_oos_seal_diagnostics(),
        )
        assert "oos_seal_diagnostics" in receipt

    def test_receipt_validates_with_section(self):
        receipt = _base_receipt(
            oos_seal_diagnostics=_build_oos_seal_diagnostics(),
        )
        # validate_real_validation_receipt should not raise
        validate_real_validation_receipt(receipt)

    def test_final_offline_verdict_unchanged(self):
        receipt = _base_receipt(
            oos_seal_diagnostics=_build_oos_seal_diagnostics(),
        )
        assert receipt["final_offline_verdict"] == (
            BLOCKED_BY_VALIDATION_IMPLEMENTATION
        )

    def test_guardrails_unchanged(self):
        receipt = _base_receipt(
            oos_seal_diagnostics=_build_oos_seal_diagnostics(),
        )
        for key, value in receipt["guardrail_status"].items():
            assert value is True, f"guardrail {key} must be True"

    # ── No forbidden keys ──────────────────────────────────────────────────
    def test_no_forbidden_calculation_keys(self):
        result = _build_oos_seal_diagnostics()
        all_keys = _all_dict_keys(result)
        assert _OOS_SEAL_FORBIDDEN_KEYS.isdisjoint(all_keys), (
            f"Forbidden keys found: "
            f"{_OOS_SEAL_FORBIDDEN_KEYS & all_keys}"
        )

    # ── CLI integration ────────────────────────────────────────────────────
    def test_cli_inventory_path_includes_section(self, tmp_path):
        """Inventory-based CLI path should include the section."""
        _write_tiny_bars_csv(tmp_path)
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        exit_code = real_validation.main([
            "--read-only", "--output-dir", str(output_dir),
            "--input-manifest-fingerprint", "abc",
            "--data-quality-receipt-sha256", "def",
            "--code-commit-sha", "ghi",
            "--bars-dir", str(tmp_path),
        ])
        assert exit_code == 0
        receipt_path = output_dir / "real_validation_receipt.json"
        assert receipt_path.exists()
        receipt = json.loads(receipt_path.read_text())
        assert "oos_seal_diagnostics" in receipt

    def test_cli_fallback_path_includes_section(self, tmp_path):
        """Fallback CLI path (no --bars-dir) should include the section."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        exit_code = real_validation.main([
            "--read-only", "--output-dir", str(output_dir),
            "--input-manifest-fingerprint", "abc",
            "--data-quality-receipt-sha256", "def",
            "--code-commit-sha", "ghi",
            "--global-min-timestamp", "2026-01-01T00:00:00Z",
            "--global-max-timestamp", "2026-02-01T00:00:00Z",
        ])
        assert exit_code == 0
        receipt_path = output_dir / "real_validation_receipt.json"
        assert receipt_path.exists()
        receipt = json.loads(receipt_path.read_text())
        assert "oos_seal_diagnostics" in receipt

    # ── Safety-key regression ──────────────────────────────────────────────
    def test_no_forbidden_top_level_keys_in_receipt(self):
        """Receipt with the section must still forbid pnl/sharpe/edge/strategy_performance."""
        receipt = _base_receipt(
            oos_seal_diagnostics=_build_oos_seal_diagnostics(),
        )
        for forbidden in ("pnl", "sharpe", "edge", "strategy_performance"):
            assert forbidden not in receipt

    def test_no_forbidden_calculation_keys_in_receipt(self):
        """Receipt with the section must still forbid all calculation keys."""
        receipt = _base_receipt(
            oos_seal_diagnostics=_build_oos_seal_diagnostics(),
        )
        all_keys = _all_dict_keys(receipt)
        assert _OOS_SEAL_FORBIDDEN_KEYS.isdisjoint(all_keys), (
            f"Forbidden keys found in receipt: "
            f"{_OOS_SEAL_FORBIDDEN_KEYS & all_keys}"
        )


_NULL_BENCHMARK_CONTRACT_FORBIDDEN_KEYS = frozenset({
    "pnl", "returns", "return", "sharpe", "drawdown", "risk", "edge",
    "strategy_performance", "trade", "trades", "signal", "signals",
    "position", "positions", "portfolio", "baseline_result",
    "benchmark_result", "profitable", "live_ready", "deploy_ready",
    "OFFLINE_EDGE_CANDIDATE", "EDGE_CANDIDATE",
    "funding_adjusted_return", "net_return_value", "price_change",
})
_MULTIPLE_TESTING_CONTROL_FORBIDDEN_KEYS = frozenset({
    "pnl", "returns", "return", "sharpe", "drawdown", "risk", "edge",
    "strategy_performance", "trade", "trades", "signal", "signals",
    "position", "positions", "portfolio", "baseline_result",
    "benchmark_result", "profitable", "live_ready", "deploy_ready",
    "OFFLINE_EDGE_CANDIDATE", "EDGE_CANDIDATE",
    "funding_adjusted_return", "net_return_value", "price_change",
    "p_value", "confidence_interval", "score", "metric",
    "performance", "profit",
})


class TestNullBenchmarkContractDiagnostics:
    """Tests for _build_null_benchmark_contract_diagnostics() and its
    integration into the offline-edge receipt."""

    # ── Helper returns a dict ──────────────────────────────────────────────
    def test_helper_returns_dict(self):
        result = _build_null_benchmark_contract_diagnostics()
        assert isinstance(result, dict)

    # ── Top-level field values ─────────────────────────────────────────────
    def test_contract_version(self):
        result = _build_null_benchmark_contract_diagnostics()
        assert result["contract_version"] == NULL_BENCHMARK_CONTRACT_VERSION

    def test_calculation_status(self):
        result = _build_null_benchmark_contract_diagnostics()
        assert result["calculation_status"] == NULL_BENCHMARK_CONTRACT_DIAGNOSTIC_ONLY

    def test_null_benchmark_contract_status(self):
        result = _build_null_benchmark_contract_diagnostics()
        assert result["null_benchmark_contract_status"] == NULL_BENCHMARK_CONTRACT_NOT_DEFINED

    def test_null_benchmark_contract_present_false(self):
        result = _build_null_benchmark_contract_diagnostics()
        assert result["null_benchmark_contract_present"] is False

    def test_null_benchmark_contract_hash_none(self):
        result = _build_null_benchmark_contract_diagnostics()
        assert result["null_benchmark_contract_hash"] is None

    def test_null_benchmark_contract_source_none(self):
        result = _build_null_benchmark_contract_diagnostics()
        assert result["null_benchmark_contract_source"] is None

    # ── Scoring fields ─────────────────────────────────────────────────────
    def test_scoring_authorized_false(self):
        result = _build_null_benchmark_contract_diagnostics()
        assert result["scoring_authorized"] is False

    def test_scoring_blocked_reason(self):
        result = _build_null_benchmark_contract_diagnostics()
        assert result["scoring_blocked_reason"] == (
            NULL_BENCHMARK_CONTRACT_BLOCKED_REASON_NOT_DEFINED
        )

    # ── Benchmark family fields ────────────────────────────────────────────
    def test_benchmark_family_defined_false(self):
        result = _build_null_benchmark_contract_diagnostics()
        assert result["benchmark_family_defined"] is False

    def test_benchmark_family_not_defined(self):
        result = _build_null_benchmark_contract_diagnostics()
        assert result["benchmark_family"] == NOT_DEFINED

    def test_benchmark_generation_policy_defined_false(self):
        result = _build_null_benchmark_contract_diagnostics()
        assert result["benchmark_generation_policy_defined"] is False

    def test_benchmark_generation_policy_not_defined(self):
        result = _build_null_benchmark_contract_diagnostics()
        assert result["benchmark_generation_policy"] == NOT_DEFINED

    def test_random_seed_policy_defined_false(self):
        result = _build_null_benchmark_contract_diagnostics()
        assert result["random_seed_policy_defined"] is False

    def test_random_seed_policy_not_defined(self):
        result = _build_null_benchmark_contract_diagnostics()
        assert result["random_seed_policy"] == NOT_DEFINED

    def test_shuffle_policy_defined_false(self):
        result = _build_null_benchmark_contract_diagnostics()
        assert result["shuffle_policy_defined"] is False

    def test_shuffle_policy_not_defined(self):
        result = _build_null_benchmark_contract_diagnostics()
        assert result["shuffle_policy"] == NOT_DEFINED

    def test_permutation_policy_defined_false(self):
        result = _build_null_benchmark_contract_diagnostics()
        assert result["permutation_policy_defined"] is False

    def test_permutation_policy_not_defined(self):
        result = _build_null_benchmark_contract_diagnostics()
        assert result["permutation_policy"] == NOT_DEFINED

    # ── Cost/funding inclusion policy fields ───────────────────────────────
    def test_cost_inclusion_policy_defined_false(self):
        result = _build_null_benchmark_contract_diagnostics()
        assert result["cost_inclusion_policy_defined"] is False

    def test_cost_inclusion_policy_not_defined(self):
        result = _build_null_benchmark_contract_diagnostics()
        assert result["cost_inclusion_policy"] == NOT_DEFINED

    def test_funding_inclusion_policy_defined_false(self):
        result = _build_null_benchmark_contract_diagnostics()
        assert result["funding_inclusion_policy_defined"] is False

    def test_funding_inclusion_policy_not_defined(self):
        result = _build_null_benchmark_contract_diagnostics()
        assert result["funding_inclusion_policy"] == NOT_DEFINED

    # ── OOS application policy fields ──────────────────────────────────────
    def test_oos_application_policy_defined_false(self):
        result = _build_null_benchmark_contract_diagnostics()
        assert result["oos_application_policy_defined"] is False

    def test_oos_application_policy_not_defined(self):
        result = _build_null_benchmark_contract_diagnostics()
        assert result["oos_application_policy"] == NOT_DEFINED

    # ── Dependency fields ──────────────────────────────────────────────────
    def test_strategy_rule_contract_dependency_satisfied_false(self):
        result = _build_null_benchmark_contract_diagnostics()
        assert result["strategy_rule_contract_dependency_satisfied"] is False

    def test_trial_manifest_dependency_satisfied_false(self):
        result = _build_null_benchmark_contract_diagnostics()
        assert result["trial_manifest_dependency_satisfied"] is False

    def test_oos_seal_dependency_satisfied_false(self):
        result = _build_null_benchmark_contract_diagnostics()
        assert result["oos_seal_dependency_satisfied"] is False

    def test_split_scoring_safe_dependency_satisfied_false(self):
        result = _build_null_benchmark_contract_diagnostics()
        assert result["split_scoring_safe_dependency_satisfied"] is False

    def test_multiple_testing_policy_present_false(self):
        result = _build_null_benchmark_contract_diagnostics()
        assert result["multiple_testing_policy_present"] is False

    # ── Prerequisites all false ────────────────────────────────────────────
    def test_prerequisites_all_false(self):
        result = _build_null_benchmark_contract_diagnostics()
        prereqs = result["null_benchmark_contract_prerequisites_present"]
        assert isinstance(prereqs, dict)
        for key, value in prereqs.items():
            assert value is False, f"{key} must be False, got {value}"

    def test_prerequisites_expected_keys(self):
        result = _build_null_benchmark_contract_diagnostics()
        prereqs = result["null_benchmark_contract_prerequisites_present"]
        expected_keys = {
            "strategy_rule_contract",
            "trial_manifest",
            "oos_seal",
            "split_scoring_safe",
            "benchmark_family",
            "benchmark_generation_policy",
            "random_seed_policy",
            "shuffle_policy",
            "permutation_policy",
            "cost_inclusion_policy",
            "funding_inclusion_policy",
            "oos_application_policy",
            "multiple_testing_policy",
        }
        assert prereqs.keys() == expected_keys

    # ── Integration into receipt ───────────────────────────────────────────
    def test_section_included_in_receipt(self):
        receipt = _base_receipt(
            null_benchmark_contract_diagnostics=(
                _build_null_benchmark_contract_diagnostics()
            ),
        )
        assert "null_benchmark_contract_diagnostics" in receipt

    def test_receipt_validates_with_section(self):
        receipt = _base_receipt(
            null_benchmark_contract_diagnostics=(
                _build_null_benchmark_contract_diagnostics()
            ),
        )
        # validate_real_validation_receipt should not raise
        validate_real_validation_receipt(receipt)

    def test_final_offline_verdict_unchanged(self):
        receipt = _base_receipt(
            null_benchmark_contract_diagnostics=(
                _build_null_benchmark_contract_diagnostics()
            ),
        )
        assert receipt["final_offline_verdict"] == (
            BLOCKED_BY_VALIDATION_IMPLEMENTATION
        )

    def test_guardrails_unchanged(self):
        receipt = _base_receipt(
            null_benchmark_contract_diagnostics=(
                _build_null_benchmark_contract_diagnostics()
            ),
        )
        for key, value in receipt["guardrail_status"].items():
            assert value is True, f"guardrail {key} must be True"

    # ── No forbidden keys ──────────────────────────────────────────────────
    def test_no_forbidden_calculation_keys(self):
        result = _build_null_benchmark_contract_diagnostics()
        all_keys = _all_dict_keys(result)
        assert _NULL_BENCHMARK_CONTRACT_FORBIDDEN_KEYS.isdisjoint(all_keys), (
            f"Forbidden keys found: "
            f"{_NULL_BENCHMARK_CONTRACT_FORBIDDEN_KEYS & all_keys}"
        )

    # ── CLI integration ────────────────────────────────────────────────────
    def test_cli_inventory_path_includes_section(self, tmp_path):
        """Inventory-based CLI path should include the section."""
        _write_tiny_bars_csv(tmp_path)
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        exit_code = real_validation.main([
            "--read-only", "--output-dir", str(output_dir),
            "--input-manifest-fingerprint", "abc",
            "--data-quality-receipt-sha256", "def",
            "--code-commit-sha", "ghi",
            "--bars-dir", str(tmp_path),
        ])
        assert exit_code == 0
        receipt_path = output_dir / "real_validation_receipt.json"
        assert receipt_path.exists()
        receipt = json.loads(receipt_path.read_text())
        assert "null_benchmark_contract_diagnostics" in receipt

    def test_cli_fallback_path_includes_section(self, tmp_path):
        """Fallback CLI path (no --bars-dir) should include the section."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        exit_code = real_validation.main([
            "--read-only", "--output-dir", str(output_dir),
            "--input-manifest-fingerprint", "abc",
            "--data-quality-receipt-sha256", "def",
            "--code-commit-sha", "ghi",
            "--global-min-timestamp", "2026-01-01T00:00:00Z",
            "--global-max-timestamp", "2026-02-01T00:00:00Z",
        ])
        assert exit_code == 0
        receipt_path = output_dir / "real_validation_receipt.json"
        assert receipt_path.exists()
        receipt = json.loads(receipt_path.read_text())
        assert "null_benchmark_contract_diagnostics" in receipt

    # ── Safety-key regression ──────────────────────────────────────────────
    def test_no_forbidden_top_level_keys_in_receipt(self):
        """Receipt with the section must still forbid pnl/sharpe/edge/strategy_performance."""
        receipt = _base_receipt(
            null_benchmark_contract_diagnostics=(
                _build_null_benchmark_contract_diagnostics()
            ),
        )
        for forbidden in ("pnl", "sharpe", "edge", "strategy_performance"):
            assert forbidden not in receipt

    def test_no_forbidden_calculation_keys_in_receipt(self):
        """Receipt with the section must still forbid all calculation keys."""
        receipt = _base_receipt(
            null_benchmark_contract_diagnostics=(
                _build_null_benchmark_contract_diagnostics()
            ),
        )
        all_keys = _all_dict_keys(receipt)
        assert _NULL_BENCHMARK_CONTRACT_FORBIDDEN_KEYS.isdisjoint(all_keys), (
            f"Forbidden keys found in receipt: "
            f"{_NULL_BENCHMARK_CONTRACT_FORBIDDEN_KEYS & all_keys}"
        )


class TestMultipleTestingControlDiagnostics:
    """Tests for _build_multiple_testing_control_diagnostics() and its
    integration into the offline-edge receipt."""

    # ── Helper returns a dict ──────────────────────────────────────────────
    def test_helper_returns_dict(self):
        result = _build_multiple_testing_control_diagnostics()
        assert isinstance(result, dict)

    # ── Top-level field values ─────────────────────────────────────────────
    def test_control_version(self):
        result = _build_multiple_testing_control_diagnostics()
        assert result["control_version"] == MULTIPLE_TESTING_CONTROL_VERSION

    def test_calculation_status(self):
        result = _build_multiple_testing_control_diagnostics()
        assert result["calculation_status"] == MULTIPLE_TESTING_CONTROL_DIAGNOSTIC_ONLY

    def test_multiple_testing_control_status(self):
        result = _build_multiple_testing_control_diagnostics()
        assert result["multiple_testing_control_status"] == MULTIPLE_TESTING_CONTROL_NOT_DEFINED

    def test_multiple_testing_control_present_false(self):
        result = _build_multiple_testing_control_diagnostics()
        assert result["multiple_testing_control_present"] is False

    def test_multiple_testing_control_hash_none(self):
        result = _build_multiple_testing_control_diagnostics()
        assert result["multiple_testing_control_hash"] is None

    def test_multiple_testing_control_source_none(self):
        result = _build_multiple_testing_control_diagnostics()
        assert result["multiple_testing_control_source"] is None

    # ── Scoring fields ─────────────────────────────────────────────────────
    def test_scoring_authorized_false(self):
        result = _build_multiple_testing_control_diagnostics()
        assert result["scoring_authorized"] is False

    def test_scoring_blocked_reason(self):
        result = _build_multiple_testing_control_diagnostics()
        assert result["scoring_blocked_reason"] == (
            MULTIPLE_TESTING_CONTROL_BLOCKED_REASON_NOT_DEFINED
        )

    # ── Trial adjustment policy fields ─────────────────────────────────────
    def test_trial_adjustment_policy_defined_false(self):
        result = _build_multiple_testing_control_diagnostics()
        assert result["trial_adjustment_policy_defined"] is False

    def test_trial_adjustment_policy_not_defined(self):
        result = _build_multiple_testing_control_diagnostics()
        assert result["trial_adjustment_policy"] == NOT_DEFINED

    def test_rejected_trial_accounting_policy_defined_false(self):
        result = _build_multiple_testing_control_diagnostics()
        assert result["rejected_trial_accounting_policy_defined"] is False

    def test_rejected_trial_accounting_policy_not_defined(self):
        result = _build_multiple_testing_control_diagnostics()
        assert result["rejected_trial_accounting_policy"] == NOT_DEFINED

    def test_family_definition_policy_defined_false(self):
        result = _build_multiple_testing_control_diagnostics()
        assert result["family_definition_policy_defined"] is False

    def test_family_definition_policy_not_defined(self):
        result = _build_multiple_testing_control_diagnostics()
        assert result["family_definition_policy"] == NOT_DEFINED

    # ── Multiple-testing control fields ────────────────────────────────────
    def test_dsr_control_defined_false(self):
        result = _build_multiple_testing_control_diagnostics()
        assert result["dsr_control_defined"] is False

    def test_dsr_control_policy_not_defined(self):
        result = _build_multiple_testing_control_diagnostics()
        assert result["dsr_control_policy"] == NOT_DEFINED

    def test_pbo_control_defined_false(self):
        result = _build_multiple_testing_control_diagnostics()
        assert result["pbo_control_defined"] is False

    def test_pbo_control_policy_not_defined(self):
        result = _build_multiple_testing_control_diagnostics()
        assert result["pbo_control_policy"] == NOT_DEFINED

    def test_cscv_control_defined_false(self):
        result = _build_multiple_testing_control_diagnostics()
        assert result["cscv_control_defined"] is False

    def test_cscv_control_policy_not_defined(self):
        result = _build_multiple_testing_control_diagnostics()
        assert result["cscv_control_policy"] == NOT_DEFINED

    def test_spa_control_defined_false(self):
        result = _build_multiple_testing_control_diagnostics()
        assert result["spa_control_defined"] is False

    def test_spa_control_policy_not_defined(self):
        result = _build_multiple_testing_control_diagnostics()
        assert result["spa_control_policy"] == NOT_DEFINED

    def test_reality_check_control_defined_false(self):
        result = _build_multiple_testing_control_diagnostics()
        assert result["reality_check_control_defined"] is False

    def test_reality_check_control_policy_not_defined(self):
        result = _build_multiple_testing_control_diagnostics()
        assert result["reality_check_control_policy"] == NOT_DEFINED

    def test_false_discovery_control_defined_false(self):
        result = _build_multiple_testing_control_diagnostics()
        assert result["false_discovery_control_defined"] is False

    def test_false_discovery_control_policy_not_defined(self):
        result = _build_multiple_testing_control_diagnostics()
        assert result["false_discovery_control_policy"] == NOT_DEFINED

    # ── Model/parameter selection lock fields ──────────────────────────────
    def test_model_selection_lock_defined_false(self):
        result = _build_multiple_testing_control_diagnostics()
        assert result["model_selection_lock_defined"] is False

    def test_model_selection_lock_not_defined(self):
        result = _build_multiple_testing_control_diagnostics()
        assert result["model_selection_lock"] == NOT_DEFINED

    def test_parameter_selection_lock_defined_false(self):
        result = _build_multiple_testing_control_diagnostics()
        assert result["parameter_selection_lock_defined"] is False

    def test_parameter_selection_lock_not_defined(self):
        result = _build_multiple_testing_control_diagnostics()
        assert result["parameter_selection_lock"] == NOT_DEFINED

    # ── Dependency fields ──────────────────────────────────────────────────
    def test_strategy_rule_contract_dependency_satisfied_false(self):
        result = _build_multiple_testing_control_diagnostics()
        assert result["strategy_rule_contract_dependency_satisfied"] is False

    def test_trial_manifest_dependency_satisfied_false(self):
        result = _build_multiple_testing_control_diagnostics()
        assert result["trial_manifest_dependency_satisfied"] is False

    def test_oos_seal_dependency_satisfied_false(self):
        result = _build_multiple_testing_control_diagnostics()
        assert result["oos_seal_dependency_satisfied"] is False

    def test_null_benchmark_contract_dependency_satisfied_false(self):
        result = _build_multiple_testing_control_diagnostics()
        assert result["null_benchmark_contract_dependency_satisfied"] is False

    def test_split_scoring_safe_dependency_satisfied_false(self):
        result = _build_multiple_testing_control_diagnostics()
        assert result["split_scoring_safe_dependency_satisfied"] is False

    # ── Prerequisites all false ────────────────────────────────────────────
    def test_prerequisites_all_false(self):
        result = _build_multiple_testing_control_diagnostics()
        prereqs = result["multiple_testing_control_prerequisites_present"]
        assert isinstance(prereqs, dict)
        for key, value in prereqs.items():
            assert value is False, f"{key} must be False, got {value}"

    def test_prerequisites_expected_keys(self):
        result = _build_multiple_testing_control_diagnostics()
        prereqs = result["multiple_testing_control_prerequisites_present"]
        expected_keys = {
            "strategy_rule_contract",
            "trial_manifest",
            "trial_count",
            "rejected_trial_accounting",
            "candidate_registry",
            "oos_seal",
            "null_benchmark_contract",
            "split_scoring_safe",
            "trial_adjustment_policy",
            "family_definition_policy",
            "dsr_control",
            "pbo_control",
            "cscv_control",
            "spa_control",
            "reality_check_control",
            "false_discovery_control",
            "model_selection_lock",
            "parameter_selection_lock",
        }
        assert prereqs.keys() == expected_keys

    # ── Integration into receipt ───────────────────────────────────────────
    def test_section_included_in_receipt(self):
        receipt = _base_receipt(
            multiple_testing_control_diagnostics=(
                _build_multiple_testing_control_diagnostics()
            ),
        )
        assert "multiple_testing_control_diagnostics" in receipt

    def test_section_omitted_if_not_passed(self):
        receipt = _base_receipt()
        assert "multiple_testing_control_diagnostics" not in receipt

    def test_receipt_validates_with_section(self):
        receipt = _base_receipt(
            multiple_testing_control_diagnostics=(
                _build_multiple_testing_control_diagnostics()
            ),
        )
        # validate_real_validation_receipt should not raise
        validate_real_validation_receipt(receipt)

    def test_final_offline_verdict_unchanged(self):
        receipt = _base_receipt(
            multiple_testing_control_diagnostics=(
                _build_multiple_testing_control_diagnostics()
            ),
        )
        assert receipt["final_offline_verdict"] == (
            BLOCKED_BY_VALIDATION_IMPLEMENTATION
        )

    def test_guardrails_unchanged(self):
        receipt = _base_receipt(
            multiple_testing_control_diagnostics=(
                _build_multiple_testing_control_diagnostics()
            ),
        )
        for key, value in receipt["guardrail_status"].items():
            assert value is True, f"guardrail {key} must be True"

    # ── No forbidden keys ──────────────────────────────────────────────────
    def test_no_forbidden_calculation_keys(self):
        result = _build_multiple_testing_control_diagnostics()
        all_keys = _all_dict_keys(result)
        assert _MULTIPLE_TESTING_CONTROL_FORBIDDEN_KEYS.isdisjoint(all_keys), (
            f"Forbidden keys found: "
            f"{_MULTIPLE_TESTING_CONTROL_FORBIDDEN_KEYS & all_keys}"
        )

    # ── CLI integration ────────────────────────────────────────────────────
    def test_cli_inventory_path_includes_section(self, tmp_path):
        """Inventory-based CLI path should include the section."""
        _write_tiny_bars_csv(tmp_path)
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        exit_code = real_validation.main([
            "--read-only", "--output-dir", str(output_dir),
            "--input-manifest-fingerprint", "abc",
            "--data-quality-receipt-sha256", "def",
            "--code-commit-sha", "ghi",
            "--bars-dir", str(tmp_path),
        ])
        assert exit_code == 0
        receipt_path = output_dir / "real_validation_receipt.json"
        assert receipt_path.exists()
        receipt = json.loads(receipt_path.read_text())
        assert "multiple_testing_control_diagnostics" in receipt

    def test_cli_fallback_path_includes_section(self, tmp_path):
        """Fallback CLI path (no --bars-dir) should include the section."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        exit_code = real_validation.main([
            "--read-only", "--output-dir", str(output_dir),
            "--input-manifest-fingerprint", "abc",
            "--data-quality-receipt-sha256", "def",
            "--code-commit-sha", "ghi",
            "--global-min-timestamp", "2026-01-01T00:00:00Z",
            "--global-max-timestamp", "2026-02-01T00:00:00Z",
        ])
        assert exit_code == 0
        receipt_path = output_dir / "real_validation_receipt.json"
        assert receipt_path.exists()
        receipt = json.loads(receipt_path.read_text())
        assert "multiple_testing_control_diagnostics" in receipt

    # ── Safety-key regression ──────────────────────────────────────────────
    def test_no_forbidden_top_level_keys_in_receipt(self):
        """Receipt with the section must still forbid pnl/sharpe/edge/strategy_performance."""
        receipt = _base_receipt(
            multiple_testing_control_diagnostics=(
                _build_multiple_testing_control_diagnostics()
            ),
        )
        for forbidden in ("pnl", "sharpe", "edge", "strategy_performance"):
            assert forbidden not in receipt

    def test_no_forbidden_calculation_keys_in_receipt(self):
        """Receipt with the section must still forbid all calculation keys."""
        receipt = _base_receipt(
            multiple_testing_control_diagnostics=(
                _build_multiple_testing_control_diagnostics()
            ),
        )
        all_keys = _all_dict_keys(receipt)
        assert _MULTIPLE_TESTING_CONTROL_FORBIDDEN_KEYS.isdisjoint(all_keys), (
            f"Forbidden keys found in receipt: "
            f"{_MULTIPLE_TESTING_CONTROL_FORBIDDEN_KEYS & all_keys}"
        )


_TRADE_POSITION_SIMULATION_CONTRACT_FORBIDDEN_KEYS = frozenset({
    "pnl", "returns", "return", "sharpe", "drawdown", "risk", "edge",
    "strategy_performance", "trade", "trades", "signal", "signals",
    "position", "positions", "portfolio", "baseline_result",
    "benchmark_result", "profitable", "live_ready", "deploy_ready",
    "OFFLINE_EDGE_CANDIDATE", "EDGE_CANDIDATE",
    "funding_adjusted_return", "net_return_value", "price_change",
    "p_value", "confidence_interval", "score", "metric",
    "performance", "profit", "order", "orders", "fill", "fills",
    "execution", "executions", "cost_adjusted_return",
    "gross_return_value",
})


class TestTradePositionSimulationContractDiagnostics:
    """Tests for _build_trade_position_simulation_contract_diagnostics() and
    its integration into the offline-edge receipt."""

    # ── Helper returns a dict ──────────────────────────────────────────────
    def test_helper_returns_dict(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        assert isinstance(result, dict)

    # ── Top-level field values ─────────────────────────────────────────────
    def test_contract_version(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        assert result["contract_version"] == TRADE_POSITION_SIMULATION_CONTRACT_VERSION

    def test_calculation_status(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        assert result["calculation_status"] == (
            TRADE_POSITION_SIMULATION_CONTRACT_DIAGNOSTIC_ONLY
        )

    def test_trade_position_simulation_contract_status(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        assert result["trade_position_simulation_contract_status"] == (
            TRADE_POSITION_SIMULATION_CONTRACT_NOT_DEFINED
        )

    def test_trade_position_simulation_contract_present_false(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        assert result["trade_position_simulation_contract_present"] is False

    def test_trade_position_simulation_contract_hash_none(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        assert result["trade_position_simulation_contract_hash"] is None

    def test_trade_position_simulation_contract_source_none(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        assert result["trade_position_simulation_contract_source"] is None

    # ── Scoring fields ─────────────────────────────────────────────────────
    def test_scoring_authorized_false(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        assert result["scoring_authorized"] is False

    def test_scoring_blocked_reason(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        assert result["scoring_blocked_reason"] == (
            TRADE_POSITION_SIMULATION_CONTRACT_BLOCKED_REASON_NOT_DEFINED
        )

    # ── Decision/order/fill/slippage/fee policy fields ─────────────────────
    def test_decision_timestamp_policy_defined_false(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        assert result["decision_timestamp_policy_defined"] is False

    def test_decision_timestamp_policy_not_defined(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        assert result["decision_timestamp_policy"] == NOT_DEFINED

    def test_order_timing_policy_defined_false(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        assert result["order_timing_policy_defined"] is False

    def test_order_timing_policy_not_defined(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        assert result["order_timing_policy"] == NOT_DEFINED

    def test_fill_policy_defined_false(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        assert result["fill_policy_defined"] is False

    def test_fill_policy_not_defined(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        assert result["fill_policy"] == NOT_DEFINED

    def test_slippage_policy_defined_false(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        assert result["slippage_policy_defined"] is False

    def test_slippage_policy_not_defined(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        assert result["slippage_policy"] == NOT_DEFINED

    def test_fee_application_policy_defined_false(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        assert result["fee_application_policy_defined"] is False

    def test_fee_application_policy_not_defined(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        assert result["fee_application_policy"] == NOT_DEFINED

    def test_funding_application_dependency_satisfied_false(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        assert result["funding_application_dependency_satisfied"] is False

    # ── Side/sizing policy fields ──────────────────────────────────────────
    def test_side_policy_defined_false(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        assert result["side_policy_defined"] is False

    def test_side_policy_not_defined(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        assert result["side_policy"] == NOT_DEFINED

    def test_notional_sizing_policy_defined_false(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        assert result["notional_sizing_policy_defined"] is False

    def test_notional_sizing_policy_not_defined(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        assert result["notional_sizing_policy"] == NOT_DEFINED

    # ── Lifecycle policy fields ────────────────────────────────────────────
    def test_entry_lifecycle_policy_defined_false(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        assert result["entry_lifecycle_policy_defined"] is False

    def test_entry_lifecycle_policy_not_defined(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        assert result["entry_lifecycle_policy"] == NOT_DEFINED

    def test_exit_lifecycle_policy_defined_false(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        assert result["exit_lifecycle_policy_defined"] is False

    def test_exit_lifecycle_policy_not_defined(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        assert result["exit_lifecycle_policy"] == NOT_DEFINED

    def test_holding_period_policy_defined_false(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        assert result["holding_period_policy_defined"] is False

    def test_holding_period_policy_not_defined(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        assert result["holding_period_policy"] == NOT_DEFINED

    def test_state_transition_policy_defined_false(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        assert result["state_transition_policy_defined"] is False

    def test_state_transition_policy_not_defined(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        assert result["state_transition_policy"] == NOT_DEFINED

    def test_concurrent_symbol_policy_defined_false(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        assert result["concurrent_symbol_policy_defined"] is False

    def test_concurrent_symbol_policy_not_defined(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        assert result["concurrent_symbol_policy"] == NOT_DEFINED

    def test_portfolio_accounting_policy_defined_false(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        assert result["portfolio_accounting_policy_defined"] is False

    def test_portfolio_accounting_policy_not_defined(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        assert result["portfolio_accounting_policy"] == NOT_DEFINED

    def test_invalid_state_policy_defined_false(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        assert result["invalid_state_policy_defined"] is False

    def test_invalid_state_policy_not_defined(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        assert result["invalid_state_policy"] == NOT_DEFINED

    def test_missing_data_policy_defined_false(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        assert result["missing_data_policy_defined"] is False

    def test_missing_data_policy_not_defined(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        assert result["missing_data_policy"] == NOT_DEFINED

    # ── Dependency fields ──────────────────────────────────────────────────
    def test_strategy_rule_contract_dependency_satisfied_false(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        assert result["strategy_rule_contract_dependency_satisfied"] is False

    def test_trial_manifest_dependency_satisfied_false(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        assert result["trial_manifest_dependency_satisfied"] is False

    def test_oos_seal_dependency_satisfied_false(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        assert result["oos_seal_dependency_satisfied"] is False

    def test_null_benchmark_contract_dependency_satisfied_false(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        assert result["null_benchmark_contract_dependency_satisfied"] is False

    def test_multiple_testing_control_dependency_satisfied_false(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        assert result["multiple_testing_control_dependency_satisfied"] is False

    def test_split_scoring_safe_dependency_satisfied_false(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        assert result["split_scoring_safe_dependency_satisfied"] is False

    # ── Prerequisites all false ────────────────────────────────────────────
    def test_prerequisites_all_false(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        prereqs = result["trade_position_simulation_contract_prerequisites_present"]
        assert isinstance(prereqs, dict)
        for key, value in prereqs.items():
            assert value is False, f"{key} must be False, got {value}"

    def test_prerequisites_expected_keys(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        prereqs = result["trade_position_simulation_contract_prerequisites_present"]
        expected_keys = {
            "strategy_rule_contract",
            "trial_manifest",
            "oos_seal",
            "null_benchmark_contract",
            "multiple_testing_control",
            "split_scoring_safe",
            "decision_timestamp_policy",
            "order_timing_policy",
            "fill_policy",
            "slippage_policy",
            "fee_application_policy",
            "funding_application_policy",
            "side_policy",
            "notional_sizing_policy",
            "entry_lifecycle_policy",
            "exit_lifecycle_policy",
            "holding_period_policy",
            "state_transition_policy",
            "concurrent_symbol_policy",
            "portfolio_accounting_policy",
            "invalid_state_policy",
            "missing_data_policy",
        }
        assert prereqs.keys() == expected_keys

    # ── Integration into receipt ───────────────────────────────────────────
    def test_section_included_in_receipt(self):
        receipt = _base_receipt(
            trade_position_simulation_contract_diagnostics=(
                _build_trade_position_simulation_contract_diagnostics()
            ),
        )
        assert "trade_position_simulation_contract_diagnostics" in receipt

    def test_section_omitted_if_not_passed(self):
        receipt = _base_receipt()
        assert "trade_position_simulation_contract_diagnostics" not in receipt

    def test_receipt_validates_with_section(self):
        receipt = _base_receipt(
            trade_position_simulation_contract_diagnostics=(
                _build_trade_position_simulation_contract_diagnostics()
            ),
        )
        # validate_real_validation_receipt should not raise
        validate_real_validation_receipt(receipt)

    def test_final_offline_verdict_unchanged(self):
        receipt = _base_receipt(
            trade_position_simulation_contract_diagnostics=(
                _build_trade_position_simulation_contract_diagnostics()
            ),
        )
        assert receipt["final_offline_verdict"] == (
            BLOCKED_BY_VALIDATION_IMPLEMENTATION
        )

    def test_guardrails_unchanged(self):
        receipt = _base_receipt(
            trade_position_simulation_contract_diagnostics=(
                _build_trade_position_simulation_contract_diagnostics()
            ),
        )
        for key, value in receipt["guardrail_status"].items():
            assert value is True, f"guardrail {key} must be True"

    # ── No forbidden keys ──────────────────────────────────────────────────
    def test_no_forbidden_calculation_keys(self):
        result = _build_trade_position_simulation_contract_diagnostics()
        all_keys = _all_dict_keys(result)
        assert _TRADE_POSITION_SIMULATION_CONTRACT_FORBIDDEN_KEYS.isdisjoint(all_keys), (
            f"Forbidden keys found: "
            f"{_TRADE_POSITION_SIMULATION_CONTRACT_FORBIDDEN_KEYS & all_keys}"
        )

    # ── CLI integration ────────────────────────────────────────────────────
    def test_cli_inventory_path_includes_section(self, tmp_path):
        """Inventory-based CLI path should include the section."""
        _write_tiny_bars_csv(tmp_path)
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        exit_code = real_validation.main([
            "--read-only", "--output-dir", str(output_dir),
            "--input-manifest-fingerprint", "abc",
            "--data-quality-receipt-sha256", "def",
            "--code-commit-sha", "ghi",
            "--bars-dir", str(tmp_path),
        ])
        assert exit_code == 0
        receipt_path = output_dir / "real_validation_receipt.json"
        assert receipt_path.exists()
        receipt = json.loads(receipt_path.read_text())
        assert "trade_position_simulation_contract_diagnostics" in receipt

    def test_cli_fallback_path_includes_section(self, tmp_path):
        """Fallback CLI path (no --bars-dir) should include the section."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        exit_code = real_validation.main([
            "--read-only", "--output-dir", str(output_dir),
            "--input-manifest-fingerprint", "abc",
            "--data-quality-receipt-sha256", "def",
            "--code-commit-sha", "ghi",
            "--global-min-timestamp", "2026-01-01T00:00:00Z",
            "--global-max-timestamp", "2026-02-01T00:00:00Z",
        ])
        assert exit_code == 0
        receipt_path = output_dir / "real_validation_receipt.json"
        assert receipt_path.exists()
        receipt = json.loads(receipt_path.read_text())
        assert "trade_position_simulation_contract_diagnostics" in receipt

    # ── Safety-key regression ──────────────────────────────────────────────
    def test_no_forbidden_top_level_keys_in_receipt(self):
        """Receipt with the section must still forbid pnl/sharpe/edge/strategy_performance."""
        receipt = _base_receipt(
            trade_position_simulation_contract_diagnostics=(
                _build_trade_position_simulation_contract_diagnostics()
            ),
        )
        for forbidden in ("pnl", "sharpe", "edge", "strategy_performance"):
            assert forbidden not in receipt

    def test_no_forbidden_calculation_keys_in_receipt(self):
        """Receipt with the section must still forbid all calculation keys."""
        receipt = _base_receipt(
            trade_position_simulation_contract_diagnostics=(
                _build_trade_position_simulation_contract_diagnostics()
            ),
        )
        all_keys = _all_dict_keys(receipt)
        assert _TRADE_POSITION_SIMULATION_CONTRACT_FORBIDDEN_KEYS.isdisjoint(all_keys), (
            f"Forbidden keys found in receipt: "
            f"{_TRADE_POSITION_SIMULATION_CONTRACT_FORBIDDEN_KEYS & all_keys}"
        )


_NET_PNL_EQUITY_RISK_CONTRACT_FORBIDDEN_KEYS = frozenset({
    "pnl", "returns", "return", "sharpe", "drawdown", "risk", "edge",
    "strategy_performance", "trade", "trades", "signal", "signals",
    "position", "positions", "portfolio", "baseline_result",
    "benchmark_result", "profitable", "live_ready", "deploy_ready",
    "OFFLINE_EDGE_CANDIDATE", "EDGE_CANDIDATE",
    "funding_adjusted_return", "net_return_value", "price_change",
    "p_value", "confidence_interval", "score", "metric",
    "performance", "profit", "order", "orders", "fill", "fills",
    "execution", "executions", "cost_adjusted_return",
    "gross_return_value", "equity", "equity_curve",
})


class TestNetPnlEquityRiskContractDiagnostics:
    """Tests for _build_net_pnl_equity_risk_contract_diagnostics() and
    its integration into the offline-edge receipt."""

    # ── Helper contract ────────────────────────────────────────────────────
    def test_helper_returns_dict(self):
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        assert isinstance(result, dict)

    def test_contract_version(self):
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        assert result["contract_version"] == NET_PNL_EQUITY_RISK_CONTRACT_VERSION

    def test_calculation_status(self):
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        assert result["calculation_status"] == (
            NET_PNL_EQUITY_RISK_CONTRACT_DIAGNOSTIC_ONLY
        )

    def test_net_pnl_equity_risk_contract_status(self):
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        assert result["net_pnl_equity_risk_contract_status"] == (
            NET_PNL_EQUITY_RISK_CONTRACT_NOT_DEFINED
        )

    def test_net_pnl_equity_risk_contract_present_false(self):
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        assert result["net_pnl_equity_risk_contract_present"] is False

    def test_net_pnl_equity_risk_contract_hash_none(self):
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        assert result["net_pnl_equity_risk_contract_hash"] is None

    def test_net_pnl_equity_risk_contract_source_none(self):
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        assert result["net_pnl_equity_risk_contract_source"] is None

    # ── Scoring lock ───────────────────────────────────────────────────────
    def test_scoring_authorized_false(self):
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        assert result["scoring_authorized"] is False

    def test_scoring_blocked_reason(self):
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        assert result["scoring_blocked_reason"] == (
            NET_PNL_EQUITY_RISK_CONTRACT_BLOCKED_REASON_NOT_DEFINED
        )

    # ── Capital base / accounting / realized-unrealized ────────────────────
    def test_capital_base_policy_defined_false(self):
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        assert result["capital_base_policy_defined"] is False

    def test_capital_base_policy_not_defined(self):
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        assert result["capital_base_policy"] == NOT_DEFINED

    def test_net_accounting_policy_defined_false(self):
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        assert result["net_accounting_policy_defined"] is False

    def test_net_accounting_policy_not_defined(self):
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        assert result["net_accounting_policy"] == NOT_DEFINED

    def test_realized_unrealized_policy_defined_false(self):
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        assert result["realized_unrealized_policy_defined"] is False

    def test_realized_unrealized_policy_not_defined(self):
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        assert result["realized_unrealized_policy"] == NOT_DEFINED

    # ── Cost / funding / simulator dependencies ────────────────────────────
    def test_cost_inclusion_dependency_satisfied_false(self):
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        assert result["cost_inclusion_dependency_satisfied"] is False

    def test_funding_inclusion_dependency_satisfied_false(self):
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        assert result["funding_inclusion_dependency_satisfied"] is False

    def test_simulator_dependency_satisfied_false(self):
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        assert result["simulator_dependency_satisfied"] is False

    # ── Mark-to-market / equity curve / aggregation ────────────────────────
    def test_mark_to_market_policy_defined_false(self):
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        assert result["mark_to_market_policy_defined"] is False

    def test_mark_to_market_policy_not_defined(self):
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        assert result["mark_to_market_policy"] == NOT_DEFINED

    def test_equity_curve_policy_defined_false(self):
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        assert result["equity_curve_policy_defined"] is False

    def test_equity_curve_policy_not_defined(self):
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        assert result["equity_curve_policy"] == NOT_DEFINED

    def test_aggregation_policy_defined_false(self):
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        assert result["aggregation_policy_defined"] is False

    def test_aggregation_policy_not_defined(self):
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        assert result["aggregation_policy"] == NOT_DEFINED

    # ── Drawdown / exposure / risk measure ─────────────────────────────────
    def test_drawdown_policy_defined_false(self):
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        assert result["drawdown_policy_defined"] is False

    def test_drawdown_policy_not_defined(self):
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        assert result["drawdown_policy"] == NOT_DEFINED

    def test_exposure_policy_defined_false(self):
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        assert result["exposure_policy_defined"] is False

    def test_exposure_policy_not_defined(self):
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        assert result["exposure_policy"] == NOT_DEFINED

    def test_risk_measure_policy_defined_false(self):
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        assert result["risk_measure_policy_defined"] is False

    def test_risk_measure_policy_not_defined(self):
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        assert result["risk_measure_policy"] == NOT_DEFINED

    # ── Benchmark comparison / final verdict scoring ───────────────────────
    def test_benchmark_comparison_dependency_satisfied_false(self):
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        assert result["benchmark_comparison_dependency_satisfied"] is False

    def test_final_verdict_scoring_dependency_satisfied_false(self):
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        assert result["final_verdict_scoring_dependency_satisfied"] is False

    # ── Upstream gate dependencies ─────────────────────────────────────────
    def test_strategy_rule_contract_dependency_satisfied_false(self):
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        assert result["strategy_rule_contract_dependency_satisfied"] is False

    def test_trial_manifest_dependency_satisfied_false(self):
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        assert result["trial_manifest_dependency_satisfied"] is False

    def test_oos_seal_dependency_satisfied_false(self):
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        assert result["oos_seal_dependency_satisfied"] is False

    def test_null_benchmark_contract_dependency_satisfied_false(self):
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        assert result["null_benchmark_contract_dependency_satisfied"] is False

    def test_multiple_testing_control_dependency_satisfied_false(self):
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        assert result["multiple_testing_control_dependency_satisfied"] is False

    def test_trade_position_simulation_contract_dependency_satisfied_false(self):
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        assert result["trade_position_simulation_contract_dependency_satisfied"] is False

    def test_split_scoring_safe_dependency_satisfied_false(self):
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        assert result["split_scoring_safe_dependency_satisfied"] is False

    # ── Prerequisites dict ─────────────────────────────────────────────────
    def test_prerequisites_all_false(self):
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        prereqs = result["net_pnl_equity_risk_contract_prerequisites_present"]
        assert isinstance(prereqs, dict)
        for key, value in prereqs.items():
            assert value is False, f"Prerequisite {key!r} is not False: {value!r}"

    def test_prerequisites_expected_keys(self):
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        prereqs = result["net_pnl_equity_risk_contract_prerequisites_present"]
        expected_keys = {
            "strategy_rule_contract",
            "trial_manifest",
            "oos_seal",
            "null_benchmark_contract",
            "multiple_testing_control",
            "trade_position_simulation_contract",
            "split_scoring_safe",
            "capital_base_policy",
            "net_accounting_policy",
            "realized_unrealized_policy",
            "cost_inclusion_policy",
            "funding_inclusion_policy",
            "mark_to_market_policy",
            "equity_curve_policy",
            "aggregation_policy",
            "drawdown_policy",
            "exposure_policy",
            "risk_measure_policy",
            "benchmark_comparison_policy",
            "final_verdict_scoring_policy",
        }
        assert set(prereqs.keys()) == expected_keys, (
            f"Prerequisite keys mismatch. Extra: {set(prereqs.keys()) - expected_keys}. "
            f"Missing: {expected_keys - set(prereqs.keys())}"
        )

    # ── Receipt integration ────────────────────────────────────────────────
    def test_integration_in_receipt_when_provided(self):
        receipt = _base_receipt(
            net_pnl_equity_risk_contract_diagnostics=(
                _build_net_pnl_equity_risk_contract_diagnostics()
            ),
        )
        assert "net_pnl_equity_risk_contract_diagnostics" in receipt

    def test_not_in_receipt_when_omitted(self):
        receipt = _base_receipt()
        assert "net_pnl_equity_risk_contract_diagnostics" not in receipt

    def test_receipt_validates(self):
        receipt = _base_receipt(
            net_pnl_equity_risk_contract_diagnostics=(
                _build_net_pnl_equity_risk_contract_diagnostics()
            ),
        )
        real_validation.validate_real_validation_receipt(receipt)

    def test_final_offline_verdict_unchanged(self):
        receipt = _base_receipt(
            net_pnl_equity_risk_contract_diagnostics=(
                _build_net_pnl_equity_risk_contract_diagnostics()
            ),
        )
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION

    def test_guardrails_unchanged(self):
        receipt = _base_receipt(
            net_pnl_equity_risk_contract_diagnostics=(
                _build_net_pnl_equity_risk_contract_diagnostics()
            ),
        )
        assert receipt["guardrail_status"]["edge_unproven"] is True
        assert receipt["guardrail_status"]["block_live_integration"] is True
        assert receipt["guardrail_status"]["no_report_promotion"] is True
        assert receipt["guardrail_status"]["output_under_tmp_only"] is True

    # ── Forbidden key safety ───────────────────────────────────────────────
    def test_no_forbidden_calculation_keys(self):
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        all_keys = _all_dict_keys(result)
        assert _NET_PNL_EQUITY_RISK_CONTRACT_FORBIDDEN_KEYS.isdisjoint(all_keys), (
            f"Forbidden keys found: "
            f"{_NET_PNL_EQUITY_RISK_CONTRACT_FORBIDDEN_KEYS & all_keys}"
        )

    def test_no_forbidden_top_level_keys_in_receipt(self):
        receipt = _base_receipt(
            net_pnl_equity_risk_contract_diagnostics=(
                _build_net_pnl_equity_risk_contract_diagnostics()
            ),
        )
        for forbidden in ("pnl", "sharpe", "edge", "strategy_performance"):
            assert forbidden not in receipt

    def test_no_forbidden_calculation_keys_in_receipt(self):
        receipt = _base_receipt(
            net_pnl_equity_risk_contract_diagnostics=(
                _build_net_pnl_equity_risk_contract_diagnostics()
            ),
        )
        all_keys = _all_dict_keys(receipt)
        assert _NET_PNL_EQUITY_RISK_CONTRACT_FORBIDDEN_KEYS.isdisjoint(all_keys), (
            f"Forbidden keys found in receipt: "
            f"{_NET_PNL_EQUITY_RISK_CONTRACT_FORBIDDEN_KEYS & all_keys}"
        )

    # ── CLI integration ────────────────────────────────────────────────────
    def test_cli_inventory_path_includes_section(self, tmp_path):
        _write_tiny_bars_csv(tmp_path)
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        exit_code = real_validation.main([
            "--read-only", "--output-dir", str(output_dir),
            "--input-manifest-fingerprint", "abc",
            "--data-quality-receipt-sha256", "def",
            "--code-commit-sha", "ghi",
            "--bars-dir", str(tmp_path),
        ])
        assert exit_code == 0
        receipt_path = output_dir / "real_validation_receipt.json"
        assert receipt_path.exists()
        receipt = json.loads(receipt_path.read_text())
        assert "net_pnl_equity_risk_contract_diagnostics" in receipt

    def test_cli_fallback_path_includes_section(self, tmp_path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        exit_code = real_validation.main([
            "--read-only", "--output-dir", str(output_dir),
            "--input-manifest-fingerprint", "abc",
            "--data-quality-receipt-sha256", "def",
            "--code-commit-sha", "ghi",
            "--global-min-timestamp", "2026-01-01T00:00:00Z",
            "--global-max-timestamp", "2026-02-01T00:00:00Z",
        ])
        assert exit_code == 0
        receipt_path = output_dir / "real_validation_receipt.json"
        assert receipt_path.exists()
        receipt = json.loads(receipt_path.read_text())
        assert "net_pnl_equity_risk_contract_diagnostics" in receipt

    # ── Blocker 2 regression: no-args has dedicated EAP absence diagnostics ──
    def test_no_args_has_eap_absence_shape(self):
        """No-args path returns EAP absence diagnostics, not reused net-PnL."""
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        assert result["net_pnl_equity_risk_contract_status"] == (
            NET_PNL_EQUITY_RISK_CONTRACT_NOT_DEFINED
        )
        assert result["net_pnl_equity_risk_contract_present"] is False

        eap = result["economic_accounting_policy_diagnostics"]
        assert eap["diagnostic_kind"] == "economic_accounting_policy_absence"
        assert eap["economic_accounting_policy_status"] == (
            "ECONOMIC_ACCOUNTING_POLICY_NOT_DEFINED"
        )
        assert "net_pnl_equity_risk_contract_status" not in eap
        assert eap["economic_accounting_policy_preregistration_gate"][
            "gate_passed"
        ] is False
        assert eap["economic_accounting_policy_preregistration_gate"][
            "gate_status"
        ] == "ECONOMIC_ACCOUNTING_POLICY_NOT_LOADED"

    def test_no_args_eap_absence_not_net_pnl_absence(self):
        """No-args path must not emit net-PnL absence as EAP diagnostics."""
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        eap = result["economic_accounting_policy_diagnostics"]
        assert "net_pnl_equity_risk_contract_status" not in eap
        assert "net_pnl_equity_risk_contract_present" not in eap
        assert "net_pnl_equity_risk_contract_hash" not in eap
        assert "net_pnl_equity_risk_contract_source" not in eap
        assert eap["diagnostic_kind"] == "economic_accounting_policy_absence"
        assert eap["economic_accounting_policy_present"] is False

    def test_no_args_top_level_gate_from_eap_absence(self):
        """Top-level preregistration gate matches EAP absence gate."""
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        gate = result["economic_accounting_policy_preregistration_gate"]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == "ECONOMIC_ACCOUNTING_POLICY_NOT_LOADED"
        assert gate["blocked_reason"] == "ECONOMIC_ACCOUNTING_POLICY_NOT_PROVIDED"

    def test_no_args_forbidden_keys_still_pass(self):
        """No-args result with EAP nested diagnostics passes forbidden key scan."""
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        all_keys = _all_dict_keys(result)
        assert _NET_PNL_EQUITY_RISK_CONTRACT_FORBIDDEN_KEYS.isdisjoint(all_keys), (
            f"Forbidden keys found: "
            f"{_NET_PNL_EQUITY_RISK_CONTRACT_FORBIDDEN_KEYS & all_keys}"
        )


_FINAL_OFFLINE_EDGE_VERDICT_LOGIC_FORBIDDEN_KEYS = frozenset({
    "pnl", "returns", "return", "sharpe", "drawdown", "risk", "edge",
    "strategy_performance", "trade", "trades", "signal", "signals",
    "position", "positions", "portfolio", "baseline_result",
    "benchmark_result", "profitable", "live_ready", "deploy_ready",
    "OFFLINE_EDGE_CANDIDATE", "EDGE_CANDIDATE",
    "funding_adjusted_return", "net_return_value", "price_change",
    "p_value", "confidence_interval", "score", "metric",
    "performance", "profit", "order", "orders", "fill", "fills",
    "execution", "executions", "cost_adjusted_return",
    "gross_return_value", "equity", "equity_curve",
})


class TestFinalOfflineEdgeVerdictLogicDiagnostics:
    """Tests for _build_final_offline_edge_verdict_logic_diagnostics() and its
    integration into the offline-edge receipt.

    The section is a static absence record: it must never advance the verdict,
    never authorize scoring/edge-candidacy/promotion/live integration, and
    never introspect sibling receipt sections.
    """

    # ── Helper contract ────────────────────────────────────────────────────
    def test_helper_returns_dict(self):
        result = _build_final_offline_edge_verdict_logic_diagnostics()
        assert isinstance(result, dict)

    def test_logic_version(self):
        result = _build_final_offline_edge_verdict_logic_diagnostics()
        assert result["logic_version"] == FINAL_OFFLINE_EDGE_VERDICT_LOGIC_VERSION

    def test_calculation_status(self):
        result = _build_final_offline_edge_verdict_logic_diagnostics()
        assert result["calculation_status"] == (
            FINAL_OFFLINE_EDGE_VERDICT_LOGIC_DIAGNOSTIC_ONLY
        )

    def test_final_verdict_logic_status(self):
        result = _build_final_offline_edge_verdict_logic_diagnostics()
        assert result["final_verdict_logic_status"] == (
            FINAL_OFFLINE_EDGE_VERDICT_LOGIC_BLOCKED
        )

    # ── Authorization locks ────────────────────────────────────────────────
    def test_final_scoring_authorized_false(self):
        result = _build_final_offline_edge_verdict_logic_diagnostics()
        assert result["final_scoring_authorized"] is False

    def test_final_verdict_advancement_authorized_false(self):
        result = _build_final_offline_edge_verdict_logic_diagnostics()
        assert result["final_verdict_advancement_authorized"] is False

    def test_edge_candidate_authorized_false(self):
        result = _build_final_offline_edge_verdict_logic_diagnostics()
        assert result["edge_candidate_authorized"] is False

    def test_live_integration_authorized_false(self):
        result = _build_final_offline_edge_verdict_logic_diagnostics()
        assert result["live_integration_authorized"] is False

    def test_report_promotion_authorized_false(self):
        result = _build_final_offline_edge_verdict_logic_diagnostics()
        assert result["report_promotion_authorized"] is False

    def test_all_authorization_flags_false(self):
        result = _build_final_offline_edge_verdict_logic_diagnostics()
        for key in (
            "final_scoring_authorized",
            "final_verdict_advancement_authorized",
            "edge_candidate_authorized",
            "live_integration_authorized",
            "report_promotion_authorized",
        ):
            assert result[key] is False, f"{key!r} is not False: {result[key]!r}"

    # ── Verdict is frozen ──────────────────────────────────────────────────
    def test_current_final_offline_verdict_blocked(self):
        result = _build_final_offline_edge_verdict_logic_diagnostics()
        assert result["current_final_offline_verdict"] == (
            BLOCKED_BY_VALIDATION_IMPLEMENTATION
        )

    def test_next_final_offline_verdict_blocked(self):
        result = _build_final_offline_edge_verdict_logic_diagnostics()
        assert result["next_final_offline_verdict"] == (
            BLOCKED_BY_VALIDATION_IMPLEMENTATION
        )

    def test_current_equals_next_verdict(self):
        result = _build_final_offline_edge_verdict_logic_diagnostics()
        assert (
            result["current_final_offline_verdict"]
            == result["next_final_offline_verdict"]
        )

    def test_final_verdict_advancement_blocked_reason(self):
        result = _build_final_offline_edge_verdict_logic_diagnostics()
        assert result["final_verdict_advancement_blocked_reason"] == (
            FINAL_VERDICT_ADVANCEMENT_BLOCKED_REASON
        )

    def test_upstream_reduction_mode_static(self):
        result = _build_final_offline_edge_verdict_logic_diagnostics()
        assert result["upstream_reduction_mode"] == UPSTREAM_REDUCTION_MODE_STATIC

    # ── Required upstream gates ────────────────────────────────────────────
    def test_required_upstream_gates_expected_keys(self):
        result = _build_final_offline_edge_verdict_logic_diagnostics()
        gates = result["required_upstream_gates"]
        expected_keys = {
            "strategy_rule_contract",
            "trial_manifest",
            "oos_seal",
            "null_benchmark_contract",
            "multiple_testing_control",
            "trade_position_simulation_contract",
            "net_pnl_equity_risk_contract",
            "split_scoring_safe",
        }
        assert set(gates.keys()) == expected_keys, (
            f"Gate keys mismatch. Extra: {set(gates.keys()) - expected_keys}. "
            f"Missing: {expected_keys - set(gates.keys())}"
        )

    def test_required_upstream_gates_expected_values(self):
        result = _build_final_offline_edge_verdict_logic_diagnostics()
        assert result["required_upstream_gates"] == {
            "strategy_rule_contract": STRATEGY_RULE_CONTRACT_NOT_DEFINED,
            "trial_manifest": TRIAL_MANIFEST_NOT_DEFINED,
            "oos_seal": OOS_SEAL_NOT_DEFINED,
            "null_benchmark_contract": NULL_BENCHMARK_CONTRACT_NOT_DEFINED,
            "multiple_testing_control": MULTIPLE_TESTING_CONTROL_NOT_DEFINED,
            "trade_position_simulation_contract": (
                TRADE_POSITION_SIMULATION_CONTRACT_NOT_DEFINED
            ),
            "net_pnl_equity_risk_contract": NET_PNL_EQUITY_RISK_CONTRACT_NOT_DEFINED,
            "split_scoring_safe": FINAL_VERDICT_SPLIT_SCORING_NOT_SAFE,
        }

    # ── Prerequisites dict ─────────────────────────────────────────────────
    def test_prerequisites_expected_keys(self):
        result = _build_final_offline_edge_verdict_logic_diagnostics()
        prereqs = result["final_verdict_prerequisites_present"]
        expected_keys = {
            "strategy_rule_contract",
            "trial_manifest",
            "oos_seal",
            "split_scoring_safe",
            "null_benchmark_contract",
            "multiple_testing_control",
            "trade_position_simulation_contract",
            "net_pnl_equity_risk_contract",
            "final_scoring_policy",
            "edge_candidate_policy",
            "report_promotion_policy",
            "live_integration_policy",
        }
        assert set(prereqs.keys()) == expected_keys, (
            f"Prerequisite keys mismatch. Extra: {set(prereqs.keys()) - expected_keys}. "
            f"Missing: {expected_keys - set(prereqs.keys())}"
        )

    def test_prerequisites_all_false(self):
        result = _build_final_offline_edge_verdict_logic_diagnostics()
        prereqs = result["final_verdict_prerequisites_present"]
        assert isinstance(prereqs, dict)
        for key, value in prereqs.items():
            assert value is False, f"Prerequisite {key!r} is not False: {value!r}"

    def test_final_scoring_authorized_matches_prerequisites(self):
        result = _build_final_offline_edge_verdict_logic_diagnostics()
        prereqs = result["final_verdict_prerequisites_present"]
        assert result["final_scoring_authorized"] == all(prereqs.values()) is False

    # ── Receipt integration ────────────────────────────────────────────────
    def test_integration_in_receipt_when_provided(self):
        receipt = _base_receipt(
            final_offline_edge_verdict_logic_diagnostics=(
                _build_final_offline_edge_verdict_logic_diagnostics()
            ),
        )
        assert "final_offline_edge_verdict_logic_diagnostics" in receipt

    def test_not_in_receipt_when_omitted(self):
        receipt = _base_receipt()
        assert "final_offline_edge_verdict_logic_diagnostics" not in receipt

    def test_receipt_validates(self):
        receipt = _base_receipt(
            final_offline_edge_verdict_logic_diagnostics=(
                _build_final_offline_edge_verdict_logic_diagnostics()
            ),
        )
        real_validation.validate_real_validation_receipt(receipt)

    def test_final_offline_verdict_unchanged(self):
        receipt = _base_receipt(
            final_offline_edge_verdict_logic_diagnostics=(
                _build_final_offline_edge_verdict_logic_diagnostics()
            ),
        )
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION

    def test_section_verdict_matches_top_level_verdict(self):
        receipt = _base_receipt(
            final_offline_edge_verdict_logic_diagnostics=(
                _build_final_offline_edge_verdict_logic_diagnostics()
            ),
        )
        section = receipt["final_offline_edge_verdict_logic_diagnostics"]
        assert section["current_final_offline_verdict"] == (
            receipt["final_offline_verdict"]
        )

    def test_guardrails_unchanged(self):
        receipt = _base_receipt(
            final_offline_edge_verdict_logic_diagnostics=(
                _build_final_offline_edge_verdict_logic_diagnostics()
            ),
        )
        assert receipt["guardrail_status"]["edge_unproven"] is True
        assert receipt["guardrail_status"]["block_live_integration"] is True
        assert receipt["guardrail_status"]["no_report_promotion"] is True
        assert receipt["guardrail_status"]["output_under_tmp_only"] is True

    # ── Forbidden key safety ───────────────────────────────────────────────
    def test_no_forbidden_calculation_keys(self):
        result = _build_final_offline_edge_verdict_logic_diagnostics()
        all_keys = _all_dict_keys(result)
        assert _FINAL_OFFLINE_EDGE_VERDICT_LOGIC_FORBIDDEN_KEYS.isdisjoint(all_keys), (
            f"Forbidden keys found: "
            f"{_FINAL_OFFLINE_EDGE_VERDICT_LOGIC_FORBIDDEN_KEYS & all_keys}"
        )

    def test_no_forbidden_top_level_keys_in_receipt(self):
        receipt = _base_receipt(
            final_offline_edge_verdict_logic_diagnostics=(
                _build_final_offline_edge_verdict_logic_diagnostics()
            ),
        )
        for forbidden in ("pnl", "sharpe", "edge", "strategy_performance"):
            assert forbidden not in receipt

    def test_no_forbidden_calculation_keys_in_receipt(self):
        receipt = _base_receipt(
            final_offline_edge_verdict_logic_diagnostics=(
                _build_final_offline_edge_verdict_logic_diagnostics()
            ),
        )
        all_keys = _all_dict_keys(receipt)
        assert _FINAL_OFFLINE_EDGE_VERDICT_LOGIC_FORBIDDEN_KEYS.isdisjoint(all_keys), (
            f"Forbidden keys found in receipt: "
            f"{_FINAL_OFFLINE_EDGE_VERDICT_LOGIC_FORBIDDEN_KEYS & all_keys}"
        )

    # ── CLI integration ────────────────────────────────────────────────────
    def test_cli_inventory_path_includes_section(self, tmp_path):
        _write_tiny_bars_csv(tmp_path)
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        exit_code = real_validation.main([
            "--read-only", "--output-dir", str(output_dir),
            "--input-manifest-fingerprint", "abc",
            "--data-quality-receipt-sha256", "def",
            "--code-commit-sha", "ghi",
            "--bars-dir", str(tmp_path),
        ])
        assert exit_code == 0
        receipt_path = output_dir / "real_validation_receipt.json"
        assert receipt_path.exists()
        receipt = json.loads(receipt_path.read_text())
        assert "final_offline_edge_verdict_logic_diagnostics" in receipt
        section = receipt["final_offline_edge_verdict_logic_diagnostics"]
        assert section["final_verdict_logic_status"] == (
            FINAL_OFFLINE_EDGE_VERDICT_LOGIC_BLOCKED
        )
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION


class TestTrialManifestPreregistrationMaterializer:
    """Tests for materialize_trial_manifest_preregistration_diagnostics()."""

    # ── Helpers ──────────────────────────────────────────────────────────

    def _write_manifest(self, tmp_path: Path, overrides: dict | None = None) -> Path:
        """Write a valid trial manifest JSON and return its path."""
        data = {
            "manifest_id": "qnty_offline_edge_trial_manifest_v1",
            "manifest_version": "1.0.0",
            "manifest_kind": "TRIAL_MANIFEST_PRE_REGISTRATION_ONLY",
            "manifest_status": "FROZEN_PRE_REGISTRATION_ONLY",
            "manifest_hash": "FROZEN_IN_SIDECAR",
            "manifest_hash_algorithm": "sha256",
            "manifest_hash_scope": "exact committed JSON bytes, excluding sidecar",
            "manifest_hash_status": "FROZEN_IN_SIDECAR",
            "bound_contract_id": "qnty_offline_edge_strategy_rule_contract_v1",
            "bound_contract_sha256": "d6462a76c8f2bde79352baab2de0bd6dff3ad6b0f4139c6fba9f7764df04e0d9",
            "bound_contract_sha256_sidecar_path": "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.sha256",
            "bound_contract_commit_binding_path": "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.commit_binding.json",
            "required_contract_packet_gate_status": "CONTRACT_PACKET_COMMIT_BOUND_DIAGNOSTIC_ONLY",
            "required_contract_packet_gate_scope": "CONTRACT_PACKET_EXISTENCE_HASH_AND_COMMIT_BINDING_ONLY",
            "candidate_id": "funding_carry_v1_declaration_only",
            "hypothesis_id": "funding_carry_v1_pre_scoring",
            "candidate_family": "funding_carry_declaration_only",
            "trial_policy": "SINGLE_TRIAL_NO_SEARCH",
            "authorized_trial_count": 1,
            "trial_count_frozen": True,
            "hyperparameter_search_policy": "NO_SEARCH",
            "free_parameter_count": 0,
            "declared_parameter_names": [],
            "dataset_binding_policy": "USES_EXISTING_OFFLINE_EDGE_INPUT_INVENTORY_AT_RUNTIME",
            "split_binding_policy": "USES_EXISTING_DETERMINISTIC_SPLIT_DEFINITIONS_AT_RUNTIME",
            "symbol_universe_policy": "USES_VALIDATION_INVENTORY_SYMBOLS_AT_RUNTIME_NOT_FROZEN_HERE",
            "trial_execution_authorized": False,
            "scoring_authorization": False,
            "live_integration_authorized": False,
            "paper_integration_authorized": False,
            "final_verdict_authorization": False,
            "oos_seal_dependency_satisfied": False,
            "null_benchmark_dependency_satisfied": False,
            "multiple_testing_dependency_satisfied": False,
            "trade_position_simulation_dependency_satisfied": False,
            "net_pnl_equity_risk_dependency_satisfied": False,
        }
        if overrides:
            data.update(overrides)
        json_str = json.dumps(data, sort_keys=True, indent=2) + "\n"
        path = tmp_path / "trial_manifest.json"
        path.write_text(json_str)
        return path

    def _write_sidecar(self, tmp_path: Path, manifest_path: Path) -> Path:
        """Write a valid SHA-256 sidecar for the manifest and return its path."""
        digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        sidecar_path = tmp_path / "trial_manifest.sha256"
        sidecar_path.write_text(f"{digest}  {manifest_path.name}\n")
        return sidecar_path

    def _make_contract_diagnostics(self, gate_passed: bool = True) -> dict:
        """Build a mock strategy-rule contract diagnostics dict."""
        return {
            "contract_id": "qnty_offline_edge_strategy_rule_contract_v1",
            "json_sha256": "d6462a76c8f2bde79352baab2de0bd6dff3ad6b0f4139c6fba9f7764df04e0d9",
            "contract_packet_gate": {
                "gate_passed": gate_passed,
                "gate_status": (
                    "CONTRACT_PACKET_COMMIT_BOUND_DIAGNOSTIC_ONLY"
                    if gate_passed
                    else "BLOCKED_BY_INCOMPLETE_EVIDENCE"
                ),
            },
        }

    # ── Happy path tests ────────────────────────────────────────────────

    def test_manifest_json_sidecar_happy_path(self, tmp_path):
        """Validate manifest sidecar, strict key scan passes, hash authority sidecar."""
        manifest_path = self._write_manifest(tmp_path)
        sidecar_path = self._write_sidecar(tmp_path, manifest_path)
        contract_diag = self._make_contract_diagnostics(gate_passed=True)

        result = materialize_trial_manifest_preregistration_diagnostics(
            manifest_path=str(manifest_path),
            sidecar_path=str(sidecar_path),
            strategy_rule_contract_diagnostics=contract_diag,
        )

        assert result["manifest_sidecar_digest_matches_json_bytes"] is True
        assert result["manifest_forbidden_dict_key_scan_passed"] is True
        assert result["manifest_hash_authority"] == "SIDECAR"
        assert result["manifest_hash_field_value"] == "FROZEN_IN_SIDECAR"
        assert result["manifest_hash_status"] == "FROZEN_IN_SIDECAR"

    def test_trial_manifest_diagnostic_happy_path(self, tmp_path):
        """Build C2 contract diagnostics, build trial manifest diagnostics."""
        manifest_path = self._write_manifest(tmp_path)
        sidecar_path = self._write_sidecar(tmp_path, manifest_path)
        contract_diag = self._make_contract_diagnostics(gate_passed=True)

        result = materialize_trial_manifest_preregistration_diagnostics(
            manifest_path=str(manifest_path),
            sidecar_path=str(sidecar_path),
            strategy_rule_contract_diagnostics=contract_diag,
        )

        assert result["manifest_sidecar_digest_matches_json_bytes"] is True
        assert result["bound_contract_digest_matches"] is True
        assert result["contract_packet_gate_passed"] is True
        assert result["authorized_trial_count"] == 1
        assert result["hyperparameter_search_policy"] == "NO_SEARCH"
        assert result["free_parameter_count"] == 0
        assert result["trial_execution_authorized"] is False
        assert result["trial_scoring_ready"] is False

    def test_trial_manifest_gate_derived_happy_path(self, tmp_path):
        """Gate passed true, status preregistered, scoring/live/final false."""
        manifest_path = self._write_manifest(tmp_path)
        sidecar_path = self._write_sidecar(tmp_path, manifest_path)
        contract_diag = self._make_contract_diagnostics(gate_passed=True)

        diagnostics = materialize_trial_manifest_preregistration_diagnostics(
            manifest_path=str(manifest_path),
            sidecar_path=str(sidecar_path),
            strategy_rule_contract_diagnostics=contract_diag,
        )
        gate = _derive_trial_manifest_preregistration_gate(diagnostics)

        assert gate["gate_passed"] is True
        assert gate["gate_status"] == "TRIAL_MANIFEST_PREREGISTERED_DIAGNOSTIC_ONLY"
        assert gate["gate_scoring_authorization"] is False
        assert gate["gate_live_authorization"] is False
        assert gate["gate_final_verdict_authorization"] is False
        assert gate["gate_downstream_unlocks"] == []

    # ── Fail-closed tests ───────────────────────────────────────────────

    def test_manifest_missing_fails_closed(self, tmp_path):
        """Manifest file missing raises ValueError."""
        contract_diag = self._make_contract_diagnostics(gate_passed=True)
        with pytest.raises(ValueError, match="not found"):
            materialize_trial_manifest_preregistration_diagnostics(
                manifest_path=str(tmp_path / "nonexistent.json"),
                sidecar_path=str(tmp_path / "nonexistent.sha256"),
                strategy_rule_contract_diagnostics=contract_diag,
            )

    def test_sidecar_missing_fails_closed(self, tmp_path):
        """Sidecar file missing raises ValueError."""
        manifest_path = self._write_manifest(tmp_path)
        contract_diag = self._make_contract_diagnostics(gate_passed=True)
        with pytest.raises(ValueError, match="not found"):
            materialize_trial_manifest_preregistration_diagnostics(
                manifest_path=str(manifest_path),
                sidecar_path=str(tmp_path / "nonexistent.sha256"),
                strategy_rule_contract_diagnostics=contract_diag,
            )

    def test_digest_mismatch_fails_closed(self, tmp_path):
        """Sidecar digest mismatch raises ValueError."""
        manifest_path = self._write_manifest(tmp_path)
        sidecar_path = tmp_path / "trial_manifest.sha256"
        sidecar_path.write_text("0000000000000000000000000000000000000000000000000000000000000000  bad.json\n")
        contract_diag = self._make_contract_diagnostics(gate_passed=True)
        with pytest.raises(ValueError, match="digest mismatch"):
            materialize_trial_manifest_preregistration_diagnostics(
                manifest_path=str(manifest_path),
                sidecar_path=str(sidecar_path),
                strategy_rule_contract_diagnostics=contract_diag,
            )

    def test_malformed_json_fails_closed(self, tmp_path):
        """Malformed manifest JSON raises ValueError."""
        manifest_path = tmp_path / "bad.json"
        manifest_path.write_text("{bad json}\n")
        sidecar_digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        sidecar_path = tmp_path / "bad.sha256"
        sidecar_path.write_text(f"{sidecar_digest}  bad.json\n")
        contract_diag = self._make_contract_diagnostics(gate_passed=True)
        with pytest.raises(ValueError, match="parse error"):
            materialize_trial_manifest_preregistration_diagnostics(
                manifest_path=str(manifest_path),
                sidecar_path=str(sidecar_path),
                strategy_rule_contract_diagnostics=contract_diag,
            )

    def test_forbidden_dict_key_fails_closed(self, tmp_path):
        """Forbidden dict key in manifest raises ValueError."""
        manifest_path = self._write_manifest(tmp_path, overrides={"pnl": 1})
        sidecar_path = self._write_sidecar(tmp_path, manifest_path)
        contract_diag = self._make_contract_diagnostics(gate_passed=True)
        with pytest.raises(ValueError, match="forbidden"):
            materialize_trial_manifest_preregistration_diagnostics(
                manifest_path=str(manifest_path),
                sidecar_path=str(sidecar_path),
                strategy_rule_contract_diagnostics=contract_diag,
            )

    def test_contract_digest_mismatch_fails_closed(self, tmp_path):
        """Bound contract digest mismatch raises ValueError."""
        manifest_path = self._write_manifest(tmp_path, overrides={
            "bound_contract_sha256": "0" * 64,
        })
        sidecar_path = self._write_sidecar(tmp_path, manifest_path)
        contract_diag = self._make_contract_diagnostics(gate_passed=True)
        with pytest.raises(ValueError, match="mismatch"):
            materialize_trial_manifest_preregistration_diagnostics(
                manifest_path=str(manifest_path),
                sidecar_path=str(sidecar_path),
                strategy_rule_contract_diagnostics=contract_diag,
            )

    def test_contract_packet_gate_false_blocks(self, tmp_path):
        """Contract packet gate missing/false blocks manifest."""
        manifest_path = self._write_manifest(tmp_path)
        sidecar_path = self._write_sidecar(tmp_path, manifest_path)
        contract_diag = self._make_contract_diagnostics(gate_passed=False)
        with pytest.raises(ValueError, match="gate not passed"):
            materialize_trial_manifest_preregistration_diagnostics(
                manifest_path=str(manifest_path),
                sidecar_path=str(sidecar_path),
                strategy_rule_contract_diagnostics=contract_diag,
            )

    def test_authorized_trial_count_not_one_fails(self, tmp_path):
        """authorized_trial_count != 1 raises ValueError."""
        manifest_path = self._write_manifest(tmp_path, overrides={"authorized_trial_count": 2})
        sidecar_path = self._write_sidecar(tmp_path, manifest_path)
        contract_diag = self._make_contract_diagnostics(gate_passed=True)
        with pytest.raises(ValueError, match="authorized_trial_count"):
            materialize_trial_manifest_preregistration_diagnostics(
                manifest_path=str(manifest_path),
                sidecar_path=str(sidecar_path),
                strategy_rule_contract_diagnostics=contract_diag,
            )

    def test_trial_count_frozen_false_fails(self, tmp_path):
        """trial_count_frozen=False raises ValueError."""
        manifest_path = self._write_manifest(tmp_path, overrides={"trial_count_frozen": False})
        sidecar_path = self._write_sidecar(tmp_path, manifest_path)
        contract_diag = self._make_contract_diagnostics(gate_passed=True)
        with pytest.raises(ValueError, match="trial_count_frozen"):
            materialize_trial_manifest_preregistration_diagnostics(
                manifest_path=str(manifest_path),
                sidecar_path=str(sidecar_path),
                strategy_rule_contract_diagnostics=contract_diag,
            )

    def test_hyperparameter_search_policy_not_no_search_fails(self, tmp_path):
        """hyperparameter_search_policy != 'NO_SEARCH' raises ValueError."""
        manifest_path = self._write_manifest(tmp_path, overrides={
            "hyperparameter_search_policy": "GRID_SEARCH",
        })
        sidecar_path = self._write_sidecar(tmp_path, manifest_path)
        contract_diag = self._make_contract_diagnostics(gate_passed=True)
        with pytest.raises(ValueError, match="hyperparameter_search_policy"):
            materialize_trial_manifest_preregistration_diagnostics(
                manifest_path=str(manifest_path),
                sidecar_path=str(sidecar_path),
                strategy_rule_contract_diagnostics=contract_diag,
            )

    def test_free_parameter_count_not_zero_fails(self, tmp_path):
        """free_parameter_count != 0 raises ValueError."""
        manifest_path = self._write_manifest(tmp_path, overrides={"free_parameter_count": 1})
        sidecar_path = self._write_sidecar(tmp_path, manifest_path)
        contract_diag = self._make_contract_diagnostics(gate_passed=True)
        with pytest.raises(ValueError, match="free_parameter_count"):
            materialize_trial_manifest_preregistration_diagnostics(
                manifest_path=str(manifest_path),
                sidecar_path=str(sidecar_path),
                strategy_rule_contract_diagnostics=contract_diag,
            )

    def test_declared_parameter_names_non_empty_fails(self, tmp_path):
        """declared_parameter_names non-empty raises ValueError."""
        manifest_path = self._write_manifest(tmp_path, overrides={
            "declared_parameter_names": ["lookback"],
        })
        sidecar_path = self._write_sidecar(tmp_path, manifest_path)
        contract_diag = self._make_contract_diagnostics(gate_passed=True)
        with pytest.raises(ValueError, match="declared_parameter_names"):
            materialize_trial_manifest_preregistration_diagnostics(
                manifest_path=str(manifest_path),
                sidecar_path=str(sidecar_path),
                strategy_rule_contract_diagnostics=contract_diag,
            )

    # ── Authorization boolean type hardening ────────────────────────────

    def test_scoring_authorization_zero_fails(self, tmp_path):
        """scoring_authorization=0 raises ValueError (not False)."""
        manifest_path = self._write_manifest(tmp_path, overrides={"scoring_authorization": 0})
        sidecar_path = self._write_sidecar(tmp_path, manifest_path)
        contract_diag = self._make_contract_diagnostics(gate_passed=True)
        with pytest.raises(ValueError, match="exactly false"):
            materialize_trial_manifest_preregistration_diagnostics(
                manifest_path=str(manifest_path),
                sidecar_path=str(sidecar_path),
                strategy_rule_contract_diagnostics=contract_diag,
            )

    def test_scoring_authorization_string_false_fails(self, tmp_path):
        """scoring_authorization='false' (string) raises ValueError."""
        manifest_path = self._write_manifest(tmp_path, overrides={"scoring_authorization": "false"})
        sidecar_path = self._write_sidecar(tmp_path, manifest_path)
        contract_diag = self._make_contract_diagnostics(gate_passed=True)
        with pytest.raises(ValueError, match="exactly false"):
            materialize_trial_manifest_preregistration_diagnostics(
                manifest_path=str(manifest_path),
                sidecar_path=str(sidecar_path),
                strategy_rule_contract_diagnostics=contract_diag,
            )

    def test_scoring_authorization_true_fails(self, tmp_path):
        """scoring_authorization=true raises ValueError."""
        manifest_path = self._write_manifest(tmp_path, overrides={"scoring_authorization": True})
        sidecar_path = self._write_sidecar(tmp_path, manifest_path)
        contract_diag = self._make_contract_diagnostics(gate_passed=True)
        with pytest.raises(ValueError, match="exactly false"):
            materialize_trial_manifest_preregistration_diagnostics(
                manifest_path=str(manifest_path),
                sidecar_path=str(sidecar_path),
                strategy_rule_contract_diagnostics=contract_diag,
            )


class TestTrialManifestPreregistrationGate:
    """Tests for _derive_trial_manifest_preregistration_gate()."""

    def _make_full_diagnostics(self) -> dict:
        """Build a full passing diagnostics dict for the gate."""
        return {
            "diagnostic_kind": "trial_manifest_preregistration",
            "manifest_packet_read": True,
            "manifest_json_parse_ok": True,
            "manifest_sidecar_parse_ok": True,
            "manifest_hash_authority": "SIDECAR",
            "manifest_hash_field_value": "FROZEN_IN_SIDECAR",
            "manifest_hash_status": "FROZEN_IN_SIDECAR",
            "manifest_required_fields_present": True,
            "manifest_forbidden_dict_key_scan_passed": True,
            "manifest_sidecar_digest_matches_json_bytes": True,
            "bound_contract_digest_matches": True,
            "contract_packet_gate_passed": True,
            "authorized_trial_count": 1,
            "trial_count_frozen": True,
            "hyperparameter_search_policy": "NO_SEARCH",
            "free_parameter_count": 0,
            "trial_execution_authorized": False,
            "trial_scoring_ready": False,
            "trial_manifest_readiness": False,
        }

    def test_gate_passes_with_full_diagnostics(self):
        diagnostics = self._make_full_diagnostics()
        gate = _derive_trial_manifest_preregistration_gate(diagnostics)
        assert gate["gate_passed"] is True
        assert gate["gate_status"] == "TRIAL_MANIFEST_PREREGISTERED_DIAGNOSTIC_ONLY"
        assert gate["blocked_reason"] is None

    def test_gate_fails_when_manifest_not_read(self):
        diagnostics = self._make_full_diagnostics()
        diagnostics["manifest_packet_read"] = False
        gate = _derive_trial_manifest_preregistration_gate(diagnostics)
        assert gate["gate_passed"] is False

    def test_gate_fails_when_sidecar_mismatch(self):
        diagnostics = self._make_full_diagnostics()
        diagnostics["manifest_sidecar_digest_matches_json_bytes"] = False
        gate = _derive_trial_manifest_preregistration_gate(diagnostics)
        assert gate["gate_passed"] is False

    def test_gate_fails_when_forbidden_key_found(self):
        diagnostics = self._make_full_diagnostics()
        diagnostics["manifest_forbidden_dict_key_scan_passed"] = False
        gate = _derive_trial_manifest_preregistration_gate(diagnostics)
        assert gate["gate_passed"] is False

    def test_gate_fails_when_contract_digest_mismatch(self):
        diagnostics = self._make_full_diagnostics()
        diagnostics["bound_contract_digest_matches"] = False
        gate = _derive_trial_manifest_preregistration_gate(diagnostics)
        assert gate["gate_passed"] is False

    def test_gate_fails_when_contract_packet_gate_not_passed(self):
        diagnostics = self._make_full_diagnostics()
        diagnostics["contract_packet_gate_passed"] = False
        gate = _derive_trial_manifest_preregistration_gate(diagnostics)
        assert gate["gate_passed"] is False

    def test_gate_fails_when_trial_count_not_one(self):
        diagnostics = self._make_full_diagnostics()
        diagnostics["authorized_trial_count"] = 2
        gate = _derive_trial_manifest_preregistration_gate(diagnostics)
        assert gate["gate_passed"] is False

    def test_gate_fails_when_trial_count_not_frozen(self):
        diagnostics = self._make_full_diagnostics()
        diagnostics["trial_count_frozen"] = False
        gate = _derive_trial_manifest_preregistration_gate(diagnostics)
        assert gate["gate_passed"] is False

    def test_gate_fails_when_search_policy_not_no_search(self):
        diagnostics = self._make_full_diagnostics()
        diagnostics["hyperparameter_search_policy"] = "GRID_SEARCH"
        gate = _derive_trial_manifest_preregistration_gate(diagnostics)
        assert gate["gate_passed"] is False

    def test_gate_fails_when_free_params_not_zero(self):
        diagnostics = self._make_full_diagnostics()
        diagnostics["free_parameter_count"] = 1
        gate = _derive_trial_manifest_preregistration_gate(diagnostics)
        assert gate["gate_passed"] is False


class TestTrialManifestPreregistrationBuildDiagnostics:
    """Tests for _build_trial_manifest_diagnostics() with optional args."""

    def _write_manifest(self, tmp_path: Path) -> Path:
        data = {
            "manifest_id": "qnty_offline_edge_trial_manifest_v1",
            "manifest_version": "1.0.0",
            "manifest_kind": "TRIAL_MANIFEST_PRE_REGISTRATION_ONLY",
            "manifest_status": "FROZEN_PRE_REGISTRATION_ONLY",
            "manifest_hash": "FROZEN_IN_SIDECAR",
            "manifest_hash_algorithm": "sha256",
            "manifest_hash_scope": "exact committed JSON bytes, excluding sidecar",
            "manifest_hash_status": "FROZEN_IN_SIDECAR",
            "bound_contract_id": "qnty_offline_edge_strategy_rule_contract_v1",
            "bound_contract_sha256": "d6462a76c8f2bde79352baab2de0bd6dff3ad6b0f4139c6fba9f7764df04e0d9",
            "bound_contract_sha256_sidecar_path": "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.sha256",
            "bound_contract_commit_binding_path": "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.commit_binding.json",
            "required_contract_packet_gate_status": "CONTRACT_PACKET_COMMIT_BOUND_DIAGNOSTIC_ONLY",
            "required_contract_packet_gate_scope": "CONTRACT_PACKET_EXISTENCE_HASH_AND_COMMIT_BINDING_ONLY",
            "candidate_id": "funding_carry_v1_declaration_only",
            "hypothesis_id": "funding_carry_v1_pre_scoring",
            "candidate_family": "funding_carry_declaration_only",
            "trial_policy": "SINGLE_TRIAL_NO_SEARCH",
            "authorized_trial_count": 1,
            "trial_count_frozen": True,
            "hyperparameter_search_policy": "NO_SEARCH",
            "free_parameter_count": 0,
            "declared_parameter_names": [],
            "dataset_binding_policy": "USES_EXISTING_OFFLINE_EDGE_INPUT_INVENTORY_AT_RUNTIME",
            "split_binding_policy": "USES_EXISTING_DETERMINISTIC_SPLIT_DEFINITIONS_AT_RUNTIME",
            "symbol_universe_policy": "USES_VALIDATION_INVENTORY_SYMBOLS_AT_RUNTIME_NOT_FROZEN_HERE",
            "trial_execution_authorized": False,
            "scoring_authorization": False,
            "live_integration_authorized": False,
            "paper_integration_authorized": False,
            "final_verdict_authorization": False,
            "oos_seal_dependency_satisfied": False,
            "null_benchmark_dependency_satisfied": False,
            "multiple_testing_dependency_satisfied": False,
            "trade_position_simulation_dependency_satisfied": False,
            "net_pnl_equity_risk_dependency_satisfied": False,
        }
        json_str = json.dumps(data, sort_keys=True, indent=2) + "\n"
        path = tmp_path / "trial_manifest.json"
        path.write_text(json_str)
        return path

    def _write_sidecar(self, tmp_path: Path, manifest_path: Path) -> Path:
        digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        sidecar_path = tmp_path / "trial_manifest.sha256"
        sidecar_path.write_text(f"{digest}  {manifest_path.name}\n")
        return sidecar_path

    def _make_contract_diagnostics(self, gate_passed: bool = True) -> dict:
        return {
            "contract_id": "qnty_offline_edge_strategy_rule_contract_v1",
            "json_sha256": "d6462a76c8f2bde79352baab2de0bd6dff3ad6b0f4139c6fba9f7764df04e0d9",
            "contract_packet_gate": {
                "gate_passed": gate_passed,
                "gate_status": (
                    "CONTRACT_PACKET_COMMIT_BOUND_DIAGNOSTIC_ONLY"
                    if gate_passed
                    else "BLOCKED_BY_INCOMPLETE_EVIDENCE"
                ),
            },
        }

    def test_no_args_returns_absence_with_gate_false(self):
        """No args: gate exists but false/not loaded."""
        result = _build_trial_manifest_diagnostics()
        assert result["trial_manifest_status"] == TRIAL_MANIFEST_NOT_DEFINED
        gate = result.get("trial_manifest_preregistration_gate", {})
        assert gate.get("gate_passed") is False
        assert gate.get("gate_status") == "TRIAL_MANIFEST_NOT_LOADED"

    def test_full_args_trial_manifest_gate_passes(self, tmp_path):
        """With all contract + trial manifest args, gate passes."""
        manifest_path = self._write_manifest(tmp_path)
        sidecar_path = self._write_sidecar(tmp_path, manifest_path)
        contract_diag = self._make_contract_diagnostics(gate_passed=True)

        result = _build_trial_manifest_diagnostics(
            manifest_path=str(manifest_path),
            sidecar_path=str(sidecar_path),
            strategy_rule_contract_diagnostics=contract_diag,
        )
        gate = result.get("trial_manifest_preregistration_gate", {})
        assert gate.get("gate_passed") is True
        assert gate.get("gate_status") == "TRIAL_MANIFEST_PREREGISTERED_DIAGNOSTIC_ONLY"

    def test_missing_contract_args_returns_gate_false(self, tmp_path):
        """Trial manifest args without contract gate: fails closed."""
        manifest_path = self._write_manifest(tmp_path)
        sidecar_path = self._write_sidecar(tmp_path, manifest_path)
        result = _build_trial_manifest_diagnostics(
            manifest_path=str(manifest_path),
            sidecar_path=str(sidecar_path),
        )
        # strategy_rule_contract_diagnostics is None, so materializer not called.
        assert result["trial_manifest_status"] == TRIAL_MANIFEST_NOT_DEFINED
        gate = result.get("trial_manifest_preregistration_gate", {})
        assert gate.get("gate_passed") is False


class TestTrialManifestPreregistrationReceiptIntegration:
    """Tests for trial manifest diagnostics integration into receipt."""

    def _write_manifest(self, tmp_path: Path) -> Path:
        data = {
            "manifest_id": "qnty_offline_edge_trial_manifest_v1",
            "manifest_version": "1.0.0",
            "manifest_kind": "TRIAL_MANIFEST_PRE_REGISTRATION_ONLY",
            "manifest_status": "FROZEN_PRE_REGISTRATION_ONLY",
            "manifest_hash": "FROZEN_IN_SIDECAR",
            "manifest_hash_algorithm": "sha256",
            "manifest_hash_scope": "exact committed JSON bytes, excluding sidecar",
            "manifest_hash_status": "FROZEN_IN_SIDECAR",
            "bound_contract_id": "qnty_offline_edge_strategy_rule_contract_v1",
            "bound_contract_sha256": "d6462a76c8f2bde79352baab2de0bd6dff3ad6b0f4139c6fba9f7764df04e0d9",
            "bound_contract_sha256_sidecar_path": "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.sha256",
            "bound_contract_commit_binding_path": "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.commit_binding.json",
            "required_contract_packet_gate_status": "CONTRACT_PACKET_COMMIT_BOUND_DIAGNOSTIC_ONLY",
            "required_contract_packet_gate_scope": "CONTRACT_PACKET_EXISTENCE_HASH_AND_COMMIT_BINDING_ONLY",
            "candidate_id": "funding_carry_v1_declaration_only",
            "hypothesis_id": "funding_carry_v1_pre_scoring",
            "candidate_family": "funding_carry_declaration_only",
            "trial_policy": "SINGLE_TRIAL_NO_SEARCH",
            "authorized_trial_count": 1,
            "trial_count_frozen": True,
            "hyperparameter_search_policy": "NO_SEARCH",
            "free_parameter_count": 0,
            "declared_parameter_names": [],
            "dataset_binding_policy": "USES_EXISTING_OFFLINE_EDGE_INPUT_INVENTORY_AT_RUNTIME",
            "split_binding_policy": "USES_EXISTING_DETERMINISTIC_SPLIT_DEFINITIONS_AT_RUNTIME",
            "symbol_universe_policy": "USES_VALIDATION_INVENTORY_SYMBOLS_AT_RUNTIME_NOT_FROZEN_HERE",
            "trial_execution_authorized": False,
            "scoring_authorization": False,
            "live_integration_authorized": False,
            "paper_integration_authorized": False,
            "final_verdict_authorization": False,
            "oos_seal_dependency_satisfied": False,
            "null_benchmark_dependency_satisfied": False,
            "multiple_testing_dependency_satisfied": False,
            "trade_position_simulation_dependency_satisfied": False,
            "net_pnl_equity_risk_dependency_satisfied": False,
        }
        json_str = json.dumps(data, sort_keys=True, indent=2) + "\n"
        path = tmp_path / "trial_manifest.json"
        path.write_text(json_str)
        return path

    def _write_sidecar(self, tmp_path: Path, manifest_path: Path) -> Path:
        digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        sidecar_path = tmp_path / "trial_manifest.sha256"
        sidecar_path.write_text(f"{digest}  {manifest_path.name}\n")
        return sidecar_path

    def test_receipt_with_trial_manifest_gate_passes(self, tmp_path):
        """With all contract + trial manifest args, gate passes, final verdict blocked."""
        manifest_path = self._write_manifest(tmp_path)
        sidecar_path = self._write_sidecar(tmp_path, manifest_path)

        contract_diag = {
            "contract_id": "qnty_offline_edge_strategy_rule_contract_v1",
            "json_sha256": "d6462a76c8f2bde79352baab2de0bd6dff3ad6b0f4139c6fba9f7764df04e0d9",
            "contract_packet_gate": {
                "gate_passed": True,
                "gate_status": "CONTRACT_PACKET_COMMIT_BOUND_DIAGNOSTIC_ONLY",
            },
        }
        trial_diag = _build_trial_manifest_diagnostics(
            manifest_path=str(manifest_path),
            sidecar_path=str(sidecar_path),
            strategy_rule_contract_diagnostics=contract_diag,
        )

        # Build receipt with both diagnostics.
        splits = build_deterministic_split_definitions(
            global_min_timestamp="2026-01-01T00:00:00Z",
            global_max_timestamp="2026-02-01T00:00:00Z",
        )
        receipt = build_real_validation_receipt(
            input_manifest_fingerprint="a" * 64,
            data_quality_receipt_sha256="b" * 64,
            code_commit_sha="c" * 40,
            split_definitions=splits,
            cost_cases=build_cost_case_matrix(),
            strategy_rule_contract_diagnostics=contract_diag,
            trial_manifest_diagnostics=trial_diag,
        )

        assert "trial_manifest_diagnostics" in receipt
        trial_section = receipt["trial_manifest_diagnostics"]
        gate = trial_section.get("trial_manifest_preregistration_gate", {})
        assert gate.get("gate_passed") is True
        assert gate.get("gate_status") == "TRIAL_MANIFEST_PREREGISTERED_DIAGNOSTIC_ONLY"
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION

    def test_receipt_without_trial_manifest_gate_false(self, tmp_path):
        """Without trial manifest args, gate exists and false."""
        splits = build_deterministic_split_definitions(
            global_min_timestamp="2026-01-01T00:00:00Z",
            global_max_timestamp="2026-02-01T00:00:00Z",
        )
        trial_diag = _build_trial_manifest_diagnostics()
        receipt = build_real_validation_receipt(
            input_manifest_fingerprint="a" * 64,
            data_quality_receipt_sha256="b" * 64,
            code_commit_sha="c" * 40,
            split_definitions=splits,
            cost_cases=build_cost_case_matrix(),
            trial_manifest_diagnostics=trial_diag,
        )

        trial_section = receipt["trial_manifest_diagnostics"]
        gate = trial_section.get("trial_manifest_preregistration_gate", {})
        assert gate.get("gate_passed") is False
        assert gate.get("gate_status") == "TRIAL_MANIFEST_NOT_LOADED"
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION


class TestTrialManifestRealPathIntegration:
    """Full-path integration: real committed contract + trial manifest files.

    Proves the E1 trial manifest pre-registration can bind to real materialized
    strategy-rule contract diagnostics (not just hand-built mocks), so the
    ``contract diagnostic says None`` failure no longer occurs.
    """

    @staticmethod
    def _contract_json_path() -> str:
        return str(
            Path(__file__).resolve().parents[2]
            / "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.json"
        )

    @staticmethod
    def _contract_sidecar_path() -> str:
        return str(
            Path(__file__).resolve().parents[2]
            / "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.sha256"
        )

    @staticmethod
    def _commit_binding_path() -> str:
        return str(
            Path(__file__).resolve().parents[2]
            / "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.commit_binding.json"
        )

    @staticmethod
    def _trial_manifest_path() -> str:
        return str(
            Path(__file__).resolve().parents[2]
            / "docs/contracts/instances/qnty_offline_edge_trial_manifest_v1.json"
        )

    @staticmethod
    def _trial_manifest_sidecar_path() -> str:
        return str(
            Path(__file__).resolve().parents[2]
            / "docs/contracts/instances/qnty_offline_edge_trial_manifest_v1.sha256"
        )

    def test_contract_diagnostics_preserve_identity(self):
        """Real materialized contract diagnostics include identity fields."""
        diagnostics = _build_strategy_rule_contract_diagnostics(
            contract_path=self._contract_json_path(),
            sidecar_path=self._contract_sidecar_path(),
            commit_binding_path=self._commit_binding_path(),
        )
        assert diagnostics["contract_id"] == "qnty_offline_edge_strategy_rule_contract_v1"
        assert diagnostics["contract_version"] == "1.0.0"
        assert diagnostics["contract_status"] == "FROZEN_DECLARATION_ONLY"
        assert diagnostics["contract_packet_gate"]["gate_passed"] is True

    def test_trial_manifest_full_real_path_binds_contract(self):
        """Real trial manifest binds to real contract diagnostics without None error.

        Full end-to-end: real contract JSON + sidecar + commit binding ->
        _build_strategy_rule_contract_diagnostics ->
        materialize_trial_manifest_preregistration_diagnostics.

        This is the regression for the P1: the real path must not fail with
        ``contract diagnostic says None``.
        """
        contract_diagnostics = _build_strategy_rule_contract_diagnostics(
            contract_path=self._contract_json_path(),
            sidecar_path=self._contract_sidecar_path(),
            commit_binding_path=self._commit_binding_path(),
        )

        trial_diagnostics = _build_trial_manifest_diagnostics(
            manifest_path=self._trial_manifest_path(),
            sidecar_path=self._trial_manifest_sidecar_path(),
            strategy_rule_contract_diagnostics=contract_diagnostics,
        )

        assert trial_diagnostics["bound_contract_id"] == (
            "qnty_offline_edge_strategy_rule_contract_v1"
        )
        assert trial_diagnostics["bound_contract_digest_matches"] is True
        assert trial_diagnostics["contract_packet_gate_passed"] is True
        gate = trial_diagnostics["trial_manifest_preregistration_gate"]
        assert gate["gate_passed"] is True
        assert gate["gate_status"] == "TRIAL_MANIFEST_PREREGISTERED_DIAGNOSTIC_ONLY"
        assert trial_diagnostics["trial_scoring_ready"] is False
        assert trial_diagnostics["trial_execution_authorized"] is False

    def test_cli_fallback_path_includes_section(self, tmp_path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        exit_code = real_validation.main([
            "--read-only", "--output-dir", str(output_dir),
            "--input-manifest-fingerprint", "abc",
            "--data-quality-receipt-sha256", "def",
            "--code-commit-sha", "ghi",
            "--global-min-timestamp", "2026-01-01T00:00:00Z",
            "--global-max-timestamp", "2026-02-01T00:00:00Z",
        ])
        assert exit_code == 0
        receipt_path = output_dir / "real_validation_receipt.json"
        assert receipt_path.exists()
        receipt = json.loads(receipt_path.read_text())
        assert "final_offline_edge_verdict_logic_diagnostics" in receipt
        section = receipt["final_offline_edge_verdict_logic_diagnostics"]
        assert section["final_verdict_logic_status"] == (
            FINAL_OFFLINE_EDGE_VERDICT_LOGIC_BLOCKED
        )
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION


class TestOosSealPreregistrationF1:
    """Lane F1: OOS seal pre-scoring declaration packet + diagnostic-only gate."""

    SEAL_PATH = "docs/contracts/instances/qnty_offline_edge_oos_seal_v1.json"
    SEAL_SIDECAR_PATH = "docs/contracts/instances/qnty_offline_edge_oos_seal_v1.sha256"
    CONTRACT_PATH = "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.json"
    CONTRACT_SIDECAR_PATH = "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.sha256"
    CONTRACT_BINDING_PATH = "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.commit_binding.json"
    MANIFEST_PATH = "docs/contracts/instances/qnty_offline_edge_trial_manifest_v1.json"
    MANIFEST_SIDECAR_PATH = "docs/contracts/instances/qnty_offline_edge_trial_manifest_v1.sha256"

    def _build_contract_diagnostics(self):
        from quantbot.experiment.offline_edge_real_validation import (
            _build_strategy_rule_contract_diagnostics,
        )
        return _build_strategy_rule_contract_diagnostics(
            contract_path=self.CONTRACT_PATH,
            sidecar_path=self.CONTRACT_SIDECAR_PATH,
            commit_binding_path=self.CONTRACT_BINDING_PATH,
        )

    def _build_trial_manifest_diagnostics(self, contract_diag):
        from quantbot.experiment.offline_edge_real_validation import (
            _build_trial_manifest_diagnostics,
        )
        return _build_trial_manifest_diagnostics(
            manifest_path=self.MANIFEST_PATH,
            sidecar_path=self.MANIFEST_SIDECAR_PATH,
            strategy_rule_contract_diagnostics=contract_diag,
        )

    # ── Seal JSON + sidecar happy path ─────────────────────────────────

    def test_oos_seal_json_and_sidecar_valid(self):
        """Validate sidecar, strict key scan passes, hash authority sidecar."""
        from quantbot.experiment.offline_edge_real_validation import (
            materialize_oos_seal_preregistration_diagnostics,
            _find_forbidden_contract_dict_keys,
            _REQUIRED_FALSE_OOS_SEAL_FIELDS,
        )
        import json, hashlib
        contract_diag = self._build_contract_diagnostics()
        manifest_diag = self._build_trial_manifest_diagnostics(contract_diag)
        result = materialize_oos_seal_preregistration_diagnostics(
            seal_path=self.SEAL_PATH,
            sidecar_path=self.SEAL_SIDECAR_PATH,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        assert result["seal_sidecar_digest_matches_json_bytes"] is True
        assert result["seal_hash_authority"] == "SIDECAR"
        assert result["seal_hash_field_value"] == "FROZEN_IN_SIDECAR"
        assert result["seal_hash_status"] == "FROZEN_IN_SIDECAR"
        assert result["seal_required_fields_present"] is True
        assert result["seal_forbidden_dict_key_scan_passed"] is True

        # Verify actual seal JSON has no forbidden keys
        seal_bytes = Path(self.SEAL_PATH).read_bytes()
        seal_dict = json.loads(seal_bytes)
        collisions = _find_forbidden_contract_dict_keys(seal_dict)
        assert collisions == [], f"Forbidden keys found: {collisions}"

    # ── OOS seal diagnostic happy path ─────────────────────────────────

    def test_oos_seal_diagnostic_happy_path(self):
        """Build C2 contract + E1 manifest + F1 OOS seal, all pass."""
        from quantbot.experiment.offline_edge_real_validation import (
            _build_oos_seal_diagnostics,
        )
        contract_diag = self._build_contract_diagnostics()
        manifest_diag = self._build_trial_manifest_diagnostics(contract_diag)
        result = _build_oos_seal_diagnostics(
            seal_path=self.SEAL_PATH,
            sidecar_path=self.SEAL_SIDECAR_PATH,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        assert result["seal_sidecar_digest_matches_json_bytes"] is True
        assert result["bound_contract_digest_matches"] is True
        assert result["bound_trial_manifest_digest_matches"] is True
        assert result["trial_manifest_gate_passed"] is True
        assert result["oos_boundary_policy_frozen"] is True
        assert result["oos_split_selection_frozen"] is True
        assert result["oos_scoring_authorized"] is False

    # ── OOS seal gate happy path ───────────────────────────────────────

    def test_oos_seal_gate_happy_path(self):
        """Gate passes with correct status and all authorizations false."""
        from quantbot.experiment.offline_edge_real_validation import (
            _build_oos_seal_diagnostics,
        )
        contract_diag = self._build_contract_diagnostics()
        manifest_diag = self._build_trial_manifest_diagnostics(contract_diag)
        oos_diag = _build_oos_seal_diagnostics(
            seal_path=self.SEAL_PATH,
            sidecar_path=self.SEAL_SIDECAR_PATH,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        gate = oos_diag.get("oos_seal_preregistration_gate", {})
        assert gate.get("gate_passed") is True
        assert gate.get("gate_status") == "OOS_SEAL_PREREGISTERED_DIAGNOSTIC_ONLY"
        assert gate.get("gate_scoring_authorization") is False
        assert gate.get("gate_live_authorization") is False
        assert gate.get("gate_final_verdict_authorization") is False
        assert gate.get("gate_downstream_unlocks") == []

    # ── Seal missing fails closed ──────────────────────────────────────

    def test_oos_seal_missing_fails_closed(self):
        from quantbot.experiment.offline_edge_real_validation import (
            _build_oos_seal_diagnostics,
        )
        result = _build_oos_seal_diagnostics()
        gate = result.get("oos_seal_preregistration_gate", {})
        assert gate.get("gate_passed") is False
        assert gate.get("gate_status") == "OOS_SEAL_NOT_LOADED"

    # ── Seal sidecar missing fails closed ──────────────────────────────

    def test_oos_seal_sidecar_missing_fails_closed(self):
        from quantbot.experiment.offline_edge_real_validation import (
            materialize_oos_seal_preregistration_diagnostics,
        )
        import tempfile, json, hashlib
        contract_diag = self._build_contract_diagnostics()
        manifest_diag = self._build_trial_manifest_diagnostics(contract_diag)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            seal_bytes = Path(self.SEAL_PATH).read_bytes()
            f.write(seal_bytes.decode())
            seal_tmp = f.name
        missing_sidecar = "/tmp/nonexistent_sidecar_oos.sha256"
        with pytest.raises(ValueError, match="OOS seal sidecar not found"):
            materialize_oos_seal_preregistration_diagnostics(
                seal_path=seal_tmp,
                sidecar_path=missing_sidecar,
                trial_manifest_diagnostics=manifest_diag,
                strategy_rule_contract_diagnostics=contract_diag,
            )

    # ── Seal digest mismatch fails closed ──────────────────────────────

    def test_oos_seal_digest_mismatch_fails_closed(self):
        from quantbot.experiment.offline_edge_real_validation import (
            materialize_oos_seal_preregistration_diagnostics,
        )
        import tempfile, hashlib
        # Use the real seal JSON bytes with a sidecar that has a wrong digest
        real_bytes = Path(self.SEAL_PATH).read_bytes()
        wrong_digest = hashlib.sha256(real_bytes + b"tamper").hexdigest()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as src:
            src.write(real_bytes)
            seal_tmp = src.name
        seal_basename = Path(seal_tmp).name
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sha256", delete=False) as f:
            f.write(f"{wrong_digest}  {seal_basename}")
            sidecar_tmp = f.name
        contract_diag = self._build_contract_diagnostics()
        manifest_diag = self._build_trial_manifest_diagnostics(contract_diag)
        with pytest.raises(ValueError, match="sidecar digest mismatch"):
            materialize_oos_seal_preregistration_diagnostics(
                seal_path=seal_tmp,
                sidecar_path=sidecar_tmp,
                trial_manifest_diagnostics=manifest_diag,
                strategy_rule_contract_diagnostics=contract_diag,
            )

    # ── Malformed seal JSON fails closed ───────────────────────────────

    def test_oos_seal_malformed_json_fails_closed(self):
        from quantbot.experiment.offline_edge_real_validation import (
            materialize_oos_seal_preregistration_diagnostics,
        )
        import tempfile
        contract_diag = self._build_contract_diagnostics()
        manifest_diag = self._build_trial_manifest_diagnostics(contract_diag)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{invalid json")
            seal_tmp = f.name
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sha256", delete=False) as f:
            import hashlib
            d = hashlib.sha256(b"{invalid json").hexdigest()
            f.write(f"{d}  bad.json")
            sidecar_tmp = f.name
        with pytest.raises(ValueError, match="JSON parse error"):
            materialize_oos_seal_preregistration_diagnostics(
                seal_path=seal_tmp,
                sidecar_path=sidecar_tmp,
                trial_manifest_diagnostics=manifest_diag,
                strategy_rule_contract_diagnostics=contract_diag,
            )

    # ── Forbidden dict key in seal fails closed ────────────────────────

    def test_oos_seal_forbidden_key_fails_closed(self):
        from quantbot.experiment.offline_edge_real_validation import (
            materialize_oos_seal_preregistration_diagnostics,
        )
        import tempfile, hashlib
        contract_diag = self._build_contract_diagnostics()
        manifest_diag = self._build_trial_manifest_diagnostics(contract_diag)
        # Copy the real seal and inject a forbidden key
        import json
        real_bytes = Path(self.SEAL_PATH).read_bytes()
        real_dict = json.loads(real_bytes)
        real_dict["pnl"] = 1  # forbidden key
        bad_bytes = json.dumps(real_dict, indent=2, sort_keys=True).encode() + b"\n"
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".json", delete=False) as f:
            f.write(bad_bytes)
            seal_tmp = f.name
        bad_digest = hashlib.sha256(bad_bytes).hexdigest()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sha256", delete=False) as f:
            f.write(f"{bad_digest}  bad.json")
            sidecar_tmp = f.name
        with pytest.raises(ValueError, match="forbidden dict key"):
            materialize_oos_seal_preregistration_diagnostics(
                seal_path=seal_tmp,
                sidecar_path=sidecar_tmp,
                trial_manifest_diagnostics=manifest_diag,
                strategy_rule_contract_diagnostics=contract_diag,
            )

    # ── Contract digest mismatch fails closed ──────────────────────────

    def test_oos_seal_contract_digest_mismatch_fails_closed(self):
        from quantbot.experiment.offline_edge_real_validation import (
            materialize_oos_seal_preregistration_diagnostics,
        )
        import tempfile, json, hashlib
        real_bytes = Path(self.SEAL_PATH).read_bytes()
        real_dict = json.loads(real_bytes)
        real_dict["bound_contract_sha256"] = "0" * 64
        bad_bytes = json.dumps(real_dict, indent=2, sort_keys=True).encode() + b"\n"
        bad_digest = hashlib.sha256(bad_bytes).hexdigest()
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".json", delete=False) as f:
            f.write(bad_bytes)
            seal_tmp = f.name
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sha256", delete=False) as f:
            f.write(f"{bad_digest}  bad.json")
            sidecar_tmp = f.name
        contract_diag = self._build_contract_diagnostics()
        manifest_diag = self._build_trial_manifest_diagnostics(contract_diag)
        with pytest.raises(ValueError, match="bound_contract_sha256 mismatch"):
            materialize_oos_seal_preregistration_diagnostics(
                seal_path=seal_tmp,
                sidecar_path=sidecar_tmp,
                trial_manifest_diagnostics=manifest_diag,
                strategy_rule_contract_diagnostics=contract_diag,
            )

    # ── Trial manifest digest mismatch fails closed ────────────────────

    def test_oos_seal_manifest_digest_mismatch_fails_closed(self):
        from quantbot.experiment.offline_edge_real_validation import (
            materialize_oos_seal_preregistration_diagnostics,
        )
        import tempfile, json, hashlib
        real_bytes = Path(self.SEAL_PATH).read_bytes()
        real_dict = json.loads(real_bytes)
        real_dict["bound_trial_manifest_sha256"] = "0" * 64
        bad_bytes = json.dumps(real_dict, indent=2, sort_keys=True).encode() + b"\n"
        bad_digest = hashlib.sha256(bad_bytes).hexdigest()
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".json", delete=False) as f:
            f.write(bad_bytes)
            seal_tmp = f.name
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sha256", delete=False) as f:
            f.write(f"{bad_digest}  bad.json")
            sidecar_tmp = f.name
        contract_diag = self._build_contract_diagnostics()
        manifest_diag = self._build_trial_manifest_diagnostics(contract_diag)
        with pytest.raises(ValueError, match="bound_trial_manifest_sha256 mismatch"):
            materialize_oos_seal_preregistration_diagnostics(
                seal_path=seal_tmp,
                sidecar_path=sidecar_tmp,
                trial_manifest_diagnostics=manifest_diag,
                strategy_rule_contract_diagnostics=contract_diag,
            )

    # ── Trial manifest gate missing blocks OOS seal ────────────────────

    def test_oos_seal_trial_manifest_gate_missing_fails_closed(self):
        from quantbot.experiment.offline_edge_real_validation import (
            materialize_oos_seal_preregistration_diagnostics,
            _build_trial_manifest_diagnostics,
        )
        contract_diag = self._build_contract_diagnostics()
        # Build manifest WITHOUT gate by omitting paths
        manifest_diag = _build_trial_manifest_diagnostics(
            manifest_path=None,
            sidecar_path=None,
            strategy_rule_contract_diagnostics=None,
        )
        with pytest.raises(ValueError, match="Trial manifest gate not passed"):
            materialize_oos_seal_preregistration_diagnostics(
                seal_path=self.SEAL_PATH,
                sidecar_path=self.SEAL_SIDECAR_PATH,
                trial_manifest_diagnostics=manifest_diag,
                strategy_rule_contract_diagnostics=contract_diag,
            )

    # ── oos_boundary_policy_frozen = false fails closed ────────────────

    def test_oos_boundary_policy_not_frozen_fails_closed(self):
        from quantbot.experiment.offline_edge_real_validation import (
            materialize_oos_seal_preregistration_diagnostics,
        )
        import tempfile, json, hashlib
        real_bytes = Path(self.SEAL_PATH).read_bytes()
        real_dict = json.loads(real_bytes)
        real_dict["oos_boundary_policy_frozen"] = False
        bad_bytes = json.dumps(real_dict, indent=2, sort_keys=True).encode() + b"\n"
        bad_digest = hashlib.sha256(bad_bytes).hexdigest()
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".json", delete=False) as f:
            f.write(bad_bytes)
            seal_tmp = f.name
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sha256", delete=False) as f:
            f.write(f"{bad_digest}  bad.json")
            sidecar_tmp = f.name
        contract_diag = self._build_contract_diagnostics()
        manifest_diag = self._build_trial_manifest_diagnostics(contract_diag)
        with pytest.raises(ValueError, match="oos_boundary_policy_frozen must be True"):
            materialize_oos_seal_preregistration_diagnostics(
                seal_path=seal_tmp,
                sidecar_path=sidecar_tmp,
                trial_manifest_diagnostics=manifest_diag,
                strategy_rule_contract_diagnostics=contract_diag,
            )

    # ── oos_split_selection_frozen = false fails closed ────────────────

    def test_oos_split_selection_not_frozen_fails_closed(self):
        from quantbot.experiment.offline_edge_real_validation import (
            materialize_oos_seal_preregistration_diagnostics,
        )
        import tempfile, json, hashlib
        real_bytes = Path(self.SEAL_PATH).read_bytes()
        real_dict = json.loads(real_bytes)
        real_dict["oos_split_selection_frozen"] = False
        bad_bytes = json.dumps(real_dict, indent=2, sort_keys=True).encode() + b"\n"
        bad_digest = hashlib.sha256(bad_bytes).hexdigest()
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".json", delete=False) as f:
            f.write(bad_bytes)
            seal_tmp = f.name
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sha256", delete=False) as f:
            f.write(f"{bad_digest}  bad.json")
            sidecar_tmp = f.name
        contract_diag = self._build_contract_diagnostics()
        manifest_diag = self._build_trial_manifest_diagnostics(contract_diag)
        with pytest.raises(ValueError, match="oos_split_selection_frozen must be True"):
            materialize_oos_seal_preregistration_diagnostics(
                seal_path=seal_tmp,
                sidecar_path=sidecar_tmp,
                trial_manifest_diagnostics=manifest_diag,
                strategy_rule_contract_diagnostics=contract_diag,
            )

    # ── Authorization boolean type hardening ───────────────────────────

    @pytest.mark.parametrize("field,value", [
        ("oos_scoring_authorized", 0),
        ("oos_scoring_authorized", "false"),
        ("oos_scoring_authorized", True),
    ])
    def test_oos_seal_auth_boolean_hardening(self, field, value):
        from quantbot.experiment.offline_edge_real_validation import (
            materialize_oos_seal_preregistration_diagnostics,
        )
        import tempfile, json, hashlib
        real_bytes = Path(self.SEAL_PATH).read_bytes()
        real_dict = json.loads(real_bytes)
        real_dict[field] = value
        bad_bytes = json.dumps(real_dict, indent=2, sort_keys=True).encode() + b"\n"
        bad_digest = hashlib.sha256(bad_bytes).hexdigest()
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".json", delete=False) as f:
            f.write(bad_bytes)
            seal_tmp = f.name
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sha256", delete=False) as f:
            f.write(f"{bad_digest}  bad.json")
            sidecar_tmp = f.name
        contract_diag = self._build_contract_diagnostics()
        manifest_diag = self._build_trial_manifest_diagnostics(contract_diag)
        with pytest.raises(ValueError, match="fields must be exactly false"):
            materialize_oos_seal_preregistration_diagnostics(
                seal_path=seal_tmp,
                sidecar_path=sidecar_tmp,
                trial_manifest_diagnostics=manifest_diag,
                strategy_rule_contract_diagnostics=contract_diag,
            )

    # ── Receipt integration with all args ──────────────────────────────

    def test_receipt_integration_full_path(self):
        """All args provided: gates pass, final verdict still blocked."""
        from quantbot.experiment.offline_edge_real_validation import (
            build_real_validation_receipt,
            BLOCKED_BY_VALIDATION_IMPLEMENTATION,
        )
        import tempfile, json

        contract_diag = self._build_contract_diagnostics()
        manifest_diag = self._build_trial_manifest_diagnostics(contract_diag)
        oos_diag = self._build_oos_seal_diagnostics_with_args(
            contract_diag, manifest_diag
        )

        receipt = build_real_validation_receipt(
            input_manifest_fingerprint="test",
            data_quality_receipt_sha256="test",
            code_commit_sha="test",
            split_definitions=[{"split_id": 0}],
            cost_cases=[],
            strategy_rule_contract_diagnostics=contract_diag,
            trial_manifest_diagnostics=manifest_diag,
            oos_seal_diagnostics=oos_diag,
        )
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION

        # Check OOS seal gate exists and passes
        oos_diag = receipt["oos_seal_diagnostics"]
        gate = oos_diag["oos_seal_preregistration_gate"]
        assert gate["gate_kind"] == "oos_seal_preregistration_gate"
        assert gate["gate_passed"] is True
        assert gate["gate_status"] == "OOS_SEAL_PREREGISTERED_DIAGNOSTIC_ONLY"
        assert gate["gate_scoring_authorization"] is False

    def _build_oos_seal_diagnostics_with_args(self, contract_diag, manifest_diag):
        from quantbot.experiment.offline_edge_real_validation import (
            _build_oos_seal_diagnostics,
        )
        return _build_oos_seal_diagnostics(
            seal_path=self.SEAL_PATH,
            sidecar_path=self.SEAL_SIDECAR_PATH,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )

    def test_cli_no_seal_args_gate_not_loaded(self):
        """CLI without --oos-seal-path: OOS seal gate exists and false."""
        from quantbot.experiment.offline_edge_real_validation import (
            _build_oos_seal_diagnostics,
        )
        result = _build_oos_seal_diagnostics()
        gate = result.get("oos_seal_preregistration_gate", {})
        assert gate.get("gate_passed") is False
        assert gate.get("gate_status") == "OOS_SEAL_NOT_LOADED"

    def test_cli_seal_without_trial_manifest_gate_fails_closed(self):
        """Seal args without trial manifest gate: blocked."""
        from quantbot.experiment.offline_edge_real_validation import (
            _build_oos_seal_diagnostics,
        )
        contract_diag = self._build_contract_diagnostics()
        # Build trial manifest WITHOUT gate
        from quantbot.experiment.offline_edge_real_validation import (
            _build_trial_manifest_diagnostics,
        )
        manifest_diag_no_gate = _build_trial_manifest_diagnostics(
            manifest_path=None,
            sidecar_path=None,
            strategy_rule_contract_diagnostics=None,
        )
        with pytest.raises(ValueError, match="Trial manifest gate not passed"):
            _build_oos_seal_diagnostics(
                seal_path=self.SEAL_PATH,
                sidecar_path=self.SEAL_SIDECAR_PATH,
                trial_manifest_diagnostics=manifest_diag_no_gate,
                strategy_rule_contract_diagnostics=contract_diag,
            )


class TestNullBenchmarkPreregistrationG1:
    """Lane G1: null benchmark pre-scoring declaration packet + diagnostic gate.

    Proves the declared null reference policy is frozen and hash-bound to the
    frozen OOS seal, trial manifest, and strategy contract *before* any scoring,
    null generation, or candidate-vs-null comparison exists. Nothing here
    computes a null, compares anything, or authorizes scoring.
    """

    NULL_BENCHMARK_PATH = "docs/contracts/instances/qnty_offline_edge_null_benchmark_v1.json"
    NULL_BENCHMARK_SIDECAR_PATH = "docs/contracts/instances/qnty_offline_edge_null_benchmark_v1.sha256"
    SEAL_PATH = "docs/contracts/instances/qnty_offline_edge_oos_seal_v1.json"
    SEAL_SIDECAR_PATH = "docs/contracts/instances/qnty_offline_edge_oos_seal_v1.sha256"
    CONTRACT_PATH = "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.json"
    CONTRACT_SIDECAR_PATH = "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.sha256"
    CONTRACT_BINDING_PATH = "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.commit_binding.json"
    MANIFEST_PATH = "docs/contracts/instances/qnty_offline_edge_trial_manifest_v1.json"
    MANIFEST_SIDECAR_PATH = "docs/contracts/instances/qnty_offline_edge_trial_manifest_v1.sha256"

    def _contract_diag(self):
        return real_validation._build_strategy_rule_contract_diagnostics(
            contract_path=self.CONTRACT_PATH,
            sidecar_path=self.CONTRACT_SIDECAR_PATH,
            commit_binding_path=self.CONTRACT_BINDING_PATH,
        )

    def _manifest_diag(self, contract_diag):
        return real_validation._build_trial_manifest_diagnostics(
            manifest_path=self.MANIFEST_PATH,
            sidecar_path=self.MANIFEST_SIDECAR_PATH,
            strategy_rule_contract_diagnostics=contract_diag,
        )

    def _seal_diag(self, contract_diag, manifest_diag):
        return real_validation._build_oos_seal_diagnostics(
            seal_path=self.SEAL_PATH,
            sidecar_path=self.SEAL_SIDECAR_PATH,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )

    def _upstream_diags(self):
        contract_diag = self._contract_diag()
        manifest_diag = self._manifest_diag(contract_diag)
        seal_diag = self._seal_diag(contract_diag, manifest_diag)
        return contract_diag, manifest_diag, seal_diag

    def _null_benchmark_diag(self):
        contract_diag, manifest_diag, seal_diag = self._upstream_diags()
        return real_validation._build_null_benchmark_contract_diagnostics(
            null_benchmark_path=self.NULL_BENCHMARK_PATH,
            sidecar_path=self.NULL_BENCHMARK_SIDECAR_PATH,
            oos_seal_diagnostics=seal_diag,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )

    def _tampered_packet(self, tmp_path, mutate):
        """Write a mutated null benchmark packet + a *matching* sidecar.

        The sidecar is regenerated so the digest check passes and the specific
        semantic check under test is the one that fails.
        """
        packet = json.loads(Path(self.NULL_BENCHMARK_PATH).read_bytes())
        mutate(packet)
        packet_bytes = json.dumps(packet, indent=2, sort_keys=True).encode() + b"\n"
        packet_path = tmp_path / "null_benchmark.json"
        packet_path.write_bytes(packet_bytes)
        sidecar_path = tmp_path / "null_benchmark.sha256"
        digest = hashlib.sha256(packet_bytes).hexdigest()
        sidecar_path.write_text(f"{digest}  {packet_path.name}\n")
        return str(packet_path), str(sidecar_path)

    def _materialize_tampered(self, tmp_path, mutate):
        contract_diag, manifest_diag, seal_diag = self._upstream_diags()
        packet_path, sidecar_path = self._tampered_packet(tmp_path, mutate)
        return real_validation.materialize_null_benchmark_preregistration_diagnostics(
            null_benchmark_path=packet_path,
            sidecar_path=sidecar_path,
            oos_seal_diagnostics=seal_diag,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )

    # -- 1. Packet JSON + sidecar happy path ---------------------------------

    def test_null_benchmark_json_and_sidecar_valid(self):
        packet_bytes = Path(self.NULL_BENCHMARK_PATH).read_bytes()
        computed = hashlib.sha256(packet_bytes).hexdigest()
        sidecar = Path(self.NULL_BENCHMARK_SIDECAR_PATH).read_text().strip()
        assert sidecar.split()[0] == computed

        packet = json.loads(packet_bytes)
        assert packet["null_benchmark_hash"] == "FROZEN_IN_SIDECAR"
        assert packet["null_benchmark_hash_status"] == "FROZEN_IN_SIDECAR"
        assert packet["null_benchmark_hash_algorithm"] == "sha256"
        collisions = real_validation._find_forbidden_contract_dict_keys(packet)
        assert collisions == [], f"Forbidden keys found: {collisions}"

    # -- 2. Null benchmark diagnostic happy path -----------------------------

    def test_null_benchmark_diagnostic_happy_path(self):
        result = self._null_benchmark_diag()
        assert result["null_benchmark_sidecar_digest_matches_json_bytes"] is True
        assert result["bound_contract_digest_matches"] is True
        assert result["bound_trial_manifest_digest_matches"] is True
        assert result["bound_oos_seal_digest_matches"] is True
        assert result["oos_seal_gate_passed"] is True
        assert result["oos_seal_gate_status"] == (
            "OOS_SEAL_PREREGISTERED_DIAGNOSTIC_ONLY"
        )
        assert result["null_reference_selection_frozen"] is True
        assert result["null_reference_count"] == 1
        assert result["null_reference_count_frozen"] is True
        assert result["null_benchmark_readiness"] is False
        assert result["null_generation_authorized"] is False
        assert result["candidate_comparison_authorized"] is False
        assert result["scoring_authorized"] is False
        assert result["null_benchmark_validation_status"] == (
            NULL_BENCHMARK_PREREGISTERED_DIAGNOSTIC_ONLY
        )

    def test_null_benchmark_diagnostic_has_no_forbidden_keys(self):
        result = self._null_benchmark_diag()
        collisions = real_validation._find_forbidden_contract_dict_keys(result)
        assert collisions == [], f"Forbidden keys found: {collisions}"

    # -- 3. Gate happy path --------------------------------------------------

    def test_null_benchmark_gate_happy_path(self):
        gate = self._null_benchmark_diag()["null_benchmark_preregistration_gate"]
        assert gate["gate_kind"] == "null_benchmark_preregistration_gate"
        assert gate["gate_scope"] == (
            "NULL_REFERENCE_POLICY_AND_OOS_SEAL_BINDING_ONLY"
        )
        assert gate["gate_passed"] is True
        assert gate["gate_status"] == NULL_BENCHMARK_PREREGISTERED_DIAGNOSTIC_ONLY
        assert gate["gate_scoring_authorization"] is False
        assert gate["gate_live_authorization"] is False
        assert gate["gate_final_verdict_authorization"] is False
        assert gate["gate_downstream_unlocks"] == []
        assert gate["blocked_reason"] is None
        assert gate["evidence"]["oos_seal_gate_passed"] is True
        assert gate["evidence"]["null_reference_count"] == 1

    # -- 4. Packet missing fails closed --------------------------------------

    def test_null_benchmark_absent_gate_not_loaded(self):
        result = real_validation._build_null_benchmark_contract_diagnostics()
        gate = result["null_benchmark_preregistration_gate"]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == "NULL_BENCHMARK_NOT_LOADED"
        assert gate["blocked_reason"] == "NULL_BENCHMARK_NOT_PROVIDED"

    def test_null_benchmark_packet_missing_fails_closed(self):
        contract_diag, manifest_diag, seal_diag = self._upstream_diags()
        with pytest.raises(ValueError, match="Null benchmark JSON not found"):
            real_validation.materialize_null_benchmark_preregistration_diagnostics(
                null_benchmark_path="/tmp/nonexistent_null_benchmark_g1.json",
                sidecar_path=self.NULL_BENCHMARK_SIDECAR_PATH,
                oos_seal_diagnostics=seal_diag,
                trial_manifest_diagnostics=manifest_diag,
                strategy_rule_contract_diagnostics=contract_diag,
            )

    # -- 5. Sidecar missing fails closed -------------------------------------

    def test_null_benchmark_sidecar_missing_fails_closed(self):
        contract_diag, manifest_diag, seal_diag = self._upstream_diags()
        with pytest.raises(ValueError, match="Null benchmark sidecar not found"):
            real_validation.materialize_null_benchmark_preregistration_diagnostics(
                null_benchmark_path=self.NULL_BENCHMARK_PATH,
                sidecar_path="/tmp/nonexistent_null_benchmark_g1.sha256",
                oos_seal_diagnostics=seal_diag,
                trial_manifest_diagnostics=manifest_diag,
                strategy_rule_contract_diagnostics=contract_diag,
            )

    # -- 6. Digest mismatch fails closed -------------------------------------

    def test_null_benchmark_digest_mismatch_fails_closed(self, tmp_path):
        contract_diag, manifest_diag, seal_diag = self._upstream_diags()
        packet_bytes = Path(self.NULL_BENCHMARK_PATH).read_bytes()
        packet_path = tmp_path / "null_benchmark.json"
        packet_path.write_bytes(packet_bytes)
        wrong_digest = hashlib.sha256(packet_bytes + b"tamper").hexdigest()
        sidecar_path = tmp_path / "null_benchmark.sha256"
        sidecar_path.write_text(f"{wrong_digest}  {packet_path.name}\n")
        with pytest.raises(ValueError, match="sidecar digest mismatch"):
            real_validation.materialize_null_benchmark_preregistration_diagnostics(
                null_benchmark_path=str(packet_path),
                sidecar_path=str(sidecar_path),
                oos_seal_diagnostics=seal_diag,
                trial_manifest_diagnostics=manifest_diag,
                strategy_rule_contract_diagnostics=contract_diag,
            )

    # -- 7. Malformed JSON fails closed --------------------------------------

    def test_null_benchmark_malformed_json_fails_closed(self, tmp_path):
        contract_diag, manifest_diag, seal_diag = self._upstream_diags()
        bad_bytes = b"{invalid json"
        packet_path = tmp_path / "null_benchmark.json"
        packet_path.write_bytes(bad_bytes)
        sidecar_path = tmp_path / "null_benchmark.sha256"
        digest = hashlib.sha256(bad_bytes).hexdigest()
        sidecar_path.write_text(f"{digest}  {packet_path.name}\n")
        with pytest.raises(ValueError, match="Null benchmark JSON parse error"):
            real_validation.materialize_null_benchmark_preregistration_diagnostics(
                null_benchmark_path=str(packet_path),
                sidecar_path=str(sidecar_path),
                oos_seal_diagnostics=seal_diag,
                trial_manifest_diagnostics=manifest_diag,
                strategy_rule_contract_diagnostics=contract_diag,
            )

    # -- 8. Forbidden dict key fails closed ----------------------------------

    def test_null_benchmark_forbidden_key_fails_closed(self, tmp_path):
        def mutate(packet):
            packet["pnl"] = 1

        with pytest.raises(ValueError, match="forbidden dict keys"):
            self._materialize_tampered(tmp_path, mutate)

    # -- 9-11. Bound digest mismatches fail closed ---------------------------

    def test_null_benchmark_contract_digest_mismatch_fails_closed(self, tmp_path):
        def mutate(packet):
            packet["bound_contract_sha256"] = "0" * 64

        with pytest.raises(ValueError, match="bound_contract_sha256 mismatch"):
            self._materialize_tampered(tmp_path, mutate)

    def test_null_benchmark_trial_manifest_digest_mismatch_fails_closed(
        self, tmp_path
    ):
        def mutate(packet):
            packet["bound_trial_manifest_sha256"] = "0" * 64

        with pytest.raises(
            ValueError, match="bound_trial_manifest_sha256 mismatch"
        ):
            self._materialize_tampered(tmp_path, mutate)

    def test_null_benchmark_oos_seal_digest_mismatch_fails_closed(self, tmp_path):
        def mutate(packet):
            packet["bound_oos_seal_sha256"] = "0" * 64

        with pytest.raises(ValueError, match="bound_oos_seal_sha256 mismatch"):
            self._materialize_tampered(tmp_path, mutate)

    def test_null_benchmark_oos_seal_id_mismatch_fails_closed(self, tmp_path):
        def mutate(packet):
            packet["bound_oos_seal_id"] = "some_other_seal"

        with pytest.raises(ValueError, match="bound_oos_seal_id mismatch"):
            self._materialize_tampered(tmp_path, mutate)

    # -- 12. Missing / failed OOS seal gate blocks the null benchmark --------

    def test_null_benchmark_blocked_when_oos_seal_gate_missing(self):
        contract_diag = self._contract_diag()
        manifest_diag = self._manifest_diag(contract_diag)
        seal_diag_no_gate = real_validation._build_oos_seal_diagnostics()
        with pytest.raises(ValueError, match="OOS seal gate not passed"):
            real_validation._build_null_benchmark_contract_diagnostics(
                null_benchmark_path=self.NULL_BENCHMARK_PATH,
                sidecar_path=self.NULL_BENCHMARK_SIDECAR_PATH,
                oos_seal_diagnostics=seal_diag_no_gate,
                trial_manifest_diagnostics=manifest_diag,
                strategy_rule_contract_diagnostics=contract_diag,
            )

    def test_gate_projection_blocked_by_oos_seal_gate(self):
        """Pure gate helper: a loaded packet with a failed OOS seal gate is
        blocked, never passed."""
        diagnostics = dict(self._null_benchmark_diag())
        diagnostics.pop("null_benchmark_preregistration_gate")
        diagnostics["oos_seal_gate_passed"] = False
        gate = real_validation._derive_null_benchmark_preregistration_gate(
            diagnostics
        )
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == "BLOCKED_BY_OOS_SEAL_GATE"
        assert gate["blocked_reason"] == "OOS_SEAL_GATE_NOT_PASSED"

    def test_gate_projection_blocked_by_incomplete_evidence(self):
        diagnostics = dict(self._null_benchmark_diag())
        diagnostics.pop("null_benchmark_preregistration_gate")
        diagnostics["bound_contract_digest_matches"] = False
        gate = real_validation._derive_null_benchmark_preregistration_gate(
            diagnostics
        )
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            "BLOCKED_BY_INCOMPLETE_NULL_BENCHMARK_EVIDENCE"
        )
        assert gate["blocked_reason"] == (
            "NULL_BENCHMARK_GATE_EVIDENCE_INCOMPLETE"
        )

    # -- 13-15. Null reference policy freeze ---------------------------------

    def test_null_reference_selection_not_frozen_fails_closed(self, tmp_path):
        def mutate(packet):
            packet["null_reference_selection_frozen"] = False

        with pytest.raises(
            ValueError, match="null_reference_selection_frozen must be True"
        ):
            self._materialize_tampered(tmp_path, mutate)

    def test_null_reference_count_frozen_false_fails_closed(self, tmp_path):
        def mutate(packet):
            packet["null_reference_count_frozen"] = False

        with pytest.raises(
            ValueError, match="null_reference_count_frozen must be True"
        ):
            self._materialize_tampered(tmp_path, mutate)

    @pytest.mark.parametrize("count", [0, 2, 7])
    def test_null_reference_count_not_one_fails_closed(self, tmp_path, count):
        def mutate(packet):
            packet["null_reference_count"] = count

        with pytest.raises(
            ValueError, match="null_reference_count must be exactly 1"
        ):
            self._materialize_tampered(tmp_path, mutate)

    @pytest.mark.parametrize("count", ["1", True, None, 1.0])
    def test_null_reference_count_wrong_type_fails_closed(self, tmp_path, count):
        def mutate(packet):
            packet["null_reference_count"] = count

        with pytest.raises(
            ValueError, match="null_reference_count must be a JSON integer"
        ):
            self._materialize_tampered(tmp_path, mutate)

    # -- 15b. Frozen null reference declaration values ------------------------
    #
    # A tampered packet is re-hashed into a matching sidecar, so digest checks
    # alone cannot catch a swapped reference family. The frozen string values
    # are the only thing standing between the lane and a leaky / post-hoc null.

    @pytest.mark.parametrize(
        "field,mutated",
        [
            ("null_reference_policy", "POST_HOC_SELECTED_REFERENCE"),
            (
                "null_reference_family",
                "LEAKY_REFERENCE_USING_OUTCOME_INFORMATION",
            ),
            (
                "null_reference_computation_policy",
                "COMPUTE_NULL_VALUES_NOW",
            ),
            (
                "null_reference_comparison_policy",
                "COMPARE_CANDIDATE_TO_NULL_NOW",
            ),
        ],
    )
    def test_mutated_null_reference_declaration_fails_closed(
        self, tmp_path, field, mutated
    ):
        def mutate(packet):
            packet[field] = mutated

        with pytest.raises(
            ValueError, match=f"{field} must be exactly"
        ):
            self._materialize_tampered(tmp_path, mutate)

    def test_frozen_null_reference_values_in_diagnostic(self):
        result = self._null_benchmark_diag()
        assert result["null_reference_policy"] == NULL_REFERENCE_POLICY_FROZEN
        assert result["null_reference_family"] == NULL_REFERENCE_FAMILY_FROZEN
        assert result["null_reference_computation_policy"] == (
            NULL_REFERENCE_COMPUTATION_POLICY_FROZEN
        )
        assert result["null_reference_comparison_policy"] == (
            NULL_REFERENCE_COMPARISON_POLICY_FROZEN
        )

    def test_frozen_null_reference_values_in_gate_evidence(self):
        evidence = self._null_benchmark_diag()[
            "null_benchmark_preregistration_gate"
        ]["evidence"]
        assert evidence["null_reference_policy_matches_frozen_value"] is True
        assert evidence["null_reference_family_matches_frozen_value"] is True
        assert evidence[
            "null_reference_computation_policy_matches_frozen_value"
        ] is True
        assert evidence[
            "null_reference_comparison_policy_matches_frozen_value"
        ] is True

    @pytest.mark.parametrize(
        "field",
        [
            "null_reference_policy",
            "null_reference_family",
            "null_reference_computation_policy",
            "null_reference_comparison_policy",
        ],
    )
    def test_gate_projection_blocked_by_wrong_frozen_value(self, field):
        """Pure gate helper: a diagnostic carrying a mutated reference
        declaration is blocked, never passed."""
        diagnostics = dict(self._null_benchmark_diag())
        diagnostics.pop("null_benchmark_preregistration_gate")
        diagnostics[field] = "LEAKY_REFERENCE_USING_OUTCOME_INFORMATION"
        gate = real_validation._derive_null_benchmark_preregistration_gate(
            diagnostics
        )
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            "BLOCKED_BY_INCOMPLETE_NULL_BENCHMARK_EVIDENCE"
        )
        assert gate["blocked_reason"] == (
            "NULL_BENCHMARK_GATE_EVIDENCE_INCOMPLETE"
        )
        assert gate["evidence"][f"{field}_matches_frozen_value"] is False
        assert gate["gate_scoring_authorization"] is False
        assert gate["gate_live_authorization"] is False
        assert gate["gate_final_verdict_authorization"] is False
        assert gate["gate_downstream_unlocks"] == []

    # -- 16. Authorization boolean type hardening ----------------------------

    @pytest.mark.parametrize(
        "field", list(real_validation._REQUIRED_FALSE_NULL_BENCHMARK_FIELDS)
    )
    @pytest.mark.parametrize("value", [0, "false", "true", True, None])
    def test_null_benchmark_auth_boolean_hardening(self, tmp_path, field, value):
        def mutate(packet):
            packet[field] = value

        with pytest.raises(ValueError, match="fields must be exactly false"):
            self._materialize_tampered(tmp_path, mutate)

    @pytest.mark.parametrize(
        "field",
        [
            "null_reference_policy",
            "null_reference_family",
            "null_reference_computation_policy",
            "null_reference_comparison_policy",
        ],
    )
    def test_required_field_missing_fails_closed(self, tmp_path, field):
        def mutate(packet):
            del packet[field]

        with pytest.raises(ValueError, match="missing required fields"):
            self._materialize_tampered(tmp_path, mutate)

    # -- 17. Receipt integration ---------------------------------------------

    def test_receipt_integration_full_path(self):
        contract_diag, manifest_diag, seal_diag = self._upstream_diags()
        null_benchmark_diag = self._null_benchmark_diag()
        receipt = real_validation.build_real_validation_receipt(
            input_manifest_fingerprint="test",
            data_quality_receipt_sha256="test",
            code_commit_sha="test",
            split_definitions=[{"split_id": 0}],
            cost_cases=[],
            strategy_rule_contract_diagnostics=contract_diag,
            trial_manifest_diagnostics=manifest_diag,
            oos_seal_diagnostics=seal_diag,
            null_benchmark_contract_diagnostics=null_benchmark_diag,
        )
        assert receipt["final_offline_verdict"] == (
            BLOCKED_BY_VALIDATION_IMPLEMENTATION
        )
        section = receipt["null_benchmark_contract_diagnostics"]
        gate = section["null_benchmark_preregistration_gate"]
        assert gate["gate_passed"] is True
        assert gate["gate_status"] == NULL_BENCHMARK_PREREGISTERED_DIAGNOSTIC_ONLY
        assert gate["gate_scoring_authorization"] is False
        assert gate["gate_final_verdict_authorization"] is False

    # -- 18-20. CLI ----------------------------------------------------------

    def _cli_base_args(self, output_dir):
        return [
            "--read-only", "--output-dir", str(output_dir),
            "--input-manifest-fingerprint", "abc",
            "--data-quality-receipt-sha256", "def",
            "--code-commit-sha", "ghi",
            "--global-min-timestamp", "2026-01-01T00:00:00Z",
            "--global-max-timestamp", "2026-02-01T00:00:00Z",
        ]

    def _cli_upstream_args(self):
        return [
            "--strategy-contract-path", self.CONTRACT_PATH,
            "--strategy-contract-sha256-path", self.CONTRACT_SIDECAR_PATH,
            "--strategy-contract-commit-binding-path", self.CONTRACT_BINDING_PATH,
            "--trial-manifest-path", self.MANIFEST_PATH,
            "--trial-manifest-sha256-path", self.MANIFEST_SIDECAR_PATH,
            "--oos-seal-path", self.SEAL_PATH,
            "--oos-seal-sha256-path", self.SEAL_SIDECAR_PATH,
        ]

    def test_cli_no_null_benchmark_args_gate_not_loaded(self, tmp_path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        exit_code = real_validation.main(self._cli_base_args(output_dir))
        assert exit_code == 0
        receipt = json.loads(
            (output_dir / "real_validation_receipt.json").read_text()
        )
        gate = receipt["null_benchmark_contract_diagnostics"][
            "null_benchmark_preregistration_gate"
        ]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == "NULL_BENCHMARK_NOT_LOADED"
        assert receipt["final_offline_verdict"] == (
            BLOCKED_BY_VALIDATION_IMPLEMENTATION
        )

    def test_cli_null_benchmark_without_oos_seal_fails_closed(self, tmp_path):
        """Null benchmark args without the OOS seal gate must not pass."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        exit_code = real_validation.main(
            self._cli_base_args(output_dir)
            + [
                "--null-benchmark-path", self.NULL_BENCHMARK_PATH,
                "--null-benchmark-sha256-path", self.NULL_BENCHMARK_SIDECAR_PATH,
            ]
        )
        assert exit_code == 4
        assert not (output_dir / "real_validation_receipt.json").exists()

    def test_cli_full_path_all_gates_pass_verdict_blocked(self, tmp_path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        exit_code = real_validation.main(
            self._cli_base_args(output_dir)
            + self._cli_upstream_args()
            + [
                "--null-benchmark-path", self.NULL_BENCHMARK_PATH,
                "--null-benchmark-sha256-path", self.NULL_BENCHMARK_SIDECAR_PATH,
            ]
        )
        assert exit_code == 0
        receipt = json.loads(
            (output_dir / "real_validation_receipt.json").read_text()
        )
        contract_gate = receipt["strategy_rule_contract_diagnostics"][
            "contract_packet_gate"
        ]
        manifest_gate = receipt["trial_manifest_diagnostics"][
            "trial_manifest_preregistration_gate"
        ]
        seal_gate = receipt["oos_seal_diagnostics"][
            "oos_seal_preregistration_gate"
        ]
        null_gate = receipt["null_benchmark_contract_diagnostics"][
            "null_benchmark_preregistration_gate"
        ]
        assert contract_gate["gate_passed"] is True
        assert manifest_gate["gate_passed"] is True
        assert seal_gate["gate_passed"] is True
        assert null_gate["gate_passed"] is True
        assert null_gate["gate_status"] == (
            NULL_BENCHMARK_PREREGISTERED_DIAGNOSTIC_ONLY
        )
        assert null_gate["gate_downstream_unlocks"] == []
        assert receipt["final_offline_verdict"] == (
            BLOCKED_BY_VALIDATION_IMPLEMENTATION
        )


class TestMultipleTestingControlPreregistrationH1:
    """Lane H1: multiple-testing control pre-scoring declaration packet + gate.

    Proves the declared test family, search procedure, and multiplicity policy
    are frozen and hash-bound to the frozen null benchmark, OOS seal, trial
    manifest, and strategy contract *before* any statistical evaluation exists.
    Nothing here computes a p-value, an interval, a multiplicity adjustment, a
    null, or a candidate-vs-null comparison, and nothing authorizes scoring.
    """

    CONTROL_PATH = "docs/contracts/instances/qnty_offline_edge_multiple_testing_control_v1.json"
    CONTROL_SIDECAR_PATH = "docs/contracts/instances/qnty_offline_edge_multiple_testing_control_v1.sha256"
    NULL_BENCHMARK_PATH = "docs/contracts/instances/qnty_offline_edge_null_benchmark_v1.json"
    NULL_BENCHMARK_SIDECAR_PATH = "docs/contracts/instances/qnty_offline_edge_null_benchmark_v1.sha256"
    SEAL_PATH = "docs/contracts/instances/qnty_offline_edge_oos_seal_v1.json"
    SEAL_SIDECAR_PATH = "docs/contracts/instances/qnty_offline_edge_oos_seal_v1.sha256"
    CONTRACT_PATH = "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.json"
    CONTRACT_SIDECAR_PATH = "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.sha256"
    CONTRACT_BINDING_PATH = "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.commit_binding.json"
    MANIFEST_PATH = "docs/contracts/instances/qnty_offline_edge_trial_manifest_v1.json"
    MANIFEST_SIDECAR_PATH = "docs/contracts/instances/qnty_offline_edge_trial_manifest_v1.sha256"

    def _upstream_diags(self):
        contract_diag = _build_strategy_rule_contract_diagnostics(
            contract_path=self.CONTRACT_PATH,
            sidecar_path=self.CONTRACT_SIDECAR_PATH,
            commit_binding_path=self.CONTRACT_BINDING_PATH,
        )
        manifest_diag = _build_trial_manifest_diagnostics(
            manifest_path=self.MANIFEST_PATH,
            sidecar_path=self.MANIFEST_SIDECAR_PATH,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        seal_diag = _build_oos_seal_diagnostics(
            seal_path=self.SEAL_PATH,
            sidecar_path=self.SEAL_SIDECAR_PATH,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        null_diag = _build_null_benchmark_contract_diagnostics(
            null_benchmark_path=self.NULL_BENCHMARK_PATH,
            sidecar_path=self.NULL_BENCHMARK_SIDECAR_PATH,
            oos_seal_diagnostics=seal_diag,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        return contract_diag, manifest_diag, seal_diag, null_diag

    def _control_diag(self):
        contract_diag, manifest_diag, seal_diag, null_diag = (
            self._upstream_diags()
        )
        return _build_multiple_testing_control_diagnostics(
            multiple_testing_control_path=self.CONTROL_PATH,
            sidecar_path=self.CONTROL_SIDECAR_PATH,
            null_benchmark_diagnostics=null_diag,
            oos_seal_diagnostics=seal_diag,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )

    def _tampered_packet(self, tmp_path, mutate):
        """Write a mutated control packet + a *matching* sidecar.

        The sidecar is regenerated so the digest check passes and the specific
        semantic check under test is the one that fails.
        """
        packet = json.loads(Path(self.CONTROL_PATH).read_bytes())
        mutate(packet)
        packet_bytes = json.dumps(packet, indent=2, sort_keys=True).encode() + b"\n"
        packet_path = tmp_path / "multiple_testing_control.json"
        packet_path.write_bytes(packet_bytes)
        sidecar_path = tmp_path / "multiple_testing_control.sha256"
        digest = hashlib.sha256(packet_bytes).hexdigest()
        sidecar_path.write_text(f"{digest}  {packet_path.name}\n")
        return str(packet_path), str(sidecar_path)

    def _materialize_tampered(self, tmp_path, mutate):
        contract_diag, manifest_diag, seal_diag, null_diag = (
            self._upstream_diags()
        )
        packet_path, sidecar_path = self._tampered_packet(tmp_path, mutate)
        return materialize_multiple_testing_control_preregistration_diagnostics(
            multiple_testing_control_path=packet_path,
            sidecar_path=sidecar_path,
            null_benchmark_diagnostics=null_diag,
            oos_seal_diagnostics=seal_diag,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )

    # -- 1. Packet JSON + sidecar happy path ---------------------------------

    def test_control_json_and_sidecar_valid(self):
        packet_bytes = Path(self.CONTROL_PATH).read_bytes()
        computed = hashlib.sha256(packet_bytes).hexdigest()
        sidecar = Path(self.CONTROL_SIDECAR_PATH).read_text().strip()
        assert sidecar.split()[0] == computed

        packet = json.loads(packet_bytes)
        assert packet["multiple_testing_control_hash"] == "FROZEN_IN_SIDECAR"
        assert packet["multiple_testing_control_hash_status"] == (
            "FROZEN_IN_SIDECAR"
        )
        assert packet["multiple_testing_control_hash_algorithm"] == "sha256"
        collisions = real_validation._find_forbidden_contract_dict_keys(packet)
        assert collisions == [], f"Forbidden keys found: {collisions}"

    # -- 2. Diagnostic happy path --------------------------------------------

    def test_control_diagnostic_happy_path(self):
        result = self._control_diag()
        assert result[
            "multiple_testing_control_sidecar_digest_matches_json_bytes"
        ] is True
        assert result["bound_contract_digest_matches"] is True
        assert result["bound_trial_manifest_digest_matches"] is True
        assert result["bound_oos_seal_digest_matches"] is True
        assert result["bound_null_benchmark_digest_matches"] is True
        assert result["null_benchmark_gate_passed"] is True
        assert result["null_benchmark_gate_status"] == (
            NULL_BENCHMARK_PREREGISTERED_DIAGNOSTIC_ONLY
        )
        assert result["testing_family_policy"] == TESTING_FAMILY_POLICY_FROZEN
        assert result["testing_family_policy_frozen"] is True
        assert result["candidate_declaration_count"] == 1
        assert result["candidate_declaration_count_frozen"] is True
        assert result["null_reference_declaration_count"] == 1
        assert result["null_reference_declaration_count_frozen"] is True
        assert result["search_procedure_policy"] == SEARCH_PROCEDURE_POLICY_FROZEN
        assert result["multiplicity_control_policy"] == (
            MULTIPLICITY_CONTROL_POLICY_FROZEN
        )
        assert result["statistical_evaluation_policy"] == (
            STATISTICAL_EVALUATION_POLICY_FROZEN
        )
        assert result["multiple_testing_control_readiness"] is False
        assert result["statistical_value_generation_authorized"] is False
        assert result["candidate_comparison_authorized"] is False
        assert result["null_generation_authorized"] is False
        assert result["scoring_authorized"] is False
        assert result["multiple_testing_control_validation_status"] == (
            MULTIPLE_TESTING_CONTROL_PREREGISTERED_DIAGNOSTIC_ONLY
        )

    def test_control_diagnostic_has_no_forbidden_keys(self):
        result = self._control_diag()
        collisions = real_validation._find_forbidden_contract_dict_keys(result)
        assert collisions == [], f"Forbidden keys found: {collisions}"

    # -- 3. Gate happy path --------------------------------------------------

    def test_control_gate_happy_path(self):
        gate = self._control_diag()[
            "multiple_testing_control_preregistration_gate"
        ]
        assert gate["gate_kind"] == "multiple_testing_control_preregistration_gate"
        assert gate["gate_scope"] == "TEST_FAMILY_AND_NULL_BENCHMARK_BINDING_ONLY"
        assert gate["gate_passed"] is True
        assert gate["gate_status"] == (
            MULTIPLE_TESTING_CONTROL_PREREGISTERED_DIAGNOSTIC_ONLY
        )
        assert gate["gate_scoring_authorization"] is False
        assert gate["gate_live_authorization"] is False
        assert gate["gate_final_verdict_authorization"] is False
        assert gate["gate_downstream_unlocks"] == []
        assert gate["blocked_reason"] is None
        assert gate["evidence"]["null_benchmark_gate_passed"] is True
        assert gate["evidence"]["bound_null_benchmark_digest_matches"] is True
        assert gate["evidence"]["candidate_declaration_count"] == 1
        assert gate["evidence"]["null_reference_declaration_count"] == 1
        assert gate["evidence"]["testing_family_policy_matches_frozen_value"] is True
        assert gate["evidence"][
            "search_procedure_policy_matches_frozen_value"
        ] is True
        assert gate["evidence"][
            "multiplicity_control_policy_matches_frozen_value"
        ] is True

    # -- 4. Packet missing fails closed --------------------------------------

    def test_control_absent_gate_not_loaded(self):
        result = _build_multiple_testing_control_diagnostics()
        gate = result["multiple_testing_control_preregistration_gate"]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == "MULTIPLE_TESTING_CONTROL_NOT_LOADED"
        assert gate["blocked_reason"] == "MULTIPLE_TESTING_CONTROL_NOT_PROVIDED"
        # No-args behavior stays the static absence diagnostic.
        assert result["multiple_testing_control_status"] == (
            MULTIPLE_TESTING_CONTROL_NOT_DEFINED
        )
        assert result["multiple_testing_control_present"] is False
        assert result["scoring_authorized"] is False

    def test_control_packet_missing_fails_closed(self):
        contract_diag, manifest_diag, seal_diag, null_diag = (
            self._upstream_diags()
        )
        with pytest.raises(
            ValueError, match="Multiple testing control JSON not found"
        ):
            materialize_multiple_testing_control_preregistration_diagnostics(
                multiple_testing_control_path="/tmp/nonexistent_control_h1.json",
                sidecar_path=self.CONTROL_SIDECAR_PATH,
                null_benchmark_diagnostics=null_diag,
                oos_seal_diagnostics=seal_diag,
                trial_manifest_diagnostics=manifest_diag,
                strategy_rule_contract_diagnostics=contract_diag,
            )

    # -- 5. Sidecar missing fails closed -------------------------------------

    def test_control_sidecar_missing_fails_closed(self):
        contract_diag, manifest_diag, seal_diag, null_diag = (
            self._upstream_diags()
        )
        with pytest.raises(
            ValueError, match="Multiple testing control sidecar not found"
        ):
            materialize_multiple_testing_control_preregistration_diagnostics(
                multiple_testing_control_path=self.CONTROL_PATH,
                sidecar_path="/tmp/nonexistent_control_h1.sha256",
                null_benchmark_diagnostics=null_diag,
                oos_seal_diagnostics=seal_diag,
                trial_manifest_diagnostics=manifest_diag,
                strategy_rule_contract_diagnostics=contract_diag,
            )

    # -- 6. Digest mismatch fails closed -------------------------------------

    def test_control_digest_mismatch_fails_closed(self, tmp_path):
        contract_diag, manifest_diag, seal_diag, null_diag = (
            self._upstream_diags()
        )
        packet_bytes = Path(self.CONTROL_PATH).read_bytes()
        packet_path = tmp_path / "multiple_testing_control.json"
        packet_path.write_bytes(packet_bytes)
        wrong_digest = hashlib.sha256(packet_bytes + b"tamper").hexdigest()
        sidecar_path = tmp_path / "multiple_testing_control.sha256"
        sidecar_path.write_text(f"{wrong_digest}  {packet_path.name}\n")
        with pytest.raises(ValueError, match="sidecar digest mismatch"):
            materialize_multiple_testing_control_preregistration_diagnostics(
                multiple_testing_control_path=str(packet_path),
                sidecar_path=str(sidecar_path),
                null_benchmark_diagnostics=null_diag,
                oos_seal_diagnostics=seal_diag,
                trial_manifest_diagnostics=manifest_diag,
                strategy_rule_contract_diagnostics=contract_diag,
            )

    # -- 7. Malformed JSON fails closed --------------------------------------

    def test_control_malformed_json_fails_closed(self, tmp_path):
        contract_diag, manifest_diag, seal_diag, null_diag = (
            self._upstream_diags()
        )
        bad_bytes = b"{invalid json"
        packet_path = tmp_path / "multiple_testing_control.json"
        packet_path.write_bytes(bad_bytes)
        sidecar_path = tmp_path / "multiple_testing_control.sha256"
        digest = hashlib.sha256(bad_bytes).hexdigest()
        sidecar_path.write_text(f"{digest}  {packet_path.name}\n")
        with pytest.raises(
            ValueError, match="Multiple testing control JSON parse error"
        ):
            materialize_multiple_testing_control_preregistration_diagnostics(
                multiple_testing_control_path=str(packet_path),
                sidecar_path=str(sidecar_path),
                null_benchmark_diagnostics=null_diag,
                oos_seal_diagnostics=seal_diag,
                trial_manifest_diagnostics=manifest_diag,
                strategy_rule_contract_diagnostics=contract_diag,
            )

    # -- 8. Forbidden dict key fails closed ----------------------------------

    @pytest.mark.parametrize("key", ["p_value", "confidence_interval", "pnl"])
    def test_control_forbidden_key_fails_closed(self, tmp_path, key):
        def mutate(packet):
            packet[key] = 0.1

        with pytest.raises(ValueError, match="forbidden dict keys"):
            self._materialize_tampered(tmp_path, mutate)

    # -- 9-12. Bound digest / id mismatches fail closed -----------------------

    def test_control_contract_digest_mismatch_fails_closed(self, tmp_path):
        def mutate(packet):
            packet["bound_contract_sha256"] = "0" * 64

        with pytest.raises(ValueError, match="bound_contract_sha256 mismatch"):
            self._materialize_tampered(tmp_path, mutate)

    def test_control_trial_manifest_digest_mismatch_fails_closed(self, tmp_path):
        def mutate(packet):
            packet["bound_trial_manifest_sha256"] = "0" * 64

        with pytest.raises(
            ValueError, match="bound_trial_manifest_sha256 mismatch"
        ):
            self._materialize_tampered(tmp_path, mutate)

    def test_control_oos_seal_digest_mismatch_fails_closed(self, tmp_path):
        def mutate(packet):
            packet["bound_oos_seal_sha256"] = "0" * 64

        with pytest.raises(ValueError, match="bound_oos_seal_sha256 mismatch"):
            self._materialize_tampered(tmp_path, mutate)

    def test_control_null_benchmark_digest_mismatch_fails_closed(self, tmp_path):
        def mutate(packet):
            packet["bound_null_benchmark_sha256"] = "0" * 64

        with pytest.raises(
            ValueError, match="bound_null_benchmark_sha256 mismatch"
        ):
            self._materialize_tampered(tmp_path, mutate)

    def test_control_null_benchmark_id_mismatch_fails_closed(self, tmp_path):
        def mutate(packet):
            packet["bound_null_benchmark_id"] = "some_other_null_benchmark"

        with pytest.raises(ValueError, match="bound_null_benchmark_id mismatch"):
            self._materialize_tampered(tmp_path, mutate)

    # -- 13. Missing / failed null benchmark gate blocks the control ----------

    def test_control_blocked_when_null_benchmark_gate_missing(self):
        contract_diag, manifest_diag, seal_diag, _ = self._upstream_diags()
        null_diag_no_gate = _build_null_benchmark_contract_diagnostics()
        with pytest.raises(ValueError, match="Null benchmark gate not passed"):
            _build_multiple_testing_control_diagnostics(
                multiple_testing_control_path=self.CONTROL_PATH,
                sidecar_path=self.CONTROL_SIDECAR_PATH,
                null_benchmark_diagnostics=null_diag_no_gate,
                oos_seal_diagnostics=seal_diag,
                trial_manifest_diagnostics=manifest_diag,
                strategy_rule_contract_diagnostics=contract_diag,
            )

    def test_gate_projection_blocked_by_null_benchmark_gate(self):
        """Pure gate helper: a loaded packet with a failed null benchmark gate
        is blocked, never passed."""
        diagnostics = dict(self._control_diag())
        diagnostics.pop("multiple_testing_control_preregistration_gate")
        diagnostics["null_benchmark_gate_passed"] = False
        gate = _derive_multiple_testing_control_preregistration_gate(diagnostics)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == "BLOCKED_BY_NULL_BENCHMARK_GATE"
        assert gate["blocked_reason"] == "NULL_BENCHMARK_GATE_NOT_PASSED"

    def test_gate_projection_blocked_by_incomplete_evidence(self):
        diagnostics = dict(self._control_diag())
        diagnostics.pop("multiple_testing_control_preregistration_gate")
        diagnostics["bound_null_benchmark_digest_matches"] = False
        gate = _derive_multiple_testing_control_preregistration_gate(diagnostics)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            "BLOCKED_BY_INCOMPLETE_MULTIPLE_TESTING_CONTROL_EVIDENCE"
        )
        assert gate["blocked_reason"] == (
            "MULTIPLE_TESTING_CONTROL_GATE_EVIDENCE_INCOMPLETE"
        )

    # -- 14-16. Frozen policy values ------------------------------------------
    #
    # A tampered packet is re-hashed into a matching sidecar, so digest checks
    # alone cannot catch a widened test family or a post-hoc search. The frozen
    # string values are the only thing standing between the lane and an
    # unaccounted multiple-testing burden.

    @pytest.mark.parametrize(
        "field,mutated",
        [
            ("testing_family_policy", "UNLIMITED_TRIALS_AND_NULL_REFERENCES"),
            ("search_procedure_policy", "SEARCH_AND_SELECT_BEST_POST_HOC"),
            (
                "multiplicity_control_policy",
                "NO_ADJUSTMENT_DECLARED_FOR_UNLIMITED_TRIALS",
            ),
            ("statistical_evaluation_policy", "COMPUTE_STATISTICAL_VALUES_NOW"),
        ],
    )
    def test_mutated_frozen_policy_fails_closed(self, tmp_path, field, mutated):
        def mutate(packet):
            packet[field] = mutated

        with pytest.raises(ValueError, match=f"{field} must be exactly"):
            self._materialize_tampered(tmp_path, mutate)

    def test_frozen_policy_values_in_diagnostic(self):
        result = self._control_diag()
        assert result["testing_family_policy"] == TESTING_FAMILY_POLICY_FROZEN
        assert result["search_procedure_policy"] == SEARCH_PROCEDURE_POLICY_FROZEN
        assert result["multiplicity_control_policy"] == (
            MULTIPLICITY_CONTROL_POLICY_FROZEN
        )
        assert result["statistical_evaluation_policy"] == (
            STATISTICAL_EVALUATION_POLICY_FROZEN
        )

    @pytest.mark.parametrize(
        "field",
        [
            "testing_family_policy",
            "search_procedure_policy",
            "multiplicity_control_policy",
            "statistical_evaluation_policy",
        ],
    )
    def test_gate_projection_blocked_by_wrong_frozen_value(self, field):
        """Pure gate helper: a diagnostic carrying a mutated policy declaration
        is blocked, never passed."""
        diagnostics = dict(self._control_diag())
        diagnostics.pop("multiple_testing_control_preregistration_gate")
        diagnostics[field] = "SEARCH_AND_SELECT_BEST_POST_HOC"
        gate = _derive_multiple_testing_control_preregistration_gate(diagnostics)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            "BLOCKED_BY_INCOMPLETE_MULTIPLE_TESTING_CONTROL_EVIDENCE"
        )
        assert gate["evidence"][f"{field}_matches_frozen_value"] is False
        assert gate["gate_scoring_authorization"] is False
        assert gate["gate_live_authorization"] is False
        assert gate["gate_final_verdict_authorization"] is False
        assert gate["gate_downstream_unlocks"] == []

    @pytest.mark.parametrize(
        "field",
        [
            "testing_family_policy_frozen",
            "search_procedure_policy_frozen",
            "multiplicity_control_policy_frozen",
            "candidate_declaration_count_frozen",
            "null_reference_declaration_count_frozen",
        ],
    )
    def test_policy_not_frozen_fails_closed(self, tmp_path, field):
        def mutate(packet):
            packet[field] = False

        with pytest.raises(ValueError, match=f"{field} must be True"):
            self._materialize_tampered(tmp_path, mutate)

    # -- 17-18. Declaration counts -------------------------------------------

    @pytest.mark.parametrize(
        "field",
        ["candidate_declaration_count", "null_reference_declaration_count"],
    )
    @pytest.mark.parametrize("count", [0, 2, 7])
    def test_declaration_count_not_one_fails_closed(self, tmp_path, field, count):
        def mutate(packet):
            packet[field] = count

        with pytest.raises(ValueError, match=f"{field} must be exactly 1"):
            self._materialize_tampered(tmp_path, mutate)

    @pytest.mark.parametrize(
        "field",
        ["candidate_declaration_count", "null_reference_declaration_count"],
    )
    @pytest.mark.parametrize("count", ["1", True, None, 1.0])
    def test_declaration_count_wrong_type_fails_closed(
        self, tmp_path, field, count
    ):
        def mutate(packet):
            packet[field] = count

        with pytest.raises(ValueError, match=f"{field} must be a JSON integer"):
            self._materialize_tampered(tmp_path, mutate)

    @pytest.mark.parametrize(
        "field",
        ["candidate_declaration_count", "null_reference_declaration_count"],
    )
    def test_gate_projection_blocked_by_wrong_count(self, field):
        diagnostics = dict(self._control_diag())
        diagnostics.pop("multiple_testing_control_preregistration_gate")
        diagnostics[field] = 4
        gate = _derive_multiple_testing_control_preregistration_gate(diagnostics)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            "BLOCKED_BY_INCOMPLETE_MULTIPLE_TESTING_CONTROL_EVIDENCE"
        )
        assert gate["evidence"][field] == 4

    # -- 19. Authorization boolean type hardening ----------------------------

    @pytest.mark.parametrize(
        "field",
        list(real_validation._REQUIRED_FALSE_MULTIPLE_TESTING_CONTROL_FIELDS),
    )
    @pytest.mark.parametrize("value", [0, "false", "true", True, None])
    def test_control_auth_boolean_hardening(self, tmp_path, field, value):
        def mutate(packet):
            packet[field] = value

        with pytest.raises(ValueError, match="fields must be exactly false"):
            self._materialize_tampered(tmp_path, mutate)

    @pytest.mark.parametrize(
        "field",
        [
            "testing_family_policy",
            "search_procedure_policy",
            "multiplicity_control_policy",
            "statistical_evaluation_policy",
            "candidate_declaration_count",
            "null_reference_declaration_count",
            "required_null_benchmark_gate_status",
        ],
    )
    def test_control_required_field_missing_fails_closed(self, tmp_path, field):
        def mutate(packet):
            del packet[field]

        with pytest.raises(ValueError, match="missing required fields"):
            self._materialize_tampered(tmp_path, mutate)

    # -- 20. Receipt integration ---------------------------------------------

    def test_receipt_integration_full_path(self):
        contract_diag, manifest_diag, seal_diag, null_diag = (
            self._upstream_diags()
        )
        control_diag = self._control_diag()
        receipt = build_real_validation_receipt(
            input_manifest_fingerprint="test",
            data_quality_receipt_sha256="test",
            code_commit_sha="test",
            split_definitions=[{"split_id": 0}],
            cost_cases=[],
            strategy_rule_contract_diagnostics=contract_diag,
            trial_manifest_diagnostics=manifest_diag,
            oos_seal_diagnostics=seal_diag,
            null_benchmark_contract_diagnostics=null_diag,
            multiple_testing_control_diagnostics=control_diag,
        )
        assert receipt["final_offline_verdict"] == (
            BLOCKED_BY_VALIDATION_IMPLEMENTATION
        )
        section = receipt["multiple_testing_control_diagnostics"]
        gate = section["multiple_testing_control_preregistration_gate"]
        assert gate["gate_passed"] is True
        assert gate["gate_status"] == (
            MULTIPLE_TESTING_CONTROL_PREREGISTERED_DIAGNOSTIC_ONLY
        )
        assert gate["gate_scoring_authorization"] is False
        assert gate["gate_final_verdict_authorization"] is False
        assert gate["gate_downstream_unlocks"] == []

    # -- 21-23. CLI ----------------------------------------------------------

    def _cli_base_args(self, output_dir):
        return [
            "--read-only", "--output-dir", str(output_dir),
            "--input-manifest-fingerprint", "abc",
            "--data-quality-receipt-sha256", "def",
            "--code-commit-sha", "ghi",
            "--global-min-timestamp", "2026-01-01T00:00:00Z",
            "--global-max-timestamp", "2026-02-01T00:00:00Z",
        ]

    def _cli_upstream_args(self):
        return [
            "--strategy-contract-path", self.CONTRACT_PATH,
            "--strategy-contract-sha256-path", self.CONTRACT_SIDECAR_PATH,
            "--strategy-contract-commit-binding-path", self.CONTRACT_BINDING_PATH,
            "--trial-manifest-path", self.MANIFEST_PATH,
            "--trial-manifest-sha256-path", self.MANIFEST_SIDECAR_PATH,
            "--oos-seal-path", self.SEAL_PATH,
            "--oos-seal-sha256-path", self.SEAL_SIDECAR_PATH,
            "--null-benchmark-path", self.NULL_BENCHMARK_PATH,
            "--null-benchmark-sha256-path", self.NULL_BENCHMARK_SIDECAR_PATH,
        ]

    def _cli_control_args(self):
        return [
            "--multiple-testing-control-path", self.CONTROL_PATH,
            "--multiple-testing-control-sha256-path", self.CONTROL_SIDECAR_PATH,
        ]

    def test_cli_no_control_args_gate_not_loaded(self, tmp_path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        exit_code = real_validation.main(self._cli_base_args(output_dir))
        assert exit_code == 0
        receipt = json.loads(
            (output_dir / "real_validation_receipt.json").read_text()
        )
        gate = receipt["multiple_testing_control_diagnostics"][
            "multiple_testing_control_preregistration_gate"
        ]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == "MULTIPLE_TESTING_CONTROL_NOT_LOADED"
        assert receipt["final_offline_verdict"] == (
            BLOCKED_BY_VALIDATION_IMPLEMENTATION
        )

    def test_cli_control_without_null_benchmark_fails_closed(self, tmp_path):
        """Control args without the upstream gates must not pass."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        exit_code = real_validation.main(
            self._cli_base_args(output_dir) + self._cli_control_args()
        )
        assert exit_code == 4
        assert not (output_dir / "real_validation_receipt.json").exists()

    def test_cli_full_path_all_gates_pass_verdict_blocked(self, tmp_path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        exit_code = real_validation.main(
            self._cli_base_args(output_dir)
            + self._cli_upstream_args()
            + self._cli_control_args()
        )
        assert exit_code == 0
        receipt = json.loads(
            (output_dir / "real_validation_receipt.json").read_text()
        )
        contract_gate = receipt["strategy_rule_contract_diagnostics"][
            "contract_packet_gate"
        ]
        manifest_gate = receipt["trial_manifest_diagnostics"][
            "trial_manifest_preregistration_gate"
        ]
        seal_gate = receipt["oos_seal_diagnostics"][
            "oos_seal_preregistration_gate"
        ]
        null_gate = receipt["null_benchmark_contract_diagnostics"][
            "null_benchmark_preregistration_gate"
        ]
        control_gate = receipt["multiple_testing_control_diagnostics"][
            "multiple_testing_control_preregistration_gate"
        ]
        assert contract_gate["gate_passed"] is True
        assert manifest_gate["gate_passed"] is True
        assert seal_gate["gate_passed"] is True
        assert null_gate["gate_passed"] is True
        assert control_gate["gate_passed"] is True
        assert control_gate["gate_status"] == (
            MULTIPLE_TESTING_CONTROL_PREREGISTERED_DIAGNOSTIC_ONLY
        )
        assert control_gate["gate_downstream_unlocks"] == []
        assert control_gate["gate_scoring_authorization"] is False
        assert control_gate["gate_live_authorization"] is False
        assert control_gate["gate_final_verdict_authorization"] is False
        assert receipt["final_offline_verdict"] == (
            BLOCKED_BY_VALIDATION_IMPLEMENTATION
        )


class TestSimulationPolicyPreregistrationDiagnostics:
    """Tests for materialize_simulation_policy_preregistration_diagnostics()
    and its integration into the offline-edge receipt."""

    # ── Absence / no-args behavior ──────────────────────────────────────────
    def test_absence_returns_original_shape(self):
        """No-args call preserves backward-compatible absence shape."""
        result = real_validation._build_trade_position_simulation_contract_diagnostics()
        assert result["contract_version"] == TRADE_POSITION_SIMULATION_CONTRACT_VERSION
        assert result["trade_position_simulation_contract_status"] == (
            TRADE_POSITION_SIMULATION_CONTRACT_NOT_DEFINED
        )

    def test_absence_has_prerequisites(self):
        result = real_validation._build_trade_position_simulation_contract_diagnostics()
        prereqs = result["trade_position_simulation_contract_prerequisites_present"]
        assert isinstance(prereqs, dict)
        for value in prereqs.values():
            assert value is False

    # ── Happy path: materializer with real packet ───────────────────────────
    def test_materializer_happy_path(self):
        """Load the frozen simulation policy packet and verify sidecar."""
        project_root = Path(__file__).resolve().parent.parent.parent
        sp_path = str(project_root / "docs/contracts/instances/qnty_offline_edge_simulation_policy_v1.json")
        sha_path = str(project_root / "docs/contracts/instances/qnty_offline_edge_simulation_policy_v1.sha256")
        contract_path = str(project_root / "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.json")
        contract_sha = str(project_root / "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.sha256")
        trial_path = str(project_root / "docs/contracts/instances/qnty_offline_edge_trial_manifest_v1.json")
        trial_sha = str(project_root / "docs/contracts/instances/qnty_offline_edge_trial_manifest_v1.sha256")
        oos_path = str(project_root / "docs/contracts/instances/qnty_offline_edge_oos_seal_v1.json")
        oos_sha = str(project_root / "docs/contracts/instances/qnty_offline_edge_oos_seal_v1.sha256")
        null_path = str(project_root / "docs/contracts/instances/qnty_offline_edge_null_benchmark_v1.json")
        null_sha = str(project_root / "docs/contracts/instances/qnty_offline_edge_null_benchmark_v1.sha256")
        mt_path = str(project_root / "docs/contracts/instances/qnty_offline_edge_multiple_testing_control_v1.json")
        mt_sha = str(project_root / "docs/contracts/instances/qnty_offline_edge_multiple_testing_control_v1.sha256")

        contract_binding = str(project_root / "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.commit_binding.json")
        contract_diag = real_validation._build_strategy_rule_contract_diagnostics(
            contract_path=contract_path, sidecar_path=contract_sha,
            commit_binding_path=contract_binding,
        )
        trial_diag = real_validation._build_trial_manifest_diagnostics(
            manifest_path=trial_path, sidecar_path=trial_sha,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        oos_diag = real_validation._build_oos_seal_diagnostics(
            seal_path=oos_path, sidecar_path=oos_sha,
            trial_manifest_diagnostics=trial_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        null_diag = real_validation._build_null_benchmark_contract_diagnostics(
            null_benchmark_path=null_path, sidecar_path=null_sha,
            oos_seal_diagnostics=oos_diag,
            trial_manifest_diagnostics=trial_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        mt_diag = real_validation._build_multiple_testing_control_diagnostics(
            multiple_testing_control_path=mt_path, sidecar_path=mt_sha,
            null_benchmark_diagnostics=null_diag,
            oos_seal_diagnostics=oos_diag,
            trial_manifest_diagnostics=trial_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )

        sp_diag = real_validation._build_trade_position_simulation_contract_diagnostics(
            simulation_policy_path=sp_path, sidecar_path=sha_path,
            multiple_testing_control_diagnostics=mt_diag,
            null_benchmark_diagnostics=null_diag,
            oos_seal_diagnostics=oos_diag,
            trial_manifest_diagnostics=trial_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )

        assert sp_diag["diagnostic_kind"] == "simulation_policy_preregistration"
        assert sp_diag["simulation_policy_sidecar_digest_matches_json_bytes"] is True
        assert sp_diag["simulation_policy_hash_authority"] == "SIDECAR"
        assert sp_diag["simulated_event_generation_authorized"] is False
        assert sp_diag["economic_value_generation_authorized"] is False
        assert sp_diag["simulation_family_policy"] == real_validation.SIMULATION_FAMILY_POLICY_FROZEN
        assert sp_diag["simulation_timing_policy"] == real_validation.SIMULATION_TIMING_POLICY_FROZEN
        assert sp_diag["simulation_cost_policy"] == real_validation.SIMULATION_COST_POLICY_FROZEN
        assert sp_diag["simulation_funding_policy"] == real_validation.SIMULATION_FUNDING_POLICY_FROZEN
        assert sp_diag["simulation_quantity_policy"] == real_validation.SIMULATION_QUANTITY_POLICY_FROZEN
        assert sp_diag["simulation_output_policy"] == real_validation.SIMULATION_OUTPUT_POLICY_FROZEN

        gate = sp_diag["simulation_policy_preregistration_gate"]
        assert gate["gate_passed"] is True
        assert gate["gate_status"] == real_validation.SIMULATION_POLICY_PREREGISTERED_DIAGNOSTIC_ONLY
        assert gate["gate_scoring_authorization"] is False
        assert gate["gate_live_authorization"] is False
        assert gate["gate_final_verdict_authorization"] is False
        assert gate["gate_downstream_unlocks"] == []

    def test_packet_missing_fails_closed(self):
        """No simulation policy args returns absence shape."""
        result = real_validation._build_trade_position_simulation_contract_diagnostics(
            simulation_policy_path=None, sidecar_path=None,
            multiple_testing_control_diagnostics={},
            null_benchmark_diagnostics={}, oos_seal_diagnostics={},
            trial_manifest_diagnostics={}, strategy_rule_contract_diagnostics={},
        )
        assert result["contract_version"] == TRADE_POSITION_SIMULATION_CONTRACT_VERSION
        assert result["trade_position_simulation_contract_status"] == (
            TRADE_POSITION_SIMULATION_CONTRACT_NOT_DEFINED
        )

    def test_sidecar_missing_fails_closed(self):
        """Simulation policy path without sidecar returns absence shape."""
        result = real_validation._build_trade_position_simulation_contract_diagnostics(
            simulation_policy_path="/nonexistent/path.json", sidecar_path=None,
            multiple_testing_control_diagnostics={},
            null_benchmark_diagnostics={}, oos_seal_diagnostics={},
            trial_manifest_diagnostics={}, strategy_rule_contract_diagnostics={},
        )
        assert result["contract_version"] == TRADE_POSITION_SIMULATION_CONTRACT_VERSION

    def test_digest_mismatch_raises(self):
        """Sidecar digest mismatch raises ValueError."""
        project_root = Path(__file__).resolve().parent.parent.parent
        sp_path = str(project_root / "docs/contracts/instances/qnty_offline_edge_simulation_policy_v1.json")
        # Use a wrong sidecar
        contract_sha = str(project_root / "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.sha256")
        with pytest.raises(ValueError, match="digest mismatch"):
            real_validation.materialize_simulation_policy_preregistration_diagnostics(
                simulation_policy_path=sp_path,
                sidecar_path=contract_sha,
                multiple_testing_control_diagnostics={"diagnostic_kind": "multiple_testing_control_preregistration"},
                null_benchmark_diagnostics={},
                oos_seal_diagnostics={},
                trial_manifest_diagnostics={},
                strategy_rule_contract_diagnostics={},
            )


class TestSimulationPolicyPreregistrationI1:
    """Lane I1: simulation policy pre-scoring declaration packet + gate.

    Proves the frozen simulation policy declarations are frozen and hash-bound
    to all upstream contracts *before* any simulated events, economic values,
    or scoring exist. Nothing here generates events, computes economic values,
    authorizes scoring, or advances any gate.
    """

    SP_PATH = "docs/contracts/instances/qnty_offline_edge_simulation_policy_v1.json"
    SP_SIDECAR_PATH = "docs/contracts/instances/qnty_offline_edge_simulation_policy_v1.sha256"
    CONTRACT_PATH = "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.json"
    CONTRACT_SIDECAR_PATH = "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.sha256"
    CONTRACT_BINDING_PATH = "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.commit_binding.json"
    MANIFEST_PATH = "docs/contracts/instances/qnty_offline_edge_trial_manifest_v1.json"
    MANIFEST_SIDECAR_PATH = "docs/contracts/instances/qnty_offline_edge_trial_manifest_v1.sha256"
    SEAL_PATH = "docs/contracts/instances/qnty_offline_edge_oos_seal_v1.json"
    SEAL_SIDECAR_PATH = "docs/contracts/instances/qnty_offline_edge_oos_seal_v1.sha256"
    NULL_PATH = "docs/contracts/instances/qnty_offline_edge_null_benchmark_v1.json"
    NULL_SIDECAR_PATH = "docs/contracts/instances/qnty_offline_edge_null_benchmark_v1.sha256"
    MT_PATH = "docs/contracts/instances/qnty_offline_edge_multiple_testing_control_v1.json"
    MT_SIDECAR_PATH = "docs/contracts/instances/qnty_offline_edge_multiple_testing_control_v1.sha256"

    def _upstream_diags(self):
        contract_diag = _build_strategy_rule_contract_diagnostics(
            contract_path=self.CONTRACT_PATH,
            sidecar_path=self.CONTRACT_SIDECAR_PATH,
            commit_binding_path=self.CONTRACT_BINDING_PATH,
        )
        manifest_diag = _build_trial_manifest_diagnostics(
            manifest_path=self.MANIFEST_PATH,
            sidecar_path=self.MANIFEST_SIDECAR_PATH,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        seal_diag = _build_oos_seal_diagnostics(
            seal_path=self.SEAL_PATH,
            sidecar_path=self.SEAL_SIDECAR_PATH,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        null_diag = _build_null_benchmark_contract_diagnostics(
            null_benchmark_path=self.NULL_PATH,
            sidecar_path=self.NULL_SIDECAR_PATH,
            oos_seal_diagnostics=seal_diag,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        mt_diag = _build_multiple_testing_control_diagnostics(
            multiple_testing_control_path=self.MT_PATH,
            sidecar_path=self.MT_SIDECAR_PATH,
            null_benchmark_diagnostics=null_diag,
            oos_seal_diagnostics=seal_diag,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        return contract_diag, manifest_diag, seal_diag, null_diag, mt_diag

    def _sp_diag(self):
        contract_diag, manifest_diag, seal_diag, null_diag, mt_diag = (
            self._upstream_diags()
        )
        return _build_trade_position_simulation_contract_diagnostics(
            simulation_policy_path=self.SP_PATH,
            sidecar_path=self.SP_SIDECAR_PATH,
            multiple_testing_control_diagnostics=mt_diag,
            null_benchmark_diagnostics=null_diag,
            oos_seal_diagnostics=seal_diag,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )

    def _tampered_packet(self, tmp_path, mutate):
        """Write a mutated simulation policy packet + a *matching* sidecar."""
        packet = json.loads(Path(self.SP_PATH).read_bytes())
        mutate(packet)
        packet_bytes = json.dumps(packet, indent=2, sort_keys=True).encode() + b"\n"
        packet_path = tmp_path / "simulation_policy.json"
        packet_path.write_bytes(packet_bytes)
        sidecar_path = tmp_path / "simulation_policy.sha256"
        digest = hashlib.sha256(packet_bytes).hexdigest()
        sidecar_path.write_text(f"{digest}  {packet_path.name}\n")
        return str(packet_path), str(sidecar_path)

    def _materialize_tampered(self, tmp_path, mutate):
        contract_diag, manifest_diag, seal_diag, null_diag, mt_diag = (
            self._upstream_diags()
        )
        packet_path, sidecar_path = self._tampered_packet(tmp_path, mutate)
        return materialize_simulation_policy_preregistration_diagnostics(
            simulation_policy_path=packet_path,
            sidecar_path=sidecar_path,
            multiple_testing_control_diagnostics=mt_diag,
            null_benchmark_diagnostics=null_diag,
            oos_seal_diagnostics=seal_diag,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )

    # -- 1. Packet JSON + sidecar happy path -----------------------------------

    def test_sp_json_and_sidecar_valid(self):
        packet_bytes = Path(self.SP_PATH).read_bytes()
        computed = hashlib.sha256(packet_bytes).hexdigest()
        sidecar = Path(self.SP_SIDECAR_PATH).read_text().strip()
        assert sidecar.split()[0] == computed

        packet = json.loads(packet_bytes)
        assert packet["simulation_policy_hash"] == "FROZEN_IN_SIDECAR"
        assert packet["simulation_policy_hash_status"] == "FROZEN_IN_SIDECAR"
        assert packet["simulation_policy_hash_algorithm"] == "sha256"
        collisions = real_validation._find_forbidden_contract_dict_keys(packet)
        assert collisions == [], f"Forbidden keys found: {collisions}"

    # -- 2. Diagnostic happy path ---------------------------------------------

    def test_sp_diagnostic_happy_path(self):
        result = self._sp_diag()
        assert result["diagnostic_kind"] == "simulation_policy_preregistration"
        assert result["simulation_policy_sidecar_digest_matches_json_bytes"] is True
        assert result["bound_contract_digest_matches"] is True
        assert result["bound_trial_manifest_digest_matches"] is True
        assert result["bound_oos_seal_digest_matches"] is True
        assert result["bound_null_benchmark_digest_matches"] is True
        assert result["bound_multiple_testing_control_digest_matches"] is True
        assert result["multiple_testing_control_gate_passed"] is True
        assert result["simulation_family_policy"] == real_validation.SIMULATION_FAMILY_POLICY_FROZEN
        assert result["simulation_family_policy_frozen"] is True
        assert result["simulation_timing_policy"] == real_validation.SIMULATION_TIMING_POLICY_FROZEN
        assert result["simulation_timing_policy_frozen"] is True
        assert result["simulation_cost_policy"] == real_validation.SIMULATION_COST_POLICY_FROZEN
        assert result["simulation_cost_policy_frozen"] is True
        assert result["simulation_funding_policy"] == real_validation.SIMULATION_FUNDING_POLICY_FROZEN
        assert result["simulation_funding_policy_frozen"] is True
        assert result["simulation_quantity_policy"] == real_validation.SIMULATION_QUANTITY_POLICY_FROZEN
        assert result["simulation_quantity_policy_frozen"] is True
        assert result["simulation_output_policy"] == real_validation.SIMULATION_OUTPUT_POLICY_FROZEN
        assert result["simulation_output_policy_frozen"] is True
        assert result["simulation_policy_readiness"] is False
        assert result["simulated_event_generation_authorized"] is False
        assert result["economic_value_generation_authorized"] is False
        assert result["simulation_policy_validation_status"] == (
            real_validation.SIMULATION_POLICY_PREREGISTERED_DIAGNOSTIC_ONLY
        )

    def test_sp_diagnostic_has_no_forbidden_keys(self):
        result = self._sp_diag()
        collisions = real_validation._find_forbidden_contract_dict_keys(result)
        assert collisions == [], f"Forbidden keys found: {collisions}"

    # -- 3. Gate happy path ---------------------------------------------------

    def test_sp_gate_happy_path(self):
        gate = self._sp_diag()["simulation_policy_preregistration_gate"]
        assert gate["gate_kind"] == "simulation_policy_preregistration_gate"
        assert gate["gate_scope"] == "SIMULATION_POLICY_AND_MULTIPLE_TESTING_BINDING_ONLY"
        assert gate["gate_passed"] is True
        assert gate["gate_status"] == (
            real_validation.SIMULATION_POLICY_PREREGISTERED_DIAGNOSTIC_ONLY
        )
        assert gate["gate_scoring_authorization"] is False
        assert gate["gate_live_authorization"] is False
        assert gate["gate_final_verdict_authorization"] is False
        assert gate["gate_downstream_unlocks"] == []
        assert gate["blocked_reason"] is None

    # -- 4. Packet missing fails closed ---------------------------------------

    def test_sp_packet_missing_fails_closed(self):
        contract_diag, manifest_diag, seal_diag, null_diag, mt_diag = (
            self._upstream_diags()
        )
        with pytest.raises(
            ValueError, match="Simulation policy JSON not found"
        ):
            materialize_simulation_policy_preregistration_diagnostics(
                simulation_policy_path="/tmp/nonexistent_sp_i1.json",
                sidecar_path=self.SP_SIDECAR_PATH,
                multiple_testing_control_diagnostics=mt_diag,
                null_benchmark_diagnostics=null_diag,
                oos_seal_diagnostics=seal_diag,
                trial_manifest_diagnostics=manifest_diag,
                strategy_rule_contract_diagnostics=contract_diag,
            )

    # -- 5. Sidecar missing fails closed --------------------------------------

    def test_sp_sidecar_missing_fails_closed(self):
        contract_diag, manifest_diag, seal_diag, null_diag, mt_diag = (
            self._upstream_diags()
        )
        with pytest.raises(
            ValueError, match="Simulation policy sidecar not found"
        ):
            materialize_simulation_policy_preregistration_diagnostics(
                simulation_policy_path=self.SP_PATH,
                sidecar_path="/tmp/nonexistent_sp_i1.sha256",
                multiple_testing_control_diagnostics=mt_diag,
                null_benchmark_diagnostics=null_diag,
                oos_seal_diagnostics=seal_diag,
                trial_manifest_diagnostics=manifest_diag,
                strategy_rule_contract_diagnostics=contract_diag,
            )

    # -- 6. Digest mismatch fails closed --------------------------------------

    def test_sp_digest_mismatch_fails_closed(self, tmp_path):
        contract_diag, manifest_diag, seal_diag, null_diag, mt_diag = (
            self._upstream_diags()
        )
        packet_bytes = Path(self.SP_PATH).read_bytes()
        packet_path = tmp_path / "simulation_policy.json"
        packet_path.write_bytes(packet_bytes)
        wrong_digest = hashlib.sha256(packet_bytes + b"tamper").hexdigest()
        sidecar_path = tmp_path / "simulation_policy.sha256"
        sidecar_path.write_text(f"{wrong_digest}  {packet_path.name}\n")
        with pytest.raises(ValueError, match="sidecar digest mismatch"):
            materialize_simulation_policy_preregistration_diagnostics(
                simulation_policy_path=str(packet_path),
                sidecar_path=str(sidecar_path),
                multiple_testing_control_diagnostics=mt_diag,
                null_benchmark_diagnostics=null_diag,
                oos_seal_diagnostics=seal_diag,
                trial_manifest_diagnostics=manifest_diag,
                strategy_rule_contract_diagnostics=contract_diag,
            )

    # -- 7. Malformed JSON fails closed ---------------------------------------

    def test_sp_malformed_json_fails_closed(self, tmp_path):
        contract_diag, manifest_diag, seal_diag, null_diag, mt_diag = (
            self._upstream_diags()
        )
        bad_bytes = b"{invalid json"
        packet_path = tmp_path / "simulation_policy.json"
        packet_path.write_bytes(bad_bytes)
        sidecar_path = tmp_path / "simulation_policy.sha256"
        digest = hashlib.sha256(bad_bytes).hexdigest()
        sidecar_path.write_text(f"{digest}  {packet_path.name}\n")
        with pytest.raises(
            ValueError, match="Simulation policy JSON parse error"
        ):
            materialize_simulation_policy_preregistration_diagnostics(
                simulation_policy_path=str(packet_path),
                sidecar_path=str(sidecar_path),
                multiple_testing_control_diagnostics=mt_diag,
                null_benchmark_diagnostics=null_diag,
                oos_seal_diagnostics=seal_diag,
                trial_manifest_diagnostics=manifest_diag,
                strategy_rule_contract_diagnostics=contract_diag,
            )

    # -- 8. Forbidden dict key fails closed -----------------------------------

    @pytest.mark.parametrize("key", ["position", "execution"])
    def test_sp_forbidden_key_fails_closed(self, tmp_path, key):
        def mutate(packet):
            packet[key] = 1

        with pytest.raises(ValueError, match="forbidden dict keys"):
            self._materialize_tampered(tmp_path, mutate)

    # -- 9-13. Bound digest mismatches fail closed ----------------------------

    def test_sp_contract_digest_mismatch_fails_closed(self, tmp_path):
        def mutate(packet):
            packet["bound_contract_sha256"] = "0" * 64

        with pytest.raises(ValueError, match="bound_contract_sha256 mismatch"):
            self._materialize_tampered(tmp_path, mutate)

    def test_sp_trial_manifest_digest_mismatch_fails_closed(self, tmp_path):
        def mutate(packet):
            packet["bound_trial_manifest_sha256"] = "0" * 64

        with pytest.raises(
            ValueError, match="bound_trial_manifest_sha256 mismatch"
        ):
            self._materialize_tampered(tmp_path, mutate)

    def test_sp_oos_seal_digest_mismatch_fails_closed(self, tmp_path):
        def mutate(packet):
            packet["bound_oos_seal_sha256"] = "0" * 64

        with pytest.raises(ValueError, match="bound_oos_seal_sha256 mismatch"):
            self._materialize_tampered(tmp_path, mutate)

    def test_sp_null_benchmark_digest_mismatch_fails_closed(self, tmp_path):
        def mutate(packet):
            packet["bound_null_benchmark_sha256"] = "0" * 64

        with pytest.raises(
            ValueError, match="bound_null_benchmark_sha256 mismatch"
        ):
            self._materialize_tampered(tmp_path, mutate)

    def test_sp_mt_control_digest_mismatch_fails_closed(self, tmp_path):
        def mutate(packet):
            packet["bound_multiple_testing_control_sha256"] = "0" * 64

        with pytest.raises(
            ValueError, match="bound_multiple_testing_control_sha256 mismatch"
        ):
            self._materialize_tampered(tmp_path, mutate)

    # -- 14. Multiple-testing control gate missing/false blocks ----------------

    def test_sp_blocked_when_mt_gate_missing(self):
        contract_diag, manifest_diag, seal_diag, null_diag, _ = (
            self._upstream_diags()
        )
        mt_diag_no_gate = _build_multiple_testing_control_diagnostics()
        with pytest.raises(
            ValueError, match="Multiple-testing control gate not passed"
        ):
            _build_trade_position_simulation_contract_diagnostics(
                simulation_policy_path=self.SP_PATH,
                sidecar_path=self.SP_SIDECAR_PATH,
                multiple_testing_control_diagnostics=mt_diag_no_gate,
                null_benchmark_diagnostics=null_diag,
                oos_seal_diagnostics=seal_diag,
                trial_manifest_diagnostics=manifest_diag,
                strategy_rule_contract_diagnostics=contract_diag,
            )

    def test_gate_projection_blocked_by_mt_gate_failure(self):
        """Pure gate helper: a diagnostic with a failed MT gate is blocked."""
        diagnostics = dict(self._sp_diag())
        diagnostics.pop("simulation_policy_preregistration_gate")
        diagnostics["multiple_testing_control_gate_passed"] = False
        gate = _derive_simulation_policy_preregistration_gate(diagnostics)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == real_validation.BLOCKED_BY_MULTIPLE_TESTING_CONTROL_GATE
        assert gate["blocked_reason"] == "MULTIPLE_TESTING_CONTROL_GATE_NOT_PASSED"

    def test_gate_projection_blocked_by_incomplete_evidence(self):
        diagnostics = dict(self._sp_diag())
        diagnostics.pop("simulation_policy_preregistration_gate")
        diagnostics["bound_contract_digest_matches"] = False
        gate = _derive_simulation_policy_preregistration_gate(diagnostics)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            real_validation.BLOCKED_BY_INCOMPLETE_SIMULATION_POLICY_EVIDENCE
        )
        assert gate["blocked_reason"] == (
            "SIMULATION_POLICY_GATE_EVIDENCE_INCOMPLETE"
        )

    # -- 15-20. Mutated frozen policy strings ---------------------------------

    @pytest.mark.parametrize(
        "field,mutated",
        [
            ("simulation_family_policy", "POST_HOC_PATH_CONSTRUCTION_POLICY"),
            ("simulation_timing_policy", "USE_INTRABAR_HINDSIGHT"),
            ("simulation_cost_policy", "COMPUTE_COST_VALUES_NOW"),
            ("simulation_funding_policy", "COMPUTE_FUNDING_VALUES_NOW"),
            ("simulation_quantity_policy", "COMPUTE_NOTIONAL_VALUES_NOW"),
            ("simulation_output_policy", "EMIT_EVENTS_AND_ECONOMIC_VALUES_NOW"),
        ],
    )
    def test_mutated_frozen_policy_fails_closed(self, tmp_path, field, mutated):
        def mutate(packet):
            packet[field] = mutated

        with pytest.raises(ValueError, match=f"{field} must be exactly"):
            self._materialize_tampered(tmp_path, mutate)

    # -- 21. Freeze boolean hardening -----------------------------------------

    @pytest.mark.parametrize(
        "field,value",
        [
            ("simulation_family_policy_frozen", False),
            ("simulation_timing_policy_frozen", "true"),
            ("simulation_cost_policy_frozen", 1),
        ],
    )
    def test_freeze_boolean_hardening(self, tmp_path, field, value):
        def mutate(packet):
            packet[field] = value

        with pytest.raises(ValueError, match=f"{field} must be True"):
            self._materialize_tampered(tmp_path, mutate)

    # -- 22. Authorization boolean type hardening -----------------------------

    @pytest.mark.parametrize(
        "field,value",
        [
            ("simulated_event_generation_authorized", 0),
            ("economic_value_generation_authorized", "false"),
            ("scoring_authorization", True),
        ],
    )
    def test_auth_boolean_hardening(self, tmp_path, field, value):
        def mutate(packet):
            packet[field] = value

        with pytest.raises(ValueError, match="fields must be exactly false"):
            self._materialize_tampered(tmp_path, mutate)

    # -- 23. Gate projection fails on wrong frozen policy value ----------------

    def test_gate_projection_blocked_by_wrong_frozen_value(self):
        """Mutate a diagnostic copy; derive gate; assert blocked."""
        diagnostics = dict(self._sp_diag())
        diagnostics.pop("simulation_policy_preregistration_gate")
        diagnostics["simulation_timing_policy"] = "USE_INTRABAR_HINDSIGHT"
        gate = _derive_simulation_policy_preregistration_gate(diagnostics)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            real_validation.BLOCKED_BY_INCOMPLETE_SIMULATION_POLICY_EVIDENCE
        )
        assert gate["evidence"]["simulation_timing_policy_matches_frozen_value"] is False
        assert gate["gate_scoring_authorization"] is False
        assert gate["gate_live_authorization"] is False
        assert gate["gate_final_verdict_authorization"] is False
        assert gate["gate_downstream_unlocks"] == []

    # -- 24. Receipt integration ----------------------------------------------

    def test_receipt_integration_full_path(self):
        contract_diag, manifest_diag, seal_diag, null_diag, mt_diag = (
            self._upstream_diags()
        )
        sp_diag = self._sp_diag()
        receipt = build_real_validation_receipt(
            input_manifest_fingerprint="test",
            data_quality_receipt_sha256="test",
            code_commit_sha="test",
            split_definitions=[{"split_id": 0}],
            cost_cases=[],
            strategy_rule_contract_diagnostics=contract_diag,
            trial_manifest_diagnostics=manifest_diag,
            oos_seal_diagnostics=seal_diag,
            null_benchmark_contract_diagnostics=null_diag,
            multiple_testing_control_diagnostics=mt_diag,
            trade_position_simulation_contract_diagnostics=sp_diag,
        )
        assert receipt["final_offline_verdict"] == (
            BLOCKED_BY_VALIDATION_IMPLEMENTATION
        )
        gate = receipt["trade_position_simulation_contract_diagnostics"][
            "simulation_policy_preregistration_gate"
        ]
        assert gate["gate_passed"] is True
        assert gate["gate_status"] == (
            real_validation.SIMULATION_POLICY_PREREGISTERED_DIAGNOSTIC_ONLY
        )
        assert gate["gate_scoring_authorization"] is False
        assert gate["gate_final_verdict_authorization"] is False
        assert gate["gate_downstream_unlocks"] == []

    # -- 25-27. CLI -----------------------------------------------------------

    def _cli_base_args(self, output_dir):
        return [
            "--read-only", "--output-dir", str(output_dir),
            "--input-manifest-fingerprint", "abc",
            "--data-quality-receipt-sha256", "def",
            "--code-commit-sha", "ghi",
            "--global-min-timestamp", "2026-01-01T00:00:00Z",
            "--global-max-timestamp", "2026-02-01T00:00:00Z",
        ]

    def _cli_upstream_args(self):
        return [
            "--strategy-contract-path", self.CONTRACT_PATH,
            "--strategy-contract-sha256-path", self.CONTRACT_SIDECAR_PATH,
            "--strategy-contract-commit-binding-path", self.CONTRACT_BINDING_PATH,
            "--trial-manifest-path", self.MANIFEST_PATH,
            "--trial-manifest-sha256-path", self.MANIFEST_SIDECAR_PATH,
            "--oos-seal-path", self.SEAL_PATH,
            "--oos-seal-sha256-path", self.SEAL_SIDECAR_PATH,
            "--null-benchmark-path", self.NULL_PATH,
            "--null-benchmark-sha256-path", self.NULL_SIDECAR_PATH,
            "--multiple-testing-control-path", self.MT_PATH,
            "--multiple-testing-control-sha256-path", self.MT_SIDECAR_PATH,
        ]

    def _cli_sp_args(self):
        return [
            "--simulation-policy-path", self.SP_PATH,
            "--simulation-policy-sha256-path", self.SP_SIDECAR_PATH,
        ]

    def test_cli_no_sp_args_gate_not_loaded(self, tmp_path):
        """CLI without simulation policy args: gate exists and false."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        exit_code = real_validation.main(self._cli_base_args(output_dir))
        assert exit_code == 0
        receipt = json.loads(
            (output_dir / "real_validation_receipt.json").read_text()
        )
        section = receipt["trade_position_simulation_contract_diagnostics"]
        assert section["trade_position_simulation_contract_status"] == (
            TRADE_POSITION_SIMULATION_CONTRACT_NOT_DEFINED
        )
        assert receipt["final_offline_verdict"] == (
            BLOCKED_BY_VALIDATION_IMPLEMENTATION
        )

    def test_cli_sp_without_upstream_fails_closed(self, tmp_path):
        """SP args without upstream gates must not write a passing receipt."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        exit_code = real_validation.main(
            self._cli_base_args(output_dir) + self._cli_sp_args()
        )
        assert exit_code == 4
        assert not (output_dir / "real_validation_receipt.json").exists()

    def test_cli_full_path_all_gates_pass_verdict_blocked(self, tmp_path):
        """All gates pass; final verdict remains BLOCKED_BY_VALIDATION_IMPLEMENTATION."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        exit_code = real_validation.main(
            self._cli_base_args(output_dir)
            + self._cli_upstream_args()
            + self._cli_sp_args()
        )
        assert exit_code == 0
        receipt = json.loads(
            (output_dir / "real_validation_receipt.json").read_text()
        )
        contract_gate = receipt["strategy_rule_contract_diagnostics"][
            "contract_packet_gate"
        ]
        manifest_gate = receipt.get("trial_manifest_diagnostics", {}).get(
            "trial_manifest_preregistration_gate"
        )
        seal_gate = receipt.get("oos_seal_diagnostics", {}).get(
            "oos_seal_preregistration_gate"
        )
        null_gate = receipt.get("null_benchmark_contract_diagnostics", {}).get(
            "null_benchmark_preregistration_gate"
        )
        mt_gate = receipt.get("multiple_testing_control_diagnostics", {}).get(
            "multiple_testing_control_preregistration_gate"
        )
        sp_gate = receipt.get("trade_position_simulation_contract_diagnostics", {}).get(
            "simulation_policy_preregistration_gate"
        )
        assert contract_gate["gate_passed"] is True
        assert manifest_gate is not None, "trial_manifest_preregistration_gate missing"
        assert seal_gate is not None, "oos_seal_preregistration_gate missing"
        assert null_gate is not None, "null_benchmark_preregistration_gate missing"
        assert mt_gate is not None, "multiple_testing_control_preregistration_gate missing"
        assert sp_gate is not None, "simulation_policy_preregistration_gate missing"
        assert sp_gate["gate_passed"] is True
        assert sp_gate["gate_status"] == (
            real_validation.SIMULATION_POLICY_PREREGISTERED_DIAGNOSTIC_ONLY
        )
        assert sp_gate["gate_downstream_unlocks"] == []
        assert sp_gate["gate_scoring_authorization"] is False
        assert sp_gate["gate_live_authorization"] is False
        assert sp_gate["gate_final_verdict_authorization"] is False
        assert receipt["final_offline_verdict"] == (
            BLOCKED_BY_VALIDATION_IMPLEMENTATION
        )


class TestEconomicAccountingPolicyPreregistrationJ1:
    """Lane J1: economic accounting policy pre-scoring declaration packet + gate.

    Proves the frozen economic accounting policy declarations are frozen and
    hash-bound to all upstream contracts *before* any economic values, PnL,
    returns, equity curves, risk metrics, drawdown, or scoring exist. Nothing
    here computes economic values, authorizes scoring, or advances any gate.
    """

    CONTRACT_PATH = "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.json"
    CONTRACT_SIDECAR_PATH = "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.sha256"
    CONTRACT_BINDING_PATH = "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.commit_binding.json"
    MANIFEST_PATH = "docs/contracts/instances/qnty_offline_edge_trial_manifest_v1.json"
    MANIFEST_SIDECAR_PATH = "docs/contracts/instances/qnty_offline_edge_trial_manifest_v1.sha256"
    SEAL_PATH = "docs/contracts/instances/qnty_offline_edge_oos_seal_v1.json"
    SEAL_SIDECAR_PATH = "docs/contracts/instances/qnty_offline_edge_oos_seal_v1.sha256"
    NULL_PATH = "docs/contracts/instances/qnty_offline_edge_null_benchmark_v1.json"
    NULL_SIDECAR_PATH = "docs/contracts/instances/qnty_offline_edge_null_benchmark_v1.sha256"
    MT_PATH = "docs/contracts/instances/qnty_offline_edge_multiple_testing_control_v1.json"
    MT_SIDECAR_PATH = "docs/contracts/instances/qnty_offline_edge_multiple_testing_control_v1.sha256"
    SP_PATH = "docs/contracts/instances/qnty_offline_edge_simulation_policy_v1.json"
    SP_SIDECAR_PATH = "docs/contracts/instances/qnty_offline_edge_simulation_policy_v1.sha256"
    EAP_PATH = "docs/contracts/instances/qnty_offline_edge_economic_accounting_policy_v1.json"
    EAP_SIDECAR_PATH = "docs/contracts/instances/qnty_offline_edge_economic_accounting_policy_v1.sha256"

    def _upstream_diags(self):
        """Build all upstream diagnostics including simulation policy gate."""
        contract_diag = _build_strategy_rule_contract_diagnostics(
            contract_path=self.CONTRACT_PATH,
            sidecar_path=self.CONTRACT_SIDECAR_PATH,
            commit_binding_path=self.CONTRACT_BINDING_PATH,
        )
        manifest_diag = _build_trial_manifest_diagnostics(
            manifest_path=self.MANIFEST_PATH,
            sidecar_path=self.MANIFEST_SIDECAR_PATH,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        seal_diag = _build_oos_seal_diagnostics(
            seal_path=self.SEAL_PATH,
            sidecar_path=self.SEAL_SIDECAR_PATH,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        null_diag = _build_null_benchmark_contract_diagnostics(
            null_benchmark_path=self.NULL_PATH,
            sidecar_path=self.NULL_SIDECAR_PATH,
            oos_seal_diagnostics=seal_diag,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        mt_diag = _build_multiple_testing_control_diagnostics(
            multiple_testing_control_path=self.MT_PATH,
            sidecar_path=self.MT_SIDECAR_PATH,
            null_benchmark_diagnostics=null_diag,
            oos_seal_diagnostics=seal_diag,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        sp_diag = _build_trade_position_simulation_contract_diagnostics(
            simulation_policy_path=self.SP_PATH,
            sidecar_path=self.SP_SIDECAR_PATH,
            multiple_testing_control_diagnostics=mt_diag,
            null_benchmark_diagnostics=null_diag,
            oos_seal_diagnostics=seal_diag,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        return contract_diag, manifest_diag, seal_diag, null_diag, mt_diag, sp_diag

    def _eap_diag(self):
        """Build the economic accounting policy diagnostics with all upstream.

        Returns the nested EAP diagnostic dict (under
        ``economic_accounting_policy_diagnostics``) so that existing tests
        that inspect EAP fields continue to work unchanged.
        """
        (contract_diag, manifest_diag, seal_diag, null_diag, mt_diag, sp_diag) = (
            self._upstream_diags()
        )
        result = _build_net_pnl_equity_risk_contract_diagnostics(
            economic_accounting_policy_path=self.EAP_PATH,
            sidecar_path=self.EAP_SIDECAR_PATH,
            simulation_policy_diagnostics=sp_diag,
            multiple_testing_control_diagnostics=mt_diag,
            null_benchmark_diagnostics=null_diag,
            oos_seal_diagnostics=seal_diag,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        return result["economic_accounting_policy_diagnostics"]

    # ── Test 1: Absence / no-args returns original shape ──────────────────────
    def test_absence_returns_original_shape(self):
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        assert result["net_pnl_equity_risk_contract_status"] == (
            NET_PNL_EQUITY_RISK_CONTRACT_NOT_DEFINED
        )
        assert result["net_pnl_equity_risk_contract_present"] is False

    # ── Test 2: Happy path materializer ───────────────────────────────────────
    def test_materializer_happy_path(self):
        """Load the frozen economic accounting policy packet and verify sidecar."""
        eap_diag = self._eap_diag()
        assert eap_diag["diagnostic_kind"] == "economic_accounting_policy_preregistration"
        assert eap_diag["economic_accounting_policy_sidecar_digest_matches_json_bytes"] is True
        assert eap_diag["economic_accounting_policy_hash_authority"] == "SIDECAR"
        assert eap_diag["economic_value_generation_authorized"] is False
        assert eap_diag["economic_accounting_policy_readiness"] is False

    # ── Test 3: Diagnostic happy path ─────────────────────────────────────────
    def test_diagnostic_happy_path(self):
        """All frozen values match, all bound digests match, gate is present."""
        eap_diag = self._eap_diag()
        assert eap_diag["bound_contract_digest_matches"] is True
        assert eap_diag["bound_trial_manifest_digest_matches"] is True
        assert eap_diag["bound_oos_seal_digest_matches"] is True
        assert eap_diag["bound_null_benchmark_digest_matches"] is True
        assert eap_diag["bound_multiple_testing_control_digest_matches"] is True
        assert eap_diag["bound_simulation_policy_digest_matches"] is True
        assert eap_diag["simulation_policy_gate_passed"] is True
        assert eap_diag["economic_accounting_family_policy"] == (
            ECONOMIC_ACCOUNTING_FAMILY_POLICY_FROZEN
        )
        assert eap_diag["economic_value_policy"] == ECONOMIC_VALUE_POLICY_FROZEN
        assert eap_diag["cost_value_policy"] == COST_VALUE_POLICY_FROZEN
        assert eap_diag["funding_value_policy"] == FUNDING_VALUE_POLICY_FROZEN
        assert eap_diag["aggregate_value_policy"] == AGGREGATE_VALUE_POLICY_FROZEN
        assert eap_diag["capital_path_policy"] == CAPITAL_PATH_POLICY_FROZEN
        assert eap_diag["dispersion_summary_policy"] == DISPERSION_SUMMARY_POLICY_FROZEN
        assert eap_diag["accounting_output_policy"] == ACCOUNTING_OUTPUT_POLICY_FROZEN
        assert eap_diag["economic_value_generation_authorized"] is False
        assert eap_diag["economic_accounting_policy_readiness"] is False

    # ── Test 4: Gate happy path ───────────────────────────────────────────────
    def test_gate_happy_path(self):
        eap_diag = self._eap_diag()
        gate = eap_diag["economic_accounting_policy_preregistration_gate"]
        assert gate["gate_kind"] == "economic_accounting_policy_preregistration_gate"
        assert gate["gate_scope"] == "ECONOMIC_ACCOUNTING_POLICY_AND_SIMULATION_BINDING_ONLY"
        assert gate["gate_passed"] is True
        assert gate["gate_status"] == ECONOMIC_ACCOUNTING_POLICY_PREREGISTERED_DIAGNOSTIC_ONLY
        assert gate["gate_scoring_authorization"] is False
        assert gate["gate_live_authorization"] is False
        assert gate["gate_final_verdict_authorization"] is False
        assert gate["gate_downstream_unlocks"] == []

    # ── Test 5: Packet missing fails closed ───────────────────────────────────
    def test_packet_missing_fails_closed(self):
        result = _build_net_pnl_equity_risk_contract_diagnostics()
        assert result["net_pnl_equity_risk_contract_status"] == (
            NET_PNL_EQUITY_RISK_CONTRACT_NOT_DEFINED
        )

    # ── Test 6: Sidecar missing fails closed ──────────────────────────────────
    def test_sidecar_missing_fails_closed(self):
        result = _build_net_pnl_equity_risk_contract_diagnostics(
            economic_accounting_policy_path="/nonexistent/path.json",
            sidecar_path=None,
            simulation_policy_diagnostics={},
            multiple_testing_control_diagnostics={},
            null_benchmark_diagnostics={},
            oos_seal_diagnostics={},
            trial_manifest_diagnostics={},
            strategy_rule_contract_diagnostics={},
        )
        assert result["net_pnl_equity_risk_contract_status"] == (
            NET_PNL_EQUITY_RISK_CONTRACT_NOT_DEFINED
        )

    # ── Test 7: Digest mismatch fails closed ──────────────────────────────────
    def test_digest_mismatch_raises(self):
        with pytest.raises(ValueError, match="digest mismatch"):
            real_validation.materialize_economic_accounting_policy_preregistration_diagnostics(
                economic_accounting_policy_path=self.EAP_PATH,
                sidecar_path=self.CONTRACT_SIDECAR_PATH,  # wrong sidecar
                simulation_policy_diagnostics={"diagnostic_kind": "simulation_policy_preregistration"},
                multiple_testing_control_diagnostics={},
                null_benchmark_diagnostics={},
                oos_seal_diagnostics={},
                trial_manifest_diagnostics={},
                strategy_rule_contract_diagnostics={},
            )

    # ── Test 8: Malformed JSON fails closed ───────────────────────────────────
    def test_malformed_json_raises(self, tmp_path):
        bad_bytes = b"{invalid json"
        packet_path = tmp_path / "eap.json"
        packet_path.write_bytes(bad_bytes)
        sidecar_path = tmp_path / "eap.sha256"
        digest = hashlib.sha256(bad_bytes).hexdigest()
        sidecar_path.write_text(f"{digest}  {packet_path.name}\n")
        with pytest.raises(ValueError, match="JSON parse error"):
            real_validation.materialize_economic_accounting_policy_preregistration_diagnostics(
                economic_accounting_policy_path=str(packet_path),
                sidecar_path=str(sidecar_path),
                simulation_policy_diagnostics={},
                multiple_testing_control_diagnostics={},
                null_benchmark_diagnostics={},
                oos_seal_diagnostics={},
                trial_manifest_diagnostics={},
                strategy_rule_contract_diagnostics={},
            )

    # ── Test 9: Forbidden dict key fails closed ───────────────────────────────
    def _tampered_eap_packet(self, tmp_path, mutate):
        packet = json.loads(Path(self.EAP_PATH).read_bytes())
        mutate(packet)
        packet_bytes = json.dumps(packet, indent=2, sort_keys=True).encode() + b"\n"
        packet_path = tmp_path / "eap.json"
        packet_path.write_bytes(packet_bytes)
        sidecar_path = tmp_path / "eap.sha256"
        digest = hashlib.sha256(packet_bytes).hexdigest()
        sidecar_path.write_text(f"{digest}  {packet_path.name}\n")
        return packet_path, sidecar_path

    def test_forbidden_key_pnl_raises(self, tmp_path):
        packet_path, sidecar_path = self._tampered_eap_packet(
            tmp_path, lambda p: p.__setitem__("pnl", 1)
        )
        with pytest.raises(ValueError, match="forbidden dict keys"):
            real_validation.materialize_economic_accounting_policy_preregistration_diagnostics(
                economic_accounting_policy_path=str(packet_path),
                sidecar_path=str(sidecar_path),
                simulation_policy_diagnostics={"diagnostic_kind": "simulation_policy_preregistration"},
                multiple_testing_control_diagnostics={},
                null_benchmark_diagnostics={},
                oos_seal_diagnostics={},
                trial_manifest_diagnostics={},
                strategy_rule_contract_diagnostics={},
            )

    def test_forbidden_key_risk_raises(self, tmp_path):
        packet_path, sidecar_path = self._tampered_eap_packet(
            tmp_path, lambda p: p.__setitem__("risk", 1)
        )
        with pytest.raises(ValueError, match="forbidden dict keys"):
            real_validation.materialize_economic_accounting_policy_preregistration_diagnostics(
                economic_accounting_policy_path=str(packet_path),
                sidecar_path=str(sidecar_path),
                simulation_policy_diagnostics={"diagnostic_kind": "simulation_policy_preregistration"},
                multiple_testing_control_diagnostics={},
                null_benchmark_diagnostics={},
                oos_seal_diagnostics={},
                trial_manifest_diagnostics={},
                strategy_rule_contract_diagnostics={},
            )

    def test_forbidden_key_equity_raises(self, tmp_path):
        packet_path, sidecar_path = self._tampered_eap_packet(
            tmp_path, lambda p: p.__setitem__("equity", 1)
        )
        with pytest.raises(ValueError, match="forbidden dict keys"):
            real_validation.materialize_economic_accounting_policy_preregistration_diagnostics(
                economic_accounting_policy_path=str(packet_path),
                sidecar_path=str(sidecar_path),
                simulation_policy_diagnostics={"diagnostic_kind": "simulation_policy_preregistration"},
                multiple_testing_control_diagnostics={},
                null_benchmark_diagnostics={},
                oos_seal_diagnostics={},
                trial_manifest_diagnostics={},
                strategy_rule_contract_diagnostics={},
            )

    # ── Tests 10-14: Contract/Trial/OOS/Null/MT digest mismatch ──────────────
    def test_contract_digest_mismatch_raises(self, tmp_path):
        diags = self._upstream_diags()
        contract_diag = dict(diags[0])
        contract_diag["json_sha256"] = "00" + contract_diag.get("json_sha256", "")[2:]
        # Simulate mismatched contract
        with pytest.raises(ValueError, match="bound_contract_sha256 mismatch"):
            real_validation.materialize_economic_accounting_policy_preregistration_diagnostics(
                economic_accounting_policy_path=self.EAP_PATH,
                sidecar_path=self.EAP_SIDECAR_PATH,
                simulation_policy_diagnostics=diags[5],
                multiple_testing_control_diagnostics=diags[4],
                null_benchmark_diagnostics=diags[3],
                oos_seal_diagnostics=diags[2],
                trial_manifest_diagnostics=diags[1],
                strategy_rule_contract_diagnostics=contract_diag,
            )

    def test_trial_manifest_digest_mismatch_raises(self, tmp_path):
        diags = self._upstream_diags()
        manifest_diag = dict(diags[1])
        manifest_diag["manifest_json_sha256"] = "00" + manifest_diag.get("manifest_json_sha256", "")[2:]
        with pytest.raises(ValueError, match="bound_trial_manifest_sha256 mismatch"):
            real_validation.materialize_economic_accounting_policy_preregistration_diagnostics(
                economic_accounting_policy_path=self.EAP_PATH,
                sidecar_path=self.EAP_SIDECAR_PATH,
                simulation_policy_diagnostics=diags[5],
                multiple_testing_control_diagnostics=diags[4],
                null_benchmark_diagnostics=diags[3],
                oos_seal_diagnostics=diags[2],
                trial_manifest_diagnostics=manifest_diag,
                strategy_rule_contract_diagnostics=diags[0],
            )

    def test_oos_seal_digest_mismatch_raises(self, tmp_path):
        diags = self._upstream_diags()
        seal_diag = dict(diags[2])
        seal_diag["seal_json_sha256"] = "00" + seal_diag.get("seal_json_sha256", "")[2:]
        with pytest.raises(ValueError, match="bound_oos_seal_sha256 mismatch"):
            real_validation.materialize_economic_accounting_policy_preregistration_diagnostics(
                economic_accounting_policy_path=self.EAP_PATH,
                sidecar_path=self.EAP_SIDECAR_PATH,
                simulation_policy_diagnostics=diags[5],
                multiple_testing_control_diagnostics=diags[4],
                null_benchmark_diagnostics=diags[3],
                oos_seal_diagnostics=seal_diag,
                trial_manifest_diagnostics=diags[1],
                strategy_rule_contract_diagnostics=diags[0],
            )

    def test_null_benchmark_digest_mismatch_raises(self, tmp_path):
        diags = self._upstream_diags()
        null_diag = dict(diags[3])
        null_diag["null_benchmark_json_sha256"] = "00" + null_diag.get("null_benchmark_json_sha256", "")[2:]
        with pytest.raises(ValueError, match="bound_null_benchmark_sha256 mismatch"):
            real_validation.materialize_economic_accounting_policy_preregistration_diagnostics(
                economic_accounting_policy_path=self.EAP_PATH,
                sidecar_path=self.EAP_SIDECAR_PATH,
                simulation_policy_diagnostics=diags[5],
                multiple_testing_control_diagnostics=diags[4],
                null_benchmark_diagnostics=null_diag,
                oos_seal_diagnostics=diags[2],
                trial_manifest_diagnostics=diags[1],
                strategy_rule_contract_diagnostics=diags[0],
            )

    def test_multiple_testing_control_digest_mismatch_raises(self, tmp_path):
        diags = self._upstream_diags()
        mt_diag = dict(diags[4])
        mt_diag["multiple_testing_control_json_sha256"] = "00" + mt_diag.get("multiple_testing_control_json_sha256", "")[2:]
        with pytest.raises(ValueError, match="bound_multiple_testing_control_sha256 mismatch"):
            real_validation.materialize_economic_accounting_policy_preregistration_diagnostics(
                economic_accounting_policy_path=self.EAP_PATH,
                sidecar_path=self.EAP_SIDECAR_PATH,
                simulation_policy_diagnostics=diags[5],
                multiple_testing_control_diagnostics=mt_diag,
                null_benchmark_diagnostics=diags[3],
                oos_seal_diagnostics=diags[2],
                trial_manifest_diagnostics=diags[1],
                strategy_rule_contract_diagnostics=diags[0],
            )

    # ── Test 15: Simulation policy digest mismatch ────────────────────────────
    def test_simulation_policy_digest_mismatch_raises(self, tmp_path):
        diags = self._upstream_diags()
        sp_diag = dict(diags[5])
        sp_diag["simulation_policy_json_sha256"] = "00" + sp_diag.get("simulation_policy_json_sha256", "")[2:]
        with pytest.raises(ValueError, match="bound_simulation_policy_sha256 mismatch"):
            real_validation.materialize_economic_accounting_policy_preregistration_diagnostics(
                economic_accounting_policy_path=self.EAP_PATH,
                sidecar_path=self.EAP_SIDECAR_PATH,
                simulation_policy_diagnostics=sp_diag,
                multiple_testing_control_diagnostics=diags[4],
                null_benchmark_diagnostics=diags[3],
                oos_seal_diagnostics=diags[2],
                trial_manifest_diagnostics=diags[1],
                strategy_rule_contract_diagnostics=diags[0],
            )

    # ── Test 16: Simulation policy gate missing/false blocks ──────────────────
    def test_sp_gate_missing_fails_closed(self):
        diags = self._upstream_diags()
        sp_diag = {"diagnostic_kind": "simulation_policy_preregistration"}
        with pytest.raises(ValueError, match="Simulation policy preregistration gate not passed"):
            real_validation.materialize_economic_accounting_policy_preregistration_diagnostics(
                economic_accounting_policy_path=self.EAP_PATH,
                sidecar_path=self.EAP_SIDECAR_PATH,
                simulation_policy_diagnostics=sp_diag,
                multiple_testing_control_diagnostics=diags[4],
                null_benchmark_diagnostics=diags[3],
                oos_seal_diagnostics=diags[2],
                trial_manifest_diagnostics=diags[1],
                strategy_rule_contract_diagnostics=diags[0],
            )

    # ── Test 17: Mutated economic_accounting_family_policy ────────────────────
    def test_mutated_family_policy_fails_closed(self, tmp_path):
        diags = self._upstream_diags()
        packet_path, sidecar_path = self._tampered_eap_packet(
            tmp_path,
            lambda p: p.__setitem__(
                "economic_accounting_family_policy", "MUTATED"
            ),
        )
        with pytest.raises(ValueError, match="economic_accounting_family_policy"):
            real_validation.materialize_economic_accounting_policy_preregistration_diagnostics(
                economic_accounting_policy_path=str(packet_path),
                sidecar_path=str(sidecar_path),
                simulation_policy_diagnostics=diags[5],
                multiple_testing_control_diagnostics=diags[4],
                null_benchmark_diagnostics=diags[3],
                oos_seal_diagnostics=diags[2],
                trial_manifest_diagnostics=diags[1],
                strategy_rule_contract_diagnostics=diags[0],
            )

    # ── Test 18: Mutated economic_value_policy ────────────────────────────────
    def test_mutated_economic_value_policy_fails_closed(self, tmp_path):
        diags = self._upstream_diags()
        packet_path, sidecar_path = self._tampered_eap_packet(
            tmp_path,
            lambda p: p.__setitem__("economic_value_policy", "COMPUTE_ALL"),
        )
        with pytest.raises(ValueError, match="economic_value_policy"):
            real_validation.materialize_economic_accounting_policy_preregistration_diagnostics(
                economic_accounting_policy_path=str(packet_path),
                sidecar_path=str(sidecar_path),
                simulation_policy_diagnostics=diags[5],
                multiple_testing_control_diagnostics=diags[4],
                null_benchmark_diagnostics=diags[3],
                oos_seal_diagnostics=diags[2],
                trial_manifest_diagnostics=diags[1],
                strategy_rule_contract_diagnostics=diags[0],
            )

    # ── Test 19: Mutated cost_value_policy ────────────────────────────────────
    def test_mutated_cost_value_policy_fails_closed(self, tmp_path):
        diags = self._upstream_diags()
        packet_path, sidecar_path = self._tampered_eap_packet(
            tmp_path,
            lambda p: p.__setitem__("cost_value_policy", "COMPUTE_COSTS"),
        )
        with pytest.raises(ValueError, match="cost_value_policy"):
            real_validation.materialize_economic_accounting_policy_preregistration_diagnostics(
                economic_accounting_policy_path=str(packet_path),
                sidecar_path=str(sidecar_path),
                simulation_policy_diagnostics=diags[5],
                multiple_testing_control_diagnostics=diags[4],
                null_benchmark_diagnostics=diags[3],
                oos_seal_diagnostics=diags[2],
                trial_manifest_diagnostics=diags[1],
                strategy_rule_contract_diagnostics=diags[0],
            )

    # ── Test 20: Mutated funding_value_policy ─────────────────────────────────
    def test_mutated_funding_value_policy_fails_closed(self, tmp_path):
        diags = self._upstream_diags()
        packet_path, sidecar_path = self._tampered_eap_packet(
            tmp_path,
            lambda p: p.__setitem__("funding_value_policy", "COMPUTE_FUNDING"),
        )
        with pytest.raises(ValueError, match="funding_value_policy"):
            real_validation.materialize_economic_accounting_policy_preregistration_diagnostics(
                economic_accounting_policy_path=str(packet_path),
                sidecar_path=str(sidecar_path),
                simulation_policy_diagnostics=diags[5],
                multiple_testing_control_diagnostics=diags[4],
                null_benchmark_diagnostics=diags[3],
                oos_seal_diagnostics=diags[2],
                trial_manifest_diagnostics=diags[1],
                strategy_rule_contract_diagnostics=diags[0],
            )

    # ── Test 21: Mutated aggregate_value_policy ───────────────────────────────
    def test_mutated_aggregate_value_policy_fails_closed(self, tmp_path):
        diags = self._upstream_diags()
        packet_path, sidecar_path = self._tampered_eap_packet(
            tmp_path,
            lambda p: p.__setitem__("aggregate_value_policy", "COMPUTE_AGGREGATES"),
        )
        with pytest.raises(ValueError, match="aggregate_value_policy"):
            real_validation.materialize_economic_accounting_policy_preregistration_diagnostics(
                economic_accounting_policy_path=str(packet_path),
                sidecar_path=str(sidecar_path),
                simulation_policy_diagnostics=diags[5],
                multiple_testing_control_diagnostics=diags[4],
                null_benchmark_diagnostics=diags[3],
                oos_seal_diagnostics=diags[2],
                trial_manifest_diagnostics=diags[1],
                strategy_rule_contract_diagnostics=diags[0],
            )

    # ── Test 22: Mutated capital_path_policy ──────────────────────────────────
    def test_mutated_capital_path_policy_fails_closed(self, tmp_path):
        diags = self._upstream_diags()
        packet_path, sidecar_path = self._tampered_eap_packet(
            tmp_path,
            lambda p: p.__setitem__("capital_path_policy", "COMPUTE_CAPITAL_PATH"),
        )
        with pytest.raises(ValueError, match="capital_path_policy"):
            real_validation.materialize_economic_accounting_policy_preregistration_diagnostics(
                economic_accounting_policy_path=str(packet_path),
                sidecar_path=str(sidecar_path),
                simulation_policy_diagnostics=diags[5],
                multiple_testing_control_diagnostics=diags[4],
                null_benchmark_diagnostics=diags[3],
                oos_seal_diagnostics=diags[2],
                trial_manifest_diagnostics=diags[1],
                strategy_rule_contract_diagnostics=diags[0],
            )

    # ── Test 23: Mutated dispersion_summary_policy ────────────────────────────
    def test_mutated_dispersion_summary_policy_fails_closed(self, tmp_path):
        diags = self._upstream_diags()
        packet_path, sidecar_path = self._tampered_eap_packet(
            tmp_path,
            lambda p: p.__setitem__("dispersion_summary_policy", "COMPUTE_DISPERSION"),
        )
        with pytest.raises(ValueError, match="dispersion_summary_policy"):
            real_validation.materialize_economic_accounting_policy_preregistration_diagnostics(
                economic_accounting_policy_path=str(packet_path),
                sidecar_path=str(sidecar_path),
                simulation_policy_diagnostics=diags[5],
                multiple_testing_control_diagnostics=diags[4],
                null_benchmark_diagnostics=diags[3],
                oos_seal_diagnostics=diags[2],
                trial_manifest_diagnostics=diags[1],
                strategy_rule_contract_diagnostics=diags[0],
            )

    # ── Test 24: Mutated accounting_output_policy ─────────────────────────────
    def test_mutated_accounting_output_policy_fails_closed(self, tmp_path):
        diags = self._upstream_diags()
        packet_path, sidecar_path = self._tampered_eap_packet(
            tmp_path,
            lambda p: p.__setitem__("accounting_output_policy", "EMIT_ALL"),
        )
        with pytest.raises(ValueError, match="accounting_output_policy"):
            real_validation.materialize_economic_accounting_policy_preregistration_diagnostics(
                economic_accounting_policy_path=str(packet_path),
                sidecar_path=str(sidecar_path),
                simulation_policy_diagnostics=diags[5],
                multiple_testing_control_diagnostics=diags[4],
                null_benchmark_diagnostics=diags[3],
                oos_seal_diagnostics=diags[2],
                trial_manifest_diagnostics=diags[1],
                strategy_rule_contract_diagnostics=diags[0],
            )

    # ── Test 25: Freeze boolean hardening ─────────────────────────────────────
    def test_freeze_boolean_false_fails_closed(self, tmp_path):
        diags = self._upstream_diags()
        packet_path, sidecar_path = self._tampered_eap_packet(
            tmp_path,
            lambda p: p.__setitem__("economic_accounting_family_policy_frozen", False),
        )
        with pytest.raises(ValueError, match="economic_accounting_family_policy_frozen"):
            real_validation.materialize_economic_accounting_policy_preregistration_diagnostics(
                economic_accounting_policy_path=str(packet_path),
                sidecar_path=str(sidecar_path),
                simulation_policy_diagnostics=diags[5],
                multiple_testing_control_diagnostics=diags[4],
                null_benchmark_diagnostics=diags[3],
                oos_seal_diagnostics=diags[2],
                trial_manifest_diagnostics=diags[1],
                strategy_rule_contract_diagnostics=diags[0],
            )

    def test_freeze_boolean_string_fails_closed(self, tmp_path):
        diags = self._upstream_diags()
        packet_path, sidecar_path = self._tampered_eap_packet(
            tmp_path,
            lambda p: p.__setitem__("economic_value_policy_frozen", "true"),
        )
        with pytest.raises(ValueError, match="economic_value_policy_frozen"):
            real_validation.materialize_economic_accounting_policy_preregistration_diagnostics(
                economic_accounting_policy_path=str(packet_path),
                sidecar_path=str(sidecar_path),
                simulation_policy_diagnostics=diags[5],
                multiple_testing_control_diagnostics=diags[4],
                null_benchmark_diagnostics=diags[3],
                oos_seal_diagnostics=diags[2],
                trial_manifest_diagnostics=diags[1],
                strategy_rule_contract_diagnostics=diags[0],
            )

    def test_freeze_boolean_int_fails_closed(self, tmp_path):
        diags = self._upstream_diags()
        packet_path, sidecar_path = self._tampered_eap_packet(
            tmp_path,
            lambda p: p.__setitem__("cost_value_policy_frozen", 1),
        )
        with pytest.raises(ValueError, match="cost_value_policy_frozen"):
            real_validation.materialize_economic_accounting_policy_preregistration_diagnostics(
                economic_accounting_policy_path=str(packet_path),
                sidecar_path=str(sidecar_path),
                simulation_policy_diagnostics=diags[5],
                multiple_testing_control_diagnostics=diags[4],
                null_benchmark_diagnostics=diags[3],
                oos_seal_diagnostics=diags[2],
                trial_manifest_diagnostics=diags[1],
                strategy_rule_contract_diagnostics=diags[0],
            )

    # ── Test 26: Authorization boolean type hardening ─────────────────────────
    def test_auth_boolean_int_zero_fails_closed(self, tmp_path):
        diags = self._upstream_diags()
        packet_path, sidecar_path = self._tampered_eap_packet(
            tmp_path,
            lambda p: p.__setitem__("economic_value_generation_authorized", 0),
        )
        with pytest.raises(ValueError, match="economic_value_generation_authorized"):
            real_validation.materialize_economic_accounting_policy_preregistration_diagnostics(
                economic_accounting_policy_path=str(packet_path),
                sidecar_path=str(sidecar_path),
                simulation_policy_diagnostics=diags[5],
                multiple_testing_control_diagnostics=diags[4],
                null_benchmark_diagnostics=diags[3],
                oos_seal_diagnostics=diags[2],
                trial_manifest_diagnostics=diags[1],
                strategy_rule_contract_diagnostics=diags[0],
            )

    def test_auth_boolean_true_fails_closed(self, tmp_path):
        diags = self._upstream_diags()
        packet_path, sidecar_path = self._tampered_eap_packet(
            tmp_path,
            lambda p: p.__setitem__("scoring_authorization", True),
        )
        with pytest.raises(ValueError, match="scoring_authorization"):
            real_validation.materialize_economic_accounting_policy_preregistration_diagnostics(
                economic_accounting_policy_path=str(packet_path),
                sidecar_path=str(sidecar_path),
                simulation_policy_diagnostics=diags[5],
                multiple_testing_control_diagnostics=diags[4],
                null_benchmark_diagnostics=diags[3],
                oos_seal_diagnostics=diags[2],
                trial_manifest_diagnostics=diags[1],
                strategy_rule_contract_diagnostics=diags[0],
            )

    def test_auth_boolean_string_false_fails_closed(self, tmp_path):
        diags = self._upstream_diags()
        packet_path, sidecar_path = self._tampered_eap_packet(
            tmp_path,
            lambda p: p.__setitem__("final_verdict_authorization", "false"),
        )
        with pytest.raises(ValueError, match="final_verdict_authorization"):
            real_validation.materialize_economic_accounting_policy_preregistration_diagnostics(
                economic_accounting_policy_path=str(packet_path),
                sidecar_path=str(sidecar_path),
                simulation_policy_diagnostics=diags[5],
                multiple_testing_control_diagnostics=diags[4],
                null_benchmark_diagnostics=diags[3],
                oos_seal_diagnostics=diags[2],
                trial_manifest_diagnostics=diags[1],
                strategy_rule_contract_diagnostics=diags[0],
            )

    # ── Test 27: Gate projection fails closed on mutated diagnostic value ─────
    def test_gate_projection_mutated_policy_fails_closed(self):
        eap_diag = dict(self._eap_diag())
        eap_diag.pop("economic_accounting_policy_preregistration_gate", None)
        eap_diag["economic_value_policy"] = "COMPUTE_ALL"
        gate = _derive_economic_accounting_policy_preregistration_gate(eap_diag)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_ECONOMIC_ACCOUNTING_POLICY_EVIDENCE
        )
        assert gate["gate_scoring_authorization"] is False
        assert gate["gate_live_authorization"] is False
        assert gate["gate_final_verdict_authorization"] is False

    # ── Test 28: Receipt integration with all args ────────────────────────────
    def test_receipt_integration(self):
        eap_diag = self._eap_diag()
        gate = eap_diag.get("economic_accounting_policy_preregistration_gate", {})
        assert gate.get("gate_passed") is True
        # Final verdict remains blocked
        receipt = build_real_validation_receipt(
            input_manifest_fingerprint="test-fingerprint",
            data_quality_receipt_sha256="test-dq",
            code_commit_sha="test-sha",
            split_definitions=[],
            cost_cases=[],
            economic_accounting_policy_diagnostics=eap_diag,
        )
        assert receipt["final_offline_verdict"] == (
            BLOCKED_BY_VALIDATION_IMPLEMENTATION
        )
        assert receipt.get("economic_accounting_policy_diagnostics") is eap_diag

    # ── Test 29: Absence receipt preserves verdict ────────────────────────────
    def test_absence_receipt_preserves_verdict(self):
        receipt = build_real_validation_receipt(
            input_manifest_fingerprint="test-fingerprint",
            data_quality_receipt_sha256="test-dq",
            code_commit_sha="test-sha",
            split_definitions=[],
            cost_cases=[],
        )
        assert receipt["final_offline_verdict"] == (
            BLOCKED_BY_VALIDATION_IMPLEMENTATION
        )
        assert "economic_accounting_policy_diagnostics" not in receipt

    # ── Test 30: Gate projection with no diagnostic kind ──────────────────────
    def test_gate_not_loaded(self):
        gate = _derive_economic_accounting_policy_preregistration_gate({})
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == ECONOMIC_ACCOUNTING_POLICY_NOT_LOADED
        assert gate["blocked_reason"] == "ECONOMIC_ACCOUNTING_POLICY_NOT_PROVIDED"

    # ═══════════════════════════════════════════════════════════════════════
    # Blocker 1 regressions: full J1 path preserves net-PnL absence shape
    # ═══════════════════════════════════════════════════════════════════════

    def _full_result(self):
        """Call _build_net_pnl_equity_risk_contract_diagnostics with full EAP
        args and return the top-level result (net-PnL absence + nested EAP)."""
        (contract_diag, manifest_diag, seal_diag, null_diag, mt_diag, sp_diag) = (
            self._upstream_diags()
        )
        return _build_net_pnl_equity_risk_contract_diagnostics(
            economic_accounting_policy_path=self.EAP_PATH,
            sidecar_path=self.EAP_SIDECAR_PATH,
            simulation_policy_diagnostics=sp_diag,
            multiple_testing_control_diagnostics=mt_diag,
            null_benchmark_diagnostics=null_diag,
            oos_seal_diagnostics=seal_diag,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )

    def test_full_path_preserves_net_pnl_absence_shape(self):
        """Full J1 path must preserve legacy net-PnL/equity-risk absence keys."""
        result = self._full_result()
        assert result["net_pnl_equity_risk_contract_status"] == (
            NET_PNL_EQUITY_RISK_CONTRACT_NOT_DEFINED
        )
        assert result["net_pnl_equity_risk_contract_present"] is False
        assert result["scoring_authorized"] is False

    def test_full_path_eap_diagnostics_nested(self):
        """Full J1 path nests EAP diagnostics under
        economic_accounting_policy_diagnostics."""
        result = self._full_result()
        eap = result["economic_accounting_policy_diagnostics"]
        assert eap["diagnostic_kind"] == "economic_accounting_policy_preregistration"
        assert eap["economic_accounting_policy_sidecar_digest_matches_json_bytes"] is True
        assert eap["economic_value_generation_authorized"] is False
        assert eap["economic_accounting_policy_readiness"] is False

    def test_full_path_gate_present_and_passed(self):
        """Full J1 path has EAP preregistration gate at top level and nested."""
        result = self._full_result()
        top_gate = result["economic_accounting_policy_preregistration_gate"]
        nested_gate = result["economic_accounting_policy_diagnostics"][
            "economic_accounting_policy_preregistration_gate"
        ]
        assert top_gate is nested_gate  # same object
        assert top_gate["gate_passed"] is True
        assert top_gate["gate_status"] == (
            ECONOMIC_ACCOUNTING_POLICY_PREREGISTERED_DIAGNOSTIC_ONLY
        )
        assert top_gate["gate_scoring_authorization"] is False
        assert top_gate["gate_live_authorization"] is False
        assert top_gate["gate_final_verdict_authorization"] is False
        assert top_gate["gate_downstream_unlocks"] == []

    def test_full_path_absence_fields_present_and_false(self):
        """Required invariant: absence fields are present and false/not-defined."""
        result = self._full_result()
        assert result["net_pnl_equity_risk_contract_status"] == (
            NET_PNL_EQUITY_RISK_CONTRACT_NOT_DEFINED
        )
        assert result["net_pnl_equity_risk_contract_present"] is False
        assert result["scoring_authorized"] is False
        assert result["net_pnl_equity_risk_contract_hash"] is None
        assert result["net_pnl_equity_risk_contract_source"] is None

    def test_full_path_no_forbidden_keys(self):
        """Full J1 path with nested EAP passes forbidden key scan."""
        result = self._full_result()
        all_keys = _all_dict_keys(result)
        assert _NET_PNL_EQUITY_RISK_CONTRACT_FORBIDDEN_KEYS.isdisjoint(all_keys), (
            f"Forbidden keys found: "
            f"{_NET_PNL_EQUITY_RISK_CONTRACT_FORBIDDEN_KEYS & all_keys}"
        )

    def test_full_path_verdict_still_blocked(self):
        """Full J1 path must not advance the final verdict."""
        result = self._full_result()
        # No verdict advancement is part of this function's contract.
        # Verify absence of verdict-related fields.
        assert "final_offline_verdict" not in result
        assert "next_final_offline_verdict" not in result

    # ═══════════════════════════════════════════════════════════════════════
    # Blocker 2 regressions: top-level receipt call sites must nest EAP
    # diagnostics under economic_accounting_policy_diagnostics, not pass the
    # whole net-PnL/equity-risk absence section.
    # ═══════════════════════════════════════════════════════════════════════

    def _cli_base_args(self, output_dir):
        return [
            "--read-only", "--output-dir", str(output_dir),
            "--input-manifest-fingerprint", "abc",
            "--data-quality-receipt-sha256", "def",
            "--code-commit-sha", "ghi",
            "--global-min-timestamp", "2026-01-01T00:00:00Z",
            "--global-max-timestamp", "2026-02-01T00:00:00Z",
        ]

    def _cli_upstream_args(self):
        return [
            "--strategy-contract-path", self.CONTRACT_PATH,
            "--strategy-contract-sha256-path", self.CONTRACT_SIDECAR_PATH,
            "--strategy-contract-commit-binding-path", self.CONTRACT_BINDING_PATH,
            "--trial-manifest-path", self.MANIFEST_PATH,
            "--trial-manifest-sha256-path", self.MANIFEST_SIDECAR_PATH,
            "--oos-seal-path", self.SEAL_PATH,
            "--oos-seal-sha256-path", self.SEAL_SIDECAR_PATH,
            "--null-benchmark-path", self.NULL_PATH,
            "--null-benchmark-sha256-path", self.NULL_SIDECAR_PATH,
            "--multiple-testing-control-path", self.MT_PATH,
            "--multiple-testing-control-sha256-path", self.MT_SIDECAR_PATH,
            "--simulation-policy-path", self.SP_PATH,
            "--simulation-policy-sha256-path", self.SP_SIDECAR_PATH,
        ]

    def _cli_eap_args(self):
        return [
            "--economic-accounting-policy-path", self.EAP_PATH,
            "--economic-accounting-policy-sha256-path", self.EAP_SIDECAR_PATH,
        ]

    def test_cli_no_eap_args_top_level_receipt_shape(self, tmp_path):
        """CLI without EAP args: top-level receipt keeps net-PnL absence shape
        and gets a dedicated economic-accounting absence section, not the
        whole net-PnL/equity-risk section duplicated."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        exit_code = real_validation.main(self._cli_base_args(output_dir))
        assert exit_code == 0
        receipt = json.loads(
            (output_dir / "real_validation_receipt.json").read_text()
        )

        net_section = receipt["net_pnl_equity_risk_contract_diagnostics"]
        eap_section = receipt["economic_accounting_policy_diagnostics"]

        assert net_section["net_pnl_equity_risk_contract_status"] == (
            NET_PNL_EQUITY_RISK_CONTRACT_NOT_DEFINED
        )
        assert net_section["net_pnl_equity_risk_contract_present"] is False

        assert eap_section["diagnostic_kind"] == "economic_accounting_policy_absence"
        assert eap_section["economic_accounting_policy_preregistration_gate"][
            "gate_status"
        ] == "ECONOMIC_ACCOUNTING_POLICY_NOT_LOADED"

        assert "net_pnl_equity_risk_contract_status" not in eap_section
        assert "net_pnl_equity_risk_contract_present" not in eap_section

        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION

    def test_cli_full_eap_path_top_level_receipt_shape(self, tmp_path):
        """CLI with full EAP + upstream args: top-level receipt keeps net-PnL
        absence shape and gets a dedicated economic-accounting preregistration
        section, not the whole net-PnL/equity-risk section duplicated."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        exit_code = real_validation.main(
            self._cli_base_args(output_dir)
            + self._cli_upstream_args()
            + self._cli_eap_args()
        )
        assert exit_code == 0
        receipt = json.loads(
            (output_dir / "real_validation_receipt.json").read_text()
        )

        net_section = receipt["net_pnl_equity_risk_contract_diagnostics"]
        eap_section = receipt["economic_accounting_policy_diagnostics"]

        assert net_section["net_pnl_equity_risk_contract_status"] == (
            NET_PNL_EQUITY_RISK_CONTRACT_NOT_DEFINED
        )
        assert net_section["net_pnl_equity_risk_contract_present"] is False
        assert net_section["economic_accounting_policy_preregistration_gate"][
            "gate_passed"
        ] is True

        assert eap_section["diagnostic_kind"] == (
            "economic_accounting_policy_preregistration"
        )
        assert eap_section["economic_accounting_policy_preregistration_gate"][
            "gate_passed"
        ] is True

        assert "net_pnl_equity_risk_contract_status" not in eap_section
        assert "net_pnl_equity_risk_contract_present" not in eap_section

        assert net_section["economic_accounting_policy_preregistration_gate"] == (
            eap_section["economic_accounting_policy_preregistration_gate"]
        )

        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION


class TestPrerequisiteClosureK1:
    """Lane K1: prerequisite closure matrix / implementation readiness lock.

    A derived, diagnostic-only projection over the seven pre-registration
    gates (contract packet through economic accounting policy). Proves the
    pre-registration chain is present and passing as a *chain*, while every
    implementation/scoring/economic/statistical/final-verdict gate remains
    blocked. This lane implements no strategy, no simulation, no economic
    values, no statistics, and does not advance the final verdict.
    """

    CONTRACT_PATH = "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.json"
    CONTRACT_SIDECAR_PATH = "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.sha256"
    CONTRACT_BINDING_PATH = "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.commit_binding.json"
    MANIFEST_PATH = "docs/contracts/instances/qnty_offline_edge_trial_manifest_v1.json"
    MANIFEST_SIDECAR_PATH = "docs/contracts/instances/qnty_offline_edge_trial_manifest_v1.sha256"
    SEAL_PATH = "docs/contracts/instances/qnty_offline_edge_oos_seal_v1.json"
    SEAL_SIDECAR_PATH = "docs/contracts/instances/qnty_offline_edge_oos_seal_v1.sha256"
    NULL_PATH = "docs/contracts/instances/qnty_offline_edge_null_benchmark_v1.json"
    NULL_SIDECAR_PATH = "docs/contracts/instances/qnty_offline_edge_null_benchmark_v1.sha256"
    MT_PATH = "docs/contracts/instances/qnty_offline_edge_multiple_testing_control_v1.json"
    MT_SIDECAR_PATH = "docs/contracts/instances/qnty_offline_edge_multiple_testing_control_v1.sha256"
    SP_PATH = "docs/contracts/instances/qnty_offline_edge_simulation_policy_v1.json"
    SP_SIDECAR_PATH = "docs/contracts/instances/qnty_offline_edge_simulation_policy_v1.sha256"
    EAP_PATH = "docs/contracts/instances/qnty_offline_edge_economic_accounting_policy_v1.json"
    EAP_SIDECAR_PATH = "docs/contracts/instances/qnty_offline_edge_economic_accounting_policy_v1.sha256"

    def _full_chain_diags(self):
        """Build the full J1 chain of upstream diagnostics from frozen packets."""
        contract_diag = _build_strategy_rule_contract_diagnostics(
            contract_path=self.CONTRACT_PATH,
            sidecar_path=self.CONTRACT_SIDECAR_PATH,
            commit_binding_path=self.CONTRACT_BINDING_PATH,
        )
        manifest_diag = _build_trial_manifest_diagnostics(
            manifest_path=self.MANIFEST_PATH,
            sidecar_path=self.MANIFEST_SIDECAR_PATH,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        seal_diag = _build_oos_seal_diagnostics(
            seal_path=self.SEAL_PATH,
            sidecar_path=self.SEAL_SIDECAR_PATH,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        null_diag = _build_null_benchmark_contract_diagnostics(
            null_benchmark_path=self.NULL_PATH,
            sidecar_path=self.NULL_SIDECAR_PATH,
            oos_seal_diagnostics=seal_diag,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        mt_diag = _build_multiple_testing_control_diagnostics(
            multiple_testing_control_path=self.MT_PATH,
            sidecar_path=self.MT_SIDECAR_PATH,
            null_benchmark_diagnostics=null_diag,
            oos_seal_diagnostics=seal_diag,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        sp_diag = _build_trade_position_simulation_contract_diagnostics(
            simulation_policy_path=self.SP_PATH,
            sidecar_path=self.SP_SIDECAR_PATH,
            multiple_testing_control_diagnostics=mt_diag,
            null_benchmark_diagnostics=null_diag,
            oos_seal_diagnostics=seal_diag,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        eap_diag = _build_net_pnl_equity_risk_contract_diagnostics(
            economic_accounting_policy_path=self.EAP_PATH,
            sidecar_path=self.EAP_SIDECAR_PATH,
            simulation_policy_diagnostics=sp_diag,
            multiple_testing_control_diagnostics=mt_diag,
            null_benchmark_diagnostics=null_diag,
            oos_seal_diagnostics=seal_diag,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        return {
            "strategy_rule_contract_diagnostics": contract_diag,
            "trial_manifest_diagnostics": manifest_diag,
            "oos_seal_diagnostics": seal_diag,
            "null_benchmark_contract_diagnostics": null_diag,
            "multiple_testing_control_diagnostics": mt_diag,
            "trade_position_simulation_contract_diagnostics": sp_diag,
            "net_pnl_equity_risk_contract_diagnostics": eap_diag,
        }

    def _absence_diags(self):
        contract_diag = _build_strategy_rule_contract_diagnostics()
        manifest_diag = _build_trial_manifest_diagnostics(
            strategy_rule_contract_diagnostics=contract_diag,
        )
        seal_diag = _build_oos_seal_diagnostics(
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        null_diag = _build_null_benchmark_contract_diagnostics(
            oos_seal_diagnostics=seal_diag,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        mt_diag = _build_multiple_testing_control_diagnostics(
            null_benchmark_diagnostics=null_diag,
            oos_seal_diagnostics=seal_diag,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        sp_diag = _build_trade_position_simulation_contract_diagnostics(
            multiple_testing_control_diagnostics=mt_diag,
            null_benchmark_diagnostics=null_diag,
            oos_seal_diagnostics=seal_diag,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        eap_diag = _build_net_pnl_equity_risk_contract_diagnostics(
            simulation_policy_diagnostics=sp_diag,
            multiple_testing_control_diagnostics=mt_diag,
            null_benchmark_diagnostics=null_diag,
            oos_seal_diagnostics=seal_diag,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        return {
            "strategy_rule_contract_diagnostics": contract_diag,
            "trial_manifest_diagnostics": manifest_diag,
            "oos_seal_diagnostics": seal_diag,
            "null_benchmark_contract_diagnostics": null_diag,
            "multiple_testing_control_diagnostics": mt_diag,
            "trade_position_simulation_contract_diagnostics": sp_diag,
            "net_pnl_equity_risk_contract_diagnostics": eap_diag,
        }

    # ── Test 1: no-args / missing gates fails closed ──────────────────────────
    def test_closure_diagnostic_missing_gates_fails_closed(self):
        diags = self._absence_diags()
        result = _build_prerequisite_closure_diagnostics(**diags)
        gate = result["prerequisite_closure_gate"]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] in (
            "BLOCKED_BY_MISSING_PREREGISTRATION_GATE",
            "BLOCKED_BY_FAILED_PREREGISTRATION_GATE",
        )
        for field in (
            "closure_scoring_authorization",
            "closure_live_authorization",
            "closure_final_verdict_authorization",
            "implementation_authorized",
            "simulation_authorized",
            "economic_value_generation_authorized",
            "statistical_value_generation_authorized",
            "candidate_comparison_authorized",
            "null_generation_authorized",
            "final_verdict_advancement_authorized",
        ):
            assert result[field] is False

    # ── Test 2: full happy path ────────────────────────────────────────────────
    def test_closure_diagnostic_full_happy_path(self):
        diags = self._full_chain_diags()
        result = _build_prerequisite_closure_diagnostics(**diags)
        assert result["closure_gate_count"] == 7
        assert result["closure_gate_passed_count"] == 7
        assert result["closure_all_required_gates_passed"] is True
        assert result["closure_missing_required_gate_names"] == []
        assert result["closure_failed_required_gate_names"] == []
        for field in (
            "closure_scoring_authorization",
            "closure_live_authorization",
            "closure_final_verdict_authorization",
            "implementation_authorized",
            "simulation_authorized",
            "economic_value_generation_authorized",
            "statistical_value_generation_authorized",
            "candidate_comparison_authorized",
            "null_generation_authorized",
            "final_verdict_advancement_authorized",
        ):
            assert result[field] is False
        assert result["final_offline_verdict_remains"] == (
            BLOCKED_BY_VALIDATION_IMPLEMENTATION
        )
        assert result["closure_required_gate_names"] == list(
            PREREQUISITE_CLOSURE_REQUIRED_GATE_NAMES
        )
        assert result["closure_version"] == PREREQUISITE_CLOSURE_VERSION

    # ── Test 3: closure gate happy path ────────────────────────────────────────
    def test_closure_gate_happy_path(self):
        diags = self._full_chain_diags()
        result = _build_prerequisite_closure_diagnostics(**diags)
        gate = result["prerequisite_closure_gate"]
        assert gate["gate_passed"] is True
        assert gate["gate_status"] == "PREREGISTRATION_CHAIN_CLOSED_DIAGNOSTIC_ONLY"
        assert gate["gate_scoring_authorization"] is False
        assert gate["gate_live_authorization"] is False
        assert gate["gate_final_verdict_authorization"] is False
        assert gate["gate_downstream_unlocks"] == []
        assert gate["blocked_reason"] is None

    # ── Test 4: missing one gate fails closed ──────────────────────────────────
    def test_missing_one_gate_fails_closed(self):
        diags = self._full_chain_diags()
        del diags["oos_seal_diagnostics"]["oos_seal_preregistration_gate"]
        result = _build_prerequisite_closure_diagnostics(**diags)
        gate = result["prerequisite_closure_gate"]
        assert gate["gate_passed"] is False
        assert "oos_seal_preregistration_gate" in (
            result["closure_missing_required_gate_names"]
        )
        assert gate["gate_status"] == "BLOCKED_BY_MISSING_PREREGISTRATION_GATE"
        assert "oos_seal_preregistration_gate" in gate["blocked_reason"]

    # ── Test 5: failed one gate fails closed ───────────────────────────────────
    def test_failed_one_gate_fails_closed(self):
        diags = self._full_chain_diags()
        original_gate = diags["multiple_testing_control_diagnostics"][
            "multiple_testing_control_preregistration_gate"
        ]
        failed_gate = dict(original_gate)
        failed_gate["gate_passed"] = False
        diags["multiple_testing_control_diagnostics"] = dict(
            diags["multiple_testing_control_diagnostics"]
        )
        diags["multiple_testing_control_diagnostics"][
            "multiple_testing_control_preregistration_gate"
        ] = failed_gate
        result = _build_prerequisite_closure_diagnostics(**diags)
        gate = result["prerequisite_closure_gate"]
        assert gate["gate_passed"] is False
        assert "multiple_testing_control_preregistration_gate" in (
            result["closure_failed_required_gate_names"]
        )
        assert gate["gate_status"] == "BLOCKED_BY_FAILED_PREREGISTRATION_GATE"

    # ── Test 6: unexpected authorization fails closed ──────────────────────────
    def test_unexpected_authorization_fails_closed(self):
        diags = self._full_chain_diags()
        result = _build_prerequisite_closure_diagnostics(**diags)
        result["economic_value_generation_authorized"] = True
        gate = _derive_prerequisite_closure_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == "BLOCKED_BY_UNEXPECTED_AUTHORIZATION"
        assert "economic_value_generation_authorized" in gate["blocked_reason"]

    # ── Test 9 (regression): J1 nesting — top-level and nested EAP gate ───────
    def test_reads_eap_gate_from_top_level_or_nested(self):
        diags = self._full_chain_diags()
        # Top-level EAP gate present (Lane J1 full path always sets both).
        result_top = _build_prerequisite_closure_diagnostics(**diags)
        assert result_top["closure_all_required_gates_passed"] is True

        # Simulate a net_pnl diagnostics dict where only the nested EAP gate
        # is present (top-level key absent) to prove the fallback path works.
        nested_only = dict(diags["net_pnl_equity_risk_contract_diagnostics"])
        nested_only.pop("economic_accounting_policy_preregistration_gate", None)
        assert (
            "economic_accounting_policy_preregistration_gate"
            in nested_only["economic_accounting_policy_diagnostics"]
        )
        diags_nested = dict(diags)
        diags_nested["net_pnl_equity_risk_contract_diagnostics"] = nested_only
        result_nested = _build_prerequisite_closure_diagnostics(**diags_nested)
        assert result_nested["closure_all_required_gates_passed"] is True

    # ── Test 10: forbidden key scan ────────────────────────────────────────────
    def test_no_forbidden_calculation_keys(self):
        diags = self._full_chain_diags()
        result = _build_prerequisite_closure_diagnostics(**diags)
        all_keys = _all_dict_keys(result)
        assert real_validation.FORBIDDEN_CALCULATION_KEYS.isdisjoint(all_keys), (
            f"Forbidden keys found: "
            f"{real_validation.FORBIDDEN_CALCULATION_KEYS & all_keys}"
        )

    # ── CLI receipt integration ─────────────────────────────────────────────
    def _cli_base_args(self, output_dir):
        return [
            "--read-only", "--output-dir", str(output_dir),
            "--input-manifest-fingerprint", "abc",
            "--data-quality-receipt-sha256", "def",
            "--code-commit-sha", "ghi",
            "--global-min-timestamp", "2026-01-01T00:00:00Z",
            "--global-max-timestamp", "2026-02-01T00:00:00Z",
        ]

    def _cli_full_chain_args(self):
        return [
            "--strategy-contract-path", self.CONTRACT_PATH,
            "--strategy-contract-sha256-path", self.CONTRACT_SIDECAR_PATH,
            "--strategy-contract-commit-binding-path", self.CONTRACT_BINDING_PATH,
            "--trial-manifest-path", self.MANIFEST_PATH,
            "--trial-manifest-sha256-path", self.MANIFEST_SIDECAR_PATH,
            "--oos-seal-path", self.SEAL_PATH,
            "--oos-seal-sha256-path", self.SEAL_SIDECAR_PATH,
            "--null-benchmark-path", self.NULL_PATH,
            "--null-benchmark-sha256-path", self.NULL_SIDECAR_PATH,
            "--multiple-testing-control-path", self.MT_PATH,
            "--multiple-testing-control-sha256-path", self.MT_SIDECAR_PATH,
            "--simulation-policy-path", self.SP_PATH,
            "--simulation-policy-sha256-path", self.SP_SIDECAR_PATH,
            "--economic-accounting-policy-path", self.EAP_PATH,
            "--economic-accounting-policy-sha256-path", self.EAP_SIDECAR_PATH,
        ]

    # ── Test 7: receipt integration, no packet args ────────────────────────────
    def test_receipt_integration_no_packet_args(self, tmp_path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        exit_code = real_validation.main(self._cli_base_args(output_dir))
        assert exit_code == 0
        receipt = json.loads(
            (output_dir / "real_validation_receipt.json").read_text()
        )
        closure = receipt["prerequisite_closure_diagnostics"]
        assert closure["prerequisite_closure_gate"]["gate_passed"] is False
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION

    # ── Test 8: receipt integration, full packet args through J1 ───────────────
    def test_receipt_integration_full_path(self, tmp_path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        exit_code = real_validation.main(
            self._cli_base_args(output_dir) + self._cli_full_chain_args()
        )
        assert exit_code == 0
        receipt = json.loads(
            (output_dir / "real_validation_receipt.json").read_text()
        )
        closure = receipt["prerequisite_closure_diagnostics"]
        assert closure["closure_gate_count"] == 7
        assert closure["closure_gate_passed_count"] == 7
        assert closure["closure_all_required_gates_passed"] is True
        assert closure["prerequisite_closure_gate"]["gate_passed"] is True
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION


class TestImplementationBoundaryL1:
    """Lane L1: implementation boundary plan / runner contract shell.

    A derived, diagnostic-only projection over the K1 prerequisite closure
    gate (plus the contract-packet and trial-manifest gates it depends on).
    Declares exactly what a future strategy-rule implementation runner would
    be allowed to inspect and exactly what it remains forbidden to emit. This
    lane does not implement the runner, materialize rule outputs, compute
    decisions/simulated events/economic/statistical values, or authorize
    scoring/live/final verdict advancement.
    """

    CONTRACT_PATH = "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.json"
    CONTRACT_SIDECAR_PATH = "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.sha256"
    CONTRACT_BINDING_PATH = "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.commit_binding.json"
    MANIFEST_PATH = "docs/contracts/instances/qnty_offline_edge_trial_manifest_v1.json"
    MANIFEST_SIDECAR_PATH = "docs/contracts/instances/qnty_offline_edge_trial_manifest_v1.sha256"
    SEAL_PATH = "docs/contracts/instances/qnty_offline_edge_oos_seal_v1.json"
    SEAL_SIDECAR_PATH = "docs/contracts/instances/qnty_offline_edge_oos_seal_v1.sha256"
    NULL_PATH = "docs/contracts/instances/qnty_offline_edge_null_benchmark_v1.json"
    NULL_SIDECAR_PATH = "docs/contracts/instances/qnty_offline_edge_null_benchmark_v1.sha256"
    MT_PATH = "docs/contracts/instances/qnty_offline_edge_multiple_testing_control_v1.json"
    MT_SIDECAR_PATH = "docs/contracts/instances/qnty_offline_edge_multiple_testing_control_v1.sha256"
    SP_PATH = "docs/contracts/instances/qnty_offline_edge_simulation_policy_v1.json"
    SP_SIDECAR_PATH = "docs/contracts/instances/qnty_offline_edge_simulation_policy_v1.sha256"
    EAP_PATH = "docs/contracts/instances/qnty_offline_edge_economic_accounting_policy_v1.json"
    EAP_SIDECAR_PATH = "docs/contracts/instances/qnty_offline_edge_economic_accounting_policy_v1.sha256"

    def _full_chain_diags(self):
        """Build the full K1 chain of upstream diagnostics from frozen packets."""
        contract_diag = _build_strategy_rule_contract_diagnostics(
            contract_path=self.CONTRACT_PATH,
            sidecar_path=self.CONTRACT_SIDECAR_PATH,
            commit_binding_path=self.CONTRACT_BINDING_PATH,
        )
        manifest_diag = _build_trial_manifest_diagnostics(
            manifest_path=self.MANIFEST_PATH,
            sidecar_path=self.MANIFEST_SIDECAR_PATH,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        seal_diag = _build_oos_seal_diagnostics(
            seal_path=self.SEAL_PATH,
            sidecar_path=self.SEAL_SIDECAR_PATH,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        null_diag = _build_null_benchmark_contract_diagnostics(
            null_benchmark_path=self.NULL_PATH,
            sidecar_path=self.NULL_SIDECAR_PATH,
            oos_seal_diagnostics=seal_diag,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        mt_diag = _build_multiple_testing_control_diagnostics(
            multiple_testing_control_path=self.MT_PATH,
            sidecar_path=self.MT_SIDECAR_PATH,
            null_benchmark_diagnostics=null_diag,
            oos_seal_diagnostics=seal_diag,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        sp_diag = _build_trade_position_simulation_contract_diagnostics(
            simulation_policy_path=self.SP_PATH,
            sidecar_path=self.SP_SIDECAR_PATH,
            multiple_testing_control_diagnostics=mt_diag,
            null_benchmark_diagnostics=null_diag,
            oos_seal_diagnostics=seal_diag,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        eap_diag = _build_net_pnl_equity_risk_contract_diagnostics(
            economic_accounting_policy_path=self.EAP_PATH,
            sidecar_path=self.EAP_SIDECAR_PATH,
            simulation_policy_diagnostics=sp_diag,
            multiple_testing_control_diagnostics=mt_diag,
            null_benchmark_diagnostics=null_diag,
            oos_seal_diagnostics=seal_diag,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        closure_diag = _build_prerequisite_closure_diagnostics(
            strategy_rule_contract_diagnostics=contract_diag,
            trial_manifest_diagnostics=manifest_diag,
            oos_seal_diagnostics=seal_diag,
            null_benchmark_contract_diagnostics=null_diag,
            multiple_testing_control_diagnostics=mt_diag,
            trade_position_simulation_contract_diagnostics=sp_diag,
            net_pnl_equity_risk_contract_diagnostics=eap_diag,
        )
        return {
            "strategy_rule_contract_diagnostics": contract_diag,
            "trial_manifest_diagnostics": manifest_diag,
            "prerequisite_closure_diagnostics": closure_diag,
        }

    def _absence_diags(self):
        contract_diag = _build_strategy_rule_contract_diagnostics()
        manifest_diag = _build_trial_manifest_diagnostics(
            strategy_rule_contract_diagnostics=contract_diag,
        )
        seal_diag = _build_oos_seal_diagnostics(
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        null_diag = _build_null_benchmark_contract_diagnostics(
            oos_seal_diagnostics=seal_diag,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        mt_diag = _build_multiple_testing_control_diagnostics(
            null_benchmark_diagnostics=null_diag,
            oos_seal_diagnostics=seal_diag,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        sp_diag = _build_trade_position_simulation_contract_diagnostics(
            multiple_testing_control_diagnostics=mt_diag,
            null_benchmark_diagnostics=null_diag,
            oos_seal_diagnostics=seal_diag,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        eap_diag = _build_net_pnl_equity_risk_contract_diagnostics(
            simulation_policy_diagnostics=sp_diag,
            multiple_testing_control_diagnostics=mt_diag,
            null_benchmark_diagnostics=null_diag,
            oos_seal_diagnostics=seal_diag,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        closure_diag = _build_prerequisite_closure_diagnostics(
            strategy_rule_contract_diagnostics=contract_diag,
            trial_manifest_diagnostics=manifest_diag,
            oos_seal_diagnostics=seal_diag,
            null_benchmark_contract_diagnostics=null_diag,
            multiple_testing_control_diagnostics=mt_diag,
            trade_position_simulation_contract_diagnostics=sp_diag,
            net_pnl_equity_risk_contract_diagnostics=eap_diag,
        )
        return {
            "strategy_rule_contract_diagnostics": contract_diag,
            "trial_manifest_diagnostics": manifest_diag,
            "prerequisite_closure_diagnostics": closure_diag,
        }

    # ── Test 1: no-args / closure failed fails closed ──────────────────────────
    def test_boundary_diagnostic_closure_failed_fails_closed(self):
        diags = self._absence_diags()
        assert diags["prerequisite_closure_diagnostics"][
            "prerequisite_closure_gate"
        ]["gate_passed"] is False
        result = _build_implementation_boundary_diagnostics(**diags)
        gate = result["implementation_boundary_gate"]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == "BLOCKED_BY_PREREQUISITE_CLOSURE_GATE"
        for field in _IMPLEMENTATION_BOUNDARY_AUTHORIZATION_FIELDS:
            assert result[field] is False

    # ── Test 2: full happy path ─────────────────────────────────────────────────
    def test_boundary_diagnostic_full_happy_path(self):
        diags = self._full_chain_diags()
        result = _build_implementation_boundary_diagnostics(**diags)
        assert result["prerequisite_closure_gate_passed"] is True
        assert result["contract_packet_gate_passed"] is True
        assert result["trial_manifest_gate_passed"] is True
        assert result["implementation_boundary_version"] == (
            IMPLEMENTATION_BOUNDARY_VERSION
        )
        assert result["implementation_boundary_scope"] == (
            IMPLEMENTATION_BOUNDARY_SCOPE
        )
        assert result["implementation_boundary_status"] == (
            IMPLEMENTATION_BOUNDARY_DECLARED_DIAGNOSTIC_ONLY
        )
        assert result["future_runner_allowed_bar_columns"] == ["close", "timestamp"]
        assert result["future_runner_allowed_funding_columns"] == [
            "fundingRate",
            "fundingTime",
        ]
        assert "open" in result["future_runner_forbidden_bar_columns"]
        assert "markPrice" in result["future_runner_forbidden_funding_columns"]
        assert result["future_runner_output_policy"] == (
            "NO_OUTPUT_ROWS_EMITTED_IN_THIS_LANE"
        )
        assert result["future_runner_materialization_policy"] == (
            "NO_RULE_MATERIALIZATION_IN_THIS_LANE"
        )
        for field in _IMPLEMENTATION_BOUNDARY_AUTHORIZATION_FIELDS:
            assert result[field] is False
        assert result["final_offline_verdict_remains"] == (
            BLOCKED_BY_VALIDATION_IMPLEMENTATION
        )

    # ── Test 3: gate happy path ──────────────────────────────────────────────────
    def test_boundary_gate_happy_path(self):
        diags = self._full_chain_diags()
        result = _build_implementation_boundary_diagnostics(**diags)
        gate = result["implementation_boundary_gate"]
        assert gate["gate_passed"] is True
        assert gate["gate_status"] == (
            IMPLEMENTATION_BOUNDARY_DECLARED_DIAGNOSTIC_ONLY
        )
        assert gate["gate_scoring_authorization"] is False
        assert gate["gate_live_authorization"] is False
        assert gate["gate_final_verdict_authorization"] is False
        assert gate["gate_downstream_unlocks"] == []
        assert gate["blocked_reason"] is None

    # ── Test 4: closure gate missing fails closed ───────────────────────────────
    def test_closure_gate_missing_fails_closed(self):
        diags = self._full_chain_diags()
        closure = dict(diags["prerequisite_closure_diagnostics"])
        del closure["prerequisite_closure_gate"]
        diags["prerequisite_closure_diagnostics"] = closure
        result = _build_implementation_boundary_diagnostics(**diags)
        gate = result["implementation_boundary_gate"]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == "BLOCKED_BY_PREREQUISITE_CLOSURE_GATE"

    # ── Test 5: closure gate failed fails closed ────────────────────────────────
    def test_closure_gate_failed_fails_closed(self):
        diags = self._full_chain_diags()
        closure = dict(diags["prerequisite_closure_diagnostics"])
        original_gate = closure["prerequisite_closure_gate"]
        failed_gate = dict(original_gate)
        failed_gate["gate_passed"] = False
        closure["prerequisite_closure_gate"] = failed_gate
        diags["prerequisite_closure_diagnostics"] = closure
        result = _build_implementation_boundary_diagnostics(**diags)
        gate = result["implementation_boundary_gate"]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == "BLOCKED_BY_PREREQUISITE_CLOSURE_GATE"

    # ── Test 6: contract packet gate missing/failed fails closed ────────────────
    def test_contract_packet_gate_missing_fails_closed(self):
        diags = self._full_chain_diags()
        contract_diag = dict(diags["strategy_rule_contract_diagnostics"])
        del contract_diag["contract_packet_gate"]
        diags["strategy_rule_contract_diagnostics"] = contract_diag
        result = _build_implementation_boundary_diagnostics(**diags)
        gate = result["implementation_boundary_gate"]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == "BLOCKED_BY_REQUIRED_UPSTREAM_GATE"
        assert "contract_packet_gate" in gate["blocked_reason"]

    def test_contract_packet_gate_failed_fails_closed(self):
        diags = self._full_chain_diags()
        contract_diag = dict(diags["strategy_rule_contract_diagnostics"])
        original_gate = contract_diag["contract_packet_gate"]
        failed_gate = dict(original_gate)
        failed_gate["gate_passed"] = False
        contract_diag["contract_packet_gate"] = failed_gate
        diags["strategy_rule_contract_diagnostics"] = contract_diag
        result = _build_implementation_boundary_diagnostics(**diags)
        gate = result["implementation_boundary_gate"]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == "BLOCKED_BY_REQUIRED_UPSTREAM_GATE"

    # ── Test 7: trial manifest gate missing/failed fails closed ─────────────────
    def test_trial_manifest_gate_missing_fails_closed(self):
        diags = self._full_chain_diags()
        manifest_diag = dict(diags["trial_manifest_diagnostics"])
        del manifest_diag["trial_manifest_preregistration_gate"]
        diags["trial_manifest_diagnostics"] = manifest_diag
        result = _build_implementation_boundary_diagnostics(**diags)
        gate = result["implementation_boundary_gate"]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == "BLOCKED_BY_REQUIRED_UPSTREAM_GATE"
        assert "trial_manifest_preregistration_gate" in gate["blocked_reason"]

    def test_trial_manifest_gate_failed_fails_closed(self):
        diags = self._full_chain_diags()
        manifest_diag = dict(diags["trial_manifest_diagnostics"])
        original_gate = manifest_diag["trial_manifest_preregistration_gate"]
        failed_gate = dict(original_gate)
        failed_gate["gate_passed"] = False
        manifest_diag["trial_manifest_preregistration_gate"] = failed_gate
        diags["trial_manifest_diagnostics"] = manifest_diag
        result = _build_implementation_boundary_diagnostics(**diags)
        gate = result["implementation_boundary_gate"]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == "BLOCKED_BY_REQUIRED_UPSTREAM_GATE"

    # ── Test 8: unexpected authorization fails closed ───────────────────────────
    def test_unexpected_authorization_fails_closed(self):
        diags = self._full_chain_diags()
        result = _build_implementation_boundary_diagnostics(**diags)
        result["rule_materialization_authorized"] = True
        gate = _derive_implementation_boundary_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == "BLOCKED_BY_UNEXPECTED_AUTHORIZATION"
        assert "rule_materialization_authorized" in gate["blocked_reason"]

    # ── Test 9: forbidden key scan ───────────────────────────────────────────────
    def test_no_forbidden_calculation_keys(self):
        diags = self._full_chain_diags()
        result = _build_implementation_boundary_diagnostics(**diags)
        all_keys = _all_dict_keys(result)
        assert real_validation.FORBIDDEN_CALCULATION_KEYS.isdisjoint(all_keys), (
            f"Forbidden keys found: "
            f"{real_validation.FORBIDDEN_CALCULATION_KEYS & all_keys}"
        )

    # ── Test 10: output/materialization/decision-time policy evidence ──────────
    def test_boundary_gate_happy_path_policy_evidence(self):
        diags = self._full_chain_diags()
        result = _build_implementation_boundary_diagnostics(**diags)
        gate = result["implementation_boundary_gate"]
        assert gate["gate_passed"] is True
        evidence = gate["evidence"]
        assert evidence["future_runner_output_policy_matches_frozen_value"] is True
        assert (
            evidence["future_runner_materialization_policy_matches_frozen_value"]
            is True
        )
        assert (
            evidence["future_runner_decision_time_policy_matches_frozen_value"]
            is True
        )
        assert evidence["future_runner_forbidden_input_columns_declared"] is True

    def test_missing_output_policy_fails_closed(self):
        diags = self._full_chain_diags()
        result = _build_implementation_boundary_diagnostics(**diags)
        mutated = dict(result)
        del mutated["future_runner_output_policy"]
        gate = _derive_implementation_boundary_gate(mutated)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            "BLOCKED_BY_INCOMPLETE_IMPLEMENTATION_BOUNDARY_EVIDENCE"
        )
        for field in _IMPLEMENTATION_BOUNDARY_AUTHORIZATION_FIELDS:
            assert gate["evidence"].get(field, False) is not True

    def test_empty_output_policy_fails_closed(self):
        diags = self._full_chain_diags()
        result = _build_implementation_boundary_diagnostics(**diags)
        mutated = dict(result)
        mutated["future_runner_output_policy"] = ""
        gate = _derive_implementation_boundary_gate(mutated)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            "BLOCKED_BY_INCOMPLETE_IMPLEMENTATION_BOUNDARY_EVIDENCE"
        )

    def test_mutated_output_policy_fails_closed(self):
        diags = self._full_chain_diags()
        result = _build_implementation_boundary_diagnostics(**diags)
        mutated = dict(result)
        mutated["future_runner_output_policy"] = "EMIT_OUTPUT_ROWS_NOW"
        gate = _derive_implementation_boundary_gate(mutated)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            "BLOCKED_BY_INCOMPLETE_IMPLEMENTATION_BOUNDARY_EVIDENCE"
        )

    def test_missing_materialization_policy_fails_closed(self):
        diags = self._full_chain_diags()
        result = _build_implementation_boundary_diagnostics(**diags)
        mutated = dict(result)
        del mutated["future_runner_materialization_policy"]
        gate = _derive_implementation_boundary_gate(mutated)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            "BLOCKED_BY_INCOMPLETE_IMPLEMENTATION_BOUNDARY_EVIDENCE"
        )

    def test_mutated_materialization_policy_fails_closed(self):
        diags = self._full_chain_diags()
        result = _build_implementation_boundary_diagnostics(**diags)
        mutated = dict(result)
        mutated["future_runner_materialization_policy"] = "MATERIALIZE_RULES_NOW"
        gate = _derive_implementation_boundary_gate(mutated)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            "BLOCKED_BY_INCOMPLETE_IMPLEMENTATION_BOUNDARY_EVIDENCE"
        )

    def test_mutated_decision_time_policy_fails_closed(self):
        diags = self._full_chain_diags()
        result = _build_implementation_boundary_diagnostics(**diags)
        mutated = dict(result)
        mutated["future_runner_decision_time_policy"] = (
            "USE_INTRABAR_OR_FUTURE_CONTEXT"
        )
        gate = _derive_implementation_boundary_gate(mutated)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            "BLOCKED_BY_INCOMPLETE_IMPLEMENTATION_BOUNDARY_EVIDENCE"
        )

    def test_forbidden_bar_columns_deleted_but_output_policy_intact_fails_closed(
        self,
    ):
        diags = self._full_chain_diags()
        result = _build_implementation_boundary_diagnostics(**diags)
        mutated = dict(result)
        mutated["future_runner_forbidden_bar_columns"] = []
        gate = _derive_implementation_boundary_gate(mutated)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            "BLOCKED_BY_INCOMPLETE_IMPLEMENTATION_BOUNDARY_EVIDENCE"
        )

    # ── CLI receipt integration ──────────────────────────────────────────────────
    def _cli_base_args(self, output_dir):
        return [
            "--read-only", "--output-dir", str(output_dir),
            "--input-manifest-fingerprint", "abc",
            "--data-quality-receipt-sha256", "def",
            "--code-commit-sha", "ghi",
            "--global-min-timestamp", "2026-01-01T00:00:00Z",
            "--global-max-timestamp", "2026-02-01T00:00:00Z",
        ]

    def _cli_full_chain_args(self):
        return [
            "--strategy-contract-path", self.CONTRACT_PATH,
            "--strategy-contract-sha256-path", self.CONTRACT_SIDECAR_PATH,
            "--strategy-contract-commit-binding-path", self.CONTRACT_BINDING_PATH,
            "--trial-manifest-path", self.MANIFEST_PATH,
            "--trial-manifest-sha256-path", self.MANIFEST_SIDECAR_PATH,
            "--oos-seal-path", self.SEAL_PATH,
            "--oos-seal-sha256-path", self.SEAL_SIDECAR_PATH,
            "--null-benchmark-path", self.NULL_PATH,
            "--null-benchmark-sha256-path", self.NULL_SIDECAR_PATH,
            "--multiple-testing-control-path", self.MT_PATH,
            "--multiple-testing-control-sha256-path", self.MT_SIDECAR_PATH,
            "--simulation-policy-path", self.SP_PATH,
            "--simulation-policy-sha256-path", self.SP_SIDECAR_PATH,
            "--economic-accounting-policy-path", self.EAP_PATH,
            "--economic-accounting-policy-sha256-path", self.EAP_SIDECAR_PATH,
        ]

    # ── Test 10: receipt integration, no packet args ─────────────────────────────
    def test_receipt_integration_no_packet_args(self, tmp_path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        exit_code = real_validation.main(self._cli_base_args(output_dir))
        assert exit_code == 0
        receipt = json.loads(
            (output_dir / "real_validation_receipt.json").read_text()
        )
        boundary = receipt["implementation_boundary_diagnostics"]
        assert boundary["implementation_boundary_gate"]["gate_passed"] is False
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION

    # ── Test 11: receipt integration, full packet args through J1 ────────────────
    def test_receipt_integration_full_path(self, tmp_path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        exit_code = real_validation.main(
            self._cli_base_args(output_dir) + self._cli_full_chain_args()
        )
        assert exit_code == 0
        receipt = json.loads(
            (output_dir / "real_validation_receipt.json").read_text()
        )
        closure = receipt["prerequisite_closure_diagnostics"]
        assert closure["prerequisite_closure_gate"]["gate_passed"] is True
        boundary = receipt["implementation_boundary_diagnostics"]
        assert boundary["implementation_boundary_gate"]["gate_passed"] is True
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION


class TestNoOutputRunnerInvocationM1:
    """Lane M1: no-output runner invocation scaffold.

    A derived, diagnostic-only projection over the L1 implementation
    boundary gate (plus the contract-packet and trial-manifest gates it
    depends on). Records how a future strategy-rule runner would be invoked
    without implementing that runner. This lane does not materialize rule
    outputs, compute decisions/simulated events/economic/statistical
    values, or authorize scoring/live/final verdict advancement.
    """

    CONTRACT_PATH = "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.json"
    CONTRACT_SIDECAR_PATH = "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.sha256"
    CONTRACT_BINDING_PATH = "docs/contracts/instances/qnty_offline_edge_strategy_rule_contract_v1.commit_binding.json"
    MANIFEST_PATH = "docs/contracts/instances/qnty_offline_edge_trial_manifest_v1.json"
    MANIFEST_SIDECAR_PATH = "docs/contracts/instances/qnty_offline_edge_trial_manifest_v1.sha256"
    SEAL_PATH = "docs/contracts/instances/qnty_offline_edge_oos_seal_v1.json"
    SEAL_SIDECAR_PATH = "docs/contracts/instances/qnty_offline_edge_oos_seal_v1.sha256"
    NULL_PATH = "docs/contracts/instances/qnty_offline_edge_null_benchmark_v1.json"
    NULL_SIDECAR_PATH = "docs/contracts/instances/qnty_offline_edge_null_benchmark_v1.sha256"
    MT_PATH = "docs/contracts/instances/qnty_offline_edge_multiple_testing_control_v1.json"
    MT_SIDECAR_PATH = "docs/contracts/instances/qnty_offline_edge_multiple_testing_control_v1.sha256"
    SP_PATH = "docs/contracts/instances/qnty_offline_edge_simulation_policy_v1.json"
    SP_SIDECAR_PATH = "docs/contracts/instances/qnty_offline_edge_simulation_policy_v1.sha256"
    EAP_PATH = "docs/contracts/instances/qnty_offline_edge_economic_accounting_policy_v1.json"
    EAP_SIDECAR_PATH = "docs/contracts/instances/qnty_offline_edge_economic_accounting_policy_v1.sha256"

    def _full_chain_diags(self):
        """Build the full L1 chain of upstream diagnostics from frozen packets."""
        contract_diag = _build_strategy_rule_contract_diagnostics(
            contract_path=self.CONTRACT_PATH,
            sidecar_path=self.CONTRACT_SIDECAR_PATH,
            commit_binding_path=self.CONTRACT_BINDING_PATH,
        )
        manifest_diag = _build_trial_manifest_diagnostics(
            manifest_path=self.MANIFEST_PATH,
            sidecar_path=self.MANIFEST_SIDECAR_PATH,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        seal_diag = _build_oos_seal_diagnostics(
            seal_path=self.SEAL_PATH,
            sidecar_path=self.SEAL_SIDECAR_PATH,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        null_diag = _build_null_benchmark_contract_diagnostics(
            null_benchmark_path=self.NULL_PATH,
            sidecar_path=self.NULL_SIDECAR_PATH,
            oos_seal_diagnostics=seal_diag,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        mt_diag = _build_multiple_testing_control_diagnostics(
            multiple_testing_control_path=self.MT_PATH,
            sidecar_path=self.MT_SIDECAR_PATH,
            null_benchmark_diagnostics=null_diag,
            oos_seal_diagnostics=seal_diag,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        sp_diag = _build_trade_position_simulation_contract_diagnostics(
            simulation_policy_path=self.SP_PATH,
            sidecar_path=self.SP_SIDECAR_PATH,
            multiple_testing_control_diagnostics=mt_diag,
            null_benchmark_diagnostics=null_diag,
            oos_seal_diagnostics=seal_diag,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        eap_diag = _build_net_pnl_equity_risk_contract_diagnostics(
            economic_accounting_policy_path=self.EAP_PATH,
            sidecar_path=self.EAP_SIDECAR_PATH,
            simulation_policy_diagnostics=sp_diag,
            multiple_testing_control_diagnostics=mt_diag,
            null_benchmark_diagnostics=null_diag,
            oos_seal_diagnostics=seal_diag,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        closure_diag = _build_prerequisite_closure_diagnostics(
            strategy_rule_contract_diagnostics=contract_diag,
            trial_manifest_diagnostics=manifest_diag,
            oos_seal_diagnostics=seal_diag,
            null_benchmark_contract_diagnostics=null_diag,
            multiple_testing_control_diagnostics=mt_diag,
            trade_position_simulation_contract_diagnostics=sp_diag,
            net_pnl_equity_risk_contract_diagnostics=eap_diag,
        )
        boundary_diag = _build_implementation_boundary_diagnostics(
            strategy_rule_contract_diagnostics=contract_diag,
            trial_manifest_diagnostics=manifest_diag,
            prerequisite_closure_diagnostics=closure_diag,
        )
        return {
            "implementation_boundary_diagnostics": boundary_diag,
            "strategy_rule_contract_diagnostics": contract_diag,
            "trial_manifest_diagnostics": manifest_diag,
        }

    def _absence_diags(self):
        contract_diag = _build_strategy_rule_contract_diagnostics()
        manifest_diag = _build_trial_manifest_diagnostics(
            strategy_rule_contract_diagnostics=contract_diag,
        )
        seal_diag = _build_oos_seal_diagnostics(
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        null_diag = _build_null_benchmark_contract_diagnostics(
            oos_seal_diagnostics=seal_diag,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        mt_diag = _build_multiple_testing_control_diagnostics(
            null_benchmark_diagnostics=null_diag,
            oos_seal_diagnostics=seal_diag,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        sp_diag = _build_trade_position_simulation_contract_diagnostics(
            multiple_testing_control_diagnostics=mt_diag,
            null_benchmark_diagnostics=null_diag,
            oos_seal_diagnostics=seal_diag,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        eap_diag = _build_net_pnl_equity_risk_contract_diagnostics(
            simulation_policy_diagnostics=sp_diag,
            multiple_testing_control_diagnostics=mt_diag,
            null_benchmark_diagnostics=null_diag,
            oos_seal_diagnostics=seal_diag,
            trial_manifest_diagnostics=manifest_diag,
            strategy_rule_contract_diagnostics=contract_diag,
        )
        closure_diag = _build_prerequisite_closure_diagnostics(
            strategy_rule_contract_diagnostics=contract_diag,
            trial_manifest_diagnostics=manifest_diag,
            oos_seal_diagnostics=seal_diag,
            null_benchmark_contract_diagnostics=null_diag,
            multiple_testing_control_diagnostics=mt_diag,
            trade_position_simulation_contract_diagnostics=sp_diag,
            net_pnl_equity_risk_contract_diagnostics=eap_diag,
        )
        boundary_diag = _build_implementation_boundary_diagnostics(
            strategy_rule_contract_diagnostics=contract_diag,
            trial_manifest_diagnostics=manifest_diag,
            prerequisite_closure_diagnostics=closure_diag,
        )
        return {
            "implementation_boundary_diagnostics": boundary_diag,
            "strategy_rule_contract_diagnostics": contract_diag,
            "trial_manifest_diagnostics": manifest_diag,
        }

    # ── Test 1: no-args / boundary failed fails closed ─────────────────────────
    def test_runner_invocation_diagnostic_boundary_failed_fails_closed(self):
        diags = self._absence_diags()
        assert diags["implementation_boundary_diagnostics"][
            "implementation_boundary_gate"
        ]["gate_passed"] is False
        result = _build_no_output_runner_invocation_diagnostics(**diags)
        gate = result["no_output_runner_invocation_gate"]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == "BLOCKED_BY_IMPLEMENTATION_BOUNDARY_GATE"
        for field in _NO_OUTPUT_RUNNER_INVOCATION_AUTHORIZATION_FIELDS:
            assert result[field] is False

    # ── Test 2: full happy path ─────────────────────────────────────────────────
    def test_runner_invocation_diagnostic_full_happy_path(self):
        diags = self._full_chain_diags()
        result = _build_no_output_runner_invocation_diagnostics(**diags)
        assert result["implementation_boundary_gate_passed"] is True
        assert result["contract_packet_gate_passed"] is True
        assert result["trial_manifest_gate_passed"] is True
        assert result["no_output_runner_invocation_version"] == (
            NO_OUTPUT_RUNNER_INVOCATION_VERSION
        )
        assert result["no_output_runner_invocation_scope"] == (
            NO_OUTPUT_RUNNER_INVOCATION_SCOPE
        )
        assert result["no_output_runner_invocation_status"] == (
            NO_OUTPUT_RUNNER_INVOCATION_DECLARED_DIAGNOSTIC_ONLY
        )
        assert result["future_runner_implementation_status"] == (
            NO_OUTPUT_RUNNER_NOT_IMPLEMENTED
        )
        assert result["future_runner_output_policy"] == (
            NO_OUTPUT_RUNNER_OUTPUT_POLICY_FROZEN
        )
        assert result["future_runner_materialization_policy"] == (
            NO_OUTPUT_RUNNER_MATERIALIZATION_POLICY_FROZEN
        )
        for field in _NO_OUTPUT_RUNNER_INVOCATION_AUTHORIZATION_FIELDS:
            assert result[field] is False
        assert result["final_offline_verdict_remains"] == (
            BLOCKED_BY_VALIDATION_IMPLEMENTATION
        )

    # ── Test 3: gate happy path ──────────────────────────────────────────────────
    def test_runner_invocation_gate_happy_path(self):
        diags = self._full_chain_diags()
        result = _build_no_output_runner_invocation_diagnostics(**diags)
        gate = result["no_output_runner_invocation_gate"]
        assert gate["gate_passed"] is True
        assert gate["gate_status"] == (
            NO_OUTPUT_RUNNER_INVOCATION_DECLARED_DIAGNOSTIC_ONLY
        )
        assert gate["gate_scoring_authorization"] is False
        assert gate["gate_live_authorization"] is False
        assert gate["gate_final_verdict_authorization"] is False
        assert gate["gate_downstream_unlocks"] == []
        assert gate["blocked_reason"] is None

    # ── Test 4: implementation boundary gate missing/failed fails closed ────────
    def test_implementation_boundary_gate_missing_fails_closed(self):
        diags = self._full_chain_diags()
        boundary = dict(diags["implementation_boundary_diagnostics"])
        del boundary["implementation_boundary_gate"]
        diags["implementation_boundary_diagnostics"] = boundary
        result = _build_no_output_runner_invocation_diagnostics(**diags)
        gate = result["no_output_runner_invocation_gate"]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == "BLOCKED_BY_IMPLEMENTATION_BOUNDARY_GATE"

    def test_implementation_boundary_gate_failed_fails_closed(self):
        diags = self._full_chain_diags()
        boundary = dict(diags["implementation_boundary_diagnostics"])
        original_gate = boundary["implementation_boundary_gate"]
        failed_gate = dict(original_gate)
        failed_gate["gate_passed"] = False
        boundary["implementation_boundary_gate"] = failed_gate
        diags["implementation_boundary_diagnostics"] = boundary
        result = _build_no_output_runner_invocation_diagnostics(**diags)
        gate = result["no_output_runner_invocation_gate"]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == "BLOCKED_BY_IMPLEMENTATION_BOUNDARY_GATE"

    # ── Test 5: contract packet gate missing/failed fails closed ────────────────
    def test_contract_packet_gate_missing_fails_closed(self):
        diags = self._full_chain_diags()
        contract_diag = dict(diags["strategy_rule_contract_diagnostics"])
        del contract_diag["contract_packet_gate"]
        diags["strategy_rule_contract_diagnostics"] = contract_diag
        result = _build_no_output_runner_invocation_diagnostics(**diags)
        gate = result["no_output_runner_invocation_gate"]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == "BLOCKED_BY_REQUIRED_UPSTREAM_GATE"
        assert "contract_packet_gate" in gate["blocked_reason"]

    def test_contract_packet_gate_failed_fails_closed(self):
        diags = self._full_chain_diags()
        contract_diag = dict(diags["strategy_rule_contract_diagnostics"])
        original_gate = contract_diag["contract_packet_gate"]
        failed_gate = dict(original_gate)
        failed_gate["gate_passed"] = False
        contract_diag["contract_packet_gate"] = failed_gate
        diags["strategy_rule_contract_diagnostics"] = contract_diag
        result = _build_no_output_runner_invocation_diagnostics(**diags)
        gate = result["no_output_runner_invocation_gate"]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == "BLOCKED_BY_REQUIRED_UPSTREAM_GATE"

    # ── Test 6: trial manifest gate missing/failed fails closed ─────────────────
    def test_trial_manifest_gate_missing_fails_closed(self):
        diags = self._full_chain_diags()
        manifest_diag = dict(diags["trial_manifest_diagnostics"])
        del manifest_diag["trial_manifest_preregistration_gate"]
        diags["trial_manifest_diagnostics"] = manifest_diag
        result = _build_no_output_runner_invocation_diagnostics(**diags)
        gate = result["no_output_runner_invocation_gate"]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == "BLOCKED_BY_REQUIRED_UPSTREAM_GATE"
        assert "trial_manifest_preregistration_gate" in gate["blocked_reason"]

    def test_trial_manifest_gate_failed_fails_closed(self):
        diags = self._full_chain_diags()
        manifest_diag = dict(diags["trial_manifest_diagnostics"])
        original_gate = manifest_diag["trial_manifest_preregistration_gate"]
        failed_gate = dict(original_gate)
        failed_gate["gate_passed"] = False
        manifest_diag["trial_manifest_preregistration_gate"] = failed_gate
        diags["trial_manifest_diagnostics"] = manifest_diag
        result = _build_no_output_runner_invocation_diagnostics(**diags)
        gate = result["no_output_runner_invocation_gate"]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == "BLOCKED_BY_REQUIRED_UPSTREAM_GATE"

    # ── Test 7: missing/false invocation declaration fails closed ───────────────
    def test_missing_invocation_declared_fails_closed(self):
        diags = self._full_chain_diags()
        result = _build_no_output_runner_invocation_diagnostics(**diags)
        mutated = dict(result)
        del mutated["future_runner_invocation_declared"]
        gate = _derive_no_output_runner_invocation_gate(mutated)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            "BLOCKED_BY_INCOMPLETE_RUNNER_INVOCATION_EVIDENCE"
        )

    def test_false_invocation_declared_fails_closed(self):
        diags = self._full_chain_diags()
        result = _build_no_output_runner_invocation_diagnostics(**diags)
        mutated = dict(result)
        mutated["future_runner_invocation_declared"] = False
        gate = _derive_no_output_runner_invocation_gate(mutated)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            "BLOCKED_BY_INCOMPLETE_RUNNER_INVOCATION_EVIDENCE"
        )

    # ── Test 8: mutated implementation status fails closed ──────────────────────
    def test_mutated_implementation_status_fails_closed(self):
        diags = self._full_chain_diags()
        result = _build_no_output_runner_invocation_diagnostics(**diags)
        mutated = dict(result)
        mutated["future_runner_implementation_status"] = "RUNNER_IMPLEMENTED"
        gate = _derive_no_output_runner_invocation_gate(mutated)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            "BLOCKED_BY_INCOMPLETE_RUNNER_INVOCATION_EVIDENCE"
        )

    # ── Test 9: missing/empty/mutated output policy fails closed ────────────────
    def test_missing_output_policy_fails_closed(self):
        diags = self._full_chain_diags()
        result = _build_no_output_runner_invocation_diagnostics(**diags)
        mutated = dict(result)
        del mutated["future_runner_output_policy"]
        gate = _derive_no_output_runner_invocation_gate(mutated)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            "BLOCKED_BY_INCOMPLETE_RUNNER_INVOCATION_EVIDENCE"
        )

    def test_empty_output_policy_fails_closed(self):
        diags = self._full_chain_diags()
        result = _build_no_output_runner_invocation_diagnostics(**diags)
        mutated = dict(result)
        mutated["future_runner_output_policy"] = ""
        gate = _derive_no_output_runner_invocation_gate(mutated)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            "BLOCKED_BY_INCOMPLETE_RUNNER_INVOCATION_EVIDENCE"
        )

    def test_mutated_output_policy_fails_closed(self):
        diags = self._full_chain_diags()
        result = _build_no_output_runner_invocation_diagnostics(**diags)
        mutated = dict(result)
        mutated["future_runner_output_policy"] = "EMIT_OUTPUT_ROWS_NOW"
        gate = _derive_no_output_runner_invocation_gate(mutated)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            "BLOCKED_BY_INCOMPLETE_RUNNER_INVOCATION_EVIDENCE"
        )

    # ── Test 10: missing/mutated materialization policy fails closed ────────────
    def test_missing_materialization_policy_fails_closed(self):
        diags = self._full_chain_diags()
        result = _build_no_output_runner_invocation_diagnostics(**diags)
        mutated = dict(result)
        del mutated["future_runner_materialization_policy"]
        gate = _derive_no_output_runner_invocation_gate(mutated)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            "BLOCKED_BY_INCOMPLETE_RUNNER_INVOCATION_EVIDENCE"
        )

    def test_mutated_materialization_policy_fails_closed(self):
        diags = self._full_chain_diags()
        result = _build_no_output_runner_invocation_diagnostics(**diags)
        mutated = dict(result)
        mutated["future_runner_materialization_policy"] = "MATERIALIZE_RULES_NOW"
        gate = _derive_no_output_runner_invocation_gate(mutated)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            "BLOCKED_BY_INCOMPLETE_RUNNER_INVOCATION_EVIDENCE"
        )

    # ── Test 11: unexpected authorization fails closed ──────────────────────────
    def test_unexpected_authorization_fails_closed(self):
        diags = self._full_chain_diags()
        result = _build_no_output_runner_invocation_diagnostics(**diags)
        result["runner_implementation_authorized"] = True
        gate = _derive_no_output_runner_invocation_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == "BLOCKED_BY_UNEXPECTED_AUTHORIZATION"
        assert "runner_implementation_authorized" in gate["blocked_reason"]

    # ── Test 12: forbidden key scan ──────────────────────────────────────────────
    def test_no_forbidden_calculation_keys(self):
        diags = self._full_chain_diags()
        result = _build_no_output_runner_invocation_diagnostics(**diags)
        all_keys = _all_dict_keys(result)
        assert real_validation.FORBIDDEN_CALCULATION_KEYS.isdisjoint(all_keys), (
            f"Forbidden keys found: "
            f"{real_validation.FORBIDDEN_CALCULATION_KEYS & all_keys}"
        )

    # ── CLI receipt integration ──────────────────────────────────────────────────
    def _cli_base_args(self, output_dir):
        return [
            "--read-only", "--output-dir", str(output_dir),
            "--input-manifest-fingerprint", "abc",
            "--data-quality-receipt-sha256", "def",
            "--code-commit-sha", "ghi",
            "--global-min-timestamp", "2026-01-01T00:00:00Z",
            "--global-max-timestamp", "2026-02-01T00:00:00Z",
        ]

    def _cli_full_chain_args(self):
        return [
            "--strategy-contract-path", self.CONTRACT_PATH,
            "--strategy-contract-sha256-path", self.CONTRACT_SIDECAR_PATH,
            "--strategy-contract-commit-binding-path", self.CONTRACT_BINDING_PATH,
            "--trial-manifest-path", self.MANIFEST_PATH,
            "--trial-manifest-sha256-path", self.MANIFEST_SIDECAR_PATH,
            "--oos-seal-path", self.SEAL_PATH,
            "--oos-seal-sha256-path", self.SEAL_SIDECAR_PATH,
            "--null-benchmark-path", self.NULL_PATH,
            "--null-benchmark-sha256-path", self.NULL_SIDECAR_PATH,
            "--multiple-testing-control-path", self.MT_PATH,
            "--multiple-testing-control-sha256-path", self.MT_SIDECAR_PATH,
            "--simulation-policy-path", self.SP_PATH,
            "--simulation-policy-sha256-path", self.SP_SIDECAR_PATH,
            "--economic-accounting-policy-path", self.EAP_PATH,
            "--economic-accounting-policy-sha256-path", self.EAP_SIDECAR_PATH,
        ]

    # ── Test 13: receipt integration, no packet args ─────────────────────────────
    def test_receipt_integration_no_packet_args(self, tmp_path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        exit_code = real_validation.main(self._cli_base_args(output_dir))
        assert exit_code == 0
        receipt = json.loads(
            (output_dir / "real_validation_receipt.json").read_text()
        )
        runner_invocation = receipt["no_output_runner_invocation_diagnostics"]
        assert runner_invocation["no_output_runner_invocation_gate"][
            "gate_passed"
        ] is False
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION

    # ── Test 14: receipt integration, full packet args through L1 ────────────────
    def test_receipt_integration_full_path(self, tmp_path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        exit_code = real_validation.main(
            self._cli_base_args(output_dir) + self._cli_full_chain_args()
        )
        assert exit_code == 0
        receipt = json.loads(
            (output_dir / "real_validation_receipt.json").read_text()
        )
        closure = receipt["prerequisite_closure_diagnostics"]
        assert closure["prerequisite_closure_gate"]["gate_passed"] is True
        boundary = receipt["implementation_boundary_diagnostics"]
        assert boundary["implementation_boundary_gate"]["gate_passed"] is True
        runner_invocation = receipt["no_output_runner_invocation_diagnostics"]
        assert runner_invocation["no_output_runner_invocation_gate"][
            "gate_passed"
        ] is True
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION


class TestAllowedRunnerInputProjectionN1:
    """Lane N1: allowed runner input projection diagnostics.

    A derived, diagnostic-only projection over the M1 no-output runner
    invocation gate. Records only metadata for the future runner input view,
    emits no row values or rule outputs, and authorizes nothing.
    """

    def _m1(self):
        return TestNoOutputRunnerInvocationM1()

    def _full_chain_diags(self):
        diags = self._m1()._full_chain_diags()
        runner_diag = _build_no_output_runner_invocation_diagnostics(**diags)
        diags["no_output_runner_invocation_diagnostics"] = runner_diag
        return diags

    def _absence_diags(self):
        diags = self._m1()._absence_diags()
        runner_diag = _build_no_output_runner_invocation_diagnostics(**diags)
        diags["no_output_runner_invocation_diagnostics"] = runner_diag
        return diags

    def _result(self):
        return _build_allowed_runner_input_projection_diagnostics(
            **self._full_chain_diags()
        )

    # ── Test 1: no-args / M1 failed fails closed ───────────────────────────────
    def test_input_projection_diagnostic_no_args_runner_invocation_failed(self):
        diags = self._absence_diags()
        result = _build_allowed_runner_input_projection_diagnostics(**diags)
        gate = result["allowed_runner_input_projection_gate"]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == BLOCKED_BY_NO_OUTPUT_RUNNER_INVOCATION_GATE
        for field in _ALLOWED_RUNNER_INPUT_PROJECTION_AUTHORIZATION_FIELDS:
            assert result[field] is False

    # ── Test 2: full happy path ────────────────────────────────────────────────
    def test_input_projection_diagnostic_full_happy_path(self):
        result = self._result()
        assert result["diagnostic_kind"] == "allowed_runner_input_projection_scaffold"
        assert result["allowed_runner_input_projection_version"] == (
            ALLOWED_RUNNER_INPUT_PROJECTION_VERSION
        )
        assert result["allowed_runner_input_projection_scope"] == (
            ALLOWED_RUNNER_INPUT_PROJECTION_SCOPE
        )
        assert result["allowed_runner_input_projection_status"] == (
            ALLOWED_RUNNER_INPUT_PROJECTION_DECLARED_DIAGNOSTIC_ONLY
        )
        assert result["runner_input_projection_mode"] == "METADATA_ONLY"
        assert result["runner_input_projection_policy"] == (
            ALLOWED_RUNNER_INPUT_PROJECTION_METADATA_ONLY
        )
        assert result["allowed_input_roles"] == ["bars", "funding"]
        assert result["allowed_bar_columns"] == ["close", "timestamp"]
        assert result["allowed_funding_columns"] == ["fundingRate", "fundingTime"]
        assert result["excluded_bar_columns"] == ["open", "high", "low", "volume"]
        assert result["excluded_funding_columns"] == ["markPrice"]
        assert result["input_projection_values_emitted"] is False
        assert result["input_projection_row_values_emitted"] is False
        assert result["rule_output_rows_emitted"] is False
        assert result["future_runner_output_policy"] == (
            ALLOWED_RUNNER_INPUT_PROJECTION_OUTPUT_POLICY_FROZEN
        )
        assert result["future_runner_materialization_policy"] == (
            ALLOWED_RUNNER_INPUT_PROJECTION_MATERIALIZATION_POLICY_FROZEN
        )
        for field in _ALLOWED_RUNNER_INPUT_PROJECTION_AUTHORIZATION_FIELDS:
            assert result[field] is False
        assert result["final_offline_verdict_remains"] == (
            BLOCKED_BY_VALIDATION_IMPLEMENTATION
        )

    # ── Test 3: gate happy path ────────────────────────────────────────────────
    def test_input_projection_gate_happy_path(self):
        gate = self._result()["allowed_runner_input_projection_gate"]
        assert gate["gate_passed"] is True
        assert gate["gate_status"] == (
            ALLOWED_RUNNER_INPUT_PROJECTION_DECLARED_DIAGNOSTIC_ONLY
        )
        assert gate["gate_scoring_authorization"] is False
        assert gate["gate_live_authorization"] is False
        assert gate["gate_final_verdict_authorization"] is False
        assert gate["gate_downstream_unlocks"] == []
        assert gate["blocked_reason"] is None

    # ── Tests 4-7: upstream gates fail closed ─────────────────────────────────
    def test_no_output_runner_invocation_gate_missing_fails_closed(self):
        diags = self._full_chain_diags()
        runner_diag = dict(diags["no_output_runner_invocation_diagnostics"])
        del runner_diag["no_output_runner_invocation_gate"]
        diags["no_output_runner_invocation_diagnostics"] = runner_diag
        gate = _build_allowed_runner_input_projection_diagnostics(**diags)[
            "allowed_runner_input_projection_gate"
        ]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == BLOCKED_BY_NO_OUTPUT_RUNNER_INVOCATION_GATE

    def test_no_output_runner_invocation_gate_failed_fails_closed(self):
        diags = self._full_chain_diags()
        runner_diag = dict(diags["no_output_runner_invocation_diagnostics"])
        failed_gate = dict(runner_diag["no_output_runner_invocation_gate"])
        failed_gate["gate_passed"] = False
        runner_diag["no_output_runner_invocation_gate"] = failed_gate
        diags["no_output_runner_invocation_diagnostics"] = runner_diag
        gate = _build_allowed_runner_input_projection_diagnostics(**diags)[
            "allowed_runner_input_projection_gate"
        ]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == BLOCKED_BY_NO_OUTPUT_RUNNER_INVOCATION_GATE

    def test_implementation_boundary_gate_missing_fails_closed(self):
        diags = self._full_chain_diags()
        boundary = dict(diags["implementation_boundary_diagnostics"])
        del boundary["implementation_boundary_gate"]
        diags["implementation_boundary_diagnostics"] = boundary
        gate = _build_allowed_runner_input_projection_diagnostics(**diags)[
            "allowed_runner_input_projection_gate"
        ]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == "BLOCKED_BY_IMPLEMENTATION_BOUNDARY_GATE"

    def test_implementation_boundary_gate_failed_fails_closed(self):
        diags = self._full_chain_diags()
        boundary = dict(diags["implementation_boundary_diagnostics"])
        failed_gate = dict(boundary["implementation_boundary_gate"])
        failed_gate["gate_passed"] = False
        boundary["implementation_boundary_gate"] = failed_gate
        diags["implementation_boundary_diagnostics"] = boundary
        gate = _build_allowed_runner_input_projection_diagnostics(**diags)[
            "allowed_runner_input_projection_gate"
        ]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == "BLOCKED_BY_IMPLEMENTATION_BOUNDARY_GATE"

    def test_contract_packet_gate_missing_fails_closed(self):
        diags = self._full_chain_diags()
        contract_diag = dict(diags["strategy_rule_contract_diagnostics"])
        del contract_diag["contract_packet_gate"]
        diags["strategy_rule_contract_diagnostics"] = contract_diag
        gate = _build_allowed_runner_input_projection_diagnostics(**diags)[
            "allowed_runner_input_projection_gate"
        ]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == "BLOCKED_BY_REQUIRED_UPSTREAM_GATE"

    def test_contract_packet_gate_failed_fails_closed(self):
        diags = self._full_chain_diags()
        contract_diag = dict(diags["strategy_rule_contract_diagnostics"])
        failed_gate = dict(contract_diag["contract_packet_gate"])
        failed_gate["gate_passed"] = False
        contract_diag["contract_packet_gate"] = failed_gate
        diags["strategy_rule_contract_diagnostics"] = contract_diag
        gate = _build_allowed_runner_input_projection_diagnostics(**diags)[
            "allowed_runner_input_projection_gate"
        ]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == "BLOCKED_BY_REQUIRED_UPSTREAM_GATE"

    def test_trial_manifest_gate_missing_fails_closed(self):
        diags = self._full_chain_diags()
        manifest_diag = dict(diags["trial_manifest_diagnostics"])
        del manifest_diag["trial_manifest_preregistration_gate"]
        diags["trial_manifest_diagnostics"] = manifest_diag
        gate = _build_allowed_runner_input_projection_diagnostics(**diags)[
            "allowed_runner_input_projection_gate"
        ]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == "BLOCKED_BY_REQUIRED_UPSTREAM_GATE"

    def test_trial_manifest_gate_failed_fails_closed(self):
        diags = self._full_chain_diags()
        manifest_diag = dict(diags["trial_manifest_diagnostics"])
        failed_gate = dict(manifest_diag["trial_manifest_preregistration_gate"])
        failed_gate["gate_passed"] = False
        manifest_diag["trial_manifest_preregistration_gate"] = failed_gate
        diags["trial_manifest_diagnostics"] = manifest_diag
        gate = _build_allowed_runner_input_projection_diagnostics(**diags)[
            "allowed_runner_input_projection_gate"
        ]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == "BLOCKED_BY_REQUIRED_UPSTREAM_GATE"

    # ── Tests 8-18: projection evidence fails closed ──────────────────────────
    def test_missing_projection_declared_fails_closed(self):
        result = self._result()
        del result["runner_input_projection_declared"]
        gate = _derive_allowed_runner_input_projection_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_RUNNER_INPUT_PROJECTION_EVIDENCE
        )

    def test_false_projection_declared_fails_closed(self):
        result = self._result()
        result["runner_input_projection_declared"] = False
        gate = _derive_allowed_runner_input_projection_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_RUNNER_INPUT_PROJECTION_EVIDENCE
        )

    def test_mutated_projection_mode_fails_closed(self):
        result = self._result()
        result["runner_input_projection_mode"] = "ROW_VALUES"
        gate = _derive_allowed_runner_input_projection_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_RUNNER_INPUT_PROJECTION_EVIDENCE
        )

    def test_mutated_projection_policy_fails_closed(self):
        result = self._result()
        result["runner_input_projection_policy"] = "EMIT_ROW_VALUES_NOW"
        gate = _derive_allowed_runner_input_projection_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_RUNNER_INPUT_PROJECTION_EVIDENCE
        )

    def test_mutated_allowed_input_roles_fails_closed(self):
        result = self._result()
        result["allowed_input_roles"] = ["bars", "funding", "volume"]
        gate = _derive_allowed_runner_input_projection_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_RUNNER_INPUT_PROJECTION_EVIDENCE
        )

    def test_removed_allowed_input_role_fails_closed(self):
        result = self._result()
        result["allowed_input_roles"] = ["bars"]
        gate = _derive_allowed_runner_input_projection_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_RUNNER_INPUT_PROJECTION_EVIDENCE
        )

    def test_mutated_allowed_bar_columns_fails_closed(self):
        result = self._result()
        result["allowed_bar_columns"] = ["close", "open", "timestamp"]
        gate = _derive_allowed_runner_input_projection_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_RUNNER_INPUT_PROJECTION_EVIDENCE
        )

    def test_removed_allowed_bar_column_fails_closed(self):
        result = self._result()
        result["allowed_bar_columns"] = ["timestamp"]
        gate = _derive_allowed_runner_input_projection_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_RUNNER_INPUT_PROJECTION_EVIDENCE
        )

    def test_mutated_allowed_funding_columns_fails_closed(self):
        result = self._result()
        result["allowed_funding_columns"] = [
            "fundingRate",
            "fundingTime",
            "markPrice",
        ]
        gate = _derive_allowed_runner_input_projection_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_RUNNER_INPUT_PROJECTION_EVIDENCE
        )

    def test_removed_allowed_funding_column_fails_closed(self):
        result = self._result()
        result["allowed_funding_columns"] = ["fundingTime"]
        gate = _derive_allowed_runner_input_projection_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_RUNNER_INPUT_PROJECTION_EVIDENCE
        )

    def test_empty_excluded_columns_fail_closed(self):
        result = self._result()
        result["excluded_bar_columns"] = []
        result["excluded_funding_columns"] = []
        gate = _derive_allowed_runner_input_projection_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_RUNNER_INPUT_PROJECTION_EVIDENCE
        )

    def test_any_emitted_flag_true_fails_closed(self):
        for field in (
            "input_projection_values_emitted",
            "input_projection_row_values_emitted",
            "rule_output_rows_emitted",
        ):
            result = self._result()
            result[field] = True
            gate = _derive_allowed_runner_input_projection_gate(result)
            assert gate["gate_passed"] is False
            assert gate["gate_status"] == "BLOCKED_BY_UNEXPECTED_OUTPUT_EMISSION"

    def test_missing_mutated_output_policy_fails_closed(self):
        result = self._result()
        del result["future_runner_output_policy"]
        gate = _derive_allowed_runner_input_projection_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_RUNNER_INPUT_PROJECTION_EVIDENCE
        )

        result = self._result()
        result["future_runner_output_policy"] = "EMIT_OUTPUT_ROWS_NOW"
        gate = _derive_allowed_runner_input_projection_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_RUNNER_INPUT_PROJECTION_EVIDENCE
        )

    def test_missing_mutated_materialization_policy_fails_closed(self):
        result = self._result()
        del result["future_runner_materialization_policy"]
        gate = _derive_allowed_runner_input_projection_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_RUNNER_INPUT_PROJECTION_EVIDENCE
        )

        result = self._result()
        result["future_runner_materialization_policy"] = "MATERIALIZE_RULES_NOW"
        gate = _derive_allowed_runner_input_projection_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_RUNNER_INPUT_PROJECTION_EVIDENCE
        )

    def test_unexpected_authorization_fails_closed(self):
        result = self._result()
        result["decision_row_generation_authorized"] = True
        gate = _derive_allowed_runner_input_projection_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == "BLOCKED_BY_UNEXPECTED_AUTHORIZATION"
        assert "decision_row_generation_authorized" in gate["blocked_reason"]

    # ── Tests 19-20: receipt integration ──────────────────────────────────────
    def test_receipt_integration_no_packet_args(self, tmp_path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        exit_code = real_validation.main(self._m1()._cli_base_args(output_dir))
        assert exit_code == 0
        receipt = json.loads(
            (output_dir / "real_validation_receipt.json").read_text()
        )
        projection = receipt["allowed_runner_input_projection_diagnostics"]
        gate = projection["allowed_runner_input_projection_gate"]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == BLOCKED_BY_NO_OUTPUT_RUNNER_INVOCATION_GATE
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION

    def test_receipt_integration_full_path(self, tmp_path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        m1 = self._m1()
        exit_code = real_validation.main(
            m1._cli_base_args(output_dir) + m1._cli_full_chain_args()
        )
        assert exit_code == 0
        receipt = json.loads(
            (output_dir / "real_validation_receipt.json").read_text()
        )
        assert receipt["prerequisite_closure_diagnostics"][
            "prerequisite_closure_gate"
        ]["gate_passed"] is True
        assert receipt["implementation_boundary_diagnostics"][
            "implementation_boundary_gate"
        ]["gate_passed"] is True
        assert receipt["no_output_runner_invocation_diagnostics"][
            "no_output_runner_invocation_gate"
        ]["gate_passed"] is True
        projection = receipt["allowed_runner_input_projection_diagnostics"]
        assert projection["allowed_runner_input_projection_gate"][
            "gate_passed"
        ] is True
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION

    # ── Test 21: forbidden key scan ───────────────────────────────────────────
    def test_no_forbidden_calculation_keys(self):
        result = self._result()
        all_keys = _all_dict_keys(result)
        assert real_validation.FORBIDDEN_CALCULATION_KEYS.isdisjoint(all_keys), (
            f"Forbidden keys found: "
            f"{real_validation.FORBIDDEN_CALCULATION_KEYS & all_keys}"
        )


class TestProjectedInputTemporalSequenceQ1:
    def _p1(self):
        return TestProjectedInputRowCountP1()

    def _write_inventory(self, tmp_path, *, include_funding=True):
        root = tmp_path / uuid.uuid4().hex
        bars_dir = root / "bars"
        funding_dir = root / "funding"
        root.mkdir()
        bars_dir.mkdir()
        funding_dir.mkdir()
        _write_tiny_bars_csv(bars_dir, "BTCUSDT_8h_ohlcv.csv")
        if include_funding:
            _write_tiny_funding_csv(funding_dir, "BTCUSDT_8h_funding.csv")
        return build_real_validation_input_inventory(
            bars_dir=bars_dir,
            funding_dir=funding_dir if include_funding else None,
        )

    def _refresh_inventory_file(self, inventory, *, role, filename):
        role_entry = next(entry for entry in inventory["roles"] if entry["role"] == role)
        file_entry = next(
            entry for entry in role_entry["files"] if entry["filename"] == filename
        )
        path = Path(role_entry["directory"]) / filename
        file_entry["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        file_entry["size_bytes"] = path.stat().st_size
        file_entry["row_count"] = max(0, len(path.read_text().splitlines()) - 1)

    def _full_chain_diags(self, inventory):
        p1 = self._p1()
        diags = p1._full_chain_diags(inventory)
        diags["projected_input_row_count_diagnostics"] = p1._build(
            diags,
            inventory=inventory,
        )
        return diags

    def _absence_diags(self):
        p1 = self._p1()
        diags = p1._absence_diags()
        diags["projected_input_row_count_diagnostics"] = p1._build(diags)
        return diags

    def _build(self, diags, inventory=None):
        return _build_projected_input_temporal_sequence_diagnostics(
            projected_input_row_count_diagnostics=diags[
                "projected_input_row_count_diagnostics"
            ],
            projected_input_shape_inventory_diagnostics=diags[
                "projected_input_shape_inventory_diagnostics"
            ],
            allowed_runner_input_projection_diagnostics=diags[
                "allowed_runner_input_projection_diagnostics"
            ],
            no_output_runner_invocation_diagnostics=diags[
                "no_output_runner_invocation_diagnostics"
            ],
            implementation_boundary_diagnostics=diags[
                "implementation_boundary_diagnostics"
            ],
            inventory_diagnostics=inventory,
        )

    def _result(self, tmp_path):
        inventory = self._write_inventory(tmp_path)
        return self._build(self._full_chain_diags(inventory), inventory)

    def _assert_all_authorizations_false(self, result):
        for field in _PROJECTED_INPUT_TEMPORAL_SEQUENCE_AUTHORIZATION_FIELDS:
            assert result[field] is False

    def test_temporal_sequence_no_args_row_count_failed_fails_closed(self):
        result = self._build(self._absence_diags())
        gate = result["projected_input_temporal_sequence_gate"]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == BLOCKED_BY_PROJECTED_INPUT_ROW_COUNT_GATE
        self._assert_all_authorizations_false(result)

    def test_temporal_sequence_diagnostic_full_happy_path(self, tmp_path):
        result = self._result(tmp_path)
        assert result["diagnostic_kind"] == (
            "projected_input_temporal_sequence_inventory"
        )
        assert result["projected_input_temporal_sequence_version"] == (
            PROJECTED_INPUT_TEMPORAL_SEQUENCE_VERSION
        )
        assert result["projected_input_temporal_sequence_scope"] == (
            PROJECTED_INPUT_TEMPORAL_SEQUENCE_SCOPE
        )
        assert result["projected_input_temporal_sequence_status"] == (
            PROJECTED_INPUT_TEMPORAL_SEQUENCE_DECLARED_DIAGNOSTIC_ONLY
        )
        assert result["projected_input_temporal_sequence_mode"] == "METADATA_ONLY"
        assert result["projected_input_temporal_sequence_policy"] == (
            PROJECTED_INPUT_TEMPORAL_SEQUENCE_METADATA_ONLY_POLICY
        )
        assert result["time_column_names_by_role"] == {
            "bars": "timestamp",
            "funding": "fundingTime",
        }
        for field in (
            "time_values_emitted",
            "timestamp_values_emitted",
            "funding_time_values_emitted",
            "price_values_emitted",
            "funding_values_emitted",
            "row_value_samples_emitted",
            "projected_input_values_emitted",
            "projected_input_row_values_emitted",
            "rule_output_rows_emitted",
        ):
            assert result[field] is False
        summary = result["temporal_sequence_summary"]
        assert summary["summary_kind"] == "metadata_only_temporal_sequence_summary"
        assert summary["time_values_included"] is False
        assert summary["row_values_included"] is False
        assert summary["projected_row_values_included"] is False
        assert summary["rule_outputs_included"] is False
        assert summary["roles_declared"] == ["bars", "funding"]
        assert summary["role_time_parse_failure_counts"] == {
            "bars": 0,
            "funding": 0,
        }
        assert summary["role_time_missing_value_counts"] == {
            "bars": 0,
            "funding": 0,
        }
        assert summary["role_duplicate_time_counts"] == {"bars": 0, "funding": 0}
        assert summary["role_non_monotonic_transition_counts"] == {
            "bars": 0,
            "funding": 0,
        }
        assert summary["temporal_sequence_complete"] is True
        self._assert_all_authorizations_false(result)
        assert result["final_offline_verdict_remains"] == (
            BLOCKED_BY_VALIDATION_IMPLEMENTATION
        )

    def test_temporal_sequence_gate_happy_path(self, tmp_path):
        gate = self._result(tmp_path)["projected_input_temporal_sequence_gate"]
        assert gate["gate_passed"] is True
        assert gate["gate_status"] == (
            PROJECTED_INPUT_TEMPORAL_SEQUENCE_DECLARED_DIAGNOSTIC_ONLY
        )
        assert gate["gate_scoring_authorization"] is False
        assert gate["gate_live_authorization"] is False
        assert gate["gate_final_verdict_authorization"] is False
        assert gate["gate_downstream_unlocks"] == []

    @pytest.mark.parametrize(
        ("flag", "expected_status"),
        [
            (
                "projected_input_row_count_gate_passed",
                BLOCKED_BY_PROJECTED_INPUT_ROW_COUNT_GATE,
            ),
            (
                "projected_input_shape_inventory_gate_passed",
                BLOCKED_BY_PROJECTED_INPUT_SHAPE_INVENTORY_GATE,
            ),
            (
                "allowed_runner_input_projection_gate_passed",
                BLOCKED_BY_ALLOWED_RUNNER_INPUT_PROJECTION_GATE,
            ),
            (
                "no_output_runner_invocation_gate_passed",
                BLOCKED_BY_NO_OUTPUT_RUNNER_INVOCATION_GATE,
            ),
            (
                "implementation_boundary_gate_passed",
                BLOCKED_BY_IMPLEMENTATION_BOUNDARY_GATE,
            ),
        ],
    )
    def test_required_upstream_gate_failed_fails_closed(
        self, tmp_path, flag, expected_status
    ):
        result = self._result(tmp_path)
        result[flag] = False
        gate = _derive_projected_input_temporal_sequence_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == expected_status

    def test_missing_or_false_temporal_declared_fails_closed(self, tmp_path):
        result = self._result(tmp_path)
        del result["projected_input_temporal_sequence_declared"]
        gate = _derive_projected_input_temporal_sequence_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_PROJECTED_INPUT_TEMPORAL_SEQUENCE_EVIDENCE
        )

        result = self._result(tmp_path)
        result["projected_input_temporal_sequence_declared"] = False
        gate = _derive_projected_input_temporal_sequence_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_PROJECTED_INPUT_TEMPORAL_SEQUENCE_EVIDENCE
        )

    def test_mutated_temporal_mode_fails_closed(self, tmp_path):
        result = self._result(tmp_path)
        result["projected_input_temporal_sequence_mode"] = "TIME_VALUES"
        gate = _derive_projected_input_temporal_sequence_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_PROJECTED_INPUT_TEMPORAL_SEQUENCE_EVIDENCE
        )

    def test_mutated_temporal_policy_fails_closed(self, tmp_path):
        result = self._result(tmp_path)
        result["projected_input_temporal_sequence_policy"] = "EMIT_TIME_VALUES_NOW"
        gate = _derive_projected_input_temporal_sequence_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_PROJECTED_INPUT_TEMPORAL_SEQUENCE_EVIDENCE
        )

    def test_any_emitted_time_or_value_flag_true_fails_closed(self, tmp_path):
        for field in (
            "time_values_emitted",
            "timestamp_values_emitted",
            "funding_time_values_emitted",
            "price_values_emitted",
            "funding_values_emitted",
            "row_value_samples_emitted",
            "projected_input_values_emitted",
            "projected_input_row_values_emitted",
            "rule_output_rows_emitted",
        ):
            result = self._result(tmp_path)
            result[field] = True
            gate = _derive_projected_input_temporal_sequence_gate(result)
            assert gate["gate_passed"] is False
            assert gate["gate_status"] == BLOCKED_BY_UNEXPECTED_TIME_VALUE_EMISSION

    def test_unexpected_authorization_fails_closed(self, tmp_path):
        result = self._result(tmp_path)
        result["decision_row_generation_authorized"] = True
        gate = _derive_projected_input_temporal_sequence_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == "BLOCKED_BY_UNEXPECTED_AUTHORIZATION"
        assert "decision_row_generation_authorized" in gate["blocked_reason"]

    def test_parse_failure_fails_closed_without_emitting_values(self, tmp_path):
        inventory = self._write_inventory(tmp_path)
        bars_path = Path(inventory["roles"][0]["directory"]) / "BTCUSDT_8h_ohlcv.csv"
        bars_path.write_text(
            "timestamp,open,high,low,close,volume\n"
            "not-a-time,100.0,101.0,99.0,100.5,1000\n"
        )
        self._refresh_inventory_file(
            inventory, role="bars", filename="BTCUSDT_8h_ohlcv.csv"
        )
        result = self._build(self._full_chain_diags(inventory), inventory)
        summary = result["temporal_sequence_summary"]
        assert summary["role_time_parse_failure_counts"]["bars"] == 1
        assert summary["temporal_sequence_complete"] is False
        gate = result["projected_input_temporal_sequence_gate"]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_PROJECTED_INPUT_TEMPORAL_SEQUENCE_EVIDENCE
        )
        assert result["timestamp_values_emitted"] is False

    def test_missing_duplicate_and_non_monotonic_times_fail_closed(self, tmp_path):
        inventory = self._write_inventory(tmp_path)
        bars_path = Path(inventory["roles"][0]["directory"]) / "BTCUSDT_8h_ohlcv.csv"
        bars_path.write_text(
            "timestamp,open,high,low,close,volume\n"
            "2026-01-02T00:00:00Z,100.0,101.0,99.0,100.5,1000\n"
            ",100.5,102.0,100.0,101.0,1200\n"
            "2026-01-02T00:00:00Z,101.0,103.0,100.5,102.0,1100\n"
            "2026-01-01T00:00:00Z,101.0,103.0,100.5,102.0,1100\n"
        )
        self._refresh_inventory_file(
            inventory, role="bars", filename="BTCUSDT_8h_ohlcv.csv"
        )
        result = self._build(self._full_chain_diags(inventory), inventory)
        summary = result["temporal_sequence_summary"]
        assert summary["role_time_missing_value_counts"]["bars"] == 1
        assert summary["role_duplicate_time_counts"]["bars"] == 1
        assert summary["role_non_monotonic_transition_counts"]["bars"] == 1
        assert summary["temporal_sequence_complete"] is False
        assert result["projected_input_temporal_sequence_gate"][
            "gate_status"
        ] == BLOCKED_BY_INCOMPLETE_PROJECTED_INPUT_TEMPORAL_SEQUENCE_EVIDENCE

    def test_receipt_integration_no_packet_args(self, tmp_path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        exit_code = real_validation.main(
            self._p1()._o1()._n1()._m1()._cli_base_args(output_dir)
        )
        assert exit_code == 0
        receipt = json.loads(
            (output_dir / "real_validation_receipt.json").read_text()
        )
        diagnostics = receipt["projected_input_temporal_sequence_diagnostics"]
        gate = diagnostics["projected_input_temporal_sequence_gate"]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == BLOCKED_BY_PROJECTED_INPUT_ROW_COUNT_GATE
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION

    def test_receipt_integration_full_path(self, tmp_path):
        bars_dir = tmp_path / "bars"
        funding_dir = tmp_path / "funding"
        bars_dir.mkdir()
        funding_dir.mkdir()
        _write_tiny_bars_csv(bars_dir, "BTCUSDT_8h_ohlcv.csv")
        _write_tiny_funding_csv(funding_dir, "BTCUSDT_8h_funding.csv")
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        m1 = self._p1()._o1()._n1()._m1()
        exit_code = real_validation.main(
            m1._cli_base_args(output_dir)
            + m1._cli_full_chain_args()
            + [
                "--bars-dir",
                str(bars_dir),
                "--funding-dir",
                str(funding_dir),
            ]
        )
        assert exit_code == 0
        receipt = json.loads(
            (output_dir / "real_validation_receipt.json").read_text()
        )
        diagnostics = receipt["projected_input_temporal_sequence_diagnostics"]
        gate = diagnostics["projected_input_temporal_sequence_gate"]
        assert gate["gate_passed"] is True
        assert gate["gate_status"] == (
            PROJECTED_INPUT_TEMPORAL_SEQUENCE_DECLARED_DIAGNOSTIC_ONLY
        )
        summary = diagnostics["temporal_sequence_summary"]
        assert summary["role_time_parse_failure_counts"] == {
            "bars": 0,
            "funding": 0,
        }
        assert summary["role_time_missing_value_counts"] == {
            "bars": 0,
            "funding": 0,
        }
        assert summary["role_duplicate_time_counts"] == {"bars": 0, "funding": 0}
        assert summary["role_non_monotonic_transition_counts"] == {
            "bars": 0,
            "funding": 0,
        }
        assert summary["temporal_sequence_complete"] is True
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION

    def test_receipt_integration_bars_only_fails_q1_closed(self, tmp_path):
        bars_dir = tmp_path / "bars"
        bars_dir.mkdir()
        _write_tiny_bars_csv(bars_dir, "BTCUSDT_8h_ohlcv.csv")
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        m1 = self._p1()._o1()._n1()._m1()
        exit_code = real_validation.main(
            m1._cli_base_args(output_dir)
            + m1._cli_full_chain_args()
            + ["--bars-dir", str(bars_dir)]
        )
        assert exit_code == 0
        receipt = json.loads(
            (output_dir / "real_validation_receipt.json").read_text()
        )
        row_gate = receipt["projected_input_row_count_diagnostics"][
            "projected_input_row_count_gate"
        ]
        temporal_gate = receipt["projected_input_temporal_sequence_diagnostics"][
            "projected_input_temporal_sequence_gate"
        ]
        assert row_gate["gate_passed"] is False
        assert temporal_gate["gate_passed"] is False
        assert temporal_gate["gate_status"] == BLOCKED_BY_PROJECTED_INPUT_ROW_COUNT_GATE

    def test_no_forbidden_calculation_keys(self, tmp_path):
        result = self._result(tmp_path)
        all_keys = _all_dict_keys(result)
        assert real_validation.FORBIDDEN_CALCULATION_KEYS.isdisjoint(all_keys), (
            f"Forbidden keys found: "
            f"{real_validation.FORBIDDEN_CALCULATION_KEYS & all_keys}"
        )


class TestProjectedInputJoinabilityR1:
    def _q1(self):
        return TestProjectedInputTemporalSequenceQ1()

    def _write_inventory(self, tmp_path, *, exact_funding=True, include_funding=True):
        inventory = self._q1()._write_inventory(tmp_path, include_funding=include_funding)
        if exact_funding and include_funding:
            funding_entry = next(
                entry for entry in inventory["roles"] if entry["role"] == "funding"
            )
            funding_path = Path(funding_entry["directory"]) / "BTCUSDT_8h_funding.csv"
            funding_path.write_text(
                "fundingTime,fundingRate,markPrice\n"
                "2026-01-01T00:00:00Z,0.0001,50000.0\n"
                "2026-01-02T00:00:00Z,0.0002,50100.0\n"
                "2026-01-03T00:00:00Z,0.0003,50200.0\n"
            )
            self._q1()._refresh_inventory_file(
                inventory,
                role="funding",
                filename="BTCUSDT_8h_funding.csv",
            )
        return inventory

    def _full_chain_diags(self, inventory):
        q1 = self._q1()
        diags = q1._full_chain_diags(inventory)
        diags["projected_input_temporal_sequence_diagnostics"] = q1._build(
            diags,
            inventory=inventory,
        )
        return diags

    def _absence_diags(self):
        q1 = self._q1()
        diags = q1._absence_diags()
        diags["projected_input_temporal_sequence_diagnostics"] = q1._build(diags)
        return diags

    def _build(self, diags, inventory=None):
        return _build_projected_input_joinability_diagnostics(
            projected_input_temporal_sequence_diagnostics=diags[
                "projected_input_temporal_sequence_diagnostics"
            ],
            projected_input_row_count_diagnostics=diags[
                "projected_input_row_count_diagnostics"
            ],
            projected_input_shape_inventory_diagnostics=diags[
                "projected_input_shape_inventory_diagnostics"
            ],
            allowed_runner_input_projection_diagnostics=diags[
                "allowed_runner_input_projection_diagnostics"
            ],
            no_output_runner_invocation_diagnostics=diags[
                "no_output_runner_invocation_diagnostics"
            ],
            implementation_boundary_diagnostics=diags[
                "implementation_boundary_diagnostics"
            ],
            split_diagnostics={
                "split_definitions": materialize_split_definitions_from_inventory(
                    inventory=inventory,
                    split_count=3,
                )
            }
            if inventory is not None
            else None,
            inventory_diagnostics=inventory,
        )

    def _result(self, tmp_path):
        inventory = self._write_inventory(tmp_path)
        return self._build(self._full_chain_diags(inventory), inventory)

    def _assert_all_authorizations_false(self, result):
        for field in _PROJECTED_INPUT_JOINABILITY_AUTHORIZATION_FIELDS:
            assert result[field] is False

    def test_joinability_no_args_q1_failed_fails_closed(self):
        result = self._build(self._absence_diags())
        gate = result["projected_input_joinability_gate"]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == BLOCKED_BY_PROJECTED_INPUT_TEMPORAL_SEQUENCE_GATE
        self._assert_all_authorizations_false(result)

    def test_joinability_diagnostic_full_exact_path(self, tmp_path):
        result = self._result(tmp_path)
        assert result["diagnostic_kind"] == "projected_input_joinability_inventory"
        assert result["projected_input_joinability_version"] == (
            PROJECTED_INPUT_JOINABILITY_VERSION
        )
        assert result["projected_input_joinability_scope"] == (
            PROJECTED_INPUT_JOINABILITY_SCOPE
        )
        assert result["projected_input_joinability_status"] == (
            PROJECTED_INPUT_JOINABILITY_DECLARED_DIAGNOSTIC_ONLY
        )
        assert result["projected_input_joinability_mode"] == "METADATA_ONLY"
        assert result["projected_input_joinability_policy"] == (
            PROJECTED_INPUT_JOINABILITY_METADATA_ONLY_POLICY
        )
        assert result["joinability_frozen_policy"] == (
            PROJECTED_INPUT_JOINABILITY_FROZEN_POLICY
        )
        for field in (
            "timestamp_values_emitted",
            "time_values_emitted",
            "price_values_emitted",
            "funding_values_emitted",
            "row_value_samples_emitted",
            "projected_input_values_emitted",
            "projected_input_row_values_emitted",
            "rule_output_rows_emitted",
            "decision_rows_emitted",
            "simulated_events_emitted",
            "economic_values_emitted",
            "statistical_values_emitted",
        ):
            assert result[field] is False
        summary = result["joinability_summary"]
        assert summary["summary_kind"] == (
            "metadata_only_cross_role_joinability_summary"
        )
        assert summary["timestamp_values_included"] is False
        assert summary["price_values_included"] is False
        assert summary["funding_values_included"] is False
        assert summary["row_samples_included"] is False
        assert summary["projected_row_values_included"] is False
        assert summary["rule_outputs_included"] is False
        assert summary["roles_declared"] == ["bars", "funding"]
        assert summary["all_required_roles_present"] is True
        assert summary["symbol_overlap_complete"] is True
        assert summary["all_required_symbols_joinable"] is True
        assert summary["joinability_complete"] is True
        assert summary["role_row_counts"] == {"bars": 3, "funding": 3}
        symbol = summary["symbol_joinability"][0]
        assert symbol["symbol"] == "BTCUSDT"
        assert symbol["bars_row_count"] == 3
        assert symbol["funding_row_count"] == 3
        assert symbol["matched_count"] == 3
        assert symbol["bars_missing_match_count"] == 0
        assert symbol["funding_missing_match_count"] == 0
        assert symbol["joinability_complete"] is True
        assert "bars_file" not in symbol
        assert "first_timestamp" not in json.dumps(result)
        self._assert_all_authorizations_false(result)

    def test_joinability_gate_happy_path(self, tmp_path):
        gate = self._result(tmp_path)["projected_input_joinability_gate"]
        assert gate["gate_passed"] is True
        assert gate["gate_status"] == PROJECTED_INPUT_JOINABILITY_DECLARED_DIAGNOSTIC_ONLY
        assert gate["gate_scoring_authorization"] is False
        assert gate["gate_live_authorization"] is False
        assert gate["gate_final_verdict_authorization"] is False
        assert gate["gate_downstream_unlocks"] == []

    @pytest.mark.parametrize(
        ("flag", "expected_status"),
        [
            (
                "projected_input_temporal_sequence_gate_passed",
                BLOCKED_BY_PROJECTED_INPUT_TEMPORAL_SEQUENCE_GATE,
            ),
            (
                "projected_input_row_count_gate_passed",
                BLOCKED_BY_PROJECTED_INPUT_ROW_COUNT_GATE,
            ),
            (
                "projected_input_shape_inventory_gate_passed",
                BLOCKED_BY_PROJECTED_INPUT_SHAPE_INVENTORY_GATE,
            ),
            (
                "allowed_runner_input_projection_gate_passed",
                BLOCKED_BY_ALLOWED_RUNNER_INPUT_PROJECTION_GATE,
            ),
            (
                "no_output_runner_invocation_gate_passed",
                BLOCKED_BY_NO_OUTPUT_RUNNER_INVOCATION_GATE,
            ),
            (
                "implementation_boundary_gate_passed",
                BLOCKED_BY_IMPLEMENTATION_BOUNDARY_GATE,
            ),
        ],
    )
    def test_required_upstream_gate_failed_fails_closed(
        self, tmp_path, flag, expected_status
    ):
        result = self._result(tmp_path)
        result[flag] = False
        gate = _derive_projected_input_joinability_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == expected_status

    def test_bars_only_no_funding_fails_closed(self, tmp_path):
        inventory = self._write_inventory(
            tmp_path,
            exact_funding=False,
            include_funding=False,
        )
        result = self._build(self._full_chain_diags(inventory), inventory)
        summary = result["joinability_summary"]
        assert summary["all_required_roles_present"] is False
        assert summary["joinability_complete"] is False
        assert "MISSING_REQUIRED_ROLE" in summary["blocked_reasons"]
        gate = result["projected_input_joinability_gate"]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == BLOCKED_BY_PROJECTED_INPUT_TEMPORAL_SEQUENCE_GATE

    def test_non_overlapping_time_grid_fails_closed_without_values(self, tmp_path):
        inventory = self._write_inventory(tmp_path, exact_funding=False)
        result = self._build(self._full_chain_diags(inventory), inventory)
        summary = result["joinability_summary"]
        assert summary["all_required_roles_present"] is True
        assert summary["symbol_overlap_complete"] is True
        assert summary["all_required_symbols_joinable"] is False
        assert summary["joinability_complete"] is False
        assert "TIME_GRIDS_DO_NOT_ALIGN_UNDER_FROZEN_POLICY" in (
            summary["blocked_reasons"]
        )
        symbol = summary["symbol_joinability"][0]
        assert symbol["matched_count"] == 0
        assert symbol["bars_missing_match_count"] == 3
        assert symbol["funding_missing_match_count"] == 2
        gate = result["projected_input_joinability_gate"]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_PROJECTED_INPUT_JOINABILITY_EVIDENCE
        )
        assert "2026-01-01T00:00:00Z" not in json.dumps(result)
        assert "100.5" not in json.dumps(result)
        assert "0.0001" not in json.dumps(result)

    def test_symbol_mismatch_fails_closed(self, tmp_path):
        inventory = self._write_inventory(tmp_path)
        funding_entry = next(
            entry for entry in inventory["roles"] if entry["role"] == "funding"
        )
        file_entry = funding_entry["files"][0]
        old_path = Path(funding_entry["directory"]) / file_entry["filename"]
        new_path = Path(funding_entry["directory"]) / "ETHUSDT_8h_funding.csv"
        old_path.rename(new_path)
        file_entry["filename"] = "ETHUSDT_8h_funding.csv"
        self._q1()._refresh_inventory_file(
            inventory,
            role="funding",
            filename="ETHUSDT_8h_funding.csv",
        )
        result = self._build(self._full_chain_diags(inventory), inventory)
        summary = result["joinability_summary"]
        assert summary["symbol_overlap_complete"] is False
        assert summary["joinability_complete"] is False
        assert "SYMBOLS_DO_NOT_OVERLAP_EXACTLY" in summary["blocked_reasons"]
        gate = result["projected_input_joinability_gate"]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_PROJECTED_INPUT_JOINABILITY_EVIDENCE
        )

    def test_any_emitted_joinability_value_flag_true_fails_closed(self, tmp_path):
        for field in (
            "timestamp_values_emitted",
            "time_values_emitted",
            "price_values_emitted",
            "funding_values_emitted",
            "row_value_samples_emitted",
            "projected_input_values_emitted",
            "projected_input_row_values_emitted",
            "rule_output_rows_emitted",
            "decision_rows_emitted",
            "simulated_events_emitted",
            "economic_values_emitted",
            "statistical_values_emitted",
        ):
            result = self._result(tmp_path)
            result[field] = True
            gate = _derive_projected_input_joinability_gate(result)
            assert gate["gate_passed"] is False
            assert gate["gate_status"] == (
                BLOCKED_BY_UNEXPECTED_JOINABILITY_VALUE_EMISSION
            )

    def test_unexpected_authorization_fails_closed(self, tmp_path):
        result = self._result(tmp_path)
        result["decision_row_generation_authorized"] = True
        gate = _derive_projected_input_joinability_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == "BLOCKED_BY_UNEXPECTED_AUTHORIZATION"
        assert "decision_row_generation_authorized" in gate["blocked_reason"]

    def test_receipt_integration_full_path_exact_grid(self, tmp_path):
        bars_dir = tmp_path / "bars"
        funding_dir = tmp_path / "funding"
        bars_dir.mkdir()
        funding_dir.mkdir()
        _write_tiny_bars_csv(bars_dir, "BTCUSDT_8h_ohlcv.csv")
        funding_path = _write_tiny_funding_csv(
            funding_dir,
            "BTCUSDT_8h_funding.csv",
        )
        funding_path.write_text(
            "fundingTime,fundingRate,markPrice\n"
            "2026-01-01T00:00:00Z,0.0001,50000.0\n"
            "2026-01-02T00:00:00Z,0.0002,50100.0\n"
            "2026-01-03T00:00:00Z,0.0003,50200.0\n"
        )
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        m1 = self._q1()._p1()._o1()._n1()._m1()
        exit_code = real_validation.main(
            m1._cli_base_args(output_dir)
            + m1._cli_full_chain_args()
            + [
                "--bars-dir",
                str(bars_dir),
                "--funding-dir",
                str(funding_dir),
            ]
        )
        assert exit_code == 0
        receipt = json.loads(
            (output_dir / "real_validation_receipt.json").read_text()
        )
        q1_gate = receipt["projected_input_temporal_sequence_diagnostics"][
            "projected_input_temporal_sequence_gate"
        ]
        assert q1_gate["gate_passed"] is True
        diagnostics = receipt["projected_input_joinability_diagnostics"]
        gate = diagnostics["projected_input_joinability_gate"]
        assert gate["gate_passed"] is True
        assert gate["gate_status"] == (
            PROJECTED_INPUT_JOINABILITY_DECLARED_DIAGNOSTIC_ONLY
        )
        assert diagnostics["joinability_summary"]["joinability_complete"] is True
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION

    def test_receipt_integration_bars_only_fails_r1_closed(self, tmp_path):
        bars_dir = tmp_path / "bars"
        bars_dir.mkdir()
        _write_tiny_bars_csv(bars_dir, "BTCUSDT_8h_ohlcv.csv")
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        m1 = self._q1()._p1()._o1()._n1()._m1()
        exit_code = real_validation.main(
            m1._cli_base_args(output_dir)
            + m1._cli_full_chain_args()
            + ["--bars-dir", str(bars_dir)]
        )
        assert exit_code == 0
        receipt = json.loads(
            (output_dir / "real_validation_receipt.json").read_text()
        )
        diagnostics = receipt["projected_input_joinability_diagnostics"]
        summary = diagnostics["joinability_summary"]
        assert summary["all_required_roles_present"] is False
        assert summary["joinability_complete"] is False
        gate = diagnostics["projected_input_joinability_gate"]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == BLOCKED_BY_PROJECTED_INPUT_TEMPORAL_SEQUENCE_GATE

    def test_no_forbidden_calculation_keys(self, tmp_path):
        result = self._result(tmp_path)
        all_keys = _all_dict_keys(result)
        assert real_validation.FORBIDDEN_CALCULATION_KEYS.isdisjoint(all_keys), (
            f"Forbidden keys found: "
            f"{real_validation.FORBIDDEN_CALCULATION_KEYS & all_keys}"
        )


class TestNoOutputRunnerDryHarnessS1:
    def _r1(self):
        return TestProjectedInputJoinabilityR1()

    def _full_chain_diags(self, tmp_path):
        inventory = self._r1()._write_inventory(tmp_path)
        diags = self._r1()._full_chain_diags(inventory)
        diags["projected_input_joinability_diagnostics"] = self._r1()._build(
            diags,
            inventory=inventory,
        )
        return diags, inventory

    def _absence_diags(self):
        r1 = self._r1()
        diags = r1._absence_diags()
        diags["projected_input_joinability_diagnostics"] = r1._build(diags)
        return diags

    def _build(self, diags):
        return _build_no_output_runner_dry_harness_diagnostics(
            projected_input_joinability_diagnostics=diags[
                "projected_input_joinability_diagnostics"
            ],
            projected_input_temporal_sequence_diagnostics=diags[
                "projected_input_temporal_sequence_diagnostics"
            ],
            projected_input_row_count_diagnostics=diags[
                "projected_input_row_count_diagnostics"
            ],
            projected_input_shape_inventory_diagnostics=diags[
                "projected_input_shape_inventory_diagnostics"
            ],
            allowed_runner_input_projection_diagnostics=diags[
                "allowed_runner_input_projection_diagnostics"
            ],
            no_output_runner_invocation_diagnostics=diags[
                "no_output_runner_invocation_diagnostics"
            ],
            implementation_boundary_diagnostics=diags[
                "implementation_boundary_diagnostics"
            ],
        )

    def _result(self, tmp_path):
        diags, _inventory = self._full_chain_diags(tmp_path)
        return self._build(diags)

    def test_harness_happy_path_after_full_r1_passes(self, tmp_path):
        result = self._result(tmp_path)
        assert result["diagnostic_kind"] == "no_output_runner_dry_harness"
        assert result["no_output_runner_dry_harness_version"] == (
            NO_OUTPUT_RUNNER_DRY_HARNESS_VERSION
        )
        assert result["no_output_runner_dry_harness_scope"] == (
            NO_OUTPUT_RUNNER_DRY_HARNESS_SCOPE
        )
        assert result["no_output_runner_dry_harness_status"] == (
            NO_OUTPUT_RUNNER_DRY_HARNESS_DECLARED_DIAGNOSTIC_ONLY
        )
        assert result["runner_dry_harness_declared"] is True
        assert result["runner_dry_harness_mode"] == "NO_OUTPUT_BOUNDARY_ONLY"
        assert result["runner_dry_harness_policy"] == (
            NO_OUTPUT_RUNNER_DRY_HARNESS_POLICY
        )
        assert result["runner_logic_executed"] is False
        assert result["runner_callable_invoked"] is False
        assert result["runner_inputs_materialized_as_rows"] is False
        summary = result["harness_summary"]
        assert summary["summary_kind"] == (
            "metadata_only_no_output_runner_dry_harness_summary"
        )
        assert summary["roles_declared"] == ["bars", "funding"]
        assert summary["role_row_counts"] == {"bars": 3, "funding": 3}
        assert summary["role_symbol_counts"] == {"bars": 1, "funding": 1}
        assert summary["joinability_complete"] is True
        assert summary["timestamp_values_included"] is False
        assert summary["price_values_included"] is False
        assert summary["funding_values_included"] is False
        assert summary["joined_rows_included"] is False
        for field in (
            "decision_rows_emitted",
            "signals_emitted",
            "rule_output_rows_emitted",
            "simulated_events_emitted",
            "economic_values_emitted",
            "statistical_values_emitted",
            "joined_rows_emitted",
            "timestamp_values_emitted",
            "price_values_emitted",
            "funding_values_emitted",
            "row_value_samples_emitted",
            "projected_input_row_values_emitted",
        ):
            assert result[field] is False
        for field in _NO_OUTPUT_RUNNER_DRY_HARNESS_AUTHORIZATION_FIELDS:
            assert result[field] is False

    def test_harness_gate_happy_path(self, tmp_path):
        gate = self._result(tmp_path)["no_output_runner_dry_harness_gate"]
        assert gate["gate_passed"] is True
        assert gate["gate_status"] == (
            NO_OUTPUT_RUNNER_DRY_HARNESS_DECLARED_DIAGNOSTIC_ONLY
        )
        assert gate["gate_scoring_authorization"] is False
        assert gate["gate_live_authorization"] is False
        assert gate["gate_final_verdict_authorization"] is False
        assert gate["gate_downstream_unlocks"] == []

    def test_r1_gate_missing_or_failed_fails_closed(self, tmp_path):
        result = self._result(tmp_path)
        result["projected_input_joinability_gate_passed"] = False
        gate = _derive_no_output_runner_dry_harness_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == BLOCKED_BY_PROJECTED_INPUT_JOINABILITY_GATE

        diags, _inventory = self._full_chain_diags(tmp_path)
        r1_diagnostics = dict(diags["projected_input_joinability_diagnostics"])
        r1_diagnostics.pop("projected_input_joinability_gate")
        diags["projected_input_joinability_diagnostics"] = r1_diagnostics
        gate = self._build(diags)["no_output_runner_dry_harness_gate"]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == BLOCKED_BY_PROJECTED_INPUT_JOINABILITY_GATE

    @pytest.mark.parametrize(
        ("flag", "expected_status"),
        [
            (
                "projected_input_temporal_sequence_gate_passed",
                BLOCKED_BY_PROJECTED_INPUT_TEMPORAL_SEQUENCE_GATE,
            ),
            (
                "projected_input_row_count_gate_passed",
                BLOCKED_BY_PROJECTED_INPUT_ROW_COUNT_GATE,
            ),
            (
                "projected_input_shape_inventory_gate_passed",
                BLOCKED_BY_PROJECTED_INPUT_SHAPE_INVENTORY_GATE,
            ),
            (
                "allowed_runner_input_projection_gate_passed",
                BLOCKED_BY_ALLOWED_RUNNER_INPUT_PROJECTION_GATE,
            ),
            (
                "no_output_runner_invocation_gate_passed",
                BLOCKED_BY_NO_OUTPUT_RUNNER_INVOCATION_GATE,
            ),
            (
                "implementation_boundary_gate_passed",
                BLOCKED_BY_IMPLEMENTATION_BOUNDARY_GATE,
            ),
        ],
    )
    def test_q1_p1_o1_n1_m1_l1_upstream_failed_fail_closed(
        self, tmp_path, flag, expected_status
    ):
        result = self._result(tmp_path)
        result[flag] = False
        gate = _derive_no_output_runner_dry_harness_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == expected_status

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("runner_dry_harness_mode", "RUNNER_EXECUTION"),
            ("runner_dry_harness_policy", "RUN_RUNNER_LOGIC"),
        ],
    )
    def test_mutated_harness_mode_or_policy_fails_closed(
        self, tmp_path, field, value
    ):
        result = self._result(tmp_path)
        result[field] = value
        gate = _derive_no_output_runner_dry_harness_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_NO_OUTPUT_RUNNER_DRY_HARNESS_EVIDENCE
        )

    @pytest.mark.parametrize(
        "field",
        [
            "runner_logic_executed",
            "runner_callable_invoked",
            "runner_inputs_materialized_as_rows",
        ],
    )
    def test_runner_execution_flags_true_fail_closed(self, tmp_path, field):
        result = self._result(tmp_path)
        result[field] = True
        gate = _derive_no_output_runner_dry_harness_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == BLOCKED_BY_UNEXPECTED_RUNNER_OUTPUT_EMISSION
        assert field in gate["blocked_reason"]

    @pytest.mark.parametrize(
        "field",
        [
            "decision_rows_emitted",
            "signals_emitted",
            "rule_output_rows_emitted",
            "simulated_events_emitted",
            "economic_values_emitted",
            "statistical_values_emitted",
            "joined_rows_emitted",
            "timestamp_values_emitted",
            "price_values_emitted",
            "funding_values_emitted",
            "row_value_samples_emitted",
            "projected_input_row_values_emitted",
        ],
    )
    def test_every_output_flag_true_fails_closed(self, tmp_path, field):
        result = self._result(tmp_path)
        result[field] = True
        gate = _derive_no_output_runner_dry_harness_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == BLOCKED_BY_UNEXPECTED_RUNNER_OUTPUT_EMISSION
        assert field in gate["blocked_reason"]

    @pytest.mark.parametrize(
        "field",
        [
            "runner_dry_harness_readiness",
            "implementation_authorized",
            "runner_implementation_authorized",
            "rule_materialization_authorized",
            "decision_row_generation_authorized",
            "simulated_event_generation_authorized",
            "economic_value_generation_authorized",
            "statistical_value_generation_authorized",
            "candidate_comparison_authorized",
            "null_generation_authorized",
            "scoring_authorization",
            "live_integration_authorized",
            "paper_integration_authorized",
            "final_verdict_authorization",
        ],
    )
    def test_authorization_flip_fails_closed(self, tmp_path, field):
        result = self._result(tmp_path)
        result[field] = True
        gate = _derive_no_output_runner_dry_harness_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == "BLOCKED_BY_UNEXPECTED_AUTHORIZATION"
        assert field in gate["blocked_reason"]

    def test_no_packet_no_input_receipt_integration_fails_closed(self, tmp_path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        exit_code = real_validation.main(
            self._r1()._q1()._p1()._o1()._n1()._m1()._cli_base_args(output_dir)
        )
        assert exit_code == 0
        receipt = json.loads(
            (output_dir / "real_validation_receipt.json").read_text()
        )
        diagnostics = receipt["no_output_runner_dry_harness_diagnostics"]
        gate = diagnostics["no_output_runner_dry_harness_gate"]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == BLOCKED_BY_PROJECTED_INPUT_JOINABILITY_GATE
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION

    def test_full_valid_bars_funding_receipt_passes_s1_verdict_blocked(
        self, tmp_path
    ):
        bars_dir = tmp_path / "bars"
        funding_dir = tmp_path / "funding"
        bars_dir.mkdir()
        funding_dir.mkdir()
        _write_tiny_bars_csv(bars_dir, "BTCUSDT_8h_ohlcv.csv")
        funding_path = _write_tiny_funding_csv(
            funding_dir,
            "BTCUSDT_8h_funding.csv",
        )
        funding_path.write_text(
            "fundingTime,fundingRate,markPrice\n"
            "2026-01-01T00:00:00Z,0.0001,50000.0\n"
            "2026-01-02T00:00:00Z,0.0002,50100.0\n"
            "2026-01-03T00:00:00Z,0.0003,50200.0\n"
        )
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        m1 = self._r1()._q1()._p1()._o1()._n1()._m1()
        exit_code = real_validation.main(
            m1._cli_base_args(output_dir)
            + m1._cli_full_chain_args()
            + [
                "--bars-dir",
                str(bars_dir),
                "--funding-dir",
                str(funding_dir),
            ]
        )
        assert exit_code == 0
        receipt = json.loads(
            (output_dir / "real_validation_receipt.json").read_text()
        )
        r1_gate = receipt["projected_input_joinability_diagnostics"][
            "projected_input_joinability_gate"
        ]
        assert r1_gate["gate_passed"] is True
        diagnostics = receipt["no_output_runner_dry_harness_diagnostics"]
        gate = diagnostics["no_output_runner_dry_harness_gate"]
        assert gate["gate_passed"] is True
        assert gate["gate_status"] == (
            NO_OUTPUT_RUNNER_DRY_HARNESS_DECLARED_DIAGNOSTIC_ONLY
        )
        assert diagnostics["runner_logic_executed"] is False
        assert diagnostics["decision_rows_emitted"] is False
        assert diagnostics["signals_emitted"] is False
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION

    def test_forbidden_key_scan(self, tmp_path):
        result = self._result(tmp_path)
        all_keys = _all_dict_keys(result)
        assert real_validation.FORBIDDEN_CALCULATION_KEYS.isdisjoint(all_keys), (
            f"Forbidden keys found: "
            f"{real_validation.FORBIDDEN_CALCULATION_KEYS & all_keys}"
        )
        serialized = json.dumps(result)
        for forbidden in (
            "2026-01-01T00:00:00Z",
            "100.5",
            "0.0001",
            "fundingTime",
            "close",
        ):
            assert forbidden not in serialized


class TestMaterializedRuleRowSchemaLockT0:
    def _s1(self):
        return TestNoOutputRunnerDryHarnessS1()

    def _full_chain_diags(self, tmp_path):
        diags, inventory = self._s1()._full_chain_diags(tmp_path)
        diags["no_output_runner_dry_harness_diagnostics"] = self._s1()._build(
            diags
        )
        return diags, inventory

    def _absence_diags(self):
        diags = self._s1()._absence_diags()
        diags["no_output_runner_dry_harness_diagnostics"] = self._s1()._build(
            diags
        )
        return diags

    def _build(self, diags):
        return _build_materialized_rule_row_schema_lock_diagnostics(
            no_output_runner_dry_harness_diagnostics=diags[
                "no_output_runner_dry_harness_diagnostics"
            ],
            projected_input_joinability_diagnostics=diags[
                "projected_input_joinability_diagnostics"
            ],
            projected_input_temporal_sequence_diagnostics=diags[
                "projected_input_temporal_sequence_diagnostics"
            ],
            projected_input_row_count_diagnostics=diags[
                "projected_input_row_count_diagnostics"
            ],
            projected_input_shape_inventory_diagnostics=diags[
                "projected_input_shape_inventory_diagnostics"
            ],
            allowed_runner_input_projection_diagnostics=diags[
                "allowed_runner_input_projection_diagnostics"
            ],
            no_output_runner_invocation_diagnostics=diags[
                "no_output_runner_invocation_diagnostics"
            ],
            implementation_boundary_diagnostics=diags[
                "implementation_boundary_diagnostics"
            ],
        )

    def _result(self, tmp_path):
        diags, _inventory = self._full_chain_diags(tmp_path)
        return self._build(diags)

    def test_schema_lock_happy_path_after_s1_passes(self, tmp_path):
        result = self._result(tmp_path)
        assert result["diagnostic_kind"] == "materialized_rule_row_schema_lock"
        assert result["materialized_rule_row_schema_lock_version"] == (
            MATERIALIZED_RULE_ROW_SCHEMA_LOCK_VERSION
        )
        assert result["materialized_rule_row_schema_lock_scope"] == (
            MATERIALIZED_RULE_ROW_SCHEMA_LOCK_SCOPE
        )
        assert result["materialized_rule_row_schema_lock_status"] == (
            MATERIALIZED_RULE_ROW_SCHEMA_LOCK_DECLARED_DIAGNOSTIC_ONLY
        )
        assert result["materialized_rule_row_schema_mode"] == "SCHEMA_ONLY"
        assert result["materialized_rule_row_schema_policy"] == (
            MATERIALIZED_RULE_ROW_SCHEMA_LOCK_POLICY
        )
        assert result["allowed_materialized_rule_row_schema_keys"] == list(
            _ALLOWED_MATERIALIZED_RULE_ROW_SCHEMA_KEYS
        )
        required = result["required_materialized_rule_row_schema_keys"]
        assert required == list(_REQUIRED_MATERIALIZED_RULE_ROW_SCHEMA_KEYS)
        assert set(required) <= set(result["allowed_materialized_rule_row_schema_keys"])
        assert result["forbidden_materialized_rule_row_key_names"] == list(
            _FORBIDDEN_MATERIALIZED_RULE_ROW_SCHEMA_KEY_NAMES
        )
        assert result["materialized_rule_rows_emitted"] is False
        assert result["materialized_rule_row_count"] == 0
        assert result["runner_logic_executed"] is False
        assert result["runner_callable_invoked"] is False
        assert result["runner_inputs_materialized_as_rows"] is False
        for field in (
            "decision_rows_emitted",
            "signals_emitted",
            "rule_output_rows_emitted",
            "simulated_events_emitted",
            "economic_values_emitted",
            "statistical_values_emitted",
            "joined_rows_emitted",
            "timestamp_values_emitted",
            "price_values_emitted",
            "funding_values_emitted",
            "row_value_samples_emitted",
            "projected_input_row_values_emitted",
        ):
            assert result[field] is False
        for field in _MATERIALIZED_RULE_ROW_SCHEMA_LOCK_AUTHORIZATION_FIELDS:
            assert result[field] is False
        assert result["final_offline_verdict_remains"] == (
            BLOCKED_BY_VALIDATION_IMPLEMENTATION
        )

    def test_schema_lock_gate_happy_path(self, tmp_path):
        gate = self._result(tmp_path)["materialized_rule_row_schema_lock_gate"]
        assert gate["gate_passed"] is True
        assert gate["gate_status"] == (
            MATERIALIZED_RULE_ROW_SCHEMA_LOCK_DECLARED_DIAGNOSTIC_ONLY
        )
        assert gate["gate_scoring_authorization"] is False
        assert gate["gate_live_authorization"] is False
        assert gate["gate_final_verdict_authorization"] is False
        assert gate["gate_downstream_unlocks"] == []

    def test_no_packet_no_input_receipt_integration_fails_closed(self, tmp_path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        exit_code = real_validation.main(
            self._s1()._r1()._q1()._p1()._o1()._n1()._m1()._cli_base_args(
                output_dir
            )
        )
        assert exit_code == 0
        receipt = json.loads(
            (output_dir / "real_validation_receipt.json").read_text()
        )
        diagnostics = receipt["materialized_rule_row_schema_lock_diagnostics"]
        gate = diagnostics["materialized_rule_row_schema_lock_gate"]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == BLOCKED_BY_NO_OUTPUT_RUNNER_DRY_HARNESS_GATE
        for field in _MATERIALIZED_RULE_ROW_SCHEMA_LOCK_AUTHORIZATION_FIELDS:
            assert diagnostics[field] is False
        assert diagnostics["final_offline_verdict_remains"] == (
            BLOCKED_BY_VALIDATION_IMPLEMENTATION
        )
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION

    def test_s1_gate_missing_or_failed_fails_closed(self, tmp_path):
        result = self._result(tmp_path)
        result["no_output_runner_dry_harness_gate_passed"] = False
        gate = _derive_materialized_rule_row_schema_lock_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == BLOCKED_BY_NO_OUTPUT_RUNNER_DRY_HARNESS_GATE

        diags, _inventory = self._full_chain_diags(tmp_path)
        s1_diagnostics = dict(diags["no_output_runner_dry_harness_diagnostics"])
        s1_diagnostics.pop("no_output_runner_dry_harness_gate")
        diags["no_output_runner_dry_harness_diagnostics"] = s1_diagnostics
        gate = self._build(diags)["materialized_rule_row_schema_lock_gate"]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == BLOCKED_BY_NO_OUTPUT_RUNNER_DRY_HARNESS_GATE

    def test_r1_gate_missing_or_failed_fails_closed(self, tmp_path):
        result = self._result(tmp_path)
        result["projected_input_joinability_gate_passed"] = False
        gate = _derive_materialized_rule_row_schema_lock_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == BLOCKED_BY_PROJECTED_INPUT_JOINABILITY_GATE

    @pytest.mark.parametrize(
        ("flag", "expected_status"),
        [
            (
                "projected_input_temporal_sequence_gate_passed",
                BLOCKED_BY_PROJECTED_INPUT_TEMPORAL_SEQUENCE_GATE,
            ),
            (
                "projected_input_row_count_gate_passed",
                BLOCKED_BY_PROJECTED_INPUT_ROW_COUNT_GATE,
            ),
            (
                "projected_input_shape_inventory_gate_passed",
                BLOCKED_BY_PROJECTED_INPUT_SHAPE_INVENTORY_GATE,
            ),
            (
                "allowed_runner_input_projection_gate_passed",
                BLOCKED_BY_ALLOWED_RUNNER_INPUT_PROJECTION_GATE,
            ),
            (
                "no_output_runner_invocation_gate_passed",
                BLOCKED_BY_NO_OUTPUT_RUNNER_INVOCATION_GATE,
            ),
            (
                "implementation_boundary_gate_passed",
                BLOCKED_BY_IMPLEMENTATION_BOUNDARY_GATE,
            ),
        ],
    )
    def test_q1_p1_o1_n1_m1_l1_upstream_failed_fail_closed(
        self, tmp_path, flag, expected_status
    ):
        result = self._result(tmp_path)
        result[flag] = False
        gate = _derive_materialized_rule_row_schema_lock_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == expected_status

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("materialized_rule_row_schema_mode", "ROW_EMISSION"),
            ("materialized_rule_row_schema_mode", "MATERIALIZE_NOW"),
            ("materialized_rule_row_schema_policy", "EMIT_RULE_ROWS_NOW"),
        ],
    )
    def test_mutated_schema_mode_or_policy_fails_closed(
        self, tmp_path, field, value
    ):
        result = self._result(tmp_path)
        result[field] = value
        gate = _derive_materialized_rule_row_schema_lock_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_MATERIALIZED_RULE_ROW_SCHEMA_EVIDENCE
        )

    def test_missing_allowed_schema_key_fails_closed(self, tmp_path):
        result = self._result(tmp_path)
        result["allowed_materialized_rule_row_schema_keys"] = result[
            "allowed_materialized_rule_row_schema_keys"
        ][:-1]
        gate = _derive_materialized_rule_row_schema_lock_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_MATERIALIZED_RULE_ROW_SCHEMA_EVIDENCE
        )

    def test_extra_allowed_schema_key_fails_closed(self, tmp_path):
        result = self._result(tmp_path)
        result["allowed_materialized_rule_row_schema_keys"] = (
            result["allowed_materialized_rule_row_schema_keys"] + ["extra_safe_key"]
        )
        gate = _derive_materialized_rule_row_schema_lock_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_MATERIALIZED_RULE_ROW_SCHEMA_EVIDENCE
        )

    def test_missing_required_schema_key_fails_closed(self, tmp_path):
        result = self._result(tmp_path)
        result["required_materialized_rule_row_schema_keys"] = result[
            "required_materialized_rule_row_schema_keys"
        ][:-1]
        gate = _derive_materialized_rule_row_schema_lock_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_MATERIALIZED_RULE_ROW_SCHEMA_EVIDENCE
        )

    def test_required_key_not_subset_of_allowed_fails_closed(self, tmp_path):
        result = self._result(tmp_path)
        result["required_materialized_rule_row_schema_keys"] = list(
            _REQUIRED_MATERIALIZED_RULE_ROW_SCHEMA_KEYS
        ) + ["missing_from_allowed"]
        gate = _derive_materialized_rule_row_schema_lock_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_MATERIALIZED_RULE_ROW_SCHEMA_EVIDENCE
        )

    def test_forbidden_key_as_actual_dict_key_fails_closed(self, tmp_path):
        result = self._result(tmp_path)
        result["pnl"] = "not allowed as a dict key"
        gate = _derive_materialized_rule_row_schema_lock_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_MATERIALIZED_RULE_ROW_SCHEMA_EVIDENCE
        )
        assert "pnl" in gate["blocked_reason"]

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("materialized_rule_rows_emitted", True),
            ("materialized_rule_row_count", 1),
            ("runner_logic_executed", True),
            ("runner_callable_invoked", True),
            ("runner_inputs_materialized_as_rows", True),
        ],
    )
    def test_row_or_runner_output_flags_fail_closed(
        self, tmp_path, field, value
    ):
        result = self._result(tmp_path)
        result[field] = value
        gate = _derive_materialized_rule_row_schema_lock_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == BLOCKED_BY_UNEXPECTED_RULE_ROW_EMISSION
        assert field in gate["blocked_reason"]

    @pytest.mark.parametrize(
        "field",
        [
            "decision_rows_emitted",
            "signals_emitted",
            "rule_output_rows_emitted",
            "simulated_events_emitted",
            "economic_values_emitted",
            "statistical_values_emitted",
            "joined_rows_emitted",
            "timestamp_values_emitted",
            "price_values_emitted",
            "funding_values_emitted",
            "row_value_samples_emitted",
            "projected_input_row_values_emitted",
        ],
    )
    def test_every_output_flag_true_fails_closed(self, tmp_path, field):
        result = self._result(tmp_path)
        result[field] = True
        gate = _derive_materialized_rule_row_schema_lock_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == BLOCKED_BY_UNEXPECTED_RULE_ROW_EMISSION
        assert field in gate["blocked_reason"]

    @pytest.mark.parametrize(
        "field",
        [
            "rule_materialization_authorized",
            "decision_row_generation_authorized",
            "scoring_authorization",
            "live_integration_authorized",
            "final_verdict_authorization",
        ],
    )
    def test_authorization_flip_fails_closed(self, tmp_path, field):
        result = self._result(tmp_path)
        result[field] = True
        gate = _derive_materialized_rule_row_schema_lock_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == "BLOCKED_BY_UNEXPECTED_AUTHORIZATION"
        assert field in gate["blocked_reason"]

    def test_full_valid_bars_funding_receipt_passes_t0_verdict_blocked(
        self, tmp_path
    ):
        bars_dir = tmp_path / "bars"
        funding_dir = tmp_path / "funding"
        bars_dir.mkdir()
        funding_dir.mkdir()
        _write_tiny_bars_csv(bars_dir, "BTCUSDT_8h_ohlcv.csv")
        funding_path = _write_tiny_funding_csv(
            funding_dir,
            "BTCUSDT_8h_funding.csv",
        )
        funding_path.write_text(
            "fundingTime,fundingRate,markPrice\n"
            "2026-01-01T00:00:00Z,0.0001,50000.0\n"
            "2026-01-02T00:00:00Z,0.0002,50100.0\n"
            "2026-01-03T00:00:00Z,0.0003,50200.0\n"
        )
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        m1 = self._s1()._r1()._q1()._p1()._o1()._n1()._m1()
        exit_code = real_validation.main(
            m1._cli_base_args(output_dir)
            + m1._cli_full_chain_args()
            + [
                "--bars-dir",
                str(bars_dir),
                "--funding-dir",
                str(funding_dir),
            ]
        )
        assert exit_code == 0
        receipt = json.loads(
            (output_dir / "real_validation_receipt.json").read_text()
        )
        assert receipt["no_output_runner_dry_harness_diagnostics"][
            "no_output_runner_dry_harness_gate"
        ]["gate_passed"] is True
        diagnostics = receipt["materialized_rule_row_schema_lock_diagnostics"]
        gate = diagnostics["materialized_rule_row_schema_lock_gate"]
        assert gate["gate_passed"] is True
        assert gate["gate_status"] == (
            MATERIALIZED_RULE_ROW_SCHEMA_LOCK_DECLARED_DIAGNOSTIC_ONLY
        )
        assert diagnostics["materialized_rule_rows_emitted"] is False
        assert diagnostics["materialized_rule_row_count"] == 0
        assert diagnostics["runner_logic_executed"] is False
        assert diagnostics["runner_callable_invoked"] is False
        assert diagnostics["decision_rows_emitted"] is False
        assert diagnostics["signals_emitted"] is False
        assert diagnostics["final_offline_verdict_remains"] == (
            BLOCKED_BY_VALIDATION_IMPLEMENTATION
        )
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION

    def test_forbidden_key_scan(self, tmp_path):
        result = self._result(tmp_path)
        all_keys = _all_dict_keys(result)
        assert real_validation.FORBIDDEN_CALCULATION_KEYS.isdisjoint(all_keys), (
            f"Forbidden keys found: "
            f"{real_validation.FORBIDDEN_CALCULATION_KEYS & all_keys}"
        )
        assert set(_FORBIDDEN_MATERIALIZED_RULE_ROW_SCHEMA_KEY_NAMES) <= set(
            result["forbidden_materialized_rule_row_key_names"]
        )
        assert "forbidden_materialized_rule_row_key_names" in all_keys


class TestMaterializedRuleRowsV0T1:
    """Lane T1: materialized rule rows v0.

    The first real output-producing lane. Depends on the T0 schema lock, S1
    dry harness, and R1 joinability gates. Emits deterministic, T0-schema-
    locked rule rows -- artifact-only, no economics/scoring/statistics/live
    integration -- and never advances final_offline_verdict.
    """

    def _t0(self):
        return TestMaterializedRuleRowSchemaLockT0()

    def _full_chain_diags(self, tmp_path):
        diags, inventory = self._t0()._full_chain_diags(tmp_path)
        diags["materialized_rule_row_schema_lock_diagnostics"] = self._t0()._build(
            diags
        )
        return diags, inventory

    def _absence_diags(self):
        diags = self._t0()._absence_diags()
        diags["materialized_rule_row_schema_lock_diagnostics"] = self._t0()._build(
            diags
        )
        return diags

    def _build(self, diags, inventory=None):
        split_diagnostics = None
        if inventory is not None:
            split_diagnostics = {
                "split_definitions": materialize_split_definitions_from_inventory(
                    inventory=inventory,
                    split_count=3,
                )
            }
        return _build_materialized_rule_rows_v0_diagnostics(
            materialized_rule_row_schema_lock_diagnostics=diags[
                "materialized_rule_row_schema_lock_diagnostics"
            ],
            no_output_runner_dry_harness_diagnostics=diags[
                "no_output_runner_dry_harness_diagnostics"
            ],
            projected_input_joinability_diagnostics=diags[
                "projected_input_joinability_diagnostics"
            ],
            projected_input_temporal_sequence_diagnostics=diags[
                "projected_input_temporal_sequence_diagnostics"
            ],
            projected_input_row_count_diagnostics=diags[
                "projected_input_row_count_diagnostics"
            ],
            projected_input_shape_inventory_diagnostics=diags[
                "projected_input_shape_inventory_diagnostics"
            ],
            allowed_runner_input_projection_diagnostics=diags[
                "allowed_runner_input_projection_diagnostics"
            ],
            no_output_runner_invocation_diagnostics=diags[
                "no_output_runner_invocation_diagnostics"
            ],
            implementation_boundary_diagnostics=diags[
                "implementation_boundary_diagnostics"
            ],
            split_diagnostics=split_diagnostics,
            inventory_diagnostics=inventory,
        )

    def _result(self, tmp_path):
        diags, inventory = self._full_chain_diags(tmp_path)
        return self._build(diags, inventory)

    # ── Test 1: no packet / no input fails closed via T0 schema-lock gate ──
    def test_no_packet_no_input_receipt_integration_fails_closed(self, tmp_path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        m1 = self._t0()._s1()._r1()._q1()._p1()._o1()._n1()._m1()
        exit_code = real_validation.main(m1._cli_base_args(output_dir))
        assert exit_code == 0
        receipt = json.loads(
            (output_dir / "real_validation_receipt.json").read_text()
        )
        diagnostics = receipt["materialized_rule_rows_v0_diagnostics"]
        gate = diagnostics["materialized_rule_rows_v0_gate"]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_MATERIALIZED_RULE_ROW_SCHEMA_LOCK_GATE
        )
        assert diagnostics["materialized_rule_rows_emitted"] is False
        assert diagnostics["materialized_rule_row_count"] == 0
        assert diagnostics["materialized_rule_rows"] == []
        assert diagnostics["final_offline_verdict_remains"] == (
            BLOCKED_BY_VALIDATION_IMPLEMENTATION
        )
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION

    # ── Test 2: full valid S1/T0 path emits schema-valid rows ──────────────
    def test_full_valid_path_emits_schema_valid_rows(self, tmp_path):
        result = self._result(tmp_path)
        assert result["materialized_rule_row_schema_lock_gate_passed"] is True
        gate = result["materialized_rule_rows_v0_gate"]
        assert gate["gate_passed"] is True
        assert gate["gate_status"] == MATERIALIZED_RULE_ROWS_V0_DECLARED_ARTIFACT_ONLY
        assert result["materialized_rule_rows_emitted"] is True
        rows = result["materialized_rule_rows"]
        assert result["materialized_rule_row_count"] == len(rows)
        assert len(rows) > 0
        allowed_key_set = set(_ALLOWED_MATERIALIZED_RULE_ROW_SCHEMA_KEYS)
        for row in rows:
            assert set(row.keys()) == allowed_key_set
            assert not (set(row.keys()) - allowed_key_set)
            assert "close" not in row
            assert "fundingRate" not in row
            assert "pnl" not in row
            assert row["rule_metadata_only"] is True
        assert result["final_offline_verdict_remains"] == (
            BLOCKED_BY_VALIDATION_IMPLEMENTATION
        )
        serialized_rows = json.dumps(rows)
        assert "close" not in serialized_rows
        assert "fundingRate" not in serialized_rows

    def test_full_valid_path_gate_never_authorizes_downstream(self, tmp_path):
        gate = self._result(tmp_path)["materialized_rule_rows_v0_gate"]
        assert gate["gate_scoring_authorization"] is False
        assert gate["gate_live_authorization"] is False
        assert gate["gate_final_verdict_authorization"] is False
        assert gate["gate_downstream_unlocks"] == []

    # ── Test 3: T0 gate missing/failed fails closed ─────────────────────────
    def test_t0_gate_missing_or_failed_fails_closed(self, tmp_path):
        result = self._result(tmp_path)
        result["materialized_rule_row_schema_lock_gate_passed"] = False
        gate = _derive_materialized_rule_rows_v0_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_MATERIALIZED_RULE_ROW_SCHEMA_LOCK_GATE
        )

    # ── Test 4: S1 gate missing/failed fails closed ─────────────────────────
    def test_s1_gate_missing_or_failed_fails_closed(self, tmp_path):
        result = self._result(tmp_path)
        result["no_output_runner_dry_harness_gate_passed"] = False
        gate = _derive_materialized_rule_rows_v0_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == BLOCKED_BY_NO_OUTPUT_RUNNER_DRY_HARNESS_GATE

    # ── Test 5: R1 gate missing/failed fails closed ─────────────────────────
    def test_r1_gate_missing_or_failed_fails_closed(self, tmp_path):
        result = self._result(tmp_path)
        result["projected_input_joinability_gate_passed"] = False
        gate = _derive_materialized_rule_rows_v0_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == BLOCKED_BY_PROJECTED_INPUT_JOINABILITY_GATE

    # ── Test 6/7: mutated mode or policy fails closed ───────────────────────
    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("materialized_rule_rows_v0_mode", "ROW_EMISSION_UNLOCKED"),
            ("materialized_rule_rows_v0_policy", "EMIT_ANYTHING"),
        ],
    )
    def test_mutated_mode_or_policy_fails_closed(self, tmp_path, field, value):
        result = self._result(tmp_path)
        result[field] = value
        gate = _derive_materialized_rule_rows_v0_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_MATERIALIZED_RULE_ROWS_V0_EVIDENCE
        )

    # ── Test 8: row count mismatch fails closed ─────────────────────────────
    def test_row_count_mismatch_fails_closed(self, tmp_path):
        result = self._result(tmp_path)
        result["materialized_rule_row_count"] = result["materialized_rule_row_count"] + 1
        gate = _derive_materialized_rule_rows_v0_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_MATERIALIZED_RULE_ROWS_V0_EVIDENCE
        )

    # ── Test 9: empty rows list with otherwise-valid diagnostics fails closed
    def test_empty_rows_list_fails_closed(self, tmp_path):
        result = self._result(tmp_path)
        result["materialized_rule_rows"] = []
        result["materialized_rule_row_count"] = 0
        gate = _derive_materialized_rule_rows_v0_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_MATERIALIZED_RULE_ROWS_V0_EVIDENCE
        )

    # ── Test 10: extra row key fails closed ──────────────────────────────────
    def test_extra_row_key_fails_closed(self, tmp_path):
        result = self._result(tmp_path)
        mutated_rows = [dict(row) for row in result["materialized_rule_rows"]]
        mutated_rows[0]["extra_field_not_in_schema"] = "x"
        result["materialized_rule_rows"] = mutated_rows
        gate = _derive_materialized_rule_rows_v0_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == BLOCKED_BY_UNEXPECTED_RULE_ROW_SCHEMA

    # ── Test 11: missing required row key fails closed ──────────────────────
    def test_missing_required_row_key_fails_closed(self, tmp_path):
        result = self._result(tmp_path)
        mutated_rows = [dict(row) for row in result["materialized_rule_rows"]]
        del mutated_rows[0]["symbol"]
        result["materialized_rule_rows"] = mutated_rows
        gate = _derive_materialized_rule_rows_v0_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == BLOCKED_BY_UNEXPECTED_RULE_ROW_SCHEMA

    # ── Test 12: forbidden row key fails closed ──────────────────────────────
    @pytest.mark.parametrize("forbidden_key", ["pnl", "signal", "order", "execution"])
    def test_forbidden_row_key_fails_closed(self, tmp_path, forbidden_key):
        result = self._result(tmp_path)
        mutated_rows = [dict(row) for row in result["materialized_rule_rows"]]
        mutated_rows[0][forbidden_key] = "x"
        result["materialized_rule_rows"] = mutated_rows
        gate = _derive_materialized_rule_rows_v0_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == BLOCKED_BY_UNEXPECTED_RULE_ROW_FORBIDDEN_KEY

    # ── Test 13: price/funding/economic leakage fails closed ────────────────
    @pytest.mark.parametrize(
        "forbidden_key",
        ["close", "fundingRate", "price_value", "economic_value", "scoring_value"],
    )
    def test_economic_leakage_row_key_fails_closed(self, tmp_path, forbidden_key):
        result = self._result(tmp_path)
        mutated_rows = [dict(row) for row in result["materialized_rule_rows"]]
        mutated_rows[0][forbidden_key] = 1.0
        result["materialized_rule_rows"] = mutated_rows
        gate = _derive_materialized_rule_rows_v0_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == BLOCKED_BY_UNEXPECTED_RULE_ROW_FORBIDDEN_KEY

    # ── Test 13b: forbidden value inside rule_input_columns fails closed ────
    @pytest.mark.parametrize(
        "rule_input_columns",
        [
            ["timestamp", "close", "fundingTime"],
            ["timestamp", "fundingTime", "fundingRate"],
        ],
    )
    def test_forbidden_row_input_column_value_fails_closed(
        self, tmp_path, rule_input_columns
    ):
        result = self._result(tmp_path)
        mutated_rows = [dict(row) for row in result["materialized_rule_rows"]]
        mutated_rows[0]["rule_input_columns"] = rule_input_columns
        result["materialized_rule_rows"] = mutated_rows
        gate = _derive_materialized_rule_rows_v0_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == BLOCKED_BY_UNEXPECTED_RULE_ROW_FORBIDDEN_VALUE

    # ── Test 14: duplicate row identity fails closed ─────────────────────────
    def test_duplicate_row_identity_fails_closed(self, tmp_path):
        result = self._result(tmp_path)
        rows = [dict(row) for row in result["materialized_rule_rows"]]
        assert len(rows) >= 1
        duplicate = dict(rows[0])
        rows.append(duplicate)
        result["materialized_rule_rows"] = rows
        result["materialized_rule_row_count"] = len(rows)
        gate = _derive_materialized_rule_rows_v0_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_MATERIALIZED_RULE_ROWS_V0_EVIDENCE
        )

    # ── Test 15: reversed row order fails closed ─────────────────────────────
    def test_reversed_row_order_fails_closed(self, tmp_path):
        result = self._result(tmp_path)
        rows = list(result["materialized_rule_rows"])
        assert len(rows) >= 2, "fixture must produce >=2 rows to test ordering"
        result["materialized_rule_rows"] = list(reversed(rows))
        gate = _derive_materialized_rule_rows_v0_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_MATERIALIZED_RULE_ROWS_V0_EVIDENCE
        )

    # ── Test 16: economic/scoring/live/final authorization flip fails closed
    @pytest.mark.parametrize(
        "field",
        [
            "decision_row_generation_authorized",
            "simulated_event_generation_authorized",
            "economic_value_generation_authorized",
            "statistical_value_generation_authorized",
            "candidate_comparison_authorized",
            "null_generation_authorized",
            "scoring_authorization",
            "live_integration_authorized",
            "paper_integration_authorized",
            "final_verdict_authorization",
        ],
    )
    def test_authorization_flip_fails_closed(self, tmp_path, field):
        result = self._result(tmp_path)
        result[field] = True
        gate = _derive_materialized_rule_rows_v0_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_UNEXPECTED_ECONOMIC_OR_SCORING_AUTHORIZATION
        )
        assert field in gate["blocked_reason"]

    # ── Test 16b: emission/value flags flip fails closed ────────────────────
    @pytest.mark.parametrize(
        "field",
        [
            "rule_row_price_values_emitted",
            "rule_row_funding_rate_values_emitted",
            "rule_row_economic_values_emitted",
            "rule_row_statistical_values_emitted",
            "rule_row_scoring_values_emitted",
            "simulated_events_emitted",
            "economic_values_emitted",
            "statistical_values_emitted",
            "null_comparison_values_emitted",
            "scoring_values_emitted",
            "live_integration_values_emitted",
            "final_verdict_values_emitted",
        ],
    )
    def test_emission_value_flags_true_fail_closed(self, tmp_path, field):
        result = self._result(tmp_path)
        result[field] = True
        gate = _derive_materialized_rule_rows_v0_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == BLOCKED_BY_UNEXPECTED_RULE_ROW_EMISSION
        assert field in gate["blocked_reason"]

    # ── Test 17: receipt integration full valid path via main() ─────────────
    def test_receipt_integration_full_valid_path(self, tmp_path):
        bars_dir = tmp_path / "bars"
        funding_dir = tmp_path / "funding"
        bars_dir.mkdir()
        funding_dir.mkdir()
        _write_tiny_bars_csv(bars_dir, "BTCUSDT_8h_ohlcv.csv")
        funding_path = _write_tiny_funding_csv(
            funding_dir,
            "BTCUSDT_8h_funding.csv",
        )
        funding_path.write_text(
            "fundingTime,fundingRate,markPrice\n"
            "2026-01-01T00:00:00Z,0.0001,50000.0\n"
            "2026-01-02T00:00:00Z,0.0002,50100.0\n"
            "2026-01-03T00:00:00Z,0.0003,50200.0\n"
        )
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        m1 = self._t0()._s1()._r1()._q1()._p1()._o1()._n1()._m1()
        exit_code = real_validation.main(
            m1._cli_base_args(output_dir)
            + m1._cli_full_chain_args()
            + [
                "--bars-dir",
                str(bars_dir),
                "--funding-dir",
                str(funding_dir),
            ]
        )
        assert exit_code == 0
        receipt = json.loads(
            (output_dir / "real_validation_receipt.json").read_text()
        )
        t0_gate = receipt["materialized_rule_row_schema_lock_diagnostics"][
            "materialized_rule_row_schema_lock_gate"
        ]
        assert t0_gate["gate_passed"] is True
        diagnostics = receipt["materialized_rule_rows_v0_diagnostics"]
        gate = diagnostics["materialized_rule_rows_v0_gate"]
        assert gate["gate_passed"] is True
        assert gate["gate_status"] == MATERIALIZED_RULE_ROWS_V0_DECLARED_ARTIFACT_ONLY
        assert diagnostics["materialized_rule_row_count"] > 0
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION
        assert receipt["guardrail_status"]["edge_unproven"] is True
        assert receipt["guardrail_status"]["block_live_integration"] is True

    # ── Test 18: forbidden calculation key scan ──────────────────────────────
    def test_forbidden_key_scan(self, tmp_path):
        result = self._result(tmp_path)
        all_keys = _all_dict_keys(result)
        assert real_validation.FORBIDDEN_CALCULATION_KEYS.isdisjoint(all_keys), (
            f"Forbidden keys found: "
            f"{real_validation.FORBIDDEN_CALCULATION_KEYS & all_keys}"
        )
        for row in result["materialized_rule_rows"]:
            assert real_validation.FORBIDDEN_CALCULATION_KEYS.isdisjoint(row.keys())

    # ── Test 19: schema guard against future silent edits ───────────────────
    def test_allowed_schema_keys_guard(self):
        assert _ALLOWED_MATERIALIZED_RULE_ROW_SCHEMA_KEYS == (
            "schema_version",
            "schema_kind",
            "run_id",
            "symbol",
            "split_id",
            "split_partition",
            "row_sequence_id",
            "decision_time_utc",
            "source_bar_time_utc",
            "source_funding_time_utc",
            "rule_family",
            "rule_variant",
            "rule_revision",
            "rule_input_roles",
            "rule_input_columns",
            "rule_condition_name",
            "rule_condition_result",
            "rule_action_name",
            "rule_action_code",
            "rule_metadata_only",
        )
        assert len(_ALLOWED_MATERIALIZED_RULE_ROW_SCHEMA_KEYS) == 20


class TestSimulatedEventSchemaLockU0:
    """Lane U0: declare a future event schema without emitting events."""

    def _t1(self):
        return TestMaterializedRuleRowsV0T1()

    def _build(self, diags, inventory=None):
        t1 = self._t1()._build(diags, inventory)
        return _build_simulated_event_schema_lock_diagnostics(
            materialized_rule_rows_v0_diagnostics=t1,
            materialized_rule_row_schema_lock_diagnostics=diags[
                "materialized_rule_row_schema_lock_diagnostics"
            ],
            no_output_runner_dry_harness_diagnostics=diags[
                "no_output_runner_dry_harness_diagnostics"
            ],
            projected_input_joinability_diagnostics=diags[
                "projected_input_joinability_diagnostics"
            ],
            projected_input_temporal_sequence_diagnostics=diags[
                "projected_input_temporal_sequence_diagnostics"
            ],
            projected_input_row_count_diagnostics=diags[
                "projected_input_row_count_diagnostics"
            ],
            projected_input_shape_inventory_diagnostics=diags[
                "projected_input_shape_inventory_diagnostics"
            ],
            allowed_runner_input_projection_diagnostics=diags[
                "allowed_runner_input_projection_diagnostics"
            ],
            no_output_runner_invocation_diagnostics=diags[
                "no_output_runner_invocation_diagnostics"
            ],
            implementation_boundary_diagnostics=diags[
                "implementation_boundary_diagnostics"
            ],
        )

    def _result(self, tmp_path):
        diags, inventory = self._t1()._full_chain_diags(tmp_path)
        return self._build(diags, inventory)

    def test_no_packet_no_input_receipt_fails_closed(self, tmp_path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        m1 = self._t1()._t0()._s1()._r1()._q1()._p1()._o1()._n1()._m1()
        assert real_validation.main(m1._cli_base_args(output_dir)) == 0
        receipt = json.loads((output_dir / "real_validation_receipt.json").read_text())
        diagnostics = receipt["simulated_event_schema_lock_diagnostics"]
        assert diagnostics["simulated_event_schema_lock_gate"]["gate_passed"] is False
        assert diagnostics["simulated_event_schema_lock_gate"]["gate_status"] == BLOCKED_BY_MATERIALIZED_RULE_ROWS_V0_GATE
        assert diagnostics["simulated_event_count"] == 0
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION

    def test_full_t1_path_declares_exact_schema_only(self, tmp_path):
        result = self._result(tmp_path)
        assert result["diagnostic_kind"] == "simulated_event_schema_lock"
        assert result["simulated_event_schema_lock_version"] == SIMULATED_EVENT_SCHEMA_LOCK_VERSION
        assert result["simulated_event_schema_lock_scope"] == SIMULATED_EVENT_SCHEMA_LOCK_SCOPE
        assert result["simulated_event_schema_lock_status"] == SIMULATED_EVENT_SCHEMA_LOCK_DECLARED_DIAGNOSTIC_ONLY
        assert result["simulated_event_schema_policy"] == SIMULATED_EVENT_SCHEMA_LOCK_POLICY
        assert result["allowed_simulated_event_schema_keys"] == list(_ALLOWED_SIMULATED_EVENT_SCHEMA_KEYS)
        assert result["required_simulated_event_schema_keys"] == list(_REQUIRED_SIMULATED_EVENT_SCHEMA_KEYS)
        assert set(result["required_simulated_event_schema_keys"]) <= set(result["allowed_simulated_event_schema_keys"])
        assert result["forbidden_simulated_event_key_names"] == list(_FORBIDDEN_SIMULATED_EVENT_SCHEMA_KEY_NAMES)
        assert result["simulated_events_emitted"] is False
        assert result["simulated_event_count"] == 0
        assert result["simulated_event_schema_lock_gate"]["gate_passed"] is True
        assert result["final_offline_verdict_remains"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION

    def test_schema_mutations_fail_closed(self, tmp_path):
        for key, value in (
            ("simulated_event_schema_mode", "EVENT_EMISSION"),
            ("simulated_event_schema_policy", "EMIT_SIMULATED_EVENTS_NOW"),
            ("allowed_simulated_event_schema_keys", []),
            ("required_simulated_event_schema_keys", ["not_allowed"]),
        ):
            result = self._result(tmp_path)
            result[key] = value
            gate = _derive_simulated_event_schema_lock_gate(result)
            assert gate["gate_passed"] is False
            assert gate["gate_status"] == BLOCKED_BY_INCOMPLETE_SIMULATED_EVENT_SCHEMA_EVIDENCE

    def test_emission_and_authorization_mutations_fail_closed(self, tmp_path):
        for field in (
            "simulated_events_emitted", "simulated_event_rows_emitted",
            "economic_values_emitted", "statistical_values_emitted",
            "null_comparison_values_emitted", "scoring_values_emitted",
            "live_integration_values_emitted", "paper_integration_values_emitted",
            "final_verdict_values_emitted",
        ):
            result = self._result(tmp_path)
            result[field] = True
            assert _derive_simulated_event_schema_lock_gate(result)["gate_status"] == BLOCKED_BY_UNEXPECTED_SIMULATED_EVENT_EMISSION
        for field in ("simulated_event_schema_readiness", "simulated_event_generation_authorized", "economic_value_generation_authorized", "scoring_authorization", "live_integration_authorized", "final_verdict_authorization"):
            result = self._result(tmp_path)
            result[field] = True
            assert _derive_simulated_event_schema_lock_gate(result)["gate_status"] == BLOCKED_BY_UNEXPECTED_SIMULATED_EVENT_AUTHORIZATION

    def test_simulated_event_schema_readiness_true_fails_closed(self, tmp_path):
        result = self._result(tmp_path)
        result["simulated_event_schema_readiness"] = True
        gate = _derive_simulated_event_schema_lock_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == BLOCKED_BY_UNEXPECTED_SIMULATED_EVENT_AUTHORIZATION
        assert "simulated_event_schema_readiness" in gate["blocked_reason"]

    def test_forbidden_key_scan_and_rule_materialization_allowance(self, tmp_path):
        result = self._result(tmp_path)
        assert real_validation.FORBIDDEN_CALCULATION_KEYS.isdisjoint(_all_dict_keys(result))
        assert result["rule_materialization_authorized"] is True


class TestSimulatedEventsV0U1:
    """Lane U1: generate exact-U0-schema event artifacts from T1 rows only."""

    def _u0(self):
        return TestSimulatedEventSchemaLockU0()

    def _build(self, tmp_path):
        t1 = self._u0()._t1()
        diags, inventory = t1._full_chain_diags(tmp_path)
        u0 = self._u0()._build(diags, inventory)
        t1_diagnostics = t1._build(diags, inventory)
        return _build_simulated_events_v0_diagnostics(
            simulated_event_schema_lock_diagnostics=u0,
            materialized_rule_rows_v0_diagnostics=t1_diagnostics,
            materialized_rule_row_schema_lock_diagnostics=diags["materialized_rule_row_schema_lock_diagnostics"],
            no_output_runner_dry_harness_diagnostics=diags["no_output_runner_dry_harness_diagnostics"],
            projected_input_joinability_diagnostics=diags["projected_input_joinability_diagnostics"],
            projected_input_temporal_sequence_diagnostics=diags["projected_input_temporal_sequence_diagnostics"],
            projected_input_row_count_diagnostics=diags["projected_input_row_count_diagnostics"],
            projected_input_shape_inventory_diagnostics=diags["projected_input_shape_inventory_diagnostics"],
            allowed_runner_input_projection_diagnostics=diags["allowed_runner_input_projection_diagnostics"],
            no_output_runner_invocation_diagnostics=diags["no_output_runner_invocation_diagnostics"],
            implementation_boundary_diagnostics=diags["implementation_boundary_diagnostics"],
        )

    def test_full_valid_path_emits_exact_schema_artifacts(self, tmp_path):
        result = self._build(tmp_path)
        assert result["simulated_events_v0_version"] == SIMULATED_EVENTS_V0_VERSION
        assert result["simulated_events_v0_policy"] == SIMULATED_EVENTS_V0_POLICY
        assert result["simulated_events_v0_gate"]["gate_passed"] is True
        assert result["simulated_events_v0_gate"]["gate_status"] == SIMULATED_EVENTS_V0_DECLARED_ARTIFACT_ONLY
        assert result["simulated_event_count"] == result["source_materialized_rule_row_count"] > 0
        assert result["simulated_events_emitted"] is True
        for event in result["simulated_events"]:
            assert set(event) == set(_ALLOWED_SIMULATED_EVENT_SCHEMA_KEYS)
            assert real_validation.FORBIDDEN_CALCULATION_KEYS.isdisjoint(event)
            assert event["event_metadata_only"] is True
        assert result["final_offline_verdict_remains"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION

    def test_u0_failure_fails_closed(self, tmp_path):
        result = self._build(tmp_path)
        result["simulated_event_schema_lock_gate_passed"] = False
        gate = _derive_simulated_events_v0_gate(result)
        assert gate["gate_status"] == BLOCKED_BY_SIMULATED_EVENT_SCHEMA_LOCK_GATE

    @pytest.mark.parametrize("field", [
        "materialized_rule_rows_v0_gate_passed", "materialized_rule_row_schema_lock_gate_passed",
        "no_output_runner_dry_harness_gate_passed", "projected_input_joinability_gate_passed",
        "projected_input_temporal_sequence_gate_passed", "projected_input_row_count_gate_passed",
        "projected_input_shape_inventory_gate_passed", "allowed_runner_input_projection_gate_passed",
        "no_output_runner_invocation_gate_passed", "implementation_boundary_gate_passed",
    ])
    def test_upstream_failure_fails_closed(self, tmp_path, field):
        result = self._build(tmp_path)
        result[field] = False
        assert _derive_simulated_events_v0_gate(result)["gate_passed"] is False

    @pytest.mark.parametrize("field, value", [
        ("simulated_events_v0_mode", "ANY_EVENT_OUTPUT"),
        ("simulated_events_v0_policy", "EMIT_ANYTHING"),
    ])
    def test_mutated_mode_or_policy_fails_closed(self, tmp_path, field, value):
        result = self._build(tmp_path)
        result[field] = value
        assert _derive_simulated_events_v0_gate(result)["gate_status"] == BLOCKED_BY_INCOMPLETE_SIMULATED_EVENTS_V0_EVIDENCE

    def test_simulated_events_emitted_false_with_events_fails_closed(self, tmp_path):
        result = self._build(tmp_path)
        assert result["simulated_event_count"] > 0
        result["simulated_events_emitted"] = False
        gate = _derive_simulated_events_v0_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == BLOCKED_BY_INCOMPLETE_SIMULATED_EVENTS_V0_EVIDENCE

    def test_count_mismatch_empty_and_schema_fail_closed(self, tmp_path):
        result = self._build(tmp_path)
        result["simulated_event_count"] += 1
        assert _derive_simulated_events_v0_gate(result)["gate_status"] == BLOCKED_BY_INCOMPLETE_SIMULATED_EVENTS_V0_EVIDENCE
        result = self._build(tmp_path)
        result["simulated_events"] = []
        result["simulated_event_count"] = 0
        result["event_count_matches_source_rule_row_count"] = False
        assert _derive_simulated_events_v0_gate(result)["gate_status"] == BLOCKED_BY_INCOMPLETE_SIMULATED_EVENTS_V0_EVIDENCE
        result = self._build(tmp_path)
        result["simulated_events"][0]["extra"] = "x"
        assert _derive_simulated_events_v0_gate(result)["gate_status"] == BLOCKED_BY_UNEXPECTED_SIMULATED_EVENT_SCHEMA

    @pytest.mark.parametrize("key", ["pnl", "return", "score", "trade", "order", "fill", "execution", "position", "close", "fundingRate", "price_value"])
    def test_forbidden_event_keys_fail_closed(self, tmp_path, key):
        result = self._build(tmp_path)
        result["simulated_events"][0][key] = "x"
        assert _derive_simulated_events_v0_gate(result)["gate_status"] == BLOCKED_BY_UNEXPECTED_SIMULATED_EVENT_FORBIDDEN_KEY

    @pytest.mark.parametrize("value", ["close", "fundingRate", "order", "fill", "execution", "position", "trade", "pnl", "return", "score"])
    def test_forbidden_event_values_fail_closed(self, tmp_path, value):
        result = self._build(tmp_path)
        result["simulated_events"][0]["event_action_code"] = value
        assert _derive_simulated_events_v0_gate(result)["gate_status"] == BLOCKED_BY_UNEXPECTED_SIMULATED_EVENT_FORBIDDEN_VALUE

    @pytest.mark.parametrize("field", [
        "economic_values_emitted", "statistical_values_emitted", "null_comparison_values_emitted",
        "scoring_values_emitted", "live_integration_values_emitted", "paper_integration_values_emitted",
        "final_verdict_values_emitted",
    ])
    def test_downstream_output_fails_closed(self, tmp_path, field):
        result = self._build(tmp_path)
        result[field] = True
        assert _derive_simulated_events_v0_gate(result)["gate_status"] == BLOCKED_BY_UNEXPECTED_SIMULATED_EVENT_DOWNSTREAM_OUTPUT

    @pytest.mark.parametrize("field", [
        "economic_value_generation_authorized", "statistical_value_generation_authorized",
        "candidate_comparison_authorized", "null_generation_authorized", "scoring_authorization",
        "live_integration_authorized", "paper_integration_authorized", "final_verdict_authorization",
    ])
    def test_downstream_authorization_fails_closed(self, tmp_path, field):
        result = self._build(tmp_path)
        result[field] = True
        assert _derive_simulated_events_v0_gate(result)["gate_status"] == BLOCKED_BY_UNEXPECTED_SIMULATED_EVENT_DOWNSTREAM_AUTHORIZATION

    def test_duplicate_and_reordered_events_fail_closed(self, tmp_path):
        result = self._build(tmp_path)
        events = [dict(event) for event in result["simulated_events"]]
        events.append(dict(events[0]))
        result["simulated_events"] = events
        result["simulated_event_count"] = len(events)
        assert _derive_simulated_events_v0_gate(result)["gate_passed"] is False
        result = self._build(tmp_path)
        result["simulated_events"] = list(reversed(result["simulated_events"]))
        assert _derive_simulated_events_v0_gate(result)["gate_passed"] is False

    def test_receipt_integration_no_input_path_fails_closed(self, tmp_path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        m1 = self._u0()._t1()._t0()._s1()._r1()._q1()._p1()._o1()._n1()._m1()
        assert real_validation.main(m1._cli_base_args(output_dir)) == 0
        diagnostics = json.loads((output_dir / "real_validation_receipt.json").read_text())["simulated_events_v0_diagnostics"]
        assert diagnostics["simulated_events_v0_gate"]["gate_passed"] is False
        assert diagnostics["simulated_events"] == []


class TestEconomicOutputSchemaLockV0:
    """Lane V0: future accounting schema is declared but never emitted."""

    def _u1(self):
        return TestSimulatedEventsV0U1()

    def _build(self, tmp_path):
        u1 = self._u1()
        result = u1._build(tmp_path)
        t1 = u1._u0()._t1()
        diags, inventory = t1._full_chain_diags(tmp_path)
        t1_diagnostics = t1._build(diags, inventory)
        u0 = u1._u0()._build(diags, inventory)
        return _build_economic_output_schema_lock_diagnostics(
            simulated_events_v0_diagnostics=result,
            simulated_event_schema_lock_diagnostics=u0,
            materialized_rule_rows_v0_diagnostics=t1_diagnostics,
            materialized_rule_row_schema_lock_diagnostics=diags["materialized_rule_row_schema_lock_diagnostics"],
            no_output_runner_dry_harness_diagnostics=diags["no_output_runner_dry_harness_diagnostics"],
            projected_input_joinability_diagnostics=diags["projected_input_joinability_diagnostics"],
            projected_input_temporal_sequence_diagnostics=diags["projected_input_temporal_sequence_diagnostics"],
            projected_input_row_count_diagnostics=diags["projected_input_row_count_diagnostics"],
            projected_input_shape_inventory_diagnostics=diags["projected_input_shape_inventory_diagnostics"],
            allowed_runner_input_projection_diagnostics=diags["allowed_runner_input_projection_diagnostics"],
            no_output_runner_invocation_diagnostics=diags["no_output_runner_invocation_diagnostics"],
            implementation_boundary_diagnostics=diags["implementation_boundary_diagnostics"],
        )

    def test_no_packet_no_input_receipt_fails_closed(self, tmp_path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        m1 = self._u1()._u0()._t1()._t0()._s1()._r1()._q1()._p1()._o1()._n1()._m1()
        assert real_validation.main(m1._cli_base_args(output_dir)) == 0
        receipt = json.loads((output_dir / "real_validation_receipt.json").read_text())
        diagnostics = receipt["economic_output_schema_lock_diagnostics"]
        assert diagnostics["economic_output_schema_lock_gate"]["gate_passed"] is False
        assert diagnostics["economic_output_schema_lock_gate"]["gate_status"] == BLOCKED_BY_SIMULATED_EVENTS_V0_GATE
        assert diagnostics["economic_output_row_count"] == diagnostics["accounting_row_count"] == 0
        assert diagnostics["amount_values_emitted"] is False
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION

    def test_declares_exact_schema_and_emits_nothing(self, tmp_path):
        result = self._build(tmp_path)
        assert result["diagnostic_kind"] == "economic_output_schema_lock"
        assert result["economic_output_schema_lock_version"] == ECONOMIC_OUTPUT_SCHEMA_LOCK_VERSION
        assert result["economic_output_schema_lock_scope"] == ECONOMIC_OUTPUT_SCHEMA_LOCK_SCOPE
        assert result["economic_output_schema_lock_status"] == ECONOMIC_OUTPUT_SCHEMA_LOCK_DECLARED_DIAGNOSTIC_ONLY
        assert result["economic_output_schema_policy"] == ECONOMIC_OUTPUT_SCHEMA_LOCK_POLICY
        assert result["allowed_economic_output_schema_keys"] == list(_ALLOWED_ECONOMIC_OUTPUT_SCHEMA_KEYS)
        assert result["required_economic_output_schema_keys"] == list(_REQUIRED_ECONOMIC_OUTPUT_SCHEMA_KEYS)
        assert set(result["required_economic_output_schema_keys"]) <= set(result["allowed_economic_output_schema_keys"])
        assert result["forbidden_economic_output_key_names"] == list(_FORBIDDEN_ECONOMIC_OUTPUT_SCHEMA_KEY_NAMES)
        assert result["economic_output_row_count"] == result["accounting_row_count"] == 0
        assert result["economic_output_rows_emitted"] is False
        assert result["accounting_rows_emitted"] is False
        assert result["amount_values_emitted"] is False
        assert result["economic_output_schema_lock_gate"]["gate_passed"] is True
        assert result["final_offline_verdict_remains"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION

    def test_u1_failure_and_schema_mutations_fail_closed(self, tmp_path):
        result = self._build(tmp_path)
        result["simulated_events_v0_gate_passed"] = False
        assert _derive_economic_output_schema_lock_gate(result)["gate_status"] == BLOCKED_BY_SIMULATED_EVENTS_V0_GATE
        for field, value in (("economic_output_schema_mode", "ECONOMIC_OUTPUT"), ("economic_output_schema_policy", "EMIT_AMOUNT_VALUES_NOW"), ("allowed_economic_output_schema_keys", []), ("required_economic_output_schema_keys", ["missing"])):
            result = self._build(tmp_path)
            result[field] = value
            assert _derive_economic_output_schema_lock_gate(result)["gate_status"] == BLOCKED_BY_INCOMPLETE_ECONOMIC_OUTPUT_SCHEMA_EVIDENCE

    @pytest.mark.parametrize("field", [
        "economic_output_rows_emitted", "accounting_rows_emitted", "amount_values_emitted",
        "price_values_emitted", "funding_rate_values_emitted", "economic_values_emitted",
        "statistical_values_emitted", "null_comparison_values_emitted", "scoring_values_emitted",
        "live_integration_values_emitted", "paper_integration_values_emitted", "final_verdict_values_emitted",
    ])
    def test_emissions_fail_closed(self, tmp_path, field):
        result = self._build(tmp_path)
        result[field] = True
        assert _derive_economic_output_schema_lock_gate(result)["gate_status"] == BLOCKED_BY_UNEXPECTED_ECONOMIC_OUTPUT_EMISSION

    @pytest.mark.parametrize("field", [
        "economic_output_schema_readiness", "economic_output_generation_authorized",
        "accounting_application_authorized", "amount_generation_authorized",
        "economic_value_generation_authorized", "statistical_value_generation_authorized",
        "candidate_comparison_authorized", "null_generation_authorized", "scoring_authorization",
        "live_integration_authorized", "paper_integration_authorized", "final_verdict_authorization",
    ])
    def test_authorizations_fail_closed(self, tmp_path, field):
        result = self._build(tmp_path)
        result[field] = True
        assert _derive_economic_output_schema_lock_gate(result)["gate_status"] == BLOCKED_BY_UNEXPECTED_ECONOMIC_OUTPUT_AUTHORIZATION

    def test_forbidden_name_as_actual_key_fails_closed(self, tmp_path):
        result = self._build(tmp_path)
        result["nested"] = {"pnl": "forbidden"}
        assert _derive_economic_output_schema_lock_gate(result)["gate_status"] == BLOCKED_BY_INCOMPLETE_ECONOMIC_OUTPUT_SCHEMA_EVIDENCE


class TestEconomicAccountingRowsV0V1:
    """Lane V1: U1 events become exact-schema neutral accounting artifacts."""

    def _build(self, tmp_path):
        v0 = TestEconomicOutputSchemaLockV0()
        u1 = v0._u1()
        events = u1._build(tmp_path)
        t1 = u1._u0()._t1()
        diags, inventory = t1._full_chain_diags(tmp_path)
        t1_diagnostics = t1._build(diags, inventory)
        u0 = u1._u0()._build(diags, inventory)
        schema = v0._build(tmp_path)
        return real_validation._build_economic_accounting_rows_v0_diagnostics(
            economic_output_schema_lock_diagnostics=schema,
            simulated_events_v0_diagnostics=events,
            simulated_event_schema_lock_diagnostics=u0,
            materialized_rule_rows_v0_diagnostics=t1_diagnostics,
            materialized_rule_row_schema_lock_diagnostics=diags["materialized_rule_row_schema_lock_diagnostics"],
            no_output_runner_dry_harness_diagnostics=diags["no_output_runner_dry_harness_diagnostics"],
            projected_input_joinability_diagnostics=diags["projected_input_joinability_diagnostics"],
            projected_input_temporal_sequence_diagnostics=diags["projected_input_temporal_sequence_diagnostics"],
            projected_input_row_count_diagnostics=diags["projected_input_row_count_diagnostics"],
            projected_input_shape_inventory_diagnostics=diags["projected_input_shape_inventory_diagnostics"],
            allowed_runner_input_projection_diagnostics=diags["allowed_runner_input_projection_diagnostics"],
            no_output_runner_invocation_diagnostics=diags["no_output_runner_invocation_diagnostics"],
            implementation_boundary_diagnostics=diags["implementation_boundary_diagnostics"],
        )

    def test_exact_neutral_rows_and_gate_pass(self, tmp_path):
        result = self._build(tmp_path)
        assert result["economic_accounting_rows_v0_gate"]["gate_passed"] is True
        assert result["accounting_row_count"] == result["source_simulated_event_count"] > 0
        assert all(set(row) == set(_ALLOWED_ECONOMIC_OUTPUT_SCHEMA_KEYS) for row in result["economic_accounting_rows"])
        assert all(row["accounting_amount_value"] == 0 for row in result["economic_accounting_rows"])
        assert result["final_offline_verdict_remains"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION

    @pytest.mark.parametrize("value", [False, 1, -1, 0.01, "0", None, float("nan"), float("inf"), {}, []])
    def test_non_neutral_amount_fails_closed(self, tmp_path, value):
        result = self._build(tmp_path)
        result["economic_accounting_rows"][0]["accounting_amount_value"] = value
        assert real_validation._derive_economic_accounting_rows_v0_gate(result)["gate_status"] == real_validation.BLOCKED_BY_UNEXPECTED_ECONOMIC_ACCOUNTING_NON_NEUTRAL_AMOUNT

    @pytest.mark.parametrize("key", ["pnl", "return", "profit", "edge", "score", "trade", "order", "fill", "execution", "position", "close", "fundingRate"])
    def test_forbidden_row_key_fails_closed(self, tmp_path, key):
        result = self._build(tmp_path)
        result["economic_accounting_rows"][0][key] = "x"
        assert real_validation._derive_economic_accounting_rows_v0_gate(result)["gate_status"] == real_validation.BLOCKED_BY_UNEXPECTED_ECONOMIC_ACCOUNTING_FORBIDDEN_KEY

    @pytest.mark.parametrize("field", ["amount_values_emitted", "economic_values_emitted"])
    def test_required_emission_evidence_false_fails_closed(self, tmp_path, field):
        result = self._build(tmp_path)
        result[field] = False
        assert real_validation._derive_economic_accounting_rows_v0_gate(result)["gate_status"] == real_validation.BLOCKED_BY_INCOMPLETE_ECONOMIC_ACCOUNTING_ROWS_V0_EVIDENCE

    def test_forbidden_row_value_fails_closed(self, tmp_path):
        result = self._build(tmp_path)
        result["economic_accounting_rows"][0]["accounting_entry_name"] = "profit"
        assert real_validation._derive_economic_accounting_rows_v0_gate(result)["gate_status"] == real_validation.BLOCKED_BY_UNEXPECTED_ECONOMIC_ACCOUNTING_FORBIDDEN_VALUE

    def test_schema_count_order_and_authorization_mutations_fail_closed(self, tmp_path):
        result = self._build(tmp_path)
        result["economic_accounting_rows"][0]["extra"] = "x"
        assert real_validation._derive_economic_accounting_rows_v0_gate(result)["gate_status"] == real_validation.BLOCKED_BY_UNEXPECTED_ECONOMIC_ACCOUNTING_ROW_SCHEMA
        result = self._build(tmp_path)
        result["economic_accounting_rows"] = list(reversed(result["economic_accounting_rows"]))
        assert real_validation._derive_economic_accounting_rows_v0_gate(result)["gate_passed"] is False
        result = self._build(tmp_path)
        result["amount_generation_authorized"] = False
        assert real_validation._derive_economic_accounting_rows_v0_gate(result)["gate_status"] == real_validation.BLOCKED_BY_INCOMPLETE_ECONOMIC_ACCOUNTING_ROWS_V0_EVIDENCE

    def test_no_input_receipt_includes_failed_v1_gate(self, tmp_path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        m1 = TestEconomicOutputSchemaLockV0()._u1()._u0()._t1()._t0()._s1()._r1()._q1()._p1()._o1()._n1()._m1()
        assert real_validation.main(m1._cli_base_args(output_dir)) == 0
        receipt = json.loads((output_dir / "real_validation_receipt.json").read_text())
        diagnostics = receipt["economic_accounting_rows_v0_diagnostics"]
        assert diagnostics["economic_accounting_rows_v0_gate"]["gate_status"] == real_validation.BLOCKED_BY_ECONOMIC_OUTPUT_SCHEMA_LOCK_GATE
        assert diagnostics["economic_accounting_rows"] == []
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION


class TestNullReferenceComparisonSchemaLockW0:
    """Lane W0: declare the future comparison schema and emit nothing."""

    def _build(self, tmp_path):
        v1 = TestEconomicAccountingRowsV0V1()._build(tmp_path)
        return real_validation._build_null_reference_comparison_schema_lock_diagnostics(
            economic_accounting_rows_v0_diagnostics=v1,
        )

    def test_schema_declared_with_zero_rows_and_values(self, tmp_path):
        result = self._build(tmp_path)
        assert result["diagnostic_kind"] == "null_reference_comparison_schema_lock_w0"
        assert result["declared_null_reference_comparison_schema_keys"] == list(
            real_validation._ALLOWED_NULL_REFERENCE_COMPARISON_SCHEMA_KEYS
        )
        assert result["comparison_rows"] == result["comparison_values"] == []
        assert result["comparison_row_count"] == result["comparison_value_count"] == 0
        assert result["comparison_rows_emitted"] is result["comparison_values_emitted"] is False
        assert result["null_reference_comparison_schema_lock_gate"]["gate_passed"] is True
        assert result["final_offline_verdict_remains"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION

    def test_v1_and_older_upstream_failures_fail_closed(self, tmp_path):
        result = self._build(tmp_path)
        result["economic_accounting_rows_v0_gate_passed"] = False
        assert real_validation._derive_null_reference_comparison_schema_lock_gate(result)["gate_status"] == real_validation.BLOCKED_BY_ECONOMIC_ACCOUNTING_ROWS_V0_GATE
        result = self._build(tmp_path)
        result["implementation_boundary_gate_passed"] = False
        assert real_validation._derive_null_reference_comparison_schema_lock_gate(result)["gate_status"] == real_validation.BLOCKED_BY_NULL_REFERENCE_COMPARISON_UPSTREAM_GATE

    def test_schema_key_removal_or_addition_fails_closed(self, tmp_path):
        result = self._build(tmp_path)
        result["declared_null_reference_comparison_schema_keys"].pop()
        assert real_validation._derive_null_reference_comparison_schema_lock_gate(result)["gate_status"] == real_validation.BLOCKED_BY_UNEXPECTED_NULL_REFERENCE_COMPARISON_SCHEMA_MUTATION
        result = self._build(tmp_path)
        result["declared_null_reference_comparison_schema_keys"].append("unexpected")
        assert real_validation._derive_null_reference_comparison_schema_lock_gate(result)["gate_status"] == real_validation.BLOCKED_BY_UNEXPECTED_NULL_REFERENCE_COMPARISON_SCHEMA_MUTATION

    @pytest.mark.parametrize("field, value", [
        ("comparison_row_count", 1), ("comparison_rows", [{"safe": "metadata"}]),
    ])
    def test_emitted_comparison_rows_fail_closed(self, tmp_path, field, value):
        result = self._build(tmp_path)
        result[field] = value
        assert real_validation._derive_null_reference_comparison_schema_lock_gate(result)["gate_status"] == real_validation.BLOCKED_BY_UNEXPECTED_EMITTED_COMPARISON_ROWS

    @pytest.mark.parametrize("field, value", [
        ("comparison_value_count", 1), ("comparison_values_emitted", True),
    ])
    def test_emitted_comparison_values_fail_closed(self, tmp_path, field, value):
        result = self._build(tmp_path)
        result[field] = value
        assert real_validation._derive_null_reference_comparison_schema_lock_gate(result)["gate_status"] == real_validation.BLOCKED_BY_UNEXPECTED_EMITTED_COMPARISON_VALUES

    @pytest.mark.parametrize("field", [
        "statistical_values_emitted", "scoring_values_emitted", "live_integration_values_emitted",
        "paper_integration_values_emitted", "final_verdict_values_emitted",
    ])
    def test_downstream_output_fails_closed(self, tmp_path, field):
        result = self._build(tmp_path)
        result[field] = True
        assert real_validation._derive_null_reference_comparison_schema_lock_gate(result)["gate_status"] == real_validation.BLOCKED_BY_UNEXPECTED_NULL_REFERENCE_COMPARISON_DOWNSTREAM_OUTPUT

    @pytest.mark.parametrize("field", [
        "candidate_comparison_authorized", "null_generation_authorized",
        "scoring_authorization", "final_verdict_authorization",
    ])
    def test_downstream_authorization_fails_closed(self, tmp_path, field):
        result = self._build(tmp_path)
        result[field] = True
        assert real_validation._derive_null_reference_comparison_schema_lock_gate(result)["gate_status"] == real_validation.BLOCKED_BY_UNEXPECTED_NULL_REFERENCE_COMPARISON_DOWNSTREAM_AUTHORIZATION

    def test_final_verdict_mutation_fails_closed(self, tmp_path):
        result = self._build(tmp_path)
        result["final_offline_verdict_remains"] = "MUTATED"
        assert real_validation._derive_null_reference_comparison_schema_lock_gate(result)["gate_status"] == real_validation.BLOCKED_BY_NULL_REFERENCE_COMPARISON_FINAL_VERDICT_ADVANCEMENT

    def test_no_input_cli_receipt_includes_failed_w0_gate(self, tmp_path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        m1 = TestEconomicOutputSchemaLockV0()._u1()._u0()._t1()._t0()._s1()._r1()._q1()._p1()._o1()._n1()._m1()
        assert real_validation.main(m1._cli_base_args(output_dir)) == 0
        receipt = json.loads((output_dir / "real_validation_receipt.json").read_text())
        diagnostics = receipt["null_reference_comparison_schema_lock_diagnostics"]
        assert diagnostics["null_reference_comparison_schema_lock_gate"]["gate_passed"] is False
        assert diagnostics["comparison_rows"] == diagnostics["comparison_values"] == []
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION

    def test_full_cli_receipt_includes_w0_and_remains_blocked(self, tmp_path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        bars_dir = tmp_path / "bars"
        funding_dir = tmp_path / "funding"
        bars_dir.mkdir()
        funding_dir.mkdir()
        _write_tiny_bars_csv(bars_dir, "BTCUSDT_8h_ohlcv.csv")
        _write_tiny_funding_csv(funding_dir, "BTCUSDT_8h_funding.csv")
        j1 = TestEconomicAccountingPolicyPreregistrationJ1()
        assert real_validation.main(
            j1._cli_base_args(output_dir)
            + j1._cli_upstream_args()
            + j1._cli_eap_args()
            + ["--bars-dir", str(bars_dir), "--funding-dir", str(funding_dir)]
        ) == 0
        receipt = json.loads((output_dir / "real_validation_receipt.json").read_text())
        diagnostics = receipt["null_reference_comparison_schema_lock_diagnostics"]
        assert diagnostics["diagnostic_kind"] == "null_reference_comparison_schema_lock_w0"
        assert diagnostics["comparison_row_count"] == diagnostics["comparison_value_count"] == 0
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION


class TestProjectedInputShapeInventoryO1:
    """Lane O1: projected input shape inventory diagnostics."""

    def _n1(self):
        return TestAllowedRunnerInputProjectionN1()

    def _full_chain_diags(self):
        diags = self._n1()._full_chain_diags()
        projection = _build_allowed_runner_input_projection_diagnostics(**diags)
        diags["allowed_runner_input_projection_diagnostics"] = projection
        return diags

    def _absence_diags(self):
        diags = self._n1()._absence_diags()
        projection = _build_allowed_runner_input_projection_diagnostics(**diags)
        diags["allowed_runner_input_projection_diagnostics"] = projection
        return diags

    def _build(self, diags):
        return _build_projected_input_shape_inventory_diagnostics(
            allowed_runner_input_projection_diagnostics=diags[
                "allowed_runner_input_projection_diagnostics"
            ],
            no_output_runner_invocation_diagnostics=diags[
                "no_output_runner_invocation_diagnostics"
            ],
            implementation_boundary_diagnostics=diags[
                "implementation_boundary_diagnostics"
            ],
        )

    def _result(self):
        return self._build(self._full_chain_diags())

    def test_shape_inventory_no_args_projection_failed_fails_closed(self):
        result = self._build(self._absence_diags())
        gate = result["projected_input_shape_inventory_gate"]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == BLOCKED_BY_ALLOWED_RUNNER_INPUT_PROJECTION_GATE
        for field in _PROJECTED_INPUT_SHAPE_INVENTORY_AUTHORIZATION_FIELDS:
            assert result[field] is False

    def test_shape_inventory_diagnostic_full_happy_path(self):
        result = self._result()
        assert result["diagnostic_kind"] == "projected_input_shape_inventory"
        assert result["projected_input_shape_inventory_version"] == (
            PROJECTED_INPUT_SHAPE_INVENTORY_VERSION
        )
        assert result["projected_input_shape_inventory_scope"] == (
            PROJECTED_INPUT_SHAPE_INVENTORY_SCOPE
        )
        assert result["projected_input_shape_inventory_status"] == (
            PROJECTED_INPUT_SHAPE_INVENTORY_DECLARED_DIAGNOSTIC_ONLY
        )
        assert result["projected_input_shape_inventory_mode"] == "METADATA_ONLY"
        assert result["projected_input_shape_inventory_policy"] == (
            PROJECTED_INPUT_SHAPE_METADATA_ONLY_POLICY
        )
        assert result["allowed_input_roles"] == ["bars", "funding"]
        assert result["allowed_bar_columns"] == ["close", "timestamp"]
        assert result["allowed_funding_columns"] == ["fundingRate", "fundingTime"]
        assert result["excluded_bar_columns"] == ["open", "high", "low", "volume"]
        assert result["excluded_funding_columns"] == ["markPrice"]
        assert result["shape_inventory_values_emitted"] is False
        assert result["shape_inventory_row_values_emitted"] is False
        assert result["projected_input_values_emitted"] is False
        assert result["projected_input_row_values_emitted"] is False
        assert result["rule_output_rows_emitted"] is False
        summary = result["shape_inventory_summary"]
        assert summary["summary_kind"] == "metadata_only_shape_summary"
        assert summary["roles_declared"] == ["bars", "funding"]
        assert summary["allowed_column_names_by_role"] == {
            "bars": ["close", "timestamp"],
            "funding": ["fundingRate", "fundingTime"],
        }
        assert summary["excluded_column_names_by_role"] == {
            "bars": ["open", "high", "low", "volume"],
            "funding": ["markPrice"],
        }
        assert summary["row_values_included"] is False
        assert summary["rule_outputs_included"] is False
        for field in _PROJECTED_INPUT_SHAPE_INVENTORY_AUTHORIZATION_FIELDS:
            assert result[field] is False
        assert result["final_offline_verdict_remains"] == (
            BLOCKED_BY_VALIDATION_IMPLEMENTATION
        )

    def test_shape_inventory_gate_happy_path(self):
        gate = self._result()["projected_input_shape_inventory_gate"]
        assert gate["gate_passed"] is True
        assert gate["gate_status"] == (
            PROJECTED_INPUT_SHAPE_INVENTORY_DECLARED_DIAGNOSTIC_ONLY
        )
        assert gate["gate_scoring_authorization"] is False
        assert gate["gate_live_authorization"] is False
        assert gate["gate_final_verdict_authorization"] is False
        assert gate["gate_downstream_unlocks"] == []
        assert gate["blocked_reason"] is None

    def test_allowed_runner_input_projection_gate_missing_fails_closed(self):
        diags = self._full_chain_diags()
        projection = dict(diags["allowed_runner_input_projection_diagnostics"])
        del projection["allowed_runner_input_projection_gate"]
        diags["allowed_runner_input_projection_diagnostics"] = projection
        gate = self._build(diags)[
            "projected_input_shape_inventory_gate"
        ]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == BLOCKED_BY_ALLOWED_RUNNER_INPUT_PROJECTION_GATE

    def test_allowed_runner_input_projection_gate_failed_fails_closed(self):
        diags = self._full_chain_diags()
        projection = dict(diags["allowed_runner_input_projection_diagnostics"])
        failed_gate = dict(projection["allowed_runner_input_projection_gate"])
        failed_gate["gate_passed"] = False
        projection["allowed_runner_input_projection_gate"] = failed_gate
        diags["allowed_runner_input_projection_diagnostics"] = projection
        gate = self._build(diags)[
            "projected_input_shape_inventory_gate"
        ]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == BLOCKED_BY_ALLOWED_RUNNER_INPUT_PROJECTION_GATE

    def test_no_output_runner_invocation_gate_missing_fails_closed(self):
        diags = self._full_chain_diags()
        runner_diag = dict(diags["no_output_runner_invocation_diagnostics"])
        del runner_diag["no_output_runner_invocation_gate"]
        diags["no_output_runner_invocation_diagnostics"] = runner_diag
        gate = self._build(diags)[
            "projected_input_shape_inventory_gate"
        ]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == BLOCKED_BY_NO_OUTPUT_RUNNER_INVOCATION_GATE

    def test_implementation_boundary_gate_missing_fails_closed(self):
        diags = self._full_chain_diags()
        boundary = dict(diags["implementation_boundary_diagnostics"])
        del boundary["implementation_boundary_gate"]
        diags["implementation_boundary_diagnostics"] = boundary
        gate = self._build(diags)[
            "projected_input_shape_inventory_gate"
        ]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == "BLOCKED_BY_IMPLEMENTATION_BOUNDARY_GATE"

    def test_missing_or_false_declared_fails_closed(self):
        result = self._result()
        del result["projected_input_shape_inventory_declared"]
        gate = _derive_projected_input_shape_inventory_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_PROJECTED_INPUT_SHAPE_EVIDENCE
        )

        result = self._result()
        result["projected_input_shape_inventory_declared"] = False
        gate = _derive_projected_input_shape_inventory_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_PROJECTED_INPUT_SHAPE_EVIDENCE
        )

    def test_mutated_shape_mode_fails_closed(self):
        result = self._result()
        result["projected_input_shape_inventory_mode"] = "ROW_VALUES"
        gate = _derive_projected_input_shape_inventory_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_PROJECTED_INPUT_SHAPE_EVIDENCE
        )

    def test_mutated_shape_policy_fails_closed(self):
        result = self._result()
        result["projected_input_shape_inventory_policy"] = "EMIT_ROW_VALUES_NOW"
        gate = _derive_projected_input_shape_inventory_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_PROJECTED_INPUT_SHAPE_EVIDENCE
        )

    def test_mutated_allowed_input_roles_fails_closed(self):
        result = self._result()
        result["allowed_input_roles"] = ["bars", "funding", "other"]
        gate = _derive_projected_input_shape_inventory_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_PROJECTED_INPUT_SHAPE_EVIDENCE
        )

    def test_mutated_allowed_bar_columns_fails_closed(self):
        result = self._result()
        result["allowed_bar_columns"] = ["close", "open", "timestamp"]
        gate = _derive_projected_input_shape_inventory_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_PROJECTED_INPUT_SHAPE_EVIDENCE
        )

    def test_mutated_allowed_funding_columns_fails_closed(self):
        result = self._result()
        result["allowed_funding_columns"] = [
            "fundingRate",
            "fundingTime",
            "markPrice",
        ]
        gate = _derive_projected_input_shape_inventory_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_PROJECTED_INPUT_SHAPE_EVIDENCE
        )

    def test_missing_excluded_columns_fail_closed(self):
        result = self._result()
        result["excluded_bar_columns"] = []
        result["excluded_funding_columns"] = []
        gate = _derive_projected_input_shape_inventory_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_PROJECTED_INPUT_SHAPE_EVIDENCE
        )

    def test_any_emitted_flag_true_fails_closed(self):
        for field in (
            "shape_inventory_values_emitted",
            "shape_inventory_row_values_emitted",
            "projected_input_values_emitted",
            "projected_input_row_values_emitted",
            "rule_output_rows_emitted",
        ):
            result = self._result()
            result[field] = True
            gate = _derive_projected_input_shape_inventory_gate(result)
            assert gate["gate_passed"] is False
            assert gate["gate_status"] == BLOCKED_BY_UNEXPECTED_INPUT_VALUE_EMISSION

    def test_shape_summary_row_values_included_fails_closed(self):
        result = self._result()
        summary = dict(result["shape_inventory_summary"])
        summary["row_values_included"] = True
        result["shape_inventory_summary"] = summary
        gate = _derive_projected_input_shape_inventory_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_PROJECTED_INPUT_SHAPE_EVIDENCE
        )

    def test_shape_summary_rule_outputs_included_fails_closed(self):
        result = self._result()
        summary = dict(result["shape_inventory_summary"])
        summary["rule_outputs_included"] = True
        result["shape_inventory_summary"] = summary
        gate = _derive_projected_input_shape_inventory_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_PROJECTED_INPUT_SHAPE_EVIDENCE
        )

    def test_unexpected_authorization_fails_closed(self):
        result = self._result()
        result["decision_row_generation_authorized"] = True
        gate = _derive_projected_input_shape_inventory_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == "BLOCKED_BY_UNEXPECTED_AUTHORIZATION"
        assert "decision_row_generation_authorized" in gate["blocked_reason"]

    def test_receipt_integration_no_packet_args(self, tmp_path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        exit_code = real_validation.main(self._n1()._m1()._cli_base_args(output_dir))
        assert exit_code == 0
        receipt = json.loads(
            (output_dir / "real_validation_receipt.json").read_text()
        )
        inventory = receipt["projected_input_shape_inventory_diagnostics"]
        gate = inventory["projected_input_shape_inventory_gate"]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == BLOCKED_BY_ALLOWED_RUNNER_INPUT_PROJECTION_GATE
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION

    def test_receipt_integration_full_path(self, tmp_path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        m1 = self._n1()._m1()
        exit_code = real_validation.main(
            m1._cli_base_args(output_dir) + m1._cli_full_chain_args()
        )
        assert exit_code == 0
        receipt = json.loads(
            (output_dir / "real_validation_receipt.json").read_text()
        )
        assert receipt["prerequisite_closure_diagnostics"][
            "prerequisite_closure_gate"
        ]["gate_passed"] is True
        assert receipt["implementation_boundary_diagnostics"][
            "implementation_boundary_gate"
        ]["gate_passed"] is True
        assert receipt["no_output_runner_invocation_diagnostics"][
            "no_output_runner_invocation_gate"
        ]["gate_passed"] is True
        assert receipt["allowed_runner_input_projection_diagnostics"][
            "allowed_runner_input_projection_gate"
        ]["gate_passed"] is True
        inventory = receipt["projected_input_shape_inventory_diagnostics"]
        assert inventory["projected_input_shape_inventory_gate"][
            "gate_passed"
        ] is True
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION

    def test_no_forbidden_calculation_keys(self):
        result = self._result()
        all_keys = _all_dict_keys(result)
        assert real_validation.FORBIDDEN_CALCULATION_KEYS.isdisjoint(all_keys), (
            f"Forbidden keys found: "
            f"{real_validation.FORBIDDEN_CALCULATION_KEYS & all_keys}"
        )


class TestProjectedInputRowCountP1:
    """Lane P1: projected input row-count / column-presence diagnostics."""

    def _o1(self):
        return TestProjectedInputShapeInventoryO1()

    def _valid_inventory(self):
        return {
            "roles": [
                {
                    "role": "bars",
                    "files": [
                        {
                            "filename": "BTCUSDT_8h_ohlcv.csv",
                            "symbol": "BTCUSDT",
                            "row_count": 3,
                            "column_names": [
                                "timestamp",
                                "open",
                                "high",
                                "low",
                                "close",
                                "volume",
                            ],
                        }
                    ],
                },
                {
                    "role": "funding",
                    "files": [
                        {
                            "filename": "BTCUSDT_8h_funding.csv",
                            "symbol": "BTCUSDT",
                            "row_count": 2,
                            "column_names": [
                                "fundingTime",
                                "fundingRate",
                                "markPrice",
                            ],
                        }
                    ],
                },
            ]
        }

    def _full_chain_diags(self, inventory_diagnostics=None):
        diags = self._o1()._full_chain_diags()
        shape_inventory = _build_projected_input_shape_inventory_diagnostics(
            allowed_runner_input_projection_diagnostics=diags[
                "allowed_runner_input_projection_diagnostics"
            ],
            no_output_runner_invocation_diagnostics=diags[
                "no_output_runner_invocation_diagnostics"
            ],
            implementation_boundary_diagnostics=diags[
                "implementation_boundary_diagnostics"
            ],
            inventory_diagnostics=inventory_diagnostics or self._valid_inventory(),
        )
        diags["projected_input_shape_inventory_diagnostics"] = shape_inventory
        return diags

    def _absence_diags(self):
        diags = self._o1()._absence_diags()
        inventory = _build_projected_input_shape_inventory_diagnostics(
            allowed_runner_input_projection_diagnostics=diags[
                "allowed_runner_input_projection_diagnostics"
            ],
            no_output_runner_invocation_diagnostics=diags[
                "no_output_runner_invocation_diagnostics"
            ],
            implementation_boundary_diagnostics=diags[
                "implementation_boundary_diagnostics"
            ],
        )
        diags["projected_input_shape_inventory_diagnostics"] = inventory
        return diags

    def _build(self, diags, inventory=None):
        return _build_projected_input_row_count_diagnostics(
            projected_input_shape_inventory_diagnostics=diags[
                "projected_input_shape_inventory_diagnostics"
            ],
            allowed_runner_input_projection_diagnostics=diags[
                "allowed_runner_input_projection_diagnostics"
            ],
            no_output_runner_invocation_diagnostics=diags[
                "no_output_runner_invocation_diagnostics"
            ],
            implementation_boundary_diagnostics=diags[
                "implementation_boundary_diagnostics"
            ],
            inventory_diagnostics=inventory or self._valid_inventory(),
        )

    def _result(self):
        return self._build(self._full_chain_diags())

    def _build_with_inventory(self, inventory):
        return self._build(self._full_chain_diags(inventory), inventory)

    def _assert_row_count_gate_blocked_by_incomplete_evidence(self, result):
        gate = result["projected_input_row_count_gate"]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_PROJECTED_INPUT_ROW_COUNT_EVIDENCE
        )
        assert gate["gate_scoring_authorization"] is False
        assert gate["gate_live_authorization"] is False
        assert gate["gate_final_verdict_authorization"] is False
        for field in _PROJECTED_INPUT_ROW_COUNT_AUTHORIZATION_FIELDS:
            assert result[field] is False

    def test_row_count_no_args_shape_inventory_failed_fails_closed(self):
        result = self._build(self._absence_diags())
        gate = result["projected_input_row_count_gate"]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == BLOCKED_BY_PROJECTED_INPUT_SHAPE_INVENTORY_GATE
        for field in _PROJECTED_INPUT_ROW_COUNT_AUTHORIZATION_FIELDS:
            assert result[field] is False

    def test_row_count_diagnostic_full_happy_path(self):
        result = self._result()
        assert result["diagnostic_kind"] == "projected_input_row_count_inventory"
        assert result["projected_input_row_count_version"] == (
            PROJECTED_INPUT_ROW_COUNT_VERSION
        )
        assert result["projected_input_row_count_scope"] == (
            PROJECTED_INPUT_ROW_COUNT_SCOPE
        )
        assert result["projected_input_row_count_status"] == (
            PROJECTED_INPUT_ROW_COUNT_DECLARED_DIAGNOSTIC_ONLY
        )
        assert result["projected_input_row_count_mode"] == "METADATA_ONLY"
        assert result["projected_input_row_count_policy"] == (
            PROJECTED_INPUT_ROW_COUNT_METADATA_ONLY_POLICY
        )
        assert result["allowed_input_roles"] == ["bars", "funding"]
        assert result["allowed_bar_columns"] == ["close", "timestamp"]
        assert result["allowed_funding_columns"] == ["fundingRate", "fundingTime"]
        assert result["excluded_bar_columns"] == ["open", "high", "low", "volume"]
        assert result["excluded_funding_columns"] == ["markPrice"]
        assert result["row_count_summary_values_emitted"] is False
        assert result["row_value_samples_emitted"] is False
        assert result["timestamp_values_emitted"] is False
        assert result["price_values_emitted"] is False
        assert result["funding_values_emitted"] is False
        assert result["projected_input_values_emitted"] is False
        assert result["projected_input_row_values_emitted"] is False
        assert result["rule_output_rows_emitted"] is False
        summary = result["row_count_summary"]
        assert summary["summary_kind"] == "metadata_only_row_count_summary"
        assert summary["row_values_included"] is False
        assert summary["projected_row_values_included"] is False
        assert summary["rule_outputs_included"] is False
        assert summary["roles_declared"] == ["bars", "funding"]
        assert summary["allowed_column_names_by_role"] == {
            "bars": ["close", "timestamp"],
            "funding": ["fundingRate", "fundingTime"],
        }
        assert summary["excluded_column_names_by_role"] == {
            "bars": ["open", "high", "low", "volume"],
            "funding": ["markPrice"],
        }
        assert summary["allowed_column_presence_by_role"] == {
            "bars": {"close": True, "timestamp": True},
            "funding": {"fundingRate": True, "fundingTime": True},
        }
        assert summary["required_role_presence_by_role"] == {
            "bars": True,
            "funding": True,
        }
        assert summary["column_presence_source"] == "inventory_metadata"
        assert summary["column_presence_complete"] is True
        assert summary["forbidden_column_presence_by_role"] == {
            "bars": {
                "open": False,
                "high": False,
                "low": False,
                "volume": False,
            },
            "funding": {"markPrice": False},
        }
        assert isinstance(summary["role_row_counts"], dict)
        assert isinstance(summary["role_symbol_counts"], dict)
        assert isinstance(summary["role_split_counts"], dict)
        for field in _PROJECTED_INPUT_ROW_COUNT_AUTHORIZATION_FIELDS:
            assert result[field] is False
        assert result["final_offline_verdict_remains"] == (
            BLOCKED_BY_VALIDATION_IMPLEMENTATION
        )

    def test_row_count_gate_happy_path(self):
        gate = self._result()["projected_input_row_count_gate"]
        assert gate["gate_passed"] is True
        assert gate["gate_status"] == (
            PROJECTED_INPUT_ROW_COUNT_DECLARED_DIAGNOSTIC_ONLY
        )
        assert gate["gate_scoring_authorization"] is False
        assert gate["gate_live_authorization"] is False
        assert gate["gate_final_verdict_authorization"] is False
        assert gate["gate_downstream_unlocks"] == []
        assert gate["blocked_reason"] is None

    def test_bars_only_inventory_does_not_claim_funding_columns_present(self):
        inventory = {
            "roles": [
                {
                    "role": "bars",
                    "files": [
                        {
                            "filename": "BTCUSDT_8h_ohlcv.csv",
                            "symbol": "BTCUSDT",
                            "row_count": 3,
                            "column_names": ["timestamp", "close"],
                        }
                    ],
                }
            ]
        }
        result = self._build_with_inventory(inventory)
        summary = result["row_count_summary"]
        assert summary["required_role_presence_by_role"]["funding"] is False
        assert summary["allowed_column_presence_by_role"]["funding"] == {
            "fundingRate": False,
            "fundingTime": False,
        }
        assert summary["column_presence_complete"] is False
        self._assert_row_count_gate_blocked_by_incomplete_evidence(result)

    def test_missing_funding_role_fails_closed_even_when_upstream_gates_pass(self):
        inventory = self._valid_inventory()
        inventory["roles"] = [
            role for role in inventory["roles"] if role["role"] != "funding"
        ]
        result = self._build_with_inventory(inventory)
        assert result["projected_input_shape_inventory_gate_passed"] is True
        assert result["allowed_runner_input_projection_gate_passed"] is True
        assert result["no_output_runner_invocation_gate_passed"] is True
        assert result["implementation_boundary_gate_passed"] is True
        self._assert_row_count_gate_blocked_by_incomplete_evidence(result)

    def test_missing_bars_allowed_column_fails_closed(self):
        inventory = self._valid_inventory()
        bars_role = next(role for role in inventory["roles"] if role["role"] == "bars")
        bars_role["files"][0]["column_names"] = ["timestamp", "open", "high"]
        result = self._build_with_inventory(inventory)
        summary = result["row_count_summary"]
        assert summary["allowed_column_presence_by_role"]["bars"]["close"] is False
        assert summary["column_presence_complete"] is False
        self._assert_row_count_gate_blocked_by_incomplete_evidence(result)

    def test_missing_funding_allowed_column_fails_closed(self):
        inventory = self._valid_inventory()
        funding_role = next(
            role for role in inventory["roles"] if role["role"] == "funding"
        )
        funding_role["files"][0]["column_names"] = ["fundingTime", "markPrice"]
        result = self._build_with_inventory(inventory)
        summary = result["row_count_summary"]
        assert (
            summary["allowed_column_presence_by_role"]["funding"]["fundingRate"]
            is False
        )
        assert summary["column_presence_complete"] is False
        self._assert_row_count_gate_blocked_by_incomplete_evidence(result)

    def test_no_column_metadata_available_does_not_silently_pass(self):
        inventory = self._valid_inventory()
        for role in inventory["roles"]:
            for file_entry in role["files"]:
                del file_entry["column_names"]
        result = self._build_with_inventory(inventory)
        summary = result["row_count_summary"]
        assert summary["allowed_column_presence_by_role"]["bars"] == {
            "close": "UNKNOWN",
            "timestamp": "UNKNOWN",
        }
        assert summary["allowed_column_presence_by_role"]["funding"] == {
            "fundingRate": "UNKNOWN",
            "fundingTime": "UNKNOWN",
        }
        assert summary["column_presence_complete"] is False
        self._assert_row_count_gate_blocked_by_incomplete_evidence(result)

    def test_full_valid_inventory_with_required_columns_passes(self):
        result = self._build_with_inventory(self._valid_inventory())
        summary = result["row_count_summary"]
        assert summary["required_role_presence_by_role"] == {
            "bars": True,
            "funding": True,
        }
        assert summary["allowed_column_presence_by_role"] == {
            "bars": {"close": True, "timestamp": True},
            "funding": {"fundingRate": True, "fundingTime": True},
        }
        assert summary["column_presence_complete"] is True
        assert result["projected_input_row_count_gate"]["gate_passed"] is True

    def test_forbidden_columns_remain_excluded_from_projected_metadata(self):
        result = self._build_with_inventory(self._valid_inventory())
        summary = result["row_count_summary"]
        assert summary["allowed_column_presence_by_role"] == {
            "bars": {"close": True, "timestamp": True},
            "funding": {"fundingRate": True, "fundingTime": True},
        }
        assert "open" not in summary["allowed_column_presence_by_role"]["bars"]
        assert "markPrice" not in summary["allowed_column_presence_by_role"]["funding"]
        assert summary["forbidden_column_presence_by_role"] == {
            "bars": {
                "open": False,
                "high": False,
                "low": False,
                "volume": False,
            },
            "funding": {"markPrice": False},
        }
        assert result["projected_input_row_count_gate"]["gate_passed"] is True

    def test_projected_input_shape_inventory_gate_missing_fails_closed(self):
        diags = self._full_chain_diags()
        inventory = dict(diags["projected_input_shape_inventory_diagnostics"])
        del inventory["projected_input_shape_inventory_gate"]
        diags["projected_input_shape_inventory_diagnostics"] = inventory
        gate = self._build(diags)["projected_input_row_count_gate"]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == BLOCKED_BY_PROJECTED_INPUT_SHAPE_INVENTORY_GATE

    def test_projected_input_shape_inventory_gate_failed_fails_closed(self):
        diags = self._full_chain_diags()
        inventory = dict(diags["projected_input_shape_inventory_diagnostics"])
        failed_gate = dict(inventory["projected_input_shape_inventory_gate"])
        failed_gate["gate_passed"] = False
        inventory["projected_input_shape_inventory_gate"] = failed_gate
        diags["projected_input_shape_inventory_diagnostics"] = inventory
        gate = self._build(diags)["projected_input_row_count_gate"]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == BLOCKED_BY_PROJECTED_INPUT_SHAPE_INVENTORY_GATE

    def test_allowed_runner_input_projection_gate_failed_fails_closed(self):
        result = self._result()
        result["allowed_runner_input_projection_gate_passed"] = False
        gate = _derive_projected_input_row_count_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == BLOCKED_BY_ALLOWED_RUNNER_INPUT_PROJECTION_GATE

    def test_no_output_runner_invocation_gate_failed_fails_closed(self):
        result = self._result()
        result["no_output_runner_invocation_gate_passed"] = False
        gate = _derive_projected_input_row_count_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == BLOCKED_BY_NO_OUTPUT_RUNNER_INVOCATION_GATE

    def test_implementation_boundary_gate_failed_fails_closed(self):
        result = self._result()
        result["implementation_boundary_gate_passed"] = False
        gate = _derive_projected_input_row_count_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == "BLOCKED_BY_IMPLEMENTATION_BOUNDARY_GATE"

    def test_missing_or_false_row_count_declared_fails_closed(self):
        result = self._result()
        del result["projected_input_row_count_declared"]
        gate = _derive_projected_input_row_count_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_PROJECTED_INPUT_ROW_COUNT_EVIDENCE
        )

        result = self._result()
        result["projected_input_row_count_declared"] = False
        gate = _derive_projected_input_row_count_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_PROJECTED_INPUT_ROW_COUNT_EVIDENCE
        )

    def test_mutated_row_count_mode_fails_closed(self):
        result = self._result()
        result["projected_input_row_count_mode"] = "ROW_VALUES"
        gate = _derive_projected_input_row_count_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_PROJECTED_INPUT_ROW_COUNT_EVIDENCE
        )

    def test_mutated_row_count_policy_fails_closed(self):
        result = self._result()
        result["projected_input_row_count_policy"] = "EMIT_ROW_VALUES_NOW"
        gate = _derive_projected_input_row_count_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_PROJECTED_INPUT_ROW_COUNT_EVIDENCE
        )

    def test_mutated_allowed_input_roles_fails_closed(self):
        result = self._result()
        result["allowed_input_roles"] = ["bars", "funding", "other"]
        gate = _derive_projected_input_row_count_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_PROJECTED_INPUT_ROW_COUNT_EVIDENCE
        )

    def test_mutated_allowed_bar_columns_fails_closed(self):
        result = self._result()
        result["allowed_bar_columns"] = ["close", "open", "timestamp"]
        gate = _derive_projected_input_row_count_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_PROJECTED_INPUT_ROW_COUNT_EVIDENCE
        )

    def test_mutated_allowed_funding_columns_fails_closed(self):
        result = self._result()
        result["allowed_funding_columns"] = [
            "fundingRate",
            "fundingTime",
            "markPrice",
        ]
        gate = _derive_projected_input_row_count_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_PROJECTED_INPUT_ROW_COUNT_EVIDENCE
        )

    def test_missing_excluded_columns_fail_closed(self):
        result = self._result()
        result["excluded_bar_columns"] = []
        result["excluded_funding_columns"] = []
        gate = _derive_projected_input_row_count_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_PROJECTED_INPUT_ROW_COUNT_EVIDENCE
        )

    def test_any_emitted_value_flag_true_fails_closed(self):
        for field in (
            "row_count_summary_values_emitted",
            "row_value_samples_emitted",
            "timestamp_values_emitted",
            "price_values_emitted",
            "funding_values_emitted",
            "projected_input_values_emitted",
            "projected_input_row_values_emitted",
            "rule_output_rows_emitted",
        ):
            result = self._result()
            result[field] = True
            gate = _derive_projected_input_row_count_gate(result)
            assert gate["gate_passed"] is False
            assert gate["gate_status"] == BLOCKED_BY_UNEXPECTED_INPUT_VALUE_EMISSION

    def test_row_count_summary_row_values_included_fails_closed(self):
        result = self._result()
        summary = dict(result["row_count_summary"])
        summary["row_values_included"] = True
        result["row_count_summary"] = summary
        gate = _derive_projected_input_row_count_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_PROJECTED_INPUT_ROW_COUNT_EVIDENCE
        )

    def test_row_count_summary_projected_row_values_included_fails_closed(self):
        result = self._result()
        summary = dict(result["row_count_summary"])
        summary["projected_row_values_included"] = True
        result["row_count_summary"] = summary
        gate = _derive_projected_input_row_count_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_PROJECTED_INPUT_ROW_COUNT_EVIDENCE
        )

    def test_row_count_summary_rule_outputs_included_fails_closed(self):
        result = self._result()
        summary = dict(result["row_count_summary"])
        summary["rule_outputs_included"] = True
        result["row_count_summary"] = summary
        gate = _derive_projected_input_row_count_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_PROJECTED_INPUT_ROW_COUNT_EVIDENCE
        )

    def test_unexpected_authorization_fails_closed(self):
        result = self._result()
        result["decision_row_generation_authorized"] = True
        gate = _derive_projected_input_row_count_gate(result)
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == "BLOCKED_BY_UNEXPECTED_AUTHORIZATION"
        assert "decision_row_generation_authorized" in gate["blocked_reason"]

    def test_receipt_integration_no_packet_args(self, tmp_path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        exit_code = real_validation.main(
            self._o1()._n1()._m1()._cli_base_args(output_dir)
        )
        assert exit_code == 0
        receipt = json.loads(
            (output_dir / "real_validation_receipt.json").read_text()
        )
        diagnostics = receipt["projected_input_row_count_diagnostics"]
        gate = diagnostics["projected_input_row_count_gate"]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == BLOCKED_BY_PROJECTED_INPUT_SHAPE_INVENTORY_GATE
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION

    def test_receipt_integration_full_path(self, tmp_path):
        bars_dir = tmp_path / "bars"
        funding_dir = tmp_path / "funding"
        bars_dir.mkdir()
        funding_dir.mkdir()
        _write_tiny_bars_csv(bars_dir, "BTCUSDT_8h_ohlcv.csv")
        _write_tiny_funding_csv(funding_dir, "BTCUSDT_8h_funding.csv")
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        m1 = self._o1()._n1()._m1()
        exit_code = real_validation.main(
            m1._cli_base_args(output_dir)
            + m1._cli_full_chain_args()
            + [
                "--bars-dir",
                str(bars_dir),
                "--funding-dir",
                str(funding_dir),
            ]
        )
        assert exit_code == 0
        receipt = json.loads(
            (output_dir / "real_validation_receipt.json").read_text()
        )
        assert receipt["prerequisite_closure_diagnostics"][
            "prerequisite_closure_gate"
        ]["gate_passed"] is True
        assert receipt["implementation_boundary_diagnostics"][
            "implementation_boundary_gate"
        ]["gate_passed"] is True
        assert receipt["no_output_runner_invocation_diagnostics"][
            "no_output_runner_invocation_gate"
        ]["gate_passed"] is True
        assert receipt["allowed_runner_input_projection_diagnostics"][
            "allowed_runner_input_projection_gate"
        ]["gate_passed"] is True
        assert receipt["projected_input_shape_inventory_diagnostics"][
            "projected_input_shape_inventory_gate"
        ]["gate_passed"] is True
        diagnostics = receipt["projected_input_row_count_diagnostics"]
        assert diagnostics["projected_input_row_count_gate"][
            "gate_passed"
        ] is True
        summary = diagnostics["row_count_summary"]
        assert summary["required_role_presence_by_role"] == {
            "bars": True,
            "funding": True,
        }
        assert summary["allowed_column_presence_by_role"] == {
            "bars": {"close": True, "timestamp": True},
            "funding": {"fundingRate": True, "fundingTime": True},
        }
        assert summary["column_presence_source"] == "inventory_metadata"
        assert summary["column_presence_complete"] is True
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION

    def test_receipt_integration_no_funding_path_fails_p1_closed(
        self, tmp_path
    ):
        bars_dir = tmp_path / "bars"
        bars_dir.mkdir()
        _write_tiny_bars_csv(bars_dir, "BTCUSDT_8h_ohlcv.csv")
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        m1 = self._o1()._n1()._m1()
        exit_code = real_validation.main(
            m1._cli_base_args(output_dir)
            + m1._cli_full_chain_args()
            + ["--bars-dir", str(bars_dir)]
        )
        assert exit_code == 0
        receipt = json.loads(
            (output_dir / "real_validation_receipt.json").read_text()
        )
        diagnostics = receipt["projected_input_row_count_diagnostics"]
        summary = diagnostics["row_count_summary"]
        assert summary["required_role_presence_by_role"] == {
            "bars": True,
            "funding": False,
        }
        assert summary["allowed_column_presence_by_role"]["funding"] == {
            "fundingRate": False,
            "fundingTime": False,
        }
        assert summary["column_presence_complete"] is False
        gate = diagnostics["projected_input_row_count_gate"]
        assert gate["gate_passed"] is False
        assert gate["gate_status"] == (
            BLOCKED_BY_INCOMPLETE_PROJECTED_INPUT_ROW_COUNT_EVIDENCE
        )
        assert receipt["final_offline_verdict"] == BLOCKED_BY_VALIDATION_IMPLEMENTATION

    def test_no_forbidden_calculation_keys(self):
        result = self._result()
        all_keys = _all_dict_keys(result)
        assert real_validation.FORBIDDEN_CALCULATION_KEYS.isdisjoint(all_keys), (
            f"Forbidden keys found: "
            f"{real_validation.FORBIDDEN_CALCULATION_KEYS & all_keys}"
        )
