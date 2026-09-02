"""Read site location from an EPW and convert it to the DAYSIM/.wea convention.

This reproduces, in Python, the exact transform `epw2wea` applies to the EPW `LOCATION`
line (Daysim master `src/cv/epw2wea.c:54-77`). The Lark 2.0 component derived the Daysim
`.hea` site block by reading these values back from the epw2wea-generated `.wea`; we derive
them straight from the EPW so the same correct, weather-file-consistent values are used —
the caller never has to know the DAYSIM sign/units conventions. Explicit values still win
(see `generate_subhourly_wea`); this is the safe default that prevents a silent lat-0/long-0
sub-hourly run.

It lives in `hcl_core` rather than in the Daysim adapter because that convention is the
core's own site convention: `hcl_core.solpos.compute` and `hcl_core.weather.solar_zenith`
both consume west-positive longitude and a standard-meridian time zone, and the spectral
pipeline needs this parse with no engine installed. `hcl_daysim.epw` re-exports it, so the
`.wea`/`.hea` writers keep reading it from the module next to them.

epw2wea's conversion (verified against source):
  latitude:       EPW latitude, verbatim (north-positive)
  longitude:      -1 * EPW longitude  (EPW east-positive -> .wea west-positive), 2 dp
  time_zone:      -15 * trunc(EPW timezone hours)  -> degrees  (C `atoi` truncates toward zero)
  site_elevation: EPW elevation, verbatim (metres)
"""

import warnings

# EPW LOCATION line: LOCATION,City,State,Country,Source,WMO,latitude,longitude,timezone,elevation
_LAT, _LON, _TZ, _ELEV = 6, 7, 8, 9

def parse_epw_location(epw_path):
    """Return {latitude, longitude, time_zone, site_elevation} in DAYSIM/.wea convention.

    Returns None if the file can't be read or the first line isn't a parseable LOCATION line,
    so callers can fall back to explicit values. longitude/time_zone match what epw2wea writes
    (west-positive longitude rounded to 2 dp; time_zone = -15 x truncated UTC offset in degrees).
    """
    try:
        with open(epw_path) as fh:
            first = fh.readline()
    except (OSError, TypeError):   # TypeError: epw_path is None / not a path
        return None
    parts = first.split(",")
    if len(parts) <= _ELEV or parts[0].strip().upper() != "LOCATION":
        return None
    try:
        tz_raw = float(parts[_TZ])
        tz_int = int(tz_raw)   # truncate toward zero, matching epw2wea's atoi(time_zone)
        truncated = tz_raw != tz_int
        if truncated:
            warnings.warn(
                f"EPW time zone {tz_raw} is not a whole hour; truncating to {tz_int} for epw2wea "
                "parity (DAYSIM .wea uses integer offsets). Pass an explicit time_zone to override.",
                stacklevel=2)
        return {
            "latitude": float(parts[_LAT]),
            "longitude": round(-1.0 * float(parts[_LON]), 2),
            "time_zone": int(-15 * tz_int),
            "site_elevation": float(parts[_ELEV]),
            "tz_truncated": truncated,
        }
    except ValueError:
        return None
