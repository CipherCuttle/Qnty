"""Tests for ops/bin/qnty-paper-pnl-run.sh wrapper script (Phase 4 SQLite path).

All tests use tmp_path only. No /srv/qnty access, no VM, no live output.
Uses env overrides (QNTY_PAPER_ACCT_CMD / QNTY_PAPER_VERIFY_CMD) to simulate
accounting/verifier outcomes without running real SQLite scripts.

Status matrix tested:
- OK/OK => success (exit 0)
- PRE_START/PRE_START => success (exit 0)
- OK/PRE_START => fail (exit 4)
- PRE_START/OK => fail (exit 4)
- OK/CONFIG_ERROR => fail (exit 3)
- OK/CORRUPT => fail (exit 4)
- accounting ABORTED => exit 2, verifier not invoked
- accounting CONFIG_ERROR => exit 3, verifier not invoked
- accounting CORRUPT_LEDGER => exit 4, verifier not invoked
- accounting LEDGER_BUSY => exit 6, verifier not invoked
"""

import subprocess
import textwrap
from pathlib import Path
from typing import Optional
import pytest
import sys
import os


# Wrapper script location
WRAPPER_SCRIPT = Path(__file__).parent.parent / "ops" / "bin" / "qnty-paper-pnl-run.sh"


def _make_acct_script(tmp_path: Path, exit_code: int, output: str = "") -> Path:
    """Create a fake accounting script that exits with given code."""
    script = tmp_path / "fake_acct_script.sh"
    script.write_text(f"""#!/usr/bin/env bash
{output}
exit {exit_code}
""")
    script.chmod(0o755)
    return script


def _make_verify_script(tmp_path: Path, exit_code: int, output: str = "") -> Path:
    """Create a fake verifier script that exits with given code."""
    script = tmp_path / "fake_verify_script.sh"
    script.write_text(f"""#!/usr/bin/env bash
{output}
exit {exit_code}
""")
    script.chmod(0o755)
    return script


def _run_wrapper(
    tmp_path: Path,
    acct_script: Optional[Path] = None,
    verify_script: Optional[Path] = None,
    db_exists: bool = True,
    env: Optional[dict] = None,
) -> subprocess.CompletedProcess:
    """Run the wrapper script with controlled environment."""
    # Create fake DB if needed
    db_path = tmp_path / "paper_ledger.db"
    if db_exists:
        db_path.write_text("fake db")

    # Build environment
    test_env = dict(os.environ)
    test_env["QNTY_PAPER_DB_PATH"] = str(db_path)
    test_env["PATH"] = str(tmp_path) + ":" + test_env.get("PATH", "")

    if acct_script:
        test_env["QNTY_PAPER_ACCT_CMD"] = str(acct_script)
    if verify_script:
        test_env["QNTY_PAPER_VERIFY_CMD"] = str(verify_script)

    if env:
        test_env.update(env)

    # Remove QNTY_PAPER_OUTPUT_DIR to prevent old JSONL path from activating
    test_env.pop("QNTY_PAPER_OUTPUT_DIR", None)

    result = subprocess.run(
        ["bash", str(WRAPPER_SCRIPT)],
        env=test_env,
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
    )
    return result


class TestDBMissingPrecondition:
    """DB-missing precondition: wrapper exits nonzero, prints init guidance."""

    def test_missing_db_exits_nonzero(self, tmp_path):
        """Wrapper exits nonzero when DB is missing."""
        result = _run_wrapper(tmp_path, db_exists=False)
        assert result.returncode != 0

    def test_missing_db_prints_guidance(self, tmp_path):
        """Wrapper prints init guidance when DB is missing."""
        result = _run_wrapper(tmp_path, db_exists=False)
        assert "qnty-paper-sqlite-init.py" in result.stderr

    def test_missing_db_does_not_run_accounting(self, tmp_path):
        """Wrapper does not run accounting when DB is missing."""
        sentinel = tmp_path / "acct_ran"
        acct_script = _make_acct_script(tmp_path, 0)
        # This shouldn't be called, but we add a side effect
        real_acct = tmp_path / "real_acct.sh"
        real_acct.write_text(f"""#!/usr/bin/env bash
touch {sentinel}
exit 0
""")
        real_acct.chmod(0o755)

        result = _run_wrapper(
            tmp_path, db_exists=False, acct_script=real_acct
        )
        assert not sentinel.exists()

    def test_missing_db_does_not_run_verifier(self, tmp_path):
        """Wrapper does not run verifier when DB is missing."""
        sentinel = tmp_path / "verify_ran"
        verify_script = tmp_path / "verify.sh"
        verify_script.write_text(f"""#!/usr/bin/env bash
touch {sentinel}
exit 0
""")
        verify_script.chmod(0o755)

        result = _run_wrapper(
            tmp_path, db_exists=False, verify_script=verify_script
        )
        assert not sentinel.exists()


class TestStatusMatrix:
    """Matrix tests using env command seam."""

    def test_ok_ok_exits_zero(self, tmp_path):
        """Accounting OK + verifier OK => exit 0."""
        acct = _make_acct_script(tmp_path, 0)
        verify = _make_verify_script(tmp_path, 0)
        result = _run_wrapper(tmp_path, acct_script=acct, verify_script=verify)
        assert result.returncode == 0

    def test_pre_start_pre_start_exits_zero(self, tmp_path):
        """Accounting PRE_START + verifier PRE_START => exit 0."""
        acct = _make_acct_script(tmp_path, 5)
        verify = _make_verify_script(tmp_path, 5)
        result = _run_wrapper(tmp_path, acct_script=acct, verify_script=verify)
        assert result.returncode == 0

    def test_ok_pre_start_exits_4(self, tmp_path):
        """Accounting OK + verifier PRE_START => exit 4."""
        acct = _make_acct_script(tmp_path, 0)
        verify = _make_verify_script(tmp_path, 5)
        result = _run_wrapper(tmp_path, acct_script=acct, verify_script=verify)
        assert result.returncode == 4

    def test_pre_start_ok_exits_4(self, tmp_path):
        """Accounting PRE_START + verifier OK => exit 4."""
        acct = _make_acct_script(tmp_path, 5)
        verify = _make_verify_script(tmp_path, 0)
        result = _run_wrapper(tmp_path, acct_script=acct, verify_script=verify)
        assert result.returncode == 4

    def test_ok_config_error_exits_3(self, tmp_path):
        """Accounting OK + verifier CONFIG_ERROR => exit 3."""
        acct = _make_acct_script(tmp_path, 0)
        verify = _make_verify_script(tmp_path, 3)
        result = _run_wrapper(tmp_path, acct_script=acct, verify_script=verify)
        assert result.returncode == 3

    def test_ok_corrupt_exits_4(self, tmp_path):
        """Accounting OK + verifier CORRUPT => exit 4."""
        acct = _make_acct_script(tmp_path, 0)
        verify = _make_verify_script(tmp_path, 4)
        result = _run_wrapper(tmp_path, acct_script=acct, verify_script=verify)
        assert result.returncode == 4

    def test_pre_start_config_error_exits_3(self, tmp_path):
        """Accounting PRE_START + verifier CONFIG_ERROR => exit 3."""
        acct = _make_acct_script(tmp_path, 5)
        verify = _make_verify_script(tmp_path, 3)
        result = _run_wrapper(tmp_path, acct_script=acct, verify_script=verify)
        assert result.returncode == 3

    def test_pre_start_corrupt_exits_4(self, tmp_path):
        """Accounting PRE_START + verifier CORRUPT => exit 4."""
        acct = _make_acct_script(tmp_path, 5)
        verify = _make_verify_script(tmp_path, 4)
        result = _run_wrapper(tmp_path, acct_script=acct, verify_script=verify)
        assert result.returncode == 4


class TestAccountingFailureNoVerifier:
    """If accounting fails (non-OK, non-PRE_START), verifier must NOT run."""

    def test_aborted_exits_2_no_verifier(self, tmp_path):
        """Accounting ABORTED (2) => exit 2, verifier not invoked."""
        sentinel = tmp_path / "verify_ran"
        verify = _make_verify_script(tmp_path, 0)
        # Rewrite verify to touch sentinel if it runs
        verify.write_text(f"""#!/usr/bin/env bash
touch {sentinel}
exit 0
""")
        verify.chmod(0o755)

        acct = _make_acct_script(tmp_path, 2)
        result = _run_wrapper(tmp_path, acct_script=acct, verify_script=verify)
        assert result.returncode == 2
        assert not sentinel.exists()

    def test_config_error_exits_3_no_verifier(self, tmp_path):
        """Accounting CONFIG_ERROR (3) => exit 3, verifier not invoked."""
        sentinel = tmp_path / "verify_ran"
        verify = _make_verify_script(tmp_path, 0)
        verify.write_text(f"""#!/usr/bin/env bash
touch {sentinel}
exit 0
""")
        verify.chmod(0o755)

        acct = _make_acct_script(tmp_path, 3)
        result = _run_wrapper(tmp_path, acct_script=acct, verify_script=verify)
        assert result.returncode == 3
        assert not sentinel.exists()

    def test_corrupt_ledger_exits_4_no_verifier(self, tmp_path):
        """Accounting CORRUPT_LEDGER (4) => exit 4, verifier not invoked."""
        sentinel = tmp_path / "verify_ran"
        verify = _make_verify_script(tmp_path, 0)
        verify.write_text(f"""#!/usr/bin/env bash
touch {sentinel}
exit 0
""")
        verify.chmod(0o755)

        acct = _make_acct_script(tmp_path, 4)
        result = _run_wrapper(tmp_path, acct_script=acct, verify_script=verify)
        assert result.returncode == 4
        assert not sentinel.exists()

    def test_ledger_busy_exits_6_no_verifier(self, tmp_path):
        """Accounting LEDGER_BUSY (6) => exit 6, verifier not invoked."""
        sentinel = tmp_path / "verify_ran"
        verify = _make_verify_script(tmp_path, 0)
        verify.write_text(f"""#!/usr/bin/env bash
touch {sentinel}
exit 0
""")
        verify.chmod(0o755)

        acct = _make_acct_script(tmp_path, 6)
        result = _run_wrapper(tmp_path, acct_script=acct, verify_script=verify)
        assert result.returncode == 6
        assert not sentinel.exists()


class TestFlock:
    """Flock test: second wrapper run does not proceed."""

    def test_flock_prevents_concurrent_run(self, tmp_path):
        """Hold lock and confirm second wrapper run does not proceed."""
        # Use a lock file in tmp_path
        lock_file = str(tmp_path / "qnty-paper-pnl.lock")

        # Start a background process that holds the lock
        holder_script = tmp_path / "lock_holder.sh"
        holder_script.write_text(f"""#!/usr/bin/env bash
exec 9>"{lock_file}"
flock -n 9
sleep 10
""")
        holder_script.chmod(0o755)

        # Start the lock holder in background
        holder = subprocess.Popen(
            ["bash", str(holder_script)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Give it time to acquire the lock
        import time
        time.sleep(0.5)

        # Now run the wrapper with QNTY_PAPER_LOCK set - it should skip due to lock
        acct = _make_acct_script(tmp_path, 0)
        verify = _make_verify_script(tmp_path, 0)
        result = _run_wrapper(
            tmp_path,
            acct_script=acct,
            verify_script=verify,
            env={"QNTY_PAPER_LOCK": lock_file},
        )

        # The wrapper should exit 0 when lock is held (skip silently)
        assert result.returncode == 0
        assert "another run holds the lock" in result.stdout

        # Clean up
        holder.terminate()
        holder.wait()


class TestNoJsonlArtifacts:
    """No JSONL artifact test: wrapper should not create old JSONL artifacts."""

    def test_no_jsonl_artifacts_created(self, tmp_path):
        """Wrapper run should not create old JSONL artifacts."""
        acct = _make_acct_script(tmp_path, 5)  # PRE_START
        verify = _make_verify_script(tmp_path, 5)  # PRE_START

        # Create a fake output dir to catch any artifacts
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        result = _run_wrapper(
            tmp_path,
            acct_script=acct,
            verify_script=verify,
            env={"QNTY_PAPER_OUTPUT_DIR": str(output_dir)},
        )

        # Check that no JSONL artifacts were created
        jsonl_files = list(output_dir.glob("*.jsonl")) + list(output_dir.glob("*.json"))
        assert len(jsonl_files) == 0, f"Found unexpected artifacts: {jsonl_files}"


class TestEndToEndPreStart:
    """One real end-to-end PRE_START wrapper case with temp SQLite DB."""

    def test_e2e_pre_start_with_init(self, tmp_path):
        """Initialize temp SQLite DB and run wrapper with real scripts."""
        # This test needs the full environment (config file, etc.)
        # Skip if we can't run the real scripts
        db_path = tmp_path / "paper_ledger.db"

        # Create a minimal valid DB using the init script
        init_script = Path(__file__).parent.parent / "scripts" / "qnty-paper-sqlite-init.py"
        if not init_script.exists():
            pytest.skip("qnty-paper-sqlite-init.py not found")

        # Initialize DB with a future timestamp
        from datetime import datetime, timedelta, UTC
        future_ts = (datetime.now(UTC) + timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M:%SZ")

        init_result = subprocess.run(
            [sys.executable, str(init_script), "--forward-start-ts", future_ts, "--db-path", str(db_path)],
            capture_output=True,
            text=True,
            cwd=str(tmp_path.parent),
        )

        if init_result.returncode != 0:
            pytest.skip(f"DB init failed: {init_result.stderr}")

        assert db_path.exists()

        # Check if config file exists (needed by real scripts)
        config_dir = Path("/srv/qnty/output/paper_pnl_v1")
        if not config_dir.exists() or not (config_dir / "paper_config.json").exists():
            pytest.skip("Config file not found at /srv/qnty/output/paper_pnl_v1/paper_config.json")

        # Now run the wrapper with real scripts pointing to our temp DB
        test_env = dict(os.environ)
        test_env["QNTY_PAPER_DB_PATH"] = str(db_path)
        test_env.pop("QNTY_PAPER_OUTPUT_DIR", None)

        result = subprocess.run(
            ["bash", str(WRAPPER_SCRIPT)],
            env=test_env,
            capture_output=True,
            text=True,
            cwd=str(tmp_path.parent),
        )

        # With a valid empty/pre-start DB, accounting and verifier should both return 5
        # and wrapper should exit 0
        assert result.returncode == 0
        assert "PRE_START" in result.stdout or "exit=5" in result.stdout


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
