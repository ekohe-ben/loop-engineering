#!/usr/bin/env python3
"""Mail chat tools: search a connected mailbox, read one message, and (after the
user approves the card) send one from a Gmail mailbox. Everything in a message
is third-party text, so it is wrapped as untrusted. Outlook has no send: its
grant lacks Mail.Send and Inbox Triage's grant is kept send-free."""
from chat_tools.registry import Arg, READ, WRITE, Tool, ToolInputError, register, untrusted
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


def _addresses(text, label):
    parts = [p.strip() for p in str(text or "").replace(";", ",").split(",") if p.strip()]
    if not parts and label == "to":
        raise ToolInputError("to is required")
    return parts


def _select_gmail(candidates, args):
    """First mailbox account that is a Gmail inbox (sending is Gmail-only)."""
    import inbox_config
    for account in candidates:
        try:
            if inbox_config.get_inbox(account["id"]).get("provider") == "gmail":
                return account["id"]
        except (KeyError, FileNotFoundError, ValueError):
            continue
    return None


def _send(connector, args):
    return _call(connector.send_message, _addresses(args.get("to"), "to"), _addresses(args.get("cc"), "cc"),
                 str(args["subject"]), str(args["body"]))


register(Tool(
    name="mail.send", mode=WRITE, connector_type="mailbox", handler=_send, select=_select_gmail,
    description="Send a plain-text email from the user's Gmail mailbox (to/cc: comma-separated plain "
                "addresses, at most 10 in total; needs the user's approval)",
    args=(Arg("to"), Arg("subject"), Arg("body"), Arg("cc", required=False))))
