"""Minimal experiment result for QuantBot.

Paper mode only - no real trading, no profitability claims.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from quantbot.core.determinism import canonical_json_dumps
from quantbot.experiment.spec import ExperimentSpec

if TYPE_CHECKING:
    from quantbot.experiment.gates import GateVerdict


@dataclass
class EconomicsSummary:
    """Event-accounting summary for cost estimation.

    Tracks explicit position transitions that incur costs:
    - entry: position opens (None -> long/short)
    - exit: position closes (long/short -> None)
    - flip: position reverses (long -> short or short -> long)

    A flip counts as exit + entry (2 cost-bearing events).
    """

    cost_side_count: int = 0
    entry_count: int = 0
    exit_count: int = 0
    flip_count: int = 0
    fee_bps: float = 0.0
    slippage_bps: float = 0.0
    assumed_total_cost_bps: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "cost_side_count": self.cost_side_count,
            "entry_count": self.entry_count,
            "exit_count": self.exit_count,
            "flip_count": self.flip_count,
            "fee_bps": self.fee_bps,
            "slippage_bps": self.slippage_bps,
            "assumed_total_cost_bps": self.assumed_total_cost_bps,
        }


@dataclass
class ReturnSummary:
    """Return series summary for an experiment.

    Computes deterministic gross and net returns from bar-to-bar close changes
    under derived position state. Costs are applied as basis points of notional
    on each cost-bearing event (entry, exit, flip).

    Attributes:
        gross_return_total: Cumulative gross return (product of 1 + bar returns).
        net_return_total: Gross return minus event-based costs.
        cost_deduction_total: Total cost deducted in return terms.
        bars_held: Number of bars with non-flat position.
        winning_bars: Number of bars with positive return.
        losing_bars: Number of bars with negative return.
    """

    gross_return_total: float = 0.0
    net_return_total: float = 0.0
    cost_deduction_total: float = 0.0
    bars_held: int = 0
    winning_bars: int = 0
    losing_bars: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "gross_return_total": self.gross_return_total,
            "net_return_total": self.net_return_total,
            "cost_deduction_total": self.cost_deduction_total,
            "bars_held": self.bars_held,
            "winning_bars": self.winning_bars,
            "losing_bars": self.losing_bars,
        }


@dataclass
class ReturnSeries:
    """Per-bar return series for an experiment.

    Preserves the full per-bar gross and net return sequence for later
    honest inference. Interval may be 'unknown' if not reliably determined
    from the data source.

    Attributes:
        gross_returns: Per-bar gross return series (1-element per bar held).
        net_returns: Per-bar net return series (gross minus cost per bar).
        bar_timestamps: ISO timestamp for each bar in the series.
        interval: Bar interval string (e.g., '8h', '1d') or 'unknown'.
    """

    gross_returns: list[float] = field(default_factory=list)
    net_returns: list[float] = field(default_factory=list)
    bar_timestamps: list[str] = field(default_factory=list)
    interval: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "gross_returns": self.gross_returns,
            "net_returns": self.net_returns,
            "bar_timestamps": self.bar_timestamps,
            "interval": self.interval,
        }


@dataclass
class InferenceSummary:
    """Inferential summary statistics computed from a per-bar return series.

    All statistics are computed directly from the preserved net_returns series.
    Annualization is EXPLICITLY DISABLED unless the bar interval is known and
    documented. sharpe_like will be None unless annualized is True.

    Attributes:
        bar_count_for_returns: Length of the net_returns series (bars held).
        mean_return: Mean of net_returns series.
        std_return: Standard deviation of net_returns series (population).
                     None if bar_count < 2 (std undefined for single observation).
        gross_return_total: Sum/gross total from series computation.
        net_return_total: Sum/net total from series computation.
        cost_deduction_total: gross - net total.
        sharpe_like: Sharpe-ratio-like statistic ONLY if interval is known.
                    None otherwise (interval unknown = cannot annualize).
        annualized: False unless interval is known and annualization was applied.
        interval: 'unknown' or the actual bar interval string.
        annualization_note: Human-readable note explaining why not annualized,
                           or what annualization was applied.
    """

    bar_count_for_returns: int = 0
    mean_return: float = 0.0
    std_return: Optional[float] = None
    gross_return_total: float = 0.0
    net_return_total: float = 0.0
    cost_deduction_total: float = 0.0
    sharpe_like: Optional[float] = None
    annualized: bool = False
    interval: str = "unknown"
    annualization_note: str = "not annualized - interval unknown"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "bar_count_for_returns": self.bar_count_for_returns,
            "mean_return": self.mean_return,
            "std_return": self.std_return,
            "gross_return_total": self.gross_return_total,
            "net_return_total": self.net_return_total,
            "cost_deduction_total": self.cost_deduction_total,
            "sharpe_like": self.sharpe_like,
            "annualized": self.annualized,
            "interval": self.interval,
            "annualization_note": self.annualization_note,
        }


def compute_inference_summary(return_series: ReturnSeries) -> InferenceSummary:
    """Compute inference statistics from a ReturnSeries.

    Statistics are computed from the net_returns series only.
    std_return uses population standard deviation (ddof=0).
    sharpe_like is ONLY computed if interval is known and bars >= 2.

    Degenerate cases handled:
    - Empty series: returns zero/invalid stats
    - Single bar: std_return = None (undefined)
    - All identical returns: std_return = 0.0

    Args:
        return_series: ReturnSeries with net_returns and interval.

    Returns:
        InferenceSummary with computed statistics.
    """
    net_returns = return_series.net_returns
    bar_count = len(net_returns)
    interval = return_series.interval

    if bar_count == 0:
        return InferenceSummary(
            bar_count_for_returns=0,
            mean_return=0.0,
            std_return=None,
            gross_return_total=0.0,
            net_return_total=0.0,
            cost_deduction_total=0.0,
            sharpe_like=None,
            annualized=False,
            interval=interval,
            annualization_note="not annualized - empty return series",
        )

    # Compute mean
    mean_return = sum(net_returns) / bar_count

    # Compute population std (ddof=0)
    std_return: Optional[float] = None
    if bar_count >= 2:
        squared_diffs = [(r - mean_return) ** 2 for r in net_returns]
        variance = sum(squared_diffs) / bar_count
        std_return = math.sqrt(variance)
    else:
        # Single bar - std undefined
        std_return = None

    # Compute totals from series (not pre-computed)
    net_return_total = sum(net_returns)
    gross_return_total = sum(return_series.gross_returns)
    cost_deduction_total = gross_return_total - net_return_total

    # sharpe_like only if interval is known and bars >= 2
    sharpe_like: Optional[float] = None
    annualized = False
    annualization_note = "not annualized - interval unknown"

    if interval != "unknown" and bar_count >= 2 and std_return is not None and std_return > 0:
        # Annualization factor: assume ~252 trading periods per year for crypto
        # This is an approximation; 24h/day * 365.25 days ~= 8766 but crypto trades 24/7
        # For bar intervals like '8h', '1h', '4h' we can compute annualization
        annualization_note = f"not annualized - interval '{interval}' requires explicit annualization factor"

    return InferenceSummary(
        bar_count_for_returns=bar_count,
        mean_return=mean_return,
        std_return=std_return,
        gross_return_total=gross_return_total,
        net_return_total=net_return_total,
        cost_deduction_total=cost_deduction_total,
        sharpe_like=sharpe_like,
        annualized=annualized,
        interval=interval,
        annualization_note=annualization_note,
    )


@dataclass
class ExperimentResult:
    """Result of a single deterministic experiment run.

    Combines the experiment spec with execution outcomes.
    Honest summary: what ran, what it saw, what it emitted.

    Attributes:
        spec: The ExperimentSpec describing the experiment setup.
        receipt_path: Path to the produced receipt JSON file.
        receipt_digest: SHA256 digest of the receipt file.
        bar_count: Number of bars processed.
        signal_count: Number of signals emitted.
        first_timestamp: First bar timestamp.
        last_timestamp: Last bar timestamp.
        long_count: Number of long signals (if strategy emits direction).
        short_count: Number of short signals (if strategy emits direction).
        flat_count: Number of flat/neutral transitions (if applicable).
        engine_version: Version string of the QuantBot engine.
    """

    spec: ExperimentSpec
    receipt_path: Path
    result_path: Path
    receipt_digest: str
    bar_count: int
    signal_count: int
    first_timestamp: str
    last_timestamp: str
    long_count: int = 0
    short_count: int = 0
    flat_count: int = 0
    engine_version: str = ""
    gate_verdict: Optional[GateVerdict] = None
    fee_bps: float = 0.0
    slippage_bps: float = 0.0
    economics_summary: Optional[EconomicsSummary] = None
    return_summary: Optional[ReturnSummary] = None
    return_series: Optional[ReturnSeries] = None
    inference_summary: Optional[InferenceSummary] = None

    def _gate_verdict_to_dict(self) -> dict[str, Any]:
        """Serialize gate_verdict to dict, or None if not set."""
        if self.gate_verdict is None:
            return None
        return {
            "status": self.gate_verdict.status,
            "reasons": self.gate_verdict.reasons,
            "checked": self.gate_verdict.checked,
        }

    def _economics_summary_to_dict(self) -> dict[str, Any] | None:
        """Serialize economics_summary to dict, or None if not set."""
        if self.economics_summary is None:
            return None
        return self.economics_summary.to_dict()

    def _return_summary_to_dict(self) -> dict[str, Any] | None:
        """Serialize return_summary to dict, or None if not set."""
        if self.return_summary is None:
            return None
        return self.return_summary.to_dict()

    def _return_series_to_dict(self) -> dict[str, Any] | None:
        """Serialize return_series to dict, or None if not set."""
        if self.return_series is None:
            return None
        return self.return_series.to_dict()

    def _inference_summary_to_dict(self) -> dict[str, Any] | None:
        """Serialize inference_summary to dict, or None if not set."""
        if self.inference_summary is None:
            return None
        return self.inference_summary.to_dict()

    def to_dict(self) -> dict[str, Any]:
        """Serialize result to dict."""
        d = {
            "experiment_name": self.spec.experiment_name,
            "strategy_name": self.spec.strategy_name,
            "strategy_params": self.spec.strategy_params,
            "fixture_name": self.spec.fixture_name,
            "family_id": self.spec.family_id,
            "variant_id": self.spec.variant_id,
            "trial_count": self.spec.trial_count,
            "engine_version": self.engine_version,
            "receipt_digest": self.receipt_digest,
            "bar_count": self.bar_count,
            "signal_count": self.signal_count,
            "first_timestamp": self.first_timestamp,
            "last_timestamp": self.last_timestamp,
            "long_count": self.long_count,
            "short_count": self.short_count,
            "flat_count": self.flat_count,
            "gate_verdict": self._gate_verdict_to_dict(),
            "fee_bps": self.fee_bps,
            "slippage_bps": self.slippage_bps,
            "economics_summary": self._economics_summary_to_dict(),
            "return_summary": self._return_summary_to_dict(),
            "return_series": self._return_series_to_dict(),
            "inference_summary": self._inference_summary_to_dict(),
        }
        return d

    def to_json(self) -> str:
        """Serialize result to deterministic canonical JSON string."""
        return canonical_json_dumps(self.to_dict())

    def write_json(self, path: Path) -> None:
        """Write result as deterministic JSON to disk."""
        path.write_text(self.to_json(), encoding="utf-8")


@dataclass
class WalkForwardSplitResult:
    """Summary of a single walk-forward split's execution."""

    split_index: int
    train_bar_count: int
    test_bar_count: int
    signal_count: int
    long_count: int
    short_count: int
    flat_count: int
    receipt_path: str | None  # None if no receipt written
    artifact_path: str | None
    first_timestamp: str = ""
    last_timestamp: str = ""
    economics_summary: Optional[EconomicsSummary] = None
    return_summary: Optional[ReturnSummary] = None
    return_series: Optional[ReturnSeries] = None
    inference_summary: Optional[InferenceSummary] = None


@dataclass
class WalkForwardExperimentResult:
    """Summary of a walk-forward experiment across multiple splits."""

    experiment_name: str
    split_count: int
    splits: list[WalkForwardSplitResult]  # per-split summaries
    total_bar_count: int
    total_signal_count: int
    strategy_name: str = ""
    strategy_params: dict = None
    fixture_name: str = ""
    family_id: str = ""
    variant_id: str = ""
    trial_count: int = 1
    engine_version: str = ""
    gate_verdict: Optional[GateVerdict] = None
    fee_bps: float = 0.0
    slippage_bps: float = 0.0
    economics_summary: Optional[EconomicsSummary] = None
    return_summary: Optional[ReturnSummary] = None
    return_series: Optional[ReturnSeries] = None
    inference_summary: Optional[InferenceSummary] = None

    def __post_init__(self) -> None:
        if self.strategy_params is None:
            self.strategy_params = {}

    def _gate_verdict_to_dict(self) -> dict[str, Any]:
        """Serialize gate_verdict to dict, or None if not set."""
        if self.gate_verdict is None:
            return None
        return {
            "status": self.gate_verdict.status,
            "reasons": self.gate_verdict.reasons,
            "checked": self.gate_verdict.checked,
        }

    def _economics_summary_to_dict(self) -> dict[str, Any] | None:
        """Serialize economics_summary to dict, or None if not set."""
        if self.economics_summary is None:
            return None
        return self.economics_summary.to_dict()

    def _return_summary_to_dict(self) -> dict[str, Any] | None:
        """Serialize return_summary to dict, or None if not set."""
        if self.return_summary is None:
            return None
        return self.return_summary.to_dict()

    def _return_series_to_dict(self) -> dict[str, Any] | None:
        """Serialize return_series to dict, or None if not set."""
        if self.return_series is None:
            return None
        return self.return_series.to_dict()

    def _inference_summary_to_dict(self) -> dict[str, Any] | None:
        """Serialize inference_summary to dict, or None if not set."""
        if self.inference_summary is None:
            return None
        return self.inference_summary.to_dict()

    def aggregate_inference_summary(self) -> InferenceSummary | None:
        """Aggregate inference summaries from all splits.

        Computes aggregate statistics by concatenating all split net_returns
        series and recomputing statistics. This preserves the semantics of
        computing from a single combined series rather than averaging means.

        Returns:
            Aggregated InferenceSummary, or None if no splits have return_series.
        """
        all_gross_returns: list[float] = []
        all_net_returns: list[float] = []
        interval = "unknown"
        has_series = False

        for split in self.splits:
            if split.return_series is not None:
                has_series = True
                all_gross_returns.extend(split.return_series.gross_returns)
                all_net_returns.extend(split.return_series.net_returns)
                if split.return_series.interval != "unknown":
                    interval = split.return_series.interval

        if not has_series:
            return None

        # Build a combined ReturnSeries and compute
        combined = ReturnSeries(
            gross_returns=all_gross_returns,
            net_returns=all_net_returns,
            bar_timestamps=[],  # Not needed for summary stats
            interval=interval,
        )
        return compute_inference_summary(combined)

    def aggregate_economics_summary(self) -> EconomicsSummary | None:
        """Aggregate economics summaries from all splits.

        Sums entry_count, exit_count, flip_count, cost_side_count.
        Uses fee_bps and slippage_bps from the first split that has them.
        Recomputes assumed_total_cost_bps from summed values.

        Returns:
            Aggregated EconomicsSummary, or None if no splits have economics data.
        """
        total_cost_side = 0
        total_entry = 0
        total_exit = 0
        total_flip = 0
        fee_bps = 0.0
        slippage_bps = 0.0
        has_economics = False

        for split in self.splits:
            if split.economics_summary is not None:
                has_economics = True
                total_cost_side += split.economics_summary.cost_side_count
                total_entry += split.economics_summary.entry_count
                total_exit += split.economics_summary.exit_count
                total_flip += split.economics_summary.flip_count
                if fee_bps == 0.0 and split.economics_summary.fee_bps > 0:
                    fee_bps = split.economics_summary.fee_bps
                if slippage_bps == 0.0 and split.economics_summary.slippage_bps > 0:
                    slippage_bps = split.economics_summary.slippage_bps

        if not has_economics:
            return None

        assumed_total = total_cost_side * (fee_bps + slippage_bps)

        return EconomicsSummary(
            cost_side_count=total_cost_side,
            entry_count=total_entry,
            exit_count=total_exit,
            flip_count=total_flip,
            fee_bps=fee_bps,
            slippage_bps=slippage_bps,
            assumed_total_cost_bps=assumed_total,
        )

    def aggregate_return_summary(self) -> ReturnSummary | None:
        """Aggregate return summaries from all splits.

        Sums gross_return_total, net_return_total, cost_deduction_total.
        Sums bars_held, winning_bars, losing_bars.

        Returns:
            Aggregated ReturnSummary, or None if no splits have return data.
        """
        total_gross = 0.0
        total_net = 0.0
        total_cost = 0.0
        total_bars_held = 0
        total_winning = 0
        total_losing = 0
        has_returns = False

        for split in self.splits:
            if split.return_summary is not None:
                has_returns = True
                total_gross += split.return_summary.gross_return_total
                total_net += split.return_summary.net_return_total
                total_cost += split.return_summary.cost_deduction_total
                total_bars_held += split.return_summary.bars_held
                total_winning += split.return_summary.winning_bars
                total_losing += split.return_summary.losing_bars

        if not has_returns:
            return None

        return ReturnSummary(
            gross_return_total=total_gross,
            net_return_total=total_net,
            cost_deduction_total=total_cost,
            bars_held=total_bars_held,
            winning_bars=total_winning,
            losing_bars=total_losing,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to deterministic dict for canonical JSON output."""
        # Aggregate signal counts across all splits
        aggregate_signal_count = sum(s.signal_count for s in self.splits)
        aggregate_long_count = sum(s.long_count for s in self.splits)
        aggregate_short_count = sum(s.short_count for s in self.splits)
        aggregate_flat_count = sum(s.flat_count for s in self.splits)

        # Find earliest and latest timestamps across all splits
        first_timestamp = ""
        last_timestamp = ""
        for split in self.splits:
            if split.first_timestamp:
                if not first_timestamp or split.first_timestamp < first_timestamp:
                    first_timestamp = split.first_timestamp
                if not last_timestamp or split.last_timestamp > last_timestamp:
                    last_timestamp = split.last_timestamp

        split_results = [
            {
                "split_index": s.split_index,
                "test_bar_count": s.test_bar_count,
                "train_bar_count": s.train_bar_count,
                "signal_count": s.signal_count,
                "long_count": s.long_count,
                "short_count": s.short_count,
                "flat_count": s.flat_count,
                "first_timestamp": s.first_timestamp,
                "last_timestamp": s.last_timestamp,
                "economics_summary": (
                    s.economics_summary.to_dict() if s.economics_summary else None
                ),
                "return_summary": (
                    s.return_summary.to_dict() if s.return_summary else None
                ),
                "return_series": (
                    s.return_series.to_dict() if s.return_series else None
                ),
                "inference_summary": (
                    s.inference_summary.to_dict() if s.inference_summary else None
                ),
            }
            for s in self.splits
        ]

        return {
            "experiment_name": self.experiment_name,
            "strategy_name": self.strategy_name,
            "strategy_params": self.strategy_params,
            "fixture_name": self.fixture_name,
            "family_id": self.family_id,
            "variant_id": self.variant_id,
            "trial_count": self.trial_count,
            "engine_version": self.engine_version,
            "split_count": self.split_count,
            "aggregate_signal_count": aggregate_signal_count,
            "aggregate_long_count": aggregate_long_count,
            "aggregate_short_count": aggregate_short_count,
            "aggregate_flat_count": aggregate_flat_count,
            "first_timestamp": first_timestamp,
            "last_timestamp": last_timestamp,
            "split_results": split_results,
            "gate_verdict": self._gate_verdict_to_dict(),
            "fee_bps": self.fee_bps,
            "slippage_bps": self.slippage_bps,
            "economics_summary": self._economics_summary_to_dict(),
            "return_summary": self._return_summary_to_dict(),
            "return_series": self._return_series_to_dict(),
            "inference_summary": self._inference_summary_to_dict(),
        }

    def to_json(self) -> str:
        """Serialize to deterministic canonical JSON string."""
        return canonical_json_dumps(self.to_dict())

    def write_json(self, path: Path) -> None:
        """Write result as deterministic JSON to disk."""
        path.write_text(self.to_json(), encoding="utf-8")
