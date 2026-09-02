# ADR-0006: mel-DER is reported at the point, not at the source

Status: accepted
Date: 2026-08-01

## Context

ADR-0001 settled *which* quantity a circadian threshold is scored against: mel-EDI. It left open
*where* that quantity is measured, and the codebase answered inconsistently.

`circadian_metrics(channels, channel_type, spd=...)` computed mel-DER from the supplied source SPD
and multiplied it by the photopic lux at the point: `mel_edi = photopic_lux(point) x mel_der(lamp)`.
The arithmetic was right and the choice deliberate — the docstrings argued it, and for
characterising a luminaire it is genuinely the better route, because the binned route reads up to
~8% high on a narrow-band source whose emission lines fall inside a bin.

The boundary was never stated. `run_grid` passed the luminaire's SPD to the whole **electric** block
(in `grid.py`, at the `_recombine(electric_res, spd=...)` call — cited here as `:284` when this ADR was
written, since drifted to `:464`, and `:284` is now an unrelated function), so every point in that block
received the *same* mel-DER, identical by construction,
however the room had reshaped the spectrum on the way to each one. Two consequences followed:

- `mel_der_source: "spd"` labelled that value, and everywhere else in this codebase "spd" means
  *more* trustworthy. In a spectrally selective room it was the *less* accurate of the two routes,
  and it carried no `mel_der_note` while the honest binned route did.
- Measured on a fluorescent 840 (source mel-DER 0.5550 exact / 0.5910 binned): with neutral surfaces
  the SPD route was exact and binned ran +6.5%; with warm surfaces the SPD route ran +7.5% while
  binned stayed at +6.5%. The label and the accuracy pointed opposite ways.

mel-DER is defined on the spectral irradiance **at the observer**. A source spectrum is the right
answer only where the source *is* the point.

## Decision

`mel_der` and `mel_edi` always describe the spectrum at the point the channels were measured.

A supplied `spd` is read as "the source spectrum feeding these channels", and the transport between
them is recovered from the channels themselves. The engine models transport at the resolution of its
bins — it bins the source, bins each material, and multiplies per channel — so the per-bin transport
it applied is recoverable exactly as `T_i = channels_i / bin_average(spd)_i`, and the spectrum it
implies at the point is `S(lambda) * T_i` for lambda in band i. Weighting that against the S 026
action spectra (`spectral_metrics.mel_der_transported`) keeps the source's full 1-nm structure —
which the nine channel averages cannot represent — and applies the transport the simulation actually
ran.

Three routes, recorded in `mel_der_source`:

| route | when | worst error* |
|---|---|---|
| `spd_transported` | a source SPD is supplied | 0.73% |
| `binned_channels` | no SPD; inferred from channel averages alone | 8.49% |
| `spd_source_untransported` | SPD supplied but no transport recoverable (a dark point) | falls back to the source value, labelled, with a note |

\* against the mel-DER of the true transported spectrum, over 6 sources x 3 transports. The old
source-SPD route scored 12.74% worst / 8.78% rms on the same set; `spd_transported` scores 0.73% /
0.38%.

> **Provenance of these figures.** They come from a one-off comparison run made while deciding this
> ADR, not from a committed artifact — no test or fixture pins them, so they cannot be re-derived from
> the tree as it stands and should be read as the measurement that motivated the decision rather than a
> reproducible benchmark. What *is* pinned is the property the decision rests on: `tests/test_mel_edi_exact_route.py`
> asserts the neutral-transport reduction at `rel=1e-9` over five presets, and the route labelling and
> caveats are asserted alongside it. Anyone re-opening the accuracy question should re-run the sweep
> rather than trust the numbers above.

Alongside a `spd_transported` result, `source_mel_der` (the source's own value) and
`transport_ratio` (the two divided) are returned, so the shift the room imposed is visible rather
than folded away. A `SPECTRAL_TRANSPORT_SHIFT` advisory fires at >= 5%.

## Consequences

- **This is a generalisation, not a change of answer.** When the transport is neutral every `T_i` is
  equal and the result reduces *exactly* to `mel_der(spd)` — verified at `rel=1e-9` across five
  presets. Source characterisation is untouched, which is why the whole of
  `tests/test_mel_edi_exact_route.py` stayed green on its value assertions.
- `mel_der_source` no longer emits the bare string `"spd"`. Callers matching on it exactly must
  move to `"spd_transported"`; `"spd" in mel_der_source` still holds.
- Per-point mel-DER now *varies across points*, as it must. A test asserting it is constant would
  pin the defect — `test_many_points_share_one_spd` was narrowed to the claim it can actually
  support (points seeing the *same* spectrum agree) and paired with its complement.
- A luminaire datasheet quotes the source figure and will not match the reported one. That is the
  correct behaviour and the advisory says so; do not "correct" `mel_der` toward the datasheet.
- Two carriers had to be widened to hold the new fields, and both had failed *silently*:
  `export_csv` took its header from the first block only, so `source_mel_der`/`transport_ratio`
  never reached the exported table (now the union of every block's keys); and the
  `SPECTRAL_TRANSPORT_SHIFT` rule read `transport_ratio` off the top level, where `run_grid` never
  puts it — the advisory fired in a unit test and never on the tool the defect lived in. A rule
  reading a PER-POINT field must walk `daylight`/`electric`/`combined` `.metrics[]`.
- `MEL_DER_BINNED` had the same blindness for far longer and has been fixed the same way, but the
  noise objection was real and is answered by making the block name part of `_point_metrics`'s
  contract: `daylight` is exempt (present on every run, ~0.13% error, no source spectrum to pass —
  a permanent unactionable warning), while `electric` and `combined` each get an actionable message.
  For `combined`, whose mixture has no single source spectrum, that action is to exploit **mel-EDI's
  additivity**: summing the `daylight` and `electric` blocks stays within ~0.4% of the continuous
  truth while the `combined` block's own binned value degrades to **+8.11%** as luminaires dominate.
  An advisory that fires on every result, cannot be acted on, and overstates its magnitude ~60x is
  not a smaller version of a useful one — it is what stops the others from being read.
- The estimator is only as good as the engine's bin resolution. It cannot recover spectral structure
  the simulation never carried — it recovers the source structure the *SPD* carries, weighted by the
  transport the *simulation* carried, which is the best available combination of the two.
