"""Constraints loading stub for QuantBot.

Paper mode only - no real trading.
"""

import json
from pathlib import Path


def load_constraints(config_path: Path) -> dict:
    """Load symbol constraints from JSON config.

    Args:
        config_path: Path to constraints JSON file.

    Returns:
        Constraints dict.
    """
    if not config_path.exists():
        return {}
    with open(config_path) as fh:
        return json.load(fh)
