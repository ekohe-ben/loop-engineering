import json

from chat_tools import github as chat_github, pending, registry


class FakeGitHub:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def api(self, method, path, **kw):
        self.calls.append((method, path, kw.get("json_body")))
        return self.routes[path]


ACCOUNTS = [{"id": "gh", "type": "github", "label": "GH", "managed_by": "native", "settings": {}}]
ISSUE = {"number": 5, "title": "Bug", "state": "open", "body": "details", "user": {"login": "ann"},
         "html_url": "https://github.com/o/r/issues/5"}
COMMENTS = [{"user": {"login": "bob"}, "body": "me too", "created_at": "2026-10-01T00:00:00Z"}]


def _run(name, args, fake):
    return registry.run(name, json.dumps(args), load=lambda i: fake, list_accounts=lambda: ACCOUNTS)


def test_read_issue_wraps_body_and_comments():
    fake = FakeGitHub({"/repos/o/r/issues/5": ISSUE, "/repos/o/r/issues/5/comments?per_page=50": COMMENTS})
    result = _run("github.read_issue", {"repo": "o/r", "number": 5}, fake)["result"]
    assert result["title"].startswith("<untrusted_content>")
    assert result["comments"][0]["author"] == registry.untrusted("bob")
    assert result["comments"][0]["body"].startswith("<untrusted_content>")


def test_read_pr_includes_branches_and_changed_files_count():
    pr = dict(ISSUE, head={"ref": "feat"}, base={"ref": "main"}, changed_files=3, merged=False)
    fake = FakeGitHub({"/repos/o/r/pulls/5": pr, "/repos/o/r/issues/5/comments?per_page=50": COMMENTS})
    result = _run("github.read_pr", {"repo": "o/r", "number": 5}, fake)["result"]
    assert (result["head"], result["base"], result["changed_files"]) == ("feat", "main", 3)


def test_repo_must_be_owner_slash_name():
    result = _run("github.read_issue", {"repo": "../../etc", "number": 1}, FakeGitHub({}))
    assert "owner/name" in result["error"]


def test_comment_posts_json_body_only_when_executed():
    fake = FakeGitHub({"/repos/o/r/issues/5/comments": {"id": 77}})
    tool = registry.TOOLS["github.comment"]
    assert tool.mode == registry.WRITE
    result = registry.execute(tool, {"repo": "o/r", "number": 5, "body": "thanks"},
                              load=lambda i: fake, list_accounts=lambda: ACCOUNTS)
    assert result["result"] == {"comment_id": 77}
    assert fake.calls == [("POST", "/repos/o/r/issues/5/comments", {"body": "thanks"})]


def test_run_only_proposes_the_comment(tmp_path, monkeypatch):
    monkeypatch.setattr(pending, "PENDING_DIR", tmp_path)
    fake = FakeGitHub({})
    result = registry.run("github.comment", json.dumps({"repo": "o/r", "number": 5, "body": "thanks"}),
                          load=lambda i: fake, list_accounts=lambda: ACCOUNTS, session="s1")
    assert result["status"] == "pending_approval"
    assert fake.calls == []


def test_small_thread_is_not_truncated_and_author_is_wrapped():
    fake = FakeGitHub({"/repos/o/r/issues/5": ISSUE, "/repos/o/r/issues/5/comments?per_page=50": COMMENTS})
    result = _run("github.read_issue", {"repo": "o/r", "number": 5}, fake)["result"]
    assert result["comments_truncated"] is False
    assert result["author"] == registry.untrusted("ann") and result["state"] == registry.untrusted("open")
    assert result["comments"][0]["author"] == registry.untrusted("bob")


def test_120_comments_requests_the_last_page_and_flags():
    issue = dict(ISSUE, comments=120, labels=[{"name": "bug"}])
    fake = FakeGitHub({"/repos/o/r/issues/5": issue,
                       "/repos/o/r/issues/5/comments?per_page=50&page=3": COMMENTS})
    result = _run("github.read_issue", {"repo": "o/r", "number": 5}, fake)["result"]
    assert result["comments_truncated"] is True and result["labels"] == [registry.untrusted("bug")]
    assert fake.calls[-1][1].endswith("page=3")
