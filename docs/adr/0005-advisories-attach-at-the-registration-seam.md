# ADR-0005: advisories live in `hcl_mcp` and attach at the registration seam

Status: accepted
Date: 2026-07-28

## Context

`hcl_core` computes physical quantities correctly but says nothing about how easy each one is to
misread. Three domain traps had already cost real debugging time before a rule existed for any of
them: `melanopic_lux` substituted for `mel_edi` (ADR-0001), a zero-albedo EPW column read as measured
ground reflectance (ADR-0004), and a zone-weights convention clash that silently changes a savings
figure. In each case the number returned was defensible on its own; the failure was a caller trusting
it further than the data supported. Six such rules were written — `MEL_DER_BINNED`,
`ALBEDO_NOT_MEASURED`, `DOSE_THRESHOLD_IS_DEFAULT`, `ZONE_WEIGHT_REMAINDER`,
`GEOMETRY_HEALTH_UNCLEAN`, `NVRD_ZERO_DIVERGENCE` — each reading a field a tool already returns and
attaching a `{code, severity, message, field?}` caution about it. Two decisions had to be made before
they could ship: which layer owns them, and how they attach to the registered tool names (50 then, 51 today).

## Decision

**1. Advisory rules live in `hcl_mcp`, not `hcl_core`.**

Every rule in `src/hcl_mcp/advisories.py` reads a field `hcl_core` already computed and phrases a
caution about it — that is reporting, not physics. `hcl_core`'s layer rule (`CONTEXT.md`) was "no
Radiance, no subprocesses, no file formats" when this ADR was written (since restated with its audited
exceptions — see CONTEXT.md), which advisories don't violate either way, but putting
caller-facing phrasing in the pure-math layer would give it a dependency on presentation it doesn't
need: message wording, severity levels, and the `{code, severity, message, field}` shape are protocol
concerns, not computation. Rejected alternative: put the rules in `hcl_core` next to the fields they
describe, on the theory that co-location aids discovery. Rejected because it inverts the dependency —
`hcl_core` must stay callable with no knowledge of MCP result shapes — and because none of the six
rules compute anything; they only re-read.

Consequence: `hcl_mcp` gains one small pure module (`advisories.py`, no I/O, a rule that raises is
skipped rather than failing the call). The layer rule still holds because no rule computes a physical
quantity — `_albedo_not_measured` distinguishes `source: "default"` from `source: "epw"`, it does not
recompute albedo.

**2. Rules attach by wrapping at the tool-registration loops, not by decorating each tool.**

`_with_advisories` wraps each callable once, at the two `for` loops that call `mcp.tool(...)`
(`src/hcl_mcp/server.py`, the loops over `_TOOL_FUNCS` and `_TOOL_ALIASES` — located by content, not by
line number: this ADR originally cited `:1829`/`:1832`, which have drifted repeatedly since),
rather than putting `@advise`-style decorators on all 51
tool definitions. One wiring point covers every registered name — the 47 functions in `_TOOL_FUNCS`
and the 4 aliases in `_TOOL_ALIASES` (46 + 4 = 50 when this ADR was written; `lm83_daylight` joined
2026-08-12) — and the module-level functions themselves stay unwrapped, so
the existing test suite's 71 exact-dict assertions (written against the bare functions) keep passing
unmodified. Rejected alternative: decorate each tool function individually. Rejected because it is 51
call sites to keep in sync instead of one, and because it would have forced every one of those 71
assertions to either ignore an `advisories` key or be rewritten.

Consequence: the wrapped path — what an MCP client actually calls — has no incidental coverage from
the rest of the suite, since every other test calls the unwrapped function directly. Two tests carry
the entire burden: `tests/test_advisories_wiring.py` proves advisories actually attach through the
wrapper, and `tests/test_tool_registration.py` proves wrapping does not alter the published JSON
schema. Neither test may be weakened without a replacement.

### Shape decisions reached by probing, not reasoning

Two of the six rules have a shape that isn't derivable from the requirements alone — both were settled
by probing the installed `fastmcp 3.4.2`, not by design preference, and both are worth recording so a
future change doesn't "fix" them back to the more obvious-looking form:

- **`DOSE_THRESHOLD_IS_DEFAULT` is value-based, not provenance-based.** FastMCP fills every unset
  parameter with its declared default *before* calling the tool function, so by the time
  `_with_advisories`'s wrapper runs, "the caller explicitly passed 250.0" and "the caller passed
  nothing" are the same call — there is no `**kwargs`-level signal left to distinguish them. The rule
  therefore fires whenever `result["dosimetry"]["threshold"] == DEFAULT_DOSE_THRESHOLD` (250.0),
  regardless of whether that was the caller's deliberate choice. This makes the advisory a false
  positive for a caller who explicitly wants 250 lx mel-EDI, but the alternative — silence — is a false
  negative for the far more common case of not knowing the default was in effect, which is the failure
  mode that motivated the rule.
- **`ZONE_WEIGHT_REMAINDER` reports a consequence, it does not assert an error.** A zone-weights sum
  below 1.0 is documented, intended behaviour: `src/hcl_mcp/server.py` states the remainder is
  uncontrolled floor billed at full power. The rule cannot know whether the caller's weights are
  floor-area fractions (where summing under 1.0 is normal and the uncontrolled core is real) or
  `photosensors` zone weights (a different convention — on the `office_room` reference fixture
  Σw ≈ 0.707, two zones at ≈0.354; the value is not a constant but a depth-ratio that varies with room
  depth and window head height, so no rule can recognise the convention from the sum alone) misread as
  floor-area fractions. It therefore always phrases
  the message as "X% is billed at full power as uncontrolled core, correct if these are floor-area
  fractions, not if they're zone weights" rather than flagging Σw < 1 as wrong.

A third probed fact belongs here too, because it bears directly on how much trust the registration-seam
decision deserves: `functools.wraps` on `_with_advisories`'s inner wrapper is load-bearing, and its
failure mode is loud, not silent. FastMCP inspects the wrapped callable's signature to build the tool's
JSON schema and rejects any callable whose signature is `(*args, **kwargs)`. `functools.wraps` copies
`__wrapped__` onto the wrapper, and `inspect.signature` follows `__wrapped__` back to the original
function's real parameter list. Removing `wraps` (confirmed by mutation testing during the advisory
rules' implementation) does not degrade a schema quietly — it makes every `mcp.tool(...)` registration
raise `ValueError: Functions with *args are not supported as tools` at import time, so the entire
server fails to start rather than shipping a wrong or empty schema. This is why `wraps` was kept as a
one-line requirement rather than defended with an extra test: the failure is already maximally visible.

## Consequences

- Advisories are opt-in to read and additive to the contract: a dict result either gains an
  `advisories` key or is returned unchanged (`_attach` in `server.py` never mutates the input and omits
  the key entirely when there is nothing to say), so no existing caller that ignores unknown keys can
  break.
- A rule that raises is caught and skipped (`advise()` in `advisories.py`), so a bug in a rule can only
  cause it to go silent, never fail the tool call it's attached to.
- List-shaped results (`circadian_metrics` with multi-point input) carry no advisories at all —
  wrapping a list would change that tool's published contract, so `_attach` passes non-dict results
  through untouched. This is a real v1 gap, not an oversight: `mel_der_source` still needs checking
  per-point by hand there.
- Extending v1 means adding one `@rule`-decorated function to `advisories.py`; it does not touch
  `server.py` unless the new rule needs a field no existing tool returns yet.

## Amendment, 2026-08-01 — depth and noise are part of a rule's contract

The six rules above are the set as accepted; there are now nine (`SPECTRAL_TRANSPORT_SHIFT` and
`ELECTRIC_EXCEEDS_LUMEN_BOUND`, added by ADR-0006 and ADR-0007, and later
`RADIANCE_DROPS_IES_CANDELA_SCALE`). The count is not the point. Two
structural properties this ADR did not state turned out to be load-bearing, and each was found only
after a rule had shipped silently wrong.

**Depth.** `_iter_dicts` walks the top level of a result. That is right for `circadian_metrics`,
where the metrics dict *is* the result, and wrong for `run_grid`, which nests every per-point field
under `daylight`/`electric`/`combined`.`metrics[]`. A rule reading a per-point field through
`_iter_dicts` alone therefore **fires in its unit test and never in production** — and the unit test
looks entirely convincing, because it hands the rule a metrics dict picked out of the result by hand.
`MEL_DER_BINNED` was written that way at v1 and had never once fired on `run_grid`, the tool that
produces most channels in this codebase; `SPECTRAL_TRANSPORT_SHIFT` repeated the mistake and shipped
that way for one commit. Both now use `_point_metrics`, which yields `(block, metrics)` over both
shapes. **A test asserting a rule against a hand-constructed nested dict does not prove the rule
reaches the tool** — assert against the whole tool result.

**Noise.** Widening a rule's reach is not automatically an improvement. `MEL_DER_BINNED` walking
every block would fire on the `daylight` block of every single run: a block that is always present,
whose smooth-sky spectrum costs ~0.13% on the binned route, and for which no single source spectrum
exists to pass instead — so the warning would be permanent, unactionable, and quote a ~8% figure
roughly 60x its real exposure. An advisory like that is not a weaker version of a useful one; it is
the thing that teaches people to stop reading the block, taking the other seven down with it. Hence
`_point_metrics` yields the **block name**, and a rule may carry a different message — or stay
silent — per block. The test that a rule is correctly scoped is therefore *two*-sided: one case
proving it fires where it must, and one proving it stays quiet where nothing can be done.

Both properties are consequences of the same original decision — that rules read result shapes at the
protocol layer — so they belong here rather than in the ADRs that surfaced them.
