"""Caller-facing advisories attached to MCP tool results.

REPORTING ONLY. Every rule reads a field `hcl_core` already computed and phrases a
caution about it. Nothing here recomputes a physical quantity, touches the filesystem,
or shells out — that would put physics in the protocol layer (see CONTEXT.md).

A rule takes (tool, args, result) and returns a list of advisories or None. Rules are
registered with @rule and evaluated in registration order. A rule that raises is skipped:
an advisory is never worth failing a tool call over.
"""

from hcl_core.lighting_controls import _WEIGHT_EPS  # single source of truth for the tolerance

_RULES = []


def rule(fn):
    """Register an advisory rule. Returns fn unchanged so it stays directly testable."""
    _RULES.append(fn)
    return fn


def _advisory(code, severity, message, *, field=None):
    a = {"code": code, "severity": severity, "message": message}
    if field is not None:
        a["field"] = field
    return a


def _iter_dicts(result):
    """Yield every dict in a result. Tools like circadian_metrics return a list of
    per-point dicts when given many points (hcl_core/metrics.py, the multi-point branch).

    The list branch is UNREACHABLE in production: `_attach` (hcl_mcp/server.py)
    returns non-dict results untouched, so a rule is never called with a list from the
    registration seam. It is kept for direct callers and tests — do not read it as
    evidence that multi-point list results carry advisories, because they do not.
    """
    if isinstance(result, dict):
        yield result
    elif isinstance(result, list):
        for item in result:
            if isinstance(item, dict):
                yield item


def advise(tool, args, result):
    """All advisories for one tool call. Never raises."""
    out = []
    for fn in _RULES:
        try:
            got = fn(tool, args or {}, result)
        except Exception:
            continue
        if got:
            out.extend(got)
    return out


_BINNED_MESSAGE = (
    "mel-EDI was inferred from binned channels, not a full spectrum: exact for "
    "D65, within ~1.5% for smooth spectra, but up to ~8% high for a narrow-band "
    "source whose lines fall inside a bin. Pass spd= for an exact value.")

# Per-block guidance for a run_grid result, where "pass spd=" is not the action. Absent from
# this map means the generic message above.
_BINNED_BY_BLOCK = {
    "electric": (
        "The `electric` block's mel-EDI was inferred from binned channels, because the driven "
        "luminaires do not share one spectrum — they carry different `spd`/`preset` values, or "
        "none at all. That is the ~8%-high case exactly: a fluorescent's emission lines fall "
        "inside a bin. Give every luminaire the same `spd` (or `preset`) and the block moves to "
        "the transported route."),
    "combined": (
        "The `combined` block's mel-EDI was inferred from binned channels. It is a two-source "
        "mixture with no single source spectrum, so this route is unavoidable there — but its "
        "error grows with the electric share, reaching the full ~8% when luminaires dominate. "
        "mel-EDI is additive (melanopic irradiance is linear in the spectrum), so read "
        "`daylight` and `electric` separately and ADD their `mel_edi`: measured, the parts stay "
        "within ~0.4% where the mixture runs up to 8.1% high."),
}


_METRIC_BLOCKS = ("daylight", "electric", "combined")


def _point_metrics(result):
    """Yield (block, metrics_dict) for every per-point metrics dict in a result.

    `block` is the condition block's name for a `run_grid`-shaped result, and None when the
    metrics dict IS the result (single-point `circadian_metrics`). Rules need the name because
    the right caution differs per block — see `_mel_der_binned`.

    Two shapes carry per-point metrics and both must be covered, because a rule that reads a
    per-point field off the top level alone silently never fires on the tool where that field
    actually appears:
    - `circadian_metrics` (single point) returns the metrics dict itself;
    - `run_grid` nests one `metrics` list per condition block (hcl_radiance/grid.py), so nothing
      per-point is ever top-level there.
    """
    for d in _iter_dicts(result):
        yield None, d
        for block in _METRIC_BLOCKS:
            b = d.get(block)
            if not isinstance(b, dict):
                continue
            for m in (b.get("metrics") or []):
                if isinstance(m, dict):
                    yield block, m


@rule
def _mel_der_binned(tool, args, result):
    """mel-EDI inferred from channel averages rather than a full spectrum.

    Walks the nested per-point blocks as well as the top level, so it reaches a `run_grid`
    result — it read only the top level for a long time, and `run_grid` puts nothing per-point
    there, so it had never once fired on the tool where most channels are produced.

    The `daylight` block is deliberately EXEMPT. It is the one block whose spectrum is a smooth
    sky, where the binned route costs ~0.13% (methodology §"mel-DER accuracy"), and where there
    is no single source spectrum to pass instead — so the caller can neither act on the warning
    nor be misled without it. Since `daylight` is present on every single run, warning there
    would put a permanent, unactionable, ~60x-overstated caution on every result and teach
    people to skip the advisories block. `electric`/`combined` exist only when luminaires were
    driven, which is exactly when a narrow-band source can make the ~8% real.
    """
    for block, r in _point_metrics(result):
        if r.get("mel_der_source") != "binned_channels":
            continue
        if block == "daylight":
            continue
        return [_advisory("MEL_DER_BINNED", "warn",
                          _BINNED_BY_BLOCK.get(block, _BINNED_MESSAGE),
                          field="mel_der_source")]
    return None


# Below this the shift is inside the binned route's own accuracy band (~1.5% on smooth spectra)
# and saying so would be noise. Above it, the number a reader is most likely to cross-check
# against — the luminaire's datasheet mel-DER — disagrees with the reported one, on purpose.
_TRANSPORT_SHIFT_PCT = 5.0


@rule
def _spectral_transport_shift(tool, args, result):
    """The room moved the spectrum away from the luminaire's own.

    Not a defect and not a caution about validity: the reported mel-DER is the correct at-point
    value (ADR-0006). It fires because the mismatch against a datasheet figure is otherwise
    unexplained, and because the size of the shift is itself a finding about the room.

    Reports the LARGEST shift over the points, since one advisory stands for the whole result and
    the worst point is the one most likely to be misread.
    """
    worst = None
    for _block, r in _point_metrics(result):
        ratio = r.get("transport_ratio")
        if not isinstance(ratio, (int, float)) or isinstance(ratio, bool):
            continue
        if worst is None or abs(1.0 - ratio) > abs(1.0 - worst):
            worst = ratio
    if worst is None:
        return None
    shift = abs(1.0 - worst) * 100.0
    if shift < _TRANSPORT_SHIFT_PCT:
        return None
    direction = "lower" if worst < 1 else "higher"
    return [_advisory(
        "SPECTRAL_TRANSPORT_SHIFT", "warn",
        f"The room shifted the spectrum up to {shift:.1f}% from the luminaire's own, so mel-DER "
        f"is {direction} than the source value in `source_mel_der` (worst point). `mel_der` and "
        "`mel_edi` are the AT-POINT quantities and are the ones to report; the luminaire's "
        "datasheet figure will not match them, and should not.",
        field="transport_ratio")]


@rule
def _electric_exceeds_lumen_bound(tool, args, result):
    """The electric-only block reports more light than the luminaires can emit.

    Reads the bound hcl_radiance computed (`electric.lumen_bound`); no physics here. Mean
    illuminance above sum(luminaire lumens)/area means the block is counting light no fixture in
    the scene produced — most often a sky that reached the "electric-only" octree, but any
    double-count or wrong multiplier lands here too.
    """
    if not isinstance(result, dict):
        return None
    bound = (result.get("electric") or {}).get("lumen_bound")
    if not isinstance(bound, dict) or not bound.get("exceeded"):
        return None
    mean_lux, ceiling = bound.get("mean_lux"), bound.get("ceiling_lux")
    over = (mean_lux / ceiling) if ceiling else 0.0
    return [_advisory(
        "ELECTRIC_EXCEEDS_LUMEN_BOUND", "error",
        f"The electric-only block averages {mean_lux:g} lx, {over:.1f}x the "
        f"{ceiling:g} lx ceiling set by {bound.get('lamp_lumens'):g} lm over "
        f"{bound.get('area_m2'):g} m2. No room reaches perfect utilisation, so this block is "
        "counting light the luminaires did not emit — check that no sky reached the electric "
        "octree (pass sky_files= to run_grid to name them exactly), and that fixture counts and "
        "multipliers are not applied twice.",
        field="electric.lumen_bound")]


DEFAULT_DOSE_THRESHOLD = 250.0  # mirrors run_annual's dosimetry_threshold default in hcl_mcp/server.py


@rule
def _albedo_not_measured(tool, args, result):
    """Ground reflectance came from a documented default, not an instrument.

    IWEC/TMY2 files write a literal 0.000 albedo for every hour instead of the 999.0
    sentinel, so hcl_core treats sub-physical values as missing and substitutes
    (ADR-0004). The substituted value is correct practice; reporting it as measured
    is not.

    atmosphere_from_epw returns the AtmosphericState dict directly, so its provenance
    map is top-level. spectral_sky_from_epw wraps it a level down instead
    (hcl_core.spectral_emit.record_to_dict nests the same AtmosphericState under an
    "atmosphere" key) — checked here too so the higher-traffic tool isn't silently
    uncovered.
    """
    if not isinstance(result, dict):
        return None
    entry = (result.get("provenance") or {}).get("albedo")
    if not isinstance(entry, dict):
        entry = ((result.get("atmosphere") or {}).get("provenance") or {}).get("albedo")
    if isinstance(entry, dict) and entry.get("source") == "default":
        return [_advisory(
            "ALBEDO_NOT_MEASURED", "warn",
            "Ground albedo is a documented default, not a measured value — the EPW "
            "supplied none, or supplied a sub-physical one. Diffuse irradiance on tilted "
            "surfaces is sensitive to it; pass an override if the site is known.",
            field="albedo")]
    return None


@rule
def _dose_threshold_is_default(tool, args, result):
    """Dosimetry was summarised against the built-in threshold.

    Value-based, not provenance-based: FastMCP fills unset parameters with their
    declared defaults before the call, so a wrapper cannot tell a deliberate 250.0
    from an absent argument. The advice holds either way.
    """
    if not isinstance(result, dict):
        return None
    dose = result.get("dosimetry")
    if isinstance(dose, dict) and dose.get("threshold") == DEFAULT_DOSE_THRESHOLD:
        return [_advisory(
            "DOSE_THRESHOLD_IS_DEFAULT", "info",
            f"Dosimetry used the default {DEFAULT_DOSE_THRESHOLD:g} lx mel-EDI threshold. "
            "Confirm it is the one your standard or brief requires before quoting "
            "hours_above.",
            field="dosimetry.threshold")]
    return None


_WEIGHT_TOOLS = frozenset({"lighting_controls", "daylight_savings"})


@rule
def _zone_weight_remainder(tool, args, result):
    """Zone weights leave part of the floor uncontrolled.

    Sum < 1 is documented, intended behaviour: the leftover is the uncontrolled core
    billed at full power (stated in daylight_savings' docstring, hcl_mcp/server.py). This is NOT a validity check. It
    quantifies the remainder, because weights carrying one convention (photosensors
    zone weights) read as another (floor-area fractions) change the savings figure
    substantially without changing the shape of the result.
    """
    if tool not in _WEIGHT_TOOLS:
        return None
    weights = args.get("weights")
    if not isinstance(weights, (list, tuple)) or not weights:
        return None
    try:
        total = sum(float(w) for w in weights)
    except (TypeError, ValueError):
        return None
    if total >= 1.0 - _WEIGHT_EPS:
        return None
    remainder_pct = round((1.0 - total) * 100.0, 1)
    return [_advisory(
        "ZONE_WEIGHT_REMAINDER", "warn",
        f"Zone weights sum to {total:.3f}, so {remainder_pct}% of the floor is billed at "
        "full power as uncontrolled core. That is correct if these are floor-area "
        "fractions from area_weights_from_geometry; it is not if they came from "
        "photosensors zone weights, which use a different convention.",
        field="weights")]


def _skipped_category(entry):
    """Name of one `skipped` entry. build_report emits DICTS of
    {"category", "reason"} (hcl_radiance/geometry_health.py:684); a bare string is
    tolerated so the rule never renders a raw dict repr into caller-facing text."""
    if isinstance(entry, dict):
        return str(entry.get("category", entry))
    return str(entry)


def _health_report(result):
    """The geometry health report carried by `result`, or None.

    Two shapes carry the same report and both must be covered:
    - import_geometry EMBEDS it under `health` (hcl_mcp/server.py:454);
    - check_geometry RETURNS it directly (hcl_mcp/server.py:529), so `ok`/`counts`/
      `findings`/`skipped` sit at the top level with no wrapper. Looking only under
      `health` left the dedicated health-check tool as the one tool that never warns.

    The top-level shape is recognised structurally (`ok` AND `counts` present) rather
    than by tool name, and no more broadly than that.
    """
    if not isinstance(result, dict):
        return None
    health = result.get("health")
    if isinstance(health, dict):
        return health
    if "ok" in result and "counts" in result:
        return result
    return None


@rule
def _geometry_health_unclean(tool, args, result):
    """The geometry health report is not clean.

    Fires ONLY on a real defect: `ok` false, or a non-zero warning count. NOT on a
    non-empty `skipped`, which is structurally never empty — check_geometry_health
    always appends the tier-1 categories plus a `sensors` and a `luminaires` entry on
    every branch (hcl_radiance/geometry_health.py:684-695), so triggering on it warned
    on every single import, spotless report included. The skipped CATEGORIES are still
    named once the rule fires, where they are useful context rather than noise.
    """
    health = _health_report(result)
    if health is None:
        return None
    counts = health.get("counts") or {}
    ok = health.get("ok", True)
    warnings = counts.get("warning") or 0
    if ok and not warnings:
        return None
    parts = []
    if not ok:
        parts.append(f"{counts.get('error', 0)} error(s)")
    if warnings:
        parts.append(f"{warnings} warning(s)")
    skipped = health.get("skipped") or []
    if skipped:
        parts.append("not checked: " + ", ".join(_skipped_category(s) for s in skipped))
    return [_advisory(
        "GEOMETRY_HEALTH_UNCLEAN", "error" if not ok else "warn",
        "Geometry health report is not clean — " + "; ".join(parts) +
        ". Each finding carries a `fix`; a silent geometry defect still returns a "
        "plausible number.",
        field="health" if isinstance(result.get("health"), dict) else None)]


@rule
def _nvrd_zero_divergence(tool, args, result):
    """An exactly-zero single-shot divergence is a timestep artefact.

    The single-shot comparison picks one representative timestep. When that lands on a
    pre-sunrise hour every sun channel is zero, so neutral and coloured suns agree
    exactly and the divergence reads 0.
    """
    if tool != "annual_nvrd" or not isinstance(result, dict):
        return None
    pair = (result.get("divergence") or {}).get("neutral_vs_colored_sun")
    if isinstance(pair, dict) and pair.get("mel_edi_pct") == 0:
        return [_advisory(
            "NVRD_ZERO_DIVERGENCE", "warn",
            "neutral_vs_colored_sun divergence is exactly 0, which almost always means the "
            "representative timestep fell on an hour with no sun rather than that the "
            "spectra agree. Quote RD_series_divergence instead.",
            field="divergence.neutral_vs_colored_sun")]
    return None


@rule
def _radiance_drops_ies_candela_scale(tool, args, result):
    """This Radiance build ignores the ies2rad A1 candela scale, so IES luminaires under-emit.

    Keys off the engine stamp rather than off an `electric` block, because the two paths that
    render luminaires report them differently: the grid path carries `electric`, while the
    image path (glare_ugr / run_image) carries only `total_wattage`. The stamp is written by
    exactly the runs that rendered IES luminaires, so it is the condition that matches both
    without flagging a daylight-only run, whose sky path never references A1.
    """
    if not isinstance(result, dict):
        return None
    cal = (result.get("engine") or {}).get("source_cal") or {}
    if cal.get("a1_honored") is not False:
        return None
    return [_advisory(
        "RADIANCE_DROPS_IES_CANDELA_SCALE", "error",
        "This Radiance build does not apply the ies2rad A1 candela-scale multiplier, so every "
        "IES luminaire in this run emitted at unit scale and the electric illuminances are low "
        "by each luminaire's own candela scale. Glare metrics are affected the same way and "
        "collapse toward zero. Because the factor differs per luminaire, these numbers cannot "
        "be rescaled and must be re-run. Fix without touching the Radiance install: set "
        "HCL_RADIANCE_SHIM=1, which puts a corrected source.cal on RAYPATH for every run.",
        field="engine.source_cal")]
