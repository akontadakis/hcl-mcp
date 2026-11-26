"""Command text for a person to paste, quoted for the shell of the platform.

Commands are RUN as argument lists and never pass through a shell. These helpers are for the
text shown instead: an emitted plan, an error message, a `!command` line in a Radiance file.
POSIX shells take single quotes (shlex); cmd.exe does not, and takes double quotes.
"""
import os
import shlex
import subprocess


def _windows(windows):
    return os.name == "nt" if windows is None else windows


def shell_join(argv, windows=None):
    """One command line from an argument list."""
    argv = [str(a) for a in argv]
    return subprocess.list2cmdline(argv) if _windows(windows) else shlex.join(argv)


def shell_quote(text, windows=None):
    """One argument (a path after `>`), quoted only if it needs it."""
    text = str(text)
    return subprocess.list2cmdline([text]) if _windows(windows) else shlex.quote(text)
