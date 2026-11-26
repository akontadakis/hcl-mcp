"""Minimal FastMCP stdio server exposing the verified hcl_core toolkit."""
import functools
import inspect
import os
import signal
import threading
from datetime import timedelta

import anyio
import anyio.from_thread
import anyio.to_thread

from fastmcp import FastMCP, Context
from pydantic import TypeAdapter, ValidationError
from fastmcp.server.middleware import Middleware
from fastmcp.tools import InputRequiredToolResult
from fastmcp_tasks import TasksExtension

from hcl_core import data
from hcl_core import jobcontrol
from hcl_mcp.advisories import advise as _advise
from hcl_core.spd import parse_spd, bin_average
from hcl_core.materials import glass_transmissivity as _glass, write_material as _write_material
from hcl_core.metrics import circadian_metrics as _metrics
from hcl_core.alpha_opic import alpha_opic_from_channels, alpha_opic_from_spd
from hcl_core.validation import run_validation

from hcl_core.spectral_metrics import cct_duv, mel_der, mel_photopic_ratio, eml_medi_convert
from hcl_core.spectral_metrics import alpha_opic_from_spd as _spd_alpha_opic
from hcl_core.spectral_metrics import scale_warning_for as _scale_warning_for
from hcl_core.compliance import check_compliance
from hcl_core import presets as _presets
from hcl_core.lighting_controls import (controls_point as _controls_point,
                                        controls_series as _controls_series)
from hcl_radiance.sky import colored_sky as _colored_sky
from hcl_radiance.grid import run_grid as _run_grid
from hcl_platform import write_text
from hcl_radiance.commands import pts_to_text as _pts_to_text
from hcl_radiance.image import run_image as _run_image
from hcl_radiance.geometry_import import import_geometry as _import_geometry
from hcl_radiance.discover import radiance_status as _radiance_status
from hcl_daysim.discover import daysim_status as _daysim_status
from hcl_daysim.build import build_daysim as _build_daysim
from hcl_daysim.subhourly import generate_subhourly_wea as _generate_subhourly_wea
from hcl_core.spectral_reconstruct import (reconstruct_spectrum as _reconstruct_spectrum,
                                           reconstruction_divergence as _recon_divergence)
from hcl_core.spectral_pipeline import record_from_epw as _record_from_epw, annual_records as _annual_records
from hcl_core.cloud_modifier import Sedes1Modifier
from hcl_core import sedes1_fit
from hcl_core.spectral_engine import resolve_engine as _resolve_engine
from hcl_core.spectral_emit import (record_to_dict as _record_to_dict, emit_spd_set as _emit_spd_set,
                                    emit_band_matrix as _emit_band_matrix,
                                    emit_spectral_wea as _emit_spectral_wea,
                                    emit_augmented_epw_sidecar as _emit_sidecar)
from hcl_core.spectral_sky import ground_for_receiver as _ground_for_receiver
from hcl_core.atmosphere import AtmosphericState  # noqa: F401 (asdict via record_to_dict)
from dataclasses import asdict as _asdict
from hcl_radiance.annual_nvrd import annual_nvrd as _annual_nvrd
from hcl_core.luminaire import color_luminaire as _color_luminaire
from hcl_radiance.annual import run_annual as _run_annual
from hcl_core.nvrd import nvrd as _nvrd
from hcl_core.fixtures import recommend_fixtures as _recommend_fixtures
from hcl_core.weather import import_wea, analysis_period, decompose, subset_wea
from hcl_core.ies import parse_ies as _parse_ies, analyze_ies as _analyze_ies
from hcl_radiance.ies_radiance import build_ies2rad, place_luminaires
from hcl_radiance.runner import run_sequence
from hcl_radiance.spectral_native import run_gensdaymtx as _run_gensdaymtx
from hcl_radiance.sensor_sets import (create_sensor_set as _create_sensor_set,
                                       list_sensor_sets as _list_sensor_sets,
                                       get_sensor_set as _get_sensor_set,
                                       delete_sensor_set as _delete_sensor_set)
from hcl_radiance.annual_daylight import run_annual_daylight as _run_annual_daylight  # noqa: F401 (used by Task 12)
from hcl_radiance.daylight_factor import run_daylight_factor as _run_daylight_factor  # noqa: F401 (used by Task 13)
from hcl_radiance.lm83_run import run_lm83 as _run_lm83
from hcl_core.daylight_metrics import daylight_metrics as _daylight_metrics  # noqa: F401 (used by Tasks 12-13)
from hcl_core.lighting_controls import default_schedule as _default_schedule  # noqa: F401 (used by Task 12)
from mcp.types import InputRequiredResult
from hcl_mcp import __version__
from hcl_mcp.clientfeatures import resolve_work_dir, confirm_run, is_modern_protocol
from hcl_mcp.studio import (save_brief_to_dir as _save_brief, load_brief_from_dir as _load_brief,
                            build_report_to_dir as _build_report)
from hcl_mcp import resources as _resources
# MCP-6: the 13 prompt builders live in hcl_mcp.prompts; re-exported here so they
# stay importable from hcl_mcp.server (tests import hcl_studio / electric_lighting_design
# from this module) and register via the mcp.prompt(...) loop below. The spectral-sky prompt is
# aliased (`spectral_sky_from_epw_prompt`) to avoid clobbering the same-named TOOL defined below.
from hcl_mcp.prompts import (electric_lighting_design, spd_to_circadian, hcl_grid_study,
                             fisheye_eye_analysis, annual_circadian_dose, explain_concept,
                             annual_alertness, hcl_studio, import_obj_room, place_sensors,
                             annual_daylight_study, visualize_scene,
                             spectral_sky_from_epw as spectral_sky_from_epw_prompt)

INSTRUCTIONS = """\
Spectral and human-centric-lighting toolkit: sky and luminaire spectra, CIE S 026
alpha-opic metrics, Radiance-driven daylight simulation, circadian compliance.

QUANTITIES
- Report mel-EDI (`mel_edi`). Every circadian standard is written in it. `melanopic_lux`
  is a different, larger quantity (~1.0997x on the 9-bin route); substituting it silently
  relaxes any threshold.
- mel-DER is always reported AT THE POINT, never at the lamp. `mel_der_source` records how:
  "spd_transported" (a source SPD was supplied, so the source's within-bin detail is kept and
  the per-bin transport is recovered from the channels) or "binned_channels" (no SPD; inferred
  from channel averages alone, up to ~8% high on narrow-band sources).
- With "spd_transported" you also get `source_mel_der` — the luminaire's own — and
  `transport_ratio` between them. A luminaire datasheet quotes the SOURCE figure; the room is
  entitled to disagree with it, and `mel_der` is the one to report.
- An `electric` block carries `lumen_bound`: sum of luminaire lumens over the grid area, the
  ceiling its mean illuminance cannot physically pass. Check it before quoting the block.
- Provenance ranks override > measured/epw > documented default. Never report a
  substituted constant as a measured one.
- For LM-83 sDA/ASE use `lm83_daylight`, which operates blinds on 2.2.6's trigger.
  `annual_daylight` computes the same arithmetic on whatever shading the scene already has.
  Neither is a submission: `lm83_method_conformant` is always false (2.2.8-2.2.11 out of
  scope, so glazing runs at raw `tvis`, biasing sDA up). Read `conditions.departures`.

PATHS
- Every file-shaped argument resolves against the server's working directory, not your
  shell's. Pass absolute paths. A bad relative path can fail confusingly: arguments that
  accept a path OR inline data may parse it as content instead of reporting it missing.

ORDER OF WORK
- Geometry: import_geometry (or check_geometry first for a cheap health pass) ->
  read the `health` report -> place sensors (workplane_grid / observer_points /
  photosensors / sensors) -> build the sky -> run -> report.
- check_geometry needs no Radiance binaries and builds no scene, so re-run it freely
  while fixing a model.
- Radiance polygons are two-sided: a face normal pointing "the wrong way" is not a
  physics defect.

ADVISORIES
- Any dict-shaped result may carry an `advisories` list of {code, severity, message}.
  Read it before quoting a number. severity "error" means the result is probably not
  usable as-is; "warn" means it is usable but easy to misreport; "info" is a default
  worth confirming.
- Tools returning a LIST rather than a dict carry no advisories. The only one is
  circadian_metrics with multi-point input — inspect `mel_der_source` per point there.
"""

# Everything this server lists (tools, prompts, resources, reference texts) is fixed for the life
# of the process and none of it is specific to a user, so clients on MCP 2026-07-28 are told they
# may cache it: ttlMs = one hour, cacheScope = "public". Handshake-era clients never see the hint.
CACHE_TTL_SECONDS = 3600

mcp = FastMCP("hcl-mcp", instructions=INSTRUCTIONS, version=__version__,
              cache_ttl=CACHE_TTL_SECONDS, cache_scope="public")

# Background tasks (MCP tasks extension, SEP-2663) for the tools in _TASK_TOOLS below. A client
# that declared the extension gets a task handle back at once and polls it; every other client
# keeps getting the plain inline call. The backend is in-process (memory://), so nothing has to
# be installed or started and a task lives exactly as long as this server process does.
# Kept for a day: an annual run can take hours, and its result is fetched after it ends.
TASK_TTL = timedelta(hours=24)
_TASKS_EXTENSION = "io.modelcontextprotocol/tasks"   # the extension's identifier in the spec
mcp.add_extension(TasksExtension(execution_ttl=TASK_TTL))

# ============================================================================
# TOOL WRAPPERS (grouped by backend). Definitions stay in this module so the
# registration loops below + the MCP-11 aliases keep working.
# ----------------------------------------------------------------------------
# Core spectral / metrics (hcl_core)
# ============================================================================
def spd_to_channels(spd: str | list, channel_type: int = 1) -> dict:
    """Average a spectral power distribution into the 3- or 9-channel bins.

    spd: a `.spd` file path, 2-column text, or list of [wavelength, value]. channel_type: 0=3ch [r,g,b], 1=9ch [b1..r3].
    The str|list annotation is load-bearing: an untyped arg makes FastMCP stringify a list-of-pairs
    over the wire, which parse_spd then mis-reads as 2-column text (DEF-1/DEF-2 class).
    """
    return {"channels": bin_average(parse_spd(spd), channel_type), "channel_type": channel_type}

def glass_transmissivity(transmittance: float | list[float]) -> dict:
    """Convert glazing transmittance (0-1) to Radiance transmissivity. Accepts a number or list.

    Transmittance (Tvis, the datasheet number) and transmissivity (the value a Radiance glass
    primitive takes) are NOT the same: transmissivity is always the larger, e.g. 0.70 -> 0.763.

    USE THIS ONLY when hand-writing a Radiance glass primitive. Do NOT pre-convert for
    `write_material(material_type=0)` or for an `import_geometry` material_map
    {"type": "glass", "tvis": ...} -- both run this same conversion internally, so feeding
    them 0.763 yields 0.831 (~9% high) and silently inflates every downstream daylight and
    mel-EDI result. Those two take the raw datasheet Tvis.

    The float|list annotation is load-bearing: without it FastMCP emits an empty arg schema and
    delivers the value as a string, so the core's transmittance-squared term would raise (DEF-1)."""
    return {"transmissivity": _glass(transmittance)}


# One simulation at a time. Engines write fixed file names into the work directory (points.pts,
# daylight0.oct, img0.hdr, ...). While an engine held the event loop two calls could not overlap;
# now that it runs on a worker thread, this lock is what keeps parallel calls from silently
# overwriting each other's octrees and results. It is a thread lock on purpose: it is held by
# the thread doing the work, so it also covers the last moments of a cancelled run whose thread
# is still shutting its process down when the next call arrives.
_ENGINE_TURN = threading.Lock()


def _take_turn(fn, args, kwargs):
    with _ENGINE_TURN:
        jobcontrol.raise_if_cancelled()      # cancelled while waiting: never start
        return fn(*args, **kwargs)


async def _offload(fn, /, *args, **kwargs):
    """Run a blocking engine call on a worker thread and wait for it.

    Every simulation entry point goes through here. Called straight from a coroutine it would
    hold the event loop for as long as Radiance runs, and a held loop cannot read a
    cancellation, send progress, or answer another request.

    The thread inherits this coroutine's context, so the engine runs inside the tool call's
    `hcl_core.jobcontrol` job (opened in `_with_advisories`). If the call is cancelled the wait
    is abandoned at once -- a thread cannot be interrupted -- and leaving the job is what stops
    the thread: the process it is waiting on is killed and its next step raises. That takes a
    moment (a poll interval, plus a grace period for a process that ignores the request), so
    "stopped" means within seconds, not at the instant the call returns.

    Engines take turns (`_ENGINE_TURN`): a second simulation waits for the first, while every
    other request -- status, validation, task polling, cancellation -- is still answered.
    """
    return await anyio.to_thread.run_sync(functools.partial(_take_turn, fn, args, kwargs),
                                          abandon_on_cancel=True)


def _progress_reporter(ctx):
    """A job's `on_step` callback: forward an engine step to the client as MCP progress.

    Called on the worker thread; `report_progress` belongs to the event loop, hence the hop.
    It sends `notifications/progress` when the request carried a progress token, updates the
    task's status message inside a background task, and is silent otherwise. `total` is left
    out: a tool may run several command sequences, and only the running count is monotonic.
    """
    if ctx is None:
        return None

    def report(count, message):
        anyio.from_thread.run(ctx.report_progress, count, None, message)

    return report


def emit_envelope(ran: bool, *, commands=None, result=None, reason=None, **extra) -> dict:
    """Uniform run-or-emit envelope. ran=False -> {ran, commands?, reason?, **extra};
    ran=True -> {ran, **(result or {}), **extra}. None-valued standard keys dropped."""
    env = {"ran": ran}
    if not ran:
        if commands is not None:
            env["commands"] = commands
        if reason is not None:
            env["reason"] = reason
    elif result:
        env.update(result)
    env.update(extra)
    return env


async def write_material(channels: list, material_type: int, channel_type: int, name: str,
                         roughness: float = 0.0, specularity: float = 0.0,
                         work_dir: str | None = None, ctx: Context | None = None) -> dict:
    """Write Radiance material .rad file(s). material_type 0=glass,1=plastic. Written to work_dir (default: HCL_WORK_ROOT, else ~/hcl_work)."""
    wd = await resolve_work_dir(ctx, work_dir)
    return _write_material(channels, material_type=material_type, channel_type=channel_type,
                           name=name, roughness=roughness, specularity=specularity, work_dir=wd)

def circadian_metrics(channels: list, channel_type: int = 1,
                      spd: str | list | None = None) -> dict | list:
    """Photopic / melanopic / neuropic equivalent illuminance from channel irradiances.

    Returns one metrics dict for a single point, or a list of dicts for many points. Each carries
    BOTH `melanopic_lux` (a melanopic-weighted illuminance) and `mel_edi` (CIE S 026 melanopic
    equivalent daylight illuminance) — they are different quantities, and the circadian standards
    are written in mel-EDI, so pass `mel_edi` to `compliance`, never `melanopic_lux`.

    spd: the SOURCE spectrum feeding these channels, when known (`.spd` path, 2-column text, or
    [[nm, value], ...]). It is the spectrum at the LAMP, and `mel_der` is always reported at the
    POINT: supplying it keeps the source's within-bin structure, which the channel averages cannot
    represent, and combines it with the per-bin transport the channels reveal. Two extra fields come
    with it — `source_mel_der` (the source's own) and `transport_ratio` (the two divided), so a room
    that shifts the spectrum is visible rather than folded away. Without an SPD, mel-DER is inferred
    from the channel averages alone: exact for D65, within ~1.5% for smooth spectra, up to ~8% high
    for a narrow-band fluorescent. `mel_der_source` records which route ran.
    """
    return _metrics(channels, channel_type, spd=spd)

def alpha_opic(channels: list | None = None, spd: str | list | None = None, channel_type: int = 1, alpha: int | None = None) -> dict:
    """CIE S 026 alpha-opic E/ELR/EDI. Provide `spd` (exact-spectrum route) OR `channels` (binned route).

    spd accepts a `.spd` file path, 2-column text, or a list of [wavelength, value].
    alpha: 1=S,2=M,3=L,4=rhodopic,5=melanopic; omit for all five.

    For the `spd` path, a `scale_warning` key is attached (CORE-3): non-None when the SPD looks
    RELATIVE/normalized (peak <= 1.5) and the E/EDI values are shape indicators rather than
    lux-scale, else None. The channel path is unaffected.
    """
    if spd is not None:
        out = alpha_opic_from_spd(spd, alpha=alpha)
        out["scale_warning"] = _scale_warning_for(spd)
        return out
    if channels is not None:
        return alpha_opic_from_channels(channels, channel_type=channel_type, alpha=alpha)
    raise ValueError("provide either `spd` or `channels`")

def validate() -> dict:
    """Run the built-in correctness self-test (weight sums, alpha-opic guards)."""
    return run_validation()

def spectral_metrics(spd: str | list | None = None, metric: str = "all",
                     eml_edi_value: float | None = None,
                     eml_edi_direction: str = "medi_to_eml") -> dict:
    """Derived HCL quantities from an SPD: cct/duv, mel-DER, mel/photopic ratio, and EML<->EDI.

    spd accepts a `.spd` file path, 2-column text, or a list of [wavelength, value].
    The two modes below are mutually exclusive, so the `eml_edi` key has a DIFFERENT shape in each:
      * spd=<SPD>            -> {cct_duv, mel_der, mel_photopic_ratio, eml_edi:{mel_edi, eml}}.
                               Here `eml_edi` is the SPD's melanopic EDI + its EML equivalent.
                               NOTE: the `eml_edi` block is ABSOLUTE/scale-dependent (see its
                               `scale_note`); the other metrics are scale-invariant.
                               `metric` ('all' | one key) selects a single block.
      * eml_edi_value=<x>    -> scalar EML<->mel-EDI conversion only (no SPD needed):
                               {eml_edi:{input, direction, result}}.
        eml_edi_direction=    'medi_to_eml' (default) or 'eml_to_medi'. (Spec 7.1 row 5 EML<->EDI.)
    """
    if spd is None:
        if eml_edi_value is None:
            raise ValueError("provide spd= for metrics, or eml_edi_value= for a scalar EML<->EDI conversion")
        return {"eml_edi": {"input": eml_edi_value, "direction": eml_edi_direction,
                            "result": eml_medi_convert(eml_edi_value, eml_edi_direction)}}
    md = mel_der(spd)
    mel_edi = _spd_alpha_opic(spd)["mel_edi"]
    out = {"cct_duv": cct_duv(spd), "mel_der": md, "mel_photopic_ratio": mel_photopic_ratio(spd),
           "eml_edi": {"mel_edi": mel_edi, "eml": eml_medi_convert(mel_edi, "medi_to_eml"),
                       "units": "lx (absolute melanopic-EDI / EML)",
                       # CORE-3: conditional warning (non-None only for a RELATIVE-looking SPD),
                       # surfaced alongside the always-on scale_note below.
                       "scale_warning": _scale_warning_for(spd),
                       "scale_note": ("ABSOLUTE and scale-dependent: tracks SPD magnitude. For "
                                      "relative/normalized SPDs (e.g. presets, spec 5.7) this is NOT "
                                      "physical (rescale to a measured photopic illuminance first). "
                                      "cct_duv, mel_der and mel_photopic_ratio are scale-invariant "
                                      "and unaffected.")}}
    if metric != "all" and metric not in out:
        raise ValueError(f"metric must be 'all' or one of {sorted(out)}")
    return out if metric == "all" else {metric: out[metric]}

def compliance(mel_edi: float | None = None, eml: float | None = None, standard: str = "brown_2022",
               period: str = "daytime", daylight_met: bool = False,
               task: str | None = None, em: float | None = None, ugr: float | None = None,
               uo: float | None = None, ra: float | None = None,
               em_surround: float | None = None, uo_surround: float | None = None,
               em_background: float | None = None, uo_background: float | None = None,
               em_wall: float | None = None, uo_wall: float | None = None,
               em_ceiling: float | None = None, uo_ceiling: float | None = None,
               em_cylindrical: float | None = None, uo_cylindrical: float | None = None) -> dict:
    """Check a value against a lighting standard.

    standard: well_v2_l03 | brown_2022 | iso_cie_8995_1_2025 | en_17037 | en_12464_1 | ul_24480.

    CIRCADIAN standards are scored on `mel_edi` (CIE S 026 mel-EDI -- NOT `melanopic_lux`, which is
    larger by D65's melanopic/photopic ratio ~1.10 and would silently relax the threshold); `eml` is
    accepted and converted. EML is the LARGER number -- EML = mel-EDI * 1.103 -- so an `eml`
    input is DIVIDED by 1.103 to score it. Pass ONE of them: if both are given, `mel_edi` wins,
    `eml` is discarded without warning, and the result is stamped quantity "mel_edi" with no
    trace of the ignored input. To go the other way, from mel-EDI to EML, use
    `spectral_metrics(eml_edi_value=..., eml_edi_direction='medi_to_eml')`; do not do the
    arithmetic by hand. en_17037 returns "n/a" (daylight-provision, non-circadian) and
    ul_24480 returns "unsupported" (Circadian Stimulus, not computed here).

    standard="en_12464_1" is the ELECTRIC VISUAL-TASK path and ignores mel_edi entirely: pass
    `task` (see EN_12464_1_TASKS / the hcl://compliance/en_12464_1 resource) plus the measured
    em/ugr/uo/ra, and optionally the surround/background (em_surround, uo_surround, em_background,
    uo_background) and wall/ceiling/cylindrical (em_wall, uo_wall, em_ceiling, uo_ceiling,
    em_cylindrical, uo_cylindrical) values -- each relationship is evaluated only when supplied.
    Supplying the task but no measured values returns "incomplete", never a vacuous "pass".
    """
    return check_compliance(mel_edi=mel_edi, eml=eml, standard=standard, period=period,
                            daylight_met=daylight_met, task=task, em=em, ugr=ugr, uo=uo, ra=ra,
                            em_surround=em_surround, uo_surround=uo_surround,
                            em_background=em_background, uo_background=uo_background,
                            em_wall=em_wall, uo_wall=uo_wall,
                            em_ceiling=em_ceiling, uo_ceiling=uo_ceiling,
                            em_cylindrical=em_cylindrical, uo_cylindrical=uo_cylindrical)

def quality_presets(level: str | None = None) -> dict:
    """Ambient-quality presets: pick the accuracy/runtime trade-off up front, by name.

    Radiance's ambient parameters govern the indirect (interreflected) solve, which dominates both
    runtime and the accuracy of every climate-based metric. Passing no `rad_params` means
    inheriting a preview-grade default by not choosing — which on a validated annual run returned
    sDA 77.78% where a converged solve returned 100.00% on identical geometry.

    Levels, cheapest first:
      low        -ab 0  : geometry checks and direct-sun questions only. NO interreflection.
      medium     -ab 2  : draft studies and design comparison. Preview-grade convergence.
      high       -ab 3  : reportable results — DA/sDA/UDI, compliance. Use this to publish.
      extra_high -ab 5  : indirect-dominated scenes (light shelves, atria) and validation.

    Call with no argument for the full table including each level's caveat; call with a level to
    get just that one. Pass the level to a simulation tool as `quality=`, or its `rad_params`
    string directly if you want to tune from it.
    """
    from hcl_radiance.commands import QUALITY_PRESETS, quality_preset_table
    if level is None:
        return {"presets": quality_preset_table(),
                "note": ("Higher levels cost more: relative_cost is an order-of-magnitude guide, "
                         "not a measurement. Direct-only metrics such as ASE are unaffected by "
                         "these settings and are correct at any level.")}
    if level not in QUALITY_PRESETS:
        # RAISE, not an in-band {"error": ...}: every other validation failure in this module
        # raises, so FastMCP marks the call is_error=True. Returning the error in the payload left
        # is_error=False, and a client's error path never fired -- a typo'd level read as success.
        raise ValueError(f"unknown quality level {level!r}; "
                         f"choose from {list(QUALITY_PRESETS)}")
    return {"name": level, **QUALITY_PRESETS[level]}


def _resolve_rad_params(rad_params, quality, *, default=None):
    """rad_params wins over quality; quality wins over the caller-supplied default.

    Explicit parameters always take precedence so a tuned string is never silently overridden,
    but naming a level is enough for the common case.
    """
    if rad_params:
        return rad_params
    if quality:
        from hcl_radiance.commands import quality_params
        return quality_params(quality)
    return default


def presets(name: str | None = None) -> dict:
    """List available illuminant presets (CIE standards + illustrative LED models), or fetch one by name.

    Names: D65, D50, A, FL1..FL12, and the illustrative LED models LED_3000K/4000K/5000K/BLUEPUMP/VIOLETPUMP
    (flagged illustrative, not measured - see spec 5.7). Returns SPD + metadata when a name is given.
    """
    if name is None:
        return {"presets": _presets.list_presets()}
    return {"name": name, "spd": _presets.get_preset(name), "meta": _presets.preset_meta(name)}

# ---- Materials / sky / luminaire (hcl_core.materials, hcl_radiance.sky, hcl_core.luminaire) ----
async def colored_sky(diffuse_channels: list, direct_channels: list, channel_type: int = 1,
                      month: int = 6, day: int = 21, hour: float = 12.0, irrad_mode: str = "W",
                      mode: str = "spectra",
                      lat: float = 0.0, lon: float = 0.0, utc: int = 0,
                      direct: float | None = None, diffuse: float | None = None, globl: float | None = None,
                      sun_zenith_deg: float | None = None, sun_azimuth_deg: float | None = None,
                      name: str = "sky", work_dir: str | None = None, run: bool = True, ctx: Context | None = None) -> dict:
    """Generate a colored Perez sky+sun Radiance definition.

    mode 'spectra' (per-channel spectral scaling, runs gendaylit) or 'luminance' (Radiance -C built-in
    coloring, 3-channel only, pure emit). irrad_mode 'W' (direct+diffuse) or 'E' (global).
    diffuse_channels/direct_channels: 3 or 9 channel values (from spd_to_channels); ignored in luminance mode.
    lon is standard signed / EAST-positive (Seattle = -122.3, Athens = 23.73), matching raw EPW.

    SOLAR POSITION. By default the sun is derived by gendaylit's own ephemeris from month/day/hour +
    lat/lon/utc, and `hour` is read as a WALL-CLOCK instant. spectral_sky_from_epw's `hour` is a
    different thing — an EPW hour-ENDING label, whose geometry is evaluated at the mid-interval
    instant (hour - 0.5) because the row's DNI/DHI are averaged over the preceding hour. Passing the
    same integer to both therefore puts the spectrum and the traced sky half an hour (7.5 deg of
    diurnal arc) apart, with no error raised.

    To keep them on one instant, pass that record's geometry through here VERBATIM:
        sun_zenith_deg  = record["geometry"]["zenith_deg"]
        sun_azimuth_deg = record["geometry"]["azimuth_deg"]
    Both are required together; supplied, they emit gendaylit's `-ang` form and make the record's
    position authoritative for the traced geometry. Omitted, behaviour is unchanged.
    """
    wd = await resolve_work_dir(ctx, work_dir)
    return await _offload(_colored_sky, diffuse_channels, direct_channels, channel_type, month=month, day=day, hour=hour,
                        irrad_mode=irrad_mode, mode=mode, lat=lat, lon=lon, utc=utc,
                        direct=direct, diffuse=diffuse, globl=globl, name=name, work_dir=wd, run=run,
                        sun_zenith_deg=sun_zenith_deg, sun_azimuth_deg=sun_azimuth_deg)

async def colored_luminaire(rad_path: str, channels9: list, count: int, name: str | None = None,
                            work_dir: str | None = None, ctx: Context | None = None) -> dict:
    """Inject a channel triplet into a luminaire .rad, writing a NEW file (never edits the input).

    count: 0=blue,1=green,2=red third of 9 values. The colored definition is written to work_dir
    (default: HCL_WORK_ROOT, else ~/hcl_work) as <name>.rad — the source rad_path is left untouched — and its absolute
    path is returned. rad_path may be a .rad file path or raw .rad text. Returns {file, rad}.
    """
    rad_text = _color_luminaire(rad_path, channels9, count, in_place=False)
    wd = await resolve_work_dir(ctx, work_dir)
    os.makedirs(wd, exist_ok=True)
    if name is None:
        is_path = os.path.exists(rad_path)
        stem = os.path.splitext(os.path.basename(rad_path))[0] if is_path else "luminaire"
        name = f"{stem}_colored"
    out_path = os.path.join(wd, f"{name}.rad")
    with open(out_path, "w") as fh:
        fh.write(rad_text)
    return emit_envelope(True, result={"file": out_path, "rad": rad_text})

# ---- Radiance simulation (hcl_radiance: status / grid / image) ----
def radiance_status() -> dict:
    """Report Radiance availability: {available, bin_dir, version, found, missing}.

    Use this to check whether Radiance tools (run_grid, ...) will execute vs return commands.
    """
    return _radiance_status()

async def run_grid(scene_sets: list, points: str | list, channel_type: int = 1,
                   rad_params: str | None = None, quality: str | None = None, work_dir: str | None = None,
                   run: bool = True, export_csv: str | None = None,
                   electric_lights: list | None = None, sky_files: list | None = None,
                   ctx: Context | None = None) -> dict:
    """Point-in-time grid HCL metrics via Radiance (oconv -> rtrace -I per channel -> recombine).

    scene_sets: 1 list of .rad paths for 3-channel, or 3 lists (blue/green/red bin sets) for 9-channel.
    points: rows [x,y,z,dx,dy,dz] or a .pts path. Runs Radiance if present, else returns the commands.
    export_csv: optional path (abs or relative to work_dir) to dump the per-point result table.

    sky_files: which scene paths are sky, listed exactly as they appear in scene_sets. Only matters
    with electric_lights, which builds a sky-free octree for the `electric` block. Left unset, the
    sky is DETECTED (gensky/gendaylit primitives, skyfunc, the sky/ground hemispheres, plus a
    basename hint), which covers the generators this codebase and Radiance use but cannot cover a
    hand-rolled sky using none of them. Pass it explicitly for an unusual scene — in both
    directions: to name a sky nothing would detect, or to KEEP a sky-looking file (exterior context)
    inside the electric octree. A leak here reports daylight as electric light; the `electric` block
    carries a `lumen_bound` (sum of luminaire lumens / grid area) so an over-count is visible.
    """
    wd = await resolve_work_dir(ctx, work_dir)
    kwargs = {"work_dir": wd, "run": run}
    _rp = _resolve_rad_params(rad_params, quality)
    if _rp:
        kwargs["rad_params"] = _rp
    if export_csv:
        kwargs["export_csv"] = export_csv
    if electric_lights:
        kwargs["electric_lights"] = electric_lights
    if sky_files:
        kwargs["sky_files"] = sky_files
    return await _offload(_run_grid, scene_sets, points, channel_type, **kwargs)

async def run_image(scene_sets: list, channel_type: int = 1, view: str = "-vta -vh 180 -vv 180",
                    x: int = 800, y: int = 800, rad_params: str | None = None, quality: str | None = None,
                    fov_weighting: bool = False, mask_dir: str | None = None,
                    electric_lights: list | None = None, glare: bool = False,
                    glare_params: str | None = None,
                    work_dir: str | None = None, run: bool = True, ctx: Context | None = None) -> dict:
    """Fisheye HCL image workflow: rpict -> mel/neuropic greyscale luminance maps (falsecolor-ready)
    -> optional ipRGC FOV weighting -> RGB-from-HDR eye irradiance. Runs Radiance if present, else
    returns the commands."""
    wd = await resolve_work_dir(ctx, work_dir)
    kw = {"channel_type": channel_type, "view": view, "x": x, "y": y,
          "fov_weighting": fov_weighting, "mask_dir": mask_dir, "work_dir": wd, "run": run}
    if electric_lights:
        kw["electric_lights"] = electric_lights
    if glare:
        kw["glare"] = glare
    if glare_params:
        kw["glare_params"] = glare_params
    _rp = _resolve_rad_params(rad_params, quality)
    if _rp:
        kw["rad_params"] = _rp
    return await _offload(_run_image, scene_sets, **kw)


async def import_geometry(obj_path: str, material_map: dict | None = None,
                          units: str | None = None, up_axis: str | None = None,
                          channel_type: int = 1, north_angle_deg: float | None = None,
                          dry_run: bool = False, sidecar: str | None = None,
                          derive_sensors: bool = False, annotate: bool = False,
                          eye_heights: list | None = None, workplane_h: float = 0.8,
                          spacing: float = 0.6, strict: bool = False,
                          run: bool = True, work_dir: str | None = None,
                          ctx: Context | None = None) -> dict:
    """Import a Wavefront .obj room into a per-channel Radiance scene (obj2rad -> xform).

    material_map: {group_name: spec} keyed by OBJ usemtl (else g) names; unmapped groups hard-fail.
    spec is a library-name string (illustrative reflectance) or a dict
    {"type": "plastic"|"glass"|"ground"|"context"|"luminaire"|"floor", "refl"/"tvis": float, ...}:
      plastic=opaque diffuse; glass=transmitting; ground=opaque + drives ground_albedo;
      context=exterior shading (in oconv, excluded from sensor footprint/room-sanity);
      luminaire=marker + IES (-> electric_lights); floor=opaque + anchors the sensor footprint.
    units: mm|cm|m|ft. up_axis: Y|Z.

    v2/v3 parameters:
    - north_angle_deg: clockwise azimuth (degrees) that post-remap +Y points toward; applied as
      -rz(-north) after up-axis correction.
    - dry_run=True: return a discovery payload (groups, bbox_m, mesh_quality, suggestions) without
      binding materials or running Radiance. material_map not required in dry_run mode.
    - sidecar: path to a JSON file supplying defaults (explicit kwargs always win over sidecar).
    - derive_sensors: derive a work-plane grid + eye-level observer_sets (at BOTH seated 1.2 m and
      standing 1.6 m by default) + DGP-view strings from the geometry.
    - eye_heights / workplane_h / spacing: tune the derived-sensor layout (defaults (1.2, 1.6) / 0.8 / 0.6).
    - annotate: build a colored-by-material falsecolor render (oconv -> rpict -> falsecolor; live-validated).
    - strict: raise GeometryHealthError when the embedded health report (result["health"]) holds
      error-severity findings (e.g. coincident surfaces), instead of returning a report that looks
      plausible but is built on defective geometry. strict has NO effect when dry_run=True: the
      dry_run path returns before materials are bound, so no health report is computed to raise on.

    Returns geometry_set + material_sets (index-aligned per channel-set) to compose into
    run_grid / run_annual scene_sets, plus discovered groups and warnings, an always-present
    `apertures` report, and a provenance `manifest` (written as a manifest.json sidecar -> `manifest_path`,
    and embedded as a #-comment header in each geometry .rad). Conditional keys appear only when their
    feature is mapped/requested: `ground_albedo`/`ground_albedo_kind` (a 1-nm albedo from any type:"ground"
    group -> feed to spectral_sky_from_epw(spectral_albedo=...)); `electric_lights` (drop-in luminaire
    payload for run_grid/run_image, which run ies2rad + colorize); `context_groups` (type:"context"
    exterior-shading groups); and grid_points/observer_sets/observer_points/glare_views (derive_sensors).
    """
    wd = await resolve_work_dir(ctx, work_dir)
    extra = {} if eye_heights is None else {"eye_heights": tuple(eye_heights)}
    from hcl_radiance.geometry_import import _normalize_up_axis
    if up_axis is not None:
        up_axis = _normalize_up_axis(up_axis)
    return await _offload(
        _import_geometry, obj_path, material_map=material_map, units=units, up_axis=up_axis,
        channel_type=channel_type, work_dir=wd, run=run,
        north_angle_deg=north_angle_deg, dry_run=dry_run, sidecar=sidecar,
        derive_sensors=derive_sensors, annotate=annotate, strict=strict,
        workplane_h=workplane_h, spacing=spacing, **extra)


async def check_geometry(obj_path: str, material_map: dict | None = None,
                         sidecar: str | None = None, units: str | None = None,
                         up_axis: str | None = None,
                         sensors: dict | None = None,
                         photosensors: dict | None = None,
                         electric_lights: list | None = None,
                         ctx: Context | None = None) -> dict:
    """Health-check an OBJ scene without building it (spec 2026-07-23).

    Reports geometry defects that would otherwise complete silently and return a plausible
    number: coplanar surfaces (Radiance z-fighting), glazing with no opening cut in the
    wall, duplicated and non-planar faces, an unclosed enclosure. Every error and warning
    carries a `fix`. Categories not yet implemented appear in `skipped`, so an absent
    category never reads as clean.

    Needs no Radiance binaries and builds no scene, so it is cheap to re-run while fixing
    a model. import_geometry embeds the same report as result["health"].
    """
    from hcl_radiance.geometry_health import check_geometry_health
    from hcl_radiance.geometry_import import (
        _normalize_up_axis, load_sidecar, resolve_spec, scale_factor, split_map_metadata,
    )
    from hcl_radiance.geometry_obj import parse_obj

    if sidecar is not None:
        sc = load_sidecar(sidecar)
        material_map = material_map if material_map else sc.get("material_map")
        units = units if units is not None else sc.get("units")
        up_axis = up_axis if up_axis is not None else sc.get("up_axis")
    if not material_map:
        raise ValueError("check_geometry needs a material_map (or a sidecar providing one) "
                         "to classify glazing, floors and context geometry")
    # material_map may be a FLAT map (group specs at the top level alongside units/up_axis/
    # north_angle_deg and a _README, as office_room_material_map.json ships it) -- split it
    # the same way load_sidecar does, so a scalar key never gets read as a surface-library name.
    group_map, scalars = split_map_metadata(material_map)
    if group_map:
        material_map = group_map
        units = units if units is not None else scalars.get("units")
        up_axis = up_axis if up_axis is not None else scalars.get("up_axis")
    if up_axis is not None:
        up_axis = _normalize_up_axis(up_axis)

    with open(os.path.abspath(obj_path)) as fh:
        parsed = parse_obj(fh.read())
    resolved = {g: resolve_spec(v)[0] for g, v in material_map.items()}
    # Every health tolerance is absolute metres, so the model's unit scale must reach the checker
    # -- otherwise a mm model both MISSES real defects and hard-fails on valid geometry.
    return check_geometry_health(parsed, resolved, sensors=sensors,
                                 photosensors=photosensors,
                                 electric_lights=electric_lights,
                                 scale=scale_factor(units) if units else 1.0)


# detect_interior's innermost-wall-face rule finds the OUTER bbox for convex/rectangular
# rooms but collapses to an inner sub-rectangle (or a degenerate zero-extent bbox) for
# concave (L/T/U) rooms. If its area is below this fraction of the floor-footprint bbox
# area, treat it as untrustworthy and fall back to laying the grid over the floor bbox
# (relying on footprint clipping to trim the notch/off-floor cells).
_INTERIOR_TRUST_RATIO = 0.6


async def workplane_grid(obj_path: str, material_map: dict | None = None, sidecar: str | None = None,
                         units: str | None = None, up_axis: str | None = None,
                         north_angle_deg: float | None = None,
                         workplane_h: float = 0.8, border_offset: float = 0.25,
                         max_spacing: float | None = None, wall_thickness: float | None = None,
                         interior_extent: list | None = None,
                         clip_to_footprint: bool = True, footprint_border: float = 0.0,
                         write_pts: str | None = "grid.pts",
                         work_dir: str | None = None, ctx: Context | None = None) -> dict:
    """EN 12464-1 working-plane illuminance grid from an OBJ room.

    Interior extent via inner-surface detection (bbox of inward-facing vertical wall faces),
    plane at floor-top + workplane_h, max spacing p=0.2*5^log10(d) with d=the larger
    dimension of the calculation area (the interior inset by border_offset, per EN 12464-1 --
    not the raw interior extent), cell-centre points. Returns points
    [x,y,z,0,0,1] + a methodology breakdown; writes a .pts (write_pts=None to skip).
    material_map OR sidecar is required (to identify floor & walls).
    clip_to_footprint (default True) drops lattice cells outside the floor slab for
    non-rectangular rooms (ignored when interior_extent is supplied explicitly);
    footprint_border insets the kept region from the footprint edges.
    """
    from hcl_radiance.geometry_obj import parse_obj
    from hcl_radiance.geometry_import import scale_factor, load_sidecar, resolve_spec, _rotate_north
    from hcl_radiance.sensor_methodology import detect_interior, floor_top_z, en12464_grid
    from hcl_radiance.footprint import floor_polygons

    wd = await resolve_work_dir(ctx, work_dir)

    if sidecar is not None:
        sc = load_sidecar(sidecar)
        material_map = material_map if material_map else sc.get("material_map")
        units = units if units is not None else sc.get("units")
        up_axis = up_axis if up_axis is not None else sc.get("up_axis")
        if north_angle_deg is None:
            north_angle_deg = sc.get("north_angle_deg")
    if not material_map:
        raise ValueError("workplane_grid needs a material_map (or a sidecar providing one) to "
                         "identify the floor and walls")

    from hcl_radiance.geometry_import import _normalize_up_axis
    if up_axis is not None:
        up_axis = _normalize_up_axis(up_axis)

    scale = scale_factor(units) if units is not None else 1.0
    with open(os.path.abspath(obj_path)) as fh:
        parsed = parse_obj(fh.read())
    resolved = {g: resolve_spec(v)[0] for g, v in material_map.items()}

    interior = detect_interior(parsed, resolved, scale, up_axis,
                               wall_thickness=wall_thickness, override=interior_extent)
    ftz = floor_top_z(parsed, resolved, scale, up_axis)
    footprint = None
    if clip_to_footprint and interior_extent is None:
        footprint = floor_polygons(parsed, resolved, scale, up_axis)

    interior_xyxy = interior[:4]
    interior_source = interior[4]
    concave_fallback = False
    if footprint is not None:
        # detect_interior can collapse to an inner sub-rectangle (or a degenerate,
        # zero-extent bbox) for concave rooms; check it against the floor bbox before
        # trusting it, and fall back to the floor bbox (clipped to the footprint below)
        # when it looks wrong.
        fxs = [x for ring in footprint for x, y in ring]
        fys = [y for ring in footprint for x, y in ring]
        if fxs and fys:
            fxmin, fxmax, fymin, fymax = min(fxs), max(fxs), min(fys), max(fys)
            fb_area = (fxmax - fxmin) * (fymax - fymin)
            xmin, xmax, ymin, ymax = interior_xyxy
            di_w, di_h = xmax - xmin, ymax - ymin
            di_area = di_w * di_h if (di_w > 0 and di_h > 0) else 0.0
            if di_w <= 0 or di_h <= 0 or (fb_area > 0 and di_area < _INTERIOR_TRUST_RATIO * fb_area):
                t = wall_thickness or 0.0
                interior_xyxy = (fxmin + t, fxmax - t, fymin + t, fymax - t)
                interior_source = "footprint_bbox"
                concave_fallback = True

    points, methodology = en12464_grid(interior_xyxy, ftz, workplane_h=workplane_h,
                                       border_offset=border_offset, max_spacing=max_spacing,
                                       footprint=footprint, footprint_border=footprint_border)
    methodology["interior_extent_source"] = interior_source
    points = _rotate_north(points, north_angle_deg)

    warnings = []
    if interior[4].startswith("fallback"):
        warnings.append(f"interior extent via {interior[4]}: inner-surface detection found no "
                        f"inward-facing wall faces; result may include wall thickness")
    if concave_fallback:
        warnings.append("concave/degenerate interior from wall detection; grid laid over the "
                        "floor bounding box and clipped to the floor polygon")
    if methodology.get("clipped", {}).get("dropped"):
        warnings.append(f"{methodology['clipped']['dropped']} grid cell(s) fell outside the floor "
                        f"footprint and were dropped (non-rectangular room)")
    assumptions = [
        "d = larger INTERIOR dimension; cell counts derived from the calc area",
        f"border_offset={border_offset} m (EN 12464-1:2021 commonly uses 0.5 m)",
        "EN cell aspect-ratio (<=2) and absolute spacing caps are not enforced",
        "clip_to_footprint drops cells outside the floor slab; EN border is enforced only along "
        "the interior bounding box, not concave walls (raise footprint_border to inset all edges)",
    ]

    pts_path = None
    if write_pts:
        os.makedirs(wd, exist_ok=True)
        pts_path = os.path.join(wd, write_pts)
        write_text(pts_path, _pts_to_text(points))  # LF: fed to rtrace
    return {"points": points, "methodology": methodology, "pts_path": pts_path,
            "assumptions": assumptions, "warnings": warnings}


async def observer_points(obj_path: str, material_map: dict | None = None, sidecar: str | None = None,
                          units: str | None = None, up_axis: str | None = None,
                          north_angle_deg: float | None = None,
                          eye_height: float | list = 1.2, seat_pattern: str = r"(?i)chair.*seat|seat",
                          screen_pattern: str = r"(?i)disp.*panel|screen|monitor|display",
                          direction_fallback: str = "window", fallback_azimuth: float | None = None,
                          sweep_n: int = 8, workstations: list | None = None,
                          position_fallback: str | list = "room_center", clip_to_footprint: bool = True,
                          write_pts: str | None = "observers.pts",
                          work_dir: str | None = None, ctx: Context | None = None) -> dict:
    """Workstation eye-point observers from an OBJ room.

    Auto-detects seat objects (seat_pattern) paired to screen objects (screen_pattern) by trailing
    suffix: eye = seat centroid at floor-top+eye_height, gaze = eye->screen centroid (dz=0). Fallback
    when no screen: direction_fallback in {window, azimuth, sweep}. No seats: position_fallback. Pass
    workstations=[{eye:[x,y], target:[x,y]|azimuth}] to bypass detection. Returns observers + glare_views
    (DGP fisheye) + a .pts. material_map OR sidecar required.
    clip_to_footprint (default True) does NOT move observers (they are furniture-anchored) —
    it only reports, via a warning, any observer whose eye position falls outside the floor slab.
    """
    from hcl_radiance.geometry_obj import parse_obj
    from hcl_radiance.geometry_import import scale_factor, load_sidecar, resolve_spec, _rotate_north
    from hcl_radiance.sensor_layout import dgp_views
    from hcl_radiance.sensor_methodology import build_observers, detect_workstations, floor_top_z
    from hcl_radiance.footprint import floor_polygons, point_in_footprint

    wd = await resolve_work_dir(ctx, work_dir)

    if sidecar is not None:
        sc = load_sidecar(sidecar)
        material_map = material_map if material_map else sc.get("material_map")
        units = units if units is not None else sc.get("units")
        up_axis = up_axis if up_axis is not None else sc.get("up_axis")
        if north_angle_deg is None:
            north_angle_deg = sc.get("north_angle_deg")
    if not material_map:
        raise ValueError("observer_points needs a material_map (or a sidecar providing one) to "
                         "identify the floor and glazing")

    from hcl_radiance.geometry_import import _normalize_up_axis
    if up_axis is not None:
        up_axis = _normalize_up_axis(up_axis)

    scale = scale_factor(units) if units is not None else 1.0
    with open(os.path.abspath(obj_path)) as fh:
        parsed = parse_obj(fh.read())
    resolved = {g: resolve_spec(v)[0] for g, v in material_map.items()}

    observers = build_observers(parsed, resolved, scale, up_axis, eye_height=eye_height,
                                seat_pattern=seat_pattern, screen_pattern=screen_pattern,
                                direction_fallback=direction_fallback,
                                fallback_azimuth=fallback_azimuth, sweep_n=sweep_n,
                                workstations=workstations, position_fallback=position_fallback)

    rows = [o["eye"] + o["direction"] for o in observers]
    rows = _rotate_north(rows, north_angle_deg)
    for o, row in zip(observers, rows):           # write rotated coords back into observer dicts
        o["eye"], o["direction"] = list(row[:3]), list(row[3:])
    glare_views = dgp_views(rows)

    warnings = []
    methodology_footprint = False
    if clip_to_footprint:
        polys = floor_polygons(parsed, resolved, scale, up_axis, north_angle_deg=north_angle_deg)
        methodology_footprint = bool(polys)
        outside = [o["id"] for o, row in zip(observers, rows)
                   if polys and not point_in_footprint(row[0], row[1], polys)]
        if outside:
            warnings.append(f"{len(outside)} observer(s) fall outside the floor footprint "
                            f"(ids {outside}); check seat placement")
    if workstations:
        z_eyes = sum(1 for ws in workstations
                     if isinstance(ws.get("eye"), (list, tuple)) and len(ws["eye"]) > 2)
        if z_eyes:
            warnings.append(f"{z_eyes} workstation eye(s) supplied a Z coordinate; ignored — "
                            "eye Z is fixed at floor-top + eye_height")
        z_tgts = sum(1 for ws in workstations
                     if isinstance(ws.get("target"), (list, tuple)) and len(ws["target"]) > 2)
        if z_tgts:
            warnings.append(f"{z_tgts} workstation target(s) supplied a Z coordinate; ignored — "
                            "gaze is horizontal (dz=0)")
    unpaired = len({o["seat_object"] for o in observers if o["source"].startswith("fallback") and o.get("seat_object")})
    if unpaired:
        warnings.append(f"{unpaired} seat(s) had no paired screen; used {direction_fallback} fallback")

    # Transparency fields: run detection (or stub) to populate methodology
    if workstations:
        ftz_value = floor_top_z(parsed, resolved, scale, up_axis)
        det_seats: list = []
        det_screens: list = []
        det_pairings: list = []
        methodology = {"direction_fallback": direction_fallback,
                       "eye_heights": list(eye_height) if isinstance(eye_height, (list, tuple)) else [eye_height],
                       "n_observers": len(observers),
                       "floor_top_z": ftz_value,
                       "detected_seats": det_seats,
                       "detected_screens": det_screens,
                       "pairings": det_pairings,
                       "footprint_checked": methodology_footprint,
                       "explicit_workstations": True}
    else:
        det_pairings, det_seats_dict, det_screens_dict = detect_workstations(
            parsed, seat_pattern, screen_pattern)
        ftz_value = floor_top_z(parsed, resolved, scale, up_axis)
        det_seats = sorted(det_seats_dict.keys())
        det_screens = sorted(det_screens_dict.keys())
        paired_screens = {pr["screen"] for pr in det_pairings if pr["screen"] is not None}
        unpaired_screens = sorted(s for s in det_screens_dict if s not in paired_screens)
        if unpaired_screens:
            warnings.append(
                f"{len(unpaired_screens)} screen(s) had no matching seat suffix: {unpaired_screens}")
        methodology = {"direction_fallback": direction_fallback,
                       "eye_heights": list(eye_height) if isinstance(eye_height, (list, tuple)) else [eye_height],
                       "n_observers": len(observers),
                       "floor_top_z": ftz_value,
                       "detected_seats": det_seats,
                       "detected_screens": det_screens,
                       "pairings": det_pairings,
                       "footprint_checked": methodology_footprint}
    assumptions = ["gaze is horizontal (dz=0); eye anchored at seat centroid (no posture offset)",
                   "azimuth fallback is measured in the pre-north frame (exact when north=0)"]

    pts_path = None
    if write_pts:
        os.makedirs(wd, exist_ok=True)
        pts_path = os.path.join(wd, write_pts)
        write_text(pts_path, _pts_to_text(rows))  # LF: fed to rtrace
    return {"observers": observers, "points": rows, "glare_views": glare_views,
            "methodology": methodology, "pts_path": pts_path,
            "assumptions": assumptions, "warnings": warnings}


async def photosensors(obj_path: str, material_map: dict | None = None, sidecar: str | None = None,
                       units: str | None = None, up_axis: str | None = None,
                       north_angle_deg: float | None = None,
                       zone_rule: str = "head_height", depth_factors: list | None = None,
                       sensor_fraction: float = 2 / 3, task_height: float = 0.0,
                       mount: str = "workplane", workplane_h: float = 0.8,
                       write_pts: str | None = "photosensors.pts",
                       work_dir: str | None = None, ctx: Context | None = None) -> dict:
    """Daylight-dimming photosensors from an OBJ room (methodology.md §3).

    Locates the dominant glazed facade, builds sidelighting zones from the window head height
    (zone_rule='head_height' with depth_factors like [1,2], or 'ies_2.5'), and places one
    horizontal sensor per zone at sensor_fraction of the zone depth, centred on the facade and
    clipped to the floor. mount='workplane' (z=floor+workplane_h, up) or 'ceiling' (down).
    Returns points [x,y,z,dx,dy,dz] + a per-zone methodology; writes a .pts. material_map OR
    sidecar required (to identify floor & glazing).
    """
    from hcl_radiance.geometry_obj import parse_obj
    from hcl_radiance.geometry_import import scale_factor, load_sidecar, resolve_spec, _rotate_north
    from hcl_radiance.sensor_daylight import place_photosensors

    wd = await resolve_work_dir(ctx, work_dir)

    if sidecar is not None:
        sc = load_sidecar(sidecar)
        material_map = material_map if material_map else sc.get("material_map")
        units = units if units is not None else sc.get("units")
        up_axis = up_axis if up_axis is not None else sc.get("up_axis")
        if north_angle_deg is None:
            north_angle_deg = sc.get("north_angle_deg")
    if not material_map:
        raise ValueError("photosensors needs a material_map (or a sidecar providing one) to "
                         "identify the floor and glazing")

    from hcl_radiance.geometry_import import _normalize_up_axis
    if up_axis is not None:
        up_axis = _normalize_up_axis(up_axis)

    scale = scale_factor(units) if units is not None else 1.0
    with open(os.path.abspath(obj_path)) as fh:
        parsed = parse_obj(fh.read())
    resolved = {g: resolve_spec(v)[0] for g, v in material_map.items()}

    dfs = tuple(depth_factors) if depth_factors else (1, 2)
    points, methodology = place_photosensors(parsed, resolved, scale, up_axis,
                                             zone_rule=zone_rule, depth_factors=dfs,
                                             sensor_fraction=sensor_fraction, task_height=task_height,
                                             mount=mount, workplane_h=workplane_h)
    points = _rotate_north(points, north_angle_deg)

    warnings = []
    for zm in methodology["zones"]:
        if zm.get("snapped"):
            warnings.append(f"zone '{zm['name']}' sensor was snapped inward to stay on the floor "
                            f"(zone deeper than the room)")
    assumptions = [
        "sensor at 2/3 of the zone depth is a closed-loop rule of thumb, not a commissioned "
        "calibration",
        "modelled as a work-plane reference point at workplane_h; physical photosensors are usually "
        "ceiling-mounted (use mount='ceiling')",
        "inward direction is derived from the room centroid, not the glazing face normal",
    ]

    pts_path = None
    if write_pts:
        os.makedirs(wd, exist_ok=True)
        pts_path = os.path.join(wd, write_pts)
        write_text(pts_path, _pts_to_text(points))  # LF: fed to rtrace
    return {"points": points, "methodology": methodology, "pts_path": pts_path,
            "assumptions": assumptions, "warnings": warnings}


async def preview_scene(obj_path: str, material_map: dict | None = None, sidecar: str | None = None,
                        units: str | None = None, up_axis: str | None = None,
                        north_angle_deg: float | None = None, render: str = "all",
                        grid_pts: str | list | None = None, observer_pts: str | list | None = None,
                        photosensor_pts: str | list | None = None,
                        luminaire_groups: list | None = None, write_prefix: str = "preview",
                        work_dir: str | None = None, ctx: Context | None = None) -> dict:
    """matplotlib PNG preview of a room with sensor overlays (plan + 3D).

    render: 'grid' (grid, plan+3d), 'observers' (plan), 'observers_3d' (3d), or 'all'
    (all layers, plan+3d). Point layers are given as .pts paths OR inline [x,y,z,dx,dy,dz]
    rows in the post-north frame; layers left None are simply omitted. Diagnostic overlays
    only — not a photometric render. material_map OR sidecar required.
    """
    from hcl_radiance.geometry_obj import parse_obj
    from hcl_radiance.geometry_import import scale_factor, load_sidecar, resolve_spec
    from hcl_radiance.scene_preview import build_scene, render_plan, render_3d

    wd = await resolve_work_dir(ctx, work_dir)

    if sidecar is not None:
        sc = load_sidecar(sidecar)
        material_map = material_map if material_map else sc.get("material_map")
        units = units if units is not None else sc.get("units")
        up_axis = up_axis if up_axis is not None else sc.get("up_axis")
        if north_angle_deg is None:
            north_angle_deg = sc.get("north_angle_deg")
    if not material_map:
        raise ValueError("preview_scene needs a material_map (or a sidecar providing one)")

    scale = scale_factor(units) if units is not None else 1.0
    with open(os.path.abspath(obj_path)) as fh:
        parsed = parse_obj(fh.read())
    resolved = {g: resolve_spec(v)[0] for g, v in material_map.items()}
    scene = build_scene(parsed, resolved, scale, up_axis, north_angle_deg,
                        luminaire_groups=luminaire_groups)

    def _layer(v):
        if v is None:
            return None
        if isinstance(v, str):
            return _read_pts_rows(v)
        if isinstance(v, list):
            rows = []
            for item in v:
                if isinstance(item, str):
                    rows.extend(_read_pts_rows(item))   # a .pts file path
                else:
                    rows.append(item)                   # an inline [x,y,z,dx,dy,dz] row
            return rows
        return None

    all_layers = {"grid": _layer(grid_pts), "observers": _layer(observer_pts),
                  "photosensors": _layer(photosensor_pts)}
    all_layers = {k: v for k, v in all_layers.items() if v}

    presets = {
        "grid": ({"grid"}, ("plan", "3d")),
        "observers": ({"observers"}, ("plan",)),
        "observers_3d": ({"observers"}, ("3d",)),
        "all": (set(all_layers), ("plan", "3d")),
    }
    warnings = []
    if render not in presets:
        warnings.append(f"unknown render preset {render!r}; falling back to 'all'")
    keep, views = presets.get(render, presets["all"])
    layers = {k: v for k, v in all_layers.items() if k in keep}

    if not scene["footprint"]:
        warnings.append("no floor faces found; footprint outline will be empty")
    if not scene["luminaires"] and luminaire_groups:
        warnings.append("no luminaire footprints found for the given groups")
    if not layers and not scene["luminaires"]:
        warnings.append("no point layers to preview; grid_pts/observer_pts/photosensor_pts "
                        "all empty or omitted for the selected render preset")

    os.makedirs(wd, exist_ok=True)
    image_paths = []
    if "plan" in views:
        p = os.path.join(wd, f"{write_prefix}_{render}_plan.png")
        render_plan(scene, layers, p)
        image_paths.append(p)
    if "3d" in views:
        p = os.path.join(wd, f"{write_prefix}_{render}_3d.png")
        render_3d(scene, layers, p)
        image_paths.append(p)

    layer_counts = {k: len(v) for k, v in layers.items()}
    if scene["luminaires"]:
        layer_counts["luminaires"] = len(scene["luminaires"])
    return {"image_paths": image_paths, "format": "png", "render": render,
            "layers": layer_counts, "warnings": warnings}


def reference(topic: str = "overview") -> dict:
    """Look up HCL reference content. topic: bins | coefficients | caveats | overview."""
    if topic == "bins":
        return {"bins_9": data.BINS_9, "bins_3": data.BINS_3}
    if topic == "coefficients":
        return {"photopic_9": data.W_PHOTOPIC_9, "melanopic_9": data.W_MELANOPIC_9,
                "neuropic_9": data.W_NEUROPIC_9, "photopic_3": data.W_PHOTOPIC_3,
                "melanopic_3": data.W_MELANOPIC_3, "luminous_efficacy": data.LUMINOUS_EFFICACY}
    if topic == "caveats":
        return {"section_9_3": _resources.SECTION_9_3_CAVEATS}
    if topic == "overview":
        return {"overview": "hcl-mcp spectral/HCL toolkit. Topics: bins, coefficients, caveats, overview. "
                            "Resources: hcl://reference/{coefficients,bins}, hcl://action-spectrum/{type}, "
                            "hcl://preset/{name}, hcl://compliance/{standard}."}
    raise ValueError(f"unknown reference topic {topic!r}; choose from "
                     "['bins', 'coefficients', 'caveats', 'overview']")

# ---- Weather + annual transport / dosimetry (hcl_core.weather, hcl_radiance.annual, hcl_core.nvrd) ----
def _wea_summary(wea: dict) -> dict:
    """Compact digest of a parsed .wea: record count, first/last timestamp, DNI/DHI ranges.

    The raw .wea holds one row per hour (up to 8760), so echoing every months/days/hours/DNI/DHI
    array inline blows the MCP token budget (~238 KB for a full year). Callers that need the period
    rows already get them via `decomposed` (HOY + wea_lines) and the written `subset_wea` file.
    """
    n = len(wea.get("DNI", []))

    def _ts(i):
        return None if not n else [wea["months"][i], wea["days"][i], wea["hours"][i]]

    def _rng(key):
        vals = []
        for v in wea.get(key, []):
            try:
                vals.append(float(v))
            except (TypeError, ValueError):
                pass
        return [min(vals), max(vals)] if vals else None

    return {"n_records": n, "first": _ts(0), "last": _ts(n - 1) if n else None,
            "dni_range": _rng("DNI"), "dhi_range": _rng("DHI")}


def weather(wea_path: str | None = None, period: list | None = None, timestep_min: int = 60,
            subset_out: str | None = None) -> dict:
    """Ingest a .wea (DNI/DHI per timestamp) and/or decompose an analysis period into HOY + wea line numbers.

    Returns `wea_summary` (record count, first/last timestamp, DNI/DHI ranges) rather than the full
    per-hour arrays — those reach up to 8760 rows and overflow the response budget. Use `period` +
    `subset_out` to get the rows you actually need (HOY/wea_lines in `decomposed`, the subset .wea on disk).
    """
    out = {}
    if wea_path:
        out["wea_summary"] = _wea_summary(import_wea(wea_path))
    if period:
        if (not isinstance(period, (list, tuple)) or len(period) != 2
                or any(not isinstance(p, (list, tuple)) or len(p) != 3 for p in period)):
            raise ValueError("period must be [[m,d,h],[m,d,h]] (two endpoints, each [month,day,hour])")
        out["decomposed"] = decompose(analysis_period(tuple(period[0]), tuple(period[1])), timestep_min)
        if subset_out:
            if wea_path:
                write_text(subset_out, subset_wea(wea_path, out["decomposed"]["wea_lines"]))  # LF: fed to gendaymtx
                out["subset_wea"] = subset_out
            else:
                out["warning"] = ("subset_out was set but no wea_path was given; nothing to subset. "
                                  "Pass wea_path to write the period subset.")
    return out

def _ensure_points_path(points, work_dir: str, name: str = "annual_points.pts") -> str:
    """Normalize a `points` arg to a .pts file path.

    run_grid accepts inline [x,y,z,dx,dy,dz] rows OR a .pts path; the annual transports
    only consume a path (they stream it as rtrace/rfluxmtx stdin). To give the MCP tools one
    consistent contract, materialize an inline list to a .pts under work_dir and return its path;
    pass a string through unchanged.
    """
    if isinstance(points, str):
        return points
    os.makedirs(work_dir, exist_ok=True)
    path = os.path.join(work_dir, name)
    write_text(path, _pts_to_text(points))  # LF: fed to rtrace/rfluxmtx stdin
    return path


def _resolve_points(points, sensor_set, work_dir: str, name: str = "annual_points.pts") -> str:
    """Resolve a points arg to a .pts path. A named sensor_set wins over inline points."""
    if sensor_set:
        return _get_sensor_set(work_dir, sensor_set)["path"]
    if points is None:
        raise ValueError("provide points=[...] or sensor_set='name'")
    return _ensure_points_path(points, work_dir, name=name)


def _count_points_for(points, sensor_set, work_dir) -> int:
    """Count reference points without materializing/resolving them (weight-count validation)."""
    from hcl_radiance.annual import _count_points
    if sensor_set:
        return _get_sensor_set(work_dir, sensor_set)["count"]
    if isinstance(points, str):
        return _count_points(points, work_dir)
    return len(points) if points else 0


def _read_pts_rows(pts_path: str) -> list:
    """Read a .pts file into inline [x,y,z,dx,dy,dz] rows (daylight_factor needs indoor points
    inline to append an exterior reference in a separate sky-only run)."""
    with open(pts_path) as fh:
        return [[float(x) for x in ln.split()] for ln in fh if ln.strip()]


async def run_annual(channel_scenes: list, wea: str, points: str | list, channel_type: int = 1,
                     rad_params: str | None = None, quality: str | None = None, dosimetry_threshold: float | None = 250.0,
                     period: list | None = None, timestep_min: int = 60,
                     work_dir: str | None = None, run: bool = True, ctx: Context | None = None) -> dict:
    """Annual 2-phase DDS HCL simulation (per channel) -> annual mel-EDI + circadian dosimetry.

    channel_scenes: 1 dict (3ch) or 3 dicts (9ch), each {materials:[paths], geometry:path,
      sky_color:[r,g,b]}. NOTE each dict's `geometry` is a SINGLE .rad path (geometry_set[i] from
      import_geometry), not the whole geometry_set list.
    points: inline [x,y,z,dx,dy,dz] rows OR a .pts path (inline rows are written to a .pts for you,
      matching run_grid).
    period: optional [[m,d,h],[m,d,h]] analysis window; when given, the .wea is subset to that
    period before the run and real HOY drives dosimetry (omit to run the full year).
    Runs Radiance if present, else returns the exact command sequence.
    """
    wd = await resolve_work_dir(ctx, work_dir)
    points = _ensure_points_path(points, wd)
    kw = {"work_dir": wd, "run": run, "dosimetry_threshold": dosimetry_threshold,
          "period": period, "timestep_min": timestep_min}
    _rp = _resolve_rad_params(rad_params, quality)
    if _rp:
        kw["rad_params"] = _rp
    return await _offload(_run_annual, channel_scenes, wea, points, channel_type, **kw)

async def annual_daylight(channel_scenes: list, wea: str, points: str | list | None = None,
                          sensor_set: str | None = None, channel_type: int = 1,
                          rad_params: str | None = None, quality: str | None = None, da_threshold: float = 300.0,
                          udi_lower: float = 100.0, udi_sup: float = 300.0, udi_aut: float = 3000.0,
                          sda_da_fraction: float = 0.5, ase_threshold: float = 1000.0,
                          ase_hours: float = 250.0, occupancy: list | None = None,
                          occupied_start: int = 8, occupied_end: int = 18, timestep_min: int = 60,
                          shading_model: str | None = None,
                          work_dir: str | None = None, run: bool = True,
                          ctx: Context | None = None) -> dict:
    """Annual climate-based daylight metrics on the grid: per-point DA/cDA/UDI + spatial sDA/ASE.

    channel_scenes: 1 dict (3ch) or 3 dicts (9ch), each {materials:[paths], geometry:path,
      sky_color:[r,g,b]} -- same shape as run_annual. points: inline rows or a .pts path; OR pass
      sensor_set='name' (created via the sensors tool). ASE uses a dedicated direct-only (-ab 0)
      pass. occupancy: optional per-timestep 0/1 mask (defaults to weekday occupied_start..end,
      Monday-anchored 8760-h). Runs Radiance if present, else returns the command sequence.

    shading_model: declare the scene's operable shading -- 'none' (no device modelled),
      'modelled' (a device is in the geometry) or 'lm83_default_blind'. The returned `sDA_basis`
      block records it alongside the analysis period and says whether the `sDA` key is an LM-83
      sDA or only the underlying DA-based spatial fraction. Left undeclared it reports
      'undeclared' and `lm83_conformant: false` -- the metric is never assumed conformant.
    """
    wd = await resolve_work_dir(ctx, work_dir)
    pts = _resolve_points(points, sensor_set, wd)
    if run:
        proceed = await confirm_run(ctx, _LONG_RUN_QUESTIONS["annual_daylight"])
        if isinstance(proceed, InputRequiredResult):
            return proceed  # the question itself: the client answers by calling again
        if proceed is False:
            run = False
    kw = {"work_dir": wd, "run": run}
    _rp = _resolve_rad_params(rad_params, quality)
    if _rp:
        kw["rad_params"] = _rp
    sim = await _offload(_run_annual_daylight, channel_scenes, wea, pts, channel_type, **kw)
    if not sim.get("ran"):
        return emit_envelope(False, commands=sim.get("commands"), reason=sim.get("reason"))
    if "lux_matrix" not in sim:
        return emit_envelope(True, error=sim.get("error"), failed_step=sim.get("failed_step"))
    n_ts = sim["n_timesteps"]
    if occupancy is not None and len(occupancy) != n_ts:
        raise ValueError(f"occupancy length ({len(occupancy)}) must match the simulated timesteps ({n_ts})")
    occ = occupancy if occupancy is not None else _default_schedule(n_ts, occupied_start, occupied_end)
    metrics = _daylight_metrics(sim["lux_matrix"], occ, da_threshold=da_threshold,
                                udi=(udi_lower, udi_sup, udi_aut), sda_da_fraction=sda_da_fraction,
                                ase_threshold=ase_threshold, ase_hours=ase_hours,
                                sun_lux_matrix=sim["sun_lux_matrix"], step_hours=timestep_min / 60.0,
                                shading_model=shading_model)
    # The convergence warning must cross this boundary with the rad_params that caused it: the
    # core computes it, but an envelope that forwards only the metrics drops exactly the field
    # that says those metrics are sampling-limited. Threshold metrics (DA/sDA/UDI) are what move
    # most under coarse ambient sampling, and nothing else in this return would reveal it.
    extra = {k: sim[k] for k in ("convergence_warning", "rad_params") if sim.get(k)}
    return emit_envelope(True, n_points=sim["n_points"], n_timesteps=n_ts, metrics=metrics, **extra)

async def lm83_daylight(obj_path: str, material_map: dict, wea: str,
                        points: str | list | None = None, sensor_set: str | None = None,
                        units: str = "m", up_axis: str = "Z",
                        north_angle_deg: float | None = None,
                        areas: list | None = None, floor_area_m2: float | None = None,
                        blind: dict | None = None, window_groups: list | None = None,
                        latitude: float | None = None, declared_no_blinds: bool = False,
                        v_params: str | None = None, d_params: str | None = None,
                        quality: str | None = None, work_dir: str | None = None,
                        run: bool = True, ctx: Context | None = None) -> dict:
    """IES LM-83-12 sDA(300/50%) and ASE(1000,250h) with MANDATORY operable blinds.

    Unlike annual_daylight, which computes the arithmetic of sDA/ASE on whatever shading the
    scene happens to contain, this runs LM-83's method: a three-phase (V.T.D.s) engine per
    window group, an hourly blind that closes when 2.2.6's direct-sun trigger fires, and a
    zero-bounce ASE pass with blinds retracted and no sky or ground (3.2.6, 3.3).

    obj_path + material_map: the same OBJ room and material mapping import_geometry takes.
    Glazing must be mapped {"type": "glass", "tvis": ...} -- window groups are formed from
    those faces, and with no glass face there is no window to operate.

    units (mm|cm|m|ft) and up_axis (Y|Z) describe the OBJ, defaulting to metres and Z-up;
    north_angle_deg is the clockwise azimuth post-remap +Y points toward. These decide the
    facade azimuths that window grouping keys on, so a wrong up_axis silently regroups the
    windows.

    points: inline rows or a .pts path, OR sensor_set='name'. Grid spacing, workplane height
    and wall offset are MEASURED from these coordinates and reported, never accepted as
    parameters.

    areas: 2.2.6 trigger areas, [{name, area_m2, point_indices}], split by facade orientation
    and each under 10,000 sf -- the trigger must hold in EVERY area, and pooling facades
    dilutes the fraction so blinds close later than the standard requires. Omit and pass
    floor_area_m2 to get a single whole-grid area, which is only correct for a single-facade
    space. An area over 10,000 sf is refused before any Radiance runs.

    blind: the operable shade, per 2.2.7. Omitted -> the unknown-shade default of 5% diffuse
    VLT. {"shade_type": "fabric", "vlt": .., "openness": ..}, {"shade_type": "louver",
    "reflectance": >0.8} for the 20% white-louver branch, or {"bsdf": "path.xml"} for a
    measured Klems file. Note the default is 5%, NOT 20% -- the 20% figure is the louver
    branch and needs a declared reflectance.

    window_groups: optionally declare grouping instead of auto-clustering by azimuth and
    plane, [{name, face_indices, role}] with role 'view' or 'clerestory' -- 2.2.6 asks that
    view groups close before clerestory ones, and role cannot be inferred from azimuth.

    declared_no_blinds: assert the design documents state no blinds (2.2.6's escape clause).
    Reported as a per-group condition; it never replaces the headline, which always operates
    blinds.

    Returns `metrics` (sDA, ASE, per_point_DA, conditions) plus blind_hours and the window
    groups. The conformance flag is `lm83_method_conformant` and is presently ALWAYS FALSE:
    2.2.8-2.2.11's model-input clauses (dirt depreciation, frame occlusion, reveals,
    obstructions, interior reflectance defaults, mandatory furniture) are out of scope, so
    glazing runs at its raw tvis and sDA is biased upward -- roughly 32% of transmitted flux
    on an unknown-frame vertical window. Read `metrics.conditions.departures` before quoting
    a number; this is not by itself an LM-83 or LEED submission.
    """
    wd = await resolve_work_dir(ctx, work_dir)
    pts = _resolve_points(points, sensor_set, wd, name="lm83_points.pts")
    n_pts = _count_points_for(points, sensor_set, wd)
    if not n_pts:
        raise ValueError("provide points=[...] or sensor_set='name'")
    # run_lm83 measures the grid conditions (2.2.5 spacing, workplane height, wall offset)
    # from the coordinates themselves, so it needs the rows, not the path.
    point_rows = _read_pts_rows(pts)

    if areas is None:
        if floor_area_m2 is None:
            raise ValueError(
                "LM-83 2.2.6 evaluates the blind trigger per analysis area, so pass "
                "areas=[{name, area_m2, point_indices}] split by facade orientation, or "
                "floor_area_m2 to treat the whole grid as one area (correct only for a "
                "single-facade space)")
        areas = [{"name": "whole_grid", "area_m2": float(floor_area_m2),
                  "point_indices": list(range(len(point_rows)))}]

    if run:
        proceed = await confirm_run(ctx, _LONG_RUN_QUESTIONS["lm83_daylight"])
        if isinstance(proceed, InputRequiredResult):
            return proceed  # the question itself: the client answers by calling again
        if proceed is False:
            run = False

    from hcl_radiance.geometry_obj import parse_obj
    with open(obj_path) as fh:
        parsed = parse_obj(fh.read())
    scene = await _offload(_import_geometry, obj_path, material_map=material_map, units=units,
                           up_axis=up_axis, north_angle_deg=north_angle_deg,
                           work_dir=wd, run=run)
    geometry_set = scene.get("geometry_set") or []
    material_sets = scene.get("material_sets") or []
    if not geometry_set or not material_sets:
        return emit_envelope(False, reason=(
            "import_geometry produced no scene for this OBJ; check material_map covers "
            f"every group. Import reported: {scene.get('warnings') or scene.get('error')}"))
    # `exterior` is empty by construction: import_geometry writes type:"context" groups into
    # the same per-channel geometry .rad as the room, so the fixed shading LM-83 3.2.6 wants
    # kept in the ASE model is already in `geometry`. `context_groups` is a list of OBJ group
    # NAMES, not paths -- forwarding it here would hand oconv a bare name.
    lm_scene = {"materials": material_sets[0], "geometry": geometry_set[0],
                "exterior": [], "sky_color": [1, 1, 1]}

    kw = {"work_dir": wd, "areas": areas, "point_rows": point_rows, "run": run,
          "blind": blind, "declared_groups": window_groups, "latitude": latitude,
          "declared_no_blinds": declared_no_blinds}
    if _resolve_rad_params(v_params, quality):
        kw["v_params"] = _resolve_rad_params(v_params, quality)
    if _resolve_rad_params(d_params, quality):
        kw["d_params"] = _resolve_rad_params(d_params, quality)

    out = await _offload(_run_lm83, lm_scene, parsed, material_map, wea, pts, n_pts, **kw)
    if not out.get("ran"):
        # Forward the grouping on the emit path too. How the windows were grouped is the
        # main thing a dry run is for -- 2.2.6 grouping drives both the trigger and the
        # state count, and it is decided before any Radiance step runs.
        preview = {k: out[k] for k in ("window_groups", "blind_source", "states_simulated")
                   if k in out}
        return emit_envelope(False, commands=out.get("commands"),
                             reason=out.get("reason"), **preview)
    if "metrics" not in out:
        return emit_envelope(True, error=out.get("error"),
                             failed_step=out.get("failed_step"),
                             window_groups=out.get("window_groups"))
    return emit_envelope(True, metrics=out["metrics"], blind_hours=out["blind_hours"],
                         window_groups=out["window_groups"],
                         blind_source=out["blind_source"],
                         states_simulated=out["states_simulated"])

async def daylight_factor(scene_sets: list, points: str | list | None = None,
                          sensor_set: str | None = None, rad_params: str | None = None, quality: str | None = None,
                          month: int = 6, day: int = 21, hour: float = 12.0, gnd_refl: float = 0.2,
                          work_dir: str | None = None, run: bool = True,
                          ctx: Context | None = None) -> dict:
    """Daylight Factor (%) per point under the CIE Standard Overcast Sky (gensky -c).

    DF = E_indoor / E_outdoor * 100, with E_outdoor traced from a sky-only exterior reference.
    scene_sets: the building scene as a single 3-channel list of .rad paths (materials + geometry);
    the overcast sky is added internally. points: inline rows or a .pts path, OR sensor_set='name'.
    Returns df_per_point + df_avg/df_min/uniformity + e_outdoor, or the command plan when not run.
    """
    wd = await resolve_work_dir(ctx, work_dir)
    pts = _resolve_points(points, sensor_set, wd)
    indoor_points = _read_pts_rows(pts)
    kw = {"work_dir": wd, "run": run, "month": month, "day": day, "hour": hour, "gnd_refl": gnd_refl}
    _rp = _resolve_rad_params(rad_params, quality)
    if _rp:
        kw["rad_params"] = _rp
    out = await _offload(_run_daylight_factor, scene_sets, indoor_points, **kw)
    if not out.get("ran"):
        return emit_envelope(False, commands=out.get("commands"), reason=out.get("reason"))
    if "df_per_point" not in out:
        return emit_envelope(True, error=out.get("error"), failed_step=out.get("failed_step"))
    return emit_envelope(True, result=out)

def nvrd(spectral_series: str | list, timestep_h: float = 0.1, hours: list | None = None) -> dict:
    """Light-driven alerting response over time (Amundadottir nvRD).

    spectral_series: per-timestep spectral irradiance rows (311 pts 390-700 nm, or 401 pts 380-780)
      as an inline list, OR a path to a text/CSV file with one row per line. PREFER THE FILE PATH for
      large/full-resolution series: a big inline array can be truncated over the MCP wire (e.g. 401-pt
      rows arriving as 367) and then fail the row-length check. Rows must be a SINGLE point+view
      orientation, in CHRONOLOGICAL order, ideally uniformly spaced at timestep_h. Pre-group
      multi-orientation/multi-day data and call once per orientation (§9.4 — the source's automatic
      per-orientation grouping is not reproduced in v1).
    timestep_h: hours per step. Must be <= 0.3 and yield odd nvRD filter lengths; the model is
      validated at 0.1 (= 6 min), the recommended value. Other steps raise ValueError. You supply
      the series (no Daysim).
    hours: optional explicit per-timestep hour vector for non-uniform spacing; must be monotonically
      non-decreasing. When omitted, a uniform grid (i*timestep_h) is used.
    Returns effective_irradiance, relative_response, and cumulative_response per timestep.
    """
    return _nvrd(spectral_series, timestep_h=timestep_h, hours=hours)


# ---- IES luminaires (hcl_core.ies, hcl_radiance.ies_radiance) ----
def ies_analyze(ies: str) -> dict:
    """Parse an IESNA LM-63 luminaire and return its photometric report (rated lumens, watts,
    efficacy, max candela + location, beam/field angles, zonal flux down/up, LOR).

    ies: raw IES text or a file path.
    """
    return _analyze_ies(_parse_ies(ies))


async def ies_to_radiance(ies: str, placement: dict | None = None, color: list | None = None,
                          lamp: str | None = None, units: int = 2, units_divisor: int | None = None,
                          multiplier: float = 1.0, maintenance_factor: float = 1.0,
                          out_prefix: str | None = None, work_dir: str | None = None,
                          run: bool = True, ctx: Context | None = None) -> dict:
    """Convert an IES luminaire to a Radiance .rad via ies2rad, optionally placed via xform.

    -m carries user scaling only (multiplier * maintenance_factor); ies2rad applies the IES
    candela/ballast/pfactor itself. Runs ies2rad if Radiance is present, else returns the commands.
    """
    wd = await resolve_work_dir(ctx, work_dir)
    prefix = out_prefix or "luminaire"
    steps = [{"cmd": build_ies2rad(ies, multiplier=multiplier, maintenance_factor=maintenance_factor,
                                   color=color, lamp=lamp, units=units, units_divisor=units_divisor,
                                   out_prefix=prefix), "stdout": f"{prefix}.rad"}]
    if placement:
        os.makedirs(wd, exist_ok=True)
        block = place_luminaires(f"{prefix}.rad", placement)
        with open(os.path.join(wd, f"{prefix}_placed.rad"), "w") as fh:
            fh.write(block)
        steps.append({"cmd": ["xform", f"{prefix}_placed.rad"], "stdout": f"{prefix}_instances.rad"})
    available = run and _radiance_status()["available"]
    return await _offload(run_sequence, steps, work_dir=wd, available=available)


async def glare_ugr(scene_sets: list, channel_type: int = 0, view: str = "-vta -vh 180 -vv 180",
                    electric_lights: list | None = None, x: int = 800, y: int = 800,
                    rad_params: str | None = None, quality: str | None = None, glare_params: str | None = None,
                    work_dir: str | None = None, run: bool = True, ctx: Context | None = None) -> dict:
    """Render a fisheye (daylight and/or electric_lights) and run evalglare -> UGR/DGP/glare sources.

    Delegates to run_image with glare=True. Runs Radiance if present, else returns the commands.
    """
    wd = await resolve_work_dir(ctx, work_dir)
    kw = {"channel_type": channel_type, "view": view, "x": x, "y": y,
          "electric_lights": electric_lights, "glare": True, "glare_params": glare_params,
          "work_dir": wd, "run": run}
    _rp = _resolve_rad_params(rad_params, quality)
    if _rp:
        kw["rad_params"] = _rp
    return await _offload(_run_image, scene_sets, **kw)

# ---- Controls / energy (hcl_core.lighting_controls + daylight_savings orchestration) ----
def lighting_controls(itot_per_point: list | None = None, itot_series: list | None = None,
                      weights: list | None = None, iset: float = 500.0,
                      control_type: str = "ContinuousOff", fP_min: float = 0.15,
                      fL_min: float = 0.05, n_steps: int = 3, p_rated: float = 448.0,
                      schedule: float | list | None = None, area: float | None = None,
                      workbook_compat: bool = False) -> dict:
    """Daylight-responsive lighting-control calculator (EnergyPlus §7.3.5; verified vs elec_lights.xlsx).

    Point-in-time: pass itot_per_point=[lx at each reference point] -> {fL, fP, FP, P_elec, P_saved,
    reduction}. Annual/series: pass itot_series=[[lx per point] per hour] + area -> {per_hour,
    annual_kwh, annual_kwh_per_m2, mean_FP, mean_reduction, occupied_hours}. weights are the per-point
    area weights (e.g. from area_weights_from_geometry). control_type: ContinuousOff (default) |
    Continuous | Stepped. workbook_compat=True reproduces the elec_lights.xlsx off-gates (regression).
    """
    params = dict(iset=iset, control_type=control_type, fP_min=fP_min, fL_min=fL_min,
                  n_steps=n_steps, p_rated=p_rated)
    if not weights:
        raise ValueError("weights is required: pass the per-point area weights (e.g. [1.0] for a "
                         "single reference point, or area_weights_from_geometry(...))")
    if itot_series is not None:
        return _controls_series(itot_series, weights, schedule=schedule, area=area,
                                workbook_compat=workbook_compat, **params)
    if itot_per_point is not None:
        sch = schedule if isinstance(schedule, (int, float)) else 1.0
        return _controls_point(itot_per_point, weights, schedule=sch,
                               workbook_compat=workbook_compat, **params)
    raise ValueError("provide itot_per_point (point-in-time) or itot_series (annual)")


def _daylight_lux_per_point(metrics):
    """Pull per-point photopic lux out of a run_grid/run_annual metrics structure (one value/point)."""
    if isinstance(metrics, list):
        return [m["photopic_lux"] for m in metrics]
    return [metrics["photopic_lux"]]


async def daylight_savings(scene_sets: list | None = None, channel_scenes: list | None = None,
                           points: str | list | None = None, sensor_set: str | None = None,
                           wea: str | None = None, channel_type: int = 1,
                           weights: list | None = None, mode: str = "point_in_time",
                           iset: float = 500.0, control_type: str = "ContinuousOff",
                           fP_min: float = 0.15, fL_min: float = 0.05, n_steps: int = 3,
                           p_rated: float = 448.0, area: float | None = None,
                           schedule: float | list | None = None, workbook_compat: bool = False,
                           rad_params: str | None = None, quality: str | None = None, work_dir: str | None = None,
                           run: bool = True, ctx: Context | None = None) -> dict:
    """Automated daylight-responsive savings: daylight sim at the reference points -> lighting_controls.

    mode='point_in_time' uses run_grid (scene_sets + points; supports multiple reference points);
    mode='annual' uses run_annual_daylight (channel_scenes + wea + points, 8760 h) and supports a
    multi-point grid (one weight per reference point) via points=[...] or sensor_set='name'.
    run=False emits the command plan without executing. An annual run elicits confirmation first
    (it is long); decline -> the emitted plan is returned.

    weights: one per reference point, interpreted as that daylight zone's FLOOR-AREA FRACTION, so
    they must sum to <= 1.0 (NOT one-per-zone full-power flags -- e.g. [1, 1] is invalid; use
    [0.4, 0.3] etc.). The leftover (1 - Σweights) is the uncontrolled core area billed at full
    power. For a single point pass [1.0]. Compute proper fractions with
    hcl_core.lighting_controls.area_weights_from_geometry(width, length, window_head, task_height).

    Return shapes: {"ran": False, ...commands...} (not executed); {"ran": True, "error": ...,
    "failed_step": ...} (a Radiance step failed mid-run); else {"ran": True, "mode": ...,
    "controls": ...} on success.

    Note: in annual mode with schedule=None, the default weekday 08:00-18:00 mask is built to the
    length run_annual returns and assumes an 8760-h, Monday-anchored (HOY 0 = Mon 00:00) series. If
    run_annual is run over a sub-period or a non-Monday-anchored year, pass an explicit `schedule`.
    """
    wd = await resolve_work_dir(ctx, work_dir)
    if mode not in {"point_in_time", "annual"}:
        raise ValueError(f"mode must be 'point_in_time' or 'annual', got {mode!r}")
    params = dict(iset=iset, control_type=control_type, fP_min=fP_min, fL_min=fL_min,
                  n_steps=n_steps, p_rated=p_rated)

    # Validate weights BEFORE any (potentially long) simulation or confirmation prompt.
    if mode == "annual":
        # v2: annual supports a multi-point grid. weights (one floor-area fraction per reference
        # point, summing to <= 1.0) must match the point count when given.
        n_pts = _count_points_for(points, sensor_set, wd)
        if weights is not None and n_pts and len(weights) != n_pts:
            raise ValueError(f"annual weights must have one entry per reference point: got "
                             f"{len(weights)} weight(s) for {n_pts} point(s)")
    else:  # point_in_time (unchanged)
        if not weights:
            raise ValueError("weights is required: pass the per-point area weights (e.g. [1.0] for a "
                             "single reference point, or area_weights_from_geometry(...))")
        # DEF-7: catch a weight/point-count mismatch here with a user-facing message, instead of the
        # opaque internal "fps and weights must be the same length" raised deep in lighting_controls.
        from hcl_radiance.annual import _count_points
        n_pts = _count_points(points, wd) if isinstance(points, str) else (len(points) if points else 0)
        if n_pts and len(weights) != n_pts:
            raise ValueError(f"weights must have one entry per reference point: got {len(weights)} "
                             f"weight(s) for {n_pts} point(s)")

    if mode == "annual" and run:
        proceed = await confirm_run(ctx, _LONG_RUN_QUESTIONS["daylight_savings"])
        if isinstance(proceed, InputRequiredResult):
            return proceed  # the question itself: the client answers by calling again
        if proceed is False:
            run = False  # declined -> fall through to the emit path

    if mode == "annual":
        pts = _resolve_points(points, sensor_set, wd)
        kw = {"work_dir": wd, "run": run, "ase": False}   # savings needs total lux only, not ASE
        _rp = _resolve_rad_params(rad_params, quality)
        if _rp:
            kw["rad_params"] = _rp
        sim = await _offload(_run_annual_daylight, channel_scenes, wea, pts, channel_type, **kw)
        if not sim.get("ran"):
            return emit_envelope(False, mode="annual", commands=sim.get("commands"),
                                 reason=sim.get("reason"))
        if "lux_matrix" not in sim:  # ran, but a Radiance step failed (non-zero returncode)
            return emit_envelope(True, mode="annual", error=sim.get("error"),
                                 failed_step=sim.get("failed_step"))
        lux = sim["lux_matrix"]                                   # [n_pts][n_ts]
        n_ts = sim["n_timesteps"]
        series = [[lux[p][t] for p in range(len(lux))] for t in range(n_ts)]  # [n_ts][n_pts]
        applied_weights = weights if weights else [1.0 / len(lux)] * len(lux)
        controls = _controls_series(series, applied_weights, schedule=schedule, area=area,
                                    workbook_compat=workbook_compat, **params)
        return emit_envelope(True, mode="annual", n_timesteps=n_ts,
                             applied_weights=applied_weights, controls=controls)

    # point_in_time
    gkw = {"work_dir": wd, "run": run}
    _rp = _resolve_rad_params(rad_params, quality)
    if _rp:
        gkw["rad_params"] = _rp
    sim = await _offload(_run_grid, scene_sets, points, channel_type, **gkw)
    if not sim.get("ran"):
        return emit_envelope(False, mode="point_in_time", commands=sim.get("commands"),
                             reason=sim.get("reason"))
    if "daylight" not in sim:  # ran, but a Radiance step failed (non-zero returncode)
        return emit_envelope(True, mode="point_in_time", error=sim.get("error"),
                             failed_step=sim.get("failed_step"))
    # run_grid returns the daylight-only per-point metrics under sim["daylight"]["metrics"].
    itot = _daylight_lux_per_point(sim["daylight"]["metrics"])
    # Pass the control knobs explicitly (controls_point has no **params catch-all, unlike
    # controls_series): unpacking the heterogeneous `params` dict trips the type checker.
    controls = _controls_point(itot, weights, iset=iset, control_type=control_type,
                               fP_min=fP_min, fL_min=fL_min, n_steps=n_steps, p_rated=p_rated,
                               workbook_compat=workbook_compat)
    return emit_envelope(True, mode="point_in_time", daylight_lux=itot, controls=controls)


# ---- Daysim (hcl_daysim: status / build / sub-hourly) + spectral reconstruction / annual nvRD ----
def daysim_status() -> dict:
    """Report Daysim availability (ds_shortterm + epw2wea) via HCL_DAYSIM_BIN or PATH.

    Returns {available, bin_dir, version, found, missing}. No subprocess run except a best-effort
    version probe. Daysim is built from source locally (never bundled); use build_daysim if missing.
    """
    return _daysim_status()


async def build_daysim(src_dir: str | None = None, run: bool = True,
                       work_dir: str | None = None, ctx: Context | None = None) -> dict:
    """Build Daysim (ds_shortterm + epw2wea) from source: clone master + headless arm64 CMake.

    run=True executes if git+cmake are present; otherwise returns the ordered command plan + a reason.
    On success, bin_dir is the build/bin directory — set it as HCL_DAYSIM_BIN. Daysim is NOT bundled
    (NRC/Fraunhofer ISE source-available EULA); this clones+builds on your machine.
    """
    return await _offload(_build_daysim, src_dir=src_dir, run=run, work_dir=work_dir)


_MAX_INLINE_TIMESTEPS = 2000  # ~ a few days at 6-min; a full year (87600) is written to a sidecar


def _trim_subhourly_result(res: dict, work_dir: str) -> dict:
    """DEF-6: a full-year sub-hourly run yields ~87600 timestamps + solar_zeniths (~2.7 MB), far too
    large to return inline over the MCP wire. Persist the pair to a sidecar CSV next to the .wea and
    replace the inline arrays with a path + count + a small head/tail preview. Small series (<=
    _MAX_INLINE_TIMESTEPS) are returned inline unchanged. The core Python function still returns the
    full arrays for in-process callers (e.g. annual_nvrd)."""
    ts = res.get("timestamps")
    if not ts or len(ts) <= _MAX_INLINE_TIMESTEPS:
        return res
    zen = res.get("solar_zeniths") or []
    side = os.path.join(work_dir, "subhourly_timesteps.csv")
    with open(side, "w") as fh:
        fh.write("index,timestamp,solar_zenith_deg\n")
        for i, t in enumerate(ts):
            z = zen[i] if i < len(zen) else ""
            fh.write(f"{i},{t},{z}\n")
    preview = [str(t) for t in (ts[:3] + ts[-3:])]
    out = {k: v for k, v in res.items() if k not in ("timestamps", "solar_zeniths")}
    out["timesteps_csv"] = side
    out["n_timesteps"] = len(ts)
    out["timesteps_preview"] = preview
    out["note"] = (f"{len(ts)} timesteps written to subhourly_timesteps.csv "
                   "(omitted inline to stay within the MCP response budget).")
    return out


async def generate_subhourly_wea(epw: str, timestep_min: int = 6, latitude: float | None = None,
                                 longitude: float | None = None, time_zone: float | None = None,
                                 site_elevation: float | None = None, solar_time: int = 0,
                                 work_dir: str | None = None, run: bool = True,
                                 ctx: Context | None = None) -> dict:
    """EPW -> sub-hourly broadband .wea via Daysim (epw2wea -> .hea -> ds_shortterm).

    timestep_min default 6 (0.1 h) satisfies the nvRD step guard. Site location defaults to the EPW's
    own LOCATION line (converted to the DAYSIM convention), so normally you only pass the epw + work_dir.
    Pass explicit latitude/longitude/time_zone/site_elevation only to override — and only in DAYSIM
    convention: WEST-positive longitude, time_zone in DEGREES (= -15 × UTC offset); do NOT pass raw EPW
    East-positive coordinates. Runs Daysim if present, else returns the command plan + the written .hea
    so you can build Daysim and run it yourself.
    """
    wd = await resolve_work_dir(ctx, work_dir)
    res = await _offload(_generate_subhourly_wea, epw, timestep_min=timestep_min,
                         latitude=latitude, longitude=longitude, time_zone=time_zone,
                         site_elevation=site_elevation, solar_time=solar_time,
                         work_dir=wd, run=run)
    return _trim_subhourly_result(res, wd)


def reconstruct_spectrum(sky_channels: list, sun_channels: list, channel_type: int = 1,
                         method: str = "reference", sky_spd: list | None = None,
                         sun_spd: list | None = None,
                         sun_spectral: str = "colored", solar_zenith: float | None = None,
                         dseries_sky: bool = False, sky_cct: float | None = None) -> dict:
    """Reconstruct a 401-value 380-780 nm @1 nm per-nm spectrum from sky+sun channel sets (spec §5.2).

    method: 'faithful' (flat §9.3a step-expansion + neutral sun -> reproduces the legacy 2.0 method) or 'reference'
      (reference-SPD-shaped sky + air-mass colored direct sun; re-integrates to the channel bin totals).
      sun_spectral: 'colored' (air-mass solar SPD by solar_zenith) | 'neutral' (flat). dseries_sky=True
      reconstructs a per-timestep CIE D-series sky from sky_cct. sun_spd: optional 401-value physical
      sun reference that overrides the air-mass template. Returns the spectrum + the flat-vs-reference
      and neutral-vs-colored-sun divergence (always surfaced).
    """
    spectrum = _reconstruct_spectrum(sky_channels, sun_channels, channel_type, method=method,
                                     sky_spd=sky_spd, sun_spd=sun_spd, sun_spectral=sun_spectral,
                                     solar_zenith=solar_zenith,
                                     dseries_sky=dseries_sky, sky_cct=sky_cct)
    divergence = _recon_divergence(sky_channels, sun_channels, channel_type, sky_spd=sky_spd,
                                   solar_zenith=solar_zenith, dseries_sky=dseries_sky, sky_cct=sky_cct)
    return {"spectrum": spectrum, "n": len(spectrum), "method": method, "divergence": divergence}


async def annual_nvrd(point_xyz: list, view_vec: list, epw: str | None = None,
                      channel_scenes: list | None = None, points: str | list | None = None,
                      channel_type: int = 1, timestep_min: int = 6,
                      reconstruction: str = "both", sky_reconstruction: str = "reference",
                      sun_spectral: str = "colored", sky_cct: float | None = None,
                      rad_params: str | None = None, quality: str | None = None, work_dir: str | None = None,
                      run: bool = True, physical_sky: bool = False,
                      engine: str = "spectrl2", ctx: Context | None = None) -> dict:
    """Annual light-driven alertness (nvRD R_D) straight from weather (spec §5.1). LONG-RUNNING.

    EPW -> Daysim sub-hourly .wea -> colored 2-phase DDS (sky & sun separate) -> per-timestep dual
    reconstruction (faithful flat + neutral sun; enhanced reference sky + air-mass colored sun) ->
    nvRD twice -> {faithful:{R_D,RD_cum}, enhanced:{R_D,RD_cum}, divergence, RD_series_divergence}.
    R_D is RELATIVE only. SINGLE reference point+view per run. reconstruction={both|faithful|enhanced}
    (default both). timestep_min default 6 (0.1 h). run=False emits the full Daysim+Radiance command plan
    — but `channel_scenes` and `points` are required for BOTH the live and emit paths (the plan is built
    from the actual per-channel scene transport, not from point_xyz/view_vec alone).
    points: inline [x,y,z,dx,dy,dz] rows OR a .pts path (a list is materialized to a .pts under work_dir,
    same contract as run_annual).
    physical_sky (opt-in): shape the enhanced reconstruction with the physical EPW-derived per-timestep sky/sun spectra instead of templates; default off.
    engine: spectrl2 (default) | smarts (requires SMARTSPATH); only used when physical_sky=True.

    Site location is read from the EPW itself (converted to DAYSIM convention by the Daysim adapter);
    the tool takes no caller-supplied coordinates, so wrong-convention coordinates cannot silently
    corrupt the solar geometry.
    """
    wd = await resolve_work_dir(ctx, work_dir)
    if run:
        # Elicit confirmation before the long run (scope = timesteps x channels x DDS transport).
        proceed = await confirm_run(ctx, _LONG_RUN_QUESTIONS["annual_nvrd"])
        if isinstance(proceed, InputRequiredResult):
            return proceed  # the question itself: the client answers by calling again
        if proceed is False:
            run = False  # user declined -> fall through to emit
    # Engine only matters on the physical_sky path; resolve lazily so engine="smarts" without a
    # binary does not raise on a call that never uses it.
    engine_obj = _resolve_engine(engine) if physical_sky else None
    # Match run_annual: accept inline [x,y,z,dx,dy,dz] rows OR a .pts path
    # (the DDS transport streams a path), materializing a list to a .pts under work_dir.
    if points is not None:
        points = _ensure_points_path(points, wd, name="nvrd_points.pts")
    return await _offload(
        _annual_nvrd, point_xyz=point_xyz, view_vec=view_vec, timestep_min=timestep_min,
        reconstruction=reconstruction, sky_reconstruction=sky_reconstruction,
        sun_spectral=sun_spectral, sky_cct=sky_cct, epw=epw,
        channel_scenes=channel_scenes, points=points, channel_type=channel_type,
        rad_params=rad_params, work_dir=wd, run=run, physical_sky=physical_sky,
        engine=engine_obj)


# ---- Studio (hcl_core.fixtures + hcl_mcp.studio: sizing + resumable brief/report) ----
def recommend_fixtures(length_m: float, width_m: float, height_m: float, mount_height_m: float,
                       workplane_height_m: float = 0.8, eye_height_m: float = 1.2,
                       rho_ceiling: float = 0.7, rho_wall: float = 0.5, rho_floor: float = 0.2,
                       maintenance_factor: float = 0.8, target_em_lux: float = 500.0,
                       target_mel_edi: float | None = None, mel_edi_daylight: float = 0.0,
                       vertical_horizontal_ratio: float = 0.4, distribution: str = "direct",
                       target_efficacy_lm_w: float = 120.0) -> dict:
    """First-principles HCL fixture sizing: lumen-method visual flux reconciled with a CIE S 026
    mel-DER circadian solve. Returns flux, count, layout, CCT band, energy, and explicit caveats.
    distribution: direct|direct_indirect|indirect. Deterministic - always runs. See operating-guide.md workflow F."""
    return _recommend_fixtures(
        length_m=length_m, width_m=width_m, height_m=height_m, mount_height_m=mount_height_m,
        workplane_height_m=workplane_height_m, eye_height_m=eye_height_m,
        rho_ceiling=rho_ceiling, rho_wall=rho_wall, rho_floor=rho_floor,
        maintenance_factor=maintenance_factor, target_em_lux=target_em_lux,
        target_mel_edi=target_mel_edi, mel_edi_daylight=mel_edi_daylight,
        vertical_horizontal_ratio=vertical_horizontal_ratio, distribution=distribution,
        target_efficacy_lm_w=target_efficacy_lm_w)


async def save_brief(study: str, brief: dict, work_dir: str | None = None,
                     ctx: Context | None = None) -> dict:
    """Persist (shallow-merge) a study brief to <work_dir>/<study>/brief.json. Call after each phase."""
    base = await resolve_work_dir(ctx, work_dir)
    path = _save_brief(base, study, brief)
    return {"saved": True, "path": path}


async def load_brief(study: str, work_dir: str | None = None, ctx: Context | None = None) -> dict:
    """Load a study brief (empty skeleton if none). Call at journey start to resume where you left off."""
    base = await resolve_work_dir(ctx, work_dir)
    return _load_brief(base, study)


async def build_report(study: str, brief: dict, work_dir: str | None = None,
                       ctx: Context | None = None) -> dict:
    """Render a study brief to <work_dir>/<study>/report.{md,html}: goal recap, fixture spec,
    target-vs-achieved table with pass/fail, circadian↔glare cross-check, compliance. Always runs."""
    base = await resolve_work_dir(ctx, work_dir)
    return _build_report(base, study, brief)


def _build_modifier(cloud_variant: str | None, ccm_coeffs: str | None):
    """Build a Sedes1Modifier from tool-facing (cloud_variant, ccm_coeffs) args, or None for pipeline default.

    cloud_variant: None/'reanchored' (pipeline default, byte-identical) | 'verbatim' | 'seed' | 'local'.
    ccm_coeffs: path to a fitted CCM CSV (required, and only meaningful, for cloud_variant='local').
    """
    if cloud_variant in (None, "reanchored"):
        return None                                    # pipeline default = Sedes1Modifier()
    if cloud_variant == "local":
        if not ccm_coeffs:
            raise ValueError("cloud_variant='local' requires ccm_coeffs (path to a fitted CSV)")
        try:
            coeffs, sigma = sedes1_fit.load_ccm_csv(ccm_coeffs)
        except (FileNotFoundError, ValueError, IndexError, OSError) as e:
            raise ValueError(
                f"cloud_variant='local' could not load ccm_coeffs {ccm_coeffs!r}: {e}"
            ) from e
        return Sedes1Modifier(variant="local", coeffs=coeffs, sigma=sigma, source=ccm_coeffs)
    return Sedes1Modifier(variant=cloud_variant)        # verbatim | seed


def atmosphere_from_epw(epw: str, month: int, day: int, hour: int, *,
                        ozone_mode: str | None = None, aerosol_g: float | None = None,
                        aod_anchor_nm: float | None = None) -> dict:
    """Derived atmospheric state (AOD, PWV, ozone, pressure, albedo, aerosol_g + provenance).

    Opt-in refinements (defaults reproduce prior output): ozone_mode='climatology' computes ozone
    from the EPW LOCATION lat/lon + date (van Heuklon 1979); aerosol_g overrides the 0.65 asymmetry;
    aod_anchor_nm converts a declared-wavelength AOD (e.g. 550) to tau500 via the Angstrom exponent.
    """
    rec = _record_from_epw(epw, month, day, hour, ozone_mode=ozone_mode,
                           aerosol_g=aerosol_g, aod_anchor_nm=aod_anchor_nm)
    return _asdict(rec.atmosphere)


def spectral_sky_from_epw(epw: str, month: int, day: int, hour: int,
                          overrides: dict | None = None,
                          surface_tilt_deg: float | None = None,
                          engine: str = "spectrl2",
                          spectral_albedo: list | None = None, *,
                          ozone_mode: str | None = None, aerosol_g: float | None = None,
                          aod_anchor_nm: float | None = None,
                          smarts_aerosol: str | None = None,
                          cloud_variant: str | None = None,
                          ccm_coeffs: str | None = None) -> dict:
    """Physical spectral sky (1nm direct + sky-diffuse) reconstructed from an EPW hour.

    Returns the canonical record as a dict. If surface_tilt_deg is given, also returns the spectral
    ground-glow term for that receiver tilt. spectral_albedo (len 401, 380-780nm @1nm) overrides the
    default gray albedo — pass import_geometry(...)["ground_albedo"] to couple scene ground reflectance
    to the sky ground-glow term. engine: spectrl2 (default) | smarts (requires SMARTSPATH).

    Opt-in refinements (defaults reproduce prior output): ozone_mode='climatology' computes ozone
    from the EPW LOCATION lat/lon + date (van Heuklon 1979); aerosol_g overrides the 0.65 asymmetry;
    aod_anchor_nm converts a declared-wavelength AOD (e.g. 550) to tau500 via the Angstrom exponent.
    smarts_aerosol (engine="smarts" only): None/"rural" (default) or "user" to make the Ångström
    exponent + asymmetry factor settable via the SMARTS Card 8 USER aerosol model.
    cloud_variant: which SEDES1 cloud CCM to apply to the sky-diffuse spectrum — 'reanchored' (default,
    byte-identical to omitting this arg) | 'verbatim' (faithful Fig.11 CCM) | 'seed' (legacy eyeballed
    9-anchor seed) | 'local' (your own locally-fitted CCM, requires ccm_coeffs).
    ccm_coeffs: path to a fitted CCM CSV (from sedes1_fit) — required when cloud_variant='local'.
    """
    if spectral_albedo is not None and len(spectral_albedo) != 401:
        raise ValueError("spectral_albedo must have length 401 (380-780 nm @1 nm)")
    modifier = _build_modifier(cloud_variant, ccm_coeffs)
    rec = _record_from_epw(epw, month, day, hour, overrides=overrides,
                           engine=_resolve_engine(engine, smarts_aerosol=smarts_aerosol),
                           ozone_mode=ozone_mode,
                           aerosol_g=aerosol_g, aod_anchor_nm=aod_anchor_nm,
                           modifier=modifier)
    out = _record_to_dict(rec)
    if surface_tilt_deg is not None:
        if spectral_albedo is not None:
            albedo = [min(1.0, max(0.0, float(a))) for a in spectral_albedo]
        else:
            albedo = [rec.atmosphere.albedo] * 401
        out["ground"] = _ground_for_receiver(rec, surface_tilt_deg=surface_tilt_deg,
                                             spectral_albedo=albedo)
    return out


async def spectral_epw(epw: str, forms: list | None = None, hours: list | None = None,
                       work_dir: str | None = None, engine: str = "spectrl2",
                       ctx: Context | None = None, *,
                       ozone_mode: str | None = None, aerosol_g: float | None = None,
                       aod_anchor_nm: float | None = None,
                       smarts_aerosol: str | None = None,
                       cloud_variant: str | None = None,
                       ccm_coeffs: str | None = None) -> dict:
    """Emit spectral-sky artifacts from an EPW over the year (or `hours`). LONG-RUNNING for a full year.

    forms ⊆ {spd_set, band_matrix, spectral_wea, sidecar} (default all). Writes into work_dir and
    returns {files: {form: path}, n_records}. `hours` is a list of [month, day, hour] to subset.
    engine: spectrl2 (default) | smarts (requires SMARTSPATH).

    Opt-in refinements (defaults reproduce prior output): ozone_mode='climatology' computes ozone
    from the EPW LOCATION lat/lon + date (van Heuklon 1979); aerosol_g overrides the 0.65 asymmetry;
    aod_anchor_nm converts a declared-wavelength AOD (e.g. 550) to tau500 via the Angstrom exponent.
    smarts_aerosol (engine="smarts" only): None/"rural" (default) or "user" to make the Ångström
    exponent + asymmetry factor settable via the SMARTS Card 8 USER aerosol model.
    cloud_variant: which SEDES1 cloud CCM to apply to the sky-diffuse spectrum — 'reanchored' (default,
    byte-identical to omitting this arg) | 'verbatim' (faithful Fig.11 CCM) | 'seed' (legacy eyeballed
    9-anchor seed) | 'local' (your own locally-fitted CCM, requires ccm_coeffs).
    ccm_coeffs: path to a fitted CCM CSV (from sedes1_fit) — required when cloud_variant='local'.
    """
    wd = await resolve_work_dir(ctx, work_dir)
    os.makedirs(wd, exist_ok=True)
    forms = forms or ["spd_set", "band_matrix", "spectral_wea", "sidecar"]
    hset = [tuple(h) for h in hours] if hours else None
    modifier = _build_modifier(cloud_variant, ccm_coeffs)
    def compute_and_write():
        recs = _annual_records(epw, hours=hset,
                               engine=_resolve_engine(engine, smarts_aerosol=smarts_aerosol),
                               ozone_mode=ozone_mode, aerosol_g=aerosol_g,
                               aod_anchor_nm=aod_anchor_nm,
                               modifier=modifier)

        def _write(name, text):
            jobcontrol.raise_if_cancelled()   # a cancelled call must not leave late files behind
            p = os.path.join(wd, name)
            with open(p, "w") as fh:        # context-managed: flush/close deterministically
                fh.write(text)
            return p

        written = {}
        if "spd_set" in forms:
            # one combined CSV: blocks per record separated by a timestamp comment
            blocks = [f"# {r.timestamp[0]} {r.timestamp[1]} {r.timestamp[2]}\n" + _emit_spd_set(r) for r in recs]
            written["spd_set"] = _write("spectral_spd_set.csv", "".join(blocks))
        if "band_matrix" in forms:
            written["band_matrix"] = _write("spectral_band_matrix.txt", _emit_band_matrix(recs))
        if "spectral_wea" in forms:
            written["spectral_wea"] = _write("spectral_sky.wea", _emit_spectral_wea(recs))
        if "sidecar" in forms:
            written["sidecar"] = _write("spectral_epw_sidecar.csv", _emit_sidecar(recs))
        return {"files": written, "n_records": len(recs)}

    # A full year is 8760 spectra and four files: minutes of pure Python, so off the loop too.
    return await _offload(compute_and_write)


async def spectral_sky_native(epw: str, mf: int = 1, mode: str = "all",
                              work_dir: str | None = None, run: bool = True,
                              timeout: float | None = None, ctx: Context | None = None) -> dict:
    """Native Radiance 6.x spectral sky from an EPW via gensdaymtx (20-band W/sr/m² matrix).

    mode: all | sun (-d) | sky (-s). Degrades to emitting the gensdaymtx + rcomb command plan when
    Radiance 6.x isn't installed. The melanopic collapse is `rcomb -c M`.

    `timeout` caps the gensdaymtx subprocess in seconds (default None = no cap). gensdaymtx ALWAYS
    processes every EPW hour. A full 8760-hour year at mf=1 is fast (~12 s on Radiance 6.1a), but cost
    grows steeply with the Reinhart subdivision mf (minutes at mf>=4); on expiry the tool returns
    {ok: False, timed_out: True} rather than raising. Trim the EPW, or raise mf only as needed.
    """
    wd = await resolve_work_dir(ctx, work_dir)
    return await _offload(_run_gensdaymtx, epw, wd, mf=mf, mode=mode, run=run, timeout=timeout)


async def sensors(action: str, name: str | None = None, points: list | None = None,
                  grid: dict | None = None, overwrite: bool = False,
                  work_dir: str | None = None, ctx: Context | None = None) -> dict:
    """Manage named, persistent daylight sensor sets (reused across annual_daylight / daylight_factor
    / daylight_savings via sensor_set='name').

    action: 'create' | 'list' | 'get' | 'delete'.
      create: name + (points=[[x,y,z,dx,dy,dz],...] OR grid={interior:[xmin,xmax,ymin,ymax],
              floor_z, workplane_h?, max_spacing?}); overwrite=True to replace an existing set.
      list:   all saved sets (name, path, count, source).
      get:    name -> the set's points + .pts path.
      delete: name -> remove the set.
    """
    wd = await resolve_work_dir(ctx, work_dir)
    if action == "create":
        if not name:
            raise ValueError("create requires name=")
        return _create_sensor_set(wd, name, points=points, grid=grid, overwrite=overwrite)
    if action == "list":
        return {"sensor_sets": _list_sensor_sets(wd)}
    if action == "get":
        if not name:
            raise ValueError("get requires name=")
        return _get_sensor_set(wd, name)
    if action == "delete":
        if not name:
            raise ValueError("delete requires name=")
        return _delete_sensor_set(wd, name)
    raise ValueError(f"action must be create|list|get|delete, got {action!r}")


def _attach(tool, args, result):
    """Attach advisories to a dict result. Returns a new dict; never mutates the input.

    Non-dict results pass through untouched: circadian_metrics returns a LIST of
    per-point dicts for multi-point input, and wrapping that would change the tool's
    published contract.
    """
    if not isinstance(result, dict):
        return result
    items = _advise(tool, args, result)
    if not items:
        return result
    return {**result, "advisories": items}


def _with_advisories(fn):
    """Wrap a tool for registration: successful dict results carry advisories, and every
    async tool call runs as one `hcl_core.jobcontrol` job.

    The job is what makes a call stoppable and observable. Whatever the tool hands to
    `_offload` runs inside it, so each command-sequence step is forwarded to the client as
    progress, and leaving the job -- normally, on an error, or because the client cancelled,
    timed out or went away -- kills the process a worker thread is still waiting on.

    Branches on iscoroutinefunction: 27 of the registered tools are async and 20 are sync
    (the sync ones are pure computation and start no process), and returning the wrong
    wrapper type changes how FastMCP invokes them. functools.wraps keeps __name__, __doc__
    and __wrapped__, which is what preserves the published JSON schema -- guarded by
    tests/test_tool_registration.py.

    Only successful returns are wrapped; an exception propagates so FastMCP still marks
    the call is_error.
    """
    if inspect.iscoroutinefunction(fn):
        @functools.wraps(fn)
        async def _async_wrapper(*a, **kw):
            with jobcontrol.job(on_step=_progress_reporter(kw.get("ctx"))):
                result = await fn(*a, **kw)
            return _attach(fn.__name__, kw, result)
        return _async_wrapper

    @functools.wraps(fn)
    def _sync_wrapper(*a, **kw):
        return _attach(fn.__name__, kw, fn(*a, **kw))
    return _sync_wrapper


# GAP-5: convert_eml_medi is intentionally NOT registered — EML<->EDI is folded into spectral_metrics
# (spec 7.1 row 5).
_TOOL_FUNCS = (spd_to_channels, glass_transmissivity, write_material, circadian_metrics,
               alpha_opic, validate, spectral_metrics, compliance, presets,
               colored_sky, colored_luminaire, reference, run_grid, run_image, import_geometry, check_geometry, radiance_status,
               weather, run_annual, nvrd,
               ies_analyze, ies_to_radiance, glare_ugr,
               lighting_controls, daylight_savings, annual_daylight, lm83_daylight,
               daylight_factor, sensors,
               daysim_status, build_daysim, generate_subhourly_wea,
               reconstruct_spectrum, annual_nvrd, recommend_fixtures,
               atmosphere_from_epw, spectral_sky_from_epw, spectral_epw, spectral_sky_native,
               save_brief, load_brief, build_report, workplane_grid, observer_points,
               photosensors, preview_scene, quality_presets)

# MCP-11: verb_object aliases for clearer AI tool selection, registered ALONGSIDE the terse
# names (non-breaking — the originals above are preserved). FastMCP allows registering the same
# callable under a second name via mcp.tool(fn, name="..."), so no wrappers are needed.
_TOOL_ALIASES = (
    ("get_reference", reference),
    ("list_presets", presets),
    ("import_weather", weather),
    ("run_validation", validate),
)

# The question put to the user before a run that takes minutes to hours. One text per tool, used
# both by the tool itself (an inline call) and by `_ConfirmBeforeTask` (a call about to become a
# background task).
_LONG_RUN_QUESTIONS = {
    "annual_daylight": (
        "annual_daylight runs an 8760-hour 2-phase DDS simulation plus a direct-only ASE "
        "pass (minutes-to-hours). Proceed?"),
    "lm83_daylight": (
        "lm83_daylight traces a three-phase V and D matrix per window group, then "
        "runs an 8760-hour multiply per shading state plus a zero-bounce sun pass "
        "(minutes-to-hours). Proceed?"),
    "daylight_savings": (
        "Annual daylight_savings runs an 8760-hour 2-phase DDS simulation (minutes-to-hours). "
        "Proceed?"),
    "annual_nvrd": (
        "annual_nvrd runs Daysim sub-hourly generation + a full 2-phase DDS annual transport "
        "(potentially long). Proceed? (set run=false to only emit the command plan)"),
}


_AS_BOOL = TypeAdapter(bool)


def _would_simulate(tool, arguments):
    """Would this call start the long simulation? Mirrors each tool's own condition for asking;
    absent arguments take the tool's defaults (run=True, daylight_savings mode="point_in_time").

    `run` is read the way the tool's signature reads it. Clients that do not type their
    arguments send the string "false", which the tool accepts as False; a truthiness test here
    would ask about a dry run. A value the tool would reject is not asked about either: the
    call is about to fail on its own.
    """
    try:
        run = _AS_BOOL.validate_python(arguments.get("run", True))
    except ValidationError:
        return False
    if not run:
        return False
    return tool != "daylight_savings" or arguments.get("mode", "point_in_time") == "annual"


class _ConfirmBeforeTask(Middleware):
    """Settle the long-run question in the foreground, before a call becomes a background task.

    A task body runs without a request or a session: it cannot see which capabilities its
    client declared, so it cannot tell a client that can be asked from one that cannot, and
    asking the second kind would leave the task waiting for input for ever. The tasks extension
    says the same thing from the other side: resolve input requests before answering with a
    task. Middleware is the place: it wraps every call and runs ahead of task creation.

    Only calls that are about to become tasks are handled here (MCP 2026-07-28, client declared
    the extension, tool is one of the four that ask). Every other call asks from inside the
    tool, as before. A yes creates the task; a no creates it with run=False, so the task
    returns the command plan; the task body itself then asks nothing.

    One difference from the inline path: the question comes BEFORE the tool has checked its
    other arguments (a weights/points mismatch, a missing file), because those checks live in
    the tool body and the body runs in the task. A user can therefore say yes to a call that
    then fails at once. Nothing is simulated in that case.
    """

    async def on_call_tool(self, context, call_next):
        ctx = context.fastmcp_context
        name = context.message.name
        arguments = context.message.arguments or {}
        if (name not in _LONG_RUN_QUESTIONS or ctx is None or not is_modern_protocol(ctx)
                or ctx.client_extension_settings(_TASKS_EXTENSION) is None
                or not _would_simulate(name, arguments)):
            return await call_next(context)
        answer = await confirm_run(ctx, _LONG_RUN_QUESTIONS[name])
        if isinstance(answer, InputRequiredResult):
            return InputRequiredToolResult(input_required=answer)
        if answer is False:
            declined = context.message.model_copy(update={"arguments": {**arguments, "run": False}})
            context = context.copy(message=declined)
        return await call_next(context)


mcp.add_middleware(_ConfirmBeforeTask())

# The tools that run for minutes to hours. Only these are offered as background tasks: a task
# costs the client a polling round trip, which is wasted on a call that returns in a second.
_TASK_TOOLS = (run_annual, annual_daylight, lm83_daylight, daylight_savings, annual_nvrd,
               spectral_epw, spectral_sky_native, build_daysim)

for _tool in _TOOL_FUNCS:
    mcp.tool(_with_advisories(_tool), task=_tool in _TASK_TOOLS)

for _alias_name, _alias_fn in _TOOL_ALIASES:
    mcp.tool(_with_advisories(_alias_fn), name=_alias_name)

_resources.register_resources(mcp)

for _prompt in (spd_to_circadian, hcl_grid_study, fisheye_eye_analysis, annual_circadian_dose,
                explain_concept, electric_lighting_design, annual_alertness, hcl_studio,
                import_obj_room, spectral_sky_from_epw_prompt, place_sensors,
                annual_daylight_study, visualize_scene):
    mcp.prompt(_prompt)

def _stop_simulations_when_signalled():
    """Take running simulations down with the server when it is terminated or hung up.

    An MCP client stops a stdio server by closing its stdin and then, if it has not gone,
    by signal. Python's default action for SIGTERM and SIGHUP is to die on the spot: no
    cancellation reaches the tool call, no exit hook runs. Each command runs in its own process
    group (so that cancelling a call can kill what the command forked), which also means the
    signal that kills the server never reaches it. Without this handler a client that closes
    its window leaves Radiance running for hours with no owner.

    The handler kills the groups outright -- the server may have no time for a grace period --
    then lets the signal do what it would have done. SIGINT is left alone: it becomes
    KeyboardInterrupt, which unwinds the tool call and the exit hook normally. SIGKILL cannot be
    handled by anyone.
    """
    def handler(signum, frame):
        jobcontrol.terminate_all(force=True)
        signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)

    for name in ("SIGTERM", "SIGHUP"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), handler)


def main():
    _stop_simulations_when_signalled()
    mcp.run()

if __name__ == "__main__":
    main()
