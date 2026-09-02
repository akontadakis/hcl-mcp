from hcl_core.materials import glass_transmissivity, write_material

def test_glass_transmissivity_golden():
    assert glass_transmissivity(0.88) == 0.958
    assert glass_transmissivity(0.50) == 0.545
    assert glass_transmissivity(0.90) == 0.98

def test_glass_transmissivity_list():
    assert glass_transmissivity([0.88, 0.50]) == [0.958, 0.545]

def test_glass_transmissivity_zero():
    """Fully opaque glass (Tn=0.0) should return 0.0 without raising ZeroDivisionError."""
    assert glass_transmissivity(0.0) == 0.0

def test_glass_transmissivity_zero_in_list():
    """glass_transmissivity([..., 0.0, ...]) should include 0.0 without raising."""
    assert glass_transmissivity([0.88, 0.0, 0.50]) == [0.958, 0.0, 0.545]


def test_write_glass_3channel(tmp_path):
    res = write_material([0.88, 0.85, 0.80], material_type=0, channel_type=0,
                         name="myglass", work_dir=str(tmp_path))
    assert len(res["files"]) == 1
    content = open(res["files"][0]).read()
    assert content.startswith("void glass myglass")
    # transmittance converted to transmissivity
    assert res["channel_output"] == glass_transmissivity([0.88, 0.85, 0.80])

def test_write_plastic_9channel(tmp_path):
    ch = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    res = write_material(ch, material_type=1, channel_type=1, name="wall",
                         roughness=0.0, specularity=0.0, work_dir=str(tmp_path))
    assert len(res["files"]) == 3  # _a/_b/_c
    a = open([f for f in res["files"] if f.endswith("_a.rad")][0]).read()
    assert a.startswith("void plastic wall_a") and "5 0.1 0.2 0.3 0.0 0.0" in a
