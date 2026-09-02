"""Colored Perez sky/sun definitions — port of Lark 'Perez Sky - Colored with Sky and Sun Spectra'.

Pure construction (solar scaling, sky-glow normalization, assembly) is split from the gendaylit call.
"""
import os

from hcl_core.data import W_PHOTOPIC_3, W_PHOTOPIC_9
# NOTE: hcl_radiance.discover.radiance_status and hcl_radiance.runner.run_sequence are imported
# LAZILY inside _available() and colored_sky()'s run branch (Plan-3 modules, not present yet).

_SKY_TAIL = (
    "sky_mat source sky\n0\n0\n4 0 0 1 180\n\n"
    "skyfunc glow ground_glow\n0\n0\n4 1 1 1 0\n\n"
    "ground_glow source ground\n0\n0\n4 0 0 -1 180\n\n"
)

# Luminance-mode tail: NEUTRAL sky glow (1 1 1), WARM ground glow (1 0.8 0.5) — port L115-L118.
_SKY_TAIL_LUMINANCE = (
    "skyfunc glow sky_mat\n0\n0\n4 1 1 1 0\n\n"
    "sky_mat source sky\n0\n0\n4 0 0 1 180\n\n"
    "skyfunc glow ground_glow\n0\n0\n4 1 0.8 0.5 0\n\n"
    "ground_glow source ground\n0\n0\n4 0 0 -1 180\n"
)

def _solar_position_args(sun_zenith_deg, sun_azimuth_deg):
    """gendaylit `-ang altitude azimuth` args from a SolarGeometry-convention position, or None.

    Both must be supplied together (an explicit position needs two numbers; silently defaulting one
    would aim the sun wrong with no error). Conventions are taken VERBATIM from a SpectralSkyRecord's
    `geometry` block so a caller threads `rec["geometry"]["zenith_deg"]`/`["azimuth_deg"]` with no
    arithmetic of its own:
      zenith_deg  — degrees from vertical      -> gendaylit altitude = 90 - zenith
      azimuth_deg — clockwise from NORTH (N=0) -> gendaylit azimuth  = azimuth - 180
                                                  (gendaylit measures from SOUTH, +toward WEST)
    Returns None when neither is given (the caller then emits the date/time form).
    """
    if sun_zenith_deg is None and sun_azimuth_deg is None:
        return None
    if sun_zenith_deg is None or sun_azimuth_deg is None:
        raise ValueError("sun_zenith_deg and sun_azimuth_deg must be supplied together")
    altitude = 90.0 - float(sun_zenith_deg)
    azimuth = float(sun_azimuth_deg) - 180.0
    return ["-ang", f"{altitude:.4f}", f"{azimuth:.4f}"]

def build_gendaylit(month, day, hour, *, irrad_mode, lat, lon, utc, direct=None, diffuse=None,
                    globl=None, sun_zenith_deg=None, sun_azimuth_deg=None):
    """gendaylit command (spectra mode). irrad_mode 'W' (direct+diffuse) or 'E' (global).
    UTC->meridian = UTC*-15. `lon` is standard signed / EAST-positive (e.g. Seattle = -122.3,
    Athens = 23.73, matching raw EPW), negated internally (lon*-1) to gendaylit's west-positive -o.
    (import_weather's explicit longitude override uses the opposite, west-positive, sign because it
    feeds the Daysim .wea path directly.)

    Solar position. By default gendaylit derives the sun from `month day hour` + `-a/-o/-m` using its
    OWN ephemeris, and `hour` is read as a wall-clock instant. Supplying sun_zenith_deg AND
    sun_azimuth_deg instead emits the `-ang altitude azimuth` form, which bypasses that ephemeris so
    an upstream position is authoritative for the traced geometry. `-a/-o/-m` are dropped in that
    form: gendaylit ignores them under `-ang` (verified byte-identical output), so keeping them would
    imply a dependency that is not there.

    This function never applies an EPW hour-ending -> mid-interval (`hour - 0.5`) conversion. That is
    the orchestrator's job (spectral_pipeline.py:43), and `hour` here may legitimately be a wall-clock
    time. To keep a spectral record's spectrum and this sky on the SAME instant, pass that record's
    geometry through sun_zenith_deg/sun_azimuth_deg rather than relying on `hour` to agree."""
    meridian = int(utc * -15)
    lon_w = lon * -1
    ang = _solar_position_args(sun_zenith_deg, sun_azimuth_deg)
    if ang is not None:
        base = ["gendaylit"] + ang
        tail = []
    else:
        base = ["gendaylit", str(month), str(day), str(hour)]
        tail = ["-a", str(lat), "-o", str(lon_w), "-m", str(meridian)]
    # Guard BEFORE str() turns a None into the literal "None". gendaylit ACCEPTS "None" as an
    # irradiance, computes a zero-energy sky and emits no solar primitive at all, so the mistake
    # would otherwise surface much later as find_solar_line's "no solar RGB line" — a message that
    # points at the parser and says nothing about the missing argument. Found live 2026-08-06:
    # `direct`/`diffuse` are SEPARATE params from the channel lists, so omitting them is an easy slip.
    if irrad_mode == "W":
        if direct is None or diffuse is None:
            raise ValueError(
                "irrad_mode='W' needs both `direct` and `diffuse` (W/m2). These are SEPARATE from "
                "direct_channels/diffuse_channels, which carry spectral shape only — gendaylit needs "
                "the broadband magnitudes to place the sun. Pass the EPW hour's DNI and DHI.")
        base += ["-W", str(direct), str(diffuse)]
    elif irrad_mode == "E":
        if globl is None:
            raise ValueError(
                "irrad_mode='E' needs `globl` (global horizontal irradiance, W/m2). It is SEPARATE "
                "from the channel lists, which carry spectral shape only.")
        base += ["-E", str(globl)]
    else:
        raise ValueError("irrad_mode must be 'W' or 'E'")
    return base + tail

def find_solar_line(out_lines):
    """Index of the solar-source RGB data line ('3 R G B') in gendaylit output.

    Anchors on the 'void light solar' primitive when present, then takes the next '3 '-prefixed
    line — robust against any earlier 3-arg primitive. Falls back to the first '3 ' line otherwise.
    """
    start = 0
    for i, line in enumerate(out_lines):
        if line.strip().endswith("light solar"):
            start = i
            break
    for i in range(start, len(out_lines)):
        if out_lines[i].strip().startswith("3 "):
            return i
    raise ValueError("no solar RGB line ('3 R G B') found in gendaylit output")

def _photopic_sum(channels, channel_type):
    w = W_PHOTOPIC_3 if channel_type == 0 else W_PHOTOPIC_9
    return sum(c * wi for c, wi in zip(channels, w))

def scale_solar(solar_rgb, direct_channels, channel_type):
    """Return scaled solar-source line(s). solar_rgb = [3, R, G, B]. 3ch: 1 line; 9ch: 3 lines (a/b/c)."""
    s = _photopic_sum(direct_channels, channel_type)
    if channel_type == 0:
        coef = ((solar_rgb[1] + solar_rgb[2] + solar_rgb[3]) / 3) / s  # mean of RGB
        triplet = [round(direct_channels[i] * coef, 2) for i in range(3)]
        return ["3 " + " ".join(str(v) for v in triplet)]
    coef = ((solar_rgb[1] + solar_rgb[2] + solar_rgb[3]) / 3) / s  # mean of solar RGB (matches 3ch path)
    lines = []
    for grp in range(3):  # a=blue(0:3), b=green(3:6), c=red(6:9)
        triplet = [round(direct_channels[grp * 3 + i] * coef, 2) for i in range(3)]
        lines.append("3 " + " ".join(str(v) for v in triplet))
    return lines

def sky_glow(diffuse_channels, channel_type):
    """Normalized sky-glow material(s): each channel / photopic-weighted sum. 3ch: str; 9ch: [a,b,c]."""
    s = _photopic_sum(diffuse_channels, channel_type)
    def _mat(triplet):
        vals = " ".join(str(round(t / s, 2)) for t in triplet)
        return f"skyfunc glow sky_mat\n0\n0\n4 {vals} 0\n\n"
    if channel_type == 0:
        return _mat(diffuse_channels[:3])
    return [_mat(diffuse_channels[0:3]), _mat(diffuse_channels[3:6]), _mat(diffuse_channels[6:9])]

def assemble_sky_def(gendaylit_out, solar_lines, sky_mats, channel_type):
    """Build the final sky definition string(s): modified gendaylit output + sky_mat + sky/ground tail."""
    lines = gendaylit_out.splitlines()
    idx = find_solar_line(lines)
    out = []
    mats = sky_mats if isinstance(sky_mats, list) else [sky_mats]  # accept a bare string (3ch) or list (9ch)
    n = len(mats)
    for k in range(n):
        modified = list(lines)
        modified[idx] = solar_lines[k]
        body = "\n".join(modified).strip() + "\n\n" + mats[k] + _SKY_TAIL
        out.append(body)
    return out

def _available():
    # LAZY import: the Radiance adapter (radiance_status) lands in a later plan. Until it exists
    # (or if Radiance isn't installed), treat as "not available" so colored_sky degrades to the
    # emit path (return commands) instead of raising.
    try:
        from hcl_radiance.discover import radiance_status
    except ImportError:
        return False
    return radiance_status()["available"]

def colored_sky(diffuse_channels, direct_channels, channel_type, *, month, day, hour, irrad_mode,
                lat, lon, utc, direct=None, diffuse=None, globl=None, name="sky", work_dir, run=True,
                mode="spectra", sun_zenith_deg=None, sun_azimuth_deg=None):
    """Generate colored Perez sky/sun .rad definition(s). mode 'spectra' (per-channel scaling, runs
    gendaylit) or 'luminance' (Radiance -C built-in coloring, pure emit — see colored_sky_luminance).
    irrad_mode 'W' (direct+diffuse) or 'E' (global). `lon` is standard signed / EAST-positive
    (Seattle = -122.3, Athens = 23.73), matching raw EPW.

    sun_zenith_deg/sun_azimuth_deg (optional, together) pin the sun explicitly instead of letting
    gendaylit derive it from month/day/hour — pass a SpectralSkyRecord's `geometry.zenith_deg` and
    `geometry.azimuth_deg` verbatim so the rendered sky sits at the same instant the spectrum feeding
    diffuse_channels/direct_channels was computed for. See build_gendaylit for why `hour` alone does
    not guarantee that. Omitted -> byte-identical to before these parameters existed.

    Returns {ran, files?|commands, sky_defs?}. 3ch -> name.rad; 9ch -> name_a/_b/_c.rad.
    """
    if mode == "luminance":
        return colored_sky_luminance(channel_type, month=month, day=day, hour=hour, irrad_mode=irrad_mode,
                                     lat=lat, lon=lon, utc=utc, direct=direct, diffuse=diffuse, globl=globl,
                                     name=name, work_dir=work_dir,
                                     sun_zenith_deg=sun_zenith_deg, sun_azimuth_deg=sun_azimuth_deg)
    if mode != "spectra":
        raise ValueError("mode must be 'spectra' or 'luminance'")
    os.makedirs(work_dir, exist_ok=True)
    cmd = build_gendaylit(month, day, hour, irrad_mode=irrad_mode, lat=lat, lon=lon, utc=utc,
                          direct=direct, diffuse=diffuse, globl=globl,
                          sun_zenith_deg=sun_zenith_deg, sun_azimuth_deg=sun_azimuth_deg)
    if not (run and _available()):
        return {"ran": False, "commands": [" ".join(cmd) + " > gendaylit.out"],
                "reason": "Radiance/gendaylit not available; run the command, then re-call with run=True.",
                "next": "feed gendaylit output to assemble_sky_def via the same channels"}
    from hcl_radiance.runner import run_sequence  # LAZY import (Plan-3 module not present in Plan 2b)
    res = run_sequence([{"cmd": cmd, "stdout": "gendaylit.out"}], work_dir=work_dir, available=True)
    if res.get("returncode", 0) != 0:
        return {"ran": True, "error": res.get("error")}
    with open(os.path.join(work_dir, "gendaylit.out")) as fh:
        gendaylit_out = fh.read()
    lines = gendaylit_out.splitlines()
    solar_rgb = [float(x) for x in lines[find_solar_line(lines)].split()]
    solar_lines = scale_solar(solar_rgb, direct_channels, channel_type)
    mats = sky_glow(diffuse_channels, channel_type)
    defs = assemble_sky_def(gendaylit_out, solar_lines, mats, channel_type)
    suffixes = [""] if channel_type == 0 else ["_a", "_b", "_c"]
    files = []
    for suf, d in zip(suffixes, defs):
        path = os.path.join(work_dir, f"{name}{suf}.rad")
        with open(path, "w") as fh:
            fh.write(d)
        files.append(path)
    return {"ran": True, "files": files, "sky_defs": defs}

def build_gendaylit_luminance(month, day, hour, *, irrad_mode, lat, lon, utc,
                              direct=None, diffuse=None, globl=None,
                              sun_zenith_deg=None, sun_azimuth_deg=None):
    """gendaylit command for luminance mode: adds the Radiance `-C` (chromaticity coloring) flag.
    irrad_mode 'W' (direct+diffuse) or 'E' (global). UTC->meridian = UTC*-15. `lon` is standard
    signed / EAST-positive (Seattle = -122.3, matching raw EPW), negated internally to gendaylit's
    west-positive -o.

    sun_zenith_deg/sun_azimuth_deg behave exactly as in build_gendaylit: supplied together they emit
    the `-ang altitude azimuth` form (which composes with `-C`, verified live) and drop the then-inert
    `-a/-o/-m`; omitted, the command is byte-identical to before this parameter existed."""
    meridian = int(utc * -15)
    lon_w = lon * -1
    ang = _solar_position_args(sun_zenith_deg, sun_azimuth_deg)
    if ang is not None:
        base = ["gendaylit"] + ang + ["-C"]
        tail = []
    else:
        base = ["gendaylit", str(month), str(day), str(hour), "-C"]
        tail = ["-a", str(lat), "-o", str(lon_w), "-m", str(meridian)]
    # Guard BEFORE str() turns a None into the literal "None". gendaylit ACCEPTS "None" as an
    # irradiance, computes a zero-energy sky and emits no solar primitive at all, so the mistake
    # would otherwise surface much later as find_solar_line's "no solar RGB line" — a message that
    # points at the parser and says nothing about the missing argument. Found live 2026-08-06:
    # `direct`/`diffuse` are SEPARATE params from the channel lists, so omitting them is an easy slip.
    if irrad_mode == "W":
        if direct is None or diffuse is None:
            raise ValueError(
                "irrad_mode='W' needs both `direct` and `diffuse` (W/m2). These are SEPARATE from "
                "direct_channels/diffuse_channels, which carry spectral shape only — gendaylit needs "
                "the broadband magnitudes to place the sun. Pass the EPW hour's DNI and DHI.")
        base += ["-W", str(direct), str(diffuse)]
    elif irrad_mode == "E":
        if globl is None:
            raise ValueError(
                "irrad_mode='E' needs `globl` (global horizontal irradiance, W/m2). It is SEPARATE "
                "from the channel lists, which carry spectral shape only.")
        base += ["-E", str(globl)]
    else:
        raise ValueError("irrad_mode must be 'W' or 'E'")
    return base + tail

def colored_sky_luminance(channel_type, *, month, day, hour, irrad_mode, lat, lon, utc,
                          direct=None, diffuse=None, globl=None, name="sky", work_dir,
                          sun_zenith_deg=None, sun_azimuth_deg=None):
    """Build the luminance-mode (`-C`) colored Perez sky. 3-channel only; gendaylit is embedded
    inline ('!gendaylit ... -C ...') so this is a pure emit — no Radiance run required (port L121).
    sun_zenith_deg/sun_azimuth_deg pin the sun explicitly — see build_gendaylit."""
    if channel_type != 0:
        raise ValueError("luminance mode is 3-channel only (no 9-channel -C path)")
    os.makedirs(work_dir, exist_ok=True)
    cmd = build_gendaylit_luminance(month, day, hour, irrad_mode=irrad_mode, lat=lat, lon=lon, utc=utc,
                                    direct=direct, diffuse=diffuse, globl=globl,
                                    sun_zenith_deg=sun_zenith_deg, sun_azimuth_deg=sun_azimuth_deg)
    rad = "!" + " ".join(cmd) + "\n" + _SKY_TAIL_LUMINANCE
    path = os.path.join(work_dir, f"{name}.rad")
    with open(path, "w") as fh:
        fh.write(rad)
    return {"ran": False, "files": [path], "sky_defs": [rad]}
