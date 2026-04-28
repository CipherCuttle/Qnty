#!/usr/bin/env bash
set -euo pipefail

python - <<'PY'
import quantbot
import numpy
import pandas
import requests
print("IMPORT_OK")
PY

python -m pytest tests/test_determinism_smoke.py -q
