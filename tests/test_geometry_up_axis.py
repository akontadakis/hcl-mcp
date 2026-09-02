"""Regression tests for the up_axis case-sensitivity seam.

build_xform compared up_axis case-INsensitively while _to_world and
object_centroid compared it case-sensitively. up_axis="y" therefore rotated the
traced geometry to Z-up while leaving every sensor/luminaire/aperture in the
unrotated frame -- a silent 90-degree error returning plausible illuminances for
a room lying on its side.

Also covers Task 2 (commit 78d2cf8): each of the four MCP entry points
(import_geometry, workplane_grid, observer_points, photosensors) now calls
_normalize_up_axis on up_axis itself, AFTER the sidecar merge, so a bad value --
whether passed directly or supplied only via a sidecar JSON -- is rejected at
the server boundary instead of reaching the transform chain silently.
"""
import asyncio
import json
import os

import pytest

import hcl_mcp.server as server
import hcl_radiance.geometry_import as gi
from hcl_radiance.geometry_obj import object_centroid

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
OFFICE_OBJ = os.path.join(FIXTURES, "office_room.obj")
OFFICE_SIDE = os.path.join(FIXTURES, "office_room_material_map.json")


def test_to_world_and_xform_agree_for_lowercase_y():
    """The seam: both paths must treat 'y' exactly as 'Y'."""
    p = (1.0, 2.0, 3.0)
    assert gi._to_world(p, "y") == gi._to_world(p, "Y")
    assert gi.build_xform("r.rad", up_axis="y") == gi.build_xform("r.rad", up_axis="Y")


def test_to_world_and_xform_agree_for_lowercase_z():
    p = (1.0, 2.0, 3.0)
    assert gi._to_world(p, "z") == gi._to_world(p, "Z")
    assert gi.build_xform("r.rad", up_axis="z") == gi.build_xform("r.rad", up_axis="Z")


def test_y_up_actually_remaps():
    """Guard the fix does not flatten Y-up into a no-op."""
    assert gi._to_world((1.0, 2.0, 3.0), "Y") == (1.0, -3.0, 2.0)
    assert gi._to_world((1.0, 2.0, 3.0), "Z") == (1.0, 2.0, 3.0)


def test_normalize_up_axis_accepts_case_and_whitespace():
    assert gi._normalize_up_axis("y") == "Y"
    assert gi._normalize_up_axis(" Z ") == "Z"
    assert gi._normalize_up_axis(None) == "Z"


def test_normalize_up_axis_rejects_garbage():
    with pytest.raises(ValueError, match="up_axis"):
        gi._normalize_up_axis("X")


def test_object_centroid_honours_lowercase_y():
    parsed = {
        "vertices": [(0.0, 2.0, 0.0), (2.0, 2.0, 0.0), (2.0, 2.0, 2.0)],
        "faces": [{"object": "g", "group": "g", "verts": [1, 2, 3]}],
        "groups": ["g"],
    }
    lower = object_centroid(parsed, "g", 1.0, "y")
    upper = object_centroid(parsed, "g", 1.0, "Y")
    assert lower == upper
    assert lower != (0.0, 0.0, 0.0)


def test_server_import_geometry_rejects_bad_up_axis(tmp_path, monkeypatch):
    # _import_geometry (hcl_radiance.geometry_import.import_geometry) redundantly
    # re-validates up_axis itself once it reaches build_xform/_to_world, so a bare
    # pytest.raises(ValueError, match="up_axis") alone would pass even with the
    # server.py boundary check removed. Spy on that module's parse_obj (called
    # partway through _import_geometry, well after the boundary check's location)
    # to prove the boundary rejects the axis before the deeper call is reached.
    import hcl_radiance.geometry_import as geometry_import
    calls = []
    real = geometry_import.parse_obj

    def spy(text):
        calls.append(True)
        return real(text)

    monkeypatch.setattr(geometry_import, "parse_obj", spy)

    obj = tmp_path / "r.obj"
    obj.write_text("v 0 0 0\nv 1 0 0\nv 1 1 0\ng walls\nf 1 2 3\n")
    with pytest.raises(ValueError, match="up_axis"):
        asyncio.run(server.import_geometry(
            str(obj), material_map={"walls": {"refl": 0.5}},
            units="m", up_axis="sideways", work_dir=str(tmp_path), run=False))
    assert calls == [], "boundary validation should reject up_axis before _import_geometry parses the OBJ"


def test_server_import_geometry_accepts_lowercase_up_axis(tmp_path):
    obj = tmp_path / "r.obj"
    obj.write_text("v 0 0 0\nv 1 0 0\nv 1 1 0\ng walls\nf 1 2 3\n")
    res = asyncio.run(server.import_geometry(
        str(obj), material_map={"walls": {"refl": 0.5}},
        units="m", up_axis="y", work_dir=str(tmp_path), run=False))
    assert res["groups"] == ["walls"]


def _office_material_map():
    """The flat office_room_material_map.json fixture, minus its metadata keys,
    i.e. exactly the group-spec dict the *_map: dict argument expects."""
    with open(OFFICE_SIDE) as fh:
        raw = json.load(fh)
    meta = {"_README", "units", "up_axis", "north_angle_deg"}
    return {k: v for k, v in raw.items() if k not in meta}


# --- direct-argument up_axis validation, all four MCP tools -----------------
#
# Each case supplies a real office_room material_map (glazing + floor included)
# so the ONLY thing that can go wrong is the axis -- distinguishing this from
# the "needs a material_map"/"needs a glazing group" ValueErrors those tools
# also raise.

def _parse_obj_spy(monkeypatch):
    """Wrap hcl_radiance.geometry_obj.parse_obj so tests can prove whether it ran.

    All three sidecar-capable tools call parse_obj(fh.read()) AFTER the boundary
    up_axis normalisation but BEFORE any of the deep per-vertex _to_world calls
    that redundantly re-validate up_axis inside sensor_methodology/footprint. A
    bad axis is therefore always rejected with a ValueError naming "up_axis" --
    that alone can't tell the boundary check apart from the deeper one. Whether
    parse_obj ran before the raise can: with the boundary check in place the
    ValueError fires immediately and parse_obj never executes; with the boundary
    check removed, the tool sails past the merge straight into parse_obj and only
    fails later, deep in the transform chain -- by which point parse_obj already
    ran. calls[0] being False is the signal the boundary validation is gone.
    """
    import hcl_radiance.geometry_obj as geometry_obj
    calls = []
    real = geometry_obj.parse_obj

    def spy(text):
        calls.append(True)
        return real(text)

    monkeypatch.setattr(geometry_obj, "parse_obj", spy)
    return calls


def test_server_workplane_grid_rejects_bad_up_axis_direct(tmp_path, monkeypatch):
    calls = _parse_obj_spy(monkeypatch)
    with pytest.raises(ValueError, match="up_axis"):
        asyncio.run(server.workplane_grid(
            obj_path=OFFICE_OBJ, material_map=_office_material_map(),
            units="m", up_axis="sideways", work_dir=str(tmp_path)))
    assert calls == [], "boundary validation should reject up_axis before parse_obj runs"


def test_server_observer_points_rejects_bad_up_axis_direct(tmp_path, monkeypatch):
    calls = _parse_obj_spy(monkeypatch)
    with pytest.raises(ValueError, match="up_axis"):
        asyncio.run(server.observer_points(
            obj_path=OFFICE_OBJ, material_map=_office_material_map(),
            units="m", up_axis="sideways", work_dir=str(tmp_path)))
    assert calls == [], "boundary validation should reject up_axis before parse_obj runs"


def test_server_photosensors_rejects_bad_up_axis_direct(tmp_path, monkeypatch):
    calls = _parse_obj_spy(monkeypatch)
    with pytest.raises(ValueError, match="up_axis"):
        asyncio.run(server.photosensors(
            obj_path=OFFICE_OBJ, material_map=_office_material_map(),
            units="m", up_axis="sideways", work_dir=str(tmp_path)))
    assert calls == [], "boundary validation should reject up_axis before parse_obj runs"


# --- sidecar-supplied up_axis validation -------------------------------------
#
# Proves normalisation runs AFTER the sidecar merge: a bad up_axis that arrives
# only through the sidecar JSON (never as a direct kwarg) must still be rejected
# at the server boundary -- before parse_obj runs -- not silently absorbed into
# the transform chain and only caught several calls later.

def _bad_axis_sidecar(tmp_path, name):
    with open(OFFICE_SIDE) as fh:
        sc = json.load(fh)
    sc["up_axis"] = "sideways"
    path = tmp_path / name
    path.write_text(json.dumps(sc))
    return str(path)


def test_server_workplane_grid_rejects_bad_up_axis_via_sidecar(tmp_path, monkeypatch):
    side = _bad_axis_sidecar(tmp_path, "bad_axis_workplane.json")
    calls = _parse_obj_spy(monkeypatch)
    with pytest.raises(ValueError, match="up_axis"):
        asyncio.run(server.workplane_grid(
            obj_path=OFFICE_OBJ, sidecar=side, work_dir=str(tmp_path)))
    assert calls == [], "sidecar-supplied up_axis must be rejected before parse_obj runs"


def test_server_observer_points_rejects_bad_up_axis_via_sidecar(tmp_path, monkeypatch):
    side = _bad_axis_sidecar(tmp_path, "bad_axis_observers.json")
    calls = _parse_obj_spy(monkeypatch)
    with pytest.raises(ValueError, match="up_axis"):
        asyncio.run(server.observer_points(
            obj_path=OFFICE_OBJ, sidecar=side, work_dir=str(tmp_path)))
    assert calls == [], "sidecar-supplied up_axis must be rejected before parse_obj runs"


def test_server_photosensors_rejects_bad_up_axis_via_sidecar(tmp_path, monkeypatch):
    side = _bad_axis_sidecar(tmp_path, "bad_axis_photosensors.json")
    calls = _parse_obj_spy(monkeypatch)
    with pytest.raises(ValueError, match="up_axis"):
        asyncio.run(server.photosensors(
            obj_path=OFFICE_OBJ, sidecar=side, work_dir=str(tmp_path)))
    assert calls == [], "sidecar-supplied up_axis must be rejected before parse_obj runs"
