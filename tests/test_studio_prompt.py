from hcl_mcp.server import hcl_studio

def test_studio_prompt_mentions_all_phases_and_tools():
    text = hcl_studio(space_description="open-plan office, 6x4x3 m", daylight_aware=True)
    for kw in ("load_brief", "recommend_fixtures", "ies_analyze", "ies_to_radiance",
               "run_grid", "run_annual", "nvrd", "daylight_savings", "build_report", "save_brief"):
        assert kw in text, f"prompt missing reference to {kw}"
    assert "vertical" in text.lower()
    assert "no-daylight" in text.lower() or "not subtract" in text.lower()
    assert "6x4x3" in text or "open-plan" in text

def test_studio_prompt_daylight_branch_toggles():
    on = hcl_studio(space_description="x", daylight_aware=True)
    off = hcl_studio(space_description="x", daylight_aware=False)
    assert "daylight baseline" in on.lower()
    # pin the off-branch: the daylight-credit narrative must be gone, replaced by a "skipped" note
    assert "circadian budget" in on.lower() and "circadian budget" not in off.lower()
    assert "skipped" in off.lower()
    assert on != off

def test_studio_prompt_flags_fixture_sizing_as_illustrative():
    low = hcl_studio(space_description="x", daylight_aware=True).lower()
    assert "first-principles" in low or "illustrative" in low
    assert "real photometry" in low or "real ies" in low
