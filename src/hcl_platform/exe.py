"""Executable resolution that works on Windows (.exe/PATHEXT) and POSIX.

Fixes the Windows-blind lookup in the adapters' resolve_bin: a bare-name isfile() check never
matches rtrace.exe, and os.access(X_OK) is meaningless on Windows."""
import os
import shutil


def _pathext():
    """Executable extensions to try inside an explicit bin dir. [''] on POSIX (exact name)."""
    if os.name != "nt":
        return [""]
    raw = os.environ.get("PATHEXT", ".EXE;.BAT;.CMD;.COM")
    exts = [e if e.startswith(".") else "." + e
            for e in (x.strip() for x in raw.split(os.pathsep)) if e]
    return [""] + exts


def resolve_exe(name, bin_dir=None):
    """Absolute path to executable ``name``, or None.

    Tries ``bin_dir`` first (with platform executable extensions), then shutil.which (PATH +
    PATHEXT). On POSIX an explicit-dir hit must be +x; on Windows the X_OK check is skipped."""
    if bin_dir:
        for ext in _pathext():
            cand = os.path.join(bin_dir, name + ext)
            if os.path.isfile(cand) and (os.name == "nt" or os.access(cand, os.X_OK)):
                return cand
    return shutil.which(name)
