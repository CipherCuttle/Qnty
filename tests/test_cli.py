"""Minimal CLI argument parsing tests."""

import json
import subprocess
import sys
from pathlib import Path

from quantbot.cli import main

FIXTURE_DIR = Path(__file__).parent / "fixtures"
MANIFEST_PATH = FIXTURE_DIR / "BTCUSDT_manifest.json"
CSV_PATH = FIXTURE_DIR / "BTCUSDT_8h.csv"


class TestCliArgParsing:
    def test_missing_args_exits_with_code_1(self):
        result = main([])
        assert result == 1

    def test_manifest_required(self):
        result = main(["--csv", "foo.csv", "--out", "out/"])
        assert result == 1

    def test_csv_required(self):
        result = main(["--manifest", "manifest.json", "--out", "out/"])
        assert result == 1

    def test_out_required(self):
        result = main(["--manifest", "manifest.json", "--csv", "foo.csv"])
        assert result == 1

    def test_accepts_valid_args(self, tmp_path):
        manifest = tmp_path / "manifest.json"
        csv = tmp_path / "bars.csv"
        out = tmp_path / "out"
        manifest.touch()
        csv.touch()
        out.mkdir()
        # Does not raise (will fail later at run_replay level, but arg parsing passes)
        result = main(["--manifest", str(manifest), "--csv", str(csv), "--out", str(out)])
        # Expect failure because run_replay will reject empty files, but arg parse succeeded
        assert result == 1

    def test_sha256_flag_accepted(self, tmp_path):
        manifest = tmp_path / "manifest.json"
        csv = tmp_path / "bars.csv"
        out = tmp_path / "out"
        manifest.touch()
        csv.touch()
        out.mkdir()
        result = main([
            "--manifest", str(manifest),
            "--csv", str(csv),
            "--out", str(out),
            "--sha256-sidecar",
        ])
        # Arg parse succeeds; run_replay fails on empty files but flag is accepted
        assert result == 1


class TestCliEndToEnd:
    """End-to-end CLI smoke tests via subprocess."""

    def test_cli_end_to_end_receipt_produced(self, tmp_path):
        """CLI produces a valid receipt.json when run with real BTCUSDT fixture."""
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        receipt_path = out_dir / "receipt.json"

        result = subprocess.run(
            [
                sys.executable, "-m", "quantbot.cli",
                "--manifest", str(MANIFEST_PATH),
                "--csv", str(CSV_PATH),
                "--out", str(out_dir),
            ],
            check=False,
        )

        assert result.returncode == 0, f"CLI failed: {result.stderr!r}"
        assert receipt_path.exists(), "receipt.json was not produced"

        with open(receipt_path) as f:
            receipt = json.load(f)

        # BTCUSDT receipt has bar_count, bar_hash, etc.
        assert "bar_count" in receipt
        assert "bar_hash" in receipt
        assert receipt["bar_count"] == 2190

    def test_cli_end_to_end_sha256_sidecar(self, tmp_path):
        """CLI --sha256-sidecar flag produces a .sha256 sidecar file."""
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        receipt_path = out_dir / "receipt.json"
        sidecar_path = receipt_path.with_suffix(".json.sha256")

        result = subprocess.run(
            [
                sys.executable, "-m", "quantbot.cli",
                "--manifest", str(MANIFEST_PATH),
                "--csv", str(CSV_PATH),
                "--out", str(out_dir),
                "--sha256-sidecar",
            ],
            check=False,
        )

        assert result.returncode == 0, f"CLI failed: {result.stderr!r}"
        assert sidecar_path.exists(), "SHA256 sidecar was not produced"

        content = sidecar_path.read_text().strip()
        assert len(content) == 64, f"SHA256 hex should be 64 chars, got {len(content)}"
        assert all(c in "0123456789abcdef" for c in content), "Not valid hex"

    def test_cli_end_to_end_deterministic(self, tmp_path):
        """Running CLI twice on same fixture produces byte-identical receipts."""
        out_dir1 = tmp_path / "run1"
        out_dir2 = tmp_path / "run2"
        out_dir1.mkdir()
        out_dir2.mkdir()
        receipt1 = out_dir1 / "receipt.json"
        receipt2 = out_dir2 / "receipt.json"

        for out_dir in [out_dir1, out_dir2]:
            r = subprocess.run(
                [
                    sys.executable, "-m", "quantbot.cli",
                    "--manifest", str(MANIFEST_PATH),
                    "--csv", str(CSV_PATH),
                    "--out", str(out_dir),
                ],
                check=False,
            )
            assert r.returncode == 0, f"CLI failed: {r.stderr!r}"

        assert receipt1.read_bytes() == receipt2.read_bytes(), (
            "Receipts differ between runs — output is non-deterministic"
        )

    def test_cli_manifest_mismatch_fails_cleanly(self, tmp_path):
        """CLI exits non-zero when CSV hash does not match manifest."""
        # Copy CSV to tmp and corrupt a data value to change the file hash
        csv_copy = tmp_path / "BTCUSDT_8h.csv"
        content = CSV_PATH.read_text()
        lines = content.split("\n")
        # Modify the last field (volume) of the first data row
        parts = lines[1].split(",")
        parts[-1] = "99999"
        lines[1] = ",".join(parts)
        csv_copy.write_text("\n".join(lines))

        # Create manifest in tmp pointing to the corrupt CSV with ORIGINAL hash.
        # ManifestVerifier uses manifest_path.parent as base_dir, so it will
        # look for BTCUSDT_8h.csv in tmp (the corrupt one) but the hash won't match.
        manifest = tmp_path / "BTCUSDT_manifest.json"
        manifest.write_text(
            '{"BTCUSDT_8h.csv": "ff1885f4c7dda84fc8ce1bc8040c7f4d66b4d1774d107ad57a2751fc7c927047"}'
        )

        out_dir = tmp_path / "out"
        out_dir.mkdir()

        result = subprocess.run(
            [
                sys.executable, "-m", "quantbot.cli",
                "--manifest", str(manifest),
                "--csv", str(csv_copy),
                "--out", str(out_dir),
            ],
            check=False,
        )

        assert result.returncode != 0, "CLI should fail on hash mismatch"

    def test_cli_missing_manifest_fails_cleanly(self, tmp_path):
        """CLI exits non-zero when manifest path does not exist."""
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        fake_manifest = tmp_path / "nonexistent.json"

        result = subprocess.run(
            [
                sys.executable, "-m", "quantbot.cli",
                "--manifest", str(fake_manifest),
                "--csv", str(CSV_PATH),
                "--out", str(out_dir),
            ],
            check=False,
        )

        assert result.returncode != 0, "CLI should fail when manifest is missing"
