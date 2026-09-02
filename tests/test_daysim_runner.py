from hcl_daysim.runner import run_sequence

def test_emit_only_when_unavailable():
    steps = [{"cmd": ["epw2wea", "in.epw", "in.wea"]},
             {"cmd": ["ds_shortterm", "daysim_header.hea"]}]
    res = run_sequence(steps, work_dir="/tmp/x", available=False)
    assert res["ran"] is False
    assert res["commands"] == ["epw2wea in.epw in.wea", "ds_shortterm daysim_header.hea"]
    assert "not available" in res["reason"].lower()

def test_emit_renders_stdin_stdout_redirection():
    steps = [{"cmd": ["epw2wea", "in.epw"], "stdout": "in.wea"}]
    res = run_sequence(steps, work_dir="/tmp/x", available=False)
    assert res["commands"] == ["epw2wea in.epw > in.wea"]

def test_emit_quotes_paths_with_spaces():
    steps = [{"cmd": ["epw2wea", "/my dir/in.epw"], "stdout": "/my dir/in.wea"}]
    res = run_sequence(steps, work_dir="/tmp/x", available=False)
    assert res["commands"] == ["epw2wea '/my dir/in.epw' > '/my dir/in.wea'"]

def test_run_executes_and_reports_outputs(tmp_path):
    # A trivial step that always works: copy a file via `cp` so no Daysim is needed.
    src = tmp_path / "a.txt"; src.write_text("hi")
    steps = [{"cmd": ["cp", "a.txt", "b.txt"]}]
    res = run_sequence(steps, work_dir=str(tmp_path), available=True)
    assert res["ran"] is True and res["returncode"] == 0
    assert (tmp_path / "b.txt").read_text() == "hi"

def test_run_sequence_per_step_timeout_is_passed_through(tmp_path, monkeypatch):
    import hcl_core.proc as proc
    from hcl_daysim.runner import run_sequence as ds_run
    seen = {}
    real_run = proc.subprocess.run
    def spy(*args, **kwargs):
        seen["timeout"] = kwargs.get("timeout")
        return real_run(*args, **kwargs)
    monkeypatch.setattr(proc.subprocess, "run", spy)
    (tmp_path / "a.txt").write_text("hi")
    res = ds_run([{"cmd": ["cp", "a.txt", "b.txt"]}], work_dir=str(tmp_path), available=True, timeout=30)
    assert res["ran"] is True and res.get("returncode") == 0
    assert seen["timeout"] == 30
    assert (tmp_path / "b.txt").read_text() == "hi"
