import pytest
from hcl_core.spectral_reconstruct import assemble_nvrd_rows
from hcl_core.alpha_opic import alpha_opic_from_channels

POINT = [1.0, 2.0, 3.0]
VIEW = [0.0, 0.0, 1.0]
TS = [(1, 1, 8.0), (1, 1, 8.1), (1, 1, 8.2)]
# per_timestep_channels: list of (sky_channels, sun_channels) per timestep (9-channel here)
SERIES = [
    ([0.2, 0.22, 0.25, 0.30, 0.28, 0.24, 0.18, 0.14, 0.10],
     [0.05, 0.06, 0.07, 0.09, 0.08, 0.07, 0.06, 0.05, 0.04]),
    ([0.1] * 9, [0.02] * 9),
    ([0.0] * 9, [0.0] * 9),
]

def test_row_count_matches_timesteps():
    rows = assemble_nvrd_rows(POINT, VIEW, TS, SERIES, method="faithful", channel_type=1)
    assert len(rows) == 3

def test_row_length_is_413():
    rows = assemble_nvrd_rows(POINT, VIEW, TS, SERIES, method="faithful", channel_type=1)
    for r in rows:
        assert len(r) == 413, f"row length {len(r)} != 413"

def test_column_layout():
    rows = assemble_nvrd_rows(POINT, VIEW, TS, SERIES, method="faithful", channel_type=1)
    r0 = rows[0]
    assert r0[0:3] == [1.0, 2.0, 3.0]          # point xyz
    assert r0[3:6] == [0.0, 0.0, 1.0]          # view vector
    assert r0[6] == 1 and r0[7] == 1 and r0[8] == 8.0   # month, day, hour
    # cols 9-11 == alpha-opic melanopic E/ELR/EDI from the summed channels
    summed = [s + u for s, u in zip(SERIES[0][0], SERIES[0][1])]
    ao = alpha_opic_from_channels(summed, 1, alpha=5)
    assert r0[9] == pytest.approx(ao["E_alpha"]) and r0[10] == pytest.approx(ao["ELR"]) \
        and r0[11] == pytest.approx(ao["EDI"])
    assert len(r0[12:]) == 401                  # spectral block

def test_faithful_spectral_block_matches_irradiance_per_nm():
    from hcl_core.alpha_opic import irradiance_per_nm
    rows = assemble_nvrd_rows(POINT, VIEW, TS, SERIES, method="faithful", channel_type=1)
    summed = [s + u for s, u in zip(SERIES[0][0], SERIES[0][1])]
    assert rows[0][12:] == irradiance_per_nm(summed, 1)

def test_enhanced_rows_also_413():
    rows = assemble_nvrd_rows(POINT, VIEW, TS, SERIES, method="reference", channel_type=1,
                              solar_zenith=30.0, sun_spectral="colored")
    assert all(len(r) == 413 for r in rows)
