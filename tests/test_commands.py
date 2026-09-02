from hcl_radiance.commands import build_oconv, build_rtrace, pts_to_text

def test_build_oconv_order():
    cmd = build_oconv(["mat.rad", "sky.rad", "geo.rad"], "scene.oct")
    assert cmd[0] == "oconv"
    assert cmd[-3:] == ["mat.rad", "sky.rad", "geo.rad"]
    assert cmd[1] == "-f"  # frozen octree

def test_build_rtrace_irradiance_flags():
    cmd = build_rtrace("scene.oct", rad_params="-ab 3 -ad 1024")
    s = " ".join(cmd)
    assert cmd[0] == "rtrace"
    assert "-I+" in s and "-h-" in s and "-ab 3 -ad 1024" in s and s.endswith("scene.oct")
    # value output (-ov), NOT contribution (-oV which warns "requires trace mode")
    assert "-ov" in cmd and "-oV" not in cmd

def test_pts_to_text_formats_six_columns():
    txt = pts_to_text([[0, 0, 1.2, 0, 0, 1], [1, 2, 0.8, 0, 0, 1]])
    lines = txt.strip().splitlines()
    assert lines[0] == "0 0 1.2 0 0 1" and len(lines) == 2
