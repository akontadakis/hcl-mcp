"""Review 2026-11-26, annual and sky findings: A2, A6, A7, N1, N2."""
import os
import re
import signal
import stat
import sys

import pytest

import hcl_radiance.annual_nvrd as bridge
from hcl_radiance import sky


# ---- A2: a failed annual run is reported, it does not crash the tool ----

def _nvrd(tmp_path, monkeypatch, wea_result, annual_result):
    import hcl_daysim.subhourly as subhourly
    import hcl_radiance.annual as annual_mod
    monkeypatch.setattr(subhourly, "generate_subhourly_wea",
                        lambda epw, *, timestep_min, work_dir, run: wea_result)
    monkeypatch.setattr(annual_mod, "run_annual_separated",
                        lambda scenes, wea, points, channel_type, **kw: annual_result)
    epw = tmp_path / "w.epw"
    epw.write_text("LOCATION,Test,WA,USA,Custom,000000,47.6,-122.3,-8.0,20.0\n")
    return bridge.annual_nvrd(point_xyz=[1, 2, 3], view_vec=[0, 0, 1], epw=str(epw),
                              channel_scenes=[{"materials": "m.rad", "geometry": "g.rad",
                                               "sky_color": [0.3, 0.4, 0.5]}],
                              points="pts.pts", channel_type=1, work_dir=str(tmp_path), run=True)


_WEA_OK = {"ran": True, "commands": ["epw2wea"], "wea": "sub.wea",
           "timestamps": [(6, 21, 12.0)], "solar_zeniths": [18.0]}


def test_a_failed_annual_run_comes_back_as_an_error_not_a_crash(tmp_path, monkeypatch):
    """`run_annual_separated` answers {ran: True, error: ...} when a Radiance step fails. The
    caller looked only at `ran` and then read `sky_sets`, which is not there: KeyError."""
    out = _nvrd(tmp_path, monkeypatch, _WEA_OK,
                {"ran": True, "error": "rfluxmtx: fatal - no such file", "failed_step": 4})
    assert out["ran"] is True and out["ok"] is False
    assert "rfluxmtx: fatal" in out["error"] and out["failed_step"] == 4
    assert out["stage"] == "annual_transport"
    assert "rows" not in out


def test_a_failed_daysim_run_comes_back_as_an_error_not_a_crash(tmp_path, monkeypatch):
    """Same shape one step earlier: ds_shortterm fails, so there is no .wea to trace."""
    out = _nvrd(tmp_path, monkeypatch,
                {"ran": True, "commands": ["ds_shortterm"], "wea": "sub.wea",
                 "error": "ds_shortterm: bad header", "failed_step": 1},
                {"ran": True, "sky_sets": [], "sun_sets": []})
    assert out["ran"] is True and out["ok"] is False
    assert "bad header" in out["error"] and out["stage"] == "subhourly_weather"


# ---- A6: a weak channel keeps its value ----

def _numbers(text):
    line = next(l for l in text.splitlines() if l.startswith(("3 ", "4 ")))
    return [float(v) for v in line.split()[1:4]]


def test_a_weak_sky_channel_is_not_rounded_away():
    """Two decimals is fine for a channel near 1 and ruinous for one near 0.01: 0.0149 became
    0.01, a third of the light in that channel gone."""
    channels = [0.0149, 1.0, 1.0]                       # photopic sum is close to 1
    s = sky._photopic_sum(channels, 0)
    got = _numbers(sky.sky_glow(channels, 0))
    assert got == pytest.approx([c / s for c in channels], rel=1e-4)


def test_a_weak_solar_channel_is_not_rounded_away():
    """The solar line is scaled to the gendaylit radiance. In daylight that is millions and two
    decimals lose nothing; at a low sun it is below 1 and they lose a great deal."""
    channels = [0.0149, 1.0, 1.0]
    s = sky._photopic_sum(channels, 0)
    got = _numbers(sky.scale_solar([3, 0.5, 0.5, 0.5], channels, 0)[0])
    assert got == pytest.approx([c * 0.5 / s for c in channels], rel=1e-4)


def test_nine_channel_skies_keep_their_weak_channels_too():
    channels = [0.004, 0.02, 0.3, 0.9, 1.0, 1.1, 0.8, 0.05, 0.003]
    s = sky._photopic_sum(channels, 1)
    mats = sky.sky_glow(channels, 1)
    got = [v for m in mats for v in _numbers(m)]
    assert got == pytest.approx([c / s for c in channels], rel=1e-4)


# ---- A7, N1, N2: gensdaymtx, driven through a stand-in program ----

def _stand_in(tmp_path, body):
    """A `gensdaymtx` that is really a Python script, put where discovery looks first."""
    bin_dir = tmp_path / "radiance" / "bin"
    bin_dir.mkdir(parents=True)
    exe = bin_dir / "gensdaymtx"
    exe.write_text(f"#!{sys.executable}\nimport os, sys\n{body}\n")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    return bin_dir


_HEADER = ("#?RADIANCE\\nNROWS=146\\nNCOLS=1\\nNCOMP=20\\n"
           "WAVELENGTH_SPLITS= 780 588 480 380\\nFORMAT=ascii\\n\\n0.1 0.2\\n")


@pytest.mark.skipif(os.name != "posix", reason="stand-in is a #! script")
def test_gensdaymtx_that_writes_nothing_is_a_failure(tmp_path, monkeypatch):
    from hcl_radiance.spectral_native import run_gensdaymtx
    monkeypatch.setenv("HCL_RADIANCE_BIN", str(_stand_in(tmp_path, "sys.exit(0)")))
    out = run_gensdaymtx(str(tmp_path / "site.epw"), str(tmp_path / "work"))
    assert out["ran"] is True and out["ok"] is False
    assert "empty" in out["error"]


@pytest.mark.skipif(os.name != "posix", reason="stand-in is a #! script")
def test_gensdaymtx_that_writes_no_matrix_header_is_a_failure(tmp_path, monkeypatch):
    from hcl_radiance.spectral_native import run_gensdaymtx
    monkeypatch.setenv("HCL_RADIANCE_BIN", str(_stand_in(tmp_path, "print('not a matrix')")))
    out = run_gensdaymtx(str(tmp_path / "site.epw"), str(tmp_path / "work"))
    assert out["ok"] is False and "header" in out["error"]


@pytest.mark.skipif(os.name != "posix", reason="signals")
def test_a_crash_without_the_library_path_says_what_to_set(tmp_path, monkeypatch):
    """With RAYPATH unset the real gensdaymtx dies of a segmentation fault and prints nothing.
    The tool passed that on as an empty error and a bare -11."""
    from hcl_radiance.spectral_native import run_gensdaymtx
    crash = f"os.kill(os.getpid(), {int(signal.SIGSEGV)})"
    monkeypatch.setenv("HCL_RADIANCE_BIN", str(_stand_in(tmp_path, crash)))
    monkeypatch.delenv("RAYPATH", raising=False)
    out = run_gensdaymtx(str(tmp_path / "site.epw"), str(tmp_path / "work"))
    assert out["ok"] is False and out["returncode"] == -signal.SIGSEGV
    assert "RAYPATH" in out["error"] and "mie_ca.dat" in out["error"]
    assert "SIGSEGV" in out["error"]


@pytest.mark.skipif(os.name != "posix", reason="stand-in is a #! script")
def test_the_library_beside_the_program_is_used_when_raypath_is_unset(tmp_path, monkeypatch):
    """An MCP client starts a server with a minimal environment: no RAYPATH. The data file
    gensdaymtx needs sits in `lib` beside `bin`, so the tool can point at it itself."""
    from hcl_radiance.spectral_native import run_gensdaymtx
    echo = ("ok = any(os.path.isfile(os.path.join(d, 'mie_ca.dat'))\n"
            "         for d in os.environ.get('RAYPATH', '').split(os.pathsep) if d)\n"
            f"sys.stdout.write('{_HEADER}') if ok else os.kill(os.getpid(), 11)")
    bin_dir = _stand_in(tmp_path, echo)
    lib = bin_dir.parent / "lib"
    lib.mkdir()
    (lib / "mie_ca.dat").write_text("0\n")
    monkeypatch.setenv("HCL_RADIANCE_BIN", str(bin_dir))
    monkeypatch.delenv("RAYPATH", raising=False)
    out = run_gensdaymtx(str(tmp_path / "site.epw"), str(tmp_path / "work"))
    assert out["ok"] is True, out
    assert out["raypath_supplied"] == str(lib)
    assert "RAYPATH" not in os.environ                   # the server's own environment is untouched


@pytest.mark.skipif(os.name != "posix", reason="stand-in is a #! script")
def test_a_raypath_that_already_has_the_data_is_left_alone(tmp_path, monkeypatch):
    from hcl_radiance.spectral_native import run_gensdaymtx
    echo = f"sys.stdout.write('{_HEADER}'); sys.stderr.write(os.environ['RAYPATH'])"
    bin_dir = _stand_in(tmp_path, echo)
    mine = tmp_path / "mylib"
    mine.mkdir()
    (mine / "mie_ca.dat").write_text("0\n")
    monkeypatch.setenv("HCL_RADIANCE_BIN", str(bin_dir))
    monkeypatch.setenv("RAYPATH", str(mine))
    out = run_gensdaymtx(str(tmp_path / "site.epw"), str(tmp_path / "work"))
    assert out["ok"] is True and "raypath_supplied" not in out


@pytest.mark.skipif(os.name != "posix", reason="stand-in is a #! script")
def test_gensdaymtx_keeps_its_tables_in_one_cache_and_still_finds_the_weather_file(
        tmp_path, monkeypatch):
    """gensdaymtx writes an `atmos_data` folder where it stands. That was the SERVER's folder:
    `/` under Claude Desktop, where it cannot write, and anywhere at all otherwise."""
    from hcl_radiance.spectral_native import run_gensdaymtx
    body = ("os.mkdir('atmos_data')\n"
            "open(sys.argv[-1]).read()\n"                # the weather file must still be found
            f"sys.stdout.write('{_HEADER}')")
    monkeypatch.setenv("HCL_RADIANCE_BIN", str(_stand_in(tmp_path, body)))
    monkeypatch.delenv("HCL_ATMOS_CACHE")
    monkeypatch.setenv("HCL_WORK_ROOT", str(tmp_path / "root"))
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "site.epw").write_text("LOCATION\n")
    monkeypatch.chdir(elsewhere)
    out = run_gensdaymtx("site.epw", str(tmp_path / "work"))     # a RELATIVE weather path
    assert out["ok"] is True, out
    cache = tmp_path / "root" / "atmos_cache" / "atmos_data"
    assert cache.is_dir() and out["atmosphere_cache"] == str(cache)
    assert not (elsewhere / "atmos_data").exists()
    assert not (tmp_path / "work" / "atmos_data").exists()


@pytest.mark.skipif(os.name != "posix", reason="stand-in is a #! script")
def test_the_cache_folder_can_be_named_and_falls_back_to_the_work_folder(tmp_path, monkeypatch):
    from hcl_radiance.spectral_native import atmosphere_cache_dir
    monkeypatch.setenv("HCL_ATMOS_CACHE", str(tmp_path / "named"))
    assert atmosphere_cache_dir("/w") == str(tmp_path / "named")
    blocker = tmp_path / "a_file"
    blocker.write_text("")
    monkeypatch.setenv("HCL_ATMOS_CACHE", str(blocker / "cannot_exist"))
    assert atmosphere_cache_dir("/w") == "/w"


def test_the_status_says_when_the_data_file_cannot_be_found(tmp_path, monkeypatch):
    from hcl_radiance.spectral_native import radiance_spectral_status
    if os.name != "posix":
        pytest.skip("stand-in is a #! script")
    monkeypatch.setenv("HCL_RADIANCE_BIN", str(_stand_in(tmp_path, "pass")))
    monkeypatch.delenv("RAYPATH", raising=False)
    status = radiance_spectral_status()
    assert status["available"] is True and status["aerosol_data"] is None
    assert "RAYPATH is not set" in status["data_note"]


# ---- A8: a folder or file name with a space in it ----

def test_the_emitted_gensdaymtx_plan_survives_a_space_in_a_path(tmp_path, monkeypatch):
    import shlex
    import hcl_radiance.spectral_native as sn
    monkeypatch.setattr(sn, "radiance_spectral_status",
                        lambda: {"available": False, "gensdaymtx": None, "rcomb": None})
    work = tmp_path / "my study"
    out = sn.run_gensdaymtx("/data/GRC Athens.epw", str(work), run=False)
    words = shlex.split(out["commands"][0])
    assert "/data/GRC Athens.epw" in words                      # one argument, not two
    assert words[-2:] == [">", str(work / "sky_spectral.smx")]
    assert str(work / "sky_spectral.smx") in shlex.split(out["commands"][1])


def test_the_emitted_daysim_build_plan_survives_a_space_in_a_path():
    import shlex
    from hcl_daysim.build import _plan
    commands, bin_dir = _plan("/Users/me/My Work/daysim-src")
    assert bin_dir == "/Users/me/My Work/daysim-src/build/bin"
    assert shlex.split(commands[0]) == ["git", "init", "-q", "/Users/me/My Work/daysim-src"]
    configure = next(shlex.split(c) for c in commands if c.startswith("cmake -S"))
    assert configure[1:5] == ["-S", "/Users/me/My Work/daysim-src",
                              "-B", "/Users/me/My Work/daysim-src/build"]
    for command in commands:                       # every line is one path, never two words
        assert "/Users/me/My" not in [w for w in shlex.split(command) if w.endswith("/My")]


def test_a_weather_file_name_with_a_space_gives_daysim_names_without_one(tmp_path):
    """A Daysim header is `keyword value` split on blanks. A file name with a blank in it is read
    as a name and some rubbish, and ds_shortterm opens the wrong file."""
    from hcl_daysim.subhourly import generate_subhourly_wea
    epw = tmp_path / "GRC Athens 167160.epw"
    epw.write_text("LOCATION,Athens,-,GRC,IWEC,167160,37.9,23.73,2.0,15.0\n")
    out = generate_subhourly_wea(str(epw), timestep_min=6, work_dir=str(tmp_path / "w"), run=False)
    hea = (tmp_path / "w" / "daysim_header.hea").read_text()
    for key in ("wea_data_file", "wea_data_short_file"):
        line = next(l for l in hea.splitlines() if l.split()[:1] == [key])
        assert len(line.split()) == 2, line
    assert " " not in os.path.basename(out["wea"])
    assert os.path.basename(out["wea"]).startswith("GRC_Athens_167160")


@pytest.mark.skipif(os.name != "posix", reason="POSIX shell quoting")
def test_an_inline_ies2rad_command_survives_a_space_in_a_path():
    import shlex
    from hcl_radiance.ies_radiance import build_ies2rad
    line = build_ies2rad("/lib/My Fixtures/a b.ies", out_prefix="/w/out dir/lum", inline=True)
    assert line.startswith("!ies2rad ")
    words = shlex.split(line[1:])
    assert words[-1] == "/lib/My Fixtures/a b.ies" and "/w/out dir/lum" in words


# ---- A11: a Reinhart .cal left in the work folder by an older Radiance is refreshed ----

def test_a_stale_cal_file_in_the_work_folder_is_replaced(tmp_path, monkeypatch):
    """The copy was made only when the file was missing. After a Radiance upgrade the work
    folder kept the old definitions for good, and rfluxmtx read those."""
    import hcl_radiance.annual_commands as ac
    lib, work = tmp_path / "lib", tmp_path / "work"
    lib.mkdir(), work.mkdir()
    for name in ac.REINHART_CAL_FILES:
        (lib / name).write_text(f"{{ new {name} }}\n")
    (work / "reinsrc.cal").write_text("{ old }\n")
    monkeypatch.setattr(ac, "_radiance_lib_dir", lambda: str(lib))
    ac.stage_cal_files(str(work), run=True)
    assert (work / "reinsrc.cal").read_text() == "{ new reinsrc.cal }\n"
    assert (work / "reinhart.cal").read_text() == "{ new reinhart.cal }\n"


def test_a_dry_run_copies_no_cal_file(tmp_path, monkeypatch):
    import hcl_radiance.annual_commands as ac
    lib, work = tmp_path / "lib", tmp_path / "work"
    lib.mkdir(), work.mkdir()
    for name in ac.REINHART_CAL_FILES:
        (lib / name).write_text("x\n")
    monkeypatch.setattr(ac, "_radiance_lib_dir", lambda: str(lib))
    steps = ac.stage_cal_files(str(work), run=False)
    assert len(steps) == 3 and os.listdir(work) == []


# ---- A14: the sky and sun matrices of one run must be the same size ----

def test_sky_and_sun_matrices_of_different_sizes_are_refused():
    """`zip` stops at the shorter one. A sun matrix one point short dropped the last sensor from
    every result with no word said."""
    from hcl_radiance.annual_daylight import _pair_sky_sun
    sky = [[[1.0, 1.0, 1.0]] * 2] * 3          # 3 points, 2 timesteps
    sun = [[[0.5, 0.5, 0.5]] * 2] * 2          # 2 points
    with pytest.raises(ValueError, match="3 point.*2 point"):
        _pair_sky_sun(sky, sun, "c0_sky.ill", "c0_sun.ill")
    assert len(_pair_sky_sun(sky, sky, "a", "b")) == 3
