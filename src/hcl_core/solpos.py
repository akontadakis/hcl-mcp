"""Solar geometry for the spectral pipeline (pure-Python, stdlib only).

Extends the existing Cooper-1969 `weather.solar_zenith` lineage into a full SolarGeometry:
zenith (identical to weather.solar_zenith), azimuth, Kasten-Young air mass, the NREL/Spencer
earth-radius-vector correction, and day-of-year. DAYSIM site convention throughout:
latitude north-positive; longitude WEST-positive; time_zone = standard meridian deg = -15*UTC.
"""
import math
from dataclasses import dataclass

from hcl_core.weather import _day_of_year


@dataclass(frozen=True)
class SolarGeometry:
    zenith_deg: float
    azimuth_deg: float          # 0=N, 90=E, 180=S, 270=W (SPECTRL2 aspect convention)
    air_mass: float             # Kasten-Young 1989 relative air mass; inf below horizon
    earth_radius_vector: float  # NREL/Spencer correction factor; multiply ETR by this
    day_of_year: int


def air_mass(zenith_deg):
    """Kasten-Young (1989) relative optical air mass. inf when the sun is at/below the horizon."""
    if zenith_deg >= 90.0:
        return float("inf")
    zr = math.radians(zenith_deg)
    return 1.0 / (math.cos(zr) + 0.50572 * (96.07995 - zenith_deg) ** -1.6364)


def earth_radius_vector(day_of_year):
    """NREL solpos / Spencer (1971) earth-radius-vector correction factor (=(r0/r)^2), ~0.966..1.034.

    Apply multiplicatively to the extraterrestrial spectrum (ETR * erv) to correct for the
    sun-earth distance on this day. Max near perihelion (early Jan), min near aphelion (early Jul).
    """
    dayang = 2.0 * math.pi * (day_of_year - 1) / 365.0
    return (1.000110
            + 0.034221 * math.cos(dayang) + 0.001280 * math.sin(dayang)
            + 0.000719 * math.cos(2 * dayang) + 0.000077 * math.sin(2 * dayang))


def compute(*, month, day, hour, latitude, longitude, time_zone):
    """Full SolarGeometry from date/clock-hour + DAYSIM-convention site location.

    Zenith is computed identically to weather.solar_zenith (Cooper 1969 declination + EoT +
    hour-angle). Azimuth is measured clockwise from North (N=0, E=90, S=180, W=270).
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
    zenith_deg = math.degrees(math.acos(cos_zenith))

    # Azimuth from South (+toward West), then rotate to clockwise-from-North.
    az_from_south = math.atan2(
        math.sin(hour_angle),
        math.cos(hour_angle) * math.sin(lat) - math.tan(decl) * math.cos(lat),
    )
    azimuth_deg = (math.degrees(az_from_south) + 180.0) % 360.0

    return SolarGeometry(
        zenith_deg=zenith_deg,
        azimuth_deg=azimuth_deg,
        air_mass=air_mass(zenith_deg),
        earth_radius_vector=earth_radius_vector(doy),
        day_of_year=doy,
    )
