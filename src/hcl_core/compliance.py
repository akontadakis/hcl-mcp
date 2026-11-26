"""Multi-standard circadian compliance (extra). Thresholds verified from Papers PDFs (spec 8)."""
from hcl_core.data import EML_PER_MEDI

# WELL v2 Feature L03 mel-EDI thresholds (used for scoring): {points: (electric_only, daylight_met)}
# Derived by converting the literal published EML thresholds to mel-EDI (EML / EML_PER_MEDI ~ /1.103).
# The 3pt electric threshold tracks the CURRENT IWBI value (275 EML -> 250 mel-EDI), not the
# pilot-era 240 EML -> 218 that the _PUBLISHED_EML snapshot below still records.
_WELL_L03 = {1: (136, 109), 3: (250, 163)}

# Spec 8.1 "store all": the LITERAL published EML threshold table, kept verbatim for surfacing.
# 1pt >=150 electric / >=120 daylight; 3pt >=240 / >=180 (in EML) are the PILOT-ERA values, kept
# for provenance only. The current IWBI criterion is "EML >=275 by noon, >=4h, at eye level", and
# it is what _WELL_L03 scores against. All flagged "verify against live WELL standard".
_WELL_L03_PUBLISHED_EML = {
    "1pt": {"electric": 150, "daylight": 120},
    "3pt_pilot": {"electric": 240, "daylight": 180},
    "iwbi_current_noon_eml": 275,
    "iwbi_current_criterion": "EML >=275, >=4h beginning no later than 12:00, at eye level "
                              "(vertical), at >=75% of workstations",
}
_WELL_VERIFY_FLAG = ("verify against live WELL standard — IWBI has revised L03 thresholds across "
                     "WELL versions; treat these stored values as a snapshot, not authoritative.")
# Brown 2022 consensus / ISO-CIE 8995-1:2025: (operator, lx) by period.
# Brown specifies THREE tiers: daytime >=250, evening (from 3 h before bedtime) <=10, and the
# sleep environment <=1. "night" is an alias for the sleep-environment tier, NOT a looser fourth
# one — it previously read <=10, which is 10x the consensus night-time figure under a Brown
# citation, so a caller who said "night" was scored against the evening limit by accident.
_CONSENSUS = {"daytime": (">=", 250), "evening": ("<=", 10), "sleep": ("<=", 1), "night": ("<=", 1)}

# EN 12464-1:2021 Clause 7 (Schedule of specific lighting requirements). Each row: maintained
# illuminance Ēm (lx), unified glare rating limit UGRL, min uniformity Uo, min colour rendering Ra.
# [external — verify against EN 12464-1:2021 text].
EN_12464_1_TASKS = {
    "office_writing_reading":   {"em": 500, "ugrl": 19, "uo": 0.60, "ra": 80},
    "office_technical_drawing": {"em": 750, "ugrl": 16, "uo": 0.70, "ra": 80},
    "office_conference":        {"em": 500, "ugrl": 19, "uo": 0.60, "ra": 80},
    "office_filing_copying":    {"em": 300, "ugrl": 19, "uo": 0.40, "ra": 80},
    "office_reception":         {"em": 300, "ugrl": 22, "uo": 0.60, "ra": 80},
    "classroom":                {"em": 300, "ugrl": 19, "uo": 0.60, "ra": 80},
    "classroom_evening_adult":  {"em": 500, "ugrl": 19, "uo": 0.60, "ra": 80},
    "corridor_circulation":     {"em": 100, "ugrl": 28, "uo": 0.40, "ra": 40},
}

_EN_12464_1_CITATION = "EN 12464-1:2021 Clause 7 (Schedule of specific lighting requirements)"
_EN_12464_1_FLAG = ("mandatory — tabulated thresholds [verify against EN 12464-1:2021 text]; "
                    "task-area-only checks pass non-compliant designs, so supply surround/background "
                    "and wall/ceiling/cylindrical values where available.")

# EN 12464-1 surround/background/wall/ceiling/cylindrical relationships (Table 3 / Clause 7).
EN_12464_1_RELATIONSHIPS = {
    "surround": "Ēm,surround graded by task Ēm (>=750->500, >=500->300, >=300->200, <=200->equal), Uo>=0.40",
    "background": "Ēm,background >= (1/3)*Ēm,surround, Uo>=0.10",
    "wall": "Ēm,wall >= 50 lx, Uo>=0.10",
    "ceiling": "Ēm,ceiling >= 30 lx, Uo>=0.10",
    "cylindrical": "Ēm,z >= 50 lx (>=150 lx where good visual communication is needed), Uo>=0.10",
}

# Standards for which describe_thresholds() returns a stored table (used by the
# hcl://compliance/{standard} resource + its completion list).
THRESHOLD_STANDARDS = (
    "well_v2_l03", "brown_2022", "iso_cie_8995_1_2025", "en_17037", "en_12464_1", "ul_24480",
)


def describe_thresholds(standard: str) -> dict:
    """Return the STORED threshold table for a standard — no scoring, no fictitious
    input. Read-only companion to check_compliance (spec 8.1 'store all'). Used by the
    hcl://compliance/{standard} resource."""
    if standard == "well_v2_l03":
        return {
            "standard": "WELL v2 L03 Circadian Lighting Design",
            "kind": "circadian",
            "thresholds_mel_edi": {
                "electric_only": {"1pt": _WELL_L03[1][0], "3pt": _WELL_L03[3][0]},
                "daylight_met": {"1pt": _WELL_L03[1][1], "3pt": _WELL_L03[3][1]},
            },
            "published_eml_thresholds": _WELL_L03_PUBLISHED_EML,
            "measurement": "vertical at eye, >=4h beginning no later than 12:00, at >=75% of workstations",
            "flag": "mandatory (WELL credit)",
            "citation": "Five-Step Table 3 / IWBI WELL v2 (verify against live standard)",
            "verify_flag": _WELL_VERIFY_FLAG,
        }
    if standard in ("brown_2022", "iso_cie_8995_1_2025"):
        thresholds = {period: {"operator": op, "mel_edi_lx": thr}
                      for period, (op, thr) in _CONSENSUS.items()}
        if standard == "brown_2022":
            cite = "Brown et al. 2022, PLoS Biol 20:e3001571"
            flag = "consensus recommendation"
        else:
            cite = "ISO/CIE 8995-1:2025 subclause 5.4"
            flag = "threshold taken from the Brown 2022 consensus; NOT independently verified against the ISO text — subclause 5.4 is a design-criteria clause, not an informative annex"
        return {"standard": standard, "kind": "circadian", "thresholds": thresholds,
                "measurement": "vertical at eye", "flag": flag, "citation": cite}
    if standard == "en_12464_1":
        return {"standard": "EN 12464-1:2021 (indoor work places)",
                "kind": "photopic_visual",
                "tasks": EN_12464_1_TASKS,
                "relationships": EN_12464_1_RELATIONSHIPS,
                "flag": _EN_12464_1_FLAG,
                "citation": _EN_12464_1_CITATION}
    if standard == "en_17037":
        return {"standard": "EN 17037:2018", "kind": "daylight_provision",
                "thresholds": {
                    "target_lx": {"minimum": 300, "medium": 500, "high": 750},
                    "target_fraction_of_plane": 0.5,
                    "minimum_lx": {"minimum": 100, "medium": 300, "high": 500},
                    "minimum_fraction_of_plane": 0.95,
                },
                "flag": "non-circadian (daylight provision only)",
                "citation": "EN 17037:2018 (external — verify against text)"}
    if standard == "ul_24480":
        return {"standard": "UL 24480", "kind": "unsupported",
                "flag": "out of scope",
                "citation": "UL 24480 (CS / Rea-LRC CLA; out of scope — see spec 8.3)",
                "notes": "UL 24480 uses Circadian Stimulus (Rea/LRC CLA), which this toolkit does not compute."}
    raise ValueError(f"unknown standard {standard!r}; choose from {list(THRESHOLD_STANDARDS)}")


def en_12464_surround_minimum(em_task):
    """Immediate-surround Ēm minimum from the task Ēm (EN 12464-1 Table 3 grading).

    >=750 -> 500, >=500 -> 300, >=300 -> 200, and at or below 200 lx the surround equals the task.
    """
    if em_task >= 750:
        return 500
    if em_task >= 500:
        return 300
    if em_task >= 300:
        return 200
    if em_task >= 200:
        return 200
    return em_task  # < 200 lx: surround equals task

def _to_medi(mel_edi, eml):
    if mel_edi is not None:
        return float(mel_edi)
    if eml is not None:
        return float(eml) / EML_PER_MEDI
    raise ValueError("provide mel_edi or eml")

def _consensus(medi, period, standard):
    if period not in _CONSENSUS:
        raise ValueError(f"period must be one of {list(_CONSENSUS)}")
    op, thr = _CONSENSUS[period]
    ok = medi >= thr if op == ">=" else medi <= thr
    if standard == "brown_2022":
        cite, flag = "Brown et al. 2022, PLoS Biol 20:e3001571", "consensus recommendation"
        note = "Consensus recommendation; mel-EDI at the plane of the eye, applied daily at the same clock time."
    else:
        cite, flag = "ISO/CIE 8995-1:2025 subclause 5.4", "threshold taken from the Brown 2022 consensus; NOT independently verified against the ISO text — subclause 5.4 is a design-criteria clause, not an informative annex"
        note = ("Subclause 5.4 (ipRGC-influenced responses to light), a design-criteria clause rather than an annex; mel-EDI quantified per CIE S 026. The mandatory task "
                "tables remain photopic; meeting Clause 7 does not automatically fulfil this.")
    return {"standard": standard, "result": "pass" if ok else "fail", "mel_edi_used": round(medi, 2),
            "period": period, "threshold": f"{op} {thr} lx mel-EDI", "measurement": "vertical at eye",
            "flag": flag, "citation": cite, "notes": note}

def check_compliance(*, mel_edi=None, eml=None, standard, period="daytime", daylight_met=False,
                     **kw):
    """Check a mel-EDI (or EML) value against a standard, recording WHICH quantity was scored.

    `quantity`/`quantity_note` are stamped on every result so an artifact can never be ambiguous
    after the fact about whether it was fed CIE S 026 mel-EDI or something else. This matters
    because `melanopic_lux` — a melanopic-weighted illuminance returned alongside mel-EDI by the
    metrics core — is a DIFFERENT quantity, larger by D65's melanopic/photopic ratio (~1.10), and
    nothing in a numeric argument distinguishes them. See hcl_core.metrics._with_mel_edi.
    """
    out = _check_compliance_impl(mel_edi=mel_edi, eml=eml, standard=standard, period=period,
                                 daylight_met=daylight_met, **kw)
    if isinstance(out, dict) and out.get("kind") != "daylight_provision":
        out.setdefault("quantity", "mel_edi" if mel_edi is not None else
                       ("eml->mel_edi" if eml is not None else "non_melanopic"))
        out.setdefault("quantity_note", (
            "Not a melanopic check: scored on the photometric values supplied "
            "(illuminance, glare, uniformity, colour rendering). No mel-EDI was used."
            if out["quantity"] == "non_melanopic" else
            "Scored as CIE S 026 mel-EDI. `melanopic_lux` is NOT this quantity "
            "(larger by D65's melanopic/photopic ratio); pass `mel_edi`."))
    return out


def _check_compliance_impl(*, mel_edi=None, eml=None, standard, period="daytime", daylight_met=False,
                     task=None, em=None, ugr=None, uo=None, ra=None,
                     em_surround=None, uo_surround=None, em_background=None, uo_background=None,
                     em_wall=None, uo_wall=None, em_ceiling=None, uo_ceiling=None,
                     em_cylindrical=None, uo_cylindrical=None):
    """Check a mel-EDI (or EML) value against a standard.

    EML is the LARGER number: EML = mel-EDI * 1.103. So an `eml` input is DIVIDED by
    1.103 to score it, and a mel-EDI turned back into EML is MULTIPLIED by 1.103.

    standard="en_12464_1" uses the EN 12464-1:2021 task-lighting params (task/em/ugr/uo/ra and
    the surround/background/wall/ceiling/cylindrical inputs) instead of mel-EDI.
    """
    if standard == "en_12464_1":
        return _check_en_12464_1(task, em, ugr, uo, ra, em_surround, uo_surround,
                                 em_background, uo_background, em_wall, uo_wall,
                                 em_ceiling, uo_ceiling, em_cylindrical, uo_cylindrical)
    medi = _to_medi(mel_edi, eml)
    if standard == "well_v2_l03":
        idx = 1 if daylight_met else 0
        points = 0
        for p in (1, 3):
            if medi >= _WELL_L03[p][idx]:
                points = p
        return {"standard": "WELL v2 L03 Circadian Lighting Design", "result_points": points,
                "mel_edi_used": round(medi, 2),
                "thresholds_mel_edi": {"1pt": _WELL_L03[1][idx], "3pt": _WELL_L03[3][idx]},
                # Spec 8.1 "store all": the literal published EML table + current IWBI noon value.
                "published_eml_thresholds": _WELL_L03_PUBLISHED_EML,
                "condition": "daylight criteria met" if daylight_met else "electric light only",
                "measurement": "vertical at eye, >=4h beginning no later than 12:00, at >=75% of workstations", "flag": "mandatory (WELL credit)",
                "citation": "Five-Step Table 3 / IWBI WELL v2 (verify against live standard)",
                "verify_flag": _WELL_VERIFY_FLAG,
                "notes": ("Scoring is on mel-EDI. EML is the larger number: EML = mel-EDI * 1.103, "
                          "so an EML input is DIVIDED by 1.103 to score it. The stored mel-EDI "
                          "thresholds are that conversion ROUNDED, not exact: the 3pt electric "
                          "threshold is 250, while 275 EML / 1.103 = 249.32, so a 249.5 mel-EDI "
                          "room scores 1 point where the exact arithmetic would give 3. The "
                          "published EML thresholds are stored verbatim under 'published_eml_thresholds' "
                          "and surfaced via hcl://compliance/well_v2_l03. WELL has revised thresholds "
                          "across versions; verify current values.")}
    if standard in ("brown_2022", "iso_cie_8995_1_2025"):
        return _consensus(medi, period, standard)
    if standard == "en_17037":
        return {"standard": "EN 17037:2018", "result": "n/a", "flag": "non-circadian",
                "citation": "EN 17037:2018 (external)",
                "notes": ("EN 17037 is daylight-provision (illuminance) only; no melanopic requirement. "
                          "Targets 300/500/750 lx (min/med/high) on >=50% of plane; minima 100/300/500 lx "
                          "on >=95% [external: verify against EN 17037:2018].")}
    if standard == "ul_24480":
        return {"standard": "UL 24480", "result": "unsupported", "flag": "out of scope",
                "citation": "UL 24480 (CS / Rea-LRC CLA; out of scope — see spec 8.3)",
                "notes": "UL 24480 uses Circadian Stimulus (Rea/LRC CLA), which this toolkit does not compute."}
    raise ValueError(f"unknown standard {standard!r}")


def _check_en_12464_1(task, em, ugr, uo, ra, em_surround, uo_surround, em_background, uo_background,
                      em_wall, uo_wall, em_ceiling, uo_ceiling, em_cylindrical, uo_cylindrical):
    """EN 12464-1:2021 verdict: per-parameter task check + surround/background + wall/ceiling/
    cylindrical relationships. Each relationship is evaluated only when its inputs are supplied."""
    if task not in EN_12464_1_TASKS:
        raise ValueError(f"unknown EN 12464-1 task {task!r}; choose from {sorted(EN_12464_1_TASKS)}")
    req = EN_12464_1_TASKS[task]

    parameters = {}
    if em is not None:
        parameters["em"] = {"value": em, "required": req["em"], "met": em >= req["em"],
                            "measurement": "maintained illuminance on the task area (lx)"}
    if ugr is not None:
        parameters["ugr"] = {"value": ugr, "limit": req["ugrl"], "met": ugr <= req["ugrl"],
                             "measurement": "unified glare rating (<= UGRL)"}
    if uo is not None:
        parameters["uo"] = {"value": uo, "required": req["uo"], "met": uo >= req["uo"],
                            "measurement": "illuminance uniformity on the task area"}
    if ra is not None:
        parameters["ra"] = {"value": ra, "required": req["ra"], "met": ra >= req["ra"],
                            "measurement": "colour rendering index (>= Ra)"}

    relationships = {}
    if em_surround is not None:
        req_surround = en_12464_surround_minimum(req["em"])
        em_ok = em_surround >= req_surround
        uo_ok = uo_surround is None or uo_surround >= 0.40
        relationships["surround"] = {
            "value": em_surround, "required_em": req_surround, "met": em_ok,
            "uo_value": uo_surround, "uo_required": 0.40, "uo_met": uo_ok,
            "citation": "EN 12464-1:2021 Clause 5.3 (immediate surround) [verify]",
            "flag": "mandatory"}
        if em_background is not None:
            req_bg = em_surround / 3.0
            bg_ok = em_background >= req_bg
            bg_uo_ok = uo_background is None or uo_background >= 0.10
            relationships["background"] = {
                "value": em_background, "required_em": req_bg, "met": bg_ok,
                "uo_value": uo_background, "uo_required": 0.10, "uo_met": bg_uo_ok,
                "citation": "EN 12464-1:2021 Clause 5.3 (background) [verify]",
                "flag": "mandatory"}
    elif em_background is not None:
        # Background supplied without surround: its required Ēm (= em_surround/3) is undefined,
        # so the check cannot be evaluated. Surface it as an explicit "incomplete" entry rather
        # than dropping it silently — an unevaluated background must not green-light a pass.
        relationships["background"] = {
            "value": em_background, "required_em": None, "met": "incomplete",
            "uo_value": uo_background, "uo_required": 0.10, "uo_met": None,
            "note": ("background check needs em_surround (required Ēm = em_surround/3); "
                     "supply em_surround to evaluate it"),
            "citation": "EN 12464-1:2021 Clause 5.3 (background) [verify]",
            "flag": "mandatory"}

    surfaces = {}
    if em_wall is not None:
        surfaces["wall"] = {"value": em_wall, "required_em": 50, "met": em_wall >= 50,
                            "uo_value": uo_wall, "uo_required": 0.10,
                            "uo_met": uo_wall is None or uo_wall >= 0.10,
                            "citation": "EN 12464-1:2021 (wall Ēm >= 50 lx) [verify]",
                            "flag": "mandatory"}
    if em_ceiling is not None:
        surfaces["ceiling"] = {"value": em_ceiling, "required_em": 30, "met": em_ceiling >= 30,
                               "uo_value": uo_ceiling, "uo_required": 0.10,
                               "uo_met": uo_ceiling is None or uo_ceiling >= 0.10,
                               "citation": "EN 12464-1:2021 (ceiling Ēm >= 30 lx) [verify]",
                               "flag": "mandatory"}
    if em_cylindrical is not None:
        surfaces["cylindrical"] = {"value": em_cylindrical, "required_em": 50, "met": em_cylindrical >= 50,
                                   "uo_value": uo_cylindrical, "uo_required": 0.10,
                                   "uo_met": uo_cylindrical is None or uo_cylindrical >= 0.10,
                                   "note": ("mean cylindrical (vertical) illuminance Ēm,z >= 50 lx; "
                                            ">= 150 lx where good visual communication is needed"),
                                   "citation": "EN 12464-1:2021 (cylindrical Ēm,z) [verify]",
                                   "flag": "mandatory"}

    def _all_met(d, sub_keys=("met",)):
        # A sub-key counts as "met" only when it is exactly True; None means "not supplied /
        # not applicable" and is ignored. Anything else (False, "incomplete", ...) blocks a pass,
        # so an unevaluated relationship cannot green-light the design.
        ok = True
        for v in d.values():
            for k in sub_keys:
                if k in v and v[k] is not True and v[k] is not None:
                    ok = False
        return ok

    overall = _all_met(parameters) and _all_met(relationships, ("met", "uo_met")) \
        and _all_met(surfaces, ("met", "uo_met"))
    if not parameters and not relationships and not surfaces:
        result = "incomplete"
    else:
        result = "pass" if overall else "fail"
    return {"standard": "EN 12464-1:2021 (indoor work places)", "task": task,
            "requirements": req, "parameters": parameters, "relationships": relationships,
            "surfaces": surfaces, "result": result,
            "mandatory": True, "citation": _EN_12464_1_CITATION, "flag": _EN_12464_1_FLAG,
            "notes": ("Task rows carry a base minimum; a higher context-modified Ēm applies for "
                      "critical/long-duration/low-contrast tasks or reduced visual capacity (carried "
                      "as a note, not auto-applied). Items the toolkit cannot measure are informative.")}
