# inputs/sensors — your sensor / eye points

> **Drop-and-run (optional):** copy a `<name>.pts` here and it's auto-discovered by extension (no
> JSON editing). This folder is **optional** — with no `.pts`, the tester uses
> `import_geometry(derive_sensors=true)` to generate work-plane + eye-level points from your room.
> If both a sample and your file are present, yours wins. (Rules: `../active_inputs.json` → `_resolution`.)

> **⚠️ NAME YOUR FILE BY ROLE — this folder holds three different kinds of sensor, not one.**
> The extension is shared but the sensors are **not** interchangeable:
>
> | Role | Filename must match | What it is | Ships as |
> |---|---|---|---|
> | `points` | `grid` · `workplane` · `wp` · `task` | horizontal work-plane grid, up-facing `0 0 1` at `workplane_h` | `office_room_grid.pts` (45 pts) |
> | `points_observer` | `observer` · `eye` · `view` · `occupant` | **vertical** eye sensors, gaze toward glazing | `observer_1.pts`, `observer_2.pts` |
> | `points_photosensor` | `sensor` · `photo` · `dimming` · `zone` | daylight-dimming reference sensors | `sensor_1.pts`, `sensor_2.pts` |
>
> Substituting one for another fails **silently**, because each is a perfectly valid `.pts`. A 1-point
> eye file used as the work-plane grid makes **sDA/ASE degenerate** (one point can only score 0% or 100%),
> averages **DF over the wrong plane**, and leaves **EN 12464-1 uniformity undefined**. Roles are matched
> before — and always beat — alphabetical order. If a role has no match it is **regenerated**, never
> borrowed from another role.

## What to drop here
A Radiance points file (`.pts`): one sensor per line as `x y z dx dy dz` (position + gaze direction).
For circadian (mel-EDI) work the meaningful sensor is **vertical at the eye**, oriented toward the glazing.

## You usually don't need to author this
Four routes generate sensor points from the OBJ automatically:

1. `import_geometry(derive_sensors=True)` — returns `grid_points` (work-plane, up-facing) and
   `observer_sets` (seated **1.2 m** + standing **1.6 m**, each with DGP `glare_views`). Tunable
   via `eye_heights`, `workplane_h`, `spacing`.
2. `workplane_grid` — dedicated EN 12464-1 working-plane grid. Detects interior extent, applies a
   border offset, and lays a uniform grid at `workplane_h` (default 0.8 m). Feed the resulting `.pts`
   (shipped as `office_room_grid.pts`) → `run_grid` for horizontal/task illuminance and EN 12464-1 compliance.
3. `observer_points` — workstation eye sensors. Pairs chair seats to display screens by object-name
   suffix; falls back to glazing centroid, a fixed azimuth, or sweep views. Returns `observers[]`
   with `eye`, `direction`, and ready-made `glare_views` fisheye strings for `glare_ugr`.
4. `photosensors` — daylight-dimming closed-loop sensors (methodology.md §3). Builds sidelighting
   zones from the glazing head height (`zone_rule='head_height'`) and places one horizontal sensor
   per zone at `sensor_fraction` (default 2/3) of the zone depth, centred on the facade. Feed
   `sensor_1.pts`/`sensor_2.pts` to `run_grid`/`run_annual` for daylight-linked dimming control logic.

The agent prefers auto-derived points because they match the imported scene's coordinate frame exactly.

## Shipped files

`.pts` files ship pre-generated (2026-07-05) from **`office_room.obj`** — the single-window, **south-facing**
model (`north_angle_deg 0`; the geometry is authored in the true-north frame with the window in the −Y
"South" wall). They are the output of the dedicated tools and can always be regenerated. **The other three
models (blinds / corner / corner+blinds) are not covered by these files** — derive their sensors on the fly
with `workplane_grid` / `observer_points` / `photosensors` (or `import_geometry(derive_sensors=true)`), which
read the OBJ + its `*_material_map.json` sidecar.

| File | Points | Tool that produced it | Feed to |
|------|--------|-----------------------|---------|
| `office_room_grid.pts` | 45 work-plane pts at z=0.8 m, up-facing (`0 0 1`) | `workplane_grid` | `run_grid` (horizontal/task lux, EN 12464-1) |
| `observer_1.pts` | `-1.7500 1.2000 1.2000 1.0000 0.0000 0.0000` (Chair_Seat_1↔Disp_Panel_1, gaze +X toward its screen) | `observer_points` | `run_grid`/`run_annual` (vertical mel-EDI), `glare_ugr` |
| `observer_2.pts` | `1.7500 -1.2000 1.2000 -1.0000 0.0000 0.0000` (Chair_Seat_2↔Disp_Panel_2, gaze −X toward its screen) | `observer_points` | `run_grid`/`run_annual` (vertical mel-EDI), `glare_ugr` |
| `sensor_1.pts` | primary daylight-dimming zone `0 −1.8467 0.8` (near the south facade), up-facing | `photosensors` | `run_grid`/`run_annual` (daylight-linked dimming) |
| `sensor_2.pts` | secondary zone `0 0.6333 0.8` (deeper in the room), up-facing | `photosensors` | `run_grid`/`run_annual` (daylight-linked dimming) |

`sensor_1.pts`/`sensor_2.pts` are **tool-produced**, not hand-made — regenerate them by calling
`photosensors(obj_path, sidecar=..., write_pts=...)` rather than hand-editing.

> **Previews no longer ship.** The `preview_all_plan.png` / `preview_all_3d.png` diagnostic overlays were
> removed. Regenerate a fresh overlay for any model with `preview_scene(render="all")` (it is a placement
> diagnostic, not a photometric render — that's `run_image`).

> **Auto-discovery ambiguity.** With several `.pts` files present, `active_inputs.json`'s
> `"points":"auto"` is ambiguous (the resolution rules expect a single match). The tools above
> always *regenerate* the files from the OBJ, so you can just call them. For explicit downstream
> runs, pass the path directly: `"points":"inputs/sensors/office_room_grid.pts"` for the work-plane grid, or
> `"points":"inputs/sensors/observer_1.pts"` for a workstation eye run — do **not** rely on
> auto-discovery when multiple `.pts` are present.

## Coordinate-frame caveat (if you hand-author)
The importer remaps a Y-up OBJ to Z-up (`-rx 90`), so a hand-made `.pts` must be in the **post-import Z-up,
metres** frame or it won't line up with the scene. When in doubt, use `derive_sensors=True`.

## How to bring your own
1. Copy your file here, e.g. `inputs/sensors/my_points.pts`.
2. Set `"points": "sensors/my_points.pts"` in `inputs/active_inputs.json`.
