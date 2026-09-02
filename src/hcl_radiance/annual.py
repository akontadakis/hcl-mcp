"""Annual 2-phase DDS workflow: per channel-set build sky+sun matrices, dctimestep, ADD sky+sun
(total = sky-diffuse + sun-direct; the Lark source keeps them separate), recombine."""
import os

from hcl_platform import write_text
from hcl_radiance.discover import radiance_status
from hcl_radiance.annual_commands import (skyglow_rad, suns_rad_steps, build_rfluxmtx_sky, missing_cal_files,
    materials_files,
    build_gendaymtx_sky, build_rcontrib_sun, build_gendaymtx_sun, build_dctimestep,
    build_oconv_annual, stage_cal_files)
from hcl_radiance.annual_results import parse_ill, combine_sky_sun, recombine_annual
from hcl_radiance.runner import run_sequence

def _available():
    return radiance_status()["available"]

def _emit_if_cal_missing(steps, work_dir, run):
    """DEF-4: when Radiance is present but a required Reinhart .cal file isn't in its lib, return an
    honest emit envelope (ran:False + the full command plan + a reason) instead of letting the run
    fail mid-sequence at `cp <cal>`. Returns None when nothing is missing (proceed with the run)."""
    if not (run and _available()):
        return None
    missing = missing_cal_files()
    if not missing:
        return None
    plan = run_sequence(steps, work_dir=work_dir, available=False)
    return {"ran": False, "commands": plan["commands"],
            "reason": ("Radiance is installed but required Reinhart .cal file(s) are missing from its "
                       "lib: " + ", ".join(missing) + ". The 2-phase DDS workflow needs them. Add them "
                       "to the Radiance lib (or run the emitted commands manually).")}

def _count_points(points_path, work_dir):
    # Count non-blank sensor rows (rfluxmtx/rcontrib -y). Lark uses raw len(readlines()); we drop
    # blank/trailing lines so -y matches the rows Radiance actually traces even for sloppy files.
    p = points_path if os.path.isabs(points_path) else os.path.join(work_dir, points_path)
    return sum(1 for ln in open(p) if ln.strip()) if os.path.isfile(p) else 0

def _build_annual_steps(channel_scenes, wea, points, rad_params, n_pts, *, work_dir, run_available,
                        ase_rad_params=None):
    """Per-channel-set annual step builder shared by run_annual and run_annual_separated.

    Lifts the exact per-channel loop body (stage_cal_files + suns_rad_steps + per-channel
    oconv/rfluxmtx/gendaymtx_sky/dctimestep for sky, plus frozen oconv/rcontrib/gendaymtx_sun/
    dctimestep for sun). Returns (steps, set_outputs) where set_outputs is a list of
    (ill_sky, ill_sun) tuples (one per channel-set). Emitted commands are byte-identical to the
    previously inline loops. Callers handle period/pre_steps prepend and post-run combine.

    ase_rad_params: when None (default), behaviour and set_outputs are byte-identical to before
    (2-tuples). When a rad_params string is given (e.g. -ab forced to 0), an additional
    direct-only rcontrib+dctimestep pass is appended per channel-set (reusing the same frozen sun
    octree and neutral sun matrix), and set_outputs entries become 3-tuples
    (ill_sky, ill_sun, ill_sun_ase) for the ASE (Annual Sunlight Exposure) metric.
    """
    steps, set_outputs = [], []
    # Stage the Reinhart .cal files into work_dir BEFORE any rfluxmtx/rcontrib step, mirroring the
    # source's copy guard (reinhartb.cal/reinsrc.cal/reinhart.cal). These copy commands are included
    # in the emitted command list so the run=False path is reproducible.
    steps += stage_cal_files(work_dir, run=run_available)
    steps += suns_rad_steps("suns.rad")
    for i, sc in enumerate(channel_scenes):
        oct_s, oct_sun = f"sky{i}.oct", f"sun{i}.oct"
        illum_s, illum_sun = f"illum_sky{i}.mtx", f"illum_sun{i}.mtx"
        sky_mtx, sun_mtx = f"sky{i}.mtx", f"sun{i}.mtx"
        ill_sky, ill_sun = f"annual_sky{i}.ill", f"annual_sun{i}.ill"
        # Accept materials as a space-joined string ("a.rad b.rad") OR a list of paths — the latter is
        # exactly what import_geometry's material_sets returns (DEF-3). Flatten either into oconv args.
        mat_files = materials_files(sc["materials"])
        # Sky octree: plain (NO -f). Source line 122: `oconv {materials} {geometry} > {oct}`.
        steps.append({"cmd": build_oconv_annual([*mat_files, sc["geometry"]], frozen=False), "stdout": oct_s})
        steps.append({"cmd": build_rfluxmtx_sky(n_pts, rad_params, "skyglow.rad", oct_s, points, illum_s),
                      "stdin": points, "stdout": illum_s})
        steps.append({"cmd": build_gendaymtx_sky(wea, sc["sky_color"], sky_mtx), "stdout": sky_mtx})
        steps.append({"cmd": build_dctimestep(illum_s, sky_mtx), "stdout": ill_sky})
        # Sun octree: FROZEN (-f). Source line 177: `oconv -f {materials} {geometry} {suns} > {octSun}`.
        steps.append({"cmd": build_oconv_annual([*mat_files, sc["geometry"], "suns.rad"], frozen=True), "stdout": oct_sun})
        steps.append({"cmd": build_rcontrib_sun(n_pts, rad_params, oct_sun, points, illum_sun),
                      "stdin": points, "stdout": illum_sun})
        steps.append({"cmd": build_gendaymtx_sun(wea, sun_mtx), "stdout": sun_mtx})
        steps.append({"cmd": build_dctimestep(illum_sun, sun_mtx), "stdout": ill_sun})
        if ase_rad_params is None:
            set_outputs.append((ill_sky, ill_sun))
        else:
            # Dedicated direct-only (-ab 0) ASE pass: reuse the sun octree + neutral sun matrix,
            # recompute the coefficient matrix with no ambient bounces.
            illum_sun_ase = f"illum_sun_ase{i}.mtx"
            ill_sun_ase = f"annual_sun_ase{i}.ill"
            steps.append({"cmd": build_rcontrib_sun(n_pts, ase_rad_params, oct_sun, points, illum_sun_ase),
                          "stdin": points, "stdout": illum_sun_ase})
            steps.append({"cmd": build_dctimestep(illum_sun_ase, sun_mtx), "stdout": ill_sun_ase})
            set_outputs.append((ill_sky, ill_sun, ill_sun_ase))
    return steps, set_outputs


def run_annual(channel_scenes, wea, points, channel_type, *, rad_params="-ab 2 -ad 512 -aa 0.1 -ar 64",
               work_dir, run=True, dosimetry_threshold=None, period=None, timestep_min=60):
    """channel_scenes: 1 dict (3ch) or 3 dicts (9ch). Each {materials, geometry, sky_color:[r,g,b]}.

    Builds the sky + accurate-sun annual matrices per channel-set, dctimestep, ADDS sky+sun
    (total = sky-diffuse + sun-direct; NOT a Lark port — the source keeps the two .ill outputs
    separate), recombines to per-timestep circadian metrics. Returns {ran, metrics?|commands}.

    period: optional [[m,d,h],[m,d,h]] analysis period. When given, the .wea is decomposed
    (Task 1's weather.decompose) and subset (subset_wea) into work_dir before gendaymtx, so the
    run covers only that window instead of the full 8760 h; the real HOY timestamps then drive the
    dosimetry step durations. If the .wea exists on disk the subset is written in-process; if it is
    absent (the normal run=False emit case) a `subset_wea` command is emitted instead, so emit never
    requires a readable .wea. Omit period to run the whole year (original behaviour).
    """
    n_expected = 1 if channel_type == 0 else 3
    if len(channel_scenes) != n_expected:
        raise ValueError(f"channel_type {channel_type} needs {n_expected} channel scene(s)")
    os.makedirs(work_dir, exist_ok=True)
    with open(os.path.join(work_dir, "skyglow.rad"), "w") as fh:
        fh.write(skyglow_rad())
    n_pts = _count_points(points, work_dir)

    hoy = None
    pre_steps = []
    if period is not None:
        from hcl_core.weather import analysis_period, decompose, subset_wea
        dec = decompose(analysis_period(tuple(period[0]), tuple(period[1])), timestep_min)
        hoy = dec["HOY"]
        subset_name = "period.wea"
        # Subset the .wea to just the period's hours. When the source .wea is readable, do the
        # subset in-process (writes period.wea now). When it's absent (the normal run=False emit
        # scenario) DON'T read it — emit a `subset_wea` command instead, so emit never requires the
        # input file to exist. Either way, point `wea` at period.wea so gendaymtx reads the subset.
        wea_path = wea if os.path.isabs(wea) else os.path.join(work_dir, wea)
        if os.path.isfile(wea_path):
            write_text(os.path.join(work_dir, subset_name), subset_wea(wea, dec["wea_lines"]))  # LF: fed to gendaymtx
        else:
            pre_steps.append({"cmd": ["subset_wea", wea, subset_name,
                                      *[str(n) for n in dec["wea_lines"]]]})
        wea = subset_name  # feed the period-subset .wea to gendaymtx (relative to work_dir)

    steps, set_outputs = _build_annual_steps(channel_scenes, wea, points, rad_params, n_pts,
                                             work_dir=work_dir, run_available=run and _available())
    # RAD-3: prepend the subset_wea emit (if any) so it runs before gendaymtx. This prepend stays in
    # the run_annual caller (run_annual_separated has no period path).
    steps = pre_steps + steps

    degraded = _emit_if_cal_missing(steps, work_dir, run)
    if degraded is not None:
        return degraded
    result = run_sequence(steps, work_dir=work_dir, available=run and _available())
    if not result["ran"]:
        return {"ran": False, "commands": result["commands"], "reason": result.get("reason")}
    if result.get("returncode", 0) != 0:
        return {"ran": True, "error": result.get("error"), "failed_step": result.get("failed_step")}

    combined_sets = []
    for ill_sky, ill_sun in set_outputs:
        # Source keeps these two .ill files separate; we ADD them (total = sky-diffuse + sun-direct).
        sky = parse_ill(open(os.path.join(work_dir, ill_sky)).read())
        sun = parse_ill(open(os.path.join(work_dir, ill_sun)).read())
        combined_sets.append(combine_sky_sun(sky, sun))
    metrics = recombine_annual(combined_sets, channel_type)
    out = {"ran": True, "n_timesteps": len(metrics), "metrics": metrics}
    if dosimetry_threshold is not None:
        from hcl_core.dosimetry import dose_summary
        # mel-EDI, NOT melanopic_lux: every circadian threshold is written in CIE S 026 mel-EDI,
        # and melanopic_lux is larger by D65's melanopic/photopic ratio (1.0997x on the 9-bin
        # route), which would silently relax `dosimetry_threshold`. See metrics._with_mel_edi.
        medi = [m["mel_edi"] for m in metrics]
        # Real HOY (from the period decomposition) gives honest step durations; fall back to unit
        # hourly steps only when no period was supplied or lengths disagree.
        hoy_series = hoy if (hoy is not None and len(hoy) == len(medi)) else list(range(len(medi)))
        # The run's own timestep sets each sample's duration, so a gapped/multi-month HOY series
        # cannot charge a sample the non-occupied gap that follows it.
        out["dosimetry"] = dose_summary(medi, hoy_series, threshold=dosimetry_threshold,
                                        step_hours=(timestep_min / 60.0))
    return out


def run_annual_separated(channel_scenes, wea, points, channel_type, *,
                         rad_params="-ab 2 -ad 512 -aa 0.1 -ar 64", work_dir, run=True):
    """Like run_annual, but returns sky & sun .ill rows SEPARATELY (no combine_sky_sun).

    The annual->nvRD bridge (spec §5.1) needs sky-diffuse and sun-direct kept apart so the enhanced
    reconstruction can re-color only the direct beam. Reuses run_annual's exact step building; on
    success returns {ran:True, sky_sets, sun_sets} where each *_sets is a list (one per channel-set)
    of per-timestep [R,G,B] rows. On emit returns {ran:False, commands}.

    Unlike run_annual, this does NOT support period/hoy/dosimetry_threshold subsetting — it always
    processes the full .wea passed in (the bridge feeds a ready sub-hourly .wea; subset upstream if needed).
    """
    n_expected = 1 if channel_type == 0 else 3
    if len(channel_scenes) != n_expected:
        raise ValueError(f"channel_type {channel_type} needs {n_expected} channel scene(s)")
    os.makedirs(work_dir, exist_ok=True)
    with open(os.path.join(work_dir, "skyglow.rad"), "w") as fh:
        fh.write(skyglow_rad())
    n_pts = _count_points(points, work_dir)

    # No period/pre_steps path here — use the shared per-channel step builder directly.
    steps, set_outputs = _build_annual_steps(channel_scenes, wea, points, rad_params, n_pts,
                                             work_dir=work_dir, run_available=run and _available())

    degraded = _emit_if_cal_missing(steps, work_dir, run)
    if degraded is not None:
        return degraded
    result = run_sequence(steps, work_dir=work_dir, available=run and _available())
    if not result["ran"]:
        return {"ran": False, "commands": result["commands"], "reason": result.get("reason")}
    if result.get("returncode", 0) != 0:
        return {"ran": True, "error": result.get("error"), "failed_step": result.get("failed_step")}

    sky_sets, sun_sets = [], []
    for ill_sky, ill_sun in set_outputs:
        sky_sets.append(parse_ill(open(os.path.join(work_dir, ill_sky)).read()))
        sun_sets.append(parse_ill(open(os.path.join(work_dir, ill_sun)).read()))
    return {"ran": True, "sky_sets": sky_sets, "sun_sets": sun_sets}
