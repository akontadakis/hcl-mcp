"""Review 2026-11-26, hardening: S4, S5, S12. Names and paths that arrive from a model file or
from the caller must not choose where the server writes or deletes."""
import json
import os

import pytest

from hcl_core.materials import require_safe_name, write_material
from hcl_radiance import sensor_sets
from hcl_radiance.geometry_import import import_geometry, manifest_header

_BOX = ("v 0 0 0\nv 4 0 0\nv 4 4 0\nv 0 4 0\nv 0 0 3\nv 4 0 3\nv 4 4 3\nv 0 4 3\n"
        "usemtl floor\nf 1 2 3 4\nusemtl {name}\nf 5 8 7 6\n")


# ---- S4 ----

@pytest.mark.parametrize("name", ["../../escape", "a/b", "a\\b", "..", 'say"hi', "a;b", "a&b",
                                  "", "tab\tname", "two words", "!touch", "#note"])
def test_a_name_that_could_leave_the_folder_or_break_a_radiance_file_is_refused(name):
    with pytest.raises(ValueError, match="name"):
        require_safe_name(name, "material")


@pytest.mark.parametrize("name", ["walls", "glass.1", "wg_S_180", "Τοίχος",
                                  # measured with obj2rad 2026-11-26: these convert correctly
                                  "Walls(Ext)", "a#b", "a!b"])
def test_ordinary_names_pass(name):
    assert require_safe_name(name, "material") == name


def test_write_material_does_not_write_outside_its_folder(tmp_path):
    work = tmp_path / "a" / "work"
    with pytest.raises(ValueError, match="material name"):
        write_material([0.5, 0.5, 0.5], material_type=1, channel_type=0, name="../../escape",
                       work_dir=str(work))
    assert not (tmp_path / "escape.rad").exists()


def test_an_obj_material_name_cannot_write_outside_the_work_folder(tmp_path):
    work = tmp_path / "a" / "work"
    obj = tmp_path / "room.obj"
    obj.write_text(_BOX.format(name="../../escape"))
    with pytest.raises(ValueError, match=r"\.\./\.\./escape"):
        import_geometry(str(obj), units="m", up_axis="Z", channel_type=0, work_dir=str(work),
                        run=False, material_map={"floor": {"type": "floor", "refl": 0.2},
                                                 "../../escape": {"type": "plastic", "refl": 0.5}})
    assert not (tmp_path / "escape.rad").exists()
    assert not list(tmp_path.glob("escape*"))


def test_a_dry_run_still_lists_an_odd_name_so_the_user_can_see_it(tmp_path):
    obj = tmp_path / "room.obj"
    obj.write_text(_BOX.format(name="../../escape"))
    out = import_geometry(str(obj), work_dir=str(tmp_path / "w"), dry_run=True)
    assert "../../escape" in json.dumps(out)


def test_a_sensor_set_may_still_be_called_by_two_words(tmp_path):
    """It is only a file name, and such sets exist. A material name is also a Radiance
    identifier and cannot hold a blank; a sensor set name is not."""
    made = sensor_sets.create_sensor_set(str(tmp_path / "w"), "desk 1",
                                         points=[[0, 0, 0, 0, 0, 1]])
    assert os.path.basename(made["path"]) == "desk 1.pts"
    with pytest.raises(ValueError, match="sensor set name"):
        sensor_sets.create_sensor_set(str(tmp_path / "w"), "desk\n1", points=[[0, 0, 0, 0, 0, 1]])


def test_a_sensor_set_name_cannot_leave_the_sensor_folder(tmp_path):
    with pytest.raises(ValueError, match="sensor set name"):
        sensor_sets.create_sensor_set(str(tmp_path / "w"), "../../escape",
                                      points=[[0, 0, 0, 0, 0, 1]])
    assert not list(tmp_path.glob("escape*"))


# ---- S5 ----

def test_a_line_break_in_a_manifest_value_cannot_start_a_new_line_in_the_rad_file():
    """Every header line starts with `#`. A value with a line break in it ended the comment and
    put the rest on a line of its own, where `!command` is something Radiance runs."""
    header = manifest_header({"map_source": "side.json\n!touch /tmp/owned", "units": "m"})
    for line in header.splitlines():
        assert line.startswith("#"), line


# ---- S12 ----

def test_deleting_a_sensor_set_never_removes_a_file_outside_the_sensor_folder(tmp_path):
    """The path comes from sensors.json, a file anyone with the work folder can edit."""
    work = tmp_path / "w"
    sensor_sets.create_sensor_set(str(work), "desk", points=[[0, 0, 0, 0, 0, 1]])
    precious = tmp_path / "precious.txt"
    precious.write_text("keep me")
    registry = next(p for p in work.rglob("*.json"))
    reg = json.loads(registry.read_text())
    reg["desk"]["path"] = str(precious)
    registry.write_text(json.dumps(reg))
    out = sensor_sets.delete_sensor_set(str(work), "desk")
    assert precious.read_text() == "keep me"
    assert out["deleted"] == "desk" and out["file_left"] == str(precious)
    assert "desk" not in [s["name"] for s in sensor_sets.list_sensor_sets(str(work))]


def test_deleting_a_sensor_set_still_removes_its_own_file(tmp_path):
    work = tmp_path / "w"
    made = sensor_sets.create_sensor_set(str(work), "desk", points=[[0, 0, 0, 0, 0, 1]])
    out = sensor_sets.delete_sensor_set(str(work), "desk")
    assert not os.path.exists(made["path"]) and "file_left" not in out


# ---- second review 2026-11-26 ----

@pytest.mark.parametrize("name", ["-rf", "a$b", "a`b`", "a<b", "a>b", "a|b", "a*b", "a?b"])
def test_shell_and_option_characters_are_refused_too(name):
    with pytest.raises(ValueError, match="name"):
        require_safe_name(name, "material")


@pytest.mark.parametrize("name", ["CON", "nul", "COM1", "lpt9", "aux.rad", "wall:1", "wall.",
                                  "Basic_Wall:Generic-200mm"])
def test_names_windows_cannot_store_are_refused_on_windows(name):
    """`wall:1.rad` on NTFS is a hidden stream of a file called `wall`; CON and NUL are devices."""
    with pytest.raises(ValueError, match="Windows"):
        require_safe_name(name, "material", windows=True)


def test_a_colon_stays_legal_where_the_file_system_allows_it():
    assert require_safe_name("Basic_Wall:Generic-200mm", "material", windows=False)


def test_a_sky_name_cannot_write_outside_its_folder(tmp_path):
    from hcl_radiance import sky
    work = tmp_path / "a" / "work"
    with pytest.raises(ValueError, match="sky name"):
        sky.colored_sky([1, 1, 1], [1, 1, 1], 0, name="../../escape", work_dir=str(work),
                        run=False, month=6, day=21, hour=12.0, irrad_mode="W", lat=38.0,
                        lon=-23.7, utc=2, direct=500, diffuse=100)
    assert not list(tmp_path.glob("escape*"))


def test_a_luminaire_name_cannot_write_outside_its_folder(tmp_path):
    import asyncio
    from hcl_mcp.server import colored_luminaire
    rad = "void light lamp\n0\n0\n3 1 1 1\n"
    with pytest.raises(ValueError, match="luminaire name"):
        asyncio.run(colored_luminaire(rad_path=rad, channels9=[1.0] * 9, count=1,
                                      name="../../escape", work_dir=str(tmp_path / "a" / "w")))
    assert not list(tmp_path.glob("escape*"))


# ---- command text for the platform it will be pasted into ----

def test_command_text_is_quoted_for_the_shell_of_the_platform():
    from hcl_platform import shell_join, shell_quote
    argv = ["gensdaymtx", "-m", "1", "C:/My Data/site.epw"]
    assert shell_join(argv, windows=False) == "gensdaymtx -m 1 'C:/My Data/site.epw'"
    assert shell_join(argv, windows=True) == 'gensdaymtx -m 1 "C:/My Data/site.epw"'
    assert shell_quote("C:/My Data/out.smx", windows=True) == '"C:/My Data/out.smx"'
    assert shell_quote("plain.smx", windows=True) == "plain.smx"
