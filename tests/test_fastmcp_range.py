"""The declared FastMCP range must not admit a release the server cannot import on.

`uvx --from git+...` resolves from pyproject.toml, never from uv.lock, so the declared range IS
what a public user installs. With an open-ended range that became FastMCP 4.2.6, which removed
the low-level hook `resources.register_resources` relies on (`mcp._mcp_server.completion`), and
the server crashed on import (2026-11-26).

Lift the bound only in the same change that ports `register_resources` to the public
`FastMCP.completion` decorator.
"""
import pathlib
import tomllib

from packaging.requirements import Requirement


def _declared_fastmcp_requirement():
    pyproject = pathlib.Path(__file__).resolve().parents[1] / "pyproject.toml"
    declared = tomllib.loads(pyproject.read_text())["project"]["dependencies"]
    (requirement,) = [r for r in map(Requirement, declared) if r.name == "fastmcp"]
    return requirement


def test_the_declared_fastmcp_range_excludes_the_release_that_crashes_on_import():
    assert not _declared_fastmcp_requirement().specifier.contains("4.2.6")
