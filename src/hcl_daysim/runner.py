"""Execute a sequence of Daysim steps, or emit the exact shell commands when Daysim is absent.

Same contract as hcl_radiance.runner.run_sequence (plan 03): steps are {cmd:[...], stdin?, stdout?}.
Thin wrapper over hcl_core.proc (audit XCUT-4/DAYSIM-7). ``_render`` is re-exported.
"""
import os

from hcl_core.proc import render as _render, run_sequence as _run_sequence

_REASON = ("Daysim not available; build it (build_daysim) or set HCL_DAYSIM_BIN, "
           "or run the commands yourself.")

def run_sequence(steps, work_dir, available, *, timeout=None):
    """steps: list of {cmd:[...], stdin?:path, stdout?:path}. Returns
    {ran, commands, reason?, outputs}. HCL_DAYSIM_BIN is prepended to PATH for execution so
    ds_shortterm/epw2wea resolve even when that dir isn't on PATH (DAYSIM-PATH); the emitted
    command plan stays bare-name and portable."""
    bin_dir = os.environ.get("HCL_DAYSIM_BIN")
    return _run_sequence(steps, work_dir, available, unavailable_reason=_REASON,
                         timeout=timeout, path_prepend=[bin_dir] if bin_dir else None)
