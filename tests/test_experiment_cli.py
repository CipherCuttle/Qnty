"""Tests for quantbot.experiment_cli module.

Paper mode only - no real trading.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from quantbot.experiment_cli import main


FIXTURE_DIR = Path(__file__).parent / "fixtures"


class TestExperimentCliArgParsing:
    def test_missing_fixture_exits_1(self):
        result = main(["--strategy", "ThresholdStrategy", "--out", "/tmp/out"])
        assert result == 1

    def test_missing_strategy_exits_1(self):
        result = main(["--fixture", "btcusdt-8h", "--out", "/tmp/out"])
        assert result == 1

    def test_missing_out_exits_1(self):
        result = main(["--fixture", "btcusdt-8h", "--strategy", "ThresholdStrategy"])
        assert result == 1

    def test_unknown_fixture_exits_1(self):
        result = main([
            "--fixture", "nonexistent-fixture",
            "--strategy", "ThresholdStrategy",
            "--out", "/tmp/out",
        ])
        assert result == 1

    def test_unknown_strategy_exits_1(self, tmp_path):
        out = tmp_path / "out"
        out.mkdir()
        result = main([
            "--fixture", "btcusdt-8h",
            "--strategy", "NotAStrategy",
            "--out", str(out),
        ])
        assert result == 1

    def test_valid_params_accepted(self, tmp_path):
        out = tmp_path / "out"
        out.mkdir()
        result = main([
            "--fixture", "btcusdt-8h",
            "--strategy", "ThresholdStrategy",
            "--param", "threshold=16500.0",
            "--out", str(out),
        ])
        # Experiment succeeds when strategy is properly registered
        assert result == 0

    def test_multiple_params_accepted(self, tmp_path):
        out = tmp_path / "out"
        out.mkdir()
        result = main([
            "--fixture", "btcusdt-8h",
            "--strategy", "ThresholdStrategy",
            "--param", "threshold=16500.0",
            "--param", "symbol=BTCUSDT",
            "--out", str(out),
        ])
        assert result == 0


class TestExperimentCliEndToEnd:
    def test_experiment_cli_produces_result(self, tmp_path):
        """qnty-experiment on btcusdt-8h with ThresholdStrategy produces receipt."""
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        result = subprocess.run(
            [
                sys.executable, "-m", "quantbot.experiment_cli",
                "--fixture", "btcusdt-8h",
                "--strategy", "ThresholdStrategy",
                "--param", "threshold=16500.0",
                "--param", "symbol=BTCUSDT",
                "--out", str(out_dir),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"CLI failed: {result.stderr!r}"
        receipt_path = out_dir / "receipt.json"
        assert receipt_path.exists(), "receipt.json was not produced"

        import json
        receipt = json.loads(receipt_path.read_text())
        assert receipt["bar_count"] == 2190
        assert receipt["signal_count"] >= 0

    def test_experiment_cli_experiment_name_default(self, tmp_path):
        """Default experiment name is {strategy}_{fixture}."""
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        result = subprocess.run(
            [
                sys.executable, "-m", "quantbot.experiment_cli",
                "--fixture", "btcusdt-8h",
                "--strategy", "ThresholdStrategy",
                "--param", "threshold=16500.0",
                "--out", str(out_dir),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        output = result.stdout
        assert "ThresholdStrategy_btcusdt-8h" in output

    def test_experiment_cli_custom_experiment_name(self, tmp_path):
        """Custom experiment name is used when --experiment-name is passed."""
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        result = subprocess.run(
            [
                sys.executable, "-m", "quantbot.experiment_cli",
                "--fixture", "btcusdt-8h",
                "--strategy", "ThresholdStrategy",
                "--param", "threshold=16500.0",
                "--experiment-name", "my-custom-exp",
                "--out", str(out_dir),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "my-custom-exp" in result.stdout

    def test_experiment_cli_invalid_param_format(self, tmp_path):
        """Invalid --param format exits with code 1."""
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        result = subprocess.run(
            [
                sys.executable, "-m", "quantbot.experiment_cli",
                "--fixture", "btcusdt-8h",
                "--strategy", "ThresholdStrategy",
                "--param", "invalid-no-equals",
                "--out", str(out_dir),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1
        assert "Invalid param format" in result.stderr

    def test_experiment_cli_prints_result_path(self, tmp_path):
        """CLI stdout contains the experiment_result.json path."""
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        result = subprocess.run(
            [
                sys.executable, "-m", "quantbot.experiment_cli",
                "--fixture", "btcusdt-8h",
                "--strategy", "ThresholdStrategy",
                "--param", "threshold=16500.0",
                "--out", str(out_dir),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        expected_result_path = str(out_dir / "experiment_result.json")
        assert expected_result_path in result.stdout
