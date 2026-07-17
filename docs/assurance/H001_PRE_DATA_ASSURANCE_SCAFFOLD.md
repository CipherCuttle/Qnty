# H001 pre-data assurance scaffold

This repository-owned scaffold is metadata-only and non-executable. It records a draft temporal-causality proposal, an unfrozen synthetic null-calibration proposal, an empty append-only holdout disclosure ledger, metadata schemas for future failure-domain evidence and replayable review packets, and an in-memory synthetic canary descriptor.

Nothing here accesses Binance, the network, real bars or funding, holdout bytes, candidate stores, credentials, or artifact stores. No calibration, canary, review packet, data disclosure, result statistic, FWER estimate, return, ranking, or authorization is produced. The existing H001 preregistration remains unchanged.

The temporal amendment remains `DRAFT_ONLY_NOT_EFFECTIVE`; it proposes strict funding precedence but does not apply it. The calibration specification remains `DRAFT_ONLY_UNFROZEN_NOT_EXECUTABLE`; block length, HAC lag, DGP selection, and results are not tuned or exposed. Later independent review and append-only governance are required before either proposal can become effective.

The holdout ledger accepts metadata-only entries and requires append-only preservation of prior entries. This transition creates it empty and performs no historical backfill. Store failure-domain labels are merely a future evidence schema: self-declared metadata is not store qualification and later independent restore/re-hash governance is required.

Review packets explicitly exclude private reasoning, real bytes, secrets, and scientific edge claims. The synthetic canary returns deterministic bytes only in memory; it is not written, ingested, restored, registered, or represented by a real artifact URI.

All JSON documents use canonical UTF-8, sorted keys, compact separators, ASCII, and no trailing newline. `EDGE_UNPROVEN`, `BLOCK_LIVE_INTEGRATION`, zero execution, unavailable V0, and forbidden real-data access remain invariant.
