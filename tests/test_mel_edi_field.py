"""Channel metrics must expose S 026 mel-EDI explicitly, not only melanopic lux.

Regression: `melanopic_lux` is a melanopic-weighted illuminance (K_m x the melanopic-weighted
channel sum). CIE S 026 mel-EDI is photopic_lux x mel-DER. They differ by a fixed factor
(~1.169 for a clear-sky spectrum), and nothing in the tool signatures stopped a caller passing
one to `compliance` as though it were the other -- a 16.9% overstatement of the quantity every
circadian standard is written in.

Both quantities are legitimate, so the fix is to return mel-EDI alongside rather than rename.
"""
import math

from hcl_core.metrics import circadian_metrics

# A flat 9-channel vector: equal irradiance in every bin.
FLAT9 = [1.0] * 9


def test_mel_edi_is_returned_for_nine_channel():
    m = circadian_metrics(FLAT9, 1)
    assert "mel_edi" in m, f"no mel_edi in {sorted(m)}"


def test_mel_edi_is_not_melanopic_lux():
    """The two must be distinguishable; equality would mean the conflation is baked in."""
    m = circadian_metrics(FLAT9, 1)
    assert not math.isclose(m["mel_edi"], m["melanopic_lux"], rel_tol=1e-9)


def test_mel_edi_equals_photopic_times_mel_der():
    """The defining relation of S 026 mel-EDI."""
    m = circadian_metrics(FLAT9, 1)
    assert math.isclose(m["mel_edi"], m["photopic_lux"] * m["mel_der"], rel_tol=1e-9)


def test_mel_der_is_dimensionless_and_plausible():
    m = circadian_metrics(FLAT9, 1)
    assert 0.0 < m["mel_der"] < 2.0, m["mel_der"]


def test_scaling_the_spectrum_scales_edi_but_not_der():
    """mel-DER is a spectral-shape ratio: doubling the irradiance must not move it."""
    a = circadian_metrics(FLAT9, 1)
    b = circadian_metrics([2.0 * c for c in FLAT9], 1)
    assert math.isclose(b["mel_edi"], 2.0 * a["mel_edi"], rel_tol=1e-9)
    assert math.isclose(b["mel_der"], a["mel_der"], rel_tol=1e-9)


def test_three_channel_also_carries_mel_edi():
    m = circadian_metrics([1.0, 1.0, 1.0], 0)
    assert "mel_edi" in m and "mel_der" in m


def test_many_points_each_get_mel_edi():
    rows = circadian_metrics([FLAT9, [2.0] * 9], 1)
    assert all("mel_edi" in r for r in rows)


def test_zero_input_does_not_divide_by_zero():
    m = circadian_metrics([0.0] * 9, 1)
    assert m["mel_edi"] == 0.0
    assert m["mel_der"] == 0.0


def test_compliance_rejects_a_melanopic_lux_sized_confusion_silently_passing():
    """`compliance` must at least record which quantity it scored, so an artifact cannot be
    ambiguous about it after the fact."""
    from hcl_core.compliance import check_compliance
    r = check_compliance(mel_edi=917.7, standard="brown_2022")
    assert r.get("quantity") == "mel_edi", (
        "compliance result does not name the quantity it scored")


def test_the_units_confusion_can_flip_a_verdict_near_the_threshold():
    """The ~9% gap is not always cosmetic: near a threshold it changes pass to fail.

    Real case from the validation kit (TEST-PLAN W3.4/W3.5), whose 2026-06-29 capture scored
    `melanopic_lux` against Brown's 250 lx mel-EDI threshold and recorded a PASS. On the correct
    quantity the same eye point FAILS, so the kit had shipped a wrong verdict. Wide-margin scenes
    hide this; this one does not, which is why the two quantities must never be interchanged.
    """
    from hcl_core.compliance import check_compliance
    from hcl_core.metrics import _d65_ratio

    photopic, melanopic_lux = 240.04, 260.65          # the brightest eye point, as captured
    mel_edi = photopic * ((melanopic_lux / photopic) / _d65_ratio(1))

    assert round(mel_edi, 2) == 237.03
    assert melanopic_lux > 250 > mel_edi              # the two quantities straddle the threshold
    assert check_compliance(mel_edi=melanopic_lux, standard="brown_2022")["result"] == "pass"
    assert check_compliance(mel_edi=mel_edi, standard="brown_2022")["result"] == "fail"
