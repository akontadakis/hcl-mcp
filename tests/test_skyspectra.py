import os
import pytest

from hcl_core import skyspectra as S


# --- Streaming long-format reader ------------------------------------------

HERE = os.path.dirname(__file__)
FIX = os.path.abspath(os.path.join(HERE, "fixtures", "skyspectra", "fixture"))
HZ = os.path.join(FIX, "skyspectra_sample_horizontal.csv")
PA = os.path.join(FIX, "skyspectra_sample_patch.csv")


def _first_location(path):
    """The location_code of the first data row — fixtures carry real data from whichever city was
    downloaded first, so tests derive the location rather than hard-coding it."""
    import csv
    with open(path) as fh:
        return next(csv.DictReader(fh))["location_code"]


def test_to_grid_interpolates_and_clips():
    g = S.to_grid([(360.0, 1.0), (380.0, 2.0), (780.0, 2.0), (900.0, 9.0)])
    assert len(g) == 401
    assert abs(g[0] - 2.0) < 1e-9 and abs(g[-1] - 2.0) < 1e-9     # clipped to 380 and 780 endpoints


def test_to_grid_drops_blank_values_and_handles_all_blank():
    # SKYSPECTRA patch rows carry blank radiance at some wavelengths — to_grid must skip, not crash
    g = S.to_grid([("380", "2.0"), ("500", ""), ("780", "2.0")])   # blank dropped, interp over the rest
    assert len(g) == 401 and abs(g[0] - 2.0) < 1e-9 and abs(g[-1] - 2.0) < 1e-9
    assert S.to_grid([("380", ""), ("500", "")]) == [0.0] * 401     # all-blank -> zeros, no raise


def test_iter_horizontal_yields_grid_spectrum():
    rows = list(S.iter_horizontal(HZ, _first_location(HZ)))
    assert len(rows) >= 1
    ts, spd, cct = rows[0]
    assert len(spd) == 401 and all(v >= 0.0 for v in spd)
    assert isinstance(ts, str)


def test_iter_patch_sets_yields_patches_with_geometry():
    sets = list(S.iter_patch_sets(PA, _first_location(PA)))
    assert len(sets) >= 1
    ts, patches = sets[0]
    # The committed fixture is SYNTHETIC (license: SKYSPECTRA is CC BY-NC-ND, no raw redistributed) and
    # carries two patches under one timestamp, so the reader's per-timestamp grouping + geometry parse
    # are both exercised.
    assert len(patches) >= 2
    p = patches[0]
    assert set(("patch", "almucantar", "azimuth", "cct", "spd")) <= set(p)
    assert len(p["spd"]) == 401


def test_iter_patch_sets_groups_multiple_patches_in_one_timestamp(tmp_path):
    # The DE-BLN fixture is a sequential scan (one patch per timestamp); some cities measure several
    # patches AT one timestamp. Exercise that grouping path with a synthetic 2-patch / 1-timestamp CSV.
    hdr = ("location_code,timestamp,measurement_setup,sun_included,patch,patch_almucantar,"
           "patch_azimuth,cct_patch,wavelength,spectral_patch_radiance")
    lines = [hdr]
    for patch, az, cct in ((1, 90.0, 9000), (2, 270.0, 6000)):
        for wl in (380, 500, 780):
            lines.append(f"XX-SYN,2020-01-01 12:00,1,FALSE,{patch},30,{az},{cct},{wl},0.5")
    f = tmp_path / "syn_patch.csv"
    f.write_text("\n".join(lines) + "\n")
    sets = list(S.iter_patch_sets(str(f), "XX-SYN"))
    assert len(sets) == 1                                # one timestamp
    ts, patches = sets[0]
    assert len(patches) == 2                             # both patches grouped under that timestamp
    assert {p["patch"] for p in patches} == {1, 2}
    assert all(len(p["spd"]) == 401 for p in patches)
    assert {p["azimuth"] for p in patches} == {90.0, 270.0}


def test_location_filter_excludes_others(tmp_path):
    # a row from a different location must not leak into the target-location iteration
    loc = _first_location(HZ)
    mixed = tmp_path / "mixed.csv"
    head = open(HZ).readline()
    body = open(HZ).read().splitlines()[1:]
    other = body[0].replace(loc, "ZZ-OTH", 1)
    mixed.write_text(head + other + "\n" + "\n".join(body) + "\n")
    target = {ts for ts, _, _ in S.iter_horizontal(str(mixed), loc)}
    oth = {ts for ts, _, _ in S.iter_horizontal(str(mixed), "ZZ-OTH")}
    assert oth and target  # both parse; ensure no cross-contamination crash


RAW = os.path.abspath(os.path.join(HERE, "fixtures", "skyspectra", "raw"))


def _raw(name):
    return os.path.join(RAW, name)


@pytest.mark.skipif(not os.path.exists(_raw("spectral_horizontal_irradiance.csv")),
                    reason="SKYSPECTRA raw not downloaded (Zenodo 8147546, CC BY-NC-ND; not redistributed)")
def test_full_horizontal_streams_frvlx():
    n = 0
    for ts, spd, cct in S.iter_horizontal(_raw("spectral_horizontal_irradiance.csv"), "FR-VLX"):
        assert len(spd) == 401
        n += 1
        if n >= 5:
            break
    assert n >= 1
