# src/hcl_core/fixtures.py
"""First-principles HCL fixture-design engine (pure Python, zero external deps).

Sizes an electric lighting installation from a visual target (lumen method) reconciled with a
circadian target (CIE S 026 mel-DER) solved over the project's ILLUSTRATIVE LED palette. Every
estimate is an engineering approximation and is reported with its assumption inline; the real chosen
IES (phase 5) and the phase-6 Radiance grid are what validate the design. See spec 2026-06-11.
"""
import math
import warnings

from hcl_core.presets import get_preset, ILLUSTRATIVE_LEDS
from hcl_core.spectral_metrics import mel_der, cct_duv

try:  # colour emits ColourRuntimeWarning ("Aligning ... spectral data shape") from cct_duv/mel_der
    from colour.utilities import ColourRuntimeWarning as _ColourRuntimeWarning
except Exception:  # pragma: no cover - colour optional / API drift
    _ColourRuntimeWarning = None

# Coefficient-of-utilization approximation, indexed by integer Room Cavity Ratio (0..10), for a
# reference reflectance set (ceiling 0.70 / wall 0.50 / floor 0.20). ILLUSTRATIVE planning values,
# not a manufacturer photometric table; phase-5 ies_analyze recomputes UF from the real luminaire.
_CU_TABLE = {
    "direct":          {0: 0.95, 1: 0.86, 2: 0.78, 3: 0.71, 4: 0.64, 5: 0.58,
                        6: 0.53, 7: 0.48, 8: 0.44, 9: 0.40, 10: 0.37},
    "direct_indirect": {0: 0.80, 1: 0.72, 2: 0.65, 3: 0.59, 4: 0.53, 5: 0.48,
                        6: 0.43, 7: 0.39, 8: 0.35, 9: 0.32, 10: 0.29},
    "indirect":        {0: 0.62, 1: 0.54, 2: 0.47, 3: 0.41, 4: 0.36, 5: 0.31,
                        6: 0.27, 7: 0.24, 8: 0.21, 9: 0.18, 10: 0.16},
}


def room_cavity_ratio(length_m: float, width_m: float, h_cavity_m: float) -> float:
    """Zonal-cavity RCR = 5 * h_cav * (L + W) / (L * W). h_cav = luminaire-plane->work-plane height."""
    return 5.0 * h_cavity_m * (length_m + width_m) / (length_m * width_m)


def utilization_factor(rcr: float, distribution: str,
                       rho_ceiling: float, rho_wall: float, rho_floor: float) -> float:
    """Estimate UF by linear interpolation of _CU_TABLE over RCR, scaled by a reflectance factor.

    Reflectance factor is 1.0 at the reference set (0.70/0.50/0.20) and adjusts linearly with the
    weighted reflectance delta. Clamped to a sane band. ILLUSTRATIVE - see module docstring.
    """
    table = _CU_TABLE[distribution]
    r = max(0.0, min(10.0, rcr))
    lo = int(math.floor(r))
    hi = min(10, lo + 1)
    frac = r - lo
    base = table[lo] + (table[hi] - table[lo]) * frac
    # reflectance adjustment: ceiling weighted most for indirect, walls for direct; keep it simple.
    delta = 0.5 * (rho_ceiling - 0.70) + 0.4 * (rho_wall - 0.50) + 0.1 * (rho_floor - 0.20)
    factor = max(0.6, min(1.25, 1.0 + delta))
    return round(base * factor, 4)


def visual_flux_lm(*, length_m: float, width_m: float, h_cavity_m: float,
                   target_em_lux: float, maintenance_factor: float, distribution: str,
                   rho_ceiling: float, rho_wall: float, rho_floor: float) -> float:
    """Total luminous flux to meet the maintained visual target by the lumen method.

    Phi = Em * A / (UF * MF). Daylight is intentionally NOT subtracted (spec C1): the installation
    must meet Em with no daylight; daylight savings are realized operationally by phase-7 controls.
    """
    area = length_m * width_m
    rcr = room_cavity_ratio(length_m, width_m, h_cavity_m)
    uf = utilization_factor(rcr, distribution, rho_ceiling, rho_wall, rho_floor)
    return target_em_lux * area / (uf * maintenance_factor)


_PALETTE_CACHE = None

def led_palette():
    """The illustrative LED candidate palette: [{name, cct_K, mel_der}], sorted by CCT.

    Uses the project's ILLUSTRATIVE_LEDS and the verified mel_der()/cct_duv() - NOT a Planckian
    idealization (spec C3), since LED spectral structure changes mel-DER. Illustrative, not measured.
    """
    global _PALETTE_CACHE
    if _PALETTE_CACHE is None:
        # cct_duv/mel_der go through colour, which emits ColourRuntimeWarning ("Aligning ...
        # spectral data shape") to stderr — noise for stdio MCP clients. Suppress it narrowly here.
        with warnings.catch_warnings():
            if _ColourRuntimeWarning is not None:
                warnings.filterwarnings("ignore", category=_ColourRuntimeWarning)
            warnings.filterwarnings("ignore", message=".*Aligning.*spectral data shape.*")
            warnings.filterwarnings("ignore", message=".*CCT.*")
            pal = []
            for name in ILLUSTRATIVE_LEDS:
                spd = get_preset(name)
                pal.append({"name": name, "cct_K": cct_duv(spd)["cct_K"], "mel_der": mel_der(spd)})
        _PALETTE_CACHE = sorted(pal, key=lambda e: e["cct_K"])
    return [dict(e) for e in _PALETTE_CACHE]


# Practical mel-DER ceiling for a usable white source: D65 = 1.0 by definition; deliberately blue/
# cyan-enriched white reaches ~1.1-1.2. We gate REACHABILITY on this physical ceiling, NOT on the
# illustrative palette's much lower max (~0.82), so the recommender does not over-advise supplementary
# fixtures for targets a real cool/blue-enriched product could meet. Documented approximation (spec C2).
MEL_DER_PHYSICAL_MAX = 1.2


def solve_circadian_spectrum(*, required_mel_der: float,
                             physical_max: float = MEL_DER_PHYSICAL_MAX) -> dict:
    """Resolve a required mel-DER into one of three bands (spec C2):

    - required <= palette max (~0.82)      -> reachable, by_palette=True, name the lowest-CCT preset
    - palette max < required <= physical   -> reachable, by_palette=False (beyond illustrative palette)
    - required > physical                  -> not reachable (caller routes to extra vertical E_v)

    Returns {reachable, by_palette, chosen_preset, chosen_cct_K, palette_max, physical_max}.
    """
    pal = led_palette()
    palette_max = max(e["mel_der"] for e in pal)
    base = {"palette_max": round(palette_max, 4), "physical_max": round(physical_max, 4)}
    if required_mel_der > physical_max:
        return {**base, "reachable": False, "by_palette": False,
                "chosen_preset": None, "chosen_cct_K": None}
    within = [e for e in pal if e["mel_der"] >= required_mel_der]
    if within:
        chosen = min(within, key=lambda e: e["cct_K"])
        return {**base, "reachable": True, "by_palette": True,
                "chosen_preset": chosen["name"], "chosen_cct_K": chosen["cct_K"]}
    # reachable in the real world, but beyond the illustrative palette - no example preset to name
    return {**base, "reachable": True, "by_palette": False,
            "chosen_preset": None, "chosen_cct_K": None}


# Spacing-to-height ratio (max) by distribution class — uniformity criterion S <= SHR * h_cav.
_SHR = {"direct": 1.5, "direct_indirect": 1.25, "indirect": 1.0}


def _grid_layout(length_m, width_m, count, s_max):
    """Arrange `count` fixtures on a near-square grid with spacing <= s_max; return nx, ny, positions."""
    nx = max(1, math.ceil(length_m / s_max))
    ny = max(1, math.ceil(width_m / s_max))
    # densify toward a near-square grid until nx*ny >= count
    while nx * ny < count:
        if length_m / nx >= width_m / ny:
            nx += 1
        else:
            ny += 1
    sx, sy = length_m / nx, width_m / ny
    positions = [[round((i + 0.5) * sx, 3), round((j + 0.5) * sy, 3)]
                 for j in range(ny) for i in range(nx)]
    return nx, ny, round(max(sx, sy), 3), positions


def recommend_fixtures(*, length_m, width_m, height_m, mount_height_m,
                       workplane_height_m=0.8, eye_height_m=1.2,
                       rho_ceiling=0.7, rho_wall=0.5, rho_floor=0.2, maintenance_factor=0.8,
                       target_em_lux=500.0, target_mel_edi=None, mel_edi_daylight=0.0,
                       vertical_horizontal_ratio=0.4, distribution="direct",
                       target_efficacy_lm_w=120.0,
                       per_fixture_lumen_options=(2000, 3000, 4000)) -> dict:
    """First-principles HCL fixture-design recommendation. See spec 2026-06-11 §6. Pure; always runs."""
    if distribution not in _CU_TABLE:
        raise ValueError(f"distribution must be one of {sorted(_CU_TABLE)}")
    h_cav = mount_height_m - workplane_height_m
    if h_cav <= 0:
        raise ValueError("mount_height_m must exceed workplane_height_m")
    if vertical_horizontal_ratio <= 0:
        raise ValueError("vertical_horizontal_ratio must be > 0")
    area = length_m * width_m

    # --- visual sizing (C1: no daylight subtraction) ---
    phi_visual = visual_flux_lm(length_m=length_m, width_m=width_m, h_cavity_m=h_cav,
                                target_em_lux=target_em_lux, maintenance_factor=maintenance_factor,
                                distribution=distribution, rho_ceiling=rho_ceiling,
                                rho_wall=rho_wall, rho_floor=rho_floor)

    # --- circadian sizing (CIE S 026 mel-DER) ---
    pal = led_palette()
    palette_max = max(e["mel_der"] for e in pal)
    binding = "visual"
    phi_total = phi_visual
    reachable = True
    beyond_palette = False
    chosen_cct = pal[-1]["cct_K"]
    min_mel_der = None
    supplementary = False
    glare_warning = False
    if target_mel_edi is not None:
        if target_em_lux <= 0:
            raise ValueError("target_em_lux must be > 0 when a circadian target is given")
        e_v_eye = target_em_lux * vertical_horizontal_ratio            # vertical photopic at eye (electric)
        net_mel_edi = max(0.0, target_mel_edi - mel_edi_daylight)      # daylight credited here only (C1)
        required_der = net_mel_edi / e_v_eye                            # e_v_eye > 0 (em & vhr guarded above)
        min_mel_der = round(required_der, 4)
        solve = solve_circadian_spectrum(required_mel_der=required_der)
        reachable = solve["reachable"]
        beyond_palette = reachable and not solve["by_palette"]
        if reachable:
            # spectrum handles the circadian target — no extra flux; visual stays binding.
            chosen_cct = solve["chosen_cct_K"] if solve["by_palette"] else pal[-1]["cct_K"]
        else:
            # C2: above the physical ceiling → need more vertical light. Extra horizontal lux at the cap.
            e_v_needed = net_mel_edi / MEL_DER_PHYSICAL_MAX
            extra_horizontal = e_v_needed / vertical_horizontal_ratio
            rcr = room_cavity_ratio(length_m, width_m, h_cav)
            uf = utilization_factor(rcr, distribution, rho_ceiling, rho_wall, rho_floor)
            phi_circadian = extra_horizontal * area / (uf * maintenance_factor)
            if phi_circadian > phi_total:
                phi_total = phi_circadian
                binding = "circadian"
            supplementary = True
            glare_warning = True

    # --- layout: reconcile flux vs uniformity counts (C5) ---
    s_max = _SHR[distribution] * h_cav
    nx0 = max(1, math.ceil(length_m / s_max))
    ny0 = max(1, math.ceil(width_m / s_max))
    uniformity_count = nx0 * ny0
    required_per_fix = phi_total / uniformity_count
    viable = [lm for lm in per_fixture_lumen_options if lm >= required_per_fix]
    if viable:
        rec_lumens = min(viable)
    else:
        rec_lumens = max(per_fixture_lumen_options)
    flux_count = math.ceil(phi_total / rec_lumens)
    target_count = max(flux_count, uniformity_count)
    nx, ny, spacing_m, positions = _grid_layout(length_m, width_m, target_count, s_max)
    fixture_count = nx * ny  # realized grid count (>= both drivers); matches placed positions

    per_fixture_options = [{"lumens": lm, "count": max(uniformity_count, math.ceil(phi_total / lm))}
                           for lm in per_fixture_lumen_options]

    watts = phi_total / target_efficacy_lm_w
    # CCT band recommendation:
    #   - no circadian target → a neutral default band
    #   - reachable within palette → from the chosen example CCT up to the coolest palette CCT
    #   - beyond palette / unreachable → recommend cool / blue-enriched white (verify on real SPD)
    coolest = max(e["cct_K"] for e in pal)
    if target_mel_edi is None:
        cct_band = [3000.0, 4000.0]
    elif reachable and not beyond_palette:
        cct_band = [chosen_cct, coolest]
    else:
        cct_band = [5500.0, 6500.0]

    return {
        "required_flux_lm": round(phi_total, 1),
        "fixture_count": fixture_count,
        "layout": {"nx": nx, "ny": ny, "spacing_m": spacing_m, "positions": positions},
        "target_cct_band": [round(cct_band[0], 0), round(cct_band[1], 0)],
        "min_mel_der": min_mel_der,
        "mel_der_achievable_max": MEL_DER_PHYSICAL_MAX,
        "palette_mel_der_max": round(palette_max, 4),
        "beyond_illustrative_palette": beyond_palette,
        "circadian_reachable_by_cct": reachable,
        "binding_constraint": binding,
        "vertical_horizontal_ratio": vertical_horizontal_ratio,
        "flux_count": flux_count,
        "uniformity_count": uniformity_count,
        "est_total_watts": round(watts, 1),
        "power_density_w_m2": round(watts / area, 2),
        "per_fixture_options": per_fixture_options,
        "supplementary_fixtures_advised": supplementary,
        "glare_warning": glare_warning,
        "assumptions": [
            f"distribution class = {distribution}",
            "UF = first estimate from CU table, revalidated by phase-5 ies_analyze",
            f"V/H (vertical-at-eye / horizontal) ratio = {vertical_horizontal_ratio} "
            f"(dominant circadian uncertainty)",
            "CCT->mel-DER solved over illustrative LED palette (not measured product data)",
        ],
        "caveats": [
            "Lumen-method averages; not a point-by-point calc. Confirm with phase-6 run_grid.",
            "Illustrative palette caps at mel-DER ~%.2f; physical ceiling assumed %.2f. Reachability is "
            "gated on the physical ceiling — verify the real product's mel-DER on its SPD."
            % (palette_max, MEL_DER_PHYSICAL_MAX),
        ] + (["Beyond the illustrative palette: target a cool / blue-enriched white (CCT >= ~5500 K) and "
              "confirm mel-DER on the real SPD."] if beyond_palette else [])
          + (["Circadian-bound: extra vertical light may raise UGR/DGP — confirm in phase-6 UGR."]
             if glare_warning else []),
    }
