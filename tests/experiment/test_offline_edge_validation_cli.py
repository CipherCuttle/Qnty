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
from pathlib import Path

import pytest

from quantbot.experiment.offline_edge_input_manifest import (
    discover_input_files,
    compute_input_manifest_fingerprint,
)

CLI_MODULE = "quantbot.experiment.offline_edge_validation_cli"

FIXTURE_DIR = Path(
    "tests/fixtures/edge_validation_golden"
).resolve()


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
            # Create actual fixture directories with at least one file
            bars_dir = os.path.join(tmpdir, "bars")
            funding_dir = os.path.join(tmpdir, "funding")
            manifest_dir = os.path.join(tmpdir, "manifest")
            os.makedirs(bars_dir)
            os.makedirs(funding_dir)
            os.makedirs(manifest_dir)
            # Write dummy fixture files so CLI can discover them
            with open(os.path.join(bars_dir, "bars.csv"), "w") as f:
                f.write("timestamp,open,high,low,close,volume\n")
            with open(os.path.join(funding_dir, "funding.csv"), "w") as f:
                f.write("timestamp,funding_rate\n")

            result = _run_cli(
                "--read-only",
                "--output-dir",
                tmpdir,
                "--bars-dir",
                bars_dir,
                "--funding-dir",
                funding_dir,
                "--manifest-dir",
                manifest_dir,
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


class TestInputManifestFingerprint:
    """Tests for input_manifest_fingerprint in CLI output."""

    def test_cli_with_fixture_dirs_writes_non_placeholder_fingerprint(self) -> None:
        """CLI with fixture dirs computes real fingerprint (not PLACEHOLDER)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_cli(
                "--read-only",
                "--output-dir",
                tmpdir,
                "--bars-dir",
                str(FIXTURE_DIR),
                "--funding-dir",
                str(FIXTURE_DIR),
                "--manifest-dir",
                str(FIXTURE_DIR),
            )
            assert result.returncode == 0
            receipt_path = os.path.join(tmpdir, "validation_receipt.json")
            with open(receipt_path) as f:
                receipt = json.load(f)
            fp = receipt["input_manifest_fingerprint"]
            assert fp != "PLACEHOLDER_SKELETON_NO_OP"
            assert len(fp) == 64

    def test_cli_no_input_dirs_still_placeholder_fingerprint(self) -> None:
        """CLI with no input dirs still writes PLACEHOLDER_SKELETON_NO_OP."""
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
            assert receipt["input_manifest_fingerprint"] == "PLACEHOLDER_SKELETON_NO_OP"

    def test_cli_with_fixture_dirs_final_verdict_still_skeleton_only(self) -> None:
        """final_verdict remains SKELETON_ONLY even with fixture dirs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_cli(
                "--read-only",
                "--output-dir",
                tmpdir,
                "--bars-dir",
                str(FIXTURE_DIR),
            )
            assert result.returncode == 0
            receipt_path = os.path.join(tmpdir, "validation_receipt.json")
            with open(receipt_path) as f:
                receipt = json.load(f)
            assert receipt["final_verdict"] == "SKELETON_ONLY"
            assert receipt["final_verdict"] != "EDGE_CANDIDATE"

    def test_cli_refuses_srv_qnty_path_via_bars_dir(self) -> None:
        """Using --bars-dir pointing under /srv/qnty fails."""
        result = _run_cli(
            "--read-only",
            "--output-dir",
            "/tmp/safe_output",
            "--bars-dir",
            "/srv/qnty/data/bars",
        )
        assert result.returncode == 3
        assert "Refusing" in result.stdout

    def test_cli_refuses_srv_qnty_path_via_funding_dir(self) -> None:
        """Using --funding-dir pointing under /srv/qnty fails."""
        result = _run_cli(
            "--read-only",
            "--output-dir",
            "/tmp/safe_output",
            "--funding-dir",
            "/srv/qnty/data/funding",
        )
        assert result.returncode == 3
        assert "Refusing" in result.stdout

    def test_cli_refuses_srv_qnty_path_via_manifest_dir(self) -> None:
        """Using --manifest-dir pointing under /srv/qnty fails."""
        result = _run_cli(
            "--read-only",
            "--output-dir",
            "/tmp/safe_output",
            "--manifest-dir",
            "/srv/qnty/manifests/v1",
        )
        assert result.returncode == 3
        assert "Refusing" in result.stdout

    def test_cli_fingerprint_deterministic_across_invocations(self) -> None:
        """Fingerprint is deterministic across separate CLI invocations."""
        with tempfile.TemporaryDirectory() as tmpdir1:
            result1 = _run_cli(
                "--read-only",
                "--output-dir",
                tmpdir1,
                "--bars-dir",
                str(FIXTURE_DIR),
            )
            assert result1.returncode == 0

            with tempfile.TemporaryDirectory() as tmpdir2:
                result2 = _run_cli(
                    "--read-only",
                    "--output-dir",
                    tmpdir2,
                    "--bars-dir",
                    str(FIXTURE_DIR),
                )
                assert result2.returncode == 0

                with open(os.path.join(tmpdir1, "validation_receipt.json")) as f:
                    r1 = json.load(f)
                with open(os.path.join(tmpdir2, "validation_receipt.json")) as f:
                    r2 = json.load(f)
                assert r1["input_manifest_fingerprint"] == r2["input_manifest_fingerprint"]


class TestInputManifestSummaryInReceipt:
    """Tests for input_manifest_summary in receipt when fixture dirs provided."""

    def test_summary_present_when_fixture_dirs_provided(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_cli(
                "--read-only",
                "--output-dir",
                tmpdir,
                "--bars-dir",
                str(FIXTURE_DIR),
            )
            assert result.returncode == 0
            with open(os.path.join(tmpdir, "validation_receipt.json")) as f:
                receipt = json.load(f)
            assert "input_manifest_summary" in receipt
            summary = receipt["input_manifest_summary"]
            assert "file_count" in summary
            assert summary["file_count"] > 0
            assert "files" in summary
            assert "fingerprint" in summary
            assert len(summary["fingerprint"]) == 64

    def test_summary_not_present_without_fixture_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_cli(
                "--read-only",
                "--output-dir",
                tmpdir,
            )
            assert result.returncode == 0
            with open(os.path.join(tmpdir, "validation_receipt.json")) as f:
                receipt = json.load(f)
            assert "input_manifest_summary" not in receipt

    def test_summary_fingerprint_matches_top_level(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_cli(
                "--read-only",
                "--output-dir",
                tmpdir,
                "--bars-dir",
                str(FIXTURE_DIR),
            )
            assert result.returncode == 0
            with open(os.path.join(tmpdir, "validation_receipt.json")) as f:
                receipt = json.load(f)
            assert receipt["input_manifest_summary"]["fingerprint"] == receipt["input_manifest_fingerprint"]


class TestInputManifestFingerprintMatchesDirect:
    """Verify CLI's fingerprint matches a direct call to discover_input_files."""

    def test_cli_fingerprint_matches_direct_computation(self) -> None:
        """Fingerprint from CLI run matches directly calling discover_input_files + compute."""
        discovered = discover_input_files([FIXTURE_DIR])
        expected_fp = compute_input_manifest_fingerprint(discovered)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_cli(
                "--read-only",
                "--output-dir",
                tmpdir,
                "--bars-dir",
                str(FIXTURE_DIR),
                "--funding-dir",
                str(FIXTURE_DIR),
                "--manifest-dir",
                str(FIXTURE_DIR),
            )
            assert result.returncode == 0
            with open(os.path.join(tmpdir, "validation_receipt.json")) as f:
                receipt = json.load(f)
            assert receipt["input_manifest_fingerprint"] == expected_fp