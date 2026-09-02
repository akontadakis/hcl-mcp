"""Locate Radiance binaries via HCL_RADIANCE_BIN or PATH.

Discovery is execution-free except for one benign, read-only `rtrace -version` probe
in `radiance_version()` (spec §3.2 requires a version in radiance_status). No Radiance
*workload* is ever run here — that stays in runner.py.
"""
import os
import subprocess

from hcl_platform import resolve_exe

# Binaries this *grid* phase actually needs. `available` keys off these.
_REQUIRED_GRID = ["oconv", "rtrace"]

# Full Radiance binary set per spec §6 (+ epw2wea from §5.11). Later phases
# (image/annual/weather) extend the live set; we probe-and-report all of them
# so `radiance_status()` mirrors spec §6, but only _REQUIRED_GRID gates `available`
# for this phase. rtrace/rpict are NOT in Lark's own Python (see provenance note);
# they belong to the standard Radiance pattern this port reconstructs.
_REQUIRED = ["oconv", "rtrace", "rpict", "pcomb", "gendaylit", "gendaymtx",
             "rfluxmtx", "dctimestep", "rcontrib", "pfilt", "pvalue",
             "getinfo", "falsecolor", "epw2wea", "obj2rad", "xform", "ies2rad"]

def resolve_bin(name):
    """Absolute path to a Radiance binary, or None. Checks HCL_RADIANCE_BIN first (with platform
    executable extensions, e.g. rtrace.exe on Windows), then PATH."""
    return resolve_exe(name, os.environ.get("HCL_RADIANCE_BIN"))

def radiance_version():
    """Best-effort Radiance version string via `rtrace -version`, or None if unavailable.

    A read-only probe (no scene, no side effects). Returns the first output line, e.g.
    'RADIANCE 5.4 2023-11-05 LBNL (5.4.4ee32974b1)'.
    """
    rtrace = resolve_bin("rtrace")
    if not rtrace:
        return None
    try:
        proc = subprocess.run([rtrace, "-version"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    text = (proc.stdout or proc.stderr or "").strip()
    return text.splitlines()[0].strip() if text else None

def geometry_available():
    """True when obj2rad and xform are both resolvable (gate for OBJ import live tests)."""
    return bool(resolve_bin("obj2rad") and resolve_bin("xform"))


def radiance_status():
    """Report which Radiance binaries are available, plus the Radiance version.

    Probes the full spec-§6 set (`_REQUIRED`) for found/missing reporting, but
    `available` keys only off the binaries this grid phase needs (`_REQUIRED_GRID`:
    oconv + rtrace). Later phases (image/annual/weather) consume the rest. `version`
    is a best-effort string (None if rtrace is absent or the probe fails).
    """
    found, missing = [], []
    for name in _REQUIRED:
        (found if resolve_bin(name) else missing).append(name)
    bin_dir = os.environ.get("HCL_RADIANCE_BIN")
    if not bin_dir:
        rtrace_path = resolve_bin("rtrace")  # capture once: avoid a re-resolve race on dirname()
        if rtrace_path:
            bin_dir = os.path.dirname(rtrace_path)
    # A1 integrity is reported here because this is where a caller checks the engine before
    # trusting a result. Text inspection only — the live probe costs a Radiance run, so it
    # stays opt-in via source_cal.check_a1(work_dir=...).
    from hcl_radiance.source_cal import inspect_source_cal, system_source_cal
    cal_path = system_source_cal(bin_dir)
    source_cal = inspect_source_cal(cal_path) if cal_path else {
        "a1_honored": None, "path": None,
        "reason": "could not locate the Radiance source.cal"}
    if source_cal["a1_honored"] is False:
        source_cal["impact"] = ("IES luminaires under-emit by their own candela scale, and "
                                "glare metrics collapse toward zero; the factor differs per "
                                "luminaire, so affected results must be re-run, not rescaled.")

    return {"available": all(resolve_bin(n) for n in _REQUIRED_GRID),
            "bin_dir": bin_dir, "version": radiance_version(), "found": found,
            "missing": missing, "source_cal": source_cal}
