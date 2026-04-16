"""Tests for quantbot.experiment.calibration.

Requires PYTHONHASHSEED=0 for deterministic dict ordering.
Paper mode only - no real trading.
"""

import json
import tempfile
from pathlib import Path

import pytest

from quantbot.experiment.calibration import (
    FrankenReconciliationRecord,
    CalibrationComparison,
    ingest_franken_reconciliation,
    compare_record,
    compare_reconciliation_dir,
)
from quantbot.experiment.result import EconomicsSummary


class TestIngestFrankenReconciliation:
    """Tests for ingest_franken_reconciliation."""

    def test_ingest_full_record(self, tmp_path: Path) -> None:
        """Full Franken record is parsed correctly."""
        data = {
            "family_id": "my-family",
            "variant_id": "v1",
            "trial_count": 3,
            "observed_avg_shortfall_bps": 15.0,
            "observed_entry_shortfall_bps": 7.5,
            "observed_exit_shortfall_bps": 7.5,
            "record_count": 100,
        }
        path = tmp_path / "reconciliation.json"
        path.write_text(json.dumps(data))

        record = ingest_franken_reconciliation(path)

        assert record.family_id == "my-family"
        assert record.variant_id == "v1"
        assert record.trial_count == 3
        assert record.observed_avg_shortfall_bps == 15.0
        assert record.observed_entry_shortfall_bps == 7.5
        assert record.observed_exit_shortfall_bps == 7.5
        assert record.record_count == 100
        assert record.source_path == str(path)

    def test_ingest_missing_linkage_fields(self, tmp_path: Path) -> None:
        """Missing linkage fields default to None."""
        data = {
            "observed_avg_shortfall_bps": 12.0,
            "observed_entry_shortfall_bps": 6.0,
            "observed_exit_shortfall_bps": 6.0,
            "record_count": 50,
        }
        path = tmp_path / "reconciliation.json"
        path.write_text(json.dumps(data))

        record = ingest_franken_reconciliation(path)

        assert record.family_id is None
        assert record.variant_id is None
        assert record.trial_count is None
        assert record.observed_avg_shortfall_bps == 12.0
        assert record.record_count == 50

    def test_ingest_missing_shortfall_fields_use_defaults(self, tmp_path: Path) -> None:
        """Missing shortfall fields default to 0.0."""
        data: dict[str, object] = {}
        path = tmp_path / "reconciliation.json"
        path.write_text(json.dumps(data))

        record = ingest_franken_reconciliation(path)

        assert record.observed_avg_shortfall_bps == 0.0
        assert record.observed_entry_shortfall_bps == 0.0
        assert record.observed_exit_shortfall_bps == 0.0
        assert record.record_count == 0


class TestCompareRecord:
    """Tests for compare_record."""

    def test_delta_positive_when_observed_exceeds_assumed(self) -> None:
        """Positive delta when observed shortfall exceeds assumed total cost."""
        record = FrankenReconciliationRecord(
            observed_avg_shortfall_bps=20.0,
            observed_entry_shortfall_bps=10.0,
            observed_exit_shortfall_bps=10.0,
            record_count=50,
            family_id="fam",
            variant_id="v1",
            trial_count=2,
        )
        eco = EconomicsSummary(
            cost_side_count=10,
            fee_bps=5.0,
            slippage_bps=3.0,
            assumed_total_cost_bps=80.0,  # 10 * (5 + 3)
        )

        comp = compare_record(record, eco)

        assert comp.assumed_fee_bps == 5.0
        assert comp.assumed_slippage_bps == 3.0
        assert comp.assumed_total_cost_bps == 80.0
        assert comp.observed_avg_shortfall_bps == 20.0
        assert comp.delta_bps == -60.0  # 20 - 80

    def test_delta_zero_when_observed_matches_assumed(self) -> None:
        """Delta is zero when observed avg shortfall equals assumed total."""
        record = FrankenReconciliationRecord(
            observed_avg_shortfall_bps=10.0,
            observed_entry_shortfall_bps=5.0,
            observed_exit_shortfall_bps=5.0,
            record_count=20,
        )
        eco = EconomicsSummary(
            cost_side_count=5,
            fee_bps=1.0,
            slippage_bps=1.0,
            assumed_total_cost_bps=10.0,
        )

        comp = compare_record(record, eco)

        assert comp.delta_bps == 0.0
        assert comp.record_count == 20
        assert comp.family_id is None

    def test_delta_carries_linkage_fields(self) -> None:
        """CalibrationComparison preserves linkage fields from Franken record."""
        record = FrankenReconciliationRecord(
            observed_avg_shortfall_bps=5.0,
            record_count=1,
            family_id="linked-family",
            variant_id="linked-variant",
            trial_count=7,
            source_path="/path/to/reconciliation.json",
        )
        eco = EconomicsSummary(
            fee_bps=2.0,
            slippage_bps=1.0,
            assumed_total_cost_bps=3.0,
        )

        comp = compare_record(record, eco)

        assert comp.family_id == "linked-family"
        assert comp.variant_id == "linked-variant"
        assert comp.trial_count == 7
        assert comp.source_path == "/path/to/reconciliation.json"
        assert comp.delta_bps == 2.0  # 5 - 3


class TestCompareReconciliationDir:
    """Tests for compare_reconciliation_dir."""

    def test_scans_dir_for_reconciliation_files(self, tmp_path: Path) -> None:
        """Directory scan returns one comparison per found reconciliation file."""
        data = {
            "family_id": "fam",
            "observed_avg_shortfall_bps": 10.0,
            "observed_entry_shortfall_bps": 5.0,
            "observed_exit_shortfall_bps": 5.0,
            "record_count": 10,
        }
        path1 = tmp_path / "run1_reconciliation.json"
        path2 = tmp_path / "run2_reconciliation.json"
        path1.write_text(json.dumps(data))
        path2.write_text(json.dumps({**data, "family_id": "fam2"}))

        comparisons = compare_reconciliation_dir(tmp_path)

        assert len(comparisons) == 2
        ids = {c.family_id for c in comparisons}
        assert ids == {"fam", "fam2"}

    def test_skips_malformed_files(self, tmp_path: Path) -> None:
        """Malformed JSON files are skipped without raising."""
        good = {
            "family_id": "good",
            "observed_avg_shortfall_bps": 5.0,
            "record_count": 1,
        }
        (tmp_path / "good_reconciliation.json").write_text(json.dumps(good))
        (tmp_path / "bad_reconciliation.json").write_text("{ not json }")

        comparisons = compare_reconciliation_dir(tmp_path)

        assert len(comparisons) == 1
        assert comparisons[0].family_id == "good"

    def test_dir_with_no_reconciliation_files_returns_empty(self, tmp_path: Path) -> None:
        """Directory with no reconciliation files returns empty list."""
        (tmp_path / "other.json").write_text(json.dumps({}))

        comparisons = compare_reconciliation_dir(tmp_path)

        assert comparisons == []

    def test_delta_undefined_in_dir_scan_path(self, tmp_path: Path) -> None:
        """Delta is 0 in dir-scan path because EconomicsSummary is not available."""
        data = {
            "observed_avg_shortfall_bps": 25.0,
            "observed_entry_shortfall_bps": 12.0,
            "observed_exit_shortfall_bps": 13.0,
            "record_count": 30,
        }
        path = tmp_path / "reconciliation.json"
        path.write_text(json.dumps(data))

        comparisons = compare_reconciliation_dir(tmp_path)

        assert len(comparisons) == 1
        comp = comparisons[0]
        assert comp.delta_bps == 0.0  # assumed_total_cost_bps unknown
        assert comp.observed_avg_shortfall_bps == 25.0


class TestClassifyCalibrationStatus:
    """Tests for classify_calibration_status."""

    def test_insufficient_data_classification(self):
        """record_count below threshold → insufficient_data."""
        from quantbot.experiment.calibration import classify_calibration_status
        result = classify_calibration_status(delta_bps=0.0, record_count=29)
        assert result == "insufficient_data"

    def test_aligned_classification(self):
        """Sufficient records and |delta| <= 5 bps → aligned."""
        from quantbot.experiment.calibration import classify_calibration_status
        result = classify_calibration_status(delta_bps=3.0, record_count=100)
        assert result == "aligned"

    def test_aligned_at_boundary(self):
        """|delta| == threshold is aligned."""
        from quantbot.experiment.calibration import classify_calibration_status
        result = classify_calibration_status(delta_bps=5.0, record_count=100)
        assert result == "aligned"

    def test_aligned_negative_delta(self):
        """Negative delta is compared by magnitude."""
        from quantbot.experiment.calibration import classify_calibration_status
        result = classify_calibration_status(delta_bps=-4.0, record_count=100)
        assert result == "aligned"

    def test_mild_mismatch_classification(self):
        """5 bps < |delta| <= 15 bps → mild_mismatch."""
        from quantbot.experiment.calibration import classify_calibration_status
        result = classify_calibration_status(delta_bps=10.0, record_count=100)
        assert result == "mild_mismatch"

    def test_mild_mismatch_at_lower_boundary(self):
        """|delta| just above mild threshold."""
        from quantbot.experiment.calibration import classify_calibration_status
        result = classify_calibration_status(delta_bps=5.1, record_count=100)
        assert result == "mild_mismatch"

    def test_mild_mismatch_at_upper_boundary(self):
        """|delta| == material threshold is still mild_mismatch."""
        from quantbot.experiment.calibration import classify_calibration_status
        result = classify_calibration_status(delta_bps=15.0, record_count=100)
        assert result == "mild_mismatch"

    def test_material_mismatch_classification(self):
        """|delta| > 15 bps → material_mismatch."""
        from quantbot.experiment.calibration import classify_calibration_status
        result = classify_calibration_status(delta_bps=20.0, record_count=100)
        assert result == "material_mismatch"

    def test_material_mismatch_just_above_threshold(self):
        """|delta| just above material threshold."""
        from quantbot.experiment.calibration import classify_calibration_status
        result = classify_calibration_status(delta_bps=15.1, record_count=100)
        assert result == "material_mismatch"

    def test_insufficient_data_overrides_mild(self):
        """Insufficient records wins over delta magnitude."""
        from quantbot.experiment.calibration import classify_calibration_status
        result = classify_calibration_status(delta_bps=10.0, record_count=10)
        assert result == "insufficient_data"

    def test_insufficient_data_overrides_material(self):
        """Insufficient records wins over delta magnitude."""
        from quantbot.experiment.calibration import classify_calibration_status
        result = classify_calibration_status(delta_bps=50.0, record_count=5)
        assert result == "insufficient_data"
