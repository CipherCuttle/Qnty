"""CLI for the QNTY durable artifact plane (stdlib only).

Usage:
    python -m quantbot.artifacts manifest --artifact-id ID --role NAME=DIR ... --out FILE
    python -m quantbot.artifacts ingest --manifest FILE --role NAME=DIR ... --store-root DIR
    python -m quantbot.artifacts verify-copy --manifest-sha SHA --store-root DIR
    python -m quantbot.artifacts restore --manifest-sha SHA --store-root DIR --dest DIR
    python -m quantbot.artifacts verify-registry [--root PATH]
    python -m quantbot.artifacts status [--root PATH]

Store-facing commands treat ``--store-root`` as canonical storage and refuse
``/tmp`` and ``/srv/qnty``. ``--workspace-store`` marks the store as an
ephemeral synthetic workspace instead; workspace stores are never durable
copies and never canonical artifact locations.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

from quantbot.artifacts.manifest import (
    build_portable_manifest,
    canonical_json_bytes,
    validate_manifest_bytes,
)
from quantbot.artifacts.registry import validate_operational_registry, validate_registry_tree
from quantbot.artifacts.store import FilesystemStore


def _parse_roles(pairs: list) -> dict:
    roles: dict = {}
    for pair in pairs:
        if "=" not in pair:
            raise ValueError(f"--role expects NAME=DIR, got {pair!r}")
        role, _, root = pair.partition("=")
        if not role or not root:
            raise ValueError(f"--role expects NAME=DIR, got {pair!r}")
        if role in roles:
            raise ValueError(f"--role {role!r} was given more than once")
        roles[role] = Path(root)
    if not roles:
        raise ValueError("at least one --role NAME=DIR is required")
    return roles


def _discover_root(explicit: str | None) -> Path:
    if explicit is not None:
        return Path(explicit)
    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if (candidate / "docs/artifacts").is_dir():
            return candidate
    raise ValueError(f"docs/artifacts not found from {current}; pass --root")


def _store(args: argparse.Namespace) -> FilesystemStore:
    return FilesystemStore(Path(args.store_root), canonical=not args.workspace_store)


def _cmd_manifest(args: argparse.Namespace) -> int:
    manifest = build_portable_manifest(args.artifact_id, _parse_roles(args.role))
    data = canonical_json_bytes(manifest)
    sha = hashlib.sha256(data).hexdigest()
    out = Path(args.out)
    if out.exists():
        raise ValueError(f"manifest output {args.out!r} already exists; refusing to overwrite")
    out.write_bytes(data)
    print(f"ARTIFACTS_MANIFEST_OK artifact_id={manifest['artifact_id']} manifest_sha256={sha} "
          f"file_count={manifest['file_count']} total_size_bytes={manifest['total_size_bytes']}")
    return 0


def _cmd_ingest(args: argparse.Namespace) -> int:
    manifest_bytes = Path(args.manifest).read_bytes()
    report = _store(args).ingest(manifest_bytes, _parse_roles(args.role))
    print(f"ARTIFACTS_INGEST_OK manifest_sha256={report['manifest_sha256']} "
          f"objects={report['object_count']} ingested={report['ingested']} "
          f"already_present={report['already_present']} canonical={str(not args.workspace_store).lower()}")
    return 0


def _cmd_verify_copy(args: argparse.Namespace) -> int:
    report = _store(args).verify_copy(args.manifest_sha)
    print(f"ARTIFACTS_VERIFY_COPY_OK artifact_id={report['artifact_id']} "
          f"manifest_sha256={report['manifest_sha256']} "
          f"verified_object_count={report['verified_object_count']}")
    return 0


def _cmd_restore(args: argparse.Namespace) -> int:
    report = _store(args).restore(args.manifest_sha, Path(args.dest))
    print(f"ARTIFACTS_RESTORE_OK artifact_id={report['artifact_id']} "
          f"manifest_sha256={report['manifest_sha256']} "
          f"restored_file_count={report['restored_file_count']}")
    return 0


def _cmd_verify_registry(args: argparse.Namespace) -> int:
    result = validate_registry_tree(_discover_root(args.root))
    validate_operational_registry(_discover_root(args.root), registry_tree=result)
    store_count = len(result["store_registry"]["stores"])
    print(f"ARTIFACTS_REGISTRY_OK records={len(result['records'])} stores={store_count}")
    for artifact_id in sorted(result["records"]):
        entry = result["records"][artifact_id]
        print(f"ARTIFACT_RECORD id={artifact_id} sha256={entry['sha256']}")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    result = validate_registry_tree(_discover_root(args.root))
    validate_operational_registry(_discover_root(args.root), registry_tree=result)
    print("QNTY_ARTIFACT_STATUS schema=1.0.0")
    stores = result["store_registry"]["stores"]
    if not stores:
        print("STORES=UNCONFIGURED count=0")
    else:
        print(f"STORES=CONFIGURED count={len(stores)}")
        for store in sorted(stores, key=lambda s: s["store_id"]):
            print(
                f"STORE id={store['store_id']} backend={store['backend_kind']} "
                f"failure_domain={store['failure_domain']} "
                f"read={str(store['read_enabled']).lower()} write={str(store['write_enabled']).lower()}"
            )
    for artifact_id in sorted(result["records"]):
        record = result["records"][artifact_id]["record"]
        portable = record["portable_manifest_sha256"]
        print(
            f"ARTIFACT id={artifact_id} availability={record['availability']} "
            f"copies={len(record['copies'])} "
            f"portable_manifest_sha256={'null' if portable is None else portable} "
            f"legacy_input_manifest_fingerprint={record['legacy_bindings']['legacy_input_manifest_fingerprint']}"
        )
        for copy in sorted(record["copies"], key=lambda c: c["canonical_location"]):
            print(f"COPY location={copy['canonical_location']} failure_domain={copy['failure_domain']}")
    return 0


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m quantbot.artifacts")
    subparsers = parser.add_subparsers(dest="command", required=True)

    manifest_parser = subparsers.add_parser("manifest", help="build a portable manifest from explicit role roots")
    manifest_parser.add_argument("--artifact-id", required=True)
    manifest_parser.add_argument("--role", action="append", required=True, metavar="NAME=DIR")
    manifest_parser.add_argument("--out", required=True)
    manifest_parser.set_defaults(func=_cmd_manifest)

    def add_store_arguments(sub: argparse.ArgumentParser) -> None:
        sub.add_argument("--store-root", required=True)
        sub.add_argument(
            "--workspace-store",
            action="store_true",
            help="ephemeral synthetic workspace store (never canonical, never a durable copy)",
        )

    ingest_parser = subparsers.add_parser("ingest", help="ingest a manifest and its files into one store")
    ingest_parser.add_argument("--manifest", required=True)
    ingest_parser.add_argument("--role", action="append", required=True, metavar="NAME=DIR")
    add_store_arguments(ingest_parser)
    ingest_parser.set_defaults(func=_cmd_ingest)

    verify_copy_parser = subparsers.add_parser("verify-copy", help="rehash a manifest and every referenced object")
    verify_copy_parser.add_argument("--manifest-sha", required=True)
    add_store_arguments(verify_copy_parser)
    verify_copy_parser.set_defaults(func=_cmd_verify_copy)

    restore_parser = subparsers.add_parser("restore", help="restore a manifest into a fresh destination")
    restore_parser.add_argument("--manifest-sha", required=True)
    restore_parser.add_argument("--dest", required=True)
    add_store_arguments(restore_parser)
    restore_parser.set_defaults(func=_cmd_restore)

    verify_registry_parser = subparsers.add_parser("verify-registry", help="validate the Git-owned artifact registry")
    verify_registry_parser.add_argument("--root", default=None)
    verify_registry_parser.set_defaults(func=_cmd_verify_registry)

    status_parser = subparsers.add_parser("status", help="deterministic read-only registry status")
    status_parser.add_argument("--root", default=None)
    status_parser.set_defaults(func=_cmd_status)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, OSError) as error:
        print(f"ARTIFACTS_FAILED: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
