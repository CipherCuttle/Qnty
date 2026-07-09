"""Opt-in full-window funding-source snapshot + bundle emission.

PR #120 added the *semantics* of a ``full_window`` snapshot scope (an explicit
discriminator, a full-window snapshot builder, absolute
``resolved_funding_source_dir`` provenance, bundle carry-through, and a
scope-aware full-ledger clean-carry gate) but emitted no runtime artifacts. A
multi-batch ledger therefore still cannot reach full-ledger
``CLEAN_NET_OF_CARRY`` because there is no full-window sidecar for the verifier
to consume (the PR #119 blocker).

This module is the writer-side counterpart: a narrow, explicit, opt-in path that
reads a target lane DB **read-only**, computes the full-ledger funding window
across every committed batch, freezes the required funding source rows, and
writes exactly one ``full_window`` snapshot sidecar plus its immutable bundle
into the lane's ``funding_source_snapshots/`` and ``funding_source_bundles/``
directories.

Deliberate boundaries (see the guardrails in the task receipt):

* The existing per-batch snapshot writer path is untouched: this is a separate
  entry point, invoked explicitly, never wired into ``run_sqlite_accounting``.
* The target DB is opened read-only (``mode=ro`` + ``PRAGMA query_only=ON``).
  This path never mutates the ledger, never updates ``ledger_batches`` reference
  columns, never runs the trader/live/backfill, and never touches a report.
* Selection is unambiguous: the full-window snapshot filename is bound to the
  latest committed batch id (``funding_source_full_window_snapshot_v1_batch<N>``)
  so the verifier resolves it by an exact, derivable path — never a fuzzy glob.
* Binding and digest strictness are identical to the batch builder; nothing here
  weakens a check. A wrong lane/DB/batch/watermark or a drifted source row is
  caught by the same snapshot/bundle validation the batch path uses.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import quantbot.data.funding_loader as _funding_loader
from quantbot.paper.db import connect_readonly
from quantbot.paper.funding_source_bundle import (
    build_funding_source_bundle_v1,
    write_funding_source_bundle,
)
from quantbot.paper.funding_source_snapshot import (
    FULL_WINDOW_SNAPSHOT_FILENAME_PREFIX,
    SNAPSHOT_SCOPE_FULL_WINDOW,
    build_full_window_funding_source_snapshot_payload_v1,
    build_funding_source_snapshot_envelope_v1,
    canonical_json,
    full_window_snapshot_filename,
    full_window_snapshot_path,
    sha256_text,
    validate_funding_source_snapshot_envelope_v1,
)
from quantbot.paper.sqlite_writer import (
    FundingSourceSnapshotEmissionError,
    _read_funding_source_csv_rows,
    _write_json_atomic,
)

_DEFAULT_LANE_ID = "paper_pnl_v1"
_REQUIRED_BY = "paper_engine_funding_interval"


@dataclass(frozen=True)
class FullWindowEmissionResult:
    """Paths + identity of a written full-window snapshot and its bundle."""

    snapshot_path: Path
    bundle_path: Path
    target_batch_id: int
    lane_id: str
    source_bundle_sha256: str
    snapshot_sha256: str
    evaluation_window: dict[str, Any]
    resolved_funding_source_dir: str
    envelope: dict[str, Any]


def _iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _lane_id_from_config(conn: Any) -> str:
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(paper_config)")}
    if "lane_id" not in cols:
        return _DEFAULT_LANE_ID
    row = conn.execute("SELECT lane_id FROM paper_config WHERE id = 1").fetchone()
    if row is None or row["lane_id"] in (None, ""):
        return _DEFAULT_LANE_ID
    return str(row["lane_id"])


def _latest_committed_batch(conn: Any) -> Any:
    return conn.execute(
        """
        SELECT batch_id, prior_watermark_bar_ts, new_watermark_bar_ts
        FROM ledger_batches
        WHERE committed_at IS NOT NULL
        ORDER BY batch_id DESC
        LIMIT 1
        """
    ).fetchone()


def _full_ledger_windows(conn: Any) -> list[dict[str, str]]:
    """Every distinct required funding window across the whole committed ledger."""
    rows = conn.execute(
        """
        SELECT DISTINCT symbol, window_start, window_end
        FROM funding
        ORDER BY symbol, window_start, window_end
        """
    ).fetchall()
    windows: list[dict[str, str]] = []
    for row in rows:
        symbol = str(row["symbol"])
        window_start = str(row["window_start"])
        window_end = str(row["window_end"])
        if not symbol or not window_start or not window_end:
            raise FundingSourceSnapshotEmissionError(
                "full-window emission cannot derive a required funding window "
                f"from funding row {dict(row)!r}"
            )
        windows.append(
            {
                "symbol": symbol,
                "window_start": window_start,
                "window_end": window_end,
                "required_by": _REQUIRED_BY,
            }
        )
    return windows


def _full_ledger_evaluation_window(conn: Any) -> dict[str, str]:
    row = conn.execute(
        "SELECT MIN(window_start) AS start, MAX(window_end) AS end FROM funding"
    ).fetchone()
    if row is None or row["start"] is None or row["end"] is None:
        raise FundingSourceSnapshotEmissionError(
            "full-window emission requires at least one funding row to define the "
            "full-ledger evaluation window"
        )
    return {"start": str(row["start"]), "end": str(row["end"])}


def _resolve_source_dir(data_dir: Path | None) -> Path:
    raw = Path(data_dir) if data_dir is not None else Path(_funding_loader._DATA_DIR)
    resolved = raw.resolve()
    if not resolved.is_absolute():  # pragma: no cover - resolve() is absolute
        raise FundingSourceSnapshotEmissionError(
            f"resolved funding source dir is not absolute: {resolved}"
        )
    return resolved


def _source_csv_paths(windows: list[dict[str, str]], source_dir: Path) -> list[Path]:
    symbols = sorted({w["symbol"] for w in windows})
    return [source_dir / f"{symbol}_8h_funding.csv" for symbol in symbols]


def _db_identity_hash(
    *, db_path: Path, lane_id: str, target_batch_id: int, evaluation_window: dict[str, str]
) -> str:
    identity = {
        "db_path_reference": str(db_path),
        "lane_id": lane_id,
        "ledger_batch_id": str(target_batch_id),
        "evaluation_window": evaluation_window,
        "snapshot_scope": SNAPSHOT_SCOPE_FULL_WINDOW,
    }
    return sha256_text(canonical_json(identity))


def emit_full_window_funding_source_snapshot(
    db_path: str | Path,
    *,
    data_dir: str | Path | None = None,
    generated_at_utc: str | None = None,
    qnty_git_commit: str = "",
    writer_or_verifier_command: str | None = None,
) -> FullWindowEmissionResult:
    """Emit one full-window snapshot + bundle for a target lane DB (read-only).

    Reads ``db_path`` read-only to determine the lane, the latest committed
    batch, and the full-ledger funding window across every committed batch, then
    freezes the required source rows into an explicit ``full_window`` snapshot
    and its immutable bundle. Returns the written paths and identity.

    Raises :class:`FundingSourceSnapshotEmissionError` if the DB has no committed
    batch, no funding rows, or the built snapshot fails validation. This never
    mutates the DB, a report, or a service.
    """
    db_path = Path(db_path)
    data_dir_path = Path(data_dir) if data_dir is not None else None
    lane_output_dir = db_path.parent

    conn = connect_readonly(db_path)
    try:
        lane_id = _lane_id_from_config(conn)
        target_batch = _latest_committed_batch(conn)
        if target_batch is None:
            raise FundingSourceSnapshotEmissionError(
                "full-window emission requires a committed ledger batch"
            )
        target_batch_id = int(target_batch["batch_id"])
        required_windows = _full_ledger_windows(conn)
        evaluation_window = _full_ledger_evaluation_window(conn)
    finally:
        conn.close()

    if not required_windows:
        raise FundingSourceSnapshotEmissionError(
            "full-window emission requires at least one funding window"
        )

    source_dir = _resolve_source_dir(data_dir_path)
    source_file_paths = _source_csv_paths(required_windows, source_dir)
    source_rows = _read_funding_source_csv_rows(source_file_paths)

    generated = generated_at_utc or _iso_z(datetime.now(timezone.utc))
    command = writer_or_verifier_command or (
        "quantbot.paper.funding_source_full_window_emit."
        f"emit_full_window_funding_source_snapshot --db-path {db_path}"
    )
    db_identity_hash_before = _db_identity_hash(
        db_path=db_path,
        lane_id=lane_id,
        target_batch_id=target_batch_id,
        evaluation_window=evaluation_window,
    )

    payload = build_full_window_funding_source_snapshot_payload_v1(
        source_rows=source_rows,
        source_file_paths=source_file_paths,
        required_windows=required_windows,
        full_ledger_evaluation_window=evaluation_window,
        generated_at_utc=generated,
        lane_id=lane_id,
        output_dir=str(lane_output_dir),
        resolved_funding_source_dir=str(source_dir),
        writer_or_verifier_command=command,
        qnty_git_commit=qnty_git_commit,
        write_state="committed",
        db_identity_hash_before=db_identity_hash_before,
        pending_batch_id=None,
        ledger_batch_id=str(target_batch_id),
        batch_identity_matches=True,
        evaluation_identity_matches=True,
        db_path_reference=str(db_path),
        batch_start_watermark=evaluation_window["start"],
        batch_end_watermark=evaluation_window["end"],
    )
    if required_windows and not payload.get("source_files"):
        raise FundingSourceSnapshotEmissionError(
            "full-window snapshot digest construction produced no source_files"
        )
    if payload.get("coverage_decision") != "complete":
        raise FundingSourceSnapshotEmissionError(
            "full-window snapshot coverage is not complete: "
            f"{payload.get('coverage_decision')!r} "
            f"reasons={payload.get('reason_codes')!r}"
        )

    envelope = build_funding_source_snapshot_envelope_v1(payload)
    validation_reasons = validate_funding_source_snapshot_envelope_v1(envelope)
    if validation_reasons:
        raise FundingSourceSnapshotEmissionError(
            "full-window snapshot envelope validation failed: "
            + ", ".join(validation_reasons)
        )

    source_bundle_sha256 = str(payload.get("source_bundle_sha256") or "")
    if len(source_bundle_sha256) != 64:
        raise FundingSourceSnapshotEmissionError(
            f"full-window snapshot bundle digest invalid: {source_bundle_sha256!r}"
        )

    snapshot_path = full_window_snapshot_path(lane_output_dir, target_batch_id)
    _write_json_atomic(snapshot_path, envelope)

    bundle = build_funding_source_bundle_v1(envelope)
    bundle_dir = lane_output_dir / "funding_source_bundles"
    bundle_path = write_funding_source_bundle(bundle, bundle_dir)

    return FullWindowEmissionResult(
        snapshot_path=snapshot_path,
        bundle_path=bundle_path,
        target_batch_id=target_batch_id,
        lane_id=lane_id,
        source_bundle_sha256=source_bundle_sha256,
        snapshot_sha256=str(envelope.get("snapshot_sha256") or ""),
        evaluation_window=evaluation_window,
        resolved_funding_source_dir=str(source_dir),
        envelope=envelope,
    )


__all__ = [
    "FULL_WINDOW_SNAPSHOT_FILENAME_PREFIX",
    "FullWindowEmissionResult",
    "full_window_snapshot_filename",
    "full_window_snapshot_path",
    "emit_full_window_funding_source_snapshot",
]
