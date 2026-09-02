"""Tests for hcl_core.surface_library — Part 1 of D2."""

import os
import pytest

import hcl_core.surface_library as lib
from hcl_core.surface_library import list_surfaces, surface_lookup, surface_meta


def test_known_surface_returns_spec_with_valid_refl():
    spec = surface_lookup("painted_gypsum")
    assert "refl" in spec
    assert 0 < spec["refl"] <= 1


def test_glass_entry_has_tvis():
    spec = surface_lookup("clear_float_6mm")
    assert "tvis" in spec
    assert 0 < spec["tvis"] <= 1


def test_surface_meta_exposes_bool_illustrative():
    meta = surface_meta("white_ceiling")
    assert "illustrative" in meta
    assert isinstance(meta["illustrative"], bool)
    assert meta["illustrative"] is True


def test_unknown_raises_key_error():
    with pytest.raises(KeyError):
        surface_lookup("nonexistent_material_xyz")


def test_unknown_meta_raises_key_error():
    with pytest.raises(KeyError):
        surface_meta("nonexistent_material_xyz")


def test_oak_floor_in_list_surfaces():
    assert "oak_floor" in list_surfaces()


def test_surface_lookup_returns_copy():
    """Mutating the returned dict must not affect the catalog."""
    spec1 = surface_lookup("painted_gypsum")
    spec1["refl"] = 0.99
    spec2 = surface_lookup("painted_gypsum")
    assert spec2["refl"] == 0.70


def test_all_expected_names_present():
    names = list_surfaces()
    expected = [
        "painted_gypsum", "white_ceiling", "oak_floor", "concrete",
        "clear_float_6mm", "low_e_double", "grass_ground", "asphalt_ground",
    ]
    for name in expected:
        assert name in names, f"{name!r} missing from list_surfaces()"


def test_surface_meta_has_family_and_notes():
    meta = surface_meta("oak_floor")
    assert "family" in meta and meta["family"] == "floor"
    assert "notes" in meta
    assert "illustrative" in meta["notes"].lower() or "starting" in meta["notes"].lower()


def test_all_entries_have_illustrative_true():
    for name in list_surfaces():
        meta = surface_meta(name)
        assert meta["illustrative"] is True, f"{name!r} not flagged illustrative"


def test_shipped_catalog_is_all_illustrative():
    for name in lib.list_surfaces():
        assert lib.surface_meta(name)["measured"] is False


def test_measured_requires_source_and_readable_spd(tmp_path, monkeypatch):
    spd = tmp_path / "demo.spd"
    spd.write_text("380 0.2\n780 0.2\n")
    # inject a test-only measured entry (never shipped)
    monkeypatch.setitem(lib._CATALOG, "demo_measured", {
        "type": "plastic", "refl": 0.2, "family": "floor",
        "illustrative": False, "source": "Test fixture (synthetic)", "spd": str(spd)})
    meta = lib.surface_meta("demo_measured")
    assert meta["measured"] is True and meta["illustrative"] is False
    assert "Test fixture" in meta["source"]


def test_measured_false_without_source(tmp_path, monkeypatch):
    spd = tmp_path / "demo.spd"; spd.write_text("380 0.2\n780 0.2\n")
    monkeypatch.setitem(lib._CATALOG, "no_source", {
        "type": "plastic", "refl": 0.2, "family": "floor",
        "illustrative": True, "spd": str(spd)})        # spd but no source
    assert lib.surface_meta("no_source")["measured"] is False
