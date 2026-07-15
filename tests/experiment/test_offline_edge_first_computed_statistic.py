from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from quantbot.experiment import offline_edge_real_validation as subject


def _timestamp(index: int) -> str:
    return (datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(hours=index)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _write_cut(
    tmp_path: Path,
    *,
    close_overrides: dict[int, str | float] | None = None,
    funding_rows: list[tuple[int, str | float]] | None = None,
    canonical_funding_columns: bool = True,
    extra_funding_columns: tuple[str, ...] = (),
) -> tuple[Path, Path]:
    bars_dir = tmp_path / "bars"
    funding_dir = tmp_path / "funding"
    bars_dir.mkdir(parents=True)
    funding_dir.mkdir(parents=True)
    close_overrides = close_overrides or {}
    with open(bars_dir / "BTC.csv", "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp", "close"])
        for index in range(400):
            writer.writerow([_timestamp(index), close_overrides.get(index, 100)])

    if canonical_funding_columns:
        header = ["fundingTime", "fundingRate", *extra_funding_columns]
    else:
        header = ["timestamp", "funding_rate", *extra_funding_columns]
    with open(funding_dir / "BTC.csv", "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for index, rate in funding_rows or [(100, "0.01")]:
            writer.writerow([_timestamp(index), rate, *(["x"] * len(extra_funding_columns))])
    return bars_dir, funding_dir


def _split(boundary: int = 220) -> dict[str, object]:
    return {
        "leakage_audit_killed": False,
        "boundary_index": boundary,
        "declared_purge_intervals": 8,
        "declared_embargo_intervals": 90,
    }


def _registry(bars_dir: Path, funding_dir: Path) -> dict[str, object]:
    declaration = {
        "candidate_definition": dict(subject._FIRST_CANDIDATE_DEFINITION),
        "null_definition": dict(subject._FIRST_NULL_DEFINITION),
        "statistic_definition": dict(subject._FIRST_STATISTIC_DEFINITION),
        "candidate_rule_fingerprint": subject._FIRST_CANDIDATE_RULE_FINGERPRINT,
        "null_rule_fingerprint": subject._FIRST_NULL_RULE_FINGERPRINT,
        "statistic_rule_fingerprint": subject._FIRST_STATISTIC_RULE_FINGERPRINT,
        "registered_before_execution": True,
        "data_cut_fingerprint": subject._first_statistic_bound_fingerprint(
            bars_dir / "BTC.csv", funding_dir / "BTC.csv"
        ),
    }
    return {subject.FIRST_COMPUTED_STATISTIC_VERSION: declaration}


def _compute(
    bars_dir: Path,
    funding_dir: Path,
    *,
    registry: dict[str, object] | None = None,
    split: dict[str, object] | None = None,
    gate: dict[str, object] | None = None,
) -> dict[str, object]:
    return subject.build_first_computed_statistic_v0(
        bars_dir=bars_dir,
        funding_dir=funding_dir,
        registry_entry=registry or _registry(bars_dir, funding_dir),
        split_audit=split or _split(),
        holdout_open_gate=gate,
    )


@pytest.mark.parametrize(
    ("rate", "expected"),
    [("0.01", -0.2), ("-0.01", 0.0), ("0", 0.0)],
)
def test_candidate_side_mapping_positive_short_negative_long_zero_flat(
    tmp_path: Path, rate: str, expected: float
) -> None:
    bars, funding = _write_cut(
        tmp_path,
        close_overrides={101: 100, 109: 110},
        funding_rows=[(100, rate)],
    )
    result = _compute(bars, funding)
    assert result["statistic_state"] == "computed"
    assert result["statistic_value_T"] == pytest.approx(expected)


def test_entry_is_first_hourly_close_strictly_after_funding_time(tmp_path: Path) -> None:
    bars, funding = _write_cut(
        tmp_path,
        close_overrides={100: 50, 101: 100, 108: 200, 109: 110},
        funding_rows=[(100, "0.01")],
    )
    assert _compute(bars, funding)["statistic_value_T"] == pytest.approx(-0.2)


def test_exit_is_exactly_eight_hourly_bars_after_entry(tmp_path: Path) -> None:
    bars, funding = _write_cut(
        tmp_path,
        close_overrides={101: 100, 108: 500, 109: 125, 110: 700},
        funding_rows=[(100, "0.01")],
    )
    assert _compute(bars, funding)["statistic_value_T"] == pytest.approx(-0.5)


def test_funding_at_decision_excluded_and_after_entry_through_exit_included(
    tmp_path: Path,
) -> None:
    bars, funding = _write_cut(
        tmp_path,
        funding_rows=[(99, "0.01"), (105, "0.02")],
    )
    result = _compute(bars, funding)
    assert result["scored_slot_count"] == 2
    assert result["statistic_value_T"] == pytest.approx(0.02)


def test_null_alternates_only_on_active_slots_and_flat_does_not_advance(
    tmp_path: Path,
) -> None:
    bars, funding = _write_cut(
        tmp_path,
        close_overrides={101: 100, 109: 110, 121: 100, 129: 110, 141: 100, 149: 110},
        funding_rows=[(100, "0.01"), (120, "0"), (140, "0.01")],
    )
    result = _compute(bars, funding)
    # Active null sides are +1 then -1; the middle flat contributes zero and
    # does not advance the active-slot alternation.
    assert result["statistic_value_T"] == pytest.approx((-0.2 + 0.0 + 0.0) / 3)


def test_costs_apply_only_to_active_slots_and_identically_cancel(tmp_path: Path) -> None:
    bars, funding = _write_cut(
        tmp_path,
        funding_rows=[(100, "0"), (120, "0.01"), (140, "0.01")],
    )
    result = _compute(bars, funding)
    assert result["statistic_value_T"] == pytest.approx(0.0)


def test_T_is_deterministic(tmp_path: Path) -> None:
    bars, funding = _write_cut(tmp_path, funding_rows=[(100, "0.01"), (120, "-0.02")])
    registry = _registry(bars, funding)
    assert _compute(bars, funding, registry=registry) == _compute(
        bars, funding, registry=registry
    )


def test_altered_input_changes_T_when_manifest_is_refrozen(tmp_path: Path) -> None:
    bars, funding = _write_cut(
        tmp_path,
        close_overrides={101: 100, 109: 110},
        funding_rows=[(100, "0.01")],
    )
    first = _compute(bars, funding)["statistic_value_T"]
    rows = list(csv.reader((bars / "BTC.csv").open()))
    rows[110][1] = "120"  # header + bar index 109
    with open(bars / "BTC.csv", "w", newline="") as handle:
        csv.writer(handle).writerows(rows)
    second = _compute(bars, funding, registry=_registry(bars, funding))["statistic_value_T"]
    assert first != second


@pytest.mark.parametrize(
    ("missing", "reason"),
    [
        ("candidate_definition", "candidate_definition_missing"),
        ("null_definition", "null_definition_missing"),
        ("statistic_definition", "statistic_definition_missing"),
    ],
)
def test_missing_frozen_definition_blocks(tmp_path: Path, missing: str, reason: str) -> None:
    bars, funding = _write_cut(tmp_path)
    registry = _registry(bars, funding)
    del registry[subject.FIRST_COMPUTED_STATISTIC_VERSION][missing]
    result = _compute(bars, funding, registry=registry)
    assert result["statistic_state"] == "blocked"
    assert reason in result["statistic_reason_codes"]


def test_missing_or_changed_frozen_data_fingerprint_blocks(tmp_path: Path) -> None:
    bars, funding = _write_cut(tmp_path)
    registry = _registry(bars, funding)
    registry[subject.FIRST_COMPUTED_STATISTIC_VERSION]["data_cut_fingerprint"] = None
    assert _compute(bars, funding, registry=registry)["statistic_state"] == "blocked"
    registry = _registry(bars, funding)
    with open(bars / "BTC.csv", "a") as handle:
        handle.write("\n")
    result = _compute(bars, funding, registry=registry)
    assert result["statistic_state"] == "blocked"
    assert "data_cut_fingerprint_mismatch" in result["statistic_reason_codes"]


def test_split_purge_embargo_are_fixed_and_crossing_position_is_invalid(tmp_path: Path) -> None:
    bars, funding = _write_cut(tmp_path, funding_rows=[(100, "0.01"), (205, "0.01")])
    result = _compute(bars, funding)
    assert result["scored_slot_count"] == 1
    assert result["invalid_slot_count"] == 1
    wrong_split = dict(_split())
    wrong_split["declared_purge_intervals"] = 7
    blocked = _compute(bars, funding, split=wrong_split)
    assert blocked["statistic_state"] == "blocked"


def test_warmup_excludes_early_position(tmp_path: Path) -> None:
    bars, funding = _write_cut(tmp_path, funding_rows=[(80, "0.01"), (100, "0.01")])
    result = _compute(bars, funding)
    assert result["scored_slot_count"] == 1
    assert result["invalid_slot_count"] == 1


def test_holdout_remains_unopened_without_explicit_passed_gate(tmp_path: Path) -> None:
    bars, funding = _write_cut(
        tmp_path,
        funding_rows=[(100, "0.01"), (230, "not-inspected")],
        close_overrides={350: "not-inspected"},
    )
    result = _compute(bars, funding, gate={"holdout_open_gate_state": "blocked"})
    assert result["statistic_state"] == "computed"
    assert result["statistic_reason_codes"] == ["holdout_remained_sealed_non_holdout_scored"]


def test_passed_structural_gate_does_not_open_or_read_holdout_partition(tmp_path: Path) -> None:
    bars, funding = _write_cut(
        tmp_path,
        funding_rows=[(100, "0.01"), (320, "not-inspected")],
        close_overrides={320: "not-inspected", 328: "not-inspected"},
    )
    gate = {"holdout_open_gate_state": "gate_passed", "holdout_open_gate_killed": False}
    result = _compute(bars, funding, gate=gate)
    assert result["statistic_state"] == "computed"
    assert result["scored_slot_count"] == 1
    assert result["statistic_reason_codes"] == ["holdout_remained_sealed_non_holdout_scored"]


@pytest.mark.parametrize("rate", ["0", "0.01"])
def test_zero_or_negative_T_emits_honestly(tmp_path: Path, rate: str) -> None:
    overrides = {101: 100, 109: 110} if rate == "0.01" else {}
    bars, funding = _write_cut(tmp_path, close_overrides=overrides, funding_rows=[(100, rate)])
    result = _compute(bars, funding)
    assert result["statistic_state"] == "computed"
    assert result["statistic_value_T"] <= 0


def test_boundary_normalizes_alias_columns_and_rejects_ambiguous_columns(tmp_path: Path) -> None:
    bars, funding = _write_cut(tmp_path, canonical_funding_columns=False)
    assert _compute(bars, funding)["statistic_state"] == "computed"

    other = tmp_path / "ambiguous"
    bars, funding = _write_cut(
        other,
        extra_funding_columns=("timestamp", "funding_rate"),
    )
    result = _compute(bars, funding)
    assert result["statistic_state"] == "invalid"
    assert "funding_columns_ambiguous" in result["statistic_reason_codes"]


def test_btc_universe_requires_exactly_one_matched_file_per_role(tmp_path: Path) -> None:
    bars, funding = _write_cut(tmp_path)
    (bars / "BTC_second.csv").write_text((bars / "BTC.csv").read_text())
    result = subject.build_first_computed_statistic_v0(
        bars_dir=bars,
        funding_dir=funding,
        registry_entry=_registry(bars, funding),
        split_audit=_split(),
        holdout_open_gate=None,
    )
    assert result["statistic_state"] == "blocked"
    assert "btc_file_match_count_not_one" in result["statistic_reason_codes"]


def test_full_receipt_validates_and_authorizations_remain_false(tmp_path: Path) -> None:
    bars, funding = _write_cut(tmp_path)
    block = _compute(bars, funding)
    computed_slice = {
        "immutable_data_cut": {},
        "trial_registry": {},
        "deterministic_split": {},
        "kill_criteria": {},
        "computed_input_integrity_result": {
            "status": "EDGE_UNPROVEN",
            "paper_trade_authorized": False,
            "live_integration_authorized": False,
        },
        subject.FIRST_COMPUTED_STATISTIC_VERSION: block,
    }
    receipt = subject.build_real_validation_receipt(
        input_manifest_fingerprint="a" * 64,
        data_quality_receipt_sha256="b" * 64,
        code_commit_sha="deadbeef",
        split_definitions=[{"split_id": "one"}],
        cost_cases=subject.build_cost_case_matrix(),
        protocol_computed_validation_slice=computed_slice,
    )
    subject.validate_real_validation_receipt(receipt)
    assert receipt["forbidden_calculation_status"]["returns_computed"] is True
    assert receipt["forbidden_calculation_status"]["pnl_computed"] is False
    assert receipt["final_offline_verdict"] == subject.BLOCKED_BY_VALIDATION_IMPLEMENTATION
    assert computed_slice["computed_input_integrity_result"]["paper_trade_authorized"] is False
    assert computed_slice["computed_input_integrity_result"]["live_integration_authorized"] is False


def test_exact_key_forbidden_scanner_still_rejects_elsewhere(tmp_path: Path) -> None:
    bars, funding = _write_cut(tmp_path)
    block = _compute(bars, funding)
    with pytest.raises(ValueError, match="Forbidden calculation key"):
        subject._assert_no_forbidden_calculation_keys(
            {subject.FIRST_COMPUTED_STATISTIC_VERSION: block, "elsewhere": {"sharpe": 1}}
        )


def test_receipt_block_has_exact_narrow_key_set(tmp_path: Path) -> None:
    bars, funding = _write_cut(tmp_path)
    assert set(_compute(bars, funding)) == subject._FIRST_STATISTIC_RECEIPT_KEYS


def test_real_cli_emits_valid_bounded_statistic_receipt(tmp_path: Path) -> None:
    bars, funding = _write_cut(tmp_path / "cut")
    registry_entry = _registry(bars, funding)
    registry_entry.update(
        {
            "candidate_family": subject._PROTOCOL_CANDIDATE_FAMILY,
            "null_family": subject._PROTOCOL_NULL_FAMILY,
            "append_only": True,
            "registered_before_execution": True,
            "split_boundary_index": 220,
            "purge_intervals": 8,
            "embargo_intervals": 90,
        }
    )
    protocol_fingerprint = subject._data_cut_fingerprint(
        [("bars/BTC.csv", bars / "BTC.csv"), ("funding/BTC.csv", funding / "BTC.csv")]
    )
    registry_entry["data_cut_fingerprint"] = protocol_fingerprint
    registry_path = tmp_path / "trial_registry.json"
    registry_path.write_text(json.dumps([registry_entry]))
    output_dir = tmp_path / "output"

    exit_code = subject.main(
        [
            "--read-only",
            "--output-dir",
            str(output_dir),
            "--input-manifest-fingerprint",
            "a" * 64,
            "--data-quality-receipt-sha256",
            "b" * 64,
            "--code-commit-sha",
            "deadbeef",
            "--protocol-computed-validation",
            "--first-computed-statistic",
            "--expected-data-cut-fingerprint",
            protocol_fingerprint,
            "--trial-registry-path",
            str(registry_path),
            "--purge-intervals",
            "8",
            "--embargo-intervals",
            "90",
            "--split-boundary-index",
            "220",
            "--bars-dir",
            str(bars),
            "--funding-dir",
            str(funding),
        ]
    )
    assert exit_code == 0
    receipt = json.loads((output_dir / "real_validation_receipt.json").read_text())
    block = receipt["protocol_computed_validation"][subject.FIRST_COMPUTED_STATISTIC_VERSION]
    assert block["statistic_state"] == "computed"
    assert receipt["final_offline_verdict"] == subject.BLOCKED_BY_VALIDATION_IMPLEMENTATION
    subject.validate_real_validation_receipt(receipt)
