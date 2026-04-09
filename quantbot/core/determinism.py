"""Determinism helpers for QuantBot.

Pure functions for canonical serialization and file hashing.
"""

import hashlib
import json
from pathlib import Path


def canonical_json_dumps(obj: object) -> str:
    """Serialize object to canonical JSON string.

    Args:
        obj: Any JSON-serializable Python object.

    Returns:
        Canonical JSON string with sorted keys and no extra whitespace.
    """
    return json.dumps(obj, separators=(",", ":"), sort_keys=True, ensure_ascii=True)


def sha256_file(path: Path) -> str:
    """Compute SHA-256 hex digest of a file.

    Args:
        path: Path to the file.

    Returns:
        Hex digest string (64 characters).
    """
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()
