import os
import pytest
from hcl_core.spectral_engine import resolve_engine
from hcl_core.spectral_engine.base import SpectralEngine
from hcl_core.spectral_engine.spectrl2 import Spectrl2Engine
from hcl_core.spectral_engine.smarts import smarts_available


def test_default_is_spectrl2():
    eng = resolve_engine()
    assert isinstance(eng, Spectrl2Engine)
    assert eng.name == "spectrl2"
    assert isinstance(eng, SpectralEngine)


def test_explicit_spectrl2():
    assert resolve_engine("spectrl2").name == "spectrl2"


def test_unknown_engine_raises_valueerror():
    with pytest.raises(ValueError) as e:
        resolve_engine("bogus")
    assert "bogus" in str(e.value)
    assert "spectrl2" in str(e.value)  # message lists valid choices


def test_smarts_without_binary_raises_runtimeerror(monkeypatch):
    monkeypatch.delenv("SMARTSPATH", raising=False)
    assert not smarts_available()
    with pytest.raises(RuntimeError) as e:
        resolve_engine("smarts")
    assert "SMARTS" in str(e.value)


@pytest.mark.skipif(not smarts_available(), reason="SMARTS binary not present (SMARTSPATH unset)")
def test_smarts_with_binary_resolves():
    from hcl_core.spectral_engine.smarts import SmartsEngine
    assert isinstance(resolve_engine("smarts"), SmartsEngine)
