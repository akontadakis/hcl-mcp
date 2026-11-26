"""Where a file-writing tool puts its output: explicit arg > HCL_WORK_ROOT > ~/hcl_work.

The client's "roots" used to sit between the last two. MCP 2026-07-28 deprecates Roots and
removes the server-initiated request that fetched them, so a rule that consulted roots would put
the same call's output in a different folder depending on which protocol revision the client
speaks. The location is decided by the caller and the server's own configuration only.
"""
import asyncio
import os

from hcl_mcp.clientfeatures import resolve_work_dir


class RootOfferingCtx:
    """A client context that would still answer the retired roots request."""

    async def list_roots(self):
        return [type("Root", (), {"uri": "file:///proj"})()]


def test_resolve_explicit_wins(monkeypatch):
    monkeypatch.setenv("HCL_WORK_ROOT", "/env")
    assert asyncio.run(resolve_work_dir(RootOfferingCtx(), explicit="/x")) == "/x"


def test_resolve_env_when_no_explicit(monkeypatch):
    monkeypatch.setenv("HCL_WORK_ROOT", "/env")
    assert asyncio.run(resolve_work_dir(RootOfferingCtx())) == "/env"


def test_a_client_root_does_not_move_the_default_work_dir(monkeypatch):
    monkeypatch.delenv("HCL_WORK_ROOT", raising=False)
    assert asyncio.run(resolve_work_dir(RootOfferingCtx())) == os.path.expanduser("~/hcl_work")


def test_resolve_default_without_a_client(monkeypatch):
    monkeypatch.delenv("HCL_WORK_ROOT", raising=False)
    assert asyncio.run(resolve_work_dir(None)) == os.path.expanduser("~/hcl_work")
