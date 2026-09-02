import math
import pytest
from hcl_core import sky_radiance as B
from hcl_core import receiver as R

WL = list(range(380, 781))


def test_rayleigh_phase_symmetric_and_minimised_at_90():
    assert abs(B.rayleigh_phase(0.0) - B.rayleigh_phase(180.0)) < 1e-9
    assert B.rayleigh_phase(90.0) < B.rayleigh_phase(0.0)


def test_hg_phase_forward_peaked_and_normalised_integral():
    g = 0.65
    assert B.hg_phase(0.0, g) > B.hg_phase(90.0, g) > B.hg_phase(180.0, g)
    # HG integrates to 1 over the sphere: (1/2)∫ p(Θ) sinΘ dΘ = 1
    n, acc = 2000, 0.0
    for i in range(n):
        th = math.pi * (i + 0.5) / n
        acc += B.hg_phase(math.degrees(th), g) * math.sin(th) * (math.pi / n)
    assert abs(0.5 * acc - 1.0) < 1e-2


def test_color_field_dome_mean_is_grey_unity():
    field = B.color_ratio_field(WL, sun_alt=45.0, sun_az=180.0, aod_ratio=0.3, eta=1.0)
    assert len(field) == R.N_SKY and all(len(r) == len(WL) for r in field)
    # cosine-weighted dome mean ratio == 1 at every wavelength (colour-only, carries no magnitude)
    for k in range(0, len(WL), 50):
        mean = R.integrate_diffuse([field[i][k] for i in range(R.N_SKY)]) / math.pi
        assert abs(mean - 1.0) < 1e-6


def test_eta_zero_collapses_to_isotropic_grey():
    field = B.color_ratio_field(WL, sun_alt=45.0, sun_az=180.0, aod_ratio=0.3, eta=0.0)
    for i in (0, 70, 144):
        assert all(abs(field[i][k] - 1.0) < 1e-9 for k in range(0, len(WL), 40))


def test_blue_red_tilt_present_when_eta_one():
    # a patch far from the sun (Rayleigh-dominated) is bluer than one near the sun (aerosol/warm)
    field = B.color_ratio_field(WL, sun_alt=45.0, sun_az=180.0, aod_ratio=0.3, eta=1.0)
    near = min(range(R.N_SKY), key=lambda i: R.scattering_angle_deg(R.DOME[i]["alt"], R.DOME[i]["az"], 45.0, 180.0))
    far = max(range(R.N_SKY), key=lambda i: R.scattering_angle_deg(R.DOME[i]["alt"], R.DOME[i]["az"], 45.0, 180.0))
    blue, red = WL.index(450), WL.index(650)
    assert (field[far][blue] / field[far][red]) > (field[near][blue] / field[near][red])


def test_color_ratio_field_g_changes_result():
    f1 = B.color_ratio_field([380.0, 550.0, 780.0], sun_alt=45.0, sun_az=180.0, aod_ratio=0.4, g=0.65)
    f2 = B.color_ratio_field([380.0, 550.0, 780.0], sun_alt=45.0, sun_az=180.0, aod_ratio=0.4, g=0.50)
    assert f1 != f2


def test_receiver_single_scatter_honors_record_aerosol_g(tmp_path):
    # CONTROLLER-MANDATED EXTRA TEST: the sensitivity test above only proves g matters at the
    # sky_radiance layer; this test actually exercises the receiver.py wiring end to end.
    #
    # NOTE on a confound found while writing this test: record.atmosphere.aerosol_g ALSO already
    # feeds src/hcl_core/spectral_engine/spectrl2.py's forward-scatter fraction (a prior, already-wired
    # D-7 site) and so changes record.sky_diffuse_horizontal (the base spectrum) itself, independent
    # of any receiver.py wiring. A naive `mode="single_scatter"` output-equality check therefore passes
    # even WITHOUT the receiver.py edit, for the wrong reason (confirmed empirically: comparing raw
    # single_scatter outputs is True both before and after the fix). To isolate the receiver-level
    # effect, normalise by the `perez` mode output computed from the SAME record — perez uses no
    # colour_field / no g at all, so this ratio cancels the shared base spectrum and Layer-A magnitude,
    # leaving only the single-scatter colour-ratio field's contribution. Before the fix that ratio is
    # identical between r_hi/r_lo up to float noise (~1e-15); after the fix it differs by ~0.06.
    from test_atmos_refinements_guard import _write_epw, _row   # bare sibling import, no tests/__init__.py
    from hcl_core.spectral_pipeline import record_from_epw
    epw = _write_epw(tmp_path, _row(6, 12, 28, 12, 40, 101300, 800, 850, 120, 2, 1, 15, 0.12, 0.2))
    r_hi = record_from_epw(epw, 6, 21, 12, overrides={"aerosol_g": 0.65})
    r_lo = record_from_epw(epw, 6, 21, 12, overrides={"aerosol_g": 0.50})
    ss_hi = R.oriented_diffuse_for_receiver(r_hi, surface_az=180.0, mode="single_scatter")
    ss_lo = R.oriented_diffuse_for_receiver(r_lo, surface_az=180.0, mode="single_scatter")
    pz_hi = R.oriented_diffuse_for_receiver(r_hi, surface_az=180.0, mode="perez")
    pz_lo = R.oriented_diffuse_for_receiver(r_lo, surface_az=180.0, mode="perez")
    ratio_hi = [a / b for a, b in zip(ss_hi, pz_hi)]
    ratio_lo = [a / b for a, b in zip(ss_lo, pz_lo)]
    max_diff = max(abs(a - b) for a, b in zip(ratio_hi, ratio_lo))
    assert max_diff > 1e-6   # receiver threads record.atmosphere.aerosol_g through (not float noise)


def test_default_eta_lands_facade_spread_in_measured_band():
    from hcl_core import solpos
    from hcl_core.atmosphere import AtmosphericState
    from hcl_core.spectral_engine.spectrl2 import Spectrl2Engine
    from hcl_core.cloud_modifier import Sedes1Modifier
    from hcl_core.spectral_sky import build_record
    from hcl_core import receiver as R
    from hcl_core.spectral_metrics import cct_duv
    assert 0.0 < B.DEFAULT_ETA < 1.0                       # fitted, damped (not the raw overshoot)
    atm = AtmosphericState(aod500=0.15, angstrom_alpha=1.3, pw_cm=1.5, ozone_atm_cm=0.34,
                           pressure_mbar=1008.0, albedo=0.2, provenance={})
    # Arbitrary fixture coordinates, NOT any measured site. The expectations below are
    # pinned at THIS geometry, so the values stay as they are.
    #
    # hour=14 (afternoon, sun west of south, az~206°) is deliberate: the afternoon anisotropy
    # (E bluer than W) is an afternoon phenomenon. At hour=13 the sun is still east of south
    # (az~165°) and the E/W ordering reverses — afternoon is required, not arbitrary. The full
    # E>N>W ordering emerges later in the afternoon.
    geo = solpos.compute(month=5, day=13, hour=14, latitude=37.98, longitude=-23.73, time_zone=-45)
    rec = build_record(Spectrl2Engine(), Sedes1Modifier(), atm, geo, timestamp=(5, 13, 14),
                       dni=800.0, dhi=120.0, ghi=900.0, i0_normal=1361.0)
    ccts = {o: cct_duv(list(zip(rec.grid_nm,
            R.oriented_diffuse_for_receiver(rec, surface_az=az, mode="single_scatter"))))["cct_K"]
            for o, az in (("E", 90.0), ("N", 0.0), ("S", 180.0), ("W", 270.0))}
    spread = max(ccts.values()) - min(ccts.values())
    # The bounds are the EMPIRICAL band the wrapper was fitted against — an internal
    # dataset that is not published with this toolkit. They are recorded here as plain
    # numbers; the fit itself is not reproducible from this repo.
    #
    # NOT a tight guard on eta. At eta=0.19 (the bottom of the admissible interval) the
    # spread is 472 K against this 468 K floor - 4 K of margin on a ~1676 K quantity - so
    # dropping eta to the bottom of its range SURVIVES this assertion. eta=0.7 is caught.
    # Anyone reading this as pinning eta will be misled; it pins the BAND, not the knob.
    assert 468.0 < spread < 2860.0
    assert ccts["E"] > ccts["W"]                           # afternoon: E (anti-solar, Rayleigh-blue) > W
