import pytest
from hcl_radiance.threephase import build_threephase_steps, multiply_steps
from hcl_radiance.runner import _render

_SCENE = {"materials": ["/w/m.rad"], "geometry": "/w/g.rad",
          "exterior": ["/w/context.rad"], "sky_color": [1, 1, 1]}
_SENDERS = {"wg_south": "/w/wg_south_sender.rad", "wg_north": "/w/wg_north_sender.rad"}


def _cmds(steps):
    return [_render(s) for s in steps]


def test_builds_one_view_and_one_daylight_matrix_per_group():
    steps, out = build_threephase_steps(_SCENE, _SENDERS, "in.wea", "p.pts", 50,
                                        work_dir="/w")
    joined = _cmds(steps)
    assert sum(1 for c in joined if "rfluxmtx -I+" in c) == 2
    assert sum(1 for c in joined if c.startswith("rfluxmtx") and "-I+" not in c) == 2
    assert set(out["v_mtx"]) == {"wg_south", "wg_north"}
    assert set(out["d_mtx"]) == {"wg_south", "wg_north"}


def test_builds_two_octrees_with_the_right_contents():
    """D excludes the interior (outbound rays would be absorbed) and any sky (a glow
    source in the D octree occludes the receiver -- measured D = 0.0 with it present)."""
    steps, _out = build_threephase_steps(_SCENE, _SENDERS, "in.wea", "p.pts", 50,
                                         work_dir="/w")
    oconvs = [c for c in _cmds(steps) if c.startswith("oconv")]
    assert len(oconvs) == 2
    vmx = next(c for c in oconvs if "vmx.oct" in c)
    dmx = next(c for c in oconvs if "dmx.oct" in c)
    assert "/w/g.rad" in vmx
    assert "/w/g.rad" not in dmx
    assert "/w/context.rad" in dmx
    assert "sky" not in dmx.replace("dmx.oct", "")


def test_the_window_glow_is_not_baked_into_the_v_octree():
    """rfluxmtx oconv's the receiver onto the octree itself; its header shows
    `oconv -f -i vmx.oct <receiver>`. Including it too risks a duplicate modifier."""
    steps, _out = build_threephase_steps(_SCENE, _SENDERS, "in.wea", "p.pts", 50,
                                         work_dir="/w")
    vmx = next(c for c in _cmds(steps) if c.startswith("oconv") and "vmx.oct" in c)
    assert "sender.rad" not in vmx


def test_both_matrix_roles_use_the_same_sender_file():
    steps, _out = build_threephase_steps(_SCENE, _SENDERS, "in.wea", "p.pts", 50,
                                         work_dir="/w")
    joined = _cmds(steps)
    v = next(c for c in joined if "rfluxmtx -I+" in c and "wg_south" in c)
    d = next(c for c in joined if c.startswith("rfluxmtx") and "-I+" not in c
             and "wg_south" in c)
    assert "wg_south_sender.rad" in v
    assert "wg_south_sender.rad" in d


def test_sky_matrix_is_built_once_at_the_receivers_subdivision():
    """A -m 1 sky (145 rows) cannot multiply a D built against an h=r4 receiver."""
    steps, out = build_threephase_steps(_SCENE, _SENDERS, "in.wea", "p.pts", 50,
                                        work_dir="/w", sky_mf=4)
    gendaymtx = [c for c in _cmds(steps) if c.startswith("gendaymtx")]
    assert len(gendaymtx) == 1
    assert "-m 4" in gendaymtx[0]
    assert out["sky_mtx"] == "sky.smx"


def test_receiver_file_is_written_not_echoed():
    steps, _out = build_threephase_steps(_SCENE, _SENDERS, "in.wea", "p.pts", 50,
                                         work_dir="/w")
    assert any("write" in s for s in steps)
    assert not any("cmd" in s and s["cmd"][0] == "echo" for s in steps)


def test_step_io_paths_are_bare_filenames():
    """run_sequence joins stdin/stdout against work_dir, so they must not be absolute."""
    steps, _out = build_threephase_steps(_SCENE, _SENDERS, "in.wea", "p.pts", 50,
                                         work_dir="/w")
    for s in steps:
        for key in ("stdin", "stdout"):
            if s.get(key):
                assert not s[key].startswith("/"), f"{key}={s[key]} must be a bare name"


def test_multiply_adds_no_raytracing_steps():
    """The three-phase payoff: a new shading state costs a multiply, not a trace."""
    _steps, out = build_threephase_steps(_SCENE, _SENDERS, "in.wea", "p.pts", 50,
                                         work_dir="/w")
    mul, ill = multiply_steps(out, {"wg_south": "open.xml", "wg_north": "open.xml"}, "open")
    joined = _cmds(mul)
    assert not any("rfluxmtx" in c for c in joined)
    assert not any("oconv" in c for c in joined)
    assert ill == "open.ill"


def test_each_state_costs_one_dctimestep_per_group():
    """With G groups and S states the count is G*S. A single-group fixture would make
    this assertion pass for the wrong reason, so use two."""
    _steps, out = build_threephase_steps(_SCENE, _SENDERS, "in.wea", "p.pts", 50,
                                         work_dir="/w")
    t = {"wg_south": "b.xml", "wg_north": "b.xml"}
    total = 0
    for tag in ("open", "closed_a", "closed_b"):
        mul, _ill = multiply_steps(out, t, tag)
        total += sum(1 for c in _cmds(mul) if "dctimestep" in c)
    assert total == 2 * 3


def test_multiply_sums_the_group_contributions_into_the_returned_file():
    _steps, out = build_threephase_steps(_SCENE, _SENDERS, "in.wea", "p.pts", 50,
                                         work_dir="/w")
    mul, ill = multiply_steps(out, {"wg_south": "o.xml", "wg_north": "o.xml"}, "open")
    summed = [s for s in mul if s.get("stdout") == ill]
    assert len(summed) == 1
    assert "+" in summed[0]["cmd"]


def test_multiply_requires_a_t_matrix_for_every_group():
    _steps, out = build_threephase_steps(_SCENE, _SENDERS, "in.wea", "p.pts", 50,
                                         work_dir="/w")
    with pytest.raises(ValueError, match="wg_north"):
        multiply_steps(out, {"wg_south": "open.xml"}, "partial")


def test_state_tag_keeps_outputs_from_colliding():
    _steps, out = build_threephase_steps(_SCENE, _SENDERS, "in.wea", "p.pts", 50,
                                         work_dir="/w")
    t = {"wg_south": "b.xml", "wg_north": "b.xml"}
    assert multiply_steps(out, t, "open")[1] != multiply_steps(out, t, "closed")[1]
