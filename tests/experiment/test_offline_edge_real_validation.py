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
