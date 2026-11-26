import pytest
from hcl_radiance.threephase_commands import (
    build_rfluxmtx_view, build_rfluxmtx_daylight, build_dctimestep_3ph,
    build_rmtxop_photopic, build_rmtxop_sum, build_gendaymtx_sky_mf,
    sky_receiver_rad, DEFAULT_V_PARAMS, DEFAULT_D_PARAMS)


def test_view_matrix_uses_irradiance_mode_and_point_count():
    cmd = build_rfluxmtx_view(120, "-ab 12 -ad 50000 -lw 2e-5", "wg0_sender.rad", "vmx.oct")
    assert cmd[0] == "rfluxmtx"
    assert "-I+" in cmd
    assert cmd[cmd.index("-y") + 1] == "120"
    assert cmd.index("-") < cmd.index("wg0_sender.rad")
    assert cmd[cmd.index("-i") + 1] == "vmx.oct"


def test_daylight_matrix_sends_from_window_to_sky():
    cmd = build_rfluxmtx_daylight("-c 1000 -ab 2", "wg0_sender.rad", "sky_rx.rad", "dmx.oct")
    assert cmd[0] == "rfluxmtx"
    assert cmd.index("wg0_sender.rad") < cmd.index("sky_rx.rad")
    assert "-I+" not in cmd          # D is not an irradiance-at-points calculation


def test_dctimestep_is_the_four_argument_form():
    assert build_dctimestep_3ph("v.mtx", "t.xml", "d.mtx", "sky.smx") == [
        "dctimestep", "v.mtx", "t.xml", "d.mtx", "sky.smx"]


def test_photopic_collapse_reads_stdin_and_uses_the_efficacy_weights():
    cmd = build_rmtxop_photopic()
    assert cmd[0] == "rmtxop"
    assert "-fa" in cmd
    assert cmd[cmd.index("-c") + 1:cmd.index("-c") + 4] == ["47.4", "119.9", "11.6"]
    assert cmd[-1] == "-"            # trailing dash reads the piped matrix


def test_sum_combines_group_contributions():
    assert build_rmtxop_sum(["a.ill", "b.ill", "c.ill"]) == [
        "rmtxop", "-fa", "a.ill", "+", "b.ill", "+", "c.ill"]


def test_sum_of_a_single_group_is_a_plain_copy():
    assert build_rmtxop_sum(["only.ill"]) == ["rmtxop", "-fa", "only.ill"]


def test_sum_rejects_an_empty_list():
    with pytest.raises(ValueError, match="at least one"):
        build_rmtxop_sum([])


def test_sky_receiver_carries_the_ground_patch_before_the_dome():
    """gendaymtx emits 2305 sky patches + 1 ground = 2306 rows. A receiver with only the
    dome gives D 2305 columns and dctimestep dies on 'unexpected column count'."""
    text = sky_receiver_rad(4)
    assert "h=u" in text and "h=r4" in text
    assert text.index("h=u") < text.index("h=r4")
    assert "groundglow" in text and "skyglow" in text
    assert "4 1 1 1 0" in text


def test_the_sky_receivers_up_vector_is_not_its_own_axis():
    """rfluxmtx bins the sky by azimuth around the receiver's axis, measured from `u`. The
    dome's axis is Z, so u=+Z leaves the azimuth undefined: every patch of an altitude band
    collapsed onto the one due north, and no window ever saw the sun. +Y is north, the
    convention gendaymtx numbers its patches by (and what the two-phase path always used)."""
    for line in sky_receiver_rad(4).splitlines():
        if line.startswith("#@rfluxmtx"):
            assert "u=+Y" in line.split(), line


def test_the_sky_matrix_comes_with_or_without_the_sun():
    """Sky light and sunlight take different routes to an unshaded point (matrices; the exact
    direct-sun pass), so the engine needs the sky alone -- and, for a diffusing blind, the
    sky together with the sun."""
    sky_only = build_gendaymtx_sky_mf("in.wea", [1, 1, 1], mf=4)
    with_sun = build_gendaymtx_sky_mf("in.wea", [1, 1, 1], mf=4, sun=True)
    assert "-s" in sky_only and "-d" not in sky_only
    assert "-s" not in with_sun and "-d" not in with_sun
    assert with_sun[-1] == "in.wea" and with_sun[with_sun.index("-m") + 1] == "4"


def test_sky_matrix_subdivision_is_settable_and_matches_the_receiver():
    """annual_commands.build_gendaymtx_sky hardcodes -m 1 (145 patches), which cannot
    multiply a D matrix built against an h=r4 receiver."""
    cmd = build_gendaymtx_sky_mf("in.wea", [1, 1, 1], mf=4)
    assert cmd[0] == "gendaymtx"
    assert cmd[cmd.index("-m") + 1] == "4"
    assert "-c" in cmd
    assert cmd[-1] == "in.wea"


def test_default_params_follow_the_lbnl_tutorial():
    assert "-ab 12" in DEFAULT_V_PARAMS and "-ad 50000" in DEFAULT_V_PARAMS
    assert "-ab 2" in DEFAULT_D_PARAMS and "-c 1000" in DEFAULT_D_PARAMS
