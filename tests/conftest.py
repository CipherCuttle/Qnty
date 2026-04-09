"""Test configuration for QuantBot.

Note: PYTHONHASHSEED must be set externally for deterministic tests.
This conftest may CHECK the environment variable but does NOT set it.
"""

import os

import pytest


def pytest_configure(config):
    """Check for deterministic hash seed if configured."""
    hashseed = os.environ.get("PYTHONHASHSEED")
    if hashseed is not None:
        config.option.verbose and print(f"PYTHONHASHSEED={hashseed}")


@pytest.fixture
def sample_signal():
    """Provide a sample signal dict for testing."""
    return {
        "symbol": "BTCUSDT",
        "direction": "long",
        "confidence": 0.75,
    }
