"""annual_nvrd's single-timestep `divergence` must be evaluated where the sun is actually up.

Regression: the representative timestep was the first with non-zero SKY channels, which on a
real year is a pre-sunrise step -- faint diffuse sky, every SUN channel identically zero. The
neutral-vs-colored-sun comparison then divided zero by zero and reported exactly 0.0, which reads
as "the sun's spectral treatment does not matter" when the true value at a sunlit step is ~+0.6%.
"""
from hcl_radiance.annual_nvrd import _representative_timestep


def _mk(sky, sun):
    """One timestep in the (sky_channels, sun_channels) shape the series carries."""
    return ([sky] * 9, [sun] * 9)


def test_prefers_peak_sun_over_first_lit_sky():
    series = [
        _mk(0.0, 0.0),      # 0 night
        _mk(0.004, 0.0),    # 1 pre-sunrise: sky lit, sun still below horizon  <-- the old pick
        _mk(0.5, 2.0),      # 2 sun up
        _mk(0.9, 9.0),      # 3 peak sun
        _mk(0.3, 1.0),      # 4 declining
    ]
    assert _representative_timestep(series) == 3


def test_never_picks_a_timestep_with_no_sun():
    series = [_mk(0.0, 0.0), _mk(0.004, 0.0), _mk(0.7, 3.0)]
    rep = _representative_timestep(series)
    assert any(v > 0 for v in series[rep][1]), "representative timestep has no direct sun"


def test_falls_back_to_brightest_sky_when_the_sun_never_rises():
    """An all-overcast series has no sun anywhere; the comparison is then degenerate by nature,
    but the pick should still be the most-lit step rather than the first faintly-lit one."""
    series = [_mk(0.0, 0.0), _mk(0.004, 0.0), _mk(0.5, 0.0), _mk(0.2, 0.0)]
    assert _representative_timestep(series) == 2


def test_all_dark_series_returns_zero():
    series = [_mk(0.0, 0.0), _mk(0.0, 0.0)]
    assert _representative_timestep(series) == 0


def test_empty_series_returns_zero():
    assert _representative_timestep([]) == 0
