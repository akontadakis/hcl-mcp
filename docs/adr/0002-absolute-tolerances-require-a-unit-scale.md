# ADR-0002: code comparing lengths or areas against a constant must receive the unit scale

Status: accepted
Date: 2026-07-25

## Context

`geometry_health`'s tolerances are absolute physical quantities: 1 mm coincidence, 5 mm planarity,
and a 2 m² ceiling on the end-cap containment exclusion. The checker was handed raw OBJ vertices with
no scale, so those constants silently changed meaning with the model's unit system.

It broke in **both** directions, and the false positive was the worse one:

- a real 0.5 mm z-fight in a millimetre model read as a 0.5-unit separation and was **missed**;
- a legitimate 1 x 1 m end-cap read as 1e6 units², blew past the 2 m² gate, and produced a spurious
  `COINCIDENT_SURFACES` **error** — so `import_geometry(strict=True)` refused to import the repo's own
  reference fixture merely re-expressed in mm.

Every health test authored in metres, so the whole class was invisible.

## Decision

Any check comparing a length or area against an absolute constant runs on **world-space (metre)**
geometry. `check_geometry_health` takes a `scale` and converts vertices once at entry
(`_scaled_to_metres`); callers pass the scale they already resolved. `scale=1.0` is byte-identical to
the previous behaviour.

Scale only — the checks are rotation-invariant, so `up_axis`/north never affect a finding.

Preferred over the alternative of scaling each tolerance, because it keeps every constant honestly in
metres and needs no per-check plumbing, matching how `footprint`, `sensor_methodology` and
`scene_preview` already take `scale` and route through `_to_world`.

## Consequences

- Any new check may state its tolerance in metres and trust the input.
- A reported deviation is in metres and may be labelled `_m`. (`face_area` still returns raw
  units² — it is used for ratio and degeneracy tests, which are scale-invariant, but its docstring's
  "m²" claim only holds once the input is scaled.)
- Tolerances quantised into buckets need care at the bucket edge: `_plane_key` quantises the plane
  offset by `tol`, so a pair separated by almost exactly `tol` could straddle two buckets and never be
  compared. Faces now register in both adjacent buckets with pairs de-duplicated. Unit conversion
  makes such round-off reachable, so this is not merely theoretical.
- Non-metre coverage is now required for any new geometry check.
