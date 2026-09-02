"""Automatic annual -> nvRD bridge (spec §5.1). Dual reconstruction in one shared transport.

EPW -> generate_subhourly_wea (Daysim, Plan 09) -> run_annual_separated (colored 2-phase DDS, sky &
sun kept SEPARATE) -> per timestep reconstruct the 401-value per-nm spectrum TWO ways (faithful flat
+ neutral sun; enhanced reference sky + air-mass colored sun) -> assemble nvRD rows -> nvrd() twice ->
both R_D series + divergence. R_D is RELATIVE only (spec §5.3).
"""
import os
import math

from hcl_core.spectral_emit import to_reference
from hcl_core.spectral_reconstruct import assemble_nvrd_rows, reconstruction_divergence
from hcl_core.nvrd import nvrd as _nvrd

_RELATIVE_NOTE = ("R_D is RELATIVE only: the nvRD intensity-response was fit from nighttime studies; "
                  "daytime adaptation is unvalidated, and the §9.3a reconstruction constant scales "
                  "absolute R_D (does NOT cancel). Compare R_D across scenarios, not as an absolute. "
                  "Accuracy envelope: daylight mel-EDI within ~±20% of the reference; ~9% of 6-h exposures show a "
                  "significant cumulative-R_D error (Pierson 2023).")

def _regroup_to_channels(sets, channel_type):
    """sets: per-channel-set list of per-timestep [R,G,B]. -> per-timestep flat channel vector.

    9-channel: concat the 3 channel-sets' RGB -> 9 values/timestep. 3-channel: the single set's RGB.
    """
    expected = 3 if channel_type == 1 else 1
    if len(sets) != expected:
        raise ValueError(f"channel_type {channel_type} expects {expected} channel-set(s), got {len(sets)}")
    n_steps = len(sets[0])
    out = []
    for t in range(n_steps):
        vec = []
        for s in sets:
            vec.extend(s[t])
        out.append(vec)
    return out

def _is_zero_record(rec):
    """A night/zero record carries all-~0 direct + diffuse — its reference would only trip the flat fallback."""
    return (not any(abs(v) > 1e-12 for v in rec.direct_normal)
            and not any(abs(v) > 1e-12 for v in rec.sky_diffuse_horizontal))

def _physical_spd_series(record_index, timestamps, *, real_timestamps):
    """Map each transport timestep (m,d,h_frac) to its EPW hour-ending record and build per-timestep
    reference SPDs. Returns (sky_spd_series, sun_spd_series, coverage).

    record_index: {(month, day, hour_ending): record}. Each *_series[t] is a 401-value SPD (physics for
    that step) or None (template fallback). A miss, a synthetic-timestamp run (real_timestamps=False), or a
    night/zero record all yield None and count as template. coverage = {n_physical, n_template, coverage_pct}.
    """
    sky_series, sun_series = [], []
    n_physical = n_template = 0
    for (m, d, h) in timestamps:
        rec = None
        if real_timestamps:
            H = min(24, max(1, math.ceil(h)))
            rec = record_index.get((m, d, H))
        if rec is not None and not _is_zero_record(rec):
            sky_spd, sun_spd = to_reference(rec)
            sky_series.append(sky_spd)
            sun_series.append(sun_spd)
            n_physical += 1
        else:
            sky_series.append(None)
            sun_series.append(None)
            n_template += 1
    n = len(timestamps)
    coverage = {"n_physical": n_physical, "n_template": n_template,
                "coverage_pct": (100.0 * n_physical / n) if n else 0.0}
    return sky_series, sun_series, coverage

def _build_record_index(epw, timestamps, real_timestamps, engine=None):
    """Memoized {(m,d,hour_ending): record} from the EPW — one record_from_epw call per UNIQUE hour-ending.
    A missing/unparseable hour is simply absent (→ per-step template fallback). Synthetic timestamps → {}.
    engine: optional SpectralEngine instance (None → record_from_epw's spectrl2 default)."""
    if not (epw and real_timestamps):
        return {}
    from hcl_core.spectral_pipeline import record_from_epw
    index, seen = {}, set()
    for (m, d, h) in timestamps:
        key = (m, d, min(24, max(1, math.ceil(h))))
        if key in seen:
            continue
        seen.add(key)
        try:
            index[key] = record_from_epw(epw, key[0], key[1], key[2], engine=engine)
        except ValueError:
            pass   # record_from_epw raises ValueError for a missing row / LOCATION → absent → template
                   # fallback for those steps. Narrowed from `except Exception` so a real integration
                   # break (e.g. a record_from_epw signature change) surfaces instead of hiding as 0% coverage.
    return index

def _representative_timestep(series):
    """Index of the timestep the single-shot `divergence` comparison should use.

    Picks PEAK SUN — the step whose direct-sun channels sum highest. The comparison it feeds
    contrasts a colored against a neutral sun, so a step with no sun makes it degenerate: the
    percent-difference guard divides zero by zero and reports exactly 0.0, which reads as "the
    sun's spectral treatment is immaterial" rather than "this step has no sun". Selecting on
    non-zero SKY instead lands on a pre-sunrise step on any real year and does exactly that.

    Falls back to the brightest SKY step when the sun never rises (fully overcast series), and
    to 0 when the series is empty or wholly dark.
    """
    if not series:
        return 0
    sun_tot = [sum(t[1]) for t in series]
    best = max(range(len(series)), key=lambda t: sun_tot[t])
    if sun_tot[best] > 1e-12:
        return best
    sky_tot = [sum(t[0]) for t in series]
    best_sky = max(range(len(series)), key=lambda t: sky_tot[t])
    return best_sky if sky_tot[best_sky] > 1e-12 else 0


def _run_nvrd_for_method(point_xyz, view_vec, timestamps, series, *, method, channel_type,
                         timestep_h, sun_spectral, dseries_sky, sky_cct, solar_zeniths,
                         sky_spd_series=None, sun_spd_series=None):
    rows = assemble_nvrd_rows(point_xyz, view_vec, timestamps, series, method=method,
                              channel_type=channel_type, sun_spectral=sun_spectral,
                              solar_zenith=solar_zeniths, dseries_sky=dseries_sky, sky_cct=sky_cct,
                              sky_spd_series=sky_spd_series, sun_spd_series=sun_spd_series)
    res = _nvrd([r[12:] for r in rows], timestep_h=timestep_h)
    return {"R_D": res["relative_response"], "RD_cum": res["cumulative_response"]}

def annual_nvrd(*, point_xyz, view_vec, timestep_min=6, reconstruction="both",
                sky_reconstruction="reference", sun_spectral="colored", sky_cct=None,
                epw=None, channel_scenes=None, points=None, channel_type=1,
                rad_params=None, work_dir=None, run=True, physical_sky=False,
                engine=None, _record_provider=None, _channel_provider=None):
    """Annual alertness (R_D) from weather via the dual-reconstruction bridge.

    reconstruction: 'both' (default) | 'faithful' | 'enhanced'.
    sky_reconstruction: 'reference' (static/default sky shape) | 'dseries' (per-timestep CIE D-series
      sky from sky_cct). sun_spectral: 'colored' (air-mass solar) | 'neutral' (sim-faithful flat).
    SINGLE reference point + view per run (spec §5.1). timestep_min default 6 (0.1 h) for the nvRD
    δ<=0.3 h guard.

    Site location is taken from the EPW (via Plan 09's generate_subhourly_wea, which converts the EPW
    LOCATION line to DAYSIM convention) — the bridge never accepts raw caller coordinates, so there is
    no way to silently feed wrong solar geometry into the live path.

    _channel_provider: test/advanced hook -> {timestamps, series:[(sky_ch,sun_ch)...], channel_type,
      solar_zeniths}. When omitted, the production path runs Daysim + the separated annual transport.
    """
    timestep_h = timestep_min / 60.0
    dseries_sky = (sky_reconstruction == "dseries")
    real_ts_flag = False   # defensive default; both branches below set it before any physical_sky use

    # --- obtain per-timestep channels + timestamps ---
    if _channel_provider is not None:
        prov = _channel_provider()
        timestamps = prov["timestamps"]
        series = prov["series"]
        channel_type = prov.get("channel_type", channel_type)
        solar_zeniths = prov.get("solar_zeniths")
        real_ts_flag = bool(prov.get("timestamps"))
    else:
        # production path: Daysim sub-hourly .wea -> separated annual transport
        missing_inputs = [n for n, v in (("epw", epw), ("channel_scenes", channel_scenes),
                                         ("points", points)) if not v]
        if missing_inputs:
            raise ValueError(
                f"annual_nvrd requires {', '.join(missing_inputs)} for the production path "
                "(or pass _channel_provider with a precomputed channel series).")
        wd = work_dir or os.path.expanduser("~/hcl_work")
        os.makedirs(wd, exist_ok=True)
        commands = []
        # 1) sub-hourly .wea via Daysim (Plan 09). Emit on run=False or if the adapter is unavailable.
        #    generate_subhourly_wea (hcl_daysim.subhourly) derives the site location from the EPW
        #    LOCATION line itself (converting to DAYSIM convention), so the bridge passes NO coordinates
        #    — there is no caller-supplied-coordinate path that could silently corrupt the solar geometry.
        try:
            from hcl_daysim.subhourly import generate_subhourly_wea  # Plan 09 (EPW-derived location)
        except Exception:
            generate_subhourly_wea = None
        if generate_subhourly_wea is None:
            commands.append("# Daysim adapter unavailable: build Daysim or set HCL_DAYSIM_BIN (Plan 09)")
            wea_res = {"ran": False, "commands": ["epw2wea <epw> <wea>", "ds_shortterm <hea>"], "wea": None}
        else:
            wea_res = generate_subhourly_wea(epw, timestep_min=timestep_min, work_dir=wd, run=run)
        commands += wea_res.get("commands", [])
        wea = wea_res.get("wea")
        # 2) separated annual transport on the sub-hourly .wea
        from hcl_radiance.annual import run_annual_separated
        kw = {"work_dir": wd, "run": run and bool(wea)}
        if rad_params:
            kw["rad_params"] = rad_params
        ann = run_annual_separated(channel_scenes, wea or "<subhourly.wea>", points, channel_type, **kw)
        commands += ann.get("commands", [])
        if not (wea_res.get("ran") and ann.get("ran")):
            # DEF-7: when the caller passed run=False, that is the reason — do not surface a downstream
            # "Radiance not available" message that misleads a user whose engines ARE installed. Only
            # when run=True (a genuine degrade) do we surface the specific step reason (e.g. a missing
            # Reinhart .cal, DEF-4), falling back to the generic message when none is available.
            if not run:
                reason = ("run=False: emitted the full Daysim + separated-annual command plan "
                          "(no execution requested).")
            else:
                reason = (ann.get("reason") or wea_res.get("reason")
                          or "Daysim and/or Radiance unavailable; full command plan emitted.")
            return {"ran": False, "commands": commands, "reason": reason,
                    "relative_RD_note": _RELATIVE_NOTE}
        sky_ch = _regroup_to_channels(ann["sky_sets"], channel_type)
        sun_ch = _regroup_to_channels(ann["sun_sets"], channel_type)
        series = list(zip(sky_ch, sun_ch))
        # timestamps + solar zeniths from the .wea (the adapter/weather decompose supplies these);
        # if not surfaced, synthesize a uniform grid and a default zenith (documented limitation).
        # An EMPTY list ([]) must NOT silently re-enable the synthetic grid / constant-zenith path:
        # treat empty exactly like missing so the enhanced_solar_note guard still fires (XCUT-1).
        wea_ts = wea_res.get("timestamps")
        timestamps = wea_ts if wea_ts else [(1, 1, i * timestep_h) for i in range(len(series))]
        wea_zen = wea_res.get("solar_zeniths")
        solar_zeniths = wea_zen if wea_zen else None
        real_ts_flag = bool(wea_ts)

    # --- run nvRD under the requested method(s) ---
    out = {"ran": True, "n_timesteps": len(series), "timestep_h": timestep_h,
           "relative_RD_note": _RELATIVE_NOTE}
    sky_series = sun_series = None
    phys_cov = None
    if physical_sky:
        index = _record_provider() if _record_provider is not None else \
            _build_record_index(epw, timestamps, real_ts_flag, engine=engine)
        sky_series, sun_series, phys_cov = _physical_spd_series(index or {}, timestamps,
                                                                real_timestamps=real_ts_flag)
    if reconstruction in ("both", "faithful"):
        out["faithful"] = _run_nvrd_for_method(point_xyz, view_vec, timestamps, series,
                                               method="faithful", channel_type=channel_type,
                                               timestep_h=timestep_h, sun_spectral="neutral",
                                               dseries_sky=False, sky_cct=sky_cct,
                                               solar_zeniths=solar_zeniths)
    if reconstruction in ("both", "enhanced"):
        out["enhanced"] = _run_nvrd_for_method(point_xyz, view_vec, timestamps, series,
                                               method="reference", channel_type=channel_type,
                                               timestep_h=timestep_h, sun_spectral=sun_spectral,
                                               dseries_sky=dseries_sky, sky_cct=sky_cct,
                                               solar_zeniths=solar_zeniths,
                                               sky_spd_series=sky_series, sun_spd_series=sun_series)
    if reconstruction == "both":
        rep = _representative_timestep(series)
        sky0, sun0 = series[rep]
        zen0 = (solar_zeniths[rep] if isinstance(solar_zeniths, (list, tuple)) else solar_zeniths)
        rep_sky_spd = sky_series[rep] if (physical_sky and sky_series) else None
        out["divergence"] = reconstruction_divergence(sky0, sun0, channel_type, sky_spd=rep_sky_spd,
                                                       solar_zenith=zen0, dseries_sky=dseries_sky,
                                                       sky_cct=sky_cct)
        if rep_sky_spd is not None:
            out["divergence_note"] = (
                "Single-timestep `divergence` uses the PHYSICAL sky shape but the TEMPLATE sun "
                "(reconstruction_divergence has no sun_spd); RD_series_divergence is the physics-aware "
                "enhanced-vs-faithful delta.")
        # R_D-series divergence: how much the reconstruction CHOICE actually moves the alertness
        # result over the whole run (the spectral `divergence` above is a single-timestep proxy).
        f_rd, e_rd = out["faithful"]["R_D"], out["enhanced"]["R_D"]
        absdiff = [abs(e - f) for e, f in zip(e_rd, f_rd)]
        f_cum = out["faithful"]["RD_cum"][-1] if out["faithful"]["RD_cum"] else 0.0
        e_cum = out["enhanced"]["RD_cum"][-1] if out["enhanced"]["RD_cum"] else 0.0
        out["RD_series_divergence"] = {
            "mean_abs": sum(absdiff) / len(absdiff) if absdiff else 0.0,
            "max_abs": max(absdiff) if absdiff else 0.0,
            "final_cum_pct": (100.0 * (e_cum - f_cum) / f_cum) if abs(f_cum) > 1e-15 else 0.0,
        }
    if physical_sky:
        cov = phys_cov or {"n_physical": 0, "n_template": len(series), "coverage_pct": 0.0}
        out["physical_sky"] = {
            "requested": True, **cov,
            "note": (f"Enhanced reconstruction used physical EPW-derived sky/sun shapes for "
                     f"{cov['n_physical']}/{len(series)} timesteps ({cov['coverage_pct']:.1f}%); the rest "
                     f"fell back to the reference-sky / air-mass-sun template. Shape-only — per-bin "
                     f"transport totals are unchanged."),
        }
    full_physics = bool(physical_sky and phys_cov and phys_cov["n_template"] == 0)
    if "enhanced" in out and solar_zeniths is None and not full_physics:
        # Under partial physics coverage only the template-FALLBACK steps use the 30° template sun;
        # the physics-covered steps carry a time-resolved physical sun. Say so accurately.
        scope = ("the template-fallback timesteps"
                 if (physical_sky and phys_cov and phys_cov["n_physical"]) else "ALL timesteps")
        out["enhanced_solar_note"] = (
            f"Per-timestep solar zeniths were unavailable, so the enhanced colored-sun used a constant "
            f"30° zenith for {scope} (air-mass reddening is NOT time-resolved). Supply solar_zeniths "
            f"(e.g. via _channel_provider, or once Daysim surfaces per-timestep sun positions) for the "
            f"fully time-resolved enhanced reconstruction.")
    return out
