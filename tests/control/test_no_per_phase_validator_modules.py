"""Forward-looking tripwire for the replacement control architecture (PR-2
onward): reject a per-phase validator module naming shape (e.g.
``phase_v027_validator.py``) anywhere under ``quantbot/control/`` or
``quantbot/continuity/``. Neither directory contains such a module on
origin/main today -- this test exists so a future PR cannot introduce one
without the hygiene suite catching it, per the mandate that the replacement
architecture uses one declarative transition table, not one module per phase.
"""

from __future__ import annotations

from pathlib import Path

from hygiene_ast import check_against_allowlist, find_per_phase_validator_modules, load_debt_allowlist

ROOT = Path(__file__).parents[2]
SCAN_DIRS = ["quantbot/control/", "quantbot/continuity/"]


def test_no_per_phase_validator_modules_in_repo():
    violations = find_per_phase_validator_modules(ROOT, SCAN_DIRS)
    allowlist = load_debt_allowlist()["per_phase_validator_modules"]
    problems = check_against_allowlist(violations, allowlist, ("file",))
    assert not problems, "\n".join(problems)


def test_detector_fires_on_seeded_per_phase_validator_module(tmp_path):
    scan_dir = tmp_path / "quantbot" / "control"
    scan_dir.mkdir(parents=True)
    (scan_dir / "phase_v027_validator.py").write_text("# stub\n", encoding="utf-8")
    violations = find_per_phase_validator_modules(tmp_path, ["quantbot/control/"])
    assert len(violations) == 1
    assert violations[0]["file"] == "quantbot/control/phase_v027_validator.py"


def test_detector_ignores_ordinarily_named_module(tmp_path):
    scan_dir = tmp_path / "quantbot" / "control"
    scan_dir.mkdir(parents=True)
    (scan_dir / "validator.py").write_text("# stub\n", encoding="utf-8")
    (scan_dir / "guard.py").write_text("# stub\n", encoding="utf-8")
    assert find_per_phase_validator_modules(tmp_path, ["quantbot/control/"]) == []
