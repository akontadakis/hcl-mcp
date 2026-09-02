import pytest
from dataclasses import dataclass
from hcl_core.spectral_engine.smarts import (smarts_available, smarts_misconfigured, SmartsEngine,
                                             build_deck, parse_ext_output)
from hcl_core.spectral_engine.base import SpectralEngine


@dataclass
class _Atm:
    aod500: float; angstrom_alpha: float; pw_cm: float; ozone_atm_cm: float
    pressure_mbar: float; albedo: float; aerosol_g: float = 0.65
@dataclass
class _Geo:
    zenith_deg: float
@dataclass
class _GeoFull:
    # SPECTRL2 also reads air_mass + earth_radius_vector; SMARTS derives air mass from zenith itself.
    zenith_deg: float
    air_mass: float
    earth_radius_vector: float = 1.0


def test_smarts_engine_satisfies_protocol():
    assert isinstance(SmartsEngine(), SpectralEngine)
    assert SmartsEngine().name == "smarts"


def test_smarts_available_is_bool():
    assert isinstance(smarts_available(), bool)


def test_smarts_misconfigured_is_distinguishable_from_unset(monkeypatch, tmp_path):
    """A set-but-wrong SMARTSPATH must be reportable, not silently identical to unset.

    Both states make smarts_available() False, but they are NOT the same situation and the
    difference is expensive: every comparison script auto-detects ~/smarts/smarts295bat only
    `if not os.environ.get("SMARTSPATH")`, so a wrong non-empty value BLOCKS the fallback that
    would otherwise have rescued the run. The realistic typo is a trailing slash — SMARTSPATH
    pointing at the containing directory rather than the binary — which reads as "configured",
    disables SMARTS, and lets a study report CANNOT COMPUTE with no indication why.
    """
    binary = tmp_path / "smarts295bat"
    binary.write_text("#!/bin/sh\n")
    binary.chmod(0o755)

    monkeypatch.delenv("SMARTSPATH", raising=False)
    assert smarts_misconfigured() is None, "unset is a legitimate state, not a misconfiguration"

    monkeypatch.setenv("SMARTSPATH", str(binary))
    assert smarts_available()
    assert smarts_misconfigured() is None

    # The trailing-slash / directory form: the binary exists, but SMARTSPATH names its parent.
    monkeypatch.setenv("SMARTSPATH", str(tmp_path))
    assert not smarts_available()
    reason = smarts_misconfigured()
    assert reason is not None, "a directory-valued SMARTSPATH must be reported, not silent"
    assert "directory" in reason.lower()
    assert str(binary) in reason, "the reason should name the binary the user probably meant"

    # The exact typo that silently disabled SMARTS in a real study run: a trailing separator
    # on an otherwise-correct path. POSIX resolves "<file>/" to nothing, so this is NOT the
    # isdir case and must not degrade to a bare "does not exist" about a binary that is present.
    monkeypatch.setenv("SMARTSPATH", str(binary) + "/")
    assert not smarts_available()
    reason = smarts_misconfigured()
    assert reason is not None and "trailing" in reason.lower()
    assert str(binary) in reason, "the reason should point at the correct path"

    # A path that simply does not exist is also a misconfiguration, with a different reason.
    monkeypatch.setenv("SMARTSPATH", str(tmp_path / "nope" / "smarts295bat"))
    assert not smarts_available()
    reason = smarts_misconfigured()
    assert reason is not None and "does not exist" in reason.lower()

    # Present but not executable — the third realistic failure (lost +x on copy).
    plain = tmp_path / "not_executable"
    plain.write_text("")
    plain.chmod(0o644)
    monkeypatch.setenv("SMARTSPATH", str(plain))
    assert not smarts_available()
    reason = smarts_misconfigured()
    assert reason is not None and "not executable" in reason.lower()


# Two independent clear-sky radiative-transfer models (SPECTRL2 vs the SMARTS oracle) will NOT
# agree to a few percent. The envelope is deliberately loose and applies to DIRECT-normal (both are
# Beer–Lambert beam transmittance, the well-constrained quantity). Spectral DIFFUSE between the two
# models genuinely diverges far more (different single-scatter + multi-reflection treatments, and
# SMARTS reports the *pure* diffuse), so it is only sanity-checked for finite/positive signal, not
# bounded — bounding it tightly would make this gated test flake-fail on real hardware.
CROSS_ENGINE_DIRECT_ENVELOPE_PCT = 35.0


@pytest.mark.skipif(not smarts_available(), reason="SMARTS binary not present (SMARTSPATH unset)")
def test_smarts_cross_check_clear_sky():
    """Gated cross-validation of the default SPECTRL2 engine against the SMARTS oracle.

    Runs both engines for one clear-sky atmosphere/geometry and compares the visible band via
    compare_engines. This is the executable form of Phase 6's "cross-engine compare (SMARTS vs
    SPECTRL2)" deliverable. Green here means a LIVE SMARTS run agreed with SPECTRL2 within the
    documented direct-normal envelope — still capability-gated (skips when the binary is absent),
    so green pytest WITHOUT a binary does not imply this ran.
    """
    import math
    from hcl_core.spectral_engine.spectrl2 import Spectrl2Engine
    from hcl_core.spectral_validate import compare_engines

    atm = _Atm(0.084, 1.14, 2.0, 0.33, 1013.0, 0.2)
    zenith = 48.19  # a clear mid-morning sun, well above the horizon
    geo = _GeoFull(zenith_deg=zenith, air_mass=1.0 / math.cos(math.radians(zenith)))

    spectrl2 = Spectrl2Engine().compute(atm, geo)
    smarts = SmartsEngine().compute(atm, geo)

    # Both engines must cover the photopic/melanopic band and carry real direct signal.
    for cs in (spectrl2, smarts):
        assert min(cs.wavelength_nm) <= 380.0 and max(cs.wavelength_nm) >= 780.0
        assert any(v > 0 for v in cs.direct_normal)
        assert any(v > 0 for v in cs.sky_diffuse_horizontal)

    diff = compare_engines(spectrl2, smarts)            # raises if either grid fails to span 380–780
    assert all(math.isfinite(v) for v in diff.values())
    assert abs(diff["direct_mean_pct"]) < CROSS_ENGINE_DIRECT_ENVELOPE_PCT


def test_build_deck_encodes_inputs():
    deck = build_deck(_Atm(0.084, 1.14, 2.0, 0.33, 1013.0, 0.2), _Geo(45.0))
    lines = deck.splitlines()
    assert deck.endswith("\n") and "\r" not in deck            # LF only
    assert "'USSA'" in deck and "'S&F_RURAL'" in deck
    assert "1013.0" in lines[2]                                 # Card 2a pressure
    assert "2.0" in lines[6]                                    # Card 4a PWV
    assert "0.33" in lines[8]                                   # Card 5a ozone
    assert "0.084" in deck                                      # Card 9a TAU5 = AOD500
    assert "0.2" in deck                                        # Card 10a albedo
    assert "1 2 3" in deck                                      # IOUT codes
    assert "45.0" in lines[-1]                                  # Card 17a zenith


def test_parse_ext_output_columns():
    sample = (
        "Wvlgth Extraterrestrial_spectrm Direct_normal_irradiance Diffuse_horizn_irradiance\n"
        "380.0 1.5000E+00 8.0000E-01 2.0000E-01\n"
        "381.0 1.6000E+00 8.1000E-01 2.1000E-01\n"
    )
    wl, direct, diffuse = parse_ext_output(sample)
    assert wl == [380.0, 381.0]
    assert direct == [0.8, 0.81]
    assert diffuse == [0.2, 0.21]


def test_compute_raises_without_binary():
    if smarts_available():
        pytest.skip("SMARTS present; gating test only meaningful when absent")
    with pytest.raises(RuntimeError):
        SmartsEngine().compute(_Atm(0.084, 1.14, 2.0, 0.33, 1013.0, 0.2), _Geo(45.0))


@pytest.mark.skipif(not smarts_available(), reason="SMARTS binary not present (SMARTSPATH unset)")
def test_compute_returns_um_units_and_visible_band():
    cs = SmartsEngine().compute(_Atm(0.084, 1.14, 2.0, 0.33, 1013.0, 0.2), _Geo(45.0))
    assert cs.units == "W/m^2/um"
    assert min(cs.wavelength_nm) <= 380.0 and max(cs.wavelength_nm) >= 780.0
    assert any(v > 0 for v in cs.direct_normal)
