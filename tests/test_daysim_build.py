"""build_daysim: which source it builds, and when it builds at all.

The build downloads code and compiles it on the user's machine, so three things are pinned
here: it builds ONE known commit and checks that it got it; it does not build a folder it
cannot identify as that source; and it does nothing but print the plan unless asked to run.

The tests that run git use a small local repository as the "upstream", so they are real git
behaviour with no network. `cmake` is a stand-in that records its calls.
"""
import inspect
import os
import shutil
import stat
import subprocess
import sys

import pytest

import hcl_daysim.build as build

needs_git = pytest.mark.skipif(shutil.which("git") is None or os.name != "posix",
                               reason="needs git and a POSIX shell")


# ---- the plan (nothing runs) ----

def test_nothing_is_built_unless_run_is_asked_for():
    assert inspect.signature(build.build_daysim).parameters["run"].default is False
    out = build.build_daysim(src_dir="/tmp/Daysim")
    assert out["ran"] is False and "run=True" in out["reason"]


def test_the_plan_names_one_commit_not_a_moving_branch():
    out = build.build_daysim(src_dir="/tmp/Daysim", run=False)
    joined = "\n".join(out["commands"])
    assert "github.com/MITSustainableDesignLab/Daysim" in joined
    assert build.PINNED_COMMIT in joined and len(build.PINNED_COMMIT) == 40
    assert "--branch" not in joined and " master" not in joined
    assert out["source"] == {"repo": build.REPO, "ref": build.PINNED_COMMIT, "pinned": True}


def test_the_plan_keeps_the_cmake_flags_and_targets():
    joined = "\n".join(build.build_daysim(src_dir="/tmp/Daysim", run=False)["commands"])
    assert "-DBUILD_HEADLESS=ON" in joined
    assert "-DCMAKE_BUILD_TYPE=Release" in joined
    assert "-DCMAKE_POLICY_VERSION_MINIMUM=3.5" in joined
    assert "--target ds_shortterm epw2wea" in joined


def test_build_uses_given_src_dir_in_paths():
    out = build.build_daysim(src_dir="/opt/Daysim", run=False)
    assert "/opt/Daysim/build" in "\n".join(out["commands"])
    assert out["bin_dir"] == "/opt/Daysim/build/bin"


def test_build_default_src_dir_under_work(tmp_path):
    out = build.build_daysim(src_dir=None, run=False, work_dir=str(tmp_path))
    assert out["bin_dir"].endswith("/build/bin") and str(tmp_path) in out["bin_dir"]


def test_build_emit_when_no_compiler(monkeypatch, tmp_path):
    monkeypatch.setattr(build.shutil, "which", lambda name: None)
    out = build.build_daysim(src_dir=str(tmp_path / "Daysim"), run=True, work_dir=str(tmp_path))
    assert out["ran"] is False and "cmake" in out["reason"].lower()
    assert any("cmake" in c for c in out["commands"])


def test_only_the_user_can_change_what_is_built():
    """The ref comes from the environment of the server, which the user sets. It is not a tool
    argument: the model that calls the tool cannot point the build at other code."""
    assert "ref" not in inspect.signature(build.build_daysim).parameters
    assert "repo" not in inspect.signature(build.build_daysim).parameters


# ---- real git against a local upstream ----

def _git(cwd, *args):
    done = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                           "-c", "commit.gpgsign=false", *args], cwd=cwd, check=True,
                          capture_output=True, text=True)
    return done.stdout.strip()


@pytest.fixture
def upstream(tmp_path, monkeypatch):
    """A local "Daysim" repository with two commits; the FIRST is the pinned one, so the
    branch has already moved past the pin. Returns the paths and both commits."""
    repo = tmp_path / "upstream"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "master")
    _git(repo, "config", "uploadpack.allowAnySHA1InWant", "true")   # as GitHub allows
    (repo / "CMakeLists.txt").write_text("# daysim, the pinned state\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "pinned")
    pinned = _git(repo, "rev-parse", "HEAD")
    (repo / "CMakeLists.txt").write_text("# daysim, a later state nobody here has looked at\n")
    _git(repo, "commit", "-q", "-am", "later")
    later = _git(repo, "rev-parse", "HEAD")

    # A stand-in cmake: logs each call; `--build <dir>` leaves the two programs in <dir>/bin.
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    log = tmp_path / "cmake.log"
    cmake = bin_dir / "cmake"
    cmake.write_text(f"#!{sys.executable}\nimport os, sys\n"
                     f"open({str(log)!r}, 'a').write(' '.join(sys.argv[1:]) + '\\n')\n"
                     "if '--build' in sys.argv:\n"
                     "    out = os.path.join(sys.argv[sys.argv.index('--build') + 1], 'bin')\n"
                     "    os.makedirs(out, exist_ok=True)\n"
                     "    for name in ('ds_shortterm', 'epw2wea'):\n"
                     "        open(os.path.join(out, name), 'w').close()\n")
    cmake.chmod(cmake.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.delenv("HCL_DAYSIM_REF", raising=False)
    monkeypatch.setattr(build, "REPO", str(repo))
    monkeypatch.setattr(build, "PINNED_COMMIT", pinned)

    class Upstream:
        pass
    u = Upstream()
    u.repo, u.pinned, u.later, u.work, u.log = repo, pinned, later, tmp_path / "work", log
    u.src = u.work / "Daysim"
    u.cmake_calls = lambda: log.read_text().splitlines() if log.exists() else []
    return u


def _build(u, **kw):
    return build.build_daysim(str(u.src), run=True, work_dir=str(u.work), **kw)


@needs_git
def test_a_fresh_build_gets_the_pinned_commit_though_the_branch_has_moved_on(upstream):
    out = _build(upstream)
    assert out["ran"] is True, out
    assert _git(upstream.src, "rev-parse", "HEAD") == upstream.pinned != upstream.later
    assert "pinned state" in (upstream.src / "CMakeLists.txt").read_text()
    assert out["source"]["commit"] == upstream.pinned and out["source"]["pinned"] is True
    assert len(upstream.cmake_calls()) == 2


@needs_git
def test_an_existing_clean_clone_at_another_commit_is_moved_to_the_pin(upstream):
    """It used to `fetch` and then `checkout master`, which leaves the local branch where it
    was: an old clone was rebuilt at its old commit for ever."""
    upstream.work.mkdir()
    _git(upstream.work, "clone", "-q", str(upstream.repo), str(upstream.src))
    assert _git(upstream.src, "rev-parse", "HEAD") == upstream.later
    out = _build(upstream)
    assert out["ran"] is True, out
    assert _git(upstream.src, "rev-parse", "HEAD") == upstream.pinned


@needs_git
def test_a_clone_at_the_pin_with_a_local_fix_is_built_and_the_fix_is_reported(upstream):
    """The documented way out of the `time_step` compile error is to edit one line and build
    again. That must keep working, and the result must say the source is not pristine."""
    assert _build(upstream)["ran"] is True
    (upstream.src / "CMakeLists.txt").write_text("# daysim, with my one-line fix\n")
    out = _build(upstream)
    assert out["ran"] is True, out
    assert out["source"]["local_changes"] == ["CMakeLists.txt"]
    assert "my one-line fix" in (upstream.src / "CMakeLists.txt").read_text()   # not discarded


@needs_git
def test_a_changed_clone_at_another_commit_is_not_built(upstream):
    upstream.work.mkdir()
    _git(upstream.work, "clone", "-q", str(upstream.repo), str(upstream.src))
    (upstream.src / "CMakeLists.txt").write_text("# something else entirely\n")
    out = _build(upstream)
    assert out["ran"] is False and "local changes" in out["reason"]
    assert upstream.cmake_calls() == []
    assert "something else" in (upstream.src / "CMakeLists.txt").read_text()    # left alone


@needs_git
def test_a_clone_of_some_other_repository_is_not_built(upstream, tmp_path):
    """`src_dir` is a tool argument. Pointed at an existing checkout of other code, the tool
    used to run cmake on whatever was there."""
    other = tmp_path / "other"
    other.mkdir()
    _git(other, "init", "-q", "-b", "master")
    (other / "CMakeLists.txt").write_text("# not daysim\n")
    _git(other, "add", "-A")
    _git(other, "commit", "-q", "-m", "x")
    upstream.work.mkdir()
    _git(upstream.work, "clone", "-q", str(other), str(upstream.src))
    out = _build(upstream)
    assert out["ran"] is False and "origin" in out["reason"]
    assert upstream.cmake_calls() == []


@needs_git
def test_a_folder_that_is_not_a_checkout_is_not_built(upstream):
    upstream.src.mkdir(parents=True)
    (upstream.src / "CMakeLists.txt").write_text("# who knows\n")
    out = _build(upstream)
    assert out["ran"] is False and "not a git checkout" in out["reason"]
    assert upstream.cmake_calls() == []


@needs_git
def test_cmake_does_not_run_if_the_checkout_is_not_the_commit_asked_for(upstream, monkeypatch):
    """The last gate before any code is configured or compiled."""
    monkeypatch.setattr(build, "_head_commit", lambda src, **k: "0" * 40)
    out = _build(upstream)
    assert out["ran"] is False and "expected" in out["reason"]
    assert upstream.cmake_calls() == []


@needs_git
def test_a_commit_the_upstream_does_not_have_stops_the_build(upstream, monkeypatch):
    monkeypatch.setattr(build, "PINNED_COMMIT", "1" * 40)
    out = _build(upstream)
    assert out["ran"] is False and "fetch" in out["reason"]
    assert upstream.cmake_calls() == []


@needs_git
def test_the_user_can_ask_for_another_ref_and_the_result_says_it_is_not_the_pin(
        upstream, monkeypatch):
    monkeypatch.setenv("HCL_DAYSIM_REF", "master")
    out = _build(upstream)
    assert out["ran"] is True, out
    assert _git(upstream.src, "rev-parse", "HEAD") == upstream.later
    assert out["source"]["pinned"] is False and out["source"]["ref"] == "master"
    assert out["source"]["commit"] == upstream.later


def test_a_ref_that_could_be_read_as_an_option_is_refused(monkeypatch, tmp_path):
    monkeypatch.setenv("HCL_DAYSIM_REF", "--upload-pack=touch /tmp/x")
    out = build.build_daysim(str(tmp_path / "Daysim"), run=True, work_dir=str(tmp_path))
    assert out["ran"] is False and "HCL_DAYSIM_REF" in out["reason"]
