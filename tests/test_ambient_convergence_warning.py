"""Under-converged ambient settings must be flagged, not silently accepted.

Not a bug: `-ab 2 -ad 512` is a legitimate fast preview. But on a real annual run it moved sDA
from 77.78% to 100.00% on identical geometry — 22 points of a headline climate-based metric —
and nothing in the return said the result was sampling-limited. An agent uses whatever default
it is handed, so the honest fix is to say so in the result rather than to change the number
underneath existing callers.
"""
from hcl_radiance.commands import ambient_convergence_note, DEFAULT_RTRACE_PARAMS


def test_tool_defaults_are_flagged_as_preview_grade():
    n = ambient_convergence_note(DEFAULT_RTRACE_PARAMS)
    assert n is not None, "the shipped default must not pass unflagged"
    assert "-ad" in n and "-ab" in n


def test_converged_settings_are_not_flagged():
    assert ambient_convergence_note(
        "-ab 3 -ad 4096 -as 2048 -ar 512 -aa 0.1 -lw 1e-5") is None


def test_low_ad_is_flagged_even_with_enough_bounces():
    assert ambient_convergence_note("-ab 5 -ad 256") is not None


def test_low_ab_is_flagged_even_with_many_samples():
    assert ambient_convergence_note("-ab 1 -ad 8192") is not None


def test_note_names_the_metric_at_risk():
    n = ambient_convergence_note("-ab 2 -ad 512")
    assert "sDA" in n or "daylight autonomy" in n.lower()


def test_deliberate_direct_only_pass_is_not_flagged():
    """ASE and the internal sun pass use -ab 0 by design; ambient settings cannot affect them."""
    assert ambient_convergence_note("-ab 0 -ad 512", direct_only_ok=True) is None


# --- the tool boundary ---------------------------------------------------------------------------

def test_the_warning_survives_the_server_envelope():
    """Producing the note is not the same as returning it.

    `run_annual_daylight` set `convergence_warning` on its own result, but the server's final
    `emit_envelope` forwarded only n_points/n_timesteps/metrics, so the warning and the
    `rad_params` that caused it were dropped at the MCP boundary and no client ever saw them.
    Caught by a live `annual_daylight(quality="medium")` call whose return had no warning while
    the same params flagged fine in-process. Every other test in this file calls
    `ambient_convergence_note` directly and so passed throughout — the same blind spot that hid
    the unregistered `quality_presets`.

    Stubbed rather than run: an 8760-h Radiance solve is not a unit test.
    """
    import hcl_mcp.server as server

    captured = {}

    def _fake_run(channel_scenes, wea, points, channel_type, **kw):
        captured["rad_params"] = kw.get("rad_params")
        n_ts = 2
        return {"ran": True, "n_points": 1, "n_timesteps": n_ts,
                "lux_matrix": [[500.0] * n_ts], "sun_lux_matrix": [[0.0] * n_ts],
                "rad_params": kw.get("rad_params"),
                "convergence_warning": "PREVIEW-GRADE SENTINEL"}

    real = server._run_annual_daylight
    server._run_annual_daylight = _fake_run
    try:
        import asyncio
        out = asyncio.run(server.annual_daylight(
            channel_scenes=[{"materials": [], "geometry": "g.rad", "sky_color": [1, 1, 1]}],
            wea="x.wea", points=[[0, 0, 0.8, 0, 0, 1]], channel_type=0, quality="medium"))
    finally:
        server._run_annual_daylight = real

    assert captured["rad_params"] and "-ab 2" in captured["rad_params"]
    assert out.get("convergence_warning") == "PREVIEW-GRADE SENTINEL", (
        "the core's convergence_warning was dropped by the server envelope")
    assert out.get("rad_params") == captured["rad_params"], (
        "the rad_params that produced the warning must travel with it")


def test_whole_run_at_ab_0_is_flagged_as_the_worst_case():
    """Without that opt-out, -ab 0 is the most severe under-convergence, not the absence of one:
    no interreflection is computed at all, so DA/sDA/UDI are meaningless."""
    n = ambient_convergence_note("-ab 0 -ad 512")
    assert n is not None and "interreflect" in n.lower()


def test_missing_parameters_fall_back_to_radiance_defaults():
    """rtrace's own default is -ab 0. Parameters that name no ambient flag at all therefore run
    direct-only, exactly like an explicit `-ab 0` -- and get the same warning. (This used to
    return None, on the argument that an empty string is "not under-converged": the one
    direct-only run nobody chose was the one that went unreported. Review 2026-11-26, G13.)"""
    note = ambient_convergence_note("")
    assert note and "NO interreflected light" in note
    assert ambient_convergence_note("", direct_only_ok=True) is None


def test_malformed_input_does_not_raise():
    """Unreadable ambient values are treated as absent: no exception, and the absent-flag
    warning, since rtrace would not be running with the values the caller meant."""
    note = ambient_convergence_note("-ab notanumber -ad")
    assert note and "NO interreflected light" in note
