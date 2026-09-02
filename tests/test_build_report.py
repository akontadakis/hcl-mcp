import os
import pytest
from hcl_mcp.studio import build_report_to_dir, empty_brief

def _populated(study="r1"):
    b = empty_brief(study)
    b["goal"] = {"standard": "well_l03", "mel_edi_target": 250, "measurement_plane": "vertical@eye",
                 "condition": "clear-sky noon", "visual_task": "office", "em_lux": 500,
                 "ugr_max": 19, "uo_min": 0.6, "ra_min": 80}
    b["space"] = {"L": 6, "W": 4, "H": 3}
    b["fixture_spec"] = {"required_flux_lm": 30000, "fixture_count": 9,
                         "target_cct_band": [4000, 5000], "binding_constraint": "visual",
                         "glare_warning": False, "power_density_w_m2": 10.4}
    b["sim_results"] = {"photopic_lux": 520, "ugr": 17, "mel_edi": 260,
                        "verdict_source": "annual", "images": []}
    b["energy"] = {"savings_kwh_m2_yr": 4.2}
    b["compliance"] = [{"standard": "well_l03", "verdict": "pass", "citation": "WELL v2 L03"}]
    return b

def test_report_writes_html_and_md(tmp_path):
    res = build_report_to_dir(str(tmp_path), "r1", _populated())
    assert os.path.exists(res["html_path"]) and os.path.exists(res["md_path"])
    html = open(res["html_path"]).read()
    assert "WELL" in html and "Target vs Achieved" in html

def test_report_cross_checks_circadian_and_glare(tmp_path):
    b = _populated("r2")
    b["sim_results"] = {"photopic_lux": 520, "ugr": 22, "mel_edi": 260, "verdict_source": "grid",
                        "images": []}
    b["goal"]["ugr_max"] = 19
    res = build_report_to_dir(str(tmp_path), "r2", b)
    md = open(res["md_path"]).read()
    # P2: mel-EDI met but UGR over limit must be flagged together
    assert "mel-EDI met but UGR" in md or "UGR exceeds" in md

def test_report_marks_verdict_provenance(tmp_path):
    res = build_report_to_dir(str(tmp_path), "r3", _populated("r3"))
    md = open(res["md_path"]).read()
    assert "annual" in md  # P3: provenance of the circadian verdict is stated

def test_report_renders_emit_only_brief(tmp_path):
    b = empty_brief("r4")
    b["goal"] = {"standard": "well_l03", "mel_edi_target": 250}
    # no sim_results / fixture_spec -> must render "not evaluated", not crash
    res = build_report_to_dir(str(tmp_path), "r4", b)
    md = open(res["md_path"]).read()
    assert "not evaluated" in md.lower()

def test_report_includes_space_daylight_renderings_and_caveats(tmp_path):
    b = _populated("r5")
    b["daylight_baseline"] = {"e_daylight_lux": 120, "mel_edi_daylight": 90,
                              "condition": "clear-sky noon", "source": "run_grid"}
    b["sim_results"]["images"] = ["grid.hdr", "fisheye.hdr"]
    b["fixture_spec"]["assumptions"] = ["V/H ratio = 0.4"]
    b["fixture_spec"]["caveats"] = ["Lumen-method averages; confirm with run_grid."]
    md = open(build_report_to_dir(str(tmp_path), "r5", b)["md_path"]).read()
    assert "## Space" in md and "6 × 4 × 3" in md
    assert "## Daylight Baseline" in md and "120" in md and "90" in md
    assert "## Renderings" in md and "grid.hdr" in md and "fisheye.hdr" in md
    assert "## Notes & Caveats" in md and "V/H ratio" in md and "confirm with run_grid" in md

def test_report_populates_space_and_fixture_from_alias_keys(tmp_path):
    # DEF-5: a brief whose space is a [L,W,H] list and whose fixture_spec uses shorter aliases must
    # still render real numbers, not "? × ? × ?" / None.
    b = _populated("r5b")
    b["space"] = {"dimensions": [4.3, 7.3, 3.4]}
    b["fixture_spec"] = {"required_flux": 13767, "count": 4, "cct_band": [5500, 6500],
                         "binding": "circadian", "power_density": 8.5}
    md = open(build_report_to_dir(str(tmp_path), "r5b", b)["md_path"]).read()
    assert "4.3 × 7.3 × 3.4" in md
    assert "13767 lm" in md and "count **4**" in md
    assert "circadian" in md
    assert "? × ? × ?" not in md and "None lm" not in md

def test_report_renderings_emit_only_when_sim_ran_without_images(tmp_path):
    # sim_results present but images empty -> "emit-only", distinct from "not evaluated"
    md = open(build_report_to_dir(str(tmp_path), "r6", _populated("r6"))["md_path"]).read()
    assert "emit-only" in md.lower()

def test_report_tolerates_non_dict_compliance(tmp_path):
    b = _populated("r7")
    b["compliance"] = ["WELL v2 L03: pass"]  # a bare string, not a dict — must not crash
    md = open(build_report_to_dir(str(tmp_path), "r7", b)["md_path"]).read()
    assert "WELL v2 L03: pass" in md

def test_report_rejects_path_traversal_study(tmp_path):
    with pytest.raises(ValueError):
        build_report_to_dir(str(tmp_path), "../escape", _populated("x"))
