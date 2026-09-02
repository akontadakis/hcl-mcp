import pytest
from hcl_core import glazing


@pytest.mark.parametrize("kind", glazing.KINDS)
def test_transmittance_normalized_to_assumed_uncoated_double_vt(kind):
    t = glazing.transmittance(kind)
    assert len(t) == 401
    assert abs(glazing._visible_transmittance(t) - glazing.ASSUMED_UNCOATED_DOUBLE_VT) < 1e-3


def _red_blue_ratio(t):
    # T(700nm)/T(450nm); index = wl-380
    return t[700 - 380] / t[450 - 380]


def test_transmittance_in_unit_interval():
    for kind in glazing.KINDS:
        t = glazing.transmittance(kind)
        assert all(0.0 < v <= 1.0 for v in t)


def test_warmth_ordering_clear_lt_single_lt_double():
    # warmer glazing = higher red/blue ratio; clear is ~neutral (~1.0)
    r = {k: _red_blue_ratio(glazing.transmittance(k)) for k in glazing.KINDS}
    assert abs(r["clear"] - 1.0) < 1e-6
    assert r["clear"] < r["lowE_single"] < r["lowE_double"]


def test_deconfound_roundtrip_recovers_original():
    spd = [(float(wl), 0.5) for wl in glazing.GRID_NM]
    de = glazing.deconfound(spd, "lowE_double")
    t = glazing.transmittance("lowE_double")
    re = [(wl, v * t[int(round(wl)) - 380]) for wl, v in de]
    assert all(abs(a[1] - b[1]) < 1e-9 for a, b in zip(re, spd))


def test_deconfound_by_warm_glazing_bluens_the_spd():
    # a flat measured SPD, deconfounded by a WARM (red-tilted) glazing, becomes BLUE-tilted
    spd = [(float(wl), 1.0) for wl in glazing.GRID_NM]
    de = glazing.deconfound(spd, "lowE_double")
    rb_before = spd[700 - 380][1] / spd[450 - 380][1]            # 1.0
    rb_after = de[700 - 380][1] / de[450 - 380][1]
    assert rb_after < rb_before                                   # red suppressed → bluer


def test_the_falsified_low_e_default_is_gone():
    """0.744 was a coated-Low-E default that is falsified and retired. It must not
    survive as a default anyone can inherit silently.
    """
    assert not hasattr(glazing, "TARGET_VT"), (
        "TARGET_VT is the falsified 0.744 default - it must be renamed, not kept")
    assert glazing.ASSUMED_UNCOATED_DOUBLE_VT != 0.744


def test_the_assumed_vt_is_in_the_uncoated_double_range():
    """Plain uncoated double glazing runs nearer 0.78-0.82 than the coated 0.744."""
    assert 0.78 <= glazing.ASSUMED_UNCOATED_DOUBLE_VT <= 0.82


def test_the_module_states_the_vt_is_ASSUMED_not_measured():
    """PROVENANCE section 10: the CONSTRUCTION is settled, the TRANSMITTANCE is not.
    No product name or datasheet exists. A reader must not be able to mistake this
    for a measured value."""
    text = (glazing.__doc__ or "") + (glazing.transmittance.__doc__ or "")
    assert "assum" in text.lower()
    assert "not measured" in text.lower()


def test_the_module_no_longer_claims_a_low_e_window():
    """The old docstring said the source SPDs were "seen through a VT 74.4% Low-E
    window". Both halves are false: no Low-E, and the readings never crossed glass."""
    doc = (glazing.__doc__ or "").lower()
    assert "74.4" not in doc
    assert "seen through" not in doc


def test_deconfound_docstring_states_the_outside_reading_exclusion():
    """The operation is valid for a genuinely glazed SPD and INVALID for an outside
    reading. That distinction has to travel with the function, not only in a document."""
    doc = (glazing.deconfound.__doc__ or "").lower()
    assert "outside" in doc


def test_deconfound_still_works_on_a_genuinely_glazed_spd():
    """The function is kept, not deprecated - it remains correct for a user's own
    interior measurement. Retiring the DEFAULT must not break the OPERATION."""
    spd = [(wl, 1.0) for wl in glazing.GRID_NM]
    out = glazing.deconfound(spd, "lowE_double", target_vt=0.70)
    assert len(out) == len(spd)
    assert all(v > 0 for _, v in out)
