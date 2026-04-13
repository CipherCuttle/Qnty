"""Minimal experiment index for reading and comparing existing artifacts.

Paper mode only - no live trading, no profitability claims.
Reads existing experiment_result.json or walkforward_result.json files
and produces a stable normalized summary suitable for sorting/comparison.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional


@dataclass
class IndexedExperiment:
    """Normalized summary of an experiment artifact.

    Provides a stable shape for sorting and comparing experiment runs
    regardless of whether the source is a single experiment or walk-forward.

    Attributes:
        experiment_name: Name of the experiment.
        strategy_name: Name of the strategy used.
        fixture_name: Name of the data fixture used.
        gate_status: Gate verdict status ("PASS", "FAIL") or None if no gate run.
        split_count: Number of splits (0 for single experiment, >0 for walk-forward).
        signal_count: Total signals (aggregate for walk-forward).
        receipt_digest: SHA256 digest of the receipt, or None if not present.
        artifact_path: Path to the source artifact file.
        result_type: "single" for experiment_result.json, "walkforward" for walkforward_result.json.
        family_id: Trial family identifier, or None if not present in artifact.
        variant_id: Variant identifier, or None if not present in artifact.
        trial_count: Cumulative trial count, or None if not present in artifact.
    """

    experiment_name: str
    strategy_name: str
    fixture_name: str
    gate_status: Optional[str]
    split_count: int
    signal_count: int
    receipt_digest: Optional[str]
    artifact_path: Path
    result_type: Literal["single", "walkforward"]
    family_id: Optional[str] = None
    variant_id: Optional[str] = None
    trial_count: Optional[int] = None

    def gate_passed(self) -> bool:
        """Return True if gate status is PASS."""
        return self.gate_status == "PASS"

    def gate_failed(self) -> bool:
        """Return True if gate status is FAIL."""
        return self.gate_status == "FAIL"


def _load_experiment_result(path: Path) -> dict:
    """Load and parse an experiment_result.json file."""
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _load_walkforward_result(path: Path) -> dict:
    """Load and parse a walkforward_result.json file."""
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _extract_gate_status(data: dict) -> Optional[str]:
    """Extract gate status from artifact data dict."""
    gate = data.get("gate_verdict")
    if gate is None:
        return None
    return gate.get("status")


def index_experiment_artifacts(paths: list[Path]) -> list[IndexedExperiment]:
    """Read experiment artifact files and produce normalized summaries.

    Accepts paths to either experiment_result.json or walkforward_result.json
    files (or directories containing them). Produces a stable normalized summary
    for each artifact that can be sorted and compared.

    Args:
        paths: List of paths to artifact JSON files or directories.
               If a directory is given, looks for experiment_result.json
               or walkforward_result.json inside it.

    Returns:
        List of IndexedExperiment summaries, one per valid artifact found.

    Raises:
        FileNotFoundError: If a specified path does not exist.
        ValueError: If a file is not a recognized experiment artifact.
    """
    results: list[IndexedExperiment] = []

    for path in paths:
        if not path.exists():
            raise FileNotFoundError(f"Path does not exist: {path}")

        # If directory, look for artifact files inside
        if path.is_dir():
            if (path / "experiment_result.json").exists():
                artifact_path = path / "experiment_result.json"
            elif (path / "walkforward_result.json").exists():
                artifact_path = path / "walkforward_result.json"
            else:
                continue  # Skip directories without artifacts
        else:
            artifact_path = path

        filename = artifact_path.name

        if filename == "experiment_result.json":
            data = _load_experiment_result(artifact_path)
            indexed = IndexedExperiment(
                experiment_name=data.get("experiment_name", ""),
                strategy_name=data.get("strategy_name", ""),
                fixture_name=data.get("fixture_name", ""),
                gate_status=_extract_gate_status(data),
                split_count=0,
                signal_count=data.get("signal_count", 0),
                receipt_digest=data.get("receipt_digest"),
                artifact_path=artifact_path,
                result_type="single",
                family_id=data.get("family_id"),
                variant_id=data.get("variant_id"),
                trial_count=data.get("trial_count"),
            )
            results.append(indexed)

        elif filename == "walkforward_result.json":
            data = _load_walkforward_result(artifact_path)
            indexed = IndexedExperiment(
                experiment_name=data.get("experiment_name", ""),
                strategy_name=data.get("strategy_name", ""),
                fixture_name=data.get("fixture_name", ""),
                gate_status=_extract_gate_status(data),
                split_count=data.get("split_count", 0),
                signal_count=data.get("aggregate_signal_count", 0),
                receipt_digest=None,  # Walk-forward results don't expose a single receipt digest
                artifact_path=artifact_path,
                result_type="walkforward",
                family_id=data.get("family_id"),
                variant_id=data.get("variant_id"),
                trial_count=data.get("trial_count"),
            )
            results.append(indexed)

        else:
            raise ValueError(
                f"Unrecognized experiment artifact: {artifact_path}. "
                "Expected experiment_result.json or walkforward_result.json."
            )

    return results
