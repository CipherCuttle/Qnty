# Qnty VM 90-Day Runbook — Frozen Package V2 Observer

**Phase:** Forward Observation (Shadow Mode)
**Package:** Package V2 (volnorm, frozen)
**Duration:** 90 days after successful burn-in
**VM:** Example — Hetzner CX23, Ubuntu 24.04 LTS, 1× IPv4

> **Note:** This runbook uses `/srv/qnty` as an example operator path and mentions Hetzner/Tailscale as example infrastructure. These are not requirements. Alerting, backups, and snapshots are operator responsibilities.

---

## 1. VM Directory Layout

```
/srv/qnty/
├── repo/              # git clone of Qnty (frozen at deploy SHA)
├── venv/              # python -m venv (Python 3.10+)
├── data/              # OHLCV + funding CSVs (symlink to /srv/qnty/repo/data)
├── output/           # all run outputs
│   └── forward_obs_v1/   # forward observation output family
├── state/            # freshness tracking (created at runtime)
├── logs/              # systemd journal excerpts + script logs
├── config/            # reserved for overrides (not used during freeze)
└── backups/           # Hetzner snapshot references + manual backup copies
```

**Why this layout:**
- `repo/` is frozen at a specific git SHA. No pulls, no branches touched.
- `data/` symlinks to `repo/data` — fetch scripts write in-place.
- `output/forward_obs_v1/` accumulates all observation artifacts.
- All service logs go to systemd journal (journalctl).

---

## 2. Security Posture

### SSH
- SSH key only, **no password authentication**
- `PermitRootLogin no`
- `PubkeyAuthentication yes`
- `PasswordAuthentication no`
- SSH key for `qnty` user only (not root)

### Firewall (UFW)
```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw enable
```

### Tailscale
**Optional.** If used: install and authenticate. Provides WireGuard VPN tunnel for <operator>'s laptop. Not required for the observer to function.

### Exchange API Keys
**Not required.** All data is public market data from Binance public API. No exchange credentials exist on this VM at any point.

### Live Trading
**Not authorized.** The VM has no exchange API keys, no order-routing code, and no wallet access. It is purely a computation and observation engine.

---

## 3. Software Installation (One-Time VM Setup)

### 3.1 OS User
```bash
adduser --system --group --home /srv/qnty qnty
mkdir -p /srv/qnty
```

### 3.2 Python
```bash
apt-get update && apt-get install -y python3.11 python3.11-venv git curl
python3.11 -m venv /srv/qnty/venv
```

### 3.3 Clone Repo (at frozen SHA)
```bash
cd /srv/qnty
git clone https://github.com/<org>/Qnty.git repo
cd repo
git checkout <FROZEN_SHA>   # Record this SHA in the burn-in checklist
git submodule update --init  # if any submodules exist
pip install -e .
```

### 3.4 Data Symlink
```bash
ln -sf /srv/qnty/repo/data /srv/qnty/data
```

### 3.5 Create Required Directories
```bash
mkdir -p /srv/qnty/output/forward_obs_v1
mkdir -p /srv/qnty/state
mkdir -p /srv/qnty/logs
mkdir -p /srv/qnty/config
mkdir -p /srv/qnty/backups
```

### 3.5b Paper PnL config — archive stale output, re-init fresh

The hardened paper engine (`engine_version 0.2.0`) **rejects any pre-existing
`paper_config.json` that predates the current contract** (an old `0.1.0` config, or one
missing `baseline_label` / `freshness`): `load_config` fails loudly and the run aborts.

**Any stale `/srv/qnty/output/paper_pnl_v1/` content from before this patch (e.g. a lone
`paper_config.json` with no fills/trades/equity) MUST be archived or deleted and re-init'd**
with a **fresh, future `forward_start_ts`** — do not reuse a stale forward start:

```bash
# 1. Archive whatever is there (never silently overwrite a write-once config):
ts=$(date -u +%Y%m%dT%H%M%SZ)
mv /srv/qnty/output/paper_pnl_v1 /srv/qnty/output/paper_pnl_v1.archived-$ts 2>/dev/null || true
mkdir -p /srv/qnty/output/paper_pnl_v1

# 2. Re-init the write-once config with a fresh FUTURE 8h boundary (no fill before it):
cd /srv/qnty/repo
QNTY_PAPER_OUTPUT_DIR=/srv/qnty/output/paper_pnl_v1 \
  .venv/bin/python -m quantbot.paper.config --forward-start-ts <FUTURE_UTC_8H_BOUNDARY>
```

The paper timer remains disabled until the config is re-init'd against this engine version.

**Paper accounting status / exit-code matrix (do not conflate them).** `scripts/qnty-paper-accounting.py`
writes a `status` into `paper_pnl_summary.json` (and `paper_provenance.json`) and returns an
exit code. **`exit 0` is NOT proof a normal accounting run happened** — it covers both a real
`OK` run *and* a healthy `NO_ELIGIBLE_BARS_YET` no-op. Always read the summary `status` /
journald log, never the exit code alone:

| `status` | exit | meaning | writes |
| --- | --- | --- | --- |
| `OK` | `0` | completed accounting: freshness + config + existing-ledger health + post-mutation reconcile all passed; the watermark advanced. | full ledger rows + state + summary/receipt/provenance |
| `NO_ELIGIBLE_BARS_YET` | `0` | **healthy no-op** — observer output is clean/fresh/on-grid and the existing ledgers reconcile, but no bar has reached `forward_start_ts` yet. NOT a FLAT/zero result. | summary/receipt/provenance only; **no** ledger rows, **no** state/watermark |
| `ABORTED` | `2` | freshness/divergence gate abort (config valid, observer output stale/missing/malformed/diverged). | clearly-marked `ABORTED` summary/receipt/provenance; **no** fills/trades/equity |
| `CONFIG_ERROR` (`ConfigContractError`) | `3` | the `paper_config.json` that *defines* the output contract is itself stale/malformed (old `0.1.0`, wrong `schema_version`/`engine_version`/`baseline_label`, missing/non-finite `freshness`, bad JSON, or hash mismatch). Clean operator message + archive/re-init guidance, **no Python traceback**. | **nothing** — no ledger/state/summary/provenance/receipt |
| `CORRUPT_LEDGER` | `4` | an existing ledger is unreadable (malformed JSONL) **or** a reconcile invariant fails (orphan fill/snapshot, disagreeing `bar_commit_id`, partial bar) — caught either on the pre-run existing-ledger health gate or the post-mutation reconcile. The watermark is **NOT** advanced and **no** `OK` is published. | `CORRUPT_LEDGER` summary/receipt/provenance surfacing the reconcile failures; **no** new ledger rows, **no** state |

So: `exit 0` = `OK` run **or** healthy `NO_ELIGIBLE_BARS_YET` no-op (read the status) · `exit 2`
= gate-aborted with an `ABORTED` summary · `exit 3` = stale/malformed-config abort with **no**
writes (re-init required) · `exit 4` = `CORRUPT_LEDGER`.

**`CORRUPT_LEDGER` (exit 4) is an operator-action stop, not a transient.** It means the
persisted ledger is partial/unreadable. **Pause the paper timer** (`systemctl stop
qnty-paper-pnl.timer`) and review `paper_pnl_summary.json` → `reconcile_failures` before any
further run. Do NOT delete or "fix" ledger rows by hand on the VM; capture the corrupt files
and the summary for off-VM review. The watermark was not advanced, so once the underlying
corruption is understood and resolved off-VM the run can be retried safely.

### 3.6 Copy Systemd Units
```bash
cp /srv/qnty/repo/ops/systemd/*.service /etc/systemd/system/
cp /srv/qnty/repo/ops/systemd/*.timer /etc/systemd/system/
systemctl daemon-reload
```

The committed unit files use the canonical `qnty` system user. **The current
production VM runs these services as `viktor`, not `qnty`.** Keep the committed
unit files canonical and add local systemd drop-ins instead — this is the
documented deployment override referenced by `docs/paper_pnl_v1_schema.md`
section 12. The loop below includes `qnty-paper-pnl` so the paper service runs as
the **same user as the shadow service**; a unit whose `User=` does not exist on
the VM fails silently at activation and its timer would never produce output:

```bash
for svc in qnty-data-refresh qnty-shadow-run qnty-healthcheck qnty-daily-summary qnty-paper-pnl; do
  mkdir -p /etc/systemd/system/${svc}.service.d
  cat > /etc/systemd/system/${svc}.service.d/user.conf <<'EOF'
[Service]
User=viktor
Group=viktor
EOF
done

systemctl daemon-reload
```

This makes local user drift visible in `systemctl cat` without changing the
repo's production baseline. Verify after deploy with
`systemctl show -p User,Group qnty-paper-pnl.service` and confirm it matches
`qnty-shadow-run.service`.

### 3.7 Enable and Start Timers
```bash
systemctl enable qnty-data-refresh.timer
systemctl enable qnty-shadow-run.timer
systemctl enable qnty-healthcheck.timer
systemctl enable qnty-daily-summary.timer

systemctl start qnty-data-refresh.timer
systemctl start qnty-shadow-run.timer
systemctl start qnty-healthcheck.timer
systemctl start qnty-daily-summary.timer
```

### 3.8 Hetzner Backup
- Enable Provider Backup in Hetzner console (automatic daily backups)
- After setup and before burn-in: take one **manual snapshot** labeled `clean-deploy-<date>`
- After burn-in and before 90-day start: take one **manual snapshot** labeled `post-burnin-<date>`

### 3.9 Provenance Files and Protocol Receipt

Before starting the 90-day clock, write the VM provenance files:

```bash
cd /srv/qnty/repo
/srv/qnty/repo/ops/bin/qnty-write-provenance-receipt.sh
```

This creates:

| File | Purpose |
|------|---------|
| `/srv/qnty/state/deploy_sha` | Git SHA deployed on the VM |
| `/srv/qnty/state/authorized_sha` | Git SHA authorized for observation |
| `/srv/qnty/state/90d_start_date` | UTC start date for the observation clock |
| `/srv/qnty/state/protocol_receipt.md` | Host, unit, healthcheck, and unit-file-hash receipt |

The helper refuses to overwrite existing files unless `FORCE=1` is set after
operator review. To authorize a different SHA explicitly:

```bash
AUTHORIZED_SHA=<approved-sha> /srv/qnty/repo/ops/bin/qnty-write-provenance-receipt.sh
```

---

## 4. Scheduling — 8h Bar Close Times (UTC)

| Bar Index | Closes (UTC) |
|-----------|-------------|
| Bar 0     | 00:00 UTC   |
| Bar 1     | 08:00 UTC   |
| Bar 2     | 16:00 UTC   |

### 8h Cycle
```
00:00 UTC  → Bar 0 close
00:05 UTC  → data-refresh fires (fetch new data)
00:10 UTC  → shadow-run fires (observe on Bar 0)

08:00 UTC  → Bar 1 close
08:05 UTC  → data-refresh fires
08:10 UTC  → shadow-run fires

16:00 UTC  → Bar 2 close
16:05 UTC  → data-refresh fires
16:10 UTC  → shadow-run fires
```

### Systemd Timer Schedule (Exact)

| Timer | Schedule |
|-------|----------|
| `qnty-data-refresh.timer` | `*-*-* 00:05:00, 08:05:00, 16:05:00` |
| `qnty-shadow-run.timer`   | `*-*-* 00:10:00, 08:10:00, 16:10:00` |
| `qnty-healthcheck.timer`  | Every 4h: `00,04,08,12,16,20,22:00` |
| `qnty-daily-summary.timer` | Daily at `17:00:00` |

The 5-minute buffer after bar close ensures fetch scripts have completed before shadow-run starts. The 10-minute buffer gives the exchange time to finalize the bar.

---

## 5. Service Descriptions

### 5.1 Data Refresh (`qnty-data-refresh.service`)
- Calls `scripts/fetch_ohlcv_rest.py` (OHLCV for 10 symbols)
- Calls `scripts/fetch_funding_rest.py` (funding rates for 10 symbols)
- Uses public Binance API — **no keys required**
- Overwrites full CSV files each run (acceptable: ~40k records, ~40s)
- Sets `END_TIME_MS` to tomorrow to capture all available data
- **Fails loudly** if network is unavailable or API returns errors

### 5.2 Shadow Run (`qnty-shadow-run.service`)
- Runs `scripts/run_stage4_volnorm.py` (full walkforward, kill criteria)
- Runs `scripts/run_validation_v2.py` (holdout observation)
- Copies outputs to `/srv/qnty/output/forward_obs_v1/`
- Writes `bar_decisions.jsonl` entry per run
- **Never places orders. Never requires exchange credentials.**
- Timeout: 30 minutes

### 5.3 Healthcheck (`qnty-healthcheck.service`)
- Checks all active `data/*_8h_ohlcv.csv` files are ≤9h old
- Parses both Unix epoch timestamps and ISO timestamps
- Logs an explicit skip for known stale/delisted symbols in `KNOWN_STALE_OHLCV_FILES`
- Checks disk usage ≤80%
- Checks all systemd timer states are `active`
- Checks `bar_decisions.jsonl` exists and has recent entry
- **Exits 0 on pass, exits 1 on fail**
- Failure triggers alerting (see Alerts section)

Current VM policy sets `KNOWN_STALE_OHLCV_FILES=MATICUSDT_8h_ohlcv.csv` by
default because MATICUSDT is a known stale/delisted/migrated market in this
observer dataset. This exception is logged on every healthcheck; it must not be
silent.

### 5.4 Daily Summary (`qnty-daily-summary.service`)
- Collects run metadata: commit SHA, bar count, newest bar timestamp, last verdict
- Writes `daily_summary.jsonl` entry
- Writes human-readable `logs/daily_summary_<YYYY-MM-DD>.txt`
- Not a dashboard — <operator> reads the text file

---

## 6. Output / Artifact Plan

All outputs live under `/srv/qnty/output/forward_obs_v1/`:

| File | Purpose |
|------|---------|
| `run_metadata.json` | Run timestamp + frozen commit SHA |
| `bar_decisions.jsonl` | One line per shadow run: timestamp + commit SHA |
| `daily_summary.jsonl` | One line per day: bar count, newest bar, verdict |
| `per_split_metrics.csv` | From stage4: per-split equity, sharpe, max drawdown |
| `kill_criteria.json` | From stage4: K1, K2, K4, heat_cap status |
| `verdict.json` | From validation: GO/FAIL, observation count |
| `observation_log.json` | From validation: per-bar observation details |
| `caveat_note.md` | From validation: caveats in effect |
| `validation_receipt.md` | From validation: protocol receipt |
| `logs/daily_summary_<YYYY-MM-DD>.txt` | Human-readable daily summary |

A `GO`, `PASSED`, or `SURVIVED` label means the configured observer kill
criteria were not triggered for that research run. It does not prove real-money
profitability, deployment readiness, or live-trading approval.

Runtime `data/`, `output/`, and `experiment_results/` churn belongs on the VM
and is ignored by git. Curated, human-authored receipts and verdicts belong
under `docs/` when they are intentionally promoted into repo history.

### 90-Day Final Outputs
At the end of 90 days, the following files constitute the complete evidence package:
- `bar_decisions.jsonl` — all bar observations across 90 days
- `daily_summary.jsonl` — all daily summaries
- `per_split_metrics.csv` — walkforward equity series
- `kill_criteria.json` — kill criteria status at end of run
- `final_90d_verdict.md` — <operator>'s verdict document (manually authored after review)

---

## 7. Freeze Rules (Forbidden During 90-Day Run)

**Absolutely no changes to:**
1. Strategy logic (`quantbot/strategy/`)
2. Signal logic (`quantbot/experiment/volnorm_portfolio.py`)
3. Threshold values (vol lookback, heat cap)
4. Universe composition (10 symbols)
5. K3 implementation (not available)
6. Benchmark semantics (gross)
7. Carry semantics (net of realistic funding)
8. Any code in `quantbot/` or `scripts/`

**Absolutely no:**
- `git pull`, branch switches, or commits in `/srv/qnty/repo`
- Installation of new Python packages
- Overlay/ML/Kelly/RAMOM additions
- Live trading enablement
- Exchange API key introduction
- Research mutation mixed with observation operations

**If a change is needed:**
1. Stop all timers: `systemctl stop qnty-*.timer`
2. Take a Hetzner snapshot
3. Make the change on a branch (off-VM)
4. Test it separately (not on this VM)
5. Get explicit authorization
6. If approved: snapshot again, then restart timers

---

## 8. Viewing Logs

```bash
# All qnty services
journalctl -t qnty-data-refresh
journalctl -t qnty-shadow-run
journalctl -t qnty-healthcheck
journalctl -t qnty-daily-summary

# All qnty logs in reverse time order
journalctl -t qnty-data-refresh -t qnty-shadow-run -t qnty-healthcheck -t qnty-daily-summary -r

# Filter by timer
journalctl -u qnty-data-refresh.timer --since "1 hour ago"

# Human-readable daily summaries
cat /srv/qnty/logs/daily_summary_$(date -u +%Y-%m-%d).txt

# Bar decisions
cat /srv/qnty/output/forward_obs_v1/bar_decisions.jsonl | tail -10

# Forward observation outputs
ls -la /srv/qnty/output/forward_obs_v1/

# Verify VM provenance and runtime truth
/srv/qnty/repo/ops/bin/qnty-verify-vm-provenance.sh

# Hetzner/operator laptop check
ssh -i ~/.ssh/hetzner_qnty_key <operator>@<VM_IP> \
  'hostname; date -u; /srv/qnty/repo/ops/bin/qnty-verify-vm-provenance.sh'
```

---

## 9. Manual Commands (Emergency Only)

```bash
# Force a data refresh
systemctl start qnty-data-refresh.service

# Force a shadow run
systemctl start qnty-shadow-run.service

# Force a healthcheck
systemctl start qnty-healthcheck.service

# Check all timer statuses
systemctl list-timers qnty-

# Check a specific data file freshness
tail -1 /srv/qnty/data/BTCUSDT_8h_ohlcv.csv

# Check disk space
df -h /srv/qnty
```

---

## 10. Git SHA Tracking and Verification

Record the frozen SHA at deploy time with the provenance helper:

```bash
cd /srv/qnty/repo
/srv/qnty/repo/ops/bin/qnty-write-provenance-receipt.sh
/srv/qnty/repo/ops/bin/qnty-verify-vm-provenance.sh
```

The verifier checks:

- deployed Git HEAD
- non-runtime git drift, excluding generated `data/`, `output/`, and `experiment_results/`
- active qnty timers
- latest healthcheck PASS
- latest output timestamp
- `/srv/qnty/state/deploy_sha`
- `/srv/qnty/state/authorized_sha`
- `/srv/qnty/state/90d_start_date`
- deployed HEAD equals `deploy_sha`
- `deploy_sha` equals `authorized_sha`

This SHA is appended to every shadow-run output. It is the anchor that proves no
code mutation occurred during the 90-day run.

---

## 11. Prerequisites Before 90-Day Clock Starts

1. Burn-in completed successfully (see `VM_90D_BURNIN_CHECKLIST.md`)
2. Clean-deploy snapshot taken
3. Post-burnin snapshot taken
4. All timers verified active: `systemctl list-timers qnty-`
5. First shadow run completed with output in `forward_obs_v1/`
6. <operator> has SSH access and can view daily summaries
7. Alerting configured (see `VM_90D_ALERTS_AND_RECOVERY.md`)
