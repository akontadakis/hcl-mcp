"""Radiance image-path command builders.

The pcomb action-curve maps are a numerically-equivalent SINGLE-PASS refactor of Lark's
multi-pass pcomb chain (Lark uses per-channel temp HDRs + a greyscale-collapse pass; we fold
each map into one combined expression). Same coefficients, same per-pixel result. Output is a
greyscale luminance .hdr per action curve, intended to be viewed in `falsecolor` (as in Lark,
which also does not invoke falsecolor itself). The FOV expressions are verbatim Lark ports.
"""
import shlex

def build_rpict(oct_file, view="-vta -vh 180 -vv 180", x=800, y=800, rad_params="-ab 2 -ad 512 -aa 0.1 -ar 64"):
    """rpict for a fisheye (angular) HDR. Returns args; runner redirects stdout to the .hdr."""
    return ["rpict", *shlex.split(view), "-x", str(x), "-y", str(y), *shlex.split(rad_params), oct_file]

def _pcomb_map(triplet, out, e_b, e_g, e_r):
    """Single-pass pcomb summing 9 channels (3 HDRs x RGB) against one action curve into a greyscale
    luminance map. Numerically equivalent to Lark's per-channel-temp + collapse passes (same result)."""
    b, g, r = triplet
    expr = (f'ro=ri(1)*{e_b[0]}+gi(1)*{e_b[1]}+bi(1)*{e_b[2]}+'
            f'ri(2)*{e_g[0]}+gi(2)*{e_g[1]}+bi(2)*{e_g[2]}+'
            f'ri(3)*{e_r[0]}+gi(3)*{e_r[1]}+bi(3)*{e_r[2]};go=ro;bo=ro')
    return ["pcomb", "-h", "-e", expr, "-o", b, g, r]  # stdout -> out (runner redirects)

# Coefficients (b1,b2,b3),(g1,g2,g3),(r1,r2,r3) — verbatim from Lark 9-channel image path / grid engine.
# Only the multi-pass -> single-pass STRUCTURE is refactored; these literal values are unchanged.
# Stored as EXACT decimal STRINGS so the pcomb expression reads "0.000069431" verbatim — a float
# would render as "6.9431e-05" (still valid for Radiance's calculator, but we match Lark's literals).
_PHOTOPIC = (("0.0003", "0.009098397", "0.055590209"), ("0.164071102", "0.250355905", "0.259754249"),
             ("0.130177072", "0.081085718", "0.049591265"))
_MELANOPIC = (("0.0119", "0.1784", "0.4165"), ("0.268843", "0.1033", "0.019"), ("0.0017", "0.000296", "0.000061"))
_NEUROPIC = (("0.905130569", "0.0948", "0.000069431"), ("0", "0", "0"), ("0", "0", "0"))  # grid value (§9.2)

def pcomb_photopic_map(triplet, out): return _pcomb_map(triplet, out, *_PHOTOPIC)
def pcomb_melanopic_map(triplet, out): return _pcomb_map(triplet, out, *_MELANOPIC)
def pcomb_neuropic_map(triplet, out): return _pcomb_map(triplet, out, *_NEUROPIC)

# ipRGC FOV weights (Khademagha et al. 2018/2016) — region: weight.
_FOV = {"upper_inner": 2.06, "upper_outer": 1.37, "lower_inner": 0.34, "lower_outer": 0.23}

def fov_pcomb_steps(picture, masks, out):
    """Apply regional ipRGC weights via masked pcomb, then sum the 4 masked images. Verbatim Lark FOV logic."""
    region_files = {"upper_inner": ("Temp_ui.hdr", masks["upper_inner"]),
                    "upper_outer": ("Temp_uo.hdr", masks["upper_outer"]),
                    "lower_inner": ("Temp_li.hdr", masks["lower_inner"]),
                    "lower_outer": ("Temp_lo.hdr", masks["lower_outer"])}
    steps = []
    for region, (tmp, mask) in region_files.items():
        w = _FOV[region]
        expr1 = f"thresh=if((ri(2)+bi(2)+gi(2)-0.01),{w},0)"
        expr2 = "ro=thresh*ri(1);go=thresh*gi(1);bo=thresh*bi(1)"
        steps.append({"cmd": ["pcomb", "-h", "-e", expr1, "-e", expr2, "-o", picture, mask], "stdout": tmp})
    tmps = [t for t, _ in region_files.values()]
    total_expr = "ro=ri(1)+ri(2)+ri(3)+ri(4);go=gi(1)+gi(2)+gi(3)+gi(4);bo=bi(1)+bi(2)+bi(3)+bi(4)"
    steps.append({"cmd": ["pcomb", "-h", "-e", total_expr, "-o", *tmps], "stdout": out})
    return steps

def rgb_from_hdr_steps(picture, out):
    """Cosine-weighted RGB irradiance from a fisheye HDR (verbatim Lark pipeline)."""
    dot = "dot=Dx(1)*Vdx+Dy(1)*Vdy+Dz(1)*Vdz"
    ch = "ro=if(dot,S(1)*dot*ri(1),0);go=if(dot,S(1)*dot*gi(1),0);bo=if(dot,S(1)*dot*bi(1),0)"
    return [
        {"cmd": ["vwright", "-vf", picture, "V"], "stdout": "vwr.cal"},
        {"cmd": ["pcomb", "-h", "-f", "vwr.cal", "-e", dot, "-e", ch, "-o", picture,
                 "|", "pvalue", "-h", "-H", "-df", "|", "total", "-if3"], "stdout": out},
    ]
