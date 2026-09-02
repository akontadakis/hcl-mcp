import os, asyncio
from hcl_mcp.server import observer_points

ROOT = os.path.join(os.path.dirname(__file__), "fixtures")
OBJ = os.path.join(ROOT, "office_room.obj")
SIDE = os.path.join(ROOT, "office_room_material_map.json")


def _call(**kw):
    return asyncio.run(observer_points(**kw))


def test_two_observers_with_glare_views(tmp_path):
    r = _call(obj_path=OBJ, sidecar=SIDE, work_dir=str(tmp_path))
    assert len(r["observers"]) == 2
    assert len(r["glare_views"]) == 2 and r["glare_views"][0].startswith("-vp ")
    assert os.path.isfile(r["pts_path"])


def test_explicit_override(tmp_path):
    r = _call(obj_path=OBJ, sidecar=SIDE, work_dir=str(tmp_path),
              workstations=[{"eye": [0.0, 0.0], "target": [0.0, 3.5]}])
    assert len(r["observers"]) == 1
    o = r["observers"][0]
    assert o["source"] == "explicit" and o["direction"] == [0, 1, 0]


def test_methodology_carries_transparency_fields(tmp_path):
    """Spec §5: methodology must include floor_top_z, detected_seats, detected_screens, pairings."""
    r = _call(obj_path=OBJ, sidecar=SIDE, work_dir=str(tmp_path))
    m = r["methodology"]
    assert "floor_top_z" in m, "floor_top_z missing from methodology"
    assert "detected_seats" in m, "detected_seats missing from methodology"
    assert "detected_screens" in m, "detected_screens missing from methodology"
    assert "pairings" in m, "pairings missing from methodology"
    # office_room has 2 paired workstations
    assert len(m["pairings"]) == 2
    assert all(pr["screen"] is not None for pr in m["pairings"])
    assert len(m["detected_seats"]) == 2
    assert len(m["detected_screens"]) == 2
    assert isinstance(m["floor_top_z"], float)


def test_no_unpaired_screen_warning_on_office_room(tmp_path):
    """office_room has all screens paired — no unpaired-screen warning should appear."""
    r = _call(obj_path=OBJ, sidecar=SIDE, work_dir=str(tmp_path))
    unpaired_warnings = [w for w in r["warnings"] if "no matching seat suffix" in w]
    assert unpaired_warnings == [], f"Unexpected unpaired-screen warning: {unpaired_warnings}"


def test_unpaired_screen_produces_warning(tmp_path):
    """When a screen has no matching seat suffix, a warning is emitted."""
    import json, os
    # Use a screen_pattern that matches something in office_room but a seat_pattern that
    # matches nothing — so detected_screens is non-empty but no seat pairs them.
    r = _call(obj_path=OBJ, sidecar=SIDE, work_dir=str(tmp_path),
              seat_pattern=r"(?i)__nomatch__",
              screen_pattern=r"(?i)disp.*panel|screen|monitor|display")
    # No seats found => pairings is empty, screens are still detected
    # (detect_workstations returns them under detected_screens)
    m = r["methodology"]
    # With no seats, build_observers falls back to position_fallback (room_center path);
    # detected_screens has entries but pairings=[] => all screens are unpaired
    if m["detected_screens"]:
        warning_msgs = [w for w in r["warnings"] if "no matching seat suffix" in w]
        assert warning_msgs, (
            "Expected unpaired-screen warning when screens exist but no seat pairs them; "
            f"got warnings={r['warnings']!r}"
        )


def test_unpaired_seat_warning_counts_distinct_seats(tmp_path):
    """The unpaired-seat warning must count distinct seats, not observer rows.

    Regression: with sweep_n>1 and/or a list eye_height, each unpaired seat emits
    many observer rows (seats x sweep dirs x eye heights). The warning must still
    report the number of seats, not the inflated row count.
    """
    r = _call(obj_path=OBJ, sidecar=SIDE, work_dir=str(tmp_path),
              screen_pattern=r"(?i)__nomatch__",
              direction_fallback="sweep", sweep_n=8,
              eye_height=[1.2, 1.6])
    # office_room has 2 seats; with no screen matches both are unpaired and use the
    # sweep fallback => 2 seats * 8 sweep dirs * 2 eye heights = 32 observer rows.
    assert len(r["observers"]) > 2, "expected fallback rows to be multiplied"
    seat_warnings = [w for w in r["warnings"] if "had no paired screen" in w]
    assert seat_warnings, f"expected an unpaired-seat warning; got {r['warnings']!r}"
    assert seat_warnings[0].startswith("2 seat(s) "), seat_warnings[0]


def test_three_element_eye_warns_z_ignored(tmp_path):
    """B4: a 3-element workstation eye silently drops its Z (eye Z = floor-top + eye_height).
    The tool must surface a warning that the supplied Z was ignored."""
    r = _call(obj_path=OBJ, sidecar=SIDE, work_dir=str(tmp_path),
              workstations=[{"eye": [0.0, 0.0, 5.0], "target": [0.0, 3.5]}])
    assert len(r["observers"]) == 1
    # eye Z is governed by floor-top + eye_height (1.2), NOT the supplied 5.0
    assert abs(r["observers"][0]["eye"][2] - 1.2) < 1e-6
    z_warnings = [w for w in r["warnings"] if "z" in w.lower()]
    assert z_warnings, f"expected a warning that the supplied eye Z is ignored; got {r['warnings']!r}"


def test_three_element_target_warns_z_ignored(tmp_path):
    """B4 sibling: a 3-element workstation target also silently drops its Z (gaze is horizontal);
    the tool must warn about that too."""
    r = _call(obj_path=OBJ, sidecar=SIDE, work_dir=str(tmp_path),
              workstations=[{"eye": [0.0, 0.0], "target": [0.0, 3.5, 9.0]}])
    assert len(r["observers"]) == 1
    assert r["observers"][0]["direction"][2] == 0          # gaze forced horizontal
    tgt_warnings = [w for w in r["warnings"] if "target" in w.lower()]
    assert tgt_warnings, f"expected a warning about the dropped target Z; got {r['warnings']!r}"
