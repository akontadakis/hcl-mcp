import hcl_radiance.image as image

def test_run_image_electric_emits_extra_octrees_and_glare(monkeypatch, tmp_path):
    monkeypatch.setattr(image, "_available", lambda: False)
    out = image.run_image(
        scene_sets=[["m.rad", "sky.rad", "g.rad"]], channel_type=0, work_dir=str(tmp_path),
        electric_lights=[{"ies": "lamp.ies", "placement": {"positions": [{"xyz": [0, 0, 3]}]},
                          "wattage": 40}],
        glare=True, run=True)
    assert out["ran"] is False
    blob = " ".join(out["commands"])
    assert "ies2rad" in blob and "evalglare" in blob
    assert any("combined" in c for c in out["commands"])
    assert out["total_wattage"] == 40

def test_run_image_glare_without_electric(monkeypatch, tmp_path):
    monkeypatch.setattr(image, "_available", lambda: False)
    out = image.run_image(scene_sets=[["m.rad", "sky.rad", "g.rad"]], channel_type=0,
                          work_dir=str(tmp_path), glare=True, run=True)
    assert out["ran"] is False
    assert any("evalglare" in c for c in out["commands"])
