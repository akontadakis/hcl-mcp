from hcl_radiance.annual_daylight import _force_direct_only, _concat_sets, run_annual_daylight

def test_force_direct_only_replaces_ab():
    assert _force_direct_only("-ab 2 -ad 512 -aa 0.1") == "-ab 0 -ad 512 -aa 0.1"

def test_force_direct_only_adds_ab_when_absent():
    assert _force_direct_only("-ad 512") == "-ab 0 -ad 512"

def test_force_direct_only_replaces_trailing_dangling_ab():
    assert _force_direct_only("-ad 512 -ab") == "-ad 512 -ab 0"

def test_concat_sets_9channel():
    # 3 sets, 1 point, 1 timestep, each [r,g,b] -> concatenated 9-vector
    sets = [[[[1, 1, 1]]], [[[2, 2, 2]]], [[[3, 3, 3]]]]
    assert _concat_sets(sets) == [[[1, 1, 1, 2, 2, 2, 3, 3, 3]]]

def test_run_annual_daylight_emits_commands_when_not_run():
    scenes = [{"materials": ["m.rad"], "geometry": "g.rad", "sky_color": [1, 1, 1]}]
    out = run_annual_daylight(scenes, "in.wea", [[0, 0, 0.8, 0, 0, 1]], 0,
                              work_dir="/tmp/hcl_ase_test", run=False)
    assert out["ran"] is False
    cmds = " ".join(out["commands"])   # commands are pre-rendered shell strings
    # the direct-only ASE rcontrib carries -ab 0; the sky/sun path carries -ab 2
    assert "-ab 0" in cmds
    assert "annual_sun_ase0.ill" in cmds

def test_run_annual_daylight_no_ase_skips_direct_pass():
    scenes = [{"materials": ["m.rad"], "geometry": "g.rad", "sky_color": [1, 1, 1]}]
    out = run_annual_daylight(scenes, "in.wea", [[0, 0, 0.8, 0, 0, 1]], 0,
                              work_dir="/tmp/hcl_noase_test", run=False, ase=False)
    assert out["ran"] is False
    assert "annual_sun_ase0.ill" not in " ".join(out["commands"])


def test_concat_sets_rejects_ragged_point_counts():
    """A channel set short by a POINT must fail loudly, not mispair across sets.

    Found by audit 2026-08-06, the same class as grid._recombine. n_pts/n_ts are taken from
    sets[0] and every set is then indexed [p][t], so a short set silently supplies a LATER
    point's series before the ragged tail raises a bare IndexError naming neither the set nor
    the mismatch. Annual mel-EDI is the headline circadian number, so a silent mispair here is
    a wrong dose reported with full confidence.
    """
    import pytest
    a = [[[1, 1, 1], [2, 2, 2]], [[3, 3, 3], [4, 4, 4]]]   # 2 points
    b = [[[9, 9, 9], [8, 8, 8]]]                            # 1 point  <- short
    c = [[[5, 5, 5], [6, 6, 6]], [[7, 7, 7], [8, 8, 8]]]
    with pytest.raises(ValueError, match="sensor count"):
        _concat_sets([a, b, c])


def test_concat_sets_rejects_ragged_timestep_counts():
    """A set short by a TIMESTEP must fail loudly too."""
    import pytest
    a = [[[1, 1, 1], [2, 2, 2]]]
    b = [[[9, 9, 9]]]                                       # 1 timestep instead of 2
    c = [[[5, 5, 5], [6, 6, 6]]]
    with pytest.raises(ValueError, match="timestep count"):
        _concat_sets([a, b, c])


def test_concat_sets_still_concatenates_when_sets_agree():
    """The guard must not fire on well-formed input."""
    a = [[[1, 1, 1]]]
    b = [[[2, 2, 2]]]
    c = [[[3, 3, 3]]]
    assert _concat_sets([a, b, c]) == [[[1, 1, 1, 2, 2, 2, 3, 3, 3]]]
