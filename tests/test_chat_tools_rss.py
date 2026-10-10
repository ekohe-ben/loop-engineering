import json

from chat_tools import registry


class FakeRSS:
    def feed_urls(self):
        return ["https://a.example/feed.xml", "https://b.example/feed.xml"]

    def entries(self, url):
        if url.startswith("https://bad"):
            raise RuntimeError("secret detail")
        return [{"title": f"T{i}", "link": f"{url}/{i}", "id": str(i), "published": "2026-10-01"}
                for i in range(30)]


ACCOUNTS = [{"id": "rss", "type": "rss", "label": "RSS", "managed_by": "native", "settings": {}}]


def _run(args):
    return registry.run("rss.read_feed", json.dumps(args),
                        load=lambda i: FakeRSS(), list_accounts=lambda: ACCOUNTS)


def test_defaults_to_first_feed_and_returns_at_most_20_entries():
    result = _run({})["result"]
    assert result["feed"] == "https://a.example/feed.xml" and len(result["entries"]) == 20
    assert result["entries"][0]["title"].startswith("<untrusted_content>")


def test_only_configured_feed_urls_are_fetched():
    assert "not a configured feed" in _run({"url": "https://evil.example/x"})["error"]
    assert _run({"url": "https://b.example/feed.xml"})["result"]["feed"] == "https://b.example/feed.xml"
