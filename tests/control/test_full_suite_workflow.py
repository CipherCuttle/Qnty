"""Structural contract for the always-on full-suite workflow."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).parents[2]
WORKFLOW = ROOT / ".github/workflows/qnty-full-suite.yml"

CHECKOUT_USES = "actions/checkout@v4"
SETUP_PYTHON_USES = "actions/setup-python@v5"
INSTALL_STEP_NAME = "Install package (test extras only)"
INSTALL_COMMAND = 'python -m pip install -e ".[test]"'
FULL_SUITE_STEP_NAME = "Full suite (unfiltered, default /tmp-backed tmp_path)"
FULL_SUITE_COMMAND = "python -m pytest -q"

REAL_FULL_SUITE_BLOCK = (
    f"      - name: {FULL_SUITE_STEP_NAME}\n"
    f"        run: {FULL_SUITE_COMMAND}"
)
ACTUAL_RUN_LINE = f"        run: {FULL_SUITE_COMMAND}"
CHECKOUT_BLOCK = (
    f"      - uses: {CHECKOUT_USES}\n"
    "        with:\n"
    "          fetch-depth: 0"
)
SETUP_PYTHON_BLOCK = (
    f"      - uses: {SETUP_PYTHON_USES}\n"
    "        with:\n"
    '          python-version: "3.12"'
)
INSTALL_BLOCK = (
    f"      - name: {INSTALL_STEP_NAME}\n"
    f"        run: {INSTALL_COMMAND}"
)


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


def _exact_matches(steps: list[dict[str, str]], key: str, value: str) -> list[dict[str, str]]:
    return [step for step in steps if step.get(key) == value]


def _unique_step(steps: list[dict[str, str]], key: str, value: str) -> dict[str, str]:
    """Return the single step matching key==value; fail on zero or >1 matches."""
    matches = _exact_matches(steps, key, value)
    assert len(matches) == 1, f"expected exactly one step with {key}={value!r}, found {len(matches)}"
    return matches[0]


def _full_suite_command_is_exact(workflow: str) -> bool:
    """True iff exactly one step has the exact Full suite name and exact command."""
    matches = _exact_matches(_workflow_steps(workflow), "name", FULL_SUITE_STEP_NAME)
    return len(matches) == 1 and matches[0].get("run") == FULL_SUITE_COMMAND


def _workflow_is_structurally_valid(workflow: str) -> bool:
    try:
        steps = _workflow_steps(workflow)
        assert _unique_step(steps, "uses", CHECKOUT_USES)["with.fetch-depth"] == "0"
        assert _unique_step(steps, "uses", SETUP_PYTHON_USES)["with.python-version"] == '"3.12"'
        assert _unique_step(steps, "name", INSTALL_STEP_NAME)["run"] == INSTALL_COMMAND
        assert _full_suite_command_is_exact(workflow)
    except AssertionError:
        return False
    return True


def test_full_suite_workflow_preserves_history_and_ci_scope():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    steps = _workflow_steps(workflow)

    assert _unique_step(steps, "uses", CHECKOUT_USES)["with.fetch-depth"] == "0"
    assert _unique_step(steps, "uses", SETUP_PYTHON_USES)["with.python-version"] == '"3.12"'
    assert _unique_step(steps, "name", INSTALL_STEP_NAME)["run"] == INSTALL_COMMAND
    assert _full_suite_command_is_exact(workflow)
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
    assert _full_suite_command_is_exact(workflow)
    assert workflow.count(REAL_FULL_SUITE_BLOCK) == 1
    assert workflow.count(ACTUAL_RUN_LINE) == 1

    mutations = {
        # 1. Real command shortened; a duplicate prefix-name decoy has the exact command.
        "shortened_real_command_with_prefix_name_decoy": workflow.replace(
            REAL_FULL_SUITE_BLOCK,
            f"      - name: {FULL_SUITE_STEP_NAME}\n"
            "        run: python -m pytest\n\n"
            "      - name: Full suite (mirrored backup)\n"
            f"        run: {FULL_SUITE_COMMAND}",
        ),
        # 2. Two steps with the exact Full suite name, only one correct.
        "duplicate_exact_name_only_one_correct": workflow.replace(
            REAL_FULL_SUITE_BLOCK,
            REAL_FULL_SUITE_BLOCK + "\n\n"
            f"      - name: {FULL_SUITE_STEP_NAME}\n"
            "        run: python -m pytest",
        ),
        # 3. Two steps with the exact Full suite name, both correct.
        "duplicate_exact_name_both_correct": workflow.replace(
            REAL_FULL_SUITE_BLOCK, REAL_FULL_SUITE_BLOCK + "\n\n" + REAL_FULL_SUITE_BLOCK
        ),
        # 4. Exact command under a differently named decoy step (real step broken).
        "exact_command_under_differently_named_decoy": workflow.replace(
            REAL_FULL_SUITE_BLOCK,
            f"      - name: {FULL_SUITE_STEP_NAME}\n"
            "        run: python -m pytest\n\n"
            "      - name: Decoy\n"
            f"        run: {FULL_SUITE_COMMAND}",
        ),
        # 5. Exact command appears only inside a free-form comment.
        "exact_command_in_a_comment": workflow.replace(
            ACTUAL_RUN_LINE, f"        # full suite: {FULL_SUITE_COMMAND}"
        ),
        # 6. Exact command text used as the step name; run field wrong.
        "exact_command_as_step_name_wrong_run": workflow.replace(
            REAL_FULL_SUITE_BLOCK,
            f"      - name: {FULL_SUITE_COMMAND}\n        run: python -m pytest",
        ),
        # 7. Commented-out run key (looks like a real key but is disabled).
        "commented_out_run_key": workflow.replace(
            ACTUAL_RUN_LINE, f"        # run: {FULL_SUITE_COMMAND}"
        ),
        # 8. Wrongly indented run key (9 spaces instead of the fixed 8).
        "wrongly_indented_run_key": workflow.replace(
            ACTUAL_RUN_LINE, f"         run: {FULL_SUITE_COMMAND}"
        ),
        # 9. Multiline block scalar containing the command but no exact run field.
        "multiline_scalar_command_no_exact_run_field": workflow.replace(
            ACTUAL_RUN_LINE,
            "        run: |\n"
            "          echo setup\n"
            f"          {FULL_SUITE_COMMAND}",
        ),
        # 10. Full suite step missing entirely.
        "missing_full_suite_step": workflow.replace(REAL_FULL_SUITE_BLOCK, ""),
        # 11. Full suite step renamed; command untouched.
        "renamed_full_suite_step": workflow.replace(
            FULL_SUITE_STEP_NAME, "Full suite (renamed)"
        ),
        # 12. Real, unique Full suite step present but with the wrong command.
        "unique_step_wrong_command": workflow.replace(
            ACTUAL_RUN_LINE, "        run: python -m pytest"
        ),
    }

    assert len(mutations) == 12
    for label, mutated in mutations.items():
        assert mutated != workflow, label
        assert not _full_suite_command_is_exact(mutated), label


def test_duplicate_identifying_steps_break_structural_validity():
    """Checkout, setup-python, and install steps must also match uniquely."""
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert _workflow_is_structurally_valid(workflow)
    assert workflow.count(CHECKOUT_BLOCK) == 1
    assert workflow.count(SETUP_PYTHON_BLOCK) == 1
    assert workflow.count(INSTALL_BLOCK) == 1

    duplicate_checkout = workflow.replace(CHECKOUT_BLOCK, CHECKOUT_BLOCK + "\n\n" + CHECKOUT_BLOCK)
    duplicate_setup_python = workflow.replace(
        SETUP_PYTHON_BLOCK, SETUP_PYTHON_BLOCK + "\n\n" + SETUP_PYTHON_BLOCK
    )
    duplicate_install = workflow.replace(INSTALL_BLOCK, INSTALL_BLOCK + "\n\n" + INSTALL_BLOCK)
    missing_checkout = workflow.replace(CHECKOUT_BLOCK, "")

    assert not _workflow_is_structurally_valid(duplicate_checkout)
    assert not _workflow_is_structurally_valid(duplicate_setup_python)
    assert not _workflow_is_structurally_valid(duplicate_install)
    assert not _workflow_is_structurally_valid(missing_checkout)
