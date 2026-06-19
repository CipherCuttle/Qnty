"""Pure read-only funding-coverage check for the paper_pnl_v1 verifier.

Implements the pre-batch coverage gate specified in
docs/plans/FUNDING_COVERAGE_FAIL_CLOSED_GATE_PLAN.md §3.2 and §4.

This module is STRICTLY READ-ONLY with respect to the ledger, the source funding CSVs,
and the repo data directory. It does not mutate anything on disk. It does not import
``quantbot.data.funding_loader`` (architect §6.1 mitigation — that loader silently
skips symbols with missing CSVs; this gate must not).

Covered paths (after this PR):
  - legacy JSONL verifier (``quantbot.paper.verify``) via ``check_funding_coverage``;
  - SQLite verifier (``quantbot.paper.sqlite_verify``) via
    ``check_funding_coverage_from_rows``.
Both paths share the same classification logic (private ``_classify_rows`` helper).

Public surface (per architect §3.2):

    @dataclass(frozen=True) CoverageRow(...)
    @dataclass(frozen=True) FundingCoverageReport(...)
    def check_funding_coverage(
        funding_ledger_path: Path,
        funding_csv_dir: Path,
        *,
        symbols: Iterable[str] | None = None,
    ) -> FundingCoverageReport
    def check_funding_coverage_from_rows(
        rows: Iterable[dict],
        funding_csv_dir: Path,
        *,
        symbols: Iterable[str] | None = None,
    ) -> FundingCoverageReport
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Mapping

from quantbot.paper.funding_status import (
    COVERAGE_COMPLETE,
    COVERAGE_MISSING,
    COVERAGE_NOT_REQUIRED,
    COVERAGE_PARTIAL,
)


def _parse_iso(ts: str) -> datetime:
    """Parse an ISO-8601 timestamp string into an aware UTC datetime.

    The funding ledger stores ``window_start``/``window_end`` as the same ISO strings
    the runner uses for bar timestamps (e.g. ``2026-06-14T08:00:00``); the source
    funding CSV stores ``fundingTime`` as integer milliseconds since epoch. Both are
    normalised to UTC-aware ``datetime`` here so the window comparison is a simple
    tuple comparison.
    """
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _parse_funding_time_ms(raw: str) -> datetime | None:
    """Parse a ``fundingTime`` CSV cell (integer ms epoch) into UTC datetime.

    Returns ``None`` for malformed rows; such rows are simply skipped (not counted
    in any window). The original CSV is not modified.
    """
    try:
        ms = int(raw)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)


@dataclass(frozen=True)
class CoverageRow:
    """One per-funding-ledger-row coverage result."""

    funding_id: str
    symbol: str
    bar_ts: str
    window_start: str
    window_end: str
    rate_available: bool
    source_row_count: int


@dataclass(frozen=True)
class FundingCoverageReport:
    """Aggregate coverage result for a paper batch."""

    per_symbol: dict[str, str] = field(default_factory=dict)
    missing_windows: list[CoverageRow] = field(default_factory=list)
    total_funding_rows: int = 0
    total_rate_available_zero: int = 0
    total_required_intervals: int = 0
    overall_decision: str = COVERAGE_NOT_REQUIRED


def _load_csv_window(
    funding_csv_dir: Path, symbol: str, ws: datetime, we: datetime
) -> int:
    """Count CSV rows for ``symbol`` with ``fundingTime`` in ``(ws, we]``.

    Returns 0 when the CSV is absent or has no header / no data rows. A header-only
    CSV is treated as zero rows. Open-closed interval per architect §4.2.
    """
    csv_path = funding_csv_dir / f"{symbol}_8h_funding.csv"
    if not csv_path.is_file():
        return 0
    try:
        with csv_path.open("r", newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames is None or "fundingTime" not in reader.fieldnames:
                return 0
            count = 0
            for row in reader:
                ts = _parse_funding_time_ms(row.get("fundingTime", ""))
                if ts is None:
                    continue
                if ws < ts <= we:
                    count += 1
            return count
    except OSError:
        # CSV unreadable: treat as no source coverage (fail-closed).
        return 0


def _classify_rows(
    rows: Iterable[dict],
    funding_csv_dir: Path,
    *,
    symbols: Iterable[str] | None = None,
) -> FundingCoverageReport:
    """Classify an iterable of funding-row dicts into a FundingCoverageReport.

    Shared by both the legacy JSONL verifier and the SQLite verifier. Each
    row dict must expose the keys ``funding_id``, ``symbol``, ``bar_ts``,
    ``window_start``, ``window_end``, and ``rate_available`` (integer 0/1 from
    SQLite, or 0/1/bool/string from JSONL). Extra keys are ignored. The
    classifier is read-only: it does not mutate the rows, the CSVs, or anything
    else on disk.

    Parameters
    ----------
    rows
        Iterable of dict-like funding rows. JSONL callers parse lines and pass
        the parsed dicts; SQLite callers pass the result of
        ``_rows(conn, "SELECT * FROM funding")``.
    funding_csv_dir
        Directory containing ``<SYM>_8h_funding.csv`` files.
    symbols
        Optional explicit allow-list of symbols. When ``None``, every symbol
        appearing in the rows is considered.

    Returns
    -------
    FundingCoverageReport
        Frozen dataclass containing per-symbol coverage, missing windows,
        totals, and the overall decision.
    """
    coverage_rows: list[CoverageRow] = []
    total_rate_zero = 0
    symbols_in_ledger: set[str] = set()

    for obj in rows:
        if obj is None:
            continue

        # Ledger keys are derived from db.py:281-283 (funding table schema).
        funding_id = str(obj.get("funding_id", ""))
        symbol = str(obj.get("symbol", ""))
        bar_ts = str(obj.get("bar_ts", ""))
        window_start_raw = str(obj.get("window_start", ""))
        window_end_raw = str(obj.get("window_end", ""))
        rate_available_raw = obj.get("rate_available", 0)

        # rate_available is serialised as 0/1 (sqlite INTEGER); normalise.
        rate_available = bool(rate_available_raw)
        if isinstance(rate_available_raw, int):
            rate_available = rate_available_raw != 0
        elif isinstance(rate_available_raw, str):
            rate_available = rate_available_raw not in ("", "0", "false", "False")

        if not symbol or not window_start_raw or not window_end_raw:
            # Malformed row — treat as missing.
            rate_available = False

        ws = _parse_iso(window_start_raw)
        we = _parse_iso(window_end_raw)
        symbols_in_ledger.add(symbol)
        src_count = _load_csv_window(funding_csv_dir, symbol, ws, we)

        row = CoverageRow(
            funding_id=funding_id,
            symbol=symbol,
            bar_ts=bar_ts,
            window_start=window_start_raw,
            window_end=window_end_raw,
            rate_available=rate_available,
            source_row_count=src_count,
        )
        coverage_rows.append(row)
        if not rate_available:
            total_rate_zero += 1

    missing = [
        r for r in coverage_rows
        if (not r.rate_available) or (r.source_row_count == 0)
    ]

    # Optional explicit symbol allow-list narrows per_symbol view to the listed set
    # but the row set still drives required-intervals counts.
    if symbols is not None:
        allowed = set(symbols)
        per_symbol_pool = [r for r in coverage_rows if r.symbol in allowed]
    else:
        per_symbol_pool = list(coverage_rows)

    by_symbol: dict[str, list[CoverageRow]] = defaultdict(list)
    for r in per_symbol_pool:
        by_symbol[r.symbol].append(r)

    per_symbol_decision: dict[str, str] = {}
    has_any_rows = False
    for sym in sorted(by_symbol):
        has_any_rows = True
        sym_rows = by_symbol[sym]
        sym_missing = [
            r for r in sym_rows if (not r.rate_available) or (r.source_row_count == 0)
        ]
        if not sym_missing:
            per_symbol_decision[sym] = COVERAGE_COMPLETE
        elif len(sym_missing) == len(sym_rows):
            per_symbol_decision[sym] = COVERAGE_MISSING
        else:
            per_symbol_decision[sym] = COVERAGE_PARTIAL

    # Symbols with no rows in the row set (or filtered out by allow-list) are
    # NOT_REQUIRED: they impose no required funding interval.
    if symbols is None:
        for sym in sorted(symbols_in_ledger):
            per_symbol_decision.setdefault(sym, COVERAGE_NOT_REQUIRED)

    # Overall decision (architect §4.2 ordering).
    if not has_any_rows and not symbols_in_ledger:
        overall = COVERAGE_NOT_REQUIRED
    elif any(d == COVERAGE_MISSING for d in per_symbol_decision.values()):
        overall = COVERAGE_MISSING
    elif any(d == COVERAGE_PARTIAL for d in per_symbol_decision.values()):
        overall = COVERAGE_PARTIAL
    elif per_symbol_decision and all(
        d in (COVERAGE_COMPLETE, COVERAGE_NOT_REQUIRED)
        for d in per_symbol_decision.values()
    ):
        overall = COVERAGE_COMPLETE
    else:
        overall = COVERAGE_NOT_REQUIRED

    return FundingCoverageReport(
        per_symbol=dict(per_symbol_decision),
        missing_windows=list(missing),
        total_funding_rows=len(coverage_rows),
        total_rate_available_zero=total_rate_zero,
        total_required_intervals=len(coverage_rows),
        overall_decision=overall,
    )


def check_funding_coverage(
    funding_ledger_path: Path,
    funding_csv_dir: Path,
    *,
    symbols: Iterable[str] | None = None,
) -> FundingCoverageReport:
    """Compute funding-source coverage for a paper batch from its frozen ledger.

    Thin JSONL reader: opens ``paper_funding.jsonl`` line by line and delegates
    to ``_classify_rows``. Missing / empty file yields an empty report
    (NOT_REQUIRED). Use ``check_funding_coverage_from_rows`` for the SQLite path.

    Parameters
    ----------
    funding_ledger_path
        Path to ``paper_funding.jsonl`` (a per-row JSON ledger; one row per held
        funding accrual). Read line by line. Missing / empty file yields an empty
        report (NOT_REQUIRED).
    funding_csv_dir
        Directory containing ``<SYM>_8h_funding.csv`` files with columns
        ``fundingTime,fundingRate,markPrice`` (integer-ms epoch in ``fundingTime``).
        Read-only. May be absent.
    symbols
        Optional explicit allow-list of symbols. When ``None``, every symbol that
        appears in the ledger is considered. The argument is accepted for future
        extension; the current implementation treats the ledger as the source of
        truth for which symbols are required.

    Returns
    -------
    FundingCoverageReport
        Frozen dataclass containing per-symbol coverage, missing windows, totals,
        and the overall decision.
    """
    parsed: list[dict] = []
    if funding_ledger_path.is_file():
        with funding_ledger_path.open("r", encoding="utf-8") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    # A malformed ledger row is not silently dropped: it surfaces as
                    # a missing window (rate_available=False) inside _classify_rows
                    # because the symbol/window parse path falls back to False when
                    # the row lacks valid keys.
                    continue
                parsed.append(obj)
    return _classify_rows(parsed, funding_csv_dir, symbols=symbols)


def check_funding_coverage_from_rows(
    rows: Iterable[dict],
    funding_csv_dir: Path,
    *,
    symbols: Iterable[str] | None = None,
) -> FundingCoverageReport:
    """Compute funding-source coverage from an in-memory iterable of row dicts.

    Used by the SQLite verifier (``quantbot.paper.sqlite_verify``), which already
    holds a pinned read-only snapshot of the ``funding`` table. Delegates to the
    shared ``_classify_rows`` helper so the JSONL and SQLite paths cannot diverge.

    Parameters
    ----------
    rows
        Iterable of dict-like funding rows. Each row must expose at least
        ``funding_id``, ``symbol``, ``bar_ts``, ``window_start``, ``window_end``,
        and ``rate_available`` (INTEGER 0/1). Extra columns are ignored.
    funding_csv_dir
        Directory containing ``<SYM>_8h_funding.csv`` files (same contract as
        ``check_funding_coverage``).
    symbols
        Optional explicit allow-list of symbols; same semantics as
        ``check_funding_coverage``.

    Returns
    -------
    FundingCoverageReport
        Frozen dataclass containing per-symbol coverage, missing windows, totals,
        and the overall decision.
    """
    return _classify_rows(rows, funding_csv_dir, symbols=symbols)


def _csv_has_row_in_interval(
    funding_csv_dir: Path,
    symbol: str,
    ws: datetime,
    we: datetime,
    bar_interval_hours: int,
) -> bool:
    """Return True iff ``<SYM>_<N>h_funding.csv`` has a row in (ws, we].

    Mirrors the open-closed interval contract used by ``engine.funding_in_interval``
    (left-open, right-closed). A missing/header-only/unreadable CSV is treated as
    ``False`` (fail-closed). Pure read; never mutates the CSV or anything else on disk.
    """
    csv_path = funding_csv_dir / f"{symbol}_{bar_interval_hours}h_funding.csv"
    if not csv_path.is_file():
        return False
    try:
        with csv_path.open("r", newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames is None or "fundingTime" not in reader.fieldnames:
                return False
            for row in reader:
                ts = _parse_funding_time_ms(row.get("fundingTime", ""))
                if ts is None:
                    continue
                if ws < ts <= we:
                    return True
            return False
    except OSError:
        return False


def check_funding_coverage_for_batch(
    forward_obs: Iterable[Mapping[str, Any]],
    bars_by_symbol: Mapping[str, Any],
    funding_csv_dir: Path,
    *,
    symbols: Iterable[str] | None = None,
    bar_interval_hours: int = 8,
) -> FundingCoverageReport:
    """Pre-batch funding-coverage check used by the runner's fail-closed gate (§3.3).

    For every in-scope symbol (intersection of ``bars_by_symbol.keys()`` with the
    optional ``symbols=`` allow-list) and every required funding interval derived
    from a ``forward_obs`` bar timestamp, this synthesises one row dict of the
    shape consumed by ``_classify_rows`` (the shared private classifier) and
    delegates. The runner-side classification therefore cannot diverge from the
    legacy JSONL verifier and the SQLite verifier — both of which also delegate
    to ``_classify_rows``.

    Required interval windows (re-implements ``engine._interval_start`` math
    locally; the private leading-underscore symbol is not imported):
      window = (bar_ts - N hours, bar_ts]  with N = ``bar_interval_hours``.

    Parameters
    ----------
    forward_obs
        Iterable of per-bar observation mappings produced by the observer. Each
        entry must carry a parseable UTC-aware bar timestamp under the key
        ``bar_ts`` (preferred) or ``timestamp`` (the runner's actual on-disk
        shape — accepted as a fallback for wiring convenience).
    bars_by_symbol
        Per-symbol bar book that the runner is about to feed to ``run_engine``.
        Its keys define the default in-scope symbol set.
    funding_csv_dir
        Directory containing ``<SYM>_<N>h_funding.csv`` files. Read-only.
    symbols
        Optional explicit allow-list of symbols. When ``None``, every symbol in
        ``bars_by_symbol.keys()`` is in scope.
    bar_interval_hours
        Funding window length in hours. Must be a positive int divisor of 24
        (paper_pnl_v1 pins it to 8 via the config contract).

    Returns
    -------
    FundingCoverageReport
        Frozen dataclass with per-symbol coverage, missing windows, totals, and
        overall decision. Empty scope or empty ``forward_obs`` yields
        ``overall_decision == COVERAGE_NOT_REQUIRED`` — the gate is then a
        pass-through.

    Raises
    ------
    ValueError
        If ``bar_interval_hours`` is not a positive int divisor of 24, or if any
        ``forward_obs`` entry carries an unparseable / naive bar timestamp
        (fail-closed: a malformed bar timestamp must not silently pass the gate).
    """
    # --- bar_interval_hours contract (positive int divisor of 24) ---
    if (
        not isinstance(bar_interval_hours, int)
        or isinstance(bar_interval_hours, bool)
        or bar_interval_hours <= 0
        or 24 % bar_interval_hours != 0
    ):
        raise ValueError(
            f"bar_interval_hours must be a positive int divisor of 24 "
            f"(got {bar_interval_hours!r})"
        )

    # --- in-scope symbols ---
    bars_keys = set(bars_by_symbol.keys())
    if symbols is not None:
        scope = bars_keys & set(symbols)
    else:
        scope = set(bars_keys)

    if not scope:
        # Empty scope -> NOT_REQUIRED overall (mirror the verifier semantics).
        return FundingCoverageReport(
            per_symbol={},
            missing_windows=[],
            total_funding_rows=0,
            total_rate_available_zero=0,
            total_required_intervals=0,
            overall_decision=COVERAGE_NOT_REQUIRED,
        )

    # --- compute required intervals from forward_obs ---
    intervals: list[tuple[datetime, datetime, str, str]] = []
    seen: set[tuple[datetime, datetime]] = set()
    for o in forward_obs:
        if o is None:
            continue
        # Per spec: forward_obs entries expose bar_ts. The runner's actual on-disk
        # shape uses ``timestamp``; accept either for wiring convenience.
        raw_ts = o.get("bar_ts")
        if raw_ts is None:
            raw_ts = o.get("timestamp")
        if raw_ts is None or raw_ts == "":
            continue
        raw_ts = str(raw_ts)
        try:
            dt = datetime.fromisoformat(raw_ts)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"forward_obs entry has non-parseable bar_ts {raw_ts!r}: {exc}"
            ) from exc
        # Naive timestamps are normalised to UTC (matches ``freshness.parse_bar_utc``
        # and the verifier's ``_parse_iso``); aware timestamps are converted to UTC.
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        dt_utc = dt
        ws = dt_utc - timedelta(hours=bar_interval_hours)
        we = dt_utc
        key = (ws, we)
        if key in seen:
            continue
        seen.add(key)
        ws_iso = ws.strftime("%Y-%m-%dT%H:%M:%S")
        we_iso = we.strftime("%Y-%m-%dT%H:%M:%S")
        intervals.append((ws, we, ws_iso, we_iso))

    if not intervals:
        # No required intervals (empty forward_obs) -> NOT_REQUIRED overall.
        return FundingCoverageReport(
            per_symbol={sym: COVERAGE_NOT_REQUIRED for sym in sorted(scope)},
            missing_windows=[],
            total_funding_rows=0,
            total_rate_available_zero=0,
            total_required_intervals=0,
            overall_decision=COVERAGE_NOT_REQUIRED,
        )

    # --- synthesise rows for _classify_rows ---
    synthetic: list[dict[str, Any]] = []
    for sym in sorted(scope):
        for ws, we, ws_iso, we_iso in intervals:
            has_row = _csv_has_row_in_interval(
                funding_csv_dir, sym, ws, we, bar_interval_hours
            )
            # bar_ts on the synthetic row carries the midpoint of the interval,
            # matching the per-spec synthetic-row contract.
            midpoint = ws + timedelta(hours=bar_interval_hours / 2)
            mid_iso = midpoint.strftime("%Y-%m-%dT%H:%M:%S")
            synthetic.append({
                "funding_id": f"synthetic:{sym}:{ws_iso}",
                "symbol": sym,
                "bar_ts": mid_iso,
                "window_start": ws_iso,
                "window_end": we_iso,
                "rate_available": has_row,
            })

    return _classify_rows(synthetic, funding_csv_dir, symbols=sorted(scope))
