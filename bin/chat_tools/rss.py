#!/usr/bin/env python3
"""rss.read_feed: entries of one of the user's configured feeds (read-only).
Configured feed URLs may embed secrets (userinfo, ?token=), so they are never
returned: the model sees and selects feeds by a sanitized label or 1-based index."""
import re
import urllib.parse

from chat_tools.registry import Arg, READ, Tool, ToolInputError, register, untrusted

_MAX_ENTRIES = 20


def feed_label(url):
    """host[:port]/path with scheme, userinfo, query and fragment removed."""
    parts = urllib.parse.urlsplit(str(url or ""))
    host = parts.hostname or ""
    try:
        port = parts.port
    except ValueError:  # malformed port: fall back to the bare host
        port = None
    if port:
        host += f":{port}"
    return (host + parts.path).rstrip("/")


_SECRET_NAMES = ("token", "key", "sig", "auth", "secret", "pass", "session", "credential", "jwt")
_OPAQUE_VALUE = re.compile(r"^[A-Za-z0-9_-]{20,}$")


def _secret_looking(name, value, feed_values):
    return (any(word in name.lower() for word in _SECRET_NAMES)
            or (value != "" and value in feed_values)
            or bool(_OPAQUE_VALUE.match(value)))


def entry_link(link, feed_url):
    """Entry links are third-party. Off-host links (or any with userinfo) are
    reduced to host+path. A same-host link is kept without its fragment and
    without secret-looking query params (secret-ish name, a value that
    appears in the feed's own query, or an opaque 20+ char token value), so
    a feed token echoed into item links cannot reach the model."""
    parts = urllib.parse.urlsplit(str(link or ""))
    feed_parts = urllib.parse.urlsplit(feed_url)
    if not (parts.hostname and parts.hostname == feed_parts.hostname) or "@" in parts.netloc:
        return feed_label(link)
    feed_values = {v for _, v in urllib.parse.parse_qsl(feed_parts.query, keep_blank_values=True)}
    kept = []
    for pair in parts.query.split("&"):
        if not pair:
            continue
        name, _, value = pair.partition("=")
        name, value = urllib.parse.unquote_plus(name), urllib.parse.unquote_plus(value)
        if not _secret_looking(name, value, feed_values):
            kept.append(pair)
    return urllib.parse.urlunsplit(parts._replace(query="&".join(kept), fragment=""))


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
            "entries": [{"title": untrusted(e["title"]), "link": entry_link(e["link"], url),
                         "published": e["published"]} for e in entries]}


register(Tool(
    name="rss.read_feed", mode=READ, connector_type="rss", handler=_read_feed,
    description="Read the latest entries of a configured RSS/Atom feed (feed: its label or 1-based "
                "index from the feeds list; default: the first feed)",
    args=(Arg("feed", required=False),)))
