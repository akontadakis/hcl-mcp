"""EPW → canonical SpectralSkyRecord orchestration (point-in-time + annual).

Chains Phase 1–3: parse the EPW hourly row + LOCATION header → derive atmosphere → solar geometry at
the MID-INTERVAL hour (EPW is hour-ending) → build_record (engine → cloud modifier → resample).
"""
from hcl_core import jobcontrol
from hcl_core import epw_hourly, atmosphere, solpos
from hcl_core.spectral_sky import build_record
from hcl_core.spectral_engine.spectrl2 import Spectrl2Engine
from hcl_core.cloud_modifier import Sedes1Modifier
from hcl_core.epw_location import parse_epw_location

_SOLAR_CONSTANT = 1361.0   # W/m² at mean sun–earth distance (modern WMO value).
# Used ONLY to normalize the clearness index Kt (i0_normal = 1361·ERV); it is a normalization constant,
# deliberately decoupled from any engine's internal ETR spectrum. (SMARTS keeps its native 1367; SPECTRL2
# has its own ET_H0 table. These are different roles — not unified, not a bug. spec §12.)


def record_from_epw(epw_path, month, day, hour, *, engine=None, modifier=None, overrides=None,
                    ozone_mode=None, aerosol_g=None, aod_anchor_nm=None,
                    return_diagnostics=False):
    """Build one SpectralSkyRecord for (month, day, hour) from an EPW. Mid-interval hour for geometry.

    ozone_mode: passed through to atmosphere.derive() ("constant" default, or "climatology" to
      use van_heuklon_ozone() seeded from the EPW LOCATION lat/lon and this hour's day-of-year).
    aerosol_g, aod_anchor_nm: passed through to atmosphere.derive() (the explicit aerosol_g
      kwarg takes precedence over an aerosol_g supplied in overrides; aod_anchor_nm forwarded
      directly).

    return_diagnostics=True returns `(record, diag)` where diag is the EPW parse drop report
    ({"kept", "dropped", "reasons"}); default returns just the record (backward-compatible).
    """
    engine = engine or Spectrl2Engine()
    modifier = modifier or Sedes1Modifier()

    rows, diag = epw_hourly.parse_epw_hourly_diagnostics(epw_path)
    row = epw_hourly.row_for(rows, month, day, hour)
    if row is None:
        raise ValueError(f"no EPW data row for {month}/{day} hour {hour}")
    loc = parse_epw_location(epw_path)
    if loc is None:
        raise ValueError("could not parse EPW LOCATION header")

    geo = solpos.compute(month=month, day=day, hour=hour - 0.5,
                         latitude=loc["latitude"], longitude=loc["longitude"],
                         time_zone=loc["time_zone"])
    ovr = dict(overrides or {})
    if aerosol_g is not None:
        ovr["aerosol_g"] = aerosol_g
    # loc["longitude"] is DAYSIM/.wea WEST-positive (what solpos consumes); van_heuklon_ozone
    # expects the paper's EAST-positive convention, so the sign flips back here.
    atm = atmosphere.derive(row, overrides=ovr, ozone_mode=(ozone_mode or "constant"),
                            aod_anchor_nm=aod_anchor_nm, lat_deg=loc["latitude"],
                            lon_deg=-loc["longitude"], day_of_year=geo.day_of_year)
    dni = row["dni"] or 0.0
    dhi = row["dhi"] or 0.0
    ghi = row["ghi"] or 0.0
    i0_normal = _SOLAR_CONSTANT * geo.earth_radius_vector
    record = build_record(engine, modifier, atm, geo, timestamp=(month, day, hour),
                          dni=dni, dhi=dhi, ghi=ghi, i0_normal=i0_normal)
    return (record, diag) if return_diagnostics else record


def annual_records(epw_path, *, engine=None, modifier=None, hours=None, overrides=None,
                   ozone_mode=None, aerosol_g=None, aod_anchor_nm=None,
                   return_diagnostics=False):
    """One SpectralSkyRecord per EPW data row (or per (month,day,hour) in `hours`).

    ozone_mode, aerosol_g, aod_anchor_nm, overrides: passed through to atmosphere.derive() for
      EACH row (same semantics as record_from_epw). ozone_mode="climatology" uses each row's own
      geo.day_of_year (from solpos, computed per row) so ozone varies by season across the year.

    return_diagnostics=True returns `(records, diag)` where diag is the EPW parse drop report
    ({"kept", "dropped", "reasons"}); default returns just the list (backward-compatible).
    """
    engine = engine or Spectrl2Engine()
    modifier = modifier or Sedes1Modifier()
    wanted = set(hours) if hours is not None else None
    rows, diag = epw_hourly.parse_epw_hourly_diagnostics(epw_path)
    loc = parse_epw_location(epw_path)
    if loc is None:
        raise ValueError("could not parse EPW LOCATION header")

    out = []
    for row in rows:
        # A year is 8760 spectra of pure Python, with no command to kill: stop here if the
        # caller's job was cancelled (a no-op outside a job).
        jobcontrol.raise_if_cancelled()
        key = (row["month"], row["day"], row["hour"])
        if wanted is not None and key not in wanted:
            continue
        geo = solpos.compute(month=row["month"], day=row["day"], hour=row["hour"] - 0.5,
                             latitude=loc["latitude"], longitude=loc["longitude"],
                             time_zone=loc["time_zone"])
        ovr = dict(overrides or {})
        if aerosol_g is not None:
            ovr["aerosol_g"] = aerosol_g
        # Same sign flip as record_from_epw: west-positive .wea longitude -> east-positive for ozone.
        atm = atmosphere.derive(row, overrides=ovr, ozone_mode=(ozone_mode or "constant"),
                                aod_anchor_nm=aod_anchor_nm, lat_deg=loc["latitude"],
                                lon_deg=-loc["longitude"], day_of_year=geo.day_of_year)
        i0_normal = _SOLAR_CONSTANT * geo.earth_radius_vector
        out.append(build_record(engine, modifier, atm, geo, timestamp=key,
                                dni=row["dni"] or 0.0, dhi=row["dhi"] or 0.0,
                                ghi=row["ghi"] or 0.0, i0_normal=i0_normal))
    return (out, diag) if return_diagnostics else out
