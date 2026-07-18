"""Independent, data-free validator for the H001 preregistration design."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

PROTOCOL_ID = "real_btc_h001_funding_crowding_reversal_falsification_v0"
HYPOTHESIS_ID = "candidate1-v1-funding-crowding-reversal-h001"
STATUS = "PREREGISTERED_DESIGN_ONLY"
DATA_IDENTITY = "UNBOUND_DESIGN_ONLY"
FUTURE_ARTIFACT_IDENTITY = "UNASSIGNED_REQUIRES_LATER_GOVERNANCE"
DESIGN_PATH = "docs/experiments/candidate1_h001_real_data_falsification_v0.json"

TOP_LEVEL = {
    "accounting_contract", "amendment_policy", "authorization_state", "classifications",
    "controls", "cost_contract", "custody_gates", "data_identity_status",
    "data_universe", "future_execution_sequence", "holdout_confirmation", "holdout_test",
    "future_artifact_identity", "hypothesis_id", "hypothesis_statement", "persistent_safety_state", "primary_question",
    "primary_statistic", "prohibited_interpretations", "protocol_id", "protocol_status",
    "raw_schema", "schema_version", "secondary_diagnostics", "signal_transformations",
    "source_synthetic_evidence", "split_contract", "stop_conditions", "temporal_join_contract",
    "trial_accounting", "validation_eligibility", "validation_selection", "validation_test",
    "variant_family",
}
VARIANT_KEYS = {"variant_id", "lookback", "price_deadband", "funding_deadband"}
AUTH_KEYS = {"artifact_operations_authorized", "current_primary_execution_budget", "current_primary_execution_count", "execution_authorized", "holdout_execution_authorized", "live_integration_authorized", "paper_trade_authorized", "real_data_access_authorized", "scientific_claim_authorized", "validation_execution_authorized"}
SAFETY_KEYS = {"edge_status", "live_status", "quarantine_access", "scientific_use_authorized", "paper_trade_authorized", "live_integration_authorized"}
DATA_KEYS = {"venue", "instrument", "timeframe", "timezone", "start", "end", "price_source", "funding_source", "allowed_later_source", "cross_venue_mixing"}
SPLIT_KEYS = {"development", "validation", "holdout"}
SPLIT_REGION_KEYS = {
    "development": {"start", "end", "allowed_purposes", "performance_selection_forbidden"},
    "validation": {"start", "end", "all_variants_and_controls_once"},
    "holdout": {"start", "end", "sealed_until_validation_pass", "warmup_bars_max", "warmup_from_prior_region_allowed", "warmup_excluded_from_statistics", "random_splits_forbidden", "outcome_informed_boundaries_forbidden"},
}
ACCOUNTING_KEYS = {"compounding_primary", "funding_return", "gross_price_return", "leverage", "net_return", "normalized_notional", "terminal_liquidation", "turnover"}
COST_KEYS = {"execution", "frozen_taker_fee", "funding_excluded_from_stress", "maker_or_favorable_tier_forbidden", "official_fee_source", "primary_cost", "slippage_spread_one_way", "stress_1_required", "stress_multipliers"}
PRIMARY_KEYS = {"flat_intervals_in_denominator", "name", "secondary_diagnostics"}
VALIDATION_KEYS = {"alternative", "bootstrap_repetitions", "candidate_family_size", "expected_stationary_bootstrap_block_length_intervals", "familywise_alpha", "hac_standard_error_lag_intervals", "null", "p_value", "record", "seed", "synchronous_resampling", "test"}
HOLDOUT_KEYS = {"alpha", "alternative", "bootstrap_repetitions", "expected_block_length_intervals", "hac_lag_intervals", "seed", "test"}
EXACT_NESTED_KEYS = {
    "raw_schema": {"bars", "funding", "integrity"},
    "signal_transformations": {"accounting_uses_raw_values", "funding_deadbands", "funding_signal_value", "price_deadbands", "price_signal_value", "rescaling_after_observation_forbidden"},
    "source_synthetic_evidence": {"may_select_real_variant", "status", "synthetic_variants_previously_explored"},
    "holdout_confirmation": {"active_intervals_min", "entries_min", "half_year_max_positive_contribution_fraction", "mean_base_cost_net_return_gt", "mean_stress_1_net_return_gt", "no_retry_after_failure", "p_value_lte", "periods", "positive_half_years_min"},
    "validation_eligibility": {"active_intervals_min", "entries_min", "familywise_adjusted_p_lte", "max_month_positive_contribution_fraction", "mean_base_cost_net_return_gt", "mean_stress_1_net_return_gt", "none_eligible_classification", "positive_base_mean_by_year"},
    "validation_selection": {"preserve_all_results", "primary", "tie_break"},
    "trial_accounting": {"controls", "current_authorized_executions", "exposed_result_replay_forbidden", "holdout_executions_allowed_conditional", "otherwise_new_protocol_required", "real_validation_candidate_tests", "replay_exception", "synthetic_variants_previously_explored", "validation_executions_allowed", "validation_selected_holdout_candidate_tests_max"},
    "custody_gates": {"artifact_identity_created_by_this_task", "bootstrap_independently_reviewed", "canonical_paths_forbidden", "cost_documentation_frozen_and_hashed", "data_files_created_by_this_task", "dependency_environment_frozen", "final_no_computation_preflight", "implementation_commit_frozen", "independent_restore_and_rehash_required", "joinability_without_strategy_computation", "later_governance_authorization", "portable_canonical_manifest_required", "raw_and_parsed_hashes_match_design", "raw_files_in_both", "required_durable_store_count", "two_independent_qualified_stores_required"},
}

VARIANTS = (
    ("h001-l1-pdb0-fdb0", 1, 0, 0), ("h001-l1-pdb0p5-fdb0p05", 1, 0.5, 0.05),
    ("h001-l1-pdb1-fdb0p1", 1, 1, 0.1), ("h001-l2-pdb0-fdb0", 2, 0, 0),
    ("h001-l2-pdb1-fdb0p05", 2, 1, 0.05), ("h001-l2-pdb2-fdb0p1", 2, 2, 0.1),
    ("h001-l4-pdb0-fdb0", 4, 0, 0), ("h001-l4-pdb1-fdb0p05", 4, 1, 0.05),
    ("h001-l4-pdb2-fdb0p1", 4, 2, 0.1),
)
CONTROLS = ["ALWAYS_FLAT", "ALWAYS_LONG", "ALWAYS_SHORT", "FUNDING_SIGN_FADE", "LAGGED_RETURN_SIGN", "LAGGED_RETURN_FADE"]

# This digest is an independently recorded fingerprint of the complete frozen
# canonical design.  It is deliberately not read from DESIGN_PATH: the input
# file is the value under test, not the validator's source of truth.
EXPECTED_CANONICAL_SHA256 = "c6fb8d796559c53188c10e729a2257bc593c7a80526963c97515f747820e2276"


class DesignValidationError(ValueError):
    pass


def _fail(message: str) -> None:
    raise DesignValidationError(message)


def _keys(value: object, expected: set[str], label: str) -> dict:
    if not isinstance(value, dict):
        _fail(f"{label} must be an object")
    actual = set(value)
    if actual != expected:
        _fail(f"{label} keys mismatch missing={sorted(expected - actual)} extra={sorted(actual - expected)}")
    return value


def _eq(value: object, expected: object, label: str) -> None:
    if value != expected:
        _fail(f"{label} drifted: expected {expected!r}")


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _false_auth(data: dict) -> None:
    _keys(data["authorization_state"], AUTH_KEYS, "authorization_state")
    for key, value in data["authorization_state"].items():
        if key.startswith("current_"):
            _eq(value, 0, f"authorization_state.{key}")
        else:
            _eq(value, False, f"authorization_state.{key}")
    _keys(data["persistent_safety_state"], SAFETY_KEYS, "persistent_safety_state")
    _eq(data["persistent_safety_state"], {"edge_status": "EDGE_UNPROVEN", "live_status": "BLOCK_LIVE_INTEGRATION", "quarantine_access": "forbidden", "scientific_use_authorized": False, "paper_trade_authorized": False, "live_integration_authorized": False}, "persistent_safety_state")


def _validate_variants(data: dict) -> None:
    variants = data["variant_family"]
    if len(variants) != 9:
        _fail("variant family must contain exactly nine candidates")
    actual = []
    for item in variants:
        _keys(item, VARIANT_KEYS, "variant")
        actual.append((item["variant_id"], item["lookback"], item["price_deadband"], item["funding_deadband"]))
    if len({x[0] for x in actual}) != 9 or tuple(actual) != VARIANTS:
        _fail("variant family differs from the frozen nine-variant family")
    _eq(data["controls"], CONTROLS, "controls")
    if data["controls"] == [v[0] for v in VARIANTS]:
        _fail("controls cannot become H001 candidates")


def _validate(data: dict) -> None:
    _keys(data, TOP_LEVEL, "design")
    _eq(data["schema_version"], "0.1.0", "schema_version")
    _eq(data["protocol_id"], PROTOCOL_ID, "protocol_id")
    _eq(data["hypothesis_id"], HYPOTHESIS_ID, "hypothesis_id")
    _eq(data["protocol_status"], STATUS, "protocol_status")
    _eq(data["data_identity_status"], DATA_IDENTITY, "data_identity_status")
    _eq(data["future_artifact_identity"], FUTURE_ARTIFACT_IDENTITY, "future_artifact_identity")
    _false_auth(data)
    _eq(data["source_synthetic_evidence"]["status"], "MECHANICAL_ONLY_NOT_SCIENTIFIC_EVIDENCE", "source_synthetic_evidence.status")
    for name, keys in EXACT_NESTED_KEYS.items():
        _keys(data[name], keys, name)
    _eq(data["source_synthetic_evidence"]["may_select_real_variant"], False, "source_synthetic_evidence.may_select_real_variant")
    _eq(data["data_universe"], {"venue": "Binance USD-M Futures", "instrument": "BTCUSDT linear USDT-margined perpetual contract", "timeframe": "8h", "timezone": "UTC", "start": "2020-01-01T00:00:00Z", "end": "2026-06-30T23:59:59Z", "price_source": "same Binance BTCUSDT perpetual venue", "funding_source": "same Binance BTCUSDT perpetual venue", "allowed_later_source": "official Binance public historical files or official Binance public API only", "cross_venue_mixing": False}, "data_universe")
    _keys(data["data_universe"], DATA_KEYS, "data_universe")
    _eq(data["raw_schema"]["bars"], ["open_time_utc", "close_time_utc", "open", "high", "low", "close", "volume"], "raw_schema.bars")
    _eq(data["raw_schema"]["funding"], ["funding_time_utc", "funding_rate_decimal"], "raw_schema.funding")
    _eq(data["signal_transformations"]["price_signal_value"], "100 * natural_log(raw_close)", "price transformation")
    _eq(data["signal_transformations"]["funding_signal_value"], "100 * raw_funding_rate_decimal", "funding transformation")
    join = data["temporal_join_contract"]
    for key, expected in {"decision_timestamp": "bar[t].open_time_utc", "entry": "bar[t].open", "exit": "bar[t].close", "signal_bar_closes": "close_time_utc <= bar[t].open_time_utc", "prior_funding": "latest funding_time_utc < bar[t].open_time_utc", "funding_cashflow_events": "bar[t].open_time_utc < funding_time_utc <= bar[t].close_time_utc", "funding_forward_fill_max_hours": 12, "nearest_neighbour_forbidden": True, "future_funding_forbidden": True, "equality_deadband_position": 0}.items():
        _eq(join[key], expected, f"temporal_join_contract.{key}")
    _validate_variants(data)
    _keys(data["split_contract"], SPLIT_KEYS, "split_contract")
    for name, region in data["split_contract"].items():
        _keys(region, SPLIT_REGION_KEYS[name], f"split_contract.{name}")
    _eq(data["split_contract"]["development"]["start"], "2020-01-01T00:00:00Z", "development start")
    _eq(data["split_contract"]["development"]["end"], "2022-12-31T23:59:59Z", "development end")
    _eq(data["split_contract"]["validation"]["start"], "2023-01-01T00:00:00Z", "validation start")
    _eq(data["split_contract"]["validation"]["end"], "2024-12-31T23:59:59Z", "validation end")
    _eq(data["split_contract"]["holdout"]["start"], "2025-01-01T00:00:00Z", "holdout start")
    _eq(data["split_contract"]["holdout"]["end"], "2026-06-30T23:59:59Z", "holdout end")
    _eq(data["split_contract"]["holdout"]["sealed_until_validation_pass"], True, "holdout sealing")
    cost = _keys(data["cost_contract"], COST_KEYS, "cost_contract")
    _eq(cost["execution"], "taker only", "cost execution")
    _eq(cost["frozen_taker_fee"], "max(official documented VIP-0 taker fee, 0.0005)", "taker fee floor")
    _eq(cost["slippage_spread_one_way"], 0.0002, "slippage/spread")
    _eq(cost["stress_multipliers"], {"base": 1.0, "stress_1": 1.5, "stress_2": 2.0}, "stress multipliers")
    _eq(cost["stress_1_required"], True, "stress-1 gate")
    accounting = _keys(data["accounting_contract"], ACCOUNTING_KEYS, "accounting_contract")
    _eq(accounting["gross_price_return"], "position * ((close / open) - 1)", "gross accounting")
    _eq(accounting["funding_return"], "-position * sum(raw_funding_rate_decimal for eligible held funding events)", "funding accounting")
    _eq(accounting["turnover"], "abs(position[t] - position[t-1])", "turnover accounting")
    _eq(accounting["terminal_liquidation"], "abs(final_position) * (frozen_taker_fee + 0.0002)", "terminal liquidation")
    primary = _keys(data["primary_statistic"], PRIMARY_KEYS, "primary_statistic")
    _eq(primary["name"], "mean net return per all evaluated 8h intervals", "primary statistic")
    if not primary["secondary_diagnostics"]:
        _fail("primary statistic must retain secondary diagnostics")
    validation = _keys(data["validation_test"], VALIDATION_KEYS, "validation_test")
    _eq(validation["test"], "synchronous stationary-bootstrap maximum-t family test", "validation test")
    for key, expected in {"candidate_family_size": 9, "bootstrap_repetitions": 10000, "expected_stationary_bootstrap_block_length_intervals": 63, "hac_standard_error_lag_intervals": 21, "alternative": "one-sided mean net return > 0", "familywise_alpha": 0.05, "synchronous_resampling": True}.items():
        _eq(validation[key], expected, f"validation_test.{key}")
    _eq(validation["seed"], "integer from first 16 hex characters of SHA256(protocol_id + ':validation:max-t:v0')", "validation seed")
    holdout = _keys(data["holdout_test"], HOLDOUT_KEYS, "holdout_test")
    _eq(holdout["test"], "single-series stationary-bootstrap t-test", "holdout test")
    for key, expected in {"bootstrap_repetitions": 10000, "expected_block_length_intervals": 63, "hac_lag_intervals": 21, "alternative": "one-sided mean net return > 0", "alpha": 0.05}.items():
        _eq(holdout[key], expected, f"holdout_test.{key}")
    _eq(data["holdout_confirmation"]["no_retry_after_failure"], True, "holdout fallback")
    _eq(data["holdout_confirmation"]["periods"], ["2025-H1", "2025-H2", "2026-H1"], "holdout periods")
    _eq(data["custody_gates"]["required_durable_store_count"], 2, "durable copy requirement")
    _eq(data["custody_gates"]["canonical_paths_forbidden"], ["/tmp", "/srv/qnty", "Git repository"], "canonical custody paths")
    for path in data["custody_gates"]["canonical_paths_forbidden"]:
        if path.startswith("/") and (path == "/tmp" or path == "/srv/qnty"):
            continue
    if any("/tmp" in str(v) or "/srv/qnty" in str(v) for v in data["custody_gates"].values() if isinstance(v, str)):
        _fail("canonical data custody path is forbidden")
    _eq(data["trial_accounting"]["current_authorized_executions"], 0, "trial execution count")
    _eq(data["trial_accounting"]["validation_executions_allowed"], 1, "validation execution budget")
    _eq(data["trial_accounting"]["holdout_executions_allowed_conditional"], 1, "holdout execution budget")


def verify(path: str | Path) -> None:
    p = Path(path)
    try:
        raw = p.read_bytes()
        data = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DesignValidationError(f"cannot load design: {exc}") from exc
    if raw.endswith(b"\n") or raw != _canonical_json_bytes(data):
        _fail("design JSON is not canonical")
    if hashlib.sha256(raw).hexdigest() != EXPECTED_CANONICAL_SHA256:
        _fail("design does not equal the independently frozen canonical contract")
    _validate(data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("verify")
    command.add_argument("path")
    args = parser.parse_args(argv)
    if args.command == "verify":
        verify(args.path)
        print("H001_PREREGISTRATION_VERIFY_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
