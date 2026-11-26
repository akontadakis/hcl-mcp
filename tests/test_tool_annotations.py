"""Review 2026-11-26, M8: every tool tells the client whether it only reads.

A client uses these hints to decide what it may run without asking. A wrong `readOnlyHint` is
worse than none, so the read-only set is pinned here by name and checked against the code.
"""
import asyncio
import inspect

import pytest

from hcl_mcp import server

READ_ONLY = {
    "spd_to_channels", "glass_transmissivity", "circadian_metrics", "alpha_opic", "validate",
    "spectral_metrics", "compliance", "presets", "reference", "check_geometry",
    "radiance_status", "nvrd", "ies_analyze", "lighting_controls", "daysim_status",
    "reconstruct_spectrum", "recommend_fixtures", "atmosphere_from_epw",
    "quality_presets", "load_brief",
    # aliases of tools above
    "get_reference", "list_presets", "run_validation",
}


@pytest.fixture(scope="module")
def tools():
    return {t.name: t for t in asyncio.run(server.mcp.list_tools())}


def test_every_tool_carries_all_four_hints(tools):
    for name, tool in tools.items():
        a = tool.annotations
        assert a is not None, name
        for hint in ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint"):
            assert isinstance(getattr(a, hint), bool), (name, hint)


def test_the_read_only_tools_are_exactly_the_named_ones(tools):
    assert {n for n, t in tools.items() if t.annotations.readOnlyHint} == READ_ONLY


def test_no_read_only_tool_can_be_told_to_run_or_write(tools):
    """The check behind the list: a tool that takes `run`, an output path or a name to save
    under does something on disk, whatever its label says."""
    # `engine`: a tool that lets the caller pick an engine can start an external program
    # (spectral_sky_from_epw with engine="smarts" runs SMARTS in a temporary folder).
    writers = {"run", "subset_out", "out_path", "src_dir", "engine"}
    by_name = {f.__name__: f for f in server._TOOL_FUNCS} | dict(server._TOOL_ALIASES)
    for name in READ_ONLY:
        params = set(inspect.signature(by_name[name]).parameters)
        assert not params & writers, (name, params & writers)
        if "work_dir" in params:
            assert name == "load_brief"            # reads a saved brief, writes nothing


def test_a_read_only_tool_is_neither_destructive_nor_open_world(tools):
    for name in READ_ONLY:
        a = tools[name].annotations
        assert (a.destructiveHint, a.openWorldHint, a.idempotentHint) == (False, False, True), name


def test_every_tool_that_writes_is_marked_destructive(tools):
    """MCP reads destructiveHint=false as "additive updates only". Every writer here replaces
    its earlier output of the same name (a material, a sky, a brief, a result matrix), and
    `sensors` can delete. None of them may claim to be additive."""
    for name, tool in tools.items():
        assert tool.annotations.destructiveHint is (name not in READ_ONLY), name


def test_a_tool_that_can_start_smarts_is_not_read_only(tools):
    assert tools["spectral_sky_from_epw"].annotations.readOnlyHint is False


def test_only_the_daysim_build_reaches_the_network(tools):
    assert [n for n, t in tools.items() if t.annotations.openWorldHint] == ["build_daysim"]


def test_the_hints_survive_the_modern_protocol_listing():
    """What a 2026-07-28 client is actually sent."""
    from fastmcp import Client

    async def listed():
        async with Client(server.mcp) as client:
            return {t.name: t for t in await client.list_tools()}

    sent = asyncio.run(listed())
    assert sent["compliance"].annotations.readOnlyHint is True
    assert sent["run_grid"].annotations.readOnlyHint is False
