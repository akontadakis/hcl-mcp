"""Cross-platform contract for the hcl_platform compat layer."""
import os
import pytest


# --- rad_path -------------------------------------------------------------
def test_rad_path_forward_slashes_backslashes():
    from hcl_platform import rad_path
    assert rad_path("C:\\rooms\\a.rad") == "C:/rooms/a.rad"


def test_rad_path_preserves_relative():
    # Relative generated names (materials/sky in work_dir) must stay relative — only the
    # separator is normalized, never made absolute (else they'd stop resolving in work_dir).
    from hcl_platform import rad_path
    assert rad_path("materials.rad") == "materials.rad"
    assert rad_path("sub/a.rad") == "sub/a.rad"


def test_rad_path_idempotent():
    from hcl_platform import rad_path
    once = rad_path("C:\\x\\room.rad")
    assert rad_path(once) == once


# --- resolve_exe ----------------------------------------------------------
def test_resolve_exe_finds_bare_name_in_bin_dir(tmp_path):
    from hcl_platform import resolve_exe
    exe = tmp_path / "rtrace"
    exe.write_text("#!/bin/sh\n")
    os.chmod(exe, 0o755)
    assert resolve_exe("rtrace", str(tmp_path)) == str(exe)


def test_resolve_exe_tries_windows_extensions(tmp_path, monkeypatch):
    import hcl_platform.exe as exe_mod
    (tmp_path / "rtrace.exe").write_text("MZ")
    monkeypatch.setattr(exe_mod, "_pathext", lambda: ["", ".exe"])
    monkeypatch.setattr(exe_mod.os, "name", "nt")  # skip the POSIX X_OK gate
    assert exe_mod.resolve_exe("rtrace", str(tmp_path)) == str(tmp_path / "rtrace.exe")


def test_resolve_exe_returns_none_when_absent(tmp_path):
    from hcl_platform import resolve_exe
    assert resolve_exe("no_such_binary_xyz", str(tmp_path)) is None


def test_resolve_exe_falls_back_to_which(tmp_path, monkeypatch):
    from hcl_platform import resolve_exe
    import hcl_platform.exe as exe_mod
    monkeypatch.setattr(exe_mod.shutil, "which", lambda n: "/usr/bin/" + n if n == "found" else None)
    assert resolve_exe("found", None) == "/usr/bin/found"


# --- read_text / write_text ----------------------------------------------
def test_write_text_uses_lf_not_crlf(tmp_path):
    from hcl_platform import write_text
    p = tmp_path / "a.rad"
    write_text(str(p), "void plastic m\n0\n0\n5 .5 .5 .5 0 0\n")
    raw = p.read_bytes()
    assert b"\r\n" not in raw
    assert raw.endswith(b"0 0\n")


def test_read_text_normalizes_newlines(tmp_path):
    from hcl_platform import read_text
    p = tmp_path / "b.txt"
    p.write_bytes(b"line1\r\nline2\r\n")
    assert read_text(str(p)) == "line1\nline2\n"


def test_write_text_append(tmp_path):
    from hcl_platform import read_text, write_text
    p = tmp_path / "c.txt"
    write_text(str(p), "a\n")
    write_text(str(p), "b\n", append=True)
    assert read_text(str(p)) == "a\nb\n"


# --- integration: exec resolution wired through the compat layer -----------
def test_radiance_runner_forwards_path_prepend(monkeypatch):
    # The Radiance runner must forward HCL_RADIANCE_BIN into proc.run_sequence's path_prepend, or a
    # binary reachable only via the env var resolves for discovery yet never executes (R-6).
    import hcl_radiance.runner as rr
    captured = {}

    def fake(steps, work_dir, available, *, unavailable_reason, timeout=None, path_prepend=None,
             env_extra=None):
        captured["path_prepend"] = path_prepend
        return {"ran": False, "commands": []}

    monkeypatch.setenv("HCL_RADIANCE_BIN", "/opt/rad/bin")
    monkeypatch.setattr(rr, "_run_sequence", fake)
    rr.run_sequence([{"cmd": ["oconv"]}], "wd", False)
    assert captured["path_prepend"] == ["/opt/rad/bin"]


def test_spectral_native_honors_radiance_bin(tmp_path, monkeypatch):
    # gensdaymtx reachable ONLY via HCL_RADIANCE_BIN (not on PATH) must be detected.
    for name in ("gensdaymtx", "rcomb"):
        (tmp_path / name).write_text("#!/bin/sh\n")
        os.chmod(tmp_path / name, 0o755)
    monkeypatch.setenv("HCL_RADIANCE_BIN", str(tmp_path))
    from hcl_radiance.spectral_native import radiance_spectral_status
    st = radiance_spectral_status()
    assert st["available"] is True
    assert st["gensdaymtx"] == str(tmp_path / "gensdaymtx")


def test_radiance_resolve_bin_finds_env_only_binary(tmp_path, monkeypatch):
    (tmp_path / "oconv").write_text("#!/bin/sh\n")
    os.chmod(tmp_path / "oconv", 0o755)
    monkeypatch.setenv("HCL_RADIANCE_BIN", str(tmp_path))
    from hcl_radiance.discover import resolve_bin
    assert resolve_bin("oconv") == str(tmp_path / "oconv")


# --- rad_path wired at the user-path command seams ------------------------
def test_build_oconv_forward_slashes_user_paths_keeps_relative():
    from hcl_radiance.commands import build_oconv
    # Absolute (user) path gets forward-slashed; the generated relative name is untouched.
    assert build_oconv(["C:\\rooms\\a.rad", "materials.rad"], "s.oct") == \
        ["oconv", "-f", "C:/rooms/a.rad", "materials.rad"]


def test_build_obj2rad_forward_slashes_obj_path():
    from hcl_radiance.geometry_import import build_obj2rad
    assert build_obj2rad("C:\\rooms\\room.obj", "map.txt") == \
        ["obj2rad", "-m", "map.txt", "C:/rooms/room.obj"]


def test_build_ies2rad_forward_slashes_ies_path():
    from hcl_radiance.ies_radiance import build_ies2rad
    assert "C:/l.ies" in build_ies2rad("C:\\l.ies")
    assert "\\" not in build_ies2rad("C:\\l.ies", inline=True)
