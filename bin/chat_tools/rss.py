#!/usr/bin/env python3
"""rss.read_feed: entries of one of the user's configured feeds (read-only).
Configured feed URLs may embed secrets (userinfo, ?token=), so they are never
returned: the model sees and selects feeds by a sanitized label or 1-based index."""
import urllib.parse

from chat_tools.registry import Arg, READ, Tool, ToolInputError, register, untrusted

_MAX_ENTRIES = 20


def feed_label(url):
    """host[:port]/path with scheme, userinfo, query and fragment removed."""
    parts = urllib.parse.urlsplit(str(url or ""))
    host = parts.hostname or ""
    if parts.port:
        host += f":{parts.port}"
    return (host + parts.path).rstrip("/")


def _entry_link(link, feed_url):
    """Entry links are third-party. Keep one as-is only when it is on the
    feed's own host and carries no userinfo; otherwise reduce it to host+path
    so a credential or token query cannot reach the model."""
    parts = urllib.parse.urlsplit(str(link or ""))
    same_host = parts.hostname and parts.hostname == urllib.parse.urlsplit(feed_url).hostname
    if same_host and "@" not in parts.netloc:
        return link
    return feed_label(link)


def _pick(feeds, wanted):
    labels = [feed_label(f) for f in feeds]
    if not wanted:
        return 0
    if wanted.isdigit() and 1 <= int(wanted) <= len(feeds):
        return int(wanted) - 1
    if wanted in labels:
        return labels.index(wanted)
    raise ToolInputError("feed is not a configured feed; choose one of: " + ", ".join(labels))


def _read_feed(connector, args):
    feeds = connector.feed_urls()
    if not feeds:
        raise ToolInputError("no feeds are configured")
    index = _pick(feeds, str(args.get("feed") or "").strip())
    url = feeds[index]
    entries = connector.entries(url)[:_MAX_ENTRIES]
    return {"feed": feed_label(url), "index": index + 1,
            "feeds": [feed_label(f) for f in feeds],
            "entries": [{"title": untrusted(e["title"]), "link": _entry_link(e["link"], url),
                         "published": e["published"]} for e in entries]}


register(Tool(
    name="rss.read_feed", mode=READ, connector_type="rss", handler=_read_feed,
    description="Read the latest entries of a configured RSS/Atom feed (feed: its label or 1-based "
                "index from the feeds list; default: the first feed)",
    args=(Arg("feed", required=False),)))
