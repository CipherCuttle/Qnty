"""Minimal end-to-end replay runner for Gate45.

Orchestrates: manifest verification -> CSV bar loading -> replay -> receipt emission.
No live trading.
"""

from pathlib import Path
from typing import Protocol, runtime_checkable

from quantbot.core.determinism import canonical_json_dumps, sha256_file
from quantbot.data.loaders import load_bars_from_csv
from quantbot.data.manifest import ManifestVerifier
from quantbot.replay.runner import ReplayRunner


@runtime_checkable
class Strategy(Protocol):
    """Protocol for strategies used in replay runs."""

    def on_bar(self, bar) -> "Signal | None":
        ...


def run_replay(
    manifest_path: Path,
    csv_path: Path,
    output_dir: Path,
    strategy: Strategy | None = None,
    emit_sha256: bool = False,
) -> Path:
    """Run deterministic replay from manifest-verified CSV.

    Steps:
        1. Verify all files in manifest.
        2. Load bars from CSV.
        3. Run replay with optional strategy.
        4. Emit receipt JSON.
        5. Optionally emit SHA256 sidecar.

    Args:
        manifest_path: Path to manifest JSON file.
        csv_path: Path to bars CSV file.
        output_dir: Directory for output files.
        strategy: Optional strategy implementing on_bar(bar) -> Signal|None.
        emit_sha256: If True, write .sha256 sidecar alongside receipt.

    Returns:
        Path to the emitted receipt JSON file.

    Raises:
        AssertionError: If manifest verification fails.
    """
    # Step 1: verify manifest
    verifier = ManifestVerifier(manifest_path)
    base_dir = manifest_path.parent
    assert verifier.verify_all(base_dir), (
        f"Manifest verification failed for {manifest_path}"
    )

    # Step 2: load bars
    bars = load_bars_from_csv(csv_path)

    # Step 3: run replay with optional strategy
    runner = ReplayRunner(bars, strategy=strategy)
    receipt = runner.run()

    # Step 4: emit receipt JSON
    output_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = output_dir / "receipt.json"
    receipt_json = canonical_json_dumps(receipt.to_dict())
    receipt_path.write_text(receipt_json, encoding="utf-8")

    # Step 5: optionally emit SHA256 sidecar
    if emit_sha256:
        sidecar_path = output_dir / "receipt.json.sha256"
        sidecar_path.write_text(sha256_file(receipt_path), encoding="utf-8")

    return receipt_path
