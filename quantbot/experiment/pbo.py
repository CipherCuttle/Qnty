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
from typing import Optional

from quantbot.experiment.result import ReturnSeries


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