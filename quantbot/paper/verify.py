"""Authoritative, read-only verifier for paper_pnl_v1.

Authority model (see docs/paper_pnl_v1_schema.md § 5a):

  - The paper accounting **runner** (`quantbot.paper.runner`) is NOT the authority on `OK`. It
    only appends deterministic accounting artifacts (fills/trades/funding/positions/equity/
    snapshots + the position state) and may publish a *runner status* in
    `paper_pnl_summary.json`. That summary, `paper_receipt.md`, and `paper_provenance.json` are
    runner conveniences; they are NOT authoritative proof of a trusted run.
  - This **verifier** is the only component allowed to publish an authoritative
    `OK` / `CORRUPT` / `INCOMPLETE` / `RUNNING_STALE` / `CONFIG_ERROR` status. It reads every
    paper artifact read-only, re-derives the verdict from the ledgers themselves (never trusting
    the runner's summary status or its provenance manifest), pins the EXACT raw bytes of every
    authoritative artifact, and writes:
      * ``paper_verify_report.json``  — the single authoritative status,
      * ``paper_verify_receipt.md``   — a human receipt,
      * ``paper_verify_log.jsonl``    — an append-only audit trail of every verification.

Why this defeats the multi-file TOCTOU loop the runner kept losing:

  1. The verdict is a pure function of the on-disk artifacts AT VERIFY TIME. The verifier does
     not try to make the runner achieve cross-file Byzantine atomicity.
  2. The report is written ``VERIFYING`` FIRST — before any read that could fail — so a stale
     prior ``OK`` is superseded the instant a verification begins. If this run then fails (or
     crashes) before its terminal write, the visible status is ``VERIFYING``, never a stale
     ``OK``.
  3. Digests are taken over the EXACT raw bytes of each file (length + line count + sha256 of
     the whole file), not over re-canonicalized parsed rows. Rewriting bytes that decode to the
     same JSON values therefore still changes the digest.
  4. Immediately before the final ``OK`` is committed, the verifier RE-READS the exact bytes of
     every authoritative artifact and confirms they still match the digests the verdict was based
     on. If anything changed during verification, it publishes ``CORRUPT``, not ``OK``.
  5. The terminal report is written atomically LAST. If that write fails, no ``OK`` exists.
  6. Against this verifier's own prior ``OK`` report it enforces append-only immutability on the
     raw bytes: the current file must be at least as long, its line count must not decrease, and
     the previously-verified byte prefix must hash identically. A truncation, a reorder, or a
     whitespace-only rewrite of a previously-verified ledger fails closed.

A paper run is only trusted if THIS report says ``OK``.

The verifier is strictly read-only with respect to the runner's artifacts: it writes only its own
``paper_verify_*`` files.
"""

from __future__ import annotations

import hashlib
import json
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

VERIFIER_VERSION = "0.2.0"

REPORT_FILE = "paper_verify_report.json"
RECEIPT_FILE = "paper_verify_receipt.md"
LOG_FILE = "paper_verify_log.jsonl"

SUMMARY_FILE = "paper_pnl_summary.json"
STATE_FILE = "paper_position_state.json"

# A runner that left a `RUNNING` marker older than this (and whose state has not caught up to the
# ledgers) is treated as a crashed/abandoned run -> RUNNING_STALE, never OK.
DEFAULT_RUNNING_STALE_HOURS = 1.0

# Every paper artifact whose exact bytes the report pins (provenance for the verification). The
# runner-convenience files (summary/provenance/receipt) are recorded here but are NOT trusted for
# the verdict (Option B, § 5a) and are NOT part of the re-read TOCTOU gate below.
_DIGEST_ARTIFACTS = (
    "paper_config.json",
    "paper_fills.jsonl",
    "paper_positions.jsonl",
    "paper_trades.jsonl",
    "paper_equity.jsonl",
    "paper_funding.jsonl",
    "paper_signal_snapshots.jsonl",
    STATE_FILE,
    SUMMARY_FILE,
    "paper_provenance.json",
    "paper_receipt.md",
)

# The artifacts whose bytes actually determine the verdict. Only these are re-read immediately
# before the final OK (the TOCTOU gate): the config, the six append-only ledgers, and the
# position state. The runner-convenience files are intentionally excluded so a concurrent runner
# summary/receipt rewrite cannot flip a clean OK to CORRUPT.
_AUTHORITATIVE_ARTIFACTS = (
    "paper_config.json",
    *LEDGER_JSONL_FILES,
    STATE_FILE,
)

# Authoritative verifier statuses. OK is the only trusted verdict.
STATUS_OK = "OK"
STATUS_CORRUPT = "CORRUPT"
STATUS_INCOMPLETE = "INCOMPLETE"
STATUS_RUNNING_STALE = "RUNNING_STALE"
STATUS_CONFIG_ERROR = "CONFIG_ERROR"
# In-flight marker (never a trusted terminal verdict). Written FIRST so a crash/failure during
# verification leaves VERIFYING visible, never a stale OK.
STATUS_VERIFYING = "VERIFYING"


def _now_utc_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _raw_digest(path: Path) -> dict[str, Any]:
    """Digest the EXACT raw bytes of a file (Blocker 3).

    Returns ``{present, bytes, lines, sha256}``. ``sha256`` is the digest of the whole file's raw
    bytes (not of re-serialized parsed rows), so a whitespace-only rewrite that decodes to the
    same JSON still changes it. Absence/unreadability is recorded as a marker instead of raising
    (the verifier is read-only and must never traceback on a missing/locked artifact).
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


def _sha(path: Path) -> str:
    """Full-file raw-byte sha256 (or an absence/error marker) for ``output_digests``."""
    return _raw_digest(path)["sha256"]


def _parse_started_at(ts: Any) -> datetime | None:
    if not isinstance(ts, str):
        return None
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _read_prior_report(path: Path) -> tuple[dict[str, Any] | None, bool]:
    """Read THIS verifier's prior report fully guarded (never raises).

    Returns ``(report_or_None, corrupt)``:
      - ``(dict, False)``  — a parseable JSON object (any status, incl. a prior OK or VERIFYING).
      - ``(None, False)``  — the report is absent (a genuine first verification).
      - ``(None, True)``   — the file exists but is unreadable / not valid JSON / not an object
                             (the authoritative record was damaged or tampered — Blocker 4).

    Must run BEFORE the ``VERIFYING`` marker overwrites the file, so the prior report's pinned
    append-only digests and its presence are captured first.
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
    if not isinstance(obj, dict):
        return None, True
    return obj, False


def _verifying_report(out: Path, forward_start_ts: str) -> dict[str, Any]:
    """The minimal in-flight marker written first (supersedes any stale prior OK, Blocker 2)."""
    return {
        "schema_version": SCHEMA_VERSION,
        "verifier_version": VERIFIER_VERSION,
        "baseline_label": BASELINE_LABEL,
        "authoritative": True,
        "verified_at": _now_utc_str(),
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


def _append_only_failures(
    out: Path,
    prior_report: dict[str, Any] | None,
    current: dict[str, dict[str, Any]],
) -> list[str]:
    """Append-only immutability vs THIS verifier's prior `OK` report, over RAW bytes (Blocker 3).

    Once a verification pinned the append-only ledgers at `OK`, a later run must only have
    *appended* raw bytes to them. We pin per ledger ``{bytes, lines, sha256}`` where ``sha256`` is
    the digest of the whole raw file (== the digest of its first ``bytes`` bytes). A later run is
    a non-append mutation — and fails closed as CORRUPT — if any previously-verified ledger:

      - is now absent/unreadable;
      - shrank below the previously-verified byte length (truncation);
      - lost lines (rows removed);
      - whose previously-verified byte prefix no longer hashes identically (a reorder, an
        in-place edit, or a whitespace-only rewrite that re-encodes the same JSON values).

    A legitimate append (more bytes, identical prefix, line count not decreased) is allowed and is
    re-validated in full by the caller's reconcile/state suite. A missing/corrupt/non-OK prior
    report is handled separately (Blocker 4); here it simply yields no append-only constraint.
    """
    if not isinstance(prior_report, dict) or prior_report.get("status") != STATUS_OK:
        return []
    pinned = prior_report.get("append_only_digests")
    if not isinstance(pinned, dict):
        return []

    failures: list[str] = []
    for name, info in pinned.items():
        if not isinstance(info, dict):
            continue
        p_bytes = info.get("bytes")
        p_lines = info.get("lines")
        p_sha = info.get("sha256")
        if not isinstance(p_bytes, int) or p_bytes < 0 or not isinstance(p_sha, str):
            continue
        cur = current.get(name)
        if cur is None or not cur.get("present"):
            failures.append(
                f"{name}: verified OK previously but is now unreadable/absent "
                f"(non-append mutation after a verifier OK)"
            )
            continue
        if cur["bytes"] < p_bytes:
            failures.append(
                f"{name}: truncated to {cur['bytes']} byte(s) below the previously verified "
                f"{p_bytes} (append-only ledger shrank after a verifier OK)"
            )
            continue
        if isinstance(p_lines, int) and cur["lines"] < p_lines:
            failures.append(
                f"{name}: line count fell to {cur['lines']} below the previously verified "
                f"{p_lines} (rows removed after a verifier OK)"
            )
            continue
        try:
            prefix = (out / name).read_bytes()[:p_bytes]
        except OSError as exc:
            failures.append(
                f"{name}: cannot re-read to verify the append-only prefix "
                f"({type(exc).__name__}: {exc})"
            )
            continue
        if hashlib.sha256(prefix).hexdigest() != p_sha:
            failures.append(
                f"{name}: the previously verified {p_bytes}-byte prefix changed (raw-byte digest "
                f"mismatch — an append-only artifact was rewritten/reordered/truncated after a "
                f"verifier OK)"
            )
    return failures


def _verdict_line(status: str, n_failures: int) -> str:
    return {
        STATUS_OK: (
            "OK (simulation) — every paper artifact re-validated read-only, the ledgers "
            "reconcile, and the exact bytes were re-confirmed before commit; this is the "
            "authoritative paper status"
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
        STATUS_VERIFYING: (
            "VERIFYING — a verification is in flight (or crashed before its terminal write); this "
            "is NOT a trusted result"
        ),
    }[status]


def verify(
    output_dir: Path | None = None,
    *,
    now: datetime | None = None,
    running_stale_after: timedelta | None = None,
    _pre_commit_hook: Callable[[Path], None] | None = None,
) -> dict[str, Any]:
    """Read-only verification of a paper_pnl_v1 output dir. Returns the report dict.

    Writes ``paper_verify_report.json`` (authoritative), ``paper_verify_receipt.md``, and appends
    ``paper_verify_log.jsonl``. Never mutates any runner artifact.

    The on-disk report is overwritten with ``VERIFYING`` BEFORE any read that could fail, so a
    crash/exception mid-verification can never leave a stale ``OK`` visible. The terminal report
    is written atomically LAST; if that write fails, no terminal status (and in particular no
    ``OK``) is published.

    ``now`` and ``running_stale_after`` are injectable for deterministic tests.
    ``_pre_commit_hook`` is a test-only seam invoked immediately before the final re-read gate to
    simulate a concurrent mutation during verification; production callers never pass it.
    """
    out = Path(output_dir) if output_dir is not None else paper_output_dir()
    now = now or datetime.now(timezone.utc)
    stale_after = running_stale_after or timedelta(hours=DEFAULT_RUNNING_STALE_HOURS)

    # === PRIOR VERIFIER REPORT (read BEFORE we overwrite it) ============================
    # Captured first so we can (a) enforce append-only immutability against the digests a prior
    # OK pinned, and (b) detect that the authoritative record was removed/corrupted while
    # committed ledgers exist (Blocker 4). The log presence distinguishes a genuine first
    # verification (no prior report AND no prior log) from a removed report (log present).
    prior_report, prior_report_corrupt = _read_prior_report(out / REPORT_FILE)
    prior_log_present = (out / LOG_FILE).exists()

    # === CONFIG CONTRACT (read-only) ==================================================
    config_error: str | None = None
    forward_start_ts = "unknown"
    try:
        config = load_config(out)
        forward_start_ts = config["forward_start_ts"]
    except ConfigContractError as exc:
        config_error = str(exc)

    # === VERIFYING MARKER (atomic, FIRST write — supersedes any stale prior OK) ===========
    # From here on, the on-disk authoritative status is VERIFYING until a terminal report is
    # committed last. Any failure/crash before that leaves VERIFYING, never a stale OK (Blocker 2).
    ledger.write_json_atomic(out / REPORT_FILE, _verifying_report(out, forward_start_ts))

    # === PARSE + DEEP SHAPE VALIDATION of every persisted artifact (fail closed) ========
    parse_failures: list[str] = []
    rows_by_file: dict[str, list[dict[str, Any]]] = {}
    for fname in LEDGER_JSONL_FILES:
        try:
            rows_by_file[fname] = read_ledger_validated(out, fname)
        except (LedgerCorruptionError, OSError) as exc:
            parse_failures.append(str(exc))

    state: dict[str, Any] | None = None
    try:
        state = ledger.read_state_obj(out / STATE_FILE)
    except (LedgerCorruptionError, OSError) as exc:
        parse_failures.append(str(exc))

    runner_summary_status = "absent"
    summary_started_at: datetime | None = None
    try:
        summ = ledger.read_summary_obj(out / SUMMARY_FILE)
        if summ:
            runner_summary_status = str(summ.get("status", "absent"))
            summary_started_at = _parse_started_at(summ.get("started_at"))
    except (LedgerCorruptionError, OSError) as exc:
        parse_failures.append(str(exc))

    # === RAW-BYTE DIGESTS (Blocker 3) ==================================================
    # Taken now, over the exact bytes the verdict will be based on. The OK path re-reads these
    # immediately before commit to prove nothing drifted (Blocker 1).
    ledger_raw = {name: _raw_digest(out / name) for name in LEDGER_JSONL_FILES}
    output_digests = {name: _sha(out / name) for name in _DIGEST_ARTIFACTS}

    # === COMMITTED-NESS (derived from the LEDGERS, never the summary's OK) ==============
    equity_rows = rows_by_file.get("paper_equity.jsonl", [])
    bars_committed = len(equity_rows)
    committed = False
    if not config_error and not parse_failures and state is not None and equity_rows:
        latest_equity_ts = max(e["bar_ts"] for e in equity_rows)
        committed = state.get("watermark_bar_ts") == latest_equity_ts

    # === FULL READ-ONLY RE-DERIVATION =================================================
    validation_failures: list[str] = []
    if not config_error and not parse_failures:
        # Structural ledger invariants: schema, uniqueness/append-only, one snapshot per
        # consumed bar, bar_commit_id agreement, no fills before forward_start_ts, trade
        # net_pnl = gross - fees - funding, equity recomputation, funding ties to equity, etc.
        validation_failures += reconcile(out)
        # State tied to the ledgers. Strict lockstep only when the ledgers are at rest after a
        # commit (watermark == latest equity); a lagging state on a mid-commit run is allowed.
        validation_failures += reconcile_state_against_ledgers(
            out, require_committed=committed
        )
        # Append-only immutability vs this verifier's own prior OK report (raw bytes).
        validation_failures += _append_only_failures(out, prior_report, ledger_raw)

    # === PRIOR AUTHORITATIVE RECORD INTEGRITY (Blocker 4) ===============================
    # If committed ledgers exist but the authoritative report was removed (with a log proving
    # prior verifications) or corrupted, the verifier must NOT casually emit OK as if history were
    # clean. A genuine first verification (no prior report AND no prior log) is exempt.
    prior_history_failures: list[str] = []
    if equity_rows:
        if prior_report_corrupt:
            prior_history_failures.append(
                "paper_verify_report.json existed but was unreadable/corrupt while committed "
                "paper ledgers exist (the authoritative verifier record was damaged or tampered)"
            )
        elif prior_report is None and prior_log_present:
            prior_history_failures.append(
                "paper_verify_report.json is missing while paper_verify_log.jsonl records prior "
                "verification(s) over committed ledgers (the authoritative report was removed)"
            )

    all_failures = parse_failures + validation_failures + prior_history_failures

    # === STATUS DECISION ==============================================================
    if config_error:
        status = STATUS_CONFIG_ERROR
        all_failures = [config_error] + all_failures
    elif all_failures:
        status = STATUS_CORRUPT
    elif not equity_rows:
        # Nothing committed to certify yet (fresh dir / NO_ELIGIBLE_BARS_YET / observer not past
        # forward_start_ts). Clean, but not an OK accounting result.
        status = STATUS_INCOMPLETE
    elif not committed:
        # Equity rows exist but the state has not caught up to them: a run is in flight or
        # crashed mid-commit. If the runner's RUNNING marker has gone stale, flag it as such.
        if (
            runner_summary_status == "RUNNING"
            and summary_started_at is not None
            and (now - summary_started_at) > stale_after
        ):
            status = STATUS_RUNNING_STALE
        else:
            status = STATUS_INCOMPLETE
    else:
        status = STATUS_OK

    # === RE-READ TOCTOU GATE (Blocker 1) ==============================================
    # Immediately before committing OK, re-read the EXACT bytes of every authoritative artifact
    # and confirm they still match the digests the verdict was based on. Anything that mutated
    # during verification (a trade/equity/state/config edit that slipped in after reconcile)
    # makes the re-read digest disagree -> publish CORRUPT, never OK.
    if status == STATUS_OK:
        if _pre_commit_hook is not None:
            _pre_commit_hook(out)
        drift: list[str] = []
        for name in _AUTHORITATIVE_ARTIFACTS:
            if _sha(out / name) != output_digests[name]:
                drift.append(
                    f"{name}: bytes changed during verification (TOCTOU — the artifact was "
                    f"mutated after it was validated/digested; refusing to commit OK)"
                )
        if drift:
            status = STATUS_CORRUPT
            all_failures = all_failures + drift

    # Per-ledger raw-byte pins for the NEXT verification's append-only immutability check.
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
        "verified_at": _now_utc_str(),
        "output_dir": str(out),
        "forward_start_ts": forward_start_ts,
        "status": status,
        "committed": committed,
        "bars_committed": bars_committed,
        "failure_count": len(all_failures),
        "failures": list(all_failures),
        # The runner's own summary status is RECORDED for operators but is NOT trusted as the
        # source of the verdict above (it is a runner convenience artifact only). Likewise the
        # verifier does NOT consult paper_provenance.json for authority (Option B, § 5a).
        "runner_summary_status": runner_summary_status,
        "output_digests": output_digests,
        "append_only_digests": append_only_digests,
        "current_verdict": _verdict_line(status, len(all_failures)),
        "disclaimer": DISCLAIMER,
    }

    # === PUBLISH (the terminal report is the single authoritative status, written LAST) ====
    # Receipt + log are conveniences. The authoritative report is written atomically last, so a
    # failure writing the receipt (or anything before the report write) leaves the on-disk status
    # at VERIFYING, never a stale OK (Blocker 1/2). If the report write itself fails, no terminal
    # OK exists.
    ledger.write_text_atomic(out / RECEIPT_FILE, _render_receipt(report))
    ledger.write_json_atomic(out / REPORT_FILE, report)
    ledger.append_rows(
        out / LOG_FILE,
        [{
            "verified_at": report["verified_at"],
            "status": status,
            "committed": committed,
            "bars_committed": bars_committed,
            "failure_count": len(all_failures),
            "verifier_version": VERIFIER_VERSION,
        }],
    )
    return report


def _render_receipt(report: dict[str, Any]) -> str:
    status = report["status"]
    icon = {
        STATUS_OK: "✅",
        STATUS_CORRUPT: "🛑",
        STATUS_INCOMPLETE: "⏳",
        STATUS_RUNNING_STALE: "🛑",
        STATUS_CONFIG_ERROR: "🛑",
        STATUS_VERIFYING: "⏳",
    }.get(status, "❓")
    lines = [
        "# Paper PnL v1 — Verifier Receipt (AUTHORITATIVE)",
        "",
        f"> **{report['disclaimer']}**",
        "",
        f"## {icon} {status}",
        "",
        "- This report (`paper_verify_report.json`) is the **authoritative** paper status. "
        "`paper_pnl_summary.json`, `paper_receipt.md`, and `paper_provenance.json` from the "
        "runner are convenience artifacts only and are NOT proof of an OK run. This verifier "
        "verifies (digest-seals) the ledgers; it does not cryptographically sign them.",
        f"- Verified (UTC): {report['verified_at']}",
        f"- Verifier version: {report['verifier_version']}",
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
