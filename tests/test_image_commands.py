from hcl_radiance.image_commands import (
    build_rpict, pcomb_melanopic_map, pcomb_neuropic_map, fov_pcomb_steps, rgb_from_hdr_steps)

def test_build_rpict_fisheye():
    cmd = build_rpict("scene.oct", view="-vta -vh 180 -vv 180", x=800, y=800, rad_params="-ab 2")
    s = " ".join(cmd)
    assert cmd[0] == "rpict" and "-vta" in s and "-x 800" in s and "-y 800" in s and s.endswith("scene.oct")

def test_pcomb_melanopic_coeffs_present():
    s = " ".join(pcomb_melanopic_map(["b.hdr", "g.hdr", "r.hdr"], "mel.hdr"))
    # melanopic b1,b2,b3 = 0.0119, 0.1784, 0.4165
    assert "0.0119" in s and "0.1784" in s and "0.4165" in s and s.startswith("pcomb")

def test_pcomb_neuropic_uses_grid_value():
    s = " ".join(pcomb_neuropic_map(["b.hdr", "g.hdr", "r.hdr"], "neu.hdr"))
    assert "0.905130569" in s and "0.000069431" in s  # grid value, not 0.00007

def test_fov_pcomb_steps_weights():
    steps = fov_pcomb_steps("in.hdr", masks={"upper_inner": "1.hdr", "upper_outer": "3.hdr",
                                             "lower_inner": "2.hdr", "lower_outer": "4.hdr"}, out="w.hdr")
    blob = " ".join(" ".join(s["cmd"]) for s in steps)
    assert "2.06" in blob and "1.37" in blob and "0.34" in blob and "0.23" in blob

def test_rgb_from_hdr_pipeline():
    steps = rgb_from_hdr_steps("eye.hdr", out="rgb.txt")
    blob = " ".join(" ".join(s["cmd"]) for s in steps)
    assert "vwright" in blob and "pcomb" in blob and "pvalue" in blob and "total" in blob
