"""DEF-INLINE-MAP: an inline material_map may carry the same metadata a sidecar file does.

`load_sidecar` has always stripped `_`-prefixed comment keys and absorbed the import scalars
(units/up_axis/north_angle_deg/channel_type) before treating what remains as group specs. The
inline `material_map=` argument did not, so a caller who read a sidecar JSON and passed its
parsed contents — the obvious thing to do, and what the validation kit's own TEST-PLAN told
testers to do — hit `resolve_spec` treating every non-group key as a surface-library name:

    KeyError: unknown surface "Pinned material map for office_room.obj. Keys are the OBJ's ..."

an error naming the README's prose as a material. The two paths now share one convention.
"""
import json
import os

import pytest

from hcl_radiance.geometry_import import import_geometry

KIT = os.path.join(os.path.dirname(__file__), "..", "hcl_validation", "inputs", "geometry")
OBJ = os.path.abspath(os.path.join(KIT, "office_room.obj"))
SIDECAR = os.path.abspath(os.path.join(KIT, "office_room_material_map.json"))

pytestmark = pytest.mark.skipif(
    not (os.path.exists(OBJ) and os.path.exists(SIDECAR)),
    reason="validation-kit geometry fixtures not present")


def _raw():
    with open(SIDECAR) as fh:
        return json.load(fh)


def _groups_only(raw):
    return {k: v for k, v in raw.items() if isinstance(v, dict) and not k.startswith("_")}


def test_pasting_a_whole_sidecar_inline_no_longer_raises(tmp_path):
    """The exact call the TEST-PLAN prescribed for W2.3: parsed sidecar contents, inline."""
    out = import_geometry(obj_path=OBJ, material_map=_raw(), work_dir=str(tmp_path),
                          run=False, derive_sensors=True, channel_type=1)
    assert out["material_sets"] and len(out["material_sets"][0]) == 7


def test_inline_metadata_matches_the_sidecar_path_exactly(tmp_path):
    """Both routes must produce the same scene, since they describe the same file."""
    a = import_geometry(obj_path=OBJ, material_map=_raw(), work_dir=str(tmp_path / "a"),
                        run=False, derive_sensors=True, channel_type=1)
    b = import_geometry(obj_path=OBJ, sidecar=SIDECAR, work_dir=str(tmp_path / "b"),
                        run=False, derive_sensors=True, channel_type=1)
    assert a["grid_points"] == b["grid_points"]
    assert a["observer_points"] == b["observer_points"]
    assert len(a["material_sets"][0]) == len(b["material_sets"][0])


def test_scalars_are_absorbed_from_the_inline_map(tmp_path):
    """units/up_axis/north_angle_deg carried in the map apply when not passed explicitly.

    The fixture is Z-up in metres; without absorbing `up_axis` the derived heights come out
    against the wrong axis, so the working plane is the observable proof it was read.
    """
    out = import_geometry(obj_path=OBJ, material_map=_raw(), work_dir=str(tmp_path),
                          run=False, derive_sensors=True, channel_type=1)
    assert {round(p[2], 4) for p in out["grid_points"]} == {0.8}
    assert out["manifest"]["units"] == "m"
    assert out["manifest"]["up_axis"] == "Z"


def test_an_explicit_argument_still_beats_the_maps_metadata(tmp_path):
    """Absorption must never override what the caller stated outright."""
    out = import_geometry(obj_path=OBJ, material_map=_raw(), work_dir=str(tmp_path),
                          run=False, derive_sensors=True, channel_type=1,
                          north_angle_deg=90)
    assert out["manifest"]["north_angle_deg"] == 90


def test_a_groups_only_map_is_unaffected(tmp_path):
    """The pre-existing, documented shape must stay byte-identical."""
    a = import_geometry(obj_path=OBJ, material_map=_groups_only(_raw()), units="m",
                        up_axis="Z", north_angle_deg=0, work_dir=str(tmp_path / "a"),
                        run=False, derive_sensors=True, channel_type=1)
    b = import_geometry(obj_path=OBJ, material_map=_raw(), work_dir=str(tmp_path / "b"),
                        run=False, derive_sensors=True, channel_type=1)
    assert a["grid_points"] == b["grid_points"]
    assert len(a["material_sets"][0]) == len(b["material_sets"][0])


def test_an_unknown_group_still_fails_loudly(tmp_path):
    """Stripping metadata must not become a licence to swallow real mistakes.

    A key that is neither underscore-prefixed nor a recognised scalar is still a group spec,
    so a typo'd material name must raise rather than be quietly dropped.
    """
    bad = dict(_raw())
    bad["Rad_Wall_R050"] = "not_a_library_surface"
    with pytest.raises(KeyError, match="unknown surface"):
        import_geometry(obj_path=OBJ, material_map=bad, work_dir=str(tmp_path),
                        run=False, channel_type=1)
