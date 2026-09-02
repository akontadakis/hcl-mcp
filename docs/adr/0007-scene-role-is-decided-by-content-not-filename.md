# ADR-0007: a scene file's role is decided by its content, not its filename

Status: accepted
Date: 2026-08-01

## Context

`run_grid` with `electric_lights` builds three octrees: daylight (geometry + materials + sky),
combined (+ luminaires), and **electric-only** (geometry + materials + luminaires, *no sky*). The
electric-only octree is what isolates the luminaires' contribution, and it is only meaningful if the
sky is genuinely absent from it.

Which files were sky was decided by a basename regex:

```python
_SKY_RE = re.compile(r"(^|[^a-z])sky([^a-z]|$)", re.IGNORECASE)
```

`re.IGNORECASE` makes `[^a-z]` exclude letters of **both** cases, so any `sky` adjacent to a letter
failed to match. `sky.rad` and `clear_sky.rad` matched; `skydome.rad`, `SKYDOME.rad`, `skyvault.rad`
and `clearsky.rad` did not. The docstring nonetheless claimed sky geometry "can never leak into the
electric octree".

It leaked. A sky named for its condition rather than for the word "sky" reached the electric-only
octree and the block reported **17705 lx where the true value was 1662 lx** — a 10.7x overstatement
that looked entirely plausible on its own. Nothing in the result said anything was wrong. It was
caught only by an external physical bound: 24 fixtures x 8620 lm / 75.6 m2 = 2737 lx is the
perfect-utilisation ceiling, so 17705 lx sat 6.5x above a value no real room can reach.

The reliable path already existed — `sky_files` takes exact-path precedence in the library — but
`run_grid`'s MCP signature never accepted it, so a tool caller was forced onto the heuristic with no
override at all.

## Decision

Three changes, in order of how much they fix.

**1. Detect by content; the basename is a hint.** A file is what it contains. `_is_sky_file` reads
the head of each scene file and looks for markers only a sky carries: `gensky`/`gendaylit` (inlined,
run, or the comment header gensky itself writes), `skyfunc` (whether defined by gensky as
`void brightfunc skyfunc` or used as a modifier), the `source sky` / `source ground` hemispheres,
`light solar`, and the `skybright.cal` / `perezlum.cal` patterns those evaluate. Content and
basename are OR'd, never AND'd, because the file legitimately does not exist yet on the emit path.

**2. The basename fallback is a plain substring.** Any boundary rule just relocates the edge that
produced this defect. `"sky" in basename.lower()` has no edge to get wrong. It over-matches
(`whisky.rad`), and that is the cheap direction: it is consulted only when the file cannot be read,
so a false positive drops a file from one octree on the emit path, while a false negative puts
daylight into an executed result.

**3. `sky_files` is exposed through the MCP `run_grid` signature** and remains authoritative when
given. It is the escape hatch in both directions: naming a sky no detector would spot, and *keeping*
a sky-looking file (an exterior context block) inside the electric octree.

Additionally, the `electric` block now carries `lumen_bound` — sum of luminaire lumens over the
sensor grid's bounding box, with `exceeded` — and an `ELECTRIC_EXCEEDS_LUMEN_BOUND` advisory at
severity `error`. The bound needs nothing the run does not already hold and catches the whole class
of over-count, not just this instance.

## Consequences

- Detection is a **detector, not a guarantee**, and the docstring now says so. A hand-rolled sky
  using none of these primitives, under a name with no "sky" in it, will still reach the electric
  octree. That is what `sky_files` is for. The replaced docstring's "can never leak" was the more
  dangerous artefact than the regex.
- Content sniffing reads up to 64 kB per scene file per set. A sky definition is a handful of
  primitives, so this is bounded and cheap; unreadable files fall back to the name silently, which
  is exactly the emit path and every unit test passing bare names like `"m.rad"`.
- A single-file scene containing *both* room and sky would now be dropped from the electric octree
  entirely, producing a near-zero electric block. That is a louder failure than the silent 10.7x
  over-count it replaces, and the lumen bound does not mask it.
- `lumen_bound` bounds the **mean**, never a single point — illuminance directly beneath a downlight
  legitimately exceeds it — and its area is the sensor grid's bounding box, which understates the
  floor and so overstates the ceiling, erring toward silence. `exceeded` is evidence to check, not
  proof of a defect. The leak that motivated it ran 6.5x over.
- Blast radius confirmed as `run_grid`'s electric block only: `_select_non_sky` has one call site,
  `run_image` builds no electric-only octree, and the annual paths have no electric block at all.
