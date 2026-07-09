# QNTY Prod Full-Window Immutable Bundle Build + Read-Only Eval (BLOCKED)

**Task:** `QNTY_PROD_FULL_WINDOW_IMMUTABLE_BUNDLE_BUILD_AND_READONLY_EVAL_GIT_OWNED`
**Date (UTC):** 2026-07-09
**Verdict:** `QNTY_PROD_FULL_WINDOW_IMMUTABLE_BUNDLE_BUILD_AND_READONLY_EVAL_BLOCKED`
**Strategy label:** `EDGE_UNPROVEN` (unchanged) · `BLOCK_LIVE_INTEGRATION` (unchanged)

Attempt to build an **immutable, content-addressed prod full-window funding-source
bundle** for `paper_pnl_v1` (bound to the latest committed prod ledger state) and run a
read-only bundle-mode clean-carry eval. **Outcome: BLOCKED at build.** A full-window prod
bundle is **not constructible from existing prod artifacts** with existing `origin/main`
code, because no committed prod snapshot covers the full-ledger window and the bundle
builder freezes a single snapshot. No prod artifact was mutated; a candidate 8h bundle was
built to `/tmp` only, as evidence. All figures are paper diagnostics — no edge/profit/live
claim.

---

## PLAN

1. Git prep: fetch, confirm PR #118 merge on `origin/main`, branch off it.
2. VM read-only preflight (identity, procs/timers, prod inventory + hashes).
3. Determine target prod full-ledger window; enumerate every snapshot's `evaluation_window`.
4. Test constructibility: does any committed snapshot cover the full-ledger window?
5. Build candidate bundle from the DB-linked (selected) snapshot in a scratch worktree,
   write to `/tmp` only, measure its coverage.
6. Compare against the full-ledger gate's requirement; decide CLEAN vs BLOCKED.
7. Docs-only receipt (this file). No prod bundle written (see rationale).

---

## CHANGESET

Single added file (docs-only):

- `docs/status/qnty_prod_full_window_bundle_build_readonly_eval_2026-07-09.md`

No code, no config, **no prod bundle written**, no prod DB/report/CSV/snapshot mutated,
no service/timer/cron change.

---

## VERIFY

### Environment / identity

| Item | Value |
|---|---|
| VM | `viktor@37.27.216.174` (`ubuntu-4gb-hel1-1-qnty`), uid 1000 |
| VM time at audit | `2026-07-09T09:09:53Z` |
| VM repo HEAD (`/srv/qnty/repo`, main worktree untouched, before & after) | `2bd88430fe6b2881aaa2b32947002217d3e02ba5` |
| Scratch worktree (detached, then removed) | `/tmp/qnty_scratch_wt_20260709T091242Z` @ `6c8799e6…` |
| Local branch | `docs/qnty-prod-full-window-bundle-build-readonly-eval` |
| Local HEAD / base | `6c8799e6836f5cc0386394d71d4fceec70c9c1c1` (PR #118 merge) |
| `origin/main` contains PR #118 merge | yes |

**SQLite access:** `file:<db>?mode=ro` + `PRAGMA query_only=ON`. Prod is live-written
(`qnty-paper-pnl.timer` next 16:21Z; `-wal` empty/checkpointed at audit); reads taken in
the safe window (~09:1x Z). Editable-install workaround used for the scratch worktree:
dropped `__editable__` meta-path finders, prepended the worktree to `sys.path`, and
confirmed `quantbot.__file__ = /tmp/qnty_scratch_wt_…/quantbot/__init__.py`.

### Process / service scan

No `writer`/`trader`/`live`/`backfill`/`data-refresh`/`paper-pnl`/`verify` process running
at audit time. Timers listed read-only (unchanged): `qnty-paper-pnl` (next 16:21Z),
`qnty-data-refresh` (next 16:05Z), `qnty-shadow-run` (next 16:10Z), watchdog/healthcheck/
health-receipt/daily-summary. **None mutated.**

### Prod preflight inventory (sha256, read-only) — `/srv/qnty/output/paper_pnl_v1`

| Artifact | Size | mtime (UTC) | sha256 |
|---|---|---|---|
| `paper_ledger.db` | 245760 | 2026-07-09 08:20:40 | `4b947febc8373ca065f9fdd5b8705dd311a1e2feba73e71cb714e6e73e432773` |
| `paper_verify_report.json` | 58289 | 2026-07-09 08:20:40 | `5bd406d6f4b2f8fa8c71d5f91c9e2865e997bcf917ddb9e359fecc7df9071d00` |
| `paper_ledger.db-wal` | 0 (checkpointed) | 2026-07-09 08:20:40 | — |
| `funding_source_snapshots/` | — | — | 18 per-batch sidecars (latest `aded2f13…`, 08:20) |
| `funding_source_bundles/` | — | — | **absent (does not exist)** |

Source CSVs `/srv/qnty/repo/data/*_8h_funding.csv` (10 symbols) — **context only, not
mutated.** Before/after sha256 identical (e.g. `BTCUSDT` `d3440041…`, `ETHUSDT`
`f2a0d592…`, `XRPUSDT` `38db9b9c…`, `BNBUSDT` `49ac518a…`, `SOLUSDT` `be95f3fe…`).

### Target prod full-ledger window (from prod DB, read-only)

| Field | Value |
|---|---|
| full-ledger funding window (`MIN(window_start)`→`MAX(window_end)` over `funding`) | `2026-06-21T00:00:00` → `2026-07-09T00:00:00` |
| funding rows / symbols | 118 / 5 (BTC, ETH, SOL, XRP, BNB) |
| latest committed batch id | 56 |
| latest watermark (`new_watermark_bar_ts`) | `2026-07-09T00:00:00` |
| batch git_sha | `2bd88430…` |
| DB-linked snapshot on batch 56 | `funding_source_snapshot_v1_aded2f13…json` (sha `e1a30847…`) |
| batch-56 snapshot `source_bundle_sha256` (bundle binding key) | `aded2f1348f3a198372d9916e242df84fe76dd2cc5f504f6c0e7a6f24cc0b698` |
| batch-56 snapshot `evaluation_window` | `2026-07-08T16:00:00Z` → `2026-07-09T00:00:00Z` (one 8h batch) |

### Snapshot coverage census — **no full-window snapshot exists**

All 18 committed prod snapshots carry an `evaluation_window` spanning exactly one 8h batch
(e.g. `…07-03T00:00→07-03T08:00`, …, latest `…07-08T16:00→07-09T00:00`).
**`FULL_WINDOW_SNAPSHOT_MATCHES = []`** — none equals the full-ledger window
`2026-06-21T00:00:00 → 2026-07-09T00:00:00`. (This matches the writer design: each
`qnty-paper-pnl` batch captures a snapshot for its own watermark window only.)

### Candidate bundle build (scratch worktree → `/tmp` only)

Built via existing `origin/main` `build_funding_source_bundle_v1(envelope)` from the
selected DB-linked snapshot (`aded2f13…`, batch 56):

| Field | Value |
|---|---|
| candidate `source_bundle_sha256` | `03228ab7bdeb9f6961e07e79e5a1fb22dad0bc61fe70c2fd72d7446c102fc88a` |
| self-integrity (`recompute == stored`) | **OK (True)** |
| canonical rows | 4 (BNBUSDT 1, BTCUSDT 1, ETHUSDT 1, XRPUSDT 1) |
| **coverage window** | `2026-07-08T16:00:00Z` → `2026-07-09T00:00:00Z` (**8h, not full-ledger**) |
| `snapshot_bundle_sha256` (binding) | `aded2f13…` (binds to batch-56 snapshot) |
| candidate file (in `/tmp`, never prod) | `/tmp/qnty_prod_full_window_bundle_eval_20260709T091242Z/funding_source_bundle_v1_03228ab7….json` (file sha `8f53438f…`) |

The candidate is a **structurally valid, self-consistent 8h bundle** — but it covers only
the batch-56 window (SOL absent because its funding ends `07-08T16:00`, outside this
window). It is **not** a full-window bundle and cannot be made one from a single snapshot.

### Why a full-window bundle cannot yield full-ledger `CLEAN_NET_OF_CARRY` (code-grounded)

The top-level `funding_clean_carry_decision` is set by the **full-ledger** gate
`_build_funding_clean_carry_stamp` (`quantbot/paper/sqlite_verify.py:2502`):

```
clean_decision = clean_mode_decision_from_snapshot_v1(
    envelope,                                            # the SELECTED snapshot (batch 56)
    expected_evaluation_window=_funding_evaluation_window(conn),   # FULL-LEDGER window
    ...
    expected_source_file_sha256_by_path=expected_file_sha_by_path, # <- bundle only swaps THESE
    expected_row_subset_sha256_by_path=expected_row_sha_by_path,
)
```

- `source_mode="bundle"` only changes `expected_*_sha256_by_path` (via
  `_bundle_source_digest_expectations`, line 2563-2574). It does **not** change the
  `envelope` selected, nor the `expected_evaluation_window` (always the full-ledger span).
- `clean_mode_decision_from_snapshot_v1` compares the selected snapshot's own
  `evaluation_window` (batch-56 = `07-08T16:00→07-09T00:00`) against the full-ledger window
  (`06-21T00:00→07-09T00:00`); they differ ⇒ `funding_source_snapshot_window_mismatch`.
- Therefore the full-ledger gate emits `funding_source_snapshot_window_mismatch`
  **regardless of any bundle**. A bundle can only remove `source_path_unavailable`.

This is confirmed by the live official report (read-only):

| Gate | decision | status | reason_codes |
|---|---|---|---|
| full-ledger `funding_clean_carry` | `CAVEATED_ENGINE_SEMANTICS` | `refused_db_or_lane_mismatch` | `funding_source_snapshot_window_mismatch`, `source_path_unavailable` |
| batch `funding_clean_carry_batch` | `CAVEATED_ENGINE_SEMANTICS` | — | `source_path_unavailable` (batch window already matches) |
| report top-level | `status=OK`, `trusted=True`, `failure_count=0` | | |

Projected effect **if** the 8h candidate were written to prod (NOT done): bundle mode would
resolve (binding `aded2f13` matches the selected snapshot) and remove
`source_path_unavailable` from both gates → the **batch** stamp would go
`CLEAN_NET_OF_CARRY` (its only remaining reason clears), but the **full-ledger** gate would
still be `funding_source_snapshot_window_mismatch` → `CAVEATED_ENGINE_SEMANTICS`. Full-ledger
CLEAN is **unreachable** by any bundle.

### Why no prod bundle was written

Writing the 8h candidate to prod is the task's one allowed mutation, but it was declined:
(a) it does **not** achieve the goal (a full-window bundle / full-ledger CLEAN);
(b) a file named `funding_source_bundle_v1_*` that covers only 8h would be a misleading,
permanent prod-lane artifact that alters bundle-mode verifier semantics; (c) step 5's guard
("if a valid bundle cannot be built without mutating snapshot metadata, stop and record the
blocker instead of hacking around it") applies — a full-window bundle would require
fabricating a full-window snapshot envelope, which is forbidden. Minimal-diff wins.

### Acceptance gate

| Criterion | Result |
|---|---|
| prod DB unchanged | ✅ `4b947feb…` before == after |
| prod official report unchanged | ✅ `5bd406d6…` before == after |
| source CSVs unchanged | ✅ all 10 identical before/after |
| bundle self-integrity OK | ✅ (candidate, in `/tmp`) |
| full-window bundle **constructible** | ❌ no full-window snapshot to build from |
| full-ledger source mode bundle/provenance | ❌ not run against prod (would require prod write) |
| full-ledger decision `CLEAN_NET_OF_CARRY` | ❌ unreachable (`funding_source_snapshot_window_mismatch`) |
| reason_codes `[]` | ❌ `funding_source_snapshot_window_mismatch` (+`source_path_unavailable`) |
| no snapshot window mismatch | ❌ structural |

→ **Acceptance FAILED at constructibility. Verdict BLOCKED.**

---

## What was touched

- Local git: created branch `docs/qnty-prod-full-window-bundle-build-readonly-eval` off
  `6c8799e6…`; added this receipt.
- VM: `git -C /srv/qnty/repo fetch origin` (refs only); created + **removed** a detached
  scratch worktree; wrote one candidate bundle to `/tmp` (ephemeral). Nothing else.

## What was NOT touched

Real prod DB · official report · prod snapshots · prod source CSVs · `funding_source_bundles/`
(still absent) · `/srv/qnty/repo` main worktree (HEAD still `2bd88430…`) ·
other pre-existing scratch worktrees · systemd services/timers/cron · no
writer/trader/live/backfill/data-refresh/deploy · no exchange keys · no report promotion ·
no source-freeze · **no prod bundle written.**

---

## VERDICT

`QNTY_PROD_FULL_WINDOW_IMMUTABLE_BUNDLE_BUILD_AND_READONLY_EVAL_BLOCKED`
`EDGE_UNPROVEN` · `BLOCK_LIVE_INTEGRATION`

**Root cause:** prod `paper_pnl_v1` has **no committed full-window funding-source
snapshot** — every batch captures only its own 8h snapshot — and `build_funding_source_bundle_v1`
freezes a single snapshot, so the deepest coverage any prod bundle can reach is one 8h
batch. The full-ledger clean-carry gate compares the *selected snapshot's* window to the
*full-ledger* window, so `funding_source_snapshot_window_mismatch` is unavoidable and
bundle-independent. A bundle removes only `source_path_unavailable`, not the window
mismatch.

**Recommended next action (requires a separate code-owned PR, not this docs task):** to
ever reach prod full-ledger `CLEAN_NET_OF_CARRY` read-only, add writer/verifier support to
either (a) capture a **full-window prod snapshot** whose `evaluation_window` equals the
full funding-table span (then build a matching immutable bundle over it), or (b) teach the
full-ledger gate to assemble/validate a **multi-snapshot full-window bundle** and check
per-batch window coverage instead of single-snapshot window equality. Also emit an absolute
`resolved_funding_source_dir` in snapshot provenance so default mode stops reporting
`source_path_unavailable`. Until then, prod stays `CAVEATED_ENGINE_SEMANTICS` (a
source/window-resolution caveat, not a failure: `status=OK`, `failure_count=0`), and the
**shadow** lane remains the only bundle-mode `CLEAN_NET_OF_CARRY` lane. No live action;
no 2x leverage or shorting recommended or enabled.
