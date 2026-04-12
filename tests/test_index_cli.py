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