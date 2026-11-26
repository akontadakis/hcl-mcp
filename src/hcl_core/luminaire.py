"""Inject a spectral channel triplet into a luminaire .rad (port of Lark 'Colored Electric Luminaire')."""
import os
import re

# The light primitive's real-args line is "...\n0\n0\n3 1 1 1\n". Anchor on the preceding
# "0\n0\n" (string + integer arg counts) so a stray "3 1 1 1" elsewhere in the .rad (polygon
# vertices, a second primitive) is never recolored. The lookahead refuses a longer number:
# "3 1 1 10" and "3 1 1 1.0" are not the default line (a bare \b let the second one match up
# to the dot and turned it into "3 0.1 0.2 0.3.0").
_DEFAULT_LIGHT = re.compile(r"(?<=\n0\n0\n)3 1 1 1(?![\d.])")  # Radiance default light data line


def _recolor(text, sub):
    """Replace the default light line, or say why not. Never return the text unchanged: that
    reads as success, and the caller goes on to simulate an uncoloured lamp."""
    normalised = text.replace("\r\n", "\n").replace("\r", "\n")
    new, count = _DEFAULT_LIGHT.subn(sub, normalised, count=1)
    if count == 0:
        raise ValueError(
            "no default light line `3 1 1 1` found after a `0 / 0` argument pair, so there is "
            "nothing to colour. The luminaire .rad must define its `light` with the Radiance "
            "default radiance 1 1 1 (ies2rad writes that unless given -m / -c).")
    return new


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
        new = _recolor(text, sub)
        if in_place:
            with open(rad, "w") as fh:
                fh.write(new)
        return new
    return _recolor(rad, sub)  # treat rad as raw text
