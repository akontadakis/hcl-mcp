# ADR-0003: a timestep's duration is its own interval, never the gap to the next sample

Status: accepted
Date: 2026-07-25

## Context

`hours_above_threshold` credited each qualifying sample the **forward** difference
`hoy[i+1] - hoy[i]`. That is exact on a contiguous series, which is what it was written for (the
commit's intent was sub-hourly resolution, replacing an assumed 1 h step).

But production series are gapped. `weather.decompose` emits occupied hours only, and for a
multi-month period it repeats a fixed day/hour window across months. So the last sample of every
block absorbed the whole non-occupied gap:

| window | reported | true |
|---|---|---|
| 3 days, 08:00-18:00 | 59.0 h | 33.0 h |
| Jun-Aug, 08:00-18:00 | 1475.0 h | 33.0 h |

The error does not shrink with a finer timestep — it comes entirely from the gaps. `dosimetry_threshold`
defaults to 250.0, so every default `run_annual` was affected.

`min(forward, backward)` does **not** fix it: for the first sample of a block the backward gap is also
the overnight gap.

## Decision

Each sample contributes **its own timestep**:

- an explicit `step_hours` wins (`run_annual` threads `timestep_min / 60`);
- otherwise infer the **modal** positive gap — a real timestep recurs once per sample while
  block/overnight/inter-month gaps appear at most once per block, so the most frequent gap is the
  nominal step, ties breaking to the smaller;
- clamp to the actual forward gap, so a genuinely short tail interval is still exact.

This matches `daylight_metrics.annual_sunlight_exposure`, which already took an explicit `step_hours`
and is gap-immune by construction. New time-integrating code follows that convention.

## Consequences

- Contiguous full-year runs are unchanged (8760 samples -> 8760 h).
- Any dosimetry figure computed over a `period` is superseded; `docs/hcl-methodology.md` H-19 and
  `docs/technical-reference.md` describe the rule as stated here.
- A two-sample series with two distinct gaps is genuinely ambiguous from spacing alone. Production
  always knows its timestep, so callers should pass `step_hours` rather than rely on inference.
- Six "characterization" tests asserted the old forward-gap behaviour as correct and were rewritten; they
  now live in `tests/test_dosimetry.py` (the explicit-step, unit-fallback, last-point, short-tail and
  following-gap cases, alongside `test_modal_gap_infers_the_step_when_it_recurs`). Tests that pin current
  behaviour must say so, or they defend the bug.
