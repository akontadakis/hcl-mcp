import pytest

from hcl_radiance.sky import (build_gendaylit, find_solar_line, scale_solar, sky_glow, assemble_sky_def, colored_sky)

# Minimal fixture mimicking gendaylit output with a solar source RGB line "3 R G B".
GENDAYLIT_OUT = ("void light solar\n0\n0\n3 0.5 0.4 0.3\n"
                 "solar source sun\n0\n0\n4 0 0 1 0.533\n")

def test_build_gendaylit_W_and_E():
    # lon is standard signed / EAST-positive (Seattle = -122.3), negated internally to west-positive -o.
    w = " ".join(build_gendaylit(6, 21, 12.0, irrad_mode="W", direct=800, diffuse=120,
                                 lat=47.6, lon=-122.3, utc=-8))
    assert w.startswith("gendaylit 6 21 12.0 -W 800 120") and "-a 47.6" in w and "-m 120" in w  # UTC*-15
    assert "-o 122.3" in w  # signed -122.3 in -> west-positive 122.3 out; guards hemisphere
    e = " ".join(build_gendaylit(6, 21, 12.0, irrad_mode="E", globl=900, lat=47.6, lon=-122.3, utc=-8))
    assert "-E 900" in e and "-o 122.3" in e


# --- explicit solar position (-ang): keeps a spectral record's spectrum and the traced sky on one
# instant instead of letting gendaylit's own ephemeris re-derive it from a differently-conventioned hour.

def test_build_gendaylit_ang_form_converts_record_conventions():
    """zenith/azimuth are taken VERBATIM from a SpectralSkyRecord geometry block.

    Athens 2026-03-21, EPW hour 12 -> mid-interval geometry z=40.9586, az=155.5695 (clockwise from N).
    gendaylit wants altitude (90-z) and azimuth measured from SOUTH, +toward WEST (az-180).
    """
    cmd = " ".join(build_gendaylit(3, 21, 12.0, irrad_mode="W", direct=830, diffuse=149,
                                   lat=37.9, lon=23.73, utc=2,
                                   sun_zenith_deg=40.958645, sun_azimuth_deg=155.569539))
    assert cmd == "gendaylit -ang 49.0414 -24.4305 -W 830 149"
    # -a/-o/-m are inert under -ang (verified byte-identical gendaylit output) -> not emitted, so the
    # command never implies a dependency on a site the sun is no longer derived from.
    for dead in ("-a ", "-o ", "-m "):
        assert dead not in cmd
    # month/day/hour must NOT survive: they are what -ang exists to override.
    assert "3 21 12.0" not in cmd


def test_build_gendaylit_ang_requires_both_components():
    import pytest
    for kw in ({"sun_zenith_deg": 40.0}, {"sun_azimuth_deg": 155.0}):
        with pytest.raises(ValueError, match="must be supplied together"):
            build_gendaylit(3, 21, 12.0, irrad_mode="W", direct=830, diffuse=149,
                            lat=37.9, lon=23.73, utc=2, **kw)


def test_build_gendaylit_default_is_byte_identical_without_solar_position():
    """The new parameters must not perturb the shipped path when unused."""
    kw = dict(irrad_mode="W", direct=800, diffuse=120, lat=47.6, lon=-122.3, utc=-8)
    assert build_gendaylit(6, 21, 12.0, **kw) == build_gendaylit(
        6, 21, 12.0, sun_zenith_deg=None, sun_azimuth_deg=None, **kw)


def test_find_solar_line():
    idx = find_solar_line(GENDAYLIT_OUT.splitlines())
    assert GENDAYLIT_OUT.splitlines()[idx].strip().startswith("3 ")

def test_scale_solar_3channel_uses_mean():
    # direct == diffuse == [0.8,0.9,0.85]; solar "3 0.5 0.4 0.3"; coef = mean(0.5,0.4,0.3)/sum3
    out = scale_solar([3, 0.5, 0.4, 0.3], [0.8, 0.9, 0.85], channel_type=0)
    # Lark's golden line was "3 0.37 0.41 0.39": the same numbers cut to two decimals. Six
    # significant figures are written now (review 2026-11-26, A6); they round to Lark's.
    assert out == ["3 0.36771 0.413674 0.390692"]
    assert [round(float(v), 2) for v in out[0].split()[1:]] == [0.37, 0.41, 0.39]

def test_scale_solar_9channel_uses_first_component():
    ch = [0.1] * 9
    out = scale_solar([3, 0.5, 0.4, 0.3], ch, channel_type=1)
    assert len(out) == 3 and all(line.startswith("3 ") for line in out)

def test_sky_glow_3channel_normalized():
    s = sky_glow([0.8, 0.9, 0.85], channel_type=0)
    # Lark's golden values were "0.92 1.03 0.98", the same numbers cut to two decimals (A6).
    assert isinstance(s, str) and "skyfunc glow sky_mat" in s and "4 0.919276 1.03419 0.976731 0" in s

def test_assemble_includes_solar_and_skymat():
    defs = assemble_sky_def(GENDAYLIT_OUT, ["3 0.37 0.41 0.39"], [sky_glow([0.8, 0.9, 0.85], 0)], channel_type=0)
    assert len(defs) == 1 and "3 0.37 0.41 0.39" in defs[0] and "sky_mat" in defs[0] and "ground_glow" in defs[0]


from hcl_radiance.sky import build_gendaylit_luminance, colored_sky_luminance

def test_build_gendaylit_luminance_W_has_C_flag():
    cmd = " ".join(build_gendaylit_luminance(6, 21, 12.0, irrad_mode="W", direct=800, diffuse=120,
                                             lat=47.6, lon=-122.3, utc=-8))
    # -C precedes -W; meridian = UTC*-15 = 120; signed -122.3 negated to west-positive -o 122.3
    assert cmd == "gendaylit 6 21 12.0 -C -W 800 120 -a 47.6 -o 122.3 -m 120"

def test_build_gendaylit_luminance_E_global():
    cmd = " ".join(build_gendaylit_luminance(6, 21, 12.0, irrad_mode="E", globl=900,
                                             lat=47.6, lon=-122.3, utc=-8))
    assert cmd == "gendaylit 6 21 12.0 -C -E 900 -a 47.6 -o 122.3 -m 120"

def test_build_gendaylit_luminance_ang_form_keeps_C_flag():
    # -ang composes with -C (verified live on Radiance 6.1a); -C still precedes the irradiance flag.
    cmd = " ".join(build_gendaylit_luminance(3, 21, 12.0, irrad_mode="W", direct=830, diffuse=149,
                                             lat=37.9, lon=23.73, utc=2,
                                             sun_zenith_deg=40.958645, sun_azimuth_deg=155.569539))
    assert cmd == "gendaylit -ang 49.0414 -24.4305 -C -W 830 149"

def test_colored_sky_luminance_threads_solar_position(tmp_path):
    out = colored_sky_luminance(0, month=3, day=21, hour=12.0, irrad_mode="W", direct=830, diffuse=149,
                                lat=37.9, lon=23.73, utc=2, work_dir=str(tmp_path),
                                sun_zenith_deg=40.958645, sun_azimuth_deg=155.569539)
    assert out["sky_defs"][0].startswith("!gendaylit -ang 49.0414 -24.4305 -C -W 830 149")

def test_colored_sky_luminance_rad_content(tmp_path):
    out = colored_sky_luminance(0, month=6, day=21, hour=12.0, irrad_mode="W", direct=800, diffuse=120,
                                lat=47.6, lon=-122.3, utc=-8, work_dir=str(tmp_path))
    rad = out["sky_defs"][0]
    assert rad.startswith("!gendaylit 6 21 12.0 -C -W 800 120")   # inline ! + -C
    assert "skyfunc glow sky_mat" in rad and "4 1 1 1 0" in rad   # neutral sky glow
    assert "skyfunc glow ground_glow" in rad and "4 1 0.8 0.5 0" in rad  # warm ground glow
    assert out["ran"] is False and len(out["files"]) == 1         # pure emit, single 3ch file

def test_colored_sky_luminance_rejects_9channel(tmp_path):
    import pytest
    with pytest.raises(ValueError, match="luminance mode is 3-channel only"):
        colored_sky_luminance(1, month=6, day=21, hour=12.0, irrad_mode="W", direct=800, diffuse=120,
                              lat=47.6, lon=-122.3, utc=-8, work_dir=str(tmp_path))

def test_colored_sky_routes_to_luminance(tmp_path):
    out = colored_sky([0.8, 0.9, 0.85], [0.8, 0.9, 0.85], 0, month=6, day=21, hour=12.0,
                      irrad_mode="W", direct=800, diffuse=120, lat=47.6, lon=-122.3, utc=-8,
                      work_dir=str(tmp_path), mode="luminance")
    assert "!gendaylit 6 21 12.0 -C -W 800 120" in out["sky_defs"][0]


def test_colored_sky_spectra_run_true_degrades_when_radiance_adapter_absent(tmp_path, monkeypatch):
    # Regression: with run=True (the DEFAULT) and the Radiance adapter unavailable, colored_sky must
    # degrade gracefully to the emit path (return commands), NOT raise ModuleNotFoundError.
    # We force _available()->False so the "adapter absent" path is exercised deterministically,
    # regardless of whether Radiance is installed on this machine (Plan 3 makes the discover/runner
    # modules present, so the original "module not importable" premise no longer holds everywhere).
    import hcl_radiance.sky as sky
    monkeypatch.setattr(sky, "_available", lambda: False)
    out = colored_sky([0.8, 0.9, 0.85], [0.8, 0.9, 0.85], 0, month=6, day=21, hour=12.0,
                      irrad_mode="W", direct=800, diffuse=120, lat=47.6, lon=122.3, utc=-8,
                      work_dir=str(tmp_path), run=True, mode="spectra")
    assert out["ran"] is False
    assert any("gendaylit 6 21 12.0 -W 800 120" in c for c in out["commands"])


def test_find_solar_line_anchors_on_solar_primitive():
    # A decoy 3-arg primitive precedes the solar source; find_solar_line must anchor on
    # 'void light solar' and return the SOLAR rgb line, not the decoy.
    out = ("void brightfunc skyfunc\n0\n0\n3 9 9 9\n"   # decoy '3 ' line
           "void light solar\n0\n0\n3 0.5 0.4 0.3\n"
           "solar source sun\n0\n0\n4 0 0 1 0.533\n")
    lines = out.splitlines()
    assert lines[find_solar_line(lines)] == "3 0.5 0.4 0.3"


def test_colored_sky_rejects_missing_irradiance():
    """No irradiance must fail with a message naming the cause, not a parser artefact.

    Found live 2026-08-06 driving the validation kit. `direct`/`diffuse` are separate optional
    params from the CHANNELS, so omitting them is an easy caller error. gendaylit accepts the
    literal string "None", computes a zero-irradiance sky, and emits NO solar primitive at all --
    so the failure surfaced ~40 lines later as "no solar RGB line ('3 R G B') found in gendaylit
    output", which points at the parser and says nothing about the actual mistake.
    """
    with pytest.raises(ValueError, match="irrad_mode='W' needs both `direct` and `diffuse`"):
        build_gendaylit(6, 21, 12, irrad_mode="W", lat=37.9, lon=23.73, utc=2)
    with pytest.raises(ValueError, match="irrad_mode='E' needs `globl`"):
        build_gendaylit(6, 21, 12, irrad_mode="E", lat=37.9, lon=23.73, utc=2)


def test_colored_sky_still_builds_with_irradiance_supplied():
    """The guard must not fire on a well-formed call."""
    cmd = build_gendaylit(6, 21, 12, irrad_mode="W", lat=37.9, lon=23.73, utc=2,
                          direct=354.0, diffuse=464.0)
    assert "None" not in cmd
    assert "-W" in cmd and "354.0" in cmd and "464.0" in cmd
