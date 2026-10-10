#!/usr/bin/env python3
"""Tool registry for the dashboard chat. Each Tool is a named, validated
action the chat's `chat-tool call <tool> '<json>'` command can run against a
connector account. `run()` never raises: every failure becomes {"error": ...}
with no tokens or secret-bearing URLs in it."""
import json
from dataclasses import dataclass

import connectors_config

READ = "read"
WRITE = "write"
LOCAL = "local"
MAX_RESULT_BYTES = 20000
_MARKER_OPEN = "<untrusted_content>"
_MARKER_CLOSE = "</untrusted_content>"

TOOLS = {}


class ToolInputError(ValueError):
    """Raised by a handler for a user-facing input problem; its message is
    returned to the model verbatim, so it must be hand-written and secret-free."""


@dataclass(frozen=True)
class Arg:
    name: str
    kind: str = "str"
    required: bool = True
    help: str = ""


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args: tuple
    mode: str
    connector_type: object
    handler: object
    select: object = None


def register(tool):
    TOOLS[tool.name] = tool
    return tool


def _load_all():
    # Imported lazily so `import chat_tools.registry` stays cheap and cycle-free.
    from chat_tools import documents, github, gitlab, rss  # noqa: F401


def untrusted(text):
    """Wraps third-party text so the model treats it as data. A closing marker
    inside the text is defanged so it cannot end the wrapper early."""
    safe = str(text or "").replace(_MARKER_CLOSE, "</untrusted_content_>")
    return f"{_MARKER_OPEN}{safe}{_MARKER_CLOSE}"


def describe_all():
    _load_all()
    lines = []
    for tool in sorted(TOOLS.values(), key=lambda t: t.name):
        args = ", ".join(a.name + ("" if a.required else " (optional)") for a in tool.args)
        suffix = f" Args: {args}" if args else ""
        lines.append(f"{tool.name} ({tool.mode}): {tool.description}.{suffix}")
    return "\n".join(lines)


def _validate(tool, raw):
    try:
        args = json.loads(raw) if raw else None
    except ValueError:
        args = None
    if not isinstance(args, dict):
        return None, "Arguments must be a JSON object"
    allowed = {a.name for a in tool.args} | {"account"}
    for key in args:
        if key not in allowed:
            return None, f"Unknown argument: {key}"
    for arg in tool.args:
        value = args.get(arg.name)
        if value is None or value == "":
            if arg.required:
                return None, f"{arg.name} is required"
            continue
        if arg.kind == "int":
            if isinstance(value, bool) or not isinstance(value, int):
                return None, f"{arg.name} must be an integer"
        elif not isinstance(value, str):
            return None, f"{arg.name} must be a string"
    return args, None


def _resolve(tool, args, load, list_accounts):
    if tool.connector_type is None:
        return None, None
    if load is None:
        load = connectors_config.load_connector
    if list_accounts is None:
        list_accounts = connectors_config.list_accounts
    candidates = [a for a in list_accounts() if a["type"] == tool.connector_type]
    wanted = args.get("account")
    if wanted:
        candidates = [a for a in candidates if a["id"] == wanted]
    if not candidates:
        return None, f"No {tool.connector_type} connector account configured" + (
            f" with id {wanted}" if wanted else "")
    account_id = tool.select(candidates, args) if tool.select else None
    if tool.select and account_id is None:
        return None, f"No {tool.connector_type} connector account matches this request"
    return load(account_id or candidates[0]["id"]), None


def _cap(payload):
    text = json.dumps(payload)
    if len(text) <= MAX_RESULT_BYTES:
        return payload
    return {"tool": payload.get("tool"), "truncated": True,
            "result_prefix": text[:MAX_RESULT_BYTES]}


def execute(tool, args, load=None, list_accounts=None):
    """Runs the handler now (read, local, or an already-approved write)."""
    try:
        connector, error = _resolve(tool, args, load, list_accounts)
        if error:
            return {"error": error}
        result = tool.handler(connector, {k: v for k, v in args.items() if k != "account"})
        return _cap({"tool": tool.name, "result": result})
    except ToolInputError as exc:  # hand-written, secret-free by contract
        return {"error": str(exc)}
    except Exception as exc:  # noqa: BLE001 - never leak exception text (may quote tokens)
        return {"error": f"{tool.name} failed ({type(exc).__name__})"}


def run(name, args_json, load=None, list_accounts=None, session=""):
    _load_all()
    tool = TOOLS.get(name)
    if tool is None:
        return {"error": f"Unknown tool: {name}"}
    args, error = _validate(tool, args_json)
    if error:
        return {"error": error}
    return execute(tool, args, load=load, list_accounts=list_accounts)
