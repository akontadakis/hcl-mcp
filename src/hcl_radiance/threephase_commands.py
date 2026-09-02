"""Three-phase (V.T.D.s) command builders.

Pure functions returning argv lists, same contract as annual_commands.py: the runner
handles stdin/stdout redirection.

We use `rfluxmtx` rather than `rcontrib` + `genklemsamp`. The LBNL tutorials teach the
rcontrib route, but their own guidance recommends rfluxmtx for new work, and it removes
the two commonest causes of a silently-wrong matrix: the `genklemsamp -c` / `rcontrib -c`
sample-count mismatch, and manual `kbin` orientation bookkeeping.
"""
import shlex

#: V wants high ambient accuracy -- it carries every interreflection in the room.
DEFAULT_V_PARAMS = "-ab 12 -ad 50000 -lw 2e-5"
#: D is cheap: the window mostly sees sky. -c averages 1000 samples per Klems bin.
DEFAULT_D_PARAMS = "-c 1000 -ab 2 -ad 1024"

_SKY_RECEIVER = """#@rfluxmtx h=u u=+Z
void glow groundglow
0
0
4 1 1 1 0

groundglow source ground
0
0
4 0 0 -1 180

#@rfluxmtx h=r{mf} u=+Z
void glow skyglow
0
0
4 1 1 1 0

skyglow source skydome
0
0
4 0 0 1 180
"""


def sky_receiver_rad(mf=4):
    """Reinhart sky receiver for D. MF:4 = 2305 sky patches + 1 ground = 2306 bins.

    2.3.2 states the patch count conditionally ("should ... if daylight coefficients
    and/or discrete sky patches are applied"); the binding requirement is 2.3.1's 5 deg
    solar-position accuracy, from which 2305 is derived.

    The `h=u` groundglow MUST come first and is not optional. gendaymtx emits 2306 rows
    (2305 sky + 1 ground); a receiver carrying only the sky dome yields a D matrix of
    2305 columns and dctimestep fails with "unexpected column count in header". This is
    the same two-part shape `annual_commands.skyglow_rad` already uses for the 2-phase
    path. Live-verified.
    """
    return _SKY_RECEIVER.format(mf=int(mf))


def build_gendaymtx_sky_mf(wea, sky_color, mf=4):
    """Coloured sky matrix at a CHOSEN Reinhart subdivision.

    annual_commands.build_gendaymtx_sky hardcodes `-m 1` (145 patches), which is right
    for the 2-phase path but fatal here: the D matrix is built against an `h=r{mf}`
    receiver, so a 145-row sky vector cannot multiply a 2305-column D. dctimestep would
    reject the shapes or, worse, mis-multiply them. The subdivision MUST match whatever
    `sky_receiver_rad` was given.
    """
    r, g, b = sky_color
    return ["gendaymtx", "-m", str(int(mf)), "-s", "-c", str(r), str(g), str(b), wea]


def build_rfluxmtx_view(n_points, rad_params, receiver_rad, oct_file):
    """V: sensors -> window. Sender is stdin (the points), receiver is the window glow."""
    return ["rfluxmtx", "-I+", "-y", str(n_points), *shlex.split(rad_params),
            "-", receiver_rad, "-i", oct_file]


def build_rfluxmtx_daylight(rad_params, sender_rad, sky_receiver, oct_file):
    """D: window -> sky. The window is the sender, the sky dome the receiver."""
    return ["rfluxmtx", *shlex.split(rad_params), sender_rad, sky_receiver, "-i", oct_file]


def build_dctimestep_3ph(v_mtx, t_xml, d_mtx, sky_mtx):
    """The four-argument dctimestep: I = V . T . D . s."""
    return ["dctimestep", v_mtx, t_xml, d_mtx, sky_mtx]


def build_rmtxop_photopic():
    """Collapse piped RGB to photopic lux: 179 lm/W times the CIE weights.

    Reads the matrix from stdin (the trailing "-"), so this is the right-hand side of a
    pipe from dctimestep. `-fa` forces ASCII out so parse_lux_matrix can read it.
    """
    return ["rmtxop", "-fa", "-c", "47.4", "119.9", "11.6", "-"]


def build_rmtxop_sum(paths):
    """Add per-window-group illuminance matrices into one.

    Each window group contributes independently to every sensor, so the group matrices
    must be SUMMED, not concatenated or overwritten.
    """
    if not paths:
        raise ValueError("build_rmtxop_sum needs at least one matrix")
    cmd = ["rmtxop", "-fa", paths[0]]
    for p in paths[1:]:
        cmd += ["+", p]
    return cmd
