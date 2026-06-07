"""Tests for the authoritative, read-only paper verifier (quantbot.paper.verify).

Authority model (§ 5a): the runner only appends accounting artifacts and maintains a convenience
status; the verifier is the only component that publishes an authoritative
OK/CORRUPT/INCOMPLETE/RUNNING_STALE/CONFIG_ERROR status, written VERIFYING-first and committed
last. These tests exercise the adversarial cases the multi-file TOCTOU loop kept losing:

  Blocker 1 (false OK via TOCTOU): a trade/equity/state mutation DURING verification => CORRUPT.
  Blocker 2 (stale OK survives a failed run): a receipt-write failure / malformed ledger / config
    error after a prior verifier OK => the visible report is never a stale OK.
  Blocker 3 (append-only digest bypass): a whitespace-only rewrite / truncation / reorder / orphan
    append of a previously-verified ledger => next verify CORRUPT (raw-byte digests).
  Blocker 4 (missing/corrupt prior report): a removed/corrupt authoritative report over committed
    ledgers => not OK; a fresh empty dir => INCOMPLETE, never OK.
  Plus: corrupt ledger / malformed state / runner stale OK ignored / stale config / running-stale.
"""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from quantbot.paper import ledger as _ledger
from quantbot.paper.verify import (
    LOG_FILE,
    REPORT_FILE,
    STATUS_CONFIG_ERROR,
    STATUS_CORRUPT,
    STATUS_INCOMPLETE,
    STATUS_OK,
    STATUS_RUNNING_STALE,
    STATUS_VERIFYING,
    verify,
)

# Reuse the clean-run fixtures from the main paper test module.
from tests.test_paper_pnl import (  # noqa: E402
    NOW,
    TS,
    _read,
    _rewrite_jsonl,
    _setup,
)


def _clean_run(tmp_path):
    """A clean OK accounting run: one round-trip AAA trade, fully committed by the runner."""
    out, _fwd, _summary = _setup(tmp_path, [[], ["AAA"], ["AAA"], [], [], []])
    return out


def _report_on_disk(out: Path) -> dict:
    return json.loads((out / REPORT_FILE).read_text())


# --------------------------------------------------------------------------- clean OK


def test_clean_runner_output_verifies_ok(tmp_path):
    out = _clean_run(tmp_path)
    report = verify(out)
    assert report["status"] == STATUS_OK, report["failures"]
    assert report["authoritative"] is True
    assert report["committed"] is True
    assert report["bars_committed"] >= 1
    # The report and receipt are published; the report is the authoritative artifact.
    assert (out / REPORT_FILE).exists()
    assert (out / "paper_verify_receipt.md").exists()
    assert (out / LOG_FILE).exists()
    # Raw-byte append-only pins are recorded for the next verification (Blocker 3).
    pins = report["append_only_digests"]["paper_equity.jsonl"]
    assert set(pins) >= {"bytes", "lines", "sha256"}
    assert pins["sha256"] == hashlib.sha256((out / "paper_equity.jsonl").read_bytes()).hexdigest()


# ------------------------------------------------- Blocker 1: false OK via TOCTOU during verify


def _byte_mutator(rel: str):
    """A pre-commit hook that flips the raw bytes of one artifact mid-verification."""

    def _hook(out: Path) -> None:
        p = out / rel
        p.write_bytes(p.read_bytes() + b"\n")

    return _hook


def test_mutate_trade_during_verification_is_corrupt(tmp_path):
    out = _clean_run(tmp_path)
    report = verify(out, _pre_commit_hook=_byte_mutator("paper_trades.jsonl"))
    assert report["status"] == STATUS_CORRUPT
    assert any("during verification" in f for f in report["failures"])
    assert _report_on_disk(out)["status"] != STATUS_OK


def test_mutate_equity_during_verification_is_corrupt(tmp_path):
    out = _clean_run(tmp_path)
    report = verify(out, _pre_commit_hook=_byte_mutator("paper_equity.jsonl"))
    assert report["status"] == STATUS_CORRUPT
    assert any("during verification" in f for f in report["failures"])


def test_mutate_state_during_verification_is_corrupt(tmp_path):
    out = _clean_run(tmp_path)
    report = verify(out, _pre_commit_hook=_byte_mutator("paper_position_state.json"))
    assert report["status"] == STATUS_CORRUPT
    assert any("during verification" in f for f in report["failures"])


def test_concurrent_runner_summary_rewrite_does_not_break_ok(tmp_path):
    """A runner-convenience file (summary) is NOT in the TOCTOU gate; rewriting it keeps OK."""
    out = _clean_run(tmp_path)

    def _touch_summary(o: Path) -> None:
        p = o / "paper_pnl_summary.json"
        p.write_bytes(p.read_bytes() + b"\n")

    report = verify(out, _pre_commit_hook=_touch_summary)
    assert report["status"] == STATUS_OK, report["failures"]


# ------------------------------------------------- Blocker 2: stale OK must not survive a failure


def test_prev_ok_then_receipt_write_failure_visible_report_not_ok(tmp_path, monkeypatch):
    out = _clean_run(tmp_path)
    assert verify(out)["status"] == STATUS_OK

    def _boom(path, text):
        raise RuntimeError("injected receipt write failure")

    monkeypatch.setattr(_ledger, "write_text_atomic", _boom)
    with pytest.raises(RuntimeError):
        verify(out)
    # The VERIFYING marker was written first; the receipt failure aborts before the terminal
    # report write, so the visible authoritative status is VERIFYING, never a stale OK.
    on_disk = _report_on_disk(out)
    assert on_disk["status"] != STATUS_OK
    assert on_disk["status"] == STATUS_VERIFYING


def test_prev_ok_then_malformed_ledger_visible_report_not_ok(tmp_path):
    out = _clean_run(tmp_path)
    assert verify(out)["status"] == STATUS_OK
    (out / "paper_equity.jsonl").write_text("{not valid json}\n", encoding="utf-8")
    report = verify(out)
    assert report["status"] in (STATUS_CORRUPT, STATUS_VERIFYING)
    assert report["status"] != STATUS_OK
    assert _report_on_disk(out)["status"] != STATUS_OK


def test_prev_ok_then_config_error_visible_report_not_ok(tmp_path):
    out = _clean_run(tmp_path)
    assert verify(out)["status"] == STATUS_OK
    cfg = json.loads((out / "paper_config.json").read_text())
    cfg["engine_version"] = "0.1.0"
    (out / "paper_config.json").write_text(json.dumps(cfg), encoding="utf-8")
    report = verify(out)
    assert report["status"] in (STATUS_CONFIG_ERROR, STATUS_VERIFYING)
    assert report["status"] != STATUS_OK
    assert _report_on_disk(out)["status"] != STATUS_OK


# --------------------------------------------------------------------------- corrupt ledger


def test_corrupt_ledger_verifies_corrupt(tmp_path):
    out = _clean_run(tmp_path)
    assert verify(out)["status"] == STATUS_OK
    (out / "paper_equity.jsonl").write_text("{not valid json}\n", encoding="utf-8")
    report = verify(out)
    assert report["status"] == STATUS_CORRUPT
    assert report["failure_count"] >= 1


def test_malformed_state_verifies_corrupt(tmp_path):
    out = _clean_run(tmp_path)
    assert verify(out)["status"] == STATUS_OK
    # A present-but-empty `{}` state is corrupt, not "absent".
    (out / "paper_position_state.json").write_text("{}", encoding="utf-8")
    report = verify(out)
    assert report["status"] == STATUS_CORRUPT
    assert any("state" in f.lower() or "watermark" in f.lower() for f in report["failures"])


def test_modified_trade_after_runner_verifies_corrupt(tmp_path):
    out = _clean_run(tmp_path)
    assert verify(out)["status"] == STATUS_OK
    trades = _read(out / "paper_trades.jsonl")
    assert trades, "clean run should have at least one closed trade"
    # Tamper net_pnl so it no longer equals gross - fees - funding.
    trades[-1]["net_pnl"] = trades[-1]["net_pnl"] + 1234.5
    _rewrite_jsonl(out / "paper_trades.jsonl", trades)
    report = verify(out)
    assert report["status"] == STATUS_CORRUPT
    assert any("net_pnl" in f for f in report["failures"])


# --------------------------------------------------------------------------- runner stale OK ignored


def test_runner_stale_ok_summary_is_ignored(tmp_path):
    """A summary claiming OK over absent/empty ledgers must NOT yield a verifier OK."""
    out = tmp_path / "paper"
    out.mkdir(parents=True)
    from quantbot.paper.config import build_config, write_config_once

    write_config_once(build_config(forward_start_ts=TS[0]), output_dir=out)
    # A shape-valid OK summary, but NO ledger rows / state exist behind it.
    fake_ok = {
        "schema_version": 1,
        "status": "OK",
        "baseline_label": "fixed_notional_active_symbols_paper_v1",
        "baseline_note": "x",
        "forward_start_ts": TS[0],
        "bars_elapsed": 99,
        "closed_trades": 5,
        "winrate": 0.8,
        "realized_net_pnl": 100.0,
        "total_pnl": 100.0,
        "max_drawdown": 0.0,
        "profit_factor": 2.0,
        "expectancy": 20.0,
        "open_positions": [],
        "num_open": 0,
        "funding_gap": False,
        "funding_gap_count": 0,
        "current_verdict": "stale OK",
        "disclaimer": "SIMULATION ONLY.",
    }
    _ledger.write_json_atomic(out / "paper_pnl_summary.json", fake_ok)
    report = verify(out)
    # Verifier records the runner's claim but does not trust it.
    assert report["runner_summary_status"] == "OK"
    assert report["status"] != STATUS_OK
    assert report["status"] == STATUS_INCOMPLETE


# ------------------------------------------------- Blocker 3: append-only raw-byte digest pinning


def test_verifier_ok_then_modified_file_next_verify_corrupt(tmp_path):
    out = _clean_run(tmp_path)
    first = verify(out)
    assert first["status"] == STATUS_OK
    # Mutate a previously-verified equity row (tamper the stored equity value).
    equity = _read(out / "paper_equity.jsonl")
    equity[-1]["equity"] = equity[-1]["equity"] + 9999.0
    _rewrite_jsonl(out / "paper_equity.jsonl", equity)
    second = verify(out)
    assert second["status"] == STATUS_CORRUPT
    # Caught both by re-derivation (equity recompute) and append-only immutability.
    assert second["failure_count"] >= 1


def test_append_only_truncation_after_ok_is_corrupt(tmp_path):
    """Even an invariant-preserving truncation of a verified ledger is caught by digest pinning."""
    out = _clean_run(tmp_path)
    assert verify(out)["status"] == STATUS_OK
    snaps = _read(out / "paper_signal_snapshots.jsonl")
    assert len(snaps) >= 1
    # Drop the last verified snapshot row (a non-append mutation).
    _rewrite_jsonl(out / "paper_signal_snapshots.jsonl", snaps[:-1])
    report = verify(out)
    assert report["status"] == STATUS_CORRUPT


def test_whitespace_only_rewrite_after_ok_is_corrupt(tmp_path):
    """Re-encoding identical JSON values with different spacing still fails (raw-byte digest)."""
    out = _clean_run(tmp_path)
    assert verify(out)["status"] == STATUS_OK
    p = out / "paper_signal_snapshots.jsonl"
    rows = _read(p)
    # Same values, compact (non-canonical) spacing -> different raw bytes. The on-disk ledger
    # uses json default separators (", " / ": "); compact ("," / ":") re-encodes identically-
    # valued rows into different bytes.
    p.write_text(
        "".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in rows),
        encoding="utf-8",
    )
    report = verify(out)
    assert report["status"] == STATUS_CORRUPT
    assert any("after a verifier OK" in f for f in report["failures"])


def test_reorder_rows_after_ok_is_corrupt(tmp_path):
    out = _clean_run(tmp_path)
    assert verify(out)["status"] == STATUS_OK
    p = out / "paper_signal_snapshots.jsonl"
    rows = _read(p)
    assert len(rows) >= 2, "need >=2 rows to reorder"
    _rewrite_jsonl(p, list(reversed(rows)))
    assert verify(out)["status"] == STATUS_CORRUPT


def test_orphan_append_after_ok_is_corrupt(tmp_path):
    """Appending a structurally-valid but orphan equity row (no snapshot) fails re-derivation."""
    out = _clean_run(tmp_path)
    assert verify(out)["status"] == STATUS_OK
    equity = _read(out / "paper_equity.jsonl")
    rogue = dict(equity[-1])
    rogue["bar_ts"] = "2026-06-07T00:00:00"  # a later grid bar with NO consumed-signal snapshot
    with open(out / "paper_equity.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rogue, sort_keys=True) + "\n")
    report = verify(out)
    assert report["status"] == STATUS_CORRUPT


# ------------------------------------------------- Blocker 4: missing/corrupt prior report


def test_missing_prior_report_after_committed_ledgers_is_not_ok(tmp_path):
    out = _clean_run(tmp_path)
    assert verify(out)["status"] == STATUS_OK  # creates report + log
    (out / REPORT_FILE).unlink()
    report = verify(out)
    assert report["status"] != STATUS_OK
    assert report["status"] == STATUS_CORRUPT
    assert any("missing" in f and "verify_report" in f for f in report["failures"])


def test_corrupt_prior_report_after_committed_ledgers_is_corrupt(tmp_path):
    out = _clean_run(tmp_path)
    assert verify(out)["status"] == STATUS_OK
    (out / REPORT_FILE).write_text("{ not valid json", encoding="utf-8")
    report = verify(out)
    assert report["status"] == STATUS_CORRUPT
    assert any("verify_report" in f for f in report["failures"])


def test_fresh_empty_dir_is_incomplete_not_ok(tmp_path):
    out = tmp_path / "paper"
    out.mkdir(parents=True)
    from quantbot.paper.config import build_config, write_config_once

    write_config_once(build_config(forward_start_ts=TS[0]), output_dir=out)
    report = verify(out)
    assert report["status"] != STATUS_OK
    assert report["status"] == STATUS_INCOMPLETE


# --------------------------------------------------------------------------- stale config


def test_stale_incompatible_config_is_config_error(tmp_path):
    out = _clean_run(tmp_path)
    assert verify(out)["status"] == STATUS_OK
    # Simulate a stale/incompatible config (old engine version) left on the VM.
    cfg = json.loads((out / "paper_config.json").read_text())
    cfg["engine_version"] = "0.1.0"
    (out / "paper_config.json").write_text(json.dumps(cfg), encoding="utf-8")
    report = verify(out)
    assert report["status"] == STATUS_CONFIG_ERROR
    assert report["status"] != STATUS_OK


def test_config_hash_mutation_is_config_error(tmp_path):
    out = _clean_run(tmp_path)
    assert verify(out)["status"] == STATUS_OK
    # Mutate a hashed field without recomputing config_hash -> hash mismatch.
    cfg = json.loads((out / "paper_config.json").read_text())
    cfg["initial_equity_usd"] = cfg["initial_equity_usd"] + 1.0
    (out / "paper_config.json").write_text(json.dumps(cfg), encoding="utf-8")
    assert verify(out)["status"] == STATUS_CONFIG_ERROR


# --------------------------------------------------------------------------- running-stale


def test_running_marker_stale_is_running_stale(tmp_path):
    """A crashed run: equity rows exist but state lags, and the RUNNING marker has aged out."""
    out = _clean_run(tmp_path)
    assert verify(out)["status"] == STATUS_OK
    # Remove the committed state so the ledgers are no longer at-rest (mid-commit / crash).
    (out / "paper_position_state.json").unlink()
    # Leave a stale RUNNING marker.
    running = {
        "schema_version": 1,
        "status": "RUNNING",
        "baseline_label": "fixed_notional_active_symbols_paper_v1",
        "forward_start_ts": TS[0],
        "run_id": "deadbeef",
        "started_at": "2026-06-06T00:00:00Z",
        "phase": "preflight",
        "previous_watermark": "",
        "current_verdict": "RUNNING",
        "disclaimer": "SIMULATION ONLY.",
    }
    _ledger.write_json_atomic(out / "paper_pnl_summary.json", running)
    report = verify(
        out, now=datetime(2026, 6, 6, 16, 5, 0, tzinfo=timezone.utc),
        running_stale_after=timedelta(hours=1),
    )
    assert report["status"] == STATUS_RUNNING_STALE


# --------------------------------------------------------------------------- read-only guarantee


def test_verifier_does_not_mutate_runner_artifacts(tmp_path):
    out = _clean_run(tmp_path)
    runner_files = [
        "paper_fills.jsonl", "paper_trades.jsonl", "paper_funding.jsonl",
        "paper_positions.jsonl", "paper_equity.jsonl", "paper_signal_snapshots.jsonl",
        "paper_position_state.json", "paper_pnl_summary.json", "paper_config.json",
        "paper_provenance.json", "paper_receipt.md",
    ]
    before = {f: sha256(out / f) for f in runner_files}
    verify(out)
    after = {f: sha256(out / f) for f in runner_files}
    assert before == after, "verifier must not mutate any runner artifact"


# --------------------------------------------------------------------------- CLI exit codes


def test_cli_exit_codes_map_status(tmp_path, monkeypatch):
    """scripts/paper_verify.py maps the authoritative status to the documented exit code."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "paper_verify_cli",
        str(Path(__file__).resolve().parent.parent / "scripts" / "paper_verify.py"),
    )
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)

    out = _clean_run(tmp_path)
    assert cli.main(["--output-dir", str(out)]) == 0  # OK
    # Corrupt a ledger -> exit 4.
    (out / "paper_equity.jsonl").write_text("{not valid json}\n", encoding="utf-8")
    assert cli.main(["--output-dir", str(out)]) == 4


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
