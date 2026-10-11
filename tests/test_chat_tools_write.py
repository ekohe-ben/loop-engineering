import json

import pytest

from chat_tools import pending, registry

CAL = [{"id": "cal", "type": "google_calendar", "label": "Cal", "managed_by": "native", "settings": {}}]
BOX = [{"id": "work", "type": "mailbox", "label": "Work", "managed_by": "native", "settings": {}},
       {"id": "outl", "type": "mailbox", "label": "Outlook", "managed_by": "native", "settings": {}}]


class FakeCal:
    def __init__(self):
        self.created = []

    def create_event(self, event):
        self.created.append(event)
        return {"id": "ev1", "html_link": "https://cal.example/ev1"}


class FakeMail:
    def __init__(self):
        self.sent = []

    def send_message(self, to, cc, subject, body):
        self.sent.append((to, cc, subject, body))
        return {"id": "g1", "thread_id": "t1"}


@pytest.fixture(autouse=True)
def _pending_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(pending, "PENDING_DIR", tmp_path / "pending", raising=False)
    import inbox_config
    providers = {"work": "gmail", "outl": "outlook"}
    monkeypatch.setattr(inbox_config, "get_inbox", lambda name: {"name": name, "provider": providers[name]})


def test_write_tools_are_registered_as_write():
    registry._load_all()
    assert registry.TOOLS["calendar.create_event"].mode == registry.WRITE
    assert registry.TOOLS["mail.send"].mode == registry.WRITE


def test_proposing_a_write_never_executes_it():
    fake = FakeMail()
    out = registry.run("mail.send", json.dumps({"to": "a@x.com", "subject": "S", "body": "B"}),
                       load=lambda i: fake, list_accounts=lambda: BOX[:1], session="s1")
    assert out["status"] == "pending_approval" and fake.sent == []
    assert out["args"]["account"] == "work"


def test_calendar_create_event_runs_with_parsed_event_after_approval():
    fake = FakeCal()
    tool = registry.TOOLS["calendar.create_event"]
    out = registry.execute(tool, {"summary": "Sync", "start": "2026-10-12T15:00:00+08:00",
                                  "end": "2026-10-12T15:30:00+08:00", "attendees": "a@x.com, b@x.com"},
                           load=lambda i: fake, list_accounts=lambda: CAL)
    assert out["result"]["id"] == "ev1"
    assert fake.created[0]["attendees"] == ["a@x.com", "b@x.com"]


@pytest.mark.parametrize("patch,message", [
    ({"start": "2026-10-12T15:00:00"}, "UTC offset"),
    ({"end": "2026-10-12T14:00:00+08:00"}, "after start"),
    ({"attendees": "nope"}, "attendee"),
    ({"summary": "x\ny"}, "summary")])
def test_calendar_create_event_validates_input(patch, message):
    args = {"summary": "Sync", "start": "2026-10-12T15:00:00+08:00", "end": "2026-10-12T15:30:00+08:00", **patch}
    out = registry.execute(registry.TOOLS["calendar.create_event"], args,
                           load=lambda i: FakeCal(), list_accounts=lambda: CAL)
    assert message in out["error"]


def test_mail_send_splits_recipients_and_calls_connector():
    fake = FakeMail()
    out = registry.execute(registry.TOOLS["mail.send"],
                           {"to": "a@x.com, b@x.com", "cc": "c@x.com", "subject": "S", "body": "B", "account": "work"},
                           load=lambda i: fake, list_accounts=lambda: BOX)
    assert out["result"] == {"id": "g1", "thread_id": "t1"}
    assert fake.sent == [(["a@x.com", "b@x.com"], ["c@x.com"], "S", "B")]


def test_mail_send_picks_a_gmail_mailbox_and_rejects_outlook_only(monkeypatch):
    import inbox_config
    providers = {"work": "gmail", "outl": "outlook"}
    monkeypatch.setattr(inbox_config, "get_inbox", lambda name: {"name": name, "provider": providers[name]})
    from chat_tools import mail
    assert mail._select_gmail(BOX, {}) == "work"
    assert mail._select_gmail(BOX[1:], {}) is None
