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
from pathlib import Path

import pytest

import quantbot.experiment.offline_edge_real_validation as real_validation
from quantbot.experiment.offline_edge_real_validation import (
    _parse_timestamp,
    build_cost_case_matrix,
    build_deterministic_split_definitions,
    build_real_validation_input_inventory,
    build_real_validation_receipt,
    materialize_cost_case_observational_drag,
    materialize_gross_observational_returns,
    materialize_funding_observational_adjustments,
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
        _write_tiny_bars_csv(bars_dir)
        _write_tiny_funding_csv(funding_dir)

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
        _write_tiny_bars_csv(bars_dir)
        _write_tiny_funding_csv(funding_dir)

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
        _write_tiny_bars_csv(bars_dir)
        _write_tiny_numeric_funding_csv(funding_dir)

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
        (bars_dir / "bars.csv").symlink_to(bars_source)
        (funding_dir / "funding.csv").symlink_to(funding_source)

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
