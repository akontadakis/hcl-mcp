import os, asyncio
from hcl_mcp.server import preview_scene

ROOT = os.path.join(os.path.dirname(__file__), "fixtures")
OBJ = os.path.join(ROOT, "office_room.obj")
SIDE = os.path.join(ROOT, "office_room_material_map.json")
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
LUMS = ["Luminaire_L09_1", "Luminaire_L09_2", "Luminaire_L09_3", "Luminaire_L09_4"]


def _is_png(path):
    assert os.path.exists(path) and path.endswith(".png")
    assert os.path.getsize(path) > 0
    with open(path, "rb") as fh:
        assert fh.read(8) == PNG_MAGIC


def test_preview_scene_all(tmp_path):
    res = asyncio.run(preview_scene(obj_path=OBJ, sidecar=SIDE, render="all",
                                    luminaire_groups=LUMS, work_dir=str(tmp_path)))
    assert res["format"] == "png"
    assert len(res["image_paths"]) == 2                    # plan + 3d
    for p in res["image_paths"]:
        _is_png(p)


def test_preview_scene_unknown_render_warns_and_falls_back_to_all(tmp_path):
    res = asyncio.run(preview_scene(obj_path=OBJ, sidecar=SIDE, render="bogus_preset",
                                    grid_pts=[[0.0, 0.0, 0.8, 0, 0, 1]],
                                    work_dir=str(tmp_path)))
    assert any("bogus_preset" in w and "all" in w for w in res["warnings"])
    assert len(res["image_paths"]) == 2                    # 'all' -> plan + 3d


def test_preview_scene_no_point_layers_warns(tmp_path):
    res = asyncio.run(preview_scene(obj_path=OBJ, sidecar=SIDE, render="all",
                                    work_dir=str(tmp_path)))
    assert res["layers"] == {}
    assert any("no point layers" in w for w in res["warnings"])


def test_preview_scene_reports_luminaires_without_point_layers(tmp_path):
    res = asyncio.run(preview_scene(obj_path=OBJ, sidecar=SIDE, render="all",
                                    luminaire_groups=LUMS, work_dir=str(tmp_path)))
    assert res["layers"].get("luminaires", 0) > 0
    assert not any("no point layers" in w for w in res["warnings"])


def test_preview_scene_reads_pts_path_list(tmp_path):
    pts1 = tmp_path / "observer_1.pts"
    pts2 = tmp_path / "observer_2.pts"
    pts1.write_text("1.0 1.0 1.2 0 0 1\n2.0 1.0 1.2 0 0 1\n")
    pts2.write_text("3.0 1.0 1.2 0 0 1\n")

    res = asyncio.run(preview_scene(obj_path=OBJ, sidecar=SIDE, render="all",
                                    observer_pts=[str(pts1), str(pts2)],
                                    work_dir=str(tmp_path)))

    assert res["layers"]["observers"] == 3               # 2 rows from pts1 + 1 row from pts2
    assert len(res["image_paths"]) == 2                   # plan + 3d
    for p in res["image_paths"]:
        _is_png(p)
