"""Build-from-source helper for Daysim (spec §4.1, §10).

We never bundle or redistribute Daysim binaries (NRC/Fraunhofer ISE source-available EULA);
this clones + builds on the user's machine. Branch is `master` (the README's `combined` is gone).
The headless flags + CMAKE_POLICY_VERSION_MINIMUM=3.5 avoid the two known macOS frictions. On macOS
the `-DCMAKE_OSX_ARCHITECTURES` flag is set to the host architecture (arm64 on Apple silicon); off
macOS that Apple-only flag is omitted so the plan is usable on Linux too.

Known source wart: src/daysim/ds_shortterm.c declares a `time_step` extern that some toolchains
reject; on a build failure we emit the plan so the user can apply the one-line fix and rebuild.
"""
import os
import platform
import shutil
import subprocess

from hcl_core import jobcontrol
from hcl_platform import shell_quote

REPO = "https://github.com/MITSustainableDesignLab/Daysim.git"
BRANCH = "master"
# cmake --build can compile for several minutes; cap each step so a hang can't block forever.
_BUILD_TIMEOUT = 1800

def _configure_flags():
    """cmake configure flags. The Apple-only OSX-arch flag is added (host arch) only on macOS."""
    flags = ["-DBUILD_HEADLESS=ON", "-DCMAKE_BUILD_TYPE=Release"]
    if platform.system() == "Darwin":
        flags.append(f"-DCMAKE_OSX_ARCHITECTURES={platform.machine()}")
    flags.append("-DCMAKE_POLICY_VERSION_MINIMUM=3.5")
    return flags

def _plan(src_dir):
    """Ordered clone + configure + build commands (the exact ground-truth recon plan)."""
    build_dir = f"{src_dir}/build"
    # Quoted for a shell: these lines are for a person to paste, and a path may hold a blank.
    src, build = shell_quote(src_dir), shell_quote(build_dir)
    clone = (f"git clone --depth 1 --branch {BRANCH} {REPO} {src}")
    configure = f"cmake -S {src} -B {build} " + " ".join(_configure_flags())
    compile_ = f"cmake --build {build} --target ds_shortterm epw2wea"
    return [clone, configure, compile_], f"{build_dir}/bin"

def build_daysim(src_dir=None, *, run=True, work_dir=None, build_timeout=_BUILD_TIMEOUT):
    """Emit (or run) the Daysim build plan.

    src_dir: where to clone/build (default <work_dir>/Daysim). run: execute if cmake+git present.
    build_timeout: per-step subprocess timeout in seconds (clone/configure/compile each).
    Returns {commands, ran, bin_dir, reason?}. On run=True success, bin_dir is the built build/bin
    (set it as HCL_DAYSIM_BIN). On run=False or missing toolchain/failure, returns the plan + reason.
    """
    work = work_dir or os.path.expanduser("~/hcl_work")
    if src_dir is None:
        src_dir = os.path.join(work, "Daysim")
    commands, bin_dir = _plan(src_dir)

    if not run:
        return {"commands": commands, "ran": False, "bin_dir": bin_dir,
                "reason": "run=False: emitted the clone+cmake plan. After building, "
                          "set HCL_DAYSIM_BIN to the build/bin directory."}

    if not (shutil.which("git") and shutil.which("cmake")):
        return {"commands": commands, "ran": False, "bin_dir": bin_dir,
                "reason": "git and cmake are required to build Daysim; run the emitted "
                          "commands on a machine with both, then set HCL_DAYSIM_BIN."}

    os.makedirs(work, exist_ok=True)
    argvs = [
        ["git", "clone", "--depth", "1", "--branch", BRANCH, REPO, src_dir],
        ["cmake", "-S", src_dir, "-B", f"{src_dir}/build"] + _configure_flags(),
        ["cmake", "--build", f"{src_dir}/build", "--target", "ds_shortterm", "epw2wea"],
    ]
    if os.path.isdir(os.path.join(src_dir, ".git")):
        # Already cloned (has .git): don't build whatever happens to be checked out.
        # Refresh the existing tree to the intended BRANCH (fetch + checkout) before
        # configuring/building, then skip the clone step.
        argvs = [
            ["git", "-C", src_dir, "fetch", "origin", BRANCH],
            ["git", "-C", src_dir, "checkout", BRANCH],
        ] + argvs[1:]
    for i, argv in enumerate(argvs, 1):
        # Clone, configure and compile are minutes each: report them, and stop between or
        # during them if the caller gave up (no-ops outside a job).
        jobcontrol.step(f"{' '.join(argv[:2])} ({i}/{len(argvs)})")
        try:
            proc = jobcontrol.run(argv, cwd=work, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, timeout=build_timeout)
        except subprocess.TimeoutExpired:
            return {"commands": commands, "ran": False, "bin_dir": bin_dir,
                    "reason": f"Daysim build step timed out after {build_timeout}s: "
                              + " ".join(argv) + "\nRun it manually, or raise build_timeout."}
        if proc.returncode != 0:
            return {"commands": commands, "ran": False, "bin_dir": bin_dir,
                    "reason": "Daysim build step failed: " + " ".join(argv) + "\n"
                              + proc.stdout.decode("utf-8", "ignore")[-2000:]
                              + "\n(If ds_shortterm.c errors on the `time_step` extern, apply the "
                                "one-line fix and rerun the cmake --build step.)"}
    ok = os.path.isfile(os.path.join(bin_dir, "ds_shortterm")) and \
        os.path.isfile(os.path.join(bin_dir, "epw2wea"))
    return {"commands": commands, "ran": ok, "bin_dir": bin_dir,
            "reason": None if ok else "Build finished but ds_shortterm/epw2wea not found in build/bin."}
