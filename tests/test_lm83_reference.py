"""The LM-83 engine against an independent ray trace, hour by hour.

Every earlier live test of this engine asked whether its output was plausible: non-zero,
brighter near the window, darker under a darker blind. All of that held while the engine was
wrong by a factor of 2 to 30, because five separate defects each produced a well-formed,
plausible matrix (review 2026-11-26):

  1. the sky receiver's up vector was parallel to the dome's axis, so every sky patch of one
     altitude band collapsed onto the patch due north -- the window never saw the sun;
  2. Klems matrices were scaled by solid angle where Radiance weights by PROJECTED solid angle,
     so a matrix declared at 64 % transmitted 32 %;
  3. the sun was in no sky matrix and was never added, so sDA was computed without it;
  4. the direct-sun pass laid a second pane of 100 % transmission over the real glazing;
  5. a closed blind replaced the glazing instead of standing behind it.

Plausibility cannot catch these. Agreement with a second, unrelated calculation can: `rtrace`
against a `gendaylit` sky, with the real glass, shares nothing with the matrix chain but the
room and the weather.

Tolerances are wide on purpose. The matrix method resolves direction to a Klems bin and the
glazing matrix has no angular dependence (a recorded departure), which together cost 10-30 %.
A defect of the kinds above costs a factor.
"""
import os
import shutil
import subprocess

import pytest

from hcl_radiance.geometry_import import import_geometry
from hcl_radiance.geometry_obj import parse_obj
from hcl_radiance.lm83_run import _read_lux, plan_lm83, state_illuminance
from hcl_radiance.runner import run_sequence
from test_lm83_tool import _MAP, _OBJ

pytestmark = pytest.mark.skipif(
    any(shutil.which(tool) is None for tool in ("rfluxmtx", "dctimestep", "rtrace", "gendaylit")),
    reason="Radiance not installed")

LAT, LON_WEST, MERIDIAN_WEST = 37.9, -23.7, -30.0
#: month, day, hour, direct normal, diffuse horizontal (W/m2)
HOURS = {"overcast": (12, 21, 10.5, 0, 150),
         "winter_noon_sun": (12, 21, 12.5, 850, 100),
         "equinox_morning_sun": (3, 21, 9.5, 600, 150)}
POINTS = [[x, y, 0.8, 0.0, 0.0, 1.0] for y in (0.6, 1.8, 3.0) for x in (1.0, 2.0, 3.0)]
BLIND_VLT = 0.05

_SKY_TAIL = ("\nskyfunc glow skyglow\n0\n0\n4 1 1 1 0\nskyglow source sky\n0\n0\n4 0 0 1 180\n"
             "skyfunc glow groundglow\n0\n0\n4 1 1 1 0\ngroundglow source ground\n0\n0\n4 0 0 -1 180\n")
#: A sheet just inside the glazing, larger than the opening, that transmits BLIND_VLT
#: diffusely and reflects nothing -- the same thing the engine's default blind matrix states.
_BLIND_SHEET = (f"void trans blind\n0\n0\n7 {BLIND_VLT} {BLIND_VLT} {BLIND_VLT} 0 0 1 0\n"
                "blind polygon sheet\n0\n0\n12  0.9 0.02 0.7  3.1 0.02 0.7  3.1 0.02 2.4  0.9 0.02 2.4\n")


def _lux(rgb):
    return 179.0 * (0.265 * rgb[0] + 0.670 * rgb[1] + 0.065 * rgb[2])


def _mean(values):
    return sum(values) / len(values)


def _gendaylit(hour):
    month, day, clock, dni, dhi = hour
    return subprocess.run(["gendaylit", str(month), str(day), str(clock), "-W", str(dni), str(dhi),
                           "-a", str(LAT), "-o", str(LON_WEST), "-m", str(MERIDIAN_WEST)],
                          capture_output=True, text=True).stdout


def _sun_only(sky_text):
    """Just gendaylit's solar source: the direct beam, no sky and no ground."""
    lines = sky_text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith("void light solar")), None)
    if start is None:
        return ""
    end = next(i for i in range(start, len(lines)) if lines[i].startswith("void brightfunc"))
    return "\n".join(lines[start:end]) + "\n"


def _rtrace(work, name, scene_files, sky_text, ambient):
    sky = os.path.join(work, name + "_sky.rad")
    with open(sky, "w") as fh:
        fh.write(sky_text)
    octree = os.path.join(work, name + ".oct")
    with open(octree, "wb") as fh:
        subprocess.run(["oconv", *scene_files, sky], stdout=fh, check=True, cwd=work)
    points = "".join(" ".join(f"{v:g}" for v in p) + "\n" for p in POINTS)
    out = subprocess.run(["rtrace", "-h", "-I", *ambient, "-dc", "1", "-dt", "0", "-dj", "0", octree],
                         input=points, capture_output=True, text=True, cwd=work)
    return [_lux([float(v) for v in line.split()[:3]]) for line in out.stdout.strip().splitlines()]


@pytest.fixture(scope="module")
def room(tmp_path_factory):
    """Build the room once; run the engine once; ray-trace the references once."""
    work = str(tmp_path_factory.mktemp("lm83_reference"))
    obj = os.path.join(work, "room.obj")
    with open(obj, "w") as fh:
        fh.write(_OBJ)
    wea = os.path.join(work, "t.wea")
    with open(wea, "w") as fh:
        fh.write(f"place ATHENS_GRC\nlatitude {LAT}\nlongitude {LON_WEST}\n"
                 f"time_zone {MERIDIAN_WEST:g}\nsite_elevation 28.0\nweather_data_file_units 1\n")
        for month, day, clock, dni, dhi in HOURS.values():
            fh.write(f"{month} {day} {clock} {dni} {dhi}\n")
    pts = os.path.join(work, "points.pts")
    with open(pts, "w") as fh:
        fh.write("".join(" ".join(f"{v:g}" for v in p) + "\n" for p in POINTS))

    scene = import_geometry(obj, material_map=_MAP, units="m", up_axis="Z", channel_type=0,
                            work_dir=work, run=True)
    materials, geometry = scene["material_sets"][0], scene["geometry_set"][0]

    engine_dir = os.path.join(work, "engine")
    os.makedirs(engine_dir)
    plan = plan_lm83({"materials": materials, "geometry": geometry, "exterior": [],
                      "sky_color": [1, 1, 1]},
                     parse_obj(_OBJ), _MAP, wea, pts, len(POINTS), work_dir=engine_dir,
                     v_params="-ab 5 -ad 10000 -lw 1e-5", interior_point=(2.0, 1.8, 0.8))
    assert "error" not in plan, plan
    ran = run_sequence(plan["steps"], engine_dir, True)
    assert ran.get("returncode") == 0, ran
    by_state = state_illuminance(plan, engine_dir)
    all_closed = max(by_state, key=len)

    # -lw matters: behind a 5 % blind an ambient ray's weight is already ~1e-5, and a cut-off
    # at 1e-4 silently drops it (the closed-blind reference then reads 40 % low).
    high = ["-ab", "5", "-ad", "4096", "-as", "1024", "-aa", "0", "-lw", "1e-6"]
    sheet = os.path.join(work, "blind_sheet.rad")
    with open(sheet, "w") as fh:
        fh.write(_BLIND_SHEET)
    reference = {"open": [], "closed": [], "direct": []}
    for name, hour in HOURS.items():
        sky = _gendaylit(hour)
        reference["open"].append(_rtrace(work, f"open_{name}", [*materials, geometry],
                                         sky + _SKY_TAIL, high))
        reference["closed"].append(_rtrace(work, f"closed_{name}", [*materials, geometry, sheet],
                                           sky + _SKY_TAIL, high))
        reference["direct"].append(_rtrace(work, f"direct_{name}", [*materials, geometry],
                                           _sun_only(sky), ["-ab", "0"]))

    def by_hour(series):                       # engine matrices are [point][hour]
        return [[series[p][t] for p in range(len(POINTS))] for t in range(len(HOURS))]

    return {"hours": list(HOURS),
            "engine": {"open": by_hour(by_state[frozenset()]),
                       "closed": by_hour(by_state[all_closed]),
                       "direct": by_hour(_read_lux(plan["sun_total_ill"], engine_dir))},
            "reference": reference}


def _ratio_of_means(room, state, hour):
    t = room["hours"].index(hour)
    return _mean(room["engine"][state][t]) / _mean(room["reference"][state][t])


@pytest.mark.parametrize("hour", list(HOURS))
def test_blinds_open_the_room_is_as_bright_as_a_ray_trace_says(room, hour):
    assert 0.70 <= _ratio_of_means(room, "open", hour) <= 1.40


@pytest.mark.parametrize("hour", list(HOURS))
def test_blinds_open_the_same_points_reach_300_lux(room, hour):
    """sDA is a count of points over a threshold, so the count is what has to agree."""
    t = room["hours"].index(hour)
    over = {who: sum(1 for v in room[who]["open"][t] if v >= 300.0) for who in ("engine", "reference")}
    assert abs(over["engine"] - over["reference"]) <= 1, over


def test_blinds_open_the_light_falls_off_from_the_window_as_a_ray_trace_says(room):
    """Glass keeps the direction of the light: bright under the sky near the window, dim at
    the back, which sees only the sky near the horizon. A glazing matrix that scatters lights
    the room as if the window itself glowed -- the right total, spread too evenly, and a mean
    over the grid does not notice. Overcast hour, so no sun patch decides the answer."""
    t = room["hours"].index("overcast")

    def front_over_back(who):
        values = room[who]["open"][t]                 # 3 rows of 3 points, window row first
        return _mean(values[:3]) / _mean(values[-3:])

    reference = front_over_back("reference")
    assert reference > 3, "the fixture no longer has a gradient to speak of"
    assert 0.75 * reference <= front_over_back("engine") <= 1.30 * reference


@pytest.mark.parametrize("hour", list(HOURS))
def test_blinds_closed_the_light_that_still_gets_through_matches_a_ray_trace(room, hour):
    """A closed blind stands BEHIND the glazing and still passes its share of the sun's light,
    diffused. On a sunny hour that is most of what is left in the room."""
    assert 0.65 <= _ratio_of_means(room, "closed", hour) <= 1.45


def test_a_sunny_hour_stays_far_brighter_than_an_overcast_one_behind_the_closed_blind(room):
    """The sun on the facade outweighs the sky many times over, and a diffusing blind passes
    the same share of both. An engine that forgets the sun shows no such contrast."""
    overcast = _mean(room["engine"]["closed"][room["hours"].index("overcast")])
    sunny = _mean(room["engine"]["closed"][room["hours"].index("winter_noon_sun")])
    reference = (_mean(room["reference"]["closed"][room["hours"].index("winter_noon_sun")])
                 / _mean(room["reference"]["closed"][room["hours"].index("overcast")]))
    assert reference > 5, "the fixture no longer puts the sun on the window"
    assert 0.6 * reference <= sunny / overcast <= 1.6 * reference


@pytest.mark.parametrize("hour", ["winter_noon_sun", "equinox_morning_sun"])
def test_the_direct_sun_pass_sees_the_beam_through_the_real_glazing(room, hour):
    """This series decides ASE and the blind trigger. Compared where the beam actually lands,
    as a sum over the grid, so a patch edge falling between two points does not decide it."""
    t = room["hours"].index(hour)
    engine, reference = sum(room["engine"]["direct"][t]), sum(room["reference"]["direct"][t])
    assert reference > 1000, "the fixture no longer puts direct sun on the grid"
    assert 0.75 <= engine / reference <= 1.30


def test_without_sun_the_direct_sun_pass_reads_nothing(room):
    t = room["hours"].index("overcast")
    assert max(room["engine"]["direct"][t]) < 1.0


# ---- two window groups: whose sun is it? ----

def test_each_window_group_is_credited_with_its_own_sun_only(tmp_path):
    """Equinox morning: the sun stands in the south-east. It comes through the south window
    and cannot come through the west one. With every pane in the room geometry and a clear
    pane laid over each group, both groups used to report the whole model's sun -- so closing
    either blind 'removed' beam it had never admitted."""
    from test_lm83_plan import TWO_WINDOW_MAP, TWO_WINDOW_OBJ

    work = str(tmp_path)
    obj = os.path.join(work, "room.obj")
    with open(obj, "w") as fh:
        fh.write(TWO_WINDOW_OBJ)
    wea = os.path.join(work, "t.wea")
    month, day, clock, dni, dhi = HOURS["equinox_morning_sun"]
    with open(wea, "w") as fh:
        fh.write(f"place ATHENS_GRC\nlatitude {LAT}\nlongitude {LON_WEST}\n"
                 f"time_zone {MERIDIAN_WEST:g}\nsite_elevation 28.0\nweather_data_file_units 1\n"
                 f"{month} {day} {clock} {dni} {dhi}\n")
    pts = os.path.join(work, "points.pts")
    with open(pts, "w") as fh:
        fh.write("".join(" ".join(f"{v:g}" for v in p) + "\n" for p in POINTS))
    scene = import_geometry(obj, material_map=TWO_WINDOW_MAP, units="m", up_axis="Z",
                            channel_type=0, work_dir=work, run=True)
    engine_dir = os.path.join(work, "engine")
    os.makedirs(engine_dir)
    plan = plan_lm83({"materials": scene["material_sets"][0], "geometry": scene["geometry_set"][0],
                      "exterior": [], "sky_color": [1, 1, 1]},
                     parse_obj(TWO_WINDOW_OBJ), TWO_WINDOW_MAP, wea, pts, len(POINTS),
                     work_dir=engine_dir, v_params="-ab 1 -ad 500", interior_point=(2.0, 1.8, 0.8))
    assert run_sequence(plan["steps"], engine_dir, True).get("returncode") == 0
    by_azimuth = {round(g["azimuth_deg"]): g["name"] for g in plan["window_groups"]}
    total = sum(row[0] for row in _read_lux(plan["sun_total_ill"], engine_dir))
    south = sum(row[0] for row in _read_lux(plan["sun_ill"][by_azimuth[180]], engine_dir))
    west = sum(row[0] for row in _read_lux(plan["sun_ill"][by_azimuth[270]], engine_dir))
    assert total > 1000, "the fixture no longer puts direct sun on the grid"
    assert west < 0.01 * total
    assert south == pytest.approx(total, rel=0.02)


# ---- second review 2026-11-26: the sky matrix is the right way round ----

def test_the_morning_sun_lights_an_east_wall_not_a_west_one(tmp_path):
    """The sky receiver's `u=` vector decides where azimuth 0 is. `u=+Z` lost azimuth altogether;
    `u=-Y` would keep it and mirror it, putting the morning sun in the west. A room with one
    south window cannot tell those apart, so this asks the receiver itself: four upright
    sensors in the open, facing east, south, west and north, at 9:30 on the equinox."""
    from hcl_radiance.threephase_commands import (build_gendaymtx_sky_mf, build_rmtxop_photopic,
                                                  sky_receiver_rad)
    work = str(tmp_path)
    with open(os.path.join(work, "sky_receiver.rad"), "w") as fh:
        fh.write(sky_receiver_rad(4))
    with open(os.path.join(work, "t.wea"), "w") as fh:
        fh.write("place ATHENS_GRC\nlatitude 37.9\nlongitude -23.7\ntime_zone -30\n"
                 "site_elevation 28.0\nweather_data_file_units 1\n3 21 9.5 700 100\n")
    facing = {"east": (1, 0, 0), "south": (0, -1, 0), "west": (-1, 0, 0), "north": (0, 1, 0)}
    with open(os.path.join(work, "pts"), "w") as fh:
        fh.write("".join(f"0 0 1 {x} {y} {z}\n" for x, y, z in facing.values()))

    def run(cmd, stdin=None, stdout=None):
        with open(os.path.join(work, stdout), "wb") as out:
            subprocess.run(cmd, cwd=work, check=True, stdout=out,
                           stdin=open(os.path.join(work, stdin)) if stdin else None)

    run(["rfluxmtx", "-I+", "-y", "4", "-ab", "1", "-ad", "20000", "-lw", "1e-6",
         "-", "sky_receiver.rad"], stdin="pts", stdout="dc.mtx")
    run(build_gendaymtx_sky_mf("t.wea", [1, 1, 1], mf=4, sun=True), stdout="skysun.smx")
    with open(os.path.join(work, "lux.txt"), "wb") as out:
        first = subprocess.Popen(["dctimestep", "dc.mtx", "skysun.smx"], cwd=work,
                                 stdout=subprocess.PIPE)
        subprocess.run(build_rmtxop_photopic(), cwd=work, check=True, stdin=first.stdout,
                       stdout=out)
        first.wait()
    lux = dict(zip(facing, (row[0] for row in _read_lux("lux.txt", work))))
    assert lux["east"] > 3 * lux["west"], lux
    assert lux["south"] > 3 * lux["north"], lux
    assert lux["east"] > 20000, lux                       # it is the sun, not a bright patch of sky
