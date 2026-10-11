import json
import os
import urllib.request

import pytest

from chat_tools import pending, registry, settings

BOX = [{"id": "work", "type": "mailbox", "label": "Work", "managed_by": "native", "settings": {}}]


@pytest.fixture(autouse=True)
def _scratch(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DEFAULT_PATH", tmp_path / "chat_tools.json")
    monkeypatch.setattr(pending, "PENDING_DIR", tmp_path / "pending", raising=False)


def test_nothing_is_skipped_by_default():
    assert settings.auto_approved() == set()


def test_set_and_clear_round_trip_with_private_file_mode():
    settings.set_auto_approve("gitlab.comment", True)
    assert settings.auto_approved() == {"gitlab.comment"}
    assert (os.stat(settings.DEFAULT_PATH).st_mode & 0o777) == 0o600
    settings.set_auto_approve("gitlab.comment", False)
    assert settings.auto_approved() == set()


def test_only_registered_write_tools_can_be_skipped():
    for name in ("gitlab.read_issue", "docs.save", "nope.tool"):
        with pytest.raises(settings.SettingsError):
            settings.set_auto_approve(name, True)


def test_corrupt_or_unknown_entries_are_ignored():
    settings.DEFAULT_PATH.write_text("{not json")
    assert settings.auto_approved() == set()
    settings.DEFAULT_PATH.write_text(json.dumps({"auto_approve": ["gitlab.comment", "gitlab.read_issue", 5]}))
    assert settings.auto_approved() == {"gitlab.comment"}


class _Calls:
    def __init__(self):
        self.sent = []

    def api(self, method, path, json_body=None):
        self.sent.append((method, path, json_body))
        return {"id": 7}


GL = [{"id": "gl", "type": "gitlab", "label": "GL", "managed_by": "native", "settings": {"url": "https://gl.example"}}]
ARGS = json.dumps({"url": "https://gl.example/g/p/-/issues/3", "body": "hi"})


def test_a_skipped_write_runs_immediately_and_others_still_wait():
    fake = _Calls()
    settings.set_auto_approve("gitlab.comment", True)
    out = registry.run("gitlab.comment", ARGS, load=lambda i: fake, list_accounts=lambda: GL, session="s1")
    assert out["result"] == {"note_id": 7} and out.get("auto_approved") is True and len(fake.sent) == 1
    other = registry.run("github.comment", json.dumps({"repo": "o/r", "number": 1, "body": "x"}),
                         load=lambda i: fake, list_accounts=lambda: [
                             {"id": "gh", "type": "github", "label": "GH", "managed_by": "native", "settings": {}}],
                         session="s1")
    assert other["status"] == "pending_approval" and len(fake.sent) == 1


def test_default_still_requires_approval():
    fake = _Calls()
    out = registry.run("gitlab.comment", ARGS, load=lambda i: fake, list_accounts=lambda: GL, session="s1")
    assert out["status"] == "pending_approval" and fake.sent == []
