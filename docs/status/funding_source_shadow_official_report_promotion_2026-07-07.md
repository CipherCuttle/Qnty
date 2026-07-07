# QNTY Funding Source Shadow Official Report Promotion -- 2026-07-07

## Status Boundary

- The official report was **not** replaced because candidate acceptance failed.
- No DB mutation.
- No prod DB mutation.
- No writer / trader / live / backfill run.
- No code / test / schema / verifier / reporter / writer change.
- No shorting / trial-registry / null / benchmark lane change.
- No edge / profit / live / deployment claim.
- `EDGE_UNPROVEN` remains.
- `BLOCK_LIVE_INTEGRATION` remains.

## Scope

- task: `FUNDING_SOURCE_SHADOW_OFFICIAL_REPORT_PROMOTION_EXECUTION_GIT_OWNED`.
- PR #101 merge SHA: `23344f8e4ff315712b528780733d8cc6ccc97f68`.
- PR #102 plan/local main head: `771e9852511fc8556093ee333512dde2a80e84ef`.
- branch: `docs/funding-source-shadow-official-report-promotion-execution`.
- official report path:
  `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_verify_report.json`.
- candidate report path:
  `/tmp/qnty_shadow_report_promotion_20260707T160809Z/paper_verify_report.candidate.json`.
- candidate stderr path:
  `/tmp/qnty_shadow_report_promotion_20260707T160809Z/paper_verify_report.candidate.err`.
- backup dir:
  `/tmp/qnty_shadow_report_promotion_backup_20260707T160526Z`.
- DB path: `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db`.
- data dir: `/srv/qnty/repo/data`.
- VM repo path: `/srv/qnty/repo`.
- VM verifier code copy:
  `/tmp/qnty-shadow-report-promotion-code-20260707T160746Z`.
- MemPalace: not used / unavailable. No hooks or autosave enabled. A narrow
  local Codex memory quick-pass was used only to recall QNTY guardrails; source
  of truth remained git, `CLAUDE.md`, `docs/status/`, `docs/plans/`, and verifier
  output.

## Preflight

- local `main` includes PR #101: `git merge-base --is-ancestor ... main` exit
  `0`.
- local `main` includes the PR #102 promotion plan after fast-forward to
  `origin/main`: `docs/plans/QNTY_FUNDING_SOURCE_SHADOW_OFFICIAL_REPORT_PROMOTION_PLAN.md`.
- official report before:
  - size: `3531`
  - mtime: `2026-07-01T18:15:57Z`
  - sha256: `653605a76fdd0b8117c8373c9dadd3fcd41bed147778920c82f29f19f14e0ffd`
- real shadow DB before:
  - size: `172032`
  - mtime: `2026-07-07T15:20:43Z`
  - sha256: `00a4817e1d49aef51398fe0022cc2f3754302bc12f445912d4eb0d0596fc21ce`
- latest committed DB watermark:
  - `batch_id`: `17`
  - `committed_count`: `17`
  - `prior_watermark_bar_ts`: `2026-07-03T08:00:00`
  - `new_watermark_bar_ts`: `2026-07-05T16:00:00`
  - `committed_at`: `2026-07-06T04:33:09Z`
- output dir before aggregate:
  `1ce645a638ff19ae78db4425b3caf8be5f00d185180aa5bfea91742353348504`.
- output dir before listing:
  - `funding_source_snapshots/`
  - `funding_source_snapshots/funding_source_snapshot_v1_0559a411561c10c9d1180ce555f03ad86ee167716c3a9072dc225eabc74adfc6.json`
    sha256 `bbe7841c8b67e2197ee253228fc410ce58f07d5a187a9d85438b3ff2c1a51929`
  - `funding_source_snapshots/funding_source_snapshot_v1_07108989b34b9d99f863d58fb04b1388f185e6c4c5561117c6c9f1454dd1902b.json`
    sha256 `a920b0277badbef5275d795af9f8e4e2a2a33f976636a33e1a75b221a5c1ddd5`
  - `funding_source_snapshots/funding_source_snapshot_v1_1c5b433eb3adc345bdf024f20b45ffba874e77090ab5fc652f81fe169791451b.json`
    sha256 `730455698eb58e72dd7586d52f0e064350ace8dcbc077eddadeb85d740bfe8a7`
  - `funding_source_snapshots/funding_source_snapshot_v1_8b9d80408b5aae517ba745a5072d9f7d09125572a23ea5e792e2d80e9c099d69.json`
    sha256 `7c5068afef44fc360e88bbde126d892c538973e8f98cbd32dfd0a63ae310ab66`
  - `lane_config_v2.json`
  - `lane_identity.json`
  - `paper_config.json`
  - `paper_ledger.db`
  - `paper_ledger.db-shm`
  - `paper_ledger.db-wal`
  - `paper_ledger.db.before_shadow_dry_run.20260703T142916Z.bak`
  - `paper_ledger.db.before_shadow_dry_run.20260703T185642Z.bak`
  - `paper_ledger.db.before_snapshot_columns.20260703T133137Z.bak`
  - `paper_ledger.db.before_snapshot_columns.20260703T133855Z.bak`
  - `paper_verify_log.jsonl`
  - `paper_verify_receipt.md`
  - `paper_verify_report.json`
- source digests before:
  - `ADAUSDT_8h_funding.csv`
    `f3ff569bdfa43c408eb46b04cbd8c91beda33bd8898dc30920a824df2038927e`
  - `AVAXUSDT_8h_funding.csv`
    `dae86e6cfb14bad50acc7e2c3fd7330bebc7e0cb4f8776ad30cc40970af32e60`
  - `BNBUSDT_8h_funding.csv`
    `ad40bf885bb71dd43fd3dda2aafc70fd0ebcaafb31e94a9fb091110e5d170ef3`
  - `BTCUSDT_8h_funding.csv`
    `65c66a32ed97638bd80ac6110b484a8d96707f6d9e80d57313e2295210750c8e`
  - `DOTUSDT_8h_funding.csv`
    `f5185e71043f4bbeec9f0a63d18102ba9c4a35a9934cb37dd84eeaffd3dda6fa`
  - `ETHUSDT_8h_funding.csv`
    `e9b3423bd567bd1724a2d1819300b6f6c7ac8f49fa406a2b68f504996db467a9`
  - `LINKUSDT_8h_funding.csv`
    `0d0539fd35a2fc3ded08460434c9548e5bfd79a2b7f397d44175e412d944baf5`
  - `MATICUSDT_8h_funding.csv`
    `a7c3c7058abe7bb9e79a090448b823eb4a38a63c2036fbddb08036e06359d57c`
  - `SOLUSDT_8h_funding.csv`
    `a0980a1a1e154a2282601b98210e1d80ce7bafef0cc66ee1acbac3f66a15cf6a`
  - `XRPUSDT_8h_funding.csv`
    `2e9b5971bd324d13a4939abacfa4e921cf0850b3b70bb83d4d68909dbc00a560`
- VM repo before:
  - head: `2bd88430fe6b2881aaa2b32947002217d3e02ba5`
  - status: `## main...origin/main`
- no writer / trader / live / backfill process matched the preflight process
  scan.
- disk: `/dev/sda1` `75G` size, `3.5G` used, `69G` available, `5%` used for
  both `/srv/qnty/output/paper_pnl_null_shadow_v0` and `/tmp`.

## Backup

- backup path:
  `/tmp/qnty_shadow_report_promotion_backup_20260707T160526Z/paper_verify_report.json`.
- backup report sha:
  `653605a76fdd0b8117c8373c9dadd3fcd41bed147778920c82f29f19f14e0ffd`.
- official report before sha:
  `653605a76fdd0b8117c8373c9dadd3fcd41bed147778920c82f29f19f14e0ffd`.
- equality check: `true`.
- backup preserved size and mtime: `3531`, `2026-07-01T18:15:57Z`.

## Candidate Verifier Report

Exact verifier command for the final candidate:

```bash
PYTHONPATH=/tmp/qnty-shadow-report-promotion-code-20260707T160746Z \
  /srv/qnty/venv/bin/python -m quantbot.paper.sqlite_verify \
  --db-path /srv/qnty/output/paper_pnl_null_shadow_v0/paper_ledger.db \
  --read-only \
  --json \
  --data-dir /srv/qnty/repo/data \
  > /tmp/qnty_shadow_report_promotion_20260707T160809Z/paper_verify_report.candidate.json \
  2> /tmp/qnty_shadow_report_promotion_20260707T160809Z/paper_verify_report.candidate.err
```

- exit code: `0`.
- stdout path:
  `/tmp/qnty_shadow_report_promotion_20260707T160809Z/paper_verify_report.candidate.json`.
- stdout size: `17332`.
- stdout sha256:
  `1ab6f015ccfe2be918b93834660406bd7723fbab80aa86bc4f424fad7557637e`.
- stderr path:
  `/tmp/qnty_shadow_report_promotion_20260707T160809Z/paper_verify_report.candidate.err`.
- stderr size: `0`.
- stderr sha256:
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
- JSON parse result: OK.
- status: `OK`.
- failure_count: `0`.
- watermark: `2026-07-05T16:00:00`.
- full-ledger clean-carry decision: `CAVEATED_ENGINE_SEMANTICS`.
- full-ledger clean-carry status: `refused_digest_mismatch`.
- full-ledger reason codes:
  - `funding_source_file_digest_mismatch`
- batch clean-carry decision: `CAVEATED_ENGINE_SEMANTICS`.
- batch clean-carry status: `refused_digest_mismatch`.
- batch clean-carry reason codes:
  - `funding_source_batch_window_mismatch`
  - `funding_source_file_digest_mismatch`
- funding snapshot status: `present_valid`.
- DB-linked: `true`.
- selector: `ledger_batches`.
- target batch: `17`.
- candidate_count: `4`.
- selected snapshot:
  `/srv/qnty/output/paper_pnl_null_shadow_v0/funding_source_snapshots/funding_source_snapshot_v1_8b9d80408b5aae517ba745a5072d9f7d09125572a23ea5e792e2d80e9c099d69.json`.
- selected snapshot file sha:
  `7c5068afef44fc360e88bbde126d892c538973e8f98cbd32dfd0a63ae310ab66`.
- selected snapshot source bundle sha:
  `8b9d80408b5aae517ba745a5072d9f7d09125572a23ea5e792e2d80e9c099d69`.
- target caveats absent: **false**. `funding_source_file_digest_mismatch`
  appeared in the full-ledger reason-code set.
- `db_mutation_performed`: `false`.
- read-only / immutable open mode: `sqlite_open_mode=file_uri_mode_ro_immutable`;
  `read_only=true`; `query_only=1`; `query_only_pragma_enabled=true`.
- `wal_shm_files_created`: `false`.
- source path availability: `source_path_available=true`;
  `source_path_resolution_mode=explicit_data_dir`;
  `resolved_funding_source_dir=/srv/qnty/repo/data`.
- candidate acceptance result: **blocked**.

Diagnostic note: an earlier `/srv/qnty/repo` verifier candidate was written to
`/tmp/qnty_shadow_report_promotion_20260707T160553Z/` and was not used for
promotion because that runtime was not safe for the final candidate path. The
final candidate above used the git-owned `/tmp` code copy allowed by the plan.

## Promotion

- promotion skipped: candidate acceptance failed before any official report
  replacement.
- temp path: not created; no
  `/srv/qnty/output/paper_pnl_null_shadow_v0/paper_verify_report.json.tmp.*`
  promotion file was written.
- rename path: not executed.
- official report after:
  - size: `3531`
  - mtime: `2026-07-01T18:15:57Z`
  - sha256: `653605a76fdd0b8117c8373c9dadd3fcd41bed147778920c82f29f19f14e0ffd`
- candidate hash:
  `1ab6f015ccfe2be918b93834660406bd7723fbab80aa86bc4f424fad7557637e`.
- equality check: not applicable; promotion was not attempted.
- rollback: not needed because no official report replacement occurred.

## Post-Run Integrity

- DB after:
  - size: `172032`
  - mtime: `2026-07-07T15:20:43Z`
  - sha256: `00a4817e1d49aef51398fe0022cc2f3754302bc12f445912d4eb0d0596fc21ce`
- DB hash unchanged vs preflight: `true`.
- source digests after: **changed** vs preflight before the final candidate was
  accepted; this is the blocker.
  - `ADAUSDT_8h_funding.csv`
    `3d86bb6b75dd05674e5506f95cd6a6143bfd0c6245b7426a9585280c21bf4bf1`
    mtime `2026-07-07T16:06:54Z`
  - `AVAXUSDT_8h_funding.csv`
    `69da5e204d1d705e210e91c5265a5d8f7c7db6a57e4b01a358e57c274615ea42`
    mtime `2026-07-07T16:07:06Z`
  - `BNBUSDT_8h_funding.csv`
    `6d20cd71593faa1339f0d762cec27fffb5333a62b86d50a64c5ae7761c77243a`
    mtime `2026-07-07T16:06:42Z`
  - `BTCUSDT_8h_funding.csv`
    `418636f41ff2876a6df60ca8ed8b41d342765a912584f250760015dc9deb74a6`
    mtime `2026-07-07T16:06:29Z`
  - `DOTUSDT_8h_funding.csv`
    `1892043a7a116c81e6eeeb68898e4ffcd0cb81d9d78c0c07d103d1ed2c3d11fe`
    mtime `2026-07-07T16:07:00Z`
  - `ETHUSDT_8h_funding.csv`
    `3bd2c7b5a88daf4a14423f2cfa1abc45c7a0199ae004b6efa1b1f7e74e07f0e8`
    mtime `2026-07-07T16:06:36Z`
  - `LINKUSDT_8h_funding.csv`
    `45c3abedc24bef7b69572b9165be21344351f66b800e0ccefb4785cde322df9f`
    mtime `2026-07-07T16:07:13Z`
  - `MATICUSDT_8h_funding.csv`
    `6cb3f3b754eb710e777417c41ea3887445ad7f80276b4f41d6c647272f835485`
    mtime `2026-07-07T16:07:19Z`
  - `SOLUSDT_8h_funding.csv`
    `ab2538c965f05fd9659e434c7730ee81abe7c373a9df1bd8c0215d8251e29656`
    mtime `2026-07-07T16:06:48Z`
  - `XRPUSDT_8h_funding.csv`
    `ea79a4c908e941ea49414122b73cb4e45eca47cfea6ce21978ac34d38ac0d4bb`
    mtime `2026-07-07T16:07:25Z`
- VM repo after:
  - head: `2bd88430fe6b2881aaa2b32947002217d3e02ba5`
  - status: `## main...origin/main`
- VM repo unchanged: `true`.
- output dir after aggregate:
  `1ce645a638ff19ae78db4425b3caf8be5f00d185180aa5bfea91742353348504`.
- output dir changed vs preflight: `false`.
- output dir changes: none. The official report was not replaced, no promotion
  temp file was created, no DB file hash changed, and no extra files appeared in
  the shadow output dir.
- no temp residue in official report directory: true.
- no writer / trader / live / backfill process matched the post-run process scan.

## Impact On Existing Receipts

- PR #101 made the real shadow DB clean against the source CSV state captured at
  that time.
- This promotion attempt re-ran the verifier fresh against the real shadow DB,
  but current source CSV digests drifted before candidate acceptance.
- Because the fresh verifier now reports `funding_source_file_digest_mismatch`,
  the official report cannot be promoted and remains stale.
- The official report is **not** fresh after this run.
- `EDGE_UNPROVEN` and `BLOCK_LIVE_INTEGRATION` remain.

## Recommended Next Action

Do not proceed to `QNTY_POST_FUNDING_SOURCE_REPAIR_STATUS_ROLLUP_GIT_OWNED` yet.
First stabilize or intentionally snapshot the current source CSV state and rerun
the real shadow DB funding-source recommit / verification path so the real
DB-linked full-ledger clean-carry gate is clean again. After that, rerun the
official report promotion task.

## Non-Goals

- no official report replacement.
- no DB mutation.
- no prod DB mutation.
- no writer / trader / live / backfill.
- no deploy.
- no code change.
- no test change.
- no schema change.
- no verifier / reporter / writer logic change.
- no shorting / trial-registry / null / benchmark lane change.
- no live trading approval.
- no shorting approval.
- no edge / profitability claim.
- no MemPalace path mining.
- no hooks / autosave enablement.

## Verdict

`FUNDING_SOURCE_SHADOW_OFFICIAL_REPORT_PROMOTION_BLOCKED_CANDIDATE`
