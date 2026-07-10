"""Tests for quantbot/experiment/offline_edge_real_validation.py

Receipt-skeleton PR: verifies the schema, split-builder skeleton, cost-case
matrix skeleton, validation refusals, and /tmp-only writer for the first
real offline validation receipt. This PR does not compute returns, PnL,
Sharpe, or run any engine — every test here confirms that stays true.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from quantbot.experiment.offline_edge_real_validation import (
    build_cost_case_matrix,
    build_deterministic_split_definitions,
    build_real_validation_receipt,
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
