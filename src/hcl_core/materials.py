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


def write_material(channels, *, material_type, channel_type, name,
                   roughness=0.0, specularity=0.0, work_dir):
    """Write Radiance material .rad file(s). material_type 0=glass,1=plastic. Returns {files, channel_output}.

    For glass, channel transmittances are converted to transmissivity first.
    3-channel -> one file; 9-channel -> name_a/_b/_c (b1b2b3 / g1g2g3 / r1r2r3).
    """
    if material_type not in (0, 1):
        raise ValueError("write_material supports material_type 0=glass or 1=plastic in this version")
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
