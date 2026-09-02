from hcl_radiance.discover import radiance_status, resolve_bin, radiance_version
from hcl_radiance import discover

def test_status_shape():
    st = radiance_status()
    assert set(["available", "bin_dir", "version", "found", "missing"]) <= set(st.keys())
    assert isinstance(st["available"], bool)
    assert isinstance(st["found"], list) and isinstance(st["missing"], list)
    assert st["version"] is None or isinstance(st["version"], str)  # spec §3.2

def test_version_none_when_rtrace_absent(monkeypatch):
    monkeypatch.setattr("hcl_radiance.discover.resolve_bin", lambda name: None)
    assert radiance_version() is None

def test_resolve_bin_uses_env(monkeypatch, tmp_path):
    fake = tmp_path / "rtrace"
    fake.write_text("#!/bin/sh\n"); fake.chmod(0o755)
    monkeypatch.setenv("HCL_RADIANCE_BIN", str(tmp_path))
    assert resolve_bin("rtrace") == str(fake)

def test_resolve_bin_missing_returns_none(monkeypatch):
    monkeypatch.setenv("HCL_RADIANCE_BIN", "/nonexistent_dir_xyz")
    monkeypatch.setattr("shutil.which", lambda name: None)
    assert resolve_bin("rtrace") is None
