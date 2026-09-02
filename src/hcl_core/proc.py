"""Shared subprocess runner: execute a sequence of steps, or emit the exact shell
commands when the toolchain is absent.

This is the single implementation behind hcl_radiance.runner.run_sequence and
hcl_daysim.runner.run_sequence (audit XCUT-4/DAYSIM-7). It is the radiance
superset: it handles multi-stage pipes (a "|" token in cmd), a {"write": (path, text)}
file-write pseudo-step, per-step stdin/stdout redirection, and an optional per-step
timeout (seconds) passed to subprocess.run.

Cross-platform (hcl_platform compat): pipes run via chained Popen (NO shell), so nothing
depends on POSIX shell quoting or Unix-only shell builtins on Windows; write pseudo-steps
materialize via write_text (UTF-8 / LF) on the run path and render a reproducible here-doc
on the emit path — replacing the old Unix `cat`-heredoc / `printf` file-writes.
"""
import os
import shlex
import subprocess

from hcl_platform import write_text


def render(step):
    # {"write": (path, text)} pseudo-step: render a reproducible file-write for the emit path.
    if "write" in step:
        path, text = step["write"]
        op = ">>" if step.get("append") else ">"
        body = text if text.endswith("\n") else text + "\n"
        return f"cat {op} {shlex.quote(path)} <<'RAD'\n{body}RAD"
    parts = [tok if tok == "|" else shlex.quote(tok) for tok in step["cmd"]]
    line = " ".join(parts)
    if step.get("stdin"):
        line += f" < {shlex.quote(step['stdin'])}"
    if step.get("stdout"):
        op = ">>" if step.get("append") else ">"
        line += f" {op} {shlex.quote(step['stdout'])}"
    return line


def _run_pipe(cmd, work_dir, run_env, stdin_path, stdout_path, append, timeout):
    """Run an ``a | b | c`` chain via chained Popen (no shell). Binary handles throughout.

    Intermediate stages send stderr to DEVNULL (only the last stage's stderr is captured) so a
    chatty middle stage can't deadlock on an undrained stderr pipe. Returns (returncode,
    stderr_bytes); returncode is the FIRST non-zero across all stages (a failing upstream stage
    is surfaced, unlike a POSIX pipeline which reports only the last)."""
    stages, cur = [], []
    for tok in cmd:
        if tok == "|":
            stages.append(cur)
            cur = []
        else:
            cur.append(tok)
    stages.append(cur)
    infile = open(os.path.join(work_dir, stdin_path), "rb") if stdin_path else None
    outfile = (open(os.path.join(work_dir, stdout_path), "ab" if append else "wb")
               if stdout_path else None)
    procs = []
    try:
        prev = infile
        for i, stage in enumerate(stages):
            last = i == len(stages) - 1
            p = subprocess.Popen(
                stage, cwd=work_dir, env=run_env, stdin=prev,
                stdout=(outfile if last else subprocess.PIPE),
                stderr=(subprocess.PIPE if last else subprocess.DEVNULL))
            if prev is not None and prev is not infile:
                prev.close()  # let the upstream stage receive SIGPIPE
            prev = p.stdout
            procs.append(p)
        try:
            _, err = procs[-1].communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            for p in procs:
                p.kill()
            raise
        for p in procs[:-1]:
            p.wait()
        rc = next((p.returncode for p in procs if p.returncode not in (0, None)), 0)
        return rc, (err or b"")
    finally:
        if infile:
            infile.close()
        if outfile:
            outfile.close()


def run_sequence(steps, work_dir, available, *, unavailable_reason, timeout=None,
                 path_prepend=None, env_extra=None):
    """steps: list of {cmd:[...], stdin?:path, stdout?:path} or {"write": (path, text), append?}.
    A step whose cmd contains a "|" token runs as a shell-free Popen pipe. ``timeout`` (seconds,
    optional) is passed to each subprocess.run; on TimeoutExpired returns returncode 124.
    ``path_prepend`` (list of dirs) is prepended to PATH for EXECUTION only — the emitted
    ``commands`` stay bare-name/portable; this lets a binary that lives only in a discovery dir
    (e.g. HCL_RADIANCE_BIN / HCL_DAYSIM_BIN, not on PATH) be found at run time.
    ``env_extra`` (dict) overlays environment variables for EXECUTION only — used to prepend the
    Radiance A1 shim to RAYPATH without mutating the caller's environment.
    Returns {ran, commands, reason?|returncode, outputs|error|failed_step}."""
    commands = [render(s) for s in steps]
    if not available:
        return {"ran": False, "commands": commands,
                "reason": unavailable_reason,
                "outputs": [s["stdout"] for s in steps if s.get("stdout")]}
    os.makedirs(work_dir, exist_ok=True)
    run_env = None
    dirs = [d for d in (path_prepend or []) if d]
    if dirs or env_extra:
        run_env = {**os.environ, **(env_extra or {})}
        if dirs:
            run_env["PATH"] = os.pathsep.join(dirs + [os.environ.get("PATH", "")])
    for s in steps:
        try:
            if "write" in s:
                path, text = s["write"]
                write_text(os.path.join(work_dir, path), text, append=s.get("append", False))
                continue
            if "|" in s["cmd"]:
                rc, err = _run_pipe(s["cmd"], work_dir, run_env, s.get("stdin"),
                                    s.get("stdout"), s.get("append", False), timeout)
                if rc != 0:
                    return {"ran": True, "commands": commands, "returncode": rc,
                            "error": err.decode("utf-8", "ignore")[-2000:], "failed_step": render(s)}
                continue
            stdin = open(os.path.join(work_dir, s["stdin"]), "rb") if s.get("stdin") else None
            stdout = (open(os.path.join(work_dir, s["stdout"]), "ab" if s.get("append") else "wb")
                      if s.get("stdout") else None)
            try:
                proc = subprocess.run(s["cmd"], cwd=work_dir, stdin=stdin, stdout=stdout,
                                      env=run_env, stderr=subprocess.PIPE, timeout=timeout)
            finally:
                if stdin:
                    stdin.close()
                if stdout:
                    stdout.close()
        except subprocess.TimeoutExpired as e:
            err = e.stderr.decode("utf-8", "ignore")[-2000:] if isinstance(e.stderr, (bytes, bytearray)) \
                else f"timed out after {timeout}s"
            return {"ran": True, "commands": commands, "returncode": 124,
                    "error": err, "failed_step": render(s)}
        except OSError as e:
            # The command could not be STARTED at all - missing binary, not executable, bad
            # interpreter. subprocess raises instead of returning a code, and nothing further up
            # the chain (runner -> server) caught it, so it escaped as a raw traceback to the MCP
            # client while this function's contract promises an envelope. Reachable on a partial
            # Radiance install: `available` gates on oconv+rtrace only, so the gate says run and
            # then rpict/pcomb/gendaymtx are not there. 127 is the shell's command-not-found code.
            return {"ran": True, "commands": commands, "returncode": 127,
                    "error": f"{type(e).__name__}: {e}", "failed_step": render(s)}
        if proc.returncode != 0:
            return {"ran": True, "commands": commands, "returncode": proc.returncode,
                    "error": proc.stderr.decode("utf-8", "ignore")[-2000:], "failed_step": render(s)}
    return {"ran": True, "commands": commands, "returncode": 0,
            "outputs": [s["stdout"] for s in steps if s.get("stdout")]}
