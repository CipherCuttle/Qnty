# QNTY_FULL_WINDOW_EMIT_PROD_CLI_DRY_RUN_VALIDATION

**Date:** 2026-07-09
**Branch:** `docs/qnty-full-window-emit-prod-cli-dry-run-validation`
**Base:** `origin/main` (commit `0d0af9c0693137471809edb264c6b7ef222017b3` — PR #123 merge)
**VM:** `viktor@37.27.216.174`
**Lane:** `paper_pnl_v1`
**Mode:** Dry-run only

---

## Purpose

Validate the newly merged CLI entrypoint (`funding_source_full_window_emit_cli.py`) against the real prod `paper_pnl_v1` lane in **dry-run mode only**, proving the installed/module CLI resolves correctly on the VM and can inspect the real paths without writing snapshot/bundle/report artifacts.

---

## Procedure

1. `git fetch origin` — confirmed `origin/main` includes merge commit `0d0af9c`
2. Created branch `docs/qnty-full-window-emit-prod-cli-dry-run-validation` at `origin/main`
3. SSH to VM (`viktor@37.27.216.174`)
4. Created scratch worktree at `/tmp/qnty_full_window_emit_cli_dry_run_20260709_worktree` at `origin/main` (detached HEAD) — **not** modifying `/srv/qnty/repo` main worktree
5. Installed package from scratch checkout (`pip install -e . --break-system-packages`)
6. Verified CLI resolves:
   - `python3 -m quantbot.paper.funding_source_full_window_emit_cli --help` — **OK**
   - `~/.local/bin/qnty-full-window-emit --help` — **OK** (not on non-interactive PATH)
7. Captured preflight hashes (prod DB, prod report, 20 source CSVs, snapshot/bundle dirs)
8. Executed dry-run with `--dry-run` flag against real prod paths
9. Captured JSON output
10. Verified postflight hashes unchanged
11. Cleaned up scratch worktree
12. Wrote this receipt

---

## Dry-Run JSON Output

```json
{
  "status": "DRY_RUN",
  "db": "/srv/qnty/output/paper_pnl_v1/paper_ledger.db",
  "funding_source_dir": "/srv/qnty/repo/data",
  "output_dir": "/tmp/qnty_full_window_emit_cli_dry_run_20260709",
  "generated_at_utc": "2026-07-09T18:01:19.733682+00:00",
  "qnty_git_commit": null
}
```

### Dry-Run Output Validation

| Check | Result |
|-------|--------|
| `status` is `"DRY_RUN"` | ✅ PASS |
| `db` path is absolute | ✅ PASS |
| `funding_source_dir` path is absolute | ✅ PASS |
| `output_dir` path is absolute | ✅ PASS |
| No snapshot was created | ✅ PASS (dry-run) |
| No bundle was created | ✅ PASS (dry-run) |
| No report was touched | ✅ PASS (dry-run) |

---

## Preflight Hashes

### Prod DB
```
94874dab6d82701785fdf7379777b3e8a5850c3f869a42625edd90dcdc18bc11  paper_ledger.db
```

### Prod Report
```
2c6af12ba74d92b52d827263225760145c5e7c2eef5b6053ff18779a8f9c10c3  paper_verify_report.json
```

### Source CSVs (20 files)
```
78f9d96b93103fbf28aa254c82efe37e32e3a6b6e40013ee2e243d744cce06c2  ETHUSDT_8h_ohlcv.csv
e266c83d620e0a706244ef7883efd86e5965aa4a120ca5dbaaab107654b43217  ETHUSDT_8h_funding.csv
219ec8aa749a53808ccf00d73c4b4fe4c8366d2c70882de12c074dbd9d9741dd  AVAXUSDT_8h_funding.csv
fc909f3309dd41af57b12dcb84e78fea3e443ff36eb4a78e9a3427b09376232a  BNBUSDT_8h_funding.csv
649144760b074a90c0bbfe8e9cbe3167990e788e4b66ec31d73a55591a0e95c3  XRPUSDT_8h_funding.csv
38ebd4b1c16c1932eee4446083f5c693451818e94a14ab248a339ecf59acc0c6  LINKUSDT_8h_funding.csv
8a9983c65312135f7a55dc9f2483c4aefe5c1b19189b015832b0cae5b62e52f8  XRPUSDT_8h_ohlcv.csv
5e0f8fdc36bb42fe392a2327533a386c0c3aaebe510ea58022b27234807538b2  LINKUSDT_8h_ohlcv.csv
90c10f05590445466cf029deac1ca433dbc22c1174f7ee01d0029c828053e644  AVAXUSDT_8h_ohlcv.csv
03546caa08ad9dbdd17766ca2f7216ffbdb2f8260535cf06fe9d103080cec481  ADAUSDT_8h_funding.csv
ee03ce02c218a59f2698b8969a4d699af8642de20ef1e0798d7d3798b2c5541c  BNBUSDT_8h_ohlcv.csv
f4d409de00bc7446f1d0515d8bbbc02d096a40a0cc3abb4ec626fc9a46a39ff1  DOTUSDT_8h_ohlcv.csv
a63eedc017bc5ab2abb963d547ffca479f99742e19917f8f988e31a3f54f857d  ADAUSDT_8h_ohlcv.csv
fb21209267593a356018a7f32f305a919d345054e7e13eb7bccaee06206a54c4  BTCUSDT_8h_ohlcv.csv
6503fbcd5410673ec822e4f4a7893299ec36cf2197e6a2a800ce3c13db157ff8  SOLUSDT_8h_funding.csv
4417bf586a47f9ef45791eee63c7eff0bc9ecf3730784b477e1760b313bfa78d  DOTUSDT_8h_funding.csv
ed62ddc0ca0e5f2e7d3b0ce0594e47be13c6bfb23fd4d7c835d092c4cc9da9b9  SOLUSDT_8h_ohlcv.csv
de4a2844e1b79a27e4aa0e2085b3d656c2c1fdfbdb921d5e688cccb0591a663f  MATICUSDT_8h_funding.csv
0ada906693dea58afea3919b1bfadc52cf9730538534fb75ca1e9cc6ebf4bcbd  MATICUSDT_8h_ohlcv.csv
60909583ab00c2e6353dff0dd6b18c72ac020691410401ea71ab8716b1ab27a6  BTCUSDT_8h_funding.csv
```

### Snapshot Dir
`/srv/qnty/output/paper_pnl_v1/funding_snapshots/` — **DOES NOT EXIST**

### Bundle Dir
`/srv/qnty/output/paper_pnl_v1/funding_bundles/` — **DOES NOT EXIST**

---

## Postflight Hashes

| Artifact | Preflight | Postflight | Status |
|----------|-----------|------------|--------|
| Prod DB | `94874dab...` | `94874dab...` | ✅ UNCHANGED |
| Prod Report | `2c6af12b...` | `2c6af12b...` | ✅ UNCHANGED |
| Source CSVs (20) | all hashes recorded | all hashes identical | ✅ UNCHANGED |
| Snapshot Dir | absent | absent | ✅ UNCHANGED |
| Bundle Dir | absent | absent | ✅ UNCHANGED |
| Output Dir (`/tmp`) | n/a | empty (only `.` and `..`) | ✅ NO ARTIFACTS |

**Hash Comparison Verdict: PASS** — All prod artifacts unchanged. No mutations detected.

---

## Guardrail Compliance

| Guardrail | Status |
|-----------|--------|
| Dry-run only | ✅ |
| No prod DB mutation | ✅ (hash unchanged) |
| No shadow DB mutation | ✅ (not touched) |
| No official report overwrite | ✅ (hash unchanged) |
| No source CSV mutation | ✅ (all 20 hashes unchanged) |
| No prod snapshot write | ✅ (no snapshot dir created) |
| No prod bundle write | ✅ (no bundle dir created) |
| No full emission artifact write | ✅ (output dir empty) |
| No service/timer/cron/systemd mutation | ✅ (not touched) |
| No writer/trader/live/backfill/data-refresh run | ✅ |
| No deploy | ✅ |
| No exchange keys | ✅ |
| No live integration | ✅ |
| No prod report promotion | ✅ |
| `/srv/qnty/repo` main worktree unmodified | ✅ (scratch worktree used) |
| `EDGE_UNPROVEN` remains | ✅ |
| `BLOCK_LIVE_INTEGRATION` remains | ✅ |

---

## Issues Encountered

1. **PEP 668 externally-managed-environment** — `pip install -e .` requires `--break-system-packages` flag. Resolved.
2. **VM uses `python3`, not `python`** — CLI must be invoked as `python3 -m quantbot.paper.funding_source_full_window_emit_cli`.
3. **`qnty-full-window-emit` installed to `~/.local/bin`** — not on non-interactive SSH PATH; verified via explicit full path. Consider adding to PATH or documenting for future use.
4. **`qnty_git_commit: null`** — expected for detached HEAD scratch worktree; auto-detection does not resolve. Does not affect dry-run correctness.

---

## Verdict

```
QNTY_FULL_WINDOW_EMIT_PROD_CLI_DRY_RUN_VALIDATION_RECORDED
```

The CLI entrypoint resolves correctly on the VM (both as a module and as an installed command), correctly inspects real prod paths, produces valid `DRY_RUN` status JSON output, and writes zero snapshot/bundle/report artifacts. All prod data remains unmodified. The validation is recorded and the guardrails are satisfied.

---

## Files Modified

- `docs/status/qnty_full_window_emit_prod_cli_dry_run_validation_2026-07-09.md` — this receipt (new)
- `.roo/dry_run_results.json` — raw JSON output (temporary, not committed)
- `.roo/dry_run_validation.txt` — full validation summary (temporary, not committed)