# Qnty VM 90-Day Burn-In Checklist

**Purpose:** Verify the VM observer is functioning correctly before the 90-day clock starts.
**Minimum Duration:** 7 consecutive days of successful operation.
**VM:** Example — Hetzner CX23, Ubuntu 24.04 LTS

> **Note:** This runbook uses `/srv/qnty` as an example operator path and mentions Hetzner/Tailscale as example infrastructure. These are not requirements. Alerting, backups, and snapshots are operator responsibilities.

---

## Burn-In Overview

Burn-in runs the full systemd schedule but does NOT start the 90-day clock. The 90-day clock starts only after all burn-in checks pass and <operator> explicitly authorizes it.

Burn-in checks are repeated daily during the burn-in window. <operator> reviews the accumulated evidence and signs off before the 90-day start.

---

## Daily Burn-In Checks

Run this checklist each day during burn-in. All items must pass for that day.

### Day 1 (Baseline)

- [ ] **SSH access verified** — <operator> can SSH to VM as `qnty` user
- [ ] **Disk space** — `df -h /srv/qnty` shows <50% used
- [ ] **Python venv** — `/srv/qnty/venv/bin/python --version` returns 3.10+
- [ ] **Repo SHA recorded** — `git rev-parse HEAD` matches expected SHA, recorded in `/srv/qnty/state/deploy_sha.txt`
- [ ] **No git changes** — `git status` in `/srv/qnty/repo` shows clean working tree
- [ ] **Systemd units installed** — `systemctl list-unit-files qnty-*` shows all 8 units
- [ ] **Timers enabled** — `systemctl list-timers qnty-` shows all 4 timers active
- [ ] **Initial data fetch** — Manually run `systemctl start qnty-data-refresh.service`, check it completes with exit 0
- [ ] **Initial shadow run** — After data fetch, run `systemctl start qnty-shadow-run.service`, check it completes with exit 0
- [ ] **Output files exist** — `ls /srv/qnty/output/forward_obs_v1/` shows all expected files
- [ ] **No exchange keys on VM** — `grep -r api_key /srv/qnty/` returns nothing

### Day 2–7 (Repeated Daily)

- [ ] **Data fresh** — All `data/*_8h_ohlcv.csv` files have newest bar ≤9h old
- [ ] **Data refresh succeeded** — `journalctl -t qnty-data-refresh --since "24h ago"` shows successful runs
- [ ] **Shadow run succeeded** — `journalctl -t qnty-shadow-run --since "24h ago"` shows successful runs  
- [ ] **No stale timer failures** — `systemctl list-units qnty-*.service` shows no failed units
- [ ] **Healthcheck passes** — `systemctl start qnty-healthcheck.service && echo $?` returns 0
- [ ] **Daily summary generated** — `ls /srv/qnty/logs/daily_summary_*.txt` has entry for today
- [ ] **Bar decision recorded** — `tail -1 /srv/qnty/output/forward_obs_v1/bar_decisions.jsonl` shows today's run
- [ ] **Disk still <60%** — `df -h /srv/qnty` shows <60% used (allowing headroom for 90 days)
- [ ] **No unexpected cron/systemd changes** — `journalctl --since "yesterday" --no-pager | grep -i "systemd\|cron" | grep -v "timer\|service" | grep -v "started\|stopped"` returns no unexpected changes
- [ ] **Repo still clean** — `git status` in `/srv/qnty/repo` still shows clean working tree

---

## Burn-In Completion Criteria

The 90-day clock MAY start when ALL of the following are true:

### Data Integrity
- [ ] At least 3 complete 8h cycles (3 bar closes, 3 data fetches, 3 shadow runs) completed successfully
- [ ] All 10 symbols have OHLCV data (no missing symbols)
- [ ] All 10 symbols have funding data (no missing symbols)
- [ ] Data files are growing in row count (bars accumulating over time)
- [ ] No data gaps detected (consecutive timestamps, no jumps)

### System Stability  
- [ ] 7 consecutive days with no failed systemd units
- [ ] No data-refresh failures
- [ ] No shadow-run failures
- [ ] No healthcheck failures
- [ ] No disk space alerts
- [ ] No network connectivity issues

### Output Quality
- [ ] `bar_decisions.jsonl` has ≥3 entries
- [ ] `daily_summary.jsonl` has ≥3 entries  
- [ ] `per_split_metrics.csv` exists and has non-zero rows
- [ ] `kill_criteria.json` exists and has all K values
- [ ] `verdict.json` exists from validation run

### Authorization
- [ ] <operator> has reviewed the burn-in evidence
- [ ] <operator> has reviewed the caveat reminder (Package V2 not deployment-ready)
- [ ] <operator> explicitly authorizes 90-day start in writing (email/slack/issue)

---

## Blockers — 90-Day Start Must NOT Begin If:

1. **Any data-refresh failure** during burn-in — investigate and resolve
2. **Any shadow-run failure** during burn-in — investigate and resolve  
3. **Healthcheck returns FAIL** at any point — investigate and resolve
4. **Disk usage exceeds 70%** before 90-day start — clean outputs or expand storage
5. **Repo git status is dirty** — must be clean at deploy time
6. **Missing symbols** in OHLCV or funding data — Binance API may be down or symbols changed
7. **Any exchange credentials found on VM** — must be zero, stop immediately and audit
8. **<operator> has not signed off** — explicit authorization required

---

## Snapshot Schedule

| Snapshot | When | Label |
|----------|------|-------|
| Clean Deploy | After initial setup, before burn-in | `clean-deploy-<YYYY-MM-DD>` |
| Post-Burn-In | After 7 days pass, before 90-day start | `post-burnin-<YYYY-MM-DD>` |
| Monthly | Every 30 days during 90-day run | `90d-monthly-<N>-<YYYY-MM-DD>` |
| End | After 90-day run completes | `90d-complete-<YYYY-MM-DD>` |

---

## Burn-In Log Template

Create `/srv/qnty/logs/burnin_log.md` with this template:

```markdown
# Burn-In Log

## Deploy SHA: <FROZEN_SHA>
## Deploy Date: <YYYY-MM-DD>
## Expected Burn-In End: <YYYY-MM-DD+7>

## Day-by-Day Sign-Off

| Day | Date | Data Refresh | Shadow Run | Healthcheck | Disk | Signed Off |
|-----|------|-------------|------------|-------------|------|------------|
| 1   |      |             |            |             |      |            |
| 2   |      |             |            |             |      |            |
| 3   |      |             |            |             |      |            |
| 4   |      |             |            |             |      |            |
| 5   |      |             |            |             |      |            |
| 6   |      |             |            |             |      |            |
| 7   |      |             |            |             |      |            |

## <operator> Sign-Off

- Authorization to start 90-day run: YES / NO
- <operator> signature: ___________________
- Date: ___________________
```

---

## Burn-In Failure Response

If any burn-in day fails:

1. **Do NOT start the 90-day clock**
2. Diagnose the failure using `journalctl`
3. Document the failure in `/srv/qnty/logs/burnin_failure_<YYYY-MM-DD>.md`
4. If fixable (e.g., disk full, network glitch): fix, reset burn-in day counter to 1, restart burn-in
5. If unfixable (e.g., Binance API permanently changed): escalate, do not proceed to 90-day

---

## Post-Burn-In, Pre-90-Day Actions

After burn-in completes and <operator> authorizes:

1. Take Hetzner snapshot labeled `post-burnin-<date>`
2. Record the authorized SHA in `/srv/qnty/state/authorized_sha.txt`
3. Record authorization date in `/srv/qnty/state/90d_start_date.txt`
4. Create `/srv/qnty/output/forward_obs_v1/protocol_receipt.md`:
   ```markdown
   # 90-Day Forward Observation — Protocol Receipt
   
   Package: Package V2 (volnorm, frozen)
   Authorized SHA: <SHA>
   Burn-in completed: <YYYY-MM-DD>
   90-day start: <YYYY-MM-DD>
   90-day end: <YYYY-MM-DD+90>
   <operator> authorized: <date>
   
   Caveats in effect:
   - benchmark remains gross
   - strategy remains net of realistic funding
   - K3 remains unavailable / caveated
   - Package V2 is NOT deployment-ready
   ```
5. Set a calendar reminder for 90-day end date