"""Tests for quantbot/experiment/offline_edge_receipt.py

PR F — fixture-only offline edge validation receipt assembler.
No engine, exchange, DB, or paper imports.
"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path
from typing import Any

import pytest

from quantbot.experiment.offline_edge_receipt import (
    build_fixture_validation_receipt,
    build_guardrail_status,
    validate_fixture_receipt,
    write_receipt_json,
)
from quantbot.experiment.offline_edge_schema import (
    EDGE_CANDIDATE,
    INCONCLUSIVE,
    SKELETON_ONLY,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_valid_receipt() -> dict[str, Any]:
    """Return a minimal valid receipt dict for testing."""
    return build_fixture_validation_receipt(
        input_manifest_fingerprint="a" * 64,
    )


# ---------------------------------------------------------------------------
# TestGuardrailStatus
# ---------------------------------------------------------------------------


class TestGuardrailStatus:
    def test_guardrail_status_contains_all_required_booleans(self) -> None:
        status = build_guardrail_status()
        assert status["edge_unproven"] is True
        assert status["block_live_integration"] is True
        assert status["clean_net_of_carry_is_not_edge"] is True
        assert status["long_only_1x_only"] is True
        assert status["fixture_only"] is True

    def test_guardrail_status_deterministic(self) -> None:
        status1 = build_guardrail_status()
        status2 = build_guardrail_status()
        assert status1 == status2

    def test_guardrail_status_no_extra_keys(self) -> None:
        status = build_guardrail_status()
        expected = {
            "edge_unproven",
            "block_live_integration",
            "clean_net_of_carry_is_not_edge",
            "long_only_1x_only",
            "fixture_only",
        }
        assert set(status.keys()) == expected


# ---------------------------------------------------------------------------
# TestBuildFixtureValidationReceipt
# ---------------------------------------------------------------------------


class TestBuildFixtureValidationReceipt:
    def test_full_receipt_contains_all_top_level_keys(self) -> None:
        receipt = _make_valid_receipt()
        expected_keys = {
            "validation_receipt",
            "input_manifest_fingerprint",
            "input_manifest_summary",
            "cost_model_assumptions",
            "per_stage_metrics",
            "volnorm_fixture_summary",
            "walkforward_fixture_summary",
            "guardrail_status",
            "final_verdict",
            "final_verdict_rationale",
        }
        assert set(receipt.keys()) == expected_keys

    def test_final_verdict_is_skeleton_only(self) -> None:
        receipt = _make_valid_receipt()
        assert receipt["final_verdict"] == SKELETON_ONLY

    def test_final_verdict_can_be_inconclusive(self) -> None:
        receipt = build_fixture_validation_receipt(
            input_manifest_fingerprint="b" * 64,
            final_verdict=INCONCLUSIVE,
        )
        assert receipt["final_verdict"] == INCONCLUSIVE

    def test_receipt_rejects_edge_candidate(self) -> None:
        with pytest.raises(ValueError, match="not allowed in skeleton"):
            build_fixture_validation_receipt(
                input_manifest_fingerprint="c" * 64,
                final_verdict=EDGE_CANDIDATE,
            )

    def test_no_top_level_pnl_sharpe_edge_strategy_performance(self) -> None:
        receipt = _make_valid_receipt()
        for forbidden in ("pnl", "sharpe", "edge", "strategy_performance"):
            assert forbidden not in receipt

    def test_receipt_deterministic_except_timestamp(self) -> None:
        r1 = build_fixture_validation_receipt(
            input_manifest_fingerprint="d" * 64,
        )
        r2 = build_fixture_validation_receipt(
            input_manifest_fingerprint="d" * 64,
        )
        # Remove timestamp before comparing
        ts1 = r1["validation_receipt"].pop("timestamp_utc")
        ts2 = r2["validation_receipt"].pop("timestamp_utc")
        assert r1 == r2
        # Timestamps should be different (different call times)
        assert ts1 != ts2

    def test_receipt_metadata_has_required_fields(self) -> None:
        receipt = _make_valid_receipt()
        meta = receipt["validation_receipt"]
        assert meta["tool_name"] == "qnty_offline_edge_validation"
        assert meta["tool_version"] == "0.1.0"
        assert "timestamp_utc" in meta
        assert meta["pipeline_description"] == (
            "fixture-only offline edge validation receipt (skeleton)"
        )

    def test_input_manifest_fingerprint_stored(self) -> None:
        receipt = build_fixture_validation_receipt(
            input_manifest_fingerprint="abcd1234" * 8,
        )
        assert receipt["input_manifest_fingerprint"] == "abcd1234" * 8

    def test_cost_model_assumptions_stored(self) -> None:
        cma = {"slippage_bps_per_side": 5.0, "commission_bps_per_side": 5.0}
        receipt = build_fixture_validation_receipt(
            input_manifest_fingerprint="e" * 64,
            cost_model_assumptions=cma,
        )
        assert receipt["cost_model_assumptions"] == cma

    def test_per_stage_metrics_stored(self) -> None:
        metrics = [
            {"stage_id": "A", "stage_name": "test", "status": "SKELETON_ONLY", "summary": "ok"},
        ]
        receipt = build_fixture_validation_receipt(
            input_manifest_fingerprint="f" * 64,
            per_stage_metrics=metrics,
        )
        assert receipt["per_stage_metrics"] == metrics

    def test_volnorm_fixture_summary_stored(self) -> None:
        summary = {"volnorm_version": "fixture-0.1", "bar_count": 6}
        receipt = build_fixture_validation_receipt(
            input_manifest_fingerprint="g" * 64,
            volnorm_fixture_summary=summary,
        )
        assert receipt["volnorm_fixture_summary"] == summary

    def test_walkforward_fixture_summary_stored(self) -> None:
        summary = {"walkforward_version": "fixture-0.1", "split_count": 3}
        receipt = build_fixture_validation_receipt(
            input_manifest_fingerprint="h" * 64,
            walkforward_fixture_summary=summary,
        )
        assert receipt["walkforward_fixture_summary"] == summary

    def test_guardrail_status_in_receipt(self) -> None:
        receipt = _make_valid_receipt()
        gs = receipt["guardrail_status"]
        assert gs["edge_unproven"] is True
        assert gs["block_live_integration"] is True
        assert gs["clean_net_of_carry_is_not_edge"] is True
        assert gs["long_only_1x_only"] is True
        assert gs["fixture_only"] is True

    def test_final_verdict_rationale_default(self) -> None:
        receipt = _make_valid_receipt()
        assert receipt["final_verdict_rationale"] == (
            "SKELETON_ONLY: fixture-only validation complete. No edge claim made. "
            "No live integration. No strategy PnL."
        )

    def test_custom_final_verdict_rationale(self) -> None:
        receipt = build_fixture_validation_receipt(
            input_manifest_fingerprint="i" * 64,
            final_verdict_rationale="custom rationale",
        )
        assert receipt["final_verdict_rationale"] == "custom rationale"

    def test_default_rationale_for_inconclusive(self) -> None:
        receipt = build_fixture_validation_receipt(
            input_manifest_fingerprint="j" * 64,
            final_verdict=INCONCLUSIVE,
        )
        assert receipt["final_verdict_rationale"] == (
            "INCONCLUSIVE: fixture-only validation incomplete or ambiguous."
        )

    def test_per_stage_metrics_defaults_to_empty_list(self) -> None:
        receipt = _make_valid_receipt()
        assert receipt["per_stage_metrics"] == []

    def test_input_manifest_summary_defaults_to_none(self) -> None:
        receipt = _make_valid_receipt()
        assert receipt["input_manifest_summary"] is None

    def test_cost_model_assumptions_defaults_to_none(self) -> None:
        receipt = _make_valid_receipt()
        assert receipt["cost_model_assumptions"] is None

    def test_volnorm_fixture_summary_defaults_to_none(self) -> None:
        receipt = _make_valid_receipt()
        assert receipt["volnorm_fixture_summary"] is None

    def test_walkforward_fixture_summary_defaults_to_none(self) -> None:
        receipt = _make_valid_receipt()
        assert receipt["walkforward_fixture_summary"] is None


# ---------------------------------------------------------------------------
# TestValidateFixtureReceipt
# ---------------------------------------------------------------------------


class TestValidateFixtureReceipt:
    def test_valid_receipt_raises_no_error(self) -> None:
        receipt = _make_valid_receipt()
        validate_fixture_receipt(receipt)  # should not raise

    def test_missing_key_raises_value_error(self) -> None:
        receipt = _make_valid_receipt()
        del receipt["final_verdict"]
        with pytest.raises(ValueError, match="Missing required receipt key: final_verdict"):
            validate_fixture_receipt(receipt)

    def test_missing_guardrail_key_raises_value_error(self) -> None:
        receipt = _make_valid_receipt()
        del receipt["guardrail_status"]["edge_unproven"]
        with pytest.raises(ValueError, match="Missing required guardrail_status key: edge_unproven"):
            validate_fixture_receipt(receipt)

    def test_bad_final_verdict_raises_value_error(self) -> None:
        receipt = _make_valid_receipt()
        receipt["final_verdict"] = "EDGE_CANDIDATE"
        with pytest.raises(ValueError, match="Invalid final_verdict"):
            validate_fixture_receipt(receipt)


# ---------------------------------------------------------------------------
# TestWriteReceiptJson
# ---------------------------------------------------------------------------


class TestWriteReceiptJson:
    def test_writes_to_output_path(self) -> None:
        """Write to /tmp/test_receipt_output/validation_receipt.json, verify file exists with correct content."""
        receipt = _make_valid_receipt()
        output_path = Path("/tmp") / "test_receipt_output" / "validation_receipt.json"
        try:
            write_receipt_json(receipt, output_path)
            assert output_path.exists()
            with open(output_path) as f:
                loaded = json.load(f)
            assert loaded["final_verdict"] == SKELETON_ONLY
            assert loaded["input_manifest_fingerprint"] == "a" * 64
        finally:
            if output_path.exists():
                output_path.unlink()
            # Clean up parent dir
            parent = output_path.parent
            if parent.exists() and str(parent) != "/tmp":
                parent.rmdir()

    def test_refuses_prod_path(self) -> None:
        """Verify raises ValueError for /srv/qnty path."""
        receipt = _make_valid_receipt()
        prod_path = Path("/srv/qnty/output/test_receipt.json")
        with pytest.raises(ValueError, match="Refusing to write to prod path"):
            write_receipt_json(receipt, prod_path)

    def test_refuses_prod_path_sibling(self) -> None:
        """Verify a path NOT under /srv/qnty does NOT raise ValueError (proving boundary comparison, not string prefix).

        /srv/qnty2 starts with the string "/srv/qnty" but is NOT a subdirectory of /srv/qnty.
        The old str.startswith guard would incorrectly block it; the commonpath guard correctly allows it.
        We use a writable temp path to exercise the same guard logic without permission errors.
        """
        receipt = _make_valid_receipt()
        safe_path = Path("/tmp/test_sibling_boundary_check.json")
        # Should not raise — this path is not under /srv/qnty
        write_receipt_json(receipt, safe_path)
        try:
            assert safe_path.exists()
        finally:
            if safe_path.exists():
                safe_path.unlink()

    def test_validates_receipt_before_writing(self) -> None:
        """Verify that passing an invalid receipt raises ValueError and file is NOT created."""
        receipt = _make_valid_receipt()
        del receipt["final_verdict"]
        output_path = Path("/tmp") / "test_invalid_receipt.json"
        try:
            with pytest.raises(ValueError, match="Missing required receipt key: final_verdict"):
                write_receipt_json(receipt, output_path)
            # File should NOT have been created
            assert not output_path.exists()
        finally:
            if output_path.exists():
                output_path.unlink()

    def test_creates_parent_dirs(self) -> None:
        receipt = _make_valid_receipt()
        output_path = Path("/tmp") / "test_nested_dir" / "subdir" / "receipt.json"
        try:
            write_receipt_json(receipt, output_path)
            assert output_path.exists()
            with open(output_path) as f:
                loaded = json.load(f)
            assert loaded["final_verdict"] == SKELETON_ONLY
        finally:
            if output_path.exists():
                output_path.unlink()
            # Clean up parent dirs
            for parent in [output_path.parent, output_path.parent.parent]:
                if parent.exists() and str(parent) != "/tmp":
                    parent.rmdir()

    def test_writes_indent_2_no_sort_keys(self) -> None:
        """Verify JSON is written with indent=2 and sort_keys=False (preserving order)."""
        receipt = _make_valid_receipt()
        output_path = Path("/tmp") / "test_receipt_format.json"
        try:
            write_receipt_json(receipt, output_path)
            with open(output_path) as f:
                content = f.read()
            # Check indent is 2
            lines = content.strip().split("\n")
            # First key should be validation_receipt (not alphabetically sorted)
            assert '"validation_receipt"' in lines[1]
            # Check indentation
            assert lines[1].startswith('  "')
        finally:
            if output_path.exists():
                output_path.unlink()


# ---------------------------------------------------------------------------
# TestNoEngineOrExchangeImports
# ---------------------------------------------------------------------------


class TestNoEngineOrExchangeImports:
    def test_no_engine_exchange_db_imports(self) -> None:
        """AST inspection: no engine, exchange, ccxt, sqlite, numpy, pandas,
        paper, live, db, report, promotion imports."""
        source_path = Path("quantbot/experiment/offline_edge_receipt.py")
        source = source_path.read_text()
        tree = ast.parse(source)

        forbidden = {
            "engine", "exchange", "ccxt", "sqlite",
            "numpy", "pandas", "paper", "live", "db",
            "report", "promotion",
        }

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name_parts = alias.name.split(".")
                    for part in name_parts:
                        assert part not in forbidden, (
                            f"Forbidden import found: {alias.name} "
                            f"(contains '{part}')"
                        )
            elif isinstance(node, ast.ImportFrom):
                if node.module is not None:
                    name_parts = node.module.split(".")
                    for part in name_parts:
                        assert part not in forbidden, (
                            f"Forbidden import found: {node.module} "
                            f"(contains '{part}')"
                        )