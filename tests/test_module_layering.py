"""The package's dependency direction is a documented claim; assert it here.

`hcl_core` is the pure-Python science layer: it may import `hcl_platform` (the
stdlib-only compat base) and nothing else in the package. The engine adapters sit
above it and the server layer above them. A new upward import is an architecture
regression rather than a style nit, so it fails the suite instead of a linter.

The one deliberate lateral edge is `hcl_radiance` -> `hcl_daysim`: the annual nvRD
pass borrows Daysim's sub-hourly `.wea` generator. It is allowed here and drawn in
the paper's module figure; the reverse direction is not.
"""
import ast
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"

PACKAGES = ("hcl_core", "hcl_daysim", "hcl_radiance", "hcl_mcp", "hcl_platform")

# package -> the sibling packages it is allowed to import
ALLOWED = {
    "hcl_platform": set(),
    "hcl_core": {"hcl_platform"},
    "hcl_daysim": {"hcl_core", "hcl_platform"},
    "hcl_radiance": {"hcl_core", "hcl_daysim", "hcl_platform"},
    "hcl_mcp": {"hcl_core", "hcl_daysim", "hcl_radiance", "hcl_platform"},
}


def _imported_packages(path):
    """Every hcl_* package ``path`` imports, at module level or inside a function."""
    tree = ast.parse(path.read_text(), filename=str(path))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            # level > 0 is a relative import: same package by construction
            names = [node.module] if (node.module and not node.level) else []
        else:
            continue
        for name in names:
            head = name.split(".")[0]
            if head in PACKAGES:
                found.add(head)
    return found


def test_every_package_is_present():
    for pkg in PACKAGES:
        assert (SRC / pkg).is_dir(), f"{pkg} missing from {SRC}"


def test_no_module_imports_above_its_layer():
    violations = []
    for pkg in PACKAGES:
        allowed = ALLOWED[pkg] | {pkg}
        for path in sorted((SRC / pkg).rglob("*.py")):
            for imported in sorted(_imported_packages(path) - allowed):
                violations.append(f"{path.relative_to(SRC)} imports {imported}")
    assert not violations, "upward/disallowed imports:\n  " + "\n  ".join(violations)


def test_epw_location_parser_lives_in_the_core_layer():
    """The canonical home is hcl_core; hcl_daysim re-exports the same object."""
    from hcl_core.epw_location import parse_epw_location as core_fn
    from hcl_daysim.epw import parse_epw_location as daysim_fn

    assert daysim_fn is core_fn
