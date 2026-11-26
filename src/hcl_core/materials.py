"""Channel values -> Radiance materials. Port of Lark 'Convert SPD' (lines 209-302)."""
import math
import os

def glass_transmissivity(Tn):
    """Transmittance Tn -> Radiance transmissivity. Accepts a float or a list."""
    if isinstance(Tn, (list, tuple)):
        return [glass_transmissivity(t) for t in Tn]
    if Tn == 0:
        return 0.0
    return round(
        (math.sqrt(0.8402528435 + 0.0072522239 * (Tn * Tn)) - 0.9166530661)
        / (0.003626119 * Tn),
        3,
    )


_TYPE_NAME = {0: "glass", 1: "plastic"}


def _primitive(modifier, mtype, name, vals, specularity, roughness):
    head = f"{modifier} {mtype} {name}\n0\n0\n"
    if mtype == "glass":
        return head + "3 %s %s %s" % tuple(vals)
    return head + "5 %s %s %s %s %s" % (vals[0], vals[1], vals[2], specularity, roughness)


#: Characters a name may not hold. `/` and `\\` would let it choose a folder; `"` and `;`
#: break the obj2rad map line the name is written into (`mat (Material "name") ;` -- measured:
#: `a;b` comes out as modifier `b`); the rest mean something to the shell that Radiance hands a
#: `!command` line to. Brackets, and `!` or `#` inside a name, convert correctly and are allowed.
_UNSAFE_IN_A_NAME = '/\\"\';$`<>|&*?'
#: Device names Windows will not store as files, with or without an extension.
_WINDOWS_DEVICES = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                    *(f"LPT{i}" for i in range(1, 10))}


def require_safe_name(name, what="material", windows=None, allow_blank=False):
    """Return `name`, or raise ValueError if it cannot be used as a file stem and identifier.

    Names reach the server from a model file (`usemtl`, `g`) and from callers, and become
    `<work_dir>/<name>.rad` plus an identifier inside Radiance files. `usemtl ../../x` used to
    write outside the work folder. Refused everywhere: an empty name, `.` and `..`; a leading
    `-` (read as an option by the next program), `!` or `#` (a command or a comment at the head
    of a Radiance line); anything with a path separator, a control character, or one of
    ``" ' ; $ ` < > | & * ?``; and a blank, unless `allow_blank` (a name that is only a file
    name, not also an identifier). Refused on Windows as well (`windows`, default: the running
    platform): a `:` (on NTFS `wall:1.rad` is a hidden stream of a file called `wall`), a
    trailing `.` or blank, and the device names CON, NUL, COM1 ...
    """
    text = str(name)
    on_windows = os.name == "nt" if windows is None else windows
    bad = sorted({c for c in text
                  if c in _UNSAFE_IN_A_NAME or ord(c) < 32
                  or (c.isspace() and not (allow_blank and c == " "))})
    why = None
    if not text.strip() or text in (".", ".."):
        why = "it is empty or a folder reference"
    elif bad:
        why = f"it holds {', '.join(repr(c) for c in bad)}"
    elif text[0] in "-!#":
        why = (f"it starts with {text[0]!r}, which the next program reads as an option, a "
               "command or a comment")
    elif on_windows and (":" in text or text[-1] in ". "
                         or text.split(".")[0].upper() in _WINDOWS_DEVICES):
        why = "Windows cannot store a file of that name (a `:`, a trailing `.`, or a device name)"
    if why:
        raise ValueError(
            f"{what} name {text!r} cannot be used: {why}. The name becomes a file name and a "
            "Radiance identifier; use letters, digits, `_`, `-` and `.` and rename it in the "
            "model file.")
    return text


def write_material(channels, *, material_type, channel_type, name,
                   roughness=0.0, specularity=0.0, work_dir):
    """Write Radiance material .rad file(s). material_type 0=glass,1=plastic. Returns {files, channel_output}.

    For glass, channel transmittances are converted to transmissivity first.
    3-channel -> one file; 9-channel -> name_a/_b/_c (b1b2b3 / g1g2g3 / r1r2r3).
    """
    if material_type not in (0, 1):
        raise ValueError("write_material supports material_type 0=glass or 1=plastic in this version")
    require_safe_name(name, "material")
    vals = glass_transmissivity(channels) if material_type == 0 else list(channels)
    mtype = _TYPE_NAME[material_type]
    os.makedirs(work_dir, exist_ok=True)
    files = []

    def _write(suffix, triplet):
        path = os.path.join(work_dir, f"{name}{suffix}.rad")
        with open(path, "w") as fh:
            fh.write(_primitive("void", mtype, f"{name}{suffix}", triplet, specularity, roughness))
        files.append(path)

    if channel_type == 0:
        _write("", vals[:3])
    else:
        _write("_a", vals[0:3])
        _write("_b", vals[3:6])
        _write("_c", vals[6:9])
    return {"files": files, "channel_output": vals}
