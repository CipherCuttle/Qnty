"""Synthetic-only tests for the Candidate 1 train mechanism decomposition core.

Everything here is synthetic: ``tmp_path`` CSVs, synthetic registries, and
synthetic receipt bytes with synthetic expected hashes. No real BTC data, no
archived receipt, and no execution of Candidate 1 or the decomposition on real
inputs is read or performed. The only non-synthetic constants referenced are the
data-independent frozen rule fingerprints and canonical names, which are pure
functions of the module's definitions (not of any market data).
"""

from __future__ import annotations

import builtins
import csv
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from quantbot.experiment import offline_edge_real_validation as subject


BOUNDARY = 220

# Synthetic seal / packet / gate / partition fingerprints. The core only checks
# equality between the registry and the (authenticated) receipt for these, so
# opaque sentinels suffice — no real seal/packet value is used.
_SEAL_FP = "synthetic-two-role-seal-fingerprint"
_PACKET_FP = "synthetic-execution-packet-fingerprint"
_GATE_FP = "synthetic-structural-gate-fingerprint"
_PARTITION_FP = "synthetic-partition-use-policy-fingerprint"


def _timestamp(index: int) -> str:
    return (datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(hours=index)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _write_cut(
    tmp_path: Path,
    *,
    n_bars: int = 400,
    close_overrides: dict[int, str | float] | None = None,
    funding_rows: list[tuple[int, str | float]] | None = None,
    canonical_funding_columns: bool = True,
    extra_funding_columns: tuple[str, ...] = (),
    funding_time_header: str | None = None,
    funding_rate_header: str | None = None,
    drop_funding_time: bool = False,
    drop_funding_rate: bool = False,
    non_monotonic_bar_index: int | None = None,
) -> tuple[Path, Path]:
    bars_dir = tmp_path / "bars"
    funding_dir = tmp_path / "funding"
    bars_dir.mkdir(parents=True)
    funding_dir.mkdir(parents=True)
    close_overrides = close_overrides or {}
    with open(bars_dir / "BTC.csv", "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp", "close"])
        for index in range(n_bars):
            ts = _timestamp(index)
            if non_monotonic_bar_index is not None and index == non_monotonic_bar_index:
                ts = _timestamp(index - 2)  # break strict hourly monotonicity
            writer.writerow([ts, close_overrides.get(index, 100)])

    time_name = funding_time_header or ("fundingTime" if canonical_funding_columns else "timestamp")
    rate_name = funding_rate_header or ("fundingRate" if canonical_funding_columns else "funding_rate")
    header: list[str] = []
    if not drop_funding_time:
        header.append(time_name)
    if not drop_funding_rate:
        header.append(rate_name)
    header.extend(extra_funding_columns)
    with open(funding_dir / "BTC.csv", "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for index, rate in funding_rows or [(100, "0.01")]:
            row: list[str] = []
            if not drop_funding_time:
                row.append(_timestamp(index))
            if not drop_funding_rate:
                row.append(str(rate))
            row.extend(["x"] * len(extra_funding_columns))
            writer.writerow(row)
    return bars_dir, funding_dir


def _split(boundary: int = BOUNDARY) -> dict[str, object]:
    return {
        "leakage_audit_killed": False,
        "boundary_index": boundary,
        "declared_purge_intervals": 8,
        "declared_embargo_intervals": 90,
    }


def _first_stat_registry(bars: Path, funding: Path) -> dict[str, object]:
    declaration = {
        "candidate_definition": dict(subject._FIRST_CANDIDATE_DEFINITION),
        "null_definition": dict(subject._FIRST_NULL_DEFINITION),
        "statistic_definition": dict(subject._FIRST_STATISTIC_DEFINITION),
        "candidate_rule_fingerprint": subject._FIRST_CANDIDATE_RULE_FINGERPRINT,
        "null_rule_fingerprint": subject._FIRST_NULL_RULE_FINGERPRINT,
        "statistic_rule_fingerprint": subject._FIRST_STATISTIC_RULE_FINGERPRINT,
        "registered_before_execution": True,
        "data_cut_fingerprint": subject._first_statistic_bound_fingerprint(
            bars / "BTC.csv", funding / "BTC.csv"
        ),
    }
    return {subject.FIRST_COMPUTED_STATISTIC_VERSION: declaration}


def _run_scorer(bars: Path, funding: Path, split: dict[str, object]) -> dict[str, object]:
    return subject.build_first_computed_statistic_v0(
        bars_dir=bars,
        funding_dir=funding,
        registry_entry=_first_stat_registry(bars, funding),
        split_audit=split,
        holdout_open_gate=None,
    )


def _frozen_fingerprints(bars: Path, funding: Path, boundary: int) -> dict[str, str]:
    bars_file = bars / "BTC.csv"
    funding_file = funding / "BTC.csv"
    return {
        "outer_data_cut": subject._data_cut_fingerprint(
            [("bars/BTC.csv", bars_file), ("funding/BTC.csv", funding_file)]
        ),
        "nested_first_statistic_data_binding": subject._first_statistic_bound_fingerprint(
            bars_file, funding_file
        ),
        "candidate_rule_fingerprint": subject._FIRST_CANDIDATE_RULE_FINGERPRINT,
        "null_rule_fingerprint": subject._FIRST_NULL_RULE_FINGERPRINT,
        "statistic_fingerprint": subject._FIRST_STATISTIC_RULE_FINGERPRINT,
        "split_fingerprint": subject._hash_split_boundary_declaration(boundary, 8, 90),
        "two_role_seal": _SEAL_FP,
        "execution_packet": _PACKET_FP,
        "structural_gate": _GATE_FP,
        "partition_use_policy": _PARTITION_FP,
    }


def _synthetic_receipt(scorer: dict[str, object], fingerprints: dict[str, str], boundary: int) -> bytes:
    receipt = {
        "protocol_computed_validation": {
            "immutable_data_cut": {"actual_sha256": fingerprints["outer_data_cut"]},
            "deterministic_split_audit": {
                "boundary_index": boundary,
                "declared_purge_intervals": 8,
                "declared_embargo_intervals": 90,
            },
            "holdout_seal_audit": {"holdout_seal_fingerprint": fingerprints["two_role_seal"]},
            "execution_packet_lock": {
                "execution_packet_fingerprint": fingerprints["execution_packet"]
            },
            "holdout_open_gate": {"holdout_open_gate_fingerprint": fingerprints["structural_gate"]},
            "partition_use_policy_v0": {
                "partition_use_policy_fingerprint": fingerprints["partition_use_policy"]
            },
            "first_computed_statistic_v0": {
                "statistic_name": scorer["statistic_name"],
                "candidate_name": scorer["candidate_name"],
                "null_name": scorer["null_name"],
                "statistic_value_T": scorer["statistic_value_T"],
                "scored_slot_count": scorer["scored_slot_count"],
                "invalid_slot_count": scorer["invalid_slot_count"],
                "data_cut_fingerprint": fingerprints["nested_first_statistic_data_binding"],
                "candidate_rule_fingerprint": fingerprints["candidate_rule_fingerprint"],
                "null_rule_fingerprint": fingerprints["null_rule_fingerprint"],
            },
        }
    }
    return json.dumps(receipt).encode("utf-8")


def _registry_entry(scorer: dict[str, object], fingerprints: dict[str, str], receipt_bytes: bytes) -> dict[str, object]:
    return {
        "protocol_id": subject.CANDIDATE1_DECOMPOSITION_PROTOCOL_ID,
        "source_quarantine_state": "sealed",
        "quarantine_access": "forbidden",
        "allowed_partition": "exact_source_non_quarantine_scored_slot_universe_only",
        "source_binding": {
            "archived_receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
            "source_statistic_name": scorer["statistic_name"],
            "source_candidate_name": scorer["candidate_name"],
            "source_null_name": scorer["null_name"],
            "source_statistic_value_T": scorer["statistic_value_T"],
            "source_scored_slot_count": scorer["scored_slot_count"],
            "source_invalid_slot_count": scorer["invalid_slot_count"],
        },
        "frozen_fingerprints": dict(fingerprints),
        "exact_decomposition_universe": {
            "scored_slot_count": scorer["scored_slot_count"],
            "invalid_slot_count": scorer["invalid_slot_count"],
            "reconstruction_requirement": {
                "reconstructed_statistic_value_T": scorer["statistic_value_T"],
            },
        },
    }


def _case(tmp_path: Path, *, boundary: int = BOUNDARY, **cut_kwargs) -> dict[str, object]:
    bars, funding = _write_cut(tmp_path, **cut_kwargs)
    split = _split(boundary)
    scorer = _run_scorer(bars, funding, split)
    assert scorer["statistic_state"] == "computed", scorer
    fingerprints = _frozen_fingerprints(bars, funding, boundary)
    receipt_bytes = _synthetic_receipt(scorer, fingerprints, boundary)
    registry = _registry_entry(scorer, fingerprints, receipt_bytes)
    return {
        "bars": bars,
        "funding": funding,
        "split": split,
        "scorer": scorer,
        "fingerprints": fingerprints,
        "receipt_bytes": receipt_bytes,
        "registry": registry,
    }


def _decompose(case: dict[str, object], **overrides) -> dict[str, object]:
    return subject.build_candidate1_train_mechanism_decomposition_v0(
        bars_dir=overrides.get("bars", case["bars"]),
        funding_dir=overrides.get("funding", case["funding"]),
        registry_entry=overrides.get("registry", case["registry"]),
        split_audit=overrides.get("split", case["split"]),
        holdout_open_gate=overrides.get("gate", None),
        source_receipt_bytes=overrides.get("receipt_bytes", case["receipt_bytes"]),
    )


# ── Component signs and separation ──────────────────────────────────────────


def test_positive_candidate_price_component(tmp_path: Path) -> None:
    case = _case(
        tmp_path,
        close_overrides={101: 100, 109: 110},
        funding_rows=[(100, "-0.01")],  # long, single active slot
    )
    result = _decompose(case)
    assert result["decomposition_state"] == "computed"
    assert result["outputs"]["mean_candidate_price_component"] > 0


def test_negative_candidate_price_component(tmp_path: Path) -> None:
    case = _case(
        tmp_path,
        close_overrides={101: 100, 109: 90},
        funding_rows=[(100, "-0.01")],  # long, price falls
    )
    result = _decompose(case)
    assert result["outputs"]["mean_candidate_price_component"] < 0


def test_positive_funding_component(tmp_path: Path) -> None:
    case = _case(tmp_path, funding_rows=[(100, "0.01"), (104, "0.05")])
    assert _decompose(case)["outputs"]["mean_candidate_funding_component"] > 0


def test_negative_funding_component(tmp_path: Path) -> None:
    case = _case(tmp_path, funding_rows=[(100, "0.01"), (104, "-0.05")])
    assert _decompose(case)["outputs"]["mean_candidate_funding_component"] < 0


def test_zero_funding_component(tmp_path: Path) -> None:
    case = _case(tmp_path, funding_rows=[(100, "0.01")])  # no in-window funding
    assert _decompose(case)["outputs"]["mean_candidate_funding_component"] == 0


def test_candidate_and_null_same_side_zero_relative_price(tmp_path: Path) -> None:
    # Single active slot: null starts +1; a long candidate is the same side.
    case = _case(
        tmp_path,
        close_overrides={101: 100, 109: 110},
        funding_rows=[(100, "-0.01")],
    )
    assert _decompose(case)["outputs"]["mean_relative_price_component"] == 0


def test_candidate_and_null_opposite_side_nonzero_relative_price(tmp_path: Path) -> None:
    # Single active slot: null +1, candidate short (-1) => opposite sides.
    case = _case(
        tmp_path,
        close_overrides={101: 100, 109: 110},
        funding_rows=[(100, "0.01")],
    )
    result = _decompose(case)
    assert result["outputs"]["mean_relative_price_component"] == pytest.approx(-0.2)


def test_flat_slot_and_null_alternation_not_advanced_by_flat(tmp_path: Path) -> None:
    # active(short) / flat / active(short), identical +0.1 price move each.
    case = _case(
        tmp_path,
        close_overrides={101: 100, 109: 110, 121: 100, 129: 110, 141: 100, 149: 110},
        funding_rows=[(100, "0.01"), (120, "0"), (140, "0.01")],
    )
    outputs = _decompose(case)["outputs"]
    # Null sides on the two active slots are +1 then -1 (flat did not advance
    # the alternation). Slot1 relative_price = (-1-1)*0.1 = -0.2, slot3 =
    # (-1-(-1))*0.1 = 0, flat = 0 => mean = -0.2/3. If flat HAD advanced,
    # slot3 null would be +1 and the mean would be -0.4/3.
    assert outputs["mean_relative_price_component"] == pytest.approx(-0.2 / 3)
    assert outputs["candidate_active_slot_count"] == 2
    assert outputs["candidate_flat_slot_count"] == 1
    assert outputs["scored_slot_count"] == 3


def test_identical_active_costs_produce_exact_zero_relative_cost_difference(tmp_path: Path) -> None:
    case = _case(tmp_path, funding_rows=[(100, "0.01"), (120, "-0.02"), (140, "0.03")])
    outputs = _decompose(case)["outputs"]
    assert outputs["mean_relative_cost_difference"] == 0
    assert outputs["candidate_active_slot_count"] > 0  # costs actually applied


def test_activity_matched_always_long_and_short_benchmarks(tmp_path: Path) -> None:
    # Single active short slot, price up 0.1. Always-long net = 0.1 - cost;
    # always-short net = -0.1 - cost. Both use the candidate active mask/cost.
    case = _case(
        tmp_path,
        close_overrides={101: 100, 109: 110},
        funding_rows=[(100, "0.01")],
    )
    outputs = _decompose(case)["outputs"]
    cost = float(subject.FIRST_COMPUTED_ROUND_TRIP_COST)
    assert outputs["mean_activity_matched_always_long_net"] == pytest.approx(0.1 - cost)
    assert outputs["mean_activity_matched_always_short_net"] == pytest.approx(-0.1 - cost)
    assert outputs["flat_benchmark_net"] == 0


def test_benchmarks_remain_flat_where_candidate_is_flat(tmp_path: Path) -> None:
    # Two flat slots only: no active slot => benchmarks average to exactly 0.
    case = _case(tmp_path, funding_rows=[(100, "0"), (120, "0")])
    outputs = _decompose(case)["outputs"]
    assert outputs["candidate_active_slot_count"] == 0
    assert outputs["mean_activity_matched_always_long_net"] == 0
    assert outputs["mean_activity_matched_always_short_net"] == 0
    assert outputs["mean_candidate_cost_drag"] == 0


def test_active_plus_flat_equals_scored(tmp_path: Path) -> None:
    case = _case(
        tmp_path,
        funding_rows=[(100, "0.01"), (120, "0"), (140, "-0.02"), (160, "0")],
    )
    outputs = _decompose(case)["outputs"]
    assert (
        outputs["candidate_active_slot_count"] + outputs["candidate_flat_slot_count"]
        == outputs["scored_slot_count"]
    )


# ── Reconstruction ──────────────────────────────────────────────────────────


def test_exact_known_synthetic_reconstruction_of_T(tmp_path: Path) -> None:
    # Single short slot, price up 0.1, no funding: relative_net = -0.2 exactly.
    case = _case(
        tmp_path,
        close_overrides={101: 100, 109: 110},
        funding_rows=[(100, "0.01")],
    )
    outputs = _decompose(case)["outputs"]
    assert outputs["reconstructed_statistic_value_T"] == -0.2


def test_reconstructed_T_equals_scorer_T_on_same_cut(tmp_path: Path) -> None:
    case = _case(
        tmp_path,
        close_overrides={101: 100, 109: 110, 121: 105, 129: 95},
        funding_rows=[(100, "0.01"), (120, "-0.02"), (140, "0"), (160, "0.03")],
    )
    result = _decompose(case)
    assert result["outputs"]["reconstructed_statistic_value_T"] == case["scorer"]["statistic_value_T"]
    assert result["outputs"]["scored_slot_count"] == case["scorer"]["scored_slot_count"]
    assert result["outputs"]["invalid_slot_count"] == case["scorer"]["invalid_slot_count"]


def test_deterministic_repeatability(tmp_path: Path) -> None:
    case = _case(tmp_path, funding_rows=[(100, "0.01"), (120, "-0.02")])
    assert _decompose(case) == _decompose(case)


# ── Classification ──────────────────────────────────────────────────────────


def test_classification_absolute_net_nonpositive(tmp_path: Path) -> None:
    # Short slot with rising price => candidate_net = -0.1 - cost < 0.
    case = _case(
        tmp_path,
        close_overrides={101: 100, 109: 110},
        funding_rows=[(100, "0.01")],
    )
    result = _decompose(case)
    assert result["outputs"]["mean_candidate_net"] <= 0
    assert result["classification"] == subject.CANDIDATE_1_ABSOLUTE_NET_NONPOSITIVE


def test_classification_net_positive_relative_price_nonpositive(tmp_path: Path) -> None:
    # Long candidate, same side as null => relative_price == 0; large price gain
    # makes absolute candidate_net positive.
    case = _case(
        tmp_path,
        close_overrides={101: 100, 109: 130},
        funding_rows=[(100, "-0.01")],
    )
    result = _decompose(case)
    outputs = result["outputs"]
    assert outputs["mean_candidate_net"] > 0
    assert outputs["mean_relative_price_component"] <= 0
    assert (
        result["classification"]
        == subject.CANDIDATE_1_ABSOLUTE_NET_POSITIVE_RELATIVE_PRICE_NONPOSITIVE
    )


def test_classification_net_and_relative_price_positive(tmp_path: Path) -> None:
    # Two active slots so null sides are +1 then -1; make the null-(-1) slot the
    # profitable long so candidate long beats null short on price there.
    case = _case(
        tmp_path,
        close_overrides={101: 100, 109: 101, 121: 100, 129: 140},
        funding_rows=[(100, "-0.01"), (120, "-0.01")],
    )
    result = _decompose(case)
    outputs = result["outputs"]
    assert outputs["mean_candidate_net"] > 0
    assert outputs["mean_relative_price_component"] > 0
    assert (
        result["classification"]
        == subject.CANDIDATE_1_ABSOLUTE_NET_AND_RELATIVE_PRICE_POSITIVE
    )


# ── Source authentication and contract ──────────────────────────────────────


def test_source_receipt_sha256_mismatch_blocks(tmp_path: Path) -> None:
    case = _case(tmp_path)
    registry = json.loads(json.dumps(case["registry"]))
    registry["source_binding"]["archived_receipt_sha256"] = "0" * 64
    result = _decompose(case, registry=registry)
    assert result["decomposition_state"] == "blocked"
    assert "source_receipt_sha256_mismatch" in result["reason_codes"]


def test_malformed_source_receipt_json_blocks(tmp_path: Path) -> None:
    case = _case(tmp_path)
    bad = b"{not valid json"
    registry = json.loads(json.dumps(case["registry"]))
    registry["source_binding"]["archived_receipt_sha256"] = hashlib.sha256(bad).hexdigest()
    result = _decompose(case, registry=registry, receipt_bytes=bad)
    assert result["decomposition_state"] == "blocked"
    assert "source_receipt_malformed_json" in result["reason_codes"]


def test_source_scored_slot_count_mismatch_blocks(tmp_path: Path) -> None:
    case = _case(tmp_path, funding_rows=[(100, "0.01"), (120, "-0.02")])
    registry = json.loads(json.dumps(case["registry"]))
    registry["source_binding"]["source_scored_slot_count"] = 999
    result = _decompose(case, registry=registry)
    assert result["decomposition_state"] == "blocked"
    assert "source_scored_slot_count_mismatch" in result["reason_codes"]


def test_source_invalid_slot_count_mismatch_blocks(tmp_path: Path) -> None:
    case = _case(tmp_path, funding_rows=[(100, "0.01"), (205, "0.01")])
    registry = json.loads(json.dumps(case["registry"]))
    registry["source_binding"]["source_invalid_slot_count"] = 999
    result = _decompose(case, registry=registry)
    assert result["decomposition_state"] == "blocked"
    assert "source_invalid_slot_count_mismatch" in result["reason_codes"]


@pytest.mark.parametrize(
    ("field", "reason"),
    [
        ("source_statistic_name", "source_statistic_name_mismatch"),
        ("source_candidate_name", "source_candidate_name_mismatch"),
        ("source_null_name", "source_null_name_mismatch"),
        ("source_statistic_value_T", "source_statistic_value_T_mismatch"),
    ],
)
def test_source_name_and_statistic_mismatch_blocks(tmp_path: Path, field: str, reason: str) -> None:
    case = _case(tmp_path)
    registry = json.loads(json.dumps(case["registry"]))
    registry["source_binding"][field] = "TAMPERED"
    result = _decompose(case, registry=registry)
    assert result["decomposition_state"] == "blocked"
    assert reason in result["reason_codes"]


@pytest.mark.parametrize(
    ("key", "reason"),
    [
        ("candidate_rule_fingerprint", "candidate_rule_fingerprint_mismatch"),
        ("null_rule_fingerprint", "null_rule_fingerprint_mismatch"),
        ("statistic_fingerprint", "statistic_fingerprint_mismatch"),
        ("nested_first_statistic_data_binding", "nested_data_binding_fingerprint_mismatch"),
        ("outer_data_cut", "outer_data_cut_fingerprint_mismatch"),
        ("split_fingerprint", "split_fingerprint_mismatch"),
        ("two_role_seal", "two_role_seal_mismatch"),
        ("execution_packet", "execution_packet_fingerprint_mismatch"),
        ("structural_gate", "structural_gate_fingerprint_mismatch"),
        ("partition_use_policy", "partition_use_policy_fingerprint_mismatch"),
    ],
)
def test_each_frozen_fingerprint_mismatch_blocks(tmp_path: Path, key: str, reason: str) -> None:
    case = _case(tmp_path)
    registry = json.loads(json.dumps(case["registry"]))
    registry["frozen_fingerprints"][key] = "deadbeef" * 8
    result = _decompose(case, registry=registry)
    assert result["decomposition_state"] == "blocked"
    assert reason in result["reason_codes"]


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("source_quarantine_state", "open", "quarantine_state_not_sealed"),
        ("quarantine_access", "allowed", "quarantine_access_not_forbidden"),
        ("allowed_partition", "everything", "allowed_partition_mismatch"),
    ],
)
def test_quarantine_and_partition_contract_blocks(tmp_path: Path, field: str, value: str, reason: str) -> None:
    case = _case(tmp_path)
    registry = json.loads(json.dumps(case["registry"]))
    registry[field] = value
    result = _decompose(case, registry=registry)
    assert result["decomposition_state"] == "blocked"
    assert reason in result["reason_codes"]


def test_source_slot_universe_mismatch_blocks(tmp_path: Path) -> None:
    case = _case(tmp_path)
    registry = json.loads(json.dumps(case["registry"]))
    registry["exact_decomposition_universe"]["scored_slot_count"] = 12345
    result = _decompose(case, registry=registry)
    assert result["decomposition_state"] == "blocked"
    assert "source_slot_universe_mismatch" in result["reason_codes"]


# ── Output-schema closure and forbidden outputs ─────────────────────────────


def test_success_output_has_exactly_nineteen_frozen_keys(tmp_path: Path) -> None:
    case = _case(tmp_path)
    outputs = _decompose(case)["outputs"]
    assert set(outputs) == subject._DECOMPOSITION_OUTPUT_KEYS
    assert len(outputs) == 19


def test_output_closure_rejects_missing_key(tmp_path: Path) -> None:
    outputs = {k: 0 for k in subject._DECOMPOSITION_OUTPUT_KEYS}
    outputs.pop("mean_candidate_net")
    reasons = subject._validate_decomposition_output_closure(outputs)
    assert "missing_success_output_key" in reasons


def test_output_closure_rejects_unexpected_key(tmp_path: Path) -> None:
    outputs = {k: 0 for k in subject._DECOMPOSITION_OUTPUT_KEYS}
    outputs["surprise"] = 1
    reasons = subject._validate_decomposition_output_closure(outputs)
    assert "unexpected_success_output_key" in reasons


@pytest.mark.parametrize(
    "forbidden",
    ["sharpe_ratio", "return_series", "t_statistic", "equity_curve", "p_value", "per_slot_returns"],
)
def test_prohibited_key_recursive_rejection(forbidden: str) -> None:
    with pytest.raises(ValueError, match="Forbidden decomposition output key"):
        subject._assert_no_forbidden_decomposition_outputs(
            {"outputs": {"nested": {forbidden: 1.0}}}
        )


def test_success_result_contains_no_forbidden_keys(tmp_path: Path) -> None:
    case = _case(tmp_path)
    result = _decompose(case)
    # Should not raise: the whole returned structure is clean.
    subject._assert_no_forbidden_decomposition_outputs(result)


# ── Quarantine sealed: poison sentinels are never decoded ────────────────────


def test_quarantine_poison_bars_never_read(tmp_path: Path) -> None:
    # Poison close cells sit strictly beyond the split boundary (holdout side).
    # If the decomposition decoded them, Decimal("POISON") would raise; success
    # therefore proves those rows were never read.
    poison = {index: "POISON" for index in range(BOUNDARY + 5, BOUNDARY + 40)}
    case = _case(
        tmp_path,
        close_overrides={**poison, 101: 100, 109: 110},
        funding_rows=[(100, "0.01")],
    )
    result = _decompose(case)
    assert result["decomposition_state"] == "computed"
    assert result["outputs"]["scored_slot_count"] == 1


def test_quarantine_poison_funding_never_read(tmp_path: Path) -> None:
    # Poison funding rate sits at a timestamp beyond the last train bar; the
    # semantic reader breaks before decoding it. Non-poison rows precede it.
    case = _case(
        tmp_path,
        funding_rows=[(100, "0.01"), (BOUNDARY + 30, "POISON")],
    )
    result = _decompose(case)
    assert result["decomposition_state"] == "computed"
    assert result["outputs"]["scored_slot_count"] == 1


# ── Malformed / structural funding & bars failures ──────────────────────────


def test_missing_funding_time_field_blocks(tmp_path: Path) -> None:
    bars, funding = _write_cut(tmp_path, drop_funding_time=True)
    result = _blocked_from_raw(bars, funding)
    assert result["decomposition_state"] == "blocked"


def test_missing_funding_rate_field_blocks(tmp_path: Path) -> None:
    bars, funding = _write_cut(tmp_path, drop_funding_rate=True)
    result = _blocked_from_raw(bars, funding)
    assert result["decomposition_state"] == "blocked"


def test_ambiguous_funding_columns_block(tmp_path: Path) -> None:
    bars, funding = _write_cut(tmp_path, extra_funding_columns=("timestamp", "funding_rate"))
    result = _blocked_from_raw(bars, funding)
    assert "funding_columns_ambiguous" in result["reason_codes"]


def test_malformed_funding_timestamp_blocks(tmp_path: Path) -> None:
    bars, funding = _write_cut(tmp_path)
    _overwrite_funding(funding, [("not-a-time", "0.01")])
    result = _blocked_from_raw(bars, funding)
    assert result["decomposition_state"] == "blocked"


def test_malformed_funding_rate_blocks(tmp_path: Path) -> None:
    bars, funding = _write_cut(tmp_path, funding_rows=[(100, "not-a-rate")])
    result = _blocked_from_raw(bars, funding)
    assert result["decomposition_state"] == "blocked"


def test_non_monotonic_bars_timestamps_block(tmp_path: Path) -> None:
    bars, funding = _write_cut(tmp_path, non_monotonic_bar_index=150)
    result = _blocked_from_raw(bars, funding)
    assert "bars_not_strict_hourly_sequence" in result["reason_codes"]


def test_non_monotonic_funding_timestamps_block(tmp_path: Path) -> None:
    bars, funding = _write_cut(tmp_path)
    _overwrite_funding(funding, [(120, "0.01"), (100, "0.01")], canonical=True)
    result = _blocked_from_raw(bars, funding)
    assert "funding_times_not_strictly_increasing" in result["reason_codes"]


def _overwrite_funding(funding: Path, rows: list[tuple], *, canonical: bool = True) -> None:
    header = ["fundingTime", "fundingRate"] if canonical else ["timestamp", "funding_rate"]
    with open(funding / "BTC.csv", "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for index, rate in rows:
            ts = index if isinstance(index, str) else _timestamp(index)
            writer.writerow([ts, rate])


def _blocked_from_raw(bars: Path, funding: Path) -> dict[str, object]:
    """Decompose a structurally-broken cut with a self-consistent contract.

    The source contract is built to authenticate cleanly (so the block comes
    from slot materialization, not the contract), using placeholder source
    counts/T that would only matter on a successful cut.
    """
    fingerprints = _frozen_fingerprints(bars, funding, BOUNDARY)
    scorer_like = {
        "statistic_name": subject.FIRST_COMPUTED_STATISTIC_NAME,
        "candidate_name": subject.FIRST_COMPUTED_CANDIDATE_NAME,
        "null_name": subject.FIRST_COMPUTED_NULL_NAME,
        "statistic_value_T": 0.0,
        "scored_slot_count": 1,
        "invalid_slot_count": 0,
    }
    receipt_bytes = _synthetic_receipt(scorer_like, fingerprints, BOUNDARY)
    registry = _registry_entry(scorer_like, fingerprints, receipt_bytes)
    return subject.build_candidate1_train_mechanism_decomposition_v0(
        bars_dir=bars,
        funding_dir=funding,
        registry_entry=registry,
        split_audit=_split(),
        holdout_open_gate=None,
        source_receipt_bytes=receipt_bytes,
    )


# ── Purge / embargo / quarantine boundary crossings & warmup ────────────────


def test_slot_crossing_purge_boundary_is_invalid(tmp_path: Path) -> None:
    # allowed_end = boundary - purge - 1 = 211; a decision at 205 exits at 214.
    case = _case(tmp_path, funding_rows=[(100, "0.01"), (205, "0.01")])
    outputs = _decompose(case)["outputs"]
    assert outputs["scored_slot_count"] == 1
    assert outputs["invalid_slot_count"] == 1


def test_slot_requiring_holdout_bars_is_invalid_and_unread(tmp_path: Path) -> None:
    # A decision near the boundary would need bars in the sealed holdout; it is
    # classified invalid and the holdout bars are never dereferenced (poison).
    poison = {index: "POISON" for index in range(BOUNDARY, BOUNDARY + 30)}
    case = _case(
        tmp_path,
        close_overrides={**poison, 101: 100, 109: 110},
        funding_rows=[(100, "0.01"), (215, "0.01")],
    )
    outputs = _decompose(case)["outputs"]
    assert outputs["scored_slot_count"] == 1
    assert outputs["invalid_slot_count"] == 1


def test_warmup_invalid_slot_preservation(tmp_path: Path) -> None:
    # A decision before warmup (index 80 => entry 81 < 90) is invalid.
    case = _case(tmp_path, funding_rows=[(80, "0.01"), (100, "0.01")])
    outputs = _decompose(case)["outputs"]
    assert outputs["scored_slot_count"] == 1
    assert outputs["invalid_slot_count"] == 1


# ── Input immutability & read-only access ───────────────────────────────────


def test_input_files_remain_byte_identical_and_no_files_created(tmp_path: Path) -> None:
    case = _case(tmp_path, funding_rows=[(100, "0.01"), (120, "-0.02")])
    bars_file = case["bars"] / "BTC.csv"
    funding_file = case["funding"] / "BTC.csv"
    before = {
        bars_file: bars_file.read_bytes(),
        funding_file: funding_file.read_bytes(),
    }
    before_listing = sorted(p.name for p in case["bars"].iterdir()) + sorted(
        p.name for p in case["funding"].iterdir()
    )
    _decompose(case)
    assert bars_file.read_bytes() == before[bars_file]
    assert funding_file.read_bytes() == before[funding_file]
    after_listing = sorted(p.name for p in case["bars"].iterdir()) + sorted(
        p.name for p in case["funding"].iterdir()
    )
    assert before_listing == after_listing


def test_no_write_mode_opened_against_source_inputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    case = _case(tmp_path, funding_rows=[(100, "0.01"), (120, "-0.02")])
    input_root = str(tmp_path.resolve())
    real_open = builtins.open
    offenders: list[tuple[str, str]] = []

    def guarded_open(file, mode="r", *args, **kwargs):
        try:
            resolved = str(Path(file).resolve())
        except TypeError:
            resolved = ""
        if resolved.startswith(input_root) and any(flag in mode for flag in ("w", "a", "x", "+")):
            offenders.append((resolved, mode))
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded_open)
    result = _decompose(case)
    assert result["decomposition_state"] == "computed"
    assert offenders == []
