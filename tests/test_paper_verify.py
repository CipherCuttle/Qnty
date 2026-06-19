"""Tests for the authoritative, read-only paper verifier (quantbot.paper.verify).

Authority model (§ 5a, verify-run snapshot model): the runner only appends accounting artifacts
and maintains a convenience status; the verifier is the only component that publishes an
authoritative status. Each invocation freezes the exact bytes of every input into
``verify_runs/<run_id>/inputs/``, verifies that FROZEN snapshot, updates the top-level pointer
``paper_verify_report.json``, and — only on OK — advances the separately-preserved trusted baseline
``paper_verify_trusted_ok.json``. These tests exercise the adversarial cases Codex rejected:

  Blocker 1 (TOCTOU false OK): a source mutation DURING the snapshot => not OK; a mutation AFTER
    the snapshot does not flip this run's verdict but the NEXT verify detects it.
  Blocker 2 (detected tampering forgotten): a CORRUPT run never overwrites the trusted baseline, so
    tampering detected once stays detected; a legitimate append is still accepted.
  Blocker 3 (prior report schema / bootstrap): a malformed trusted baseline => CORRUPT (never
    reset); committed ledgers with no baseline => NEEDS_BOOTSTRAP unless explicit --bootstrap.
  Blocker 4 (full re-derivation): fabricated fee / gross / funding / drawdown / exposure => CORRUPT.
  Blocker 5 (exact bytes): config / state / ledger whitespace rewrite after OK => CORRUPT.
"""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from quantbot.paper import ledger as _ledger
from quantbot.paper.config import build_config, write_config_once
from quantbot.paper.runner import run_once
from quantbot.paper.verify import (
    LOG_FILE,
    REPORT_FILE,
    TRUSTED_OK_FILE,
    STATUS_CONFIG_ERROR,
    STATUS_CORRUPT,
    STATUS_INCOMPLETE,
    STATUS_NEEDS_BOOTSTRAP,
    STATUS_OK,
    STATUS_RUNNING_STALE,
    STATUS_VERIFYING,
    verify,
)

# Reuse the clean-run fixtures from the main paper test module.
from tests.test_paper_pnl import (  # noqa: E402
    AAA_PRICES,
    NOW,
    TS,
    _bars,
    _funding_df,
    _obs,
    _read,
    _rewrite_jsonl,
    _setup,
    _write_obs,
)


def _clean_run(tmp_path):
    """A clean accounting run: one round-trip AAA trade, fully committed by the runner."""
    out, _fwd, _summary = _setup(tmp_path, [[], ["AAA"], ["AAA"], [], [], []])
    return out


def _bootstrapped(tmp_path):
    """A clean run with the trusted OK baseline already established."""
    out = _clean_run(tmp_path)
    assert verify(out, bootstrap=True)["status"] == STATUS_OK
    return out


def _report_on_disk(out: Path) -> dict:
    return json.loads((out / REPORT_FILE).read_text())


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --------------------------------------------------------------------------- clean OK


def test_clean_runner_output_verifies_ok(tmp_path):
    out = _clean_run(tmp_path)
    report = verify(out, bootstrap=True)
    assert report["status"] == STATUS_OK, report["failures"]
    assert report["authoritative"] is True
    assert report["committed"] is True
    assert report["bars_committed"] >= 1
    # The per-run snapshot dir, the pointer, the receipt, the trusted baseline, and the log exist.
    run_dir = out / report["verify_run_dir"]
    assert (run_dir / "inputs" / "paper_equity.jsonl").exists()
    assert (run_dir / REPORT_FILE).exists()
    assert (out / REPORT_FILE).exists()
    assert (out / "paper_verify_receipt.md").exists()
    assert (out / TRUSTED_OK_FILE).exists()
    assert (out / LOG_FILE).exists()
    # The snapshot is an EXACT byte copy of the live ledger.
    assert _sha(run_dir / "inputs" / "paper_equity.jsonl") == _sha(out / "paper_equity.jsonl")


def test_second_clean_verify_is_ok(tmp_path):
    out = _bootstrapped(tmp_path)
    assert verify(out)["status"] == STATUS_OK


# ----------------------------------------------- Blocker 1: TOCTOU via snapshot


def _byte_appender(rel: str):
    def _hook(live: Path) -> None:
        p = live / rel
        p.write_bytes(p.read_bytes() + b"\n")

    return _hook


def test_mutate_trade_during_snapshot_is_not_ok(tmp_path):
    """A source mutation DURING the input snapshot is detected (double-read) => not OK."""
    out = _clean_run(tmp_path)
    report = verify(
        out, bootstrap=True, _during_snapshot_hook=_byte_appender("paper_trades.jsonl")
    )
    assert report["status"] != STATUS_OK
    assert report["status"] == STATUS_CORRUPT
    assert any("during the input snapshot" in f for f in report["failures"])


def _net_pnl_tamperer(live: Path) -> None:
    p = live / "paper_trades.jsonl"
    rows = [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
    rows[-1]["net_pnl"] = rows[-1]["net_pnl"] + 1000.0
    p.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8")


def test_mutate_after_snapshot_ok_for_snapshot_then_next_verify_detects(tmp_path):
    """A mutation AFTER the snapshot does not flip THIS run; the NEXT verify detects the drift."""
    out = _bootstrapped(tmp_path)
    # This run snapshots the (clean) live files, then the hook tampers the LIVE trade ledger.
    report = verify(out, _after_snapshot_hook=_net_pnl_tamperer)
    assert report["status"] == STATUS_OK, report["failures"]
    # The frozen snapshot this run verified is still the clean copy.
    run_dir = out / report["verify_run_dir"]
    assert (run_dir / "inputs" / "paper_trades.jsonl").read_bytes() != (
        out / "paper_trades.jsonl"
    ).read_bytes()
    # The next verify snapshots the now-mutated live files and fails closed.
    nxt = verify(out)
    assert nxt["status"] == STATUS_CORRUPT


# ----------------------------------------------- Blocker 2: trusted baseline not forgotten


def test_whitespace_tamper_after_ok_stays_corrupt(tmp_path):
    """OK baseline -> whitespace rewrite of a ledger -> CORRUPT -> re-run unchanged -> still CORRUPT."""
    out = _bootstrapped(tmp_path)
    p = out / "paper_signal_snapshots.jsonl"
    rows = _read(p)
    # Same values, compact spacing -> different raw bytes (append-only prefix mismatch).
    p.write_text(
        "".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in rows),
        encoding="utf-8",
    )
    first = verify(out)
    assert first["status"] == STATUS_CORRUPT
    assert any("since the trusted baseline" in f for f in first["failures"])
    # The trusted baseline was NOT overwritten by the CORRUPT run, so re-running is still CORRUPT.
    second = verify(out)
    assert second["status"] == STATUS_CORRUPT


def test_truncate_ledger_after_ok_stays_corrupt(tmp_path):
    out = _bootstrapped(tmp_path)
    snaps = _read(out / "paper_signal_snapshots.jsonl")
    assert len(snaps) >= 1
    _rewrite_jsonl(out / "paper_signal_snapshots.jsonl", snaps[:-1])
    assert verify(out)["status"] == STATUS_CORRUPT
    # Trust baseline preserved -> still corrupt on the next run.
    assert verify(out)["status"] == STATUS_CORRUPT


def test_corrupt_run_does_not_advance_trusted_baseline(tmp_path):
    out = _bootstrapped(tmp_path)
    before = (out / TRUSTED_OK_FILE).read_bytes()
    equity = _read(out / "paper_equity.jsonl")
    equity[-1]["equity"] = equity[-1]["equity"] + 9999.0
    _rewrite_jsonl(out / "paper_equity.jsonl", equity)
    assert verify(out)["status"] == STATUS_CORRUPT
    assert (out / TRUSTED_OK_FILE).read_bytes() == before, "CORRUPT must not touch the baseline"


def test_legit_append_after_ok_is_accepted(tmp_path):
    """A genuine runner append (prefix preserved, reconcile/state pass) advances trust to OK."""
    out = tmp_path / "paper"
    fwd = tmp_path / "fwd"
    # Stage AAA funding CSV so the runner's pre-batch funding-coverage gate (§3.3) sees AAA
    # as COMPLETE (the production symbol set in the workspace ``data/`` has no AAA CSV).
    from tests.test_paper_pnl import _stage_aaa_csv  # noqa: WPS433
    _stage_aaa_csv(tmp_path / "data")
    write_config_once(build_config(forward_start_ts=TS[0]), output_dir=out)
    # Run 1: enter at T1 (fill T2), exit signal at T2 but withhold the T3 open -> T2 deferred,
    # so only T0,T1 commit.
    _write_obs(fwd, _obs([[], ["AAA"], []]))
    run_once(
        output_dir=out, forward_obs_dir=fwd,
        bars_by_symbol={"AAA": _bars(AAA_PRICES[:3])}, funding_df=_funding_df(),
        data_dir=tmp_path / "data",
        now=datetime(2026, 6, 5, 16, 5, 0, tzinfo=timezone.utc),
    )
    r1 = verify(out, bootstrap=True)
    assert r1["status"] == STATUS_OK, r1["failures"]
    n1 = r1["bars_committed"]
    eq_prefix = (out / "paper_equity.jsonl").read_bytes()
    # Run 2: now provide the T3 open -> T2,T3 process and APPEND (old rows unchanged).
    _write_obs(fwd, _obs([[], ["AAA"], [], []]))
    run_once(
        output_dir=out, forward_obs_dir=fwd,
        bars_by_symbol={"AAA": _bars(AAA_PRICES[:4])}, funding_df=_funding_df(),
        data_dir=tmp_path / "data",
        now=datetime(2026, 6, 6, 0, 5, 0, tzinfo=timezone.utc),
    )
    # The append preserved the verified prefix.
    assert (out / "paper_equity.jsonl").read_bytes().startswith(eq_prefix)
    r2 = verify(out)
    assert r2["status"] == STATUS_OK, r2["failures"]
    assert r2["bars_committed"] > n1


# ----------------------------------------------- Blocker 3: baseline schema / bootstrap


def test_missing_baseline_with_ledgers_needs_bootstrap(tmp_path):
    out = _clean_run(tmp_path)
    # No trusted baseline yet, no --bootstrap: committed ledgers are NOT auto-trusted.
    report = verify(out)
    assert report["status"] == STATUS_NEEDS_BOOTSTRAP
    assert report["status"] != STATUS_OK
    # Explicit bootstrap establishes it.
    assert verify(out, bootstrap=True)["status"] == STATUS_OK


def test_empty_trusted_baseline_is_corrupt(tmp_path):
    out = _bootstrapped(tmp_path)
    (out / TRUSTED_OK_FILE).write_text("{}", encoding="utf-8")
    report = verify(out)
    assert report["status"] == STATUS_CORRUPT
    assert any("trusted OK baseline" in f for f in report["failures"])


def test_corrupt_trusted_baseline_is_corrupt(tmp_path):
    out = _bootstrapped(tmp_path)
    (out / TRUSTED_OK_FILE).write_text("{ not valid json", encoding="utf-8")
    report = verify(out)
    assert report["status"] == STATUS_CORRUPT
    # A corrupt baseline must NOT be silently reset (bootstrap does not rescue it).
    assert verify(out, bootstrap=True)["status"] == STATUS_CORRUPT


def test_wrong_status_trusted_baseline_is_corrupt(tmp_path):
    out = _bootstrapped(tmp_path)
    base = json.loads((out / TRUSTED_OK_FILE).read_text())
    base["status"] = "CORRUPT"  # not an OK baseline
    (out / TRUSTED_OK_FILE).write_text(json.dumps(base), encoding="utf-8")
    assert verify(out)["status"] == STATUS_CORRUPT


def test_fresh_empty_dir_is_incomplete_not_ok(tmp_path):
    out = tmp_path / "paper"
    out.mkdir(parents=True)
    write_config_once(build_config(forward_start_ts=TS[0]), output_dir=out)
    report = verify(out, bootstrap=True)  # bootstrap requested, but nothing to certify
    assert report["status"] == STATUS_INCOMPLETE
    assert report["status"] != STATUS_OK


# ----------------------------------------------- Blocker 4: full accounting re-derivation


def _tamper_then_bootstrap(out: Path):
    """Verify a freshly-tampered dir in bootstrap mode (no baseline) so re-derivation is isolated
    from the append-only/exact-byte checks."""
    return verify(out, bootstrap=True)


def test_fabricated_fee_is_corrupt(tmp_path):
    out = _clean_run(tmp_path)
    fills = _read(out / "paper_fills.jsonl")
    fills[0]["fee"] = fills[0]["fee"] + 7.0
    _rewrite_jsonl(out / "paper_fills.jsonl", fills)
    report = _tamper_then_bootstrap(out)
    assert report["status"] == STATUS_CORRUPT
    assert any("fee" in f for f in report["failures"])


def test_fabricated_gross_pnl_is_corrupt(tmp_path):
    out = _clean_run(tmp_path)
    trades = _read(out / "paper_trades.jsonl")
    # Inflate gross AND net by the same amount so net = gross - fees - funding still holds.
    trades[-1]["gross_pnl"] = trades[-1]["gross_pnl"] + 500.0
    trades[-1]["net_pnl"] = trades[-1]["net_pnl"] + 500.0
    _rewrite_jsonl(out / "paper_trades.jsonl", trades)
    report = _tamper_then_bootstrap(out)
    assert report["status"] == STATUS_CORRUPT
    assert any("gross_pnl" in f for f in report["failures"])


def test_fabricated_funding_is_corrupt(tmp_path):
    out = _clean_run(tmp_path)
    funding = _read(out / "paper_funding.jsonl")
    assert funding
    funding[0]["funding_amount"] = funding[0]["funding_amount"] + 3.0
    _rewrite_jsonl(out / "paper_funding.jsonl", funding)
    report = _tamper_then_bootstrap(out)
    assert report["status"] == STATUS_CORRUPT
    assert any("funding" in f for f in report["failures"])


def test_fabricated_drawdown_is_corrupt(tmp_path):
    out = _clean_run(tmp_path)
    equity = _read(out / "paper_equity.jsonl")
    equity[-1]["drawdown"] = 0.5  # arbitrary in-range drawdown that does not match peak/equity
    _rewrite_jsonl(out / "paper_equity.jsonl", equity)
    report = _tamper_then_bootstrap(out)
    assert report["status"] == STATUS_CORRUPT
    assert any("drawdown" in f for f in report["failures"])


def test_fabricated_exposure_is_corrupt(tmp_path):
    out = _clean_run(tmp_path)
    positions = _read(out / "paper_positions.jsonl")
    # Pick a bar with an open position and inflate its exposure far beyond the open-book notional.
    idx = next(i for i, p in enumerate(positions) if p["num_open"] > 0)
    positions[idx]["gross_exposure_usd"] = positions[idx]["gross_exposure_usd"] + 1_000_000.0
    _rewrite_jsonl(out / "paper_positions.jsonl", positions)
    report = _tamper_then_bootstrap(out)
    assert report["status"] == STATUS_CORRUPT
    assert any("exposure" in f for f in report["failures"])


def test_modified_net_pnl_is_corrupt(tmp_path):
    out = _clean_run(tmp_path)
    trades = _read(out / "paper_trades.jsonl")
    trades[-1]["net_pnl"] = trades[-1]["net_pnl"] + 1234.5
    _rewrite_jsonl(out / "paper_trades.jsonl", trades)
    report = _tamper_then_bootstrap(out)
    assert report["status"] == STATUS_CORRUPT
    assert any("net_pnl" in f for f in report["failures"])


# ----------------------------------------------- Blocker 5: exact-byte protection


def test_config_whitespace_rewrite_after_ok_is_corrupt(tmp_path):
    out = _bootstrapped(tmp_path)
    cfg = json.loads((out / "paper_config.json").read_text())
    # Re-encode the SAME values with different spacing -> config_hash still valid, bytes differ.
    (out / "paper_config.json").write_text(
        json.dumps(cfg, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )
    report = verify(out)
    assert report["status"] == STATUS_CORRUPT
    assert any("paper_config.json bytes changed" in f for f in report["failures"])


def test_state_whitespace_rewrite_after_ok_is_corrupt(tmp_path):
    out = _bootstrapped(tmp_path)
    state = json.loads((out / "paper_position_state.json").read_text())
    # Same values, different bytes; no new committed bar -> a state rewrite is corruption.
    (out / "paper_position_state.json").write_text(
        json.dumps(state, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )
    report = verify(out)
    assert report["status"] == STATUS_CORRUPT
    assert any("paper_position_state.json bytes changed" in f for f in report["failures"])


def test_ledger_whitespace_rewrite_after_ok_is_corrupt(tmp_path):
    out = _bootstrapped(tmp_path)
    p = out / "paper_equity.jsonl"
    rows = _read(p)
    p.write_text(
        "".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in rows),
        encoding="utf-8",
    )
    assert verify(out)["status"] == STATUS_CORRUPT


# ----------------------------------------------- corrupt ledger / malformed state / config


def test_corrupt_ledger_verifies_corrupt(tmp_path):
    out = _bootstrapped(tmp_path)
    (out / "paper_equity.jsonl").write_text("{not valid json}\n", encoding="utf-8")
    report = verify(out)
    assert report["status"] == STATUS_CORRUPT
    assert report["failure_count"] >= 1


def test_malformed_state_verifies_corrupt(tmp_path):
    out = _bootstrapped(tmp_path)
    (out / "paper_position_state.json").write_text("{}", encoding="utf-8")
    report = verify(out)
    assert report["status"] == STATUS_CORRUPT


def test_stale_incompatible_config_is_config_error(tmp_path):
    out = _bootstrapped(tmp_path)
    cfg = json.loads((out / "paper_config.json").read_text())
    cfg["engine_version"] = "0.1.0"
    (out / "paper_config.json").write_text(json.dumps(cfg), encoding="utf-8")
    report = verify(out)
    assert report["status"] == STATUS_CONFIG_ERROR
    assert report["status"] != STATUS_OK


def test_config_hash_mutation_is_config_error(tmp_path):
    out = _bootstrapped(tmp_path)
    cfg = json.loads((out / "paper_config.json").read_text())
    cfg["initial_equity_usd"] = cfg["initial_equity_usd"] + 1.0
    (out / "paper_config.json").write_text(json.dumps(cfg), encoding="utf-8")
    assert verify(out)["status"] == STATUS_CONFIG_ERROR


# ----------------------------------------------- runner stale OK ignored


def test_runner_stale_ok_summary_is_ignored(tmp_path):
    """A summary claiming OK over absent/empty ledgers must NOT yield a verifier OK."""
    out = tmp_path / "paper"
    out.mkdir(parents=True)
    write_config_once(build_config(forward_start_ts=TS[0]), output_dir=out)
    fake_ok = {
        "schema_version": 1, "status": "OK",
        "baseline_label": "fixed_notional_active_symbols_paper_v1", "baseline_note": "x",
        "forward_start_ts": TS[0], "bars_elapsed": 99, "closed_trades": 5, "winrate": 0.8,
        "realized_net_pnl": 100.0, "total_pnl": 100.0, "max_drawdown": 0.0, "profit_factor": 2.0,
        "expectancy": 20.0, "open_positions": [], "num_open": 0, "funding_gap": False,
        "funding_gap_count": 0, "current_verdict": "stale OK", "disclaimer": "SIMULATION ONLY.",
    }
    _ledger.write_json_atomic(out / "paper_pnl_summary.json", fake_ok)
    report = verify(out, bootstrap=True)
    assert report["runner_summary_status"] == "OK"
    assert report["status"] != STATUS_OK
    assert report["status"] == STATUS_INCOMPLETE


# ----------------------------------------------- running-stale


def test_running_marker_stale_is_running_stale(tmp_path):
    out = _bootstrapped(tmp_path)
    (out / "paper_position_state.json").unlink()
    running = {
        "schema_version": 1, "status": "RUNNING",
        "baseline_label": "fixed_notional_active_symbols_paper_v1", "forward_start_ts": TS[0],
        "run_id": "deadbeef", "started_at": "2026-06-06T00:00:00Z", "phase": "preflight",
        "previous_watermark": "", "current_verdict": "RUNNING", "disclaimer": "SIMULATION ONLY.",
    }
    _ledger.write_json_atomic(out / "paper_pnl_summary.json", running)
    report = verify(
        out, now=datetime(2026, 6, 6, 16, 5, 0, tzinfo=timezone.utc),
        running_stale_after=timedelta(hours=1),
    )
    assert report["status"] == STATUS_RUNNING_STALE


# ----------------------------------------------- stale-OK pointer superseded


def test_receipt_write_failure_leaves_pointer_verifying_not_ok(tmp_path, monkeypatch):
    out = _bootstrapped(tmp_path)
    assert _report_on_disk(out)["status"] == STATUS_OK

    def _boom(path, text):
        raise RuntimeError("injected receipt write failure")

    monkeypatch.setattr(_ledger, "write_text_atomic", _boom)
    with pytest.raises(RuntimeError):
        verify(out)
    on_disk = _report_on_disk(out)
    assert on_disk["status"] != STATUS_OK
    assert on_disk["status"] == STATUS_VERIFYING


# ----------------------------------------------- read-only guarantee


def test_verifier_does_not_mutate_runner_artifacts(tmp_path):
    out = _clean_run(tmp_path)
    runner_files = [
        "paper_fills.jsonl", "paper_trades.jsonl", "paper_funding.jsonl",
        "paper_positions.jsonl", "paper_equity.jsonl", "paper_signal_snapshots.jsonl",
        "paper_position_state.json", "paper_pnl_summary.json", "paper_config.json",
        "paper_provenance.json", "paper_receipt.md",
    ]
    before = {f: _sha(out / f) for f in runner_files}
    verify(out, bootstrap=True)
    after = {f: _sha(out / f) for f in runner_files}
    assert before == after, "verifier must not mutate any runner artifact"


# ----------------------------------------------- CLI exit codes


def test_cli_exit_codes_map_status(tmp_path):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "paper_verify_cli",
        str(Path(__file__).resolve().parent.parent / "scripts" / "paper_verify.py"),
    )
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)

    out = _clean_run(tmp_path)
    # Committed ledgers, no baseline, no --bootstrap -> NEEDS_BOOTSTRAP (exit 5).
    assert cli.main(["--output-dir", str(out)]) == 5
    # Explicit bootstrap -> OK (exit 0).
    assert cli.main(["--output-dir", str(out), "--bootstrap"]) == 0
    # Corrupt a ledger -> exit 4.
    (out / "paper_equity.jsonl").write_text("{not valid json}\n", encoding="utf-8")
    assert cli.main(["--output-dir", str(out)]) == 4
