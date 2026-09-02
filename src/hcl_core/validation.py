"""Self-test anchors (§5.10). Phase-1 subset; expands as presets/SPD paths land."""
from hcl_core import data
from hcl_core.alpha_opic import alpha_opic_from_channels
from hcl_core.data import (ACTION_S, ACTION_M, ACTION_L, ACTION_RHOD, ACTION_MEL,
                           V_LAMBDA, D65_ELR)
from hcl_core.spectral_metrics import mel_der, alpha_opic_from_spd, EDI_NAME
from hcl_core.presets import get_preset
from hcl_core.spd import parse_spd, bin_average


def _check(name, passed, detail):
    return {"name": name, "passed": bool(passed), "ok": bool(passed), "detail": detail}


_PUBLISHED_KD65 = {"S": 0.8173, "M": 1.4558, "L": 1.6289, "rhod": 1.4497, "mel": 1.3262}  # CIE S 026 mW/lm

def _kd65(action):
    a = sum(D65_ELR[i] * action[i] for i in range(401))
    v = 683 * sum(D65_ELR[i] * V_LAMBDA[i] for i in range(401))
    return (a / v) * 1000

def _rel_pct(a, b):
    """Relative divergence of a vs b, in %, robust to b==0."""
    return 0.0 if b == 0 else round(abs(a - b) / abs(b) * 100.0, 3)


def run_validation():
    checks = []

    sums = {n: sum(getattr(data, n)) for n in
            ["W_PHOTOPIC_9", "W_MELANOPIC_9", "W_NEUROPIC_9", "W_PHOTOPIC_3", "W_MELANOPIC_3"]}
    checks.append(_check("weight_sums", all(abs(s - 1.0) < 5e-5 for s in sums.values()),
                         {n: round(s, 8) for n, s in sums.items()}))

    a = alpha_opic_from_channels([0.1] * 9, channel_type=1, alpha=5)
    checks.append(_check("alpha_opic_nonzero", a["EDI"] > 0 and a["E_alpha"] > 0,
                         {"melanopic_EDI": a["EDI"]}))

    b = alpha_opic_from_channels([0.2] * 9, channel_type=1, alpha=5)
    checks.append(_check("elr_scale_invariant", round(a["ELR"], 6) == round(b["ELR"], 6),
                         {"elr_1x": a["ELR"], "elr_2x": b["ELR"]}))

    computed = {"S": _kd65(ACTION_S), "M": _kd65(ACTION_M), "L": _kd65(ACTION_L),
                "rhod": _kd65(ACTION_RHOD), "mel": _kd65(ACTION_MEL)}
    kd65_ok = all(abs(computed[k] - _PUBLISHED_KD65[k]) / _PUBLISHED_KD65[k] < 0.005 for k in computed)
    checks.append(_check("kd65_vs_published", kd65_ok,
                         {k: round(computed[k], 4) for k in computed}))

    der = mel_der(get_preset("D65"))
    checks.append(_check("mel_der_d65", abs(der - 1.0) < 1e-6, {"mel_der_D65": der}))

    # §5.10 #4: compare the channel-reconstruction alpha-opic path against the exact-from-SPD path
    # on a preset SPD. The reconstruction constant (§9.3a) is suspect; EDI/E_alpha may diverge while
    # ELR-type ratios (constant cancels) agree closely. SURFACE divergence; do NOT hard-fail.
    _spd = get_preset("D65")
    exact = alpha_opic_from_spd(_spd)                       # {s_edi..mel_edi} (flat)
    _channels = bin_average(parse_spd(_spd), 1)             # 9-channel binning
    _chan_full = alpha_opic_from_channels(_channels, channel_type=1)  # {"s_cone":{EDI..},..}
    chan = {f"{k}_edi": _chan_full[name]["EDI"] for k, name in EDI_NAME.items()}
    div = {k: _rel_pct(chan[k], exact[k]) for k in exact if k.endswith("_edi")}
    # ELR-type sanity: the §9.3a constant cancels in a same-path EDI ratio, so mel/m should agree.
    elr_div = _rel_pct(
        (chan["mel_edi"] / chan["m_edi"]) if chan["m_edi"] else 0.0,
        (exact["mel_edi"] / exact["m_edi"]) if exact["m_edi"] else 0.0)
    agree = all(v < 1.0 for v in div.values())
    # CORE-8: the EDI divergence above is intentionally informative (never gates). Still, a runaway
    # regression must not pass silently — gate on a sane ceiling: EDI divergence < 300% (the §9.3a
    # reconstruction sits near ~100%, so 300% is comfortably loose) AND the ELR-type ratio (which
    # cancels the §9.3a constant) stays tight (< 5%).
    _DIV_CEILING_PCT = 300.0
    _ELR_CEILING_PCT = 5.0
    bounded = all(v < _DIV_CEILING_PCT for v in div.values()) and elr_div < _ELR_CEILING_PCT
    detail = {"preset": "D65", "divergence_pct": div, "elr_ratio_divergence_pct": elr_div,
              "exact": exact, "channel": chan,
              "bounded": bounded, "divergence_ceiling_pct": _DIV_CEILING_PCT,
              "elr_ceiling_pct": _ELR_CEILING_PCT,
              "flag": "agree" if agree else "divergent (channel reconstruction §9.3a)",
              "note": ("Informative only — does not gate report['ok']. EDI divergence reflects the "
                       "physically-suspect §9.3a 9-channel reconstruction constant; ELR-type ratios "
                       "should cancel the constant and agree closely. A SEPARATE "
                       "channel_vs_spd_divergence_bounded check DOES gate on the ceilings above.")}
    checks.append(_check("channel_vs_spd_alpha_opic", agree, detail))
    # CORE-8: hard gate — catches a catastrophic divergence regression (e.g. ballooning to 1000%).
    checks.append(_check("channel_vs_spd_divergence_bounded", bounded,
                         {"bounded": bounded, "divergence_pct": div,
                          "elr_ratio_divergence_pct": elr_div,
                          "ceiling_pct": _DIV_CEILING_PCT, "elr_ceiling_pct": _ELR_CEILING_PCT}))

    # §5.10 #5: binning fidelity — a fixture ramp SPD must reproduce the golden channel values
    # (same goldens proven in tests/test_spd.py; bin_average methodology unchanged).
    _ramp = parse_spd([(380, 380), (780, 780)])
    _b9 = bin_average(_ramp, 1)
    _b3 = bin_average(_ramp, 0)
    _G9 = [399.5, 439.0, 479.0, 514.0, 543.5, 572.5, 597.5, 619.0, 705.0]
    _G3 = [683.5, 543.0, 439.5]
    checks.append(_check("binning_fidelity", _b9 == _G9 and _b3 == _G3,
                         {"channels_9": _b9, "channels_3": _b3}))

    _INFORMATIVE = {"channel_vs_spd_alpha_opic"}
    ok = all(c["ok"] for c in checks if c["name"] not in _INFORMATIVE)
    return {"ok": ok, "checks": checks}
