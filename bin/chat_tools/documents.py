#!/usr/bin/env python3
"""docs.save: the chat saves a markdown document (summary, report) the user can
open from the reply. A local write only, so it needs no confirmation card."""
import re
from pathlib import Path

from chat_tools.registry import Arg, LOCAL, Tool, register

_LOOP_DIR = Path(__file__).resolve().parent.parent.parent
DOCS_DIR = _LOOP_DIR / "outputs" / "chat-docs"
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,80}\.md$")


def safe_doc_name(name):
    return name if isinstance(name, str) and _NAME_RE.match(name) else None


def _slug(title):
    slug = re.sub(r"[^a-z0-9]+", "-", str(title).lower()).strip("-")[:60]
    return slug or "document"


def _save(_connector, args):
    docs_dir = Path(DOCS_DIR)
    docs_dir.mkdir(parents=True, exist_ok=True)
    slug = _slug(args["title"])
    name, n = f"{slug}.md", 1
    while (docs_dir / name).exists():
        n += 1
        name = f"{slug}-{n}.md"
    (docs_dir / name).write_text(args["content"], encoding="utf-8")
    return {"name": name, "url": f"/chat-docs/{name}"}


register(Tool(
    name="docs.save", mode=LOCAL, connector_type=None, handler=_save,
    description="Save a markdown document (e.g. a summary) and get a link the user can open",
    args=(Arg("title"), Arg("content"))))
