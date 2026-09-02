"""Client-feature helpers (roots, elicitation). Everything degrades gracefully.

Capability recording (spec 3.2/7.5): record_client_caps(ctx) reads the MCP initialize handshake
(via the FastMCP context/session) into a {roots, elicitation, sampling} bool dict. The server records
this once at init (see server.py) and stores it as CLIENT_CAPS, an explicit, inspectable record of
the negotiated client capabilities. The roots/elicitation helpers attempt their ctx round-trip
whenever a ctx is present and rely on try/except for graceful degradation (rather than blocking on
the recorded CLIENT_CAPS), so they stay correct regardless of what was recorded. Sampling is recorded
for completeness but is not used by any tool in this plan.
"""
import os
from urllib.parse import urlparse

# Populated once at server init by record_client_caps(ctx). Default: assume nothing until recorded.
CLIENT_CAPS = {"roots": False, "elicitation": False, "sampling": False}

def record_client_caps(ctx):
    """Derive {roots, elicitation, sampling} client support from the MCP initialize handshake.

    Returns a dict of bools. With no ctx (or no recorded handshake) everything is False. The result
    is also written to the module-level CLIENT_CAPS so gated helpers can consult it without a ctx.
    Sampling is recorded for completeness but is not used by any tool in this plan.
    """
    caps = {"roots": False, "elicitation": False, "sampling": False}
    try:
        # FastMCP exposes the negotiated client capabilities from the initialize handshake.
        client_caps = ctx.session.client_params.capabilities  # may raise if unsupported/None
        caps["roots"] = getattr(client_caps, "roots", None) is not None
        caps["elicitation"] = getattr(client_caps, "elicitation", None) is not None
        caps["sampling"] = getattr(client_caps, "sampling", None) is not None
    except Exception:
        pass  # no handshake info available -> leave all False
    CLIENT_CAPS.update(caps)
    return caps

def _uri_to_path(uri):
    s = str(uri)
    if s.startswith("file://"):
        return urlparse(s).path
    return s

async def resolve_work_dir(ctx, explicit=None):
    """Pick the output dir. Precedence: explicit arg > HCL_WORK_ROOT env > first client root > ~/hcl_work."""
    if explicit:
        return explicit
    env = os.environ.get("HCL_WORK_ROOT")
    if env:
        return env
    # Attempt the roots round-trip whenever a ctx is present; the try/except below is the
    # authoritative graceful-degradation guard. CLIENT_CAPS is recorded for spec 3.2/7.5 and is
    # available to callers, but the in-helper path stays robust to whatever was recorded.
    if ctx is not None:
        try:
            roots = await ctx.list_roots()
            if roots:
                return os.path.join(_uri_to_path(roots[0].uri), "hcl_work")
        except Exception:
            pass  # client doesn't support roots (belt-and-suspenders fallback)
    return os.path.expanduser("~/hcl_work")

async def elicit_value(ctx, message, response_type):
    """Request a value from the user via the client. Returns the value, or None if unsupported/declined."""
    if ctx is None:
        return None
    # Attempt elicitation whenever a ctx is present; the try/except below is the authoritative
    # graceful-degradation guard. CLIENT_CAPS is recorded for spec 3.2/7.5 and is available to
    # callers, but the in-helper path stays robust to whatever was recorded.
    try:
        result = await ctx.elicit(message, response_type=response_type)
    except Exception:
        return None  # client doesn't support elicitation (belt-and-suspenders fallback)
    return getattr(result, "data", None)  # AcceptedElicitation has .data; Declined/Cancelled don't
