"""Seeded contract tests for exact, path-scoped governance debt allowances."""

from hygiene_ast import check_against_allowlist


KEYS = ("file", "symbol")
ENTRY = {"file": "tests/control/example.py", "symbol": "guard", "max_count": 1}


def test_missing_allowance_fails():
    assert check_against_allowlist([{"file": ENTRY["file"], "symbol": "new_guard"}], [ENTRY], KEYS)


def test_stale_allowance_fails():
    assert check_against_allowlist([], [ENTRY], KEYS)


def test_duplicate_allowance_fails():
    assert check_against_allowlist([{ "file": ENTRY["file"], "symbol": ENTRY["symbol"]}], [ENTRY, ENTRY.copy()], KEYS)


def test_over_count_fails():
    violation = {"file": ENTRY["file"], "symbol": ENTRY["symbol"]}
    assert check_against_allowlist([violation, violation], [ENTRY], KEYS)


def test_missing_path_or_symbol_in_allowance_fails():
    assert check_against_allowlist([], [{"file": ENTRY["file"], "max_count": 1}], KEYS)
