#!/usr/bin/env python3
"""rss.read_feed: entries of one of the user's configured feeds (read-only)."""
from chat_tools.registry import Arg, READ, Tool, ToolInputError, register, untrusted

_MAX_ENTRIES = 20


def _read_feed(connector, args):
    feeds = connector.feed_urls()
    url = args.get("url") or (feeds[0] if feeds else "")
    if url not in feeds:
        raise ToolInputError("url is not a configured feed" if feeds else "no feeds are configured")
    entries = connector.entries(url)[:_MAX_ENTRIES]
    return {"feed": url, "entries": [
        {"title": untrusted(e["title"]), "link": e["link"], "published": e["published"]}
        for e in entries]}


register(Tool(
    name="rss.read_feed", mode=READ, connector_type="rss", handler=_read_feed,
    description="Read the latest entries of a configured RSS/Atom feed (default: the first feed)",
    args=(Arg("url", required=False),)))
