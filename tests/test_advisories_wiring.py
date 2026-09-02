"""Advisories must reach results through the REGISTERED tools.

The module-level functions stay unwrapped on purpose, so the existing suite (which calls
them directly) is unaffected. The corollary is that nothing else in the suite exercises
the wrapped path — these tests are the only coverage it has.
"""
import asyncio
import inspect

import hcl_mcp.server as S


def _structured(res):
    """Unwrap a ToolResult's payload.

    circadian_metrics is annotated `dict | list` (server.py:141): a union return type has
    no single JSON-object schema, so FastMCP wraps structured_content as {"result": ...}
    and flags it via meta.fastmcp.wrap_result (fastmcp/tools/base.py:334-339). That
    wrapping is a pre-existing property of the tool's own annotation, present even in the
    unwrapped `_raw_server()` comparison in test_tool_registration.py — nothing this task
    adds. Unwrap it here rather than asserting into the wrong nesting level.
    """
    sc = getattr(res, "structured_content", None)
    if sc is None:
        return getattr(res, "data", None)
    meta = getattr(res, "meta", None) or {}
    if isinstance(meta, dict) and meta.get("fastmcp", {}).get("wrap_result"):
        return sc.get("result")
    return sc


def test_every_registered_tool_including_aliases_is_wrapped():
    """The alias loop registers the raw module functions, so wrapping only the main
    loop leaves get_reference / list_presets / import_weather / run_validation
    un-advised — and invisibly so, because those names keep working."""
    tools = asyncio.run(S.mcp.list_tools())
    unwrapped = [t.name for t in tools
                 if not hasattr(getattr(t, "fn", None), "__wrapped__")]
    assert unwrapped == [], f"registered but not wrapped: {unwrapped}"


def test_wrapper_preserves_coroutine_nature():
    for fn in S._TOOL_FUNCS:
        w = S._with_advisories(fn)
        assert inspect.iscoroutinefunction(w) == inspect.iscoroutinefunction(fn), fn.__name__


def test_attach_adds_advisories_when_a_rule_fires():
    out = S._attach("circadian_metrics", {}, {"mel_der_source": "binned_channels"})
    assert [a["code"] for a in out["advisories"]] == ["MEL_DER_BINNED"]


def test_attach_omits_the_key_entirely_when_clean():
    out = S._attach("circadian_metrics", {}, {"mel_der_source": "spd"})
    assert "advisories" not in out


def test_attach_does_not_mutate_the_original_result():
    original = {"mel_der_source": "binned_channels"}
    S._attach("circadian_metrics", {}, original)
    assert "advisories" not in original


def test_attach_passes_non_dict_results_through_untouched():
    assert S._attach("circadian_metrics", {}, [{"a": 1}]) == [{"a": 1}]
    assert S._attach("validate", {}, None) is None


def test_advisories_appear_on_a_live_registered_call():
    """Single-point channels with no spd -> a dict result on the binned mel-DER route."""
    res = asyncio.run(S.mcp.call_tool("circadian_metrics",
                                      {"channels": [0.1] * 9, "channel_type": 1}))
    payload = _structured(res)
    assert payload is not None
    assert [a["code"] for a in payload["advisories"]] == ["MEL_DER_BINNED"]
