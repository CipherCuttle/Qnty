"""Path dispersion diagnostic (NOT Bailey-style CSCV/PBO).

IMPORTANT: This is a PROXY DIAGNOSTIC, not the Bailey et al. CSCV/PBO method.

This module measures path-score dispersion as a proxy for potential overfitting.
It does NOT implement the canonical CSCV procedure which requires:
- Paired train/test return series per split
- Combinatorial enumeration of all path combinations
- Direct comparison of in-sample vs out-of-sample performance per path

Instead, this implementation uses a z-score heuristic on path variance,
which is fundamentally different from true PBO.

Paper mode only - no live trading, no profitability claims.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Literal

from quantbot.experiment.result import ReturnSeries, WalkForwardSplitResult


# Combinatorial path cap to prevent explosion
_MAX_PATHS: int = 1000


@dataclass
class PathDispersionSummary:
    """Result of path dispersion diagnostic (proxy for PBO).

    IMPORTANT: This is NOT the Bailey et al. CSCV/PBO method.
    This measures path-score dispersion as a proxy for overfitting risk.

    Attributes:
        method: Always "path_dispersion" for this implementation.
        path_count: Number of combinatorial paths evaluated.
        dispersion_ratio: Z-score-based dispersion measure (0.0-1.0).
            Higher = more dispersion across paths (potential overfitting signal).
            Lower = paths score similarly (more consistent).
        assumptions: Explicit list of assumptions made.
        limitations: Explicit list of limitations.
        provenance: Dict with family_id, variant_id, artifact_path.
    """

    method: str = "path_dispersion"
    path_count: int = 0
    dispersion_ratio: float = 0.0
    assumptions: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    provenance: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize to dict for JSON output."""
        return {
            "method": self.method,
            "path_count": self.path_count,
            "dispersion_ratio": self.dispersion_ratio,
            "assumptions": self.assumptions,
            "limitations": self.limitations,
            "provenance": self.provenance,
        }


@dataclass
class PBOSummary:
    """Result of Bailey-style PBO computation.

    PBO (Probability of Beat a Random) measures the probability that an
    in-sample selected path beats a randomly selected path out-of-sample.

    Attributes:
        method: Always "pbo" for this implementation.
        path_count: Number of combinatorial paths evaluated.
        selection_metric: Metric used for in-sample selection ("sharpe" or "return").
        pbo: Probability of beat-a-random (0.0 to 1.0).
        assumptions: Explicit list of assumptions made.
        limitations: Explicit list of known limitations.
        provenance: Dict linking back to family/variant/artifact.
    """

    method: str = "pbo"
    path_count: int = 0
    selection_metric: str = "sharpe"
    pbo: float = 0.0
    assumptions: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    provenance: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize to dict for JSON output."""
        return {
            "method": self.method,
            "path_count": self.path_count,
            "selection_metric": self.selection_metric,
            "pbo": self.pbo,
            "assumptions": self.assumptions,
            "limitations": self.limitations,
            "provenance": self.provenance,
        }


# Threshold constants for PBO status classification.
# Observational labels only — no promotion claims.
PBO_INSUFFICIENT_PATH_COUNT: int = 3
PBO_LOW_RISK_THRESHOLD: float = 0.05
PBO_ELEVATED_RISK_THRESHOLD: float = 0.15


def classify_pbo_status(pbo: float | None, path_count: int | None) -> str:
    """Classify overfit risk from PBO metric.

    Policy knobs (inspectable at module level):
        PBO_INSUFFICIENT_PATH_COUNT : minimum path count for classification
        PBO_LOW_RISK_THRESHOLD      : pbo <= this → low overfit risk
        PBO_ELEVATED_RISK_THRESHOLD  : pbo <= this → elevated overfit risk

    Status values:
        insufficient_data : pbo is None or path_count < PBO_INSUFFICIENT_PATH_COUNT
        low_overfit_risk   : pbo <= PBO_LOW_RISK_THRESHOLD with sufficient paths
        elevated_overfit_risk : PBO_LOW_RISK_THRESHOLD < pbo <= PBO_ELEVATED_RISK_THRESHOLD
        high_overfit_risk  : pbo > PBO_ELEVATED_RISK_THRESHOLD

    Returns:
        One of: "insufficient_data", "low_overfit_risk", "elevated_overfit_risk", "high_overfit_risk"
    """
    if pbo is None or path_count is None or path_count < PBO_INSUFFICIENT_PATH_COUNT:
        return "insufficient_data"
    if pbo <= PBO_LOW_RISK_THRESHOLD:
        return "low_overfit_risk"
    if pbo <= PBO_ELEVATED_RISK_THRESHOLD:
        return "elevated_overfit_risk"
    return "high_overfit_risk"


def pbo_status_label(pbo: float | None, path_count: int | None) -> str:
    """Compact inline PBO risk label for display.

    Returns a short label suitable for inline display in review rows.
    """
    status = classify_pbo_status(pbo, path_count)
    if status == "insufficient_data":
        return "pbo=?"
    if status == "low_overfit_risk":
        return f"pbo={pbo:.3f}"
    if status == "elevated_overfit_risk":
        return f"pbo={pbo:.3f}!"
    return f"pbo={pbo:.3f}!!"


def _compute_sharpe(returns: list[float], bars_per_year: Optional[float] = None) -> float:
    """Compute Sharpe-like ratio from return series.

    Args:
        returns: List of per-bar returns.
        bars_per_year: Annualization factor. If None, returns unannualized.

    Returns:
        Sharpe-like ratio (annualized if bars_per_year provided).
    """
    if not returns:
        return 0.0

    n = len(returns)
    if n < 2:
        return 0.0

    mean = sum(returns) / n

    # Population std (ddof=0)
    squared_diffs = [(r - mean) ** 2 for r in returns]
    variance = sum(squared_diffs) / n
    std = math.sqrt(variance)

    if std == 0.0:
        return 0.0  # Cannot compute Sharpe when std is zero

    sharpe = mean / std

    # Annualize if factor provided
    if bars_per_year is not None:
        sharpe = sharpe * math.sqrt(bars_per_year)

    return sharpe


def _generate_paths(
    split_metrics: list[list[float]],
    max_paths: int,
) -> list[list[int]]:
    """Generate combinatorial paths by picking one metric per split.

    Args:
        split_metrics: List of metric values per split (one per walk-forward split).
        max_paths: Maximum number of paths to generate.

    Returns:
        List of paths, where each path is a list of indices (one per split).
    """
    if not split_metrics:
        return []

    # For N splits with Mi options per split, total paths = product(Mi)
    # But we cap at max_paths and use sampling if too many

    n_splits = len(split_metrics)

    # Count total possible paths
    total_paths = 1
    for split_opts in split_metrics:
        total_paths *= len(split_opts)
        if total_paths > max_paths * 100:  # Way over cap, will need sampling
            break

    if total_paths <= max_paths:
        # Generate all paths via Cartesian product
        paths = _cartesian_product(split_metrics)
        return paths
    else:
        # Sample max_paths random paths (deterministic with seed)
        # Use a simple hash-based approach for reproducibility
        return _sample_paths(split_metrics, max_paths)


def _cartesian_product(split_metrics: list[list[float]]) -> list[list[int]]:
    """Generate full Cartesian product of indices."""
    if not split_metrics:
        return []

    n_splits = len(split_metrics)

    # Start with first split's indices
    paths = [[i] for i in range(len(split_metrics[0]))]

    # Iterate through remaining splits
    for split_idx in range(1, n_splits):
        new_paths = []
        for path in paths:
            for opt_idx in range(len(split_metrics[split_idx])):
                new_paths.append(path + [opt_idx])
        paths = new_paths

    return paths


def _sample_paths(split_metrics: list[list[float]], max_paths: int) -> list[list[int]]:
    """Sample paths deterministically to stay under max_paths."""
    n_splits = len(split_metrics)
    paths = []

    # Simple approach: iterate through first split up to max_paths, then fill
    # This is deterministic and covers the space reasonably
    for i in range(min(max_paths, len(split_metrics[0]))):
        # For each i in first split, pick corresponding index in others if available
        path = [i]
        for split_idx in range(1, n_splits):
            # Use modular arithmetic for consistent selection
            opt_idx = i % len(split_metrics[split_idx])
            path.append(opt_idx)
        paths.append(path)

    # If we still have room, add more varied paths
    if len(paths) < max_paths:
        # Add paths with different combinations
        for offset in range(1, len(split_metrics[0])):
            if len(paths) >= max_paths:
                break
            path = [offset]
            for split_idx in range(1, n_splits):
                opt_idx = (offset + split_idx) % len(split_metrics[split_idx])
                path.append(opt_idx)
            paths.append(path)

    return paths


def compute_path_dispersion(
    return_series_list: list[ReturnSeries],
    metric_name: str = "sharpe",
    family_id: Optional[str] = None,
    variant_id: Optional[str] = None,
    artifact_path: Optional[str] = None,
) -> PathDispersionSummary:
    """Compute path dispersion diagnostic (proxy for PBO).

    IMPORTANT: This is NOT the Bailey et al. CSCV/PBO method.
    This measures z-score-based dispersion across combinatorial paths as a
    proxy for potential overfitting risk.

    Args:
        return_series_list: List of ReturnSeries, one per walk-forward split.
            Each ReturnSeries represents the in-sample (train) returns for that split.
        metric_name: Metric to use. Currently only "sharpe" is supported.
        family_id: Optional family identifier for provenance.
        variant_id: Optional variant identifier for provenance.
        artifact_path: Optional artifact path for provenance.

    Returns:
        PathDispersionSummary with dispersion_ratio and diagnostic metadata.
    """
    assumptions = [
        "NOT Bailey-style CSCV/PBO - lacks paired train/test data per split",
        "No purge/embargo between train/test periods (inherited from walk-forward)",
        "Metric is Sharpe ratio (unless specified otherwise)",
        "Returns are log returns",
        "No transaction costs in computation (costs already in return series)",
        "Combinatorial paths are sampled if total exceeds cap (may introduce bias)",
    ]

    limitations = [
        "NOT CSCV/PBO - uses z-score heuristic on path variance, not OOS ratio",
        "Combinatorial explosion risk - capped at 1000 paths max",
        "Single metric assumption - different metric may yield different dispersion",
        "Sampled paths may not fully represent the combinatorial space",
        "This is a PROXY DIAGNOSTIC, not proof of edge or profitability",
        "Cannot detect overfitting to test period with this approach",
    ]

    provenance = {}
    if family_id:
        provenance["family_id"] = family_id
    if variant_id:
        provenance["variant_id"] = variant_id
    if artifact_path:
        provenance["artifact_path"] = artifact_path

    # Handle degenerate cases
    if not return_series_list:
        return PathDispersionSummary(
            method="path_dispersion",
            path_count=0,
            dispersion_ratio=0.0,
            assumptions=assumptions,
            limitations=limitations,
            provenance=provenance,
        )

    n_splits = len(return_series_list)
    if n_splits == 1:
        # Single split - cannot compute dispersion
        return PathDispersionSummary(
            method="path_dispersion",
            path_count=1,
            dispersion_ratio=0.0,
            assumptions=assumptions,
            limitations=limitations + ["Single split - cannot measure path dispersion"],
            provenance=provenance,
        )

    # Extract per-split metrics (Sharpe-like) from each ReturnSeries
    split_metrics: list[list[float]] = []
    for rs in return_series_list:
        # Use net_returns for Sharpe computation
        if not rs.net_returns:
            # Empty series - use 0.0 metric
            split_metrics.append([0.0])
        else:
            # Compute Sharpe from net_returns
            sharpe = _compute_sharpe(rs.net_returns)
            split_metrics.append([sharpe])

    # Check if we have actual variation across splits
    all_metrics = [m for split in split_metrics for m in split]
    if len(set(all_metrics)) <= 1:
        # All metrics identical - cannot determine dispersion
        return PathDispersionSummary(
            method="path_dispersion",
            path_count=len(split_metrics),
            dispersion_ratio=0.0,
            assumptions=assumptions,
            limitations=limitations + ["All metrics identical - no variation to measure"],
            provenance=provenance,
        )

    # Generate combinatorial paths
    paths = _generate_paths(split_metrics, _MAX_PATHS)

    if not paths:
        return PathDispersionSummary(
            method="path_dispersion",
            path_count=0,
            dispersion_ratio=0.0,
            assumptions=assumptions,
            limitations=limitations,
            provenance=provenance,
        )

    # Compute path scores (sum of metrics across splits per path)
    path_scores = []
    for path in paths:
        path_score = sum(split_metrics[split_idx][opt_idx] for split_idx, opt_idx in enumerate(path))
        path_scores.append(path_score)

    if not path_scores:
        dispersion_ratio = 0.0
    else:
        best_score = max(path_scores)
        avg_score = sum(path_scores) / len(path_scores)

        if avg_score == 0:
            dispersion_ratio = 0.0
        else:
            variance = sum((s - avg_score) ** 2 for s in path_scores) / len(path_scores)
            std = math.sqrt(variance) if variance > 0 else 0.0

            if std == 0:
                # All paths same score - no dispersion
                dispersion_ratio = 0.0
            else:
                # Z-score of best path
                z = (best_score - avg_score) / std
                # Convert to dispersion measure: high z = high dispersion
                if z < 1.0:
                    dispersion_ratio = 0.0
                elif z < 2.0:
                    dispersion_ratio = 0.25
                elif z < 3.0:
                    dispersion_ratio = 0.5
                else:
                    dispersion_ratio = 0.75

    return PathDispersionSummary(
        method="path_dispersion",
        path_count=len(paths),
        dispersion_ratio=dispersion_ratio,
        assumptions=assumptions,
        limitations=limitations,
        provenance=provenance,
    )


# Backward compatibility alias - marks the old interface as deprecated
def compute_pbo_cscv(
    return_series_list: list[ReturnSeries],
    metric_name: str = "sharpe",
    family_id: Optional[str] = None,
    variant_id: Optional[str] = None,
    artifact_path: Optional[str] = None,
) -> PathDispersionSummary:
    """DEPRECATED: Use compute_path_dispersion instead.

    This function now returns PathDispersionSummary, not true CSCV/PBO.
    """
    return compute_path_dispersion(
        return_series_list, metric_name, family_id, variant_id, artifact_path
    )


def _aggregate_metric(
    rs: ReturnSeries,
    metric: Literal["sharpe", "return"] = "sharpe",
) -> float:
    """Aggregate return series into a single score for path selection.

    Args:
        rs: ReturnSeries to aggregate.
        metric: "sharpe" for Sharpe-like ratio, "return" for net return total.

    Returns:
        Aggregate score (higher is better for selection).
    """
    if not rs.net_returns:
        return 0.0

    if metric == "sharpe":
        return _compute_sharpe(rs.net_returns)
    else:  # "return"
        return sum(rs.net_returns)


def compute_pbo(
    paths: list[list[WalkForwardSplitResult]],
    selection_metric: Literal["sharpe", "return"] = "sharpe",
    family_id: Optional[str] = None,
    variant_id: Optional[str] = None,
    artifact_path: Optional[str] = None,
) -> PBOSummary:
    """Compute Bailey-style PBO using paired train/test return series.

    PBO (Probability of Beat a Random) is the probability that a path selected
    based on in-sample (train) performance beats a randomly selected path
    out-of-sample (test).

    Procedure:
    1. For each path, compute in-sample score from train splits and
       out-of-sample score from test splits.
    2. Select the best in-sample path (highest train score).
    3. Count how many random paths the selected path beats OOS.
    4. PBO = fraction of random paths beaten.

    Args:
        paths: List of paths, where each path is a list of WalkForwardSplitResult
            with split_role="both". Each split has train_inference_summary,
            train_return_summary (for IS score) and return_series/return_summary
            (for OOS score).
        selection_metric: "sharpe" uses Sharpe-like ratio; "return" uses net return total.
        family_id: Optional family identifier for provenance.
        variant_id: Optional variant identifier for provenance.
        artifact_path: Optional artifact path for provenance.

    Returns:
        PBOSummary with pbo probability and diagnostic metadata.
    """
    assumptions = [
        "PBO is computed as P(selected beats random OOS), not combinatorial CSCV",
        "Train/test split is inherited from walk-forward (no purge/embargo applied here)",
        "Best-in-sample selection is deterministic (highest train score wins)",
        "Win condition: selected path OOS score > random path OOS score",
        "Selection metric: " + selection_metric + " (from train_inference_summary or train_return_summary)",
        "Evaluation metric: same as selection metric, computed on test-side data",
        "Log returns used for Sharpe computation",
        "No transaction costs in computation (costs already in return series)",
        "This is a DIAGNOSTIC for overfitting, not proof of edge or profitability",
    ]

    limitations = [
        "Bailey-style PBO requires many random paths - results unstable with few paths",
        "No purge/embargo between train and test periods (inherited from walk-forward)",
        "Best-of-N selection introduces selection bias not accounted for in PBO formula",
        "Single selection (best) - does not represent full combinatorial enumeration",
        "Test period performance may not generalize to live trading",
        "This is a DIAGNOSTIC, not proof of edge or readiness to trade",
    ]

    provenance = {}
    if family_id:
        provenance["family_id"] = family_id
    if variant_id:
        provenance["variant_id"] = variant_id
    if artifact_path:
        provenance["artifact_path"] = artifact_path

    # Handle degenerate cases
    if not paths:
        return PBOSummary(
            method="pbo",
            path_count=0,
            selection_metric=selection_metric,
            pbo=0.0,
            assumptions=assumptions,
            limitations=limitations,
            provenance=provenance,
        )

    if len(paths) < 2:
        return PBOSummary(
            method="pbo",
            path_count=len(paths),
            selection_metric=selection_metric,
            pbo=0.0,
            assumptions=assumptions,
            limitations=limitations + ["Need at least 2 paths for PBO comparison"],
            provenance=provenance,
        )

    # Compute in-sample and out-of-sample scores for each path
    path_scores: list[tuple[int, float, float]] = []  # (path_idx, train_score, test_score)

    for path_idx, path in enumerate(paths):
        # Collect train and test scores across splits
        train_scores: list[float] = []
        test_scores: list[float] = []

        for split in path:
            if split.split_role != "both":
                continue

            # In-sample score: use train_inference_summary or train_return_summary
            if split.train_inference_summary is not None:
                if selection_metric == "sharpe":
                    train_score = split.train_inference_summary.sharpe_like or 0.0
                else:
                    train_score = split.train_return_summary.net_return_total if split.train_return_summary else 0.0
                train_scores.append(train_score)

            # Out-of-sample score: use return_series
            if split.return_series is not None and split.return_series.net_returns:
                if selection_metric == "sharpe":
                    test_score = _compute_sharpe(split.return_series.net_returns)
                else:
                    test_score = sum(split.return_series.net_returns)
                test_scores.append(test_score)

        if not train_scores or not test_scores:
            # Cannot compute path score - use zeros
            path_scores.append((path_idx, 0.0, 0.0))
        else:
            # Aggregate across splits (simple sum for now)
            train_score = sum(train_scores) / len(train_scores) if train_scores else 0.0
            test_score = sum(test_scores) / len(test_scores) if test_scores else 0.0
            path_scores.append((path_idx, train_score, test_score))

    if not path_scores:
        return PBOSummary(
            method="pbo",
            path_count=0,
            selection_metric=selection_metric,
            pbo=0.0,
            assumptions=assumptions,
            limitations=limitations + ["No valid path scores computed"],
            provenance=provenance,
        )

    # Select best in-sample path
    best_path_idx, best_train_score, best_test_score = max(
        path_scores, key=lambda x: x[1]
    )

    # Compute PBO: probability that selected path BEATS a random path OOS.
    # Higher OOS score = better (for Sharpe/return metrics where higher is better).
    # PBO = fraction of random paths that the selected path beats.
    # If selected_path OOS > random_path OOS, selected beats random.
    # If selected_path OOS < random_path OOS, random beats selected (overfitting signal).
    selected_beats_count = 0
    total_random = len(path_scores) - 1  # Exclude self

    for path_idx, train_score, test_score in path_scores:
        if path_idx == best_path_idx:
            continue  # Skip self
        if best_test_score > test_score:
            # Selected beats random OOS
            selected_beats_count += 1
        elif best_test_score == test_score:
            # Half credit for ties
            selected_beats_count += 0.5
        # else: random beats selected (overfitting signal) - no increment

    if total_random > 0:
        pbo = selected_beats_count / total_random
    else:
        pbo = 0.0

    return PBOSummary(
        method="pbo",
        path_count=len(paths),
        selection_metric=selection_metric,
        pbo=pbo,
        assumptions=assumptions,
        limitations=limitations,
        provenance=provenance,
    )