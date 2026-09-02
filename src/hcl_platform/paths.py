"""Forward-slash path normalization for embedding in Radiance command args / .rad references.

Radiance accepts forward slashes on every platform; a Windows backslash inside a .rad arg is
misparsed as an escape. Used at the user-input seams (geometry/IES paths into oconv/obj2rad/
ies2rad). Only the separator is normalized — relative paths stay relative, so generated work_dir
names (materials/sky) still resolve against cwd=work_dir."""


def rad_path(p):
    """Return the path with backslashes normalized to forward slashes. Idempotent; relative-safe."""
    return p.replace("\\", "/")
