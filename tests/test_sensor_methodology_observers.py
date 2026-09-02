import os
from hcl_radiance.geometry_obj import parse_obj
from hcl_radiance.sensor_methodology import detect_workstations, build_observers

OBJ = os.path.join(os.path.dirname(__file__), "fixtures", "office_room.obj")
MAP = {"Rad_Floor_R020": {"type": "floor", "refl": 0.2},
       "Rad_Wall_R050": {"type": "plastic", "refl": 0.5},
       "Rad_Glazing_T073": {"type": "glass", "tvis": 0.73}}
SEAT = r"(?i)chair.*seat|seat"
SCREEN = r"(?i)disp.*panel|screen|monitor|display"

def _p():
    with open(OBJ) as fh:
        return parse_obj(fh.read())

def test_detects_two_paired_workstations():
    pairings, seats, screens = detect_workstations(_p(), SEAT, SCREEN)
    assert len(pairings) == 2
    assert all(pr["screen"] is not None for pr in pairings)

def test_observer_directions_point_at_screens():
    obs = build_observers(_p(), MAP, 1.0, "Z", eye_height=1.2,
                          seat_pattern=SEAT, screen_pattern=SCREEN)
    dirs = sorted([round(o["direction"][0]) for o in obs])
    assert dirs == [-1, 1]                       # (-1,0,0) and (+1,0,0)
    assert all(abs(o["eye"][2] - 1.2) < 1e-6 and o["direction"][2] == 0 for o in obs)
    assert all(o["source"] == "workstation" for o in obs)

def test_eye_height_list_doubles_observers():
    obs = build_observers(_p(), MAP, 1.0, "Z", eye_height=[1.2, 1.6],
                          seat_pattern=SEAT, screen_pattern=SCREEN)
    assert len(obs) == 4

def test_window_fallback_when_no_screen():
    obs = build_observers(_p(), MAP, 1.0, "Z", eye_height=1.2,
                          seat_pattern=SEAT, screen_pattern=r"(?i)__nomatch__")
    assert len(obs) == 2
    assert all(o["source"] == "fallback:window" for o in obs)
    # window is on +Y (y~3.575); both eyes are south of it -> gaze has +y component
    assert all(o["direction"][1] > 0 for o in obs)

def test_sweep_fallback_cardinality():
    obs = build_observers(_p(), MAP, 1.0, "Z", eye_height=1.2,
                          seat_pattern=SEAT, screen_pattern=r"(?i)__nomatch__",
                          direction_fallback="sweep", sweep_n=8)
    assert len(obs) == 2 * 8
    assert all(o["source"].startswith("fallback:sweep") for o in obs)

def test_no_seats_uses_room_center():
    obs = build_observers(_p(), MAP, 1.0, "Z", eye_height=1.2,
                          seat_pattern=r"(?i)__nomatch__", screen_pattern=SCREEN,
                          interior=(-2.0, 2.0, -3.5, 3.5))
    assert len(obs) == 1
    assert abs(obs[0]["eye"][0]) < 1e-6 and abs(obs[0]["eye"][1]) < 1e-6   # room centre


def test_explicit_workstation_no_target_no_azimuth_yields_fallback_source():
    """Fix #3: targetless/azimuthless explicit workstation must emit a 'fallback:' source, not 'explicit'."""
    obs = build_observers(_p(), MAP, 1.0, "Z", eye_height=1.2,
                          workstations=[{"eye": [0, 0]}])
    assert len(obs) == 1
    src = obs[0]["source"]
    assert src.startswith("fallback:"), (
        f"Expected source starting with 'fallback:' for explicit entry with no target/azimuth; got {src!r}"
    )


def test_explicit_workstation_eye_equals_target_no_zero_direction():
    """A1: when eye == target the gaze is degenerate; the emitted direction must still be a
    non-zero vector (Radiance rtrace requires a non-zero direction; [0,0,0] is undefined)."""
    obs = build_observers(_p(), MAP, 1.0, "Z", eye_height=1.2,
                          workstations=[{"eye": [0.0, 0.0], "target": [0.0, 0.0]}])
    assert len(obs) == 1
    d = obs[0]["direction"]
    mag = (d[0] ** 2 + d[1] ** 2 + d[2] ** 2) ** 0.5
    assert mag > 1e-9, f"degenerate gaze produced a zero-direction vector: {d}"
