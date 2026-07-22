"""Exact-surface governance growth ratchet helpers.

The ratchet measures legacy and replacement governance directories plus the
QNTY namespace in mixed-purpose tooling directories.  Exceptions are exact
repository-relative file paths, never a fungible per-directory byte budget.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

GOVERNED_DIRS = [
    "quantbot/continuity/", "quantbot/assurance/", "quantbot/control/",
    "tests/continuity/", "tests/assurance/", "tests/control/",
    "docs/control/", "docs/governance/",
]
MIXED_SURFACE = "mixed_governance_files"
_GENERIC_BASENAMES = {"__init__.py", "__main__.py", "conftest.py", "README.md"}
_EXCLUDED_DIR_PARTS = {".git", ".venv", "__pycache__"}
_GLOB_CHARS = set("*?[]{}")


def classify_governance_path(relative_path: str | Path) -> str | None:
    """Return the one measured surface that owns a repository-relative path."""
    rel = str(relative_path).replace("\\", "/")
    for surface in GOVERNED_DIRS:
        if rel.startswith(surface):
            return surface
    pure = PurePosixPath(rel)
    if pure.parent == PurePosixPath("scripts") and pure.name.startswith("qnty_"):
        return MIXED_SURFACE
    if pure.parent == PurePosixPath(".github/workflows") and pure.name.startswith("qnty-"):
        return MIXED_SURFACE
    return None


def _is_scannable(path: Path, root: Path) -> bool:
    if not path.is_file():
        return False
    rel = path.relative_to(root)
    return not (_EXCLUDED_DIR_PARTS & set(rel.parts))


def measure_governed_surface(root: Path) -> dict:
    root = Path(root)
    per_surface = {surface: 0 for surface in [*GOVERNED_DIRS, MIXED_SURFACE]}
    per_file_bytes: dict[str, int] = {}
    for path in sorted(root.rglob("*")):
        if not _is_scannable(path, root):
            continue
        rel = str(path.relative_to(root))
        surface = classify_governance_path(rel)
        if surface is None:
            continue
        size = path.stat().st_size
        per_surface[surface] += size
        per_file_bytes[rel] = size
    return {
        "per_dir_bytes": per_surface,
        "per_file_bytes": per_file_bytes,
        "total_bytes": sum(per_surface.values()),
        "governed_basenames": sorted({Path(path).name for path in per_file_bytes}),
    }


def validate_exceptions(baseline: dict) -> list[str]:
    """Validate exact, surface-owned exception records without reading disk."""
    problems = []
    seen_paths = set()
    surfaces = set(baseline["per_dir_bytes"])
    for exception in baseline.get("exceptions", []):
        surface = exception.get("surface")
        path = exception.get("path")
        if surface not in surfaces:
            problems.append(f"unknown exception surface: {surface!r}")
        if not isinstance(path, str) or not path or path.endswith("/"):
            problems.append(f"exception path must be an exact file path: {path!r}")
            continue
        pure = PurePosixPath(path)
        if pure.is_absolute() or ".." in pure.parts or any(char in path for char in _GLOB_CHARS):
            problems.append(f"exception path is not a safe exact relative path: {path!r}")
            continue
        classified = classify_governance_path(path)
        if classified is None:
            problems.append(f"exception path is outside governed surfaces: {path!r}")
        elif classified != surface:
            problems.append(f"exception surface/path mismatch: {surface!r} != {classified!r} for {path!r}")
        if path in seen_paths:
            problems.append(f"duplicate exception path: {path!r}")
        seen_paths.add(path)
        amount = exception.get("max_additional_bytes")
        if not isinstance(amount, int) or isinstance(amount, bool) or amount < 1:
            problems.append(f"exception max_additional_bytes must be a positive integer: {path!r}")
        for key in ("reason", "expires_in_pr"):
            if not isinstance(exception.get(key), str) or not exception[key]:
                problems.append(f"exception {key} must be non-empty: {path!r}")
    return problems


def ratchet_problems(current: dict, baseline: dict) -> list[str]:
    """Return growth violations under exact-path exception semantics."""
    problems = validate_exceptions(baseline)
    if problems:
        return problems
    exceptions = {item["path"]: item for item in baseline.get("exceptions", [])}
    baseline_files = baseline.get("per_file_bytes", {})
    permitted_by_surface = {surface: 0 for surface in baseline["per_dir_bytes"]}
    for path, exception in exceptions.items():
        delta = max(0, current["per_file_bytes"].get(path, 0) - baseline_files.get(path, 0))
        if delta > exception["max_additional_bytes"]:
            problems.append(f"{path}: positive delta {delta} exceeds exception cap {exception['max_additional_bytes']}")
        permitted_by_surface[exception["surface"]] += min(delta, exception["max_additional_bytes"])
    for surface, baseline_bytes in baseline["per_dir_bytes"].items():
        delta = current["per_dir_bytes"].get(surface, 0) - baseline_bytes
        if delta > permitted_by_surface[surface]:
            problems.append(f"{surface}: net growth {delta} exceeds exact-path exception delta budget {permitted_by_surface[surface]}")
    total_delta = current["total_bytes"] - baseline["total_bytes"]
    total_permitted = sum(permitted_by_surface.values())
    if total_delta > total_permitted:
        problems.append(f"total: net growth {total_delta} exceeds exact-path exception delta budget {total_permitted}")
    return problems


def find_relocated_governance_basenames(root: Path, governed_basenames: list[str]) -> list[str]:
    """Defense-in-depth tripwire for known governed basenames outside a surface."""
    root = Path(root)
    basenames = set(governed_basenames) - _GENERIC_BASENAMES
    hits = []
    for path in sorted(root.rglob("*")):
        if not _is_scannable(path, root) or path.name not in basenames:
            continue
        rel = str(path.relative_to(root))
        if classify_governance_path(rel) is None:
            hits.append(rel)
    return hits
