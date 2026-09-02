"""Study-brief persistence and report rendering for the hcl_studio guided journey (spec 2026-06-11)."""
import json
import os
import re

_PHASE_KEYS = ("orient", "goal", "space", "daylight_baseline", "fixture_spec",
               "sim_results", "energy", "compliance")


def _d65_mel_phot_ratio_9():
    """D65's own melanopic/photopic ratio on the 9-bin route (~1.0997).

    Only needed to rescue a legacy brief that stored `melanopic_lux` instead of mel-EDI. Derived
    from the shared D65 reference rather than hardcoded so it cannot drift from `hcl_core.metrics`.
    """
    from hcl_core.metrics import _d65_ratio
    return _d65_ratio(1)


_D65_MEL_PHOT_RATIO_9 = _d65_mel_phot_ratio_9()
# Keys a brief may legitimately carry: the phase slots plus the study slug.
_ALLOWED_BRIEF_KEYS = frozenset(_PHASE_KEYS) | {"study"}

# Common natural-language key typos -> the canonical phase slot, for a "did you mean" hint when
# save_brief rejects an unknown key (DEF-6). Maps lowercased input keys to allowed slots.
_BRIEF_KEY_ALIASES = {
    "fixtures": "fixture_spec", "fixture": "fixture_spec", "luminaire": "fixture_spec",
    "annual": "sim_results", "sim": "sim_results", "results": "sim_results",
    "simulation": "sim_results", "grid": "sim_results",
    "daylight": "daylight_baseline", "baseline": "daylight_baseline",
    "compliances": "compliance", "standards": "compliance",
    "energy_savings": "energy", "savings": "energy",
    "goals": "goal", "target": "goal", "room": "space", "geometry": "space",
}

# A study slug becomes a directory name, and it arrives from MCP tool arguments, so it must not be
# able to traverse out of the work dir. Restrict to a filename-safe token and reject "."/"..".
_SAFE_STUDY = re.compile(r"^[A-Za-z0-9._-]+$")


def _safe_study(study: str) -> str:
    """Validate a study slug used as a directory name; raise ValueError if it could traverse paths."""
    if not isinstance(study, str) or study in (".", "..") or not _SAFE_STUDY.match(study):
        raise ValueError(
            "study must match [A-Za-z0-9._-]+ with no path separators (got %r)" % (study,))
    return study


def empty_brief(study: str) -> dict:
    """A fresh brief skeleton: study slug + one null slot per phase."""
    b: dict[str, str | None] = {"study": study}
    b.update({k: None for k in _PHASE_KEYS})
    return b


def _brief_path(study_dir: str, study: str) -> str:
    return os.path.join(study_dir, _safe_study(study), "brief.json")


def load_brief_from_dir(study_dir: str, study: str) -> dict:
    """Read brief.json under study_dir/<study>/; return an empty skeleton if absent."""
    path = _brief_path(study_dir, study)
    if not os.path.exists(path):
        return empty_brief(study)
    with open(path) as fh:
        return json.load(fh)


def save_brief_to_dir(study_dir: str, study: str, brief: dict) -> str:
    """Shallow per-top-level-key merge of `brief` into the stored brief; write and return the path.

    A phase passing only the keys it changed leaves the others intact. Unknown top-level keys are
    rejected (raise ValueError) so a typo'd phase name fails loudly rather than silently corrupting
    the schema; the only accepted keys are the phase slots plus "study" (which the slug param always
    overrides — see below).
    """
    unknown = set(brief) - _ALLOWED_BRIEF_KEYS
    if unknown:
        hints = []
        for k in sorted(unknown):
            suggestion = _BRIEF_KEY_ALIASES.get(k.lower())
            if suggestion:
                hints.append("%r -> did you mean %r?" % (k, suggestion))
        suffix = (" (" + "; ".join(hints) + ")") if hints else ""
        raise ValueError("unknown brief key(s) %s; allowed: %s%s"
                         % (sorted(unknown), sorted(_ALLOWED_BRIEF_KEYS), suffix))
    path = _brief_path(study_dir, study)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    current = load_brief_from_dir(study_dir, study)
    for k, v in brief.items():
        current[k] = v
    current["study"] = _safe_study(study)  # slug param is canonical — always wins over any "study" in `brief`
    with open(path, "w") as fh:
        json.dump(current, fh, indent=2)
    return path


def _row(label, target, achieved, lower_is_better=False):
    """One target-vs-achieved row. lower_is_better flips the pass test (for UGR etc.)."""
    shown_target = target if target not in ("", None) else "—"
    if achieved is None:
        return f"| {label} | {shown_target} | _not evaluated_ | — |"
    if target in ("", None):
        return f"| {label} | — | {achieved} | — |"
    try:
        t, a = float(target), float(achieved)
        ok = "✅" if (a <= t if lower_is_better else a >= t) else "❌"
    except (TypeError, ValueError):
        ok = "—"
    return f"| {label} | {target} | {achieved} | {ok} |"


def _first(d: dict, *keys, default="?"):
    """First present (non-None, non-empty) value among alias keys, else `default`. Lets the report
    renderer accept the natural key shapes upstream tools/users save (DEF-5)."""
    for k in keys:
        v = d.get(k)
        if v not in (None, ""):
            return v
    return default


def _render_markdown(brief: dict) -> str:
    # ISSUE-2: a phase field given as a non-dict (e.g. goal="office") must degrade to {} -> "not
    # evaluated", not crash later on `.get` ('str' object has no attribute 'get').
    def _d(key):
        v = brief.get(key)
        return v if isinstance(v, dict) else {}
    g = _d("goal")
    sp = _d("space")
    dl = _d("daylight_baseline")
    fx = _d("fixture_spec")
    sim = _d("sim_results")
    en = _d("energy")
    comp = brief.get("compliance") or []
    L = ["# HCL Study Report — %s" % brief.get("study", "?"), "",
         "> Values are ILLUSTRATIVE where SPD/utilance were estimated; confirm against the real IES "
         "and the Radiance grid.", ""]

    L += ["## Goal"]
    if g:
        L += ["- Circadian standard: **%s**, target mel-EDI **%s** at %s (condition: %s)" %
              (g.get("standard"), g.get("mel_edi_target"), g.get("measurement_plane", "?"),
               g.get("condition", "?")),
              "- Visual task: **%s**, Ēm %s lx, UGR ≤ %s, Uo ≥ %s, Ra ≥ %s" %
              (g.get("visual_task"), g.get("em_lux"), g.get("ugr_max"), g.get("uo_min"), g.get("ra_min"))]
    else:
        L += ["_not evaluated_"]

    L += ["", "## Space"]
    if sp:
        # DEF-5: accept the natural shapes an upstream tool / user is likely to save — L/W/H, lower-case
        # l/w/h, length/width/height, or a [L,W,H] list under dimensions/bbox_m/size — so a round-trip
        # populates the report instead of rendering "? × ? × ?".
        dims = sp.get("dimensions") or sp.get("bbox_m") or sp.get("size")
        if isinstance(dims, (list, tuple)) and len(dims) >= 3:
            dL, dW, dH = dims[0], dims[1], dims[2]
        else:
            dL = _first(sp, "L", "l", "length", "length_m")
            dW = _first(sp, "W", "w", "width", "width_m")
            dH = _first(sp, "H", "h", "height", "height_m")
        L += ["- Dimensions: %s × %s × %s m (mounting %s m, work-plane %s m, eye %s m)" %
              (dL, dW, dH,
               _first(sp, "mount_h", "mounting_h"), _first(sp, "workplane_h"), _first(sp, "eye_h")),
              "- Reflectances %s, maintenance factor %s" %
              (_first(sp, "rho", "reflectances"), _first(sp, "mf", "maintenance_factor"))]
    else:
        L += ["_not evaluated_"]

    L += ["", "## Daylight Baseline"]
    if dl:
        L += ["- Daylight contribution at the reference: %s lx photopic, %s lx mel-EDI "
              "(condition: %s, source: %s). Credits the circadian budget only — not the installed "
              "visual flux." %
              (dl.get("e_daylight_lux", "?"), dl.get("mel_edi_daylight", "?"),
               dl.get("condition", "?"), dl.get("source", "?"))]
    else:
        L += ["_not evaluated_"]

    L += ["", "## Fixture Spec"]
    if fx:
        # DEF-5: recommend_fixtures emits required_flux_lm/fixture_count/target_cct_band/... ; accept
        # those plus shorter aliases a user might hand-enter so the section never blanks out.
        L += ["- Required flux: **%s lm**, count **%s**, CCT band %s" %
              (_first(fx, "required_flux_lm", "required_flux"),
               _first(fx, "fixture_count", "count"),
               _first(fx, "target_cct_band", "cct_band")),
              "- Binding constraint: **%s**, power density %s W/m²" %
              (_first(fx, "binding_constraint", "binding"),
               _first(fx, "power_density_w_m2", "power_density"))]
    else:
        L += ["_not evaluated_"]

    # Prefer the true CIE S 026 mel-EDI. A brief saved before mel_edi was returned may carry only
    # `melanopic_lux`; that is NOT mel-EDI (larger by D65's melanopic/photopic ratio), so grading it
    # against a mel-EDI target would manufacture a false PASS near threshold. Convert it via the
    # brief's own mel_der when available, and flag the row when only the approximate route exists
    # (DEF-7 keeps the round-trip working; it must not silently change the quantity).
    mel_achieved = sim.get("mel_edi")
    mel_approx = False
    if mel_achieved is None and sim.get("melanopic_lux") is not None:
        ph, der = sim.get("photopic_lux"), sim.get("mel_der")
        if ph is not None and der is not None:
            mel_achieved = round(ph * der, 2)        # exact S 026 relation: mel-EDI = E_v x mel-DER
        else:
            mel_achieved = round(sim["melanopic_lux"] / _D65_MEL_PHOT_RATIO_9, 2)
            mel_approx = True
    L += ["", "## Target vs Achieved", "",
          "| Metric | Target | Achieved | Pass |", "|---|---|---|---|",
          _row("Photopic Ēm (lx)", g.get("em_lux"), sim.get("photopic_lux")),
          _row("mel-EDI (lx)", g.get("mel_edi_target"), mel_achieved),
          _row("UGR (≤)", g.get("ugr_max"), sim.get("ugr"), lower_is_better=True),
          _row("Energy saved (kWh/m²·yr)", "", en.get("savings_kwh_m2_yr"))]

    if mel_approx:
        L += ["", "_⚠️ mel-EDI derived from a legacy `melanopic_lux` brief by dividing out D65's "
              "melanopic/photopic ratio (%.4f); re-run the sim to record mel-EDI directly._"
              % _D65_MEL_PHOT_RATIO_9]

    # P3 provenance
    if sim.get("verdict_source"):
        L += ["", "_Circadian verdict source: **%s**._" % sim["verdict_source"]]

    # P2 circadian-glare cross-check
    mel = mel_achieved
    ugr = sim.get("ugr")
    ugr_max = g.get("ugr_max")
    if mel is not None and ugr is not None and ugr_max is not None:
        mel_ok = g.get("mel_edi_target") is not None and mel >= g["mel_edi_target"]
        if mel_ok and ugr > ugr_max:
            L += ["", "> ⚠️ **Conflict:** mel-EDI met but UGR exceeds the EN 12464-1 limit "
                  "(%s > %s). Reduce vertical glare or redistribute fixtures." % (ugr, ugr_max)]

    L += ["", "## Renderings"]
    if brief.get("sim_results") is None:
        L += ["_not evaluated_"]
    elif sim.get("images"):
        L += ["- `%s`" % p for p in sim["images"]]
    else:
        L += ["_emit-only — no renderings produced (run with Radiance to generate the grid/fisheye "
              "images)._"]

    L += ["", "## Compliance"]
    if isinstance(comp, dict) and comp:
        # DEF-5: a {standard: verdict} mapping must render the verdict, not silently drop it.
        for standard, verdict in comp.items():
            L.append("- %s — **%s**" % (standard, verdict))
    elif comp:
        for c in comp:
            if isinstance(c, dict):
                L.append("- %s — **%s** (%s)" %
                         (c.get("standard"), c.get("verdict"), c.get("citation")))
            else:
                L.append("- %s" % (c,))
    else:
        L += ["_not evaluated_"]

    # Recommendations / what to change — surfaced from the fixture spec's own assumptions & caveats.
    assumptions = (fx.get("assumptions") or []) if fx else []
    caveats = (fx.get("caveats") or []) if fx else []
    if assumptions or caveats:
        L += ["", "## Notes & Caveats"]
        L += ["- %s" % a for a in assumptions]
        L += ["- ⚠️ %s" % c for c in caveats]

    return "\n".join(L) + "\n"


def build_report_to_dir(study_dir: str, study: str, brief: dict) -> dict:
    """Render the brief to study_dir/<study>/report.{md,html}. Pure templating — no Radiance needed."""
    study = _safe_study(study)
    # DEF-6: the slug param is canonical — render it even when the caller's brief omits "study"
    # (otherwise the header shows "?"). An explicit brief["study"] is overridden by the param.
    md = _render_markdown({**brief, "study": study})
    out_dir = os.path.join(study_dir, study)
    os.makedirs(out_dir, exist_ok=True)
    md_path = os.path.join(out_dir, "report.md")
    html_path = os.path.join(out_dir, "report.html")
    with open(md_path, "w") as fh:
        fh.write(md)
    body = md.replace("&", "&amp;").replace("<", "&lt;")
    with open(html_path, "w") as fh:
        fh.write("<!doctype html><meta charset='utf-8'><title>HCL Study %s</title>"
                 "<body><pre style='font:14px/1.5 ui-monospace,monospace;white-space:pre-wrap'>%s</pre>"
                 % (study, body))
    return {"md_path": md_path, "html_path": html_path}
