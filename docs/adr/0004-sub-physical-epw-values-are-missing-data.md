# ADR-0004: a physically impossible EPW value is missing data, not a measurement

Status: accepted
Date: 2026-07-25

## Context

`atmosphere.derive`'s `resolve` helper implements `override > EPW > documented default` and decided
"is the EPW value present?" with `epw_value is not None`. The EPW data dictionary defines a per-field
missing sentinel (`999.0` for albedo, `9999.0` for irradiance, and so on), and `epw_hourly` maps those to
`None`. That contract is correct for pressure and AOD, where a zero does not occur.

It fails for albedo. IWEC and TMY2 files write a literal `0.000` in the albedo column for **every hour**
as a de-facto "no data" marker rather than the documented sentinel — 4 of the 11 EPWs this project runs
against do exactly that, Athens (the primary validation file) among them. (Only Athens still sits inside
this repository; the other ten moved out of the tree in the 2026-08-10 reorg, so the count is a property of
the project's weather set, not of a checkout.) The four are **Athens, Thessaloniki,
Singapore and Phoenix** (re-confirmed 2026-08-11 by tallying the distinct values of EPW field 32 across the
10-city comparison set plus Athens: those four carry `{0.000}` and nothing else, while Chania carries
0.060–0.090, London/Mumbai/Lagos 0.200, and Manaus/Berga a real varying series). So `albedo = 0.0` was adopted as
data, which:

- zeroed the entire ground-reflected term — `spectral_sky_from_epw` returned a 401-array of zeros at every
  surface tilt, and `server.py` broadcasts `[albedo] * 401` as the default spectral albedo whenever the
  caller does not pass one;
- reported `provenance: {"source": "epw"}` — asserting an instrument had measured a value no instrument
  produced.

The second half is the worse defect. A wrong number is recoverable; a wrong number wearing a measured-data
label is not, because every downstream audit trusts the provenance.

## Decision

A value outside its physically possible range is **missing**, and the documented default applies with
`source: "default"`.

For albedo the floor is `_ALBEDO_MIN_PHYSICAL = 0.01`. Nothing outdoors is a perfect absorber — fresh
asphalt is ≈0.04 and calm deep water at high sun ≈0.03 — so a broadband shortwave albedo at or below 0.01
cannot be real. (It is also adjacent to a singularity: SPECTRL2's ground–sky multiple-reflection term
`ρ·ρ_a / (1 − ρ·ρ_a)` goes identically zero there.)

Enforced in **two** places, deliberately:

- `epw_hourly._num` takes an optional `valid` predicate (`_VALID` maps field → predicate), applied after
  the sentinel test. Rejecting at the parse layer means `derive`'s existing three-way precedence reports
  honest provenance for free.
- `atmosphere.resolve` takes the same `valid=` predicate, because callers legitimately build rows by hand
  (the paper pipelines do) and would otherwise bypass the parser.

An explicit **override always wins** — the caller owns that choice, including an unphysical one.

Preferred over a plausibility *clamp* inside `derive`, which would still stamp `source: "epw"` and
therefore still lie; and over a config flag, which pushes a physics decision onto every caller and leaves
the default broken.

## Consequences

- Athens/Thessaloniki/Singapore/Phoenix now resolve to the documented 0.20 with `source: "default"`, and a
  vertical surface sees a ground term of ≈55 rather than exactly 0.
- A genuinely dark surface is untouched: Chania's 0.07 still reads `source: "epw"`. Any floor must be
  justified physically and set low enough that real data survives.
- **Publication impact — ✅ DONE, and the re-run found more than this ADR predicted.** As accepted, this
  bullet read: the four zero-albedo cities ran at albedo 0.0 while the other six used real values, the
  delivered spectrum shifts only ≈0.4–0.7 % because `energy_normalize` re-anchors diffuse to EPW DHI, and
  "those four rows want a re-run or an explicit caveat". **The re-run was carried out** and its numbers are reproduced in full below, so this ADR stands alone.
  Do not re-run them again on the strength of the retired sentence.

  The result **contradicts the "only ≈0.4–0.7 %" framing** this ADR used to justify treating the impact as
  cosmetic. The correction is **not a uniform offset and not sign-stable**: the two Greek cities' gaps
  narrowed while Singapore's and Phoenix's widened, because ground glow enters the diffuse stream *before*
  the cloud modifier, so its colour effect is conditioned on clearness. Paired Athens hours (identical 4383
  timestamps) give **+318 K clear, −186 K intermediate, −1368 K overcast** — a grey ground *blues* a
  clear-sky diffuse spectrum and *warms* an overcast one. Per-city movement (bb Δ% / mel-EDI Δ% / CCT gap):
  Athens −2.6→−0.9 / −12.2→−10.5 / 2981→2932; Thessaloniki −2.9→−0.8 / −12.5→−10.3 / 2383→2301; Singapore
  −3.2→−3.6 / −14.9→−16.0 / 3657→3995; Phoenix +4.8→+4.2 / −2.2→−3.5 / 2434→2765.

  The ≈0.4–0.7 % figure was right about the *delivered* spectrum and wrong as a measure of the defect's
  reach: |CCT gap| moved −82 to +338 K in **both** directions, enough to shift Table 6's partial
  correlations (**PWV partial +0.50 → +0.38**). The cross-city conclusion's direction survives; its
  precision is lower than the pre-correction numbers implied. A DHI re-anchoring bounds the energy, not the
  colour — an ADR asserting an impact is small must say which quantity it means.
- The pattern generalises: any EPW field whose "no data" encoding differs from the data dictionary gets a
  `_VALID` predicate rather than a special case at the point of use. Add the field to `_VALID`, not an
  `if` at the call site.
