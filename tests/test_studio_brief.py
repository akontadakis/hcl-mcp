import json
import os
import pytest
from hcl_mcp.studio import save_brief_to_dir, load_brief_from_dir, empty_brief

def test_empty_brief_has_phase_keys():
    b = empty_brief("demo")
    assert b["study"] == "demo"
    for k in ("orient", "goal", "space", "daylight_baseline", "fixture_spec",
              "sim_results", "energy", "compliance"):
        assert k in b

def test_load_missing_returns_empty_skeleton(tmp_path):
    b = load_brief_from_dir(str(tmp_path), "newstudy")
    assert b == empty_brief("newstudy")

def test_save_then_load_roundtrip(tmp_path):
    b = empty_brief("s1")
    b["goal"] = {"standard": "well_l03", "mel_edi_target": 250}
    path = save_brief_to_dir(str(tmp_path), "s1", b)
    assert os.path.exists(path)
    again = load_brief_from_dir(str(tmp_path), "s1")
    assert again["goal"]["mel_edi_target"] == 250

def test_save_shallow_merges_top_level_keys(tmp_path):
    save_brief_to_dir(str(tmp_path), "s2", {"goal": {"mel_edi_target": 250}})
    save_brief_to_dir(str(tmp_path), "s2", {"space": {"L": 6}})
    merged = load_brief_from_dir(str(tmp_path), "s2")
    assert merged["goal"]["mel_edi_target"] == 250   # preserved
    assert merged["space"]["L"] == 6                  # added

def test_save_keeps_slug_param_over_brief_study_key(tmp_path):
    # a full brief carrying its own (stale/wrong) "study" key must not override the slug param
    save_brief_to_dir(str(tmp_path), "real", {"study": "WRONG", "goal": {"mel_edi_target": 250}})
    out = load_brief_from_dir(str(tmp_path), "real")
    assert out["study"] == "real"
    assert out["goal"]["mel_edi_target"] == 250

@pytest.mark.parametrize("bad", ["../escape", "a/b", "..", ".", "x/../y", ""])
def test_path_traversal_slugs_are_rejected(tmp_path, bad):
    # study becomes a directory name and arrives from tool args — must not escape the work dir
    with pytest.raises(ValueError):
        save_brief_to_dir(str(tmp_path), bad, {"goal": {}})
    with pytest.raises(ValueError):
        load_brief_from_dir(str(tmp_path), bad)

def test_save_rejects_unknown_brief_key(tmp_path):
    # a typo'd phase name must fail loudly, not silently corrupt the brief schema
    with pytest.raises(ValueError):
        save_brief_to_dir(str(tmp_path), "ok", {"fixtures_spec": {}})  # typo of fixture_spec

def test_save_accepts_all_phase_keys_plus_study(tmp_path):
    full = empty_brief("ok")
    full["goal"] = {"mel_edi_target": 250}
    # passing a complete brief (every phase key + study) must be accepted, not rejected
    save_brief_to_dir(str(tmp_path), "ok", full)
    assert load_brief_from_dir(str(tmp_path), "ok")["goal"]["mel_edi_target"] == 250
