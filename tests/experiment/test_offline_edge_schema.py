"""Tests for quantbot/experiment/offline_edge_schema.py

PR A — safe skeleton schema tests.
"""

import pytest
from quantbot.experiment.offline_edge_schema import (
    ReceiptMetadata,
    CostModelAssumptions,
    StageMetrics,
    ValidationReceipt,
    SKELETON_ONLY,
    INCONCLUSIVE,
    EDGE_CANDIDATE,
    NO_EDGE,
    NEEDS_MORE_DATA,
    BLOCKED_BY_DATA_QUALITY,
    validate_skeleton_verdict,
)


class TestSchemaConstants:
    def test_allowed_verdicts(self):
        assert SKELETON_ONLY == "SKELETON_ONLY"
        assert INCONCLUSIVE == "INCONCLUSIVE"

    def test_forbidden_future_verdicts_named(self):
        # These constants must exist for refusal tests even though not allowed
        assert EDGE_CANDIDATE == "EDGE_CANDIDATE"
        assert NO_EDGE == "NO_EDGE"
        assert NEEDS_MORE_DATA == "NEEDS_MORE_DATA"
        assert BLOCKED_BY_DATA_QUALITY == "BLOCKED_BY_DATA_QUALITY"


class TestCostModelDefaults:
    def test_defaults_match_spec(self):
        assumptions = CostModelAssumptions(
            slippage_bps_per_side=5.0,
            commission_bps_per_side=5.0,
            heat_cap=1.0,
            vol_lookback_bars=90,
            vol_floor=1e-6,
        )
        assert assumptions["slippage_bps_per_side"] == 5.0
        assert assumptions["commission_bps_per_side"] == 5.0
        assert assumptions["heat_cap"] == 1.0
        assert assumptions["vol_lookback_bars"] == 90
        assert assumptions["vol_floor"] == 1e-6


class TestValidateSkeletonVerdict:
    def test_accepts_skeleton_only(self):
        assert validate_skeleton_verdict(SKELETON_ONLY) == SKELETON_ONLY

    def test_accepts_inconclusive(self):
        assert validate_skeleton_verdict(INCONCLUSIVE) == INCONCLUSIVE

    def test_rejects_edge_candidate(self):
        with pytest.raises(ValueError, match="EDGE_CANDIDATE"):
            validate_skeleton_verdict(EDGE_CANDIDATE)

    def test_rejects_no_edge(self):
        with pytest.raises(ValueError):
            validate_skeleton_verdict(NO_EDGE)

    def test_rejects_random_verdict(self):
        with pytest.raises(ValueError):
            validate_skeleton_verdict("SOME_RANDOM_VERDICT")


class TestReceiptMetadataStructure:
    def test_receipt_metadata_fields(self):
        meta = ReceiptMetadata(
            tool_name="offline_edge_validator",
            tool_version="0.1.0",
            timestamp_utc="2026-07-09T00:00:00Z",
            pipeline_description="skeleton",
        )
        assert meta["tool_name"] == "offline_edge_validator"
        assert meta["tool_version"] == "0.1.0"
        assert meta["timestamp_utc"] == "2026-07-09T00:00:00Z"
        assert meta["pipeline_description"] == "skeleton"


class TestStageMetricsStructure:
    def test_stage_metrics_fields(self):
        stage = StageMetrics(
            stage_id="A",
            stage_name="data_quality",
            status="SKELETON_ONLY",
            summary="placeholder",
        )
        assert stage["stage_id"] == "A"
        assert stage["stage_name"] == "data_quality"
        assert stage["status"] == "SKELETON_ONLY"
        assert stage["summary"] == "placeholder"


class TestValidationReceiptStructure:
    def test_receipt_all_required_keys(self):
        receipt = ValidationReceipt(
            validation_receipt=ReceiptMetadata(
                tool_name="offline_edge_validator",
                tool_version="0.1.0",
                timestamp_utc="2026-07-09T00:00:00Z",
                pipeline_description="skeleton",
            ),
            input_manifest_fingerprint="abc123",
            cost_model_assumptions=CostModelAssumptions(
                slippage_bps_per_side=5.0,
                commission_bps_per_side=5.0,
                heat_cap=1.0,
                vol_lookback_bars=90,
                vol_floor=1e-6,
            ),
            per_stage_metrics={},
            final_verdict=SKELETON_ONLY,
        )
        assert set(receipt.keys()) == {
            "validation_receipt",
            "input_manifest_fingerprint",
            "cost_model_assumptions",
            "per_stage_metrics",
            "final_verdict",
        }
        assert receipt["final_verdict"] == SKELETON_ONLY