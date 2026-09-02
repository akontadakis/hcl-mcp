import math
import os
import pathlib
from hcl_core.ies import analyze_ies, parse_ies

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "synthetic_typeC.ies")

def test_parse_header_and_data_line_1():
    ies = parse_ies(FIX)
    assert ies.header["TEST"] == "synthetic"
    assert ies.header["MANUFAC"] == "HCL-MCP"
    assert ies.tilt == "NONE"
    assert ies.num_lamps == 1
    assert ies.lumens_per_lamp == 1000.0
    assert ies.candela_multiplier == 1.0
    assert ies.num_vert_angles == 4
    assert ies.num_horiz_angles == 1
    assert ies.photometric_type == 1  # C
    assert ies.units_type == 2         # meters

def test_parse_data_line_2_captures_pfactor():
    ies = parse_ies(FIX)
    assert ies.ballast_factor == 1.0
    assert ies.pfactor == 1.0          # NOT "future_use"
    assert ies.input_watts == 10.0

def test_parse_angles_and_candela_grid():
    ies = parse_ies(FIX)
    assert ies.vertical_angles == [0.0, 30.0, 60.0, 90.0]
    assert ies.horizontal_angles == [0.0]
    # candela[num_horiz][num_vert]
    assert ies.candela == [[1000.0, 800.0, 400.0, 0.0]]

def test_parse_accepts_text_not_just_path():
    ies = parse_ies(pathlib.Path(FIX).read_text())
    assert ies.num_vert_angles == 4


# TILT=INCLUDE with a 2-pair embedded tilt block; if the parser merely "reads two lines
# after TILT=", data-line-1 shifts and num_vert_angles comes out wrong.
TILT_INCLUDE = (
    "IESNA:LM-63-2002\n[TEST] inc\nTILT=INCLUDE\n"
    "1\n2\n0 90\n1.0 0.95\n"                       # geom=1, 2 pairs: angles 0,90; mults 1.0,0.95
    "1 1000 1 4 1 1 2 0.3 0.3 0.1\n1.0 1.0 10\n"
    "0 30 60 90\n0\n1000 800 400 0\n"
)

def test_tilt_include_is_consumed_not_misread():
    ies = parse_ies(TILT_INCLUDE)
    assert ies.tilt == "INCLUDE"
    assert ies.tilt_block["num_tilt_pairs"] == 2
    assert ies.tilt_block["angles"] == [0.0, 90.0]
    assert ies.tilt_block["multipliers"] == [1.0, 0.95]
    assert ies.num_vert_angles == 4            # NOT shifted
    assert ies.candela == [[1000.0, 800.0, 400.0, 0.0]]

# Candela values wrapped arbitrarily across lines must read as one flat stream.
WRAPPED = (
    "IESNA:LM-63-2002\nTILT=NONE\n"
    "1 1000 1 4 1 1 2 0.3 0.3 0.1\n1.0 1.0 10\n"
    "0 30\n60 90\n0\n1000 800\n400\n0\n"
)

def test_wrapped_candela_lines():
    ies = parse_ies(WRAPPED)
    assert ies.vertical_angles == [0.0, 30.0, 60.0, 90.0]
    assert ies.candela == [[1000.0, 800.0, 400.0, 0.0]]

def test_missing_keywords_is_non_fatal():
    ies = parse_ies(WRAPPED)
    assert ies.header == {}                    # no [TEST] etc. — still parses


def test_analyze_rated_lumens_and_efficacy():
    rep = analyze_ies(parse_ies(FIX))
    assert rep["rated_lumens"] == 1000.0
    assert rep["efficacy"] == 100.0
    assert rep["input_watts"] == 10.0

def test_analyze_max_candela_and_location():
    rep = analyze_ies(parse_ies(FIX))
    assert rep["max_candela"] == 1000.0
    assert rep["max_candela_at"] == {"vert": 0.0, "horiz": 0.0}

def test_analyze_beam_and_field_angles():
    rep = analyze_ies(parse_ies(FIX))
    assert round(rep["beam_angle"], 4) == 105.0    # 2 * 52.5
    assert round(rep["field_angle"], 4) == 165.0   # 2 * 82.5

def test_analyze_zonal_flux_goldens():
    rep = analyze_ies(parse_ies(FIX))
    assert round(rep["flux_down"], 2) == 2765.81
    assert rep["flux_up"] == 0.0
    assert round(rep["total_flux"], 2) == 2765.81
    assert round(rep["LOR"], 3) == 2.766

def test_analyze_absolute_photometry_guard():
    # lumens_per_lamp == -1 -> rated_lumens is the integrated flux, LOR is None, never negative.
    text = ("IESNA:LM-63-2002\nTILT=NONE\n"
            "1 -1 1 4 1 1 2 0.3 0.3 0.1\n1.0 1.0 10\n"
            "0 30 60 90\n0\n1000 800 400 0\n")
    rep = analyze_ies(parse_ies(text))
    assert rep["absolute_photometry"] is True
    assert round(rep["rated_lumens"], 2) == round(rep["total_flux"], 2)
    assert rep["rated_lumens"] >= 0
    assert rep["LOR"] is None

def test_analyze_type_b_flux_unsupported():
    text = ("IESNA:LM-63-2002\nTILT=NONE\n"
            "1 1000 1 4 1 2 2 0.3 0.3 0.1\n1.0 1.0 10\n"   # photometric_type=2 (B)
            "0 30 60 90\n0\n1000 800 400 0\n")
    rep = analyze_ies(parse_ies(text))
    assert rep["flux_supported"] is False
    assert "unsupported photometric type" in rep["flux_note"].lower()
    assert rep["total_flux"] is None
    assert rep["flux_down_fraction"] is None
    assert rep["sanity_flux_to_rated_ratio"] is None


def test_analyze_applies_candela_multiplier():
    # candela_multiplier=5 -> every effective intensity/flux/efficacy/LOR scales by 5 vs the
    # multiplier=1 fixture. Guards bug B (multiplier was parsed but never applied).
    text = ("IESNA:LM-63-2002\nTILT=NONE\n"
            "1 1000 5 4 1 1 2 0.3 0.3 0.1\n1.0 1.0 10\n"   # candela_multiplier = 5
            "0 30 60 90\n0\n1000 800 400 0\n")
    rep = analyze_ies(parse_ies(text))
    base = analyze_ies(parse_ies(FIX))
    assert rep["candela_scale_applied"] == 5.0
    assert rep["max_candela"] == 5000.0                       # 1000 * 5
    assert round(rep["total_flux"], 2) == round(base["total_flux"] * 5, 2)
    # efficacy = rated_lumens/W, and rated_lumens (lamp output) is NOT scaled -> efficacy unchanged.
    assert round(rep["efficacy"], 2) == round(base["efficacy"], 2)
    assert round(rep["LOR"], 3) == round(base["LOR"] * 5, 3)             # flux scales, rated doesn't


def test_analyze_folds_ballast_and_pfactor():
    # effective candela = raw * candela_multiplier * ballast_factor * pfactor (matches ies2rad).
    text = ("IESNA:LM-63-2002\nTILT=NONE\n"
            "1 1000 2 4 1 1 2 0.3 0.3 0.1\n0.9 1.1 10\n"   # mult=2, ballast=0.9, pfactor=1.1
            "0 30 60 90\n0\n1000 800 400 0\n")
    rep = analyze_ies(parse_ies(text))
    assert round(rep["candela_scale_applied"], 6) == round(2 * 0.9 * 1.1, 6)   # 1.98
    assert round(rep["max_candela"], 4) == round(1000 * 1.98, 4)


def test_analyze_beam_field_reliable_for_nadir_peaked_fixture():
    rep = analyze_ies(parse_ies(FIX))
    assert rep["beam_field_reliable"] is True
    assert rep["beam_field_note"] is None


def test_analyze_flags_offnadir_beam_as_unreliable():
    # Wall-washer: peak at 30deg, not nadir -> beam/field flagged approximate.
    text = ("IESNA:LM-63-2002\nTILT=NONE\n"
            "1 1000 1 4 1 1 2 0.3 0.3 0.1\n1.0 1.0 10\n"
            "0 30 60 90\n0\n200 1000 600 0\n")   # peak at vert=30
    rep = analyze_ies(parse_ies(text))
    assert rep["beam_field_reliable"] is False
    assert "off-nadir" in rep["beam_field_note"].lower() or "approximate" in rep["beam_field_note"].lower()


def test_analyze_flags_multiplane_flux_azimuth():
    # 2 horizontal planes -> flat-mean azimuth approximation surfaced.
    text = ("IESNA:LM-63-2002\nTILT=NONE\n"
            "1 1000 1 4 2 1 2 0.3 0.3 0.1\n1.0 1.0 10\n"
            "0 30 60 90\n0 90\n1000 800 400 0\n900 700 300 0\n")
    rep = analyze_ies(parse_ies(text))
    assert rep["flux_azimuth_note"] is not None


def test_full_angle_never_exceeds_180():
    # Wide/flat distribution: candela (1000..970) stays above BOTH thresholds (beam 500,
    # field 100) out to the 135deg vertical node, so the half-angle walk falls through to the
    # last vertical (135). Without clamping, full = 2*135 = 270 deg -- a non-physical angle.
    # The half-angle must be clamped to <=90 so the full angle never exceeds 180.
    text = ("IESNA:LM-63-2002\nTILT=NONE\n"
            "1 1000 1 4 1 1 2 0.3 0.3 0.1\n1.0 1.0 10\n"
            "0 45 90 135\n0\n1000 990 980 970\n")
    rep = analyze_ies(parse_ies(text))
    assert rep["field_angle"] is not None
    assert rep["field_angle"] <= 180.0
    assert rep["beam_angle"] <= 180.0


def test_analyze_zone_straddling_90_splits_into_hemispheres():
    # Vertical grid 0,80,100 has a zone (80,100) crossing the 90deg boundary with NO node at 90.
    # The straddling zone must contribute to flux_up; without the split it would all go down.
    text = ("IESNA:LM-63-2002\nTILT=NONE\n"
            "1 1000 1 3 1 1 2 0.3 0.3 0.1\n1.0 1.0 10\n"
            "0 80 100\n0\n1000 500 0\n")
    rep = analyze_ies(parse_ies(text))
    assert rep["flux_up"] > 0.0                  # the (90,100) half lands in the upper hemisphere
    assert rep["flux_down"] > 0.0
    # total is preserved across the split (cos is additive)
    assert round(rep["flux_down"] + rep["flux_up"], 6) == round(rep["total_flux"], 6)
