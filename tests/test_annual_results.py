from hcl_radiance.annual_results import parse_ill, parse_ill_matrix, combine_sky_sun, recombine_annual

# A real dctimestep ASCII matrix: info header (NROWS=points, NCOLS=timesteps, NCOMP=3)
# terminated by a blank line, then ONE row per sensor point holding NCOLS interleaved
# RGB triplets across the row. parse_ill must return a sensor's per-timestep series.
ILL_1PT_3T = ("#?RADIANCE\n"
              "dctimestep illum.mtx sky.mtx\n"
              "NROWS=1\nNCOLS=3\nNCOMP=3\nFORMAT=ascii\n"
              "\n"
              "0.1 0.1 0.1\t0.2 0.2 0.2\t0.3 0.3 0.3\n")

ILL_2PT_2T = ("#?RADIANCE\n"
              "NROWS=2\nNCOLS=2\nNCOMP=3\nFORMAT=ascii\n"
              "\n"
              "1 1 1\t2 2 2\n"      # sensor 0: two timesteps
              "9 9 9\t8 8 8\n")     # sensor 1: two timesteps

def test_parse_ill_reads_sensor_row_as_timestep_series():
    # one sensor, three timesteps -> three [R,G,B], NOT one triplet per line
    assert parse_ill(ILL_1PT_3T) == [[0.1, 0.1, 0.1], [0.2, 0.2, 0.2], [0.3, 0.3, 0.3]]

def test_parse_ill_selects_sensor_zero_by_default():
    assert parse_ill(ILL_2PT_2T) == [[1.0, 1.0, 1.0], [2.0, 2.0, 2.0]]
    assert parse_ill(ILL_2PT_2T, sensor=1) == [[9.0, 9.0, 9.0], [8.0, 8.0, 8.0]]

def test_parse_ill_headerless_stream_chunks_into_triples():
    # no Radiance header -> whole numeric stream treated as one sensor's series
    assert parse_ill("0.1 0.1 0.1 0.2 0.2 0.2\n") == [[0.1, 0.1, 0.1], [0.2, 0.2, 0.2]]

def test_combine_sky_sun_adds():
    sky = [[1.0, 1.0, 1.0]]; sun = [[0.5, 0.5, 0.5]]
    assert combine_sky_sun(sky, sun) == [[1.5, 1.5, 1.5]]

def test_recombine_annual_3channel():
    # one timestep, [1,1,1] 3-channel -> melanopic 179
    combined_sets = [[[1.0, 1.0, 1.0]]]  # one channel-set, one timestep
    metrics = recombine_annual(combined_sets, channel_type=0)
    assert round(metrics[0]["melanopic_lux"], 6) == 179.0

def test_recombine_annual_multi_timestep():
    # one channel-set, two timesteps -> two metric dicts (proves the series survives end to end)
    combined_sets = [parse_ill(ILL_1PT_3T)]  # 3 timesteps, all neutral
    metrics = recombine_annual(combined_sets, channel_type=0)
    assert len(metrics) == 3
    assert round(metrics[0]["melanopic_lux"], 4) == round(0.1 * 179.0, 4)

def test_parse_ill_rejects_binary_format():
    import pytest
    binary = ("#?RADIANCE\ndctimestep illum.mtx sky.mtx\n"
              "NROWS=1\nNCOLS=3\nNCOMP=3\nFORMAT=float\n\n<binary bytes here>\n")
    with pytest.raises(ValueError, match="(?i)ascii|binary|format"):
        parse_ill(binary)

def test_parse_ill_accepts_explicit_ascii_format():
    # FORMAT=ascii must still parse normally (ILL_1PT_3T declares FORMAT=ascii)
    assert parse_ill(ILL_1PT_3T) == [[0.1, 0.1, 0.1], [0.2, 0.2, 0.2], [0.3, 0.3, 0.3]]

def test_parse_ill_matrix_all_rows():
    out = parse_ill_matrix(ILL_2PT_2T)
    assert out == [
        [[1.0, 1.0, 1.0], [2.0, 2.0, 2.0]],   # sensor 0, 2 timesteps
        [[9.0, 9.0, 9.0], [8.0, 8.0, 8.0]],   # sensor 1, 2 timesteps
    ]

def test_parse_ill_matrix_empty():
    assert parse_ill_matrix("#?RADIANCE\nNROWS=0\nNCOLS=0\nNCOMP=3\nFORMAT=ascii\n\n") == []
