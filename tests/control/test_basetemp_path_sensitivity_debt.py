"""Documents, without changing, a technical-debt coupling found during the
Phase-A audit: ``tests/artifacts/test_store.py::test_workspace_store_must_be_declared_explicitly``
and ``::test_cli_rejects_tmp_store_without_workspace_declaration`` use pytest's
default ``tmp_path`` fixture as a stand-in for "a location under a prohibited
canonical-store prefix" (``PROHIBITED_CANONICAL_STORE_PREFIXES = ("/tmp",
"/srv/qnty")`` in ``quantbot/artifacts/store.py``). That stand-in is only valid
because pytest's default ``tmp_path`` resolves under ``/tmp``.

This is *not* a bug in ``quantbot.artifacts.store`` -- the prohibition itself
is an intentional, correct safety invariant (see
docs/agent/START_HERE.md: "Canonical artifact paths must never be under /tmp
or production /srv/qnty"). It is a test-authoring coupling: running the suite
with ``--basetemp`` pointed outside ``/tmp`` (as this task's own hygiene
guidance for copy-heavy tests elsewhere suggests) silently flips those two
tests' outcome, because their fixture no longer resolves under a prohibited
prefix. The Phase-A audit reproduced this directly: running the full suite
with a home-cache-backed ``--basetemp`` produced 90 apparent failures; the
same suite passes cleanly (0 failed) under pytest's default (``/tmp``-backed)
``tmp_path``. Only these 2 of the 90 were genuine path-sensitivity artifacts
in this narrow sense; the other 88 were downstream of the same root cause in
different tests (see PR-0 report for the full breakdown).

Per the PR-0 instructions, this is recorded as debt, not fixed here: fixing it
would mean changing ``tests/artifacts/test_store.py`` to assert on the
prohibited-prefix behavior directly (e.g. via ``PROHIBITED_CANONICAL_STORE_PREFIXES``
or a monkeypatched root) rather than relying on ``tmp_path``'s default
location, which is a real behavior/semantics change out of scope for an
enforcement-baseline PR.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from quantbot.artifacts.store import ArtifactStoreError, FilesystemStore, require_allowed_canonical_root


def test_prohibited_prefix_check_is_keyed_on_absolute_path_not_fixture_identity(tmp_path):
    """The real invariant is about the resolved path prefix, not about
    "being a pytest tmp_path". Demonstrate both sides directly, independent of
    where pytest's tmp_path happens to be configured to live.
    """
    under_tmp = Path("/tmp/qnty-hygiene-demo-not-created")
    with pytest.raises(ArtifactStoreError, match="prohibited"):
        require_allowed_canonical_root(under_tmp)

    not_under_tmp = tmp_path / "store"  # tmp_path here is whatever this test run's basetemp is
    if str(not_under_tmp.resolve()).startswith(("/tmp", "/srv/qnty")):
        pytest.skip("this test run's tmp_path itself resolves under a prohibited prefix; no contrast to show")
    assert require_allowed_canonical_root(not_under_tmp) == not_under_tmp.resolve()


def test_documents_that_test_store_assertions_depend_on_tmp_path_location(tmp_path):
    """Direct, minimal reproduction of the coupling, without touching
    tests/artifacts/test_store.py: build the same two assertions that file
    makes, and show the outcome is contingent on whether tmp_path resolves
    under a prohibited prefix.
    """
    resolves_under_prohibited = str(tmp_path.resolve()).startswith(("/tmp", "/srv/qnty"))

    if resolves_under_prohibited:
        with pytest.raises(ArtifactStoreError, match="prohibited"):
            FilesystemStore(tmp_path)
    else:
        # This is exactly the silent flip: under a non-/tmp basetemp, the
        # same call that test_store.py expects to raise instead succeeds.
        store = FilesystemStore(tmp_path)
        assert store.canonical is True
