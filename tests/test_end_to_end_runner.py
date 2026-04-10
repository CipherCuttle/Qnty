"""End-to-end tests for quantbot.app.run_replay.

Requires PYTHONHASHSEED=0 for deterministic dict ordering.
"""

import json
import tempfile
from pathlib import Path

import pytest

from quantbot.app.run_replay import run_replay
from quantbot.core.determinism import sha256_file


FIXTURE_DIR = Path(__file__).parent / "fixtures"
MANIFEST_PATH = FIXTURE_DIR / "sample_manifest.json"
CSV_PATH = FIXTURE_DIR / "sample_bars.csv"


def test_replay_determinism() -> None:
    """Two identical runs produce byte-identical receipt JSON."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out1 = Path(tmpdir) / "run1"
        out2 = Path(tmpdir) / "run2"

        # Run twice
        path1 = run_replay(MANIFEST_PATH, CSV_PATH, out1)
        path2 = run_replay(MANIFEST_PATH, CSV_PATH, out2)

        # Receipts must be byte-identical
        assert path1.read_bytes() == path2.read_bytes()

        # Parse and validate structure
        data = json.loads(path1.read_text())
        assert data["bar_count"] == 8
        assert data["bar_hash"]  # non-empty
        assert data["output_digest"]  # non-empty
        assert data["first_timestamp"] == "2024-01-02T09:00:00"
        assert data["last_timestamp"] == "2024-01-02T16:00:00"


def test_replay_with_sha256_sidecar() -> None:
    """With emit_sha256=True, a .sha256 sidecar is written."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "run"
        receipt_path = run_replay(MANIFEST_PATH, CSV_PATH, out, emit_sha256=True)

        assert receipt_path.exists()
        sidecar_path = receipt_path.with_suffix(".json.sha256")
        assert sidecar_path.exists()
        # sidecar must be 64-char hex digest
        assert len(sidecar_path.read_text().strip()) == 64


def test_manifest_mismatch_raises() -> None:
    """If CSV is modified after manifest creation, verification fails."""
    import hashlib

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a copy of the CSV
        test_csv = Path(tmpdir) / "sample_bars.csv"
        test_csv.write_bytes(CSV_PATH.read_bytes())

        # Create manifest for the original CSV
        original_hash = sha256_file(test_csv)
        manifest = Path(tmpdir) / "manifest.json"
        manifest.write_text(
            json.dumps({"sample_bars.csv": original_hash}), encoding="utf-8"
        )

        # Now corrupt the CSV (modify data after manifest was created)
        # Change volume in second row: 1200.0 -> 9999.9
        content = test_csv.read_bytes()
        corrupted = content.replace(b"1200.0", b"9999.9")
        test_csv.write_bytes(corrupted)

        out = Path(tmpdir) / "out"
        # Verification must fail because CSV no longer matches manifest hash
        with pytest.raises(AssertionError, match="Manifest verification failed"):
            run_replay(manifest, test_csv, out)
