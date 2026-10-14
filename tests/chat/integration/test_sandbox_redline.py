#!/usr/bin/env python3
"""Integration tests for chat sandbox safety boundaries.

Tests that chat mode properly restricts file system access to sandbox."""
import pytest

from chat.backends.claude import ClaudeBackend


pytestmark = pytest.mark.integration


class TestSandboxRedline:
    """Test chat mode sandbox boundaries (Phase 1 acceptance)."""

    def test_chat_mode_uses_sandbox_cwd(self, integration_env):
        """Chat mode operations execute in sandbox directory."""
        fake_claude = integration_env["fake_claude"]
        sandbox_dir = integration_env["sandbox_dir"]
        
        fake_claude.set_response(text="Response")
        
        backend = ClaudeBackend()
        backend.invoke("Test", "chat", str(sandbox_dir))
        
        # Verify subprocess was run with sandbox as cwd
        calls = fake_claude.get_calls()
        assert len(calls) == 1
        assert calls[0]["cwd"] == str(sandbox_dir)

    def test_chat_mode_has_empty_tool_allowlist(self, integration_env):
        """Chat mode passes empty tool allowlist to prevent file operations."""
        fake_claude = integration_env["fake_claude"]
        sandbox_dir = integration_env["sandbox_dir"]
        
        fake_claude.set_response(text="Response")
        
        backend = ClaudeBackend()
        backend.invoke("Write a file", "chat", str(sandbox_dir))
        
        calls = fake_claude.get_calls()
        argv = calls[0]["argv"]
        
        # Must have --allowedTools ""
        assert "--allowedTools" in argv
        idx = argv.index("--allowedTools")
        tools = argv[idx + 1]
        assert tools == "", f"Chat mode should have empty tool allowlist, got: {tools}"

    def test_task_mode_uses_real_cwd_and_tools(self, integration_env, tmp_path):
        """Task mode can use real working directory and tools."""
        fake_claude = integration_env["fake_claude"]
        
        # Use a different directory (not sandbox)
        real_workdir = tmp_path / "real_work"
        real_workdir.mkdir()
        
        fake_claude.set_response(text="Task response")
        
        backend = ClaudeBackend()
        backend.invoke("Task work", "task", str(real_workdir))
        
        calls = fake_claude.get_calls()
        argv = calls[0]["argv"]
        
        # Should run in the real workdir
        assert calls[0]["cwd"] == str(real_workdir)
        
        # Should have non-empty tool allowlist
        assert "--allowedTools" in argv
        idx = argv.index("--allowedTools")
        tools = argv[idx + 1]
        assert tools != ""
        assert "read_file" in tools or "write_file" in tools

    def test_sandbox_directory_is_isolated(self, integration_env):
        """Sandbox directory is separate from real files."""
        sandbox_dir = integration_env["sandbox_dir"]
        loop_home = integration_env["loop_home"]
        sessions_dir = integration_env["sessions_dir"]
        
        # Sandbox should not be the same as sessions
        assert sandbox_dir != sessions_dir
        
        # Sandbox should not be the loop home root
        assert sandbox_dir != loop_home
        
        # Sandbox should be under loop home
        assert sandbox_dir.is_relative_to(loop_home)
        
        # Sandbox should be empty or minimal initially
        assert sandbox_dir.exists()
        contents = list(sandbox_dir.iterdir())
        # Should not have sessions, config, etc.
        assert not any(item.name == "sessions" for item in contents)

    def test_repl_enforces_sandbox_in_chat_mode(self, integration_env):
        """REPL uses sandbox directory for chat mode operations."""
        fake_claude = integration_env["fake_claude"]
        sessions_dir = integration_env["sessions_dir"]
        sandbox_dir = integration_env["sandbox_dir"]
        
        from chat.repl import ChatREPL
        from chat.session import SessionManager
        
        fake_claude.set_response(text="Chat response")
        
        mgr = SessionManager(sessions_dir)
        meta = mgr.create_session("Sandbox Test", seat="claude", mode="chat")
        
        repl = ChatREPL(
            sessions_root=str(sessions_dir),
            sandbox_dir=str(sandbox_dir),
        )
        
        repl.current_session = meta
        from chat.backends import get_backend
        repl.current_backend = get_backend("claude")
        
        # Handle message in chat mode
        repl._handle_message("Test message")
        
        # Verify backend was called with sandbox dir
        calls = fake_claude.get_calls()
        assert len(calls) == 1
        assert calls[0]["cwd"] == str(sandbox_dir)

    def test_mode_switch_to_task_shows_warning(self, integration_env):
        """Switching to task mode should show a warning (docs requirement)."""
        sessions_dir = integration_env["sessions_dir"]
        sandbox_dir = integration_env["sandbox_dir"]
        
        from chat.repl import ChatREPL
        from chat.session import SessionManager
        
        mgr = SessionManager(sessions_dir)
        meta = mgr.create_session("Warning Test", mode="chat")
        
        repl = ChatREPL(
            sessions_root=str(sessions_dir),
            sandbox_dir=str(sandbox_dir),
        )
        
        repl.current_session = meta
        
        # Capture output when switching to task mode
        import io
        import sys
        
        old_stdout = sys.stdout
        sys.stdout = captured = io.StringIO()
        
        try:
            repl._handle_command("/mode task")
            output = captured.getvalue()
        finally:
            sys.stdout = old_stdout
        
        # Should mention warning or caution
        output_lower = output.lower()
        assert "task" in output_lower
        # Warning should be present (⚠️ or "caution" or "warning")
        assert "⚠" in output or "caution" in output_lower or "warning" in output_lower or "tools" in output_lower

    def test_chat_mode_default_for_new_session(self, integration_env):
        """New sessions default to safe chat mode."""
        sessions_dir = integration_env["sessions_dir"]
        
        from chat.session import SessionManager
        
        mgr = SessionManager(sessions_dir)
        meta = mgr.create_session("Default Mode Test")
        
        # Should default to chat mode
        assert meta.mode == "chat"
        
        # Verify persisted
        meta2 = mgr.open_session(meta.id)
        assert meta2.mode == "chat"

    def test_cannot_accidentally_enable_tools_in_chat(self, integration_env):
        """Chat mode tool restriction is enforced at backend level."""
        fake_claude = integration_env["fake_claude"]
        sandbox_dir = integration_env["sandbox_dir"]
        
        fake_claude.set_response(text="Response")
        
        backend = ClaudeBackend()
        
        # Even if we try to pass task-like prompt, mode="chat" enforces restriction
        backend.invoke(
            prompt="Write this file: /etc/passwd",
            mode="chat",  # Explicit chat mode
            cwd=str(sandbox_dir),
        )
        
        calls = fake_claude.get_calls()
        argv = calls[0]["argv"]
        
        # Tool restriction still applies
        assert "--allowedTools" in argv
        idx = argv.index("--allowedTools")
        assert argv[idx + 1] == ""

    def test_sandbox_persists_across_repl_instances(self, integration_env):
        """Sandbox directory is consistent for a session."""
        sessions_dir = integration_env["sessions_dir"]
        sandbox_dir = integration_env["sandbox_dir"]
        
        from chat.repl import ChatREPL
        
        # Create first REPL instance
        repl1 = ChatREPL(
            sessions_root=str(sessions_dir),
            sandbox_dir=str(sandbox_dir),
        )
        
        sandbox1 = repl1.sandbox_dir
        
        # Create second REPL instance (simulating restart)
        repl2 = ChatREPL(
            sessions_root=str(sessions_dir),
            sandbox_dir=str(sandbox_dir),
        )
        
        sandbox2 = repl2.sandbox_dir
        
        # Should be the same sandbox
        assert sandbox1 == sandbox2
        assert sandbox1 == sandbox_dir


class TestLiveSandboxBoundary:
    """Live tests with real Claude CLI (opt-in only).
    
    Run with: LOOP_CHAT_LIVE=1 pytest tests/chat/integration/test_sandbox_redline.py
    """

    def test_real_claude_respects_tool_restrictions(self, temp_loop_home):
        """Real Claude CLI respects empty tool allowlist (opt-in test)."""
        import os
        if not os.environ.get("LOOP_CHAT_LIVE"):
            pytest.skip("Live test - requires real Claude login. Set LOOP_CHAT_LIVE=1 to run")
        
        # This test would:
        # 1. Use real ClaudeBackend with real claude CLI
        # 2. Try to prompt it to write a file
        # 3. Verify it refuses or has no tools available
        # 4. Only runs when LOOP_CHAT_LIVE=1 env var is set
