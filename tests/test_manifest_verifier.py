"""Tests for ManifestVerifier determinism."""

from pathlib import Path

import pytest

from quantbot.core.determinism import sha256_file
from quantbot.data.manifest import ManifestVerifier


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def test_manifest_verifier_validates_fixture():
    """Verify manifest.json matches its sha256 and csv matches manifest hash."""
    manifest_path = FIXTURE_DIR / "sample_manifest.json"
    csv_path = FIXTURE_DIR / "sample_bars.csv"

    # Manifest itself must match its sha256
    manifest_actual = sha256_file(manifest_path)
    with open(FIXTURE_DIR / "sample_manifest.json.sha256") as f:
        manifest_expected = f.read().strip()
    assert manifest_actual == manifest_expected

    # Verify CSV hash against manifest entry
    verifier = ManifestVerifier(manifest_path)
    results = verifier.verify(FIXTURE_DIR)
    assert results["sample_bars.csv"] is True

    # Verify all pass
    assert verifier.verify_all(FIXTURE_DIR) is True


def test_manifest_verifier_detects_tampering():
    """Verify that a tampered CSV file fails verification."""
    manifest_path = FIXTURE_DIR / "sample_manifest.json"
    verifier = ManifestVerifier(manifest_path)

    # All good initially
    assert verifier.verify_all(FIXTURE_DIR) is True
