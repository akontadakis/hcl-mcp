"""Parse the hourly EPW columns the rest of hcl-mcp ignores (only the LOCATION header is read today).

0-based comma indices (the A1 data-source-flags STRING sits at index 5, which is the classic
off-by-one trap): dry-bulb 6, dew-point 7, RH 8, pressure 9 (Pa), GHI 13, DNI 14, DHI 15,
total-sky-cover 22, opaque-sky-cover 23, precipitable-water 28, AOD 29, albedo 32.
EPW has 8 header lines before the hourly data. Missing-value sentinels map to None.

NB: `hour` is the raw EPW hour-ENDING value (1-24); converting it to a mid-interval local clock
hour for solpos is the Phase 5 orchestrator's (`spectral_pipeline`) responsibility, not done here.
"""
import logging

logger = logging.getLogger(__name__)

_HEADER_LINES = 8

# field key -> (comma index, missing-sentinel). Sentinels per the EPW data dictionary.
_FIELDS = {
    "dry_bulb_c": (6, 99.9),
    "dew_point_c": (7, 99.9),
    "rh_pct": (8, 999.0),
    "pressure_pa": (9, 999999.0),
    "ghi": (13, 9999.0),
    "dni": (14, 9999.0),
    "dhi": (15, 9999.0),
    "total_sky_cover": (22, 99.0),
    "opaque_sky_cover": (23, 99.0),
    "precip_water_mm": (28, 999.0),
    "aod": (29, 0.999),
    "albedo": (32, 999.0),
}


# Physical lower bound on broadband shortwave ground albedo, below which a value is a de-facto
# "no data" marker rather than a measurement. IWEC and TMY2 files write a literal 0.000 in the
# albedo column for every hour instead of the data dictionary's 999.0 sentinel (4 of the 11 EPWs
# bundled with this repo do exactly that, Athens among them). Nothing outdoors is a perfect
# absorber: fresh asphalt is ~0.04 and calm deep water at high sun ~0.03, so a value at or below
# this floor cannot be real. Accepting 0.0 as data silently zeroed the whole ground-reflected term
# AND stamped it `source: "epw"`, claiming an instrument had measured it.
_ALBEDO_MIN_PHYSICAL = 0.01

# field key -> validity predicate applied AFTER the sentinel test. A False verdict means "missing",
# so `atmosphere.derive` falls back to its documented default and reports source="default".
_VALID = {
    "albedo": lambda v: v >= _ALBEDO_MIN_PHYSICAL,
}


def _num(parts, idx, sentinel, valid=None):
    """Float at parts[idx], or None if absent/unparseable/the missing sentinel/non-physical."""
    if idx >= len(parts):
        return None
    try:
        v = float(parts[idx])
    except ValueError:
        return None
    if v == sentinel:
        return None
    return None if (valid is not None and not valid(v)) else v


def parse_epw_hourly_diagnostics(path):
    """Parse like `parse_epw_hourly`, but also return why/how many rows were dropped.

    Returns `(rows, diagnostics)` where diagnostics is
    `{"kept": int, "dropped": int, "reasons": {"short_row": int, "bad_date": int}}`.
    Each dropped row is logged with its 1-based data-line number and reason, and a one-line
    summary is logged when any rows are dropped — satisfying the spec §13 / methodology §14
    "skipped with a logged reason" + "a run reports how many timesteps were dropped" contract.
    """
    with open(path) as fh:
        lines = fh.readlines()[_HEADER_LINES:]
    rows = []
    reasons = {"short_row": 0, "bad_date": 0}
    for n, line in enumerate(lines, start=1):
        parts = line.strip().split(",")
        if len(parts) < 16:  # need at least through DHI to be a usable radiation row
            if line.strip():  # don't count trailing blank lines as drops
                reasons["short_row"] += 1
                logger.warning("epw row %d dropped: short_row (%d < 16 fields)", n, len(parts))
            continue
        try:
            month, day, hour = int(parts[1]), int(parts[2]), int(parts[3])
        except (ValueError, IndexError):
            reasons["bad_date"] += 1
            logger.warning("epw row %d dropped: bad_date (%r)", n, parts[1:4])
            continue
        row: dict[str, float | None] = {"month": month, "day": day, "hour": hour}
        for key, (idx, sentinel) in _FIELDS.items():
            row[key] = _num(parts, idx, sentinel, _VALID.get(key))
        rows.append(row)
    dropped = reasons["short_row"] + reasons["bad_date"]
    if dropped:
        logger.warning("epw parse: kept %d rows, dropped %d (%s)", len(rows), dropped, reasons)
    return rows, {"kept": len(rows), "dropped": dropped, "reasons": reasons}


def parse_epw_hourly(path):
    """Return a list of per-row dicts. Skips the 8 header lines and any short/blank rows.

    Backward-compatible thin wrapper over `parse_epw_hourly_diagnostics` (drops are logged;
    use that function directly for the programmatic drop count).
    """
    return parse_epw_hourly_diagnostics(path)[0]


def row_for(rows, month, day, hour):
    """First row matching (month, day, hour), or None."""
    for r in rows:
        if r["month"] == month and r["day"] == day and r["hour"] == hour:
            return r
    return None
