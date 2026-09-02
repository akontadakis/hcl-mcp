"""True CIE Standard Overcast Sky (gensky -c) for Daylight Factor. The codebase's colored_sky
only reaches the Perez lowest-epsilon bin, which is NOT the CIE overcast distribution DF is
defined against, so DF uses this dedicated builder."""

_OVERCAST_GLOW = """
skyfunc glow sky_glow
0
0
4 1 1 1 0

sky_glow source sky
0
0
4 0 0 1 180

skyfunc glow ground_glow
0
0
4 1 1 1 0

ground_glow source ground
0
0
4 0 0 -1 180
"""


def build_gensky_overcast(month=6, day=21, hour=12.0, gnd_refl=0.2):
    """gensky CIE Standard Overcast Sky command. -c selects the overcast distribution; the date/
    time only fixes solar geometry for the (sun-free) overcast dome. -g sets ground reflectance."""
    return ["gensky", str(month), str(day), str(hour), "-c", "-g", str(gnd_refl)]


def write_overcast_sky(work_dir, out="overcast_sky.rad", *, month=6, day=21, hour=12.0,
                       gnd_refl=0.2):
    """Return (steps, out): a gensky step (writes the skyfunc head) + an append step that adds
    the sky/ground glow tail, producing a complete sky scene .rad usable in run_grid scene_sets."""
    steps = [
        {"cmd": build_gensky_overcast(month, day, hour, gnd_refl), "stdout": out},
        # Windows-safe: append the glow tail via the write-tuple pseudo-step (no Unix `printf`).
        {"write": (out, _OVERCAST_GLOW), "append": True},
    ]
    return steps, out
