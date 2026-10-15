#!/usr/bin/env python3
"""Integration tests for session persistence E2E.

Tests real file system operations and session lifecycle."""
import json

import pytest

from chat.repl import ChatREPL
from chat.session import SessionManager


pytestmark = pytest.mark.integration


class TestSessionPersistenceE2E:
    """Test session persistence through real file operations."""

    def test_session_creates_correct_directory_structure(self, integration_env):
        """Creating a session creates expected files on disk."""
        loop_home = integration_env["loop_home"]
        sessions_dir = integration_env["sessions_dir"]
        
        mgr = SessionManager(sessions_dir)
        meta = mgr.create_session("Test Session", seat="claude", mode="chat")
        
        session_dir = sessions_dir / meta.id
        
        # Verify directory exists
        assert session_dir.exists()
        assert session_dir.is_dir()
        
        # Verify meta.json exists and is valid
        meta_file = session_dir / "meta.json"
        assert meta_file.exists()
        with open(meta_file) as f:
            meta_data = json.load(f)
        assert meta_data["title"] == "Test Session"
        assert meta_data["active_seat"] == "claude"
        assert meta_data["mode"] == "chat"
        
        # Verify transcript.jsonl exists (empty initially)
        transcript_file = session_dir / "transcript.jsonl"
        assert transcript_file.exists()
        assert transcript_file.read_text() == ""

    def test_append_message_persists_to_jsonl(self, integration_env):
        """Appending messages writes to transcript.jsonl."""
        sessions_dir = integration_env["sessions_dir"]
        
        mgr = SessionManager(sessions_dir)
        meta = mgr.create_session("Persistence Test")
        
        # Append user message
        mgr.append_message(meta.id, "user", "Hello")
        
        # Read transcript file directly
        transcript_file = sessions_dir / meta.id / "transcript.jsonl"
        lines = transcript_file.read_text().strip().split("\n")
        assert len(lines) == 1
        
        entry = json.loads(lines[0])
        assert entry["role"] == "user"
        assert entry["text"] == "Hello"
        assert "ts" in entry
        
        # Append assistant message
        mgr.append_message(
            meta.id, "assistant", "Hi there",
            seat="claude", native_id="session-123",
            tokens_in=50, tokens_out=20
        )
        
        # Read again
        lines = transcript_file.read_text().strip().split("\n")
        assert len(lines) == 2
        
        entry2 = json.loads(lines[1])
        assert entry2["role"] == "assistant"
        assert entry2["text"] == "Hi there"
        assert entry2["seat"] == "claude"
        assert entry2["native_id"] == "session-123"
        assert entry2["tokens_in"] == 50
        assert entry2["tokens_out"] == 20

    def test_session_reopens_from_disk(self, integration_env):
        """Sessions can be reopened and data is preserved."""
        sessions_dir = integration_env["sessions_dir"]
        
        # Create and populate session
        mgr1 = SessionManager(sessions_dir)
        meta1 = mgr1.create_session("Reopen Test", seat="claude")
        mgr1.append_message(meta1.id, "user", "Message 1")
        mgr1.append_message(meta1.id, "assistant", "Reply 1", seat="claude")
        mgr1.update_seat(meta1.id, "agy", "native-789")
        
        # Create NEW session manager (simulating restart)
        mgr2 = SessionManager(sessions_dir)
        meta2 = mgr2.open_session(meta1.id)
        
        # Verify metadata loaded correctly
        assert meta2.id == meta1.id
        assert meta2.title == "Reopen Test"
        assert meta2.active_seat == "agy"
        assert meta2.native["agy"] == "native-789"
        
        # Verify transcript loaded correctly
        transcript = mgr2.read_transcript(meta1.id)
        assert len(transcript) == 2
        assert transcript[0].text == "Message 1"
        assert transcript[1].text == "Reply 1"

    def test_multiple_sessions_coexist(self, integration_env):
        """Multiple sessions can exist independently."""
        sessions_dir = integration_env["sessions_dir"]
        
        mgr = SessionManager(sessions_dir)
        
        # Create multiple sessions
        meta1 = mgr.create_session("Session One")
        meta2 = mgr.create_session("Session Two")
        meta3 = mgr.create_session("Session Three")
        
        # Add different messages to each
        mgr.append_message(meta1.id, "user", "One message")
        mgr.append_message(meta2.id, "user", "Two message")
        mgr.append_message(meta3.id, "user", "Three message")
        
        # Verify all sessions exist
        assert (sessions_dir / meta1.id).exists()
        assert (sessions_dir / meta2.id).exists()
        assert (sessions_dir / meta3.id).exists()
        
        # Verify list_sessions returns all
        sessions = mgr.list_sessions(limit=10)
        assert len(sessions) >= 3
        session_ids = [s.id for s in sessions]
        assert meta1.id in session_ids
        assert meta2.id in session_ids
        assert meta3.id in session_ids
        
        # Verify each has correct transcript
        t1 = mgr.read_transcript(meta1.id)
        t2 = mgr.read_transcript(meta2.id)
        t3 = mgr.read_transcript(meta3.id)
        
        assert t1[0].text == "One message"
        assert t2[0].text == "Two message"
        assert t3[0].text == "Three message"

    def test_update_operations_persist(self, integration_env):
        """Session updates write to disk correctly."""
        sessions_dir = integration_env["sessions_dir"]
        
        mgr = SessionManager(sessions_dir)
        meta = mgr.create_session("Update Test")
        
        # Update seat
        mgr.update_seat(meta.id, "agy", "native-456")
        
        # Verify by reading meta.json directly
        meta_file = sessions_dir / meta.id / "meta.json"
        with open(meta_file) as f:
            data = json.load(f)
        assert data["active_seat"] == "agy"
        assert data["native"]["agy"] == "native-456"
        
        # Update mode
        mgr.update_mode(meta.id, "task")
        
        # Verify again
        with open(meta_file) as f:
            data = json.load(f)
        assert data["mode"] == "task"

    def test_session_survives_process_boundary(self, integration_env):
        """Session persists across process-like boundaries."""
        sessions_dir = integration_env["sessions_dir"]
        
        # Phase 1: Create and populate
        mgr1 = SessionManager(sessions_dir)
        meta = mgr1.create_session("Cross Process Test")
        mgr1.append_message(meta.id, "user", "First message")
        session_id = meta.id
        
        # Explicitly delete manager (simulate process exit)
        del mgr1
        
        # Phase 2: New "process" (new manager instance)
        mgr2 = SessionManager(sessions_dir)
        
        # Should be able to list and find the session
        sessions = mgr2.list_sessions()
        assert any(s.id == session_id for s in sessions)
        
        # Should be able to open and read
        meta2 = mgr2.open_session(session_id)
        transcript = mgr2.read_transcript(session_id)
        
        assert meta2.title == "Cross Process Test"
        assert len(transcript) == 1
        assert transcript[0].text == "First message"
        
        # Should be able to continue
        mgr2.append_message(session_id, "assistant", "Response after restart")
        transcript = mgr2.read_transcript(session_id)
        assert len(transcript) == 2

    def test_corrupted_session_skipped_in_list(self, integration_env):
        """Corrupted sessions don't break list_sessions."""
        sessions_dir = integration_env["sessions_dir"]
        
        mgr = SessionManager(sessions_dir)
        
        # Create a good session
        meta = mgr.create_session("Good Session")
        
        # Create a corrupted session directory
        bad_dir = sessions_dir / "2026-10-14-corrupted"
        bad_dir.mkdir()
        bad_meta = bad_dir / "meta.json"
        bad_meta.write_text("{ invalid json")
        
        # list_sessions should not crash
        sessions = mgr.list_sessions()
        
        # Should still find the good one
        assert any(s.id == meta.id for s in sessions)
        
        # Should not include the bad one
        assert not any(s.id == "2026-10-14-corrupted" for s in sessions)
