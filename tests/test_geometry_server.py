"""Minimal tests that the import_geometry MCP wrapper is wired up correctly."""
import hcl_mcp.server as server


def test_import_geometry_registered_on_server():
    assert hasattr(server, "import_geometry"), (
        "import_geometry must be a top-level name in server.py "
        "(registered in the FastMCP tool tuple)"
    )


def test_import_geometry_signature_has_v2_kwargs():
    """All v2 keyword arguments must be present in the server wrapper's signature."""
    import inspect
    sig = inspect.signature(server.import_geometry)
    params = set(sig.parameters)
    expected = {
        "obj_path", "material_map", "units", "up_axis",
        "channel_type", "north_angle_deg", "dry_run", "sidecar",
        "derive_sensors", "annotate", "run", "work_dir", "ctx",
    }
    missing = expected - params
    assert not missing, f"import_geometry missing params: {missing}"


def test_import_geometry_material_map_is_optional():
    """material_map must default to None (required for dry_run without a map)."""
    import inspect
    sig = inspect.signature(server.import_geometry)
    p = sig.parameters["material_map"]
    assert p.default is None, (
        f"material_map must default to None, got {p.default!r}"
    )


def test_spectral_sky_from_epw_accepts_spectral_albedo():
    import inspect
    sig = inspect.signature(server.spectral_sky_from_epw)
    assert "spectral_albedo" in sig.parameters
    assert sig.parameters["spectral_albedo"].default is None


def test_spectral_albedo_wrong_length_rejected():
    import pytest
    # surface_tilt_deg present so the ground branch runs; bad albedo must raise before any EPW work
    with pytest.raises(ValueError):
        server.spectral_sky_from_epw("nonexistent.epw", 6, 21, 12,
                                     surface_tilt_deg=90, spectral_albedo=[0.2] * 10)


def test_reference_geometry_lists_all_types():
    from hcl_mcp.resources import reference_geometry
    text = reference_geometry()
    for t in ("plastic", "glass", "ground", "context", "luminaire", "floor"):
        assert t in text, f"type {t!r} missing from hcl://reference/geometry"
