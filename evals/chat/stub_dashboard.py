#!/usr/bin/env python3
"""Offline stand-in for `dashboard_server.py chat-tool call` used only by the
chat eval (bin/chat_eval.py copies it to <sandbox>/bin/web/dashboard_server.py).
It runs the REAL chat_tools registry against canned connectors from a fixture
file, so the model sees real tool output but nothing touches GitLab, mail or
calendar. Every call and every side effect is appended to a JSONL log the
harness grades from."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ["LOOP_CHAT_EVAL_DIR"])
sys.path.insert(0, os.environ["LOOP_CHAT_EVAL_REPO_BIN"])

from chat_tools import documents, pending, registry, settings  # noqa: E402
import inbox_config  # noqa: E402

FIXTURE = json.loads(Path(os.environ["LOOP_CHAT_EVAL_FIXTURE"]).read_text())
LOG = Path(os.environ["LOOP_CHAT_EVAL_LOG"])
pending.PENDING_DIR = ROOT / "pending"
documents.DOCS_DIR = ROOT / "docs"
settings.DEFAULT_PATH = ROOT / "chat_tools.json"
settings.save(FIXTURE.get("auto_approve", []))
inbox_config.get_inbox = lambda name: {"name": name, "provider": "gmail", "account": "me@example.com"}

ACCOUNTS = [
    {"id": "gl", "type": "gitlab", "label": "GitLab", "managed_by": "native",
     "settings": {"url": "https://gitlab.example.com"}},
    {"id": "work", "type": "mailbox", "label": "Work", "managed_by": "native", "settings": {}},
    {"id": "cal", "type": "google_calendar", "label": "Cal", "managed_by": "native", "settings": {}},
]
EFFECTS = []


class FakeGitLab:
    def api(self, method, path, json_body=None):
        issue = FIXTURE["issue"]
        if method == "POST":
            EFFECTS.append("gitlab.comment")
            return {"id": 1}
        if "/notes" in path:
            return FIXTURE.get("notes", [])
        return {"iid": issue["iid"], "title": issue["title"], "state": "opened", "labels": [],
                "author": {"username": "reporter"}, "web_url": issue["web_url"],
                "description": issue["description"]}


class FakeMailbox:
    def send_message(self, to, cc, subject, body):
        EFFECTS.append("mail.send")
        return {"id": "m1", "thread_id": "t1"}

    def search_messages(self, query, limit):
        return []

    def read_message(self, message_id):
        raise registry.ToolInputError("no such message")


class FakeCalendar:
    def create_event(self, event):
        EFFECTS.append("calendar.create_event")
        return {"id": "e1", "html_link": ""}

    def list_events(self, time_min, time_max, max_results=50):
        return []


FAKES = {"gitlab": FakeGitLab, "mailbox": FakeMailbox, "google_calendar": FakeCalendar}


def main(argv):
    if len(argv) < 3 or argv[0] != "chat-tool" or argv[1] != "call":
        print("eval stub: only `chat-tool call <tool> <json>` is available", file=sys.stderr)
        return 1
    accounts = {a["id"]: a for a in ACCOUNTS}
    result = registry.run(argv[2], argv[3] if len(argv) > 3 else "{}",
                          load=lambda account_id: FAKES[accounts[account_id]["type"]](),
                          list_accounts=lambda: ACCOUNTS, session="chat-eval")
    status = ("error" if "error" in result else result.get("status") or
              ("auto_approved" if result.get("auto_approved") else "ok"))
    with LOG.open("a") as handle:
        handle.write(json.dumps({"tool": argv[2], "status": status, "effects": list(EFFECTS)}) + "\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
