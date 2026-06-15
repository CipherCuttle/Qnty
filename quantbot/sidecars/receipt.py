"""Receipt assembly, host/service introspection, and atomic write for the sidecars.

Pure-ish assembly: builds the health and watchdog receipt dicts from already-read inputs and
records best-effort host/service context. Anything that may be unavailable locally (systemd,
disk/load) degrades to ``"unknown"`` rather than failing the receipt.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quantbot.paper.ledger import write_json_atomic
from quantbot.sidecars import SIDECAR_SCHEMA_VERSION

# Paper report fields surfaced verbatim into the health receipt.
PAPER_REPORT_FIELDS = (
    "status",
    "exit_code",
    "failure_count",
    "batches",
    "events",
    "equity_rows",
    "watermark_bar_ts",
)


def now_utc_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def working_tree_clean() -> bool | str:
    """True/False if the git working tree is clean; ``"unknown"`` if git is unavailable."""
    try:
        out = subprocess.check_output(
            ["git", "status", "--porcelain"], text=True, stderr=subprocess.DEVNULL
        )
        return out.strip() == ""
    except Exception:
        return "unknown"


def service_status(units: list[str]) -> dict[str, Any]:
    """Best-effort systemd introspection. ``"unknown"`` when systemctl is unavailable.

    Read-only: only ``systemctl show`` (no start/stop/enable). Returns ``ActiveState`` /
    ``SubState`` / ``Result`` per unit, or ``"unknown"`` for the whole map if systemctl is absent.
    """
    if shutil.which("systemctl") is None:
        return {unit: "unknown" for unit in units}

    result: dict[str, Any] = {}
    for unit in units:
        try:
            out = subprocess.check_output(
                ["systemctl", "show", unit,
                 "--property=ActiveState,SubState,Result,LoadState"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
            props = dict(
                line.split("=", 1) for line in out.splitlines() if "=" in line
            )
            result[unit] = props or "unknown"
        except Exception:
            result[unit] = "unknown"
    return result


def host_stats(disk_path: str | Path = "/") -> dict[str, Any]:
    """Best-effort host disk/load context. Fields degrade to ``"unknown"`` if unavailable."""
    stats: dict[str, Any] = {"disk_free_bytes": "unknown", "disk_total_bytes": "unknown",
                             "load_avg_1m": "unknown"}
    try:
        usage = shutil.disk_usage(str(disk_path))
        stats["disk_free_bytes"] = usage.free
        stats["disk_total_bytes"] = usage.total
    except Exception:
        pass
    try:
        stats["load_avg_1m"] = round(os.getloadavg()[0], 4)
    except (OSError, AttributeError):
        pass
    return stats


def build_health_receipt(
    *,
    generator_commit: str,
    expected_commit: str | None,
    paper_report: dict[str, Any] | None,
    paper_report_sha256: str | None,
    ledger_head: dict[str, Any] | None,
    ledger_physical: dict[str, Any] | None,
    services: dict[str, Any],
    host: dict[str, Any],
    overall: str,
    tree_clean: bool | str | None = None,
) -> dict[str, Any]:
    """Assemble the health receipt dict.

    ``commit_matches_expected`` is ``None`` when no expected commit was supplied (the common
    case — expected-commit is opt-in via CLI/env and never hardcoded into unit templates).
    """
    if expected_commit is None:
        commit_matches = None
    else:
        commit_matches = generator_commit == expected_commit

    report_view: dict[str, Any] = {}
    if paper_report is not None:
        report_view = {field: paper_report.get(field) for field in PAPER_REPORT_FIELDS}

    return {
        "receipt_type": "health",
        "schema_version": SIDECAR_SCHEMA_VERSION,
        "generated_at_utc": now_utc_str(),
        "generator_commit": generator_commit,
        "expected_commit": expected_commit,
        "commit_matches_expected": commit_matches,
        "working_tree_clean": working_tree_clean() if tree_clean is None else tree_clean,
        "paper_report": report_view,
        "paper_report_sha256": paper_report_sha256,
        "ledger_head": ledger_head,
        "ledger_physical": ledger_physical,
        "services": services,
        "host": host,
        "overall": overall,
    }


def build_watchdog_receipt(
    *,
    status: str,
    overall: str,
    detail: dict[str, Any],
    generator_commit: str,
) -> dict[str, Any]:
    """Assemble the watchdog receipt dict from an ``evaluate_watchdog`` detail map."""
    return {
        "receipt_type": "watchdog",
        "schema_version": SIDECAR_SCHEMA_VERSION,
        "generated_at_utc": now_utc_str(),
        "generator_commit": generator_commit,
        "status": status,
        "overall": overall,
        "now_utc": detail.get("now_utc"),
        "grace_minutes": detail.get("grace_minutes"),
        "latest_boundary": detail.get("latest_boundary"),
        "expected_min_watermark": detail.get("expected_min_watermark"),
        "observed_watermark": detail.get("observed_watermark"),
    }


def write_receipt(out_dir: str | Path, name: str, receipt: dict[str, Any]) -> Path:
    """Atomically write *receipt* as JSON to ``<out_dir>/<name>`` (creates the dir)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / name
    write_json_atomic(path, receipt)
    return path
