"""HCL-MCP Resources: handlers + declarative registry + parameter completion.

Single source of truth for every MCP resource the server exposes. server.py calls
register_resources(mcp).
"""
import json
from dataclasses import dataclass
from typing import Callable

import mcp.types as mcp_types

from hcl_core import data
from hcl_core import presets as _presets
from hcl_core.compliance import describe_thresholds, THRESHOLD_STANDARDS


@dataclass(frozen=True)
class ResourceDef:
    uri: str
    handler: Callable[..., str]
    name: str          # machine id, kebab-case
    title: str         # human label
    description: str
    mime_type: str
    tags: frozenset[str]


# --- 1-nm action spectra (copied from server.py:289-290) ---
_ACTION = {"S": data.ACTION_S, "M": data.ACTION_M, "L": data.ACTION_L,
           "rhod": data.ACTION_RHOD, "mel": data.ACTION_MEL, "V": data.V_LAMBDA, "D65": data.D65_ELR}

# §9.3 source-port caveats — single source shared by the `reference` tool and
# the hcl://reference/caveats resource (so the prose cannot drift).
SECTION_9_3_CAVEATS = [
    "(a) alpha-opic reconstruction float-division fix: (179.0/683.0)*(1.0/107.0) (source int-divides to 0).",
    "(b) 9-channel ordering for alpha-opic; 3-channel bin order is reversed in source -> realigned.",
    "image vs grid neuropic b3: image path 0.00007 vs grid 0.000069431; port uses the grid value.",
]


def reference_coefficients() -> str:
    """Verified metric coefficient vectors (photopic/melanopic/neuropic, 3- and 9-channel)."""
    return json.dumps({
        "photopic_9": data.W_PHOTOPIC_9, "melanopic_9": data.W_MELANOPIC_9,
        "neuropic_9": data.W_NEUROPIC_9, "photopic_3": data.W_PHOTOPIC_3,
        "melanopic_3": data.W_MELANOPIC_3, "luminous_efficacy": data.LUMINOUS_EFFICACY,
    }, indent=2)

def reference_bins() -> str:
    """v3.0 wavelength bin definitions (3- and 9-channel)."""
    return json.dumps({"bins_9": data.BINS_9, "bins_3": data.BINS_3}, indent=2)

def reference_ies() -> str:
    """IESNA LM-63 field guide: the data-line layout, photometric/units types, and what the
    derived metrics mean."""
    return (
        "IESNA LM-63 (1995/2002) — photometric data file\n"
        "================================================\n"
        "Keyword block (before TILT=): [TEST], [MANUFAC], [LUMCAT], [LAMP], ... (free-form, optional).\n"
        "TILT= line: NONE | <filename> | INCLUDE. INCLUDE is followed by an embedded tilt block:\n"
        "  lamp_to_lumin_geometry, num_tilt_pairs, then that many angle/multiplier pairs.\n"
        "  (A parser must CONSUME this block so data-line-1 indexing does not shift.)\n\n"
        "Data line 1 (10 fields):\n"
        "  num_lamps, lumens_per_lamp, candela_multiplier, num_vert_angles, num_horiz_angles,\n"
        "  photometric_type (1=C, 2=B, 3=A), units_type (1=feet, 2=meters), width, length, height.\n"
        "Data line 2 (3 fields):\n"
        "  ballast_factor, ballast_lamp_photometric_factor (pfactor), input_watts.\n"
        "  (pfactor is the test-lamp/rated-lamp ratio — NOT a 'future use' field; capture it.)\n"
        "Then: vertical_angles[num_vert], horizontal_angles[num_horiz],\n"
        "  candela[num_horiz][num_vert] (row-major per horizontal plane), all whitespace-tolerant.\n\n"
        "Effective candela (internal photometry only) = raw * candela_multiplier * ballast_factor * pfactor.\n"
        "  Do NOT fold these into ies2rad -m; ies2rad applies them itself (-m is user scaling only).\n\n"
        "Derived photometrics (type C):\n"
        "  rated_lumens = num_lamps * lumens_per_lamp (lumens_per_lamp = -1 -> absolute photometry:\n"
        "    rated_lumens = integrated zonal flux, LOR undefined).\n"
        "  efficacy = rated_lumens / input_watts (lm/W).\n"
        "  beam angle = full vertical angle at 50% of peak; field angle = at 10% (peak's horiz plane).\n"
        "  zonal flux: dPhi = I_bar * 2*pi * (cos v1 - cos v2) per vertical zone; split down(0-90)/up(90-180).\n"
        "  LOR = total_flux / rated_lumens.\n"
        "  Type B/A: the 2*pi*(cos v1 - cos v2) zonal solid angle does not apply -> flux is unsupported.\n"
    )

def reference_geometry() -> str:
    """OBJ/CAD geometry-import field guide: the import_geometry contract — material_map shape, the
    obj2rad Material/Group qualifier rule, units/axis/north, per-channel assembly, run-or-emit, and the
    v2/v3 conveniences (library/sidecar/dry_run, dual-height sensors, ground-albedo bridge,
    context-shading, drop-in electric_lights, manifest sidecar+header)."""
    return (
        "OBJ/CAD GEOMETRY IMPORT (import_geometry) — Wavefront .obj -> per-channel Radiance scene\n"
        "=======================================================================================\n"
        "\n"
        "import_geometry(obj_path, *, material_map, units, up_axis, channel_type=1, work_dir, run=True,\n"
        "                north_angle_deg=None, dry_run=False, sidecar=None, derive_sensors=False, annotate=False)\n"
        "  Converts a Wavefront .obj (obj2rad) + a unit/up-axis transform (xform) into a per-channel\n"
        "  Radiance scene that drops into run_grid / run_annual. RUN-OR-EMIT: the material .rad and the\n"
        "  obj2rad -m mapfiles are ALWAYS written in pure Python; only obj2rad/xform EXECUTION is gated\n"
        "  on Radiance (needs obj2rad + xform; Radiance 6.1a). Absent -> returns the exact command plan.\n"
        "\n"
        "MATERIAL MAP (the OBJ carries NO spectral data — you assign it)\n"
        "  Keyed by discovered group name: usemtl tokens in order, else g group names (deduped).\n"
        "  value = a library-name STRING (resolved via the surface library, flagged 'illustrative'),\n"
        "          OR an inline dict {type:'plastic'|'glass'|'ground'|'context'|'luminaire'|'floor',\n"
        "                             refl|tvis: float, spd?: <2-col SPD>, ies?: <path>, roughness?, specularity?}\n"
        "  MATERIAL TYPES: plastic (opaque diffuse) | glass (transmitting) | ground (opaque + drives\n"
        "    ground_albedo for the sky ground-glow) | context (exterior shading: in oconv, excluded from\n"
        "    sensor footprint + room-sanity) | luminaire (marker + IES -> electric_lights) | floor\n"
        "    (opaque + anchors the derived sensor footprint).\n"
        "    - scalar refl (plastic/ground/context) / tvis (glass) -> flat per-channel triplet [v]*N\n"
        "    - spd -> bin_average(parse_spd(spd)) per channel (e.g. spectral ground albedo)\n"
        "    - glass -> write_material(material_type=0) (transmittance->transmissivity internally); opaque=1\n"
        "    - luminaire -> NOT a surface; an IES marker (see LUMINAIRES) — excluded from material binding\n"
        "  EVERY discovered group MUST be mapped — an unmapped group HARD-FAILS with UnmappedGroupsError\n"
        "  (a ValueError subclass; .payload is the SAME discovery report dry_run returns). No silent\n"
        "  generic material (honesty boundary). The adjacent .mtl is a HINT source only (never a value).\n"
        "\n"
        "UNITS / AXIS\n"
        "  units = mm|cm|m|ft -> xform -s <factor> to metres. up_axis = Y|Z -> xform -rx 90 for Y-up.\n"
        "  A bounding-box sanity check warns on implausible room sizes (the usual wrong-unit/axis symptom).\n"
        "\n"
        "PER-CHANNEL ASSEMBLY (spec D8)\n"
        "  One obj2rad -m <mapfile> run per channel-set; the mapfile assigns each group its suffixed\n"
        "  modifier (<group>_a/_b/_c) so emitted modifiers match write_material's. 3-channel = 1 run\n"
        "  (base names); 9-channel = 3 runs (_a/_b/_c) -> index-aligned geometry_set + material_sets.\n"
        "\n"
        "obj2rad QUALIFIER RULE (live-confirmed on Radiance 6.1a)\n"
        "  obj2rad's -m mapfile matches the Material qualifier ONLY to usemtl names; a g-group name is\n"
        "  matched by the Group qualifier. So the importer emits (Group \"x\") for group-only OBJs (no\n"
        "  usemtl) — otherwise obj2rad silently drops every face -> empty scene — and (Material \"x\")\n"
        "  when usemtl is present. A MIXED OBJ (usemtl + bare-g faces obj2rad would drop) HARD-FAILS.\n"
        "\n"
        "OUTPUT\n"
        "  {ran: bool, geometry_set:[...], material_sets:[[...]], channel_type, groups:[...],\n"
        "   warnings:[...], commands:[...], work_dir,\n"
        "   apertures:[{group, area_m2, azimuth_deg(true-north), tilt_deg}],  # always present\n"
        "   manifest:{source_sha256, units, up_axis, north_angle_deg, channel_type, bbox_m, ...},  # always\n"
        "   manifest_path,  # manifest.json sidecar; the same block is also embedded as a #-header in each .rad\n"
        "   # conditional (only when their feature is mapped/requested):\n"
        "   ground_albedo:[401], ground_albedo_kind:'spd'|'flat',  # any type:'ground' group (v3)\n"
        "   electric_lights:[{ies, placement, spd, ...}],           # any type:'luminaire' group (v3)\n"
        "   context_groups:[...],                                   # any type:'context' group (v3)\n"
        "   grid_points, observer_sets:[{eye_h, points, glare_views}], observer_points, glare_views}  # derive_sensors\n"
        "   (+ reason on the emit path; + error/failed_step on a run failure)\n"
        "  Compose: scene_sets = [[*mats, sky, geom] for mats, geom in zip(material_sets, geometry_set)];\n"
        "  feed result['ground_albedo'] to spectral_sky_from_epw(spectral_albedo=...) and\n"
        "  result['electric_lights'] to run_grid/run_image directly.\n"
        "\n"
        "v2/v3 CONVENIENCES (additive — v1 return contract unchanged; live-validated on Radiance 6.1a)\n"
        "  dry_run=True   -> discovery payload {groups, bbox_m, mesh_quality, suggestions(.mtl hints)};\n"
        "                    no binding, no Radiance. Same body the UnmappedGroupsError .payload carries.\n"
        "  sidecar=PATH   -> reusable *.matmap.json supplying defaults (explicit kwargs always win).\n"
        "  north_angle_deg-> true CW azimuth (0=N,90=E) post-remap +Y faces; final xform -rz(-north) on\n"
        "                    EVERY channel run, so the room is oriented to the spectral sky. Wrong-is-silent.\n"
        "  derive_sensors=True -> grid_points (work-plane, floor+workplane_h, up-facing) and observer_sets\n"
        "                    (eye-level, toward glazing) at BOTH seated 1.2m + standing 1.6m, each with\n"
        "                    points + glare_views (DGP); flat observer_points/glare_views kept for back-compat.\n"
        "                    eye_heights/workplane_h/spacing tune the layout. All in the scene frame.\n"
        "  DEDICATED SENSOR TOOLS (methodology-grade alternatives to derive_sensors):\n"
        "    workplane_grid(obj_path, sidecar/material_map, workplane_h=0.8, ...) -> EN 12464-1 working-plane\n"
        "      illuminance grid; writes grid.pts (up-facing [x y z 0 0 1] rows). Feed to run_grid for\n"
        "      horizontal task illuminance + EN 12464-1 compliance.\n"
        "    observer_points(obj_path, sidecar/material_map, eye_height=1.2, ...) -> workstation eye sensors\n"
        "      (seat->screen gaze; window/azimuth/sweep fallbacks); writes a single observers.pts (one row\n"
        "      per eye, vertical at the eye) + glare_views fisheye strings (-vta -vh 180 -vv 180). Feed .pts to\n"
        "      run_grid/run_annual for vertical mel-EDI; feed glare_views to glare_ugr for DGP.\n"
        "    photosensors(obj_path, sidecar/material_map, zone_rule='head_height', mount='workplane')\n"
        "      -> daylight-dimming reference sensors, one per sidelighting zone (window-head-height\n"
        "      rule); writes photosensors.pts (up-facing work-plane refs, or down-facing if\n"
        "      mount='ceiling'). Feed to lighting_controls / daylight_savings.\n"
        "    preview_scene(obj_path, sidecar/material_map, render='all', grid_pts=..., observer_pts=...,\n"
        "      photosensor_pts=...) -> matplotlib PNG overlays (plan + 3D) of the room outline\n"
        "      + point layers + luminaire footprints; diagnostic placement check, NOT a photometric\n"
        "      render. Non-rectangular rooms render their true floor polygon.\n"
        "    NOTE: workplane_grid/observer_points clip to the floor footprint by default\n"
        "      (clip_to_footprint=True), dropping grid cells outside a non-rectangular floor; the EN\n"
        "      border is enforced along the interior bounding box, not concave walls (raise\n"
        "      footprint_border to inset all edges).\n"
        "  ground (v3)    -> type:'ground' yields result['ground_albedo'] (1nm, 401): feed it to\n"
        "                    spectral_sky_from_epw(spectral_albedo=...) so the ground colours the sky glow.\n"
        "  context (v3)   -> type:'context' = EXTERIOR SHADING: stays in oconv (casts shadows) but is excluded\n"
        "                    from the auto-sensor footprint + room-sanity check (result['context_groups']).\n"
        "  luminaires (v3)-> type:'luminaire' groups: OBJ 'p' markers -> result['electric_lights'], a DROP-IN\n"
        "                    payload run_grid/run_image consume directly (they run ies2rad+colorize). The v2\n"
        "                    informational result['luminaires'] dict is kept. No photometry is inferred (the\n"
        "                    IES + its scaling are user-supplied).\n"
        "  annotate=True  -> material 'summary' table + colored-by-material oconv->rpict->falsecolor render\n"
        "                    (live-validated on Radiance 6.1a).\n"
        "\n"
        "HONEST LIMITS\n"
        "  The OBJ/.mtl carry NO spectral data; the SHIPPED surface library is ILLUSTRATIVE scalar\n"
        "  reflectances (flagged + warned). The measured-SPD path EXISTS (an entry is 'measured' only with a\n"
        "  citation + a readable spd file) but the shipped catalog stays illustrative pending data. The\n"
        "  provenance manifest is now written as a manifest.json sidecar AND embedded as a #-comment header in\n"
        "  each geometry .rad. Deferred: frame/glazing split, auto ground-plane GEOMETRY synthesis,\n"
        "  BSDF/shading-device conventions, glTF/IFC.\n"
    )

def preset_resource(name: str) -> str:
    """Resource template: an illuminant SPD as JSON."""
    return json.dumps({"name": name, "spd": _presets.get_preset(name)})

def action_spectrum_resource(type: str) -> str:
    """Resource template: a 1-nm action spectrum array (S|M|L|rhod|mel|V|D65), 380-780 nm."""
    if type not in _ACTION:
        raise ValueError(f"unknown action spectrum {type!r}; choose from {sorted(_ACTION)}")
    return json.dumps({"type": type, "start_nm": 380, "step_nm": 1, "values": _ACTION[type]})

def lighting_controls_reference() -> str:
    """Resource: the EnergyPlus §7.3.5 daylight-control equations as readable text."""
    return (
        "EnergyPlus §7.3.5 daylight-responsive lighting controls (verified vs elec_lights.xlsx)\n"
        "\n"
        "Per reference point i, one time step:\n"
        "  fL(i) = max(0, (Iset - Itot(i)) / Iset)\n"
        "    Itot(i) = total daylight (sum of window contributions) at point i.\n"
        "    DEFAULT (EnergyPlus): Itot=0 -> fL=1 (full electric at darkness). 'No sensor reading'\n"
        "    is a DISTINCT state (None / occupancy-off), NOT Itot==0. workbook_compat=True adds the\n"
        "    elec_lights.xlsx gate Itot==0 -> fL=0.\n"
        "\n"
        "Power-input fraction fP (control_type), with fP_min, fL_min, N_steps:\n"
        "  Continuous:    fP_min                                    if fL < fL_min\n"
        "                 (fL + (1-fL)*fP_min - fL_min)/(1-fL_min)  if fL_min <= fL <= 1\n"
        "                 (== fP_min + (fL-fL_min)*(1-fP_min)/(1-fL_min), algebraically identical)\n"
        "  ContinuousOff: as Continuous, but fP=0 (lamp OFF) when fL < fL_min   [DEFAULT]\n"
        "  Stepped:       0 if fL==0 ; 1 if fL==1 ; else (floor(N_steps*fL)+1)/N_steps  [floor, NOT ceil]\n"
        "\n"
        "Zone aggregation (Lighting Power Reduction):\n"
        "  FP = Σ_i fP(i)*W(i) + (1 - Σ_i W(i))   (remainder = uncontrolled lights at full power; Σ W <= 1)\n"
        "\n"
        "Power / energy / savings:\n"
        "  P_elec = P_rated*schedule*FP ; P_saved = P_rated*schedule*(1 - FP) ; reduction = 1 - FP\n"
        "  annual_kwh_per_m2 = Σ consumed_Wh / 1000 / area (occupied hours only)\n"
        "\n"
        "Defaults: control_type=ContinuousOff, Iset=500 lx, fP_min=0.15, fL_min=0.05, N_steps=3,\n"
        "          schedule=weekdays 08:00-18:00.\n"
    )

def reference_daysim() -> str:
    """Daysim adapter reference: build-from-source steps, ds_shortterm/epw2wea I/O, and credits."""
    return (
        "DAYSIM ADAPTER (hcl_daysim) — sub-hourly weather generation\n"
        "===========================================================\n"
        "\n"
        "Daysim is NOT bundled or redistributed. It is built from source locally under the\n"
        "NRC / Fraunhofer ISE source-available EULA (redistribution carries credit + 'send a copy'\n"
        "obligations). Use the build_daysim tool, or build manually:\n"
        "\n"
        "  git clone --depth 1 --branch master \\\n"
        "      https://github.com/MITSustainableDesignLab/Daysim.git <src>\n"
        "  cmake -S <src> -B <src>/build -DBUILD_HEADLESS=ON -DCMAKE_BUILD_TYPE=Release \\\n"
        "      -DCMAKE_OSX_ARCHITECTURES=arm64 -DCMAKE_POLICY_VERSION_MINIMUM=3.5\n"
        "  cmake --build <src>/build --target ds_shortterm epw2wea\n"
        "\n"
        "Binaries land in <src>/build/bin — set HCL_DAYSIM_BIN to that directory (else PATH is used).\n"
        "Branch is 'master' (the README's 'combined' branch is gone). The headless arm64 flags and\n"
        "CMAKE_POLICY_VERSION_MINIMUM=3.5 avoid the two known macOS build frictions. If the build\n"
        "errors on ds_shortterm.c's `time_step` extern, apply the one-line fix and rerun the build.\n"
        "\n"
        "TOOLS\n"
        "-----\n"
        "  epw2wea <file.epw> <file.wea>\n"
        "      Hourly .wea: a 6-line header + rows `month day hour dir_norm_rad dif_hor_rad`,\n"
        "      units 1 (direct-normal + diffuse-horizontal irradiance).\n"
        "  ds_shortterm <header.hea>\n"
        "      Reads a Daysim .hea (input_weather hourly .wea, output path, time_step minutes,\n"
        "      units, latitude/longitude/time_zone/site_elevation/solar_time) and writes a\n"
        "      sub-hourly broadband .wea (1-min native via the Walkenhorst/Skartveit-Olseth\n"
        "      stochastic model, averaged to the target timestep; default 6 min = 0.1 h to satisfy\n"
        "      the nvRD δ ≤ 0.3 h guard).\n"
        "\n"
        "WORKFLOW\n"
        "--------\n"
        "  generate_subhourly_wea(epw, timestep_min=6, latitude, longitude, time_zone,\n"
        "                         site_elevation, solar_time, work_dir, run)\n"
        "  = epw2wea -> write .hea -> ds_shortterm -> <stem>_<timestep>_short.wea.\n"
        "  A faithful port of Lark 2.0 'Generate Sub-Hourly wea File'. Hybrid run/emit: if Daysim is\n"
        "  absent it writes the .hea + emits the command plan (run=False, or no binaries).\n"
        "\n"
        "CREDITS / LICENSING\n"
        "-------------------\n"
        "  Daysim: National Research Council Canada (NRC) and Fraunhofer Institute for Solar Energy\n"
        "  Systems (ISE). ds_shortterm implements the Walkenhorst et al. (2002) sub-hourly model.\n"
        "  Built on Radiance (BSD, LBNL / Greg Ward). The sub-hourly workflow is ported from Lark\n"
        "  Spectral Lighting 2.0 (EPFL / Oregon State / TU Eindhoven; Modified 3-Clause BSD).\n"
        "  We build from source locally and never redistribute Daysim binaries.\n"
    )

def nvrd_bridge_reference() -> str:
    """Reference: the annual->nvRD bridge data flow + the honesty caveats (spec §5.1, §5.3)."""
    return (
        "ANNUAL -> nvRD BRIDGE (dual reconstruction)\n"
        "Data flow: EPW -> generate_subhourly_wea (Daysim ds_shortterm, 6-min) -> run_annual "
        "(colored 2-phase DDS; sky & sun kept SEPARATE) -> per timestep reconstruct a 401-value "
        "380-780 nm @1 nm per-nm spectrum TWO ways -> assemble nvRD rows "
        "[x,y,z, vx,vy,vz, m,d,h, aopic, ELR, EDI, <401>] -> nvrd() -> R_D / RD_cum.\n"
        "  faithful : flat (179/683)*(1/107) step-expansion + NEUTRAL sun (reproduces the legacy 2.0 method).\n"
        "  enhanced : reference-SPD-shaped sky + air-mass colored direct sun; re-integrates to the "
        "channel bin totals (never contradicts the Radiance transport).\n"
        "\nCAVEATS (always read R_D in this light):\n"
        "1. R_D is RELATIVE, not absolute: the nvRD intensity-response was fit from nighttime "
        "electric-light studies; daytime adaptation is unvalidated (Amundadottir 2016; Pierson 2023).\n"
        "2. nvRD inherits the §9.3a reconstruction constant (179/683)*(1/107) — and here it SCALES "
        "I_eff, hence R_D, and does NOT cancel (unlike ELR). Both methods share this, so absolute R_D "
        "magnitude depends on the constant; compare R_D across scenarios, not as an absolute number.\n"
        "3. Neutral sun biases melanopic/R_D UPWARD at high direct-sun fractions (Inanici 2023: direct "
        "beam ~4736 K vs the ~5455 K white the legacy model assumes). The enhanced colored sun targets this; the "
        "divergence report quantifies it per run.\n"
        "4. Accuracy envelope: daylight mel-EDI within ~±20% of the reference; ~9% of 6-h daylight exposures yield "
        "a significant cumulative-R_D error, concentrated where mel-EDI is in the 150-1500 lx band "
        "(Pierson 2023). Validated for neutral-colored interiors; chromatic/strongly inter-reflecting "
        "scenes degrade.\n"
        "5. Flat reconstruction (faithful) is coarse across the steep 459-558 nm melanopic bins; the "
        "enhanced reference-shaping reduces this (Pierson 2021: flat ~+7% vs reference ~measured). The "
        "per-run flat_vs_reference divergence quantifies it for the actual scene.\n"
        "Single reference point+view per run. Credits: nvRD model Amundadottir 2016; Daysim NRC/ISE "
        "(build-from-source, not bundled); Radiance (BSD); ASTM G173 solar; CIE 15 D-series."
    )


def caveats_resource() -> str:
    """Resource: the §9.3 source-port caveats as markdown."""
    lines = ["# §9.3 source-port caveats", ""]
    lines += [f"- {c}" for c in SECTION_9_3_CAVEATS]
    return "\n".join(lines) + "\n"

def glossary_resource() -> str:
    """Resource: HCL metrics & units glossary as markdown."""
    return (
        "# HCL metrics & units glossary\n"
        "\n"
        "- **mel-EDI** (melanopic equivalent daylight illuminance, lx): illuminance weighted by the\n"
        "  melanopic action spectrum and normalised to D65, per CIE S 026. The circadian quantity.\n"
        "- **EML** (equivalent melanopic lux): the WELL-era melanopic metric. EML ≈ mel-EDI × 1.103.\n"
        "- **mel-DER** (melanopic daylight efficacy ratio): mel-EDI per photopic lux of a source,\n"
        "  relative to D65 (= 1.0). Scale-invariant; characterises an SPD's circadian 'colour'.\n"
        "- **CCT / Duv**: correlated colour temperature (K) and the signed distance from the Planckian\n"
        "  locus on the CIE 1960 uv diagram. Together they place a white point.\n"
        "- **alpha-opic** (α-opic): the five CIE S 026 photoreceptor-weighted quantities\n"
        "  (S-cone, M-cone, L-cone, rhodopic, melanopic). 'mel' (melanopic) drives circadian response.\n"
        "- **photopic / melanopic / neuropic**: the three channel weightings. Photopic = visual\n"
        "  luminous response (V(λ)); melanopic = ipRGC/circadian; neuropic = an alerting weighting.\n"
        "- **channel_type**: 0 = 3-channel (RGB-style bins), 1 = 9-channel (spectral bins).\n"
    )

def index_resource() -> str:
    """Resource: a one-read catalog of every resource + valid template argument values."""
    entries = []
    for r in RESOURCES:
        entry = {"uri": r.uri, "name": r.name, "title": r.title,
                 "description": r.description, "mime_type": r.mime_type,
                 "tags": sorted(r.tags)}
        args = {arg: source() for (uri, arg), source in COMPLETIONS.items() if uri == r.uri}
        if args:
            entry["arguments"] = args
        entries.append(entry)
    return json.dumps({"resources": entries}, indent=2)

def compliance_resource(standard: str) -> str:
    """Resource template: the stored threshold table for a standard (no scoring)."""
    return json.dumps(describe_thresholds(standard), indent=2)

def en_12464_1_resource() -> str:
    """Resource: the EN 12464-1:2021 task table (Ēm/UGRL/Uo/Ra) as JSON."""
    return json.dumps(describe_thresholds("en_12464_1"), indent=2)


RESOURCES = [
    ResourceDef("hcl://reference/coefficients", reference_coefficients,
                "reference-coefficients", "Metric coefficient vectors",
                "Verified photopic/melanopic/neuropic coefficient vectors (3- and 9-channel).",
                "application/json", frozenset({"reference"})),
    ResourceDef("hcl://reference/bins", reference_bins,
                "reference-bins", "Wavelength bins",
                "v3.0 wavelength bin definitions (3- and 9-channel).",
                "application/json", frozenset({"reference"})),
    ResourceDef("hcl://reference/ies", reference_ies,
                "reference-ies", "IESNA LM-63 field guide",
                "IESNA LM-63 data-line layout, photometric/units types, and derived metrics.",
                "text/plain", frozenset({"reference"})),
    ResourceDef("hcl://reference/lighting-controls", lighting_controls_reference,
                "reference-lighting-controls", "EnergyPlus daylight-control equations",
                "EnergyPlus §7.3.5 daylight-responsive lighting-control equations.",
                "text/plain", frozenset({"controls"})),
    ResourceDef("hcl://reference/daysim", reference_daysim,
                "reference-daysim", "Daysim adapter reference",
                "Daysim adapter build-from-source steps, ds_shortterm/epw2wea I/O, and credits.",
                "text/plain", frozenset({"daysim"})),
    ResourceDef("hcl://reference/nvrd-bridge", nvrd_bridge_reference,
                "reference-nvrd-bridge", "Annual→nvRD bridge reference",
                "The annual->nvRD bridge data flow and honesty caveats (spec §5.1, §5.3).",
                "text/plain", frozenset({"daysim"})),
    ResourceDef("hcl://reference/geometry", reference_geometry,
                "reference-geometry", "OBJ/CAD geometry-import field guide",
                "The import_geometry contract: material_map shape (+ surface library), the obj2rad "
                "Material/Group qualifier rule, units/axis/north, per-channel assembly, run-or-emit, and "
                "the v2/v3 conveniences (dual-height sensors, ground-albedo bridge, context-shading, "
                "drop-in electric_lights, manifest sidecar+header).",
                "text/plain", frozenset({"reference"})),
    ResourceDef("hcl://preset/{name}", preset_resource,
                "preset", "Illuminant preset SPD",
                "An illuminant SPD by name (e.g. D65, A, LED_4000K) as JSON.",
                "application/json", frozenset({"spectra"})),
    ResourceDef("hcl://action-spectrum/{type}", action_spectrum_resource,
                "action-spectrum", "CIE S 026 action spectrum",
                "A 1-nm action spectrum array (S|M|L|rhod|mel|V|D65), 380-780 nm.",
                "application/json", frozenset({"spectra"})),
    ResourceDef("hcl://compliance/en_12464_1", en_12464_1_resource,
                "compliance-en-12464-1", "EN 12464-1:2021 task table",
                "EN 12464-1:2021 maintained-illuminance/UGR/Uo/Ra task table + relationships.",
                "application/json", frozenset({"compliance"})),
    ResourceDef("hcl://compliance/{standard}", compliance_resource,
                "compliance-standard", "Compliance thresholds by standard",
                "Stored threshold table for a standard (well_v2_l03|brown_2022|"
                "iso_cie_8995_1_2025|en_17037|en_12464_1|ul_24480).",
                "application/json", frozenset({"compliance"})),
    ResourceDef("hcl://reference/caveats", caveats_resource,
                "reference-caveats", "§9.3 source-port caveats",
                "Correctness-critical port caveats: float-division fix, channel ordering, image-vs-grid b3.",
                "text/markdown", frozenset({"reference"})),
    ResourceDef("hcl://reference/glossary", glossary_resource,
                "reference-glossary", "HCL metrics & units glossary",
                "Definitions: mel-EDI, EML, mel-DER, CCT/Duv, alpha-opic, photopic/melanopic/neuropic.",
                "text/markdown", frozenset({"reference"})),
    ResourceDef("hcl://index", index_resource,
                "index", "Resource catalog",
                "One-read catalog of every resource + valid template argument values.",
                "application/json", frozenset({"index"})),
]


COMPLETIONS = {
    ("hcl://preset/{name}", "name"): lambda: list(_presets.list_presets()),
    ("hcl://action-spectrum/{type}", "type"): lambda: list(_ACTION.keys()),
    ("hcl://compliance/{standard}", "standard"): lambda: list(THRESHOLD_STANDARDS),
}


async def _complete(ref, argument, context=None):
    """Low-level MCP completion handler for resource-template arguments.

    ref is a ResourceTemplateReference (ref.uri == template URI) or a PromptReference.
    Returns prefix-filtered values for mapped (template, arg) pairs, else None (empty).
    """
    uri = getattr(ref, "uri", None)
    if uri is None:
        return None
    source = COMPLETIONS.get((uri, argument.name))
    if source is None:
        return None
    prefix = argument.value.lower()
    values = [v for v in source() if v.lower().startswith(prefix)]
    return mcp_types.Completion(values=values, total=len(values), hasMore=False)


def register_resources(mcp):
    """Register every resource (with full metadata) and the completion handler."""
    for r in RESOURCES:
        mcp.resource(r.uri, name=r.name, title=r.title, description=r.description,
                     mime_type=r.mime_type, tags=set(r.tags))(r.handler)
    mcp._mcp_server.completion()(_complete)
