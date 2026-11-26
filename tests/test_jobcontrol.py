"""Job control: a running simulation can be stopped, and reports where it is.

A long tool call runs its Radiance commands in a worker thread. When the client cancels the
call, times out, or goes away, the thread has to be told and the process it is waiting on has
to die -- together with the children Radiance starts itself (`rfluxmtx`, `rtrace -n`). Before
this module a cancelled annual run simply kept the machine busy until it finished.

Real processes throughout: the thing under test is whether a process is really gone.
"""
import contextvars
import os
import subprocess
import sys
import threading
import time

import pytest

from hcl_core import jobcontrol
from hcl_core import proc

PY = sys.executable
posix_only = pytest.mark.skipif(os.name != "posix", reason="process groups are checked the POSIX way")


def _sleeper(pid_file, seconds=60):
    """A command that records its own pid, then idles."""
    return [PY, "-c", f"import os,time; open({str(pid_file)!r},'w').write(str(os.getpid())); "
                      f"time.sleep({seconds})"]


def _parent_with_child(pid_file, seconds=60):
    """A command that starts a child (as rfluxmtx starts rcontrib), records both pids, idles."""
    child = f"import time; time.sleep({seconds})"
    return [PY, "-c",
            "import os,subprocess,sys,time; "
            f"c=subprocess.Popen([sys.executable,'-c',{child!r}]); "
            f"open({str(pid_file)!r},'w').write(f'{{os.getpid()}} {{c.pid}}'); time.sleep({seconds})"]


def _fake_program(path, pid_file):
    """An executable that records its pid and then idles, standing in for a slow binary."""
    path.write_text(f"#!/bin/sh\necho $$ > {pid_file}\nexec sleep 60\n")
    path.chmod(0o755)
    return path


def _pids(pid_file, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            text = open(pid_file).read().split()
        except FileNotFoundError:
            text = []
        if text:
            return [int(t) for t in text]
        time.sleep(0.02)
    raise AssertionError("the command never started")


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _gone(pids, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not any(_alive(p) for p in pids):
            return True
        time.sleep(0.05)
    return False


def _in_worker_thread(fn):
    """Run fn the way the server does: in another thread that inherits the caller's context."""
    context, box = contextvars.copy_context(), {}

    def target():
        try:
            box["result"] = context.run(fn)
        except BaseException as exc:  # JobCancelled is a BaseException, like CancelledError
            box["error"] = exc

    thread = threading.Thread(target=target)
    thread.start()
    return thread, box


# ---- run(): subprocess.run that can be stopped ----

def _exits_3_with_stderr():
    return [PY, "-c", "import sys; sys.stderr.write('boom'); sys.exit(3)"]


def test_outside_a_job_run_is_plain_subprocess_run():
    done = jobcontrol.run(_exits_3_with_stderr(), stderr=subprocess.PIPE)
    assert (done.returncode, done.stderr) == (3, b"boom")


def test_inside_a_job_run_returns_the_same_thing(tmp_path):
    out = tmp_path / "out.txt"
    with jobcontrol.job():
        with open(out, "wb") as fh:
            ok = jobcontrol.run([PY, "-c", "print('hello')"], stdout=fh, stderr=subprocess.PIPE)
        failed = jobcontrol.run(_exits_3_with_stderr(), stderr=subprocess.PIPE)
    assert (ok.returncode, out.read_text().strip()) == (0, "hello")
    assert (failed.returncode, failed.stderr) == (3, b"boom")


@pytest.mark.parametrize("in_job", [False, True])
def test_check_raises_on_a_non_zero_exit_in_and_out_of_a_job(in_job):
    def call():
        return jobcontrol.run(_exits_3_with_stderr(), stderr=subprocess.PIPE, check=True)

    with pytest.raises(subprocess.CalledProcessError):
        if in_job:
            with jobcontrol.job():
                call()
        else:
            call()


@posix_only
def test_cancelling_the_job_kills_the_command_and_the_children_it_started(tmp_path):
    pid_file = tmp_path / "pids"
    with jobcontrol.job() as job:
        thread, box = _in_worker_thread(lambda: jobcontrol.run(_parent_with_child(pid_file)))
        parent, child = _pids(pid_file)
        assert _alive(parent) and _alive(child)

        job.cancel.set()
        thread.join(timeout=10)

    assert not thread.is_alive(), "the waiting thread never noticed the cancellation"
    assert isinstance(box.get("error"), jobcontrol.JobCancelled)
    assert _gone([parent, child]), "a process outlived the cancelled job"


@posix_only
def test_a_timeout_inside_a_job_still_raises_timeout_and_kills_the_command(tmp_path):
    # The command must exist before the timeout fires, however busy the machine is. A Python
    # child can take longer than that to start under load, and a freshly written script can be
    # held up on its first exec by endpoint-security software (both failed here once). /bin/sh
    # with an inline script is neither: an existing binary that has its pid on disk in
    # milliseconds.
    pid_file = tmp_path / "pids"
    command = ["/bin/sh", "-c", f"echo $$ > {pid_file}; exec sleep 60"]
    with jobcontrol.job():
        with pytest.raises(subprocess.TimeoutExpired):
            jobcontrol.run(command, timeout=2.0)
    assert _gone(_pids(pid_file))


@posix_only
def test_leaving_the_job_stops_work_that_was_left_running(tmp_path):
    """The server abandons the worker thread when a call is cancelled. Leaving the job is what
    tells that thread to stop, whatever the reason the call ended."""
    pid_file = tmp_path / "pids"
    with jobcontrol.job():
        thread, box = _in_worker_thread(lambda: jobcontrol.run(_sleeper(pid_file)))
        pids = _pids(pid_file)
    thread.join(timeout=10)
    assert isinstance(box.get("error"), jobcontrol.JobCancelled)
    assert _gone(pids)


@posix_only
@pytest.mark.parametrize("force", [False, True], ids=["exit_hook", "signal_handler"])
def test_terminate_all_kills_whatever_is_still_running(force, tmp_path):
    """A server that is going away must not leave Radiance behind: politely from the exit
    hook, at once from the signal handler."""
    pid_file = tmp_path / "pids"
    with jobcontrol.job():
        thread, _ = _in_worker_thread(lambda: jobcontrol.run(_parent_with_child(pid_file)))
        pids = _pids(pid_file)
        jobcontrol.terminate_all(force=force)
        thread.join(timeout=10)
    assert _gone(pids)


# ---- progress ----

def test_steps_are_counted_upwards_across_the_whole_job():
    seen = []
    with jobcontrol.job(on_step=lambda count, message: seen.append((count, message))):
        jobcontrol.step("oconv")
        jobcontrol.step("rtrace")
        jobcontrol.step("oconv")       # a second sequence in the same tool call keeps counting
    assert seen == [(1, "oconv"), (2, "rtrace"), (3, "oconv")]


def test_a_step_outside_a_job_is_a_no_op():
    jobcontrol.step("oconv")           # must not raise


def test_a_failing_progress_callback_never_breaks_the_run():
    def broken(count, message):
        raise RuntimeError("client went away")

    with jobcontrol.job(on_step=broken):
        jobcontrol.step("oconv")


def test_a_step_in_a_cancelled_job_raises_instead_of_reporting():
    with jobcontrol.job() as job:
        job.cancel.set()
        with pytest.raises(jobcontrol.JobCancelled):
            jobcontrol.step("oconv")


# ---- the shared sequence runner honours both ----

def _run_sequence(steps, work_dir):
    return proc.run_sequence(steps, str(work_dir), True, unavailable_reason="n/a")


def test_the_sequence_runner_reports_each_step_with_its_position(tmp_path):
    seen = []
    steps = [{"write": ("a.txt", "x")},
             {"cmd": [PY, "-c", "print(1)"], "stdout": "b.txt"},
             {"cmd": [PY, "-c", "print(2)", "|", PY, "-c", "import sys; sys.stdout.write(sys.stdin.read())"],
              "stdout": "c.txt"}]
    with jobcontrol.job(on_step=lambda count, message: seen.append((count, message))):
        out = _run_sequence(steps, tmp_path)
    assert out["returncode"] == 0
    name = os.path.basename(PY)
    assert seen == [(1, "write a.txt (1/3)"), (2, f"{name} (2/3)"), (3, f"{name} | {name} (3/3)")]


@posix_only
def test_cancelling_stops_the_sequence_and_later_steps_never_run(tmp_path):
    pid_file = tmp_path / "pids"
    steps = [{"cmd": _sleeper(pid_file)}, {"write": ("after.txt", "must not exist")}]
    with jobcontrol.job() as job:
        thread, box = _in_worker_thread(lambda: _run_sequence(steps, tmp_path))
        pids = _pids(pid_file)
        job.cancel.set()
        thread.join(timeout=10)
    assert isinstance(box.get("error"), jobcontrol.JobCancelled)
    assert _gone(pids)
    assert not (tmp_path / "after.txt").exists()


@posix_only
def test_cancelling_kills_every_stage_of_a_pipe(tmp_path):
    first, second = tmp_path / "p1", tmp_path / "p2"
    steps = [{"cmd": [*_sleeper(first), "|", *_sleeper(second)], "stdout": "out.txt"}]
    with jobcontrol.job() as job:
        thread, box = _in_worker_thread(lambda: _run_sequence(steps, tmp_path))
        pids = _pids(first) + _pids(second)
        job.cancel.set()
        thread.join(timeout=10)
    assert isinstance(box.get("error"), jobcontrol.JobCancelled)
    assert _gone(pids)


# ---- the three engines that start a long process of their own ----

def _gensdaymtx(tmp_path, monkeypatch, pid_file):
    import hcl_radiance.spectral_native as native
    monkeypatch.setattr(native, "radiance_spectral_status", lambda: {"available": True})
    monkeypatch.setattr(native, "build_gensdaymtx_cmd", lambda *a, **k: _sleeper(pid_file))
    return lambda: native.run_gensdaymtx("in.epw", str(tmp_path))


def _daysim_build(tmp_path, monkeypatch, pid_file):
    from hcl_daysim import build
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake_program(bin_dir / "git", pid_file)
    _fake_program(bin_dir / "cmake", pid_file)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return lambda: build.build_daysim(str(tmp_path / "Daysim"), run=True, work_dir=str(tmp_path))


def _smarts(tmp_path, monkeypatch, pid_file):
    from hcl_core.spectral_engine.smarts import SmartsEngine
    from test_smarts import _Atm, _Geo
    home = tmp_path / "smarts"
    home.mkdir()
    monkeypatch.setenv("SMARTSPATH", str(_fake_program(home / "smarts295bat", pid_file)))
    return lambda: SmartsEngine().compute(_Atm(0.084, 1.14, 2.0, 0.33, 1013.0, 0.2), _Geo(45.0))


@posix_only
@pytest.mark.parametrize("engine", [_gensdaymtx, _daysim_build, _smarts],
                         ids=["gensdaymtx", "daysim_build", "smarts"])
def test_an_engine_with_its_own_process_is_stopped_when_the_job_is_cancelled(engine, tmp_path,
                                                                             monkeypatch):
    pid_file = tmp_path / "pid"
    call = engine(tmp_path, monkeypatch, pid_file)
    pids = []
    try:
        with jobcontrol.job() as job:
            thread, box = _in_worker_thread(call)
            pids = _pids(pid_file)
            job.cancel.set()
            thread.join(timeout=10)
        assert not thread.is_alive(), "the engine never noticed the cancellation"
        assert isinstance(box.get("error"), jobcontrol.JobCancelled), box
        assert _gone(pids)
    finally:
        for pid in pids:                       # never leave a stand-in running after a failure
            try:
                os.kill(pid, 9)
            except ProcessLookupError:
                pass


# ---- the rarer paths (found by review, 2026-11-26) ----

def _stubborn_program(path, pid_file):
    """A stand-in that ignores SIGTERM, like a process stuck where it cannot be interrupted.
    The ignore is inherited by the `sleep` it runs, so only SIGKILL ends the group."""
    path.write_text(f"#!/bin/sh\ntrap '' TERM\necho $$ > {pid_file}\nwhile :; do sleep 1; done\n")
    path.chmod(0o755)
    return path


@posix_only
def test_a_command_that_ignores_the_polite_request_is_killed_after_the_grace_period(
        tmp_path, monkeypatch):
    monkeypatch.setattr(jobcontrol, "_GRACE_SECONDS", 0.3)
    pid_file = tmp_path / "pid"
    program = _stubborn_program(tmp_path / "stubborn", pid_file)
    with jobcontrol.job() as job:
        thread, box = _in_worker_thread(lambda: jobcontrol.run([str(program)]))
        pids = _pids(pid_file)
        job.cancel.set()
        thread.join(timeout=15)
    try:
        assert isinstance(box.get("error"), jobcontrol.JobCancelled)
        assert _gone(pids)
    finally:
        for pid in pids:
            try:
                os.killpg(pid, 9)
            except (ProcessLookupError, PermissionError):
                pass


@posix_only
def test_the_signal_handler_path_kills_at_once_without_waiting_out_the_grace_period(
        tmp_path, monkeypatch):
    """A server being terminated has no time to ask nicely. With the grace period set far
    beyond this test's patience, only an immediate kill can pass."""
    grace = 40
    monkeypatch.setattr(jobcontrol, "_GRACE_SECONDS", grace)
    pid_file = tmp_path / "pid"
    program = _stubborn_program(tmp_path / "stubborn", pid_file)
    with jobcontrol.job():
        thread, _ = _in_worker_thread(lambda: jobcontrol.run([str(program)]))
        pids = _pids(pid_file)
        try:
            started = time.monotonic()
            jobcontrol.terminate_all(force=True)
            assert _gone(pids, timeout=10)
            # the call itself must not have sat out the grace period before killing
            assert time.monotonic() - started < grace / 2
        finally:
            for pid in pids:
                try:
                    os.killpg(pid, 9)
                except (ProcessLookupError, PermissionError):
                    pass
        thread.join(timeout=10)


@posix_only
def test_cancelling_stops_an_upstream_pipe_stage_that_outlives_the_last_one(tmp_path):
    """`a | b` where b has finished and a is still busy: the wait for a must be stoppable too,
    or the call hangs until a ends by itself."""
    pid_file = tmp_path / "pid"
    steps = [{"cmd": [*_sleeper(pid_file), "|", PY, "-c", "pass"], "stdout": "out.txt"}]
    started = time.monotonic()
    with jobcontrol.job() as job:
        thread, box = _in_worker_thread(lambda: _run_sequence(steps, tmp_path))
        pids = _pids(pid_file)
        time.sleep(0.5)                               # the last stage has long finished
        job.cancel.set()
        thread.join(timeout=15)
    assert isinstance(box.get("error"), jobcontrol.JobCancelled), box
    assert _gone(pids)
    assert time.monotonic() - started < 20, "waited the upstream stage out"


def _running_commands_mentioning(marker):
    """Pids of processes whose command line contains `marker` (a unique temp path)."""
    out = subprocess.run(["pgrep", "-f", marker], capture_output=True, text=True).stdout.split()
    return [int(pid) for pid in out if int(pid) != os.getpid()]


@posix_only
@pytest.mark.parametrize("in_job", [True, False])
def test_a_pipe_whose_later_stage_cannot_start_does_not_leave_the_earlier_one_running(
        in_job, tmp_path):
    # Found by its command line, not by a pid file: a stage that is stopped at once may never
    # get as far as writing one, and "no pid file" must not read as "nothing left running".
    marker = str(tmp_path / "pid")
    steps = [{"cmd": [*_sleeper(marker), "|", "/nonexistent/binary"], "stdout": "out.txt"}]

    def run():
        return _run_sequence(steps, tmp_path)

    try:
        if in_job:
            with jobcontrol.job():
                out = run()
        else:
            out = run()
        assert out["returncode"] == 127
        deadline = time.monotonic() + 10
        while _running_commands_mentioning(marker) and time.monotonic() < deadline:
            time.sleep(0.1)
        assert _running_commands_mentioning(marker) == [], "the stage that did start was left running"
    finally:
        for pid in _running_commands_mentioning(marker):
            try:
                os.kill(pid, 9)
            except ProcessLookupError:
                pass


def test_a_careless_except_exception_cannot_swallow_the_stop():
    """Engines are full of `except Exception` around a step. Cancellation must pass through
    them, or a cancelled run would log a failed step and carry on with the next one."""
    with jobcontrol.job() as job:
        job.cancel.set()
        with pytest.raises(jobcontrol.JobCancelled):
            try:
                jobcontrol.step("oconv")
            except Exception:
                pass


@posix_only
def test_a_process_that_already_finished_is_never_signalled_again(monkeypatch):
    """Its pid may belong to somebody else by now: signalling the group of a reaped process
    could kill an unrelated program of the same user."""
    with jobcontrol.job():
        process = jobcontrol.popen([PY, "-c", "pass"])
        process.wait()
    signalled = []
    monkeypatch.setattr(os, "killpg", lambda pid, sig: signalled.append((pid, sig)))
    jobcontrol._terminate(process)
    jobcontrol.terminate_all()
    jobcontrol.terminate_all(force=True)
    assert signalled == []


def test_a_cancelled_job_stops_the_yearly_spectral_loop(tmp_path):
    """8760 spectra is pure Python: no command to kill, so the loop itself has to look."""
    from hcl_core.spectral_pipeline import annual_records
    from test_spectral_pipeline import _row, _write_epw
    epw = _write_epw(tmp_path, _row(6, 12, 28, 12, 40, 101300, 800, 850, 120, 2, 1, 15, 0.12, 0.2))
    with jobcontrol.job() as job:
        job.cancel.set()
        with pytest.raises(jobcontrol.JobCancelled):
            annual_records(str(epw))
