"""mel-EDI must be exact whenever the source spectrum is known.

The binned route infers mel-DER from 9 channel averages. That is exact for D65 by construction
and good to ~1.5% for smooth spectra, but a narrow-band fluorescent reads up to 8% high because
the bins cannot resolve its emission lines. Anywhere the pipeline actually holds the source SPD —
every electric-lighting path, and any sky whose spectral record is at hand — mel-DER must be
computed from that SPD instead, and the result must say which route produced it.
"""
import warnings

import pytest

from hcl_core.metrics import circadian_metrics
from hcl_core.presets import get_preset
from hcl_core.spd import parse_spd, bin_average
from hcl_core.spectral_metrics import mel_der

warnings.filterwarnings("ignore")

# FL4 is the worst binning case in the preset library (+8.1% on the binned route).
SPIKY = "FL4"
SMOOTH = "D50"


def _channels(preset, channel_type=1):
    return bin_average(parse_spd(get_preset(preset)), channel_type)


@pytest.mark.parametrize("preset", [SPIKY, SMOOTH, "FL11", "A", "LED_3000K"])
def test_exact_route_matches_the_continuous_spd(preset):
    """With the SPD supplied, mel_der must equal the continuous-SPD value, not the binned one.

    These channels ARE the source's own bin averages — the source characterisation case — so the
    transport is neutral and the transported route must land exactly on the continuous value.
    That equality is what makes ADR-0006 a generalisation rather than a change of answer.
    """
    m = circadian_metrics(_channels(preset), 1, spd=get_preset(preset))
    assert m["mel_der"] == pytest.approx(mel_der(get_preset(preset)), rel=1e-9)
    assert m["mel_der_source"] == "spd_transported"
    assert m["transport_ratio"] == pytest.approx(1.0, abs=1e-4)


def test_exact_route_fixes_the_worst_binning_case():
    ch = _channels(SPIKY)
    binned = circadian_metrics(ch, 1)
    exact = circadian_metrics(ch, 1, spd=get_preset(SPIKY))
    err = abs(binned["mel_der"] - exact["mel_der"]) / exact["mel_der"]
    assert err > 0.05, "fixture no longer exercises a large binning error"
    assert exact["mel_der"] == pytest.approx(mel_der(get_preset(SPIKY)), rel=1e-9)


def test_mel_edi_uses_the_exact_der():
    ch = _channels(SPIKY)
    m = circadian_metrics(ch, 1, spd=get_preset(SPIKY))
    assert m["mel_edi"] == pytest.approx(m["photopic_lux"] * m["mel_der"], rel=1e-9)


def test_binned_route_is_still_labelled_when_no_spd_is_given():
    m = circadian_metrics(_channels(SMOOTH), 1)
    assert m["mel_der_source"] == "binned_channels"


def test_binned_route_carries_its_accuracy_caveat():
    """A value that may be several percent off must not look authoritative."""
    m = circadian_metrics(_channels(SPIKY), 1)
    assert "mel_der_note" in m
    assert "binned" in m["mel_der_note"].lower()


def test_exact_route_has_no_caveat():
    m = circadian_metrics(_channels(SPIKY), 1, spd=get_preset(SPIKY))
    assert "mel_der_note" not in m


def test_d65_is_unity_on_both_routes():
    """The definition anchor must hold whichever way it is computed."""
    assert circadian_metrics(_channels("D65"), 1)["mel_der"] == pytest.approx(1.0, abs=1e-9)
    assert circadian_metrics(_channels("D65"), 1,
                             spd=get_preset("D65"))["mel_der"] == pytest.approx(1.0, abs=1e-9)


def test_many_points_share_one_spd():
    """One source SPD, many points. Points seeing the SAME spectrum agree; that is not the same
    claim as 'every point agrees' — see test_points_seeing_different_spectra_get_different_der."""
    rows = circadian_metrics([_channels(SPIKY), _channels(SPIKY)], 1, spd=get_preset(SPIKY))
    assert all(r["mel_der_source"] == "spd_transported" for r in rows)
    assert rows[0]["mel_der"] == pytest.approx(mel_der(get_preset(SPIKY)), rel=1e-9)


def test_points_seeing_different_spectra_get_different_der():
    """The complement of the test above, and the defect it would otherwise hide.

    Sharing one SOURCE spectrum does not mean sharing one mel-DER: the room stands between the
    lamp and each point, and it does not treat every wavelength alike.
    """
    src = _channels(SPIKY)
    warm = [c * (0.45 + 0.30 * i / 8.0) for i, c in enumerate(src)]
    rows = circadian_metrics([src, warm], 1, spd=get_preset(SPIKY))
    assert rows[1]["mel_der"] < rows[0]["mel_der"]
    assert rows[1]["transport_ratio"] < 0.99
    assert rows[0]["source_mel_der"] == rows[1]["source_mel_der"], "the lamp is still one lamp"


def test_three_channel_exact_route():
    ch = bin_average(parse_spd(get_preset(SPIKY)), 0)
    m = circadian_metrics(ch, 0, spd=get_preset(SPIKY))
    assert m["mel_der"] == pytest.approx(mel_der(get_preset(SPIKY)), rel=1e-9)


def test_scaling_channels_does_not_move_the_exact_der():
    """mel-DER is a spectral-shape ratio; brightness must not affect it."""
    ch = _channels(SPIKY)
    a = circadian_metrics(ch, 1, spd=get_preset(SPIKY))
    b = circadian_metrics([2 * c for c in ch], 1, spd=get_preset(SPIKY))
    assert b["mel_der"] == pytest.approx(a["mel_der"], rel=1e-12)
    assert b["mel_edi"] == pytest.approx(2 * a["mel_edi"], rel=1e-9)
