import asyncio

from fastmcp import FastMCP

import hcl_mcp.server as S

EXPECTED_TOOL_COUNT = 51  # 47 functions + 4 verb_object aliases


def _names(server):
    return {t.name for t in asyncio.run(server.list_tools())}


def _by_name(server):
    return {t.name: t for t in asyncio.run(server.list_tools())}


def _raw_server():
    """A server built from the UNWRAPPED functions, for schema comparison."""
    m = FastMCP("raw")
    for fn in S._TOOL_FUNCS:
        m.tool(fn)
    for name, fn in S._TOOL_ALIASES:
        m.tool(fn, name=name)
    return m


def test_registration_tuples_cover_every_registered_name():
    expected = {fn.__name__ for fn in S._TOOL_FUNCS} | {n for n, _ in S._TOOL_ALIASES}
    assert _names(S.mcp) == expected


def test_registered_tool_count_is_stable():
    assert len(_names(S.mcp)) == EXPECTED_TOOL_COUNT


def test_aliases_are_registered_under_their_alias_names():
    names = _names(S.mcp)
    for alias, _fn in S._TOOL_ALIASES:
        assert alias in names, f"alias {alias} not registered"


def test_schemas_match_the_unwrapped_registration():
    """Guards the load-bearing `str | list` annotations (server.py:88, :96).

    fastmcp is pinned only as >=2.0, so a minor upgrade could change how a
    wrapped callable's signature is introspected. This test fails loudly if
    wrapping ever alters a published schema.
    """
    live, raw = _by_name(S.mcp), _by_name(_raw_server())
    assert set(live) == set(raw)
    for name in sorted(live):
        assert live[name].parameters == raw[name].parameters, f"schema drift in {name}"
        assert live[name].description == raw[name].description, f"description drift in {name}"


def test_server_publishes_instructions():
    assert S.mcp.instructions
    assert S.mcp.instructions == S.INSTRUCTIONS


def test_instructions_name_the_load_bearing_traps():
    text = S.INSTRUCTIONS
    for token in ("mel_edi", "mel_der_source", "absolute", "advisories", "check_geometry"):
        assert token in text, f"instructions omit {token}"


def test_instructions_stay_within_budget():
    """Paid by every session of every client — keep it to what changes behaviour."""
    assert len(S.INSTRUCTIONS.splitlines()) <= 45


def test_instructions_do_not_overclaim_advisory_coverage():
    """_attach only wraps dict results; the instructions must say so."""
    assert "dict-shaped" in S.INSTRUCTIONS
    assert "circadian_metrics" in S.INSTRUCTIONS
