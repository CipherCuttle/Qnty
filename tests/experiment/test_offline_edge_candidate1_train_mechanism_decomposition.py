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
from decimal import Decimal
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

# Synthetic stand-ins for the archived artifact hashes. The core requires these
# fields to be structurally present but must NOT claim to authenticate their
# bytes: only the receipt bytes are an input here. Artifact-byte authentication
# belongs to the later no-computation preflight.
_SYNTHETIC_REPO_HEAD = "1" * 40
_SYNTHETIC_IMPL_SHA = "2" * 40
_SYNTHETIC_COMMAND_SHA = "3" * 64
_SYNTHETIC_LOG_SHA = "4" * 64
_SYNTHETIC_EXIT_CODE_SHA = "5" * 64

# The frozen output schema and classification contract, spelled out independently
# of the module constants. Double entry is the point: if the implementation's
# frozen contract drifts from the preregistration, these literals fail.
_FROZEN_OUTPUT_SCHEMA = {
    "primary_outputs": [
        "mean_candidate_price_component",
        "mean_candidate_funding_component",
        "mean_candidate_cost_drag",
        "mean_candidate_net",
        "mean_relative_price_component",
        "mean_relative_funding_component",
        "mean_relative_cost_difference",
        "reconstructed_statistic_value_T",
    ],
    "secondary_outputs": [
        "mean_null_price_component",
        "mean_null_funding_component",
        "mean_null_cost_drag",
        "mean_null_net",
        "mean_activity_matched_always_long_net",
        "mean_activity_matched_always_short_net",
        "flat_benchmark_net",
        "scored_slot_count",
        "invalid_slot_count",
        "candidate_active_slot_count",
        "candidate_flat_slot_count",
    ],
    "flat_benchmark_net_fixed_value": 0,
    "activity_matched_benchmark_contract": {
        "use_candidate_1_exact_active_flat_mask": True,
        "remain_flat_where_candidate_1_flat": True,
        "same_entries_exits_funding_window_cost": True,
        "differ_only_in_side_assignment": True,
        "role": "regime_diagnostics_not_new_candidates",
    },
    "forbidden_outputs": [
        "per_slot_returns",
        "return_series",
        "cumulative_pnl",
        "equity_curve",
        "sharpe_ratio",
        "sortino_ratio",
        "drawdown",
        "hit_rate",
        "annualized_return",
        "p_value",
        "confidence_interval",
        "t_statistic",
        "bootstrap_result",
        "regime_split",
        "sensitivity_analysis",
        "alternative_hold_period",
        "alternative_cost",
        "funding_threshold",
        "candidate_variant",
        "quarantine_result",
    ],
    "no_random_side_ensemble": True,
    "no_receive_side_matched_ensemble": True,
    "ensembles_require_separate_preregistration_and_trial_accounting": True,
}

_CLASSIFICATION_CONTRACT = {
    "DECOMPOSITION_BLOCKED_OR_INVALID": {
        "use_when_any": [
            "source_receipt_cannot_be_authenticated",
            "source_slot_universe_differs",
            "slot_counts_differ",
            "original_T_cannot_be_reconstructed_exactly",
            "any_frozen_rule_or_fingerprint_differs",
            "quarantine_access_occurs",
            "output_schema_differs",
            "any_prohibited_calculation_occurs",
        ]
    },
    "CANDIDATE_1_ABSOLUTE_NET_NONPOSITIVE": {
        "condition": "mean_candidate_net <= 0",
        "interpretation": "diagnostic baseline only",
    },
    "CANDIDATE_1_ABSOLUTE_NET_POSITIVE_RELATIVE_PRICE_NONPOSITIVE": {
        "condition": "mean_candidate_net > 0 and mean_relative_price_component <= 0",
        "interpretation": "no price alpha claim",
    },
    "CANDIDATE_1_ABSOLUTE_NET_AND_RELATIVE_PRICE_POSITIVE": {
        "condition": "mean_candidate_net > 0 and mean_relative_price_component > 0",
        "interpretation": "eligible for a separately preregistered prospective test",
    },
    "no_percentage_contribution_threshold": True,
    "no_significance_inference": True,
}

_PER_SLOT_DEFINITIONS = {
    "candidate_price_i": "candidate_side_i * (exit_close_i / entry_close_i - 1)",
    "candidate_funding_i": (
        "-candidate_side_i * sum(funding_rates where entry_time_i < fundingTime <= exit_time_i)"
    ),
    "candidate_cost_i": "0.0022 when candidate is active, otherwise 0",
    "candidate_net_i": "candidate_price_i + candidate_funding_i - candidate_cost_i",
    "null_components": "null components use the frozen null side",
    "relative_price_i": "candidate_price_i - null_price_i",
    "relative_funding_i": "candidate_funding_i - null_funding_i",
    "relative_cost_difference_i": "candidate_cost_i - null_cost_i",
    "relative_net_i": "relative_price_i + relative_funding_i - relative_cost_difference_i",
    "fixed_cost_per_active_slot": 0.0022,
    "relative_cost_difference_expectation": "exactly zero; the executor MUST verify",
}

_EXECUTION_PRECONDITIONS = [
    "this_preregistration_pr_merged",
    "separate_implementation_pr_reviewed_and_merged",
    "implementation_fingerprint_or_commit_bound",
    "final_no_computation_preflight_passed",
]

_AUTHORIZATION_STATE = {
    "scientific_use_authorized": False,
    "paper_trade_authorized": False,
    "live_integration_authorized": False,
    "edge_status": "EDGE_UNPROVEN",
    "live_status": "BLOCK_LIVE_INTEGRATION",
}


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


def _synthetic_receipt(
    scorer: dict[str, object], fingerprints: dict[str, str], boundary: int
) -> bytes:
    """Build synthetic source-receipt bytes modelling the archived receipt's shape.

    Structural only: the states here are the ones the decomposition requires of
    an authenticated source receipt. No archived receipt is read.
    """
    receipt = {
        "protocol_computed_validation": {
            "immutable_data_cut": {"actual_sha256": fingerprints["outer_data_cut"]},
            "deterministic_split_audit": {
                "boundary_index": boundary,
                "declared_purge_intervals": 8,
                "declared_embargo_intervals": 90,
            },
            "holdout_seal_audit": {
                "holdout_seal_fingerprint": fingerprints["two_role_seal"],
                "holdout_seal_state": "sealed",
                "holdout_seal_killed": False,
                "sealed_roles": ["bars", "funding"],
                "projection_policy": "bars_timestamp_partition_projection_v1",
            },
            "execution_packet_lock": {
                "execution_packet_fingerprint": fingerprints["execution_packet"],
                "packet_lock_state": "locked",
                "packet_lock_killed": False,
            },
            "holdout_open_gate": {
                "holdout_open_gate_fingerprint": fingerprints["structural_gate"],
                "holdout_open_gate_state": "gate_passed",
                "holdout_open_gate_killed": False,
            },
            "partition_use_policy_v0": {
                "partition_use_policy_fingerprint": fingerprints["partition_use_policy"],
                "partition_use_policy_state": "quarantine_only",
                "partition_use_policy_killed": False,
                "scientific_use_authorized": False,
            },
            "first_computed_statistic_v0": {
                "statistic_name": scorer["statistic_name"],
                "candidate_name": scorer["candidate_name"],
                "null_name": scorer["null_name"],
                "statistic_value_T": scorer["statistic_value_T"],
                "scored_slot_count": scorer["scored_slot_count"],
                "invalid_slot_count": scorer["invalid_slot_count"],
                "statistic_state": "computed",
                "statistic_reason_codes": ["holdout_remained_sealed_non_holdout_scored"],
                "data_cut_fingerprint": fingerprints["nested_first_statistic_data_binding"],
                "candidate_rule_fingerprint": fingerprints["candidate_rule_fingerprint"],
                "null_rule_fingerprint": fingerprints["null_rule_fingerprint"],
            },
        }
    }
    return json.dumps(receipt).encode("utf-8")


def _registry_entry(
    scorer: dict[str, object], fingerprints: dict[str, str], receipt_bytes: bytes
) -> dict[str, object]:
    """A synthetic entry structurally modelling the full preregistration entry.

    Every field of the real entry is present with its preregistered value; only
    the data-dependent hashes and source outputs are synthetic.
    """
    return {
        "protocol_id": "real_btc_candidate1_train_mechanism_decomposition_v0",
        "registered_before_execution": True,
        "append_only": True,
        "decomposition_execution_budget": 1,
        "decomposition_execution_count": 0,
        "source_train_execution_consumed": True,
        "source_quarantine_state": "sealed",
        "allowed_partition": "exact_source_non_quarantine_scored_slot_universe_only",
        "quarantine_access": "forbidden",
        "source_binding": {
            "source_classification": "CANDIDATE_1_TRAIN_SMOKE_SURVIVED",
            "source_repo_head": _SYNTHETIC_REPO_HEAD,
            "bound_implementation_sha": _SYNTHETIC_IMPL_SHA,
            "archived_receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
            "archived_command_sha256": _SYNTHETIC_COMMAND_SHA,
            "archived_log_sha256": _SYNTHETIC_LOG_SHA,
            "archived_exit_code_sha256": _SYNTHETIC_EXIT_CODE_SHA,
            "archived_receipt_path": "synthetic/real_validation_receipt.json",
            "source_statistic_name": scorer["statistic_name"],
            "source_statistic_value_T": scorer["statistic_value_T"],
            "source_scored_slot_count": scorer["scored_slot_count"],
            "source_invalid_slot_count": scorer["invalid_slot_count"],
            "source_statistic_reason_code": "holdout_remained_sealed_non_holdout_scored",
            "source_candidate_name": scorer["candidate_name"],
            "source_null_name": scorer["null_name"],
        },
        "frozen_fingerprints": dict(fingerprints),
        "exact_decomposition_universe": {
            "must_reuse_without_change": [
                "scored_slots",
                "invalid_slots",
                "entry_timestamps",
                "exit_timestamps",
                "candidate_activity_mask",
                "candidate_sides",
                "null_sides",
                "funding_accounting_window",
                "cost_accounting",
                "warmup",
                "split",
                "purge",
                "embargo",
                "hold_period",
            ],
            "scored_slot_count": scorer["scored_slot_count"],
            "invalid_slot_count": scorer["invalid_slot_count"],
            "no_slot_added_removed_or_reclassified": True,
            "reconstruction_requirement": {
                "reconstructed_statistic_value_T": scorer["statistic_value_T"],
                "reconstructed_from": "component_means",
                "reconstruction_identity": "mean(relative_net_i)",
            },
        },
        "per_slot_definitions": json.loads(json.dumps(_PER_SLOT_DEFINITIONS)),
        "frozen_output_schema": json.loads(json.dumps(_FROZEN_OUTPUT_SCHEMA)),
        "classification_contract": json.loads(json.dumps(_CLASSIFICATION_CONTRACT)),
        "authorization_state": json.loads(json.dumps(_AUTHORIZATION_STATE)),
        "execution_preconditions": list(_EXECUTION_PRECONDITIONS),
    }


def _case(
    tmp_path: Path,
    *,
    boundary: int = BOUNDARY,
    source_values: dict[str, object] | None = None,
    **cut_kwargs,
) -> dict[str, object]:
    """Build a synthetic cut plus a self-consistent registry and receipt.

    ``source_values`` overrides the frozen source outputs bound into the registry
    and receipt. The golden fixture passes hand-calculated values so the source
    contract is specified independently of the scorer: if the scorer disagrees,
    the decomposition fails its reconstruction gate and the test fails loudly.
    """
    bars, funding = _write_cut(tmp_path, **cut_kwargs)
    split = _split(boundary)
    scorer = _run_scorer(bars, funding, split)
    assert scorer["statistic_state"] == "computed", scorer
    bound_source = dict(scorer)
    bound_source.update(source_values or {})
    fingerprints = _frozen_fingerprints(bars, funding, boundary)
    receipt_bytes = _synthetic_receipt(bound_source, fingerprints, boundary)
    registry = _registry_entry(bound_source, fingerprints, receipt_bytes)
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


_DELETE = object()


def _mutated(node: dict[str, object], path: tuple[str, ...], value: object) -> dict[str, object]:
    """Return a deep copy of ``node`` with ``path`` set to ``value`` (or removed)."""
    copied = json.loads(json.dumps(node))
    target = copied
    for key in path[:-1]:
        target = target[key]
    if value is _DELETE:
        target.pop(path[-1], None)
    else:
        target[path[-1]] = value
    return copied


def _receipt_mutation(case: dict[str, object], path: tuple[str, ...], value: object) -> dict[str, object]:
    """Mutate the source receipt and re-bind its hash so it still authenticates.

    Re-hashing is deliberate: it proves the block comes from the required state
    check rather than from the byte-authentication step.
    """
    receipt = json.loads(bytes(case["receipt_bytes"]).decode("utf-8"))
    receipt["protocol_computed_validation"] = _mutated(
        receipt["protocol_computed_validation"], path, value
    )
    receipt_bytes = json.dumps(receipt).encode("utf-8")
    registry = _mutated(
        case["registry"],
        ("source_binding", "archived_receipt_sha256"),
        hashlib.sha256(receipt_bytes).hexdigest(),
    )
    return {"registry": registry, "receipt_bytes": receipt_bytes}


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


# ── Golden decomposition fixture ────────────────────────────────────────────
#
# One small hand-calculated cut. Every expected value below is derived on paper
# from the frozen per-slot definitions and written as a literal; none is produced
# by calling the production decomposition helpers.
#
# Cost = 0.0022 per active slot, hold = 8 bars, warmup = 90, boundary = 220,
# purge = 8 => allowed slot range [90, 211]. A funding row at index i decides at
# ts(i), enters at bar i+1 and exits at bar i+9; its funding window is the rows
# strictly after ts(i+1) up to and including ts(i+9). Null sides alternate +1,
# -1, +1 across ACTIVE slots only.
#
#   rows: (100, -0.01) (102, +0.004) (120, +0.02) (140, 0)
#
#   slot 1  decide 100  rate -0.01 -> candidate +1 (long), null +1  (SAME side)
#           entry 101 (100.0) exit 109 (110.0) -> price delta +0.1
#           in-window funding: the +0.004 row at 102 -> funding 0.004
#           candidate: price +0.1, funding -0.004, cost 0.0022 => net  0.0938
#           null:      price +0.1, funding -0.004, cost 0.0022 => net  0.0938
#           relative:  price 0, funding 0, cost 0               => net  0
#           always_long  = +0.1 - 0.004 - 0.0022 =  0.0938
#           always_short = -0.1 + 0.004 - 0.0022 = -0.0982
#
#   slot 2  decide 102  rate +0.004 -> candidate -1 (short), null -1 (SAME side)
#           entry 103 (100.0) exit 111 (105.0) -> price delta +0.05, funding 0
#           candidate: price -0.05, funding 0, cost 0.0022 => net -0.0522
#           null:      price -0.05, funding 0, cost 0.0022 => net -0.0522
#           relative:  0 across the board
#           always_long  = +0.05 - 0.0022 =  0.0478
#           always_short = -0.05 - 0.0022 = -0.0522
#
#   slot 3  decide 120  rate +0.02 -> candidate -1 (short), null +1 (OPPOSITE)
#           entry 121 (100.0) exit 129 (95.0) -> price delta -0.05, funding 0
#           candidate: price +0.05, funding 0, cost 0.0022 => net  0.0478
#           null:      price -0.05, funding 0, cost 0.0022 => net -0.0522
#           relative:  price +0.1, funding 0, cost 0        => net  0.1
#           always_long  = -0.05 - 0.0022 = -0.0522
#           always_short = +0.05 - 0.0022 =  0.0478
#
#   slot 4  decide 140  rate 0 -> candidate flat, null flat
#           entry 141 (100.0) exit 149 (104.0) -> price delta +0.04, funding 0
#           flat slot: every component 0, no cost, benchmarks stay flat at 0.
#           (The price does move: this pins that a flat slot contributes nothing.)
#
#   means over n = 4 scored slots:
#     candidate price   = (0.1 - 0.05 + 0.05 + 0) / 4      =  0.025
#     candidate funding = (-0.004 + 0 + 0 + 0) / 4         = -0.001
#     candidate cost    = (0.0022 * 3 + 0) / 4             =  0.00165
#     candidate net     = 0.025 - 0.001 - 0.00165          =  0.02235
#     relative price    = (0 + 0 + 0.1 + 0) / 4            =  0.025
#     relative funding  = 0 ;  relative cost difference    =  0
#     T                 = 0.025 + 0 - 0                    =  0.025
#     null price        = (0.1 - 0.05 - 0.05 + 0) / 4      =  0
#     null funding      = -0.001 ; null cost = 0.00165
#     null net          = 0 - 0.001 - 0.00165              = -0.00265
#     always_long       = (0.0938 + 0.0478 - 0.0522 + 0)/4 =  0.02235
#     always_short      = (-0.0982 - 0.0522 + 0.0478 + 0)/4= -0.02565

_GOLDEN_CLOSES = {101: 100, 109: 110, 103: 100, 111: 105, 121: 100, 129: 95, 141: 100, 149: 104}
_GOLDEN_FUNDING = [(100, "-0.01"), (102, "0.004"), (120, "0.02"), (140, "0")]
_GOLDEN_SOURCE = {"statistic_value_T": 0.025, "scored_slot_count": 4, "invalid_slot_count": 0}

_GOLDEN_EXPECTED_OUTPUTS = {
    "mean_candidate_price_component": 0.025,
    "mean_candidate_funding_component": -0.001,
    "mean_candidate_cost_drag": 0.00165,
    "mean_candidate_net": 0.02235,
    "mean_relative_price_component": 0.025,
    "mean_relative_funding_component": 0.0,
    "mean_relative_cost_difference": 0.0,
    "reconstructed_statistic_value_T": 0.025,
    "mean_null_price_component": 0.0,
    "mean_null_funding_component": -0.001,
    "mean_null_cost_drag": 0.00165,
    "mean_null_net": -0.00265,
    "mean_activity_matched_always_long_net": 0.02235,
    "mean_activity_matched_always_short_net": -0.02565,
    "flat_benchmark_net": 0.0,
    "scored_slot_count": 4,
    "invalid_slot_count": 0,
    "candidate_active_slot_count": 3,
    "candidate_flat_slot_count": 1,
}


def _golden_case(tmp_path: Path) -> dict[str, object]:
    return _case(
        tmp_path,
        close_overrides=dict(_GOLDEN_CLOSES),
        funding_rows=list(_GOLDEN_FUNDING),
        source_values=dict(_GOLDEN_SOURCE),
    )


@pytest.mark.parametrize("key", sorted(_GOLDEN_EXPECTED_OUTPUTS))
def test_golden_fixture_exact_expected_output(tmp_path: Path, key: str) -> None:
    outputs = _decompose(_golden_case(tmp_path))["outputs"]
    assert outputs[key] == _GOLDEN_EXPECTED_OUTPUTS[key]


def test_golden_fixture_matches_all_nineteen_outputs_exactly(tmp_path: Path) -> None:
    result = _decompose(_golden_case(tmp_path))
    assert result["decomposition_state"] == "computed"
    assert result["outputs"] == _GOLDEN_EXPECTED_OUTPUTS
    assert len(_GOLDEN_EXPECTED_OUTPUTS) == 19


def test_golden_fixture_classification(tmp_path: Path) -> None:
    # candidate net 0.02235 > 0 and relative price 0.025 > 0.
    result = _decompose(_golden_case(tmp_path))
    assert result["classification"] == subject.CANDIDATE_1_ABSOLUTE_NET_AND_RELATIVE_PRICE_POSITIVE


def test_golden_fixture_scorer_agrees_with_hand_calculated_source(tmp_path: Path) -> None:
    # The hand-calculated T/counts are bound into the registry and receipt, so a
    # scorer that disagreed would have blocked the decomposition above. This
    # states the agreement directly.
    case = _golden_case(tmp_path)
    assert case["scorer"]["statistic_value_T"] == _GOLDEN_SOURCE["statistic_value_T"]
    assert case["scorer"]["scored_slot_count"] == _GOLDEN_SOURCE["scored_slot_count"]
    assert case["scorer"]["invalid_slot_count"] == _GOLDEN_SOURCE["invalid_slot_count"]


# ── Execution-critical registry contract: fail-closed matrix ────────────────


@pytest.mark.parametrize(
    ("path", "value", "reason"),
    [
        # Protocol identity and execution control.
        (("protocol_id",), "some_other_protocol_v9", "decomposition_protocol_id_mismatch"),
        (("protocol_id",), _DELETE, "decomposition_protocol_id_mismatch"),
        (
            ("registered_before_execution",),
            False,
            "decomposition_not_registered_before_execution",
        ),
        (
            ("registered_before_execution",),
            _DELETE,
            "decomposition_not_registered_before_execution",
        ),
        (("append_only",), False, "decomposition_registry_not_append_only"),
        (("append_only",), _DELETE, "decomposition_registry_not_append_only"),
        (
            ("decomposition_execution_budget",),
            2,
            "decomposition_execution_budget_mismatch",
        ),
        (
            ("decomposition_execution_budget",),
            _DELETE,
            "decomposition_execution_budget_mismatch",
        ),
        # The single budgeted execution is already spent.
        (
            ("decomposition_execution_count",),
            1,
            "decomposition_execution_budget_exhausted",
        ),
        (
            ("decomposition_execution_count",),
            _DELETE,
            "decomposition_execution_budget_exhausted",
        ),
        (
            ("source_train_execution_consumed",),
            False,
            "source_train_execution_not_consumed",
        ),
        (
            ("source_train_execution_consumed",),
            _DELETE,
            "source_train_execution_not_consumed",
        ),
        # Quarantine and partition.
        (("source_quarantine_state",), "open", "quarantine_state_not_sealed"),
        (("quarantine_access",), "allowed", "quarantine_access_not_forbidden"),
        (
            ("allowed_partition",),
            "exact_source_scored_slot_universe_plus_quarantine",
            "allowed_partition_mismatch",
        ),
        # Frozen source binding.
        (
            ("source_binding", "source_classification"),
            "CANDIDATE_1_TRAIN_SMOKE_KILLED",
            "source_classification_mismatch",
        ),
        (
            ("source_binding", "source_classification"),
            _DELETE,
            "source_classification_mismatch",
        ),
        (
            ("source_binding", "source_statistic_reason_code"),
            "holdout_opened_and_scored",
            "source_statistic_reason_code_mismatch",
        ),
        (
            ("source_binding", "source_statistic_reason_code"),
            _DELETE,
            "source_statistic_reason_code_mismatch",
        ),
        # Authorization state: this diagnostic authorizes nothing.
        (
            ("authorization_state", "scientific_use_authorized"),
            True,
            "scientific_use_authorization_not_false",
        ),
        (
            ("authorization_state", "paper_trade_authorized"),
            True,
            "paper_trade_authorization_not_false",
        ),
        (
            ("authorization_state", "live_integration_authorized"),
            True,
            "live_integration_authorization_not_false",
        ),
        (("authorization_state", "edge_status"), "EDGE_PROVEN", "edge_status_not_unproven"),
        (
            ("authorization_state", "live_status"),
            "ALLOW_LIVE_INTEGRATION",
            "live_status_not_blocked",
        ),
        (("authorization_state",), _DELETE, "decomposition_authorization_state_missing"),
        # Structural presence of the remaining preregistered blocks.
        (("execution_preconditions",), _DELETE, "execution_preconditions_missing"),
        (("per_slot_definitions",), _DELETE, "per_slot_definitions_missing"),
    ],
)
def test_registry_contract_fails_closed(
    tmp_path: Path, path: tuple[str, ...], value: object, reason: str
) -> None:
    case = _case(tmp_path)
    result = _decompose(case, registry=_mutated(case["registry"], path, value))
    assert result["decomposition_state"] == "blocked"
    assert result["classification"] == subject.DECOMPOSITION_BLOCKED_OR_INVALID
    assert reason in result["reason_codes"]
    assert result["outputs"] is None


@pytest.mark.parametrize("truthy", [1, "true", "yes"])
def test_boolean_flags_reject_truthy_non_booleans(tmp_path: Path, truthy: object) -> None:
    # A flag must be exactly True; a truthy stand-in must not satisfy it.
    case = _case(tmp_path)
    result = _decompose(
        case, registry=_mutated(case["registry"], ("registered_before_execution",), truthy)
    )
    assert "decomposition_not_registered_before_execution" in result["reason_codes"]


def test_execution_count_must_be_a_real_integer(tmp_path: Path) -> None:
    case = _case(tmp_path)
    result = _decompose(
        case, registry=_mutated(case["registry"], ("decomposition_execution_count",), 0.0)
    )
    assert "decomposition_execution_count_malformed" in result["reason_codes"]


# ── Authenticated source receipt: required frozen states ────────────────────


@pytest.mark.parametrize(
    ("path", "value", "reason"),
    [
        (
            ("first_computed_statistic_v0", "statistic_state"),
            "invalid",
            "source_statistic_state_not_computed",
        ),
        (
            ("first_computed_statistic_v0", "statistic_state"),
            _DELETE,
            "source_statistic_state_not_computed",
        ),
        (
            ("first_computed_statistic_v0", "statistic_reason_codes"),
            ["holdout_opened_and_scored"],
            "source_statistic_reason_code_mismatch",
        ),
        (
            ("first_computed_statistic_v0", "statistic_reason_codes"),
            ["holdout_remained_sealed_non_holdout_scored", "extra_code"],
            "source_statistic_reason_code_mismatch",
        ),
        (
            ("holdout_seal_audit", "holdout_seal_state"),
            "open",
            "source_holdout_seal_not_sealed",
        ),
        (
            ("holdout_seal_audit", "holdout_seal_killed"),
            True,
            "source_holdout_seal_killed",
        ),
        (
            ("holdout_seal_audit", "sealed_roles"),
            ["bars"],
            "source_sealed_roles_mismatch",
        ),
        (
            ("holdout_seal_audit", "sealed_roles"),
            ["funding", "bars"],
            "source_sealed_roles_mismatch",
        ),
        (
            ("holdout_seal_audit", "projection_policy"),
            "some_other_projection_v2",
            "source_projection_policy_mismatch",
        ),
        (
            ("execution_packet_lock", "packet_lock_state"),
            "mismatch",
            "source_packet_not_locked",
        ),
        (
            ("execution_packet_lock", "packet_lock_killed"),
            True,
            "source_packet_lock_killed",
        ),
        (
            ("holdout_open_gate", "holdout_open_gate_state"),
            "gate_blocked",
            "source_holdout_open_gate_not_passed",
        ),
        (
            ("holdout_open_gate", "holdout_open_gate_killed"),
            True,
            "source_holdout_open_gate_killed",
        ),
        (
            ("partition_use_policy_v0", "partition_use_policy_state"),
            "unrestricted",
            "source_partition_use_policy_not_quarantine_only",
        ),
        (
            ("partition_use_policy_v0", "partition_use_policy_killed"),
            True,
            "source_partition_use_policy_killed",
        ),
        (
            ("partition_use_policy_v0", "scientific_use_authorized"),
            True,
            "source_scientific_use_authorized",
        ),
    ],
)
def test_source_receipt_state_fails_closed(
    tmp_path: Path, path: tuple[str, ...], value: object, reason: str
) -> None:
    case = _case(tmp_path)
    result = _decompose(case, **_receipt_mutation(case, path, value))
    assert result["decomposition_state"] == "blocked"
    assert reason in result["reason_codes"]
    assert result["outputs"] is None


# ── Frozen output schema and classification contract ────────────────────────


def _schema_without(key: str) -> dict[str, object]:
    schema = json.loads(json.dumps(_FROZEN_OUTPUT_SCHEMA))
    schema.pop(key)
    return schema


def _outputs_without(key: str) -> list[str]:
    return [name for name in _FROZEN_OUTPUT_SCHEMA["primary_outputs"] if name != key]


@pytest.mark.parametrize(
    ("path", "value", "reason"),
    [
        # A primary output removed, renamed, reordered, or added.
        (
            ("frozen_output_schema", "primary_outputs"),
            _outputs_without("mean_candidate_net"),
            "frozen_output_schema_mismatch",
        ),
        (
            ("frozen_output_schema", "primary_outputs"),
            _FROZEN_OUTPUT_SCHEMA["primary_outputs"] + ["mean_bonus_component"],
            "frozen_output_schema_mismatch",
        ),
        (
            ("frozen_output_schema", "secondary_outputs"),
            _FROZEN_OUTPUT_SCHEMA["secondary_outputs"][:-1],
            "frozen_output_schema_mismatch",
        ),
        # A key removed from, or added to, the frozen schema itself.
        (("frozen_output_schema",), _schema_without("flat_benchmark_net_fixed_value"), "frozen_output_schema_mismatch"),
        (
            ("frozen_output_schema", "surprise_contract_field"),
            "anything",
            "frozen_output_schema_mismatch",
        ),
        (("frozen_output_schema",), _DELETE, "frozen_output_schema_missing"),
        # Fixed values and sub-contracts.
        (
            ("frozen_output_schema", "flat_benchmark_net_fixed_value"),
            1,
            "frozen_output_schema_mismatch",
        ),
        (
            ("frozen_output_schema", "activity_matched_benchmark_contract", "differ_only_in_side_assignment"),
            False,
            "frozen_output_schema_mismatch",
        ),
        (
            ("frozen_output_schema", "no_random_side_ensemble"),
            False,
            "frozen_output_schema_mismatch",
        ),
        (
            ("frozen_output_schema", "no_receive_side_matched_ensemble"),
            False,
            "frozen_output_schema_mismatch",
        ),
        (
            ("frozen_output_schema", "ensembles_require_separate_preregistration_and_trial_accounting"),
            False,
            "frozen_output_schema_mismatch",
        ),
        # The forbidden-output list is its own contract.
        (
            ("frozen_output_schema", "forbidden_outputs"),
            [name for name in _FROZEN_OUTPUT_SCHEMA["forbidden_outputs"] if name != "sharpe_ratio"],
            "forbidden_output_contract_mismatch",
        ),
        (
            ("frozen_output_schema", "forbidden_outputs"),
            _FROZEN_OUTPUT_SCHEMA["forbidden_outputs"] + ["newly_allowed_metric"],
            "forbidden_output_contract_mismatch",
        ),
        (("frozen_output_schema", "forbidden_outputs"), [], "forbidden_output_contract_mismatch"),
    ],
)
def test_frozen_output_schema_fails_closed(
    tmp_path: Path, path: tuple[str, ...], value: object, reason: str
) -> None:
    case = _case(tmp_path)
    result = _decompose(case, registry=_mutated(case["registry"], path, value))
    assert result["decomposition_state"] == "blocked"
    assert reason in result["reason_codes"]


@pytest.mark.parametrize(
    ("path", "value"),
    [
        # A frozen condition reworded.
        (
            ("classification_contract", "CANDIDATE_1_ABSOLUTE_NET_NONPOSITIVE", "condition"),
            "mean_candidate_net < 0",
        ),
        (
            (
                "classification_contract",
                "CANDIDATE_1_ABSOLUTE_NET_AND_RELATIVE_PRICE_POSITIVE",
                "condition",
            ),
            "mean_candidate_net > 0",
        ),
        (
            ("classification_contract", "CANDIDATE_1_ABSOLUTE_NET_NONPOSITIVE", "condition"),
            _DELETE,
        ),
        # A classification added or dropped.
        (("classification_contract", "CANDIDATE_1_MARGINAL"), {"condition": "x"}),
        (("classification_contract", "CANDIDATE_1_ABSOLUTE_NET_NONPOSITIVE"), _DELETE),
        (("classification_contract", "DECOMPOSITION_BLOCKED_OR_INVALID"), _DELETE),
        # The blocked contract's trigger list.
        (
            ("classification_contract", "DECOMPOSITION_BLOCKED_OR_INVALID", "use_when_any"),
            ["source_receipt_cannot_be_authenticated"],
        ),
        # The no-inference guarantees.
        (("classification_contract", "no_percentage_contribution_threshold"), False),
        (("classification_contract", "no_significance_inference"), False),
        (("classification_contract",), _DELETE),
    ],
)
def test_classification_contract_fails_closed(
    tmp_path: Path, path: tuple[str, ...], value: object
) -> None:
    case = _case(tmp_path)
    result = _decompose(case, registry=_mutated(case["registry"], path, value))
    assert result["decomposition_state"] == "blocked"
    assert result["reason_codes"]
    assert result["outputs"] is None


def test_implementation_frozen_contract_matches_preregistered_literals() -> None:
    # Double entry: the module's frozen contract must equal the literals above.
    assert subject._DECOMPOSITION_FROZEN_OUTPUT_SCHEMA == _FROZEN_OUTPUT_SCHEMA
    assert list(subject._DECOMPOSITION_FORBIDDEN_OUTPUT_LIST) == _FROZEN_OUTPUT_SCHEMA["forbidden_outputs"]
    for name, condition in subject._DECOMPOSITION_CLASSIFICATION_CONDITIONS.items():
        assert _CLASSIFICATION_CONTRACT[name]["condition"] == condition
    assert subject._DECOMPOSITION_BLOCKED_USE_WHEN_ANY == (
        _CLASSIFICATION_CONTRACT["DECOMPOSITION_BLOCKED_OR_INVALID"]["use_when_any"]
    )
    assert subject._DECOMPOSITION_AUTHORIZATION_STATE == _AUTHORIZATION_STATE


def test_registry_entry_stays_open_to_append_only_evidence_fields(tmp_path: Path) -> None:
    # A harmless future append-only evidence field must not hard-close the entry:
    # the later implementation-binding stage has to be able to add one.
    case = _case(tmp_path)
    registry = _mutated(
        case["registry"], ("implementation_binding_evidence",), {"bound_commit": "0" * 40}
    )
    assert _decompose(case, registry=registry)["decomposition_state"] == "computed"


# ── Differential equivalence against the consumed scorer ────────────────────
#
# A deterministic matrix (no randomness). For every valid case the reconstructed
# T and both slot counts must equal what ``build_first_computed_statistic_v0``
# produced on the same cut. The scorer itself is never modified: it is imported
# and called as-is. Each case also pins the shape it claims to exercise, so a
# case cannot silently stop covering its name.

_EQUIVALENCE_CLOSES = {
    81: 100, 89: 102,
    101: 100, 109: 110,
    103: 100, 111: 105,
    105: 100, 113: 98,
    107: 100, 115: 103,
    121: 100, 129: 95,
    141: 100, 149: 104,
    161: 100, 169: 97,
}

# name -> (cut kwargs, expected slot shape)
_EQUIVALENCE_CASES = {
    "positive_funding_decision": (
        {"funding_rows": [(100, "0.01")]},
        {"scored_slot_count": 1, "invalid_slot_count": 0, "candidate_active_slot_count": 1},
    ),
    "negative_funding_decision": (
        {"funding_rows": [(100, "-0.01")]},
        {"scored_slot_count": 1, "invalid_slot_count": 0, "candidate_active_slot_count": 1},
    ),
    "zero_funding_decision": (
        {"funding_rows": [(100, "0")]},
        {"scored_slot_count": 1, "invalid_slot_count": 0, "candidate_active_slot_count": 0},
    ),
    "mixed_active_and_flat_slots": (
        {"funding_rows": [(100, "0.01"), (120, "0"), (140, "-0.02")]},
        {"scored_slot_count": 3, "invalid_slot_count": 0, "candidate_active_slot_count": 2},
    ),
    "same_side_null_assignment": (
        # First active slot takes null +1; a negative rate makes the candidate long.
        {"funding_rows": [(100, "-0.01")]},
        {"scored_slot_count": 1, "invalid_slot_count": 0, "candidate_active_slot_count": 1},
    ),
    "opposite_side_null_assignment": (
        # First active slot takes null +1; a positive rate makes the candidate short.
        {"funding_rows": [(100, "0.01")]},
        {"scored_slot_count": 1, "invalid_slot_count": 0, "candidate_active_slot_count": 1},
    ),
    "both_null_side_assignments": (
        # Two active slots => null +1 then -1: one same-side, one opposite-side.
        {"funding_rows": [(100, "-0.01"), (120, "-0.01")]},
        {"scored_slot_count": 2, "invalid_slot_count": 0, "candidate_active_slot_count": 2},
    ),
    "multiple_in_window_funding_events": (
        {"funding_rows": [(100, "-0.01"), (102, "0.003"), (104, "0.002"), (106, "0.001")]},
        {"scored_slot_count": 4, "invalid_slot_count": 0, "candidate_active_slot_count": 4},
    ),
    "canonical_funding_columns": (
        {"funding_rows": [(100, "0.01"), (120, "-0.02")], "canonical_funding_columns": True},
        {"scored_slot_count": 2, "invalid_slot_count": 0, "candidate_active_slot_count": 2},
    ),
    "alias_funding_columns": (
        {"funding_rows": [(100, "0.01"), (120, "-0.02")], "canonical_funding_columns": False},
        {"scored_slot_count": 2, "invalid_slot_count": 0, "candidate_active_slot_count": 2},
    ),
    "warmup_invalid_slot": (
        # Decision at 80 enters at bar 81, before the 90-bar warmup => invalid.
        {"funding_rows": [(80, "0.01"), (100, "0.01")]},
        {"scored_slot_count": 1, "invalid_slot_count": 1, "candidate_active_slot_count": 1},
    ),
    "purge_crossing_invalid_slot": (
        # Decision at 205 exits at bar 214, past allowed_end 211 => invalid.
        {"funding_rows": [(100, "0.01"), (205, "0.01")]},
        {"scored_slot_count": 1, "invalid_slot_count": 1, "candidate_active_slot_count": 1},
    ),
    "multiple_valid_slots": (
        {"funding_rows": [(100, "0.01"), (120, "-0.02"), (140, "0.03"), (160, "0")]},
        {"scored_slot_count": 4, "invalid_slot_count": 0, "candidate_active_slot_count": 3},
    ),
}


@pytest.mark.parametrize("name", sorted(_EQUIVALENCE_CASES))
def test_reconstruction_equals_scorer_on_same_cut(tmp_path: Path, name: str) -> None:
    cut_kwargs, expected_shape = _EQUIVALENCE_CASES[name]
    case = _case(tmp_path, close_overrides=dict(_EQUIVALENCE_CLOSES), **cut_kwargs)
    result = _decompose(case)
    assert result["decomposition_state"] == "computed", result
    outputs, scorer = result["outputs"], case["scorer"]

    assert outputs["reconstructed_statistic_value_T"] == scorer["statistic_value_T"]
    assert outputs["scored_slot_count"] == scorer["scored_slot_count"]
    assert outputs["invalid_slot_count"] == scorer["invalid_slot_count"]
    # The case really exercises the shape its name claims.
    for key, expected in expected_shape.items():
        assert outputs[key] == expected


@pytest.mark.parametrize("name", sorted(_EQUIVALENCE_CASES))
def test_reconstruction_is_from_components_not_mean_of_differences(
    tmp_path: Path, name: str
) -> None:
    # T must equal the relative component means combined under the frozen
    # identity, not merely mean(candidate_net - null_net).
    cut_kwargs, _ = _EQUIVALENCE_CASES[name]
    case = _case(tmp_path, close_overrides=dict(_EQUIVALENCE_CLOSES), **cut_kwargs)
    outputs = _decompose(case)["outputs"]
    reconstructed = (
        Decimal(repr(outputs["mean_relative_price_component"]))
        + Decimal(repr(outputs["mean_relative_funding_component"]))
        - Decimal(repr(outputs["mean_relative_cost_difference"]))
    )
    assert float(reconstructed) == outputs["reconstructed_statistic_value_T"]


# ── Reconstruction gate ─────────────────────────────────────────────────────


def test_reconstruction_mismatch_blocks(tmp_path: Path) -> None:
    # Registry and receipt agree with each other but not with the recomputation:
    # every binding check passes and only the reconstruction gate can catch it.
    case = _case(tmp_path, source_values={"statistic_value_T": 0.123456})
    result = _decompose(case)
    assert result["decomposition_state"] == "blocked"
    assert result["classification"] == subject.DECOMPOSITION_BLOCKED_OR_INVALID
    assert "reconstruction_mismatch" in result["reason_codes"]
    assert result["outputs"] is None


def test_source_slot_universe_mismatch_blocks_on_recomputed_counts(tmp_path: Path) -> None:
    case = _case(tmp_path, source_values={"scored_slot_count": 99})
    result = _decompose(case)
    assert result["decomposition_state"] == "blocked"
    assert "source_slot_universe_mismatch" in result["reason_codes"]


def test_blocked_reason_codes_are_bounded_and_deterministic(tmp_path: Path) -> None:
    case = _case(tmp_path, source_values={"statistic_value_T": 0.123456})
    first, second = _decompose(case), _decompose(case)
    assert first["reason_codes"] == second["reason_codes"]
    assert first["reason_codes"] == sorted(set(first["reason_codes"]))


# ── Component identities are verified exactly, on Decimals ──────────────────


def _consistent_slot(**overrides: Decimal) -> dict[str, object]:
    slot: dict[str, object] = {
        "active": Decimal("1"),
        "candidate_price": Decimal("0.1"),
        "candidate_funding": Decimal("-0.004"),
        "candidate_cost": Decimal("0.0022"),
        "null_price": Decimal("-0.1"),
        "null_funding": Decimal("0.004"),
        "null_cost": Decimal("0.0022"),
        "always_long_net": Decimal("0.0938"),
        "always_short_net": Decimal("-0.0982"),
        "flat_net": Decimal("0"),
    }
    for role in ("candidate", "null"):
        slot[f"{role}_net"] = (
            slot[f"{role}_price"] + slot[f"{role}_funding"] - slot[f"{role}_cost"]
        )
    slot["relative_price"] = slot["candidate_price"] - slot["null_price"]
    slot["relative_funding"] = slot["candidate_funding"] - slot["null_funding"]
    slot["relative_cost_difference"] = slot["candidate_cost"] - slot["null_cost"]
    slot["relative_net"] = slot["candidate_net"] - slot["null_net"]
    slot.update(overrides)
    return slot


def test_consistent_slots_satisfy_the_per_slot_identities() -> None:
    assert subject._per_slot_component_identity_reasons([_consistent_slot()]) == []


@pytest.mark.parametrize("field", ["candidate_net", "null_net", "relative_net"])
def test_per_slot_identity_violation_is_detected(field: str) -> None:
    broken = _consistent_slot(**{field: Decimal("0.5")})
    assert subject._per_slot_component_identity_reasons([broken]) == [
        "per_slot_component_identity_violation"
    ]


def test_per_slot_identity_violation_detected_even_one_ulp_off() -> None:
    slot = _consistent_slot()
    slot["candidate_net"] = slot["candidate_net"] + Decimal("1e-27")
    assert subject._per_slot_component_identity_reasons([slot]) == [
        "per_slot_component_identity_violation"
    ]


def test_per_slot_identity_reasons_stay_bounded_and_leak_no_slot_values() -> None:
    broken = [_consistent_slot(candidate_net=Decimal(index)) for index in range(50)]
    reasons = subject._per_slot_component_identity_reasons(broken)
    assert reasons == ["per_slot_component_identity_violation"]


def test_aggregate_means_satisfy_the_frozen_additive_identities(tmp_path: Path) -> None:
    # Exercised through the public core: the golden outputs must satisfy the
    # aggregate identities at serialization precision.
    outputs = _decompose(_golden_case(tmp_path))["outputs"]
    for net, (price, funding, cost) in {
        "mean_candidate_net": (
            "mean_candidate_price_component",
            "mean_candidate_funding_component",
            "mean_candidate_cost_drag",
        ),
        "mean_null_net": (
            "mean_null_price_component",
            "mean_null_funding_component",
            "mean_null_cost_drag",
        ),
        "reconstructed_statistic_value_T": (
            "mean_relative_price_component",
            "mean_relative_funding_component",
            "mean_relative_cost_difference",
        ),
    }.items():
        derived = (
            Decimal(repr(outputs[price]))
            + Decimal(repr(outputs[funding]))
            - Decimal(repr(outputs[cost]))
        )
        assert float(derived) == outputs[net]


# ── Classification runs on Decimals, never on rounded floats ────────────────


def test_classification_uses_decimal_means_not_rounded_floats() -> None:
    # A mean too small to survive float conversion is still strictly positive.
    # Classifying the rounded float would call it non-positive; the Decimal must
    # win.
    underflowing = Decimal("1e-400")
    assert float(underflowing) == 0.0
    assert (
        subject._classify_candidate1_decomposition(underflowing, underflowing)
        == subject.CANDIDATE_1_ABSOLUTE_NET_AND_RELATIVE_PRICE_POSITIVE
    )


def test_classification_relative_price_underflow_uses_decimal() -> None:
    underflowing = Decimal("1e-400")
    assert (
        subject._classify_candidate1_decomposition(Decimal("0.5"), underflowing)
        == subject.CANDIDATE_1_ABSOLUTE_NET_AND_RELATIVE_PRICE_POSITIVE
    )
    assert (
        subject._classify_candidate1_decomposition(Decimal("0.5"), -underflowing)
        == subject.CANDIDATE_1_ABSOLUTE_NET_POSITIVE_RELATIVE_PRICE_NONPOSITIVE
    )


@pytest.mark.parametrize(
    ("net", "relative_price", "expected"),
    [
        (Decimal("-0.01"), Decimal("0.5"), "CANDIDATE_1_ABSOLUTE_NET_NONPOSITIVE"),
        (Decimal("0"), Decimal("0.5"), "CANDIDATE_1_ABSOLUTE_NET_NONPOSITIVE"),
        (
            Decimal("0.01"),
            Decimal("0"),
            "CANDIDATE_1_ABSOLUTE_NET_POSITIVE_RELATIVE_PRICE_NONPOSITIVE",
        ),
        (
            Decimal("0.01"),
            Decimal("-0.5"),
            "CANDIDATE_1_ABSOLUTE_NET_POSITIVE_RELATIVE_PRICE_NONPOSITIVE",
        ),
        (
            Decimal("0.01"),
            Decimal("0.5"),
            "CANDIDATE_1_ABSOLUTE_NET_AND_RELATIVE_PRICE_POSITIVE",
        ),
    ],
)
def test_frozen_classification_boundaries(
    net: Decimal, relative_price: Decimal, expected: str
) -> None:
    assert subject._classify_candidate1_decomposition(net, relative_price) == expected


# ── Archived artifact binding: structural presence only ─────────────────────


@pytest.mark.parametrize(
    "field",
    [
        "archived_command_sha256",
        "archived_log_sha256",
        "archived_exit_code_sha256",
        "archived_receipt_path",
    ],
)
def test_missing_archived_artifact_binding_blocks(tmp_path: Path, field: str) -> None:
    case = _case(tmp_path)
    result = _decompose(
        case, registry=_mutated(case["registry"], ("source_binding", field), _DELETE)
    )
    assert result["decomposition_state"] == "blocked"
    assert "source_artifact_binding_incomplete" in result["reason_codes"]


@pytest.mark.parametrize("bad", ["not-a-sha", "AB" * 32, ""])
def test_malformed_archived_artifact_hash_blocks(tmp_path: Path, bad: str) -> None:
    case = _case(tmp_path)
    result = _decompose(
        case,
        registry=_mutated(case["registry"], ("source_binding", "archived_log_sha256"), bad),
    )
    assert "source_artifact_binding_incomplete" in result["reason_codes"]


def test_artifact_bytes_are_not_authenticated_here(tmp_path: Path) -> None:
    # The command/log/exit-code bytes are not inputs to this core, so a
    # structurally valid but arbitrary hash must NOT block: authenticating those
    # artifacts is the later no-computation preflight's job. Only the receipt
    # bytes are authenticated here, and that check is exercised separately.
    case = _case(tmp_path)
    registry = _mutated(
        case["registry"], ("source_binding", "archived_command_sha256"), "f" * 64
    )
    assert _decompose(case, registry=registry)["decomposition_state"] == "computed"


def test_aggregate_component_mean_disagreement_is_detected() -> None:
    # Components that do not account for the total must be caught: the derived
    # net mean and the directly aggregated per-slot nets then disagree.
    slot = _consistent_slot()
    slot["candidate_net"] = slot["candidate_net"] + Decimal("0.5")
    _means, reasons = subject._candidate1_decomposition_means([slot])
    assert "component_mean_direct_disagreement" in reasons


def test_aggregate_means_are_derived_from_components(tmp_path: Path) -> None:
    # The reported net means are the component reconstruction, exactly.
    slots = [_consistent_slot(), _consistent_slot(candidate_price=Decimal("0.3"))]
    for slot in slots:
        slot["candidate_net"] = (
            slot["candidate_price"] + slot["candidate_funding"] - slot["candidate_cost"]
        )
    means, reasons = subject._candidate1_decomposition_means(slots)
    assert reasons == []
    assert (
        means["candidate_net"]
        == means["candidate_price"] + means["candidate_funding"] - means["candidate_cost"]
    )
