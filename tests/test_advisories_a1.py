"""The A1 advisory: an electric run on a defective build must say so."""
from hcl_mcp.advisories import advise


def test_electric_run_on_defective_build_raises_an_advisory():
    result = {"electric": {"total_wattage": 152.0},
              "engine": {"source_cal": {"a1_honored": False}}}
    codes = [a["code"] for a in advise("run_grid", {}, result)]
    assert "RADIANCE_DROPS_IES_CANDELA_SCALE" in codes


def test_healthy_build_raises_no_a1_advisory():
    result = {"electric": {"total_wattage": 152.0},
              "engine": {"source_cal": {"a1_honored": True}}}
    codes = [a["code"] for a in advise("run_grid", {}, result)]
    assert "RADIANCE_DROPS_IES_CANDELA_SCALE" not in codes


def test_daylight_only_run_raises_no_a1_advisory():
    """Sky paths never use A1, so a daylight-only result must not be flagged.

    A daylight-only run carries no engine stamp at all — provenance is written only where
    luminaires were rendered — and that absence is what keeps this quiet on a bad build.
    """
    result = {"ran": True, "daylight": {"metrics": [{"photopic_lux": 500.0}]}}
    codes = [a["code"] for a in advise("run_grid", {}, result)]
    assert "RADIANCE_DROPS_IES_CANDELA_SCALE" not in codes


def test_glare_run_on_defective_build_raises_an_advisory():
    """The image path reports total_wattage rather than an `electric` block.

    Keying only off `electric` left glare_ugr and run_image silent — the very path where
    the defect manifests as UGR 0 rather than as an obviously low number.
    """
    result = {"ran": True, "total_wattage": 152.0, "glare": {"ugr": 0.0},
              "engine": {"source_cal": {"a1_honored": False}}}
    codes = [a["code"] for a in advise("glare_ugr", {}, result)]
    assert "RADIANCE_DROPS_IES_CANDELA_SCALE" in codes


def test_result_without_luminaires_raises_no_a1_advisory():
    """No engine stamp means no luminaires were rendered; nothing to warn about."""
    result = {"ran": True, "daylight": {"metrics": []}}
    codes = [a["code"] for a in advise("run_grid", {}, result)]
    assert "RADIANCE_DROPS_IES_CANDELA_SCALE" not in codes
