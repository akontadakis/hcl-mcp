"""The "this run takes long, proceed?" guard, on both protocol eras.

Up to MCP 2025-11-25 a server could send the client an `elicitation/create` request in the
middle of a tool call. MCP 2026-07-28 removed server-initiated requests: the tool RETURNS the
question (`InputRequiredResult`) and the client calls the tool again with the answer. The old
helper swallowed every exception, so on a new-protocol client the question failed silently and
the hour-long run simply started. These tests pin the three outcomes that matter -- proceed,
do not run, ask -- for each way a client can answer.
"""
import asyncio

import mcp.types as mt
import pytest
from fastmcp.server.elicitation import (AcceptedElicitation, CancelledElicitation,
                                        DeclinedElicitation)

from hcl_mcp import clientfeatures

LEGACY, MODERN = "2025-11-25", "2026-07-28"
MESSAGE = "annual run, minutes to hours. Proceed?"


BARE, FORM, URL_ONLY = (mt.ElicitationCapability(), mt.ElicitationCapability(form={}),
                        mt.ElicitationCapability(url={}))


class _Session:
    def __init__(self, elicitation):
        self.client_capabilities = type("Caps", (), {"elicitation": elicitation})()


class FakeCtx:
    """Just the surface confirm_run reads. `asked` records imperative elicitations.

    `elicitation` is the capability the client declared: BARE (`{}`, the pre-2025-11-25 way of
    saying "forms"), FORM, URL_ONLY, or None for a client that declared nothing.
    """

    def __init__(self, protocol, *, elicitation=BARE, legacy_reply=None, answers=None,
                 elicit_raises=None):
        self.session = _Session(elicitation)
        self.request_context = type("RC", (), {"protocol_version": protocol})()
        self.input_responses = answers
        self.asked = []
        self._legacy_reply = legacy_reply
        self._elicit_raises = elicit_raises

    async def elicit(self, message, response_type=None):
        self.asked.append(message)
        if self._elicit_raises is not None:
            raise self._elicit_raises
        return self._legacy_reply


def _confirm(ctx):
    return asyncio.run(clientfeatures.confirm_run(ctx, MESSAGE))


def test_without_a_client_context_the_run_proceeds():
    assert _confirm(None) is True


@pytest.mark.parametrize("protocol", [LEGACY, MODERN])
@pytest.mark.parametrize("declared", [None, URL_ONLY], ids=["nothing", "url_only"])
def test_a_client_that_cannot_show_a_form_is_not_asked_and_the_run_proceeds(protocol, declared):
    """The question is a form. A client that declared no elicitation, or only URL mode, must not
    be sent one ("MUST NOT send an inputRequests that the client has not declared support for")."""
    ctx = FakeCtx(protocol, elicitation=declared)
    assert _confirm(ctx) is True
    assert ctx.asked == []


@pytest.mark.parametrize("reply, proceeds", [
    (AcceptedElicitation(data=True), True),
    (AcceptedElicitation(data=False), False),
    (DeclinedElicitation(), False),
    (CancelledElicitation(), False),
])
def test_on_the_handshake_era_the_client_is_asked_directly(reply, proceeds):
    ctx = FakeCtx(LEGACY, legacy_reply=reply)
    assert _confirm(ctx) is proceeds
    assert ctx.asked == [MESSAGE]


def test_on_the_handshake_era_a_client_without_the_method_is_treated_as_unaskable():
    from mcp.shared.exceptions import MCPError
    refused = MCPError(mt.METHOD_NOT_FOUND, "Method not found")
    assert _confirm(FakeCtx(LEGACY, elicit_raises=refused)) is True


@pytest.mark.parametrize("failure", [
    RuntimeError("client went away while the question was open"),
    ValueError("malformed elicitation response"),
])
def test_on_the_handshake_era_any_other_failure_stops_the_tool_instead_of_starting_the_run(failure):
    """An unanswered question is not a yes. Swallowing these used to start an hours-long run
    on a dead session."""
    with pytest.raises(type(failure)):
        _confirm(FakeCtx(LEGACY, elicit_raises=failure))


@pytest.mark.parametrize("declared", [BARE, FORM], ids=["bare", "form"])
def test_on_the_modern_era_the_first_round_returns_the_question_instead_of_sending_it(declared):
    ctx = FakeCtx(MODERN, elicitation=declared)
    ask = _confirm(ctx)
    assert isinstance(ask, mt.InputRequiredResult)
    assert ctx.asked == [], "a server-initiated request is not allowed on this protocol"
    (request,) = ask.input_requests.values()
    assert request.method == "elicitation/create"
    assert request.params.message == MESSAGE
    assert request.params.requested_schema["properties"]["value"]["type"] == "boolean"


@pytest.mark.parametrize("answer, proceeds", [
    (mt.ElicitResult(action="accept", content={"value": True}), True),
    (mt.ElicitResult(action="accept", content={"value": False}), False),
    (mt.ElicitResult(action="decline"), False),
    (mt.ElicitResult(action="cancel"), False),
    # Only a real boolean true is a yes. bool("false") is True in Python, so a client that
    # sends the string would otherwise start the run the user refused.
    (mt.ElicitResult(action="accept", content={"value": "false"}), False),
    (mt.ElicitResult(action="accept", content={"value": "no"}), False),
    (mt.ElicitResult(action="accept", content={"value": "true"}), False),
    (mt.ElicitResult(action="accept", content={"value": 1}), False),
    (mt.ElicitResult(action="accept", content={}), False),
    (mt.ElicitResult(action="accept"), False),
])
def test_on_the_modern_era_the_retry_carries_the_answer(answer, proceeds):
    (key,) = _confirm(FakeCtx(MODERN)).input_requests       # the key the server minted
    assert _confirm(FakeCtx(MODERN, answers={key: answer})) is proceeds


def test_an_answer_to_some_other_question_does_not_count_and_the_question_is_asked_again():
    yes = mt.ElicitResult(action="accept", content={"value": True})
    ask = _confirm(FakeCtx(MODERN, answers={"not_our_question": yes}))
    assert isinstance(ask, mt.InputRequiredResult)


@pytest.mark.parametrize("value, proceeds", [(True, True), (False, False)])
def test_an_answer_is_honoured_even_if_the_retry_no_longer_declares_elicitation(value, proceeds):
    """Capabilities ride on each request, so the retry may declare less than the first call.
    A no that was given must not be forgotten because of that."""
    (key,) = _confirm(FakeCtx(MODERN)).input_requests
    answer = mt.ElicitResult(action="accept", content={"value": value})
    assert _confirm(FakeCtx(MODERN, elicitation=None, answers={key: answer})) is proceeds


# ---- through the real framework, both directions of the round trip ----

def _guarded_server():
    from fastmcp import Context, FastMCP
    server = FastMCP("guarded")

    @server.tool
    async def long_job(ctx: Context | None = None) -> dict:
        answer = await clientfeatures.confirm_run(ctx, MESSAGE)
        if isinstance(answer, mt.InputRequiredResult):
            return answer
        return {"ran": answer, "protocol": ctx.request_context.protocol_version}

    return server


def _call_through_a_real_client(mode, **client_kwargs):
    from fastmcp import Client

    async def call():
        async with Client(_guarded_server(), mode=mode, **client_kwargs) as client:
            return (await client.call_tool("long_job", {})).structured_content

    return asyncio.run(call())


async def _says_yes(message, response_type, params, context):
    return response_type(value=True)


async def _says_no(message, response_type, params, context):
    return response_type(value=False)


async def _declines(message, response_type, params, context):
    from fastmcp.client.elicitation import ElicitResult
    return ElicitResult(action="decline")


# `mode` is the client's side of the era: "legacy" forces the initialize handshake, "auto"
# adopts 2026-07-28. The protocol the tool actually saw is asserted, so neither row can pass
# by quietly running on the other era's code path.
_ERAS = [("legacy", LEGACY), ("auto", MODERN)]


@pytest.mark.parametrize("mode, protocol", _ERAS)
@pytest.mark.parametrize("handler, ran", [(_says_yes, True), (_says_no, False),
                                          (_declines, False)])
def test_a_real_client_answer_decides_whether_the_tool_runs(mode, protocol, handler, ran):
    out = _call_through_a_real_client(mode, elicitation_handler=handler)
    assert out == {"ran": ran, "protocol": protocol}


@pytest.mark.parametrize("mode, protocol", _ERAS)
def test_a_real_client_with_no_way_to_answer_still_gets_its_run(mode, protocol):
    assert _call_through_a_real_client(mode) == {"ran": True, "protocol": protocol}
