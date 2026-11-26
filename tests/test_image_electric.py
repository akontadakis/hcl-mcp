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


# ---- review 2026-11-26, G10: the electric lights are in the eye quantities, not only in glare ----

_LAMP = [{"ies": "lamp.ies", "placement": {"positions": [{"xyz": [0, 0, 3]}]}, "wattage": 40}]


def _plan(monkeypatch, tmp_path, channel_type, **kw):
    monkeypatch.setattr(image, "_available", lambda: False)
    sets = [["m.rad", "sky.rad", "g.rad"]] * (1 if channel_type == 0 else 3)
    return image.run_image(scene_sets=sets, channel_type=channel_type, work_dir=str(tmp_path),
                           run=True, **kw)


def _first(commands, word):
    return next(i for i, c in enumerate(commands) if word in c)


def test_the_eye_irradiance_is_read_from_the_image_with_the_lights_in_it(monkeypatch, tmp_path):
    """rgb.txt came from img0.hdr, the render WITHOUT the luminaires. A room lit only by its
    luminaires gave a black image and an eye irradiance of zero."""
    out = _plan(monkeypatch, tmp_path, 0, electric_lights=_LAMP)
    eye = next(c for c in out["commands"] if c.startswith("vwright"))
    assert "combined0.hdr" in eye and "img0.hdr" not in eye
    # ... which has to exist by then
    assert _first(out["commands"], "> combined0.hdr") < _first(out["commands"], "vwright")
    assert any("include the electric lights" in n for n in out["notes"])


def test_the_nine_channel_maps_are_built_from_the_images_with_the_lights_in_them(
        monkeypatch, tmp_path):
    out = _plan(monkeypatch, tmp_path, 1, electric_lights=_LAMP)
    mel = next(c for c in out["commands"] if "> melanopic.hdr" in c)
    assert all(f"combined{i}.hdr" in mel for i in range(3))
    assert not any(f"img{i}.hdr" in mel for i in range(3))
    assert _first(out["commands"], "> combined2.hdr") < _first(out["commands"], "> melanopic.hdr")


def test_without_electric_lights_nothing_changes(monkeypatch, tmp_path):
    out = _plan(monkeypatch, tmp_path, 0)
    eye = next(c for c in out["commands"] if c.startswith("vwright"))
    assert "img0.hdr" in eye and not any("combined" in c for c in out["commands"])
    assert not any("electric" in n for n in out["notes"])


def test_a_finished_run_names_the_lit_image_and_keeps_the_daylight_one(monkeypatch, tmp_path):
    monkeypatch.setattr(image, "_available", lambda: True)
    monkeypatch.setattr(image, "_run_with_colorize",
                        lambda steps, work_dir, available: {"ran": True, "returncode": 0,
                                                            "outputs": []})
    monkeypatch.setattr(image, "engine_provenance", lambda work: {})
    out = image.run_image(scene_sets=[["m.rad", "g.rad"]], channel_type=0,
                          work_dir=str(tmp_path), electric_lights=_LAMP, run=True)
    assert [m.rsplit("/", 1)[-1] for m in out["maps"]] == ["combined0.hdr"]
    assert [m.rsplit("/", 1)[-1] for m in out["daylight_only_images"]] == ["img0.hdr"]
