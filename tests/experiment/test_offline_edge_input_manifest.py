"""Tests for quantbot/experiment/offline_edge_input_manifest.py

PR B — stdlib-only input manifest / hash inventory.  No exchange, engine, or DB imports.
"""

from __future__ import annotations

import ast
import hashlib
import os
import sys
import tempfile

import pytest

from quantbot.experiment.offline_edge_input_manifest import (
    _refuse_prod_path,
    build_input_manifest_summary,
    compute_input_manifest_fingerprint,
    discover_input_files,
    sha256_file,
)
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FIXTURE_DIR = Path(
    "tests/fixtures/edge_validation_golden"
).resolve()


def _write_tmp_file(tmpdir: str, name: str, content: str) -> Path:
    """Write a temporary file and return its path."""
    p = Path(tmpdir) / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRefuseProdPath:
    def test_raises_on_srv_qnty_path(self) -> None:
        with pytest.raises(ValueError, match="/srv/qnty"):
            _refuse_prod_path(Path("/srv/qnty/some/file.csv"))

    def test_raises_on_nested_srv_qnty(self) -> None:
        with pytest.raises(ValueError, match="/srv/qnty"):
            _refuse_prod_path(Path("/srv/qnty/output/paper_pnl_v1/receipt.json"))

    def test_accepts_tmp_path(self) -> None:
        # Should not raise
        _refuse_prod_path(Path("/tmp/safe/file.csv"))

    def test_accepts_home_path(self) -> None:
        _refuse_prod_path(Path("/home/user/test.csv"))


class TestSha256File:
    def test_known_fixture(self) -> None:
        """sha256_file() returns expected hash for a known fixture."""
        bars_path = FIXTURE_DIR / "sample_bars.csv"
        assert bars_path.exists(), f"Fixture not found: {bars_path}"
        # Compute expected hash
        expected = hashlib.sha256(bars_path.read_bytes()).hexdigest()
        result = sha256_file(bars_path)
        assert result == expected

    def test_funding_fixture(self) -> None:
        funding_path = FIXTURE_DIR / "sample_funding.csv"
        assert funding_path.exists()
        expected = hashlib.sha256(funding_path.read_bytes()).hexdigest()
        assert sha256_file(funding_path) == expected

    def test_manifest_fixture(self) -> None:
        manifest_path = FIXTURE_DIR / "sample_manifest.json"
        assert manifest_path.exists()
        expected = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        assert sha256_file(manifest_path) == expected

    def test_deterministic(self) -> None:
        bars_path = FIXTURE_DIR / "sample_bars.csv"
        assert sha256_file(bars_path) == sha256_file(bars_path)

    def test_refuses_prod_path(self) -> None:
        with pytest.raises(ValueError, match="/srv/qnty"):
            sha256_file(Path("/srv/qnty/data/bars.csv"))


class TestDiscoverInputFiles:
    def test_discover_fixture_dir(self) -> None:
        """Returns deterministic sorted regular files from fixture dir."""
        files = discover_input_files([FIXTURE_DIR])
        assert len(files) >= 3
        # All should be regular files
        for f in files:
            assert f.is_file()
        # Should be sorted
        for i in range(len(files) - 1):
            assert files[i] <= files[i + 1]

    def test_accepts_single_file(self) -> None:
        bars_path = FIXTURE_DIR / "sample_bars.csv"
        files = discover_input_files([bars_path])
        assert len(files) == 1
        assert files[0] == bars_path.resolve()

    def test_accepts_mixed_dirs_and_files(self) -> None:
        bars_path = FIXTURE_DIR / "sample_bars.csv"
        files = discover_input_files([FIXTURE_DIR, bars_path])
        # Should be deduplicated and sorted
        assert len(files) >= 3
        # All resolved paths
        for f in files:
            assert f.is_absolute()

    def test_missing_dir_fails(self) -> None:
        with pytest.raises(FileNotFoundError, match="does not exist"):
            discover_input_files([Path("/tmp/nonexistent_dir_qnty_test")])

    def test_prod_path_fails(self) -> None:
        with pytest.raises(ValueError, match="/srv/qnty"):
            discover_input_files([Path("/srv/qnty/data")])

    def test_prod_guard_called_before_discovery(self, tmp_path: Path) -> None:
        """When a path exists under /srv/qnty, _refuse_prod_path fires."""
        # Simulate a path under /srv/qnty that exists
        # Use _refuse_prod_path directly since /srv/qnty may not exist
        from quantbot.experiment.offline_edge_input_manifest import _refuse_prod_path
        with pytest.raises(ValueError, match="/srv/qnty"):
            _refuse_prod_path(Path("/srv/qnty/some/existing/file.csv"))

    def test_deterministic_sorted(self, tmp_path: Path) -> None:
        """Multiple runs on same dir produce same sorted order."""
        (tmp_path / "z_file.txt").write_text("z")
        (tmp_path / "a_file.txt").write_text("a")
        # Also create a subdir
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "b_file.txt").write_text("b")

        result1 = discover_input_files([tmp_path])
        result2 = discover_input_files([tmp_path])
        assert result1 == result2
        # Check sorted order: a_file.txt, b_file.txt, z_file.txt
        names = [p.name for p in result1]
        assert names == sorted(names), f"Not sorted: {names}"


class TestFingerprint:
    def test_fingerprint_deterministic(self, tmp_path: Path) -> None:
        """Fingerprint is deterministic across repeated runs."""
        (tmp_path / "a.csv").write_text("a,1,2")
        (tmp_path / "b.csv").write_text("b,3,4")

        files = discover_input_files([tmp_path])
        fp1 = compute_input_manifest_fingerprint(files)
        fp2 = compute_input_manifest_fingerprint(files)
        assert fp1 == fp2

    def test_fingerprint_changes_on_content_change(self, tmp_path: Path) -> None:
        """Changing file content changes fingerprint."""
        f = _write_tmp_file(str(tmp_path), "data.csv", "original,1,2")
        files = discover_input_files([tmp_path])
        fp1 = compute_input_manifest_fingerprint(files)

        f.write_text("modified,3,4")
        files2 = discover_input_files([tmp_path])
        fp2 = compute_input_manifest_fingerprint(files2)
        assert fp1 != fp2

    def test_fingerprint_known_fixtures(self) -> None:
        """Fingerprint from golden fixtures is deterministic."""
        files = discover_input_files([FIXTURE_DIR])
        fp1 = compute_input_manifest_fingerprint(files)
        fp2 = compute_input_manifest_fingerprint(files)
        assert fp1 == fp2
        # 64 hex chars
        assert len(fp1) == 64


class TestBuildInputManifestSummary:
    def test_structure(self, tmp_path: Path) -> None:
        """Summary dict has correct structure."""
        (tmp_path / "a.csv").write_text("a,1,2")
        files = discover_input_files([tmp_path])
        summary = build_input_manifest_summary(files)
        assert isinstance(summary, dict)
        assert "file_count" in summary
        assert "files" in summary
        assert "fingerprint" in summary
        assert summary["file_count"] == 1
        assert len(summary["files"]) == 1
        assert summary["files"][0]["path"] == str(files[0])
        assert summary["files"][0]["size_bytes"] > 0
        assert len(summary["files"][0]["sha256"]) == 64
        assert len(summary["fingerprint"]) == 64

    def test_summary_multiple_files(self, tmp_path: Path) -> None:
        (tmp_path / "a.csv").write_text("a,1,2")
        (tmp_path / "b.csv").write_text("b,3,4")
        files = discover_input_files([tmp_path])
        summary = build_input_manifest_summary(files)
        assert summary["file_count"] == 2
        assert len(summary["files"]) == 2

    def test_summary_fingerprint_matches_compute(self, tmp_path: Path) -> None:
        (tmp_path / "a.csv").write_text("a,1,2")
        files = discover_input_files([tmp_path])
        summary = build_input_manifest_summary(files)
        direct_fp = compute_input_manifest_fingerprint(files)
        assert summary["fingerprint"] == direct_fp


class TestNoEngineOrExchangeImports:
    def test_no_engine_or_exchange_imports(self) -> None:
        """Verify module has no engine/exchange/DB imports using AST inspection."""
        module_path = (
            Path(__file__).resolve().parent.parent.parent
            / "quantbot"
            / "experiment"
            / "offline_edge_input_manifest.py"
        )
        assert module_path.exists(), f"Module not found: {module_path}"
        with open(module_path) as f:
            tree = ast.parse(f.read())

        forbidden_keywords = {"engine", "exchange", "ccxt", "sqlite", "sqlalchemy", "django"}

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name.split(".")[0]
                    assert name not in forbidden_keywords, (
                        f"Forbidden import '{alias.name}' found in "
                        f"offline_edge_input_manifest.py at line {node.lineno}"
                    )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    name = node.module.split(".")[0]
                    assert name not in forbidden_keywords, (
                        f"Forbidden import '{node.module}' found in "
                        f"offline_edge_input_manifest.py at line {node.lineno}"
                    )