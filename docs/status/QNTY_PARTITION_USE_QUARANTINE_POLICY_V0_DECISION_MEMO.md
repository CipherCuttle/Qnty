# Partition-Use Quarantine Policy v0

`holdout_open_gate_state` remains a structural attestation. Its closed
vocabulary remains `blocked`, `mismatch`, and `gate_passed`; `gate_passed`
is necessary but not sufficient for any scientific use and is not trading,
paper, or live authorization.

Scientific eligibility is represented separately by `partition_use_policy_v0`.
Its closed state vocabulary is `quarantine_only` and `confirmatory_eligible`.
The declaration is registry-metadata-only, canonical-fingerprinted, and fails
closed when it is absent, malformed, unknown, not preregistered, or changed
without a matching fingerprint. It never reads bars, funding, train, purge,
embargo, or holdout rows, and it cannot invoke a scorer.

The current real BTC tail requires `quarantine_only` because final-row economic
values were displayed before a split boundary was frozen. A future amendment
may declare `prior_economic_value_exposure_before_split_freeze`, a future
confirmatory cutoff of `2026-04-23T01:00:00Z`, and that it was declared before
the first statistic execution. This memo does not amend the real registry or
choose a boundary.

Confirmatory use must be based on future unseen data: a new data cut and a new
declaration with the prior quarantine declaration's fingerprint are required,
rather than changing the quarantined partition in place. No statistic value T has been observed. Candidate 1 execution count
is zero for this work. Paper trading and live integration remain unauthorized.
