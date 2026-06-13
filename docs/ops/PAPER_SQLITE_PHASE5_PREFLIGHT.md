# Phase 5 SQLite Paper PnL VM Preflight Runbook

**Status:** Recovery planning after interrupted VM preflight. No recovery mutation executed.

**Approved implementation baseline (2026-06-11):**

- Branch: `feature/paper-pnl-v1`
- Reviewed implementation HEAD: `afcd149 Align SQLite paper verifier preflight gates`
- The current clean HEAD may be one later runbook-only baseline-attestation commit. Before VM
  reconnaissance, `git diff --name-only afcd149..HEAD` must print only
  `docs/ops/PAPER_SQLITE_PHASE5_PREFLIGHT.md`; any behavior-code difference is a hard stop.
- Full local suite: `996 passed, 0 skipped`
- Real wrapper -> accounting -> verifier `PRE_START` E2E passes on temporary paths
- SQLite writer/verifier/wrapper path is locally approved
- VM repo synced to `88bc7633c5282be0341acf07626113cc76e8d28c`; only this runbook differs
  from reviewed implementation HEAD `afcd149`
- VM reconnaissance found that the paper timer had run the SQLite wrapper automatically before
  the approved preflight; the timer is now contained as disabled/inactive
- Current `/srv/qnty/output/paper_pnl_v1` is provenance-contaminated accidental evidence and must
  not be used as clean preflight evidence
- No live trading or observer/shadow mutation occurred; no deployment readiness claimed

This runbook now records the interrupted preflight and defines a later, explicitly approved
recovery path. Commands under **Accidental automatic execution recovery branch** and
**VM preflight mutation plan** are future commands and were **not executed while authoring this
recovery patch**.

---

## 1. Scope and boundaries

- This is **paper simulation only**.
- No live trading, orders, exchange changes, wallet changes, or credentials.
- No observer, strategy, exchange, or order-code changes.
- The observer/shadow timer is observed only; it is never stopped, restarted, enabled, disabled,
  or otherwise touched.
- The paper timer remains disabled before, during, and after this preflight.
- The one manual wrapper run reads the observer output, writes the SQLite paper ledger DB/WAL/SHM,
  and lets the verifier publish `paper_verify_report.json`, `paper_verify_receipt.md`, and the
  audit-only `paper_verify_log.jsonl`. The report is authoritative for its recorded SQLite
  snapshot digest; the append-only audit log is non-gating and is not a paper ledger or trust
  authority.
- It must not generate legacy JSONL paper-ledger artifacts.
- Preflight setup creates a fresh SQLite DB and the required write-once `paper_config.json`;
  neither is a live-trading artifact.
- No stale JSONL data is imported into SQLite.
- No deployment, timer enablement, live readiness, or profitability claim follows from success.

**Hard boundary:** this runbook does not authorize enabling `qnty-paper-pnl.timer`. A later
proposal to enable it requires a separate review and explicit operator approval.

---

## 2. Local preflight gates

Run these locally from the Qnty repo before any VM action:

```bash
git status --short
git branch --show-current
git log --oneline -10
git diff --name-only afcd149..HEAD
bash -n ops/bin/qnty-paper-pnl-run.sh
PYTHONPATH=. pytest tests/test_paper_pnl_wrapper.py -v
PYTHONPATH=. pytest tests/test_paper_sqlite_writer.py -v
PYTHONPATH=. pytest tests/test_paper_sqlite_verify.py -v
PYTHONPATH=. pytest tests/test_paper_sqlite_verify_report.py -v
PYTHONPATH=. pytest tests/test_paper_sqlite.py -v
PYTHONPATH=. pytest tests/test_paper_pnl.py -q
PYTHONPATH=. pytest tests/test_paper_verify.py -v
PYTHONPATH=. pytest -q
find . \( -name 'paper_ledger.db' -o -name 'paper_ledger.db-wal' -o -name 'paper_ledger.db-shm' \) -print
```

Expected gates:

| Check | Required result |
| --- | --- |
| `git status --short` | No output: clean worktree |
| `git branch --show-current` | `feature/paper-pnl-v1` |
| `git log --oneline -10` | Reviewed implementation HEAD `afcd149` is present; current HEAD is either it or one runbook-only attestation commit |
| `git diff --name-only afcd149..HEAD` | No output, or only `docs/ops/PAPER_SQLITE_PHASE5_PREFLIGHT.md` |
| `bash -n` | Exit `0`, no output |
| Targeted tests | All pass |
| Full suite | All pass and `0 skipped` |
| DB artifact `find` | No output |

**Stop:** do not begin VM reconnaissance if any local gate fails, is skipped, or the approved
branch/commit changed without review.

---

## 3. VM read-only reconnaissance

> **READ-ONLY COMMAND SET.** Some reconnaissance commands were executed during the interrupted
> preflight and found the accidental automatic execution. Any approved rerun of this section
> remains read-only. Do not use `stop`, `start`, `enable`, `disable`, `mv`, `mkdir`, `install`,
> init scripts, or the wrapper here.

Run each command individually and preserve its output in the evidence pack:

```bash
# Paper timer/service: both must be inactive; timer must be disabled.
sudo systemctl is-enabled qnty-paper-pnl.timer || true
sudo systemctl is-active qnty-paper-pnl.timer || true
sudo systemctl is-active qnty-paper-pnl.service || true
sudo systemctl status qnty-paper-pnl.timer qnty-paper-pnl.service --no-pager || true

# Observer/shadow: timer must remain enabled and active.
sudo systemctl is-enabled qnty-shadow-run.timer || true
sudo systemctl is-active qnty-shadow-run.timer || true
sudo systemctl status qnty-shadow-run.timer qnty-shadow-run.service --no-pager || true

# Repo identity and worktree.
cd /srv/qnty/repo
git status --short
git branch --show-current
git rev-parse HEAD
git log -1 --oneline

# Effective unit definitions, users, groups, paths, and environment.
sudo systemctl cat qnty-paper-pnl.service qnty-paper-pnl.timer
sudo systemctl cat qnty-shadow-run.service qnty-shadow-run.timer
sudo systemctl show -p User,Group,WorkingDirectory,Environment qnty-paper-pnl.service
sudo systemctl show -p User,Group,WorkingDirectory,Environment qnty-shadow-run.service
getent passwd qnty || true
getent passwd viktor || true

# Existing paper output and observer output. These commands do not create either path.
sudo find /srv/qnty/output/paper_pnl_v1 -maxdepth 2 -printf '%M %u:%g %s %TY-%Tm-%TdT%TH:%TM:%TS %p\n' 2>/dev/null || true
sudo find /srv/qnty/output/forward_obs_v1 -maxdepth 1 -printf '%M %u:%g %s %TY-%Tm-%TdT%TH:%TM:%TS %p\n' 2>/dev/null | sort || true
sudo stat -c '%U:%G %a %n' /srv/qnty /srv/qnty/repo /srv/qnty/output /srv/qnty/output/forward_obs_v1 2>/dev/null || true
```

Required read-only findings:

- `qnty-paper-pnl.timer`: `disabled` and `inactive`.
- `qnty-paper-pnl.service`: `inactive`; it must not be running.
- `qnty-shadow-run.timer`: `enabled` and `active`.
- A oneshot `qnty-shadow-run.service` may be inactive between runs, but must not be failed.
- VM repo path is confirmed as `/srv/qnty/repo`, worktree is clean, and HEAD exactly matches the
  reviewed commit.
- The reviewed target commit already contains the SQLite wrapper path. This runbook has no deploy
  or checkout step; if the VM is still on the old JSONL wrapper commit, stop and obtain separate
  deployment approval.
- Effective `User=` and `Group=` for paper and shadow services match. The committed template uses
  `qnty`, while the existing VM may use a `viktor` drop-in. Any unresolved mismatch is a stop.
- `WorkingDirectory`, `QNTY_PAPER_DB_PATH`, paper output path, and the actual observer output path
  are understood before mutation.
- Existing `/srv/qnty/output/paper_pnl_v1/` contents are fully inventoried before archival.

**No mutation yet.** Present the reconnaissance evidence for operator review. If accidental
automatic execution is found, follow section 4 and do not continue directly to the generic
mutation plan. Otherwise, continue only after explicit approval for the mutation plan.

---

## 4. Accidental automatic execution recovery branch

Use this branch because reconnaissance found that `qnty-paper-pnl.timer` was unexpectedly
enabled/active and had already run the SQLite wrapper automatically:

- 2026-06-10 01:27 UTC: `PRE_START` / `PRE_START`
- 2026-06-10 08:20 UTC: `OK`, batch 1
- 2026-06-10 16:21 UTC: `OK`, batch 2
- 2026-06-11 00:21 UTC: `OK`, batch 3
- 2026-06-11 08:20 UTC: `OK`, batch 4

The timer has since been contained as disabled/inactive; the paper service was inactive at
inspection, and the shadow timer remained enabled/active. No live trading or observer/shadow
mutation occurred.

### 4.1 Classification and recovery boundary

- Classify `/srv/qnty/output/paper_pnl_v1` as **contaminated accidental preflight output**.
- Here, contaminated means **provenance-contaminated**, not necessarily SQLite-corrupt. Its
  initialization and automatic batches occurred outside the approved preflight session.
- Do not continue using the existing DB as clean preflight evidence.
- Do not delete, overwrite, import from, or reuse any accidental DB state.
- Avoid querying or opening SQLite before filesystem-level preservation. Opening SQLite can affect
  the WAL/SHM family even when the intended operation is read-only.
- Capture read-only filesystem, systemd, journal, and repo evidence first.
- Preserve the entire output directory intact, including DB/WAL/SHM and published artifacts, under
  `/srv/qnty/output/paper_pnl_v1.accidental-auto-run-<UTC_TIMESTAMP>`.
- Only under a separate approval, create a fresh empty output directory and initialize a fresh
  DB/config with a strictly future UTC 8-hour boundary.

Old journal output from before implementation HEAD `afcd149` may show matching
`PRE_START` / `PRE_START` followed by `VERIFIED OK`. Preserve that wording as historical evidence
from before the wrapper wording fix. Do not rewrite or otherwise "repair" old logs. Current wrapper
behavior reports matching pre-start status as `VERIFIED PRE_START`.

### 4.2 Read-only accidental-output evidence capture

> **FUTURE COMMANDS - READ-ONLY AND REQUIRE OPERATOR APPROVAL.** Run commands individually and
> preserve their outputs. Do not run SQLite, Python, init, wrapper, accounting, verifier, `mv`,
> `install`, or any systemctl mutation command in this stage.

```bash
# Paper and shadow state.
sudo systemctl is-enabled qnty-paper-pnl.timer || true
sudo systemctl is-active qnty-paper-pnl.timer || true
sudo systemctl is-active qnty-paper-pnl.service || true
sudo systemctl status qnty-paper-pnl.timer qnty-paper-pnl.service --no-pager || true
sudo systemctl is-enabled qnty-shadow-run.timer || true
sudo systemctl is-active qnty-shadow-run.timer || true
sudo systemctl status qnty-shadow-run.timer qnty-shadow-run.service --no-pager || true

# Unit definitions and effective settings.
sudo systemctl cat qnty-paper-pnl.service qnty-paper-pnl.timer
sudo systemctl cat qnty-shadow-run.service qnty-shadow-run.timer
sudo systemctl show qnty-paper-pnl.service qnty-paper-pnl.timer
sudo systemctl show qnty-shadow-run.service qnty-shadow-run.timer

# Historical automatic execution evidence. Preserve old wording exactly as recorded.
sudo journalctl --utc --since "2026-06-10 00:00:00 UTC" \
  -u qnty-paper-pnl.timer -u qnty-paper-pnl.service \
  -o short-iso-precise --no-pager

# Repo identity and worktree.
cd /srv/qnty/repo
git rev-parse HEAD
git status --short
git log -1 --oneline

# Filesystem-level accidental-output evidence. Do not query SQLite yet.
sudo find /srv/qnty/output/paper_pnl_v1 -maxdepth 1 \
  -printf '%M %u:%g %s %i %TY-%Tm-%TdT%TH:%TM:%TS %p\n' | sort
sudo find /srv/qnty/output/paper_pnl_v1 -maxdepth 1 -type f \
  -exec sha256sum -- {} + | sort
sudo lsof +D /srv/qnty/output/paper_pnl_v1 || true
sudo stat -c '%U:%G %a %n' \
  /srv/qnty /srv/qnty/repo /srv/qnty/output /srv/qnty/output/paper_pnl_v1

# Repeat inventory and hashes at the end; they must exactly match the first capture.
sudo find /srv/qnty/output/paper_pnl_v1 -maxdepth 1 \
  -printf '%M %u:%g %s %i %TY-%Tm-%TdT%TH:%TM:%TS %p\n' | sort
sudo find /srv/qnty/output/paper_pnl_v1 -maxdepth 1 -type f \
  -exec sha256sum -- {} + | sort
```

Required findings before archive approval:

- Paper timer is disabled/inactive and paper service is inactive.
- Shadow timer is enabled/active and neither shadow unit failed or changed.
- VM HEAD is exactly `88bc7633c5282be0341acf07626113cc76e8d28c` and the worktree is clean.
- Inventory and hashes cover the complete accidental output, including DB/WAL/SHM together.
- `lsof` shows no open handles anywhere under the paper output directory.
- Output inventory, hashes, timestamps, or ownership do not change during evidence capture.
- No SQLite DB query has been run during this evidence stage.

### 4.3 Later-approval archive/reset command plan

> **FUTURE COMMANDS - RUN ONLY UNDER A SEPARATE EXPLICIT OPERATOR APPROVAL.** This plan archives
> accidental evidence and creates fresh initialized state only. It stops before wrapper,
> accounting, verifier, timer execution, or any observer/shadow mutation.

```bash
set -euo pipefail

QNTY_PAPER_OUTPUT_DIR=/srv/qnty/output/paper_pnl_v1
QNTY_PAPER_DB_PATH=/srv/qnty/output/paper_pnl_v1/paper_ledger.db
RECOVERY_TS="$(date -u +%Y%m%dT%H%M%SZ)"
ACCIDENTAL_ARCHIVE_DIR="/srv/qnty/output/paper_pnl_v1.accidental-auto-run-${RECOVERY_TS}"
export QNTY_PAPER_OUTPUT_DIR QNTY_PAPER_DB_PATH RECOVERY_TS ACCIDENTAL_ARCHIVE_DIR

test "$(sudo systemctl is-enabled qnty-paper-pnl.timer 2>/dev/null || true)" = "disabled"
test "$(sudo systemctl is-active qnty-paper-pnl.timer 2>/dev/null || true)" = "inactive"
test "$(sudo systemctl is-active qnty-paper-pnl.service 2>/dev/null || true)" = "inactive"
test "$(sudo systemctl is-enabled qnty-shadow-run.timer 2>/dev/null || true)" = "enabled"
test "$(sudo systemctl is-active qnty-shadow-run.timer 2>/dev/null || true)" = "active"

PAPER_USER="$(sudo systemctl show -p User --value qnty-paper-pnl.service)"
PAPER_GROUP="$(sudo systemctl show -p Group --value qnty-paper-pnl.service)"
SHADOW_USER="$(sudo systemctl show -p User --value qnty-shadow-run.service)"
SHADOW_GROUP="$(sudo systemctl show -p Group --value qnty-shadow-run.service)"
test -n "$PAPER_USER"
test -n "$PAPER_GROUP"
test "$PAPER_USER" = "$SHADOW_USER"
test "$PAPER_GROUP" = "$SHADOW_GROUP"
test "$(dirname -- "$QNTY_PAPER_DB_PATH")" = "$QNTY_PAPER_OUTPUT_DIR"

OPEN_HANDLES="$(sudo lsof +D "$QNTY_PAPER_OUTPUT_DIR" 2>/dev/null || true)"
test -z "$OPEN_HANDLES"
test -d "$QNTY_PAPER_OUTPUT_DIR"
test ! -e "$ACCIDENTAL_ARCHIVE_DIR"

sudo mv "$QNTY_PAPER_OUTPUT_DIR" "$ACCIDENTAL_ARCHIVE_DIR"
sudo install -d -o "$PAPER_USER" -g "$PAPER_GROUP" -m 0750 "$QNTY_PAPER_OUTPUT_DIR"
sudo find "$QNTY_PAPER_OUTPUT_DIR" -maxdepth 1 -mindepth 1 -print
```

Expected: the archive destination did not previously exist, the entire accidental output directory
was moved intact, and the final `find` prints nothing. Preserve the archive permanently; never
import or reuse its DB state.

After the archive/reset commands pass, execute the reviewed fresh-boundary and initialization
steps in sections **5.4** and **5.5** only: choose a strictly future UTC 8-hour boundary, initialize
the fresh SQLite DB first, write matching config second, and confirm DB/config identity. Then stop.
Do not execute section **5.6**, accounting, verifier, wrapper, deployment, or any timer command.

---

## 5. VM preflight mutation plan

> **FUTURE COMMANDS - RUN ONLY AFTER EXPLICIT OPERATOR APPROVAL.**
>
> These steps intentionally do not enable or start the paper timer. Do not modify the
> observer/shadow service or timer.

For the accidental automatic execution scenario, complete the separately approved recovery branch
in section 4 and resume at section 5.4. Do not archive accidental evidence under the generic stale
output name in section 5.3.

### 5.1 Establish the approved session variables

Use the correct observer path found during reconnaissance. The expected path is shown below:

```bash
set -euo pipefail

cd /srv/qnty/repo

QNTY_PAPER_OUTPUT_DIR=/srv/qnty/output/paper_pnl_v1
QNTY_PAPER_DB_PATH=/srv/qnty/output/paper_pnl_v1/paper_ledger.db
QNTY_FORWARD_OBS_DIR=/srv/qnty/output/forward_obs_v1
export QNTY_PAPER_OUTPUT_DIR QNTY_PAPER_DB_PATH QNTY_FORWARD_OBS_DIR

PAPER_USER="$(sudo systemctl show -p User --value qnty-paper-pnl.service)"
PAPER_GROUP="$(sudo systemctl show -p Group --value qnty-paper-pnl.service)"
SHADOW_USER="$(sudo systemctl show -p User --value qnty-shadow-run.service)"
SHADOW_GROUP="$(sudo systemctl show -p Group --value qnty-shadow-run.service)"
export PAPER_USER PAPER_GROUP SHADOW_USER SHADOW_GROUP

test -n "$PAPER_USER"
test -n "$PAPER_GROUP"
test "$PAPER_USER" = "$SHADOW_USER"
test "$PAPER_GROUP" = "$SHADOW_GROUP"
getent passwd "$PAPER_USER"

test "$(dirname -- "$QNTY_PAPER_DB_PATH")" = "$QNTY_PAPER_OUTPUT_DIR"
test -d "$QNTY_FORWARD_OBS_DIR"
```

Expected:

- All `test` commands exit `0`.
- Paper and shadow effective user/group match.
- `dirname "$QNTY_PAPER_DB_PATH"` exactly equals `"$QNTY_PAPER_OUTPUT_DIR"`.
- The selected observer output directory already exists.

Stop on any mismatch. Do not compensate with ad hoc permissions or a unit edit during this
preflight. Resolve and review the mismatch separately.

### 5.2 Stop/confirm the paper timer remains disabled

```bash
sudo systemctl stop qnty-paper-pnl.timer
test "$(sudo systemctl is-enabled qnty-paper-pnl.timer 2>/dev/null || true)" = "disabled"
test "$(sudo systemctl is-active qnty-paper-pnl.timer 2>/dev/null || true)" = "inactive"
test "$(sudo systemctl is-active qnty-paper-pnl.service 2>/dev/null || true)" = "inactive"
```

Expected: every `test` exits `0`. If the timer is enabled unexpectedly, stop immediately; do not
run `systemctl disable` as an unreviewed repair.

### 5.3 Start the evidence transcript and archive stale paper output

```bash
PREFLIGHT_TS="$(date -u +%Y%m%dT%H%M%SZ)"
ARCHIVE_DIR="/srv/qnty/output/paper_pnl_v1.archived-${PREFLIGHT_TS}"
EVIDENCE_DIR="/srv/qnty/logs/paper-sqlite-phase5-preflight-${PREFLIGHT_TS}"
export PREFLIGHT_TS ARCHIVE_DIR EVIDENCE_DIR

sudo install -d -o "$(id -un)" -g "$(id -gn)" -m 0750 "$EVIDENCE_DIR"
script -q -f "$EVIDENCE_DIR/command-transcript.txt"
```

The `script` command starts a recorded subshell. Run the remaining commands inside it and type
`exit` only after the post-run checks or rollback are complete.

At the recorded-shell prompt, restore strict mode and confirm the exported session state:

```bash
set -euo pipefail
test -n "$PAPER_USER"
test -n "$PAPER_GROUP"
test -n "$ARCHIVE_DIR"
test -n "$EVIDENCE_DIR"
test "$(dirname -- "$QNTY_PAPER_DB_PATH")" = "$QNTY_PAPER_OUTPUT_DIR"
```

Archive the whole stale output family, then create a fresh directory:

```bash
if sudo test -e "$QNTY_PAPER_OUTPUT_DIR"; then
  sudo mv "$QNTY_PAPER_OUTPUT_DIR" "$ARCHIVE_DIR"
fi
sudo install -d -o "$PAPER_USER" -g "$PAPER_GROUP" -m 0750 "$QNTY_PAPER_OUTPUT_DIR"
sudo find "$QNTY_PAPER_OUTPUT_DIR" -maxdepth 1 -mindepth 1 -print
```

Expected: the final `find` prints nothing. Preserve `ARCHIVE_DIR`; do not delete it.

### 5.4 Choose a strictly future UTC 8-hour boundary

```bash
FORWARD_START_TS="$(
  /srv/qnty/venv/bin/python - <<'PY'
from datetime import datetime, timedelta, timezone

now = datetime.now(timezone.utc)
next_hour = ((now.hour // 8) + 1) * 8
if next_hour >= 24:
    boundary = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
else:
    boundary = now.replace(hour=next_hour, minute=0, second=0, microsecond=0)
print(boundary.strftime("%Y-%m-%dT%H:%M:%SZ"))
PY
)"
export FORWARD_START_TS
printf 'forward_start_ts=%s\n' "$FORWARD_START_TS"
```

Expected: timestamp ends in `T00:00:00Z`, `T08:00:00Z`, or `T16:00:00Z` and is strictly in the
future. Record it in the evidence pack.

### 5.5 Initialize the fresh DB, then the required write-once config

The order matters: SQLite init refuses legacy JSON/JSONL artifacts, including
`paper_config.json`, so initialize the DB first and write the matching config second.

```bash
sudo -u "$PAPER_USER" env \
  QNTY_PAPER_OUTPUT_DIR="$QNTY_PAPER_OUTPUT_DIR" \
  QNTY_PAPER_DB_PATH="$QNTY_PAPER_DB_PATH" \
  /srv/qnty/venv/bin/python scripts/qnty-paper-sqlite-init.py \
  --forward-start-ts "$FORWARD_START_TS" \
  2>"$EVIDENCE_DIR/sqlite-init.stderr" \
  | tee "$EVIDENCE_DIR/sqlite-init.stdout"

sudo -u "$PAPER_USER" env \
  QNTY_PAPER_OUTPUT_DIR="$QNTY_PAPER_OUTPUT_DIR" \
  /srv/qnty/venv/bin/python -m quantbot.paper.config \
  --forward-start-ts "$FORWARD_START_TS" \
  --output-dir "$QNTY_PAPER_OUTPUT_DIR" \
  2>"$EVIDENCE_DIR/paper-config-init.stderr" \
  | tee "$EVIDENCE_DIR/paper-config-init.stdout"
```

Expected:

- SQLite init exits `0` and prints JSON containing the DB path, schema version, engine version,
  `forward_start_ts`, `config_hash`, and `created_at`.
- Config init exits `0`, writes only `paper_config.json`, and prints the same
  `forward_start_ts` and `config_hash`.
- No `--force` option is used.

Confirm DB/config identity and path consistency:

```bash
sudo -u "$PAPER_USER" env \
  QNTY_PAPER_OUTPUT_DIR="$QNTY_PAPER_OUTPUT_DIR" \
  QNTY_PAPER_DB_PATH="$QNTY_PAPER_DB_PATH" \
  /srv/qnty/venv/bin/python - <<'PY' | tee "$EVIDENCE_DIR/db-config-identity.txt"
import json
import os
import sqlite3
from pathlib import Path

db_path = Path(os.environ["QNTY_PAPER_DB_PATH"])
output_dir = Path(os.environ["QNTY_PAPER_OUTPUT_DIR"])
assert db_path.parent == output_dir
with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
    row = conn.execute(
        "SELECT forward_start_ts, config_hash FROM paper_config WHERE id = 1"
    ).fetchone()
config = json.loads((output_dir / "paper_config.json").read_text(encoding="utf-8"))
assert row == (config["forward_start_ts"], config["config_hash"])
print(f"db_path={db_path}")
print(f"forward_start_ts={row[0]}")
print(f"config_hash={row[1]}")
print("db_config_identity=OK")
PY
```

Expected: `db_config_identity=OK`.

### 5.6 Run the wrapper manually once

```bash
set +e
sudo -u "$PAPER_USER" env \
  QNTY_PAPER_OUTPUT_DIR="$QNTY_PAPER_OUTPUT_DIR" \
  QNTY_PAPER_DB_PATH="$QNTY_PAPER_DB_PATH" \
  QNTY_FORWARD_OBS_DIR="$QNTY_FORWARD_OBS_DIR" \
  QNTY_PAPER_PYTHON=/srv/qnty/venv/bin/python \
  /srv/qnty/repo/ops/bin/qnty-paper-pnl-run.sh \
  >"$EVIDENCE_DIR/wrapper.stdout" \
  2>"$EVIDENCE_DIR/wrapper.stderr"
WRAPPER_RC=$?
set -e

printf 'wrapper_exit=%s\n' "$WRAPPER_RC" | tee "$EVIDENCE_DIR/wrapper.exit"
cat "$EVIDENCE_DIR/wrapper.stdout"
cat "$EVIDENCE_DIR/wrapper.stderr"
grep -E 'Status:|accounting exit=|verifier exit=|VERIFIED (OK|PRE_START)' "$EVIDENCE_DIR/wrapper.stdout" || true
```

Expected success is exactly one matching pair:

- Accounting `OK (0)` and verifier `OK (exit 0)`, wrapper exit `0`; or
- Accounting `PRE_START (5)` and verifier `PRE_START (exit 5)`, wrapper exit `0`.

The wrapper must not produce legacy JSONL paper-ledger artifacts. The verifier-owned
`paper_verify_log.jsonl` is expected audit-only output. Keep the paper timer disabled.

---

## 6. Success/failure matrix

| Accounting | Verifier | Wrapper exit | Preflight result |
| --- | --- | --- | --- |
| `OK` (`0`) | `OK` (`0`) | `0` | Success; preserve evidence for review |
| `PRE_START` (`5`) | `PRE_START` (`5`) | `0` | Success; preserve evidence for review |
| Any other result or mismatch | Any | Any | **Fail and stop** |

On any failure:

- Do not rerun until evidence is reviewed.
- Do not enable the paper timer.
- Preserve DB/WAL/SHM, config, stdout, stderr, and transcript.
- Run the rollback only after the operator chooses rollback.

---

## 7. Post-run inspection

Run after the one manual wrapper invocation, whether it succeeds or fails:

```bash
# List DB and optional SQLite-managed sidecars.
sudo ls -l "$QNTY_PAPER_DB_PATH" "$QNTY_PAPER_DB_PATH-wal" "$QNTY_PAPER_DB_PATH-shm" 2>/dev/null || true
sudo find "$QNTY_PAPER_OUTPUT_DIR" -maxdepth 1 -printf '%M %u:%g %s %TY-%Tm-%TdT%TH:%TM:%TS %p\n' | sort

# Run the read-only SQLite verifier manually and capture JSON stdout.
set +e
sudo -u "$PAPER_USER" env \
  QNTY_PAPER_DB_PATH="$QNTY_PAPER_DB_PATH" \
  /srv/qnty/venv/bin/python scripts/qnty-paper-sqlite-verify.py --json \
  >"$EVIDENCE_DIR/manual-verifier.json" \
  2>"$EVIDENCE_DIR/manual-verifier.stderr"
MANUAL_VERIFY_RC=$?
set -e
printf 'manual_verifier_exit=%s\n' "$MANUAL_VERIFY_RC" | tee "$EVIDENCE_DIR/manual-verifier.exit"
cat "$EVIDENCE_DIR/manual-verifier.json"
cat "$EVIDENCE_DIR/manual-verifier.stderr"

# No legacy JSONL-era paper-ledger output may have been generated. The verifier-owned
# paper_verify_log.jsonl is expected audit-only output and is intentionally not matched here.
sudo find "$QNTY_PAPER_OUTPUT_DIR" -maxdepth 1 -type f \( \
  -name 'paper_fills.jsonl' -o \
  -name 'paper_trades.jsonl' -o \
  -name 'paper_equity.jsonl' -o \
  -name 'paper_positions.jsonl' -o \
  -name 'paper_funding.jsonl' -o \
  -name 'paper_signal_snapshots.jsonl' -o \
  -name 'paper_pnl_summary.json' -o \
  -name 'paper_position_state.json' \
\) -print | tee "$EVIDENCE_DIR/unexpected-jsonl-era-artifacts.txt"
test ! -s "$EVIDENCE_DIR/unexpected-jsonl-era-artifacts.txt"

# Paper state must remain disabled/inactive; observer timer must remain enabled/active.
test "$(sudo systemctl is-enabled qnty-paper-pnl.timer 2>/dev/null || true)" = "disabled"
test "$(sudo systemctl is-active qnty-paper-pnl.timer 2>/dev/null || true)" = "inactive"
test "$(sudo systemctl is-active qnty-paper-pnl.service 2>/dev/null || true)" = "inactive"
test "$(sudo systemctl is-enabled qnty-shadow-run.timer 2>/dev/null || true)" = "enabled"
test "$(sudo systemctl is-active qnty-shadow-run.timer 2>/dev/null || true)" = "active"
sudo systemctl status qnty-paper-pnl.timer qnty-paper-pnl.service qnty-shadow-run.timer qnty-shadow-run.service --no-pager || true

# Repo and behavior code must remain unchanged.
cd /srv/qnty/repo
git rev-parse HEAD
git status --short
git diff --name-only -- quantbot scripts ops
```

Expected:

- Manual verifier returns the same `OK` (`0`) or `PRE_START` (`5`) status as the wrapper pair.
- Artifact listing contains `paper_config.json`, `paper_ledger.db`, optional SQLite-managed
  `paper_ledger.db-wal` / `paper_ledger.db-shm`, verifier-owned `paper_verify_report.json`,
  `paper_verify_receipt.md`, and audit-only `paper_verify_log.jsonl`; no legacy JSONL-era paper
  ledger artifacts.
- Paper timer/service state is unchanged; observer/shadow timer remains active and enabled.
- VM repo worktree remains clean; no strategy, observer, exchange, order, script, or ops files
  changed.

Any mismatch is a failure and hard stop.

---

## 8. Rollback

Rollback restores filesystem state only. It does not import JSONL into SQLite, enable timers, or
change observer/shadow state.

Run only after the operator explicitly chooses rollback:

```bash
set -euo pipefail

test "$(sudo systemctl is-enabled qnty-paper-pnl.timer 2>/dev/null || true)" = "disabled"
sudo systemctl stop qnty-paper-pnl.timer

ROLLBACK_TS="$(date -u +%Y%m%dT%H%M%SZ)"
FAILED_PREFLIGHT_DIR="/srv/qnty/output/paper_pnl_v1.preflight-${ROLLBACK_TS}"

sudo mv "$QNTY_PAPER_OUTPUT_DIR" "$FAILED_PREFLIGHT_DIR"
if sudo test -e "$ARCHIVE_DIR"; then
  sudo mv "$ARCHIVE_DIR" "$QNTY_PAPER_OUTPUT_DIR"
fi

sudo systemctl is-enabled qnty-paper-pnl.timer || true
sudo systemctl is-active qnty-paper-pnl.timer || true
sudo systemctl is-active qnty-shadow-run.timer || true
sudo find "$FAILED_PREFLIGHT_DIR" -maxdepth 1 -printf '%M %u:%g %s %p\n' | sort
sudo find "$QNTY_PAPER_OUTPUT_DIR" -maxdepth 1 -printf '%M %u:%g %s %p\n' 2>/dev/null | sort || true
```

Expected:

- Fresh preflight output is moved aside, never deleted.
- Archived JSONL-era output is restored if an archive existed.
- Paper timer remains disabled/inactive.
- Observer/shadow timer remains active and untouched.

Do not run a git revert on the VM. If review determines that the wrapper migration itself must be
reverted, do that in a separate local-only changeset after identifying all relevant commits with:

```bash
git log --oneline -- ops/bin/qnty-paper-pnl-run.sh
```

Review the resulting local revert and tests before any later deployment. Never import the archived
JSONL data into SQLite.

---

## 9. Hard stop conditions

Stop immediately and preserve evidence if any condition occurs:

- Local targeted or full suite is not green, or any test is skipped.
- Local or VM branch/commit/worktree differs from the approved state.
- VM does not already contain the reviewed SQLite wrapper code; deployment is outside this
  runbook.
- Paper timer or service becomes active.
- Observer/shadow timer or service is affected, failed, stopped, restarted, disabled, or changed.
- Paper and shadow effective service users/groups do not match, or ownership/permission risk is
  unresolved.
- Repo path, DB path, output path, observer path, or environment is unresolved or inconsistent.
- `dirname "$QNTY_PAPER_DB_PATH"` differs from `"$QNTY_PAPER_OUTPUT_DIR"`.
- Existing output was not inventoried or stale output was not archived intact.
- Any process holds the accidental DB/WAL/SHM or another file under the paper output directory
  open.
- Accidental output files, hashes, timestamps, ownership, or inventory change during evidence
  capture.
- The accidental DB/WAL/SHM family cannot be preserved together and archived intact.
- The selected accidental archive destination already exists.
- SQLite init/config identity, config hash, or `forward_start_ts` differs.
- The new `forward_start_ts` is not strictly future and on the UTC 8-hour grid.
- Wrapper returns anything except matching `OK`/`OK` exit `0` or
  `PRE_START`/`PRE_START` exit `0`.
- Accounting returns `ABORTED`, `CONFIG_ERROR`, `CORRUPT_LEDGER`, `LEDGER_BUSY`, or an unexpected
  code.
- Verifier returns `CONFIG_ERROR`, `CORRUPT`, or an unexpected code.
- Unexpected legacy JSONL-era paper-ledger artifacts are generated.
- VM repo or strategy/observer/exchange/order/script/ops files change.
- Any recovery step would require wrapper, accounting, verifier, deployment, timer enablement, or
  an unreviewed repair or unit edit.

---

## 10. Evidence pack

Collect and retain:

- Full command transcript: `command-transcript.txt`.
- Local gate outputs, including full-suite summary and local artifact `find`.
- `git rev-parse HEAD`, branch, log line, and clean `git status --short`.
- Before/after `systemctl is-enabled`, `is-active`, `status`, `cat`, and effective
  `User`/`Group`/`Environment` snippets for paper and shadow units.
- Before/archive/after `find` listings for the paper output directory.
- Selected `QNTY_PAPER_OUTPUT_DIR`, `QNTY_PAPER_DB_PATH`, and `QNTY_FORWARD_OBS_DIR`.
- `forward_start_ts`, DB path, config hash, schema version, and engine version.
- SQLite init stdout and paper-config init stdout.
- DB/config identity receipt.
- Wrapper stdout, stderr, and exit code.
- Manual verifier JSON stdout, stderr, and exit code.
- Published verifier report, receipt, and audit-only `paper_verify_log.jsonl`.
- DB/WAL/SHM listing and unexpected-artifact check.
- Accidental-output journal, inventory with inode metadata, SHA-256 hashes, `lsof` output, path
  ownership, and intact archive path, when the recovery branch applies.
- Rollback transcript and confirmation if rollback is executed.

Exit the recorded shell after evidence collection:

```bash
exit
```

---

## 11. Review gates before timer enablement is even proposed

All gates require explicit human review:

- This runbook is reviewed and approved.
- Local targeted tests and full suite are green with `0 skipped`.
- Approved branch/commit and clean worktree are confirmed locally and on the VM.
- VM read-only reconnaissance is reviewed.
- Accidental automatic execution evidence and intact archive are reviewed, when the recovery branch
  applies.
- Manual wrapper run evidence is reviewed.
- Status matrix success is exactly `OK`/`OK` or `PRE_START`/`PRE_START`, wrapper exit `0`.
- DB/output/observer path consistency and DB/config identity are verified.
- No stale legacy JSONL-era paper-ledger artifacts were generated; verifier-owned
  `paper_verify_log.jsonl` is audit-only and expected.
- Paper timer is still disabled/inactive.
- Service user/group issue is resolved and reviewed.
- Observer/shadow timer remains active/enabled and untouched.
- No strategy, observer, exchange, order, script, or ops code changed on the VM.
- No live readiness, deployment readiness, or profitability claims are made.

Only after every gate passes may a separate timer-enablement proposal be authored. This preflight
runbook never authorizes that proposal's execution.
