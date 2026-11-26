"""Annual photopic daylight runner: reuses the 2-phase DDS step-builder, adds a direct-only
(-ab 0) ASE pass, and returns per-point lux matrices for hcl_core.daylight_metrics."""
import os

from hcl_platform import write_text
from hcl_radiance.annual import _build_annual_steps, _count_points, _emit_if_cal_missing, _available
from hcl_radiance.annual_commands import skyglow_rad
from hcl_radiance.annual_results import parse_ill_matrix, combine_sky_sun
from hcl_radiance.commands import pts_to_text, ambient_convergence_note
from hcl_radiance.runner import run_sequence
from hcl_core.daylight_metrics import rgb_to_photopic_lux


def _force_direct_only(rad_params):
    """Return rad_params with the ambient-bounce count forced to 0 (-ab 0) for the ASE pass."""
    toks = rad_params.split()
    out, i, saw = [], 0, False
    while i < len(toks):
        if toks[i] == "-ab":
            out += ["-ab", "0"]
            saw = True
            i += 2 if i + 1 < len(toks) else 1
            continue
        out.append(toks[i])
        i += 1
    if not saw:
        out = ["-ab", "0"] + out
    return " ".join(out)


def _concat_sets(sets):
    """Concatenate per-set [n_pts][n_ts][3] -> [n_pts][n_ts][3*len(sets)] in set order."""
    if not sets:
        return []
    n_pts = len(sets[0])
    n_ts = len(sets[0][0]) if sets[0] else 0
    # Every set must agree on BOTH dimensions: the loops below pair them positionally at [p][t],
    # so a set short by a point or a timestep silently supplies a LATER entry's values (a wrong
    # annual mel-EDI, reported with full confidence) until the ragged tail raises a bare
    # IndexError naming neither the set nor the mismatch.
    pt_counts = [len(s) for s in sets]
    if len(set(pt_counts)) > 1:
        raise ValueError(
            f"channel sets disagree on sensor count {pt_counts}; the per-point series cannot be "
            f"paired. A short set usually means one channel's matrix failed to parse.")
    ts_counts = [len(s[0]) if s else 0 for s in sets]
    if len(set(ts_counts)) > 1:
        raise ValueError(
            f"channel sets disagree on timestep count {ts_counts}; the per-timestep series cannot "
            f"be paired. A short set usually means one channel's matrix was truncated.")
    out = []
    for p in range(n_pts):
        prow = []
        for t in range(n_ts):
            ch = []
            for s in sets:
                ch.extend(s[p][t])
            prow.append(ch)
        out.append(prow)
    return out


def _pair_sky_sun(sky, sun, sky_name, sun_name):
    """Sky + sun per point and timestep. The two matrices come from one run over one set of
    points and one weather file, so they are the same size; if they are not, a step went wrong
    and `zip` would hide it by dropping the surplus points or hours."""
    def shape(m):
        return len(m), (len(m[0]) if m else 0)
    if shape(sky) != shape(sun):
        (sp, st), (up, ut) = shape(sky), shape(sun)
        raise ValueError(
            f"the sky and sun results of one annual run differ in size: {sky_name} has "
            f"{sp} point(s) x {st} timestep(s), {sun_name} has {up} point(s) x {ut} timestep(s). "
            "One of the two matrix steps did not finish; clear the work folder and run again.")
    return [combine_sky_sun(s, u) for s, u in zip(sky, sun)]


def run_annual_daylight(channel_scenes, wea, points, channel_type, *,
                        rad_params="-ab 2 -ad 512 -aa 0.1 -ar 64", work_dir, run=True, ase=True):
    """Run the annual sim -> per-point total lux matrix (and, when ase=True, a direct-only
    ASE lux matrix). ase=False skips the extra -ab 0 pass (daylight_savings needs only total)."""
    n_expected = 1 if channel_type == 0 else 3
    if len(channel_scenes) != n_expected:
        raise ValueError(f"channel_type {channel_type} needs {n_expected} channel scene(s)")
    os.makedirs(work_dir, exist_ok=True)
    with open(os.path.join(work_dir, "skyglow.rad"), "w") as fh:
        fh.write(skyglow_rad())
    if not isinstance(points, str):
        # Accept inline [[x,y,z,dx,dy,dz], ...] points too (matching run_grid's convention):
        # write them to a .pts file in work_dir so downstream stdin/_count_points both see a path.
        inline_points, points = points, "points.pts"
        write_text(os.path.join(work_dir, points), pts_to_text(inline_points))  # LF: fed to rtrace
    n_pts = _count_points(points, work_dir)
    ase_rad = _force_direct_only(rad_params) if ase else None
    steps, set_outputs = _build_annual_steps(channel_scenes, wea, points, rad_params, n_pts,
                                             work_dir=work_dir, run_available=run and _available(),
                                             ase_rad_params=ase_rad)
    degraded = _emit_if_cal_missing(steps, work_dir, run)
    if degraded is not None:
        return degraded
    result = run_sequence(steps, work_dir=work_dir, available=run and _available())
    if not result["ran"]:
        return {"ran": False, "commands": result["commands"], "reason": result.get("reason")}
    if result.get("returncode", 0) != 0:
        return {"ran": True, "error": result.get("error"), "failed_step": result.get("failed_step")}

    total_sets, ase_sets = [], []
    for entry in set_outputs:
        ill_sky, ill_sun = entry[0], entry[1]
        sky = parse_ill_matrix(open(os.path.join(work_dir, ill_sky)).read())
        sun = parse_ill_matrix(open(os.path.join(work_dir, ill_sun)).read())
        total_sets.append(_pair_sky_sun(sky, sun, ill_sky, ill_sun))
        if ase:
            ill_sun_ase = entry[2]
            ase_sets.append(parse_ill_matrix(open(os.path.join(work_dir, ill_sun_ase)).read()))
    total_channels = _concat_sets(total_sets)
    lux = rgb_to_photopic_lux(total_channels, channel_type)
    sun_lux = rgb_to_photopic_lux(_concat_sets(ase_sets), channel_type) if ase else None
    out = {"ran": True, "n_points": len(lux),
           "n_timesteps": len(lux[0]) if lux else 0,
           "lux_matrix": lux, "sun_lux_matrix": sun_lux,
           "rad_params": rad_params}
    note = ambient_convergence_note(rad_params)
    if note:
        # Travels with the result because DA/sDA/UDI are threshold crossings: under-converged
        # indirect sampling moves them far more than it moves means, and nothing else in this
        # return would reveal that the number is sampling-limited.
        out["convergence_warning"] = note
    return out
