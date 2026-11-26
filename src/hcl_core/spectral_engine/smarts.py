"""SMARTS 2.9.5 backend — the validation-oracle slot (fully implemented in Phase 6).

Capability-gated: smarts_available() reports whether a runnable SMARTS binary is configured via the
SMARTSPATH env var.  build_deck / parse_ext_output handle SMARTS I/O (input-deck generation and
output parsing), and SmartsEngine.compute() runs the smarts295bat subprocess in a fresh temp dir.
When SMARTSPATH is unset or the binary is absent, compute() raises RuntimeError — so green pytest
results do NOT imply a live SMARTS run; they only verify the Python logic with the binary gated off.
"""
import os
import shutil
import subprocess
import tempfile

from hcl_core import jobcontrol
from hcl_core.spectral_engine.base import ClearSkySpectra


SMARTS_BINARY_NAME = "smarts295bat"


def smarts_available() -> bool:
    """True iff SMARTSPATH names an existing executable file."""
    path = os.environ.get("SMARTSPATH")
    return bool(path) and os.path.isfile(path) and os.access(path, os.X_OK)


def smarts_misconfigured():
    """Why a *set* SMARTSPATH is unusable, or None if it is usable or simply unset.

    `smarts_available()` collapses two very different states into one False: SMARTSPATH unset
    (a legitimate "SMARTS not installed" configuration) and SMARTSPATH set to something wrong
    (a mistake the user believes they have already fixed). Only the second is reportable, and
    it is the expensive one — the comparison scripts auto-detect ~/smarts/smarts295bat only
    `if not os.environ.get("SMARTSPATH")`, so a wrong non-empty value additionally BLOCKS the
    fallback that would otherwise have rescued the run. Setting the variable incorrectly is
    therefore strictly worse than leaving it unset.

    The dominant real-world mistake is pointing at the containing directory rather than the
    binary (a trailing slash, or `~/smarts`), which is why the directory case names the
    binary the caller probably meant.
    """
    path = os.environ.get("SMARTSPATH")
    if not path:
        return None                                   # unset: a choice, not an error
    if os.path.isdir(path):
        cand = os.path.join(path, SMARTS_BINARY_NAME)
        hint = (f"; did you mean {cand}?" if os.path.isfile(cand)
                else f"; it should name the {SMARTS_BINARY_NAME} binary itself")
        return (f"SMARTSPATH={path!r} is a directory, not the SMARTS executable{hint}")
    if not os.path.exists(path):
        # A trailing slash on an otherwise-correct path is the single most common form of
        # this mistake: POSIX requires "<file>/" to resolve to nothing, so it lands here
        # rather than in the isdir branch and would otherwise report the unhelpful
        # "does not exist" about a binary that is sitting right there.
        stripped = path.rstrip(os.sep)
        if stripped != path and os.path.isfile(stripped) and os.access(stripped, os.X_OK):
            return (f"SMARTSPATH={path!r} has a trailing '{os.sep}', so it names nothing; "
                    f"the binary at {stripped} is correct - drop the trailing separator")
        return (f"SMARTSPATH={path!r} does not exist; it must name the {SMARTS_BINARY_NAME} "
                f"binary (see docs/smarts-build.md)")
    if not os.path.isfile(path):
        return f"SMARTSPATH={path!r} is not a regular file"
    if not os.access(path, os.X_OK):
        return (f"SMARTSPATH={path!r} is not executable; run "
                f"`chmod +x {path}` (the +x bit is commonly lost when the binary is copied)")
    return None


def build_deck(atm, geo, *, aerosol="rural"):
    """Generate a 17-card (18 with aerosol="user", which adds Card 8a) SMARTS 2.9.5 deck (LF-terminated)
    for spectral direct+diffuse, 280-4000nm.

    Solar zenith is given directly (IMASS=0). AOD500 set via TAU5 (ITURB=0). aerosol="rural" (default)
    uses the S&F_RURAL aerosol model, whose Ångström exponent is fixed by the model (NOT settable).
    aerosol="user" instead emits AEROS='USER' + a Card 8a (ALPHA1 ALPHA2 OMEGL GG), making the Ångström
    exponent settable via atm.angstrom_alpha (and the asymmetry factor via atm.aerosol_g).
    """
    if aerosol == "user":
        aero_cards = [
            "'USER'                       !Card 8 AEROS",
            f"{atm.angstrom_alpha} {atm.angstrom_alpha} 0.95 {atm.aerosol_g}   !Card 8a ALPHA1 ALPHA2 OMEGL GG",
        ]
    else:
        aero_cards = ["'S&F_RURAL'                  !Card 8 AEROS"]
    cards = [
        "'HCL_spectral_sky'           !Card 1 COMNT",
        "1                            !Card 2 ISPR=1",
        f"{atm.pressure_mbar} 0.012 0.   !Card 2a SPR ALTIT HEIGHT",
        "1                            !Card 3 IATMOS=1",
        "'USSA'                       !Card 3a ATMOS",
        "0                            !Card 4 IH2O=0",
        f"{atm.pw_cm}                  !Card 4a W (cm)",
        "0                            !Card 5 IO3=0",
        f"0 {atm.ozone_atm_cm}        !Card 5a IALT AbO3 (atm-cm)",
        "1                            !Card 6 IGAS=1",
        "370.0                        !Card 7 qCO2 (ppm)",
        "1                            !Card 7a ISPCTR",
        *aero_cards,
        "0                            !Card 9 ITURB=0",
        f"{atm.aod500}                 !Card 9a TAU5 (AOD@500nm)",
        "-1                           !Card 10 IALBDX=-1",
        f"{atm.albedo}                 !Card 10a RHOX",
        "0                            !Card 10b ITILT=0",
        # SUNCOR = Earth-radius-vector correction D (was 1.0 until 2026-08-17: with IMASS=0
        # SMARTS cannot derive D from a date, so the raw SMARTS spectrum carried no Earth-Sun
        # distance factor while SPECTRL2 did; ~+/-3.4 % scale error at the solstices, review
        # 2026-08-17 B10). SOLARC = 1361 to match the pipeline's clearness normalisation.
        f"280 4000 {getattr(geo, 'earth_radius_vector', 1.0):.6f} 1361.0   !Card 11 WLMN WLMX SUNCOR SOLARC",
        "2                            !Card 12 IPRT=2",
        "280 4000 1.0                 !Card 12a WPMN WPMX INTVL",
        "3                            !Card 12b IOTOT",
        "1 2 3                        !Card 12c IOUT (ET, Direct-normal, Diffuse-horizontal)",
        "0                            !Card 13 ICIRC=0",
        "0                            !Card 14 ISCAN=0",
        "0                            !Card 15 ILLUM=0",
        "0                            !Card 16 IUV=0",
        "0                            !Card 17 IMASS=0",
        f"{geo.zenith_deg} 180.0       !Card 17a ZENIT AZIM",
    ]
    return "\n".join(cards) + "\n"


def parse_ext_output(text):
    """Parse smarts295.ext.txt → (wavelength_nm, direct_normal, diffuse_horizontal). Cols: 0=Wvlgth,
    2=Direct-normal (IOUT 2), 3=Diffuse-horizontal (IOUT 3). Values W/m²/nm."""
    wl, direct, diffuse = [], [], []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        try:
            w = float(parts[0]); dn = float(parts[2]); df = float(parts[3])
        except ValueError:
            continue  # header / non-numeric
        wl.append(w); direct.append(dn); diffuse.append(df)
    return wl, direct, diffuse


class SmartsEngine:
    name = "smarts"
    native_resolution = "smarts_mixed_0.5-1-10nm"   # 280-4000nm: 0.5nm UV / 1nm VIS / ~10nm NIR

    def __init__(self, aerosol="rural"):
        self.aerosol = aerosol

    def compute(self, atm, geo, *, tilt_deg=0.0, cos_incidence=None):
        if not smarts_available():
            why = smarts_misconfigured()
            raise RuntimeError(
                f"SMARTS not available - {why}" if why else
                "SMARTS not available (set SMARTSPATH to the smarts295bat binary)")
        binary = os.environ["SMARTSPATH"]
        data_dir = os.path.dirname(binary)  # SMARTS data tree lives beside the binary
        run_dir = tempfile.mkdtemp(prefix="smarts_")
        try:
            # SMARTS needs its ancillary data reachable; symlink the binary's dir contents in.
            for entry in os.listdir(data_dir):
                src = os.path.join(data_dir, entry)
                dst = os.path.join(run_dir, entry)
                if not os.path.exists(dst):
                    try:
                        os.symlink(src, dst)
                    except OSError:
                        pass
            with open(os.path.join(run_dir, "smarts295.inp.txt"), "w", newline="\n") as fh:
                fh.write(build_deck(atm, geo, aerosol=self.aerosol))
            # One call per timestep: inside a job each can be stopped, so an annual SMARTS
            # run ends when its tool call does instead of working through the year.
            jobcontrol.run([binary], cwd=run_dir, check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
            with open(os.path.join(run_dir, "smarts295.ext.txt")) as fh:
                wl, direct, diffuse = parse_ext_output(fh.read())
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)
        # SMARTS is W/m²/nm; ×1000 → W/m²/µm for engine-uniform units (resampler does ÷1000).
        return ClearSkySpectra(wavelength_nm=wl,
                               direct_normal=[v * 1000.0 for v in direct],
                               sky_diffuse_horizontal=[v * 1000.0 for v in diffuse])
