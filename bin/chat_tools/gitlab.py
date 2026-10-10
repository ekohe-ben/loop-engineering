#!/usr/bin/env python3
"""GitLab chat tools. All issue text (title, description, comments) is
third-party content and is wrapped with registry.untrusted()."""
import re
import urllib.parse

from chat_tools.registry import Arg, READ, WRITE, Tool, ToolInputError, register, untrusted

_ISSUE_URL_RE = re.compile(r"^https?://([^/]+)/(.+?)/-/issues/(\d+)(?:[/?#].*)?$")


def parse_issue_url(url):
    match = _ISSUE_URL_RE.match(str(url or "").strip())
    if not match:
        return None
    return match.group(1), match.group(2), int(match.group(3))


def _quote(project):
    return urllib.parse.quote(str(project), safe="")


def _host(account):
    return urllib.parse.urlparse(account.get("settings", {}).get("url", "")).netloc


def _select_by_url(accounts, args):
    """Account whose instance host equals the URL's host; with no URL, the
    first account. None when a URL names a host nobody is configured for."""
    parsed = parse_issue_url(args.get("url"))
    if parsed is None:
        return accounts[0]["id"]
    for account in accounts:
        if _host(account) == parsed[0]:
            return account["id"]
    return None


def _issue_ref(args):
    parsed = parse_issue_url(args.get("url"))
    if parsed:
        _, project, iid = parsed
        return project, iid
    if args.get("project") and args.get("iid"):
        return args["project"], args["iid"]
    raise ToolInputError("url, or project and iid, is required")


def _read_issue(connector, args):
    project, iid = _issue_ref(args)
    base = f"/projects/{_quote(project)}/issues/{int(iid)}"
    issue = connector.api("GET", base)
    raw_notes = connector.api("GET", f"{base}/notes?per_page=50&sort=desc")
    notes = list(reversed(raw_notes))  # newest 50, oldest first
    return {
        "iid": issue["iid"], "title": untrusted(issue.get("title")),
        "state": issue.get("state"),
        "labels": [untrusted(l) for l in issue.get("labels") or []],
        "author": untrusted((issue.get("author") or {}).get("username")),
        "web_url": issue.get("web_url"),
        "description": untrusted(issue.get("description")),
        "comments": [
            {"author": untrusted((n.get("author") or {}).get("username")),
             "created_at": n.get("created_at"), "body": untrusted(n.get("body"))}
            for n in notes if not n.get("system")
        ],
        "comments_truncated": len(raw_notes) >= 50,
    }


def _list_issues(connector, args):
    state = args.get("state") or "opened"
    issues = connector.api(
        "GET", f"/projects/{_quote(args['project'])}/issues?state={urllib.parse.quote(state)}&per_page=20")
    return {"issues": [
        {"iid": i["iid"], "title": untrusted(i.get("title")), "state": i.get("state"),
         "web_url": i.get("web_url")} for i in issues]}


register(Tool(
    name="gitlab.read_issue", mode=READ, connector_type="gitlab", handler=_read_issue,
    select=_select_by_url,
    description="Read one GitLab issue with its description and comments (pass the issue url, or project and iid)",
    args=(Arg("url", required=False), Arg("project", required=False),
          Arg("iid", kind="int", required=False))))
def _comment(connector, args):
    project, iid = _issue_ref(args)
    note = connector.api("POST", f"/projects/{_quote(project)}/issues/{int(iid)}/notes",
                         json_body={"body": args["body"]})
    return {"note_id": note.get("id")}


register(Tool(
    name="gitlab.list_issues", mode=READ, connector_type="gitlab", handler=_list_issues,
    description="List up to 20 issues of a GitLab project (state: opened, closed or all)",
    args=(Arg("project"), Arg("state", required=False))))
register(Tool(
    name="gitlab.comment", mode=WRITE, connector_type="gitlab", handler=_comment,
    select=_select_by_url,
    description="Post a comment on a GitLab issue (needs the user's approval)",
    args=(Arg("body"), Arg("url", required=False), Arg("project", required=False),
          Arg("iid", kind="int", required=False))))
