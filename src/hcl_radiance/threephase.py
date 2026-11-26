"""Three-phase step assembly.

The contract that matters: `build_threephase_steps` ray-traces V and D ONCE per window
group, and `multiply_steps` is then called once per shading state, emitting only
dctimestep + rmtxop. A new blind state therefore costs a matrix multiply, not a retrace.

Two octrees, both shapes established by live test (.scratch/lm83/engine-findings.md):
  vmx.oct = materials + interior geometry.  The window glow is NOT in it -- rfluxmtx
            appends the receiver itself (its header records `oconv -f -i vmx.oct rx.rad`).
  dmx.oct = materials + exterior context only.  No interior, and NO sky: a white-sky
            glow in this octree occludes the sky receiver and drives D to exactly 0.

stdin/stdout values are BARE FILENAMES: proc.run_sequence joins them against work_dir.
"""
import os

from hcl_radiance.annual_commands import build_oconv_annual, materials_files
from hcl_radiance.threephase_commands import (DEFAULT_D_PARAMS, DEFAULT_V_PARAMS,
                                              build_dctimestep_3ph,
                                              build_gendaymtx_sky_mf,
                                              build_rfluxmtx_daylight,
                                              build_rfluxmtx_view,
                                              build_rmtxop_photopic, build_rmtxop_sum,
                                              sky_receiver_rad)


def build_threephase_steps(scene, senders, wea, points, n_pts, *, work_dir,
                           v_params=None, d_params=None, sky_mf=4):
    """Steps that ray-trace V and D once per window group, plus the sky matrix.

    `senders` maps a window-group name to its glow .rad path (aperture.write_window_sender).
    One file serves both roles: D is winding-insensitive and V wants the OBJ's own
    outward winding.

    `scene` is {materials, geometry, sky_color} plus an optional `exterior` list of .rad
    paths (context/ground) that belong in the D octree.
    """
    v_params = v_params or DEFAULT_V_PARAMS
    d_params = d_params or DEFAULT_D_PARAMS
    mats = materials_files(scene["materials"])
    exterior = list(scene.get("exterior") or [])
    steps = [{"write": ("sky_receiver.rad", sky_receiver_rad(sky_mf))}]

    # V's octree carries the room. The window glow is deliberately absent: rfluxmtx
    # oconv's the receiver onto the octree itself, and a duplicate modifier is at best
    # redundant and at worst a "duplicate modifier" failure.
    steps.append({"cmd": build_oconv_annual([*mats, scene["geometry"]]),
                  "stdout": "vmx.oct"})
    # D's octree deliberately excludes the interior (outbound rays would be absorbed by
    # the room) and any sky (a glow source there occludes the receiver).
    steps.append({"cmd": build_oconv_annual([*mats, *exterior]), "stdout": "dmx.oct"})

    out = {"v_mtx": {}, "d_mtx": {}}
    for name, sender in senders.items():
        v_name, d_name = f"{name}_v.mtx", f"{name}_d.mtx"
        steps.append({"cmd": build_rfluxmtx_view(n_pts, v_params, sender, "vmx.oct"),
                      "stdin": points, "stdout": v_name})
        steps.append({"cmd": build_rfluxmtx_daylight(d_params, sender,
                                                     "sky_receiver.rad", "dmx.oct"),
                      "stdout": d_name})
        out["v_mtx"][name] = v_name
        out["d_mtx"][name] = d_name

    # Two sky matrices: the sky alone, and the sky with the sun in it. Which one a window
    # group multiplies depends on its blind -- see multiply_steps.
    steps.append({"cmd": build_gendaymtx_sky_mf(wea, scene["sky_color"], mf=sky_mf),
                  "stdout": "sky.smx"})
    steps.append({"cmd": build_gendaymtx_sky_mf(wea, scene["sky_color"], mf=sky_mf, sun=True),
                  "stdout": "skysun.smx"})
    out["sky_mtx"] = "sky.smx"
    out["skysun_mtx"] = "skysun.smx"
    out["sky_mf"] = sky_mf
    return steps, out


def multiply_steps(outputs, t_matrices, tag, *, with_sun=()):
    """dctimestep + photopic collapse + group sum for ONE shading state. No ray tracing.

    `t_matrices` maps every group name to a Klems T-matrix path. A missing group is an
    error, not a silent omission: dropping a group would quietly delete a window's whole
    contribution. Group contributions are SUMMED, since each lights every sensor.

    `with_sun` names the groups that multiply the sky-WITH-sun matrix: the ones whose blind
    is closed in this state, since a diffusing blind passes its share of the sun's light.
    Every other group multiplies the sky alone; its sunlight is added afterwards from the
    exact direct-sun pass (hcl_core.lm83.add_direct_sun), which resolves the beam far better
    than a 10-15 degree Klems bin can.
    """
    missing = sorted(set(outputs["v_mtx"]) - set(t_matrices))
    if missing:
        raise ValueError(f"no T matrix supplied for window group(s): {', '.join(missing)}")
    with_sun = set(with_sun)
    steps, per_group = [], []
    for name in outputs["v_mtx"]:
        lux = f"{name}_{tag}.ill"
        sky = outputs["skysun_mtx"] if name in with_sun else outputs["sky_mtx"]
        steps.append({"cmd": [*build_dctimestep_3ph(outputs["v_mtx"][name],
                                                    t_matrices[name],
                                                    outputs["d_mtx"][name],
                                                    sky),
                              "|", *build_rmtxop_photopic()],
                      "stdout": lux})
        per_group.append(lux)
    combined = f"{tag}.ill"
    steps.append({"cmd": build_rmtxop_sum(per_group), "stdout": combined})
    return steps, combined
