#!/usr/bin/env python3
"""GitHub chat tools. Issue/PR text is third-party content (untrusted)."""
import re

from chat_tools.registry import Arg, READ, WRITE, Tool, ToolInputError, register, untrusted

_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def _repo(args):
    repo = str(args["repo"])
    if not _REPO_RE.match(repo) or ".." in repo.split("/"):
        raise ToolInputError("repo must look like owner/name")
    return repo


def _comments(connector, repo, number, total):
    """Newest 50 comments, oldest first. The endpoint is ascending-only, so
    with more than 50 the last page is requested instead of the first."""
    total = total if isinstance(total, int) and not isinstance(total, bool) else 0
    path = f"/repos/{repo}/issues/{int(number)}/comments?per_page=50"
    if total > 50:
        path += f"&page={-(-total // 50)}"
    items = connector.api("GET", path)
    return [{"author": untrusted((c.get("user") or {}).get("login")), "created_at": c.get("created_at"),
             "body": untrusted(c.get("body"))} for c in items], total > 50


def _read_issue(connector, args):
    repo = _repo(args)
    issue = connector.api("GET", f"/repos/{repo}/issues/{int(args['number'])}")
    comments, truncated = _comments(connector, repo, args["number"], issue.get("comments"))
    return {"number": issue["number"], "title": untrusted(issue.get("title")),
            "state": untrusted(issue.get("state")),
            "labels": [untrusted(l.get("name") if isinstance(l, dict) else l)
                       for l in issue.get("labels") or []],
            "author": untrusted((issue.get("user") or {}).get("login")),
            "html_url": issue.get("html_url"), "body": untrusted(issue.get("body")),
            "comments": comments, "comments_truncated": truncated}


def _read_pr(connector, args):
    repo = _repo(args)
    pr = connector.api("GET", f"/repos/{repo}/pulls/{int(args['number'])}")
    comments, truncated = _comments(connector, repo, args["number"], pr.get("comments"))
    return {"number": pr["number"], "title": untrusted(pr.get("title")), "state": untrusted(pr.get("state")),
            "merged": bool(pr.get("merged")), "author": untrusted((pr.get("user") or {}).get("login")),
            "html_url": pr.get("html_url"), "body": untrusted(pr.get("body")),
            "head": (pr.get("head") or {}).get("ref"), "base": (pr.get("base") or {}).get("ref"),
            "changed_files": pr.get("changed_files"),
            "comments": comments, "comments_truncated": truncated}


def _comment(connector, args):
    repo = _repo(args)
    made = connector.api("POST", f"/repos/{repo}/issues/{int(args['number'])}/comments",
                         json_body={"body": args["body"]})
    return {"comment_id": made.get("id")}


_REPO_NUMBER = (Arg("repo", help="owner/name"), Arg("number", kind="int"))
register(Tool(name="github.read_issue", mode=READ, connector_type="github", handler=_read_issue,
              description="Read a GitHub issue with its comments", args=_REPO_NUMBER))
register(Tool(name="github.read_pr", mode=READ, connector_type="github", handler=_read_pr,
              description="Read a GitHub pull request with its comments", args=_REPO_NUMBER))
register(Tool(name="github.comment", mode=WRITE, connector_type="github", handler=_comment,
              description="Post a comment on a GitHub issue or pull request (needs the user's approval)",
              args=(Arg("body"),) + _REPO_NUMBER))
