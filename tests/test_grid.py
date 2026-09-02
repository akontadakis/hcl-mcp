import os

import hcl_radiance.grid as grid

def _fake_run_writing(res_by_file):
    """Build a fake run_sequence that writes the given {res_name: content} files."""
    def fake_run(steps, work_dir, available):
        for s in steps:
            o = s.get("stdout", "")
            if o.endswith(".res"):
                with open(os.path.join(work_dir, o), "w") as fh:
                    fh.write(res_by_file[o])
        return {"ran": True, "returncode": 0, "commands": [], "outputs": list(res_by_file)}
    return fake_run

def test_run_grid_3channel_recombines(monkeypatch, tmp_path):
    # mock the runner so no Radiance is needed: pretend rtrace produced these RGB res files
    monkeypatch.setattr(grid, "run_sequence",
                        _fake_run_writing({"daylight0.res": "1.0 1.0 1.0\n0.0 0.0 0.0\n"}))
    monkeypatch.setattr(grid, "_available", lambda: True)
    out = grid.run_grid(scene_sets=[["m.rad", "sky.rad", "g.rad"]],
                        points=[[0, 0, 1.2, 0, 0, 1], [0, 0, 0, 0, 0, 1]],
                        channel_type=0, work_dir=str(tmp_path), run=True)
    assert out["ran"] is True
    assert round(out["daylight"]["metrics"][0]["melanopic_lux"], 6) == 179.0  # [1,1,1] 3ch -> 179
    assert out["daylight"]["metrics"][1]["melanopic_lux"] == 0.0
    # spec §3.1/§7.2: absolute paths for written artifacts
    assert out["work_dir"] == os.path.abspath(str(tmp_path))
    assert all(os.path.isabs(p) for p in out["files_written"])
    assert os.path.join(os.path.abspath(str(tmp_path)), "daylight0.res") in out["files_written"]

def test_run_grid_9channel_assembles_channels_in_order(monkeypatch, tmp_path):
    # Asymmetric per-set values pin the concatenation permutation (b1b2b3,g1g2g3,r1r2r3).
    monkeypatch.setattr(grid, "run_sequence", _fake_run_writing(
        {"daylight0.res": "1 2 3\n", "daylight1.res": "4 5 6\n", "daylight2.res": "7 8 9\n"}))
    monkeypatch.setattr(grid, "_available", lambda: True)
    out = grid.run_grid(scene_sets=[["a.rad"], ["b.rad"], ["c.rad"]],
                        points=[[0, 0, 0, 0, 0, 1]], channel_type=1,
                        work_dir=str(tmp_path), run=True)
    assert out["daylight"]["channels"][0] == [1, 2, 3, 4, 5, 6, 7, 8, 9]  # set-major, RGB-minor
    assert "neuropic_lux" in out["daylight"]["metrics"][0]  # 9ch yields neuropic

def test_run_grid_export_csv(monkeypatch, tmp_path):
    monkeypatch.setattr(grid, "run_sequence",
                        _fake_run_writing({"daylight0.res": "1.0 1.0 1.0\n0.0 0.0 0.0\n"}))
    monkeypatch.setattr(grid, "_available", lambda: True)
    out = grid.run_grid(scene_sets=[["m.rad"]], points=[[0, 0, 0, 0, 0, 1], [0, 0, 0, 0, 0, 1]],
                        channel_type=0, work_dir=str(tmp_path), run=True, export_csv="grid.csv")
    csv_path = out["csv_path"]
    assert os.path.isabs(csv_path) and os.path.exists(csv_path)
    lines = open(csv_path).read().strip().splitlines()
    cols = lines[0].split(",")
    # Leading layout is fixed; the metric tail follows the metrics dict, which now also carries
    # mel_der/mel_edi (see hcl_core.metrics._with_mel_edi), so assert the contract not a frozen
    # string. A daylight-only run stays single-block, hence no leading `condition` column.
    assert cols[:5] == ["point", "ch0", "ch1", "ch2", "photopic_lux"]
    assert "melanopic_lux" in cols and "mel_edi" in cols
    assert "condition" not in cols
    assert len(lines) == 3  # header + 2 points

def test_run_grid_emits_commands_when_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(grid, "_available", lambda: False)
    out = grid.run_grid(scene_sets=[["m.rad", "sky.rad", "g.rad"]],
                        points=[[0, 0, 1.2, 0, 0, 1]], channel_type=0,
                        work_dir=str(tmp_path), run=True)
    assert out["ran"] is False and any("oconv" in c for c in out["commands"])
    assert (tmp_path / "points.pts").exists()  # inputs still written
    # emit path returns absolute paths for what was actually written (just the .pts)
    assert out["inputs_written"] == [os.path.join(os.path.abspath(str(tmp_path)), "points.pts")]
    assert out["work_dir"] == os.path.abspath(str(tmp_path))

def test_run_grid_9channel_requires_three_sets(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        grid.run_grid(scene_sets=[["m.rad"]], points=[[0, 0, 0, 0, 0, 1]],
                      channel_type=1, work_dir=str(tmp_path), run=False)


def test_run_grid_rejects_channel_sets_of_unequal_length(monkeypatch, tmp_path):
    """A dropped sensor row must fail loudly, not silently misalign the channels.

    Found by audit 2026-08-06. parse_rtrace_res skips any line whose first three tokens are not
    numeric -- which is correct robustness against a stray `rtrace: warning ...` on stdout, but it
    means one channel set can come back SHORTER than its siblings. _recombine then took n_points
    from per_set[0] and indexed every other set at the same p, so point 1 silently received set-b's
    point 2 (a wrong melanopic number reported with full confidence) before finally dying on a bare
    IndexError that named neither the file nor the mismatch.
    """
    monkeypatch.setattr(grid, "run_sequence", _fake_run_writing({
        "daylight0.res": "10 10 10\n20 20 20\n30 30 30\n",
        "daylight1.res": "11 11 11\nrtrace: warning - ray recursion exceeded\n31 31 31\n",
        "daylight2.res": "12 12 12\n22 22 22\n32 32 32\n"}))
    monkeypatch.setattr(grid, "_available", lambda: True)
    try:
        grid.run_grid(scene_sets=[["a.rad"], ["b.rad"], ["c.rad"]],
                      points=[[0, 0, 0, 0, 0, 1]] * 3, channel_type=1,
                      work_dir=str(tmp_path), run=True)
    except ValueError as e:
        msg = str(e)
        assert "daylight1.res" in msg, f"the offending file must be named: {msg}"
        assert "3" in msg and "2" in msg, f"both counts must appear: {msg}"
    else:
        raise AssertionError("unequal channel sets silently produced a result")


def test_run_grid_still_recombines_when_sets_agree(monkeypatch, tmp_path):
    """The guard must not fire on well-formed output."""
    monkeypatch.setattr(grid, "run_sequence", _fake_run_writing({
        "daylight0.res": "1 2 3\n4 5 6\n", "daylight1.res": "7 8 9\n10 11 12\n",
        "daylight2.res": "13 14 15\n16 17 18\n"}))
    monkeypatch.setattr(grid, "_available", lambda: True)
    out = grid.run_grid(scene_sets=[["a.rad"], ["b.rad"], ["c.rad"]],
                        points=[[0, 0, 0, 0, 0, 1]] * 2, channel_type=1,
                        work_dir=str(tmp_path), run=True)
    assert out["daylight"]["channels"][0] == [1, 2, 3, 7, 8, 9, 13, 14, 15]
    assert out["daylight"]["channels"][1] == [4, 5, 6, 10, 11, 12, 16, 17, 18]
