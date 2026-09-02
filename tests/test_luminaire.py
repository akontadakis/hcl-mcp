from hcl_core.luminaire import color_luminaire

LAMP = "void light lamp_mat\n0\n0\n3 1 1 1\nlamp_mat polygon lamp\n0\n0\n12 ...\n"

def test_color_luminaire_replaces_default_triplet(tmp_path):
    p = tmp_path / "lamp.rad"; p.write_text(LAMP)
    out = color_luminaire(str(p), [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9], count=1)  # green third
    assert "3 0.4 0.5 0.6" in out and "3 1 1 1" not in out

def test_color_luminaire_count_selects_third(tmp_path):
    p = tmp_path / "lamp.rad"; p.write_text(LAMP)
    out = color_luminaire(str(p), list(range(9)), count=2)  # red third -> [6,7,8]
    assert "3 6 7 8" in out

def test_color_luminaire_from_text():
    out = color_luminaire(LAMP, [0.1] * 9, count=0, in_place=False)  # blue third
    assert "3 0.1 0.1 0.1" in out


def test_color_luminaire_leaves_stray_triplet_in_geometry(tmp_path):
    # Regression: an unanchored global re.sub recolored every "3 1 1 1" in the .rad, corrupting
    # geometry/aux primitives. Now only the light primitive's data line (after "0\n0\n") is changed.
    rad = ("void light lamp_mat\n0\n0\n3 1 1 1\n\n"
           "lamp_mat polygon p\n0\n0\n3 1 1 1\n")  # stray "3 1 1 1" as polygon vertex data
    out = color_luminaire(rad, [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9], count=2, in_place=False)
    assert out.count("3 0.7 0.8 0.9") == 1   # only the light line recolored (red third)
    assert out.count("3 1 1 1") == 1         # the geometry triplet is untouched
