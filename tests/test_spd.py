import pytest

from hcl_core.spd import parse_spd, to_grid_list, bin_average

def test_parse_flat_spd_is_constant():
    d = parse_spd([(380, 1.0), (780, 1.0)])
    assert d[380] == 1.0 and d[780] == 1.0 and len(d) == 401

def test_parse_ramp_value_equals_wavelength():
    d = parse_spd([(380, 380), (780, 780)])
    assert d[500] == 500 and d[700] == 700

def test_to_grid_list_length():
    d = parse_spd([(380, 1.0), (780, 1.0)])
    assert len(to_grid_list(d)) == 401

def test_string_input_ignores_text_but_keeps_non_integer_wavelengths():
    d = parse_spd("# header\n380 1.0\n380.5 9.9\n780, 2.0\n")
    assert d[380] == 1.0 and d[780] == 2.0
    assert len(d) == 401

def test_parse_spd_accepts_a_file_path(tmp_path):
    # A bare path to a readable .spd file is loaded from disk (mirrors the IES reader
    # and the geometry-importer's luminaire-SPD path-read). Inline text still works.
    p = tmp_path / "demo.spd"
    p.write_text("380 1.0\n780 1.0\n")
    d = parse_spd(str(p))
    assert d[380] == 1.0 and d[780] == 1.0 and len(d) == 401

def test_parse_spd_path_and_inline_text_agree(tmp_path):
    text = "380 380\n780 780\n"
    p = tmp_path / "ramp.spd"
    p.write_text(text)
    assert parse_spd(str(p)) == parse_spd(text)

def test_parse_spd_missing_path_falls_through_to_text(tmp_path):
    # A non-existent string isn't a path; it's parsed as (empty) text -> the existing
    # "no wavelength rows" error, not a FileNotFoundError.
    import pytest
    with pytest.raises(ValueError):
        parse_spd(str(tmp_path / "nope.spd"))

def test_parse_spd_tab_delimited_file_via_path(tmp_path):
    # Tab-delimited rows read from a path: exercises both the path-read branch and the
    # tab-splitting branch of _rows_from_text on real file content.
    p = tmp_path / "tabs.spd"
    p.write_text("380\t1.0\n780\t1.0\n")
    d = parse_spd(str(p))
    assert d[380] == 1.0 and d[780] == 1.0 and len(d) == 401

def test_parse_spd_directory_is_not_read_as_a_file(tmp_path):
    # isfile (not exists) guards the read, so a directory path doesn't raise IsADirectoryError;
    # it falls through to the text parse -> the normal "no rows" ValueError.
    import pytest
    with pytest.raises(ValueError):
        parse_spd(str(tmp_path))

def test_parse_spd_resamples_subinteger_grid_via_interpolation():
    d = parse_spd([(380.0, 0.0), (500.0, 0.0), (500.5, 100.0), (501.0, 0.0), (780.0, 0.0)])
    assert len(d) == 401
    assert d[500] > 0.0 or d[501] > 0.0

def test_parse_spd_rejects_all_out_of_range():
    import pytest
    with pytest.raises(ValueError):
        parse_spd([(900.0, 1.0), (1000.0, 2.0)])

def test_bin_average_flat_is_all_ones():
    d = parse_spd([(380, 1.0), (780, 1.0)])
    assert bin_average(d, 1) == [1.0] * 9
    assert bin_average(d, 0) == [1.0, 1.0, 1.0]

def test_bin_average_ramp_9channel_golden():
    d = parse_spd([(380, 380), (780, 780)])
    assert bin_average(d, 1) == [399.5, 439.0, 479.0, 514.0, 543.5, 572.5, 597.5, 619.0, 705.0]

def test_bin_average_ramp_3channel_golden():
    d = parse_spd([(380, 380), (780, 780)])
    assert bin_average(d, 0) == [683.5, 543.0, 439.5]  # r,g,b

@pytest.mark.parametrize("bad", [2, 7, -1, 9])
def test_bin_average_rejects_invalid_channel_type(bad):
    # A channel_type other than 0/1 must raise, not silently fall through to the 9-channel
    # path and echo the bad value back (DEF: spd_to_channels(channel_type=7) used to return
    # the 9-ch result labelled channel_type:7). Matches the guards in alpha_opic/metrics.
    d = parse_spd([(380, 1.0), (780, 1.0)])
    with pytest.raises(ValueError, match="channel_type must be 0"):
        bin_average(d, bad)

def test_parse_spd_half_integer_aligned_yields_full_401_grid():
    # round-half-to-even previously collapsed consecutive .5 nodes, dropping odd integer keys.
    d = parse_spd([(554.5, 10.0), (748.5, 20.0)])
    assert len(d) == 401
    assert set(d.keys()) == set(range(380, 781))

def test_to_grid_list_after_half_integer_parse_does_not_raise():
    from hcl_core.spd import to_grid_list
    grid = to_grid_list(parse_spd([(554.5, 10.0), (748.5, 20.0)]))
    assert len(grid) == 401


def test_parse_spd_single_in_range_sample_no_crash():
    # Regression: a single 380-780 sample used to IndexError (unpacking lines[1]); now flat-extends.
    d = parse_spd([(500, 1.0)])
    assert len(d) == 401 and d[380] == 1.0 and d[780] == 1.0


def test_parse_spd_extrapolation_clamps_negative():
    # Regression: leading linear extrapolation could emit negative irradiance; now clamped at 0.
    d = parse_spd([(500, 1.0), (600, 2.0)])  # grad +0.01/nm -> raw 380 = -0.2
    assert d[380] >= 0.0
    assert all(v >= 0.0 for v in d.values())


# ---- bin_average must be scale-equivariant: no absolute rounding quantum ----

def test_bin_average_is_scale_equivariant():
    """REGRESSION: `round(mean, 3)` was an absolute 5e-4 quantum, so accuracy depended on the
    SPD's magnitude -- fine for preset-scale SPDs (~75-113), corrupting for the absolute
    W/m2/nm spectral irradiance `spectral_emit.to_channels` feeds in (worst band error ~13% at
    peak 0.01). Scaling the input must scale the output exactly."""
    import math
    base = {w: 0.5 * math.exp(-((w - 550) / 120.0) ** 2) + 0.05 for w in range(380, 781)}
    for channel_type in (0, 1):
        ref = bin_average(base, channel_type)
        for s in (1e-3, 1e-2, 1.0, 1e3):
            scaled = bin_average({w: v * s for w, v in base.items()}, channel_type)
            for got, want in zip(scaled, ref):
                assert got == pytest.approx(want * s, rel=1e-12), (
                    f"channel_type={channel_type} scale={s}: {got} != {want * s}")


def test_bin_average_is_exact_on_a_flat_spd():
    # a flat SPD's band mean is the same constant, at any magnitude
    for level in (0.002, 0.2, 200.0):
        flat = {w: level for w in range(380, 781)}
        assert bin_average(flat, 0) == pytest.approx([level] * 3, rel=1e-12)
