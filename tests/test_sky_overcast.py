from hcl_radiance.sky_overcast import build_gensky_overcast, write_overcast_sky

def test_build_gensky_overcast_has_c_flag():
    cmd = build_gensky_overcast(month=3, day=21, hour=12.0)
    assert cmd[0] == "gensky"
    assert "-c" in cmd                     # CIE overcast distribution
    assert cmd[1:4] == ["3", "21", "12.0"]

def test_write_overcast_sky_steps(tmp_path):
    steps, out = write_overcast_sky(str(tmp_path))
    assert out == "overcast_sky.rad"
    assert steps[0]["cmd"][0] == "gensky"
    assert steps[0]["stdout"] == "overcast_sky.rad"
    # glow tail step appends the sky/ground glow to the same file
    assert any(s.get("append") for s in steps[1:])

def test_overcast_glow_is_write_tuple_not_printf(tmp_path):
    # Windows-safe: the glow tail is a {"write": (path, text)} pseudo-step, not a Unix `printf`.
    steps, out = write_overcast_sky(str(tmp_path))
    assert not any(s.get("cmd", [None])[0] == "printf" for s in steps)
    writes = [s for s in steps if "write" in s]
    assert len(writes) == 1
    path, text = writes[0]["write"]
    assert path == out and writes[0].get("append") is True
    assert "sky_glow" in text and "ground_glow" in text
