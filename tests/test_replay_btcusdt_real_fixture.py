"""Deterministic test for replay on real BTCUSDT 8h data.

Requires PYTHONHASHSEED=0 for deterministic dict ordering.
"""

import json
import tempfile
from pathlib import Path

from quantbot.app.run_replay import run_replay


FIXTURE_DIR = Path(__file__).parent / "fixtures"
MANIFEST_PATH = FIXTURE_DIR / "BTCUSDT_manifest.json"
CSV_PATH = FIXTURE_DIR / "BTCUSDT_8h.csv"


def test_replay_btcusdt_receipt_produced() -> None:
    """Replay on BTCUSDT data produces a valid receipt."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "run"
        receipt_path = run_replay(MANIFEST_PATH, CSV_PATH, out)

        assert receipt_path.exists()
        data = json.loads(receipt_path.read_text())
        assert data["bar_count"] == 2190
        assert data["bar_hash"]
        assert data["output_digest"]
        assert data["first_timestamp"] == "2023-01-01 00:00:00+00:00"
        assert data["last_timestamp"] == "2024-12-30 16:00:00+00:00"


def test_replay_btcusdt_deterministic() -> None:
    """Two identical runs on BTCUSDT data produce byte-identical receipts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out1 = Path(tmpdir) / "run1"
        out2 = Path(tmpdir) / "run2"

        path1 = run_replay(MANIFEST_PATH, CSV_PATH, out1)
        path2 = run_replay(MANIFEST_PATH, CSV_PATH, out2)

        assert path1.read_bytes() == path2.read_bytes()
