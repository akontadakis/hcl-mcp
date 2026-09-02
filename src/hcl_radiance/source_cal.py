"""Detect (and shim around) a Radiance build that drops the ies2rad `A1` candela scale.

`ies2rad` writes an IES file's candela scale into the scene as the `brightdata` argument
`A1`, and `source.cal`'s `corr`/`flatcorr` are responsible for applying it. Some builds
resolve those to a compiled `source_corr` that ignores `A1`, so every IES luminaire emits
at unit scale: a room reads 34 lx where it should read 494 lx, with no error at any stage,
and `evalglare` reports UGR 0 because the sources fall below its detection threshold.

The under-emission equals the luminaire's OWN candela scale — 14.4x for one fixture, 2.07x
for another — so an affected result cannot be repaired by rescaling; it must be re-run.

Nothing here writes to the Radiance installation. The correction is a patched `source.cal`
placed in a directory prepended to RAYPATH, which Radiance resolves ahead of the system
copy. That is reversible by dropping the directory and needs no elevated privileges.
"""
import os
import re
import subprocess

from hcl_radiance.discover import resolve_bin

# `corr(v) = noneg(if(AC-.5, A1*v, v))` — the stock definition. AC is the real-argument
# count (1 for ies2rad brightdata), so the true branch applies A1.
_A1_APPLIED = re.compile(r"\bA1\s*\*")
_DEFN = re.compile(r"^\s*(corr|flatcorr)\s*\(")


def _strip_comments(text):
    """Remove Radiance { } comments, which nest."""
    out, depth = [], 0
    for ch in text:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(ch)
    return "".join(out)


def inspect_source_cal(path):
    """Report whether `path`'s corr/flatcorr apply A1. Text inspection only, no Radiance run.

    Returns {a1_honored, path, reason}. `a1_honored` is None — never False — when the file
    cannot be read, so an unreadable install is reported as unknown rather than as a defect,
    and never as a pass.

    Radiance takes the LAST definition of a function, so a file that delegates to
    `source_corr` early and redefines `corr` explicitly later does honor A1. That is exactly
    how the shim works, and why this reads the final definition rather than the first match.
    """
    try:
        with open(path, "r", errors="replace") as fh:
            text = fh.read()
    except OSError as exc:
        return {"a1_honored": None, "path": path, "reason": f"cannot read source.cal: {exc}"}

    # Accumulate each definition to its terminating ';' rather than reading one line: a
    # definition wrapped across lines would otherwise lose its body and be misread as not
    # applying A1, raising a loud "your engine is broken" error on a healthy install.
    latest, current, name = {}, None, None
    for line in _strip_comments(text).splitlines():
        if current is None:
            m = _DEFN.match(line)
            if not m:
                continue
            current, name = line, m.group(1)
        else:
            current += " " + line.strip()
        if ";" in current:
            latest[name] = current
            current, name = None, None
    if not latest:
        return {"a1_honored": None, "path": path,
                "reason": "no corr/flatcorr definition found in source.cal"}

    # `flatcorr` is what ies2rad brightdata actually names, so it is the one that decides.
    # It usually delegates to `corr` rather than applying A1 itself, so an A1 in either its
    # own body or in the corr it calls counts.
    deciding = latest.get("flatcorr") or latest["corr"]
    honored = bool(_A1_APPLIED.search(deciding))
    if not honored and "flatcorr" in latest and re.search(r"\bcorr\s*\(", latest["flatcorr"]):
        honored = bool(_A1_APPLIED.search(latest.get("corr", "")))
    return {"a1_honored": honored, "path": path,
            "reason": ("corr/flatcorr apply the A1 multiplier" if honored else
                       "corr/flatcorr do not apply A1 (delegated to the built-in source_corr); "
                       "IES luminaires will under-emit by their candela scale")}


# A minimal ies2rad-shaped luminaire: a 0.3 x 0.3 m flat emitter at z = 3 m, with the
# brightdata A1 argument written as {A1} for substitution. Deliberately not a real IES
# file — the probe tests the ENGINE's handling of A1, so the distribution is irrelevant
# and a flat one keeps the geometry trivial and the run under a second.
_PROBE_DAT = """\
2
0 90 2
0 360 2

\t1\t1
\t1\t1
"""

_PROBE_RAD = """\
void brightdata probe_dist
5 flatcorr probe.dat source.cal src_phi4 src_theta
0
1 {a1}

probe_dist light probe_light
0
0
3 1 1 1

probe_light polygon probe.geo
0
0
12
\t-0.15\t-0.15\t3
\t-0.15\t0.15\t3
\t0.15\t0.15\t3
\t0.15\t-0.15\t3
"""


def _system_lib_dir():
    """The Radiance installation's lib dir (<bin_dir>/../lib), or "" if not locatable."""
    rtrace = resolve_bin("rtrace")
    if not rtrace:
        return ""
    candidate = os.path.join(os.path.dirname(os.path.dirname(rtrace)), "lib")
    return candidate if os.path.isdir(candidate) else ""


def _probe_once(work_dir, a1, env):
    """Irradiance at the origin under the probe luminaire scaled by `a1`, or None."""
    rad = os.path.join(work_dir, f"probe_{a1}.rad")
    oct_path = os.path.join(work_dir, f"probe_{a1}.oct")
    with open(rad, "w") as fh:
        fh.write(_PROBE_RAD.format(a1=a1))
    try:
        with open(oct_path, "wb") as out:
            subprocess.run([resolve_bin("oconv"), rad], stdout=out, stderr=subprocess.PIPE,
                           cwd=work_dir, env=env, timeout=30, check=True)
        proc = subprocess.run([resolve_bin("rtrace"), "-I", "-h", "-w", oct_path],
                              input="0 0 0 0 0 1\n", capture_output=True, text=True,
                              cwd=work_dir, env=env, timeout=30, check=True)
    except (OSError, subprocess.SubprocessError):
        return None
    parts = proc.stdout.split()
    if len(parts) < 3:
        return None
    try:
        return sum(float(p) for p in parts[:3]) / 3.0
    except ValueError:
        return None


def probe_a1_honored(work_dir, *, raypath=None):
    """Measure whether this Radiance build applies A1, by scaling it and comparing.

    Runs the same luminaire twice with A1 differing by 10x. A build that honors A1 returns
    10x the irradiance; one that drops it returns the same number both times. This is the
    check `inspect_source_cal` cannot make, because the defect lives in the compiled
    `source_corr` the text delegates to rather than in the text itself.

    `raypath` prepends a directory to RAYPATH, which is how the shim is verified.
    Returns {ran, a1_honored, ratio, reason}; `ran` is False when Radiance is absent or the
    probe could not complete, and `a1_honored` is then None rather than False.
    """
    if not (resolve_bin("oconv") and resolve_bin("rtrace")):
        return {"ran": False, "a1_honored": None, "ratio": None,
                "reason": "Radiance (oconv/rtrace) not available; cannot probe"}

    os.makedirs(work_dir, exist_ok=True)
    with open(os.path.join(work_dir, "probe.dat"), "w") as fh:
        fh.write(_PROBE_DAT)

    # The system lib MUST stay on RAYPATH: shadowing source.cal is the whole mechanism, but
    # Radiance still loads rayinit.cal and friends from the installation. Prepending rather
    # than replacing is what makes the shim an override instead of a broken environment.
    env = {**os.environ, "RAYPATH": os.pathsep.join(
        [d for d in ([raypath] if raypath else []) + [work_dir, _system_lib_dir(),
                                                      os.environ.get("RAYPATH", "")] if d])}

    low = _probe_once(work_dir, 1.0, env)
    high = _probe_once(work_dir, 10.0, env)
    if not low or not high:
        return {"ran": False, "a1_honored": None, "ratio": None,
                "reason": "probe did not produce a usable reading"}

    ratio = high / low
    honored = ratio > 5.0  # 10x when applied, 1x when dropped; nothing lands between.
    return {"ran": True, "a1_honored": honored, "ratio": round(ratio, 4),
            "reason": ("A1 scales the emitted intensity as expected" if honored else
                       "changing A1 did not change the result: this build drops the "
                       "ies2rad candela scale, so IES luminaires under-emit")}


# The explicit pre-source_corr correction formulas. Radiance takes the LAST definition of a
# function, and RAYPATH resolves source.cal to the FIRST directory that has one, so a file
# carrying these overrides the system copy without that copy being touched. `AC` is the
# real-argument count (1 for ies2rad brightdata), so the true branch applies A1.
_SHIM_SOURCE_CAL = """\
{ hcl-mcp A1 shim. Some Radiance builds resolve corr/flatcorr to a compiled source_corr
  that ignores the ies2rad brightdata A1 (candela-scale) argument, so IES luminaires emit
  at unit scale and every electric-lighting result is low by the luminaire's own candela
  scale, with no error raised. These explicit definitions restore A1.

  This file is placed on RAYPATH ahead of the Radiance installation, which is left
  untouched; remove the directory to revert. Sky paths (gensky/gendaymtx) never use A1
  and are unaffected either way. }

boxprojection = abs(Dx)*A3*A4 + abs(Dy)*A2*A4 + abs(Dz)*A2*A3;
lboxprojection = ( noneg(abs(Px-Dx*Ts)-A2/2)*A3*A4 + noneg(abs(Py-Dy*Ts)-A3/2)*A2*A4 + noneg(abs(Pz-Dz*Ts)-A4/2)*A2*A3 ) / Ts;
cylprojection = A2*A3*sqrt(1-Dz*Dz) + PI/4*A2*A2*abs(Dz);
corr(v) = noneg(if(AC-.5, A1*v, v));
flatcorr(v) = corr(v) / Rdot;
boxcorr(v) = noneg(A1*v) / boxprojection;
lboxcorr(v) = noneg(A1*v) / lboxprojection;
cylcorr(v) = noneg(A1*v) / cylprojection;
"""


def write_shim(shim_dir, *, base=None):
    """Write a source.cal that applies A1 into `shim_dir`, and return that directory.

    Writes ONLY inside `shim_dir`. The Radiance installation is never modified, so this
    needs no elevated privileges and is undone by deleting the directory. Put the returned
    path at the front of RAYPATH and Radiance resolves this source.cal instead of the
    system one.

    RAYPATH resolution takes the FIRST file of a given name, not the union of all of them,
    so the shim must be a COMPLETE source.cal: it copies the installation's file and appends
    the corrected definitions, which win because Radiance takes the last definition of a
    function. Writing the overrides alone would shadow everything else the real file
    defines — `src_theta` among them — and break the scene rather than fix it.

    Prefer this over patching the install: a patched install is shared by every tool on the
    machine and is silently lost when Radiance is upgraded or rebuilt.
    """
    source = base or system_source_cal()
    if not (source and os.path.exists(source)):
        raise RuntimeError(
            f"cannot locate the Radiance source.cal to base the shim on (tried {source!r}). "
            "Writing the overrides alone would shadow the real file and remove src_theta and "
            "every other definition, so no scene would render at all. Set RAYPATH or "
            "HCL_RADIANCE_BIN so the installation can be found, or pass base= explicitly.")
    with open(source, "r", errors="replace") as fh:
        original = fh.read().rstrip() + "\n"

    # A truncated or unexpected base is as dangerous as a missing one and reads as success,
    # so confirm the file really is a source.cal before shadowing the installation with it.
    if "src_theta" not in original:
        raise RuntimeError(
            f"{source!r} does not define src_theta, so it is not a complete Radiance "
            "source.cal; shadowing the installation with it would break every scene.")

    os.makedirs(shim_dir, exist_ok=True)
    with open(os.path.join(shim_dir, "source.cal"), "w") as fh:
        fh.write(original + _SHIM_SOURCE_CAL)
    return shim_dir


def system_source_cal(bin_dir=None):
    """Best-effort path to the Radiance installation's source.cal, or None.

    Looks in RAYPATH first (which is what Radiance itself consults), then at
    <bin_dir>/../lib for the install the binaries belong to.
    """
    for entry in os.environ.get("RAYPATH", "").split(os.pathsep):
        if entry and os.path.exists(os.path.join(entry, "source.cal")):
            return os.path.join(entry, "source.cal")
    if not bin_dir:
        rtrace = resolve_bin("rtrace")
        bin_dir = os.path.dirname(rtrace) if rtrace else None
    if bin_dir:
        candidate = os.path.join(os.path.dirname(bin_dir), "lib", "source.cal")
        if os.path.exists(candidate):
            return candidate
    return None


def check_a1(work_dir=None, *, bin_dir=None):
    """Report this build's A1 handling: text inspection, plus a live probe when possible.

    The two layers answer different questions. Inspection is instant and needs no Radiance,
    but reads only what the file says; the probe measures what the engine does, which is the
    only way to catch a build whose text delegates to a compiled source_corr that ignores
    A1. The probe's verdict wins when the two disagree, since it is the one that measured.

    Returns {a1_honored, source_cal, inspected, probed, severity, fix}. `a1_honored` is None
    when neither layer could reach a verdict — never False, so an install this cannot read
    is reported as unknown rather than as broken.
    """
    path = system_source_cal(bin_dir)
    inspected = inspect_source_cal(path) if path else {
        "a1_honored": None, "path": None, "reason": "could not locate the Radiance source.cal"}
    probed = probe_a1_honored(work_dir) if work_dir else {
        "ran": False, "a1_honored": None, "ratio": None,
        "reason": "no work_dir given; text inspection only"}

    verdict = probed["a1_honored"] if probed.get("ran") else inspected["a1_honored"]
    out = {"a1_honored": verdict, "source_cal": path,
           "inspected": inspected, "probed": probed,
           "severity": "ok" if verdict else ("error" if verdict is False else "unknown")}
    if verdict is False:
        out["detail"] = ("This Radiance build drops the ies2rad A1 candela scale: every IES "
                         "luminaire under-emits by its own candela scale, and glare metrics "
                         "collapse toward zero because the sources fall below evalglare's "
                         "threshold. The factor differs per luminaire, so affected results "
                         "must be re-run, not rescaled.")
        out["fix"] = ("Call write_shim(<dir>) and put <dir> first on RAYPATH, or set "
                      "HCL_RADIANCE_SHIM=1 to have hcl-mcp do it automatically for every run.")
    return out


def shim_raypath(work_dir):
    """The shim directory to prepend to RAYPATH, or None when the shim is not enabled.

    Off by default: hcl-mcp does not alter the engine environment unless asked, because a
    silent override would make two machines disagree about what the same scene means. Set
    HCL_RADIANCE_SHIM=1 to enable it for every run on a build known to drop A1.
    """
    if os.environ.get("HCL_RADIANCE_SHIM", "").strip().lower() not in ("1", "true", "yes", "on"):
        return None
    return write_shim(os.path.join(work_dir, ".hcl_shim"))
