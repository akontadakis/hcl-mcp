"""Pure builders for Radiance command lines (arg lists). No execution."""
import shlex

from hcl_platform import rad_path

# Sane Radiance irradiance defaults chosen by THIS port (NOT Lark-derived: Lark
# never sets rtrace ambient params). Callers override via rad_params.
DEFAULT_RTRACE_PARAMS = "-ab 2 -ad 512 -as 256 -aa 0.1 -ar 64 -lw 0.001"

# Below these, the indirect solve is preview-grade rather than converged. Calibrated on a real
# annual run: at -ab 2 -ad 512 ten of 45 work-plane points fell below the DA 0.50 threshold (worst
# 0.030) that better sampling lifted across it, moving sDA by 22 percentage points on unchanged
# geometry. The thresholds are deliberately loose — the aim is to catch "this is the fast preview"
# rather than to certify convergence, which only a parameter sweep can do.
_CONVERGED_AB = 3
_CONVERGED_AD = 2048


# --- Named ambient-quality presets -------------------------------------------------------------
# Values follow the standard Radiance parameter tables (Min / Fast / Accurate / Very accurate),
# restricted to the ambient group, which is what governs the indirect solve and therefore the
# runtime and the accuracy of every climate-based metric.
#
# WHY THESE EXIST. The rtrace default is a preview setting, and a caller who does not pass
# rad_params gets it by not choosing. On a validated annual run that default returned sDA 77.78%
# where a converged solve returned 100.00% on identical geometry: a 22-point difference in a
# headline metric, invisible in the result. Naming the levels makes the trade-off a decision.
#
# -aa is an ERROR TOLERANCE, so it decreases as quality rises, while -ab/-ad/-as/-ar increase.
# -as is kept near half of -ad, which is where extra super-samples still buy accuracy.
QUALITY_PRESETS = {
    "low": {
        "rad_params": "-ab 0 -ad 32 -as 0 -aa 0.4 -ar 8 -lw 0.05",
        "use_for": ("Geometry checks and direct-sun questions. No interreflection is computed at "
                    "all (-ab 0), so this is the right setting for verifying that a model is "
                    "assembled correctly, and for direct-only metrics such as ASE, which are "
                    "exact here because they never use the ambient calculation."),
        "caveat": ("NOT valid for any metric that depends on interreflected light. With -ab 0 an "
                   "interior point sees only what it sees directly, so illuminance away from the "
                   "window is severely understated and DA/sDA/UDI are meaningless."),
        "relative_cost": 1,
    },
    "medium": {
        "rad_params": "-ab 2 -ad 512 -as 256 -aa 0.2 -ar 32 -lw 0.01",
        "use_for": ("Draft studies and design iteration: comparing options, seeing where daylight "
                    "falls, checking trends. Two bounces capture the dominant interreflection in "
                    "a normal room."),
        "caveat": ("Preview-grade convergence. Absolute illuminance carries a few percent of "
                   "sampling noise, which matters disproportionately for THRESHOLD metrics: a "
                   "point near DA 0.5 can fall either side of it between runs. Compare options at "
                   "this level; do not publish sDA/UDI from it."),
        "relative_cost": 8,
    },
    "high": {
        "rad_params": "-ab 3 -ad 2048 -as 1024 -aa 0.15 -ar 128 -lw 0.005",
        "use_for": ("Reportable results: climate-based metrics (DA, sDA, UDI), compliance "
                    "checks, and any number that will be published or used for a decision. "
                    "Three bounces plus dense hemisphere sampling put threshold crossings on a "
                    "stable footing."),
        "caveat": ("Roughly an order of magnitude slower than medium. On an annual run over "
                   "thousands of timesteps, budget hours rather than minutes."),
        "relative_cost": 60,
    },
    "extra_high": {
        "rad_params": "-ab 5 -ad 4096 -as 2048 -aa 0.08 -ar 512 -lw 0.002",
        "use_for": ("Difficult daylighting where the indirect component dominates: deep plans, "
                    "light shelves, indirect or cove lighting, atria, and validation against "
                    "measurement. Five bounces are for cases where light reaches the sensor only "
                    "after several diffuse reflections."),
        "caveat": ("Very expensive, and past the point of diminishing returns for an ordinary "
                   "side-lit room, where it will agree with `high` to within its own noise. Use "
                   "it when the geometry justifies it, not as a default."),
        "relative_cost": 400,
    },
}

_QUALITY_ORDER = ["low", "medium", "high", "extra_high"]


def quality_params(level):
    """rad_params string for a named quality level. Raises ValueError naming the valid levels."""
    try:
        return QUALITY_PRESETS[level]["rad_params"]
    except KeyError:
        raise ValueError(
            f"unknown quality level {level!r}; choose one of {', '.join(_QUALITY_ORDER)}") from None


def quality_preset_table():
    """The presets as an ordered list of rows, for showing a caller their options up front."""
    return [{"name": n, **QUALITY_PRESETS[n]} for n in _QUALITY_ORDER]


def _rad_param(params, flag):
    """Value of a Radiance -flag in a parameter string, or None if absent/unparseable."""
    toks = (params or "").split()
    for i, t in enumerate(toks):
        if t == flag and i + 1 < len(toks):
            try:
                return float(toks[i + 1])
            except ValueError:
                return None
    return None


def ambient_convergence_note(params, *, direct_only_ok=False):
    """Warn when ambient settings are too coarse for a climate-based metric, else None.

    Returns a human-readable note, not an exception: coarse settings are a legitimate choice for
    a preview, and changing the shipped default underneath existing callers would silently move
    their published numbers. What is NOT legitimate is a sampling-limited result that looks
    converged, so the note travels with the result.

    `-ab 0` means no interreflection at all. Pass direct_only_ok=True when that is deliberate —
    the ASE pass and the internal direct sun pass — to suppress the note; otherwise it is reported
    as the most severe under-convergence, since a whole run at -ab 0 yields no valid DA/sDA/UDI.
    """
    ab = _rad_param(params, "-ab")
    ad = _rad_param(params, "-ad")
    if ab is None and ad is None:
        # No ambient flag at all leaves rtrace on its own default, which is -ab 0: the same
        # direct-only run as an explicit -ab 0, and the easiest one to make without noticing.
        ab = 0.0
    if ab is not None and ab <= 0:
        # -ab 0 computes NO interreflection. For a deliberately direct-only pass (ASE, and the
        # internal sun pass) that is exactly right and needs no warning. But as a whole-run
        # setting it is the most severe under-convergence there is, not the absence of a problem,
        # so it is reported as such — with different wording, because the fix is different: raise
        # the quality level rather than nudge a parameter.
        if direct_only_ok:
            return None
        return ("Ambient bounces are 0, so NO interreflected light is computed: an interior point "
                "sees only what it sees directly. Illuminance away from the aperture is severely "
                "understated and DA/sDA/UDI are not meaningful. Direct-only metrics (ASE) are "
                "unaffected and correct. Use quality level 'medium' or above for anything that "
                "depends on interreflection.")
    weak = []
    if ab is not None and ab < _CONVERGED_AB:
        weak.append(f"-ab {ab:g} (< {_CONVERGED_AB})")
    if ad is not None and ad < _CONVERGED_AD:
        weak.append(f"-ad {ad:g} (< {_CONVERGED_AD})")
    if not weak:
        return None
    return (f"Ambient sampling is preview-grade: {', '.join(weak)}. Indirect illuminance may be "
            "under-converged, which moves threshold-crossing metrics (DA, sDA, UDI) far more than "
            "it moves means — on a validation run this shifted sDA by 22 percentage points on "
            "unchanged geometry. Direct-only metrics (ASE) are unaffected. Report the ambient "
            "parameters alongside any metric computed at these settings.")

def build_oconv(scene_files, out_oct):
    """oconv -f <files...> > out_oct  (returns args; redirection handled by the runner).

    User-supplied scene paths are forward-slash-normalized (Windows-safe); relative generated
    work_dir names (materials/sky) are left untouched so they still resolve against cwd=work_dir.
    Order: modifiers/materials + sky BEFORE geometry that references them.
    """
    return ["oconv", "-f", *[rad_path(f) for f in scene_files]]  # stdout -> out_oct (runner redirects)

def build_rtrace(oct_file, rad_params=DEFAULT_RTRACE_PARAMS):
    """rtrace for per-point irradiance (RGB). Reads points on stdin, writes 'R G B' per line.

    Flags: -I+ irradiance at the measurement point; -h- suppress the info header (cleaner
    .res output); -ov output the value (radiance/irradiance). NB: -ov (value), NOT -oV
    (contribution) — rtrace warns that -oV requires trace mode, though both coincide for -I.
    """
    return ["rtrace", "-I+", "-h-", *shlex.split(rad_params), "-ov", oct_file]

def pts_to_text(points):
    """points: iterable of [x,y,z,dx,dy,dz] -> Radiance points text (one per line).

    Every row must be exactly six numbers. rtrace reads its input as one free stream of
    numbers, so a short row is not an error to it: four 3-column rows become two rays, at the
    wrong places, and the result comes back plausible and half as long.
    """
    lines = []
    for i, row in enumerate(points):
        values = list(row)
        ok = len(values) == 6
        if ok:
            try:
                for value in values:
                    float(value)
            except (TypeError, ValueError):
                ok = False
        if not ok:
            raise ValueError(f"sensor row {i} is {values!r}; every row must be six numbers, "
                             "x y z dx dy dz (a position and a direction)")
        lines.append(" ".join(str(c) for c in values))
    return "\n".join(lines) + "\n"
