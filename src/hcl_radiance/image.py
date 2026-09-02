"""Point-in-time fisheye image workflow: rpict per channel -> pcomb maps (+ optional FOV) -> RGB-from-HDR."""
import os

from hcl_radiance.discover import radiance_status
from hcl_radiance.commands import build_oconv
from hcl_radiance.image_commands import (build_rpict, pcomb_photopic_map, pcomb_melanopic_map,
                                          pcomb_neuropic_map, fov_pcomb_steps, rgb_from_hdr_steps)
from hcl_radiance.masks import fov_mask_paths, masks_present, synthesize_fov_masks_steps, mask_resize_steps
from hcl_radiance.ies_radiance import build_ies2rad, build_evalglare, parse_evalglare
from hcl_radiance.grid import (engine_provenance, _run_with_colorize, _luminaire_channels, _instance_count,
                               _luminaire_wattage)

def _available():
    return radiance_status()["available"]

# Emitted whenever fov_weighting=True. The ipRGC-FOV directional weighting (Khademagha et al.
# 2018/2016) is a NON-STANDARDIZED, opt-in research companion: WELL/CIE S 026/iNSOM define the
# circadian (250 lx mel-EDI) target on the cosine-weighted corneal-vertical quantity, which is the
# DEFAULT path (fov_weighting=False). The FOV-weighted value must be read comparatively
# (gaze-vs-gaze, source-vs-source) and is NOT a threshold verdict -- see hcl-methodology.md §12bis.2.
FOV_OPT_IN_NOTE = ("ipRGC-FOV directional weighting is ON: this is an OPT-IN, non-standardized "
                   "research quantity (Khademagha et al. 2018/2016 regional weights) and is NOT a "
                   "threshold verdict -- read it comparatively, never against the 250 lx target, "
                   "which is defined on the cosine-vertical (standards-aligned) default "
                   "(fov_weighting=False). See methodology §12bis.2 (metric-ladder Rung 3).")

def run_image(scene_sets, channel_type, *, view="-vta -vh 180 -vv 180", x=800, y=800,
              rad_params="-ab 2 -ad 512 -aa 0.1 -ar 64", fov_weighting=False, mask_dir=None,
              electric_lights=None, glare=False, glare_params=None,
              work_dir, run=True):
    """Fisheye eye-level workflow. scene_sets: 1 set (3ch) or 3 sets (9ch, a/b/c). Renders the
    fisheye HDR(s), builds greyscale luminance maps, optionally applies ipRGC FOV weighting, and
    extracts cosine-weighted RGB eye irradiance (rgb.txt). Returns {ran, outputs|commands, maps,
    notes, weighting}.

    fov_weighting (default False) selects the reported quantity, echoed in result["weighting"]:
      * False -> "cosine_vertical": cosine-weighted corneal-vertical eye irradiance, the
        STANDARDS-ALIGNED quantity WELL/CIE S 026/iNSOM threshold against 250 lx mel-EDI. Use this
        for any compliance/target comparison.
      * True  -> "fov_ipRGC": additionally applies the Khademagha 2018/2016 directional weighting.
        This is a NON-STANDARDIZED, opt-in research companion (metric-ladder Rung 3): read it
        comparatively, NEVER against the 250 lx target. A FOV_OPT_IN_NOTE is added to notes.

    What rgb.txt contains depends on channel_type:
      * 3-channel (channel_type=0): raw cosine-weighted RGB eye irradiance of the rendered HDR ->
        feed to circadian_metrics(channel_type=0) for photopic/melanopic lux.
      * 9-channel (channel_type=1): the eye image is the MELANOPIC luminance map, so rgb.txt is
        ALREADY melanopic-weighted eye irradiance. Multiply by 179 for melanopic-equivalent lux and
        send that to compliance directly -- do NOT re-run circadian_metrics on it (double-counts).
    """
    n_expected = 1 if channel_type == 0 else 3
    if len(scene_sets) != n_expected:
        raise ValueError(f"channel_type {channel_type} needs {n_expected} scene set(s)")
    os.makedirs(work_dir, exist_ok=True)
    notes = []
    steps, hdrs = [], []
    for i, files in enumerate(scene_sets):
        oct_name, hdr = f"img{i}.oct", f"img{i}.hdr"
        steps.append({"cmd": build_oconv(files, oct_name), "stdout": oct_name})
        steps.append({"cmd": build_rpict(oct_name, view, x, y, rad_params), "stdout": hdr})
        hdrs.append(hdr)

    if channel_type == 1:
        steps.append({"cmd": pcomb_photopic_map(hdrs, "photopic.hdr"), "stdout": "photopic.hdr"})
        steps.append({"cmd": pcomb_melanopic_map(hdrs, "melanopic.hdr"), "stdout": "melanopic.hdr"})
        steps.append({"cmd": pcomb_neuropic_map(hdrs, "neuropic.hdr"), "stdout": "neuropic.hdr"})
        eye_src = "melanopic.hdr"
    else:
        eye_src = hdrs[0]  # 3-channel: the rendered RGB HDR is the photopic-bin image

    if fov_weighting:
        notes.append(FOV_OPT_IN_NOTE)
        md = mask_dir or os.path.join(work_dir, "masks")
        if not masks_present(md):
            os.makedirs(md, exist_ok=True)
            mk_steps, note = synthesize_fov_masks_steps(resolution=x, mask_dir=md)
            steps = mk_steps + steps
            notes.append(note)
        # Resample masks to the render resolution (pcomb requires matching dimensions; the shipped
        # Khademagha masks are 512px while renders default to 800px). Mirrors Lark's pfilt resize.
        resize_steps, masks = mask_resize_steps(fov_mask_paths(md), x, y)
        steps += resize_steps
        steps += fov_pcomb_steps(eye_src, masks=masks, out="weighted.hdr")
        eye_src = "weighted.hdr"

    steps += list(rgb_from_hdr_steps(eye_src, "rgb.txt"))  # "|" steps route to the shell-free Popen pipe

    total_w = 0.0
    if electric_lights:
        n_sets = 1 if channel_type == 0 else 3
        for li, lum in enumerate(electric_lights):
            ch = _luminaire_channels(lum, channel_type)
            total_w += _luminaire_wattage(lum) * lum.get("count", _instance_count(lum["placement"]))
            for si in range(n_sets):
                name = f"img_lum{li}_set{si}"
                rad = f"{name}.rad"          # ies2rad -o writes <name>.rad (+ <name>.dat) into work_dir
                placed = f"{name}_placed.rad"
                # No stdout redirect: ies2rad -o writes the .rad itself (see grid._run_with_colorize).
                steps.append({"cmd": build_ies2rad(
                    lum["ies"], multiplier=lum.get("multiplier", 1.0),
                    maintenance_factor=lum.get("maintenance_factor", 1.0),
                    units=lum.get("units", 2), out_prefix=name)})
                sel = 0 if channel_type == 0 else si
                steps.append({"colorize": (rad, placed, ch, sel, lum["placement"], name)})
        for i, files in enumerate(scene_sets):
            placed_all = [f"img_lum{li}_set{i}_placed.rad" for li in range(len(electric_lights))]
            c_oct, c_hdr = f"combined{i}.oct", f"combined{i}.hdr"
            steps.append({"cmd": build_oconv(list(files) + placed_all, c_oct), "stdout": c_oct})
            steps.append({"cmd": build_rpict(c_oct, view, x, y, rad_params), "stdout": c_hdr})

    if glare:
        combined_hdr = "combined0.hdr" if electric_lights else hdrs[0]
        steps.append({"cmd": build_evalglare(combined_hdr, params=glare_params), "stdout": "glare.txt"})
        if channel_type == 1:
            notes.append("glare for 9-channel uses combined0.hdr (the 'a'/blue-bin scene) as the "
                         "luminance source; UGR/DGP is approximate for 9-channel renders")

    weighting = "fov_ipRGC" if fov_weighting else "cosine_vertical"
    result = _run_with_colorize(steps, work_dir=work_dir, available=run and _available())
    if not result["ran"]:
        emit = {"ran": False, "commands": result["commands"], "reason": result.get("reason"),
                "notes": notes, "weighting": weighting}
        if electric_lights:
            emit["total_wattage"] = total_w
        return emit
    if result.get("returncode", 0) != 0:
        return {"ran": True, "error": result.get("error"), "failed_step": result.get("failed_step"), "notes": notes}
    abs_work = os.path.abspath(work_dir)
    analysis_maps = (["photopic.hdr", "melanopic.hdr", "neuropic.hdr"] if channel_type == 1 else [hdrs[0]])
    if fov_weighting:
        analysis_maps.append("weighted.hdr")
    out = {"ran": True, "outputs": result.get("outputs"),
           "rgb_values_file": os.path.join(abs_work, "rgb.txt"),
           "maps": [os.path.join(abs_work, m) for m in analysis_maps],
           "notes": notes, "weighting": weighting}
    if electric_lights:
        out["total_wattage"] = total_w
        # Same reason as the grid path: A1 governs how brightly IES luminaires rendered, and
        # this is the path where a build that drops it shows up as UGR 0 rather than as a
        # low number, because the sources fall below evalglare's detection threshold.
        out["engine"] = engine_provenance(abs_work)
    if glare:
        glare_path = os.path.join(work_dir, "glare.txt")
        if os.path.isfile(glare_path):
            with open(glare_path) as fh:
                out["glare"] = parse_evalglare(fh.read())
    return out
