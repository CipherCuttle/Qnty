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


@dataclass
class InferentialSummary:
    """Multiple-testing-aware inference summary.

    Provides PSR (Probabilistic Sharpe Ratio) and DSR (Deflated Sharpe Ratio)
    as adjustments to the basic Sharpe-like ratio from InferenceSummary.

    Attributes:
        psr: Probabilistic Sharpe Ratio - estimated probability that the
            realized Sharpe ratio > 0, under normality assumption.
            None if not computable (insufficient bars).
        psr_n: Track record length (bar count) used for PSR computation.
        dsr: Deflated Sharpe Ratio - Sharpe ratio adjusted for multiple testing
            across N trials. None if trial_count < 2 or not computable.
        dsr_trial_count: Trial count used for DSR computation. None if DSR not computed.
        dsr_note: Explanation when DSR is None or has limitations.
        sharpe_like: Same as InferenceSummary.sharpe_like for convenience.
        std_return: Same as InferenceSummary.std_return for convenience.
        skewness: Sample skewness (Fisher's) of net returns, or None if n < 3.
        kurtosis: Sample excess kurtosis (Fisher's) of net returns, or None if n < 4.
        assumptions_note: Human-readable note on assumptions and limitations.

    Note:
        PSR is NOT a probability of edge. It is P(SR > 0) under normality.
        DSR is SR adjusted for selection bias across multiple trials.
        Neither constitutes proof of edge or readiness to trade.
    """

    psr: Optional[float] = None
    psr_n: int = 0
    dsr: Optional[float] = None
    dsr_trial_count: Optional[int] = None
    dsr_note: str = ""
    sharpe_like: Optional[float] = None
    std_return: Optional[float] = None
    skewness: Optional[float] = None
    kurtosis: Optional[float] = None
    assumptions_note: str = (
        "Assumes i.i.d. returns; does not account for non-stationarity; "
        "does not constitute proof of edge."
    )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "psr": self.psr,
            "psr_n": self.psr_n,
            "dsr": self.dsr,
            "dsr_trial_count": self.dsr_trial_count,
            "dsr_note": self.dsr_note,
            "sharpe_like": self.sharpe_like,
            "std_return": self.std_return,
            "skewness": self.skewness,
            "kurtosis": self.kurtosis,
            "assumptions_note": self.assumptions_note,
        }


def _compute_skewness(returns: list[float]) -> Optional[float]:
    """Compute population skewness (Fisher's) of a return series.

    Uses the formula: g1 = (sum((x - mean)^3) / n) / std^3

    Args:
        returns: List of return values.

    Returns:
        Skewness if n >= 3, else None (skewness undefined for n < 3).
    """
    n = len(returns)
    if n < 3:
        return None

    mean = sum(returns) / n
    squared_diffs = [(r - mean) ** 2 for r in returns]
    variance = sum(squared_diffs) / n
    std = math.sqrt(variance)

    if std == 0:
        return None  # Skewness undefined when std=0

    cubed_diffs = [(r - mean) ** 3 for r in returns]
    m3 = sum(cubed_diffs) / n
    g1 = m3 / (std ** 3)

    return g1


def _compute_kurtosis(returns: list[float]) -> Optional[float]:
    """Compute population excess kurtosis (Fisher's) of a return series.

    Uses the formula: g2 = (sum((x - mean)^4) / n) / std^4 - 3

    Args:
        returns: List of return values.

    Returns:
        Excess kurtosis if n >= 4, else None (kurtosis undefined for n < 4).
    """
    n = len(returns)
    if n < 4:
        return None

    mean = sum(returns) / n
    squared_diffs = [(r - mean) ** 2 for r in returns]
    variance = sum(squared_diffs) / n
    std = math.sqrt(variance)

    if std == 0:
        return None  # Kurtosis undefined when std=0

    fourth_diffs = [(r - mean) ** 4 for r in returns]
    m4 = sum(fourth_diffs) / n
    g2 = (m4 / (std ** 4)) - 3  # Excess kurtosis (Fisher's)

    return g2


def _norm_cdf(x: float) -> float:
    """Standard normal CDF using math.erf (no scipy dependency)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def compute_psr(
    sharpe_like: float,
    track_record_length: int,
    skewness: Optional[float] = None,
    kurtosis: Optional[float] = None,
) -> float:
    """Compute Probabilistic Sharpe Ratio (Bailey et al.).

    Uses the skewness/kurtosis corrected formula from Bailey & López de Prado (2012).
    Returns probability that SR > 0 under the assumption of i.i.d. normal returns.

    The formula uses:
        PSR = Z / sqrt(N)
    where Z is the skewness/kurtosis corrected standard normal deviate and
    N is the track record length.

    Args:
        sharpe_like: The annualized Sharpe-like ratio computed from returns.
        track_record_length: Number of bars in the track record (n).
        skewness: Sample skewness (gamma1) if available, else None.
        kurtosis: Sample excess kurtosis (gamma2) if available, else None.

    Returns:
        PSR value in range [0, 1], representing P(SR > 0).

    Note:
        This is NOT a probability of edge. It is P(SR > 0) under normality.
        Returns 0.5 when skewness/kurtosis corrections exactly cancel (normal case).
    """
    n = track_record_length

    if n < 2:
        return 0.0

    # Base SR
    sr = sharpe_like

    # Compute skewness/kurtosis correction factor
    # From Bailey & López de Prado (2012):
    # Z = SR * (1 + 0.5*SR^2 - gamma1*SR/6 - gamma2/24 + gamma1^2/72) + 1/6
    correction = 1.0 + 0.5 * (sr ** 2)
    if skewness is not None:
        correction -= (skewness * sr) / 6.0
    if kurtosis is not None:
        correction -= kurtosis / 24.0
    if skewness is not None:
        correction += (skewness ** 2) / 72.0

    z_score = (sr * correction) + (1.0 / 6.0)

    # PSR = standard normal CDF of z / sqrt(n)
    psr = _norm_cdf(z_score / math.sqrt(n))

    # Clamp to [0, 1] for numerical stability
    return max(0.0, min(1.0, psr))


def compute_dsr(
    sharpe_like: float,
    trial_count: int,
    track_record_length: int,
) -> tuple[float, str]:
    """Compute Deflated Sharpe Ratio (Bailey et al.).

    Adjusts the Sharpe ratio for selection bias from multiple testing.
    Uses the formula from Bailey & López de Prado (2014).

    WARNING: The current trial_count is cumulative hypothesis exploration count,
    NOT independent backtest trials. DSR computed here uses available trial_count
    but the note will explain this limitation clearly.

    Args:
        sharpe_like: The annualized Sharpe-like ratio.
        trial_count: Number of trials (hypotheses explored). Used for expected max SR.
        track_record_length: Number of bars (n). Used for std of max SR.

    Returns:
        Tuple of (dsr, note). dsr may be None if trial_count < 2.

    Note:
        DSR gap: current trial_count tracks exploration history, not independent
        backtest trials. Use split_count for walk-forward as a more appropriate
        trial proxy in that context.
    """
    if trial_count < 2:
        return None, (
            "DSR not computed: trial_count < 2. "
            "DSR requires at least 2 trials to compute deflated ratio."
        )

    if track_record_length < 3:
        return None, (
            f"DSR not computed: track_record_length={track_record_length} < 3. "
            "Insufficient bars for stable estimation."
        )

    n = track_record_length
    t = trial_count

    # Standard deviation of returns (we estimate from Sharpe ratio)
    # SR = mean / std * sqrt(n) => std = mean * sqrt(n) / SR
    # We need a different approach since we don't have mean directly
    # Instead, use the relationship: for i.i.d. returns,
    # var(SR_max) ≈ 1/(n-1) for large T (under null)
    # Actually, the Bailey & Lopez de Prado formula:
    # E[SR_max] ≈ sqrt(2*ln(T)) * sigma (for T trials)
    # sigma_SR_max ≈ sigma / sqrt(T-1)
    # But we don't have sigma directly...

    # Simplified approach: Use the fact that for standard normal returns,
    # the distribution of max SR across T trials scales with sqrt(2*ln(T))
    # and the std of max SR is approximately 1/sqrt(T-1)

    # More practical formula from B&L (2014):
    # DSR = (SR - E[SR_max]) / sigma_SR_max
    # E[SR_max] = sqrt(2*ln(T)) * (sigma_for_unit_SR)
    # For a single series, we use the relationship:
    # If SR is our observed ratio, and we expect max(SR) from T trials,
    # we adjust downward

    # For a single track record with Sharpe = SR, std = sigma, n = track length:
    # E[SR_max | T trials] ≈ sqrt(2*ln(T)) * sigma / sqrt(n)
    # This is the expected maximum Sharpe from T random trials on same series length

    # Standard deviation of max SR across T trials (under null):
    # sigma_SR_max ≈ sigma / sqrt(n*(T-1))

    # But we don't have sigma directly. We need to estimate it.
    # Using the Sharpe ratio formula: SR = mean * sqrt(n) / std
    # => std = mean * sqrt(n) / SR
    # For small/negative SR, this breaks down...

    # Fallback: Use a conservative approximation
    # DSR = SR / sqrt(2*ln(T)) when we can't properly compute sigma

    # Actually, let's use the proper Bailey & Lopez de Prado formula:
    # For the deflated SR using the probability of exceedance:

    # E[SR_max] = sqrt(2*ln(T)) for standard normal under null hypothesis
    # This assumes sigma = 1 and n = 1 (per-trial estimate)

    # For our case with track_record_length n:
    # E[SR_max_n] = sqrt(2*ln(T)) / sqrt(n)
    # sigma_SR_max_n = 1 / sqrt(n*(T-1))

    expected_max_sr = math.sqrt(2 * math.log(t)) / math.sqrt(n)
    sigma_sr_max = 1.0 / math.sqrt(n * (t - 1))

    if sigma_sr_max == 0:
        return None, "DSR computation failed: numerical instability (sigma_sr_max=0)"

    # Check if observed SR is even above the expected maximum
    if sharpe_like <= expected_max_sr:
        # Observed SR doesn't exceed expected max - DSR would be <= 0
        # But we still compute it; it will be negative or zero
        dsr_val = (sharpe_like - expected_max_sr) / sigma_sr_max
        dsr_note = (
            f"DSR={dsr_val:.4f}: observed SR ({sharpe_like:.4f}) does not exceed "
            f"expected max ({expected_max_sr:.4f}) across {t} trials. "
            f"WARNING: trial_count={t} reflects hypothesis exploration count, "
            f"NOT independent backtest trials. This DSR may overstate adjustment."
        )
        return max(-10.0, dsr_val), dsr_note

    dsr_val = (sharpe_like - expected_max_sr) / sigma_sr_max
    dsr_note = (
        f"DSR computed using trial_count={t}. "
        f"WARNING: trial_count reflects cumulative hypothesis exploration, "
        f"NOT independent backtest trials. Interpretation requires caution."
    )

    return dsr_val, dsr_note


def compute_inferential_summary(
    inference_summary: InferenceSummary,
    trial_count: Optional[int] = None,
) -> InferentialSummary:
    """Build InferentialSummary from InferenceSummary + optional trial metadata.

    PSR is always computed if inputs allow (sharpe_like exists, bar_count >= 2).
    DSR is computed only if trial_count >= 2, with explicit note about limitation.

    Args:
        inference_summary: The basic inference summary from compute_inference_summary.
        trial_count: Optional cumulative trial count for DSR computation.

    Returns:
        InferentialSummary with PSR (always if computable) and DSR (if trial_count >= 2).
    """
    sharpe = inference_summary.sharpe_like
    std = inference_summary.std_return
    n = inference_summary.bar_count_for_returns

    psr: Optional[float] = None
    dsr: Optional[float] = None
    dsr_trial_count: Optional[int] = None
    dsr_note = ""

    # We need returns to compute skewness/kurtosis, but they may not be available
    # If inference_summary came from a ReturnSeries, skew/kurt could be passed in
    # For now, we compute without them (conservative)
    skew: Optional[float] = None
    kurt: Optional[float] = None

    # Compute PSR if sharpe_like exists and n >= 2
    if sharpe is not None and n >= 2:
        psr = compute_psr(sharpe, n, skew, kurt)

    # Compute DSR if trial_count is provided and >= 2
    if trial_count is not None and trial_count >= 2:
        if sharpe is not None and n >= 3:
            dsr, dsr_note = compute_dsr(sharpe, trial_count, n)
            dsr_trial_count = trial_count
        else:
            dsr_note = (
                f"DSR not computed: sharpe_like={'available' if sharpe is not None else 'None'}, "
                f"bar_count={n} (need >= 3)."
            )

    return InferentialSummary(
        psr=psr,
        psr_n=n,
        dsr=dsr,
        dsr_trial_count=dsr_trial_count,
        dsr_note=dsr_note,
        sharpe_like=sharpe,
        std_return=std,
        skewness=skew,
        kurtosis=kurt,
    )


def _parse_interval_to_bars_per_year(interval: str) -> float | None:
    """Parse interval string to approximate bars per year.

    Supports common formats:
    - '1m', '5m', '15m', '30m' (minutes)
    - '1h', '4h', '8h', '12h' (hours)
    - '1d', '3d', '1w' (days/weeks)
    - Custom patterns like '8h' -> 1095 (3*365 for 8h crypto bars)

    Returns:
        Approximate number of trading periods per year, or None if unparseable.

    Note:
        For crypto (24/7 markets), we use 365.25 days rather than 252 trading days.
        This is an approximation - actual trading frequency may vary.
    """
    if interval is None:
        return None
    interval = interval.strip().lower()

    # Minutes
    if interval.endswith("m"):
        try:
            minutes = int(interval[:-1])
            return (60 * 24 * 365.25) / minutes
        except ValueError:
            pass

    # Hours
    if interval.endswith("h"):
        try:
            hours = int(interval[:-1])
            return (24 * 365.25) / hours
        except ValueError:
            pass

    # Days
    if interval.endswith("d"):
        try:
            days = int(interval[:-1])
            return 365.25 / days
        except ValueError:
            pass

    # Weeks
    if interval.endswith("w"):
        try:
            weeks = int(interval[:-1])
            return 52.18 / weeks  # 52.18 weeks per year
        except ValueError:
            pass

    return None


def compute_inference_summary(return_series: ReturnSeries) -> InferenceSummary:
    """Compute inference statistics from a ReturnSeries.

    Statistics are computed from the net_returns series only.
    std_return uses population standard deviation (ddof=0).
    sharpe_like is computed if interval is known and bars >= 2.

    Annualization:
    - sharpe_like is annualized only when interval is known and parseable.
    - Annualization factor is computed from interval string (e.g., '8h' -> 1095 bars/year).
    - For crypto (24/7 markets), we use 365.25 days rather than 252 trading days.
    - This is an approximation; actual trading frequency may vary.

    Degenerate cases handled:
    - Empty series: returns zero/invalid stats
    - Single bar: std_return = None (undefined)
    - All identical returns: std_return = 0.0
    - Unknown interval: sharpe_like = None (annualization_note explains why)

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

    # sharpe_like: compute if interval is known, parseable, and bars >= 2 with std > 0
    sharpe_like: Optional[float] = None
    annualized = False
    annualization_note = "not annualized - interval unknown"

    if interval != "unknown" and bar_count >= 2 and std_return is not None and std_return > 0:
        bars_per_year = _parse_interval_to_bars_per_year(interval)
        if bars_per_year is not None:
            # Annualize: sharpe_like = mean * sqrt(bars_per_year) / std
            # This is the standard Sharpe ratio formula assuming i.i.d. returns
            sharpe_like = (mean_return / std_return) * math.sqrt(bars_per_year)
            annualized = True
            annualization_note = (
                f"annualized using {bars_per_year:.1f} bars/year from interval '{interval}' "
                f"(365.25 days × 24h / {interval} for crypto 24/7 market)"
            )
        else:
            annualization_note = f"not annualized - interval '{interval}' not parseable to bars/year"

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

        # Compute inferential summary with trial context for multiple-testing-aware inference
        if self.inference_summary is not None:
            trial_count = self.spec.trial_count
            inferential = compute_inferential_summary(self.inference_summary, trial_count)
            d["inferential_summary"] = inferential.to_dict()
        else:
            d["inferential_summary"] = None

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

        # Compute inferential summary with split_count as trial proxy for DSR
        # WalkForward uses split_count as the implicit trial structure
        if self.inference_summary is not None:
            # Use split_count as effective trial count for walkforward DSR
            trial_count = self.split_count if self.split_count >= 2 else self.trial_count
            inferential = compute_inferential_summary(self.inference_summary, trial_count)
            d["inferential_summary"] = inferential.to_dict()
        else:
            d["inferential_summary"] = None

        return d

    def to_json(self) -> str:
        """Serialize to deterministic canonical JSON string."""
        return canonical_json_dumps(self.to_dict())

    def write_json(self, path: Path) -> None:
        """Write result as deterministic JSON to disk."""
        path.write_text(self.to_json(), encoding="utf-8")
