"""Cross-platform compat helpers (paths / exe resolution / text I/O). Dependency-free (stdlib only)."""
from .paths import rad_path
from .exe import resolve_exe
from .textio import read_text, write_text

__all__ = ["rad_path", "resolve_exe", "read_text", "write_text"]
