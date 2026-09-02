"""run_grid(export_csv=...) must serialise every result block it computed, not only daylight.

Regression: the writer dumped `daylight` unconditionally. On an electric-only run (no sky) the
daylight block is legitimately all zeros, so the CSV was all zeros while the tool return carried
the real electric numbers. A caller trusting the file over the return would conclude the
luminaires emit nothing.
"""
import csv
import os

from hcl_radiance.grid import _write_metrics_csv


def _rows(path):
    with open(path, newline="") as fh:
        return list(csv.reader(fh))


def _blocks(daylight_v, electric_v=None, combined_v=None):
    """Build the minimal {channels, metrics} block shapes _write_metrics_csv consumes."""
    def blk(v):
        return {"channels": [[v, v, v]], "metrics": [{"photopic_lux": v, "melanopic_lux": v}]}
    out = {"daylight": blk(daylight_v)}
    if electric_v is not None:
        out["electric"] = blk(electric_v)
    if combined_v is not None:
        out["combined"] = blk(combined_v)
    return out


def test_daylight_only_run_is_unchanged(tmp_path):
    """A daylight-only run must keep the historical single-block layout."""
    p = str(tmp_path / "g.csv")
    _write_metrics_csv(p, blocks=_blocks(5.0))
    rows = _rows(p)
    assert rows[0][0] == "point"
    assert "condition" not in rows[0], "no condition column when there is only one block"
    assert len(rows) == 2
    assert float(rows[1][-1]) == 5.0


def test_electric_only_run_does_not_write_an_all_zero_file(tmp_path):
    """The defect: electric numbers present in the return but absent from the CSV."""
    p = str(tmp_path / "g.csv")
    _write_metrics_csv(p, blocks=_blocks(0.0, electric_v=908.7, combined_v=908.7))
    body = _rows(p)[1:]
    vals = [float(c) for r in body for c in r[1:] if _is_num(c)]
    assert any(v > 0 for v in vals), "CSV is all zeros while the electric block is non-zero"


def test_multi_block_run_labels_each_condition(tmp_path):
    p = str(tmp_path / "g.csv")
    _write_metrics_csv(p, blocks=_blocks(1.0, electric_v=2.0, combined_v=3.0))
    rows = _rows(p)
    assert rows[0][0] == "condition", "multi-block CSV must name the condition per row"
    conds = [r[0] for r in rows[1:]]
    assert conds == ["daylight", "electric", "combined"]
    # each block's own value survives
    assert float(rows[1][-1]) == 1.0
    assert float(rows[2][-1]) == 2.0
    assert float(rows[3][-1]) == 3.0


def _is_num(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


def test_header_is_the_union_of_every_block_s_metric_keys(tmp_path):
    """Blocks legitimately carry DIFFERENT metric keys, and the export must not lose the odd ones.

    The binned route adds `mel_der_note`; the transported route adds `source_mel_der` and
    `transport_ratio` (ADR-0006). Taking the header from the first block alone silently dropped
    whatever only a later block had — so the electric rows lost exactly the provenance needed to
    read them, in the file most likely to end up in a paper.
    """
    p = str(tmp_path / "g.csv")
    _write_metrics_csv(p, blocks={
        "daylight": {"channels": [[1, 1, 1]],
                     "metrics": [{"photopic_lux": 1.0, "mel_der": 0.72,
                                  "mel_der_source": "binned_channels", "mel_der_note": "n"}]},
        "electric": {"channels": [[2, 2, 2]],
                     "metrics": [{"photopic_lux": 2.0, "mel_der": 0.26,
                                  "mel_der_source": "spd_transported",
                                  "source_mel_der": 0.3155, "transport_ratio": 0.834}]},
    })
    rows = _rows(p)
    header = rows[0]
    for k in ("mel_der_note", "source_mel_der", "transport_ratio"):
        assert k in header, f"{k} missing from the CSV header {header}"

    # and the values land under the right columns, per block
    by_condition = {r[0]: dict(zip(header, r)) for r in rows[1:]}
    assert by_condition["electric"]["source_mel_der"] == "0.3155"
    assert by_condition["electric"]["transport_ratio"] == "0.834"
    assert by_condition["daylight"]["source_mel_der"] == ""     # absent for this block, not wrong
    assert by_condition["daylight"]["mel_der_note"] == "n"
