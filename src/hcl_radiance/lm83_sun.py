"""The zero-bounce direct-sun pass that feeds both ASE and the blind trigger.

LM-83 3.3: "ASE does not require modeling of sky luminance or ground reflectance. Only
the direct sunlight component is modeled to calculate ASE." That is a permission to omit
rather than a prohibition, but since ASE is defined at zero bounce (3.2.2: "It does not
account for surface inter-reflections") omitting them makes the result unambiguously the
direct component. The annual path's sky definition carries a groundglow
(annual_commands.py:68), so this pass builds its own octree: materials + geometry +
solar discs, with no sky and no ground.

2.2.6's "direct sunlight" for the blind trigger is the same quantity as 3.2.2's for ASE
-- 1000 lux of direct beam, zero bounce, glazing transmittance included, operable blinds
excluded -- so one pass serves both.
"""
from hcl_core.data import LUMINOUS_EFFICACY, W_PHOTOPIC_3
from hcl_radiance.annual_commands import (build_dctimestep, build_gendaymtx_sun,
                                          build_oconv_annual, build_rcontrib_sun,
                                          materials_files, stage_cal_files,
                                          suns_rad_steps)
from hcl_radiance.annual_results import _parse_ill_header


def build_sun_pass_steps(scene, wea, points, n_pts, *, work_dir, rad_params="-ab 0",
                         run=True, tag="sun_direct"):
    """Steps for the direct-only illuminance matrix. Returns (steps, ill_filename).

    Operable blinds are absent by construction -- this scene never carries a blind T
    matrix -- which is what 3.2.6 requires ("Blinds and shades are NOT deployed for the
    ASE analysis") and what 2.2.6 requires of the trigger quantity. Fixed shading in
    `geometry`/`exterior` is retained, per 3.2.6's "Any fixed or static shading devices,
    such as overhangs or light shelves, should be included in the ASE model."

    `tag` names the output so a per-window-group pass (each with only that group's
    glazing present) does not collide with the whole-model one.
    """
    mats = materials_files(scene["materials"])
    exterior = list(scene.get("exterior") or [])
    steps = list(stage_cal_files(work_dir, run=run))
    steps.extend(suns_rad_steps("suns.rad"))

    oct_name = f"{tag}.oct"
    coeff = f"{tag}_coeff.mtx"
    ill = f"{tag}.ill"
    # No sky, no ground (3.3). Geometry and context stay for the fixed-shading rule.
    steps.append({"cmd": build_oconv_annual([*mats, scene["geometry"], *exterior,
                                             "suns.rad"], frozen=True),
                  "stdout": oct_name})
    steps.append({"cmd": build_rcontrib_sun(n_pts, rad_params, oct_name, points, coeff),
                  "stdin": points, "stdout": coeff})
    steps.append({"cmd": build_gendaymtx_sun(wea, "sun.mtx"), "stdout": "sun.mtx"})
    steps.append({"cmd": build_dctimestep(coeff, "sun.mtx"), "stdout": ill})
    return steps, ill


def parse_lux_matrix(text):
    """A dctimestep/rmtxop ASCII matrix -> [n_points][n_timesteps] photopic lux.

    Handles NCOMP=1 (already collapsed by `rmtxop -c`) and NCOMP=3 (raw RGB, collapsed
    here with the same efficacy weighting daylight_metrics uses).
    """
    lines = text.splitlines()
    _nrows, _ncols, ncomp, fmt, data_start = _parse_ill_header(lines)
    if fmt is not None and fmt.strip().lower() != "ascii":
        raise ValueError(
            f"parse_lux_matrix needs an ASCII matrix but the header declares FORMAT={fmt!r}; "
            "re-run without binary output before parsing.")
    ncomp = int(ncomp or 1)
    out = []
    for line in lines[data_start:]:
        toks = line.split()
        if not toks:
            continue
        vals = [float(t) for t in toks]
        if ncomp == 1:
            out.append(vals)
        else:
            row = []
            for i in range(0, len(vals), ncomp):
                chunk = vals[i:i + ncomp]
                row.append(LUMINOUS_EFFICACY * sum(w * c for w, c
                                                   in zip(W_PHOTOPIC_3, chunk)))
            out.append(row)
    return out
