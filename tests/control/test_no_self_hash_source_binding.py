"""Reject new bindings of a test-file or validator-source path to a hash
(pinned literal or dynamically computed) inside the continuity/control
modules themselves. Binding a hash of the test suite or the validator's own
source into the evidence the validator checks is circular: the validator can
be made to validate itself. New instances are rejected; the debt allowlist
permits exactly the bindings confirmed present on origin/main's
``quantbot/continuity/context.py`` (see ``debt_allowlist.json``).
"""

from __future__ import annotations

from pathlib import Path

from hygiene_ast import check_against_allowlist, find_self_hash_source_bindings, load_debt_allowlist

ROOT = Path(__file__).parents[2]
SCAN_DIRS = ["quantbot/continuity/", "quantbot/control/"]


def test_no_new_self_hash_source_binding_in_repo():
    violations = find_self_hash_source_bindings(ROOT, SCAN_DIRS)
    allowlist = load_debt_allowlist()["self_hash_source_bindings"]
    problems = check_against_allowlist(violations, allowlist, ("file", "key", "kind"))
    assert not problems, "\n".join(problems)


def test_detector_fires_on_seeded_pinned_hash_binding(tmp_path):
    scan_dir = tmp_path / "quantbot" / "continuity"
    scan_dir.mkdir(parents=True)
    (scan_dir / "validator.py").write_text(
        "_EXPECTED = {\n"
        "    'tests/some/test_thing.py': '" + ("ab" * 32) + "',\n"
        "}\n",
        encoding="utf-8",
    )
    violations = find_self_hash_source_bindings(tmp_path, ["quantbot/continuity/"])
    assert len(violations) == 1
    assert violations[0]["kind"] == "pinned_hash"
    assert violations[0]["key"] == "tests/some/test_thing.py"


def test_detector_fires_on_seeded_dynamic_hash_binding(tmp_path):
    scan_dir = tmp_path / "quantbot" / "control"
    scan_dir.mkdir(parents=True)
    (scan_dir / "validator.py").write_text(
        "import hashlib\n"
        "\n"
        "def expected(root):\n"
        "    return {\n"
        "        'quantbot/control/validator.py': hashlib.sha256((root / 'quantbot/control/validator.py').read_bytes()).hexdigest(),\n"
        "    }\n",
        encoding="utf-8",
    )
    violations = find_self_hash_source_bindings(tmp_path, ["quantbot/control/"])
    assert len(violations) == 1
    assert violations[0]["kind"] == "dynamic_hash"


def test_detector_ignores_hash_binding_of_a_non_source_artifact(tmp_path):
    scan_dir = tmp_path / "quantbot" / "continuity"
    scan_dir.mkdir(parents=True)
    (scan_dir / "validator.py").write_text(
        "_EXPECTED = {\n"
        "    'docs/artifacts/candidate1-real-input-v0.json': '" + ("cd" * 32) + "',\n"
        "}\n",
        encoding="utf-8",
    )
    assert find_self_hash_source_bindings(tmp_path, ["quantbot/continuity/"]) == []
