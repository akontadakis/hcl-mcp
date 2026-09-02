import pytest
from hcl_core.presets import list_presets, get_preset, preset_meta, ILLUSTRATIVE_LEDS

def test_list_presets_includes_standards():
    names = list_presets()
    assert "D65" in names and "A" in names and "FL11" in names

def test_list_presets_includes_illustrative_leds():
    names = list_presets()
    for n in ("LED_3000K", "LED_4000K", "LED_5000K", "LED_BLUEPUMP", "LED_VIOLETPUMP"):
        assert n in names

def test_get_preset_returns_401_pairs_on_1nm_grid():
    spd = get_preset("D65")
    assert len(spd) == 401
    assert spd[0][0] == 380 and spd[-1][0] == 780
    assert all(isinstance(v, float) for _, v in spd)

def test_get_preset_accepts_f_alias():
    assert get_preset("F1") == get_preset("FL1")

def test_unknown_preset_raises():
    with pytest.raises(KeyError):
        get_preset("nope")

# --- Illustrative LED presets (spec 5.7) ---

@pytest.mark.parametrize("name", ["LED_3000K", "LED_4000K", "LED_5000K", "LED_BLUEPUMP", "LED_VIOLETPUMP"])
def test_led_preset_is_401_points_normalized(name):
    spd = get_preset(name)
    assert len(spd) == 401
    assert spd[0][0] == 380 and spd[-1][0] == 780
    vals = [v for _, v in spd]
    assert all(v >= 0.0 for v in vals)
    assert abs(max(vals) - 1.0) < 1e-6           # normalized so peak == 1.0

@pytest.mark.parametrize("name", ["LED_3000K", "LED_4000K", "LED_5000K", "LED_BLUEPUMP", "LED_VIOLETPUMP"])
def test_led_preset_flagged_illustrative(name):
    meta = preset_meta(name)
    assert meta["illustrative"] is True
    assert "not measured" in meta["notes"].lower()
    assert name in ILLUSTRATIVE_LEDS

def test_standard_presets_not_flagged_illustrative():
    assert preset_meta("D65")["illustrative"] is False

@pytest.mark.parametrize("name,target_K", [("LED_3000K", 3000), ("LED_4000K", 4000), ("LED_5000K", 5000)])
def test_led_preset_cct_lands_near_named_temperature(name, target_K):
    # Loose tolerance: these are an illustrative model, not measured data.
    import colour
    spd = get_preset(name)
    sd = colour.SpectralDistribution({float(w): v for w, v in spd})
    xyz = colour.sd_to_XYZ(sd)
    uv = colour.UCS_to_uv(colour.XYZ_to_UCS(xyz))
    cct, _ = colour.uv_to_CCT(uv, method="Ohno 2013")
    assert abs(float(cct) - target_K) < 600     # +/- 600 K is fine for an illustrative model
