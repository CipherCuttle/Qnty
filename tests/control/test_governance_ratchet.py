"""Governance growth ratchet: the governed control-plane surface
(quantbot/continuity/, quantbot/assurance/, tests/continuity/,
tests/assurance/, docs/control/) may not grow beyond its recorded baseline
except through an exact, path-scoped, expiring exception.

This is a floor, not a target: a shrinkage (e.g. the entropy-brake PR
deleting fake-pass wrappers) is always allowed and should be followed by
re-recording a lower baseline in that same PR. Nothing here can verify that a
given deletion preserved every meaningful adversarial test rather than just
deleting it to make a byte budget -- that judgment call is for human review;
this ratchet only proves size didn't silently grow.
"""

from __future__ import annotations

import json
from pathlib import Path

from governance_ratchet import find_relocated_governance_basenames, measure_governed_surface

ROOT = Path(__file__).parents[2]
BASELINE_PATH = Path(__file__).parent / "governance_baseline.json"


def _load_baseline():
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def _exception_budget_for(baseline, governed_dir):
    return sum(
        exc["max_additional_bytes"]
        for exc in baseline["exceptions"]
        if exc["path"] == governed_dir or exc["path"].startswith(governed_dir)
    )


def test_governed_surface_has_not_grown_beyond_baseline_plus_exceptions():
    baseline = _load_baseline()
    current = measure_governed_surface(ROOT)

    problems = []
    for governed_dir, baseline_bytes in baseline["per_dir_bytes"].items():
        current_bytes = current["per_dir_bytes"].get(governed_dir, 0)
        ceiling = baseline_bytes + _exception_budget_for(baseline, governed_dir)
        if current_bytes > ceiling:
            problems.append(
                f"{governed_dir}: {current_bytes} bytes exceeds baseline+exceptions ceiling {ceiling} "
                f"(baseline={baseline_bytes}, exception_budget={ceiling - baseline_bytes})"
            )

    total_ceiling = baseline["total_bytes"] + sum(exc["max_additional_bytes"] for exc in baseline["exceptions"])
    if current["total_bytes"] > total_ceiling:
        problems.append(f"total: {current['total_bytes']} bytes exceeds ceiling {total_ceiling}")

    assert not problems, "\n".join(problems)


def test_no_governance_code_relocated_outside_counted_directories():
    baseline = _load_baseline()
    # Use the basenames frozen in the baseline (not recomputed from the
    # current tree): the evasion this guards against is moving a file fully
    # OUT of a governed directory, which would make it vanish from a
    # "current tree" basename set and defeat the check entirely.
    hits = find_relocated_governance_basenames(ROOT, baseline["governed_basenames"])
    assert not hits, f"governance-named files found outside counted directories: {hits}"


def test_every_exception_is_path_scoped_bounded_justified_and_has_an_expiry():
    baseline = _load_baseline()
    for exc in baseline["exceptions"]:
        assert isinstance(exc.get("path"), str) and exc["path"], exc
        assert any(exc["path"].startswith(d) for d in baseline["per_dir_bytes"]), (
            f"exception path must be scoped under a counted governed directory: {exc}"
        )
        assert isinstance(exc.get("max_additional_bytes"), int) and exc["max_additional_bytes"] > 0, exc
        assert isinstance(exc.get("reason"), str) and exc["reason"], exc
        assert isinstance(exc.get("expires_in_pr"), str) and exc["expires_in_pr"], exc


def test_seeded_growth_beyond_baseline_is_rejected(tmp_path):
    """Proves the ratchet actually fires: build a synthetic tree matching the
    baseline's governed directories, add one file's worth of growth beyond the
    recorded baseline, and confirm the same comparison logic used above would
    reject it.
    """
    baseline = _load_baseline()
    for governed_dir in baseline["per_dir_bytes"]:
        (tmp_path / governed_dir).mkdir(parents=True, exist_ok=True)
    # Recorded baseline says quantbot/continuity/ had 305061 bytes; write more.
    (tmp_path / "quantbot/continuity/context.py").write_bytes(b"x" * (baseline["per_dir_bytes"]["quantbot/continuity/"] + 1))

    current = measure_governed_surface(tmp_path)
    grew_dir = "quantbot/continuity/"
    ceiling = baseline["per_dir_bytes"][grew_dir] + _exception_budget_for(baseline, grew_dir)
    assert current["per_dir_bytes"][grew_dir] > ceiling
