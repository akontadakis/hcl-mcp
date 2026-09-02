"""Inject a spectral channel triplet into a luminaire .rad (port of Lark 'Colored Electric Luminaire')."""
import os
import re

# The light primitive's real-args line is "...\n0\n0\n3 1 1 1\n". Anchor on the preceding
# "0\n0\n" (string + integer arg counts) so a stray "3 1 1 1" elsewhere in the .rad (polygon
# vertices, a second primitive) is never recolored. \b guards against "3 1 1 10".
_DEFAULT_LIGHT = re.compile(r"(?<=\n0\n0\n)3 1 1 1\b")  # Radiance default light data line

def color_luminaire(rad, channels9, count, in_place=True):
    """Replace `3 1 1 1` in a luminaire definition with the count-th RGB third of a 9-value list.

    rad: a .rad file path (modified in place if in_place) or raw .rad text (returns the new text).
    count: 0=blue (vals 0-2), 1=green (3-5), 2=red (6-8). Returns the resulting text.
    """
    if count not in (0, 1, 2):
        raise ValueError("count must be 0 (blue), 1 (green), or 2 (red)")
    if len(channels9) != 9:
        raise ValueError("channels9 must be 9 values")
    triplet = channels9[count * 3: count * 3 + 3]
    sub = "3 " + " ".join(str(v) for v in triplet)

    is_path = os.path.sep in rad or rad.endswith(".rad")
    if is_path and os.path.isfile(rad):
        with open(rad) as fh:
            text = fh.read()
        new = _DEFAULT_LIGHT.sub(sub, text, count=1)
        if in_place:
            with open(rad, "w") as fh:
                fh.write(new)
        return new
    return _DEFAULT_LIGHT.sub(sub, rad, count=1)  # treat rad as raw text
