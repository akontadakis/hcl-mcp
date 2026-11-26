"""Build-from-source helper for Daysim (spec §4.1, §10).

We never bundle or redistribute Daysim binaries (NRC/Fraunhofer ISE source-available EULA);
this fetches the source and builds it on the user's machine.

What is built is ONE commit, `PINNED_COMMIT`, not whatever the `master` branch holds on the
day. The build downloads code and compiles it; a moving branch means running code nobody here
has looked at. The checkout is compared with the pin before cmake is started. A user who
wants another state sets HCL_DAYSIM_REF in the server's environment (a commit or a branch);
that is not a tool argument, so the model calling the tool cannot choose the code.

An existing `src_dir` is built only if it can be identified: a git checkout whose `origin`
is the Daysim repository, at the wanted commit. Local edits at that commit are allowed and
reported (the known `time_step` compile error is fixed by editing one line); a checkout at
another commit is moved to the pin if it is clean and refused if it is not.

The headless flags + CMAKE_POLICY_VERSION_MINIMUM=3.5 avoid the two known macOS frictions. On macOS
the `-DCMAKE_OSX_ARCHITECTURES` flag is set to the host architecture (arm64 on Apple silicon); off
macOS that Apple-only flag is omitted so the plan is usable on Linux too.

Known source wart: src/daysim/ds_shortterm.c declares a `time_step` extern that some toolchains
reject; on a build failure we emit the plan so the user can apply the one-line fix and rebuild.
"""
import os
import platform
import re
import shutil
import subprocess

from hcl_core import jobcontrol
from hcl_platform import shell_join, shell_quote

REPO = "https://github.com/MITSustainableDesignLab/Daysim.git"
#: The Daysim commit this server builds: `master` as of 2025-01-19, the state its adapter
#: (epw2wea -> ds_shortterm) was written and run against. Move it deliberately, after
#: building and running the Daysim live tests against the new commit.
PINNED_COMMIT = "27df1dfc98b6a75e209f787bef98374ce86ca077"
# cmake --build can compile for several minutes; cap each step so a hang can't block forever.
_BUILD_TIMEOUT = 1800
_QUERY_TIMEOUT = 60
_SHA = re.compile(r"[0-9a-fA-F]{40}")
#: A commit or branch name. No leading `-` (git would read it as an option), no `..`.
_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*")


def wanted_ref():
    """(ref, pinned): the commit to build, and whether it is this server's own pin."""
    ref = (os.environ.get("HCL_DAYSIM_REF") or "").strip()
    if not ref:
        return PINNED_COMMIT, True
    return ref, ref.lower() == PINNED_COMMIT.lower()


def _configure_flags():
    """cmake configure flags. The Apple-only OSX-arch flag is added (host arch) only on macOS."""
    flags = ["-DBUILD_HEADLESS=ON", "-DCMAKE_BUILD_TYPE=Release"]
    if platform.system() == "Darwin":
        flags.append(f"-DCMAKE_OSX_ARCHITECTURES={platform.machine()}")
    flags.append("-DCMAKE_POLICY_VERSION_MINIMUM=3.5")
    return flags

def _fetch_steps(src_dir, ref):
    """Bring `ref` into an initialised checkout and stand on it. A full commit id can be
    fetched directly (GitHub serves any commit reachable from a branch), one commit deep."""
    return [["git", "-C", src_dir, "fetch", "--depth", "1", "origin", ref],
            ["git", "-C", src_dir, "-c", "advice.detachedHead=false", "checkout", "--detach",
             "FETCH_HEAD"]]


def _fresh_steps(src_dir, ref):
    return [["git", "init", "-q", src_dir],
            ["git", "-C", src_dir, "remote", "add", "origin", REPO],
            *_fetch_steps(src_dir, ref)]


def _cmake_steps(src_dir):
    build_dir = f"{src_dir}/build"
    return [["cmake", "-S", src_dir, "-B", build_dir] + _configure_flags(),
            ["cmake", "--build", build_dir, "--target", "ds_shortterm", "epw2wea"]]


def _plan(src_dir, ref=None):
    """Ordered fetch + configure + build commands for a fresh folder, as text to paste."""
    ref = ref or PINNED_COMMIT
    steps = _fresh_steps(src_dir, ref) + _cmake_steps(src_dir)
    return [shell_join(argv) for argv in steps], f"{src_dir}/build/bin"


def _git_out(src_dir, *args):
    """Output of a quick git query in `src_dir`, or None if git says no."""
    done = jobcontrol.run(["git", "-C", src_dir, *args], stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, timeout=_QUERY_TIMEOUT)
    # rstrip only: `git status --porcelain` lines start with a significant blank.
    return done.stdout.decode("utf-8", "ignore").rstrip() if done.returncode == 0 else None


def _head_commit(src_dir):
    return _git_out(src_dir, "rev-parse", "HEAD")


def _local_changes(src_dir):
    """Tracked files that differ from the commit. The build folder is untracked and ignored."""
    out = _git_out(src_dir, "status", "--porcelain", "--untracked-files=no") or ""
    return [line[3:] for line in out.splitlines() if line.strip()]


def _same_repo(a, b):
    def norm(url):
        url = (url or "").strip().rstrip("/")
        url = url[:-4] if url.endswith(".git") else url
        return url.lower() if "://" in url or url.startswith("git@") else os.path.realpath(url)
    return bool(a) and norm(a) == norm(b)


def build_daysim(src_dir=None, *, run=False, work_dir=None, build_timeout=_BUILD_TIMEOUT):
    """Emit (or, with run=True, run) the Daysim build plan.

    run: False (the default) only returns the commands. True downloads the source and compiles
    it, which is why it has to be asked for. src_dir: where to fetch and build (default
    <work_dir>/Daysim); an existing folder is built only if it is a Daysim checkout at the
    wanted commit (see the module text). build_timeout: per-step timeout in seconds.

    Returns {commands, ran, bin_dir, source, reason?}. `source` is {repo, ref, pinned} plus,
    after a run, `commit` (what was actually built) and `local_changes` if the checkout had
    any. On success set HCL_DAYSIM_BIN to `bin_dir`.
    """
    work = work_dir or os.path.expanduser("~/hcl_work")
    if src_dir is None:
        src_dir = os.path.join(work, "Daysim")
    ref, pinned = wanted_ref()
    source = {"repo": REPO, "ref": ref, "pinned": pinned}
    commands, bin_dir = _plan(src_dir, ref if _REF.fullmatch(ref) else PINNED_COMMIT)

    def stopped(reason, **extra):
        return {"commands": commands, "ran": False, "bin_dir": bin_dir, "source": source,
                "reason": reason, **extra}

    if not _REF.fullmatch(ref) or ".." in ref:
        return stopped(f"HCL_DAYSIM_REF={ref!r} is not a commit id or a branch name; nothing "
                       "was fetched. Unset it to build the pinned commit.")
    if not run:
        return stopped("run=False: emitted the fetch + cmake plan and ran nothing. Call again "
                       "with run=True to download and compile it; then set HCL_DAYSIM_BIN to "
                       "the build/bin directory.")
    if not (shutil.which("git") and shutil.which("cmake")):
        return stopped("git and cmake are required to build Daysim; run the emitted "
                       "commands on a machine with both, then set HCL_DAYSIM_BIN.")

    os.makedirs(work, exist_ok=True)
    # ---- which git steps does this folder need? ----
    if not os.path.exists(src_dir) or (os.path.isdir(src_dir) and not os.listdir(src_dir)):
        git_steps = _fresh_steps(src_dir, ref)
    elif not os.path.isdir(os.path.join(src_dir, ".git")):
        return stopped(f"{src_dir} exists and is not a git checkout, so there is no telling "
                       "what it holds. Nothing was built. Name an empty or new folder, or "
                       "build that source yourself with the emitted cmake commands.")
    else:
        origin = _git_out(src_dir, "remote", "get-url", "origin")
        if not _same_repo(origin, REPO):
            return stopped(f"{src_dir} is a checkout of another repository (origin: "
                           f"{origin or 'none'}; expected {REPO}). Nothing was built.")
        at_the_commit = bool(_SHA.fullmatch(ref)) and (
            (_head_commit(src_dir) or "").lower() == ref.lower())
        changes = _local_changes(src_dir)
        if at_the_commit:
            git_steps = []                 # nothing to fetch; local edits are built and reported
        elif changes:
            return stopped(f"{src_dir} is not at {ref} and has local changes "
                           f"({', '.join(changes[:5])}). Moving it would mix or lose them, so "
                           "nothing was built. Commit or discard them, or name a new folder.",
                           source={**source, "local_changes": changes})
        else:
            git_steps = _fetch_steps(src_dir, ref)

    def run_steps(steps, first, total):
        for i, argv in enumerate(steps, first):
            # Fetch, configure and compile are minutes each: report them, and stop between or
            # during them if the caller gave up (no-ops outside a job).
            jobcontrol.step(f"{' '.join(a for a in argv[:4] if a != src_dir)} ({i}/{total})")
            try:
                proc = jobcontrol.run(argv, cwd=work, stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT, timeout=build_timeout)
            except subprocess.TimeoutExpired:
                return (f"Daysim build step timed out after {build_timeout}s: "
                        + shell_join(argv) + "\nRun it manually, or raise build_timeout.")
            if proc.returncode != 0:
                return ("Daysim build step failed: " + shell_join(argv) + "\n"
                        + proc.stdout.decode("utf-8", "ignore")[-2000:]
                        + "\n(If ds_shortterm.c errors on the `time_step` extern, apply the "
                          "one-line fix and rerun the cmake --build step.)")
        return None

    cmake_steps = _cmake_steps(src_dir)
    total = len(git_steps) + len(cmake_steps)
    failed = run_steps(git_steps, 1, total)
    if failed:
        return stopped(failed)

    # ---- the gate: is the folder at the commit that was asked for? Only then compile. ----
    commit = _head_commit(src_dir)
    source = {**source, "commit": commit}
    if _SHA.fullmatch(ref) and (commit or "").lower() != ref.lower():
        return stopped(f"the checkout in {src_dir} is at {commit or 'no commit'}; expected "
                       f"{ref}. Nothing was configured or compiled.")
    changes = _local_changes(src_dir)
    if changes:
        source["local_changes"] = changes

    failed = run_steps(cmake_steps, len(git_steps) + 1, total)
    if failed:
        return stopped(failed)
    ok = os.path.isfile(os.path.join(bin_dir, "ds_shortterm")) and \
        os.path.isfile(os.path.join(bin_dir, "epw2wea"))
    return {"commands": commands, "ran": ok, "bin_dir": bin_dir, "source": source,
            "reason": None if ok else "Build finished but ds_shortterm/epw2wea not found in build/bin."}
