#!/usr/bin/env bash
# qnty-paper-pnl-init.sh - Write the write-once paper_config.json for paper_pnl_v1.
# Strictly additive. Does NOT place orders. Does NOT touch the observer.
# Refuses to overwrite an existing config unless --force is passed.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Activate venv if present (VM path); harmless to skip on dev boxes.
if [ -f /srv/qnty/venv/bin/activate ]; then
    # shellcheck disable=SC1091
    source /srv/qnty/venv/bin/activate
fi

cd "$REPO_DIR"

# All flags pass through to the python entrypoint, e.g.:
#   --forward-start-ts 2026-06-05T00:00:00 [--notional-usd 1000] [--force]
exec python -m quantbot.paper.config "$@"
