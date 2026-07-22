"""Tests for the all-surface, exact-path governance growth ratchet."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from governance_ratchet import (
    MIXED_SURFACE, classify_governance_path, find_relocated_governance_basenames,
    measure_governed_surface, ratchet_problems, validate_exceptions,
)

ROOT = Path(__file__).parents[2]
BASELINE_PATH = Path(__file__).parent / "governance_baseline.json"


def _baseline(root: Path, exceptions=()):
    measured = measure_governed_surface(root)
    return {**measured, "exceptions": list(exceptions)}


def _exception(surface, path, cap=10):
    return {"surface": surface, "path": path, "max_additional_bytes": cap,
            "reason": "temporary exact-path governance work", "expires_in_pr": "fix/continuity-entropy-brake-v032"}


def _write(root: Path, path: str, content: bytes):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)


def _load_baseline():
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def test_governed_surface_has_not_grown_beyond_exact_path_exception_deltas():
    assert not ratchet_problems(measure_governed_surface(ROOT), _load_baseline())


def test_no_governance_code_relocated_outside_counted_directories():
    assert not find_relocated_governance_basenames(ROOT, _load_baseline()["governed_basenames"])


def test_classifier_owns_every_governance_surface():
    assert classify_governance_path("quantbot/control/guard.py") == "quantbot/control/"
    assert classify_governance_path("scripts/qnty_runtime_guard_audit.py") == MIXED_SURFACE
    assert classify_governance_path(".github/workflows/qnty-new-check.yml") == MIXED_SURFACE
    assert classify_governance_path("scripts/qnty_tools/unrelated.py") is None


def test_exact_exception_for_replacement_control_file_is_accepted(tmp_path):
    base = _baseline(tmp_path)
    _write(tmp_path, "quantbot/control/guard.py", b"x" * 8)
    assert not ratchet_problems(measure_governed_surface(tmp_path), base | {"exceptions": [_exception("quantbot/control/", "quantbot/control/guard.py")]})


def test_exact_exception_for_new_mixed_tool_is_accepted(tmp_path):
    base = _baseline(tmp_path)
    _write(tmp_path, "scripts/qnty_runtime_guard_audit.py", b"x" * 8)
    assert not ratchet_problems(measure_governed_surface(tmp_path), base | {"exceptions": [_exception(MIXED_SURFACE, "scripts/qnty_runtime_guard_audit.py")]})


def test_exact_exception_for_new_mixed_workflow_is_accepted(tmp_path):
    base = _baseline(tmp_path)
    _write(tmp_path, ".github/workflows/qnty-new-check.yml", b"x" * 8)
    assert not ratchet_problems(measure_governed_surface(tmp_path), base | {"exceptions": [_exception(MIXED_SURFACE, ".github/workflows/qnty-new-check.yml")]})


def test_mixed_exception_contributes_its_permitted_budget(tmp_path):
    base = _baseline(tmp_path)
    _write(tmp_path, "scripts/qnty_runtime_guard_audit.py", b"x" * 10)
    assert not ratchet_problems(measure_governed_surface(tmp_path), base | {"exceptions": [_exception(MIXED_SURFACE, "scripts/qnty_runtime_guard_audit.py", 10)]})


def test_mixed_exception_cannot_be_consumed_by_another_mixed_path(tmp_path):
    base = _baseline(tmp_path)
    _write(tmp_path, "scripts/qnty_other.py", b"x" * 4)
    problems = ratchet_problems(measure_governed_surface(tmp_path), base | {"exceptions": [_exception(MIXED_SURFACE, "scripts/qnty_guard.py")]})
    assert problems


def test_control_exception_cannot_be_consumed_by_another_control_file(tmp_path):
    base = _baseline(tmp_path)
    _write(tmp_path, "quantbot/control/other.py", b"x" * 4)
    assert ratchet_problems(measure_governed_surface(tmp_path), base | {"exceptions": [_exception("quantbot/control/", "quantbot/control/guard.py")]})


def test_new_file_baseline_is_zero_and_growth_over_cap_fails(tmp_path):
    base = _baseline(tmp_path)
    assert base["per_file_bytes"].get("quantbot/control/guard.py", 0) == 0
    _write(tmp_path, "quantbot/control/guard.py", b"x" * 11)
    problems = ratchet_problems(measure_governed_surface(tmp_path), base | {"exceptions": [_exception("quantbot/control/", "quantbot/control/guard.py", 10)]})
    assert any("exceeds exception cap" in problem for problem in problems)


@pytest.mark.parametrize(("surface", "path", "identifier"), [
    ("quantbot/control/", "quantbot/control/*.py", "wildcard"),
    ("quantbot/control/", "quantbot/control/", "directory"),
    ("quantbot/control/", "/quantbot/control/guard.py", "absolute"),
    ("quantbot/control/", "quantbot/control/../guard.py", "traversal"),
    (MIXED_SURFACE, "quantbot/control/guard.py", "surface_mismatch"),
    ("unknown", "quantbot/control/guard.py", "unknown_surface"),
])
def test_invalid_exception_path_or_ownership_fails(tmp_path, surface, path, identifier):
    base = _baseline(tmp_path)
    assert validate_exceptions(base | {"exceptions": [_exception(surface, path)]}), identifier


def test_duplicate_exception_path_fails(tmp_path):
    base = _baseline(tmp_path)
    item = _exception("quantbot/control/", "quantbot/control/guard.py")
    assert validate_exceptions(base | {"exceptions": [item, item.copy()]})


def test_net_shrinkage_without_exceptions_remains_allowed(tmp_path):
    _write(tmp_path, "quantbot/control/old.py", b"x" * 10)
    base = _baseline(tmp_path)
    (tmp_path / "quantbot/control/old.py").unlink()
    assert not ratchet_problems(measure_governed_surface(tmp_path), base)


def test_net_zero_refactoring_without_exceptions_remains_allowed(tmp_path):
    _write(tmp_path, "quantbot/control/old.py", b"x" * 10)
    base = _baseline(tmp_path)
    (tmp_path / "quantbot/control/old.py").unlink()
    _write(tmp_path, "quantbot/control/new.py", b"x" * 10)
    assert not ratchet_problems(measure_governed_surface(tmp_path), base)


def test_unexcepted_growth_fails(tmp_path):
    base = _baseline(tmp_path)
    _write(tmp_path, "quantbot/control/guard.py", b"x")
    assert ratchet_problems(measure_governed_surface(tmp_path), base)
