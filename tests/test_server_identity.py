"""The server tells a client who it is: hcl-mcp at the project's version.

Left unset, FastMCP fills in its OWN version, so a client's "about this server" line and any
bug report built from it named the framework release instead of the hcl-mcp release.
"""
import asyncio
import pathlib
import tomllib

from fastmcp import Client

from hcl_mcp.server import mcp


def _project_version():
    pyproject = pathlib.Path(__file__).resolve().parents[1] / "pyproject.toml"
    return tomllib.loads(pyproject.read_text())["project"]["version"]


def test_a_client_is_told_the_hcl_mcp_version_not_the_framework_version():
    async def identify():
        async with Client(mcp) as client:
            return client.server_info

    info = asyncio.run(identify())
    assert (info.name, info.version) == ("hcl-mcp", _project_version())


def test_the_version_is_written_the_same_in_every_place_that_states_it():
    """A release changes five files. One left behind gives a plugin, a lock file or a README
    that names a different release from the code. A paper cites this number."""
    import json
    import re

    import hcl_mcp

    root = pathlib.Path(__file__).resolve().parents[1]
    version = _project_version()
    assert hcl_mcp.__version__ == version
    assert json.loads((root / ".claude-plugin" / "plugin.json").read_text())["version"] == version
    readme = (root / "README.md").read_text(encoding="utf-8")
    assert re.search(r"\*\*Version\*\* (\S+)", readme).group(1) == version
    lock = (root / "uv.lock").read_text(encoding="utf-8")
    locked = re.search(r'\[\[package\]\]\nname = "hcl-mcp"\nversion = "([^"]+)"', lock)
    assert locked and locked.group(1) == version
    install = (root / "INSTALL.md").read_text(encoding="utf-8")
    assert f"@v{version}" in install          # the pin example names a tag that exists
