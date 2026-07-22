"""Reject new phase-dependent wrappers that return early -- skipping the
wrapped historical test body -- instead of executing it.

Shape: ``def outer(original): def inner(*a, **kw): if <cond>: ...; return
(bare); return original(*a, **kw); return inner``. New instances are
rejected; the debt allowlist permits exactly the five already-existing guard
generations confirmed on origin/main (see ``debt_allowlist.json``).
"""

from __future__ import annotations

from pathlib import Path

from hygiene_ast import check_against_allowlist, find_fake_pass_wrappers, load_debt_allowlist

ROOT = Path(__file__).parents[2]


def test_no_new_fake_pass_wrapper_in_repo():
    violations = find_fake_pass_wrappers(ROOT)
    allowlist = load_debt_allowlist()["fake_pass_wrappers"]
    problems = check_against_allowlist(violations, allowlist, ("file", "function"))
    assert not problems, "\n".join(problems)


def test_detector_fires_on_seeded_fake_pass_wrapper(tmp_path):
    bad_file = tmp_path / "bad_module.py"
    bad_file.write_text(
        "def _v099_guard(original):\n"
        "    def guarded(*args, **kwargs):\n"
        "        if current_phase() == 'v099':\n"
        "            check_v099_state()\n"
        "            return\n"
        "        return original(*args, **kwargs)\n"
        "    return guarded\n",
        encoding="utf-8",
    )
    violations = find_fake_pass_wrappers(tmp_path)
    assert len(violations) == 1
    assert violations[0]["function"] == "_v099_guard"


def test_detector_ignores_ordinary_decorator_that_always_calls_original(tmp_path):
    ok_file = tmp_path / "ok_module.py"
    ok_file.write_text(
        "def logged(original):\n"
        "    def wrapper(*args, **kwargs):\n"
        "        print('calling')\n"
        "        return original(*args, **kwargs)\n"
        "    return wrapper\n",
        encoding="utf-8",
    )
    assert find_fake_pass_wrappers(tmp_path) == []
