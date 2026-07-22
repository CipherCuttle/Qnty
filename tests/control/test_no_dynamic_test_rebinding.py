"""Reject new dynamic test-function rebinding via ``globals()[...] = ...``.

This is the mechanism that lets a later "phase" silently swap out an earlier,
already-collected test function for a different implementation at collection
time. New instances are rejected outright; the debt allowlist permits exactly
the already-existing instances confirmed on origin/main (see
``debt_allowlist.json``), pending their removal in the entropy-brake PR.
"""

from __future__ import annotations

from pathlib import Path

from hygiene_ast import check_against_allowlist, find_globals_rebindings, load_debt_allowlist

ROOT = Path(__file__).parents[2]


def test_no_new_globals_rebinding_in_repo():
    violations = find_globals_rebindings(ROOT)
    allowlist = load_debt_allowlist()["globals_rebindings"]
    problems = check_against_allowlist(violations, allowlist, ("file", "wrapper"))
    assert not problems, "\n".join(problems)


def test_detector_fires_on_seeded_globals_rebinding(tmp_path):
    bad_file = tmp_path / "bad_module.py"
    bad_file.write_text(
        "def _v099_guard(original):\n"
        "    def guarded(*args, **kwargs):\n"
        "        return original(*args, **kwargs)\n"
        "    return guarded\n"
        "\n"
        "for _name in ('test_something',):\n"
        "    globals()[_name] = _v099_guard(globals()[_name])\n",
        encoding="utf-8",
    )
    violations = find_globals_rebindings(tmp_path)
    assert len(violations) == 1
    assert violations[0]["wrapper"] == "_v099_guard"


def test_detector_ignores_ordinary_globals_read(tmp_path):
    ok_file = tmp_path / "ok_module.py"
    ok_file.write_text(
        "def f():\n"
        "    return globals().get('x')\n"
        "\n"
        "x = 1\n",
        encoding="utf-8",
    )
    assert find_globals_rebindings(tmp_path) == []
