import asyncio
import pytest
from hcl_mcp import clientfeatures
from hcl_mcp.clientfeatures import resolve_work_dir, elicit_value, record_client_caps

@pytest.fixture(autouse=True)
def _restore_client_caps():
    snapshot = dict(clientfeatures.CLIENT_CAPS)
    yield
    clientfeatures.CLIENT_CAPS.clear()
    clientfeatures.CLIENT_CAPS.update(snapshot)

class FakeRoot:
    def __init__(self, uri): self.uri = uri

class FakeCtx:
    def __init__(self, roots=None, elicit_data=None, fail=False, caps=None):
        self._roots = roots or []; self._ed = elicit_data; self._fail = fail; self._caps = caps
    async def list_roots(self):
        if self._fail: raise RuntimeError("unsupported")
        return self._roots
    async def elicit(self, message, response_type=None):
        if self._fail: raise RuntimeError("unsupported")
        class Accepted: data = self._ed
        return Accepted()

def test_resolve_explicit_wins(monkeypatch):
    monkeypatch.setenv("HCL_WORK_ROOT", "/env")
    assert asyncio.run(resolve_work_dir(FakeCtx(), explicit="/x")) == "/x"

def test_resolve_env_over_root(monkeypatch):
    monkeypatch.setenv("HCL_WORK_ROOT", "/env")
    assert asyncio.run(resolve_work_dir(FakeCtx([FakeRoot("file:///proj")]))) == "/env"

def test_resolve_root_when_no_env(monkeypatch):
    monkeypatch.delenv("HCL_WORK_ROOT", raising=False)
    assert asyncio.run(resolve_work_dir(FakeCtx([FakeRoot("file:///proj")]))) == "/proj/hcl_work"

def test_resolve_default_when_nothing(monkeypatch):
    monkeypatch.delenv("HCL_WORK_ROOT", raising=False)
    assert asyncio.run(resolve_work_dir(None)).endswith("hcl_work")

def test_elicit_none_without_ctx():
    assert asyncio.run(elicit_value(None, "m", str)) is None

def test_elicit_returns_data():
    assert asyncio.run(elicit_value(FakeCtx(elicit_data=42), "m", int)) == 42

def test_elicit_swallows_unsupported():
    assert asyncio.run(elicit_value(FakeCtx(fail=True), "m", str)) is None

# --- Capability recording at init (spec 3.2/7.5) ---

def test_record_client_caps_shape():
    caps = record_client_caps(None)
    assert set(caps) == {"roots", "elicitation", "sampling"}
    assert all(isinstance(v, bool) for v in caps.values())

def test_record_client_caps_none_ctx_all_false():
    assert record_client_caps(None) == {"roots": False, "elicitation": False, "sampling": False}

def test_record_client_caps_reads_handshake():
    # A ctx exposing the initialize handshake client capabilities.
    class Caps: roots = object(); elicitation = object(); sampling = None
    class Sess:
        client_params = type("P", (), {"capabilities": Caps()})()
    ctx = FakeCtx()
    ctx.session = Sess()
    caps = record_client_caps(ctx)
    assert caps["roots"] is True and caps["elicitation"] is True and caps["sampling"] is False

def test_record_client_caps_mutates_global():
    class Caps: roots = object(); elicitation = None; sampling = object()
    class Sess:
        client_params = type("P", (), {"capabilities": Caps()})()
    ctx = FakeCtx()
    ctx.session = Sess()
    record_client_caps(ctx)
    assert clientfeatures.CLIENT_CAPS == {"roots": True, "elicitation": False, "sampling": True}
    # the autouse fixture restores CLIENT_CAPS afterward, preventing cross-test bleed
