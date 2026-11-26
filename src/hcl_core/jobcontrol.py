"""Job control: let a running simulation be stopped, and let it say where it is.

A *job* is one unit of work somebody may give up on -- in the MCP server, one tool call. The
caller opens a job; everything that runs inside it, in this thread or in a worker thread that
inherited the context, can then

  * be cancelled: `job.cancel.set()`, or simply leaving the `with job():` block, makes the
    command currently being waited on die, together with the children it started itself
    (`rfluxmtx` and `rtrace -n` fork), and makes the next `step()` raise `JobCancelled`;
  * report progress: `step("rtrace (3/15)")` hands a running count and a message to the job's
    `on_step` callback.

Outside a job nothing changes. `run()` is then exactly `subprocess.run`, no process group is
created, and `step()` does nothing -- so library use, scripts and a terminal Ctrl-C behave as
they always did.

The module knows nothing about MCP. The server owns the mapping from a job to a client request
(see `hcl_mcp.server`): a cancellation notice, a timeout, a `tasks/cancel`, or the client going
away all end the tool call, which leaves the job.
"""
import atexit
import contextlib
import contextvars
import os
import signal
import subprocess
import threading
import time

_POLL_SECONDS = 0.1    # how often a waiting thread looks at the cancel flag
_GRACE_SECONDS = 2.0   # between asking a process to stop and killing it


class JobCancelled(BaseException):
    """The job this work belongs to was cancelled.

    A BaseException, like `asyncio.CancelledError`: the many `except Exception` blocks between
    a subprocess and a tool's return value must not mistake "stop" for a failed step and carry
    on with the next one.
    """


class Job:
    def __init__(self, on_step=None):
        self.cancel = threading.Event()
        self.on_step = on_step
        self.steps = 0


_JOB = contextvars.ContextVar("hcl_job", default=None)

# Every process started inside a job, until it has been waited for. Read by the exit hook.
_LIVE = set()
# Re-entrant: `terminate_all` also runs from the server's signal handler, on the main thread,
# which may be the very thread that holds this lock when the signal arrives.
_LIVE_LOCK = threading.RLock()


def current():
    """The job this code runs in, or None."""
    return _JOB.get()


@contextlib.contextmanager
def job(on_step=None):
    """Open a job. Leaving the block cancels it, however the block is left.

    That is deliberate: when the block is left normally all the work is finished and the flag
    is inert; when it is left because the caller was cancelled, the worker thread it abandoned
    is still running, and the flag is how that thread finds out.
    """
    this = Job(on_step)
    token = _JOB.set(this)
    try:
        yield this
    finally:
        this.cancel.set()
        _JOB.reset(token)


def raise_if_cancelled():
    this = _JOB.get()
    if this is not None and this.cancel.is_set():
        raise JobCancelled()


def step(message):
    """Mark the start of one step of the job: stop here if cancelled, else report it.

    The count runs over the whole job, not over one command sequence, so a tool that runs two
    sequences still reports a number that only ever goes up (MCP requires that of progress).
    A failing callback is ignored: progress is a courtesy and must never break a run.
    """
    this = _JOB.get()
    if this is None:
        return
    if this.cancel.is_set():
        raise JobCancelled()
    this.steps += 1
    if this.on_step is not None:
        try:
            this.on_step(this.steps, message)
        except Exception:
            pass


# ---- processes ----

def popen(cmd, **kwargs):
    """`subprocess.Popen`. Inside a job the process leads its own group, so that stopping it
    also stops whatever it forked, and it is tracked until waited for."""
    if _JOB.get() is None:
        return subprocess.Popen(cmd, **kwargs)
    if os.name == "posix":
        kwargs.setdefault("start_new_session", True)
    else:
        kwargs["creationflags"] = (kwargs.get("creationflags", 0)
                                   | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    process = subprocess.Popen(cmd, **kwargs)
    process._hcl_own_group = True
    with _LIVE_LOCK:
        _LIVE.add(process)
    return process


def _signal_group(process, sig):
    try:
        os.killpg(process.pid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def _terminate(process):
    """Stop a process and, when it leads its own group, everything in that group.

    A process that has already finished is left alone, group included: once it has been waited
    for, its pid can belong to somebody else, and signalling "its" group could kill an unrelated
    program of the same user.
    """
    if process.poll() is not None:
        return
    own_group = getattr(process, "_hcl_own_group", False)
    if own_group and os.name == "posix":
        _signal_group(process, signal.SIGTERM)
    elif own_group:
        # Windows: terminate() would leave the children running; taskkill /T takes the tree.
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        process.terminate()
    try:
        process.wait(timeout=_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        if own_group and os.name == "posix":
            _signal_group(process, signal.SIGKILL)   # leader and group together
        else:
            process.kill()
        process.wait()
        return
    if own_group and os.name == "posix":
        # The leader went quietly and was reaped a moment ago; anything in its group that
        # ignored SIGTERM goes now.
        _signal_group(process, signal.SIGKILL)


def stop(processes):
    """Stop these processes and forget them. For a chain that could not be completed: the
    stages that did start must not be left running, in or out of a job."""
    for process in processes:
        _terminate(process)
    with _LIVE_LOCK:
        _LIVE.difference_update(processes)


def _stop_and_raise_if_due(this, processes, deadline, timeout):
    """While waiting on a chain: stop every stage and raise, if cancelled or out of time."""
    if this is not None and this.cancel.is_set():
        for process in processes:
            _terminate(process)
        raise JobCancelled()
    if deadline is not None and time.monotonic() >= deadline:
        for process in processes:
            _terminate(process)
        last = processes[-1]
        try:
            out, err = last.communicate(timeout=_GRACE_SECONDS)
        except (subprocess.TimeoutExpired, ValueError):
            out, err = None, None
        raise subprocess.TimeoutExpired(last.args, timeout, output=out, stderr=err)


def communicate(processes, *, timeout=None):
    """Wait for a chain of processes; collect the LAST one's output: `Popen.communicate`.

    While waiting it watches the job's cancel flag and the timeout -- for every stage, not only
    the last: in `a | b`, b can finish while a is still busy, and that wait has to be stoppable
    too. On either, EVERY stage is stopped first; then `JobCancelled` or
    `subprocess.TimeoutExpired` is raised. Returns (stdout, stderr) of the last process once
    all stages have ended.
    """
    this = _JOB.get()
    last = processes[-1]
    deadline = None if timeout is None else time.monotonic() + timeout
    try:
        while True:
            try:
                out, err = last.communicate(timeout=_POLL_SECONDS)
                break
            except subprocess.TimeoutExpired:
                _stop_and_raise_if_due(this, processes, deadline, timeout)
        for earlier in processes[:-1]:
            while True:
                try:
                    earlier.wait(timeout=_POLL_SECONDS)
                    break
                except subprocess.TimeoutExpired:
                    _stop_and_raise_if_due(this, processes, deadline, timeout)
        return out, err
    finally:
        with _LIVE_LOCK:
            _LIVE.difference_update(processes)


def run(cmd, *, timeout=None, check=False, **kwargs):
    """`subprocess.run`, stoppable when called inside a job.

    Outside a job this IS `subprocess.run`, argument for argument. Inside one, the same
    `CompletedProcess` comes back, `TimeoutExpired` and `CalledProcessError` are raised under
    the same conditions, and `JobCancelled` is raised if the job is cancelled while waiting.
    """
    if _JOB.get() is None:
        return subprocess.run(cmd, timeout=timeout, check=check, **kwargs)
    raise_if_cancelled()
    if kwargs.pop("capture_output", False):
        kwargs["stdout"] = kwargs["stderr"] = subprocess.PIPE
    process = popen(cmd, **kwargs)
    out, err = communicate([process], timeout=timeout)
    done = subprocess.CompletedProcess(process.args, process.returncode, out, err)
    if check:
        done.check_returncode()
    return done


def _kill_now(process):
    """Kill a process (and its group, when it leads one) without asking and without waiting."""
    if process.poll() is not None:
        return                      # finished: its pid may be somebody else's by now
    try:
        if getattr(process, "_hcl_own_group", False) and os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except (ProcessLookupError, PermissionError, OSError):
        pass


def terminate_all(*, force=False):
    """Stop every process a job started and has not yet waited for.

    Registered as an exit hook, as a last line of defence. The normal way a process stops is
    its job being left: the thread waiting on it then kills it. This covers what that cannot
    reach -- an interpreter that is exiting while such a thread has not yet had its turn.

    `force=True` kills at once instead of asking first and waiting out the grace period. It is
    for a process that is itself being killed and has no time left -- see the server's signal
    handler: these commands lead their own process groups, so nothing else will stop them.
    """
    with _LIVE_LOCK:
        live = list(_LIVE)
    for process in live:
        if force:
            _kill_now(process)
        else:
            _terminate(process)


atexit.register(terminate_all)
