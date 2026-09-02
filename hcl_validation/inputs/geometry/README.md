# inputs/geometry — your room model

## What to drop here
A **Wavefront `.obj`** of your space (exported from Rhino / Revit / SketchUp / Blender / etc.),
optionally its `.mtl`. This is the **only** geometry format the importer accepts (no inline mesh, no `.rad`).

## Drop-and-run (auto-discovery)
**Just copy your `<name>.obj` (and its `<name>.mtl`) into this folder — that's the only required step.** The
`hcl-mcp-tester` discovers it by extension (`active_inputs.json` is `"auto"`), and if you don't supply a matching
`material_map.json` it **auto-generates** one from your group names + the `.mtl` colors so the run completes
end-to-end (reflectances are *illustrative*, flagged in the report). If both a shipped sample and your file are
present, **yours wins**. Author a map yourself only when you want exact, measured materials (see "Pin the
materials" below).

## Good practice (helps the importer + the auto-map)
1. **One group per surface class.** Use `g <name>` and/or `usemtl <name>` lines to separate floor, walls,
   ceiling, each glazing, shading, etc. The importer prefers `usemtl` names; if none, it uses `g` names.
   Name them descriptively (`floor`, `ext_wall`, `glazing_south`, `shading_fin`…) — the auto-map infers each
   material `type` from these names.
2. **Vertex normals** (`vn`) are strongly recommended — without them you get a winding-orientation warning,
   and the auto-map uses them to guess the up axis (Y vs Z).
3. Know your **units** (`mm | cm | m | ft`) — the auto-map defaults to `m`; set it in your own map if different.
4. The OBJ carries **no color/reflectance** — it's assigned by the (auto or hand-written) `material_map`.

## Pin the materials exactly (optional)
To control reflectances precisely instead of the auto-generated guess:
1. Find your group names (the agent dry-runs automatically, or you can):
   `grep -E '^(g|usemtl) ' inputs/geometry/my_office.obj | sort -u`
2. Write `geometry/<name>_material_map.json` (named after your OBJ so it's discovered alongside it) so **every**
   group is a key. Each value is a library-name string or an inline dict:
   - opaque surface: `{"type":"plastic","refl":0.5}` (or `"floor"`, `"ground"`, `"context"`)
   - glazing: `{"type":"glass","tvis":0.65}`
   - luminaire marker: `{"type":"luminaire","ies":"/abs/path.ies","spd":"/abs/path.spd"}`
   - measured spectrum instead of a scalar: replace `refl`/`tvis` with `"spd":"/abs/path.spd"`
3. Set `units`, `up_axis`, `north_angle_deg`. **north_angle_deg matters** — the sky is built in a fixed
   +Y = true-north frame; omitting it is silently wrong for daylight.
4. An on-disk map whose keys **cover** the OBJ's groups always wins over auto-generation.

## Provided (four models — two comparison pairs)
All four are real Blender exports of the **same** furnished office (desks, chairs, monitors, 2×2 ceiling
luminaires). They come as **two ± blinds pairs** so any measured difference within a pair is the blinds'
effect, and the two pairs let you compare a **single window** vs a **wraparound corner window** — see
GUIDE.md **Part 4.5, Scenario S1**. As of 2026-07-05 the geometry is authored **directly in the true-north
frame** (so `north_angle_deg 0`), and the glazing/blind/frame group names encode the **compass facade**:

- `office_room.obj` (+ `.mtl`) — base room, single window in the **South** (`Room_Wall_South`, model −Y) wall
  → **south-facing** at `north_angle_deg 0`. Groups (8): `Rad_Floor_R020`, `Rad_Wall_R050`,
  `Rad_Ceiling_R080`, `Rad_Frame_R050`, `Rad_Furniture_R050`, `Rad_ScreenGlass_R004`, `Rad_Glazing_T073`,
  `Rad_Luminaire_L09`.
- `office_room_blinds.obj` (+ `.mtl`) — same room **plus a `Venetian_Blinds` surface** (`Rad_Blind_R070`).
  Groups (8): the seven surfaces above **minus `Rad_Luminaire_L09`** (this variant carries no luminaire
  group — the electric fixtures live only in the pre-authored `radiance/` scene) **plus `Rad_Blind_R070`**.
- `office_room_corner_window.obj` (+ `.mtl`) — corner-window variant: an L-shaped opening with glazing on
  **two** walls — **South** (−Y, `Rad_Glazing_South_T073`) and **West** (−X, `Rad_Glazing_West_T073`) — split
  head/jamb/sill frames (`Rad_Frame_South_R050`, `Rad_Frame_West_R050`) and a shared corner mullion
  (`Rad_Frame_Corner_R050`). Groups (11).
- `office_room_corner_window_blinds.obj` (+ `.mtl`) — the corner room **plus per-facade blinds
  `Rad_Blind_South_R070` and `Rad_Blind_West_R070`**. Groups (13).

**Pinned material maps ship beside every OBJ** — `office_room_material_map.json`,
`office_room_blinds_material_map.json`, `office_room_corner_window_material_map.json`, and
`office_room_corner_window_blinds_material_map.json` — so the **exact** intended values are used (an on-disk
map that covers the groups always wins over auto-generation): floor 0.20, wall 0.50, ceiling 0.80,
frame/furniture 0.50, glazing **glass tvis 0.73** (each facade separately for the corner), screen as a dark
opaque panel (refl 0.04), blind 0.70, and `Rad_Luminaire_L09` as a `type:luminaire` bound to the L09_neutral
fixture. They also pin the two things the auto-map would get wrong here:

1. **up axis = Z.** These are **Z-up** Blender exports (height on +Z, room ≈ 4.3 × 7.3 m, 3.4 m tall). Tell
   `import_geometry` `up_axis="Z"` — passing `Y` would rotate the room 90° (floor → wall).
2. **Glazing transmittance & the monitor screen.** The auto-map types groups by *name* and would set any
   `glass` group to a generic `tvis 0.65` and mis-read `Rad_ScreenGlass_R004` (a near-black monitor screen)
   as a transparent window. The pinned map fixes both.

**Orientation.** `north_angle_deg` is the clockwise azimuth the model's +Y axis points toward (0 = +Y is
true north). Because the rooms are modelled in the true-north frame, **all pinned maps set `north_angle_deg
0`**: the single window (in the −Y "South" wall) faces true **south**, and the corner faces **south + west**
(−Y and −X panes). The facade names in the group/material names are therefore the real compass facing at
`north_angle_deg 0` — change `north_angle_deg` only if you want to *rotate the whole building* off true
north (0 = as-modelled, 90 = rotate CW, …).

### Equivalent pre-authored Radiance scenes — `radiance/`
Each model also ships as a hand-authored Radiance scene under [`radiance/`](radiance/) for the **second**
geometry path (fed straight to `run_grid` / `run_annual`, no `import_geometry` needed):
`radiance/office_room.rad`, `office_room_blinds.rad`, `office_room_corner_window.rad`,
`office_room_corner_window_blinds.rad`, with modifiers in **`radiance/materials.rad`** (the single source of
truth for reflectances — includes the compass-named `Rad_Glazing_South/West_T073`, `Rad_Frame_*`,
`Rad_Blind_*`) and the four IES fixtures in **`radiance/luminaires_L09.rad`** (`L09_neutral.rad` +
`L09_neutral.dat`, keep them on `RAYPATH`). Build an octree with
`oconv materials.rad luminaires_L09.rad <model>.rad > <model>.oct`. Note `materials.rad` currently defines
`Rad_Luminaire_L09` as **non-emissive plastic 0.80** (per `Ke=0` in the `.mtl`); the IES emitters in
`luminaires_L09.rad` are the real light sources.

## `office_room_mm.obj` — the units regression fixture (added 2026-07-30)

`office_room_mm.obj` + `office_room_mm.mtl` + `office_room_mm_material_map.json` are the **same physical
room** as `office_room.obj` with every vertex ×1000 and the sidecar's `units` flipped to `"mm"`. It exists
for **TEST-PLAN W2.10** / **ADR-0002**: every tolerance in `check_geometry` is an absolute **metre**
(1 mm coincidence, 5 mm planarity, a 2 m² end-cap gate), so `units` is load-bearing, not cosmetic — it
resolves the scale that converts vertices *before any check runs*.

The regression it guards: `units`/`up_axis` were resolved from the sidecar and then **never passed on**
(dead parameters), so tolerances were compared against raw model units. That broke both ways — a real
0.5 mm z-fight in an mm model read as a 0.5-*unit* separation and was **missed**, while a legitimate
1 × 1 m end-cap read as 1e6 units² and raised a spurious `COINCIDENT_SURFACES` **error**, making
`import_geometry(strict=true)` refuse this very reference model merely re-expressed in mm.

**Invariant:** `check_geometry` on the mm twin must return a report **identical** to the metre model.
Verified 2026-07-30 — both report `ok:true`, `counts {error:0, warning:1, info:0}`, and the same single
`NOT_ENCLOSED` finding (20 boundary edges, `Rad_Glazing_T073` + `Rad_Luminaire_L09`). Regenerate with
vertices ×1000 if `office_room.obj` ever changes.

> **📌 The reference model is not silent.** `office_room.obj` legitimately reports **one** warning —
> `NOT_ENCLOSED`, because the glazing and luminaire groups are inset panels rather than sealed solids.
> That is an accepted property of the fixture, so `check_geometry` returns a `GEOMETRY_HEALTH_UNCLEAN`
> advisory (`warn`) on every import. Treat `ok:false`, a second finding, or a *different* code as the
> regression — not the warning itself.

> For **your own** OBJ (no pinned map), the tester auto-generates a complete map from the group names + `.mtl`
> colours — reflectances are plausible but glass/`up_axis`/orientation are heuristic guesses, so pin a map
> when you need exact daylight. (The importer hard-fails on a *partial* hand-written map — tested on purpose
> in W2.2 — which is why the tester supplies a *complete* auto-map when you give none.)
