#!/usr/bin/env bash
# Fix the local Radiance build's source_corr dropping the ies2rad brightdata A1 multiplier
# (electric IES luminaires under-emit ~14x). Appends explicit corr/flatcorr overrides to
# the system source.cal. Idempotent (skips if already applied). Run with sudo.
#
#   sudo bash scripts/live_validation_phase2/apply_source_cal_patch.sh
#
# Revert: sudo cp /usr/local/radiance/lib/source.cal.hclbak /usr/local/radiance/lib/source.cal
set -euo pipefail
SRC="${RADIANCE_SOURCE_CAL:-/usr/local/radiance/lib/source.cal}"
HERE="$(cd "$(dirname "$0")" && pwd)"
APPEND="$HERE/source_cal_A1_fix.append"

[ -f "$SRC" ] || { echo "source.cal not found at $SRC"; exit 1; }
if grep -q "hcl-mcp patch 2026-07-18" "$SRC"; then
  echo "Already patched ($SRC) — nothing to do."; exit 0
fi
cp -n "$SRC" "$SRC.hclbak" && echo "Backed up: $SRC.hclbak"
cat "$APPEND" >> "$SRC"
echo "Patched: $SRC"
echo "Verify: re-run mcp__hcl-mcp__run_grid with an electric_lights payload — under-fixture lux should be ~10-15x higher."
