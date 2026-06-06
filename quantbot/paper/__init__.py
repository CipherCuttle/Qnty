"""Paper PnL accounting layer (paper_pnl_v1).

Strictly additive: consumes the read-only shadow observer output and writes a
deterministic simulated ledger (fills -> positions -> trades -> equity -> funding).

This is a SIMULATION. Paper PnL is not live trading and does not prove real-money
profitability. See docs/paper_pnl_v1_schema.md for the full contract.
"""

import os
from pathlib import Path

SCHEMA_VERSION = 1
PAPER_ENGINE_VERSION = "0.2.0"

# This layer is a FIXED-NOTIONAL ACTIVE-SYMBOL baseline, NOT a faithful reproduction of
# the Package V2 vol-normalized portfolio. See docs/paper_pnl_v1_schema.md section 8.
BASELINE_LABEL = "fixed_notional_active_symbols_paper_v1"

# What this baseline deliberately does NOT reproduce from Package V2 (the adapter loss).
BASELINE_NOT_REPRODUCED = (
    "vol-normalized weights are not reproduced; portfolio heat/weights are not used for "
    "sizing; a fixed $notional per active symbol is substituted; no compounding; no "
    "shorting. This only tests the active-symbol fixed-notional baseline — a green paper "
    "PnL does NOT validate the V2 vol-normalized edge."
)


def forward_obs_dir() -> Path:
    """Read-only shadow observer output directory.

    Override with QNTY_FORWARD_OBS_DIR (used for tests / dev boxes where
    /srv/qnty does not exist).
    """
    return Path(os.environ.get("QNTY_FORWARD_OBS_DIR", "/srv/qnty/output/forward_obs_v1"))


def paper_output_dir() -> Path:
    """Forward paper ledger output directory.

    Override with QNTY_PAPER_OUTPUT_DIR.
    """
    return Path(os.environ.get("QNTY_PAPER_OUTPUT_DIR", "/srv/qnty/output/paper_pnl_v1"))
