#!/usr/bin/env python3
"""Which chat write tools skip the Approve card. Empty by default: every write
waits for a human click. The file is changed only by the dashboard's CSRF-guarded
settings route; no chat-tool action touches it, and the chat's own tools cannot
write files."""
import json
import os
from pathlib import Path

LOOP_ENGINEERING_HOME = Path(os.environ.get("LOOP_ENGINEERING_HOME", str(Path.home() / ".loop-engineering")))
DEFAULT_PATH = LOOP_ENGINEERING_HOME / "chat_tools.json"


class SettingsError(ValueError):
    """A hand-written, secret-free message."""


def _write_tools():
    from chat_tools import registry
    registry._load_all()
    return {t.name for t in registry.TOOLS.values() if t.mode == registry.WRITE}


def auto_approved(path=None):
    """Names of write tools the user chose to run without review. A missing or
    corrupt file, or an entry that is not a known write tool, means review."""
    if path is None:
        path = DEFAULT_PATH
    try:
        names = json.loads(Path(path).read_text()).get("auto_approve")
    except (OSError, ValueError, AttributeError):
        return set()
    if not isinstance(names, list):
        return set()
    return {n for n in names if isinstance(n, str)} & _write_tools()


def set_auto_approve(tool, enabled, path=None):
    if path is None:
        path = DEFAULT_PATH
    if tool not in _write_tools():
        raise SettingsError(f"{tool} is not a chat write tool")
    chosen = auto_approved(path)
    chosen.add(tool) if enabled else chosen.discard(tool)
    save(chosen, path)


def save(names, path=None):
    """Replaces the whole list (every name must be a known write tool)."""
    if path is None:
        path = DEFAULT_PATH
    names = set(names)
    unknown = names - _write_tools()
    if unknown:
        raise SettingsError(f"{sorted(unknown)[0]} is not a chat write tool")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump({"auto_approve": sorted(names)}, handle, indent=2)
    os.replace(tmp, path)
