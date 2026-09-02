import math
import shutil
import subprocess
import pytest
from hcl_core.klems import (KLEMS_BASIS_NAME, clear_glazing_tmatrix, klems_solid_angles,
                            lm83_default_blind, uniform_diffuse_tmatrix, write_klems_xml)


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


def test_total_transmission_equals_the_vlt():
    omega = klems_solid_angles()
    t = uniform_diffuse_tmatrix(0.05)
    assert math.isclose(sum(t[0][j] * omega[j] for j in range(145)), 0.05, rel_tol=1e-9)


def test_specular_adds_to_the_total_so_the_sum_is_the_shades_true_vlt():
    """Callers pass diffuse and openness separately; together they must integrate to the
    shade's real VLT. Testing only the specular=0 case would miss a wrong divisor."""
    omega = klems_solid_angles()
    t = uniform_diffuse_tmatrix(0.07, specular=0.03)
    assert math.isclose(sum(t[0][j] * omega[j] for j in range(145)), 0.10, rel_tol=1e-9)


def test_every_row_is_uniform_and_carries_the_right_magnitude():
    """Not merely 'constant' -- a constant of the WRONG value would pass that alone."""
    t = uniform_diffuse_tmatrix(0.05)
    expected = 0.05 / (2 * math.pi)
    for row in t:
        assert len(set(round(v, 12) for v in row)) == 1
        assert math.isclose(row[0], expected, rel_tol=1e-12)


def test_specular_component_adds_a_forward_peak():
    t = uniform_diffuse_tmatrix(0.07, specular=0.03)
    assert t[0][0] > t[0][1]
    assert t[40][40] > t[40][0]


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
