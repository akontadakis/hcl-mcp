import hcl_mcp.server as srv
import hcl_mcp.resources as res

def test_server_object_exists():
    assert srv.mcp is not None and srv.mcp.name == "hcl-mcp"

def test_core_tool_functions_work():
    # The tool functions are plain callables registered on the server.
    ch = srv.spd_to_channels([(380, 1.0), (780, 1.0)], channel_type=1)
    assert ch["channels"] == [1.0] * 9
    m = srv.circadian_metrics([1.0] * 9, channel_type=1)
    assert round(m["melanopic_lux"], 6) == 179.0
    a = srv.alpha_opic(channels=[0.1] * 9, channel_type=1, alpha=5)
    assert a["EDI"] > 0
    assert srv.validate()["ok"] is True

def test_reference_resource_returns_text():
    assert "0.265" in res.reference_coefficients()

def test_ensure_points_path_passes_a_path_through(tmp_path):
    # A string is already a .pts path -> returned unchanged, nothing written.
    assert srv._ensure_points_path("/some/where.pts", str(tmp_path)) == "/some/where.pts"
    assert list(tmp_path.iterdir()) == []

def test_ensure_points_path_materializes_inline_rows(tmp_path):
    # Inline [x,y,z,dx,dy,dz] rows are written to a .pts under work_dir; the file round-trips.
    rows = [[0.0, 0.0, 0.8, 0.0, 0.0, 1.0], [1.5, 2.0, 0.8, 0.0, 0.0, 1.0]]
    p = srv._ensure_points_path(rows, str(tmp_path), name="nvrd_points.pts")
    assert p == str(tmp_path / "nvrd_points.pts")
    text = (tmp_path / "nvrd_points.pts").read_text()
    assert text == "0.0 0.0 0.8 0.0 0.0 1.0\n1.5 2.0 0.8 0.0 0.0 1.0\n"
    # The written file is a valid points path the transports can stream back.
    assert srv._ensure_points_path(p, str(tmp_path)) == p

import asyncio

def test_new_tools_present():
    import hcl_mcp.server as srv
    # FastMCP 3.x list_tools() returns a LIST of Tool objects (each with .name), not a dict.
    names = {t.name for t in asyncio.run(srv.mcp.list_tools())}
    assert {"spectral_metrics", "compliance", "presets"} <= names

def test_convert_eml_medi_not_a_separate_tool():
    # GAP-5: EML<->EDI is folded into spectral_metrics; no standalone 11th tool.
    import hcl_mcp.server as srv
    names = {t.name for t in asyncio.run(srv.mcp.list_tools())}
    assert "convert_eml_medi" not in names

def test_spectral_metrics_scalar_eml_edi_fold():
    import hcl_mcp.server as srv
    out = srv.spectral_metrics(eml_edi_value=250, eml_edi_direction="medi_to_eml")
    assert out["eml_edi"]["result"] == 275.75

def test_presets_resource_includes_illustrative_leds():
    import hcl_mcp.server as srv, json
    out = json.loads(res.preset_resource("LED_4000K"))
    assert len(out["spd"]) == 401

def test_resource_templates_present():
    import hcl_mcp.server as srv
    tmpls = asyncio.run(srv.mcp.list_resource_templates())
    uris = {str(t.uri_template) for t in tmpls}
    assert any("preset" in u for u in uris) and any("action-spectrum" in u for u in uris)
    # templates are self-documenting (title carried through registration)
    for t in tmpls:
        assert t.title, f"{t.uri_template} missing title"

def test_prompts_present():
    import hcl_mcp.server as srv
    names = {p.name for p in asyncio.run(srv.mcp.list_prompts())}
    assert {"spd_to_circadian", "explain_concept"} <= names

def test_spectral_sky_prompt_registered():
    # The physical spectral-sky-from-EPW path must have its own guiding prompt (9th prompt), and it
    # must coexist with the same-named TOOL (separate MCP registries).
    import hcl_mcp.server as srv
    prompt_names = {p.name for p in asyncio.run(srv.mcp.list_prompts())}
    tool_names = {t.name for t in asyncio.run(srv.mcp.list_tools())}
    assert "spectral_sky_from_epw" in prompt_names
    assert "spectral_sky_from_epw" in tool_names
    body = srv.spectral_sky_from_epw_prompt("Athens office")
    assert "atmosphere_from_epw" in body and "spectral_sky_from_epw" in body and "alpha_opic" in body

def test_preset_resource_fn():
    import hcl_mcp.server as srv
    import json
    out = json.loads(res.preset_resource("D65"))
    assert len(out["spd"]) == 401

def test_write_material_async_with_roots(tmp_path):
    import hcl_mcp.server as srv
    res = asyncio.run(srv.write_material([0.88, 0.85, 0.80], material_type=0, channel_type=0,
                                         name="g", work_dir=str(tmp_path)))
    assert res["files"][0].endswith("g.rad")

def test_spectral_metrics_spd_mode_includes_eml_edi_fold():
    import hcl_mcp.server as srv
    from hcl_core.presets import get_preset
    out = srv.spectral_metrics(spd=get_preset("D65"))
    assert set(out) == {"cct_duv", "mel_der", "mel_photopic_ratio", "eml_edi"}
    assert {"mel_edi", "eml"} <= set(out["eml_edi"])
    assert {"units", "scale_note"} <= set(out["eml_edi"])  # additive scale caveat metadata
    # eml should be mel_edi * 1.103 (EML_PER_MEDI), rounded
    assert out["eml_edi"]["eml"] == round(out["eml_edi"]["mel_edi"] * 1.103, 2)


def test_spectral_metrics_invalid_metric_raises():
    import hcl_mcp.server as srv
    from hcl_core.presets import get_preset
    import pytest
    with pytest.raises(ValueError):
        srv.spectral_metrics(spd=get_preset("D65"), metric="bogus")

def test_action_spectrum_resource_invalid_type_raises():
    import hcl_mcp.server as srv
    import pytest
    with pytest.raises(ValueError):
        res.action_spectrum_resource("BOGUS")

import asyncio
from hcl_mcp.server import atmosphere_from_epw, spectral_sky_from_epw, spectral_epw

_EPW_HEADER = "\n".join([
    "LOCATION,Athens,-,GRC,TMY,167160,37.90,23.73,2.0,28.0",
    "DESIGN CONDITIONS,0", "TYPICAL/EXTREME PERIODS,0", "GROUND TEMPERATURES,0",
    "HOLIDAYS/DAYLIGHT SAVINGS,No,0,0,0", "COMMENTS 1,", "COMMENTS 2,",
    "DATA PERIODS,1,1,Data,Sunday, 1/ 1,12/31",
])


def _epw_row(month, hour, db, dew, rh, pr, ghi, dni, dhi):
    v = ["2020", str(month), "21", str(hour), "0", "C9C9C9"] + ["0"] * 29
    v[6] = str(db); v[7] = str(dew); v[8] = str(rh); v[9] = str(pr)
    v[13] = str(ghi); v[14] = str(dni); v[15] = str(dhi); v[32] = "0.2"
    return ",".join(v)


def _make_epw(tmp_path):
    p = tmp_path / "s.epw"
    p.write_text(_EPW_HEADER + "\n" + _epw_row(6, 12, 28, 12, 40, 101300, 800, 850, 120) + "\n")
    return str(p)


def test_atmosphere_from_epw_tool(tmp_path):
    out = atmosphere_from_epw(_make_epw(tmp_path), 6, 21, 12)
    assert "aod500" in out and "pw_cm" in out and "provenance" in out


def test_spectral_sky_from_epw_tool(tmp_path):
    out = spectral_sky_from_epw(_make_epw(tmp_path), 6, 21, 12)
    assert out["timestamp"] == [6, 21, 12]
    assert len(out["direct_normal"]) == 401
    assert "ground" not in out
    out2 = spectral_sky_from_epw(_make_epw(tmp_path), 6, 21, 12, surface_tilt_deg=90.0)
    assert len(out2["ground"]) == 401


def test_spectral_epw_writes_artifacts(tmp_path):
    epw = _make_epw(tmp_path)
    out = asyncio.run(spectral_epw(epw, forms=["spd_set", "band_matrix"],
                                   hours=[[6, 21, 12]], work_dir=str(tmp_path)))
    assert set(out["files"].keys()) == {"spd_set", "band_matrix"}
    for path in out["files"].values():
        assert __import__("os").path.isfile(path)

def test_spectral_input_tools_registered():
    import hcl_mcp.server as srv
    names = {t.name for t in asyncio.run(srv.mcp.list_tools())}
    assert {"colored_sky", "colored_luminaire", "reference"} <= names

def test_reference_tool_topics():
    import hcl_mcp.server as srv
    assert srv.reference("coefficients")["photopic_3"] == [0.265, 0.670, 0.065]
    assert "section_9_3" in srv.reference("caveats")

def test_colored_sky_emits_without_radiance(tmp_path, monkeypatch):
    import hcl_radiance.sky as sky
    monkeypatch.setattr(sky, "_available", lambda: False)
    import asyncio, hcl_mcp.server as srv
    out = asyncio.run(srv.colored_sky([0.8, 0.9, 0.85], [0.8, 0.9, 0.85], channel_type=0,
                                      month=6, day=21, hour=12.0, irrad_mode="W", mode="spectra",
                                      direct=800, diffuse=120,
                                      lat=47.6, lon=-122.3, utc=-8, work_dir=str(tmp_path), run=True))
    assert out["ran"] is False and any("gendaylit 6 21 12.0 -W 800 120" in c for c in out["commands"])

def test_colored_sky_luminance_mode_via_tool(tmp_path):
    import asyncio, hcl_mcp.server as srv
    out = asyncio.run(srv.colored_sky([], [], channel_type=0, month=6, day=21, hour=12.0,
                                      irrad_mode="W", mode="luminance", direct=800, diffuse=120,
                                      lat=47.6, lon=-122.3, utc=-8, work_dir=str(tmp_path), run=False))
    rad = out["sky_defs"][0]
    assert rad.startswith("!gendaylit 6 21 12.0 -C -W 800 120")
    assert "4 1 1 1 0" in rad and "4 1 0.8 0.5 0" in rad

def test_colored_sky_luminance_9channel_errors(tmp_path):
    import asyncio, pytest, hcl_mcp.server as srv
    with pytest.raises(ValueError, match="luminance mode is 3-channel only"):
        asyncio.run(srv.colored_sky([], [], channel_type=1, month=6, day=21, hour=12.0,
                                    irrad_mode="W", mode="luminance", direct=800, diffuse=120,
                                    lat=47.6, lon=-122.3, utc=-8, work_dir=str(tmp_path), run=False))


def test_reference_unknown_topic_raises():
    import pytest, hcl_mcp.server as srv
    with pytest.raises(ValueError, match="unknown reference topic"):
        srv.reference("bogus")
    # overview is a valid explicit topic, not a silent fallback
    assert "overview" in srv.reference("overview")

def test_colored_luminaire_is_non_destructive(tmp_path):
    import asyncio, hcl_mcp.server as srv
    src = tmp_path / "lamp.rad"
    src.write_text("void light lamp_mat\n0\n0\n3 1 1 1\nlamp_mat polygon lamp\n")
    before = src.read_text()
    out = asyncio.run(srv.colored_luminaire(str(src), list(range(9)), count=1,
                                            work_dir=str(tmp_path / "work")))
    # source file untouched; a NEW file written and its path returned
    assert src.read_text() == before and "3 1 1 1" in before
    assert out["file"].endswith(".rad") and out["file"] != str(src)
    import os as _os
    assert _os.path.isfile(out["file"])
    assert "3 3 4 5" in open(out["file"]).read() and "3 3 4 5" in out["rad"]

def test_colored_luminaire_names_from_real_file_basename(tmp_path):
    import asyncio, hcl_mcp.server as srv
    src = tmp_path / "downlight.rad"; src.write_text("void light m\n0\n0\n3 1 1 1\n")
    out = asyncio.run(srv.colored_luminaire(str(src), list(range(9)), count=1,
                                            work_dir=str(tmp_path / "w")))
    assert out["file"].endswith("downlight_colored.rad")

def test_colored_luminaire_raw_text_uses_generic_name(tmp_path):
    import asyncio, hcl_mcp.server as srv
    # Embeds a path-like token ("/scenes/foo.rad") so the OLD string-sniff
    # (os.path.sep in rad_path) would have misclassified this inline text as a file
    # path and named the output "foo_colored.rad". os.path.exists correctly returns
    # the generic stem since this multi-line string is not a real file.
    rad_text = "void light m\n0\n0\n3 1 1 1\nm polygon /scenes/foo.rad\n"
    out = asyncio.run(srv.colored_luminaire(rad_text, list(range(9)), count=1,
                                            work_dir=str(tmp_path / "w")))
    assert out["file"].endswith("luminaire_colored.rad")

def test_radiance_status_tool_registered_and_callable():
    import asyncio, hcl_mcp.server as srv
    names = {t.name for t in asyncio.run(srv.mcp.list_tools())}
    assert {"radiance_status", "run_grid"} <= names
    st = srv.radiance_status()
    assert set(["available", "bin_dir", "version", "found", "missing"]) <= set(st.keys())
    assert isinstance(st["available"], bool)

def test_run_image_registered():
    import hcl_mcp.server as srv
    names = {t.name for t in asyncio.run(srv.mcp.list_tools())}
    assert "run_image" in names

def test_nvrd_tool_registered_and_runs():
    import hcl_mcp.server as srv
    names = {t.name for t in asyncio.run(srv.mcp.list_tools())}
    assert "nvrd" in names
    out = srv.nvrd([[0.01] * 311 for _ in range(12)], timestep_h=0.1)
    assert len(out["relative_response"]) == 12

import pytest

def test_lighting_controls_and_daylight_savings_tools_present():
    import hcl_mcp.server as srv
    names = {t.name for t in asyncio.run(srv.mcp.list_tools())}
    assert {"lighting_controls", "daylight_savings"} <= names

def test_lighting_controls_point_in_time():
    import hcl_mcp.server as srv
    out = srv.lighting_controls(itot_per_point=[122.543, 24.427], weights=[0.6071428571, 0.3928571429],
                                iset=500, control_type="ContinuousOff", fP_min=0.15, fL_min=0.05,
                                n_steps=3, p_rated=448)
    assert out["FP"] == pytest.approx(0.84968881, abs=1e-6)
    assert out["reduction"] == pytest.approx(0.15031119, abs=1e-6)

def test_lighting_controls_annual_series():
    import hcl_mcp.server as srv
    series = [[300.0, 200.0]] * 8760
    out = srv.lighting_controls(itot_series=series, weights=[0.6071428571, 0.3928571429],
                                area=28.0, iset=500, control_type="ContinuousOff", fP_min=0.15,
                                fL_min=0.05, n_steps=3, p_rated=448)
    assert out["occupied_hours"] == 2610
    assert out["annual_kwh_per_m2"] > 0

def test_daylight_savings_run_false_emits_plan(tmp_path):
    import hcl_mcp.server as srv
    out = asyncio.run(srv.daylight_savings(
        scene_sets=[["m.rad", "sky.rad", "g.rad"]], points=[[1, 1, 0.8, 0, 0, 1], [3, 3, 0.8, 0, 0, 1]],
        channel_type=0,   # one scene_set -> 3-channel; run_grid validates 3 sets for channel_type=1
        weights=[0.6071428571, 0.3928571429], mode="point_in_time", iset=500,
        control_type="ContinuousOff", fP_min=0.15, fL_min=0.05, n_steps=3, p_rated=448,
        work_dir=str(tmp_path), run=False))
    assert out["ran"] is False
    assert "commands" in out and out["mode"] == "point_in_time"

def test_daylight_savings_annual_run_false_emits_plan(tmp_path):
    import hcl_mcp.server as srv
    out = asyncio.run(srv.daylight_savings(
        channel_scenes=[{"materials": "m.rad", "geometry": "g.rad", "sky_color": [1, 1, 1]}],
        wea="w.wea", points="p.pts", channel_type=0, weights=[1.0],  # annual v1 = single point
        area=28.0, mode="annual", iset=500, control_type="ContinuousOff", fP_min=0.15,
        fL_min=0.05, n_steps=3, p_rated=448, work_dir=str(tmp_path), run=False))
    assert out["ran"] is False and out["mode"] == "annual"


def test_lighting_controls_requires_weights():
    import hcl_mcp.server as srv
    with pytest.raises(ValueError):
        srv.lighting_controls(itot_per_point=[122.543, 24.427])  # weights omitted

def test_daylight_savings_rejects_unknown_mode(tmp_path):
    import hcl_mcp.server as srv
    with pytest.raises(ValueError):
        asyncio.run(srv.daylight_savings(
            scene_sets=[["m.rad", "sky.rad", "g.rad"]], points=[[1, 1, 0.8, 0, 0, 1]],
            channel_type=0, weights=[1.0], mode="bogus", work_dir=str(tmp_path), run=False))


def test_lighting_controls_reference_resource():
    import hcl_mcp.server as srv
    txt = res.lighting_controls_reference()
    assert "fL" in txt and "ContinuousOff" in txt and "floor" in txt
    assert "FP" in txt and "Iset" in txt

def test_en12464_compliance_resource():
    import hcl_mcp.server as srv, json
    out = json.loads(res.en_12464_1_resource())
    assert out["tasks"]["office_writing_reading"]["em"] == 500
    assert out["tasks"]["corridor_circulation"]["ugrl"] == 28

def test_electric_lighting_design_prompt_present():
    import hcl_mcp.server as srv
    names = {p.name for p in asyncio.run(srv.mcp.list_prompts())}
    assert "electric_lighting_design" in names

def test_electric_lighting_design_prompt_text():
    import hcl_mcp.server as srv
    txt = srv.electric_lighting_design("an open-plan office")
    assert "daylight_savings" in txt and "EN 12464-1" in txt

def test_annual_daylight_study_prompt_registered():
    import hcl_mcp.server as srv
    names = {p.name for p in asyncio.run(srv.mcp.list_prompts())}
    assert "annual_daylight_study" in names

def test_annual_daylight_study_prompt_text():
    import hcl_mcp.server as srv
    txt = srv.annual_daylight_study("a 6x4x3 m office")
    # chains the three climate-based daylight tools over a persistent sensor set
    for tool in ("sensors", "annual_daylight", "daylight_factor", "daylight_savings"):
        assert tool in txt
    # names the key metrics and the direct-only ASE caveat
    assert "sDA" in txt and "ASE" in txt and "-ab 0" in txt
    assert "sensor_set" in txt

def test_lighting_controls_resources_registered():
    import hcl_mcp.server as srv
    tmpls = asyncio.run(srv.mcp.list_resources())
    uris = {str(getattr(t, "uri", "")) for t in tmpls}
    assert any("lighting-controls" in u for u in uris)
    assert any("en_12464_1" in u for u in uris)


def test_en12464_resource_surround_grading_matches_helper():
    import hcl_mcp.server as srv, json
    from hcl_core.compliance import en_12464_surround_minimum
    rel = json.loads(res.en_12464_1_resource())["relationships"]["surround"]
    # The documented bands must match the actual helper.
    assert "750->500" in rel and "500->300" in rel and "300->200" in rel
    assert "200->150" not in rel  # the invented step must not reappear
    assert en_12464_surround_minimum(750) == 500 and en_12464_surround_minimum(200) == 200


def test_daylight_savings_point_in_time_surfaces_radiance_error(monkeypatch, tmp_path):
    # run_grid can return {"ran": True, "error": ..., "failed_step": ...} when a Radiance step fails
    # (non-zero returncode) with NO "daylight" key. daylight_savings must surface that, not KeyError.
    import hcl_mcp.server as srv
    monkeypatch.setattr(srv, "_run_grid",
                        lambda *a, **k: {"ran": True, "error": "oconv failed", "failed_step": "oconv"})
    out = asyncio.run(srv.daylight_savings(
        scene_sets=[["m.rad", "sky.rad", "g.rad"]], points=[[1, 1, 0.8, 0, 0, 1]],
        channel_type=0, weights=[1.0], mode="point_in_time", work_dir=str(tmp_path), run=True))
    assert out["ran"] is True and out["mode"] == "point_in_time"
    assert out["error"] == "oconv failed" and out["failed_step"] == "oconv"
    assert "controls" not in out


def test_daylight_savings_annual_surfaces_radiance_error(monkeypatch, tmp_path):
    import hcl_mcp.server as srv
    monkeypatch.setattr(srv, "_run_annual_daylight",
                        lambda *a, **k: {"ran": True, "error": "rfluxmtx failed", "failed_step": "rfluxmtx"})
    out = asyncio.run(srv.daylight_savings(
        channel_scenes=[{"materials": "m.rad", "geometry": "g.rad", "sky_color": [1, 1, 1]}],
        wea="w.wea", points="p.pts", channel_type=0, weights=[1.0], area=28.0,
        mode="annual", work_dir=str(tmp_path), run=True))
    assert out["ran"] is True and out["mode"] == "annual"
    assert out["error"] == "rfluxmtx failed" and out["failed_step"] == "rfluxmtx"
    assert "controls" not in out


def test_daylight_savings_point_in_time_validates_weights_before_running(monkeypatch, tmp_path):
    # Missing weights must raise BEFORE the (expensive) grid simulation runs.
    import hcl_mcp.server as srv

    def _boom(*a, **k):
        raise AssertionError("simulation must not run when weights is invalid")

    monkeypatch.setattr(srv, "_run_grid", _boom)
    with pytest.raises(ValueError):
        asyncio.run(srv.daylight_savings(
            scene_sets=[["m.rad", "sky.rad", "g.rad"]], points=[[1, 1, 0.8, 0, 0, 1]],
            channel_type=0, mode="point_in_time", work_dir=str(tmp_path), run=True))  # weights omitted


def test_daylight_savings_annual_rejects_weight_point_mismatch(monkeypatch, tmp_path):
    # weights count must match the reference-point count; mismatch raises BEFORE simulating.
    import hcl_mcp.server as srv

    def _boom(*a, **k):
        raise AssertionError("simulation must not run when weights/points mismatch")

    monkeypatch.setattr(srv, "_run_annual_daylight", _boom)
    with pytest.raises(ValueError):
        asyncio.run(srv.daylight_savings(
            channel_scenes=[{"materials": "m.rad", "geometry": "g.rad", "sky_color": [1, 1, 1]}],
            wea="w.wea", points=[[1, 1, 0.8, 0, 0, 1]], channel_type=0,
            weights=[0.5, 0.5], area=28.0, mode="annual", work_dir=str(tmp_path), run=True))


def test_daylight_savings_annual_surfaces_applied_weights(monkeypatch, tmp_path):
    # Annual mode coerces a missing/empty weights to a uniform default; that applied default must
    # be surfaced in the success payload (additive "applied_weights" key) so the AI client can see it.
    import hcl_mcp.server as srv
    monkeypatch.setattr(srv, "_run_annual_daylight", lambda *a, **k: {
        "ran": True, "n_points": 1, "n_timesteps": 2,
        "lux_matrix": [[300.0, 120.0]], "sun_lux_matrix": None})
    out = asyncio.run(srv.daylight_savings(
        channel_scenes=[{"materials": "m.rad", "geometry": "g.rad", "sky_color": [1, 1, 1]}],
        wea="w.wea", points="p.pts", channel_type=0, area=28.0, mode="annual",
        schedule=[1, 1], work_dir=str(tmp_path), run=True))   # weights omitted -> [1.0]
    assert out["ran"] is True and out["mode"] == "annual"
    assert out["applied_weights"] == [1.0] and "controls" in out


def test_reconstruct_spectrum_tool_registered_and_runs():
    import hcl_mcp.server as srv
    names = {t.name for t in asyncio.run(srv.mcp.list_tools())}
    assert "reconstruct_spectrum" in names
    out = srv.reconstruct_spectrum(
        sky_channels=[0.2, 0.22, 0.25, 0.30, 0.28, 0.24, 0.18, 0.14, 0.10],
        sun_channels=[0.05, 0.06, 0.07, 0.09, 0.08, 0.07, 0.06, 0.05, 0.04],
        channel_type=1, method="reference", solar_zenith=30.0)
    assert len(out["spectrum"]) == 401
    assert set(out["divergence"]) == {"flat_vs_reference", "neutral_vs_colored_sun"}

def test_annual_nvrd_tool_registered():
    import hcl_mcp.server as srv
    names = {t.name for t in asyncio.run(srv.mcp.list_tools())}
    assert "annual_nvrd" in names

def test_annual_nvrd_tool_emits_without_radiance(tmp_path):
    import hcl_mcp.server as srv
    epw = tmp_path / "w.epw"
    epw.write_text("LOCATION,Test,WA,USA,Custom,000000,47.6,-122.3,-8.0,20.0\n")
    out = asyncio.run(srv.annual_nvrd(
        point_xyz=[1, 2, 3], view_vec=[0, 0, 1], epw=str(epw),
        channel_scenes=[{"materials": "m.rad", "geometry": "g.rad", "sky_color": [0.3, 0.4, 0.5]}],
        points="pts.pts", channel_type=0,
        work_dir=str(tmp_path), run=False))
    assert out["ran"] is False and "commands" in out
    assert "relative_RD_note" in out  # honesty caveat always present

def test_nvrd_bridge_resource_and_prompt_registered():
    import hcl_mcp.server as srv
    uris = {str(r.uri) for r in asyncio.run(srv.mcp.list_resources())}
    assert "hcl://reference/nvrd-bridge" in uris
    prompts = {p.name for p in asyncio.run(srv.mcp.list_prompts())}
    assert "annual_alertness" in prompts
    text = res.nvrd_bridge_reference()
    assert "relative" in text.lower() and "±20" in text  # caveats surfaced


def test_recommend_fixtures_tool_returns_contract():
    from hcl_mcp.server import recommend_fixtures
    out = recommend_fixtures(length_m=6, width_m=4, height_m=3, mount_height_m=2.8,
                             target_em_lux=500, target_mel_edi=250)
    assert out["fixture_count"] >= 1
    assert out["binding_constraint"] in ("visual", "circadian")
    assert "required_flux_lm" in out


def test_save_and_load_brief_tools(tmp_path):
    import asyncio
    from hcl_mcp.server import save_brief, load_brief
    asyncio.run(save_brief(study="t1", brief={"goal": {"mel_edi_target": 250}},
                           work_dir=str(tmp_path)))
    out = asyncio.run(load_brief(study="t1", work_dir=str(tmp_path)))
    assert out["goal"]["mel_edi_target"] == 250


def test_build_report_tool_writes_files(tmp_path):
    import asyncio, os
    from hcl_mcp.server import build_report
    out = asyncio.run(build_report(study="rt", brief={"study": "rt",
                      "goal": {"standard": "well_l03", "mel_edi_target": 250}},
                      work_dir=str(tmp_path)))
    assert out["md_path"].endswith("report.md")
    assert os.path.exists(out["html_path"])


def test_weather_rejects_malformed_period():
    import pytest, hcl_mcp.server as srv
    with pytest.raises(ValueError, match="period must be"):
        srv.weather(period=[[6, 21, 12]])            # only one endpoint
    with pytest.raises(ValueError, match="period must be"):
        srv.weather(period=[[6, 21], [6, 21, 14]])   # endpoint not length-3


def test_weather_warns_when_subset_out_without_wea(tmp_path):
    import hcl_mcp.server as srv
    out = srv.weather(period=[[6, 21, 12], [6, 21, 14]], subset_out=str(tmp_path / "s.wea"))
    assert "decomposed" in out and "subset_wea" not in out
    assert "warning" in out and "wea_path" in out["warning"]


def test_verb_object_aliases_present_alongside_terse_names():
    import asyncio, hcl_mcp.server as srv
    names = {t.name for t in asyncio.run(srv.mcp.list_tools())}
    assert {"reference", "presets", "weather", "validate"} <= names   # terse preserved
    assert {"get_reference", "list_presets", "import_weather", "run_validation"} <= names


def test_emit_envelope_emit_shape():
    import hcl_mcp.server as srv
    env = srv.emit_envelope(False, commands=["a", "b"], reason="no radiance", mode="annual")
    assert env == {"ran": False, "commands": ["a", "b"], "reason": "no radiance", "mode": "annual"}

def test_emit_envelope_ran_shape_drops_none():
    import hcl_mcp.server as srv
    env = srv.emit_envelope(True, result={"file": "/x.rad"}, mode="point_in_time")
    assert env == {"ran": True, "file": "/x.rad", "mode": "point_in_time"}
    assert "commands" not in env and "reason" not in env

def test_colored_luminaire_envelope_marks_ran(tmp_path):
    import asyncio, hcl_mcp.server as srv
    src = tmp_path / "l.rad"; src.write_text("void light m\n0\n0\n3 1 1 1\n")
    out = asyncio.run(srv.colored_luminaire(str(src), list(range(9)), count=1,
                                            work_dir=str(tmp_path / "w")))
    assert out["ran"] is True and out["file"].endswith(".rad") and "rad" in out


# ============================================================================
# MCP-3: emit-path / pure invocation tests for the six wrappers whose
# arg-mapping/kwarg-threading was previously only registration-checked.
# These drive each wrapper through the MCP boundary (not just list_tools) to
# lock down kwarg passthrough + return shape. Characterization tests: they
# assert current (correct) behavior.
# ============================================================================

def test_run_image_emit_threads_optional_kwargs(tmp_path, monkeypatch):
    # run_image is async + ctx-bearing; it threads electric_lights/glare/glare_params/rad_params
    # ONLY when truthy, and always passes channel_type/view/x/y/fov_weighting/mask_dir/work_dir/run.
    import asyncio, hcl_mcp.server as srv
    captured = {}
    monkeypatch.setattr(srv, "_run_image",
                        lambda scene_sets, **kw: captured.update(kw) or
                        {"ran": False, "commands": ["rpict ..."], "reason": "no radiance"})
    out = asyncio.run(srv.run_image(
        scene_sets=[["m.rad", "sky.rad"]], channel_type=0,
        electric_lights=[{"ies": "l.ies"}], glare=True, glare_params="-vth",
        rad_params="-ab 2", work_dir=str(tmp_path), run=False))
    assert out["ran"] is False and out["commands"]
    # optional kwargs forwarded because truthy
    assert captured["electric_lights"] == [{"ies": "l.ies"}]
    assert captured["glare"] is True
    assert captured["glare_params"] == "-vth"
    assert captured["rad_params"] == "-ab 2"
    # always-threaded kwargs
    assert captured["channel_type"] == 0 and captured["run"] is False
    assert captured["work_dir"] == str(tmp_path)


def test_run_image_emit_omits_falsy_optional_kwargs(tmp_path, monkeypatch):
    # When the optional toggles are falsy/None, run_image must NOT forward them
    # (so the backend defaults apply). glare defaults False; electric_lights/rad_params None.
    import asyncio, hcl_mcp.server as srv
    captured = {}
    monkeypatch.setattr(srv, "_run_image",
                        lambda scene_sets, **kw: captured.update(kw) or {"ran": False, "commands": ["x"]})
    asyncio.run(srv.run_image(scene_sets=[["m.rad", "sky.rad"]], channel_type=0,
                              work_dir=str(tmp_path), run=False))
    assert "electric_lights" not in captured
    assert "glare" not in captured
    assert "glare_params" not in captured
    assert "rad_params" not in captured
    assert captured["channel_type"] == 0 and captured["run"] is False


def test_run_annual_emit_threads_kwargs(tmp_path, monkeypatch):
    # run_annual (async, ctx-bearing) always threads work_dir/run/dosimetry_threshold/period/
    # timestep_min, and rad_params only when truthy.
    import asyncio, hcl_mcp.server as srv
    captured = {}
    monkeypatch.setattr(srv, "_run_annual",
                        lambda channel_scenes, wea, points, channel_type, **kw:
                        captured.update(kw) or {"ran": False, "commands": ["rfluxmtx ..."]})
    out = asyncio.run(srv.run_annual(
        channel_scenes=[{"materials": "m.rad", "geometry": "g.rad", "sky_color": [1, 1, 1]}],
        wea="w.wea", points="p.pts", channel_type=0, rad_params="-ab 5",
        dosimetry_threshold=300.0, period=[[6, 21, 8], [6, 21, 18]], timestep_min=30,
        work_dir=str(tmp_path), run=False))
    assert out["ran"] is False and out["commands"]
    assert captured["dosimetry_threshold"] == 300.0
    assert captured["period"] == [[6, 21, 8], [6, 21, 18]]
    assert captured["timestep_min"] == 30
    assert captured["rad_params"] == "-ab 5"
    assert captured["run"] is False and captured["work_dir"] == str(tmp_path)


def test_run_annual_emit_defaults_and_omits_falsy_rad_params(tmp_path, monkeypatch):
    # Defaults: dosimetry_threshold=250.0, timestep_min=60, period=None. rad_params omitted when None.
    import asyncio, hcl_mcp.server as srv
    captured = {}
    monkeypatch.setattr(srv, "_run_annual",
                        lambda channel_scenes, wea, points, channel_type, **kw:
                        captured.update(kw) or {"ran": False, "commands": ["x"]})
    asyncio.run(srv.run_annual(
        channel_scenes=[{"materials": "m.rad", "geometry": "g.rad", "sky_color": [1, 1, 1]}],
        wea="w.wea", points="p.pts", channel_type=0, work_dir=str(tmp_path), run=False))
    assert captured["dosimetry_threshold"] == 250.0
    assert captured["timestep_min"] == 60
    assert captured["period"] is None
    assert "rad_params" not in captured


def test_weather_pure_decompose_returns_shape():
    # weather is sync; with period only (no wea_path) it returns just the decomposed block:
    # months/days/hours/HOY/HOYround/wea_lines. No "wea" key when wea_path is omitted.
    import hcl_mcp.server as srv
    out = srv.weather(period=[[6, 21, 12], [6, 21, 14]])
    assert set(out) == {"decomposed"}
    d = out["decomposed"]
    assert {"months", "days", "hours", "HOY", "HOYround", "wea_lines"} <= set(d)
    assert len(d["wea_lines"]) == len(d["HOY"]) and len(d["wea_lines"]) >= 1


def test_glass_transmissivity_scalar_and_list():
    # glass_transmissivity is sync; scalar -> scalar transmissivity, list -> list (same length).
    import hcl_mcp.server as srv
    scalar = srv.glass_transmissivity(0.88)
    assert set(scalar) == {"transmissivity"}
    assert isinstance(scalar["transmissivity"], float) and 0.0 < scalar["transmissivity"] < 1.0
    lst = srv.glass_transmissivity([0.88, 0.85, 0.80])
    assert isinstance(lst["transmissivity"], list) and len(lst["transmissivity"]) == 3
    assert all(0.0 < t < 1.0 for t in lst["transmissivity"])


def test_presets_list_and_fetch_by_name():
    # presets is sync; no name -> {"presets": [...]}; with name -> {name, spd(401), meta}.
    import hcl_mcp.server as srv
    listing = srv.presets()
    assert set(listing) == {"presets"}
    assert isinstance(listing["presets"], list) and "D65" in listing["presets"]
    one = srv.presets("D65")
    assert set(one) == {"name", "spd", "meta"}
    assert one["name"] == "D65" and len(one["spd"]) == 401
    assert "family" in one["meta"]


def test_compliance_returns_verdict_dict():
    # compliance is sync (mel_edi/eml/standard/period/daylight_met). Returns a verdict dict
    # with standard/result/threshold/citation for a real standard.
    import hcl_mcp.server as srv
    out = srv.compliance(mel_edi=250, standard="brown_2022", period="daytime")
    assert out["standard"] == "brown_2022"
    assert out["result"] == "pass"
    assert "threshold" in out and "citation" in out
    # a clearly-failing value flips the verdict
    fail = srv.compliance(mel_edi=10, standard="brown_2022", period="daytime")
    assert fail["result"] != "pass"


def test_compliance_tool_forwards_en_12464_1_task_params():
    # The EN 12464-1 branch is scored on task/em/ugr/uo/ra -- NOT on a mel_edi. The core has
    # always supported it, but the MCP wrapper did not forward those arguments, so the whole
    # electric-task standard was unreachable over MCP: `standard="en_12464_1"` arrived with
    # task=None and raised "unknown EN 12464-1 task None". Both the operating guide (workflow A
    # step 4) and the electric_lighting_design / hcl_studio prompts instruct clients to call it
    # this way, so the documented path crashed.
    import hcl_mcp.server as srv
    out = srv.compliance(standard="en_12464_1", task="office_writing_reading",
                         em=520, ugr=17, uo=0.62, ra=85)
    assert out["standard"].startswith("EN 12464-1")
    assert out["result"] == "pass"
    assert out["parameters"]["em"]["required"] == 500
    assert out["parameters"]["ugr"]["limit"] == 19


def test_compliance_tool_forwards_en_12464_1_surround_and_surface_params():
    # The surround/background/wall/ceiling/cylindrical relationships are separate arguments;
    # forwarding only task/em/ugr/uo/ra would silently drop them and under-report the verdict.
    import hcl_mcp.server as srv
    out = srv.compliance(standard="en_12464_1", task="office_writing_reading", em=520,
                         em_surround=320, uo_surround=0.45, em_background=120, uo_background=0.12,
                         em_wall=60, uo_wall=0.12, em_ceiling=40, uo_ceiling=0.11,
                         em_cylindrical=160, uo_cylindrical=0.15)
    assert out["relationships"]["surround"]["required_em"] == 300
    assert out["relationships"]["background"]["met"] is True
    assert out["surfaces"]["wall"]["required_em"] == 50
    assert out["surfaces"]["ceiling"]["required_em"] == 30
    assert out["surfaces"]["cylindrical"]["required_em"] == 50


def test_compliance_tool_en_12464_1_no_params_is_incomplete_not_pass():
    # Supplying the standard but no measured values must not green-light an empty design.
    import hcl_mcp.server as srv
    out = srv.compliance(standard="en_12464_1", task="office_writing_reading")
    assert out["result"] == "incomplete"


# GAP 1 (CORE-3): a RELATIVE SPD passed through the user-facing MCP tools must
# surface a scale_warning; an ABSOLUTE SPD must not.
def test_alpha_opic_tool_flags_relative_spd():
    import hcl_mcp.server as srv
    out = srv.alpha_opic(spd=[(380, 1.0), (780, 1.0)], alpha=5)
    assert out.get("scale_warning") and "relative" in out["scale_warning"].lower()


def test_alpha_opic_tool_flags_relative_spd_all_alpha():
    # alpha=None -> nested {melanopic:{...}, ...}; warning attached top-level, numbers untouched.
    import hcl_mcp.server as srv
    out = srv.alpha_opic(spd=[(380, 1.0), (780, 1.0)])
    assert out.get("scale_warning") and "relative" in out["scale_warning"].lower()
    assert "melanopic" in out and "EDI" in out["melanopic"]


def test_alpha_opic_tool_no_warning_for_absolute_spd():
    import hcl_mcp.server as srv
    out = srv.alpha_opic(spd=[(380, 100.0), (780, 100.0)], alpha=5)
    assert out.get("scale_warning") in (None,)  # absent or None


def test_alpha_opic_tool_channels_path_has_no_scale_warning():
    # channel path is not an SPD-scale path; must be untouched.
    import hcl_mcp.server as srv
    out = srv.alpha_opic(channels=[0.1] * 9, channel_type=1, alpha=5)
    assert out.get("scale_warning") in (None,)


def test_spectral_metrics_tool_flags_relative_spd():
    # scale_warning surfaced in the eml_edi block (the scale-dependent block) for relative input.
    import hcl_mcp.server as srv
    out = srv.spectral_metrics(spd=[(380, 1.0), (780, 1.0)])
    assert out["eml_edi"].get("scale_warning") and "relative" in out["eml_edi"]["scale_warning"].lower()


def test_spectral_metrics_tool_no_warning_for_absolute_spd():
    import hcl_mcp.server as srv
    out = srv.spectral_metrics(spd=[(380, 100.0), (780, 100.0)])
    assert out["eml_edi"].get("scale_warning") in (None,)


from hcl_mcp.server import reconstruct_spectrum as _tool_reconstruct


def test_server_reconstruct_spectrum_accepts_sun_spd():
    sky = [10.0] * 9
    sun = [5.0] * 9
    red_ref = [float(i) for i in range(401)]
    out = _tool_reconstruct(sky, sun, channel_type=1, method="reference", sun_spd=red_ref)
    base = _tool_reconstruct(sky, sun, channel_type=1, method="reference")
    assert out["n"] == 401
    assert out["spectrum"] != base["spectrum"]      # the injected sun reference changed the result

def test_annual_nvrd_mcp_forwards_physical_sky(monkeypatch):
    import asyncio, hcl_mcp.server as srv
    captured = {}
    def fake_core(**kw):
        captured.update(kw)
        return {"ran": False}
    async def fake_wd(ctx, work_dir):
        return work_dir or "/tmp/x"
    monkeypatch.setattr(srv, "_annual_nvrd", fake_core)
    monkeypatch.setattr(srv, "resolve_work_dir", fake_wd)
    asyncio.run(srv.annual_nvrd(point_xyz=[1, 2, 3], view_vec=[0, 0, 1], epw=None,
                                channel_scenes=None, points=None, run=False,
                                physical_sky=True, ctx=None))
    assert captured.get("physical_sky") is True

def test_annual_nvrd_mcp_materializes_inline_points(monkeypatch, tmp_path):
    # Parity with run_annual: inline [x,y,z,dx,dy,dz] rows passed to the MCP
    # wrapper are written to a .pts under work_dir; the backend receives a path it can stream.
    import asyncio, os
    captured = {}
    def fake_core(**kw):
        captured.update(kw)
        return {"ran": False}
    async def fake_wd(ctx, work_dir):
        return work_dir or str(tmp_path)
    monkeypatch.setattr(srv, "_annual_nvrd", fake_core)
    monkeypatch.setattr(srv, "resolve_work_dir", fake_wd)
    asyncio.run(srv.annual_nvrd(point_xyz=[1, 2, 3], view_vec=[0, 0, 1], epw=None,
                                channel_scenes=None, points=[[0, 0, 0.8, 0, 0, 1]],
                                run=False, work_dir=str(tmp_path), ctx=None))
    pts = captured.get("points")
    assert isinstance(pts, str) and os.path.isfile(pts)  # a list became a real .pts path
    assert "0 0 0.8 0 0 1" in open(pts).read()


def test_spectral_sky_native_emits_without_radiance6(tmp_path):
    import asyncio
    from hcl_mcp.server import spectral_sky_native
    out = asyncio.run(spectral_sky_native("site.epw", work_dir=str(tmp_path), run=True))
    # System Radiance has no gensdaymtx → emit path.
    assert "commands" in out or out.get("ran") is True


def test_spectral_sky_from_epw_engine_default_records_spectrl2(tmp_path):
    out = spectral_sky_from_epw(_make_epw(tmp_path), 6, 21, 12)
    assert out["provenance"]["engine"] == "spectrl2"


def test_spectral_sky_from_epw_explicit_spectrl2_matches_default(tmp_path):
    a = spectral_sky_from_epw(_make_epw(tmp_path), 6, 21, 12)
    b = spectral_sky_from_epw(_make_epw(tmp_path), 6, 21, 12, engine="spectrl2")
    assert a["direct_normal"] == b["direct_normal"]
    assert a["sky_diffuse_horizontal"] == b["sky_diffuse_horizontal"]


def test_spectral_sky_from_epw_unknown_engine_raises(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        spectral_sky_from_epw(_make_epw(tmp_path), 6, 21, 12, engine="bogus")


def test_spectral_sky_from_epw_smarts_without_binary_raises(tmp_path, monkeypatch):
    import pytest
    monkeypatch.delenv("SMARTSPATH", raising=False)
    with pytest.raises(RuntimeError):
        spectral_sky_from_epw(_make_epw(tmp_path), 6, 21, 12, engine="smarts")


def test_spectral_epw_engine_default_unchanged(tmp_path):
    epw = _make_epw(tmp_path)
    out = asyncio.run(spectral_epw(epw, forms=["spd_set"], hours=[[6, 21, 12]],
                                   work_dir=str(tmp_path), engine="spectrl2"))
    assert set(out["files"].keys()) == {"spd_set"}
    assert out["n_records"] == 1


def test_server_annual_nvrd_smarts_no_binary_only_raises_when_physical(monkeypatch):
    # Hermetic: monkeypatch _annual_nvrd (mirrors test_annual_nvrd_mcp_forwards_physical_sky) so the
    # physical_sky=False branch can't fail for unrelated reasons. The physical_sky=True branch raises
    # at resolve_engine BEFORE reaching _annual_nvrd, so the patch is irrelevant there.
    import asyncio, pytest, hcl_mcp.server as srv
    monkeypatch.delenv("SMARTSPATH", raising=False)
    captured = {}
    def fake_core(**kw):
        captured.update(kw)
        return {"ran": False}
    async def fake_wd(ctx, work_dir):
        return work_dir or "/tmp/x"
    monkeypatch.setattr(srv, "_annual_nvrd", fake_core)
    monkeypatch.setattr(srv, "resolve_work_dir", fake_wd)

    # physical_sky=False -> engine unused -> must NOT raise; engine_obj passed down as None.
    out = asyncio.run(srv.annual_nvrd(point_xyz=[1, 2, 3], view_vec=[0, 0, 1], epw=None,
                                      channel_scenes=None, points=None, run=False,
                                      physical_sky=False, engine="smarts", ctx=None))
    assert out == {"ran": False}
    assert captured.get("engine") is None

    # physical_sky=True with smarts + no binary -> resolve_engine raises RuntimeError early.
    with pytest.raises(RuntimeError):
        asyncio.run(srv.annual_nvrd(point_xyz=[1, 2, 3], view_vec=[0, 0, 1], epw=None,
                                    channel_scenes=None, points=None, run=False,
                                    physical_sky=True, engine="smarts", ctx=None))


import asyncio
from hcl_mcp import server

def test_annual_attribution_is_not_registered():
    """Attribution moved to a companion study outside this repo; the tool must be gone."""
    import asyncio
    names = [t.name for t in asyncio.run(server.mcp.list_tools())]
    assert "annual_attribution" not in names
    # 47 registered functions + 4 verb-object aliases. The running tally, most recent last:
    # 44 unique, + quality_presets, which was defined but left out of the registration tuple
    # until 2026-07-23 (see test_quality_presets.py), + check_geometry (task 12, 2026-07-23):
    # the standalone iterate-while-fixing entry point for the geometry health check,
    # + lm83_daylight (2026-08-12): IES LM-83-12 sDA/ASE with operated blinds.
    assert len(names) == 51


def test_hcl_core_does_not_import_hcl_radiance():
    """Removing attribution_metrics leaves hcl_core with no reach into hcl_radiance (README:375).

    Must check real imports via AST, NOT raw text: six hcl_core modules legitimately mention
    hcl_radiance in prose/docstrings (surface_library, proc, daylight_metrics,
    lighting_controls, ies). Only an actual import breaks the layering claim.
    """
    import ast, pathlib
    core = pathlib.Path(server.__file__).parent.parent / "hcl_core"
    offenders = []
    for p in core.rglob("*.py"):
        for node in ast.walk(ast.parse(p.read_text())):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("hcl_radiance"):
                offenders.append(p.name)
            elif isinstance(node, ast.Import) and any(
                    a.name.startswith("hcl_radiance") for a in node.names):
                offenders.append(p.name)
    assert sorted(set(offenders)) == []
