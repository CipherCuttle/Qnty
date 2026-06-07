"""Authoritative, read-only verifier for paper_pnl_v1 — verify-run snapshot model.

Authority model (see docs/paper_pnl_v1_schema.md § 5a):

  - The paper accounting **runner** (`quantbot.paper.runner`) is NOT the authority on `OK`. It
    only appends deterministic accounting artifacts (fills/trades/funding/positions/equity/
    snapshots + the position state) and may publish a *runner status* in
    `paper_pnl_summary.json`. That summary, `paper_receipt.md`, and `paper_provenance.json` are
    runner conveniences; they are NOT authoritative proof of a trusted run.
  - This **verifier** is the only component allowed to publish an authoritative status. It does
    NOT certify the live, mutable runner artifacts directly. Each invocation:

      1. creates a frozen verify-run directory ``paper_pnl_v1/verify_runs/<run_id>/``;
      2. copies the EXACT raw bytes of every verifier input into ``verify_runs/<run_id>/inputs/``
         (config, the six append-only ledgers, the position state, and the runner summary), and
         detects any source mutation *during* the copy (double-read stat/digest) — an unstable
         snapshot is never `OK`;
      3. verifies the FROZEN input snapshot (never the live files), re-deriving the whole verdict
         from the snapshotted ledgers themselves;
      4. writes the per-run terminal report + receipt into ``verify_runs/<run_id>/`` and updates
         the top-level pointer ``paper_pnl_v1/paper_verify_report.json`` to the latest terminal
         report;
      5. on `OK`, advances the separately-preserved trusted baseline
         ``paper_pnl_v1/paper_verify_trusted_ok.json``. A CORRUPT / INCOMPLETE / CONFIG_ERROR /
         RUNNING_STALE / NEEDS_BOOTSTRAP run NEVER overwrites the trusted baseline, so detected
         tampering is not forgotten on the next run.

Why this defeats the multi-file TOCTOU loop the runner kept losing:

  1. The verdict is a pure function of the FROZEN snapshot bytes. Live files mutating after the
     snapshot cannot flip this run's verdict; they are caught by the *next* verification.
  2. A source file mutating *during* the snapshot copy is detected (double-read digest) and the
     run is CORRUPT, never OK.
  3. Append-only immutability is enforced against the **trusted OK baseline** (preserved across
     corrupt runs), not against the immediately-previous report. A whitespace rewrite / truncation
     / reorder of a previously-trusted ledger fails closed and STAYS failed until the underlying
     corruption is resolved.
  4. The verifier re-derives ALL accounting from the snapshot (fees, gross/net PnL, funding,
     equity, drawdown, open-book/exposure bound) — a fabricated value fails closed.

A paper run is trusted iff the latest ``paper_verify_report.json`` says ``OK``.

The verifier is strictly read-only with respect to the runner's artifacts: it writes only its own
``paper_verify_*`` files and the ``verify_runs/`` tree.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from quantbot.paper import BASELINE_LABEL, SCHEMA_VERSION, paper_output_dir
from quantbot.paper import ledger
from quantbot.paper.config import ConfigContractError, load_config
from quantbot.paper.ledger import LedgerCorruptionError
from quantbot.paper.provenance import DISCLAIMER
from quantbot.paper.reconcile import (
    LEDGER_JSONL_FILES,
    read_ledger_validated,
    reconcile,
    reconcile_state_against_ledgers,
)

VERIFIER_VERSION = "0.3.0"

# Top-level pointer / trust-anchor files (in the paper output dir).
REPORT_FILE = "paper_verify_report.json"          # latest terminal report (pointer)
RECEIPT_FILE = "paper_verify_receipt.md"          # latest terminal receipt (pointer)
LOG_FILE = "paper_verify_log.jsonl"               # append-only audit trail (NON-gating)
TRUSTED_OK_FILE = "paper_verify_trusted_ok.json"  # last trusted OK baseline (preserved)

# Per-run snapshot tree.
VERIFY_RUNS_DIRNAME = "verify_runs"
INPUTS_DIRNAME = "inputs"

SUMMARY_FILE = "paper_pnl_summary.json"
STATE_FILE = "paper_position_state.json"

# A runner that left a `RUNNING` marker older than this (and whose state has not caught up to the
# ledgers) is treated as a crashed/abandoned run -> RUNNING_STALE, never OK.
DEFAULT_RUNNING_STALE_HOURS = 1.0

# The complete set of inputs whose EXACT bytes are snapshotted into verify_runs/<run_id>/inputs/.
# The snapshot dir is laid out exactly like a paper output dir, so every existing read-only
# validator (load_config / reconcile / reconcile_state_against_ledgers) runs unchanged against
# the frozen copy. The runner summary is snapshotted for runner_summary_status / RUNNING_STALE
# detection only (NOT trusted for the verdict).
_AUTHORITATIVE_ARTIFACTS = ("paper_config.json", *LEDGER_JSONL_FILES, STATE_FILE)
_SNAPSHOT_FILES = (*_AUTHORITATIVE_ARTIFACTS, SUMMARY_FILE)

# Authoritative verifier statuses. OK is the only trusted verdict.
STATUS_OK = "OK"
STATUS_CORRUPT = "CORRUPT"
STATUS_INCOMPLETE = "INCOMPLETE"
STATUS_RUNNING_STALE = "RUNNING_STALE"
STATUS_CONFIG_ERROR = "CONFIG_ERROR"
# Committed ledgers exist but there is no trusted OK baseline yet and this run was not asked to
# bootstrap one. The operator must run an explicit `--bootstrap` verification once after review.
STATUS_NEEDS_BOOTSTRAP = "NEEDS_BOOTSTRAP"
# In-flight pointer marker (never a trusted terminal verdict). Written FIRST so a crash/failure
# during verification leaves VERIFYING in the pointer, never a stale OK.
STATUS_VERIFYING = "VERIFYING"


def _now_utc_str(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _raw_digest(path: Path) -> dict[str, Any]:
    """Digest the EXACT raw bytes of a file.

    Returns ``{present, bytes, lines, sha256}``. ``sha256`` is the digest of the whole file's raw
    bytes (not of re-serialized parsed rows), so a whitespace-only rewrite that decodes to the
    same JSON still changes it. Absence/unreadability is recorded as a marker instead of raising.
    """
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return {"present": False, "bytes": 0, "lines": 0, "sha256": "absent"}
    except OSError as exc:
        return {
            "present": False,
            "bytes": 0,
            "lines": 0,
            "sha256": f"unreadable:{type(exc).__name__}:errno={exc.errno}",
        }
    return {
        "present": True,
        "bytes": len(data),
        "lines": data.count(b"\n"),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _parse_started_at(ts: Any) -> datetime | None:
    if not isinstance(ts, str):
        return None
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _run_id(now: datetime) -> str:
    return now.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]


def _snapshot_inputs(
    live: Path,
    inputs: Path,
    *,
    during_snapshot_hook: Callable[[Path], None] | None,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Copy the EXACT bytes of every verifier input into the frozen snapshot dir (Blocker 1/5).

    Returns ``(snapshot_digests, unstable)``:
      - ``snapshot_digests``: ``{name: raw_digest}`` of the COPIED files (what the verdict is
        based on).
      - ``unstable``: inputs whose live bytes changed across a double-read straddling the copy
        (a concurrent mutation during the snapshot). Any unstable input makes the run CORRUPT —
        the cross-file consistency of the snapshot cannot be trusted.

    ``during_snapshot_hook`` is a test-only seam invoked between the copy pass and the second
    stat/digest pass to simulate a concurrent mutation; production callers never pass it.
    """
    inputs.mkdir(parents=True, exist_ok=True)
    first = {n: _raw_digest(live / n) for n in _SNAPSHOT_FILES}
    for n in _SNAPSHOT_FILES:
        if not first[n]["present"]:
            continue
        try:
            ledger.write_bytes_atomic(inputs / n, (live / n).read_bytes())
        except OSError:
            # A file that vanished/locked mid-copy is left absent in the snapshot; the second
            # read below records the instability.
            pass
    if during_snapshot_hook is not None:
        during_snapshot_hook(live)
    second = {n: _raw_digest(live / n) for n in _SNAPSHOT_FILES}
    unstable = [n for n in _SNAPSHOT_FILES if first[n] != second[n]]
    snap = {n: _raw_digest(inputs / n) for n in _SNAPSHOT_FILES}
    return snap, unstable


def _read_trusted_baseline(path: Path) -> tuple[dict[str, Any] | None, bool]:
    """Read + deeply validate the preserved trusted-OK baseline (never raises) (Blocker 3).

    Returns ``(baseline_or_None, corrupt)``:
      - ``(dict, False)`` — a schema-valid trusted OK baseline.
      - ``(None, False)`` — absent (no baseline established yet).
      - ``(None, True)``  — present but unreadable / not JSON / not an object / fails the deep
                            schema check (a malformed baseline must NOT silently reset trust).
    """
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None, False
    except OSError:
        return None, True
    try:
        obj = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, True
    if not isinstance(obj, dict) or not _valid_trusted_baseline(obj):
        return None, True
    return obj, False


def _valid_trusted_baseline(obj: dict[str, Any]) -> bool:
    """Deep schema check of a trusted-OK baseline (Blocker 3).

    A baseline is only usable if it is a genuine OK baseline carrying append-only digest pins for
    every ledger. Anything short of that (``{}``, wrong status, missing/garbage pins) is treated
    as corrupt by the caller rather than reset.
    """
    if obj.get("status") != STATUS_OK:
        return False
    if obj.get("schema_version") != SCHEMA_VERSION:
        return False
    if obj.get("baseline_label") != BASELINE_LABEL:
        return False
    if not isinstance(obj.get("verifier_version"), str) or not obj["verifier_version"]:
        return False
    if obj.get("committed") is not True:
        return False
    bc = obj.get("bars_committed")
    if isinstance(bc, bool) or not isinstance(bc, int) or bc <= 0:
        return False
    if not isinstance(obj.get("forward_start_ts"), str) or not obj["forward_start_ts"]:
        return False
    pins = obj.get("append_only_digests")
    if not isinstance(pins, dict):
        return False
    for name in LEDGER_JSONL_FILES:
        info = pins.get(name)
        if not isinstance(info, dict):
            return False
        if (
            isinstance(info.get("bytes"), bool)
            or not isinstance(info.get("bytes"), int)
            or info["bytes"] < 0
            or isinstance(info.get("lines"), bool)
            or not isinstance(info.get("lines"), int)
            or info["lines"] < 0
            or not isinstance(info.get("sha256"), str)
            or not info["sha256"]
            or not isinstance(info.get("present"), bool)
        ):
            return False
    return True


def _append_only_failures(
    inputs: Path,
    baseline: dict[str, Any] | None,
    current: dict[str, dict[str, Any]],
) -> list[str]:
    """Append-only immutability of the SNAPSHOT ledgers vs the trusted OK baseline (Blocker 2/5).

    The trusted baseline (preserved across corrupt runs) pinned per ledger ``{bytes, lines,
    sha256}`` over RAW bytes. A later run is a non-append mutation — and fails closed as CORRUPT —
    if any previously-trusted ledger:

      - is now absent/unreadable;
      - shrank below the trusted byte length (truncation);
      - lost lines (rows removed);
      - whose trusted byte prefix no longer hashes identically (a reorder, an in-place edit, or a
        whitespace-only rewrite that re-encodes the same JSON values).

    A legitimate append (more bytes, identical prefix, line count not decreased) is allowed and is
    re-validated in full by the caller's reconcile/state suite. Comparing against the trusted
    baseline (not the previous report) means a CORRUPT run does not reset the comparison: tampering
    detected once stays detected until the corruption is resolved.
    """
    if not isinstance(baseline, dict):
        return []
    pinned = baseline.get("append_only_digests")
    if not isinstance(pinned, dict):
        return []

    failures: list[str] = []
    for name, info in pinned.items():
        if not isinstance(info, dict):
            continue
        # A ledger that was ABSENT at the trusted baseline carries no append-only constraint: it
        # may legitimately appear later with appended rows (e.g. the funding ledger gains its
        # first rows once a position is held). Skip it (its content is fully re-validated by
        # reconcile/state).
        if not info.get("present"):
            continue
        p_bytes = info.get("bytes")
        p_lines = info.get("lines")
        p_sha = info.get("sha256")
        if not isinstance(p_bytes, int) or p_bytes < 0 or not isinstance(p_sha, str):
            continue
        cur = current.get(name)
        if cur is None or not cur.get("present"):
            failures.append(
                f"{name}: trusted at the last verifier OK but is now unreadable/absent "
                f"(non-append mutation since the trusted baseline)"
            )
            continue
        if cur["bytes"] < p_bytes:
            failures.append(
                f"{name}: truncated to {cur['bytes']} byte(s) below the trusted "
                f"{p_bytes} (append-only ledger shrank since the trusted baseline)"
            )
            continue
        if isinstance(p_lines, int) and cur["lines"] < p_lines:
            failures.append(
                f"{name}: line count fell to {cur['lines']} below the trusted "
                f"{p_lines} (rows removed since the trusted baseline)"
            )
            continue
        try:
            prefix = (inputs / name).read_bytes()[:p_bytes]
        except OSError as exc:
            failures.append(
                f"{name}: cannot re-read the snapshot to verify the append-only prefix "
                f"({type(exc).__name__}: {exc})"
            )
            continue
        if hashlib.sha256(prefix).hexdigest() != p_sha:
            failures.append(
                f"{name}: the trusted {p_bytes}-byte prefix changed (raw-byte digest "
                f"mismatch — an append-only artifact was rewritten/reordered/truncated since the "
                f"trusted baseline)"
            )
    return failures


def _exact_byte_failures(
    baseline: dict[str, Any] | None,
    snap_digests: dict[str, dict[str, Any]],
    bars_committed: int,
) -> list[str]:
    """Exact-byte immutability of the non-ledger authority artifacts vs the baseline (Blocker 5).

    The append-only check covers the six ledgers. This covers the other two authority artifacts
    whose append-only logic does not apply:

      - ``paper_config.json`` is WRITE-ONCE, so ANY byte change since the trusted baseline (incl.
        a whitespace-only reformat that re-encodes the same values and keeps config_hash valid) is
        corruption.
      - ``paper_position_state.json`` is overwritten each run, so it legitimately changes when a
        new bar commits. But while the ledgers have NOT advanced (``bars_committed`` unchanged from
        the baseline) a byte change is a rewrite/reformat of the committed state — a whitespace-only
        rewrite that keeps the same values (which the content reconcile would otherwise pass) is
        caught here.
    """
    if not isinstance(baseline, dict):
        return []
    prior = baseline.get("output_digests")
    if not isinstance(prior, dict):
        return []
    failures: list[str] = []
    cfg_prior = prior.get("paper_config.json")
    cfg_now = snap_digests.get("paper_config.json", {}).get("sha256")
    if isinstance(cfg_prior, str) and cfg_now != cfg_prior:
        failures.append(
            "paper_config.json bytes changed since the trusted baseline (the write-once config "
            "was rewritten/reformatted — exact-byte mismatch)"
        )
    st_info = snap_digests.get(STATE_FILE, {})
    if bars_committed == baseline.get("bars_committed") and st_info.get("present"):
        st_prior = prior.get(STATE_FILE)
        st_now = st_info.get("sha256")
        if isinstance(st_prior, str) and st_now != st_prior:
            failures.append(
                f"{STATE_FILE} bytes changed without a new committed bar (the committed position "
                f"state was rewritten/reformatted since the trusted baseline — exact-byte "
                f"mismatch)"
            )
    return failures


def _verdict_line(status: str, n_failures: int) -> str:
    return {
        STATUS_OK: (
            "OK (simulation) — every paper artifact in the frozen snapshot re-validated and "
            "re-derived read-only, the ledgers reconcile and append-only-extend the trusted "
            "baseline; this is the authoritative paper status"
        ),
        STATUS_CORRUPT: (
            f"CORRUPT — {n_failures} integrity failure(s); the paper run is NOT trusted"
        ),
        STATUS_INCOMPLETE: (
            "INCOMPLETE — no committed paper run to certify yet (no eligible bars, or a run is "
            "in flight / crashed before its state caught up to the ledgers)"
        ),
        STATUS_RUNNING_STALE: (
            "RUNNING_STALE — a runner RUNNING marker has outlived its window and the state never "
            "caught up to the ledgers; treat as a crashed run, NOT OK"
        ),
        STATUS_CONFIG_ERROR: (
            "CONFIG_ERROR — paper_config.json is stale/incompatible/unloadable; nothing can be "
            "verified against it"
        ),
        STATUS_NEEDS_BOOTSTRAP: (
            "NEEDS_BOOTSTRAP — committed ledgers exist but no trusted OK baseline has been "
            "established; re-run the verifier with --bootstrap after operator review to anchor "
            "trust. NOT a trusted result"
        ),
        STATUS_VERIFYING: (
            "VERIFYING — a verification is in flight (or crashed before its terminal write); this "
            "is NOT a trusted result"
        ),
    }[status]


def _verifying_report(out: Path, forward_start_ts: str, now: datetime) -> dict[str, Any]:
    """The minimal in-flight pointer marker written first (supersedes any stale prior OK)."""
    return {
        "schema_version": SCHEMA_VERSION,
        "verifier_version": VERIFIER_VERSION,
        "baseline_label": BASELINE_LABEL,
        "authoritative": True,
        "verified_at": _now_utc_str(now),
        "output_dir": str(out),
        "forward_start_ts": forward_start_ts,
        "status": STATUS_VERIFYING,
        "committed": False,
        "bars_committed": 0,
        "failure_count": 0,
        "failures": [],
        "current_verdict": _verdict_line(STATUS_VERIFYING, 0),
        "disclaimer": DISCLAIMER,
    }


def verify(
    output_dir: Path | None = None,
    *,
    now: datetime | None = None,
    running_stale_after: timedelta | None = None,
    bootstrap: bool = False,
    _during_snapshot_hook: Callable[[Path], None] | None = None,
    _after_snapshot_hook: Callable[[Path], None] | None = None,
) -> dict[str, Any]:
    """Read-only verification of a paper_pnl_v1 output dir via a frozen verify-run snapshot.

    Snapshots the exact bytes of every input into ``verify_runs/<run_id>/inputs/``, verifies the
    FROZEN snapshot, writes the per-run report/receipt under ``verify_runs/<run_id>/``, updates the
    top-level pointer ``paper_verify_report.json`` (VERIFYING-first, terminal-last), and — only on
    ``OK`` — advances the preserved trusted baseline ``paper_verify_trusted_ok.json``. Never mutates
    any runner artifact.

    ``bootstrap`` permits establishing the first trusted baseline when committed ledgers exist but
    none has been anchored yet (otherwise that case is ``NEEDS_BOOTSTRAP``, never ``OK``).

    ``now`` / ``running_stale_after`` are injectable for deterministic tests.
    ``_during_snapshot_hook`` / ``_after_snapshot_hook`` are test-only seams (concurrent-mutation
    simulation); production callers never pass them.
    """
    out = Path(output_dir) if output_dir is not None else paper_output_dir()
    now = now or datetime.now(timezone.utc)
    stale_after = running_stale_after or timedelta(hours=DEFAULT_RUNNING_STALE_HOURS)

    # === TRUSTED BASELINE (preserved across corrupt runs; read before anything else) ======
    baseline, baseline_corrupt = _read_trusted_baseline(out / TRUSTED_OK_FILE)

    # === CONFIG CONTRACT of the LIVE config (for the forward_start_ts shown in VERIFYING) ===
    forward_start_ts = "unknown"
    try:
        forward_start_ts = load_config(out)["forward_start_ts"]
    except ConfigContractError:
        pass

    # === VERIFYING POINTER (atomic, FIRST write — supersedes any stale prior OK pointer) ====
    ledger.write_json_atomic(out / REPORT_FILE, _verifying_report(out, forward_start_ts, now))

    # === FROZEN SNAPSHOT of every input (Blocker 1/5) =====================================
    run_id = _run_id(now)
    run_dir = out / VERIFY_RUNS_DIRNAME / run_id
    inputs = run_dir / INPUTS_DIRNAME
    snap_digests, unstable = _snapshot_inputs(
        out, inputs, during_snapshot_hook=_during_snapshot_hook
    )
    if _after_snapshot_hook is not None:
        _after_snapshot_hook(out)

    # From here on EVERY read is against the frozen snapshot dir `inputs`, never the live `out`.
    # === CONFIG CONTRACT (snapshot) =======================================================
    config_error: str | None = None
    try:
        config = load_config(inputs)
        forward_start_ts = config["forward_start_ts"]
    except ConfigContractError as exc:
        config_error = str(exc)

    # === PARSE + DEEP SHAPE VALIDATION of the snapshot artifacts (fail closed) =============
    parse_failures: list[str] = []
    rows_by_file: dict[str, list[dict[str, Any]]] = {}
    for fname in LEDGER_JSONL_FILES:
        try:
            rows_by_file[fname] = read_ledger_validated(inputs, fname)
        except (LedgerCorruptionError, OSError) as exc:
            parse_failures.append(str(exc))

    state: dict[str, Any] | None = None
    try:
        state = ledger.read_state_obj(inputs / STATE_FILE)
    except (LedgerCorruptionError, OSError) as exc:
        parse_failures.append(str(exc))

    runner_summary_status = "absent"
    summary_started_at: datetime | None = None
    try:
        summ = ledger.read_summary_obj(inputs / SUMMARY_FILE)
        if summ:
            runner_summary_status = str(summ.get("status", "absent"))
            summary_started_at = _parse_started_at(summ.get("started_at"))
    except (LedgerCorruptionError, OSError) as exc:
        parse_failures.append(str(exc))

    # Raw-byte digests of the authoritative snapshot artifacts (recorded in the report + pinned
    # into the trusted baseline on OK).
    ledger_raw = {name: snap_digests[name] for name in LEDGER_JSONL_FILES}
    output_digests = {name: snap_digests[name]["sha256"] for name in _SNAPSHOT_FILES}

    # === COMMITTED-NESS (derived from the snapshot LEDGERS, never the summary's OK) =========
    equity_rows = rows_by_file.get("paper_equity.jsonl", [])
    bars_committed = len(equity_rows)
    committed = False
    if not config_error and not parse_failures and state is not None and equity_rows:
        latest_equity_ts = max(e["bar_ts"] for e in equity_rows)
        committed = state.get("watermark_bar_ts") == latest_equity_ts

    # === FULL READ-ONLY RE-DERIVATION over the snapshot ===================================
    validation_failures: list[str] = []
    if not config_error and not parse_failures:
        validation_failures += reconcile(inputs)
        validation_failures += reconcile_state_against_ledgers(
            inputs, require_committed=committed
        )
        validation_failures += _append_only_failures(inputs, baseline, ledger_raw)
        validation_failures += _exact_byte_failures(baseline, snap_digests, bars_committed)

    # === SNAPSHOT STABILITY (Blocker 1) ===================================================
    snapshot_failures: list[str] = []
    for name in unstable:
        snapshot_failures.append(
            f"{name}: live bytes changed during the input snapshot (concurrent mutation — the "
            f"frozen snapshot cannot be trusted; refusing OK)"
        )

    # === TRUSTED-BASELINE INTEGRITY (Blocker 2/3) =========================================
    baseline_failures: list[str] = []
    if baseline_corrupt:
        baseline_failures.append(
            f"{TRUSTED_OK_FILE} exists but is unreadable/corrupt/malformed (the preserved trusted "
            f"OK baseline was damaged or tampered — refusing to reset trust)"
        )

    all_failures = (
        snapshot_failures
        + parse_failures
        + validation_failures
        + baseline_failures
    )

    # === STATUS DECISION ==================================================================
    if config_error:
        status = STATUS_CONFIG_ERROR
        all_failures = [config_error] + all_failures
    elif all_failures:
        status = STATUS_CORRUPT
    elif not equity_rows:
        # Nothing committed to certify yet (fresh dir / NO_ELIGIBLE_BARS_YET / observer not past
        # forward_start_ts). Clean, but not an OK accounting result. No bootstrap needed.
        status = STATUS_INCOMPLETE
    elif not committed:
        if (
            runner_summary_status == "RUNNING"
            and summary_started_at is not None
            and (now - summary_started_at) > stale_after
        ):
            status = STATUS_RUNNING_STALE
        else:
            status = STATUS_INCOMPLETE
    elif baseline is None and not bootstrap:
        # Committed, clean, append-only-consistent — but no trusted baseline anchors it and this
        # was not an explicit bootstrap. Refuse to silently establish trust (Blocker 3).
        status = STATUS_NEEDS_BOOTSTRAP
    else:
        status = STATUS_OK

    # Per-ledger raw-byte pins for the trusted baseline (only persisted on OK below).
    append_only_digests = {
        name: {
            "bytes": info["bytes"],
            "lines": info["lines"],
            "sha256": info["sha256"],
            "present": info["present"],
        }
        for name, info in ledger_raw.items()
    }

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "verifier_version": VERIFIER_VERSION,
        "baseline_label": BASELINE_LABEL,
        "authoritative": True,
        "verified_at": _now_utc_str(now),
        "output_dir": str(out),
        "run_id": run_id,
        "verify_run_dir": str(Path(VERIFY_RUNS_DIRNAME) / run_id),
        "bootstrap": bool(bootstrap),
        "trusted_baseline_present": baseline is not None,
        "forward_start_ts": forward_start_ts,
        "status": status,
        "committed": committed,
        "bars_committed": bars_committed,
        "failure_count": len(all_failures),
        "failures": list(all_failures),
        # The runner's own summary status is RECORDED for operators but is NOT trusted as the
        # source of the verdict above (it is a runner convenience artifact only).
        "runner_summary_status": runner_summary_status,
        "output_digests": output_digests,
        "append_only_digests": append_only_digests,
        "current_verdict": _verdict_line(status, len(all_failures)),
        "disclaimer": DISCLAIMER,
    }

    # === PUBLISH ==========================================================================
    # 1. Per-run terminal report + receipt inside the frozen verify-run dir (immutable record).
    ledger.write_text_atomic(run_dir / RECEIPT_FILE, _render_receipt(report))
    ledger.write_json_atomic(run_dir / REPORT_FILE, report)
    # 2. Advance the preserved trusted baseline ONLY on OK (a non-OK run never touches it).
    if status == STATUS_OK:
        ledger.write_json_atomic(out / TRUSTED_OK_FILE, _trusted_baseline(report))
    # 3. Update the top-level pointer to the latest terminal report (receipt first, report last;
    #    a failure before the report write leaves the pointer at VERIFYING, never a stale OK).
    ledger.write_text_atomic(out / RECEIPT_FILE, _render_receipt(report))
    ledger.write_json_atomic(out / REPORT_FILE, report)
    # 4. Audit-only trail (NON-gating).
    ledger.append_rows(
        out / LOG_FILE,
        [{
            "verified_at": report["verified_at"],
            "run_id": run_id,
            "status": status,
            "committed": committed,
            "bars_committed": bars_committed,
            "failure_count": len(all_failures),
            "verifier_version": VERIFIER_VERSION,
        }],
    )
    return report


def _trusted_baseline(report: dict[str, Any]) -> dict[str, Any]:
    """The preserved trusted-OK baseline written from an OK report (Blocker 2)."""
    return {
        "schema_version": SCHEMA_VERSION,
        "verifier_version": VERIFIER_VERSION,
        "baseline_label": BASELINE_LABEL,
        "status": STATUS_OK,
        "verified_at": report["verified_at"],
        "run_id": report["run_id"],
        "verify_run_dir": report["verify_run_dir"],
        "forward_start_ts": report["forward_start_ts"],
        "committed": True,
        "bars_committed": report["bars_committed"],
        "append_only_digests": report["append_only_digests"],
        "output_digests": report["output_digests"],
        "disclaimer": DISCLAIMER,
    }


def _render_receipt(report: dict[str, Any]) -> str:
    status = report["status"]
    icon = {
        STATUS_OK: "✅",
        STATUS_CORRUPT: "🛑",
        STATUS_INCOMPLETE: "⏳",
        STATUS_RUNNING_STALE: "🛑",
        STATUS_CONFIG_ERROR: "🛑",
        STATUS_NEEDS_BOOTSTRAP: "⏳",
        STATUS_VERIFYING: "⏳",
    }.get(status, "❓")
    lines = [
        "# Paper PnL v1 — Verifier Receipt (AUTHORITATIVE)",
        "",
        f"> **{report['disclaimer']}**",
        "",
        f"## {icon} {status}",
        "",
        "- The latest `paper_verify_report.json` is the **authoritative** paper status, produced "
        "from a frozen verify-run snapshot. `paper_pnl_summary.json`, `paper_receipt.md`, and "
        "`paper_provenance.json` from the runner are convenience artifacts only and are NOT proof "
        "of an OK run. This verifier verifies (digest-seals) the snapshotted ledgers; it does not "
        "cryptographically sign them.",
        f"- Verified (UTC): {report['verified_at']}",
        f"- Verifier version: {report['verifier_version']}",
        f"- Verify-run snapshot: {report['verify_run_dir']}/",
        f"- Bootstrap run: {report['bootstrap']}",
        f"- Trusted baseline present: {report['trusted_baseline_present']}",
        f"- forward_start_ts: {report['forward_start_ts']}",
        f"- Committed bars (equity rows): {report['bars_committed']}",
        f"- Ledgers committed/at-rest: {report['committed']}",
        f"- Runner summary status (observed, not trusted): {report['runner_summary_status']}",
        f"- Verdict: {report['current_verdict']}",
        "",
    ]
    if report["failures"]:
        lines.append(f"## Failures ({report['failure_count']})")
        for f in report["failures"]:
            lines.append(f"- {f}")
        lines.append("")
    return "\n".join(lines)
