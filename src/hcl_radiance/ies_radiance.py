"""Radiance electric-light command builders: ies2rad + xform placement + evalglare.

Pure functions returning argv lists (string-tested, no Radiance), in the Plan 3 style.
CRITICAL: ies2rad -m carries USER scaling only (multiplier * maintenance_factor). The IES
candela_multiplier / ballast_factor / pfactor are applied by ies2rad itself
(sinf->mult = -m * mult * bfactor * pfactor); folding them into -m would square them.
"""

import shlex

from hcl_platform import rad_path

_UNITS_LETTER = {1: "f", 2: "m"}  # 1=feet, 2=meters


def build_ies2rad(ies_path, *, multiplier=1.0, maintenance_factor=1.0, color=None,
                  lamp=None, units=None, units_divisor=None, out_prefix=None, inline=False):
    """Emit an ies2rad argv (or an inline '!ies2rad ...' string if inline=True).

    -m = multiplier * maintenance_factor  (user/maintenance scaling ONLY).
    color = [R,G,B] -> -c R G B ; lamp -> -t <lamp> ; units 1->-df, 2->-dm (+ optional /divisor).
    out_prefix -> -o <prefix>.
    """
    m = multiplier * maintenance_factor
    argv = ["ies2rad", "-m", _fmt(m)]
    if color is not None:
        argv += ["-c", _fmt(color[0]), _fmt(color[1]), _fmt(color[2])]
    if lamp is not None:
        argv += ["-t", lamp]
    if units is not None:
        letter = _UNITS_LETTER.get(units)
        if letter is None:
            raise ValueError("units must be 1 (feet) or 2 (meters)")
        flag = f"-d{letter}"
        if units_divisor is not None:
            flag += f"/{units_divisor}"
        argv.append(flag)
    if out_prefix is not None:
        argv += ["-o", out_prefix]
    argv.append(rad_path(ies_path))  # forward-slash user IES path (Windows-safe)
    if inline:
        return "!" + " ".join(argv)
    return argv


def _fmt(x):
    """Format a number without trailing-zero noise (1.6 not 1.6000000000000001)."""
    s = f"{float(x):.10g}"
    return s


def _instance_line(name, xyz, rot):
    """One inline-xform line: rotation (Y-up->Z-up remap) BEFORE translation.

    Emitted with a leading '!' so the line is a Radiance inline command: oconv/rpict (and xform)
    expand '!xform ... obj.rad' by running it and reading its stdout. A bare 'xform ...' line is
    NOT valid scene input (oconv reports `undefined modifier "xform"`).
    """
    rx = rot[0]            # rotX = rx
    ry = rot[2]            # rotY = rz   (remap)
    rz = -rot[1]           # rotZ = -ry  (remap)
    return (f"!xform -rx {_fmt(rx)} -ry {_fmt(ry)} -rz {_fmt(rz)} "
            f"-t {_fmt(xyz[0])} {_fmt(xyz[1])} {_fmt(xyz[2])} {name}")


def place_luminaires(name, placement):
    """Return a .rad xform block placing `name` per instance.

    placement is either {"positions": [{"xyz":[x,y,z], "rot":[rx,ry,rz]?}, ...]}
    or {"grid": {"rows","cols","row_spacing","col_spacing","origin":[x,y,z],"rot":[..]?}}.
    Rotation precedes translation in every emitted line.

    LIMITATION: the Y-up->Z-up convention is applied by REMAPPING the Euler angles
    (rotX=rx, rotY=rz, rotZ=-ry). That equals the correct axis change only for SINGLE-axis
    rotations (one non-zero component) — the overwhelmingly common case (a down-pointing fixture
    with one tilt). For compound 3-axis orientations the remapped-angle aim diverges from the true
    conjugated rotation; if you need arbitrary 3-axis aiming, pre-orient the luminaire .rad instead.
    """
    lines = []
    if "positions" in placement:
        for inst in placement["positions"]:
            rot = inst.get("rot", [0, 0, 0])
            lines.append(_instance_line(name, inst["xyz"], rot))
    elif "grid" in placement:
        g = placement["grid"]
        ox, oy, oz = g.get("origin", [0, 0, 0])
        rot = g.get("rot", [0, 0, 0])
        for r in range(g["rows"]):
            for c in range(g["cols"]):
                xyz = [ox + c * g["col_spacing"], oy + r * g["row_spacing"], oz]
                lines.append(_instance_line(name, xyz, rot))
    else:
        raise ValueError("placement must provide 'positions' or 'grid'")
    return "\n".join(lines) + "\n"


def build_evalglare(hdr, *, params=None, detailed=True):
    """evalglare on a fisheye HDR. -d prints the detailed summary line we parse.

    params: extra evalglare args (e.g. view overrides) inserted before the HDR path.
    """
    argv = ["evalglare"]
    if detailed:
        argv.append("-d")
    if params:
        argv += shlex.split(params)
    argv.append(hdr)
    return argv


def parse_evalglare(stdout):
    """Parse evalglare -d stdout -> {UGR, DGP, glare_sources:[{index, values}]}.

    The detailed summary line is '<comma-separated field names>: <space-separated values>' in the
    SAME order, e.g. real evalglare emits
        'dgp,av_lum,E_v,lum_backg,E_v_dir,dgi,ugr,vcp,...: 0.33 274.4 1157 ... 31.7 ...'
    so UGR is NOT at a fixed column (this build emits it 7th). We map field-name -> value index
    rather than assume a position; assuming `ugr = column 1` silently returns av_lum (the
    "UGR=274" bug). Glare-source rows precede the summary: a leading integer index followed by
    numeric columns; the 'N No pixels x-pos ...' text label row is skipped (its 2nd token is
    non-numeric). The legacy '<index>: <vals>' colon form is also accepted.
    """
    dgp = ugr = None
    sources = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        header, sep, rest = line.partition(":")
        if sep and "dgp" in header.lower() and "ugr" in header.lower():
            # Summary line: align comma-separated field names to space-separated values by index.
            fields = [f.strip().lower() for f in header.split(",")]
            vals = rest.split()

            def _field(name):
                if name in fields:
                    idx = fields.index(name)
                    if idx < len(vals) and _is_num(vals[idx]):
                        return float(vals[idx])
                return None

            dgp = _field("dgp")
            ugr = _field("ugr")
            continue
        # Legacy colon source row: "<index>: <vals>".
        if sep and header.strip().isdigit():
            vals = [float(t) for t in rest.split() if _is_num(t)]
            if vals:
                sources.append({"index": int(header.strip()), "values": vals})
            continue
        # Real evalglare source-data row: "<idx> <num> <num> ..." (skip the label row whose 2nd
        # token is non-numeric, e.g. 'N No pixels x-pos ...').
        toks = line.split()
        if len(toks) >= 3 and toks[0].lstrip("-").isdigit() and _is_num(toks[1]):
            sources.append({"index": int(toks[0]),
                            "values": [float(t) for t in toks[1:] if _is_num(t)]})
    return {"UGR": ugr, "DGP": dgp, "glare_sources": sources}


def _is_num(t):
    try:
        float(t)
        return True
    except ValueError:
        return False
