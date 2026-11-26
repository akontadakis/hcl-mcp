"""The declared FastMCP range must admit only releases the server is known to import on.

`uvx --from git+...` resolves from pyproject.toml, never from uv.lock, so the declared range IS
what a public user installs. An open-ended range once shipped a FastMCP major that removed a hook
the server used, and the public install crashed on import (2026-11-26).

The server now needs the 4.x line: `FastMCP.completion`, the returned-question guard
(`InputRequiredResult`) and the protocol-version table all arrive with it, so 3.x cannot import
this code (checked: ImportError on fastmcp 3.4.2). Nothing is known about 5.x, so it stays out until someone runs the suite on it.
"""
import pathlib
import tomllib

import pytest
from packaging.requirements import Requirement


def _declared_fastmcp_range():
    pyproject = pathlib.Path(__file__).resolve().parents[1] / "pyproject.toml"
    declared = tomllib.loads(pyproject.read_text())["project"]["dependencies"]
    (requirement,) = [r for r in map(Requirement, declared) if r.name == "fastmcp"]
    return requirement.specifier


@pytest.mark.parametrize("release, admitted, why", [
    ("3.4.11", False, "last 3.x: its MCP SDK has no InputRequiredResult, server cannot import"),
    ("4.2.6", True, "the release the suite was run on"),
    ("5.0.0", False, "next major: unverified"),
])
def test_the_declared_fastmcp_range_matches_what_was_verified(release, admitted, why):
    assert _declared_fastmcp_range().contains(release) is admitted, why
