import hcl_daysim.build as build

def test_build_commands_emit_master_and_targets():
    out = build.build_daysim(src_dir="/tmp/Daysim", run=False)
    assert out["ran"] is False
    joined = "\n".join(out["commands"])
    # clone the MITSustainableDesignLab repo on the master branch
    assert "github.com/MITSustainableDesignLab/Daysim" in joined
    assert "--branch master" in joined or "-b master" in joined
    # the exact cmake configure flags from the recon
    assert "-DBUILD_HEADLESS=ON" in joined
    assert "-DCMAKE_BUILD_TYPE=Release" in joined
    assert "-DCMAKE_OSX_ARCHITECTURES=arm64" in joined
    assert "-DCMAKE_POLICY_VERSION_MINIMUM=3.5" in joined
    # build only the two targets we use
    assert "--target ds_shortterm epw2wea" in joined

def test_build_uses_given_src_dir_in_paths():
    out = build.build_daysim(src_dir="/opt/Daysim", run=False)
    joined = "\n".join(out["commands"])
    assert "/opt/Daysim/build" in joined
    assert out["bin_dir"] == "/opt/Daysim/build/bin"

def test_build_default_src_dir_under_work(monkeypatch, tmp_path):
    out = build.build_daysim(src_dir=None, run=False, work_dir=str(tmp_path))
    assert out["bin_dir"].endswith("/build/bin")
    assert str(tmp_path) in out["bin_dir"]

def test_build_emit_when_no_compiler(monkeypatch, tmp_path):
    # Pretend cmake is absent: run=True must NOT execute; returns the plan + a reason.
    monkeypatch.setattr(build.shutil, "which", lambda name: None)
    out = build.build_daysim(src_dir=str(tmp_path / "Daysim"), run=True, work_dir=str(tmp_path))
    assert out["ran"] is False
    assert "cmake" in out["reason"].lower()
    assert any("cmake" in c for c in out["commands"])

def test_build_resume_refreshes_existing_clone(monkeypatch, tmp_path):
    # Existing .git: refresh to BRANCH (fetch + checkout) before cmake, never re-clone.
    src = tmp_path / "Daysim"
    (src / ".git").mkdir(parents=True)
    monkeypatch.setattr(build.shutil, "which", lambda name: f"/usr/bin/{name}")
    calls = []
    def fake_run(argv, **kwargs):
        calls.append(argv)
        class R:
            returncode = 0
            stdout = b""
        return R()
    monkeypatch.setattr(build.subprocess, "run", fake_run)
    bin_dir = src / "build" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "ds_shortterm").write_text("")
    (bin_dir / "epw2wea").write_text("")
    out = build.build_daysim(src_dir=str(src), run=True, work_dir=str(tmp_path))
    assert out["ran"] is True
    assert not any(c[:2] == ["git", "clone"] for c in calls)
    fetch_calls = [c for c in calls if "fetch" in c]
    checkout_calls = [c for c in calls if "checkout" in c]
    assert fetch_calls and build.BRANCH in fetch_calls[0]
    assert checkout_calls and build.BRANCH in checkout_calls[0]
    first_cmake = next(i for i, c in enumerate(calls) if c and c[0] == "cmake")
    assert calls.index(fetch_calls[0]) < first_cmake
    assert calls.index(checkout_calls[0]) < first_cmake

def test_build_resume_emitted_commands_unchanged(monkeypatch, tmp_path):
    # The emitted (run=False) plan is the fresh-clone plan regardless of resume state.
    out = build.build_daysim(src_dir=str(tmp_path / "Daysim"), run=False, work_dir=str(tmp_path))
    joined = "\n".join(out["commands"])
    assert "git clone" in joined
    assert not any("fetch" in c or "checkout" in c for c in out["commands"])
