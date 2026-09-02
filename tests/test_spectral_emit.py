from dataclasses import dataclass
from hcl_core.spectral_emit import to_channels, to_reference, record_to_spd_dict, reconstruct_from_record
from hcl_core.spectral_emit import record_to_dict, emit_spd_set
from hcl_core.spectral_emit import (BAND_EDGES_20, band_average, emit_band_matrix,
                                     emit_spectral_wea, emit_augmented_epw_sidecar)
from dataclasses import dataclass as _dc
from hcl_core.spectral_reconstruct import reconstruct_spectrum


@dataclass
class _Rec:
    grid_nm: list
    direct_normal: list
    sky_diffuse_horizontal: list


def _rec():
    grid = [380.0 + i for i in range(401)]
    # diffuse: blue-heavy (high at 380, low at 780); direct: flat.
    diffuse = [1.0 - 0.5 * i / 400.0 for i in range(401)]
    direct = [2.0] * 401
    return _Rec(grid_nm=grid, direct_normal=direct, sky_diffuse_horizontal=diffuse)


def test_record_to_spd_dict_keys_and_values():
    d = record_to_spd_dict([380.0, 381.0, 382.0], [1.0, 2.0, 3.0])
    assert d == {380: 1.0, 381: 2.0, 382: 3.0}


def test_to_channels_returns_diffuse_and_direct_nine():
    diffuse_ch, direct_ch = to_channels(_rec(), 1)
    assert len(diffuse_ch) == 9 and len(direct_ch) == 9
    assert all(v == 2.0 for v in direct_ch)             # flat direct → 2.0 in every bin
    # diffuse is blue-heavy → ascending bins decrease (bin 0 = 380-419 > bin 8 = 630-780)
    assert diffuse_ch[0] > diffuse_ch[-1]


def test_to_channels_three_uses_rgb_order():
    diffuse_ch, direct_ch = to_channels(_rec(), 0)
    assert len(diffuse_ch) == 3 and len(direct_ch) == 3
    # BINS_3 is [r,g,b]; blue-heavy diffuse → b (index 2) > r (index 0).
    assert diffuse_ch[2] > diffuse_ch[0]


def test_to_reference_returns_401_sky_and_sun():
    sky_spd, sun_spd = to_reference(_rec())
    assert len(sky_spd) == 401 and len(sun_spd) == 401
    assert sky_spd[0] == 1.0                              # diffuse at 380
    assert all(v == 2.0 for v in sun_spd)                # direct flat


def test_reconstruct_from_record_uses_physical_references():
    rec = _rec()
    sky_ch = [10.0] * 9
    sun_ch = [5.0] * 9
    got = reconstruct_from_record(rec, sky_ch, sun_ch, channel_type=1)
    # Equivalent to passing the record's sky/sun spectra as explicit references.
    sky_spd, sun_spd = to_reference(rec)
    expect = reconstruct_spectrum(sky_ch, sun_ch, 1, method="reference",
                                  sky_spd=sky_spd, sun_spd=sun_spd, sun_spectral="colored")
    assert got == expect
    assert len(got) == 401


def test_reconstruct_from_record_differs_from_template():
    # The record's PHYSICAL references must actually replace the D-series/air-mass templates:
    # reconstruct_from_record must differ from a plain template reconstruct_spectrum (no refs).
    rec = _rec()
    sky_ch = [10.0] * 9
    sun_ch = [5.0] * 9
    physical = reconstruct_from_record(rec, sky_ch, sun_ch, channel_type=1)
    template = reconstruct_spectrum(sky_ch, sun_ch, 1, method="reference")
    assert physical != template


@_dc
class _FullRec:
    timestamp: tuple
    grid_nm: list
    direct_normal: list
    sky_diffuse_horizontal: list
    broadband: dict
    provenance: dict
    atmosphere: object = None
    geometry: object = None


def _full_rec():
    grid = [380.0 + i for i in range(401)]
    return _FullRec(timestamp=(6, 21, 12), grid_nm=grid,
                    direct_normal=[2.0] * 401, sky_diffuse_horizontal=[1.0] * 401,
                    broadband={"dni": 850.0, "dhi": 120.0, "ghi": 812.0, "clearness_kt": 0.7},
                    provenance={"engine": "spectrl2", "cloud_model": "sedes1"})


def test_record_to_dict_shape():
    d = record_to_dict(_full_rec())
    assert d["timestamp"] == [6, 21, 12]
    assert d["broadband"]["dni"] == 850.0
    assert len(d["direct_normal"]) == 401
    assert d["provenance"]["engine"] == "spectrl2"


def test_emit_spd_set_csv_structure():
    csv = emit_spd_set(_full_rec())
    lines = csv.strip().splitlines()
    assert lines[0] == "wavelength_nm,direct_normal,sky_diffuse_horizontal"
    assert len(lines) == 402                         # header + 401 rows
    assert lines[1] == "380,2.0,1.0"
    assert lines[-1].startswith("780,")


def test_emit_spd_set_with_ground_column():
    csv = emit_spd_set(_full_rec(), ground=[0.5] * 401)
    lines = csv.strip().splitlines()
    assert lines[0].endswith(",ground")
    assert lines[1] == "380,2.0,1.0,0.5"


def test_band_edges_and_average():
    assert BAND_EDGES_20[0] == 380 and BAND_EDGES_20[-1] == 780 and len(BAND_EDGES_20) == 21
    bands = band_average([2.0] * 401)
    assert len(bands) == 20 and all(abs(b - 2.0) < 1e-9 for b in bands)


def test_emit_band_matrix_row_shape():
    txt = emit_band_matrix([_full_rec()])
    lines = txt.strip().splitlines()
    body = [l for l in lines if not l.startswith("#")]
    cols = body[0].split()
    assert cols[:3] == ["6", "21", "12"]
    assert len(cols) == 3 + 20 + 20            # m d h + 20 diffuse + 20 direct


def test_emit_spectral_wea_and_sidecar():
    wea = emit_spectral_wea([_full_rec()]).strip().splitlines()
    assert len(wea[-1].split()) == 3 + 20      # m d h + 20 diffuse bands
    side = emit_augmented_epw_sidecar([_full_rec()]).strip().splitlines()
    assert side[0].startswith("month,day,hour,dir_380,")
    assert "dif_380" in side[0]
    assert len(side[1].split(",")) == 3 + 401 + 401  # m,d,h + 401 direct + 401 diffuse values
