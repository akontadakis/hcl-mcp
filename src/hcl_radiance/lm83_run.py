"""LM-83 orchestration: geometry -> groups -> matrices -> states -> metrics.

  1. Extract glass faces; group them (2.2.6) or take the caller's declaration.
  2. Write one glow sender per group; ray-trace V and D ONCE per group.
  3. Synthesise a T matrix per state: clear glazing open, 2.2.7's blind closed.
  4. Multiply for the open state and each closure step -- N+1 states, not 2^N.
  5. Run the zero-bounce sun pass PER GROUP, which feeds ASE (3.2.6) and the trigger
     (2.2.6). Per-group matters: with one whole-model series shared between groups,
     closing any group cancels beam that another group admitted, so the criterion is
     satisfied with the wrong blind down.

`plan_lm83` builds the step list; `run_lm83` executes it and computes the metrics.
"""
import os

from hcl_core.klems import (clear_glazing_tmatrix, lm83_default_blind,
                            uniform_diffuse_tmatrix, write_klems_xml)
from hcl_core.lm83 import (group_windows, lm83_metrics, lm83_schedule, resolve_states,
                           select_illuminance, validate_analysis_areas)
from hcl_radiance.aperture import glass_faces, write_window_sender
from hcl_radiance.discover import radiance_status
from hcl_radiance.lm83_sun import build_sun_pass_steps, parse_lux_matrix
from hcl_radiance.runner import _render, run_sequence as _run_sequence
from hcl_radiance.threephase import build_threephase_steps, multiply_steps


def _glazing_tvis(material_map, default=0.7):
    """The first declared glass tvis. Used UNDEPRECIATED -- see MODEL_INPUTS_DEPARTURE."""
    for spec in material_map.values():
        if isinstance(spec, dict) and spec.get("type") == "glass":
            return float(spec.get("tvis", default))
    return default


def _group_geometry(faces, name, work_dir):
    """A .rad holding only this group's glazing, for its own direct-sun pass.

    The sun pass needs to know how much beam THIS group admits, so every other group's
    aperture must be absent from its octree. Written as an opaque-free surface: the
    surrounding walls come from the scene geometry, and only this group's opening lets
    sun through.
    """
    path = os.path.abspath(os.path.join(work_dir, f"{name}_glazing.rad"))
    lines = []
    for i, face in enumerate(faces):
        reals = " ".join(f"{c:g}" for v in face["verts"] for c in v)
        lines += [f"void glass {name}_g", "0", "0", "3 1 1 1", "",
                  f"{name}_g polygon {name}_g.{i}", "0", "0",
                  f"{len(face['verts']) * 3} {reals}", ""]
    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    return path


def plan_lm83(scene, parsed, material_map, wea, points, n_pts, *, work_dir,
              declared_groups=None, blind=None, v_params=None, d_params=None,
              interior_point=None):
    """Plan the full LM-83 workflow. Returns the step list and every state's output."""
    faces = glass_faces(parsed, material_map)
    if not faces:
        return {"error": (
            "no glass faces in this model, so no window group could be formed. LM-83 "
            "2.2.6 requires every exterior window to carry an operable blind; declare "
            "the glazing group in material_map with type 'glass'.")}

    groups = group_windows(faces, declared=declared_groups)
    by_index = {f["index"]: f for f in faces}
    senders, group_faces = {}, {}
    for group in groups:
        picked = [by_index[i] for i in group["face_indices"]]
        group_faces[group["name"]] = picked
        senders[group["name"]] = write_window_sender(picked, group["name"], work_dir,
                                                     interior_point=interior_point)

    steps, outputs = build_threephase_steps(scene, senders, wea, points, n_pts,
                                            work_dir=work_dir, v_params=v_params,
                                            d_params=d_params)

    open_xml = write_klems_xml(clear_glazing_tmatrix(_glazing_tvis(material_map)),
                               os.path.join(work_dir, "t_open.xml"), name="glazing_open")
    spec = dict(blind or {})
    if spec.get("bsdf"):
        closed_xml, blind_source, beam_pass = spec["bsdf"], "supplied_bsdf", 0.0
    else:
        d = lm83_default_blind(spec.get("shade_type"), vlt=spec.get("vlt"),
                               openness=spec.get("openness"),
                               reflectance=spec.get("reflectance"))
        closed_xml = write_klems_xml(
            uniform_diffuse_tmatrix(d["diffuse_vlt"], specular=d["specular"]),
            os.path.join(work_dir, "t_blind.xml"), name=d["source"])
        blind_source = d["source"]
        total = d["diffuse_vlt"] + d["specular"]
        beam_pass = (d["specular"] / total) if total > 0 else 0.0

    # N+1 states: all open, then close one more group per step in a fixed nested order.
    order = [g["name"] for g in groups]
    states = [frozenset()] + [frozenset(order[:k + 1]) for k in range(len(order))]
    state_ill = {}
    for state in states:
        tag = "open" if not state else "closed_" + "_".join(sorted(state))
        t_map = {name: (closed_xml if name in state else open_xml) for name in senders}
        mul, ill = multiply_steps(outputs, t_map, tag)
        steps.extend(mul)
        state_ill[state] = ill

    # One zero-bounce pass per group, each seeing only that group's glazing, plus one
    # whole-model pass for ASE. Sharing a single series across groups would let a
    # closure cancel beam it never admitted.
    sun_ill = {}
    for name, picked in group_faces.items():
        group_scene = dict(scene)
        group_scene["exterior"] = [*(scene.get("exterior") or []),
                                   _group_geometry(picked, name, work_dir)]
        sun_steps, ill = build_sun_pass_steps(group_scene, wea, points, n_pts,
                                              work_dir=work_dir, tag=f"sun_{name}")
        steps.extend(sun_steps)
        sun_ill[name] = ill
    all_glazing = [f for picked in group_faces.values() for f in picked]
    total_scene = dict(scene)
    total_scene["exterior"] = [*(scene.get("exterior") or []),
                              _group_geometry(all_glazing, "all", work_dir)]
    sun_steps, sun_total = build_sun_pass_steps(total_scene, wea, points, n_pts,
                                               work_dir=work_dir, tag="sun_all")
    steps.extend(sun_steps)

    return {"window_groups": groups, "blind_source": blind_source,
            "beam_pass_fraction": {name: beam_pass for name in senders},
            "states": states, "steps": steps, "state_ill": state_ill,
            "sun_ill": sun_ill, "sun_total_ill": sun_total,
            "commands": [_render(s) for s in steps]}


def _read_lux(path, work_dir):
    """Read one produced .ill into [n_points][n_timesteps] lux."""
    with open(os.path.join(work_dir, path)) as fh:
        return parse_lux_matrix(fh.read())


def run_lm83(scene, parsed, material_map, wea, points, n_pts, *, work_dir, areas,
             point_rows, latitude=None, declared_groups=None, blind=None,
             declared_no_blinds=False, run=True, v_params=None, d_params=None):
    """Plan, run, and compute the LM-83 metrics.

    This is where the policy layer is applied: the per-group zero-bounce sun matrices
    drive resolve_states, which selects among the per-state illuminance matrices, which
    feeds lm83_metrics.

    `areas` are 2.2.6 trigger areas (by facade, each <= 10,000 sf). `point_rows` are the
    sensor coordinates -- grid conditions are MEASURED from them, so a .pts path will not
    do.
    """
    try:
        validate_analysis_areas(areas)
    except ValueError as exc:
        return {"ran": False, "reason": str(exc)}

    interior = None
    if point_rows:
        n = float(len(point_rows))
        interior = tuple(sum(float(p[i]) for p in point_rows) / n for i in range(3))

    plan = plan_lm83(scene, parsed, material_map, wea, points, n_pts,
                     work_dir=work_dir, declared_groups=declared_groups, blind=blind,
                     v_params=v_params, d_params=d_params, interior_point=interior)
    if "error" in plan:
        return {"ran": False, "reason": plan["error"]}

    base = {"window_groups": plan["window_groups"], "blind_source": plan["blind_source"],
            "states_simulated": [sorted(s) for s in plan["states"]],
            "commands": plan["commands"]}
    if not run:
        # A reason is not decoration: every other run-or-emit path in this codebase pairs
        # ran:False with one, and a bare command list leaves a caller unable to tell a
        # deliberate dry run from a missing Radiance install or a refused elicitation.
        return {"ran": False, "reason": "run=False: emitting the command plan without "
                                        "executing it.", **base}

    available = bool(radiance_status().get("bin_dir"))
    res = _run_sequence(plan["steps"], work_dir, available)
    if not res.get("ran"):
        return {"ran": False, "reason": res.get("reason"), **base}
    if res.get("error") or res.get("returncode"):
        return {"ran": True, "error": res.get("error"),
                "failed_step": res.get("failed_step"), **base}

    sun_total = _read_lux(plan["sun_total_ill"], work_dir)
    sun_by_group = {name: _read_lux(ill, work_dir)
                    for name, ill in plan["sun_ill"].items()}
    state_matrices = {state: _read_lux(path, work_dir)
                      for state, path in plan["state_ill"].items()}
    n_ts = len(sun_total[0]) if sun_total else 0
    occupancy = lm83_schedule(n_ts)

    states = resolve_states(plan["window_groups"], sun_by_group, sun_total, occupancy,
                            areas, beam_pass_fraction=plan["beam_pass_fraction"])
    operated = select_illuminance(state_matrices, states)
    metrics = lm83_metrics(operated, sun_total, occupancy,
                           groups=plan["window_groups"], points=point_rows, areas=areas,
                           blind_source=plan["blind_source"], latitude=latitude,
                           no_blind_lux=state_matrices.get(frozenset()),
                           declared_no_blinds=declared_no_blinds)
    return {"ran": True, "metrics": metrics,
            "blind_hours": sum(1 for s in states if s), **base}
