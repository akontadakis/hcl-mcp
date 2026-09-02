"""Weather + analysis-period utilities (pure-Python ports of Lark's wea/period components)."""
import datetime
import math

def import_wea(path):
    """Parse a Radiance .wea: skip 6 header lines; return month/day/hour/DNI/DHI as string lists."""
    with open(path) as fh:
        lines = fh.readlines()[6:]
    months, days, hours, dni, dhi = [], [], [], [], []
    for line in lines:
        t = line.split()
        if len(t) < 5:
            continue
        months.append(t[0]); days.append(t[1]); hours.append(t[2]); dni.append(t[3]); dhi.append(t[4])
    return {"months": months, "days": days, "hours": hours, "DNI": dni, "DHI": dhi}

def analysis_period(from_mdh, to_mdh):
    """(month,day,hour) start/end -> [[m,d,h],[m,d,h]] (Lark analysisPeriod shape)."""
    return [list(from_mdh), list(to_mdh)]

def _range1(a, b):
    return range(a, b + 1)

def decompose(period, timestep_min=60):
    """Expand a period to months/days/hours/HOY/HOYround/wea_lines (verbatim Lark logic; key renamed to snake_case per spec §5.11).

    Faithful port — the loop nests month×day×hour as a Cartesian product, so the day
    window (d0..d1) and hour window (h0..h1) apply uniformly to every month in m0..m1.
    This mirrors Lark's analysisPeriod semantics: it expands a fixed day/hour window
    repeated across months, NOT a continuous calendar span. Preconditions: timestep_min
    should divide 60 evenly (n = round(60/step)); the reference year is the non-leap 2010,
    which is why Feb 29 is among the skipped invalid days."""
    (m0, d0, h0), (m1, d1, h1) = period[0], period[1]
    step = timestep_min
    n = int(round(60 / step))
    dt0 = datetime.datetime(2010, 1, 1, 0, 0, 0)
    months, days, hours, HOY, HOYround = [], [], [], [], []
    for i in _range1(m0, m1):
        for j in _range1(d0, d1):
            for k in _range1(h0, h1):
                for l in range(n):
                    if i == 2 and j in (29, 30, 31):
                        continue
                    if i in (4, 6, 9, 11) and j == 31:
                        continue
                    minute = (l * step) / 60.0
                    months.append(i); days.append(j); hours.append(k + minute if minute else k)
                    # datetime rejects hour 24; the .wea/Daysim 1-24 convention means hour 24 of
                    # day D == hour 0 of day D+1. Roll over via timedelta so a window reaching
                    # midnight expands instead of raising ValueError("hour must be in 0..23").
                    day_off, hh = (1, 0) if k == 24 else (0, k)
                    dt = datetime.datetime(2010, i, j, hh, int(l * step), 0) + datetime.timedelta(days=day_off)
                    dtr = datetime.datetime(2010, i, j, hh, 0, 0) + datetime.timedelta(days=day_off)
                    HOY.append((dt - dt0).days * 24 + (dt - dt0).seconds / 3600)
                    HOYround.append((dtr - dt0).days * 24 + (dtr - dt0).seconds / 3600)
    wea_lines = [h * (60 / step) + 7 for h in HOY]  # spec §5.11 key: wea_lines (snake_case)
    return {"months": months, "days": days, "hours": hours, "HOY": HOY,
            "HOYround": HOYround, "wea_lines": [int(round(w)) for w in wea_lines]}

def subset_wea(path, line_numbers):
    """Return a .wea string with the 6 header lines + only the given 1-based data line numbers."""
    with open(path) as fh:
        all_lines = [ln.rstrip("\n") for ln in fh.readlines()]
    header = all_lines[:6]
    # wea_lines are computed from decompose()'s timestep_min, which must match THIS file's actual
    # resolution. If it doesn't, line numbers overrun the file; fail loudly rather than silently
    # dropping rows (which would emit a wrong-timestamp subset and corrupt downstream runs).
    out_of_range = [n for n in line_numbers if not (6 < n <= len(all_lines))]
    if out_of_range:
        raise ValueError(
            f"subset_wea: {len(out_of_range)} requested line number(s) fall outside the "
            f"{len(all_lines) - 6} data rows of {path!r}; the wea_lines were likely computed with "
            f"a timestep_min that does not match this file's resolution.")
    keep = [all_lines[n - 1] for n in line_numbers]
    return "\n".join(header + keep) + "\n"

# Day-of-year for the 2010 reference year decompose() uses (non-leap), so month/day map 1:1.
_MONTH_CUM = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)

def _day_of_year(month, day):
    """1-based day-of-year in the non-leap 2010 reference year (matches decompose())."""
    return _MONTH_CUM[month - 1] + day

def solar_zenith(*, month, day, hour, latitude, longitude, time_zone):
    """Solar zenith angle (degrees) from date/clock-hour and DAYSIM-convention site location.

    Pure-Python, no deps. Cooper (1969) declination + equation-of-time + hour-angle altitude.
    Convention (matches hcl_core.epw_location / the .wea site block):
      latitude  north-positive deg; longitude WEST-positive deg; time_zone standard meridian deg
      (WEST-positive, = -15 x UTC offset); hour local standard clock hour (0..24, may be fractional).
    Returns a zenith in [0, 180]; >90 means the sun is below the horizon.
    """
    doy = _day_of_year(month, day)
    decl = math.radians(23.45 * math.sin(math.radians(360.0 * (284 + doy) / 365.0)))
    b = math.radians(360.0 * (doy - 81) / 364.0)
    eot = 9.87 * math.sin(2 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)
    solar_time = hour + (4.0 * (time_zone - longitude) + eot) / 60.0
    hour_angle = math.radians(15.0 * (solar_time - 12.0))
    lat = math.radians(latitude)
    cos_zenith = (math.sin(lat) * math.sin(decl)
                  + math.cos(lat) * math.cos(decl) * math.cos(hour_angle))
    cos_zenith = max(-1.0, min(1.0, cos_zenith))
    return math.degrees(math.acos(cos_zenith))
