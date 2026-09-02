import hcl_radiance.annual as annual

def test_run_annual_separated_emits_when_unavailable(tmp_path):
    out = annual.run_annual_separated(
        channel_scenes=[{"materials": "m.rad", "geometry": "g.rad", "sky_color": [0.3, 0.4, 0.5]}],
        wea="w.wea", points="pts.pts", channel_type=0, work_dir=str(tmp_path), run=False)
    assert out["ran"] is False
    blob = " ".join(out["commands"])
    assert "rfluxmtx" in blob and "gendaymtx -m 1 -s -c" in blob and "rcontrib" in blob and "dctimestep" in blob
    # the result advertises the separated outputs (no combine)
    assert "sky_sets" not in out  # on emit there is no parsed data yet


import hcl_radiance.annual_nvrd as bridge

# synthetic per-timestep channels: 12 timesteps, 9-channel sky + sun (so timestep_h=0.1 is fine)
def _synthetic_provider():
    ts = [(1, 1, 8.0 + 0.1 * i) for i in range(12)]
    series = []
    for i in range(12):
        scale = 0.5 + 0.04 * i
        sky = [scale * v for v in [0.20, 0.22, 0.25, 0.30, 0.28, 0.24, 0.18, 0.14, 0.10]]
        sun = [scale * v for v in [0.05, 0.06, 0.07, 0.09, 0.08, 0.07, 0.06, 0.05, 0.04]]
        series.append((sky, sun))
    zeniths = [30.0 + 2.0 * i for i in range(12)]
    return {"timestamps": ts, "series": series, "channel_type": 1, "solar_zeniths": zeniths}

def test_annual_nvrd_both_methods_return_two_RD_series_and_divergence():
    out = bridge.annual_nvrd(point_xyz=[1, 2, 3], view_vec=[0, 0, 1], timestep_min=6,
                             reconstruction="both", _channel_provider=_synthetic_provider)
    assert set(out) >= {"faithful", "enhanced", "divergence", "relative_RD_note"}
    for key in ("faithful", "enhanced"):
        assert set(out[key]) >= {"R_D", "RD_cum"}
        assert len(out[key]["R_D"]) == 12
        assert all(0.0 <= r <= 1.0 for r in out[key]["R_D"])
        cum = out[key]["RD_cum"]
        assert all(cum[i + 1] >= cum[i] - 1e-9 for i in range(len(cum) - 1))  # non-decreasing
    assert set(out["divergence"]) == {"flat_vs_reference", "neutral_vs_colored_sun"}
    # the R_D-series divergence reports how much the reconstruction choice moves the actual result
    assert set(out["RD_series_divergence"]) == {"mean_abs", "max_abs", "final_cum_pct"}
    rsd = out["RD_series_divergence"]
    assert 0.0 <= rsd["mean_abs"] <= rsd["max_abs"] <= 1.0
    assert rsd["max_abs"] > 0.0   # the two reconstructions genuinely diverge (non-vacuous)
    assert all(isinstance(rsd[k], float) for k in rsd)

def test_annual_nvrd_production_path_requires_epw():
    import pytest
    # No _channel_provider and no epw -> clear error, not an opaque TypeError from open(None).
    with pytest.raises(ValueError, match="epw"):
        bridge.annual_nvrd(point_xyz=[1, 2, 3], view_vec=[0, 0, 1],
                           channel_scenes=[{"materials": "m", "geometry": "g", "sky_color": [0.3, 0.4, 0.5]}],
                           points="p.pts", channel_type=0, run=False)

def test_annual_nvrd_faithful_only():
    out = bridge.annual_nvrd(point_xyz=[1, 2, 3], view_vec=[0, 0, 1], reconstruction="faithful",
                             _channel_provider=_synthetic_provider)
    assert "faithful" in out and "enhanced" not in out

def test_annual_nvrd_faithful_path_uses_alpha_opic_reconstruction():
    # The faithful nvRD series must come from the flat irradiance_per_nm reconstruction.
    from hcl_core.spectral_reconstruct import assemble_nvrd_rows
    from hcl_core.nvrd import nvrd as _nvrd
    prov = _synthetic_provider()
    rows = assemble_nvrd_rows([1, 2, 3], [0, 0, 1], prov["timestamps"], prov["series"],
                              method="faithful", channel_type=1)
    expected = _nvrd([r[12:] for r in rows], timestep_h=0.1)
    out = bridge.annual_nvrd(point_xyz=[1, 2, 3], view_vec=[0, 0, 1], reconstruction="faithful",
                             _channel_provider=_synthetic_provider)
    assert out["faithful"]["R_D"] == expected["relative_response"]

def test_production_path_consumes_real_timestamps_and_zeniths(monkeypatch, tmp_path):
    # XCUT-1 regression: the production EPW->wea->nvRD bridge must feed the REAL per-timestep
    # timestamps + solar zeniths surfaced by generate_subhourly_wea straight into
    # assemble_nvrd_rows, and must NOT emit the constant-30 fallback note.
    import hcl_daysim.subhourly as subhourly
    import hcl_radiance.annual as annual_mod

    real_ts = [(6, 21, 8.0), (6, 21, 12.0), (6, 21, 16.0)]
    real_zen = [61.0, 18.0, 55.0]

    # generate_subhourly_wea (imported inside annual_nvrd from hcl_daysim.subhourly) -> real ts/zeniths
    def fake_wea(epw, *, timestep_min, work_dir, run):
        return {"ran": True, "commands": ["epw2wea"], "wea": str(tmp_path / "sub.wea"),
                "timestamps": real_ts, "solar_zeniths": real_zen}
    monkeypatch.setattr(subhourly, "generate_subhourly_wea", fake_wea)

    # separated annual transport -> minimal success (the regroup is patched, so sets shape is irrelevant)
    def fake_annual(channel_scenes, wea, points, channel_type, **kw):
        return {"ran": True, "commands": ["rfluxmtx"], "sky_sets": ["S"], "sun_sets": ["U"]}
    monkeypatch.setattr(annual_mod, "run_annual_separated", fake_annual)

    # regroup -> 3 timesteps of 9-channel vectors (one per real timestamp)
    def fake_regroup(sets, channel_type):
        return [[0.2] * 9, [0.3] * 9, [0.25] * 9]
    monkeypatch.setattr(bridge, "_regroup_to_channels", fake_regroup)

    # spy on assemble_nvrd_rows to capture exactly what the bridge forwards
    captured = []
    real_assemble = bridge.assemble_nvrd_rows
    def spy_assemble(point_xyz, view_vec, timestamps, series, **kw):
        captured.append({"timestamps": timestamps, "solar_zenith": kw.get("solar_zenith")})
        return real_assemble(point_xyz, view_vec, timestamps, series, **kw)
    monkeypatch.setattr(bridge, "assemble_nvrd_rows", spy_assemble)

    epw = tmp_path / "w.epw"
    epw.write_text("LOCATION,Test,WA,USA,Custom,000000,47.6,-122.3,-8.0,20.0\n")
    out = bridge.annual_nvrd(point_xyz=[1, 2, 3], view_vec=[0, 0, 1], epw=str(epw),
                             channel_scenes=[{"materials": "m.rad", "geometry": "g.rad",
                                              "sky_color": [0.3, 0.4, 0.5]}],
                             points="pts.pts", channel_type=1, reconstruction="enhanced",
                             work_dir=str(tmp_path), run=True)

    assert out["ran"] is True
    assert captured, "assemble_nvrd_rows was never called on the production path"
    assert captured[0]["timestamps"] == real_ts
    assert captured[0]["solar_zenith"] == real_zen
    # real zeniths present -> NO constant-30 fallback note
    assert "enhanced_solar_note" not in out


def test_production_path_empty_zeniths_do_not_resurrect_constant_fallback(monkeypatch, tmp_path):
    # If generate_subhourly_wea surfaces EMPTY lists, the hardened fallback must NOT silently
    # re-enable the synthetic-grid / constant-30 path: zeniths fall back to None (note fires),
    # and timestamps fall back to the synthetic uniform grid (not the empty list).
    import hcl_daysim.subhourly as subhourly
    import hcl_radiance.annual as annual_mod

    def fake_wea(epw, *, timestep_min, work_dir, run):
        return {"ran": True, "commands": ["epw2wea"], "wea": str(tmp_path / "sub.wea"),
                "timestamps": [], "solar_zeniths": []}
    monkeypatch.setattr(subhourly, "generate_subhourly_wea", fake_wea)

    def fake_annual(channel_scenes, wea, points, channel_type, **kw):
        return {"ran": True, "commands": ["rfluxmtx"], "sky_sets": ["S"], "sun_sets": ["U"]}
    monkeypatch.setattr(annual_mod, "run_annual_separated", fake_annual)

    def fake_regroup(sets, channel_type):
        return [[0.2] * 9, [0.3] * 9, [0.25] * 9]
    monkeypatch.setattr(bridge, "_regroup_to_channels", fake_regroup)

    captured = []
    real_assemble = bridge.assemble_nvrd_rows
    def spy_assemble(point_xyz, view_vec, timestamps, series, **kw):
        captured.append({"timestamps": timestamps, "solar_zenith": kw.get("solar_zenith")})
        return real_assemble(point_xyz, view_vec, timestamps, series, **kw)
    monkeypatch.setattr(bridge, "assemble_nvrd_rows", spy_assemble)

    epw = tmp_path / "w.epw"
    epw.write_text("LOCATION,Test,WA,USA,Custom,000000,47.6,-122.3,-8.0,20.0\n")
    out = bridge.annual_nvrd(point_xyz=[1, 2, 3], view_vec=[0, 0, 1], epw=str(epw),
                             channel_scenes=[{"materials": "m.rad", "geometry": "g.rad",
                                              "sky_color": [0.3, 0.4, 0.5]}],
                             points="pts.pts", channel_type=1, reconstruction="enhanced",
                             work_dir=str(tmp_path), run=True)

    # empty zeniths -> None -> fallback note fires; empty timestamps -> synthetic uniform grid (len 3)
    assert captured[0]["solar_zenith"] is None
    assert len(captured[0]["timestamps"]) == 3
    assert "enhanced_solar_note" in out


def test_annual_nvrd_emits_command_plan_when_no_provider(tmp_path):
    # run=False with a real EPW (location is read from the EPW, never passed by the caller)
    # -> emits the Daysim + annual command plan, no execution.
    epw = tmp_path / "w.epw"
    epw.write_text("LOCATION,Test,WA,USA,Custom,000000,47.6,-122.3,-8.0,20.0\n")
    out = bridge.annual_nvrd(point_xyz=[1, 2, 3], view_vec=[0, 0, 1], epw=str(epw),
                             channel_scenes=[{"materials": "m.rad", "geometry": "g.rad",
                                              "sky_color": [0.3, 0.4, 0.5]}],
                             points="pts.pts", channel_type=0,
                             work_dir=str(tmp_path), run=False)
    assert out["ran"] is False
    blob = " ".join(out["commands"])
    assert ("ds_shortterm" in blob or "epw2wea" in blob)   # Daysim sub-hourly step
    assert "rfluxmtx" in blob and "gendaymtx" in blob and "dctimestep" in blob  # annual transport
    # DEF-7: the reason must attribute the emit to run=False, NOT a misleading "Radiance not available"
    assert "run=False" in out["reason"]
    assert "not available" not in out["reason"].lower()


from dataclasses import dataclass as _dataclass

@_dataclass
class _Rec:
    grid_nm: list
    sky_diffuse_horizontal: list
    direct_normal: list

def _mk_rec(scale=1.0):
    grid = [380.0 + i for i in range(401)]
    return _Rec(grid, [scale * 0.5] * 401, [scale * 1.0] * 401)

def test_physical_spd_series_maps_and_counts():
    from hcl_radiance.annual_nvrd import _physical_spd_series
    idx = {(1, 1, 9): _mk_rec(), (1, 1, 10): _mk_rec()}
    ts = [(1, 1, 8.1), (1, 1, 9.0), (1, 1, 9.5), (1, 1, 12.0)]   # ceil -> 9, 9, 10, 12
    sky, sun, cov = _physical_spd_series(idx, ts, real_timestamps=True)
    assert sky[0] is not None and sky[1] is not None and sky[2] is not None and sky[3] is None
    assert len(sky[0]) == 401 and len(sun[0]) == 401
    assert cov == {"n_physical": 3, "n_template": 1, "coverage_pct": 75.0}

def test_physical_spd_series_synthetic_timestamps_all_template():
    from hcl_radiance.annual_nvrd import _physical_spd_series
    idx = {(1, 1, 1): _mk_rec()}
    ts = [(1, 1, 0.1), (1, 1, 0.2)]
    sky, sun, cov = _physical_spd_series(idx, ts, real_timestamps=False)
    assert sky == [None, None] and sun == [None, None]
    assert cov["n_physical"] == 0 and cov["n_template"] == 2

def test_physical_spd_series_night_record_counts_template():
    from hcl_radiance.annual_nvrd import _physical_spd_series
    night = _Rec([380.0 + i for i in range(401)], [0.0] * 401, [0.0] * 401)
    idx = {(1, 1, 9): night}
    sky, sun, cov = _physical_spd_series(idx, [(1, 1, 8.5)], real_timestamps=True)  # ceil(8.5)=9 -> night
    assert sky == [None] and cov["n_physical"] == 0 and cov["n_template"] == 1


def _record_map_provider():
    # synthetic_provider hours are 8.0..9.1 -> ceil -> hour-endings {8, 9, 10}; cover all three.
    grid = [380.0 + i for i in range(401)]
    rec = _Rec(grid, [2.0 - 0.003 * i for i in range(401)], [1.0 + 0.005 * i for i in range(401)])
    return {(1, 1, 8): rec, (1, 1, 9): rec, (1, 1, 10): rec}

def _partial_record_provider():
    grid = [380.0 + i for i in range(401)]
    rec = _Rec(grid, [0.5] * 401, [1.0 + 0.005 * i for i in range(401)])
    return {(1, 1, 9): rec}   # only hour-ending 9 -> covers the 10 steps 8.1..9.0; 8.0 and 9.1 miss

def test_annual_nvrd_physical_sky_changes_enhanced_only():
    base = bridge.annual_nvrd(point_xyz=[1, 2, 3], view_vec=[0, 0, 1], reconstruction="both",
                              _channel_provider=_synthetic_provider)
    phys = bridge.annual_nvrd(point_xyz=[1, 2, 3], view_vec=[0, 0, 1], reconstruction="both",
                              physical_sky=True, _channel_provider=_synthetic_provider,
                              _record_provider=_record_map_provider)
    assert phys["faithful"]["R_D"] == base["faithful"]["R_D"]      # faithful untouched
    assert phys["enhanced"]["R_D"] != base["enhanced"]["R_D"]       # enhanced moved by physics
    ps = phys["physical_sky"]
    assert ps["requested"] is True
    assert ps["n_physical"] == 12 and ps["n_template"] == 0 and ps["coverage_pct"] == 100.0

def test_annual_nvrd_physical_sky_false_is_unchanged():
    a = bridge.annual_nvrd(point_xyz=[1, 2, 3], view_vec=[0, 0, 1], reconstruction="both",
                           _channel_provider=_synthetic_provider)
    b = bridge.annual_nvrd(point_xyz=[1, 2, 3], view_vec=[0, 0, 1], reconstruction="both",
                           physical_sky=False, _channel_provider=_synthetic_provider)
    assert a["enhanced"]["R_D"] == b["enhanced"]["R_D"]
    assert "physical_sky" not in a and "physical_sky" not in b

def test_annual_nvrd_physical_sky_partial_coverage_reported():
    out = bridge.annual_nvrd(point_xyz=[1, 2, 3], view_vec=[0, 0, 1], reconstruction="enhanced",
                             physical_sky=True, _channel_provider=_synthetic_provider,
                             _record_provider=_partial_record_provider)
    ps = out["physical_sky"]
    assert ps["n_physical"] == 10 and ps["n_template"] == 2
    assert abs(ps["coverage_pct"] - (100.0 * 10 / 12)) < 1e-9

def _synthetic_provider_no_zeniths():
    prov = _synthetic_provider()
    prov["solar_zeniths"] = None
    return prov

def test_build_record_index_memoizes_and_degrades(monkeypatch):
    # The production EPW glue: one record_from_epw call per UNIQUE hour-ending; a ValueError (missing
    # row / LOCATION) leaves that hour absent (→ template). Monkeypatch keeps it EPW/binary-free.
    import hcl_core.spectral_pipeline as sp
    from hcl_radiance.annual_nvrd import _build_record_index
    calls = []
    def fake_rfe(epw, m, d, h, **kw):
        calls.append((m, d, h))
        if (m, d, h) == (6, 21, 10):
            raise ValueError("no row for this hour")   # per-hour degradation
        return _Rec([380.0 + i for i in range(401)], [0.5] * 401, [1.0] * 401)
    monkeypatch.setattr(sp, "record_from_epw", fake_rfe)
    ts = [(6, 21, 8.0 + 0.1 * i) for i in range(12)]    # hours 8.0..9.1 -> hour-endings {8, 9, 10}
    idx = _build_record_index("fake.epw", ts, real_timestamps=True)
    assert sorted(idx.keys()) == [(6, 21, 8), (6, 21, 9)]   # the ValueError hour (10) is absent
    assert calls == [(6, 21, 8), (6, 21, 9), (6, 21, 10)]   # exactly one call per unique hour-ending
    assert _build_record_index("fake.epw", ts, real_timestamps=False) == {}   # synthetic grid -> {}
    assert _build_record_index(None, ts, real_timestamps=True) == {}          # no epw -> {}

def test_annual_nvrd_physical_sky_divergence_uses_physical_sky_spd():
    base = bridge.annual_nvrd(point_xyz=[1, 2, 3], view_vec=[0, 0, 1], reconstruction="both",
                              _channel_provider=_synthetic_provider)
    phys = bridge.annual_nvrd(point_xyz=[1, 2, 3], view_vec=[0, 0, 1], reconstruction="both",
                              physical_sky=True, _channel_provider=_synthetic_provider,
                              _record_provider=_record_map_provider)
    assert "divergence_note" in phys and "divergence_note" not in base
    assert phys["divergence"] != base["divergence"]   # the physical sky_spd reached reconstruction_divergence

def test_annual_nvrd_physical_sky_no_record_source_is_zero_coverage():
    # physical_sky=True with no _record_provider and no epw -> all template, 0% coverage, no raise (spec §6).
    out = bridge.annual_nvrd(point_xyz=[1, 2, 3], view_vec=[0, 0, 1], reconstruction="enhanced",
                             physical_sky=True, _channel_provider=_synthetic_provider)
    ps = out["physical_sky"]
    assert ps["n_physical"] == 0 and ps["n_template"] == 12 and ps["coverage_pct"] == 0.0

def test_physical_sky_note_is_not_globally_false():
    # The per-run note must describe THIS run's transport, not make a global
    # "never live-validated" claim that a live host would contradict.
    out = bridge.annual_nvrd(point_xyz=[1, 2, 3], view_vec=[0, 0, 1],
                             reconstruction="enhanced", physical_sky=True,
                             _channel_provider=_synthetic_provider,
                             _record_provider=lambda: {})
    ps = out["physical_sky"]
    assert ps["n_template"] == 12          # empty record index -> every step falls back to template
    assert "Not live-validated" not in ps["note"]

def test_annual_nvrd_partial_physics_note_does_not_overclaim_all_timesteps():
    # Minor C: with partial coverage + no solar_zeniths, the 30° note must NOT say "ALL timesteps".
    out = bridge.annual_nvrd(point_xyz=[1, 2, 3], view_vec=[0, 0, 1], reconstruction="enhanced",
                             physical_sky=True, _channel_provider=_synthetic_provider_no_zeniths,
                             _record_provider=_partial_record_provider)
    note = out["enhanced_solar_note"]
    assert "ALL timesteps" not in note and "template-fallback timesteps" in note


def test_build_record_index_forwards_engine(monkeypatch):
    # The engine instance must reach record_from_epw as a kwarg, once per unique hour-ending.
    import hcl_core.spectral_pipeline as sp
    from hcl_radiance.annual_nvrd import _build_record_index
    seen_engine = []
    def fake_rfe(epw, m, d, h, **kw):
        seen_engine.append(kw.get("engine"))
        return _Rec([380.0 + i for i in range(401)], [0.5] * 401, [1.0] * 401)
    monkeypatch.setattr(sp, "record_from_epw", fake_rfe)
    sentinel = object()
    ts = [(6, 21, 8.0)]
    _build_record_index("fake.epw", ts, real_timestamps=True, engine=sentinel)
    assert seen_engine == [sentinel]


def test_annual_nvrd_engine_none_defaults_unchanged():
    # engine=None must behave exactly like the existing physical_sky path (spectrl2 default).
    base = bridge.annual_nvrd(point_xyz=[1, 2, 3], view_vec=[0, 0, 1], reconstruction="both",
                              physical_sky=True, _channel_provider=_synthetic_provider,
                              _record_provider=_record_map_provider)
    same = bridge.annual_nvrd(point_xyz=[1, 2, 3], view_vec=[0, 0, 1], reconstruction="both",
                              physical_sky=True, engine=None, _channel_provider=_synthetic_provider,
                              _record_provider=_record_map_provider)
    assert base["enhanced"]["R_D"] == same["enhanced"]["R_D"]
