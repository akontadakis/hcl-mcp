"""Annual 2-phase DDS command builders — verbatim from Lark 'Colored Sky For Annual Irradiance'."""
import filecmp
import os
import shutil
import shlex

# rfluxmtx/rcontrib error out if these Reinhart .cal files are not findable. The Lark source
# COPIES them from C:\Radiance\lib into the project folder before running:
#   reinhartb.cal (source line 126, before rfluxmtx), reinsrc.cal (source line 160, before the
#   cnt|rcalc solar-disc step), reinhart.cal (source line 183, before rcontrib).
# Source comment: "if it is not there rfluxmtx gives an error".
REINHART_CAL_FILES = ("reinhartb.cal", "reinsrc.cal", "reinhart.cal")

def _radiance_lib_dir():
    """Best-effort Radiance lib dir: <bin_dir>/../lib (from discovery) or the first RAYPATH entry."""
    try:
        from hcl_radiance.discover import radiance_status
        bin_dir = radiance_status().get("bin_dir")
    except Exception:
        bin_dir = None
    if bin_dir:
        cand = os.path.normpath(os.path.join(bin_dir, os.pardir, "lib"))
        if os.path.isdir(cand):
            return cand
    for entry in os.environ.get("RAYPATH", "").split(os.pathsep):
        if entry and os.path.isdir(entry):
            return entry
    return None

def materials_files(materials):
    """Normalize a scene's `materials` to a flat list of oconv file args. Accepts a space-joined
    string ("a.rad b.rad") OR a list of paths (what import_geometry's material_sets return). A single
    path stays a 1-element list, so existing space-string callers emit byte-identical commands (DEF-3).
    """
    return list(materials) if isinstance(materials, (list, tuple)) else str(materials).split()


def missing_cal_files(lib_dir=None):
    """Required Reinhart .cal files absent from the Radiance lib (empty list = all present).

    Some Radiance builds (e.g. the 6.1a install seen in validation) ship reinhart/reinhartb but not
    reinsrc.cal, which the 2-phase DDS solar-disc step needs. Callers use this to degrade to the
    emit path with an honest reason instead of failing mid-run at the `cp` step (DEF-4). When no lib
    dir can be located at all, every required file counts as missing.
    """
    lib = lib_dir if lib_dir is not None else _radiance_lib_dir()
    if not lib:
        return list(REINHART_CAL_FILES)
    return [name for name in REINHART_CAL_FILES if not os.path.isfile(os.path.join(lib, name))]


def stage_cal_files(work_dir, run=True):
    """Mirror the source's guard: ensure reinhartb.cal/reinsrc.cal/reinhart.cal are in work_dir.

    Returns a list of describe-able 'copy' step dicts for the emit (run=False) path so the user
    can reproduce. When run=True, also copies any found .cal that is missing from work_dir or
    differs from the installed one: a copy left by an older Radiance must not outlive it.
    """
    lib = _radiance_lib_dir()
    steps = []
    for name in REINHART_CAL_FILES:
        src = os.path.join(lib, name) if lib else name
        dst = os.path.join(work_dir, name)
        steps.append({"cmd": ["cp", src, dst], "stage_cal": name})
        if run and lib and os.path.isfile(src) and not (
                os.path.isfile(dst) and filecmp.cmp(src, dst, shallow=False)):
            shutil.copyfile(src, dst)
    return steps

_SKYGLOW = """#@rfluxmtx u=+Y h=u
void glow groundglow
0
0
4 1 1 1 0

groundglow source ground
0
0
4 0 0 -1 180

#@rfluxmtx u=+Y h=r1
void glow skyglow
0
0
4 1 1 1 0

skyglow source skydome
0
0
4 0 0 1 180
"""

def skyglow_rad():
    """The rfluxmtx-annotated sky/ground glow definition (neutral; color applied via gendaymtx -c)."""
    return _SKYGLOW

# One solar disc per Reinhart MF:6 SKY bin. reinsrc.cal's own Rmax is the count:
#   Rmax = raccum(7*MF + 1) = 5185 at MF:6, i.e. bins 1..5185.
# reinhart.cal's Nrbins = Rmax + 1 = 5186, because rcontrib's bin 0 is the GROUND. So the
# disc count is 5185 and the coefficient matrix has 5186 columns; the two differ by one by
# construction and neither is a typo for the other.
# The Lark source's 5165 is simply wrong: it omits bins 5166..5185, the twenty near-zenith
# patches at altitude >= 87.9 deg, which then carry a sun with no disc to receive it. Verified
# against the install: `rcalc -e MF:6 -f reinsrc.cal -e '$1=Rmax'` -> 5185.
SUN_DISC_COUNT = 5185

def suns_rad_steps(out="suns.rad"):
    """Steps to build one solar-disc source per Reinhart MF:6 sky bin (accurate-sun)."""
    return [
        {"cmd": ["echo", "void light solar 0 0 3 1e6 1e6 1e6"], "stdout": out},
        # NOTE: the -o format must NOT carry literal double-quotes. render() shell-quotes each token,
        # so a quoted format would land literal `"` chars in suns.rad and oconv would read the whole
        # line as one quoted modifier ("undefined modifier"). Keep it bare; the shell quoting is added
        # at render time. (Latent until reinsrc.cal was installed — the cp guard failed earlier before.)
        {"cmd": ["cnt", str(SUN_DISC_COUNT), "|", "rcalc", "-e", "MF:6", "-f", "reinsrc.cal",
                 "-e", "Rbin=recno",
                 "-o", 'solar source sun 0 0 4 ${Dx} ${Dy} ${Dz} 0.533'], "stdout": out, "append": True},
    ]

def build_rfluxmtx_sky(n_points, rad_params, sky_rad, oct_file, points, out_mtx):
    """rfluxmtx daylight-coefficient matrix for the sky."""
    return ["rfluxmtx", "-I+", "-y", str(n_points), *shlex.split(rad_params), "-", sky_rad, "-i", oct_file]
    # stdin = points, stdout = out_mtx (runner redirects)

def build_gendaymtx_sky(wea, sky_color, out_mtx):
    """Colored sky matrix (145 patches): gendaymtx -m 1 -s -c R G B."""
    r, g, b = sky_color
    return ["gendaymtx", "-m", "1", "-s", "-c", str(r), str(g), str(b), wea]

def build_rcontrib_sun(n_points, rad_params, oct_sun, points, out_mtx):
    """Accurate-sun coefficient matrix via rcontrib over the solar discs.

    GAP 2 — v1 uses ASCII output, NOT the source's `-faf` (binary float). The source line 186 has
    `rcontrib -I+ -y ... -faf -e MF:6 -f reinhart.cal -b rbin -bn Nrbins -m solar ...`, which makes
    the sun-side dctimestep `.ill` BINARY float. Our `parse_ill` is an ASCII row parser, so emitting
    `-faf` here would feed it binary it can't read. We deliberately DROP `-faf` so the sun `.ill`
    is ASCII and parses with the same `parse_ill` as the sky path.
    Tradeoff: this diverges from the source flag; the numbers are identical (only the encoding
    differs) and the per-timestep data volume is tiny, so ASCII is the simpler, safe v1 choice.
    If a future version restores `-faf` for speed/size, `parse_ill` must gain a binary-float branch
    (read 3×4-byte little-endian floats per timestep via `struct`).
    """
    return ["rcontrib", "-I+", "-y", str(n_points), *shlex.split(rad_params), "-e", "MF:6",
            "-f", "reinhart.cal", "-b", "rbin", "-bn", "Nrbins", "-m", "solar", oct_sun]

def build_gendaymtx_sun(wea, out_mtx):
    """Neutral sun matrix: gendaymtx -5 0.533 -d -m 6 (no -c; sun stays neutral)."""
    return ["gendaymtx", "-5", "0.533", "-d", "-m", "6", wea]

def build_dctimestep(coeff_mtx, sky_or_sun_mtx):
    """dctimestep <coeff> <sky/sun> -> annual .ill (runner redirects stdout)."""
    return ["dctimestep", coeff_mtx, sky_or_sun_mtx]

def build_oconv_annual(scene_files, frozen=False):
    """oconv for the annual workflow. The shared hcl_radiance.commands.build_oconv hardcodes -f,
    but the source uses -f ONLY for the sun octree:
      sky octree -> `oconv {materials} {geometry} > {oct}`            (NO -f)   [source line 122]
      sun octree -> `oconv -f {materials} {geometry} {suns} > {octSun}` (WITH -f) [source line 177]
    So build the sky octree with frozen=False and the sun octree with frozen=True.
    """
    return ["oconv", *(["-f"] if frozen else []), *scene_files]  # stdout -> oct (runner redirects)
