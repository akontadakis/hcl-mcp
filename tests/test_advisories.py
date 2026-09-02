from hcl_mcp.advisories import advise, rule, _RULES
from hcl_radiance.geometry_health import build_report, check_geometry_health, finding
from hcl_radiance.geometry_obj import parse_obj


def test_clean_result_produces_no_advisories():
    assert advise("circadian_metrics", {}, {"mel_edi": 300.0}) == []


def test_non_dict_result_is_tolerated():
    assert advise("validate", {}, "not a dict") == []
    assert advise("validate", {}, None) == []


def test_mel_der_binned_fires_on_the_binned_route():
    out = advise("circadian_metrics", {}, {"mel_der_source": "binned_channels"})
    codes = [a["code"] for a in out]
    assert codes == ["MEL_DER_BINNED"]
    assert out[0]["severity"] == "warn"
    assert out[0]["field"] == "mel_der_source"
    assert "spd" in out[0]["message"]


def test_mel_der_binned_silent_on_the_exact_spd_route():
    # "spd" was the route string before ADR-0006; assert the ones the code can emit.
    assert advise("circadian_metrics", {}, {"mel_der_source": "spd_transported"}) == []
    assert advise("circadian_metrics", {},
                  {"mel_der_source": "spd_source_untransported"}) == []


def test_mel_der_binned_fires_inside_a_list_of_points():
    out = advise("circadian_metrics", {},
                 [{"mel_der_source": "spd"}, {"mel_der_source": "binned_channels"}])
    assert [a["code"] for a in out] == ["MEL_DER_BINNED"]


def test_a_raising_rule_cannot_break_advise():
    @rule
    def _boom(tool, args, result):
        raise RuntimeError("rule bug")

    try:
        assert advise("validate", {}, {"ok": True}) == []
    finally:
        _RULES.remove(_boom)


def test_albedo_not_measured_fires_when_the_value_was_substituted():
    result = {"albedo": 0.2,
              "provenance": {"albedo": {"source": "default", "method": "documented",
                                        "uncertainty": None}}}
    out = advise("atmosphere_from_epw", {}, result)
    assert [a["code"] for a in out] == ["ALBEDO_NOT_MEASURED"]
    assert out[0]["severity"] == "warn"
    assert out[0]["field"] == "albedo"


def test_albedo_not_measured_silent_on_measured_data():
    result = {"provenance": {"albedo": {"source": "epw", "method": "epw",
                                        "uncertainty": None}}}
    assert advise("atmosphere_from_epw", {}, result) == []


def test_albedo_not_measured_silent_on_an_explicit_override():
    result = {"provenance": {"albedo": {"source": "override", "method": "override",
                                        "uncertainty": None}}}
    assert advise("atmosphere_from_epw", {}, result) == []


def test_albedo_not_measured_fires_on_the_nested_atmosphere_shape():
    # spectral_sky_from_epw nests atmosphere provenance under "atmosphere" instead of at
    # the top level (hcl_core.spectral_emit.record_to_dict) — verified live against the
    # Athens EPW, whose 0.000 albedo triggers this same substitution.
    result = {"atmosphere": {"albedo": 0.2,
                             "provenance": {"albedo": {"source": "default", "method": "fixed",
                                                       "uncertainty": None}}}}
    out = advise("spectral_sky_from_epw", {}, result)
    assert [a["code"] for a in out] == ["ALBEDO_NOT_MEASURED"]
    assert out[0]["severity"] == "warn"
    assert out[0]["field"] == "albedo"


def test_dose_threshold_is_default_fires_on_250():
    out = advise("run_annual", {}, {"dosimetry": {"threshold": 250.0, "hours_above": 33.0}})
    assert [a["code"] for a in out] == ["DOSE_THRESHOLD_IS_DEFAULT"]
    assert out[0]["severity"] == "info"


def test_dose_threshold_is_default_silent_on_a_chosen_threshold():
    assert advise("run_annual", {}, {"dosimetry": {"threshold": 150.0}}) == []


def test_dose_threshold_is_default_silent_when_no_dosimetry_ran():
    assert advise("run_annual", {}, {"ran": True}) == []


def test_zone_weight_remainder_reports_the_uncontrolled_core():
    out = advise("daylight_savings", {"weights": [0.4, 0.307]}, {"savings_pct": 54.0})
    assert [a["code"] for a in out] == ["ZONE_WEIGHT_REMAINDER"]
    assert out[0]["severity"] == "warn"
    assert "29.3" in out[0]["message"]
    assert "area_weights_from_geometry" in out[0]["message"]


def test_zone_weight_remainder_silent_when_weights_sum_to_one():
    assert advise("daylight_savings", {"weights": [0.6, 0.4]}, {}) == []


def test_zone_weight_remainder_ignores_unrelated_tools():
    assert advise("run_grid", {"weights": [0.5]}, {}) == []


def test_zone_weight_remainder_tolerates_junk_weights():
    assert advise("lighting_controls", {"weights": ["x"]}, {}) == []
    assert advise("lighting_controls", {"weights": []}, {}) == []


# --- GEOMETRY_HEALTH_UNCLEAN ------------------------------------------------------
# Every fixture below is REAL output from hcl_radiance.geometry_health, never a
# hand-written dict. Hand-written ones are exactly why the two production defects
# shipped: the old positive test used `skipped: ["enclosure"]` (a list of STRINGS) and
# the old negative test used `skipped: []` (empty) — production emits neither shape.

_MINIMAL_OBJ = "v 0 0 0\nv 1 0 0\nv 1 1 0\ng slab\nf 1 2 3\n"


def _real_skipped():
    """The `skipped` list check_geometry_health actually emits: five
    {"category", "reason"} DICTS, and structurally never empty
    (hcl_radiance/geometry_health.py:684-695)."""
    return check_geometry_health(parse_obj(_MINIMAL_OBJ), {})["skipped"]


def _real_report(findings):
    return build_report(findings, checked=["geometry"], skipped=_real_skipped())


def _error_finding():
    return finding("COINCIDENT_SURFACES", "error", "geometry",
                   "2 face pairs are coplanar and overlapping",
                   fix="Delete one of each coplanar pair or offset it.")


def _warning_finding():
    return finding("NO_FLOOR_GROUP", "warning", "geometry",
                   "no group is typed type:\"floor\"",
                   fix="Type the floor group as `type:\"floor\"`.")


def test_geometry_health_unclean_silent_on_a_clean_report_with_skipped_categories():
    """The as-shipped defect: `skipped` is never empty, so a rule that triggers on it
    warns on EVERY import, spotless report included."""
    health = _real_report([])
    assert health["ok"] is True and health["counts"]["warning"] == 0
    assert health["skipped"], "fixture must keep production's non-empty skipped list"
    assert advise("import_geometry", {}, {"health": health}) == []


def test_geometry_health_unclean_fires_on_errors():
    health = _real_report([_error_finding()])
    out = advise("import_geometry", {}, {"health": health})
    assert [a["code"] for a in out] == ["GEOMETRY_HEALTH_UNCLEAN"]
    assert out[0]["severity"] == "error"
    assert "1 error" in out[0]["message"]


def test_geometry_health_unclean_fires_on_a_warning_only_report():
    health = _real_report([_warning_finding()])
    assert health["ok"] is True  # warnings alone do not clear `ok`
    out = advise("import_geometry", {}, {"health": health})
    assert [a["code"] for a in out] == ["GEOMETRY_HEALTH_UNCLEAN"]
    assert out[0]["severity"] == "warn"
    assert "1 warning" in out[0]["message"]


def test_geometry_health_unclean_names_skipped_categories_without_dict_reprs():
    """Regression: `", ".join(str(s) for s in skipped)` over the real dict entries
    emitted raw Python reprs like {'category': 'materials', ...} into caller-facing
    text. The categories stay; the reprs must never come back."""
    for health in (_real_report([_error_finding()]), _real_report([_warning_finding()])):
        msg = advise("import_geometry", {}, {"health": health})[0]["message"]
        assert "{" not in msg, msg
        for category in ("materials", "apertures", "conventions", "sensors", "luminaires"):
            assert category in msg


def test_geometry_health_unclean_covers_both_result_shapes():
    """check_geometry returns the report at the TOP LEVEL (server.py:529);
    import_geometry embeds the same report under `health` (server.py:454). Before the
    fix the dedicated health-check tool was the one tool that never warned."""
    report = check_geometry_health(parse_obj(_MINIMAL_OBJ), {})
    assert report["counts"]["warning"] > 0  # real defects, not a synthetic fixture

    top_level = advise("check_geometry", {}, report)
    assert [a["code"] for a in top_level] == ["GEOMETRY_HEALTH_UNCLEAN"]
    assert top_level[0]["severity"] == "warn"

    nested = advise("import_geometry", {}, {"health": report})
    assert [a["code"] for a in nested] == ["GEOMETRY_HEALTH_UNCLEAN"]
    assert nested[0]["field"] == "health"


def test_geometry_health_unclean_ignores_a_result_that_is_not_a_report():
    """The top-level shape is recognised structurally, so the guess must stay narrow:
    `ok` alone (no `counts`) is not a health report."""
    assert advise("run_grid", {}, {"ok": False}) == []
    assert advise("run_grid", {}, {"counts": {"error": 1}}) == []


def test_nvrd_zero_divergence_fires_on_an_exact_zero():
    result = {"divergence": {"neutral_vs_colored_sun": {"mel_edi_pct": 0, "i_eff_pct": 0}}}
    out = advise("annual_nvrd", {}, result)
    assert [a["code"] for a in out] == ["NVRD_ZERO_DIVERGENCE"]
    assert "RD_series_divergence" in out[0]["message"]


def test_nvrd_zero_divergence_silent_on_a_real_value():
    result = {"divergence": {"neutral_vs_colored_sun": {"mel_edi_pct": 0.579}}}
    assert advise("annual_nvrd", {}, result) == []


def test_nvrd_zero_divergence_ignores_reconstruct_spectrum():
    result = {"divergence": {"neutral_vs_colored_sun": {"mel_edi_pct": 0}}}
    assert advise("reconstruct_spectrum", {}, result) == []


# MEL_DER_BINNED must reach a run_grid result — and must not become an always-on alarm there.

def _grid_result(*, daylight_binned=True, electric=None, combined=None):
    """A run_grid-shaped result: per-point metrics nested under condition blocks."""
    out = {"ran": True, "daylight": {"metrics": [
        {"photopic_lux": 300.0, "mel_der": 0.72, "mel_edi": 216.0,
         "mel_der_source": "binned_channels" if daylight_binned else "spd_transported"}]}}
    for name, src in (("electric", electric), ("combined", combined)):
        if src:
            out[name] = {"metrics": [{"photopic_lux": 100.0, "mel_der": 0.5,
                                      "mel_edi": 50.0, "mel_der_source": src}]}
    return out


def test_mel_der_binned_reaches_a_nested_run_grid_result():
    """It read the top level only, and run_grid puts nothing per-point there — so it had never
    once fired on the tool that produces most channels."""
    out = advise("run_grid", {}, _grid_result(electric="binned_channels"))
    assert [a["code"] for a in out] == ["MEL_DER_BINNED"]
    assert "electric" in out[0]["message"]


def test_mel_der_binned_is_silent_on_a_daylight_only_run():
    """The exemption that keeps this from being noise.

    `daylight` is present on EVERY run, its spectrum is a smooth sky (binned costs ~0.13%), and
    there is no single source spectrum to pass instead — so a warning there is permanent,
    unactionable and ~60x overstated, and would teach people to skip the advisories block.
    """
    assert advise("run_grid", {}, _grid_result()) == []


def test_mel_der_binned_fires_on_the_combined_mixture():
    """Unavoidable there, but its error grows with the electric share to the full ~8%, and the
    message must carry the action (read the parts and add them)."""
    out = advise("run_grid", {}, _grid_result(combined="binned_channels"))
    assert [a["code"] for a in out] == ["MEL_DER_BINNED"]
    assert "additive" in out[0]["message"] or "ADD" in out[0]["message"]


def test_mel_der_binned_silent_when_the_electric_block_used_a_source_spectrum():
    assert advise("run_grid", {}, _grid_result(electric="spd_transported",
                                               combined="spd_transported")) == []


def test_mel_der_binned_message_differs_by_block():
    """A generic 'pass spd=' is wrong advice for a two-source mixture — there is no single
    source spectrum to pass. The blocks must not share one message."""
    e = advise("run_grid", {}, _grid_result(electric="binned_channels"))[0]["message"]
    c = advise("run_grid", {}, _grid_result(combined="binned_channels"))[0]["message"]
    top = advise("circadian_metrics", {}, {"mel_der_source": "binned_channels"})[0]["message"]
    assert e != c and e != top and c != top
