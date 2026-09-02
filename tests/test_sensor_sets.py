import pytest
from hcl_radiance.sensor_sets import (create_sensor_set, list_sensor_sets, get_sensor_set,
                                       delete_sensor_set)

def test_create_explicit_and_get(tmp_path):
    wd = str(tmp_path)
    out = create_sensor_set(wd, "desk", points=[[1, 2, 0.8, 0, 0, 1]])
    assert out["count"] == 1 and out["source"] == "explicit"
    got = get_sensor_set(wd, "desk")
    assert got["points"] == [[1.0, 2.0, 0.8, 0.0, 0.0, 1.0]]

def test_create_grid(tmp_path):
    out = create_sensor_set(str(tmp_path), "room",
                            grid={"interior": [0, 4, 0, 3], "floor_z": 0.0, "max_spacing": 1.0})
    assert out["source"] == "grid" and out["count"] > 0
    assert all(len(p) == 6 for p in out["points"])

def test_overwrite_guard(tmp_path):
    wd = str(tmp_path)
    create_sensor_set(wd, "a", points=[[0, 0, 0.8, 0, 0, 1]])
    with pytest.raises(ValueError):
        create_sensor_set(wd, "a", points=[[1, 1, 0.8, 0, 0, 1]])
    create_sensor_set(wd, "a", points=[[1, 1, 0.8, 0, 0, 1]], overwrite=True)  # ok

def test_list_and_delete(tmp_path):
    wd = str(tmp_path)
    create_sensor_set(wd, "a", points=[[0, 0, 0.8, 0, 0, 1]])
    assert [s["name"] for s in list_sensor_sets(wd)] == ["a"]
    delete_sensor_set(wd, "a")
    assert list_sensor_sets(wd) == []
    with pytest.raises(ValueError):
        get_sensor_set(wd, "a")
