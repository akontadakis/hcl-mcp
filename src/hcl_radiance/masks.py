"""ipRGC FOV masks. Faithful path = the four shipped Khademagha .hdr masks; synthesis is approximate."""
import os

_MASK_NAMES = {"upper_inner": "1_upper_inner.hdr", "lower_inner": "2_lower_inner.hdr",
               "upper_outer": "3_upper_outer.hdr", "lower_outer": "4_lower_outer.hdr"}

def fov_mask_paths(mask_dir):
    """Expected absolute paths of the four FOV masks in mask_dir (standard FOV-mask naming)."""
    return {region: os.path.join(mask_dir, fname) for region, fname in _MASK_NAMES.items()}

def masks_present(mask_dir):
    """True iff all four mask files exist."""
    return all(os.path.isfile(p) for p in fov_mask_paths(mask_dir).values())

def mask_resize_steps(masks, x, y):
    """Resample each FOV mask to (x, y) pixels via pfilt, returning (steps, resized_paths).

    Mirrors Lark's FOV component, which pfilt-resizes the shipped 512px Khademagha masks to the
    render resolution -- a pcomb mask/picture resolution mismatch errors otherwise. `masks` is a
    region->path dict (from fov_mask_paths); resized masks are written into the work dir under
    deterministic names and the returned dict maps region->resized filename.
    """
    out_steps = []
    resized = {}
    for region, src in masks.items():
        dst = f"mask_{region}.hdr"
        out_steps.append({"cmd": ["pfilt", "-1", "-x", str(x), "-y", str(y), src], "stdout": dst})
        resized[region] = dst
    return out_steps, resized

def synthesize_fov_masks_steps(resolution, mask_dir, inner_deg=30.0):
    """APPROXIMATE mask generation: upper/lower split at the horizontal meridian, inner/outer at
    `inner_deg` eccentricity in an angular fisheye. Returns (radiance_steps, note).

    NOT a substitute for the validated Khademagha masks — those should be supplied when available.
    """
    paths = fov_mask_paths(mask_dir)
    r = resolution
    # pcomb generates each mask from pixel angular position: x,y in [0,1]; ecc from center; hemisphere by y.
    region_expr = {
        "upper_inner": f"ro=if(and(yp-0.5,{_ecc(r)}),1,0);go=ro;bo=ro",
        "lower_inner": f"ro=if(and(0.5-yp,{_ecc(r)}),1,0);go=ro;bo=ro",
        "upper_outer": f"ro=if(and(yp-0.5,-({_ecc(r)})),1,0);go=ro;bo=ro",
        "lower_outer": f"ro=if(and(0.5-yp,-({_ecc(r)})),1,0);go=ro;bo=ro",
    }
    steps = []
    for region, expr in region_expr.items():
        steps.append({"cmd": ["pcomb", "-x", str(r), "-y", str(r), "-e",
                              f"xp=x/{r};yp=y/{r};and(a,b)=if(a,b,-1);{expr}"], "stdout": paths[region]})
    note = (f"APPROXIMATE FOV masks generated (upper/lower at meridian; inner/outer at {inner_deg} deg). "
            "Replace with the validated Khademagha masks for publication-grade results.")
    return steps, note

def _ecc(r):
    """Eccentricity boolean fragment: inside the inner cone (centered fisheye)."""
    return f"(0.09 - ((x/{r}-0.5)*(x/{r}-0.5)+(y/{r}-0.5)*(y/{r}-0.5)))"  # ~30deg of a 180deg fisheye
