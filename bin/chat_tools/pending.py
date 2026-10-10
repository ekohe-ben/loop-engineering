#!/usr/bin/env python3
"""Pending write actions awaiting an Approve click. One JSON file per action
under outputs/chat-pending/. Args are frozen when the model proposes the
action; claim() is single use, expires after TTL_SECONDS and is bound to the
chat session that proposed it. Nothing here executes a tool: only the
dashboard's browser-only approve route does, with the record claim() hands it."""
import json
import os
import re
import secrets
import time
from pathlib import Path

_LOOP_DIR = Path(__file__).resolve().parent.parent.parent
PENDING_DIR = _LOOP_DIR / "outputs" / "chat-pending"
TTL_SECONDS = 900
_ID_RE = re.compile(r"^[0-9a-f]{32,64}$")


def _dir():
    path = Path(PENDING_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def create(tool, args, session, summary="", now=None):
    pending_id = secrets.token_hex(16)
    record = {"tool": tool, "args": args, "session": session, "summary": summary,
              "created": time.time() if now is None else now}
    fd = os.open(_dir() / f"{pending_id}.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(record, handle)
    return pending_id


def _valid(record, session, now):
    if not isinstance(record, dict) or not session or record.get("session") != session:
        return False
    created = record.get("created")
    if isinstance(created, bool) or not isinstance(created, (int, float)):
        return False
    now = time.time() if now is None else now
    return now - created <= TTL_SECONDS


def _load(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _read(pending_id, session, now):
    if not _ID_RE.match(str(pending_id)):
        return None
    record = _load(_dir() / f"{pending_id}.json")
    return record if _valid(record, session, now) else None


def lookup(pending_id, session, now=None):
    """The live record for this session, or None - never consumes it."""
    return _read(pending_id, session, now)


def claim(pending_id, session, now=None):
    if _read(pending_id, session, now) is None:
        return None
    path = _dir() / f"{pending_id}.json"
    claimed = path.with_suffix(".claimed")
    try:
        os.rename(path, claimed)   # atomic: only one caller wins
    except OSError:
        return None
    # Return what was actually claimed, not the earlier read.
    record = _load(claimed)
    return record if _valid(record, session, now) else None


def discard(pending_id, session):
    if _read(pending_id, session, None) is None:
        return False
    try:
        (_dir() / f"{pending_id}.json").unlink()
    except OSError:
        return False
    return True
