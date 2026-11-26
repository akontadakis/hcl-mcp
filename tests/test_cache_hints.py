"""Clients are told that the server's lists and reference texts may be cached.

MCP 2026-07-28 lets a result carry `ttlMs` and `cacheScope`. Everything this server lists is
fixed for the life of the process (the tool list alone is ~19 k tokens), and none of it is
specific to a user, so a client that honours the hint can stop re-fetching it. The hint only
exists on the new protocol; a handshake-era client simply never sees it.
"""
import asyncio

import pytest
from fastmcp import Client

from hcl_mcp.server import mcp

ONE_HOUR_MS = 3_600_000


def _list(method):
    async def call():
        async with Client(mcp, mode="auto") as client:
            return await getattr(client, method)()

    return asyncio.run(call())


@pytest.mark.parametrize("method", ["list_tools_mcp", "list_resources_mcp",
                                    "list_resource_templates_mcp", "list_prompts_mcp"])
def test_every_list_is_marked_cacheable_for_an_hour_by_anyone(method):
    result = _list(method)
    assert (result.ttl_ms, result.cache_scope) == (ONE_HOUR_MS, "public")
