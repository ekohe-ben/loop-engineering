#!/usr/bin/env python3
"""Integration tests for REPL/CLI entry point.

Tests bin/loop_chat.py through programmatic invocation (non-interactive)."""
import json
import subprocess
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.integration


class TestREPLSmoke:
    """Smoke tests for REPL entry point."""

    def test_repl_can_be_imported(self):
        """REPL module imports without errors."""
        from chat.repl import ChatREPL
        
        # Should be instantiable
        repl = ChatREPL()
        assert repl is not None

    def test_repl_starts_with_temp_home(self, integration_env):
        """REPL starts successfully with temp LOOP_ENGINEERING_HOME."""
        from chat.repl import ChatREPL
        
        sessions_dir = integration_env["sessions_dir"]
        sandbox_dir = integration_env["sandbox_dir"]
        
        # Create REPL with specific dirs
        repl = ChatREPL(
            sessions_root=str(sessions_dir),
            sandbox_dir=str(sandbox_dir),
        )
        
        assert repl.session_mgr is not None
        assert repl.sandbox_dir == sandbox_dir
        assert repl.assembler is not None

    def test_repl_handle_message_flow(self, integration_env):
        """REPL._handle_message processes a full turn."""
        fake_claude = integration_env["fake_claude"]
        sessions_dir = integration_env["sessions_dir"]
        sandbox_dir = integration_env["sandbox_dir"]
        
        from chat.repl import ChatREPL
        from chat.session import SessionManager
        
        # Set up response
        fake_claude.set_response(
            text="REPL response",
            session_id="repl-session-1",
        )
        
        # Create session first
        mgr = SessionManager(sessions_dir)
        meta = mgr.create_session("REPL Test", seat="claude")
        
        # Create REPL
        repl = ChatREPL(
            sessions_root=str(sessions_dir),
            sandbox_dir=str(sandbox_dir),
        )
        
        # Open session
        repl.current_session = meta
        from chat.backends import get_backend
        repl.current_backend = get_backend("claude")
        
        # Handle a message (simulating REPL flow)
        repl._handle_message("Test message")
        
        # Verify transcript was updated
        transcript = mgr.read_transcript(meta.id)
        assert len(transcript) == 2  # User + assistant
        assert transcript[0].role == "user"
        assert transcript[0].text == "Test message"
        assert transcript[1].role == "assistant"
        assert transcript[1].text == "REPL response"
        
        # Verify subprocess was called
        calls = fake_claude.get_calls()
        assert len(calls) == 1

    def test_repl_seat_switch_command(self, integration_env):
        """REPL /seat command switches backend."""
        sessions_dir = integration_env["sessions_dir"]
        sandbox_dir = integration_env["sandbox_dir"]
        
        from chat.repl import ChatREPL
        from chat.session import SessionManager
        
        mgr = SessionManager(sessions_dir)
        meta = mgr.create_session("Switch Test", seat="claude")
        
        repl = ChatREPL(
            sessions_root=str(sessions_dir),
            sandbox_dir=str(sandbox_dir),
        )
        
        repl.current_session = meta
        from chat.backends import get_backend
        repl.current_backend = get_backend("claude")
        
        # Execute seat switch command
        result = repl._handle_command("/seat agy")
        
        # Should continue (not exit)
        assert result is True
        
        # Backend should be switched (though agy is stub)
        assert repl.current_backend.name == "agy"
        
        # Session metadata should be updated
        updated_meta = mgr.open_session(meta.id)
        assert updated_meta.active_seat == "agy"

    def test_repl_mode_switch_command(self, integration_env):
        """REPL /mode command switches mode."""
        sessions_dir = integration_env["sessions_dir"]
        sandbox_dir = integration_env["sandbox_dir"]
        
        from chat.repl import ChatREPL
        from chat.session import SessionManager
        
        mgr = SessionManager(sessions_dir)
        meta = mgr.create_session("Mode Test", seat="claude", mode="chat")
        
        repl = ChatREPL(
            sessions_root=str(sessions_dir),
            sandbox_dir=str(sandbox_dir),
        )
        
        repl.current_session = meta
        from chat.backends import get_backend
        repl.current_backend = get_backend("claude")
        
        # Switch to task mode
        result = repl._handle_command("/mode task")
        
        assert result is True
        assert repl.current_session.mode == "task"
        
        # Verify persisted
        updated_meta = mgr.open_session(meta.id)
        assert updated_meta.mode == "task"

    def test_repl_end_command_exits(self, integration_env):
        """REPL /end command triggers exit."""
        sessions_dir = integration_env["sessions_dir"]
        sandbox_dir = integration_env["sandbox_dir"]
        
        from chat.repl import ChatREPL
        from chat.session import SessionManager
        
        mgr = SessionManager(sessions_dir)
        meta = mgr.create_session("End Test", seat="claude")
        
        repl = ChatREPL(
            sessions_root=str(sessions_dir),
            sandbox_dir=str(sandbox_dir),
        )
        
        repl.current_session = meta
        
        # Execute end command
        result = repl._handle_command("/end")
        
        # Should return False to exit REPL loop
        assert result is False

    def test_cli_entry_point_exists(self):
        """bin/loop_chat.py exists and is executable."""
        cli_path = Path(__file__).parent.parent.parent.parent / "bin" / "loop_chat.py"
        
        assert cli_path.exists()
        assert cli_path.is_file()
        # Check if executable (on Unix)
        import stat
        mode = cli_path.stat().st_mode
        assert mode & stat.S_IXUSR or mode & stat.S_IXGRP or mode & stat.S_IXOTH

    def test_cli_can_be_invoked(self, integration_env, tmp_path):
        """CLI can be invoked as a subprocess (list sessions)."""
        loop_home = integration_env["loop_home"]
        sessions_dir = integration_env["sessions_dir"]
        
        # Create a session so list isn't empty
        from chat.session import SessionManager
        mgr = SessionManager(sessions_dir)
        mgr.create_session("CLI Test Session")
        
        # Find the CLI script
        cli_path = Path(__file__).parent.parent.parent.parent / "bin" / "loop_chat.py"
        
        # Invoke it with no args (should show session list and not hang)
        # Use timeout to prevent hanging
        result = subprocess.run(
            [sys.executable, str(cli_path)],
            env={**subprocess.os.environ, "LOOP_ENGINEERING_HOME": str(loop_home)},
            capture_output=True,
            text=True,
            timeout=5,
        )
        
        # Should not crash (exit code doesn't matter for display-only)
        # Should mention sessions or Loop X
        output = result.stdout + result.stderr
        assert "Loop X" in output or "session" in output.lower()

    def test_repl_two_turn_conversation(self, integration_env):
        """REPL handles a two-turn conversation correctly."""
        fake_claude = integration_env["fake_claude"]
        sessions_dir = integration_env["sessions_dir"]
        sandbox_dir = integration_env["sandbox_dir"]
        
        from chat.repl import ChatREPL
        from chat.session import SessionManager
        
        # Set up two responses
        fake_claude.set_response(text="First reply", session_id="sess-1", response_num=0)
        
        mgr = SessionManager(sessions_dir)
        meta = mgr.create_session("Two Turn Test", seat="claude")
        
        repl = ChatREPL(
            sessions_root=str(sessions_dir),
            sandbox_dir=str(sandbox_dir),
        )
        
        repl.current_session = meta
        from chat.backends import get_backend
        repl.current_backend = get_backend("claude")
        
        # Turn 1
        repl._handle_message("First message")
        
        transcript = mgr.read_transcript(meta.id)
        assert len(transcript) == 2
        assert transcript[1].text == "First reply"
        
        # Set up second response
        fake_claude.clear_calls()
        fake_claude.set_response(text="Second reply", session_id="sess-1", response_num=0)
        
        # Turn 2 - should use resume (has native_id from turn 1)
        repl._handle_message("Second message")
        
        transcript = mgr.read_transcript(meta.id)
        assert len(transcript) == 4
        assert transcript[3].text == "Second reply"
        
        # Verify second call used --continue
        calls = fake_claude.get_calls()
        assert len(calls) == 1
        assert "--continue" in calls[0]["argv"]
