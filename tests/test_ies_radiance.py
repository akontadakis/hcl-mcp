from hcl_radiance.ies_radiance import build_ies2rad

def test_ies2rad_multiplier_is_user_scaling_only():
    cmd = build_ies2rad("lamp.ies", multiplier=2.0, maintenance_factor=0.8, units=2)
    s = " ".join(cmd)
    assert cmd[0] == "ies2rad"
    assert "-m 1.6" in s          # 2.0 * 0.8 ; NOT candela_multiplier/ballast/pfactor
    assert s.endswith("lamp.ies")

def test_ies2rad_units_letter_form():
    assert "-dm" in " ".join(build_ies2rad("l.ies", units=2))     # meters
    assert "-df" in " ".join(build_ies2rad("l.ies", units=1))     # feet

def test_ies2rad_units_divisor():
    assert "-dm/1000" in " ".join(build_ies2rad("l.ies", units=2, units_divisor=1000))

def test_ies2rad_color_lamp_outprefix():
    s = " ".join(build_ies2rad("l.ies", color=[0.9, 0.8, 0.7], lamp="cool_white",
                               out_prefix="lum", units=2))
    assert "-c 0.9 0.8 0.7" in s and "-t cool_white" in s and "-o lum" in s

def test_ies2rad_inline_form():
    line = build_ies2rad("l.ies", units=2, inline=True)
    assert line.startswith("!ies2rad ") and line.rstrip().endswith("l.ies")

from hcl_radiance.ies_radiance import place_luminaires

def test_place_explicit_rotation_before_translation():
    block = place_luminaires("lum", {"positions": [{"xyz": [1, 2, 3], "rot": [10, 20, 30]}]})
    line = block.strip().splitlines()[0]
    # Y-up -> Z-up: rotX=rx=10, rotY=rz=30, rotZ=-ry=-20
    assert line.startswith("!xform ")          # inline-xform form (oconv/rpict expand '!xform ...')
    rxi, ryi, rzi = line.index("-rx"), line.index("-ry"), line.index("-rz")
    ti = line.index("-t ")
    assert rxi < ryi < rzi < ti                 # rotation BEFORE translation
    assert "-rx 10" in line and "-ry 30" in line and "-rz -20" in line
    assert "-t 1 2 3" in line and line.rstrip().endswith("lum")

def test_place_grid_expands_rows_cols():
    block = place_luminaires("lum", {"grid": {"rows": 2, "cols": 3,
                                              "row_spacing": 1.0, "col_spacing": 2.0,
                                              "origin": [0, 0, 3], "rot": [0, 0, 0]}})
    lines = [ln for ln in block.splitlines() if ln.strip()]
    assert len(lines) == 6                       # 2 * 3 instances
    assert all(ln.startswith("!xform ") for ln in lines)
    assert "-t 4 1 3" in block                   # col 2 (2*2=4), row 1 (1*1=1), z=3

def test_place_zero_rotation_still_orders_t_last():
    block = place_luminaires("lum", {"positions": [{"xyz": [0, 0, 2]}]})
    line = block.strip().splitlines()[0]
    assert "-rx 0 -ry 0 -rz 0" in line and line.index("-rz") < line.index("-t ")

from hcl_radiance.ies_radiance import build_evalglare, parse_evalglare

def test_build_evalglare_detailed():
    cmd = build_evalglare("fisheye.hdr")
    s = " ".join(cmd)
    assert cmd[0] == "evalglare" and "-d" in cmd and s.endswith("fisheye.hdr")

def test_build_evalglare_extra_params():
    cmd = build_evalglare("f.hdr", params="-vta -vh 180 -vv 180")
    assert "-vta" in cmd and cmd[-1] == "f.hdr"

# Legacy/simple sample (UGR labelled as the 2nd field) — exercises the field-name mapping.
SAMPLE = (
    "dgp,ugr,vertical_illuminance,...: 0.230000 18.450000 423.1 ...\n"
    "0: 1 5234.0 0.0123 12.3 45.6\n"
    "1: 1 8900.0 0.0040 30.1 22.2\n"
)

def test_parse_evalglare_extracts_ugr_dgp_sources():
    out = parse_evalglare(SAMPLE)
    assert round(out["DGP"], 3) == 0.230
    assert round(out["UGR"], 2) == 18.45
    assert len(out["glare_sources"]) == 2

# REAL evalglare 5.4 `-d` output (captured live). UGR is the 7th field (`ugr`), NOT the 2nd
# (`av_lum`). Parsing by position would report av_lum=274.45 as UGR — the bug this guards.
REAL_EVALGLARE = (
    "1 No pixels x-pos y-pos L_s Omega_s Posindx L_b L_t E_vert Edir Max_Lum Sigma "
    "xdir ydir zdir Eglare_cie Lveil_cie teta glare_zone\n"
    "1 3651.000000 399.471579 400.509728 10775.178457 0.0562152682 1.002221 176.498840 "
    "274.446960 1157.403557 602.916089 11120.375000 0.159099 0.001963 -0.001963 0.999996 "
    "602.916089 238189.079160 0.159099 0 \n"
    "dgp,av_lum,E_v,lum_backg,E_v_dir,dgi,ugr,vcp,cgi,lum_sources,omega_sources,Lveil,"
    "Lveil_cie,dgr,ugp,ugr_exp,dgi_mod,av_lum_pos,av_lum_pos2,med_lum,med_lum_pos,med_lum_pos2: "
    "0.329837 274.446957 1157.403557 176.498840 602.916089 25.790134 31.711792 0.000000 "
    "35.151150 10775.178457 0.056215 19036.169922 238189.079160 875.541016 1.030633 24.799555 "
    "26.102495 144.842557 16.956802 179.699219 51.021084 14.486157\n"
)

def test_parse_evalglare_real_format_maps_ugr_by_field_name():
    out = parse_evalglare(REAL_EVALGLARE)
    assert round(out["DGP"], 4) == 0.3298            # field 'dgp', column 0
    assert round(out["UGR"], 2) == 31.71             # field 'ugr', column 6 — NOT av_lum (274.45)
    assert out["UGR"] < 100                           # sanity: a real UGR is a small index, not a luminance
    assert len(out["glare_sources"]) == 1            # one source-data row (the label row is skipped)
    assert out["glare_sources"][0]["index"] == 1
