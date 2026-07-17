"""Portable artifact manifest v1 (stdlib only).

The portable manifest is the QNTY scientific content identity of a
role-partitioned file set. Its hash domain contains, per file, exactly
``role``, ``relative_path``, ``size_bytes`` and ``sha256`` -- never a source
root, absolute path, machine name, timestamp, uid, gid, inode, mtime, or
storage location. Identical role trees under two different absolute roots
therefore produce the same portable manifest SHA-256.

This identity is deliberately distinct from the legacy protocol
input-manifest fingerprint (``quantbot.experiment.offline_edge_input_manifest``),
which mixes resolved absolute paths into its hash and is therefore
path-sensitive, historical and immutable -- not a portable content digest.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat as stat_module
from pathlib import Path

__all__ = [
    "ARTIFACT_MANIFEST_KIND",
    "MANIFEST_SCHEMA_VERSION",
    "ArtifactManifestError",
    "build_portable_manifest",
    "canonical_json_bytes",
    "hash_regular_file",
    "portable_manifest_sha256",
    "scan_role_root",
    "validate_manifest_bytes",
    "validate_manifest_object",
]

ARTIFACT_MANIFEST_KIND = "qnty_portable_artifact_manifest"
MANIFEST_SCHEMA_VERSION = "1.0.0"

_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_ROLE_RE = re.compile(r"[a-z][a-z0-9_-]{0,63}")
_ARTIFACT_ID_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}")
_PATH_SEGMENT_RE = re.compile(r"[A-Za-z0-9._-]+")

_MANIFEST_KEYS = {
    "artifact_id",
    "artifact_manifest_kind",
    "file_count",
    "files",
    "schema_version",
    "total_size_bytes",
}
_FILE_KEYS = {"relative_path", "role", "sha256", "size_bytes"}

_CHUNK_SIZE = 65536


class ArtifactManifestError(ValueError):
    """Fail-closed portable-manifest violation."""


def _fail(message: str) -> None:
    raise ArtifactManifestError(f"portable manifest violation: {message}")


def canonical_json_bytes(value: object) -> bytes:
    """Canonical QNTY JSON bytes: UTF-8, sorted keys, compact, ASCII, no newline."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _require_int(value: object, label: str) -> int:
    if type(value) is not int:
        _fail(f"{label} must be an int (bool is not accepted)")
    return value


def _require_sha256(value: object, label: str) -> str:
    if type(value) is not str or not _SHA256_RE.fullmatch(value):
        _fail(f"{label} must be a lowercase hex sha256")
    return value


def _require_role(value: object) -> str:
    if type(value) is not str or not _ROLE_RE.fullmatch(value):
        _fail(f"role {value!r} is not a valid role name")
    return value


def _require_artifact_id(value: object) -> str:
    if type(value) is not str or not _ARTIFACT_ID_RE.fullmatch(value):
        _fail(f"artifact_id {value!r} is not a valid artifact id")
    return value


def _require_relative_path(value: object) -> str:
    if type(value) is not str or not value:
        _fail("relative_path must be a non-empty string")
    if value.startswith("/"):
        _fail(f"relative_path {value!r} is absolute")
    if "\\" in value or "\x00" in value:
        _fail(f"relative_path {value!r} contains a prohibited character")
    if value.endswith("/"):
        _fail(f"relative_path {value!r} ends with a separator")
    for segment in value.split("/"):
        if segment in ("", ".", ".."):
            _fail(f"relative_path {value!r} contains an empty, '.' or '..' segment")
        if not _PATH_SEGMENT_RE.fullmatch(segment):
            _fail(f"relative_path segment {segment!r} is outside the allowed character policy")
    return value


def hash_regular_file(path: Path) -> tuple[str, int]:
    """SHA-256 and byte size of a regular file; symlinks and special files reject."""
    path = Path(path)
    try:
        mode = os.lstat(path).st_mode
    except OSError as error:
        _fail(f"cannot stat source file {path.name!r}: {error.strerror}")
    if stat_module.S_ISLNK(mode):
        _fail(f"source file {path.name!r} is a symlink")
    if not stat_module.S_ISREG(mode):
        _fail(f"source file {path.name!r} is not a regular file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(str(path), flags)
    except OSError as error:
        _fail(f"cannot open source file {path.name!r}: {error.strerror}")
    digest = hashlib.sha256()
    size = 0
    try:
        if not stat_module.S_ISREG(os.fstat(fd).st_mode):
            _fail(f"source file {path.name!r} is not a regular file")
        while True:
            chunk = os.read(fd, _CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
    finally:
        os.close(fd)
    return digest.hexdigest(), size


def scan_role_root(role: str, root: Path) -> list[dict]:
    """Deterministically scan one explicit role root into portable file entries.

    Rejects symlinks (files or directories), special files, and any relative
    path outside the allowed policy. The returned entries carry no trace of
    the absolute root.
    """
    _require_role(role)
    root = Path(root)
    try:
        mode = os.lstat(root).st_mode
    except OSError:
        _fail(f"role root for role {role!r} does not exist")
    if stat_module.S_ISLNK(mode):
        _fail(f"role root for role {role!r} is a symlink")
    if not stat_module.S_ISDIR(mode):
        _fail(f"role root for role {role!r} is not a directory")
    entries: list[dict] = []
    stack = [root]
    while stack:
        directory = stack.pop()
        for child in sorted(directory.iterdir()):
            child_mode = os.lstat(child).st_mode
            if stat_module.S_ISLNK(child_mode):
                _fail(f"symlink {child.name!r} under role {role!r} is prohibited")
            if stat_module.S_ISDIR(child_mode):
                stack.append(child)
                continue
            if not stat_module.S_ISREG(child_mode):
                _fail(f"special file {child.name!r} under role {role!r} is prohibited")
            relative = child.relative_to(root).as_posix()
            _require_relative_path(relative)
            sha256, size_bytes = hash_regular_file(child)
            entries.append(
                {
                    "relative_path": relative,
                    "role": role,
                    "sha256": sha256,
                    "size_bytes": size_bytes,
                }
            )
    if not entries:
        _fail(f"role root for role {role!r} contains no files")
    return entries


def build_portable_manifest(artifact_id: str, role_roots: dict) -> dict:
    """Build the portable manifest v1 from explicit role -> root mappings.

    Roles are never inferred from directory names; every role must be named
    explicitly by the caller. The result is validated before it is returned
    and never mutates the sources.
    """
    _require_artifact_id(artifact_id)
    if type(role_roots) is not dict or not role_roots:
        _fail("role_roots must be a non-empty mapping of role -> directory")
    files: list[dict] = []
    for role in sorted(role_roots):
        files.extend(scan_role_root(role, role_roots[role]))
    files.sort(key=lambda entry: (entry["role"], entry["relative_path"]))
    manifest = {
        "artifact_id": artifact_id,
        "artifact_manifest_kind": ARTIFACT_MANIFEST_KIND,
        "file_count": len(files),
        "files": files,
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "total_size_bytes": sum(entry["size_bytes"] for entry in files),
    }
    return validate_manifest_object(manifest)


def validate_manifest_object(manifest: object) -> dict:
    """Strict fail-closed validation of a parsed portable manifest."""
    if type(manifest) is not dict:
        _fail("manifest must be a JSON object")
    if set(manifest) != _MANIFEST_KEYS:
        missing = sorted(_MANIFEST_KEYS - set(manifest))
        extra = sorted(set(manifest) - _MANIFEST_KEYS)
        _fail(f"manifest keys mismatch (missing={missing} extra={extra})")
    if manifest["artifact_manifest_kind"] != ARTIFACT_MANIFEST_KIND:
        _fail("artifact_manifest_kind is wrong")
    if manifest["schema_version"] != MANIFEST_SCHEMA_VERSION:
        _fail(f"schema_version is not {MANIFEST_SCHEMA_VERSION}")
    _require_artifact_id(manifest["artifact_id"])
    files = manifest["files"]
    if type(files) is not list or not files:
        _fail("files must be a non-empty list")
    previous_key = None
    seen_folded: set = set()
    total_size = 0
    for entry in files:
        if type(entry) is not dict or set(entry) != _FILE_KEYS:
            _fail("file entry must contain exactly role, relative_path, size_bytes, sha256")
        role = _require_role(entry["role"])
        relative_path = _require_relative_path(entry["relative_path"])
        size_bytes = _require_int(entry["size_bytes"], "size_bytes")
        if size_bytes < 0:
            _fail("size_bytes must be >= 0")
        _require_sha256(entry["sha256"], "file sha256")
        key = (role, relative_path)
        if previous_key is not None and key <= previous_key:
            _fail("files must be strictly ordered by (role, relative_path) with no duplicates")
        previous_key = key
        folded = (role, relative_path.casefold())
        if folded in seen_folded:
            _fail(f"file paths collide under case folding for role {role!r}: {relative_path!r}")
        seen_folded.add(folded)
        total_size += size_bytes
    if _require_int(manifest["file_count"], "file_count") != len(files):
        _fail("file_count does not match the number of file entries")
    if _require_int(manifest["total_size_bytes"], "total_size_bytes") != total_size:
        _fail("total_size_bytes does not match the sum of file sizes")
    return manifest


def validate_manifest_bytes(data: bytes) -> tuple[dict, str]:
    """Validate exact canonical manifest bytes; return (manifest, manifest sha256)."""
    if type(data) is not bytes:
        _fail("manifest bytes must be bytes")
    if data.endswith(b"\n"):
        _fail("manifest bytes must not end with a trailing newline")
    try:
        parsed = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        _fail("manifest bytes are not strict UTF-8 JSON")
    validate_manifest_object(parsed)
    if data != canonical_json_bytes(parsed):
        _fail("manifest bytes are not canonical QNTY JSON (sorted keys, compact, ASCII, no trailing newline)")
    return parsed, hashlib.sha256(data).hexdigest()


def portable_manifest_sha256(manifest: dict) -> str:
    """SHA-256 over the exact canonical bytes of a validated portable manifest."""
    validate_manifest_object(manifest)
    return hashlib.sha256(canonical_json_bytes(manifest)).hexdigest()
