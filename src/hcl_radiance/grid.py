"""Point-in-time grid workflow: oconv -> rtrace -I per channel-set -> recombine to circadian metrics.

This reconstructs the standard Radiance point-in-time pattern. The legacy tool itself has no
rtrace/oconv in Python — it delegates this pipeline to Honeybee-generated .bat files and
just runs them. The recombination step (circadian_metrics) IS the faithfully ported Lark math.
"""
import csv
import os
import re

from hcl_platform import write_text

def _basename_hints_sky(path):
    """Does the BASENAME mention a sky at all? A plain case-insensitive substring, deliberately.

    The predecessor tried to be clever — r"(^|[^a-z])sky([^a-z]|$)" under IGNORECASE, which makes
    [^a-z] exclude letters of BOTH cases, so every name with a letter beside 'sky' slipped through:
    skydome.rad, clearsky.rad, skyvault.rad. Any boundary rule just relocates that edge. A
    substring has no edge to get wrong.

    It over-matches instead (whisky.rad), and that is the cheap direction: this is consulted only
    when the file cannot be read, so a false positive drops a file from one octree on the emit
    path, while a false negative puts daylight into an executed electric-only result.

    Directory names are ignored, so /home/sky_user/room.rad is still not a sky.
    """
    return "sky" in os.path.basename(path).lower()

# Markers that only a sky scene carries. Content beats naming: a file is what it contains, and
# the filename is chosen by whoever built the scene.
#
# Matched as WORDS anywhere in the head, not anchored to the start of a line, because the same
# marker appears in several syntactic positions and anchoring missed real output. `gensky` shows
# up inlined (`!gensky ...`), as a bare command, and as the comment header gensky itself writes
# (`# gensky 3 21 14 -c`). `skyfunc` appears both as a modifier (`skyfunc glow sky_mat`) and as
# the name gensky DEFINES (`void brightfunc skyfunc`) — the earlier line-anchored modifier
# pattern matched the first and missed the second, i.e. missed every plain gensky sky.
_SKY_CONTENT_RE = re.compile(
    r"\bgen(sky|daylit)\b"                 # the generator: inlined, run, or its comment header
    r"|\bskyfunc\b"                        # the sky-brightness pattern, defined or referenced
    r"|\bsource\s+(sky|ground)\b"          # the two hemispherical (180-degree) glows
    r"|\blight\s+solar\b"                  # gendaylit's sun
    r"|\b(skybright|perezlum)\.cal\b",     # the .cal files those patterns evaluate
    re.IGNORECASE)

# A sky definition is a handful of primitives; a geometry file can be enormous. Read only
# enough to decide, so this stays cheap enough to run on every scene file of every set.
_SKY_SNIFF_BYTES = 64_000


def _has_sky_primitives(path):
    """True when the file's CONTENT is a sky definition. False when it is unreadable.

    Unreadable is not a judgement of absence — it is the emit path, where scene files legitimately
    do not exist yet, and every unit test that passes bare names like "m.rad". The caller treats
    this as one of two independent signals precisely so an unreadable file falls back to the name.
    """
    try:
        with open(path, errors="ignore") as fh:
            head = fh.read(_SKY_SNIFF_BYTES)
    except OSError:
        return False
    return _SKY_CONTENT_RE.search(head) is not None


def _is_sky_file(path):
    """Is this scene file a sky? Content first, basename as a fallback hint.

    CONTENT is the reliable signal (`_has_sky_primitives`) and is checked whenever the file can be
    read. The BASENAME test is kept as well, because on the emit path there is no file to read:
    it matches sky.rad / sky_clear.rad / clear_sky.rad / Sky.rad / skydome.rad / clearsky.rad, and
    still rejects whiskey.rad. Directory names are ignored (/home/sky_user/room.rad is not a sky).

    The two are OR'd, never AND'd. A miss puts daylight into an electric-only result — the failure
    that motivated ADR-0007, where 1662 lx was reported as 17705 lx — whereas a false positive
    drops a file from one octree, which shows up immediately as a near-zero electric block rather
    than as a plausible wrong number.
    """
    return _has_sky_primitives(path) or _basename_hints_sky(path)


def _select_non_sky(files, sky_files):
    """Files for the electric-only octree (sky excluded).

    A non-empty explicit sky_files (exact path membership) is AUTHORITATIVE and used alone: the
    caller knows its own scene, and this is the escape hatch for both directions — naming a sky no
    detector would spot, and keeping a file whose name or content looks sky-ish (an exterior
    context block, say) inside the electric octree.

    An empty/falsy sky_files (None or []) falls back to `_is_sky_file`. That fallback is a
    DETECTOR, not a guarantee: it recognises the sky primitives this codebase and Radiance's own
    generators emit, plus a basename hint for files that cannot be read. A hand-rolled sky using
    none of those primitives, under a name with no 'sky' in it, will still reach the electric
    octree — pass sky_files explicitly when the scene is unusual. (The docstring this replaces
    claimed sky geometry "can never leak"; it could, and did.)
    """
    if sky_files:
        sky_indices = set()
        for named in sky_files:
            matches = [i for i, f in enumerate(files) if _same_scene_file(named, f)]
            if not matches:
                # A name that matches nothing would leave the real sky in the electric-only
                # octree and report daylight as electric light. Refuse instead.
                raise ValueError(
                    f"sky_files names {named!r}, which is none of the scene files "
                    f"({', '.join(files)}). Give it exactly as it appears in scene_sets.")
            sky_indices.update(matches)
        return [f for i, f in enumerate(files) if i not in sky_indices]
    return [f for f in files if not _is_sky_file(f)]


def _same_scene_file(named, scene_file):
    """Does a caller's `sky_files` entry mean this scene file?

    Yes when the two paths are the same once normalised (`/w/./sky.rad`), or when the entry is
    relative and the scene file ends with it on a path boundary (`sky.rad`, `skies/sky.rad`
    against `/w/skies/sky.rad`). Never on a partial file name.
    """
    a, b = os.path.normpath(named), os.path.normpath(scene_file)
    if a == b or os.path.abspath(a) == os.path.abspath(b):
        return True
    return not os.path.isabs(a) and b.endswith(os.sep + a)

from hcl_core.metrics import circadian_metrics
from hcl_core.data import W_PHOTOPIC_3, W_PHOTOPIC_9
from hcl_core.spd import parse_spd, bin_average
from hcl_core.ies import parse_ies, analyze_ies
from hcl_core.luminaire import color_luminaire
from hcl_radiance.discover import radiance_status
from hcl_radiance.commands import build_oconv, build_rtrace, pts_to_text, DEFAULT_RTRACE_PARAMS
from hcl_radiance.ies_radiance import build_ies2rad, place_luminaires
from hcl_radiance.runner import run_sequence, parse_rtrace_res

def _available():
    return radiance_status()["available"]

def _normalize_luminance(channels, channel_type):
    """Scale a luminaire's spectral channel vector so its photopic-weighted sum matches a flat
    (1,1,1...) white.

    ies2rad already bakes the IES luminous output into the light source for the default `3 1 1 1`
    color, so the per-channel multipliers must only REDISTRIBUTE that output across spectral bands —
    they must not rescale its magnitude. A RELATIVE SPD (peak~1) has tiny band means (~0.01), which
    without this normalization collapses the electric contribution ~100x (DEF-2). After scaling,
    dot(W_PHOTOPIC, channels) == dot(W_PHOTOPIC, [1]*n), i.e. the luminous output is preserved while
    the spectral shape (and thus mel/neuropic ratios) is faithful.
    """
    w = W_PHOTOPIC_3 if channel_type == 0 else W_PHOTOPIC_9
    denom = sum(wi * ci for wi, ci in zip(w, channels))
    if denom <= 0:
        return list(channels)
    factor = sum(w) / denom
    return [round(c * factor, 6) for c in channels]


def _sole_electric_spd(electric_lights):
    """The one SPD shared by every driven luminaire, or None if they differ / are unspecified.

    With a single spectrum the electric block's mel-DER can be computed exactly from it. With a
    mix of luminaire spectra there is no single source SPD, so the binned route (which labels
    itself approximate) is the honest answer.
    """
    if not electric_lights:
        return None
    # Compared pairwise rather than through a set: an inline SPD arrives as [[nm, value], ...] —
    # the only shape JSON can carry, and therefore what every MCP caller sends — and a list is
    # unhashable, so building a set raised TypeError and took the whole run down with it.
    spds = [lum.get("spd") or lum.get("preset") for lum in electric_lights]
    only = spds[0]
    if only is None or any(s != only for s in spds[1:]):
        return None
    if any(lum.get("spd") for lum in electric_lights):
        return only
    from hcl_core.presets import get_preset
    return get_preset(only)


def _luminaire_lumens(lum):
    """Luminaire output flux (lm), scaled exactly as ies2rad scales the emission, or None.

    `total_flux` is the integrated zonal flux — the light the luminaire actually puts into the
    room — which is what a utilisation bound needs; `rated_lumens` is the bare lamp output before
    the optic, and is only the fallback for photometric types whose zonal flux this codebase does
    not integrate (type A/B). ies2rad applies `-m multiplier * maintenance_factor` (see
    build_ies2rad), so the same product scales the flux.
    """
    ies = lum.get("ies")
    if not ies:
        return None
    try:
        report = analyze_ies(parse_ies(ies))
    except Exception:
        return None
    flux = report.get("total_flux") if report.get("flux_supported") else report.get("rated_lumens")
    if not flux or flux <= 0:
        return None
    return flux * lum.get("multiplier", 1.0) * lum.get("maintenance_factor", 1.0)


def _point_rows(points, pts_path, work_dir):
    """The sensor rows as numbers, whether they came inline or as a .pts path."""
    if not isinstance(points, str):
        return [list(p) for p in points]
    p = pts_path if os.path.isabs(pts_path) else os.path.join(work_dir, pts_path)
    rows = []
    try:
        with open(p) as fh:
            for ln in fh:
                parts = ln.split()
                if len(parts) >= 3:
                    try:
                        rows.append([float(v) for v in parts])
                    except ValueError:
                        continue
    except OSError:
        return []
    return rows


def _lumen_bound(electric_lights, rows, metrics):
    """The perfect-utilisation ceiling for the electric block's MEAN illuminance.

    Sum(luminaire lumens) / area is the illuminance a plane would receive if every lumen landed on
    it and none were absorbed. Real utilisation factors run 0.3-0.7, so a mean ABOVE this ceiling
    means the electric block is counting light no luminaire in the scene emitted — a leaked sky, a
    double-counted fixture, a wrong multiplier. It is the cheapest check that bounds the whole
    class, and it needs nothing the run does not already hold.

    `area` is the sensor grid's horizontal bounding box, not the room. That is deliberate: the flux
    reaching a sub-region cannot exceed the total emitted, so the bound stays valid on a partial
    grid, and because the box is inset from the walls it UNDERSTATES the floor and so overstates
    the ceiling — erring toward silence rather than false alarms.

    Two caveats, stated because the number invites over-reading. It bounds the MEAN, never a single
    point: illuminance directly beneath a downlight legitimately exceeds it. And in an enclosure
    with very high reflectances, interreflection can carry a plane slightly past unity utilisation,
    so `exceeded` is evidence to check rather than proof of a defect. The leak it was written for
    ran 6.5x over.

    Returns None when the ceiling cannot be formed (no resolvable lumens, or a degenerate grid) —
    a bound nobody can compute must not be reported as one that passed.
    """
    lumens = [_luminaire_lumens(lum) for lum in electric_lights]
    if any(l is None for l in lumens):
        return None
    total = sum(l * _instance_count(lum["placement"])
                for l, lum in zip(lumens, electric_lights))
    xs = [r[0] for r in rows if len(r) >= 2]
    ys = [r[1] for r in rows if len(r) >= 2]
    if not xs:
        return None
    area = (max(xs) - min(xs)) * (max(ys) - min(ys))
    lux = [m.get("photopic_lux", 0.0) for m in metrics]
    if area <= 0 or total <= 0 or not lux:
        return None
    ceiling = total / area
    mean_lux = sum(lux) / len(lux)
    return {"lamp_lumens": round(total, 1), "area_m2": round(area, 3),
            "ceiling_lux": round(ceiling, 1), "mean_lux": round(mean_lux, 1),
            "exceeded": mean_lux > ceiling,
            "area_basis": "sensor-grid bounding box (understates floor area)"}


def engine_provenance(work_dir):
    """What the engine did to this run's luminaires: {source_cal: {a1_honored, ...}}.

    Recorded on the result rather than looked up when the result is read, because which
    engine produced a number is a property of the run. A stored artifact stays interpretable
    on a machine whose Radiance differs from the one that made it.

    `work_dir` must be the SAME directory the run executed in: the shim lives under it, so
    resolving it from anywhere else would describe a different source.cal than the one
    Radiance actually loaded.
    """
    from hcl_radiance.source_cal import inspect_source_cal, shim_raypath, system_source_cal

    # With the shim active the effective source.cal is the shim's, not the installation's.
    shim = shim_raypath(work_dir)
    path = os.path.join(shim, "source.cal") if shim else system_source_cal()
    cal = inspect_source_cal(path) if path else {
        "a1_honored": None, "path": None, "reason": "could not locate the Radiance source.cal"}
    cal["shim_active"] = bool(shim)
    return {"source_cal": cal}


def _luminaire_channels(lum, channel_type):
    """Resolve a luminaire's 3-/9-channel triplet vector from spd/preset, default to flat.

    SPD/preset vectors are luminance-normalized (see `_normalize_luminance`) so the ies2rad-baked
    photometric output is preserved and only the spectrum is imposed. Flat white is already
    luminance-1, so it passes through unchanged.
    """
    n = 3 if channel_type == 0 else 9
    spd = lum.get("spd")
    preset = lum.get("preset")
    if spd is not None:
        return _normalize_luminance(bin_average(parse_spd(spd), channel_type), channel_type)
    if preset is not None:
        from hcl_core.presets import get_preset
        return _normalize_luminance(
            bin_average(parse_spd(get_preset(preset)), channel_type), channel_type)
    return [1.0] * n


def _instance_count(placement):
    if "positions" in placement:
        return len(placement["positions"])
    g = placement["grid"]
    return g["rows"] * g["cols"]


def _luminaire_wattage(lum):
    """Per-fixture input watts for the energy tally. An explicit `wattage` on the spec wins; else it
    is read from the IES file's input-watts field (DEF-3: the drop-in electric_lights payload carries
    `ies` but no `wattage`, so total_wattage came out 0). Returns 0.0 when neither is resolvable."""
    if lum.get("wattage") is not None:
        return lum["wattage"]
    ies = lum.get("ies")
    if ies:
        try:
            return parse_ies(ies).input_watts or 0.0
        except Exception:
            return 0.0
    return 0.0

def _write_metrics_csv(path, blocks):
    """Dump per-point channels + metrics to CSV (port of 'Write To csv Or txt File').

    `blocks` is an ordered {condition: {"channels": [...], "metrics": [...]}} mapping. EVERY
    block present is written, because a run that drove `electric_lights` carries its real
    numbers in `electric`/`combined` while `daylight` is legitimately all zeros with no sky —
    dumping only `daylight` produced an all-zero file that silently contradicted the tool return.

    With one block the historical layout is preserved exactly (`point, ch*, metrics...`). With
    more than one, a leading `condition` column names the block each row came from.
    """
    items = [(name, b) for name, b in blocks.items()
             if b and b.get("metrics")]
    if not items:
        items = [("daylight", {"channels": [], "metrics": []})]
    multi = len(items) > 1
    first = items[0][1]
    # UNION of each block's metric keys, in first-seen order — not just the first block's. The
    # blocks legitimately differ: the binned route carries `mel_der_note`, the transported route
    # carries `source_mel_der` and `transport_ratio` (ADR-0006). Taking the first block's keys
    # alone silently dropped whichever fields only the later blocks had, so the exported table
    # lost exactly the provenance a reader needs to interpret the electric numbers.
    metric_keys = []
    for _, blk in items:
        for k in (blk["metrics"][0] if blk["metrics"] else {}):
            if k not in metric_keys:
                metric_keys.append(k)
    n_ch = len(first["channels"][0]) if first["channels"] else 0
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow((["condition"] if multi else [])
                   + ["point"] + [f"ch{i}" for i in range(n_ch)] + metric_keys)
        for name, blk in items:
            for i, (ch, m) in enumerate(zip(blk["channels"], blk["metrics"])):
                w.writerow(([name] if multi else [])
                           + [i] + list(ch) + [m.get(k) for k in metric_keys])

def run_grid(scene_sets, points, channel_type, *, rad_params=DEFAULT_RTRACE_PARAMS,
             work_dir, run=True, export_csv=None, electric_lights=None, sky_files=None):
    """scene_sets: 1 file-list (3ch) or 3 file-lists (9ch). points: [x,y,z,dx,dy,dz] rows or .pts path.

    Returns {ran, metrics?|commands, ...}. Per the §9.2 ordering, 9ch sets are [a(blue),b(green),c(red)].
    Absolute paths are returned for any written artifacts (spec §3.1/§7.2). export_csv (path, abs or
    relative to work_dir) dumps the per-point result table on the success path.

    sky_files: optional iterable of exact scene paths to treat as sky and drop from the
    electric-only octree. When provided it takes precedence over the _is_sky_file basename
    heuristic; when None (default) the heuristic decides, preserving prior behavior.
    """
    n_expected = 1 if channel_type == 0 else 3
    if len(scene_sets) != n_expected:
        raise ValueError(f"channel_type {channel_type} needs {n_expected} scene set(s), got {len(scene_sets)}")
    # Each scene set is a flat list of .rad file paths. Reject dict elements early with a clear
    # message: run_annual uses {materials, geometry, sky_color} dicts, run_grid uses path lists —
    # a dict here otherwise reaches oconv as the filename "materials" and fails opaquely.
    for s in scene_sets:
        if not isinstance(s, (list, tuple)):
            raise ValueError(
                "each scene_sets element must be a list of .rad file paths, got "
                f"{type(s).__name__}; run_grid takes flat path lists "
                "(run_annual is the one that takes {materials, geometry, sky_color} dicts)")
    os.makedirs(work_dir, exist_ok=True)
    abs_work = os.path.abspath(work_dir)

    def _abs(p):
        return p if os.path.isabs(p) else os.path.join(abs_work, p)

    if isinstance(points, str):
        # Make caller-provided paths absolute: proc.run_sequence opens the stdin path as
        # os.path.join(work_dir, pts_path), so a RELATIVE caller path would be reinterpreted
        # relative to work_dir (not cwd) and rtrace would fail to find it. abspath() resolves
        # against cwd and os.path.join leaves an absolute path unchanged.
        pts_path = points if os.path.isabs(points) else os.path.abspath(points)
        wrote_pts = False
    else:
        pts_path = "points.pts"
        write_text(os.path.join(work_dir, pts_path), pts_to_text(points))  # LF: fed to rtrace stdin
        wrote_pts = True

    steps = []
    daylight_res, electric_res, combined_res = [], [], []
    for i, files in enumerate(scene_sets):
        # daylight-only octree/res (geometry + materials + sky)
        d_oct, d_res = f"daylight{i}.oct", f"daylight{i}.res"
        steps.append({"cmd": build_oconv(files, d_oct), "stdout": d_oct})
        steps.append({"cmd": build_rtrace(d_oct, rad_params), "stdin": pts_path, "stdout": d_res})
        daylight_res.append(d_res)

        if electric_lights:
            placed_rads = []
            for li, lum in enumerate(electric_lights):
                name = f"lum{li}_set{i}"
                rad = f"{name}.rad"            # ies2rad -o writes <name>.rad (+ <name>.dat) into work_dir
                placed = f"{name}_placed.rad"
                # No stdout redirect: ies2rad -o writes the .rad to a file itself (without -o it would
                # write to <ies-stem>.rad, NOT stdout). The .dat distribution file lands in work_dir too.
                steps.append({"cmd": build_ies2rad(
                    lum["ies"], multiplier=lum.get("multiplier", 1.0),
                    maintenance_factor=lum.get("maintenance_factor", 1.0),
                    units=lum.get("units", 2), out_prefix=name)})
                ch = _luminaire_channels(lum, channel_type)
                sel = 0 if channel_type == 0 else i   # color_luminaire bin selector: 0 for 3ch, set-index for 9ch
                steps.append({"colorize": (rad, placed, ch, sel, lum["placement"], name)})
                placed_rads.append(placed)

            # electric-only: geometry+materials+luminaires, NO sky
            e_oct, e_res = f"electric{i}.oct", f"electric{i}.res"
            e_inputs = _select_non_sky(files, sky_files) + placed_rads
            steps.append({"cmd": build_oconv(e_inputs, e_oct), "stdout": e_oct})
            steps.append({"cmd": build_rtrace(e_oct, rad_params), "stdin": pts_path, "stdout": e_res})
            electric_res.append(e_res)

            # combined: geometry+materials+sky+luminaires
            c_oct, c_res = f"combined{i}.oct", f"combined{i}.res"
            c_inputs = list(files) + placed_rads
            steps.append({"cmd": build_oconv(c_inputs, c_oct), "stdout": c_oct})
            steps.append({"cmd": build_rtrace(c_oct, rad_params), "stdin": pts_path, "stdout": c_res})
            combined_res.append(c_res)

    total_wattage = None
    if electric_lights:
        # `count` (when provided on a luminaire) is the per-fixture WATTAGE multiplier and
        # defaults to the placement instance count; it does NOT affect coloring/placement geometry.
        total_wattage = sum(
            _luminaire_wattage(lum) * lum.get("count", _instance_count(lum["placement"]))
            for lum in electric_lights)

    result = _run_with_colorize(steps, work_dir=work_dir, available=run and _available())
    if not result["ran"]:
        # Emit path: the points file plus any colored/placed luminaire .rad are on disk.
        emit = {"ran": False, "commands": result["commands"], "reason": result.get("reason"),
                "work_dir": abs_work,
                "inputs_written": [_abs(pts_path)] if wrote_pts else []}
        if total_wattage is not None:
            emit["total_wattage"] = total_wattage
        return emit
    if result.get("returncode", 0) != 0:
        return {"ran": True, "error": result.get("error"), "failed_step": result.get("failed_step")}

    # parse each channel-set's RGB, concatenate per point, recombine
    def _recombine(res_files, spd=None):
        """spd: the source spectrum when the block has exactly one, making mel-DER exact.

        Only the electric-only block qualifies: a daylight block's spectrum is the sky record
        (not held here), and a combined block is a mixture of two spectra whose ratio varies per
        point, so neither has a single SPD to hand. Those fall back to the binned mel-DER, which
        labels itself as approximate.
        """
        per_set = []
        for rf in res_files:
            with open(os.path.join(work_dir, rf)) as fh:
                per_set.append(parse_rtrace_res(fh.read()))
        # Every channel set must carry the SAME number of sensor rows, because the loop below
        # pairs them positionally. parse_rtrace_res drops any line whose first three tokens are
        # not numeric - right for a stray `rtrace: warning ...` on stdout, but it means one set
        # can come back short. Unchecked, point p then took a LATER point's value from the short
        # set (a wrong melanopic number, reported with full confidence) until the ragged tail
        # finally raised a bare IndexError naming neither the file nor the mismatch.
        counts = [len(s) for s in per_set]
        if len(set(counts)) > 1:
            detail = ", ".join(f"{rf}={n}" for rf, n in zip(res_files, counts))
            raise ValueError(
                f"channel sets disagree on sensor count ({detail}). Radiance returned a different "
                f"number of rows per channel set, so the per-point channels cannot be paired. "
                f"A non-numeric line (typically an rtrace warning on stdout) is the usual cause - "
                f"inspect the .res files in {work_dir}.")
        n_points = len(per_set[0])
        channels = []
        for p in range(n_points):
            row = []
            for s in per_set:    # a,b,c -> b1b2b3, g1g2g3, r1r2r3 (9ch); or just r,g,b (3ch)
                row.extend(s[p])
            channels.append(row)
        return {"channels": channels,
                "metrics": circadian_metrics(channels, channel_type, spd=spd)}

    daylight = _recombine(daylight_res)
    n_points = len(daylight["channels"])
    written = ([_abs(pts_path)] if wrote_pts else []) + [_abs(rf) for rf in daylight_res]
    out = {"ran": True, "n_points": n_points, "daylight": daylight,
           "work_dir": abs_work}
    if electric_lights:
        out["electric"] = _recombine(electric_res, spd=_sole_electric_spd(electric_lights))
        out["combined"] = _recombine(combined_res)
        bound = _lumen_bound(electric_lights, _point_rows(points, pts_path, abs_work),
                             out["electric"]["metrics"])
        if bound is not None:
            out["electric"]["lumen_bound"] = bound
        out["total_wattage"] = total_wattage
        # Only stamped when luminaires were actually rendered: A1 is an ies2rad concept, so a
        # daylight-only run is unaffected and must not carry an electric-engine caveat.
        out["engine"] = engine_provenance(abs_work)
        written += [_abs(rf) for rf in electric_res] + [_abs(rf) for rf in combined_res]
    out["files_written"] = written
    if export_csv:
        csv_path = _abs(export_csv)
        _write_metrics_csv(csv_path, {k: out[k] for k in ("daylight", "electric", "combined")
                                      if k in out})
        out["csv_path"] = csv_path
    return out


def _do_colorize(colorize, work_dir):
    """Write a colored+placed luminaire .rad for one 'colorize' pseudo-step.

    Reads the ies2rad-produced <name>.rad (which contains the literal `3 1 1 1` light line and a
    `brightdata ... '<name>.dat'` distribution); color_luminaire swaps in the spectral triplet, and
    place_luminaires wraps the colored copy in '!xform ...' so oconv/rpict can include it. The colored
    copy keeps the relative '<name>.dat' reference, which resolves in work_dir. When the ies2rad .rad
    is absent (emit path: ies2rad has not run), fall back to a flat-white stub so the command list
    stays honest and the placed .rad input exists.
    """
    rad, placed, ch, sel, placement, name = colorize
    rad_fp = os.path.join(work_dir, rad)
    if os.path.isfile(rad_fp):
        with open(rad_fp) as fh:
            text = fh.read()
    else:
        text = f"void light {name}_mat\n0\n0\n3 1 1 1\n"
    ch9 = ch * 3 if len(ch) == 3 else ch
    colored = color_luminaire(text, ch9, sel, in_place=False)
    with open(os.path.join(work_dir, f"{name}_colored.rad"), "w") as fh:
        fh.write(colored)
    block = place_luminaires(f"{name}_colored.rad", placement)
    with open(os.path.join(work_dir, placed), "w") as fh:
        fh.write(f"# inline luminaire\n{block}")


def _run_with_colorize(steps, work_dir, available):
    """Run a step list containing 'colorize' pseudo-steps, preserving ORDER.

    Order matters: a luminaire's colorize reads the .rad that its preceding ies2rad command writes,
    and the oconv that follows reads the colorize's placed .rad. So on the run path we execute the
    buffered commands up to each colorize boundary (forcing ies2rad to run and produce its .rad),
    THEN colorize, THEN continue — and flush the remainder at the end. The return dict matches the
    run_sequence contract (ran/returncode/commands/outputs/error/failed_step).

    On the emit path (available=False) no commands run; colorize uses the stub fallback so the .rad
    inputs exist and the emitted command list is honest, exactly as run_sequence would report it.
    """
    if not available:
        cmd_steps = []
        for s in steps:
            if "colorize" in s:
                _do_colorize(s["colorize"], work_dir)
            else:
                cmd_steps.append(s)
        return run_sequence(cmd_steps, work_dir=work_dir, available=False)

    commands, outputs, buffer = [], [], []

    def _flush():
        if not buffer:
            return None
        res = run_sequence(buffer, work_dir=work_dir, available=True)
        buffer.clear()
        commands.extend(res.get("commands", []))
        outputs.extend(res.get("outputs", []))
        return res

    for s in steps:
        if "colorize" in s:
            res = _flush()
            if res is not None and (not res.get("ran") or res.get("returncode", 0) != 0):
                return {"ran": True, "returncode": res.get("returncode", 1), "commands": commands,
                        "outputs": outputs, "error": res.get("error"),
                        "failed_step": res.get("failed_step")}
            _do_colorize(s["colorize"], work_dir)
        else:
            buffer.append(s)
    res = _flush()
    if res is not None and (not res.get("ran") or res.get("returncode", 0) != 0):
        return {"ran": True, "returncode": res.get("returncode", 1), "commands": commands,
                "outputs": outputs, "error": res.get("error"), "failed_step": res.get("failed_step")}
    return {"ran": True, "returncode": 0, "commands": commands, "outputs": outputs}
