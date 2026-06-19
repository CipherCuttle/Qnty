"""Regression tests for the REST fetcher ``END_TIME_MS`` resolution.

Root cause being guarded: ``scripts/fetch_funding_rest.py`` and
``scripts/fetch_ohlcv_rest.py`` previously hardcoded a stale pagination cutoff
(``1776643200000`` == 2026-04-20) and ignored the ``END_TIME_MS`` env var that
``ops/bin/qnty-data-refresh.sh`` exports. For a symbol whose pages landed past
that stale date (SOLUSDT funding), pagination stopped early and silently
truncated the most recent data while the fetch logged success. These tests pin
the corrected env-driven, fail-closed behavior.

The scripts are not a package and import ``requests`` at module top, so they are
loaded by file path with a stubbed ``requests`` module. ``main()`` (the only
network path) is never invoked, so no live network is touched and no real
``data/*.csv`` is written.
"""

import importlib.util
import sys
import time
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = {
    "fetch_funding_rest": REPO_ROOT / "scripts" / "fetch_funding_rest.py",
    "fetch_ohlcv_rest": REPO_ROOT / "scripts" / "fetch_ohlcv_rest.py",
}

# The stale cutoff that caused the SOLUSDT truncation bug. It must not appear as
# active production logic in either fetcher (it may live only here, as a marker).
STALE_END_TIME_MS = 1776643200000


def _load_script(mod_name: str, monkeypatch) -> types.ModuleType:
    """Load a script module by path with a stubbed ``requests`` and a clean env."""
    # Ensure import-time END_TIME_MS resolution uses the default branch (no network).
    monkeypatch.delenv("END_TIME_MS", raising=False)
    if "requests" not in sys.modules:
        monkeypatch.setitem(sys.modules, "requests", types.ModuleType("requests"))

    spec = importlib.util.spec_from_file_location(mod_name, SCRIPTS[mod_name])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(params=sorted(SCRIPTS))
def fetcher(request, monkeypatch):
    return _load_script(request.param, monkeypatch)


def test_reads_end_time_ms_from_env(fetcher, monkeypatch):
    """When END_TIME_MS is set, it is parsed as integer epoch ms verbatim."""
    monkeypatch.setenv("END_TIME_MS", "1781856000001")
    assert fetcher.resolve_end_time_ms() == 1781856000001


def test_defaults_to_future_cutoff_when_env_absent(fetcher, monkeypatch):
    """With no env var, default to ~now + 1 day (a dynamic future cutoff)."""
    monkeypatch.delenv("END_TIME_MS", raising=False)
    before = int(time.time() * 1000)
    resolved = fetcher.resolve_end_time_ms()
    after = int(time.time() * 1000)
    one_day_ms = 86_400_000
    # Strictly in the future and within a day-ish of now (no stale 2026-04-20).
    assert before < resolved
    assert before + one_day_ms - 5_000 <= resolved <= after + one_day_ms + 5_000
    assert resolved != STALE_END_TIME_MS


def test_blank_env_falls_back_to_default(fetcher, monkeypatch):
    """An empty/whitespace value is treated as unset (the default branch)."""
    monkeypatch.setenv("END_TIME_MS", "   ")
    assert fetcher.resolve_end_time_ms() > int(time.time() * 1000)


@pytest.mark.parametrize("bad", ["not-a-number", "12.5", "1e9", "0x10"])
def test_malformed_env_fails_closed(fetcher, monkeypatch, bad):
    """A malformed (non-integer) value must raise — never silently fall back."""
    monkeypatch.setenv("END_TIME_MS", bad)
    with pytest.raises(ValueError, match="END_TIME_MS"):
        fetcher.resolve_end_time_ms()


@pytest.mark.parametrize("path", sorted(SCRIPTS.values()))
def test_stale_constant_absent_from_active_logic(path):
    """The stale hardcoded cutoff must not appear anywhere in the fetcher source."""
    source = path.read_text()
    assert str(STALE_END_TIME_MS) not in source, (
        f"{path.name} still references the stale cutoff {STALE_END_TIME_MS}"
    )


@pytest.mark.parametrize("mod_name", sorted(SCRIPTS))
def test_module_end_time_ms_is_dynamic_int(mod_name, monkeypatch):
    """Module-level END_TIME_MS is resolved (int) at import via the helper."""
    module = _load_script(mod_name, monkeypatch)
    assert isinstance(module.END_TIME_MS, int)
    assert module.END_TIME_MS != STALE_END_TIME_MS
