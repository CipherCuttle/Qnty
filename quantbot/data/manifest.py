"""Manifest verification using deterministic hashing."""

import json
from dataclasses import dataclass
from pathlib import Path

from quantbot.core.determinism import sha256_file


@dataclass
class ManifestEntry:
    """Single entry in a manifest file."""

    path: str
    expected_hash: str


class ManifestVerifier:
    """Verify file integrity against a manifest using sha256_file.

    The manifest is a JSON file mapping relative paths to SHA-256 hashes.
    """

    def __init__(self, manifest_path: Path):
        """Initialize verifier with path to manifest file.

        Args:
            manifest_path: Path to the manifest JSON file.
        """
        self.manifest_path = manifest_path
        self._entries: list[ManifestEntry] = []
        self._load()

    def _load(self) -> None:
        """Load manifest entries from JSON file."""
        with open(self.manifest_path) as fh:
            data = json.load(fh)
        for path_str, hash_str in data.items():
            self._entries.append(ManifestEntry(path=path_str, expected_hash=hash_str))

    def verify(self, base_dir: Path) -> dict[str, bool]:
        """Verify all files in the manifest against their expected hashes.

        Args:
            base_dir: Base directory for resolving relative paths.

        Returns:
            Dictionary mapping file paths to verification status (True=valid).
        """
        results = {}
        for entry in self._entries:
            file_path = base_dir / entry.path
            actual_hash = sha256_file(file_path)
            results[entry.path] = actual_hash == entry.expected_hash
        return results

    def verify_all(self, base_dir: Path) -> bool:
        """Verify all files; return True only if all pass.

        Args:
            base_dir: Base directory for resolving relative paths.

        Returns:
            True if all files verify correctly, False otherwise.
        """
        results = self.verify(base_dir)
        return all(results.values())
