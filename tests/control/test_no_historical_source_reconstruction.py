"""Reject new helpers that reconstruct historical *source* (.py) bytes and
hash-verify them before writing -- whether by truncating current bytes back
to a marker boundary, by in-place byte find/replace, or by decoding an
embedded base64 historical blob. New instances are rejected; the debt
allowlist permits exactly the instances confirmed present on origin/main (see
``debt_allowlist.json`` for the exact list and a factual correction regarding
one entry's true origin).
"""

from __future__ import annotations

from pathlib import Path

from hygiene_ast import check_against_allowlist, find_source_reconstruction_functions, load_debt_allowlist

ROOT = Path(__file__).parents[2]


def test_no_new_source_reconstruction_helper_in_repo():
    violations = find_source_reconstruction_functions(ROOT)
    allowlist = load_debt_allowlist()["source_reconstruction_functions"]
    problems = check_against_allowlist(violations, allowlist, ("file", "function"))
    assert not problems, "\n".join(problems)


def test_detector_fires_on_seeded_truncation_restore(tmp_path):
    bad_file = tmp_path / "bad_module.py"
    bad_file.write_text(
        "import hashlib\n"
        "\n"
        "_PINNED = {'quantbot/some_module.py': 'deadbeef' * 8}\n"
        "\n"
        "def _restore_v099_sources(root):\n"
        "    for path, expected in _PINNED.items():\n"
        "        target = root / path\n"
        "        raw = target.read_bytes()\n"
        "        boundary = raw.index(b'MARKER')\n"
        "        historical = raw[:boundary]\n"
        "        assert hashlib.sha256(historical).hexdigest() == expected\n"
        "        target.write_bytes(historical)\n",
        encoding="utf-8",
    )
    violations = find_source_reconstruction_functions(tmp_path)
    assert len(violations) == 1
    assert violations[0]["function"] == "_restore_v099_sources"


def test_detector_fires_on_seeded_base64_blob_restore(tmp_path):
    bad_file = tmp_path / "bad_module2.py"
    bad_file.write_text(
        "import base64\n"
        "import hashlib\n"
        "\n"
        "_BLOBS = {'quantbot/some_module.py': 'ZGVhZGJlZWY='}\n"
        "_HASHES = {'quantbot/some_module.py': 'deadbeef' * 8}\n"
        "\n"
        "def _restore_historical_tree(destination):\n"
        "    for path, expected in _HASHES.items():\n"
        "        target = destination / path\n"
        "        if hashlib.sha256(target.read_bytes()).hexdigest() == expected:\n"
        "            continue\n"
        "        historical = base64.b64decode(_BLOBS[path])\n"
        "        assert hashlib.sha256(historical).hexdigest() == expected\n"
        "        target.write_bytes(historical)\n",
        encoding="utf-8",
    )
    violations = find_source_reconstruction_functions(tmp_path)
    assert len(violations) == 1
    assert violations[0]["function"] == "_restore_historical_tree"


def test_detector_ignores_verbatim_fixture_copy_with_unrelated_json_rehash(tmp_path):
    """A fixture builder that copies real current .py files verbatim (no byte
    manipulation) and separately rehashes unrelated JSON evidence is not the
    anti-pattern; it must not be flagged.
    """
    ok_file = tmp_path / "ok_fixture.py"
    ok_file.write_text(
        "import hashlib\n"
        "import json\n"
        "import shutil\n"
        "\n"
        "def build_fixture(tmp_path):\n"
        "    for relpath in ('quantbot/mod.py', 'tests/test_mod.py'):\n"
        "        target = tmp_path / relpath\n"
        "        shutil.copy2(ROOT / relpath, target)\n"
        "    receipt_path = tmp_path / 'receipt.json'\n"
        "    receipt = json.loads(receipt_path.read_bytes())\n"
        "    for item in receipt['evidence']:\n"
        "        p = tmp_path / item['path']\n"
        "        item['sha256'] = hashlib.sha256(p.read_bytes()).hexdigest()\n"
        "    receipt_path.write_bytes(json.dumps(receipt).encode())\n",
        encoding="utf-8",
    )
    assert find_source_reconstruction_functions(tmp_path) == []
