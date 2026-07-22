"""Unit tests for scripts/qnty_ruleset_snapshot.py's normalization logic.

Does not shell out to the real `gh` CLI (no network, no auth dependency in
CI): `subprocess.run` is monkeypatched with canned responses matching what
the Phase-A audit actually observed (empty rulesets, unprotected main, all
three merge methods enabled), so this proves the tool reports that state
faithfully without requiring a live GitHub session.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import qnty_ruleset_snapshot as tool  # noqa: E402


class _FakeCompletedProcess:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _fake_run_factory(responses):
    def _fake_run(cmd, capture_output, text, check):
        key = tuple(cmd)
        if key not in responses:
            raise AssertionError(f"unexpected command: {cmd}")
        return responses[key]

    return _fake_run


def test_normalize_reports_absent_enforcement_faithfully(monkeypatch):
    responses = {
        ("gh", "api", "--paginate", "repos/CipherCuttle/Qnty/rulesets"): _FakeCompletedProcess(
            stdout="[]\n", returncode=0
        ),
        ("gh", "api", "repos/CipherCuttle/Qnty/branches/main/protection"): _FakeCompletedProcess(
            stdout="", stderr='{"message":"Branch not protected","status":"404"}', returncode=1
        ),
        ("gh", "api", "repos/CipherCuttle/Qnty"): _FakeCompletedProcess(
            stdout=json.dumps(
                {
                    "allow_squash_merge": True,
                    "allow_merge_commit": True,
                    "allow_rebase_merge": True,
                    "delete_branch_on_merge": False,
                }
            ),
            returncode=0,
        ),
    }
    monkeypatch.setattr(subprocess, "run", _fake_run_factory(responses))

    snapshot = tool.normalize("CipherCuttle/Qnty", now=datetime(2026, 1, 1, tzinfo=timezone.utc))

    assert snapshot["rulesets"] == []
    assert snapshot["rulesets_configured"] is False
    assert snapshot["main_branch_protected"] is False
    assert snapshot["main_branch_protection"] is None
    assert snapshot["merge_methods"] == {
        "allow_squash_merge": True,
        "allow_merge_commit": True,
        "allow_rebase_merge": True,
        "delete_branch_on_merge": False,
    }
    assert snapshot["bypass_actors_present"] is False


def test_normalize_flags_bypass_actors_when_present(monkeypatch):
    responses = {
        ("gh", "api", "--paginate", "repos/CipherCuttle/Qnty/rulesets"): _FakeCompletedProcess(
            stdout=json.dumps([{"id": 1, "bypass_actors": [{"actor_id": 1}]}]), returncode=0
        ),
        ("gh", "api", "repos/CipherCuttle/Qnty/branches/main/protection"): _FakeCompletedProcess(
            stdout=json.dumps({"required_status_checks": {}}), returncode=0
        ),
        ("gh", "api", "repos/CipherCuttle/Qnty"): _FakeCompletedProcess(stdout=json.dumps({}), returncode=0),
    }
    monkeypatch.setattr(subprocess, "run", _fake_run_factory(responses))

    snapshot = tool.normalize("CipherCuttle/Qnty")

    assert snapshot["bypass_actors_present"] is True
    assert snapshot["main_branch_protected"] is True


def test_committed_snapshot_matches_audit_baseline():
    snapshot_path = ROOT / "docs/governance/github_ruleset_snapshot.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert snapshot["rulesets"] == []
    assert snapshot["main_branch_protected"] is False
    assert snapshot["repo"] == "CipherCuttle/Qnty"
