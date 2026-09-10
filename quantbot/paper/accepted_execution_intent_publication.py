"""Build and assemble Qnty accepted-intent publication receipts without key custody.

This ADMIN_LANE helper closes the producer side of the publication-authentication
protocol. Qnty derives the exact domain-separated bytes that an external
publication signer must sign, then assembles a canonical receipt from an
externally supplied 64-byte signature.

The module contains no private-key API, signer callback, wallet dependency,
network access, policy evaluation, venue logic, or execution authority.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from quantbot.core.determinism import canonical_json_dumps
from quantbot.paper import ledger
from quantbot.paper.accepted_execution_intent_v2 import (
    QNTY_REPOSITORY,
    SCHEMA_NAME as ACCEPTED_INTENT_SCHEMA_NAME,
    SCHEMA_VERSION as ACCEPTED_INTENT_SCHEMA_VERSION,
    IntentRejected,
    validate_accepted_execution_intent_v2,
)

PUBLICATION_AUTH_CONTRACT_VERSION = "QNTY_ACCEPTED_EXECUTION_INTENT_PUBLICATION_AUTH_V0"
PUBLICATION_PURPOSE = "QNTY_ACCEPTED_INTENT_ORIGIN_AUTHENTICATION_ONLY"
PUBLICATION_ROOT_ID = "qnty-accepted-intent-publication"
PUBLICATION_RECEIPT_SCHEMA = "qntyspot.qnty_publication_auth.v0.receipt"
PUBLICATION_RECEIPT_ID_SCHEMA = "qntyspot.qnty_publication_auth.v0.receipt_id"
ED25519_SIGNATURE_ALGORITHM = "Ed25519"

_SHA256_RE = re.compile(r"\A[0-9a-f]{64}\Z")
_GIT_COMMIT_RE = re.compile(r"\A[0-9a-f]{40}\Z")
_HEX128_RE = re.compile(r"\A[0-9a-f]{128}\Z")
_BODY_FIELDS = {
    "accepted_intent_schema_name",
    "accepted_intent_schema_version",
    "artifact_sha256",
    "intent_digest",
    "publication_epoch",
    "published_at_epoch_s",
    "public_key_fingerprint",
    "purpose",
    "qnty_repository",
    "qnty_repository_commit",
    "root_id",
    "schema",
    "serial",
    "signature_algorithm",
}
_RECEIPT_FIELDS = _BODY_FIELDS | {"receipt_id", "signature"}


class PublicationReceiptRejected(ValueError):
    """Publication body or externally signed receipt failed closed."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return canonical_json_dumps(dict(value)).encode("utf-8")


def _sha256_text(value: Any, where: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise PublicationReceiptRejected(
            "DIGEST_INVALID", f"{where} must be lowercase sha256"
        )
    return value


def _git_commit(value: Any, where: str) -> str:
    if not isinstance(value, str) or not _GIT_COMMIT_RE.fullmatch(value):
        raise PublicationReceiptRejected(
            "COMMIT_INVALID", f"{where} must be a full lowercase git commit"
        )
    return value


def _positive_int(value: Any, where: str) -> int:
    if type(value) is not int or value <= 0:
        raise PublicationReceiptRejected(
            "VALUE_INVALID", f"{where} must be a positive integer"
        )
    return value


def _non_negative_int(value: Any, where: str) -> int:
    if type(value) is not int or value < 0:
        raise PublicationReceiptRejected(
            "VALUE_INVALID", f"{where} must be a non-negative integer"
        )
    return value


def _exact(value: Any, expected: set[str], where: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise PublicationReceiptRejected("SCHEMA_INVALID", f"{where} must be an object")
    result = dict(value)
    actual = set(result)
    if actual != expected:
        raise PublicationReceiptRejected(
            "SCHEMA_FIELDS",
            f"{where} keys differ; missing={sorted(expected - actual)} unknown={sorted(actual - expected)}",
        )
    return result


def _load_exact_intent_bytes(value: Path | str | bytes) -> tuple[dict[str, Any], bytes]:
    if isinstance(value, Path):
        try:
            raw = value.read_bytes()
        except OSError as exc:
            raise PublicationReceiptRejected("INPUT_UNREADABLE", str(exc)) from exc
    elif isinstance(value, bytes):
        raw = value
    elif isinstance(value, str):
        raw = Path(value).read_bytes()
    else:
        raise PublicationReceiptRejected(
            "INPUT_TYPE", "accepted intent must be a filesystem path or bytes"
        )
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PublicationReceiptRejected(
            "INPUT_JSON", f"accepted intent is not strict UTF-8 JSON: {exc}"
        ) from exc
    try:
        intent = validate_accepted_execution_intent_v2(parsed)
    except IntentRejected as exc:
        raise PublicationReceiptRejected(exc.code, exc.detail) from exc
    expected = (canonical_json_dumps(intent) + "\n").encode("utf-8")
    if raw != expected:
        raise PublicationReceiptRejected(
            "NON_CANONICAL_BYTES",
            "accepted intent bytes are not the canonical V2 artifact representation",
        )
    return intent, raw


def validate_publication_body_v0(value: Any) -> dict[str, Any]:
    """Validate a canonical publication body before external signing."""
    body = _exact(value, _BODY_FIELDS, "publication body")
    if body["root_id"] != PUBLICATION_ROOT_ID:
        raise PublicationReceiptRejected("ROOT_MISMATCH", "publication root id is not canonical")
    if body["purpose"] != PUBLICATION_PURPOSE:
        raise PublicationReceiptRejected("PURPOSE_MISMATCH", "publication purpose is not canonical")
    if body["signature_algorithm"] != ED25519_SIGNATURE_ALGORITHM:
        raise PublicationReceiptRejected("ALGORITHM_MISMATCH", "publication algorithm must be Ed25519")
    if body["schema"] != PUBLICATION_RECEIPT_SCHEMA:
        raise PublicationReceiptRejected("SCHEMA_INVALID", "publication receipt schema is not canonical")
    if body["accepted_intent_schema_name"] != ACCEPTED_INTENT_SCHEMA_NAME:
        raise PublicationReceiptRejected("SCHEMA_INVALID", "accepted-intent schema name is not V2")
    if body["accepted_intent_schema_version"] != ACCEPTED_INTENT_SCHEMA_VERSION:
        raise PublicationReceiptRejected("SCHEMA_INVALID", "accepted-intent schema version is not V2")
    if body["qnty_repository"] != QNTY_REPOSITORY:
        raise PublicationReceiptRejected("REPOSITORY_MISMATCH", "Qnty repository identity is not canonical")
    _git_commit(body["qnty_repository_commit"], "qnty_repository_commit")
    _sha256_text(body["intent_digest"], "intent_digest")
    _sha256_text(body["artifact_sha256"], "artifact_sha256")
    _sha256_text(body["public_key_fingerprint"], "public_key_fingerprint")
    _positive_int(body["publication_epoch"], "publication_epoch")
    _positive_int(body["serial"], "serial")
    _non_negative_int(body["published_at_epoch_s"], "published_at_epoch_s")
    return body


def build_publication_body_v0(
    accepted_intent: Path | str | bytes,
    *,
    qnty_repository_commit: str,
    public_key_fingerprint: str,
    publication_epoch: int,
    serial: int,
    published_at_epoch_s: int,
) -> dict[str, Any]:
    """Derive exact bytes for an external publication signer to sign."""
    intent, raw = _load_exact_intent_bytes(accepted_intent)
    body = {
        "accepted_intent_schema_name": ACCEPTED_INTENT_SCHEMA_NAME,
        "accepted_intent_schema_version": ACCEPTED_INTENT_SCHEMA_VERSION,
        "artifact_sha256": hashlib.sha256(raw).hexdigest(),
        "intent_digest": intent["intent_digest"],
        "publication_epoch": publication_epoch,
        "published_at_epoch_s": published_at_epoch_s,
        "public_key_fingerprint": public_key_fingerprint,
        "purpose": PUBLICATION_PURPOSE,
        "qnty_repository": QNTY_REPOSITORY,
        "qnty_repository_commit": qnty_repository_commit,
        "root_id": PUBLICATION_ROOT_ID,
        "schema": PUBLICATION_RECEIPT_SCHEMA,
        "serial": serial,
        "signature_algorithm": ED25519_SIGNATURE_ALGORITHM,
    }
    return validate_publication_body_v0(body)


def publication_body_bytes_v0(body: Mapping[str, Any]) -> bytes:
    """Return the exact canonical bytes that must be signed externally."""
    return _canonical_bytes(validate_publication_body_v0(body))


def _receipt_id(body: Mapping[str, Any], signature: bytes) -> str:
    signed_body_digest = hashlib.sha256(publication_body_bytes_v0(body)).hexdigest()
    signature_digest = hashlib.sha256(signature).hexdigest()
    identity = {
        "public_key_fingerprint": body["public_key_fingerprint"],
        "root_id": body["root_id"],
        "schema": PUBLICATION_RECEIPT_ID_SCHEMA,
        "signature_digest": signature_digest,
        "signed_body_digest": signed_body_digest,
    }
    return hashlib.sha256(_canonical_bytes(identity)).hexdigest()


def assemble_publication_receipt_v0(
    body: Mapping[str, Any], *, signature: bytes
) -> dict[str, Any]:
    """Assemble a receipt from externally supplied Ed25519 signature bytes.

    This function does not and cannot create a signature. Cryptographic
    verification belongs to the downstream QntySpot publication verifier.
    """
    validated_body = validate_publication_body_v0(body)
    if type(signature) is not bytes or len(signature) != 64:
        raise PublicationReceiptRejected(
            "SIGNATURE_INVALID", "external Ed25519 signature must be exactly 64 bytes"
        )
    receipt = dict(validated_body)
    receipt.update(
        {
            "receipt_id": _receipt_id(validated_body, signature),
            "signature": signature.hex(),
        }
    )
    return validate_publication_receipt_v0(receipt)


def validate_publication_receipt_v0(value: Any) -> dict[str, Any]:
    """Validate receipt structure and deterministic receipt identity."""
    receipt = _exact(value, _RECEIPT_FIELDS, "publication receipt")
    body = {key: receipt[key] for key in _BODY_FIELDS}
    validate_publication_body_v0(body)
    signature_hex = receipt["signature"]
    if not isinstance(signature_hex, str) or not _HEX128_RE.fullmatch(signature_hex):
        raise PublicationReceiptRejected(
            "SIGNATURE_INVALID", "receipt signature must be lowercase 64-byte hex"
        )
    signature = bytes.fromhex(signature_hex)
    expected_id = _receipt_id(body, signature)
    if receipt["receipt_id"] != expected_id:
        raise PublicationReceiptRejected("RECEIPT_ID_INVALID", "receipt_id does not recompute")
    _sha256_text(receipt["receipt_id"], "receipt_id")
    return receipt


def publication_receipt_bytes_v0(receipt: Mapping[str, Any]) -> bytes:
    return _canonical_bytes(validate_publication_receipt_v0(receipt))


def write_publication_receipt_v0(
    receipt: Mapping[str, Any], receipt_path: Path, sidecar_path: Path
) -> None:
    """Persist canonical receipt bytes and file-SHA sidecar, write-once.

    A deterministic exclusive lock serializes writers for the receipt path.
    Existing partial or conflicting output always fails closed rather than being
    repaired or overwritten.
    """
    receipt_path = Path(receipt_path)
    sidecar_path = Path(sidecar_path)
    if receipt_path.resolve(strict=False) == sidecar_path.resolve(strict=False):
        raise PublicationReceiptRejected(
            "OUTPUT_PATH_ALIAS", "receipt and sidecar paths must be distinct"
        )

    data = publication_receipt_bytes_v0(receipt)
    file_sha = hashlib.sha256(data).hexdigest()
    sidecar = (file_sha + "\n").encode("ascii")
    lock_path = receipt_path.with_name(receipt_path.name + ".publication.lock")
    if lock_path.resolve(strict=False) == sidecar_path.resolve(strict=False):
        raise PublicationReceiptRejected(
            "OUTPUT_PATH_ALIAS", "sidecar path aliases the publication lock path"
        )

    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise PublicationReceiptRejected(
            "OUTPUT_BUSY", "publication receipt path is locked by another writer"
        ) from exc
    try:
        os.close(lock_fd)
        if receipt_path.exists() or sidecar_path.exists():
            if (
                not receipt_path.exists()
                or not sidecar_path.exists()
                or receipt_path.read_bytes() != data
                or sidecar_path.read_bytes() != sidecar
            ):
                raise PublicationReceiptRejected(
                    "OUTPUT_CONFLICT", "existing publication receipt is not byte-identical"
                )
            return
        ledger.write_bytes_atomic(receipt_path, data)
        ledger.write_bytes_atomic(sidecar_path, sidecar)
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


__all__ = [
    "ED25519_SIGNATURE_ALGORITHM",
    "PUBLICATION_AUTH_CONTRACT_VERSION",
    "PUBLICATION_PURPOSE",
    "PUBLICATION_RECEIPT_SCHEMA",
    "PUBLICATION_ROOT_ID",
    "PublicationReceiptRejected",
    "assemble_publication_receipt_v0",
    "build_publication_body_v0",
    "publication_body_bytes_v0",
    "publication_receipt_bytes_v0",
    "validate_publication_body_v0",
    "validate_publication_receipt_v0",
    "write_publication_receipt_v0",
]
