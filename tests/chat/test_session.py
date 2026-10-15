#!/usr/bin/env python3
"""Tests for chat session manager."""
import json
import tempfile
from pathlib import Path

import pytest

from chat.session import SessionManager, SessionMeta, TranscriptEntry


class TestSessionManager:
    """Test session creation, opening, and persistence."""

    @pytest.fixture
    def temp_sessions_root(self):
        """Temporary directory for sessions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def session_mgr(self, temp_sessions_root):
        """Session manager with temp root."""
        return SessionManager(temp_sessions_root)

    def test_create_session(self, session_mgr):
        """Create a new session."""
        meta = session_mgr.create_session("Test Session", seat="claude", mode="chat")
        
        assert meta.title == "Test Session"
        assert meta.active_seat == "claude"
        assert meta.mode == "chat"
        assert meta.id.endswith("-test-session")
        assert meta.summarized_through == 0
        assert meta.native == {}
        
        # Check files were created
        session_dir = session_mgr.sessions_root / meta.id
        assert session_dir.exists()
        assert (session_dir / "meta.json").exists()
        assert (session_dir / "transcript.jsonl").exists()

    def test_open_existing_session(self, session_mgr):
        """Open a session that was previously created."""
        # Create session
        meta1 = session_mgr.create_session("Test Session")
        
        # Open it again
        meta2 = session_mgr.open_session(meta1.id)
        
        assert meta2.id == meta1.id
        assert meta2.title == meta1.title
        assert meta2.active_seat == meta1.active_seat

    def test_open_nonexistent_session_raises(self, session_mgr):
        """Opening non-existent session raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            session_mgr.open_session("nonexistent-session")

    def test_list_sessions(self, session_mgr):
        """List recent sessions."""
        # Create multiple sessions
        session_mgr.create_session("First")
        session_mgr.create_session("Second")
        session_mgr.create_session("Third")
        
        sessions = session_mgr.list_sessions(limit=10)
        
        assert len(sessions) == 3
        # Should be newest first
        assert sessions[0].title == "Third"
        assert sessions[1].title == "Second"
        assert sessions[2].title == "First"

    def test_list_sessions_limit(self, session_mgr):
        """List sessions respects limit."""
        for i in range(5):
            session_mgr.create_session(f"Session {i}")
        
        sessions = session_mgr.list_sessions(limit=2)
        
        assert len(sessions) == 2

    def test_append_user_message(self, session_mgr):
        """Append a user message to transcript."""
        meta = session_mgr.create_session("Test")
        
        session_mgr.append_message(meta.id, role="user", text="Hello")
        
        transcript = session_mgr.read_transcript(meta.id)
        assert len(transcript) == 1
        assert transcript[0].role == "user"
        assert transcript[0].text == "Hello"
        assert transcript[0].seat is None

    def test_append_assistant_message(self, session_mgr):
        """Append assistant message with metadata."""
        meta = session_mgr.create_session("Test")
        
        session_mgr.append_message(
            meta.id,
            role="assistant",
            text="Hi there",
            seat="claude",
            native_id="session-123",
            tokens_in=100,
            tokens_out=50,
        )
        
        transcript = session_mgr.read_transcript(meta.id)
        assert len(transcript) == 1
        entry = transcript[0]
        assert entry.role == "assistant"
        assert entry.text == "Hi there"
        assert entry.seat == "claude"
        assert entry.native_id == "session-123"
        assert entry.tokens_in == 100
        assert entry.tokens_out == 50

    def test_read_transcript_preserves_order(self, session_mgr):
        """Transcript entries are in chronological order."""
        meta = session_mgr.create_session("Test")
        
        session_mgr.append_message(meta.id, "user", "First")
        session_mgr.append_message(meta.id, "assistant", "Second", seat="claude")
        session_mgr.append_message(meta.id, "user", "Third")
        
        transcript = session_mgr.read_transcript(meta.id)
        assert len(transcript) == 3
        assert transcript[0].text == "First"
        assert transcript[1].text == "Second"
        assert transcript[2].text == "Third"

    def test_update_seat(self, session_mgr):
        """Update active seat and native session ID."""
        meta = session_mgr.create_session("Test", seat="claude")
        
        session_mgr.update_seat(meta.id, seat="agy", native_id="conv-456")
        
        meta2 = session_mgr.open_session(meta.id)
        assert meta2.active_seat == "agy"
        assert meta2.native["agy"] == "conv-456"

    def test_update_mode(self, session_mgr):
        """Update session mode."""
        meta = session_mgr.create_session("Test", mode="chat")
        
        session_mgr.update_mode(meta.id, mode="task")
        
        meta2 = session_mgr.open_session(meta.id)
        assert meta2.mode == "task"

    def test_get_native_id(self, session_mgr):
        """Get native session ID for a seat."""
        meta = session_mgr.create_session("Test")
        
        # Initially no native ID
        assert session_mgr.get_native_id(meta.id, "claude") is None
        
        # Update it
        session_mgr.update_seat(meta.id, "claude", native_id="session-789")
        
        # Should be retrievable
        assert session_mgr.get_native_id(meta.id, "claude") == "session-789"
        # Other seats still None
        assert session_mgr.get_native_id(meta.id, "agy") is None

    def test_slug_generation(self, session_mgr):
        """Test title -> slug conversion."""
        test_cases = [
            ("Simple Title", "simple-title"),
            ("Title with CAPS", "title-with-caps"),
            ("Title_with_underscores", "title-with-underscores"),
            ("Title   with    spaces", "title-with-spaces"),
            ("Title!@#$%with^&*()special", "titlewithspecial"),
        ]
        
        for title, expected_slug_part in test_cases:
            meta = session_mgr.create_session(title)
            # Session ID is YYYY-MM-DD-<slug>
            assert expected_slug_part in meta.id

    def test_open_session_rejects_path_traversal(self, session_mgr):
        """Opening session with .. or / in ID raises ValueError."""
        with pytest.raises(ValueError, match="path traversal"):
            session_mgr.open_session("../etc/passwd")
        
        with pytest.raises(ValueError, match="path traversal"):
            session_mgr.open_session("../../other")
        
        with pytest.raises(ValueError, match="path traversal"):
            session_mgr.open_session("sessions/2026-10-14-test")
        
        with pytest.raises(ValueError, match="path traversal"):
            session_mgr.open_session("test\\windows\\path")
