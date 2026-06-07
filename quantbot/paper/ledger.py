"""Append-only JSONL ledger IO with idempotent, id-keyed appends.

All ledger rows are written with sorted keys for deterministic, byte-stable output.
Prior rows are never rewritten (see docs/paper_pnl_v1_schema.md section 5).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


class LedgerCorruptionError(ValueError):
    """A persisted JSONL ledger is unreadable (a line is not valid JSON).

    Reads of existing ledgers must fail CLOSED (Blocker 2): a malformed line can never be
    silently skipped or allowed to traceback as a bare JSONDecodeError. The runner converts
    this into a CORRUPT_LEDGER status (CLI exit 4) before any new ledger/snapshot/state row is
    written.
    """


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read all rows from a JSONL file. Missing file -> empty list.

    A malformed line raises LedgerCorruptionError (fail closed), never a bare JSONDecodeError
    and never a silent skip — a corrupt ledger must surface as CORRUPT_LEDGER (Blocker 2).
    """
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise LedgerCorruptionError(
                    f"{path.name}: line {lineno} is not valid JSON ({exc}); refusing to "
                    f"read a corrupt ledger"
                ) from exc
    return rows


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


def write_json(path: Path, obj: Any) -> None:
    """Overwrite a JSON file deterministically (sorted keys, trailing newline)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)
