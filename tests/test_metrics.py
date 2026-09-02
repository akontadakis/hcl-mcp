from hcl_core.metrics import circadian_metrics

def test_metrics_9channel_all_ones():
    m = circadian_metrics([1.0] * 9, channel_type=1)
    assert round(m["photopic_lux"], 6) == 179.004281
    assert round(m["melanopic_lux"], 6) == 179.0
    assert round(m["neuropic_lux"], 6) == 179.0

def test_metrics_3channel_has_no_neuropic():
    m = circadian_metrics([1.0, 1.0, 1.0], channel_type=0)
    assert round(m["photopic_lux"], 6) == 179.0
    assert round(m["melanopic_lux"], 6) == 179.0
    assert "neuropic_lux" not in m

def test_metrics_9channel_example():
    ch = [0.10, 0.12, 0.20, 0.30, 0.35, 0.33, 0.25, 0.18, 0.12]
    m = circadian_metrics(ch, channel_type=1)
    assert round(m["photopic_lux"], 4) == 51.5333
    assert round(m["melanopic_lux"], 4) == 41.0736
    assert round(m["neuropic_lux"], 4) == 18.2406

def test_metrics_grid_of_points():
    out = circadian_metrics([[1.0] * 9, [0.0] * 9], channel_type=1)
    assert isinstance(out, list) and len(out) == 2
    assert round(out[0]["melanopic_lux"], 6) == 179.0 and out[1]["melanopic_lux"] == 0.0
