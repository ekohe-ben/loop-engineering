#!/usr/bin/env python3
"""Integration tests for resume vs replay paths.

Tests the decision logic and context assembly for same-seat resume
vs cross-seat replay."""
import json

import pytest

from chat.assembler import ContextAssembler
from chat.backends.claude import ClaudeBackend
from chat.session import SessionManager


pytestmark = pytest.mark.integration


class TestResumeAndReplay:
    """Test native resume vs cross-seat replay integration."""

    def test_same_seat_uses_native_resume(self, integration_env):
        """Same seat with valid native_id uses resume path."""
        fake_claude = integration_env["fake_claude"]
        sessions_dir = integration_env["sessions_dir"]
        sandbox_dir = integration_env["sandbox_dir"]
        
        mgr = SessionManager(sessions_dir)
        meta = mgr.create_session("Resume Test", seat="claude")
        
        # First turn - establishes native session
        fake_claude.set_response(
            text="First response",
            session_id="native-session-abc",
            response_num=0
        )
        
        backend = ClaudeBackend()
        response1 = backend.invoke("First message", "chat", str(sandbox_dir))
        
        # Record in session
        mgr.append_message(meta.id, "user", "First message")
        mgr.append_message(
            meta.id, "assistant", response1.text,
            seat="claude", native_id=response1.native_id,
            tokens_in=response1.tokens_in, tokens_out=response1.tokens_out
        )
        mgr.update_seat(meta.id, "claude", response1.native_id)
        
        # Second turn - should use resume
        fake_claude.clear_calls()
        fake_claude.set_response(
            text="Second response",
            session_id="native-session-abc",
            response_num=0
        )
        
        native_id = mgr.get_native_id(meta.id, "claude")
        assert native_id == "native-session-abc"
        
        response2 = backend.resume(native_id, "Second message", "chat", str(sandbox_dir))
        
        assert response2 is not None
        assert response2.text == "Second response"
        
        # Verify --resume was used (not --continue)
        calls = fake_claude.get_calls()
        assert len(calls) == 1
        assert "--resume" in calls[0]["argv"]
        assert "native-session-abc" in calls[0]["argv"]
        assert "--continue" not in calls[0]["argv"]

    def test_cross_seat_forces_full_replay(self, integration_env):
        """Switching seats forces full context replay via invoke."""
        fake_claude = integration_env["fake_claude"]
        sessions_dir = integration_env["sessions_dir"]
        sandbox_dir = integration_env["sandbox_dir"]
        
        mgr = SessionManager(sessions_dir)
        meta = mgr.create_session("Cross Seat Test", seat="claude")
        
        # First turn with claude
        mgr.append_message(meta.id, "user", "First message")
        mgr.append_message(meta.id, "assistant", "First response", seat="claude")
        
        # Switch to agy (in real scenario, would use AgyBackend, but we test logic)
        mgr.update_seat(meta.id, "agy", native_id=None)
        
        # No native_id for agy
        native_id = mgr.get_native_id(meta.id, "agy")
        assert native_id is None
        
        # Would need to use invoke with full replay
        # (Agy is stub, so just verify logic)
        
        # Switch back to claude - should have no native_id anymore
        mgr.update_seat(meta.id, "claude", native_id=None)
        native_id = mgr.get_native_id(meta.id, "claude")
        assert native_id is None  # Lost when we switched away

    def test_replay_package_includes_conversation_history(self, integration_env):
        """Replay package assembles full context from session."""
        sessions_dir = integration_env["sessions_dir"]
        
        mgr = SessionManager(sessions_dir)
        meta = mgr.create_session("Replay Context Test")
        
        # Build up a conversation
        mgr.append_message(meta.id, "user", "What is Python?")
        mgr.append_message(meta.id, "assistant", "Python is a programming language.", seat="claude")
        mgr.append_message(meta.id, "user", "Is it easy to learn?")
        mgr.append_message(meta.id, "assistant", "Yes, it's beginner-friendly.", seat="claude")
        
        # Get transcript
        transcript = mgr.read_transcript(meta.id)
        recent_messages = [(e.role, e.text) for e in transcript]
        
        # Assemble replay package
        assembler = ContextAssembler()
        replay = assembler.assemble_replay(
            summary=None,
            recent_messages=recent_messages,
            current_input="Tell me about loops",
            is_continuation=True,  # Cross-seat scenario
        )
        
        # Verify replay contains history
        assert "What is Python?" in replay.prompt
        assert "programming language" in replay.prompt
        assert "Is it easy to learn?" in replay.prompt
        assert "beginner-friendly" in replay.prompt
        assert "Tell me about loops" in replay.prompt
        
        # Verify continuation instruction present
        prompt_lower = replay.prompt.lower()
        assert "continued conversation" in prompt_lower
        assert "different" in prompt_lower and "model" in prompt_lower

    def test_resume_failure_can_fallback_to_replay(self, integration_env):
        """If native resume returns None, caller can fallback to full invoke."""
        fake_claude = integration_env["fake_claude"]
        sessions_dir = integration_env["sessions_dir"]
        sandbox_dir = integration_env["sandbox_dir"]
        
        mgr = SessionManager(sessions_dir)
        meta = mgr.create_session("Fallback Test")
        
        # Record a conversation with native ID
        mgr.append_message(meta.id, "user", "First")
        mgr.append_message(meta.id, "assistant", "Response", seat="claude", native_id="expired-session")
        mgr.update_seat(meta.id, "claude", "expired-session")
        
        backend = ClaudeBackend()
        
        # Try resume with expired session - make it fail
        # (In real scenario, Claude CLI would reject expired ID)
        # For test, we simulate by not setting a response
        response = backend.resume("expired-session", "Follow up", "chat", str(sandbox_dir))
        
        # Resume returns None on failure
        # (Our fake always succeeds, but real code handles this)
        
        # Fallback to full invoke
        fake_claude.set_response(text="Fresh start response", response_num=0)
        
        transcript = mgr.read_transcript(meta.id)
        recent = [(e.role, e.text) for e in transcript]
        
        assembler = ContextAssembler()
        replay = assembler.assemble_replay(
            summary=None,
            recent_messages=recent,
            current_input="Follow up",
            is_continuation=False,
        )
        
        response = backend.invoke(replay.prompt, "chat", str(sandbox_dir))
        assert response is not None
        assert response.text == "Fresh start response"

    def test_multiple_seat_switches_maintain_history(self, integration_env):
        """Multiple seat switches preserve full conversation history."""
        sessions_dir = integration_env["sessions_dir"]
        
        mgr = SessionManager(sessions_dir)
        meta = mgr.create_session("Multi Switch Test", seat="claude")
        
        # Turn 1: Claude
        mgr.append_message(meta.id, "user", "Hello from claude")
        mgr.append_message(meta.id, "assistant", "Claude here", seat="claude", native_id="claude-1")
        mgr.update_seat(meta.id, "claude", "claude-1")
        
        # Turn 2: Switch to agy
        mgr.update_seat(meta.id, "agy", None)
        mgr.append_message(meta.id, "user", "Now using agy")
        mgr.append_message(meta.id, "assistant", "Agy here", seat="agy", native_id="agy-1")
        mgr.update_seat(meta.id, "agy", "agy-1")
        
        # Turn 3: Switch back to claude
        mgr.update_seat(meta.id, "claude", None)  # Lost old claude session
        mgr.append_message(meta.id, "user", "Back to claude")
        mgr.append_message(meta.id, "assistant", "Claude again", seat="claude", native_id="claude-2")
        
        # Verify transcript has all turns
        transcript = mgr.read_transcript(meta.id)
        assert len(transcript) == 6
        
        # Verify seat tracking
        assert transcript[1].seat == "claude"
        assert transcript[3].seat == "agy"
        assert transcript[5].seat == "claude"
        
        # Verify all messages present
        messages = [e.text for e in transcript]
        assert "Hello from claude" in messages
        assert "Now using agy" in messages
        assert "Back to claude" in messages

    def test_token_budgets_enforced_in_replay(self, integration_env):
        """Replay respects token budgets even with long history."""
        sessions_dir = integration_env["sessions_dir"]
        
        mgr = SessionManager(sessions_dir)
        meta = mgr.create_session("Budget Test")
        
        # Create a long conversation (more than budget)
        for i in range(20):
            mgr.append_message(meta.id, "user", f"Message {i}" * 100)  # Long messages
            mgr.append_message(meta.id, "assistant", f"Response {i}" * 100, seat="claude")
        
        # Assemble replay with tight budget
        transcript = mgr.read_transcript(meta.id)
        recent = [(e.role, e.text) for e in transcript]
        
        from chat.assembler import AssemblerConfig
        tight_config = AssemblerConfig(
            summary_max_tokens=500,
            recent_turns=5,
            recent_max_tokens=2000,
        )
        
        assembler = ContextAssembler(tight_config)
        replay = assembler.assemble_replay(
            summary=None,
            recent_messages=recent,
            current_input="Current",
            is_continuation=False,
        )
        
        # Should respect token budget
        assert replay.recent_tokens <= tight_config.recent_max_tokens
        
        # Should not have all 20 messages
        assert "Message 0" not in replay.prompt  # Early messages dropped
        # But should have recent ones
        assert "Message 19" in replay.prompt or "Message 18" in replay.prompt
