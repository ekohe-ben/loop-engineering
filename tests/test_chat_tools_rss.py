import json

import pytest

from chat_tools import registry, rss as chat_rss

SECRET_FEED = "https://u:p@feeds.example/x.xml?token=SECRET#frag"


class FakeRSS:
    def __init__(self, feeds=None, entries=None):
        self._feeds = ["https://a.example/feed.xml", "https://b.example/feed.xml"] if feeds is None else feeds
        self._entries = entries
        self.fetched = []

    def feed_urls(self):
        return self._feeds

    def entries(self, url):
        self.fetched.append(url)
        if self._entries is not None:
            return self._entries
        return [{"title": f"T{i}", "link": f"{url}/{i}", "id": str(i), "published": "2026-10-01"}
                for i in range(30)]


ACCOUNTS = [{"id": "rss", "type": "rss", "label": "RSS", "managed_by": "native", "settings": {}}]


def _run(args, fake=None):
    fake = fake or FakeRSS()
    return registry.run("rss.read_feed", json.dumps(args),
                        load=lambda i: fake, list_accounts=lambda: ACCOUNTS)


@pytest.mark.parametrize("url,label", [
    ("https://u:p@h.example/a/b.xml", "h.example/a/b.xml"),
    ("https://h.example/a.xml?token=SECRET", "h.example/a.xml"),
    ("https://h.example/a.xml#frag", "h.example/a.xml"),
    ("https://h.example:8443/a.xml", "h.example:8443/a.xml"),
    ("https://h.example", "h.example"),
    ("https://h.example/", "h.example"),
])
def test_feed_label_strips_userinfo_query_fragment_and_scheme(url, label):
    assert chat_rss.feed_label(url) == label


def test_defaults_to_first_feed_and_returns_at_most_20_entries():
    result = _run({})["result"]
    assert result["feed"] == "a.example/feed.xml" and result["index"] == 1
    assert result["feeds"] == ["a.example/feed.xml", "b.example/feed.xml"]
    assert len(result["entries"]) == 20
    assert result["entries"][0]["title"].startswith("<untrusted_content>")


def test_feed_selected_by_label_or_one_based_index():
    fake = FakeRSS()
    assert _run({"feed": "b.example/feed.xml"}, fake)["result"]["index"] == 2
    assert _run({"feed": "2"}, fake)["result"]["feed"] == "b.example/feed.xml"
    assert fake.fetched == ["https://b.example/feed.xml"] * 2


def test_unknown_feed_lists_only_sanitized_labels():
    fake = FakeRSS(feeds=[SECRET_FEED])
    for bad in ("https://evil.example/x", "9", "0"):
        error = _run({"feed": bad}, fake)["error"]
        assert "not a configured feed" in error and "feeds.example/x.xml" in error
        assert "SECRET" not in error and "u:p" not in error
    assert fake.fetched == []


def test_no_feeds_configured():
    assert "no feeds" in _run({}, FakeRSS(feeds=[]))["error"]


def test_result_never_contains_feed_secrets():
    entries = [{"title": "t", "link": "https://feeds.example/post/1", "published": "d"}]
    result = _run({}, FakeRSS(feeds=[SECRET_FEED], entries=entries))
    text = json.dumps(result)
    assert result["result"]["feed"] == "feeds.example/x.xml"
    for leaked in ("SECRET", "u:p", "token=", "frag"):
        assert leaked not in text


def test_entry_links_kept_only_when_same_host_as_feed():
    entries = [
        {"title": "a", "link": "https://feeds.example/p/1?utm=x", "published": "d"},
        {"title": "b", "link": "https://other.example/p/2?token=SECRET", "published": "d"},
        {"title": "c", "link": "https://z:y@feeds.example/p/3", "published": "d"},
    ]
    links = [e["link"] for e in
             _run({}, FakeRSS(feeds=["https://feeds.example/x.xml"], entries=entries))["result"]["entries"]]
    assert links == ["https://feeds.example/p/1?utm=x", "other.example/p/2", "feeds.example/p/3"]
