#!/usr/bin/env python3
"""Live validation of the physical_sky flip on annual_nvrd (spec 2026-07-18).

One-command, self-contained: bootstraps sys.path + engine env, runs a coarse (hourly)
proof then a representative run, writes every returned dict to out/. See the design doc:
docs/superpowers/specs/2026-07-18-physical-sky-live-validation-design.md
"""
import os, sys, json, time, shutil

HCLMCP = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # .../hcl-mcp
REPO = os.path.dirname(HCLMCP)
SRC = os.path.join(HCLMCP, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT, exist_ok=True)

# Engine env (idempotent).
os.environ.setdefault("HCL_DAYSIM_BIN", "/usr/local/daysim/bin")
_RAD_BIN = "/usr/local/radiance/bin"
_RAD_LIB = "/usr/local/radiance/lib"
os.environ["PATH"] = _RAD_BIN + os.pathsep + os.environ.get("PATH", "")
os.environ["RAYPATH"] = ".:" + _RAD_LIB + os.pathsep + os.environ.get("RAYPATH", "")

EPW  = os.path.join(HCLMCP, "hcl_validation/inputs/weather/GRC_Athens.167160_IWEC.epw")
GEOM = os.path.join(HCLMCP, "hcl_validation/inputs/geometry/radiance/office_room.rad")
MATS = os.path.join(HCLMCP, "hcl_validation/inputs/geometry/radiance/materials.rad")
# PTS is GENERATED (single eye point), not a fixed asset — see write_eye_pts() in Task 2.


def _on_raypath(fname):
    roots = [".", _RAD_LIB] + os.environ.get("RAYPATH", "").split(os.pathsep)
    return any(r and os.path.exists(os.path.join(r, fname)) for r in roots)


def preflight():
    dbin = os.environ["HCL_DAYSIM_BIN"]
    checks = {
        "radiance": bool(shutil.which("rtrace") and shutil.which("gendaymtx") and shutil.which("oconv")),
        "daysim": os.path.exists(os.path.join(dbin, "epw2wea")) and os.path.exists(os.path.join(dbin, "ds_shortterm")),
        "reinsrc_cal": _on_raypath("reinsrc.cal"),
        "assets": all(os.path.exists(p) for p in (EPW, GEOM, MATS)),
        "hcl_daysim_bin": dbin,
    }
    missing = [k for k in ("radiance", "daysim", "reinsrc_cal", "assets") if not checks[k]]
    if missing:
        raise SystemExit(f"PREFLIGHT FAILED: {missing}. Details: {json.dumps(checks, indent=2)}")
    return checks


POINT_XYZ = (0.0, 0.0, 1.2)
VIEW_VEC = (0.0, -1.0, 0.0)  # gaze toward the -Y window (Rad_Glazing_T073 @ y=-3.575)


def write_eye_pts():
    # ONE eye sensor matching POINT_XYZ/VIEW_VEC. The transport reduces to sensor 0
    # (parse_ill(sensor=0)), so a single-point .pts is correct AND ~45x cheaper than the grid.
    p = os.path.join(OUT, "eye.pts")
    with open(p, "w") as fh:
        fh.write(f"{POINT_XYZ[0]} {POINT_XYZ[1]} {POINT_XYZ[2]} {VIEW_VEC[0]} {VIEW_VEC[1]} {VIEW_VEC[2]}\n")
    return p


def build_channel_scenes():
    # 3-channel: exactly ONE scene dict; sky_color=[1,1,1] is the native gendaymtx RGB split.
    return [{"materials": MATS, "geometry": GEOM, "sky_color": [1.0, 1.0, 1.0]}]


def run_once(label, timestep_min, rad_params):
    from hcl_radiance.annual_nvrd import annual_nvrd
    # The core annual_nvrd (unlike the MCP tool wrapper in server.py) expects an actual
    # SpectralEngine instance for `engine`, not a name string -- only server.py's
    # `_resolve_engine(engine)` does that string->object mapping. Resolve it here ourselves
    # since this script calls the core function directly.
    from hcl_core.spectral_engine import resolve_engine
    wd = os.path.join(OUT, f"work_{label}")
    os.makedirs(wd, exist_ok=True)
    t0 = time.time()
    res = annual_nvrd(
        point_xyz=POINT_XYZ, view_vec=VIEW_VEC,
        timestep_min=timestep_min, reconstruction="both",
        epw=EPW, channel_scenes=build_channel_scenes(), points=write_eye_pts(),
        channel_type=0, rad_params=rad_params, work_dir=wd, run=True,
        physical_sky=True, engine=resolve_engine("spectrl2"),
    )
    res["_meta"] = {"label": label, "timestep_min": timestep_min,
                    "rad_params": rad_params, "wall_clock_s": round(time.time() - t0, 1)}
    # Full dict (large: per-step R_D arrays) stays in out/ but is NOT committed.
    with open(os.path.join(OUT, f"{label}.json"), "w") as fh:
        json.dump(res, fh, indent=2, default=str)
    # Compact summary (acceptance signals + coverage + divergence + meta) is the committed evidence.
    summary = {**summarize(res), "_meta": res.get("_meta")}
    with open(os.path.join(OUT, f"{label}.summary.json"), "w") as fh:
        json.dump(summary, fh, indent=2, default=str)
    return res


def summarize(res):
    ps = res.get("physical_sky", {})
    return {
        "ran": res.get("ran"),
        "n_timesteps": res.get("n_timesteps"),
        "coverage": {k: ps.get(k) for k in ("n_physical", "n_template", "coverage_pct")},
        "has_enhanced_solar_note": "enhanced_solar_note" in res,   # True => sun fell back to 30 deg
        "rd_series_divergence": res.get("RD_series_divergence"),
        "wall_clock_s": res.get("_meta", {}).get("wall_clock_s"),
        "reason_if_not_ran": res.get("reason"),
    }


if __name__ == "__main__":
    print("PREFLIGHT:", json.dumps(preflight(), indent=2))
    phase = sys.argv[1] if len(sys.argv) > 1 else "A"
    if phase in ("A", "all"):
        # NOTE: timestep_min must satisfy TWO constraints: (1) ds_shortterm accepts only
        # [1,2,3,4,5,6,10,12,15,20,30]; (2) nvrd() requires timestep_h <= 0.3 h (<= 18 min).
        # The coarsest value satisfying both is 15 min (0.25 h). The plan's original 60/30 both fail
        # a constraint (60 rejected by ds_shortterm; 30 = 0.5 h violates the nvRD guard).
        a = run_once("phaseA_coarse", timestep_min=15,
                     rad_params="-ab 1 -ad 256 -aa 0.2 -ar 32")
        print("PHASE A SUMMARY:", json.dumps(summarize(a), indent=2, default=str))
    if phase in ("B", "all"):
        # Representative run: default nvRD timestep (6 min = 0.1 h, satisfies both the ds_shortterm
        # set and the nvRD <=0.3 h guard) + default annual rad_params.
        b = run_once("phaseB_default", timestep_min=6,
                     rad_params="-ab 2 -ad 512 -aa 0.1 -ar 64")
        print("PHASE B SUMMARY:", json.dumps(summarize(b), indent=2, default=str))
