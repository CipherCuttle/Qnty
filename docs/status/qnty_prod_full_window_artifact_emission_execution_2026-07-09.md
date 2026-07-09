# QNTY_PROD_FULL_WINDOW_ARTIFACT_EMISSION_EXECUTION

**Date:** 2026-07-09
**Branch:** `docs/qnty-prod-full-window-artifact-emission-execution`
**Base:** `origin/main` (commit `5e08c86f3ea83b03b2b05b0939bdbfed5436f743` — PR #125 merge)
**VM:** `viktor@37.27.216.174`
**Lane:** `paper_pnl_v1`
**Mode:** Real emission — additive snapshot + bundle write only
**Guardrails held:** artifact-emission only; no prod/shadow DB mutation; no report overwrite; no
source CSV mutation; no writer/trader/live/backfill/data-refresh; no service/timer/cron/systemd
change; no deploy; no exchange keys; no live integration; no prod report promotion; `/srv/qnty/repo`
main worktree untouched. `EDGE_UNPROVEN` and `BLOCK_LIVE_INTEGRATION` remain in force.

---

## Purpose

Execute the first controlled prod artifact emission using the merged full-window emit CLI: create
the full-window funding-source snapshot and its immutable content-addressed bundle in the prod
`paper_pnl_v1` lane, then prove — with a **read-only** candidate verify — that the full-ledger
clean-carry gate now reaches `CLEAN_NET_OF_CARRY`. The authoritative published prod report is **not**
promoted or overwritten.

---

## Base / merge-commit confirmation

`git fetch origin`; `origin/main` HEAD = `5e08c86f3ea83b03b2b05b0939bdbfed5436f743`. All three
required merge commits are ancestors of `origin/main`:

- PR #123: `0d0af9c0693137471809edb264c6b7ef222017b3` — PRESENT
- PR #124: `c71de82cb855eea451e2a99d75cc8599080a213e` — PRESENT
- PR #125: `5e08c86f3ea83b03b2b05b0939bdbfed5436f743` — PRESENT (HEAD)

---

## Execution environment (module resolution)

- Scratch worktree at `origin/main` (detached HEAD `5e08c86`):
  `/tmp/qnty-emit-exec-20260709T190140Z` — created via `git worktree add --detach`; the
  `/srv/qnty/repo` main worktree (still at `2bd8843`) was **not** modified.
- The VM venv (`/srv/qnty/venv`) is an **editable install pinned to the stale `/srv/qnty/repo`** (a
  meta-path finder). Using it would resolve `quantbot` from the stale checkout, which lacks the merged
  CLI. Emission therefore ran under **`/usr/bin/python3`** (system numpy 2.5.1 / pandas 3.0.3 /
  requests present) with `PYTHONPATH=<scratch>`, empirically confirmed immediately before the run:
  `import quantbot -> /tmp/qnty-emit-exec-20260709T190140Z/quantbot/__init__.py`.

---

## Preflight (baseline hashes — captured before emission)

| Artifact | sha256 |
| --- | --- |
| prod DB `paper_ledger.db` | `94874dab6d82701785fdf7379777b3e8a5850c3f869a42625edd90dcdc18bc11` |
| prod report `paper_verify_report.json` | `2c6af12ba74d92b52d827263225760145c5e7c2eef5b6053ff18779a8f9c10c3` |

Source funding CSVs (`/srv/qnty/repo/data`, 10 `_8h_funding.csv`; the 10 `_8h_ohlcv.csv` were also
hashed and are unchanged):

```
03546caa08ad9dbdd17766ca2f7216ffbdb2f8260535cf06fe9d103080cec481  ADAUSDT_8h_funding.csv
219ec8aa749a53808ccf00d73c4b4fe4c8366d2c70882de12c074dbd9d9741dd  AVAXUSDT_8h_funding.csv
fc909f3309dd41af57b12dcb84e78fea3e443ff36eb4a78e9a3427b09376232a  BNBUSDT_8h_funding.csv
60909583ab00c2e6353dff0dd6b18c72ac020691410401ea71ab8716b1ab27a6  BTCUSDT_8h_funding.csv
4417bf586a47f9ef45791eee63c7eff0bc9ecf3730784b477e1760b313bfa78d  DOTUSDT_8h_funding.csv
e266c83d620e0a706244ef7883efd86e5965aa4a120ca5dbaaab107654b43217  ETHUSDT_8h_funding.csv
38ebd4b1c16c1932eee4446083f5c693451818e94a14ab248a339ecf59acc0c6  LINKUSDT_8h_funding.csv
de4a2844e1b79a27e4aa0e2085b3d656c2c1fdfbdb921d5e688cccb0591a663f  MATICUSDT_8h_funding.csv
6503fbcd5410673ec822e4f4a7893299ec36cf2197e6a2a800ce3c13db157ff8  SOLUSDT_8h_funding.csv
649144760b074a90c0bbfe8e9cbe3167990e788e4b66ec31d73a55591a0e95c3  XRPUSDT_8h_funding.csv
```

- Snapshot dir `funding_source_snapshots/`: **19** existing per-batch snapshots
  (`funding_source_snapshot_v1_<hash>.json`); **no** full-window snapshot present.
- Bundle dir `funding_source_bundles/`: **did not exist** (first full-window emission).
- Process check: **no** QNTY writer/trader/live/backfill/data-refresh process running.
- systemd/cron: state read-out only; **no** change needed. Next ledger/CSV-mutating timers
  (`qnty-paper-pnl`, `qnty-data-refresh`, `qnty-shadow-run`) all ~5h out (Fri 2026-07-10 00:0x UTC);
  emission window safe.

---

## Emission (real run — no `--dry-run`)

```bash
PYTHONPATH=<scratch> /usr/bin/python3 -m quantbot.paper.funding_source_full_window_emit_cli \
  --db /srv/qnty/output/paper_pnl_v1/paper_ledger.db \
  --funding-source-dir /srv/qnty/repo/data \
  --output-dir /srv/qnty/output/paper_pnl_v1 \
  --qnty-git-commit 5e08c86f3ea83b03b2b05b0939bdbfed5436f743
```

The emit path opens the DB **read-only** (`mode=ro` + `PRAGMA query_only=ON`), computes the
full-ledger funding window across every committed batch, freezes the required source rows, and writes
exactly one `full_window` snapshot (bound to the latest committed batch id) plus one immutable
content-addressed bundle. Exit code `0`. JSON:

```json
{
  "status": "OK",
  "snapshot_path": "/srv/qnty/output/paper_pnl_v1/funding_source_snapshots/funding_source_full_window_snapshot_v1_batch57.json",
  "snapshot_sha256": "37ef84f31b5ba13900fd3052811b5d06f96b37aaa785ad225a386a0ca525a6bb",
  "bundle_path": "/srv/qnty/output/paper_pnl_v1/funding_source_bundles/funding_source_bundle_v1_0a66bb38fd5d4f0c77f9cf1be58ce0979cf6672bad5733994ec9ad37d7758704.json",
  "bundle_sha256": "af27385a44e0d942af17c28bed5b7f47b2f08be287cbf75eda00807a2c613b6c",
  "target_batch_id": 57,
  "lane_id": "paper_pnl_v1",
  "evaluation_window": { "start": "2026-06-21T00:00:00", "end": "2026-07-09T08:00:00" },
  "resolved_funding_source_dir": "/srv/qnty/repo/data"
}
```

### Artifact assertions (step 10)

- Exactly **one** full-window snapshot emitted: `funding_source_full_window_snapshot_v1_batch57.json`.
- Exactly **one** immutable bundle emitted (bundle dir created fresh, count = 1).
- Snapshot path under `…/funding_source_snapshots/` ✓; bundle path under `…/funding_source_bundles/` ✓.
- `snapshot_payload.snapshot_scope = "full_window"` ✓.
- Snapshot evaluation window `{2026-06-21T00:00:00Z → 2026-07-09T08:00:00Z}` **equals** the DB
  full-ledger funding window (`SELECT MIN(window_start), MAX(window_end) FROM funding`) ✓; latest
  committed batch = 57 ✓.
- Provenance carries **absolute** `resolved_funding_source_dir = /srv/qnty/repo/data`
  (`provenance.source_path_resolution` and `snapshot_metadata`) ✓.
- Bundle is **content-addressed**: `bundle_payload.source_bundle_sha256 =
  recompute_bundle_sha256(bundle_payload) = 0a66bb38…8704` = filename hash ✓; it cross-links
  `snapshot_bundle_sha256 = af27385a…` and `snapshot_sha256 = 37ef84f3…`.
- `qnty_git_commit = 5e08c86f3ea83b03b2b05b0939bdbfed5436f743` (not null) ✓.
- Coverage `complete`; snapshot `reason_codes = []`.

---

## Read-only candidate verify (step 11–12 — report NOT replaced)

The full-ledger clean-carry gate was exercised with the pure read-only immutable CLI, which opens
`file:<abs>?mode=ro&immutable=1` + `PRAGMA query_only=ON` and **has no write mode** (never touches
`paper_verify_report.json`/receipt/log or `-wal`/`-shm`):

```bash
PYTHONPATH=<scratch> /usr/bin/python3 -m quantbot.paper.sqlite_verify \
  --db-path /srv/qnty/output/paper_pnl_v1/paper_ledger.db \
  --data-dir /srv/qnty/repo/data \
  --read-only --json [--strict-clean-carry]
```

Candidate result:

| Field | Value |
| --- | --- |
| `status` | `OK` |
| `resolved_funding_source_dir` | `/srv/qnty/repo/data` |
| `source_path_available` | `True` |
| `source_path_resolution_mode` | `explicit_data_dir` |
| `funding_clean_carry.full_window_scope_required` | `True` |
| `funding_clean_carry.full_window_snapshot_selected_path` | `…/funding_source_full_window_snapshot_v1_batch57.json` |
| `funding_clean_carry.snapshot_status` | `present_valid` |
| `funding_clean_carry.funding_coverage_decision` | `complete` |
| `funding_clean_carry_decision` | **`CLEAN_NET_OF_CARRY`** |
| `funding_clean_carry_reason_codes` | `[]` |
| `funding_source_coverage_verdict` | `CLEAN_NET_OF_CARRY` |
| `--strict-clean-carry` process exit | `0` |

Step-12 criteria:

- Full-window sidecar **selected** (batch57, `present_valid`) ✓
- `funding_source_snapshot_window_mismatch` — **gone** (full-window scope selected; window matches) ✓
- `source_path_unavailable` — **gone** (`explicit_data_dir`, `source_path_available=True`) ✓
- `CLEAN_NET_OF_CARRY` **reached** ✓
- reason codes **empty** ✓

### Documented nuance — source-dir resolution is invocation-dependent

A candidate run of the standard `scripts/qnty-paper-sqlite-verify.py` (which does **not** expose a
`--data-dir` flag) reports `source_path_unavailable`. Root cause: that path resolves the source dir
from the **DB-linked per-batch** snapshot stamp, and the current prod DB-linked per-batch snapshot
(`…bae4788e…`, legacy default-mode) has `provenance.source_path_resolution = null` and only
**relative** `entity_inputs` paths (`data/…_8h_funding.csv`) → no absolute parent → unavailable. It
does **not** consult the full-window snapshot's absolute provenance. The authoritative read-only
clean-carry CLI (`python -m quantbot.paper.sqlite_verify --read-only --data-dir <abs>`) supplies the
source dir explicitly and reaches `CLEAN_NET_OF_CARRY`. The clean verdict below is therefore
conditional on the verify invocation providing the funding source dir (as prod's publish path does
from its `/srv/qnty/repo` working directory). This is an invocation/config property, not a defect in
the emitted artifact.

---

## Postflight (step 13 — additive-only, no mutation)

| Artifact | sha256 | vs preflight |
| --- | --- | --- |
| prod DB `paper_ledger.db` | `94874dab…bc11` | **UNCHANGED** |
| prod report `paper_verify_report.json` | `2c6af12b…10c3` | **UNCHANGED** |
| all 10 source funding CSVs | (as preflight) | **UNCHANGED** |

- prod DB `-wal` = 0 bytes (no uncommitted frames); the committed ledger lives in the main file,
  whose sha256 is byte-identical. A transient `-shm` timestamp reflects read-only WAL access during
  verification, not a committed-data mutation.
- Snapshot dir: **19 → 20** (exactly +1: the full-window batch57 snapshot). All 19 prior per-batch
  snapshots untouched.
- Bundle dir: newly created, **exactly one** bundle (`…0a66bb38…8704.json`).
- systemd timers: unchanged (7 qnty/paper timers, state read-out only); no `.service`/`.timer`/cron
  edited.
- No writer/trader/live/backfill/data-refresh process was spawned during the operation.

---

## Emitted artifacts (identity)

| Artifact | Path | Digest |
| --- | --- | --- |
| Full-window snapshot | `funding_source_snapshots/funding_source_full_window_snapshot_v1_batch57.json` | `snapshot_sha256 = 37ef84f31b5ba13900fd3052811b5d06f96b37aaa785ad225a386a0ca525a6bb` |
| Immutable bundle | `funding_source_bundles/funding_source_bundle_v1_0a66bb38fd5d4f0c77f9cf1be58ce0979cf6672bad5733994ec9ad37d7758704.json` | `source_bundle_sha256 = 0a66bb38…8704` |

Both are generated lane artifacts under `/srv/qnty/output/…` and are **not** committed to git (this
PR is docs-only).

---

## Verdict

**QNTY_PROD_FULL_WINDOW_ARTIFACT_EMISSION_EXECUTION_RECORDED_CLEAN**

The first controlled prod full-window artifact emission succeeded additively: one `full_window`
snapshot (batch57, full-ledger window, absolute source provenance) and one content-addressed
immutable bundle were written to the prod `paper_pnl_v1` lane. The read-only candidate verify reaches
`CLEAN_NET_OF_CARRY` with empty reason codes — `funding_source_snapshot_window_mismatch` and
`source_path_unavailable` both cleared (the latter when the verify invocation supplies the funding
source dir, as prod's publish path does). No prod/shadow DB mutation, no report overwrite/promotion,
no source CSV mutation, no service/timer/cron change, no writer/trader/live/backfill/data-refresh run.
`EDGE_UNPROVEN` and `BLOCK_LIVE_INTEGRATION` remain in force.
