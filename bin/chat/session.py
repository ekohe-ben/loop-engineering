#!/usr/bin/env python3
"""Session manager for chat mode - handles session archive
(transcript.jsonl, meta.json, summary.md) under ~/.loop-engineering/sessions/.
See design PDF section 4."""
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator


@dataclass
class SessionMeta:
    """Session metadata stored in meta.json."""
    id: str
    title: str
    created: str  # ISO 8601 timestamp
    active_seat: str  # Current backend: 'claude', 'agy', etc.
    native: dict[str, str]  # Backend name -> native session ID
    summarized_through: int  # Index of last summarized message
    mode: str  # 'chat' or 'task'


@dataclass
class TranscriptEntry:
    """One message in transcript.jsonl."""
    ts: str  # ISO 8601 timestamp
    role: str  # 'user' | 'assistant' | 'tool'
    seat: str | None  # Which backend (for assistant messages)
    text: str
    native_id: str | None = None  # Session ID (for assistant messages)
    tokens_in: int | None = None
    tokens_out: int | None = None


class SessionManager:
    """Manages chat session lifecycle and persistence."""

    def __init__(self, sessions_root: str | Path | None = None):
        """Initialize session manager.
        
        Args:
            sessions_root: Root directory for sessions. Defaults to
                          ~/.loop-engineering/sessions/
        """
        if sessions_root is None:
            home = Path(os.environ.get("LOOP_ENGINEERING_HOME", 
                                      str(Path.home() / ".loop-engineering")))
            sessions_root = home / "sessions"
        
        self.sessions_root = Path(sessions_root)
        self.sessions_root.mkdir(parents=True, exist_ok=True)

    def create_session(self, title: str, seat: str = "claude", mode: str = "chat") -> SessionMeta:
        """Create a new session.
        
        Args:
            title: Human-readable session title
            seat: Initial backend ('claude', 'agy', etc.)
            mode: 'chat' or 'task'
            
        Returns:
            SessionMeta for the new session
        """
        # Generate slug from title + timestamp
        slug = self._make_slug(title)
        session_id = f"{datetime.now().strftime('%Y-%m-%d')}-{slug}"
        
        # Ensure unique ID (rare collision case)
        session_dir = self.sessions_root / session_id
        counter = 1
        while session_dir.exists():
            session_id = f"{datetime.now().strftime('%Y-%m-%d')}-{slug}-{counter}"
            session_dir = self.sessions_root / session_id
            counter += 1
        
        # Create session directory
        session_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize metadata
        meta = SessionMeta(
            id=session_id,
            title=title,
            created=datetime.now().isoformat(),
            active_seat=seat,
            native={},
            summarized_through=0,
            mode=mode,
        )
        
        self._write_meta(session_id, meta)
        
        # Create empty transcript
        transcript_path = session_dir / "transcript.jsonl"
        transcript_path.touch()
        
        return meta

    def open_session(self, session_id: str) -> SessionMeta:
        """Open existing session and load metadata.
        
        Args:
            session_id: Session identifier (directory name)
            
        Returns:
            SessionMeta for the session
            
        Raises:
            FileNotFoundError: If session doesn't exist
            ValueError: If session_id contains path traversal
        """
        # Prevent path traversal attacks
        if ".." in session_id or "/" in session_id or "\\" in session_id:
            raise ValueError(f"Invalid session_id (path traversal not allowed): {session_id}")
        
        session_dir = self.sessions_root / session_id
        if not session_dir.exists():
            raise FileNotFoundError(f"Session not found: {session_id}")
        
        return self._read_meta(session_id)

    def list_sessions(self, limit: int = 10) -> list[SessionMeta]:
        """List recent sessions, newest first.
        
        Args:
            limit: Maximum number of sessions to return
            
        Returns:
            List of SessionMeta, sorted by creation time descending
        """
        sessions = []
        for session_dir in self.sessions_root.iterdir():
            if not session_dir.is_dir():
                continue
            try:
                meta = self._read_meta(session_dir.name)
                sessions.append(meta)
            except (FileNotFoundError, json.JSONDecodeError):
                # Skip corrupted/incomplete sessions
                continue
        
        # Sort by created timestamp, newest first
        sessions.sort(key=lambda s: s.created, reverse=True)
        return sessions[:limit]

    def append_message(self, session_id: str, role: str, text: str, 
                      seat: str | None = None, native_id: str | None = None,
                      tokens_in: int | None = None, tokens_out: int | None = None):
        """Append a message to the transcript.
        
        Args:
            session_id: Session identifier
            role: 'user' | 'assistant' | 'tool'
            text: Message content
            seat: Backend name (for assistant messages)
            native_id: Native session ID (for assistant messages)
            tokens_in: Input tokens used
            tokens_out: Output tokens used
        """
        entry = TranscriptEntry(
            ts=datetime.now().isoformat(),
            role=role,
            seat=seat,
            text=text,
            native_id=native_id,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
        
        transcript_path = self.sessions_root / session_id / "transcript.jsonl"
        with open(transcript_path, "a") as f:
            json.dump(asdict(entry), f)
            f.write("\n")

    def read_transcript(self, session_id: str) -> list[TranscriptEntry]:
        """Read full transcript for a session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            List of TranscriptEntry in chronological order
        """
        transcript_path = self.sessions_root / session_id / "transcript.jsonl"
        if not transcript_path.exists():
            return []
        
        entries = []
        with open(transcript_path) as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    entries.append(TranscriptEntry(**data))
                except (json.JSONDecodeError, TypeError):
                    # Skip malformed lines
                    continue
        
        return entries

    def update_seat(self, session_id: str, seat: str, native_id: str | None = None):
        """Update active seat and optionally record native session ID.
        
        Args:
            session_id: Session identifier
            seat: New backend name
            native_id: Native session ID for this seat (if available)
        """
        meta = self._read_meta(session_id)
        meta.active_seat = seat
        
        if native_id:
            meta.native[seat] = native_id
        
        self._write_meta(session_id, meta)

    def update_mode(self, session_id: str, mode: str):
        """Update session mode (chat/task).
        
        Args:
            session_id: Session identifier
            mode: 'chat' or 'task'
        """
        meta = self._read_meta(session_id)
        meta.mode = mode
        self._write_meta(session_id, meta)

    def get_native_id(self, session_id: str, seat: str) -> str | None:
        """Get native session ID for a specific seat.
        
        Args:
            session_id: Session identifier
            seat: Backend name
            
        Returns:
            Native session ID or None if not available
        """
        meta = self._read_meta(session_id)
        return meta.native.get(seat)

    def _read_meta(self, session_id: str) -> SessionMeta:
        """Read meta.json for a session."""
        meta_path = self.sessions_root / session_id / "meta.json"
        with open(meta_path) as f:
            data = json.load(f)
        return SessionMeta(**data)

    def _write_meta(self, session_id: str, meta: SessionMeta):
        """Write meta.json for a session."""
        meta_path = self.sessions_root / session_id / "meta.json"
        with open(meta_path, "w") as f:
            json.dump(asdict(meta), f, indent=2)

    def _make_slug(self, title: str) -> str:
        """Convert title to filesystem-safe slug.
        
        Args:
            title: Human-readable title
            
        Returns:
            URL-safe slug (lowercase, hyphens, max 40 chars)
        """
        # Lowercase and replace spaces/underscores with hyphens
        slug = title.lower().replace(" ", "-").replace("_", "-")
        
        # Keep only alphanumeric and hyphens
        slug = re.sub(r"[^a-z0-9-]", "", slug)
        
        # Collapse multiple hyphens
        slug = re.sub(r"-+", "-", slug)
        
        # Trim leading/trailing hyphens
        slug = slug.strip("-")
        
        # Limit length
        return slug[:40] if slug else "untitled"
