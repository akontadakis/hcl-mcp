from hcl_mcp.prompts import place_sensors, visualize_scene
from hcl_mcp.resources import reference_geometry


def test_place_sensors_mentions_photosensors_and_preview():
    txt = place_sensors("open-plan office")
    assert "photosensors" in txt
    assert "preview_scene" in txt


def test_visualize_scene_prompt_exists():
    txt = visualize_scene("office")
    assert "preview_scene" in txt


def test_reference_geometry_documents_new_tools():
    txt = reference_geometry()
    assert "photosensors" in txt
    assert "preview_scene" in txt
