"""Append-only JSONL ledger IO with idempotent, id-keyed appends.

All ledger rows are written with sorted keys for deterministic, byte-stable output.
Prior rows are never rewritten (see docs/paper_pnl_v1_schema.md section 5).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable


class LedgerCorruptionError(ValueError):
    """A persisted JSON/JSONL artifact is unreadable or has the wrong shape.

    Reads of existing ledgers/summaries must fail CLOSED (Blocker 2). A corrupt artifact can
    never be silently skipped or allowed to traceback as a bare JSONDecodeError / UnicodeError /
    AttributeError. Every fault mode is normalized to this one type:
      - invalid UTF-8 bytes,
      - invalid JSON (a JSONL line, or a whole JSON file),
      - a JSONL row that parses but is NOT an object (e.g. ``[]`` / ``123``),
      - a JSON file that parses but is NOT an object.
    The runner converts this into a CORRUPT_LEDGER status (CLI exit 4) before any new
    ledger/snapshot/state row is written.
    """


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read all rows from a JSONL file. Missing file -> empty list.

    Fails CLOSED with LedgerCorruptionError (never a bare JSONDecodeError, UnicodeDecodeError,
    or a silent skip) on: invalid UTF-8 bytes, a line that is not valid JSON, or a line that
    parses but is not a JSON object (e.g. ``[]`` / ``123`` — a non-dict row would otherwise
    AttributeError on ``.get`` downstream). A corrupt ledger must surface as CORRUPT_LEDGER
    (Blocker 2).
    """
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with open(path, encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise LedgerCorruptionError(
                        f"{path.name}: line {lineno} is not valid JSON ({exc}); refusing to "
                        f"read a corrupt ledger"
                    ) from exc
                # Every JSONL ledger row MUST be an object. A valid-JSON non-object row such as
                # `[]` or `123` would pass json.loads but then AttributeError on `.get(...)` in
                # reconcile/freshness — fail closed here instead (Blocker 2).
                if not isinstance(row, dict):
                    raise LedgerCorruptionError(
                        f"{path.name}: line {lineno} is valid JSON but not an object "
                        f"(got {type(row).__name__}); every ledger row must be an object — "
                        f"refusing to read a corrupt ledger"
                    )
                rows.append(row)
    except UnicodeDecodeError as exc:
        raise LedgerCorruptionError(
            f"{path.name} is not valid UTF-8 ({exc}); refusing to read a corrupt ledger"
        ) from exc
    return rows


def read_json_obj(path: Path, default: Any = None) -> Any:
    """Read a JSON *object* file, failing CLOSED on any parse/shape fault (Blocker 2).

    Missing file -> ``default``. Invalid UTF-8, invalid JSON, or a value that parses but is not
    a JSON object (e.g. ``[]`` / ``123`` / ``"x"``) raises LedgerCorruptionError instead of
    tracebacking as a bare JSONDecodeError / UnicodeError or silently feeding a non-dict into
    ``.get(...)``. Used for the persisted summary and position-state artifacts.
    """
    if not path.exists():
        return default
    try:
        obj = json.loads(path.read_bytes().decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise LedgerCorruptionError(
            f"{path.name} is not valid UTF-8 ({exc}); refusing to read a corrupt artifact"
        ) from exc
    except json.JSONDecodeError as exc:
        raise LedgerCorruptionError(
            f"{path.name} is not valid JSON ({exc}); refusing to read a corrupt artifact"
        ) from exc
    if not isinstance(obj, dict):
        raise LedgerCorruptionError(
            f"{path.name} is valid JSON but not an object (got {type(obj).__name__}); "
            f"refusing to read a corrupt artifact"
        )
    return obj


def existing_ids(path: Path, id_field: str) -> set[str]:
    """Return the set of id values already present in a JSONL ledger."""
    return {str(row[id_field]) for row in read_jsonl(path) if id_field in row}


def append_rows(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    """Append rows as JSONL with sorted keys. Returns number of rows written."""
    rows = list(rows)
    if not rows:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    return len(rows)


def append_new(path: Path, rows: Iterable[dict[str, Any]], id_field: str) -> int:
    """Append only rows whose id_field is not already present (idempotent)."""
    seen = existing_ids(path, id_field)
    fresh = [r for r in rows if str(r[id_field]) not in seen]
    return append_rows(path, fresh)


def json_bytes(obj: Any) -> bytes:
    """Deterministic on-disk byte encoding of a JSON file (sorted keys, trailing newline).

    Exposed so the evidence-publication protocol (Blocker 1) can hash the EXACT bytes a
    summary will occupy on disk before it is written — the OK summary is published last, so
    provenance pins its digest from these in-memory bytes rather than reading the (still
    stale) file.
    """
    return (json.dumps(obj, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write bytes via a temp file + atomic os.replace (Blocker 1).

    The final path is only ever observed as fully-old or fully-new content: a crash mid-write
    leaves the temp file (cleaned up) and never a half-written final artifact. This is what
    lets the OK summary be published as an all-or-nothing final step.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_json_atomic(path: Path, obj: Any) -> None:
    """Atomically overwrite a JSON file deterministically (sorted keys, trailing newline)."""
    _atomic_write_bytes(path, json_bytes(obj))


def write_text_atomic(path: Path, text: str) -> None:
    """Atomically overwrite a text file (temp + os.replace)."""
    _atomic_write_bytes(path, text.encode("utf-8"))


def write_bytes_atomic(path: Path, data: bytes) -> None:
    """Atomically overwrite a file with pre-serialized bytes (temp + os.replace)."""
    _atomic_write_bytes(path, data)


def write_json(path: Path, obj: Any) -> None:
    """Overwrite a JSON file deterministically (sorted keys, trailing newline)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)
