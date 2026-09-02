"""Circadian metrics from channel irradiances. Port of grid engine (9-channel:276-278)."""
from hcl_core.data import (
    LUMINOUS_EFFICACY, W_PHOTOPIC_9, W_MELANOPIC_9, W_NEUROPIC_9, W_PHOTOPIC_3, W_MELANOPIC_3,
)

def _dot(weights, channels):
    return LUMINOUS_EFFICACY * sum(w * float(c) for w, c in zip(weights, channels))


# D65's melanopic/photopic CHANNEL ratio, per channel_type, computed once through the same
# bin_average path these metrics use. mel-DER is defined against D65, so dividing a source's
# channel ratio by D65's yields mel-DER on the binned route — exactly 1.0 for D65 itself.
# Derived rather than hardcoded from literature so the two stay consistent if the bins move.
_D65_MEL_PHOT_RATIO = {}


def _d65_ratio(channel_type):
    if channel_type not in _D65_MEL_PHOT_RATIO:
        from hcl_core.presets import get_preset
        from hcl_core.spd import parse_spd, bin_average
        ch = bin_average(parse_spd(get_preset("D65")), channel_type)
        wp = W_PHOTOPIC_9 if channel_type == 1 else W_PHOTOPIC_3
        wm = W_MELANOPIC_9 if channel_type == 1 else W_MELANOPIC_3
        den = sum(w * c for w, c in zip(wp, ch))
        num = sum(w * c for w, c in zip(wm, ch))
        _D65_MEL_PHOT_RATIO[channel_type] = (num / den) if den else 0.0
    return _D65_MEL_PHOT_RATIO[channel_type]

def _one(channels, channel_type, spd=None):
    if channel_type not in (0, 1):
        raise ValueError("channel_type must be 0 (3-channel) or 1 (9-channel)")
    if channel_type == 1:
        if len(channels) != 9:
            raise ValueError("9-channel metrics need 9 values")
        out = {"photopic_lux": _dot(W_PHOTOPIC_9, channels),
               "melanopic_lux": _dot(W_MELANOPIC_9, channels),
               "neuropic_lux": _dot(W_NEUROPIC_9, channels)}
    else:
        if len(channels) != 3:
            raise ValueError("3-channel metrics need 3 values")
        out = {"photopic_lux": _dot(W_PHOTOPIC_3, channels),
               "melanopic_lux": _dot(W_MELANOPIC_3, channels)}  # neuropic undefined for 3-channel
    return _with_mel_edi(out, channel_type, spd, channels)


_BINNED_NOTE = (
    "mel_der was inferred from BINNED channels because no source SPD was supplied. Accuracy "
    "depends on how smooth the spectrum is: exact for D65 by construction, ~0.1% for daylight, "
    "~1.5% for other smooth spectra, but up to ~8% high for a narrow-band fluorescent whose "
    "emission lines fall inside a bin. Pass spd=<the source spectrum> for the exact CIE S 026 "
    "value; for a daylit sensor, where the spectrum is a transported mixture with no single "
    "source SPD, the binned value is already accurate to a few tenths of a percent.")

_UNTRANSPORTED_NOTE = (
    "mel_der is the SOURCE spectrum's value, not the spectrum at this point: no channel carries "
    "light in a band the source emits, so the transport between them could not be recovered. This "
    "is the right answer only where the source IS the point (characterising a luminaire). Anywhere "
    "light has crossed a spectrally selective surface it overstates or understates mel-EDI by the "
    "size of the spectral shift.")


def _with_mel_edi(m, channel_type, spd=None, channels=None):
    """Add CIE S 026 mel-DER and mel-EDI alongside the melanopic-weighted illuminance.

    `melanopic_lux` is NOT mel-EDI: it is K_m x the melanopic-weighted channel sum, whereas
    mel-EDI is photopic_lux x mel-DER. They differ by D65's own melanopic/photopic ratio (~1.10
    on the 9-bin route), so passing one where the other is expected — and every circadian standard
    is written in mel-EDI — silently misstates the result by that factor. Both are returned so the
    caller never has to convert, and `mel_der` is exposed so the relation is checkable.

    WHERE THE SPECTRUM IS. `mel_der` describes the spectrum AT THE POINT the channels were measured,
    never at the lamp. That distinction is the whole content of ADR-0006: a source SPD makes mel-DER
    exact where the source IS the point (characterising a luminaire) and wrong everywhere the light
    has travelled through a spectrally selective room, which is every real room. So `spd` is read as
    "the source spectrum feeding these channels", and the transport between them is recovered from
    the channels themselves (spectral_metrics.mel_der_transported).

    ACCURACY, by route, measured against the mel-DER of the true transported spectrum:
      * "spd_transported" — source SPD supplied. Keeps the source's 1-nm structure AND the per-bin
        transport the engine applied. Worst error 0.73% over 6 sources x 3 transports; reduces
        exactly to the continuous-SPD value when the transport is neutral. Also returns
        `source_mel_der` (the luminaire's own) and `transport_ratio` = the two divided, so the shift
        the room imposed is visible rather than folded away.
      * "binned_channels" — no SPD. mel-DER inferred from the channel averages alone: exact for D65,
        ~1.5% for smooth spectra, up to ~8% high for a narrow-band fluorescent whose lines fall
        inside a bin. Carries `mel_der_note` so an approximate value never looks authoritative.
      * "spd_source_untransported" — an SPD was supplied but the transport could not be recovered
        (no band carries light). Falls back to the source value and says so.

    `mel_der_source` always records which route ran.
    """
    ph = m.get("photopic_lux", 0.0)
    ml = m.get("melanopic_lux", 0.0)
    if spd is not None:
        from hcl_core.spectral_metrics import mel_der as _exact_mel_der
        from hcl_core.spectral_metrics import mel_der_transported
        source_der = _exact_mel_der(spd)
        der = mel_der_transported(spd, channels, channel_type) if channels is not None else None
        if der is None:
            m["mel_der"] = source_der
            m["mel_edi"] = ph * source_der
            m["mel_der_source"] = "spd_source_untransported"
            m["source_mel_der"] = source_der
            m["mel_der_note"] = _UNTRANSPORTED_NOTE
            return m
        m["mel_der"] = der
        m["mel_edi"] = ph * der
        m["mel_der_source"] = "spd_transported"
        m["source_mel_der"] = source_der
        m["transport_ratio"] = round(der / source_der, 4) if source_der else None
        return m
    k = _d65_ratio(channel_type)
    der = ((ml / ph) / k) if (ph and k) else 0.0
    m["mel_der"] = der
    m["mel_edi"] = ph * der
    m["mel_der_source"] = "binned_channels"
    m["mel_der_note"] = _BINNED_NOTE
    return m

def circadian_metrics(channels, channel_type, spd=None):
    """channels: one point (list of 3/9) or many (list of lists). Returns dict or list of dicts.

    spd: the SOURCE spectrum feeding these channels, when known. Supplying it keeps the source's
    within-bin structure — which the 9 channel averages cannot represent — and combines it with the
    per-bin transport the channels reveal, so mel-DER describes the spectrum AT EACH POINT rather
    than at the lamp. Per-point values therefore differ across points, as they must. Accepts
    anything hcl_core.spd.parse_spd takes. See _with_mel_edi for the routes and their accuracy.
    """
    if channels and isinstance(channels[0], (list, tuple)):
        return [_one(row, channel_type, spd) for row in channels]
    return _one(channels, channel_type, spd)
