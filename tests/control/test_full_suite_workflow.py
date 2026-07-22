"""Structural contract for the always-on full-suite workflow."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).parents[2]
WORKFLOW = ROOT / ".github/workflows/qnty-full-suite.yml"


def _workflow_steps(workflow: str) -> list[dict[str, str]]:
    """Read this workflow's fixed-indentation step sequence without YAML."""
    steps = []
    step = None
    in_with = False
    for line in workflow.splitlines():
        step_start = re.match(r"^ {6}- (uses|name): (.+)$", line)
        if step_start:
            step = {step_start.group(1): step_start.group(2)}
            steps.append(step)
            in_with = False
            continue
        if step is None:
            continue
        field = re.match(r"^ {8}([a-z-]+):(?: (.+))?$", line)
        if field:
            key, value = field.groups()
            step[key] = value or ""
            in_with = key == "with"
            continue
        nested_field = re.match(r"^ {10}([a-z-]+): (.+)$", line)
        if in_with and nested_field:
            key, value = nested_field.groups()
            step[f"with.{key}"] = value
    return steps


def _step_with(steps: list[dict[str, str]], key: str, value: str) -> dict[str, str]:
    return next(step for step in steps if step.get(key) == value)


def _has_exact_full_suite_command(workflow: str) -> bool:
    steps = _workflow_steps(workflow)
    return any(
        step.get("name", "").startswith("Full suite")
        and step.get("run") == "python -m pytest -q"
        for step in steps
    )


def test_full_suite_workflow_preserves_history_and_ci_scope():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    steps = _workflow_steps(workflow)

    assert _step_with(steps, "uses", "actions/checkout@v4")["with.fetch-depth"] == "0"
    assert _step_with(steps, "uses", "actions/setup-python@v5")["with.python-version"] == '"3.12"'
    assert _step_with(steps, "name", "Install package (test extras only)")["run"] == 'python -m pip install -e ".[test]"'
    assert _has_exact_full_suite_command(workflow)
    assert all("--basetemp" not in step.get("run", "") for step in steps)
    assert not re.search(r"^\s*paths:\s*", workflow, re.MULTILINE)
    assert not re.search(r"^\s*paths-ignore:\s*", workflow, re.MULTILINE)
    assert re.search(r"^\s*pull_request:\s*$", workflow, re.MULTILINE)
    assert re.search(
        r"^\s*push:\n\s*branches:\s*\[main\]\s*$", workflow, re.MULTILINE
    )
    assert re.search(
        r"^permissions:\n\s+contents:\s+read\s*$", workflow, re.MULTILINE
    )


def test_full_suite_command_rejects_adversarial_mutations():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    actual_run = "        run: python -m pytest -q"
    mutations = [
        workflow.replace(actual_run, "        # python -m pytest -q"),
        workflow.replace(actual_run, "        run: python -m pytest"),
        workflow.replace(
            actual_run,
            "        run: python -m pytest\n\n"
            "      - name: Decoy\n"
            "        run: python -m pytest -q",
        ),
        workflow.replace(
            "      - name: Full suite (unfiltered, default /tmp-backed tmp_path)\n"
            f"{actual_run}",
            "      - name: python -m pytest -q\n"
            "        run: python -m pytest",
        ),
        workflow.replace(actual_run, "        # run: python -m pytest -q"),
    ]
    assert all(not _has_exact_full_suite_command(mutated) for mutated in mutations)
