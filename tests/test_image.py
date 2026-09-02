from hcl_radiance.masks import fov_mask_paths, synthesize_fov_masks_steps

def test_fov_mask_paths_default_names(tmp_path):
    paths = fov_mask_paths(str(tmp_path))
    assert paths["upper_inner"].endswith("1_upper_inner.hdr")
    assert paths["lower_outer"].endswith("4_lower_outer.hdr")

def test_synthesize_is_flagged_approximate():
    steps, note = synthesize_fov_masks_steps(resolution=512, mask_dir="/m")
    assert "approximate" in note.lower()
    assert len(steps) == 4

import hcl_radiance.image as image

def test_run_image_emits_when_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(image, "_available", lambda: False)
    out = image.run_image(scene_sets=[["m_a.rad", "sky_a.rad", "g.rad"],
                                      ["m_b.rad", "sky_b.rad", "g.rad"],
                                      ["m_c.rad", "sky_c.rad", "g.rad"]],
                          channel_type=1, work_dir=str(tmp_path), fov_weighting=False, run=True)
    assert out["ran"] is False
    blob = " ".join(out["commands"])
    assert "rpict" in blob and "pcomb" in blob  # maps built

def test_run_image_3channel_one_rpict(monkeypatch, tmp_path):
    monkeypatch.setattr(image, "_available", lambda: False)
    out = image.run_image(scene_sets=[["m.rad", "sky.rad", "g.rad"]], channel_type=0,
                          work_dir=str(tmp_path), run=True)
    assert sum(1 for c in out["commands"] if c.startswith("rpict")) == 1

def test_mask_resize_steps_targets_render_resolution():
    from hcl_radiance.masks import fov_mask_paths, mask_resize_steps
    steps, resized = mask_resize_steps(fov_mask_paths("/m"), x=800, y=600)
    blob = " ".join(" ".join(s["cmd"]) for s in steps)
    assert "pfilt" in blob and "-x 800" in blob and "-y 600" in blob
    assert len(steps) == 4
    assert resized["upper_inner"].endswith("mask_upper_inner.hdr")

def test_fov_weighting_emits_opt_in_caveat(monkeypatch, tmp_path):
    """fov_weighting=True must surface the non-standardized/never-threshold caveat in notes;
    the standards-aligned default (False) must NOT carry it."""
    import hcl_radiance.image as image
    monkeypatch.setattr(image, "_available", lambda: False)
    on = image.run_image(scene_sets=[["m.rad", "sky.rad", "g.rad"]], channel_type=0,
                         work_dir=str(tmp_path / "on"), fov_weighting=True, run=True)
    off = image.run_image(scene_sets=[["m.rad", "sky.rad", "g.rad"]], channel_type=0,
                          work_dir=str(tmp_path / "off"), fov_weighting=False, run=True)
    assert any("standards-aligned" in n or "not a threshold" in n.lower() for n in on["notes"])
    assert not any("threshold" in n.lower() for n in off["notes"])
    assert on["weighting"] == "fov_ipRGC"
    assert off["weighting"] == "cosine_vertical"

def test_run_image_fov_resizes_supplied_masks(monkeypatch, tmp_path):
    import hcl_radiance.image as image
    from hcl_radiance.masks import fov_mask_paths
    monkeypatch.setattr(image, "_available", lambda: False)
    md = tmp_path / "masks"
    md.mkdir()
    # create the four shipped-mask files so the faithful (supplied) path is taken
    for p in fov_mask_paths(str(md)).values():
        open(p, "w").close()
    out = image.run_image(scene_sets=[["m.rad", "sky.rad", "g.rad"]], channel_type=0,
                          work_dir=str(tmp_path), x=800, y=800,
                          fov_weighting=True, mask_dir=str(md), run=True)
    blob = " ".join(out["commands"])
    assert "pfilt" in blob and "-x 800" in blob          # masks resampled to render size
    assert "mask_upper_inner.hdr" in blob                # FOV reads the RESIZED masks
