# ADR-0001: mel-EDI is the only quantity a circadian threshold is scored against

Status: accepted
Date: 2026-07-25

## Context

`circadian_metrics` returns both `melanopic_lux` (K_m x the melanopic-weighted channel sum) and
`mel_edi` (photopic lux x mel-DER, the CIE S 026 quantity). They differ by D65's own
melanopic/photopic ratio — ~1.0997 on the 9-bin route, 1.0432 on the 3-bin route.

Nothing in a bare number distinguishes them, and `melanopic_lux` is the more obvious-looking name.
It was substituted at three separate call sites over the project's life: `run_annual`'s dosimetry,
`build_report`'s target-vs-achieved verdict, and (historically) the tool return itself. Every
substitution biased the same direction — thresholds are `>=`, so the inflated quantity manufactures
compliance. A design at a true 240 lx mel-EDI reported 107 h above a 250 lx threshold instead of 0 h.

## Decision

Every circadian threshold, compliance check, and dose accumulation takes **mel-EDI**.

- `dose_summary`/`hours_above_threshold` document mel-EDI as their contract and callers pass
  `m["mel_edi"]`.
- `check_compliance` scores mel-EDI and says so in its `note`.
- Where a legacy payload carries only `melanopic_lux`, convert it — exactly via `photopic_lux x
  mel_der` when both are present, else by dividing out the D65 ratio — and **disclose** the
  conversion in the output. Never grade the raw value.
- `melanopic_lux` stays on the return (it is a legitimate quantity) but is never the input to a
  threshold.

## Consequences

- Reported compliance hours drop by whatever the substitution was inflating; any previously quoted
  dosimetry figure computed from `melanopic_lux` is wrong and must be recomputed, not rescaled (the
  threshold comparison is non-linear).
- `mel_der_source` must be checked when accuracy matters: `spd_transported` keeps the source
  spectrum's within-bin detail, `binned_channels` is within ~1.5 % for smooth spectra but up to
  ~8 % high for narrow-band sources. **ADR-0006 settles the question this ADR left open** — *where*
  mel-EDI is measured. It is always at the point, never at the lamp.
- A test that feeds a series straddling the threshold in one quantity but not the other is the only
  reliable guard, and one exists (`test_dose_summary_threshold_is_evaluated_on_the_values_given`).
