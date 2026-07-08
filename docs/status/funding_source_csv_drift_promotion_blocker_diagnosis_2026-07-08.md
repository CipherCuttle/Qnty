# Funding Source CSV Drift — Official Report Promotion Blocker Diagnosis

- date: `2026-07-08`
- task: `FUNDING_SOURCE_CSV_DRIFT_PROMOTION_BLOCKER_DIAGNOSIS_GIT_OWNED`
- branch: `docs/funding-source-csv-drift-promotion-blocker-diagnosis`
- base: `origin/main` @ `affd9d7e649eb610c56041cab9b99b587e8d1d43` (PR #103 merge)
- mode: **read-only / docs-only diagnosis. No repair performed.**
- shadow lane: `/srv/qnty/output/paper_pnl_null_shadow_v0`
- source data dir: `/srv/qnty/repo/data`
- VM: `viktor@37.27.216.174` → `ubuntu-4gb-hel1-1-qnty`

> "clean" / `CLEAN_NET_OF_CARRY` in the referenced receipts means **"not killed
> by this verifier carry/digest gate"** — it is **not** an edge, profitability,
> or live-approval signal. `EDGE_UNPROVEN` and `BLOCK_LIVE_INTEGRATION` remain.

---

## PLAN

1. Sync local repo safely: confirm branch/status, fetch origin, confirm `main`
   includes PR #103 merge `affd9d7…`, branch from `origin/main`.
2. Inspect current funding CSV state on the VM read-only (sha256, size, mtime,
   rows) and compare against PR #101 / PR #103 recorded digests.
3. Inspect possible active refresh sources read-only: systemd timers/services,
   `systemctl cat`, journal for the promotion window, user crontab, `/etc/cron*`,
   live process scan.
4. Inspect repo code paths read-only: find what writes `*_8h_funding.csv`; prove
   whether the verifier can mutate funding CSVs.
5. Classify root cause with one verdict.
6. Record this receipt (only new file).

---

## CHANGESET

- **1 new file only:** this receipt
  (`docs/status/funding_source_csv_drift_promotion_blocker_diagnosis_2026-07-08.md`).
- No code / test / schema / verifier / reporter / writer changes.
- No `data/` / `output/` / DB / official-report changes.
- No service / timer / cron / systemd changes.

---

## VERIFY

### 1. Local repo sync

```bash
git status                          # on docs/...promotion-execution, clean (only .claude/ untracked)
git fetch origin                    # 771e985..affd9d7  main -> origin/main
git rev-parse origin/main           # affd9d7e649eb610c56041cab9b99b587e8d1d43
git merge-base --is-ancestor affd9d7e649eb610c56041cab9b99b587e8d1d43 origin/main && echo YES
git checkout -b docs/funding-source-csv-drift-promotion-blocker-diagnosis origin/main
git rev-parse HEAD                  # affd9d7e649eb610c56041cab9b99b587e8d1d43
```

- `origin/main` head **is exactly** the PR #103 merge commit `affd9d7…`.
- Diagnosis branch created at that commit.

### 2. Current funding CSV state (VM, read-only)

```bash
ssh -i ~/.ssh/hetzner_qnty_key viktor@37.27.216.174 \
  'cd /srv/qnty/repo/data; for f in *_8h_funding.csv; do
     sha256sum "$f"; stat -c "%n %s %Y" "$f"; wc -l < "$f"; done'
```

Current state, mtime UTC (2026-07-08 08:05 timer run):

| CSV | size | mtime (UTC) | rows | sha256 (current, 2026-07-08) |
|---|---|---|---|---|
| BTCUSDT | 220964 | 08:06:50Z | 5502 | `872212ab3a05ab4ebb5804f9dcf805e8243a587be9436c440abd5776931f5866` |
| ETHUSDT | 219260 | 08:06:56Z | 5502 | `7a9510d4793a61c64ff9099e5681222d59de56738937632b322693db78c1b84d` |
| BNBUSDT | 206579 | 08:07:03Z | 5502 | `fb9df46794667ef0b30e319f02cee2937be21f21b728121f0909566c174061ab` |
| SOLUSDT | 220008 | 08:07:10Z | 5577 | `7938d6e17b2b443deb9bcba33f879fb80e81fc00f2defef1b43416178de392b7` |
| ADAUSDT | 212722 | 08:07:17Z | 5502 | `a636d09687a518ee1bba1d14ad8bebb373e70d66af5127ddabeb98c48fe685e1` |
| DOTUSDT | 214680 | 08:07:23Z | 5502 | `753cef9f3b5f5daddaf3cc8b0a653de3fe00e5fa71b6bd8b461bd364468f4273` |
| AVAXUSDT | 220874 | 08:07:30Z | 5502 | `64da6afda291c8c9bcedb611805c01634fe426dbe7fdb54928002e5c5353cde9` |
| LINKUSDT | 217849 | 08:07:37Z | 5502 | `19ff0dbd8deb47b5132bc819637c001edcdde27b98aed5a33eabd68ddffb521a` |
| MATICUSDT | 214210 | 08:07:43Z | 5502 | `a15e7afe06cb467b366d54d1ec342e2eacb9b40dcc6bf793d10d3a077f2b8e35` |
| XRPUSDT | 213390 | 08:07:50Z | 5502 | `d56ad8d49aa1b2db31278c71f8eec134c29b1928192730ca62132d152487473b` |

Key observation: mtimes increase monotonically **in the fixed `SYMBOLS` list
order** (BTC→ETH→BNB→SOL→ADA→DOT→AVAX→LINK→MATIC→XRP), ~6–7s apart, ending
`08:07:50Z` — the exact completion time of today's `qnty-data-refresh` service run.

### Digest comparison across the three snapshots

`before` = PR #101 committed source state (= PR #103 preflight "source digests
before"); `PR#103 after` = drifted state that blocked promotion; `current` = today.

| CSV | PR #101 / PR #103-before | PR #103 after (blocker) | current 2026-07-08 |
|---|---|---|---|
| BTCUSDT | `65c66a32…750c8e` | `418636f4…9deb74a6` | `872212ab…931f5866` |
| ETHUSDT | `e9b3423b…6db467a9` | `3bd2c7b5…4e07f0e8` | `7a9510d4…78c1b84d` |
| BNBUSDT | `ad40bf88…5d170ef3` | `6d20cd71…61c77243a` | `fb9df467…c174061ab` |
| SOLUSDT | `a0980a1a…f66a15cf6a` | `ab2538c9…251e29656` | `7938d6e1…78de392b7` |
| XRPUSDT | `2e9b5971…dbc00a560` | `ea79a4c9…8ac0d4bb` | `d56ad8d4…2487473b` |

- Truncated PR #101 digests (BNB/BTC/ETH/SOL/XRP) match the PR #103 "before" full
  digests byte-for-byte → the recommit baseline and promotion preflight agreed.
- All ten digests changed at PR #103 promotion time, and have changed **again**
  since (three more days of 8h funding periods accrued). Drift is ongoing, not a
  one-off.

### 3. Active refresh source (VM, read-only)

```bash
systemctl list-timers --all
systemctl is-enabled qnty-data-refresh.timer qnty-data-refresh.service
systemctl cat qnty-data-refresh.timer
systemctl status qnty-data-refresh.service --no-pager
journalctl -u qnty-data-refresh.service --since "2026-07-07 16:04:00 UTC" \
                                          --until "2026-07-07 16:09:00 UTC"
crontab -l                     # no funding/fetch/refresh/qnty entries
ls -la /etc/cron.d /etc/cron.daily /etc/cron.hourly   # no qnty/funding cron files
grep -iE 'qnty|fund|refresh' /etc/crontab             # none
ps -eo pid,etimes,cmd | grep -iE 'fetch_funding|data-refresh|writer|trader|backfill'  # none live
```

- **`qnty-data-refresh.timer` is `enabled`**, `OnCalendar` `00:05 / 08:05 / 16:05
  UTC`, `RandomizedDelaySec=60`, `Persistent=true`.
- Last run: `Wed 2026-07-08 08:05:34 UTC` → service completed `08:07:50 UTC`,
  `ExecStart … (code=exited, status=0/SUCCESS)`. Next: `2026-07-08 16:05:04 UTC`.
- Service journal shows it writes `data/*_8h_funding.csv` (via
  `scripts/fetch_funding_rest.py`).
- **No** crontab entry, **no** `/etc/cron*` file, **no** live process, and **no
  other** qnty service writes funding CSVs. The remaining qnty services
  (`paper-pnl`, `shadow-run`, `health-receipt`, `watermark-watchdog`,
  `healthcheck`, `daily-summary`) are simulation / read-only-observability and do
  not touch source CSVs.

#### Decisive: journal for the PR #103 promotion window (2026-07-07)

```
16:05:19Z  qnty-data-refresh: starting          (timer 16:05:00 + randomized delay)
16:06:23Z  Fetching funding rates...            (after OHLCV fetch)
16:07:08Z  -> Saved … data/BTCUSDT_8h_funding.csv … (funding CSVs rewritten)
16:07:25Z  qnty-data-refresh: complete
```

The refresh **completed at `16:07:25Z`** — matching the PR #103 recorded "after"
mtime of the last-written file (`XRPUSDT_8h_funding.csv … 2026-07-07T16:07:25Z`)
to the second.

#### Promotion-window timeline (reconstructed)

| time (UTC) | event | source |
|---|---|---|
| 16:05:00 | `qnty-data-refresh.timer` scheduled fire | `systemctl cat` |
| 16:05:19 | data-refresh service **starts** (randomized delay) | journal |
| 16:05:26 | PR #103 promotion takes report backup; CSVs still at PR #101 digests | PR #103 receipt |
| 16:06:23 | funding fetch begins | journal |
| 16:07:25 | data-refresh **complete**; all 10 funding CSVs rewritten | journal / PR #103 "after" mtimes |
| 16:08:09 | PR #103 **candidate verifier** runs → reads new CSV digests | PR #103 receipt |
| → | `funding_source_file_digest_mismatch` → promotion **blocked** | PR #103 receipt |

The candidate verifier ran **44 seconds after** the refresh finished rewriting the
CSVs, so it necessarily saw the drifted source. The guardrail fired correctly.

### 4. Repo code paths (local, read-only)

Writers of `*_8h_funding.csv`:

- `scripts/fetch_funding_rest.py` → `save_to_csv()` opens `DATA_DIR /
  f"{symbol}_8h_funding.csv"` in mode `"w"` (full rewrite per symbol).
  `SYMBOLS = [BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, ADAUSDT, DOTUSDT, AVAXUSDT,
  LINKUSDT, MATICUSDT, XRPUSDT]` — **exactly** the observed mtime ordering.
  `DATA_DIR = Path("data")` is **relative**; `qnty-data-refresh.sh` does
  `cd "$REPO_DIR"` first, so it resolves to `/srv/qnty/repo/data` — the same
  directory the verifier reads via `--data-dir /srv/qnty/repo/data`.
  (Note: `qnty-data-refresh.sh` sets an unused `DATA_DIR=/srv/qnty/data` shell
  var; the effective path is the Python relative `data/` under the repo. Harmless
  here but worth cleaning up later.)
- `ops/bin/qnty-data-refresh.sh` → invokes `fetch_ohlcv_rest.py` then
  `fetch_funding_rest.py`. Triggered only by `qnty-data-refresh.service`/`.timer`.

Verifier / snapshot / loader open funding CSVs **read-only** — proven:

```bash
grep -nE "open\(|to_csv|\.write\(|'w'|\"w\"" \
  quantbot/paper/sqlite_verify.py quantbot/paper/funding_source_snapshot.py \
  quantbot/paper/funding_coverage.py quantbot/data/funding_loader.py
# only matches:
#   funding_coverage.py:138  csv_path.open("r", newline=…)
#   funding_coverage.py:465  funding_ledger_path.open("r", …)
#   sqlite_verify.py:2321    resolved.open("r", newline=…)
```

No write-mode open, no `to_csv`, no `.write()` on any CSV in the verifier path.
**The verifier cannot and did not mutate the funding CSVs.**

---

## What was NOT touched

- No funding CSV mutated (all VM reads: `sha256sum`, `stat`, `wc -l`, `ls`).
- No prod/shadow DB read or opened (not even read-only) in this diagnosis.
- No official report read or overwritten.
- No writer / trader / live / backfill / fetch run.
- No service / timer / cron / systemd unit started, stopped, disabled, or edited.
- No code / test / schema / verifier / reporter / writer change.
- No deploy, no cleanup.
- Only one new file added (this receipt).

---

## Root cause

The `/srv/qnty/repo/data/*_8h_funding.csv` files drifted because the
**scheduled `qnty-data-refresh.timer` fired at its regular `16:05 UTC` slot and
ran concurrently with the PR #103 official-report promotion attempt**, rewriting
all ten funding CSVs (via `scripts/fetch_funding_rest.py`) between `16:06:23Z` and
`16:07:25Z` — after the promotion backup (`16:05:26Z`) but before the candidate
verifier (`16:08:09Z`). The fresh verifier therefore saw new source digests and
correctly raised `funding_source_file_digest_mismatch`, refusing promotion. This
is expected, non-anomalous, automated behavior, not verifier-caused drift and not
a manual/unknown edit.

---

## VERDICT

`FUNDING_SOURCE_CSV_DRIFT_DIAGNOSIS_RECORDED_SOURCE_REFRESH_ACTIVE`

- Root cause: active scheduled source refresh (`qnty-data-refresh.timer`,
  `00:05 / 08:05 / 16:05 UTC`) rewriting `*_8h_funding.csv` in the promotion
  window. Guardrail worked: DB unmutated, official report not overwritten.
- `EDGE_UNPROVEN` and `BLOCK_LIVE_INTEGRATION` remain. "clean" = "not killed by
  this gate," not edge/profit/live approval.

### Current blocker

Any fresh full-ledger verifier run against the real shadow DB will keep raising
`funding_source_file_digest_mismatch` because the committed
`funding_source_snapshot` bundle is pinned to the PR #101 source-CSV state, while
the live CSVs are rewritten every 8 hours by `qnty-data-refresh`. Promotion cannot
succeed as long as the verifier reads a moving source that races the refresh timer.

### Recommended next action (choose one; not executed here)

- **A. Source-freeze operational plan** — before a recommit/promotion, gate the
  `qnty-data-refresh.timer` for the promotion window (e.g. transient mask /
  inhibit) so the snapshot rebuild and the candidate verifier observe a stable
  source, then restore the timer. Pro: minimal code change. Con: manual, timing-
  fragile, must be reversible and logged; touches a service (out of scope for
  this read-only task).
- **B. Immutable source-bundle semantics plan** — have the verifier resolve
  funding source rows from the committed, content-addressed
  `funding_source_snapshot` bundle (pinned digests) instead of re-reading live
  `/srv/qnty/repo/data/*.csv`, so a background refresh no longer races promotion.
  Pro: removes the race structurally, no operational timing dance. Con: requires
  verifier/snapshot code + tests (a separate, code-owned task).

Recommendation: pursue **B** as the durable fix; use **A** only as a stopgap if a
promotion is needed before B lands. Both are follow-up tasks — no change is made
here.

Do **not** proceed to repair/promotion from this receipt. This is diagnosis only.
