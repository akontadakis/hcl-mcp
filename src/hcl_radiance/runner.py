"""Execute a sequence of Radiance steps, or emit the exact shell commands when Radiance is absent.

Thin wrapper over hcl_core.proc (audit XCUT-4/DAYSIM-7): the shared runner is the
radiance superset. ``_render`` is re-exported for callers/tests; ``parse_rtrace_res``
stays here.
"""
import os

from hcl_core.proc import render as _render, run_sequence as _run_sequence

_REASON = "Radiance not available; set HCL_RADIANCE_BIN or run the commands yourself."

def run_env_for(work_dir):
    """The environment Radiance steps run under: os.environ, plus the A1 shim when enabled.

    Returns the environment unchanged unless HCL_RADIANCE_SHIM is set, so the default is to
    leave the engine exactly as the machine configured it. When enabled, a corrected
    source.cal is written under work_dir and prepended to RAYPATH, which overrides the
    installation's copy for this run only — the install is never modified.
    """
    from hcl_radiance.source_cal import shim_raypath

    shim = shim_raypath(work_dir)
    if not shim:
        return dict(os.environ)
    existing = os.environ.get("RAYPATH", "")
    return {**os.environ,
            "RAYPATH": os.pathsep.join([shim] + ([existing] if existing else []))}


def run_sequence(steps, work_dir, available, *, timeout=None):
    """steps: list of {cmd:[...], stdin?:path, stdout?:path} or {"write": (path, text)}. A step
    whose cmd contains a "|" token runs as a shell-free Popen pipe. HCL_RADIANCE_BIN is prepended
    to PATH for execution so oconv/rtrace resolve even when that dir isn't on PATH; the emitted
    command plan stays bare-name and portable. Returns {ran, commands, reason?, outputs}."""
    bin_dir = os.environ.get("HCL_RADIANCE_BIN")
    from hcl_radiance.source_cal import shim_raypath

    env_extra = None
    shim = shim_raypath(work_dir) if available else None
    if shim:
        existing = os.environ.get("RAYPATH", "")
        env_extra = {"RAYPATH": os.pathsep.join([shim] + ([existing] if existing else []))}
    return _run_sequence(steps, work_dir, available, unavailable_reason=_REASON,
                         timeout=timeout, path_prepend=[bin_dir] if bin_dir else None,
                         env_extra=env_extra)

def parse_rtrace_res(text):
    """Parse standard Radiance rtrace '.res' output (the format Honeybee writes; not Lark-authored):
    first three numeric columns per non-empty line -> [[r,g,b], ...]."""
    rows = []
    for line in text.splitlines():
        toks = line.replace("\t", " ").split()
        if len(toks) < 3:
            continue
        try:
            rows.append([float(toks[0]), float(toks[1]), float(toks[2])])
        except ValueError:
            continue
    return rows
