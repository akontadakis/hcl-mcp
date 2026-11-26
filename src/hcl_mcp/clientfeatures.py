"""Client-facing helpers: where output goes, and how a long run is confirmed.

Both are written for a protocol with no connection state. From MCP 2026-07-28 there is no
`initialize` handshake to remember, capabilities ride on every request, and a server may not
send the client a request of its own. So nothing here is recorded at start-up or cached between
calls: `resolve_work_dir` depends only on its arguments and the server's environment, and
`confirm_run` reads what it needs from the request in hand. Clients on the older handshake
revisions are served by the same two functions.
"""
import os

import mcp.types as mcp_types
from mcp.shared.exceptions import MCPError
from mcp_types.version import MODERN_PROTOCOL_VERSIONS


async def resolve_work_dir(ctx, explicit=None):
    """Pick the output dir. Precedence: explicit arg > HCL_WORK_ROOT env > ~/hcl_work.

    `ctx` is accepted so every file-writing tool keeps one call shape, but it is not consulted.
    The client's roots used to be a third source; Roots is deprecated in MCP 2026-07-28 and the
    request that fetched them no longer exists there, so honouring them would put the same call's
    output in a different folder depending on the client's protocol revision.
    """
    if explicit:
        return explicit
    env = os.environ.get("HCL_WORK_ROOT")
    if env:
        return env
    return os.path.expanduser("~/hcl_work")


_CONFIRM_KEY = "confirm_long_run"
_CONFIRM_SCHEMA = {"type": "object",
                   "properties": {"value": {"type": "boolean", "title": "Proceed"}},
                   "required": ["value"]}


def _client_can_be_asked(ctx):
    """True when THIS request's client declared that it can show an elicitation FORM.

    Read live from the session every time. From MCP 2026-07-28 capabilities ride on each request
    and a server must not infer them from an earlier one, so there is nothing to cache.

    Elicitation has two modes, `form` and `url`, and the confirmation is a form. A bare
    `elicitation: {}` is how clients declared forms before the modes existed, so it counts; a
    client that names only `url` must not be sent a form.
    """
    try:
        declared = ctx.session.client_capabilities.elicitation
    except Exception:
        return False  # no live session (e.g. a context built outside a request)
    if declared is None:
        return False
    form, url = getattr(declared, "form", None), getattr(declared, "url", None)
    return form is not None or url is None


def _is_modern_protocol(ctx):
    """True when the request arrived on a revision without server-initiated requests."""
    rc = getattr(ctx, "request_context", None)
    return rc is not None and rc.protocol_version in MODERN_PROTOCOL_VERSIONS


def _is_yes(answer):
    """Only an accepted form whose value is the boolean true is a yes.

    `bool("false")` is True, so a truthiness test would turn a client's string "false" into
    consent. Decline, cancel, a missing value and every non-boolean are all a no.
    """
    return answer.action == "accept" and (answer.content or {}).get("value") is True


async def confirm_run(ctx, message):
    """Ask the user to confirm a long run. Returns one of three things:

      True                  proceed -- confirmed, or nobody can be asked (no ctx, or the client
                            did not declare form elicitation). A client that cannot answer must
                            still be able to run the tool.
      False                 do not run -- the user answered no, declined, or cancelled.
      InputRequiredResult   the question itself. The tool must RETURN it unchanged; the client
                            answers by calling the same tool again, and that second call lands
                            back here with the answer in `ctx.input_responses`.

    Which path runs depends on the protocol revision of the request. Up to 2025-11-25 the server
    sends `elicitation/create` and waits. From 2026-07-28 server-initiated requests no longer
    exist (SEP-2322), so the question is returned instead. Nothing is kept between the two
    rounds: the retry carries everything needed.

    This is a courtesy prompt about cost, not an authorization check: a caller can always pass
    run=False, and a client that cannot be asked runs unasked. So an answer supplied without the
    question having been put is simply taken at its word.
    """
    if ctx is None:
        return True
    # An answer in hand wins over everything else. Capabilities are per request, so the retry
    # may declare less than the first call did; a no that was given must still be a no.
    answers = getattr(ctx, "input_responses", None)
    if answers and _CONFIRM_KEY in answers:
        return _is_yes(answers[_CONFIRM_KEY])
    if not _client_can_be_asked(ctx):
        return True
    if _is_modern_protocol(ctx):
        return mcp_types.InputRequiredResult(input_requests={
            _CONFIRM_KEY: mcp_types.ElicitRequest(params=mcp_types.ElicitRequestFormParams(
                message=message, requested_schema=_CONFIRM_SCHEMA))})
    try:
        reply = await ctx.elicit(message, response_type=bool)
    except MCPError as exc:
        if exc.code == mcp_types.METHOD_NOT_FOUND:
            return True  # declared, but the client has no such method: it cannot be asked
        raise
    # Any other failure propagates and the tool errors: an unanswered question is not a yes.
    return getattr(reply, "data", None) is True  # Declined/Cancelled carry no .data
