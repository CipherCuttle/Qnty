# Timestamp Canonicalization Diagnostics — Implementation Plan

## 1. Codebase Analysis Summary

### Current Architecture

The file [`quantbot/experiment/offline_edge_real_validation.py`](quantbot/experiment/offline_edge_real_validation.py) (3018 lines) contains three existing funding-to-bars diagnostic sections plus supporting infrastructure:

| Section | Function | Lines | Type |
|---------|----------|-------|------|
| Alignment | `materialize_funding_to_bars_alignment_diagnostics` | 1363-1570 | No I/O — consumes already-materialized receipt sections |
| Temporal Joinability | `materialize_funding_to_bars_temporal_joinability_diagnostics` | 1776-2008 | I/O — re-opens CSV files, validates timestamps |
| Timestamp Convention / Offset | `materialize_funding_to_bars_timestamp_convention_diagnostics` | 2304-2524 | I/O — re-opens CSV files, offset detection, nearest-delta histogram |

### Key Patterns to Follow

Every diagnostic section follows a strict pattern:

1. **Function signature**: keyword-only args including `inventory` and `split_definitions`, returns `dict[str, Any]`
2. **Timestamp loading**: uses `_load_role_symbol_timestamps()` to re-open CSVs, validate SHA256, enforce monotonic/unique timestamps
3. **Split window building**: uses `_build_split_windows_for_joinability()` to create deterministic per-split windows
4. **Symbol indexing**: bars and funding timestamps indexed by normalized symbol via `_files_by_symbol()`
5. **Return shape**: top-level `calculation_status`, `symbol_count`, `symbols` list; per-symbol `funding_application_status: "NOT_EXECUTED"`, `splits` list
6. **Receipt integration**: `build_real_validation_receipt()` accepts optional section; `main()` conditionally calls when `funding_dir is not None`
7. **Safety keys**: `_assert_no_forbidden_calculation_keys()` scans for PnL/Sharpe/edge/return/trade/position
8. **Fail-closed**: `ValueError` for all invalid states (duplicate timestamps, non-monotonic, malformed, SHA256 mismatch, missing headers)

### Existing Helpers to Reuse

| Helper | Location | Purpose |
|--------|----------|---------|
| `_parse_timestamp(ts: str) -> datetime` | line 188 | Parse ISO/epoch timestamp |
| `_format_timestamp(dt: datetime) -> str` | line 211 | Format datetime as ISO UTC Z |
| `_timestamp_in_window(ts, *, start, end, include_end) -> bool` | line 544 | Split window membership test |
| `_load_role_symbol_timestamps(...) -> dict[str, dict]` | line 1596 | Re-open CSVs, validate, return timestamp lists |
| `_build_split_windows_for_joinability(...) -> list[dict]` | line 1722 | Build deterministic split windows |
| `_symbol_from_filename(filename, suffix, role) -> str` | line 1318 | Extract symbol from filename |
| `_mode_step_seconds(timestamps) -> tuple` | line 2174 | Mode of consecutive step durations |
| `_timedelta_to_microseconds(delta) -> int` | line 2214 | Exact signed microseconds (no float loss) |
| `_safe_ratio(numerator, denominator) -> float` | line 2075 | Safe division with non-finite guard |

---

## 2. New Function: `materialize_funding_to_bars_timestamp_canonicalization_diagnostics`

### Location

Insert after line 2524 (after the existing `materialize_funding_to_bars_timestamp_convention_diagnostics` function ends), before the `build_cost_case_matrix` function at line 2527.

Add to `__all__` at line 49.

### Function Signature

```python
def materialize_funding_to_bars_timestamp_canonicalization_diagnostics(
    *,
    inventory: dict[str, Any],
    split_definitions: list[dict[str, Any]],
) -> dict[str, Any]:
```

**Parameters:**
- `inventory`: The input inventory dict (must contain both `bars` and `funding` roles)
- `split_definitions`: List of split definitions from `materialize_split_definitions_from_inventory`

**Returns:** A dict with keys described in section 4 below.

---

## 3. Helper Functions to Add

### 3a. Canonicalization Core

```python
def _canonicalize_floor(dt: datetime) -> datetime:
    """Truncate sub-second microsecond component to zero."""
    return dt.replace(microsecond=0)


def _canonicalize_round_half_away_from_zero(dt: datetime) -> datetime:
    """Round to nearest whole second, half away from zero.

    For positive microseconds >=500000: add 1 second, zero microseconds.
    For negative microseconds (before epoch): abs(microseconds) >=500000
    subtracts 1 second. This is deterministic half-away-from-zero.
    """
    if dt.microsecond >= 500_000:
        return dt.replace(microsecond=0) + timedelta(seconds=1)
    elif dt.microsecond <= -500_000:  # negative microseconds (pre-epoch edge)
        return dt.replace(microsecond=0) - timedelta(seconds=1)
    return dt.replace(microsecond=0)


def _canonicalize_ceil(dt: datetime) -> datetime:
    """Ceil to nearest whole second: if any subsecond component, bump up."""
    if dt.microsecond > 0:
        return dt.replace(microsecond=0) + timedelta(seconds=1)
    return dt
```

### 3b. Collision Detection

```python
def _detect_canonicalization_collisions(
    raw_timestamps: list[datetime],
    canonicalize_fn: Callable[[datetime], datetime],
) -> dict[str, Any]:
    """Detect when multiple raw timestamps canonicalize to same whole-second.

    Returns:
        collision_count: number of raw timestamps that participate in collisions
        collision_groups: list of {canonical_timestamp, raw_timestamps, count}
        canonical_counts: dict mapping canonical timestamp -> count of raw timestamps
        unique_canonical_count: number of distinct canonical timestamps
        collision_free_count: number of raw timestamps with no collision
    """
```

Pseudocode:
```
canonical_counts = defaultdict(int)
raw_by_canonical = defaultdict(list)
for ts in raw_timestamps:
    canon = canonicalize_fn(ts)
    canonical_counts[canon] += 1
    raw_by_canonical[canon].append(ts)

collision_groups = []
for canon, raws in raw_by_canonical.items():
    if len(raws) > 1:
        collision_groups.append({
            "canonical_timestamp": _format_timestamp(canon),
            "collision_count": len(raws),
            "raw_timestamps": [_format_timestamp(r) for r in raws],
        })

collision_count = sum(g["collision_count"] for g in collision_groups)
unique_count = len(canonical_counts)
collision_free_count = sum(1 for v in canonical_counts.values() if v == 1)
```

### 3c. Ambiguous Nearest Bar Detection

```python
def _detect_ambiguous_nearest_bars(
    funding_canonical: list[datetime],
    bars_timestamps: list[datetime],
) -> dict[str, Any]:
    """Detect funding timestamps equidistant from two bar timestamps.

    For each canonicalized funding timestamp, find the nearest bar timestamp
    using bisect. If distance is equal both forward and backward, it's ambiguous.

    Returns:
        ambiguous_count: number of funding timestamps with ambiguous nearest bar
        ambiguous_rows: list of {funding_timestamp, bar_before, bar_after, distance_seconds}
        unambiguous_count: number of funding timestamps with unique nearest bar
    """
```

Pseudocode:
```
ambiguous_count = 0
ambiguous_rows = []
for ft in funding_canonical:
    idx = bisect.bisect_left(bars_sorted, ft)
    before_dist = None
    after_dist = None
    if idx > 0:
        before_dist = abs((bars_sorted[idx-1] - ft).total_seconds())
    if idx < len(bars_sorted):
        after_dist = abs((bars_sorted[idx] - ft).total_seconds())
    if before_dist is not None and after_dist is not None and before_dist == after_dist:
        ambiguous_count += 1
        ambiguous_rows.append({
            "funding_timestamp": _format_timestamp(ft),
            "bar_before_timestamp": _format_timestamp(bars_sorted[idx-1]),
            "bar_after_timestamp": _format_timestamp(bars_sorted[idx]),
            "distance_seconds": before_dist,
        })
```

### 3d. Subsecond Stats

```python
def _subsecond_stats(timestamps: list[datetime]) -> dict[str, Any]:
    """Compute sub-second component statistics for funding timestamps.

    Returns:
        subsecond_present: bool
        subsecond_count: int
        subsecond_fraction: float (ratio of subsecond timestamps to total)
        min_subsecond_microseconds: int or None
        max_subsecond_microseconds: int or None
        mean_subsecond_microseconds: float or None
    """
```

### 3e. Best Policy Selection

```python
def _select_best_canonicalization_policy(
    policy_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Select the best canonicalization policy by fewest collisions.

    Deterministic tie-breaking: prefer floor > round > ceil (canonical
    policy order). If tie persists, prefer smaller unique_canonical_count.
    Records tie_count and tied_policy_names for transparency.
    """
```

### 3f. History Range Status

```python
def _history_range_status(
    bars_first: datetime | None,
    bars_last: datetime | None,
    funding_first: datetime | None,
    funding_last: datetime | None,
) -> dict[str, Any]:
    """Determine if bars and funding time ranges overlap.

    Returns:
        overlapped: bool
        overlap_start: str or None
        overlap_end: str or None
        bars_start: str or None
        bars_end: str or None
        funding_start: str or None
        funding_end: str or None
    """
```

---

## 4. Data Structures (Receipt Section Schema)

### Top-Level Section

```python
{
    "calculation_status": "FUNDING_TO_BARS_TIMESTAMP_CANONICALIZATION_DIAGNOSTIC_ONLY",
    "funding_application_status": "NOT_EXECUTED",
    "timestamp_canonicalization_policies": [
        {"policy_name": "floor", "policy_description": "truncate sub-second to zero"},
        {"policy_name": "round_half_away_from_zero",
         "policy_description": "round to nearest second, half away from zero"},
        {"policy_name": "ceil", "policy_description": "ceil to next whole second"},
    ],
    "symbol_count": <int>,
    "symbols": [...],
}
```

### Per-Symbol Entry

```python
{
    "symbol": "BTCUSDT",
    "bars_file": "BTCUSDT_8h_ohlcv.csv",
    "funding_file": "BTCUSDT_funding.csv",
    "bars_timestamp_count": 5271,
    "funding_timestamp_count": 5271,
    "raw_funding_subsecond_stats": {
        "subsecond_present": True,
        "subsecond_count": 5271,
        "subsecond_fraction": 1.0,
        "min_subsecond_microseconds": 1000,
        "max_subsecond_microseconds": 47000,
        "mean_subsecond_microseconds": 5432.1,
    },
    "canonicalization_policies": [
        {
            "policy_name": "floor",
            "collision_count": 0,
            "collision_groups": [],
            "unique_canonical_count": 5271,
            "collision_free_count": 5271,
            "ambiguous_nearest_bar_count": 0,
            "ambiguous_nearest_bar_rows": [],
            "unambiguous_count": 5271,
        },
        # ... same for round_half_away_from_zero and ceil
    ],
    "best_policy": {
        "policy_name": "floor",
        "collision_count": 0,
        "unique_canonical_count": 5271,
        "tie_count": 1,
        "tied_policy_names": ["floor"],
        "selection_reason": "FEWEST_COLLISIONS then PREFER_FLOOR",
    },
    "history_range_status": {
        "overlapped": True,
        "overlap_start": "2024-01-01T00:00:00Z",
        "overlap_end": "2026-01-01T00:00:00Z",
        "bars_start": "2024-01-01T00:00:00Z",
        "bars_end": "2026-01-01T00:00:00Z",
        "funding_start": "2024-01-01T00:00:00Z",
        "funding_end": "2026-04-22T08:00:00Z",
    },
    "subsecond_jitter_detected": True,
    "splits": [
        {
            "split_id": "split_00",
            "train_window": {
                "bars_timestamp_count": 0,
                "funding_timestamp_count": 0,
                "canonicalization_policies": [...],
                "best_policy": {...},
                "ambiguous_nearest_bar_count": 0,
                "unambiguous_count": 0,
                "collision_count": 0,
            },
            "validation_window": {
                # same structure
            },
        },
        # ...
    ],
    "funding_application_status": "NOT_EXECUTED",
    "calculation_status": "FUNDING_TO_BARS_TIMESTAMP_CANONICALIZATION_DIAGNOSTIC_ONLY",
}
```

---

## 5. Receipt Integration

### 5a. `build_real_validation_receipt` (line 2579)

Add parameter:
```python
funding_to_bars_timestamp_canonicalization_diagnostics: dict[str, Any] | None = None,
```

Add conditional inclusion (after line 2678):
```python
if funding_to_bars_timestamp_canonicalization_diagnostics is not None:
    receipt["funding_to_bars_timestamp_canonicalization_diagnostics"] = (
        funding_to_bars_timestamp_canonicalization_diagnostics
    )
```

### 5b. `main()` (line 2886)

Add after the timestamp convention diagnostics block (line 2958):
```python
funding_to_bars_timestamp_canonicalization_diagnostics = (
    materialize_funding_to_bars_timestamp_canonicalization_diagnostics(
        inventory=inventory,
        split_definitions=split_definitions,
    )
    if funding_dir is not None
    else None
)
```

Add to the `build_real_validation_receipt` call (after line 2982):
```python
funding_to_bars_timestamp_canonicalization_diagnostics=(
    funding_to_bars_timestamp_canonicalization_diagnostics
),
```

### 5c. `__all__` (line 49)

Add:
```python
"materialize_funding_to_bars_timestamp_canonicalization_diagnostics",
```

---

## 6. Main Function Pseudocode

```python
def materialize_funding_to_bars_timestamp_canonicalization_diagnostics(
    *,
    inventory: dict[str, Any],
    split_definitions: list[dict[str, Any]],
) -> dict[str, Any]:
    # 1. Validate inventory has both bars and funding roles
    roles = inventory.get("roles")
    # ... same pattern as timestamp_convention_diagnostics ...

    # 2. Build split windows
    windows = _build_split_windows_for_joinability(split_definitions)

    # 3. Load bars and funding timestamps by symbol
    bars_by_symbol = _load_role_symbol_timestamps(...)
    funding_by_symbol = _load_role_symbol_timestamps(...)

    # 4. Validate symbol parity
    # ...

    # 5. Define canonicalization policies
    policies = [
        ("floor", _canonicalize_floor),
        ("round_half_away_from_zero", _canonicalize_round_half_away_from_zero),
        ("ceil", _canonicalize_ceil),
    ]

    # 6. Process each symbol
    symbols = []
    for symbol in sorted(bars_symbols):
        bars_entry = bars_by_symbol[symbol]
        funding_entry = funding_by_symbol[symbol]
        bars_timestamps = bars_entry["timestamps"]
        funding_timestamps = funding_entry["timestamps"]
        bars_set = set(bars_timestamps)
        funding_set = set(funding_timestamps)

        # Subsecond stats
        subsecond_stats = _subsecond_stats(funding_timestamps)

        # History range status
        range_status = _history_range_status(...)

        # Per-policy analysis
        policy_results = []
        for policy_name, canonicalize_fn in policies:
            canonical = [canonicalize_fn(ft) for ft in funding_timestamps]
            collisions = _detect_canonicalization_collisions(
                funding_timestamps, canonicalize_fn
            )
            ambiguous = _detect_ambiguous_nearest_bars(
                canonical, bars_timestamps
            )
            policy_results.append({
                "policy_name": policy_name,
                **collisions,
                **ambiguous,
            })

        # Best policy selection
        best_policy = _select_best_canonicalization_policy(policy_results)

        # Overall subsecond jitter flag
        subsecond_jitter = subsecond_stats["subsecond_present"]

        # Per-split diagnostics
        split_diagnostics = []
        for window in windows:
            # ... filter timestamps by window ...
            # ... compute per-policy results for train/validation ...

        symbols.append({
            "symbol": symbol,
            "bars_file": bars_entry["filename"],
            "funding_file": funding_entry["filename"],
            "bars_timestamp_count": len(bars_timestamps),
            "funding_timestamp_count": len(funding_timestamps),
            "raw_funding_subsecond_stats": subsecond_stats,
            "canonicalization_policies": policy_results,
            "best_policy": best_policy,
            "history_range_status": range_status,
            "subsecond_jitter_detected": subsecond_jitter,
            "splits": split_diagnostics,
            "funding_application_status": "NOT_EXECUTED",
            "calculation_status": (
                "FUNDING_TO_BARS_TIMESTAMP_CANONICALIZATION_DIAGNOSTIC_ONLY"
            ),
        })

    return {
        "calculation_status": "FUNDING_TO_BARS_TIMESTAMP_CANONICALIZATION_DIAGNOSTIC_ONLY",
        "funding_application_status": "NOT_EXECUTED",
        "timestamp_canonicalization_policies": [
            {"policy_name": "floor",
             "policy_description": "truncate sub-second to zero"},
            {"policy_name": "round_half_away_from_zero",
             "policy_description": "round to nearest whole second, half away from zero"},
            {"policy_name": "ceil",
             "policy_description": "ceil to next whole second"},
        ],
        "symbol_count": len(symbols),
        "symbols": symbols,
    }
```

---

## 7. Test Plan — 24 Test Cases

All tests go in class `TestFundingToBarsTimestampCanonicalizationDiagnostics` in [`tests/experiment/test_offline_edge_real_validation.py`](tests/experiment/test_offline_edge_real_validation.py) after the existing timestamp convention tests (after line 3379).

### Test Infrastructure

```python
class TestFundingToBarsTimestampCanonicalizationDiagnostics:
    @staticmethod
    def _inventory(
        tmp_path: Path,
        *,
        bars_timestamps: list[str],
        funding_timestamps: list[str],
        bars_filename: str = "BTCUSDT_8h_ohlcv.csv",
        funding_filename: str = "BTCUSDT_funding.csv",
    ) -> dict:
        # Same pattern as TestFundingToBarsTimestampConventionDiagnostics._inventory
        ...

    def _build(
        self, tmp_path, *, split_definitions=None, **kwargs
    ):
        inventory = self._inventory(tmp_path, **kwargs)
        return materialize_funding_to_bars_timestamp_canonicalization_diagnostics(
            inventory=inventory,
            split_definitions=split_definitions or _two_split_windows(),
        )
```

Use existing timestamp constants `_T1`, `_T2`, `_T3`, `_B1`, `_B2`, etc. from the test file. Add new constants for subsecond timestamps:

```python
_B1_SUBSECOND = "2026-01-01T00:00:00.123000Z"
_B2_SUBSECOND = "2026-01-02T00:00:00.456000Z"
_B3_SUBSECOND_500MS = "2026-01-03T00:00:00.500000Z"
_B1_SUBSECOND_999MS = "2026-01-01T00:00:00.999000Z"
_B2_EXACT = "2026-01-02T00:00:00.000000Z"
```

### Test Case Details

| # | Test Method | What It Validates |
|---|-------------|-------------------|
| 1 | `test_floor_no_subsecond_no_collisions` | Floor with exact-second funding timestamps → 0 collisions, `unique_canonical_count == funding_timestamp_count` |
| 2 | `test_floor_subsecond_present_canonicalizes` | Floor with subsecond funding timestamps → `raw_funding_subsecond_stats.subsecond_present is True`, microsecond component truncated |
| 3 | `test_round_half_away_from_zero_500ms_rounds_up` | 500ms rounds to next second (positive microsecond threshold) |
| 4 | `test_round_half_away_from_zero_499ms_rounds_down` | 499ms rounds to same second |
| 5 | `test_round_half_away_from_zero_501ms_rounds_up` | 501ms rounds to next second |
| 6 | `test_ceil_no_subsecond_unchanged` | Ceil with exact-second timestamps → no change |
| 7 | `test_ceil_subsecond_present_bumps` | Ceil with subsecond timestamps → timestamp bumps to next second |
| 8 | `test_collision_detection_two_raw_same_canonical` | Two funding timestamps (e.g., `T1+0.1s` and `T1+0.2s`) both floor to `T1` → `collision_count == 2`, `collision_groups` has 1 group with count 2 |
| 9 | `test_collision_detection_three_raw_same_canonical` | Three funding timestamps all floor to same second → `collision_count == 3` |
| 10 | `test_collision_detection_no_collisions` | All funding timestamps already whole-seconds → `collision_count == 0`, `collision_free_count == funding_timestamp_count` |
| 11 | `test_ambiguous_nearest_bar_equidistant` | Funding timestamp exactly between two bar timestamps → `ambiguous_nearest_bar_count == 1`, `ambiguous_nearest_bar_rows` has entry with equal distances |
| 12 | `test_ambiguous_nearest_bar_no_ambiguity` | Each funding timestamp clearly nearest one bar → `ambiguous_nearest_bar_count == 0` |
| 13 | `test_best_policy_floor_wins` | Floor has fewest collisions → `best_policy.policy_name == "floor"` |
| 14 | `test_best_policy_round_wins` | Round has fewest collisions → `best_policy.policy_name == "round_half_away_from_zero"` |
| 15 | `test_best_policy_ceil_wins` | Ceil has fewest collisions → `best_policy.policy_name == "ceil"` |
| 16 | `test_best_policy_tie_deterministic` | All policies have same collision count → tie broken by canonical order (floor > round > ceil). `tie_count == 3`, winner is `"floor"` |
| 17 | `test_history_range_overlap` | Bars and funding overlap → `history_range_status.overlapped is True`, `overlap_start` and `overlap_end` populated |
| 18 | `test_history_range_no_overlap` | Bars and funding disjoint → `history_range_status.overlapped is False` |
| 19 | `test_subsecond_jitter_detected` | Funding has subsecond timestamps → `subsecond_jitter_detected is True` |
| 20 | `test_subsecond_jitter_not_detected` | All funding timestamps are exact seconds → `subsecond_jitter_detected is False` |
| 21 | `test_per_split_diagnostics_uses_boundary_policy` | Per-split windows use existing start-inclusive/end-exclusive policy; verify against `_two_split_windows()` |
| 22 | `test_duplicate_funding_timestamp_fails_closed` | Duplicate `fundingTime` → raises `ValueError` matching "Duplicate fundingTime" |
| 23 | `test_non_monotonic_funding_timestamp_fails_closed` | Non-monotonic `fundingTime` → raises `ValueError` matching "Non-monotonic" |
| 24 | `test_safe_keys_and_receipt_guardrails` | Full receipt integration: section in receipt, no forbidden keys, `BLOCKED_BY_VALIDATION_IMPLEMENTATION`, etc. |

---

## 8. Execution Order

### Phase 1: Helper Functions (file: `offline_edge_real_validation.py`)

1. Add `_canonicalize_floor(dt) -> datetime` — insert after the timestamp convention helpers (after `_nearest_delta_histogram` at line 2301)
2. Add `_canonicalize_round_half_away_from_zero(dt) -> datetime`
3. Add `_canonicalize_ceil(dt) -> datetime`
4. Add `_detect_canonicalization_collisions(raw_timestamps, canonicalize_fn) -> dict`
5. Add `_detect_ambiguous_nearest_bars(funding_canonical, bars_timestamps) -> dict`
6. Add `_subsecond_stats(timestamps) -> dict`
7. Add `_select_best_canonicalization_policy(policy_results) -> dict`
8. Add `_history_range_status(...) -> dict`

### Phase 2: Main Function (file: `offline_edge_real_validation.py`)

9. Add `materialize_funding_to_bars_timestamp_canonicalization_diagnostics` function body after line 2524
10. Add to `__all__` list

### Phase 3: Receipt Integration (file: `offline_edge_real_validation.py`)

11. Add parameter to `build_real_validation_receipt` signature (line 2579)
12. Add conditional inclusion in receipt body (after line 2678)
13. Add CLI call in `main()` (after line 2958)
14. Add parameter to `build_real_validation_receipt` call in `main()` (after line 2982)

### Phase 4: Tests (file: `tests/experiment/test_offline_edge_real_validation.py`)

15. Add new timestamp constants for subsecond values
16. Add `TestFundingToBarsTimestampCanonicalizationDiagnostics` class with `_inventory` and `_build` helpers
17. Add tests 1-24 in order

### Phase 5: Verify

18. Run `python -m pytest tests/experiment/test_offline_edge_real_validation.py -x -v`
19. Verify all existing tests still pass (regression)
20. Verify no forbidden imports (AST scan test)

---

## 9. Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Negative microseconds on pre-epoch timestamps | `_canonicalize_round_half_away_from_zero` handles `<= -500_000` case; `_canonicalize_ceil` only handles `> 0` |
| Very large collision groups (thousands of raw → one canonical) | `collision_groups` lists `raw_timestamps` capped at e.g. 10 per group with `truncated_to` count; or just list timestamps for small groups and show count for large |
| Ambiguous nearest bar with empty bars | `_detect_ambiguous_nearest_bars` returns 0 counts when bars or funding empty |
| Rounding 500ms at epoch boundary | Test coverage for `1970-01-01T00:00:00.500000Z` |
| Performance with 5000+ timestamps | All algorithms O(n log n) or better; `bisect` is O(log n) per lookup |

---

## 10. Rollback Plan

```bash
git checkout -- quantbot/experiment/offline_edge_real_validation.py
git checkout -- tests/experiment/test_offline_edge_real_validation.py
```

Or if partial revert needed:

```bash
git diff quantbot/experiment/offline_edge_real_validation.py | \
  grep '^[+-]' | grep -v '^[+-]{3}' | grep -v '^[+-]import' | \
  patch -R
```

---

## 11. Verification Checklist

After implementation, run these checks:

```bash
# Full test suite
python -m pytest tests/experiment/test_offline_edge_real_validation.py -x -v 2>&1 | tail -30

# AST import scan
python -c "
import ast, sys
tree = ast.parse(open('quantbot/experiment/offline_edge_real_validation.py').read())
for node in ast.walk(tree):
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        print(node.names if isinstance(node, ast.Import) else node.module)
"

# CLI smoke test with real data
python -m quantbot.experiment.offline_edge_real_validation \
  --read-only \
  --output-dir /tmp/qnty_canon_smoke \
  --input-manifest-fingerprint aaaaa... \
  --data-quality-receipt-sha256 bbbbb... \
  --code-commit-sha ccccc... \
  --bars-dir /path/to/bars \
  --funding-dir /path/to/funding