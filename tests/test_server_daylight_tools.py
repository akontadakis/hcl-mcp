import asyncio
from hcl_mcp import server

def test_sensors_create_list_get_delete(tmp_path):
    wd = str(tmp_path)
    run = asyncio.run
    c = run(server.sensors("create", name="grid1",
                            grid={"interior": [0, 4, 0, 3], "floor_z": 0.0, "max_spacing": 1.0},
                            work_dir=wd))
    assert c["count"] > 0
    assert [s["name"] for s in run(server.sensors("list", work_dir=wd))["sensor_sets"]] == ["grid1"]
    g = run(server.sensors("get", name="grid1", work_dir=wd))
    assert len(g["points"]) == c["count"]
    run(server.sensors("delete", name="grid1", work_dir=wd))
    assert run(server.sensors("list", work_dir=wd))["sensor_sets"] == []

def test_resolve_points_prefers_sensor_set(tmp_path):
    wd = str(tmp_path)
    asyncio.run(server.sensors("create", name="s", points=[[1, 1, 0.8, 0, 0, 1]], work_dir=wd))
    path = server._resolve_points(None, "s", wd)
    assert path.endswith("s.pts")

def test_annual_daylight_computes_metrics(monkeypatch, tmp_path):
    import asyncio
    from hcl_mcp import server
    # stub the runner: 2 points x 4 timesteps, point0 bright, point1 dark; no direct sun
    def fake_runner(channel_scenes, wea, points, channel_type, **kw):
        return {"ran": True, "n_points": 2, "n_timesteps": 4,
                "lux_matrix": [[500, 500, 500, 500], [50, 50, 50, 50]],
                "sun_lux_matrix": [[0, 0, 0, 0], [0, 0, 0, 0]]}
    monkeypatch.setattr(server, "_run_annual_daylight", fake_runner)
    out = asyncio.run(server.annual_daylight(
        [{"materials": ["m.rad"], "geometry": "g.rad", "sky_color": [1, 1, 1]}],
        "in.wea", points=[[0, 0, 0.8, 0, 0, 1], [1, 0, 0.8, 0, 0, 1]], channel_type=0,
        occupancy=[1, 1, 1, 1], work_dir=str(tmp_path), run=True))
    assert out["ran"] is True
    assert out["metrics"]["spatial"]["sDA"] == 0.5
    assert out["metrics"]["per_point"][0]["DA"] == 1.0
    assert out["metrics"]["spatial"]["ASE"] == 0.0

def test_annual_daylight_rejects_mismatched_occupancy_length(monkeypatch, tmp_path):
    import asyncio
    import pytest
    from hcl_mcp import server
    # stub the runner: 2 points x 4 timesteps
    def fake_runner(channel_scenes, wea, points, channel_type, **kw):
        return {"ran": True, "n_points": 2, "n_timesteps": 4,
                "lux_matrix": [[500, 500, 500, 500], [50, 50, 50, 50]],
                "sun_lux_matrix": [[0, 0, 0, 0], [0, 0, 0, 0]]}
    monkeypatch.setattr(server, "_run_annual_daylight", fake_runner)
    with pytest.raises(ValueError, match="occupancy length"):
        asyncio.run(server.annual_daylight(
            [{"materials": ["m.rad"], "geometry": "g.rad", "sky_color": [1, 1, 1]}],
            "in.wea", points=[[0, 0, 0.8, 0, 0, 1], [1, 0, 0.8, 0, 0, 1]], channel_type=0,
            occupancy=[1, 1, 1], work_dir=str(tmp_path), run=True))

def test_daylight_factor_tool(monkeypatch, tmp_path):
    import asyncio
    from hcl_mcp import server
    def fake_df(scene_sets, indoor_points, **kw):
        return {"ran": True, "df_per_point": [20.0], "df_avg": 20.0, "df_min": 20.0,
                "uniformity": 1.0, "e_outdoor": 1500.0}
    monkeypatch.setattr(server, "_run_daylight_factor", fake_df)
    out = asyncio.run(server.daylight_factor([["m.rad", "g.rad"]],
                                             points=[[1, 1, 0.8, 0, 0, 1]],
                                             work_dir=str(tmp_path), run=True))
    assert out["ran"] is True
    assert out["df_per_point"] == [20.0]
    assert out["df_avg"] == 20.0

def test_daylight_savings_annual_multipoint(monkeypatch, tmp_path):
    import asyncio
    from hcl_mcp import server
    # 2 points x 3 hours
    def fake_runner(channel_scenes, wea, points, channel_type, **kw):
        return {"ran": True, "n_points": 2, "n_timesteps": 3,
                "lux_matrix": [[600, 600, 0], [600, 0, 0]], "sun_lux_matrix": [[0] * 3, [0] * 3]}
    monkeypatch.setattr(server, "_run_annual_daylight", fake_runner)
    # no confirmation prompt: with ctx=None confirm_run proceeds without asking
    out = asyncio.run(server.daylight_savings(
        channel_scenes=[{"materials": ["m.rad"], "geometry": "g.rad", "sky_color": [1, 1, 1]}],
        wea="in.wea", points=[[0, 0, 0.8, 0, 0, 1], [1, 0, 0.8, 0, 0, 1]],
        channel_type=0, mode="annual", weights=[0.5, 0.5], area=20.0,
        schedule=[1, 1, 1], work_dir=str(tmp_path), run=True))
    assert out["ran"] is True and out["mode"] == "annual"
    assert out["controls"]["occupied_hours"] == 3

def test_new_daylight_tools_registered():
    from hcl_mcp import server
    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert "annual_daylight" in names
    assert "daylight_factor" in names
    assert "sensors" in names
