"""Append-only JSONL ledger IO with idempotent, id-keyed appends.

All ledger rows are written with sorted keys for deterministic, byte-stable output.
Prior rows are never rewritten (see docs/paper_pnl_v1_schema.md section 5).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read all rows from a JSONL file. Missing file -> empty list."""
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
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
