#!/usr/bin/env bash
# Live physical_sky validation runner. Sets engine env then runs the Python driver.
set -euo pipefail
export HCL_DAYSIM_BIN="${HCL_DAYSIM_BIN:-/usr/local/daysim/bin}"
export PATH="/usr/local/radiance/bin:$PATH"
export RAYPATH=".:/usr/local/radiance/lib:${RAYPATH:-}"
cd "$(dirname "$0")"
python3 run_physical_sky_live.py "$@"
