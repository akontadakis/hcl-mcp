import os

import pytest

from hcl_radiance.annual_commands import (skyglow_rad, suns_rad_steps, build_rfluxmtx_sky,
    build_gendaymtx_sky, build_rcontrib_sun, build_gendaymtx_sun, build_dctimestep,
    build_oconv_annual, stage_cal_files, SUN_DISC_COUNT, _radiance_lib_dir)

def test_sky_octree_is_not_frozen_sun_octree_is_frozen():
    sky = build_oconv_annual(["m.rad", "g.rad"], frozen=False)
    sun = build_oconv_annual(["m.rad", "g.rad", "suns.rad"], frozen=True)
    assert sky == ["oconv", "m.rad", "g.rad"]  # NO -f (source line 122)
    assert sun == ["oconv", "-f", "m.rad", "g.rad", "suns.rad"]  # -f frozen (source line 177)

def test_skyglow_has_rfluxmtx_controls():
    s = skyglow_rad()
    assert "#@rfluxmtx" in s and "skyglow" in s and "groundglow" in s

def test_gendaymtx_sky_is_colored():
    s = " ".join(build_gendaymtx_sky("w.wea", (0.3, 0.4, 0.5), "sky.mtx"))
    assert "gendaymtx" in s and "-m 1" in s and "-s" in s and "-c 0.3 0.4 0.5" in s

def test_gendaymtx_sun_is_neutral_5phase():
    s = " ".join(build_gendaymtx_sun("w.wea", "sun.mtx"))
    assert "-5 0.533" in s and "-d" in s and "-m 6" in s and "-c" not in s  # sun stays neutral

def test_rfluxmtx_and_rcontrib_use_point_count():
    rf = " ".join(build_rfluxmtx_sky(120, "-ab 2", "sky.rad", "oct", "pts", "illum.mtx"))
    rc = " ".join(build_rcontrib_sun(120, "-ab 2", "octsun", "pts", "illumsun.mtx"))
    assert "-I+ -y 120" in rf and "rfluxmtx" in rf
    assert "-I+ -y 120" in rc and "-m solar" in rc and "reinhart.cal" in rc
    # GAP 2: v1 emits ASCII (no -faf) so the sun .ill parses with the same parse_ill as the sky.
    assert "-faf" not in rc

def test_suns_rad_steps_build_one_disc_per_reinhart_sky_bin():
    steps = suns_rad_steps("suns.rad")
    blob = " ".join(" ".join(s["cmd"]) for s in steps)
    assert str(SUN_DISC_COUNT) in blob and "reinsrc.cal" in blob and "light solar" in blob


def test_the_disc_count_is_reinsrc_cal_own_rmax():
    """The count is not a constant to be trusted -- it is reinsrc.cal's Rmax at MF:6, and
    the shipped Lark figure (5165) was 20 short, silently leaving the near-zenith patches
    with a sun and no disc to receive it. Ask the installed .cal rather than assert 5185.
    """
    import shutil
    import subprocess
    if shutil.which("rcalc") is None:
        pytest.skip("Radiance not installed")
    lib = _radiance_lib_dir()
    cal = os.path.join(lib, "reinsrc.cal") if lib else None
    if not cal or not os.path.isfile(cal):
        pytest.skip("reinsrc.cal not present in the Radiance lib")
    out = subprocess.run(["rcalc", "-e", "MF:6", "-f", cal, "-e", "$1=Rmax"],
                         input="\n", capture_output=True, text=True, check=True)
    assert int(float(out.stdout.split()[0])) == SUN_DISC_COUNT


def test_the_coefficient_matrix_has_exactly_one_more_column_than_there_are_discs():
    """rcontrib's Nrbins counts bin 0 (ground) as well, so 5186 columns pair with 5185
    discs. Confusing the two is what makes dctimestep die on 'unexpected column count'.
    """
    import shutil
    import subprocess
    if shutil.which("rcalc") is None:
        pytest.skip("Radiance not installed")
    lib = _radiance_lib_dir()
    cal = os.path.join(lib, "reinhart.cal") if lib else None
    if not cal or not os.path.isfile(cal):
        pytest.skip("reinhart.cal not present in the Radiance lib")
    out = subprocess.run(["rcalc", "-e", "MF:6", "-f", cal, "-e", "$1=Nrbins"],
                         input="\n", capture_output=True, text=True, check=True)
    assert int(float(out.stdout.split()[0])) == SUN_DISC_COUNT + 1

def test_dctimestep():
    assert " ".join(build_dctimestep("illum.mtx", "sky.mtx")) == "dctimestep illum.mtx sky.mtx"
