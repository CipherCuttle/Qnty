# QNTY Realized Attribution Reporter Parity Receipt — 2026-07-06

**Receipt date:** 2026-07-06
**Run timestamp (UTC):** 2026-07-06T18:21:49Z (reporter `generated_at_utc`)
**Reporter:** `scripts/qnty-paper-realized-attribution.py` +
`quantbot/paper/realized_attribution.py`
(schema `realized_attribution_report_v0`, spec version 1.0.0)
**Manual snapshot compared against:** `docs/status/realized_attribution_2026-07-06.md`
**Type:** docs-only parity / evidence-tooling receipt. This is a **parity/evidence
receipt, not a strategy result** — not an edge claim, not a trading
recommendation, not a live-readiness artifact, and not a
verifier/schema/writer/trader change.

This receipt records that the read-only realized attribution reporter merged in
PR #83 reproduces, field-for-field, the hand-SQL realized attribution snapshot
dated 2026-07-06 for the two accessible long-only V2 lanes (prod and shadow),
without ad-hoc SQL and without mutating any database.

---

## Status Boundary

- `EDGE_UNPROVEN` remains.
- `BLOCK_LIVE_INTEGRATION` remains.
- Full-ledger `CAVEATED_ENGINE_SEMANTICS` remains for both lanes. The prod
  verifier report records `funding_clean_carry_decision =
  CAVEATED_ENGINE_SEMANTICS`; the shadow verifier report predates the
  clean-carry fields, so no upgrade is asserted for it either. Only an explicit
  verifier report can ever change that label; this receipt does not and cannot.
- This receipt **validates reporter reproducibility / evidence tooling only.**
  It demonstrates that the tool reproduces a previously hand-computed snapshot.
- This receipt **does not prove** edge, profitability, statistical
  significance, shorting readiness, or live readiness.
- **No trader/writer/verifier/schema/strategy behavior changes are made.** No
  writer ran. No database was mutated.

---

## Scope

- **Reporter version / git commit used:** local repo head
  `8a775ff4b527534f8733ddd8db643b87292d98a3` (the PR #83 merge commit on
  `main`), branch `docs/realized-attribution-reporter-parity-2026-07-06`. The
  reporter module byte-shipped to the VM was sha256
  `cb8e55034fc38e3080f0b3a942bcb2b94a7d50c98ce75774c907fc7173863276`, identical
  to the repo copy.
- **Manual snapshot compared against:** `docs/status/realized_attribution_2026-07-06.md`.
- **Lanes inspected:** prod paper lane (`paper_pnl_v1`) and shadow paper lane
  (`paper_pnl_null_shadow_v0`) — both accessible and read.
- **DB paths:**
  - Prod DB: `/srv/qnty/output/paper_pnl_v1/paper_ledger.db`
  - Shadow DB: `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db`
- **VM repo head (`/srv/qnty/repo`):** `2bd88430fe6b2881aaa2b32947002217d3e02ba5`
  (`2bd8843`, on `main`) — inspected read-only, **not modified**. The VM repo
  does **not** contain PR #83 reporter code, and was **not** pulled or updated.
- **Local repo head:** `8a775ff` (`main` fast-forwarded to `origin/main`, then
  the parity branch cut from it).
- **Read-only method:** the self-contained reporter module (stdlib-only) was
  copied to `/tmp/qnty_reporter_ro/` on the VM and executed with the system
  `python3` (3.12.3) against each live DB in SQLite `mode=ro` + `PRAGMA
  query_only=ON`. Nothing was written into `/srv/qnty/repo` or
  `/srv/qnty/output`.
- **No writer ran. No DB was mutated** (see Source Integrity / Mutation Proof).

---

## Method

- **Reporter command (per lane):**

  ```
  python3 scripts/qnty-paper-realized-attribution.py \
    --db-path <db> --json --pretty --lane-label <lane>
  ```

  On the VM the equivalent was invoked through a thin stdlib runner importing
  the byte-identical module (`build_report(db, lane_label=...)` +
  `render_json(report, pretty=True)`), because the VM repo does not carry PR
  #83 code and was deliberately not updated.
- **Where it ran:** on the VM (`37.27.216.174`), against the live prod and
  shadow ledgers at their canonical `/srv/qnty/output/...` paths, so the exact
  same bytes the manual snapshot read were re-read.
- **Temporary files:** the reporter module and a small runner were placed under
  `/tmp/qnty_reporter_ro/` on the VM (outside the repo and outside the output
  tree). No temporary JSON was persisted into the repo; reporter output was
  read from stdout only. No JSON artifact is committed.
- **Source integrity proof:** `stat` (size, mtime) + `sha256sum` on both DB
  files before and after the reads, captured externally; and the reporter's own
  embedded before/after sha256/size/mtime with a
  `read_only_integrity = READ_ONLY_CONFIRMED` verdict.
- **Comparison tolerance:** exact-float fields compared at absolute tolerance
  `1e-6` (the spec / verifier accounting tolerance). Integer counts
  (`N_closed`, fills, open positions, batch id) and string fields (watermark)
  compared for exact equality.
- **Fields compared:** latest batch id, watermark, latest equity, equity delta,
  realized gross PnL, closed-trade realized net PnL, unrealized PnL, fees
  cumulative, funding cumulative, open positions count, `N_closed`, fills count,
  read-only integrity, and unavailable fields.

---

## Source Integrity / Mutation Proof

Captured immediately before the first read and immediately after the last read
(external `stat`/`sha256sum`), cross-checked against the reporter's own embedded
before/after integrity fields.

**Prod — `/srv/qnty/output/paper_pnl_v1/paper_ledger.db`**

| | size (bytes) | mtime (epoch) | sha256 |
|---|---|---|---|
| before | 217088 | 1783354846 | `8d21c37406647e2252fd6c7079ac4b55dcfa300b6b94aded9561fc06cc4184d3` |
| after  | 217088 | 1783354846 | `8d21c37406647e2252fd6c7079ac4b55dcfa300b6b94aded9561fc06cc4184d3` |

- **Reporter `read_only_integrity`:** `READ_ONLY_CONFIRMED`
  (`db_sha256_before == db_sha256_after`, `db_size_before == db_size_after`,
  `db_mtime_before == db_mtime_after` at ns resolution).
- **Match status:** identical (size, mtime, sha256 all unchanged).
- **Verdict:** `READ_ONLY_CONFIRMED`.

**Shadow — `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db`**

| | size (bytes) | mtime (epoch) | sha256 |
|---|---|---|---|
| before | 172032 | 1783312420 | `3cbc6e9c63c74072aa019d6a53b1f5519f369f95cec1f9c21495e307c739a897` |
| after  | 172032 | 1783312420 | `3cbc6e9c63c74072aa019d6a53b1f5519f369f95cec1f9c21495e307c739a897` |

- **Reporter `read_only_integrity`:** `READ_ONLY_CONFIRMED`.
- **Match status:** identical (size, mtime, sha256 all unchanged).
- **Verdict:** `READ_ONLY_CONFIRMED`.

Both DB files are byte-identical before and after all reads, and both hashes
match the manual 2026-07-06 snapshot's recorded hashes exactly — i.e. the
ledgers have **not advanced** since the manual snapshot, so the comparison is a
valid same-bytes parity check.

---

## Reporter Output Summary

Realized and unrealized are reported separately and are **never** summed into a
single headline.

| Field | Prod (`paper_pnl_v1`) | Shadow (`paper_pnl_null_shadow_v0`) |
|---|---|---|
| Latest committed batch | 48 | 17 |
| Watermark | `2026-07-06T08:00:00` | `2026-07-05T16:00:00` |
| Latest equity (mark-to-market) | 10312.77956158 | 10350.80781593 |
| Equity delta | +312.77956158 | +350.80781593 |
| Realized gross PnL (ledger) | −36.61557032 | −25.40311929 |
| **Closed-trade realized net PnL (`SUM(trades.net_pnl)`)** | **−43.91342549** | **−28.58037638** |
| Unrealized PnL (`equity_snapshots.unrealized_pnl`) | +362.93382432 | +385.13824051 |
| Fees cumulative | 9.48169221 | 5.48729844 |
| Funding cumulative | 4.05700021 | 3.44000685 |
| Open positions (`num_open`) | 5 | 5 |
| **`N_closed`** | **7** | **3** |
| Fills count | 19 | 11 |
| Accounting identity residual | 0.0 (≤ 1e-6) | 1.82e-12 (≤ 1e-6) |
| `read_only_integrity` | `READ_ONLY_CONFIRMED` | `READ_ONLY_CONFIRMED` |
| Unavailable fields (count) | 4 | 8 |
| Unavailable fields (list) | `lane_identity.config_hash_v2`, `lane_identity.git_sha`, `lane_identity.lane_id`, `latest_batch.lane_id` | `lane_identity.git_sha`, and all seven `evidence_quality.funding_clean_carry_*` fields (shadow verifier report predates clean-carry fields) |

Notes on the unavailable fields (consistent with the manual snapshot's Method
section):

- **`lane_id` / `config_hash_v2` for prod** are genuinely absent in the prod
  `paper_config` (implicit v1 baseline), so the reporter emits
  `UNAVAILABLE_READ_ONLY` rather than inventing them. The manual snapshot
  recorded the same ("absent / NULL (implicit v1 baseline)").
- **`git_sha` in `lane_identity`** is a per-batch stamp by design; the reporter
  surfaces it from `latest_batch.git_sha`
  (`2bd88430fe6b2881aaa2b32947002217d3e02ba5`) for both lanes, matching the
  manual snapshot.
- **Shadow `funding_clean_carry_*` fields** are `UNAVAILABLE_READ_ONLY` because
  the shadow `paper_verify_report.json` predates the clean-carry fields — the
  same reason the manual snapshot recorded them as `UNAVAILABLE_READ_ONLY`.
- **Per-symbol `unrealized_pnl` (`position_snapshot_symbols.unrealized_gross`)**
  is `0.0` for every open position on both lanes (the writer stores 0.0 at mark
  time), matching the manual snapshot. The authoritative aggregate unrealized
  figure is `equity_snapshots.unrealized_pnl`, which is consistent under the
  accounting identity (residual ≤ 1e-6).

---

## Parity Against Manual Snapshot

All exact-float fields compared at absolute tolerance `1e-6`; integers and
strings compared for exact equality.

**Prod (`paper_pnl_v1`)**

| Field | Manual snapshot value | Reporter value | Delta | Status |
|---|---|---|---|---|
| Latest batch id | 48 | 48 | 0 | `MATCH` |
| Watermark | `2026-07-06T08:00:00` | `2026-07-06T08:00:00` | — | `MATCH` |
| Latest equity | 10312.77956158 | 10312.77956158 | 0.0 | `MATCH` |
| Equity delta | +312.77956158 | +312.77956158 | ≈5e-13 | `MATCH` |
| Realized gross PnL | −36.61557032 | −36.61557032 | 0.0 | `MATCH` |
| Closed-trade realized net PnL | −43.91342549 | −43.91342549 | 0.0 | `MATCH` |
| Unrealized PnL | +362.93382432 | +362.93382432 | 0.0 | `MATCH` |
| Fees cumulative | 9.48169221 | 9.48169221 | 0.0 | `MATCH` |
| Funding cumulative | 4.05700021 | 4.05700021 | 0.0 | `MATCH` |
| Open positions | 5 | 5 | 0 | `MATCH` |
| `N_closed` | 7 | 7 | 0 | `MATCH` |
| Fills count | 19 | 19 | 0 | `MATCH` |
| Read-only integrity | `READ_ONLY_CONFIRMED` | `READ_ONLY_CONFIRMED` | — | `MATCH` |

**Shadow (`paper_pnl_null_shadow_v0`)**

| Field | Manual snapshot value | Reporter value | Delta | Status |
|---|---|---|---|---|
| Latest batch id | 17 | 17 | 0 | `MATCH` |
| Watermark | `2026-07-05T16:00:00` | `2026-07-05T16:00:00` | — | `MATCH` |
| Latest equity | 10350.80781593 | 10350.80781593 | 0.0 | `MATCH` |
| Equity delta | +350.80781593 | +350.80781593 | ≈3e-13 | `MATCH` |
| Realized gross PnL | −25.40311929 | −25.40311929 | 0.0 | `MATCH` |
| Closed-trade realized net PnL | −28.58037638 | −28.58037638 | ≈4e-15 | `MATCH` |
| Unrealized PnL | +385.13824051 | +385.13824051 | 0.0 | `MATCH` |
| Fees cumulative | 5.48729844 | 5.48729844 | 0.0 | `MATCH` |
| Funding cumulative | 3.44000685 | 3.44000685 | 0.0 | `MATCH` |
| Open positions | 5 | 5 | 0 | `MATCH` |
| `N_closed` | 3 | 3 | 0 | `MATCH` |
| Fills count | 11 | 11 | 0 | `MATCH` |
| Read-only integrity | `READ_ONLY_CONFIRMED` | `READ_ONLY_CONFIRMED` | — | `MATCH` |

**Explicit findings:**

- **Prod matches the manual snapshot** on every compared field, within the
  stated tolerance.
- **Shadow matches the manual snapshot** on every compared field, within the
  stated tolerance.
- **No mismatch was found.** The only sub-`1e-6` deltas are floating-point
  representation differences in derived quantities (equity delta, closed-trade
  net), well inside the `1e-6` tolerance; they are **not** reporter bugs, and
  are **not** due to ledger advance (the DBs are byte-identical to the manual
  snapshot). Unavailable fields are unavailable for the same documented reasons
  in both artifacts, not because of a reporter defect.

---

## Interpretation

- **The reporter reproduces the manual snapshot.** Every field compared for both
  lanes matches within `1e-6`; the tool re-derives the same realized/unrealized
  attribution the hand-SQL snapshot produced, from the same ledger bytes,
  without ad-hoc SQL.
- **Ledgers did not advance.** Both DB hashes equal the manual snapshot's
  recorded hashes, so this is a same-bytes parity check, not a moving-target
  comparison.
- **Realized closed-trade net remains the primary evidence.** It is negative on
  both lanes (prod −43.91342549; shadow −28.58037638).
- **Unrealized marks remain secondary and reversible.** The positive equity
  delta on both lanes is entirely unrealized mark-to-market on open long
  positions — a mark, not a capture.
- **This receipt is evidence-tooling validation, not strategy validation.** It
  says the tool is faithful; it says nothing about the strategy.
- **No live implication.** `BLOCK_LIVE_INTEGRATION` stands.
- **No shorting implication.** The engine remains long-only; shorting remains an
  untested, preregistered hypothesis.

---

## What This Receipt Proves

- The reporter executed **read-only** against both live ledgers
  (`READ_ONLY_CONFIRMED`, DBs byte-identical before and after, no writer run).
- The reporter output **matched** the manual 2026-07-06 snapshot for both prod
  and shadow, field-for-field, within `1e-6`, under the stated conditions
  (ledgers unchanged since the snapshot).
- **Source integrity was preserved** — both DBs unchanged; both hashes also
  equal to the manual snapshot's recorded hashes.
- The **realized/unrealized split was reproducible through the tool**, with
  closed-trade realized net PnL as the headline realized figure and unrealized
  mark-to-market reported separately.

---

## What This Receipt Does Not Prove

- **No edge.** `EDGE_UNPROVEN`.
- **No profitability** beyond the observed paper/accounting values themselves;
  realized closed-trade net PnL is negative on both lanes.
- **No statistical significance.** `N_closed` (7 prod, 3 shadow) is far below any
  plausible minimum track record length.
- **No live readiness.** `BLOCK_LIVE_INTEGRATION` stands.
- **No shorting readiness.**
- **No full-ledger clean-status upgrade.** Full-ledger
  `CAVEATED_ENGINE_SEMANTICS` stands; only an explicit verifier report can ever
  change it, and none is run here.
- **No authorization** to change code, create lanes, or trade.

---

## Non-Goals

- No code changes.
- No reporter changes.
- No tests changed.
- No DB writes.
- No writer run.
- No verifier change (no verifier was run; existing reports were read as-is).
- No schema change.
- No trader / decision / signal change.
- No null model.
- No benchmark run.
- No trial registry.
- No live integration.
- No leverage.

---

## Reproduction Notes

All reads are read-only; no file is written into `/srv/qnty/repo` or
`/srv/qnty/output`. Temporary reporter files live only under
`/tmp/qnty_reporter_ro/` on the VM.

1. **Before-mutation proof:**
   `stat -c "%n %s %Y" <prod.db> <shadow.db>`; `sha256sum <prod.db> <shadow.db>`.
2. **Run the reporter (read-only) per lane:**

   ```
   python3 scripts/qnty-paper-realized-attribution.py \
     --db-path /srv/qnty/output/paper_pnl_v1/paper_ledger.db \
     --json --pretty --lane-label prod

   python3 scripts/qnty-paper-realized-attribution.py \
     --db-path /srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db \
     --json --pretty --lane-label shadow
   ```

   The reporter opens each DB as `file:<path>?mode=ro` with `PRAGMA
   query_only=ON` and emits its own before/after sha256/size/mtime plus
   `read_only_integrity`. (Because the VM repo does not carry PR #83 code, the
   byte-identical stdlib-only module was copied to `/tmp/qnty_reporter_ro/` and
   invoked there; the local repo `main` at `8a775ff` runs the command above
   directly.)
3. **After-mutation proof:** repeat `stat` + `sha256sum`; confirm byte-identity
   and that both hashes equal those recorded in
   `docs/status/realized_attribution_2026-07-06.md`.
4. **Compare** the reporter fields against the manual snapshot's Realized
   Attribution Table and Lane Summary Table at absolute tolerance `1e-6` for
   floats, exact equality for integers/strings.
5. **Reporter unit tests (optional):**
   `python3 -m pytest tests/test_paper_realized_attribution_reporter.py`
   (16 passed).

Full JSON is intentionally not dumped here; the summarized fields above are
sufficient for parity.

---

## Open Questions

None of these block this receipt.

- Whether to automate recurring reporter receipts (e.g. a scheduled read-only
  run producing a dated parity artifact).
- Whether the reporter should emit Markdown directly later, rather than JSON
  that is transcribed into a receipt by hand.
- Whether the stale shadow verifier report (predating the clean-carry fields,
  verified only through an older watermark) should be refreshed by a separate,
  verifier-only, read-only PR so its clean-carry fields become available.
- Whether `position_snapshot_symbols.unrealized_gross` being `0.0` everywhere
  (per-symbol unrealized not populated by the writer) should be investigated
  later — a writer/schema concern, out of scope here.

---

## Verdict

`REPORTER_PARITY_RECEIPT_RECORDED_MATCH`

---

*This receipt is docs-only. No writer ran, no database was mutated (both DBs
byte-identical before and after reads, and byte-identical to the 2026-07-06
manual snapshot: `READ_ONLY_CONFIRMED`), no trader/decision/signal/verifier/
schema/writer code was modified, no test changed, no reporter code changed. The
VM repo was inspected read-only and not updated. `EDGE_UNPROVEN`,
`BLOCK_LIVE_INTEGRATION`, and full-ledger `CAVEATED_ENGINE_SEMANTICS` are
preserved. This document authorizes no code, no lane, no registry, and no live
integration.*
