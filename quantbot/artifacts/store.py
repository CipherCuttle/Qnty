"""Content-addressed artifact store v1 (pure-stdlib filesystem backend).

Deterministic layout under a store root:

    objects/sha256/<first-two-hex>/<full-file-sha256>
    manifests/sha256/<first-two-hex>/<artifact-manifest-sha256>.json

Fail-closed invariants:

- objects are addressed by file SHA-256, manifests by manifest SHA-256;
- every write goes through a temp file in the final directory followed by
  ``os.replace`` plus fsync, so a partial write can never appear complete;
- ingest verifies every byte (hash-while-copy plus independent read-back
  rehash) before reporting success;
- an existing exact object is idempotent, an existing mismatched object
  fails closed and is never overwritten;
- symlinks are never followed;
- a canonical store root must never live under ``/tmp`` or ``/srv/qnty``
  (ephemeral workspace stores for synthetic tests must be declared
  explicitly and are never durable copies).

The backend is intentionally replaceable: this module provides the QNTY
identity and verification layer, not a storage-vendor dependency.
"""

from __future__ import annotations

import ctypes
import errno
import hashlib
import os
import shutil
import stat as stat_module
import tempfile
from pathlib import Path

from quantbot.artifacts.manifest import (
    build_portable_manifest,
    canonical_json_bytes,
    validate_manifest_bytes,
)

__all__ = [
    "PROHIBITED_CANONICAL_STORE_PREFIXES",
    "ArtifactStoreError",
    "FilesystemStore",
    "PinnedStoreRoot",
    "require_allowed_canonical_root",
]

PROHIBITED_CANONICAL_STORE_PREFIXES = ("/tmp", "/srv/qnty")

_CHUNK_SIZE = 65536


class ArtifactStoreError(ValueError):
    """Fail-closed artifact-store violation."""


def _fail(message: str) -> None:
    raise ArtifactStoreError(f"artifact store violation: {message}")


def _is_under(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + "/")


def require_allowed_canonical_root(root: Path) -> Path:
    """Resolve *root* and reject prohibited canonical storage locations."""
    resolved = Path(root).resolve()
    for prefix in PROHIBITED_CANONICAL_STORE_PREFIXES:
        if _is_under(str(resolved), prefix):
            _fail(f"canonical store root {str(resolved)!r} is under prohibited prefix {prefix!r}")
    return resolved


def _hash_store_file(path: Path) -> tuple[str, int]:
    """Independent full read-back hash of a store-owned file (no symlinks)."""
    mode = os.lstat(path).st_mode
    if stat_module.S_ISLNK(mode):
        _fail(f"store entry {path.name!r} is a symlink")
    if not stat_module.S_ISREG(mode):
        _fail(f"store entry {path.name!r} is not a regular file")
    fd = os.open(str(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    digest = hashlib.sha256()
    size = 0
    try:
        while True:
            chunk = os.read(fd, _CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
    finally:
        os.close(fd)
    return digest.hexdigest(), size


def _open_relative_file(root_fd: int, components: tuple[str, ...]) -> int:
    """Open a fixed relative store path beneath an already opened root FD."""
    if not components or any(not component or component in {".", ".."} or "/" in component for component in components):
        _fail("invalid relative store path")
    directory_fd = os.dup(root_fd)
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
    try:
        for component in components[:-1]:
            component_stat = os.lstat(component, dir_fd=directory_fd)
            if stat_module.S_ISLNK(component_stat.st_mode):
                _fail(f"store directory component {component!r} is a symlink")
            if not stat_module.S_ISDIR(component_stat.st_mode):
                _fail(f"store directory component {component!r} is not a directory")
            next_fd = os.open(component, directory_flags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = next_fd
        file_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
        final_stat = os.lstat(components[-1], dir_fd=directory_fd)
        if stat_module.S_ISLNK(final_stat.st_mode):
            _fail(f"store entry {components[-1]!r} is a symlink")
        file_fd = os.open(components[-1], file_flags, dir_fd=directory_fd)
        mode = os.fstat(file_fd).st_mode
        if not stat_module.S_ISREG(mode):
            os.close(file_fd)
            _fail(f"store entry {components[-1]!r} is not a regular file")
        return file_fd
    except OSError as error:
        if error.errno == errno.ENOENT:
            _fail("store entry is missing beneath the pinned root")
        if error.errno == errno.ELOOP:
            _fail("store entry is a symlink beneath the pinned root")
        _fail(f"cannot open store path beneath pinned root: {error}")
    finally:
        os.close(directory_fd)


def _hash_fd(file_fd: int, *, expected_size: int | None = None, expected_sha256: str | None = None) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    while True:
        chunk = os.read(file_fd, _CHUNK_SIZE)
        if not chunk:
            break
        digest.update(chunk)
        size += len(chunk)
    actual_sha256 = digest.hexdigest()
    if expected_size is not None and size != expected_size:
        _fail(f"store file has size {size}, manifest requires {expected_size}")
    if expected_sha256 is not None and actual_sha256 != expected_sha256:
        _fail(f"store file content hash mismatch (expected {expected_sha256})")
    return actual_sha256, size


def _read_fd(file_fd: int) -> bytes:
    chunks = []
    while True:
        chunk = os.read(file_fd, _CHUNK_SIZE)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


class PinnedStoreRoot:
    """Context-managed directory handle and identity for one store root."""

    def __init__(self, configured_path: Path, resolved_path: Path, fd: int, identity: tuple[int, int]):
        self.configured_path = configured_path
        self.resolved_path = resolved_path
        self.fd = fd
        self.identity = identity

    def __enter__(self) -> "PinnedStoreRoot":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        os.close(self.fd)

    def assert_path_still_bound(self) -> None:
        try:
            path_stat = os.lstat(self.configured_path)
            if stat_module.S_ISLNK(path_stat.st_mode):
                _fail("configured store root became a symlink")
            current = os.stat(self.configured_path)
        except OSError as error:
            _fail(f"configured store root is no longer accessible: {error}")
        if not stat_module.S_ISDIR(current.st_mode):
            _fail("configured store root is no longer a directory")
        if (current.st_dev, current.st_ino) != self.identity:
            _fail("configured store root changed during verification")

    def verify_copy(self, manifest_sha256: str) -> dict:
        """Verify a manifest and all objects using only this pinned root FD."""
        manifest_components = ("manifests", "sha256", manifest_sha256[:2], f"{manifest_sha256}.json")
        manifest_fd = _open_relative_file(self.fd, manifest_components)
        try:
            manifest_bytes = _read_fd(manifest_fd)
            actual_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
        finally:
            os.close(manifest_fd)
        if actual_sha256 != manifest_sha256:
            _fail(f"manifest {manifest_sha256} bytes do not match their address (corrupt)")
        manifest, validated_sha = validate_manifest_bytes(manifest_bytes)
        if validated_sha != manifest_sha256:
            _fail(f"manifest {manifest_sha256} failed canonical re-validation")
        for entry in manifest["files"]:
            object_fd = _open_relative_file(
                self.fd, ("objects", "sha256", entry["sha256"][:2], entry["sha256"])
            )
            try:
                _hash_fd(object_fd, expected_size=entry["size_bytes"], expected_sha256=entry["sha256"])
            finally:
                os.close(object_fd)
        self.assert_path_still_bound()
        return {
            "artifact_id": manifest["artifact_id"],
            "manifest_sha256": manifest_sha256,
            "verified_object_count": manifest["file_count"],
        }


def _fsync_directory(directory: Path) -> None:
    fd = os.open(str(directory), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _rename_directory_no_replace(source: Path, destination: Path) -> None:
    """Publish a prepared directory without ever replacing a concurrent entry."""
    try:
        renameat2 = ctypes.CDLL(None, use_errno=True).renameat2
    except AttributeError:
        _fail("atomic no-replace directory publication is unavailable")
    renameat2.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
    renameat2.restype = ctypes.c_int
    result = renameat2(-100, os.fsencode(source), -100, os.fsencode(destination), 1)
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number == errno.EEXIST:
        _fail(f"restore destination {destination.name!r} already exists")
    _fail(f"atomic no-replace directory publication failed: {os.strerror(error_number)}")


def _fsync_tree_bottom_up(root: Path) -> None:
    directories = [Path(directory) for directory, _, _ in os.walk(root)]
    for directory in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        _fsync_directory(directory)


def _install_new_file(temp_name: str, final_path: Path) -> bool:
    """Atomically install a new file without replacing a concurrent writer.

    A hard-link create is atomic within the destination directory.  Unlike
    ``os.replace`` it cannot silently overwrite a complete object installed
    after our preflight check.  Callers re-validate an existing object when it
    returns ``False``.
    """
    try:
        os.link(temp_name, final_path)
    except FileExistsError:
        return False
    os.unlink(temp_name)
    _fsync_directory(final_path.parent)
    return True


class FilesystemStore:
    """One explicitly selected content-addressed store rooted at a directory."""

    def __init__(self, root: Path, *, canonical: bool = True):
        self.canonical = bool(canonical)
        self.configured_root = Path(root)
        if self.canonical:
            self.root = require_allowed_canonical_root(root)
        else:
            self.root = Path(root).resolve()

    def open_pinned_root(self) -> PinnedStoreRoot:
        """Resolve, policy-check, open, and identity-bind the configured root."""
        configured = self.configured_root
        try:
            configured_stat = os.lstat(configured)
        except OSError as error:
            _fail(f"configured store root cannot be opened: {error}")
        if stat_module.S_ISLNK(configured_stat.st_mode):
            _fail("configured store root is a symlink")
        try:
            resolved = Path(configured).resolve(strict=True)
        except OSError as error:
            _fail(f"configured store root cannot be resolved: {error}")
        if self.canonical:
            require_allowed_canonical_root(resolved)
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
        try:
            root_fd = os.open(resolved, flags)
            opened = os.fstat(root_fd)
            expected = os.stat(resolved)
        except OSError as error:
            try:
                os.close(root_fd)
            except (UnboundLocalError, OSError):
                pass
            _fail(f"configured store root cannot be opened safely: {error}")
        if not stat_module.S_ISDIR(opened.st_mode):
            os.close(root_fd)
            _fail("configured store root is not a directory")
        opened_identity = (opened.st_dev, opened.st_ino)
        expected_identity = (expected.st_dev, expected.st_ino)
        if opened_identity != expected_identity or opened_identity != (configured_stat.st_dev, configured_stat.st_ino):
            os.close(root_fd)
            _fail("configured store root path and opened FD identities differ")
        return PinnedStoreRoot(configured, resolved, root_fd, opened_identity)

    # -- layout ---------------------------------------------------------

    def object_path(self, sha256: str) -> Path:
        return self.root / "objects" / "sha256" / sha256[:2] / sha256

    def manifest_path(self, manifest_sha256: str) -> Path:
        return self.root / "manifests" / "sha256" / manifest_sha256[:2] / f"{manifest_sha256}.json"

    # -- atomic write ---------------------------------------------------

    def _write_atomic(self, final_path: Path, source_fd: int, expected_sha256: str, expected_size: int) -> bool:
        final_path.parent.mkdir(parents=True, exist_ok=True)
        temp_fd, temp_name = tempfile.mkstemp(prefix=".qnty-tmp-", dir=str(final_path.parent))
        try:
            digest = hashlib.sha256()
            size = 0
            with os.fdopen(temp_fd, "wb") as temp_file:
                while True:
                    chunk = os.read(source_fd, _CHUNK_SIZE)
                    if not chunk:
                        break
                    digest.update(chunk)
                    size += len(chunk)
                    temp_file.write(chunk)
                temp_file.flush()
                os.fsync(temp_file.fileno())
            if size != expected_size:
                _fail(f"source size {size} does not match manifest size {expected_size}")
            if digest.hexdigest() != expected_sha256:
                _fail("source bytes do not match the manifest sha256; refusing partial/mismatched ingest")
            installed = _install_new_file(temp_name, final_path)
            temp_name = ""
            return installed
        except BaseException:
            try:
                if temp_name:
                    os.unlink(temp_name)
            except OSError:
                pass
            raise

    # -- objects --------------------------------------------------------

    def ingest_object(self, source: Path, expected_sha256: str, expected_size: int) -> str:
        """Ingest one source file; returns 'ingested' or 'already_present'."""
        final_path = self.object_path(expected_sha256)
        if os.path.lexists(final_path):
            existing_sha, existing_size = _hash_store_file(final_path)
            if existing_sha == expected_sha256 and existing_size == expected_size:
                return "already_present"
            _fail(f"existing object {expected_sha256} has mismatched bytes; refusing to overwrite")
        source = Path(source)
        mode = os.lstat(source).st_mode
        if stat_module.S_ISLNK(mode):
            _fail(f"source {source.name!r} is a symlink")
        if not stat_module.S_ISREG(mode):
            _fail(f"source {source.name!r} is not a regular file")
        source_fd = os.open(str(source), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            installed = self._write_atomic(final_path, source_fd, expected_sha256, expected_size)
        finally:
            os.close(source_fd)
        if not installed:
            existing_sha, existing_size = _hash_store_file(final_path)
            if existing_sha == expected_sha256 and existing_size == expected_size:
                return "already_present"
            _fail(f"existing object {expected_sha256} has mismatched bytes; refusing to overwrite")
        readback_sha, readback_size = _hash_store_file(final_path)
        if readback_sha != expected_sha256 or readback_size != expected_size:
            try:
                os.unlink(final_path)
            except OSError:
                pass
            _fail(f"read-back verification failed for object {expected_sha256}")
        return "ingested"

    def verify_object(self, expected_sha256: str, expected_size: int) -> None:
        final_path = self.object_path(expected_sha256)
        if not os.path.lexists(final_path):
            _fail(f"object {expected_sha256} is missing from the store")
        actual_sha, actual_size = _hash_store_file(final_path)
        if actual_size != expected_size:
            _fail(f"object {expected_sha256} has size {actual_size}, manifest requires {expected_size}")
        if actual_sha != expected_sha256:
            _fail(f"object {expected_sha256} content hash mismatch (corrupt or truncated)")

    # -- manifests ------------------------------------------------------

    def put_manifest(self, manifest_bytes: bytes) -> str:
        manifest, manifest_sha = validate_manifest_bytes(manifest_bytes)
        final_path = self.manifest_path(manifest_sha)
        if os.path.lexists(final_path):
            mode = os.lstat(final_path).st_mode
            if not stat_module.S_ISREG(mode):
                _fail(f"existing manifest entry {manifest_sha} is not a regular file")
            if final_path.read_bytes() == manifest_bytes:
                return manifest_sha
            _fail(f"existing manifest {manifest_sha} has mismatched bytes; refusing to overwrite")
        final_path.parent.mkdir(parents=True, exist_ok=True)
        temp_fd, temp_name = tempfile.mkstemp(prefix=".qnty-tmp-", dir=str(final_path.parent))
        try:
            with os.fdopen(temp_fd, "wb") as temp_file:
                temp_file.write(manifest_bytes)
                temp_file.flush()
                os.fsync(temp_file.fileno())
            installed = _install_new_file(temp_name, final_path)
            temp_name = ""
        except BaseException:
            try:
                if temp_name:
                    os.unlink(temp_name)
            except OSError:
                pass
            raise
        if not installed:
            if final_path.read_bytes() == manifest_bytes:
                return manifest_sha
            _fail(f"existing manifest {manifest_sha} has mismatched bytes; refusing to overwrite")
        if final_path.read_bytes() != manifest_bytes:
            _fail(f"read-back verification failed for manifest {manifest_sha}")
        return manifest_sha

    def load_manifest(self, manifest_sha256: str) -> tuple[dict, bytes]:
        final_path = self.manifest_path(manifest_sha256)
        if not os.path.lexists(final_path):
            _fail(f"manifest {manifest_sha256} is missing from the store")
        actual_sha, _ = _hash_store_file(final_path)
        data = final_path.read_bytes()
        if actual_sha != manifest_sha256 or hashlib.sha256(data).hexdigest() != manifest_sha256:
            _fail(f"manifest {manifest_sha256} bytes do not match their address (corrupt)")
        manifest, validated_sha = validate_manifest_bytes(data)
        if validated_sha != manifest_sha256:
            _fail(f"manifest {manifest_sha256} failed canonical re-validation")
        return manifest, data

    # -- high-level operations -------------------------------------------

    def ingest(self, manifest_bytes: bytes, role_roots: dict) -> dict:
        """Ingest a pre-built manifest plus its source files, verifying all bytes.

        The manifest is stored last so a stored manifest always implies its
        objects were fully verified. Sources are never mutated.
        """
        manifest, manifest_sha = validate_manifest_bytes(manifest_bytes)
        manifest_roles = {entry["role"] for entry in manifest["files"]}
        if type(role_roots) is not dict or set(role_roots) != manifest_roles:
            _fail(
                "role roots must be provided explicitly for exactly the manifest roles "
                f"{sorted(manifest_roles)}"
            )
        resolved_roots = {role: os.path.realpath(str(role_roots[role])) for role in role_roots}
        ingested = 0
        already_present = 0
        for entry in manifest["files"]:
            source = Path(role_roots[entry["role"]]) / entry["relative_path"]
            real_source = os.path.realpath(str(source))
            if not _is_under(real_source, resolved_roots[entry["role"]]):
                _fail(f"source {entry['relative_path']!r} escapes its role root")
            result = self.ingest_object(source, entry["sha256"], entry["size_bytes"])
            if result == "ingested":
                ingested += 1
            else:
                already_present += 1
        self.put_manifest(manifest_bytes)
        return {
            "already_present": already_present,
            "ingested": ingested,
            "manifest_sha256": manifest_sha,
            "object_count": len(manifest["files"]),
        }

    def verify_copy(self, manifest_sha256: str) -> dict:
        """Rehash the complete manifest and every referenced object (full bytes)."""
        with self.open_pinned_root() as pinned_root:
            return pinned_root.verify_copy(manifest_sha256)

    def restore(self, manifest_sha256: str, destination: Path) -> dict:
        """Restore into a fresh destination; roles become top-level directories.

        Uses a temporary sibling directory plus atomic rename. After
        restoration the portable manifest is recomputed from the restored
        files and must match ``manifest_sha256`` exactly; a failed restore
        leaves no destination behind.
        """
        destination = Path(destination)
        if os.path.lexists(destination):
            _fail(f"restore destination {destination.name!r} already exists")
        parent = destination.parent.resolve()
        destination = parent / destination.name
        if self.canonical:
            require_allowed_canonical_root(destination)
        if not parent.is_dir():
            _fail("restore destination parent directory does not exist")
        workspace = parent / f".{destination.name}.qnty-restore-tmp"
        if os.path.lexists(workspace):
            _fail(f"stale restore workspace {workspace.name!r} exists; refusing to reuse it")
        manifest, _ = self.load_manifest(manifest_sha256)
        try:
            workspace.mkdir()
            for entry in manifest["files"]:
                object_path = self.object_path(entry["sha256"])
                target = workspace / entry["role"] / entry["relative_path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                source_fd = os.open(str(object_path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
                try:
                    if not stat_module.S_ISREG(os.fstat(source_fd).st_mode):
                        _fail(f"store object {entry['sha256']} is not a regular file")
                    target_fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    try:
                        digest = hashlib.sha256()
                        size = 0
                        while True:
                            chunk = os.read(source_fd, _CHUNK_SIZE)
                            if not chunk:
                                break
                            digest.update(chunk)
                            size += len(chunk)
                            os.write(target_fd, chunk)
                        os.fsync(target_fd)
                    finally:
                        os.close(target_fd)
                finally:
                    os.close(source_fd)
                if size != entry["size_bytes"] or digest.hexdigest() != entry["sha256"]:
                    _fail(f"store object {entry['sha256']} changed or is corrupt during restore")
            role_roots = {role: workspace / role for role in {e["role"] for e in manifest["files"]}}
            rebuilt = build_portable_manifest(manifest["artifact_id"], role_roots)
            rebuilt_sha = hashlib.sha256(canonical_json_bytes(rebuilt)).hexdigest()
            if rebuilt_sha != manifest_sha256:
                _fail(
                    "restored portable manifest does not match the requested manifest "
                    f"({rebuilt_sha} != {manifest_sha256})"
                )
            _fsync_tree_bottom_up(workspace)
            _rename_directory_no_replace(workspace, destination)
            _fsync_directory(parent)
        except BaseException:
            shutil.rmtree(workspace, ignore_errors=True)
            raise
        return {
            "artifact_id": manifest["artifact_id"],
            "manifest_sha256": manifest_sha256,
            "restored_file_count": manifest["file_count"],
        }
