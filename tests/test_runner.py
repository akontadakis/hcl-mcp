from hcl_radiance.runner import run_sequence, parse_rtrace_res

def test_parse_res_takes_first_three_floats():
    text = "0.10\t0.20\t0.30\n1.0 2.0 3.0 99\n"
    assert parse_rtrace_res(text) == [[0.10, 0.20, 0.30], [1.0, 2.0, 3.0]]

def test_run_sequence_emit_only_when_unavailable():
    steps = [{"cmd": ["oconv", "-f", "a.rad"], "stdout": "scene.oct"},
             {"cmd": ["rtrace", "scene.oct"], "stdin": "p.pts", "stdout": "out.res"}]
    res = run_sequence(steps, work_dir="/tmp/x", available=False)
    assert res["ran"] is False
    assert res["commands"] == ["oconv -f a.rad > scene.oct", "rtrace scene.oct < p.pts > out.res"]
    assert "not available" in res["reason"].lower()

import subprocess
from hcl_radiance.image_commands import rgb_from_hdr_steps
from hcl_radiance.runner import _render

def test_render_quotes_shell_pipe_step_to_valid_bash():
    # The rgb-from-hdr pcomb pipe carries ';', '()' and '*' in its -e expression.
    # The rendered shell line must be syntactically valid AND keep '|' as a pipe operator.
    line = _render(rgb_from_hdr_steps("eye.hdr", out="rgb.txt")[1])
    assert " | " in line  # pipe preserved as an operator, not quoted
    r = subprocess.run(["bash", "-n", "-c", line], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr

def test_render_leaves_simple_tokens_unquoted():
    # Regression: simple commands must render identically (no spurious quoting).
    step = {"cmd": ["oconv", "-f", "a.rad"], "stdout": "scene.oct"}
    assert _render(step) == "oconv -f a.rad > scene.oct"

def test_run_sequence_per_step_timeout_is_passed_through(tmp_path, monkeypatch):
    import hcl_core.proc as proc
    from hcl_radiance.runner import run_sequence as rad_run
    seen = {}
    real_run = proc.subprocess.run
    def spy(*args, **kwargs):
        seen["timeout"] = kwargs.get("timeout")
        return real_run(*args, **kwargs)
    monkeypatch.setattr(proc.subprocess, "run", spy)
    (tmp_path / "a.txt").write_text("hi")
    res = rad_run([{"cmd": ["cp", "a.txt", "b.txt"]}], work_dir=str(tmp_path), available=True, timeout=30)
    assert res["ran"] is True and res.get("returncode") == 0
    assert seen["timeout"] == 30
    assert (tmp_path / "b.txt").read_text() == "hi"

def test_run_sequence_timeout_returns_124(tmp_path, monkeypatch):
    # A step that exceeds the per-step timeout maps to returncode 124 (the GAP-2 branch),
    # reporting ran=True, a timeout error, and the failed step. Patched to be deterministic/fast.
    import subprocess as sp
    from hcl_radiance.runner import run_sequence as rad_run
    def boom(*a, **k):
        raise sp.TimeoutExpired(cmd=a[0] if a else "x", timeout=k.get("timeout"))
    monkeypatch.setattr("hcl_core.proc.subprocess.run", boom)
    res = rad_run([{"cmd": ["sleep", "9"]}], work_dir=str(tmp_path), available=True, timeout=1)
    assert res["ran"] is True and res["returncode"] == 124
    assert "timed out" in (res.get("error") or "").lower()
    assert res.get("failed_step") == "sleep 9"


def test_run_sequence_returns_an_envelope_when_the_binary_is_missing(tmp_path):
    """A missing binary must come back as the documented envelope, not a raw traceback.

    Found by audit 2026-08-06. subprocess.run raises FileNotFoundError when the executable does
    not exist, and NOTHING in the runner chain (hcl_core.proc -> hcl_radiance.runner ->
    hcl_mcp.server) caught OSError, so it escaped as an unhandled traceback to the MCP client
    while the docstring promised {ran, commands, returncode|error|failed_step}. The sibling
    TimeoutExpired handler already returns a 124 envelope; this is the same contract for the
    can't-even-start case. 127 mirrors the shell's convention for command-not-found.

    Reachable in practice: `available` gates on oconv+rtrace only, so a partial Radiance install
    passes the gate and then dies here on rpict/pcomb/gendaymtx.
    """
    out = run_sequence([{"cmd": ["definitely_not_a_binary_xyz", "-x"]}],
                       work_dir=str(tmp_path), available=True)
    assert out["ran"] is True
    assert out["returncode"] == 127
    assert "definitely_not_a_binary_xyz" in out["error"]
    assert "definitely_not_a_binary_xyz" in out["failed_step"]


def test_run_sequence_still_succeeds_on_a_real_binary(tmp_path):
    """The OSError guard must not swallow a working command."""
    out = run_sequence([{"cmd": ["echo", "hello"], "stdout": "o.txt"}],
                       work_dir=str(tmp_path), available=True)
    assert out["ran"] is True
    assert out.get("returncode", 0) == 0
    assert (tmp_path / "o.txt").read_text().strip() == "hello"
