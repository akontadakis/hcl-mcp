"""A tool call is a job: it runs off the event loop, reports progress, and can be stopped.

Before this, every simulation tool called its blocking engine straight from the event loop.
While Radiance ran, the server could not read a cancellation, send a progress notification, or
answer any other request -- and a client that gave up left the simulation running.

Three properties, each observed rather than inferred:
  * the engine entry point runs on a worker thread, for every tool that reaches a subprocess;
  * progress reported by the engine arrives at a real client, on both protocol eras;
  * cancelling a call kills the process it was waiting on, and the server keeps answering.
"""
import asyncio
import os
import sys
import threading
import time

import pytest
from fastmcp import Client

import hcl_mcp.server as srv
from hcl_core import jobcontrol
from test_jobcontrol import _gone, _pids, _sleeper, posix_only
from test_lm83_tool import _MAP, _setup

_SCENE = [{"materials": ["m.rad"], "geometry": "g.rad", "sky_color": [1, 1, 1]}]
_PTS = [[0, 0, 0.8, 0, 0, 1]]
_ERAS = ["legacy", "auto"]          # initialize handshake, and MCP 2026-07-28
_PLAN = {"ran": False, "commands": ["<plan>"], "reason": "recorded"}


def _lm83_args(tmp_path):
    work, obj, wea, points = _setup(tmp_path)
    return dict(obj_path=obj, material_map=_MAP, wea=wea, points=points, floor_area_m2=16.0)


# tool, the engine entry points it must reach off-loop, what they return, arguments
_HEAVY = [
    ("colored_sky", {"_colored_sky": _PLAN},
     lambda t: dict(diffuse_channels=[1, 1, 1], direct_channels=[1, 1, 1], channel_type=0)),
    ("run_grid", {"_run_grid": _PLAN}, lambda t: dict(scene_sets=[["m.rad"]], points=_PTS)),
    ("run_image", {"_run_image": _PLAN}, lambda t: dict(scene_sets=[["m.rad"]])),
    ("glare_ugr", {"_run_image": _PLAN}, lambda t: dict(scene_sets=[["m.rad"]])),
    ("import_geometry", {"_import_geometry": _PLAN}, lambda t: dict(obj_path="room.obj")),
    ("run_annual", {"_run_annual": _PLAN},
     lambda t: dict(channel_scenes=_SCENE, wea="in.wea", points=_PTS, channel_type=0)),
    ("annual_daylight", {"_run_annual_daylight": _PLAN},
     lambda t: dict(channel_scenes=_SCENE, wea="in.wea", points=_PTS, channel_type=0)),
    ("daylight_factor", {"_run_daylight_factor": _PLAN},
     lambda t: dict(scene_sets=[["m.rad"]], points=_PTS)),
    ("daylight_savings", {"_run_annual_daylight": _PLAN},
     lambda t: dict(channel_scenes=_SCENE, wea="in.wea", points=_PTS, channel_type=0,
                    mode="annual", weights=[1.0], area=20.0)),
    ("daylight_savings", {"_run_grid": _PLAN},
     lambda t: dict(scene_sets=[["m.rad"]], points=_PTS, weights=[1.0])),
    ("lm83_daylight",
     {"_import_geometry": {"geometry_set": ["g.rad"], "material_sets": [["m.rad"]]},
      "_run_lm83": _PLAN}, _lm83_args),
    ("annual_nvrd", {"_annual_nvrd": _PLAN},
     lambda t: dict(point_xyz=[0, 0, 1.2], view_vec=[0, 1, 0], epw="in.epw",
                    channel_scenes=_SCENE, points=[[0, 0, 1.2, 0, 1, 0]], channel_type=0)),
    ("ies_to_radiance", {"run_sequence": _PLAN}, lambda t: dict(ies="lamp.ies")),
    ("build_daysim", {"_build_daysim": _PLAN}, lambda t: dict()),
    ("generate_subhourly_wea", {"_generate_subhourly_wea": _PLAN}, lambda t: dict(epw="in.epw")),
    ("spectral_sky_native", {"_run_gensdaymtx": _PLAN}, lambda t: dict(epw="in.epw")),
    ("spectral_epw", {"_annual_records": []}, lambda t: dict(epw="in.epw", forms=["spd_set"])),
]


@pytest.mark.parametrize("tool, engines, build_args", _HEAVY,
                         ids=[f"{t}:{'+'.join(e)}" for t, e, _ in _HEAVY])
def test_the_engine_runs_on_a_worker_thread_not_on_the_event_loop(tool, engines, build_args,
                                                                  tmp_path, monkeypatch):
    ran_on = {}

    def recorder(name, result):
        def engine(*args, **kwargs):
            ran_on[name] = threading.get_ident()
            return result
        return engine

    for name, result in engines.items():
        monkeypatch.setattr(srv, name, recorder(name, result))

    async def call():
        loop_thread = threading.get_ident()
        await getattr(srv, tool)(**build_args(tmp_path), work_dir=str(tmp_path))
        return loop_thread

    loop_thread = asyncio.run(call())
    assert set(ran_on) == set(engines), "an engine entry point was never reached"
    assert loop_thread not in ran_on.values()


# ---- through the real framework ----

def _client(mode, **kwargs):
    return Client(srv.mcp, mode=mode, **kwargs)


_GRID_ARGS = {"scene_sets": [["m.rad"]], "points": _PTS}
_SLEEPER_SECONDS = 60


def _assert_it_was_killed_not_waited_out(started):
    """A process that is "gone" proves nothing if the test waited for it to finish by itself --
    which is exactly what happens when the engine blocks the event loop."""
    assert time.monotonic() - started < _SLEEPER_SECONDS / 3


@pytest.mark.parametrize("mode", _ERAS)
def test_the_server_answers_other_requests_while_a_simulation_runs(mode, monkeypatch):
    release = threading.Event()

    def slow_engine(*args, **kwargs):
        release.wait(timeout=20)
        return _PLAN

    monkeypatch.setattr(srv, "_run_grid", slow_engine)

    async def scenario():
        async with _client(mode) as client:
            simulation = asyncio.create_task(client.call_tool("run_grid", _GRID_ARGS))
            await asyncio.sleep(0.2)                       # let the call reach the engine
            other = await asyncio.wait_for(client.call_tool("validate", {}), timeout=10)
            still_running = not simulation.done()
            release.set()
            await simulation
            return other.structured_content["ok"], still_running

    try:
        assert asyncio.run(scenario()) == (True, True)
    finally:
        release.set()


@pytest.mark.parametrize("mode", _ERAS)
def test_progress_from_the_engine_reaches_the_client_and_only_goes_up(mode, monkeypatch):
    def engine(*args, **kwargs):
        jobcontrol.step("oconv (1/2)")
        jobcontrol.step("rtrace (2/2)")
        return _PLAN

    monkeypatch.setattr(srv, "_run_grid", engine)
    seen = []

    async def on_progress(progress, total, message):
        seen.append((progress, message))

    async def scenario():
        async with _client(mode, progress_handler=on_progress) as client:
            await client.call_tool("run_grid", _GRID_ARGS)
            await asyncio.sleep(0.1)                       # notifications are not awaited

    asyncio.run(scenario())
    assert seen == [(1, "oconv (1/2)"), (2, "rtrace (2/2)")]


@posix_only
@pytest.mark.parametrize("mode", _ERAS)
def test_cancelling_a_call_kills_its_process_and_the_server_keeps_answering(mode, tmp_path,
                                                                            monkeypatch):
    pid_file = tmp_path / "pid"

    def engine(*args, **kwargs):
        jobcontrol.run(_sleeper(pid_file, _SLEEPER_SECONDS))
        return _PLAN

    monkeypatch.setattr(srv, "_run_grid", engine)

    async def scenario():
        async with _client(mode) as client:
            simulation = asyncio.create_task(client.call_tool("run_grid", _GRID_ARGS))
            pids = await asyncio.to_thread(_pids, pid_file)
            simulation.cancel()
            with pytest.raises(asyncio.CancelledError):
                await simulation
            gone = await asyncio.to_thread(_gone, pids)
            answers = (await client.call_tool("validate", {})).structured_content["ok"]
            return gone, answers

    started = time.monotonic()
    assert asyncio.run(scenario()) == (True, True)
    _assert_it_was_killed_not_waited_out(started)


@posix_only
@pytest.mark.parametrize("mode", _ERAS)
def test_a_client_that_goes_away_does_not_leave_its_simulation_running(mode, tmp_path,
                                                                       monkeypatch):
    pid_file = tmp_path / "pid"

    def engine(*args, **kwargs):
        jobcontrol.run(_sleeper(pid_file, _SLEEPER_SECONDS))
        return _PLAN

    monkeypatch.setattr(srv, "_run_grid", engine)

    async def scenario():
        client = _client(mode)
        await client.__aenter__()
        simulation = asyncio.create_task(client.call_tool("run_grid", _GRID_ARGS))
        pids = await asyncio.to_thread(_pids, pid_file)
        simulation.cancel()
        await client.__aexit__(None, None, None)           # the connection closes mid-run
        return await asyncio.to_thread(_gone, pids)

    started = time.monotonic()
    assert asyncio.run(scenario()) is True
    _assert_it_was_killed_not_waited_out(started)


# ---- a real server process, killed or abandoned in the middle of a run ----

def _start_server_with_a_slow_build(tmp_path):
    """Start the real server as a subprocess and put it in the middle of `build_daysim`, whose
    `git clone` is a stand-in that records its pid and idles. Returns (server, pids of the run)."""
    import json
    import subprocess

    from test_jobcontrol import _fake_program

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    pid_file = tmp_path / "pid"
    _fake_program(bin_dir / "git", pid_file)
    _fake_program(bin_dir / "cmake", pid_file)
    src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "PYTHONPATH": src}
    server = subprocess.Popen([sys.executable, "-m", "hcl_mcp.server"], env=env, cwd=str(tmp_path),
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, text=True)

    def send(message):
        server.stdin.write(json.dumps(message) + "\n")
        server.stdin.flush()

    send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
          "params": {"protocolVersion": "2025-11-25", "capabilities": {},
                     "clientInfo": {"name": "test", "version": "0"}}})
    assert json.loads(server.stdout.readline())["id"] == 1
    send({"jsonrpc": "2.0", "method": "notifications/initialized"})
    send({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
          "params": {"name": "build_daysim",
                     "arguments": {"src_dir": str(tmp_path / "Daysim"), "work_dir": str(tmp_path)}}})
    return server, _pids(pid_file, timeout=60)


def _kill_leftovers(server, pids):
    for pid in pids:
        try:
            os.kill(pid, 9)
        except ProcessLookupError:
            pass
    if server.poll() is None:
        server.kill()
    server.wait(timeout=10)


@posix_only
@pytest.mark.parametrize("how", ["terminated", "hung_up", "stdin_closed"])
def test_a_server_that_is_stopped_mid_run_takes_its_simulation_with_it(how, tmp_path):
    """MCP clients stop a stdio server by closing its stdin and, shortly after, by signal.
    The simulation runs in its own process group, so nothing but the server can stop it:
    a server that dies without doing so leaves Radiance running for hours with no owner."""
    import signal

    server, pids = _start_server_with_a_slow_build(tmp_path)
    try:
        if how == "terminated":
            server.send_signal(signal.SIGTERM)
        elif how == "hung_up":
            server.send_signal(signal.SIGHUP)
        else:
            server.stdin.close()
        gone = _gone(pids, timeout=15)
        server.wait(timeout=15)
        assert gone, f"the simulation outlived a server that was {how}"
    finally:
        _kill_leftovers(server, pids)


# ---- found by review, 2026-11-26 ----

def test_every_async_tool_takes_a_context_so_it_can_report_progress():
    import inspect
    without = [tool.__name__ for tool in srv._TOOL_FUNCS
               if inspect.iscoroutinefunction(tool)
               and "ctx" not in inspect.signature(tool).parameters]
    assert without == []


def test_two_simulations_never_run_at_the_same_time(tmp_path, monkeypatch):
    """Engines write fixed file names into the work directory. While the engine blocked the
    event loop, two calls could not overlap; now that it does not, something else has to
    keep them apart, or parallel calls silently overwrite each other's octrees and results."""
    spans, lock = [], threading.Lock()

    def engine(*args, **kwargs):
        started = time.monotonic()
        time.sleep(0.3)
        with lock:
            spans.append((started, time.monotonic()))
        return _PLAN

    monkeypatch.setattr(srv, "_run_grid", engine)
    tool = srv._with_advisories(srv.run_grid)

    async def scenario():
        await asyncio.gather(*(tool(**_GRID_ARGS, work_dir=str(tmp_path)) for _ in range(3)))

    asyncio.run(scenario())
    spans.sort()
    assert len(spans) == 3
    assert all(later[0] >= earlier[1] for earlier, later in zip(spans, spans[1:])), spans


def test_a_call_cancelled_while_it_waits_its_turn_never_starts_its_simulation(tmp_path,
                                                                              monkeypatch):
    release, ran = threading.Event(), []

    def engine(scene_sets, *args, **kwargs):
        ran.append(scene_sets[0][0])
        release.wait(timeout=20)
        return _PLAN

    monkeypatch.setattr(srv, "_run_grid", engine)
    tool = srv._with_advisories(srv.run_grid)

    async def scenario():
        first = asyncio.create_task(tool(scene_sets=[["first.rad"]], points=_PTS,
                                         work_dir=str(tmp_path)))
        await asyncio.sleep(0.2)
        second = asyncio.create_task(tool(scene_sets=[["second.rad"]], points=_PTS,
                                          work_dir=str(tmp_path)))
        await asyncio.sleep(0.2)
        second.cancel()
        with pytest.raises(asyncio.CancelledError):
            await second
        release.set()
        await first
        await asyncio.sleep(0.5)                      # give a wrongly started engine time to show

    try:
        asyncio.run(scenario())
    finally:
        release.set()
    assert ran == ["first.rad"]


def test_progress_keeps_counting_up_across_the_two_engines_of_one_tool(tmp_path, monkeypatch):
    # Handshake era only: lm83_daylight is one of the task tools, and a client that declares
    # the tasks extension reads progress as the task's status, not as notifications.
    mode = "legacy"
    def importer(*args, **kwargs):
        jobcontrol.step("obj2rad (1/1)")
        return {"geometry_set": ["g.rad"], "material_sets": [["m.rad"]]}

    def lm83(*args, **kwargs):
        jobcontrol.step("rfluxmtx (1/1)")
        return _PLAN

    monkeypatch.setattr(srv, "_import_geometry", importer)
    monkeypatch.setattr(srv, "_run_lm83", lm83)
    seen = []

    async def on_progress(progress, total, message):
        seen.append((progress, message))

    async def scenario():
        async with _client(mode, progress_handler=on_progress) as client:
            await client.call_tool("lm83_daylight", {**_lm83_args(tmp_path),
                                                     "work_dir": str(tmp_path)})
            await asyncio.sleep(0.1)

    asyncio.run(scenario())
    assert seen == [(1, "obj2rad (1/1)"), (2, "rfluxmtx (1/1)")]


@pytest.mark.parametrize("tool, arguments, simulates", [
    ("annual_daylight", {}, True),
    ("annual_daylight", {"run": True}, True),
    ("annual_daylight", {"run": False}, False),
    # Clients that do not type their arguments send strings; the tool's own validation reads
    # "false" as False, so the question must not be asked about a dry run.
    ("annual_daylight", {"run": "false"}, False),
    ("annual_daylight", {"run": "true"}, True),
    ("annual_daylight", {"run": 0}, False),
    ("annual_daylight", {"run": "not a boolean"}, False),      # the tool will reject the call
    ("daylight_savings", {}, False),                           # point_in_time by default
    ("daylight_savings", {"mode": "annual"}, True),
    ("daylight_savings", {"mode": "annual", "run": "false"}, False),
])
def test_would_simulate_reads_arguments_the_way_the_tool_does(tool, arguments, simulates):
    assert srv._would_simulate(tool, arguments) is simulates
