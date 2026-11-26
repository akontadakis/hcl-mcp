"""generate_subhourly_wea — port of `Lark Generate Sub-Hourly wea File.py` (spec §4.3).

EPW -> epw2wea (hourly .wea) -> write Daysim .hea -> ds_shortterm -> sub-hourly broadband .wea.
Default timestep 6 min (0.1 h) to satisfy the nvRD δ <= 0.3 h guard (base §5.9). Hybrid run/emit:
when Daysim is absent, writes the .hea, emits the command plan, and returns a structured error.

Like the Lark component (which read the site block back from the epw2wea-generated .wea), the
site values default to the EPW's own LOCATION line, converted to the DAYSIM convention
(`hcl_daysim.epw.parse_epw_location`). This keeps the sub-hourly run consistent with the weather
file without the caller having to know DAYSIM's sign/units conventions; explicit args override.
"""
import os

from hcl_core.weather import import_wea, solar_zenith
from hcl_daysim.discover import _available
from hcl_daysim.commands import build_epw2wea, write_hea, build_ds_shortterm, DS_SHORTTERM_TIMESTEPS
from hcl_daysim.epw import parse_epw_location
from hcl_daysim.runner import run_sequence


def _parse_wea_timestamps_and_zeniths(wea_path, *, latitude, longitude, time_zone):
    """Read the produced sub-hourly .wea -> ([(m,d,h)...], [zenith_deg...]).

    Returns ([], []) if the file is absent/empty so callers degrade to the documented
    constant-zenith fallback.
    """
    try:
        data = import_wea(wea_path)
    except OSError:
        return [], []
    timestamps, zeniths = [], []
    for m, d, h in zip(data["months"], data["days"], data["hours"]):
        mi, di, hi = int(m), int(d), float(h)
        timestamps.append((mi, di, hi))
        zeniths.append(solar_zenith(month=mi, day=di, hour=hi,
                                    latitude=latitude, longitude=longitude, time_zone=time_zone))
    return timestamps, zeniths

def generate_subhourly_wea(epw, *, timestep_min=6, latitude=None, longitude=None, time_zone=None,
                           site_elevation=None, solar_time=0, work_dir, run=True):
    """Generate a sub-hourly .wea from an EPW via Daysim.

    epw: path to an .epw. timestep_min: minutes within the hour (default 6).
    latitude/longitude/time_zone/site_elevation: site information for the .hea. When omitted (None)
    they are read from the EPW's LOCATION line and converted to the DAYSIM convention — WEST-positive
    longitude, time_zone in DEGREES (= -15 × UTC offset) — exactly as epw2wea would. Pass explicit
    values only to override; if a value is given it must already be in DAYSIM convention (do NOT pass
    raw EPW East-positive coordinates). If latitude/longitude/time_zone are neither supplied nor
    derivable from the EPW, a ValueError is raised rather than silently running at lat 0 / long 0.
    work_dir: scratch dir. Returns {wea, ran, commands, reason?}. On run=False or Daysim absent,
    returns the emit plan.
    """
    os.makedirs(work_dir, exist_ok=True)

    # Validate the timestep against the ds_shortterm allow-set BEFORE any file I/O so an
    # out-of-set value never produces a .hea / command plan that only fails at runtime.
    if timestep_min not in DS_SHORTTERM_TIMESTEPS:
        raise ValueError(
            f"timestep_min={timestep_min!r} is rejected by ds_shortterm; "
            f"choose one of {sorted(DS_SHORTTERM_TIMESTEPS)}.")

    # Site values default to the EPW LOCATION line (DAYSIM convention); explicit args win.
    site = parse_epw_location(epw) or {}
    latitude = latitude if latitude is not None else site.get("latitude")
    longitude = longitude if longitude is not None else site.get("longitude")
    time_zone = time_zone if time_zone is not None else site.get("time_zone")
    site_elevation = site_elevation if site_elevation is not None else site.get("site_elevation", 0)
    missing = [n for n, v in (("latitude", latitude), ("longitude", longitude),
                              ("time_zone", time_zone)) if v is None]
    if missing:
        raise ValueError(
            f"{', '.join(missing)} could not be determined for {epw!r}: the EPW LOCATION line was "
            "unreadable and no explicit value was supplied. Pass latitude/longitude/time_zone "
            "(DAYSIM convention: WEST-positive longitude, time_zone = -15 × UTC offset).")
    # A Daysim header is `keyword value`, split on blanks, with no way to quote: a file name
    # with a blank in it is read as a name plus rubbish. These two files are ours to name.
    stem = "_".join(os.path.splitext(os.path.basename(epw))[0].split())
    hourly_wea = f"{stem}.wea"
    short_wea = f"{stem}_{timestep_min}_short.wea"
    hea_name = "daysim_header.hea"

    # Always write the .hea so the emitted commands are runnable by hand.
    hea_text = write_hea(input_wea=hourly_wea, output_wea=short_wea, timestep_min=timestep_min,
                         latitude=latitude, longitude=longitude, time_zone=time_zone,
                         site_elevation=site_elevation, solar_time=solar_time)
    with open(os.path.join(work_dir, hea_name), "w") as fh:
        fh.write(hea_text)

    steps = [
        {"cmd": build_epw2wea(epw, hourly_wea)},
        {"cmd": build_ds_shortterm(hea_name)},
    ]
    wea_path = os.path.join(work_dir, short_wea)

    available = run and _available()
    result = run_sequence(steps, work_dir=work_dir, available=available)
    if not result["ran"]:
        if not run:
            reason = ("run=False (dry run): wrote the .hea and emitted the epw2wea -> ds_shortterm "
                      "command plan. Set run=True (with Daysim available) to execute.")
        else:
            reason = ("Daysim not available — call build_daysim(run=True) (fetches and builds one pinned commit from source) or set "
                      "HCL_DAYSIM_BIN to a directory with ds_shortterm + epw2wea, then retry. "
                      "The .hea and command plan were written so you can run them yourself.")
        return {"wea": wea_path, "ran": False, "commands": result["commands"], "reason": reason}
    if result.get("returncode", 0) != 0:
        return {"wea": wea_path, "ran": True, "commands": result["commands"],
                "error": result.get("error"), "failed_step": result.get("failed_step")}
    timestamps, solar_zeniths = _parse_wea_timestamps_and_zeniths(
        wea_path, latitude=latitude, longitude=longitude, time_zone=time_zone)
    return {"wea": wea_path, "ran": True, "commands": result["commands"],
            "timestamps": timestamps, "solar_zeniths": solar_zeniths}
