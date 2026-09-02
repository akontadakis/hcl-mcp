"""Spectral-engine registry: resolve a backend name to a SpectralEngine instance.

The single string->instance mapping point for the MCP layer. `native` (gensdaymtx) is deliberately
absent — it has a different output contract (band matrix, not a 1nm record) and its own tool.
"""
from hcl_core.spectral_engine.spectrl2 import Spectrl2Engine

_ENGINES = ("spectrl2", "smarts")


def resolve_engine(name: str = "spectrl2", *, smarts_aerosol=None):
    """Map an engine name to a SpectralEngine instance.

    "spectrl2" (default) is always available and ignores smarts_aerosol. "smarts" requires a runnable
    binary (SMARTSPATH); since the SMARTS gate lives in compute(), not the ctor, we check availability
    here and raise early so the error surfaces at the MCP boundary. smarts_aerosol selects the SMARTS
    Card-8 aerosol model: None/"rural" (default, byte-identical to prior behavior) or "user" (settable
    Ångström α + asymmetry g via Card 8a — see SmartsEngine/build_deck). Unknown names raise ValueError.
    """
    if name == "spectrl2":
        return Spectrl2Engine()
    if name == "smarts":
        from hcl_core.spectral_engine.smarts import (smarts_available, smarts_misconfigured,
                                                     SmartsEngine)
        if not smarts_available():
            # Distinguish "not installed" from "installed but SMARTSPATH is wrong" - the
            # second is a fixable user mistake and the message should say how.
            why = smarts_misconfigured()
            raise RuntimeError(
                f"SMARTS not available - {why}" if why else
                "SMARTS not available (set SMARTSPATH to the smarts295bat binary)")
        return SmartsEngine(aerosol=(smarts_aerosol or "rural"))
    raise ValueError(f"unknown engine {name!r}; choose from {', '.join(_ENGINES)}")
