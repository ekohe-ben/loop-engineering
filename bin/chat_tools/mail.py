#!/usr/bin/env python3
"""Mail chat tools (read-only): search a connected mailbox and read one message.
Everything in a message is third-party text, so it is wrapped as untrusted.
There is deliberately no send tool: the mailbox OAuth scopes do not cover it."""
from chat_tools.registry import Arg, READ, Tool, ToolInputError, register, untrusted
from connectors.base import ConnectorError

_MAX_LIMIT = 20
_DEFAULT_LIMIT = 10


def _call(fn, *args):
    try:
        return fn(*args)
    except ConnectorError as exc:  # connector messages are token-free by contract
        raise ToolInputError(str(exc)) from None


def _search(connector, args):
    limit = min(max(int(args.get("limit") or _DEFAULT_LIMIT), 1), _MAX_LIMIT)
    rows = _call(connector.search_messages, str(args["query"]), limit)
    return {"messages": [{"id": r["id"], "subject": untrusted(r["subject"]), "from": untrusted(r["from"]),
                          "date": r["date"], "snippet": untrusted(r["snippet"])} for r in rows]}


def _read(connector, args):
    m = _call(connector.read_message, str(args["id"]))
    return {"message": {
        "id": m["id"], "date": m["date"], "from": untrusted(m["from"]), "to": untrusted(m["to"]),
        "cc": untrusted(m["cc"]), "subject": untrusted(m["subject"]), "body_text": untrusted(m["body_text"]),
        "attachments": [untrusted(a) for a in m["attachments"]]}}


register(Tool(
    name="mail.search", mode=READ, connector_type="mailbox", handler=_search,
    description="Search a connected mailbox (query: Gmail search syntax or free text; limit: up to 20) "
                "and list matching messages without bodies",
    args=(Arg("query"), Arg("limit", kind="int", required=False))))
register(Tool(
    name="mail.read", mode=READ, connector_type="mailbox", handler=_read,
    description="Read one message (id from mail.search) with its body text",
    args=(Arg("id"),)))
