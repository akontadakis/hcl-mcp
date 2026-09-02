"""EPW -> atmospheric inputs for the spectral engines (pure-Python, offline).

Precipitable water: Gueymard 1994 (primary, from temperature + RH; the pvlib formulation) with
Reitan 1963 (ln(W)=a+b*Td) as a dew-point-only fallback. Both return W in cm. The rest of the
state (AOD, ozone, pressure, albedo) is assembled in derive() with documented defaults + provenance.
"""
import math
from dataclasses import dataclass


def gueymard94_pw(temp_air_c, relative_humidity_pct):
    """Precipitable water (cm) via Gueymard (1994), as implemented in pvlib.atmosphere.gueymard94_pw."""
    T = temp_air_c + 273.15            # Kelvin
    rh = relative_humidity_pct
    theta = T / 273.15
    pw = (0.1
          * (0.4976 + 1.5265 * theta + math.exp(13.6897 * theta - 14.9188 * theta ** 3))
          * (216.7 * rh / (100.0 * T)
             * math.exp(22.330 - 49.140 * (100.0 / T)
                        - 10.922 * (100.0 / T) ** 2 - 0.39015 * T / 100.0)))
    return pw


def reitan63_pw(dew_point_c):
    """Precipitable water (cm) via Reitan (1963): ln(W) = a + b*Td, b≈0.0681 /°C.

    APPROXIMATE fallback only (Reitan was fit to monthly means; on hourly dew points expect larger
    scatter — Gueymard94 is preferred when RH is available). Coefficients: a=-0.0392, b=0.0681.
    """
    return math.exp(-0.0392 + 0.0681 * dew_point_c)


def van_heuklon_ozone(lat_deg, lon_deg, day_of_year):
    """Total column ozone (atm-cm) via van Heuklon (1979), Sol. Energy 22:63, Table 1.

    Ω[matm-cm] = J + (A + C·sin(D·(doy+F)) + G·sin(H·(lon+I)))·sin²(B·lat); all trig args in
    degrees. The model is HEMISPHERE-SPECIFIC (distinct A/B/C/D/F/G/H/I coefficient sets north
    vs south of the equator) — it is not the hemisphere-symmetric approximation the name might
    suggest. Reference implementation: R.T. Wilson's `vanHOzone` (canonical port of the original
    van Heuklon Fortran/BASIC). Returns column ozone in atm-cm (i.e. matm-cm / 1000; the J=235
    base term alone is 0.235 atm-cm = 235 DU).

    The Northern-hemisphere coefficients (J=235, A=150, C=40, D=0.9865, F=-30, G=20, H=3, I=20,
    B=1.28) are reproduced verbatim as the original van Heuklon 1979 model in Karavana-Papadimou
    et al. (2013), Global NEST J. 15(2):152, eq. 2 — which independently confirms F=-30 (maximum
    ozone in NH spring, minimum in autumn), NOT a summer-peaking phase.
    """
    if lat_deg >= 0.0:
        A, B, C, D, F, G, H, J = 150.0, 1.28, 40.0, 0.9865, -30.0, 20.0, 3.0, 235.0
        I = 20.0 if lon_deg > 0.0 else 0.0
    else:
        A, B, C, D, F, G, H, I, J = 100.0, 1.5, 30.0, 0.9865, 152.625, 20.0, 2.0, -75.0, 235.0
    seasonal = C * math.sin(math.radians(D * (day_of_year + F)))
    longitudinal = G * math.sin(math.radians(H * (lon_deg + I)))
    lat_term = math.sin(math.radians(B * lat_deg)) ** 2
    matm_cm = J + (A + seasonal + longitudinal) * lat_term
    return matm_cm / 1000.0


# Documented defaults (spec §3, §13).
_OZONE_DEFAULT = 0.30      # atm-cm (300 DU)
_ALPHA_DEFAULT = 1.14      # Ångström exponent
_AOD500_DEFAULT = 0.10     # clean-continental (pvlib default) when EPW AOD missing
_PRESSURE_DEFAULT = 1013.25  # mbar
_ALBEDO_DEFAULT = 0.20
# Shared with the EPW parser so the "is this albedo real?" rule has one definition.
from hcl_core.epw_hourly import _ALBEDO_MIN_PHYSICAL   # noqa: E402  (constant, not a cycle)
_G_DEFAULT = 0.65          # rural aerosol asymmetry (SPECTRL2 default)


@dataclass(frozen=True)
class AtmosphericState:
    aod500: float            # AOD @ 500nm (base e)
    angstrom_alpha: float    # Ångström exponent
    pw_cm: float             # precipitable water, cm
    ozone_atm_cm: float      # ozone column, atm-cm (300 DU = 0.30)
    pressure_mbar: float
    albedo: float            # broadband ground albedo
    provenance: dict         # {field: {source, method, uncertainty}} — uncertainty reserved (None) in v1
    aerosol_g: float = 0.65  # aerosol asymmetry factor (SPECTRL2 forward-scatter term); appended last


def _pw_and_provenance(row):
    """Precipitable water (cm) + provenance: Gueymard94 if temp+RH present, else Reitan63 on dew point."""
    temp, rh, dew = row.get("dry_bulb_c"), row.get("rh_pct"), row.get("dew_point_c")
    if temp is not None and rh is not None:
        return gueymard94_pw(temp, rh), {"source": "epw", "method": "gueymard94"}
    if dew is not None:
        return reitan63_pw(dew), {"source": "epw", "method": "reitan63"}
    # No humidity info at all → mid-latitude default ~1.5 cm.
    return 1.5, {"source": "default", "method": "fixed"}


def derive(row, *, overrides=None, ozone_mode="constant", aod_anchor_nm=None,
           lat_deg=None, lon_deg=None, day_of_year=None):
    """EPW hourly row dict -> AtmosphericState with documented defaults + per-field provenance.

    overrides: optional {field_name: value} that wins over EPW/defaults (marked source='override').
    EPW precip-water column is intentionally ignored for PWV (officially unreliable); PWV comes
    from temp+RH (Gueymard94) or dew point (Reitan63).

    aod_anchor_nm: if the AOD supplied (row["aod"] or overrides["aod500"]) is anchored at a
      wavelength other than 500nm, pass that wavelength here to Ångström-convert it to tau500
      (D-3). None or 500.0 is a no-op (identity; today's behavior, unchanged provenance).

    ozone_mode: "constant" (default) always uses _OZONE_DEFAULT (0.30 atm-cm) unless an explicit
      "ozone_atm_cm" override is supplied. "climatology" computes ozone via van_heuklon_ozone()
      from lat_deg/lon_deg/day_of_year (falls back to the constant default if any of those three
      are None). An explicit "ozone_atm_cm" override always wins regardless of ozone_mode.

    pw_cm provenance["pw_cm"]["method"] vocabulary (for Phase 2 consumers):
      "gueymard94" — computed from temp_air_c + rh_pct via Gueymard (1994)
      "reitan63"   — computed from dew_point_c via Reitan (1963) fallback
      "fixed"      — no humidity fields present; mid-latitude default (1.5 cm) applied
      "explicit"   — pw_cm was supplied via overrides; bypasses all humidity logic
    """
    overrides = overrides or {}
    prov = {}

    def resolve(field, epw_value, default, *, epw_method="epw", transform=lambda v: v,
                valid=None):
        """Override > EPW value > documented default, recording which one was used.

        `valid` rejects a physically impossible EPW value as MISSING rather than adopting it, so
        the provenance never claims `source: "epw"` for something no instrument measured. An
        explicit override is always honoured -- the caller owns that choice.
        """
        if field in overrides:
            prov[field] = {"source": "override", "method": "explicit"}
            return overrides[field]
        if epw_value is not None and (valid is None or valid(epw_value)):
            prov[field] = {"source": "epw", "method": epw_method}
            return transform(epw_value)
        prov[field] = {"source": "default", "method": "fixed"}
        return default

    pw_cm, pw_prov = _pw_and_provenance(row)
    if "pw_cm" in overrides:
        pw_cm, pw_prov = overrides["pw_cm"], {"source": "override", "method": "explicit"}
    prov["pw_cm"] = pw_prov

    pressure_mbar = resolve("pressure_mbar", row.get("pressure_pa"), _PRESSURE_DEFAULT,
                            epw_method="pa_to_mbar", transform=lambda pa: pa / 100.0)
    # IWEC/TMY2 write a literal 0.000 albedo for every hour as a de-facto "no data" marker rather
    # than the data dictionary's 999.0 sentinel (4 of the 11 EPWs surveyed for ADR-0004 did,
    # Athens among them). Nothing outdoors is a perfect absorber, so a sub-physical value is missing data: taking
    # it at face value zeroed the entire ground-reflected term while stamping it `source: "epw"`.
    # Guarded here as well as in `epw_hourly` so a caller passing a hand-built row is covered too.
    albedo = resolve("albedo", row.get("albedo"), _ALBEDO_DEFAULT,
                     valid=lambda v: v >= _ALBEDO_MIN_PHYSICAL)
    # EPW AOD (when present) is broadband, not strictly @500nm; treated as a 500nm proxy here and
    # noted in provenance. Usually missing → default. (spec §13: Ångström conversion is a later refinement.)
    aod500 = resolve("aod500", row.get("aod"), _AOD500_DEFAULT, epw_method="epw_broadband_proxy")
    if "ozone_atm_cm" in overrides:
        ozone_atm_cm = overrides["ozone_atm_cm"]
        prov["ozone_atm_cm"] = {"source": "override", "method": "explicit", "uncertainty": None}
    elif ozone_mode == "climatology" and None not in (lat_deg, lon_deg, day_of_year):
        ozone_atm_cm = van_heuklon_ozone(lat_deg, lon_deg, day_of_year)
        prov["ozone_atm_cm"] = {"source": "climatology", "method": "van_heuklon79", "uncertainty": None}
    else:
        ozone_atm_cm = _OZONE_DEFAULT
        prov["ozone_atm_cm"] = {"source": "default", "method": "fixed", "uncertainty": None}
    angstrom_alpha = resolve("angstrom_alpha", None, _ALPHA_DEFAULT)
    # D-3: convert a declared-anchor AOD to tau500 using the same alpha the engine spreads with.
    if aod_anchor_nm is not None and abs(aod_anchor_nm - 500.0) > 1e-9:
        aod500 = aod500 * (aod_anchor_nm / 500.0) ** angstrom_alpha
        prov["aod500"] = {"source": prov["aod500"]["source"],
                          "method": f"angstrom_from_{float(aod_anchor_nm)}nm", "uncertainty": None}
    aerosol_g = resolve("aerosol_g", None, _G_DEFAULT)

    # spec §4 declares per-field provenance as {source, method, uncertainty}. The uncertainty band is
    # reserved/unquantified in v1 (no per-field uncertainty model yet) — carried as None so the schema
    # is complete and an uncertainty value is a later additive fill, not a key addition. (D-1)
    for entry in prov.values():
        entry.setdefault("uncertainty", None)

    return AtmosphericState(
        aod500=aod500,
        angstrom_alpha=angstrom_alpha,
        pw_cm=pw_cm,
        ozone_atm_cm=ozone_atm_cm,
        pressure_mbar=pressure_mbar,
        albedo=albedo,
        provenance=prov,
        aerosol_g=aerosol_g,
    )
