"""A1 candela-scale integrity of the Radiance build (docs: the source_corr defect).

A Radiance build whose `source.cal` resolves `flatcorr` to a compiled `source_corr` that
drops the `ies2rad` brightdata `A1` multiplier makes every IES luminaire under-emit by its
own candela scale, silently. These tests cover the detection and the RAYPATH shim that
corrects it without writing to the system install.
"""
import os

import pytest

from hcl_radiance.source_cal import inspect_source_cal

# A stock source.cal: `corr` carries the explicit A1 branch.
_STOCK = """\
{ Radiance source.cal }
corr(v) = noneg(if(AC-.5, A1*v, v));
flatcorr(v) = corr(v) / Rdot;
"""

# The defective form: both delegate to the built-in source_corr, which ignores A1.
_DEFECTIVE = """\
{ Radiance source.cal }
corr(v) = source_corr(v, 1);
flatcorr(v) = source_corr(v, Rdot);
"""


# A stand-in for an installation's source.cal. It carries src_theta (write_shim's
# completeness guard) plus the DEFECTIVE delegation, so the shim tests below start from the
# state the shim exists to correct. Using this instead of the machine's real file makes those
# tests deterministic AND runnable with no Radiance installed — the live probe tests further
# down still exercise the actual build.
_INSTALL = """\
{ Radiance source.cal }
src_theta = Acos(-Dz);
src_phi = atan2(-Dy, -Dx);
corr(v) = source_corr(v, 1);
flatcorr(v) = source_corr(v, Rdot);
"""


@pytest.fixture
def stub_install(tmp_path, monkeypatch):
    """Put a stand-in Radiance lib on RAYPATH and return its source.cal path.

    system_source_cal() consults RAYPATH first, so this is what write_shim copies as its
    base — no Radiance install required, and the base is identical on every machine.
    """
    lib = tmp_path / "stub_radiance_lib"
    lib.mkdir()
    cal = lib / "source.cal"
    cal.write_text(_INSTALL)
    monkeypatch.setenv("RAYPATH", str(lib))
    monkeypatch.delenv("HCL_RADIANCE_BIN", raising=False)
    return cal


def _write(tmp_path, text):
    p = tmp_path / "source.cal"
    p.write_text(text)
    return str(p)


def test_stock_source_cal_reports_a1_honored(tmp_path):
    assert inspect_source_cal(_write(tmp_path, _STOCK))["a1_honored"] is True


def test_source_corr_delegation_reports_a1_dropped(tmp_path):
    assert inspect_source_cal(_write(tmp_path, _DEFECTIVE))["a1_honored"] is False


def test_missing_file_is_unknown_not_a_pass(tmp_path):
    """A file that cannot be read must never be reported as honoring A1."""
    result = inspect_source_cal(str(tmp_path / "absent.cal"))
    assert result["a1_honored"] is None
    assert result["reason"]


def test_later_definition_wins(tmp_path):
    """Radiance takes the LAST definition of a function, which is how the patch works."""
    text = _DEFECTIVE + "\ncorr(v) = noneg(if(AC-.5, A1*v, v));\nflatcorr(v) = corr(v) / Rdot;\n"
    assert inspect_source_cal(_write(tmp_path, text))["a1_honored"] is True


def test_commented_a1_branch_does_not_count(tmp_path):
    """An A1 branch inside a Radiance { } comment is not a definition."""
    text = "{ corr(v) = noneg(if(AC-.5, A1*v, v)); }\ncorr(v) = source_corr(v, 1);\n"
    assert inspect_source_cal(_write(tmp_path, text))["a1_honored"] is False


# ---- live probe (needs Radiance) ----

_HAVE_RAD = bool(os.environ.get("HCL_RADIANCE_BIN")) or any(
    os.path.exists(os.path.join(d, "rtrace"))
    for d in os.environ.get("PATH", "").split(os.pathsep) if d)


@pytest.mark.skipif(not _HAVE_RAD, reason="Radiance not installed")
def test_live_probe_detects_a1_on_this_build(tmp_path):
    """Scaling A1 must scale the measured irradiance proportionally.

    This is the check text inspection cannot make: a build whose source.cal *reads*
    correct can still resolve to a compiled source_corr that ignores A1.
    """
    from hcl_radiance.source_cal import probe_a1_honored

    result = probe_a1_honored(str(tmp_path))
    assert result["ran"] is True
    # On a build that honors A1, a 10x A1 gives 10x the irradiance.
    assert result["ratio"] == pytest.approx(10.0, rel=0.02)
    assert result["a1_honored"] is True


# ---- the RAYPATH shim (writes only inside its own directory) ----

def test_shim_writes_a_source_cal_that_honors_a1(tmp_path, stub_install):
    """The shim must flip a base that DROPS A1 (see _INSTALL) into one that applies it."""
    from hcl_radiance.source_cal import inspect_source_cal, write_shim

    assert inspect_source_cal(str(stub_install))["a1_honored"] is False  # the base is defective

    shim_dir = write_shim(str(tmp_path / "shim"))

    written = os.path.join(shim_dir, "source.cal")
    assert os.path.exists(written)
    assert inspect_source_cal(written)["a1_honored"] is True


def test_shim_never_writes_outside_its_own_directory(tmp_path, stub_install):
    """The whole point of the shim: the Radiance installation is not modified.

    stub_install is the file write_shim actually reads as its base, so this asserts the
    installation is left untouched by the very call that copies from it.
    """
    from hcl_radiance.source_cal import write_shim

    before = stub_install.read_text()
    siblings_before = sorted(os.listdir(str(stub_install.parent)))

    write_shim(str(tmp_path / "shim"))

    assert stub_install.read_text() == before
    assert sorted(os.listdir(str(stub_install.parent))) == siblings_before


@pytest.mark.skipif(not _HAVE_RAD, reason="Radiance not installed")
def test_shim_restores_a1_on_a_defective_build(tmp_path):
    """End-to-end: a defective source.cal shadowed by the shim measures as honoring A1.

    The defective file is the REAL system source.cal with only its corr/flatcorr lines
    swapped for the source_corr delegation. A stub defining corr alone would also shadow
    src_theta and the rest, which no real build does — the failure would then be a broken
    environment rather than the defect under test.
    """
    from hcl_radiance.source_cal import _system_lib_dir, probe_a1_honored, write_shim

    system = os.path.join(_system_lib_dir(), "source.cal")
    if not os.path.exists(system):
        pytest.skip("system source.cal not locatable")

    broken = tmp_path / "broken"
    broken.mkdir()
    real = open(system).read()
    # Append the delegation so it wins as the last definition, reproducing the defect.
    (broken / "source.cal").write_text(
        real + "\ncorr(v) = source_corr(v, 1);\nflatcorr(v) = source_corr(v, Rdot);\n")

    assert probe_a1_honored(str(tmp_path / "w_broken"),
                            raypath=str(broken))["a1_honored"] is False

    shim_dir = write_shim(str(tmp_path / "shim"))
    assert probe_a1_honored(str(tmp_path / "w_fixed"),
                            raypath=shim_dir)["a1_honored"] is True


# ---- reporting surface ----

def test_radiance_status_reports_a1_integrity():
    """radiance_status is where a user looks before trusting an electric result."""
    from hcl_radiance.discover import radiance_status

    status = radiance_status()
    assert "source_cal" in status
    assert "a1_honored" in status["source_cal"]


# ---- opt-in automatic shim ----

def test_shim_is_off_by_default(monkeypatch, tmp_path):
    """hcl-mcp must not alter the engine environment unless asked."""
    from hcl_radiance.source_cal import shim_raypath

    monkeypatch.delenv("HCL_RADIANCE_SHIM", raising=False)
    assert shim_raypath(str(tmp_path)) is None


def test_shim_env_var_enables_it(monkeypatch, tmp_path, stub_install):
    from hcl_radiance.source_cal import inspect_source_cal, shim_raypath

    monkeypatch.setenv("HCL_RADIANCE_SHIM", "1")
    path = shim_raypath(str(tmp_path))

    assert path is not None
    assert inspect_source_cal(os.path.join(path, "source.cal"))["a1_honored"] is True


def test_runner_prepends_the_shim_to_raypath(monkeypatch, tmp_path, stub_install):
    """With the shim enabled, the emitted run environment must resolve source.cal to it."""
    from hcl_radiance import runner

    monkeypatch.setenv("HCL_RADIANCE_SHIM", "1")
    env = runner.run_env_for(str(tmp_path))

    first = env["RAYPATH"].split(os.pathsep)[0]
    assert os.path.exists(os.path.join(first, "source.cal"))


def test_runner_leaves_raypath_alone_when_shim_is_off(monkeypatch, tmp_path):
    from hcl_radiance import runner

    monkeypatch.delenv("HCL_RADIANCE_SHIM", raising=False)
    monkeypatch.setenv("RAYPATH", "/some/lib")

    assert runner.run_env_for(str(tmp_path))["RAYPATH"] == "/some/lib"


def test_run_sequence_applies_the_shim_to_executed_commands(monkeypatch, tmp_path, stub_install):
    """The shim must reach the actual subprocess env, not just be computable."""
    import hcl_core.proc as proc
    from hcl_radiance import runner

    monkeypatch.setenv("HCL_RADIANCE_SHIM", "1")
    seen = {}

    def _fake(steps, work_dir, available, **kw):
        seen.update(kw)
        return {"ran": True, "commands": [], "outputs": []}

    monkeypatch.setattr(runner, "_run_sequence", _fake)
    runner.run_sequence([{"cmd": ["oconv", "x.rad"]}], str(tmp_path), True)

    raypath = (seen.get("env_extra") or {}).get("RAYPATH", "")
    assert os.path.exists(os.path.join(raypath.split(os.pathsep)[0], "source.cal"))


def test_electric_result_records_the_engine_a1_state(tmp_path):
    """The advisory can only fire if the run records what the engine did.

    Stamped on the result rather than resolved at advisory time so a stored artifact stays
    interpretable: which engine produced it is a fact about the run, not about the reader.
    """
    from hcl_radiance.grid import engine_provenance

    prov = engine_provenance(str(tmp_path))
    assert "source_cal" in prov
    assert "a1_honored" in prov["source_cal"]


def test_engine_provenance_uses_the_runs_work_dir(monkeypatch, tmp_path, stub_install):
    """Provenance must describe the source.cal the RUN used, not one in the process cwd.

    engine_provenance() previously fell back to ".", so with the shim on it wrote .hcl_shim
    into whatever directory the server happened to be started from and reported that file
    rather than the one the run resolved.
    """
    from hcl_radiance.grid import engine_provenance

    monkeypatch.setenv("HCL_RADIANCE_SHIM", "1")
    monkeypatch.chdir(tmp_path)
    work = tmp_path / "run_work"
    work.mkdir()

    prov = engine_provenance(str(work))["source_cal"]

    assert prov["shim_active"] is True
    assert os.path.realpath(prov["path"]).startswith(os.path.realpath(str(work)))
    assert not (tmp_path / ".hcl_shim").exists()  # cwd must stay clean


def test_image_electric_result_records_engine_provenance(tmp_path, monkeypatch):
    """glare_ugr / run_image render IES luminaires too, so they need the same stamp.

    This is the path where the defect first showed as UGR 0: the fixtures were far too dim
    for evalglare to register them as glare sources at all.
    """
    from hcl_radiance import image

    monkeypatch.setattr(image, "_available", lambda: True)
    monkeypatch.setattr(image, "_run_with_colorize",
                        lambda *a, **kw: {"ran": True, "commands": [], "outputs": []})

    out = image.run_image(
        [["s.rad"]], 0, work_dir=str(tmp_path),
        electric_lights=[{"ies": "x.ies", "placement": {"positions": [[0, 0, 3]]}}])

    assert out["ran"] is True
    assert out["engine"]["source_cal"]["a1_honored"] in (True, False, None)


def test_shim_refuses_to_write_without_a_base(tmp_path):
    """An overrides-only source.cal shadows the real one and breaks EVERY scene.

    RAYPATH resolution takes the first source.cal, not the union, so a stub that defines
    only corr/flatcorr removes src_theta and the rest: rtrace then dies with
    "src_theta: undefined variable". That is strictly worse than the defect being fixed —
    wrong-but-plausible numbers become no numbers — so refusing is the only safe outcome.
    """
    from hcl_radiance.source_cal import write_shim

    with pytest.raises(RuntimeError, match="source.cal"):
        write_shim(str(tmp_path / "shim"), base=str(tmp_path / "does_not_exist.cal"))

    assert not os.path.exists(os.path.join(str(tmp_path / "shim"), "source.cal"))


def test_shim_refuses_a_base_missing_core_definitions(tmp_path):
    """A truncated base is as dangerous as a missing one, and reads as success."""
    from hcl_radiance.source_cal import write_shim

    truncated = tmp_path / "truncated.cal"
    truncated.write_text("corr(v) = source_corr(v, 1);\n")  # no src_theta

    with pytest.raises(RuntimeError, match="src_theta"):
        write_shim(str(tmp_path / "shim2"), base=str(truncated))


def test_multiline_definition_is_read_in_full(tmp_path):
    """A definition wrapped across lines must not be misread as dropping A1.

    Failing toward False here would fire a loud "re-run everything" error on a healthy
    install, which is the one direction this module must never fail in.
    """
    text = ("corr(v) = noneg(if(AC-.5,\n"
            "                   A1*v,\n"
            "                   v));\n"
            "flatcorr(v) = corr(v) / Rdot;\n")
    assert inspect_source_cal(_write(tmp_path, text))["a1_honored"] is True
