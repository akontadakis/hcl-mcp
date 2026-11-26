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
