"""Synthetic tests for the content-addressed filesystem artifact store v1.

Generated fixture bytes only. Temporary directories are ephemeral test
workspaces (``canonical=False``); they are never canonical stores, never
durable copies, and never recorded as artifact locations.
"""

import ast
import copy
import hashlib
import os
from pathlib import Path

import pytest

from quantbot.artifacts.manifest import (
    build_portable_manifest,
    canonical_json_bytes,
    portable_manifest_sha256,
)
from quantbot.artifacts.store import (
    ArtifactStoreError,
    FilesystemStore,
    require_allowed_canonical_root,
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
        role_root = base / role
        for relative, data in files.items():
            target = role_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        roots[role] = role_root
    return roots


def make_store(tmp_path: Path) -> tuple[FilesystemStore, dict, bytes, str]:
    roots = make_role_trees(tmp_path / "sources")
    manifest = build_portable_manifest("synthetic-artifact-v0", roots)
    manifest_bytes = canonical_json_bytes(manifest)
    manifest_sha = portable_manifest_sha256(manifest)
    store = FilesystemStore(tmp_path / "store", canonical=False)
    return store, roots, manifest_bytes, manifest_sha


@pytest.mark.parametrize("prohibited", ["/tmp", "/tmp/qnty-store", "/srv/qnty", "/srv/qnty/artifacts"])
def test_tmp_and_srv_qnty_canonical_store_rejected(prohibited):
    with pytest.raises(ArtifactStoreError, match="prohibited"):
        require_allowed_canonical_root(Path(prohibited))
    with pytest.raises(ArtifactStoreError, match="prohibited"):
        FilesystemStore(Path(prohibited))


def test_workspace_store_must_be_declared_explicitly(tmp_path):
    with pytest.raises(ArtifactStoreError, match="prohibited"):
        FilesystemStore(tmp_path)
    store = FilesystemStore(tmp_path, canonical=False)
    assert store.canonical is False


def test_atomic_ingest_and_verify_copy_pass(tmp_path):
    store, roots, manifest_bytes, manifest_sha = make_store(tmp_path)
    report = store.ingest(manifest_bytes, roots)
    assert report == {
        "already_present": 0,
        "ingested": 3,
        "manifest_sha256": manifest_sha,
        "object_count": 3,
    }
    verify = store.verify_copy(manifest_sha)
    assert verify["verified_object_count"] == 3
    assert verify["manifest_sha256"] == manifest_sha


def test_idempotent_exact_reingest_passes(tmp_path):
    store, roots, manifest_bytes, manifest_sha = make_store(tmp_path)
    store.ingest(manifest_bytes, roots)
    report = store.ingest(manifest_bytes, roots)
    assert report["ingested"] == 0
    assert report["already_present"] == 3
    store.verify_copy(manifest_sha)


def test_mismatched_existing_object_rejects_and_is_not_overwritten(tmp_path):
    store, roots, manifest_bytes, _ = make_store(tmp_path)
    entry_sha = hashlib.sha256(b"synthetic,bars,1\n").hexdigest()
    poisoned = store.object_path(entry_sha)
    poisoned.parent.mkdir(parents=True)
    poisoned.write_bytes(b"attacker bytes")
    with pytest.raises(ArtifactStoreError, match="mismatched"):
        store.ingest(manifest_bytes, roots)
    assert poisoned.read_bytes() == b"attacker bytes"


@pytest.mark.parametrize("corruption", [
    lambda data: data[:-1],
    lambda data: b"X" + data[1:],
    lambda data: data + b"extra",
])
def test_truncated_or_corrupted_object_rejects(tmp_path, corruption):
    store, roots, manifest_bytes, manifest_sha = make_store(tmp_path)
    store.ingest(manifest_bytes, roots)
    victim = store.object_path(hashlib.sha256(b"synthetic,funding\n").hexdigest())
    victim.write_bytes(corruption(victim.read_bytes()))
    with pytest.raises(ArtifactStoreError):
        store.verify_copy(manifest_sha)


def test_missing_object_rejects(tmp_path):
    store, roots, manifest_bytes, manifest_sha = make_store(tmp_path)
    store.ingest(manifest_bytes, roots)
    store.object_path(hashlib.sha256(b"synthetic,funding\n").hexdigest()).unlink()
    with pytest.raises(ArtifactStoreError, match="missing"):
        store.verify_copy(manifest_sha)


def test_manifest_corruption_rejects(tmp_path):
    store, roots, manifest_bytes, manifest_sha = make_store(tmp_path)
    store.ingest(manifest_bytes, roots)
    manifest_path = store.manifest_path(manifest_sha)
    manifest_path.write_bytes(manifest_bytes.replace(b"synthetic-artifact-v0", b"synthetic-artifact-v1"))
    with pytest.raises(ArtifactStoreError, match="corrupt"):
        store.verify_copy(manifest_sha)
    with pytest.raises(ArtifactStoreError, match="corrupt"):
        store.load_manifest(manifest_sha)


def test_partial_temp_write_cannot_appear_as_complete(tmp_path):
    store, roots, manifest_bytes, manifest_sha = make_store(tmp_path)
    store.ingest(manifest_bytes, roots)
    entry_sha = hashlib.sha256(b"synthetic,bars,1\n").hexdigest()
    object_dir = store.object_path(entry_sha).parent
    (object_dir / ".qnty-tmp-partial").write_bytes(b"partial")
    store.verify_copy(manifest_sha)
    store.object_path(entry_sha).unlink()
    with pytest.raises(ArtifactStoreError, match="missing"):
        store.verify_copy(manifest_sha)


def test_symlinked_object_rejects(tmp_path):
    store, roots, manifest_bytes, manifest_sha = make_store(tmp_path)
    store.ingest(manifest_bytes, roots)
    entry_sha = hashlib.sha256(b"synthetic,bars,1\n").hexdigest()
    object_path = store.object_path(entry_sha)
    real = object_path.with_name("real-bytes")
    object_path.rename(real)
    object_path.symlink_to(real)
    with pytest.raises(ArtifactStoreError, match="symlink"):
        store.verify_copy(manifest_sha)


def test_symlinked_source_rejects_on_ingest(tmp_path):
    store, roots, manifest_bytes, _ = make_store(tmp_path)
    target = roots["funding"] / "btc" / "funding.csv"
    real = roots["funding"] / "btc" / "real.bytes"
    target.rename(real)
    target.symlink_to(real)
    with pytest.raises(ArtifactStoreError, match="symlink"):
        store.ingest(manifest_bytes, roots)
    assert not store.manifest_path(hashlib.sha256(manifest_bytes).hexdigest()).exists()


def test_ingest_requires_explicit_roles_and_verifies_before_success(tmp_path):
    store, roots, manifest_bytes, manifest_sha = make_store(tmp_path)
    with pytest.raises(ArtifactStoreError, match="role roots"):
        store.ingest(manifest_bytes, {"bars": roots["bars"]})
    (roots["funding"] / "btc" / "funding.csv").write_bytes(b"drifted bytes after manifest\n")
    with pytest.raises(ArtifactStoreError):
        store.ingest(manifest_bytes, roots)
    assert not store.manifest_path(manifest_sha).exists()


def test_restore_roundtrip_matches_original_manifest(tmp_path):
    store, roots, manifest_bytes, manifest_sha = make_store(tmp_path)
    store.ingest(manifest_bytes, roots)
    destination = tmp_path / "restored"
    report = store.restore(manifest_sha, destination)
    assert report["restored_file_count"] == 3
    rebuilt = build_portable_manifest(
        "synthetic-artifact-v0", {role: destination / role for role in ("bars", "funding")}
    )
    assert portable_manifest_sha256(rebuilt) == manifest_sha
    assert (destination / "funding" / "btc" / "funding.csv").read_bytes() == b"synthetic,funding\n"


def test_restore_to_existing_destination_rejects(tmp_path):
    store, roots, manifest_bytes, manifest_sha = make_store(tmp_path)
    store.ingest(manifest_bytes, roots)
    destination = tmp_path / "occupied"
    destination.mkdir()
    with pytest.raises(ArtifactStoreError, match="already exists"):
        store.restore(manifest_sha, destination)


def test_source_may_be_deleted_before_restore(tmp_path):
    import shutil

    store, roots, manifest_bytes, manifest_sha = make_store(tmp_path)
    store.ingest(manifest_bytes, roots)
    shutil.rmtree(tmp_path / "sources")
    destination = tmp_path / "restored"
    store.restore(manifest_sha, destination)
    rebuilt = build_portable_manifest(
        "synthetic-artifact-v0", {role: destination / role for role in ("bars", "funding")}
    )
    assert portable_manifest_sha256(rebuilt) == manifest_sha


def test_corruption_detected_during_restore_leaves_no_destination(tmp_path):
    store, roots, manifest_bytes, manifest_sha = make_store(tmp_path)
    store.ingest(manifest_bytes, roots)
    victim = store.object_path(hashlib.sha256(b"synthetic,funding\n").hexdigest())
    victim.write_bytes(b"corrupted object bytes")
    destination = tmp_path / "restored"
    with pytest.raises(ArtifactStoreError):
        store.restore(manifest_sha, destination)
    assert not destination.exists()
    assert not (tmp_path / f".{destination.name}.qnty-restore-tmp").exists()


def test_operations_do_not_mutate_sources_or_caller_structures(tmp_path):
    store, roots, manifest_bytes, manifest_sha = make_store(tmp_path)
    snapshot = {
        role: {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}
        for role, root in roots.items()
    }
    roots_snapshot = dict(roots)
    manifest_bytes_snapshot = bytes(manifest_bytes)
    store.ingest(manifest_bytes, roots)
    store.verify_copy(manifest_sha)
    store.restore(manifest_sha, tmp_path / "restored")
    assert roots == roots_snapshot
    assert manifest_bytes == manifest_bytes_snapshot
    after = {
        role: {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}
        for role, root in roots.items()
    }
    assert snapshot == after


def test_cli_manifest_ingest_verify_restore_roundtrip(tmp_path, capsys):
    from quantbot.artifacts.__main__ import main

    roots = make_role_trees(tmp_path / "sources")
    manifest_path = tmp_path / "manifest.json"
    role_args = []
    for role, root in sorted(roots.items()):
        role_args.extend(["--role", f"{role}={root}"])
    assert main([
        "manifest", "--artifact-id", "synthetic-artifact-v0", *role_args, "--out", str(manifest_path),
    ]) == 0
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    store_root = str(tmp_path / "store")
    assert main([
        "ingest", "--manifest", str(manifest_path), *role_args,
        "--store-root", store_root, "--workspace-store",
    ]) == 0
    assert main([
        "verify-copy", "--manifest-sha", manifest_sha, "--store-root", store_root, "--workspace-store",
    ]) == 0
    assert main([
        "restore", "--manifest-sha", manifest_sha, "--store-root", store_root,
        "--dest", str(tmp_path / "restored"), "--workspace-store",
    ]) == 0
    out = capsys.readouterr().out
    assert f"ARTIFACTS_MANIFEST_OK artifact_id=synthetic-artifact-v0 manifest_sha256={manifest_sha}" in out
    assert "ARTIFACTS_INGEST_OK" in out and "canonical=false" in out
    assert "ARTIFACTS_VERIFY_COPY_OK" in out
    assert "ARTIFACTS_RESTORE_OK" in out


def test_cli_rejects_tmp_store_without_workspace_declaration(tmp_path, capsys):
    from quantbot.artifacts.__main__ import main

    roots = make_role_trees(tmp_path / "sources")
    manifest_path = tmp_path / "manifest.json"
    role_args = []
    for role, root in sorted(roots.items()):
        role_args.extend(["--role", f"{role}={root}"])
    assert main([
        "manifest", "--artifact-id", "synthetic-artifact-v0", *role_args, "--out", str(manifest_path),
    ]) == 0
    assert main([
        "ingest", "--manifest", str(manifest_path), *role_args, "--store-root", str(tmp_path / "store"),
    ]) == 1
    assert "prohibited" in capsys.readouterr().err


def test_store_module_is_stdlib_only():
    allowed = {
        "__future__", "hashlib", "os", "shutil", "stat", "tempfile", "pathlib",
        "quantbot.artifacts.manifest",
    }
    tree = ast.parse((ROOT / "quantbot/artifacts/store.py").read_text(encoding="utf-8"))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0 and node.module is not None
            modules.add(node.module)
    assert modules == allowed
