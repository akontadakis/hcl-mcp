"""Locate Daysim binaries via HCL_DAYSIM_BIN or PATH. No execution here (except best-effort version)."""
import os
import subprocess

from hcl_platform import resolve_exe

# Binaries this adapter needs. `available` keys off both being present.
_REQUIRED = ["ds_shortterm", "epw2wea"]

def resolve_bin(name):
    """Absolute path to a Daysim binary, or None. Checks HCL_DAYSIM_BIN first (with platform
    executable extensions, e.g. ds_shortterm.exe on Windows), then PATH."""
    return resolve_exe(name, os.environ.get("HCL_DAYSIM_BIN"))

def _version(ds_path):
    """Best-effort Daysim version string. ds_shortterm has no --version; return None on any failure."""
    try:
        proc = subprocess.run([ds_path], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, timeout=5)
        text = proc.stdout.decode("utf-8", "ignore")
        for line in text.splitlines():
            low = line.lower()
            # Skip error/usage diagnostics — ds_shortterm with no args prints a path-prefixed
            # "fatal error - header file missing" line, and the path itself contains "daysim",
            # which would otherwise be returned as the version (DEF-8).
            if any(bad in low for bad in ("fatal", "error", "missing", "usage", "cannot", "no such")):
                continue
            if "DAYSIM" in line.upper() or "version" in low:
                return line.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return None

def daysim_status():
    """Report Daysim availability.

    Returns {available, bin_dir, version, found:[ds_shortterm,epw2wea], missing:[...]}.
    `available` is True only when BOTH ds_shortterm and epw2wea resolve.
    """
    found, missing = [], []
    for name in _REQUIRED:
        (found if resolve_bin(name) else missing).append(name)
    bin_dir = os.environ.get("HCL_DAYSIM_BIN")
    ds = resolve_bin("ds_shortterm")
    if not bin_dir and ds:
        bin_dir = os.path.dirname(ds)
    return {"available": all(resolve_bin(n) for n in _REQUIRED),
            "bin_dir": bin_dir,
            "version": _version(ds) if ds else None,
            "found": found, "missing": missing}

def _available():
    """Convenience used by the workflow/build modules (mirrors hcl_radiance.grid._available)."""
    return daysim_status()["available"]
