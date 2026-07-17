"""Synthetic tests for the portable artifact manifest v1.

Generated fixture bytes only: no real data, no Candidate 1 bytes, no
configured stores. Temporary directories are test workspaces, never
canonical stores or artifact locations.
"""

import ast
import copy
import hashlib
import json
import os
from pathlib import Path

import pytest

from quantbot.artifacts.manifest import (
    ArtifactManifestError,
    build_portable_manifest,
    canonical_json_bytes,
    portable_manifest_sha256,
    validate_manifest_bytes,
    validate_manifest_object,
)
from quantbot.experiment.offline_edge_input_manifest import (
    compute_input_manifest_fingerprint,
    discover_input_files,
)

ROOT = Path(__file__).parents[2]

SPEC = {
    "bars": {"btc/1h/part-000.csv": b"synthetic,bars,1\n", "btc/1h/part-001.csv": b"synthetic,bars,2\n"},
    "funding": {"btc/funding.csv": b"synthetic,funding\n"},
}


def make_role_trees(base: Path, spec=None) -> dict:
    spec = SPEC if spec is None else spec
    roots = {}
    for role, files in spec.items():
        role_root = base / f"{role}-root"
        for relative, data in files.items():
            target = role_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        roots[role] = role_root
    return roots


def build(base: Path, spec=None) -> tuple[dict, str]:
    manifest = build_portable_manifest("synthetic-artifact-v0", make_role_trees(base, spec))
    return manifest, portable_manifest_sha256(manifest)


def test_same_bytes_under_different_roots_same_manifest_sha(tmp_path):
    _, sha_a = build(tmp_path / "root-a")
    _, sha_b = build(tmp_path / "deeply" / "nested" / "other-root-b")
    assert sha_a == sha_b


def test_legacy_fingerprint_is_path_sensitive_unlike_portable_identity(tmp_path):
    roots_a = make_role_trees(tmp_path / "root-a")
    roots_b = make_role_trees(tmp_path / "root-b")
    portable_a = portable_manifest_sha256(build_portable_manifest("synthetic-artifact-v0", roots_a))
    portable_b = portable_manifest_sha256(build_portable_manifest("synthetic-artifact-v0", roots_b))
    assert portable_a == portable_b
    legacy_a = compute_input_manifest_fingerprint(discover_input_files(sorted(roots_a.values())))
    legacy_b = compute_input_manifest_fingerprint(discover_input_files(sorted(roots_b.values())))
    assert legacy_a != legacy_b


def test_different_bytes_different_manifest_sha(tmp_path):
    _, sha_a = build(tmp_path / "a")
    changed = {**SPEC, "funding": {"btc/funding.csv": b"synthetic,funding,CHANGED\n"}}
    _, sha_b = build(tmp_path / "b", changed)
    assert sha_a != sha_b


def test_different_role_different_manifest_sha(tmp_path):
    _, sha_a = build(tmp_path / "a")
    renamed = {"bars": SPEC["bars"], "funding_alt": SPEC["funding"]}
    _, sha_b = build(tmp_path / "b", renamed)
    assert sha_a != sha_b


def test_different_relative_path_different_manifest_sha(tmp_path):
    _, sha_a = build(tmp_path / "a")
    moved = {**SPEC, "funding": {"btc/funding-moved.csv": b"synthetic,funding\n"}}
    _, sha_b = build(tmp_path / "b", moved)
    assert sha_a != sha_b


def test_file_creation_order_does_not_affect_manifest_sha(tmp_path):
    roots_a = make_role_trees(tmp_path / "a")
    reversed_spec = {
        role: dict(reversed(list(files.items()))) for role, files in reversed(list(SPEC.items()))
    }
    roots_b = make_role_trees(tmp_path / "b", reversed_spec)
    sha_a = portable_manifest_sha256(build_portable_manifest("synthetic-artifact-v0", roots_a))
    sha_b = portable_manifest_sha256(build_portable_manifest("synthetic-artifact-v0", roots_b))
    assert sha_a == sha_b


def test_absolute_paths_never_appear_in_manifest_bytes(tmp_path):
    manifest, _ = build(tmp_path)
    data = canonical_json_bytes(manifest)
    assert str(tmp_path).encode() not in data
    assert b"root-a" not in data and b"tmp" not in data
    for entry in manifest["files"]:
        assert not entry["relative_path"].startswith("/")


def test_canonical_bytes_are_deterministic(tmp_path):
    manifest, _ = build(tmp_path)
    data_a = canonical_json_bytes(manifest)
    data_b = canonical_json_bytes(json.loads(data_a.decode("utf-8")))
    assert data_a == data_b
    assert not data_a.endswith(b"\n")
    parsed, sha = validate_manifest_bytes(data_a)
    assert sha == hashlib.sha256(data_a).hexdigest() == portable_manifest_sha256(parsed)


def test_trailing_newline_rejected(tmp_path):
    manifest, _ = build(tmp_path)
    with pytest.raises(ArtifactManifestError, match="newline"):
        validate_manifest_bytes(canonical_json_bytes(manifest) + b"\n")


def test_noncanonical_bytes_rejected(tmp_path):
    manifest, _ = build(tmp_path)
    pretty = json.dumps(manifest, indent=2).encode("utf-8")
    with pytest.raises(ArtifactManifestError, match="canonical"):
        validate_manifest_bytes(pretty)


def test_unknown_keys_rejected(tmp_path):
    manifest, _ = build(tmp_path)
    unknown_top = {**manifest, "extra_key": 1}
    with pytest.raises(ArtifactManifestError, match="keys mismatch"):
        validate_manifest_object(unknown_top)
    bad_entry = copy.deepcopy(manifest)
    bad_entry["files"][0]["source_root"] = "/leak"
    with pytest.raises(ArtifactManifestError, match="exactly"):
        validate_manifest_object(bad_entry)


@pytest.mark.parametrize("mutation", [
    lambda m: m.update(file_count=True),
    lambda m: m.update(total_size_bytes=True),
    lambda m: m["files"][0].update(size_bytes=True),
    lambda m: m["files"][0].update(size_bytes="17"),
    lambda m: m["files"][0].update(size_bytes=-1),
])
def test_bool_or_malformed_int_rejected(tmp_path, mutation):
    manifest, _ = build(tmp_path)
    mutated = copy.deepcopy(manifest)
    mutation(mutated)
    with pytest.raises(ArtifactManifestError):
        validate_manifest_object(mutated)


@pytest.mark.parametrize("bad_sha", ["Z" * 64, "abc", ("a" * 63) + "G", ("a" * 64).upper()])
def test_uppercase_or_malformed_sha_rejected(tmp_path, bad_sha):
    manifest, _ = build(tmp_path)
    mutated = copy.deepcopy(manifest)
    mutated["files"][0]["sha256"] = bad_sha
    with pytest.raises(ArtifactManifestError, match="sha256"):
        validate_manifest_object(mutated)


@pytest.mark.parametrize("mutation", [
    lambda m: m.update(schema_version="9.9.9"),
    lambda m: m.update(artifact_manifest_kind="wrong_kind"),
    lambda m: m.update(artifact_id="Bad Artifact ID"),
    lambda m: m.update(files=[]),
    lambda m: m.update(file_count=99),
    lambda m: m.update(total_size_bytes=99999),
    lambda m: m["files"][0].update(role="Bars"),
    lambda m: m["files"][0].update(role=""),
])
def test_schema_drift_rejected(tmp_path, mutation):
    manifest, _ = build(tmp_path)
    mutated = copy.deepcopy(manifest)
    mutation(mutated)
    with pytest.raises(ArtifactManifestError):
        validate_manifest_object(mutated)


def test_unsorted_or_duplicate_file_entries_rejected(tmp_path):
    manifest, _ = build(tmp_path)
    reordered = copy.deepcopy(manifest)
    reordered["files"] = list(reversed(reordered["files"]))
    with pytest.raises(ArtifactManifestError, match="ordered"):
        validate_manifest_object(reordered)
    duplicated = copy.deepcopy(manifest)
    duplicated["files"] = [duplicated["files"][0], duplicated["files"][0]] + duplicated["files"][1:]
    duplicated["file_count"] = len(duplicated["files"])
    duplicated["total_size_bytes"] = sum(e["size_bytes"] for e in duplicated["files"])
    with pytest.raises(ArtifactManifestError, match="ordered"):
        validate_manifest_object(duplicated)


def test_case_collision_rejected(tmp_path):
    manifest, _ = build(tmp_path)
    collided = copy.deepcopy(manifest)
    upper = dict(collided["files"][0])
    upper["relative_path"] = upper["relative_path"].upper()
    collided["files"] = sorted([upper, *collided["files"]], key=lambda e: (e["role"], e["relative_path"]))
    collided["file_count"] = len(collided["files"])
    collided["total_size_bytes"] = sum(e["size_bytes"] for e in collided["files"])
    with pytest.raises(ArtifactManifestError, match="case"):
        validate_manifest_object(collided)


@pytest.mark.parametrize("bad_path", [
    "/absolute/path.csv",
    "",
    ".",
    "..",
    "../escape.csv",
    "nested/../escape.csv",
    "nested/./file.csv",
    "trailing/",
    "back\\slash.csv",
    "nul\x00byte.csv",
])
def test_bad_relative_paths_rejected(tmp_path, bad_path):
    manifest, _ = build(tmp_path)
    mutated = copy.deepcopy(manifest)
    mutated["files"][0]["relative_path"] = bad_path
    mutated["files"].sort(key=lambda e: (e["role"], str(e["relative_path"])))
    with pytest.raises(ArtifactManifestError):
        validate_manifest_object(mutated)


def test_symlink_in_role_root_rejected(tmp_path):
    roots = make_role_trees(tmp_path)
    (roots["bars"] / "btc" / "link.csv").symlink_to(roots["bars"] / "btc" / "1h" / "part-000.csv")
    with pytest.raises(ArtifactManifestError, match="symlink"):
        build_portable_manifest("synthetic-artifact-v0", roots)


def test_symlinked_directory_rejected(tmp_path):
    roots = make_role_trees(tmp_path)
    (roots["bars"] / "linkdir").symlink_to(roots["funding"])
    with pytest.raises(ArtifactManifestError, match="symlink"):
        build_portable_manifest("synthetic-artifact-v0", roots)


def test_symlinked_role_root_rejected(tmp_path):
    roots = make_role_trees(tmp_path)
    link = tmp_path / "bars-link"
    link.symlink_to(roots["bars"])
    roots["bars"] = link
    with pytest.raises(ArtifactManifestError, match="symlink"):
        build_portable_manifest("synthetic-artifact-v0", roots)


def test_fifo_special_file_rejected(tmp_path):
    roots = make_role_trees(tmp_path)
    os.mkfifo(roots["funding"] / "btc" / "pipe.fifo")
    with pytest.raises(ArtifactManifestError, match="special"):
        build_portable_manifest("synthetic-artifact-v0", roots)


def test_missing_and_empty_role_roots_rejected(tmp_path):
    with pytest.raises(ArtifactManifestError, match="does not exist"):
        build_portable_manifest("synthetic-artifact-v0", {"bars": tmp_path / "missing"})
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ArtifactManifestError, match="no files"):
        build_portable_manifest("synthetic-artifact-v0", {"bars": empty})
    with pytest.raises(ArtifactManifestError, match="role_roots"):
        build_portable_manifest("synthetic-artifact-v0", {})


def test_roles_are_explicit_never_inferred(tmp_path):
    roots = make_role_trees(tmp_path)
    manifest = build_portable_manifest("synthetic-artifact-v0", roots)
    assert {entry["role"] for entry in manifest["files"]} == {"bars", "funding"}
    with pytest.raises(ArtifactManifestError, match="role"):
        build_portable_manifest("synthetic-artifact-v0", {"Bars": roots["bars"]})


def test_manifesting_does_not_mutate_sources_or_inputs(tmp_path):
    roots = make_role_trees(tmp_path)
    before = {
        role: {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}
        for role, root in roots.items()
    }
    roots_snapshot = dict(roots)
    manifest = build_portable_manifest("synthetic-artifact-v0", roots)
    manifest_snapshot = copy.deepcopy(manifest)
    portable_manifest_sha256(manifest)
    validate_manifest_object(manifest)
    assert manifest == manifest_snapshot
    assert roots == roots_snapshot
    after = {
        role: {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}
        for role, root in roots.items()
    }
    assert before == after


def test_manifest_module_is_stdlib_only():
    allowed = {"__future__", "hashlib", "json", "os", "re", "stat", "pathlib"}
    tree = ast.parse((ROOT / "quantbot/artifacts/manifest.py").read_text(encoding="utf-8"))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0 and node.module is not None
            modules.add(node.module)
    assert modules == allowed
