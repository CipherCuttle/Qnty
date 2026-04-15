"""Tests for quantbot.index_cli module.

Paper mode only - no real trading.
"""

import json
import tempfile
from pathlib import Path

import pytest

from quantbot.experiment.spec import ExperimentSpec
from quantbot.experiment.walkforward_runner import run_walkforward_experiment
from quantbot.index_cli import main


FIXTURE_DIR = Path(__file__).parent / "fixtures"
BTCUSDT_MANIFEST_PATH = FIXTURE_DIR / "BTCUSDT_manifest.json"
BTCUSDT_CSV_PATH = FIXTURE_DIR / "BTCUSDT_8h.csv"


class TestIndexCliArgParsing:
    """Tests for index CLI argument parsing."""

    def test_help_works(self):
        # argparse exits with SystemExit; repo pattern catches it and returns 1
        result = main(["--help"])
        assert result == 1

    def test_no_args_gives_error(self):
        result = main([])
        assert result == 1

    def test_nonexistent_path_gives_error(self, tmp_path):
        result = main([str(tmp_path / "nonexistent.json")])
        assert result == 1


class TestIndexCliWithRealArtifacts:
    """Tests for index CLI with real experiment artifacts."""

    def test_valid_path_returns_0(self, tmp_path):
        """Index CLI with valid artifact path returns 0."""
        out = tmp_path / "experiment"
        spec = ExperimentSpec(
            experiment_name="index-cli-test",
            strategy_name="ThresholdStrategy",
            strategy_params={"threshold": 16500.0, "symbol": "BTCUSDT"},
            fixture_name="BTCUSDT_8h",
        )
        result = run_walkforward_experiment(
            spec=spec,
            manifest_path=BTCUSDT_MANIFEST_PATH,
            csv_path=BTCUSDT_CSV_PATH,
            output_dir=out,
            train_size=100,
            test_size=50,
            step_size=50,
        )
        wf_path = out / "walkforward_result.json"
        assert wf_path.exists()

        cli_result = main([str(wf_path)])
        assert cli_result == 0

    def test_json_output_is_valid(self, tmp_path):
        """Index CLI --json outputs valid JSON."""
        out = tmp_path / "experiment"
        spec = ExperimentSpec(
            experiment_name="index-json-test",
            strategy_name="ThresholdStrategy",
            strategy_params={"threshold": 16500.0, "symbol": "BTCUSDT"},
            fixture_name="BTCUSDT_8h",
        )
        run_walkforward_experiment(
            spec=spec,
            manifest_path=BTCUSDT_MANIFEST_PATH,
            csv_path=BTCUSDT_CSV_PATH,
            output_dir=out,
            train_size=100,
            test_size=50,
            step_size=50,
        )
        wf_path = out / "walkforward_result.json"

        import io
        import sys as _sys

        old_stdout = _sys.stdout
        _sys.stdout = io.StringIO()
        try:
            result = main(["--json", str(wf_path)])
        finally:
            output = _sys.stdout.getvalue()
            _sys.stdout = old_stdout

        assert result == 0
        parsed = json.loads(output)
        assert isinstance(parsed, list)
        assert len(parsed) >= 1
        record = parsed[0]
        assert "experiment_name" in record
        assert "strategy_name" in record
        assert "result_type" in record
        # Verify new trial-family fields are present in JSON output
        assert "family_id" in record
        assert "variant_id" in record
        assert "trial_count" in record

    def test_json_output_includes_trial_family_fields(self, tmp_path):
        """Index CLI --json output includes family_id, variant_id, trial_count."""
        out = tmp_path / "experiment"
        spec = ExperimentSpec(
            experiment_name="json-trial-family-test",
            strategy_name="ThresholdStrategy",
            strategy_params={"threshold": 16500.0, "symbol": "BTCUSDT"},
            fixture_name="BTCUSDT_8h",
            family_id="my-family",
            variant_id="variant-v2",
            trial_count=7,
        )
        run_walkforward_experiment(
            spec=spec,
            manifest_path=BTCUSDT_MANIFEST_PATH,
            csv_path=BTCUSDT_CSV_PATH,
            output_dir=out,
            train_size=100,
            test_size=50,
            step_size=50,
        )
        wf_path = out / "walkforward_result.json"

        import io
        import sys as _sys

        old_stdout = _sys.stdout
        _sys.stdout = io.StringIO()
        try:
            result = main(["--json", str(wf_path)])
        finally:
            output = _sys.stdout.getvalue()
            _sys.stdout = old_stdout

        assert result == 0
        parsed = json.loads(output)
        assert len(parsed) >= 1
        record = parsed[0]
        assert record["family_id"] == "my-family"
        assert record["variant_id"] == "variant-v2"
        assert record["trial_count"] == 7

    def test_by_family_aggregation(self, tmp_path):
        """Index CLI --by-family groups artifacts by family_id and emits summary."""
        # Create two experiments in the same family
        out1 = tmp_path / "exp1"
        out2 = tmp_path / "exp2"
        spec1 = ExperimentSpec(
            experiment_name="family-a-exp1",
            strategy_name="ThresholdStrategy",
            strategy_params={"threshold": 16500.0, "symbol": "BTCUSDT"},
            fixture_name="BTCUSDT_8h",
            family_id="shared-family",
            variant_id="var-1",
            trial_count=2,
        )
        spec2 = ExperimentSpec(
            experiment_name="family-a-exp2",
            strategy_name="ThresholdStrategy",
            strategy_params={"threshold": 17000.0, "symbol": "BTCUSDT"},
            fixture_name="BTCUSDT_8h",
            family_id="shared-family",
            variant_id="var-2",
            trial_count=2,
        )
        run_walkforward_experiment(
            spec=spec1,
            manifest_path=BTCUSDT_MANIFEST_PATH,
            csv_path=BTCUSDT_CSV_PATH,
            output_dir=out1,
            train_size=100,
            test_size=50,
            step_size=50,
        )
        run_walkforward_experiment(
            spec=spec2,
            manifest_path=BTCUSDT_MANIFEST_PATH,
            csv_path=BTCUSDT_CSV_PATH,
            output_dir=out2,
            train_size=100,
            test_size=50,
            step_size=50,
        )

        import io
        import sys as _sys

        old_stdout = _sys.stdout
        _sys.stdout = io.StringIO()
        try:
            result = main(["--by-family", str(out1), str(out2)])
        finally:
            output = _sys.stdout.getvalue()
            _sys.stdout = old_stdout

        assert result == 0
        # Output should contain family summary
        assert "shared-family" in output
        assert "artifact_count" in output or "2" in output

    def test_by_family_json_output(self, tmp_path):
        """Index CLI --by-family --json outputs grouped summary as JSON."""
        out = tmp_path / "experiment"
        spec = ExperimentSpec(
            experiment_name="by-family-json-test",
            strategy_name="ThresholdStrategy",
            strategy_params={"threshold": 16500.0, "symbol": "BTCUSDT"},
            fixture_name="BTCUSDT_8h",
            family_id="test-family",
            variant_id="var-x",
            trial_count=3,
        )
        run_walkforward_experiment(
            spec=spec,
            manifest_path=BTCUSDT_MANIFEST_PATH,
            csv_path=BTCUSDT_CSV_PATH,
            output_dir=out,
            train_size=100,
            test_size=50,
            step_size=50,
        )

        import io
        import sys as _sys

        old_stdout = _sys.stdout
        _sys.stdout = io.StringIO()
        try:
            result = main(["--by-family", "--json", str(out)])
        finally:
            output = _sys.stdout.getvalue()
            _sys.stdout = old_stdout

        assert result == 0
        parsed = json.loads(output)
        assert isinstance(parsed, list)
        assert len(parsed) >= 1
        summary = parsed[0]
        assert summary["family_id"] == "test-family"
        assert summary["artifact_count"] >= 1
        assert "max_trial_count" in summary
        assert "pass_count" in summary
        assert "fail_count" in summary

    def test_text_output_includes_trial_family_columns(self, tmp_path):
        """Index CLI text output includes family_id, variant_id, trial_count columns."""
        out = tmp_path / "experiment"
        spec = ExperimentSpec(
            experiment_name="text-output-test",
            strategy_name="ThresholdStrategy",
            strategy_params={"threshold": 16500.0, "symbol": "BTCUSDT"},
            fixture_name="BTCUSDT_8h",
            family_id="text-family",
            variant_id="var-text",
            trial_count=5,
        )
        run_walkforward_experiment(
            spec=spec,
            manifest_path=BTCUSDT_MANIFEST_PATH,
            csv_path=BTCUSDT_CSV_PATH,
            output_dir=out,
            train_size=100,
            test_size=50,
            step_size=50,
        )
        wf_path = out / "walkforward_result.json"

        import io
        import sys as _sys

        old_stdout = _sys.stdout
        _sys.stdout = io.StringIO()
        try:
            result = main([str(wf_path)])
        finally:
            output = _sys.stdout.getvalue()
            _sys.stdout = old_stdout

        assert result == 0
        lines = output.strip().split("\n")
        # Header line
        header = lines[0]
        assert "family_id" in header
        assert "variant_id" in header
        assert "trial_count" in header
        # Data line
        data_line = lines[1]
        assert "text-family" in data_line
        assert "var-text" in data_line
        assert "5" in data_line


class TestIndexCliByFamilyTriage:
    """Tests for --by-family triage controls: sort, filter, limit."""

    def _run_by_family(self, tmp_path, *extra_args):
        """Helper to run --by-family with JSON capture."""
        import io
        import sys as _sys

        old_stdout = _sys.stdout
        _sys.stdout = io.StringIO()
        try:
            result = main(list(extra_args))
        finally:
            output = _sys.stdout.getvalue()
            _sys.stdout = old_stdout
        return result, output

    def _create_family_experiments(self, tmp_path, family_id, count=1, eligible_for_review=True):
        """Create `count` experiments in the given family."""
        paths = []
        for i in range(count):
            out = tmp_path / f"exp_{family_id}_{i}"
            spec = ExperimentSpec(
                experiment_name=f"{family_id}-exp{i}",
                strategy_name="ThresholdStrategy",
                strategy_params={"threshold": 16500.0 + i, "symbol": "BTCUSDT"},
                fixture_name="BTCUSDT_8h",
                family_id=family_id,
                variant_id=f"var-{i}",
                trial_count=2,
            )
            run_walkforward_experiment(
                spec=spec,
                manifest_path=BTCUSDT_MANIFEST_PATH,
                csv_path=BTCUSDT_CSV_PATH,
                output_dir=out,
                train_size=100,
                test_size=50,
                step_size=50,
            )
            paths.append(out)
        return paths

    def test_sort_by_artifact_count_descending(self, tmp_path):
        """Sort by artifact_count descending: family with more artifacts first."""
        paths1 = self._create_family_experiments(tmp_path, "bigger-family", count=2)
        paths2 = self._create_family_experiments(tmp_path, "smaller-family", count=1)

        all_paths = [str(p) for p in paths1 + paths2]
        import io
        import sys as _sys

        old_stdout = _sys.stdout
        _sys.stdout = io.StringIO()
        try:
            result = main(["--by-family", "--json", "--sort-by", "artifact_count"] + all_paths)
        finally:
            output = _sys.stdout.getvalue()
            _sys.stdout = old_stdout

        assert result == 0
        parsed = json.loads(output)
        assert parsed[0]["family_id"] == "bigger-family"
        assert parsed[1]["family_id"] == "smaller-family"

    def test_eligible_only_filter(self, tmp_path):
        """--eligible-only flag is accepted and filters output."""
        self._create_family_experiments(tmp_path, "family-a", count=1)
        self._create_family_experiments(tmp_path, "family-b", count=1)

        all_paths = [str(tmp_path / p) for p in ["exp_family-a_0", "exp_family-b_0"]]
        import io
        import sys as _sys

        old_stdout = _sys.stdout
        _sys.stdout = io.StringIO()
        try:
            result = main(["--by-family", "--json", "--eligible-only"] + all_paths)
        finally:
            output = _sys.stdout.getvalue()
            _sys.stdout = old_stdout

        assert result == 0
        parsed = json.loads(output)
        # All created experiments are ineligible, so list should be empty
        assert len(parsed) == 0

    def test_ineligible_only_filter(self, tmp_path):
        """--ineligible-only shows all families when experiments are ineligible."""
        paths1 = self._create_family_experiments(tmp_path, "family-a", count=1)
        paths2 = self._create_family_experiments(tmp_path, "family-b", count=1)

        all_paths = [str(p) for p in paths1 + paths2]
        import io
        import sys as _sys

        old_stdout = _sys.stdout
        _sys.stdout = io.StringIO()
        try:
            result = main(["--by-family", "--json", "--ineligible-only"] + all_paths)
        finally:
            output = _sys.stdout.getvalue()
            _sys.stdout = old_stdout

        assert result == 0
        parsed = json.loads(output)
        family_ids = {s["family_id"] for s in parsed}
        assert "family-a" in family_ids
        assert "family-b" in family_ids

    def test_limit_truncates_results(self, tmp_path):
        """--limit N shows only top N families after sort and filter."""
        self._create_family_experiments(tmp_path, "family-a", count=1)
        self._create_family_experiments(tmp_path, "family-b", count=1)
        self._create_family_experiments(tmp_path, "family-c", count=1)

        all_paths = [str(tmp_path / p) for p in ["exp_family-a_0", "exp_family-b_0", "exp_family-c_0"]]

        import io
        import sys as _sys

        old_stdout = _sys.stdout
        _sys.stdout = io.StringIO()
        try:
            result = main(["--by-family", "--json", "--limit", "2"] + all_paths)
        finally:
            output = _sys.stdout.getvalue()
            _sys.stdout = old_stdout

        assert result == 0
        parsed = json.loads(output)
        assert len(parsed) == 2

    def test_eligible_ineligible_mutually_exclusive(self, tmp_path):
        """Passing both --eligible-only and --ineligible-only causes argparse error."""
        self._create_family_experiments(tmp_path, "family-x", count=1)

        import io
        import sys as _sys

        old_stdout = _sys.stdout
        _sys.stdout = io.StringIO()
        try:
            result = main(["--by-family", "--eligible-only", "--ineligible-only", str(tmp_path / "exp_family-x_0")])
        finally:
            _sys.stdout = old_stdout

        assert result == 1

class TestIndexCliReviewSummary:
    """Tests for --review-summary mode."""

    def _capture_output(self, *cli_args):
        """Run CLI with args, capture stdout, return (exit_code, output)."""
        import io
        import sys as _sys
        old_stdout = _sys.stdout
        _sys.stdout = io.StringIO()
        try:
            result = main(list(cli_args))
        finally:
            output = _sys.stdout.getvalue()
            _sys.stdout = old_stdout
        return result, output

    def test_only_eligible_artifacts_appear(self, tmp_path):
        """Review-summary text mode shows only eligible artifacts."""
        # Write two directories with proper walkforward_result.json files
        dir_a = tmp_path / "exp_a"
        dir_b = tmp_path / "exp_b"
        dir_a.mkdir()
        dir_b.mkdir()

        artifact_a = dir_a / "walkforward_result.json"
        artifact_b = dir_b / "walkforward_result.json"

        eligible_data = {
            "experiment_name": "eligible-exp",
            "strategy_name": "ThresholdStrategy",
            "fixture_name": "BTCUSDT_8h",
            "family_id": "family-eligible",
            "variant_id": "var-1",
            "trial_count": 2,
            "fee_bps": 10.0,
            "slippage_bps": 5.0,
            "gate_verdict": {"status": "PASS"},
            "split_count": 3,
            "aggregate_signal_count": 50,
            "return_summary": {"gross_return_total": 0.05, "net_return_total": 0.03, "cost_deduction_total": 0.02},
        }
        ineligible_data = {
            "experiment_name": "ineligible-exp",
            "strategy_name": "ThresholdStrategy",
            "fixture_name": "BTCUSDT_8h",
            "family_id": None,  # missing - makes ineligible
            "variant_id": "var-1",
            "trial_count": 2,
            "fee_bps": 10.0,
            "slippage_bps": 5.0,
            "gate_verdict": {"status": "PASS"},
            "split_count": 3,
            "aggregate_signal_count": 50,
        }

        import json
        artifact_a.write_text(json.dumps(eligible_data))
        artifact_b.write_text(json.dumps(ineligible_data))

        result, output = self._capture_output("--review-summary", str(dir_a), str(dir_b))

        assert result == 0
        assert "eligible-exp" in output
        assert "ineligible-exp" not in output

    def test_json_output_shape_is_stable(self, tmp_path):
        """JSON output has review_summary array, count, and expected record fields."""
        artifact = tmp_path / "walkforward_result.json"
        data = {
            "experiment_name": "shape-test",
            "strategy_name": "ThresholdStrategy",
            "fixture_name": "BTCUSDT_8h",
            "family_id": "shape-family",
            "variant_id": "var-x",
            "trial_count": 3,
            "fee_bps": 10.0,
            "slippage_bps": 5.0,
            "gate_verdict": {"status": "PASS"},
            "split_count": 2,
            "aggregate_signal_count": 30,
            "return_summary": {
                "gross_return_total": 0.12,
                "net_return_total": 0.08,
                "cost_deduction_total": 0.04,
            },
        }
        import json
        artifact.write_text(json.dumps(data))

        result, output = self._capture_output("--review-summary", "--json", str(artifact))

        assert result == 0
        parsed = json.loads(output)
        assert "review_summary" in parsed
        assert "count" in parsed
        assert parsed["count"] == 1

        record = parsed["review_summary"][0]
        expected_fields = [
            "experiment_name", "family_id", "variant_id", "result_type",
            "gate_status", "trial_count", "fee_bps", "slippage_bps",
            "signal_count", "split_count", "gross_return_total",
            "net_return_total", "cost_deduction_total", "artifact_path",
        ]
        for field in expected_fields:
            assert field in record, f"Missing field: {field}"

        assert record["experiment_name"] == "shape-test"
        assert record["family_id"] == "shape-family"
        assert record["variant_id"] == "var-x"
        assert record["trial_count"] == 3
        assert record["gate_status"] == "PASS"
        assert record["gross_return_total"] == 0.12
        assert record["net_return_total"] == 0.08
        assert record["cost_deduction_total"] == 0.04

    def test_text_output_is_compact_and_operator_facing(self, tmp_path):
        """Text output is compact, operator-facing, and contains key fields."""
        artifact = tmp_path / "walkforward_result.json"
        data = {
            "experiment_name": "text-review-test",
            "strategy_name": "ThresholdStrategy",
            "fixture_name": "BTCUSDT_8h",
            "family_id": "text-family",
            "variant_id": "var-text",
            "trial_count": 4,
            "fee_bps": 10.0,
            "slippage_bps": 5.0,
            "gate_verdict": {"status": "PASS"},
            "split_count": 5,
            "aggregate_signal_count": 100,
            "return_summary": {
                "gross_return_total": 0.25,
                "net_return_total": 0.18,
                "cost_deduction_total": 0.07,
            },
        }
        import json
        artifact.write_text(json.dumps(data))

        result, output = self._capture_output("--review-summary", str(artifact))

        assert result == 0
        lines = output.strip().split("\n")
        assert len(lines) >= 2  # header + at least one data line
        header = lines[0]
        # Header should contain key field names
        assert "experiment_name" in header
        assert "family_id" in header
        assert "variant_id" in header
        assert "gate_status" in header
        assert "trial_count" in header
        data_line = lines[1]
        assert "text-review-test" in data_line
        assert "text-family" in data_line
        assert "var-text" in data_line

    def test_no_eligible_artifacts_text_mode(self, tmp_path):
        """Text mode shows clean message when no eligible artifacts exist."""
        artifact = tmp_path / "walkforward_result.json"
        # Create an ineligible artifact (missing family_id)
        data = {
            "experiment_name": "ineligible-only",
            "strategy_name": "ThresholdStrategy",
            "fixture_name": "BTCUSDT_8h",
            "variant_id": "var-1",
            "trial_count": 2,
            "fee_bps": 10.0,
            "slippage_bps": 5.0,
            "gate_verdict": {"status": "PASS"},
            "split_count": 1,
            "aggregate_signal_count": 10,
        }
        import json
        artifact.write_text(json.dumps(data))

        result, output = self._capture_output("--review-summary", str(artifact))

        assert result == 0
        assert "No eligible artifacts for review." in output

    def test_no_eligible_artifacts_json_mode(self, tmp_path):
        """JSON mode outputs empty review_summary array with count=0."""
        artifact = tmp_path / "walkforward_result.json"
        # Create an ineligible artifact (missing family_id)
        data = {
            "experiment_name": "ineligible-json",
            "strategy_name": "ThresholdStrategy",
            "fixture_name": "BTCUSDT_8h",
            "variant_id": "var-1",
            "trial_count": 2,
            "fee_bps": 10.0,
            "slippage_bps": 5.0,
            "gate_verdict": {"status": "PASS"},
            "split_count": 1,
            "aggregate_signal_count": 10,
        }
        import json
        artifact.write_text(json.dumps(data))

        result, output = self._capture_output("--review-summary", "--json", str(artifact))

        assert result == 0
        parsed = json.loads(output)
        assert parsed["review_summary"] == []
        assert parsed["count"] == 0

    def test_legacy_artifact_missing_return_summary(self, tmp_path):
        """Artifacts without return_summary do not break review-summary mode."""
        artifact = tmp_path / "walkforward_result.json"
        data = {
            "experiment_name": "legacy-exp",
            "strategy_name": "ThresholdStrategy",
            "fixture_name": "BTCUSDT_8h",
            "family_id": "legacy-family",
            "variant_id": "var-legacy",
            "trial_count": 1,
            "fee_bps": 10.0,
            "slippage_bps": 5.0,
            "gate_verdict": {"status": "PASS"},
            "split_count": 1,
            "aggregate_signal_count": 5,
            # No return_summary - this is a legacy artifact
        }
        import json
        artifact.write_text(json.dumps(data))

        result, output = self._capture_output("--review-summary", "--json", str(artifact))

        assert result == 0
        parsed = json.loads(output)
        assert parsed["count"] == 1
        record = parsed["review_summary"][0]
        assert record["experiment_name"] == "legacy-exp"
        # Return fields should be None when return_summary is absent
        assert record["gross_return_total"] is None
        assert record["net_return_total"] is None
        assert record["cost_deduction_total"] is None

    def test_legacy_artifact_missing_economics_and_return(self, tmp_path):
        """Artifacts without both economics_summary and return_summary are handled."""
        artifact = tmp_path / "walkforward_result.json"
        data = {
            "experiment_name": "bare-bones-exp",
            "strategy_name": "ThresholdStrategy",
            "fixture_name": "BTCUSDT_8h",
            "family_id": "bare-bones-family",
            "variant_id": "var-bare",
            "trial_count": 1,
            "fee_bps": 10.0,
            "slippage_bps": 5.0,
            "gate_verdict": {"status": "PASS"},
            "split_count": 1,
            "aggregate_signal_count": 5,
            # No return_summary, no economics_summary
        }
        import json
        artifact.write_text(json.dumps(data))

        result, output = self._capture_output("--review-summary", "--json", str(artifact))

        assert result == 0
        parsed = json.loads(output)
        assert parsed["count"] == 1
        record = parsed["review_summary"][0]
        assert record["experiment_name"] == "bare-bones-exp"
        assert record["gross_return_total"] is None
        assert record["net_return_total"] is None
        assert record["cost_deduction_total"] is None
