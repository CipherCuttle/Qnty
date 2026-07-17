import copy
import json
from pathlib import Path

import pytest

from quantbot.continuity.context import canonical_json_bytes
from quantbot.experiment.h001_real_falsification_preregistration import (
    DesignValidationError,
    verify,
)

ROOT = Path(__file__).parents[2]
DESIGN = ROOT / "docs/experiments/candidate1_h001_real_data_falsification_v0.json"


def loaded():
    return json.loads(DESIGN.read_bytes())


def write_design(tmp_path, data, *, canonical=True):
    path = tmp_path / "design.json"
    raw = canonical_json_bytes(data) if canonical else json.dumps(data, indent=2).encode()
    path.write_bytes(raw)
    return path


def assert_rejected(tmp_path, mutation):
    data = loaded()
    mutation(data)
    with pytest.raises(DesignValidationError):
        verify(write_design(tmp_path, data))


def test_canonical_design_passes():
    verify(DESIGN)


@pytest.mark.parametrize("mutator", [
    lambda d: d.pop("protocol_id"),
    lambda d: d.update(unknown=True),
    lambda d: d["authorization_state"].pop("execution_authorized"),
    lambda d: d["authorization_state"].update(unknown=True),
    lambda d: d["data_universe"].update(unknown=True),
    lambda d: d["variant_family"][0].pop("lookback"),
    lambda d: d["holdout_test"].update(unknown=True),
])
def test_missing_and_unknown_fields_fail_closed(tmp_path, mutator):
    assert_rejected(tmp_path, mutator)


def test_noncanonical_bytes_fail(tmp_path):
    with pytest.raises(DesignValidationError):
        verify(write_design(tmp_path, loaded(), canonical=False))
    path = tmp_path / "newline.json"
    path.write_bytes(DESIGN.read_bytes() + b"\n")
    with pytest.raises(DesignValidationError):
        verify(path)


@pytest.mark.parametrize("mutator", [
    lambda d: d.update(protocol_id="real_btc_candidate1_train_mechanism_decomposition_v0"),
    lambda d: d.update(hypothesis_id="wrong"),
    lambda d: d.update(data_identity_status="BOUND"),
    lambda d: d["authorization_state"].update(real_data_access_authorized=True),
    lambda d: d["authorization_state"].update(artifact_operations_authorized=True),
    lambda d: d["authorization_state"].update(current_primary_execution_budget=1),
    lambda d: d["persistent_safety_state"].update(edge_status="EDGE_PROVEN"),
    lambda d: d["persistent_safety_state"].update(live_status="ALLOW_LIVE_INTEGRATION"),
])
def test_identity_authorization_and_safety_mutations_fail(tmp_path, mutator):
    assert_rejected(tmp_path, mutator)


@pytest.mark.parametrize("field,value", [
    ("venue", "Other venue"), ("instrument", "BTCUSD"), ("timeframe", "1h"),
    ("start", "2021-01-01T00:00:00Z"), ("end", "2026-07-01T00:00:00Z"),
])
def test_data_universe_mutations_fail(tmp_path, field, value):
    assert_rejected(tmp_path, lambda d: d["data_universe"].update({field: value}))


@pytest.mark.parametrize("mutator", [
    lambda d: d["signal_transformations"].update(price_signal_value="raw_close"),
    lambda d: d["signal_transformations"].update(funding_signal_value="raw_funding_rate_decimal"),
    lambda d: d["temporal_join_contract"].update(future_funding_forbidden=False),
    lambda d: d["temporal_join_contract"].update(nearest_neighbour_forbidden=False),
    lambda d: d["temporal_join_contract"].update(funding_forward_fill_max_hours=13),
    lambda d: d["temporal_join_contract"].update(equality_deadband_position=1),
])
def test_transform_and_join_mutations_fail(tmp_path, mutator):
    assert_rejected(tmp_path, mutator)


@pytest.mark.parametrize("mutator", [
    lambda d: d["variant_family"].pop(),
    lambda d: d["variant_family"].append(copy.deepcopy(d["variant_family"][0])),
    lambda d: d["variant_family"].__setitem__(0, {**d["variant_family"][0], "lookback": 99}),
    lambda d: d["variant_family"].__setitem__(0, {**d["variant_family"][0], "price_deadband": 99}),
    lambda d: d["variant_family"].__setitem__(0, {**d["variant_family"][0], "funding_deadband": 99}),
    lambda d: d.update(controls=d["variant_family"]),
])
def test_variant_and_control_mutations_fail(tmp_path, mutator):
    assert_rejected(tmp_path, mutator)


@pytest.mark.parametrize("mutator", [
    lambda d: d["split_contract"]["validation"].update(start="2022-01-01T00:00:00Z"),
    lambda d: d["split_contract"]["holdout"].update(start="2024-01-01T00:00:00Z"),
    lambda d: d["split_contract"]["holdout"].update(sealed_until_validation_pass=False),
    lambda d: d["holdout_confirmation"].update(no_retry_after_failure=False),
    lambda d: d["holdout_confirmation"].update(periods=["fallback"]),
])
def test_split_and_holdout_mutations_fail(tmp_path, mutator):
    assert_rejected(tmp_path, mutator)


@pytest.mark.parametrize("mutator", [
    lambda d: d["cost_contract"].update(execution="maker"),
    lambda d: d["cost_contract"].update(frozen_taker_fee="0.0001"),
    lambda d: d["cost_contract"].update(slippage_spread_one_way=0.0),
    lambda d: d["cost_contract"]["stress_multipliers"].update(stress_1=1.0),
    lambda d: d["accounting_contract"].update(terminal_liquidation="omitted"),
    lambda d: d["primary_statistic"].update(name="mean active return"),
    lambda d: d["primary_statistic"].update(secondary_diagnostics=[]),
])
def test_cost_accounting_and_primary_statistic_mutations_fail(tmp_path, mutator):
    assert_rejected(tmp_path, mutator)


@pytest.mark.parametrize("mutator", [
    lambda d: d["validation_test"].update(bootstrap_repetitions=9999),
    lambda d: d["validation_test"].update(expected_stationary_bootstrap_block_length_intervals=64),
    lambda d: d["validation_test"].update(hac_standard_error_lag_intervals=22),
    lambda d: d["validation_test"].update(test="ordinary t-test"),
    lambda d: d["validation_test"].update(familywise_alpha=0.1),
    lambda d: d["validation_test"].update(seed="random"),
])
def test_validation_test_mutations_fail(tmp_path, mutator):
    assert_rejected(tmp_path, mutator)


@pytest.mark.parametrize("mutator", [
    lambda d: d["trial_accounting"].update(current_authorized_executions=1),
    lambda d: d["custody_gates"].update(required_durable_store_count=1),
    lambda d: d["custody_gates"].update(canonical_paths_forbidden=["/tmp/design"]),
    lambda d: d["custody_gates"].update(canonical_paths_forbidden=["/srv/qnty/design"]),
    lambda d: d["custody_gates"].update(canonical_paths_forbidden=["/home/swirky/DevHub/repos/Qnty"]),
])
def test_execution_and_custody_mutations_fail(tmp_path, mutator):
    assert_rejected(tmp_path, mutator)
