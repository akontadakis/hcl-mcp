from hcl_daysim.discover import daysim_status, resolve_bin, _available

def test_status_shape():
    st = daysim_status()
    assert set(["available", "bin_dir", "version", "found", "missing"]) <= set(st.keys())
    assert isinstance(st["available"], bool)
    assert isinstance(st["found"], list) and isinstance(st["missing"], list)

def test_resolve_bin_uses_env(monkeypatch, tmp_path):
    fake = tmp_path / "ds_shortterm"
    fake.write_text("#!/bin/sh\n"); fake.chmod(0o755)
    monkeypatch.setenv("HCL_DAYSIM_BIN", str(tmp_path))
    assert resolve_bin("ds_shortterm") == str(fake)

def test_resolve_bin_missing_returns_none(monkeypatch):
    monkeypatch.setenv("HCL_DAYSIM_BIN", "/nonexistent_dir_xyz")
    monkeypatch.setattr("shutil.which", lambda name: None)
    assert resolve_bin("ds_shortterm") is None

def test_available_true_when_both_present(monkeypatch, tmp_path):
    for name in ("ds_shortterm", "epw2wea"):
        f = tmp_path / name
        f.write_text("#!/bin/sh\n"); f.chmod(0o755)
    monkeypatch.setenv("HCL_DAYSIM_BIN", str(tmp_path))
    st = daysim_status()
    assert st["available"] is True
    assert st["bin_dir"] == str(tmp_path)
    assert set(st["found"]) == {"ds_shortterm", "epw2wea"} and st["missing"] == []

def test_available_false_when_one_missing(monkeypatch, tmp_path):
    f = tmp_path / "epw2wea"           # only one of the two present
    f.write_text("#!/bin/sh\n"); f.chmod(0o755)
    monkeypatch.setenv("HCL_DAYSIM_BIN", str(tmp_path))
    monkeypatch.setattr("shutil.which", lambda name: None)
    st = daysim_status()
    assert st["available"] is False
    assert "ds_shortterm" in st["missing"] and "epw2wea" in st["found"]
    assert _available() is False
