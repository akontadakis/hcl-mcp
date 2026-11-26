"""The long tools can run as background tasks (MCP tasks extension, SEP-2663).

An annual simulation takes minutes to hours. Held open as one request it is at the mercy of
every timeout between the model and the server. With the tasks extension the call returns a
handle at once; the client polls it, can read where the run is, and can cancel it.

The server decides per request, and only for clients that declared the extension. Everybody
else -- handshake-era clients, and clients that never heard of tasks -- keeps getting the
plain inline call, which is asserted here as carefully as the task path.
"""
import asyncio
import threading
import time

import mcp.types as mt
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from fastmcp_tasks import call_tool_task

import hcl_mcp.server as srv
from hcl_core import jobcontrol
from test_jobcontrol import _gone, _pids, _sleeper, posix_only
from test_long_run_confirmation import (_TOOLS, _annual_daylight, _daylight_savings,
                                        _record_simulation)

_SCENE = [{"materials": ["m.rad"], "geometry": "g.rad", "sky_color": [1, 1, 1]}]
_PTS = [[0, 0, 0.8, 0, 0, 1]]
_PLAN = {"ran": False, "commands": ["<plan>"], "reason": "recorded"}
_SLEEPER_SECONDS = 60


def _record_task_simulation(monkeypatch, entry_point):
    """Replace an engine entry point; record how it was called and whether a task ran it."""
    from fastmcp.server.dependencies import get_context
    calls = []

    def recorder(*args, **kwargs):
        calls.append({"run": kwargs["run"], "in_background_task": get_context().is_background_task})
        return _PLAN

    monkeypatch.setattr(srv, entry_point, recorder)
    return calls


def _annual_args(tmp_path):
    return dict(channel_scenes=_SCENE, wea="in.wea", points=_PTS, channel_type=0,
                work_dir=str(tmp_path))


def test_exactly_the_long_running_tools_are_offered_as_tasks():
    assert {t.__name__ for t in srv._TASK_TOOLS} == {
        "run_annual", "annual_daylight", "lm83_daylight", "daylight_savings", "annual_nvrd",
        "spectral_epw", "spectral_sky_native", "build_daysim"}


def test_a_task_capable_client_gets_a_handle_at_once_and_the_result_later(tmp_path, monkeypatch):
    release = threading.Event()

    def engine(*args, **kwargs):
        jobcontrol.step("rfluxmtx (1/2)")
        release.wait(timeout=30)
        return _PLAN

    monkeypatch.setattr(srv, "_run_annual", engine)

    async def scenario():
        async with Client(srv.mcp, mode="auto") as client:
            started = time.monotonic()
            task = await call_tool_task(client, "run_annual", _annual_args(tmp_path))
            handed_back_after = time.monotonic() - started
            # where the run is, readable while it is still running
            for _ in range(100):
                status = await task.status()
                if status.status_message:
                    break
                await asyncio.sleep(0.05)
            release.set()
            result = await task.result()
            return handed_back_after, status.status, status.status_message, result.structured_content

    try:
        handed_back_after, status, message, result = asyncio.run(scenario())
    finally:
        release.set()
    assert handed_back_after < 5, "the call waited for the simulation instead of returning a handle"
    assert (status, message) == ("working", "rfluxmtx (1/2)")
    assert result == _PLAN


@posix_only
def test_cancelling_a_task_kills_its_process(tmp_path, monkeypatch):
    pid_file = tmp_path / "pid"

    def engine(*args, **kwargs):
        jobcontrol.run(_sleeper(pid_file, _SLEEPER_SECONDS))
        return _PLAN

    monkeypatch.setattr(srv, "_run_annual", engine)

    async def scenario():
        async with Client(srv.mcp, mode="auto") as client:
            task = await call_tool_task(client, "run_annual", _annual_args(tmp_path))
            pids = await asyncio.to_thread(_pids, pid_file)
            await task.cancel()
            gone = await asyncio.to_thread(_gone, pids)
            for _ in range(100):
                status = (await task.status()).status
                if status != "working":
                    break
                await asyncio.sleep(0.05)
            return gone, status

    started = time.monotonic()
    assert asyncio.run(scenario()) == (True, "cancelled")
    assert time.monotonic() - started < _SLEEPER_SECONDS / 3, "waited the process out"


@pytest.mark.parametrize("build", _TOOLS, ids=lambda b: b.__name__.lstrip("_"))
@pytest.mark.parametrize("answer, simulated_with_run", [(True, True), (False, False)])
def test_the_long_run_question_is_asked_once_before_the_task_is_created(
        build, answer, simulated_with_run, tmp_path, monkeypatch):
    """A task body cannot see whether its client can answer a question, so the question is
    settled in the foreground first -- what the tasks extension itself recommends. A no still
    lands on the emit path, and the task that follows never asks again."""
    tool, entry_point, kwargs = build(tmp_path)
    simulations = _record_task_simulation(monkeypatch, entry_point)
    if tool is srv.lm83_daylight:
        monkeypatch.setattr(srv, "_import_geometry", lambda *a, **k: {
            "geometry_set": ["g.rad"], "material_sets": [["m.rad"]]})
    asked = []

    async def handler(message, response_type, params, context):
        asked.append(message)
        return response_type(value=answer)

    async def scenario():
        async with Client(srv.mcp, mode="auto", elicitation_handler=handler) as client:
            # call_tool answers the question and follows the task to its result by itself
            return (await client.call_tool(tool.__name__, kwargs)).structured_content

    assert asyncio.run(scenario())["ran"] is False
    assert len(asked) == 1 and "Proceed?" in asked[0]
    assert simulations == [{"run": simulated_with_run, "in_background_task": True}]


def test_a_task_capable_client_that_cannot_be_asked_still_gets_its_run(tmp_path, monkeypatch):
    tool, entry_point, kwargs = _annual_daylight(tmp_path)
    simulations = _record_task_simulation(monkeypatch, entry_point)

    async def scenario():
        async with Client(srv.mcp, mode="auto") as client:          # no elicitation handler
            await client.call_tool("annual_daylight", kwargs)

    asyncio.run(scenario())
    assert simulations == [{"run": True, "in_background_task": True}]


def test_a_tool_that_would_not_simulate_is_not_asked_about(tmp_path, monkeypatch):
    """daylight_savings only runs the annual engine in annual mode, and nothing at all with
    run=False. Neither call may put the long-run question to the user."""
    _record_simulation(monkeypatch, "_run_annual_daylight")
    _record_simulation(monkeypatch, "_run_grid")
    asked = []

    async def handler(message, response_type, params, context):
        asked.append(message)
        return response_type(value=True)

    async def scenario():
        async with Client(srv.mcp, mode="auto", elicitation_handler=handler) as client:
            _, _, annual = _daylight_savings(tmp_path)
            await client.call_tool("daylight_savings", {**annual, "run": False})
            await client.call_tool("daylight_savings", dict(
                scene_sets=[["m.rad"]], points=_PTS, weights=[1.0], work_dir=str(tmp_path)))

    asyncio.run(scenario())
    assert asked == []


def test_a_handshake_era_client_gets_the_plain_inline_call(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "_run_annual", lambda *a, **k: _PLAN)

    async def scenario():
        async with Client(srv.mcp, mode="legacy") as client:
            inline = await client.call_tool("run_annual", _annual_args(tmp_path))
            with pytest.raises(ToolError):       # the server ran it synchronously: no handle
                await call_tool_task(client, "run_annual", _annual_args(tmp_path))
            return inline.structured_content

    assert asyncio.run(scenario()) == _PLAN


def test_a_quick_tool_is_never_turned_into_a_task():
    async def scenario():
        async with Client(srv.mcp, mode="auto") as client:
            with pytest.raises(ToolError):
                await call_tool_task(client, "validate", {})
            return (await client.call_tool("validate", {})).structured_content["ok"]

    assert asyncio.run(scenario()) is True
