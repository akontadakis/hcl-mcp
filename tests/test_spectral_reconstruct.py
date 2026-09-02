import pytest
from hcl_core.spectral_reconstruct import reconstruct_spectrum, reconstruction_divergence, _sun_reference_spd, assemble_nvrd_rows
from hcl_core.alpha_opic import irradiance_per_nm
from hcl_core.data import BINS_9, BINS_3

SKY9 = [0.20, 0.22, 0.25, 0.30, 0.28, 0.24, 0.18, 0.14, 0.10]
SUN9 = [0.05, 0.06, 0.07, 0.09, 0.08, 0.07, 0.06, 0.05, 0.04]

def _bin_indices(channel_type):
    bins = BINS_9 if channel_type == 1 else [[380, 499], [499, 587], [587, 780]]
    spans = []
    for k, (lo, hi) in enumerate(bins):
        lo_i, hi_i = lo - 380, hi - 380
        if k == len(bins) - 1:
            hi_i = 401  # fold the appended 780-nm point into the last bin (matches module _bin_spans)
        spans.append((lo_i, hi_i))
    return spans

def test_spectrum_is_401_long_both_methods():
    for method in ("faithful", "reference"):
        v = reconstruct_spectrum(SKY9, SUN9, 1, method=method)
        assert len(v) == 401

def test_faithful_equals_alpha_opic_path_bit_for_bit():
    summed = [s + u for s, u in zip(SKY9, SUN9)]
    v = reconstruct_spectrum(SKY9, SUN9, 1, method="faithful")
    assert v == irradiance_per_nm(summed, 1)

def test_reference_reintegrates_to_flat_bin_totals():
    flat = reconstruct_spectrum(SKY9, SUN9, 1, method="faithful")
    ref = reconstruct_spectrum(SKY9, SUN9, 1, method="reference",
                               sky_spd=None, sun_spectral="colored", solar_zenith=30.0)
    for lo_i, hi_i in _bin_indices(1):
        fb = sum(flat[lo_i:hi_i]); rb = sum(ref[lo_i:hi_i])
        if fb == 0:
            assert rb == pytest.approx(0.0, abs=1e-9)
        else:
            assert rb == pytest.approx(fb, rel=1e-9), f"bin {lo_i}:{hi_i} {rb} != {fb}"

def test_reference_differs_from_flat_in_melanopic_bins():
    # melanopic bins span ~459-558 nm -> 9-channel bins index 2..4 (459-499,499-529,529-558).
    flat = reconstruct_spectrum(SKY9, SUN9, 1, method="faithful")
    ref = reconstruct_spectrum(SKY9, SUN9, 1, method="reference", solar_zenith=30.0)
    diffs = [abs(ref[i] - flat[i]) for i in range(459 - 380, 558 - 380)]
    assert max(diffs) > 1e-6, "reference should reshape within the melanopic bins"

def test_neutral_sun_falls_back_to_flat_for_sun():
    neu = reconstruct_spectrum([0.0]*9, SUN9, 1, method="reference", sun_spectral="neutral")
    col = reconstruct_spectrum([0.0]*9, SUN9, 1, method="reference", sun_spectral="colored",
                               solar_zenith=60.0)
    flat_sun = irradiance_per_nm(SUN9, 1)
    assert neu == pytest.approx(flat_sun, rel=1e-9)
    assert any(abs(col[i] - flat_sun[i]) > 1e-7 for i in range(401))

def test_dseries_sky_reintegrates_to_flat_bin_totals():
    ref = reconstruct_spectrum(SKY9, [0.0]*9, 1, method="reference",
                               dseries_sky=True, sky_cct=6504.0, sun_spectral="neutral")
    flat = reconstruct_spectrum(SKY9, [0.0]*9, 1, method="faithful")
    for lo_i, hi_i in _bin_indices(1):
        fb, rb = sum(flat[lo_i:hi_i]), sum(ref[lo_i:hi_i])
        assert rb == pytest.approx(fb, rel=1e-9)

def test_three_channel_supported():
    sky3 = [0.3, 0.4, 0.5]; sun3 = [0.1, 0.1, 0.1]   # r,g,b
    v = reconstruct_spectrum(sky3, sun3, 0, method="reference")
    assert len(v) == 401

def test_three_channel_reference_reintegrates_to_flat_bin_totals():
    sky3, sun3 = [0.3, 0.4, 0.5], [0.1, 0.12, 0.08]  # r,g,b
    flat = reconstruct_spectrum(sky3, sun3, 0, method="faithful")
    ref = reconstruct_spectrum(sky3, sun3, 0, method="reference", solar_zenith=30.0)
    for lo_i, hi_i in _bin_indices(0):
        fb, rb = sum(flat[lo_i:hi_i]), sum(ref[lo_i:hi_i])
        if fb == 0:
            assert rb == pytest.approx(0.0, abs=1e-9)
        else:
            assert rb == pytest.approx(fb, rel=1e-9)

def test_divergence_returns_four_numbers():
    d = reconstruction_divergence(SKY9, SUN9, 1, solar_zenith=30.0)
    assert set(d) == {"flat_vs_reference", "neutral_vs_colored_sun"}
    for k in d:
        assert set(d[k]) == {"mel_edi_pct", "i_eff_pct"}
        assert isinstance(d[k]["mel_edi_pct"], float) and isinstance(d[k]["i_eff_pct"], float)

def test_divergence_zero_when_inputs_make_methods_equal():
    d = reconstruction_divergence([0.0]*9, [0.0]*9, 1, solar_zenith=30.0)
    assert d["flat_vs_reference"]["mel_edi_pct"] == pytest.approx(0.0, abs=1e-9)
    assert d["neutral_vs_colored_sun"]["mel_edi_pct"] == pytest.approx(0.0, abs=1e-9)


def test_sun_spd_none_is_unchanged_template_behavior():
    # Backward-compat: omitting sun_spd reproduces the air-mass template result exactly.
    sky = [10.0] * 9
    sun = [5.0] * 9
    base = reconstruct_spectrum(sky, sun, 1, method="reference", sun_spectral="colored",
                                solar_zenith=30.0)
    same = reconstruct_spectrum(sky, sun, 1, method="reference", sun_spectral="colored",
                                solar_zenith=30.0, sun_spd=None)
    assert base == same


def test_sun_spd_injection_reshapes_sun_and_preserves_bin_energy():
    sky = [0.0] * 9          # isolate the sun contribution
    sun = [5.0] * 9
    # A red-weighted sun reference (rising 380->780) vs the template.
    red_ref = [float(i) for i in range(401)]
    out = reconstruct_spectrum(sky, sun, 1, method="reference", sun_spectral="colored",
                               sun_spd=red_ref)
    templ = reconstruct_spectrum(sky, sun, 1, method="reference", sun_spectral="colored",
                                 solar_zenith=30.0)
    assert out != templ                       # the injected reference changed the shape
    # Per-bin energy preserved: total over the whole 401 grid equals the flat-sun total.
    from hcl_core.alpha_opic import irradiance_per_nm
    flat_total = sum(irradiance_per_nm(sun, 1))
    assert abs(sum(out) - flat_total) < 1e-6


def test_sun_reference_spd_validates_length():
    with pytest.raises(ValueError):
        _sun_reference_spd([1.0, 2.0, 3.0], None)         # not 401
    assert len(_sun_reference_spd(None, 30.0)) == 401     # falls back to template
    assert _sun_reference_spd([7.0] * 401, None)[0] == 7.0


def test_assemble_nvrd_rows_threads_sun_spd():
    # The sun_spd cascade through assemble_nvrd_rows must reach reconstruct_spectrum and reshape
    # the per-nm spectrum (cols 12+), leaving the row layout (len 413) and header cols (0..11) intact.
    point = [0.0, 0.0, 0.0]
    view = [0.0, 0.0, 1.0]
    timestamps = [(6, 21, 12.0)]
    per_ts = [([10.0] * 9, [5.0] * 9)]
    red_ref = [float(i) for i in range(401)]
    rows_inj = assemble_nvrd_rows(point, view, timestamps, per_ts, method="reference",
                                  channel_type=1, sun_spd=red_ref)
    rows_templ = assemble_nvrd_rows(point, view, timestamps, per_ts, method="reference",
                                    channel_type=1)
    assert len(rows_inj[0]) == 413 and len(rows_templ[0]) == 413
    assert rows_inj[0][12:] != rows_templ[0][12:]    # sun_spd reshaped the spectrum
    assert rows_inj[0][:12] == rows_templ[0][:12]     # header + melanopic cols unchanged


def test_assemble_nvrd_rows_sun_spd_series_shapes_per_step():
    from hcl_core.spectral_reconstruct import assemble_nvrd_rows, reconstruct_spectrum
    ts = [(1, 1, 9.0), (1, 1, 10.0)]
    sky = [0.20, 0.22, 0.25, 0.30, 0.28, 0.24, 0.18, 0.14, 0.10]
    sun = [0.05, 0.06, 0.07, 0.09, 0.08, 0.07, 0.06, 0.05, 0.04]
    series = [(sky, sun), (sky, sun)]
    red = [1.0 + 0.005 * i for i in range(401)]   # a non-template, red-rising reference SPD
    rows = assemble_nvrd_rows([0, 0, 0], [0, 0, 1], ts, series, method="reference",
                              channel_type=1, sun_spd_series=[red, None])
    step0 = reconstruct_spectrum(sky, sun, 1, method="reference", sun_spd=red)
    step1 = reconstruct_spectrum(sky, sun, 1, method="reference", sun_spd=None)
    assert rows[0][12:] == step0          # step 0 shaped by the physical SPD
    assert rows[1][12:] == step1          # step 1 falls back to the air-mass template
    assert rows[0][12:] != rows[1][12:]   # the per-step series genuinely differs


def test_assemble_nvrd_rows_series_none_matches_single_spd_path():
    from hcl_core.spectral_reconstruct import assemble_nvrd_rows
    ts = [(1, 1, 9.0), (1, 1, 10.0)]
    sky = [0.20, 0.22, 0.25, 0.30, 0.28, 0.24, 0.18, 0.14, 0.10]
    sun = [0.05, 0.06, 0.07, 0.09, 0.08, 0.07, 0.06, 0.05, 0.04]
    series = [(sky, sun), (sky, sun)]
    base = assemble_nvrd_rows([0, 0, 0], [0, 0, 1], ts, series, method="reference", channel_type=1)
    withnone = assemble_nvrd_rows([0, 0, 0], [0, 0, 1], ts, series, method="reference",
                                  channel_type=1, sky_spd_series=None, sun_spd_series=None)
    assert base == withnone   # both series None → unchanged behavior


def test_sky_reference_prefers_physical_spd_over_dseries():
    # Regression: _sky_reference_spd checked dseries_sky first, so physical_sky=True +
    # sky_reconstruction='dseries' silently discarded the real EPW sky. Physical sky must win.
    from hcl_core.spectral_reconstruct import _sky_reference_spd, dseries_spd
    phys = [0.5] * 401
    assert _sky_reference_spd(phys, True, 5000.0) == phys           # explicit physical sky wins
    assert _sky_reference_spd(None, True, 5000.0) == dseries_spd(5000.0)  # dseries fallback intact


# --- D-18: _shape_within_bins must never emit negative per-nm values, even for a mixed-sign reference ---

def test_shape_within_bins_never_emits_negatives_for_mixed_sign_reference():
    from hcl_core.spectral_reconstruct import _shape_within_bins, _bin_spans
    flat = [1.0] * 401                      # each bin has a positive total
    ref = [1.0] * 401
    ref[0] = -10.0                          # a negative shape value inside an otherwise-positive bin
    out = _shape_within_bins(flat, ref, channel_type=3)
    assert min(out) >= 0.0                  # no negative per-nm irradiance
    # bin totals are preserved despite the clamp
    for lo_i, hi_i in _bin_spans(3):
        assert abs(sum(out[lo_i:hi_i]) - sum(flat[lo_i:hi_i])) < 1e-9
