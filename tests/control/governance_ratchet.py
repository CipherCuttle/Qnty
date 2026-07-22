"""Governance growth ratchet: measure the governed control-plane surface and
prevent net growth relative to a recorded baseline.

Metric: total bytes per directory (not newline-count lines). Several files
under ``docs/control/`` are canonical JSON written with no trailing newline
(per docs/agent/START_HERE.md's canonical-bytes contract), so a naive
``wc -l``-style line count silently reads as zero for an entire directory of
real content -- a blind spot this ratchet must not have. Byte count is not a
perfect defense against someone minifying code into an unreadable one-liner
to dodge the check either; that residual gap is intentionally left to human
review (see module docstring note in the test file), not mechanical
enforcement, in this first version.
"""

from __future__ import annotations

from pathlib import Path

# Replacement control-plane directories are governed alongside their legacy
# counterparts.  New control work must live in one of these prefixes, rather
# than being hidden beside an older surface under a new basename.
GOVERNED_DIRS = [
    "quantbot/continuity/",
    "quantbot/assurance/",
    "quantbot/control/",
    "tests/continuity/",
    "tests/assurance/",
    "tests/control/",
    "docs/control/",
    "docs/governance/",
]

# These directories contain unrelated repository tooling, so count only the
# QNTY governance namespace within them.  Prefixes intentionally cover future
# QNTY governance files regardless of basename; exact paths preserve the two
# existing entrypoints whose names do not use that namespace convention.
GOVERNED_FILE_PREFIXES = ["scripts/qnty_", ".github/workflows/qnty-"]
GOVERNED_EXACT_FILES = {
    "scripts/qnty_ruleset_snapshot.py",
    ".github/workflows/qnty-full-suite.yml",
}

# Generic/boilerplate basenames that recur across many unrelated packages and
# would swamp the relocation tripwire with false positives (every package has
# an __init__.py). Excluded from the relocation-basename set only; they still
# count fully toward the byte-size ratchet.
_GENERIC_BASENAMES = {"__init__.py", "__main__.py", "conftest.py", "README.md"}


def measure_governed_surface(root: Path) -> dict:
    root = Path(root)
    per_dir_bytes: dict[str, int] = {}
    governed_files: list[str] = []
    for governed_dir in GOVERNED_DIRS:
        base = root / governed_dir
        dir_total = 0
        if not base.exists():
            per_dir_bytes[governed_dir] = 0
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            dir_total += path.stat().st_size
            governed_files.append(str(path.relative_to(root)))
        per_dir_bytes[governed_dir] = dir_total
    mixed_files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or ".git" in path.parts or ".venv" in path.parts or "__pycache__" in path.parts:
            continue
        rel = str(path.relative_to(root))
        if rel in GOVERNED_EXACT_FILES or any(rel.startswith(prefix) for prefix in GOVERNED_FILE_PREFIXES):
            mixed_files.append((rel, path.stat().st_size))

    per_dir_bytes["mixed_governance_files"] = sum(size for _, size in mixed_files)
    governed_files.extend(rel for rel, _ in mixed_files)
    return {
        "per_dir_bytes": per_dir_bytes,
        "total_bytes": sum(per_dir_bytes.values()),
        "governed_basenames": sorted({Path(f).name for f in governed_files}),
    }


def find_relocated_governance_basenames(root: Path, governed_basenames: list[str]) -> list[str]:
    """Anti-evasion tripwire: reject a file elsewhere in the repo sharing a
    basename with a file that exists in one of the governed directories at
    baseline time. Catches the common evasion of moving/renaming a governed
    module out of the counted directories to make the ratchet look like it
    shrank. This is a heuristic, not a proof: a determined rewrite-and-rename
    (different basename, same logic) would not be caught by this check alone;
    it relies on the AST hygiene checks and human review for that case.
    """
    root = Path(root)
    basenames = set(governed_basenames) - _GENERIC_BASENAMES
    hits = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name not in basenames:
            continue
        rel = path.relative_to(root)
        rel_text = str(rel)
        if any(rel_text.startswith(d) for d in GOVERNED_DIRS):
            continue
        if rel_text in GOVERNED_EXACT_FILES or any(rel_text.startswith(prefix) for prefix in GOVERNED_FILE_PREFIXES):
            continue
        if ".git" in rel.parts or ".venv" in rel.parts or "__pycache__" in rel.parts:
            continue
        hits.append(str(rel))
    return hits
