"""Tests for quantbot/experiment/offline_edge_validation_cli.py

PR A — safe skeleton CLI tests.  No exchange, engine, DB, or paper imports.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import subprocess
import sys
import tempfile

import pytest

CLI_MODULE = "quantbot.experiment.offline_edge_validation_cli"


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    """Run the CLI module with given args, return CompletedProcess."""
    cmd = [sys.executable, "-m", CLI_MODULE] + list(args)
    return subprocess.run(cmd, capture_output=True, text=True)


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------


class TestRefusesWithoutReadOnly:
    def test_refuses_without_read_only(self) -> None:
        """Missing --read-only should exit non-zero with message containing --read-only."""
        result = _run_cli("--output-dir", "/tmp/test_skeleton")
        assert result.returncode != 0
        # argparse writes to stderr
        assert "--read-only" in result.stderr or "--read-only" in result.stdout


class TestRefusesProdPaths:
    def test_refuses_srv_qnty_output(self) -> None:
        # NOT under /tmp → allowlist check fires first with FATAL
        result = _run_cli(
            "--read-only",
            "--output-dir",
            "/srv/qnty/output/paper_pnl_v1",
        )
        assert result.returncode == 3
        assert "must be under" in result.stdout

    def test_refuses_srv_qnty_prefix(self) -> None:
        # NOT under /tmp → allowlist check fires first with FATAL
        result = _run_cli(
            "--read-only",
            "--output-dir",
            "/srv/qnty/anything/else",
        )
        assert result.returncode == 3
        assert "must be under" in result.stdout

    def test_refuses_official_report_path(self) -> None:
        """Test with a path that contains official report pattern.
        Path IS under /tmp, so allowlist passes; caught by pattern check."""
        result = _run_cli(
            "--read-only",
            "--output-dir",
            "/tmp/some/path/paper_verify_report.json",
        )
        assert result.returncode == 3
        assert "official report" in result.stdout


class TestRefusesProdPathsOnFixtureDirs:
    def test_refuses_bars_dir_prod(self) -> None:
        result = _run_cli(
            "--read-only",
            "--output-dir",
            "/tmp/safe_output",
            "--bars-dir",
            "/srv/qnty/data/bars",
        )
        assert result.returncode == 3
        assert "Refusing" in result.stdout

    def test_refuses_funding_dir_prod(self) -> None:
        result = _run_cli(
            "--read-only",
            "--output-dir",
            "/tmp/safe_output",
            "--funding-dir",
            "/srv/qnty/data/funding",
        )
        assert result.returncode == 3
        assert "Refusing" in result.stdout

    def test_refuses_manifest_dir_official_report(self) -> None:
        result = _run_cli(
            "--read-only",
            "--output-dir",
            "/tmp/safe_output",
            "--manifest-dir",
            "/tmp/data/official_report/v1",
        )
        assert result.returncode == 3
        assert "official report" in result.stdout


class TestAcceptsTmpOutput:
    def test_accepts_tmp_output_with_fixtures(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_cli(
                "--read-only",
                "--output-dir",
                tmpdir,
                "--bars-dir",
                "/tmp/fake_bars",
                "--funding-dir",
                "/tmp/fake_funding",
                "--manifest-dir",
                "/tmp/fake_manifest",
            )
            assert result.returncode == 0
            receipt_path = os.path.join(tmpdir, "validation_receipt.json")
            assert os.path.exists(receipt_path)


class TestReceiptContents:
    def test_receipt_contains_required_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_cli(
                "--read-only",
                "--output-dir",
                tmpdir,
            )
            assert result.returncode == 0
            receipt_path = os.path.join(tmpdir, "validation_receipt.json")
            with open(receipt_path) as f:
                receipt = json.load(f)
            assert "validation_receipt" in receipt
            assert "input_manifest_fingerprint" in receipt
            assert "cost_model_assumptions" in receipt
            assert "per_stage_metrics" in receipt
            assert "final_verdict" in receipt

    def test_final_verdict_is_skeleton_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_cli(
                "--read-only",
                "--output-dir",
                tmpdir,
            )
            assert result.returncode == 0
            receipt_path = os.path.join(tmpdir, "validation_receipt.json")
            with open(receipt_path) as f:
                receipt = json.load(f)
            assert receipt["final_verdict"] in ("SKELETON_ONLY", "INCONCLUSIVE")
            assert receipt["final_verdict"] != "EDGE_CANDIDATE"

    def test_receipt_tool_name_is_offline_edge_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_cli(
                "--read-only",
                "--output-dir",
                tmpdir,
            )
            assert result.returncode == 0
            receipt_path = os.path.join(tmpdir, "validation_receipt.json")
            with open(receipt_path) as f:
                receipt = json.load(f)
            assert receipt["validation_receipt"]["tool_name"] == "offline_edge_validation"


class TestNoExchangeModules:
    def test_no_exchange_modules_imported(self) -> None:
        """Verify that importing the CLI doesn't pull in exchange modules."""
        spec = importlib.util.find_spec(
            "quantbot.experiment.offline_edge_validation_cli"
        )
        assert spec is not None

        check_script = (
            "import sys; "
            "sys.modules.pop('quantbot.experiment.offline_edge_validation_cli', None); "
            "from quantbot.experiment.offline_edge_validation_cli import main; "
            "mods = [m for m in sys.modules.keys() "
            "       if 'exchange' in m or 'ccxt' in m]; "
            "print(f'EXCHANGE_MODS:{mods}'); "
            "assert not mods, f'Exchange modules found: {mods}'"
        )
        result = subprocess.run(
            [sys.executable, "-c", check_script],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"Exchange import check failed: {result.stderr}"
        )


class TestFixtureSha256Unchanged:
    def test_fixture_sha256_unchanged(self) -> None:
        """Verify test fixture SHAs are unchanged - placeholder for future fixtures."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a dummy fixture file
            fixture_file = os.path.join(tmpdir, "test_bars.csv")
            with open(fixture_file, "w") as f:
                f.write("timestamp,open,high,low,close,volume\n")

            sha_before = hashlib.sha256(
                open(fixture_file, "rb").read()
            ).hexdigest()

            output_dir = os.path.join(tmpdir, "output")
            os.makedirs(output_dir)

            result = _run_cli(
                "--read-only",
                "--output-dir",
                output_dir,
                "--bars-dir",
                tmpdir,
            )
            assert result.returncode == 0

            sha_after = hashlib.sha256(
                open(fixture_file, "rb").read()
            ).hexdigest()
            assert sha_before == sha_after, (
                "Fixture file was mutated by CLI run"
            )


class TestRefusesNonTempOutput:
    def test_refuses_output_outside_tmp(self) -> None:
        """--output-dir outside /tmp should be refused by positive allowlist."""
        result = _run_cli(
            "--read-only",
            "--output-dir",
            "/home/swirky/qnty-test-output",
        )
        assert result.returncode == 3
        assert "must be under" in result.stdout or "/tmp" in result.stdout

    def test_refuses_path_traversal_to_srv_qnty(self) -> None:
        """Path traversal /tmp/../../srv/qnty/... resolves to /srv/qnty/... and is refused."""
        import os
        traversal_path = os.path.join("/tmp", "..", "..", "srv", "qnty", "output")
        result = _run_cli(
            "--read-only",
            "--output-dir",
            traversal_path,
        )
        # After realpath resolution: /tmp/../../srv/qnty/output -> /srv/qnty/output
        # Refused by allowlist (not under /tmp) and/or prod-path check
        assert result.returncode == 3
        assert "Refusing" in result.stdout or "must be under" in result.stdout

    def test_refuses_path_traversal_outside_tmp(self) -> None:
        """Path traversal /tmp/../etc -> resolves to /etc, not under /tmp."""
        import os
        traversal_path = os.path.join("/tmp", "..", "etc", "qnty-test")
        result = _run_cli(
            "--read-only",
            "--output-dir",
            traversal_path,
        )
        # After realpath: /tmp/../etc -> /etc, refused by allowlist
        assert result.returncode == 3


class TestRefusesTmpBoundaryBypass:
    """Output paths that look like /tmp but are not actually under /tmp."""

    def test_refuses_tmp_evil(self) -> None:
        result = _run_cli("--read-only", "--output-dir", "/tmp_evil")
        assert result.returncode == 3
        assert "must be under" in result.stdout or "/tmp" in result.stdout

    def test_refuses_tmp123(self) -> None:
        result = _run_cli("--read-only", "--output-dir", "/tmp123")
        assert result.returncode == 3
        assert "must be under" in result.stdout

    def test_refuses_tmp_not_actually_tmp(self) -> None:
        result = _run_cli("--read-only", "--output-dir", "/tmp-not-actually-tmp")
        assert result.returncode == 3
        assert "must be under" in result.stdout

    def test_accepts_tmp_nested_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_cli(
                "--read-only",
                "--output-dir",
                os.path.join(tmpdir, "qnty-valid-output"),
            )
            assert result.returncode == 0
            receipt_path = os.path.join(tmpdir, "qnty-valid-output", "validation_receipt.json")
            assert os.path.exists(receipt_path)