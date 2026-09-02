"""Luminaire groups: their faces must not reach obj2rad, and their orientation must be settable.

Two defects this pins, both found while re-authoring the paper's office model:

D-5 — `material_sets` deliberately excludes type:"luminaire" groups ("they have no geometry
faces"), but the obj2rad mapfile was built from ALL groups. A luminaire group that *does* carry
mesh faces therefore emitted polygons whose modifier nothing ever defined, and oconv died with
`undefined modifier`. Every campaign worked around it by hand-writing a placeholder material —
which lands 0.25 mm from the ies2rad emitter polygon, i.e. a coincident-surface pair on exactly
the surface being measured. Dropping the faces is both correct and cheaper: the luminous opening
comes from ies2rad, not from a dummy diffuse face.

Orientation — `place_luminaires` accepts a per-instance `rot`, but nothing populated it, so every
luminaire was placed at -rz 0. ies2rad lays a luminaire's long axis along +Y; a fitting modelled
along +X was silently rotated 90 degrees against its own housing. Harmless for a square panel,
wrong for anything linear, and it fails quietly — the run completes and the numbers are wrong.
"""
import os

from hcl_radiance.geometry_import import (import_geometry, luminaire_block,
                                          luminaire_electric_lights)
from hcl_radiance.geometry_obj import parse_obj

# One luminaire group that carries a real face (as every Blender export does), plus one wall.
OBJ = """\
o Wall
v 0 0 0
v 1 0 0
v 1 0 1
v 0 0 1
usemtl Rad_Wall
f 1 2 3 4
o Lum
v 0.2 0.2 2.0
v 0.8 0.2 2.0
v 0.8 0.4 2.0
v 0.2 0.4 2.0
usemtl Rad_Lum
f 5 6 7 8
"""

MAP = {
    "Rad_Wall": {"type": "plastic", "refl": 0.5},
    "Rad_Lum": {"type": "luminaire", "ies": "/tmp/x.ies", "spd": "/tmp/x.spd"},
}


def test_mapfile_omits_luminaire_groups_so_obj2rad_drops_their_faces(tmp_path):
    # D-5, pinned on the mapfile import_geometry actually writes: a mapfile naming the
    # luminaire group makes obj2rad emit faces with a modifier material_sets never defines,
    # and oconv dies. Only groups that get a material definition may appear.
    obj = tmp_path / "m.obj"
    obj.write_text(OBJ)
    import_geometry(str(obj), material_map=MAP, units="m", up_axis="Z",
                    run=False, work_dir=str(tmp_path))

    mapfile = (tmp_path / "mapfile_a.txt").read_text()
    assert 'Rad_Wall_a (Material "Rad_Wall")' in mapfile
    assert "Rad_Lum" not in mapfile, f"luminaire group must not be mapped for obj2rad:\n{mapfile}"


def test_luminaire_rot_defaults_to_none_and_is_omitted():
    parsed = parse_obj(OBJ)
    el = luminaire_electric_lights(parsed, MAP, scale=1.0, up_axis="Z")[0]
    pos = el[0]["placement"]["positions"][0]
    assert "rot" not in pos, "no rotation requested -> payload stays as before"


def test_luminaire_rot_is_threaded_from_the_material_map():
    parsed = parse_obj(OBJ)
    spec = dict(MAP["Rad_Lum"], rot=[0, 90, 0])
    mp = dict(MAP, Rad_Lum=spec)

    el = luminaire_electric_lights(parsed, mp, scale=1.0, up_axis="Z")[0]
    assert el[0]["placement"]["positions"][0]["rot"] == [0, 90, 0]

    # and it must survive into the emitted xform: rot[1]=90 remaps to -rz -90,
    # which turns ies2rad's +Y-long luminaire onto the +X axis.
    block = luminaire_block(parsed, mp, scale=1.0, up_axis="Z")
    assert "-rz -90" in block["placement_rad"], block["placement_rad"]
