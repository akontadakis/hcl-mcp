"""Named ambient-quality presets, so the accuracy/runtime trade-off is chosen, not inherited.

The shipped rtrace default (-ab 2 -ad 512) is a preview setting, and on a real annual run it
moved sDA by 22 percentage points against a converged solve on unchanged geometry. Leaving that
as an unnamed default meant an agent picked it by not choosing. These presets make the choice
explicit and carry the caveat that belongs with each level.

Values follow the Radiance parameter tables: Min / Fast / Accurate / Very-accurate / Max for
-ab, -aa, -ar, -ad, -as.
"""
import pytest

from hcl_radiance.commands import (
    QUALITY_PRESETS, quality_params, quality_preset_table, ambient_convergence_note,
)

ORDER = ["low", "medium", "high", "extra_high"]


def test_all_four_levels_exist():
    assert [p for p in QUALITY_PRESETS if p in ORDER] == ORDER


def test_each_level_documents_use_and_caveat():
    for name in ORDER:
        p = QUALITY_PRESETS[name]
        assert p["use_for"].strip(), f"{name} has no stated use"
        assert p["caveat"].strip(), f"{name} has no stated caveat"
        assert p["rad_params"].strip()


def test_quality_params_returns_a_usable_rad_params_string():
    s = quality_params("high")
    assert "-ab" in s and "-ad" in s and "-aa" in s and "-ar" in s


def test_unknown_level_raises_with_the_valid_names():
    with pytest.raises(ValueError) as e:
        quality_params("ultra")
    for name in ORDER:
        assert name in str(e.value)


def _p(name, flag):
    toks = quality_params(name).split()
    return float(toks[toks.index(flag) + 1])


@pytest.mark.parametrize("flag,increasing", [("-ab", True), ("-ad", True), ("-as", True),
                                             ("-ar", True), ("-aa", False)])
def test_parameters_move_monotonically_with_quality(flag, increasing):
    """Higher quality means more bounces/divisions/resolution, and LOWER -aa (it is an error
    tolerance, so smaller is stricter). A preset table that is not monotonic is a bug."""
    vals = [_p(n, flag) for n in ORDER]
    pairs = list(zip(vals, vals[1:]))
    if increasing:
        assert all(a <= b for a, b in pairs), f"{flag} not non-decreasing: {vals}"
    else:
        assert all(a >= b for a, b in pairs), f"{flag} not non-increasing: {vals}"
    assert vals[0] != vals[-1], f"{flag} identical at both ends: {vals}"


def test_low_is_preview_grade_and_says_so():
    assert ambient_convergence_note(quality_params("low")) is not None


def test_high_and_extra_high_are_converged():
    assert ambient_convergence_note(quality_params("high")) is None
    assert ambient_convergence_note(quality_params("extra_high")) is None


def test_low_does_no_indirect_calculation():
    """Per the reference table, quality-low is -ab 0: direct only."""
    assert _p("low", "-ab") == 0


def test_supersamples_are_about_half_the_divisions_where_used():
    """-as is only useful in proportion to -ad; the guidance is a half to a quarter of it."""
    for name in ("high", "extra_high"):
        ad, as_ = _p(name, "-ad"), _p(name, "-as")
        assert 0.2 * ad <= as_ <= 0.6 * ad, f"{name}: -as {as_} vs -ad {ad}"


def test_table_is_renderable_for_a_human_choosing_upfront():
    t = quality_preset_table()
    assert isinstance(t, list) and len(t) == len(ORDER)
    for row in t:
        assert {"name", "rad_params", "use_for", "caveat", "relative_cost"} <= set(row)


def test_relative_cost_is_ordered():
    costs = [QUALITY_PRESETS[n]["relative_cost"] for n in ORDER]
    assert costs == sorted(costs) and costs[0] < costs[-1]


# --- MCP surface -------------------------------------------------------------------------------

def test_quality_presets_is_actually_registered_as_a_tool():
    """Importing the function is not the same as exposing it.

    quality_presets shipped defined, documented and unit-tested, but missing from server.py's
    registration tuple, so no MCP client could call it: `quality=` was selectable on eight tools
    while the tool that explains the levels was unreachable. Every other test here imports the
    function directly and so passed throughout. This one goes through the server's own tool list.
    """
    import asyncio
    from hcl_mcp.server import mcp
    names = {t.name for t in asyncio.run(mcp._list_tools())}
    assert "quality_presets" in names


def test_mcp_tool_lists_every_level_with_its_caveat():
    from hcl_mcp.server import quality_presets
    out = quality_presets()
    assert [r["name"] for r in out["presets"]] == ORDER
    assert all(r["caveat"] for r in out["presets"])


def test_mcp_tool_returns_one_level():
    from hcl_mcp.server import quality_presets
    assert quality_presets("high")["name"] == "high"


def test_mcp_tool_raises_on_an_unknown_level():
    """Was an in-band {"error": ...}, which left FastMCP's is_error False -- so a client's error
    path never fired and a typo'd level read as a successful lookup. Every sibling validation
    failure in server.py raises; this one now matches, and still names the valid levels."""
    import pytest as _pytest
    from hcl_mcp.server import quality_presets
    with _pytest.raises(ValueError) as exc:
        quality_presets("ultra")
    msg = str(exc.value)
    assert "ultra" in msg
    for level in ORDER:
        assert level in msg, f"{level!r} missing from the error message"


def test_explicit_rad_params_beats_quality():
    """A tuned string must never be silently overridden by a named level."""
    from hcl_mcp.server import _resolve_rad_params
    assert _resolve_rad_params("-ab 7 -ad 99", "low") == "-ab 7 -ad 99"


def test_quality_is_used_when_no_rad_params_given():
    from hcl_mcp.server import _resolve_rad_params
    assert _resolve_rad_params(None, "high") == quality_params("high")


def test_neither_given_falls_through_to_the_default():
    from hcl_mcp.server import _resolve_rad_params
    assert _resolve_rad_params(None, None) is None
    assert _resolve_rad_params(None, None, default="-ab 1") == "-ab 1"
