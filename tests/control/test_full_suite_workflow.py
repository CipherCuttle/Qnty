"""Structural contract for the always-on full-suite workflow."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).parents[2]
WORKFLOW = ROOT / ".github/workflows/qnty-full-suite.yml"


def test_full_suite_workflow_preserves_history_and_ci_scope():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    checkout = re.compile(
        r"^\s*- uses: actions/checkout@v4\n"
        r"^\s+with:\n"
        r"^\s+fetch-depth: 0\s*$",
        re.MULTILINE,
    )
    assert checkout.search(workflow)
    assert "python -m pytest -q" in workflow
    assert not re.search(r"^\s*paths:\s*", workflow, re.MULTILINE)
    assert not re.search(r"^\s*paths-ignore:\s*", workflow, re.MULTILINE)
    assert re.search(r"^\s*pull_request:\s*$", workflow, re.MULTILINE)
    assert re.search(
        r"^\s*push:\n\s*branches:\s*\[main\]\s*$", workflow, re.MULTILINE
    )
    assert re.search(
        r"^permissions:\n\s+contents:\s+read\s*$", workflow, re.MULTILINE
    )
