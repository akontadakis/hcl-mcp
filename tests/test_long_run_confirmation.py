"""The four long-running tools must hand the confirmation question back to the client.

On MCP 2026-07-28 a tool asks by RETURNING the question, so each tool has to stop and return it
before any simulation work, and must reach the client unchanged through the advisory wrapper
that every registered tool passes through. A "no" must then land on the emit path: the tool
returns the command plan and runs nothing.

Each tool is called the way the server registers it (`_with_advisories(tool)`), with the
simulation entry point replaced by a recorder, so "ran nothing" is observed, not inferred.
"""
import asyncio

import mcp.types as mt
import pytest

import hcl_mcp.server as srv
from test_confirm_run import MODERN, FakeCtx
from test_lm83_tool import _MAP, _setup

_SCENE = [{"materials": ["m.rad"], "geometry": "g.rad", "sky_color": [1, 1, 1]}]
_POINTS = [[0, 0, 0.8, 0, 0, 1], [1, 0, 0.8, 0, 0, 1]]
_NO = mt.ElicitResult(action="accept", content={"value": False})


def _annual_daylight(tmp_path):
    return srv.annual_daylight, "_run_annual_daylight", dict(
        channel_scenes=_SCENE, wea="in.wea", points=_POINTS, channel_type=0,
        work_dir=str(tmp_path))


def _daylight_savings(tmp_path):
    return srv.daylight_savings, "_run_annual_daylight", dict(
        channel_scenes=_SCENE, wea="in.wea", points=_POINTS, channel_type=0, mode="annual",
        weights=[0.5, 0.5], area=20.0, work_dir=str(tmp_path))


def _annual_nvrd(tmp_path):
    return srv.annual_nvrd, "_annual_nvrd", dict(
        point_xyz=[0, 0, 1.2], view_vec=[0, 1, 0], epw="in.epw", channel_scenes=_SCENE,
        points=[[0, 0, 1.2, 0, 1, 0]], channel_type=0, work_dir=str(tmp_path))


def _lm83_daylight(tmp_path):
    work, obj, wea, points = _setup(tmp_path)
    return srv.lm83_daylight, "_run_lm83", dict(
        obj_path=obj, material_map=_MAP, wea=wea, points=points, floor_area_m2=16.0,
        work_dir=work)


_TOOLS = [_annual_daylight, _daylight_savings, _annual_nvrd, _lm83_daylight]


def _call_registered(tool, kwargs, ctx):
    return asyncio.run(srv._with_advisories(tool)(**kwargs, ctx=ctx))


def _record_simulation(monkeypatch, entry_point):
    calls = []

    def recorder(*args, **kwargs):
        calls.append(kwargs)
        return {"ran": False, "commands": ["<plan>"], "reason": "recorded"}

    monkeypatch.setattr(srv, entry_point, recorder)
    return calls


@pytest.mark.parametrize("build", _TOOLS, ids=lambda b: b.__name__.lstrip("_"))
def test_the_tool_returns_the_question_and_starts_no_simulation(build, tmp_path, monkeypatch):
    tool, entry_point, kwargs = build(tmp_path)
    simulations = _record_simulation(monkeypatch, entry_point)

    out = _call_registered(tool, kwargs, FakeCtx(MODERN))

    assert isinstance(out, mt.InputRequiredResult), type(out)
    assert simulations == []


@pytest.mark.parametrize("build", _TOOLS, ids=lambda b: b.__name__.lstrip("_"))
def test_a_no_answer_lands_on_the_emit_path(build, tmp_path, monkeypatch):
    tool, entry_point, kwargs = build(tmp_path)
    simulations = _record_simulation(monkeypatch, entry_point)
    (key,) = _call_registered(tool, kwargs, FakeCtx(MODERN)).input_requests

    out = _call_registered(tool, kwargs, FakeCtx(MODERN, answers={key: _NO}))

    assert out["ran"] is False
    assert [call["run"] for call in simulations] == [False]


# ---- the real registered tool, through the real framework, on both eras ----

async def _yes(message, response_type, params, context):
    return response_type(value=True)


async def _no(message, response_type, params, context):
    return response_type(value=False)


@pytest.mark.parametrize("mode", ["legacy", "auto"])
@pytest.mark.parametrize("handler, simulated_with_run", [(_yes, True), (_no, False)])
def test_the_registered_tool_obeys_a_real_clients_answer(mode, handler, simulated_with_run,
                                                         tmp_path, monkeypatch):
    """Schema validation, the advisory wrapper and the guard together, as a client meets them."""
    from fastmcp import Client

    _tool, entry_point, kwargs = _annual_daylight(tmp_path)
    simulations = _record_simulation(monkeypatch, entry_point)

    async def call():
        async with Client(srv.mcp, mode=mode, elicitation_handler=handler) as client:
            return await client.call_tool("annual_daylight", kwargs)

    asyncio.run(call())
    assert [c["run"] for c in simulations] == [simulated_with_run]
