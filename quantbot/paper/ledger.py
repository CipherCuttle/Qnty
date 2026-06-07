"""Append-only JSONL ledger IO with idempotent, id-keyed appends.

All ledger rows are written with sorted keys for deterministic, byte-stable output.
Prior rows are never rewritten (see docs/paper_pnl_v1_schema.md section 5).
"""

from __future__ import annotations

import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable, Sequence

# Authoritative current-run status values (schema doc § 5). RUNNING is the transient
# in-flight marker written before any mutation; OK is the final commit marker. Every other
# value is a terminal non-OK status. A persisted summary whose `status` is not one of these
# is corrupt (Blocker 2).
KNOWN_SUMMARY_STATUSES = frozenset(
    {"OK", "RUNNING", "ABORTED", "CORRUPT_LEDGER", "NO_ELIGIBLE_BARS_YET"}
)


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


def _finite_number(v: Any) -> bool:
    """True iff v is a finite int/float (NOT bool; NaN/inf/-inf/str rejected)."""
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _nonneg_finite(v: Any) -> bool:
    """True iff v is a finite int/float (NOT bool) >= 0."""
    return _finite_number(v) and v >= 0


def _nonempty_str(v: Any) -> bool:
    """True iff v is a non-empty string."""
    return isinstance(v, str) and v != ""


def _str_list(v: Any) -> bool:
    """True iff v is a list whose every element is a non-empty string."""
    return isinstance(v, list) and all(_nonempty_str(e) for e in v)


def read_jsonl_validated(
    path: Path,
    *,
    name: str,
    spec: dict[str, Any],
) -> list[dict[str, Any]]:
    """Read a JSONL ledger and validate parse AND shape, failing CLOSED (Blocker 2).

    On top of read_jsonl's dict-ness guarantee, every row is deeply type-checked against the
    per-artifact `spec` (see quantbot.paper.reconcile.LEDGER_JSONL_SCHEMAS):

    - ``required``  : the field must be present (any value).
    - ``numeric``   : finite int/float (not bool/NaN/inf/-inf/str).
    - ``nonneg``    : finite int/float >= 0 (not bool/NaN/inf/str).
    - ``strings``   : non-empty string.
    - ``str_lists`` : a list whose every element is a non-empty string.
    - ``bools``     : a real ``bool``.
    - ``enums``     : ``{field: allowed_values}`` — value must be in the allowed set.

    A structurally malformed row — an empty object ``{}`` (which would later KeyError in
    reconcile), a string/NaN where a number is needed (which would later TypeError), a scalar
    where a list is needed (e.g. ``open_symbols="AAA"``), or an out-of-enum side/kind — raises
    LedgerCorruptionError instead. The runner/health-gate convert this to CORRUPT_LEDGER
    (exit 4) with no traceback. Well-formedness of ``bar_commit_id`` (16-hex) is intentionally
    left to reconcile's structural pass so it can report a per-row message; the spec only
    requires its presence here.
    """
    rows = read_jsonl(path)
    required: Sequence[str] = spec.get("required", ())
    numeric: Sequence[str] = spec.get("numeric", ())
    nonneg: Sequence[str] = spec.get("nonneg", ())
    strings: Sequence[str] = spec.get("strings", ())
    str_lists: Sequence[str] = spec.get("str_lists", ())
    bools: Sequence[str] = spec.get("bools", ())
    enums: dict[str, Any] = spec.get("enums", {})
    for lineno, row in enumerate(rows, start=1):
        missing = [f for f in required if f not in row]
        if missing:
            raise LedgerCorruptionError(
                f"{name}: row {lineno} is missing required field(s) {missing} "
                f"(malformed/partial ledger row); refusing to read a corrupt ledger"
            )
        for f in numeric:
            if not _finite_number(row.get(f)):
                raise LedgerCorruptionError(
                    f"{name}: row {lineno} field {f!r} must be a finite number "
                    f"(got {row.get(f)!r}); refusing to read a corrupt ledger"
                )
        for f in nonneg:
            if not _nonneg_finite(row.get(f)):
                raise LedgerCorruptionError(
                    f"{name}: row {lineno} field {f!r} must be a finite number >= 0 "
                    f"(got {row.get(f)!r}); refusing to read a corrupt ledger"
                )
        for f in strings:
            if not _nonempty_str(row.get(f)):
                raise LedgerCorruptionError(
                    f"{name}: row {lineno} field {f!r} must be a non-empty string "
                    f"(got {row.get(f)!r}); refusing to read a corrupt ledger"
                )
        for f in str_lists:
            if not _str_list(row.get(f)):
                raise LedgerCorruptionError(
                    f"{name}: row {lineno} field {f!r} must be a list of non-empty strings "
                    f"(got {row.get(f)!r}); refusing to read a corrupt ledger"
                )
        for f in bools:
            if not isinstance(row.get(f), bool):
                raise LedgerCorruptionError(
                    f"{name}: row {lineno} field {f!r} must be a boolean "
                    f"(got {row.get(f)!r}); refusing to read a corrupt ledger"
                )
        for f, allowed in enums.items():
            if row.get(f) not in allowed:
                raise LedgerCorruptionError(
                    f"{name}: row {lineno} field {f!r} must be one of {sorted(allowed)} "
                    f"(got {row.get(f)!r}); refusing to read a corrupt ledger"
                )
    return rows


def validate_summary_shape(summary: dict[str, Any], *, name: str = "paper_pnl_summary.json") -> None:
    """Fail CLOSED on a structurally malformed persisted summary (Blocker 2).

    A persisted summary that parses to an object but is empty (``{}``), carries an unknown
    `status`, or — for an `OK` summary — has wrong-typed numeric fields would otherwise be
    silently overwritten with a fresh OK or TypeError deep in reconcile/CLI. Validate the
    shape here so it surfaces as CORRUPT_LEDGER. Raises LedgerCorruptionError.
    """
    status = summary.get("status")
    if status not in KNOWN_SUMMARY_STATUSES:
        raise LedgerCorruptionError(
            f"{name}: status {status!r} is missing/unknown (expected one of "
            f"{sorted(KNOWN_SUMMARY_STATUSES)}); refusing to read a corrupt summary"
        )
    sv = summary.get("schema_version")
    if isinstance(sv, bool) or not isinstance(sv, int):
        raise LedgerCorruptionError(
            f"{name}: schema_version must be an int (got {sv!r}); corrupt summary"
        )
    if not isinstance(summary.get("baseline_label"), str):
        raise LedgerCorruptionError(
            f"{name}: baseline_label must be a string; corrupt summary"
        )
    if not isinstance(summary.get("forward_start_ts"), str):
        raise LedgerCorruptionError(
            f"{name}: forward_start_ts must be a string; corrupt summary"
        )
    # The loud SIMULATION disclaimer is mandatory on every published summary (schema § 4); a
    # summary that lost it is corrupt (Blocker 2) — a downstream reader must never see an OK/
    # accounting summary stripped of the not-live-trading guardrail.
    if not _nonempty_str(summary.get("disclaimer")):
        raise LedgerCorruptionError(
            f"{name}: disclaimer must be a non-empty string; corrupt summary"
        )
    if status == "OK":
        for fld in ("closed_trades", "bars_elapsed", "num_open"):
            v = summary.get(fld)
            if isinstance(v, bool) or not isinstance(v, int) or v < 0:
                raise LedgerCorruptionError(
                    f"{name}: OK summary field {fld!r} must be a non-negative int "
                    f"(got {v!r}); corrupt summary"
                )
        for fld in ("realized_net_pnl", "total_pnl", "max_drawdown"):
            if not _finite_number(summary.get(fld)):
                raise LedgerCorruptionError(
                    f"{name}: OK summary field {fld!r} must be a finite number "
                    f"(got {summary.get(fld)!r}); corrupt summary"
                )
        # winrate/profit_factor/expectancy are null until closed_trades > 0; if present and
        # non-null they must be finite numbers.
        for fld in ("winrate", "profit_factor", "expectancy"):
            v = summary.get(fld)
            if v is not None and not _finite_number(v):
                raise LedgerCorruptionError(
                    f"{name}: OK summary field {fld!r} must be null or a finite number "
                    f"(got {v!r}); corrupt summary"
                )


def read_summary_obj(path: Path) -> dict[str, Any]:
    """Read + shape-validate the persisted summary. Absent file -> ``{}`` (Blocker 2).

    Distinguishes an absent summary (first run, returns ``{}``) from an on-disk empty object
    ``{}`` (corrupt: it parses but has no status). A present file is read via read_json_obj
    (object-ness fail-closed) then validate_summary_shape.
    """
    if not path.exists():
        return {}
    obj = read_json_obj(path)
    validate_summary_shape(obj, name=path.name)
    return obj


# Required shape of paper_position_state.json (engine.new_state). A present-but-empty (`{}`)
# or partial state must be CORRUPT, not silently reinitialized / KeyError'd later (Blocker 2).
_STATE_ACCUMULATOR_KEYS = ("realized_gross", "fees_cum", "funding_cum")

# Required shape of each open_positions entry (engine.run_engine writes/reads all of these on a
# subsequent run). A `{}` or partial entry must be CORRUPT, not KeyError later in the engine
# (Codex: `open_positions.AAA={}` passed the health gate then KeyError'd on `hold_bars`).
_OPEN_POSITION_STR_KEYS = ("entry_fill_id", "entry_bar_ts", "entry_fill_ts")
_OPEN_POSITION_NUM_KEYS = ("entry_price", "qty", "funding_accrued", "entry_fee")


def _parseable_bar_ts(ts: str) -> bool:
    """True iff `ts` parses as an observer bar timestamp (lazy import avoids a cycle)."""
    from quantbot.paper import freshness as _freshness

    try:
        _freshness._parse_bar(ts)
    except (TypeError, ValueError):
        return False
    return True


def validate_state_shape(state: dict[str, Any], *, name: str = "paper_position_state.json") -> None:
    """Fail CLOSED on a structurally malformed persisted position state (Blocker 2).

    ``{}`` (which ``read_json_obj``+``or new_state`` would silently treat as absent) and a
    partial state (missing watermark/open_positions/accumulators — which the engine would
    KeyError on) both raise LedgerCorruptionError. The ``watermark_bar_ts`` must be EITHER the
    empty string ``""`` (no bar processed yet — engine.new_state) OR a parseable bar timestamp:
    a non-empty unparseable value (Codex: ``watermark_bar_ts="not-a-timestamp"``) would otherwise
    be republished as ``OK`` and silently shift the reprocessing boundary. Every open position
    must carry the full set of fields the engine indexes (``open_positions.AAA={}`` must fail
    closed, never KeyError on ``hold_bars``).
    """
    wm = state.get("watermark_bar_ts")
    if not isinstance(wm, str):
        raise LedgerCorruptionError(
            f"{name}: missing/invalid watermark_bar_ts (got {wm!r}); corrupt state — "
            f"`{{}}` is corrupt, not absent"
        )
    if wm != "" and not _parseable_bar_ts(wm):
        raise LedgerCorruptionError(
            f"{name}: watermark_bar_ts {wm!r} is not a parseable bar timestamp (or empty); "
            f"corrupt state — refusing to republish an unparseable watermark as OK"
        )
    open_positions = state.get("open_positions")
    if not isinstance(open_positions, dict):
        raise LedgerCorruptionError(
            f"{name}: open_positions must be an object; corrupt state"
        )
    for sym, pos in open_positions.items():
        if not isinstance(pos, dict):
            raise LedgerCorruptionError(
                f"{name}: open_positions[{sym!r}] must be an object (got {pos!r}); corrupt state"
            )
        missing = (
            [k for k in _OPEN_POSITION_STR_KEYS if not _nonempty_str(pos.get(k))]
            + [k for k in _OPEN_POSITION_NUM_KEYS if not _finite_number(pos.get(k))]
        )
        hb = pos.get("hold_bars")
        if isinstance(hb, bool) or not isinstance(hb, int) or hb < 0:
            missing.append("hold_bars")
        if missing:
            raise LedgerCorruptionError(
                f"{name}: open_positions[{sym!r}] missing/invalid field(s) {missing} "
                f"(got {pos!r}); corrupt state — `{{}}`/partial open position never KeyError'd"
            )
    acc = state.get("accumulators")
    if not isinstance(acc, dict) or any(
        not _finite_number(acc.get(k)) for k in _STATE_ACCUMULATOR_KEYS
    ):
        raise LedgerCorruptionError(
            f"{name}: accumulators must be an object with finite "
            f"{list(_STATE_ACCUMULATOR_KEYS)} (got {acc!r}); corrupt state"
        )
    if not _finite_number(state.get("peak_equity")):
        raise LedgerCorruptionError(
            f"{name}: peak_equity must be a finite number (got {state.get('peak_equity')!r}); "
            f"corrupt state"
        )
    be = state.get("bars_elapsed")
    if isinstance(be, bool) or not isinstance(be, int) or be < 0:
        raise LedgerCorruptionError(
            f"{name}: bars_elapsed must be a non-negative int (got {be!r}); corrupt state"
        )


def read_state_obj(path: Path) -> dict[str, Any] | None:
    """Read + shape-validate the persisted position state. Absent file -> None (Blocker 2).

    Absent (first run) returns None so the caller initializes a fresh state. A present file is
    read via read_json_obj (object-ness fail-closed) then validate_state_shape, so a
    present-but-empty (`{}`) or partial state fails closed as CORRUPT_LEDGER rather than being
    silently reinitialized or KeyError'd in the engine.
    """
    if not path.exists():
        return None
    obj = read_json_obj(path)
    validate_state_shape(obj, name=path.name)
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
