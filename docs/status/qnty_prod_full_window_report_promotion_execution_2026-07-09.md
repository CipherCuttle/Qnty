# QNTY_PROD_FULL_WINDOW_REPORT_PROMOTION_EXECUTION

**Date:** 2026-07-09
**VM:** `viktor@37.27.216.174` (host `ubuntu-4gb-hel1-1-qnty`) — reachable, mutation-authorized
**Lane:** `paper_pnl_v1`
**Base:** `origin/main` HEAD `7414783bb87e024780ea98f8300c2890e96f5de0` (PR #127 merge)
**Plan:** `docs/plans/QNTY_PROD_FULL_WINDOW_REPORT_PROMOTION_PLAN.md`

---

## Verdict

```
QNTY_PROD_FULL_WINDOW_REPORT_PROMOTION_HALTED_SCHEMA_MISMATCH
```

**No report promoted. No prod report overwritten. No prod DB / source CSV / snapshot /
bundle mutation. No backup written. No VM state change of any kind.**
`EDGE_UNPROVEN` and `BLOCK_LIVE_INTEGRATION` remain in force.

This is **not** a VM-access BLOCK. The VM was reachable and mutation-authorized
(`VM_SSH_OK`, host `ubuntu-4gb-hel1-1-qnty`, user `viktor`). Execution halted on the
plan's own schema-compatibility gate (plan §3 schema note / §8 stop conditions).

---

## What happened

The candidate report was generated **read-only** exactly as the plan §3 prescribes, all
data/DB acceptance gates (G1–G11) passed, but the read-only verifier's `--json` payload is
**not schema-compatible** with the published official `paper_verify_report.json`. Per plan
§3 ("If the read-only `--json` shape is not a drop-in for the published report schema, **stop
and escalate** — do not hand-edit or synthesize a report") and §8 stop conditions, promotion
was aborted before any backup or replacement.

---

## Preconditions (all confirmed before candidate generation)

| # | Precondition | Result |
|---|--------------|--------|
| P1 | PR #126 merged (`dcd028f`), PR #127 merged (`7414783`); execution receipt present. | ✅ |
| P2 | Full-window snapshot present in prod lane. | ✅ `funding_source_full_window_snapshot_v1_batch57.json` (file sha256 `75bd3af0…e88c`) |
| P3 | Immutable bundle present in prod lane. | ✅ `funding_source_bundle_v1_0a66bb38…8704.json` (file sha256 `8d116171…872f`) |
| P4 | Read-only candidate reaches `CLEAN_NET_OF_CARRY`. | ✅ `--strict-clean-carry` exit 0; decision `CLEAN_NET_OF_CARRY`, reason codes `[]` |
| P5 | Preflight hashes captured. | ✅ DB `94874dab…bc11`; official report `2c6af12b…10c3`; 20 source CSVs recorded (below) |
| P6 | No writer/trader/live/backfill/data-refresh running. | ✅ `pgrep` for `data-refresh`/`paper_run`/`qnty-shadow`/`quantbot.*run` → only the ssh command self-match; no genuine process |
| P7 | Verifier resolves from scratch worktree, not stale `/srv/qnty/repo`. | ✅ `__file__ = /tmp/qnty_scratch_promotion/quantbot/paper/sqlite_verify.py` (scratch @ `7414783`) |

Stale `/srv/qnty/repo` HEAD: `2bd88430` (untouched — see cleanup below).

---

## Candidate generation (read-only, plan §3)

```
TS = 20260709T200555Z
PYTHONPATH=/tmp/qnty_scratch_promotion /usr/bin/python3 -m quantbot.paper.sqlite_verify \
  --db-path /srv/qnty/output/paper_pnl_v1/paper_ledger.db \
  --data-dir /srv/qnty/repo/data \
  --read-only --json --strict-clean-carry \
  > /tmp/paper_verify_report.candidate_20260709T200555Z.json
```

- `--strict-clean-carry` exit code: **0**.
- Candidate sha256: `a061da08cf0a43ecc0b236ac123f58d630a6de6eca88df7748eb10b96c12cd49`.
- Post-generate immutability re-check: DB `94874dab…bc11` UNCHANGED; official report
  `2c6af12b…10c3` UNCHANGED; no `-wal`/`-shm` sidecars created.

---

## Data / DB acceptance gates (§4) — ALL PASS

| # | Gate | Result |
|---|------|--------|
| G1 | Candidate batch id == DB latest committed batch (57). | ✅ `batches=57`; `MAX(batch_id) ledger_batches = 57` |
| G2 | Candidate watermark == DB funding watermark (`2026-07-09T08:00:00`). | ✅ snapshot `batch_end_watermark = 2026-07-09T08:00:00`; DB `MAX(window_end)=2026-07-09T08:00:00` |
| G3 | Candidate `status = OK`. | ✅ |
| G4 | Candidate `failure_count = 0`. | ✅ |
| G5 | `funding_clean_carry_decision = CLEAN_NET_OF_CARRY`. | ✅ |
| G6 | `funding_clean_carry_reason_codes = []`. | ✅ |
| G7 | Full-window sidecar selected (`…batch57.json`, `snapshot_status = present_valid`). | ✅ `full_window_snapshot_selected_path` = batch57; `funding_source_snapshot_status = present_valid` |
| G8 | `funding_source_snapshot_window_mismatch` absent from reason codes. | ✅ (reason codes empty) |
| G9 | `source_path_unavailable` absent (`source_path_available = True`, `explicit_data_dir`). | ✅ `source_path_available=true`, `source_path_resolution_mode=explicit_data_dir`, `resolved_funding_source_dir=/srv/qnty/repo/data` |
| G10 | Prod DB hash unchanged (`94874dab…bc11`). | ✅ |
| G11 | Source CSV hashes unchanged. | ✅ (all 20 unchanged, below) |

---

## Schema-compatibility gate (§3 note / §8) — **FAIL → HALT**

The read-only `sqlite_verify --json` report is a **diagnostic verifier report**, not the
`verify_and_publish` **publication** schema of the official file. The CLI's own help states
it "never creates … `paper_verify_report.json`/receipt/log files (that is
`verify_and_publish`'s job, not this CLI's)."

Top-level key diff (official 42 keys vs candidate 36 keys; 30 shared):

**In official, NOT in candidate (12 — publication/provenance fields that would be lost):**
`authoritative`, `content_digests`, `content_sha256`, `current_verdict`, `exit_code`,
`failures`, `schema_version`, `snapshot_identity`, `trusted`, `verified_at`, `verifier`,
`verifier_version`.

**In candidate, NOT in official (6 — read-only-CLI diagnostics that would be injected):**
`db_mutation_performed`, `query_only_pragma_enabled`, `read_only`, `sqlite_open_mode`,
`verifier_cli_contract_version`, `wal_shm_files_created`.

Promoting the candidate would strip trust/provenance metadata (`authoritative`, `trusted`,
`verified_at`, `verifier_version`, `schema_version`, `content_digests`, `content_sha256`,
`current_verdict`) that consumers of the official report rely on, and inject read-only
diagnostic fields. That is a semantic downgrade, **not** a drop-in replacement. The plan
forbids hand-editing/synthesizing a report to bridge the gap.

Note: the current official report still carries
`funding_clean_carry_decision = CAVEATED_ENGINE_SEMANTICS` (the pre-full-window artifact),
consistent with the state description — but the read-only CLI is not the correct producer
for its replacement.

---

## Final immutability (post-halt) — everything UNCHANGED

| Artifact | sha256 | State |
|----------|--------|-------|
| Prod DB `paper_ledger.db` | `94874dab…bc11` | UNCHANGED |
| Official report `paper_verify_report.json` | `2c6af12b…10c3` | UNCHANGED (not promoted) |
| Snapshot `…batch57.json` | `75bd3af0…e88c` | UNCHANGED |
| Bundle `…0a66bb38…8704.json` | `8d116171…872f` | UNCHANGED |
| Backup `…bak_<ts>` | — | NOT CREATED (correct; promotion never entered §5) |

Source CSV sha256 (all 20, unchanged pre/post):

```
03546caa…c481  ADAUSDT_8h_funding.csv     a63eedc0…857d  ADAUSDT_8h_ohlcv.csv
219ec8aa…41dd  AVAXUSDT_8h_funding.csv    90c10f05…e644  AVAXUSDT_8h_ohlcv.csv
fc909f33…232a  BNBUSDT_8h_funding.csv     ee03ce02…541c  BNBUSDT_8h_ohlcv.csv
60909583…27a6  BTCUSDT_8h_funding.csv     fb212092…54c4  BTCUSDT_8h_ohlcv.csv
4417bf58…a78d  DOTUSDT_8h_funding.csv     f4d409de…9ff1  DOTUSDT_8h_ohlcv.csv
e266c83d…3217  ETHUSDT_8h_funding.csv     78f9d96b…06c2  ETHUSDT_8h_ohlcv.csv
38ebd4b1…c0c6  LINKUSDT_8h_funding.csv    5e0f8fdc…38b2  LINKUSDT_8h_ohlcv.csv
de4a2844…663f  MATICUSDT_8h_funding.csv   0ada9066…bcbd  MATICUSDT_8h_ohlcv.csv
6503fbcd…7ff8  SOLUSDT_8h_funding.csv     ed62ddc0…a9b9  SOLUSDT_8h_ohlcv.csv
64914476…95c3  XRPUSDT_8h_funding.csv     8a9983c6…52f8  XRPUSDT_8h_ohlcv.csv
```

---

## Cleanup / trace

- Scratch worktree `/tmp/qnty_scratch_promotion` (detached @ `7414783`) removed via
  `git worktree remove --force` + `worktree prune`.
- `/srv/qnty/repo` HEAD `2bd88430` UNCHANGED; working tree clean. (Only additive
  `git fetch` remote-tracking refs added; no working-tree or HEAD change.)
- Candidate `/tmp/paper_verify_report.candidate_20260709T200555Z.json`
  (sha256 `a061da08…cd49`) retained for audit.
- No systemd/cron/timer inspected-mutated; no service touched.

---

## Escalation / next task

The promotion cannot proceed via the read-only `sqlite_verify --json` CLI as the plan §3
command assumes — its output is not the published-report schema. Options to resolve
(decision for Viktor, none executed here):

1. Extend the plan to define a **publication-schema** candidate producer that emits the
   full `verify_and_publish` document (with `authoritative`/`trusted`/`content_digests`/
   provenance) read-only from the already-emitted full-window sidecar — then re-run the
   §4 gates + a schema-equality gate (candidate key set == official key set).
2. Or promote via the actual `verify_and_publish` path pinned to the full-window sidecar
   (requires a plan defining exactly which write path is permitted, since the current plan
   forbids report re-generation via the writer).

Recommended next task id: `QNTY_PROD_FULL_WINDOW_REPORT_PROMOTION_SCHEMA_RECONCILIATION_PLAN`.
