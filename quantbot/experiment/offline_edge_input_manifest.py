"""Fixture-only input manifest/hash inventory for offline edge validation.

Stdlib-only. No DB, engine, exchange, or file-write dependencies.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

PROD_BASE = Path("/srv/qnty")


def _refuse_prod_path(path: Path) -> None:
    """Raise ValueError if path resolves under /srv/qnty."""
    resolved = path.resolve()
    try:
        common = Path(*resolved.parts[: len(PROD_BASE.resolve().parts)])
    except ValueError:
        return
    if common == PROD_BASE.resolve():
        raise ValueError(
            f"Path resolves under prod path {PROD_BASE}: {path}"
        )


def sha256_file(path: Path) -> str:
    """Compute SHA256 hex digest of a single file. Stdlib only."""
    _refuse_prod_path(path)
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def discover_input_files(paths: list[Path]) -> list[Path]:
    """Scan input paths, return deterministic sorted list of regular files.

    - Directories are scanned recursively for regular files.
    - Non-directory paths that are regular files are included directly.
    - Symlinks and special files are skipped.
    - Results are sorted deterministically.
    - Fails with FileNotFoundError if a provided path does not exist.
    - Fails with ValueError if a provided path resolves under /srv/qnty.
    """
    results: list[Path] = []
    for p in paths:
        _refuse_prod_path(p)
        if not p.exists():
            raise FileNotFoundError(f"Input path does not exist: {p}")
        if p.is_dir():
            for child in sorted(p.rglob("*")):
                if child.is_file():
                    results.append(child.resolve())
        elif p.is_file():
            results.append(p.resolve())
    # Deduplicate while preserving order
    seen = set()
    unique: list[Path] = []
    for r in results:
        if r not in seen:
            seen.add(r)
            unique.append(r)
    return sorted(unique)


def compute_input_manifest_fingerprint(paths: list[Path]) -> str:
    """Compute deterministic SHA256 fingerprint from sorted file contents.

    For each file: mix in the resolved path, then the file's SHA256 hex digest.
    This prevents hash-equiv attacks and ensures deterministic ordering.
    """
    h = hashlib.sha256()
    for p in sorted(paths):
        h.update(str(p).encode("utf-8"))
        h.update(b"\x00")
        file_hash = sha256_file(p)
        h.update(file_hash.encode("ascii"))
        h.update(b"\x00")
    return h.hexdigest()


def build_input_manifest_summary(paths: list[Path]) -> dict:
    """Build a summary dict of the input manifest for inclusion in receipts.

    Returns dict with:
    - file_count: int
    - files: list of {path, size_bytes, sha256}
    - fingerprint: str (deterministic SHA256)
    """
    file_entries = []
    for p in sorted(paths):
        file_entries.append(
            {
                "path": str(p),
                "size_bytes": p.stat().st_size,
                "sha256": sha256_file(p),
            }
        )
    return {
        "file_count": len(file_entries),
        "files": file_entries,
        "fingerprint": compute_input_manifest_fingerprint(paths),
    }