# Qnty VM 90-Day Alerts and Recovery

**Purpose:** Define alerting behavior and recovery procedures for the 90-day observer.  
**Principle:** Minimal complexity. Viktor receives email or webhook notifications on failure only.

---

## 1. Alerting Philosophy

- **No dashboards.** No Grafana. No Prometheus. No Slack bot with charts.
- **Email on failure.** Viktor receives one email when something breaks.
- **Daily summary is read-only.** Viktor reads it when he wants, not when the system pushes.
- **Escalation path is manual.** Viktor triages and decides.

---

## 2. Alert Triggers

The `qnty-healthcheck.service` is the alert arbiter. It exits 0 (pass) or 1 (fail).

### Alert Level: CRITICAL — Page Viktor Immediately

Triggered by `qnty-healthcheck.sh` returning exit code 1:

| Condition | Threshold |
|-----------|-----------|
| Data stale | Any `data/*_8h_ohlcv.csv` >9h old |
| Disk full | `/srv/qnty` disk usage >85% |
| Service dead | Any `qnty-*.timer` not `active` |
| Shadow run silent | No `bar_decisions.jsonl` entry in >24h |

### Alert Level: WARNING — Log Only, No Page

| Condition | Action |
|-----------|--------|
| Fetch script non-zero exit | Log to journal, retry next cycle |
| Healthcheck minor warning | Log to journal, no page |
| Disk >70% but <85% | Log warning, no page yet |

---

## 3. Alert Delivery — Simplest Option (No Extra Infrastructure)

### Option A: Systemd + Email (Postfix/Mail)

The VM has `systemd` and can send email via `postfix` or `ssmtp`.

**Setup:**
```bash
apt-get install postfix mailutils  # during VM setup
```

**Healthcheck service failure alert via systemd OnFailure:**
In `qnty-healthcheck.service`, add:
```ini
[Service]
OnFailure=qnty-alert-email.service
```

Create `qnty-alert-email.service`:
```ini
[Unit]
Description=Qnty Alert Email on Healthcheck Failure
After=network.target

[Service]
Type=oneshot
ExecStart=/srv/qnty/repo/ops/bin/qnty-send-alert.sh "Qnty Healthcheck FAIL"
```

Create `ops/bin/qnty-send-alert.sh`:
```bash
#!/usr/bin/env bash
# qnty-send-alert.sh - Send alert email to Viktor
set -euo pipefail
RECIPIENT="viktor@example.com"  # Replace with Viktor's email
SUBJECT="${1:-Qnty Alert}"
BODY="${2:-Healthcheck failed on $(hostname) at $(date -u)}"
echo "$BODY" | mail -s "$SUBJECT" "$RECIPIENT"
```

**Configure postfix** to relay through Viktor's email provider (or use ssmtp for simple SMTP relay).

### Option B: Webhook to Viktor's Endpoint

Replace the email step with a curl webhook:

```bash
curl -X POST https://viktor.example.com/webhook/qnty \
  -H "Content-Type: application/json" \
  -d "{\"alert\": \"$1\", \"host\": \"$(hostname)\", \"ts\": \"$(date -u)\"}"
```

This requires Viktor to host a simple receiver endpoint. Minimal infrastructure.

### Option C: Pushover or Similar (No Infrastructure)

Use a third-party notification service with a simple API:

```bash
curl -s -F "token=YOUR_PUSHOVER_TOKEN" \
     -F "user=YOUR_PUSHOVER_USER" \
     -F "message=$1" \
     https://api.pushover.net/1/messages.json
```

---

## 4. Healthcheck Failure Response Procedure

When Viktor receives an alert:

### Step 1: Assess (5 minutes)
```bash
# Check what failed
journalctl -t qnty-healthcheck -r --no-pager | head -50

# Check all timer states
systemctl list-timers qnty- --no-pager

# Check disk
df -h /srv/qnty

# Check data freshness
for f in /srv/qnty/data/*_8h_ohlcv.csv; do
  echo "$f: $(tail -1 "$f" | cut -d',' -f1)"
done
```

### Step 2: Categorize

| Symptom | Category | Response |
|---------|----------|----------|
| Data stale, network up | Binance API issue | Wait, retry manually |
| Data stale, network down | Network outage | Wait for recovery, check Hetzner status |
| Disk >85% | Disk full | Emergency: delete old outputs, take snapshot |
| Timer inactive | systemd issue | Restart timers |
| Shadow run silent | Script error | Inspect journal logs, retry manually |

### Step 3: Act

**For data/API issues:**
```bash
# Manually trigger data refresh
systemctl start qnty-data-refresh.service

# Check if it succeeded
journalctl -t qnty-data-refresh -r --no-pager | head -20
```

**For disk pressure:**
```bash
# Check what's using space
du -sh /srv/qnty/output/*

# Archive old daily summaries
gzip /srv/qnty/logs/daily_summary_2026-*.txt

# Delete very old burn-in logs if present
rm -f /srv/qnty/logs/burnin_*.md
```

**For systemd issues:**
```bash
# Restart all timers
systemctl restart qnty-data-refresh.timer
systemctl restart qnty-shadow-run.timer
systemctl restart qnty-healthcheck.timer
systemctl restart qnty-daily-summary.timer

# Verify
systemctl list-timers qnty- --no-pager
```

### Step 4: Document

If the issue took >1 hour to resolve, document it:
```bash
echo "ALERT $(date -u): $SYMPTOM | $ACTION_TAKEN | RESOLVED_AT $(date -u)" \
    >> /srv/qnty/logs/incident_log.md
```

---

## 5. Recovery from Snapshot

If the VM becomes unrecoverable (corruption, Hetzner failure, etc.):

### Step 1: Deploy New VM
- Spin up new CX23 with Ubuntu 24.04 LTS
- Apply same SSH/firewall config

### Step 2: Restore from Snapshot
- In Hetzner console: restore from `clean-deploy-<date>` snapshot (pre-burnin) or `post-burnin-<date>` (if available)
- Attach snapshot to new VM

### Step 3: Verify State
```bash
# Check SHA matches
cat /srv/qnty/state/deploy_sha.txt
cd /srv/qnty/repo && git rev-parse HEAD  # must match

# Check timers
systemctl list-timers qnty- --no-pager

# Check data
tail -1 /srv/qnty/data/BTCUSDT_8h_ohlcv.csv
```

### Step 4: Resume
- Restart timers: `systemctl start qnty-*.timer`
- Note: data fetch will re-fetch full history (acceptable)
- Shadow run will restart from the point-in-time of the snapshot data
- Document the recovery in incident log

---

## 6. Backup Schedule

| Type | Frequency | Retention | Method |
|------|-----------|-----------|--------|
| Hetzner automatic backup | Daily | 7 days | Hetzner console (provider backup) |
| Hetzner manual snapshot | Before burn-in, after burn-in, monthly | Until replaced | Manual in Hetzner console |
| Output directory | Weekly | 90 days | Copy to Viktor's laptop or S3 |
| State directory | Weekly | 90 days | Copy alongside outputs |

### Weekly Output Copy Command (run from Viktor's laptop)
```bash
rsync -avz qnty@<VM_IP>:/srv/qnty/output/ /backup/qnty/output/
rsync -avz qnty@<VM_IP>:/srv/qnty/state/ /backup/qnty/state/
rsync -avz qnty@<VM_IP>:/srv/qnty/logs/ /backup/qnty/logs/
```

---

## 7. 90-Day End Procedure

When the 90-day observation period ends:

### Step 1: Stop All Timers
```bash
systemctl stop qnty-data-refresh.timer
systemctl stop qnty-shadow-run.timer
systemctl stop qnty-healthcheck.timer
systemctl stop qnty-daily-summary.timer
```

### Step 2: Take Final Snapshot
- Label: `90d-complete-<YYYY-MM-DD>`

### Step 3: Copy All Outputs
```bash
rsync -avz qnty@<VM_IP>:/srv/qnty/output/ /final/qnty_output/
rsync -avz qnty@<VM_IP>:/srv/qnty/logs/ /final/qnty_logs/
```

### Step 4: Write Final Verdict
Viktor authors `/final/qnty_output/forward_obs_v1/final_90d_verdict.md`:
```markdown
# 90-Day Forward Observation — Final Verdict

Package: Package V2 (volnorm, frozen)
Period: <YYYY-MM-DD> to <YYYY-MM-DD+90>
Deploy SHA: <SHA>
Observations: <N> bars

Kill Criteria Results:
- K1 (min Sharpe): <value> - PASS/FAIL
- K2 (max drawdown): <value> - PASS/FAIL  
- K4 (heat cap): <value> - PASS/FAIL

## Verdict

[ Viktor's written verdict ]

## Caveats Confirmed

- benchmark gross: confirmed / revised
- funding net: confirmed / revised
- K3: still unavailable

## Next Authorized Action

[ What Viktor authorizes next ]
```

### Step 5: Archive the VM
- Keep Hetzner snapshot labeled `90d-archive-<date>`
- Shut down the VM (don't delete yet, keep snapshot)
- Delete VM after Viktor confirms final verdict written

---

## 8. Minimal Alert Checklist

To set up alerting on a fresh VM, Viktor does these 3 things:

1. **Install mailutils** (or configure ssmtp/webhook) during VM setup:
   ```bash
   apt-get install mailutils
   ```

2. **Replace `viktor@example.com`** in `ops/bin/qnty-send-alert.sh` with real email

3. **Add `OnFailure=qnty-alert-email.service`** to `qnty-healthcheck.service`:
   ```bash
   # After copying service files, edit:
   sed -i 's/\[Service\]/[Service]\nOnFailure=qnty-alert-email.service/' \
       /etc/systemd/system/qnty-healthcheck.service
   systemctl daemon-reload
   ```

That's it. No Prometheus, no Grafana, no Slack.