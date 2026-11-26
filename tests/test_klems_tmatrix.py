import math
import shutil
import subprocess
import pytest
from hcl_core.klems import (KLEMS_BASIS_NAME, clear_glazing_tmatrix,
                            klems_projected_solid_angles, lm83_default_blind, scale_tmatrix,
                            uniform_diffuse_tmatrix, write_klems_xml)


def test_unknown_shade_defaults_to_five_percent_diffuse():
    """2.2.7: 'If the shade VLT is unknown, model the shade using 5% diffuse VLT with no
    specular transmittance.' NOT 20% -- that is the white-louver branch."""
    d = lm83_default_blind()
    assert d["diffuse_vlt"] == 0.05
    assert d["specular"] == 0.0
    assert d["source"] == "lm83_2_2_7_unknown_shade"


def test_white_louver_branch_needs_an_explicit_reflectance():
    """2.2.7 gates 20% on '>80% reflectance'. Defaulting it lets the no-knowledge case
    resolve upward to 20% -- a fourfold overstatement of transmitted flux."""
    with pytest.raises(ValueError, match="explicit reflectance"):
        lm83_default_blind("louver")
    assert lm83_default_blind("louver", reflectance=0.85)["diffuse_vlt"] == 0.20


def test_louver_vlt_depreciates_to_a_ten_percent_floor():
    # 2.2.7's anchors: 40% refl -> 15% VLT, 60% -> 17.5%, black -> 10%.
    assert math.isclose(lm83_default_blind("louver", reflectance=0.40)["diffuse_vlt"], 0.15)
    assert math.isclose(lm83_default_blind("louver", reflectance=0.60)["diffuse_vlt"], 0.175)
    assert math.isclose(lm83_default_blind("louver", reflectance=0.0)["diffuse_vlt"], 0.10)


def test_fabric_with_known_vlt_and_openness_splits_specular_from_diffuse():
    """2.2.7: specular = openness factor; diffuse = VLT minus the openness factor."""
    d = lm83_default_blind("fabric", vlt=0.10, openness=0.03)
    assert math.isclose(d["specular"], 0.03)
    assert math.isclose(d["diffuse_vlt"], 0.07)


def test_fabric_with_unknown_openness_is_all_diffuse():
    d = lm83_default_blind("fabric", vlt=0.10)
    assert math.isclose(d["diffuse_vlt"], 0.10) and d["specular"] == 0.0


def test_fabric_with_unknown_vlt_falls_back_to_five_percent():
    assert lm83_default_blind("fabric")["diffuse_vlt"] == 0.05


def test_openness_exceeding_vlt_is_rejected():
    with pytest.raises(ValueError, match="exceeds"):
        lm83_default_blind("fabric", vlt=0.05, openness=0.10)


def test_matrix_is_145_by_145():
    t = uniform_diffuse_tmatrix(0.05)
    assert len(t) == 145 and all(len(row) == 145 for row in t)


def _transmitted(matrix, incident_bin):
    """Share of the light arriving in one Klems bin that a matrix lets through.

    A BTDF is per steradian and Radiance integrates it over PROJECTED solid angle (the bin's
    solid angle times the cosine of its direction; the 145 of them sum to pi, not 2 pi).
    Weighting by plain solid angle instead is what once made every matrix transmit half of
    what it declared -- and the tests of the day asserted exactly that wrong sum.
    """
    weights = klems_projected_solid_angles()
    return sum(matrix[out][incident_bin] * weights[out] for out in range(145))


def test_projected_solid_angles_cover_the_hemisphere():
    weights = klems_projected_solid_angles()
    assert len(weights) == 145
    assert math.isclose(sum(weights), math.pi, rel_tol=1e-9)


@pytest.mark.parametrize("incident_bin", [0, 5, 40, 100, 144])
def test_a_diffuse_matrix_transmits_the_vlt_it_was_given(incident_bin):
    assert math.isclose(_transmitted(uniform_diffuse_tmatrix(0.05), incident_bin), 0.05,
                        rel_tol=1e-9)


@pytest.mark.parametrize("incident_bin", [0, 5, 40, 100, 144])
def test_diffuse_and_openness_together_transmit_the_shades_true_vlt(incident_bin):
    """Callers pass the diffuse part and the openness factor separately; from EVERY direction
    the two must add up to the shade's real VLT. Checked at steep bins too: an openness term
    divided by plain solid angle is right at normal incidence and loses a cosine elsewhere."""
    matrix = uniform_diffuse_tmatrix(0.07, specular=0.03)
    assert math.isclose(_transmitted(matrix, incident_bin), 0.10, rel_tol=1e-9)


def test_every_row_is_uniform_and_carries_the_right_magnitude():
    """Not merely 'constant' -- a constant of the WRONG value would pass that alone.
    A perfect diffuser of transmittance v has BTDF v / pi."""
    t = uniform_diffuse_tmatrix(0.05)
    expected = 0.05 / math.pi
    for row in t:
        assert len(set(round(v, 12) for v in row)) == 1
        assert math.isclose(row[0], expected, rel_tol=1e-12)


def test_specular_component_adds_a_forward_peak():
    t = uniform_diffuse_tmatrix(0.07, specular=0.03)
    assert t[0][0] > t[0][1]
    assert t[40][40] > t[40][0]


@pytest.mark.parametrize("incident_bin", [0, 5, 40, 100, 144])
def test_clear_glazing_passes_its_tvis_and_keeps_the_direction(incident_bin):
    """Glass does not scatter. Its matrix sends each incident bin to the SAME outgoing bin, so
    a point deep in the room still sees the sky near the horizon and a point at the window
    the sky overhead. A diffusing 'glazing' lights the whole room as if the window glowed."""
    matrix = clear_glazing_tmatrix(0.64)
    assert math.isclose(_transmitted(matrix, incident_bin), 0.64, rel_tol=1e-9)
    assert all(matrix[out][incident_bin] == 0.0 for out in range(145) if out != incident_bin)


def test_a_layer_behind_another_multiplies_the_transmittance():
    """A closed blind stands behind the glazing: 5 % of 64 %, not 5 %."""
    behind_glass = scale_tmatrix(uniform_diffuse_tmatrix(0.05), 0.64)
    assert math.isclose(_transmitted(behind_glass, 40), 0.05 * 0.64, rel_tol=1e-9)


def test_rejects_an_out_of_range_vlt():
    with pytest.raises(ValueError, match=r"0\.\.1"):
        uniform_diffuse_tmatrix(1.5)


def test_writes_the_basis_name_dctimestep_matches_on(tmp_path):
    path = write_klems_xml(clear_glazing_tmatrix(0.64), str(tmp_path / "t.xml"),
                           name="clear")
    text = open(path).read()
    assert KLEMS_BASIS_NAME in text
    assert "<AngleBasisBlock>" in text
    assert "<ThetaBounds>" in text


def test_writes_all_three_data_blocks(tmp_path):
    """A file carrying only Transmission Front parses as XML but dctimestep rejects it."""
    text = open(write_klems_xml(clear_glazing_tmatrix(0.64), str(tmp_path / "t.xml"),
                                name="clear")).read()
    for direction in ("Transmission Front", "Reflection Front", "Reflection Back"):
        assert direction in text


def test_payload_is_a_full_145_squared_per_block(tmp_path):
    text = open(write_klems_xml(clear_glazing_tmatrix(0.64), str(tmp_path / "t.xml"),
                                name="clear")).read()
    assert text.count(",") == 3 * 145 * 145


def test_rejects_a_wrongly_shaped_matrix(tmp_path):
    with pytest.raises(ValueError, match="expected 145 rows"):
        write_klems_xml([[0.0] * 145] * 12, str(tmp_path / "bad.xml"), name="bad")


@pytest.mark.skipif(shutil.which("dctimestep") is None, reason="Radiance not installed")
def test_dctimestep_accepts_the_xml_we_generate(tmp_path):
    """The test that matters: a hand-rolled XML can satisfy every assertion above and
    still die at multiply time with 'Empty BSDF matrix request'. Only Radiance can say."""
    xml = write_klems_xml(clear_glazing_tmatrix(0.64), str(tmp_path / "t.xml"),
                          name="clear")
    # A 1x145 V and a 145x2 D make the smallest multiply that exercises the BSDF.
    v = tmp_path / "v.mtx"
    v.write_text("#?RADIANCE\nNCOMP=3\nNROWS=1\nNCOLS=145\nFORMAT=ascii\n\n"
                 + "\t".join(["1 1 1"] * 145) + "\n")
    d = tmp_path / "d.mtx"
    d.write_text("#?RADIANCE\nNCOMP=3\nNROWS=145\nNCOLS=2\nFORMAT=ascii\n\n"
                 + "\n".join(["1 1 1\t1 1 1"] * 145) + "\n")
    s = tmp_path / "s.smx"
    s.write_text("#?RADIANCE\nNCOMP=3\nNROWS=2\nNCOLS=1\nFORMAT=ascii\n\n"
                 "1 1 1\n1 1 1\n")
    res = subprocess.run(["dctimestep", str(v), xml, str(d), str(s)],
                         capture_output=True, text=True)
    assert res.returncode == 0, f"dctimestep rejected our BSDF: {res.stderr.strip()}"
    assert "Empty BSDF" not in res.stderr


# ---- what Radiance itself makes of the file we write ----

_needs_rtrace = pytest.mark.skipif(shutil.which("rtrace") is None or shutil.which("oconv") is None,
                                   reason="Radiance not installed")


#: One reading is one Monte Carlo sample of the sheet: measured spread 0.281-0.316 for a true
#: 0.30, wider than the test's 6 % band, so the test failed about one full run in three. The
#: mean of 64 readings of the same point holds within 1 %.
_REPEATS = 64


def _irradiance_below_a_sheet(tmp_path, xml, light):
    """Irradiance just under a 1 km sheet of the BSDF in `xml` (None: no sheet), lit by `light`."""
    scene = tmp_path / "scene.rad"
    sheet = ("" if xml is None else
             f"void BSDF sheet\n6 0 {xml} 0 1 0 .\n0\n0\n"
             "sheet polygon p\n0\n0\n12 -500 -500 0  500 -500 0  500 500 0  -500 500 0\n")
    scene.write_text(light + sheet)
    octree = tmp_path / "scene.oct"
    with open(octree, "wb") as fh:
        subprocess.run(["oconv", str(scene)], stdout=fh, check=True)
    out = subprocess.run(["rtrace", "-h", "-I", "-ab", "3", "-ad", "40000", "-lw", "1e-6", "-aa", "0",
                          "-dc", "1", "-dt", "0", "-dj", "0", str(octree)],
                         input="0 0 -0.01 0 0 1\n" * _REPEATS, capture_output=True, text=True)
    readings = [float(line.split()[0]) for line in out.stdout.strip().splitlines()]
    assert len(readings) == _REPEATS, out.stderr
    return sum(readings) / _REPEATS


_UNIFORM_SKY = "void glow skyglow\n0\n0\n4 1 1 1 0\nskyglow source sky\n0\n0\n4 0 0 1 180\n"


@_needs_rtrace
@pytest.mark.parametrize("vlt", [0.05, 0.64])
def test_radiance_measures_the_declared_transmittance_through_a_diffuse_matrix(tmp_path, vlt):
    """The arbiter of the normalisation is the program that reads the file. Under a uniform
    sky, a sheet declared at `vlt` must leave `vlt` of the open-sky irradiance beneath it."""
    xml = write_klems_xml(uniform_diffuse_tmatrix(vlt), str(tmp_path / "t.xml"), name="t")
    ratio = (_irradiance_below_a_sheet(tmp_path, xml, _UNIFORM_SKY)
             / _irradiance_below_a_sheet(tmp_path, None, _UNIFORM_SKY))
    assert math.isclose(ratio, vlt, rel_tol=0.03)


@_needs_rtrace
@pytest.mark.parametrize("off_normal_deg", [0, 60])
def test_radiance_measures_the_openness_factor_at_any_sun_angle(tmp_path, off_normal_deg):
    """A shade with 30 % openness passes 30 % of a beam, steep or not."""
    angle = math.radians(off_normal_deg)
    beam = ("void light sun\n0\n0\n3 1000 1000 1000\n"
            f"sun source s\n0\n0\n4 {math.sin(angle)} 0 {math.cos(angle)} 0.5\n")
    xml = write_klems_xml(uniform_diffuse_tmatrix(0.0, specular=0.30), str(tmp_path / "t.xml"),
                          name="t")
    ratio = (_irradiance_below_a_sheet(tmp_path, xml, beam)
             / _irradiance_below_a_sheet(tmp_path, None, beam))
    assert math.isclose(ratio, 0.30, rel_tol=0.06)
