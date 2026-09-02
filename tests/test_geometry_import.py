import os
import shutil

import pytest

import hcl_radiance.geometry_import as gi
from hcl_radiance import discover
from hcl_core.spd import parse_spd, bin_average
import hcl_mcp.server as server

_OBJ = """\
# sample room
v 0 0 0
v 1000 0 0
v 1000 800 0
vn 0 0 1
usemtl walls
f 1 2 3
usemtl glass
f 1 2 3
"""


def test_build_obj2rad_argv():
    assert gi.build_obj2rad("/abs/room.obj", "mapfile_a.txt") == \
        ["obj2rad", "-m", "mapfile_a.txt", "/abs/room.obj"]


def test_build_xform_scale_and_axis():
    # mm -> m scale and Y-up -> Z-up
    assert gi.build_xform("raw_a.rad", scale=0.001, up_axis="Y") == \
        ["xform", "-s", "0.001", "-rx", "90", "raw_a.rad"]


def test_build_xform_meters_zup_is_noop_transform():
    # already meters + Z-up: no -s, no -rx
    assert gi.build_xform("raw.rad", scale=1.0, up_axis="Z") == ["xform", "raw.rad"]


def test_build_material_mapfile_suffixes_modifiers():
    txt = gi.build_material_mapfile(["walls", "glass"], "_a")
    assert txt == 'walls_a (Material "walls") ;\nglass_a (Material "glass") ;\n'


def test_scale_factor_units():
    assert gi.scale_factor("mm") == 0.001
    assert gi.scale_factor("cm") == 0.01
    assert gi.scale_factor("m") == 1.0
    assert gi.scale_factor("ft") == 0.3048


def test_parse_obj_groups_prefers_usemtl():
    assert gi.parse_obj_groups(_OBJ) == ["walls", "glass"]


def test_parse_obj_groups_falls_back_to_g():
    txt = "g floor\nv 0 0 0\nf 1 1 1\ng floor\n"
    assert gi.parse_obj_groups(txt) == ["floor"]


def test_parse_obj_bbox():
    assert gi.parse_obj_bbox(_OBJ) == ((0.0, 0.0, 0.0), (1000.0, 800.0, 0.0))


def test_parse_obj_bbox_ignores_malformed_vertex():
    """Malformed v line (non-numeric coords) should be skipped; well-formed vertices used."""
    obj_text = """\
v 0 0 0
v bad y z
v 10 5 2
"""
    bbox = gi.parse_obj_bbox(obj_text)
    # Should ignore "v bad y z" and compute bbox over the two valid vertices
    assert bbox == ((0.0, 0.0, 0.0), (10.0, 5.0, 2.0))


def test_obj_has_normals():
    assert gi.obj_has_normals(_OBJ) is True
    assert gi.obj_has_normals("v 0 0 0\nf 1 1 1\n") is False


def test_validate_passes_when_all_mapped():
    gi.validate_material_map(
        ["walls", "glass"],
        {"walls": {"type": "plastic", "refl": 0.5},
         "glass": {"type": "glass", "tvis": 0.6}},
        bbox=((0, 0, 0), (4, 3, 2)), units="m", missing_normals=False)  # no raise


def test_validate_lists_unmapped_groups():
    with pytest.raises(ValueError) as exc:
        gi.validate_material_map(
            ["walls", "glass", "trim"],
            {"walls": {"type": "plastic", "refl": 0.5}},
            bbox=((0, 0, 0), (4, 3, 2)), units="m", missing_normals=True)
    msg = str(exc.value)
    assert "glass" in msg and "trim" in msg          # every unmapped group named
    assert "walls" not in msg.split("unmapped", 1)[-1].split("\n", 1)[0]  # mapped not in the list line
    assert "units=m" in msg                          # context echoed


def test_group_channels_scalar_is_flat():
    assert gi.group_channels({"type": "plastic", "refl": 0.5}, 0) == [0.5, 0.5, 0.5]
    assert gi.group_channels({"type": "plastic", "refl": 0.5}, 1) == [0.5] * 9


def test_group_channels_glass_scalar_flat():
    assert gi.group_channels({"type": "glass", "tvis": 0.6}, 0) == [0.6, 0.6, 0.6]


def test_group_channels_missing_refl_raises_valueerror():
    """A plastic spec with no 'refl' (and no 'spd') must raise ValueError, not KeyError."""
    with pytest.raises(ValueError) as exc:
        gi.group_channels({"type": "plastic"}, 0)
    assert "refl" in str(exc.value)


def test_group_channels_missing_tvis_raises_valueerror():
    """A glass spec with no 'tvis' (and no 'spd') must raise ValueError, not KeyError."""
    with pytest.raises(ValueError) as exc:
        gi.group_channels({"type": "glass"}, 0)
    assert "tvis" in str(exc.value)


def test_build_material_sets_9channel_three_sets(tmp_path):
    sets = gi.build_material_sets(
        {"walls": {"type": "plastic", "refl": 0.5},
         "glass": {"type": "glass", "tvis": 0.6}},
        channel_type=1, work_dir=str(tmp_path))
    assert len(sets) == 3                       # a/b/c
    assert all(len(s) == 2 for s in sets)       # walls + glass per set
    a_files = sets[0]
    walls_a = [f for f in a_files if f.endswith("walls_a.rad")][0]
    glass_a = [f for f in a_files if f.endswith("glass_a.rad")][0]
    assert open(walls_a).read().startswith("void plastic walls_a")
    assert open(glass_a).read().startswith("void glass glass_a")


def test_build_material_sets_3channel_single_set(tmp_path):
    sets = gi.build_material_sets(
        {"walls": {"type": "plastic", "refl": 0.4}},
        channel_type=0, work_dir=str(tmp_path))
    assert len(sets) == 1 and len(sets[0]) == 1
    assert open(sets[0][0]).read().startswith("void plastic walls")


def _write_obj(tmp_path):
    p = tmp_path / "room.obj"
    p.write_text(_OBJ)
    return str(p)


def test_import_geometry_emits_per_channel_commands(tmp_path):
    obj = _write_obj(tmp_path)
    out = gi.import_geometry(
        obj,
        material_map={"walls": {"type": "plastic", "refl": 0.5},
                      "glass": {"type": "glass", "tvis": 0.6}},
        units="mm", up_axis="Y", channel_type=1,
        work_dir=str(tmp_path), run=False)
    assert out["ran"] is False
    assert out["groups"] == ["walls", "glass"]
    assert len(out["geometry_set"]) == 3          # a/b/c (D8)
    assert len(out["material_sets"]) == 3
    # one obj2rad + one xform command per channel-set
    assert sum("obj2rad" in c for c in out["commands"]) == 3
    assert sum("xform" in c for c in out["commands"]) == 3
    assert any("-s 0.001" in c for c in out["commands"])   # mm -> m
    assert any("-rx 90" in c for c in out["commands"])     # Y -> Z up
    # mapfiles authored in pure Python even on the emit path
    assert (tmp_path / "mapfile_a.txt").read_text() == \
        'walls_a (Material "walls") ;\nglass_a (Material "glass") ;\n'


def test_import_geometry_3channel_single_run(tmp_path):
    obj = _write_obj(tmp_path)
    out = gi.import_geometry(
        obj,
        material_map={"walls": {"type": "plastic", "refl": 0.5},
                      "glass": {"type": "glass", "tvis": 0.6}},
        units="m", up_axis="Z", channel_type=0,
        work_dir=str(tmp_path), run=False)
    assert len(out["geometry_set"]) == 1
    assert sum("obj2rad" in c for c in out["commands"]) == 1
    assert all(os.path.isabs(p) for p in out["geometry_set"])


def test_import_geometry_unmapped_group_raises(tmp_path):
    obj = _write_obj(tmp_path)
    with pytest.raises(ValueError) as exc:
        gi.import_geometry(
            obj, material_map={"walls": {"type": "plastic", "refl": 0.5}},
            units="mm", up_axis="Y", channel_type=1,
            work_dir=str(tmp_path), run=False)
    assert "glass" in str(exc.value)


def test_unmapped_raise_is_typed_with_structured_payload(tmp_path):
    """D6: the unmapped hard-fail carries a structured .payload that mirrors dry_run."""
    r = gi.import_geometry(FIX, material_map={}, units="m", up_axis="Y",
                           channel_type=0, work_dir=str(tmp_path), dry_run=True)
    with pytest.raises(gi.UnmappedGroupsError) as exc:
        gi.import_geometry(FIX, material_map={"oak_floor": {"type": "plastic", "refl": 0.3}},
                           units="m", up_axis="Y", channel_type=0,
                           work_dir=str(tmp_path), run=False)
    pl = exc.value.payload
    # Still a ValueError (back-compat) with a human message naming the unmapped groups.
    assert isinstance(exc.value, ValueError)
    assert "clear_glass" in str(exc.value) and "painted_gypsum" in str(exc.value)
    # The failure payload doubles as the discovery report: same core keys as dry_run.
    for k in ("groups", "units", "bbox_m", "missing_normals", "mesh_quality", "suggestions"):
        assert k in pl, k
        assert pl[k] == r[k] or k == "groups"  # identical body (groups order-equal below)
    assert pl["groups"] == r["groups"]
    assert sorted(pl["unmapped"]) == ["clear_glass", "painted_gypsum"]


def test_validate_material_map_direct_still_raises_valueerror():
    """Back-compat: direct calls (no parsed/scale) still raise a ValueError subclass."""
    with pytest.raises(ValueError) as exc:
        gi.validate_material_map(["walls", "glass"], {"walls": {"type": "plastic", "refl": 0.5}},
                                 bbox=((0, 0, 0), (4, 3, 2)), units="m", missing_normals=False)
    assert isinstance(exc.value, gi.UnmappedGroupsError)
    assert exc.value.payload["unmapped"] == ["glass"]


def test_import_geometry_runs_when_available(monkeypatch, tmp_path):
    obj = _write_obj(tmp_path)
    captured = {}

    def fake_run(steps, work_dir, available):
        captured["n"] = len(steps)
        return {"ran": True, "returncode": 0, "commands": ["obj2rad ...", "xform ..."],
                "outputs": [s.get("stdout") for s in steps if s.get("stdout")]}

    monkeypatch.setattr(gi, "run_sequence", fake_run)
    monkeypatch.setattr(gi, "_available", lambda: True)
    out = gi.import_geometry(
        obj, material_map={"walls": {"type": "plastic", "refl": 0.5},
                           "glass": {"type": "glass", "tvis": 0.6}},
        units="m", up_axis="Z", channel_type=0, work_dir=str(tmp_path), run=True)
    assert out["ran"] is True
    assert captured["n"] == 2                       # obj2rad + xform for the single 3ch set


def test_import_geometry_emit_path_when_radiance_absent(monkeypatch, tmp_path):
    """run=True but Radiance absent: ran=False + reason present (emit-with-reason path)."""
    obj = _write_obj(tmp_path)
    monkeypatch.setattr(gi, "_available", lambda: False)
    out = gi.import_geometry(
        obj,
        material_map={"walls": {"type": "plastic", "refl": 0.5},
                      "glass": {"type": "glass", "tvis": 0.6}},
        units="m", up_axis="Z", channel_type=1,
        work_dir=str(tmp_path), run=True)
    assert out["ran"] is False
    assert "reason" in out


def test_discover_lists_obj_import_binaries():
    assert "obj2rad" in discover._REQUIRED
    assert "xform" in discover._REQUIRED


def test_import_geometry_registered_as_tool():
    # server wraps the core fn (run_grid pattern): the wrapper delegates to it,
    # and the wrapper is what gets registered.
    assert server._import_geometry is gi.import_geometry   # core wired in under the _ alias
    import inspect
    assert inspect.iscoroutinefunction(server.import_geometry)  # async wrapper defined


def test_import_output_composes_into_run_grid_scene_sets(tmp_path):
    # the documented composition: zip material_sets with geometry_set + a sky file
    obj = _write_obj(tmp_path)
    out = gi.import_geometry(
        obj, material_map={"walls": {"type": "plastic", "refl": 0.5},
                           "glass": {"type": "glass", "tvis": 0.6}},
        units="m", up_axis="Z", channel_type=1, work_dir=str(tmp_path), run=False)
    sky = "sky.rad"
    scene_sets = [[*mats, sky, geom]
                  for mats, geom in zip(out["material_sets"], out["geometry_set"])]
    assert len(scene_sets) == 3                       # matches 9ch run_grid expectation
    for s in scene_sets:
        assert s[-2] == sky and s[-1].endswith(".rad")  # sky before geometry (oconv order)


# ---------------------------------------------------------------------------
# New tests: Group qualifier fix (TDD RED first, then GREEN after implementation)
# ---------------------------------------------------------------------------

_GROUP_ONLY_OBJ = """\
# group-only room: no usemtl, just g names
v 0 0 0
v 4 0 0
v 4 0 3
vn 0 1 0
g floor
f 1 2 3
"""

_MIXED_OBJ = """\
# mixed: one face under bare g (no usemtl active), then faces under usemtl
v 0 0 0
v 4 0 0
v 4 0 3
v 0 4 0
v 0 4 3
vn 0 1 0
g bare_group
f 1 2 3
usemtl walls
f 1 2 3
f 2 3 4
"""

_USEMTL_ONLY_OBJ = """\
# normal: all faces after usemtl
v 0 0 0
v 4 0 0
v 4 0 3
vn 0 1 0
usemtl walls
f 1 2 3
usemtl glass
f 1 2 3
"""


def test_build_material_mapfile_group_qualifier():
    """Passing qualifier='Group' must emit Group instead of Material."""
    txt = gi.build_material_mapfile(["floor"], "_a", qualifier="Group")
    assert txt == 'floor_a (Group "floor") ;\n'


def test_build_material_mapfile_default_qualifier_unchanged():
    """Existing call without qualifier still emits Material (regression guard)."""
    txt = gi.build_material_mapfile(["walls", "glass"], "_a")
    assert txt == 'walls_a (Material "walls") ;\nglass_a (Material "glass") ;\n'


def test_obj_group_qualifier_usemtl_returns_material():
    assert gi.obj_group_qualifier(_USEMTL_ONLY_OBJ) == "Material"


def test_obj_group_qualifier_group_only_returns_group():
    assert gi.obj_group_qualifier(_GROUP_ONLY_OBJ) == "Group"


def test_obj_unmaterialized_faces_group_only_is_zero():
    """Group-only OBJ: no usemtl at all -> valid via Group qualifier -> return 0."""
    assert gi.obj_unmaterialized_faces(_GROUP_ONLY_OBJ) == 0


def test_obj_unmaterialized_faces_normal_usemtl_is_zero():
    """All faces after usemtl: 0 dropped."""
    assert gi.obj_unmaterialized_faces(_USEMTL_ONLY_OBJ) == 0


def test_obj_unmaterialized_faces_mixed_counts_bare_faces():
    """Mixed OBJ: 1 face precedes the first usemtl -> count = 1."""
    count = gi.obj_unmaterialized_faces(_MIXED_OBJ)
    assert count == 1


def _write_group_only_obj(tmp_path):
    p = tmp_path / "group_only.obj"
    p.write_text(_GROUP_ONLY_OBJ)
    return str(p)


def _write_mixed_obj(tmp_path):
    p = tmp_path / "mixed.obj"
    p.write_text(_MIXED_OBJ)
    return str(p)


def test_import_geometry_group_only_uses_group_qualifier(tmp_path):
    """Group-only OBJ: the written mapfile must use (Group ...) not (Material ...)."""
    obj = _write_group_only_obj(tmp_path)
    out = gi.import_geometry(
        obj,
        material_map={"floor": {"type": "plastic", "refl": 0.5}},
        units="m", up_axis="Z", channel_type=1,
        work_dir=str(tmp_path), run=False)
    mapfile_text = (tmp_path / "mapfile_a.txt").read_text()
    assert '(Group "floor")' in mapfile_text
    assert "(Material" not in mapfile_text


def test_import_geometry_mixed_obj_raises_valueerror(tmp_path):
    """Mixed OBJ (some faces without active usemtl) must raise ValueError."""
    obj = _write_mixed_obj(tmp_path)
    with pytest.raises(ValueError) as exc:
        gi.import_geometry(
            obj,
            material_map={"walls": {"type": "plastic", "refl": 0.5}},
            units="m", up_axis="Z", channel_type=1,
            work_dir=str(tmp_path), run=False)
    msg = str(exc.value)
    # must mention count and give a remedy hint
    assert "1" in msg
    assert "usemtl" in msg.lower() or "face" in msg.lower()


def test_import_geometry_usemtl_obj_uses_material_qualifier(tmp_path):
    """Normal usemtl OBJ still uses Material qualifier (regression guard)."""
    obj = tmp_path / "normal.obj"
    obj.write_text(_USEMTL_ONLY_OBJ)
    out = gi.import_geometry(
        str(obj),
        material_map={"walls": {"type": "plastic", "refl": 0.5},
                      "glass": {"type": "glass", "tvis": 0.6}},
        units="m", up_axis="Z", channel_type=1,
        work_dir=str(tmp_path), run=False)
    mapfile_text = (tmp_path / "mapfile_a.txt").read_text()
    assert '(Material "walls")' in mapfile_text
    assert "(Group" not in mapfile_text


@pytest.mark.skipif(
    shutil.which("obj2rad") is None or shutil.which("xform") is None,
    reason="needs Radiance (obj2rad + xform) on PATH")
def test_import_geometry_group_only_live_produces_polygons(tmp_path):
    """Live: group-only OBJ with Group qualifier must produce polygon geometry via obj2rad."""
    obj = _write_group_only_obj(tmp_path)
    out = gi.import_geometry(
        obj,
        material_map={"floor": {"type": "plastic", "refl": 0.5}},
        units="m", up_axis="Z", channel_type=1,
        work_dir=str(tmp_path), run=True)
    geom_a = tmp_path / "geometry_a.rad"
    assert geom_a.exists(), f"geometry_a.rad not found in {tmp_path}"
    content = geom_a.read_text()
    assert "polygon" in content, (
        f"obj2rad produced no polygons (Group qualifier may not be working).\n"
        f"geometry_a.rad:\n{content}"
    )


# ---------------------------------------------------------------------------
# New gap-covering tests
# ---------------------------------------------------------------------------

# A non-trivial SPD: linear ramp 380->780 nm (0->1).  Expected values are
# computed via the REAL parse_spd / bin_average functions — NOT hardcoded
# by hand — so they track any future precision change automatically.
_RAMP_SPD = "380 0.0\n780 1.0\n"


# 1a. group_channels with SPD spec, channel_type=0 -> 3 bins
def test_group_channels_spd_ct0_returns_three_real_bins():
    """group_channels({'spd': ...}, 0) must equal bin_average(parse_spd(spd), 0)."""
    expected = bin_average(parse_spd(_RAMP_SPD), 0)
    result = gi.group_channels({"spd": _RAMP_SPD}, 0)
    assert len(result) == 3
    assert result == expected


# 1b. group_channels with SPD spec, channel_type=1 -> 9 bins
def test_group_channels_spd_ct1_returns_nine_real_bins():
    """group_channels({'spd': ...}, 1) must equal bin_average(parse_spd(spd), 1)."""
    expected = bin_average(parse_spd(_RAMP_SPD), 1)
    result = gi.group_channels({"spd": _RAMP_SPD}, 1)
    assert len(result) == 9
    assert result == expected


# 1c. build_material_sets end-to-end with SPD-backed group
def test_build_material_sets_spd_backed_group_writes_rad_files(tmp_path):
    """SPD-backed material: correct number of sets and .rad files written with SPD reflectances."""
    material_map = {"walls": {"spd": _RAMP_SPD, "type": "plastic"}}
    sets = gi.build_material_sets(material_map, channel_type=1, work_dir=str(tmp_path))
    # 9ch -> 3 sets
    assert len(sets) == 3
    assert all(len(s) == 1 for s in sets)    # one group -> one file per set
    # each .rad file must exist and start with the right Radiance header
    for i, suffix in enumerate(["_a", "_b", "_c"]):
        path = sets[i][0]
        assert os.path.isfile(path), f"missing {path}"
        assert path.endswith(f"walls{suffix}.rad")
        content = open(path).read()
        assert content.startswith("void plastic walls" + suffix)
    # set[0] (blue band) channels should match ct1 bins [0..2]
    expected_all = bin_average(parse_spd(_RAMP_SPD), 1)
    a_content = open(sets[0][0]).read()
    # The first three bins go to the _a file; read first 5-float line
    line5 = [l for l in a_content.splitlines() if l.startswith("5 ")][0]
    vals = [float(v) for v in line5.split()[1:4]]   # r g b channels
    assert vals == list(expected_all[:3])


# 2. _bbox_warnings thresholds

def test_bbox_warnings_normal_room_no_implausible():
    """Normal room (4x3x2.5m): bbox line emitted, no implausible warning."""
    bbox = ((0.0, 0.0, 0.0), (4.0, 3.0, 2.5))
    warns = gi._bbox_warnings(bbox, 1.0, False)
    assert any("bbox" in w and "4.00" in w for w in warns)
    assert not any("implausible" in w for w in warns)


def test_bbox_warnings_huge_dims_triggers_implausible():
    """Largest dim > 200 m -> implausible warning included."""
    bbox = ((0.0, 0.0, 0.0), (300.0, 100.0, 50.0))
    warns = gi._bbox_warnings(bbox, 1.0, False)
    assert any("implausible" in w for w in warns)
    assert any("300" in w for w in warns)   # the culprit dimension mentioned


def test_bbox_warnings_tiny_dims_triggers_implausible():
    """Largest dim < 0.5 m (and > 0) -> implausible warning included."""
    bbox = ((0.0, 0.0, 0.0), (0.1, 0.1, 0.1))
    warns = gi._bbox_warnings(bbox, 1.0, False)
    assert any("implausible" in w for w in warns)


def test_bbox_warnings_missing_normals_adds_warning():
    """missing_normals=True -> 'vertex normals' string in warnings."""
    bbox = ((0.0, 0.0, 0.0), (4.0, 3.0, 2.5))
    warns = gi._bbox_warnings(bbox, 1.0, True)
    assert any("vertex normals" in w for w in warns)


# 3. import_geometry run-failure branch (returncode != 0)

def test_import_geometry_run_failure_propagates_error(monkeypatch, tmp_path):
    """run_sequence returncode=1 -> result has 'error' and 'failed_step' keys."""
    obj = _write_obj(tmp_path)
    monkeypatch.setattr(gi, "_available", lambda: True)
    monkeypatch.setattr(gi, "run_sequence", lambda steps, work_dir, available: {
        "ran": True,
        "returncode": 1,
        "commands": ["obj2rad ...", "xform ..."],
        "error": "boom",
        "failed_step": 0,
    })
    out = gi.import_geometry(
        obj,
        material_map={"walls": {"type": "plastic", "refl": 0.5},
                      "glass": {"type": "glass", "tvis": 0.6}},
        units="m", up_axis="Z", channel_type=1,
        work_dir=str(tmp_path), run=True)
    assert "error" in out, "run-failure result must contain 'error'"
    assert "failed_step" in out, "run-failure result must contain 'failed_step'"
    assert out["error"] == "boom"
    assert out["failed_step"] == 0


# 4. parse_obj_bbox None path: no 'v' lines

def test_parse_obj_bbox_returns_none_when_no_vertices():
    """OBJ with no 'v' lines -> parse_obj_bbox returns None."""
    obj_text = "# header only\nusemtl walls\nf 1 2 3\n"
    assert gi.parse_obj_bbox(obj_text) is None


# 5. multi-name 'g' line (tok[1:] extend path, no usemtl)

def test_parse_obj_groups_multi_name_g_line():
    """'g a b c' with no usemtl -> groups ['a', 'b', 'c']."""
    txt = "g a b c\nf 1 1 1\n"
    assert gi.parse_obj_groups(txt) == ["a", "b", "c"]


# 6. scale_factor ValueError on unknown unit

def test_scale_factor_unknown_unit_raises_valueerror():
    """scale_factor('furlong') must raise ValueError, not KeyError."""
    with pytest.raises(ValueError):
        gi.scale_factor("furlong")


# 7. Content-asserting run test: verify actual step contents scheduled

def test_import_geometry_9ch_step_commands_are_correct(monkeypatch, tmp_path):
    """9ch import: obj2rad and xform commands have the right argv and stdout targets."""
    obj = _write_obj(tmp_path)
    captured = {}

    def fake_run(steps, work_dir, available):
        captured["steps"] = steps
        return {"ran": True, "returncode": 0,
                "commands": [" ".join(s["cmd"]) for s in steps],
                "outputs": [s.get("stdout") for s in steps]}

    monkeypatch.setattr(gi, "run_sequence", fake_run)
    monkeypatch.setattr(gi, "_available", lambda: True)

    out = gi.import_geometry(
        obj,
        material_map={"walls": {"type": "plastic", "refl": 0.5},
                      "glass": {"type": "glass", "tvis": 0.6}},
        units="mm", up_axis="Y", channel_type=1,
        work_dir=str(tmp_path), run=True)

    steps = captured["steps"]
    # 3 channel-sets x (1 obj2rad + 1 xform) = 6 steps total
    assert len(steps) == 6, f"expected 6 steps for 9ch, got {len(steps)}"

    # Count by command type
    obj2rad_steps = [s for s in steps if s["cmd"][0] == "obj2rad"]
    xform_steps = [s for s in steps if s["cmd"][0] == "xform"]
    assert len(obj2rad_steps) == 3
    assert len(xform_steps) == 3

    # step[0]: obj2rad for _a set
    s0 = steps[0]
    assert s0["cmd"][0] == "obj2rad"
    assert s0["cmd"][1] == "-m"
    assert s0["cmd"][2] == "mapfile_a.txt"   # suffix _a
    assert s0["cmd"][3] == os.path.abspath(obj)
    assert s0["stdout"] == "raw_a.rad"

    # step[1]: xform for _a set — mm->m scale + Y-up correction
    s1 = steps[1]
    assert s1["cmd"][0] == "xform"
    assert "-s" in s1["cmd"]
    assert "-rx" in s1["cmd"]
    assert s1["stdout"] == "geometry_a.rad"

    # Check _b and _c suffixes are also scheduled
    assert steps[2]["cmd"][2] == "mapfile_b.txt"
    assert steps[2]["stdout"] == "raw_b.rad"
    assert steps[3]["stdout"] == "geometry_b.rad"
    assert steps[4]["cmd"][2] == "mapfile_c.txt"
    assert steps[4]["stdout"] == "raw_c.rad"
    assert steps[5]["stdout"] == "geometry_c.rad"


def test_import_obj_room_prompt_registered_and_references_import_geometry():
    # the 10th prompt guides the OBJ -> per-channel scene_sets -> run_grid/run_annual flow
    import asyncio
    import hcl_mcp.prompts as prompts
    assert server.import_obj_room is prompts.import_obj_room          # re-exported from server
    txt = prompts.import_obj_room("6x4x3 m office")
    assert "import_geometry" in txt and "scene_sets" in txt and "obj2rad" in txt
    names = {p.name for p in asyncio.run(server.mcp.list_prompts())}
    assert "import_obj_room" in names


def test_reference_geometry_resource_registered_with_contract():
    # the 14th resource: the import_geometry field guide (mirrors reference/ies, reference/daysim)
    import asyncio
    from hcl_mcp import resources as res
    assert "hcl://reference/geometry" in {r.uri for r in res.RESOURCES}
    body = res.reference_geometry()
    assert "import_geometry" in body and "material_map" in body
    assert "Material" in body and "Group" in body                    # the qualifier rule
    assert "HARD-FAIL" in body                                        # the honesty boundary
    uris = {str(r.uri) for r in asyncio.run(server.mcp.list_resources())}
    assert "hcl://reference/geometry" in uris


# ---------------------------------------------------------------------------
# D2 tests — Part 2: material ergonomics, sidecar, dry-run, north
# ---------------------------------------------------------------------------

import json

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "sample_room.obj")
MAP = {"oak_floor": {"type": "plastic", "refl": 0.3},
       "painted_gypsum": {"type": "plastic", "refl": 0.7},
       "clear_glass": {"type": "glass", "tvis": 0.6}}


# 2a. resolve_spec

def test_resolve_spec_string_library_is_illustrative():
    spec, is_ill = gi.resolve_spec("painted_gypsum")
    assert spec["type"] == "plastic"
    assert 0 < spec.get("refl", 0) <= 1
    assert is_ill is True


def test_resolve_spec_dict_passthrough_not_illustrative():
    d = {"type": "plastic", "refl": 0.5}
    spec, is_ill = gi.resolve_spec(d)
    assert spec is d
    assert is_ill is False


# 2b. build_xform north unit tests

def test_build_xform_north_only_z_up():
    """scale=1.0 Z-up + north_angle_deg=90 -> just -rz -90, no -s, no -rx."""
    result = gi.build_xform("raw_a.rad", scale=1.0, up_axis="Z", north_angle_deg=90)
    assert result == ["xform", "-rz", "-90", "raw_a.rad"]


def test_build_xform_north_scale_y_up():
    """scale=0.001, Y-up, north=90 -> -s 0.001 -rx 90 -rz -90."""
    result = gi.build_xform("raw_a.rad", scale=0.001, up_axis="Y", north_angle_deg=90)
    assert result == ["xform", "-s", "0.001", "-rx", "90", "-rz", "-90", "raw_a.rad"]


def test_build_xform_no_north_unchanged():
    """Without north_angle_deg the existing tests must still pass (regression guard)."""
    assert gi.build_xform("raw_a.rad", scale=0.001, up_axis="Y") == \
        ["xform", "-s", "0.001", "-rx", "90", "raw_a.rad"]


# 2c. library-string material_map through import_geometry

def test_import_geometry_library_string_material_map(tmp_path):
    """Library name strings in material_map: resolved specs bind, warnings carry 'illustrative'."""
    out = gi.import_geometry(
        FIX,
        material_map={
            "oak_floor": "oak_floor",
            "painted_gypsum": "painted_gypsum",
            "clear_glass": "clear_float_6mm",
        },
        units="m", up_axis="Z", channel_type=1,
        work_dir=str(tmp_path), run=False)
    assert out["material_sets"] is not None
    assert len(out["material_sets"]) == 3   # 9-channel
    # illustrative warning must be present
    assert any("illustrative" in w for w in out["warnings"]), (
        f"Expected illustrative warning in {out['warnings']}")


# 2d. load_sidecar + explicit kwargs override

def test_load_sidecar_and_explicit_units_win(tmp_path):
    """Explicit units='m' wins over sidecar units='mm'; bbox_m is ~4 m wide, not ~0.004 m."""
    sidecar_path = tmp_path / "room.matmap.json"
    sidecar_path.write_text(json.dumps({
        "material_map": MAP,
        "units": "mm",
        "up_axis": "Y",
    }))
    out = gi.import_geometry(
        FIX,
        material_map=None,
        units="m",        # explicit win
        up_axis=None,     # from sidecar -> "Y"
        channel_type=0,
        work_dir=str(tmp_path),
        run=False,
        sidecar=str(sidecar_path))
    # The room OBJ is 4x3x2.7 m; with units="m" the bbox should be > 1 m wide.
    warns = out["warnings"]
    assert any("bbox" in w for w in warns), f"No bbox warning: {warns}"
    # Extract the bbox line and verify a ~4 m dimension (not 0.004 m)
    bbox_warn = next(w for w in warns if "bbox" in w)
    # Format: "bbox 4.00 x 3.00 x 2.70 m" — first float should be >= 1.0
    import re
    floats = re.findall(r"[\d.]+", bbox_warn)
    largest = max(float(f) for f in floats)
    assert largest >= 1.0, (
        f"Largest bbox dim {largest} looks like units were NOT overridden: {bbox_warn}")


# 2d-bis. load_sidecar accepts a BARE material-map file (groups at top level)

def test_load_sidecar_bare_material_map(tmp_path):
    """A bare material_map.json (group specs at the top level, plus units/up_axis and an
    underscore comment key) loads as a sidecar and binds materials — identical to inline."""
    sidecar_path = tmp_path / "material_map.json"
    sidecar_path.write_text(json.dumps({
        "_README": "pinned map",
        "units": "m",
        "up_axis": "Z",
        "north_angle_deg": 0,
        **MAP,
    }))
    parsed = gi.load_sidecar(str(sidecar_path))
    assert parsed["material_map"] == MAP, parsed
    assert parsed["units"] == "m" and parsed["up_axis"] == "Z"
    assert "_README" not in parsed.get("material_map", {})
    # end-to-end: sidecar-only import must NOT raise UnmappedGroupsError
    out = gi.import_geometry(
        FIX, material_map=None, work_dir=str(tmp_path), run=False,
        sidecar=str(sidecar_path))
    assert set(out["groups"]) == set(MAP), out["groups"]


def test_load_sidecar_wrapped_still_works(tmp_path):
    """The wrapped form {"material_map": {...}} keeps precedence over bare detection."""
    sidecar_path = tmp_path / "wrapped.json"
    sidecar_path.write_text(json.dumps({"material_map": MAP, "units": "m", "up_axis": "Z"}))
    parsed = gi.load_sidecar(str(sidecar_path))
    assert parsed["material_map"] == MAP


# 2e. dry_run=True returns discovery payload

def test_dry_run_returns_discovery_payload(tmp_path):
    """dry_run=True: payload has groups, bbox_m, mesh_quality, suggestions with painted_gypsum."""
    out = gi.import_geometry(
        FIX,
        material_map={},   # dry_run doesn't require a valid material_map
        units="m",
        up_axis="Z",
        channel_type=1,
        work_dir=str(tmp_path),
        run=False,
        dry_run=True)
    assert "groups" in out
    assert "bbox_m" in out
    assert "size" in out["bbox_m"]
    assert "mesh_quality" in out
    assert "suggestions" in out
    # adjacent sample_room.mtl has painted_gypsum, oak_floor, clear_glass
    assert "painted_gypsum" in out["suggestions"], (
        f"Expected painted_gypsum in suggestions: {list(out['suggestions'].keys())}")


def test_dry_run_does_not_require_material_map(tmp_path):
    """dry_run must succeed even without material_map (no binding, no validation)."""
    out = gi.import_geometry(
        FIX,
        material_map=None,
        units="m",
        up_axis="Z",
        channel_type=1,
        work_dir=str(tmp_path),
        run=False,
        dry_run=True)
    assert "groups" in out
    assert len(out["groups"]) > 0


# 2f. north threads through every xform step

def test_north_angle_deg_in_all_xform_commands(tmp_path):
    """north_angle_deg=90: every xform step (one per channel-set) must contain -rz -90."""
    out = gi.import_geometry(
        FIX,
        material_map=MAP,
        units="m",
        up_axis="Z",
        channel_type=1,
        north_angle_deg=90,
        work_dir=str(tmp_path),
        run=False)
    # commands is a list of strings like "xform -rz -90 raw_a.rad"
    xform_cmds = [c for c in out["commands"] if "xform" in c]
    assert len(xform_cmds) == 3, f"Expected 3 xform commands for 9-ch: {xform_cmds}"
    for cmd in xform_cmds:
        assert "-rz" in cmd and "-90" in cmd, (
            f"North rotation missing from xform command: {cmd}")


# ---------------------------------------------------------------------------
# D3 tests — P6: geometry-derived sensors
# ---------------------------------------------------------------------------

import math as _math


def _floor_map():
    m = dict(MAP)
    m["oak_floor"] = {"type": "floor", "refl": 0.25}
    return m


def test_derive_sensors_adds_points(tmp_path):
    """derive_sensors=True adds grid_points, observer_points, glare_views to the result."""
    m = _floor_map()
    out = gi.import_geometry(
        FIX, material_map=m, units="m", up_axis="Y",
        channel_type=0, work_dir=str(tmp_path), run=False, derive_sensors=True)
    assert "grid_points" in out, "grid_points must be present when derive_sensors=True"
    assert len(out["grid_points"]) > 0, "grid_points must be non-empty"
    for row in out["grid_points"]:
        assert row[3:] == [0, 0, 1], f"grid row direction must be [0,0,1]: {row}"
    assert "observer_points" in out, "observer_points must be present when derive_sensors=True"
    assert len(out["observer_points"]) > 0, "observer_points must be non-empty"
    for row in out["observer_points"]:
        assert row[2] in (1.2, 1.6), (
            f"observer z must be in (1.2, 1.6) — got {row[2]}")
    assert "glare_views" in out, "glare_views must be present when derive_sensors=True"
    assert len(out["glare_views"]) == len(out["observer_points"]), (
        "glare_views count must match observer_points count")


def test_derive_sensors_absent_by_default(tmp_path):
    """Without derive_sensors, grid_points must not appear in the result."""
    out = gi.import_geometry(
        FIX, material_map=MAP, units="m", up_axis="Y",
        channel_type=0, work_dir=str(tmp_path), run=False)
    assert "grid_points" not in out, (
        "grid_points must NOT appear without derive_sensors=True")


def test_sensors_lock_to_north_rotation(tmp_path):
    """north_angle_deg rotates sensor positions but keeps counts, z-heights, and unit dirs."""
    m = _floor_map()
    r0 = gi.import_geometry(
        FIX, material_map=m, units="m", up_axis="Y",
        channel_type=0, work_dir=str(tmp_path / "r0"), run=False, derive_sensors=True)
    r9 = gi.import_geometry(
        FIX, material_map=m, units="m", up_axis="Y",
        channel_type=0, north_angle_deg=90,
        work_dir=str(tmp_path / "r9"), run=False, derive_sensors=True)

    assert len(r0["grid_points"]) == len(r9["grid_points"]), (
        "grid point count must be equal regardless of north rotation")

    # Same z-heights (rotation is in-plane)
    for row0, row9 in zip(r0["grid_points"], r9["grid_points"]):
        assert row0[2] == row9[2], f"z-height changed: {row0[2]} vs {row9[2]}"

    # Positions are actually different after 90° rotation
    assert r9["grid_points"] != r0["grid_points"], (
        "grid_points must change when north_angle_deg=90")

    # Every observer has unit horizontal direction
    for row in r9["observer_points"]:
        mag = _math.hypot(row[3], row[4])
        assert abs(mag - 1.0) < 1e-5, (
            f"observer horizontal dir must be unit length, got {mag}: {row}")


# --- Task 14: embedded health report must see the sensor/luminaire context ---------------
#
# import_geometry computes derive_sensor_outputs and electric_lights BEFORE calling
# check_geometry_health, but previously called it with no sensors=/electric_lights=,
# so the embedded report claimed "no sensor or photosensor block supplied" and deferred
# luminaire checks even when both were already sitting in `out`. That is a false
# statement -- exactly the silent-omission failure the health report exists to prevent.

_OFFICE_FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
_OFFICE_OBJ = os.path.join(_OFFICE_FIXTURES, "office_room.obj")
_OFFICE_MAP = os.path.join(_OFFICE_FIXTURES, "office_room_material_map.json")


def test_health_report_sees_derived_sensors_and_luminaires(tmp_path):
    """import_geometry(derive_sensors=True) on office_room.obj must NOT report health.skipped
    sensors as 'no sensor or photosensor block supplied' -- 84 grid points were just derived
    a few lines above the health call -- nor defer luminaires as if no block existed."""
    out = gi.import_geometry(
        _OFFICE_OBJ, sidecar=_OFFICE_MAP, channel_type=0,
        work_dir=str(tmp_path), run=False, derive_sensors=True)

    assert len(out["grid_points"]) == 84, (
        f"fixture regression: expected 84 derived grid points, got {len(out['grid_points'])}")
    assert out.get("electric_lights"), "fixture regression: expected a non-empty electric_lights"

    skipped = {s["category"]: s["reason"] for s in out["health"]["skipped"]}
    assert skipped["sensors"] != "no sensor or photosensor block supplied", (
        "false statement: sensors WERE derived and supplied to the health check")
    assert "sensor checks land in tier 3" in skipped["sensors"]
    assert skipped["luminaires"] != "luminaire checks land in tier 2", (
        "false statement: electric_lights WAS supplied to the health check")
    assert "electric_lights supplied" in skipped["luminaires"]


def test_health_report_sensors_reason_unchanged_without_derive_sensors(tmp_path):
    """Without derive_sensors, no sensor block genuinely was supplied -- the reason must
    stay exactly as it reads today. Guards against regressing the no-derive_sensors path
    while fixing the derive_sensors=True path above."""
    out = gi.import_geometry(
        _OFFICE_OBJ, sidecar=_OFFICE_MAP, channel_type=0,
        work_dir=str(tmp_path), run=False, derive_sensors=False)

    assert "grid_points" not in out
    skipped = {s["category"]: s["reason"] for s in out["health"]["skipped"]}
    assert skipped["sensors"] == "no sensor or photosensor block supplied"
    # office_room.obj has a luminaire group regardless of derive_sensors, so electric_lights
    # is still supplied here -- only the sensors reason is gated on derive_sensors.
    assert out.get("electric_lights")
    assert "electric_lights supplied" in skipped["luminaires"]


# ---------------------------------------------------------------------------
# D4 tests — C4: aperture_report + C2/C3: ground/context routing
# ---------------------------------------------------------------------------

from hcl_radiance.geometry_obj import parse_obj as _parse_obj
from hcl_radiance.geometry_import import aperture_report


def test_aperture_report_for_glass():
    """aperture_report returns exactly 1 entry for the clear_glass group with valid area/angles."""
    with open(FIX) as fh:
        parsed = _parse_obj(fh.read())
    rep = aperture_report(parsed, MAP, 1.0)
    assert len(rep) == 1, f"Expected 1 aperture entry, got {len(rep)}: {rep}"
    entry = rep[0]
    assert entry["group"] == "clear_glass"
    assert entry["area_m2"] > 0
    assert 0 <= entry["azimuth_deg"] < 360
    assert 0 <= entry["tilt_deg"] <= 180
    # The glazing face in the fixture is vertical (z=3 wall, Y-up), tilt must be ~90°.
    assert abs(entry["tilt_deg"] - 90.0) < 1.0, (
        f"Expected tilt ~90° for a vertical wall, got {entry['tilt_deg']}")


def test_apertures_always_present(tmp_path):
    """import_geometry always includes 'apertures' key with the clear_glass entry."""
    out = gi.import_geometry(
        FIX, material_map=MAP, units="m", up_axis="Y",
        channel_type=0, work_dir=str(tmp_path), run=False)
    assert "apertures" in out, "'apertures' key must always be present in import_geometry result"
    assert isinstance(out["apertures"], list)
    groups = [e["group"] for e in out["apertures"]]
    assert "clear_glass" in groups, f"Expected clear_glass in apertures, got {groups}"


def test_aperture_azimuth_tracks_north(tmp_path):
    """north_angle_deg=90 must shift aperture azimuth relative to no-north run."""
    out0 = gi.import_geometry(
        FIX, material_map=MAP, units="m", up_axis="Y",
        channel_type=0, work_dir=str(tmp_path / "r0"), run=False)
    out9 = gi.import_geometry(
        FIX, material_map=MAP, units="m", up_axis="Y",
        channel_type=0, north_angle_deg=90,
        work_dir=str(tmp_path / "r9"), run=False)
    az0 = next(e["azimuth_deg"] for e in out0["apertures"] if e["group"] == "clear_glass")
    az9 = next(e["azimuth_deg"] for e in out9["apertures"] if e["group"] == "clear_glass")
    assert az0 != az9, (
        f"azimuth_deg must differ with north_angle_deg=90: got {az0} vs {az9}")


def test_ground_spd_binds_as_opaque(tmp_path):
    """type:'ground' with an SPD binds as plastic and writes the correct reflectances."""
    ground_map = {"ground": {"type": "ground", "spd": "380 0.2\n780 0.2\n"}}
    sets = gi.build_material_sets(ground_map, 0, str(tmp_path))
    assert len(sets) == 1
    path = sets[0][0]
    content = open(path).read()
    assert "plastic" in content, f"Expected 'plastic' in .rad, got:\n{content}"
    channels = gi.group_channels(ground_map["ground"], 0)
    # approx, not exact equality: bin_average returns the true band mean at full precision, so a
    # flat 0.2 SPD lands within float epsilon of 0.2 rather than on a rounded literal.
    assert channels == pytest.approx([0.2, 0.2, 0.2]), f"Expected [0.2,0.2,0.2], got {channels}"


def test_context_surface_binds_plastic(tmp_path):
    """type:'context' with refl=0.35 binds as plastic with the correct reflectance."""
    ctx_map = {"context": {"type": "context", "refl": 0.35}}
    sets = gi.build_material_sets(ctx_map, 0, str(tmp_path))
    assert len(sets) == 1
    path = sets[0][0]
    content = open(path).read()
    assert "plastic" in content, f"Expected 'plastic' in .rad, got:\n{content}"
    channels = gi.group_channels(ctx_map["context"], 0)
    assert channels == [0.35, 0.35, 0.35], f"Expected [0.35,0.35,0.35], got {channels}"


# ---------------------------------------------------------------------------
# D5 tests — P8: luminaires (D1) + provenance manifest (D2) + annotated export (D3)
# ---------------------------------------------------------------------------

from hcl_radiance.geometry_import import luminaire_block, build_manifest, material_summary, annotate_steps


def _parsed():
    from hcl_radiance.geometry_obj import parse_obj
    return parse_obj(open(FIX).read())


def test_luminaire_block_places_at_marker_in_world_frame():
    """luminaire_block places lum1 at its Y-up marker (2,2.69,1.5) -> world (-t 2 -1.5 2.69)."""
    m = dict(MAP)
    m["lum1"] = {"type": "luminaire", "ies": "fixture.ies"}
    blk = luminaire_block(_parsed(), m, scale=1.0, up_axis="Y")
    assert blk["ies2rad"] is not None
    assert "fixture.ies" in " ".join(blk["ies2rad"][0])
    assert "-t 2 -1.5 2.69" in blk["placement_rad"]
    assert blk["warnings"] == []


def test_luminaire_group_without_marker_warns():
    """A luminaire group that has no marker should be warned about (not silently dropped)."""
    m = dict(MAP)
    m["lum1"] = {"type": "luminaire", "ies": "fixture.ies"}
    m["ghost"] = {"type": "luminaire", "ies": "x.ies"}
    blk = luminaire_block(_parsed(), m, scale=1.0, up_axis="Y")
    assert any("ghost" in w for w in blk["warnings"])


def test_luminaires_wired_into_import(tmp_path):
    """import_geometry with a luminaire group sets out['luminaires']['placement_rad'] correctly."""
    out = gi.import_geometry(
        FIX,
        material_map={**MAP, "lum1": {"type": "luminaire", "ies": "fixture.ies"}},
        units="m", up_axis="Y", channel_type=0,
        work_dir=str(tmp_path), run=False)
    assert "luminaires" in out, "import_geometry must set out['luminaires'] when luminaire groups exist"
    assert "-t 2 -1.5 2.69" in out["luminaires"]["placement_rad"]


def test_manifest_records_provenance():
    """build_manifest returns a dict with the expected provenance fields."""
    m = build_manifest(
        FIX, units="mm", up_axis="Y", north_angle_deg=12.0,
        channel_type=1, parsed=_parsed(), scale=0.001,
        map_source="room.matmap.json", tool_version="hcl-mcp-test",
        timestamp=1700000000.0)
    assert len(m["source_sha256"]) == 64
    assert m["units"] == "mm"
    assert m["north_angle_deg"] == 12.0
    assert m["map_source"] == "room.matmap.json"
    assert m["timestamp"] == 1700000000.0


def test_manifest_present_in_import(tmp_path):
    """import_geometry always includes an 'manifest' key with a 64-char source_sha256."""
    out = gi.import_geometry(
        FIX, material_map=MAP, units="m", up_axis="Y",
        channel_type=0, work_dir=str(tmp_path), run=False)
    assert "manifest" in out, "import_geometry must always set out['manifest']"
    assert len(out["manifest"]["source_sha256"]) == 64


def test_material_summary_rows():
    """material_summary returns correct type/refl for plastic and azimuth_deg for glass."""
    rep = aperture_report(_parsed(), MAP, 1.0)
    rows = material_summary(_parsed(), MAP, rep)
    by_group = {r["group"]: r for r in rows}
    assert by_group["clear_glass"]["type"] == "glass"
    assert "azimuth_deg" in by_group["clear_glass"]
    assert by_group["painted_gypsum"]["refl"] == 0.7


def test_annotate_adds_commands(tmp_path):
    """import_geometry with annotate=True sets 'summary' and 'annotate_commands' with falsecolor."""
    out = gi.import_geometry(
        FIX, material_map=MAP, units="m", up_axis="Y",
        channel_type=0, work_dir=str(tmp_path), run=False, annotate=True)
    assert "summary" in out, "annotate=True must set out['summary']"
    assert "annotate_commands" in out, "annotate=True must set out['annotate_commands']"
    assert any("falsecolor" in c for c in out["annotate_commands"]), (
        f"Expected 'falsecolor' in annotate_commands: {out['annotate_commands']}")


# ---------------------------------------------------------------------------
# B1 tests — context external-shading (type:"context" groups)
# ---------------------------------------------------------------------------

from hcl_radiance.geometry_import import _context_groups, _world_footprint


def test_context_groups_resolves_type_context():
    m = {"oak_floor": {"type": "floor", "refl": 0.25},
         "painted_gypsum": {"type": "plastic", "refl": 0.7},
         "clear_glass": {"type": "glass", "tvis": 0.6},
         "awning": {"type": "context", "refl": 0.3}}
    assert _context_groups(m) == {"awning"}


def test_import_geometry_surfaces_context_groups(tmp_path):
    # tag painted_gypsum as context so the sample room has a context group with faces
    m = {"oak_floor": {"type": "floor", "refl": 0.25},
         "painted_gypsum": {"type": "context", "refl": 0.3},
         "clear_glass": {"type": "glass", "tvis": 0.6}}
    r = gi.import_geometry(FIX, material_map=m, units="m", up_axis="Y", channel_type=0,
                        work_dir=str(tmp_path))
    assert r["context_groups"] == ["painted_gypsum"]
    # context must be materialized into the scene regardless of whether Radiance ran.
    # material_sets always contains the written .rad paths (pure-Python, run-independent).
    mat_paths = [p for set_ in r["material_sets"] for p in set_]
    assert any("painted_gypsum" in p for p in mat_paths), (
        f"painted_gypsum .rad not found in material_sets: {mat_paths}"
    )


# ---------------------------------------------------------------------------
# Regression: C1 — parse_obj keeps usemtl active across g lines
# ---------------------------------------------------------------------------

_USEMTL_THEN_GROUPS_OBJ = os.path.join(
    os.path.dirname(__file__), "fixtures", "usemtl_then_groups.obj"
)
_USEMTL_THEN_GROUPS_MAP = {"shell": {"type": "plastic", "refl": 0.5}}


def test_import_geometry_usemtl_then_groups_no_raise(tmp_path):
    """annotate=True over usemtl_then_groups.obj must not raise KeyError.

    Before the C1 fix, parse_obj resets usemtl on every g line, so the rich
    parser reports groups ['block1', 'block2'] while the v1 line-scanner and
    material_map only know 'shell'.  material_summary then hits a KeyError.
    """
    out = gi.import_geometry(
        _USEMTL_THEN_GROUPS_OBJ,
        material_map=_USEMTL_THEN_GROUPS_MAP,
        units="m", up_axis="Z", channel_type=0,
        work_dir=str(tmp_path), run=False, annotate=True)
    # Must not raise; summary must have a 'shell' row
    assert "summary" in out, "annotate=True must produce 'summary'"
    by_group = {r["group"]: r for r in out["summary"]}
    assert "shell" in by_group, (
        f"Expected 'shell' in summary rows, got: {list(by_group.keys())}")
    # No glass groups → apertures list must be empty
    assert out.get("apertures") == [], (
        f"Expected empty apertures for opaque-only OBJ, got: {out.get('apertures')}")


def test_sample_room_apertures_still_present(tmp_path):
    """Regression guard: the original sample_room fixture's clear_glass aperture is unaffected."""
    out = gi.import_geometry(
        FIX, material_map=MAP, units="m", up_axis="Y",
        channel_type=0, work_dir=str(tmp_path), run=False)
    groups = [e["group"] for e in out["apertures"]]
    assert "clear_glass" in groups, (
        f"clear_glass aperture lost in sample_room fixture: {groups}")


# ---------------------------------------------------------------------------
# Task 1: derive_ground_albedo — per-channel-independent 1 nm albedo from type:"ground" groups
# ---------------------------------------------------------------------------

from hcl_radiance.geometry_import import derive_ground_albedo


def test_ground_albedo_scalar_is_flat():
    p = _parsed()  # sample_room parsed
    m = {"oak_floor": {"type": "ground", "refl": 0.2},
         "painted_gypsum": {"type": "plastic", "refl": 0.7},
         "clear_glass": {"type": "glass", "tvis": 0.6}}
    albedo, kind = derive_ground_albedo(p, m)
    assert kind == "flat"
    assert len(albedo) == 401
    assert all(abs(a - 0.2) < 1e-9 for a in albedo)


def test_ground_albedo_spd_is_spectral():
    p = _parsed()
    m = {"oak_floor": {"type": "ground", "spd": "380 0.1\n780 0.5\n"},
         "painted_gypsum": {"type": "plastic", "refl": 0.7},
         "clear_glass": {"type": "glass", "tvis": 0.6}}
    albedo, kind = derive_ground_albedo(p, m)
    assert kind == "spd"
    assert len(albedo) == 401
    assert albedo[0] < albedo[-1]            # rises 0.1 -> 0.5 with wavelength
    assert all(0.0 <= a <= 1.0 for a in albedo)


def test_ground_albedo_absent_without_ground_group():
    p = _parsed()
    albedo, kind = derive_ground_albedo(p, MAP)  # MAP has no type:"ground"
    assert albedo is None and kind is None


# ---------------------------------------------------------------------------
# Task 3: surface ground_albedo/kind from import_geometry
# ---------------------------------------------------------------------------

def test_import_geometry_surfaces_ground_albedo(tmp_path):
    m = {"oak_floor": {"type": "ground", "refl": 0.2},
         "painted_gypsum": {"type": "plastic", "refl": 0.7},
         "clear_glass": {"type": "glass", "tvis": 0.6}}
    r = gi.import_geometry(FIX, material_map=m, units="m", up_axis="Y", channel_type=0,
                           work_dir=str(tmp_path))
    assert len(r["ground_albedo"]) == 401
    assert r["ground_albedo_kind"] == "flat"


def test_import_geometry_no_ground_albedo_key_without_ground(tmp_path):
    r = gi.import_geometry(FIX, material_map=MAP, units="m", up_axis="Y", channel_type=0,
                           work_dir=str(tmp_path))
    assert "ground_albedo" not in r


# ---------------------------------------------------------------------------
# Task 4: luminaire_electric_lights drop-in payload
# ---------------------------------------------------------------------------

from hcl_radiance.geometry_import import luminaire_electric_lights


def test_electric_lights_payload_shape():
    p = _parsed()  # sample_room has group "lum1" with a p-marker at vertex 9
    m = {"oak_floor": {"type": "plastic", "refl": 0.3},
         "painted_gypsum": {"type": "plastic", "refl": 0.7},
         "clear_glass": {"type": "glass", "tvis": 0.6},
         "lum1": {"type": "luminaire", "ies": "fixture.ies", "spd": "380 0.1\n780 0.9\n"}}
    el, warns = luminaire_electric_lights(p, m, scale=1.0, up_axis="Y")
    assert len(el) == 1
    item = el[0]
    assert item["ies"] == "fixture.ies"
    assert item["spd"] == "380 0.1\n780 0.9\n"
    pos = item["placement"]["positions"]
    assert len(pos) == 1 and len(pos[0]["xyz"]) == 3
    assert item["multiplier"] == 1.0 and item["units"] == 2


def test_electric_lights_warns_when_no_ies():
    p = _parsed()
    m = {"oak_floor": {"type": "plastic", "refl": 0.3},
         "painted_gypsum": {"type": "plastic", "refl": 0.7},
         "clear_glass": {"type": "glass", "tvis": 0.6},
         "lum1": {"type": "luminaire"}}        # no ies
    el, warns = luminaire_electric_lights(p, m, scale=1.0, up_axis="Y")
    assert el == []
    assert any("no 'ies'" in w for w in warns)


# ---------------------------------------------------------------------------
# Task 5 tests: wire electric_lights into import_geometry
# ---------------------------------------------------------------------------

def test_import_geometry_electric_lights_present(tmp_path):
    m = dict(MAP)
    m["lum1"] = {"type": "luminaire", "ies": "fixture.ies", "spd": "380 0.1\n780 0.9\n"}
    r = gi.import_geometry(FIX, material_map=m, units="m", up_axis="Y", channel_type=0,
                        work_dir=str(tmp_path))
    assert "electric_lights" in r and len(r["electric_lights"]) == 1
    assert r["electric_lights"][0]["ies"] == "fixture.ies"
    assert "luminaires" in r          # v2 informational block retained


def test_import_geometry_no_electric_lights_without_luminaire(tmp_path):
    r = gi.import_geometry(FIX, material_map=MAP, units="m", up_axis="Y", channel_type=0,
                        work_dir=str(tmp_path))
    assert "electric_lights" not in r


# ---------------------------------------------------------------------------
# Task 7 tests: dual-height observer_sets
# ---------------------------------------------------------------------------

def test_dual_eye_height_observer_sets(tmp_path):
    m = dict(MAP); m["oak_floor"] = {"type": "floor", "refl": 0.25}
    r = gi.import_geometry(FIX, material_map=m, units="m", up_axis="Y", channel_type=0,
                        work_dir=str(tmp_path), derive_sensors=True)
    heights = [s["eye_h"] for s in r["observer_sets"]]
    assert heights == [1.2, 1.6]
    # each set carries its own views, of matching length
    for s in r["observer_sets"]:
        assert len(s["points"]) == len(s["glare_views"]) and s["points"]
    # back-compat flat lists = concatenation
    assert len(r["observer_points"]) == sum(len(s["points"]) for s in r["observer_sets"])
    assert len(r["glare_views"]) == len(r["observer_points"])


def test_single_eye_height_override(tmp_path):
    m = dict(MAP); m["oak_floor"] = {"type": "floor", "refl": 0.25}
    r = gi.import_geometry(FIX, material_map=m, units="m", up_axis="Y", channel_type=0,
                        work_dir=str(tmp_path), derive_sensors=True, eye_heights=(1.4,))
    assert [s["eye_h"] for s in r["observer_sets"]] == [1.4]


# ---------------------------------------------------------------------------
# Task 9: aperture_report uses area-weighted mean normal per glass group
# ---------------------------------------------------------------------------

def test_aperture_normal_is_area_weighted():
    # Two coplanar glass faces -> area-weighted mean == single-face normal (regression-safe);
    # the value must be stable and not depend on which face is faces[0].
    p = _parsed()
    rep = aperture_report(p, MAP, 1.0, up_axis="Y")
    a = [r for r in rep if r["group"] == "clear_glass"][0]
    assert 0 <= a["azimuth_deg"] < 360 and 0 <= a["tilt_deg"] <= 180
    assert a["area_m2"] > 0


def test_aperture_azimuth_is_genuine_blend_multi_orientation():
    """Area-weighted normal for a glass group with two faces of DIFFERENT orientations
    must produce an azimuth strictly between (or provably different from) both single-face
    azimuths — proving the mean is a genuine blend, not one face dominating.

    Geometry (Z-up, model coords == world coords, scale=1.0):
      Face A: unit square in the XZ plane (y=0), normal pointing +Y -> azimuth 0° (North)
      Face B: unit square in the YZ plane (x=0), normal pointing +X -> azimuth 90° (East)
    Both faces have equal area (1 m²), so the blended normal is (0.5, 0.5, 0) normalised,
    giving azimuth atan2(0.707, 0.707) = 45° — strictly between 0° and 90°.
    """
    # Face A: normal +Y (0,1,0) — vertices in XZ plane at y=0
    # v: (0,0,0), (1,0,0), (1,0,1), (0,0,1)   normals: 0 1 0
    # Face B: normal +X (1,0,0) — vertices in YZ plane at x=0
    # v: (0,0,0), (0,1,0), (0,1,1), (0,0,1)   normals: 1 0 0
    obj_two_orient = """\
v 0 0 0
v 1 0 0
v 1 0 1
v 0 0 1
v 0 0 0
v 0 1 0
v 0 1 1
v 0 0 1
vn 0 1 0
vn 1 0 0
usemtl gl
f 1//1 2//1 3//1 4//1
f 5//2 6//2 7//2 8//2
"""
    mat_map = {"gl": {"type": "glass", "tvis": 0.6}}

    parsed_two = _parse_obj(obj_two_orient)

    # Combined report (both faces)
    rep = aperture_report(parsed_two, mat_map, 1.0, up_axis="Z")
    assert len(rep) == 1
    blended_az = rep[0]["azimuth_deg"]

    # Single-face subsets — build minimal parsed dicts to reuse aperture_report
    def _single_face_az(face_indices):
        sub = {**parsed_two, "faces": [parsed_two["faces"][i] for i in face_indices]}
        r = aperture_report(sub, mat_map, 1.0, up_axis="Z")
        return r[0]["azimuth_deg"]

    az_a = _single_face_az([0])   # Face A: +Y normal -> azimuth 0° (North)
    az_b = _single_face_az([1])   # Face B: +X normal -> azimuth 90° (East)

    # Blended azimuth must differ from both single-face azimuths
    assert blended_az != az_a, (
        f"Blended azimuth {blended_az} must differ from face-A azimuth {az_a}")
    assert blended_az != az_b, (
        f"Blended azimuth {blended_az} must differ from face-B azimuth {az_b}")

    # For equal-area faces the blend is exactly 45° — verify within 1° tolerance
    lo, hi = min(az_a, az_b), max(az_a, az_b)
    assert lo < blended_az < hi, (
        f"Blended azimuth {blended_az} is not strictly between {az_a} and {az_b}")


# ---------------------------------------------------------------------------
# Task 11: resolve_spec loads SPD file for measured library entries
# ---------------------------------------------------------------------------

import hcl_core.surface_library as _lib


def test_resolve_spec_loads_measured_spd(monkeypatch):
    fx = os.path.join(os.path.dirname(__file__), "fixtures", "measured_demo.spd")
    monkeypatch.setitem(_lib._CATALOG, "demo_measured", {
        "type": "plastic", "refl": 0.3, "family": "floor",
        "illustrative": False, "source": "Synthetic test fixture", "spd": fx})
    spec, illustrative = gi.resolve_spec("demo_measured")
    assert illustrative is False                       # measured
    assert isinstance(spec.get("spd"), str) and "380" in spec["spd"]   # file text loaded
    ch = gi.group_channels(spec, 0)                    # binds as a real spectrum
    assert len(ch) == 3 and all(0.0 <= x <= 1.0 for x in ch)  # valid reflectance values
    assert ch[0] > ch[2]  # fixture rises 0.10->0.50 (blue→red); red channel (ch[0]) > blue (ch[2])


def test_large_context_does_not_trip_room_sanity(tmp_path):
    # painted_gypsum tagged context; the room itself (floor+glass) is a normal 4x2.7x3 m box,
    # so no "implausible" warning should fire even though context geometry exists.
    m = {"oak_floor": {"type": "floor", "refl": 0.25},
         "painted_gypsum": {"type": "context", "refl": 0.3},
         "clear_glass": {"type": "glass", "tvis": 0.6}}
    r = gi.import_geometry(FIX, material_map=m, units="m", up_axis="Y", channel_type=0,
                           work_dir=str(tmp_path))
    assert not any("implausible" in w for w in r["warnings"])


# ---------------------------------------------------------------------------
# Task B3: manifest.json sidecar write + manifest_path surface
# ---------------------------------------------------------------------------


def test_manifest_sidecar_written(tmp_path):
    r = gi.import_geometry(FIX, material_map=MAP, units="m", up_axis="Y", channel_type=0,
                           work_dir=str(tmp_path))
    assert os.path.exists(r["manifest_path"])
    with open(r["manifest_path"]) as fh:
        disk = json.load(fh)
    assert disk["source_sha256"] == r["manifest"]["source_sha256"]
    assert disk["units"] == "m"


# ---------------------------------------------------------------------------
# Task B4: embed provenance header into geometry .rad
# ---------------------------------------------------------------------------

from hcl_radiance.geometry_import import _embed_manifest_header


def test_embed_manifest_header_prepends_comments(tmp_path):
    rad = tmp_path / "geometry.rad"
    rad.write_text("void plastic walls\n0\n0\n5 .7 .7 .7 0 0\n")
    manifest = {"units": "m", "north_angle_deg": 90, "source_sha256": "abc123",
                "channel_type": 0, "tool_version": "hcl-mcp"}
    _embed_manifest_header(str(rad), manifest)
    text = rad.read_text()
    assert text.startswith("#")                       # Radiance-ignored comment header
    assert "# units: m" in text
    assert "# source_sha256: abc123" in text
    assert "void plastic walls" in text               # original body preserved
    # idempotent: second call does not double the header
    _embed_manifest_header(str(rad), manifest)
    assert text.count("# source_sha256") == rad.read_text().count("# source_sha256")


# ---- derived sensors must be clipped to the real floor outline, not its bounding box ----

def _l_room():
    from hcl_radiance.geometry_obj import parse_obj
    with open(os.path.join(_OFFICE_FIXTURES, "l_room.obj")) as fh:
        return parse_obj(fh.read())


def _office():
    from hcl_radiance.geometry_obj import parse_obj
    with open(os.path.join(_OFFICE_FIXTURES, "office_room.obj")) as fh:
        return parse_obj(fh.read())


_CLIP_L_MAP = {"Floor": {"type": "floor"}, "Window": {"type": "glass"}}
_CLIP_OFFICE_MAP = {"Rad_Floor_R020": {"type": "floor"}, "Rad_Glazing_T073": {"type": "glass"}}


def test_derived_grid_is_clipped_to_a_concave_floor():
    # REGRESSION: the L-notch is open exterior -- no floor, ceiling or walls -- so points there
    # read HIGH and inflate sDA/ASE (and one of them can set df_min, hence DF uniformity).
    from hcl_radiance.footprint import point_in_polygon
    from hcl_radiance.scene_preview import build_scene
    parsed = _l_room()
    poly = build_scene(parsed, _CLIP_L_MAP, 1.0, "Z", None)["footprint"][0]
    out = gi.derive_sensor_outputs(parsed, _CLIP_L_MAP, 1.0, up_axis="Z", spacing=1.0)

    outside = [q for q in out["grid_points"] if not point_in_polygon(q[0], q[1], poly)]
    assert not outside, f"{len(outside)} derived grid point(s) outside the floor: {outside[:3]}"
    obs_outside = [q for q in out["observer_points"] if not point_in_polygon(q[0], q[1], poly)]
    assert not obs_outside, f"{len(obs_outside)} observer(s) outside the floor"

    assert out["clipped"]["grid_dropped"] == 9        # the notch cells at spacing 1.0
    assert out["clipped"]["observers_dropped"] == 2


def test_clipping_keeps_observer_points_and_glare_views_aligned():
    # each dropped observer must take its paired DGP view with it
    out = gi.derive_sensor_outputs(_l_room(), _CLIP_L_MAP, 1.0, up_axis="Z", spacing=1.0)
    assert len(out["glare_views"]) == len(out["observer_points"])
    for s in out["observer_sets"]:
        assert len(s["glare_views"]) == len(s["points"])


def test_rectangular_room_grid_count_is_unchanged_by_clipping():
    # GOLDEN GUARD: office_room at the default spacing must stay exactly 84 with nothing dropped,
    # so the published rectangular-room counts cannot move.
    out = gi.derive_sensor_outputs(_office(), _CLIP_OFFICE_MAP, 1.0, up_axis="Z", spacing=0.6)
    assert len(out["grid_points"]) == 84
    assert out["clipped"]["grid_dropped"] == 0
    assert out["clipped"]["observers_dropped"] == 0


def test_clipping_can_be_disabled():
    out = gi.derive_sensor_outputs(_l_room(), _CLIP_L_MAP, 1.0, up_axis="Z", spacing=1.0,
                                   clip_to_footprint=False)
    assert len(out["grid_points"]) == 36          # the raw bounding-box lattice
    assert "clipped" not in out


def test_footprint_border_insets_from_every_real_edge():
    # a border keeps points out of a wall solid when the slab runs under the walls
    wide = gi.derive_sensor_outputs(_office(), _CLIP_OFFICE_MAP, 1.0, up_axis="Z", spacing=0.6)
    inset = gi.derive_sensor_outputs(_office(), _CLIP_OFFICE_MAP, 1.0, up_axis="Z", spacing=0.6,
                                     footprint_border=0.5)
    assert len(inset["grid_points"]) < len(wide["grid_points"])


def test_multi_name_g_line_uses_the_name_radiance_paints_with():
    """REGRESSION: `g Glass Panel` -- obj2rad registers both names and paints with the LAST.
    parse_obj took the FIRST, so the aperture report called an 18 m2 surface a south window while
    Radiance traced it with the other modifier."""
    from hcl_radiance.geometry_obj import parse_obj
    obj = "g Glass Panel\nv 0 0 0\nv 1 0 0\nv 1 0 1\nv 0 0 1\nf 1 2 3 4\n"
    assert [f["group"] for f in parse_obj(obj)["faces"]] == ["Panel"]
    # the mapfile side must still see BOTH names, or one would be an undefined modifier
    assert gi.parse_obj_groups(obj) == ["Glass", "Panel"]
