"""Tests for quantbot/experiment/offline_edge_data_quality.py

PR G — stdlib-only data quality preflight.  No engine, exchange, or DB imports.
"""

from __future__ import annotations

import ast
import csv
from pathlib import Path

import pytest

from quantbot.experiment.offline_edge_data_quality import (
    SCHEMA_PROFILES,
    build_data_quality_preflight,
    build_data_quality_preflight_for_roles,
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
# Tests — inspect_csv_file prod-path guards
# ---------------------------------------------------------------------------


class TestInspectCsvFileProdPathGuard:
    """inspect_csv_file must fail closed on prod paths (PR G)."""

    def test_refuses_srv_qnty_path(self):
        """inspect_csv_file('/srv/qnty/some.csv') raises ValueError."""
        with pytest.raises(ValueError, match="production boundary"):
            inspect_csv_file(Path("/srv/qnty/some.csv"))

    def test_refuses_traversal_into_srv_qnty(self):
        """inspect_csv_file('/tmp/../../srv/qnty/some.csv') raises ValueError."""
        with pytest.raises(ValueError, match="production boundary"):
            inspect_csv_file(Path("/tmp/../../srv/qnty/some.csv"))

    def test_does_not_refuse_sibling_srv_qnty2(self):
        """inspect_csv_file('/srv/qnty2/some.csv') is NOT prod-refused; falls through to FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            inspect_csv_file(Path("/srv/qnty2/some.csv"))


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
        """Empty input list now raises ValueError (prod-path guard)."""
        with pytest.raises(ValueError, match="At least one input directory path is required"):
            build_data_quality_preflight([])

    def test_refuses_empty_paths(self):
        """build_data_quality_preflight([]) raises ValueError."""
        with pytest.raises(ValueError, match="At least one input directory path is required"):
            build_data_quality_preflight([])


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
# Tests — schema-aware data-quality profiles (PR I)
# ---------------------------------------------------------------------------


class TestBarsProfile:
    """The default "bars" profile must keep requiring timestamp/close/volume."""

    def test_bars_profile_still_requires_timestamp_close_volume(self) -> None:
        result = inspect_csv_file(
            FIXTURE_DIR / "data_quality_clean.csv", profile="bars"
        )
        assert result["profile"] == "bars"
        assert result["required_columns"] == ["close", "timestamp", "volume"]
        assert result["timestamp_column"] == "timestamp"
        assert result["missing_required_columns"] == []

    def test_bars_profile_is_default(self) -> None:
        """Calling inspect_csv_file without profile= behaves like profile='bars'."""
        explicit = inspect_csv_file(
            FIXTURE_DIR / "data_quality_clean.csv", profile="bars"
        )
        default = inspect_csv_file(FIXTURE_DIR / "data_quality_clean.csv")
        assert explicit == default

    def test_bars_profile_missing_close_flagged(self) -> None:
        result = inspect_csv_file(
            FIXTURE_DIR / "data_quality_funding_clean.csv", profile="bars"
        )
        assert "close" in result["missing_required_columns"]
        assert "volume" in result["missing_required_columns"]


class TestFundingProfile:
    """The "funding" profile validates Binance funding-rate CSV shape."""

    def test_funding_profile_accepts_binance_schema_without_close_volume(self) -> None:
        result = inspect_csv_file(
            FIXTURE_DIR / "data_quality_funding_clean.csv", profile="funding"
        )
        assert result["profile"] == "funding"
        assert result["required_columns"] == [
            "fundingRate",
            "fundingTime",
            "symbol",
        ]
        assert result["missing_required_columns"] == []
        assert "close" not in result["required_columns"]
        assert "volume" not in result["required_columns"]

    def test_funding_profile_uses_funding_time_for_min_max_timestamp(self) -> None:
        result = inspect_csv_file(
            FIXTURE_DIR / "data_quality_funding_clean.csv", profile="funding"
        )
        assert result["timestamp_column"] == "fundingTime"
        assert result["min_timestamp"] == "1735689600000"
        assert result["max_timestamp"] == "1735804800000"

    def test_funding_duplicate_timestamp_detected(self) -> None:
        result = inspect_csv_file(
            FIXTURE_DIR / "data_quality_funding_duplicate_timestamp.csv",
            profile="funding",
        )
        assert result["has_duplicate_timestamps"] is True
        assert result["has_non_monotonic_timestamps"] is False

    def test_funding_non_monotonic_detected(self) -> None:
        result = inspect_csv_file(
            FIXTURE_DIR / "data_quality_funding_non_monotonic.csv",
            profile="funding",
        )
        assert result["has_non_monotonic_timestamps"] is True
        assert result["has_duplicate_timestamps"] is False

    def test_funding_null_required_funding_rate_detected(self) -> None:
        result = inspect_csv_file(
            FIXTURE_DIR / "data_quality_funding_null_funding_rate.csv",
            profile="funding",
        )
        assert result["has_null_values"] is True
        assert result["missing_required_columns"] == []

    def test_funding_missing_funding_time_detected(self) -> None:
        result = inspect_csv_file(
            FIXTURE_DIR / "data_quality_funding_missing_funding_time.csv",
            profile="funding",
        )
        assert result["has_timestamp_column"] is False
        assert "fundingTime" in result["missing_required_columns"]
        # min/max timestamp cannot be derived without the fundingTime column
        assert result["min_timestamp"] is None
        assert result["max_timestamp"] is None

    def test_unknown_profile_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown data-quality profile"):
            inspect_csv_file(
                FIXTURE_DIR / "data_quality_funding_clean.csv", profile="bogus"
            )


class TestManifestProfile:
    def test_manifest_profile_has_no_required_columns(self) -> None:
        assert SCHEMA_PROFILES["manifest"]["required_columns"] == set()
        assert SCHEMA_PROFILES["manifest"]["timestamp_column"] is None

    def test_manifest_profile_json_file_inspected_without_crash(
        self, tmp_path: Path
    ) -> None:
        manifest_path = tmp_path / "sample_manifest.json"
        manifest_path.write_text('{"bars": "a.csv", "funding": "b.csv"}')
        result = inspect_input_directory(tmp_path, profile="manifest")
        assert result["file_count"] == 1
        json_entry = result["files"][0]
        assert json_entry["kind"] == "manifest_json"
        assert json_entry["is_valid_json"] is True
        assert json_entry["top_level_key_count"] == 2

    def test_manifest_profile_malformed_json_does_not_crash(
        self, tmp_path: Path
    ) -> None:
        manifest_path = tmp_path / "broken_manifest.json"
        manifest_path.write_text("{not valid json")
        result = inspect_input_directory(tmp_path, profile="manifest")
        json_entry = result["files"][0]
        assert json_entry["kind"] == "manifest_json"
        assert json_entry["is_valid_json"] is False
        assert json_entry["error"] is not None


class TestRoleAwarePreflight:
    """build_data_quality_preflight_for_roles must not leak requirements across roles."""

    def _bars_only_dir(self, tmp_path: Path) -> Path:
        bars_dir = tmp_path / "bars"
        bars_dir.mkdir()
        (bars_dir / "data_quality_clean.csv").write_text(
            (FIXTURE_DIR / "data_quality_clean.csv").read_text()
        )
        return bars_dir

    def _funding_only_dir(self, tmp_path: Path) -> Path:
        funding_dir = tmp_path / "funding"
        funding_dir.mkdir()
        (funding_dir / "data_quality_funding_clean.csv").write_text(
            (FIXTURE_DIR / "data_quality_funding_clean.csv").read_text()
        )
        return funding_dir

    def test_mixed_bars_and_funding_does_not_globally_fail_funding(
        self, tmp_path: Path
    ) -> None:
        bars_dir = self._bars_only_dir(tmp_path)
        funding_dir = self._funding_only_dir(tmp_path)

        result = build_data_quality_preflight_for_roles(
            bars_dir=bars_dir, funding_dir=funding_dir
        )
        # Neither role is missing required columns: bars has timestamp/close/
        # volume, funding has symbol/fundingTime/fundingRate.
        assert result["missing_required_columns_by_role"]["bars"] == []
        assert result["missing_required_columns_by_role"]["funding"] == []
        assert result["readiness_flags"]["has_timestamp_column"] is True
        assert result["readiness_flags"]["by_role"]["funding"][
            "has_timestamp_column"
        ] is True

    def test_bars_dir_missing_close_fails_bars_role_only(
        self, tmp_path: Path
    ) -> None:
        bars_dir = tmp_path / "bars"
        bars_dir.mkdir()
        (bars_dir / "no_close.csv").write_text(
            "timestamp,volume\n2026-01-01T00:00:00Z,100.0\n"
        )
        funding_dir = self._funding_only_dir(tmp_path)

        result = build_data_quality_preflight_for_roles(
            bars_dir=bars_dir, funding_dir=funding_dir
        )
        assert "close" in result["missing_required_columns_by_role"]["bars"]
        assert result["missing_required_columns_by_role"]["funding"] == []
        assert result["readiness_flags"]["by_role"]["funding"][
            "has_timestamp_column"
        ] is True

    def test_funding_dir_missing_close_is_not_a_failure(
        self, tmp_path: Path
    ) -> None:
        """A funding directory missing close/volume must not fail — those
        columns are not part of the funding schema profile."""
        funding_dir = self._funding_only_dir(tmp_path)
        result = build_data_quality_preflight_for_roles(funding_dir=funding_dir)
        assert "close" not in result["missing_required_columns_by_role"]["funding"]
        assert "volume" not in result["missing_required_columns_by_role"]["funding"]
        assert result["readiness_flags"]["by_role"]["funding"][
            "has_timestamp_column"
        ] is True

    def test_funding_dir_missing_funding_time_fails(self, tmp_path: Path) -> None:
        funding_dir = tmp_path / "funding"
        funding_dir.mkdir()
        (funding_dir / "data_quality_funding_missing_funding_time.csv").write_text(
            (
                FIXTURE_DIR / "data_quality_funding_missing_funding_time.csv"
            ).read_text()
        )
        result = build_data_quality_preflight_for_roles(funding_dir=funding_dir)
        assert "fundingTime" in result["missing_required_columns_by_role"]["funding"]
        assert (
            result["readiness_flags"]["by_role"]["funding"]["has_timestamp_column"]
            is False
        )
        assert result["readiness_flags"]["has_timestamp_column"] is False

    def test_readiness_flags_are_role_aware(self, tmp_path: Path) -> None:
        bars_dir = self._bars_only_dir(tmp_path)
        funding_dir = self._funding_only_dir(tmp_path)
        result = build_data_quality_preflight_for_roles(
            bars_dir=bars_dir, funding_dir=funding_dir
        )
        by_role = result["readiness_flags"]["by_role"]
        assert set(by_role.keys()) == {"bars", "funding"}
        for role_flags in by_role.values():
            assert role_flags["has_any_rows"] is True
            assert role_flags["no_null_required_values"] is True

    def test_profile_metadata_appears_in_file_summaries(
        self, tmp_path: Path
    ) -> None:
        bars_dir = self._bars_only_dir(tmp_path)
        funding_dir = self._funding_only_dir(tmp_path)
        result = build_data_quality_preflight_for_roles(
            bars_dir=bars_dir, funding_dir=funding_dir
        )
        for f in result["files"]:
            if f.get("kind") in ("non_csv", "manifest_json"):
                continue
            assert f["profile"] in ("bars", "funding")
            assert "required_columns" in f
            assert "timestamp_column" in f

    def test_roles_dict_present_and_null_for_absent_roles(
        self, tmp_path: Path
    ) -> None:
        bars_dir = self._bars_only_dir(tmp_path)
        result = build_data_quality_preflight_for_roles(bars_dir=bars_dir)
        assert result["roles"]["bars"] is not None
        assert result["roles"]["funding"] is None
        assert result["roles"]["manifest"] is None

    def test_requires_at_least_one_role_dir(self) -> None:
        with pytest.raises(
            ValueError, match="At least one input directory path is required"
        ):
            build_data_quality_preflight_for_roles()

    def test_role_aware_preflight_still_validates(self, tmp_path: Path) -> None:
        """Role-aware summaries must still satisfy validate_data_quality_preflight."""
        bars_dir = self._bars_only_dir(tmp_path)
        result = build_data_quality_preflight_for_roles(bars_dir=bars_dir)
        validate_data_quality_preflight(result)  # no raise

    def test_role_aware_preflight_no_forbidden_edge_content(
        self, tmp_path: Path
    ) -> None:
        bars_dir = self._bars_only_dir(tmp_path)
        funding_dir = self._funding_only_dir(tmp_path)
        result = build_data_quality_preflight_for_roles(
            bars_dir=bars_dir, funding_dir=funding_dir
        )
        for forbidden in ("pnl", "sharpe", "edge", "strategy_performance"):
            assert forbidden not in result
        assert "EDGE_CANDIDATE" not in str(result)


class TestProfileProdPathGuards:
    """Prod-path guard must fail closed for every public helper, all profiles."""

    def test_inspect_csv_file_refuses_srv_qnty_funding_profile(self) -> None:
        with pytest.raises(ValueError, match="production boundary"):
            inspect_csv_file(Path("/srv/qnty/funding/some.csv"), profile="funding")

    def test_inspect_input_directory_refuses_srv_qnty_funding_profile(self) -> None:
        with pytest.raises(ValueError, match="/srv/qnty"):
            inspect_input_directory(
                Path("/srv/qnty/funding_dir"), profile="funding"
            )

    def test_inspect_input_directory_refuses_srv_qnty_manifest_profile(self) -> None:
        with pytest.raises(ValueError, match="/srv/qnty"):
            inspect_input_directory(
                Path("/srv/qnty/manifest_dir"), profile="manifest"
            )

    def test_build_data_quality_preflight_for_roles_refuses_srv_qnty_bars(
        self,
    ) -> None:
        with pytest.raises(ValueError, match="/srv/qnty"):
            build_data_quality_preflight_for_roles(
                bars_dir=Path("/srv/qnty/bars")
            )

    def test_build_data_quality_preflight_for_roles_refuses_srv_qnty_funding(
        self,
    ) -> None:
        with pytest.raises(ValueError, match="/srv/qnty"):
            build_data_quality_preflight_for_roles(
                funding_dir=Path("/srv/qnty/funding")
            )

    def test_build_data_quality_preflight_for_roles_refuses_srv_qnty_manifest(
        self,
    ) -> None:
        with pytest.raises(ValueError, match="/srv/qnty"):
            build_data_quality_preflight_for_roles(
                manifest_dir=Path("/srv/qnty/manifest")
            )


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