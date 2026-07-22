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

    policy = snapshot["policy"]
    assert policy["rulesets"] == []
    assert policy["rulesets_configured"] is False
    assert policy["main_branch_protected"] is False
    assert policy["main_branch_protection"] is None
    assert policy["merge_methods"] == {
        "allow_squash_merge": True,
        "allow_merge_commit": True,
        "allow_rebase_merge": True,
        "delete_branch_on_merge": False,
    }
    assert policy["bypass_actors_present"] is False


def test_normalize_flags_bypass_actors_when_present(monkeypatch):
    responses = {
        ("gh", "api", "--paginate", "repos/CipherCuttle/Qnty/rulesets"): _FakeCompletedProcess(
            stdout=json.dumps([{"id": 1}]), returncode=0
        ),
        ("gh", "api", "repos/CipherCuttle/Qnty/rulesets/1"): _FakeCompletedProcess(
            stdout=json.dumps({"id": 1, "bypass_actors": [{"actor_id": 1}]}), returncode=0
        ),
        ("gh", "api", "repos/CipherCuttle/Qnty/branches/main/protection"): _FakeCompletedProcess(
            stdout=json.dumps({"required_status_checks": {}}), returncode=0
        ),
        ("gh", "api", "repos/CipherCuttle/Qnty"): _FakeCompletedProcess(stdout=json.dumps({}), returncode=0),
    }
    monkeypatch.setattr(subprocess, "run", _fake_run_factory(responses))

    snapshot = tool.normalize("CipherCuttle/Qnty")

    assert snapshot["policy"]["bypass_actors_present"] is True
    assert snapshot["policy"]["main_branch_protected"] is True


def test_list_summary_cannot_hide_bypass_actors(monkeypatch):
    responses = {
        ("gh", "api", "--paginate", "repos/CipherCuttle/Qnty/rulesets"): _FakeCompletedProcess(
            stdout=json.dumps([{"id": 7, "name": "summary-without-bypass"}]), returncode=0
        ),
        ("gh", "api", "repos/CipherCuttle/Qnty/rulesets/7"): _FakeCompletedProcess(
            stdout=json.dumps({"id": 7, "bypass_actors": [{"actor_id": 9}]}), returncode=0
        ),
        ("gh", "api", "repos/CipherCuttle/Qnty/branches/main/protection"): _FakeCompletedProcess(
            stdout=json.dumps({}), returncode=0
        ),
        ("gh", "api", "repos/CipherCuttle/Qnty"): _FakeCompletedProcess(stdout=json.dumps({}), returncode=0),
    }
    monkeypatch.setattr(subprocess, "run", _fake_run_factory(responses))
    assert tool.normalize("CipherCuttle/Qnty")["policy"]["bypass_actors_present"] is True


def test_unexpected_404_raises(monkeypatch):
    responses = {
        ("gh", "api", "--paginate", "repos/CipherCuttle/Qnty/rulesets"): _FakeCompletedProcess(
            stdout="", stderr='{"message":"Not Found","status":"404"}', returncode=1
        ),
    }
    monkeypatch.setattr(subprocess, "run", _fake_run_factory(responses))
    import pytest
    with pytest.raises(RuntimeError, match="failed"):
        tool.normalize("CipherCuttle/Qnty")


def test_unexpected_branch_protection_404_raises(monkeypatch):
    responses = {
        ("gh", "api", "--paginate", "repos/CipherCuttle/Qnty/rulesets"): _FakeCompletedProcess(stdout="[]", returncode=0),
        ("gh", "api", "repos/CipherCuttle/Qnty/branches/main/protection"): _FakeCompletedProcess(
            stdout="", stderr='{"message":"Not Found","status":"404"}', returncode=1
        ),
    }
    monkeypatch.setattr(subprocess, "run", _fake_run_factory(responses))
    import pytest
    with pytest.raises(RuntimeError, match="failed"):
        tool.normalize("CipherCuttle/Qnty")


def test_unchanged_policy_is_deterministic_across_capture_times(monkeypatch):
    responses = {
        ("gh", "api", "--paginate", "repos/CipherCuttle/Qnty/rulesets"): _FakeCompletedProcess(stdout="[]", returncode=0),
        ("gh", "api", "repos/CipherCuttle/Qnty/branches/main/protection"): _FakeCompletedProcess(
            stdout="", stderr='{"message":"Branch not protected","status":"404"}', returncode=1
        ),
        ("gh", "api", "repos/CipherCuttle/Qnty"): _FakeCompletedProcess(stdout=json.dumps({}), returncode=0),
    }
    monkeypatch.setattr(subprocess, "run", _fake_run_factory(responses))
    first = tool.normalize("CipherCuttle/Qnty", now=datetime(2026, 1, 1, tzinfo=timezone.utc))
    second = tool.normalize("CipherCuttle/Qnty", now=datetime(2026, 1, 2, tzinfo=timezone.utc))
    assert first["policy"] == second["policy"]
    assert first["capture"] != second["capture"]


def test_committed_snapshot_matches_active_enforcement_audit():
    snapshot_path = ROOT / "docs/governance/github_ruleset_snapshot.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    policy = snapshot["policy"]

    assert policy["repo"] == "CipherCuttle/Qnty"
    assert policy["rulesets_configured"] is True
    assert policy["main_branch_protected"] is False
    assert policy["main_branch_protection"] is None
    assert policy["bypass_actors_present"] is False

    assert len(policy["rulesets"]) == 1
    ruleset = policy["rulesets"][0]
    assert ruleset["id"] == 19570430
    assert ruleset["name"] == "Qnty main enforcement"
    assert ruleset["enforcement"] == "active"
    assert ruleset["target"] == "branch"
    assert ruleset["bypass_actors"] == []
    assert ruleset["conditions"]["ref_name"]["include"] == ["refs/heads/main"]
    assert ruleset["conditions"]["ref_name"]["exclude"] == []

    rule_types = [rule["type"] for rule in ruleset["rules"]]
    assert rule_types == ["deletion", "non_fast_forward", "pull_request", "required_status_checks"]

    rules_by_type = {rule["type"]: rule for rule in ruleset["rules"]}

    pr_params = rules_by_type["pull_request"]["parameters"]
    assert pr_params["required_approving_review_count"] == 0
    assert pr_params["require_code_owner_review"] is False
    assert pr_params["require_last_push_approval"] is False

    status_params = rules_by_type["required_status_checks"]["parameters"]
    assert status_params["strict_required_status_checks_policy"] is True
    contexts = {check["context"]: check["integration_id"] for check in status_params["required_status_checks"]}
    assert contexts == {"artifacts": 15368, "continuity": 15368, "full-suite": 15368}
