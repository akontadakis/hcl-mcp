"""Daylight Factor via a dedicated CIE-overcast (gensky -c) run. DF = E_indoor/E_outdoor * 100.
E_outdoor is an unobstructed horizontal illuminance obtained by tracing a single upward point
in a sky-only scene (no geometry), so it is exact for the same overcast sky."""
import os

from hcl_core.proc import render
from hcl_radiance.discover import radiance_status
from hcl_radiance.runner import run_sequence
from hcl_radiance.sky_overcast import write_overcast_sky
from hcl_radiance.grid import run_grid as _run_grid


def _available():
    return radiance_status()["available"]


def _photopic(grid_result):
    """Pull per-point photopic lux out of a run_grid result (sim['daylight']['metrics'])."""
    metrics = grid_result["daylight"]["metrics"]
    metrics = metrics if isinstance(metrics, list) else [metrics]
    return [m["photopic_lux"] for m in metrics]


def run_daylight_factor(scene_sets, indoor_points, *, work_dir, run=True, rad_params=None,
                        month=6, day=21, hour=12.0, gnd_refl=0.2):
    """Indoor grid (building + overcast sky) and a sky-only exterior reference -> DF per point."""
    os.makedirs(work_dir, exist_ok=True)
    sky_steps, sky_out = write_overcast_sky(work_dir, month=month, day=day, hour=hour,
                                            gnd_refl=gnd_refl)
    building = list(scene_sets[0]) if scene_sets and isinstance(scene_sets[0], list) else list(scene_sets)
    indoor_scene = [building + [sky_out]]            # 3-channel single set incl. overcast sky
    exterior_scene = [[sky_out]]                     # sky only -> unobstructed
    exterior_point = [[0.0, 0.0, 0.0, 0.0, 0.0, 1.0]]

    gkw = {"work_dir": work_dir, "run": run}
    if rad_params:
        gkw["rad_params"] = rad_params

    # `run_grid`'s indoor octree includes overcast_sky.rad in its scene set, so that file must
    # physically exist in work_dir BEFORE run_grid's oconv reads it. On the real run path
    # (run=True and Radiance available) execute the sky-build steps in-process now, mirroring
    # how run_annual writes skyglow.rad before its own run_sequence call. On the emit path
    # (run=False, or Radiance unavailable) skip execution — nothing should touch disk/exec, and
    # the emitted command plan below still renders the sky steps as strings so it stays honest.
    sky_available = run and _available()
    if sky_available:
        sky_result = run_sequence(sky_steps, work_dir=work_dir, available=True)
        if sky_result.get("returncode", 0) != 0:
            return {"ran": True, "error": sky_result.get("error"),
                    "failed_step": sky_result.get("failed_step")}

    indoor = _run_grid(indoor_scene, indoor_points, 0, **gkw)
    if not indoor.get("ran"):
        # emit path: render the sky-build steps to strings so the command plan is uniform
        # (run_grid's emitted commands are already pre-rendered strings), and also emit the
        # exterior sky-only grid's commands so the plan reflects BOTH grids a live run performs
        # (a live run always executes the exterior reference too, to compute E_outdoor).
        exterior = _run_grid(exterior_scene, exterior_point, 0, **gkw)
        cmds = ([render(s) for s in sky_steps] + (indoor.get("commands") or [])
                + (exterior.get("commands") or []))
        return {"ran": False, "commands": cmds, "reason": indoor.get("reason")}
    if "daylight" not in indoor:
        return {"ran": True, "error": indoor.get("error"), "failed_step": indoor.get("failed_step")}

    exterior = _run_grid(exterior_scene, exterior_point, 0, **gkw)
    # Guard the exterior exactly as the indoor run is guarded above. DF is E_indoor/E_outdoor, so
    # this reference IS the denominator — without it there is no DF to report. Unguarded, a failed
    # exterior run died on `KeyError: 'daylight'` instead of saying which run failed and why.
    if "daylight" not in exterior:
        return {"ran": True, "error": exterior.get("error"),
                "failed_step": exterior.get("failed_step"),
                "stage": "exterior_reference"}
    e_out = _photopic(exterior)[0]
    e_in = _photopic(indoor)
    df = [round(100.0 * ei / e_out, 4) if e_out else 0.0 for ei in e_in]
    df_avg = sum(df) / len(df) if df else 0.0
    df_min = min(df) if df else 0.0
    return {"ran": True, "df_per_point": df, "df_avg": round(df_avg, 4), "df_min": round(df_min, 4),
            "uniformity": round(df_min / df_avg, 4) if df_avg else 0.0, "e_outdoor": e_out}
