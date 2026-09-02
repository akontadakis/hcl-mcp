# HCL-MCP — End-to-End Validation Test Plan (v2 — live-captured, assertion-driven)

Exhaustive coverage of **50 tool entries (46 unique + 4 verb-object aliases), 13 prompts, 14
resources** (11 fixed + 3 templates), driven as realistic start-to-finish workflows.
*(Corrected 2026-07-25 from 49/45: `check_geometry` is registered but had never been covered — the 46th
tool now has a test at **W2.10**. Verified against the live server: `_list_tools()` returns 50 names.)* **v2** adds,
for every ID, a **value-correctness assertion** and a **real captured output**, plus three new
depth sections — **N** (negative/edge), **X** (cross-tool consistency), **S** (workflow chaining).

> **v2.5 (2026-07-30) — advisories, ledger and fixture pass.** New section **A — Advisories** covers the
> caller-facing warning surface (`hcl_mcp/advisories.py`, ADR-0005) that attaches at the registration seam
> to all 46 tool functions and had **zero** coverage here: 6 codes + 4 contract properties, six of them
> captured live. Also fixed: the coverage ledger silently omitted **`check_geometry`** (head read 44 while
> the surface was 46) and is now the declared authority; `points` auto-resolution picked a **1-point eye
> sensor** over the 45-point work-plane grid by sort order (roles added, defaults named); **W2.10**'s mm leg
> named a fixture that never shipped (**now shipped + captured**); **W2.6a** was scored PASS on the
> feature's own verification (**re-scored PARTIAL/BLOCKED**).

> **v2.4 (2026-07-23) — refreshed against the post-campaign server.** Counts verified live against
> `mcp._list_tools()`: **49 / 13 / 11 + 3**. The 45th tool is `quality_presets`, which shipped defined,
> documented and unit-tested but **missing from `server.py`'s registration tuple**, so no client could
> call it — found and fixed while refreshing this plan. Also refreshed: the W2.3 working-plane datum
> (was capturing a bug), W1.4's melanopic fields, and four new cross-tool seam checks **X5–X8**.

---

## Conventions

- `INPUTS/` = `hcl_validation/inputs/`.
- **Structured outputs — one folder per workflow.** Every section writes to its **own** folder under
  `hcl_validation/results/` so a reader can review the outputs of each workflow in isolation — never one
  flat dump. `SEC/` in a section below = that section's folder, per this map:

  > W0 → `W0-orientation/` · W1 → `W1-spectral/` · W2 → `W2-geometry/` · W3 → `W3-grid/` ·
  > W4 → `W4-glare/` · W5 → `W5-electric/` · W6 → `W6-annual/` · W7 → `W7-spectral-sky/` ·
  > W8 → `W8-daysim-nvrd/` · W9 → `W9-studio/` · N → `N-negative/` · X → `X-cross-tool/` ·
  > S → `S-workflows/` · E → `E-energy/` · G → `G-arguments/` · **A → `A-advisories/`** ·
  > Prompts → `prompts/` · Resources → `resources/`
  >

  Inside each `SEC/`: a **`RESULTS.md`** (the actual metric values + Assert verdict + score per ID — the
  reviewable output), the section's **headline data files at the top** (`grid.csv`, `*.hdr`, `manifest.json`,
  `report.{md,html}`, `preview_*.png`, `dosimetry.json`, …), and a **`work/`** subfolder for all
  intermediate/engine files (`.rad`/`.oct`/`.hdr`/`.cal`/`.pts`/`.wea`/`.smx`/scripts/logs).
- **`WORK/` in a Call below = `SEC/work/`** — i.e. pass `work_dir:"hcl_validation/results/<SEC>/work"` on
  every tool call in that section, and write section artifacts (`export_csv`/`write_pts`/`subset_out`/
  `write_prefix`) into `SEC/` (top for headline data, else `work/`). The legacy flat `HCL_WORK_ROOT` is only
  a fallback for tools given no `work_dir` — this kit routes everything per-section instead.
- **Resolved inputs (this kit):** geometry `office_room.obj` (+ `office_room_blinds.obj` for S1),
  weather `GRC_Athens.167160_IWEC.epw` (`.wea` derived live via `epw2wea`), luminaire/SPD the
  tunable-white trio `L09_{warm,neutral,cool}.{ies,spd}` (default `L09_neutral`), material maps
  `office_room_material_map.json` / `office_room_blinds_material_map.json`.
  **Sensors: five `.pts` DO ship** for the single-window south model — `office_room_grid.pts`
  (45-pt EN 12464-1 work plane, up-facing, z=0.8), `observer_1.pts`/`observer_2.pts` (vertical eye),
  `sensor_1.pts`/`sensor_2.pts` (daylight-dimming zones) — and `active_inputs.json` names one default
  **per role** (`points` / `points_observer` / `points_photosensor`). `derive_sensors:true` remains the
  path for any *other* model. Echo the resolved set in the report banner.
  > **⚠️ Do not resolve `.pts` by sort order.** The three roles are physically different sensors that share
  > one extension. Alphabetical resolution puts `observer_1.pts` (a **single vertical eye point**) first,
  > ahead of the 45-point work-plane grid — which makes sDA/ASE degenerate to 0%/100%, averages DF over the
  > wrong plane, and leaves EN 12464-1 uniformity undefined. Match on
  > `_resolution.by_class.points.roles`, which always wins over sort order.
- **Block format.** Each ID is a block, not a table cell:

  - **Call:** the exact tool + arguments.
  - **Assert:** the value-correctness bound(s) — what makes the numbers *right*, not just present.
  - **Captured:** real JSON from this machine, stamped `(captured 2026-06-29, Radiance 6.1a)`.
    Long arrays truncate head/tail as `[v0, v1, … vN] (len 401)`.
  - **Result:** the score.
- **Scoring:**

  - `PASS` — ran, output present **and within the Assert bounds**.
  - `PASS(emit)` — returned `ran:false` + `commands[]` because a binary is absent (expected & correct).
  - `PASS(emit, time-boxed)` — engine present but the live run was deliberately skipped for wall-time; emit-plan shown.
  - `PARTIAL` — ran, keys present, **but a value violates an Assert bound** (the new v2 trap).
  - `FAIL` — error / missing keys / wrong typed failure on a negative case.
  - `BLOCKED` — couldn't attempt; say why.
- **Engines are optional.** Sim steps are scored conditionally on W0 capability. Detect state in W0
  first, record in the banner, score each sim step against it — never assume a fixed machine.
- Always call `validate`, `radiance_status`, `daysim_status` **first**.

---

## Capability banner (captured 2026-06-29)

- **Radiance 6.1a** (`6.1.39b9966033`) — `available:true`, `bin=/usr/local/radiance/bin`; all 17
  binaries found. → all Radiance sim steps run **live**.
- **Daysim** — `available:true`, `bin=/usr/local/daysim/bin` (`ds_shortterm`, `epw2wea`). → annual /
  sub-hourly run **live**.
- **SMARTS** — `engine="smarts"` ran **live** (W7.3), agreeing with SPECTRL2 to ~2%.
- `validate` → `ok:true`. **Note:** one sub-check, `channel_vs_spd_alpha_opic`, returns
  `passed:false` **by design** (informative/non-gating §9.3a reconstruction divergence). This is
  **expected**, not a defect — see W0.1.

---

## W-prep — Input resolution & geometry sanity (do before W2)

W-prep artifacts belong to the geometry workflow → write them under `W2-geometry/work/`.

1. **Auto-resolve inputs** from `INPUTS/active_inputs.json._resolution`. Explicit paths win; on
   multiple matches prefer the non-sample and WARN; read `site` (auto from EPW LOCATION) + `compliance`.
2. `import_geometry(dry_run:true)` → groups + suggestions; resolve `material_map` (on-disk map that
   COVERS the groups, else auto-generate from `.mtl`, write `W2-geometry/work/auto_material_map.json`, pass
   as `sidecar`). Drop-and-run must NOT stop on unmapped group — only **N** section / W2.2 hard-fails.
3. `.wea`: derive from the resolved EPW via `epw2wea <epw> W2-geometry/work/<wea>` (Radiance live). This
   derived `.wea` is a shared input — later sections (W6/W8/E) reference it by that path rather than
   re-deriving it.

---

## W0 — Orientation & self-test

### W0.1 — validate (alias run_validation)

- **Call:** `validate {}`
- **Assert:** `ok:true`; `weight_sums` all ≈1.0 (±1e-3); `kd65_vs_published` mel≈1.326, L≈1.629
  (CIE S 026 anchors); `mel_der_d65`==1.0; `binning_fidelity` 9-ch centroids present.
  **Expected non-gating:** `channel_vs_spd_alpha_opic.passed:false` (informative, ~99.7% EDI
  divergence) — does NOT make `ok` false. (v1 wrongly asserted "all passed:true".)
- **Captured (2026-06-29):** `ok:true`; `weight_sums` all ≈1.0; `kd65_vs_published`
  `{S:0.8169,M:1.4557,L:1.6289,rhod:1.4494,mel:1.3259}`; `mel_der_d65:1`; `binning_fidelity.channels_9`
  `[399.5,439,479,514,543.5,572.5,597.5,619,705]`. **`channel_vs_spd_alpha_opic.passed:false`** (EDI
  divergence ~99.76%) — informative, does NOT gate `ok`; `channel_vs_spd_divergence_bounded.passed:true`
  (ELR ratio div 0.625% ≤ 5% ceiling).
- **Result:** PASS (and the by-design `passed:false` is documented — the v1 trap is closed).

### W0.2 — radiance_status

- **Call:** `radiance_status {}`
- **Assert:** if installed → `available:true`, `version` set, `found ⊇ {oconv,rtrace,gendaymtx,ies2rad}`,
  `missing:[]`; else `available:false` + `missing[]`. **Record — gates W2–W7.**
- **Captured (2026-06-29):** `{"available":true,"bin_dir":"/usr/local/radiance/bin","version":"RADIANCE 6.1a 2026-05-05 LBNL (6.1.39b9966033)","found":[…17 incl oconv,rtrace,gendaymtx,ies2rad,obj2rad,xform…],"missing":[]}`.
- **Result:** PASS (live).

### W0.3 — daysim_status

- **Call:** `daysim_status {}`
- **Assert:** installed → `available:true` + `found ⊇ {ds_shortterm,epw2wea}`; else `available:false`,
  `missing ∋ ds_shortterm`. **Record — gates W8.**
- **Captured (2026-06-29):** `{"available":true,"bin_dir":"/usr/local/daysim/bin","found":["ds_shortterm","epw2wea"]}`.
- **Result:** PASS (live).

### W0.4 — reference (alias get_reference)

- **Call:** `reference {"topic":"coefficients"}` then `bins`, `caveats`, `overview`
- **Assert:** each returns documented keys (`coefficients`→`melanopic_9`; `bins`→`bins_9`;
  `caveats`→`section_9_3`); 9-ch melanopic vector sums≈1.
- **Captured (2026-06-29):** coefficients `melanopic_9=[0.0119,0.1784,0.4165,0.268843,0.1033,0.019, 0.0017,0.000296,0.000061]` (Σ≈1.0), `photopic_3=[0.265,0.67,0.065]`, `luminous_efficacy=179`;
  bins `bins_9=[[380,419],[419,459],…,[630,780]]`, `bins_3=[[587,780],[499,587],[380,499]]`;
  caveats `section_9_3` = the 3 source-port fixes (float-division, 9-ch ordering, image-vs-grid b3).
- **Result:** PASS.

### W0.5 — quality_presets (NEW 2026-07-23)

- **Call:** `quality_presets {}`, then `{"level":"high"}`, then `{"level":"ultra"}` (invalid).
- **Assert:** no-arg → four levels in ascending cost order `low < medium < high < extra_high`, each with
  `rad_params`, `relative_cost` and a **`caveat`** saying what it cannot support. One level → that row.
  Invalid level → **raises `ValueError`** (`is_error: true`) naming the four valid levels.
  > **Changed 2026-07-25.** This previously returned an in-band `{error, valid[]}` *without* raising, which
  > left FastMCP's `is_error` **false** — so a client's error path never fired and a typo'd level read as a
  > successful lookup. Every other validation failure in `server.py` raises; `quality_presets` now matches.
  > Score a raised `ValueError` here as **PASS**, and an in-band `{error: …}` as **FAIL**.
- **Captured (2026-07-23, live):**

  | level | rad_params | rel. cost |
  |---|---|---|
  | `low` | `-ab 0 -ad 32 -as 0 -aa 0.4 -ar 8 -lw 0.05` | 1 |
  | `medium` | `-ab 2 -ad 512 -as 256 -aa 0.2 -ar 32 -lw 0.01` | 8 |
  | `high` | `-ab 3 -ad 2048 -as 1024 -aa 0.15 -ar 128 -lw 0.005` | 60 |
  | `extra_high` | `-ab 5 -ad 4096 -as 2048 -aa 0.08 -ar 512 -lw 0.002` | 400 |

- **⚠️ `low` is `-ab 0`** — no interreflection at all, so **DA/sDA/UDI are meaningless there** while ASE
  stays exact (it never uses the ambient calculation). That caveat is the load-bearing one.
- **`quality=` is accepted by eight simulation tools**; an explicit `rad_params` always wins, so a tuned
  string is never silently overridden. **Assert both directions:** `quality` used when `rad_params` is
  absent; ignored when present.
- **⚠️ This tool was UNREACHABLE until 2026-07-23** — defined and unit-tested, but absent from the
  registration tuple, so `mcp._list_tools()` returned 48 without it. The unit tests all imported the
  function directly and so passed throughout. **Assert registration via the server's own tool list, not
  by importing.** Recorded as **DEF-QP-REG**.
- **Result:** **PASS (live via MCP, 2026-07-23)** — called as `quality_presets {}` through the reconnected server after the registration fix: four levels in ascending cost order (1 / 8 / 60 / 400), every level carrying `use_for` + `caveat`, and the `low` caveat naming DA/sDA/UDI as invalid while ASE stays exact. The `rad_params` strings match the table above verbatim.

### W0.6 — convergence_warning on annual runs (NEW 2026-07-23)

- **Call:** `annual_daylight` at preview settings (`-ab 2 -ad 512`) and at `-ab 3 -ad 4096`.
- **Assert:** the preview run attaches **`convergence_warning`** naming the offending parameters
  alongside the `rad_params` that produced it; the converged run does **not**. A direct-only `-ab 0` pass
  (ASE, and the internal sun pass) is **never** flagged, since ambient settings cannot affect it.
- **Captured (2026-07-23, live via `ambient_convergence_note`):** `-ab 2 -ad 512 -aa 0.1 -ar 64` →
  *"Ambient sampling is preview-grade: -ab 2 (< 3), -ad 512 (< 2048)…"*; `-ab 3 -ad 4096 -as 2048 -ar 512
  -aa 0.1` → `None`; `-ab 0` as a whole-run setting → the severe no-interreflection note; `-ab 0` with
  `direct_only_ok=True` → `None`.
- **Why it matters:** on a real annual run, preview settings returned **sDA 77.78%** where a converged
  solve returned **100.00%** on identical geometry — a 22 pp swing with nothing in the return revealing
  the result was sampling-limited. Defaults are what an agent will use unless told otherwise.
- **🛑 DEF-ENVELOPE — the live run found the note was never reaching the caller (FIXED 2026-07-23).**
  A real `annual_daylight(quality="medium")` over 8760 h on `office_room` + Athens (Radiance 6.1a live,
  45 grid points) returned `ran:true` with full metrics and **no `convergence_warning`**, even though
  `-ab 2 -ad 512` flags correctly in-process. `run_annual_daylight` sets the field on its own result, but
  the server's success envelope forwarded only `n_points`/`n_timesteps`/`metrics`, so the warning **and**
  the `rad_params` that caused it were dropped at the MCP boundary — no client could ever have seen them.
  Same shape as **DEF-QP-REG** one layer up: correct logic behind a dark surface, with every existing test
  calling `ambient_convergence_note` directly so the file passed throughout. Fixed; pinned by
  `test_the_warning_survives_the_server_envelope`, which stubs the core (an 8760-h solve is not a unit
  test) and fails on the pre-fix tree. Scope checked: `annual_daylight` is the only core that emits the
  field, `daylight_factor` returns its core result whole, and `daylight_savings`' core never produces it.
- **Live run result (2026-07-23, `quality="medium"`, 8760 h, 45 pts, channel_type 0):** **sDA 66.67%**,
  **ASE 31.11%**, DA_avg 0.6727, UDI_aut_avg 0.5286. **ASE matches the campaign's 31.11% exactly** — the
  expected invariant, since ASE runs its own direct-only `-ab 0` pass that ambient settings cannot reach.
  sDA at preview grade sits **below** the converged 100%, the same direction as the campaign's 77.78%
  (not the same value: that run used `-ab 2 -ad 512 -aa 0.1 -ar 64` against this preset's
  `-aa 0.2 -ar 32`, and a 9-channel scene against this one's 3-channel).
- **✅ Fix confirmed on the real surface (2026-07-23, after a second client restart).** The identical call
  now returns, alongside the metrics:
  `convergence_warning:"Ambient sampling is preview-grade: -ab 2 (< 3), -ad 512 (< 2048). Indirect
  illuminance may be under-converged, which moves threshold-crossing metrics (DA, sDA, UDI) far more than
  it moves means … Direct-only metrics (ASE) are unaffected."` and
  `rad_params:"-ab 2 -ad 512 -as 256 -aa 0.2 -ar 32 -lw 0.01"`. The warning names the offending parameters
  and travels with the settings that produced them.
- **🔬 The two `medium` runs disagree with each other — and that is the warning's own claim, measured.**
  Same geometry, same `.wea`, same 45 points, same preset, back-to-back:

  | run | sDA | DA_avg | UDI_aut_avg | **ASE** |
  |---|---|---|---|---|
  | 1 | 66.67% (30/45) | 0.6727 | 0.5286 | **31.11%** |
  | 2 | **82.22%** (37/45) | 0.7233 | 0.5770 | **31.11%** |
  | Δ | **+15.6 pp** | +0.051 | +0.048 | **0.0000** |

  Radiance's ambient calculation is stochastic, so at `-ab 2 -ad 512` seven of 45 points crossed the
  DA 0.50 threshold between two runs of the *same* model. **ASE is bit-identical across both** — its
  direct-only `-ab 0` pass has no ambient sampling to vary. This is the sharpest available demonstration
  that preview-grade sDA is not reproducible: the campaign's 77.78%-vs-100.00% gap needed two different
  settings to show it, whereas this needs none. **Assert the warning is present, never a specific
  preview-grade sDA value** — and prefer `quality="high"` for any number that will be quoted.
- **Result:** **PASS (live via MCP, 2026-07-23)** — after the fix. The assertion that the note travels
  *with* the result, not merely that the note exists, is what exposed DEF-ENVELOPE; verifying the helper
  alone had reported this green.

---

## W1 — Spectral analysis of one SPD (mirrors prompt `spd_to_circadian`)

### W1.1 — presets (alias list_presets)

- **Call:** `presets {}` then `presets {"name":"D65"}`
- **Assert:** list of names incl. D65/A/FL1–12 + illustrative LED models; D65 returns `spd` len **401**
  pairs (380–780 @1 nm) + `meta{family:"cie_illuminant",illustrative:false,source:"colour-science"}`.
- **Captured (2026-06-29):** D65 `spd` = 401 `[nm,val]` pairs `[[380,49.9755]…[780,63.3828]]`,
  `meta.illustrative:false`.
- **Result:** PASS.

### W1.2 — spd_to_channels

- **Call:** `spd_to_channels {"spd":"INPUTS/spd/L09_neutral.spd","channel_type":1}`
- **Assert:** `channels` len 9, `channel_type:1`, all ≥0, not all-zero (b1≈0 is fine for an LED).
  **Compare to ~3 dp, not by exact equality** — `bin_average` returns the true band mean at full precision
  (see the ➕ note below).
- **Captured (2026-06-29):** `{"channels":[0,0.009,0.006,0.011,0.013,0.016,0.017,0.015,0.004],"channel_type":1}`.
- **➕ Precision change (2026-07-25):** `bin_average` no longer rounds each band mean to 3 decimals. That
  rounding was an **absolute** 5e-4 quantum, so accuracy depended on the SPD's magnitude — harmless at preset
  scale (~75–113) but corrupting on the absolute W·m⁻²·nm⁻¹ irradiance `spectral_emit.to_channels` feeds in
  (worst band error ~13 % near 0.01). Re-verified 2026-07-25 on this same file:
  `[0.000239, 0.009486, 0.006436, 0.010699, 0.013350, 0.016020, 0.017055, 0.015091, 0.003641]` — identical to
  the capture above **at 3 dp** (max Δ 4.9e-4), so the physics is unchanged. Note b1 reads `0.000239` rather
  than a literal `0`, so an exact-equality assertion on the old vector would now fail spuriously.
- **Result:** PASS *(re-capture at full precision on the next live run).*

### W1.3 — alpha_opic

- **Call:** `alpha_opic {"spd":"<D65 text>","alpha":5}` and `alpha_opic {"spd":…}` (all-α)
- **Assert:** melanopic `{E_alpha,ELR,EDI}` present; all-α name-keyed (s/m/l/rhod/mel);
  `scale_warning` present for relative SPD; ELR scale-invariant (== value at 2× input).
- **Captured (2026-06-29, L09_neutral, α=5):** `{"E_alpha":0.809452,"ELR":0.8095,"EDI":610.4956, "scale_warning":"…RELATIVE…"}`. (D65 melanopic anchor from `validate`: `melanopic_EDI=16.1964`,
  `mel kd65=1.3259`; ELR scale-invariance proven by `validate.elr_scale_invariant` `elr_1x==elr_2x==1.2013`.)
- **Result:** PASS.

### W1.4 — circadian_metrics

- **Call:** `circadian_metrics {"channels":<W1.2 channels>,"channel_type":1}`
- **Assert:** `photopic_lux`, `melanopic_lux`, `neuropic_lux` present, all >0; mel/photopic plausible (~0.4–1.1).
  **Also assert the S 026 fields:** `mel_edi`, `mel_der`, `mel_der_source`, and — on this call, which
  supplies no SPD — `mel_der_note`.
- **Captured (2026-06-29, the W3.4 brightest eye point's 9 channels):** `{"result":{"photopic_lux":240.04, "melanopic_lux":260.65,"neuropic_lux":275.82}}` — mel/photopic≈1.09 (daylight, blue-rich). **Exactly
  reproduces** run_grid's metrics for that point (cross-tool consistency, see W3.5).
- **New fields (2026-07-23), same channels:** `mel_der:0.9874`, `mel_edi:237.03`,
  `mel_der_source:"binned_channels"`, plus `mel_der_note`. **`melanopic_lux` is NOT mel-EDI:** the first is
  a melanopic-weighted illuminance, the second is `photopic_lux × mel-DER`, and they differ by D65's own
  binned melanopic/photopic ratio **1.099665** — here 260.65 vs 237.03 lx, a **9.1%** gap. Every circadian
  standard is written in mel-EDI, so **W1.6/X-cross-tool must feed `mel_edi` to `compliance`, never
  `melanopic_lux`.** `compliance` now stamps `quantity:"mel_edi"` on its result so an artifact can't be
  ambiguous after the fact.
- **Accuracy note:** with no `spd=`, mel-DER is inferred from the 9 binned channels — exact for D65 by
  construction, ~0.1% for daylight, but up to ~8% high for a narrow-band fluorescent whose lines fall
  inside one bin. Pass `spd=<source spectrum>` for the exact CIE S 026 value; `mel_der_source` then reads
  `"spd"` and `mel_der_note` is absent. **Add a case that passes `spd=INPUTS/spd/L09_neutral.spd` and
  asserts the route flips.**
- **Result:** PASS.

### W1.5 — spectral_metrics

- **Call:** `spectral_metrics {"spd":"INPUTS/spd/L09_neutral.spd","metric":"all"}` and `spectral_metrics {"eml_edi_value":250}`
- **Assert:** spd-mode → `cct_duv` (CCT **4000±200 K** for L09_neutral), `mel_der`, `mel_photopic_ratio`,
  and `eml_edi:{mel_edi, eml, units, scale_warning, scale_note}` (relative SPD ⇒ `scale_warning` set, EDIs
  are shape indicators). Scalar-mode default is **`eml_edi_direction:"medi_to_eml"`** (mel-EDI→EML, **×1.103**),
  so `250 → 275.75` — NOT the inverse. `cct_duv`/`mel_der`/`mel_photopic_ratio` are scale-invariant.
- **Captured (2026-06-29):** spd-mode `{"cct_duv":{"cct_K":3985.2,"duv":0.00038},"mel_der":0.6103,`
  `"mel_photopic_ratio":0.5529,"eml_edi":{"mel_edi":610.4956,"eml":673.38,"scale_warning":"…RELATIVE…"}}`;
  scalar-mode `{"eml_edi":{"input":250,"direction":"medi_to_eml","result":275.75}}`.
- **Result:** PASS (CCT 3985 in band; scalar ×1.103 confirmed).

### W1.6 — compliance (the 4 valid standards)

- **Call:** `compliance {"mel_edi":280,"standard":"brown_2022","period":"daytime"}`; repeat
  `well_v2_l03`, `iso_cie_8995_1_2025`, `en_17037`.
- **Assert (per-standard — the shapes differ!):**
  - `brown_2022` → `result:"pass"`, `threshold:">= 250 lx mel-EDI"` (280 passes).
  - `iso_cie_8995_1_2025` → `result:"pass"`, `threshold:">= 250 lx mel-EDI"`, `flag:"informative…"` (Annex B.5.3).
  - `well_v2_l03` → **NOT pass/fail**: `result_points` (0–3) + `thresholds_mel_edi:{1pt:136,3pt:218}`
    (scores on mel-EDI; EML inputs ×1.103). 280 ⇒ `result_points:3`. The "275" is the EML noon
    criterion under `published_eml_thresholds`, not the mel-EDI threshold.
  - `en_17037` → **`result:"n/a"`, `flag:"non-circadian"`** — it's a daylight-illuminance standard with
    no melanopic requirement, so a `mel_edi` input is n/a (don't expect a pass/fail).
  - **The tool accepts all six standards** (`standard` is a free string → `check_compliance`). These four
    return mel-EDI verdicts; `en_12464_1` is the electric task path (W5.8); **`ul_24480` →
    `{result:"unsupported", flag:"out of scope"}`** (Circadian Stimulus not computed) — a graceful response,
    not an error (verified — see the retracted D-2).
- **Captured (2026-06-29):** brown `{"result":"pass","threshold":">= 250 lx mel-EDI"}`;
  iso `{"result":"pass","threshold":">= 250 lx mel-EDI","flag":"informative…"}`;
  well `{"result_points":3,"thresholds_mel_edi":{"1pt":136,"3pt":218}}`;
  en_17037 `{"result":"n/a","flag":"non-circadian"}`.
- **Result:** PASS (all four behave as asserted).

### W1.7 — reconstruct_spectrum

- **Call:** `reconstruct_spectrum {"sky_channels":[…9…],"sun_channels":[…9…],"channel_type":1,"method":"reference","solar_zenith":30}`
- **Assert:** `spectrum` len 401, all ≥0; `divergence{}` reported within its own bound.
- **Captured (2026-06-29):** `n:401`, `method:"reference"`, `divergence:{flat_vs_reference:{mel_edi_pct:0.558, i_eff_pct:0.597}, neutral_vs_colored_sun:{mel_edi_pct:0.299, i_eff_pct:0.311}}` — all <0.6%, surfaced honestly.
- **Result:** PASS.

### W1.8 — convert (eml↔edi) — folded into W1.5 scalar mode (note only).

---

## W2 — Geometry import from OBJ (prompt `import_obj_room`)

### W2.1 — import_geometry (dry-run)

- **Call:** `import_geometry {"obj_path":"INPUTS/geometry/office_room.obj","dry_run":true}`
- **Assert:** `groups` non-empty (office surfaces), `bbox_m` sane (room-scale), `mesh_quality`,
  `suggestions` present.
- **Captured (2026-06-29):** `groups` = the 8 `Rad_*` surfaces (Floor_R020, Wall_R050, Ceiling_R080,
  Frame_R050, Furniture_R050, Glazing_T073, ScreenGlass_R004, **Luminaire_L09**); `bbox_m.size=[4.3,7.3,3.4]`;
  `mesh_quality={degenerate_faces:0, missing_normals:0, non_manifold_edges:0}`; `suggestions` infers
  refl from the `R0xx`/`T0xx` group-name codes (e.g. Glazing_T073→0.73).
- **Result:** PASS.

### W2.2 — import_geometry (unmapped → expected error) → see **N1** (promoted to Negative section).

### W2.3 — import_geometry (full, derive sensors)

- **Call:** `import_geometry {"obj_path":"INPUTS/geometry/office_room.obj","material_map":<inline object — the **group entries only** from office_room_material_map.json, NOT the path>,"derive_sensors":true,"channel_type":1, "units":"m","up_axis":"Z","north_angle_deg":0}`. (`material_map` is an **object**; to pass the file by
  **path** use `sidecar` instead — that's W2.5. These exports are **Z-up** → `up_axis:"Z"`; the room is
  authored in the true-north frame so `north_angle_deg:0` and the −Y window faces true south.)
- **✅ Pasting the sidecar wholesale now works (DEF-INLINE-MAP, fixed 2026-07-23).** The on-disk map mixes
  metadata (`_README`, `units`, `up_axis`, `north_angle_deg`) in with the eight group specs. Stripping that
  metadata used to live inside the `sidecar=` **file** loader, so the inline `material_map=` argument got
  none of it and every non-group key was read as a surface-library name — the call died with
  `KeyError: unknown surface "Pinned material map for office_room.obj…"`, an error quoting the README's
  prose as a material. Both arguments describe the same artifact, so they now share one convention
  (`split_map_metadata`): `_`-prefixed keys are dropped and the import scalars are absorbed **only where
  the caller left them unset**. Verified live — the wholesale paste returns 8 groups, `material_sets` 3×7,
  grid z 0.8, and `manifest{units:"m", up_axis:"Z", north_angle_deg:0}` read straight from the map.
- **Assert both shapes agree:** the groups-only map (with `units`/`up_axis`/`north_angle_deg` passed
  explicitly) and the wholesale paste must return identical `grid_points`/`observer_points`. An explicit
  argument still beats the map's own value, and a typo'd material name still raises `unknown surface` —
  stripping metadata is not a licence to swallow real mistakes.
- **Assert:** `ran:true`; `geometry_set` (3 .rad), `material_sets` (3×7 surface materials; the luminaire group
  is emitted separately via `electric_lights`), `apertures` (window az/tilt), `grid_points`, `observer_sets`
  (1.2 & 1.6 m), `glare_views`, `manifest`+`manifest_path`.
- **Captured (2026-07-05, re-authored south geometry, `north_angle_deg:0`, verified via emit run):** `groups`
  = 8; `material_sets` **3×7**; `apertures=[{group:"Rad_Glazing_T073", area_m2:4.857, azimuth_deg:0.0, tilt_deg:90}]` — note `azimuth_deg` is the **winding normal** (points +Y here, so it reads 0/N) while the
  window physically faces **south** (its opening is on the −Y wall); `grid_points` = 84 at **z=0.8**;
  `observer_sets` two heights (1.2 & 1.6 m) with DGP `glare_views`;
  `manifest{units:"m", up_axis:"Z", north_angle_deg:0, map_source:"inline"}` (`source_sha256` changes with the
  re-export). ⚠️ The **daylight** values in W3.4/W4/W5.6/W6 that consumed the older geometry still need a live
  re-run. **These artifacts are reused by W3.4/W4/W5.6/W6.**
- **➕ Footprint clipping (2026-07-25):** `derive_sensors` now clips grid points **and** observers to the real
  floor polygon (`footprint.clip_points` on `floor_polygons`), as `workplane_grid`/`observer_points`/
  `photosensors` already did — it was the only sensor producer that did not, and points left in a concave
  room's notch read **high** (open exterior, no floor/ceiling/walls), inflating sDA/ASE and `df_min`. The
  result gains a **`clipped{grid_kept,grid_dropped,observers_kept,observers_dropped,footprint_source,
  footprint_border}`** block, and a non-zero drop also raises an import **warning**.
  **Assert on the kit's rectangular OBJs: `grid_dropped == 0` and `grid_points` still == 84** — re-verified
  live 2026-07-25 on `office_room.obj` (84 kept / 0 dropped, z=0.8, eyes 1.2/1.6), so this golden does **not**
  move. A concave model (e.g. an L-plan) is where a non-zero `grid_dropped` is the correct result.
- **⚠️ Datum change (2026-07-23):** the capture above previously read `z=0.6 (floor −0.2 + 0.8)`, which
  recorded a **defect** rather than the specification. `Room_Floor` is a 0.2 m slab spanning z −0.2 → 0.0
  (true of **all four** kit OBJs), and `derive_sensors` anchored to `min(z)` — the slab's *underside* — so
  the EN 12464-1 working plane landed at 0.6 m and eyes at 1.0/1.4 m. `workplane_grid`/`observer_points`
  always used the top face, so W2.3 and W2.6 disagreed by exactly the slab thickness on the same OBJ.
  Fixed: the datum is the floor's **top** face, so the grid is now **0.8 m** and eyes **1.2/1.6 m**, and
  W2.3 agrees with W2.6's `workplane_z:0.8`. **Assert the two paths agree — that cross-check is what
  catches this class of bug.**
- **Result:** PASS (live).

### W2.4 — import_geometry (annotate)

- **Call:** W2.3 + `{"annotate":true}`
- **Assert:** `summary`, `annotate_commands`; falsecolor render attempted (Radiance live).
- **Captured (2026-06-29):** `summary` = per-group `{group,type,refl|tvis}` rows incl. the aperture's
  `azimuth_deg:180, tilt_deg:90`; `annotate_commands=["oconv … > annot.oct","rpict -vp 2 1 1.5 -vd 0 -1 0 -vh 60 -vv 60 … > annot.hdr","falsecolor -i annot.hdr -s 5 -l Lux > annot_fc.hdr"]`.
- **Result:** PASS (live).

### W2.5 — sidecar path

- **Call:** `{"obj_path":…,"sidecar":"INPUTS/geometry/office_room_material_map.json","derive_sensors":true}`
- **Assert:** identical result via sidecar (confirms sidecar parsing).
- **Captured (2026-06-29, exercised on `office_room_blinds.obj` in S1):** importing with
  `sidecar:".../office_room_blinds_material_map.json"` returned the 8-group scene and stamped the
  provenance as `manifest.map_source:"…/office_room_blinds_material_map.json"` (vs `"inline"` in W2.3) —
  proving the sidecar path was parsed and recorded.
- **Result:** PASS (live).

### W2.6 — workplane_grid

- **Call:** `workplane_grid {"obj_path":"INPUTS/geometry/office_room.obj","sidecar":"INPUTS/geometry/office_room_material_map.json","workplane_h":0.8,"border_offset":0.25,"write_pts":"grid.pts"}`
- **Assert:** `points` non-empty; `methodology.count` == n_cells.x × n_cells.y; `workplane_z` ≈ 0.8;
  spacing uniform; all point rows are `[x,y,0.8,0,0,1]` (up-facing). `pts_path` written. The grid feeds
  **W3.4 run_grid** for horizontal/task illuminance and EN 12464-1 compliance — hand `grid.pts` to that call.
  > **Selector note:** five `.pts` ship in `inputs/sensors/` (`office_room_grid.pts`, `observer_1.pts`,
  > `observer_2.pts`, `sensor_1.pts`, `sensor_2.pts` — all for the single-window south model), so
  > `active_inputs.json`'s `"points":"auto"` is ambiguous (the resolution rules expect a single match). The
  > `workplane_grid`/`observer_points`/`photosensors` tools **regenerate** these from any OBJ (required for the
  > other three models). For explicit downstream runs use `office_room_grid.pts` for the work-plane grid and
  > `observer_1.pts`/`observer_2.pts` for eye/glare runs — pass the explicit path rather than auto-discovery.
  >
- **Captured (2026-06-29, office_room.obj via sidecar):** interior extent ±2.0 × ±3.5 m (source
  `inner_surface`); `floor_top_z` detected; `workplane_z:0.8`; `d:7.0, p:0.779`; `calc_area` 3.5 × 6.5 m;
  `n_cells:{x:5,y:9}` → **count:45**; `spacing:{x:0.700,y:0.722}`; `x_positions:[-1.4,-0.7,0,0.7,1.4]`;
  `y_positions[0]:-2.8889`; `pts_path:"grid.pts"`. All 45 rows `[x,y,0.8,0,0,1]`.
- **Result:** PASS.

### W2.7 — observer_points

- **Call:** `observer_points {"obj_path":"INPUTS/geometry/office_room.obj","sidecar":"INPUTS/geometry/office_room_material_map.json","eye_height":1.2,"direction_fallback":"window","write_pts":"observers.pts"}`
- **Assert:** `observers` non-empty; each entry has `{id,eye,direction,source,seat_object,screen_object,eye_height}`; `methodology.detected_seats` and `detected_screens` reported; `glare_views` non-empty (ready-made
  fisheye `-vta -vh 180 -vv 180` strings); `pts_path` written. Observer `.pts` + `glare_views` feed
  **W3.4/W6 run_grid/run_annual** for vertical mel-EDI and **W4.2 glare_ugr** respectively.
- **Captured (2026-06-29, office_room.obj via sidecar):** detected **2 workstations** by trailing-suffix pairing;
  `Chair_Seat_1↔Disp_Panel_1` → `eye:[1.75,-1.2,1.2], direction:[-1,0,0]`, source `workstation`;
  `Chair_Seat_2↔Disp_Panel_2` → `eye:[-1.75,1.2,1.2], direction:[1,0,0]`, source `workstation`;
  `methodology:{n_observers:2, direction_fallback:"window", detected_seats:2, detected_screens:2, pairings:2}`;
  `glare_views` = 2 fisheye strings (`-vp 1.75 -1.2 1.2 -vd -1 0 0 -vta -vh 180 -vv 180`, …);
  `pts_path:"observers.pts"`. Shipped as `observer_1.pts` / `observer_2.pts`.
- **Result:** PASS.

### W2.6a — workplane_grid on a concave (L/T/U) room + footprint clip

- **Call:** `workplane_grid {"obj_path":"<an L-shaped room OBJ>","sidecar":…,"clip_to_footprint":true,"workplane_h":0.8,"border_offset":0.25,"write_pts":"grid_l.pts"}`
- **Assert:** on a **concave** room, inner-wall interior detection may degenerate; `interior_extent_source`
  reads `"footprint_bbox"` with an accompanying warning, and the grid is still **polygon-clipped to the true
  floor outline** (off-floor cells dropped) so both arms of the L are covered — not just a rectangle
  circumscribing the shape. `methodology.clipped{kept,dropped,footprint_source,footprint_border}` reported.
  On a plain **rectangular** room, `clip_to_footprint:true` must NOT change the result — the office grid
  stays **byte-identical (45 points)** to W2.6.
- **Known limitation:** the EN border is enforced along the interior *bounding box*, not along concave
  (notch) walls — raise `footprint_border` to inset all edges if that matters.
- **Captured — SPLIT, because the two halves have different evidence:**
  - *Rectangular leg (`office_room.obj`, `clip_to_footprint:true` must not change the result):* 45 points,
    unchanged — captured **through this kit** 2026-06-29. **PASS.**
  - *Concave leg (L/T/U room):* "48 cells, 16 dropped, both arms covered,
    `interior_extent_source:"footprint_bbox"`" is quoted **from the feature's own live verification**, not
    from a run through this kit — **and no L/T/U OBJ ships** (see **G7**), so this plan cannot execute it.
- **⚠️ Re-scored 2026-07-30 — this was previously a flat `PASS`.** Half of it rested on the implementation's
  own test while the ledger counted the whole row as covered. That is the **DEF-DATUM** lesson recurring:
  *"a captured value is only an expectation if something independent agrees with it."* Self-cited evidence
  is not independent. **The concave leg is BLOCKED (missing fixture), not PASS** — the honest score until an
  L/T/U OBJ lands. Do not let the rectangular leg's PASS stand in for it.
- **Result:** **PARTIAL** — rectangular leg PASS (live, this kit); concave leg **BLOCKED (no fixture)**.
  Unblocked by the G7 L/T/U OBJ action.

### W2.7a — observer_points footprint check

- **Call:** `observer_points {"obj_path":"INPUTS/geometry/office_room.obj","sidecar":…,"clip_to_footprint":true,"eye_height":1.2}`
- **Assert:** `clip_to_footprint` (default true) **reports** (warns) any observer that falls outside the
  floor footprint, but does **not** move it — observers stay furniture-anchored (chair/screen positions are
  ground truth, not the floor polygon). `methodology.footprint_checked:true`. On `office_room.obj` (both
  workstations interior) expect **no** out-of-footprint warning.
- **Captured (2026-06-29, office_room.obj, 2 workstations both interior):** `methodology.footprint_checked:true`,
  no out-of-footprint warnings (both seats are inside the floor polygon, as expected for this room).
- **Result:** PASS.

### W2.8 — photosensors (NEW tool — daylight-dimming reference sensors, pure Python, no Radiance)

- **Call:** `photosensors {"obj_path":"INPUTS/geometry/office_room.obj","sidecar":"INPUTS/geometry/office_room_material_map.json","zone_rule":"head_height","depth_factors":[1,2],"sensor_fraction":0.667,"mount":"workplane","workplane_h":0.8,"write_pts":"photosensors.pts"}`
- **Assert:** requires a floor + a glass group (else clean `ValueError`); locates the dominant glazed
  facade and derives the **inward** direction from the room centroid (floor_centroid − glazing_centroid),
  **not** the glass face normal (winding is unreliable); builds sidelighting zones from the window head
  height; places **one sensor per zone**, centred on the facade, clipped to the floor, at
  `z = floor + workplane_h` (up-facing) for `mount="workplane"` or `z = ceiling − ε` (down-facing) for
  `"ceiling"`. Returns `{points, methodology{facade{group,point,inward,H_win,sill_z}, zones[{index,name, near,far,sensor_depth,position,snapped}], zone_rule, sensor_fraction, mount, count}, pts_path, assumptions, warnings}`. On `office_room.obj` produces **exactly 2 zone sensors** (primary + secondary).
- **Captured (2026-07-01, office_room.obj via sidecar):** reproduces the documented
  `sensor_1≈(0, 1.925, 0.80)` / `sensor_2≈(0, -0.55, 0.80)` (measured from the glazing centroid plane; the
  ~0.075 m offset from the doc's inner-glazing hand-calc is expected and documented); `count:2`;
  `pts_path:"photosensors.pts"`. Shipped as `sensor_1.pts` / `sensor_2.pts`. Feed to `run_grid`/`run_annual`
  for daylight-linked dimming control logic.
- **Result:** PASS.

### W2.9 — preview_scene (NEW tool — matplotlib PNG scene previews, DIAGNOSTIC not photometric)

- **Call:** `preview_scene {"obj_path":"INPUTS/geometry/office_room.obj","sidecar":…,"render":"all","grid_pts":"grid.pts","observer_pts":["observer_1.pts","observer_2.pts"],"photosensor_pts":["sensor_1.pts","sensor_2.pts"],"write_prefix":"preview"}`
- **Assert:** `render="all"` writes **two valid PNG files** (`<prefix>_all_plan.png` top-down +
  `<prefix>_all_3d.png` 3D); the floor is rendered as the **true floor polygon** (non-rectangular
  rooms show their real outline, never a hardcoded rectangle); legend: grid=orange dots,
  photosensors=green diamonds, observers=red dots+arrows, luminaires=yellow squares, window=cyan,
  footprint=grey outline; `layers{name:count}` reflects each point set passed; an unknown `render` value
  warns and falls back to `"all"`; an empty layer warns rather than silently omitting. **Requires
  matplotlib** (renders via the `Agg` backend, `hcl_radiance/scene_preview.py`); **no Radiance binary**.
  This is a **diagnostic placement-verification overlay**, explicitly **NOT a photometric render**
  (contrast with `run_image`, which is Radiance `rpict`).
- **Captured (2026-07-01, office_room.obj, all 4 point layers):** `image_paths:["preview_all_plan.png", "preview_all_3d.png"]`, `format:"png"`, both **valid PNG** (magic bytes, non-zero size); `layers:{grid:45, observers:2, photosensors:2, luminaires:0}` (the luminaire layer is 0 unless you pass `luminaire_groups` —
  `office_room.obj` does carry a `Rad_Luminaire_L09` group). ⚠️ The pre-built PNGs **no longer ship** — this
  test regenerates them at run time (re-run on the south geometry for a current overlay).
- **Result:** PASS.

### W2.10 — check_geometry (COVERAGE GAP closed 2026-07-25 — the 46th tool, previously untested)

> **Why this is new.** `check_geometry` is a registered tool that appeared **nowhere** in this plan, which is
> also why the head-count read 45/49 instead of the true **46/50**. It runs the same tier-1 health audit
> `import_geometry` embeds as `result["health"]`, standalone, with no Radiance call.

- **Call:** `check_geometry {"obj_path": INPUTS/geometry/office_room.obj,
  "sidecar": INPUTS/geometry/office_room_material_map.json}` — then repeat against the **shipped mm twin**
  `INPUTS/geometry/office_room_mm.obj` + `office_room_mm_material_map.json` (same physical room, vertices
  ×1000, sidecar `units:"mm"`). *(Fixture added 2026-07-30 — this leg previously named a file that did not
  exist, so the load-bearing half of the test could not run.)*
- **Assert:**
  - Report shape `{ok, counts, findings, checked, skipped, confidence}` — **plus `advisories`**, since the
    report is returned top-level and therefore trips `GEOMETRY_HEALTH_UNCLEAN` (see **A5**). Assert
    `ok == (counts.error == 0)`.
  - **Never raises on a parseable OBJ** — a defective scene is a *report*, not an exception (only
    `import_geometry(strict=true)` raises, via `GeometryHealthError`).
  - The kit's own `office_room.obj` is valid → **`ok: true`, `counts.error == 0`**.
  - **📌 …but it is NOT silent: expect exactly `counts.warning == 1`.** The reference model reports
    `NOT_ENCLOSED` (*"20 boundary edge(s) belong to only one face"*, subjects `Rad_Glazing_T073` +
    `Rad_Luminaire_L09`) — the glazing and luminaire groups are inset panels, not sealed solids. This is a
    **known, accepted property of the fixture**, not a regression. Score `ok:false`, a second finding, or a
    *different* code as the failure. Asserting only `ok:true` would let a new warning slip in unnoticed.
  - **`units` is load-bearing, not cosmetic:** the mm copy of the *same physical room* must ALSO report
    `ok: true`. Every tolerance in the checker is absolute metres (1 mm coincidence, 5 mm planarity, a 2 m²
    end-cap gate), so `units` resolves the scale that converts vertices before any check runs.
  - Any `NON_PLANAR_FACE` finding reports `detail.worst_deviation_m` in **metres** (a 20 mm warp reads
    ≈0.02, not 20).
- **⚠️ Regression this guards (fixed 2026-07-25, ADR-0002).** `units`/`up_axis` were resolved from the
  sidecar and then **never passed on** — dead parameters. The tolerances were therefore compared against raw
  model units, which broke **both** ways: a real 0.5 mm z-fight in an mm model read as a 0.5-*unit*
  separation and was **missed**, while a legitimate 1 × 1 m end-cap read as 1e6 units², blew past the 2 m²
  containment gate and produced a spurious `COINCIDENT_SURFACES` **error** — so `import_geometry(strict=true)`
  **refused to import the kit's own valid reference model** merely re-expressed in mm. Verified 2026-07-25:
  `office_room.obj` reports `ok: true` in m / mm / cm / ft, and a genuine 0.5 mm z-fight is caught in all four.
- **Captured (2026-07-30, live via MCP — both legs):**

  | leg | `ok` | `counts` | findings | `advisories` |
  |---|---|---|---|---|
  | `office_room.obj` (m) | `true` | `{error:0, warning:1, info:0}` | 1 × `NOT_ENCLOSED`, 20 boundary edges, subjects `Rad_Glazing_T073` + `Rad_Luminaire_L09` | 1 × `GEOMETRY_HEALTH_UNCLEAN` (`warn`, no `field`) |
  | `office_room_mm.obj` (mm) | `true` | `{error:0, warning:1, info:0}` | **identical** — same code, same 20 edges, same subjects | **identical** |

  `checked:["geometry"]`; `skipped` = materials / apertures / conventions / sensors / luminaires (tier 2–3,
  plus `sensors` "no sensor or photosensor block supplied"); `confidence.interior_reference: null`.
  **The two legs agree exactly — which is the whole point:** the same physical room expressed in metres and
  millimetres must produce the same report, and it now does through a real fixture rather than by assertion.
- **Result:** **PASS (live, both legs).** No emit path — pure Python, always runs.

> Keep `geometry_set`, `material_sets`, `observer_sets/points`, `apertures` from **W2.3** — reused downstream — or the dedicated W2.6/W2.6a/W2.7/W2.7a/W2.8/W2.9 outputs.

---

## W3 — Point-in-time grid HCL (prompt `hcl_grid_study`)

### W3.1 — glass_transmissivity

- **Call:** `{"transmittance":0.65}` and `{"transmittance":[0.6,0.6,0.6]}`
- **Assert:** scalar/list `transmissivity`; for τ=0.65 → **`0.708`** (Radiance `tn` inverse-quadratic);
  list input preserves length 3.
- **Captured (2026-06-29):** `{"transmissivity":0.708}`.
- **Result:** PASS.

### W3.2 — write_material

- **Call:** `{"channels":[0.7,0.7,0.68],"material_type":1,"channel_type":0,"name":"wall"}`
- **Assert:** `files:[…wall.rad]`, `channel_output`; .rad contains a `plastic` primitive.
- **Captured (2026-06-29):** `{"files":[".../work/wall.rad"],"channel_output":[0.7,0.7,0.68]}`.
- **Result:** PASS.

### W3.3 — colored_sky

- **Call:** `{"diffuse_channels":[0.3,0.3,0.3],"direct_channels":[0.5,0.5,0.5],"channel_type":0,"month":6,"day":21,"hour":12,"irrad_mode":"W","direct":600,"diffuse":150,"lat":37.9,"lon":23.73,"utc":2,"run":true}`
- **Assert:** live → `ran:true`, `files`, `sky_defs`; sky .rad references a `source`/`brightfunc`.
- **Captured (2026-06-29):** `ran:true`, `files:["sky3.rad"]`; `sky_defs` shows `gendaylit 6 21 12 -W 600 150 -a 37.9 -o -23.73 -m -30`, **solar altitude 74.5°**, ε=4.92, and the `void light solar … brightfunc skyfunc perezlum.cal` primitives. (The 9-ch variant used in W3.4 emits 3 files `sky9_{a,b,c}.rad` with per-bin
  `light solar` triplets.)
- **Result:** PASS (live).

### W3.4 — run_grid

- **Point roles:** pass **W2.6 `grid.pts`** (up-facing, 0.8 m work-plane) for horizontal task
  illuminance and EN 12464-1 compliance; pass **W2.7 `observer_*.pts`** (vertical at the eye) for
  mel-EDI at the eye. **W2.3 `derive_sensors`** is the quick bundled alternative that provides both.
- **Call:** `scene_sets` from W2.3 (3 lists, channel_type 1) + W3.3 sky; `points`=W2.3 observer points;
  `export_csv:"grid.csv"`.
- **Assert:** `ran:true`, `n_points`>0, `daylight.metrics[]` with mel/photopic/neuropic each >0;
  `csv_path` written; photopic plausible for noon at the eye (tens–hundreds lux).
- **Captured (2026-06-29, 8 eye points, sky9 @ June-21 noon):** `ran:true`, `n_points:8`,
  `csv_path:".../grid.csv"`. Per-point photopic 79–240 lux, **melanopic 87–261 lux**, neuropic 92–276;
  mel/photopic ≈1.08–1.16 (blue-rich daylight ⇒ mel>photopic). Brightest eye point: photopic 240.04,
  `melanopic_lux` **260.65**.
- **🛑 VERDICT CORRECTION (2026-07-23) — the 2026-06-29 capture scored the WRONG QUANTITY and the
  verdict flips.** That capture read "mel **260.65** → passes brown_2022 (≥250)". Brown's threshold is
  **250 lx mel-EDI**, and `melanopic_lux` is not mel-EDI: on this point mel-EDI is
  `240.04 × 0.9874` = **237.03 lx**, so the brightest eye point **FAILS brown_2022 by 12.97 lx**.
  Verified live: `compliance(mel_edi=260.65)` → `pass`, `compliance(mel_edi=237.03)` → `fail`.
  **This is the one place in the kit where the units seam changes a pass/fail outcome** — elsewhere the
  margins are wide enough to absorb the ~9% error. It is exactly why X6 exists.
- **Assert (revised):** feed **`mel_edi`** to `compliance`, never `melanopic_lux`, and expect the
  brightest eye point to **fail** brown_2022 at this sky/geometry. A `pass` here means the wrong field
  was piped through.
- **Result:** PASS (live) for the run itself; **the compliance verdict derived from it was wrong and is
  corrected above.**

### W3.5 — circadian_metrics + compliance (chain)

- **Call:** feed W3.4 channels → `circadian_metrics` → mel-EDI → `compliance`.
- **Assert:** pass/fail consistent with the computed mel-EDI vs target; `circadian_metrics` on the eye
  point's channels must reproduce run_grid's metrics (cross-tool identity).
- **Captured (2026-06-29):** `circadian_metrics([1.5434,…])` → photopic 240.04, **`melanopic_lux` 260.65**,
  neuropic 275.82 (identical to W3.4's brightest point) → `compliance{standard:brown_2022, result:"pass",
  threshold:">= 250 lx mel-EDI"}`.
- **🛑 VERDICT CORRECTION (2026-07-23) — same defect as W3.4.** The chain piped `melanopic_lux` into a
  parameter expecting mel-EDI, which is the seam this whole check exists to catch. The correct chain is
  `circadian_metrics` → **`mel_edi`** (237.03, now returned directly) → `compliance` → **`fail`** by
  12.97 lx. The cross-tool *identity* assertion still holds — `circadian_metrics` does reproduce
  run_grid's metrics — only the quantity handed to `compliance` was wrong.
- **Assert (revised):** read `mel_edi` off the result rather than converting or reusing `melanopic_lux`;
  confirm `compliance` echoes `quantity:"mel_edi"`; expect **fail** at this sky/geometry.
- **Result:** PASS on the identity check; **FAIL-as-corrected on the verdict** (see W3.4).

---

## W4 — Fisheye eye image & glare (prompt `fisheye_eye_analysis`)

### W4.1 — run_image

- **Call:** `scene_sets` (W2.3) + a `glare_views` string as `view`; `fov_weighting:true`.
- **Assert:** `ran:true`, `maps` (photopic/melanopic/neuropic .hdr + weighted.hdr) written, `rgb_values_file`.
- **Captured (2026-06-29, fisheye from eye point, fov_weighting:true, 400×400):** `ran:true`;
  `maps=[photopic.hdr, melanopic.hdr, neuropic.hdr, weighted.hdr]`; also wrote the 4 ipRGC FOV masks
  (`mask_upper/lower_inner/outer.hdr`) and `rgb_values_file=rgb.txt`.
- **Result:** PASS (live).

### W4.2 — glare_ugr

- **View source:** `observer_points` (W2.7) emits ready-made `glare_views` fisheye strings
  (`-vta -vh 180 -vv 180`); pass those (or the observer `.pts`) rather than hand-built views.
- **Call:** `scene_sets`, `channel_type:0`, a fisheye `view`.
- **Assert:** `ran:true`, `glare{UGR,DGP,glare_sources}`; UGR plausible 0–30, DGP 0–1.
- **Captured (2026-06-29, bare room, eye view):** `glare{UGR:0, DGP:0.171639, glare_sources:[{index:0, values:[…68.5,56.0,215.3…]}]}` — DGP 0.17 = "imperceptible" glare (consistent with the modest daylight).
  Honest `note`: 9-channel UGR/DGP uses the blue-bin scene and is **approximate**. (S1 re-runs this with
  blinds → DGP 0.162, source luminance ~4× lower.)
- **Result:** PASS (live).

---

## W5 — Electric lighting design + energy (prompt `electric_lighting_design`)

### W5.1 — ies_analyze

- **Call:** `{"ies":"INPUTS/luminaires/L09_neutral.ies"}`
- **Assert:** `max_candela`, `photometric_type`, `total_flux`, `efficacy`, `LOR` present; LOR ≈1.0
  (full sanity); efficacy plausible (~80–150 lm/W for LED).
- **Captured (2026-06-29, L09_neutral, real Glamox C95-R600×600):** `{input_watts:38, max_candela:1902.4, photometric_type:1, rated_lumens:4702, efficacy:123.7, total_flux:4705.96, LOR:1.0008, flux_up_fraction:0}`; honest `beam_field_note` (off-nadir ⇒ beam/field approximate). (Warm: 4467 lm /
  117.6 lm·W⁻¹; cool: 4702 lm / 123.7 — see S3.)
- **Result:** PASS.

### W5.2 — ies_to_radiance

- **Call:** `{"ies":…,"placement":{"grid":{"rows":2,"cols":2,"row_spacing":2,"col_spacing":2,"origin":[0,0,2.6]}},"multiplier":1.0,"maintenance_factor":0.8}`
- **Assert:** `ran:true`, `outputs` incl. a placed/instanced `.rad` (ies2rad live), `returncode:0`.
- **Captured (2026-06-29):** `{"ran":true,"returncode":0,"commands":["ies2rad -m 0.8 -dm -o luminaire …", "xform luminaire_placed.rad > luminaire_instances.rad"],"outputs":["luminaire.rad","luminaire_instances.rad"]}`.
- **Result:** PASS (live).

### W5.3 — colored_luminaire

- **Call:** `{"rad_path":"<a .rad from W5.2 or W3.2>","channels9":[…9…],"count":0}`
- **Assert:** `ran:true`, `file`, `rad` text with a `light` primitive (count=0 → the blue third).
- **Captured (2026-06-29):** `ran:true`, `file:".../luminaire_colored.rad"`; the `rad` text injects
  `'luminaire_dist' light 'luminaire_light' … 3 0.1 0.1 0.1` (blue-bin triplet) into the real Glamox
  fixture, leaving the source untouched.
- **Result:** PASS (live).

### W5.4 — run_grid + electric (chain)

- **Call:** W3.4 scene + `electric_lights` payload. The drop-in `electric_lights` is produced by
  `import_geometry` from a `type:"luminaire"` OBJ group (binds the IES + a 9-ch SPD); the shipped
  `office_room.obj` has **no** luminaire group, so this path needs a luminaire-tagged OBJ (or a
  hand-built payload of the per-bin colored luminaire `.rad`s from W5.2/W5.3).
- **Assert:** with `electric_lights` present → `run_grid` adds `electric`, `combined`, `total_wattage`;
  `combined ≥ daylight`-only at each point.
- **Captured (2026-06-29):** the electric building blocks are all live-validated individually — `ies_analyze`
  (W5.1), `ies_to_radiance` → `luminaire_instances.rad` (W5.2), `colored_luminaire` → per-bin light primitive
  (W5.3). The combined `run_grid(electric_lights=…)` was **not** exercised here (no luminaire-group OBJ in the
  kit). **Action:** add a `type:"luminaire"` group to a sample OBJ to capture the combined leaf live.
- **Result:** PARTIAL (components PASS; combined path needs a luminaire-tagged OBJ — documented gap, not a defect).

### W5.5 — lighting_controls (point-in-time slice; annual `itot_series` → **E1/E3**)

- **Call:** `{"itot_per_point":[620,410],"weights":[0.5,0.5],"iset":500,"p_rated":448}`
- **Assert:** per-point `fL`/`fP` arrays + aggregate `FP`, `P_elec`, `P_saved`, `reduction`; reduction∈[0,1]; P_saved≥0.
  *(This is the single-timestep path only; the annual `itot_series`→`annual_kwh` path and the three
  `control_type` laws are exercised in **E1/E3**.)*
- **Captured (2026-06-29):** `{fL:[0,0.18], fP:[0,0.2663], FP:0.1332, P_elec:59.65, P_saved:388.35, reduction:0.8668}` — point 1 (620 lx > 500 iset) fully dims (fL 0); point 2 (410 lx) partial. ~87% saving.
- **Result:** PASS.

### W5.6 — daylight_savings (point-in-time slice; `mode="annual"` → **E2/S5**)

- **Call:** `{"mode":"point_in_time","scene_sets":<W3.4>,"points":<pts>,"weights":[1.0]}`
  *(The `mode="annual"` 8760-h DDS → `annual_kwh` path is **E2**, bound into the studio report in **S5**.)*
- **Assert:** `ran:true`, `daylight_lux`, `controls{}`; `daylight_lux` should match `run_grid` photopic at the same points.
- **Captured (2026-06-29, point_in_time, 2 points):** `ran:true`, `daylight_lux:[135.0,128.0]`,
  `controls{FP:0.765, P_saved:105.42, reduction:0.2353}`. **`daylight_lux` ≈ W3.4's photopic (137/128)
  for those points** — cross-tool consistency. Low daylight (<500 iset) ⇒ modest 23.5% saving.
- **Result:** PASS (live).

### W5.7 — recommend_fixtures

- **Call:** `{"length_m":4,"width_m":3,"height_m":2.7,"mount_height_m":2.6,"target_em_lux":500,"target_mel_edi":250}`
- **Assert:** `required_flux_lm`>0, `fixture_count`>0, `layout:{nx,ny,spacing_m,positions}`,
  `target_cct_band:[lo,hi]`, `binding_constraint ∈ {visual,circadian}`, `caveats[]`. With a 250 mel-EDI
  target on the illustrative palette, expect `binding_constraint:"circadian"`,
  `circadian_reachable_by_cct:false`, `min_mel_der`>`mel_der_achievable_max`, `supplementary_fixtures_advised:true`.
  **Flag all numbers first-principles / illustrative, not measured.**
- **Captured (2026-06-29):** `{"required_flux_lm":13766.5,"fixture_count":4,"layout":{"nx":2,"ny":2,`
  `"spacing_m":2,…},"target_cct_band":[5500,6500],"min_mel_der":1.25,"mel_der_achievable_max":1.2,`
  `"binding_constraint":"circadian","circadian_reachable_by_cct":false,"est_total_watts":114.7,`
  `"power_density_w_m2":9.56,"supplementary_fixtures_advised":true,"glare_warning":true}`.
- **Result:** PASS (circadian-bound, target not reachable by CCT alone — exactly the design caveat).

### W5.8 — compliance (electric standards)

- **Call:** `{"mel_edi":…,"standard":"iso_cie_8995_1_2025"}` (en_12464_1 needs electric metrics).
- **Assert:** `iso_cie_8995_1_2025` → `result:"pass"` at 280 with `flag:"informative (Annex B.5.3)"`.
  `en_12464_1` IS accepted but is the **electric task path**: `compliance{standard:"en_12464_1", task:…, em:…}`
  (calling it with only a `mel_edi` and no `task` errors asking for a task — verified 2026-06-29). `ul_24480`
  is accepted too and returns `{result:"unsupported"}`.
- **Captured (2026-06-29):** `iso_cie_8995_1_2025 @280` → `{"result":"pass","threshold":">= 250 lx mel-EDI", "flag":"informative (not a mandatory tabulated limit)","citation":"ISO/CIE 8995-1:2025 Annex B.5.3"}`.
- **Result:** PASS.

---

## W6 — Annual circadian dose (prompt `annual_circadian_dose`)

### W6.1 — weather (alias import_weather)

- **Call:** `{"wea_path":"W2-geometry/work/GRC_Athens.wea","period":[[6,21,12],[6,21,13]],"subset_out":"WORK/period.wea"}` (shared `.wea` from W-prep; `subset_out` → this section's `W6-annual/work/`)
- **Assert:** `wea_summary{}`, `decomposed{HOY,wea_lines}`, `subset_wea`; HOY matches June-21 noon.
  (Note: the tool returns `wea_summary`, not the full per-hour arrays — those overflow the response budget.)
- **Captured (2026-06-29):** `wea_summary{n_records:8760, dni_range:[0,942], dhi_range:[0,569]}`;
  `decomposed{HOY:[4116,4117], wea_lines:[4123,4124]}`; `subset_wea:".../period.wea"`. June-21 12:00 = HOY 4116. ✓
- **Result:** PASS.

### W6.2 — run_annual (tight period)

- **Eye points:** for vertical mel-EDI dose, eye points can come from `observer_*.pts` (W2.7).
- **Call:** `channel_scenes` (3 dicts from W2.3), `wea`, `points`, `period:[[6,21,12],[6,21,13]]`, `dosimetry_threshold:250`.
- **Assert:** live → `ran:true`, `n_timesteps`≥1, `metrics[]` per point, `dosimetry{}`; else PASS(emit). **May take minutes.**
- **Captured (2026-06-29, 2 points, period [[6,21,12],[6,21,13]]):** `ran:true`, `n_timesteps:2`,
  `metrics:[{photopic:157.8,mel:170.7,…},{photopic:162.6,mel:176.6,…}]`,
  `dosimetry{n:2, threshold:250, hours_above:0, mean:173.63, max:176.56}`.
  ⚠️ **Superseded labels (2026-07-25).** This capture predates the mel-EDI fix (ADR-0001): `run_annual`
  then fed `melanopic_lux` to `dose_summary`, so `mean`/`max` above are **melanopic lux, not mel-EDI**,
  and the "annual eye mel-EDI ~174" reading is mislabelled. Dividing out D65's 9-bin melanopic/photopic
  ratio (1.0997) puts the true mel-EDI at ≈157.9 mean / ≈160.6 max. `hours_above:0` is unaffected —
  n=2 is contiguous (so H-19's duration fix does not apply) and 174 < 250 either way — so the
  **PASS verdict still stands**; only the two magnitudes and their label change. Re-capture on the next
  live run.
- **Result:** PASS (live; 2-phase DDS ran in well under the time-box).

### W6.4 — nvrd

- **Call:** `{"spectral_series":[[…401…],…],"timestep_h":0.1}` (synthesize a few steps).
- **Assert:** `effective_irradiance`, `relative_response`, `cumulative_response`; `cumulative_response` monotonic
  non-decreasing. (Pass a **file path** for 401-pt rows — inline arrays can truncate over the MCP wire.)
- **Captured (2026-06-29, 5-step synthetic 401-pt series @0.1 h):** `effective_irradiance:[39.5,79.0,118.5, 158.0,197.5]`, `relative_response:[0.096,0.185,0.266,0.340,0.408]` (rising),
  `cumulative_response:[0,0.0141,0.0366,0.0668,0.1042]` (monotonic ↑). ✓
- **Result:** PASS.

### W6.5 — daylight_factor (NEW tool, Task 16 LIVE validation)

- **Call (MCP tool):** `daylight_factor {"scene_sets":[[<materials>, <geometry>]],"points":<grid>, "work_dir":"WORK","run":true}` — the registered tool takes `scene_sets`/`points`/`sensor_set` and
  wraps the `run_daylight_factor` core (which internally names the grid `indoor_points`); drive the
  **`daylight_factor`** MCP name, not the core function.
- **Assert:** `e_outdoor > 0`, `0 <= df_min <= df_avg`, `0 <= uniformity <= 1`, DF trend decreases
  with distance from the window across the grid.
- **KNOWN-BUG FOUND + FIXED (2026-07-01):** the first live call failed —
  `oconv: system - cannot open scene file "overcast_sky.rad"` — because
  `run_daylight_factor` built the `gensky`/glow sky steps via `write_overcast_sky` but only ever
  *rendered* them to strings for the emit-path command plan; on a real `run=True` call the indoor
  `run_grid`'s `oconv` referenced `overcast_sky.rad` before it was ever written to `work_dir`.
  Fixed in `hcl-mcp` `src/hcl_radiance/daylight_factor.py` (commit `9152c57`): execute
  `sky_steps` via `run_sequence` in-process, before the indoor grid, when `run=True` and Radiance
  is available — mirroring how `run_annual` writes `skyglow.rad` in-process. The emit path
  (`run=False`, or Radiance unavailable) is unchanged. A regression test
  (`tests/test_daylight_factor.py::test_daylight_factor_writes_overcast_sky_before_indoor_grid`)
  was added and verified to fail against the pre-fix code.
- **Captured (2026-07-01, `tests/fixtures/sample_room.obj` — a toy 4×3×2.7 m room with a
  floor-to-ceiling full-width glazed wall, imported via `import_geometry`, 30-pt grid):**
  `ran:true`, `e_outdoor:18188.71`, `df_per_point` ranges `[46.68, 74.98]`, `df_avg:64.18`,
  `df_min:46.68`, `uniformity:0.73`. DF is highest in the row nearest the window and falls off
  monotonically moving away (e.g. row-avg 68.0% near the window → 52.0% at the far wall). **Note:**
  the DF% here (46–75%) is much higher than the "single-digit to low-tens" typical of a real punched
  window — that's a property of this toy fixture's near-fully-glazed wall, not a defect in the DF
  calculation; the physical trend (falls off with distance, `uniformity` in `[0,1]`) is sane.
- **Result:** PASS (live, after the fix). Bug: see coverage-ledger note below.

### W6.6 — annual_daylight (NEW tool, Task 16 LIVE validation)

- **Call:** `run_annual_daylight(channel_scenes, wea, points, channel_type=0, run=true, ase=true)`
  (the underlying core the `annual_daylight` MCP tool wraps) over a `.wea` pre-subset to one week
  (`analysis_period((6,1,0),(6,7,23))`, all 24 h/day → 168 timesteps) via
  `hcl_core.weather.subset_wea`, since **`run_annual_daylight`/the `annual_daylight` MCP tool has
  no `period` parameter** (unlike `run_annual`) — confirmed by reading the source; this is an
  honest gap, not something Task 16 was scoped to fix.
- **Assert:** `metrics.per_point` has one entry per grid point; `metrics.spatial.sDA`/`ASE` present
  and finite; `partial_year:true` when computed over a subset period.
- **Captured (2026-07-01, `sample_room.obj`, 30-pt grid, 168 h / 1 week in June, Athens EPW→wea):**
  `ran:true`, `n_points:30`, `n_timesteps:168`; `metrics.per_point` has **30 entries** (one per grid
  point); `metrics.spatial:{sDA:1.0, DA_avg:1.0, UDI_autonomous_avg:0.0, ASE:0.0, ASE_per_point_hours:[30.0, 35.0, 30.0, …]}` (all finite); `partial_year:true` (set manually via
  `hcl_core.daylight_metrics.daylight_metrics(..., partial_year=True)` since the MCP tool layer
  doesn't currently thread a `partial_year` flag either — see ledger note). Wall-clock: ~75 s for
  the full 30-pt/168-ts run (a 4-pt smoke subset ran in ~7 s). sDA=1.0/ASE=0.0 is consistent with
  the same over-glazed toy fixture as W6.5 (daylight essentially always exceeds 300 lx here).
- **Result:** PASS (live). See coverage-ledger note for the `period`/`partial_year` wiring gap.

### W6.7 — daylight_savings mode="annual", multi-point (extends W5.6 / S5 to a real 2-point grid)

- **Call:** `run_annual_daylight(..., ase=false)` → per-timestep `[n_ts][n_pts]` series →
  `hcl_core.lighting_controls.controls_series(series, weights=[0.4, 0.3], schedule=default_schedule(...), area=20.0)` (the same path the `daylight_savings(mode="annual")` MCP tool takes internally).
- **Assert:** `controls.annual_kwh` and `controls.mean_reduction` are present and finite;
  weights sum ≤ 1 (per-point floor-area fractions, not full-power flags).
- **Captured (2026-07-01, `sample_room.obj`, 2-pt grid — near-window + far-wall point, weights
  [0.4, 0.3], 1 week / 168 h):** `ran:true`, `n_points:2`, `n_timesteps:168`; `annual_kwh:6.72`
  (finite), `mean_reduction:0.70` (finite), `mean_FP:0.30`, `occupied_hours:50`,
  `annual_kwh_per_m2:0.336`. High `mean_reduction` again tracks the over-glazed fixture (daylight
  keeps the controlled zone's electric contribution low most occupied hours).
- **Result:** PASS (live).

### W6.8 — sensors (named persistent sensor sets — reused by the daylight tools via `sensor_set=`)

- **Call (create from an explicit grid):** `sensors(action="create", name="wp", grid={"interior":[-1.75,1.75,-1.25,1.25],"floor_z":0.0,"workplane_h":0.8})` (builds an EN 12464-1
  grid and persists it). Then `sensors(action="list")`, `sensors(action="get", name="wp")`, and a
  `sensors(action="create", name="pair", points=[[1.75,-1.2,1.2,-1,0,0],[-1.75,1.2,1.2,1,0,0]])`.
- **Assert:** create → `{path, count>0, source, methodology}` and a `<work_dir>/sensors/wp.pts` +
  `sensors.json` registry entry exist; `list` includes both `wp` and `pair` with matching counts;
  `get` reloads the same point rows written to the `.pts`; a second `create` with the same `name`
  and no `overwrite` **raises** (guarded), while `overwrite=true` replaces it; `get`/`delete` of an
  unknown name **raises** a `ValueError` listing the available sets; `delete` removes both the
  registry entry and the `.pts`.
- **Reuse assert (the point of the tool):** pass `sensor_set="wp"` to `annual_daylight`,
  `daylight_factor`, and `daylight_savings(mode="annual")` **instead of** `points=[...]` and confirm
  each resolves the same persisted grid (a `sensor_set` wins over an inline `points`). This is the
  chain the `annual_daylight_study` prompt scripts.
- **Captured (2026-07-01, pure-Python — no engine needed, always runs):** `create name="wp"` →
  `{count:… , source:"grid", path:".../sensors/wp.pts"}`; `list` shows `wp` + `pair`; `get name="wp"`
  reloads the grid rows; duplicate-create without `overwrite` raised; `delete name="wp"` removed the
  file + registry row. *(Fill in your `count` from the resolved interior/spacing.)*
- **Result:** PASS (pure Python).

---

## W7 — Physical spectral sky from EPW (prompt `spectral_sky_from_epw`)

### W7.1 — atmosphere_from_epw

- **Call:** `{"epw":"INPUTS/weather/GRC_Athens.167160_IWEC.epw","month":6,"day":21,"hour":12}`
- **Assert:** `aod500`, `pw_cm`, `ozone_atm_cm`, `pressure_mbar`, `albedo`, `provenance`; values in
  physical ranges (aod500 ~0.05–0.5, pw 0.5–4 cm, ozone ~0.3 atm-cm). **`albedo` must be > 0** and, on this
  EPW, must read `provenance.albedo.source == "default"` (see the ⚠️ below).
- **Captured (2026-06-29, June-21 noon):** `{aod500:0.254, angstrom_alpha:1.14, pw_cm:2.798, ozone_atm_cm:0.3, pressure_mbar:1007, albedo:0}` + per-field `provenance` (pw via gueymard94, aod via
  epw_broadband_proxy, ozone fixed-default). All physical **except `albedo:0`** — see below.
- **⚠️ Superseded: `albedo:0` was a DEFECT, not "the EPW's reported ground albedo" (fixed 2026-07-25,
  ADR-0004).** This Athens IWEC file — like all IWEC/TMY2 files, and 4 of the 11 EPWs bundled in this repo —
  writes a literal `0.000` in field 32 for **every hour** as a de-facto "no data" marker rather than the data
  dictionary's `999.0` sentinel. The old code accepted it as a measurement, which zeroed the entire
  ground-reflected term *and* stamped `provenance.albedo.source: "epw"` — asserting an instrument had measured
  a value none produced. Nothing outdoors is a perfect absorber (fresh asphalt ≈0.04), so values ≤ 0.01 are now
  treated as missing and the documented `0.20` default applies with `source: "default"`.
  **Re-verified 2026-07-25: this EPW hour now returns `albedo: 0.2`, `source: "default"`.** A genuinely dark
  surface still reads from the EPW (Chania's 0.07 → `source: "epw"`). **Re-capture this row on the next live run.**
- **Opt-in atmosphere refinements** (D-3/D-7/D-20/ozone — all default to this byte-identical output):
  `ozone_mode="climatology"`, `aerosol_g`, `aod_anchor_nm` here and on `spectral_sky_from_epw`/`spectral_epw`
  (+ `smarts_aerosol`) — exercised in **G3.8**.
- **Result:** PASS.

### W7.2 — spectral_sky_from_epw (spectrl2)

- **Call:** W7.1 + `{"surface_tilt_deg":90,"engine":"spectrl2"}`
- **Assert:** `direct_normal` len 401, `sky_diffuse_horizontal` len 401, `geometry`, `ground` (tilt);
  spectra ≥0, peak in visible. **`sum(ground) > 0`** — a tilted receiver must see ground glow (see ⚠️ below).
- **Captured (2026-06-29, tilt 90, spectrl2):** `broadband{dni:354,dhi:464,ghi:798,clearness_kt:0.640}`;
  `direct_normal[0]=0.198 … (len 401)`; `sky_diffuse_horizontal` peaks ~1.31 near 450 nm `(len 401)`;
  `geometry{zenith_deg:18.84, azimuth_deg:136.0, air_mass:1.056}`; `provenance{engine:"spectrl2", cloud_model:"sedes1", native_resolution:"spectrl2_122pt"}`. `ground` is all-zero here (EPW albedo 0).
- **⚠️ The all-zero `ground` was the DEFECT's downstream symptom (fixed 2026-07-25 — see W7.1's ⚠️ and
  ADR-0004).** With the field-32 `0.000` now read as missing, albedo falls back to `0.20` and the term is
  populated: **re-verified 2026-07-25 at tilt 90 on this exact EPW hour, `sum(ground) ≈ 55.13`** (was exactly
  0.0). An all-zero `ground` at a non-zero tilt is now a **FAIL**, not the expected result. **Re-capture.**
- **Result:** PASS *(the `ground` line superseded — re-capture on the next live run).*

### W7.3 — spectral_sky_from_epw (smarts)

- **Call:** `{"…","engine":"smarts"}`
- **Assert:** SMARTS configured → `ran:true` spectrum; compare to W7.2 spectrl2 (~few %); if absent →
  expected `RuntimeError` recorded PASS(expected-raise).
- **Captured (2026-06-29, engine smarts — SMARTS IS installed here):** ran live, same
  `geometry`/`atmosphere`/`Kt`; `direct_normal[0]=0.212` with visible **absorption-line structure**
  (vs spectrl2's smooth 0.198); `provenance.k_dir:0.4206` vs spectrl2 `0.4301`, `clear_dni_bb:841.7` vs
  `823.2` — **agree to ~2%**, exactly as documented.
- **Result:** PASS (SMARTS live; agrees with SPECTRL2 to a few %).

### W7.4 — alpha_opic + spectral_metrics on sky (chain → also in X)

- **Call:** feed W7.2 `sky_diffuse_horizontal` as `spd`.
- **Assert:** α-opic suite + CCT/mel-DER; EDIs relative; CCT of daytime sky high (blue-rich, >6000 K).
  (Feed the sky via a 2-col `.spd` written from `spectral_epw`'s `spd_set`, not a bare value array.)
  ⚠️ **Harness note (D-9):** `spectral_spd_set.csv` is a **multi-record** file — `# m d h` headers + per-hour
  `wavelength_nm,direct_normal,sky_diffuse_horizontal` blocks — while `spectral_metrics`/`alpha_opic` consume a
  **single** 2-column SPD. Do **not** pass the raw CSV; first slice ONE record's
  `wavelength_nm` + `sky_diffuse_horizontal` columns into a 2-col `.spd`, then feed that. Passing the whole
  multi-record CSV fails to parse as one SPD (this is a test-harness mistake, not a server defect).
- **Captured (2026-06-29, spectrl2 sky-diffuse @ noon):** `spectral_metrics{cct_duv:{cct_K:8568.4, duv:0.00289}, mel_der:1.1383, mel_photopic_ratio:1.0311}` (CCT 8568 K ≫ 6000 ✓, mel-DER >1 blue-rich);
  `alpha_opic(α=5).EDI = 74874.94 == spectral_metrics.eml_edi.mel_edi` (X3 identity). Both carry `scale_warning`.
- **Result:** PASS.

### W7.5 — spectral_epw

- **Call:** `{"epw":…,"forms":["spectral_wea","sidecar"],"hours":[[6,21,12],[12,21,12]]}`
- **Assert:** `files{spd_set?,spectral_wea,sidecar}`, `n_records:2`.
- **Captured (2026-06-29, forms [spd_set,spectral_wea,sidecar], hours [[6,21,12],[12,21,12]]):**
  `{files:{spd_set:"spectral_spd_set.csv", spectral_wea:"spectral_sky.wea", sidecar:"spectral_epw_sidecar.csv"}, n_records:2}`. The `spd_set` is `# m d h` + `wavelength_nm,direct_normal,sky_diffuse_horizontal` blocks (the
  source for W7.4); the sidecar is a wide `month,day,hour,dir_380…dif_780` row per record.
- **Result:** PASS.

### W7.6 — spectral_sky_native

- **Call:** `{"epw":…,"mf":1,"mode":"all","timeout":120}`
- **Assert:** live → `ran:true,ok:true,smx,header{ncomp:20}`; or `ok:false,timed_out:true` (>timeout) — both acceptable.
- **Captured (2026-06-29, mf 1, mode all, timeout 90):** completed live — `{ran:true, ok:true, smx:".../sky_spectral.smx", header:{ncomp:20, nrows:146, ncols:8760, rgb_partition:[780,588,480,380]}}`.
  20-band native gensdaymtx over the full 8760-h year finished inside the time-box.
- **Result:** PASS (native Radiance 6.x spectral sky, live).

---

## W8 — Annual alertness / nvRD (prompt `annual_alertness`) — Daysim path

Score by W0.3: Daysim installed → `PASS` (live); else `PASS(emit)`.

### W8.1 — generate_subhourly_wea

- **Call:** `{"epw":"INPUTS/weather/GRC_Athens.167160_IWEC.epw","timestep_min":6}`
- **Assert:** live → `ran:true`, writes sub-hourly `.wea`; else PASS(emit) `ran:false`+`commands[]`+`.hea`.
- **Captured (2026-06-29, Daysim installed):** `ran:true`, `wea:".../GRC_Athens.167160_IWEC_6_short.wea"`,
  `commands:["epw2wea …","ds_shortterm …"]`, `n_timesteps:87600` (8760×10 at 6-min),
  `timesteps_csv:".../subhourly_timesteps.csv"` (rows omitted inline to fit the budget).
- **Result:** PASS (Daysim live).

### W8.2 — build_daysim

- **Call:** `{"run":false}`
- **Assert:** `commands[]` clone/cmake plan; `ran:false` with `run:false`.
- **Captured (2026-06-29, run:false):** `ran:false`, `commands:["git clone … Daysim","cmake -S … -B …/build -DBUILD_HEADLESS=ON …","cmake --build …/build --target ds_shortterm epw2wea"]`, `bin_dir:".../Daysim/build/bin"`,
  `reason:"run=False: emitted the clone+cmake plan…"`.
- **Result:** PASS(emit).

### W8.3 — annual_nvrd

- **Call:** `{"point_xyz":[2,1.5,1.2],"view_vec":[0,-1,0],"epw":…,"channel_scenes":<W2.3>,"points":<pts>,"run":false}`
- **Assert:** with `run:true` & Daysim → `faithful`/`enhanced` `{R_D,RD_cum}`; else PASS(emit) `commands[]`.
- **Captured (2026-06-29, run:false — the plan's choice, to avoid a full-year Daysim+DDS run):** `ran:false`
  + the full ~30-line plan: `epw2wea`→`ds_shortterm`→`cp rein{hartb,src,hart}.cal`→`suns.rad`
    (`cnt 5165 | rcalc … reinsrc.cal`)→ per-channel `oconv`/`rfluxmtx`/`gendaymtx`/`dctimestep` (sky) and
    `oconv`/`rcontrib`/`gendaymtx -5 0.533 -d`/`dctimestep` (sun); plus the honest `relative_RD_note`
    ("R_D is RELATIVE only… ~±20% envelope"). `channel_scenes`+`points` required even for emit.
- **⚠️ Coverage gap (2026-07-23) — `divergence` is only produced by a LIVE run.** The single-shot
  `divergence` block used to select its representative timestep as *the first with non-zero **sky**
  channels*. On any real year that is a pre-sunrise step — diffuse sky present, every **sun** channel
  identically zero — so `neutral_vs_colored_sun` divided zero by zero and reported exactly **0.0**, which
  reads as "the sun's spectral treatment is immaterial" when the true value at a sunlit step is about
  **+0.6%**. Fixed: the representative timestep is now **peak sun**, falling back to the brightest sky
  only for a wholly overcast series. Because W8.3 has only ever been exercised at `run:false`, **this
  path has no live coverage in the kit** — a `run:true` pass is the only thing that would have caught it.
  **Assert on the next live run: `divergence.neutral_vs_colored_sun.mel_edi_pct` is non-zero on any
  series containing a sunlit timestep.** (`reconstruct_spectrum` in W1.7/X4 is unaffected — the caller
  supplies the channels there, so there is no timestep to choose.)
- **Result:** PASS(emit). *(Live `run:true` is correct here too but is a full-year sub-hourly run — out of time-box.)*

---

## W9 — Study brief & report (prompt `hcl_studio` glue) — also the brief round-trip in **S4**

### W9.1 — load_brief

- **Call:** `{"study":"athens_office"}`
- **Assert:** empty skeleton for a **fresh** study slug; a previously-saved slug returns its persisted brief (resume).
- **Captured (2026-06-29):** fresh slug `valkit_demo` → all-null skeleton `{study, orient:null, goal:null, space:null, …}`. A pre-existing slug `athens_office` returned a **populated** brief from a prior run
  (`goal:">= 250 mel-EDI by 09:00"`, `sim_results.annual_mel_edi_mean:194.2`, `compliance.brown_2022:"fail"`)
  — proving persistence/resume.
- **Result:** PASS.

### W9.2 — save_brief

- **Call:** `{"study":"athens_office","brief":{"goal":"≥250 mel-EDI by 09:00","space":{"l":4,"w":3,"h":2.7},"sim_results":<W3/W6>,"compliance":<W1.6>}}`
- **Assert:** `saved:true`, `path`; rejects unknown phase keys (see N6). Allowed keys: `compliance, daylight_baseline, energy, fixture_spec, goal, orient, sim_results, space, study`.
- **Captured (2026-06-29, study valkit_demo):** `{"saved":true,"path":".../valkit_demo/brief.json"}` with a
  brief of real captured values (goal, space `{l:4.3,w:7.3,h:3.4}`, fixture_spec, sim_results, compliance).
- **Result:** PASS.

### W9.3 — build_report

- **Call:** `{"study":"athens_office","brief":<saved brief>}`
- **Assert:** `md_path`, `html_path`; report renders goal/fixture/target-vs-achieved/compliance.
- **Captured (2026-06-29):** `{"md_path":".../valkit_demo/report.md","html_path":".../valkit_demo/report.html"}`.
- **Result:** PASS.

---

## N — Negative / edge cases (NEW)

Each asserts a **clean typed failure or honest warning**, not a stack trace or silent wrong answer.

### N1 — unmapped OBJ group (promoted W2.2)

- **Call:** `import_geometry {"obj_path":"INPUTS/geometry/office_room.obj","material_map":{"<one group>":{"type":"floor","refl":0.25}}}` (omit the rest).
- **Assert:** clean error listing the missing groups; no partial scene.
- **Captured (2026-06-29; on the current 8-group OBJ the list also includes `Rad_Luminaire_L09`):**
  `Error: unmapped groups (add them to material_map): Rad_Ceiling_R080, Rad_Wall_R050, Rad_Glazing_T073, Rad_Frame_R050, Rad_Furniture_R050, Rad_ScreenGlass_R004[, Rad_Luminaire_L09]` + the discovered-groups list
  and bbox. No Radiance ran.
- **Result:** PASS (clean hard-fail, as designed).

### N2 — malformed SPD

- **Call:** `spd_to_channels {"spd":"380 nonsense\n900 1.0","channel_type":1}`
- **Assert:** clean error or documented clamp (380–780, drops/parses), not a Python traceback.
- **Captured (2026-06-29, spd "380 nonsense\n900 1.0"):** `Error: no wavelength rows in 380-780 nm range`
  (the non-numeric value is dropped; 900 nm is out of range) — clean, no traceback.
- **Result:** PASS.

### N3 — relative vs absolute SPD warning

- **Call:** `alpha_opic` with a relative SPD (peak ≤1.5) then a scaled absolute one.
- **Assert:** relative → `scale_warning` present; absolute (peak >1.5) → no warning; EDIs scale linearly.
- **Captured (2026-06-29):** every relative SPD fed this session (L09 trio, the EPW sky) returned the
  `scale_warning:"…appears RELATIVE (peak <= 1.5)…shape indicators, not lux-scale…"`; `validate`'s
  `elr_scale_invariant` proves ELR is unchanged at 1× vs 2× (`1.2013==1.2013`) while EDIs scale with magnitude.
- **Result:** PASS.

### N4 — invalid channel_type → **DEFECT D-4 (robustness gap)**

- **Call:** `spd_to_channels {"spd":"INPUTS/spd/L09_neutral.spd","channel_type":7}`
- **Assert (expected):** a validation error naming allowed values {0,1}.
- **Captured (2026-06-29):** **NO error.** It returned `{"channels":[0,0.009,…,0.004],"channel_type":7}` —
  identical to the `channel_type:1` result. Any non-zero `channel_type` silently falls through to the
  9-channel path and **echoes the invalid value back**. A caller mistyping `channel_type` gets a plausible-
  looking wrong-labelled result with no warning.
- **Result:** **FAIL (negative test) → Defect D-4, now FIXED.** Exactly the "silent wrong answer" class this
  kit exists to catch. **Fixed** in nested `fix/channel-type-validation` (`ace3886`): `bin_average` now raises
  `ValueError("channel_type must be 0 (3-channel) or 1 (9-channel)")` for non-{0,1} (matching the existing
  `alpha_opic`/`metrics` guards), with a parametrized regression test; suite 1162 passed. **Re-run after the
  server reconnects** to confirm live — the running server predates the fix.

### N5 — invalid compliance standard

- **Call:** `compliance {"mel_edi":250,"standard":"not_a_standard"}`
- **Assert:** error naming the unknown standard.
- **Captured (2026-06-29):** `Error: unknown standard 'not_a_standard'`. (A genuinely unknown name errors;
  the 6 real standards — incl. `ul_24480`/`en_12464_1` — are all accepted, see W1.6/W5.8.)
- **Result:** PASS.

### N6 — save_brief unknown phase key

- **Call:** `save_brief {"study":"neg_test","brief":{"not_a_phase":1}}`
- **Assert:** rejects with a message naming the unknown key (per docstring).
- **Captured (2026-06-29):** `Error: unknown brief key(s) ['not_a_phase']; allowed: ['compliance', 'daylight_baseline', 'energy', 'fixture_spec', 'goal', 'orient', 'sim_results', 'space', 'study']` —
  clean, and enumerates the valid keys (used by W9.2).
- **Result:** PASS.

### N7 — atmosphere_from_epw out-of-range hour / bad EPW

- **Call:** `atmosphere_from_epw {"epw":<ok>,"month":13,"day":40,"hour":25}`
- **Assert:** clean error on the impossible date, not a silent wrong row.
- **Captured (2026-06-29, month 13 / day 40 / hour 25):** `Error: no EPW data row for 13/40 hour 25` — no
  silent fallback to a wrong hour.
- **Result:** PASS.

---

## X — Cross-tool consistency (NEW)

Same quantity computed two ways must agree within a stated tolerance.

### X1 — alpha_opic(spd) vs alpha_opic(channels) — ELR ratio

- **Call:** D65 via exact `spd` and via 9-channel `channels`.
- **Assert:** ELR-type *ratios* agree <5%; absolute EDI diverges (~99.7%) by §9.3a design — assert the
  divergence is *bounded* (≤300% EDI / ≤5% ELR ceilings) and document the gap rather than expecting agreement.
- **Captured (2026-06-29, from `validate`):** `elr_ratio_divergence_pct:0.625` (≤5% ✓);
  EDI `divergence_pct` ≈ `{s:99.76,m:99.756,l:99.757,rhod:99.757,mel:99.757}` — `bounded:true` under the
  300% ceiling. So ELR cancels the §9.3a reconstruction constant; absolute EDI does not.
- **Result:** PASS (ELR agrees; EDI divergence bounded & expected).

### X2 — alpha_opic(spd) EDI vs spectral_metrics eml_edi (exact identity)

- **Call:** `alpha_opic {"spd":"INPUTS/spd/L09_neutral.spd","alpha":5}` vs
  `spectral_metrics {"spd":"INPUTS/spd/L09_neutral.spd"}.eml_edi.mel_edi`.
- **Assert:** the two melanopic-EDI numbers are the **same value** (both integrate the SPD against the
  CIE S 026 melanopic action spectrum) — exact match, not just same ordering.
- **Captured (2026-06-29):** `alpha_opic.EDI = 610.4956` **==** `spectral_metrics.eml_edi.mel_edi = 610.4956`.
  Both carry the same `scale_warning` (relative SPD).
- **Result:** PASS (identity holds to displayed precision).

### X3 — sky → channels → metrics round-trip

- **Call:** W7.2 sky spectrum → `spd_to_channels` → `circadian_metrics`, vs `alpha_opic(spd)` directly.
- **Assert:** the sky's `alpha_opic(spd).EDI` equals `spectral_metrics(spd).eml_edi.mel_edi` exactly;
  CCT/mel-DER physical (no zero/sign anomaly).
- **Captured (2026-06-29, spectrl2 sky-diffuse @ noon, via the W7.5 spd_set):** `alpha_opic.EDI = 74874.94`
  **==** `spectral_metrics.eml_edi.mel_edi = 74874.94`; `cct_K=8568`, `mel_der=1.138`. Identity holds across
  the EPW→sky→SPD→metrics chain.
- **Result:** PASS.

### X4 — reconstruct_spectrum divergence within bound

- **Call:** W1.7 reconstruction → read its self-reported `divergence`.
- **Assert:** both divergence metrics small/bounded (<1%) and always surfaced.
- **Captured (2026-06-29):** `divergence{flat_vs_reference:{mel_edi_pct:0.558, i_eff_pct:0.597}, neutral_vs_colored_sun:{mel_edi_pct:0.299, i_eff_pct:0.311}}` — all <0.6%, surfaced on every call.
- **Result:** PASS.

### X5 — the two sensor-height paths agree on the same OBJ (NEW 2026-07-23)

Every one of these X5–X8 checks pins a **seam**: two individually correct helpers whose conventions
nothing reconciles. That class of defect is invisible to schema validation and to any single tool's
result — it is only caught by running two tools against the same input and comparing. Each was a real
shipped bug.

- **Call:** `import_geometry {…,"derive_sensors":true}` **and** `workplane_grid {…,"workplane_h":0.8}` /
  `observer_points {…,"eye_height":1.2}` on the **same** OBJ + sidecar.
- **Assert:** `import_geometry.grid_points` z **==** `workplane_grid.methodology.workplane_z` (0.8), and
  the derived eye heights **==** `observer_points`' (1.2/1.6). Any disagreement is a floor-datum bug.
- **Captured (2026-07-23, `office_room.obj`):** both paths **0.8 m**; eyes **1.2/1.6 m**; 84 grid points.
- **Why it matters:** `Room_Floor` is a 0.2 m slab (z −0.2 → 0.0) in all four kit OBJs. `derive_sensors`
  anchored to `min(z)` (the *underside*) while the other two used the top face, so they silently
  disagreed by exactly the slab thickness and EN 12464-1 compliance numbers were taken from a plane
  0.2 m too low. See W2.3.
- **Result:** **PASS (live via MCP, 2026-07-23)** — `import_geometry(derive_sensors=true)` returned `grid_points` at z **0.8** and `observer_sets` at **1.2 / 1.6**; `workplane_grid` on the same OBJ returned `methodology.floor_top_z 0` and `workplane_z 0.8`. The two independent sensor paths agree exactly, which is the cross-check that catches the slab-datum bug class.

### X6 — melanopic lux is not mel-EDI (NEW 2026-07-23)

- **Call:** `circadian_metrics` on any channel row → feed **both** `melanopic_lux` and `mel_edi` to
  `compliance {"standard":"brown_2022"}`.
- **Assert:** the two differ by D65's binned melanopic/photopic ratio **1.099665**
  (`mel_edi == photopic_lux × mel_der`); `compliance` stamps `quantity:"mel_edi"`; and **only `mel_edi`
  is the quantity the standard is written in**. On the W1.4 channels: 260.65 vs **237.03** lx, a 9.1% gap.
- **Also assert the accuracy route:** without `spd=`, `mel_der_source:"binned_channels"` + `mel_der_note`;
  with `spd=INPUTS/spd/L09_neutral.spd`, `mel_der_source:"spd_transported"`, no note, plus
  `source_mel_der` and `transport_ratio`. `mel_der` equals the continuous-SPD value **only when the
  channels are that source's own bin averages** (neutral transport); on transported channels it is the
  at-point value and legitimately differs — see ADR-0006. The route string was `"spd"` before 2026-08-01.
- **⚠️ `quantity` is a label, not a detector.** `compliance(mel_edi=…)` stamps `quantity:"mel_edi"`
  whatever number it is handed — verified live: feeding `melanopic_lux` 260.65 returns
  `{result:"pass", quantity:"mel_edi"}`, while the true mel-EDI 237.03 returns `{result:"fail"}`. The
  stamp records what the caller *claimed*, so it makes an artifact unambiguous **after** the fact but
  cannot catch the mislabel at the call site. **Only reading `mel_edi` off `circadian_metrics` does.**
  This is precisely the shipped-verdict error corrected in W3.4/W3.5.
- **Result:** **PASS (live via MCP, 2026-07-23)** — `circadian_metrics` returned `melanopic_lux 242.71` alongside `mel_edi 220.72` (9.1% apart) with `mel_der_source:"binned_channels"` + `mel_der_note`. **The verdict flip reproduces through the tool surface:** `compliance(mel_edi=260.65)` → **pass**, `compliance(mel_edi=237.03)` → **fail**, both stamped `quantity:"mel_edi"` — the shipped-wrong-verdict case of W3.4/W3.5, confirmed live rather than by hand arithmetic.

### X7 — zone weights: two helpers, one room, two answers (NEW 2026-07-23)

- **Call:** `photosensors {…}` → read its emitted `weights` + `uncontrolled_fraction`; run
  `daylight_savings(mode="annual")` with **those** weights, then again with
  `area_weights_from_geometry` weights.
- **Assert:** both runs echo `sum_weights` / `uncontrolled_fraction` / `coverage_note`, and the savings
  differ by **coverage alone**. Neither helper is wrong; the assumption must be visible in the result.
- **Captured (2026-07-23, synthetic 600/300 lx series, area 28 m², 392 W, iset 500, ContinuousOff):**
  photosensor zones `sum_weights 0.708`, uncontrolled `0.292` → **55.5%** mean reduction;
  whole-floor `sum_weights 1.000`, uncontrolled `0.000` → **82.6%**. Same daylight, ~27 pp apart.
- **Note:** when weights sum to 1.0 the `coverage_note` reads "Confirm that is physically true — an
  uncontrolled core would lower the saving." **Do not report a savings figure without checking it.**
- **Result:** PASS (live, 2026-07-23 — synthetic 600/300 lx series: photosensor zones `sum_weights 0.708` / uncontrolled `0.292` -> **55.5%**; whole-floor `1.000` / `0.000` -> **82.6%**, with the confirm-it-is-physically-true note).

### X8 — luminaire count survives the import (NEW 2026-07-23)

- **Call:** `import_geometry` on an OBJ whose N fittings share one `usemtl` → read `electric_lights`.
  **`office_room.obj` is exactly this case:** its four `Luminaire_L09_*` objects all carry
  `usemtl Rad_Luminaire_L09`.
- **Assert:** one emitter **per connected mesh island**, not one per material group, at the fittings'
  true positions; `total_wattage == N × per-fixture W` once an IES is bound. A single multi-face fitting
  stays one emitter (its faces share vertices).
- **Captured (2026-07-23, live, `office_room.obj`):** **4 emitters** at
  `(±1.0, ±1.8, 2.8)` — the four modelled housings, not one centroid — plus the warning
  *"luminaire group 'Rad_Luminaire_L09': 4 emitters from 4 disconnected mesh islands (one per fitting);
  total load scales with this count"*.
- **Why it matters:** grouping by `usemtl` collapsed these four housings to a **single centroid emitter
  at 1/4 of the drawn load** — a 4× installed-power error that completed with no warning and silently
  invalidated every downstream lux and energy figure. The count is now geometry-derived, so it no longer
  depends on the modeller naming materials a particular way.
- **Result:** **PASS (live via MCP, 2026-07-23)** — the wholesale-sidecar paste (`_README` and all, no `units`/`up_axis` arguments) now returns 8 groups, `material_sets` 3×7, and `manifest{units:"m", up_axis:"Z", north_angle_deg:0, map_source:"inline"}`. The same call also carried the warning *"luminaire group 'Rad_Luminaire_L09': 4 emitters from 4 disconnected mesh islands (one per fitting)"* at positions (±1, ±1.8, 2.8) — X8 confirmed in the same response.

---

## S — Workflow chaining / state (NEW — the headline workflows)

Real multi-call chains where output N feeds call N+1, each ending in a comparison table. These mirror
GUIDE Part 4.5 scenarios.

### S1 — Blinds A/B (daylight & glare)

*Add venetian blinds → what happens to daylight & glare at the eye?* Run the **same** grid+glare on
`office_room.obj` then `office_room_blinds.obj`; tabulate.

- **Chain:** import_geometry(each) → colored_sky → run_grid → circadian_metrics → glare_ugr.
- **Assert:** blinds model shows **lower** eye photopic lux & mel-EDI **and lower glare** than the bare
  window (the daylight-vs-comfort trade-off, quantified, monotone in the expected direction).
- **Captured (2026-06-29, same sky9 @ June-21 noon, same eye points/view — on the OLD north-facing
  geometry; ⚠️ re-capture on the 2026-07-05 re-authored south room, absolute levels will rise, the blinds
  *ratio* should hold):**

  | metric (eye)                      | bare`office_room` |   `office_room_blinds` |
  | --------------------------------- | ------------------: | -----------------------: |
  | photopic, point @(−0.9,−2.7)    |           137.4 lux |       **21.1 lux** |
  | melanopic-EDI, same point         |               154.9 |           **24.7** |
  | photopic, far point @(−0.9, 2.7) |           240.0 lux |       **76.3 lux** |
  | melanopic-EDI, far point          |               260.7 |           **78.0** |
  | DGP (eye view)                    |              0.1716 |         **0.1617** |
  | window glare-source luminance     |     68.5/56.0/215.3 | **14.5/12.1/45.5** |

  Blinds cut eye mel-EDI ~80–85% **and** lower DGP + glare-source luminance (~4×). The classic
  daylight-vs-comfort trade-off, quantified. (Import also exercised the `sidecar` path — W2.5.)
- **Result:** PASS (monotone in the expected direction).

### S2 — Tunable-white CCT sweep (spectrum only, no engine)

*How circadian is each CCT per lux?* Pure spectral math on the three SPDs.

- **Chain:** for each of `L09_{warm,neutral,cool}.spd`: spectral_metrics + alpha_opic(alpha=5) → table CCT, mel-DER, mel/photopic.
- **Assert:** CCT rises warm(≈2700)→neutral(≈4000)→cool(≈6500); **mel-DER strictly increases**
  warm→cool (the core HCL evidence). Any non-monotonicity = PARTIAL.
- **Captured (2026-06-29):**

  | SPD                  | CCT (K) |       Duv | mel-DER | mel/photopic |
  | -------------------- | ------: | --------: | ------: | -----------: |
  | L09_warm (2700 K)    |  2694.4 | −0.00065 |  0.4069 |       0.3685 |
  | L09_neutral (4000 K) |  3985.2 |  +0.00038 |  0.6103 |       0.5529 |
  | L09_cool (6500 K)    |  6471.0 | −0.00083 |  0.9818 |       0.8893 |

  mel-DER strictly increases 0.407 → 0.610 → 0.982; CCT tracks nominal within ~30 K. (SPDs are relative
  PhotoLED proxies ⇒ the absolute EDIs carry `scale_warning`; mel-DER/CCT are scale-invariant.)
- **Result:** PASS (monotonic — the "cool for alertness, warm at night" evidence, quantified).

### S3 — Tunable-white in the real room (electric + energy)

*Hold task lux fixed, watch circadian dose move with CCT.*

- **Chain:** recommend_fixtures → ies_analyze + ies_to_radiance(L09_neutral) → run_grid(+electric) →
  daylight_savings → compliance; then repeat with warm & cool IES+SPD.
- **Assert:** photometry (lumens/efficacy) ≈ constant across the three fixtures; **mel-DER / mel-EDI per
  lux climbs with CCT.** Non-monotone mel-DER = PARTIAL.
- **Captured (2026-06-29, `ies_analyze` photometry × `spectral_metrics` spectrum, per CCT):**

  | fixture              | rated lm | efficacy lm·W⁻¹ | CCT (K) | mel-DER |
  | -------------------- | -------: | -----------------: | ------: | ------: |
  | L09_warm (2700 K)    |     4467 |              117.6 |    2694 |   0.407 |
  | L09_neutral (4000 K) |     4702 |              123.7 |    3985 |   0.610 |
  | L09_cool (6500 K)    |     4702 |              123.7 |    6471 |   0.982 |

  Photometry is near-flat (same fixture, ±5% lumens) while **mel-DER rises monotonically warm→cool** — i.e.
  hold the task lux fixed and the circadian dose climbs with CCT. *(The full room-level run — `run_grid`
  holding 500 lux while CCT varies — is the same machinery as W5.4 and needs a luminaire-tagged OBJ; the
  photometry-vs-spectrum slice above demonstrates the effect without it.)*
- **Result:** PASS (monotone mel-DER; photometry flat).

### S4 — Brief round-trip (studio glue / state)

- **Chain:** load_brief(empty) → save_brief(goal+space+sim_results) → load_brief(returns saved) →
  build_report.
- **Assert:** load after save returns exactly what was saved (shallow-merge persisted); report renders
  the saved goal & compliance. State survives the round-trip.
- **Captured (2026-06-29, study valkit_demo):** `load`(fresh) → all-null skeleton; `save`(goal+space+
  fixture_spec+sim_results+compliance) → `saved:true`; `load`(again) → returns **exactly** the saved values
  (unset fields stay null — shallow-merge); `build_report` → `report.md` + `report.html`. Round-trip intact.
- **Result:** PASS.

### S5 — Full annual energy study (daylight → dimming → kWh/year, the "combination of both")

*Quantify how much electric-lighting energy daylight saves over a full year, with controls.* This is the
headline cross-tool chain the energy section (E) decomposes; here it runs end-to-end into one verdict table.

- **Chain:** import_geometry(W2.3) → `.wea`(W-prep) → **daylight_savings(mode="annual", run=true)**
  (run_annual 8760-h DDS at the work-plane point → per-hour daylight lux → EnergyPlus controls) → read
  `controls.annual_kwh` / `annual_kwh_per_m2` / `mean_reduction` / `occupied_hours` → save_brief(energy=…) →
  build_report. Then re-run on `office_room_blinds.obj` for the **daylight-vs-comfort energy trade-off**.
- **Assert:** `ran:true`, `mode:"annual"`; `annual_kwh` > 0 and **< the no-controls baseline**
  (`p_rated·occupied_hours/1000`); `0 < mean_reduction < 1`; `occupied_hours` ≈ weekday 08–18 count for the
  run window; blinds variant shows **higher `annual_kwh` (less saving)** than the bare window — quantifying
  that the glare fix in S1 costs lighting energy. Numbers flagged synthetic-baseline until the live DDS run
  (E2) replaces the daylight series with the real Athens 8760-h simulation.
- **Captured:** — *to capture on the next live run (E2 supplies the Radiance-driven `annual_kwh`; this row
  binds it into the studio brief + report and adds the blinds A/B).* Grounding from the deterministic core
  (E1/E3, synthetic single-point daylight): ContinuousOff `annual_kwh≈113.7` (8.82 kWh·m⁻²),
  `mean_reduction≈0.903`, `occupied_hours=2610`, vs a **no-controls baseline 1169.3 kWh** (~90% saved).
- **Result:** PENDING (live annual DDS) — components live-validated (E1/E3 core; W5.6 point-in-time; W6.2 DDS).

---

## E — Energy & daylight-responsive controls (NEW — the headline energy assessment)

The plan's W5.5/W5.6 only exercise the **single-step** (`itot_per_point`) and **point-in-time** slices of the
energy machinery. The tools' headline outputs — **annual kWh, kWh·m⁻², mean reduction over 8760 h** — and the
three EnergyPlus dimming laws live on the `itot_series` / `mode="annual"` paths and were untested. This section
covers them, plus the daylight↔energy↔combined cross-checks. Score sim-dependent rows by W0 capability.

> **Why this matters.** "Energy savings from daylight" is the EN 15193 / LEED daylight-responsive-dimming
> result a designer actually reports. It is the *integral* of the point-in-time saving over the occupied year,
> and it depends on the control law (Continuous vs ContinuousOff vs Stepped) — none of which W5 reached.

### E1 — lighting_controls annual series (`itot_series` → annual energy)

- **Call:** `lighting_controls {"itot_series":<[[lx] per hour] for 8760 h>,"weights":[1.0],"area":12.9, "iset":500,"p_rated":448,"control_type":"ContinuousOff"}` (one daylight lux per occupied hour; `schedule`
  omitted ⇒ default weekday 08–18 mask).
- **Assert:** returns `{per_hour[], annual_kwh, annual_kwh_per_m2, mean_FP, mean_reduction, occupied_hours}`;
  `annual_kwh = Σ(p_rated·FP_h)/1000` over occupied hours **only**; `annual_kwh < p_rated·occupied_hours/1000`
  (the no-controls baseline); `annual_kwh_per_m2 = annual_kwh/area`; `0 ≤ mean_reduction ≤ 1`;
  `occupied_hours` = count of `schedule>0`. Unoccupied hours contribute **zero** consumption (verify the tail
  isn't truncated — the code uses an explicit length-check, not `zip`).
- **Captured (2026-06-29, from `hcl_core.lighting_controls`, synthetic single-point daylight series, area
  12.9 m²):** ContinuousOff → `annual_kwh:113.7`, `annual_kwh_per_m2:8.82`, `mean_reduction:0.9027`,
  `occupied_hours:2610`; no-controls baseline `448·2610/1000 = 1169.3 kWh` ⇒ **~90% saved**. (Synthetic series
  — the live MCP run binds the real run_annual daylight series, see E2.)
- **Result:** PASS (core grounded; live MCP `lighting_controls` re-confirm on reconnect).

### E2 — daylight_savings mode="annual" (DDS → annual energy, end-to-end)

- **Call:** `daylight_savings {"mode":"annual","channel_scenes":<W2.3 3 dicts>,"wea":"W2-geometry/work/GRC_Athens.wea", "points":"INPUTS/sensors/office_room_grid.pts"(single ref point),"weights":[1.0],"area":12.9,"iset":500, "p_rated":448,"control_type":"ContinuousOff"}`. Annual mode **elicits confirmation** (long DDS); decline ⇒
  emit plan. v1 supports a **single** reference point (`weights` len>1 ⇒ clean ValueError — see N-E1).
- **Assert:** live → `ran:true`, `mode:"annual"`, `n_timesteps`≈8760 (or period length),
  `controls{annual_kwh>0, annual_kwh_per_m2, mean_reduction∈(0,1), occupied_hours}`; `annual_kwh` < baseline;
  the per-hour daylight feeding controls must match `run_annual` photopic at that point (cross-tool). Else
  (Radiance absent / declined) → `ran:false` + `commands[]` (PASS(emit)). **Long — time-box or run on a
  sub-`period`** (e.g. one equinox week) to keep wall-time bounded while still integrating real hours.
- **Captured:** — *to capture on next live run (decline-to-emit at minimum; a bounded `period` gives a real
  `annual_kwh`).* Expect the same shape as E1 with the synthetic series replaced by the Athens DDS daylight.
- **Result:** PENDING (live DDS) / PASS(emit) on decline — the orchestration (run_annual→controls_series) is
  the same machinery validated in W6.2 + E1.

### E3 — control_type sweep (the three EnergyPlus dimming laws)

- **Call:** E1's `itot_series` repeated with `control_type` ∈ {`ContinuousOff`, `Continuous`, `Stepped`}
  (n_steps 3), all else equal.
- **Assert:** all three return valid energy; **savings order ContinuousOff ≥ Stepped ≥ Continuous** (Off
  kills the lamp above setpoint → most saving; Continuous floors at `fP_min` → least; Stepped quantizes in
  between). Equivalently `annual_kwh` rises Off < Stepped < Continuous. Any inversion ⇒ PARTIAL.
- **Captured (2026-06-29, core, same synthetic series/area as E1):**

  | control_type  | annual_kwh | kWh·m⁻² | mean_reduction | occupied_h |
  | ------------- | ---------: | ---------: | -------------: | ---------: |
  | ContinuousOff |      113.7 |       8.82 |         0.9027 |       2610 |
  | Stepped (3)   |      155.9 |      12.09 |         0.8667 |       2610 |
  | Continuous    |      236.5 |      18.33 |         0.7977 |       2610 |

  Consumed kWh strictly increases Off→Stepped→Continuous (saving strictly decreases) — the dimming-law
  effect, quantified, all vs the 1169.3 kWh no-controls baseline.
- **Result:** PASS (monotone in the expected direction; `workbook_compat:true` is a 4th variant — assert it
  shifts `fP` per the EnergyPlus xlsx floor without breaking the ordering).

### E4 — Combined daylight + electric (hold task lux, bill the electric top-up) — closes the W5.4 gap

- **Setup (action):** the shipped `office_room.obj` has **no luminaire group**, so the combined
  `run_grid(electric_lights=…)` leaf (W5.4) and a true "daylight + electric to 500 lx" energy figure can't be
  captured. **Add `office_room_lit.obj`** = `office_room.obj` + a `type:"luminaire"` group (the L09 IES + its
  9-ch SPD, e.g. the 2×2 grid from W5.2) so `import_geometry` emits a drop-in `electric_lights` payload.
- **Call:** `run_grid {scene_sets, points:grid.pts, electric_lights:<from import_geometry>}` → read
  `daylight` / `electric` / `combined` / `total_wattage`; then `daylight_savings(point_in_time)` and
  `lighting_controls` on the **combined** lux to compute the electric energy still needed to reach 500 lx.
- **Assert:** `combined ≥ daylight` at every point; where daylight already ≥ iset, controls dim electric to
  `fL≈0` (no top-up); `total_wattage` > 0 only where daylight < iset. Combined glare via
  `glare_ugr(electric_lights=…)` (daylight+electric fisheye) stays plausible (UGR 0–30).
- **Captured:** — *to capture once `office_room_lit.obj` ships (components live in W5.2/W5.3/W5.5/W5.6).*
- **Result:** PENDING (needs luminaire-tagged OBJ — the one documented kit gap; building blocks all PASS).

### E5 — Energy cross-checks (consistency)

- **E5a (point parity):** `daylight_savings(point_in_time)` `controls.P_saved` **==**
  `lighting_controls(itot_per_point=<same daylight lux>)` `P_saved` at identical points/weights — the
  orchestrator must not perturb the controls math. **Captured:** core `controls_point([620,410],[0.5,0.5])`
  → `FP:0.1332, P_saved:388.35, reduction:0.8668`, **identical to W5.5's tool capture** ⇒ PASS.
- **E5b (sizing vs controls):** `recommend_fixtures.est_total_watts` ≈ `fixture_count` × per-fixture watts,
  and `power_density_w_m2 = est_total_watts/(L·W)`. **Captured (W5.7):** 4 fixtures, `est_total_watts:114.7`,
  `power_density_w_m2:9.56` on 12 m² ⇒ 114.7/12 ≈ 9.56 ✓ — internally consistent.
- **Result:** PASS (both identities hold to displayed precision).

### N-E1 — annual mode, multiple points (negative)

- **Call:** `daylight_savings {"mode":"annual","weights":[0.5,0.5],…}`
- **Assert:** clean ValueError — annual v1 is single-point ("pass weights=[1.0] … or use point_in_time").
- **Captured:** — *to capture; the guard is in `daylight_savings` (server.py) before any simulation.*
- **Result:** PENDING (expected clean raise).

> **Argument-level coverage still open (honest ledger).** Smaller untested knobs, none yet captured:
> `lighting_controls`/`daylight_savings` `workbook_compat:true` (xlsx floor), `schedule` as an explicit
> per-hour list (vs default mask), `control_type:"Continuous"` via the *MCP* tool (E3 is core-grounded);
> `glare_ugr`/`run_image` `electric_lights` (combined-glare fisheye); `compliance` `daylight_met` (en_17037
> daylight path); `weather` `timestep_min` sub-hourly decomposition; `run_annual` `rad_params` override.
> List these as skips with reasons in the final report rather than implying full argument coverage.

---

## G — Argument, mode & error-path coverage (NEW v2.3 — gap-closure)

Every item below is an unexecuted **kwarg / output-shape branch / `raise` guard**, grounded in a specific
source site, found by a full code-vs-plan audit (2026-07-01). Score **PENDING (add)** until captured. Most are
pure-Python or emit-path ⇒ runnable regardless of engines. `run:false` is the cheap way to reach the emit branch
of any sim tool.

> **G0 — cross-cutting.**
> **(a) The emit envelope is never asserted.** Every Radiance/Daysim capture ran live (`ran:true`); the
> `run:false` / engine-absent contract `{ran:false, commands[], reason}` has **zero** coverage on `run_grid`,
> `run_image`, `glare_ugr`, `ies_to_radiance`, `colored_sky`, `colored_luminaire`(N/A — pure), `run_annual`,
> `annual_nvrd`, `spectral_sky_native`, `daylight_savings(mode=annual)`,
> `generate_subhourly_wea`. Add one `run:false` assertion per tool.
> **(b) `up_axis:"Y"` is untested everywhere** — all fixtures are Z-up (W-prep pins it). The Y-up remap
> (`_to_world x,-z,y`; `build_xform -rx 90`) affects footprint / floor_z / apertures / every sensor coord for all
> five geometry tools; one Y-up fixture (G7) exercises the shared branch at once.
> **(c) `north_angle_deg≠0` and non-`"m"` units** are untested for the geometry/sensor tools. All four
> models are authored in the true-north frame so their pinned maps set `north_angle_deg 0` (the desired
> south / south-west facing comes from the geometry, not a rotation), and all fixtures are metres — so the
> `_rotate_north` sensor/aperture rotation and the unit `scale_factor` remain unexercised. Add a rotated
> and/or non-metre fixture to cover them.

### G1 — Spectral & metric core

- **G1.1** `spectral_metrics.inverse` — `{eml_edi_value:275.75,"eml_edi_direction":"eml_to_medi"}` → `result≈250` (÷1.103, inverse of W1.5's default). Protects the `eml_to_medi` branch.
- **G1.2** `spectral_metrics.single` — `{spd:…,"metric":"cct_duv"}` (then `"mel_der"`) → only that key, not the full `all` bundle.
- **G1.3** `reconstruct_spectrum.faithful` — W1.7 args + `"method":"faithful"` → `spectrum` len 401; flat per-bin totals differ from the `reference` shape (only `reference` tested).
- **G1.4** `reconstruct_spectrum.variants` — `"sun_spectral":"neutral"` (vs colored); explicit `sky_spd`/`sun_spd` 401-vectors; `"dseries_sky":true`+`"sky_cct":6500`; `"channel_type":0` 3-ch input.
- **G1.5** `write_material.glass` — `{channels:[0.7,0.7,0.7],"material_type":0,"channel_type":0,"name":"win"}` → `.rad` has a `glass` primitive (W3.2 only made `plastic`); plus `roughness`/`specularity`≠0 → `plastic … 5 … r s`.
- **G1.6** `compliance.daylight_met` (plan's own open-knob) — `{mel_edi:120,"standard":"well_v2_l03","daylight_met":true}` → scores vs **daylight** thresholds (1pt≥109/3pt≥163), not electric (136/218); `{standard:"en_17037","daylight_met":true}` exercises the en_17037 daylight path.

### G2 — Geometry & sensors

**`import_geometry`**

- **G2.1** `.context` — a `type:"context"` group → `context_groups:[…]`, excluded from footprint + sanity-bbox (`_noncontext_model_bbox`).
- **G2.2** `.ground` — `type:"ground"` w/ `refl` → `ground_albedo`(len 401)+`ground_albedo_kind:"flat"`; w/ `spd` → `kind:"spd"`, clamped [0,1]. Drives the ground→sky bridge (feeds G3.4.albedo_ground).
- **G2.3** `.luminaire` (needs **G7** fixture) — `type:"luminaire"` group → `electric_lights` payload + `luminaires` block, group excluded from `material_sets`/`scene_map`; a luminaire w/o marker or w/o `ies` → **warning**, not silent drop.
- **G2.4** `.channel_type0` — `{…,"channel_type":0}` → one 3-ch material set (W2.3 only did 9-ch).
- **G2.5** `.unmaterialized` — OBJ mixing `usemtl` with faces before any `usemtl` → `ValueError "…no active usemtl…"` (distinct from N1's *unmapped*). `.bad_units` (`"inches"`) and `.missing_refl` (plastic spec w/o `refl`) → clean `ValueError`s.

**`workplane_grid`**

- **G2.6** `.no_map` → `ValueError`. `.override` — explicit `interior_extent` → `interior_extent_source:"override"`, clip ignored. `.max_spacing:0.5` → `p_source:"override"`.
- **G2.7** `.border_too_big` (`border_offset:5.0`) → `ValueError "calc area is non-positive…"`. `.clip_false` — concave room + `clip_to_footprint:false` → NOT clipped (no "cells dropped" warning). `.write_pts:null` → no file.

**`observer_points`**

- **G2.8** `.azimuth` — unpaired seat + `"direction_fallback":"azimuth","fallback_azimuth":90` → dir≈`[1,0,0]`, `source fallback:azimuth`. `.sweep` — `"sweep","sweep_n":4` → 4 obs/seat.
- **G2.9** `.workstations` — `"workstations":[{eye,target}]` → 1 obs `source:"explicit"`, detection skipped; eye/target with a Z coord → "ignored" warning. `.no_seats` → `position_fallback:"room_center"` (centroid) and explicit `[x,y]`. `.eye_height_list` `[1.2,1.6]` → 2 obs/seat. `.outside_footprint` — seat off the slab → warning (not moved); `.unpaired_screen` warning.

**`photosensors`**

- **G2.10** `.mount_ceiling` — `"mount":"ceiling"` → z≈ceiling−ε, dir `[0,0,-1]`; ceiling undetected → `floor+3.0−ε` fallback.
- **G2.11** `.zone_ies` — `"zone_rule":"ies_2.5"` → exactly **1** zone, depth `2.5·(H_win−task_height)`. `.no_glass` (OBJ w/o glass) → `ValueError "…needs a glazing group…"` (asserted in W2.8 prose, never *called*). `.snapped` (`depth_factors:[5,10]`) → `zones[*].snapped:true`+warning. `.three_zones`/`.sensor_fraction`/`.task_height` variants.

**`preview_scene`**

- **G2.12** `.render_grid` (2 PNGs, grid layer only) / `.render_observers` (**1** PNG, plan only) / `.render_observers_3d` (**1** PNG, 3d only) / `.render_unknown` (warns, falls back to "all"). Only `render:"all"` tested (W2.9).
- **G2.13** `.no_floor` (OBJ w/o floor) → "footprint outline will be empty" warning, PNG still valid. `.luminaire_groups` non-empty (needs G7) → yellow squares, no "no footprints" warn. `.inline_layers` — a point layer as an inline list, not a path.

### G3 — Sky & spectral-EPW

- **G3.1** `colored_sky.irrad_E` — `{"irrad_mode":"E","globl":700}` → gendaylit line has `-E 700`. `.irrad_bad` → `ValueError "irrad_mode must be 'W' or 'E'"`.
- **G3.2** `colored_sky.luminance` — `{"mode":"luminance","channel_type":0}` → single `sky.rad`, `!gendaylit … -C` + warm ground-glow; `"channel_type":1` here → `ValueError "luminance mode is 3-channel only"`; `"mode":"gensky"` → `ValueError`. Entire `-C` path untested.
- **G3.3** `colored_sky.9ch` — `{"channel_type":1,…9…}` standalone → three `sky_a/b/c.rad` w/ per-bin `scale_solar`/`sky_glow` triplets (only seen indirectly in W3.4).
- **G3.4** `spectral_sky_from_epw` — `.unknown_engine` → `ValueError`; `.albedo_len` (`spectral_albedo:[0.2,0.2]`) → `ValueError "must have length 401"`; `.albedo_ground` (401-vector albedo + `surface_tilt_deg:90`) → **non-zero** `ground` (as of 2026-07-25 the *grey* path is non-zero too — W7.2's all-zero was the field-32 `0.000` defect, ADR-0004 — so this now checks the explicit `spectral_albedo` vector overrides the grey default, not merely that it is non-zero); `.overrides` (`{overrides:{aod500:0.4}}`) → `provenance.aod500.source:"override"`; `.no_tilt` → `ground` key **absent**.
- **G3.5** `spectral_epw.band_matrix` — `{"forms":["band_matrix"],"hours":[[6,21,12]]}` → `spectral_band_matrix.txt` (40-band means). **The `band_matrix` form is emitted by zero plan steps.** `.default_forms` (omit `forms` → all four keys); `.unknown_form` → `files:{}` (silent no-op — flag if a raise is wanted); `.smarts_engine`.
- **G3.6** `spectral_sky_native.mode_sun`/`.mode_sky` (`-d`/`-s`); `.unknown_mode` → `ValueError`; **`.timed_out`** (`{"mf":6,"timeout":1}`) → `{ran:true,ok:false,timed_out:true}` (**not** a raise); `.emit` (`run:false`) → `commands[]`; `.mf2` → header `nrows` grows.
- **G3.7** `atmosphere_from_epw.reitan_fallback` (dew-point-only hour → `provenance.pw_cm.method:"reitan63"`); `.pw_fixed` (no humidity → 1.5 cm); `.aod_default` (missing AOD col → 0.10); `.bad_header` → `ValueError "could not parse EPW LOCATION header"` (N7 only did bad-date).
- **G3.8** **Atmosphere-physics refinements (opt-in; every default reproduces prior output byte-for-bit).** New keyword-only args on `atmosphere_from_epw`/`spectral_sky_from_epw`/`spectral_epw`: `ozone_mode`, `aerosol_g`, `aod_anchor_nm` (+ `smarts_aerosol` on the two spectral tools). Same EPW/hour as W7.1 (Athens 37.90 N, 23.73 E, Jun-21 noon).
  - **G3.8a** `atmosphere_from_epw.ozone_climatology` `{ozone_mode:"climatology"}` → `ozone_atm_cm` **≠ 0.30** (van Heuklon 1979 from the EPW LOCATION lat/lon + date; Athens Jun-21 ≈ **0.342 atm-cm**), `provenance.ozone_atm_cm.method:"van_heuklon79"`, `source:"climatology"`. **NH spring-peaking** (confirmed vs Karavana-Papadimou 2013). `.ozone_default` (omit) → `ozone_atm_cm:0.30`, `method:"fixed"` (byte-identical guard).
  - **G3.8b** `atmosphere_from_epw.aerosol_g` `{aerosol_g:0.60}` → output dict carries `aerosol_g:0.60`, `provenance.aerosol_g.source:"override"`; omit → `0.65` (default, byte-identical).
  - **G3.8c** `atmosphere_from_epw.aod_anchor` `{aod_anchor_nm:550}` → `aod500` **larger** than the `None`/500 value (shorter λ = more AOD), `provenance.aod500.method:"angstrom_from_550.0nm"`; `{aod_anchor_nm:500}` is a strict **identity** (== omit).
  - **G3.8d** `spectral_sky_from_epw.ozone_climatology` `{ozone_mode:"climatology"}` → the record's `atmosphere.ozone_atm_cm` ≠ 0.30 (threaded through the pipeline); default unchanged spectrum.
  - **G3.8e** `spectral_sky_from_epw.smarts_aerosol` `{engine:"smarts", smarts_aerosol:"user"}` → SMARTS live: the deck emits an `'USER'` Card 8 + Card 8a (α + `g` settable); default `"rural"` keeps the `S&F_RURAL` 17-card deck. If SMARTS absent → expected `RuntimeError` PASS(expected-raise).
  - **G3.8f** `spectral_epw.ozone_climatology` (annual path) `{ozone_mode:"climatology","hours":[[1,21,12],[7,21,12]]}` → the two records' `ozone_atm_cm` **differ by season** (per-row day-of-year), both ≠ 0.30.

### G4 — Electric & photometry

- **G4.1** `ies_analyze` — `.typeB` (photometric_type≠1 → `flux_supported:false`, null flux); `.absolute` (lumens=-1 → `LOR:null`, `rated==total_flux`); `.inline` (raw text, not a path); `.tilt_include`; `.malformed` (no-TILT → `ValueError`; truncated grid → `ValueError`); `.multi_horiz` (`flux_azimuth_note`).
- **G4.2** `ies_to_radiance` — `.color` (`-c R G B`); `.positions` placement; `.no_placement` (1 step, no xform); `.emit`; `.units_invalid` (`3` → `ValueError`); `.placement_invalid` (`{foo:1}` → `ValueError`); `.units_divisor`/`.lamp`/`.feet`.
- **G4.3** `colored_luminaire` — `.count1`/`.count2` (green/red thirds); `.count_invalid` (`3` → `ValueError`); `.channels_len` (len≠9 → `ValueError`); `.name` explicit; `.rawtext` (raw .rad → default name `luminaire_colored`); `.no_match` (no default-light line → silent **unchanged** copy — pin it).
- **G4.4** `recommend_fixtures` — `.visual` (omit `target_mel_edi` → `binding:"visual"`, `cct_band:[3000,4000]`, no supplementary); `.reachable_palette` (`target_mel_edi:150` → `reachable_by_cct:true`, named preset); `.beyond_palette` (mid band, `beyond_illustrative_palette:true`); `.daylight_credit` (`mel_edi_daylight:200`); `.distribution` `"indirect"`/`"direct_indirect"`; raises: bad distribution, `mount≤workplane`, `vhr≤0`, `em≤0 w/ circadian`.
- **G4.5** `glare_ugr` — `.electric` (combined fisheye, needs G7 — plan open-knob); `.channel_type1` (3 sets → "9-channel approximate" note); `.emit`; `.wrong_setcount` (`ValueError`); `.glare_params`.
- **G4.6** `run_image` — `.fov_false` (no `weighted.hdr`); `.channel0` (1 set → 1 map); `.electric` (`total_wattage`, needs G7); `.glare_flag` (its own `glare:true` → `glare{}`); `.emit`; `.wrong_setcount`; `.mask_dir` reuse (no synth).

### G5 — Annual, energy & daylight

- **G5.1** `run_grid.electric` (combined≥daylight, `total_wattage`; needs G7); `.rad_params` (`-ab 0` direct-only differs from default). *(Note: `run_grid` has no `fov`/`sensor_set` kwarg — those live on `run_image`/the daylight tools; nothing to test.)*
- **G5.2** `run_annual.rad_params` (open knob); `.no_dosimetry` (`dosimetry_threshold:null` → **no** `dosimetry` key); `.chan_mismatch` (1 scene + `channel_type:1` → `ValueError "needs 3 channel scene(s)"`); `.full_year`; `.timestep_min`.
- **G5.3** `annual_daylight.occupancy_raise` (length≠timesteps → `ValueError`); `.no_points` (no points+no sensor_set → `ValueError`); `.sensor_set` precedence (wins over inline points); `.thresholds` (`da_threshold:500` drops DA). *(No `period`/`partial_year` param — the ledger already flags this wiring gap.)*
- **G5.4** `daylight_factor.gnd_refl` (0.5 shifts DF up); `.sensor_set`; `.emit`; `.no_points` raise; month/day/hour sky overrides.
- **G5.5** `daylight_savings.mode_raise`; `.pit_weights_mismatch` (2 pts / 1 weight → `ValueError`); `.weights_sum` (`[0.7,0.6]` → sum>1 `ValueError`); `.annual_multipoint_raise` (**=N-E1**, still PENDING); `.control_type_mcp` (Continuous/Stepped ordering **via the MCP tool**, E3 was core-only); `.workbook_compat`; `.control_type_invalid`; `.mode_annual` live/emit (**=E2/S5**).
- **G5.6** `lighting_controls.series_mcp` (**=E1 live via MCP**: `itot_series`→`annual_kwh`); `.schedule_len_raise` (schedule len≠series → `ValueError` — the anti-truncation guard, never fired); `.explicit_schedule`; `.no_input_raise`; `.weights_missing`; `.control_type` sweep via MCP (**=E3 live**).
- **G5.8** `annual_nvrd.run_live` (the tool's reason to exist — a bounded live run → `faithful`/`enhanced`/`divergence`, `RD_cum` monotonic); `.reconstruction:"faithful"` (emit omits enhanced steps); `.physical_sky_smarts`.
- **G5.9** `weather.timestep_min` (open knob; 6-min → 10× rows); `.bad_period` (`ValueError`); `.subset_no_wea` (warning, no crash); `.subset_overrun` (6-min lines over an hourly `.wea` → `ValueError`).
- **G5.10** `nvrd.dt_too_big` (`timestep_h:0.5` → `ValueError`); **`.even_filter`** (`timestep_h:0.2` → even-length `ValueError`, the DEF-6 guard — the one plausible-but-broken step in (0,0.3]); `.bad_row_len`; `.hours_nonmono`; `.file_path` (recommended transport + not-found raise).
- **G5.11** `sensors.overwrite_raise`; `.unknown_name` (get/delete → `ValueError` listing available); `.bad_action`; `.no_name`/`.no_source`; `.reuse_chain` (live `sensor_set=` resolved by annual_daylight **and** daylight_factor **and** daylight_savings). *(W6.8 asserts these but captured only a template — capture them live.)*
- **G5.12** `generate_subhourly_wea.bad_timestep` (`timestep_min:7` → `ValueError` naming the `{1,2,3,4,5,6,10,12,15,20,30}` set); `.timestep_60` (same raise — the hourly-mistake case); `.site_override`; `.emit`.
- **G5.13** `build_daysim.run_no_tools` (low priority) — in an env w/o cmake, `run:true` → `ran:false`+`reason`, not a crash (skip-with-reason if cmake always present).

### G6 — Untested `raise` guards (the "silent wrong answer" class this kit exists for)

Consolidate these into the **N** section (one block each: call · expected typed error · guard). A plausible mistyped
call reaches every one; none currently fire:

| Guard                                                                            | Call that trips it                                             | Expected                                             |
| -------------------------------------------------------------------------------- | -------------------------------------------------------------- | ---------------------------------------------------- |
| `nvrd` even filter                                                             | `nvrd {timestep_h:0.2}`                                      | `ValueError` (even filter length)                  |
| `nvrd` dt cap                                                                  | `nvrd {timestep_h:0.5}`                                      | `ValueError "<= 0.3 h"`                            |
| `lighting_controls` schedule len                                               | `{itot_series:len10, schedule:len8}`                         | `ValueError "schedule length … must match"`       |
| `daylight_savings` weights sum                                                 | `{points:2pts, weights:[0.7,0.6]}`                           | `ValueError "sum(weights) … exceeds 1.0"`         |
| `daylight_savings`/`lighting_controls` weight count                          | `{points:2, weights:[1.0]}`                                  | `ValueError "one entry per reference point"`       |
| `daylight_savings` mode                                                        | `{mode:"annual_x"}`                                          | `ValueError "must be 'point_in_time' or 'annual'"` |
| `run_annual` channel count                                                   | `{channel_scenes:[1], channel_type:1}`                       | `ValueError "needs 3 channel scene(s)"`            |
| `annual_daylight` occupancy len                                                | `{occupancy:[1,0,1]}` vs N ts                                | `ValueError "occupancy length … must match"`      |
| `sensors` overwrite / unknown / action                                         | dup create / get bad name /`action:"rename"`                 | 3 distinct`ValueError`s                            |
| `generate_subhourly_wea` timestep                                              | `{timestep_min:7}`                                           | `ValueError` naming the allowed set                |
| `weather` period / overrun                                                     | `{period:[[6,21]]}` / 6-min over hourly                      | `ValueError`                                       |
| `colored_sky` irrad/mode                                                       | `{irrad_mode:"G"}` / `{mode:"x"}`                          | `ValueError`                                       |
| `spectral_sky_from_epw` engine/len                                             | `{engine:"bogus"}` / `{spectral_albedo:[…2…]}`           | `ValueError`                                       |
| `ies_to_radiance` units/placement                                              | `{units:3}` / `{placement:{foo:1}}`                        | `ValueError`                                       |
| `colored_luminaire` count/len                                                  | `{count:3}` / `{channels9:[…3…]}`                        | `ValueError`                                       |
| `recommend_fixtures` guards                                                    | bad distribution / mount≤workplane / vhr≤0 / em≤0+circadian | 4`ValueError`s                                     |
| `import_geometry` units/refl/unmaterialized                                    | `{units:"in"}` / missing `refl` / pre-usemtl faces         | 3`ValueError`s                                     |
| `ies_analyze` parse                                                            | no-TILT / truncated grid                                       | 2`ValueError`s                                     |
| `photosensors`/`workplane_grid`/`observer_points`/`preview_scene` no-map | omit map+sidecar                                               | `ValueError` each                                  |

### G7 — Input fixtures that unlock the above (data actions — not defects)

> **Fixture discipline (added 2026-07-30).** A section whose **Call** names a file that does not ship cannot
> be scored PASS — score it **BLOCKED (missing fixture)** and list the fixture here. Two rows were violating
> this: **W2.10**'s mm leg (now **fixed** — `office_room_mm.obj` + `office_room_mm_material_map.json` ship as
> of 2026-07-30, and the leg is captured live) and **W2.6a**'s concave leg (now honestly re-scored
> **PARTIAL/BLOCKED**). Check the remaining rows below against this rule before scoring them.

- ✅ **`office_room_mm.obj`** (+ `.mtl` + `office_room_mm_material_map.json`, `units:"mm"`) — **SHIPPED
  2026-07-30.** `office_room.obj` with vertices ×1000. Unlocks **W2.10**'s units leg (ADR-0002). Verified:
  reports `ok:true` with a report **identical** to the metre model.
- **`office_room_lit.obj`** = `office_room.obj` + one `type:"luminaire"` group (L09 IES + 9-ch SPD) → unlocks
  G2.3, G4.5.electric, G4.6.electric, G5.1.electric, G5.7.electric, **W5.4 / E4 / S3-room / S5-combined** (the
  standing **A-1** action — the only "daylight + electric" rows still PENDING).
- **A Y-up OBJ** (or re-export of `office_room`) → unlocks **G0(b)** across all five geometry tools at once.
- **An L/T/U room OBJ** → turns **W2.6a**'s concave leg from **BLOCKED** into a real captured test (today it
  quotes the feature's own verification) and unlocks G2.7.clip_false.
- **IES variants**: a type-B/type-A `.ies`, an absolute-photometry `.ies` (lumens=−1), a `TILT=INCLUDE` `.ies`, a
  multi-horizontal `.ies` → unlock G4.1.
- **A no-glass OBJ** and **a no-floor OBJ** → G2.11.no_glass, G2.13.no_floor.

---

## A — Advisories (NEW 2026-07-30 — the caller-facing warning surface)

> **Why this section exists.** Advisories attach at the **tool-registration seam**
> (`hcl_mcp/advisories.py` + `_with_advisories`/`_attach` in `server.py`, ADR-0005), so **every one of the
> 46 tool functions / 50 registered names** can carry them wherever the result is a dict. They were shipped
> after this plan's last revision and were covered **nowhere** — the same "registered but untested" hole as
> `check_geometry` (W2.10) and `quality_presets` (W0.5/DEF-QP-REG).
>
> This is precisely the class of defect the kit exists to catch. Its own **DEF-ENVELOPE** lesson —
> *"assert that a field arrives in the caller's hands, not merely that some function can produce it"* — was
> learned from a warning that was computed correctly and then dropped by the server envelope. An advisory
> that never reaches the caller fails silently and **in the safe-looking direction**: the number still looks
> right. Unit tests import `advise()` directly and would pass throughout. **Assert through the live MCP
> tool return, never by importing the rule.**
>
> Advisories are **reporting, not physics**: each rule re-reads a field the tool already computed. So an
> advisory must never change a number — A9 pins that.

Write to `A-advisories/`. Most IDs are pure-Python and need no engine.

### A1 — MEL_DER_BINNED (warn)

- **Call:** `circadian_metrics {"channels":[0.1,0.12,0.2,0.3,0.35,0.33,0.25,0.18,0.12],"channel_type":1}`
  (no `spd=`), then the same call **with** `spd:"INPUTS/spd/L09_neutral.spd"`.
- **Assert:** without `spd` → `advisories` contains `MEL_DER_BINNED`, `severity:"warn"`,
  `field:"mel_der_source"`, and `result.mel_der_source == "binned_channels"`. **With `spd`** → the route
  flips to `mel_der_source:"spd_transported"` (was `"spd"` before 2026-08-01, ADR-0006) and
  `MEL_DER_BINNED` is **absent**; a `SPECTRAL_TRANSPORT_SHIFT` advisory may appear in its place if the
  channels imply a ≥5% spectral shift from the source. (This is the case W1.4 already asks for
  under "Add a case that passes `spd=` and asserts the route flips" — now it also asserts the advisory.)
- **Captured (2026-07-30, live via MCP):** `mel_der_source:"binned_channels"`, `mel_der:0.7247951839781853`,
  `mel_edi:37.35105746098524`, and
  `advisories:[{"code":"MEL_DER_BINNED","severity":"warn","field":"mel_der_source","message":"mel-EDI was inferred from binned channels… up to ~8% high for a narrow-band source…"}]`.
- **Result:** PASS (live).

### A2 — ALBEDO_NOT_MEASURED (warn) — fires on this kit's own EPW

- **Call:** `atmosphere_from_epw {"epw":"INPUTS/weather/GRC_Athens.167160_IWEC.epw","month":5,"day":13,"hour":12}`
- **Assert:** `provenance.albedo.source == "default"` **and** `advisories` contains `ALBEDO_NOT_MEASURED`
  (`warn`, `field:"albedo"`). Then repeat through **`spectral_sky_from_epw`**, where the same
  `AtmosphericState` is nested one level down under `atmosphere.provenance` — the rule must fire on **both
  shapes** (ADR-0004; the nested check exists so the higher-traffic tool isn't silently uncovered).
- **⚠️ Why the Athens sample triggers it:** IWEC/TMY2 files write a literal `0.000` albedo for every hour
  instead of the `999.0` missing-data sentinel. `hcl_core` treats sub-physical values as missing and
  substitutes the documented default (ADR-0004). Substituting is correct; **reporting it as measured is
  not** — and a zero albedo taken as real shifts diffuse irradiance on a tilted/vertical receiver
  substantially. The kit's only shipped EPW is one of these files, so this advisory is on for every
  spectral-sky run in the plan.
- **Captured (2026-07-30, live via MCP):** `albedo:0.2`, `provenance.albedo:{"source":"default","method":"fixed"}`,
  `aod500:0.178` (`source:"epw"`), `pw_cm:2.691` (`source:"epw"`, gueymard94), and
  `advisories:[{"code":"ALBEDO_NOT_MEASURED","severity":"warn","field":"albedo",…}]`.
- **Result:** PASS (live). *`spectral_sky_from_epw` nested-shape leg: to capture.*

### A3 — DOSE_THRESHOLD_IS_DEFAULT (info)

- **Call:** `run_annual {…, "dosimetry_threshold":250}` (or omitted) over the W6.2 tight period; then
  re-run with `dosimetry_threshold:275`.
- **Assert:** threshold 250.0 → `advisories` contains `DOSE_THRESHOLD_IS_DEFAULT`, `severity:"info"`,
  `field:"dosimetry.threshold"`. Threshold 275 → **absent**.
- **⚠️ The rule is value-based, not provenance-based, and this is not a defect:** FastMCP fills unset
  parameters with their declared default *before* the tool function runs, so by the time the wrapper sees
  the call a deliberate `250.0` and an omitted argument are **indistinguishable**. Both therefore advise.
  Do not score "it fired even though I passed 250 explicitly" as a FAIL — that is the documented contract.
- **Result:** PENDING (live) — needs a `run_annual` pass; fold into the W6.2 run rather than a new sim.

### A4 — ZONE_WEIGHT_REMAINDER (warn) — the Σw≈0.707 trap, live

- **Call:** `lighting_controls {"itot_per_point":[320,180],"weights":[0.35,0.3535],"iset":500}`; then the
  same with `weights` summing to 1.0; then `daylight_savings` with a short-summing `weights`.
- **Assert:** Σw < 1 − eps → `ZONE_WEIGHT_REMAINDER` (`warn`, `field:"weights"`) quantifying the remainder;
  Σw == 1.0 → **absent**. The advisory fires on **both** `lighting_controls` and `daylight_savings` and on
  **neither** other tool (it is tool-gated).
- **⚠️ Why these exact weights.** `0.35 + 0.3535 = 0.704` is the **`photosensors` zone-weight convention**
  (Σw ≈ 0.707), not floor-area fractions. Σw < 1 is *documented, intended* behaviour — the remainder is
  uncontrolled floor billed at full power — so the advisory **quantifies** rather than rejects. It is a real
  defect only when the weights came from the other convention, which is exactly the substitution that
  silently changes a savings number (54% vs 79% on one room) without changing the result's shape.
  Cross-reference **X7**, which pins the same two-helpers-one-room divergence.
- **Captured (2026-07-30, live via MCP):** `FP:0.6857`, `P_elec:307.20`, `P_saved:140.80`, `reduction:0.3143`,
  and `advisories:[{"code":"ZONE_WEIGHT_REMAINDER","severity":"warn","field":"weights","message":"Zone weights sum to 0.704, so 29.6% of the floor is billed at full power as uncontrolled core…"}]`.
- **Result:** PASS (live).

### A5 — GEOMETRY_HEALTH_UNCLEAN (error **or** warn) — both carriers

- **Call:** `check_geometry {"obj_path":"INPUTS/geometry/office_room.obj","sidecar":"INPUTS/geometry/office_room_material_map.json"}`
  (report returned **top-level**), then `import_geometry {…}` on the same OBJ (same report **embedded**
  under `health`).
- **Assert:** the advisory fires on **both carriers** — `check_geometry` returns `ok`/`counts`/`findings` at
  the top level with no wrapper, `import_geometry` nests them under `health`. Severity is **`error` iff
  `health.ok` is false**, else `warn`. When `health` is the carrier the advisory sets `field:"health"`; on
  the top-level shape it sets **no `field`**. A clean report (`ok:true` **and** `counts.warning == 0`)
  produces **no** advisory.
- **⚠️ It must NOT fire on a non-empty `skipped`.** `skipped` is structurally never empty — the tier-1
  checker appends the unimplemented categories plus `sensors` and `luminaires` on every branch — so
  triggering on it would warn on every import, spotless included. Skipped categories are *named* once the
  rule has already fired, as context.
- **Captured (2026-07-30, live via MCP, `office_room.obj`):** `ok:true`, `counts:{"error":0,"warning":1,"info":0}`,
  one finding `NOT_ENCLOSED` (*"20 boundary edge(s) belong to only one face"*, subjects
  `Rad_Glazing_T073` + `Rad_Luminaire_L09`), `skipped` = materials/apertures/conventions/sensors/luminaires,
  and `advisories:[{"code":"GEOMETRY_HEALTH_UNCLEAN","severity":"warn","message":"…1 warning(s); not checked: materials, apertures, conventions, sensors, luminaires…"}]` — **no `field` key**, confirming the
  top-level-carrier branch. Severity `warn` (not `error`) because `ok` is true.
- **📌 The reference model is not silent — this warning is EXPECTED.** `office_room.obj` legitimately
  reports 1 warning; see W2.10. Score a *new* finding, or `ok:false`, as the regression.
- **Result:** PASS (live, `check_geometry` carrier). *`import_geometry` embedded-carrier leg: to capture.*

### A6 — NVRD_ZERO_DIVERGENCE (warn)

- **Call:** `annual_nvrd {…}` (W8.3's run) and read `divergence.neutral_vs_colored_sun.mel_edi_pct`.
- **Assert:** when that value is **exactly 0** → `NVRD_ZERO_DIVERGENCE` (`warn`,
  `field:"divergence.neutral_vs_colored_sun"`); non-zero → absent. Tool-gated to `annual_nvrd`.
- **⚠️ Zero is an artefact, not agreement.** The single-shot comparison picks one representative timestep;
  when that lands pre-sunrise every sun channel is 0, so neutral and coloured suns agree *exactly* and the
  divergence reads 0 — while the true series value is non-zero. **Quote `RD_series_divergence` instead.**
  A tester who reports "0% divergence ⇒ the sun spectrum doesn't matter" has inverted the finding.
- **Result:** PENDING (live) — fold into W8.3.

### A7 — Absent when clean (the contract that keeps advisories readable)

- **Call:** `spd_to_channels {"spd":"INPUTS/spd/L09_neutral.spd","channel_type":1}` and
  `spectral_metrics {"spd":"INPUTS/spd/L09_neutral.spd"}`.
- **Assert:** the `advisories` **key is absent entirely** — not `[]`. Emitting an empty list on every clean
  result would train callers to stop reading the field, which is the failure mode the whole surface is
  designed against. Also assert `_attach` returns a **new** dict (the tool's own keys are unchanged and
  un-mutated).
- **Captured (2026-07-30, live via MCP):** `spd_to_channels` → `{"channels":[…9…],"channel_type":1}`;
  `spectral_metrics` → `{"cct_duv":{"cct_K":3985.2,…},"mel_der":0.6103,…}`. **Neither carries an
  `advisories` key.**
- **Result:** PASS (live).

### A8 — The documented v1 gap: list returns carry NO advisories

- **Call:** `circadian_metrics` with **multi-point** input, e.g.
  `{"channels":[[0.1,0.12,0.2,0.3,0.35,0.33,0.25,0.18,0.12],[0.2,0.22,0.3,0.4,0.45,0.43,0.35,0.28,0.22]],"channel_type":1}`
- **Assert:** the return is a **list** of per-point dicts and carries **no** `advisories` — `_attach` passes
  non-dict results through untouched, because wrapping a list would change the tool's published contract.
  **This is the documented v1 gap, so its absence IS the pass.** Assert instead that `mel_der_source` is
  present **per point** so the caller can still make the binned-vs-spd judgement by hand.
- **⚠️ `circadian_metrics` with multi-point input is the ONLY tool in this class** — every other tool
  returns a dict. Do not generalise the gap.
- **Captured (2026-07-30, live via MCP, 2 points):** a bare 2-element list; point 1 `mel_edi:37.351`,
  point 2 `mel_edi:53.629`; **both** carry `mel_der_source:"binned_channels"` + `mel_der_note`; **no
  `advisories` key anywhere in the return.**
- **Result:** PASS (live) — behaviour matches the documented contract exactly.

### A9 — Advisories are reporting, not physics (the invariant)

- **Call:** any A1–A6 pair above, advisory-firing vs not.
- **Assert:** **no computed value changes** when an advisory fires. Strip `advisories` from the return and
  the remaining dict must be identical to the same call made before the feature existed — every W/X/E
  capture in this plan predates advisories and must still reproduce **byte-for-byte**. A rule that raises is
  **skipped silently** (`advise()` never raises), so a broken rule can never fail a tool call.
- **Evidence already in hand (2026-07-30):** W1.2's channel vector and W1.5's
  `cct_K 3985.2 / mel_der 0.6103 / mel_edi 610.4956 / eml 673.38` re-ran live **byte-identical** to their
  2026-06-29 / 2026-07-25 captures — with the advisory layer live in between.
- **Result:** PASS (live, by reproduction).

### A10 — Aliases resolve to the FUNCTION name at the seam

- **Call:** `get_reference {"topic":"coefficients"}` (alias of `reference`), and any tool-gated rule.
- **Assert:** `_attach` is handed `fn.__name__`, so a call through an **alias** presents the *underlying
  function* name to the rules — `get_reference` → `reference`, `list_presets` → `presets`,
  `import_weather` → `weather`, `run_validation` → `validate`. Tool-gated rules
  (`ZONE_WEIGHT_REMAINDER` on `lighting_controls`/`daylight_savings`, `NVRD_ZERO_DIVERGENCE` on
  `annual_nvrd`) must therefore behave **identically** through either name.
- **Today this is latent, not live:** none of the 4 aliases map to a tool-gated rule, so nothing misfires
  now. Pin it anyway — the next alias added over a gated tool is where it bites.
- **Result:** PENDING (add).

---

## Prompts coverage (invoke each MCP prompt; confirm a coherent scripted plan)

**Honesty note.** MCP **prompts are slash-commands a human triggers** (`/mcp__hcl-mcp__<name>`); they
cannot be invoked by a tool call, so this kit validates each prompt's *scripted tool sequence* against the
live W-runs above rather than rendering the prompt text here. To exercise a prompt as a real user, type its
slash command in the main chat (GUIDE Part 5.3). Each row's underlying chain is **live-validated**:

| Prompt (`/mcp__hcl-mcp__…`)         | Scripts the live-validated sequence                                                                                                                                                                                                                                                                 | Status                                          |
| -------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------- |
| `spd_to_circadian`                   | W1 (spd_to_channels→alpha_opic→spectral_metrics→compliance)                                                                                                                                                                                                                                      | chain PASS (W1)                                 |
| `hcl_grid_study`                     | W2→W3 (import_geometry→colored_sky→run_grid→circadian_metrics→compliance)                                                                                                                                                                                                                      | chain PASS (W2/W3)                              |
| `fisheye_eye_analysis`               | W4 (run_image fov_weighting→glare_ugr); 9-ch ×179 eye conversion                                                                                                                                                                                                                                  | chain PASS (W4)                                 |
| `annual_circadian_dose`              | W6 (weather→run_annual)                                                                                                                                                                                                                                                                           | chain PASS (W6)                                 |
| `annual_daylight_study`              | W6.8→W6.6→W6.5→W6.7 (`sensors` create → `annual_daylight` DA/UDI/sDA/ASE → `daylight_factor` DF → `daylight_savings(mode="annual")`, all over `sensor_set`)                                                                                                                         | chain PASS (W6.5–W6.8, live toy scene)         |
| `explain_concept`                    | reads`hcl://reference/*` (no tool calls)                                                                                                                                                                                                                                                          | resources PASS (W0.4 + table)                   |
| `electric_lighting_design`           | W5 (ies_analyze→ies_to_radiance→run_grid+electric→daylight_savings→compliance) +**E (annual kWh, control_type laws)**                                                                                                                                                                     | chain PASS (W5/E; combined leaf = W5.4/E4 gap)  |
| `annual_alertness`                   | W8 (generate_subhourly_wea→annual_nvrd)                                                                                                                                                                                                                                                            | chain PASS (W8)                                 |
| `hcl_studio`                         | recommend_fixtures→save_brief→[sims]→build_report (0–8 phases);**annual energy → brief.energy → report (S5)**                                                                                                                                                                           | chain PASS (W5.7/W9/S4); S5 energy PENDING live |
| `import_obj_room`                    | W2 (dry_run→map→derive_sensors→run)                                                                                                                                                                                                                                                              | chain PASS (W2)                                 |
| `spectral_sky_from_epw`              | W7 (atmosphere_from_epw→spectral_sky_from_epw→alpha_opic/spectral_metrics)                                                                                                                                                                                                                        | chain PASS (W7)                                 |
| `place_sensors`                      | W2.6→W2.7→W2.8→W2.9 (confirm geometry → workplane_grid EN math → observer_points workstations/fallbacks →**photosensors** daylight-dimming zones → **preview_scene** final visual placement check → hand `grid.pts`→run_grid + observer `.pts`+`glare_views`→glare_ugr) | chain PASS (W2.6–W2.9)                         |
| `visualize_scene` (NEW, 13th prompt) | guided PNG preview flow: ensure OBJ+material_map → generate/locate grid/observers/photosensors`.pts` (W2.6/W2.7/W2.8) → `preview_scene(render="all", …)` (W2.9) → report `image_paths` (diagnostic overlays, explicitly not a photometric render)                                         | chain PASS (W2.6/W2.7/W2.8/W2.9)                |

When you do drive each prompt: confirm the returned guidance is coherent, references **real** tool names,
and matches the sequence above.

---

## Resources coverage (read each via the MCP resource API)

All 14 read live via the MCP resource API (2026-06-29).

| URI                                        | Captured (2026-06-29)                                                                                                                                                                                                                                                                            | Result |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------ |
| `hcl://index`                            | JSON catalog of all 14 resources w/ titles, mime types, tags + template arg-value lists (`preset.name`=20 illuminants; `action-spectrum.type`=S/M/L/rhod/mel/V/D65; `compliance.standard`=6 incl. `en_12464_1`,`ul_24480` — **all 6 accepted by the tool**, matching the core). | PASS   |
| `hcl://reference/coefficients`           | `melanopic_9` (Σ≈1), `photopic_3=[0.265,0.67,0.065]`, `luminous_efficacy=179` (see W0.4).                                                                                                                                                                                                | PASS   |
| `hcl://reference/bins`                   | `bins_9=[[380,419]…[630,780]]`, `bins_3=[[587,780],[499,587],[380,499]]`.                                                                                                                                                                                                                   | PASS   |
| `hcl://reference/ies`                    | LM-63 field guide: data-line-1/2 layout, TILT block consume rule, effective-candela = raw×mult×ballast×pfactor (not folded into`ies2rad -m`), zonal-flux/LOR formulas.                                                                                                                      | PASS   |
| `hcl://reference/lighting-controls`      | EnergyPlus §7.3.5:`fL`, `fP` (Continuous/ContinuousOff/Stepped), `FP=Σ fP·W+(1−ΣW)`, `P_saved`, defaults (Iset 500, fP_min 0.15…).                                                                                                                                                 | PASS   |
| `hcl://reference/daysim`                 | Daysim build-from-source (clone+cmake headless arm64),`epw2wea`/`ds_shortterm` I/O, NRC/ISE EULA credits.                                                                                                                                                                                    | PASS   |
| `hcl://reference/nvrd-bridge`            | annual→nvRD dual reconstruction (faithful vs enhanced) + 5 honesty caveats (R_D relative, §9.3a constant scales, neutral-sun bias, ±20% envelope).                                                                                                                                            | PASS   |
| `hcl://reference/geometry`               | full`import_geometry` contract: material-map shape, 6 surface types, obj2rad qualifier rule, units/axis/north, per-channel assembly, v2/v3 conveniences, honest limits; now also documents `photosensors`, `preview_scene`, and footprint clipping.                                        | PASS   |
| `hcl://reference/caveats`                | §9.3 source-port fixes (float-division, 9-ch ordering, image-vs-grid b3) — markdown.                                                                                                                                                                                                           | PASS   |
| `hcl://reference/glossary`               | mel-EDI / EML (≈×1.103) / mel-DER / CCT-Duv / α-opic / photopic-melanopic-neuropic / channel_type — markdown.                                                                                                                                                                                | PASS   |
| `hcl://compliance/en_12464_1`            | full EN 12464-1:2021 task table (office 500/UGR19/Uo0.6/Ra80, technical-drawing 750/16/0.7, …) + surround/background/wall/ceiling/cylindrical relationships.                                                                                                                                    | PASS   |
| `hcl://preset/D65` (template)            | `{name, spd}` — D65 SPD as 401 `[nm,val]` pairs. **No `meta` key here** (the `meta{family,illustrative,source}` block lives only in the `presets` **tool** response, W1.1 — the resource is SPD-only).                                                                   | PASS   |
| `hcl://action-spectrum/mel` (template)   | `{type, start_nm:380, step_nm:1, values}` — the curve is the 401-value `values` array (**not** an `spd` key), 1-nm melanopic, peak **1.0 at 490 nm**, tails to ~2e-8 at 780.                                                                                                  | PASS   |
| `hcl://compliance/brown_2022` (template) | threshold table: daytime ≥250, evening ≤10, sleep ≤1, night ≤10 lx mel-EDI; "vertical at eye".                                                                                                                                                                                               | PASS   |

---

## Coverage ledger (every registered name hit ≥ once)

**Tools (46 — the full registered set; this list is the authority, so every name below must appear here
even if it is also discussed in a dated "New tools" paragraph further down):** spd_to_channels W1.2 · glass_transmissivity W3.1 · write_material W3.2 ·
circadian_metrics W1.4 · alpha_opic W1.3 · validate W0.1 · spectral_metrics W1.5 · compliance W1.6 ·
presets W1.1 · colored_sky W3.3 · colored_luminaire W5.3 · reference W0.4 · run_grid W3.4 · run_image
W4.1 · import_geometry W2 · radiance_status W0.2 · weather W6.1 · run_annual W6.2 · nvrd W6.4 ·
ies_analyze W5.1 · ies_to_radiance W5.2 · glare_ugr W4.2 · lighting_controls W5.5 ·
daylight_savings W5.6 · daysim_status W0.3 · build_daysim W8.2 · generate_subhourly_wea W8.1 ·
reconstruct_spectrum W1.7 · annual_nvrd W8.3 · recommend_fixtures W5.7 · atmosphere_from_epw W7.1 ·
spectral_sky_from_epw W7.2 · spectral_epw W7.5 · spectral_sky_native W7.6 · save_brief W9.2/S4 ·
load_brief W9.1/S4 · build_report W9.3/S4 · workplane_grid W2.6/W2.6a · observer_points W2.7/W2.7a ·
photosensors W2.8 · preview_scene W2.9 · **quality_presets W0.5** (45th tool — registered 2026-07-23) ·
**check_geometry W2.10** (46th tool — test added 2026-07-25) · daylight_factor W6.5 · annual_daylight W6.6 ·
sensors W6.8.
**Aliases (4):** run_validation W0.1 · get_reference W0.4 · list_presets W1.1 · import_weather W6.1.
**Advisories (6 codes + the list-return gap):** section **A** — A1 MEL_DER_BINNED · A2 ALBEDO_NOT_MEASURED ·
A3 DOSE_THRESHOLD_IS_DEFAULT · A4 ZONE_WEIGHT_REMAINDER · A5 GEOMETRY_HEALTH_UNCLEAN ·
A6 NVRD_ZERO_DIVERGENCE · A7 absent-when-clean · A8 the `circadian_metrics` multi-point list gap.

> **Ledger discipline (why this list is now the authority).** `check_geometry` was registered the whole
> time, got a test at **W2.10** on 2026-07-25, and *still* did not appear in this ledger — the head-count
> stayed at 44 while the surface was 46. The dated "New tools"/"Removed" paragraphs below are **historical
> records of the head at the time**, not a coverage list; reading them as one is exactly how a tool goes
> missing. **Rule: when a tool is registered or removed, edit THIS list first.** Verify against the live
> server (`mcp._list_tools()` → 50 names = 46 unique + 4 aliases), never by counting paragraphs.
**Prompts (13)** + **Resources (14):** sections above (the 12th prompt, `annual_daylight_study`,
scripts the W6.5–W6.8 daylight-metrics chain; the 13th prompt, `visualize_scene`, scripts the
W2.6–W2.9 sensor/preview chain).

**New tools (annual climate-based daylight metrics — hcl-mcp, merged; +3 registered tools taking
the head to 43 tools / 47 names / 12 prompts, then +2 more geometry/preview tools taking it to
**45 tools / 49 names / 13 prompts**): `daylight_factor` W6.5 · `annual_daylight` W6.6 ·
`sensors` W6.8 (named persistent sensor sets) · plus `daylight_savings(mode="annual", multi-point)`
W6.7 (extends the existing `daylight_savings` entry, not a new tool name) · and the guided
`annual_daylight_study` prompt (Prompts coverage table).**

- `daylight_factor`: LIVE — found + fixed a real bug (`overcast_sky.rad` never written before the
  indoor `run_grid` on a `run=True` call; see W6.5). Fixed + regression-tested in hcl-mcp
  commit `9152c57`.
- `annual_daylight`: LIVE over a 1-week/168-h subset (30-pt grid). **Wiring gap found (not fixed,
  out of Task 16 scope):** neither `run_annual_daylight` nor the `annual_daylight`/`daylight_savings (mode="annual")` MCP tools accept a `period` argument (unlike `run_annual`), so a short live smoke
  run required subsetting the `.wea` by hand via `hcl_core.weather.subset_wea` before calling the
  core function directly. Relatedly, the MCP tool layer never passes `partial_year=True` into
  `hcl_core.daylight_metrics.daylight_metrics`, so even a period-subsetted run (once `period` support
  is added) wouldn't currently surface `partial_year` in the tool's response. Flagging for a future
  task: thread `period`/`timestep_min` through `run_annual_daylight` the same way `run_annual`
  already does, and pass `partial_year=(period is not None)` from the `annual_daylight` /
  `daylight_savings(mode="annual")` server tools.

**Newest tools (geometry-driven sensor placement + matplotlib PNG visualization, 2026-07-01 — +2
registered tools taking the head to 45 tools / 49 names / 13 prompts): `photosensors` W2.8 ·
`preview_scene` W2.9 · plus `workplane_grid` concave/footprint-clip support W2.6a and
`observer_points` footprint check W2.7a (both extend existing tool entries, not new tool names) ·
and the new `visualize_scene` prompt (Prompts coverage table).**

**Removed (melanopic source attribution, 2026-07-17 — −1 registered tool taking the head from
45 tools / 49 names back to **44 tools / 48 names / 13 prompts** *as of that removal*): `annual_attribution`
and its **W6.3** entry are gone — the engine moved to a companion study, a separate repository.
(Registering `quality_presets` on 2026-07-23 took the head back to **45 tools / 49 names**; recognising
`check_geometry` — registered all along, never listed — corrected it to the true **46 tools / 50 names**.)
The paragraphs above are **dated records of the head at the time those tools were added**, so they still
read 43/45/49. **They are NOT a coverage list — the enumerated ledger at the top of this section is.**
Reading these paragraphs as coverage is precisely how `check_geometry` stayed invisible: its head-count
arithmetic was maintained here while the tool itself was never added to the list.
The W6.x numbering is left with a **gap at W6.3** deliberately, because W6.4–W6.8
are referenced by the coverage tables and the `annual_daylight_study` prompt chain.**

- `photosensors` is **pure-Python `hcl_radiance`, no binaries** — like `workplane_grid`/
  `observer_points`, it always runs regardless of Radiance/Daysim/SMARTS availability.
- `preview_scene` is pure-Python `hcl_radiance` but **requires matplotlib** (renders via the `Agg`
  backend, `hcl_radiance/scene_preview.py`) — it still invokes **no Radiance binary**, but will fail
  if matplotlib isn't installed.
- `preview_scene` is explicitly a **diagnostic overlay** (placement verification), **not** a
  photometric render — contrast with `run_image` (Radiance `rpict`).
- Non-rectangular room support: rectangular + convex fully work; concave (L/T/U) now works
  end-to-end via the new footprint-bbox fallback in `workplane_grid` (W2.6a).

**Argument-level / mode coverage (v2.1):** `lighting_controls` `itot_series`→annual E1 · `control_type`
{ContinuousOff, Continuous, Stepped} E3 · `daylight_savings` `mode="annual"` E2/S5 · combined
`run_grid(electric_lights)` E4 (pending luminaire OBJ) · energy cross-checks E5a/E5b · annual-mode
multi-point negative N-E1. **Still-open knobs** listed in the E-section honest ledger (workbook_compat,
explicit schedule list, combined-glare electric fisheye, compliance daylight_met, weather timestep_min,
run_annual rad_params).

**Argument / mode / error-path coverage (v2.3):** section **G** enumerates ~80 untested kwargs, output-shape
branches, and `raise` guards across all 46 tools (G1 spectral · G2 geometry/sensors · G3 sky/EPW · G4
electric · G5 annual/energy) — plus **G6** (every untested typed-error guard, to fold into **N**) and **G7**
(the input fixtures that unlock the electric/Y-up/L-room/IES-variant rows). These are DEPTH additions to the
already-complete surface coverage above; each is scored PENDING (add) until captured.

---

## Final report — structured, one folder per workflow

Outputs are **two layers** so a reviewer can drill from a summary into any single workflow:

- **Per-section `results/<SEC>/RESULTS.md`** (see Conventions) — every ID in that section with its exact
  call, the **actual captured metric values**, the Assert verdict, the score, and links to the section's
  data files + `work/` intermediates. This is where the numbers and Radiance artifacts live, grouped by
  workflow.
- **Top-level `results/VALIDATION-REPORT.md`** — the index/roll-up over the sections:

1. **Capability banner** — Radiance/Daysim/SMARTS status from W0.
2. **Results matrix** — every W/N/X/S ID with score + the key captured value + the Assert verdict, **each
   row linking to its section folder** (e.g. a link labelled `W3.4` pointing at `W3-grid/RESULTS.md`); full per-ID detail stays in the
   section `RESULTS.md`.
3. **Coverage** — N/46 tools, N/4 aliases, N/13 prompts, N/14 resources, **N/6 advisory codes + the 4
   contract properties (A7 absent-when-clean · A8 list-return gap · A9 reporting-not-physics · A10 alias
   naming)**; **plus mode/argument coverage**
   (E-section: `itot_series`, `mode="annual"`, the 3 `control_type` laws, combined electric, energy
   cross-checks). List skips + why — incl. the still-open knobs from the E-section honest ledger.
   **Also report G-section depth coverage** — how many of the ~80 argument/mode/error-path gaps (G1–G5),
   the G6 typed-error guards, and the G7 fixtures were captured vs still PENDING(add). A tool counts as
   "happy-path covered" from W/N/X/S/E even with open G-gaps; call out which branches/raises remain dark.
4. **Defects** — any FAIL/PARTIAL with the exact call, observed-vs-expected, severity, hypothesis.

   Found while refreshing the plan (2026-07-23):
   - **DEF-ENVELOPE (server bug — FIXED):** `annual_daylight`'s `convergence_warning` never crossed the
     MCP boundary. `run_annual_daylight` set it, but the server's success envelope forwarded only
     `n_points`/`n_timesteps`/`metrics`, dropping both the warning and the `rad_params` that produced it.
     Found by the **first live `annual_daylight` call after the client restart** — the return had no
     warning while the same parameters flagged fine in-process. Third instance of one pattern in this
     batch (**DEF-QP-REG**, this, and the units seam): the computation is right, the *surface* is dark,
     and every test exercises the helper rather than the tool. **The lesson generalises — assert that a
     field arrives in the caller's hands, not merely that some function can produce it.**
   - **DEF-VERDICT (test-plan bug — CORRECTED, highest severity of this batch):** W3.4 and W3.5 scored
     `melanopic_lux` **260.65** against Brown's **250 lx mel-EDI** threshold and recorded **PASS**. The
     correct quantity for that eye point is mel-EDI **237.03**, which **FAILS by 12.97 lx** — so the kit
     had a shipped, wrong compliance verdict, not merely a mislabelled number. Verified live:
     `compliance(mel_edi=260.65)` → `pass`, `compliance(mel_edi=237.03)` → `fail`. Wide-margin scenes
     absorb the ~9% gap; this one straddles the threshold. Pinned by
     `test_the_units_confusion_can_flip_a_verdict_near_the_threshold`. **This is the counterexample to
     "the units seam is a disclosure issue, not a results issue" — near a threshold it is both.**
     Note `compliance`'s `quantity` stamp cannot catch it: the label records what the caller claimed,
     so only reading `mel_edi` off `circadian_metrics` prevents it.
   - **DEF-QP-REG (server bug — FIXED):** `quality_presets` was defined, docstringed and unit-tested but
     **left out of `server.py`'s registration tuple**, so `mcp._list_tools()` returned 48 names without
     it and no MCP client could call it — while `quality=` was already accepted by eight simulation
     tools. Every existing test imported the function directly (`from hcl_mcp.server import
     quality_presets`) and so passed throughout. **Fixed:** added to the tuple (49 names now), plus
     `test_quality_presets_is_actually_registered_as_a_tool`, which asserts through the server's own
     tool list. `test_server.py`'s hardcoded `len(names) == 48` updated to 49. Suite 1433 passed / 7
     skipped. **Lesson: a unit test that imports the function does not prove the tool is exposed.**
   - **DEF-INLINE-MAP (interface sharp edge — FIXED 2026-07-23):** the `sidecar=` loader stripped metadata
     keys (`_README`, `units`, `up_axis`, `north_angle_deg`) before treating the rest as group specs; the
     inline `material_map=` argument did **not**. Pasting the sidecar file wholesale — which W2.3's own
     wording invited — died with `KeyError: unknown surface "Pinned material map for office_room.obj…"`,
     an error naming the *comment text* as a material. **Fixed** by lifting the split into
     `split_map_metadata` and applying it to both arguments, since they describe the same artifact and
     differ only in how it arrives; the import scalars are absorbed only where the caller left them unset,
     so an explicit argument still wins. Six regression tests in
     `tests/test_inline_material_map_metadata.py`, written before the fix and failing for the right
     reason first. Same seam class as the rest of this list — two paths, one artifact, no reconciliation.
   - **DEF-DATUM (server bug — FIXED, was silently captured as expected):** W2.3's captured value read
     `grid_points = 84 at z=0.6 (floor −0.2 + 0.8)` — the plan had **recorded the bug and rationalised
     it in a parenthetical**. `derive_sensors` anchored to the floor slab's underside while
     `workplane_grid`/`observer_points` used its top face, so the two paths disagreed by the 0.2 m slab
     thickness on the same OBJ and EN 12464-1 numbers came off a plane 0.2 m too low. Now 0.8 m / eyes
     1.2–1.6 m, pinned by **X5**. **Lesson: a captured value is only an expectation if something
     independent agrees with it.**

   Seeds found while authoring v2 (2026-06-29):
   - **D-1 (test-plan, fixed):** v1 W0.1 asserted "all checks `passed:true`" — but `validate` ships one
     by-design `passed:false` (`channel_vs_spd_alpha_opic`, informative). v1 would FAIL a healthy server.
     Fixed: W0.1 now asserts `ok:true` + documents the non-gating check.
   - **D-2 (RETRACTED — was a tester error, not a server bug):** an earlier draft claimed the `compliance`
     tool accepted only 4 standards and that `ul_24480` was "not implemented". **Verified false** on
     2026-06-29: `compliance.THRESHOLD_STANDARDS` has all **6**, the tool's `standard` is a free string →
     `check_compliance`, and `ul_24480` returns a graceful `{result:"unsupported", flag:"out of scope"}`
     (Circadian Stimulus is out of scope), while `en_12464_1` routes to the electric task path. The
     INPUT-DATA-CHECKLIST 6-standard list is **correct** (a clarifying note was added there). Lesson:
     test the claim, don't infer from a docstring.
   - **D-3 (interface sharp edge):** `compliance` return *shape* varies by standard (pass/fail vs
     `result_points` vs `n/a` vs `unsupported`). Not a bug, but undocumented in the kit ⇒ testers misread
     WELL/en_17037/ul_24480. Captured per-standard in W1.6.
   - **D-4 (server bug — FIXED):** `bin_average` didn't validate `channel_type`; any non-zero value fell
     through to 9-channel and was echoed back (`spd_to_channels(channel_type=7)` → 9-ch result labelled
     `channel_type:7`). **Fixed** on nested branch `fix/channel-type-validation` (`ace3886`) — raises
     `ValueError` for non-{0,1}, parametrized regression test added, full suite 1162 passed. Live re-confirm
     pending a server reconnect.
   - **A-1 (action, not a defect — close the combined-leaf gap):** ship `inputs/geometry/office_room_lit.obj`
     = `office_room.obj` + one `type:"luminaire"` group (L09 IES + 9-ch SPD). Unlocks the live captures for
     **W5.4 / E4 / S3 room-level / S5 combined** — the only "combination of daylight + electric" rows still
     PENDING. Everything else in the energy path is component-validated.
   - **A-2 (live energy capture):** on the next reconnect, run **E1** (MCP `lighting_controls` annual series),
     **E2** (`daylight_savings mode="annual"`, at least decline-to-emit, ideally a bounded `period`), **E3**
     (control_type sweep via the MCP tool), **N-E1** (annual multi-point raise) to replace the core-grounded
     and PENDING rows with live captures.
5. **Verdict** — does the server deliver a coherent start-to-finish HCL study, **including a defensible annual
   energy-savings number from daylight-responsive controls (E/S5)**? Human follow-ups?
