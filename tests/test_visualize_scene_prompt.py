from hcl_mcp.prompts import visualize_scene


def test_prompt_reports_png_image_paths():
    t = visualize_scene("a small office")
    assert "image_paths" in t
    assert "svg_paths" not in t
