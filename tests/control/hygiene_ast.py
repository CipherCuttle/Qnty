"""Structural (AST-shape) detectors for governance anti-patterns.

Each ``find_*`` function detects a *behavior shape*, not a hardcoded historical
symbol name, so a renamed or newly-introduced instance of the same pattern is
still caught. Callers narrow results with an exact, path-scoped debt allowlist
(see ``debt_allowlist.json``) rather than the detectors themselves knowing
about any historical exception.

Known blind spots (documented, not solved, in this first version):
- Detection is per-function/per-dict-literal within a single file; a pattern
  spread across multiple helper functions/modules working together will not
  be found.
- ``find_fake_pass_wrappers`` requires the closure shape used by the current
  generations of continuity guards (outer function taking an ``original``-like
  first parameter, wrapping a nested function). A guard written as a decorator
  applied with ``@`` syntax rather than manual reassignment is not covered by
  ``find_globals_rebindings`` (which only looks for ``globals()[...] = ...``
  assignment), though it would still be caught by
  ``find_fake_pass_wrappers`` if the closure shape matches.
- ``find_self_hash_source_bindings`` only looks at dict literals; a hash bound
  via two separate statements (assign key, assign value elsewhere) is missed.
"""

from __future__ import annotations

import ast
import json
import re
from collections import Counter
from pathlib import Path

SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")
TEST_OR_VALIDATOR_PATH_RE = re.compile(
    r"^tests/.*\.py$|^quantbot/continuity/.*\.py$|^quantbot/control/.*\.py$"
)
PER_PHASE_VALIDATOR_MODULE_RE = re.compile(
    r"^_?v\d{3}_.*validator.*\.py$|.*validator.*_v\d{3}\.py$|^_?phase_v\d+.*\.py$",
    re.IGNORECASE,
)

_EXCLUDED_DIR_PARTS = {".git", ".venv", "__pycache__", "node_modules"}


def iter_python_files(root: Path, include_dirs: list[str] | None = None):
    root = Path(root)
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root)
        if _EXCLUDED_DIR_PARTS & set(rel.parts):
            continue
        if include_dirs is not None:
            rel_str = str(rel)
            if not any(rel_str == d or rel_str.startswith(d.rstrip("/") + "/") for d in include_dirs):
                continue
        yield rel, path


def _parse(path: Path):
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return None


def _call_signature(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def find_globals_rebindings(root: Path, include_dirs: list[str] | None = None) -> list[dict]:
    """Detect ``globals()[<key>] = <call>`` style dynamic test rebinding."""
    violations = []
    for rel, path in iter_python_files(root, include_dirs):
        tree = _parse(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if not (
                    isinstance(target, ast.Subscript)
                    and isinstance(target.value, ast.Call)
                    and isinstance(target.value.func, ast.Name)
                    and target.value.func.id == "globals"
                    and not target.value.args
                ):
                    continue
                wrapper = None
                if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
                    wrapper = node.value.func.id
                violations.append({"file": str(rel), "line": node.lineno, "wrapper": wrapper})
    return violations


def find_fake_pass_wrappers(root: Path, include_dirs: list[str] | None = None) -> list[dict]:
    """Detect phase-guard closures that return early (skip ``original``) for the
    current phase instead of executing the wrapped historical test body.

    Shape: ``def outer(original): def inner(*a, **kw): if <cond>: ...; return
    (bare); return original(*a, **kw); return inner``.
    """
    violations = []
    for rel, path in iter_python_files(root, include_dirs):
        tree = _parse(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef) or not node.args.args:
                continue
            outer_param = node.args.args[0].arg
            for inner in node.body:
                if not isinstance(inner, ast.FunctionDef):
                    continue
                has_bare_return_in_if = False
                has_trailing_call_to_param = False
                for stmt in inner.body:
                    if isinstance(stmt, ast.If):
                        last = stmt.body[-1] if stmt.body else None
                        if isinstance(last, ast.Return) and last.value is None:
                            has_bare_return_in_if = True
                    if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Call):
                        func = stmt.value.func
                        if isinstance(func, ast.Name) and func.id == outer_param:
                            has_trailing_call_to_param = True
                if has_bare_return_in_if and has_trailing_call_to_param:
                    violations.append({"file": str(rel), "line": node.lineno, "function": node.name})
    return violations


_PY_SOURCE_PATH_RE = re.compile(r"^[\w./-]+\.py$")


def find_source_reconstruction_functions(root: Path, include_dirs: list[str] | None = None) -> list[dict]:
    """Detect helper functions that reconstruct historical *source* (.py) bytes
    and verify them by hash before writing -- covers both known shapes
    (truncating current bytes back to a marker boundary, and decoding an
    embedded base64 historical blob), by behavior rather than by name.

    Shape required, all within one function: reads existing bytes, computes or
    checks a sha256 digest, writes bytes back, and references at least one
    ``*.py`` relative-path string literal (the reconstruction target/key) --
    this last requirement is what distinguishes a source-restoration helper
    from the many legitimate JSON-evidence-mutation test fixtures in this
    codebase that also happen to read/hash/write bytes. Test functions
    (``test_*``) are excluded: an inline hash-mismatch assertion inside a test
    body is not a reusable restoration helper.
    """
    violations = []
    for rel, path in iter_python_files(root, include_dirs):
        tree = _parse(path)
        if tree is None:
            continue

        # Module-level dict literals assigned to a plain name, e.g.
        # ``_V026_PINNED_SOURCES = {"quantbot/.../x.py": "...", ...}``. A
        # restoration helper commonly iterates such a dict (``for path, marker
        # in _V027_APPEND_MARKERS.items()``) without the ".py" literal
        # appearing directly in the helper's own body.
        module_dict_py_names: set[str] = set()
        for stmt in tree.body:
            if not (isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Dict)):
                continue
            keys = [k.value for k in stmt.value.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)]
            if any(_PY_SOURCE_PATH_RE.match(k) for k in keys):
                for target in stmt.targets:
                    if isinstance(target, ast.Name):
                        module_dict_py_names.add(target.id)

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name.startswith("test_"):
                continue
            calls = {_call_signature(c) for c in ast.walk(node) if isinstance(c, ast.Call)}
            if not {"read_bytes", "write_bytes", "sha256"} <= calls:
                continue
            has_py_source_literal = any(
                isinstance(n, ast.Constant) and isinstance(n.value, str) and _PY_SOURCE_PATH_RE.match(n.value)
                for n in ast.walk(node)
            )
            referenced_names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
            references_py_dict = bool(referenced_names & module_dict_py_names)
            if not (has_py_source_literal or references_py_dict):
                continue
            # Byte-manipulation signal: distinguishes an actual reconstruction
            # (decodes/truncates/rewrites bytes that differ from the file's own
            # real current content) from a fixture builder that copies real
            # current files verbatim and only rehashes unrelated JSON evidence.
            has_byte_manipulation = (
                "b64decode" in calls
                or "replace" in calls
                or (
                    ("index" in calls or "count" in calls)
                    and any(isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Slice) for n in ast.walk(node))
                )
            )
            if has_byte_manipulation:
                violations.append({"file": str(rel), "line": node.lineno, "function": node.name})
    return violations


def _is_sha256_hexdigest_call(node: ast.AST) -> bool:
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "hexdigest"):
        return False
    return any(isinstance(n, ast.Call) and _call_signature(n) == "sha256" for n in ast.walk(node))


def find_self_hash_source_bindings(root: Path, include_dirs: list[str]) -> list[dict]:
    """Detect dict literals binding a test/validator source path to a hash
    (either a hardcoded 64-hex pinned digest, or a computed ``sha256(...).hexdigest()``).
    """
    violations = []
    for rel, path in iter_python_files(root, include_dirs):
        tree = _parse(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            for key, value in zip(node.keys, node.values):
                if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
                    continue
                if not TEST_OR_VALIDATOR_PATH_RE.match(key.value):
                    continue
                kind = None
                if isinstance(value, ast.Constant) and isinstance(value.value, str) and SHA256_HEX_RE.match(value.value):
                    kind = "pinned_hash"
                elif _is_sha256_hexdigest_call(value):
                    kind = "dynamic_hash"
                if kind:
                    violations.append({"file": str(rel), "line": node.lineno, "key": key.value, "kind": kind})
    return violations


def find_per_phase_validator_modules(root: Path, scan_dirs: list[str]) -> list[dict]:
    """Forward-looking tripwire for the replacement control architecture: reject
    a per-phase validator module naming shape (e.g. ``phase_v027_validator.py``)
    anywhere under the given directories. No such directory/module exists yet
    on origin/main; this exists so PR-2 cannot introduce one silently.
    """
    violations = []
    root = Path(root)
    for scan_dir in scan_dirs:
        base = root / scan_dir
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.py")):
            rel = path.relative_to(root)
            if PER_PHASE_VALIDATOR_MODULE_RE.match(path.name):
                violations.append({"file": str(rel)})
    return violations


def load_debt_allowlist() -> dict:
    allowlist_path = Path(__file__).parent / "debt_allowlist.json"
    return json.loads(allowlist_path.read_text(encoding="utf-8"))


def check_against_allowlist(violations: list[dict], allowlist_entries: list[dict], key_fields: tuple[str, ...]) -> list[str]:
    """Compare detected violations against an exact debt allowlist.

    Each allowlist entry names the ``key_fields`` values it permits plus a
    ``max_count`` bound. Returns a list of human-readable problem descriptions:
    empty means every detected violation is covered by the allowlist within
    its bound, and nothing exceeds it. A violation tuple absent from the
    allowlist, or present but over its ``max_count``, is reported. Allowlist
    entries are exact (file [+ function/wrapper/key/kind]) -- there is no
    wildcard that matches a whole directory or file.
    """
    actual_counts: Counter = Counter()
    for v in violations:
        actual_counts[tuple(v.get(f) for f in key_fields)] += 1

    allowed_max: dict[tuple, int] = {}
    for entry in allowlist_entries:
        key = tuple(entry.get(f) for f in key_fields)
        allowed_max[key] = entry.get("max_count", 0)

    problems = []
    for key, count in actual_counts.items():
        max_count = allowed_max.get(key)
        if max_count is None:
            problems.append(
                f"NEW instance not in debt allowlist: {dict(zip(key_fields, key))} (count={count})"
            )
        elif count > max_count:
            problems.append(
                f"instance exceeds allowlisted max_count: {dict(zip(key_fields, key))} "
                f"(found={count}, allowed={max_count})"
            )
    return problems
