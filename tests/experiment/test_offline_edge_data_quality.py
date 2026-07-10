"""Tests for quantbot/experiment/offline_edge_data_quality.py

PR B — stdlib-only data quality preflight.  No engine, exchange, or DB imports.
"""

from __future__ import annotations

import ast
import csv
from pathlib import Path

import pytest

from quantbot.experiment.offline_edge_data_quality import (
    build_data_quality_preflight,
    inspect_csv_file,
    inspect_input_directory,
    validate_data_quality_preflight,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FIXTURE_DIR = Path(
    "tests/fixtures/edge_validation_golden"
).resolve()


# ---------------------------------------------------------------------------
# Tests — inspect_csv_file
# ---------------------------------------------------------------------------


class TestInspectCsvFile:
    def test_clean_csv(self) -> None:
        result = inspect_csv_file(FIXTURE_DIR / "data_quality_clean.csv")
        assert result["row_count"] == 5
        assert result["has_timestamp_column"] is True
        assert result["missing_required_columns"] == []
        assert result["has_duplicate_timestamps"] is False
        assert result["has_non_monotonic_timestamps"] is False
        assert result["has_null_values"] is False
        assert result["min_timestamp"] == "2026-01-01T00:00:00Z"
        assert result["max_timestamp"] == "2026-01-02T08:00:00Z"
        assert result["error"] is None

    def test_duplicate_timestamp(self) -> None:
        result = inspect_csv_file(
            FIXTURE_DIR / "data_quality_duplicate_timestamp.csv"
        )
        assert result["row_count"] == 4
        assert result["has_duplicate_timestamps"] is True
        assert result["has_non_monotonic_timestamps"] is False
        assert result["has_null_values"] is False

    def test_non_monotonic_timestamp(self) -> None:
        result = inspect_csv_file(
            FIXTURE_DIR / "data_quality_non_monotonic.csv"
        )
        assert result["row_count"] == 4
        assert result["has_duplicate_timestamps"] is False
        assert result["has_non_monotonic_timestamps"] is True
        assert result["has_null_values"] is False

    def test_null_values(self) -> None:
        result = inspect_csv_file(FIXTURE_DIR / "data_quality_null_values.csv")
        assert result["row_count"] == 4
        assert result["has_null_values"] is True
        assert result["has_duplicate_timestamps"] is False
        assert result["has_non_monotonic_timestamps"] is False

    def test_missing_timestamp_column(self) -> None:
        result = inspect_csv_file(
            FIXTURE_DIR / "data_quality_missing_timestamp.csv"
        )
        assert result["row_count"] == 2
        assert result["has_timestamp_column"] is False
        assert "timestamp" in result["missing_required_columns"]
        assert result["has_null_values"] is False

    def test_non_csv_file_rejected_gracefully(self) -> None:
        """Inspecting a non-CSV text file should not crash."""
        path = FIXTURE_DIR / "data_quality_sample.txt"
        result = inspect_csv_file(path)
        assert isinstance(result, dict)
        assert "error" in result
        # The function catches csv.Error internally; no exception propagates.

    def test_empty_csv_detection(self, tmp_path: Path) -> None:
        """An empty CSV file should report row_count == 0 with no error."""
        empty_path = tmp_path / "empty.csv"
        empty_path.write_text("")
        result = inspect_csv_file(empty_path)
        assert result["row_count"] == 0
        assert result["error"] is None


# ---------------------------------------------------------------------------
# Tests — inspect_input_directory
# ---------------------------------------------------------------------------


class TestInspectInputDirectory:
    def test_directory_summary(self) -> None:
        result = inspect_input_directory(FIXTURE_DIR)
        assert result["file_count"] > 0
        assert result["csv_file_count"] >= 5
        assert result["non_csv_file_count"] >= 1
        assert result["total_row_count"] > 0
        assert result["global_min_timestamp"] is not None
        assert result["global_max_timestamp"] is not None
        assert result["has_duplicate_timestamps"] is True
        assert result["has_non_monotonic_timestamps"] is True
        assert result["has_null_values"] is True
        assert "timestamp" in result["missing_required_columns"]

    def test_directory_deterministic(self) -> None:
        """Two runs on the same directory produce identical results."""
        r1 = inspect_input_directory(FIXTURE_DIR)
        r2 = inspect_input_directory(FIXTURE_DIR)
        assert r1 == r2

    def test_missing_directory_rejected(self) -> None:
        with pytest.raises(FileNotFoundError):
            inspect_input_directory(Path("/tmp/qnty_test_missing_dir_nonexistent"))

    def test_prod_path_refused(self) -> None:
        with pytest.raises(ValueError, match="/srv/qnty"):
            inspect_input_directory(Path("/srv/qnty/some_dir"))

    def test_sibling_prod_path_not_refused(self) -> None:
        """/srv/qnty2 is not under the /srv/qnty boundary, so FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            inspect_input_directory(Path("/srv/qnty2/some_dir"))


# ---------------------------------------------------------------------------
# Tests — build_data_quality_preflight
# ---------------------------------------------------------------------------


class TestBuildDataQualityPreflight:
    def test_preflight_summary(self) -> None:
        result = build_data_quality_preflight([FIXTURE_DIR])
        assert result["data_quality_version"] is not None
        assert result["file_count"] > 0
        assert result["csv_file_count"] > 0
        assert result["total_row_count"] > 0
        assert isinstance(result["readiness_flags"], dict)
        assert "has_any_rows" in result["readiness_flags"]
        assert "has_timestamp_column" in result["readiness_flags"]
        assert "timestamps_monotonic" in result["readiness_flags"]
        assert "no_duplicate_timestamps" in result["readiness_flags"]
        assert "no_null_required_values" in result["readiness_flags"]
        assert "data_quality_preflight_only" in result["readiness_flags"]
        assert result["readiness_flags"]["data_quality_preflight_only"] is True
        assert len(result["files"]) > 0

    def test_preflight_multiple_directories(self) -> None:
        """Listing the same directory twice doubles file counts."""
        single = build_data_quality_preflight([FIXTURE_DIR])
        double = build_data_quality_preflight([FIXTURE_DIR, FIXTURE_DIR])
        assert double["file_count"] == 2 * single["file_count"]
        assert double["csv_file_count"] == 2 * single["csv_file_count"]

    def test_preflight_deterministic(self) -> None:
        r1 = build_data_quality_preflight([FIXTURE_DIR])
        r2 = build_data_quality_preflight([FIXTURE_DIR])
        assert r1 == r2

    def test_preflight_empty_list(self) -> None:
        """Empty input list produces a zero-count summary with conservative flags."""
        result = build_data_quality_preflight([])
        assert result["file_count"] == 0
        assert result["csv_file_count"] == 0
        assert result["total_row_count"] == 0
        assert result["readiness_flags"]["has_any_rows"] is False
        assert result["readiness_flags"]["has_timestamp_column"] is False
        assert result["readiness_flags"]["timestamps_monotonic"] is True
        assert result["readiness_flags"]["no_duplicate_timestamps"] is True
        assert result["readiness_flags"]["no_null_required_values"] is True
        assert result["readiness_flags"]["data_quality_preflight_only"] is True


# ---------------------------------------------------------------------------
# Tests — validate_data_quality_preflight
# ---------------------------------------------------------------------------


class TestValidateDataQualityPreflight:
    def test_valid_summary(self) -> None:
        """A valid preflight summary should not raise."""
        summary = build_data_quality_preflight([FIXTURE_DIR])
        validate_data_quality_preflight(summary)  # no raise

    def test_invalid_version(self) -> None:
        summary = build_data_quality_preflight([FIXTURE_DIR])
        summary["data_quality_version"] = "0.0.0-bogus"
        with pytest.raises(ValueError, match="data_quality_version mismatch"):
            validate_data_quality_preflight(summary)

    def test_missing_readiness_flags(self) -> None:
        summary = build_data_quality_preflight([FIXTURE_DIR])
        del summary["readiness_flags"]
        with pytest.raises(ValueError, match="readiness_flags"):
            validate_data_quality_preflight(summary)


# ---------------------------------------------------------------------------
# Tests — no forbidden imports (AST inspection)
# ---------------------------------------------------------------------------


class TestNoEngineOrExchangeImports:
    def test_no_forbidden_imports(self) -> None:
        """Verify module has no engine/exchange/DB imports using AST inspection."""
        module_path = (
            Path(__file__).resolve().parent.parent.parent
            / "quantbot"
            / "experiment"
            / "offline_edge_data_quality.py"
        )
        assert module_path.exists(), f"Module not found: {module_path}"
        with open(module_path) as f:
            tree = ast.parse(f.read())

        forbidden = {"engine", "exchange", "ccxt", "sqlite", "numpy", "pandas", "paper", "db", "live"}

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name.split(".")[0]
                    assert name not in forbidden, (
                        f"Forbidden import '{alias.name}' found in "
                        f"offline_edge_data_quality.py at line {node.lineno}"
                    )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    name = node.module.split(".")[0]
                    assert name not in forbidden, (
                        f"Forbidden import '{node.module}' found in "
                        f"offline_edge_data_quality.py at line {node.lineno}"
                    )