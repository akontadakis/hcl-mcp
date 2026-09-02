"""Regression tests for the defects found in the end-to-end MCP validation (2026-06-27).

Each test reproduces one reported defect. See hcl_validation/results/VALIDATION-REPORT.md.
"""
import asyncio
import json

import pytest

import hcl_mcp.server as srv

# A minimal OBJ with two surface groups (walls + glass), Y-up, mm.
_OBJ_TWO_GROUPS = """\
# sample room
v 0 0 0
v 1000 0 0
v 1000 800 0
vn 0 0 1
usemtl walls
f 1 2 3
usemtl glass
f 1 2 3
"""


# --- DEF-1: glass_transmissivity param must be typed (untyped -> MCP delivers a string -> crash) ---
def test_glass_transmissivity_param_is_typed():
    tools = {t.name: t for t in asyncio.run(srv.mcp.list_tools())}
    schema = tools["glass_transmissivity"].parameters["properties"]["transmittance"]
    blob = json.dumps(schema)
    assert schema, "transmittance had an empty (untyped) schema -> MCP passes a string -> arithmetic crash"
    assert "number" in blob and "array" in blob, f"must accept a number or a list, got {blob}"


# --- DEF-2: run_grid points must be typed so an inline row list isn't stringified to a path ---
def test_run_grid_points_param_is_typed():
    tools = {t.name: t for t in asyncio.run(srv.mcp.list_tools())}
    schema = tools["run_grid"].parameters["properties"]["points"]
    blob = json.dumps(schema)
    assert schema, "points had an empty (untyped) schema -> MCP stringifies a row list into a path"
    assert "array" in blob and "string" in blob, f"must accept rows (array) or a .pts path (string), got {blob}"


# --- DEF-3: run_annual must accept materials as a list (what import_geometry returns), not only a string ---
def test_run_annual_accepts_materials_as_list(tmp_path):
    out = asyncio.run(srv.run_annual(
        channel_scenes=[{"materials": ["a.rad", "b.rad"], "geometry": "g.rad", "sky_color": [1, 1, 1]}],
        wea="w.wea", points="p.pts", channel_type=0, work_dir=str(tmp_path), run=False))
    assert out["ran"] is False
    # the sky oconv step must list BOTH material files + the geometry (no nested list)
    assert any("oconv" in c and "a.rad" in c and "b.rad" in c and "g.rad" in c
               for c in out["commands"]), out["commands"]


def test_run_annual_materials_string_still_space_joined(tmp_path):
    # back-compat: a space-joined string keeps working and stays byte-identical for a single path
    out = asyncio.run(srv.run_annual(
        channel_scenes=[{"materials": "a.rad b.rad", "geometry": "g.rad", "sky_color": [1, 1, 1]}],
        wea="w.wea", points="p.pts", channel_type=0, work_dir=str(tmp_path), run=False))
    assert any("oconv" in c and "a.rad" in c and "b.rad" in c and "g.rad" in c
               for c in out["commands"]), out["commands"]


# --- DEF-4: run_annual degrades to emit-path when a required Reinhart .cal file is missing ---
def test_run_annual_degrades_when_cal_file_missing(tmp_path, monkeypatch):
    import hcl_radiance.annual as annual
    import hcl_radiance.annual_commands as ac
    monkeypatch.setattr(annual, "_available", lambda: True)  # pretend Radiance is installed
    libdir = tmp_path / "lib"
    libdir.mkdir()
    (libdir / "reinhartb.cal").write_text("x")
    (libdir / "reinhart.cal").write_text("x")  # reinsrc.cal deliberately absent
    monkeypatch.setattr(ac, "_radiance_lib_dir", lambda: str(libdir))
    out = annual.run_annual(
        channel_scenes=[{"materials": "m.rad", "geometry": "g.rad", "sky_color": [1, 1, 1]}],
        wea="w.wea", points="p.pts", channel_type=0, work_dir=str(tmp_path), run=True)
    assert out["ran"] is False, out
    assert "reinsrc.cal" in (out.get("reason") or ""), out


# --- DEF-5: build_report must render dict-shaped compliance without dropping the verdict ---
def test_report_renders_dict_shaped_compliance(tmp_path):
    from hcl_mcp.studio import build_report_to_dir
    res = build_report_to_dir(str(tmp_path), "s1", {"compliance": {"brown_2022": "pass"}})
    md = open(res["md_path"]).read()
    seg = md.split("## Compliance")[1].split("##")[0]
    assert "brown_2022" in seg and "pass" in seg, f"verdict dropped: {seg!r}"


# --- DEF-6: build_report must render the study slug, not "?" ---
def test_report_renders_study_name_from_param(tmp_path):
    from hcl_mcp.studio import build_report_to_dir
    res = build_report_to_dir(str(tmp_path), "athens_office", {"goal": {"mel_edi_target": 250}})
    header = open(res["md_path"]).read().splitlines()[0]
    assert "athens_office" in header and "?" not in header, header


# --- DEF-7: daylight_savings must give a clear weight/point-count error (no internal "fps") ---
def test_daylight_savings_weights_point_count_mismatch_is_clear(tmp_path):
    with pytest.raises(ValueError) as exc:
        asyncio.run(srv.daylight_savings(
            scene_sets=[["m.rad", "sky.rad", "g.rad"]],
            points=[[1, 1, 0.8, 0, 0, 1], [3, 3, 0.8, 0, 0, 1]],
            channel_type=0, weights=[1.0], mode="point_in_time",
            work_dir=str(tmp_path), run=False))
    m = str(exc.value)
    assert "fps" not in m, m
    assert "2" in m and "1" in m and "weight" in m.lower() and "point" in m.lower(), m


# --- DEF-8: a forgotten `units` must not mask the more actionable unmapped-groups error ---
def test_import_geometry_unmapped_takes_precedence_over_missing_units(tmp_path):
    import hcl_radiance.geometry_import as gi
    p = tmp_path / "room.obj"
    p.write_text(_OBJ_TWO_GROUPS)
    with pytest.raises(gi.UnmappedGroupsError) as exc:
        gi.import_geometry(str(p), material_map={"walls": {"type": "plastic", "refl": 0.5}},
                           up_axis="Y", channel_type=1, work_dir=str(tmp_path), run=False)  # units omitted
    assert "glass" in str(exc.value)


def test_import_geometry_still_requires_units_when_groups_mapped(tmp_path):
    import hcl_radiance.geometry_import as gi
    p = tmp_path / "room.obj"
    p.write_text(_OBJ_TWO_GROUPS)
    with pytest.raises(ValueError) as exc:
        gi.import_geometry(str(p),
                           material_map={"walls": {"type": "plastic", "refl": 0.5},
                                         "glass": {"type": "glass", "tvis": 0.6}},
                           up_axis="Y", channel_type=1, work_dir=str(tmp_path), run=False)  # units omitted
    assert "units" in str(exc.value)


def test_build_report_tolerates_non_dict_phase_fields(tmp_path):
    # ISSUE-2 (same class as DEF-5): a malformed brief with a phase field given as a string instead
    # of a dict must render "not evaluated", not crash with "'str' object has no attribute 'get'".
    from hcl_mcp.studio import build_report_to_dir
    md = open(build_report_to_dir(str(tmp_path), "s",
              {"goal": "office", "space": "4x3", "sim_results": "n/a"})["md_path"]).read()
    assert "# HCL Study Report" in md and "_not evaluated_" in md


# === Completeness findings from reviewing the DEF-1..8 fixes (same defect classes) ===

# DEF-1/DEF-2 class: spd_to_channels.spd was the last untyped tool param. The docstring promises
# "list of [wavelength, value]", but an untyped arg is stringified over the wire and parse_spd then
# reads the Python repr as 2-column text and fails ("no wavelength rows").
def test_spd_to_channels_param_is_typed():
    tools = {t.name: t for t in asyncio.run(srv.mcp.list_tools())}
    schema = tools["spd_to_channels"].parameters["properties"]["spd"]
    blob = json.dumps(schema)
    assert schema, "spd had an empty (untyped) schema"
    assert "array" in blob and "string" in blob, f"must accept 2-col text or list of pairs, got {blob}"


def test_no_untyped_tool_params_remain():
    # Guard the whole class. A param is "typed" iff its schema carries a type-bearing key. An untyped
    # param WITH a default gets {"default": null, "title": ...} (NOT {}), yet still stringifies
    # structured values over the wire — so an exact-{} check is too narrow (it missed alpha_opic.spd,
    # spectral_metrics.spd, lighting_controls/daylight_savings.schedule).
    TYPED = {"type", "anyOf", "allOf", "oneOf", "$ref", "enum", "const"}
    tools = asyncio.run(srv.mcp.list_tools())
    offenders = [(t.name, p) for t in tools
                 for p, s in (t.parameters or {}).get("properties", {}).items()
                 if p != "ctx" and not (TYPED & set(s))]
    assert not offenders, f"untyped tool params still present: {offenders}"


@pytest.mark.parametrize("tool,param", [
    ("alpha_opic", "spd"), ("spectral_metrics", "spd"),
    ("lighting_controls", "schedule"), ("daylight_savings", "schedule"),
])
def test_structured_params_accept_arrays(tool, param):
    # spd (list of [wl,val]) and schedule (per-hour list) must declare array support, else FastMCP
    # stringifies the list over the wire and parse_spd / controls_series mis-handle it (DEF-1 class).
    tools = {t.name: t for t in asyncio.run(srv.mcp.list_tools())}
    blob = json.dumps(tools[tool].parameters["properties"][param])
    assert "array" in blob, f"{tool}.{param} must accept a list over the wire: {blob}"


def test_run_sequence_append_preserves_prior_stdout(tmp_path):
    # "append": True must append, not truncate. suns_rad_steps relies on it: step 1 writes the
    # `void light solar` modifier, step 2 appends the solar discs. Without append the modifier def is
    # lost and oconv fails "undefined modifier solar".
    from hcl_core.proc import run_sequence
    steps = [
        {"cmd": ["echo", "void light solar"], "stdout": "suns.rad"},
        {"cmd": ["echo", "solar source sun"], "stdout": "suns.rad", "append": True},
    ]
    res = run_sequence(steps, work_dir=str(tmp_path), available=True, unavailable_reason="x")
    assert res["ran"] and res.get("returncode", 0) == 0, res
    body = (tmp_path / "suns.rad").read_text()
    assert "void light solar" in body and "solar source sun" in body, repr(body)


def test_render_uses_append_redirect():
    from hcl_core.proc import render
    assert ">>" in render({"cmd": ["echo", "x"], "stdout": "o.rad", "append": True})
    assert ">>" not in render({"cmd": ["echo", "x"], "stdout": "o.rad"})  # plain stays truncating


def test_suns_rad_steps_oformat_has_no_literal_quotes():
    # Latent annual bug (masked while reinsrc.cal was absent): the rcalc -o format carried literal
    # double-quotes, so suns.rad lines came out as "solar source sun ..." and oconv rejected them
    # ("undefined modifier"). The format must be unquoted; render() handles shell quoting.
    from hcl_radiance.annual_commands import suns_rad_steps
    cmd = suns_rad_steps("suns.rad")[1]["cmd"]
    ofmt = cmd[cmd.index("-o") + 1]
    assert '"' not in ofmt, f"-o format has literal quotes -> malformed suns.rad: {ofmt!r}"
    assert ofmt == "solar source sun 0 0 4 ${Dx} ${Dy} ${Dz} 0.533"


def test_daysim_runner_executes_via_hcl_daysim_bin(tmp_path, monkeypatch):
    # HCL_DAYSIM_BIN must drive EXECUTION, not just discovery. The Daysim runner builds bare-name
    # commands (portable emit plan), so at run time it must prepend HCL_DAYSIM_BIN to PATH — else a
    # binary that lives only there (not on PATH) raises FileNotFoundError mid-run.
    import hcl_daysim.runner as runner
    binp = tmp_path / "ds_shortterm"
    binp.write_text("#!/bin/sh\necho ok > marker.txt\n")
    binp.chmod(0o755)
    monkeypatch.setenv("HCL_DAYSIM_BIN", str(tmp_path))
    monkeypatch.setenv("PATH", "/usr/bin:/bin")  # ds_shortterm is NOT on PATH
    wd = tmp_path / "wd"
    wd.mkdir()
    res = runner.run_sequence([{"cmd": ["ds_shortterm"]}], work_dir=str(wd), available=True)
    assert res["ran"] is True and res.get("returncode", 0) == 0, res
    assert (wd / "marker.txt").exists(), "binary on HCL_DAYSIM_BIN was not executed"


def test_annual_nvrd_surfaces_cal_missing_reason(tmp_path, monkeypatch):
    # DEF-4 honesty: when the separated annual transport degrades for a missing Reinhart .cal,
    # annual_nvrd must surface that specific reason, not the generic Daysim/run message.
    import hcl_daysim.subhourly as subhourly
    import hcl_radiance.annual as annual
    monkeypatch.setattr(subhourly, "generate_subhourly_wea",
                        lambda *a, **k: {"ran": True, "commands": [], "wea": str(tmp_path / "sub.wea")})
    monkeypatch.setattr(annual, "run_annual_separated",
                        lambda *a, **k: {"ran": False, "commands": ["oconv ..."],
                                         "reason": "Radiance is installed but required Reinhart .cal "
                                                   "file(s) are missing from its lib: reinsrc.cal."})
    epw = tmp_path / "w.epw"
    epw.write_text("LOCATION,Test,WA,USA,Custom,000000,47.6,-122.3,-8.0,20.0\n")
    out = asyncio.run(srv.annual_nvrd(
        point_xyz=[1, 2, 3], view_vec=[0, 0, 1], epw=str(epw),
        channel_scenes=[{"materials": "m.rad", "geometry": "g.rad", "sky_color": [0.3, 0.4, 0.5]}],
        points="pts.pts", channel_type=0, work_dir=str(tmp_path), run=True))
    assert out["ran"] is False
    assert "reinsrc.cal" in (out.get("reason") or ""), out
