#!/usr/bin/env python3
"""Snapshot tests for backend adapter argv_for() - pure functions that don't
execute anything, so fast and deterministic. See design PDF section 6."""
import pytest

from chat.backends.claude import ClaudeBackend
from chat.backends.agy import AgyBackend


class TestClaudeBackendArgv:
    """Test Claude backend command-line argument generation."""

    def test_invoke_chat_mode(self):
        """Fresh invoke in chat mode - no tools allowed."""
        backend = ClaudeBackend()
        argv = backend.argv_for("Hello world", mode="chat", native_id=None)
        
        assert "claude" == argv[0]
        assert "-p" in argv
        assert "--permission-mode" in argv
        assert "acceptEdits" in argv
        assert "--allowedTools" in argv
        assert "" in argv  # Empty tool allowlist for chat mode
        assert "--output-format" in argv
        assert "json" in argv
        assert "Hello world" == argv[-1]
        assert "--continue" not in argv

    def test_invoke_task_mode(self):
        """Fresh invoke in task mode - tools allowed."""
        backend = ClaudeBackend()
        argv = backend.argv_for("Do something", mode="task", native_id=None)
        
        assert "claude" == argv[0]
        assert "-p" in argv
        assert "--allowedTools" in argv
        # Should have some tools listed
        tools_idx = argv.index("--allowedTools")
        tools = argv[tools_idx + 1]
        assert tools != ""
        assert "read_file" in tools or "write_file" in tools
        assert "Do something" == argv[-1]

    def test_resume_with_native_id(self):
        """Resume existing session with --continue."""
        backend = ClaudeBackend()
        argv = backend.argv_for("Follow up", mode="chat", native_id="session-123")
        
        assert "claude" == argv[0]
        assert "--continue" in argv
        assert "session-123" in argv
        assert "Follow up" == argv[-1]

    def test_resume_without_native_id_falls_back_to_invoke(self):
        """Resume with None native_id is same as invoke."""
        backend = ClaudeBackend()
        argv_invoke = backend.argv_for("Test", mode="chat", native_id=None)
        argv_resume = backend.argv_for("Test", mode="chat", native_id=None)
        
        assert argv_invoke == argv_resume
        assert "--continue" not in argv_resume


class TestAgyBackendArgv:
    """Test Antigravity backend command-line argument generation (stub)."""

    def test_invoke_structure(self):
        """Verify agy argv structure even though backend is stub."""
        backend = AgyBackend()
        argv = backend.argv_for("Test prompt", mode="chat", native_id=None)
        
        assert "agy" == argv[0]
        assert "-p" in argv
        assert "--output-format" in argv
        assert "json" in argv
        assert "Test prompt" == argv[-1]

    def test_resume_has_continue_flag(self):
        """Resume should include --continue or --conversation."""
        backend = AgyBackend()
        argv = backend.argv_for("Follow up", mode="chat", native_id="conv-456")
        
        assert "agy" == argv[0]
        # Stub uses --continue; may change when implemented
        assert "--continue" in argv
        assert "conv-456" in argv


class TestBackendSelection:
    """Test backend factory function."""

    def test_get_claude_backend(self):
        """get_backend('claude') returns ClaudeBackend."""
        from chat.backends import get_backend
        
        backend = get_backend("claude")
        assert isinstance(backend, ClaudeBackend)
        assert backend.name == "claude"

    def test_get_agy_backend(self):
        """get_backend('agy') returns AgyBackend."""
        from chat.backends import get_backend
        
        backend = get_backend("agy")
        assert isinstance(backend, AgyBackend)
        assert backend.name == "agy"

    def test_unknown_backend_raises(self):
        """get_backend with unknown name raises ValueError."""
        from chat.backends import get_backend
        
        with pytest.raises(ValueError, match="Unknown backend"):
            get_backend("unknown")
